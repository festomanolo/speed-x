"""Smart guardrails and confirmation policies for Laya OS."""

from typing import Tuple

# Actions that modify deep system state or can interrupt ongoing user tasks
SENSITIVE_ACTIONS = {
    ("system", "sleep"): "Put your Mac to sleep",
    ("system", "lock_screen"): "Lock your screen",
    ("apps", "quit"): "Quit application",
}


class GuardrailManager:
    """Manages safety checks and user confirmations before action dispatch."""

    def requires_confirmation(self, domain: str, action: str) -> Tuple[bool, str]:
        key = (domain, action)
        if key in SENSITIVE_ACTIONS:
            return True, SENSITIVE_ACTIONS[key]
        return False, ""


guardrails = GuardrailManager()
