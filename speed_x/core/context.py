"""Context awareness for macOS (active window, frontmost app, selection)."""

import subprocess
from dataclasses import dataclass
from typing import Optional

_SELF_NAMES = {"SpeedX", "Speed-X", "Python", "python3"}


@dataclass
class SystemContext:
    frontmost_app: str
    active_window_title: Optional[str] = None


class ContextEngine:
    """Reads real-time state from macOS to resolve contextual references ('this', 'current')."""

    def __init__(self):
        # The UI reports the app the user was in before summoning Speed-X, because by the
        # time a command arrives Speed-X itself is usually frontmost.
        self.front_app_hint: Optional[str] = None

    def get_frontmost_app(self) -> str:
        if self.front_app_hint and self.front_app_hint not in _SELF_NAMES:
            return self.front_app_hint
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            name = str(app.localizedName()) if app else ""
            if name and name not in _SELF_NAMES:
                return name
        except Exception:
            pass
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
                ["osascript", "-e", script], capture_output=True, text=True, check=True
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
