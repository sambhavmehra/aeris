"""
AERIS Security Agent — Plans and runs multi-step security assessments.
Uses recon + VAPT tools, then sends results to Gemini for deep analysis.
Now enhanced with VulnSage intelligence: AI triage + threat narrative.
"""

import json
import logging
from typing import Any

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

PLAN_PROMPT = """You are a cybersecurity expert AI. Based on the user's request, decide which security tools to run.

Available tools:
{tools}

User request: {message}

Respond with ONLY valid JSON:
{{
  "target": "the target domain/IP extracted from the request",
  "tools": ["tool_name_1", "tool_name_2"],
  "reason": "brief explanation of why these tools"
}}

Rules:
- Extract the target (domain, IP, or URL) from the user's message
- Choose the most relevant tools for the request
- For "full recon" or "full scan", use: dns_lookup, subdomain_enum, port_scan, whois_lookup, header_analysis, ssl_check
- For specific requests, only pick what's needed
- Always include at least one tool
"""

REPORT_PROMPT = """You are AERIS, a cybersecurity AI analyst. Analyze these security scan results and produce a professional report.

Target: {target}
Tools executed: {tools_run}

Raw results:
{results}

Create a detailed security assessment report in markdown with:
1. **Executive Summary** — brief overview of findings
2. **Detailed Findings** — organized by tool, highlight important discoveries
3. **Risk Assessment** — rate overall security posture (Critical/High/Medium/Low)
4. **Recommendations** — actionable steps to improve security

Use clear formatting with headers, bullet points, and code blocks where appropriate.
Keep it concise but thorough. Highlight any vulnerabilities or misconfigurations found.
"""


class SecurityAgent(BaseAgent):
    """Orchestrates multi-step security assessments using recon and VAPT tools."""

    def __init__(self):
        super().__init__(
            name="SecurityAgent",
            description="Plans and executes security scans — reconnaissance, VAPT, and vulnerability analysis",
            task_domain="security",
            version="3.0.0",
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
                "Zero-Day Detection (VulnSage)",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Ask Groq to plan which security tools to run."""
        recon_tools = tool_registry.get_tools_description("recon")
        vapt_tools = tool_registry.get_tools_description("vapt")
        all_tools = f"RECON TOOLS:\n{recon_tools}\n\nVAPT TOOLS:\n{vapt_tools}"

        prompt = PLAN_PROMPT.format(tools=all_tools, message=message)

        try:
            raw = await ai_engine.classify(prompt)
            # Strip markdown fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()
            plan = json.loads(raw)
            self.logger.info(f"Security plan: target={plan.get('target')}, tools={plan.get('tools')}")
            return plan
        except (json.JSONDecodeError, Exception) as e:
            self.logger.warning(f"Plan parsing failed: {e}, using fallback")
            # Fallback: extract target and run basic scan
            target = self._extract_target(message)
            return {
                "target": target,
                "tools": ["dns_lookup", "port_scan", "header_analysis"],
                "reason": "Fallback — basic reconnaissance scan",
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

            # Build params based on tool's expected parameters
            params = self._build_params(tool_name, target)
            self.logger.info(f"Running {tool_name} on {target}")

            try:
                result = await tool_registry.execute(tool_name, params)
                results.append(result)
            except Exception as e:
                self.logger.error(f"Tool {tool_name} failed: {e}")
                results.append({"tool": tool_name, "status": "error", "error": str(e)})

        return {"target": target, "tools_run": tools_to_run, "results": results}

    async def report(self, results: Any) -> str:
        """Send all results to AI for deep analysis, triage, and narrative generation."""
        target = results.get("target", "unknown")
        tools_run = results.get("tools_run", [])
        raw_results_list = results.get("results", [])
        raw_results = json.dumps(raw_results_list, indent=2, default=str)

        # ── Stage 1: AI Auto-Triage (VulnSage) ──────────────────────────────
        triaged_findings = []
        triage_summary = ""
        try:
            triage = _get_triage()
            if triage and raw_results_list:
                # Convert tool results to finding-like dicts for triage
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

        # ── Stage 3: Full AI Report (Gemini) ─────────────────────────────────
        prompt = REPORT_PROMPT.format(
            target=target,
            tools_run=", ".join(tools_run),
            results=raw_results,
        )

        try:
            report = await ai_engine.reason(prompt)
            return report + triage_summary + narrative_section
        except Exception as e:
            self.logger.error(f"Report generation failed: {e}")
            return (f"## Security Scan Results for {target}\n\n```json\n{raw_results}\n```"
                    f"\n\n*Note: AI analysis unavailable — showing raw results.*"
                    + narrative_section)

    def _build_params(self, tool_name: str, target: str) -> dict:
        """Build the right parameter dict based on what each tool expects."""
        # Tools that take "domain"
        if tool_name in ("dns_lookup", "subdomain_enum", "whois_lookup", "ssl_check"):
            domain = target.replace("https://", "").replace("http://", "").split("/")[0]
            params = {"domain": domain}
            if tool_name == "dns_lookup":
                params["record_type"] = "ALL"
            return params
        # Tools that take "url"
        if tool_name in ("header_analysis", "directory_fuzz", "tech_detect", "cors_check", "cookie_audit"):
            return {"url": target}
        # Tools that take "target"
        if tool_name == "port_scan":
            host = target.replace("https://", "").replace("http://", "").split("/")[0]
            return {"target": host}
        if tool_name == "banner_grab":
            host = target.replace("https://", "").replace("http://", "").split("/")[0]
            return {"target": host, "port": 80}
        # Tools that take "ip"
        if tool_name == "reverse_dns":
            return {"ip": target}
        return {"target": target}

    @staticmethod
    def _extract_target(message: str) -> str:
        """Extract a domain/IP/URL from the user message."""
        import re
        # Match domains and IPs
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
