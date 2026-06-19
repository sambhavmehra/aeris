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
1. The file must define a function named `run(**kwargs)` as the main entry point, with a clear docstring.
2. The function must accept keyword arguments (`**kwargs`).
3. The function must return a string result.
4. Include all necessary imports at the top.
5. Include a TOOL_METADATA dict at module level:
   TOOL_METADATA = {
       "name": "tool_name",
       "description": "What the tool does",
       "required_params": ["param1", "param2"],
       "risk_level": "safe",    # safe|low|medium|high
       "category": "general",   # general|system|web|file|utility
   }
6. Do NOT use markdown code fences in your output. Just return the raw Python code.
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

    def create_tool(self, request: str, tool_name: Optional[str] = None,
                    context: SharedContextBuffer = None) -> Dict[str, Any]:
        """
        Generate a new tool as a Python script, validate it in a sandbox,
        auto-repair if validation fails, and hot-reload it into the UniversalToolRegistry.
        """
        self.log(f"Generating new tool for: {request[:60]}")

        # Build prompt with context from other agents
        enriched = request
        if context:
            research = context.get_latest_result(sender="ResearchAgent")
            if research:
                enriched += f"\n\nResearch context:\n{str(research)[:500]}"

        # Infer tool name if not provided
        if not tool_name:
            import re
            # Extract tool name from metadata parser or infer from prompt
            tool_name = f"dynamic_tool_{abs(hash(request)) % 10000}"

        # Loop for generation, sandbox validation, and auto-repair
        max_attempts = 3
        current_attempt = 1
        last_error = ""
        code = ""
        success = False

        while current_attempt <= max_attempts:
            self.log(f"Tool generation attempt {current_attempt}/{max_attempts} for '{tool_name}'")
            if current_attempt == 1:
                prompt_input = f"Create a tool named '{tool_name}' for: {enriched}"
            else:
                prompt_input = (
                    f"Create a tool named '{tool_name}' for: {enriched}\n\n"
                    f"Your previous attempt failed validation with the following error:\n{last_error}\n\n"
                    f"Please correct the implementation (fix syntax, missing imports, or incorrect arguments) and output the complete corrected python code. No explanation."
                )

            raw_code = self._llm_call(
                TOOL_GEN_SYSTEM_PROMPT,
                prompt_input,
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

            # Ensure tool_name matches TOOL_METADATA if generated has one
            extracted_name = self._extract_tool_name(code)
            if extracted_name and extracted_name != tool_name:
                code = code.replace(extracted_name, tool_name)

            # 1. Write to temporary file for sandbox validation
            temp_filename = f"temp_validate_{tool_name}.py"
            temp_filepath = self._tools_dir / temp_filename
            try:
                temp_filepath.write_text(code, encoding="utf-8")

                # 2. Run validation (sandbox run in subprocess)
                import subprocess
                import sys

                # Syntax compile check
                compile(code, temp_filename, "exec")

                # Test importing and loading metadata
                val_script = (
                    f"import sys\n"
                    f"sys.path.insert(0, r'{self._tools_dir}')\n"
                    f"try:\n"
                    f"    import temp_validate_{tool_name} as mod\n"
                    f"    assert hasattr(mod, 'run') or hasattr(mod, '{tool_name}'), 'No run() or main function found'\n"
                    f"    print('SUCCESS')\n"
                    f"except Exception as e:\n"
                    f"    print(f'ERROR: {{e}}')\n"
                    f"    sys.exit(1)\n"
                )
                result = subprocess.run(
                    [sys.executable, "-c", val_script],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.returncode == 0 and "SUCCESS" in result.stdout:
                    success = True
                    self.log(f"Sandbox validation passed for '{tool_name}'")
                else:
                    err_msg = result.stderr or result.stdout or "Import check failed"
                    raise RuntimeError(err_msg)

            except Exception as val_ex:
                last_error = str(val_ex)
                self.log(f"Validation failed on attempt {current_attempt}: {last_error}", "WARNING")
            finally:
                if temp_filepath.exists():
                    try:
                        import os
                        os.remove(temp_filepath)
                    except Exception:
                        pass

            if success:
                break

            current_attempt += 1

        if not success:
            raise RuntimeError(f"Failed to generate a valid tool for '{tool_name}' after {max_attempts} attempts. Last error: {last_error}")

        # Save permanent file
        file_path = self._tools_dir / f"{tool_name}.py"
        file_path.write_text(code, encoding="utf-8")
        self.log(f"Successfully saved validated tool to: {file_path}")

        # Hot-reload
        count = self.reload_tools()

        return {
            "tool_name": tool_name,
            "file_path": str(file_path),
            "code_preview": code[:500],
            "reloaded_count": count,
            "success": True
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
