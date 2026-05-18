"""
Aeris AI OS — System Self-Awareness (Part 1)
═══════════════════════════════════════════════════════════════════════
AERIS's introspective model of itself. Knows:
  • What modules exist and their roles
  • What the system can and cannot do
  • Current system state (active task, previous steps, failures)
  • Resource availability and operational constraints

This is NOT just documentation — it is a live, queryable data structure
that the Planner and ContextInjector read before every decision.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisSystemAwareness")


# ─── Module Descriptors ──────────────────────────────────────────────

class ModuleRole(str, Enum):
    PLANNER   = "planner"
    EXECUTOR  = "executor"
    OBSERVER  = "observer"
    MEMORY    = "memory"
    TOOLS     = "tools"
    SECURITY  = "security"
    ENGINE    = "engine"
    INTELLIGENCE = "intelligence"


@dataclass(frozen=True)
class ModuleDescriptor:
    """Describes a single AERIS subsystem."""
    name: str
    role: ModuleRole
    description: str
    capabilities: List[str]
    limitations: List[str]


# ─── System Capabilities ─────────────────────────────────────────────

@dataclass(frozen=True)
class Capability:
    """A single thing AERIS can do."""
    name: str
    description: str
    requires_tool: bool            # True = needs a tool call; False = built-in
    tool_categories: List[str]     # Which tool categories serve this capability
    confidence: float = 1.0        # 0-1, how reliably AERIS can do this


# ─── Live System Snapshot ─────────────────────────────────────────────

@dataclass
class SystemSnapshot:
    """Point-in-time snapshot of AERIS's operational state."""
    timestamp: float = field(default_factory=time.time)
    current_task_id: Optional[str] = None
    current_task_objective: Optional[str] = None
    current_step_index: int = 0
    total_steps: int = 0
    recent_failures: List[Dict[str, Any]] = field(default_factory=list)
    recent_successes: List[Dict[str, Any]] = field(default_factory=list)
    tools_available: int = 0
    tools_healthy: int = 0
    active_cooldowns: List[str] = field(default_factory=list)
    memory_context_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "current_task_id": self.current_task_id,
            "current_task_objective": self.current_task_objective,
            "progress": f"{self.current_step_index}/{self.total_steps}",
            "recent_failures": self.recent_failures[-3:],
            "recent_successes": self.recent_successes[-3:],
            "tools_available": self.tools_available,
            "tools_healthy": self.tools_healthy,
            "active_cooldowns": self.active_cooldowns,
            "memory_context_keys": self.memory_context_keys,
        }

    def to_llm_string(self) -> str:
        """Compact string for LLM context injection."""
        lines = [f"[System State @ {time.strftime('%H:%M:%S', time.localtime(self.timestamp))}]"]
        if self.current_task_objective:
            lines.append(f"  Active task: {self.current_task_objective}")
            lines.append(f"  Progress: step {self.current_step_index}/{self.total_steps}")
        if self.recent_failures:
            lines.append(f"  Recent failures ({len(self.recent_failures)}):")
            for f in self.recent_failures[-2:]:
                lines.append(f"    - {f.get('tool', '?')}: {f.get('error', '?')[:80]}")
        lines.append(f"  Tools: {self.tools_available} available, {self.tools_healthy} healthy")
        if self.active_cooldowns:
            lines.append(f"  Cooldowns: {', '.join(self.active_cooldowns)}")
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════
#  SYSTEM AWARENESS ENGINE
# ═════════════════════════════════════════════════════════════════════

