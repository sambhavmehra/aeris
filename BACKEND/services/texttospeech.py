"""
AERIS Text-to-Speech Engine — Streaming Edition
=================================================
High-quality TTS using Edge-TTS (Microsoft Neural voices) with TRUE
streaming playback via PyAudio + miniaudio MP3 decode.

Key architecture differences vs the old pygame version:
  - Audio chunks are decoded and played THE MOMENT they arrive from
    Edge-TTS, eliminating the wait-for-full-download bottleneck.
  - miniaudio decodes MP3→PCM natively (no ffmpeg needed).
  - A persistent background asyncio loop avoids per-call event-loop
    creation overhead.
  - PyAudio streams raw PCM, so there's no file I/O and no temp files.
  - threading.Event() for instant stop (unchanged).
  - Echo cooldown guard to prevent mic feedback loops (unchanged).
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
import threading
import time
from typing import Optional

logger = logging.getLogger("aeris.tts")

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
DEFAULT_VOICE = "hi-IN-MadhurNeural"
_ECHO_COOLDOWN = 3.5  # seconds after TTS ends before mic should resume

# PyAudio stream parameters — we resample everything to 24kHz mono 16-bit
_PA_RATE = 24000
_PA_CHANNELS = 1
_PA_WIDTH = 2  # 16-bit = 2 bytes
_FRAME_SIZE = 2048  # PCM bytes per write (keeps stop_event responsive)

# How many MP3 bytes to accumulate before attempting a decode+play batch.
# Smaller = lower latency (first sound sooner), but more decode overhead.
_BATCH_THRESHOLD = 6_000  # ~6 KB ≈ 0.3s of MP3 audio

# ---------------------------------------------------------------------------
#  Global state (memory-based, no file I/O)
# ---------------------------------------------------------------------------
_stop_event = threading.Event()
_is_speaking = False
_last_spoke_at: float = 0.0

# ---------------------------------------------------------------------------
#  Persistent asyncio loop (runs in a daemon thread)
# ---------------------------------------------------------------------------
_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_loop_lock = threading.Lock()


def _get_bg_loop() -> asyncio.AbstractEventLoop:
    """Return a long-lived asyncio event loop running in a daemon thread."""
    global _bg_loop
    if _bg_loop is not None and _bg_loop.is_running():
        return _bg_loop
    with _bg_loop_lock:
        if _bg_loop is not None and _bg_loop.is_running():
            return _bg_loop
        _bg_loop = asyncio.new_event_loop()
        t = threading.Thread(
            target=_bg_loop.run_forever,
            daemon=True,
            name="aeris-tts-loop",
        )
        t.start()
        logger.info("Persistent TTS asyncio loop started")
        return _bg_loop


# ---------------------------------------------------------------------------
#  Lazy PyAudio init
# ---------------------------------------------------------------------------
_pa_instance = None
_pa_lock = threading.Lock()


def _get_pyaudio():
    global _pa_instance
    if _pa_instance is not None:
        return _pa_instance
    with _pa_lock:
        if _pa_instance is not None:
            return _pa_instance
        import pyaudio
        _pa_instance = pyaudio.PyAudio()
        logger.info("PyAudio initialized")
        return _pa_instance


# ---------------------------------------------------------------------------
#  MP3 → raw PCM decode via miniaudio (no ffmpeg needed)
# ---------------------------------------------------------------------------
def _decode_mp3_to_pcm(mp3_bytes: bytes) -> Optional[bytes]:
    """Decode MP3 bytes to 24kHz mono signed-16-bit PCM using miniaudio."""
    try:
        import miniaudio
        # decode() returns a DecodedSoundFile with .samples (array of int16)
        decoded = miniaudio.decode(
            mp3_bytes,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=_PA_CHANNELS,
            sample_rate=_PA_RATE,
        )
        return decoded.samples.tobytes()
    except Exception as e:
        logger.debug(f"miniaudio decode failed (may be partial chunk): {e}")
        return None


# ---------------------------------------------------------------------------
#  Core streaming playback
# ---------------------------------------------------------------------------
async def _stream_and_play(text: str, voice: str) -> bool:
    """
    Stream audio from Edge-TTS and play chunks in real-time via PyAudio.
    Audio starts as soon as the first usable batch is decoded.
    """
    global _is_speaking, _last_spoke_at
    import edge_tts
    import pyaudio

    _stop_event.clear()
    _is_speaking = True

    pa = _get_pyaudio()
    stream = None
    accumulated = bytearray()
    played_any = False

    try:
        communicate = edge_tts.Communicate(text, voice, pitch="+5Hz", rate="+13%")

        async for chunk in communicate.stream():
            if _stop_event.is_set():
                logger.info("TTS stopped by stop_event (during stream)")
                break

            if chunk["type"] == "audio":
                accumulated.extend(chunk["data"])

                if len(accumulated) >= _BATCH_THRESHOLD:
                    pcm = _decode_mp3_to_pcm(bytes(accumulated))
                    if pcm:
                        if stream is None:
                            stream = pa.open(
                                format=pyaudio.paInt16,
                                channels=_PA_CHANNELS,
                                rate=_PA_RATE,
                                output=True,
                                frames_per_buffer=1024,
                            )
                        for i in range(0, len(pcm), _FRAME_SIZE):
                            if _stop_event.is_set():
                                break
                            await asyncio.to_thread(stream.write, pcm[i : i + _FRAME_SIZE])
                        played_any = True
                        accumulated.clear()

        # Flush remaining audio
        if accumulated and not _stop_event.is_set():
            pcm = _decode_mp3_to_pcm(bytes(accumulated))
            if pcm:
                if stream is None:
                    stream = pa.open(
                        format=pyaudio.paInt16,
                        channels=_PA_CHANNELS,
                        rate=_PA_RATE,
                        output=True,
                        frames_per_buffer=1024,
                    )
                for i in range(0, len(pcm), _FRAME_SIZE):
                    if _stop_event.is_set():
                        break
                    await asyncio.to_thread(stream.write, pcm[i : i + _FRAME_SIZE])
                played_any = True

        return played_any

    except Exception as e:
        logger.error(f"Streaming TTS error: {e}")
        return False
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        _last_spoke_at = time.time()
        _is_speaking = False


# ---------------------------------------------------------------------------
#  Fallback: full-buffer playback via pygame
# ---------------------------------------------------------------------------
_pygame_initialized = False


async def _buffer_and_play_pygame(text: str, voice: str) -> bool:
    """
    Fallback: download full audio → play via pygame.
    Used only if PyAudio/miniaudio streaming fails entirely.
    """
    global _is_speaking, _last_spoke_at, _pygame_initialized
    import edge_tts

    _stop_event.clear()
    _is_speaking = True

    try:
        audio_buf = io.BytesIO()
        communicate = edge_tts.Communicate(text, voice, pitch="+5Hz", rate="+13%")
        async for chunk in communicate.stream():
            if _stop_event.is_set():
                return False
            if chunk["type"] == "audio":
                audio_buf.write(chunk["data"])

        if audio_buf.tell() == 0:
            return False

        audio_buf.seek(0)

        import pygame
        if not _pygame_initialized:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=256)
            _pygame_initialized = True

        pygame.mixer.music.load(audio_buf)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            if _stop_event.is_set():
                pygame.mixer.music.stop()
                break
            await asyncio.sleep(0.1)
        return True

    except Exception as e:
        logger.error(f"Pygame fallback error: {e}")
        return False
    finally:
        _last_spoke_at = time.time()
        _is_speaking = False


# ---------------------------------------------------------------------------
#  Language detection (simple heuristic)
# ---------------------------------------------------------------------------
def _detect_language(text: str) -> str:
    hindi_chars = set(
        "अआइईउऊएऐओऔकखगघचछजझटठडढणतथदधनपफबभमयरलवशषसहािीुूेैोौंःँ"
    )
    if any(c in hindi_chars for c in text):
        return "hi"
    return "en"


# ---------------------------------------------------------------------------
#  Completion responses (for long texts, speak only a summary)
# ---------------------------------------------------------------------------
_COMPLETION_RESPONSES = [
    "The rest of the result is on the chat screen, Sir.",
    "Full details are in the chat window, Sir.",
    "Check the chat for the complete response, Sir.",
    "Complete output is in the chat panel, Sir.",
]


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------
def text_to_speech(
    text: str,
    voice: str = DEFAULT_VOICE,
    max_spoken_sentences: int = 3,
    max_spoken_chars: int = 300,
) -> bool:
    """
    Speak text using Edge-TTS with streaming PyAudio playback.
    Long responses are truncated to keep speech short and snappy.
    Returns True if speech completed, False on error.
    """
    if not text or not text.strip():
        return False

    # Truncate long responses for snappy speech
    sentences = [s.strip() for s in text.replace("!", ".").split(".") if s.strip()]
    if len(sentences) > max_spoken_sentences or len(text) > max_spoken_chars:
        spoken_text = (
            ". ".join(sentences[:max_spoken_sentences])
            + ". "
            + random.choice(_COMPLETION_RESPONSES)
        )
    else:
        spoken_text = text

    loop = _get_bg_loop()

    try:
        # Primary: streaming PyAudio playback (lowest latency)
        future = asyncio.run_coroutine_threadsafe(
            _stream_and_play(spoken_text, voice), loop
        )
        result = future.result(timeout=120)
        if result:
            return True

        # Fallback: pygame buffer playback
        logger.info("Streaming playback returned False, trying pygame fallback")
        future = asyncio.run_coroutine_threadsafe(
            _buffer_and_play_pygame(spoken_text, voice), loop
        )
        return future.result(timeout=120)

    except Exception as e:
        logger.exception("TTS pipeline error:")
        return False


def speak_async(text: str, voice: str = DEFAULT_VOICE) -> None:
    """Non-blocking wrapper: fires TTS in a daemon thread."""
    t = threading.Thread(
        target=text_to_speech,
        args=(text, voice),
        daemon=True,
        name="aeris-tts",
    )
    t.start()


def stop_speaking() -> None:
    """Instantly signal TTS to stop playback."""
    _stop_event.set()
    logger.info("TTS stop requested")


def is_currently_speaking() -> bool:
    """
    Returns True while AERIS is playing TTS audio OR within the echo
    cooldown period (prevents mic from picking up AERIS's own voice).
    """
    if _is_speaking:
        return True
    if (time.time() - _last_spoke_at) < _ECHO_COOLDOWN:
        return True
    return False
