"""Laya Brain: layered, bilingual intent decisions.

Decision pipeline (fastest first, each layer only runs if the previous one
is not confident):

1. normalize   - strip wake words / fillers / dictation punctuation      (<0.1ms)
2. rules       - precise bilingual patterns with parameter extraction     (<1ms)
3. semantic    - fuzzy bilingual matcher tolerant of ASR mistakes         (~1ms)
4. Core ML     - Laya typed-decision model, only when already warm        (seconds on Intel)

`plan()` additionally splits compound commands ("open safari and play music")
into ordered steps and resolves pronouns ("close it") from session context.
"""

import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import DEFAULT_COMPUTE_UNITS, DEFAULT_MODEL_DIR, is_apple_silicon
from ..tools.apps import normalize_app_name, resolve_app
from ..tools.web import site_url
from .context import context_engine
from .nlu import (
    normalize,
    parse_duration,
    parse_number,
    semantic_matcher,
    split_commands,
    spoken_email,
)

SEMANTIC_ACCEPT = 0.62
SEMANTIC_SUGGEST = 0.45
COREML_TIMEOUT_S = 6.0

# Requests that reason over content already on the Mac -> read it, then think.
_CONTENT_RE = re.compile(
    r"\b(summari[sz]e|summary|muhtasari|translate|tafsiri|explain|eleza|rewrite|proofread|reply to|jibu|what does|meaning of|maana ya|analy[sz]e|extract)\b",
    re.IGNORECASE,
)
_SCREEN_RE = re.compile(r"\b(screen|kioo|skrini|window|this page|ukurasa huu)\b", re.IGNORECASE)
_CLIPBOARD_RE = re.compile(r"\b(clipboard|copied|nilichonakili|ubao)\b", re.IGNORECASE)

# Questions and open conversation -> answered directly by the local model.
_QUESTION_RE = re.compile(
    r"^(what|who|whom|whose|why|how|when|which|is|are|was|were|can|could|should|would|will|do|does|did|explain|define|describe|"
    r"tell me|write( me)? a (poem|story|song|joke|haiku)|give me (some )?(ideas|tips|advice|a)|joke|translate|"
    r"nini|nani|kwa nini|vipi|lini|je|eleza|nieleze|niambie|nipe (wazo|ushauri|mawazo)|andika shairi|habari)\b",
    re.IGNORECASE,
)

# Actions the AI may propose but must never run without the user's OK.
LLM_CONFIRM = {
    ("messaging", "send"),
    ("mail", "send"),
    ("apps", "quit"),
    ("system", "lock_screen"),
    ("system", "sleep"),
    ("files", "create"),
    ("notes", "create"),
    ("notes", "update"),
    ("clipboard", "write"),
    ("clipboard", "clear"),
    ("workspaces", "delete"),
}

# Tools that activate their own app, making a preceding "open <app>" step redundant.
SELF_OPENING = {"notes": "Notes", "mail": "Mail", "messaging": None}

# Intents whose parameters swallow free text; for these, " and " is usually part of the content.
CONTENT_INTENTS = {
    ("music", "play_song"),
    ("workspaces", "create"),
    ("workspaces", "add"),
    ("messaging", "send"),
    ("notes", "create"),
    ("notes", "update"),
    ("mail", "send"),
    ("timer", "remind"),
    ("web", "search"),
    ("web", "youtube"),
}


@dataclass
class IntentDecision:
    domain: str
    action: str
    params: Dict[str, Any]
    confidence: float
    requires_confirmation: bool
    source: str  # "rules" | "semantic" | "coreml" | "fallback"
    text: str = ""
    alternatives: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def handled(self) -> bool:
        return self.domain != "general"


_MSG_APP_RE = re.compile(
    r"\s*\b(?:on|via|using|through|in|with|kwa|kwenye|kupitia)\s+(whats\s?app|imessage|messages|sms|text message)\b",
    re.IGNORECASE,
)
_SAY_RE = r"(?:saying|sayin\w*|say|sey\w*|that says|that|telling (?:him|her|them)|tell (?:him|her|them)|and say|with (?:the )?(?:message|text)|message|kwamba|useme|ukisema|akisema|:)"


def _message_app(text: str) -> str:
    t = text.lower()
    if re.search(r"whats\s?app|wasap|watsap", t):
        return "WhatsApp"
    if re.search(r"\b(imessage|messages app|sms)\b", t):
        return "Messages"
    return ""


