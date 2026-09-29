"""Timers, reminders, and time/date answers."""

import datetime
import json
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from ..config import USER_CONFIG_DIR
from ..core import events
from .base import BaseTool, ToolResult, registry


def _describe(seconds: int) -> str:
    parts = []
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    return " ".join(parts) or "0 seconds"


TIMERS_FILE = USER_CONFIG_DIR / "timers.json"
MISSED_GRACE_S = 12 * 3600  # a timer that ended while the engine was down still notifies, unless it's stale


def _notify(title: str, message: str):
    script = (
        f'display notification "{message.replace(chr(34), "")}" '
        f'with title "{title.replace(chr(34), "")}" sound name "Glass"'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True)


class TimerTool(BaseTool):
    name = "timer"
    description = "Countdown timers, Apple Reminders, and the current time/date."
    supported_actions = ["set", "list", "cancel", "remind", "time", "date"]

    def __init__(self, store=TIMERS_FILE):
        self._timers: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._store = store
        self._restore()

    # Timers are saved to disk so they survive the engine (or the whole app) restarting.
    def _save(self):
        try:
            data = [{"label": t["label"], "ends": t["ends"]} for t in self._timers]
            self._store.write_text(json.dumps(data))
        except OSError:
            pass

    def _restore(self):
        try:
            saved = json.loads(self._store.read_text())
        except (OSError, ValueError):
            return
        now = time.time()
        for item in saved if isinstance(saved, list) else []:
            try:
                ends, label = float(item["ends"]), str(item.get("label", ""))
            except (KeyError, TypeError, ValueError):
                continue
            if ends > now:
                self._schedule(label, ends)
            elif now - ends < MISSED_GRACE_S:
                # Finished while Speed-X was off: tell the user now, once.
                self._schedule(label, now + 1, missed_at=ends)
        self._save()

    def _schedule(self, label: str, ends: float, missed_at: Optional[float] = None) -> Dict[str, Any]:
        entry: Dict[str, Any] = {"label": label, "ends": ends, "missed_at": missed_at}
        timer = threading.Timer(max(0.0, ends - time.time()), self._fire, args=(entry,))
        timer.daemon = True
        entry["handle"] = timer
        with self._lock:
            self._timers.append(entry)
        timer.start()
        return entry

    def _fire(self, entry: Dict[str, Any]):
        with self._lock:
            if entry in self._timers:
                self._timers.remove(entry)
            self._save()
        label = entry["label"]
        message = f"{label} — time's up!" if label else "Time's up!"
        if entry.get("missed_at"):
            ended = datetime.datetime.fromtimestamp(entry["missed_at"]).strftime("%-I:%M %p")
            message = f"{label or 'Your timer'} finished at {ended} while Speed-X was off."
        _notify("Speed-X Timer", message)
        events.emit("timer_done", label=label or "Timer")

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        now = datetime.datetime.now()

        if action == "set":
            seconds = int(params.get("seconds", 0))
            if seconds <= 0:
                return ToolResult(success=False, message="How long should the timer run?")
            label = params.get("label", "").strip()
            self._schedule(label, time.time() + seconds)
            with self._lock:
                self._save()
            suffix = f" to {label}" if label else ""
            events.emit("timer_started", seconds=seconds, label=label or "Timer")
            return ToolResult(success=True, message=f"Timer set for {_describe(seconds)}{suffix}.", data={"seconds": seconds})

        if action == "list":
            if not self._timers:
                return ToolResult(success=True, message="No timers running.")
            parts = [f"{t['label'] or 'Timer'}: {_describe(int(t['ends'] - time.time()))} left" for t in self._timers]
            return ToolResult(success=True, message="; ".join(parts))

        if action == "cancel":
            with self._lock:
                count = len(self._timers)
                for t in self._timers:
                    t["handle"].cancel()
                self._timers.clear()
                self._save()
            return ToolResult(success=True, message=f"Cancelled {count} timer(s)." if count else "No timers to cancel.")

        if action == "remind":
            text = params.get("text", "").strip() or "Reminder from Speed-X"
            seconds = int(params.get("seconds", 0))
            safe = text.replace('"', '\\"')
            if seconds > 0:
                script = (
                    f'tell application "Reminders" to make new reminder with properties '
                    f'{{name:"{safe}", remind me date:((current date) + {seconds})}}'
                )
                when = f" in {_describe(seconds)}"
            else:
                script = f'tell application "Reminders" to make new reminder with properties {{name:"{safe}"}}'
                when = ""
            try:
                self._run_applescript(script)
            except Exception as e:
                return ToolResult(success=False, message=f"Couldn't create the reminder: {e}")
            return ToolResult(success=True, message=f"I'll remind you to {text}{when}.", data={"text": text})

        if action == "time":
            return ToolResult(success=True, message=f"It's {now.strftime('%-I:%M %p')}.")

        if action == "date":
            return ToolResult(success=True, message=f"Today is {now.strftime('%A, %B %-d, %Y')}.")

        return ToolResult(success=False, message=f"Unknown timer action: '{action}'.")


registry.register(TimerTool())
