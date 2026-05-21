"""
AERIS Memory Store — Persistent conversation history, task results, and user facts.
Saves to JSON file in BACKEND/data/ directory.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("aeris.memory")


def is_sensitive(text: str) -> bool:
    """Check if the text contains long character sequences or key patterns representing secrets."""
    sensitive_patterns = [
        r"(?i)(key|password|token|secret|credential|auth|passphrase|private)\s*[:=]\s*[a-zA-Z0-9_\-\.]{10,}",
        r"[a-fA-F0-9]{32,}",  # MD5 or hex keys
        r"[a-zA-Z0-9_\-\.]{40,}", # long key tokens
    ]
    for pattern in sensitive_patterns:
        if re.search(pattern, text):
            return True
    return False


class MemoryStore:
    """Store and retrieve conversation history, task results, and agentic memory state."""

    def __init__(self, max_history: int = 100):
        self.max_history = max_history
        self.chat_history: list[dict] = []
        self.task_results: dict[str, dict] = {}
        self.short_term_summary: str = ""
        self.long_term_facts: list[str] = []
        self.project_memory: dict[str, Any] = {}
        self.vector_hooks: list[dict] = []
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

    # ─── New Memory Layer Methods ─────────────────────────────────────

    def add_fact(self, fact: str) -> bool:
        """Add a long-term user fact, avoiding duplicates and sensitive info."""
        if not fact or not isinstance(fact, str):
            return False
        fact = fact.strip()
        if is_sensitive(fact):
            logger.warning("Rejected sensitive fact injection containing potential secrets/keys")
            return False
        if fact not in self.long_term_facts:
            self.long_term_facts.append(fact)
            self.save()
            return True
        return False

    def remove_fact(self, fact: str) -> bool:
        """Remove a fact by string match or substring match."""
        if not fact:
            return False
        fact = fact.strip().lower()
        original_len = len(self.long_term_facts)
        self.long_term_facts = [f for f in self.long_term_facts if f.strip().lower() != fact]
        # Also support substring removal
        if len(self.long_term_facts) == original_len:
            self.long_term_facts = [f for f in self.long_term_facts if fact not in f.strip().lower()]
        if len(self.long_term_facts) < original_len:
            self.save()
            return True
        return False

    def update_summary(self, summary: str) -> None:
        """Update the short-term chat summary."""
        self.short_term_summary = summary.strip()
        self.save()

    def update_project_memory(self, key: str, value: Any) -> None:
        """Update metadata about projects."""
        self.project_memory[key] = value
        self.save()

    def add_vector_hook(self, name: str, payload: dict) -> None:
        """Add a hook for future vector index indexing."""
        self.vector_hooks.append({
            "name": name,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self.save()

    def search_facts(self, query: str) -> list[str]:
        """Simulate vector search memory hook via keyword/substring search."""
        if not query:
            return []
        query_words = query.lower().split()
        matches = []
        for fact in self.long_term_facts:
            fact_lower = fact.lower()
            score = sum(1 for word in query_words if word in fact_lower)
            if score > 0:
                matches.append((score, fact))
        matches.sort(key=lambda x: x[0], reverse=True)
        return [m[1] for m in matches]

    def get_memory_context(self) -> str:
        """Get formatted memory context to inject into prompt."""
        parts = []
        if self.short_term_summary:
            parts.append(f"Short-term Chat Summary:\n{self.short_term_summary}")
        if self.long_term_facts:
            facts_str = "\n".join(f"- {fact}" for fact in self.long_term_facts)
            parts.append(f"Long-term User Facts:\n{facts_str}")
        if self.project_memory:
            proj_str = "\n".join(f"- {k}: {v}" for k, v in self.project_memory.items())
            parts.append(f"Project Memory:\n{proj_str}")
        return "\n\n".join(parts)

    def clear_history(self) -> None:
        """Clear all chat history."""
        self.chat_history = []
        self.save()
        logger.info("Chat history cleared")

    def clear_all(self) -> None:
        """Clear everything."""
        self.chat_history = []
        self.task_results = {}
        self.short_term_summary = ""
        self.long_term_facts = []
        self.project_memory = {}
        self.vector_hooks = []
        self.save()
        logger.info("All memory cleared")

    def save(self) -> None:
        """Persist memory to disk."""
        try:
            data = {
                "chat_history": self.chat_history,
                "task_results": self.task_results,
                "short_term_summary": self.short_term_summary,
                "long_term_facts": self.long_term_facts,
                "project_memory": self.project_memory,
                "vector_hooks": self.vector_hooks,
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
                self.short_term_summary = data.get("short_term_summary", "")
                self.long_term_facts = data.get("long_term_facts", [])
                self.project_memory = data.get("project_memory", {})
                self.vector_hooks = data.get("vector_hooks", [])
                logger.info(f"Loaded memory: {len(self.chat_history)} messages, {len(self.long_term_facts)} facts")
            else:
                logger.info("No existing memory file — starting fresh")
        except Exception as e:
            logger.error(f"Failed to load memory: {e}")
            self.chat_history = []
            self.task_results = {}
            self.short_term_summary = ""
            self.long_term_facts = []
            self.project_memory = {}
            self.vector_hooks = []

    def __repr__(self) -> str:
        return f"<MemoryStore: {len(self.chat_history)} messages, {len(self.long_term_facts)} facts>"


# Global singleton
memory_store = MemoryStore()
