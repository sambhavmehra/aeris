"""
Aeris AI OS — Selection Intelligence (Part 4)
═══════════════════════════════════════════════════════════════════════
Advanced tool selection that goes beyond the existing ToolSelector by:
  • Mapping user intent → tool category FIRST, then filtering
  • Ranking by relevance × past success × safety
  • Supporting pipeline detection (multi-tool sequences)
  • Using behavioral knowledge to avoid wrong tools
  • Learning from execution feedback

This wraps and enhances the existing ToolSelector with intelligence
from the ToolAwarenessEngine.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
logger = logging.getLogger("AerisSelectionIntelligence")


# ─── Intent → Category Mapping ───────────────────────────────────────
# Maps high-level user intents to tool categories for pre-filtering.

_INTENT_CATEGORY_MAP: Dict[str, List[str]] = {
    # File operations
    "read": ["file"], "write": ["file"], "edit": ["file"], "delete": ["file"],
    "list": ["file"], "find": ["file"], "search_file": ["file"],
    "grep": ["file"], "convert": ["file"],
    # Execution
    "run": ["system", "shell"], "execute": ["system", "shell"],
    "command": ["shell"], "bash": ["system"], "terminal": ["system", "shell"],
    "shell": ["shell"],
    # Web / Search
    "search": ["search", "research"], "google": ["search"],
    "web": ["search", "research"], "scrape": ["research"],
    "research": ["research"], "news": ["search"], "weather": ["search"],
    "price": ["search"], "realtime": ["search"],
    # Apps / Automation
    "open": ["automation"], "close": ["automation"], "launch": ["automation"],
    "workflow": ["automation"],
    # Media
    "play": ["automation"], "music": ["automation"], "song": ["automation"],
    # Generation
    "generate": ["generation"], "create": ["generation"], "build": ["generation"],
    "website": ["generation"], "image": ["generation", "vision"], "video": ["generation"],
    "picture": ["generation", "vision"], "photo": ["generation", "vision"],
    "code": ["generation"], "forge": ["generation"],
    # Vision
    "screen": ["vision"], "camera": ["vision"], "ocr": ["vision"],
    "face": ["vision"], "analyze": ["file", "vision"],
    "screenshot": ["system", "vision"],
    # Log / File operations
    "log": ["file"], "logs": ["file"], "text": ["file"], "data": ["file"],
    "csv": ["file"], "report": ["file"], "document": ["file"],
    # Knowledge
    "rag": ["knowledge"], "knowledge": ["knowledge"], "index": ["knowledge"],
    # Navigation
    "map": ["navigation"], "directions": ["navigation"], "navigate": ["navigation"],
    # Conversation
    "chat": ["conversation"], "explain": ["conversation"],
    "hello": ["conversation"], "help": ["conversation"],
    # System
    "volume": ["system"], "mute": ["system"], "shutdown": ["system"],
    "restart": ["system"], "lock": ["system"], "screenshot": ["system"],
    # Email
    "email": ["email"], "mail": ["email"], "brevo": ["email", "mcp"],
    "monitor": ["system", "automation"], "whatsapp": ["automation", "file"],
    "telegram": ["system", "file"], "audio": ["system"], "voice": ["system"],
}

# ─── Common Pipeline Patterns ────────────────────────────────────────
# Known multi-tool sequences that AERIS should recognize.

_PIPELINE_PATTERNS: List[Dict[str, Any]] = [
    {
        "trigger_words": ["find", "convert"],
        "pipeline": ["find_system_file", "convert_file"],
        "description": "Find a file then convert it to another format",
    },
    {
        "trigger_words": ["write", "run", "execute"],
        "pipeline": ["write_file", "run_bash"],
        "description": "Write a script then execute it",
    },
    {
        "trigger_words": ["find", "read"],
        "pipeline": ["find_system_file", "read_system_file"],
        "description": "Find a file then read its contents",
    },
    {
        "trigger_words": ["generate", "code", "run"],
        "pipeline": ["generate_code", "write_file", "run_bash"],
        "description": "Generate code, save to file, then execute",
    },
    {
        "trigger_words": ["research", "write", "content"],
        "pipeline": ["web_research", "write_content"],
        "description": "Research a topic then write content about it",
    },
]


@dataclass
class SelectionResult:
    """Result from the selection intelligence."""
    tool_name: str
    score: float
    reason: str
    is_pipeline: bool = False
    pipeline: List[str] = field(default_factory=list)
    confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "score": round(self.score, 3),
            "reason": self.reason,
            "is_pipeline": self.is_pipeline,
            "pipeline": self.pipeline,
            "confidence": round(self.confidence, 3),
            "warnings": self.warnings,
        }


_INTENT_TO_TOOL_MAP: Dict[str, Dict[str, Any]] = {
    "email": {
        "categories": ["email"],
        "keywords": ["email", "mail", "send"],
        "must_include_names": ["send_email"]
    },
    "security": {
        "categories": ["security"],
        "keywords": ["security", "scan", "nmap", "ssl", "dns", "whois", "vapt", "port"],
        "must_include_names": ["security_scan", "run_bash"]
    },
    "osint": {
        "categories": ["osint"],
        "keywords": ["osint", "stalk", "profile", "lookup", "whois"],
        "must_include_prefixes": ["osint_"]
    },
    "system": {
        "categories": ["system", "automation", "shell"],
        "keywords": ["run", "execute", "shell", "bash", "command", "terminal", "screenshot", "volume", "open", "close", "play", "youtube", "music", "song"],
        "must_include_names": ["run_bash", "smart_shell_generate", "open_app", "close_app", "system_control", "take_screenshot", "play_youtube"]
    },
    "research": {
        "categories": ["research"],
        "keywords": ["research", "paper", "arxiv", "academic", "literature", "scrape"],
        "must_include_names": ["web_research", "scrape_website"]
    },
    "search": {
        "categories": ["search", "research"],
        "keywords": ["search", "google", "web", "news", "weather", "price", "realtime", "scrape"],
        "must_include_names": ["google_search", "web_research", "youtube_search", "scrape_website"]
    },
    "code": {
        "categories": ["generation"],
        "keywords": ["code", "debug", "refactor", "explain", "python", "javascript", "flask", "api"],
        "must_include_names": ["generate_code", "write_file", "edit_file", "run_bash"]
    },
    "image": {
        "categories": ["generation", "vision"],
        "keywords": ["image", "picture", "photo", "art", "draw", "create", "generate"],
        "must_include_names": ["generate_image", "analyze_image_file"]
    },
    "diagram": {
        "categories": ["diagram", "generation"],
        "keywords": ["diagram", "flowchart", "mindmap", "er", "sequence", "chart", "widget"],
        "must_include_names": ["generate_diagram_widget"]
    },
    "codepipeline": {
        "categories": ["generation"],
        "keywords": ["build", "scaffold", "project", "entire", "workspace", "codebase", "pipeline"],
        "must_include_names": ["build_project", "generate_code", "write_file", "run_bash"]
    },
    "analyze": {
        "categories": ["file", "vision", "analyze"],
        "keywords": ["analyze", "inspect", "summarize", "diagnose", "log", "logs", "file", "csv", "data"],
        "must_include_names": ["read_file", "grep_search", "analyze_image_file", "analyze_screen"]
    },
    "chat": {
        "categories": ["conversation"],
        "keywords": ["chat", "explain", "hello", "help", "greet"],
        "must_include_names": ["chat_with_ai"]
    },
    "monitor": {
        "categories": ["system", "automation"],
        "keywords": ["monitor", "health", "cpu", "memory", "battery", "status"],
        "must_include_names": ["monitor_system"]
    },
    "whatsapp": {
        "categories": ["automation", "file"],
        "keywords": ["whatsapp", "share", "send", "chat", "contact"],
        "must_include_names": ["share_file_whatsapp"]
    },
    "telegram": {
        "categories": ["system", "file"],
        "keywords": ["telegram", "share", "send", "chat", "contact", "telegram file"],
        "must_include_names": ["send_file_telegram"]
    },
    "audio": {
        "categories": ["system"],
        "keywords": ["audio", "voice", "microphone", "mic", "record"],
        "must_include_names": ["record_audio"]
    }
}


class SelectionIntelligence:
    """
    Advanced tool selection combining:
      1. Intent → category pre-filtering
      2. Existing ToolSelector keyword/fuzzy matching
      3. Behavioral awareness (anti-patterns, reliability)
      4. Pipeline detection for multi-step tasks
      5. Safety-aware ranking

    Usage:
        si = get_selection_intelligence()
        results = si.select(objective, top_k=5)
        best = results[0]
        if best.is_pipeline:
            # Execute best.pipeline as a sequence
    """

    def __init__(self):
        pass

    def select(self, objective: str, intent: Optional[str] = None, top_k: int = 5) -> List[SelectionResult]:
        """
        Full intelligent selection pipeline.
        Returns ranked SelectionResult objects.
        """
        if not objective:
            return []

        obj_lower = objective.lower().strip()

        # 1. Detect pipeline patterns
        pipeline = self._detect_pipeline(obj_lower)
        if pipeline:
            return [pipeline]

        # 2. Extract intent categories
        intent_categories = self._extract_intent_categories(obj_lower)
        
        # If intent is provided, add its categories
        if intent and intent in _INTENT_TO_TOOL_MAP:
            intent_categories.extend(_INTENT_TO_TOOL_MAP[intent].get("categories", []))
            intent_categories = list(set(intent_categories))

        # 3. Get base candidates from ToolSelector
        base_candidates = self._get_base_candidates(objective, top_k * 2)

        # 4. Enrich with awareness data
        enriched = self._enrich_with_awareness(base_candidates, intent_categories)
        
        # Apply intent-based boosts and guarantees
        if intent and intent in _INTENT_TO_TOOL_MAP:
            intent_info = _INTENT_TO_TOOL_MAP[intent]
            must_include_prefixes = intent_info.get("must_include_prefixes", [])
            must_include_names = intent_info.get("must_include_names", [])
            intent_keywords = intent_info.get("keywords", [])
            
            # Boost matches
            for r in enriched:
                name_lower = r.tool_name.lower()
                
                # Direct must-include names boost
                if r.tool_name in must_include_names:
                    r.score = min(r.score + 0.3, 1.0)
                    r.reason += f" | intent_must_include:{intent}"
                    
                # Prefix matching (e.g. brevo_ for email)
                if any(name_lower.startswith(pref) for pref in must_include_prefixes):
                    r.score = min(r.score + 0.4, 1.0)
                    r.reason += f" | intent_prefix_match:{intent}"
                    
                # Keyword matching
                if any(kw in name_lower for kw in intent_keywords):
                    r.score = min(r.score + 0.2, 1.0)
                    r.reason += f" | intent_keyword_match:{intent}"
            
            # Guarantee intent-specific tools are present
            try:
                from tools.universal_registry import get_universal_registry
                registry = get_universal_registry()
                all_enabled_tools = registry.get_enabled_tools()
            except Exception as e:
                logger.warning(f"Could not load registry for fallback check: {e}")
                all_enabled_tools = []
                
            existing_names = {r.tool_name for r in enriched}
            
            for tool in all_enabled_tools:
                if tool.name in existing_names:
                    continue
                    
                name_lower = tool.name.lower()
                should_add = False
                add_reason = ""
                
                # Check prefixes
                for pref in must_include_prefixes:
                    if name_lower.startswith(pref):
                        should_add = True
                        add_reason = f"intent_prefix_match_fallback:{intent}"
                        break
                        
                # Check must-include names
                if not should_add and tool.name in must_include_names:
                    should_add = True
                    add_reason = f"intent_must_include_fallback:{intent}"
                    
                if should_add:
                    enriched.append(SelectionResult(
                        tool_name=tool.name,
                        score=0.9,  # High default score for guaranteed tools
                        reason=add_reason,
                        confidence=0.9
                    ))

        # 5. Filter out anti-pattern violations
        filtered = self._filter_anti_patterns(enriched, obj_lower)

        # 6. Apply reliability modifier
        reliability_scored = self._apply_reliability_scores(filtered)

        # Sort by final score
        reliability_scored.sort(key=lambda r: r.score, reverse=True)

        return reliability_scored[:top_k]

    def select_best(self, objective: str) -> Optional[SelectionResult]:
        """Return the single best tool selection."""
        results = self.select(objective, top_k=1)
        return results[0] if results else None

    # ── Internal Pipeline ─────────────────────────────────────────────

    def _detect_pipeline(self, objective: str) -> Optional[SelectionResult]:
        """Check if the objective matches a known multi-tool pipeline."""
        obj_words = set(re.findall(r'\b\w+\b', objective))

        for pattern in _PIPELINE_PATTERNS:
            trigger_words = set(pattern["trigger_words"])
            if len(trigger_words & obj_words) >= 2:
                # Verify all pipeline tools exist
                try:
                    from intelligence.tool_awareness import get_tool_awareness
                    awareness = get_tool_awareness()
                    all_exist = all(
                        awareness.get_tool_knowledge(t) is not None
                        for t in pattern["pipeline"]
                    )
                    if not all_exist:
                        continue
                except Exception:
                    continue

                return SelectionResult(
                    tool_name=pattern["pipeline"][0],
                    score=0.95,
                    reason=f"pipeline_match: {pattern['description']}",
                    is_pipeline=True,
                    pipeline=pattern["pipeline"],
                    confidence=0.9,
                )
        return None

    def _extract_intent_categories(self, objective: str) -> List[str]:
        """Extract likely tool categories from the objective text."""
        words = set(re.findall(r'\b\w+\b', objective))
        categories = set()
        for word in words:
            if word in _INTENT_CATEGORY_MAP:
                categories.update(_INTENT_CATEGORY_MAP[word])
        return list(categories)

    def _get_base_candidates(self, objective: str, top_k: int) -> List[Dict[str, Any]]:
        """Get base candidates from the existing ToolSelector."""
        try:
            from tools.universal_registry import get_universal_registry
            from tools.tool_selector import ToolSelector
            registry = get_universal_registry()
            selector = ToolSelector(registry.get_enabled_tools())
            candidates = selector.select(objective, top_k=top_k, use_advanced=False)
            return [
                {"name": c.tool.name, "score": c.score, "reason": c.match_reason}
                for c in candidates
            ]
        except Exception as e:
            logger.warning(f"Base selection failed: {e}")
            return []

    def _enrich_with_awareness(
        self, candidates: List[Dict[str, Any]], intent_categories: List[str]
    ) -> List[SelectionResult]:
        """Enrich base candidates with awareness data and category bonus."""
        results = []
        try:
            from intelligence.tool_awareness import get_tool_awareness
            awareness = get_tool_awareness()
        except Exception:
            # Just convert without enrichment
            return [
                SelectionResult(
                    tool_name=c["name"], score=c["score"],
                    reason=c["reason"], confidence=c["score"],
                )
                for c in candidates
            ]

        for c in candidates:
            tk = awareness.get_tool_knowledge(c["name"])
            score = c["score"]
            warnings = []

            if tk:
                # Category bonus
                if tk.category in intent_categories:
                    score = min(score + 0.15, 1.0)

                # Reliability warning
                if tk.total_runs >= 3 and tk.success_rate < 0.5:
                    warnings.append(f"Low reliability: {tk.success_rate:.0%} success rate")
                    score *= 0.7

                # Consecutive failure penalty
                if tk.consecutive_failures >= 3:
                    warnings.append(f"{tk.consecutive_failures} consecutive failures")
                    score *= 0.5

            results.append(SelectionResult(
                tool_name=c["name"],
                score=score,
                reason=c["reason"],
                confidence=score,
                warnings=warnings,
            ))

        return results

    def _filter_anti_patterns(
        self, candidates: List[SelectionResult], objective: str
    ) -> List[SelectionResult]:
        """Remove candidates that violate anti-patterns for this objective."""
        try:
            from intelligence.tool_awareness import get_tool_awareness
            awareness = get_tool_awareness()
        except Exception:
            return candidates

        filtered = []
        for c in candidates:
            tk = awareness.get_tool_knowledge(c.tool_name)
            if not tk or not tk.anti_patterns:
                filtered.append(c)
                continue

            # Check if the objective triggers any anti-pattern
            violated = False
            for ap in tk.anti_patterns:
                ap_lower = ap.lower()
                # Simple keyword check in objective against anti-pattern keywords
                # e.g., "Do NOT use for website URLs" + objective contains "website URL"
                # This is conservative — we only filter obvious matches
                if any(kw in objective for kw in _extract_key_phrases(ap_lower)):
                    c.warnings.append(f"Anti-pattern: {ap}")
                    c.score *= 0.3  # Heavy penalty instead of removal
                    violated = True
                    break

            filtered.append(c)

        return filtered

    def _apply_reliability_scores(self, candidates: List[SelectionResult]) -> List[SelectionResult]:
        """Final reliability adjustment based on health data."""
        try:
            from tools.tool_health import get_health_tracker
            health = get_health_tracker()
        except Exception:
            return candidates

        for c in candidates:
            metrics = health.get_metrics(c.tool_name)
            if metrics.total_runs > 2:
                # Map success_rate to a modifier: 0-1 → -0.1 to +0.1
                modifier = (metrics.success_rate - 0.5) * 0.2
                c.score = max(0, min(c.score + modifier, 1.0))

        return candidates


def _extract_key_phrases(text: str) -> List[str]:
    """Extract meaningful 2-3 word phrases from anti-pattern text."""
    # Simple extraction: look for quoted phrases or key nouns
    phrases = re.findall(r'"([^"]+)"', text)
    if phrases:
        return phrases
    # Clean text to remove punctuation
    clean_text = re.sub(r'[^\w\s]', '', text)
    # Fallback: extract significant words (>4 chars)
    words = [w for w in clean_text.split() if len(w) > 4 and w not in {
        "should", "never", "always", "instead", "using", "without"
    }]
    return words[:3]


# ── Global Singleton ─────────────────────────────────────────────────
_selection_intelligence: Optional[SelectionIntelligence] = None


def get_selection_intelligence() -> SelectionIntelligence:
    global _selection_intelligence
    if _selection_intelligence is None:
        _selection_intelligence = SelectionIntelligence()
    return _selection_intelligence
