"""
AERIS Investigation Agent
Analyzes failed tasks, logs, system errors, and performs broad general investigations.
Cooperates with surrounding agents (like RepairAgent, SystemAgent, CodeAgent) to fix issues.
"""
from __future__ import annotations

import os
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from config import settings

logger = logging.getLogger("aeris.agent.investigation")


class InvestigationAgent(BaseAgent):
    """
    Agent specialized in diagnosing task failures, examining system states,
    and performing general investigations. Can coordinate with other agents to solve problems.
    """

    def __init__(self):
        super().__init__(
            name="InvestigationAgent",
            description="Specialized agent for investigating failed tasks, error logs, and system states",
            task_domain="investigation",
            version="1.0.0",
            capabilities=[
                "failed_task_investigation",
                "general_investigation",
                "system_state_investigation",
                "collaborative_agent_repair",
            ]
        )

    async def _read_latest_failures(self) -> Dict[str, Any]:
        """Read and parse the latest entries from failed_tools.json."""
        backend_dir = Path(__file__).resolve().parent.parent
        json_path = backend_dir / "failed_tools.json"
        
        failures = []
        if json_path.exists() and json_path.stat().st_size > 0:
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                failures = data.get("failed_tools", [])
            except Exception as e:
                logger.warning(f"Failed to read failed_tools.json: {e}")
                
        # Also check failed_log.txt if JSON is empty/corrupt
        txt_path = backend_dir / "failed_log.txt"
        txt_content = ""
        if txt_path.exists() and txt_path.stat().st_size > 0:
            try:
                txt_content = txt_path.read_text(encoding="utf-8")
            except Exception:
                pass

        return {
            "json_failures": failures[-5:],  # Return last 5 failures
            "text_log_summary": txt_content[-2000:] if txt_content else "No text logs found."
        }

    async def think(self, message: str, context: dict) -> Any:
        """Formulate a plan for the investigation based on user message and logs."""
        self.log(f"Investigating request: {message[:100]}...")
        
        # Hardcoded rule for memory updates to bypass LLM classification flakiness
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in ("memory update", "apni memory", "personal details", "profile details", "save my info", "update my details")):
            return {
                "investigation_type": "memory_update",
                "target": message,
                "steps": [{"step_id": "s1", "action": "Extract and save memory details", "tool": "save_personal_details"}],
                "reasoning": "Determined as memory update via pre-classification rules.",
                "message": message
            }

        # Load failures context
        failures_ctx = await self._read_latest_failures()
        surrounding_agents = context.get("surrounding_agents_summary", "")

        system_prompt = (
            "You are the Investigation Agent (NEXUS Investigator) for AERIS.\n"
            "Your job is to examine failed tasks, logs, or general queries and propose solutions.\n\n"
            "COOPERATION & HEALING:\n"
            "- You can delegate sub-tasks to surrounding agents using the 'use_agent' tool.\n"
            "- If a file is broken (syntax/import/runtime), delegate the patch application to 'RepairAgent'.\n"
            "- If a terminal command needs to run for diagnostics, delegate to 'SystemAgent' or 'CodeAgent'.\n"
            "- If a deep internet query is needed, delegate to 'ResearchAgent'.\n"
            "- Always keep your actions scoped and constructive.\n\n"
            "Respond with ONLY a valid JSON object mapping this structure:\n"
            "{\n"
            "  \"investigation_type\": \"failed_task\" or \"general\" or \"memory_update\",\n"
            "  \"target\": \"What is being investigated (e.g. failed write_file tool, or specific file name, or user memory update string)\",\n"
            "  \"steps\": [\n"
            "     {\"step_id\": \"s1\", \"action\": \"Read details from failed log\", \"tool\": \"read_failed_log\"},\n"
            "     {\"step_id\": \"s2\", \"action\": \"Analyze and solve the bug\", \"tool\": \"llm_reasoning\"}\n"
            "  ],\n"
            "  \"reasoning\": \"Your thought process behind the investigation\"\n"
            "}"
        )

        user_prompt = (
            f"USER REQUEST: \"{message}\"\n\n"
            f"SURROUNDING ACTIVE AGENTS:\n{surrounding_agents}\n\n"
            f"LATEST FAILURE LOGS:\n"
            f"{json.dumps(failures_ctx['json_failures'], indent=2, default=str)}\n\n"
            f"Respond with ONLY JSON:"
        )

        try:
            raw = await ai_engine.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.2, response_format={"type": "json_object"})
            
            plan_dict = json.loads(raw.strip().strip("```json").strip("```").strip())
            plan_dict["message"] = message
            return plan_dict
        except Exception as e:
            logger.warning(f"LLM plan generation failed: {e}. Fallback to direct failure resolution.")
            return {
                "investigation_type": "failed_task" if "fail" in message.lower() or "error" in message.lower() else "general",
                "target": "failed_log",
                "steps": [{"step_id": "s1", "action": "Inspect latest failure and resolve it", "tool": "auto_heal"}],
                "reasoning": f"Fallback mode active due to plan generation issue: {e}",
                "message": message
            }

    async def execute(self, plan: Any) -> Any:
        """Perform the steps outlined in the investigation plan."""
        investigation_type = plan.get("investigation_type", "general")
        target = plan.get("target", "")
        self.log(f"Running investigation: type={investigation_type}, target={target}")

        # Scenario 0: Memory Update for sensitive details
        if investigation_type == "memory_update":
            text_to_extract = plan.get("message") or target or ""
            
            # Verify if this is the owner's details or someone else's details
            validation_prompt = (
                f"Verify if the following text describes personal/contact details belonging to the user/owner of this computer "
                f"(named Sambhav Mehra, or 'me', 'mera', 'owner'), or if it describes an external contact/employee (like Sandeep Kumar, Rahul, etc.).\n"
                f"Text: \"{text_to_extract}\"\n\n"
                f"Respond with ONLY a JSON object: {{\"is_owner\": true/false}}"
            )
            try:
                val_raw = await ai_engine.chat([
                    {"role": "system", "content": "You are a precise JSON classifier. Respond with ONLY JSON."},
                    {"role": "user", "content": validation_prompt}
                ], response_format={"type": "json_object"})
                val_data = json.loads(val_raw.strip())
                is_owner = val_data.get("is_owner", False)
                
                if not is_owner:
                    return {
                        "type": "memory_update",
                        "error": "This information describes an external contact and should be stored in Excel instead of the personal settings profile.",
                        "success": False,
                        "response": "Sir, ye profile/personal details storage strictly aapki settings aur email ke liye hai. Sandeep ya kisi aur contact ki details save karne ke liye Excel sheet (e.g. hr.xlsx) ka use kijiye."
                    }
            except Exception as e:
                logger.warning(f"Failed to validate owner status: {e}")
                
            prompt = (
                f"Extract structured sensitive profile details from this text and return a JSON object.\n"
                f"Fields MUST include: Name, Email, Phone, Age, Role.\n"
                f"Text to extract from: \"{text_to_extract}\""
            )
            try:
                extracted = await ai_engine.chat([
                    {"role": "system", "content": "You are a precise JSON extractor. Respond ONLY with valid JSON mapping fields."},
                    {"role": "user", "content": prompt}
                ], response_format={"type": "json_object"})
                details = json.loads(extracted.strip())
                
                from utils.personal_details_helper import save_personal_details
                saved_details = save_personal_details(details)
                
                return {
                    "type": "memory_update",
                    "updated_fields": saved_details,
                    "success": True
                }
            except Exception as e:
                logger.error(f"Failed to perform memory update in InvestigationAgent: {e}")
                return {
                    "type": "memory_update",
                    "error": str(e),
                    "success": False
                }

        # Scenario A: Investigating a task failure
        failures_ctx = await self._read_latest_failures()
        latest_failures = failures_ctx.get("json_failures", [])

        if investigation_type == "failed_task" or not latest_failures:
            if latest_failures:
                last_fail = latest_failures[-1]
                tool_name = last_fail.get("tool_name", "Unknown")
                err_msg = last_fail.get("error", "Unknown error")
                task_id = last_fail.get("task_id", "sys_manual")
                args = last_fail.get("arguments", {})

                # Generate a diagnosis
                prompt = (
                    f"AERIS Tool '{tool_name}' failed during task execution.\n"
                    f"Task ID: {task_id}\n"
                    f"Arguments: {json.dumps(args, default=str)}\n"
                    f"Error Message: {err_msg}\n\n"
                    f"{{\n"
                    f"  \"diagnosis\": \"Detailed explanation of what went wrong and why\",\n"
                    f"  \"resolution_agent\": \"The best agent to fix this (e.g. RepairAgent, SystemAgent, CodeAgent, or null if none)\",\n"
                    f"  \"resolution_message\": \"The message/prompt to send to the resolution agent to repair this issue\"\n"
                    f"}}"
                )
                
                try:
                    diag_raw = await ai_engine.chat([
                        {"role": "system", "content": "You are a senior debugging systems analyst. Respond with ONLY JSON."},
                        {"role": "user", "content": prompt}
                    ], response_format={"type": "json_object"})
                    diagnosis = json.loads(diag_raw.strip().strip("```json").strip("```").strip())
                except Exception as e:
                    diagnosis = {
                        "diagnosis": f"Failed to diagnose automatically: {e}. Raw error was: {err_msg}",
                        "resolution_agent": "RepairAgent",
                        "resolution_message": f"Diagnose and repair failed tool '{tool_name}' with error: {err_msg}"
                    }

                # Attempt automatic self-healing by calling the RepairAgent or designated agent
                repair_agent_name = diagnosis.get("resolution_agent")
                repair_msg = diagnosis.get("resolution_message")
                healing_result = "No self-healing was attempted."
                healing_success = False

                if repair_agent_name and repair_msg:
                    self.log(f"Cooperating with {repair_agent_name} to heal task failure: '{repair_msg[:80]}'")
                    try:
                        res = await self.use_agent(repair_agent_name, repair_msg)
                        healing_result = res.get("response", str(res))
                        healing_success = res.get("success", True)
                    except Exception as e:
                        healing_result = f"Failed to invoke {repair_agent_name} for repair: {e}"
                
                return {
                    "type": "failed_task",
                    "latest_failure": last_fail,
                    "diagnosis": diagnosis.get("diagnosis", ""),
                    "healing_agent": repair_agent_name,
                    "healing_message": repair_msg,
                    "healing_result": healing_result,
                    "healing_success": healing_success,
                    "success": True
                }
            else:
                return {
                    "type": "failed_task",
                    "diagnosis": "No recent task or tool failures found in failed logs.",
                    "success": True
                }

        # Scenario B: General investigation
        else:
            # Query LLM to research or investigate based on recent inputs
            prompt = (
                f"Perform a comprehensive investigation report based on the request:\n"
                f"\"{target}\"\n\n"
                f"You can use other agents if needed. If a file lookup or web research is required, synthesize the outcome. "
                f"Return a structured breakdown of findings."
            )
            try:
                findings = await ai_engine.chat([
                    {"role": "system", "content": "You are a senior intelligence analyst. Provide detailed findings and action plans."},
                    {"role": "user", "content": prompt}
                ])
            except Exception as e:
                findings = f"Failed to investigate: {e}"
                
            return {
                "type": "general",
                "findings": findings,
                "success": True
            }

    async def report(self, results: Any) -> str:
        """Format the investigation findings into a Hinglish/English report matching guidelines."""
        if not isinstance(results, dict):
            return str(results)

        r_type = results.get("type", "general")
        
        lines = []
        if r_type == "failed_task":
            fail = results.get("latest_failure")
            
            # Hinglish report structure
            lines.append("## 🔍 AERIS Investigation Report — Task Failure Diagnosis\n")
            if fail:
                lines.append(f"**Sir, maine system error logs check kiye hain. Yahan latest failure ki details hain:**\n")
                lines.append(f"- **Failed Tool/Agent:** `{fail.get('tool_name')}`")
                lines.append(f"- **Task ID:** `{fail.get('task_id')}`")
                lines.append(f"- **Timestamp:** `{fail.get('timestamp')}`")
                lines.append(f"- **Parameters Passed:** `{json.dumps(fail.get('arguments'), default=str)}`")
                lines.append(f"- **Error Output:**\n```\n{fail.get('error')}\n```\n")
                lines.append(f"### ⚙️ Root Cause Analysis (Diagnosis):")
                lines.append(f"{results.get('diagnosis')}\n")
                
                lines.append(f"### 🛠️ Self-Healing/Resolution Status:")
                if results.get("healing_agent"):
                    status = "✅ Successfully Resolved" if results.get("healing_success") else "❌ Healing Attempt Failed"
                    lines.append(f"- **Resolution Agent Triggered:** `{results.get('healing_agent')}`")
                    lines.append(f"- **Fix Instructions Sent:** *\"{results.get('healing_message')}\"*")
                    lines.append(f"- **Repair Status:** {status}")
                    lines.append(f"- **Repair Output:**\n\n{results.get('healing_result')}\n")
                else:
                    lines.append("- *No self-healing was necessary or could be automatically resolved.*")
            else:
                lines.append("Sir, recent task logs me koi failed tasks ya errors nahi mile hain. System completely normal aur healthy hai.")

        elif r_type == "memory_update":
            lines.append("## 💾 AERIS Memory Update — Sensitive Profile Details\n")
            if results.get("success", False):
                updated_fields = results.get("updated_fields", {})
                lines.append("**Sir, aapki memory update request successfully process ho gayi hai. Maine aapki sensitive information local memory me safe aur secure save kar li hai:**\n")
                lines.append("Yahan aapki updated contact details hain:")
                lines.append(f"- **Name:** {updated_fields.get('Name') or 'Not specified'}")
                lines.append(f"- **Email:** {updated_fields.get('Email') or 'Not specified'}")
                lines.append(f"- **Phone:** {updated_fields.get('Phone') or 'Not specified'}")
                lines.append(f"- **Age:** {updated_fields.get('Age') or 'Not specified'}")
                lines.append(f"- **Role:** {updated_fields.get('Role') or 'Not specified'}")
                
                # Also list any additional fields saved under Details
                extra_details = updated_fields.get("Details", {})
                if extra_details:
                    lines.append("\n**Additional Info:**")
                    for k, v in extra_details.items():
                        lines.append(f"- **{k}:** {v}")
                
                lines.append("\nAgar aap is memory me koi aur details add karna chahein, toh aap mujhe kabhi bhi bata sakte hain!")
            else:
                lines.append(f"**Sir, main memory update nahi kar paya.**\n\nError details:\n`{results.get('error', 'Unknown error')}`")
        else:
            # General investigation report
            lines.append("## 🔍 AERIS General Investigation Report\n")
            lines.append(f"**Sir, maine aapke target ki complete details investigate kiye hain. Yeh hain research findings:**\n")
            lines.append(results.get("findings", ""))

        return "\n".join(lines)
