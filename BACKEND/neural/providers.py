"""
AERIS Neural Providers — AI Service Adapters.
Modular provider classes for various AI APIs (Hugging Face, Groq, etc.).
"""

import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger("aeris.neural.providers")

class AIProvider:
    """Base class for AI service providers."""
    pass

class HuggingFaceProvider(AIProvider):
    """
    Provider for Hugging Face Inference API.
    Used for image generation, embedding, and text generation.
    """
    
    # Use the newer router endpoint as requested
    BASE_URL = "https://router.huggingface.co/hf-inference/models/"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def generate_image(self, prompt: str, model: str, parameters: Optional[Dict[str, Any]] = None) -> bytes:
        """
        Generate an image using the specified HF model.
        Returns the binary content of the image.
        """
        url = f"{self.BASE_URL}{model}"
        payload = {"inputs": prompt}
        if parameters:
            payload["parameters"] = parameters
            
        try:
            logger.info(f"HF Request: {model} | Prompt: {prompt[:50]}...")
            response = requests.post(url, headers=self.headers, json=payload, timeout=60)
            
            # Check for success
            if response.status_code == 200:
                # Validate content-type to ensure it's not returning HTML error pages
                content_type = response.headers.get("Content-Type", "").lower()
                
                # Check for binary image content
                is_image = "image" in content_type or "application/octet-stream" in content_type
                
                if "text/html" in content_type or not is_image:
                    # Sometimes errors are returned as HTML with status 200 by proxies
                    sample = response.text[:200].strip()
                    if sample.startswith("<!DOCTYPE") or sample.startswith("<html"):
                        logger.error(f"HF returned HTML instead of image: {sample}")
                        raise Exception("HF returned HTML response (likely a 404 or proxy error masked as 200)")
                
                # Double check size - images shouldn't be tiny (e.g. < 1KB is suspicious)
                if len(response.content) < 1024:
                    logger.warning(f"HF returned suspiciously small content ({len(response.content)} bytes)")
                
                return response.content
            
            # Handle specific error codes
            error_msg = ""
            try:
                error_data = response.json()
                if isinstance(error_data, dict):
                    error_msg = error_data.get("error", "")
                elif isinstance(error_data, list) and len(error_data) > 0:
                    error_msg = str(error_data[0])
            except:
                error_msg = response.text[:500]
            
            if not error_msg:
                error_msg = f"HTTP {response.status_code}"

            logger.error(f"HF Error [{response.status_code}]: {error_msg}")
            
            if response.status_code == 429:
                raise Exception("Hugging Face API rate limit reached.")
            elif response.status_code == 503:
                raise Exception(f"Model {model} is currently loading or unavailable (503).")
            elif response.status_code == 404:
                raise Exception(f"Model {model} not found (404). Check the model ID.")
            else:
                raise Exception(f"HF API failed with status {response.status_code}: {error_msg}")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"HF Request failed: {e}")
            raise Exception(f"Connection to Hugging Face failed: {e}")

class GroqProvider(AIProvider):
    """Provider for Groq Cloud API."""
    def __init__(self, api_key: str):
        self.api_key = api_key

class GeminiProvider(AIProvider):
    """Provider for Google Gemini API."""
    def __init__(self, api_key: str):
        self.api_key = api_key
