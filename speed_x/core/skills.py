"""Learn & replay: remember what worked, run it again with no model.

A *skill* is an ordered list of typed steps (domain, action, params) saved under the
words that matter in the request. Next time the same request (any word order, any filler,
or the same pattern about another app) replays the steps straight through the normal
router, so guardrails still apply. Skills are learned from:

  * a successful plan the local/cloud AI had to build, or any multi-step plan, and
  * teaching:  "when I say focus mode, close slack and open notes".

What is never learned: anything that ends in a failure, anything needing confirmation,
anything that contains this moment's words (messages, notes, e-mails), and anything that
points at "this / it / here". A replay that fails is dropped after two strikes and the
request goes back to the planner, so a stale skill can't keep misfiring.
"""

import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..config import USER_CONFIG_DIR
from .store import load_json, save_json

SKILLS_FILE = USER_CONFIG_DIR / "skills.json"
EXPIRE_DAYS = 30
MAX_FAILS = 2

STOP = set(
    "a an the to for of and then please can could you would will me my i'd i want need "
    "kindly just so um uh okay ok hey hi speed x nataka tafadhali naomba basi".split()
)
FILLER = set("now again also quick quickly real really actually yeah bro".split())
DEICTIC = re.compile(r"\b(it|this|that|these|those|here|there|him|her|them|hii|hiyo|hapa)\b", re.I)

# Steps carrying this moment's words are never replayed.
VOLATILE_PARAMS = {"text", "message", "body", "subject", "recipient", "to", "question", "request", "prompt"}
NEVER_LEARN_DOMAINS = {"assistant", "general", "messaging", "mail", "notes", "clipboard", "skills"}
APP_PARAM_ACTIONS = {("apps", "open"), ("apps", "quit"), ("apps", "switch")}


def gist(text: str) -> List[str]:
    """The words that matter, in order: 'um, could you open Safari please' -> ['open', 'safari']."""
    words = re.findall(r"[a-z0-9']+", text.lower().replace("’", "'"))
    return [w for w in words if w not in STOP and w not in FILLER]


def key_of(text: str) -> str:
    return " ".join(gist(text))


@dataclass
class Replay:
    key: str
    steps: List[Dict[str, Any]]


