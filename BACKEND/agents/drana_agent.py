"""
AERIS Drana Agent — bug bounty hunting, traffic analysis, and XSS/JS recon reasoning engine.
Interfaces with Drana-Infinity backend capabilities.
"""

import os
import sys
import re
import json
import logging
from typing import Any, Optional

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from memory.drana_store import drana_store

logger = logging.getLogger("aeris.agent.drana")

# Dynamically resolve path to Drana features to allow imports
DRANA_FEATURES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Drana features"
)
if DRANA_FEATURES_PATH not in sys.path:
    sys.path.append(DRANA_FEATURES_PATH)

try:
    import js_recon
    import drana_prompt
except ImportError:
    js_recon = None
    drana_prompt = None


class DranaAgent(BaseAgent):
    """
    Drana-Infinity reasoning agent for bug bounty hunting, manual VAPT,
    JavaScript recon, and XSS payload engineering.
    """

    def __init__(self):
        super().__init__(
            name="DranaAgent",
            description="Bug bounty hunting, manual VAPT, traffic interception, JS recon, and XSS payload engine",
            task_domain="drana",
            version="1.0.0",
            capabilities=[
                "Client-Side JS Recon & Data Extraction",
                "HTTP Request/Response Vulnerability Analysis",
                "XSS Payload Generation & Context Breakout",
                "Bug Bounty Attack Path Gating & Sinks Analysis",
            ],
        )

    def _read_prompt_file(self, filename: str) -> str:
        """Helper to read custom prompts from Drana features folder."""
        path = os.path.join(DRANA_FEATURES_PATH, "prompts", filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Failed to read prompt file {filename}: {e}")
        return ""

    async def think(self, message: str, context: dict) -> Any:
        """Classify message intent and extract code, traffic, or target inputs."""
        lower_msg = message.lower()
        
        # Scenario 0: Bug Bounty / VAPT workflow
        if "bug bounty" in lower_msg or "vapt" in lower_msg or "pentest" in lower_msg or "scan" in lower_msg:
            target = self._extract_target_from_context(message, context.get("chat_history", []))
            if target and target != "unknown":
                return {
                    "action": "bug_bounty_vapt",
                    "target": target,
                    "message": message,
                }
            else:
                return {
                    "action": "ask_for_target",
                    "message": message,
                }

        # Scenario 1: Javascript Recon
        if "javascript" in lower_msg or "js recon" in lower_msg or "js code" in lower_msg:
            # Try to extract JS code blocks
            code_blocks = self._extract_code_blocks(message)
            return {
                "action": "js_recon",
                "code": code_blocks[0] if code_blocks else message,
            }
        
        # Scenario 2: XSS Payload Generation
        if "xss" in lower_msg or "payload" in lower_msg or "reflection" in lower_msg:
            return {
                "action": "xss_payload",
                "message": message,
            }

        # Scenario 3: Request/Response Security Analysis (Triage/VAPT)
        if "http" in lower_msg or "request" in lower_msg or "response" in lower_msg or "header" in lower_msg:
            req_text = ""
            resp_text = ""
            # Extract request and response from message
            parts = message.split("---")
            if len(parts) >= 2:
                req_text = parts[0]
                resp_text = parts[1]
            else:
                req_text = message
                resp_text = ""

            return {
                "action": "traffic_analysis",
                "request": req_text,
                "response": resp_text,
            }

        # Scenario 4: General Bug Hunting Recon / Pentest advice fallback
        return {
            "action": "general_pentest",
            "message": message,
        }

    async def execute(self, plan: Any) -> Any:
        """Process the extracted plan based on action type."""
        action = plan.get("action", "general_pentest")

        if action == "bug_bounty_vapt":
            target = plan.get("target")
            self.logger.info(f"Initiating robust bug bounty/VAPT workflow for: {target}")

            # 1. Delegate baseline scanning/recon tool work to SecurityAgent
            sec_res = await self.use_agent(
                "SecurityAgent",
                f"perform full recon, subdomain enumeration, and vulnerability scan on {target}",
                plan
            )
            sec_report = sec_res.get("response", "No response from SecurityAgent.")

            # 2. Run Drana-Infinity deep analysis and checklist construction
            prompt = (
                f"You are Drana-Infinity — a security reasoning engine operating in strict epistemic mode.\n"
                f"You are conducting a VAPT / Bug Bounty assessment on target: {target}.\n\n"
                f"Here are the baseline reconnaissance, subdomain enumeration, and scanning results from the SecurityAgent:\n"
                f"{sec_report}\n\n"
                f"Your task is to analyze these findings (specifically focusing on discovered subdomains, ports, and services) and generate a highly customized manual pentesting and bug bounty roadmap.\n"
                f"Outline:\n"
                f"1. High-Value Client-Side Attack Surfaces (identify potential endpoints, technology stack indicators, JS behavior, and active subdomains).\n"
                f"2. Custom Attack Hypotheses (formulate 3-4 specific test hypotheses such as XSS, parameter fuzzing, header breakout, etc. linked to specific ports/services or subdomains found).\n"
                f"3. Potential Exploit Chains (how to chain findings across discovered subdomains or services to achieve high impact).\n"
                f"4. What NOT to waste time on.\n\n"
                f"Write the report in Hinglish, using a professional, precise, and skeptical tone. Use clear headers and formatting."
            )

            try:
                response = await ai_engine.chat([
                    {"role": "system", "content": "You are Drana-Infinity, an elite VAPT and payload reasoning engine."},
                    {"role": "user", "content": prompt}
                ])
                return {
                    "action": "bug_bounty_vapt",
                    "target": target,
                    "sec_report": sec_report,
                    "drana_analysis": response
                }
            except Exception as e:
                return {
                    "action": "bug_bounty_vapt",
                    "target": target,
                    "sec_report": sec_report,
                    "drana_analysis": f"Error running deep security analysis: {e}"
                }

        elif action == "ask_for_target":
            return {"action": "ask_for_target"}

        elif action == "js_recon":
            code = plan.get("code", "")
            if js_recon:
                recon_data = js_recon.extract_js_intelligence(code)
            else:
                recon_data = {"error": "js_recon module unavailable"}

            system_prompt = (
                drana_prompt.js_recon_system_prompt()
                if drana_prompt
                else "You are a JS recon specialist."
            )
            client_prompt_template = (
                drana_prompt.js_recon_client_prompt()
                if drana_prompt
                else "Analyze the following JS data: <DRANA_JS_RECON_DATA>"
            )
            client_prompt = client_prompt_template.replace(
                "<DRANA_JS_RECON_DATA>", json.dumps(recon_data, indent=2, default=str)
            )

            try:
                response = await ai_engine.chat([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": client_prompt}
                ])
                # Store in Drana's dedicated JSON memory
                drana_store.add_recon(recon_data)
                return {"action": "js_recon", "summary": response, "recon_data": recon_data}
            except Exception as e:
                return {"action": "js_recon", "summary": f"Error running JS analysis: {e}", "recon_data": recon_data}

        elif action == "xss_payload":
            msg = plan.get("message", "")
            system_prompt = (
                drana_prompt.xss_payload_generation_system_prompt()
                if drana_prompt
                else "You are an XSS payload generator."
            )
            client_prompt_template = (
                drana_prompt.xss_payload_generation_client_prompt()
                if drana_prompt
                else "Analyze XSS reflection: <DRANA_XSS_CODE_INFO>"
            )
            client_prompt = client_prompt_template.replace("<DRANA_XSS_CODE_INFO>", msg)

            try:
                response = await ai_engine.chat([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": client_prompt}
                ])
                # Store in Drana's dedicated JSON memory
                drana_store.add_xss_payload(msg, response)
                return {"action": "xss_payload", "response": response}
            except Exception as e:
                return {"action": "xss_payload", "response": f"Error generating XSS payload: {e}"}

        elif action == "traffic_analysis":
            req = plan.get("request", "")
            resp = plan.get("response", "")
            prompt_template = self._read_prompt_file("web_app_sec_text.txt")
            if not prompt_template:
                prompt_template = (
                    "Analyze the request: <<request>> and response: <<response>> for security issues."
                )
            prompt = prompt_template.replace("<<request>>", req).replace("<<response>>", resp)

            try:
                response = await ai_engine.chat([
                    {"role": "system", "content": "You are Drana-Infinity, an elite VAPT auditor."},
                    {"role": "user", "content": prompt}
                ])
                # Store in Drana's dedicated JSON memory
                drana_store.add_traffic_analysis(req, resp, response)
                return {"action": "traffic_analysis", "report": response}
            except Exception as e:
                return {"action": "traffic_analysis", "report": f"Error analyzing traffic: {e}"}

        else:
            msg = plan.get("message", "")
            prompt = (
                f"You are Drana-Infinity — a security reasoning engine operating in strict epistemic mode.\n"
                f"Help the user with their cybersecurity, recon, or pentesting request.\n\n"
                f"User Request: {msg}"
            )
            try:
                response = await ai_engine.chat([
                    {"role": "system", "content": "You are Drana-Infinity, a security reasoning assistant."},
                    {"role": "user", "content": prompt}
                ])
                return {"action": "general_pentest", "response": response}
            except Exception as e:
                return {"action": "general_pentest", "response": f"Error: {e}"}

    async def report(self, results: Any) -> str:
        """Generate human-readable bug bounty reports and summaries."""
        action = results.get("action")

        if action == "bug_bounty_vapt":
            target = results.get("target")
            drana_analysis = results.get("drana_analysis", "")
            sec_report = results.get("sec_report", "")

            md = [
                f"# 🛡️ Drana-Infinity VAPT & Bug Bounty Report: {target}",
                "Bhai, maine target par baseline security scans aur manual VAPT analysis perform kar li hai.\n",
                "## 🔍 Deep Security Triage & Pentest Checklist",
                drana_analysis,
                "\n---",
                "## 🌐 Baseline Reconnaissance Findings (SecurityAgent)",
                sec_report
            ]
            return "\n".join(md)

        elif action == "ask_for_target":
            return (
                "Bhai, kis target domain, IP, ya URL par bug bounty ya VAPT scan perform karna hai? "
                "Mujhe target specify karo (e.g. `sambhavmehra.me pe bug bounty scan run kar`)."
            )

        elif action == "js_recon":
            summary = results.get("summary", "")
            recon_data = results.get("recon_data", {})
            endpoints = recon_data.get("endpoints", [])
            sinks = recon_data.get("dangerous_sinks", [])
            sensitive = recon_data.get("sensitive_data", [])

            md = [
                "## 🔍 Drana JS Reconnaissance Report",
                summary,
                "### 📦 Extracted Recon Signals",
                f"- **Total Endpoints Traced:** {len(endpoints)}",
                f"- **Dangerous Sinks Detected:** {', '.join(sinks) if sinks else 'None'}",
                f"- **Potential Secrets/Keys Leakage:** {len(sensitive)}"
            ]
            if endpoints:
                md.append("\n#### Traced Endpoints / URLs:")
                for ep in endpoints[:10]:
                    md.append(f"- `{ep}`")
                if len(endpoints) > 10:
                    md.append(f"- *...and {len(endpoints) - 10} more*")
            return "\n".join(md)

        elif action == "xss_payload":
            return f"## 🎯 Drana XSS Decision & Payload\n\n{results.get('response')}"

        elif action == "traffic_analysis":
            return f"## 🛡️ Drana HTTP Traffic Security Triage\n\n{results.get('report')}"

        return f"## 🔬 Drana Security Response\n\n{results.get('response')}"

    def _extract_target_from_context(self, message: str, chat_history: list) -> str:
        """Extract domain/IP/URL from current message or backward chat history."""
        target = self._extract_target(message)
        if target and target != "unknown":
            return target

        for msg in reversed(chat_history or []):
            content = msg.get("content", "")
            t = self._extract_target(content)
            if t and t != "unknown":
                self.logger.info(f"Resolved target from history: {t}")
                return t

        return "unknown"

    @staticmethod
    def _extract_target(message: str) -> str:
        """Regex helper to extract domain, IP, or URL from text."""
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

    def _extract_code_blocks(self, text: str) -> list:
        """Regex helper to extract ``` blocks."""
        pattern = r"```(?:javascript|js|html)?(.*?)```"
        return re.findall(pattern, text, re.DOTALL)
