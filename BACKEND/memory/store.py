"""
AERIS Memory Store — Persistent conversation history and task results.
Saves to JSON file in BACKEND/data/ directory.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger("aeris.memory")


class MemoryStore:
    """Store and retrieve conversation history and task results."""

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.chat_history: list[dict] = []
        self.task_results: dict[str, dict] = {}
        self._file_path = settings.DATA_DIR / "memory.json"

        # Load existing data
        self.load()

    def add_message(self, role: str, content: str, metadata: Optional[dict] = None) -> None:
        """Add a message to chat history."""
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if metadata:
            entry["metadata"] = metadata

        self.chat_history.append(entry)

        # Trim to max history
        if len(self.chat_history) > self.max_history:
            self.chat_history = self.chat_history[-self.max_history:]

        self.save()

    def get_context(self, n: int = 10) -> list[dict]:
        """Get last N messages for context."""
        return self.chat_history[-n:]

    def get_context_string(self, n: int = 10) -> str:
        """Get last N messages as a formatted string."""
        messages = self.get_context(n)
        parts = []
        for msg in messages:
            role = "User" if msg["role"] == "user" else "AERIS"
            parts.append(f"{role}: {msg['content']}")
        return "\n".join(parts)

    def store_task(self, task_id: str, result: dict) -> None:
        """Save a task execution result."""
        self.task_results[task_id] = {
            **result,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        # Keep only last 50 tasks
        if len(self.task_results) > 50:
            keys = sorted(self.task_results.keys())
            for k in keys[:-50]:
                del self.task_results[k]
        self.save()

    def get_task(self, task_id: str) -> Optional[dict]:
        """Retrieve a stored task result."""
        return self.task_results.get(task_id)

    def clear_history(self) -> None:
        """Clear all chat history."""
        self.chat_history = []
        self.save()
        logger.info("Chat history cleared")

    def clear_all(self) -> None:
        """Clear everything."""
        self.chat_history = []
        self.task_results = {}
        self.save()
        logger.info("All memory cleared")

    def save(self) -> None:
        """Persist memory to disk."""
        try:
            data = {
                "chat_history": self.chat_history,
                "task_results": self.task_results,
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def load(self) -> None:
        """Load memory from disk."""
        try:
            if self._file_path.exists():
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
                self.chat_history = data.get("chat_history", [])
                self.task_results = data.get("task_results", {})
                logger.info(f"Loaded memory: {len(self.chat_history)} messages, {len(self.task_results)} tasks")
            else:
                logger.info("No existing memory file — starting fresh")
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            self.chat_history = []
            self.task_results = {}

    def __repr__(self) -> str:
        return f"<MemoryStore: {len(self.chat_history)} messages, {len(self.task_results)} tasks>"


# Global singleton
memory_store = MemoryStore()
