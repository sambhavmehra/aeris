"""
AERIS Observer Agent — Validates tool execution and plans recovery.
Inspired by AERIS ObserverAgent.
"""

import json
import logging
from typing import Any, Dict

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

logger = logging.getLogger("aeris.agent.observer")

OBSERVER_SYSTEM_PROMPT = """You are the Observer Agent of AERIS, an autonomous AI system.
Your job: evaluate whether a tool execution step succeeded or failed, and if it failed, decide the recovery strategy.

## Rules
1. Return ONLY valid JSON — no markdown, no explanation, no ```json wrapper.
2. If the execution was successful, return: {{"decision": "proceed", "confidence": 0.95, "summary": "brief summary of result"}}
3. If the execution failed, return:
   {{
     "decision": "recover",
     "confidence": 0.5,
     "error_category": "one of: not_found, permission_denied, invalid_params, network_error, tool_missing, unknown",
     "strategy": "one of: retry_same, retry_different_params, skip_step, abort",
     "suggestion": "what to fix before retry (e.g., correct file path, use different tool)",
     "alternative_tool": "name of an alternative tool if applicable"
   }}
4. Use "abort" only if the error is clearly unrecoverable.
5. Use "retry_same" for transient errors (network, timeout).
6. Use "retry_different_params" when the params seem wrong (wrong path, missing arg).
"""

class ObserverAgent(BaseAgent):
    """
    Analyzes execution output with LLM intelligence, checks results,
    and determines recovery paths when errors occur.
    """

    def __init__(self):
        super().__init__(
            name="ObserverAgent",
            description="Evaluates tool execution results and devises recovery strategies.",
            task_domain="observer",
            version="1.0.0",
            capabilities=[
                "Execution Monitoring",
                "Error Classification",
                "Recovery Strategy Planning",
                "False Positive Detection",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Not directly used in the standard pipeline for Observer."""
        pass

    async def execute(self, plan: Any) -> Any:
        """Not directly used in the standard pipeline for Observer."""
        pass
        
    async def report(self, results: Any) -> str:
        """Not directly used in the standard pipeline for Observer."""
        pass

    async def process(self, step_info: dict, execution_outcome: dict) -> Dict[str, Any]:
        """
        Takes the Step details and its outcome, evaluates via LLM, and returns
        a structured decision.
        """
        self.logger.info(f"Observing outcome for step using tool: {step_info.get('name')}")

        # Quick path: clear success
        if execution_outcome.get("status") == "success":
            result = execution_outcome.get("result", execution_outcome.get("stdout", ""))

            # Check for "false positive" — tool returned but with error-like output
            if self._looks_like_error(str(result)):
                self.logger.warning("Result text looks like an error despite success status. Running LLM evaluation.")
                return await self._llm_evaluate(step_info, execution_outcome)

            self.logger.info("Step execution evaluated as SUCCESS.")
            return {
                "decision": "proceed",
                "status": "success",
                "result": result,
                "confidence": 0.95,
            }

        # Failure path: use LLM for intelligent evaluation
        try:
            return await self._llm_evaluate(step_info, execution_outcome)
        except Exception as e:
            self.logger.warning(f"LLM evaluation failed: {e}. Using heuristic fallback.")
            return self._heuristic_evaluate(step_info, execution_outcome)

    async def _llm_evaluate(self, step_info: dict, outcome: dict) -> Dict[str, Any]:
        """Use LLM to evaluate execution outcome and decide recovery strategy."""
        user_prompt = (
            f"Tool: {step_info.get('name')}\n"
            f"Params: {json.dumps(step_info.get('params', {}), default=str)[:300]}\n"
            f"Status: {outcome.get('status')}\n"
            f"Result: {str(outcome.get('result', outcome.get('stdout', '')))[:500]}\n"
            f"Error: {outcome.get('error', outcome.get('stderr', 'none'))}\n"
            f"Retry count so far: {step_info.get('retry_count', 0)}\n"
        )

        raw = await ai_engine.classify(
            f"{OBSERVER_SYSTEM_PROMPT}\n\n{user_prompt}"
        )

        # Parse JSON response
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        evaluation = json.loads(cleaned)

        if evaluation.get("decision") == "proceed":
            return {
                "decision": "proceed",
                "status": "success",
                "result": outcome.get("result", outcome.get("stdout")),
                "confidence": evaluation.get("confidence", 0.9),
            }
        else:
            strategy = evaluation.get("strategy", "abort")
            return {
                "decision": "recover",
                "status": "failed",
                "error": outcome.get("error", outcome.get("stderr", "Unknown error")),
                "error_category": evaluation.get("error_category", "unknown"),
                "strategy": strategy,
                "suggestion": evaluation.get("suggestion", ""),
                "alternative_tool": evaluation.get("alternative_tool", ""),
                "confidence": evaluation.get("confidence", 0.5),
            }

    def _heuristic_evaluate(self, step_info: dict, outcome: dict) -> Dict[str, Any]:
        """Fallback heuristic evaluation when LLM is unavailable."""
        error = str(outcome.get("error", outcome.get("stderr", "Unknown error"))).lower()

        if "not found" in error or "missing" in error or "no such file" in error:
            strategy = "retry_different_params"
            category = "not_found"
        elif "permission" in error or "access denied" in error:
            strategy = "abort"
            category = "permission_denied"
        elif "timeout" in error or "connection" in error or "network" in error:
            strategy = "retry_same"
            category = "network_error"
        else:
            retry_count = step_info.get("retry_count", 0)
            strategy = "retry_same" if retry_count < 2 else "abort"
            category = "unknown"

        self.logger.debug(f"Heuristic recovery: category={category}, strategy={strategy}")

        return {
            "decision": "recover",
            "status": "failed",
            "error": outcome.get("error", outcome.get("stderr", "Unknown error")),
            "error_category": category,
            "strategy": strategy,
            "suggestion": "",
            "alternative_tool": ""
        }

    @staticmethod
    def _looks_like_error(result: str) -> bool:
        """Heuristic: does the result text look like an error?"""
        if not result or len(result) < 10:
            return False
        error_indicators = [
            "error:", "exception:", "traceback", "failed:", "failure:",
            "permission denied", "access denied", "forbidden", "unauthorized",
            "not found", "no such file", "does not exist", "filenotfounderror",
            "connection refused", "timeout", "unreachable", "connectionerror",
            "exit code", "returncode", "non-zero exit", "command failed",
            "importerror", "modulenotfounderror", "typeerror", "valueerror",
            "is not recognized", "the system cannot find",
        ]
        result_lower = result.lower()[:500]
        return any(ind in result_lower for ind in error_indicators)
