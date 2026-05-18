"""
AERIS Threat Narrative Generator
Ported from VulnSage's ai_narrative.py, adapted for AERIS's async AI engine.
Converts raw scan findings into executive-level threat reports.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aeris.intelligence.threat_narrative")


class ThreatNarrativeGenerator:
    """Generates executive threat narratives from security scan findings."""

    def __init__(self, ai_engine=None):
        self._ai = ai_engine

    def generate(self, domain_info: Dict, vulnerabilities: List[Dict], subdomains: List = None) -> Dict[str, Any]:
        """Synchronous narrative generation (no AI enhancement)."""
        if not vulnerabilities:
            return self._empty_narrative(domain_info)

        critical = [v for v in vulnerabilities if v.get("severity", "").upper() == "CRITICAL"]
        high = [v for v in vulnerabilities if v.get("severity", "").upper() == "HIGH"]
        medium = [v for v in vulnerabilities if v.get("severity", "").upper() == "MEDIUM"]
        low = [v for v in vulnerabilities if v.get("severity", "").upper() in ("LOW", "INFO")]
        confirmed = [v for v in vulnerabilities if v.get("confirmed") or v.get("poc_evidence")]

        return {
            "executive_summary": self._executive_summary(domain_info, vulnerabilities, critical, high),
            "threat_scenario": self._threat_scenario(domain_info, vulnerabilities),
            "attack_timeline": self._attack_timeline(vulnerabilities),
            "business_impact": self._business_impact(critical, high, medium),
            "risk_score": self._calculate_risk_score(vulnerabilities),
            "urgency_level": self._urgency_level(critical, high),
            "key_findings": self._key_findings(vulnerabilities[:10]),
            "recommended_actions": self._recommended_actions(vulnerabilities),
            "statistics": {
                "total": len(vulnerabilities),
                "critical": len(critical),
                "high": len(high),
                "medium": len(medium),
                "low": len(low),
                "confirmed": len(confirmed),
                "subdomains": len(subdomains or []),
            },
        }

    async def generate_async(self, domain_info: Dict, vulnerabilities: List[Dict], subdomains: List = None) -> Dict[str, Any]:
        """Async version — generates narrative then enhances with AI if available."""
        narrative = self.generate(domain_info, vulnerabilities, subdomains)
        if self._ai and vulnerabilities:
            try:
                brief = await self._ai_enhance(domain_info, vulnerabilities, narrative)
                if brief:
                    narrative["ai_executive_brief"] = brief
            except Exception as exc:
                logger.debug("AI narrative enhancement failed: %s", exc)
        return narrative

    # ── Section builders ────────────────────────────────────────────

    def _executive_summary(self, domain_info: Dict, vulns: List, critical: List, high: List) -> str:
        domain = domain_info.get("domain", "target")
        total = len(vulns)
        confirmed = sum(1 for v in vulns if v.get("confirmed") or v.get("poc_evidence"))
        if critical:
            sev = f"CRITICAL posture with {len(critical)} critical vulnerabilities"
            action = "Immediate remediation required — potential data breach risk."
        elif high:
            sev = f"HIGH risk with {len(high)} high-severity vulnerabilities"
            action = "Urgent remediation recommended within 48 hours."
        elif total > 5:
            sev = f"MODERATE risk with {total} findings"
            action = "Scheduled remediation recommended within 2 weeks."
        else:
            sev = f"LOW risk with {total} minor findings"
            action = "Standard patching cycle is sufficient."
        return (
            f"Security assessment of {domain} reveals a {sev}. "
            f"{total} vulnerabilities identified, {confirmed} confirmed with PoC evidence. {action}"
        )

    def _threat_scenario(self, domain_info: Dict, vulns: List) -> str:
        domain = domain_info.get("domain", "target")
        scenarios = []
        types = set(v.get("type", "").lower() for v in vulns)
        if any("sql" in t for t in types):
            scenarios.append(f"SQL injection could expose {domain}'s database including credentials and financial records.")
        if any("xss" in t for t in types):
            scenarios.append("XSS vulnerabilities enable session hijacking and credential theft via crafted links.")
        if any(k in t for t in types for k in ("rce", "ssti", "command")):
            scenarios.append("Remote code execution could give attackers full server control for ransomware deployment.")
        if any("smuggl" in t or "desync" in t for t in types):
            scenarios.append("HTTP request smuggling could bypass security controls and hijack user sessions.")
        if any("jwt" in t for t in types):
            scenarios.append("JWT vulnerabilities allow forged tokens granting unauthorized access to admin functions.")
        if any("cache" in t for t in types):
            scenarios.append("Cache poisoning could serve malicious content to all users via the CDN layer.")
        if any("prototype" in t or "pollution" in t for t in types):
            scenarios.append("Prototype pollution in the Node.js runtime could escalate to RCE via gadget chains.")
        if any("ssrf" in t for t in types):
            scenarios.append("SSRF allows internal network scanning and cloud metadata service access.")
        if not scenarios:
            scenarios.append(f"Identified vulnerabilities in {domain} could lead to data exposure or service disruption.")
        return " ".join(scenarios)

    def _attack_timeline(self, vulns: List) -> List[Dict]:
        timeline = []
        seen: set = set()
        priorities = [
            ("Critical", "smuggl", "0-2 min", "Session hijack via request desync"),
            ("Critical", "ssti", "0-5 min", "RCE via template engine injection"),
            ("Critical", "sql", "0-5 min", "Database dump via automated SQLi"),
            ("Critical", "rce", "5-15 min", "Full server takeover"),
            ("High", "jwt", "5-20 min", "Privilege escalation via forged token"),
            ("High", "cache", "10-30 min", "Mass user content poisoning"),
            ("High", "prototype", "15-45 min", "Node.js RCE via gadget chain"),
            ("High", "xss", "15-45 min", "Session hijacking via crafted link"),
            ("High", "ssrf", "30-60 min", "Internal network recon"),
            ("Medium", "csrf", "1-2 hrs", "Forced user actions via social engineering"),
            ("Low", "info", "immediate", "Recon and intelligence gathering"),
        ]
        for severity, kw, time_est, impact in priorities:
            matching = [v for v in vulns if kw in v.get("type", "").lower()]
            if matching and kw not in seen:
                seen.add(kw)
                timeline.append({
                    "step": len(timeline) + 1,
                    "vulnerability": matching[0].get("type", kw),
                    "time_to_exploit": time_est,
                    "impact": impact,
                    "severity": severity,
                })
        return timeline or [{"step": 1, "vulnerability": "General", "time_to_exploit": "varies", "impact": "Assessment required", "severity": "Info"}]

    def _business_impact(self, critical: List, high: List, medium: List) -> Dict:
        score = len(critical) * 10 + len(high) * 6 + len(medium) * 3
        if score >= 30:
            level, desc, fin = "SEVERE", "Immediate threat of data breach, fines, and reputational damage.", "$100K–$10M+"
        elif score >= 15:
            level, desc, fin = "HIGH", "Significant risk of data exposure and service disruption.", "$50K–$500K"
        elif score >= 5:
            level, desc, fin = "MODERATE", "Security gaps that could be exploited with moderate effort.", "$10K–$50K"
        else:
            level, desc, fin = "LOW", "Minor improvements recommended for ongoing security hygiene.", "Minimal"
        return {"level": level, "score": min(score, 100), "description": desc, "financial_estimate": fin,
                "regulatory_risk": "HIGH" if critical else "MODERATE", "reputational_risk": level}

    def _calculate_risk_score(self, vulns: List) -> int:
        weights = {"CRITICAL": 25, "HIGH": 15, "MEDIUM": 8, "LOW": 3, "INFO": 1}
        score = sum(weights.get(v.get("severity", "INFO").upper(), 1) * (v.get("confidence", 50) / 100) *
                    (1.5 if v.get("confirmed") else 1.0) for v in vulns)
        return min(int(score), 100)

    def _urgency_level(self, critical: List, high: List) -> Dict:
        if critical:
            return {"level": "IMMEDIATE", "color": "#ff003c", "action": "Deploy fixes within 24 hours", "sla": "P0 — Emergency"}
        if high:
            return {"level": "URGENT", "color": "#ff6b00", "action": "Deploy fixes within 72 hours", "sla": "P1 — High Priority"}
        return {"level": "PLANNED", "color": "#00ffe1", "action": "Schedule fixes in next sprint", "sla": "P2 — Normal Priority"}

    def _key_findings(self, vulns: List) -> List[Dict]:
        return [{"type": v.get("type", "Unknown"), "severity": v.get("severity", "Info"),
                 "confidence": v.get("confidence", 0), "url": v.get("url", ""),
                 "confirmed": bool(v.get("confirmed") or v.get("poc_evidence")),
                 "description": str(v.get("description", ""))[:200]} for v in vulns]

    def _recommended_actions(self, vulns: List) -> List[Dict]:
        actions, seen = [], set()
        sev_key = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}
        for v in sorted(vulns, key=lambda x: sev_key.get(x.get("severity", "INFO").upper(), 5)):
            vtype = v.get("type", "").split("(")[0].strip()
            if vtype not in seen and len(actions) < 8:
                seen.add(vtype)
                actions.append({"priority": len(actions) + 1, "action": v.get("recommendation", f"Remediate {vtype}"),
                                 "severity": v.get("severity", "Info"), "type": vtype,
                                 "effort": "High" if v.get("severity", "").upper() in ("CRITICAL", "HIGH") else "Medium"})
        return actions

    async def _ai_enhance(self, domain_info: Dict, vulns: List, narrative: Dict) -> Optional[str]:
        if not self._ai:
            return None
        import json
        summary = json.dumps([{"type": v.get("type"), "severity": v.get("severity"),
                                "url": str(v.get("url", ""))[:80], "confirmed": bool(v.get("confirmed"))}
                               for v in vulns[:15]], indent=2)
        prompt = (
            f"You are AERIS, a senior security AI. Write a 4-5 sentence executive threat brief.\n\n"
            f"Target: {domain_info.get('domain', 'unknown')}\n"
            f"Risk Score: {narrative['risk_score']}/100\n"
            f"Urgency: {narrative['urgency_level']['level']}\n\n"
            f"Vulnerabilities:\n{summary}\n\n"
            "Open with the most critical finding and real-world impact. Describe the most likely attack path. "
            "Quantify the risk. End with a clear call to action. "
            "No markdown, no bullet points. Output ONLY the narrative paragraph."
        )
        try:
            return (await self._ai.reason(prompt)).strip() or None
        except Exception as exc:
            logger.debug("AI brief failed: %s", exc)
            return None

    def _empty_narrative(self, domain_info: Dict) -> Dict:
        domain = domain_info.get("domain", "target")
        return {
            "executive_summary": f"Security assessment of {domain} completed with no vulnerabilities detected.",
            "threat_scenario": "No active threats identified.", "attack_timeline": [],
            "business_impact": {"level": "MINIMAL", "score": 0, "description": "No immediate concerns.",
                                 "financial_estimate": "N/A", "regulatory_risk": "LOW", "reputational_risk": "LOW"},
            "risk_score": 0,
            "urgency_level": {"level": "NONE", "color": "#00ff88", "action": "Continue regular monitoring", "sla": "N/A"},
            "key_findings": [], "recommended_actions": [],
            "statistics": {"total": 0, "critical": 0, "high": 0, "medium": 0, "low": 0, "confirmed": 0, "subdomains": 0},
        }


_instance: Optional[ThreatNarrativeGenerator] = None


def get_narrative_generator() -> ThreatNarrativeGenerator:
    global _instance
    if _instance is None:
        from ai_engine import ai_engine
        _instance = ThreatNarrativeGenerator(ai_engine=ai_engine)
    return _instance
