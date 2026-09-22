"""Workspace and routine activator for Laya OS."""

import subprocess
from typing import Any, Dict, Optional

from ..core.memory import memory
from .apps import normalize_app_name
from .base import BaseTool, ToolResult, registry


class WorkspaceTool(BaseTool):
    name = "workspaces"
    description = "Launch pre-configured sets of apps and setup routines (e.g. coding, research)."
    supported_actions = ["activate", "list"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        if action in ("activate", "start", "open"):
            name = params.get("workspace", "").strip().lower()
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
                subprocess.run(["open", "-a", norm_app], check=False)
                opened.append(norm_app)

            return ToolResult(
                success=True,
                message=f"Activated '{name}' workspace: launched {', '.join(opened)}.",
                data={"workspace": name, "apps": opened},
            )

        elif action == "list":
            workspaces = memory.list_workspaces()
            return ToolResult(
                success=True,
                message=f"Configured workspaces: {', '.join(workspaces)}",
                data={"workspaces": workspaces},
            )

        return ToolResult(success=False, message=f"Unknown workspace action: '{action}'.")


# Register tool
registry.register(WorkspaceTool())
