"""
AERIS Dedicated Scheduler Agent
=================================
Manages scheduled tasks, reminders, alarms, and meetings.
Provides capabilities to list pending, completed, or failed scheduled tasks,
and cancel them using IDs or keyword matches.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.scheduler")


class SchedulerAgent(BaseAgent):
    """
    Dedicated agent for managing the background Task Scheduler.
    Can list, cancel, and schedule tasks/reminders/meetings.
    """

    def __init__(self):
        super().__init__(
            name="SchedulerAgent",
            description="Manages background tasks, reminders, alarms, and meetings.",
            task_domain="scheduler",
            version="1.0.0",
            capabilities=[
                "List Scheduled Tasks",
                "Cancel Scheduled Task",
                "Summarize Background Tasks",
                "Schedule Reminders & Meetings",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """
        Analyze the user query to determine the scheduler action to take.
        Actions: list | cancel | schedule | unknown
        """
        prompt = (
            "You are the planner for the SchedulerAgent.\n"
            "Analyze the user message to decide what action they want to perform on the scheduler. The possible actions are:\n"
            "- 'list': User wants to see scheduled tasks, check pending tasks, or see task history/status.\n"
            "- 'cancel': User wants to cancel, delete, stop, or remove a scheduled task/reminder/meeting.\n"
            "- 'schedule': User wants to schedule a new task, reminder, alarm, or meeting.\n"
            "- 'unknown': None of the above.\n\n"
            "Extract the following parameters based on the action:\n"
            "- For 'list': extract 'status' (can be one of: pending, completed, failed, cancelled, or null if not specified).\n"
            "- For 'cancel': extract 'task_spec' (the task ID, e.g., 'sch_123456_7890', or a keyword from the task, e.g., 'meeting', 'study', 'alarm').\n"
            "- For 'schedule': extract 'instruction' (the task/reminder content, e.g., 'Remind user: Meeting' or 'open chrome') and 'time_spec' (the time string, e.g., 'in 1 minute', 'in 30 mins', '6pm').\n\n"
            "Ensure you translate pronouns and resolve details from the user's message context.\n"
            "Respond ONLY with a JSON object. Do not include markdown formatting.\n"
            "JSON structure:\n"
            '{\n'
            '  "action": "list" | "cancel" | "schedule" | "unknown",\n'
            '  "status": string | null,\n'
            '  "task_spec": string | null,\n'
            '  "instruction": string | null,\n'
            '  "time_spec": string | null,\n'
            '  "explanation": "Brief explanation of your plan"\n'
            '}\n\n'
            f"User message: {message}"
        )

        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            details = json.loads(raw)
            self.logger.info(f"Generated scheduler plan: {details}")
            return details
        except Exception as e:
            self.logger.error(f"Failed to parse scheduler details in think(): {e}")
            return {"action": "unknown", "explanation": "Fallback due to planning error."}

    async def execute(self, plan: Any) -> Any:
        """
        Execute scheduler actions by invoking registry tools.
        """
        action = plan.get("action", "unknown")
        results = []

        try:
            if action == "list":
                status = plan.get("status")
                params = {}
                if status:
                    params["status"] = status
                outcome = await tool_registry.execute_async("list_scheduled_tasks", **params)
                results.append({
                    "action": "list",
                    "status": "success",
                    "result": outcome
                })
            elif action == "cancel":
                task_spec = plan.get("task_spec")
                if not task_spec:
                    return {"success": False, "error": "No task specification provided for cancellation."}
                outcome = await tool_registry.execute_async("cancel_scheduled_task", task_spec=task_spec)
                results.append({
                    "action": "cancel",
                    "status": "success",
                    "result": outcome
                })
            elif action == "schedule":
                instruction = plan.get("instruction")
                time_spec = plan.get("time_spec")
                if not instruction or not time_spec:
                    return {"success": False, "error": "Missing instruction or time_spec for scheduling."}
                outcome = await tool_registry.execute_async("schedule_execution", instruction=instruction, time_spec=time_spec)
                results.append({
                    "action": "schedule",
                    "status": "success",
                    "result": outcome
                })
            else:
                return {
                    "success": False,
                    "error": f"Unknown action '{action}'. Please specify whether you want to list, schedule, or cancel tasks."
                }

            return {
                "success": True,
                "action": action,
                "results": results
            }
        except Exception as e:
            self.logger.error(f"Failed to execute scheduler action {action}: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def report(self, results: Any) -> str:
        """
        Format results into a conversational Hinglish response.
        """
        if not results.get("success"):
            error_msg = results.get("error", "Unknown error")
            return f"❌ **Scheduler action fail ho gaya.**\n\n**Error:** {error_msg}\n\nSir, main is action ko complete nahi kar paya. Please try again."

        results_str = json.dumps(results, indent=2, default=str)
        prompt = (
            "You are AERIS (Autonomous Enhanced Reasoning Intelligence System), speaking to your creator Sambhav Mehra.\n"
            "You need to report the results of the scheduler operations you just performed.\n\n"
            "RULES:\n"
            "- ALWAYS address the user as 'Sir' (or 'sir') in your response. NEVER use 'bhai', 'bro', 'buddy', or any other informal/colloquial terms.\n"
            "- Respond in modern, natural, conversational Hinglish (Hindi written in Roman script) to make it smooth and friendly. Match the style guidelines (e.g., 'Sir, maine list_scheduled_tasks run kiya hai aur...', 'Maine check kiya, koi pending task nahi mila').\n"
            "- Use markdown formatting for readability (bold, code blocks, lists, emojis).\n"
            "- Be concise but thorough.\n\n"
            f"Scheduler Operation Results:\n{results_str}\n\n"
            "Generate your friendly, polite, Hinglish-personalized response now:"
        )

        try:
            response = await ai_engine.chat([
                {"role": "system", "content": "You are AERIS. Report scheduler operation results clearly and politely to Sambhav Mehra in Hinglish, addressing him as Sir."},
                {"role": "user", "content": prompt}
            ], max_tokens=1024)
            return response
        except Exception as e:
            self.logger.warning(f"LLM chat for report failed: {e}")
            # Text fallback
            action = results.get("action")
            if action == "list":
                return f"Sir, maine scheduled tasks list kar diye hain.\n\n```json\n{results_str}\n```"
            elif action == "cancel":
                return f"Sir, task successfully cancel ho gaya hai.\n\n```json\n{results_str}\n```"
            return f"Sir, scheduler operation report:\n\n```json\n{results_str}\n```"
