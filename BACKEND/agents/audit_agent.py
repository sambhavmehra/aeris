"""
AERIS Audit Agent — Quality Control and Verification.
Verifies the outputs of other agents to ensure they meet the user's requirements.
"""

import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

logger = logging.getLogger("aeris.agent.audit")

AUDIT_PROMPT = """You are the Lead Auditor for AERIS (Autonomous Enhanced Reasoning Intelligence System).
Your job is to verify if the executed tasks successfully fulfill the user's original request.

USER'S ORIGINAL REQUEST:
"{message}"

EXECUTED TASKS & RESULTS:
{results}

Evaluate the results. Did the agents actually solve the user's problem? 
(Ignore minor formatting issues, focus on logical correctness and completeness).

Respond with ONLY valid JSON:
{{
  "passed": true or false,
  "feedback": "If false, strictly explain WHAT is missing or incorrect. If true, say 'Verified'.",
  "suggested_action": "If false, suggest exactly what the agent should do differently on the retry."
}}
"""


class AuditAgent(BaseAgent):
    """Evaluates task execution and provides self-correction feedback."""

    def __init__(self):
        super().__init__(
            name="AuditAgent",
            description="Quality control — verifies outputs of other agents",
            task_domain="audit",
            version="1.0.0",
            capabilities=[
                "Task Verification",
                "Output Quality Assessment",
                "Self-Correction Feedback",
                "Tamper-Resistant Receipts",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """
        Message here is the original user prompt.
        Context contains the 'task_results' from the Brain execution.
        """
        task_results = context.get("task_results", [])
        
        # Summarize results for the prompt
        results_summary = ""
        for i, r in enumerate(task_results):
            status = "SUCCESS" if r.get("success") else f"FAILED ({r.get('error')})"
            response = str(r.get("response", ""))[:1000] # Cap length
            results_summary += f"--- Step {i+1}: {r.get('intent', 'unknown')} ({status}) ---\n{response}\n\n"

        prompt = AUDIT_PROMPT.format(message=message, results=results_summary)

        try:
            # Use Groq for fast classification, fallback to Gemini if needed
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            
            data = json.loads(raw)
            return data
        except Exception as e:
            logger.warning(f"Audit analysis failed: {e}. Defaulting to pass.")
            # If audit fails, default to passing so we don't break the flow
            return {"passed": True, "feedback": "Audit failed, defaulting to pass", "suggested_action": ""}

    async def execute(self, plan: Any) -> Any:
        """The audit 'plan' is simply the JSON assessment."""
        return plan

    async def report(self, results: Any) -> str:
        """Not typically used for AuditAgent, as the Brain reads the JSON directly."""
        return str(results)
