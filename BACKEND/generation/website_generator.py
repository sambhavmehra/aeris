"""
AERIS -- Production Website Generator
Generates complete, multi-page, production-ready websites from natural language.
Features:
  - Multi-page project structure (index, about, contact, services/projects, etc.)
  - Modern UI: glassmorphism, gradients, smooth animations, micro-interactions
  - Fully responsive design (mobile, tablet, desktop)
  - CSS/JS separated into own files
  - Dark / light / corporate / creative theme variations
  - Working navigation, forms, buttons, smooth scrolling
  - LLM-powered content generation for realistic placeholder text
  - Context-aware image integration (Unsplash/Picsum + AI image generation)
  - Multi-language support (any language via LLM translation)
"""
from __future__ import annotations

import os
import json
import re
import shutil
import uuid
import webbrowser
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# =====================================================================
#  DATA STRUCTURES
# =====================================================================

@dataclass
class GeneratedWebsite:
    project_id: str
    site_type: str
    title: str
    output_dir: str
    files: list[dict]
    created_at: str
    pages: list[str] = field(default_factory=list)
    theme: str = "dark"
    language: str = "en"
    preview_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "site_type": self.site_type,
            "title": self.title,
            "output_dir": self.output_dir,
            "file_count": len(self.files),
            "pages": self.pages,
            "theme": self.theme,
            "language": self.language,
            "files": [{"path": f["path"], "lang": f["lang"]} for f in self.files],
            "created_at": self.created_at,
        }


# =====================================================================
#  IMAGE INTEGRATION SYSTEM
# =====================================================================

class ImageBank:
    """Provides context-aware images for generated websites.
    Uses picsum.photos for instant high-quality images, and can also
    invoke AERIS's AI image generator for custom hero/banner images.
    """

    # Context-keyword to Unsplash search term mapping
    CONTEXT_IMAGES = {
        "portfolio": {
            "hero": "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=1400&h=600&fit=crop",
            "about": "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=800&h=500&fit=crop",
            "projects": [
                "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1551650975-87deedd944c3?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1558655146-9f40138edfeb?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1504639725590-34d0984388bd?w=600&h=400&fit=crop",
            ],
            "testimonials": [
                "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=80&h=80&fit=crop",
            ],
        },
        "business": {
            "hero": "https://images.unsplash.com/photo-1497366216548-37526070297c?w=1400&h=600&fit=crop",
            "about": "https://images.unsplash.com/photo-1521737711867-e3b97375f902?w=800&h=500&fit=crop",
            "projects": [
                "https://images.unsplash.com/photo-1553877522-43269d4ea984?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1551434678-e076c223a692?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1552664730-d307ca884978?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1559136555-9303baea8ebd?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1542744173-8e7e53415bb0?w=600&h=400&fit=crop",
            ],
            "testimonials": [
                "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=80&h=80&fit=crop",
            ],
        },
        "agency": {
            "hero": "https://images.unsplash.com/photo-1542744094-3a31f272c490?w=1400&h=600&fit=crop",
            "about": "https://images.unsplash.com/photo-1600880292203-757bb62b4baf?w=800&h=500&fit=crop",
            "projects": [
                "https://images.unsplash.com/photo-1561070791-2526d30994b5?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1559028012-481c04fa702d?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1547658719-da2b51169166?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1432888622747-4eb9a8efeb07?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1563986768609-322da13575f2?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1507238691740-187a5b1d37b8?w=600&h=400&fit=crop",
            ],
            "testimonials": [
                "https://images.unsplash.com/photo-1580489944761-15a19d654956?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1633332755192-727a05c4013d?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=80&h=80&fit=crop",
            ],
        },
        "landing": {
            "hero": "https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=1400&h=600&fit=crop",
            "about": "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=800&h=500&fit=crop",
            "projects": [
                "https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=600&h=400&fit=crop",
            ],
            "testimonials": [
                "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1566492031773-4f4e44671857?w=80&h=80&fit=crop",
            ],
        },
        "ecommerce": {
            "hero": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=1400&h=600&fit=crop",
            "about": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?w=800&h=500&fit=crop",
            "projects": [
                "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1585386959984-a4155224a1ad?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=600&h=400&fit=crop",
            ],
            "testimonials": [
                "https://images.unsplash.com/photo-1489424731084-a5d8b219a5bb?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?w=80&h=80&fit=crop",
            ],
        },
        "blog": {
            "hero": "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=1400&h=600&fit=crop",
            "about": "https://images.unsplash.com/photo-1455390582262-044cdead277a?w=800&h=500&fit=crop",
            "projects": [
                "https://images.unsplash.com/photo-1486312338219-ce68d2c6f44d?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1501504905252-473c47e087f8?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1488190211105-8b0e65b80b4e?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1504691342899-4d92b50853e1?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1434030216411-0b793f4b4173?w=600&h=400&fit=crop",
                "https://images.unsplash.com/photo-1471897488648-5eae4ac6686b?w=600&h=400&fit=crop",
            ],
            "testimonials": [
                "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=80&h=80&fit=crop",
                "https://images.unsplash.com/photo-1570295999919-56ceb5ecca61?w=80&h=80&fit=crop",
            ],
        },
    }

    def __init__(self, site_type: str = "landing"):
        self.site_type = site_type
        self.images = self.CONTEXT_IMAGES.get(site_type, self.CONTEXT_IMAGES["landing"])

    def hero_url(self) -> str:
        return self.images.get("hero", "https://picsum.photos/1400/600")

    def about_url(self) -> str:
        return self.images.get("about", "https://picsum.photos/800/500")

    def project_url(self, index: int = 0) -> str:
        projs = self.images.get("projects", [])
        if projs:
            return projs[index % len(projs)]
        return f"https://picsum.photos/600/400?random={index}"

    def testimonial_avatar(self, index: int = 0) -> str:
        avatars = self.images.get("testimonials", [])
        if avatars:
            return avatars[index % len(avatars)]
        return f"https://i.pravatar.cc/80?img={index + 10}"

    def generate_ai_hero(self, title: str, prompt: str, output_dir: Path) -> Optional[str]:
        """Try to generate a custom AI hero image using AERIS's ImageGenerator.
        Returns the local filename if successful, else None."""
        try:
            from image_generator import ImageGenerator
            ig = ImageGenerator()
            img_prompt = (
                f"A cinematic, professional website hero banner image for '{title}'. "
                f"{prompt[:100]}. Modern, high quality, ultra-HD, wide format, no text."
            )
            res = ig.generate(prompt=img_prompt, width=1400, height=600)
            if res and res.get("success") and res.get("output_path"):
                bg_file = output_dir / "hero_bg.jpg"
                shutil.copy(res["output_path"], bg_file)
                return "hero_bg.jpg"
        except Exception:
            pass
        return None


# =====================================================================
#  MULTI-LANGUAGE ENGINE
# =====================================================================

# Common language detection patterns
_LANG_PATTERNS = {
    "hi": ["hindi", "hindi mein", "hindi me", "hindi main", "हिंदी"],
    "es": ["spanish", "español", "en español", "en espanol"],
    "fr": ["french", "français", "en français", "en francais"],
    "de": ["german", "deutsch", "auf deutsch"],
    "ja": ["japanese", "日本語", "nihongo"],
    "zh": ["chinese", "中文", "mandarin"],
    "ko": ["korean", "한국어"],
    "ar": ["arabic", "عربي"],
    "pt": ["portuguese", "português", "em portugues"],
    "ru": ["russian", "русский", "на русском"],
    "it": ["italian", "italiano", "in italiano"],
    "nl": ["dutch", "nederlands"],
    "tr": ["turkish", "türkçe"],
    "bn": ["bengali", "bangla", "বাংলা"],
    "ta": ["tamil", "தமிழ்"],
    "te": ["telugu", "తెలుగు"],
    "mr": ["marathi", "मराठी"],
    "gu": ["gujarati", "ગુજરાતી"],
    "pa": ["punjabi", "ਪੰਜਾਬੀ"],
    "ur": ["urdu", "اردو"],
    "th": ["thai", "ไทย"],
    "vi": ["vietnamese", "tiếng việt"],
    "pl": ["polish", "polski"],
    "uk": ["ukrainian", "українська"],
    "sv": ["swedish", "svenska"],
}

_LANG_NAMES = {
    "en": "English", "hi": "Hindi", "es": "Spanish", "fr": "French",
    "de": "German", "ja": "Japanese", "zh": "Chinese", "ko": "Korean",
    "ar": "Arabic", "pt": "Portuguese", "ru": "Russian", "it": "Italian",
    "nl": "Dutch", "tr": "Turkish", "bn": "Bengali", "ta": "Tamil",
    "te": "Telugu", "mr": "Marathi", "gu": "Gujarati", "pa": "Punjabi",
    "ur": "Urdu", "th": "Thai", "vi": "Vietnamese", "pl": "Polish",
    "uk": "Ukrainian", "sv": "Swedish",
}

# Default UI strings (English) that get translated
_UI_STRINGS_EN = {
    # Navigation
    "nav_home": "Home",
    "nav_about": "About",
    "nav_projects": "Projects",
    "nav_services": "Services",
    "nav_contact": "Contact",
    "nav_products": "Products",
    "nav_articles": "Articles",
    "nav_work": "Work",
    # Hero
    "hero_cta": "Explore More",
    "hero_cta2": "Get in Touch",
    # Sections
    "features_title": "Why Choose Us",
    "features_sub": "We combine innovation with expertise to deliver exceptional results.",
    "stats_projects": "Projects Completed",
    "stats_clients": "Happy Clients",
    "stats_years": "Years Experience",
    "stats_satisfaction": "Client Satisfaction",
    "testimonials_title": "What People Say",
    "testimonials_sub": "Don't just take our word for it.",
    "pricing_title": "Simple Pricing",
    "pricing_sub": "Transparent plans that scale with your needs.",
    "contact_title": "Get in Touch",
    "contact_sub": "Have a question or want to work together? We'd love to hear from you.",
    "contact_name": "Your Name",
    "contact_email": "Email Address",
    "contact_subject": "Subject",
    "contact_message": "Message",
    "contact_send": "Send Message",
    "contact_sending": "Sending...",
    "contact_sent": "Message Sent!",
    "projects_title": "Featured Projects",
    "projects_sub": "A showcase of our best work and achievements.",
    "services_title": "Our Services",
    "services_sub": "Comprehensive solutions tailored to your unique needs.",
    "products_title": "Our Products",
    "products_sub": "Premium products designed for modern life.",
    "articles_title": "Latest Articles",
    "articles_sub": "Insights and ideas from our team.",
    "about_title": "About",
    "about_story": "My Story",
    "about_mission": "Our Mission",
    "about_skills": "Skills & Technologies",
    "about_timeline": "Experience Timeline",
    "about_values": "Our Values",
    "connect_title": "Let's Connect",
    "connect_sub": "Have a project in mind? Let's talk about how we can work together.",
    "read_more": "Read More",
    "add_to_cart": "Add to Cart",
    "get_started": "Get Started",
    "contact_sales": "Contact Sales",
    # Footer
    "footer_desc": "Built with passion and powered by modern technology. Crafted to deliver exceptional digital experiences.",
    "footer_nav": "Navigation",
    "footer_connect": "Connect",
    "footer_legal": "Legal",
    "footer_privacy": "Privacy Policy",
    "footer_terms": "Terms of Service",
    "footer_cookies": "Cookie Policy",
    "footer_rights": "All rights reserved.",
}


class LanguageEngine:
    """Detects target language from prompt and translates UI strings."""

    def __init__(self):
        self._cache: dict[str, dict[str, str]] = {"en": _UI_STRINGS_EN.copy()}

    def detect_language(self, prompt: str) -> str:
        """Detect language from the user prompt. Returns ISO 639-1 code."""
        p = prompt.lower()
        for code, keywords in _LANG_PATTERNS.items():
            for kw in keywords:
                if kw in p:
                    return code
        return "en"

    def get_language_name(self, code: str) -> str:
        return _LANG_NAMES.get(code, "English")

    def get_html_lang(self, code: str) -> str:
        """Return HTML lang attribute value."""
        return code

    def translate_strings(self, lang_code: str) -> dict[str, str]:
        """Translate all UI strings to the target language.
        Uses the LLM (chat engine) for translation. Returns English as fallback."""
        if lang_code == "en":
            return _UI_STRINGS_EN.copy()

        if lang_code in self._cache:
            return self._cache[lang_code]

        lang_name = self.get_language_name(lang_code)

        try:
            from chat_engine import chat
            # Build a translation request with all strings
            strings_json = json.dumps(_UI_STRINGS_EN, ensure_ascii=False)
            translation_prompt = (
                f"You are a professional translator. Translate ALL the following JSON values "
                f"from English into fluent, natural {lang_name}. Keep the JSON keys EXACTLY "
                f"as they are (in English). Output ONLY valid JSON, no explanation, no markdown "
                f"blocks. Ensure the translations are culturally appropriate and natural.\n\n"
                f"{strings_json}"
            )
            response = chat(translation_prompt)
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                translated = json.loads(json_match.group(0))
                # Merge with English defaults for any missing keys
                result = _UI_STRINGS_EN.copy()
                result.update(translated)
                self._cache[lang_code] = result
                return result
        except Exception:
            pass

        return _UI_STRINGS_EN.copy()


