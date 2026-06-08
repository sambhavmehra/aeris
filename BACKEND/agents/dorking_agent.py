"""
AERIS Dorking Agent — Standalone Google Dorking Intelligence Agent
==================================================================
Builds advanced Google dork queries for legitimate OSINT discovery
and executes them independently via Tavily search API.

Can operate in two ways:
  1. Standalone: Brain routes "dorking" intent directly here (think → execute → report)
  2. Helper: OSINTAgent imports and calls build_queries() for its pipeline

Modes:
  - "normal": basic, high-signal queries
  - "hacker": advanced precision queries (still public info discovery)
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

logger = logging.getLogger("aeris.agent.dorking")

# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

DORKING_TARGET_PROMPT = """You are the target-inference module of AERIS's Dorking Agent.
Analyze the user's dorking request and extract what they want to search for.

User Request: {message}

=== CONVERSATION HISTORY ===
{history}
=== END HISTORY ===

Determine:
1. The search value (domain, email, username, person name, organization, keyword, etc.)
2. The target type: "domain_ip", "email", "username", "person", "organization", "phone", "cryptocurrency", or "general"
3. The dorking mode: "normal" or "hacker" (if user mentions advanced, hacker, deep, etc. use "hacker")
4. Any custom dork operators the user explicitly wants (e.g., filetype:pdf, intitle:"admin", etc.)

CRITICAL: If the user is just asking about dorking capabilities or testing, set "is_self_inquiry" to true.

Respond with ONLY valid JSON:
{{
  "targets": [
    {{
      "value": "the search target",
      "type": "one of the types above",
      "confidence": 0.0 to 1.0
    }}
  ],
  "mode": "normal or hacker",
  "custom_operators": "any extra dork operators the user explicitly mentioned, or empty string",
  "is_self_inquiry": false,
  "reasoning": "brief explanation"
}}
"""

DORKING_REPORT_PROMPT = """You are AERIS — an elite Google Dorking specialist.
Synthesize the raw search results below into a structured dorking intelligence report.

Dorking Queries Used:
{queries_used}

=== RAW SEARCH RESULTS ===
{raw_results}
=== END RESULTS ===

Create a professional markdown report with:
1. **Dorking Summary** — What queries were executed and why
2. **Key Findings** — Most important/interesting results discovered
3. **Social & Web Presence** — Any profiles, accounts, or footprints found
4. **Documents & Files** — Any exposed documents, PDFs, or data files
5. **News & Mentions** — Any relevant news or public mentions
6. **Exposure Assessment** — What information is publicly exposed
7. **Recommendations** — Actionable steps based on findings

