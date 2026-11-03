"""Tools for the 'assistant' features: shortcuts, routines, dictation, meetings, updates, agents, on-screen guide.

Each is a normal BaseTool so the router's guardrails, logging and previews apply unchanged.
"""

import subprocess
from typing import Any, Callable, Dict, List, Optional

from ..core import events
from ..core import dictation as dictation_mod
from ..core.agents import agents
from ..core.meeting import meetings
from ..core.routines import describe_when, routines
from ..core.skills import skills
from ..core.updater import check as check_update, download_and_open
from .base import BaseTool, ToolResult, registry


def _json_param(label: str, p: Dict[str, Any], key: str) -> str:
    return str(p.get(key, "")).strip()


class SkillsTool(BaseTool):
    name = "skills"
    description = "Teach, list and forget your own voice shortcuts."
    supported_actions = ["teach", "forget", "list"]
    # Set by the router: callable(text) -> List[IntentDecision]
    planner: Optional[Callable[[str], list]] = None

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        p = params or {}
        if action == "list":
            items = skills.names()
            if not items:
                return ToolResult(True, "No shortcuts yet. Say “when I say focus mode, close slack and open notes”.")
            return ToolResult(True, "Shortcuts: " + ", ".join(f"“{k}”" + ("" if mine else " (learned)") for k, mine in items) + ".")
        if action == "forget":
            name = _json_param("name", p, "name")
            return self._forget(name)
        if action == "teach":
            return self._teach(_json_param("name", p, "name"), _json_param("action", p, "action"))
        return ToolResult(False, f"Unknown skills action '{action}'.")

    def _forget(self, name: str) -> ToolResult:
        if skills.forget(name):
            return ToolResult(True, f"Forgot “{name}”.")
        return ToolResult(False, f"I don't have a shortcut called “{name}”.")

    def _teach(self, name: str, action: str) -> ToolResult:
        if not self.planner:
            return ToolResult(False, "Shortcuts aren't ready yet.")
        steps = self.planner(action)
        if not steps or any(not d.handled for d in steps):
            return ToolResult(False, f"I didn't understand “{action}”, so I couldn't save it.")
        recorded = [
            {"domain": d.domain, "action": d.action, "params": dict(d.params), "confirm": bool(d.requires_confirmation)}
            for d in steps
        ]
        if not skills.replayable(recorded):
            return ToolResult(False, "That includes something that must be said fresh each time (a message, note or sensitive step), so I can't save it as a shortcut.")
        if not skills.learn(name, recorded, mine=True):
            return ToolResult(False, f"“{name}” can't be a shortcut name.")
        return ToolResult(True, f"Learned: say “{name}” any time.", data={"steps": len(recorded)})


