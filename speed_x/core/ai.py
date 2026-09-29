"""Chooses the AI brain: Claude (if a key is configured and reachable), else the local Ollama model.

Every call falls back to the local model when the cloud call fails, so going offline
never breaks Speed-X; it just gets slower.
"""

from typing import Any, Dict, Optional

from .cloud import cloud_llm
from .llm import local_llm


def _brains():
    return [cloud_llm, local_llm] if cloud_llm.available() else [local_llm]


def plan(request: str, context: str = "") -> Optional[Dict[str, Any]]:
    for brain in _brains():
        result = brain.plan(request, context)
        if result is not None:
            result["brain"] = brain.kind
            return result
    return None


def stream(system: str, user: str, on_delta=None) -> Optional[str]:
    for brain in _brains():
        reply = brain.stream(system, user, on_delta=on_delta)
        if reply:
            return reply
    return None


def remember(request: str, summary: str):
    for brain in (cloud_llm, local_llm):
        brain.remember(request, summary)


def warm_async():
    cloud_llm.warm_async()
    local_llm.warm_async()


def status() -> Dict[str, str]:
    active = cloud_llm if cloud_llm.available() else local_llm
    return {
        "llm": active.state,
        "llm_model": active.model,
        "llm_kind": active.kind,
        "local_llm": local_llm.state,
        "cloud_llm": cloud_llm.state,
    }