class SkillStore:
    def __init__(self, path=SKILLS_FILE, resolve_app=None):
        self.path = path
        self._lock = threading.Lock()
        self._resolve_app = resolve_app  # callable(str) -> Optional[str]; injected for tests
        self._skills: Dict[str, Dict[str, Any]] = self._load()

    # ---- persistence ------------------------------------------------------------------
    def _load(self) -> Dict[str, Dict[str, Any]]:
        raw = load_json(self.path, {})
        clean = {}
        for k, v in raw.items():
            if isinstance(v, dict) and isinstance(v.get("steps"), list) and v["steps"]:
                clean[k] = v
        return clean

    def _save(self) -> None:
        cutoff = time.time() - EXPIRE_DAYS * 86400
        self._skills = {
            k: v
            for k, v in self._skills.items()
            if v.get("mine") or max(v.get("used", 0), v.get("at", 0)) >= cutoff
        }
        save_json(self.path, self._skills)

    # ---- what may be remembered ---------------------------------------------------------
    @staticmethod
    def replayable(steps: List[Dict[str, Any]]) -> bool:
        if not steps:
            return False
        for s in steps:
            if s["domain"] in NEVER_LEARN_DOMAINS or s.get("confirm"):
                return False
            if VOLATILE_PARAMS & set(s.get("params", {})):
                return False
        return True

    def learn(
        self, prompt: str, steps: List[Dict[str, Any]], mine: bool = False
    ) -> Optional[str]:
        """Save a successful plan. Returns the key if it was stored."""
        key = key_of(prompt)
        if not key or (not mine and DEICTIC.search(prompt)):
            return None
        if not self.replayable(steps):
            return None
        entry: Dict[str, Any] = {"steps": steps, "at": time.time(), "fails": 0, "used": 0}
        template = self._app_template(key, steps)
        if template:
            entry["template"] = template
        with self._lock:
            old = self._skills.get(key, {})
            entry["mine"] = bool(mine or old.get("mine"))
            self._skills[key] = entry
            self._save()
        return key

    def _app_template(self, key: str, steps: List[Dict[str, Any]]) -> Optional[str]:
        """'open safari' learned once also serves 'open mail': words naming the single app become {app}."""
        apps = {s["params"].get("app") for s in steps if (s["domain"], s["action"]) in APP_PARAM_ACTIONS}
        apps.discard(None)
        if len(apps) != 1:
            return None
        app = str(apps.pop()).lower()
        words = key.split()
        n = len(app.split())
        for i in range(len(words) - n + 1):
            if " ".join(words[i : i + n]) == app:
                return " ".join(words[:i] + ["{app}"] + words[i + n :])
        return None

    # ---- lookup -----------------------------------------------------------------------
    def find(self, prompt: str) -> Optional[Replay]:
        g = gist(prompt)
        if not g or (DEICTIC.search(prompt) and not self._skills.get(key_of(prompt))):
            return None
        key = " ".join(g)
        with self._lock:
            hit = self._skills.get(key)
            if hit:
                return Replay(key, [dict(s, params=dict(s["params"])) for s in hit["steps"]])
            # same words, any order
            sorted_g = sorted(g)
            for k, v in self._skills.items():
                if sorted(k.split()) == sorted_g and self._order_safe(v["steps"], k.split(), g):
                    return Replay(k, [dict(s, params=dict(s["params"])) for s in v["steps"]])
            # same pattern about another app
            for n in (3, 2, 1):
                for i in range(len(g) - n + 1):
                    cand = " ".join(g[i : i + n])
                    shape = " ".join(g[:i] + ["{app}"] + g[i + n :])
                    for k, v in self._skills.items():
                        if v.get("template") == shape:
                            app = self._resolve(cand)
                            if app:
                                return Replay(k, self._swap_app(v["steps"], app))
        return None

    @staticmethod
    def _order_safe(steps, a: List[str], b: List[str]) -> bool:
        """Words the steps depend on keep their order ('notes left, mail right' != 'mail left, notes right')."""
        used = set(re.findall(r"[a-z0-9]+", " ".join(str(s["params"]) for s in steps).lower()))
        x, y = [w for w in a if w in used], [w for w in b if w in used]
        return x == y or len(steps) == 1

    def _resolve(self, name: str) -> Optional[str]:
        if self._resolve_app is not None:
            return self._resolve_app(name)
        try:
            from ..tools.apps import resolve_app

            return resolve_app(name)
        except Exception:
            return None

    @staticmethod
    def _swap_app(steps, app: str):
        out = []
        for s in steps:
            s = dict(s, params=dict(s["params"]))
            if (s["domain"], s["action"]) in APP_PARAM_ACTIONS:
                s["params"]["app"] = app
            out.append(s)
        return out

    # ---- outcomes -------------------------------------------------------------------------
    def mark_used(self, key: str) -> None:
        with self._lock:
            if key in self._skills:
                self._skills[key]["used"] = time.time()
                self._skills[key]["fails"] = 0
                self._save()

    def mark_failed(self, key: str) -> bool:
        """Strike a skill whose replay failed. Returns True if it was dropped."""
        with self._lock:
            v = self._skills.get(key)
            if not v:
                return False
            v["fails"] = v.get("fails", 0) + 1
            dropped = v["fails"] >= MAX_FAILS and not v.get("mine")
            if dropped:
                del self._skills[key]
            self._save()
            return dropped

    def forget(self, name: str) -> bool:
        key = key_of(name)
        with self._lock:
            if self._skills.pop(key, None) is None:
                return False
            self._save()
            return True

    def names(self) -> List[Tuple[str, bool]]:
        return sorted((k, bool(v.get("mine"))) for k, v in self._skills.items())


# --- teaching phrases ---------------------------------------------------------------------
_TEACH = re.compile(
    r"^(?:when(?:ever)?|if) i say\s+[\"“']?(?P<name>.+?)[\"”']?\s*(?:[,:]|\bthen\b|\b(?:you\s+)?(?:do|run)\b)\s*(?P<action>.+)$",
    re.I,
)
_TEACH2 = re.compile(
    r"^(?:learn|remember|save)\s+(?:that\s+)?[\"“']?(?P<name>.+?)[\"”']?\s+(?:means|as|is)\s+(?P<action>.+)$",
    re.I,
)
_FORGET = re.compile(r"^(?:forget|delete|remove|unlearn)\s+(?:the\s+)?(?:shortcut|skill)\s+[\"“']?(?P<name>.+?)[\"”']?$", re.I)
_LIST = re.compile(r"^(?:what|which|show|list)\b.*\b(?:shortcuts?|skills?)\b.*$", re.I)


def parse_teaching(text: str) -> Optional[Dict[str, str]]:
    t = text.strip().rstrip(".!?")
    m = _FORGET.match(t)
    if m:
        return {"op": "forget", "name": m["name"]}
    if _LIST.match(t):
        return {"op": "list"}
    m = _TEACH.match(t) or _TEACH2.match(t)
    if m and len(gist(m["name"])) >= 1 and gist(m["action"]):
        return {"op": "teach", "name": m["name"].strip(), "action": m["action"].strip()}
    return None


skills = SkillStore()
