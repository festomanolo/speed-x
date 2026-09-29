"""Optional cloud brain (Claude) for fast, accurate answers when you're online.

Off unless an Anthropic API key is configured, either as ANTHROPIC_API_KEY or in
~/.config/speed_x/anthropic_api_key (the file works for the menu-bar app, which
doesn't inherit your shell environment). Set SPEEDX_CLOUD=0 to force local-only.

Only the text of requests that reach the AI layers is sent. Known commands are
decided locally by the rule engine and never leave the Mac.
"""

import os
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from ..config import USER_CONFIG_DIR
from .llm import SYSTEM_PROMPT, parse_plan_lines

MODEL = os.getenv("SPEEDX_CLOUD_MODEL", "claude-opus-5")
KEY_FILE = USER_CONFIG_DIR / "anthropic_api_key"
FALLBACK_BETA = "server-side-fallback-2026-07-01"  # pairs with fallbacks="default"


def _api_key() -> Optional[str]:
    if os.getenv("SPEEDX_CLOUD", "1") == "0":
        return None
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text().strip()
    return key or None


class CloudLLM:
    kind = "cloud"

    def __init__(self, model: str = MODEL):
        self.model = model
        self.state = "off"
        self.history: Deque[Dict[str, str]] = deque(maxlen=6)
        self._client = None
        self._key: Optional[str] = None

    def _get_client(self):
        key = _api_key()
        if not key:
            self._client, self._key, self.state = None, None, "off"
            return None
        if self._client is None or key != self._key:
            import anthropic

            # Voice UX: fail over to the local model quickly rather than hang.
            self._client = anthropic.Anthropic(api_key=key, timeout=25.0, max_retries=1)
            self._key = key
        return self._client

    def available(self) -> bool:
        if self._get_client() is None:
            return False
        if self.state in ("off", "offline"):
            self.state = "ready"
        return True

    def warm_async(self):
        self.available()

    def _call_failed(self, error: Exception):
        import anthropic

        if isinstance(error, anthropic.AuthenticationError):
            self.state = "bad_key"
        else:
            self.state = "offline"

    def plan(self, request: str, context: str = "") -> Optional[Dict[str, Any]]:
        client = self._get_client()
        if client is None:
            return None
        import anthropic

        user = request if not context else f"{request}   [{context}]"
        started = time.perf_counter()
        try:
            response = client.beta.messages.create(
                model=self.model,
                max_tokens=2000,
                system=SYSTEM_PROMPT + "\n\nReply with the action lines only, no explanation.",
                messages=list(self.history) + [{"role": "user", "content": user + " ->"}],
                output_config={"effort": "low"},  # short planning task: favour latency
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            self._call_failed(e)
            return None
        self.state = "ready"
        if response.stop_reason == "refusal":
            return {"steps": [], "reply": "I can't help with that one.", "then_answer": False}
        text = "".join(block.text for block in response.content if block.type == "text")
        plan = parse_plan_lines(text)
        if plan is not None:
            plan["latency_ms"] = (time.perf_counter() - started) * 1000
        return plan

    def stream(self, system: str, user: str, on_delta=None, timeout: float = 60) -> Optional[str]:
        client = self._get_client()
        if client is None:
            return None
        import anthropic

        messages: List[Dict[str, str]] = list(self.history) + [{"role": "user", "content": user}]
        text = ""
        last_push = 0.0
        try:
            with client.beta.messages.stream(
                model=self.model,
                max_tokens=4000,
                system=system,
                messages=messages,
                output_config={"effort": "low"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                for delta in stream.text_stream:
                    text += delta
                    now = time.perf_counter()
                    if on_delta and now - last_push > 0.06:
                        on_delta(text)
                        last_push = now
                final = stream.get_final_message()
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            self._call_failed(e)
            return text.strip() or None
        self.state = "ready"
        if final.stop_reason == "refusal":
            return "I can't help with that one."
        if on_delta and text:
            on_delta(text)
        return text.strip() or None

    def remember(self, request: str, summary: str):
        self.history.append({"role": "user", "content": request})
        self.history.append({"role": "assistant", "content": summary[:300] or "(done)"})


cloud_llm = CloudLLM()