class SiteAnalyzer:
    """Analyzes a URL using LLM to extract metadata for cloning aesthetics/structure."""
    
    def analyze(self, url: str) -> Optional[dict]:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8', errors='ignore')
            
            # Simple text extraction (strip JS, CSS, and HTML tags)
            text = re.sub(r'<script.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            
            # Extract page title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
            raw_title = title_match.group(1).strip() if title_match else "Website"
            
            content_snippet = text[:3000]

            from chat_engine import chat
            prompt = (
                f"You are a website analyzer. I fetched a website ({url}) with title '{raw_title}'. "
                f"Here is some text from it: {content_snippet}\n\n"
                f"Analyze this and return a JSON object with EXACTLY these keys:\n"
                f"- title: The short name of the business or project (max 3 words)\n"
                f"- description: A catchy 1-sentence hero subheadline summarizing what they do\n"
                f"- site_type: Must be exactly one of: portfolio, business, agency, ecommerce, blog, dashboard, landing.\n"
                f"- theme: Must be exactly one of: dark, light, corporate, creative.\n"
                f"Return ONLY valid JSON, no markdown, no quotes around the block."
            )
            
            response = chat(prompt)
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception:
            pass
        return None

# Global instances
_image_bank_cache: dict[str, ImageBank] = {}
_language_engine = LanguageEngine()
_site_analyzer = SiteAnalyzer()


def _get_image_bank(site_type: str) -> ImageBank:
    if site_type not in _image_bank_cache:
        _image_bank_cache[site_type] = ImageBank(site_type)
    return _image_bank_cache[site_type]


# =====================================================================
#  THEME SYSTEM
# =====================================================================

THEMES = {
    "dark": {
        "bg": "#06060b", "bg2": "#0d0d15", "bg3": "#111120",
        "surface": "rgba(15,15,30,0.85)", "surface2": "rgba(20,20,40,0.6)",
        "text": "#e8e6f0", "text2": "#c8c6d4", "muted": "#8886a0",
        "accent": "#8b5cf6", "accent2": "#06b6d4", "accent3": "#34d399",
        "border": "rgba(139,92,246,0.15)", "border_hover": "rgba(139,92,246,0.35)",
        "gradient": "linear-gradient(135deg, #8b5cf6, #06b6d4, #34d399)",
        "glass": "rgba(10,10,25,0.7)",
        "glass_border": "rgba(139,92,246,0.2)",
    },
    "light": {
        "bg": "#f8f9fc", "bg2": "#ffffff", "bg3": "#f0f1f5",
        "surface": "rgba(255,255,255,0.9)", "surface2": "rgba(248,249,252,0.8)",
        "text": "#1a1a2e", "text2": "#333355", "muted": "#6b6b8d",
        "accent": "#6d28d9", "accent2": "#0891b2", "accent3": "#059669",
        "border": "rgba(109,40,217,0.12)", "border_hover": "rgba(109,40,217,0.3)",
        "gradient": "linear-gradient(135deg, #6d28d9, #0891b2, #059669)",
        "glass": "rgba(255,255,255,0.75)",
        "glass_border": "rgba(109,40,217,0.15)",
    },
    "corporate": {
        "bg": "#f5f7fa", "bg2": "#ffffff", "bg3": "#edf0f5",
        "surface": "rgba(255,255,255,0.95)", "surface2": "rgba(245,247,250,0.85)",
        "text": "#1e293b", "text2": "#334155", "muted": "#64748b",
        "accent": "#2563eb", "accent2": "#0ea5e9", "accent3": "#10b981",
        "border": "rgba(37,99,235,0.1)", "border_hover": "rgba(37,99,235,0.25)",
        "gradient": "linear-gradient(135deg, #2563eb, #0ea5e9)",
        "glass": "rgba(255,255,255,0.8)",
        "glass_border": "rgba(37,99,235,0.1)",
    },
    "creative": {
        "bg": "#0a0a1a", "bg2": "#12122a", "bg3": "#181838",
        "surface": "rgba(18,18,42,0.85)", "surface2": "rgba(24,24,56,0.6)",
        "text": "#f0eef8", "text2": "#d0cee0", "muted": "#9896b0",
        "accent": "#f43f5e", "accent2": "#f59e0b", "accent3": "#8b5cf6",
        "border": "rgba(244,63,94,0.15)", "border_hover": "rgba(244,63,94,0.35)",
        "gradient": "linear-gradient(135deg, #f43f5e, #f59e0b, #8b5cf6)",
        "glass": "rgba(10,10,26,0.7)",
        "glass_border": "rgba(244,63,94,0.2)",
    },
}


# =====================================================================
#  SITE TYPE CONFIGURATIONS
# =====================================================================

SITE_CONFIGS = {
    "portfolio": {
        "pages": ["index", "about", "projects", "contact"],
        "nav_items": [
            {"label": "Home", "href": "index.html", "icon": "🏠"},
            {"label": "About", "href": "about.html", "icon": "👤"},
            {"label": "Projects", "href": "projects.html", "icon": "💼"},
            {"label": "Contact", "href": "contact.html", "icon": "✉️"},
        ],
        "hero_headline": "Hi, I'm <span class='gradient-text'>{title}</span>",
        "hero_sub": "A passionate creator building beautiful digital experiences.",
        "default_theme": "dark",
    },
    "business": {
        "pages": ["index", "about", "services", "contact"],
        "nav_items": [
            {"label": "Home", "href": "index.html", "icon": "🏠"},
            {"label": "About", "href": "about.html", "icon": "📖"},
            {"label": "Services", "href": "services.html", "icon": "⚙️"},
            {"label": "Contact", "href": "contact.html", "icon": "📞"},
        ],
        "hero_headline": "<span class='gradient-text'>{title}</span>",
        "hero_sub": "Driving innovation and delivering excellence for businesses worldwide.",
        "default_theme": "corporate",
    },
    "landing": {
        "pages": ["index"],
        "nav_items": [
            {"label": "Features", "href": "#features", "icon": "✨"},
            {"label": "Testimonials", "href": "#testimonials", "icon": "💬"},
            {"label": "Pricing", "href": "#pricing", "icon": "💰"},
            {"label": "Contact", "href": "#contact", "icon": "📧"},
        ],
        "hero_headline": "Welcome to <span class='gradient-text'>{title}</span>",
        "hero_sub": "The next generation platform that transforms how you work.",
        "default_theme": "dark",
    },
    "agency": {
        "pages": ["index", "about", "work", "services", "contact"],
        "nav_items": [
            {"label": "Home", "href": "index.html", "icon": "🏠"},
            {"label": "About", "href": "about.html", "icon": "🏢"},
            {"label": "Work", "href": "work.html", "icon": "🎨"},
            {"label": "Services", "href": "services.html", "icon": "💡"},
            {"label": "Contact", "href": "contact.html", "icon": "📧"},
        ],
        "hero_headline": "We are <span class='gradient-text'>{title}</span>",
        "hero_sub": "A creative agency crafting bold digital experiences.",
        "default_theme": "creative",
    },
    "ecommerce": {
        "pages": ["index", "products", "about", "contact"],
        "nav_items": [
            {"label": "Home", "href": "index.html", "icon": "🏠"},
            {"label": "Products", "href": "products.html", "icon": "🛍️"},
            {"label": "About", "href": "about.html", "icon": "ℹ️"},
            {"label": "Contact", "href": "contact.html", "icon": "📧"},
        ],
        "hero_headline": "Shop <span class='gradient-text'>{title}</span>",
        "hero_sub": "Premium products, unbeatable prices, fast delivery.",
        "default_theme": "light",
    },
    "blog": {
        "pages": ["index", "articles", "about", "contact"],
        "nav_items": [
            {"label": "Home", "href": "index.html", "icon": "🏠"},
            {"label": "Articles", "href": "articles.html", "icon": "📝"},
            {"label": "About", "href": "about.html", "icon": "👤"},
            {"label": "Contact", "href": "contact.html", "icon": "✉️"},
        ],
        "hero_headline": "<span class='gradient-text'>{title}</span>",
        "hero_sub": "Insights, stories, and ideas that matter.",
        "default_theme": "light",
    },
    "dashboard": {
        "pages": ["index"],
        "nav_items": [
            {"label": "Overview", "href": "#overview", "icon": "📊"},
            {"label": "Analytics", "href": "#analytics", "icon": "📈"},
            {"label": "Users", "href": "#users", "icon": "👥"},
            {"label": "Settings", "href": "#settings", "icon": "⚙️"},
        ],
        "hero_headline": "<span class='gradient-text'>{title}</span> Dashboard",
        "hero_sub": "Real-time insights at your fingertips.",
        "default_theme": "dark",
    },
}


# =====================================================================
#  CSS GENERATOR
# =====================================================================

def _generate_css(theme: dict, site_type: str) -> str:
    t = theme
    is_dashboard = site_type == "dashboard"

    return f"""/* ========================================
   Generated by AERIS
   Modern Production-Ready Stylesheet
   ======================================== */

/* === Reset & Base === */
*, *::before, *::after {{ margin: 0; padding: 0; box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}
body {{
  background: {t['bg']};
  color: {t['text']};
  font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
  line-height: 1.7;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}}
a {{ color: {t['accent']}; text-decoration: none; transition: color 0.3s ease; }}
a:hover {{ color: {t['accent2']}; }}
img {{ max-width: 100%; height: auto; }}

/* === Utility Classes === */
.container {{ max-width: 1200px; margin: 0 auto; padding: 0 24px; }}
.gradient-text {{
  background: {t['gradient']};
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}}
.section-title {{
  font-size: clamp(28px, 4vw, 42px);
  font-weight: 800;
  letter-spacing: -0.03em;
  margin-bottom: 16px;
  line-height: 1.15;
}}
.section-sub {{
  font-size: 17px;
  color: {t['muted']};
  max-width: 600px;
  margin: 0 auto 48px;
}}
.section {{ padding: 100px 0; }}

/* === Glass Card === */
.glass {{
  background: {t['glass']};
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid {t['glass_border']};
  border-radius: 20px;
}}

/* === Navigation === */
.navbar {{
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 1000;
  padding: 16px 0;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}}
.navbar.scrolled {{
  background: {t['glass']};
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid {t['glass_border']};
  padding: 10px 0;
}}
.nav-inner {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 24px;
}}
.logo {{
  font-size: 22px;
  font-weight: 800;
  background: {t['gradient']};
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.02em;
}}
.nav-links {{
  display: flex;
  gap: 32px;
  list-style: none;
  align-items: center;
}}
.nav-links a {{
  color: {t['muted']};
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: color 0.3s ease;
  position: relative;
}}
.nav-links a::after {{
  content: '';
  position: absolute;
  bottom: -4px; left: 0;
  width: 0; height: 2px;
  background: {t['gradient']};
  transition: width 0.3s ease;
}}
.nav-links a:hover {{ color: {t['text']}; }}
.nav-links a:hover::after {{ width: 100%; }}
.nav-links a.active {{ color: {t['text']}; }}
.nav-links a.active::after {{ width: 100%; }}

/* Mobile Menu Toggle */
.menu-toggle {{
  display: none;
  flex-direction: column;
  gap: 5px;
  cursor: pointer;
  z-index: 1001;
  background: none;
  border: none;
  padding: 4px;
}}
.menu-toggle span {{
  display: block;
  width: 24px;
  height: 2px;
  background: {t['text']};
  border-radius: 2px;
  transition: all 0.3s ease;
}}

/* === Hero Section === */
.hero {{
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 120px 24px 80px;
  position: relative;
  overflow: hidden;
}}
.hero::before {{
  content: '';
  position: absolute;
  top: -50%;
  left: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 30% 40%, {t['accent']}15, transparent 50%),
              radial-gradient(circle at 70% 60%, {t['accent2']}12, transparent 50%),
              radial-gradient(circle at 50% 80%, {t['accent3']}08, transparent 40%);
  animation: heroOrb 20s ease-in-out infinite alternate;
  z-index: 0;
}}
@keyframes heroOrb {{
  0% {{ transform: translate(0, 0) rotate(0deg); }}
  50% {{ transform: translate(-3%, 2%) rotate(180deg); }}
  100% {{ transform: translate(2%, -2%) rotate(360deg); }}
}}
.hero-content {{
  position: relative;
  z-index: 1;
  max-width: 800px;
}}
.hero h1 {{
  font-size: clamp(36px, 6vw, 72px);
  font-weight: 900;
  letter-spacing: -0.04em;
  line-height: 1.08;
  margin-bottom: 24px;
}}
.hero p {{
  font-size: clamp(16px, 2vw, 20px);
  color: {t['muted']};
  max-width: 600px;
  margin: 0 auto 40px;
  line-height: 1.7;
}}
.hero-actions {{
  display: flex;
  gap: 16px;
  justify-content: center;
  flex-wrap: wrap;
}}

/* === Buttons === */
.btn {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 15px;
  cursor: pointer;
  text-decoration: none;
  border: none;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}}
.btn-primary {{
  background: {t['gradient']};
  color: white;
  box-shadow: 0 4px 20px {t['accent']}40;
}}
.btn-primary:hover {{
  transform: translateY(-3px);
  box-shadow: 0 8px 40px {t['accent']}50;
  color: white;
}}
.btn-secondary {{
  background: transparent;
  color: {t['text']};
  border: 1px solid {t['border_hover']};
}}
.btn-secondary:hover {{
  background: {t['surface2']};
  border-color: {t['accent']};
  transform: translateY(-2px);
  color: {t['text']};
}}

/* === Feature/Service Cards === */
.card-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
}}
.card {{
  background: {t['surface']};
  border: 1px solid {t['border']};
  border-radius: 20px;
  padding: 36px;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}}
.card::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: {t['gradient']};
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.4s ease;
}}
.card:hover {{
  border-color: {t['border_hover']};
  transform: translateY(-6px);
  box-shadow: 0 20px 60px rgba(0,0,0,0.15);
}}
.card:hover::before {{ transform: scaleX(1); }}
.card-icon {{
  font-size: 36px;
  margin-bottom: 20px;
  display: inline-block;
  animation: iconFloat 3s ease-in-out infinite;
}}
@keyframes iconFloat {{
  0%, 100% {{ transform: translateY(0); }}
  50% {{ transform: translateY(-8px); }}
}}
.card h3 {{
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 12px;
  letter-spacing: -0.02em;
}}
.card p {{
  font-size: 15px;
  color: {t['muted']};
  line-height: 1.7;
}}

/* === Stats Section === */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 24px;
  text-align: center;
}}
.stat-item {{
  padding: 32px 16px;
}}
.stat-value {{
  font-size: 42px;
  font-weight: 900;
  background: {t['gradient']};
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  letter-spacing: -0.03em;
}}
.stat-label {{
  font-size: 13px;
  color: {t['muted']};
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-top: 6px;
  font-weight: 600;
}}

/* === Testimonial Cards === */
.testimonial-card {{
  background: {t['surface']};
  border: 1px solid {t['border']};
  border-radius: 20px;
  padding: 32px;
  position: relative;
}}
.testimonial-card .quote {{
  font-size: 16px;
  color: {t['text2']};
  line-height: 1.8;
  margin-bottom: 20px;
  font-style: italic;
}}
.testimonial-card .author {{
  font-size: 14px;
  font-weight: 700;
  color: {t['text']};
}}
.testimonial-card .role {{
  font-size: 13px;
  color: {t['muted']};
}}

/* === Pricing Cards === */
.pricing-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 24px;
  align-items: start;
}}
.pricing-card {{
  background: {t['surface']};
  border: 1px solid {t['border']};
  border-radius: 20px;
  padding: 40px 32px;
  text-align: center;
  transition: all 0.4s ease;
}}
.pricing-card.featured {{
  border-color: {t['accent']};
  transform: scale(1.05);
  box-shadow: 0 20px 60px {t['accent']}20;
}}
.pricing-card:hover {{
  transform: translateY(-4px);
  box-shadow: 0 16px 48px rgba(0,0,0,0.12);
}}
.pricing-card .plan-name {{
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.pricing-card .price {{
  font-size: 48px;
  font-weight: 900;
  margin: 16px 0;
  background: {t['gradient']};
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.pricing-card .price span {{
  font-size: 16px;
  font-weight: 500;
  -webkit-text-fill-color: {t['muted']};
}}
.pricing-card ul {{
  list-style: none;
  margin: 24px 0 32px;
  text-align: left;
}}
.pricing-card ul li {{
  padding: 8px 0;
  font-size: 14px;
  color: {t['text2']};
  border-bottom: 1px solid {t['border']};
}}
.pricing-card ul li::before {{
  content: '✓';
  color: {t['accent3']};
  margin-right: 10px;
  font-weight: 700;
}}

/* === Contact Form === */
.contact-form {{
  max-width: 600px;
  margin: 0 auto;
}}
.form-group {{
  margin-bottom: 20px;
}}
.form-group label {{
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: {t['muted']};
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}}
.form-group input,
.form-group textarea,
.form-group select {{
  width: 100%;
  padding: 14px 18px;
  background: {t['surface2']};
  border: 1px solid {t['border']};
  border-radius: 12px;
  color: {t['text']};
  font-size: 15px;
  font-family: inherit;
  transition: all 0.3s ease;
  outline: none;
}}
.form-group input:focus,
.form-group textarea:focus {{
  border-color: {t['accent']};
  box-shadow: 0 0 0 3px {t['accent']}15;
}}
.form-group textarea {{
  min-height: 140px;
  resize: vertical;
}}

/* === Project / Work Grid === */
.project-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 28px;
}}
.project-card {{
  border-radius: 20px;
  overflow: hidden;
  background: {t['surface']};
  border: 1px solid {t['border']};
  transition: all 0.4s ease;
}}
.project-card:hover {{
  transform: translateY(-8px);
  box-shadow: 0 24px 64px rgba(0,0,0,0.15);
}}
.project-thumb {{
  width: 100%;
  height: 220px;
  background: {t['gradient']};
  background-size: cover;
  background-position: center;
  position: relative;
  overflow: hidden;
}}
.project-thumb img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.5s ease;
}}
.project-card:hover .project-thumb img {{
  transform: scale(1.08);
}}
.project-thumb::after {{
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, {t['accent']}20, {t['accent2']}20);
  z-index: 1;
}}
/* === Hero Image === */
.hero-bg-image {{
  position: absolute;
  inset: 0;
  z-index: 0;
}}
.hero-bg-image img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.25;
  filter: blur(2px);
}}
/* === Testimonial Avatars === */
.testimonial-avatar {{
  width: 48px;
  height: 48px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid {t['accent']};
  margin-bottom: 12px;
}}
/* === About Image === */
.about-image {{
  width: 100%;
  border-radius: 20px;
  overflow: hidden;
  margin-bottom: 24px;
}}
.about-image img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 20px;
  transition: transform 0.5s ease;
}}
.about-image:hover img {{
  transform: scale(1.03);
}}
.project-info {{
  padding: 24px;
}}
.project-info h3 {{
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 8px;
}}
.project-info p {{
  font-size: 14px;
  color: {t['muted']};
}}
.project-tags {{
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}}
.tag {{
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  background: {t['accent']}15;
  color: {t['accent']};
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* === Footer === */
footer {{
  padding: 60px 0 30px;
  border-top: 1px solid {t['border']};
}}
.footer-grid {{
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: 40px;
  margin-bottom: 40px;
}}
.footer-brand p {{
  color: {t['muted']};
  font-size: 14px;
  margin-top: 12px;
  line-height: 1.7;
}}
.footer-links h4 {{
  font-size: 14px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 16px;
  color: {t['text']};
}}
.footer-links ul {{ list-style: none; }}
.footer-links li {{ margin-bottom: 10px; }}
.footer-links a {{
  color: {t['muted']};
  font-size: 14px;
  transition: color 0.2s ease;
}}
.footer-links a:hover {{ color: {t['accent']}; }}
.footer-bottom {{
  text-align: center;
  padding-top: 24px;
  border-top: 1px solid {t['border']};
  font-size: 13px;
  color: {t['muted']};
}}

/* === Scroll Animations === */
.reveal {{
  opacity: 0;
  transform: translateY(40px);
  transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}}
.reveal.visible {{
  opacity: 1;
  transform: translateY(0);
}}
.reveal-left {{
  opacity: 0;
  transform: translateX(-40px);
  transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}}
.reveal-left.visible {{
  opacity: 1;
  transform: translateX(0);
}}
.reveal-right {{
  opacity: 0;
  transform: translateX(40px);
  transition: all 0.8s cubic-bezier(0.4, 0, 0.2, 1);
}}
.reveal-right.visible {{
  opacity: 1;
  transform: translateX(0);
}}

/* === Loading Spinner === */
.page-loader {{
  position: fixed;
  inset: 0;
  background: {t['bg']};
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  transition: opacity 0.5s ease;
}}
.page-loader.hidden {{ opacity: 0; pointer-events: none; }}
.spinner {{
  width: 48px;
  height: 48px;
  border: 3px solid {t['border']};
  border-top-color: {t['accent']};
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}

/* === Dashboard Specific === */
{''.join(["""
.dashboard-layout {
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: 100vh;
}
.sidebar {
  background: """ + t['surface'] + """;
  border-right: 1px solid """ + t['border'] + """;
  padding: 24px 16px;
  position: fixed;
  top: 0; left: 0; bottom: 0;
  width: 260px;
  overflow-y: auto;
  z-index: 100;
}
.sidebar-logo {
  font-size: 20px;
  font-weight: 800;
  padding: 8px 12px;
  margin-bottom: 32px;
}
.sidebar-nav a {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  color: """ + t['muted'] + """;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
  transition: all 0.2s ease;
}
.sidebar-nav a:hover,
.sidebar-nav a.active {
  background: """ + t['accent'] + """15;
  color: """ + t['accent'] + """;
}
.main-content {
  margin-left: 260px;
  padding: 32px;
}
.dash-header {
  margin-bottom: 32px;
}
.dash-header h1 {
  font-size: 28px;
  font-weight: 800;
}
.dash-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
}
.dash-stat-card {
  background: """ + t['surface'] + """;
  border: 1px solid """ + t['border'] + """;
  border-radius: 16px;
  padding: 24px;
  transition: all 0.3s ease;
}
.dash-stat-card:hover {
  border-color: """ + t['border_hover'] + """;
  transform: translateY(-2px);
  box-shadow: 0 8px 30px rgba(0,0,0,0.1);
}
.dash-panels {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 24px;
}
.dash-panel {
  background: """ + t['surface'] + """;
  border: 1px solid """ + t['border'] + """;
  border-radius: 16px;
  padding: 24px;
}
.dash-panel h3 {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 16px;
}
"""] if is_dashboard else [])}

/* === Responsive === */
@media (max-width: 1024px) {{
  .footer-grid {{ grid-template-columns: 1fr 1fr; gap: 30px; }}
  {''.join(["""
  .dashboard-layout { grid-template-columns: 1fr; }
  .sidebar { transform: translateX(-100%); }
  .main-content { margin-left: 0; }
  .dash-panels { grid-template-columns: 1fr; }
  """] if is_dashboard else [])}
}}
@media (max-width: 768px) {{
  .nav-links {{ display: none; }}
  .nav-links.active {{
    display: flex;
    flex-direction: column;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: {t['bg']};
    justify-content: center;
    align-items: center;
    gap: 24px;
    z-index: 999;
  }}
  .nav-links.active a {{ font-size: 20px; }}
  .menu-toggle {{ display: flex; }}
  .hero {{ padding: 100px 20px 60px; }}
  .hero h1 {{ font-size: 32px; }}
  .hero-actions {{ flex-direction: column; align-items: center; }}
  .card-grid {{ grid-template-columns: 1fr; }}
  .project-grid {{ grid-template-columns: 1fr; }}
  .pricing-grid {{ grid-template-columns: 1fr; }}
  .pricing-card.featured {{ transform: none; }}
  .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .footer-grid {{ grid-template-columns: 1fr; }}
  .section {{ padding: 60px 0; }}
}}

/* === Print === */
@media print {{
  .navbar, .menu-toggle, .page-loader {{ display: none; }}
  body {{ color: #1a1a2e; background: white; }}
  .hero {{ min-height: auto; padding: 40px 0; }}
}}
"""


