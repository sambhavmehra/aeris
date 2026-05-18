"""
AERIS Automation Package — OS and hardware interaction.

Active modules:
  - system_automation  : App lifecycle, media, search, screenshots, system controls
  - computer_use       : PyAutoGUI-based screen interaction with AI Vision
  - command_automation  : Smart shell command execution
  - navigation_engine   : Google Maps navigation
  - workflow_engine      : Task workflow automation

NOTE: automation.py is LEGACY / DEPRECATED — use system_automation.py instead.
"""
from .system_automation import (
    execute_decision,
    open_app,
    close_app,
    play_youtube,
    play_on_youtube_visible,
    google_search,
    youtube_search,
    app_search,
    system_control,
    take_screenshot,
    youtube_control,
    media_control,
    browser_control,
)

__all__ = [
    "execute_decision",
    "open_app",
    "close_app",
    "play_youtube",
    "play_on_youtube_visible",
    "google_search",
    "youtube_search",
    "app_search",
    "system_control",
    "take_screenshot",
    "youtube_control",
    "media_control",
    "browser_control",
]
