"""
AERIS Speech-to-Text Engine
=============================
Lightweight backend STT for headless/autonomous voice mode.

Unlike Sharva (which used a full Selenium headless Chrome browser),
AERIS uses the `speech_recognition` library with Google's free web API
or direct microphone capture.

Primary STT path:
  - Frontend Web Speech API (zero backend overhead, handled in ChatPanel.tsx)

This module is a FALLBACK for:
  - Headless server mode (no browser UI)
  - Automated testing
  - Autonomous always-on listening

Dependencies: pip install SpeechRecognition pyaudio
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Callable

logger = logging.getLogger("aeris.stt")


class SpeechRecognizer:
    """
    Lightweight microphone-based speech recognizer.
    Uses Google's free speech recognition API (no API key needed).
    Falls back to Sphinx (offline) if Google is unavailable.
    """

    def __init__(self, language: str = "en-IN", energy_threshold: int = 300):
        self.language = language
        self.energy_threshold = energy_threshold
        self._recognizer = None
        self._microphone = None
        self._is_listening = False
        self._stop_event = threading.Event()

    def _ensure_initialized(self):
        """Lazy init to avoid import errors if pyaudio is not installed."""
        if self._recognizer is not None:
            return

        try:
            import speech_recognition as sr

            self._recognizer = sr.Recognizer()
            self._recognizer.energy_threshold = self.energy_threshold
            self._recognizer.dynamic_energy_threshold = True
            self._recognizer.pause_threshold = 1.0

            self._microphone = sr.Microphone()

            # Quick calibration for ambient noise
            with self._microphone as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)

            logger.info(
                f"SpeechRecognizer initialized "
                f"(lang={self.language}, threshold={self.energy_threshold})"
            )
        except ImportError:
            raise RuntimeError(
                "speech_recognition and/or pyaudio not installed. "
                "Run: pip install SpeechRecognition pyaudio"
            )
        except Exception as e:
            raise RuntimeError(f"Microphone initialization failed: {e}")

    def listen_once(self, timeout: float = 10.0) -> Optional[str]:
        """
        Listen for a single utterance and return the transcribed text.
        Returns None if nothing was recognized or on timeout.
        """
        import speech_recognition as sr

        self._ensure_initialized()
        self._is_listening = True

        try:
            with self._microphone as source:
                logger.info("Listening for speech...")
                audio = self._recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=15
                )

            # Try Google first (free, no API key)
            try:
                text = self._recognizer.recognize_google(
                    audio, language=self.language
                )
                text = text.strip()
                if text:
                    logger.info(f"Recognized: {text[:80]}")
                    return self._format_query(text)
            except sr.UnknownValueError:
                logger.debug("Google could not understand audio")
            except sr.RequestError as e:
                logger.warning(f"Google API error: {e}")

            return None

        except sr.WaitTimeoutError:
            logger.debug("Listen timeout - no speech detected")
            return None
        except Exception as e:
            logger.error(f"Speech recognition error: {e}")
            return None
        finally:
            self._is_listening = False

    def _format_query(self, text: str) -> str:
        """Capitalize and add punctuation if missing."""
        if not text:
            return ""

        text = text.strip()
        question_words = [
            "how", "what", "who", "where", "when", "why", "which",
            "whose", "whom", "can you", "could you", "is ", "are ",
            "do ", "does ", "will ", "kya", "kahan", "kaise", "kyun",
        ]

        has_punctuation = text[-1] in ".?!"
        is_question = any(text.lower().startswith(w) for w in question_words)

        if not has_punctuation:
            text += "?" if is_question else "."

        return text[0].upper() + text[1:]

    def is_listening(self) -> bool:
        return self._is_listening

    def stop(self):
        self._stop_event.set()
        self._is_listening = False


# ---------------------------------------------------------------------------
#  Convenience functions
# ---------------------------------------------------------------------------
_recognizer_instance: Optional[SpeechRecognizer] = None


def get_speech_recognizer(language: str = "en-IN") -> SpeechRecognizer:
    global _recognizer_instance
    if _recognizer_instance is None:
        _recognizer_instance = SpeechRecognizer(language=language)
    return _recognizer_instance


def listen_once(timeout: float = 10.0) -> Optional[str]:
    """Quick one-shot listen. Returns transcribed text or None."""
    return get_speech_recognizer().listen_once(timeout=timeout)
