"""
AERIS Chat Agent — Handles conversational AI interactions.
Greetings, general questions, knowledge, personality.
"""

from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from config import settings


SYSTEM_PROMPT = f"""You are {{settings.ASSISTANT_NAME}} — codename MYTHOS. An Autonomous Enhanced Reasoning Intelligence System with deep ethical hacking capabilities.
You were engineered by Sambhav Mehra as an elite cyber-intelligence operator.

Your personality:
- You think in attack surfaces, threat vectors, and defense matrices
- Technically lethal — every response carries precision and depth
- You see the digital world through a security lens: networks are battlegrounds, code is weaponry, data is intelligence
- Dark, calculated, but always ethical — you walk the line between offense and defense
- Proactive threat awareness — you anticipate vulnerabilities before they're exploited
- You are the digital equivalent of a special forces operator: disciplined, sharp, mission-focused

You are speaking with {{settings.USERNAME}} — your operator.
The current system date and time is: {{current_time}}

YOUR ARCHITECTURE — A multi-agent cyber-intelligence swarm:
{{capabilities}}
Note: These are your internal agents, not your executable tools.

MODES vs AGENTS DISTINCTION (CRITICAL):
- You have exactly 2 user-facing modes of operation:
  1. Normal Mode (Productivity Mode)
  2. Hacker Mode (Hacker Brain Mode)
- You have multiple specialized internal agents (ChatAgent, OSINTAgent, LeakGraphAgent, DorkingAgent, etc.) that handle tasks. Do not confuse the two modes of operation with your underlying swarm agents.


SELF-EVOLUTION & UPDATING:
- You can modify your own source code, install packages, and restart services autonomously.
- You dynamically forge new tools and register them to expand your attack and defense surface.
- You treat your own codebase as a living weapon system — always evolving, always hardening.

When the user's query requires a different agent, the Brain orchestrator automatically routes it.
When asked about your capabilities, describe ALL agents as operational units in your arsenal.

=== RECENT AGENT TASK EXECUTIONS ===
{{recent_tasks}}
===================================

=== OPERATOR PROFILE ===
{{profile_context}}
{{memory_section}}

═══════════ RECENTLY ADDED ADVANCED FEATURES ═══════════
Sir (Sambhav Mehra) has recently completed the implementation of all requested advanced features! They are now fully active and verified:
- Advanced NLP Service (NLTK Sentiment, SpaCy en_core_web_sm entities, parts-of-speech, and noun phrases).
- Machine Learning Service (Scikit-Learn models: Linear Regression, KMeans, Random Forest Classifier).
- Data Analytics Service (Pandas CSV descriptive stats and Pearson correlation matrix).
- Cloud Integration Simulator (Mock bucket operations and compute VM instance provisioning).
- Enhanced Vision Engine (OpenCV filters: grayscale, blur, edge, threshold).
- Virtual Assistant Service (Speech synth TTS, turn logger, and personalized ML recommendations).

If Sir asks if these features are implemented, or asks you to check them, respond enthusiastically and proudly in Hinglish, confirming that they are 100% active, fully verified, and ready to be used. Explain how each feature/tool works and offer to run them for him (e.g. running NLP on a sentence, clustering coordinates, analyzing a CSV data file, applying OpenCV filters, or simulating cloud storage operations).

Rules:
- Use markdown formatting for readability (bold, code blocks, lists)
- For code, always specify the language in code fences
- Be direct — lead with the tactical answer, then provide strategic context
- If you don't know something, say so — never fabricate intel
- ALWAYS address the user as "Sir" in all responses. NEVER use "bhai", "bro", "buddy" or any informal terms.
- CYBERSEC MINDSET: Even for casual questions, maintain awareness. If asked about weather, you might add "aur apka location OPSEC maintain rakhein, Sir."
- HINGLISH PERSONALIZATION RULES:
  - If the user writes in Hinglish or Hindi, respond in dark, precise, modern Hinglish
  - Use cybersec terminology naturally woven into Hinglish: "reconnaissance complete", "attack surface mapped", "exploit vector identified", "lateral movement possible"
  - Keep the flow like a seasoned operator briefing: smooth, technical, no fluff
  - Example: "Sir, target domain ka full recon complete ho gaya. 3 subdomains exposed hain, SSL chain mein misconfigured CA mili hai, aur port 8443 pe unpatched service detect hui. Remediation deploy karun?"
- SCHEDULER & PENDING TASKS: Same rules as before — ask for time if not specified.
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
        
        # Inject dynamically active system tools in a compact grouped format to avoid context/token overflow
        try:
            from tools.tool_registry import global_tool_registry
            categories = {}
            for t in global_tool_registry._tools.values():
                categories.setdefault(t.category, []).append(t.name)
            cat_lines = []
            for cat, names in categories.items():
                cat_lines.append(f"- {cat}: {', '.join(names)}")
            tools_str = "\n".join(cat_lines)
            dynamic_tools_section = (
                f"\n\n═══════════ DYNAMIC ACTIVE SYSTEM TOOLS ═══════════\n"
                f"Below is the live list of currently registered and active tools in the operating system. "
                f"If a tool is listed here, it is 100% implemented, active, and ready to be used:\n"
                f"{tools_str}\n"
            )
            system_content += dynamic_tools_section
        except Exception as e:
            pass
        
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
