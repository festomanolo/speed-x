"""Workspace and routine activator for Laya OS."""

import re
import subprocess
from typing import Any, Dict, List, Optional

from ..core.memory import memory
from .apps import normalize_app_name, resolve_app, running_app_names
from .base import BaseTool, ToolResult, registry

# Running apps that are never part of a saved setup.
_NOT_A_WORKSPACE_APP = {"Finder", "SpeedX", "Speed-X", "Python", "python3"}


def _app_list(raw: Any) -> List[str]:
    """Accept ["Safari", "Notes"] or "safari, notes and pages" and resolve each to an installed app name."""
    if isinstance(raw, str):
        raw = [p for p in re.split(r"\s*(?:,|\band\b|\bna\b|&|\bplus\b)\s*", raw) if p.strip()]
    apps = []
    for item in raw or []:
        name = resolve_app(normalize_app_name(str(item))) or normalize_app_name(str(item))
        if name and name not in apps:
            apps.append(name)
    return apps


class WorkspaceTool(BaseTool):
    name = "workspaces"
    description = "Launch, create and edit named sets of apps (e.g. coding, research)."
    supported_actions = ["activate", "list", "create", "save_current", "add", "delete"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        name = str(params.get("workspace", "")).strip().lower()

        if action in ("activate", "start", "open"):
            ws = memory.get_workspace(name)
            if not ws:
                available = ", ".join(memory.list_workspaces())
                return ToolResult(
                    success=False,
                    message=f"Workspace '{name}' not found. Available: {available}",
                )

            opened = []
            for app in ws.get("apps", []):
                norm_app = normalize_app_name(app)
                subprocess.Popen(
                    ["open", "-a", norm_app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                opened.append(norm_app)

            return ToolResult(
                success=True,
                message=f"Activated '{name}' workspace: launched {', '.join(opened)}.",
                data={"workspace": name, "apps": opened},
            )

        elif action == "list":
            workspaces = memory.list_workspaces()
            details = [
                f"{w} ({', '.join(memory.get_workspace(w).get('apps', []))})" for w in workspaces
            ]
            return ToolResult(
                success=True,
                message=f"Configured workspaces: {'; '.join(details)}"
                if details
                else "No workspaces yet.",
                data={"workspaces": workspaces},
            )

        if not name:
            return ToolResult(success=False, message="What should the workspace be called?")

        if action == "create":
            apps = _app_list(params.get("apps"))
            if not apps:
                return ToolResult(
                    success=False, message=f"Which apps should the '{name}' workspace open?"
                )
            memory.save_workspace(name, apps)
            return ToolResult(
                success=True,
                message=f"Saved '{name}' workspace: {', '.join(apps)}. Say “start {name} workspace” to open it.",
                data={"workspace": name, "apps": apps},
            )

        if action == "save_current":
            apps = [a for a in running_app_names() if a not in _NOT_A_WORKSPACE_APP]
            if not apps:
                return ToolResult(success=False, message="No apps are open to save.")
            memory.save_workspace(name, apps)
            return ToolResult(
                success=True,
                message=f"Saved your open apps as '{name}': {', '.join(apps)}.",
                data={"workspace": name, "apps": apps},
            )

        if action == "add":
            ws = memory.get_workspace(name)
            if not ws:
                return ToolResult(success=False, message=f"There's no '{name}' workspace yet.")
            apps = list(ws.get("apps", []))
            added = [a for a in _app_list(params.get("apps")) if a not in apps]
            if not added:
                return ToolResult(success=False, message=f"Those apps are already in '{name}'.")
            memory.save_workspace(name, apps + added, ws.get("description", ""))
            return ToolResult(
                success=True,
                message=f"Added {', '.join(added)} to '{name}'.",
                data={"workspace": name, "apps": apps + added},
            )

        if action == "delete":
            if memory.delete_workspace(name):
                return ToolResult(success=True, message=f"Deleted the '{name}' workspace.")
            return ToolResult(success=False, message=f"There's no '{name}' workspace.")

        return ToolResult(success=False, message=f"Unknown workspace action: '{action}'.")


# Register tool
registry.register(WorkspaceTool())
