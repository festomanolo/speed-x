"""Native macOS application launcher, switcher, and manager."""

import subprocess
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, registry

APP_ALIASES = {
    "safari": "Safari",
    "browser": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "whatsapp": "WhatsApp",
    "music": "Music",
    "apple music": "Music",
    "spotify": "Spotify",
    "notes": "Notes",
    "finder": "Finder",
    "calendar": "Calendar",
    "reminders": "Reminders",
    "calculator": "Calculator",
    "telegram": "Telegram",
}


def normalize_app_name(raw_name: str) -> str:
    cleaned = raw_name.strip().lower()
    return APP_ALIASES.get(cleaned, raw_name.strip())


class AppTool(BaseTool):
    name = "apps"
    description = "Launch, switch, quit, and list macOS applications."
    supported_actions = ["open", "quit", "switch", "list_running"]

    def _run_applescript(self, script: str) -> str:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        raw_app = params.get("app", "")
        app_name = normalize_app_name(raw_app) if raw_app else ""

        try:
            if action in ("open", "launch", "switch"):
                if not app_name:
                    return ToolResult(success=False, message="No application name specified.")
                # open -a is reliable across all macOS versions
                res = subprocess.run(
                    ["open", "-a", app_name],
                    capture_output=True,
                    text=True,
                )
                if res.returncode == 0:
                    return ToolResult(
                        success=True,
                        message=f"Opened {app_name}.",
                        data={"app": app_name},
                    )
                else:
                    return ToolResult(
                        success=False,
                        message=f"Could not open '{app_name}': {res.stderr.strip()}",
                    )

            elif action in ("quit", "close"):
                if not app_name:
                    return ToolResult(success=False, message="No application name specified.")
                self._run_applescript(f'tell application "{app_name}" to quit')
                return ToolResult(
                    success=True,
                    message=f"Quit {app_name}.",
                    data={"app": app_name},
                )

            elif action == "list_running":
                script = (
                    'tell application "System Events" to get name of every process '
                    "whose background only is false"
                )
                output = self._run_applescript(script)
                running_apps = [a.strip() for a in output.split(",") if a.strip()]
                return ToolResult(
                    success=True,
                    message=f"{len(running_apps)} applications currently running.",
                    data={"running_apps": running_apps},
                )

            else:
                return ToolResult(success=False, message=f"Unknown app action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Application operation failed: {str(e)}")


# Register tool
registry.register(AppTool())
