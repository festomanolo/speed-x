"""Central Command Router connecting LayaBrain, Guardrails, Memory, and Tools."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import re

from ..tools.base import ToolResult, registry
from . import events
from .brain import IntentDecision, LayaBrain
from .guardrails import guardrails
from .memory import memory


@dataclass
class StepResult:
    decision: IntentDecision
    success: bool
    message: str
    data: Optional[Any] = None


@dataclass
class ExecutionResponse:
    success: bool
    message: str
    decision: IntentDecision
    needs_confirmation: bool = False
    confirmation_prompt: str = ""
    data: Optional[Dict[str, Any]] = None
    steps: List[StepResult] = field(default_factory=list)
    suggestion: Optional[str] = None


# Human-readable labels for previews and the UI decision chip
ACTION_LABELS = {
    ("music", "play"): "Play music",
    ("music", "play_song"): "Play song",
    ("music", "pause"): "Pause music",
    ("music", "next"): "Next track",
    ("music", "previous"): "Previous track",
    ("music", "get_current_track"): "Now playing",
    ("music", "play_pause"): "Play / pause",
    ("system", "volume_up"): "Volume up",
    ("system", "volume_down"): "Volume down",
    ("system", "set_volume"): "Set volume",
    ("system", "mute"): "Mute",
    ("system", "unmute"): "Unmute",
    ("system", "lock_screen"): "Lock screen",
    ("system", "sleep"): "Sleep Mac",
    ("system", "toggle_dark_mode"): "Appearance",
    ("apps", "open"): "Open app",
    ("apps", "quit"): "Quit app",
    ("apps", "list_running"): "Running apps",
    ("apps", "switch"): "Switch to app",
    ("files", "open_file"): "Open file",
    ("files", "make_file"): "New file",
    ("clipboard", "write"): "Copy to clipboard",
    ("clipboard", "clear"): "Clear clipboard",
    ("mail", "compose"): "Draft email",
    ("screen", "ocr"): "Read screen",
    ("screen", "active_window"): "Active window",
    ("workspaces", "create"): "New workspace",
    ("workspaces", "save_current"): "Save workspace",
    ("workspaces", "add"): "Add to workspace",
    ("workspaces", "delete"): "Delete workspace",
    ("files", "search"): "Find file",
    ("files", "find_pdf"): "Find PDF",
    ("files", "create"): "New file",
    ("files", "latest_screenshot"): "Latest screenshot",
    ("clipboard", "read"): "Read clipboard",
    ("clipboard", "inspect"): "Inspect clipboard",
    ("screen", "capture"): "Screenshot",
    ("screen", "read"): "Read screen",
    ("notes", "create"): "New note",
    ("notes", "update"): "Update note",
    ("notes", "open"): "Open Notes",
    ("mail", "send"): "Compose email",
    ("mail", "open"): "Open Mail",
    ("workspaces", "activate"): "Workspace",
    ("workspaces", "list"): "Workspaces",
    ("web", "search"): "Web search",
    ("web", "youtube"): "YouTube search",
    ("web", "open_url"): "Open website",
    ("messaging", "send"): "Message",
    ("assistant", "answer"): "Answer",
    ("assistant", "think"): "Think it through",
    ("assistant", "ask"): "Answer",
    ("timer", "set"): "Timer",
    ("timer", "remind"): "Reminder",
    ("timer", "list"): "Timers",
    ("timer", "cancel"): "Cancel timers",
    ("timer", "time"): "Time",
    ("timer", "date"): "Date",
}


def describe(decision: IntentDecision) -> str:
    """Short label such as "Open app · Safari" or "Timer · 10 min"."""
    label = ACTION_LABELS.get((decision.domain, decision.action), f"{decision.domain}.{decision.action}")
    p = decision.params
    detail = ""
    if decision.domain == "messaging":
        who = p.get("contact") or p.get("to", "?")
        via = f" on {p['app']}" if p.get("app") else ""
        return f"{label} · {who}{via}" + (f" · “{p['text']}”" if p.get("text") else "")
    if "app" in p:
        detail = p["app"]
    elif "level" in p:
        detail = f"{p['level']}%"
    elif decision.action == "set" and "seconds" in p:
        mins, secs = divmod(int(p["seconds"]), 60)
        detail = f"{mins} min" + (f" {secs}s" if secs else "") if mins else f"{secs}s"
    elif "query" in p and p["query"]:
        detail = f"“{p['query']}”"
    elif "workspace" in p:
        detail = p["workspace"]
    elif decision.action == "remind":
        detail = p.get("text", "")
    elif "site" in p:
        detail = p["site"]
    elif "mode" in p:
        detail = p["mode"]
    return f"{label} · {detail}" if detail else label


def _observation(result: "StepResult") -> str:
    text = f"[{describe(result.decision)}] {result.message}"
    data = result.data if isinstance(result.data, dict) else {}
    for key in ("text", "content", "matches", "running_apps", "track"):
        if data.get(key):
            value = data[key]
            text += "\n" + ("\n".join(map(str, value)) if isinstance(value, list) else str(value))
    return text


class CommandRouter:
    """Orchestrates natural language intent recognition, safety checks, and execution."""

    def __init__(self, brain: Optional[LayaBrain] = None):
        self.brain = brain or LayaBrain()

    def _assistant_step(self, d: IntentDecision, previous: List[StepResult]) -> ToolResult:
        from . import ai
        from .llm import CHAT_PROMPT, THINK_PROMPT

        def push(text: str):
            events.emit("stream", text=text)

        if d.action == "answer":
            return ToolResult(success=True, message=d.params.get("text", ""))
        if d.action == "ask":
            reply = ai.stream(CHAT_PROMPT, d.params.get("question", d.text), on_delta=push)
            if not reply:
                return ToolResult(success=False, message="No AI brain is available — open Ollama.app (or add a Claude API key), then ask again.")
            return ToolResult(success=True, message=reply)
        if d.action in ("think", "synthesize"):
            content = "\n\n".join(_observation(r) for r in previous) or "(nothing was captured)"
            request = d.params.get("request", d.text)
            reply = ai.stream(THINK_PROMPT, f"Request: {request}\n\nContent:\n{content[:6000]}", on_delta=push)
            if not reply:
                return ToolResult(success=False, message="No AI brain is available — open Ollama.app (or add a Claude API key), then ask again.")
            if re.search(r"\b(copy|nakili|clipboard)\b", request, re.IGNORECASE) and not re.search(r"\bmy clipboard\b", request, re.IGNORECASE):
                registry.dispatch("clipboard", "write", {"text": reply})
            return ToolResult(success=True, message=reply)
        return ToolResult(success=False, message=f"Unknown assistant action '{d.action}'.")

    def preview(self, prompt: str) -> List[IntentDecision]:
        """Decide without executing or touching session context (for live transcripts)."""
        if not prompt.strip():
            return []
        return self.brain.plan(prompt, commit=False, allow_llm=False)

    def process(self, prompt: str, confirmed: bool = False) -> ExecutionResponse:
        prompt = prompt.strip()
        if not prompt:
            return ExecutionResponse(
                success=False,
                message="Empty command provided.",
                decision=IntentDecision("general", "none", {}, 0.0, False, "none"),
            )

        # 1. Plan (one or more typed decisions)
        steps = self.brain.plan(prompt, commit=False)  # context is committed below, once
        first = steps[0]

        # 2. Nothing actionable: offer the closest known command instead of a dead end
        if len(steps) == 1 and (first.domain == "general" or first.action == "unhandled"):
            suggestion = first.alternatives[0]["suggestion"] if first.alternatives else None
            if suggestion:
                message = f"Not sure what you meant — did you mean “{suggestion}”?"
            else:
                message = f"I didn't catch an action in “{first.text or prompt}”. Try music, volume, apps, files, notes, timers or web search."
            return ExecutionResponse(success=False, message=message, decision=first, suggestion=suggestion)

        # 3. Let tools resolve details up front (e.g. "manolo" -> the real contact), so the
        #    confirmation names the actual recipient and impossible steps fail early.
        for d in steps:
            tool = registry.get(d.domain) if d.handled else None
            prepare = getattr(tool, "prepare", None)
            if prepare:
                problem = prepare(d.action, d.params)
                if problem:
                    return ExecutionResponse(success=False, message=problem, decision=d, steps=[StepResult(d, False, problem)])

        # 4. Guardrails across the whole plan
        if not confirmed:
            reasons = []
            for d in steps:
                sensitive, reason = guardrails.requires_confirmation(d.domain, d.action)
                if sensitive or d.requires_confirmation:
                    reasons.append(f"{reason or describe(d)}" + (f" ({d.params['app']})" if "app" in d.params and reason else ""))
            if reasons:
                prompt_msg = f"Confirm: {', '.join(reasons)}?"
                return ExecutionResponse(
                    success=False,
                    message=prompt_msg,
                    decision=first,
                    needs_confirmation=True,
                    confirmation_prompt=prompt_msg,
                    steps=[StepResult(d, False, describe(d)) for d in steps],
                )
        # Commit session context ("close it" -> the app we just opened)
        for d in steps:
            if d.domain == "apps" and d.action == "open":
                self.brain.last_app = d.params.get("app")

        # 5. Execute steps in order
        results: List[StepResult] = []
        for d in steps:
            if not d.handled:
                results.append(StepResult(d, False, f"I don't know how to “{d.text}” yet."))
                continue
            if d.domain == "assistant":
                tool_result = self._assistant_step(d, results)
            else:
                tool_result = registry.dispatch(d.domain, d.action, d.params)
            results.append(StepResult(d, tool_result.success, tool_result.message, tool_result.data))
            if not tool_result.success and len(steps) > 1:
                break  # don't run later steps on top of a failed one

        # 5. Persistent memory
        memory.log_command(
            command=prompt,
            domain="+".join(r.decision.domain for r in results),
            action="+".join(r.decision.action for r in results),
            success=all(r.success for r in results),
        )

        success = all(r.success for r in results) and len(results) == len(steps)
        final = [r for r in results if r.decision.domain == "assistant"]
        if final:
            message = final[-1].message  # the answer is what the user wants to read
        else:
            message = results[0].message if len(results) == 1 else " ".join(r.message for r in results)
        try:
            from . import ai

            ai.remember(prompt, message)
        except Exception:
            pass
        return ExecutionResponse(
            success=success,
            message=message,
            decision=first,
            data=results[0].data if len(results) == 1 else {"steps": [r.data for r in results]},
            steps=results,
        )