class RoutineTool(BaseTool):
    name = "routines"
    description = "Schedule commands to run by themselves at a time of day."
    supported_actions = ["add", "list", "remove"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        p = params or {}
        if action == "add":
            r = routines.add(p["time"], list(p["days"]), p["command"])
            return ToolResult(True, f"Routine {r['id']}: {describe_when(r['days'], r['time'])} — {r['command']}.", data=r)
        if action == "list":
            if not routines.items:
                return ToolResult(True, "No routines. Try “every weekday at 8:30 open mail and play music”.")
            return ToolResult(
                True,
                "; ".join(f"{r['id']}. {describe_when(r['days'], r['time'])}: {r['command']}" for r in routines.items),
            )
        if action == "remove":
            gone = routines.remove(str(p.get("ref", "")))
            if not gone:
                return ToolResult(False, "I couldn't find that routine.")
            return ToolResult(True, f"Removed {len(gone)} routine(s).")
        return ToolResult(False, f"Unknown routines action '{action}'.")


class DictationTool(BaseTool):
    name = "dictation"
    description = "Personal dictionary and dictation stats."
    supported_actions = ["add_word", "add_replace", "remove", "list", "stats"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        p = params or {}
        d = dictation_mod.dictionary
        if action == "add_word":
            w = str(p.get("word", "")).strip()
            if not w:
                return ToolResult(False, "Which word?")
            added = d.add_word(w)
            events.emit("dictionary_changed", hints=d.hints())
            return ToolResult(True, f"Added “{w}” to your dictionary." if added else f"“{w}” is already in your dictionary.")
        if action == "add_replace":
            d.add_replace(str(p["heard"]), str(p["written"]))
            events.emit("dictionary_changed", hints=d.hints())
            return ToolResult(True, f"When you dictate “{p['heard']}”, I'll write “{p['written']}”.")
        if action == "remove":
            ok = d.remove(str(p.get("word", "")))
            events.emit("dictionary_changed", hints=d.hints())
            return ToolResult(ok, "Removed from your dictionary." if ok else "That isn't in your dictionary.")
        if action == "list":
            parts = d.words + [f"{k} → {v}" for k, v in d.replace.items()]
            return ToolResult(True, "Dictionary: " + ", ".join(parts) if parts else "Your dictionary is empty.")
        if action == "stats":
            s = dictation_mod.read_stats()
            return ToolResult(
                True,
                f"Dictated {s['today']} words today, {s['total']} in all ({s['sessions']} sessions) — "
                f"about {dictation_mod.minutes_saved(s['total'])} minutes saved.",
                data=s,
            )
        return ToolResult(False, f"Unknown dictation action '{action}'.")


class MeetingTool(BaseTool):
    name = "meeting"
    description = "Meeting copilot: live notes during a call, summary afterwards."
    supported_actions = ["start", "stop", "note", "last", "list"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        p = params or {}
        if action == "start":
            if meetings.active:
                return ToolResult(False, "A meeting is already being noted. Say “end meeting” first.")
            s = meetings.start(str(p.get("title", "")))
            events.emit("meeting_state", active=True, title=s.title)
            return ToolResult(True, f"Taking notes for “{s.title}”. Say “end meeting” when you're done.")
        if action == "stop":
            if not meetings.active:
                return ToolResult(False, "No meeting is being noted.")
            n = len(meetings.session.lines) if meetings.session else 0
            path = meetings.stop()
            events.emit("meeting_state", active=False, title="")
            return ToolResult(True, f"Saved {n} lines to {path.name if path else 'file'} in ~/.config/speed_x/meetings.", data={"path": str(path)})
        if action == "note":
            ok = meetings.add_note(str(p.get("text", "")))
            return ToolResult(ok, "Noted." if ok else "Start a meeting first.")
        if action == "last":
            text = meetings.last_summary()
            return ToolResult(bool(text), text or "No meetings saved yet.")
        if action == "list":
            files = meetings.list()
            return ToolResult(True, ", ".join(f.stem for f in files) if files else "No meetings saved yet.")
        return ToolResult(False, f"Unknown meeting action '{action}'.")


class UpdateTool(BaseTool):
    name = "update"
    description = "Check for and install Speed-X updates."
    supported_actions = ["check", "install"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        info = check_update()
        if not info["ok"]:
            return ToolResult(False, "Couldn't reach GitHub to check for updates.")
        if not info["newer"]:
            return ToolResult(True, f"Speed-X {info['current']} is up to date.", data=info)
        if action == "check":
            events.emit("update_available", version=info["latest"], page=info["page"])
            return ToolResult(True, f"Speed-X {info['latest']} is available (you have {info['current']}). Say “install the update”.", data=info)
        ok, msg = download_and_open(info)
        if not ok:
            subprocess.run(["open", info["page"]], check=False)
        return ToolResult(ok, msg, data=info)


class AgentTool(BaseTool):
    name = "agents"
    description = "Run commands in the background in their own windows."
    supported_actions = ["start", "list", "stop"]
    # Set by the server: callable(command, agent) that runs the command, filling agent.steps/status/message
    runner: Optional[Callable[[str, Any], None]] = None

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        p = params or {}
        if action == "start":
            if not self.runner:
                return ToolResult(False, "Background agents aren't available here.")
            try:
                a = agents.start(str(p.get("command", "")), self.runner)
            except RuntimeError as e:
                return ToolResult(False, str(e))
            return ToolResult(True, f"Agent {a.id} is working on “{a.command}” in the background.", data={"id": a.id})
        if action == "list":
            lst = agents.list()
            return ToolResult(True, "; ".join(f"{a.id}. {a.command} — {a.status}" for a in lst) if lst else "No agents running.")
        if action == "stop":
            stopped = agents.stop(str(p.get("ref", "")) or None)
            return ToolResult(bool(stopped), f"Stopped {len(stopped)} agent(s)." if stopped else "No matching agent is running.")
        return ToolResult(False, f"Unknown agents action '{action}'.")


class UITool(BaseTool):
    """Things only the app can do on screen; the engine asks, the app does it (see AppModel.swift)."""

    name = "ui"
    description = "Point at things on screen, draw on screen, wake word, permissions."
    supported_actions = ["show_where", "draw_start", "draw_stop", "draw_clear", "wake_on", "wake_off", "permissions"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        p = params or {}
        if action == "show_where":
            q = str(p.get("query", "")).strip()
            if not q:
                return ToolResult(False, "What should I point at?")
            events.emit("show_where", query=q)
            return ToolResult(True, f"Looking for “{q}” on screen…")
        msgs = {
            "draw_start": "Drawing is on — drag anywhere. Say “stop drawing” or press Esc to finish.",
            "draw_stop": "Drawing is off.",
            "draw_clear": "Cleared the drawing.",
            "wake_on": "Wake word is on. Say “Speed X” to talk.",
            "wake_off": "Wake word is off.",
            "permissions": "Opening the permissions check.",
        }
        if action not in msgs:
            return ToolResult(False, f"Unknown ui action '{action}'.")
        events.emit("ui", action=action)
        return ToolResult(True, msgs[action])


for _tool in (SkillsTool(), RoutineTool(), DictationTool(), MeetingTool(), UpdateTool(), AgentTool(), UITool()):
    registry.register(_tool)
