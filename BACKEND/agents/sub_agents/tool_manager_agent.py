"""
AERIS — Tool Manager Agent (Sub-Agent)
===============================================
Specialized agent that can discover, generate, install, and manage
tools at runtime. Sits on top of the existing UniversalToolRegistry
and DynamicToolLoader — uses them as its execution backend.

Inherits from BaseAgent → gets APIGateway, logging, and memory for free.
Does NOT modify any existing agent or engine file.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer

logger = logging.getLogger("AerisToolManagerAgent")

TOOL_GEN_SYSTEM_PROMPT = """You are AERIS's Tool Manager — you generate new Python tools at runtime.

When asked to create a tool, output a COMPLETE Python file that follows this contract:
1. The file must define a function with a clear docstring.
2. The function must accept keyword arguments.
3. The function must return a string result.
4. Include all necessary imports at the top.
5. Include a TOOL_METADATA dict at module level:
   TOOL_METADATA = {{
       "name": "tool_name",
       "description": "What the tool does",
       "required_params": ["param1", "param2"],
       "risk_level": "safe",    # safe|low|medium|high
       "category": "general",   # general|system|web|file|utility
   }}
6. The main function name must match the tool name.

Output ONLY the Python code — no explanation, no markdown fences.
"""


class ToolManagerAgent(BaseAgent):
    """
    Specialised sub-agent for dynamic tool management.

    This agent:
      - Lists and inspects available tools in the UniversalToolRegistry
      - Generates new tools at runtime (Python scripts saved to dynamic tools dir)
      - Triggers hot-reload of the tool registry
      - Can fetch and install external tools
    """

    def __init__(self, memory_agent=None):
        super().__init__(name="ToolManagerAgent", memory_agent=memory_agent)
        self._tools_dir = self._get_tools_dir()

    def process(self, objective: str, context: SharedContextBuffer = None,
                **kwargs) -> Dict[str, Any]:
        """
        Handle a tool management request.

        Supported actions (inferred from objective):
          - "list tools" → list all registered tools
          - "create tool ..." → generate a new tool
          - "find tool for ..." → search for a matching tool
          - "reload tools" → hot-reload dynamic tools
        """
        self.log(f"Tool management: {objective[:80]}")
        obj_lower = objective.lower()

        try:
            if any(kw in obj_lower for kw in ["list", "show all", "available"]):
                result = self.list_tools()
            elif any(kw in obj_lower for kw in ["create", "generate", "make", "build", "forge"]):
                result = self.create_tool(objective, context)
            elif any(kw in obj_lower for kw in ["find", "search", "lookup", "which tool"]):
                result = self.find_tool(objective)
            elif any(kw in obj_lower for kw in ["reload", "refresh", "rescan"]):
                result = self.reload_tools()
            else:
                result = self.find_tool(objective)

            if context:
                context.post(self.name, result, message_type="result", task="tool_management")

            return {"status": "success", "result": result}

        except Exception as e:
            error_msg = f"Tool manager failed: {e}"
            self.log(error_msg, "ERROR")
            if context:
                context.post(self.name, error_msg, message_type="error")
            return {"status": "error", "error": error_msg}

    def list_tools(self) -> Dict[str, Any]:
        """List all registered tools with their metadata."""
        from tools.universal_registry import get_universal_registry
        registry = get_universal_registry()
        tools = registry.get_enabled_tools()
        return {
            "total": len(tools),
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "risk_level": t.risk_level.value,
                    "source": t.source.value,
                    "params": t.required_params,
                }
                for t in tools
            ],
        }

    def find_tool(self, description: str) -> Dict[str, Any]:
        """Find the best matching tool for a description using LLM."""
        from tools.universal_registry import get_universal_registry
        registry = get_universal_registry()
        tools_text = registry.format_for_llm()

        prompt = (
            f"Given these available tools:\n{tools_text}\n\n"
            f"Which tool(s) best match this need: '{description}'?\n\n"
            f"Return JSON: {{\"matches\": [{{\"name\": \"tool_name\", \"confidence\": 0.9, \"reason\": \"...\"}}]}}"
        )

        raw = self._llm_call(
            "You are a tool matcher. Return ONLY JSON.",
            prompt, temperature=0.1, max_tokens=256,
        )

        try:
            return json.loads(raw.strip())
        except json.JSONDecodeError:
            return {"matches": [], "note": raw.strip()}

    def create_tool(self, request: str,
                    context: SharedContextBuffer = None) -> Dict[str, Any]:
        """
        Generate a new tool as a Python script and register it.
        The script is saved to the dynamic tools directory and
        hot-reloaded into the UniversalToolRegistry.
        """
        self.log(f"Generating new tool for: {request[:60]}")

        # Build prompt with context from other agents
        enriched = request
        if context:
            research = context.get_latest_result(sender="ResearchAgent")
            if research:
                enriched += f"\n\nResearch context:\n{str(research)[:500]}"

        raw_code = self._llm_call(
            TOOL_GEN_SYSTEM_PROMPT,
            f"Create a tool for: {enriched}",
            temperature=0.2,
            max_tokens=2048,
        )

        # Clean the response
        code = raw_code.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()

        # Extract tool name from TOOL_METADATA
        tool_name = self._extract_tool_name(code)
        if not tool_name:
            tool_name = f"custom_tool_{hash(request) % 10000}"

        # Save to dynamic tools directory
        file_path = self._tools_dir / f"{tool_name}.py"
        file_path.write_text(code, encoding="utf-8")
        self.log(f"Saved new tool to: {file_path}")

        # Hot-reload
        count = self.reload_tools()

        return {
            "tool_name": tool_name,
            "file_path": str(file_path),
            "code_preview": code[:500],
            "reloaded_count": count,
        }

    def reload_tools(self) -> int:
        """Trigger a hot-reload of all dynamic tools."""
        from tools.universal_registry import get_universal_registry
        registry = get_universal_registry()
        count = registry.reload_dynamic_tools()
        self.log(f"Reloaded {count} dynamic tools.")
        return count

    # ── Internal Helpers ─────────────────────────────────────────────

    def _get_tools_dir(self) -> Path:
        """Get the dynamic tools directory."""
        base = Path(__file__).resolve().parent.parent.parent.parent
        tools_dir = base / "aeris_tools"
        tools_dir.mkdir(exist_ok=True)
        return tools_dir

    @staticmethod
    def _extract_tool_name(code: str) -> Optional[str]:
        """Extract tool name from TOOL_METADATA in generated code."""
        try:
            for line in code.splitlines():
                if '"name"' in line or "'name'" in line:
                    # Extract the value
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        name = parts[1].strip().strip("'\",")
                        if name and name.isidentifier():
                            return name
        except Exception:
            pass
        return None
