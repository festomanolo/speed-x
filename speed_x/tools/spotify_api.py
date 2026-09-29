"""Minimal Spotify Web API client: finds a track's URI so the desktop app can play it.

Spotify's AppleScript can play a `spotify:track:<id>` URI but cannot search, so we look the
track up with the Client Credentials flow (an app key; no user login, no Premium needed).

Credentials: SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET, or ~/.config/speed_x/spotify.json
({"client_id": "...", "client_secret": "..."}). Create them at https://developer.spotify.com/dashboard.
"""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional, Tuple

from ..config import USER_CONFIG_DIR

CREDENTIALS_FILE = USER_CONFIG_DIR / "spotify.json"
TIMEOUT_S = 6.0

_lock = threading.Lock()
_token: Tuple[str, float] = ("", 0.0)  # (access token, expiry)


def credentials() -> Optional[Tuple[str, str]]:
    cid, secret = os.getenv("SPOTIFY_CLIENT_ID", ""), os.getenv("SPOTIFY_CLIENT_SECRET", "")
    if not (cid and secret):
        try:
            data = json.loads(CREDENTIALS_FILE.read_text())
            cid, secret = data.get("client_id", ""), data.get("client_secret", "")
        except (OSError, ValueError):
            return None
    return (cid, secret) if cid and secret else None


def _access_token(creds: Tuple[str, str]) -> str:
    global _token
    with _lock:
        if _token[0] and time.time() < _token[1] - 60:
            return _token[0]
        basic = base64.b64encode(f"{creds[0]}:{creds[1]}".encode()).decode()
        req = urllib.request.Request(
            "https://accounts.spotify.com/api/token",
            data=b"grant_type=client_credentials",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
            body = json.load(res)
        _token = (body["access_token"], time.time() + float(body.get("expires_in", 3600)))
        return _token[0]


def find_track(query: str, artist: str = "") -> Optional[Dict[str, str]]:
    """Best matching track as {"uri", "name", "artist"}, or None (no credentials, no match, offline)."""
    creds = credentials()
    if not creds:
        return None
    q = f"track:{query} artist:{artist}" if artist else query
    url = "https://api.spotify.com/v1/search?" + urllib.parse.urlencode(
        {"q": q, "type": "track", "limit": 1}
    )
    try:
        req = urllib.request.Request(
            url, headers={"Authorization": f"Bearer {_access_token(creds)}"}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
            items = json.load(res).get("tracks", {}).get("items", [])
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None
    if not items:
        return find_track(f"{query} {artist}") if artist else None
    track = items[0]
    return {
        "uri": track["uri"],
        "name": track.get("name", query),
        "artist": ", ".join(a.get("name", "") for a in track.get("artists", [])),
    }
