"""
AERIS AI OS — AI Image Generator
Generates images from text prompts using Hugging Face Inference API.
Supports multiple models with automatic fallback.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import settings
from neural.providers import HuggingFaceProvider

logger = logging.getLogger("AERISImageGenerator")

# Models ranked by quality (will try in order)
IMAGE_MODELS = [
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-3-medium-diffusers",
]


class ImageGenerator:
    """Generates images from text prompts using Hugging Face API."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or os.path.join(os.getcwd(), "data", "generated_images"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Use centralized settings for API key
        self.provider = HuggingFaceProvider(settings.HF_API_KEY)

    def generate(
        self,
        prompt: str,
        filename: str = "",
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        model: str = "",
    ) -> dict:
        """
        Generate an image from a text prompt via Hugging Face.
        Returns dict with success status, path, and metadata.
        """
        if not prompt or not prompt.strip():
            return {"success": False, "error": "Empty prompt provided"}

        # Build output filename
        if not filename:
            safe_prompt = prompt[:40].replace(" ", "_").replace("/", "_").replace("\\", "_")
            filename = f"img_{safe_prompt}_{uuid.uuid4().hex[:6]}.png"
        if not filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename += ".png"

        output_path = self.output_dir / filename

        # Models to try (specific model if provided, else fallback list)
        models_to_try = [model] if model else IMAGE_MODELS
        
        parameters = {}
        if negative_prompt:
            parameters["negative_prompt"] = negative_prompt
        if width:
            parameters["width"] = width
        if height:
            parameters["height"] = height

        last_error = ""
        for target_model in models_to_try:
            try:
                logger.info(f"Attempting image generation with {target_model}...")
                image_bytes = self.provider.generate_image(prompt, target_model, parameters)
                
                # Save binary content to file
                output_path.write_bytes(image_bytes)
                logger.info(f"Image generated successfully with {target_model}: {output_path}")
                
                # Optional: try to open in default viewer/browser
                try:
                    import webbrowser
                    webbrowser.open(output_path.absolute().as_uri())
                except Exception:
                    pass
                    
                return {
                    "success": True,
                    "output_path": str(output_path),
                    "prompt": prompt,
                    "model": target_model,
                    "size": f"{width}x{height}",
                    "size_bytes": output_path.stat().st_size,
                    "generated_at": datetime.now().isoformat(),
                }
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Generation with {target_model} failed: {e}")
                # Continue loop to try next model in fallback list
                continue

        # If we reached here, all models failed
        return {
            "success": False, 
            "error": f"All image models failed. Last error: {last_error}"
        }

    def list_generated(self) -> list[dict]:
        """List all previously generated images."""
        images = []
        if self.output_dir.exists():
            valid_extensions = (".png", ".jpg", ".jpeg", ".webp")
            files = [f for f in self.output_dir.iterdir() if f.suffix.lower() in valid_extensions]
            for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
                images.append({
                    "filename": f.name,
                    "path": str(f),
                    "size_bytes": f.stat().st_size,
                    "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
        return images

    def get_available_models(self) -> list[str]:
        """Return list of available models."""
        return list(IMAGE_MODELS)
