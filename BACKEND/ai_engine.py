"""
AERIS AI Engine — Unified LLM interface.
Abstracts Groq (fast) and Gemini (reasoning) behind a single API.
Includes automatic key rotation and fallback between providers.
"""

import asyncio
import logging
import os
import random
from typing import Optional

import httpx

from groq import AsyncGroq
from google import genai

from config import settings

logger = logging.getLogger("aeris.ai_engine")


class AIEngine:
    """Unified interface to Groq and Gemini LLMs."""

    def __init__(self):
        # --- Groq clients (one per key for rotation) ---
        self._groq_clients: list[AsyncGroq] = []
        self._groq_index: int = 0
        for key in settings.GROQ_API_KEYS:
            self._groq_clients.append(AsyncGroq(api_key=key, max_retries=0))

        # --- Gemini client ---
        self._gemini_client: Optional[genai.Client] = None
        if settings.has_gemini:
            self._gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

        # --- Cohere (final fallback) ---
        self._cohere_api_key: str = settings.COHERE_API_KEY

        logger.info(
            f"AIEngine initialized — Groq clients: {len(self._groq_clients)}, "
            f"Gemini: {'ready' if self._gemini_client else 'unavailable'}, "
            f"Cohere: {'ready' if self._cohere_api_key else 'unavailable'}"
        )

    # ──────────────────────────── Groq ────────────────────────────

    def _next_groq(self) -> AsyncGroq:
        """Round-robin key rotation across Groq clients."""
        if not self._groq_clients:
            raise RuntimeError("No Groq API keys configured")
        client = self._groq_clients[self._groq_index % len(self._groq_clients)]
        self._groq_index += 1
        return client

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: Optional[dict] = None,
    ) -> str:
        """
        Fast chat completion via Groq.
        Falls back to alternate Groq keys, then to Gemini.
        """
        target_model = model or settings.GROQ_PRIMARY_MODEL

        # Try each Groq key
        last_error = None
        for attempt in range(len(self._groq_clients)):
            try:
                client = self._next_groq()
                if response_format:
                    response = await client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                    )
                else:
                    response = await client.chat.completions.create(
                        model=target_model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                return response.choices[0].message.content or ""
            except Exception as e:
                last_error = e
                logger.warning(f"Groq attempt {attempt+1} failed: {e}")
                # Try fallback model on second attempt
                if attempt == 0 and target_model == settings.GROQ_PRIMARY_MODEL:
                    target_model = settings.GROQ_FALLBACK_MODEL

        # Fallback to Gemini
        logger.info("All Groq attempts exhausted, falling back to Gemini")
        gemini_err = None
        try:
            return await self._gemini_generate(
                self._messages_to_prompt(messages)
            )
        except Exception as ge:
            gemini_err = ge
            logger.warning(f"Gemini fallback failed: {ge}")

        # Fallback to Cohere
        logger.info("Gemini failed, falling back to Cohere Command R+")
        cohere_err = None
        try:
            return await self._cohere_chat(messages, temperature)
        except Exception as ce:
            cohere_err = ce
            logger.warning(f"Cohere fallback failed: {ce}")

        # Final local fallback to Ollama
        logger.info(f"Cohere failed, falling back to local Ollama ({settings.OLLAMA_MODEL})")
        try:
            return await self._ollama_chat(messages, temperature)
        except Exception as ollama_err:
            logger.error(f"Ollama fallback also failed: {ollama_err}")
            raise RuntimeError(
                f"All LLM providers failed. Last Groq error: {last_error}, "
                f"Gemini error: {gemini_err}, Cohere error: {cohere_err}, Ollama error: {ollama_err}"
            )

    # ──────────────────────────── Gemini ────────────────────────────

    async def reason(self, prompt: str, context: str = "") -> str:
        """
        Deep reasoning via Gemini.
        Used for complex analysis — security reports, code gen, etc.
        Falls back to Groq if Gemini unavailable.
        """
        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        try:
            return await self._gemini_generate(full_prompt)
        except Exception as e:
            logger.warning(f"Gemini reason failed: {e}, falling back to Groq")
            return await self.chat([
                {"role": "system", "content": "You are a deep reasoning AI. Think step by step."},
                {"role": "user", "content": full_prompt},
            ])

    async def _gemini_generate(self, prompt: str) -> str:
        """Internal Gemini call wrapper."""
        if not self._gemini_client:
            raise RuntimeError("Gemini API key not configured")

        # google-genai is sync, run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._gemini_client.models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
            ),
        )
        return response.text or ""

    # ──────────────────────────── Classify ────────────────────────────

    async def classify(self, prompt: str, model: Optional[str] = None) -> str:
        """
        Fast intent classification via Groq.
        Returns raw LLM output (caller parses JSON).
        """
        target_model = model or settings.GROQ_FALLBACK_MODEL
        return await self.chat(
            messages=[
                {"role": "system", "content": "You are a precise intent classifier. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            model=target_model,
            temperature=0.1,
            max_tokens=256,
        )

    # ──────────────────────────── Vision ────────────────────────────

    async def vision(self, prompt: str, image_b64: str) -> str:
        """
        Analyze an image using Gemini Vision.
        """
        if not self._gemini_client:
            raise RuntimeError("Gemini API key not configured for Vision")

        try:
            import base64
            image_bytes = base64.b64decode(image_b64)
            
            # Prepare image for Gemini
            loop = asyncio.get_event_loop()
            
            def _call_vision():
                from google.genai import types
                return self._gemini_client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=[
                        prompt,
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                    ]
                )

            response = await loop.run_in_executor(None, _call_vision)
            return response.text or ""
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            raise e

    # ──────────────────────────── Summarize ────────────────────────────

    async def summarize(self, text: str) -> str:
        """Summarize tool outputs or long text via Groq."""
        return await self.chat(
            messages=[
                {"role": "system", "content": "Summarize the following concisely while preserving all key information."},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=1024,
        )

    # ──────────────────────────── Cohere ────────────────────────────

    async def _cohere_chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> str:
        """
        Final-fallback chat via Cohere Command R+.
        Uses the raw HTTP API so no extra pip package is needed.
        """
        if not self._cohere_api_key:
            raise RuntimeError("Cohere API key not configured")

        # Separate system preamble, chat history, and the latest user message
        preamble = ""
        chat_history: list[dict] = []
        user_message = ""

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                preamble += content + "\n"
            elif role == "assistant":
                chat_history.append({"role": "CHATBOT", "message": content})
            elif role == "user":
                # All user messages except the last go into history
                if user_message:  # push previous user msg to history
                    chat_history.append({"role": "USER", "message": user_message})
                user_message = content

        if not user_message:
            user_message = "Hello"

        payload: dict = {
            "message": user_message,
            "model": "command-r-plus",
            "temperature": temperature,
        }
        if chat_history:
            payload["chat_history"] = chat_history
        if preamble.strip():
            payload["preamble"] = preamble.strip()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.cohere.ai/v1/chat",
                headers={
                    "Authorization": f"Bearer {self._cohere_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")

    async def _ollama_chat(
        self,
        messages: list[dict],
        temperature: float = 0.7,
    ) -> str:
        """Fallback chat via local Ollama instance."""
        url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature
            }
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    # ──────────────────────────── Helpers ────────────────────────────

    @staticmethod
    def _messages_to_prompt(messages: list[dict]) -> str:
        """Convert chat messages list to a single prompt string for Gemini."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System Instructions]: {content}")
            elif role == "assistant":
                parts.append(f"[Assistant]: {content}")
            else:
                parts.append(f"[User]: {content}")
        return "\n\n".join(parts)


# Global singleton
ai_engine = AIEngine()
