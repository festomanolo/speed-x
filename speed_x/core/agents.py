"""Agent windows: commands that run in the background while you keep working.

"in the background, open safari and play music" starts an *agent*: a thread that runs the
command through the router and reports live. The UI shows each agent as a small floating
window (status dot, command, step results). Agents can be stopped between steps. A step
that needs confirmation is not auto-approved: the agent stops and says so.
"""

import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import events

MAX_AGENTS = 8


class Agent:
    def __init__(self, aid: int, command: str):
        self.id, self.command = aid, command
        self.status = "running"  # running | done | failed | stopped | needs_approval
        self.steps: List[Dict[str, Any]] = []
        self.message = ""
        self.started = time.time()
        self.cancel = threading.Event()

    def to_dict(self) -> Dict[str, Any]:
        # "agent_id", not "id": responses use "id" to match requests.
        return {
            "agent_id": self.id,
            "command": self.command,
            "status": self.status,
            "message": self.message,
            "lines": [f"{'✓' if s.get('success') else '✗'} {s.get('message', '')}" for s in self.steps],
            "elapsed": round(time.time() - self.started, 1),
        }


class AgentManager:
    def __init__(self):
        self._agents: Dict[int, Agent] = {}
        self._next = 1
        self._lock = threading.Lock()

    def start(self, command: str, runner: Callable[[str, Agent], None], sync: bool = False) -> Agent:
        with self._lock:
            active = [a for a in self._agents.values() if a.status == "running"]
            if len(active) >= MAX_AGENTS:
                raise RuntimeError(f"{MAX_AGENTS} agents are already running.")
            agent = Agent(self._next, command)
            self._next += 1
            self._agents[agent.id] = agent
        events.emit("agent_update", **agent.to_dict())

        def work():
            try:
                runner(command, agent)
            except Exception as e:  # an agent must never take the daemon down
                agent.status, agent.message = "failed", f"Agent error: {e}"
            events.emit("agent_update", **agent.to_dict())

        if sync:
            work()
        else:
            threading.Thread(target=work, name=f"agent-{agent.id}", daemon=True).start()
        return agent

    def stop(self, ref: Optional[str] = None) -> List[Agent]:
        with self._lock:
            targets = [
                a
                for a in self._agents.values()
                if a.status == "running" and (not ref or ref in ("all", "everything") or ref == str(a.id) or ref.lower() in a.command.lower())
            ]
        for a in targets:
            a.cancel.set()
            a.status = "stopped"
            events.emit("agent_update", **a.to_dict())
        return targets

    def list(self) -> List[Agent]:
        with self._lock:
            return sorted(self._agents.values(), key=lambda a: a.id)

    def dismiss_finished(self) -> None:
        with self._lock:
            self._agents = {k: a for k, a in self._agents.items() if a.status == "running"}


agents = AgentManager()
