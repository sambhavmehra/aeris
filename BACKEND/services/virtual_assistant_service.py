"""
AERIS AI OS - Virtual Assistant Technology Service
Provides assistant-wide capabilities: speech output integration, user
interaction logging, history tracking, and smart personalized recommendations.
"""
import os
import json
import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger("aeris.services.assistant")


class VirtualAssistantService:
    """Service wrapping conversational interaction loggers and personalization logic."""

    def __init__(self):
        self.backend_dir = Path(__file__).resolve().parent.parent
        self.log_file = self.backend_dir / "data" / "assistant_interactions.json"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self._save_logs([])

    def _load_logs(self) -> List[Dict[str, Any]]:
        try:
            if self.log_file.exists():
                with open(self.log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load assistant interaction logs: {e}")
        return []

    def _save_logs(self, logs: List[Dict[str, Any]]):
        try:
            with open(self.log_file, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save assistant interaction logs: {e}")

    def speak(self, text: str) -> Dict[str, Any]:
        """Trigger text-to-speech (TTS) announcement."""
        try:
            # Try lazy import of speech engine
            from services.texttospeech import speak_async
            speak_async(text)
            return {"success": True, "output": f"TTS announcement triggered: '{text}'"}
        except Exception as e:
            logger.warning(f"Speech synthesizer unavailable: {e}")
            return {"success": False, "error": str(e)}

    def log_interaction(self, user_query: str, assistant_response: str) -> Dict[str, Any]:
        """Record a conversation turn for behavior logging and personalized ML."""
        try:
            logs = self._load_logs()
            from datetime import datetime
            
            new_log = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "query": user_query,
                "response": assistant_response
            }
            logs.append(new_log)
            # Limit logs to last 100 entries
            self._save_logs(logs[-100:])
            return {"success": True, "logged_turn": new_log}
        except Exception as e:
            logger.error(f"Failed to log interaction: {e}")
            return {"success": False, "error": str(e)}

    def get_personalized_recommendations(self) -> Dict[str, Any]:
        """
        Analyze user queries/behavior history and return personalized ML recommendations.
        """
        logs = self._load_logs()
        if not logs:
            return {
                "success": True,
                "recommendation": "Welcome to AERIS! Try asking me to summarize a YouTube video, generate a diagram, or search files.",
                "reason": "No interaction history available."
            }

        # Analyze keywords in history
        queries = [l.get("query", "").lower() for l in logs]
        
        system_queries = sum(1 for q in queries if any(w in q for w in ["system", "cpu", "ram", "battery", "monitor"]))
        code_queries = sum(1 for q in queries if any(w in q for w in ["code", "build", "project", "python", "clock", "calculator"]))
        search_queries = sum(1 for q in queries if any(w in q for w in ["search", "find", "google", "youtube", "dork"]))

        if system_queries >= max(code_queries, search_queries, 1):
            rec = "Sir, since you frequently monitor system health, I recommend scheduling a recurring task using 'schedule_execution' to alert you if CPU goes above 90%."
            reason = "Frequent system monitoring queries detected."
        elif code_queries >= max(system_queries, search_queries, 1):
            rec = "Sir, I see you are developing codebases. I recommend using the coding agent integration with Antigravity IDE to bootstrap frameworks natively."
            reason = "Frequent software development commands detected."
        elif search_queries >= max(system_queries, code_queries, 1):
            rec = "Sir, you perform extensive research. I recommend using the 'web_research' tool with depth='comprehensive' for deep-dive analysis."
            reason = "Frequent search or OSINT queries detected."
        else:
            rec = "Sir, I recommend trying the new data analytics tools ('analytics_summarize_csv') or cloud simulated storage bucket commands to boost your workflow!"
            reason = "General assistant usage."

        return {
            "success": True,
            "recommendation": rec,
            "reason": reason,
            "total_turns_analyzed": len(logs)
        }


# Singleton instance
assistant_service = VirtualAssistantService()