Use elegant markdown. Be precise and evidence-based. Reference URLs where available.
"""


class DorkingAgent(BaseAgent):
    """
    Standalone Google Dorking Agent for AERIS.
    
    Builds Google dork query strings for legitimate OSINT discovery
    and executes them via Tavily search API.
    
    Can be used:
      - Standalone via Brain routing (think → execute → report)
      - As a helper via build_queries() called by OSINTAgent
    """

    def __init__(self):
        super().__init__(
            name="DorkingAgent",
            description="Google dorking specialist — builds and executes advanced search queries for public info discovery",
            task_domain="dorking",
            version="2.0.0",
            capabilities=[
                "Google Dork Query Building",
                "Advanced Search Operator Construction",
                "Multi-Platform Social Footprint Discovery",
                "Document & File Type Discovery",
                "News & Media Mention Search",
                "Standalone Dorking Execution",
                "Normal & Hacker Mode Queries",
            ],
        )
        # Conservative exclusions to reduce login/admin noise
        self._common_excludes = [
            "-login", "-signin", "-sign in", "-admin",
            "-administrator", "-password", "-reset",
            "-register", "-signup", "-cart", "-checkout",
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # BaseAgent Pipeline: think → execute → report
    # ──────────────────────────────────────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Analyze the user's dorking request and extract targets."""
        chat_history = context.get("chat_history", [])
        history_str = ""
        if chat_history:
            history_str = "\n".join(
                f"[{m.get('role','').upper()}]: {m.get('content','')[:150]}"
                for m in chat_history[-5:]
            )

        prompt = DORKING_TARGET_PROMPT.format(message=message, history=history_str)
        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            plan = json.loads(raw)
            plan.setdefault("targets", [])
            plan.setdefault("mode", "normal")
            plan.setdefault("custom_operators", "")

            # Default to hacker mode if global hacker_mode is enabled
            if context.get("hacker_mode") and plan.get("mode") == "normal":
                plan["mode"] = "hacker"

            # Fallback if no target inferred
            if not plan["targets"]:
                extracted = self._extract_fallback_target(message)
                if extracted:
                    plan["targets"] = [{
                        "value": extracted,
                        "type": "general",
                        "confidence": 0.8,
                    }]

            self.logger.info(f"[DorkingAgent] Targets: {plan['targets']}, Mode: {plan['mode']}")
            return plan
        except Exception as e:
            self.logger.warning(f"[DorkingAgent] Target inference failed: {e}")
            extracted = self._extract_fallback_target(message)
            return {
                "targets": [{"value": extracted or message, "type": "general", "confidence": 0.5}],
                "mode": "hacker" if context.get("hacker_mode") else "normal",
                "custom_operators": "",
                "reasoning": "Fallback due to exception",
            }

    async def execute(self, plan: Any) -> Any:
        """Build dork queries and execute them via Tavily."""
        if plan.get("is_self_inquiry"):
            return {
                "self_inquiry": True,
                "message": plan.get("reasoning", "I am the Dorking Agent, ready to execute advanced Google dork searches."),
            }

        targets = plan.get("targets", [])
        if not targets:
            return {"success": False, "error": "No targets found for dorking"}

        mode = plan.get("mode", "normal")
        custom_ops = plan.get("custom_operators", "")
        all_results = []

        for target in targets:
            value = target["value"]
            target_type = target["type"]
            self.logger.info(f"[DorkingAgent] Dorking '{value}' ({target_type}) in {mode} mode")

            # Build the dork queries
            social_query, news_query = self.build_queries(value, target_type, mode=mode)

            # Append custom operators if provided
            if custom_ops:
                social_query = f"{social_query} {custom_ops}"
                news_query = f"{news_query} {custom_ops}"

            # Build extra specialized queries for hacker mode
            extra_queries = []
            if mode == "hacker":
                extra_queries = self._build_extra_dork_queries(value, target_type)

            # Execute all queries via Tavily
            import asyncio
            tasks = [
                self._run_tavily_search(social_query),
                self._run_tavily_search(news_query),
            ]
            for eq in extra_queries:
                tasks.append(self._run_tavily_search(eq))

            results = await asyncio.gather(*tasks)

            result_entry = {
                "target": value,
                "type": target_type,
                "mode": mode,
                "queries": {
                    "social": social_query,
                    "news": news_query,
                    "extra": extra_queries,
                },
                "social_results": results[0],
                "news_results": results[1],
                "extra_results": results[2:] if len(results) > 2 else [],
            }
            all_results.append(result_entry)

        return {"targets": targets, "mode": mode, "results": all_results}

    async def report(self, results: Any) -> str:
        """Synthesize dorking results into a formatted intelligence report."""
        if results.get("self_inquiry"):
            capabilities = "\n".join(f"  • {c}" for c in self.capabilities)
            return (
                f"**🔍 Dorking Agent Online**\n\n"
                f"{results.get('message', '')}\n\n"
                f"**Capabilities:**\n{capabilities}\n\n"
                f"**Supported Target Types:** domain/IP, email, username, person, organization, phone, crypto wallet\n\n"
                f"**Modes:** `normal` (basic queries) | `hacker` (advanced operators + filetype + intitle/inurl/intext)\n\n"
                f"**Usage Examples:**\n"
                f"  • `dork example.com` — Domain dorking\n"
                f"  • `google dork @username hacker mode` — Advanced username search\n"
                f"  • `dork user@email.com` — Email footprint discovery\n"
                f"  • `advanced dork \"Company Name\"` — Organization intel\n"
            )

        if not results.get("results"):
            return "❌ No dorking results obtained."

        # Build formatted raw results and queries used
        queries_used_parts = []
        raw_results_parts = []

        for entry in results["results"]:
            target = entry["target"]
            ttype = entry["type"]
            mode = entry["mode"]

            queries_used_parts.append(f"**Target:** `{target}` ({ttype}) — Mode: {mode}")
            queries_used_parts.append(f"  • Social: `{entry['queries']['social'][:200]}`")
            queries_used_parts.append(f"  • News: `{entry['queries']['news'][:200]}`")
            for i, eq in enumerate(entry["queries"].get("extra", [])):
                queries_used_parts.append(f"  • Extra-{i+1}: `{eq[:200]}`")

            # Format social results
            raw_results_parts.append(f"### Social Footprint — {target}")
            raw_results_parts.append(self._format_tavily_results(entry["social_results"]))

            # Format news results
            raw_results_parts.append(f"### News & Mentions — {target}")
            raw_results_parts.append(self._format_tavily_results(entry["news_results"]))

            # Format extra results
            for i, extra in enumerate(entry.get("extra_results", [])):
                raw_results_parts.append(f"### Extra Query {i+1} — {target}")
                raw_results_parts.append(self._format_tavily_results(extra))

        queries_text = "\n".join(queries_used_parts)
        raw_text = "\n\n".join(raw_results_parts)

        # Cap context to prevent token limit overflow (Groq has 12k TPM limit)
        if len(raw_text) > 6000:
            raw_text = raw_text[:6000] + "\n\n... [Results truncated to fit token limits]"

        # Use LLM to synthesize into a professional report
        prompt = DORKING_REPORT_PROMPT.format(
            queries_used=queries_text,
            raw_results=raw_text,
        )

        try:
            report = await ai_engine.reason(prompt)
            return report
        except Exception as e1:
            self.logger.warning(f"[DorkingAgent] reason() failed: {e1}, trying classify()")
            try:
                report = await ai_engine.classify(prompt)
                return report
            except Exception as e2:
                self.logger.error(f"[DorkingAgent] All LLM calls failed: {e2}")
                return (
                    f"## 🔍 Dorking Results (Raw)\n\n"
                    f"**Queries Used:**\n{queries_text}\n\n"
                    f"**Results:**\n{raw_text}"
                )

    # ──────────────────────────────────────────────────────────────────────────
    # Query Building (also used by OSINTAgent as helper)
    # ──────────────────────────────────────────────────────────────────────────

    def _escape(self, s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip())

    def _exclusion_str(self) -> str:
        return " ".join(self._common_excludes)

    def _normalize_target(self, value: str, target_type: str) -> str:
        value = self._escape(value)
        if target_type == "username":
            return value.lstrip("@")
        return value

    def build_queries(self, value: str, target_type: str, mode: str = "normal") -> Tuple[str, str]:
        """
        Build a pair of Google dork queries for the given target.
        
        Returns:
          (social_query, news_query)
          
        This method is used both standalone and by OSINTAgent.
        """
        mode = (mode or "normal").lower()
        if mode not in ("normal", "hacker"):
            mode = "normal"

        value = self._normalize_target(value, target_type)
        excludes = self._exclusion_str()

        # ---------- Normal mode (basic) ----------
        if mode == "normal":
            social_query = ""
            news_query = ""

            if target_type == "domain_ip":
                social_query = f'site:{value} OR "{value}" social profile OR footprint OR about'
                news_query = f'"{value}" news OR press OR announcement OR article OR interview'
                return social_query, news_query

            if target_type == "email":
                social_query = (
                    f'"{value}" (site:linkedin.com/in/ OR site:twitter.com OR site:github.com '
                    f'OR site:facebook.com OR site:instagram.com OR site:reddit.com/user/) social profile'
                )
                news_query = f'"{value}" news OR article OR press OR interview OR mention'
                return social_query.strip(), news_query.strip()

            if target_type == "username":
                clean = value
                social_query = (
                    f'"{clean}" OR "@{clean}" '
                    f'(site:twitter.com/{clean} OR site:x.com/{clean} OR site:linkedin.com/in/{clean} OR site:github.com/{clean} '
                    f'OR site:instagram.com/{clean} OR site:reddit.com/user/{clean} OR site:facebook.com/{clean} '
                    f'OR site:youtube.com/@{clean} OR site:tiktok.com/@{clean} OR site:medium.com/@{clean})'
                )
                news_query = f'"{clean}" OR "@{clean}" news OR article OR interview OR press OR mention'
                return social_query.strip(), news_query.strip()

            if target_type == "person":
                social_query = (
                    f'"{value}" '
                    f'(site:linkedin.com/in/ OR site:twitter.com OR site:x.com OR site:github.com '
                    f'OR site:instagram.com OR site:facebook.com OR site:reddit.com/user/ '
                    f'OR site:medium.com/@) profile'
                )
                news_query = f'"{value}" news OR article OR interview OR "press release" OR media OR achievement OR announcement'
                return social_query.strip(), news_query.strip()

            if target_type == "organization":
                social_query = (
                    f'"{value}" '
                    f'(site:linkedin.com/company/ OR site:twitter.com OR site:x.com OR site:github.com) '
                    f'profile OR about OR headquarters OR official'
                )
                news_query = f'"{value}" news OR "press release" OR announcement OR article OR funding OR acquisition'
                return social_query.strip(), news_query.strip()

            if target_type == "phone":
                social_query = f'"{value}" social profile OR contact OR directory'
                news_query = f'"{value}" news OR mention OR article'
                return social_query.strip(), news_query.strip()

            if target_type == "cryptocurrency":
                social_query = f'"{value}" crypto wallet OR blockchain OR address lookup'
                news_query = f'"{value}" news OR transaction OR mention OR scam OR alert'
                return social_query.strip(), news_query.strip()

            # fallback
            social_query = f'"{value}" (site:linkedin.com/in/ OR site:twitter.com OR site:github.com OR site:instagram.com OR site:reddit.com/user/) profile OR footprint'
            news_query = f'"{value}" news OR article OR interview OR press OR mention'
            return social_query.strip(), news_query.strip()

        # ---------- Hacker mode (advanced precision) ----------
        intitle = f'intitle:"{value}"'
        inurl = f'inurl:"{value}"'
        intext = f'intext:"{value}"'
        time_bias = ' after:2020-01-01 '

        # Advanced site lists
        twitter_sites = "site:twitter.com OR site:x.com"
        github_sites = "site:github.com"
        linkedin_sites = "site:linkedin.com"
        reddit_sites = "site:reddit.com"
        instagram_sites = "site:instagram.com"
        youtube_sites = "site:youtube.com"
        medium_sites = "site:medium.com"
        pinterest_sites = "site:pinterest.com"
        facebook_sites = "site:facebook.com"
        tiktok_sites = "site:tiktok.com"

        if target_type == "domain_ip":
            social_query = (
                f'({inurl} OR {intitle} OR {intext}) '
                f'site:{value} OR site:about.{value} OR "{value}" '
                f'("social" OR "profile" OR "footprint" OR "contact") {excludes}'
            )
            news_query = (
                f'("{value}" OR {intitle} OR {intext}) '
                f'(news OR press OR announcement OR article OR interview) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        if target_type == "email":
            social_query = (
                f'"{value}" '
                f'(site:linkedin.com/in/ OR {twitter_sites} OR {github_sites} OR {facebook_sites} OR {instagram_sites} OR site:reddit.com/user/) '
                f'("profile" OR "contact" OR "about" OR "email") '
                f'({inurl} OR {intext}) {excludes}'
            )
            news_query = (
                f'"{value}" '
                f'(news OR article OR press OR interview OR mention) '
                f'({intitle} OR {intext}) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        if target_type == "username":
            clean = value
            social_query = (
                f'("@{clean}" OR "{clean}") '
                f'(site:twitter.com/{clean} OR site:x.com/{clean} OR site:linkedin.com/in/{clean} OR site:github.com/{clean} '
                f'OR site:instagram.com/{clean} OR site:reddit.com/user/{clean} OR site:facebook.com/{clean} '
                f'OR site:youtube.com/@{clean} OR site:tiktok.com/@{clean} OR site:medium.com/@{clean} OR {pinterest_sites}) '
                f'("profile" OR "account" OR "handle" OR "bio" OR "about") '
                f'({inurl} OR {intext}) {excludes}'
            )
            news_query = (
                f'("@{clean}" OR "{clean}") '
                f'(news OR article OR interview OR press OR mention) '
                f'({intitle} OR {intext}) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        if target_type == "person":
            social_query = (
                f'"{value}" '
                f'(site:linkedin.com/in/ OR site:linkedin.com/pub/ OR site:twitter.com/ OR site:x.com/ OR site:github.com/ '
                f'OR site:instagram.com/ OR site:facebook.com/ OR site:reddit.com/user/ OR site:medium.com/@) '
                f'("profile" OR "bio" OR "about" OR "contact" OR "speaker") '
                f'{excludes}'
            )
            news_query = (
                f'"{value}" '
                f'(news OR article OR interview OR "press release" OR "media" OR achievement OR announcement) '
                f'({intitle} OR {intext}) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        if target_type == "organization":
            social_query = (
                f'"{value}" '
                f'(site:linkedin.com/company/ OR site:twitter.com OR site:x.com OR site:github.com OR site:facebook.com) '
                f'("official" OR "about" OR "headquarters" OR "profile" OR "careers") '
                f'({inurl} OR {intext}) {excludes}'
            )
            news_query = (
                f'"{value}" '
                f'(("press release" OR announcement OR funding OR acquisition OR news) '
                f'OR filetype:pdf OR filetype:doc OR filetype:xls) '
                f'({intext} OR {intitle}) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        if target_type == "phone":
            social_query = (
                f'"{value}" '
                f'("contact" OR "phone" OR "call" OR "call us") '
                f'({inurl} OR {intext}) '
                f'(site:linkedin.com/in/ OR {twitter_sites} OR {facebook_sites} OR {instagram_sites} OR site:reddit.com/user/) '
                f'{excludes}'
            )
            news_query = (
                f'"{value}" (news OR mention OR article OR "contact us") '
                f'({intext} OR {intitle}) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        if target_type == "cryptocurrency":
            social_query = (
                f'"{value}" '
                f'(wallet OR "public address" OR blockchain OR explorer) '
                f'({inurl} OR {intext}) {excludes}'
            )
            news_query = (
                f'"{value}" (news OR transaction OR mention OR scam OR alert OR investigation) '
                f'({intext} OR {intitle}) {excludes} {time_bias}'
            )
            return social_query.strip(), news_query.strip()

        # fallback advanced
        social_query = (
            f'"{value}" '
            f'(site:linkedin.com/in/ OR {twitter_sites} OR {github_sites} OR {instagram_sites} OR site:reddit.com/user/) '
            f'("profile" OR "about" OR "footprint") {excludes}'
        )
        news_query = f'"{value}" (news OR article OR interview OR press OR mention) {excludes} {time_bias}'
        return social_query.strip(), news_query.strip()

    # ──────────────────────────────────────────────────────────────────────────
    # Extra Hacker-Mode Dork Queries (standalone feature)
    # ──────────────────────────────────────────────────────────────────────────

    def _build_extra_dork_queries(self, value: str, target_type: str) -> List[str]:
        """Build additional specialized dork queries for hacker mode."""
        extras = []
        value = self._escape(value)

        if target_type == "domain_ip":
            # Exposed documents
            extras.append(f'site:{value} filetype:pdf OR filetype:doc OR filetype:docx OR filetype:xls OR filetype:xlsx OR filetype:csv OR filetype:txt')
            # Directory listings
            extras.append(f'site:{value} intitle:"index of" OR intitle:"directory listing"')
            # Config / backup / log files
            extras.append(f'site:{value} filetype:log OR filetype:conf OR filetype:env OR filetype:bak OR filetype:sql OR filetype:ini OR filetype:yaml')
            # Subdomains
            extras.append(f'site:*.{value} -www')

        elif target_type == "email":
            # Pastes and leaks (public)
            extras.append(f'"{value}" site:pastebin.com OR site:ghostbin.co OR site:dpaste.org OR site:controlc.com OR "paste"')
            # Leak indicators
            extras.append(f'"{value}" filetype:txt OR filetype:csv OR filetype:log "password" OR "hash" OR "leak"')

        elif target_type == "organization":
            # Public documents
            extras.append(f'"{value}" filetype:pdf OR filetype:xlsx OR filetype:docx OR filetype:pptx "confidential" OR "internal" OR "proprietary" OR "salary" OR "budget"')
            # Employee profiles
            extras.append(f'"{value}" site:linkedin.com/company/ OR site:linkedin.com/in/ employees OR team OR staff OR founder')
            # Login endpoints
            extras.append(f'site:{value} inurl:login OR inurl:admin OR inurl:portal OR inurl:dashboard OR inurl:wp-login')

        elif target_type == "person":
            # Resumes / CVs
            extras.append(f'"{value}" filetype:pdf OR filetype:doc OR filetype:docx "resume" OR "cv" OR "curriculum vitae"')
            # Academic / publications
            extras.append(f'"{value}" site:scholar.google.com OR site:researchgate.net OR site:academia.edu')
            # Professional profiles
            extras.append(f'"{value}" site:crunchbase.com OR site:zoominfo.com OR site:bloomberg.com/profile OR site:pitchbook.com')
            # Public records
            extras.append(f'"{value}" "public record" OR "court" OR "case" OR "filing" OR "judgement"')

        elif target_type == "username":
            clean = value.lstrip("@")
            # Code repositories
            extras.append(f'"{clean}" site:github.com OR site:gitlab.com OR site:bitbucket.org OR site:gitea.com')
            # Forum presence
            extras.append(f'"{clean}" site:stackoverflow.com OR site:quora.com OR site:news.ycombinator.com OR site:dev.to')
            # Pastes and dumps
            extras.append(f'"{clean}" site:pastebin.com OR site:ghostbin.co OR site:dpaste.org OR site:controlc.com')

        return extras

    # ──────────────────────────────────────────────────────────────────────────
    # Tavily Search Execution
    # ──────────────────────────────────────────────────────────────────────────

    async def _run_tavily_search(self, query: str) -> dict:
        """Execute a search query via Tavily API."""
        api_key = os.getenv("VITE_TAVILY_API_KEY", "")
        if not api_key:
            self.logger.warning("VITE_TAVILY_API_KEY is not set. Search skipped.")
            return {"error": "Tavily API key not set"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": 8,
                        "include_answer": True,
                        "search_depth": "advanced",
                    },
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            self.logger.warning(f"Tavily search failed for: '{query[:80]}': {e}")
            return {"error": str(e)}

    # ──────────────────────────────────────────────────────────────────────────
    # Formatting Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _format_tavily_results(self, data: dict) -> str:
        """Format Tavily API response into readable markdown."""
        if not data:
            return "No data returned."
        if isinstance(data, dict) and "error" in data:
            return f"⚠️ Error: {data['error']}"

        lines = []
        answer = data.get("answer")
        if answer:
            lines.append(f"**Summary:** {answer}\n")

        for r in data.get("results", []):
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            content = r.get("content", "")[:300]
            lines.append(f"- [{title}]({url}): {content}")

        return "\n".join(lines) if lines else "No results found."

    def _extract_fallback_target(self, message: str) -> Optional[str]:
        """Simple regex and string-cleaning fallback to extract targets from message."""
        # Try email
        m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
        if m:
            return m.group(0)
        # Try domain
        m = re.search(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', message)
        if m:
            return m.group(0)
        # Try username
        m = re.search(r'@[a-zA-Z0-9_]+', message)
        if m:
            return m.group(0)
            
        # Clean string for names/general terms by stripping common command verbs
        words = message.split()
        skip_words = {
            "dork", "dorking", "google", "search", "find", "lookup", "check", "scan",
            "hacker", "mode", "advanced", "deep", "karo", "kar", "please", "do", "run",
            "execute", "osint", "investigate", "who", "is", "profile", "information",
            "info", "details", "recon", "target", "about", "me", "show"
        }
        filtered = [w for w in words if w.lower().strip("?,.!:;\"'") not in skip_words]
        if filtered:
            return " ".join(filtered)
        return None
