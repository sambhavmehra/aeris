"""
AERIS Configuration — Single source of truth for all settings.
Loads environment variables and provides a global Settings singleton.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from BACKEND/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path, override=True)


class Settings:
    """Central configuration loaded from environment variables."""

    def __init__(self):
        # --- LLM API Keys ---
        self.GROQ_API_KEYS: list[str] = self._collect_groq_keys()
        self.GROQ_VISION_API_KEY: str = os.getenv("GROQ_VISION_API_KEY", "").strip()
        self.GEMINI_API_KEY: str = os.getenv("VITE_GEMINI_API_KEY", "")
        self.CEREBRAS_API_KEY: str = os.getenv("CEREBRAS_API_KEY", "")
        self.HF_API_KEY: str = os.getenv("VITE_IMAGE_AI_API_KEY", "")
        self.TAVILY_API_KEY: str = os.getenv("VITE_TAVILY_API_KEY", "")
        self.COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "").strip()
        self.OLLAMA_VISION_MODEL: str = os.getenv("OLLAMA_VISION_MODEL", "qwen2.5vl:3b")

        # --- Identity ---
        self.USERNAME: str = os.getenv("Username", "User")
        self.ASSISTANT_NAME: str = os.getenv("Assistantname", "AERIS")

        # --- External Services ---
        self.NOTION_API_KEY: str = os.getenv("VITE_NOTION_API_KEY", "")
        self.NOTION_DATABASE_ID: str = os.getenv("VITE_NOTION_DATABASE_ID", "")
        self.BREVO_API_KEY: str = os.getenv("BREVO_API_KEY", "")
        self.TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        # --- SMTP Services ---
        self.SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp-relay.brevo.com")
        self.SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
        self.SMTP_LOGIN: str = (
            os.getenv("SMTP_LOGIN", "").strip(" '\"") or 
            os.getenv("BREVO_SMTP_LOGIN", "").strip(" '\"") or 
            os.getenv("BREVO_SENDER_EMAIL", "").strip(" '\"")
        )
        self.SMTP_PASSWORD: str = (
            os.getenv("SMTP_PASSWORD", "").strip(" '\"") or 
            os.getenv("BREVO_API_KEY", "").strip(" '\"")
        )
        self.BREVO_SENDER_EMAIL: str = os.getenv("BREVO_SENDER_EMAIL", "").strip(" '\"")
        self.BREVO_SENDER_NAME: str = os.getenv("BREVO_SENDER_NAME", "").strip(" '\"")

        # --- Server ---
        self.API_PORT: int = int(os.getenv("API_PORT", "8000"))
        self.API_HOST: str = os.getenv("API_HOST", "0.0.0.0")

        # --- Ollama Fallback ---
        self.OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

        # --- Paths ---
        import sys
        if getattr(sys, "frozen", False):
            self.BASE_DIR = Path(sys.executable).resolve().parent
            self.DATA_DIR = Path.home() / ".aeris" / "data"
            self.WORKSPACE_DIR = Path.home() / "AerisProjects"
        else:
            self.BASE_DIR = Path(__file__).resolve().parent
            self.DATA_DIR = self.BASE_DIR / "data"
            self.WORKSPACE_DIR = self.BASE_DIR.parent / "workspace"

        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

        # --- Model Defaults ---
        self.GROQ_PRIMARY_MODEL: str = "llama-3.3-70b-versatile"
        self.GROQ_FALLBACK_MODEL: str = "llama-3.1-8b-instant"
        self.GEMINI_MODEL: str = "gemini-2.5-flash"

    def _collect_groq_keys(self) -> list[str]:
        """Collect all available Groq API keys from env vars."""
        key_names = ["AERIS", "GROQ_API_KEY", "GroqAPIKey"]
        keys = []
        for name in key_names:
            val = os.getenv(name, "").strip()
            if val and val not in keys:
                keys.append(val)
        return keys

    @property
    def has_groq(self) -> bool:
        return len(self.GROQ_API_KEYS) > 0

    @property
    def has_gemini(self) -> bool:
        return bool(self.GEMINI_API_KEY)

    @property
    def has_tavily(self) -> bool:
        return bool(self.TAVILY_API_KEY)

    @property
    def has_cohere(self) -> bool:
        return bool(self.COHERE_API_KEY)

    @property
    def has_notion(self) -> bool:
        return bool(self.NOTION_API_KEY and self.NOTION_DATABASE_ID)

    @property
    def has_brevo(self) -> bool:
        return bool(self.BREVO_API_KEY)

    @property
    def has_smtp(self) -> bool:
        return bool(self.SMTP_SERVER and self.SMTP_LOGIN and self.SMTP_PASSWORD)

    @property
    def has_telegram(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

    def __repr__(self) -> str:
        return (
            f"Settings(\n"
            f"  groq_keys={len(self.GROQ_API_KEYS)}, "
            f"gemini={'✓' if self.has_gemini else '✗'}, "
            f"tavily={'✓' if self.has_tavily else '✗'}, "
            f"cohere={'✓' if self.has_cohere else '✗'}, "
            f"notion={'✓' if self.has_notion else '✗'}, "
            f"brevo={'✓' if self.has_brevo else '✗'}, "
            f"smtp={'✓' if self.has_smtp else '✗'}\n"
            f"  user={self.USERNAME}, assistant={self.ASSISTANT_NAME}\n"
            f"  port={self.API_PORT}\n"
            f")"
        )



# Global singleton
settings = Settings()
