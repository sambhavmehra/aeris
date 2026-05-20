"""
AERIS Search Agent — Realtime Web Intelligence Engine
======================================================
Provides multi-source realtime search using:
  • Tavily Search API       — deep semantic search
  • Google Search           — traditional web search via googlesearch-python
  • BeautifulSoup Scraper   — direct page content extraction
  • Cross-agent delegation  — hands off to Security/Research agents if needed

Pipeline: think → execute → report
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

logger = logging.getLogger("aeris.agent.search")

# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

PLAN_PROMPT = """You are the planner for AERIS's realtime Search Agent.
Analyze the user's message and decide the best search strategy.

User request: {message}

Respond with ONLY valid JSON (no markdown):
{{
  "queries": ["primary search query", "optional follow-up query"],
  "search_depth": "basic | advanced",
  "scrape_urls": [],
  "delegate_to": null,
  "topic": "general | news | finance | science | security",
  "needs_live_data": true,
  "reason": "brief explanation"
}}

RULES:
- queries: 1-3 targeted queries derived from the request
- search_depth: "advanced" for research/technical; "basic" for quick facts
- scrape_urls: list specific URLs to scrape if user references a page; else []
- delegate_to: "security" if the topic involves hacking/recon/vulnerabilities;
               "research" if deep academic synthesis is needed;
               null for everything else (default)
- topic: classify the subject area
- needs_live_data: true if the answer requires up-to-date internet data
"""

SYNTHESIS_PROMPT = """You are AERIS — an advanced AI with realtime internet access.
Synthesize ALL the search results below into a comprehensive, well-structured answer.

Original question: {question}

=== SEARCH RESULTS ===
{results}
=== END RESULTS ===

