"""
AERIS Base Agent — Abstract blueprint that all sub-agents must follow.
Provides the think → execute → report orchestration pattern.
"""

from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from typing import Any, List, Optional


class BaseAgent(ABC):
    """
    Abstract base class for all AERIS sub-agents.
    
    Every agent follows the pipeline:
        think(message, context)  →  plan what to do
        execute(plan)            →  run tools / LLM calls
        report(results)          →  format human-readable output
        run(message, context)    →  orchestrate the full pipeline
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        memory_agent=None,
        task_domain: str = "general",
        version: str = "1.0.0",
        capabilities: Optional[list] = None,
    ):
        self.name = name
        self.description = description
        self.memory = memory_agent
        self.task_domain = task_domain
        self.version = version
        self.capabilities = capabilities or []
        self.logger = logging.getLogger(f"aeris.agent.{name.lower()}")
        self._is_working = True

    def health_check(self) -> bool:
        """Return True if the agent is operational. Override for custom checks."""
        return self._is_working

    @property
    def is_working(self) -> bool:
        return self._is_working

    def log(self, msg: str, level: str = "INFO"):
        """AERIS compatibility log wrapper."""
        if level.upper() == "WARNING":
            self.logger.warning(msg)
        elif level.upper() == "ERROR":
            self.logger.error(msg)
        elif level.upper() == "DEBUG":
            self.logger.debug(msg)
        else:
            self.logger.info(msg)

    def _llm_call(self, system_prompt: str, user_prompt: str, temperature: float = 0.3, max_tokens: int = 1500) -> str:
        """AERIS compatibility LLM call."""
        import asyncio
        from ai_engine import ai_engine
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = None
            
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if loop and loop.is_running():
            # If we're already in an async context, this is tricky for sync code.
            # But sub_agents run in a ThreadPoolExecutor, so loop.is_running() is usually False in their thread,
            # or they have their own event loop.
            try:
                # If there's no running loop in this thread, asyncio.run works.
                return asyncio.run(ai_engine.chat(messages, temperature=temperature, max_tokens=max_tokens))
            except RuntimeError:
                # If there IS a running loop in this thread, we shouldn't use asyncio.run
                import nest_asyncio
                nest_asyncio.apply()
                return asyncio.run(ai_engine.chat(messages, temperature=temperature, max_tokens=max_tokens))
        else:
            try:
                return asyncio.run(ai_engine.chat(messages, temperature=temperature, max_tokens=max_tokens))
            except RuntimeError:
                # Thread has no event loop running, run loop manually
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(ai_engine.chat(messages, temperature=temperature, max_tokens=max_tokens))
                finally:
                    new_loop.close()

    async def think(self, message: str, context: dict) -> Any:
        """
        Analyze the user message and decide what needs to be done.
        Returns a plan (structure depends on agent type).
        """
        ...

    async def execute(self, plan: Any) -> Any:
        """
        Execute the plan — run tools, call LLMs, etc.
        Returns raw results.
        """
        ...

    async def report(self, results: Any) -> str:
        """
        Format raw results into a human-readable response.
        Returns the final string to send back to the user.
        """
        ...

    def get_surrounding_agents(self) -> List[dict]:
        """
        Get metadata of all other active agents currently in the registry.
        """
        try:
            from agents.agent_registry import agent_registry
            all_agents = agent_registry.get_all_agents()
            return [
                {
                    "name": name,
                    "description": info.description,
                    "domain": info.task_domain,
                    "capabilities": info.capabilities
                }
                for name, info in all_agents.items()
                if name != self.name
            ]
        except Exception:
            return []

    @property
    def surrounding_agents_summary(self) -> str:
        """
        Returns a formatted string summary of other available agents.
        """
        agents_list = self.get_surrounding_agents()
        if not agents_list:
            return "No other agents are currently active."
        
        summary_lines = [f"Active surrounding agents ({len(agents_list)} total):"]
        for agent in agents_list:
            caps = ", ".join(agent["capabilities"][:3]) if agent["capabilities"] else "None"
            summary_lines.append(f"- {agent['name']} ({agent['domain']}): {agent['description']} [Capabilities: {caps}]")
        return "\n".join(summary_lines)

    async def determine_needed_agent(self, task_description: str) -> Optional[str]:
        """
        Dynamically determine if any surrounding agent is needed to help with the current task.
        Queries the LLM with the list of surrounding agents and their capabilities.
        """
        agents_list = self.get_surrounding_agents()
        if not agents_list:
            return None
            
        agents_info = "\n".join(
            f"- {a['name']}: {a['description']} (Capabilities: {', '.join(a['capabilities'])})"
            for a in agents_list
        )
        
        prompt = (
            f"You are the AERIS agent '{self.name}'. You are working on the following user request/task:\n"
            f"'{task_description}'\n\n"
            f"Here are the active surrounding agents currently available in the AERIS registry:\n"
            f"{agents_info}\n\n"
            f"Evaluate if you require assistance from any of these surrounding agents to complete this request.\n"
            f"Respond with ONLY JSON:\n"
            f"{{\n"
            f"  \"needs_help\": true or false,\n"
            f"  \"needed_agent_name\": \"exact name of the needed agent (e.g. SearchAgent, SecurityAgent) or null if false\",\n"
            f"  \"reason\": \"brief reason why you need their help\"\n"
            f"}}"
        )
        try:
            from ai_engine import ai_engine
            import json
            response = await ai_engine.classify(prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1] if "\n" in response else response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()
            data = json.loads(response)
            if data.get("needs_help") and data.get("needed_agent_name"):
                agent_name = data.get("needed_agent_name")
                # Verify the agent actually exists in the registry
                if any(a["name"] == agent_name for a in agents_list):
                    self.logger.info(f"[AgentNeed] {self.name} determines it needs help from {agent_name} for: {data.get('reason')}")
                    return agent_name
            return None
        except Exception as e:
            self.logger.warning(f"Error determining needed agent: {e}")
            return None

    async def run(self, message: str, context: Optional[dict] = None) -> dict:
        """
        Full agent pipeline: think → execute → report.
        Returns a structured dict with response, timing, and metadata.
        """
        context = context or {}
        context["surrounding_agents"] = self.get_surrounding_agents()
        context["surrounding_agents_summary"] = self.surrounding_agents_summary
        
        needed_agent = await self.determine_needed_agent(message)
        context["needed_agent"] = needed_agent

        start = time.time()
        needed_str = f", needed_agent={needed_agent}" if needed_agent else ""
        self.logger.info(f"▶ {self.name} processing (surrounding_agents={len(context['surrounding_agents'])}{needed_str}): {message[:80]}...")

        try:
            # Step 1: Think
            plan = await self.think(message, context)
            self.logger.debug(f"  Plan: {plan}")

            # Step 2: Execute
            results = await self.execute(plan)

            # Step 3: Report
            response = await self.report(results)

            elapsed = round(time.time() - start, 2)
            self.logger.info(f"✓ {self.name} completed in {elapsed}s")

            return {
                "agent": self.name,
                "response": response,
                "execution_time": elapsed,
                "success": True,
            }

        except Exception as e:
            elapsed = round(time.time() - start, 2)
            self.logger.error(f"✗ {self.name} failed after {elapsed}s: {e}")
            return {
                "agent": self.name,
                "response": f"I encountered an error while processing your request: {str(e)}",
                "execution_time": elapsed,
                "success": False,
                "error": str(e),
            }

    async def get_approved_agent_instance(self, target_agent_name: str, purpose: str) -> Optional['BaseAgent']:
        """
        Request approval from the Brain to use another agent.
        If approved, return the instance of the target agent. Otherwise return None.
        """
        self.log(f"Requesting Brain approval to use agent '{target_agent_name}' for task: {purpose[:60]}...")
        try:
            from brain import brain
        except ImportError:
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from brain import brain
            
        approved = await brain.approve_agent_delegation(
            requester_name=self.name,
            target_name=target_agent_name,
            purpose=purpose
        )
        if not approved:
            self.log(f"Brain DENIED request to use agent '{target_agent_name}'.", "WARNING")
            return None
            
        self.log(f"Brain APPROVED request to use agent '{target_agent_name}'.")
        from agents.agent_registry import agent_registry
        agent_instance = agent_registry.get_instance(target_agent_name)
        if agent_instance is None:
            try:
                import importlib
                import re
                module_name = re.sub(r'(?<!^)(?=[A-Z])', '_', target_agent_name).lower()
                try:
                    module = importlib.import_module(f"agents.{module_name}")
                except ImportError:
                    module = importlib.import_module(f"agents.sub_agents.{module_name}")
                agent_class = getattr(module, target_agent_name)
                agent_instance = agent_class()
            except Exception as e:
                self.log(f"Failed to instantiate agent '{target_agent_name}': {e}", "ERROR")
                return None
        return agent_instance

    async def use_agent(self, target_agent_name: str, message: str, context: Optional[dict] = None) -> dict:
        """
        Request approval from the central Brain to use another agent.
        If approved, run the target agent and return its response.
        """
        context = context or {}
        agent_instance = await self.get_approved_agent_instance(target_agent_name, message)
        if agent_instance is None:
            return {
                "agent": target_agent_name,
                "response": f"Delegation request to {target_agent_name} was denied by the central Brain.",
                "success": False,
                "error": "Delegation denied by central Brain."
            }
        try:
            return await agent_instance.run(message, context)
        except Exception as e:
            self.log(f"Error running delegated agent '{target_agent_name}': {e}", "ERROR")
            return {
                "agent": target_agent_name,
                "response": f"An error occurred while executing the delegated agent {target_agent_name}: {str(e)}",
                "success": False,
                "error": str(e)
            }

    def __repr__(self) -> str:
        return f"<{self.name}: {self.description}>"
