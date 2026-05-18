"""
AERIS — AI Video Generator
Generates videos from text prompts using Hugging Face Inference API.
Supports damo-vilab/text-to-video-ms-1.7b.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values

logger = logging.getLogger("AerisVideoGenerator")

# Load API key
_env_path = Path(__file__).resolve().parent.parent / ".env"
_env = dotenv_values(str(_env_path))
HF_API_KEY = (
    _env.get("VITE_IMAGE_AI_API_KEY")
    or os.environ.get("VITE_IMAGE_AI_API_KEY")
    or os.environ.get("HF_API_KEY")
    or ""
)

# Models ranked by quality (will try in order)
VIDEO_MODELS = [
    "Wan-AI/Wan2.2-T2V-A14B",
]


class VideoGenerator:
    """Generates videos from text prompts using Hugging Face API."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or os.path.join(os.getcwd(), "data", "generated_videos"))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = HF_API_KEY

    def generate(
        self,
        prompt: str,
        filename: str = "",
        model: str = "",
    ) -> dict:
        """
        Generate a video from a text prompt.
        Returns dict with success status, path, and metadata.
        """
        if not self.api_key:
            return {"success": False, "error": "No Hugging Face API key found. Set VITE_IMAGE_AI_API_KEY in .env"}

        if not prompt or not prompt.strip():
            return {"success": False, "error": "Empty prompt provided"}

        # Build output filename
        if not filename:
            safe_prompt = prompt[:40].replace(" ", "_").replace("/", "_").replace("\\", "_")
            filename = f"vid_{safe_prompt}_{uuid.uuid4().hex[:6]}.mp4"
        if not filename.endswith((".mp4", ".gif", ".avi", ".webm")):
            filename += ".mp4"

        output_path = self.output_dir / filename

        # Select models to try
        models_to_try = [model] if model else VIDEO_MODELS

        for model_id in models_to_try:
            try:
                result = self._call_hf_api(prompt, model_id)
                if result is not None:
                    output_path.write_bytes(result)
                    logger.info(f"Video generated: {output_path} using {model_id}")
                    
                    try:
                        import webbrowser
                        webbrowser.open(output_path.absolute().as_uri())
                    except Exception:
                        pass
                        
                    return {
                        "success": True,
                        "output_path": str(output_path),
                        "model_used": model_id,
                        "prompt": prompt,
                        "size_bytes": output_path.stat().st_size,
                        "generated_at": datetime.now().isoformat(),
                    }
            except Exception as e:
                logger.warning(f"Model {model_id} failed: {e}")
                continue

        return {"success": False, "error": "All video generation models failed. The API may be rate-limited or the models are loading. Try again in a moment."}

    def _call_hf_api(self, prompt: str, model_id: str) -> Optional[bytes]:
        """Call Hugging Face Inference API to generate a video."""
        import requests

        api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        payload = {"inputs": prompt}

        logger.info(f"Generating video with prompt: {prompt}")
        response = requests.post(api_url, headers=headers, json=payload, timeout=300)

        if response.status_code == 200:
            content_type = response.headers.get("content-type", "")
            if "video" in content_type or "octet-stream" in content_type or "application/" not in content_type:
                return response.content
            else:
                # Might be JSON error
                try:
                    error_data = response.json()
                    raise Exception(f"API returned non-video response: {error_data}")
                except Exception:
                    # If it's a 200 with an unknown content type but we can't parse JSON, assume it's binary content
                    return response.content

        elif response.status_code == 503:
            # Model is loading
            try:
                data = response.json()
                wait_time = data.get("estimated_time", 30)
                logger.info(f"Model {model_id} is loading, estimated wait: {wait_time}s")
            except Exception:
                pass
            raise Exception(f"Model loading (503)")

        elif response.status_code == 429:
            raise Exception("Rate limited (429)")

        else:
            try:
                error = response.json()
                raise Exception(f"API error {response.status_code}: {error}")
            except Exception:
                raise Exception(f"API error {response.status_code}: {response.text[:200]}")

    def list_generated(self) -> list[dict]:
        """List all previously generated videos."""
        videos = []
        if self.output_dir.exists():
            for f in sorted(self.output_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                if f.suffix.lower() in (".mp4", ".gif", ".avi", ".webm"):
                    videos.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_bytes": f.stat().st_size,
                        "created_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
        return videos

    def get_available_models(self) -> list[str]:
        """Return list of available models."""
        return list(VIDEO_MODELS)
