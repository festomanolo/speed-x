"""Meeting copilot: live notes during a call, a structured summary after.

The UI streams finished sentences from the microphone into `add_line`. Everything is
saved locally as Markdown in ~/.config/speed_x/meetings/. The summary is extractive
(action items, decisions, open questions, topics), so it works fully offline; if a local
or cloud model is available it adds a short written recap on top.
"""

import datetime as dt
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import USER_CONFIG_DIR

MEETINGS_DIR = USER_CONFIG_DIR / "meetings"

ACTION = re.compile(
    r"\b(i'll|i will|we'll|we will|you'll|you will|need to|needs to|have to|has to|should|must|todo|to-do|"
    r"action item|follow up|follow-up|send|schedule|deadline|by (?:monday|tuesday|wednesday|thursday|friday|"
    r"saturday|sunday|tomorrow|tonight|eod|end of (?:day|week)|next week)|nitafanya|tutafanya|lazima)\b",
    re.I,
)
DECISION = re.compile(r"\b(decided|agreed|let's go with|we'll go with|the plan is|approved|settled on|tumekubaliana)\b", re.I)
QUESTION = re.compile(r"(\?\s*$)|^(?:who|what|when|where|why|how|can|could|should|do|does|did|is|are)\b", re.I)
STOPWORDS = set(
    "the a an and or but to of in on for with is are was were be been it this that i you we they he she at as by "
    "from have has had will would can could should not so if then than just about like yeah okay ok um uh really "
    "going get got do does did what when where why how our your their my me us them there here one also very".split()
)


def _sentences(lines: List[str]) -> List[str]:
    out = []
    for line in lines:
        out += [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()]
    return out


def summarize(lines: List[str], notes: Optional[List[str]] = None) -> Dict[str, List[str]]:
    sents = _sentences(lines)
    actions = [s for s in sents if ACTION.search(s) and not s.endswith("?")]
    decisions = [s for s in sents if DECISION.search(s)]
    questions = [s for s in sents if QUESTION.search(s) and s.endswith("?")]
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z'-]{3,}", " ".join(lines).lower()) if w not in STOPWORDS]
    topics = [w for w, _ in Counter(words).most_common(6)]
    return {
        "actions": list(dict.fromkeys(actions))[:12],
        "decisions": list(dict.fromkeys(decisions))[:8],
        "questions": list(dict.fromkeys(questions))[:8],
        "topics": topics,
        "notes": list(notes or []),
    }


def to_markdown(title: str, started: dt.datetime, lines: List[str], summary: Dict[str, List[str]], recap: str = "") -> str:
    def section(head: str, items: List[str], box: bool = False) -> str:
        if not items:
            return ""
        mark = "- [ ] " if box else "- "
        return f"## {head}\n" + "\n".join(mark + i for i in items) + "\n\n"

    minutes = max(1, round((dt.datetime.now() - started).total_seconds() / 60))
    md = f"# {title}\n\n*{started.strftime('%A %-d %B %Y, %-I:%M %p')} · about {minutes} min*\n\n"
    if recap:
        md += f"## Recap\n{recap.strip()}\n\n"
    md += section("Action items", summary["actions"], box=True)
    md += section("Decisions", summary["decisions"])
    md += section("Open questions", summary["questions"])
    md += section("Your notes", summary["notes"])
    if summary["topics"]:
        md += "## Topics\n" + ", ".join(summary["topics"]) + "\n\n"
    md += "## Transcript\n" + "\n".join(lines) + "\n"
    return md


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "meeting"


class MeetingSession:
    def __init__(self, title: str):
        self.title = title.strip() or "Meeting"
        self.started = dt.datetime.now()
        self.lines: List[str] = []
        self.notes: List[str] = []


class MeetingManager:
    def __init__(self, directory: Path = MEETINGS_DIR, recap=None):
        self.dir = directory
        self.session: Optional[MeetingSession] = None
        self._lock = threading.Lock()
        self._recap = recap  # callable(transcript) -> str|None; injected (model-backed, optional)

    @property
    def active(self) -> bool:
        return self.session is not None

    def start(self, title: str = "") -> MeetingSession:
        with self._lock:
            self.session = MeetingSession(title)
            return self.session

    def add_line(self, text: str) -> bool:
        text = text.strip()
        with self._lock:
            if not self.session or not text:
                return False
            if self.session.lines and self.session.lines[-1] == text:
                return False
            self.session.lines.append(text)
            return True

    def add_note(self, text: str) -> bool:
        with self._lock:
            if not self.session or not text.strip():
                return False
            self.session.notes.append(text.strip())
            return True

    def stop(self) -> Optional[Path]:
        with self._lock:
            s, self.session = self.session, None
        if not s:
            return None
        summary = summarize(s.lines, s.notes)
        recap = ""
        if self._recap and s.lines:
            try:
                recap = self._recap("\n".join(s.lines)) or ""
            except Exception:
                recap = ""
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{s.started.strftime('%Y-%m-%d_%H%M')}_{_slug(s.title)}.md"
        path.write_text(to_markdown(s.title, s.started, s.lines, summary, recap))
        path.chmod(0o600)
        return path

    def list(self, limit: int = 10) -> List[Path]:
        if not self.dir.exists():
            return []
        return sorted(self.dir.glob("*.md"), reverse=True)[:limit]

    def last_summary(self) -> Optional[str]:
        files = self.list(1)
        if not files:
            return None
        text = files[0].read_text()
        return text.split("## Transcript")[0].strip()


meetings = MeetingManager()