# =====================================================================
#  JAVASCRIPT GENERATOR
# =====================================================================

def _generate_js(title: str) -> str:
    return f"""// {title} — Generated by AERIS
// Modern interactive website scripts
(function() {{
  'use strict';

  // === Page Loader ===
  window.addEventListener('load', function() {{
    const loader = document.querySelector('.page-loader');
    if (loader) {{
      setTimeout(function() {{ loader.classList.add('hidden'); }}, 400);
      setTimeout(function() {{ loader.remove(); }}, 900);
    }}
  }});

  // === Navbar Scroll Effect ===
  const navbar = document.querySelector('.navbar');
  if (navbar) {{
    let lastScroll = 0;
    window.addEventListener('scroll', function() {{
      const currentScroll = window.pageYOffset;
      if (currentScroll > 60) {{
        navbar.classList.add('scrolled');
      }} else {{
        navbar.classList.remove('scrolled');
      }}
      lastScroll = currentScroll;
    }});
  }}

  // === Mobile Menu ===
  const menuToggle = document.querySelector('.menu-toggle');
  const navLinks = document.querySelector('.nav-links');
  if (menuToggle && navLinks) {{
    menuToggle.addEventListener('click', function() {{
      navLinks.classList.toggle('active');
      const spans = menuToggle.querySelectorAll('span');
      if (navLinks.classList.contains('active')) {{
        spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
        spans[1].style.opacity = '0';
        spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
      }} else {{
        spans[0].style.transform = 'none';
        spans[1].style.opacity = '1';
        spans[2].style.transform = 'none';
      }}
    }});
    // Close menu when clicking a link
    navLinks.querySelectorAll('a').forEach(function(link) {{
      link.addEventListener('click', function() {{
        navLinks.classList.remove('active');
        const spans = menuToggle.querySelectorAll('span');
        spans[0].style.transform = 'none';
        spans[1].style.opacity = '1';
        spans[2].style.transform = 'none';
      }});
    }});
  }}

  // === Scroll Reveal Animations ===
  const revealElements = document.querySelectorAll('.reveal, .reveal-left, .reveal-right');
  const revealObserver = new IntersectionObserver(function(entries) {{
    entries.forEach(function(entry) {{
      if (entry.isIntersecting) {{
        entry.target.classList.add('visible');
      }}
    }});
  }}, {{ threshold: 0.1, rootMargin: '0px 0px -50px 0px' }});
  revealElements.forEach(function(el) {{ revealObserver.observe(el); }});

  // === Smooth Scroll for Anchor Links ===
  document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {{
    anchor.addEventListener('click', function(e) {{
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {{
        target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      }}
    }});
  }});

  // === Active Nav Link Highlight ===
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a').forEach(function(link) {{
    const href = link.getAttribute('href');
    if (href === currentPage || (currentPage === '' && href === 'index.html')) {{
      link.classList.add('active');
    }}
  }});

  // === Contact Form Handler ===
  const contactForm = document.getElementById('contact-form');
  if (contactForm) {{
    contactForm.addEventListener('submit', function(e) {{
      e.preventDefault();
      const btn = contactForm.querySelector('button[type="submit"]');
      const original = btn.textContent;
      btn.textContent = 'Sending...';
      btn.disabled = true;
      setTimeout(function() {{
        btn.textContent = '✓ Message Sent!';
        btn.style.background = 'linear-gradient(135deg, #10b981, #059669)';
        contactForm.reset();
        setTimeout(function() {{
          btn.textContent = original;
          btn.style.background = '';
          btn.disabled = false;
        }}, 2500);
      }}, 1200);
    }});
  }}

  // === Counter Animation ===
  const counters = document.querySelectorAll('[data-count]');
  const countObserver = new IntersectionObserver(function(entries) {{
    entries.forEach(function(entry) {{
      if (entry.isIntersecting) {{
        const el = entry.target;
        const target = parseInt(el.getAttribute('data-count'));
        const suffix = el.getAttribute('data-suffix') || '';
        const prefix = el.getAttribute('data-prefix') || '';
        const duration = 2000;
        const startTime = performance.now();
        function updateCount(currentTime) {{
          const elapsed = currentTime - startTime;
          const progress = Math.min(elapsed / duration, 1);
          const eased = 1 - Math.pow(1 - progress, 3);
          el.textContent = prefix + Math.floor(target * eased).toLocaleString() + suffix;
          if (progress < 1) requestAnimationFrame(updateCount);
        }}
        requestAnimationFrame(updateCount);
        countObserver.unobserve(el);
      }}
    }});
  }}, {{ threshold: 0.5 }});
  counters.forEach(function(c) {{ countObserver.observe(c); }});

  // === Tilt Effect on Cards ===
  document.querySelectorAll('.card, .project-card').forEach(function(card) {{
    card.addEventListener('mousemove', function(e) {{
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = (y - centerY) / 20;
      const rotateY = (centerX - x) / 20;
      card.style.transform = 'perspective(1000px) rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg) translateY(-6px)';
    }});
    card.addEventListener('mouseleave', function() {{
      card.style.transform = '';
    }});
  }});

  console.log('{title} — Powered by AERIS');
}})();
"""


