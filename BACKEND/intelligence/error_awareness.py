"""
Aeris AI OS — Error Awareness (Part 6)
═══════════════════════════════════════════════════════════════════════
Intelligent failure analysis and recovery routing. Ensures AERIS:
  • Understands WHY a tool failed (root cause analysis)
  • Knows which tool to try next (recovery routing)
  • Avoids repeating the same mistake (failure memory)
  • Provides actionable fix suggestions

Goes beyond basic error classification — uses feedback history
and tool awareness to make intelligent recovery decisions.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AerisErrorAwareness")


@dataclass
class ErrorAnalysis:
    """Structured analysis of a tool execution failure."""
    tool_name: str
    error_message: str
    error_category: str              # e.g., "not_found", "permission_denied"
    root_cause: str                   # Human-readable root cause
    is_transient: bool                # True = retry might work
    is_param_error: bool              # True = parameters were wrong
    is_tool_wrong: bool               # True = wrong tool was chosen
    recovery_strategy: str            # "retry_same", "retry_different_params", "use_alternative", "abort"
    suggested_fix: str = ""           # What to change
    alternative_tool: Optional[str] = None   # Tool to try instead
    should_avoid_in_future: bool = False     # True = mark as unreliable
    confidence: float = 0.7

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "error_category": self.error_category,
            "root_cause": self.root_cause,
            "is_transient": self.is_transient,
            "is_param_error": self.is_param_error,
            "is_tool_wrong": self.is_tool_wrong,
            "recovery_strategy": self.recovery_strategy,
            "suggested_fix": self.suggested_fix,
            "alternative_tool": self.alternative_tool,
            "should_avoid_in_future": self.should_avoid_in_future,
            "confidence": self.confidence,
        }


# ─── Error Pattern Definitions ───────────────────────────────────────

_ERROR_PATTERNS = [
    # File system errors
    {
        "patterns": ["not found", "no such file", "does not exist", "filenotfounderror"],
        "category": "not_found",
        "is_transient": False,
        "is_param_error": True,
        "root_cause": "File or path does not exist",
        "default_strategy": "retry_different_params",
        "fix_hint": "Check and correct the file path. Use find_system_file to locate it first.",
    },
    # Permission errors
    {
        "patterns": ["permission denied", "access denied", "forbidden", "unauthorized", "access is denied"],
        "category": "permission_denied",
        "is_transient": False,
        "is_param_error": False,
        "root_cause": "Insufficient permissions to perform this action",
        "default_strategy": "escalate_to_user",
        "fix_hint": "Run with elevated permissions or choose a different target path.",
    },
    # Network errors
    {
        "patterns": ["timeout", "timed out", "connection refused", "unreachable", "connectionerror", "network"],
        "category": "network_error",
        "is_transient": True,
        "is_param_error": False,
        "root_cause": "Network connectivity issue or service unavailable",
        "default_strategy": "retry_same",
        "fix_hint": "Check internet connection. Retry after a short delay.",
    },
    # Rate limiting
    {
        "patterns": ["rate limit", "429", "too many requests", "quota exceeded"],
        "category": "rate_limited",
        "is_transient": True,
        "is_param_error": False,
        "root_cause": "API rate limit exceeded",
        "default_strategy": "retry_same",
        "fix_hint": "Wait before retrying. Use exponential backoff.",
    },
    # Authentication
    {
        "patterns": ["api key", "authentication", "invalid key", "no api", "auth"],
        "category": "auth_error",
        "is_transient": False,
        "is_param_error": False,
        "root_cause": "API key missing or invalid",
        "default_strategy": "abort",
        "fix_hint": "Check API key configuration in .env file.",
    },
    # Parse errors
    {
        "patterns": ["syntax error", "parse error", "invalid json", "unexpected token", "json.decoder"],
        "category": "parse_error",
        "is_transient": False,
        "is_param_error": True,
        "root_cause": "Invalid data format in input or output",
        "default_strategy": "retry_different_params",
        "fix_hint": "Ensure input data is properly formatted.",
    },
    # Missing parameters
    {
        "patterns": ["missing required", "missing parameter", "unexpected keyword argument", "takes 0 positional"],
        "category": "missing_params",
        "is_transient": False,
        "is_param_error": True,
        "root_cause": "Required parameters missing or wrong parameter names used",
        "default_strategy": "retry_different_params",
        "fix_hint": "Check required parameters and ensure all are provided with correct names.",
    },
    # Tool not found
    {
        "patterns": ["not found in registry", "no tool named", "tool not found"],
        "category": "tool_not_found",
        "is_transient": False,
        "is_param_error": False,
        "root_cause": "The specified tool does not exist in the registry",
        "default_strategy": "use_alternative",
        "fix_hint": "Use a different tool that provides similar functionality.",
    },
    # Import / dependency errors
    {
        "patterns": ["importerror", "modulenotfounderror", "no module named"],
        "category": "dependency_error",
        "is_transient": False,
        "is_param_error": False,
        "root_cause": "Required Python module is not installed",
        "default_strategy": "abort",
        "fix_hint": "Install the missing dependency.",
    },
    # Windows-specific
    {
        "patterns": ["is not recognized", "the system cannot find"],
        "category": "command_error",
        "is_transient": False,
        "is_param_error": True,
        "root_cause": "Command not recognized or path not found on Windows",
        "default_strategy": "retry_different_params",
        "fix_hint": "Use full path to executable. Check command syntax for Windows.",
    },
    # Security blocks
    {
        "patterns": ["security_blocked", "blocked", "dangerous", "destructive pattern"],
        "category": "security_blocked",
        "is_transient": False,
        "is_param_error": False,
        "root_cause": "Security system blocked the operation as potentially dangerous",
        "default_strategy": "escalate_to_user",
        "fix_hint": "Get user approval or use a safer alternative.",
    },
    # Resource errors
    {
        "patterns": ["out of memory", "memory", "disk full", "no space"],
        "category": "resource_error",
        "is_transient": False,
        "is_param_error": False,
        "root_cause": "System resource exhaustion",
        "default_strategy": "abort",
        "fix_hint": "Free up system resources before retrying.",
    },
]


class ErrorAwareness:
    """
    Intelligent failure analysis engine. Given a tool execution error,
    produces a structured ErrorAnalysis with root cause, recovery strategy,
    and alternative tool suggestions.

    Usage:
        ea = get_error_awareness()
        analysis = ea.analyze("run_bash", "python: command not found", retry_count=1)
        if analysis.recovery_strategy == "use_alternative":
            next_tool = analysis.alternative_tool
    """

    def __init__(self):
        # Track errors seen in this session to avoid repeating same fixes
        self._error_history: List[Dict[str, Any]] = []

    def analyze(
        self,
        tool_name: str,
        error_message: str,
        retry_count: int = 0,
        objective: str = "",
        tool_params: Dict[str, Any] = None,
    ) -> ErrorAnalysis:
        """
        Full error analysis pipeline:
          1. Pattern match to classify error
          2. Check if this is a repeated error
          3. Determine if retry will help
          4. Suggest parameter fixes or alternative tools
          5. Decide recovery strategy
        """
        error_lower = error_message.lower()
        tool_params = tool_params or {}

        # 1. Pattern-match error category
        matched_pattern = None
        for pattern in _ERROR_PATTERNS:
            if any(p in error_lower for p in pattern["patterns"]):
                matched_pattern = pattern
                break

        if matched_pattern:
            category = matched_pattern["category"]
            is_transient = matched_pattern["is_transient"]
            is_param_error = matched_pattern["is_param_error"]
            root_cause = matched_pattern["root_cause"]
            base_strategy = matched_pattern["default_strategy"]
            fix_hint = matched_pattern["fix_hint"]
        else:
            category = "unknown"
            is_transient = False
            is_param_error = False
            root_cause = f"Unknown error in {tool_name}"
            base_strategy = "retry_same" if retry_count < 2 else "abort"
            fix_hint = ""

        # 2. Check for repeated errors (same tool, same category)
        is_repeated = self._is_repeated_error(tool_name, category)

        # 3. Adjust strategy based on retry count and repetition
        strategy = self._adjust_strategy(
            base_strategy, retry_count, is_repeated, is_transient, tool_name
        )

        # 4. Find alternative tool if needed
        alternative = None
        is_tool_wrong = False
        if strategy == "use_alternative" or (is_repeated and not is_transient):
            alternative = self._find_alternative(tool_name, objective)
            if alternative:
                is_tool_wrong = True

        # 5. Generate specific fix suggestion
        suggested_fix = self._generate_fix_suggestion(
            tool_name, error_message, category, tool_params, fix_hint
        )

        # 6. Determine if tool should be avoided
        should_avoid = self._should_avoid(tool_name, retry_count, is_repeated)

        # Record this error
        self._error_history.append({
            "tool": tool_name,
            "category": category,
            "error": error_message[:200],
            "retry": retry_count,
        })
        if len(self._error_history) > 50:
            self._error_history = self._error_history[-50:]

        return ErrorAnalysis(
            tool_name=tool_name,
            error_message=error_message,
            error_category=category,
            root_cause=root_cause,
            is_transient=is_transient,
            is_param_error=is_param_error,
            is_tool_wrong=is_tool_wrong,
            recovery_strategy=strategy,
            suggested_fix=suggested_fix,
            alternative_tool=alternative,
            should_avoid_in_future=should_avoid,
            confidence=0.85 if matched_pattern else 0.5,
        )

    # ── Internal Analysis ─────────────────────────────────────────────

    def _is_repeated_error(self, tool_name: str, category: str) -> bool:
        """Check if we've seen this same error type for this tool recently."""
        recent = self._error_history[-10:]
        same_errors = [
            e for e in recent
            if e["tool"] == tool_name and e["category"] == category
        ]
        return len(same_errors) >= 2

    def _adjust_strategy(
        self, base_strategy: str, retry_count: int,
        is_repeated: bool, is_transient: bool, tool_name: str
    ) -> str:
        """Adjust recovery strategy based on context."""

        # If we've retried too many times, escalate
        if retry_count >= 3:
            if base_strategy in ("retry_same", "retry_different_params"):
                return "abort"

        # If error is repeated and not transient, don't retry same
        if is_repeated and not is_transient:
            if base_strategy == "retry_same":
                return "use_alternative"

        # If error is transient but we already retried twice, abort
        if is_transient and retry_count >= 2:
            return "abort"

        # Check feedback loop for chronic failures
        try:
            from intelligence.feedback_loop import get_feedback_loop
            avoid, reason = get_feedback_loop().should_avoid_tool(tool_name)
            if avoid and base_strategy in ("retry_same", "retry_different_params"):
                return "use_alternative"
        except Exception:
            pass

        return base_strategy

    def _find_alternative(self, tool_name: str, objective: str) -> Optional[str]:
        """Find an alternative tool for the same task."""
        try:
            from intelligence.feedback_loop import get_feedback_loop
            alt = get_feedback_loop().suggest_alternative(tool_name, objective)
            if alt:
                return alt
        except Exception:
            pass

        # Fallback: check known equivalents
        _EQUIVALENTS = {
            "run_bash": "smart_shell_generate",
            "smart_shell_generate": "run_bash",
            "read_file": "read_system_file",
            "read_system_file": "read_file",
            "list_dir": "list_system_dir",
            "list_system_dir": "list_dir",
            "google_search": "realtime_search",
            "realtime_search": "web_research",
            "web_research": "realtime_search",
        }
        return _EQUIVALENTS.get(tool_name)

    def _generate_fix_suggestion(
        self, tool_name: str, error: str, category: str,
        params: Dict[str, Any], base_hint: str
    ) -> str:
        """Generate a specific fix suggestion based on error details."""
        suggestions = [base_hint] if base_hint else []

        if category == "not_found" and "path" in params:
            path = params["path"]
            suggestions.append(f"Current path '{path}' was not found. Use find_system_file to locate it.")

        if category == "missing_params":
            # Try to extract which param is missing
            match = re.search(r"missing.*?'(\w+)'", error.lower())
            if match:
                suggestions.append(f"Add the missing parameter: '{match.group(1)}'")

        if category == "command_error" and tool_name == "run_bash":
            suggestions.append("On Windows, use PowerShell syntax. Wrap file paths in double quotes.")

        return " ".join(suggestions) if suggestions else "Review the error and adjust parameters."

    def _should_avoid(self, tool_name: str, retry_count: int, is_repeated: bool) -> bool:
        """Determine if the tool should be marked as unreliable."""
        if retry_count >= 3 and is_repeated:
            return True
        try:
            from intelligence.feedback_loop import get_feedback_loop
            avoid, _ = get_feedback_loop().should_avoid_tool(tool_name)
            return avoid
        except Exception:
            return False

    # ── Queries ────────────────────────────────────────────────────────

    def get_recent_errors(self, tool_name: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Get recent errors, optionally filtered by tool."""
        errors = self._error_history
        if tool_name:
            errors = [e for e in errors if e["tool"] == tool_name]
        return errors[-limit:]

    def has_similar_recent_failure(self, tool_name: str, error_category: str) -> bool:
        """Check if a similar failure occurred very recently."""
        return self._is_repeated_error(tool_name, error_category)


# ── Global Singleton ─────────────────────────────────────────────────
_error_awareness: Optional[ErrorAwareness] = None


def get_error_awareness() -> ErrorAwareness:
    global _error_awareness
    if _error_awareness is None:
        _error_awareness = ErrorAwareness()
    return _error_awareness
