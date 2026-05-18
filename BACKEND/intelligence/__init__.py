"""
Aeris AI OS — Self-Aware & Tool-Aware Intelligence Layer
═══════════════════════════════════════════════════════════════════════
The Intelligence Layer gives AERIS full awareness of:
  • Its own modules, capabilities, and limitations
  • All available tools, their schemas, behaviors, and constraints
  • Real-time system state, execution context, and history
  • Intelligent tool selection with feedback-driven learning

Components:
  - SystemAwareness       — Self-model of AERIS's modules and capabilities
  - ToolAwareness         — Dynamic tool knowledge with rich metadata
  - ContextInjector       — Pre-planning context assembly (no hallucinated tools)
  - SelectionIntelligence — Intent→tool mapping with ranking & pipeline support
  - FeedbackLoop          — Post-execution learning and stats update
  - ErrorAwareness        — Intelligent failure analysis and recovery routing
  - SafetyAwareness       — Risk-aware execution gating
  - ConsistencyGuard      — Schema validation and output verification
═══════════════════════════════════════════════════════════════════════
"""

from intelligence.system_awareness import SystemAwareness, get_system_awareness
from intelligence.tool_awareness import ToolAwarenessEngine, get_tool_awareness
from intelligence.context_injector import ContextInjector, get_context_injector
from intelligence.selection_intelligence import SelectionIntelligence, get_selection_intelligence
from intelligence.feedback_loop import FeedbackLoop, get_feedback_loop
from intelligence.error_awareness import ErrorAwareness, get_error_awareness
from intelligence.safety_awareness import SafetyAwareness, get_safety_awareness
from intelligence.consistency_guard import ConsistencyGuard, get_consistency_guard

__all__ = [
    "SystemAwareness", "get_system_awareness",
    "ToolAwarenessEngine", "get_tool_awareness",
    "ContextInjector", "get_context_injector",
    "SelectionIntelligence", "get_selection_intelligence",
    "FeedbackLoop", "get_feedback_loop",
    "ErrorAwareness", "get_error_awareness",
    "SafetyAwareness", "get_safety_awareness",
    "ConsistencyGuard", "get_consistency_guard",
]