class SystemAwareness:
    """
    AERIS's self-model. Provides introspection on modules, capabilities,
    and live system state.

    Usage:
        awareness = get_system_awareness()
        snapshot = awareness.get_snapshot()
        caps = awareness.get_capabilities()
        can_do = awareness.can_perform("generate a website")
    """

    def __init__(self):
        self._modules = self._build_module_map()
        self._capabilities = self._build_capability_map()
        self._recent_failures: List[Dict[str, Any]] = []
        self._recent_successes: List[Dict[str, Any]] = []

    # ── Module Knowledge ──────────────────────────────────────────────

    def _build_module_map(self) -> Dict[str, ModuleDescriptor]:
        return {
            "planner": ModuleDescriptor(
                name="PlannerAgent",
                role=ModuleRole.PLANNER,
                description="Decomposes user objectives into multi-step execution plans using LLM intelligence.",
                capabilities=["intent_classification", "task_decomposition", "tool_assignment", "parameter_generation"],
                limitations=["depends_on_llm_availability", "max_1024_token_plans", "cannot_execute_tools_directly"],
            ),
            "executor": ModuleDescriptor(
                name="ExecutorAgent",
                role=ModuleRole.EXECUTOR,
                description="Executes planned steps by invoking tools through the Universal Tool Executor Service.",
                capabilities=["tool_invocation", "parameter_validation", "receipt_generation", "error_capture"],
                limitations=["single_tool_per_step", "no_parallel_execution", "depends_on_tool_registry"],
            ),
            "observer": ModuleDescriptor(
                name="ObserverAgent",
                role=ModuleRole.OBSERVER,
                description="Evaluates execution outcomes using LLM, verifies correctness, and decides recovery strategies.",
                capabilities=["output_evaluation", "error_classification", "recovery_decision", "false_positive_detection"],
                limitations=["depends_on_llm_availability", "heuristic_fallback_is_basic"],
            ),
            "memory": ModuleDescriptor(
                name="MemorySystem",
                role=ModuleRole.MEMORY,
                description="Manages short-term session context and long-term persistent facts, preferences, and command history.",
                capabilities=["context_storage", "fact_recall", "preference_tracking", "command_history", "execution_context"],
                limitations=["keyword_search_only", "max_500_facts", "max_1000_commands"],
            ),
            "tools": ModuleDescriptor(
                name="UniversalToolSystem",
                role=ModuleRole.TOOLS,
                description="Registry, loader, selector, executor, and health tracker for all tools.",
                capabilities=["tool_registration", "dynamic_loading", "tool_selection", "safe_execution", "health_tracking"],
                limitations=["tools_must_be_registered", "no_auto_install_dependencies", "no_parallel_tool_execution"],
            ),
            "security": ModuleDescriptor(
                name="SecuritySystem",
                role=ModuleRole.SECURITY,
                description="Permission system with whitelist/blacklist, risk-level policies, cooldowns, and dangerous pattern detection.",
                capabilities=["permission_checking", "pattern_blocking", "cooldown_enforcement", "user_approval_flow"],
                limitations=["no_sandboxing_for_builtins", "high_risk_auto_approved_in_autonomous"],
            ),
            "engine": ModuleDescriptor(
                name="OSEngine",
                role=ModuleRole.ENGINE,
                description="Central event loop orchestrating THINK → PLAN → EXECUTE → VERIFY → IMPROVE cycle.",
                capabilities=["objective_processing", "step_retry", "self_healing_params", "grounded_response", "error_classification"],
                limitations=["max_3_step_retries", "max_5_total_retries", "synchronous_step_execution"],
            ),
            "intelligence": ModuleDescriptor(
                name="IntelligenceLayer",
                role=ModuleRole.INTELLIGENCE,
                description="Self-awareness, tool awareness, context injection, selection intelligence, and feedback learning.",
                capabilities=["self_introspection", "tool_knowledge", "context_assembly", "intent_mapping", "feedback_learning"],
                limitations=["depends_on_tool_health_data", "keyword_based_capability_matching"],
            ),
        }

    # ── Capability Knowledge ──────────────────────────────────────────

    def _build_capability_map(self) -> Dict[str, Capability]:
        return {
            "file_operations": Capability(
                "file_operations", "Read, write, edit, delete, list, search files",
                requires_tool=True, tool_categories=["file"],
            ),
            "shell_execution": Capability(
                "shell_execution", "Run terminal/shell/bash commands",
                requires_tool=True, tool_categories=["system", "shell"],
            ),
            "web_search": Capability(
                "web_search", "Search the web, scrape websites, research topics",
                requires_tool=True, tool_categories=["search", "research"],
            ),
            "app_control": Capability(
                "app_control", "Open, close, and manage applications",
                requires_tool=True, tool_categories=["automation"],
            ),
            "media_playback": Capability(
                "media_playback", "Play music, songs, and videos",
                requires_tool=True, tool_categories=["automation"],
            ),
            "code_generation": Capability(
                "code_generation", "Generate code in multiple languages",
                requires_tool=True, tool_categories=["generation"],
            ),
            "website_generation": Capability(
                "website_generation", "Generate complete websites and dashboards",
                requires_tool=True, tool_categories=["generation"],
            ),
            "image_generation": Capability(
                "image_generation", "Generate AI images from text prompts",
                requires_tool=True, tool_categories=["generation"],
            ),
            "video_generation": Capability(
                "video_generation", "Generate AI videos from text prompts",
                requires_tool=True, tool_categories=["generation"],
            ),
            "screen_analysis": Capability(
                "screen_analysis", "Analyze screen content, OCR, camera feed",
                requires_tool=True, tool_categories=["vision"],
            ),
            "conversation": Capability(
                "conversation", "Answer questions, chat, explain concepts",
                requires_tool=True, tool_categories=["conversation"],
            ),
            "realtime_info": Capability(
                "realtime_info", "Get real-time news, weather, prices, current events",
                requires_tool=True, tool_categories=["search"],
            ),
            "knowledge_search": Capability(
                "knowledge_search", "Search indexed workspace files via RAG",
                requires_tool=True, tool_categories=["knowledge"],
            ),
            "file_conversion": Capability(
                "file_conversion", "Convert files between formats (pdf, docx, csv, etc.)",
                requires_tool=True, tool_categories=["file"],
            ),
            "navigation": Capability(
                "navigation", "Open maps, get directions",
                requires_tool=True, tool_categories=["navigation"],
            ),
            "system_control": Capability(
                "system_control", "Volume, mute, shutdown, restart, lock",
                requires_tool=True, tool_categories=["system"],
            ),
            "tool_creation": Capability(
                "tool_creation", "Create new tools dynamically using AI",
                requires_tool=True, tool_categories=["generation"],
            ),
            "workflow_automation": Capability(
                "workflow_automation", "Run saved multi-step workflows",
                requires_tool=True, tool_categories=["automation"],
            ),
        }

    # ── Queries ────────────────────────────────────────────────────────

    def get_modules(self) -> Dict[str, ModuleDescriptor]:
        return dict(self._modules)

    def get_module(self, role: str) -> Optional[ModuleDescriptor]:
        return self._modules.get(role)

    def get_capabilities(self) -> Dict[str, Capability]:
        return dict(self._capabilities)

    def can_perform(self, description: str) -> List[Capability]:
        """Find capabilities that match a natural-language description."""
        desc_lower = description.lower()
        matches = []
        for cap in self._capabilities.values():
            # Check name and description words
            cap_words = set(cap.name.split("_") + cap.description.lower().split())
            desc_words = set(desc_lower.split())
            overlap = len(cap_words & desc_words)
            if overlap >= 1:
                matches.append(cap)
        return matches

    def get_limitations(self) -> List[str]:
        """Get all system-wide limitations."""
        all_limits = []
        for mod in self._modules.values():
            for lim in mod.limitations:
                all_limits.append(f"[{mod.name}] {lim}")
        return all_limits

    # ── Live State ────────────────────────────────────────────────────

    def record_success(self, tool_name: str, step_desc: str, result_preview: str = ""):
        self._recent_successes.append({
            "tool": tool_name,
            "step": step_desc,
            "result": result_preview[:200],
            "time": time.time(),
        })
        # Keep bounded
        if len(self._recent_successes) > 20:
            self._recent_successes = self._recent_successes[-20:]

    def record_failure(self, tool_name: str, step_desc: str, error: str):
        self._recent_failures.append({
            "tool": tool_name,
            "step": step_desc,
            "error": error[:200],
            "time": time.time(),
        })
        if len(self._recent_failures) > 20:
            self._recent_failures = self._recent_failures[-20:]

    def get_snapshot(self) -> SystemSnapshot:
        """Build a live system snapshot by querying all subsystems."""
        snapshot = SystemSnapshot()

        # Query state manager
        try:
            from engine.state_manager import global_state_manager
            current_task = global_state_manager.get_current_task()
            if current_task:
                snapshot.current_task_id = current_task.task_id
                snapshot.current_task_objective = current_task.description
                snapshot.current_step_index = current_task.current_step_index
                snapshot.total_steps = len(current_task.steps)
        except Exception:
            pass

        # Query tool registry
        try:
            from tools.universal_registry import get_universal_registry
            reg = get_universal_registry()
            all_tools = reg.get_all_tools()
            snapshot.tools_available = len(all_tools)
            snapshot.tools_healthy = len([t for t in all_tools if t.is_enabled])
        except Exception:
            pass

        # Query permissions for cooldowns
        try:
            from tools.tool_permissions import get_permission_system
            perms = get_permission_system()
            summary = perms.get_permissions_summary()
            snapshot.active_cooldowns = list(summary.get("active_cooldowns", {}).keys())
        except Exception:
            pass

        # Query memory for context keys
        try:
            from memory.memory_system import ShortTermMemory
            # We access via the global if available
            snapshot.memory_context_keys = []  # Will be populated if memory agent provides
        except Exception:
            pass

        snapshot.recent_failures = list(self._recent_failures)
        snapshot.recent_successes = list(self._recent_successes)

        return snapshot

    def to_llm_context(self) -> str:
        """Generate a compact self-awareness context string for the LLM."""
        snapshot = self.get_snapshot()
        cap_names = ", ".join(self._capabilities.keys())
        return (
            f"[AERIS Self-Awareness]\n"
            f"  Modules: {', '.join(self._modules.keys())}\n"
            f"  Capabilities: {cap_names}\n"
            f"{snapshot.to_llm_string()}"
        )


# ── Global Singleton ─────────────────────────────────────────────────
_system_awareness: Optional[SystemAwareness] = None


def get_system_awareness() -> SystemAwareness:
    global _system_awareness
    if _system_awareness is None:
        _system_awareness = SystemAwareness()
    return _system_awareness
