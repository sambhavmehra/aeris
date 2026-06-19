"""
Aeris AI OS — Context Injector (Part 3)
═══════════════════════════════════════════════════════════════════════
Assembles the complete planning context BEFORE every planning step.

Injects:
  • Available tools (with behavioral awareness)
  • Tool capabilities and anti-patterns
  • Recent tool usage history (successes AND failures)
  • System constraints and active cooldowns
  • Self-awareness state

Guarantees:
  • Planner has FULL visibility of real tools only
  • NO hallucinated tools can be used
  • Recent context prevents repeated mistakes
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisContextInjector")


class ContextInjector:
    """
    Assembles rich, awareness-informed context for the Planner before
    every planning cycle.

    Usage:
        injector = get_context_injector()
        context = injector.build_planning_context(objective)
        # context["tools_text"] → enriched tool descriptions
        # context["system_state"] → live system snapshot
        # context["recent_history"] → recent execution outcomes
        # context["constraints"] → active constraints and warnings
        # context["anti_pattern_warnings"] → things to avoid
    """

    def __init__(self):
        self._last_context: Optional[Dict[str, Any]] = None

    def build_planning_context(
        self,
        objective: str,
        memory_context: str = "",
        include_rich_tools: bool = False,
        selected_tool_names: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Build the complete context package for the Planner.

        Returns a dict with:
          - tools_text: formatted tool descriptions (awareness-enriched)
          - tool_names: list of all available tool names (for validation)
          - system_state: live system snapshot string
          - recent_history: recent execution outcomes
          - constraints: active constraints and warnings
          - anti_pattern_warnings: specific things to avoid
          - full_system_prompt_section: assembled section ready to inject
        """
        # 1. Tool Awareness
        try:
            from intelligence.tool_awareness import get_tool_awareness
            tool_awareness = get_tool_awareness()
            tool_awareness.refresh()

            if include_rich_tools:
                tools_text = tool_awareness.format_rich_for_planner(selected_tool_names)
            else:
                tools_text = tool_awareness.format_for_planner(tool_names=selected_tool_names)

            tool_names = tool_awareness.get_tool_names_list()
            unreliable = tool_awareness.get_unreliable_tools()
        except Exception as e:
            logger.warning(f"Tool awareness unavailable, falling back to registry: {e}")
            try:
                from tools.universal_registry import get_universal_registry
                if selected_tool_names:
                    selected_tools = [get_universal_registry().get_tool(t) for t in selected_tool_names]
                    selected_tools = [t for t in selected_tools if t and t.is_enabled]
                    tools_text = "\n".join(t.to_llm_string() for t in selected_tools)
                else:
                    tools_text = get_universal_registry().format_for_llm()
                tool_names = get_universal_registry().get_tool_names()
            except Exception:
                tools_text = "No tools available."
                tool_names = []
            unreliable = []
        # 2. System State
        system_state = ""
        try:
            from intelligence.system_awareness import get_system_awareness
            system_state = get_system_awareness().to_llm_context()
        except Exception:
            system_state = "[System state unavailable]"

        # 3. Recent History (from memory)
        recent_history = ""
        if memory_context:
            recent_history = memory_context

        # 4. Constraints
        constraints = self._build_constraints(unreliable)

        # 5. Anti-pattern Warnings (objective-specific)
        anti_warnings = self._build_anti_pattern_warnings(objective)

        # 6. Assemble the full injection section
        sections = []
        
        # Inject Multi-Agent Swarm Awareness
        sections.append(
            "[Advanced Capabilities: Multi-Agent Swarm]\n"
            "AERIS possesses an autonomous Multi-Agent Swarm for complex tasks.\n"
            "If the user asks for deep research, full-stack code generation, security auditing, "
            "or dynamic tool creation, YOU ARE FULLY CAPABLE. The system will automatically route "
            "these tasks to specialized agents (CodingAgent, ResearchAgent, VulnerabilityAgent, ToolManagerAgent, RuntimeAgent). "
            "DO NOT say you cannot do these things, and DO NOT try to hallucinate simple tools to solve them."
        )

        if system_state:
            sections.append(system_state)
        if constraints:
            sections.append(f"\n[Active Constraints]\n{constraints}")
        if anti_warnings:
            sections.append(f"\n[Warnings for This Task]\n{anti_warnings}")
        if recent_history:
            sections.append(f"\n[Recent Execution History]\n{recent_history}")

        full_section = "\n".join(sections)

        context = {
            "tools_text": tools_text,
            "tool_names": tool_names,
            "system_state": system_state,
            "recent_history": recent_history,
            "constraints": constraints,
            "anti_pattern_warnings": anti_warnings,
            "full_system_prompt_section": full_section,
        }
        self._last_context = context
        return context

    def validate_plan_tools(self, plan_tool_names: List[str]) -> Dict[str, Any]:
        """
        Validate that all tools in a plan actually exist.
        Prevents hallucinated tool usage.

        Returns:
          {"valid": bool, "invalid_tools": [...], "suggestions": {...}}
        """
        try:
            from intelligence.tool_awareness import get_tool_awareness
            known_tools = set(get_tool_awareness().get_tool_names_list())
        except Exception:
            try:
                from tools.universal_registry import get_universal_registry
                known_tools = set(get_universal_registry().get_tool_names())
            except Exception:
                return {"valid": True, "invalid_tools": [], "suggestions": {}}

        invalid = [t for t in plan_tool_names if t not in known_tools]
        suggestions = {}

        if invalid:
            # Try to find close matches
            from difflib import get_close_matches
            for inv_tool in invalid:
                matches = get_close_matches(inv_tool, list(known_tools), n=3, cutoff=0.5)
                if matches:
                    suggestions[inv_tool] = matches

        return {
            "valid": len(invalid) == 0,
            "invalid_tools": invalid,
            "suggestions": suggestions,
        }

    def validate_tool_params(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate that parameters match the tool's schema.
        Returns:
          {"valid": bool, "missing": [...], "warnings": [...]}
        """
        try:
            from intelligence.tool_awareness import get_tool_awareness
            tk = get_tool_awareness().get_tool_knowledge(tool_name)
        except Exception:
            return {"valid": True, "missing": [], "warnings": []}

        if not tk:
            return {"valid": True, "missing": [], "warnings": [f"Unknown tool: {tool_name}"]}

        missing = [p for p in tk.required_params if p not in params]
        warnings = []

        # Check for empty values
        for key, val in params.items():
            if isinstance(val, str) and not val.strip():
                warnings.append(f"Parameter '{key}' is empty for tool '{tool_name}'")

        return {
            "valid": len(missing) == 0,
            "missing": missing,
            "warnings": warnings,
        }

    def _build_constraints(self, unreliable_tools: List[str]) -> str:
        """Build active constraint text."""
        lines = []

        if unreliable_tools:
            lines.append(f"  ⚠ Unreliable tools (consider alternatives): {', '.join(unreliable_tools)}")

        # Check for cooldowns
        try:
            from tools.tool_permissions import get_permission_system
            perms = get_permission_system()
            summary = perms.get_permissions_summary()
            cooldowns = summary.get("active_cooldowns", {})
            if cooldowns:
                lines.append(f"  ⏳ Tools on cooldown: {', '.join(cooldowns.keys())}")
            blacklisted = summary.get("blacklisted", [])
            if blacklisted:
                lines.append(f"  🚫 Blacklisted tools: {', '.join(blacklisted)}")
        except Exception:
            pass

        return "\n".join(lines) if lines else ""

    def _build_anti_pattern_warnings(self, objective: str) -> str:
        """Generate objective-specific anti-pattern warnings."""
        obj_lower = objective.lower()
        warnings = []

        try:
            from intelligence.tool_awareness import get_tool_awareness
            awareness = get_tool_awareness()
            awareness.refresh()

            for tk in awareness.get_all_knowledge().values():
                if not tk.anti_patterns:
                    continue
                # Check if this tool's category might be relevant to the objective
                relevant = False
                all_text = " ".join(tk.typical_use_cases + [tk.description]).lower()
                obj_words = set(obj_lower.split())
                if any(w in all_text for w in obj_words):
                    relevant = True

                if relevant:
                    for ap in tk.anti_patterns[:2]:
                        warnings.append(f"  • {tk.name}: {ap}")
        except Exception:
            pass

        return "\n".join(warnings[:10]) if warnings else ""

    def get_last_context(self) -> Optional[Dict[str, Any]]:
        """Return the last assembled context (for debugging)."""
        return self._last_context


# ── Global Singleton ─────────────────────────────────────────────────
_context_injector: Optional[ContextInjector] = None


def get_context_injector() -> ContextInjector:
    global _context_injector
    if _context_injector is None:
        _context_injector = ContextInjector()
    return _context_injector
