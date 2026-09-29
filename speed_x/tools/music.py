"""Native macOS music player controller (Spotify & Apple Music)."""

import subprocess
import urllib.parse
from typing import Any, Dict, Optional

from ..core.memory import memory
from . import spotify_api
from .apps import app_installed, running_app_names
from .base import BaseTool, ToolResult, registry


class MusicTool(BaseTool):
    name = "music"
    description = "Control media playback on Spotify and Apple Music."
    supported_actions = [
        "play",
        "play_song",
        "pause",
        "play_pause",
        "next",
        "previous",
        "get_current_track",
    ]


    @staticmethod
    def _quote(text: str) -> str:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _play_from_music_library(self, query: str, artist: str) -> str:
        """Play the best match from the Apple Music library; returns "name by artist" or ""."""
        q, a = self._quote(query), self._quote(artist)
        search = f"{query} {artist}".strip()
        script = (
            'tell application "Music"\n'
            f"   set hits to search library playlist 1 for {q} only names\n"
            f'   if {a} is not "" then\n'
            "       repeat with t in hits\n"
            f"           if artist of t contains {a} then\n"
            "               play t\n"
            '               return (name of t) & " by " & (artist of t)\n'
            "           end if\n"
            "       end repeat\n"
            f"       set hits to search library playlist 1 for {self._quote(search)}\n"
            "   end if\n"
            # Nothing by title: the query may be an artist or album ("play mbosso").
            f"   if hits is {{}} then set hits to search library playlist 1 for {q}\n"
            '   if hits is {} then return ""\n'
            "   set t to item 1 of hits\n"
            "   play t\n"
            '   return (name of t) & " by " & (artist of t)\n'
            "end tell"
        )
        return self._run_applescript(script, timeout=15.0).strip()

    def _play_song(self, player: str, query: str, artist: str) -> ToolResult:
        wanted = f"{query} by {artist}" if artist else query
        term = f"{query} {artist}".strip()
        if player == "Music":
            found = self._play_from_music_library(query, artist)
            if found:
                return ToolResult(success=True, message=f"Playing {found}.", data={"track": found})
            url = "music://music.apple.com/search?term=" + urllib.parse.quote(term)
            subprocess.run(["open", url], check=False)
            return ToolResult(
                success=True,
                message=f"“{wanted}” isn't in your library, so I opened it in Apple Music search. Pick it there to play.",
                data={"track": None},
            )
        # Spotify's AppleScript can only play URIs: resolve the song to one via the Web API.
        track = spotify_api.find_track(query, artist)
        if track:
            self._run_applescript(f'tell application "Spotify" to play track {self._quote(track["uri"])}')
            found = f"{track['name']} by {track['artist']}"
            return ToolResult(success=True, message=f"Playing {found} on Spotify.", data={"track": found})
        subprocess.run(["open", "spotify:search:" + urllib.parse.quote(term)], check=False)
        hint = "" if spotify_api.credentials() else " (add Spotify API keys to play songs directly — see README)"
        return ToolResult(success=True, message=f"Opened Spotify search for “{wanted}”{hint}.", data={"track": None})

    def _detect_active_player(self) -> str:
        """Pick the running player (Spotify first), without spawning processes."""
        running = running_app_names()
        if "Spotify" in running:
            return "Spotify"
        if "Music" in running:
            return "Music"
        preferred = memory.get_preference("music_player", "Music")
        return preferred if preferred in ("Spotify", "Music") and app_installed(preferred) else "Music"

    def execute(self, action: str, params: Optional[Dict[str, Any]] = None) -> ToolResult:
        params = params or {}
        player = params.get("player") or self._detect_active_player()

        try:
            if action in ("play_pause", "toggle"):
                self._run_applescript(f'tell application "{player}" to playpause')
                return ToolResult(success=True, message=f"Toggled playback on {player}.")

            elif action == "play_song":
                query = str(params.get("query") or "").strip()
                if not query:
                    self._run_applescript(f'tell application "{player}" to play')
                    return ToolResult(success=True, message=f"Playing on {player}.")
                return self._play_song(player, query, str(params.get("artist") or "").strip())

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
                if player not in running_app_names():
                    return ToolResult(success=True, message="Nothing is playing right now.", data={"track": None})
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