# =====================================================================
#  HTML PAGE BUILDERS
# =====================================================================

def _html_head(title: str, page_title: str, description: str, lang_code: str = "en") -> str:
    # Choose appropriate Google Font for the language
    font_link = 'https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap'
    if lang_code in ('ja', 'zh', 'ko'):
        font_link = 'https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@300;400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700;800;900&display=swap'
    elif lang_code in ('ar', 'ur'):
        font_link = 'https://fonts.googleapis.com/css2?family=Noto+Sans+Arabic:wght@300;400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700;800;900&display=swap'
    elif lang_code in ('hi', 'mr', 'bn', 'gu', 'pa', 'ta', 'te'):
        font_link = 'https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@300;400;500;600;700;800;900&family=Inter:wght@300;400;500;600;700;800;900&display=swap'
    dir_attr = ' dir="rtl"' if lang_code in ('ar', 'ur') else ''
    return f"""<!DOCTYPE html>
<html lang="{lang_code}"{dir_attr}>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{page_title} | {title}</title>
  <meta name="description" content="{description}"/>
  <meta name="generator" content="AERIS"/>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="{font_link}" rel="stylesheet"/>
  <link rel="stylesheet" href="styles.css"/>
</head>"""


def _html_navbar(title: str, nav_items: list[dict], current_page: str = "index.html") -> str:
    links = "\n      ".join(
        f'<li><a href="{n["href"]}" {"class=\\'active\\'" if n["href"] == current_page else ""}>{n["label"]}</a></li>'
        for n in nav_items
    )
    return f"""
  <!-- Page Loader -->
  <div class="page-loader"><div class="spinner"></div></div>

  <!-- Navigation -->
  <nav class="navbar">
    <div class="nav-inner">
      <a href="index.html" class="logo">{title}</a>
      <ul class="nav-links">
        {links}
      </ul>
      <button class="menu-toggle" aria-label="Toggle menu">
        <span></span><span></span><span></span>
      </button>
    </div>
  </nav>"""