Format your response using markdown:
- Start with a **direct answer** (1-2 sentences)
- Use headers (##), bullet points, and bold for key facts
- Cite sources as [Source Title](URL)
- Include relevant data points, numbers, or quotes
- End with a **Quick Summary** section if the answer is long
- If data is missing or outdated, state it explicitly
"""

SCRAPE_SUMMARY_PROMPT = """You are AERIS. A web page has been scraped — extract and summarize the most relevant content.

User question: {question}
Source URL: {url}
Page title: {title}

Raw page content (first 3000 chars):
{content}

Provide:
1. A concise summary of what this page contains
2. Key facts, data, or quotes directly relevant to the question
3. Any important links or references mentioned
Keep it to 200-300 words.
"""

# ──────────────────────────────────────────────────────────────────────────────
# SearchAgent
# ──────────────────────────────────────────────────────────────────────────────

class SearchAgent(BaseAgent):
    """
    Realtime internet search agent.
    Sources: Tavily API → Google CSE → BeautifulSoup scraper
    Supports cross-agent delegation to SecurityAgent or ResearchAgent.
    """

    # Tavily settings
    TAVILY_URL = "https://api.tavily.com/search"
    TAVILY_MAX_RESULTS = 6

    GOOGLE_MAX_RESULTS = 5

    # Scraper settings
    SCRAPE_TIMEOUT = 12.0
    SCRAPE_MAX_CHARS = 8000

    def __init__(self):
        super().__init__(
            name="SearchAgent",
            description=(
                "Realtime internet search — Tavily deep search, Google CSE, "
                "web scraping, and cross-agent intelligence routing"
            ),
            task_domain="search",
            version="1.0.0",
            capabilities=[
                "Realtime Web Search (Tavily)",
                "Google Search Integration",
                "Web Page Scraping & Content Extraction",
                "Multi-source Result Synthesis",
                "Cross-Agent Delegation (Security / Research)",
                "News & Trending Topics",
                "Live Data Retrieval",
                "Deep Search with Source Citations",
                "Topic Classification & Query Expansion",
            ],
        )
        self._tavily_key: str = os.getenv("VITE_TAVILY_API_KEY", "")

    # ─────────────────────────── Think ────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Use LLM to build a search plan from the user's message."""
        try:
            raw = await ai_engine.classify(
                PLAN_PROMPT.format(message=message)
            )
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            plan = json.loads(raw)
            plan.setdefault("queries", [message])
            plan.setdefault("search_depth", "basic")
            plan.setdefault("scrape_urls", [])
            plan.setdefault("delegate_to", None)
            plan.setdefault("topic", "general")
            plan.setdefault("needs_live_data", True)
            plan["original_question"] = message
            logger.info(
                f"[SearchAgent] Plan → queries={plan['queries']}, "
                f"depth={plan['search_depth']}, delegate={plan['delegate_to']}"
            )
            return plan
        except Exception as e:
            logger.warning(f"[SearchAgent] think() fallback: {e}")
            return {
                "queries": [message],
                "search_depth": "basic",
                "scrape_urls": [],
                "delegate_to": None,
                "topic": "general",
                "needs_live_data": True,
                "original_question": message,
            }

    # ─────────────────────────── Execute ──────────────────────────────────────

    async def execute(self, plan: Any) -> Any:
        """Run all search sources in parallel and collect results."""
        question   = plan.get("original_question", "")
        queries    = plan.get("queries", [question])[:3]
        depth      = plan.get("search_depth", "basic")
        scrape_urls = plan.get("scrape_urls", [])
        delegate_to = plan.get("delegate_to")

        # ── Cross-agent delegation ─────────────────────────────────────────
        if delegate_to in ("security", "research"):
            delegated = await self._delegate(delegate_to, question)
            return {
                "question": question,
                "delegated_to": delegate_to,
                "delegated_response": delegated,
                "tavily_results": [],
                "google_results": [],
                "scraped_pages": [],
            }

        # ── Parallel search tasks ──────────────────────────────────────────
        tavily_tasks = [self._tavily_search(q, depth) for q in queries]
        google_tasks = [self._google_search(q) for q in queries[:2]]  # limit Google calls
        scrape_tasks = [self._scrape_page(url, question) for url in scrape_urls[:3]]

        all_results = await asyncio.gather(
            *tavily_tasks, *google_tasks, *scrape_tasks,
            return_exceptions=True
        )

        n_tavily = len(tavily_tasks)
        n_google = len(google_tasks)

        tavily_results: List[dict] = []
        google_results: List[dict] = []
        scraped_pages:  List[dict] = []

        for i, res in enumerate(all_results):
            if isinstance(res, Exception):
                logger.warning(f"[SearchAgent] Source {i} failed: {res}")
                continue
            if i < n_tavily:
                tavily_results.append(res)
            elif i < n_tavily + n_google:
                google_results.append(res)
            else:
                scraped_pages.append(res)

        # ── Auto-scrape top Tavily URLs for richer content ─────────────────
        if depth == "advanced" and tavily_results:
            top_urls = self._extract_top_urls(tavily_results, limit=3)
            extra_scrapes = await asyncio.gather(
                *[self._scrape_page(u, question) for u in top_urls],
                return_exceptions=True
            )
            for res in extra_scrapes:
                if not isinstance(res, Exception) and res:
                    scraped_pages.append(res)

        return {
            "question": question,
            "delegated_to": None,
            "delegated_response": None,
            "tavily_results": tavily_results,
            "google_results": google_results,
            "scraped_pages": scraped_pages,
        }

    # ─────────────────────────── Report ───────────────────────────────────────

    async def report(self, results: Any) -> str:
        """Synthesize all collected data into a rich, cited answer."""
        question  = results.get("question", "")
        delegated = results.get("delegated_to")

        # If we delegated to another agent, return that response directly
        if delegated and results.get("delegated_response"):
            return (
                f"> 🔄 **Delegated to {delegated.capitalize()}Agent for specialized processing.**\n\n"
                + results["delegated_response"]
            )

        tavily  = results.get("tavily_results", [])
        google  = results.get("google_results", [])
        scraped = results.get("scraped_pages", [])

        if not tavily and not google and not scraped:
            return (
                "⚠️ **No search results found.**\n\n"
                "Possible reasons:\n"
                "- API keys missing (`VITE_TAVILY_API_KEY`, `GOOGLE_API_KEY`)\n"
                "- Network issue or rate limit\n"
                "- Query too vague — try rephrasing\n\n"
                "Please check your `.env` and retry."
            )

        formatted = self._format_all_results(tavily, google, scraped)

        try:
            synthesis = await ai_engine.chat(
                [
                    {"role": "system", "content": "You are AERIS, a realtime research AI."},
                    {"role": "user", "content": SYNTHESIS_PROMPT.format(
                        question=question,
                        results=formatted,
                    )},
                ],
                max_tokens=2048,
            )
            return synthesis
        except Exception as e:
            logger.error(f"[SearchAgent] Synthesis LLM failed: {e}")
            return f"## Search Results for: {question}\n\n{formatted}"

    # ─────────────────────────── Tavily ───────────────────────────────────────

    async def _tavily_search(self, query: str, depth: str = "basic") -> dict:
        """Call Tavily Search API."""
        if not self._tavily_key:
            raise RuntimeError("VITE_TAVILY_API_KEY not set in .env")

        payload = {
            "api_key": self._tavily_key,
            "query": query,
            "max_results": self.TAVILY_MAX_RESULTS,
            "include_answer": True,
            "include_raw_content": depth == "advanced",
            "search_depth": depth,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(self.TAVILY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"[SearchAgent][Tavily] '{query}' → {len(data.get('results', []))} results")
            return {"source": "tavily", "query": query, "data": data}

    # ─────────────────────────── Google Search (Library) ───────────────────────

    async def _google_search(self, query: str) -> dict:
        """Call Google Search via the googlesearch-python library."""
        def run_search():
            from googlesearch import search
            results = []
            try:
                # Use advanced=True to get title, url, and description
                for r in search(query, num_results=self.GOOGLE_MAX_RESULTS, advanced=True):
                    results.append({
                        "title": r.title,
                        "link": r.url,
                        "snippet": getattr(r, "description", getattr(r, "snippet", ""))
                    })
            except Exception as e:
                logger.warning(f"[SearchAgent][Google] Library search failed: {e}")
            return {"items": results}
            
        try:
            data = await asyncio.to_thread(run_search)
            items = data.get("items", [])
            logger.info(f"[SearchAgent][Google] '{query}' → {len(items)} results")
            return {"source": "google", "query": query, "data": data}
        except Exception as e:
            logger.warning(f"[SearchAgent][Google] '{query}' exception: {e}")
            return {"source": "google", "query": query, "data": {"items": []}}

    # ─────────────────────────── Scraper ──────────────────────────────────────

    async def _scrape_page(self, url: str, question: str) -> dict:
        """Scrape a URL and extract meaningful text content."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.SCRAPE_TIMEOUT,
                follow_redirects=True,
                headers=headers,
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text

            soup = BeautifulSoup(html, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header",
                              "aside", "form", "noscript", "iframe", "svg"]):
                tag.decompose()

            title = soup.title.string.strip() if soup.title else urlparse(url).netloc

            # Prefer main content areas
            main = (
                soup.find("main")
                or soup.find("article")
                or soup.find(id=re.compile(r"content|main|article", re.I))
                or soup.find(class_=re.compile(r"content|article|post|entry", re.I))
                or soup.body
            )
            raw_text = (main or soup).get_text(separator="\n", strip=True)

            # Collapse blank lines
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            clean_text = "\n".join(lines)[: self.SCRAPE_MAX_CHARS]

            # Use LLM to summarize relevance
            summary = await ai_engine.chat(
                [
                    {"role": "system", "content": "You are AERIS, a web content analyst."},
                    {"role": "user", "content": SCRAPE_SUMMARY_PROMPT.format(
                        question=question,
                        url=url,
                        title=title,
                        content=clean_text,
                    )},
                ],
                max_tokens=512,
            )

            logger.info(f"[SearchAgent][Scraper] Scraped: {url} ({len(clean_text)} chars)")
            return {
                "source": "scraper",
                "url": url,
                "title": title,
                "summary": summary,
                "char_count": len(clean_text),
            }

        except httpx.HTTPStatusError as e:
            return {"source": "scraper", "url": url, "error": f"HTTP {e.response.status_code}"}
        except Exception as e:
            logger.warning(f"[SearchAgent][Scraper] Failed {url}: {e}")
            return {"source": "scraper", "url": url, "error": str(e)}

    # ─────────────────────────── Cross-Agent Delegation ───────────────────────

    async def _delegate(self, agent_key: str, message: str) -> str:
        """
        Delegate a message to another AERIS agent by key.
        Supported: 'security', 'research'
        """
        try:
            from agents.agent_registry import agent_registry

            # Try registry first
            agent_map = {
                "security": "SecurityAgent",
                "research": "ResearchAgent",
            }
            registered_name = agent_map.get(agent_key)
            agent_instance = None

            if registered_name:
                agent_instance = agent_registry.get_instance(registered_name)

            # Fallback: direct import
            if agent_instance is None:
                if agent_key == "security":
                    from agents.security_agent import SecurityAgent
                    agent_instance = SecurityAgent()
                elif agent_key == "research":
                    from agents.research_agent import ResearchAgent
                    agent_instance = ResearchAgent()

            if agent_instance is None:
                return f"⚠️ Could not delegate to {agent_key} agent."

            logger.info(f"[SearchAgent] Delegating to {agent_key}Agent: {message[:80]}")
            result = await agent_instance.run(message, {})
            return result.get("response", "No response from delegated agent.")

        except Exception as e:
            logger.error(f"[SearchAgent] Delegation to '{agent_key}' failed: {e}")
            return f"⚠️ Delegation to {agent_key} agent failed: {str(e)}"

    # ─────────────────────────── Helpers ──────────────────────────────────────

    def _extract_top_urls(self, tavily_results: List[dict], limit: int = 3) -> List[str]:
        """Extract the top-scored URLs from Tavily results for deep scraping."""
        urls = []
        for batch in tavily_results:
            items = batch.get("data", {}).get("results", [])
            for item in items:
                u = item.get("url", "")
                if u and u not in urls:
                    # Skip PDFs, large files, social media
                    if not any(skip in u for skip in [".pdf", "twitter.com", "facebook.com", "instagram.com"]):
                        urls.append(u)
                if len(urls) >= limit:
                    break
            if len(urls) >= limit:
                break
        return urls

    def _format_all_results(
        self,
        tavily: List[dict],
        google: List[dict],
        scraped: List[dict],
    ) -> str:
        """Flatten all sources into a single readable text block for the LLM."""
        parts: List[str] = []

        # Tavily
        for batch in tavily:
            data = batch.get("data", {})
            q    = batch.get("query", "")
            if answer := data.get("answer"):
                parts.append(f"**[Tavily Direct Answer for '{q}']**: {answer}\n")
            for r in data.get("results", []):
                title   = r.get("title", "No Title")
                url     = r.get("url", "")
                content = r.get("content", "")[:400]
                score   = r.get("score", 0)
                parts.append(f"- [{title}]({url}) (score={score:.2f}): {content}")

        # Google
        for batch in google:
            data  = batch.get("data", {})
            q     = batch.get("query", "")
            items = data.get("items", [])
            if items:
                parts.append(f"\n**[Google Results for '{q}']**")
            for item in items:
                title   = item.get("title", "No Title")
                url     = item.get("link", "")
                snippet = item.get("snippet", "")[:400]
                parts.append(f"- [{title}]({url}): {snippet}")

        # Scraped
        for page in scraped:
            if page.get("error"):
                continue
            title   = page.get("title", page.get("url", "Unknown"))
            url     = page.get("url", "")
            summary = page.get("summary", "")
            parts.append(f"\n**[Scraped: {title}]({url})**\n{summary}")

        return "\n".join(parts) if parts else "No results collected."
