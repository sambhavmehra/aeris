"""
AERIS Antigravity Agent — Interface for commanding and monitoring the Antigravity Project Builder Swarm.
"""

import logging
from typing import Any
from agents.base_agent import BaseAgent
from agents.project_builder import run_project_builder, check_build_status

logger = logging.getLogger("aeris.agent.antigravity")

class AntigravityAgent(BaseAgent):
    """
    Dedicated agent for project building automation.
    Delegates instructions to the multi-agent swarm via ProjectBuilderSystem.
    """

    def __init__(self):
        super().__init__(
            name="AntigravityAgent",
            description="Antigravity agent — commands and monitors the multi-agent swarm to scaffold and build complete projects",
            task_domain="codepipeline",
            version="1.0.0",
            capabilities=[
                "Autonomously Scaffold Projects",
                "Generate Complete Multi-file Workspaces",
                "Verify Generated Codebases",
                "Monitor Swarm Progress",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """
        Decide whether the user wants to build a new project or check status.
        """
        msg_lower = message.lower().strip()
        
        # Quick rule checks for status queries
        status_keywords = [
            "status", "progress", "progress kya hai", "status kya hai",
            "kaha tak pahuncha", "kitna kaam ho gaya", "check build", "monitoring"
        ]
        is_status = any(kw in msg_lower for kw in status_keywords)
        
        if is_status:
            return {"action": "check_status"}
            
        # Extract project objective using LLM or default to message
        prompt = (
            "You are the planner for the AntigravityAgent. Determine the user's intent. "
            "Is the user asking to build/create a new project, or check status of the current build?\n"
            "If they want to build a new project, extract a clear, detailed project objective/description from their prompt.\n"
            "Respond with ONLY JSON:\n"
            '{"action": "build" | "check_status", "objective": "detailed description of the project to build"}\n\n'
            f"User message: {message}"
        )
        try:
            raw = await self._llm_call(
                system_prompt="You are the AntigravityAgent planner.",
                user_prompt=prompt,
                temperature=0.2
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            import json
            plan = json.loads(raw)
            # Default objective if not found
            if plan.get("action") == "build" and not plan.get("objective"):
                plan["objective"] = message
            return plan
        except Exception as e:
            logger.error(f"Failed to parse intent in think(): {e}")
            # Fallback based on simple string search
            if "status" in msg_lower or "progress" in msg_lower:
                return {"action": "check_status"}
            return {"action": "build", "objective": message}

    async def execute(self, plan: Any) -> Any:
        """
        Execute the planned action: build a project or check status.
        """
        action = plan.get("action", "build")
        if action == "check_status":
            try:
                status_report = check_build_status()
                return {"success": True, "action": "check_status", "report": status_report}
            except Exception as e:
                return {"success": False, "error": f"Failed to check status: {str(e)}"}
        else:
            objective = plan.get("objective", "")
            if not objective:
                return {"success": False, "error": "No project objective specified."}
            try:
                # Trigger build using our background project builder
                response_str = run_project_builder(objective)
                return {"success": True, "action": "build", "message": response_str}
            except Exception as e:
                return {"success": False, "error": f"Failed to start project build: {str(e)}"}

    async def report(self, results: Any) -> str:
        """
        Format the output for the user.
        """
        if not results.get("success"):
            return f"❌ **Antigravity command failed:** {results.get('error')}"
            
        action = results.get("action")
        if action == "check_status":
            return results.get("report", "No status report available.")
        else:
            return results.get("message", "Project build successfully triggered in background.")
