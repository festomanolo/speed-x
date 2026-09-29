"""Local AI brain (Ollama) for everything the rule engine doesn't cover.

The fast layers (rules + semantic matcher) still answer known commands in
milliseconds. When they can't, a small local model plans *tool calls* from a
catalog of Speed-X tools, or answers directly. Everything stays on this Mac.

Two passes:
  plan()    request -> {"steps": [...], "reply": "...", "then_answer": bool}
  answer()  request + what the tools returned -> final natural-language reply
            (e.g. "summarize what's on my screen", "translate my clipboard to Swahili")
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from typing import Any, Deque, Dict, List, Optional

OLLAMA_URL = os.getenv("SPEEDX_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("SPEEDX_LLM_MODEL", "qwen2.5:3b")
PLAN_TIMEOUT_S = float(os.getenv("SPEEDX_LLM_TIMEOUT", "45"))
NUM_CTX = 4096  # one size everywhere: Ollama reloads the model when this changes

# domain.action -> allowed params. Only these can ever be executed.
TOOL_CATALOG: Dict[str, List[str]] = {
    "apps.open": ["app"],
    "apps.quit": ["app"],
    "apps.list_running": [],
    "apps.switch": ["app"],
    "music.play": [],
    "music.play_song": ["query", "artist", "player"],
    "music.pause": [],
    "music.next": [],
    "music.previous": [],
    "music.get_current_track": [],
    "system.volume_up": [],
    "system.volume_down": [],
    "system.set_volume": ["level"],
    "system.mute": [],
    "system.unmute": [],
    "system.lock_screen": [],
    "system.sleep": [],
    "system.toggle_dark_mode": ["mode"],
    "messaging.send": ["to", "text", "app"],
    "mail.send": ["recipient", "subject", "message"],
    "mail.compose": ["recipient", "subject", "message"],
    "mail.open": [],
    "notes.create": ["title", "body"],
    "notes.update": ["addition"],
    "notes.open": [],
    "timer.set": ["seconds", "label"],
    "timer.remind": ["text", "seconds"],
    "timer.cancel": [],
    "timer.time": [],
    "timer.date": [],
    "timer.list": [],
    "web.search": ["query"],
    "web.youtube": ["query"],
    "web.open_url": ["url"],
    "files.search": ["query"],
    "files.find_pdf": ["query"],
    "files.create": ["filename", "content"],
    "files.latest_screenshot": [],
    "files.open_file": ["path"],
    "clipboard.read": [],
    "clipboard.write": ["text"],
    "clipboard.inspect": [],
    "clipboard.clear": [],
    "screen.capture": [],
    "screen.read": [],
    "screen.active_window": [],
    "workspaces.activate": ["workspace"],
    "workspaces.list": [],
    "workspaces.create": ["workspace", "apps"],
    "workspaces.save_current": ["workspace"],
    "workspaces.add": ["workspace", "apps"],
    "workspaces.delete": ["workspace"],
}

SYSTEM_PROMPT = """You turn a Mac user's request (English, Swahili or Sheng) into actions.
Output ONLY action lines, one per line, in the form:  tool key=value; key=value
If the user needs an answer rather than an action, output one line:  SAY <short answer>
Tools: """ + "; ".join(f"{n}({','.join(p)})" if p else n for n, p in TOOL_CATALOG.items()) + """

Examples:
make it quiet -> system.mute
play some music softly -> system.set_volume level=20
music.play
get me ready for a zoom meeting -> apps.open app=zoom.us
system.set_volume level=60
put on nadina by mbosso -> music.play_song query=nadina; artist=mbosso
nataka kulala -> music.pause
system.set_volume level=10
search how to cook pilau -> web.search query=how to cook pilau
wake me in 20 minutes -> timer.set seconds=1200; label=wake up
text Juma I'm late on whatsapp -> messaging.send to=Juma; text=I'm late; app=WhatsApp
set up a design space with figma and safari -> workspaces.create workspace=design; apps=Figma, Safari"""

ANSWER_PROMPT = """You are Speed-X, a concise Mac assistant. Using the tool results below, do what the user asked
(summarize, explain, translate, extract, answer). Reply in the user's language, plainly, under 90 words.
Respond ONLY with JSON: {"reply": "<text>", "copy": false}
Set "copy": true only if the user asked for the result to be copied or written somewhere."""


CHAT_PROMPT = """You are Speed-X, a warm, sharp assistant living on the user's Mac. You understand English, Swahili and Sheng.
Answer directly and concisely (under 80 words) in the same language the user used. Plain text, no markdown headings.
If you are not sure a fact is correct, say you're not sure instead of guessing."""

THINK_PROMPT = """You are Speed-X. Do exactly what the user asked (summarize, explain, translate, extract, rewrite, answer)
using the content provided. Reply in the language the user asked for, plainly, under 110 words. Plain text only."""


def parse_plan_lines(text: str) -> Optional[Dict[str, Any]]:
    """Parse planner output ("tool key=value; key=value" lines or "SAY ...") into validated steps."""
    steps, reply = [], ""
    for line in text.splitlines():
        line = line.strip().strip("`").strip()
        if not line:
            continue
        if line.upper().startswith("SAY "):
            reply = line[4:].strip()
            continue
        name, _, rest = line.partition(" ")
        if name not in TOOL_CATALOG:
            continue  # never execute a tool the model invented
        params: Dict[str, Any] = {}
        for pair in rest.split(";"):
            key, eq, value = pair.strip().partition("=")
            if eq and key.strip() in TOOL_CATALOG[name] and value.strip():
                params[key.strip()] = value.strip()
        for key in ("seconds", "level"):
            if key in params:
                try:
                    params[key] = int(float(params[key]))
                except ValueError:
                    params.pop(key)
        domain, action = name.split(".", 1)
        steps.append({"domain": domain, "action": action, "params": params})
    if not steps and not reply:
        return None
    return {"steps": steps[:6], "reply": reply, "then_answer": False}


