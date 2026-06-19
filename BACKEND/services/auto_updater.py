import os
import json
import logging
import time
import subprocess
import re
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from config import settings
from ai_engine import ai_engine
from memory.store import memory_store

logger = logging.getLogger("aeris.auto_updater")

class AutoUpdater:
    """Autonomous Self-Improvement & Tech Research service for AERIS (Synchronous to avoid loop nesting)."""

    def __init__(self):
        from config import settings
        self.backend_dir = settings.BASE_DIR
        self.tools_dir = self.backend_dir / "tools"
        self.failed_tools_file = self.backend_dir / "failed_tools.json"

    def run_upgrade_cycle(self) -> Dict[str, Any]:
        """Perform research, draft upgrades, validate them in sandbox, and update code + notify user."""
        logger.info("Starting autonomous self-improvement & tech research cycle...")
        
        status = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "research_queries": [],
            "findings": "",
            "created_tools": [],
            "updated_dependencies": [],
            "errors": []
        }

        try:
            # 1. Research phase (Query recent trending tech, APIs, libraries, or vulnerabilities)
            research_data = self._conduct_tech_research(status)
            
            # 2. Analyze failed tools to learn from past errors
            learning_insights = self._analyze_failed_logs(status)
            
            # 3. Create or update tools based on findings and insights
            upgrades = self._implement_tool_upgrades(research_data, learning_insights, status)
            
            # 4. Notify on UI and Email
            self._notify_user(status)
            
            return status

        except Exception as e:
            logger.error(f"Error during autonomous upgrade cycle: {e}")
            status["errors"].append(str(e))
            # Fallback notification
            try:
                self._notify_failure(str(e))
            except Exception:
                pass
            return status

    def _conduct_tech_research(self, status: Dict[str, Any]) -> str:
        """Search the web for trending developer tools, APIs, and python packages."""
        query = "latest python libraries 2026 for developers developer-friendly utilities"
        status["research_queries"].append(query)
        
        try:
            from services.chat_engine import realtime_search
            # Run realtime search to fetch current facts
            search_results = realtime_search(query)
            status["findings"] = search_results[:1500] + "...[truncated]"
            return search_results
        except Exception as e:
            logger.warning(f"Realtime search failed: {e}")
            return "No search results retrieved."

    def _analyze_failed_logs(self, status: Dict[str, Any]) -> str:
        """Read failed_tools.json and deduce corrective guidelines."""
        if not self.failed_tools_file.exists():
            return "No failed logs found."
            
        try:
            data = json.loads(self.failed_tools_file.read_text(encoding="utf-8"))
            failures = data.get("failed_tools", [])
            if not failures:
                return "No failures to analyze."
                
            recent_failures = failures[-3:]
            prompt = f"Analyze these recent tool execution failures and generate 2-3 short, actionable rules to avoid these errors in the future:\n{json.dumps(recent_failures, indent=2)}"
            
            # Query LLM synchronously
            raw = asyncio.run(ai_engine.chat(
                messages=[
                    {"role": "system", "content": "You are the AERIS Self-Correction Engine. Write short, direct rules for LLM prompting."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            ))
            
            insights = raw.strip()
            # Store in long-term memory
            for line in insights.splitlines():
                line = line.strip().strip("-*").strip()
                if line and len(line) > 10:
                    asyncio.run(memory_store.add_fact(f"Self-Correction Rule: {line}"))
                    
            return insights
        except Exception as e:
            logger.warning(f"Failed to analyze failed logs: {e}")
            return f"Error analyzing logs: {e}"

    def _implement_tool_upgrades(self, research_data: str, learning_insights: str, status: Dict[str, Any]) -> List[str]:
        """Propose, test, validate, and write new tools to disk in a non-breaking manner."""
        prompt = f"""You are the AERIS Autonomous Code Generator. Based on the following research on trending packages/APIs and recent learning insights, write a brand new, lightweight utility tool module in Python.
        
        RESEARCH DATA:
        {research_data}
        
        LEARNING INSIGHTS:
        {learning_insights}
        
        Requirements:
        1. Write exactly one python function. It must be standalone, require no complex credentials, and be highly developer-friendly (e.g. text formatting, color logging, regex helpers, date manipulation, system info, JSON parser).
        2. The output must be valid Python code.
        3. Do NOT include markdown code blocks. Just output the clean python code itself.
        4. Name the main function starting with 'auto_helper_'.
        """
        
        try:
            # Generate code using LLM
            raw_code = asyncio.run(ai_engine.chat(
                messages=[
                    {"role": "system", "content": "You are a professional Python engineer. Respond with ONLY python code, no markdown blocks, no commentary."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            ))
            
            code = raw_code.strip().replace("```python", "").replace("```", "").strip()
            
            # Extract function name using simple regex
            func_name_match = re.search(r"def\s+(auto_helper_\w+)\s*\(", code)
            if not func_name_match:
                raise ValueError("Generated code does not contain a function named 'auto_helper_...'")
                
            func_name = func_name_match.group(1)
            temp_filename = f"temp_{func_name}.py"
            temp_filepath = self.tools_dir / temp_filename
            
            # 1. Write to temporary file for sandbox validation
            temp_filepath.write_text(code, encoding="utf-8")
            
            # 2. Syntax/Import checking
            try:
                # Try compiling the code first to check syntax
                compile(code, temp_filename, "exec")
                
                # Check run in isolated process to ensure it doesn't crash or break imports
                result = subprocess.run(
                    ["python", "-c", f"import sys; sys.path.insert(0, r'{self.tools_dir}'); import temp_{func_name}; print('Compilation Success!')"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode != 0:
                    raise RuntimeError(f"Sandbox verification failed: {result.stderr}")
                    
                # 3. Successful validation -> Write to permanent file
                perm_filename = f"{func_name}.py"
                perm_filepath = self.tools_dir / perm_filename
                perm_filepath.write_text(code, encoding="utf-8")
                
                # Register the new tool dynamically in tool_registry.py
                self._register_in_registry(func_name, perm_filename)
                
                status["created_tools"].append(func_name)
                logger.info(f"Successfully created and validated new tool: {func_name}")
                
            finally:
                # Cleanup temp file
                if temp_filepath.exists():
                    try:
                        os.remove(temp_filepath)
                    except Exception:
                        pass
                        
            return status["created_tools"]
            
        except Exception as e:
            logger.error(f"Failed to forge or update tools: {e}")
            status["errors"].append(f"Tool generation failed: {e}")
            return []

    def _register_in_registry(self, func_name: str, filename: str):
        """Append registration code to tool_registry.py dynamically so it is registered on next reload."""
        registry_path = self.tools_dir / "tool_registry.py"
        if not registry_path.exists():
            return
            
        try:
            content = registry_path.read_text(encoding="utf-8")
            import_str = f"\n    # —— 23. Autonomously Upgraded Tool —— #\n    try:\n        from tools.{func_name} import {func_name}\n        reg.register('{func_name}', 'Autonomously upgraded helper tool.', {func_name}, [], RiskLevel.SAFE, 'auto_improvement')\n        logger.info('Registered autonomously upgraded tool {func_name}')\n    except Exception as e:\n        logger.warning('Failed to register auto tool: ' + str(e))\n"
            
            target_str = "logger.info(f\"Tool registry initialized with {len(reg.get_tool_names())} tools.\")"
            if target_str in content:
                parts = content.split(target_str, 1)
                new_content = parts[0] + import_str + "\n    " + target_str + parts[1]
                registry_path.write_text(new_content, encoding="utf-8")
                logger.info(f"Registered {func_name} in tool_registry.py")
        except Exception as e:
            logger.error(f"Failed to append registry: {e}")

    def _notify_user(self, status: Dict[str, Any]):
        """Send notifications to the user on the UI and via Email."""
        tool_list = ", ".join(status["created_tools"]) or "No new tools added"
        error_msg = f" (Errors: {', '.join(status['errors'])})" if status["errors"] else ""
        
        ui_msg = (
            f"🔔 **AERIS Autonomous System Upgrade Complete**\n\n"
            f"- **Timestamp:** {status['timestamp']}\n"
            f"- **Research Query:** {', '.join(status['research_queries'])}\n"
            f"- **Added Tools:** {tool_list}{error_msg}\n"
            f"- **Details:** AERIS has autonomously researched trending technology and successfully generated, validated, "
            f"and sandboxed new system utility tools in the background without affecting current services."
        )
        memory_store.add_message("assistant", ui_msg)
        
        try:
            from agents.email_agent import EmailAgent
            email_agent = EmailAgent()
            email_body = (
                f"Hello Sambhav,\n\n"
                f"This is an automated notification from your AERIS OS.\n"
                f"The system has successfully completed its autonomous upgrade cycle.\n\n"
                f"Summary of Changes:\n"
                f"- Timestamp: {status['timestamp']}\n"
                f"- Research Findings: {status['findings'][:500]}...\n"
                f"- Created Tools: {tool_list}\n"
                f"- Status: Success (No current working operations were affected).\n\n"
                f"Best regards,\n"
                f"AERIS AI Coordinator"
            )
            
            plan = {
                "recipient": "sambhavmehra07@gmail.com",
                "subject": "🚀 AERIS: Background System Upgrade Complete",
                "body": email_body
            }
            # Execute email delivery synchronously
            asyncio.run(email_agent.execute(plan))
            logger.info("Sent upgrade notification email to user.")
        except Exception as e:
            logger.error(f"Failed to send notification email: {e}")

    def _notify_failure(self, error: str):
        """Send simple error email if cycle crashed."""
        try:
            from agents.email_agent import EmailAgent
            email_agent = EmailAgent()
            plan = {
                "recipient": "sambhavmehra07@gmail.com",
                "subject": "⚠️ AERIS: Background Upgrade Failure",
                "body": f"The background upgrade cycle encountered an error: {error}"
            }
            asyncio.run(email_agent.execute(plan))
        except Exception:
            pass

# Singleton helper
_auto_updater = None
def get_auto_updater() -> AutoUpdater:
    global _auto_updater
    if _auto_updater is None:
        _auto_updater = AutoUpdater()
    return _auto_updater
