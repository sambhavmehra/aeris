"""
Aeris AI OS — Safety Awareness (Part 7)
═══════════════════════════════════════════════════════════════════════
Risk analysis and safety enforcement. Extends the basic Permission System
with contextual awareness:
  • Contextual Risk Assessment (is this "rm" safe in this dir?)
  • Pattern Detection (preventing prompt injections or malicious tasks)
  • Impact Analysis (what will this tool do?)
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisSafetyAwareness")

@dataclass
class SafetyAssessment:
    is_safe: bool
    risk_level: str
    reason: str
    requires_user_approval: bool = False
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

class SafetyAwareness:
    """
    Context-aware safety checks.
    Evaluates not just the tool's inherent risk, but the specific
    parameters being passed.
    """

    def __init__(self):
        self._suspicious_patterns = [
            r"rm\s+-rf\s+/",
            r"format\s+[a-z]:",
            r"DROP\s+TABLE",
            r"DELETE\s+FROM",
            r">\s*/dev/sda",
            r"curl.*\|.*sh",
            r"wget.*\|.*bash",
        ]

    def evaluate_execution(self, tool_name: str, params: Dict[str, Any]) -> SafetyAssessment:
        """Evaluate if a specific execution is safe."""
        warnings = []
        is_safe = True
        risk_level = "safe"
        requires_user_approval = False
        reason = "Execution passed safety checks."

        try:
            from intelligence.tool_awareness import get_tool_awareness
            tk = get_tool_awareness().get_tool_knowledge(tool_name)
            if tk:
                risk_level = tk.risk_level
                if risk_level == "critical":
                    is_safe = False
                    requires_user_approval = True
                    reason = "Critical risk tool requires explicit user approval."
        except Exception:
            pass

        # Check parameter contents for suspicious patterns
        params_str = str(params).lower()
        for pattern in self._suspicious_patterns:
            if re.search(pattern, params_str):
                is_safe = False
                requires_user_approval = True
                reason = f"Suspicious pattern detected in parameters: {pattern}"
                warnings.append("Destructive command pattern identified.")
                break

        # Contextual checks
        if tool_name == "delete_file" and "path" in params:
            path = str(params["path"]).lower()
            if any(sys_dir in path for sys_dir in ["c:\\windows", "system32", "/etc", "/bin", "/usr/bin", "/var"]):
                is_safe = False
                reason = "Attempted to delete a system file or directory."
                requires_user_approval = True

        return SafetyAssessment(
            is_safe=is_safe,
            risk_level=risk_level,
            reason=reason,
            requires_user_approval=requires_user_approval,
            warnings=warnings
        )

# ── Global Singleton ─────────────────────────────────────────────────
_safety_awareness: Optional[SafetyAwareness] = None

def get_safety_awareness() -> SafetyAwareness:
    global _safety_awareness
    if _safety_awareness is None:
        _safety_awareness = SafetyAwareness()
    return _safety_awareness
