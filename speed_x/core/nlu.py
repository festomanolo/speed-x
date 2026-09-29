"""Language utilities for the Speed-X brain.

Everything here is pure Python and runs in well under a millisecond, so the
brain can analyse every partial speech transcript live.

- normalize():        strips wake words, politeness fillers and dictation punctuation
- parse_number():     English + Swahili number words ("twenty five", "kumi na tano")
- parse_duration():   "ten minutes", "an hour and a half", "dakika tano", "saa moja"
- split_commands():   "open safari and then play music" -> two clauses
- SemanticMatcher:    fuzzy bilingual intent matching that tolerates ASR mistakes
"""

import difflib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_LEADING_FILLERS = [
    r"hey speed ?x",
    r"hi speed ?x",
    r"ok(ay)? speed ?x",
    r"speed ?x",
    r"speedx",
    r"hey",
    r"ok(ay)?",
    r"so",
    r"um+",
    r"uh+",
    r"please",
    r"kindly",
    r"just",
    r"can you( please)?",
    r"could you( please)?",
    r"would you( please)?",
    r"will you( please)?",
    r"i want you to",
    r"i'?d like you to",
    r"i need you to",
    r"go ahead and",
    r"help me( to)?",
    r"i want to",
    r"i'?d like to",
    r"let'?s",
    r"tafadhali",
    r"naomba( u)?",
    r"nisaidie( ku)?",
    r"hebu",
    r"eti",
]
_TRAILING_FILLERS = [
    r"please",
    r"for me",
    r"right now",
    r"now",
    r"sasa( hivi)?",
    r"tafadhali",
    r"thanks?( you)?",
]

_LEAD_RE = re.compile(r"^(?:(?:" + "|".join(_LEADING_FILLERS) + r")\b[\s,]*)+", re.IGNORECASE)
_TRAIL_RE = re.compile(r"(?:[\s,]+\b(?:" + "|".join(_TRAILING_FILLERS) + r"))+$", re.IGNORECASE)


