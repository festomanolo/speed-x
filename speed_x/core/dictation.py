"""Dictation cleanup + personal dictionary. Pure text rules, no model needed.

Raw on-device speech text goes in ("um so new line scratch that four actually five ..."),
clean typed text comes out. The personal dictionary does two jobs:
  * words   - names and jargon (Kilimanjaro, Nadina, kubectl) that a near-miss from the
              recognizer is snapped to ("kilimanjaro" <- "kili man jaro" / "kilimanjara")
  * replace - exact "heard -> written" rules ("my email" -> "me@example.com")
It also keeps words-today / all-time / sessions counters for the stats line.
"""

import datetime
import difflib
import re
import threading
from typing import Any, Dict, List

from ..config import USER_CONFIG_DIR
from .store import load_json, save_json

DICT_FILE = USER_CONFIG_DIR / "dictionary.json"
STATS_FILE = USER_CONFIG_DIR / "dictation_stats.json"

FILLERS = r"(?:u+m+|u+h+|e+r+m*|h+m+|m{2,}|e+h+|a+h+)"
NUMBER_WORDS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred".split()
    )
}
_NUM = r"(?:\d+(?:[.,]\d+)?|" + "|".join(NUMBER_WORDS) + r")"

# Spoken punctuation -> (text, attaches to the previous word)
SPOKEN = [
    (r"new paragraph", "\n\n", True),
    (r"new line|next line", "\n", True),
    (r"question mark", "?", True),
    (r"exclamation (?:mark|point)", "!", True),
    (r"full stop|period", ".", True),
    (r"comma", ",", True),
    (r"semi ?colon", ";", True),
    (r"colon", ":", True),
    (r"open (?:paren|parenthesis|bracket)", "(", False),
    (r"close (?:paren|parenthesis|bracket)", ")", True),
    (r"(?:hyphen|dash)", "-", False),
]


class Dictionary:
    def __init__(self, path=DICT_FILE):
        self.path = path
        self._lock = threading.Lock()
        data = load_json(path, {})
        self.words: List[str] = [w for w in data.get("words", []) if isinstance(w, str)]
        self.replace: Dict[str, str] = {
            k: v for k, v in data.get("replace", {}).items() if isinstance(k, str) and isinstance(v, str)
        }

    def _save(self):
        save_json(self.path, {"words": self.words, "replace": self.replace})

    def add_word(self, word: str) -> bool:
        word = word.strip()
        with self._lock:
            if not word or word.lower() in (w.lower() for w in self.words):
                return False
            self.words.append(word)
            self._save()
            return True

    def add_replace(self, heard: str, written: str) -> None:
        with self._lock:
            self.replace[heard.strip().lower()] = written.strip()
            self._save()

    def remove(self, term: str) -> bool:
        t = term.strip().lower()
        with self._lock:
            before = len(self.words) + len(self.replace)
            self.words = [w for w in self.words if w.lower() != t]
            self.replace = {k: v for k, v in self.replace.items() if k != t and v.lower() != t}
            changed = len(self.words) + len(self.replace) != before
            if changed:
                self._save()
            return changed

    def hints(self) -> List[str]:
        """Phrases to give the speech recognizer as vocabulary hints."""
        return list(dict.fromkeys(self.words + list(self.replace)))[:100]

    # -- application ---------------------------------------------------------------------
    def apply(self, text: str) -> str:
        for heard, written in sorted(self.replace.items(), key=lambda kv: -len(kv[0])):
            text = re.sub(rf"(?<!\w){re.escape(heard)}(?!\w)", lambda _m, w=written: w, text, flags=re.I)
        if not self.words:
            return text
        squashed = {re.sub(r"\W", "", w.lower()): w for w in self.words}
        tokens = re.findall(r"\s+|\S+", text)
        out: List[str] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.isspace():
                out.append(tok)
                i += 1
                continue
            # try 3..1 words joined ("kili man jaro" -> kilimanjaro)
            matched = False
            for n in (3, 2, 1):
                idx, parts = i, []
                while idx < len(tokens) and len(parts) < n:
                    if not tokens[idx].isspace():
                        parts.append(tokens[idx])
                    idx += 1
                if len(parts) < n:
                    continue
                core = [re.sub(r"^\W+|\W+$", "", p) for p in parts]
                joined = re.sub(r"\W", "", "".join(core).lower())
                if len(joined) < 4:
                    continue
                best = squashed.get(joined)
                if not best:
                    close = difflib.get_close_matches(joined, list(squashed), n=1, cutoff=0.86)
                    best = squashed[close[0]] if close else None
                if best:
                    lead = re.match(r"^\W*", parts[0])[0]
                    trail = re.search(r"\W*$", parts[-1])[0]
                    out.append(lead + best + trail)
                    i = idx
                    matched = True
                    break
            if not matched:
                out.append(tok)
                i += 1
        return "".join(out)


