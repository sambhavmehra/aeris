import logging
import asyncio
import io
import struct
from typing import Optional, AsyncGenerator
from config import settings

logger = logging.getLogger("aeris.voice_stream")

# Constants for incoming audio (from frontend mic)
IN_SAMPLE_RATE = 16000
IN_CHANNELS = 1

# Constants for outgoing audio (to frontend speaker)
OUT_SAMPLE_RATE = 24000
OUT_CHANNELS = 1
BATCH_THRESHOLD = 6000

def is_silent(pcm_data: bytes, threshold: int = 500) -> bool:
    """Check if a PCM audio buffer is silent based on peak amplitude."""
    count = len(pcm_data) // 2
    if count == 0:
        return True
    try:
        shorts = struct.unpack(f"{count}h", pcm_data)
        max_val = max(abs(s) for s in shorts)
        return max_val < threshold
    except Exception as e:
        logger.warning(f"Error unpacking PCM data: {e}")
        return True

async def transcribe_audio(audio_bytes: bytes) -> Optional[str]:
    """Transcribe raw PCM 16kHz mono audio bytes using Groq Whisper, falling back to Gemini."""
    if not audio_bytes or len(audio_bytes) < 3200: # Less than 100ms of audio
        return None

    # Wrap raw PCM in a simple WAV container so APIs can parse it
    wav_io = io.BytesIO()
    import wave
    with wave.open(wav_io, "wb") as wav_file:
        wav_file.setnchannels(IN_CHANNELS)
        wav_file.setsampwidth(2) # 16-bit
        wav_file.setframerate(IN_SAMPLE_RATE)
        wav_file.writeframes(audio_bytes)
    wav_bytes = wav_io.getvalue()

    # Try Groq Whisper first (extremely low latency)
    if settings.has_groq:
        try:
            from groq import AsyncGroq
            client = AsyncGroq(api_key=settings.GROQ_API_KEYS[0])
            
            # Groq SDK expects a tuple of (filename, file-like object, mime-type)
            response = await client.audio.transcriptions.create(
                file=("speech.wav", wav_bytes, "audio/wav"),
                model="whisper-large-v3-turbo",
                response_format="json",
            )
            text = response.text.strip() if response.text else ""
            if text:
                logger.info(f"Groq Whisper transcribed: '{text}'")
                return text
        except Exception as e:
            logger.warning(f"Groq Whisper transcription failed: {e}")

    # Fallback to Gemini (multimodal audio upload)
    if settings.has_gemini:
        client = None
        try:
            from google import genai
            from google.genai import types
            
            # Use generation client to transcribe
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            loop = asyncio.get_event_loop()
            
            def _gemini_transcribe():
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=[
                        types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                        "Please transcribe this audio. Respond ONLY with the transcription text, no extra explanations."
                    ]
                )
                return response.text.strip() if response.text else ""
                
            text = await loop.run_in_executor(None, _gemini_transcribe)
            if text:
                logger.info(f"Gemini transcribed fallback: '{text}'")
                return text
        except Exception as e:
            logger.error(f"Gemini fallback transcription failed: {e}")
        finally:
            if client is not None:
                try:
                    if hasattr(client, "_api_client") and hasattr(client._api_client, "_async_httpx_client"):
                        async_client = client._api_client._async_httpx_client
                        if async_client:
                            await async_client.aclose()
                except Exception as e:
                    logger.warning(f"Failed to close internal async client in voice_stream: {e}")


    return None

async def generate_voice_pcm(
    text: str, 
    voice: str = "hi-IN-MadhurNeural", 
    pitch: str = "+5Hz", 
    rate: str = "+13%"
) -> AsyncGenerator[bytes, None]:
    """Stream audio from Edge-TTS and yield decoded PCM chunks."""
    import edge_tts
    from services.texttospeech import _decode_mp3_to_pcm

    communicate = edge_tts.Communicate(text, voice, pitch=pitch, rate=rate)
    accumulated = bytearray()

    try:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                accumulated.extend(chunk["data"])
                if len(accumulated) >= BATCH_THRESHOLD:
                    # Decode MP3 buffer to raw PCM 24kHz mono
                    pcm = _decode_mp3_to_pcm(bytes(accumulated))
                    if pcm:
                        yield pcm
                    accumulated.clear()
                    
        # Flush remaining chunks
        if accumulated:
            pcm = _decode_mp3_to_pcm(bytes(accumulated))
            if pcm:
                yield pcm
    except Exception as e:
        logger.error(f"Edge-TTS streaming generator failed: {e}")
