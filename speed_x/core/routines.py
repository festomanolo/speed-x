"""Scheduled routines: "every weekday at 8:30 open mail and play music".

Routines persist in ~/.config/speed_x/routines.json and are checked every 20 s by a
background thread owned by the engine daemon. A routine runs through the normal router,
so guardrails apply: a step that needs confirmation is *skipped and reported*, never
auto-confirmed. If Speed-X wasn't running at the time, the routine still runs once when
it starts, as long as it is within GRACE_MIN minutes of the scheduled time.
"""

import datetime as dt
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config import USER_CONFIG_DIR
from .store import load_json, save_json

ROUTINES_FILE = USER_CONFIG_DIR / "routines.json"
GRACE_MIN = 30
DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DAY_ALIASES = {
    "mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6,
    "jumatatu": 0, "jumanne": 1, "jumatano": 2, "alhamisi": 3, "ijumaa": 4, "jumamosi": 5, "jumapili": 6,
}
for _i, _n in enumerate(DAY_NAMES):
    DAY_ALIASES[_n] = _i

_TIME = r"(?P<time>noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)?)"
_DAYWORD = (
    r"(?:weekdays?|weekends?|days?|siku|mondays?|tuesdays?|wednesdays?|thursdays?|fridays?|saturdays?|sundays?|"
    r"tues?|thurs?|mon|wed|thu|fri|sat|sun|jumatatu|jumanne|jumatano|alhamisi|ijumaa|jumamosi|jumapili)"
)
_EVERY = rf"(?:every|each|kila)\s+(?P<days>{_DAYWORD}(?:\s*(?:,|&|\band\b|\bna\b)\s*{_DAYWORD})*)"
_SEP = r"(?:\s*[,:]\s*|\s+(?:to|then)\s+|\s+)"
_PATTERNS = [
    re.compile(rf"^{_EVERY}\s+at\s+{_TIME}{_SEP}(?P<cmd>.+)$", re.I),
    re.compile(rf"^at\s+{_TIME}\s+{_EVERY}{_SEP}(?P<cmd>.+)$", re.I),
    re.compile(rf"^(?P<cmd>.+?)\s+{_EVERY}\s+at\s+{_TIME}$", re.I),
]
_ROUTINE_LEAD = re.compile(r"^(?:please\s+)?(?:create|add|set up|schedule|make)(?:\s+a)?(?:\s+routine)?(?:\s+to)?[:,]?\s+", re.I)


def parse_time(raw: str) -> Optional[Tuple[int, int]]:
    s = raw.strip().lower().replace(".", "")
    if s == "noon":
        return 12, 0
    if s == "midnight":
        return 0, 0
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", s)
    if not m:
        return None
    h, mi, mer = int(m[1]), int(m[2] or 0), m[3]
    if mi > 59:
        return None
    if mer:
        if not 1 <= h <= 12:
            return None
        h = h % 12 + (12 if mer == "pm" else 0)
    elif h > 23:
        return None
    return h, mi


def parse_days(raw: str) -> Optional[List[int]]:
    s = raw.strip().lower()
    if s in ("day", "days", "morning", "evening", "night", "siku", "daily"):
        return list(range(7))
    if s in ("weekday", "weekdays", "work day", "workday", "weekday morning"):
        return [0, 1, 2, 3, 4]
    if s in ("weekend", "weekends"):
        return [5, 6]
    days = []
    for part in re.split(r"\s*(?:,|&|\band\b|\bna\b)\s*", s):
        part = part.strip().rstrip("s") if part.strip() not in DAY_ALIASES else part.strip()
        if part not in DAY_ALIASES:
            return None
        days.append(DAY_ALIASES[part])
    return sorted(set(days)) or None


def parse_routine(text: str) -> Optional[Dict[str, Any]]:
    """'every weekday at 8:30 open mail' -> {'time': '08:30', 'days': [0..4], 'command': 'open mail'} or None."""
    t = _ROUTINE_LEAD.sub("", text.strip().rstrip(".!?"))
    t = re.sub(r"^(?:daily|every day)\s+at\s+", "every day at ", t, flags=re.I)
    for pat in _PATTERNS:
        m = pat.match(t)
        if not m:
            continue
        hm, days = parse_time(m["time"]), parse_days(m["days"])
        cmd = m["cmd"].strip(" ,")
        if hm and days and cmd:
            return {"time": f"{hm[0]:02d}:{hm[1]:02d}", "days": days, "command": cmd}
    return None


def describe_when(days: List[int], hhmm: str) -> str:
    h, m = map(int, hhmm.split(":"))
    clock = dt.time(h, m).strftime("%-I:%M %p")
    if days == list(range(7)):
        d = "every day"
    elif days == [0, 1, 2, 3, 4]:
        d = "every weekday"
    elif days == [5, 6]:
        d = "every weekend"
    else:
        d = "every " + ", ".join(DAY_NAMES[i].title() for i in days)
    return f"{d} at {clock}"


class RoutineStore:
    def __init__(self, path=ROUTINES_FILE):
        self.path = path
        self._lock = threading.Lock()
        raw = load_json(path, [])
        self.items: List[Dict[str, Any]] = [r for r in raw if isinstance(r, dict) and "command" in r and "time" in r]
        self._next = max([r.get("id", 0) for r in self.items] + [0]) + 1

    def _save(self):
        save_json(self.path, self.items)

    def add(self, time_s: str, days: List[int], command: str) -> Dict[str, Any]:
        with self._lock:
            for r in self.items:  # same routine twice is one routine
                if r["time"] == time_s and r["days"] == days and r["command"].lower() == command.lower():
                    return r
            r = {"id": self._next, "time": time_s, "days": days, "command": command, "last": ""}
            self._next += 1
            self.items.append(r)
            self._save()
            return r

    def remove(self, ref: str) -> List[Dict[str, Any]]:
        """Remove by number ("2") or by words in the command ("music")."""
        ref = ref.strip().lower()
        with self._lock:
            if ref.isdigit():
                gone = [r for r in self.items if r["id"] == int(ref)]
            elif ref in ("all", "everything"):
                gone = list(self.items)
            else:
                gone = [r for r in self.items if ref and ref in r["command"].lower()]
            if gone:
                self.items = [r for r in self.items if r not in gone]
                self._save()
            return gone

    def due(self, now: dt.datetime) -> List[Dict[str, Any]]:
        out = []
        today = now.date().isoformat()
        with self._lock:
            for r in self.items:
                if now.weekday() not in r["days"] or r.get("last") == today:
                    continue
                h, m = map(int, r["time"].split(":"))
                at = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if at <= now <= at + dt.timedelta(minutes=GRACE_MIN):
                    r["last"] = today
                    out.append(dict(r))
            if out:
                self._save()
        return out


class Scheduler(threading.Thread):
    """Calls `fire(routine)` for each due routine. The callback must be cheap (it queues work)."""

    def __init__(self, store: RoutineStore, fire: Callable[[Dict[str, Any]], None], interval: float = 20.0):
        super().__init__(name="routines", daemon=True)
        self.store, self.fire, self.interval = store, fire, interval
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            for r in self.store.due(dt.datetime.now()):
                try:
                    self.fire(r)
                except Exception:
                    pass
            self._halt.wait(self.interval)

    def stop(self):
        self._halt.set()


routines = RoutineStore()
