# -*- coding: utf-8 -*-
"""
AERIS — Proactive Self-Evolution System
=======================================
Enables AERIS to autonomously write, validate, and register its own tools and modules
on user request/confirmation.
"""

import os
import sys
import re
import json
import logging
import asyncio
import importlib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from config import settings
from ai_engine import ai_engine
from memory.store import memory_store

logger = logging.getLogger("aeris.self_evolution")

class SelfEvolutionEngine:
    """Autonomous Code Design, Sandbox Validation, and Dynamic Registry injection service."""

    def __init__(self):
        self.backend_dir = settings.BASE_DIR
        self.tools_dir = self.backend_dir / "tools"
        self.proposal_file = settings.DATA_DIR / "proposed_upgrade.json"
        self.tools_dir.mkdir(parents=True, exist_ok=True)

    async def propose_improvement(self, requirement_text: str) -> Dict[str, Any]:
        """Ask the LLM to design and generate a Python tool code proposal to address the user request."""
        logger.info(f"Generating self-evolution proposal for: '{requirement_text}'")
        
        system_prompt = (
            "You are the AERIS Autonomous System Designer. "
            "Your job is to design a brand new Python utility tool to fulfill the user's requirement. "
            "The tool must be self-contained and run on standard systems (use simulation fallbacks for IoT/hardware "
            "so it runs out-of-the-box). "
            "Write valid Python code. The main function in the code must start with 'auto_helper_'. "
            "You must respond ONLY with a valid JSON object (no markdown blocks, no formatting wrapper, no comments). "
            "The JSON must have the following keys:\n"
            "1. 'feature_name': Name of the function (e.g. 'auto_helper_iot_hub')\n"
            "2. 'description': Concise explanation of the capability in Hinglish/English\n"
            "3. 'code': Full, complete Python source code for the tool\n"
            "4. 'registration_code': Python code snippet to register the tool in tool_registry.py. Example format:\n"
            "   \"    try:\n"
            "        from tools.auto_helper_iot_hub import auto_helper_iot_hub\n"
            "        reg.register('auto_helper_iot_hub', 'Autonomous IoT control integration helper.', auto_helper_iot_hub, [], RiskLevel.SAFE, 'auto_improvement')\n"
            "        logger.info('Registered autonomously upgraded tool auto_helper_iot_hub')\n"
            "    except Exception as e:\n"
            "        logger.warning('Failed to register auto tool: ' + str(e))\"\n"
        )
        
        user_prompt = f"User Requirement: {requirement_text}"
        
        try:
            raw_response = await ai_engine.chat([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.3)
            
            clean_json = raw_response.strip().strip("```json").strip("```").strip()
            try:
                proposal_data = json.loads(clean_json, strict=False)
            except json.JSONDecodeError as jde:
                logger.error(f"JSON decode failed. Raw response was:\n{raw_response}")
                raise jde
            
            feature_name = proposal_data.get("feature_name", "").strip()
            code = proposal_data.get("code", "").strip("\r\n")
            
            if not feature_name or not code:
                raise ValueError("JSON response is missing feature_name or code.")
                
            # 1. Validation phase (compile check and import test in sandbox)
            temp_filename = f"temp_{feature_name}.py"
            temp_filepath = self.tools_dir / temp_filename
            temp_filepath.write_text(code, encoding="utf-8")
            
            sandbox_success = False
            sandbox_error = ""
            
            try:
                # Compile check
                compile(code, temp_filename, "exec")
                
                # Import check in subprocess
                result = subprocess.run(
                    ["python", "-c", f"import sys; sys.path.insert(0, r'{self.tools_dir}'); import temp_{feature_name}; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    sandbox_success = True
                else:
                    sandbox_error = result.stderr
            except Exception as e:
                sandbox_error = str(e)
            finally:
                if temp_filepath.exists():
                    os.remove(temp_filepath)
                    
            if not sandbox_success:
                logger.warning(f"Proposal sandbox validation failed: {sandbox_error}")
                return {
                    "success": False,
                    "error": f"Generated code did not pass sandbox validation: {sandbox_error}",
                    "proposed_code": code
                }
                
            # Save the valid proposal to disk for confirmation
            self.proposal_file.write_text(json.dumps(proposal_data, indent=2), encoding="utf-8")
            
            # Format markdown report for the user
            report = (
                f"### 🚀 AERIS PROPOSED SELF-UPGRADE PLAN\n\n"
                f"Sir, maine aapki requirement ke liye autonomously ek capability design ki hai aur check ki hai:\n\n"
                f"- **Feature Name**: `{feature_name}`\n"
                f"- **Description**: {proposal_data.get('description', 'No description provided')}\n"
                f"- **Sandbox Validation**: ✅ PASS (Syntax & imports verified)\n\n"
                f"#### Draft Python Code:\n"
                f"```python\n"
                f"{code}\n"
                f"```\n\n"
                f"#### Action Required:\n"
                f"Sir, kya main is improvement ko tools repository mein register aur install karoon? "
                f"Kripya confirmation ke liye **\"Apply proposal\"** bole ya type karein."
            )
            
            return {
                "success": True,
                "report": report,
                "proposal": proposal_data
            }
            
        except Exception as e:
            logger.error(f"Failed to generate proposal: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def execute_proposal(self) -> Tuple[bool, str]:
        """Reads the saved proposed_upgrade.json, writes it to disk, and injects registration code."""
        if not self.proposal_file.exists():
            return False, "Sir, mere paas abhi koi active proposed upgrade plan nahi hai."
            
        try:
            proposal_data = json.loads(self.proposal_file.read_text(encoding="utf-8"))
            feature_name = proposal_data.get("feature_name", "").strip()
            code = proposal_data.get("code", "").strip("\r\n")
            reg_code = proposal_data.get("registration_code", "").strip("\r\n")
            
            if not feature_name or not code or not reg_code:
                return False, "Proposed upgrade data is corrupted or incomplete."
                
            # 1. Write the permanent tool file
            perm_filename = f"{feature_name}.py"
            perm_filepath = self.tools_dir / perm_filename
            perm_filepath.write_text(code, encoding="utf-8")
            logger.info(f"Wrote permanent tool file: {perm_filepath}")
            
            # 2. Append registration to tool_registry.py
            registry_path = self.tools_dir / "tool_registry.py"
            if registry_path.exists():
                content = registry_path.read_text(encoding="utf-8")
                
                # Check if registration is already present
                if f"tools.{feature_name}" not in content:
                    target_str = "logger.info(f\"Tool registry initialized with {len(reg.get_tool_names())} tools.\")"
                    if target_str in content:
                        parts = content.split(target_str, 1)
                        # Format registration code block using textwrap to ensure perfect indentation
                        import textwrap
                        formatted_reg_code = textwrap.indent(textwrap.dedent(reg_code), "    ")
                        # Append registration code block
                        new_content = parts[0] + f"\n    # —— Dynamic Upgrade: {feature_name} ——\n" + formatted_reg_code + "\n\n    " + target_str + parts[1]
                        registry_path.write_text(new_content, encoding="utf-8")
                        logger.info(f"Appended registration to tool_registry.py")
            
            # 3. Reload tool_registry dynamically so it's loaded in active memory immediately
            try:
                import tools.tool_registry
                importlib.reload(tools.tool_registry)
                logger.info("Successfully reloaded tools.tool_registry in memory.")
            except Exception as e:
                logger.error(f"Failed to reload tool_registry in active memory: {e}")
                
            # 4. Clean up proposal file
            os.remove(self.proposal_file)
            
            # Log to long term memory
            await memory_store.add_fact(f"Self-Evolution: Upgraded and added tool '{feature_name}' successfully.")
            
            return True, f"Sir, capability `{feature_name}` autonomously compile, sandbox, aur registry register ho chuki hai! Main ab is feature ko use karne ke liye fully ready hoon."
            
        except Exception as e:
            logger.error(f"Failed to execute proposal: {e}")
            return False, f"Sir, implementation execute karne mein error aaya: {e}"

# Global singleton
self_evolution_engine = SelfEvolutionEngine()
