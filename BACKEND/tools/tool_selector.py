"""
AERIS — Tool Selection Intelligence
═══════════════════════════════════════════════════════════════════════
Given a user task / objective, selects the best tool(s) from the
Universal Tool Registry.

Selection strategy (in order):
  1. Exact name match      — user says "use read_file"
  2. Keyword extraction    — "search for files" → grep_search / find_system_file
  3. Semantic similarity   — embed the task + tool descriptions, pick closest
  4. Category filtering    — narrow by category if task type is known
  5. Capability scoring    — rank by (relevance × safety × history)

This module is STATELESS — it only reads from the registry and returns
a ranked list of tool candidates.  The Planner Agent makes the final
decision.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AerisToolSelector")

from tools.tool_interface import RiskLevel, UniversalToolDef


# ─── Keyword → Tool Category Mapping ─────────────────────────────────
_KEYWORD_MAP: Dict[str, List[str]] = {
    # File operations
    "read":        ["read_file", "read_system_file"],
    "write":       ["write_file", "write_content"],
    "edit":        ["edit_file"],
    "delete":      ["delete_file"],
    "list":        ["list_dir", "list_system_dir"],
    "find":        ["find_system_file", "grep_search"],
    "search":      ["grep_search", "web_research", "realtime_search", "google_search"],
    "grep":        ["grep_search"],
    "convert":     ["convert_file"],
    # Execution
    "run":         ["run_bash", "smart_shell_generate"],
    "execute":     ["run_bash", "smart_shell_generate"],
    "shell":       ["smart_shell_generate", "run_bash"],
    "command":     ["smart_shell_generate", "describe_shell_command"],
    "bash":        ["run_bash"],
    "terminal":    ["run_bash", "smart_shell_generate"],
    # Web / search
    "google":      ["google_search"],
    "youtube":     ["youtube_search", "play_youtube", "play_on_youtube_visible"],
    "web":         ["web_research", "scrape_website"],
    "scrape":      ["scrape_website"],
    "research":    ["web_research"],
    "news":        ["realtime_search"],
    "weather":     ["realtime_search"],
    "price":       ["realtime_search"],
    # System / automation
    "open":        ["open_app"],
    "close":       ["close_app", "close_all_apps"],
    "screenshot":  ["take_screenshot"],
    "volume":      ["system_control"],
    "mute":        ["system_control", "control_ai_voice"],
    "shutdown":    ["system_control"],
    "restart":     ["system_control"],
    "lock":        ["system_control"],
    # Music
    "play":        ["play_youtube", "play_on_youtube_visible"],
    "music":       ["play_youtube"],
    "song":        ["play_youtube"],
    # Generation
    "website":     ["generate_website"],
    "image":       ["generate_image", "analyze_image_file"],
    "picture":     ["generate_image", "analyze_image_file"],
    "photo":       ["generate_image", "analyze_image_file", "take_camera_photo"],
    "video":       ["generate_video"],
    "code":        ["generate_code"],
    "generate":    ["generate_code", "generate_website", "generate_image", "generate_video"],
    # Vision
    "screen":      ["analyze_screen", "ocr_screen"],
    "screenshot":  ["take_screenshot", "analyze_image_file"],
    "camera":      ["analyze_camera"],
    "ocr":         ["ocr_screen"],
    "face":        ["detect_faces"],
    "analyze":     ["read_file", "grep_search", "analyze_screen", "analyze_image_file"],
    # Log / File operations
    "log":         ["read_file", "grep_search", "read_system_file"],
    "logs":        ["read_file", "grep_search", "read_system_file"],
    "text":        ["read_file", "grep_search", "read_system_file", "write_file"],
    "data":        ["read_file", "grep_search", "read_system_file"],
    "csv":         ["read_file", "grep_search", "read_system_file"],
    "report":      ["read_file", "generate_pdf_report"],
    "document":    ["read_file", "write_file"],
    # Knowledge
    "rag":         ["rag_search"],
    "knowledge":   ["rag_search"],
    "index":       ["rag_index"],
    # Workflow
    "workflow":    ["list_workflows", "run_workflow"],
    # Navigation
    "map":         ["open_map"],
    "directions":  ["get_directions"],
    "navigate":    ["get_directions"],
    # Conversation
    "chat":        ["chat_with_ai"],
    "explain":     ["chat_with_ai"],
    "help":        ["chat_with_ai"],
    # Tool management
    "forge":       ["dynamic_tool_forge"],
    "tool":        ["dynamic_tool_forge"],
    # Email / Brevo
    "email":       ["send_email"],
    "mail":        ["send_email"],
    "brevo":       ["brevo_send_email", "brevo_get_contacts", "brevo_create_email_campaign", "brevo_get_account_info"],
    "send":        ["send_email", "write_file", "run_bash"],
}


class ToolCandidate:
    __slots__ = ("tool", "score", "match_reason")

    def __init__(self, tool: UniversalToolDef, score: float, match_reason: str):
        self.tool = tool
        self.score = score
        self.match_reason = match_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.tool.name,
            "score": round(self.score, 3),
            "reason": self.match_reason,
            "risk": self.tool.risk_level.value,
        }


class ToolSelector:
    """
    Intelligent tool selection engine.

    Usage:
        selector = ToolSelector(all_tools)
        candidates = selector.select("find large files in my Downloads")
        best = candidates[0].tool
    """

    def __init__(self, tools: List[UniversalToolDef]):
        self._tools = [t for t in tools if t.is_enabled]
        # Pre-compute tool name → tool for fast lookup
        self._by_name: Dict[str, UniversalToolDef] = {t.name: t for t in self._tools}

    def update_tools(self, tools: List[UniversalToolDef]):
        """Update the tool pool (called when registry changes)."""
        self._tools = [t for t in tools if t.is_enabled]
        self._by_name = {t.name: t for t in self._tools}

    # ── Main Selection API ────────────────────────────────────────────

    def select(self, task: str, top_k: int = 5, category_hint: str = "", use_advanced: bool = True) -> List[ToolCandidate]:
        """
        Given a natural-language task description, return up to top_k
        ranked tool candidates.
        """
        if not task or not self._tools:
            return []

        if use_advanced:
            try:
                from intelligence.selection_intelligence import get_selection_intelligence
                si = get_selection_intelligence()
                results = si.select(task, top_k=top_k)
                
                candidates = []
                for r in results:
                    tool = self._by_name.get(r.tool_name)
                    if tool:
                        c = ToolCandidate(tool, r.score, r.reason)
                        candidates.append(c)
                
                if candidates:
                    return candidates
            except Exception as e:
                logger.warning(f"Selection intelligence failed, using basic selector: {e}")

        candidates: List[ToolCandidate] = []
        task_lower = task.lower().strip()

        # 1. Exact tool name match — user explicitly says "use X"
        explicit = self._check_explicit_mention(task_lower)
        if explicit:
            candidates.append(ToolCandidate(explicit, 1.0, "exact_name_match"))

        # 2. Keyword-based matching
        kw_matches = self._keyword_match(task_lower)
        for tool, score in kw_matches:
            if not any(c.tool.name == tool.name for c in candidates):
                candidates.append(ToolCandidate(tool, score, "keyword_match"))

        # 3. Fuzzy description matching
        fuzzy_matches = self._fuzzy_match(task_lower)
        for tool, score in fuzzy_matches:
            if not any(c.tool.name == tool.name for c in candidates):
                candidates.append(ToolCandidate(tool, score, "fuzzy_description"))

        # 4. Tag-based matching
        tag_matches = self._tag_match(task_lower)
        for tool, score in tag_matches:
            if not any(c.tool.name == tool.name for c in candidates):
                candidates.append(ToolCandidate(tool, score, "tag_match"))

        # 5. Category filter (if hint provided)
        if category_hint:
            for c in candidates:
                if c.tool.category == category_hint:
                    c.score = min(c.score + 0.15, 1.0)

        # 6. Safety bonus — prefer safer tools
        for c in candidates:
            safety_bonus = {
                RiskLevel.SAFE: 0.05,
                RiskLevel.LOW: 0.03,
                RiskLevel.MEDIUM: 0.0,
                RiskLevel.HIGH: -0.05,
                RiskLevel.CRITICAL: -0.1,
            }.get(c.tool.risk_level, 0)
            c.score = max(0, min(c.score + safety_bonus, 1.0))
            
        # 7. Health / Reliability modifier
        try:
            from tools.tool_health import get_health_tracker
            health_tracker = get_health_tracker()
            for c in candidates:
                metrics = health_tracker.get_metrics(c.tool.name)
                # Penalize tools with poor success rates, reward high reliability
                if metrics.total_runs > 2:
                    health_modifier = (metrics.success_rate - 0.5) * 0.1 # Map 0-1 to -0.05 to +0.05
                    c.score = max(0, min(c.score + health_modifier, 1.0))
        except ImportError:
            pass

        # Sort by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[:top_k]

    def select_best(self, task: str, category_hint: str = "") -> Optional[UniversalToolDef]:
        """Return the single best tool for a task, or None."""
        candidates = self.select(task, top_k=1, category_hint=category_hint)
        return candidates[0].tool if candidates else None

    # ── Internal Matching Strategies ──────────────────────────────────

    def _check_explicit_mention(self, task: str) -> Optional[UniversalToolDef]:
        """Check if user explicitly names a tool."""
        # Pattern: "use <tool_name>" or "run <tool_name>"
        match = re.search(r'(?:use|run|call|execute|invoke)\s+(\w+)', task)
        if match:
            name = match.group(1).lower()
            return self._by_name.get(name)
        # Check if any tool name appears verbatim
        for name, tool in self._by_name.items():
            if name in task:
                return tool
        return None

    def _keyword_match(self, task: str) -> List[Tuple[UniversalToolDef, float]]:
        """Match task words against the keyword → tool map."""
        words = set(re.findall(r'\b\w+\b', task))
        tool_scores: Dict[str, float] = {}

        for word in words:
            if word in _KEYWORD_MAP:
                for tool_name in _KEYWORD_MAP[word]:
                    tool = self._by_name.get(tool_name)
                    if tool:
                        tool_scores[tool_name] = tool_scores.get(tool_name, 0) + 0.25

        results = []
        for name, score in tool_scores.items():
            tool = self._by_name[name]
            results.append((tool, min(score, 0.9)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:10]

    def _fuzzy_match(self, task: str) -> List[Tuple[UniversalToolDef, float]]:
        """Fuzzy-match task text against tool descriptions."""
        results = []
        for tool in self._tools:
            desc_lower = tool.description.lower()
            # Use SequenceMatcher ratio for fuzzy similarity
            ratio = SequenceMatcher(None, task, desc_lower).ratio()
            # Also check word overlap
            task_words = set(task.split())
            desc_words = set(desc_lower.split())
            overlap = len(task_words & desc_words) / max(len(task_words), 1)
            combined = (ratio * 0.4 + overlap * 0.6)
            if combined > 0.15:
                results.append((tool, combined))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:10]

    def _tag_match(self, task: str) -> List[Tuple[UniversalToolDef, float]]:
        """Match task words against tool tags."""
        words = set(re.findall(r'\b\w+\b', task))
        results = []
        for tool in self._tools:
            if not tool.tags:
                continue
            tag_set = set(t.lower() for t in tool.tags)
            overlap = len(words & tag_set)
            if overlap > 0:
                score = min(overlap * 0.2, 0.8)
                results.append((tool, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:10]