# "open whatsapp (and) send …" / "fungua whatsapp, tuma …": the app to use, said up front.
_OPEN_MSG_APP_RE = re.compile(
    r"^(?:open|launch|start|go to|fungua)\s+(?:the\s+)?(whats\s?app|imessage|messages)(?:\s+app)?\b[\s,.;:]*"
    r"(?:(?:and then|and|then|na|halafu|alafu|kisha)\b\s*)?",
    re.IGNORECASE,
)
# Words a spoken message usually starts with, used to find where the name ends when the
# user didn't say "saying": "message john hello there", "send a message to mama I'm late".
_MSG_STARTERS = {
    "hi",
    "hello",
    "hey",
    "yo",
    "habari",
    "mambo",
    "niaje",
    "vipi",
    "shikamoo",
    "salaam",
    "salam",
    "good",
    "i",
    "i'm",
    "im",
    "i'll",
    "ill",
    "i've",
    "i'd",
    "we",
    "we're",
    "we'll",
    "you",
    "you're",
    "are",
    "can",
    "could",
    "will",
    "would",
    "please",
    "call",
    "come",
    "where",
    "when",
    "what",
    "how",
    "why",
    "did",
    "do",
    "don't",
    "dont",
    "let's",
    "lets",
    "see",
    "thanks",
    "thank",
    "happy",
    "sorry",
    "ok",
    "okay",
    "yes",
    "no",
    "meet",
    "nimefika",
    "nipo",
    "naja",
    "nakuja",
    "nitachelewa",
    "asante",
    "pole",
    "karibu",
    "is",
    "it's",
    "its",
}
_NOT_RECIPIENTS = {"me", "us", "a", "an", "the", "about", "him", "her", "them", "it", "size"}


def _split_name_text(rest: str, allow_guess: bool) -> Optional[Tuple[str, str]]:
    """'john hello there' -> ('john', 'hello there'); 'festo manolo' -> ('festo manolo', '')."""
    words = rest.split()
    if not words or words[0].lower().strip(",.:") in _NOT_RECIPIENTS:
        return None
    for i in range(1, min(len(words), 4)):
        if words[i].lower().strip(",.:") in _MSG_STARTERS:
            return " ".join(words[:i]), " ".join(words[i:])
    if len(words) <= 2:
        return rest, ""
    if not allow_guess:
        return None
    return words[0], " ".join(words[1:])


def _parse_message(raw: str) -> Optional[Dict[str, Any]]:
    """ "send (a whatsapp) message to Manolo saying hi", "text mom that I'm late", "mwambie Juma kwamba nimefika"."""
    app = _message_app(raw)
    body = _MSG_APP_RE.sub(" ", raw)
    body = re.sub(r"\s+", " ", body).strip()
    patterns = [
        r"^(?:send|write|tuma|andika)\s+(?:a\s+|an\s+)?(?:(?:whats\s?app|imessage|text|sms)\s+)?(?:message|msg|text|ujumbe|meseji)\s+(?:to|kwa)\s+(?P<to>.+?)(?:\s+"
        + _SAY_RE
        + r"\s*(?P<text>.+))?$",
        r"^(?:message|text|whats\s?app|mwambie|tell|imessage)\s+(?P<to>.+?)\s+"
        + _SAY_RE
        + r"\s*(?P<text>.+)$",
        r"^(?:send|tuma)\s+(?P<text>.+?)\s+(?:to|kwa)\s+(?P<to>[\w'-]+(?:\s[\w'-]+)?)$",
    ]
    for pat in patterns:
        m = re.match(pat, body, re.IGNORECASE)
        if not m:
            continue
        to = re.sub(r"^(?:my\s+|the\s+)", "", m.group("to").strip(" ,.:"), flags=re.IGNORECASE)
        # "to manolo" should be a name, not a whole sentence
        if not to or len(to.split()) > 3:
            continue
        text = (m.group("text") or "").strip(" ,.:\"'“”")
        if pat.endswith("$)$") and text.lower() in ("email", "an email", "a message"):
            continue
        return {"to": to, "text": text, "app": app}
    return None


_PLAYERS = {
    "spotify": "Spotify",
    "apple music": "Music",
    "music": "Music",
    "itunes": "Music",
    "music app": "Music",
}
# "play <this>" means resume playback, not a search.
_GENERIC_PLAY = re.compile(
    r"^(?:(?:some|a|the|my|any)\s+)?(?:music|muziki|songs?|wimbo|nyimbo|ngoma|tracks?|something|anything|it|again|"
    r"playback|tunes|playlist)(?:\s+(?:please|now|sasa|again|tena))?$"
)


def _parse_song(raw: str) -> Optional[Dict[str, Any]]:
    """ "play nadina song" / "play shape of you by ed sheeran on spotify" / "cheza wimbo wa nadina"."""
    m = re.match(r"(?i)^(?:play|cheza|nichezee|put on)\s+(.+)$", raw.strip())
    if not m:
        return None
    body = m.group(1).strip(" .,!?")
    params: Dict[str, Any] = {}
    pm = re.search(
        r"(?i)\s+(?:on|in|using|with|from|kwenye|kwa)\s+(spotify|apple music|music app|music|itunes)$",
        body,
    )
    if pm:
        params["player"] = _PLAYERS[pm.group(1).lower()]
        body = body[: pm.start()].strip()
    body = re.sub(r"(?i)^(?:the\s+)?(?:song|track|tune)\s+(?:called\s+)?", "", body)
    body = re.sub(r"(?i)^(?:some\s+)?(?:songs|music|nyimbo)\s+(?:by|from|za|ya)\s+", "", body)
    body = re.sub(r"(?i)^(?:wimbo|ngoma)\s+(?:wa|ya|unaoitwa|inayoitwa)\s+", "", body)
    body = re.sub(r"(?i)\s+(?:song|track|tune|wimbo|ngoma)$", "", body).strip()
    if not body or _GENERIC_PLAY.match(body.lower()):
        return params or None  # plain "play music" (maybe with a player): resume, not a search
    am = re.match(r"(?i)^(.+?)\s+by\s+(.+)$", body)
    if am:
        params["query"], params["artist"] = am.group(1).strip(), am.group(2).strip()
    else:
        params["query"] = body
    return params


