"""
AERIS — Mechanic Agent (Self-Repair & Env Manager)
==================================================
Specialized management agent dedicated to resolving environment setup errors,
installing missing pip dependencies, repairing codebase syntax errors,
and verifying tool packages.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.mechanic")

PLAN_PROMPT = """You are AERIS's Mechanic Agent (Self-Repair & Env Manager).
Your job is to parse tracebacks, identify missing modules, fix broken dependency conflicts, and automatically execute commands to repair them.

Available actions:
- install_missing_package(package_name: str): Run automated pip installer to download and register a missing package.
- repair_codebase_syntax(path: str, errors: str): Invoke the auto-repair engine to fix formatting/compilation bugs in a script.
- verify_dependencies: Perform checking of python library imports to ensure all registered tools are executable.

User request/error trace: {message}

Rules:
- If an ImportError or ModuleNotFoundError is found -> use install_missing_package (extract the correct package name).
- If there are syntax or linting errors in a file -> use repair_codebase_syntax.
- If general dependency audit is requested -> use verify_dependencies.

Respond with ONLY valid JSON:
{{
  "actions": [
    {{"name": "action_name", "params": {{"param": "value"}}}}
  ],
  "explanation": "Brief explanation of repair actions"
}}
"""

REPORT_PROMPT = """You are AERIS's System Mechanic.
You have processed tracebacks or environment logs and executed repair operations.
Describe what was broken, what actions were run (e.g. package installations, code edits), and the final state of the environment.

User query/concern: {message}
Raw execution metrics:
{results}
"""

class MechanicAgent(BaseAgent):
    """Self-repair and environment management agent."""

    def __init__(self):
        super().__init__(
            name="MechanicAgent",
            description="Fixes environment tracebacks, runs auto-pip installations, checks tool packages, and patches syntax bugs.",
            task_domain="mechanic",
            version="1.0.0",
            capabilities=[
                "Automated Package Installation",
                "Dependency Conflict Patching",
                "Syntax Error Correction",
                "Tool Environment Hardening"
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        prompt = PLAN_PROMPT.format(message=message)
        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Mechanic plan parsing failed: {e}. Falling back to dependency verification.")
            return {"actions": [{"name": "verify_dependencies", "params": {}}], "explanation": "Fallback verify"}

    async def execute(self, plan: Any) -> Any:
        results = []
        for step in plan.get("actions", []):
            name = step.get("name")
            params = step.get("params", {})
            try:
                self.log(f"Mechanic running repair action: {name}")
                if name == "install_missing_package":
                    pkg = params.get("package_name", "")
                    if not pkg:
                        raise ValueError("Missing package_name parameter")
                    
                    # Run pip install safely
                    self.log(f"Installing missing package via pip: {pkg}")
                    cmd = f"pip install {pkg}"
                    # Use run_bash or subprocess
                    res = subprocess.run(
                        [subprocess.sys.executable, "-m", "pip", "install", pkg],
                        capture_output=True, text=True, timeout=60
                    )
                    success = res.returncode == 0
                    results.append({
                        "action": name,
                        "success": success,
                        "package": pkg,
                        "stdout": res.stdout,
                        "stderr": res.stderr
                    })
                elif name == "repair_codebase_syntax":
                    path = params.get("path", "")
                    errors = params.get("errors", "")
                    # Delegate to suggest_code_fixes
                    fix_data = await tool_registry.execute_async("suggest_code_fixes", path=path, errors=errors)
                    # Expose file write if we want to apply it or just output the suggestions
                    results.append({
                        "action": name,
                        "success": True,
                        "target_file": path,
                        "suggestion": fix_data
                    })
                elif name == "verify_dependencies":
                    deps = ["fastapi", "pydantic", "httpx", "psutil", "dotenv", "numpy", "pandas", "spacy", "nltk", "cv2", "sklearn"]
                    status = {}
                    for dep in deps:
                        try:
                            __import__(dep)
                            status[dep] = "installed"
                        except ImportError:
                            status[dep] = "missing"
                    results.append({
                        "action": name,
                        "success": True,
                        "dependencies": status
                    })
            except Exception as e:
                self.log(f"Error running action {name}: {e}", "ERROR")
                results.append({"action": name, "success": False, "error": str(e)})
        return results

    async def report(self, results: Any) -> str:
        prompt = REPORT_PROMPT.format(message="", results=json.dumps(results, indent=2))
        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS's System Mechanic. Respond in clean, technically detailed markdown showing system repair logs."},
                {"role": "user", "content": prompt}
            ], max_tokens=1500)
        except Exception as e:
            return f"## Mechanic Repair Status Report\n\n```json\n{json.dumps(results, indent=2)}\n```"
