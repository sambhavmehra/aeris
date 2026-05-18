"""
AERIS — Runtime Agent (Sub-Agent)
=========================================
Specialized agent that generates Python scripts at runtime, executes them
in a controlled environment, and captures the output. This is the agent
that can "write code and run it on the fly" within the multi-agent swarm.

It uses the existing ExecutorAgent and tool registry for actual execution
(via write_file + run_bash), ensuring all security checks and receipt
generation still apply.

Inherits from BaseAgent → gets APIGateway, logging, and memory for free.
Does NOT modify any existing agent or engine file.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer

logger = logging.getLogger("AerisRuntimeAgent")

RUNTIME_SYSTEM_PROMPT = """You are AERIS's Runtime Agent — you generate executable Python scripts.

RULES:
1. Output ONLY complete, self-contained Python scripts.
2. Include ALL imports at the top.
3. The script must be FULLY EXECUTABLE with `python script.py`.
4. Include proper error handling (try/except).
5. Print all results to stdout so the output can be captured.
6. Do NOT use interactive input() — all parameters must be hardcoded.
7. Do NOT import dangerous modules (os.system with user input, subprocess with shell=True on untrusted input).
8. If the task involves file I/O, use the current working directory.
9. Output ONLY the Python code — no markdown fences, no explanation.
"""


class RuntimeAgent(BaseAgent):
    """
    Specialised sub-agent that generates scripts and executes them at runtime.

    Workflow:
      1. Takes an objective (e.g., "calculate fibonacci and save to JSON")
      2. Generates a complete Python script via LLM
      3. Saves it to a temporary file in the workspace
      4. Executes it via the existing tool infrastructure (write_file + run_bash)
      5. Captures and returns the output

    NOTE: Execution goes through the existing ToolExecutorService,
    which applies SecurityAgent checks and generates execution receipts.
    """

    def __init__(self, memory_agent=None):
        super().__init__(name="RuntimeAgent", memory_agent=memory_agent)
        self._workspace = self._get_workspace()

    def process(self, objective: str, context: SharedContextBuffer = None,
                **kwargs) -> Dict[str, Any]:
        """
        Generate and execute a script for the given objective.

        Args:
            objective: What the script should accomplish.
            context: SharedContextBuffer for multi-agent collaboration.

        Returns:
            {"status": "success"|"error", "result": ..., "script": ..., "output": ...}
        """
        self.log(f"Runtime task: {objective[:80]}")

        try:
            # Step 1: Generate the script
            script = self._generate_script(objective, context)

            # Step 2: Save to workspace
            script_name = f"aeris_runtime_{uuid.uuid4().hex[:8]}.py"
            script_path = self._workspace / script_name
            script_path.write_text(script, encoding="utf-8")
            self.log(f"Saved runtime script: {script_path}")

            # Step 3: Execute via the existing tool infrastructure
            output = self._execute_script(str(script_path))

            # Step 4: Clean up the temporary script
            try:
                script_path.unlink()
            except Exception:
                pass  # Non-critical

            result = {
                "script": script,
                "output": output,
                "script_name": script_name,
            }

            if context:
                context.post(self.name, result, message_type="result", task="runtime")

            self.log("Runtime execution completed.")
            return {"status": "success", "result": result}

        except Exception as e:
            error_msg = f"Runtime agent failed: {e}"
            self.log(error_msg, "ERROR")
            if context:
                context.post(self.name, error_msg, message_type="error")
            return {"status": "error", "error": error_msg}

    def generate_and_run(self, task_description: str,
                         context: SharedContextBuffer = None) -> Dict[str, Any]:
        """Convenience alias for process()."""
        return self.process(task_description, context)

    def run_existing_script(self, script_content: str,
                            context: SharedContextBuffer = None) -> Dict[str, Any]:
        """Execute a pre-existing script (e.g., from CodingAgent output)."""
        self.log("Executing pre-existing script.")

        try:
            script_name = f"aeris_runtime_{uuid.uuid4().hex[:8]}.py"
            script_path = self._workspace / script_name
            script_path.write_text(script_content, encoding="utf-8")

            output = self._execute_script(str(script_path))

            try:
                script_path.unlink()
            except Exception:
                pass

            result = {"script": script_content, "output": output}

            if context:
                context.post(self.name, result, message_type="result", task="runtime")

            return {"status": "success", "result": result}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Internal Helpers ─────────────────────────────────────────────

    def _generate_script(self, objective: str,
                         context: Optional[SharedContextBuffer]) -> str:
        """Generate a Python script via LLM."""
        parts = [f"Generate a Python script that: {objective}"]

        if context:
            # Inject any relevant context from other agents
            research = context.get_latest_result(sender="ResearchAgent")
            if research:
                parts.append(f"\nRelevant research data:\n{str(research)[:1000]}")

            coding = context.get_latest_result(sender="CodingAgent")
            if coding:
                parts.append(f"\nCode/architecture guidance:\n{str(coding)[:1000]}")

            analysis = context.get_latest_result(sender="AnalysisAgent")
            if analysis:
                parts.append(f"\nAnalysis context:\n{str(analysis)[:500]}")

        prompt = "\n".join(parts)

        raw = self._llm_call(
            RUNTIME_SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            max_tokens=2048,
        )

        # Clean response
        code = raw.strip()
        if code.startswith("```"):
            code = code.split("\n", 1)[-1]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()

        return code

    def _execute_script(self, script_path: str) -> str:
        """Execute a script using the existing tool executor service."""
        from tools.tool_executor import get_executor_service

        executor = get_executor_service()
        result = executor.execute(
            tool_name="run_bash",
            task_id=f"runtime_{uuid.uuid4().hex[:8]}",
            step_id="runtime_exec",
            parent_task_id="runtime",
            command=f'python "{script_path}"',
        )

        if result.success:
            return result.stdout
        else:
            raise RuntimeError(f"Script execution failed: {result.stderr}")

    def _get_workspace(self) -> Path:
        """Get the workspace directory for temporary scripts."""
        base = Path(__file__).resolve().parent.parent.parent.parent
        workspace = base / "workspace"
        workspace.mkdir(exist_ok=True)
        return workspace