def normalize(text: str) -> str:
    """Clean a raw (often dictated) command while preserving the case of its content."""
    t = text.strip()
    t = t.replace("’", "'").replace("“", '"').replace("”", '"')
    # Dictation adds sentence punctuation: "Open Safari." / "Volume up!"
    t = re.sub(r"[.!?,;:]+$", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    for _ in range(2):
        t = _LEAD_RE.sub("", t).strip()
        t = _TRAIL_RE.sub("", t).strip()
        t = re.sub(r"[.!?,;:]+$", "", t).strip()
    return t


# ---------------------------------------------------------------------------
# Numbers & durations
# ---------------------------------------------------------------------------

_EN_UNITS = {
    "zero": 0,
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "couple": 2,
    "few": 3,
}
_EN_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SW_UNITS = {
    "moja": 1,
    "mbili": 2,
    "tatu": 3,
    "nne": 4,
    "tano": 5,
    "sita": 6,
    "saba": 7,
    "nane": 8,
    "tisa": 9,
}
_SW_TENS = {
    "kumi": 10,
    "ishirini": 20,
    "thelathini": 30,
    "arobaini": 40,
    "hamsini": 50,
    "sitini": 60,
    "sabini": 70,
    "themanini": 80,
    "tisini": 90,
}

_NUMBER_WORDS = (
    set(_EN_UNITS)
    | set(_EN_TENS)
    | set(_SW_UNITS)
    | set(_SW_TENS)
    | {"hundred", "mia", "na", "and"}
)


def parse_number(text: str) -> Optional[int]:
    """Parse "25", "twenty five", "kumi na tano", "one hundred" -> int."""
    t = text.lower().strip().replace("-", " ")
    m = re.search(r"\d+", t)
    if m:
        return int(m.group())
    words = [w for w in t.split() if w in _NUMBER_WORDS]
    if not words:
        return None
    total, seen = 0, False
    for w in words:
        if w in ("and", "na"):
            continue
        if w in ("hundred", "mia"):
            total = max(total, 1) * 100
            seen = True
            continue
        value = _EN_UNITS.get(w, _EN_TENS.get(w, _SW_UNITS.get(w, _SW_TENS.get(w))))
        if value is not None:
            total += value
            seen = True
    return total if seen else None


_NUM = (
    r"(?:\d+(?:\.\d+)?|(?:(?:"
    + "|".join(sorted(_NUMBER_WORDS - {"na", "and"}, key=len, reverse=True))
    + r")[\s-]*)+)"
)
_EN_UNIT_SECONDS = {"second": 1, "sec": 1, "minute": 60, "min": 60, "hour": 3600, "hr": 3600}
_SW_UNIT_SECONDS = {"sekunde": 1, "dakika": 60, "saa": 3600, "masaa": 3600}


def _to_float(num: str) -> Optional[float]:
    num = num.strip()
    try:
        return float(num)
    except ValueError:
        n = parse_number(num)
        return float(n) if n is not None else None


def parse_duration(text: str) -> Optional[int]:
    """Total seconds described in text, or None. Handles English and Swahili word order."""
    t = " " + text.lower() + " "
    total = 0.0
    found = False

    if re.search(r"\bhalf (an|a) hour\b|\bnusu saa\b", t):
        total += 1800
        found = True
        t = re.sub(r"\bhalf (an|a) hour\b|\bnusu saa\b", " ", t)

    # English: "<num> <unit>"  (e.g. "10 minutes", "an hour", "twenty five seconds")
    for m in re.finditer(
        r"(" + _NUM + r")\s*(second|sec|minute|min|hour|hr)s?\b(\s+and\s+a\s+half)?", t
    ):
        value = _to_float(m.group(1))
        if value is None:
            continue
        unit = _EN_UNIT_SECONDS[m.group(2)]
        if m.group(3):
            value += 0.5
        total += value * unit
        found = True

    # Swahili: "<unit> <num>"  (e.g. "dakika tano", "saa moja na nusu")
    for m in re.finditer(
        r"\b(sekunde|dakika|masaa|saa)\s+("
        + _NUM
        + r"(?:\s*na\s+(?!nusu)"
        + _NUM
        + r")?)(\s*na\s+nusu)?",
        t,
    ):
        value = _to_float(m.group(2))
        if value is None:
            continue
        if m.group(3):
            value += 0.5
        total += value * _SW_UNIT_SECONDS[m.group(1)]
        found = True

    return int(round(total)) if found and total > 0 else None


# ---------------------------------------------------------------------------
# Multi-command splitting
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(
    r"\s*(?:,\s*)?\b(?:and then|and after that|after that|then|and also|and|also|halafu|alafu|kisha|na pia|na kisha)\b\s*",
    re.IGNORECASE,
)


def split_commands(text: str) -> List[str]:
    parts = [p.strip(" ,") for p in _SPLIT_RE.split(text)]
    return [p for p in parts if p]


# ---------------------------------------------------------------------------
# Spoken e-mail addresses
# ---------------------------------------------------------------------------


def spoken_email(text: str) -> Optional[str]:
    """Find an e-mail address, including dictated ones: "alice at example dot com"."""
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    if m:
        return m.group()
    m = re.search(r"\b([\w.+-]+)\s+at\s+([\w-]+)\s+dot\s+([a-z]{2,})\b", text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}@{m.group(2)}.{m.group(3)}".lower()
    return None


# ---------------------------------------------------------------------------
# Semantic intent matcher
# ---------------------------------------------------------------------------

_STOPWORDS = {
    "the",
    "a",
    "an",
    "my",
    "me",
    "to",
    "of",
    "for",
    "on",
    "in",
    "it",
    "is",
    "please",
    "can",
    "you",
    "could",
    "would",
    "i",
    "want",
    "some",
    "this",
    "that",
    "up",
    "ya",
    "wa",
    "la",
    "kwa",
    "na",
    "yangu",
}


def _tokens(text: str) -> List[str]:
    return [
        w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOPWORDS
    ] or re.findall(r"[a-z0-9']+", text.lower())


def _fuzzy_overlap(a: List[str], b: List[str]) -> float:
    """Soft token overlap: tokens count as shared when they are near-identical (ASR typos)."""
    if not a or not b:
        return 0.0
    matched = 0.0
    for tok in a:
        best = 0.0
        for other in b:
            if tok == other:
                best = 1.0
                break
            if len(tok) > 3 and len(other) > 3:
                r = difflib.SequenceMatcher(None, tok, other).ratio()
                if r >= 0.8:
                    best = max(best, r)
        matched += best
    return matched / (len(a) + len(b) - matched)


@dataclass
class SemanticMatch:
    domain: str
    action: str
    params: Dict
    score: float
    example: str


# (domain, action, params, examples). Only intents that need no free-text
# parameters live here; parameterised intents are handled by the rule engine.
INTENT_CATALOG: List[Tuple[str, str, Dict, List[str]]] = [
    (
        "music",
        "play",
        {},
        [
            "play music",
            "play some music",
            "play a song",
            "start the music",
            "resume music",
            "cheza muziki",
            "weka muziki",
            "nipe muziki",
            "cheza wimbo",
            "weka ngoma",
        ],
    ),
    (
        "music",
        "pause",
        {},
        [
            "pause music",
            "stop the music",
            "pause the song",
            "stop playing",
            "simamisha muziki",
            "zima muziki",
            "acha muziki",
        ],
    ),
    (
        "music",
        "next",
        {},
        [
            "next song",
            "skip this song",
            "next track",
            "skip track",
            "play the next one",
            "wimbo unaofuata",
            "ngoma nyingine",
            "badilisha wimbo",
        ],
    ),
    (
        "music",
        "previous",
        {},
        [
            "previous song",
            "go back a song",
            "last track",
            "play the previous one",
            "wimbo uliopita",
            "rudisha wimbo",
        ],
    ),
    (
        "music",
        "get_current_track",
        {},
        [
            "what song is this",
            "what's playing",
            "what is playing now",
            "which song is playing",
            "wimbo gani huu",
            "ngoma gani inacheza",
        ],
    ),
    (
        "system",
        "volume_up",
        {},
        [
            "volume up",
            "turn it up",
            "louder",
            "increase the volume",
            "raise volume",
            "make it louder",
            "ongeza sauti",
            "sauti juu",
            "pandisha sauti",
        ],
    ),
    (
        "system",
        "volume_down",
        {},
        [
            "volume down",
            "turn it down",
            "quieter",
            "lower the volume",
            "decrease volume",
            "make it quieter",
            "punguza sauti",
            "sauti chini",
            "shusha sauti",
        ],
    ),
    (
        "system",
        "mute",
        {},
        [
            "mute",
            "make it quiet",
            "quiet please",
            "be quiet",
            "kimya",
            "mute the sound",
            "silence",
            "mute audio",
            "nyamazisha",
            "zima sauti",
        ],
    ),
    (
        "system",
        "unmute",
        {},
        ["unmute", "unmute the sound", "turn the sound back on", "rudisha sauti", "washa sauti"],
    ),
    (
        "system",
        "lock_screen",
        {},
        [
            "lock the screen",
            "lock my mac",
            "lock the computer",
            "funga screen",
            "funga kioo",
            "funga kompyuta",
        ],
    ),
    (
        "system",
        "sleep",
        {},
        ["put the mac to sleep", "sleep the computer", "go to sleep", "laza mac", "laza kompyuta"],
    ),
    (
        "system",
        "toggle_dark_mode",
        {},
        [
            "toggle dark mode",
            "switch appearance",
            "change theme",
            "badili rangi ya kioo",
            "badili mandhari",
        ],
    ),
    (
        "clipboard",
        "read",
        {},
        [
            "read my clipboard",
            "what's on my clipboard",
            "what did i copy",
            "show clipboard",
            "kuna nini kwenye clipboard",
            "soma clipboard",
        ],
    ),
    (
        "clipboard",
        "inspect",
        {},
        ["inspect clipboard", "clipboard stats", "analyze clipboard", "angalia clipboard"],
    ),
    (
        "screen",
        "capture",
        {},
        [
            "take a screenshot",
            "screenshot",
            "capture the screen",
            "grab the screen",
            "piga screenshot",
            "piga picha ya kioo",
        ],
    ),
    (
        "screen",
        "read",
        {},
        [
            "read my screen",
            "what's on my screen",
            "what am i looking at",
            "ocr the screen",
            "soma screen",
            "soma kioo",
        ],
    ),
    (
        "files",
        "latest_screenshot",
        {},
        [
            "latest screenshot",
            "my last screenshot",
            "most recent screenshot",
            "screenshot ya mwisho",
        ],
    ),
    (
        "apps",
        "list_running",
        {},
        [
            "what apps are running",
            "list running apps",
            "which apps are open",
            "apps zinazofanya kazi",
        ],
    ),
    (
        "workspaces",
        "activate",
        {"workspace": "coding"},
        [
            "start coding",
            "coding mode",
            "open my coding setup",
            "time to code",
            "anza coding",
            "anza kuprogram",
        ],
    ),
    (
        "workspaces",
        "activate",
        {"workspace": "research"},
        ["start research", "research mode", "open my research setup", "anza utafiti"],
    ),
    (
        "workspaces",
        "list",
        {},
        ["list workspaces", "show my workspaces", "what workspaces do i have"],
    ),
    (
        "timer",
        "list",
        {},
        ["how much time is left", "check my timers", "show timers", "timer imebaki muda gani"],
    ),
    (
        "timer",
        "cancel",
        {},
        ["cancel the timer", "stop the timer", "cancel timers", "futa timer", "zima timer"],
    ),
    (
        "timer",
        "time",
        {},
        ["what time is it", "tell me the time", "current time", "saa ngapi", "ni saa ngapi sasa"],
    ),
    (
        "timer",
        "date",
        {},
        [
            "what's the date",
            "what day is it",
            "today's date",
            "leo ni tarehe gani",
            "leo ni siku gani",
        ],
    ),
    ("notes", "open", {}, ["open my notes", "show notes", "fungua notes"]),
    ("mail", "open", {}, ["open mail", "check my email", "show my inbox", "fungua barua pepe"]),
]


class SemanticMatcher:
    def __init__(self, catalog=INTENT_CATALOG):
        self._entries = []
        for domain, action, params, examples in catalog:
            for ex in examples:
                self._entries.append((domain, action, params, ex, _tokens(ex)))

    def match(self, text: str) -> Optional[SemanticMatch]:
        query = text.lower().strip()
        q_tokens = _tokens(query)
        if not q_tokens:
            return None
        best: Optional[SemanticMatch] = None
        for domain, action, params, example, ex_tokens in self._entries:
            overlap = _fuzzy_overlap(q_tokens, ex_tokens)
            if overlap == 0:
                continue
            ratio = difflib.SequenceMatcher(None, query, example).ratio()
            score = 0.65 * overlap + 0.35 * ratio
            if best is None or score > best.score:
                best = SemanticMatch(domain, action, dict(params), score, example)
        return best


semantic_matcher = SemanticMatcher()
