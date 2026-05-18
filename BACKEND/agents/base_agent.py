"""
AERIS Base Agent — Abstract blueprint that all sub-agents must follow.
Provides the think → execute → report orchestration pattern.
"""

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
        
        loop = asyncio.get_event_loop()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if loop.is_running():
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
            return asyncio.run(ai_engine.chat(messages, temperature=temperature, max_tokens=max_tokens))

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

    async def run(self, message: str, context: Optional[dict] = None) -> dict:
        """
        Full agent pipeline: think → execute → report.
        Returns a structured dict with response, timing, and metadata.
        """
        context = context or {}
        start = time.time()

        self.logger.info(f"▶ {self.name} processing: {message[:80]}...")

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

    def __repr__(self) -> str:
        return f"<{self.name}: {self.description}>"
