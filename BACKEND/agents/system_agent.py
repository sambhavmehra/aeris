"""
AERIS System Agent -- OS automation and shell command execution.
Plans which tools to use via ToolSelector + LLM, executes them, reports results.
"""

import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.system")

PLAN_PROMPT = """You are an OS automation AI. The user wants to perform a system or browser operation.

Available tools (ranked by relevance):
{tools}

{prior_context}

User request: {message}

Respond with ONLY valid JSON:
{{
  "tools": [
    {{"name": "tool_name", "params": {{"param": "value"}}}}
  ],
  "explanation": "what you're doing and why"
}}

Rules:
- "open X" / "X khol" / "X kholo" / "X khol na" / "launch X" -> use open_app with the app name
- "search on browser / search on Google / google search X" -> use google_search with the query
- "search on YouTube / youtube search X" -> use youtube_search with the query
- "search X on Amazon/Reddit/GitHub/etc" -> use app_search with app_name and query
- "play X / play a song / play [song name]" -> use play_youtube with query
- "play X on YouTube / play X on youtube" -> use play_on_youtube_visible with query
- "pause / next / volume up / mute" (media) -> use system_control with action
- For command execution -> use run_bash with the exact command
- For file browsing -> use list_dir or read_file
- To search for a file anywhere on the system -> use find_system_file
- For UI automation, screen interaction, or visual tasks -> use computer_use_task with instruction
- You can chain multiple tools if needed. If a file path is not in the prior context, you MUST first run find_system_file to locate the file, followed by convert_file, read_file, or other file tools.
- When chaining find_system_file with convert_file or read_file, use a placeholder path like "/path/to/file" or the filename for the subsequent tool. The engine's parameter healer will automatically replace it with the found path after the search step executes.
- PREFER tools ranked higher (they scored better for this query)
- If prior context provides a file path, use that EXACT absolute path — DO NOT invent or guess paths
- For file conversion, use convert_file with the EXACT input_path from prior context (or from the find_system_file step in your chain) and the correct target_format (e.g. 'docx' for doc/Word)
"""


