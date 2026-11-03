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
    {"id": 7, "op": "dictate", "text": "um so new line hello"}      # -> {"text": "Hello"} cleaned for typing
    {"id": 8, "op": "meeting_line", "text": "we agreed to ship friday"}
    {"id": 9, "op": "dictionary"}                                    # -> {"hints": [...]}

Responses carry the same "id". Unsolicited events have an "event" key instead.
"""

import json
import os
import queue
import sys
import threading
import time
from typing import Any, Dict, Optional

from .core import ai, events
from .core import dictation as dictation_mod
from .core.agents import Agent
from .core.context import context_engine
from .core.meeting import meetings
from .core.routines import Scheduler, routines
from .core.updater import check as check_update
from .core.osa import AppleScriptError, set_remote_runner, warm_up
from .core.router import CommandRouter, describe

_write_lock = threading.Lock()
_out = sys.stdout

CONFIRM_WORDS = {
    "yes",
    "yeah",
    "yep",
    "confirm",
    "do it",
    "go ahead",
    "sure",
    "ok",
    "okay",
    "ndio",
    "ndiyo",
    "sawa",
    "endelea",
}
CANCEL_WORDS = {
    "no",
    "nope",
    "cancel",
    "stop",
    "never mind",
    "nevermind",
    "don't",
    "hapana",
    "acha",
    "sitaki",
}


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
            "meeting_active": meetings.active,
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
            return {
                "id": rid,
                "success": False,
                "message": "Nothing is waiting for confirmation.",
                "steps": [],
            }
        command, self.pending = self.pending, None
        return self.run(rid, command, confirmed=True)

    def cancel(self, rid) -> Dict[str, Any]:
        self.pending = None
        return {
            "id": rid,
            "success": True,
            "message": "Cancelled.",
            "domain": "general",
            "action": "cancel",
            "steps": [],
        }

    def preview(self, rid, command: str) -> Dict[str, Any]:
        start = time.perf_counter()
        steps = self.router.preview(command)
        handled = [s for s in steps if s.handled]
        return {
            "id": rid,
            "preview": [_decision_dict(s) for s in handled],
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        }

    # -- background agents & routines (run through the router, never auto-confirm) -----------
    def run_agent(self, command: str, agent: Agent) -> None:
        agent.status = "running"
        resp = self.router.process(command)
        if agent.cancel.is_set():
            agent.status = "stopped"
            return
        agent.steps = [
            {"label": s.decision.domain + "." + s.decision.action, "success": s.success, "message": s.message}
            for s in resp.steps
        ]
        agent.message = resp.message
        if resp.needs_confirmation:
            agent.status = "needs_approval"
            agent.message = f"Needs your OK, so I stopped: {resp.confirmation_prompt}"
        else:
            agent.status = "done" if resp.success else "failed"

    def run_routine(self, routine: Dict[str, Any]) -> None:
        resp = self.router.process(routine["command"])
        message = (
            f"Skipped (needs your OK): {resp.confirmation_prompt}" if resp.needs_confirmation else resp.message
        )
        events.emit(
            "routine_done",
            command=routine["command"],
            success=bool(resp.success) and not resp.needs_confirmation,
            message=message,
        )

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
        if op == "dictate":
            raw = str(req.get("text", ""))
            text = dictation_mod.cleanup(raw, dictation_mod.dictionary)
            stats = dictation_mod.record(text) if text.strip() else dictation_mod.read_stats()
            return {"id": rid, "success": True, "text": text, "words": len(text.split()), **stats}
        if op == "meeting_line":
            return {"id": rid, "success": meetings.add_line(str(req.get("text", ""))), "active": meetings.active}
        if op == "dictionary":
            return {"id": rid, "success": True, "hints": dictation_mod.dictionary.hints()}
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
            slot.update(
                ok=bool(reply.get("ok")), result=reply.get("result"), error=reply.get("error")
            )
            slot["done"].set()


# Ops that never touch AppleScript and can run while a command is executing.
INSTANT_OPS = {"preview", "status", "dictate", "meeting_line", "dictionary"}


def _meeting_recap(transcript: str) -> Optional[str]:
    """A short written recap, only when a model is already up (never blocks on a cold load)."""
    st = ai.status()
    if st.get("local_llm") != "ready" and st.get("cloud_llm") != "ready":
        return None
    return ai.stream(
        "You write concise meeting recaps: 3-5 plain sentences, no preamble.",
        "Recap this meeting transcript:\n" + transcript[-6000:],
    )


def _wire_features(engine: "Engine") -> None:
    """Start routines, give the agent tool its runner, and do the daily update check."""
    from .tools.base import registry

    meetings._recap = _meeting_recap
    agent_tool = registry.get("agents")
    if agent_tool is not None:
        agent_tool.runner = engine.run_agent
    # Routines are queued like any command so AppleScript still runs one thing at a time.
    Scheduler(routines, lambda r: _queue_routine(engine, r)).start()
    if os.getenv("SPEEDX_UPDATE_CHECK", "1") == "1" and os.getenv("SPEEDX_HOSTED") == "1":
        threading.Thread(target=_daily_update_check, daemon=True).start()


_routine_queue: "Optional[queue.Queue]" = None


def _queue_routine(engine: "Engine", routine: Dict[str, Any]) -> None:
    if _routine_queue is not None:
        _routine_queue.put({"op": "routine", "routine": routine})


def _daily_update_check() -> None:
    time.sleep(20)
    while True:
        info = check_update()
        if info.get("newer"):
            events.emit("update_available", version=info["latest"], page=info["page"])
        time.sleep(24 * 3600)


def main():
    global _out, _routine_queue
    # Tools must never write to our protocol channel.
    _out = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout = sys.stderr

    events.subscribe(send)
    engine = Engine()
    remote = (
        RemoteAppleScript()
        if os.getenv("SPEEDX_HOST_OSA", "1") == "1" and os.getenv("SPEEDX_HOSTED") == "1"
        else None
    )
    if remote:
        set_remote_runner(remote)
    else:
        warm_up()
    work: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
    _routine_queue = work
    engine.router.brain.warm_async()
    ai.warm_async()
    _wire_features(engine)
    threading.Thread(target=_status_pump, args=(engine,), daemon=True).start()


    def execute(req: Dict[str, Any]):
        try:
            if req.get("op") == "routine":
                engine.run_routine(req["routine"])
                return
            resp = engine.handle(req)
        except Exception as e:  # keep the daemon alive no matter what
            resp = {
                "id": req.get("id"),
                "success": False,
                "message": f"Engine error: {e}",
                "steps": [],
            }
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
