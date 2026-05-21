"""
AERIS — Research Agent (Sub-Agent)
==========================================
Specialized agent for web research, information gathering, and knowledge synthesis.
Uses Tavily (realtime search) and LLM summarisation to produce structured research.

Inherits from BaseAgent → gets APIGateway, logging, and memory for free.
Does NOT modify any existing agent or engine file.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer

logger = logging.getLogger("AerisResearchAgent")

RESEARCH_SYSTEM_PROMPT = """You are AERIS's Research Agent — a specialised AI researcher.

CAPABILITIES:
- Synthesise web search results into structured, actionable intelligence
- Extract key facts, statistics, and relevant data points
- Compare multiple sources and identify consensus vs. conflicting info
- Produce research briefs that other agents (Coding, Analysis) can act on

RULES:
1. Be FACTUAL — only use information from the provided search results.
2. Cite sources when possible (include URLs).
3. Structure your output as JSON:
   {{
     "summary": "Concise 2-3 sentence summary",
     "key_findings": ["finding1", "finding2", ...],
     "sources": [{{"title": "...", "url": "...", "relevance": "high|medium|low"}}],
     "recommendations": ["action1", "action2", ...],
     "raw_data": "Full detailed analysis if needed"
   }}
4. If the search results are insufficient, say so honestly.
5. Do NOT hallucinate facts not present in search results.
"""


class ResearchAgent(BaseAgent):
    """
    Specialised sub-agent for web research and information synthesis.
    Uses Tavily via the APIGateway for live web search, then summarises
    findings with LLM intelligence.
    """

    def __init__(self, memory_agent=None):
        super().__init__(name="ResearchAgent", memory_agent=memory_agent)

    def process(self, objective: str, context: SharedContextBuffer = None,
                **kwargs) -> Dict[str, Any]:
        """
        Research a topic by searching the web and synthesising results.

        Args:
            objective: The research query / topic.
            context: SharedContextBuffer for multi-agent collaboration.

        Returns:
            {"status": "success"|"error", "result": {...structured research...}}
        """
        self.log(f"Researching: {objective[:80]}")

        try:
            # Step 1: Web search via APIGateway → Tavily
            search_results = self._web_search(objective)

            # Step 2: Synthesise with LLM
            synthesis = self._synthesise(objective, search_results)

            # Post to shared context
            if context:
                context.post(
                    sender=self.name,
                    content=synthesis,
                    message_type="result",
                    task="research",
                )

            self.log("Research completed successfully.")
            return {"status": "success", "result": synthesis}

        except Exception as e:
            error_msg = f"Research agent failed: {e}"
            self.log(error_msg, "ERROR")
            if context:
                context.post(self.name, error_msg, message_type="error")
            return {"status": "error", "error": error_msg}

    def quick_search(self, query: str,
                     context: SharedContextBuffer = None) -> Dict[str, Any]:
        """Perform a quick web search and return raw results."""
        try:
            results = self._web_search(query)
            if context:
                context.post(self.name, results, message_type="result", task="quick_search")
            return {"status": "success", "result": results}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def deep_research(self, topic: str, num_queries: int = 3,
                      context: SharedContextBuffer = None) -> Dict[str, Any]:
        """
        Perform deep research by generating multiple sub-queries,
        searching each, and synthesising all results.
        """
        self.log(f"Deep research on: {topic[:60]} ({num_queries} sub-queries)")

        try:
            # Step 1: Generate sub-queries via LLM
            sub_queries = self._generate_sub_queries(topic, num_queries)

            # Step 2: Search each sub-query
            all_results = {}
            for q in sub_queries:
                try:
                    all_results[q] = self._web_search(q)
                except Exception as e:
                    all_results[q] = f"Search failed: {e}"

            # Step 3: Synthesise everything
            synthesis = self._synthesise_deep(topic, all_results)

            if context:
                context.post(self.name, synthesis, message_type="result", task="deep_research")

            return {"status": "success", "result": synthesis}

        except Exception as e:
            error_msg = f"Deep research failed: {e}"
            self.log(error_msg, "ERROR")
            return {"status": "error", "error": error_msg}

    # ── Internal Helpers ─────────────────────────────────────────────

    def _web_search(self, query: str) -> Dict[str, Any]:
        """Search the web via Tavily directly."""
        import os
        import httpx
        api_key = os.getenv("VITE_TAVILY_API_KEY", "")
        if not api_key:
            raise RuntimeError("VITE_TAVILY_API_KEY not set in environment.")
        
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": 5,
                        "include_answer": True,
                        "search_depth": "basic",
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            self.log(f"Tavily search failed for '{query}': {e}", "ERROR")
            return {"results": [], "answer": f"Error: {e}"}

    def _synthesise(self, objective: str, search_data: Dict[str, Any]) -> Any:
        """Use LLM to synthesise search results into structured research."""
        answer = search_data.get("answer", "")
        results = search_data.get("results", [])

        context_parts = []
        if answer:
            context_parts.append(f"Direct answer: {answer}")
        for r in results[:7]:
            title = r.get("title", "")
            content = r.get("content", "")[:400]
            url = r.get("url", "")
            context_parts.append(f"[{title}]({url}): {content}")

        search_context = "\n".join(context_parts)

        user_prompt = (
            f"Research query: {objective}\n\n"
            f"Search results:\n{search_context}\n\n"
            f"Synthesise these results into a structured JSON research brief."
        )

        raw = self._llm_call(RESEARCH_SYSTEM_PROMPT, user_prompt,
                             temperature=0.2, max_tokens=1024)
        return self._parse_json(raw)

    def _generate_sub_queries(self, topic: str, n: int) -> list:
        """Generate multiple search sub-queries for deep research."""
        prompt = (
            f"Generate exactly {n} specific search queries to deeply research this topic:\n"
            f"'{topic}'\n\n"
            f"Return ONLY a JSON array of strings. Example: [\"query1\", \"query2\"]"
        )
        raw = self._llm_call(
            "You generate search queries. Return ONLY a JSON array.",
            prompt, temperature=0.3, max_tokens=256,
        )
        try:
            queries = json.loads(raw.strip())
            if isinstance(queries, list):
                return queries[:n]
        except Exception:
            pass
        return [topic]

    def _synthesise_deep(self, topic: str, all_results: Dict[str, Any]) -> Any:
        """Synthesise results from multiple sub-queries."""
        context_parts = []
        for query, data in all_results.items():
            context_parts.append(f"\n--- Sub-query: {query} ---")
            if isinstance(data, dict):
                answer = data.get("answer", "")
                if answer:
                    context_parts.append(f"Answer: {answer}")
                for r in data.get("results", [])[:3]:
                    context_parts.append(
                        f"[{r.get('title', '')}]({r.get('url', '')}): "
                        f"{r.get('content', '')[:200]}"
                    )
            else:
                context_parts.append(str(data)[:300])

        combined = "\n".join(context_parts)
        user_prompt = (
            f"Deep research topic: {topic}\n\n"
            f"Combined search results from {len(all_results)} sub-queries:\n"
            f"{combined}\n\n"
            f"Synthesise ALL findings into a comprehensive JSON research brief."
        )

        raw = self._llm_call(RESEARCH_SYSTEM_PROMPT, user_prompt,
                             temperature=0.2, max_tokens=1536)
        return self._parse_json(raw)

    @staticmethod
    def _parse_json(raw: str) -> Any:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return cleaned
