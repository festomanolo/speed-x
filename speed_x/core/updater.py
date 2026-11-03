"""Self-updater: check GitHub releases, download the DMG, open it.

Speed-X is not notarised, so macOS wants a human to drag the app into Applications; this
does everything up to that point (check, download with a size check, mount) and tells the
UI when a newer version exists. The network is only touched when you ask or on the daily
background check (SPEEDX_UPDATE_CHECK=0 turns that off).
"""

import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .. import __version__

REPO = os.getenv("SPEEDX_REPO", "festomanolo/speed-x")
API = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOADS = Path.home() / "Downloads"


def parse_version(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _fetch(url: str, timeout: float = 6.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SpeedX-updater", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https GitHub URL
        return r.read()


def check(fetch=_fetch) -> Dict[str, Any]:
    """-> {'ok', 'current', 'latest', 'newer', 'dmg_url', 'dmg_size', 'notes', 'page'} (never raises)."""
    out: Dict[str, Any] = {"ok": False, "current": __version__, "newer": False}
    try:
        rel = json.loads(fetch(API))
    except Exception as e:
        out["error"] = str(e)
        return out
    latest = str(rel.get("tag_name", "")).lstrip("v")
    asset = next((a for a in rel.get("assets", []) if str(a.get("name", "")).lower().endswith(".dmg")), None)
    out.update(
        ok=bool(latest),
        latest=latest,
        newer=bool(latest) and is_newer(latest),
        page=rel.get("html_url", f"https://github.com/{REPO}/releases"),
        notes=str(rel.get("body", ""))[:600],
        dmg_url=asset.get("browser_download_url") if asset else None,
        dmg_size=asset.get("size") if asset else None,
    )
    return out


def download_and_open(info: Dict[str, Any], dest: Path = DOWNLOADS, fetch=_fetch, opener=None) -> Tuple[bool, str]:
    url = info.get("dmg_url")
    if not url or not url.startswith("https://"):
        return False, "This release has no DMG attached — opening the release page instead."
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"SpeedX-{info.get('latest', 'latest')}.dmg"
    try:
        data = fetch(url, 120.0) if fetch is not _fetch else _fetch(url, 120.0)
    except Exception as e:
        return False, f"Download failed: {e}"
    if info.get("dmg_size") and len(data) != int(info["dmg_size"]):
        return False, "The download was incomplete, so I didn't open it. Try again."
    path.write_bytes(data)
    (opener or (lambda p: subprocess.run(["open", str(p)], check=False)))(path)
    return True, f"Downloaded {path.name} and opened it — drag Speed-X into Applications to finish."
