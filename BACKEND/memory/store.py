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
        
        # Internal fields for Normal Mode
        self._normal_chat_history: list[dict] = []
        self._normal_task_results: dict[str, dict] = {}
        self._normal_short_term_summary: str = ""
        self._normal_long_term_facts: list[str] = []
        self._normal_project_memory: dict[str, Any] = {}
        self._normal_vector_hooks: list[dict] = []
        
        # Internal fields for Hacker Mode
        self._hacker_chat_history: list[dict] = []
        self._hacker_task_results: dict[str, dict] = {}
        self._hacker_short_term_summary: str = ""
        self._hacker_long_term_facts: list[str] = []
        self._hacker_project_memory: dict[str, Any] = {}
        self._hacker_vector_hooks: list[dict] = []

        self._normal_file_path = settings.DATA_DIR / "memory.json"
        self._hacker_file_path = settings.DATA_DIR / "hacker_memory.json"

        # Load existing data
        self.load()

    @property
    def is_hacker_mode(self) -> bool:
        try:
            from memory.user_profile import user_profile_store
            return user_profile_store.get_profile().get("hacker_mode", False)
        except Exception:
            return False

    @property
    def chat_history(self) -> list[dict]:
        return self._hacker_chat_history if self.is_hacker_mode else self._normal_chat_history

    @chat_history.setter
    def chat_history(self, val: list[dict]):
        if self.is_hacker_mode:
            self._hacker_chat_history = val
        else:
            self._normal_chat_history = val

    @property
    def task_results(self) -> dict[str, dict]:
        return self._hacker_task_results if self.is_hacker_mode else self._normal_task_results

    @task_results.setter
    def task_results(self, val: dict[str, dict]):
        if self.is_hacker_mode:
            self._hacker_task_results = val
        else:
            self._normal_task_results = val

    @property
    def short_term_summary(self) -> str:
        return self._hacker_short_term_summary if self.is_hacker_mode else self._normal_short_term_summary

    @short_term_summary.setter
    def short_term_summary(self, val: str):
        if self.is_hacker_mode:
            self._hacker_short_term_summary = val
        else:
            self._normal_short_term_summary = val

    @property
    def long_term_facts(self) -> list[str]:
        return self._hacker_long_term_facts if self.is_hacker_mode else self._normal_long_term_facts

    @long_term_facts.setter
    def long_term_facts(self, val: list[str]):
        if self.is_hacker_mode:
            self._hacker_long_term_facts = val
        else:
            self._normal_long_term_facts = val

    @property
    def project_memory(self) -> dict[str, Any]:
        return self._hacker_project_memory if self.is_hacker_mode else self._normal_project_memory

    @project_memory.setter
    def project_memory(self, val: dict[str, Any]):
        if self.is_hacker_mode:
            self._hacker_project_memory = val
        else:
            self._normal_project_memory = val

    @property
    def vector_hooks(self) -> list[dict]:
        return self._hacker_vector_hooks if self.is_hacker_mode else self._normal_vector_hooks

    @vector_hooks.setter
    def vector_hooks(self, val: list[dict]):
        if self.is_hacker_mode:
            self._hacker_vector_hooks = val
        else:
            self._normal_vector_hooks = val

    @property
    def _file_path(self) -> Path:
        return self._hacker_file_path if self.is_hacker_mode else self._normal_file_path

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

    def get_relevant_memory_context(self, query: str, limit: int = 5) -> str:
        """Get formatted memory context filtering for relevant facts to minimize tokens."""
        parts = []
        if self.short_term_summary:
            parts.append(f"Short-term Chat Summary:\n{self.short_term_summary}")
        
        # Memory Retriever: search for relevant facts
        if self.long_term_facts:
            relevant_facts = self.search_facts(query)
            if relevant_facts:
                # Take top `limit` relevant facts
                facts_str = "\n".join(f"- {fact}" for fact in relevant_facts[:limit])
                parts.append(f"Relevant Long-term User Facts:\n{facts_str}")
            else:
                # If no matching facts, we don't inject all of them to save tokens.
                # But if there are very few facts (e.g. <= 5 total), we can inject them anyway.
                if len(self.long_term_facts) <= 5:
                    facts_str = "\n".join(f"- {fact}" for fact in self.long_term_facts)
                    parts.append(f"Long-term User Facts:\n{facts_str}")
                    
        if self.project_memory:
            # Filter project memory based on keywords in query
            query_words = query.lower().split()
            relevant_projects = []
            for k, v in self.project_memory.items():
                k_lower = k.lower()
                v_lower = str(v).lower()
                if any(word in k_lower or word in v_lower for word in query_words):
                    relevant_projects.append(f"- {k}: {v}")
            
            if relevant_projects:
                parts.append(f"Relevant Project Memory:\n" + "\n".join(relevant_projects))
            elif len(self.project_memory) <= 3:
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
            # Save the active mode's data file
            is_hacker = self.is_hacker_mode
            file_path = self._hacker_file_path if is_hacker else self._normal_file_path
            
            data = {
                "chat_history": self._hacker_chat_history if is_hacker else self._normal_chat_history,
                "task_results": self._hacker_task_results if is_hacker else self._normal_task_results,
                "short_term_summary": self._hacker_short_term_summary if is_hacker else self._normal_short_term_summary,
                "long_term_facts": self._hacker_long_term_facts if is_hacker else self._normal_long_term_facts,
                "project_memory": self._hacker_project_memory if is_hacker else self._normal_project_memory,
                "vector_hooks": self._hacker_vector_hooks if is_hacker else self._normal_vector_hooks,
                "last_saved": datetime.now(timezone.utc).isoformat(),
            }
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def load(self) -> None:
        """Load memory from disk for both normal and hacker files."""
        # Load Normal memory
        try:
            if self._normal_file_path.exists():
                data = json.loads(self._normal_file_path.read_text(encoding="utf-8"))
                self._normal_chat_history = data.get("chat_history", [])
                self._normal_task_results = data.get("task_results", {})
                self._normal_short_term_summary = data.get("short_term_summary", "")
                self._normal_long_term_facts = data.get("long_term_facts", [])
                self._normal_project_memory = data.get("project_memory", {})
                self._normal_vector_hooks = data.get("vector_hooks", [])
                logger.info(f"Loaded normal memory: {len(self._normal_chat_history)} messages")
            else:
                logger.info("No existing normal memory file — starting fresh")
        except Exception as e:
            logger.error(f"Failed to load normal memory: {e}")

        # Load Hacker memory
        try:
            if self._hacker_file_path.exists():
                data = json.loads(self._hacker_file_path.read_text(encoding="utf-8"))
                self._hacker_chat_history = data.get("chat_history", [])
                self._hacker_task_results = data.get("task_results", {})
                self._hacker_short_term_summary = data.get("short_term_summary", "")
                self._hacker_long_term_facts = data.get("long_term_facts", [])
                self._hacker_project_memory = data.get("project_memory", {})
                self._hacker_vector_hooks = data.get("vector_hooks", [])
                logger.info(f"Loaded hacker memory: {len(self._hacker_chat_history)} messages")
            else:
                logger.info("No existing hacker memory file — starting fresh")
        except Exception as e:
            logger.error(f"Failed to load hacker memory: {e}")

    def __repr__(self) -> str:
        is_hacker = self.is_hacker_mode
        hist_len = len(self._hacker_chat_history) if is_hacker else len(self._normal_chat_history)
        facts_len = len(self._hacker_long_term_facts) if is_hacker else len(self._normal_long_term_facts)
        mode = "Hacker" if is_hacker else "Normal"
        return f"<MemoryStore ({mode} Mode): {hist_len} messages, {facts_len} facts>"


# Global singleton
memory_store = MemoryStore()
