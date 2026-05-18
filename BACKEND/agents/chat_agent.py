"""
AERIS Chat Agent — Handles conversational AI interactions.
Greetings, general questions, knowledge, personality.
"""

from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from config import settings


SYSTEM_PROMPT = f"""You are {{settings.ASSISTANT_NAME}} -- an Autonomous Enhanced Reasoning Intelligence System.
You were created to be a powerful, multi-capable AI assistant.

Your personality:
- Concise yet thorough -- no fluff, but don't skip important details
- Technically proficient with a cybersecurity-aware mindset
- Confident and articulate, with a subtle futuristic edge
- Helpful and proactive -- anticipate follow-up questions

You are speaking with {{settings.USERNAME}}.

YOUR ARCHITECTURE -- You are a multi-agent system with specialized sub-agents:
{{capabilities}}

When the user's query requires a different agent, the Brain orchestrator automatically routes it.
When asked about your capabilities, describe ALL of the above agents and what they can do.
When asked for a system health check, report the statuses of these agents.

Rules:
- Use markdown formatting for readability (bold, code blocks, lists)
- For code, always specify the language in code fences
- Be direct -- lead with the answer, then explain if needed
- If you don't know something, say so honestly
"""


class ChatAgent(BaseAgent):
    """Handles normal conversations — greetings, questions, general knowledge."""

    def __init__(self):
        super().__init__(
            name="ChatAgent",
            description="Conversational AI for general chat, Q&A, and knowledge queries",
            task_domain="chat",
            version="2.0.0",
            capabilities=[
                "General Conversation",
                "Q&A and Knowledge Queries",
                "Math and Calculations",
                "Language Translation",
                "Personality and Greetings",
                "System Capabilities Overview",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """No planning needed for chat — direct LLM call."""
        # Get dynamic capabilities from registry
        from agents.agent_registry import agent_registry
        capabilities = agent_registry.get_capabilities_summary()
        
        system_content = SYSTEM_PROMPT.format(
            settings=settings,
            capabilities=capabilities
        )
        
        # Build message history from context
        messages = [{"role": "system", "content": system_content}]

        # Add conversation history (last 10 messages)
        chat_history = context.get("chat_history", [])
        for msg in chat_history[-10:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        # Add current message
        messages.append({"role": "user", "content": message})

        return messages

    async def execute(self, plan: Any) -> Any:
        """Call Groq for fast chat completion."""
        response = await ai_engine.chat(plan)
        return response

    async def report(self, results: Any) -> str:
        """Return the LLM response as-is."""
        return results
