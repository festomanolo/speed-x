"""Speed-X engine daemon.

A long-lived process the macOS UI talks to over stdin/stdout, one JSON object
per line. Keeping it warm removes ~1.5s of interpreter start-up and imports
from every command, and lets AppleScript run in-process (see core.osa).

Requests  (UI -> engine):
    {"id": 1, "op": "run", "cmd": "open safari and play music"}
    {"id": 2, "op": "confirm"}                  # run the pending sensitive command
    {"id": 3, "op": "cancel"}                   # drop the pending command
    {"id": 4, "op": "preview", "cmd": "set a timer for te"}
    {"id": 5, "op": "status"}
    {"id": 6, "op": "set_coreml", "enabled": true}

Responses carry the same "id". Unsolicited events have an "event" key instead.
"""

import json
import os
import queue
import sys
import threading
import time
from typing import Any, Dict, Optional

from .core import events
from .core.context import context_engine
from .core.osa import AppleScriptError, set_remote_runner, warm_up
from .core import ai
from .core.router import CommandRouter, describe

_write_lock = threading.Lock()
_out = sys.stdout

CONFIRM_WORDS = {"yes", "yeah", "yep", "confirm", "do it", "go ahead", "sure", "ok", "okay", "ndio", "ndiyo", "sawa", "endelea"}
CANCEL_WORDS = {"no", "nope", "cancel", "stop", "never mind", "nevermind", "don't", "hapana", "acha", "sitaki"}


def send(obj: Dict[str, Any]):
    line = json.dumps(obj, ensure_ascii=False)
    with _write_lock:
        _out.write(line + "\n")
        _out.flush()


def _decision_dict(d) -> Dict[str, Any]:
    return {
        "domain": d.domain,
        "action": d.action,
        "label": describe(d),
        "confidence": round(float(d.confidence), 2),
        "source": d.source,
    }


