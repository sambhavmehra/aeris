"""
AERIS — Universal Tool Registry
═══════════════════════════════════════════════════════════════════════
The central hub for managing all tools in the system.
It aggregates:
  1. Builtin tools (migrated from the old ToolRegistry)
  2. Dynamically loaded tools (via DynamicToolLoader)
  3. External tools (via MCP / API manifests)

It acts as the single source of truth for tool lookup, metadata
generation (for LLMs), and tool lifecycle management.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from tools.tool_interface import (
    ParamSchema,
    RiskLevel,
    ToolInputSchema,
    ToolSource,
    ToolStatus,
    UniversalToolDef,
)
from tools.tool_loader import get_dynamic_loader

logger = logging.getLogger("AerisUniversalRegistry")


class UniversalToolRegistry:
    """
    Centralised registry that unifies built-in Python tools with dynamically
    loaded scripts, APIs, and CLI commands.
    """

    def __init__(self):
        self._tools: Dict[str, UniversalToolDef] = {}
        self._dynamic_loader = get_dynamic_loader()

    # ── Tool Registration ─────────────────────────────────────────────

    def register_builtin(
        self,
        name: str,
        description: str,
        func: Callable,
        required_params: List[str] = None,
        risk_level: RiskLevel = RiskLevel.SAFE,
        category: str = "general",
    ) -> UniversalToolDef:
        """Register a hardcoded Python function as a tool (backwards-compatible)."""
        required_params = required_params or []
        params = [ParamSchema(name=p, required=True) for p in required_params]

        tool = UniversalToolDef(
            name=name,
            description=description,
            func=func,
            input_schema=ToolInputSchema(params=params),
            risk_level=risk_level,
            category=category,
            source=ToolSource.BUILTIN,
            status=ToolStatus.ENABLED,
        )
        self._tools[name] = tool
        return tool

    def register_tool(self, tool: UniversalToolDef):
        """Directly register a UniversalToolDef."""
        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> bool:
        """Remove a tool from the registry."""
        if name in self._tools:
            del self._tools[name]
            # Also tell the dynamic loader in case it was loaded there
            self._dynamic_loader.unload_tool(name)
            return True
        return False

    # ── Dynamic Loading Integration ───────────────────────────────────

    def reload_dynamic_tools(self) -> int:
        """Scan directories and manifests for new/updated tools."""
        new_tools = self._dynamic_loader.scan_tools_dir()
        for tool in new_tools:
            self._tools[tool.name] = tool
            
        # Also sync any already loaded dynamic tools that might have been updated
        for tool in self._dynamic_loader.get_loaded_tools():
            self._tools[tool.name] = tool
            
        return len(new_tools)

    def load_from_file(self, file_path: str) -> Optional[UniversalToolDef]:
        """Dynamically load a tool from a specific file path."""
        tool = self._dynamic_loader.load_tool_from_file(file_path)
        if tool:
            self._tools[tool.name] = tool
        return tool

    # ── Queries & Lookups ─────────────────────────────────────────────

    def get_tool(self, name: str) -> Optional[UniversalToolDef]:
        return self._tools.get(name)

    def get_all_tools(self) -> List[UniversalToolDef]:
        return list(self._tools.values())

    def get_enabled_tools(self) -> List[UniversalToolDef]:
        return [t for t in self._tools.values() if t.is_enabled]

    def get_tools_by_category(self, category: str) -> List[UniversalToolDef]:
        return [t for t in self._tools.values() if t.category == category]

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    # ── LLM Integration ───────────────────────────────────────────────

    def get_all_metadata(self) -> List[Dict[str, Any]]:
        """Return metadata for all enabled tools (used by LLM planner)."""
        return [t.to_metadata() for t in self.get_enabled_tools()]

    def format_for_llm(self) -> str:
        """Format enabled tools as a compact text description for system prompts."""
        lines = []
        for t in self.get_enabled_tools():
            lines.append(t.to_llm_string())
        return "\n".join(lines)

    # ── Execution ─────────────────────────────────────────────────────

    async def execute_async(self, name: str, **kwargs) -> Any:
        """Execute a tool dynamically, handling both sync and async functions."""
        import inspect
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in Universal Registry.")
        
        if not tool.is_enabled:
            raise ValueError(f"Tool '{name}' is currently disabled or in error state.")

        if tool.func:
            result = tool.func(**kwargs)
            if inspect.isawaitable(result):
                return await result
            return result
        else:
            # Future extension point for ToolAdapters (API/MCP)
            raise NotImplementedError(f"Execution of {tool.source.value} tool '{name}' without a local function is not yet fully implemented via execute_async.")



# ── Global Singleton ─────────────────────────────────────────────────
_universal_registry: Optional[UniversalToolRegistry] = None


def get_universal_registry() -> UniversalToolRegistry:
    global _universal_registry
    if _universal_registry is None:
        _universal_registry = UniversalToolRegistry()
        # Auto-load dynamic tools on startup
        _universal_registry.reload_dynamic_tools()
        
        # Migrate old builtin tools
        try:
            from tools.tool_registry import global_tool_registry
            for tool_name, tool_def in global_tool_registry._tools.items():
                _universal_registry.register_builtin(
                    name=tool_def.name,
                    description=tool_def.description,
                    func=tool_def.func,
                    required_params=tool_def.required_params,
                    risk_level=tool_def.risk_level,
                    category=tool_def.category
                )
            logger.info(f"Migrated {len(global_tool_registry._tools)} builtin tools to Universal Registry.")
        except Exception as e:
            logger.warning(f"Failed to migrate builtin tools: {e}")
            
    return _universal_registry