def _to_number(tok: str):
    tok = tok.lower().replace(",", ".")
    if tok in NUMBER_WORDS:
        return NUMBER_WORDS[tok]
    try:
        return float(tok)
    except ValueError:
        return None


def cleanup(text: str, dictionary: "Dictionary | None" = None) -> str:
    """Raw speech text -> what you meant to type."""
    t = " " + text.strip() + " "
    # fillers (and "you know" only when set off by punctuation)
    t = re.sub(rf"(?i)(?<=\s){FILLERS}[,.]?(?=\s)", " ", t)
    t = re.sub(r"(?i),\s*you know,?", ",", t)
    t = re.sub(r"\s+", " ", t)

    # "scratch that" / "never mind that": drop the clause before it (back to the last sentence mark or spoken break)
    def scratch(s: str) -> str:
        pat = re.compile(r"(?i)\b(?:scratch that|delete that|strike that|forget that)\b[,.]?\s*")
        while True:
            m = pat.search(s)
            if not m:
                return s
            before = s[: m.start()]
            cut = max(before.rfind(". "), before.rfind("? "), before.rfind("! "), before.rfind("\n"))
            # spoken breaks that haven't been converted yet
            for br in (" new line ", " new paragraph ", " full stop ", " period ", " question mark "):
                cut = max(cut, before.lower().rfind(br) + len(br) - 1 if br in before.lower() else -1)
            before = before[: cut + 1] if cut >= 0 else ""
            s = before + s[m.end() :]

    t = scratch(t)

    # "four, actually five" -> "five" (only for two numbers: "I actually like it" is left alone)
    t = re.sub(
        rf"(?i)\b({_NUM})\b[,]?\s+(?:no[,]?\s+)?(?:actually|i mean|sorry)[,]?\s+({_NUM})\b",
        lambda m: m[2] if _to_number(m[1]) is not None and _to_number(m[2]) is not None else m[0],
        t,
    )

    # spoken punctuation
    for pat, rep, attach in SPOKEN:
        if attach:
            t = re.sub(rf"(?i)\s+(?:{pat})\b(?=\W|$)", lambda _m, r=rep: r, t)
        else:
            t = re.sub(rf"(?i)\b(?:{pat})\b", rep, t)
    t = re.sub(r"[ \t]*\n[ \t]*", lambda m: "\n", t)
    t = re.sub(r"([,;:.!?])(?=[A-Za-z])", r"\1 ", t)
    t = re.sub(r"\s+([,;:.!?)])", r"\1", t)
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"(?<=\w) - (?=\w)", " - ", t)
    t = re.sub(r"[ \t]{2,}", " ", t).strip()

    # dictionary (before capitalisation so dictionary casing wins)
    if dictionary is not None:
        t = dictionary.apply(t)

    # "i" / "i'm" and sentence capitals
    t = re.sub(r"\bi\b(?=\W|$)", "I", t)
    t = re.sub(r"(^|[.!?]\s+|\n)([a-z])", lambda m: m[1] + m[2].upper(), t)
    return t


# --- stats --------------------------------------------------------------------------------
def record(text: str, path=STATS_FILE) -> Dict[str, Any]:
    stats = load_json(path, {})
    today = datetime.date.today().isoformat()
    words = len(re.findall(r"\S+", text))
    if stats.get("day") != today:
        stats["day"], stats["today"] = today, 0
    stats["today"] = stats.get("today", 0) + words
    stats["total"] = stats.get("total", 0) + words
    stats["sessions"] = stats.get("sessions", 0) + 1
    save_json(path, stats)
    return stats


def read_stats(path=STATS_FILE) -> Dict[str, Any]:
    stats = load_json(path, {})
    if stats.get("day") != datetime.date.today().isoformat():
        stats["today"] = 0
    return {"today": stats.get("today", 0), "total": stats.get("total", 0), "sessions": stats.get("sessions", 0)}


def minutes_saved(words: int) -> float:
    """Typing ~40 wpm vs speaking ~150 wpm."""
    return round(words / 40 - words / 150, 1)


dictionary = Dictionary()
