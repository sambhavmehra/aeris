"""
AERIS Voice Orchestrator
=========================
Lightweight voice pipeline that connects frontend STT to the AERIS Brain.

Architecture (vs Sharva):
  - NO Selenium / headless Chrome (STT is handled in the React frontend)
  - NO mtranslate dependency (Brain understands Hindi/Hinglish natively)
  - Direct Brain.process() integration for ultra-fast routing
  - Echo guard prevents mic feedback when TTS is playing

Flow:
  Frontend mic (Web Speech API) --> POST /api/voice/process
    --> VoiceOrchestrator.process_voice(transcript)
      --> brain.process(transcript)
      --> speak_async(response)
    --> JSON response to frontend
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("aeris.voice")


# ---------------------------------------------------------------------------
#  Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class VoiceResult:
    transcript: str
    intent: str
    response_text: str
    success: bool
    spoken: bool = False
    execution_time: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "intent": self.intent,
            "response_text": self.response_text,
            "success": self.success,
            "spoken": self.spoken,
            "execution_time": self.execution_time,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
#  Echo guard helper
# ---------------------------------------------------------------------------
def _is_tts_active() -> bool:
    """Check if AERIS TTS is currently playing (prevents echo feedback)."""
    try:
        from services.texttospeech import is_currently_speaking
        return is_currently_speaking()
    except Exception:
        return False


# ---------------------------------------------------------------------------
#  Voice Orchestrator
# ---------------------------------------------------------------------------
class VoiceOrchestrator:
    """
    Stateless voice command processor for AERIS.

    Usage:
        orchestrator = VoiceOrchestrator()
        result = await orchestrator.process_voice("open chrome")
    """

    def __init__(self) -> None:
        self._brain = None

    def _get_brain(self):
        """Lazy import to avoid circular imports at module load time."""
        if self._brain is None:
            try:
                from brain import brain
                self._brain = brain
                logger.info("VoiceOrchestrator: Brain connected.")
            except Exception as e:
                logger.error(f"VoiceOrchestrator: Brain import failed: {e}")
        return self._brain

    async def process_voice(
        self,
        transcript: str,
        speak_response: bool = True,
    ) -> VoiceResult:
        """
        Process a voice command transcript end-to-end.

        Parameters
        ----------
        transcript : str
            The recognised text from frontend Web Speech API.
        speak_response : bool
            If True, automatically speak the brain's response via TTS.

        Returns
        -------
        VoiceResult with intent, response, and whether TTS was triggered.
        """
        transcript = (transcript or "").strip()
        if not transcript:
            return VoiceResult(
                transcript="",
                intent="unknown",
                response_text="",
                success=False,
                error="Empty transcript",
            )

        # -- Echo guard: drop if AERIS is currently speaking --
        if _is_tts_active():
            logger.info(
                f"VoiceOrchestrator: TTS active, dropping input: "
                f"{transcript[:50]}"
            )
            return VoiceResult(
                transcript=transcript,
                intent="echo_blocked",
                response_text="",
                success=False,
                error="TTS is active, input dropped to prevent echo",
            )

        # -- Route through AERIS Brain --
        start = time.time()
        brain = self._get_brain()

        if not brain:
            return VoiceResult(
                transcript=transcript,
                intent="error",
                response_text="Sir, voice system is not ready yet.",
                success=False,
                error="Brain not available",
            )

        try:
            result = await brain.process(transcript)
            elapsed = round(time.time() - start, 2)

            response_text = result.get("response", "")
            intent = result.get("intent", "chat")
            success = result.get("success", True)

            # -- Speak response (non-blocking) --
            spoken = False
            if speak_response and response_text:
                try:
                    from services.texttospeech import speak_async
                    speak_async(response_text)
                    spoken = True
                except Exception as e:
                    logger.warning(f"VoiceOrchestrator: TTS failed: {e}")

            return VoiceResult(
                transcript=transcript,
                intent=intent,
                response_text=response_text,
                success=success,
                spoken=spoken,
                execution_time=elapsed,
            )

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            logger.error(f"VoiceOrchestrator: Brain processing failed: {e}")
            error_msg = f"Sir, voice command mein error aaya: {e}"

            # Try to speak the error
            if speak_response:
                try:
                    from services.texttospeech import speak_async
                    speak_async("Sir, command process karne mein error aaya.")
                except Exception:
                    pass

            return VoiceResult(
                transcript=transcript,
                intent="error",
                response_text=error_msg,
                success=False,
                execution_time=elapsed,
                error=str(e),
            )


# ---------------------------------------------------------------------------
#  Global singleton
# ---------------------------------------------------------------------------
_voice_orchestrator: Optional[VoiceOrchestrator] = None


def get_voice_orchestrator() -> VoiceOrchestrator:
    global _voice_orchestrator
    if _voice_orchestrator is None:
        _voice_orchestrator = VoiceOrchestrator()
    return _voice_orchestrator
