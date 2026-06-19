"""
Aeris AI OS — Tool Awareness Engine (Part 2)
═══════════════════════════════════════════════════════════════════════
Dynamic tool knowledge system. Enriches every tool with:
  • Structured input/output schemas
  • Risk level and safety constraints
  • Typical use cases and anti-patterns
  • Behavioral notes and limitations
  • Runtime health metrics

This is NOT a replacement for the tool_registry — it is a semantic
knowledge overlay that makes AERIS *understand* each tool's purpose,
constraints, and proper usage patterns.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisToolAwareness")


@dataclass
class ToolKnowledge:
    """
    Rich semantic knowledge about a single tool — goes far beyond
    the basic ToolDefinition metadata.
    """
    name: str
    description: str
    category: str = "general"
    risk_level: str = "safe"

    # Schema awareness
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)
    param_descriptions: Dict[str, str] = field(default_factory=dict)
    output_type: str = "string"              # "string" | "json" | "file_path" | "structured"
    output_description: str = ""

    # Behavioral knowledge
    typical_use_cases: List[str] = field(default_factory=list)
    anti_patterns: List[str] = field(default_factory=list)    # When NOT to use this tool
    prerequisites: List[str] = field(default_factory=list)     # Tools that often run before this
    follow_ups: List[str] = field(default_factory=list)        # Tools that often run after this
    limitations: List[str] = field(default_factory=list)

    # Runtime stats (populated by FeedbackLoop)
    total_runs: int = 0
    success_rate: float = 1.0
    avg_execution_time_ms: float = 0.0
    last_error: Optional[str] = None
    consecutive_failures: int = 0

    def to_llm_string(self) -> str:
        """Compact LLM-friendly description with behavioral notes."""
        params_str = ", ".join(self.required_params) if self.required_params else "none"
        line = f"- {self.name}({params_str}): {self.description} [risk: {self.risk_level}]"
        if self.anti_patterns:
            line += f" ⚠ NOT for: {'; '.join(self.anti_patterns[:2])}"
        if self.consecutive_failures >= 3:
            line += f" ❌ UNRELIABLE ({self.consecutive_failures} consecutive failures)"
        elif self.total_runs > 5 and self.success_rate < 0.5:
            line += f" ⚠ LOW RELIABILITY ({self.success_rate:.0%} success)"
        return line

    def to_rich_llm_string(self) -> str:
        """Full detail for deep planning context."""
        lines = [f"### {self.name}"]
        lines.append(f"  Description: {self.description}")
        lines.append(f"  Category: {self.category} | Risk: {self.risk_level}")
        if self.required_params:
            lines.append(f"  Required params: {', '.join(self.required_params)}")
            for p in self.required_params:
                if p in self.param_descriptions:
                    lines.append(f"    - {p}: {self.param_descriptions[p]}")
        if self.optional_params:
            lines.append(f"  Optional params: {', '.join(self.optional_params)}")
        if self.typical_use_cases:
            lines.append(f"  Use when: {'; '.join(self.typical_use_cases[:3])}")
        if self.anti_patterns:
            lines.append(f"  Do NOT use when: {'; '.join(self.anti_patterns[:3])}")
        if self.limitations:
            lines.append(f"  Limitations: {'; '.join(self.limitations[:2])}")
        if self.total_runs > 0:
            lines.append(f"  Stats: {self.total_runs} runs, {self.success_rate:.0%} success, avg {self.avg_execution_time_ms:.0f}ms")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "risk_level": self.risk_level,
            "required_params": self.required_params,
            "optional_params": self.optional_params,
            "param_descriptions": self.param_descriptions,
            "output_type": self.output_type,
            "typical_use_cases": self.typical_use_cases,
            "anti_patterns": self.anti_patterns,
            "prerequisites": self.prerequisites,
            "follow_ups": self.follow_ups,
            "limitations": self.limitations,
            "total_runs": self.total_runs,
            "success_rate": self.success_rate,
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
        }


# ═══════════════════════════════════════════════════════════════════
#  BEHAVIORAL KNOWLEDGE BASE
#  Hand-crafted behavioral annotations for known tools.
#  The engine merges these with live registry data at runtime.
# ═══════════════════════════════════════════════════════════════════

_TOOL_BEHAVIORAL_KNOWLEDGE: Dict[str, Dict[str, Any]] = {
    "read_file": {
        "typical_use_cases": ["Read file contents before editing", "Inspect a configuration file", "View code"],
        "anti_patterns": ["Do NOT use for binary files", "Do NOT use to read generated website output"],
        "output_type": "string",
        "param_descriptions": {"path": "Relative or absolute path to the file to read"},
    },
    "write_file": {
        "typical_use_cases": ["Create new files", "Save scripts for execution", "Write configuration"],
        "anti_patterns": ["Do NOT use for editing existing files (use edit_file instead)"],
        "follow_ups": ["run_bash"],
        "output_type": "string",
        "param_descriptions": {"path": "Relative path to create the file", "content": "Complete file content to write"},
        "limitations": ["Use simple relative paths, not absolute", "Content must be complete and self-contained"],
    },
    "edit_file": {
        "typical_use_cases": ["Replace specific text in an existing file", "Fix code bugs", "Update configuration values"],
        "anti_patterns": ["Do NOT use if old_text doesn't exist in the file"],
        "prerequisites": ["read_file"],
        "param_descriptions": {"path": "Path to file", "old_text": "Exact text to find", "new_text": "Replacement text"},
    },
    "delete_file": {
        "typical_use_cases": ["Remove temporary files", "Clean up after execution"],
        "anti_patterns": ["NEVER delete system files", "NEVER use with wildcard paths"],
        "limitations": ["HIGH risk — double-check the path"],
    },
    "run_bash": {
        "typical_use_cases": ["Execute scripts", "Run Python files", "System commands"],
        "anti_patterns": ["Do NOT use python -c on Windows (quoting issues)", "Do NOT use for destructive system commands"],
        "prerequisites": ["write_file"],
        "limitations": ["Always wrap file paths in double quotes", "Use write_file first, then run_bash to execute"],
        "param_descriptions": {"command": "Shell command to execute. Always quote file paths."},
    },
    "chat_with_ai": {
        "typical_use_cases": ["Answer general questions", "Greetings and conversation", "Explain concepts"],
        "anti_patterns": ["Do NOT use for real-time info (use realtime_search)", "Do NOT use with empty message"],
        "param_descriptions": {"message": "The user's EXACT original question — do NOT rephrase or summarize"},
        "limitations": ["Pass user's exact words, not rephrased versions"],
    },
    "realtime_search": {
        "typical_use_cases": ["News, weather, prices, scores", "Current events", "Any recent/live information"],
        "anti_patterns": ["Do NOT use for general knowledge questions that don't need live data"],
        "param_descriptions": {"query": "Search query for real-time information"},
    },
    "generate_website": {
        "typical_use_cases": ["Build websites", "Create dashboards", "Landing pages"],
        "anti_patterns": ["Do NOT pass $prev as prompt", "Do NOT call read_file after this", "Do NOT use if the user mentions 'antigravity', 'ide', or 'antigravity_agent' (use build_project instead)"],
        "output_type": "json",
        "follow_ups": [],
        "param_descriptions": {"prompt": "Detailed design instruction describing the website to build"},
        "limitations": ["Prompt must be descriptive, not a reference to previous output"],
    },
    "build_project": {
        "typical_use_cases": [
            "Build complete multi-file projects, applications, or systems",
            "Generate workspace folders and dependencies",
            "Delegate project building to the external Antigravity IDE assistant when the user mentions 'antigravity', 'ide', or 'antigravity_agent'"
        ],
        "anti_patterns": ["Do NOT use for single web page designs or simple informational sites (use generate_website instead)"],
        "output_type": "string",
        "param_descriptions": {"objective": "Detailed description of the project, applications, or systems to build"},
    },
    "find_system_file": {
        "typical_use_cases": ["Locate files by name when path is unknown", "Find documents like resume.pdf"],
        "anti_patterns": ["Do NOT use for website URLs or domains", "ONLY for local files"],
        "follow_ups": ["convert_file", "read_system_file"],
        "param_descriptions": {"filename": "Name of the file to search for"},
    },
    "find_system_folder": {
        "typical_use_cases": ["Locate folders or directories by name when path is unknown"],
        "anti_patterns": ["Do NOT use for individual files", "ONLY for local directories"],
        "follow_ups": ["list_system_dir"],
        "param_descriptions": {"foldername": "Name of the directory/folder to search for"},
    },
    "smart_shell_generate": {
        "typical_use_cases": ["System actions in natural language", "Find large files", "Kill processes", "Check ports"],
        "anti_patterns": ["Do NOT use for simple file operations (use file tools)"],
        "param_descriptions": {"request": "Natural language description of what you want to do"},
    },
    "open_app": {
        "typical_use_cases": ["Open applications", "Launch browsers to URLs"],
        "anti_patterns": ["Do NOT use to open text editors for code writing — use write_file instead"],
        "param_descriptions": {"app_name": "Name of the application or URL to open"},
    },
    "play_youtube": {
        "typical_use_cases": ["Music playback on YouTube", "Play songs visibly in default browser"],
        "anti_patterns": ["Do NOT use for background non-visible playback"],
        "param_descriptions": {"query": "Song name or search query"},
    },
    "play_on_youtube_visible": {
        "typical_use_cases": ["User explicitly asks to play ON YouTube visibly"],
        "anti_patterns": ["Do NOT use by default — only when user says 'on YouTube'"],
        "param_descriptions": {"query": "Song/video search query"},
    },
    "take_screenshot": {
        "typical_use_cases": ["User explicitly asks for a screenshot"],
        "anti_patterns": ["Do NOT use for screen analysis (use analyze_screen)"],
    },
    "analyze_screen": {
        "typical_use_cases": ["AI vision analysis of current screen", "Describe what's visible"],
        "anti_patterns": ["Do NOT use for taking screenshots to save (use take_screenshot)"],
    },
    "generate_code": {
        "typical_use_cases": ["Generate pure code from description", "Code without markdown"],
        "anti_patterns": ["Output is raw code, not markdown-wrapped", "Do NOT use for creating a new project or building complex multi-file applications (use build_project instead)"],
        "param_descriptions": {"request": "Natural language description of code to generate"},
    },
    "dynamic_tool_forge": {
        "typical_use_cases": ["Create new capabilities that don't exist yet"],
        "anti_patterns": ["NEVER use automatically — ONLY when user explicitly asks to create a tool"],
        "limitations": ["Requires explicit user permission"],
        "param_descriptions": {"task_description": "Detailed description of the tool to create"},
    },
    "convert_file": {
        "typical_use_cases": ["Convert between file formats (pdf, docx, csv, etc.)"],
        "prerequisites": ["find_system_file"],
        "param_descriptions": {"input_path": "Path to source file (can use $prev from find_system_file)", "target_format": "Desired output format"},
    },
    "control_ai_voice": {
        "typical_use_cases": ["User says shut up, be quiet, or stop speaking"],
        "anti_patterns": ["Do NOT use unless user explicitly requests mute/unmute"],
        "param_descriptions": {"action": "'mute' or 'unmute'"},
    },
    "web_research": {
        "typical_use_cases": ["Deep research on a topic", "Synthesized information from web"],
        "anti_patterns": ["Do NOT use for simple real-time queries (use realtime_search)"],
        "param_descriptions": {"query": "Research topic or question"},
    },
    "generate_image": {
        "typical_use_cases": ["Create AI-generated images from text descriptions"],
        "param_descriptions": {"prompt": "Detailed visual description of the image to generate"},
        "output_type": "json",
    },
    "generate_video": {
        "typical_use_cases": ["Create AI-generated videos from text descriptions"],
        "param_descriptions": {"prompt": "Description of the video/animation to generate"},
        "output_type": "json",
    },
    "send_email": {
        "typical_use_cases": ["Send an email message using SMTP settings", "Send notifications", "Email reports/files to users"],
        "anti_patterns": ["Do NOT use for campaign or contact list management (use brevo tools instead)"],
        "output_type": "string",
        "param_descriptions": {
            "recipient": "Email address or resolved name (e.g. 'me', 'sambhav')",
            "body": "The email message body (plain text)",
            "subject": "The email subject line (optional)"
        },
    },
    "brevo_send_email": {
        "typical_use_cases": [],
        "anti_patterns": ["Do NOT use this tool for \"email\", \"send\", or \"mail\" tasks. Use send_email instead to avoid API authentication failures."],
        "output_type": "string",
    },
    "brevo_send_test_email": {
        "typical_use_cases": [],
        "anti_patterns": ["Do NOT use this tool for \"email\", \"send\", \"mail\", or \"test\" tasks. Use send_email instead to avoid API authentication failures."],
        "output_type": "string",
    },
    "monitor_system": {
        "typical_use_cases": ["Check CPU and RAM usage", "Check disk space on C or D drive", "Monitor running processes", "Check battery status"],
        "anti_patterns": ["Do NOT use for individual process manipulation (use close_app/run_bash)"],
        "output_type": "string",
    },
    "check_project_status": {
        "typical_use_cases": ["Check progress of the background project builder swarm (PBS)", "Get status of active code generation", "See generated files list of the building project"],
        "anti_patterns": ["Do NOT use for creating a new project (use build_project)"],
        "output_type": "string",
    },
    "share_file_whatsapp": {
        "typical_use_cases": ["Send a document to a WhatsApp contact by their name", "Share a file to anyone on WhatsApp with a proper contact name"],
        "anti_patterns": ["Do NOT use for sending text messages without a file (use open_app/computer_use_task)"],
        "output_type": "string",
        "param_descriptions": {
            "contact_name": "Name of the WhatsApp contact (e.g., 'Rahul', 'Mom', 'Papa')",
            "file_path": "Absolute path to the file to be shared/sent"
        },
    },
    "record_audio": {
        "typical_use_cases": ["Record audio or ambient voice from the microphone", "Record voice memo"],
        "anti_patterns": ["Do NOT use for speech recognition transcription (use speechtotext or similar if available)"],
        "output_type": "string",
        "param_descriptions": {
            "duration": "Duration to record audio in seconds (e.g. 5, 10, 30)"
        },
    },
    "send_file_telegram": {
        "typical_use_cases": ["Send a file, document, photo, or audio recording to user's Telegram chat"],
        "anti_patterns": ["Do NOT use for regular text notifications without a file (use send_telegram_notification or notify_job_status instead)"],
        "output_type": "string",
        "param_descriptions": {
            "file_path": "Absolute path to the file to send",
            "caption": "Optional text caption/message to send with the file"
        },
    },
}


class ToolAwarenessEngine:
    """
    Builds and maintains a rich knowledge base about every tool
    by merging registry metadata with behavioral annotations and
    runtime health data.

    Usage:
        awareness = get_tool_awareness()
        awareness.refresh()  # Sync with live registry + health
        knowledge = awareness.get_tool_knowledge("read_file")
        context = awareness.format_for_planner()
    """

    def __init__(self):
        self._knowledge: Dict[str, ToolKnowledge] = {}
        self._last_refresh: float = 0
        self._refresh_interval: float = 30.0  # seconds

    def refresh(self, force: bool = False):
        """Sync knowledge base with live tool registry and health data."""
        now = time.time()
        if not force and (now - self._last_refresh) < self._refresh_interval:
            return  # Still fresh

        try:
            from tools.universal_registry import get_universal_registry
            registry = get_universal_registry()
            tools = registry.get_all_tools()
        except Exception as e:
            logger.warning(f"Cannot refresh tool awareness — registry unavailable: {e}")
            return

        # Load health data
        health_data: Dict[str, Any] = {}
        try:
            from tools.tool_health import get_health_tracker
            health_data = get_health_tracker().get_all_metrics()
        except Exception:
            pass

        # Build knowledge for each tool
        for tool in tools:
            behavioral = _TOOL_BEHAVIORAL_KNOWLEDGE.get(tool.name, {})
            health = health_data.get(tool.name, {})

            # Get optional parameters from both the tool's input schema and behavioral annotations
            schema_optionals = [p.name for p in tool.input_schema.params if not p.required] if tool.input_schema else []
            hardcoded_optionals = behavioral.get("optional_params", [])
            combined_optionals = list(dict.fromkeys(schema_optionals + hardcoded_optionals))

            knowledge = ToolKnowledge(
                name=tool.name,
                description=tool.description,
                category=tool.category,
                risk_level=tool.risk_level.value,
                required_params=tool.required_params,
                optional_params=combined_optionals,
                param_descriptions=behavioral.get("param_descriptions", {}),
                output_type=behavioral.get("output_type", "string"),
                output_description=behavioral.get("output_description", ""),
                typical_use_cases=behavioral.get("typical_use_cases", []),
                anti_patterns=behavioral.get("anti_patterns", []),
                prerequisites=behavioral.get("prerequisites", []),
                follow_ups=behavioral.get("follow_ups", []),
                limitations=behavioral.get("limitations", []),
                total_runs=health.get("total_runs", 0),
                success_rate=health.get("success_rate", 1.0),
                avg_execution_time_ms=health.get("avg_execution_time_ms", 0.0),
                last_error=health.get("last_error"),
                consecutive_failures=0,  # Updated by feedback loop
            )
            self._knowledge[tool.name] = knowledge

        self._last_refresh = now
        logger.info(f"Tool awareness refreshed: {len(self._knowledge)} tools indexed")

    # ── Queries ────────────────────────────────────────────────────────

    def get_tool_knowledge(self, name: str) -> Optional[ToolKnowledge]:
        """Get rich knowledge about a specific tool."""
        self.refresh()
        return self._knowledge.get(name)

    def get_all_knowledge(self) -> Dict[str, ToolKnowledge]:
        """Get knowledge for all tools."""
        self.refresh()
        return dict(self._knowledge)

    def get_tools_for_intent(self, intent_keywords: List[str]) -> List[ToolKnowledge]:
        """Find tools whose use cases match the given intent keywords."""
        self.refresh()
        matches = []
        for tk in self._knowledge.values():
            score = 0
            all_text = " ".join(tk.typical_use_cases + [tk.description]).lower()
            for kw in intent_keywords:
                if kw.lower() in all_text:
                    score += 1
            if score > 0:
                matches.append((tk, score))
        matches.sort(key=lambda x: x[1], reverse=True)
        return [tk for tk, _ in matches]

    def get_anti_patterns_for_tool(self, name: str) -> List[str]:
        """Get anti-patterns (when NOT to use) for a tool."""
        tk = self._knowledge.get(name)
        return tk.anti_patterns if tk else []

    def is_tool_reliable(self, name: str, threshold: float = 0.5) -> bool:
        """Check if a tool has an acceptable success rate."""
        tk = self._knowledge.get(name)
        if not tk or tk.total_runs < 3:
            return True  # Optimistic for untested tools
        return tk.success_rate >= threshold

    def get_unreliable_tools(self) -> List[str]:
        """List tools with poor reliability."""
        self.refresh()
        return [
            name for name, tk in self._knowledge.items()
            if tk.total_runs >= 3 and tk.success_rate < 0.5
        ]

    # ── LLM Formatting ────────────────────────────────────────────────

    def format_for_planner(self, include_stats: bool = True, tool_names: List[str] = None) -> str:
        """Format tool knowledge for the planner's system prompt.
        This replaces the basic registry.format_for_llm() with awareness-enriched data."""
        self.refresh()
        lines = []
        targets = tool_names if tool_names is not None else list(self._knowledge.keys())
        for name in targets:
            tk = self._knowledge.get(name)
            if tk:
                lines.append(tk.to_llm_string())
        return "\n".join(lines)

    def format_rich_for_planner(self, tool_names: List[str] = None) -> str:
        """Full detail format for specific tools (used during re-planning)."""
        self.refresh()
        lines = []
        targets = tool_names or list(self._knowledge.keys())
        for name in targets:
            tk = self._knowledge.get(name)
            if tk:
                lines.append(tk.to_rich_llm_string())
        return "\n\n".join(lines)

    def get_tool_names_list(self) -> List[str]:
        """Return list of all known tool names."""
        self.refresh()
        return list(self._knowledge.keys())

    # ── Update from Feedback ──────────────────────────────────────────

    def update_from_execution(self, tool_name: str, success: bool,
                               execution_time_ms: float, error: Optional[str] = None):
        """Update runtime stats for a tool after execution."""
        tk = self._knowledge.get(tool_name)
        if not tk:
            return

        tk.total_runs += 1
        if success:
            tk.consecutive_failures = 0
            # Running average
            tk.success_rate = (
                (tk.success_rate * (tk.total_runs - 1) + 1.0) / tk.total_runs
            )
        else:
            tk.consecutive_failures += 1
            tk.last_error = error
            tk.success_rate = (
                (tk.success_rate * (tk.total_runs - 1) + 0.0) / tk.total_runs
            )
        
        # Update average execution time
        tk.avg_execution_time_ms = (
            (tk.avg_execution_time_ms * (tk.total_runs - 1) + execution_time_ms) / tk.total_runs
        )


# ── Global Singleton ─────────────────────────────────────────────────
_tool_awareness: Optional[ToolAwarenessEngine] = None


def get_tool_awareness() -> ToolAwarenessEngine:
    global _tool_awareness
    if _tool_awareness is None:
        _tool_awareness = ToolAwarenessEngine()
    return _tool_awareness
