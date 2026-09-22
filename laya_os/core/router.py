"""Central Command Router connecting LayaBrain, Guardrails, Memory, and Tools."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..tools.base import ToolResult, registry
from .brain import IntentDecision, LayaBrain
from .guardrails import guardrails
from .memory import memory


@dataclass
class ExecutionResponse:
    success: bool
    message: str
    decision: IntentDecision
    needs_confirmation: bool = False
    confirmation_prompt: str = ""
    data: Optional[Dict[str, Any]] = None


class CommandRouter:
    """Orchestrates natural language intent recognition, safety checks, and execution."""

    def __init__(self, brain: Optional[LayaBrain] = None):
        self.brain = brain or LayaBrain()

    def process(self, prompt: str, confirmed: bool = False) -> ExecutionResponse:
        prompt = prompt.strip()
        if not prompt:
            return ExecutionResponse(
                success=False,
                message="Empty command provided.",
                decision=IntentDecision("general", "none", {}, 0.0, False, "none"),
            )

        # 1. Decide intent via Laya Brain
        decision = self.brain.decide(prompt)

        # 2. Check if general / unhandled
        if decision.domain == "general" or decision.action == "unhandled":
            return ExecutionResponse(
                success=False,
                message=f"I didn't understand the command '{prompt}'. Try asking for music, apps, volume, files, or workspaces.",
                decision=decision,
            )

        # 3. Check guardrails
        is_sensitive, reason = guardrails.requires_confirmation(decision.domain, decision.action)
        if (is_sensitive or decision.requires_confirmation) and not confirmed:
            prompt_msg = f"Confirmation required: {reason or 'This action affects system state'}. Proceed? (y/n)"
            return ExecutionResponse(
                success=False,
                message=prompt_msg,
                decision=decision,
                needs_confirmation=True,
                confirmation_prompt=prompt_msg,
            )

        # 4. Dispatch to native tool
        tool_result: ToolResult = registry.dispatch(
            decision.domain,
            decision.action,
            decision.params,
        )

        # 5. Log to persistent memory
        memory.log_command(
            command=prompt,
            domain=decision.domain,
            action=decision.action,
            success=tool_result.success,
        )

        return ExecutionResponse(
            success=tool_result.success,
            message=tool_result.message,
            decision=decision,
            data=tool_result.data,
        )
