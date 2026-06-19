"""
AERIS Security Agent — Plans and runs multi-step security assessments.
Uses recon + VAPT tools, then sends results to Gemini for deep analysis.
Now enhanced with:
  - Zero-Day detection and assessment
  - Full conversation context awareness (resolves follow-up queries)
  - VulnSage intelligence: AI triage + threat narrative
"""

import json
import logging
import re
from typing import Any, List

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from tools.tool_registry import global_tool_registry as tool_registry

logger = logging.getLogger("aeris.agent.security")

# Lazy imports — won't break startup if intelligence modules aren't ready
def _get_triage():
    try:
        from intelligence.ai_triage import get_auto_triage
        return get_auto_triage()
    except Exception:
        return None

def _get_narrative():
    try:
        from intelligence.threat_narrative import get_narrative_generator
        return get_narrative_generator()
    except Exception:
        return None


PLAN_PROMPT = """You are an elite cybersecurity AI — a zero-day specialist and recon expert.
Your job: analyze the user's request AND the conversation history, then decide which security tools to run.

Available tools:
{tools}

=== CONVERSATION HISTORY (last 5 messages) ===
{history}
=== END HISTORY ===

Current user request: {message}

CRITICAL RULES:
1. If the user says "it", "that target", "the domain", "iska", "uska" or any pronoun — resolve it from conversation history.
2. Extract the target (domain, IP, or URL) from the current message OR from history if not present in current message.
3. Choose the most relevant tools for the request.
4. For "full recon" or "full scan", use: dns_lookup, subdomain_enum, port_scan, whois_lookup, header_analysis, ssl_check
5. For specific requests, only pick what's needed.
6. Always include at least one tool.
7. Analyze for ZERO-DAY indicators: unpatched services, unusual port behaviors, suspicious headers, outdated SSL, unknown CVE patterns.

Respond with ONLY valid JSON:
{{
  "target": "the resolved target domain/IP/URL",
  "tools": ["tool_name_1", "tool_name_2"],
  "reason": "brief explanation of why these tools",
  "zero_day_indicators": ["list any suspected zero-day patterns or leave empty array"],
  "scan_depth": "quick | standard | deep"
}}
"""

REPORT_PROMPT = """You are AERIS — an elite cybersecurity AI analyst specializing in zero-day vulnerability research.
Analyze these security scan results and produce a professional threat assessment report.

Target: {target}
Tools executed: {tools_run}
Conversation context: {context_summary}

Raw results:
{results}

Create a detailed security assessment report in markdown with:
1. **Executive Summary** — brief overview of findings
2. **Detailed Findings** — organized by tool, highlight important discoveries
3. **Zero-Day Risk Assessment** — flag any unpatched services, suspicious behaviors, or potential 0-day vectors. Rate: CRITICAL / HIGH / MEDIUM / LOW / NONE
4. **CVE & Exploit Chain Analysis** — identify any known CVEs or possible exploit chains based on detected versions/services
5. **Risk Assessment** — overall security posture (Critical/High/Medium/Low)
6. **Recommendations** — actionable remediation steps

Use clear markdown with headers, bullet points, and code blocks where appropriate.
Highlight zero-day risks prominently. Be thorough but concise.
"""