def _d(
    domain, action, params=None, confidence=0.95, confirm=False, source="rules"
) -> IntentDecision:
    return IntentDecision(domain, action, params or {}, confidence, confirm, source)


class LayaBrain:
    """Combines fast rules, a semantic matcher and (optionally) the Laya Core ML model."""

    def __init__(self, model_dir: Optional[Path] = None, compute_units: Optional[str] = None):
        self.model_dir = model_dir or DEFAULT_MODEL_DIR
        self.compute_units = compute_units or DEFAULT_COMPUTE_UNITS
        self.agent = None
        self._attempted_load = False
        self._load_lock = threading.Lock()
        # Core ML takes ~30s to load and seconds per prediction on Intel CPUs, so it is
        # opt-in there; on Apple Silicon it is warmed in the background.
        default_on = "1" if is_apple_silicon() else "0"
        self.coreml_enabled = os.getenv("SPEEDX_COREML", default_on) == "1"
        self.coreml_state = "off" if not self.coreml_enabled else "cold"
        # Session context for pronoun resolution
        self.last_app: Optional[str] = None

    # ------------------------------------------------------------------ Core ML

    def _load_agent(self):
        """Safely attempt to load Core ML model with fallback."""
        with self._load_lock:
            if self._attempted_load:
                return
            self._attempted_load = True
            weight_file = (
                self.model_dir
                / "model.mlpackage"
                / "Data"
                / "com.apple.CoreML"
                / "weights"
                / "weight.bin"
            )
            if not weight_file.exists() or weight_file.stat().st_size < 100_000_000:
                self.coreml_state = "missing"
                return
            self.coreml_state = "warming"
            try:
                import laya_coreml as laya

                self.agent = laya.load(
                    str(self.model_dir), compute_units=self.compute_units, local_files_only=True
                )
                self.coreml_state = "ready"
            except Exception:
                self.agent = None
                self.coreml_state = "error"

    def warm_async(self):
        if self.coreml_enabled and not self._attempted_load:
            threading.Thread(target=self._load_agent, name="coreml-warmup", daemon=True).start()

    def set_coreml_enabled(self, enabled: bool):
        self.coreml_enabled = enabled
        if enabled:
            if self.agent is not None:
                self.coreml_state = "ready"
            elif not self._attempted_load:
                self.coreml_state = "cold"
                self.warm_async()
        else:
            self.coreml_state = "off"

    def _coreml_decide(self, prompt: str) -> Optional[IntentDecision]:
        if not self.coreml_enabled or self.agent is None:
            return None
        box: Dict[str, Any] = {}

        def run():
            try:
                box["res"] = self.agent.predict(
                    prompt,
                    {
                        "domain": {
                            "type": "choice",
                            "instructions": "Which domain best handles this Mac command?",
                            "criteria": [
                                "system",
                                "apps",
                                "music",
                                "files",
                                "clipboard",
                                "workspaces",
                                "general",
                            ],
                        },
                        "sensitive": {
                            "type": "noul",
                            "instructions": "Does this action shut down, lock, or terminate programs?",
                        },
                    },
                )
            except Exception as e:  # pragma: no cover - model failures
                box["err"] = e

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(COREML_TIMEOUT_S)
        res = box.get("res")
        if not res:
            return None

        domain = res["answers"]["domain"]["choice"]
        confidence = float(res["answers"]["domain"]["confidence"])
        if domain == "general" or confidence < 0.6:
            return None
        requires_conf = res["answers"]["sensitive"]["noul"] > 0.5
        action, params = "auto", {"prompt": prompt}
        if domain == "files":
            action = "search"
            clean_q = re.sub(
                r"(?i)\b(where is|where did i save|find|search|document|pdf|file|faili|tafuta|iko wapi|wapi|my)\b",
                "",
                prompt,
            ).strip()
            params = {"query": clean_q or prompt}
        elif domain == "music":
            action = "play_pause"
        elif domain == "clipboard":
            action = "read"
        elif domain == "apps":
            action = "open"
            clean_app = re.sub(r"(?i)\b(open|launch|fungua|washa|app)\b", "", prompt).strip()
            params = {"app": normalize_app_name(clean_app)}
        elif domain == "workspaces":
            action = "list"
        elif domain == "system":
            return None  # too ambiguous to act on without a specific action
        return IntentDecision(domain, action, params, confidence, requires_conf, "coreml")

    # ------------------------------------------------------------------ rules

    def _resolve_pronoun_app(self, word: str) -> Optional[str]:
        if word in (
            "it",
            "that",
            "this",
            "hii",
            "hiyo",
            "hicho",
            "that app",
            "this app",
            "hii app",
            "current app",
            "the current app",
            "current",
        ):
            return self.last_app or context_engine.get_frontmost_app()
        return None

    def _heuristic_parse(self, text: str) -> Optional[IntentDecision]:
        """Precise bilingual rules (English, Swahili, Sheng). Expects normalized text."""
        raw = text.strip()
        t = raw.lower()

        # --- MESSAGING (first: the message body may contain other command words) ---
        if re.search(
            r"\b(message|msg|text|ujumbe|meseji|mwambie|whats\s?app|imessage|tell)\b", t
        ) and not re.search(r"\b(email|e-mail|barua pepe)\b", t):
            msg = _parse_message(raw)
            if msg:
                return _d("messaging", "send", msg, 0.95)

        # --- TIMERS & REMINDERS (before music: "set a timer ... play" etc.) ---
        if re.search(r"\b(remind me|nikumbushe|reminder)\b", t):
            seconds = parse_duration(t) or 0
            body = re.sub(
                r"(?i).*?\b(remind me|nikumbushe|set a reminder|create a reminder|reminder)\b\s*(to|that|kwamba)?\s*",
                "",
                raw,
            )
            body = re.sub(
                r"(?i)\b(in|baada ya|after)\s+(\S+\s+){0,4}?(seconds?|minutes?|hours?|dakika\s+\S+|saa\s+\S+|sekunde\s+\S+)\b",
                "",
                body,
            )
            body = re.sub(r"\s+", " ", body).strip(" ,")
            body = (
                re.sub(r"(?i)^(in|baada ya|to|that|kwamba)\s+", "", body).strip(" ,") or "Reminder"
            )
            return _d("timer", "remind", {"text": body, "seconds": seconds}, 0.96)
        if re.search(r"\b(timer|countdown|kipima muda)\b", t) and not re.search(
            r"\b(cancel|stop|zima|futa|left|remaining|imebaki|check)\b", t
        ):
            seconds = parse_duration(t)
            if seconds:
                label = ""
                m = re.search(r"\b(?:for|to|ya ku|ku)\s+(?!\d)([a-z][\w\s]{2,40})$", t)
                if m and not parse_duration(m.group(1)):
                    label = m.group(1).strip()
                return _d("timer", "set", {"seconds": seconds, "label": label}, 0.97)
        if re.search(
            r"\b(what time is it|what's the time|tell me the time|saa ngapi|time now)\b", t
        ):
            return _d("timer", "time")
        if re.search(
            r"\b(what's the date|what is the date|what day is it|today's date|tarehe gani|leo ni siku gani)\b",
            t,
        ):
            return _d("timer", "date")

        # --- WEB ---
        m = re.search(
            r"^(?:search|look up|google|find|tafuta)\s+(?:on\s+)?youtube\s+(?:for\s+)?(.+)$", t
        ) or re.search(r"^(?:play|cheza|watch|tazama)\s+(.+?)\s+(?:on|kwenye)\s+youtube$", t)
        if m:
            return _d("web", "youtube", {"query": m.group(1).strip()}, 0.95)
        m = re.search(
            r"^(?:search(?: the web| online| google| the internet)? for|search|google|look up|tafuta mtandaoni|tafuta kwenye google)\s+(.+)$",
            t,
        )
        if m and not re.search(r"^(file|faili|pdf|files)\b", m.group(1)):
            query = raw[m.start(1) :].strip()
            return _d("web", "search", {"query": query}, 0.93)
        m = re.search(r"\btafuta\s+(.+?)\s+mtandaoni$", t)
        if m:
            return _d("web", "search", {"query": m.group(1)}, 0.93)
        m = re.search(r"^(?:go to|visit|browse to|nenda)\s+(.+)$", t)
        if m and site_url(m.group(1)):
            return _d("web", "open_url", {"site": m.group(1)}, 0.94)

        # --- MUSIC ---
        if re.search(
            r"\b(next song|next track|skip song|skip track|skip this|(play )?the next one|wimbo unaofuata|ngoma nyingine)\b",
            t,
        ):
            return _d("music", "next")
        if re.search(
            r"\b(previous song|prev track|previous track|last song|(play )?the previous one|wimbo uliopita)\b",
            t,
        ):
            return _d("music", "previous")
        if re.search(
            r"\b(what song|current track|what's playing|what is playing|wimbo gani|ngoma gani)\b", t
        ):
            return _d("music", "get_current_track")
        if re.search(
            r"\b(pause|simamisha|stop (the )?music|stop playing|tulia|acha muziki|zima muziki)\b", t
        ):
            return _d("music", "pause")
        # "play music softly / kwa sauti ndogo" -> low volume, then play
        if re.search(r"\b(music|muziki|song|wimbo|ngoma)\b", t) and re.search(
            r"\b(softly|quietly|low volume|in the background|sauti ndogo|taratibu|kwa upole)\b", t
        ):
            return _d("system", "set_volume", {"level": 20, "then": "music.play"})
        if not re.search(r"\b(game|snake|youtube)\b", t):
            song = _parse_song(raw)
            if song and song.get("query"):
                return _d("music", "play_song", song, 0.94)
            if song:  # "play music on spotify"
                return _d("music", "play", song)
        if (
            re.search(r"\b(cheza|play)\b", t)
            or re.search(r"^resume( (the )?(music|song|playback))?$", t)
        ) and not re.search(r"\b(game|snake|youtube)\b", t):
            return _d("music", "play")

        # --- SYSTEM: VOLUME ---
        vol_match = re.search(
            r"\b(?:set (?:the )?volume to|volume to|volume at|weka sauti(?: kwenye| hadi)?|volume)\s+(\S+(?:\s+\S+)?)",
            t,
        )
        if vol_match:
            level = parse_number(vol_match.group(1))
            if level is not None:
                return _d("system", "set_volume", {"level": max(0, min(100, level))})
        to_level = re.search(
            r"\b(?:volume|sauti)\b.*\b(?:to|at|kwenye|hadi)\s+(.+?)(?:\s*(?:percent|%|asilimia))?$",
            t,
        )
        if to_level:
            level = parse_number(to_level.group(1))
            if level is not None:
                return _d("system", "set_volume", {"level": max(0, min(100, level))})
        if re.search(
            r"\b(ongeza sauti|volume up|turn (it |the volume |the sound )?up|louder|increase (the )?volume|raise (the )?volume|pandisha sauti|sauti juu)\b",
            t,
        ):
            return _d("system", "volume_up")
        if re.search(
            r"\b(punguza sauti|volume down|turn (it |the volume |the sound )?down|quieter|decrease (the )?volume|lower (the )?volume|shusha sauti|sauti chini)\b",
            t,
        ):
            return _d("system", "volume_down")
        if re.search(r"\b(unmute|rudisha sauti|washa sauti)\b", t):
            return _d("system", "unmute")
        if re.search(r"\b(mute|nyamazisha|zima sauti)\b", t):
            return _d("system", "mute")

        # --- SYSTEM: LOCK, SLEEP, APPEARANCE ---
        if re.search(
            r"\b(lock (the )?screen|lock (my )?mac|lock (the )?computer|funga kioo|funga screen|funga kompyuta)\b",
            t,
        ):
            return _d("system", "lock_screen", confirm=True)
        if re.search(
            r"\b(sleep mac|put (the |my )?mac to sleep|put (the )?computer to sleep|laza mac|laza kompyuta)\b",
            t,
        ):
            return _d("system", "sleep", confirm=True)
        if re.search(r"\b(dark mode|light mode|badili rangi ya kioo)\b", t):
            mode = ""
            if re.search(r"\b(turn on|enable|switch to|use|washa)\b.*dark|dark mode on\b", t):
                mode = "dark"
            elif re.search(r"\blight mode\b|\b(turn off|disable|zima)\b.*dark", t):
                mode = "light"
            return _d("system", "toggle_dark_mode", {"mode": mode} if mode else {})

        # --- WORKSPACES ---
        ws_name = r"(?:the\s+|my\s+|a\s+)?(?:workspace\s+(?:called\s+|named\s+|ya\s+)?([\w-]+(?:\s[\w-]+)?)|([\w-]+(?:\s[\w-]+)?)\s+workspace)"
        m = re.search(
            r"^(?:create|make|set up|setup|save|tengeneza|unda)\s+(?:a\s+)?(?:new\s+)?"
            + ws_name
            + r"\s+(?:with|that opens|for|na|yenye)\s+(.+)$",
            t,
        )
        if m:
            return _d(
                "workspaces",
                "create",
                {"workspace": (m.group(1) or m.group(2)).strip(), "apps": m.group(3).strip()},
                0.95,
            )
        m = re.search(
            r"^(?:save|hifadhi)\s+(?:my\s+|these\s+|the\s+|this\s+)?(?:current\s+|open\s+)?(?:apps|setup|windows|workspace)?\s*as\s+"
            + ws_name
            + r"$",
            t,
        ) or re.search(
            r"^(?:save|hifadhi)\s+(?:my\s+|these\s+|the\s+|this\s+)?(?:current\s+|open\s+)?(?:apps|setup|windows)\s+as\s+(?:a\s+)?([\w-]+(?:\s[\w-]+)?)()$",
            t,
        )
        if m:
            return _d(
                "workspaces",
                "save_current",
                {"workspace": (m.group(1) or m.group(2)).strip()},
                0.95,
            )
        m = re.search(r"^(?:add|ongeza|put)\s+(.+?)\s+(?:to|in|into|kwenye)\s+" + ws_name + r"$", t)
        if m:
            return _d(
                "workspaces",
                "add",
                {"workspace": (m.group(2) or m.group(3)).strip(), "apps": m.group(1).strip()},
                0.95,
            )
        m = re.search(r"^(?:delete|remove|futa|ondoa)\s+" + ws_name + r"$", t)
        if m:
            return _d(
                "workspaces",
                "delete",
                {"workspace": (m.group(1) or m.group(2)).strip()},
                0.95,
                confirm=True,
            )
        m = re.search(r"^(?:open|start|launch|activate|load|anza|fungua)\s+" + ws_name + r"$", t)
        if m:
            return _d(
                "workspaces", "activate", {"workspace": (m.group(1) or m.group(2)).strip()}, 0.95
            )
        if re.search(r"\b(start coding|anza coding|coding workspace|coding mode)\b", t):
            return _d("workspaces", "activate", {"workspace": "coding"})
        if re.search(r"\b(start research|anza utafiti|research workspace|research mode)\b", t):
            return _d("workspaces", "activate", {"workspace": "research"})

        # --- NOTES ---
        note_new = re.search(
            r"\b(open notes app and write a new note|open notes and write a new note|write a new note|write new note|create new note|create a new note|make a new note|new note|take a note|note that|andika note mpya|andika note|fungua notes uandike)\b",
            t,
        )
        if note_new:
            body = raw[note_new.end() :].strip(" ,:")
            body = re.sub(
                r"(?i)^(saying|that says|that|about|called|titled|kuhusu|inayosema)\s+", "", body
            ).strip()
            title = "Speed-X Note"
            if body:
                words = body.split()
                title = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
            return _d(
                "notes",
                "create",
                {"title": title, "body": body or "Created with Speed-X Assistant."},
                0.96,
            )

        note_upd = re.search(
            r"\b(update the existing one|update existing note|update the existing note|update (my |the )?(last )?note|append to (my |the )?note|add to (my |the )?note|ongeza kwenye note|ongeza note|rekebisha note)\b",
            t,
        )
        if note_upd:
            addition = raw[note_upd.end() :].strip(" ,:")
            addition = re.sub(r"(?i)^(saying|that says|with|kwamba)\s+", "", addition).strip()
            return _d("notes", "update", {"addition": addition or "Updated via Speed-X."}, 0.96)

        # --- EMAIL ---
        mail = re.search(
            r"\b(send email with a message|send an email with a message|send (an )?email|compose (an )?email|write (an )?email|email|tuma email|tuma barua pepe)\b",
            t,
        )
        if mail and (mail.start() == 0 or re.search(r"\b(send|compose|write|tuma)\b", t)):
            rest = raw[mail.end() :].strip()
            recipient = spoken_email(rest) or ""
            if recipient:
                rest = re.sub(
                    r"(?i)\b(to\s+)?[\w.+-]+(@|\s+at\s+)[\w-]+(\.|\s+dot\s+)[\w.-]+", "", rest
                ).strip()
            rest = re.sub(
                r"(?i)^(to\s+\w+\s+)?(saying|that says|with (a )?message|message|kwamba|inayosema)\s*",
                "",
                rest,
            ).strip(" ,:")
            subject = "Speed-X Quick Message"
            if rest:
                words = rest.split()
                subject = " ".join(words[:6]) + ("…" if len(words) > 6 else "")
            return _d(
                "mail",
                "send",
                {
                    "recipient": recipient,
                    "subject": subject,
                    "message": rest or "Hello from Speed-X Assistant!",
                },
            )

        # --- FILES ---
        if re.search(
            r"\b(make new file|create new file|make a new file|create a file|create a new file|make file|new file|tengeneza faili|unda faili|faili jipya)\b",
            t,
        ):
            name_match = re.search(
                r"\b(?:named|called|jina lake|jina)\s+([\w.-]+(?:\s+dot\s+\w+)?)",
                raw,
                re.IGNORECASE,
            ) or re.search(r"\bfile\s+(?!named|called)([\w-]+\.\w+)", raw, re.IGNORECASE)
            filename = (
                re.sub(r"\s+dot\s+", ".", name_match.group(1))
                if name_match
                else "SpeedX_Document.txt"
            )
            return _d("files", "create", {"filename": filename})
        if re.search(r"\b(find pdf|tafuta pdf|find (my |the )?pdfs?)\b", t):
            query = re.sub(r".*\b(find pdf|tafuta pdf|find (my |the )?pdfs?)\b", "", t).strip()
            return _d("files", "find_pdf", {"query": query}, 0.92)
        if re.search(
            r"\b(latest screenshot|last screenshot|recent screenshot|screenshot ya mwisho)\b", t
        ):
            return _d("files", "latest_screenshot")
        file_match = re.search(
            r"^(?:find file|search file|find (?:my |the )?file|tafuta faili|find|where is|where's|where did i (?:save|put)|iko wapi)\s+(.+)$",
            t,
        )
        if file_match:
            query = re.sub(
                r"\b(my|the|file|files|document|iko wapi|wapi)\b", " ", file_match.group(1)
            )
            query = re.sub(r"\s+", " ", query).strip()
            if query:
                return _d("files", "search", {"query": query}, 0.9)

        # --- CLIPBOARD ---
        if re.search(r"\b(clear|empty|wipe|erase|futa|safisha)\s+(my |the )?clipboard\b", t):
            return _d("clipboard", "clear")
        if re.search(
            r"\b(inspect clipboard|angalia clipboard|stats za clipboard|clipboard stats)\b", t
        ):
            return _d("clipboard", "inspect")
        if re.search(
            r"\b(read (my |the )?clipboard|what's on (my |the )?clipboard|kuna nini kwenye clipboard|soma clipboard)\b",
            t,
        ):
            return _d("clipboard", "read")

        # --- SCREEN ---
        if re.search(
            r"\b(what|which) (app|application|window) (am i (in|on|using)|is (this|open|active|in front|focused))\b|\b(active|current|front|focused) window\b|\b(niko kwenye|natumia) (app|programu|dirisha) gani\b",
            t,
        ):
            return _d("screen", "active_window")
        if re.search(
            r"\b(take (a )?screenshot|capture (the )?screen|piga screenshot|piga picha ya kioo)\b",
            t,
        ):
            return _d("screen", "capture")
        if re.search(
            r"\b(read (my |the )?screen|ocr screen|what am i looking at|soma screen|soma kioo|angalia screen)\b",
            t,
        ):
            return _d("screen", "read")

        # --- APPS (catch-alls, last) ---
        if re.search(
            r"\b(running apps|apps zinazofanya kazi|list apps|what apps are (open|running))\b", t
        ):
            return _d("apps", "list_running")

        open_match = re.search(r"^(?:open|launch|fungua|washa|switch to|go to|bring up)\s+(.+)$", t)
        if open_match:
            target = open_match.group(1).strip()
            pronoun = self._resolve_pronoun_app(target)
            if pronoun:
                return _d("apps", "open", {"app": pronoun}, 0.85)
            if not target.startswith(("file", "pdf")):
                app = resolve_app(target)
                if app:
                    return _d("apps", "open", {"app": app}, 0.95)
                if site_url(target):
                    return _d("web", "open_url", {"site": target}, 0.9)
                # An unknown multi-word "app name" is almost always a sentence we failed to split.
                if len(target.split()) <= 3 and not re.search(
                    r"\b(and|then|to|saying|halafu|kisha)\b", target
                ):
                    return _d("apps", "open", {"app": normalize_app_name(target)}, 0.7)

        quit_match = re.search(r"^(?:quit|close|exit|kill|funga|zima|toka)\s+(.+)$", t)
        if quit_match:
            target = quit_match.group(1).strip()
            app = self._resolve_pronoun_app(target) or resolve_app(target)
            if not app and not target.startswith(("tab", "window")):
                app = normalize_app_name(target)
            if app:
                return _d("apps", "quit", {"app": app}, 0.9, confirm=True)

        return None

    # ------------------------------------------------------------------ public API

    def decide(self, prompt: str) -> IntentDecision:
        """Single-intent decision for the whole prompt."""
        clean = normalize(prompt)

        rule = self._heuristic_parse(clean)
        match = semantic_matcher.match(clean)
        # A weak catch-all rule ("open <unknown>") loses to a strong semantic match.
        if rule and (rule.confidence >= 0.8 or not match or match.score < SEMANTIC_ACCEPT):
            rule.text = clean
            return rule

        if match and match.score >= SEMANTIC_ACCEPT:
            return IntentDecision(
                match.domain,
                match.action,
                match.params,
                round(min(0.94, match.score), 2),
                match.domain == "system" and match.action in ("lock_screen", "sleep"),
                "semantic",
                clean,
            )

        if self.coreml_enabled and self.agent is None and not self._attempted_load:
            self.warm_async()  # never block a command on a 30s model load
        ml = self._coreml_decide(clean) if self.agent is not None else None
        if ml:
            ml.text = clean
            return ml

        alternatives = []
        if match and match.score >= SEMANTIC_SUGGEST:
            alternatives.append(
                {
                    "domain": match.domain,
                    "action": match.action,
                    "suggestion": match.example,
                    "score": round(match.score, 2),
                }
            )
        return IntentDecision(
            "general", "unhandled", {"prompt": prompt}, 0.0, False, "fallback", clean, alternatives
        )

    def _llm_plan(self, prompt: str) -> Optional[List[IntentDecision]]:
        """Ask the local model when the fast layers can't cover the request."""
        from . import ai

        ctx = []
        front = context_engine.front_app_hint
        if front:
            ctx.append(f"frontmost app: {front}")
        if self.last_app:
            ctx.append(f"last opened app: {self.last_app}")
        plan = ai.plan(prompt, "; ".join(ctx))
        if not plan:
            return None
        steps = [
            IntentDecision(
                s["domain"],
                s["action"],
                s["params"],
                0.8,
                (s["domain"], s["action"]) in LLM_CONFIRM,
                "llm",
                prompt,
            )
            for s in plan["steps"]
        ]
        if plan["then_answer"]:
            steps.append(
                IntentDecision("assistant", "think", {"request": prompt}, 0.8, False, "llm", prompt)
            )
        if not steps and plan["reply"]:
            steps.append(
                IntentDecision(
                    "assistant", "answer", {"text": plan["reply"]}, 0.8, False, "llm", prompt
                )
            )
        return steps or None

    def plan(
        self, prompt: str, commit: bool = True, allow_llm: bool = True
    ) -> List[IntentDecision]:
        """Ordered execution plan. Compound commands become multiple steps.

        commit=False (used for live previews) leaves the session context untouched.
        """
        clean = normalize(prompt)

        # Reasoning over what's on screen / in the clipboard: read it, then think.
        if _CONTENT_RE.search(clean) and (_SCREEN_RE.search(clean) or _CLIPBOARD_RE.search(clean)):
            source = ("screen", "read") if _SCREEN_RE.search(clean) else ("clipboard", "read")
            return [
                IntentDecision(source[0], source[1], {}, 0.95, False, "rules", clean),
                IntentDecision("assistant", "think", {"request": clean}, 0.9, False, "llm", clean),
            ]

        whole = self.decide(prompt)
        parts = split_commands(clean)

        steps = [whole]
        if len(parts) > 1:
            sub = []
            saved_app = self.last_app
            for part in parts:
                d = self.decide(part)
                if d.domain == "apps" and d.action == "open":
                    self.last_app = d.params.get("app")  # so "open safari and close it" works
                sub.append(d)
            self.last_app = saved_app
            all_handled = all(d.handled and d.confidence >= 0.7 for d in sub)
            whole_is_content = (whole.domain, whole.action) in CONTENT_INTENTS
            # Prefer the split when every clause is actionable and it adds information.
            if all_handled and (
                not whole.handled
                or not whole_is_content
                or len({(d.domain, d.action) for d in sub}) > 1
            ):
                steps = sub
            elif not whole.handled and any(d.handled for d in sub):
                # Do what we understood and say clearly which clause we couldn't.
                steps = sub

        # Rules can chain a follow-up step ("play music softly" -> set volume, then play).
        expanded = []
        for d in steps:
            follow = d.params.pop("then", None) if d.handled else None
            expanded.append(d)
            if follow:
                domain, action = follow.split(".", 1)
                expanded.append(
                    IntentDecision(domain, action, {}, d.confidence, False, d.source, d.text)
                )
        steps = expanded

        # Question clauses inside a compound command ("open safari and tell me a joke") are answered.
        if len(steps) > 1:
            steps = [
                IntentDecision("assistant", "ask", {"question": d.text}, 0.85, False, "llm", d.text)
                if not d.handled and _QUESTION_RE.search(d.text or "")
                else d
                for d in steps
            ]

        if any(not d.handled for d in steps):
            if not any(d.handled for d in steps) and _QUESTION_RE.search(clean):
                # A question or conversation: answer it (streamed), no tools involved.
                steps = [
                    IntentDecision(
                        "assistant", "ask", {"question": clean}, 0.9, False, "llm", clean
                    )
                ]
            elif allow_llm:
                # An action the fast layers don't know: let the local AI plan it.
                llm_steps = self._llm_plan(clean)
                if llm_steps:
                    steps = llm_steps

        # "open whatsapp and send a message to X": the open step tells us which app to message with.
        for i, d in enumerate(steps):
            if d.domain == "messaging" and not d.params.get("app"):
                earlier = [
                    e.params.get("app")
                    for e in steps[:i]
                    if e.domain == "apps" and e.action == "open"
                ]
                if earlier and earlier[-1] in ("WhatsApp", "Messages"):
                    d.params["app"] = earlier[-1]

        # "open spotify and play nadina": play in the player that was just opened.
        for i, d in enumerate(steps):
            if (
                d.domain == "music"
                and d.action in ("play", "play_song")
                and not d.params.get("player")
            ):
                earlier = [
                    e.params.get("app")
                    for e in steps[:i]
                    if e.domain == "apps" and e.action == "open"
                ]
                if earlier and earlier[-1] in ("Music", "Spotify"):
                    d.params["player"] = earlier[-1]

        # "open notes and write a note": the Notes/Mail tools bring their app forward themselves.
        steps = [
            d
            for i, d in enumerate(steps)
            if not (
                d.domain == "apps"
                and d.action == "open"
                and any(
                    (SELF_OPENING.get(n.domain) or n.params.get("app")) == d.params.get("app")
                    for n in steps[i + 1 :]
                    if n.domain in SELF_OPENING
                )
            )
        ] or steps

        if commit:
            for d in steps:
                if d.domain == "apps" and d.action == "open":
                    self.last_app = d.params.get("app")
        return steps
