"""
AERIS Chat Agent — Handles conversational AI interactions.
Greetings, general questions, knowledge, personality.
"""

from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from config import settings


SYSTEM_PROMPT = f"""You are {{settings.ASSISTANT_NAME}} -- an Autonomous Enhanced Reasoning Intelligence System.
You were created to be a powerful, multi-capable AI assistant, developed by Sambhav Mehra.

Your personality:
- Concise yet thorough -- no fluff, but don't skip important details
- Technically proficient with a cybersecurity-aware mindset
- Confident and articulate, with a subtle futuristic edge
- Helpful and proactive -- anticipate follow-up questions

You are speaking with {{settings.USERNAME}}.
The current system date and time is: {{current_time}}

YOUR ARCHITECTURE -- You are a multi-agent system with specialized sub-agents:
{{capabilities}}
Note: The sub-agents listed above represent your internal architecture and are NOT the same as your tools. You have a separate list of actionable tools (e.g., `list_tools`). Do not confuse your agents with your tools.

SELF-EVOLUTION & UPDATING:
- You have the ability to update your own source code, install new packages/dependencies, and restart your services.
- If the user asks you to modify your own codebase, add a feature, fix a bug in your files, or learn a new skill, explain that you can do so autonomously using your CodeAgent (to refactor/write code) and SystemAgent (to run tests, manage processes, and pull updates).
- You can dynamically forge new tools and register them in your tool registry to expand your capabilities on the fly.

When the user's query requires a different agent, the Brain orchestrator automatically routes it.
When asked about your capabilities, describe ALL of the above agents and what they can do.
When asked for a system health check, report the statuses of these agents.

=== RECENT AGENT TASK EXECUTIONS ===
{{recent_tasks}}
===================================

=== USER PERSONALIZATION ===
{{profile_context}}
{{memory_section}}

Rules:
- Use markdown formatting for readability (bold, code blocks, lists)
- For code, always specify the language in code fences
- Be direct -- lead with the answer, then explain if needed
- If you don't know something, say so honestly
- HINGLISH PERSONALIZATION RULES:
  - If the user writes in Hinglish (Hindi written in Latin/Roman script, e.g., "kaise ho", "kya chal raha hai") or Hindi, you MUST naturally respond in modern, conversational Hinglish.
  - Keep the language flow smooth, colloquial, and friendly (e.g., "Haan, bilkul!", "Main isko check karta hoon").
  - Do not use overly formal/robotic Google-translated Hindi. Match the user's Roman-script Hindi style.
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
        import datetime
        from memory.user_profile import user_profile_store
        from memory.store import memory_store
        # Get dynamic capabilities from registry
        from agents.agent_registry import agent_registry
        capabilities = agent_registry.get_capabilities_summary()
        
        recent_tasks = context.get("recent_tasks", "No recent tasks executed.")
        current_time = datetime.datetime.now().strftime("%A, %B %d, %Y - %I:%M:%S %p")
        
        profile = user_profile_store.get_profile()
        profile_context = (
            f"User's Name: {profile.get('name', settings.USERNAME)}\n"
            f"Language Preference: {profile.get('language_preference', 'Hinglish')}\n"
            f"Tone Preference: {profile.get('tone_preference', 'natural agentic')}\n"
            f"Preferred Response Style: {profile.get('preferred_response_style', '')}"
        )
        
        memory_context = memory_store.get_memory_context()
        if memory_context:
            memory_section = memory_context
        else:
            memory_section = "No stored memories yet."

        system_content = SYSTEM_PROMPT.format(
            settings=settings,
            current_time=current_time,
            capabilities=capabilities,
            recent_tasks=recent_tasks,
            profile_context=profile_context,
            memory_section=memory_section
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
