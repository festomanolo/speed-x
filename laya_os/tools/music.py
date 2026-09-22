"""Native macOS music player controller (Spotify & Apple Music)."""

import subprocess
from typing import Any, Dict, Optional

from .base import BaseTool, ToolResult, registry


class MusicTool(BaseTool):
    name = "music"
    description = "Control media playback on Spotify and Apple Music."
    supported_actions = [
        "play",
        "pause",
        "play_pause",
        "next",
        "previous",
        "get_current_track",
    ]

    def _run_applescript(self, script: str) -> str:
        res = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()

    def _detect_active_player(self) -> str:
        """Check if Spotify or Music.app is currently running."""
        check_script = (
            'tell application "System Events"\n'
            '   set spotifyRunning to (name of processes) contains "Spotify"\n'
            '   set musicRunning to (name of processes) contains "Music"\n'
            '   if spotifyRunning then return "Spotify"\n'
            '   if musicRunning then return "Music"\n'
            '   return "Music"\n'
            "end tell"
        )
        try:
            return self._run_applescript(check_script)
        except Exception:
            return "Music"

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        player = params.get("player") or self._detect_active_player()

        try:
            if action in ("play_pause", "toggle"):
                self._run_applescript(f'tell application "{player}" to playpause')
                return ToolResult(success=True, message=f"Toggled playback on {player}.")

            elif action == "play":
                self._run_applescript(f'tell application "{player}" to play')
                return ToolResult(success=True, message=f"Playing on {player}.")

            elif action in ("pause", "stop"):
                self._run_applescript(f'tell application "{player}" to pause')
                return ToolResult(success=True, message=f"Paused {player}.")

            elif action in ("next", "skip"):
                self._run_applescript(f'tell application "{player}" to next track')
                return ToolResult(success=True, message=f"Skipped to next track on {player}.")

            elif action in ("previous", "prev", "back"):
                self._run_applescript(f'tell application "{player}" to previous track')
                return ToolResult(success=True, message=f"Went back to previous track on {player}.")

            elif action == "get_current_track":
                if player == "Spotify":
                    script = (
                        'tell application "Spotify"\n'
                        '   if player state is playing then\n'
                        '       return (name of current track) & " by " & (artist of current track)\n'
                        "   else\n"
                        '       return "Paused"\n'
                        "   end if\n"
                        "end tell"
                    )
                else:
                    script = (
                        'tell application "Music"\n'
                        '   if player state is playing then\n'
                        '       return (name of current track) & " by " & (artist of current track)\n'
                        "   else\n"
                        '       return "Paused"\n'
                        "   end if\n"
                        "end tell"
                    )
                info = self._run_applescript(script)
                return ToolResult(success=True, message=f"Now playing: {info}", data={"track": info})

            else:
                return ToolResult(success=False, message=f"Unknown music action: '{action}'.")

        except Exception as e:
            return ToolResult(success=False, message=f"Music control failed: {str(e)}")


# Register tool
registry.register(MusicTool())