class SecurityAgent(BaseAgent):
    """Orchestrates multi-step security assessments using recon and VAPT tools.
    Now with full context awareness and zero-day intelligence."""

    def __init__(self):
        super().__init__(
            name="SecurityAgent",
            description="Plans and executes security scans — reconnaissance, VAPT, vulnerability analysis, and zero-day detection",
            task_domain="security",
            version="4.0.0",
            capabilities=[
                "Port Scanning (Nmap)",
                "DNS Lookup and Enumeration",
                "Subdomain Discovery",
                "SSL/TLS Certificate Analysis",
                "HTTP Header Analysis",
                "WHOIS Lookup",
                "Vulnerability Assessment (VAPT)",
                "Security Report Generation",
                "AI Auto-Triage (VulnSage)",
                "Threat Narrative Generation (VulnSage)",
                "Zero-Day Detection & Assessment",
                "Context-Aware Follow-Up Query Resolution",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Ask AI to plan which security tools to run — with full context awareness."""
        recon_tools = tool_registry.get_tools_description("recon")
        vapt_tools = tool_registry.get_tools_description("vapt")
        all_tools = f"RECON TOOLS:\n{recon_tools}\n\nVAPT TOOLS:\n{vapt_tools}"

        # Build conversation history string for context injection
        history_str = self._format_history(context.get("chat_history", []))

        prompt = PLAN_PROMPT.format(
            tools=all_tools,
            history=history_str,
            message=message,
        )

        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            plan = json.loads(raw)

            # If AI returned "unknown" or empty target, try context extraction
            if not plan.get("target") or plan.get("target") == "unknown":
                plan["target"] = self._extract_target_from_context(
                    message, context.get("chat_history", [])
                )

            self.logger.info(
                f"Security plan: target={plan.get('target')}, tools={plan.get('tools')}, "
                f"zero_day_indicators={plan.get('zero_day_indicators', [])}, depth={plan.get('scan_depth', 'standard')}"
            )
            return plan
        except (json.JSONDecodeError, Exception) as e:
            self.logger.warning(f"Plan parsing failed: {e}, using fallback")
            target = self._extract_target_from_context(message, context.get("chat_history", []))
            return {
                "target": target,
                "tools": ["dns_lookup", "port_scan", "header_analysis"],
                "reason": "Fallback — basic reconnaissance scan",
                "zero_day_indicators": [],
                "scan_depth": "standard",
            }

    async def execute(self, plan: Any) -> Any:
        """Run each tool from the plan via ToolRegistry."""
        target = plan.get("target", "unknown")
        tools_to_run = plan.get("tools", [])
        results = []

        for tool_name in tools_to_run:
            tool = tool_registry.get(tool_name)
            if not tool:
                results.append({"tool": tool_name, "status": "error", "error": "Tool not found"})
                continue

            params = self._build_params(tool_name, target)
            self.logger.info(f"Running {tool_name} on {target}")

            try:
                result = await tool_registry.execute_async(tool_name, **params)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Tool {tool_name} failed: {e}")
                results.append({"tool": tool_name, "status": "error", "error": str(e)})

        return {
            "target": target,
            "tools_run": tools_to_run,
            "results": results,
            "zero_day_indicators": plan.get("zero_day_indicators", []),
            "scan_depth": plan.get("scan_depth", "standard"),
        }

    async def report(self, results: Any) -> str:
        """Send all results to AI for deep analysis, zero-day assessment, triage, and narrative."""
        target = results.get("target", "unknown")
        tools_run = results.get("tools_run", [])
        raw_results_list = results.get("results", [])
        zero_day_indicators = results.get("zero_day_indicators", [])
        raw_results = json.dumps(raw_results_list, indent=2, default=str)

        # Build context summary from memory
        try:
            from memory.store import memory_store
            history = memory_store.get_context(5)
            context_summary = self._format_history(history)
        except Exception:
            context_summary = "No prior context available."

        # ── Stage 1: AI Auto-Triage (VulnSage) ──────────────────────────────
        triaged_findings = []
        triage_summary = ""
        try:
            triage = _get_triage()
            if triage and raw_results_list:
                findings_for_triage = [
                    {"type": r.get("tool", "unknown"), "severity": r.get("severity", "Medium"),
                     "description": str(r), "confidence": 70, "url": target}
                    for r in raw_results_list if isinstance(r, dict) and r.get("status") != "error"
                ]
                if findings_for_triage:
                    triaged_findings = await triage.triage_async(findings_for_triage)
                    triage_summary = f"\n\n**AI Triage applied:** {len(triaged_findings)} findings re-evaluated."
                    self.logger.info("AI triage complete: %d findings re-evaluated", len(triaged_findings))
        except Exception as exc:
            self.logger.debug("Triage stage failed: %s", exc)

        # ── Stage 2: Threat Narrative (VulnSage) ─────────────────────────────
        narrative_section = ""
        try:
            narrator = _get_narrative()
            if narrator:
                domain_info = {"domain": target.replace("https://", "").replace("http://", "").split("/")[0]}
                narr = await narrator.generate_async(domain_info, triaged_findings or [])
                urgency = narr.get("urgency_level", {}).get("level", "UNKNOWN")
                risk = narr.get("risk_score", 0)
                business = narr.get("business_impact", {}).get("level", "N/A")
                exec_summary = narr.get("executive_summary", "")
                ai_brief = narr.get("ai_executive_brief", "")
                timeline = narr.get("attack_timeline", [])
                stats = narr.get("statistics", {})

                tl_lines = "\n".join(
                    f"  - **Step {t['step']}** ({t['severity']}): {t['vulnerability']} — {t['time_to_exploit']} — {t['impact']}"
                    for t in timeline[:5]
                )

                narrative_section = (
                    f"\n\n---\n## 🧠 AI Threat Intelligence (VulnSage)"
                    f"\n\n**Risk Score:** {risk}/100 | **Urgency:** {urgency} | **Business Impact:** {business}"
                    f"\n\n### Executive Summary\n{exec_summary}"
                    + (f"\n\n### AI Threat Brief\n{ai_brief}" if ai_brief else "")
                    + (f"\n\n### Attack Timeline\n{tl_lines}" if tl_lines else "")
                    + f"\n\n**Findings:** Critical={stats.get('critical',0)} High={stats.get('high',0)} Medium={stats.get('medium',0)} Low={stats.get('low',0)}"
                )
        except Exception as exc:
            self.logger.debug("Narrative stage failed: %s", exc)

        # ── Prepend zero-day indicators if found ──────────────────────────────
        zd_section = ""
        if zero_day_indicators:
            zd_section = "\n\n> ⚠️ **Potential Zero-Day Indicators Detected:**\n"
            for indicator in zero_day_indicators:
                zd_section += f"> - {indicator}\n"

        # ── Stage 3: Full AI Report (Gemini) ─────────────────────────────────
        prompt = REPORT_PROMPT.format(
            target=target,
            tools_run=", ".join(tools_run),
            context_summary=context_summary,
            results=raw_results,
        )

        try:
            report = await ai_engine.reason(prompt)
            return report + zd_section + triage_summary + narrative_section
        except Exception as e:
            self.logger.error(f"Report generation failed: {e}")
            return (
                f"## Security Scan Results for {target}\n\n```json\n{raw_results}\n```"
                f"\n\n*Note: AI analysis unavailable — showing raw results.*"
                + zd_section + narrative_section
            )

    # ─────────────────────── Helpers ─────────────────────────────────────────

    def _format_history(self, chat_history: list, limit: int = 5) -> str:
        """Format last N chat messages into a readable context string."""
        if not chat_history:
            return "No prior conversation."
        lines = []
        for msg in chat_history[-limit:]:
            role = msg.get("role", "user").upper()
            content = msg.get("content", "")[:2000]  # truncate long messages
            lines.append(f"[{role}]: {content}")
        return "\n".join(lines)

    def _extract_target_from_context(self, message: str, chat_history: list) -> str:
        """
        Extract a domain/IP/URL from:
        1. The current message
        2. If not found, walk backwards through chat history to find last mentioned target
        """
        # First try current message
        target = self._extract_target(message)
        if target and target != "unknown":
            return target

        # Walk history in reverse to find most recent target
        for msg in reversed(chat_history):
            content = msg.get("content", "")
            t = self._extract_target(content)
            if t and t != "unknown":
                self.logger.info(f"Resolved target from history: {t}")
                return t

        return "unknown"

    def _build_params(self, tool_name: str, target: str) -> dict:
        """Build the right parameter dict based on what each tool expects."""
        if tool_name in ("dns_lookup", "subdomain_enum", "whois_lookup", "ssl_check"):
            domain = target.replace("https://", "").replace("http://", "").split("/")[0]
            params = {"domain": domain}
            if tool_name == "dns_lookup":
                params["record_type"] = "ALL"
            return params
        if tool_name in ("header_analysis", "directory_fuzz", "tech_detect", "cors_check", "cookie_audit"):
            return {"url": target}
        if tool_name == "port_scan":
            host = target.replace("https://", "").replace("http://", "").split("/")[0]
            return {"target": host}
        if tool_name == "banner_grab":
            host = target.replace("https://", "").replace("http://", "").split("/")[0]
            return {"target": host, "port": 80}
        if tool_name == "reverse_dns":
            return {"ip": target}
        return {"target": target}

    @staticmethod
    def _extract_target(message: str) -> str:
        """Extract a domain/IP/URL from a message string."""
        patterns = [
            r'https?://[^\s<>"\']+',
            r'\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b',
            r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b',
        ]
        for p in patterns:
            m = re.search(p, message)
            if m:
                return m.group(0)
        return "unknown"
