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
        """
        Enhance prompt using SearchAgent (style/composition/negative constraints),
        then generate image via ImageGenerator.
        """
        import asyncio
        from ai_engine import ai_engine
        from agents.search_agent import SearchAgent

        # Support both:
        #  - plain string prompt (current behavior)
        #  - dict prompt payload (e.g., {"prompt": "...", "negative_prompt": "...", "width": ..., ...})
        user_prompt: str
        negative_prompt_in: str = ""
        width: int = 1024
        height: int = 1024
        model: str = ""

        if isinstance(prompt, dict):
            user_prompt = str(prompt.get("prompt") or prompt.get("text") or "").strip()
            negative_prompt_in = str(prompt.get("negative_prompt") or "").strip()
            width = int(prompt.get("width") or 1024)
            height = int(prompt.get("height") or 1024)
            model = str(prompt.get("model") or "").strip()
        else:
            user_prompt = str(prompt or "").strip()

        if not user_prompt:
            return {"success": False, "error": "Empty prompt provided"}

        # 1) Generate a high-quality visual search query using the AI Engine
        query_prompt = (
            "Given the user's image-generation request, write a single precise, high-impact web search query "
            "to find visual details, appearance characteristics, design trends, styling, colors, or materials "
            "related to the main subject. Output ONLY the query string, no quotes, no extra text.\n\n"
            f"USER REQUEST: {user_prompt}"
        )
        try:
            search_query = await ai_engine.chat([
                {"role": "system", "content": "You are a precise search query generator. Output only the query string without comments or explanation."},
                {"role": "user", "content": query_prompt}
            ], max_tokens=60, temperature=0.2)
            search_query = search_query.strip().strip('"').strip("'").strip()
            if not search_query:
                search_query = user_prompt
        except Exception:
            search_query = user_prompt

        # 2) Collect prompt enhancement details via SearchAgent web search
        search_agent = SearchAgent()
        try:
            logger.info(f"[ImageAgent] Executing web search for visual references: '{search_query}'")
            search_results = await search_agent.run(search_query, {})
            search_text = str(search_results.get("response") or "").strip()
        except Exception as e:
            logger.warning(f"[ImageAgent] SearchAgent failed during image prep: {e}")
            search_text = ""

        # 3) Generate enhanced prompt + enhanced negative prompt using visual search details
        enhance_system = "You are an expert prompt engineer for FLUX/Stable Diffusion."
        enhance_user = (
            "INSTRUCTIONS:\n"
            "- Convert the USER PROMPT into an enhanced generator prompt.\n"
            "- Integrate specific, rich visual details, color palettes, textures, and design components "
            "sourced from the web SEARCH DETAILS to make the prompt exceptionally vivid, high-fidelity, and realistic.\n"
            "- Produce a compositionally clear prompt with style + lighting + camera framing.\n"
            "- Output STRICT JSON only.\n\n"
            f"USER PROMPT:\n{user_prompt}\n\n"
            f"SEARCH DETAILS (may be empty):\n{search_text}\n\n"
            f"USER NEGATIVE PROMPT (may be empty):\n{negative_prompt_in}\n\n"
            "Return JSON (STRICT, no markdown):\n"
            "{\n"
            '  "enhanced_prompt": "...",\n'
            '  "enhanced_negative_prompt": "...",\n'
            '  "prompt_used": "string"\n'
            "}\n"
        )

        try:
            raw = await ai_engine.classify(enhance_user)  # classifier path is used elsewhere; still returns text
            # Fallback to chat if classify doesn't give JSON
            raw_text = str(raw).strip()
            if not raw_text.startswith("{"):
                raw_text = await ai_engine.chat(
                    [{"role": "system", "content": enhance_system}, {"role": "user", "content": enhance_user}],
                    max_tokens=800,
                )
            import json
            data = json.loads(raw_text.strip().strip("```json").strip("```"))
            enhanced_prompt = str(data.get("enhanced_prompt") or user_prompt).strip()
            enhanced_negative_prompt = str(data.get("enhanced_negative_prompt") or negative_prompt_in).strip()
        except Exception:
            enhanced_prompt = user_prompt
            enhanced_negative_prompt = negative_prompt_in

        # 3) Generate image (sync call in executor)
        loop = asyncio.get_event_loop()
        gen_kwargs = {
            "prompt": enhanced_prompt,
            "negative_prompt": enhanced_negative_prompt,
            "width": width,
            "height": height,
            "model": model,
        }
        result = await loop.run_in_executor(None, lambda: _generator.generate(**gen_kwargs))
        # Ensure prompt field exists for reporting
        if isinstance(result, dict) and result.get("success") and not result.get("prompt"):
            result["prompt"] = enhanced_prompt
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
