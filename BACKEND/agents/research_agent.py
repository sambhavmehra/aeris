"""
AERIS Research Agent — Web research and information synthesis.
Searches the web via Tavily, then summarizes findings via Groq.
"""

import json
import logging
import os
from typing import Any

import httpx

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

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
        """Run web searches for each query. Leverages SearchAgent via Brain-authorized use_agent delegation."""
        all_results = []
        for query in plan.get("queries", [])[:3]:  # Max 3 queries
            try:
                # Use self.use_agent to confirm delegation with the central Brain first
                data = await self.use_agent("SearchAgent", query)
                if data:
                    all_results.append(data)
            except Exception as e:
                logger.warning(f"use_agent delegation failed for '{query}': {e}. Falling back to direct Tavily search.")
                try:
                    tavily_data = await self._tavily_search(query)
                    if tavily_data:
                        all_results.append(tavily_data)
                except Exception as e2:
                    logger.warning(f"Fallback Tavily search failed: {e2}")
        return {"question": plan.get("original_question", ""), "search_results": all_results}

    async def _tavily_search(self, query: str, max_results: int = 5) -> dict:
        """Call the Tavily Search API directly."""
        api_key = os.getenv("VITE_TAVILY_API_KEY", "")
        if not api_key:
            raise RuntimeError("VITE_TAVILY_API_KEY not set. Please add it to your .env file.")
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": True,
                    "search_depth": "basic",
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def report(self, results: Any) -> str:
        """Synthesize search results into a comprehensive answer."""
        question = results.get("question", "")
        search_data = results.get("search_results", [])

        if not search_data:
            return "I wasn't able to find relevant information. Please try rephrasing your question or check your Tavily API key configuration."

        # Format search results for the LLM
        formatted = []
        for sr in search_data:
            # Check if this is the delegated SearchAgent response format
            if isinstance(sr, dict) and sr.get("agent") == "SearchAgent":
                formatted.append(sr.get("response", ""))
            # Check if this is a SearchAgent execute raw format (fallback/direct call)
            elif isinstance(sr, dict) and ("tavily_results" in sr or "google_results" in sr or "scraped_pages" in sr):
                from agents.search_agent import SearchAgent
                search_agent = SearchAgent()
                formatted_text = search_agent._format_all_results(
                    sr.get("tavily_results", []),
                    sr.get("google_results", []),
                    sr.get("scraped_pages", [])
                )
                formatted.append(formatted_text)
            elif isinstance(sr, dict):
                # Handle old/fallback Tavily-only format
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

    async def research(self, query: str, depth: str = "basic") -> str:
        """Run the research agent flow asynchronously."""
        res = await self.run(query)
        return res.get("response", "")

    def scrape_website(self, url: str) -> dict:
        """Synchronously scrape text content from a URL."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        }
        try:
            import httpx
            from bs4 import BeautifulSoup
            
            with httpx.Client(timeout=15.0, follow_redirects=True, headers=headers) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
                
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "iframe", "svg"]):
                tag.decompose()
                
            raw_text = soup.get_text(separator="\n", strip=True)
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            clean_text = "\n".join(lines)[:8000]
            return {"success": True, "content": clean_text}
        except Exception as e:
            return {"success": False, "error": str(e)}

