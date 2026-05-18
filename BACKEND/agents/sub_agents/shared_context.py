"""
AERIS — Shared Context Buffer for Multi-Agent Communication
===================================================================
A thread-safe shared memory buffer that allows specialized sub-agents
to exchange context, intermediate results, and metadata during a
multi-agent workflow execution.

This does NOT replace or interfere with the existing MemoryAgent.
It is a lightweight, ephemeral, per-task context store.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisSharedContext")


@dataclass
class AgentMessage:
    """A single message posted by a sub-agent into the shared context."""
    sender: str           # Agent name (e.g., "ResearchAgent")
    content: Any          # The payload (string, dict, list, etc.)
    message_type: str     # e.g., "result", "error", "request", "metadata"
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sender": self.sender,
            "content": str(self.content)[:2000],
            "message_type": self.message_type,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class SharedContextBuffer:
    """
    Thread-safe shared context buffer for multi-agent communication.

    Each task gets its own buffer instance. Agents can:
      - post() messages into the buffer
      - get_messages() to read all messages (or filtered by sender/type)
      - get_latest_result() to quickly grab the last result from any agent
      - set/get key-value pairs via set_var() / get_var()
    """

    def __init__(self, task_id: str, objective: str):
        self.task_id = task_id
        self.objective = objective
        self.created_at = time.time()
        self._messages: List[AgentMessage] = []
        self._variables: Dict[str, Any] = {}
        self._lock = threading.Lock()

    # ── Message Passing ──────────────────────────────────────────────

    def post(self, sender: str, content: Any,
             message_type: str = "result", **metadata) -> None:
        """Post a message into the shared context."""
        with self._lock:
            msg = AgentMessage(
                sender=sender,
                content=content,
                message_type=message_type,
                metadata=metadata,
            )
            self._messages.append(msg)
            logger.debug(
                f"[SharedContext:{self.task_id[:8]}] "
                f"{sender} posted {message_type}: {str(content)[:100]}"
            )

    def get_messages(self, sender: str = None,
                     message_type: str = None) -> List[AgentMessage]:
        """Get messages, optionally filtered by sender and/or type."""
        with self._lock:
            msgs = self._messages[:]
        if sender:
            msgs = [m for m in msgs if m.sender == sender]
        if message_type:
            msgs = [m for m in msgs if m.message_type == message_type]
        return msgs

    def get_latest_result(self, sender: str = None) -> Optional[Any]:
        """Get the content of the most recent 'result' message."""
        results = self.get_messages(sender=sender, message_type="result")
        if results:
            return results[-1].content
        return None

    def get_all_results(self) -> Dict[str, Any]:
        """Get the latest result from each sender agent."""
        with self._lock:
            latest: Dict[str, Any] = {}
            for msg in self._messages:
                if msg.message_type == "result":
                    latest[msg.sender] = msg.content
            return latest

    # ── Key-Value Store ──────────────────────────────────────────────

    def set_var(self, key: str, value: Any) -> None:
        """Store a variable accessible by all agents."""
        with self._lock:
            self._variables[key] = value

    def get_var(self, key: str, default: Any = None) -> Any:
        """Retrieve a shared variable."""
        with self._lock:
            return self._variables.get(key, default)

    # ── Serialisation ────────────────────────────────────────────────

    def to_summary(self) -> str:
        """Build a compact text summary of all context for LLM injection."""
        lines = [f"Task: {self.objective}"]
        for msg in self._messages:
            preview = str(msg.content)[:300]
            lines.append(f"[{msg.sender}|{msg.message_type}]: {preview}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "messages": [m.to_dict() for m in self._messages],
            "variables": {k: str(v)[:500] for k, v in self._variables.items()},
        }