class Engine:
    def __init__(self):
        self.router = CommandRouter()
        self.pending: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        brain = self.router.brain
        return {
            "coreml": brain.coreml_state,
            "coreml_enabled": brain.coreml_enabled,
            "compute_units": brain.compute_units,
            **ai.status(),
            "pending": self.pending,
        }

    def _respond(self, rid, resp, latency_ms: float, command: str) -> Dict[str, Any]:
        steps = [
            {**_decision_dict(s.decision), "success": s.success, "message": s.message}
            for s in resp.steps
        ] or [{**_decision_dict(resp.decision), "success": resp.success, "message": resp.message}]
        return {
            "id": rid,
            "command": command,
            "success": resp.success,
            "message": resp.message,
            "domain": resp.decision.domain,
            "action": resp.decision.action,
            "confidence": round(float(resp.decision.confidence), 2),
            "source": resp.decision.source,
            "latency_ms": round(latency_ms, 1),
            "needs_confirmation": resp.needs_confirmation,
            "suggestion": resp.suggestion,
            "steps": steps,
        }

    def run(self, rid, command: str, confirmed: bool = False) -> Dict[str, Any]:
        spoken = command.strip().lower().strip(".!? ")
        if self.pending and spoken in CONFIRM_WORDS:
            return self.confirm(rid)
        if self.pending and spoken in CANCEL_WORDS:
            return self.cancel(rid)

        start = time.perf_counter()
        resp = self.router.process(command, confirmed=confirmed)
        latency = (time.perf_counter() - start) * 1000
        self.pending = command if resp.needs_confirmation else None
        return self._respond(rid, resp, latency, command)

    def confirm(self, rid) -> Dict[str, Any]:
        if not self.pending:
            return {"id": rid, "success": False, "message": "Nothing is waiting for confirmation.", "steps": []}
        command, self.pending = self.pending, None
        return self.run(rid, command, confirmed=True)

    def cancel(self, rid) -> Dict[str, Any]:
        self.pending = None
        return {"id": rid, "success": True, "message": "Cancelled.", "domain": "general", "action": "cancel", "steps": []}

    def preview(self, rid, command: str) -> Dict[str, Any]:
        start = time.perf_counter()
        steps = self.router.preview(command)
        handled = [s for s in steps if s.handled]
        return {
            "id": rid,
            "preview": [_decision_dict(s) for s in handled],
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    def handle(self, req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        rid = req.get("id")
        op = req.get("op", "run")
        if req.get("front_app"):
            context_engine.front_app_hint = str(req["front_app"])
        if op == "run":
            return self.run(rid, str(req.get("cmd", "")))
        if op == "confirm":
            return self.confirm(rid)
        if op == "cancel":
            return self.cancel(rid)
        if op == "preview":
            return self.preview(rid, str(req.get("cmd", "")))
        if op == "status":
            return {"id": rid, **self.status()}
        if op == "set_cloud_key":
            from .core.cloud import KEY_FILE, cloud_llm

            key = str(req.get("key", "")).strip()
            if key:
                KEY_FILE.write_text(key)
                KEY_FILE.chmod(0o600)
            elif KEY_FILE.exists():
                KEY_FILE.unlink()
            cloud_llm.available()
            return {"id": rid, **self.status()}
        if op == "set_coreml":
            self.router.brain.set_coreml_enabled(bool(req.get("enabled")))
            return {"id": rid, **self.status()}
        return {"id": rid, "success": False, "message": f"Unknown op '{op}'."}


def _status_pump(engine: Engine):
    """Push Core ML state changes (cold -> warming -> ready) to the UI."""
    last = None
    while True:
        state = (engine.router.brain.coreml_state, tuple(ai.status().values()))
        if state != last:
            events.emit("status", **engine.status())
            last = state
        time.sleep(0.5)


class RemoteAppleScript:
    """Asks the host app to run AppleScript and waits for its reply."""

    def __init__(self):
        self._next = 1
        self._lock = threading.Lock()
        self._waiters: Dict[int, Dict[str, Any]] = {}

    def __call__(self, script: str, timeout: float) -> str:
        with self._lock:
            oid = self._next
            self._next += 1
            slot: Dict[str, Any] = {"done": threading.Event()}
            self._waiters[oid] = slot
        send({"event": "osa", "osa_id": oid, "script": script, "timeout": timeout})
        # Generous wait: the first call to an app may sit behind a macOS permission dialog.
        finished = slot["done"].wait(timeout + 60)
        with self._lock:
            self._waiters.pop(oid, None)
        if not finished:
            raise AppleScriptError("Timed out waiting for macOS — check for a permission dialog.")
        if not slot.get("ok"):
            raise AppleScriptError(slot.get("error") or "AppleScript failed")
        return slot.get("result") or ""

    def resolve(self, reply: Dict[str, Any]):
        with self._lock:
            slot = self._waiters.get(int(reply.get("osa_reply", -1)))
        if slot is not None:
            slot.update(ok=bool(reply.get("ok")), result=reply.get("result"), error=reply.get("error"))
            slot["done"].set()


# Ops that never touch AppleScript and can run while a command is executing.
INSTANT_OPS = {"preview", "status"}


def main():
    global _out
    # Tools must never write to our protocol channel.
    _out = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout = sys.stderr

    events.subscribe(send)
    engine = Engine()
    remote = RemoteAppleScript() if os.getenv("SPEEDX_HOST_OSA", "1") == "1" and os.getenv("SPEEDX_HOSTED") == "1" else None
    if remote:
        set_remote_runner(remote)
    else:
        warm_up()
    engine.router.brain.warm_async()
    ai.warm_async()
    threading.Thread(target=_status_pump, args=(engine,), daemon=True).start()

    work: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()

    def execute(req: Dict[str, Any]):
        try:
            resp = engine.handle(req)
        except Exception as e:  # keep the daemon alive no matter what
            resp = {"id": req.get("id"), "success": False, "message": f"Engine error: {e}", "steps": []}
        if resp is not None:
            send(resp)

    def reader():
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                send({"event": "error", "message": "bad json"})
                continue
            if "osa_reply" in req:
                if remote:
                    remote.resolve(req)
            elif req.get("op") in INSTANT_OPS:
                execute(req)
            else:
                work.put(req)
        work.put(None)

    threading.Thread(target=reader, name="stdin-reader", daemon=True).start()
    send({"event": "ready", **engine.status()})

    # Commands run on the main thread, one at a time, in arrival order.
    while True:
        req = work.get()
        if req is None:
            break
        execute(req)


if __name__ == "__main__":
    main()
