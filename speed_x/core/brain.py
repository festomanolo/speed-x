"""Laya Brain: Typed intent classification and decision router."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import DEFAULT_COMPUTE_UNITS, DEFAULT_MODEL_DIR
from ..tools.apps import normalize_app_name
from .context import context_engine


@dataclass
class IntentDecision:
    domain: str
    action: str
    params: Dict[str, Any]
    confidence: float
    requires_confirmation: bool
    source: str  # "coreml" or "heuristic"


class LayaBrain:
    """Combines Laya Core ML typed decision model with bilingual heuristic parsing."""

    def __init__(self, model_dir: Optional[Path] = None, compute_units: Optional[str] = None):
        self.model_dir = model_dir or DEFAULT_MODEL_DIR
        self.compute_units = compute_units or DEFAULT_COMPUTE_UNITS
        self.agent = None
        self._attempted_load = False

    def _load_agent(self):
        """Safely attempt to load Core ML model with fallback."""
        if self._attempted_load:
            return
        self._attempted_load = True
        weight_file = self.model_dir / "model.mlpackage" / "Data" / "com.apple.CoreML" / "weights" / "weight.bin"
        if not weight_file.exists() or weight_file.stat().st_size < 100_000_000:
            # Model weights not fully downloaded yet; use fast heuristic mode
            return
        try:
            import laya_coreml as laya

            self.agent = laya.load(
                str(self.model_dir),
                compute_units=self.compute_units,
                local_files_only=True,
            )
        except Exception:
            self.agent = None

    def _heuristic_parse(self, text: str) -> Optional[IntentDecision]:
        """Fast-path regex & keyword parser supporting English, Swahili, and Sheng code-switching."""
        t = text.lower().strip()

        # --- MUSIC ---
        # Swahili: "cheza muziki", "cheza wimbo", "simamisha muziki", "wimbo unaofuata", "ngoma"
        # English: "play music", "pause music", "next track", "skip", "previous song"
        if re.search(r"\b(cheza|play)\b", t) and not re.search(r"\b(game|snake)\b", t):
            # check if toggling or playing
            return IntentDecision("music", "play", {}, 0.95, False, "heuristic")
        if re.search(r"\b(pause|simamisha|stop music|tulia)\b", t):
            return IntentDecision("music", "pause", {}, 0.95, False, "heuristic")
        if re.search(r"\b(next song|next track|wimbo unaofuata|ngoma nyingine|skip song)\b", t):
            return IntentDecision("music", "next", {}, 0.95, False, "heuristic")
        if re.search(r"\b(previous song|prev track|wimbo uliopita)\b", t):
            return IntentDecision("music", "previous", {}, 0.95, False, "heuristic")
        if re.search(r"\b(what song|current track|wimbo gani|ngoma gani)\b", t):
            return IntentDecision("music", "get_current_track", {}, 0.95, False, "heuristic")

        # --- SYSTEM: VOLUME ---
        # Swahili: "ongeza sauti", "punguza sauti", "nyamazisha"
        # English: "volume up", "turn up volume", "volume down", "mute", "unmute"
        if re.search(r"\b(ongeza sauti|volume up|turn up)\b", t):
            return IntentDecision("system", "volume_up", {}, 0.95, False, "heuristic")
        if re.search(r"\b(punguza sauti|volume down|turn down)\b", t):
            return IntentDecision("system", "volume_down", {}, 0.95, False, "heuristic")
        if re.search(r"\b(mute|nyamazisha|zima sauti)\b", t):
            return IntentDecision("system", "mute", {}, 0.95, False, "heuristic")
        if re.search(r"\b(unmute|rudisha sauti)\b", t):
            return IntentDecision("system", "unmute", {}, 0.95, False, "heuristic")
        vol_match = re.search(r"\b(set volume to|weka sauti)\s+(\d+)\b", t)
        if vol_match:
            return IntentDecision(
                "system", "set_volume", {"level": int(vol_match.group(2))}, 0.95, False, "heuristic"
            )

        # --- SYSTEM: LOCK & SLEEP ---
        # Swahili: "funga screen", "funga kioo", "laza mac", "laza kompyuta"
        # English: "lock screen", "lock mac", "sleep mac", "put to sleep"
        if re.search(r"\b(lock screen|lock mac|funga kioo|funga screen)\b", t):
            return IntentDecision("system", "lock_screen", {}, 0.95, True, "heuristic")
        if re.search(r"\b(sleep mac|put mac to sleep|laza mac|laza kompyuta)\b", t):
            return IntentDecision("system", "sleep", {}, 0.95, True, "heuristic")
        if re.search(r"\b(dark mode|badili rangi ya kioo)\b", t):
            return IntentDecision("system", "toggle_dark_mode", {}, 0.95, False, "heuristic")

        # --- WORKSPACES & ROUTINES ---
        # "start coding", "anza coding", "coding workspace", "start research"
        if re.search(r"\b(start coding|anza coding|coding workspace)\b", t):
            return IntentDecision("workspaces", "activate", {"workspace": "coding"}, 0.95, False, "heuristic")
        if re.search(r"\b(start research|anza utafiti|research workspace)\b", t):
            return IntentDecision("workspaces", "activate", {"workspace": "research"}, 0.95, False, "heuristic")

        # --- NOTES ---
        # "open notes app and write a new note", "write a new note", "create note", "update the existing one", "andika note"
        if re.search(r"\b(open notes app and write a new note|open notes and write a new note|write a new note|write new note|create new note|create a new note|make a new note|andika note mpya|andika note|fungua notes uandike)\b", t):
            # Extract content if provided
            body = re.sub(r".*(write a new note|write new note|create new note|create a new note|andika note mpya|andika note)\s*", "", text, flags=re.IGNORECASE).strip()
            title = "Speed-X Note"
            if body and len(body.split()) <= 4:
                title = body
            params = {"title": title, "body": body if body else "Created with Speed-X Assistant."}
            return IntentDecision("notes", "create", params, 0.96, False, "heuristic")

        if re.search(r"\b(update the existing one|update existing note|update the existing note|update note|append to note|ongeza kwenye note|ongeza note|rekebisha note)\b", t):
            addition = re.sub(r".*(update the existing one|update existing note|update note|ongeza kwenye note|ongeza note)\s*", "", text, flags=re.IGNORECASE).strip()
            params = {"addition": addition if addition else "Updated via Speed-X."}
            return IntentDecision("notes", "update", params, 0.96, False, "heuristic")

        # --- EMAIL / MAIL ---
        # "send email with a message", "send an email with a message", "send email", "compose email", "tuma email"
        if re.search(r"\b(send email with a message|send an email with a message|send email|send an email|compose email|tuma email|tuma barua pepe)\b", t):
            # Parse possible recipient or message
            msg = re.sub(r".*(send email with a message|send an email with a message|send email|compose email|tuma email)\s*", "", text, flags=re.IGNORECASE).strip()
            recipient = ""
            to_match = re.search(r"\bto\s+([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)\b", text, re.IGNORECASE)
            if to_match:
                recipient = to_match.group(1)
                msg = msg.replace(to_match.group(0), "").strip()
            params = {
                "recipient": recipient,
                "subject": "Speed-X Quick Message",
                "message": msg if msg else "Hello from Speed-X Assistant!",
            }
            return IntentDecision("mail", "send", params, 0.95, False, "heuristic")

        # --- MAKE NEW FILE ---
        # "make new file", "create new file", "make a new file", "tengeneza faili", "unda faili"
        if re.search(r"\b(make new file|create new file|make a new file|create a file|make file|new file|tengeneza faili|unda faili|faili jipya)\b", t):
            name_match = re.search(r"\b(named|called|jina|file)\s+([a-zA-Z0-9_.-]+)", t)
            filename = name_match.group(2) if name_match else "SpeedX_Document.txt"
            return IntentDecision("files", "create", {"filename": filename}, 0.95, False, "heuristic")

        # --- APPS ---
        # Swahili: "fungua <app>", "washa <app>"
        # English: "open <app>", "launch <app>", "quit <app>", "close <app>"
        open_match = re.search(r"\b(open|launch|fungua|washa)\s+([a-zA-Z0-9\s]+)$", t)
        if open_match:
            app = open_match.group(2).strip()
            # Avoid mistaking "open file" or "open safari"
            if not app.startswith("file") and not app.startswith("pdf"):
                return IntentDecision("apps", "open", {"app": normalize_app_name(app)}, 0.90, False, "heuristic")

        quit_match = re.search(r"\b(quit|close|funga|zima)\s+([a-zA-Z0-9\s]+)$", t)
        if quit_match:
            app = quit_match.group(2).strip()
            if app in ("this", "hii", "current", "hii app", "this app"):
                app = context_engine.get_frontmost_app()
            if not app.startswith("tab") and not app.startswith("window"):
                return IntentDecision("apps", "quit", {"app": normalize_app_name(app)}, 0.90, True, "heuristic")

        if re.search(r"\b(running apps|apps zinazofanya kazi|list apps)\b", t):
            return IntentDecision("apps", "list_running", {}, 0.95, False, "heuristic")

        # --- FILES ---
        # Swahili: "tafuta pdf", "tafuta faili <jina>", "screenshot ya mwisho"
        # English: "find pdf", "find file <name>", "latest screenshot"
        if re.search(r"\b(find pdf|tafuta pdf)\b", t):
            query = re.sub(r".*(find pdf|tafuta pdf)", "", t).strip()
            return IntentDecision("files", "find_pdf", {"query": query}, 0.90, False, "heuristic")
        file_match = re.search(r"\b(find file|search file|tafuta faili)\s+(.+)$", t)
        if file_match:
            return IntentDecision("files", "search", {"query": file_match.group(2).strip()}, 0.90, False, "heuristic")
        if re.search(r"\b(latest screenshot|screenshot ya mwisho)\b", t):
            return IntentDecision("files", "latest_screenshot", {}, 0.95, False, "heuristic")

        # --- CLIPBOARD ---
        # Swahili: "angalia clipboard", "ubao wa kunakili", "futa clipboard"
        # English: "read clipboard", "check clipboard", "clear clipboard", "inspect clipboard"
        if re.search(r"\b(inspect clipboard|angalia clipboard|stats za clipboard)\b", t):
            return IntentDecision("clipboard", "inspect", {}, 0.95, False, "heuristic")
        if re.search(r"\b(read clipboard|what's on clipboard|kuna nini kwenye clipboard)\b", t):
            return IntentDecision("clipboard", "read", {}, 0.95, False, "heuristic")
        # --- SCREEN INTELLIGENCE ---
        # Swahili: "piga screenshot", "soma screen", "soma kioo", "angalia screen"
        # English: "take screenshot", "capture screen", "read screen", "what am i looking at"
        if re.search(r"\b(take screenshot|capture screen|piga screenshot|piga picha ya kioo)\b", t):
            return IntentDecision("screen", "capture", {}, 0.95, False, "heuristic")
        if re.search(r"\b(read screen|ocr screen|what am i looking at|soma screen|soma kioo|angalia screen)\b", t):
            return IntentDecision("screen", "read", {}, 0.95, False, "heuristic")

        return None

    def decide(self, prompt: str) -> IntentDecision:
        """Route user prompt to typed decision using Laya Core ML or fast heuristics."""
        # 1. Try fast-path heuristic first for zero-latency instant commands
        fast_result = self._heuristic_parse(prompt)
        if fast_result:
            return fast_result

        # 2. If needed, attempt to load Core ML agent for open-ended queries
        if self.agent is None and not self._attempted_load:
            self._load_agent()

        if self.agent is not None:
            try:
                res = self.agent.predict(
                    prompt,
                    {
                        "domain": {
                            "type": "choice",
                            "instructions": "Which domain best handles this Mac command?",
                            "criteria": ["system", "apps", "music", "files", "clipboard", "workspaces", "general"],
                        },
                        "sensitive": {
                            "type": "noul",
                            "instructions": "Does this action shut down, lock, or terminate programs?",
                        },
                    },
                )
                domain = res["answers"]["domain"]["choice"]
                confidence = res["answers"]["domain"]["confidence"]
                requires_conf = res["answers"]["sensitive"]["noul"] > 0.5

                # Map domain to standard action and extract parameters
                action = "auto"
                params = {"prompt": prompt}
                if domain == "files":
                    action = "search"
                    clean_q = re.sub(
                        r"(?i)\b(where is|where did i save|find|search|document|pdf|file|faili|tafuta|iko wapi|wapi)\b",
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

                return IntentDecision(
                    domain=domain,
                    action=action,
                    params=params,
                    confidence=confidence,
                    requires_confirmation=requires_conf,
                    source="coreml",
                )
            except Exception:
                pass

        # Fallback if unhandled
        return IntentDecision(
            domain="general",
            action="unhandled",
            params={"prompt": prompt},
            confidence=0.0,
            requires_confirmation=False,
            source="fallback",
        )
