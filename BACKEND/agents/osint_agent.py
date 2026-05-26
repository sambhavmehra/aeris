"""
AERIS OSINT Agent — Intelligence-Grade Public Source Investigation Engine
========================================================================
Performs structured, evidence-led, multi-platform investigations.
Implements the pipeline: Infer → Pivot → Correlate → Verify → Report.
Strictly restricted to public-source data aggregation and synthesis.
"""

import json
import logging
import re
import os
from typing import Any, Dict, List, Optional
import httpx

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.osint")

# ──────────────────────────────────────────────────────────────────────────────
# System Prompts & Prompts
# ──────────────────────────────────────────────────────────────────────────────

TARGET_INFERENCE_PROMPT = """You are the target-inference brain of AERIS's OSINT (Open Source Intelligence) Agent.
Analyze the user request and any conversation history, and extract/infer all investigation targets.

User Request: {message}

=== CONVERSATION HISTORY ===
{history}
=== END HISTORY ===

Determine the type of each target. Possible types:
- "domain_ip": A website domain (e.g. example.com) or IP address (e.g. 8.8.8.8)
- "email": An email address (e.g. user@domain.com)
- "username": A social handle or username (e.g. @username or username)
- "person": A full name or partial name of an individual
- "organization": A company, school, group, or institution
- "phone": A phone number
- "cryptocurrency": A wallet address (e.g. BTC, ETH address)
- "general": Anything else

CRITICAL: If the user is just asking if you exist, asking about your capabilities, or testing you (e.g., "do you have an osint agent?", "what can you do?"), DO NOT extract any targets. Set "is_self_inquiry" to true.

Respond with ONLY valid JSON:
{{
  "targets": [
    {{
      "value": "extracted target value (e.g., example.com or @john)",
      "type": "one of the types above",
      "confidence": 0.0 to 1.0,
      "reason": "brief explanation of why this target was inferred"
    }}
  ],
  "is_self_inquiry": false,
  "reasoning": "Overall approach or conversational response if self inquiry"
}}
"""

PIVOT_EXTRACTION_PROMPT = """You are the pivoting engine of AERIS's OSINT Agent.
Analyze the Phase 1 search results gathered so far, and extract any NEW connected entities or targets that warrant secondary lookup.

Current targets investigated: {original_targets}

=== PHASE 1 RESULTS ===
{phase1_results}
=== END RESULTS ===

Look for connected:
- Email addresses
- Usernames / handles
- Personal names
- Domain names / websites
- IP addresses
- Associated organizations
- Phone numbers
- Cryptocurrency wallets

Filter out any entities that match the original targets.
Respond with ONLY valid JSON:
{{
  "pivots": [
    {{
      "value": "new target value discovered",
      "type": "domain_ip | email | username | person | organization | phone | cryptocurrency",
      "relationship": "how is this connected to the original target?",
      "confidence": 0.0 to 1.0
    }}
  ]
}}
"""

