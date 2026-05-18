"""
AERIS AI Auto-Triage & Severity Recalculation
Ported from VulnSage's ai_triage.py.

Re-evaluates vulnerability severity using:
- HTTP security headers (WAF, CSP, HSTS detection)
- Technology stack fingerprinting
- Cross-finding attack chain correlation
- AI validation of Critical/High findings
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aeris.intelligence.ai_triage")

CONTROL_WEIGHTS = {
    "Content-Security-Policy": 0.85,
    "Strict-Transport-Security": 0.90,
    "X-Frame-Options": 0.90,
    "X-Content-Type-Options": 0.95,
    "Referrer-Policy": 0.95,
    "Permissions-Policy": 0.95,
}

SEVERITY_ORDER = {"Critical": 4, "CRITICAL": 4, "High": 3, "HIGH": 3,
                  "Medium": 2, "MEDIUM": 2, "Low": 1, "LOW": 1, "Info": 0, "INFO": 0}
SEVERITY_NAMES = {4: "Critical", 3: "High", 2: "Medium", 1: "Low", 0: "Info"}


class AIAutoTriage:
    """
    Contextually re-evaluates vulnerability severity.
    Considers compensating controls, technology stack, and attack chain potential.
    """

    def __init__(self, ai_engine=None):
        self._ai = ai_engine

    def triage(self, vulnerabilities: List[Dict], headers: Dict[str, str] = None,
               tech_stack: List[str] = None) -> List[Dict]:
        """Re-triage all findings with contextual awareness (synchronous)."""
        if not vulnerabilities:
            return vulnerabilities

        headers = headers or {}
        tech_stack = [t.lower() for t in (tech_stack or [])]
        controls = self._detect_controls(headers)
        detected_tech = self._detect_tech_from_findings(vulnerabilities) + tech_stack

        context = {
            "total_findings": len(vulnerabilities),
            "controls": controls,
            "tech_stack": list(set(detected_tech)),
            "has_waf": self._detect_waf(headers),
            "has_csp": "Content-Security-Policy" in headers,
            "has_hsts": "Strict-Transport-Security" in headers,
            "attack_surface_size": len(set(v.get("url", "") for v in vulnerabilities)),
        }

        triaged = []
        for vuln in vulnerabilities:
            tv = dict(vuln)
            tv["original_severity"] = vuln.get("severity", "Info")
            tv["triage_notes"] = []
            tv["severity"] = self._rule_triage(tv, context)
            triaged.append(tv)

        triaged = self._cross_correlate(triaged)
        return triaged

    async def triage_async(self, vulnerabilities: List[Dict], headers: Dict[str, str] = None,
                           tech_stack: List[str] = None) -> List[Dict]:
        """Async version — runs rule-based triage then AI validation."""
        triaged = self.triage(vulnerabilities, headers, tech_stack)
        if self._ai and any(v.get("severity", "").upper() in ("CRITICAL", "HIGH") for v in triaged):
            try:
                triaged = await self._ai_triage(triaged, {
                    "has_waf": self._detect_waf(headers or {}),
                    "has_csp": "Content-Security-Policy" in (headers or {}),
                    "has_hsts": "Strict-Transport-Security" in (headers or {}),
                    "tech_stack": [t.lower() for t in (tech_stack or [])],
                    "attack_surface_size": len(set(v.get("url", "") for v in triaged)),
                })
            except Exception as exc:
                logger.debug("AI triage failed: %s", exc)
        return triaged

    # ── Rule engine ──────────────────────────────────────────────────

    def _rule_triage(self, vuln: Dict, context: Dict) -> str:
        current_val = SEVERITY_ORDER.get(vuln.get("severity", "Info"), 0)
        vtype = vuln.get("type", "").lower()
        confidence = vuln.get("confidence", 50)
        confirmed = vuln.get("confirmed") or vuln.get("poc_evidence")
        notes: List[str] = vuln.get("triage_notes", [])

        # Upgrades
        if confirmed and confidence >= 90 and current_val < 3:
            current_val = min(current_val + 1, 4)
            notes.append("Upgraded: confirmed with high-confidence PoC")
        if "sql" in vtype and current_val < 3:
            current_val = 3
            notes.append("Upgraded: SQL injection is inherently high-risk")
        if any(k in vtype for k in ("rce", "code execution", "command injection", "ssti")) and current_val < 4:
            current_val = 4
            notes.append("Upgraded: RCE/SSTI is critical by nature")
        if "smuggl" in vtype or "desync" in vtype:
            current_val = max(current_val, 4)
            notes.append("Upgraded: HTTP smuggling is a critical-class vulnerability")
        if "prototype pollution" in vtype and current_val < 3:
            current_val = 3
            notes.append("Upgraded: Prototype pollution can escalate to RCE")

        # Downgrades
        if "xss" in vtype and context.get("has_csp") and current_val > 1:
            current_val -= 1
            notes.append("Downgraded: CSP present, mitigates XSS impact")
        if not confirmed and confidence < 40 and current_val > 1:
            current_val -= 1
            notes.append(f"Downgraded: low confidence ({confidence}%) without PoC confirmation")
        if context.get("has_waf") and not confirmed and current_val > 2:
            current_val -= 1
            notes.append("Downgraded: WAF detected, exploitation harder")
        if "info" in vtype and "disclosure" in vtype and current_val > 1:
            if not any(kw in str(vuln).lower() for kw in ("password", "credential", "token", "api_key", "secret")):
                current_val = min(current_val, 1)
                notes.append("Capped at Low: info disclosure without sensitive data")

        vuln["triage_notes"] = notes
        return SEVERITY_NAMES.get(min(max(current_val, 0), 4), "Info")

    def _cross_correlate(self, vulns: List[Dict]) -> List[Dict]:
        """Upgrade findings that form dangerous attack chains."""
        types = set(v.get("type", "").lower() for v in vulns)
        has_info = any("info" in t or "disclosure" in t for t in types)
        has_auth = any("auth" in t or "bypass" in t for t in types)
        has_sqli = any("sql" in t for t in types)
        has_xss = any("xss" in t for t in types)

        if has_info and has_auth:
            for v in vulns:
                if "auth" in v.get("type", "").lower() or "bypass" in v.get("type", "").lower():
                    if SEVERITY_ORDER.get(v["severity"], 0) < 4:
                        v["severity"] = "Critical"
                        v.setdefault("triage_notes", []).append(
                            "Chain upgraded: auth bypass + info disclosure = critical chain"
                        )
        if has_sqli and has_xss:
            for v in vulns:
                if "sql" in v.get("type", "").lower():
                    v.setdefault("triage_notes", []).append(
                        "Chain detected: SQLi + XSS enables data exfiltration + session hijack"
                    )
        return vulns

    # ── Detection helpers ────────────────────────────────────────────

    def _detect_controls(self, headers: Dict) -> Dict[str, bool]:
        return {control: control in headers for control in CONTROL_WEIGHTS}

    def _detect_waf(self, headers: Dict) -> bool:
        waf_indicators = [
            "cf-ray", "cf-cache-status", "x-sucuri-id",
            "x-cdn", "x-akamai-transformed", "x-fw-protection",
        ]
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
        return any(ind in headers_lower for ind in waf_indicators)

    def _detect_tech_from_findings(self, vulns: List[Dict]) -> List[str]:
        all_text = " ".join(str(v) for v in vulns).lower()
        tech_map = {
            "php": "php", "asp.net": "asp.net", "java": "java", "spring": "spring",
            "django": "django", "flask": "flask", "express": "express", "node": "nodejs",
            "wordpress": "wordpress", "apache": "apache", "nginx": "nginx",
            "iis": "iis", "tomcat": "tomcat",
        }
        return [name for kw, name in tech_map.items() if kw in all_text]

    # ── AI validation ────────────────────────────────────────────────

    async def _ai_triage(self, vulns: List[Dict], context: Dict) -> List[Dict]:
        if not self._ai:
            return vulns

        import json
        critical_high = [v for v in vulns if v.get("severity", "").upper() in ("CRITICAL", "HIGH")]
        if not critical_high:
            return vulns

        summary = json.dumps([{
            "type": v.get("type"),
            "severity": v.get("severity"),
            "original_severity": v.get("original_severity"),
            "confidence": v.get("confidence", 0),
            "confirmed": bool(v.get("confirmed")),
            "notes": v.get("triage_notes", []),
        } for v in critical_high[:8]], indent=2)

        prompt = (
            f"You are AERIS performing security triage validation.\n\n"
            f"Context:\n"
            f"- WAF detected: {context.get('has_waf', False)}\n"
            f"- CSP present: {context.get('has_csp', False)}\n"
            f"- HSTS present: {context.get('has_hsts', False)}\n"
            f"- Tech stack: {context.get('tech_stack', [])}\n\n"
            f"Critical/High findings to validate:\n{summary}\n\n"
            "For each finding, respond with a JSON array of objects:\n"
            '[{"type": "...", "validated_severity": "Critical|High|Medium|Low", "reason": "one sentence"}]\n'
            "Output ONLY the JSON array."
        )

        try:
            result = await self._ai.classify(prompt)
            if result:
                validations = __import__("json").loads(result)
                if isinstance(validations, list):
                    val_map = {v.get("type", ""): v for v in validations}
                    for vuln in vulns:
                        vtype = vuln.get("type", "")
                        if vtype in val_map:
                            ai_sev = val_map[vtype].get("validated_severity", vuln["severity"])
                            if ai_sev in SEVERITY_ORDER:
                                vuln["ai_validated_severity"] = ai_sev
                                vuln.setdefault("triage_notes", []).append(
                                    f"AI validation: {val_map[vtype].get('reason', 'confirmed')}"
                                )
        except Exception as exc:
            logger.debug("AI triage parse error: %s", exc)

        return vulns


_instance: Optional[AIAutoTriage] = None


def get_auto_triage() -> AIAutoTriage:
    global _instance
    if _instance is None:
        from ai_engine import ai_engine
        _instance = AIAutoTriage(ai_engine=ai_engine)
    return _instance