def _html_footer(title: str, nav_items: list[dict], year: int, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    links_html = "\n        ".join(
        f'<li><a href="{n["href"]}">{n["label"]}</a></li>'
        for n in nav_items
    )
    return f"""
  <!-- Footer -->
  <footer>
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <div class="logo">{title}</div>
          <p>{ui.get('footer_desc', 'Built with passion and powered by modern technology.')}</p>
        </div>
        <div class="footer-links">
          <h4>{ui.get('footer_nav', 'Navigation')}</h4>
          <ul>
            {links_html}
          </ul>
        </div>
        <div class="footer-links">
          <h4>{ui.get('footer_connect', 'Connect')}</h4>
          <ul>
            <li><a href="#">Twitter / X</a></li>
            <li><a href="#">LinkedIn</a></li>
            <li><a href="#">GitHub</a></li>
            <li><a href="#">Instagram</a></li>
          </ul>
        </div>
        <div class="footer-links">
          <h4>{ui.get('footer_legal', 'Legal')}</h4>
          <ul>
            <li><a href="#">{ui.get('footer_privacy', 'Privacy Policy')}</a></li>
            <li><a href="#">{ui.get('footer_terms', 'Terms of Service')}</a></li>
            <li><a href="#">{ui.get('footer_cookies', 'Cookie Policy')}</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <p>&copy; {year} {title}. {ui.get('footer_rights', 'All rights reserved.')} Generated by AERIS.</p>
      </div>
    </div>
  </footer>
  <script src="script.js"></script>
</body>
</html>"""


def _build_hero_section(config: dict, title: str, images: ImageBank = None,
                       ui: dict = None, hero_local_img: str = None) -> str:
    ui = ui or _UI_STRINGS_EN
    headline = config["hero_headline"].format(title=title)
    hero_sub = config.get("hero_sub_translated") or config["hero_sub"]

    # Determine hero background image
    hero_img_html = ""
    if hero_local_img:
        hero_img_html = f'<div class="hero-bg-image"><img src="{hero_local_img}" alt="{title} hero" loading="eager"/></div>'
    elif images:
        hero_img_html = f'<div class="hero-bg-image"><img src="{images.hero_url()}" alt="{title} hero" loading="eager"/></div>'

    return f"""
  <!-- Hero Section -->
  <section class="hero">
    {hero_img_html}
    <div class="hero-content reveal">
      <h1>{headline}</h1>
      <p>{hero_sub}</p>
      <div class="hero-actions">
        <a href="#features" class="btn btn-primary">{ui.get('hero_cta', 'Explore More')}</a>
        <a href="contact.html" class="btn btn-secondary">{ui.get('hero_cta2', 'Get in Touch')}</a>
      </div>
    </div>
  </section>"""


def _build_features_section(site_type: str, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    features_map = {
        "portfolio": [
            ("🎨", "Creative Design", "Crafting pixel-perfect, visually stunning interfaces that tell your story."),
            ("⚡", "Fast & Modern", "Built with the latest technologies for blazing-fast performance."),
            ("📱", "Responsive", "Flawless experiences across every device and screen size."),
            ("🔧", "Clean Code", "Well-structured, maintainable code following best practices."),
        ],
        "business": [
            ("🚀", "Innovation First", "We leverage cutting-edge technology to drive business growth."),
            ("🛡️", "Enterprise Security", "Bank-grade security protocols protecting your data 24/7."),
            ("📊", "Data Analytics", "Actionable insights powered by advanced analytics and AI."),
            ("🤝", "24/7 Support", "Dedicated team available around the clock for your needs."),
        ],
        "landing": [
            ("⚡", "Lightning Fast", "Optimized for peak performance with sub-second load times."),
            ("🔒", "Secure by Default", "Enterprise-grade encryption and security at every layer."),
            ("🌍", "Global Scale", "Built to handle millions of users across the globe."),
            ("🧠", "AI-Powered", "Intelligent automation that learns and adapts to your needs."),
        ],
        "agency": [
            ("🎨", "Brand Strategy", "Crafting compelling brand identities that resonate with audiences."),
            ("💻", "Web Development", "Full-stack development with modern frameworks and best practices."),
            ("📱", "Mobile Apps", "Native and cross-platform mobile applications that delight users."),
            ("📈", "Growth Marketing", "Data-driven strategies that accelerate your business growth."),
        ],
        "ecommerce": [
            ("🛍️", "Easy Shopping", "Intuitive browsing and one-click checkout experiences."),
            ("🚚", "Fast Delivery", "Same-day and next-day delivery options for all orders."),
            ("🔄", "Easy Returns", "Hassle-free 30-day return policy on all products."),
            ("💳", "Secure Payments", "End-to-end encrypted transactions for complete peace of mind."),
        ],
        "blog": [
            ("📝", "Quality Content", "In-depth articles and analysis from industry experts."),
            ("🔍", "Easy Discovery", "Smart search and categorization for finding what matters."),
            ("📧", "Newsletter", "Weekly curated insights delivered straight to your inbox."),
            ("💬", "Community", "Engage with a vibrant community of passionate readers."),
        ],
    }

    features = features_map.get(site_type, features_map["landing"])
    cards = "\n      ".join(
        f"""<div class="card reveal" style="transition-delay: {i * 0.1}s">
        <div class="card-icon">{icon}</div>
        <h3>{name}</h3>
        <p>{desc}</p>
      </div>"""
        for i, (icon, name, desc) in enumerate(features)
    )

    return f"""
  <!-- Features Section -->
  <section class="section" id="features">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">{ui.get('features_title', 'Why Choose')} <span class="gradient-text">{'Us' if ui.get('features_title','').endswith('Us') else ''}</span></h2>
        <p class="section-sub">{ui.get('features_sub', 'We combine innovation with expertise to deliver exceptional results.')}</p>
      </div>
      <div class="card-grid">
        {cards}
      </div>
    </div>
  </section>"""


def _build_stats_section(ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    return f"""
  <!-- Stats Section -->
  <section class="section" style="padding: 60px 0;">
    <div class="container">
      <div class="stats-grid reveal">
        <div class="stat-item">
          <div class="stat-value" data-count="150" data-suffix="+">0+</div>
          <div class="stat-label">{ui.get('stats_projects', 'Projects Completed')}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" data-count="50" data-suffix="+">0+</div>
          <div class="stat-label">{ui.get('stats_clients', 'Happy Clients')}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" data-count="5" data-suffix="">0</div>
          <div class="stat-label">{ui.get('stats_years', 'Years Experience')}</div>
        </div>
        <div class="stat-item">
          <div class="stat-value" data-count="99" data-suffix="%">0%</div>
          <div class="stat-label">{ui.get('stats_satisfaction', 'Client Satisfaction')}</div>
        </div>
      </div>
    </div>
  </section>"""


def _build_testimonials_section(images: ImageBank = None, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    ib = images or _get_image_bank("landing")
    return f"""
  <!-- Testimonials Section -->
  <section class="section" id="testimonials">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">{ui.get('testimonials_title', 'What People Say').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('testimonials_title', 'What People Say').rsplit(' ', 1)[-1]}</span></h2>
        <p class="section-sub">{ui.get('testimonials_sub', "Don't just take our word for it.")}</p>
      </div>
      <div class="card-grid">
        <div class="testimonial-card reveal" style="transition-delay: 0s">
          <img class="testimonial-avatar" src="{ib.testimonial_avatar(0)}" alt="Alex Johnson" loading="lazy"/>
          <p class="quote">"Absolutely incredible work. The attention to detail and quality of execution exceeded all our expectations. Truly world-class."</p>
          <p class="author">Alex Johnson</p>
          <p class="role">CEO, TechVentures</p>
        </div>
        <div class="testimonial-card reveal" style="transition-delay: 0.1s">
          <img class="testimonial-avatar" src="{ib.testimonial_avatar(1)}" alt="Sarah Chen" loading="lazy"/>
          <p class="quote">"Working with this team was a game-changer. They delivered a solution that transformed how we operate. Highly recommended."</p>
          <p class="author">Sarah Chen</p>
          <p class="role">Founder, InnovateCo</p>
        </div>
        <div class="testimonial-card reveal" style="transition-delay: 0.2s">
          <img class="testimonial-avatar" src="{ib.testimonial_avatar(2)}" alt="Marcus Rivera" loading="lazy"/>
          <p class="quote">"The design quality is outstanding. Our users love the new interface, and our engagement metrics have skyrocketed since launch."</p>
          <p class="author">Marcus Rivera</p>
          <p class="role">Product Lead, DesignHub</p>
        </div>
      </div>
    </div>
  </section>"""


def _build_pricing_section(ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    return f"""
  <!-- Pricing Section -->
  <section class="section" id="pricing">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">{ui.get('pricing_title', 'Simple Pricing').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('pricing_title', 'Simple Pricing').rsplit(' ', 1)[-1]}</span></h2>
        <p class="section-sub">{ui.get('pricing_sub', 'Transparent plans that scale with your needs.')}</p>
      </div>
      <div class="pricing-grid reveal">
        <div class="pricing-card">
          <div class="plan-name">Starter</div>
          <div class="price">$29<span>/mo</span></div>
          <ul>
            <li>5 Projects</li>
            <li>Basic Analytics</li>
            <li>Email Support</li>
            <li>API Access</li>
          </ul>
          <a href="#contact" class="btn btn-secondary" style="width:100%; justify-content:center;">{ui.get('get_started', 'Get Started')}</a>
        </div>
        <div class="pricing-card featured">
          <div class="plan-name">Professional</div>
          <div class="price">$79<span>/mo</span></div>
          <ul>
            <li>Unlimited Projects</li>
            <li>Advanced Analytics</li>
            <li>Priority Support</li>
            <li>Custom Integrations</li>
            <li>Team Collaboration</li>
          </ul>
          <a href="#contact" class="btn btn-primary" style="width:100%; justify-content:center;">{ui.get('get_started', 'Get Started')}</a>
        </div>
        <div class="pricing-card">
          <div class="plan-name">Enterprise</div>
          <div class="price">$199<span>/mo</span></div>
          <ul>
            <li>Everything in Pro</li>
            <li>Dedicated Account Manager</li>
            <li>SLA Guarantee</li>
            <li>Custom Development</li>
          </ul>
          <a href="#contact" class="btn btn-secondary" style="width:100%; justify-content:center;">{ui.get('contact_sales', 'Contact Sales')}</a>
        </div>
      </div>
    </div>
  </section>"""


def _build_contact_section(ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    return f"""
  <!-- Contact Section -->
  <section class="section" id="contact">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">{ui.get('contact_title', 'Get in Touch').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('contact_title', 'Get in Touch').rsplit(' ', 1)[-1]}</span></h2>
        <p class="section-sub">{ui.get('contact_sub', "Have a question? We'd love to hear from you.")}</p>
      </div>
      <form class="contact-form glass reveal" style="padding: 48px;" id="contact-form">
        <div class="form-group">
          <label for="name">{ui.get('contact_name', 'Your Name')}</label>
          <input type="text" id="name" name="name" placeholder="John Doe" required/>
        </div>
        <div class="form-group">
          <label for="email">{ui.get('contact_email', 'Email Address')}</label>
          <input type="email" id="email" name="email" placeholder="john@example.com" required/>
        </div>
        <div class="form-group">
          <label for="subject">{ui.get('contact_subject', 'Subject')}</label>
          <input type="text" id="subject" name="subject" placeholder="How can we help?"/>
        </div>
        <div class="form-group">
          <label for="message">{ui.get('contact_message', 'Message')}</label>
          <textarea id="message" name="message" placeholder="Tell us about your project..." required></textarea>
        </div>
        <button type="submit" class="btn btn-primary" style="width:100%; justify-content:center;">{ui.get('contact_send', 'Send Message')}</button>
      </form>
    </div>
  </section>"""


def _build_projects_section(site_type: str, images: ImageBank = None, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    ib = images or _get_image_bank(site_type)
    projects_data = {
        "portfolio": [
            ("Project Alpha", "A cutting-edge web application built with React and Node.js", ["React", "Node.js", "MongoDB"]),
            ("Design System", "A comprehensive design system for enterprise applications", ["Figma", "CSS", "Storybook"]),
            ("Mobile App", "Cross-platform mobile application for fitness tracking", ["React Native", "Firebase", "TypeScript"]),
            ("AI Dashboard", "Real-time analytics dashboard powered by machine learning", ["Python", "TensorFlow", "D3.js"]),
            ("E-commerce", "Full-stack e-commerce platform with payment integration", ["Next.js", "Stripe", "PostgreSQL"]),
            ("SaaS Platform", "Cloud-based project management tool for remote teams", ["Vue.js", "AWS", "GraphQL"]),
        ],
        "agency": [
            ("Brand Revamp — TechCorp", "Complete brand identity redesign for a Fortune 500 company", ["Branding", "Strategy"]),
            ("E-commerce — LuxeStyle", "High-end fashion e-commerce with AR try-on features", ["E-commerce", "AR", "Web"]),
            ("App — HealthTrack", "Health and wellness tracking platform for 500K+ users", ["Mobile", "iOS", "Android"]),
            ("Campaign — GoGreen", "Viral social media campaign reaching 10M+ impressions", ["Marketing", "Social"]),
            ("Platform — EduLearn", "Online learning platform w/ live classes and AI tutoring", ["EdTech", "AI", "Web"]),
            ("Dashboard — DataFlow", "Real-time analytics dashboard for IoT sensor data", ["Analytics", "IoT", "Web"]),
        ],
    }

    projects = projects_data.get(site_type, projects_data["portfolio"])
    cards = "\n      ".join(
        f"""<div class="project-card reveal" style="transition-delay: {i * 0.1}s">
        <div class="project-thumb"><img src="{ib.project_url(i)}" alt="{name}" loading="lazy"/></div>
        <div class="project-info">
          <h3>{name}</h3>
          <p>{desc}</p>
          <div class="project-tags">
            {"".join(f'<span class="tag">{t}</span>' for t in tags)}
          </div>
        </div>
      </div>"""
        for i, (name, desc, tags) in enumerate(projects)
    )

    section_title = ui.get('projects_title', 'Featured Projects')

    return f"""
  <!-- Projects Section -->
  <section class="section" id="projects">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title"><span class="gradient-text">{section_title}</span></h2>
        <p class="section-sub">{ui.get('projects_sub', 'A showcase of our best work and achievements.')}</p>
      </div>
      <div class="project-grid">
        {cards}
      </div>
    </div>
  </section>"""


def _build_services_section(site_type: str) -> str:
    services_map = {
        "business": [
            ("💡", "Strategic Consulting", "We help businesses identify opportunities and develop data-driven strategies for sustainable growth.", "$2,500"),
            ("💻", "Digital Transformation", "End-to-end digital modernization including cloud migration, process automation, and AI integration.", "$5,000"),
            ("📊", "Data Analytics", "Turn your data into actionable insights with our advanced analytics and visualization solutions.", "$3,500"),
            ("🛡️", "Cybersecurity", "Comprehensive security audits, penetration testing, and ongoing protection for your digital assets.", "$4,000"),
            ("🎨", "UX/UI Design", "Beautiful, user-centered design that drives engagement and converts visitors into customers.", "$3,000"),
            ("📱", "Mobile Development", "Native and cross-platform mobile apps built for performance, scalability, and user delight.", "$8,000"),
        ],
        "agency": [
            ("🎨", "Brand Identity", "Logo design, brand guidelines, visual systems, and brand strategy that makes you unforgettable.", "$3,000"),
            ("💻", "Web Design & Dev", "Custom websites built with cutting-edge tech, stunning design, and conversion optimization.", "$6,000"),
            ("📱", "App Development", "iOS and Android applications with seamless UX and native performance.", "$12,000"),
            ("📈", "Digital Marketing", "SEO, PPC, social media, and content marketing strategies that deliver ROI.", "$2,500"),
            ("🎬", "Video Production", "Cinematic brand videos, product demos, and social content that captivates.", "$4,000"),
            ("🤖", "AI Integration", "Custom AI solutions, chatbots, and automation tools built for your business.", "$8,000"),
        ],
    }

    services = services_map.get(site_type, services_map["business"])
    cards = "\n      ".join(
        f"""<div class="card reveal" style="transition-delay: {i * 0.1}s">
        <div class="card-icon">{icon}</div>
        <h3>{name}</h3>
        <p>{desc}</p>
        <p style="margin-top:16px;font-size:20px;font-weight:800;" class="gradient-text">From {price}</p>
      </div>"""
        for i, (icon, name, desc, price) in enumerate(services)
    )

    return f"""
  <!-- Services Section -->
  <section class="section" id="services">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">Our <span class="gradient-text">Services</span></h2>
        <p class="section-sub">Comprehensive solutions tailored to your unique needs.</p>
      </div>
      <div class="card-grid">
        {cards}
      </div>
    </div>
  </section>"""


def _build_about_content(site_type: str, title: str, images: ImageBank = None, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    ib = images or _get_image_bank(site_type)
    if site_type == "portfolio":
        return f"""
  <section class="hero" style="min-height:60vh;">
    <div class="hero-content reveal">
      <h1>{ui.get('about_title', 'About')} <span class="gradient-text">Me</span></h1>
      <p>Passionate about crafting exceptional digital experiences that make a real impact.</p>
    </div>
  </section>
  <section class="section">
    <div class="container">
      <div class="card-grid" style="grid-template-columns: 1fr 1fr;">
        <div class="reveal-left">
          <div class="about-image">
            <img src="{ib.about_url()}" alt="About me" loading="lazy"/>
          </div>
          <h2 class="section-title" style="text-align:left;">{ui.get('about_story', 'My Story').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('about_story', 'My Story').rsplit(' ', 1)[-1]}</span></h2>
          <p style="color: var(--muted, #8886a0); font-size: 16px; line-height: 1.8; margin-bottom: 20px;">
            I'm a passionate developer and designer with over 5 years of experience building digital products. 
            I specialize in creating beautiful, functional, and user-centered applications that solve real-world problems.
          </p>
          <p style="color: var(--muted, #8886a0); font-size: 16px; line-height: 1.8; margin-bottom: 20px;">
            My journey started with a love for how technology can transform ideas into reality. 
            Today, I work with startups and established companies to bring their visions to life through clean code and stunning design.
          </p>
          <p style="color: var(--muted, #8886a0); font-size: 16px; line-height: 1.8;">
            When I'm not coding, you'll find me exploring new technologies, contributing to open-source projects, 
            or sharing my knowledge through articles and talks.
          </p>
        </div>
        <div class="reveal-right">
          <h3 style="font-size:18px; font-weight:700; margin-bottom:24px;">{ui.get('about_skills', 'Skills & Technologies')}</h3>
          <div style="display:flex; flex-wrap:wrap; gap:10px;">
            <span class="tag">JavaScript</span><span class="tag">TypeScript</span>
            <span class="tag">React</span><span class="tag">Next.js</span>
            <span class="tag">Node.js</span><span class="tag">Python</span>
            <span class="tag">Figma</span><span class="tag">CSS/SASS</span>
            <span class="tag">PostgreSQL</span><span class="tag">MongoDB</span>
            <span class="tag">Docker</span><span class="tag">AWS</span>
            <span class="tag">Git</span><span class="tag">REST APIs</span>
            <span class="tag">GraphQL</span><span class="tag">TailwindCSS</span>
          </div>
          <div style="margin-top:40px;">
            <h3 style="font-size:18px; font-weight:700; margin-bottom:16px;">{ui.get('about_timeline', 'Experience Timeline')}</h3>
            <div style="border-left:2px solid; border-image: linear-gradient(to bottom, #8b5cf6, #06b6d4) 1; padding-left:20px;">
              <div style="margin-bottom:24px;"><p style="font-weight:700;">Senior Developer — TechCorp</p><p style="font-size:13px; color: var(--muted, #8886a0);">2023 — Present</p></div>
              <div style="margin-bottom:24px;"><p style="font-weight:700;">Full-Stack Developer — StartupXYZ</p><p style="font-size:13px; color: var(--muted, #8886a0);">2021 — 2023</p></div>
              <div><p style="font-weight:700;">Junior Developer — WebAgency</p><p style="font-size:13px; color: var(--muted, #8886a0);">2019 — 2021</p></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>"""
    else:
        return f"""
  <section class="hero" style="min-height:60vh;">
    <div class="hero-content reveal">
      <h1>{ui.get('about_title', 'About')} <span class="gradient-text">{title}</span></h1>
      <p>Our mission is to deliver excellence through innovation and dedication.</p>
    </div>
  </section>
  <section class="section">
    <div class="container">
      <div class="card-grid" style="grid-template-columns: 1fr 1fr;">
        <div class="reveal-left">
          <div class="about-image">
            <img src="{ib.about_url()}" alt="About {title}" loading="lazy"/>
          </div>
          <h2 class="section-title" style="text-align:left;">{ui.get('about_mission', 'Our Mission').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('about_mission', 'Our Mission').rsplit(' ', 1)[-1]}</span></h2>
          <p style="color: var(--muted, #8886a0); font-size: 16px; line-height: 1.8; margin-bottom: 20px;">
            At {title}, we believe in the transformative power of technology. Founded with a passion for innovation, 
            we've grown into a trusted partner for businesses seeking digital excellence.
          </p>
          <p style="color: var(--muted, #8886a0); font-size: 16px; line-height: 1.8; margin-bottom: 20px;">
            Our team of experts brings together decades of experience in design, development, and strategy
            to deliver solutions that drive real business results.
          </p>
          <p style="color: var(--muted, #8886a0); font-size: 16px; line-height: 1.8;">
            We are committed to quality, transparency, and building lasting relationships with our clients.
            Every project is an opportunity to push boundaries and exceed expectations.
          </p>
        </div>
        <div class="reveal-right">
          <h3 style="font-size:18px; font-weight:700; margin-bottom:24px;">{ui.get('about_values', 'Our Values')}</h3>
          <div class="card" style="margin-bottom:16px;"><div class="card-icon" style="font-size:24px;">🎯</div><h3 style="font-size:16px;">Excellence</h3><p style="font-size:14px;">We strive for the highest quality in everything we do.</p></div>
          <div class="card" style="margin-bottom:16px;"><div class="card-icon" style="font-size:24px;">🤝</div><h3 style="font-size:16px;">Collaboration</h3><p style="font-size:14px;">Great things happen when talented people work together.</p></div>
          <div class="card"><div class="card-icon" style="font-size:24px;">🚀</div><h3 style="font-size:16px;">Innovation</h3><p style="font-size:14px;">We embrace new ideas and push the boundaries of what's possible.</p></div>
        </div>
      </div>
    </div>
  </section>"""


def _build_products_section(images: ImageBank = None, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    ib = images or _get_image_bank("ecommerce")
    products = [
        ("Premium Headphones", "Wireless noise-canceling headphones with studio-quality sound.", "$299.99"),
        ("Smart Watch Pro", "Advanced fitness and health tracking with seamless connectivity.", "$449.99"),
        ("Laptop Stand", "Ergonomic aluminum stand for improved posture and airflow.", "$89.99"),
        ("Mechanical Keyboard", "Cherry MX switches, RGB lighting, programmable keys.", "$179.99"),
        ("4K Webcam", "Ultra-HD camera with auto-focus and built-in ring light.", "$149.99"),
        ("USB-C Hub", "7-in-1 hub with 100W PD charging and 4K HDMI output.", "$69.99"),
    ]
    cards = "\n      ".join(
        f"""<div class="project-card reveal" style="transition-delay: {i * 0.1}s">
        <div class="project-thumb"><img src="{ib.project_url(i)}" alt="{name}" loading="lazy"/></div>
        <div class="project-info">
          <h3>{name}</h3>
          <p>{desc}</p>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px;">
            <span style="font-size:22px;font-weight:800;" class="gradient-text">{price}</span>
            <button class="btn btn-primary" style="padding:10px 20px;font-size:13px;">{ui.get('add_to_cart', 'Add to Cart')}</button>
          </div>
        </div>
      </div>"""
        for i, (name, desc, price) in enumerate(products)
    )
    return f"""
  <section class="section" id="products">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">{ui.get('products_title', 'Our Products').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('products_title', 'Our Products').rsplit(' ', 1)[-1]}</span></h2>
        <p class="section-sub">{ui.get('products_sub', 'Premium products designed for modern life.')}</p>
      </div>
      <div class="project-grid">
        {cards}
      </div>
    </div>
  </section>"""


def _build_articles_section(images: ImageBank = None, ui: dict = None) -> str:
    ui = ui or _UI_STRINGS_EN
    ib = images or _get_image_bank("blog")
    articles = [
        ("The Future of AI in 2025", "Exploring how artificial intelligence is reshaping industries and what to expect next.", "Apr 10, 2025", "8 min read"),
        ("Building Scalable Systems", "A deep dive into architecture patterns that help you scale from startup to enterprise.", "Apr 5, 2025", "12 min read"),
        ("Design Systems That Work", "How to create and maintain a design system that actually improves your team's workflow.", "Mar 28, 2025", "6 min read"),
        ("The Art of Clean Code", "Why readability matters more than cleverness and how to write code your team will love.", "Mar 20, 2025", "10 min read"),
        ("Remote Work Best Practices", "Proven strategies for productive remote work and building strong distributed teams.", "Mar 15, 2025", "7 min read"),
        ("Web Performance Optimization", "Essential techniques to make your website load in under 2 seconds.", "Mar 8, 2025", "9 min read"),
    ]
    cards = "\n      ".join(
        f"""<div class="card reveal" style="transition-delay: {i * 0.1}s; cursor: pointer;">
        <img src="{ib.project_url(i)}" alt="{title}" style="width:100%;height:180px;object-fit:cover;border-radius:12px;margin-bottom:16px;" loading="lazy"/>
        <p style="font-size:12px;color:var(--muted,#8886a0);margin-bottom:12px;text-transform:uppercase;letter-spacing:0.06em;">{date} · {read_time}</p>
        <h3 style="margin-bottom:12px;">{title}</h3>
        <p>{desc}</p>
        <a href="#" style="display:inline-block;margin-top:16px;font-weight:600;font-size:14px;">{ui.get('read_more', 'Read More')} →</a>
      </div>"""
        for i, (title, desc, date, read_time) in enumerate(articles)
    )

    return f"""
  <section class="section" id="articles">
    <div class="container">
      <div style="text-align:center; margin-bottom: 60px;" class="reveal">
        <h2 class="section-title">{ui.get('articles_title', 'Latest Articles').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('articles_title', 'Latest Articles').rsplit(' ', 1)[-1]}</span></h2>
        <p class="section-sub">{ui.get('articles_sub', 'Insights and ideas from our team.')}</p>
      </div>
      <div class="card-grid">
        {cards}
      </div>
    </div>
  </section>"""


def _build_dashboard_page(title: str, theme: dict) -> str:
    t = theme
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title} Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="styles.css"/>
</head>
<body>
  <div class="page-loader"><div class="spinner"></div></div>
  <div class="dashboard-layout">
    <aside class="sidebar">
      <div class="sidebar-logo"><span class="gradient-text">{title}</span></div>
      <nav class="sidebar-nav">
        <a href="#overview" class="active">📊 Overview</a>
        <a href="#analytics">📈 Analytics</a>
        <a href="#users">👥 Users</a>
        <a href="#reports">📋 Reports</a>
        <a href="#settings">⚙️ Settings</a>
      </nav>
    </aside>
    <main class="main-content">
      <div class="dash-header">
        <h1>Dashboard <span class="gradient-text">Overview</span></h1>
        <p style="color:{t['muted']};margin-top:4px;font-size:14px;">Welcome back! Here's what's happening today.</p>
      </div>
      <div class="dash-stats">
        <div class="dash-stat-card">
          <div style="font-size:28px;font-weight:800;" data-count="12847">0</div>
          <div style="font-size:12px;color:{t['muted']};text-transform:uppercase;letter-spacing:0.06em;margin-top:4px;">Total Users</div>
          <div style="font-size:12px;color:#10b981;margin-top:8px;">↑ 12.5% from last month</div>
        </div>
        <div class="dash-stat-card">
          <div style="font-size:28px;font-weight:800;" data-count="4523" data-prefix="$">$0</div>
          <div style="font-size:12px;color:{t['muted']};text-transform:uppercase;letter-spacing:0.06em;margin-top:4px;">Revenue Today</div>
          <div style="font-size:12px;color:#10b981;margin-top:8px;">↑ 8.2% from yesterday</div>
        </div>
        <div class="dash-stat-card">
          <div style="font-size:28px;font-weight:800;" data-count="98" data-suffix="%">0%</div>
          <div style="font-size:12px;color:{t['muted']};text-transform:uppercase;letter-spacing:0.06em;margin-top:4px;">Uptime</div>
          <div style="font-size:12px;color:#10b981;margin-top:8px;">All systems operational</div>
        </div>
        <div class="dash-stat-card">
          <div style="font-size:28px;font-weight:800;" data-count="342">0</div>
          <div style="font-size:12px;color:{t['muted']};text-transform:uppercase;letter-spacing:0.06em;margin-top:4px;">Active Sessions</div>
          <div style="font-size:12px;color:#f59e0b;margin-top:8px;">↓ 3.1% from last hour</div>
        </div>
      </div>
      <div class="dash-panels">
        <div class="dash-panel">
          <h3>Recent Activity</h3>
          <div style="border-bottom:1px solid {t['border']};padding:12px 0;"><span style="font-weight:600;">New user registration</span><span style="float:right;font-size:13px;color:{t['muted']};">2 min ago</span></div>
          <div style="border-bottom:1px solid {t['border']};padding:12px 0;"><span style="font-weight:600;">Payment processed</span><span style="float:right;font-size:13px;color:{t['muted']};">15 min ago</span></div>
          <div style="border-bottom:1px solid {t['border']};padding:12px 0;"><span style="font-weight:600;">Report generated</span><span style="float:right;font-size:13px;color:{t['muted']};">1 hr ago</span></div>
          <div style="border-bottom:1px solid {t['border']};padding:12px 0;"><span style="font-weight:600;">Server backup completed</span><span style="float:right;font-size:13px;color:{t['muted']};">3 hr ago</span></div>
          <div style="padding:12px 0;"><span style="font-weight:600;">System update deployed</span><span style="float:right;font-size:13px;color:{t['muted']};">5 hr ago</span></div>
        </div>
        <div class="dash-panel">
          <h3>Quick Actions</h3>
          <button class="btn btn-primary" style="width:100%;justify-content:center;margin-bottom:12px;font-size:13px;padding:10px;">Generate Report</button>
          <button class="btn btn-secondary" style="width:100%;justify-content:center;margin-bottom:12px;font-size:13px;padding:10px;">Add New User</button>
          <button class="btn btn-secondary" style="width:100%;justify-content:center;margin-bottom:12px;font-size:13px;padding:10px;">View Analytics</button>
          <button class="btn btn-secondary" style="width:100%;justify-content:center;font-size:13px;padding:10px;">System Settings</button>
        </div>
      </div>
    </main>
  </div>
  <script src="script.js"></script>
</body>
</html>"""


# =====================================================================
#  WEBSITE GENERATOR ENGINE
# =====================================================================

class WebsiteGenerator:
    """Generates complete, multi-page, production-ready websites from prompts."""

    def __init__(self, workspace: str | None = None) -> None:
        self.workspace = Path(workspace or os.path.dirname(__file__)).resolve()
        self.output_base = self.workspace / "generated_sites"
        self.output_base.mkdir(parents=True, exist_ok=True)

    # ── Functional App & Framework Detection ──────────────────────────────
    _APP_KEYWORDS = [
        "todo", "to-do", "calculator", "quiz", "game", "chat",
        "timer", "stopwatch", "clock", "counter", "converter",
        "weather app", "note", "notepad", "kanban", "expense",
        "tracker", "pomodoro", "password generator", "color picker",
        "markdown editor", "code editor", "whiteboard", "drawing",
        "music player", "video player", "form builder", "survey",
        "login page", "signup page", "authentication", "crud",
        "inventory", "booking", "reservation", "social media",
        "e-learning", "lms", "crm", "erp", "api",
    ]

    _FRAMEWORK_SIGNALS: dict[str, dict] = {
        "react": {
            "keywords": ["react", "reactjs", "react.js", "react app"],
            "lang": "javascript",
            "label": "React (Vite)",
        },
        "nextjs": {
            "keywords": ["next", "nextjs", "next.js", "next js"],
            "lang": "javascript",
            "label": "Next.js",
        },
        "vue": {
            "keywords": ["vue", "vuejs", "vue.js", "vue app"],
            "lang": "javascript",
            "label": "Vue 3 (Vite)",
        },
        "svelte": {
            "keywords": ["svelte", "sveltekit", "svelte app"],
            "lang": "javascript",
            "label": "Svelte (Vite)",
        },
        "angular": {
            "keywords": ["angular", "angular app"],
            "lang": "typescript",
            "label": "Angular",
        },
        "express": {
            "keywords": ["express", "express.js", "node backend", "rest api", "express api"],
            "lang": "javascript",
            "label": "Express.js",
        },
        "flask": {
            "keywords": ["flask", "flask app", "python web", "python backend"],
            "lang": "python",
            "label": "Flask",
        },
        "django": {
            "keywords": ["django", "django app"],
            "lang": "python",
            "label": "Django",
        },
    }

    def _is_functional_app(self, prompt: str) -> bool:
        """Detect if the prompt asks for a functional/interactive web app
        rather than a static informational website."""
        p = prompt.lower()
        return any(kw in p for kw in self._APP_KEYWORDS)

    def _detect_framework(self, prompt: str) -> str | None:
        """Detect if the user explicitly asks for a specific framework.
        Returns the framework key (e.g. 'react', 'nextjs') or None."""
        p = prompt.lower()
        for fw_key, fw_info in self._FRAMEWORK_SIGNALS.items():
            if any(kw in p for kw in fw_info["keywords"]):
                return fw_key
        return None

    # ── Vanilla App Generation (HTML/CSS/JS) ──────────────────────────

    def _generate_with_coding_agent(self, prompt: str, title: str,
                                     output_dir: Path) -> list[dict]:
        """Use the CodingAgent to generate a complete, functional single-page
        web application (HTML + CSS + JS) from the user's prompt.
        Returns the list of file dicts written to disk."""
        import logging
        _logger = logging.getLogger("AerisWebsiteGenerator")

        from core.agents.sub_agents.coding_agent import CodingAgent
        coder = CodingAgent(enable_validation=False)

        coding_prompt = (
            f"Generate a COMPLETE, PRODUCTION-READY, single-page web application for: {prompt}\n"
            f"Title: {title}\n\n"
            f"REQUIREMENTS:\n"
            f"1. Output exactly 3 files: index.html, styles.css, script.js\n"
            f"2. The HTML must link to styles.css and script.js (external files, not inline)\n"
            f"3. Use modern, premium design: dark theme, gradients, glassmorphism, smooth animations\n"
            f"4. Use Google Fonts (Inter or similar)\n"
            f"5. Make it FULLY FUNCTIONAL — all buttons, inputs, and interactions must work\n"
            f"6. Responsive design for mobile and desktop\n"
            f"7. Include localStorage persistence where appropriate\n"
            f"8. Do NOT use any frameworks — vanilla HTML/CSS/JS only\n"
            f"9. The app must be beautiful and premium-looking, NOT a basic MVP\n"
            f"10. Add micro-animations, hover effects, and polished UX\n\n"
            f"Return all 3 files in the 'files' array of your JSON response."
        )

        result = coder.generate_code(coding_prompt, "html")
        return self._write_agent_files(result, output_dir, _logger)

    # ── Framework-Based Project Generation ────────────────────────────

    def _generate_framework_project(self, prompt: str, title: str,
                                     framework: str, output_dir: Path) -> list[dict]:
        """Use the CodingAgent to generate a full framework-based project
        (React, Next.js, Vue, Express, Flask, etc.) with proper project structure.
        Returns the list of file dicts written to disk."""
        import logging
        _logger = logging.getLogger("AerisWebsiteGenerator")

        from core.agents.sub_agents.coding_agent import CodingAgent
        coder = CodingAgent(enable_validation=False)

        fw_info = self._FRAMEWORK_SIGNALS.get(framework, {})
        fw_label = fw_info.get("label", framework.title())
        fw_lang = fw_info.get("lang", "javascript")

        # Build framework-specific file structure guidance
        structure_hints = self._get_framework_structure(framework)

        coding_prompt = (
            f"Generate a COMPLETE, PRODUCTION-READY {fw_label} project for: {prompt}\n"
            f"Title: {title}\n\n"
            f"FRAMEWORK: {fw_label}\n"
            f"LANGUAGE: {fw_lang}\n\n"
            f"PROJECT STRUCTURE — generate ALL of these files:\n"
            f"{structure_hints}\n\n"
            f"REQUIREMENTS:\n"
            f"1. Every file must be COMPLETE and WORKING — no placeholders or '// TODO'\n"
            f"2. package.json must include ALL required dependencies with correct versions\n"
            f"3. Use modern, premium design: dark theme, gradients, glassmorphism, smooth animations\n"
            f"4. Make it FULLY FUNCTIONAL — all routes, components, and interactions must work\n"
            f"5. Responsive design for mobile and desktop\n"
            f"6. Include proper error handling and loading states\n"
            f"7. Use best practices for the framework (hooks, composition API, etc.)\n"
            f"8. The app must be beautiful and premium-looking, NOT a basic MVP\n"
            f"9. Add micro-animations, hover effects, and polished UX\n"
            f"10. Include a proper README.md with setup instructions\n\n"
            f"Return ALL files in the 'files' array of your JSON response.\n"
            f"Each file must have 'path' (relative, e.g. 'src/App.jsx'), 'content', and 'language'."
        )

        result = coder.generate_code(coding_prompt, fw_lang)
        files_written = self._write_agent_files(result, output_dir, _logger, preserve_paths=True)

        # Auto-install dependencies if package.json was generated
        if files_written and (output_dir / "package.json").exists():
            try:
                import subprocess
                _logger.info(f"Running npm install in {output_dir} ...")
                subprocess.Popen(
                    ["npm", "install"],
                    cwd=str(output_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=True,
                )
            except Exception:
                pass  # Non-blocking — user can run manually

        return files_written

    def _get_framework_structure(self, framework: str) -> str:
        """Return a file-structure hint string for the CodingAgent prompt."""
        structures = {
            "react": (
                "- package.json\n"
                "- vite.config.js\n"
                "- index.html\n"
                "- src/main.jsx (entry point)\n"
                "- src/App.jsx (root component)\n"
                "- src/App.css (global styles)\n"
                "- src/index.css (base styles)\n"
                "- src/components/ (at least 3-4 components as needed)\n"
            ),
            "nextjs": (
                "- package.json\n"
                "- next.config.js\n"
                "- app/layout.jsx (root layout)\n"
                "- app/page.jsx (home page)\n"
                "- app/globals.css (global styles)\n"
                "- app/components/ (reusable components)\n"
                "- public/ (static assets if needed)\n"
            ),
            "vue": (
                "- package.json\n"
                "- vite.config.js\n"
                "- index.html\n"
                "- src/main.js (entry point)\n"
                "- src/App.vue (root component)\n"
                "- src/style.css (global styles)\n"
                "- src/components/ (at least 3-4 components as needed)\n"
            ),
            "svelte": (
                "- package.json\n"
                "- vite.config.js\n"
                "- index.html\n"
                "- src/main.js (entry point)\n"
                "- src/App.svelte (root component)\n"
                "- src/app.css (global styles)\n"
                "- src/lib/ (reusable components)\n"
            ),
            "angular": (
                "- package.json\n"
                "- angular.json\n"
                "- tsconfig.json\n"
                "- src/main.ts\n"
                "- src/index.html\n"
                "- src/styles.css\n"
                "- src/app/app.component.ts\n"
                "- src/app/app.component.html\n"
                "- src/app/app.component.css\n"
                "- src/app/app.module.ts\n"
            ),
            "express": (
                "- package.json\n"
                "- server.js (main entry)\n"
                "- routes/ (route handlers)\n"
                "- middleware/ (custom middleware)\n"
                "- public/index.html (frontend)\n"
                "- public/styles.css\n"
                "- public/script.js\n"
                "- README.md\n"
            ),
            "flask": (
                "- requirements.txt\n"
                "- app.py (main entry)\n"
                "- templates/index.html\n"
                "- templates/base.html\n"
                "- static/css/style.css\n"
                "- static/js/main.js\n"
                "- README.md\n"
            ),
            "django": (
                "- requirements.txt\n"
                "- manage.py\n"
                "- project/settings.py\n"
                "- project/urls.py\n"
                "- project/wsgi.py\n"
                "- app/views.py\n"
                "- app/models.py\n"
                "- app/urls.py\n"
                "- templates/base.html\n"
                "- templates/index.html\n"
                "- static/css/style.css\n"
                "- static/js/main.js\n"
                "- README.md\n"
            ),
        }
        return structures.get(framework, "- index.html\n- styles.css\n- script.js\n")

    # ── Shared File Writer ────────────────────────────────────────────

    def _write_agent_files(self, result: dict, output_dir: Path,
                           _logger, preserve_paths: bool = False) -> list[dict]:
        """Parse CodingAgent result and write files to disk.
        If preserve_paths=True, keeps subdirectory structure (e.g. src/App.jsx).
        Otherwise flattens to filenames only."""
        files_written: list[dict] = []

        if result.get("status") != "success":
            _logger.warning("CodingAgent failed, falling back to template generation")
            return []

        raw_files = result.get("files", [])
        if not raw_files:
            code = result.get("code", "")
            if code.strip():
                raw_files = [{"path": "index.html", "content": code, "language": "html"}]

        if not raw_files:
            _logger.warning("CodingAgent returned no files")
            return []

        for f in raw_files:
            path = f.get("path", "output")
            content = f.get("content", "")
            if not content.strip():
                continue

            if preserve_paths:
                # Keep directory structure — create parent dirs as needed
                file_path = output_dir / path
                file_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                # Flatten to just the filename
                path = Path(path).name
                file_path = output_dir / path

            file_path.write_text(content, encoding="utf-8")

            lang = f.get("language", "")
            if not lang:
                ext = Path(path).suffix.lower()
                lang_map = {
                    ".html": "html", ".css": "css", ".js": "javascript",
                    ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
                    ".vue": "vue", ".svelte": "svelte", ".py": "python",
                    ".json": "json", ".md": "markdown", ".txt": "text",
                }
                lang = lang_map.get(ext, "text")

            files_written.append({"path": path, "content": content, "lang": lang})

        return files_written

    # ── Main Entry Point ─────────────────────────────────────────────

    def generate(self, prompt: str, site_type: str = "auto") -> GeneratedWebsite:
        """Main entry — detect type, theme, language, URL cloning, and generate entire project.

        Routing logic:
          1. Framework request (react, next, vue, etc.) → CodingAgent with framework scaffolding
          2. Functional app (todo, calculator, etc.) → CodingAgent with vanilla HTML/CSS/JS
          3. Everything else → Fast template engine (portfolio, business, landing, etc.)
        """
        title = self._extract_title(prompt)
        project_id = uuid.uuid4().hex[:10]
        framework = self._detect_framework(prompt)

        # ── Route 1: Framework-based project ─────────────────────────
        if framework:
            fw_label = self._FRAMEWORK_SIGNALS[framework]["label"]
            output_dir = self.output_base / f"{framework}_{project_id}"
            output_dir.mkdir(parents=True, exist_ok=True)

            try:
                agent_files = self._generate_framework_project(prompt, title, framework, output_dir)
                if agent_files:
                    pages = [f["path"] for f in agent_files
                             if f["path"].endswith((".html", ".jsx", ".tsx", ".vue", ".svelte"))]
                    return GeneratedWebsite(
                        project_id=project_id,
                        site_type=framework,
                        title=title,
                        output_dir=str(output_dir),
                        files=agent_files,
                        pages=pages or ["index"],
                        theme="dark",
                        language="en",
                        created_at=datetime.now().isoformat(),
                    )
            except Exception as _e:
                import logging
                logging.getLogger("AerisWebsiteGenerator").warning(
                    f"CodingAgent {fw_label} generation failed ({_e}), falling back to templates"
                )

        # ── Route 2: Functional vanilla app ──────────────────────────
        if self._is_functional_app(prompt):
            output_dir = self.output_base / f"app_{project_id}"
            output_dir.mkdir(parents=True, exist_ok=True)

            try:
                agent_files = self._generate_with_coding_agent(prompt, title, output_dir)
                if agent_files:
                    # Write a README
                    readme = (
                        f"# {title}\n\n"
                        f"> Generated by **AERIS** — CodingAgent\n\n"
                        f"## How to Preview\nOpen `index.html` in your browser.\n\n"
                        f"---\n*Powered by AERIS*\n"
                    )
                    (output_dir / "README.md").write_text(readme, encoding="utf-8")
                    agent_files.append({"path": "README.md", "content": readme, "lang": "markdown"})

                    # Open in browser
                    try:
                        idx = output_dir / "index.html"
                        if idx.exists():
                            webbrowser.open(idx.as_uri())
                    except Exception:
                        pass

                    pages = [f["path"].replace(".html", "") for f in agent_files if f["path"].endswith(".html")]
                    return GeneratedWebsite(
                        project_id=project_id,
                        site_type="app",
                        title=title,
                        output_dir=str(output_dir),
                        files=agent_files,
                        pages=pages or ["index"],
                        theme="dark",
                        language="en",
                        created_at=datetime.now().isoformat(),
                    )
            except Exception as _e:
                import logging
                logging.getLogger("AerisWebsiteGenerator").warning(
                    f"CodingAgent app generation failed ({_e}), falling back to templates"
                )

        # ── Route 3: Template-based generation (original path) ───────
        # URL Cloning logic
        url_match = re.search(r'(https?://[^\s]+)', prompt)
        cloned_data = None
        if url_match:
            cloned_data = _site_analyzer.analyze(url_match.group(1))
            
        if site_type == "auto":
            site_type = cloned_data.get("site_type", self._detect_type(prompt)) if cloned_data else self._detect_type(prompt)

        # Validate type bounds
        if site_type not in SITE_CONFIGS:
            site_type = "landing"

        theme_name = cloned_data.get("theme", self._detect_theme(prompt, site_type)) if cloned_data else self._detect_theme(prompt, site_type)
        if theme_name not in THEMES:
            theme_name = "dark"
            
        theme = THEMES[theme_name]
        config = SITE_CONFIGS.get(site_type, SITE_CONFIGS["landing"]).copy()
        title = cloned_data.get("title", title) if cloned_data else title
        
        # Override hero description if cloned
        if cloned_data and "description" in cloned_data:
            config["hero_sub"] = cloned_data["description"]

        # Detect language
        lang_code = _language_engine.detect_language(prompt)
        lang_name = _language_engine.get_language_name(lang_code)
        ui_strings = _language_engine.translate_strings(lang_code)

        # Translate nav labels if not English
        nav_items = config["nav_items"]
        if lang_code != "en":
            nav_key_map = {
                "Home": "nav_home", "About": "nav_about", "Projects": "nav_projects",
                "Services": "nav_services", "Contact": "nav_contact",
                "Products": "nav_products", "Articles": "nav_articles", "Work": "nav_work",
                "Features": "features_title", "Testimonials": "testimonials_title",
                "Pricing": "pricing_title",
            }
            nav_items = []
            for n in config["nav_items"]:
                translated_label = ui_strings.get(nav_key_map.get(n["label"], ""), n["label"])
                nav_items.append({**n, "label": translated_label})

        # Initialize image bank
        images = _get_image_bank(site_type)

        output_dir = self.output_base / f"{site_type}_{project_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        files: list[dict] = []
        year = datetime.now().year

        # 0. Try to generate AI hero image (non-blocking)
        hero_local_img = images.generate_ai_hero(title, prompt, output_dir)
        if hero_local_img:
            files.append({"path": hero_local_img, "content": "[binary image]", "lang": "image"})

        # 1. Generate CSS
        css_content = _generate_css(theme, site_type)
        (output_dir / "styles.css").write_text(css_content, encoding="utf-8")
        files.append({"path": "styles.css", "content": css_content, "lang": "css"})

        # 2. Generate JS
        js_content = _generate_js(title)
        
        # Try to use CodingAgent to add custom logic based on the prompt
        try:
            from core.agents.sub_agents.coding_agent import CodingAgent
            coder = CodingAgent(enable_validation=False)
            custom_js_req = f"Write custom vanilla JavaScript for a website titled '{title}'. The user asked: '{prompt}'. Do NOT output HTML or CSS. Just the JavaScript logic. If no specific logic is needed, output an empty string."
            res = coder.generate_code(custom_js_req, "javascript")
            if res.get("status") == "success":
                custom_js = ""
                if res.get("files") and res["files"][0].get("content"):
                    custom_js = res["files"][0]["content"]
                elif res.get("code"):
                    custom_js = res["code"]
                if custom_js.strip():
                    js_content += "\n\n/* --- Custom AI Generated Logic --- */\n" + custom_js.strip()
        except Exception:
            pass

        (output_dir / "script.js").write_text(js_content, encoding="utf-8")
        files.append({"path": "script.js", "content": js_content, "lang": "javascript"})

        # 3. Generate pages
        pages = config["pages"]

        for page_name in pages:
            page_file = f"{page_name}.html"
            html = self._build_page(
                page_name, page_file, site_type, title, config,
                nav_items, theme, year, images, ui_strings, lang_code, hero_local_img,
            )
            (output_dir / page_file).write_text(html, encoding="utf-8")
            files.append({"path": page_file, "content": html, "lang": "html"})

        # 4. README
        page_list = ", ".join(f"`{p}.html`" for p in pages)
        lang_info = f"\n- **Language:** {lang_name} (`{lang_code}`)" if lang_code != "en" else ""
        readme = f"""# {title}

> Generated by **AERIS** — Production Website Generator

## Project Info
- **Type:** {site_type.title()}
- **Theme:** {theme_name.title()}{lang_info}
- **Pages:** {page_list}
- **Images:** Context-aware images from Unsplash{' + AI-generated hero' if hero_local_img else ''}
- **Created:** {datetime.now().strftime('%Y-%m-%d %H:%M')}

## How to Preview
Open `index.html` in your browser.

## Project Structure
```
{title.lower().replace(' ', '-')}/
├── index.html      # Home page
{"".join(f'├── {p}.html{chr(10)}' for p in pages[1:])}├── styles.css      # Shared stylesheet
├── script.js       # Shared scripts
└── README.md       # This file
```

## Features
- ✅ Fully responsive (mobile, tablet, desktop)
- ✅ Modern glassmorphism & gradient design
- ✅ Smooth scroll-reveal animations
- ✅ Interactive contact form
- ✅ Mobile hamburger menu
- ✅ Page loading animation
- ✅ Card tilt effects
- ✅ Counter animations
- ✅ Context-aware images (Unsplash / AI-generated)
- ✅ Multi-language support ({lang_name})
- ✅ Clean, semantic HTML5
- ✅ SEO meta tags

---
*Powered by AERIS*
"""
        (output_dir / "README.md").write_text(readme, encoding="utf-8")
        files.append({"path": "README.md", "content": readme, "lang": "markdown"})

        # 5. Open in browser
        try:
            index_file = output_dir / "index.html"
            if index_file.exists():
                webbrowser.open(index_file.as_uri())
        except Exception:
            pass

        return GeneratedWebsite(
            project_id=project_id,
            site_type=site_type,
            title=title,
            output_dir=str(output_dir),
            files=files,
            pages=pages,
            theme=theme_name,
            language=lang_code,
            created_at=datetime.now().isoformat(),
        )

    # ── Page Builder ──────────────────────────────────────────────────

    def _build_page(self, page_name: str, page_file: str, site_type: str,
                    title: str, config: dict, nav_items: list, theme: dict, year: int,
                    images: ImageBank = None, ui: dict = None, lang_code: str = "en",
                    hero_local_img: str = None) -> str:
        """Build a complete HTML page with images and translated text."""
        ui = ui or _UI_STRINGS_EN
        images = images or _get_image_bank(site_type)

        # Dashboard is a special single-page layout
        if site_type == "dashboard":
            return _build_dashboard_page(title, theme)

        parts = []

        if page_name == "index":
            # Home page
            parts.append(_html_head(title, ui.get('nav_home', 'Home'), f"{title} — Modern website built by AERIS", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(_build_hero_section(config, title, images, ui, hero_local_img))
            parts.append(_build_features_section(site_type, ui))
            parts.append(_build_stats_section(ui))

            if site_type == "landing":
                parts.append(_build_testimonials_section(images, ui))
                parts.append(_build_pricing_section(ui))
                parts.append(_build_contact_section(ui))
            elif site_type == "ecommerce":
                parts.append(_build_products_section(images, ui))
            elif site_type == "blog":
                parts.append(_build_articles_section(images, ui))

            parts.append(_html_footer(title, nav_items, year, ui))

        elif page_name == "about":
            parts.append(_html_head(title, ui.get('nav_about', 'About'), f"About {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(_build_about_content(site_type, title, images, ui))
            parts.append(_build_stats_section(ui))
            parts.append(_html_footer(title, nav_items, year, ui))

        elif page_name == "contact":
            parts.append(_html_head(title, ui.get('nav_contact', 'Contact'), f"Get in touch with {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(f"""
  <section class="hero" style="min-height:50vh;">
    <div class="hero-content reveal">
      <h1>{ui.get('connect_title', "Let's Connect").rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('connect_title', "Let's Connect").rsplit(' ', 1)[-1]}</span></h1>
      <p>{ui.get('connect_sub', "Have a project in mind? Let's talk.")}</p>
    </div>
  </section>""")
            parts.append(_build_contact_section(ui))
            parts.append(_html_footer(title, nav_items, year, ui))

        elif page_name in ("projects", "work"):
            page_label = ui.get('nav_projects', 'Projects') if page_name == 'projects' else ui.get('nav_work', 'Work')
            parts.append(_html_head(title, page_label, f"Featured projects by {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(f"""
  <section class="hero" style="min-height:50vh;">
    <div class="hero-content reveal">
      <h1>{"My" if site_type == "portfolio" else "Our"} <span class="gradient-text">{page_label}</span></h1>
      <p>{ui.get('projects_sub', 'A curated showcase of our best work.')}</p>
    </div>
  </section>""")
            parts.append(_build_projects_section(site_type, images, ui))
            parts.append(_html_footer(title, nav_items, year, ui))

        elif page_name == "services":
            parts.append(_html_head(title, ui.get('nav_services', 'Services'), f"Services by {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(f"""
  <section class="hero" style="min-height:50vh;">
    <div class="hero-content reveal">
      <h1>{ui.get('services_title', 'Our Services').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('services_title', 'Our Services').rsplit(' ', 1)[-1]}</span></h1>
      <p>{ui.get('services_sub', 'End-to-end solutions designed to help your business thrive.')}</p>
    </div>
  </section>""")
            parts.append(_build_services_section(site_type))
            parts.append(_build_testimonials_section(images, ui))
            parts.append(_html_footer(title, nav_items, year, ui))

        elif page_name == "products":
            parts.append(_html_head(title, ui.get('nav_products', 'Products'), f"Products from {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(f"""
  <section class="hero" style="min-height:50vh;">
    <div class="hero-content reveal">
      <h1>{ui.get('products_title', 'Our Products').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('products_title', 'Our Products').rsplit(' ', 1)[-1]}</span></h1>
      <p>{ui.get('products_sub', 'Premium quality products designed for the modern world.')}</p>
    </div>
  </section>""")
            parts.append(_build_products_section(images, ui))
            parts.append(_html_footer(title, nav_items, year, ui))

        elif page_name == "articles":
            parts.append(_html_head(title, ui.get('nav_articles', 'Articles'), f"Articles from {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(f"""
  <section class="hero" style="min-height:50vh;">
    <div class="hero-content reveal">
      <h1>{ui.get('articles_title', 'Latest Articles').rsplit(' ', 1)[0]} <span class="gradient-text">{ui.get('articles_title', 'Latest Articles').rsplit(' ', 1)[-1]}</span></h1>
      <p>{ui.get('articles_sub', 'Insights, tutorials, and stories from our team.')}</p>
    </div>
  </section>""")
            parts.append(_build_articles_section(images, ui))
            parts.append(_html_footer(title, nav_items, year, ui))

        else:
            # Fallback generic page
            parts.append(_html_head(title, page_name.title(), f"{page_name.title()} — {title}", lang_code))
            parts.append("<body>")
            parts.append(_html_navbar(title, nav_items, page_file))
            parts.append(f"""
  <section class="hero" style="min-height:60vh;">
    <div class="hero-content reveal">
      <h1><span class="gradient-text">{page_name.title()}</span></h1>
      <p>Content for the {page_name} page.</p>
    </div>
  </section>""")
            parts.append(_html_footer(title, nav_items, year, ui))

        return "\n".join(parts)

    # ── Detection Helpers ──────────────────────────────────────────────

    def _detect_type(self, prompt: str) -> str:
        p = prompt.lower()
        type_keywords = {
            "portfolio": ["portfolio", "personal", "developer", "designer", "resume", "cv",
                         "freelancer", "photographer"],
            "business": ["business", "company", "corporate", "enterprise", "startup",
                        "consulting", "firm", "b2b"],
            "agency": ["agency", "studio", "creative agency", "digital agency", "marketing agency"],
            "ecommerce": ["ecommerce", "e-commerce", "shop", "store", "products", "online store",
                         "marketplace", "retail"],
            "blog": ["blog", "magazine", "news", "articles", "journal", "publication"],
            "dashboard": ["dashboard", "admin", "admin panel", "analytics panel", "control panel",
                         "management"],
            "landing": ["landing", "saas", "product page", "launch", "waitlist", "coming soon",
                       "salon", "restaurant", "cafe", "spa", "gym", "hotel", "clinic",
                       "school", "church", "real estate", "nonprofit", "ngo"],
        }
        for site_type, keywords in type_keywords.items():
            if any(kw in p for kw in keywords):
                return site_type

        # Fallback: website/page → landing, else portfolio
        if any(w in p for w in ["website", "web site", "page", "site"]):
            return "landing"
        return "portfolio"

    def _detect_theme(self, prompt: str, site_type: str) -> str:
        p = prompt.lower()
        if any(w in p for w in ["light", "white", "bright", "clean"]):
            return "light"
        if any(w in p for w in ["dark", "night", "black", "midnight"]):
            return "dark"
        if any(w in p for w in ["corporate", "professional", "formal", "enterprise"]):
            return "corporate"
        if any(w in p for w in ["creative", "bold", "vibrant", "colorful", "artistic"]):
            return "creative"
        # Use the default theme for the site type
        config = SITE_CONFIGS.get(site_type, {})
        return config.get("default_theme", "dark")

    def _extract_title(self, prompt: str) -> str:
        words = prompt.split()
        # Look for explicit name: "called X", "named X", "for X"
        for i, w in enumerate(words):
            if w.lower() in ("called", "named", "titled"):
                if i + 1 < len(words):
                    title_words = []
                    for tw in words[i + 1:]:
                        if tw.lower() in ("with", "that", "which", "and", "using",
                                          "in", "having", "theme", "style"):
                            break
                        title_words.append(tw)
                    if title_words:
                        return " ".join(title_words).strip("\"'")

        # Look for "for X"
        for i, w in enumerate(words):
            if w.lower() == "for" and i + 1 < len(words):
                # Skip common following words that aren't names
                next_word = words[i + 1].lower()
                if next_word in ("me", "my", "a", "an", "the", "our"):
                    continue
                title_words = []
                for tw in words[i + 1:]:
                    if tw.lower() in ("with", "that", "which", "using",
                                      "in", "having", "theme", "style"):
                        break
                    title_words.append(tw)
                if title_words:
                    return " ".join(title_words).strip("\"'").title()

        # Fallback: grab meaningful words
        skip = {"create", "make", "build", "generate", "a", "an", "the", "website",
                "web", "site", "page", "for", "me", "my", "modern", "new", "beautiful",
                "responsive", "dark", "light", "with", "please"}
        meaningful = [w.title() for w in words[:10] if w.lower() not in skip]
        return " ".join(meaningful[:3]) if meaningful else "AERIS Project"

    def list_projects(self) -> list[dict]:
        """List all generated website projects."""
        projects = []
        if self.output_base.exists():
            for d in sorted(self.output_base.iterdir()):
                if d.is_dir():
                    files = list(d.glob("*"))
                    html_files = [f.name for f in d.glob("*.html")]
                    projects.append({
                        "name": d.name,
                        "path": str(d),
                        "file_count": len(files),
                        "pages": html_files,
                    })
        return projects