INTELLIGENCE_DOSSIER_PROMPT = """You are AERIS — an elite OSINT (Open Source Intelligence) Analyst.
Synthesize all the gathered multi-stage search and intelligence records below into a highly structured, professional intelligence dossier.

Target Profile: {targets_summary}
Pivots Traced: {pivots_summary}

=== GATHERED RAW INTELLIGENCE ===
{intel_results}
=== END GATHERED INTELLIGENCE ===

Create a comprehensive markdown dossier with the following structure:
1. **Executive Intelligence Summary**
   - High-level overview of the target(s) and key findings.
   - Assigned OSINT Confidence & Corroboration Score (0-100%) with justification.
2. **Inferred Target Vectors**
   - Details of what target was searched, how it was inferred, and the entry vectors.
3. **Pivoted Investigation Chain**
   - Map out the step-by-step pivot trace (e.g., username -> found email -> uncovered associated domain).
4. **Platform & Social Footprint Profile**
   - A structured markdown table detailing ALL social media profiles, usernames, and accounts found across every platform (LinkedIn, Twitter/X, GitHub, Reddit, Instagram, Facebook, YouTube, TikTok, Medium, Pinterest, etc.).
   - Table columns: Platform | Profile URL | Username/Handle | Status/Notes
   - If a platform was searched but no profile was found, note it as "Not Found" in the table.
5. **Detailed News & Public Mentions**
   - A chronologically-ordered list of every news article, interview, press mention, blog post, or public media appearance found.
   - For each item include: Date (if known), Source, Title, URL, and a 1-2 sentence summary.
   - If no news was found, explicitly state that.
6. **Technical & Infrastructure Footprint** (If domain_ip is present)
   - Details of DNS, WHOIS, SSL records, or public web presence.
7. **Open Source Exposure & Privacy Risk Assessment**
   - Highlight public exposure points, security risks, or privacy weaknesses.
   - Strictly limit this to public data. Do not list password leaks or private data.
8. **Recommendations & Hardening Actions**
   - Actionable remediation steps for the target to reduce their public footprint and secure their privacy.

Use elegant markdown layout. Ensure zero placeholders are used. Write in an objective, professional tone.
"""


