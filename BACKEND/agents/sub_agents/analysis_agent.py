"""
AERIS — Analysis Agent (Sub-Agent)
==========================================
Specialized agent for data analysis, log parsing, file inspection,
and system diagnostics.

Inherits from BaseAgent → gets APIGateway, logging, and memory for free.
Does NOT modify any existing agent or engine file.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer

logger = logging.getLogger("AerisAnalysisAgent")

ANALYSIS_SYSTEM_PROMPT = """You are AERIS's Analysis Agent — a specialised AI analyst.

CAPABILITIES:
- Analyse structured and unstructured data (logs, JSON, CSV, code output)
- Identify patterns, anomalies, and key insights
- Generate statistical summaries and trend analysis
- Parse error logs and system diagnostics
- Produce actionable recommendations based on data

RULES:
1. Be PRECISE — use exact numbers and data points from the input.
2. Structure your output as JSON:
   {{
     "summary": "Concise analysis summary",
     "findings": [
       {{"category": "...", "detail": "...", "severity": "info|warning|critical"}}
     ],
     "patterns": ["pattern1", "pattern2"],
     "recommendations": ["action1", "action2"],
     "metrics": {{"key": "value"}}
   }}
3. If data is insufficient for analysis, clearly state what's missing.
4. Distinguish between facts (from data) and inferences (your analysis).
5. Prioritise findings by severity/impact.
"""


class AnalysisAgent(BaseAgent):
    """
    Specialised sub-agent for data analysis, log parsing, and diagnostics.
    Receives data from other agents (or directly) and produces structured insights.
    """

    def __init__(self, memory_agent=None):
        super().__init__(name="AnalysisAgent", memory_agent=memory_agent)

    def process(self, objective: str, context: SharedContextBuffer = None,
                data: str = "", **kwargs) -> Dict[str, Any]:
        """
        Analyse data or a topic based on the objective.

        Args:
            objective: What to analyse and why.
            context: SharedContextBuffer for multi-agent collaboration.
            data: Raw data to analyse (logs, code output, etc.)

        Returns:
            {"status": "success"|"error", "result": {...analysis...}}
        """
        self.log(f"Analysing: {objective[:80]}")

        enriched = self._build_enriched_prompt(objective, data, context)

        try:
            raw = self._llm_call(
                ANALYSIS_SYSTEM_PROMPT,
                enriched,
                temperature=0.1,
                max_tokens=1536,
            )

            result = self._parse_json(raw)

            if context:
                context.post(
                    sender=self.name,
                    content=result,
                    message_type="result",
                    task="analysis",
                )

            self.log("Analysis completed successfully.")
            return {"status": "success", "result": result}

        except Exception as e:
            error_msg = f"Analysis agent failed: {e}"
            self.log(error_msg, "ERROR")
            if context:
                context.post(self.name, error_msg, message_type="error")
            return {"status": "error", "error": error_msg}

    def analyze_logs(self, log_content: str,
                     context: SharedContextBuffer = None) -> Dict[str, Any]:
        """Parse and analyse log content for errors and patterns."""
        return self.process(
            "Analyse these logs for errors, warnings, patterns, and anomalies.",
            context=context,
            data=log_content,
        )

    def analyze_code_output(self, output: str, expected: str = "",
                            context: SharedContextBuffer = None) -> Dict[str, Any]:
        """Analyse code execution output against expected results."""
        objective = "Analyse this code execution output."
        if expected:
            objective += f" Expected output: {expected}"
        return self.process(objective, context=context, data=output)

    def analyze_system_state(self, system_info: str,
                             context: SharedContextBuffer = None) -> Dict[str, Any]:
        """Analyse system state information for issues and recommendations."""
        return self.process(
            "Analyse this system state for performance issues, resource problems, and recommendations.",
            context=context,
            data=system_info,
        )

    # ── Internal Helpers ─────────────────────────────────────────────

    def _build_enriched_prompt(self, objective: str, data: str,
                               context: Optional[SharedContextBuffer]) -> str:
        parts = [f"ANALYSIS OBJECTIVE: {objective}"]

        if data:
            parts.append(f"\nDATA TO ANALYSE:\n{data[:3000]}")

        if context:
            research = context.get_latest_result(sender="ResearchAgent")
            if research:
                parts.append(f"\nRESEARCH CONTEXT:\n{str(research)[:1000]}")

            coding = context.get_latest_result(sender="CodingAgent")
            if coding:
                parts.append(f"\nCODE CONTEXT:\n{str(coding)[:1000]}")

        return "\n".join(parts)

    @staticmethod
    def _parse_json(raw: str) -> Any:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned
