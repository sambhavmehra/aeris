"""
AERIS User Profile Store — Manages and persists user preferences.
Saves to user_profile.json in the data directory.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from config import settings

logger = logging.getLogger("aeris.user_profile")


class UserProfileStore:
    """Store and retrieve user personalization configurations."""

    def __init__(self):
        self._file_path = settings.DATA_DIR / "user_profile.json"
        self.profile: Dict[str, Any] = {
            "name": settings.USERNAME,
            "language_preference": "Hinglish",
            "tone_preference": "natural agentic",
            "common_tasks": [],
            "preferred_response_style": "natural, brief, helpful, using code blocks where necessary",
            "hacker_mode": False,
        }
        self.load()

    def get_profile(self) -> Dict[str, Any]:
        """Return the current user profile configuration."""
        return self.profile

    def update_profile(self, **kwargs) -> Dict[str, Any]:
        """Update fields in the user profile and save."""
        for key, val in kwargs.items():
            if key in self.profile:
                self.profile[key] = val
        self.save()
        return self.profile

    def save(self) -> None:
        """Persist profile to disk."""
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(json.dumps(self.profile, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save user profile: {e}")

    def load(self) -> None:
        """Load user profile from disk or save default if none exists."""
        try:
            if self._file_path.exists():
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
                for key, val in data.items():
                    self.profile[key] = val
                logger.info("Loaded user profile successfully")
            else:
                self.save()
                logger.info("No existing user profile — created default profile")
        except Exception as e:
            logger.error(f"Failed to load user profile: {e}")


# Global singleton
user_profile_store = UserProfileStore()
