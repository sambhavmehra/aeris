# -*- coding: utf-8 -*-
"""
AERIS Image Agent -- Generates images from text prompts using Hugging Face API.
Routes: brain intent='image'
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from generation.image_generator import ImageGenerator

logger = logging.getLogger("aeris.agent.imageagent")

_IMAGES_DIR = Path(__file__).resolve().parent.parent / "data" / "generated_images"
_generator = ImageGenerator(output_dir=str(_IMAGES_DIR))


class ImageAgent(BaseAgent):
    """Generates images from text prompts via Hugging Face Inference API."""

    def __init__(self):
        super().__init__(
            name="ImageAgent",
            description="AI image generation from text prompts using FLUX / Stable Diffusion",
            task_domain="image",
            version="1.0.0",
            capabilities=[
                "Text-to-Image Generation",
                "FLUX / Stable Diffusion Models",
                "Custom Art and Illustrations",
                "Photo-realistic Image Synthesis",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Extract the image prompt from the user message."""
        # Strip common prefixes so we get a clean prompt
        lower = message.lower()
        for prefix in [
            "generate image of", "generate an image of", "create image of",
            "create an image of", "make image of", "make an image of",
            "draw ", "generate ", "create ", "make ", "show me ",
            "bana ", "banao ", "bana do ", "photo de ", "photo ", "image of",
            "ek ", "mujhe ", "bhai ",
        ]:
            if lower.startswith(prefix):
                message = message[len(prefix):].strip()
                lower = message.lower()
        return message.strip() or "a beautiful abstract digital artwork"

    async def execute(self, prompt: Any) -> Any:
        """Run image generation synchronously (HF API call)."""
        import asyncio
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: _generator.generate(str(prompt)))
        return result

    async def report(self, results: Any) -> str:
        """Return a response with an image marker the frontend can detect."""
        if not results or not results.get("success"):
            err = results.get("error", "Unknown error") if results else "Generation failed"
            return f"⚠️ Image generation failed: {err}"

        output_path: str = results["output_path"]
        filename = Path(output_path).name
        # Return a special marker so the frontend can render an <img> tag
        # The backend serves /images/<filename> as a static route
        image_url = f"http://localhost:8000/images/{filename}"
        return (
            f"✅ Image generated successfully!\n\n"
            f"[IMAGE:{image_url}]\n\n"
            f"*Prompt:* {results.get('prompt', '')}\n"
            f"*Size:* {results.get('size', '')}"
        )