class LocalLLM:
    kind = "local"

    def __init__(self, model: str = MODEL):
        self.model = model
        self.state = "cold"  # cold | warming | ready | missing | offline
        self.history: Deque[Dict[str, str]] = deque(maxlen=6)  # recent exchanges for follow-ups
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ transport

    def _post(self, path: str, body: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        req = urllib.request.Request(
            OLLAMA_URL + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())

    def available(self) -> bool:
        if os.getenv("SPEEDX_LLM", "1") == "0":
            self.state = "off"
            return False
        try:
            with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=1.5) as resp:
                names = [m.get("name", "") for m in json.loads(resp.read()).get("models", [])]
        except Exception:
            self.state = "offline"
            return False
        if not any(n == self.model or n.startswith(self.model + ":") or n.split(":")[0] == self.model for n in names):
            self.state = "missing"
            return False
        if self.state in ("cold", "offline", "missing"):
            self.state = "ready"
        return True

    def warm_async(self):
        """Load the model into memory in the background so the first request is fast."""

        def run():
            if not self.available():
                return
            self.state = "warming"
            try:
                # Load weights and pre-fill the chat prompt's cache; generate a single token only.
                self._post("/api/chat", {"model": self.model, "stream": False, "keep_alive": "45m",
                                         "messages": [{"role": "system", "content": CHAT_PROMPT}, {"role": "user", "content": "hi"}],
                                         "options": {"num_predict": 1, "num_ctx": NUM_CTX}}, timeout=120)
                self.state = "ready"
            except Exception:
                self.state = "offline"

        threading.Thread(target=run, name="llm-warmup", daemon=True).start()

    def _chat(self, messages: List[Dict[str, str]], timeout: float) -> Dict[str, Any]:
        with self._lock:
            out = self._post(
                "/api/chat",
                {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "45m",
                    "options": {"temperature": 0.1, "num_predict": 320, "num_ctx": NUM_CTX},
                },
                timeout,
            )
        content = out.get("message", {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start, end = content.find("{"), content.rfind("}")
            return json.loads(content[start : end + 1]) if start >= 0 < end else {}

    # ------------------------------------------------------------------ public

    def plan(self, request: str, context: str = "") -> Optional[Dict[str, Any]]:
        """Validated plan, or None when the model is unavailable/unusable."""
        if not self.available():
            return None
        user = request if not context else f"{request}   [{context}]"
        started = time.perf_counter()
        text = self._complete(SYSTEM_PROMPT, user + " ->", max_tokens=40, timeout=PLAN_TIMEOUT_S)
        if text is None:
            return None

        plan = parse_plan_lines(text)
        if plan is None:
            return None
        plan["latency_ms"] = (time.perf_counter() - started) * 1000
        return plan

    def _complete(self, system: str, user: str, max_tokens: int, timeout: float) -> Optional[str]:
        """Short, deterministic, non-streamed completion; stops at a blank line."""
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "keep_alive": "45m",
            "options": {"temperature": 0, "num_predict": max_tokens, "num_ctx": NUM_CTX, "stop": ["\n\n", "->"]},
        }
        try:
            with self._lock:
                out = self._post("/api/chat", body, timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            self.state = "offline"
            return None
        self.state = "ready"
        return out.get("message", {}).get("content", "")

    def answer(self, request: str, observations: List[str]) -> Optional[Dict[str, Any]]:
        if not self.available():
            return None
        joined = "\n\n".join(o[:3500] for o in observations)
        messages = [
            {"role": "system", "content": ANSWER_PROMPT},
            {"role": "user", "content": f"User request: {request}\n\nTool results:\n{joined}"},
        ]
        try:
            raw = self._chat(messages, timeout=PLAN_TIMEOUT_S + 15)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return None
        reply = str(raw.get("reply") or "").strip()
        return {"reply": reply, "copy": bool(raw.get("copy"))} if reply else None

    def stream(self, system: str, user: str, on_delta=None, timeout: float = 120) -> Optional[str]:
        """Plain-text streamed reply; on_delta(text_so_far) is called as tokens arrive."""
        if not self.available():
            return None
        messages = [{"role": "system", "content": system}]
        messages.extend(t for t in self.history if t["role"] == "user" or not t["content"].startswith("{"))
        messages.append({"role": "user", "content": user})
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": "45m",
            "options": {"temperature": 0.4, "num_predict": 260, "num_ctx": NUM_CTX},
        }
        req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        text = ""
        last_push = 0.0
        try:
            with self._lock, urllib.request.urlopen(req, timeout=timeout) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    text += chunk.get("message", {}).get("content", "")
                    now = time.perf_counter()
                    if on_delta and (now - last_push > 0.08 or chunk.get("done")):
                        on_delta(text)
                        last_push = now
                    if chunk.get("done"):
                        break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            self.state = "offline"
            return text.strip() or None
        self.state = "ready"
        return text.strip() or None

    def remember(self, request: str, summary: str):
        """Keep a short conversation memory so follow-ups ("send it to Juma too") make sense."""
        self.history.append({"role": "user", "content": request})
        self.history.append({"role": "assistant", "content": summary[:300]})


local_llm = LocalLLM()
