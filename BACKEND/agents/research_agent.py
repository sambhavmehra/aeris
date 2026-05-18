"""
AERIS Research Agent — Web research and information synthesis.
Searches the web via Tavily, then summarizes findings via Groq.
"""

import json
import logging
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.research")

SYNTHESIS_PROMPT = """You are AERIS, an advanced research AI. Synthesize the following search results into a comprehensive, well-structured answer.

User's question: {question}

Search results:
{results}

Rules:
- Provide a direct, clear answer first
- Use markdown formatting (headers, bullets, bold)
- Cite sources with [Source Title](URL) format
- If results are insufficient, say what's missing
- Be thorough but concise
- Include relevant quotes or data points when available
"""


class ResearchAgent(BaseAgent):
    """Searches the web and synthesizes findings into structured answers."""

    def __init__(self):
        super().__init__(
            name="ResearchAgent",
            description="Web research — searches the internet, scrapes pages, and synthesizes information",
            task_domain="research",
            version="2.0.0",
            capabilities=[
                "Web Search (Tavily)",
                "Current Events and News",
                "Data Synthesis and Summarization",
                "Multi-query Research",
                "Source Citation",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Determine search queries from the user's message."""
        # Use LLM to extract optimal search query
        try:
            raw = await ai_engine.classify(
                f"Extract the best web search query from this user message. "
                f"Respond with ONLY JSON: {{\"query\": \"optimized search query\", \"follow_up\": [\"optional additional query\"]}}\n\n"
                f"User message: {message}"
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            plan = json.loads(raw)
            return {"queries": [plan.get("query", message)] + plan.get("follow_up", []),
                    "original_question": message}
        except Exception:
            return {"queries": [message], "original_question": message}

    async def execute(self, plan: Any) -> Any:
        """Run web searches for each query."""
        all_results = []
        for query in plan.get("queries", [])[:3]:  # Max 3 queries
            result = await tool_registry.execute("web_search", {"query": query, "max_results": 5})
            if result.get("status") == "success":
                all_results.append(result.get("data", {}))
        return {"question": plan.get("original_question", ""), "search_results": all_results}

    async def report(self, results: Any) -> str:
        """Synthesize search results into a comprehensive answer."""
        question = results.get("question", "")
        search_data = results.get("search_results", [])

        if not search_data:
            return "I wasn't able to find relevant information. Please try rephrasing your question or check your Tavily API key configuration."

        # Format search results for the LLM
        formatted = []
        for sr in search_data:
            answer = sr.get("answer", "")
            if answer:
                formatted.append(f"**Direct Answer:** {answer}\n")
            for r in sr.get("results", []):
                formatted.append(f"- [{r.get('title','')}]({r.get('url','')}): {r.get('content','')}")

        results_text = "\n".join(formatted)
        prompt = SYNTHESIS_PROMPT.format(question=question, results=results_text)

        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS, a research synthesis AI."},
                {"role": "user", "content": prompt},
            ], max_tokens=2048)
        except Exception:
            return f"## Research Results\n\n{results_text}"
