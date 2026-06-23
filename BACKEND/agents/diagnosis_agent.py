"""
AERIS — Diagnosis Agent
=======================
Specialized core agent dedicated to diagnosing AERIS systems, environments,
package dependencies, and codebase quality.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.diagnostics")

PLAN_PROMPT = """You are AERIS's Diagnosis Agent.
Your job is to determine what tools to use to diagnose system health, check a specific agent, scan code for errors, or inspect websites/webpages.

Available tools:
- diagnose_system(): Checks environment configuration, hardware stats, package dependencies, and agent statuses.
- diagnose_agent(agent_name: str): Diagnose a specific agent by its name (e.g. 'SecurityAgent', 'ChatAgent', 'DorkingAgent'). Checks registration, version, capabilities, children, and runs a dry-run test.
- diagnose_code(path: str): Scans Python, JS, TS, HTML, and CSS files in a codebase recursively. Provide a specific subfolder path if requested, or leave empty/blank to scan the root workspace.
- suggest_code_fixes(path: str, errors: str): Generates automated repair solutions and cleaned code diffs for a file with specific error messages.
- inspect_webpage(url: str): Launches a headless Chromium browser using Selenium to inspect a webpage, capturing DOM details, console logs, network errors/warnings, and saving a screenshot.

User request: {message}

Rules:
- If the user wants to diagnose the entire system, check API keys, check memory/CPU, or general status -> use diagnose_system.
- If the user wants to diagnose or check a particular/specific agent (e.g. 'SecurityAgent', 'DorkingAgent', 'reaper', 'hunter', 'strategos') -> use diagnose_agent (with the agent name).
- If the user wants to scan, analyze, check, or diagnose their codebase/files for warnings, style, console.logs, or compile/syntax bugs -> use diagnose_code (optionally passing the file/folder path).
- If the user wants to fix or repair specific errors -> use suggest_code_fixes (passing path and errors).
- If the user wants to check, inspect, debug, or diagnose a website/URL for errors, console logs, or network failures -> use inspect_webpage (extracting and passing the URL).
- You can chain multiple tools if needed.

Respond with ONLY valid JSON:
{{
  "tools": [
    {{"name": "tool_name", "params": {{"param": "value"}}}}
  ],
  "explanation": "Brief explanation of what you are diagnosing and why"
}}
"""

REPORT_PROMPT = """You are AERIS's Master Diagnostician.
You have been given raw diagnostic results based on the user's request.
Your job is to format this information into a beautiful, easy-to-read, structured markdown report.
Provide a summary of the health of the system or code, clear red/green alerts, and high-level recommendations.

User request: {message}
Raw diagnostic output:
{results}
"""


class DiagnosisAgent(BaseAgent):
    """Deep diagnostics agent for systems, environment configurations, and codebases."""

    def __init__(self):
        super().__init__(
            name="DiagnosisAgent",
            description="Performs deep diagnostics on system resources, environment configuration, package dependencies, and codebase quality.",
            task_domain="diagnose",
            version="1.0.0",
            capabilities=[
                "AERIS Self-Diagnosis",
                "Code Syntax & Lint Diagnostics",
                "System Resource Diagnostics",
                "Dependency Verification",
                "Automated Code Repair Suggestions"
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
            plan = json.loads(raw)
            return plan
        except Exception as e:
            logger.warning(f"Diagnosis plan parsing failed: {e}")
            # Fallback
            lower = message.lower()
            if "agent" in lower or "chat" in lower or "security" in lower or "dork" in lower:
                # Try to extract a name
                words = lower.split()
                target_agent = "ChatAgent"
                for w in words:
                    if w in ("security", "chat", "dorking", "system", "research", "search", "code"):
                        target_agent = w.capitalize() + "Agent"
                        break
                return {"tools": [{"name": "diagnose_agent", "params": {"agent_name": target_agent}}], "explanation": "Agent diagnosis fallback"}
            elif "code" in lower or "file" in lower:
                return {"tools": [{"name": "diagnose_code", "params": {}}], "explanation": "Code scan fallback"}
            elif "http" in lower or "www." in lower or ".com" in lower or ".org" in lower or ".net" in lower or "website" in lower or "site" in lower:
                url = self._extract_url(message) or "https://google.com"
                return {"tools": [{"name": "inspect_webpage", "params": {"url": url}}], "explanation": "Website inspection fallback"}
            return {"tools": [{"name": "diagnose_system", "params": {}}], "explanation": "System check fallback"}

    async def execute(self, plan: Any) -> Any:
        results = []
        for step in plan.get("tools", []):
            name = step.get("name")
            params = step.get("params", {})
            try:
                self.logger.info(f"Diagnosis running tool: {name} with {params}")
                result = await tool_registry.execute_async(name, **params)
                results.append({"tool": name, "success": True, "output": result})
            except Exception as e:
                self.logger.warning(f"Error running {name}: {e}")
                results.append({"tool": name, "success": False, "error": str(e)})
        return results

    async def report(self, results: Any) -> str:
        # If we have a single successful tool execution that returns markdown, just return it directly!
        if len(results) == 1 and results[0]["success"] and isinstance(results[0]["output"], str) and results[0]["output"].startswith("#"):
            return results[0]["output"]

        # Otherwise format via LLM
        prompt = REPORT_PROMPT.format(message="", results=json.dumps(results, indent=2))
        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS's Master Diagnostician. Respond with clean markdown."},
                {"role": "user", "content": prompt}
            ], max_tokens=2048)
        except Exception as e:
            return f"## Diagnostics Completed\n\n```json\n{json.dumps(results, indent=2)}\n```"

    @staticmethod
    def _extract_url(text: str) -> str | None:
        import re
        match = re.search(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[a-z]{2,}|[a-zA-Z0-9.-]+\.[a-z]{2,}/?[^\s<>"\']*', text)
        if match:
            url = match.group(0)
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            return url
        return None
