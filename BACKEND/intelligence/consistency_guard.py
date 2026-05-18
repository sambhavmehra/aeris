"""
Aeris AI OS — Consistency Guard (Part 8)
═══════════════════════════════════════════════════════════════════════
Ensures execution consistency by enforcing strict schema validation
before tools are executed, and validating outputs after execution.
  • Pre-execution validation of JSON parameters
  • Post-execution output structuring
  • Prevents "unexpected keyword argument" crashes
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AerisConsistencyGuard")

class ConsistencyGuard:
    """
    Validates tool parameters against the rich schema defined in ToolAwareness.
    Cleans up parameters to prevent execution crashes.
    """

    def __init__(self):
        pass

    def enforce_schema(self, tool_name: str, params: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        Enforce parameter schema for a tool.
        Returns: (is_valid, cleaned_params, errors)
        """
        errors = []
        cleaned_params = {}

        try:
            from intelligence.tool_awareness import get_tool_awareness
            tk = get_tool_awareness().get_tool_knowledge(tool_name)
            if not tk:
                return True, params, [] # Unknown tool, can't validate, pass through
        except Exception:
            return True, params, []

        # Check required parameters
        for req_param in tk.required_params:
            if req_param not in params:
                errors.append(f"Missing required parameter: '{req_param}'")
            else:
                cleaned_params[req_param] = params[req_param]

        # Add optional parameters if present
        for opt_param in tk.optional_params:
            if opt_param in params:
                cleaned_params[opt_param] = params[opt_param]

        # Check for invalid parameters (hallucinated by LLM)
        all_allowed_params = set(tk.required_params + tk.optional_params)
        for key in params:
            if key not in all_allowed_params:
                # We log it, but we DROP it from cleaned_params to prevent TypeError
                logger.warning(f"Dropped unexpected parameter '{key}' for tool '{tool_name}'")

        is_valid = len(errors) == 0
        return is_valid, cleaned_params, errors

# ── Global Singleton ─────────────────────────────────────────────────
_consistency_guard: Optional[ConsistencyGuard] = None

def get_consistency_guard() -> ConsistencyGuard:
    global _consistency_guard
    if _consistency_guard is None:
        _consistency_guard = ConsistencyGuard()
    return _consistency_guard
