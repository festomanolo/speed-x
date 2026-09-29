"""Fast AppleScript execution.

Spawning `osascript` costs ~0.5-1s per call on Intel Macs. Inside the warm
Speed-X daemon we instead compile scripts once with NSAppleScript (PyObjC) and
execute them in-process (~3ms). Off the main thread, or without PyObjC, we fall
back to the `osascript` subprocess.
"""

import subprocess
import threading
from typing import Callable, Dict, Optional

try:
    from Foundation import NSAppleScript

    _HAS_OBJC = True
except Exception:  # pragma: no cover - PyObjC missing
    NSAppleScript = None
    _HAS_OBJC = False

_cache: Dict[str, object] = {}
_lock = threading.Lock()

# When running under the Speed-X app, scripts are executed by the app itself so macOS
# attributes Automation permissions to "SpeedX" (one prompt per target app, remembered)
# rather than to the Python interpreter. Set by speed_x.server.
_remote_runner: Optional[Callable[[str, float], str]] = None


def set_remote_runner(runner: Optional[Callable[[str, float], str]]):
    global _remote_runner
    _remote_runner = runner


class AppleScriptError(RuntimeError):
    pass


def _run_subprocess(script: str, timeout: float) -> str:
    res = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if res.returncode != 0:
        raise AppleScriptError(res.stderr.strip() or "AppleScript failed")
    return res.stdout.strip()


def run_applescript(script: str, timeout: float = 8.0) -> str:
    """Run AppleScript and return its string result; raises AppleScriptError on failure."""
    if _remote_runner is not None:
        return _remote_runner(script, timeout)
    if not _HAS_OBJC or threading.current_thread() is not threading.main_thread():
        return _run_subprocess(script, timeout)

    with _lock:
        compiled = _cache.get(script)
        if compiled is None:
            compiled = NSAppleScript.alloc().initWithSource_(script)
            if len(_cache) < 256:
                _cache[script] = compiled
        result, error = compiled.executeAndReturnError_(None)
    if error is not None:
        message = error.get("NSAppleScriptErrorMessage") or str(error)
        raise AppleScriptError(str(message))
    if result is None:
        return ""
    value = result.stringValue()
    return (value or "").strip()


def warm_up():
    """Initialise the AppleScript component so the first real command is instant."""
    try:
        run_applescript("return 1")
    except Exception:
        pass


def escape(text: str) -> str:
    """Escape a Python string for embedding inside an AppleScript string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"')