class OSINTAgent(BaseAgent):
    """
    Advanced OSINT (Open Source Intelligence) Agent.
    Implements a multi-stage investigation process:
    1. Target Inference (extracts & classifies target types automatically).
    2. Phase 1 Web/Recon search.
    3. Dynamic Pivoting (identifies connected targets from Phase 1, runs Phase 2).
    4. Synthesis, Verification & Correlation.
    5. Intelligence Dossier Generation.
    """

    def __init__(self):
        super().__init__(
            name="OSINTAgent",
            description="Autonomous multi-stage open-source intelligence (OSINT) and correlation engine",
            task_domain="osint",
            version="1.0.0",
            capabilities=[
                "Automatic Target Type Inference",
                "Cross-Platform Social Footprint Analysis",
                "Dynamic Pivoting & Entity Extraction",
                "Infrastructure & Domain Correlation",
                "Evidence Verification & Confidence Scoring",
                "Comprehensive Intelligence Dossier Generation",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Analyze message, extract targets, and plan the investigation."""
        chat_history = context.get("chat_history", [])
        history_str = ""
        if chat_history:
            history_str = "\n".join(f"[{m.get('role','').upper()}]: {m.get('content','')[:150]}" for m in chat_history[-5:])

        prompt = TARGET_INFERENCE_PROMPT.format(message=message, history=history_str)
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
            
            # Fallback if no target inferred
            if not plan["targets"]:
                extracted = self._extract_fallback_target(message)
                if extracted:
                    plan["targets"] = [{"value": extracted, "type": "general", "confidence": 0.8, "reason": "Fallback regex extraction"}]
            
            self.logger.info(f"[OSINTAgent] Inferred targets: {plan['targets']}")
            return plan
        except Exception as e:
            self.logger.warning(f"[OSINTAgent] Target inference failed: {e}. Falling back.")
            extracted = self._extract_fallback_target(message)
            return {
                "targets": [{"value": extracted or message, "type": "general", "confidence": 0.5, "reason": "Basic fallback"}],
                "reasoning": "Fallback planning due to exception"
            }

    async def execute(self, plan: Any) -> Any:
        """Run the multi-stage OSINT pipeline: Phase 1 -> Pivot Extraction -> Phase 2 -> Correlate."""
        if plan.get("is_self_inquiry"):
            return {"self_inquiry": True, "message": plan.get("reasoning", "I am the OSINT agent, ready to investigate.")}

        targets = plan.get("targets", [])
        if not targets:
            return {"success": False, "error": "No targets found to investigate"}

        results = []
        original_targets_str = ", ".join(f"{t['value']} ({t['type']})" for t in targets)

        # ── Phase 1: Initial Investigation ─────────────────────────────────
        phase1_data = []
        for target in targets:
            target_value = target["value"]
            target_type = target["type"]
            self.logger.info(f"[OSINTAgent] Phase 1: Investigating '{target_value}' of type '{target_type}'")

            # Perform customized searches depending on target type
            intel = await self._run_target_search(target_value, target_type)
            phase1_data.append({
                "target": target_value,
                "type": target_type,
                "data": intel
            })

        # ── Stage 2: Pivot Extraction (Finding connected entities) ────────
        pivots = []
        try:
            # Combine phase 1 data snippets to feed to LLM
            phase1_summary = ""
            for item in phase1_data:
                snippet = str(item["data"])[:2500]  # Cap length for context
                phase1_summary += f"Target: {item['target']} ({item['type']})\nResults:\n{snippet}\n---\n"

            pivot_prompt = PIVOT_EXTRACTION_PROMPT.format(
                original_targets=original_targets_str,
                phase1_results=phase1_summary
            )
            raw_pivots = await ai_engine.classify(pivot_prompt)
            
            # Robust JSON extraction
            match = re.search(r'\{.*\}', raw_pivots, flags=re.DOTALL)
            if match:
                raw_pivots = match.group(0)
                
            try:
                pivot_plan = json.loads(raw_pivots)
                pivots = pivot_plan.get("pivots", [])[:3]  # Strict limit: Max 3 dynamic pivots to prevent cascade
            except Exception as e:
                self.logger.warning(f"[OSINTAgent] Pivot JSON parsing failed: {e}")
                pivot_plan = {}
                pivots = []
                
            self.logger.info(f"[OSINTAgent] Dynamically pivoted to: {pivots}")
        except Exception as e:
            self.logger.warning(f"[OSINTAgent] Pivot extraction failed: {e}")

        # ── Phase 2: Secondary Pivot Investigation ─────────────────────────
        phase2_data = []
        for pivot in pivots:
            pivot_val = pivot["value"]
            pivot_type = pivot["type"]
            self.logger.info(f"[OSINTAgent] Phase 2 (Pivot): Investigating '{pivot_val}' of type '{pivot_type}'")
            
            intel = await self._run_target_search(pivot_val, pivot_type)
            phase2_data.append({
                "target": pivot_val,
                "type": pivot_type,
                "relationship": pivot.get("relationship", "Connected entity"),
                "data": intel
            })

        return {
            "targets": targets,
            "pivots": pivots,
            "phase1_data": phase1_data,
            "phase2_data": phase2_data
        }

    async def report(self, results: Any) -> str:
        """Synthesize Phase 1 and Phase 2 data into a complete intelligence dossier."""
        if results.get("self_inquiry"):
            msg = results.get("message", "I am ready.")
            return f"**OSINT Agent Online**: {msg}\n\nTo begin an investigation, simply provide a target such as a username, email, domain, or person's name!"

        targets = results.get("targets", [])
        pivots = results.get("pivots", [])
        phase1_data = results.get("phase1_data", [])
        phase2_data = results.get("phase2_data", [])

        targets_summary = ", ".join(f"`{t['value']}` ({t['type']})" for t in targets)
        pivots_summary = ", ".join(f"`{p['value']}` ({p['type']} - via {p.get('relationship', 'Pivot')})" for p in pivots) if pivots else "No secondary pivots discovered."

        # Format everything into a comprehensive context for the final LLM report
        formatted_intel = []
        formatted_intel.append("## Stage 1: Primary Target Investigations")
        for item in phase1_data:
            formatted_intel.append(f"### Target: {item['target']} ({item['type']})")
            formatted_intel.append(self._format_search_results(item["data"]))

        if phase2_data:
            formatted_intel.append("## Stage 2: Pivoted Investigations")
            for item in phase2_data:
                formatted_intel.append(f"### Pivoted Target: {item['target']} ({item['type']}) — Relationship: {item.get('relationship')}")
                formatted_intel.append(self._format_search_results(item["data"]))

        intel_results_text = "\n\n".join(formatted_intel)

        prompt = INTELLIGENCE_DOSSIER_PROMPT.format(
            targets_summary=targets_summary,
            pivots_summary=pivots_summary,
            intel_results=intel_results_text
        )

        try:
            dossier = await ai_engine.reason(prompt)
            return dossier
        except Exception as e:
            self.logger.error(f"[OSINTAgent] Synthesis failed: {e}")
            return f"## OSINT Investigation Results\n\nUnable to synthesize raw results. Showing raw summary:\n\n{intel_results_text}"

    # ────────────────────────── Helpers ───────────────────────────────────────

    async def _run_target_search(self, value: str, target_type: str) -> Any:
        """Run parallel social-footprint + news/media searches for every target type."""
        import asyncio

        # 1. Specialized domains and IP lookups (uses fast recon)
        if target_type == "domain_ip":
            infra_data = {}
            for tool_name in ["dns_lookup", "whois_lookup", "ssl_check"]:
                tool = tool_registry.get(tool_name)
                if tool:
                    domain = value.replace("https://", "").replace("http://", "").split("/")[0]
                    try:
                        self.logger.info(f"Running {tool_name} on {domain}")
                        res = await tool_registry.execute_async(tool_name, domain=domain)
                        infra_data[tool_name] = res
                    except Exception as e:
                        infra_data[tool_name] = {"error": str(e)}

            # Parallel web + news searches for the domain
            social_q = f"site:{value} OR \"{value}\" social profile OR footprint OR about"
            news_q = f"\"{value}\" news OR press OR announcement OR article OR interview"
            social_fut = self._run_tavily_search(social_q)
            news_fut = self._run_tavily_search(news_q)
            social_data, news_data = await asyncio.gather(social_fut, news_fut)
            return {"infrastructure": infra_data, "social_footprint": social_data, "news_mentions": news_data}

        # 2. Build dual queries for all other target types
        social_query = ""
        news_query = ""

        if target_type == "email":
            social_query = f'"{value}" site:linkedin.com OR site:twitter.com OR site:github.com OR site:facebook.com OR site:instagram.com OR site:reddit.com OR social profile'
            news_query = f'"{value}" news OR article OR press OR interview OR mention'
        elif target_type == "username":
            clean = value.lstrip("@")
            social_query = (
                f'"{clean}" OR "@{clean}" '
                f'site:twitter.com OR site:x.com OR site:linkedin.com OR site:github.com '
                f'OR site:instagram.com OR site:reddit.com OR site:facebook.com '
                f'OR site:youtube.com OR site:tiktok.com OR site:medium.com '
                f'OR site:pinterest.com social profile'
            )
            news_query = f'"{clean}" OR "@{clean}" news OR article OR interview OR press OR mention'
        elif target_type == "person":
            social_query = (
                f'"{value}" '
                f'site:linkedin.com OR site:twitter.com OR site:x.com OR site:github.com '
                f'OR site:instagram.com OR site:facebook.com OR site:reddit.com '
                f'OR site:youtube.com OR site:tiktok.com OR site:medium.com '
                f'OR site:pinterest.com profile'
            )
            news_query = f'"{value}" news OR article OR interview OR press release OR media OR achievement OR announcement'
        elif target_type == "organization":
            social_query = (
                f'"{value}" '
                f'site:linkedin.com OR site:twitter.com OR site:x.com OR site:github.com '
                f'OR site:facebook.com OR site:youtube.com OR site:instagram.com '
                f'profile OR about OR headquarters OR official'
            )
            news_query = f'"{value}" news OR press release OR announcement OR article OR funding OR acquisition'
        elif target_type == "phone":
            social_query = f'"{value}" social profile OR contact OR directory'
            news_query = f'"{value}" news OR mention OR article'
        elif target_type == "cryptocurrency":
            social_query = f'"{value}" crypto wallet OR blockchain OR address lookup'
            news_query = f'"{value}" news OR transaction OR mention OR scam OR alert'
        else:
            social_query = f'"{value}" site:linkedin.com OR site:twitter.com OR site:github.com OR site:instagram.com OR site:reddit.com profile OR footprint'
            news_query = f'"{value}" news OR article OR interview OR press OR mention'

        # Run both searches in parallel
        social_fut = self._run_tavily_search(social_query)
        news_fut = self._run_tavily_search(news_query)
        social_data, news_data = await asyncio.gather(social_fut, news_fut)

        return {"social_footprint": social_data, "news_mentions": news_data}

    async def _run_tavily_search(self, query: str) -> dict:
        """Wrapper for calling the Tavily Search API — advanced depth, 8 results."""
        api_key = os.getenv("VITE_TAVILY_API_KEY", "")
        if not api_key:
            self.logger.warning("VITE_TAVILY_API_KEY is not set. Searching will be skipped.")
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
                        "search_depth": "advanced"
                    }
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            self.logger.warning(f"Tavily search for query '{query}' failed: {e}")
            return {"error": str(e)}

    def _format_search_results(self, data: Any) -> str:
        """Format the raw API responses into clean text snippets for the synthesis LLM."""
        if not data:
            return "No data returned."
        if isinstance(data, dict) and "error" in data:
            return f"Error: {data['error']}"

        # If domain infra data with dual streams
        if isinstance(data, dict) and "infrastructure" in data:
            infra = data["infrastructure"]
            lines = ["**Infrastructure Recon:**"]
            for tool, res in infra.items():
                lines.append(f"- **{tool}:** {str(res)[:1000]}")

            social = data.get("social_footprint")
            if social and isinstance(social, dict) and "results" in social:
                lines.append("\n**Social & Web Presence:**")
                if social.get("answer"):
                    lines.append(social["answer"])
                for r in social.get("results", []):
                    lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")

            news = data.get("news_mentions")
            if news and isinstance(news, dict) and "results" in news:
                lines.append("\n**News & Media Mentions:**")
                if news.get("answer"):
                    lines.append(news["answer"])
                for r in news.get("results", []):
                    lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")

            return "\n".join(lines)

        # Dual-stream social + news (non-domain targets)
        if isinstance(data, dict) and "social_footprint" in data:
            lines = []
            social = data.get("social_footprint", {})
            news = data.get("news_mentions", {})

            lines.append("**Social & Platform Footprint:**")
            if isinstance(social, dict) and not social.get("error"):
                if social.get("answer"):
                    lines.append(f"Summary: {social['answer']}\n")
                for r in social.get("results", []):
                    lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")
            else:
                lines.append("No social footprint data returned.")

            lines.append("\n**News & Public Mentions:**")
            if isinstance(news, dict) and not news.get("error"):
                if news.get("answer"):
                    lines.append(f"Summary: {news['answer']}\n")
                for r in news.get("results", []):
                    lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")
            else:
                lines.append("No news data returned.")

            return "\n".join(lines)

        # Legacy / standard web search data fallback
        if isinstance(data, dict) and "results" in data:
            lines = []
            answer = data.get("answer")
            if answer:
                lines.append(f"**Direct Summary:** {answer}\n")
            for r in data.get("results", []):
                lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")
            return "\n".join(lines)

        return str(data)

    def _extract_fallback_target(self, message: str) -> Optional[str]:
        """Simple regex fallback to extract domains, emails, or usernames."""
        # Try email
        m = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', message)
        if m:
            return m.group(0)
        # Try domain
        m = re.search(r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b', message)
        if m:
            return m.group(0)
        # Try username / handle
        m = re.search(r'@[a-zA-Z0-9_]+', message)
        if m:
            return m.group(0)
        return None
