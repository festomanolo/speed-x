"""Native macOS application launcher, switcher, and manager."""

import difflib
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import BaseTool, ToolResult, registry

APP_ALIASES = {
    "safari": "Safari",
    "browser": "Safari",
    "the browser": "Safari",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "google": "Google Chrome",
    "firefox": "Firefox",
    "vscode": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "visual studio": "Visual Studio Code",
    "code": "Visual Studio Code",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "whatsapp": "WhatsApp",
    "whats app": "WhatsApp",
    "music": "Music",
    "apple music": "Music",
    "spotify": "Spotify",
    "notes": "Notes",
    "notes app": "Notes",
    "finder": "Finder",
    "files": "Finder",
    "calendar": "Calendar",
    "kalenda": "Calendar",
    "reminders": "Reminders",
    "calculator": "Calculator",
    "kikokotoo": "Calculator",
    "telegram": "Telegram",
    "mail": "Mail",
    "email": "Mail",
    "barua pepe": "Mail",
    "messages": "Messages",
    "ujumbe": "Messages",
    "photos": "Photos",
    "picha": "Photos",
    "settings": "System Settings",
    "system settings": "System Settings",
    "system preferences": "System Settings",
    "mipangilio": "System Settings",
    "app store": "App Store",
    "activity monitor": "Activity Monitor",
    "xcode": "Xcode",
    "preview": "Preview",
    "facetime": "FaceTime",
    "maps": "Maps",
    "ramani": "Maps",
    "slack": "Slack",
    "discord": "Discord",
    "zoom": "zoom.us",
}

_APP_DIRS = [
    Path("/Applications"),
    Path("/Applications/Utilities"),
    Path("/System/Applications"),
    Path("/System/Applications/Utilities"),
    Path.home() / "Applications",
]

_index: Dict[str, str] = {}
_index_time = 0.0


def installed_apps(refresh_after: float = 300.0) -> Dict[str, str]:
    """Map lower-cased app names to their display names (cached for 5 minutes)."""
    global _index, _index_time
    if _index and time.monotonic() - _index_time < refresh_after:
        return _index
    found: Dict[str, str] = {}
    for folder in _APP_DIRS:
        try:
            for entry in folder.iterdir():
                if entry.suffix == ".app":
                    found[entry.stem.lower()] = entry.stem
        except OSError:
            continue
    _index, _index_time = found, time.monotonic()
    return found


def app_installed(name: str) -> bool:
    return name.lower() in installed_apps()


def running_app_names() -> List[str]:
    """Names of regular (dock) apps currently running. Uses AppKit when available."""
    try:
        from AppKit import NSWorkspace

        return [
            str(a.localizedName())
            for a in NSWorkspace.sharedWorkspace().runningApplications()
            if a.activationPolicy() == 0 and a.localizedName()
        ]
    except Exception:
        res = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of every process whose background only is false'],
            capture_output=True,
            text=True,
        )
        return [a.strip() for a in res.stdout.split(",") if a.strip()]


def normalize_app_name(raw_name: str) -> str:
    cleaned = raw_name.strip().lower()
    return APP_ALIASES.get(cleaned, raw_name.strip())


def resolve_app(raw_name: str) -> Optional[str]:
    """Resolve a spoken app name ("vs code", "whats up", "calculater") to an installed app.

    Returns None when nothing installed is a plausible match.
    """
    cleaned = re.sub(r"\b(the|app|application|programu|ya)\b", " ", raw_name.lower())
    cleaned = re.sub(r"[^\w\s.]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None

    apps = installed_apps()
    alias = APP_ALIASES.get(cleaned) or APP_ALIASES.get(raw_name.strip().lower())
    if alias and alias.lower() in apps:
        return apps[alias.lower()]
    if cleaned in apps:
        return apps[cleaned]

    squashed = cleaned.replace(" ", "")
    for key, name in apps.items():
        if key.replace(" ", "") == squashed:
            return name

    # Prefix match ("visual studio" -> "Visual Studio Code")
    prefix = [name for key, name in apps.items() if key.startswith(cleaned) and len(cleaned) >= 3]
    if len(prefix) == 1:
        return prefix[0]

    close = difflib.get_close_matches(cleaned, list(apps.keys()), n=1, cutoff=0.78)
    if close:
        return apps[close[0]]
    close = difflib.get_close_matches(squashed, [k.replace(" ", "") for k in apps], n=1, cutoff=0.8)
    if close:
        for key, name in apps.items():
            if key.replace(" ", "") == close[0]:
                return name
    return alias


class AppTool(BaseTool):
    name = "apps"
    description = "Launch, switch, quit, and list macOS applications."
    supported_actions = ["open", "quit", "switch", "list_running"]

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        raw_app = params.get("app", "")
        app_name = (resolve_app(raw_app) or normalize_app_name(raw_app)) if raw_app else ""

        try:
            if action in ("open", "launch", "switch"):
                if not app_name:
                    return ToolResult(success=False, message="No application name specified.")
                if app_installed(app_name):
                    # Known app: don't block the reply on a cold launch (can take seconds).
                    subprocess.Popen(["open", "-a", app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return ToolResult(success=True, message=f"Opened {app_name}.", data={"app": app_name})
                res = subprocess.run(["open", "-a", app_name], capture_output=True, text=True)
                if res.returncode == 0:
                    return ToolResult(success=True, message=f"Opened {app_name}.", data={"app": app_name})
                return ToolResult(success=False, message=f"I couldn't find an app called '{raw_app}'.")

            elif action in ("quit", "close"):
                if not app_name:
                    return ToolResult(success=False, message="No application name specified.")
                if app_name not in running_app_names():
                    return ToolResult(success=True, message=f"{app_name} isn't running.", data={"app": app_name})
                self._run_applescript(f'tell application "{app_name}" to quit')
                return ToolResult(success=True, message=f"Quit {app_name}.", data={"app": app_name})

            elif action == "list_running":
                running_apps = running_app_names()
                return ToolResult(
                    success=True,
                    message=f"{len(running_apps)} apps running: {', '.join(running_apps[:8])}"
                    + ("…" if len(running_apps) > 8 else ""),
                    data={"running_apps": running_apps},
                )

            else:
                return ToolResult(success=False, message=f"Unknown app action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Application operation failed: {str(e)}")


# Register tool
registry.register(AppTool())
