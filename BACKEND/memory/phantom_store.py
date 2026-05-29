"""
PhantomTrace Memory Store — Persistent JSON storage for ethical link analytics.
Saves to BACKEND/data/phantom_links.json
"""

import json
import hashlib
import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger("aeris.phantom_store")


class PhantomStore:
    """Consent-based link analytics storage engine."""

    def __init__(self):
        self._file_path = settings.DATA_DIR / "phantom_links.json"
        self._data: dict = {"links": {}}
        self.load()

    # ── Persistence ────────────────────────────────────────────────

    def load(self) -> None:
        try:
            if self._file_path.exists():
                self._data = json.loads(
                    self._file_path.read_text(encoding="utf-8")
                )
        except Exception as e:
            logger.error(f"Failed to load phantom store: {e}")
            self._data = {"links": {}}

    def save(self) -> None:
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(
                json.dumps(self._data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save phantom store: {e}")

    # ── Link CRUD ──────────────────────────────────────────────────

    def create_link(self, target_url: str) -> dict:
        """Create a new tracked analytics link."""
        link_id = uuid.uuid4().hex[:8]
        entry = {
            "link_id": link_id,
            "target_url": target_url,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "visits": [],
            "active": True,
        }
        self._data["links"][link_id] = entry
        self.save()
        return entry

    def log_visit(
        self,
        link_id: str,
        ip: str,
        user_agent: str,
        referrer: str = "",
        geo: Optional[dict] = None,
    ) -> bool:
        """Record a visit against a tracked link. IP is hashed for privacy."""
        if link_id not in self._data["links"]:
            return False

        link = self._data["links"][link_id]
        if not link.get("active", True):
            return False

        # Hash IP for privacy — no raw IPs ever stored
        ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]
        visit = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "ip_hash": ip_hash,
            "user_agent": user_agent,
            "referrer": referrer,
            "geo": geo or {},
        }
        link["visits"].append(visit)
        self.save()
        return True

    def get_stats(self, link_id: str) -> Optional[dict]:
        """Return full stats for a specific tracked link."""
        link = self._data["links"].get(link_id)
        if not link:
            return None
        unique_visitors = len(set(v["ip_hash"] for v in link["visits"]))
        return {
            **link,
            "total_visits": len(link["visits"]),
            "unique_visitors": unique_visitors,
        }

    def list_links(self) -> list:
        """Return a summary list of all tracked links."""
        return [
            {
                "link_id": lid,
                "target_url": data["target_url"],
                "created_at": data["created_at"],
                "total_visits": len(data["visits"]),
                "active": data.get("active", True),
            }
            for lid, data in self._data["links"].items()
        ]

    def delete_link(self, link_id: str) -> bool:
        """Soft-delete a tracked link (marks inactive, keeps data)."""
        if link_id in self._data["links"]:
            self._data["links"][link_id]["active"] = False
            self.save()
            return True
        return False

    def get_target_url(self, link_id: str) -> Optional[str]:
        """Resolve a link_id to the original target URL (only if active)."""
        link = self._data["links"].get(link_id)
        if link and link.get("active", True):
            return link["target_url"]
        return None


# ── Module-level singleton ─────────────────────────────────────────
phantom_store = PhantomStore()
