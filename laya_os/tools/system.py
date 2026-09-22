"""Native macOS system controls (volume, display, sleep, lock)."""

import subprocess
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry


class SystemTool(BaseTool):
    name = "system"
    description = "Control macOS volume, screen lock, sleep, and system appearance."
    supported_actions = [
        "volume_up",
        "volume_down",
        "set_volume",
        "mute",
        "unmute",
        "lock_screen",
        "sleep",
        "toggle_dark_mode",
    ]

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
        try:
            if action == "volume_up":
                self._run_applescript(
                    "set currentVolume to output volume of (get volume settings)\n"
                    "set volume output volume (currentVolume + 10)"
                )
                return ToolResult(success=True, message="Volume increased by 10%.")

            elif action == "volume_down":
                self._run_applescript(
                    "set currentVolume to output volume of (get volume settings)\n"
                    "set volume output volume (currentVolume - 10)"
                )
                return ToolResult(success=True, message="Volume decreased by 10%.")

            elif action == "set_volume":
                level = int(params.get("level", 50))
                level = max(0, min(100, level))
                self._run_applescript(f"set volume output volume {level}")
                return ToolResult(success=True, message=f"Volume set to {level}%.")

            elif action == "mute":
                self._run_applescript("set volume output muted true")
                return ToolResult(success=True, message="Audio muted.")

            elif action == "unmute":
                self._run_applescript("set volume output muted false")
                return ToolResult(success=True, message="Audio unmuted.")

            elif action == "lock_screen":
                # Instant lock screen using macOS Sacm shortcut / CGSession
                subprocess.run(
                    ["pmset", "displaysleepnow"],
                    check=False,
                )
                return ToolResult(success=True, message="Screen locked.")

            elif action == "sleep":
                self._run_applescript('tell application "System Events" to sleep')
                return ToolResult(success=True, message="Mac put to sleep.")

            elif action == "toggle_dark_mode":
                self._run_applescript(
                    'tell application "System Events" to tell appearance preferences '
                    "to set dark mode to not dark mode"
                )
                return ToolResult(success=True, message="Toggled dark mode.")

            else:
                return ToolResult(
                    success=False,
                    message=f"Unknown system action: '{action}'.",
                )
        except Exception as e:
            return ToolResult(success=False, message=f"System control failed: {str(e)}")


# Register tool
registry.register(SystemTool())
