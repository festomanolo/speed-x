"""Context awareness for macOS (active window, frontmost app, selection)."""

import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class SystemContext:
    frontmost_app: str
    active_window_title: Optional[str] = None


class ContextEngine:
    """Reads real-time state from macOS to resolve contextual references ('this', 'current')."""

    @staticmethod
    def get_frontmost_app() -> str:
        script = (
            'tell application "System Events"\n'
            '    return name of first application process whose frontmost is true\n'
            "end tell"
        )
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True,
            )
            return res.stdout.strip()
        except Exception:
            return "Finder"

    @staticmethod
    def get_active_window_title() -> Optional[str]:
        script = (
            'tell application "System Events"\n'
            "    set frontApp to first application process whose frontmost is true\n"
            "    try\n"
            "        return name of front window of frontApp\n"
            "    on error\n"
            '        return ""\n'
            "    end try\n"
            "end tell"
        )
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True,
            )
            val = res.stdout.strip()
            return val if val else None
        except Exception:
            return None

    def get_current_context(self) -> SystemContext:
        return SystemContext(
            frontmost_app=self.get_frontmost_app(),
            active_window_title=self.get_active_window_title(),
        )


context_engine = ContextEngine()
