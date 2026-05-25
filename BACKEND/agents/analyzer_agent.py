"""
AERIS Analyzer Agent
====================
Specialized core agent dedicated entirely to deep analysis of files, data, logs, and system states.
It can search for files, read them, and run extensive analytical prompts to find insights, bugs, or summaries.

This agent is registered in the Universal Agent Registry and can be used by the Brain directly
or delegated to by other agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.analyzer")

PLAN_PROMPT = """You are AERIS's Analyzer Agent. Your ONLY job is to figure out HOW to gather the data needed for analysis based on the user's request.

Available tools you can use to gather data:
- find_system_file(filename: str) -> Searches the entire system for a file matching the name. Returns newline-separated absolute paths.
- read_system_file(path: str) -> Reads the content of ANY file on the system by its absolute path (works for PDFs, DOCX, TXT, etc.)
- run_bash(command: str) -> Runs a shell command (useful for getting system info, logs, or command output).

=== CONVERSATION HISTORY ===
{history}
========================

User request: {message}

If the user wants you to analyze a specific file (e.g., "analyze my resume.pdf"), you should first find it, then read it.
If the data is already in the message, you don't need tools.

IMPORTANT RULES:
- ALWAYS use read_system_file (NOT read_file) when reading a file found via find_system_file or absolute paths outside the workspace directory.
- Use "<USE_RESULT_FROM_PREVIOUS_STEP>" as the path placeholder so the found file path is substituted automatically.
- NEVER call read_system_file if find_system_file might return "No matching files found.".
- If the user refers to a file from the history (e.g., "pdf wali", "that docx file", "the pdf one"), resolve the absolute path from the conversation history and use it directly as the 'path' parameter for read_system_file.
- If no tools are needed, return an empty list for "tools".

Respond with ONLY valid JSON describing the steps to gather data:
{{
  "tools": [
    {{"name": "find_system_file", "params": {{"filename": "resume.pdf"}}}},
    {{"name": "read_system_file", "params": {{"path": "<USE_RESULT_FROM_PREVIOUS_STEP>"}}}}
  ],
  "target": "What exactly are we trying to analyze?"
}}
"""

ANALYSIS_PROMPT = """You are AERIS's Master Analyzer. 
You have been given raw data/files gathered from the system based on the user's request.
Your job is to deeply analyze this data and provide insights, summaries, error detection, or whatever the user specifically asked for.

Target Analysis Objective: {target}
User's Original Request: {message}

=== GATHERED DATA ===
{data}
=====================

RULES:
1. Be precise, analytical, and structured.
2. Use Markdown headers, bullet points, and code blocks for readability.
3. If analyzing logs/code, point out specific lines, errors, or security flaws.
4. If the data is empty or missing, clearly state that the file/data could not be found or read.
5. Provide actionable recommendations based on your analysis.
"""

class AnalyzerAgent(BaseAgent):
    """Deep analysis agent for files, logs, and structured data."""

    def __init__(self):
        super().__init__(
            name="AnalyzerAgent",
            description="Deep analysis of files, logs, code outputs, and system data.",
            task_domain="analyze",
            version="1.0.0",
            capabilities=[
                "File Content Analysis",
                "Log Parsing and Debugging",
                "Data Summarization",
                "System State Diagnostics"
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Determine what tools to use to fetch the data."""
        chat_history = context.get("chat_history", [])
        history_lines = []
        for msg in chat_history[-5:]:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")
            history_lines.append(f"[{role}]: {content}")
        history_summary = "\n".join(history_lines) if history_lines else "No prior conversation."

        prompt = PLAN_PROMPT.format(message=message, history=history_summary)
        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            plan = json.loads(raw)
            plan["message"] = message  # Pass original message through the pipeline
            return plan
        except Exception as e:
            logger.warning(f"Analyzer plan parsing failed: {e}")
            return {"tools": [], "target": message, "message": message}

    # Sentinel strings returned by find_system_file when nothing is found
    _NOT_FOUND_SENTINELS = ("no matching files found", "no results", "not found")

    def _resolve_placeholder(self, previous_result: str) -> str:
        """Extract the best single absolute file path from a find_system_file result."""
        stripped = previous_result.strip()
        # Check for known not-found sentinels
        if stripped.lower() in self._NOT_FOUND_SENTINELS or not stripped:
            return ""  # Signal that the file was not found
        # Try to parse as JSON (list of paths or dicts)
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list) and parsed:
                item = parsed[0]
                if isinstance(item, dict) and "path" in item:
                    return str(item["path"])
                return str(item)
        except (json.JSONDecodeError, ValueError):
            pass
        # Newline-separated paths — take the first valid-looking path
        lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
        for line in lines:
            # A valid path should start with a drive letter (Windows) or /
            if len(line) > 2 and (line[1:3] == ":\\") or line.startswith("/"):
                return line
            # Fallback: return first non-empty line
        return lines[0] if lines else stripped

    async def execute(self, plan: Any) -> Any:
        """Execute tools to gather the data to be analyzed."""
        gathered_data = ""
        previous_result = ""

        for step in plan.get("tools", []):
            name = step.get("name")
            params = step.get("params", {})

            # Handle placeholder replacement for chained tool calls
            skip_step = False
            for k, v in params.items():
                if v == "<USE_RESULT_FROM_PREVIOUS_STEP>":
                    resolved = self._resolve_placeholder(previous_result)
                    if not resolved:
                        # Previous step found nothing — skip this step gracefully
                        self.logger.warning(
                            f"Skipping tool '{name}' because previous step returned no usable result."
                        )
                        gathered_data += f"\n[Skipped {name}]: Previous step returned no file path.\n"
                        skip_step = True
                        break
                    params[k] = resolved

            if skip_step:
                previous_result = ""
                continue

            try:
                self.logger.info(f"Analyzer running tool: {name} with {params}")
                result = await tool_registry.execute_async(name, **params)
                previous_result = str(result)
                gathered_data += f"\n[Output of {name}]:\n{previous_result[:5000]}\n"  # limit to 5k chars per tool
            except Exception as e:
                err = f"Error running {name}: {e}"
                self.logger.warning(err)
                gathered_data += f"\n[Output of {name}]:\n{err}\n"
                previous_result = ""

        return {
            "target": plan.get("target", "General Analysis"),
            "data": gathered_data.strip() if gathered_data else "No external data gathered. Use user message for context.",
            "message": plan.get("message", "User analysis request") # Fallback
        }

    async def report(self, results: Any) -> str:
        """Analyze the gathered data and present it."""
        prompt = ANALYSIS_PROMPT.format(
            target=results.get("target"),
            data=results.get("data"),
            message=results.get("message", "Analyze the provided data.")
        )

        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS's elite Master Analyzer."},
                {"role": "user", "content": prompt},
            ], max_tokens=2048)
        except Exception as e:
            return f"## Analysis Failed\n\nCould not process the analysis due to an error: {e}\n\nGathered Data:\n```\n{results.get('data')[:1000]}\n```"