class SystemAgent(BaseAgent):
    """Handles OS automation -- opening apps, running commands, file ops.
    Uses ToolSelector for intelligent tool matching + LLM for final planning."""

    def __init__(self):
        super().__init__(
            name="SystemAgent",
            description="OS automation -- run commands, open apps, manage files, get system info",
            task_domain="system",
            version="2.0.0",
            capabilities=[
                "App Control (Open/Close)",
                "Browser Navigation (Google, YouTube)",
                "Screenshot Analysis",
                "Shell Command Execution",
                "File System Operations",
                "Media Playback Control",
                "System Info and Status",
                "UI Automation (Computer Use)",
            ],
        )
        self._selector = None

    def _get_selector(self):
        """Lazy-init ToolSelector from universal registry."""
        if self._selector is None:
            try:
                from tools.universal_registry import get_universal_registry
                from tools.tool_selector import ToolSelector
                reg = get_universal_registry()
                system_tools = []
                for cat in ["system", "automation", "file"]:
                    system_tools.extend(reg.get_tools_by_category(cat))
                if system_tools:
                    self._selector = ToolSelector(system_tools)
                    self.logger.info(f"ToolSelector initialized with {len(system_tools)} system/automation/file tools")
            except Exception as e:
                self.logger.debug(f"ToolSelector unavailable, using basic registry: {e}")
        return self._selector

    async def think(self, message: str, context: dict) -> Any:
        # Try ToolSelector first for smarter ranking
        selector = self._get_selector()
        if selector:
            candidates = selector.select(message, top_k=15, category_hint=None)
            if candidates:
                tools_desc = "\n".join(
                    f"- {c.tool.name}({', '.join(p.name for p in c.tool.input_schema.params)}): "
                    f"{c.tool.description} [score={c.score:.2f}]"
                    for c in candidates
                )
                self.logger.info(f"ToolSelector ranked {len(candidates)} candidates for: {message[:60]}")
            else:
                tools_desc = "\n".join(tool_registry.get_tools_description(cat) for cat in ["system", "automation", "file"])
        else:
            tools_desc = "\n".join(tool_registry.get_tools_description(cat) for cat in ["system", "automation", "file"])

        # Build prior context from previous pipeline steps (e.g. file paths found by AnalyzerAgent)
        prior_ctx = ""
        if context.get("prior_step_context"):
            prior_ctx = (
                "=== CONTEXT FROM PREVIOUS STEPS ===\n"
                f"{context['prior_step_context']}\n"
                "=== END CONTEXT ===\n"
                "CRITICAL: If the above context contains a file path, you MUST use that EXACT path in your tool parameters. DO NOT search for the file again."
            )
            self.logger.info(f"SystemAgent received prior context ({len(context['prior_step_context'])} chars)")
        elif context.get("recent_tasks"):
            prior_ctx = (
                "=== RECENT AGENT TASK EXECUTIONS ===\n"
                f"{context['recent_tasks']}\n"
                "=== END RECENT TASKS ===\n"
                "Use the recent tasks to resolve pronouns or build on top of previous work."
            )
            self.logger.info(f"SystemAgent received task history context")

        prompt = PLAN_PROMPT.format(tools=tools_desc, message=message, prior_context=prior_ctx)

        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            return json.loads(raw)
        except Exception as e:
            self.logger.warning(f"Plan parsing failed: {e}")
            return {
                "tools": [{"name": "run_bash", "params": {"command": message}}],
                "explanation": "Direct command execution",
            }

    async def execute(self, plan: Any) -> Any:
        from agents.observer_agent import ObserverAgent
        import asyncio
        observer = ObserverAgent()
        
        results = []
        aliases = {
            "run_command": "run_bash",
            "list_directory": "list_dir",
            "play_song": "play_youtube",
            "media_control": "system_control",
            "youtube_control": "system_control",
            "vision_execute_task": "computer_use_task",
        }
        for step in plan.get("tools", []):
            name = aliases.get(step.get("name", ""), step.get("name", ""))
            params = step.get("params", {})
            
            step_info = {"name": name, "params": params, "retry_count": 0}
            max_retries = 2
            
            outcome = {}
            decision = {}
            strategy = ""
            
            while step_info["retry_count"] <= max_retries:
                # 1. Execute Tool
                try:
                    result = await tool_registry.execute_async(step_info["name"], **step_info["params"])
                    outcome = {
                        "status": "success",
                        "tool": step_info["name"],
                        "result": result,
                        "execution_time": 0,
                    }
                except Exception as e:
                    outcome = {"status": "error", "error": str(e)}

                # Record health
                try:
                    from tools.tool_health import get_health_tracker
                    tracker = get_health_tracker()
                    success = outcome.get("status") == "success" or outcome.get("success") is True
                    exec_time = outcome.get("execution_time", 0)
                    tracker.record_execution(step_info["name"], success, exec_time * 1000)
                except Exception:
                    pass

                # 2. Observe Outcome
                try:
                    decision = await observer.process(step_info, outcome)
                except Exception as e:
                    self.logger.warning(f"Observer failed: {e}. Defaulting to proceed.")
                    decision = {"decision": "proceed", "status": "success", "result": outcome}
                
                # 3. Handle Decision
                if decision.get("decision") == "proceed":
                    results.append(outcome)
                    break
                    
                # Recover
                strategy = decision.get("strategy")
                self.logger.warning(f"Step {step_info['name']} failed. Observer strategy: {strategy}. Suggestion: {decision.get('suggestion')}")
                
                if strategy == "abort":
                    results.append({"status": "error", "error": decision.get("error", "Aborted by observer")})
                    break
                elif strategy == "skip_step":
                    results.append({"status": "skipped", "result": "Skipped by observer"})
                    break
                elif strategy == "retry_different_params":
                    suggestion = decision.get("suggestion", "")
                    if suggestion:
                        # Gather file paths / data from prior successful steps to avoid hallucinated paths
                        prior_results_str = ""
                        for r in results:
                            if r.get("status") == "success" and r.get("result"):
                                prior_results_str += f"\nSuccessful prior step result: {str(r['result'])[:400]}\n"

                        # Heal params using LLM
                        try:
                            prompt = (
                                f"Tool '{step_info['name']}' failed with error:\n{decision.get('error')}\n\n"
                                f"Observer suggestion:\n{suggestion}\n\n"
                                f"Current params:\n{json.dumps(step_info['params'], indent=2)}\n\n"
                                f"{prior_results_str}\n"
                                "CRITICAL: If prior step results contain a file path, use that EXACT path. DO NOT invent paths.\n"
                                "Output ONLY a raw JSON object with the corrected parameters. "
                                "Do NOT include any markdown formatting."
                            )
                            raw = await ai_engine.classify(prompt)
                            cleaned = raw.strip()
                            if cleaned.startswith("```"):
                                cleaned = cleaned.split("\n", 1)[-1]
                                if cleaned.endswith("```"):
                                    cleaned = cleaned[:-3]
                                cleaned = cleaned.strip()
                            
                            new_params = json.loads(cleaned)
                            step_info["params"] = new_params
                            self.logger.info(f"Healed params for {step_info['name']}: {new_params}")
                        except Exception as e:
                            self.logger.warning(f"Failed to heal params: {e}")
                            
                elif strategy == "use_alternative":
                    alt_tool = decision.get("alternative_tool")
                    if alt_tool:
                        step_info["name"] = alt_tool
                
                step_info["retry_count"] += 1
                if step_info["retry_count"] <= max_retries:
                    await asyncio.sleep(1) # Backoff
            
            # If exhausted retries
            if step_info["retry_count"] > max_retries:
                if strategy not in ("abort", "skip_step") and decision.get("decision") != "proceed":
                     results.append({"status": "error", "error": f"Max retries exhausted. Last error: {decision.get('error')}"})

        return {"explanation": plan.get("explanation", ""), "results": results}

    async def report(self, results: Any) -> str:
        # Check if any step returned a __ui_action__ JSON
        for r in results.get("results", []):
            if r.get("status") == "success" and isinstance(r.get("result"), str):
                try:
                    parsed = json.loads(r["result"])
                    if isinstance(parsed, dict) and "__ui_action__" in parsed:
                        return r["result"]
                except Exception:
                    pass

        explanation = results.get("explanation", "")
        raw = json.dumps(results.get("results", []), indent=2, default=str)

        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS. Report system operation results clearly using markdown. Be concise."},
                {"role": "user", "content": f"Operation: {explanation}\n\nResults:\n{raw}"},
            ], max_tokens=1024)
        except Exception:
            return f"## System Operation Complete\n\n```json\n{raw}\n```"
