"""Tiny event bus so tools can push asynchronous events (e.g. timer finished) to the UI daemon."""

from typing import Any, Callable, Dict, List

_listeners: List[Callable[[Dict[str, Any]], None]] = []


def subscribe(listener: Callable[[Dict[str, Any]], None]):
    _listeners.append(listener)


def emit(event: str, **payload: Any):
    message = {"event": event, **payload}
    for listener in list(_listeners):
        try:
            listener(message)
        except Exception:
            pass
