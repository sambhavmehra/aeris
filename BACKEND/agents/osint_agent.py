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
from agents.dorking_agent import DorkingAgent
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
- "person": A full name or partial name of an individual. VERY IMPORTANT: If the user provides additional context about the person (such as their company, location, title, or age, e.g. "John Doe from Google" or "Jane Smith in Seattle"), capture the core name as the value, but ALSO capture a "qualifiers" field containing those distinguishing terms.
- "organization": A company, school, group, or institution
- "phone": A phone number
- "cryptocurrency": A wallet address (e.g. BTC, ETH address)
- "general": Anything else

CRITICAL: If the user is just asking if you exist, asking about your capabilities, or testing you (e.g., "do you have an osint agent?", "what can you do?"), DO NOT extract any targets. Set "is_self_inquiry" to true.

Respond with ONLY valid JSON:
{{
  "targets": [
    {{
      "value": "extracted target value (e.g., example.com or John Doe)",
      "type": "one of the types above",
      "confidence": 0.0 to 1.0,
      "reason": "brief explanation of why this target was inferred",
      "qualifiers": "any company, location, role, or other context keywords (e.g. 'Google' or 'Seattle \"software engineer\"'), or empty string"
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

CRITICAL VERIFICATION GUIDELINES:
1. ONLY extract a pivot if there is clear, explicit evidence linking it directly to the target (e.g. "John's email is john@work.com" or a profile page explicitly linking to a Twitter handle).
2. DO NOT extract unrelated names, domains, or companies that just happen to appear in navigation footers, copyright notices, sidebar links, ads, or generic articles.
3. If no high-confidence connected entities are found, return an empty list.

Filter out any entities that match the original targets.
Respond with ONLY valid JSON:
{{
  "pivots": [
    {{
      "value": "new target value discovered",
      "type": "domain_ip | email | username | person | organization | phone | cryptocurrency",
      "relationship": "how is this connected to the original target? (be specific)",
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

CRITICAL OSINT GUIDELINES (ENTITY RESOLUTION & CORRELATION):
1. **Verify Identity & Resolve Names**: Carefully analyze the search results for common names or ambiguous targets. Determine if they describe multiple different individuals (e.g., matching name but different locations, occupations, or company affiliations).
2. **Handle Multiple Candidates**: If the raw data contains profiles/information for multiple different people sharing the same name:
   - DO NOT merge them into one hallucinated profile.
   - List them explicitly as separate candidates (e.g., "Candidate A (Software Engineer in NY)", "Candidate B (Doctor in London)").
   - Identify which candidate is the most likely target and explain why.
3. **Cross-Correlate Evidence**: Document how different data points are linked (e.g., "The Twitter account is linked to the GitHub account because they share the same unique username and profile bio").
4. **Attribution and Confidence**: Explain the confidence in attributing each social profile or record to the primary target.

Create a comprehensive markdown dossier with the following structure:
1. **Executive Intelligence Summary**
   - High-level overview of the target(s) and key findings.
   - Assigned OSINT Confidence & Corroboration Score (0-100%) with justification.
   - **Identity Correlation Note**: Explicitly detail if this is a common/ambiguous name and how you resolved/distinguished candidates.
2. **Inferred Target Vectors**
   - Details of what target was searched, how it was inferred, and the entry vectors.
3. **Pivoted Investigation Chain**
   - Map out the step-by-step pivot trace (e.g., username -> found email -> uncovered associated domain).
4. **Platform & Social Footprint Profile**
   - A structured markdown table detailing ALL social media profiles, usernames, and accounts found across every platform.
   - Table columns: Platform | Profile URL | Username/Handle | Attribution Confidence | Status/Notes
   - Group the table by Candidate if multiple possible targets were resolved.
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
            plan["hacker_mode"] = context.get("hacker_mode", False) or context.get("mode") == "hacker"
            
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
                "reasoning": "Fallback planning due to exception",
                "hacker_mode": context.get("hacker_mode", False) or context.get("mode") == "hacker"
            }

    async def execute(self, plan: Any) -> Any:
        """Run the multi-stage OSINT pipeline: Phase 1 -> Pivot Extraction -> Phase 2 -> Correlate."""
        if plan.get("is_self_inquiry"):
            return {"self_inquiry": True, "message": plan.get("reasoning", "I am the OSINT agent, ready to investigate.")}

        targets = plan.get("targets", [])
        if not targets:
            return {"success": False, "error": "No targets found to investigate"}

        from engine.state_manager import global_state_manager
        import asyncio
        global_state_manager.current_hud = "webweaver"

        try:
            results = []
            # Mode affects which Google dork templates are generated for social/news queries.
            mode = "hacker" if plan.get("hacker_mode") or plan.get("mode") == "hacker" else "normal"
            dork_agent = DorkingAgent()
            original_targets_str = ", ".join(f"{t['value']} ({t['type']})" for t in targets)

            # ── Phase 1: Initial Investigation ─────────────────────────────────
            phase1_data = []
            for target in targets:
                target_value = target["value"]
                target_type = target["type"]
                self.logger.info(f"[OSINTAgent] Phase 1: Investigating '{target_value}' of type '{target_type}'")

                # Perform customized searches depending on target type
                intel = await self._run_target_search(target_value, target_type, mode=mode, dork_agent=dork_agent, target=target)
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
                
                intel = await self._run_target_search(pivot_val, pivot_type, mode=mode, dork_agent=dork_agent, target=pivot)
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
        finally:
            await asyncio.sleep(15)
            if global_state_manager.current_hud == "webweaver":
                global_state_manager.current_hud = None

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

    def _build_tavily_queries(self, value: str, target_type: str) -> tuple[str, str]:
        """Build simple, high-signal queries optimized for Tavily's search parser."""
        value = (value or "").strip()
        if target_type == "person":
            social_query = f'"{value}" social media profiles LinkedIn Twitter GitHub Facebook Instagram'
            news_query = f'"{value}" news articles public mentions interviews publications'
        elif target_type == "email":
            social_query = f'"{value}" social media profile footprint accounts'
            news_query = f'"{value}" public database leaks mentions news'
        elif target_type == "username":
            clean = value.lstrip("@")
            social_query = f'"{clean}" social media profiles accounts LinkedIn Twitter GitHub'
            news_query = f'"{clean}" public mentions posts news articles'
        elif target_type == "domain_ip":
            social_query = f'"{value}" site overview social profiles about contact'
            news_query = f'"{value}" news mentions press releases announcements'
        elif target_type == "organization":
            social_query = f'"{value}" official website company profiles LinkedIn Twitter GitHub'
            news_query = f'"{value}" news articles announcements funding press releases'
        elif target_type == "phone":
            social_query = f'"{value}" contact info owner name directory'
            news_query = f'"{value}" spam reports public mentions comments'
        elif target_type == "cryptocurrency":
            social_query = f'"{value}" wallet address details blockchain owner'
            news_query = f'"{value}" transaction history scam hacks mentions'
        else:
            social_query = f'"{value}" social profile web presence footprint'
            news_query = f'"{value}" news mentions articles posts'
            
        return social_query, news_query

    async def _run_target_search(self, value: str, target_type: str, mode: str = "normal", dork_agent: Optional[DorkingAgent] = None, target: Optional[dict] = None) -> Any:
        """Run parallel social-footprint + news/media searches for every target type, with dorking and qualifiers."""
        import asyncio

        # 1. Specialized domains and IP lookups (uses fast recon)
        infra_data = {}
        if target_type == "domain_ip":
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

        # 2. Extract context qualifiers
        qualifiers = target.get("qualifiers", "") if isinstance(target, dict) else ""

        # 3. Build queries (use advanced dorks if dork_agent is present)
        if dork_agent:
            social_query, news_query = dork_agent.build_queries(value, target_type, mode=mode)
            extra_queries = dork_agent._build_extra_dork_queries(value, target_type) if mode == "hacker" else []
        else:
            social_query, news_query = self._build_tavily_queries(value, target_type)
            extra_queries = []

        if qualifiers:
            # Append qualifiers to narrow down the target context
            social_query = f"{social_query} {qualifiers}"
            news_query = f"{news_query} {qualifiers}"
            extra_queries = [f"{eq} {qualifiers}" for eq in extra_queries]

        self.logger.info(f"[OSINTAgent] Executing queries:\nSocial: {social_query}\nNews: {news_query}")
        if extra_queries:
            self.logger.info(f"[OSINTAgent] Hacker extra queries: {extra_queries}")

        # Run both searches (and extra dorks) in parallel
        hacker_mode = (mode == "hacker")
        tasks = [
            self._run_tavily_search(social_query, hacker_mode=hacker_mode),
            self._run_tavily_search(news_query, hacker_mode=hacker_mode)
        ]
        for eq in extra_queries:
            tasks.append(self._run_tavily_search(eq, hacker_mode=hacker_mode))

        completed = await asyncio.gather(*tasks)
        social_data = completed[0]
        news_data = completed[1]
        extra_data = completed[2:] if len(completed) > 2 else []

        result = {
            "social_footprint": social_data,
            "news_mentions": news_data,
            "dork_queries": {
                "social": social_query,
                "news": news_query,
                "extra": extra_queries
            }
        }
        if extra_data:
            result["extra_dorks"] = extra_data

        if target_type == "domain_ip":
            result["infrastructure"] = infra_data

        return result

    async def _run_tavily_search(self, query: str, hacker_mode: bool = False) -> dict:
        """Wrapper for calling the Tavily Search API — advanced depth, 8 results."""
        api_key = os.getenv("VITE_TAVILY_API_KEY", "")
        if not api_key:
            self.logger.warning("VITE_TAVILY_API_KEY is not set. Searching will be skipped.")
            return {"error": "Tavily API key not set"}

        try:
            from utils.stealth import configure_client_stealth
            client_kwargs = {"timeout": 30.0}
            client_kwargs = configure_client_stealth(client_kwargs, hacker_mode=hacker_mode, is_api=True)
            
            async with httpx.AsyncClient(**client_kwargs) as client:
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

        lines = []

        # 1. Print queries used
        if isinstance(data, dict) and "dork_queries" in data:
            dq = data["dork_queries"]
            lines.append("**Dork Queries Executed:**")
            lines.append(f"- Social Dork: `{dq['social']}`")
            lines.append(f"- News Dork: `{dq['news']}`")
            for i, eq in enumerate(dq.get("extra", [])):
                lines.append(f"- Extra Dork {i+1}: `{eq}`")
            lines.append("")

        # If domain infra data with dual streams
        if isinstance(data, dict) and "infrastructure" in data:
            infra = data["infrastructure"]
            lines.append("**Infrastructure Recon:**")
            for tool, res in infra.items():
                lines.append(f"- **{tool}:** {str(res)[:1000]}")

        # Social footprint
        social = data.get("social_footprint") if isinstance(data, dict) else None
        if social and isinstance(social, dict) and "results" in social:
            lines.append("\n**Social & Web Presence:**")
            if social.get("answer"):
                lines.append(social["answer"])
            for r in social.get("results", []):
                lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")

        # News mentions
        news = data.get("news_mentions") if isinstance(data, dict) else None
        if news and isinstance(news, dict) and "results" in news:
            lines.append("\n**News & Media Mentions:**")
            if news.get("answer"):
                lines.append(news["answer"])
            for r in news.get("results", []):
                lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")

        # Extra dork results (for hacker mode)
        extra_dorks = data.get("extra_dorks") if isinstance(data, dict) else None
        if extra_dorks and isinstance(extra_dorks, list):
            lines.append("\n**Exposed Files, Directory Listings & Pastes (Advanced Dorking):**")
            for idx, res in enumerate(extra_dorks):
                if isinstance(res, dict) and "results" in res:
                    for r in res.get("results", []):
                        lines.append(f"- [{r.get('title')}]({r.get('url')}): {r.get('content')}")

        if lines:
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
        """Simple regex and string-cleaning fallback to extract targets from message."""
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
