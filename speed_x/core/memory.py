"""User memory, preferences, and workspace definitions."""

import json
from typing import Any, Dict, List, Optional
from ..config import MEMORY_FILE

DEFAULT_CONFIG: Dict[str, Any] = {
    "preferences": {
        "music_player": "Spotify",
        "default_browser": "Safari",
        "confirm_sensitive": True,
        "language": "mixed",
    },
    "workspaces": {
        "coding": {
            "description": "Developer setup",
            "apps": ["Visual Studio Code", "Terminal"],
        },
        "research": {
            "description": "Research and reading setup",
            "apps": ["Safari", "Notes"],
        },
    },
    "history": [],
}


class MemoryManager:
    def __init__(self):
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if MEMORY_FILE.exists():
            try:
                return json.loads(MEMORY_FILE.read_text())
            except Exception:
                pass
        return DEFAULT_CONFIG.copy()

    def save(self):
        MEMORY_FILE.write_text(json.dumps(self._data, indent=2))

    def get_preference(self, key: str, default: Any = None) -> Any:
        return self._data.get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any):
        if "preferences" not in self._data:
            self._data["preferences"] = {}
        self._data["preferences"][key] = value
        self.save()

    def get_workspace(self, name: str) -> Optional[Dict[str, Any]]:
        return self._data.get("workspaces", {}).get(name)

    def list_workspaces(self) -> List[str]:
        return list(self._data.get("workspaces", {}).keys())

    def log_command(self, command: str, domain: str, action: str, success: bool):
        entry = {
            "command": command,
            "domain": domain,
            "action": action,
            "success": success,
        }
        history = self._data.setdefault("history", [])
        history.append(entry)
        # Keep last 50 commands
        self._data["history"] = history[-50:]
        self.save()


memory = MemoryManager()
