from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ValidationError

from ai_engine import ai_engine
from agents import ChatAgent, SecurityAgent, SystemAgent, ResearchAgent, CodeAgent, AuditAgent, ImageAgent, ObserverAgent, SearchAgent, AnalyzerAgent, OSINTAgent, EmailAgent, SchedulerAgent, DranaAgent, DorkingAgent, PentestAgent, PhantomAgent, LeakGraphAgent
from agents.agent_registry import agent_registry, AgentStatus
from memory.store import memory_store
from neural.core import neural_core
from config import settings

logger = logging.getLogger("aeris.hacker_brain")

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas for multi-task plan & Agentic Loop (Standalone definitions)
# ──────────────────────────────────────────────────────────────────────────────

class BrainTask(BaseModel):
    task_id: str
    intent: str       # chat | security | system | research | code | scheduler
    description: str  # Refined instruction for the agent
    dependencies: List[str] = []  # task_ids this task depends on


class BrainPlan(BaseModel):
    tasks: List[BrainTask]
    is_parallel: bool = False


class PlanStep(BaseModel):
    step_id: str
    tool_name: str
    args: Dict[str, Any] = {}
    description: str


class AgenticPlan(BaseModel):
    steps: List[PlanStep]
    reasoning: str


class Observation(BaseModel):
    step_id: str
    tool_name: str
    success: bool
    result: str
    error: Optional[str] = None
    duration_ms: float = 0.0


class Reflection(BaseModel):
    step_id: str
    thought: str
    should_continue: bool = True
    suggested_changes: Optional[List[PlanStep]] = None


class FinalResponse(BaseModel):
    text: str
    summary_of_actions: str


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions (Standalone definitions)
# ──────────────────────────────────────────────────────────────────────────────

async def query_llm_json(prompt: str, system_prompt: str = "You are a helpful assistant. Respond ONLY with valid JSON.") -> dict:
    """Query LLM and guarantee valid JSON response."""
    try:
        raw = await ai_engine.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            response_format={"type": "json_object"}
        )
        return json.loads(raw.strip())
    except Exception as e:
        logger.warning(f"Failed to query LLM JSON with response_format: {e}. Trying fallback cleaner.")
        try:
            raw = await ai_engine.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            clean = raw.strip().strip("```json").strip("```").strip()
            return json.loads(clean)
        except Exception as e2:
            logger.error(f"Fallback JSON parsing failed: {e2}")
            return {}


def parse_memory_command(message: str) -> Optional[str]:
    """Intercept and parse memory commands."""
    import re
    text = message.strip()
    m = re.match(r"^(remember\s+that|remember|forget\s+that|forget|update\s+memory)\s*:?\s*(.*)$", text, re.IGNORECASE)
    if not m:
        return None
        
    cmd, fact = m.groups()
    cmd = cmd.lower()
    fact = fact.strip()
    if not fact:
        return None
        
    from memory.store import memory_store
    
    if cmd in ["remember that", "remember"]:
        added = memory_store.add_fact(fact)
        if added:
            return f"I will remember that: \"{fact}\""
        else:
            return f"I already know that or it looks like sensitive information."
            
    elif cmd in ["forget that", "forget"]:
        removed = memory_store.remove_fact(fact)
        if removed:
            return f"I have forgotten: \"{fact}\""
        else:
            return f"I couldn't find a matching fact to forget."
            
    elif cmd == "update memory":
        added = memory_store.add_fact(fact)
        if added:
            return f"I have updated my memory with: \"{fact}\""
        else:
            return f"I already know that or it looks like sensitive information."
            
    return None


HACKER_PLANNER_PROMPT = """You are the Cybersecurity AI Planner for AERIS (Hacker Brain Mode).
Decompose the user's security request into a sequential plan of tool calls to achieve the goal.
For each step, specify the tool to call, the arguments (as a JSON object), and a short description.

AVAILABLE TOOLS:
{tools_summary}

WORKSPACE DIRECTORY: {workspace_dir}
All file paths for write_file/read_file/edit_file MUST be relative paths (e.g. "report.txt") or within the workspace directory above.
NEVER use paths like "C:/", "D:/", "/tmp", or any absolute path outside the workspace.

CRITICAL RULES:
- For ANY security-related request (SSL check, port scan, DNS lookup, recon, VAPT, vulnerability scan, WHOIS, subdomain enumeration), use the appropriate recon tool (e.g., `dns_lookup`, `subdomain_enum`, `port_scan`, `whois_lookup`, `header_analysis`, `ssl_check`).
- For sending email or mail notifications, ALWAYS use the `send_email` tool. Do NOT use `brevo_send_email` or `brevo_send_test_email` as they are meant for Brevo campaign/contact lists and will cause API authentication failures.
- If you need to search the web for CVE vulnerabilities, exploit databases, or threat intelligence, use `web_research` (which routes through the ResearchAgent) or `realtime_search` (which routes through the SearchAgent).
- If the user wants to schedule any security task, reminder, or periodic scan, use the `schedule_execution` tool.

CONVERSATION CONTEXT:
{history}
{memory_context}

USER PROFILE:
{profile_context}

USER MESSAGE: "{message}"

Respond with ONLY valid JSON matching this schema:
{{
  "steps": [
    {{
      "step_id": "s1",
      "tool_name": "<name of tool>",
      "args": {{ ... }},
      "description": "<what this step does>"
    }}
  ],
  "reasoning": "<short explanation of your plan>"
}}
"""

HACKER_FINAL_PROMPT = """You are AERIS — codename MYTHOS — operating in Hacker Brain Mode.
You are an elite ethical cyber-intelligence operator providing the final mission debrief.

USER MESSAGE: "{message}"

CONVERSATION HISTORY:
{history}

OPERATOR PROFILE:
{profile_context}

MEMORY CONTEXT:
{memory_context}

EXECUTED MISSION PLAN:
{plan_json}

OBSERVATIONS & TOOL OUTPUTS:
{observations_json}

MYTHOS PERSONA & RESPONSE RULES:
1. Address the user as "Sir" in every response. NEVER use "bhai", "bro", "buddy".
2. Maintain a dark, precise, technically-dense Hinglish persona. You are a cyber operator, not a chatbot.
3. Use correct English security terminology ("reconnaissance", "exfiltration vectors", "lateral movement", "privilege escalation", "CVE exploitation", "MITRE ATT&CK", "zero-day surface", "OPSEC") woven into natural Hinglish.
4. For EVERY finding, provide:
   - **Threat Score**: Rate 1-10 (1=info, 5=medium, 8=high, 10=critical)
   - **MITRE ATT&CK**: Reference the relevant technique ID if applicable (e.g., T1190 - Exploit Public-Facing Application)
   - **Operator Notes**: Your tactical assessment of what this means
   - **Remediation**: Concrete fix or mitigation steps
5. Auto-suggest the next logical reconnaissance step after findings.
6. Stay strictly within ethical boundaries. Explain vulnerabilities for defense. If asked for illegal actions, refuse and suggest defensive alternatives.
7. End security debriefs with a status summary: "Mission Status: [COMPLETE/PARTIAL/FAILED]"
8. Know the distinction between Modes and Agents: You have exactly 2 modes of operation: Normal Mode (Productivity Mode) and Hacker Mode (Hacker Brain Mode). You have multiple underlying agents (ChatAgent, OSINTAgent, LeakGraphAgent, etc.) that handle tasks. Do not confuse modes with agents.


PROACTIVE SCHEDULING RULES (CRITICAL):
- If a scan/query failed, suggest putting it in pending tasks: "Sir, recon attempt fail hua. Isko pending queue mein daalun aur 30 min baad retry karun?"

Respond with ONLY valid JSON:
{{
  "text": "<your tactical debrief response in Mythos Hinglish>",
  "summary_of_actions": "<mission summary>"
}}
"""

MULTI_TASK_PROMPT = """You are the routing brain of AERIS in Hacker Brain Mode.
Your ONLY job: decompose the user's message into an ordered execution plan.

AVAILABLE INTENTS:
- "chat"     : Casual conversation, greetings, general knowledge, jokes, math, definitions
- "security" : Port scanning, recon, vulnerability testing, VAPT, DNS lookup, SSL checks, zero-day analysis
- "system"   : Open/close apps, run shell commands, file operations, OS info, system control
- "research" : Deep academic research, synthesis of complex technical topics, multi-source information gathering
- "search"   : Realtime background web search (not opening a browser window), current events, news, live prices, trending topics, quick internet lookups, weather, user location (where am i), scraping
- "code"     : Write code, debug, explain code, refactor, generate scripts
- "image"    : Generate, create, or draw images/pictures/photos from a text description
- "diagram"  : Create flowcharts, system diagrams, architecture charts, mind maps, flow charts, graphs, charts, widgets
- "codepipeline" : Build an entire project/app autonomously, scaffold a workspace, create a full codebase
- "analyze"  : Analyze files, logs, data, code outputs, system state — find patterns, errors, insights, or summarize contents
- "osint"   : Public source investigations, profile gathering, social footprint mappings, email/username lookups, dynamic pivot investigations, target intel compilation
- "email"   : Send emails, send mail, compose and send mail via SMTP/Brevo relay
- "scheduler" : Retrieve lists of background tasks, schedule reminders/alarms/meetings, or cancel tasks by ID or keyword
- "drana"    : Bug bounty hunting, JS recon, manual VAPT, XSS payload generation, traffic analysis
- "dorking"  : Google dorking, advanced search operator queries, dork-based reconnaissance, targeted search query building and execution
- "pentest"  : Multi-phase penetration testing, vulnerability correlation, threat analysis, and security reports
- "phantom"  : Create ethical analytics tracking links (PhantomTrace), view link stats, list/delete tracked links
- "leakgraph" : Ethical recursive OSINT and public exposure analysis orchestrator

=== CONVERSATION HISTORY (last 3 messages) ===
{history}
=== END HISTORY ===

=== RECENT AGENT TASK EXECUTIONS ===
{recent_tasks}
=== END RECENT TASKS ===

CURRENT USER MESSAGE: "{message}"

Respond with ONLY valid JSON:
{{
  "tasks": [
    {{
      "task_id": "t1",
      "intent": "<one of the intents above>",
      "description": "<clear, standalone instruction — resolve any pronouns using history>",
      "dependencies": []
    }}
  ],
  "is_parallel": false
}}
"""

_KEYWORD_MAP: List[Tuple[List[str], str]] = [
    (["scan", "port", "recon", "vulnerability", "nmap", "ssl", "hack",
      "header", "fuzz", "whois", "dns", "subdomain"], "security"),
    ([
      "open ", "close ", "run ", "execute ", "shutdown", "restart",
      "screenshot", "kill process", "list files", "list directory",
      "system info", "disk space", "os info", "volume",
      "search on browser", "search the browser", "search on google",
      "google search", "search google", "open browser", "open chrome",
      "open edge", "browse to", "go to website",
      "on google", "in google", "google pe", "google par", "open google", "google open",
      "google par search", "google pe search", "google par dhoondo", "google pe dhoondo",
      "play ", "play a song", "play music", "play video",
      "youtube search", "search on youtube", "search youtube",
      "open youtube", "youtube pe", "youtube par",
     ], "system"),
    ([
      "schedule", "remind", "meeting", "alarm", "pending task", "daal do", "remind me",
      "cancel task", "list task", "list scheduled", "cancel scheduled", "task pending",
      "pending tasks", "remind me later", "meeting schedule"
     ], "scheduler"),
    (["search", "find out", "latest news", "who is ", "what is the latest",
      "current price", "weather", "trending", "look up",
      "realtime", "real-time", "live data", "right now", "today's",
      "what happened", "breaking news", "search for", "google it",
      "find me", "look for", "latest on", "current news", "my location", "where am i"], "search"),
    (["deep research", "academic research", "synthesize", "research paper",
      "technical research", "in-depth analysis", "compare technologies"], "research"),
    (["write code", "debug", "write a function", "write a script",
      "fix this code", "refactor", "explain this code",
      "generate a class", "create a flask", "create an api",
      "game banao", "code banao", "program banao", "script banao",
      "function banao", "api banao", "app banao", "website banao",
      "code likho", "program likho", "algorithm banao",
      "python mein", "javascript mein", "java mein",
      "mein banao", "mein bana do", "mein bana de",
    ], "code"),
    ([
      "generate image", "create image", "make image", "draw ",
      "generate a picture", "create a picture", "make a picture",
      "generate photo", "create photo", "make photo",
      "image of ", "picture of ", "photo of ",
      "photo de", "photo bana", "image bana", "tasveer",
      "phot de", "phot bana",
    ], "image"),
    ([
      "build a project", "build me a project", "build me an app",
      "create a project", "scaffold a project", "autonomous code",
      "create a workspace", "create workspace", "build an entire",
      "generate a full project", "full project", "code pipeline",
      "project bana", "project banao", "app bana do",
    ], "codepipeline"),
    ([
      "flowchart", "flow chart", "diagram", "chart", "mind map", "mindmap",
      "architecture diagram", "system diagram", "sequence diagram",
      "er diagram", "class diagram", "network diagram",
      "widget", "visualize", "visualise", "flow banao", "chart banao",
      "diagram banao", "diagram bana", "chart bana",
    ], "diagram"),
    ([
      "analyze", "analyse", "inspect", "diagnose", "summarize file",
      "analyze file", "analyse file", "check this file", "check this data",
      "parse this", "read and explain", "find issues in",
      "analyze karo", "analyse karo", "check karo", "dekhke batao",
      "file analyze", "log analyze", "data analyze", "analysis", "analysis karo"
    ], "analyze"),
    ([
      "osint", "investigate", "target intel", "email search", "username lookup",
      "social footprint", "trace target", "footprint check", "profile check",
      "target search", "profile trace", "stalk target", "stalk user", "recon target"
    ], "osint"),
    # ── Dorking Agent ─────────────────────────────────────────────────────────
    ([
      "dork", "dorking", "google dork", "google dorking", "dork search",
      "advanced dork", "dork karo", "dork kar", "dorking karo",
      "search dork", "dork query", "dork mode"
    ], "dorking"),
    ([
      "drana", "drafna", "js recon", "js analysis", "xss payload", "xss generate",
      "vapt analysis", "http analysis", "bug bounty", "pentest advice"
    ], "drana"),
    ([
      "send email", "send mail", "email to", "mail to", "email send", "mail send",
      "compose email", "compose mail", "mail bhejo", "email bhejo", "mail bhej", "email bhej"
    ], "email"),
    # ── Pentesting Agent ───────────────────────────────────────────────────────
    ([
      "pentest", "pentesting", "penetration test", "penetration testing", "pentest karo"
    ], "pentest"),
    # ── PhantomTrace Agent ─────────────────────────────────────────────────────
    (["phantom", "phantomtrace", "phantom trace", "tracking link", "track link",
      "create tracking", "link analytics", "link tracking", "tracked link",
      "phantom link", "phantom banao", "tracking link banao", "link track karo"
    ], "phantom"),
    # ── LeakGraph Agent ────────────────────────────────────────────────────────
    (["leakgraph", "leak graph", "recursive osint", "public exposure", "exposure analysis",
      "exposure scan", "public profile graph", "leak history", "credential leak"
    ], "leakgraph"),
]


def _keyword_route(text: str) -> Optional[str]:
    """Return an intent from keyword rules, or None if no match."""
    import re
    lower = text.lower()
    for keywords, intent in _KEYWORD_MAP:
        for kw in keywords:
            if kw.endswith(" "):
                pattern = r'\b' + re.escape(kw.rstrip()) + r'\b'
                if re.search(pattern, lower):
                    logger.debug(f"[HackerBrain] Keyword route → {intent} (kw='{kw}')")
                    return intent
            elif " " in kw or "-" in kw:
                if kw in lower:
                    logger.debug(f"[HackerBrain] Keyword route → {intent} (kw='{kw}')")
                    return intent
            else:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, lower):
                    logger.debug(f"[HackerBrain] Keyword route → {intent} (kw='{kw}')")
                    return intent
    return None


class HackerBrain:
    """
    Specialized standalone Hacker Brain orchestrator for AERIS.
    Has ALL the features of brain.py (swarm delegation, parallel execution, codepipelines)
    but tailored with high-vis cybersecurity templates and prompts.
    """

    NEURAL_CONFIDENCE_THRESHOLD = 0.80
    VALID_INTENTS = {"chat", "security", "system", "research", "search", "code", "image", "codepipeline", "diagram", "analyze", "osint", "email", "scheduler", "drana", "dorking", "pentest", "phantom", "leakgraph"}

    def __init__(self):
        # ── Instantiate all Core agents ──
        self.agents: Dict[str, Any] = {
            "chat":     ChatAgent(),
            "security": SecurityAgent(),
            "system":   SystemAgent(),
            "research": ResearchAgent(),
            "search":   SearchAgent(),
            "code":     CodeAgent(),
            "image":    ImageAgent(),
            "analyze":  AnalyzerAgent(),
            "osint":    OSINTAgent(),
            "email":    EmailAgent(),
            "scheduler": SchedulerAgent(),
            "drana":    DranaAgent(),
            "dorking":  DorkingAgent(),
            "pentest":  PentestAgent(),
            "phantom":  PhantomAgent(),
            "leakgraph": LeakGraphAgent(),
        }
        self.audit_agent = AuditAgent()
        self.observer_agent = ObserverAgent()

        # ── Register Core agents in the Universal Agent Registry ──
        for intent, agent in self.agents.items():
            agent_registry.register(agent)
        agent_registry.register(self.audit_agent)
        agent_registry.register(self.observer_agent)

        # ── Register Swarm Sub-Agents under ProjectBuilder ──
        try:
            from agents.project_builder import ProjectBuilderSystem
            from agents.proactive_agent import ProactiveAgent

            pb = ProjectBuilderSystem()
            agent_registry.register(pb)

            pa = ProactiveAgent()
            agent_registry.register(pa)

            # Sub-agents (workers in the Swarm)
            from agents.sub_agents import (
                DelegatorAgent, CodingAgent as SwarmCodingAgent,
                ResearchAgent as SwarmResearchAgent, AnalysisAgent,
                VulnerabilityAgent, ToolManagerAgent, RuntimeAgent,
                ArchitectureAgent, DocumentationAgent,
            )
            sub_agents_meta = [
                ("AnalysisAgent",       "analysis", ["Requirement Parsing", "Dependency Mapping"]),
                ("ArchitectureAgent",   "architecture", ["File Structure Design", "Stack Selection"]),
                ("SwarmCodingAgent",    "code", ["Python/JS Implementation", "Multi-file Code Generation"]),
                ("SwarmResearchAgent",  "research", ["Technical Research", "Library Comparison"]),
                ("DocumentationAgent",  "docs", ["README Generation", "API Documentation"]),
                ("VulnerabilityAgent",  "security", ["Static Code Analysis", "Security Hardening"]),
                ("RuntimeAgent",        "runtime", ["Sandbox Testing", "Code Execution Validation"]),
                ("ToolManagerAgent",    "tools", ["Dynamic Tool Creation", "Tool Registry Management"]),
                ("DelegatorAgent",      "delegation", ["Task Routing", "Agent Orchestration"]),
            ]
            for sa_name, domain, caps in sub_agents_meta:
                # Create a lightweight metadata-only registration
                class _SubAgentStub:
                    def __init__(self, n, d, c):
                        self.name = n
                        self.description = f"Swarm sub-agent: {d}"
                        self.task_domain = d
                        self.version = "1.0.0"
                        self.capabilities = c
                    def health_check(self):
                        return True
                agent_registry.register(_SubAgentStub(sa_name, domain, caps), parent="ProjectBuilderSystem")

            logger.info(f"[HackerBrain] Registered {len(agent_registry)} agents in AgentRegistry (Core + Sub-Agents).")
        except Exception as e:
            logger.warning(f"[HackerBrain] Sub-agent registration partial: {e}")

        logger.info("[HackerBrain] Initialized standalone HackerBrain with all core agents.")

    def get_system_health(self) -> dict:
        """Return the full health status of all agents."""
        agent_registry.run_health_checks()
        return {
            "total_agents": len(agent_registry),
            "statuses": agent_registry.get_all_statuses(),
            "summary": agent_registry.get_capabilities_summary(),
        }

    def get_capabilities_for_prompt(self) -> str:
        """Return a capabilities summary string for injection into LLM prompts."""
        return agent_registry.get_capabilities_summary()

    async def approve_agent_delegation(self, requester_name: str, target_name: str, purpose: str) -> bool:
        """Evaluate and approve/deny a delegation request from one agent to another."""
        # Auto-approve delegation for PentestAgent and DranaAgent
        if requester_name in ("PentestAgent", "DranaAgent") or target_name in ("PentestAgent", "DranaAgent"):
            logger.info(f"[HackerBrain] Auto-approved delegation: {requester_name} -> {target_name} ({purpose[:60]}...)")
            return True

        prompt = (
            f"You are the central AERIS central central central центральный Brain. An agent is requesting permission to use another agent.\n\n"
            f"Requester Agent: {requester_name}\n"
            f"Target Agent to Use: {target_name}\n"
            f"Purpose / Task: {purpose}\n\n"
            f"Evaluate if this delegation is logical, safe, and appropriate for the task.\n"
            f"Respond with ONLY JSON:\n"
            f"{{\n"
            f"  \"approved\": true or false,\n"
            f"  \"reason\": \"brief explanation\"\n"
            f"}}"
        )
        try:
            response = await ai_engine.classify(prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1] if "\n" in response else response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()
            decision = json.loads(response)
            approved = decision.get("approved", False)
            logger.info(f"[HackerBrain] Central central central Delegation request: {requester_name} -> {target_name} | Approved: {approved}")
            return approved
        except Exception as e:
            logger.warning(f"[HackerBrain] Error evaluating central delegation: {e}. Defaulting to True.")
            return True

    def _build_history_summary(self, limit: int = 3) -> str:
        """Format last N memory messages as a compact context string for LLM prompts."""
        try:
            history = memory_store.get_context(limit)
            if not history:
                return "No prior conversation."
            lines = []
            for msg in history:
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")[:180]
                lines.append(f"[{role}]: {content}")
            return "\n".join(lines)
        except Exception:
            return "No prior conversation."

    def _build_recent_tasks_summary(self, limit: int = 3) -> str:
        """Format the last few task execution details for LLM context."""
        try:
            results = memory_store.task_results
            if not results:
                return "No recent tasks executed."
            
            sorted_tasks = sorted(
                results.items(),
                key=lambda x: x[1].get("stored_at", ""),
                reverse=True
            )[:limit]
            
            lines = []
            for task_id, data in reversed(sorted_tasks):
                for t in data.get("tasks", []):
                    intent = t.get("intent", "unknown").upper()
                    agent = t.get("agent", "unknown")
                    success = "SUCCESS" if t.get("success") else "FAILED"
                    resp_snippet = str(t.get("response", ""))[:200].replace("\n", " ").strip()
                    lines.append(
                        f"- [{intent}] by {agent} -> Status: {success}. Response: {resp_snippet}"
                    )
            return "\n".join(lines) if lines else "No recent tasks executed."
        except Exception as e:
            logger.warning(f"[HackerBrain] Failed to build task summary: {e}")
            return "No recent tasks executed."

    async def _classify_intent(self, message: str) -> str:
        """Single-intent classification with conversation context."""
        # Keyword override check for strong intents like pentest/dorking/drana/osint/leakgraph
        keyword_intent = _keyword_route(message)
        if keyword_intent in ("pentest", "dorking", "drana", "osint", "leakgraph"):
            logger.info(f"[HackerBrain] Keyword override routing -> '{keyword_intent}'")
            return keyword_intent

        # 1. Neural ML fast-route (high confidence only)
        if neural_core.is_intent_ready:
            try:
                label, confidence = neural_core.predict_intent_from_text(message)
                if label in self.VALID_INTENTS and confidence >= 0.85:
                    logger.info(f"[HackerBrain] Neural fast-route -> '{label}' (conf={confidence:.2f})")
                    return label
            except Exception as e:
                logger.warning(f"[HackerBrain] Neural routing failed: {e}")

        # 2. LLM classification
        history_summary = self._build_history_summary(3)
        recent_tasks_summary = self._build_recent_tasks_summary(3)
        try:
            raw = await ai_engine.classify(
                f"You are an intent classifier for AERIS Hacker Brain Mode. Classify the following user message into EXACTLY ONE intent.\n\n"
                f"INTENTS:\n"
                f"- chat     : Casual conversation, greetings, general knowledge, jokes, math, definitions\n"
                f"- security : Port scanning, network recon, vulnerability scanning, DNS lookup, SSL checks, zero-day analysis\n"
                f"- system   : Open/close apps, run shell commands, file operations, OS info, system control, browser navigation (opening browser to search Google/YouTube), playing music/videos\n"
                f"- research : Deep academic/technical research, multi-source synthesis of complex topics, research papers\n"
                f"- search   : Realtime background web search (not opening a browser window), current events, breaking news, live prices, trending topics, quick internet lookups, weather, user location/where am i, web scraping\n"
                f"- code     : Write code, debug, explain code, refactor, generate scripts\n"
                f"- image    : Generate, create, draw, or produce images/pictures/photos/art from a text description\n"
                f"- diagram  : Create flowcharts, system diagrams, architecture charts, mind maps, charts, graphs, widgets — ANY visual data structure or flow diagram\n"
                f"- codepipeline : Build an entire project/app autonomously, scaffold a workspace, generate a full codebase\n"
                f"- analyze  : Analyze files, logs, data, code outputs, system state — find patterns, errors, insights, or summarize contents of files\n"
                f"- osint    : Public source investigations, profile gathering, social footprint mappings, email/username lookups, dynamic pivot investigations, target intel compilation (when the user asks for info/details on a target or person without explicitly requesting dork/dorking)\n"
                f"- email    : Send emails, send mail, compose and send mail via SMTP/Brevo relay\n"
                f"- scheduler : Retrieve lists of background tasks, schedule reminders/alarms/meetings, or cancel tasks by ID or keyword\n"
                f"- drana    : Bug bounty hunting, JS recon, manual VAPT, XSS payload generation, traffic analysis\n"
                f"- dorking  : Google dorking, advanced search operator queries. ONLY use if the user explicitly mentions 'dork', 'dorking', 'google dork', or requests advanced search operators like filetype, intitle, inurl\n"
                f"- pentest  : Multi-phase penetration testing, vulnerability correlation, threat analysis, and security reports\n"
                f"- phantom  : Create ethical analytics tracking links (PhantomTrace), view link statistics, list/delete tracked links\n"
                f"- leakgraph : Ethical recursive OSINT and public exposure analysis orchestrator\n\n"
                f"FEW-SHOT EXAMPLES:\n"
                f"- \"anuj raghuwanshi bhopal ki detail info chahiye\" -> osint (reason: target profile lookup without explicit dorking request)\n"
                f"- \"anuj raghuwanshi bhopal par google dorking karo\" -> dorking (reason: explicitly requests google dorking)\n"
                f"- \"search sambhav mehra on google\" -> system (reason: requests opening a browser to search google)\n"
                f"- \"what is gravity?\" -> chat (reason: general knowledge definition)\n\n"
                f"The message may be in ANY language (English, Hindi, Hinglish, etc). Understand the MEANING, not just keywords.\n"
                f"Use the conversation history to resolve follow-up queries and pronouns (e.g., 'it', 'that', 'iska').\n\n"
                f"=== CONVERSATION HISTORY (last 3 messages) ===\n{history_summary}\n=== END HISTORY ===\n\n"
                f"=== RECENT AGENT TASK EXECUTIONS ===\n{recent_tasks_summary}\n=== END RECENT TASKS ===\n\n"
                f'Current user message: "{message}"\n\n'
                f'Respond with ONLY valid JSON: {{"intent": "<one of: chat, security, system, research, search, code, image, diagram, codepipeline, analyze, osint, email, scheduler, drana, dorking, pentest, phantom, leakgraph>", "reason": "<brief explanation>"}}'
            )
            raw = raw.strip().strip("```json").strip("```").strip()
            data = json.loads(raw)
            intent = data.get("intent", "chat")
            if intent in self.VALID_INTENTS:
                logger.info(f"[HackerBrain] LLM classify -> '{intent}'")
                return intent
        except Exception as e:
            logger.warning(f"[HackerBrain] LLM classify failed: {e}")

        # 3. Keyword fallback — only if LLM failed
        keyword_intent = _keyword_route(message)
        if keyword_intent:
            logger.info(f"[HackerBrain] Keyword fallback -> '{keyword_intent}'")
            return keyword_intent

        logger.warning("[HackerBrain] All classifiers failed. Defaulting to 'chat'.")
        return "chat"

    async def _plan_multi_task(self, message: str) -> BrainPlan:
        """Use LLM to parse complex, multi-step queries into a BrainPlan."""
        history_summary = self._build_history_summary(3)
        recent_tasks_summary = self._build_recent_tasks_summary(3)
        try:
            raw = await ai_engine.classify(
                MULTI_TASK_PROMPT.format(message=message, history=history_summary, recent_tasks=recent_tasks_summary)
            )
            raw = raw.strip().strip("```json").strip("```").strip()
            plan = BrainPlan(**json.loads(raw))
            for t in plan.tasks:
                if t.intent not in self.VALID_INTENTS:
                    t.intent = "chat"
            logger.info(f"[HackerBrain] Multi-task plan: {len(plan.tasks)} task(s)")
            return plan
        except Exception as e:
            logger.warning(f"[HackerBrain] Multi-task plan failed ({e}), fallback single-task plan.")
            intent = await self._classify_intent(message)
            return BrainPlan(
                tasks=[BrainTask(task_id="t1", intent=intent, description=message)],
                is_parallel=False,
            )

    def _is_complex_query(self, message: str) -> bool:
        """Heuristic: check if this is a multi-step request."""
        lower = message.lower()
        conjunctions = [" and then ", " after that ", " also ", " additionally ", " then ", " next ", " followed by ",
                        " aur ", " phir ", " uske baad ", " karke ", " karne ke baad ", " fir ", " also "]
        if any(sig in lower for sig in conjunctions):
            return True
        if len(message) > 150:
            return True
        return False

    async def _run_task(self, task: BrainTask, context: dict, step_idx: int, total: int) -> dict:
        """Execute a single BrainTask through the appropriate agent."""
        logger.info(f"[HackerBrain] Task {step_idx + 1}/{total}: intent='{task.intent}' — {task.description[:80]}")

        # Handle diagram intent
        if task.intent == "diagram":
            try:
                from agents.diagram_agent import get_diagram_agent
                agent = get_diagram_agent()
                response = await agent.generate(task.description)
                return {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "DiagramAgent",
                    "response": response,
                    "success": True, "execution_time": 0.0,
                }
            except Exception as e:
                return {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "DiagramAgent",
                    "response": f"Could not generate diagram: {e}",
                    "success": False, "execution_time": 0.0, "error": str(e),
                }

        # Handle codepipeline intent
        if task.intent == "codepipeline":
            try:
                from agents.planner_agent import PlannerAgent
                from agents.verifier_agent import VerifierAgent
                from agents.sub_agents.coding_agent import CodingAgent as SwarmCoder
                import json as _json

                planner = PlannerAgent()
                manifest = await planner.plan_workspace(task.description)
                scaffold = planner.scaffold_workspace(manifest)

                coder = SwarmCoder(enable_validation=True, enable_cache=False)
                project_path = scaffold["project_path"]
                arch_summary = _json.dumps(manifest.to_dict(), indent=2)
                written = []
                for fs in manifest.files:
                    obj = (f"Generate COMPLETE code for: {fs.path}\n"
                           f"Description: {fs.description}\nProject: {task.description}\n"
                           f"Blueprint:\n{arch_summary}")
                    try:
                        res = await coder.generate_code_async(request=obj, language=fs.language or manifest.language)
                        content = res.get("code") or ""
                        if not content:
                            for ff in res.get("files", []):
                                if isinstance(ff, dict) and ff.get("content"):
                                    content = ff["content"]; break
                        if content and len(content.strip()) > 10:
                            from pathlib import Path as P
                            ap = P(project_path) / fs.path
                            ap.parent.mkdir(parents=True, exist_ok=True)
                            ap.write_text(content, encoding="utf-8")
                            written.append(fs.path)
                    except Exception as e:
                        logger.warning(f"[HackerBrain] Scaffold: failed {fs.path}: {e}")

                verifier = VerifierAgent()
                report = await verifier.verify_workspace(project_path, manifest.entry_point, manifest.language)

                summary_parts = [
                    f"📐 **Project: {manifest.project_name}**",
                    f"Language: {manifest.language} | Stack: {', '.join(manifest.tech_stack)}",
                    f"Entry: `{manifest.entry_point}` | Run: `{manifest.run_command}`",
                    f"\n**Files Generated ({len(written)}):**",
                    *[f"  • {w}" for w in written],
                    f"\n**Verification: {'✅ PASSED' if report.passed else '❌ FAILED'}**",
                ]
                if report.llm_review:
                    summary_parts.append(f"\n**AI Review:**\n{report.llm_review[:500]}")
                summary_parts.append(f"\n📂 Saved to: `{project_path}`")

                return {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "CodePipeline",
                    "response": "\n".join(summary_parts),
                    "success": True, "execution_time": 0.0,
                }
            except Exception as e:
                logger.error(f"[HackerBrain] CodePipeline failed: {e}")
                return {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "CodePipeline",
                    "response": f"Code pipeline encountered an error: {str(e)}",
                    "success": False, "execution_time": 0.0, "error": str(e),
                }

        agent = self.agents.get(task.intent, self.agents["chat"])
        try:
            result = await agent.run(task.description, context)
            return {
                "task_id": task.task_id,
                "intent": task.intent,
                "agent": agent.name,
                "response": result.get("response", ""),
                "success": result.get("success", True),
                "execution_time": result.get("execution_time", 0.0),
                "error": result.get("error"),
            }
        except Exception as e:
            logger.error(f"[HackerBrain] Task '{task.task_id}' raised exception: {e}")
            return {
                "task_id": task.task_id,
                "intent": task.intent,
                "agent": agent.name,
                "response": f"Sir, task process karte waqt error aaya: {str(e)}",
                "success": False,
                "execution_time": 0.0,
                "error": str(e),
            }

    async def _execute_plan(self, plan: BrainPlan, base_context: dict) -> List[dict]:
        """Execute all tasks in a BrainPlan — sequentially or in parallel."""
        results: List[dict] = []
        total = len(plan.tasks)

        if plan.is_parallel and total > 1:
            logger.info("[HackerBrain] Running tasks in PARALLEL.")
            coros = [
                self._run_task(task, base_context, i, total)
                for i, task in enumerate(plan.tasks)
            ]
            raw = await asyncio.gather(*coros, return_exceptions=True)
            for r in raw:
                if isinstance(r, Exception):
                    results.append({"success": False, "response": str(r), "error": str(r)})
                else:
                    results.append(r)
        else:
            logger.info("[HackerBrain] Running tasks SEQUENTIALLY.")
            accumulated_context = ""
            for i, task in enumerate(plan.tasks):
                ctx = dict(base_context)
                if accumulated_context:
                    ctx["prior_step_context"] = accumulated_context

                result = await self._run_task(task, ctx, i, total)
                results.append(result)

                if result["success"]:
                    snippet = result["response"][:600]
                    accumulated_context += f"\n--- [{task.intent.upper()}] ---\n{snippet}\n"

                    import re
                    paths_found = re.findall(r'[A-Za-z]:\\[^\s\n\r\'"<>|]+\.\w+', snippet)
                    if paths_found:
                        accumulated_context += f"\n[FILE_PATHS_FOUND]: {'; '.join(paths_found)}\n"

        return results

    async def execute_agentic_loop(self, message: str, pending_state: Optional[dict] = None, task_id: Optional[str] = None) -> dict:
        """
        Execute the agentic loop: plan -> tool call -> observe -> reflect -> final response.
        Uses Hacker Brain customized templates.
        """
        start = time.time()
        task_id = task_id or (pending_state.get("task_id") if pending_state else f"task_{int(time.time())}")
        self._retry_counts = {}
        workspace_dir = str(settings.WORKSPACE_DIR)

        # 1. Plan / Resume Plan
        if pending_state:
            plan_dict = pending_state.get("plan")
            plan = AgenticPlan(**plan_dict)
            current_step_index = pending_state.get("current_step_index", 0)
            observations = [Observation(**obs) for obs in pending_state.get("observations", [])]
            logger.info(f"[HackerBrain] Resuming agentic plan execution from step {current_step_index}")
        else:
            # Classification
            intent = await self._classify_intent(message)
            logger.info(f"[HackerBrain] Plan Generation intent classification: {intent}")

            # Tool Retrieval
            from tools.universal_registry import get_universal_registry
            from intelligence.selection_intelligence import get_selection_intelligence

            selection_intel = get_selection_intelligence()
            retrieved_candidates = selection_intel.select(message, intent=intent, top_k=10)
            retrieved_names = {c.tool_name for c in retrieved_candidates}

            # Prioritize security tools in selection
            security_recon_tools = {
                "dns_lookup", "whois_lookup", "port_scan", "header_analysis",
                "ssl_check", "subdomain_enum", "chat_with_ai", "run_bash",
                "read_file", "write_file", "edit_file", "web_research",
                "realtime_search", "schedule_execution", "read_system_file",
                "find_system_file", "list_system_dir"
            }
            selected_names = retrieved_names.union(security_recon_tools)

            registry = get_universal_registry()
            selected_tools = []
            for name in selected_names:
                tool_def = registry.get_tool(name)
                if tool_def and tool_def.is_enabled:
                    selected_tools.append(tool_def)

            tools_summary = "\n".join(t.to_llm_string() for t in selected_tools)
            all_tools_count = len(registry.get_enabled_tools())
            logger.info(f"[HackerBrain] Retracted tools list from {all_tools_count} to {len(selected_tools)}")

            history = self._build_history_summary(10)
            memory_context = memory_store.get_relevant_memory_context(message)

            from memory.user_profile import user_profile_store
            profile = user_profile_store.get_profile()
            profile_context = (
                f"User's Name: {profile.get('name', settings.USERNAME)}\n"
                f"Language Preference: {profile.get('language_preference', 'Hinglish')}\n"
                f"Tone Preference: {profile.get('tone_preference', 'natural agentic')}\n"
                f"Preferred Response Style: {profile.get('preferred_response_style', '')}"
            )

            prompt = HACKER_PLANNER_PROMPT.format(
                tools_summary=tools_summary,
                history=history,
                memory_context=memory_context,
                profile_context=profile_context,
                message=message,
                workspace_dir=workspace_dir
            )

            plan_data = await query_llm_json(prompt, system_prompt="You are a cybersecurity AI planner. Respond ONLY with valid JSON.")
            if not plan_data or "steps" not in plan_data:
                raise ValueError("LLM failed to generate a valid security plan structure.")

            plan = AgenticPlan(**plan_data)
            current_step_index = 0
            observations = []
            logger.info(f"[HackerBrain] Generated new security agentic plan with {len(plan.steps)} step(s)")

        # 2. Loop Execution
        while current_step_index < len(plan.steps):
            step = plan.steps[current_step_index]

            # If this is a background job, update its progress
            from services.job_manager import get_job_manager
            job_mgr = get_job_manager()
            if job_mgr.get_job(task_id):
                progress_pct = int((current_step_index / len(plan.steps)) * 100)
                job_mgr.update_job(
                    task_id,
                    status="running",
                    current_agent=step.tool_name,
                    progress=progress_pct,
                    event=f"Executing step {current_step_index + 1}/{len(plan.steps)}: {step.tool_name} - {step.description}"
                )

            from tools.universal_registry import get_universal_registry
            from tools.tool_permissions import get_permission_system

            tool_def = get_universal_registry().get_tool(step.tool_name)
            if not tool_def:
                obs = Observation(
                    step_id=step.step_id,
                    tool_name=step.tool_name,
                    success=False,
                    result="",
                    error=f"Tool '{step.tool_name}' not found in registry.",
                    duration_ms=0.0
                )
                observations.append(obs)
                current_step_index += 1
                continue

            decision = get_permission_system().check(tool_def, step.args)
            if not decision.allowed:
                if decision.requires_user_approval:
                    # If this is a background job, update status to paused
                    from services.job_manager import get_job_manager
                    job_mgr = get_job_manager()
                    if job_mgr.get_job(task_id):
                        job_mgr.update_job(
                            task_id,
                            status="paused",
                            event=f"Job paused. Security Check: Executing '{step.tool_name}' requires approval."
                        )
                        from services.notification_hub import notify_job_status
                        asyncio.create_task(notify_job_status(
                            task_id,
                            status="paused",
                            event=f"Security Check: Executing '{step.tool_name}' requires approval. Reason: {decision.reason}"
                        ))
                    pending_file = settings.DATA_DIR / "pending_approval.json"
                    state_to_save = {
                        "plan": plan.dict(),
                        "message": message,
                        "current_step_index": current_step_index,
                        "observations": [obs.dict() for obs in observations],
                        "tool_name_pending": step.tool_name,
                        "args_pending": step.args,
                        "task_id": task_id,
                        "agent": "HackerBrain"
                    }
                    pending_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(pending_file, "w", encoding="utf-8") as f:
                        json.dump(state_to_save, f, indent=2)

                    return {
                        "response": (
                            f"🛡️ **Security Check**: Executing `{step.tool_name}` requires your approval.\n"
                            f"**Reason**: {decision.reason}\n"
                            f"**Arguments**: `{json.dumps(step.args, indent=2)}`\n\n"
                            f"Reply with **'yes'** or **'approve'** to execute, or **'no'** / **'cancel'** to abort."
                        ),
                        "intent": "system",
                        "agent": "HackerBrain",
                        "tasks_executed": current_step_index,
                        "tasks_succeeded": sum(1 for o in observations if o.success),
                        "tasks_failed": sum(1 for o in observations if not o.success),
                        "execution_time": round(time.time() - start, 2),
                        "success": False,
                        "task_id": task_id,
                        "requires_approval": True,
                        "tool_name_pending": step.tool_name
                    }
                else:
                    obs = Observation(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=False,
                        result="",
                        error=f"SECURITY_BLOCKED: {decision.reason}",
                        duration_ms=0.0
                    )
                    observations.append(obs)
                    current_step_index += 1
                    continue

            sanitized_args = dict(step.args)
            if step.tool_name in ("write_file", "edit_file", "read_file") and "path" in sanitized_args:
                raw_path = sanitized_args["path"]
                ws_dir = Path(settings.WORKSPACE_DIR)
                resolved = Path(raw_path).resolve() if Path(raw_path).is_absolute() else (ws_dir / raw_path).resolve()
                try:
                    resolved.relative_to(ws_dir.resolve())
                except ValueError:
                    sanitized_args["path"] = Path(raw_path).name

            skip_execution = False
            if tool_def and tool_def.input_schema:
                missing = [p.name for p in tool_def.input_schema.params if p.required and p.name not in sanitized_args]
                if missing:
                    obs = Observation(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=False,
                        result="",
                        error=f"Missing required arguments: {', '.join(missing)}",
                        duration_ms=0.0
                    )
                    skip_execution = True

            step.args = sanitized_args

            if not skip_execution:
                start_time = time.perf_counter()
                try:
                    from tools.tool_executor import get_executor_service
                    executor = get_executor_service()
                    result = executor.execute(
                        tool_name=step.tool_name,
                        task_id=task_id,
                        step_id=step.step_id,
                        **step.args
                    )
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    obs = Observation(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=result.success,
                        result=result.stdout if result.success else "",
                        error=result.stderr if not result.success else None,
                        duration_ms=elapsed_ms
                    )
                except Exception as e:
                    elapsed_ms = (time.perf_counter() - start_time) * 1000
                    obs = Observation(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=False,
                        result="",
                        error=str(e),
                        duration_ms=elapsed_ms
                    )

            observations.append(obs)
            current_step_index += 1

            if not obs.success:
                reflection_prompt = f"""You are the Central AI Reflector — self-correct failures.

ORIGINAL PLAN:
{json.dumps(plan.dict(), indent=2)}

OBSERVATIONS SO FAR:
{json.dumps([o.dict() for o in observations], indent=2)}

WORKSPACE DIRECTORY: {workspace_dir}
CURRENT STEP ID: {step.step_id}

Analyze the LAST observation and adjust:
1. If arguments are invalid/missing, suggest a corrected retry step with same tool but fixed args.
2. If blocked by security, skip and continue. Do not infinite retry.
3. If files are not found, correct the paths.

Respond with ONLY valid JSON:
{{
  "step_id": "{step.step_id}",
  "thought": "<your analysis>",
  "should_continue": true,
  "suggested_changes": null or [{{"step_id": "retry_1", "tool_name": "tool_name", "args": {{}}, "description": "description"}}]
}}
"""
                ref_data = await query_llm_json(reflection_prompt, system_prompt="You are a central AI reflector. Respond ONLY with valid JSON.")
                if ref_data:
                    try:
                        suggested = ref_data.get("suggested_changes")
                        if isinstance(suggested, dict):
                            if "steps" in suggested:
                                ref_data["suggested_changes"] = suggested["steps"]
                            elif "new_plan" in suggested and isinstance(suggested["new_plan"], dict) and "steps" in suggested["new_plan"]:
                                ref_data["suggested_changes"] = suggested["new_plan"]["steps"]
                            else:
                                ref_data["suggested_changes"] = None

                        if not ref_data.get("suggested_changes"):
                            if "new_plan" in ref_data and isinstance(ref_data["new_plan"], dict) and "steps" in ref_data["new_plan"]:
                                ref_data["suggested_changes"] = ref_data["new_plan"]["steps"]
                            elif "steps" in ref_data and isinstance(ref_data["steps"], list):
                                ref_data["suggested_changes"] = ref_data["steps"]

                        reflection = Reflection(**ref_data)
                        logger.info(f"[HackerBrain] Reflection step {step.step_id}: {reflection.thought}")

                        retry_key = f"{step.step_id}_{step.tool_name}"
                        if not reflection.should_continue:
                            if not obs.success and self._retry_counts.get(retry_key, 0) < 2 and reflection.suggested_changes:
                                self._retry_counts[retry_key] = self._retry_counts.get(retry_key, 0) + 1
                                plan.steps = plan.steps[:current_step_index] + reflection.suggested_changes
                            else:
                                break
                        elif reflection.suggested_changes:
                            self._retry_counts[retry_key] = self._retry_counts.get(retry_key, 0) + 1
                            if self._retry_counts[retry_key] <= 2:
                                plan.steps = plan.steps[:current_step_index] + reflection.suggested_changes
                    except Exception as re_err:
                        logger.warning(f"Failed to parse hacker reflection: {re_err}")

        # 3. Final Response Generation
        history = self._build_history_summary(10)
        memory_context = memory_store.get_memory_context()

        from memory.user_profile import user_profile_store
        profile = user_profile_store.get_profile()
        profile_context = (
            f"User's Name: {profile.get('name', settings.USERNAME)}\n"
            f"Language Preference: {profile.get('language_preference', 'Hinglish')}\n"
            f"Tone Preference: {profile.get('tone_preference', 'natural agentic')}\n"
            f"Preferred Response Style: {profile.get('preferred_response_style', '')}"
        )

        final_prompt = HACKER_FINAL_PROMPT.format(
            message=message,
            history=history,
            profile_context=profile_context,
            memory_context=memory_context,
            plan_json=json.dumps(plan.dict(), indent=2),
            observations_json=json.dumps([o.dict() for o in observations], indent=2)
        )

        is_blocked = False
        blocked_reason = ""
        for obs in observations:
            if obs.error and "SECURITY_BLOCKED" in obs.error:
                is_blocked = True
                blocked_reason = obs.error
                break

        if is_blocked:
            text_resp = f"🛡️ SECURITY_BLOCKED: The request was blocked because it violates security boundaries: {blocked_reason}"
            summary_actions = f"Blocked execution of tool due to security policy."
        else:
            final_data = await query_llm_json(final_prompt, system_prompt="You are AERIS in Hacker Brain Mode. Respond ONLY with valid JSON.")
            if not final_data or "text" not in final_data:
                text_resp = "Sir, security assessment complete ho gayi hai."
                summary_actions = "Security execution complete."
            else:
                # Safe normalization of summary_of_actions to string to prevent validation errors
                if "summary_of_actions" in final_data and not isinstance(final_data["summary_of_actions"], str):
                    if isinstance(final_data["summary_of_actions"], dict):
                        final_data["summary_of_actions"] = json.dumps(final_data["summary_of_actions"])
                    else:
                        final_data["summary_of_actions"] = str(final_data["summary_of_actions"])
                
                final_response = FinalResponse(**final_data)
                text_resp = final_response.text
                summary_actions = final_response.summary_of_actions

        elapsed = round(time.time() - start, 2)
        succeeded = [o for o in observations if o.success]
        failed = [o for o in observations if not o.success]

        primary_tool = observations[0].tool_name if observations else "none"

        memory_store.add_message(
            "assistant",
            text_resp,
            {
                "agent": "HackerBrain",
                "tasks": len(observations),
                "execution_time": elapsed,
                "intent": primary_tool,
            },
        )

        # If this is a background job, update its completion
        from services.job_manager import get_job_manager
        job_mgr = get_job_manager()
        if job_mgr.get_job(task_id):
            status = "completed" if len(failed) == 0 else "failed"
            error_msg = failed[0].error if failed else None
            job_mgr.update_job(
                task_id,
                status=status,
                progress=100,
                final_result=text_resp,
                error=error_msg,
                event=f"Job execution completed with status: {status}."
            )
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(
                task_id,
                status=status,
                event=f"Job execution completed with status: {status}.",
                results=text_resp
            ))

        return {
            "response": text_resp,
            "intent": primary_tool,
            "agent": "HackerBrain",
            "tasks_executed": len(observations),
            "tasks_succeeded": len(succeeded),
            "tasks_failed": len(failed),
            "execution_time": elapsed,
            "success": len(failed) == 0,
            "task_id": task_id,
            "summary": summary_actions,
        }

    async def process(self, message: str) -> dict:
        """
        Specialized process router for Hacker Brain.
        Intercepts toggles, memory commands, checks approvals, and executes.
        """
        lower_msg = message.lower()

        # Check if the user query requests auto-repair of workspace syntax errors
        from services.workspace_watcher import handle_conversational_repair
        repair_res = await handle_conversational_repair(message)
        if repair_res:
            # Change agent key to HackerBrain to reflect hacker mode identity
            repair_res["agent"] = "HackerBrain"
            return repair_res

        # Check if the user query is a status check or cancellation of a background job
        from services.job_manager import get_job_manager
        job_mgr = get_job_manager()
        
        import re
        job_id_match = re.search(r'\b(job_\d+)\b', lower_msg)
        
        if job_id_match:
            job_id = job_id_match.group(1)
            # 1. Cancel request
            if any(w in lower_msg for w in ("cancel", "stop", "kill", "abort", "band karo")):
                success = job_mgr.cancel_job(job_id)
                response_text = f"Sir, I have cancelled the background job `{job_id}`." if success else f"Sir, I could not find a running background job with ID `{job_id}`."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "chat",
                    "agent": "HackerBrain",
                    "success": success,
                    "task_id": job_id
                }
            # 2. Pause request
            elif "pause" in lower_msg:
                success = job_mgr.pause_job(job_id)
                response_text = f"Sir, I have paused the background job `{job_id}`." if success else f"Sir, I could not find a running background job with ID `{job_id}`."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "chat",
                    "agent": "HackerBrain",
                    "success": success,
                    "task_id": job_id
                }
            # 3. Resume request
            elif any(w in lower_msg for w in ("resume", "chalu", "continue")):
                success = job_mgr.resume_job(job_id)
                if success:
                    # Check if there is pending approval to resume from
                    pending_file = settings.DATA_DIR / "pending_approval.json"
                    state = None
                    if pending_file.exists():
                        try:
                            with open(pending_file, "r", encoding="utf-8") as f:
                                state = json.load(f)
                        except Exception:
                            pass
                    
                    if state and state.get("task_id") == job_id:
                        try:
                            pending_file.unlink()
                        except Exception:
                            pass
                        asyncio.create_task(self._run_background_job_resume(job_id, state))
                        response_text = f"Sir, I have resumed the background job `{job_id}`."
                    else:
                        response_text = f"Sir, job `{job_id}` status has been set to queued and will be processed."
                else:
                    response_text = f"Sir, job `{job_id}` is not in a paused state."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "chat",
                    "agent": "HackerBrain",
                    "success": success,
                    "task_id": job_id
                }
            # 4. Status check for specific job
            else:
                job = job_mgr.get_job(job_id)
                if job:
                    elapsed_str = ""
                    if job.get("completed_at"):
                        elapsed_str = f"Completed at: {job['completed_at']}"
                    else:
                        elapsed_str = f"Started at: {job['started_at']}"
                    
                    response_text = f"Sir, background job `{job_id}` status is **{job['status']}**.\n"
                    response_text += f"- **Request**: \"{job['request']}\"\n"
                    response_text += f"- **Current Agent/Tool**: `{job['current_agent']}`\n"
                    response_text += f"- **Progress**: {job['progress']}%\n"
                    response_text += f"- **Status Info**: {elapsed_str}\n"
                    if job.get("error"):
                        response_text += f"- **Error**: `{job['error']}`\n"
                    if job.get("final_result"):
                        response_text += f"- **Final Result Summary**: {job['final_result'][:600]}\n"
                    
                    if job.get("event_log"):
                        last_events = job["event_log"][-3:]
                        response_text += "\n**Recent Events:**\n"
                        for evt in last_events:
                            response_text += f"- [{evt['timestamp']}] ({evt['agent']}) {evt['event']}\n"
                else:
                    response_text = f"Sir, I could not find a background job with ID `{job_id}`."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "chat",
                    "agent": "HackerBrain",
                    "success": job is not None,
                    "task_id": job_id
                }
        
        # General active/recent background jobs list
        if any(w in lower_msg for w in ("active jobs", "background tasks", "background jobs")) or lower_msg.strip(" .*!#?") in ("status", "progress", "jobs", "kaha tak pahucha", "mera task chal raha hai kya"):
            active_jobs = job_mgr.list_active_jobs()
            if not active_jobs:
                # Get last 3 completed/failed jobs for history
                all_jobs = job_mgr.list_all_jobs()
                recent_jobs = [j for j in all_jobs if j["status"] not in ("queued", "running", "paused")][-3:]
                
                if not recent_jobs:
                    response_text = "Sir, currently there are no background jobs."
                else:
                    response_text = "Sir, there are no active background jobs. Here are the most recent completed jobs:\n"
                    for job in recent_jobs:
                        response_text += f"- `{job['job_id']}`: **{job['status']}** - \"{job['request'][:50]}...\" (Finished at {job.get('completed_at')})\n"
            else:
                response_text = "Sir, here is the status of active background jobs:\n"
                for job in active_jobs:
                    response_text += f"- `{job['job_id']}`: **{job['status']}** - \"{job['request'][:50]}...\"\n"
                    response_text += f"  - Current Agent: `{job['current_agent']}` | Progress: {job['progress']}%\n"
            
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "HackerBrain",
                "success": True,
                "task_id": f"jobs_{int(time.time())}"
            }

        # Intercept deactivation / switch back commands
        if any(cmd in lower_msg for cmd in ["off hacker mode", "switch to productivity", "switch to productivity mode", "productivity mode", "switch back", "back to normal", "normal mode"]):
            from memory.user_profile import user_profile_store
            
            user_profile_store.update_profile(hacker_mode=False)
            return {
                "response": "Productivity Mode active ho gaya hai, Sir. Daily tasks, scheduling aur coding help ke liye system online hai.",
                "intent": "hacker_mode_deactivation",
                "agent": "HackerBrain",
                "hacker_mode_deactivated": True,
                "success": True,
                "tasks_executed": 1,
                "tasks_succeeded": 1,
                "tasks_failed": 0,
                "execution_time": 0.0,
                "task_id": f"hac_{int(time.time())}"
            }

        mem_cmd_res = parse_memory_command(message)
        if mem_cmd_res:
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", mem_cmd_res)
            return {
                "response": mem_cmd_res,
                "intent": "chat",
                "agent": "MemoryStore",
                "tasks_executed": 1,
                "tasks_succeeded": 1,
                "tasks_failed": 0,
                "execution_time": 0.0,
                "success": True,
                "task_id": f"mem_{int(time.time())}"
            }

        # Check pending approvals
        pending_file = settings.DATA_DIR / "pending_approval.json"
        if pending_file.exists():
            state = None
            try:
                with open(pending_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load pending approval state: {e}")

            if state:
                clean_msg = message.strip().lower().strip(".*!#")
                if clean_msg in ["yes", "y", "approve", "approve token", "approve <token>"]:
                    tool_name = state.get("tool_name_pending")
                    from tools.tool_permissions import get_permission_system
                    get_permission_system().approve_for_session(tool_name)

                    try:
                        pending_file.unlink()
                    except Exception:
                        pass

                    try:
                        task_id = state.get("task_id")
                        from services.job_manager import get_job_manager
                        if get_job_manager().get_job(task_id):
                            asyncio.create_task(self._run_background_job_resume(task_id, state))
                            response_text = f"Sir, I have resumed the background job `{task_id}`."
                            memory_store.add_message("assistant", response_text)
                            return {
                                "response": response_text,
                                "intent": state.get("intent", "chat"),
                                "agent": "HackerBrain",
                                "success": True,
                                "task_id": task_id,
                                "is_background": True
                            }
                        return await self.execute_agentic_loop(state.get("message", ""), pending_state=state)
                    except Exception as e:
                        logger.exception("Failed to resume agentic loop after approval in HackerBrain.")
                elif clean_msg in ["no", "n", "cancel", "stop", "abort"]:
                    try:
                        pending_file.unlink()
                    except Exception:
                        pass

                    return {
                        "response": "Sir, security command execution cancelled.",
                        "intent": "chat",
                        "agent": "HackerBrain",
                        "tasks_executed": 0,
                        "tasks_succeeded": 0,
                        "tasks_failed": 0,
                        "execution_time": 0.0,
                        "success": False,
                        "task_id": state.get("task_id", f"task_{int(time.time())}")
                    }
                else:
                    try:
                        pending_file.unlink()
                    except Exception:
                        pass

        try:
            memory_store.add_message("user", message)

            intent = await self._classify_intent(message)

            # Check if this is a background job request
            if self._is_long_running_task(message, intent):
                job = job_mgr.create_job(message)
                job_id = job["job_id"]
                asyncio.create_task(self._run_background_job(job_id, message, intent))
                
                response_text = f"Sir, I have started a background job for your request: `{job_id}`.\nYou can keep chatting with me normally. To check its status, ask 'status {job_id}' or 'progress'."
                memory_store.add_message("assistant", response_text)
                
                return {
                    "response": response_text,
                    "intent": intent,
                    "agent": "HackerBrain",
                    "success": True,
                    "task_id": job_id,
                    "is_background": True
                }
            if intent == "osint":
                logger.info("[HackerBrain] Routing OSINT intent directly to OSINTAgent")
                agent = self.agents["osint"]
                from memory.user_profile import user_profile_store
                profile = user_profile_store.get_profile()
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "hacker_mode": profile.get("hacker_mode", False),
                }
                result = await agent.run(message, base_context)

                elapsed = result.get("execution_time", 0.0)
                success = result.get("success", True)
                final_response = result.get("response", "")

                memory_store.add_message(
                    "assistant",
                    final_response,
                    {
                        "agent": "OSINTAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "osint",
                        "agent": "OSINTAgent",
                        "response": final_response,
                        "success": success,
                        "execution_time": elapsed,
                        "error": result.get("error"),
                    }],
                    "elapsed": elapsed,
                    "attempts": 1,
                })

                return {
                    "response": final_response,
                    "intent": "osint",
                    "agent": "OSINTAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed": 0 if success else 1,
                    "execution_time": elapsed,
                    "success": success,
                    "task_id": task_id,
                    "attempts": 1,
                }

            # ── Direct LeakGraph Agent routing ───────────────────────────────────
            # If intent is leakgraph, bypass the generic agentic loop and run
            # the LeakGraphAgent pipeline directly.
            if intent == "leakgraph":
                logger.info("[HackerBrain] Routing leakgraph intent directly to LeakGraphAgent")
                agent = self.agents["leakgraph"]
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                }
                result = await agent.run(message, base_context)

                elapsed = result.get("execution_time", 0.0)
                success = result.get("success", True)
                final_response = result.get("response", "")

                memory_store.add_message(
                    "assistant",
                    final_response,
                    {
                        "agent": "LeakGraphAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "leakgraph",
                        "agent": "LeakGraphAgent",
                        "response": final_response,
                        "success": success,
                        "execution_time": elapsed,
                        "error": result.get("error"),
                    }],
                    "elapsed": elapsed,
                    "attempts": 1,
                })

                return {
                    "response": final_response,
                    "intent": "leakgraph",
                    "agent": "LeakGraphAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed": 0 if success else 1,
                    "execution_time": elapsed,
                    "success": success,
                    "task_id": task_id,
                    "attempts": 1,
                }

            # ── Direct Dorking Agent routing ────────────────────────────────────
            if intent == "dorking":
                logger.info("[HackerBrain] Routing dorking intent directly to DorkingAgent")
                agent = self.agents["dorking"]
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "hacker_mode": True,
                }
                result = await agent.run(message, base_context)

                elapsed = result.get("execution_time", 0.0)
                success = result.get("success", True)
                final_response = result.get("response", "")

                memory_store.add_message(
                    "assistant",
                    final_response,
                    {
                        "agent": "DorkingAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "dorking",
                        "agent": "DorkingAgent",
                        "response": final_response,
                        "success": success,
                        "execution_time": elapsed,
                        "error": result.get("error"),
                    }],
                    "elapsed": elapsed,
                    "attempts": 1,
                })

                return {
                    "response": final_response,
                    "intent": "dorking",
                    "agent": "DorkingAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed": 0 if success else 1,
                    "execution_time": elapsed,
                    "success": success,
                    "task_id": task_id,
                    "attempts": 1,
                }

            if intent == "drana":
                logger.info("[HackerBrain] Routing Drana intent directly to DranaAgent")
                agent = self.agents["drana"]
                from memory.drana_store import drana_store
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "drana_context": drana_store.get_context_string(),
                }
                result = await agent.run(message, base_context)

                elapsed = result.get("execution_time", 0.0)
                success = result.get("success", True)
                final_response = result.get("response", "")

                memory_store.add_message(
                    "assistant",
                    final_response,
                    {
                        "agent": "DranaAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "drana",
                        "agent": "DranaAgent",
                        "response": final_response,
                        "success": success,
                        "execution_time": elapsed,
                        "error": result.get("error"),
                    }],
                    "elapsed": elapsed,
                    "attempts": 1,
                })

                return {
                    "response": final_response,
                    "intent": "drana",
                    "agent": "DranaAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed": 0 if success else 1,
                    "execution_time": elapsed,
                    "success": success,
                    "task_id": task_id,
                    "attempts": 1,
                }

            # ── Direct Pentest Agent routing ─────────────────────────────────────
            # If intent is pentest, bypass the generic agentic loop and run
            # the PentestAgent pipeline directly.
            if intent == "pentest":
                logger.info("[HackerBrain] Routing pentest intent directly to PentestAgent")
                agent = self.agents["pentest"]
                from memory.pentest_store import pentest_store
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "pentest_context": pentest_store.get_context_string(),
                }
                result = await agent.run(message, base_context)

                elapsed = result.get("execution_time", 0.0)
                success = result.get("success", True)
                final_response = result.get("response", "")

                memory_store.add_message(
                    "assistant",
                    final_response,
                    {
                        "agent": "PentestAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "pentest",
                        "agent": "PentestAgent",
                        "response": final_response,
                        "success": success,
                        "execution_time": elapsed,
                        "error": result.get("error"),
                    }],
                    "elapsed": elapsed,
                    "attempts": 1,
                })

                return {
                    "response":       final_response,
                    "intent":         "pentest",
                    "agent":          "PentestAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed":   0 if success else 1,
                    "execution_time": elapsed,
                    "success":        success,
                    "task_id":        task_id,
                    "attempts":       1,
                }

            # Try Agentic loop
            return await self.execute_agentic_loop(message)

        except Exception as err:
            logger.exception("HackerBrain loop failed. Falling back to legacy process.")
            # Remove last user message since legacy_process will add it again
            if memory_store.chat_history and memory_store.chat_history[-1]["content"] == message:
                memory_store.chat_history.pop()
            return await self.legacy_process(message)

    async def legacy_process(self, message: str) -> dict:
        """
        Legacy processing fallback pipeline for HackerBrain.
        """
        start = time.time()
        logger.info(f"[HackerBrain] Fallback Legacy Processing: {message[:120]}")

        # 1. Log user message
        memory_store.add_message("user", message)

        # 2. Build base context
        base_context = {
            "chat_history": memory_store.get_context(10),
            "recent_tasks": self._build_recent_tasks_summary(5),
        }

        max_retries = 2
        attempt = 0
        current_message = message
        task_results = []
        plan = None
        is_fast_route = False

        # Try delegator for complex queries
        if self._is_complex_query(message):
            from agents.sub_agents.delegator import get_delegator
            try:
                delegator = get_delegator()
                loop = asyncio.get_event_loop()
                delegation_result = await loop.run_in_executor(None, delegator.process, message)
                
                if delegation_result.get("route") == "complex":
                    elapsed = round(time.time() - start, 2)
                    final_response = str(delegation_result.get("result", "Swarm execution completed."))
                    agents_used = delegation_result.get("agents_used", [])
                    
                    audit_result = await self.audit_agent.think(message, {"task_results": [{"response": final_response, "intent": "swarm"}]})
                    if not audit_result.get("passed", True):
                        final_response += f"\n\n*(Note: Audit flagged potential issues: {audit_result.get('feedback')})*"
                    
                    memory_store.add_message(
                        "assistant",
                        final_response,
                        {
                            "agent": "Swarm Delegator",
                            "tasks": len(agents_used),
                            "execution_time": elapsed,
                            "attempts": 1
                        },
                    )
                    
                    return {
                        "response":       final_response,
                        "intent":         "swarm",
                        "agent":          "Swarm Delegator",
                        "tasks_executed": len(agents_used),
                        "tasks_succeeded": len(agents_used),
                        "tasks_failed":   0,
                        "execution_time": elapsed,
                        "success":        True,
                        "task_id":        delegation_result.get("swarm_id", f"swarm_{int(time.time())}"),
                        "attempts":       1
                    }
            except Exception as e:
                logger.warning(f"[HackerBrain] Swarm failed: {e}")

        while attempt < max_retries:
            attempt += 1
            logger.info(f"[HackerBrain] Execution Attempt {attempt}/{max_retries}")
            
            if self._is_complex_query(current_message):
                plan = await self._plan_multi_task(current_message)
                is_fast_route = False
            else:
                intent = await self._classify_intent(current_message)
                plan = BrainPlan(
                    tasks=[BrainTask(task_id="t1", intent=intent, description=current_message)],
                    is_parallel=False,
                )
                if intent in ["chat", "system", "codepipeline", "diagram", "image"] and attempt == 1:
                    is_fast_route = True

            task_results = await self._execute_plan(plan, base_context)

            if not is_fast_route and len(task_results) > 0 and attempt < max_retries:
                audit_result = await self.audit_agent.think(message, {"task_results": task_results})
                if not audit_result.get("passed", True):
                    feedback = audit_result.get("feedback", "Unknown error")
                    suggestion = audit_result.get("suggested_action", "")
                    current_message = f"{message}\n\n[SYSTEM]: Your previous attempt failed. Feedback: {feedback}. Suggestion: {suggestion}. Please try again and correct the mistake."
                    continue
                else:
                    break
            else:
                break

        elapsed = round(time.time() - start, 2)
        succeeded = [r for r in task_results if r.get("success")]
        failed = [r for r in task_results if not r.get("success")]

        if len(task_results) == 1:
            final_response = task_results[0]["response"]
        else:
            parts = []
            for i, r in enumerate(task_results):
                header = f"**Step {i + 1} — {r.get('intent', '').capitalize()}**\n"
                parts.append(header + r["response"])
            final_response = "\n\n---\n\n".join(parts)

            if failed:
                err_summary = f"\n\n⚠️ **{len(failed)} task(s) encountered errors:**\n"
                for f in failed:
                    err_summary += f"- {f.get('intent', 'unknown')}: {str(f.get('error', ''))[:120]}\n"
                final_response += err_summary

        if attempt > 1:
            final_response += f"\n\n*(Note: This required {attempt} attempts to self-correct and verify)*"

        primary_agent = task_results[0].get("agent", "HackerBrain") if task_results else "HackerBrain"
        memory_store.add_message(
            "assistant",
            final_response,
            {
                "agent": primary_agent,
                "tasks": len(plan.tasks) if plan else 0,
                "execution_time": elapsed,
                "attempts": attempt
            },
        )
        task_id = f"task_{len(memory_store.task_results) + 1}"
        memory_store.store_task(task_id, {"tasks": task_results, "elapsed": elapsed, "attempts": attempt})

        return {
            "response":       final_response,
            "intent":         plan.tasks[0].intent if plan and plan.tasks else "chat",
            "agent":          primary_agent,
            "tasks_executed": len(plan.tasks) if plan else 0,
            "tasks_succeeded": len(succeeded),
            "tasks_failed":   len(failed),
            "execution_time": elapsed,
            "success":        len(failed) == 0,
            "task_id":        task_id,
            "attempts":       attempt
        }

    def _is_long_running_task(self, message: str, intent: str) -> bool:
        lower_msg = message.lower()
        if any(phrase in lower_msg for phrase in [
            "background job", "background task", "run in background", 
            "background research", "background scan", "background project",
            "bg run", "in background", "background mein", "background me"
        ]):
            return True
        return intent in ("codepipeline", "research")

    async def _run_background_job(self, job_id: str, message: str, intent: str):
        current_task = asyncio.current_task()
        from services.job_manager import get_job_manager
        job_manager = get_job_manager()
        job_manager._register_task(job_id, current_task)
        
        try:
            job_manager.update_job(job_id, status="running", event="Background job execution started.")
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "running", "Background job execution started."))
            
            if intent == "osint":
                logger.info(f"[Background Job] Running OSINT pipeline for {job_id}")
                agent = self.agents["osint"]
                from memory.user_profile import user_profile_store
                profile = user_profile_store.get_profile()
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "hacker_mode": profile.get("hacker_mode", False),
                }
                result = await agent.run(message, base_context)
                response_text = result.get("response", "")
                success = result.get("success", True)
                error_msg = result.get("error")
                
                status = "completed" if success else "failed"
                job_manager.update_job(
                    job_id,
                    status=status,
                    progress=100,
                    final_result=response_text,
                    error=error_msg,
                    event=f"OSINT job finished with status: {status}."
                )
                asyncio.create_task(notify_job_status(job_id, status, f"OSINT job finished with status: {status}.", results=response_text))
                memory_store.add_message("assistant", response_text)
                memory_store.store_task(job_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "osint",
                        "agent": "OSINTAgent",
                        "response": response_text,
                        "success": success,
                        "execution_time": result.get("execution_time", 0.0),
                        "error": error_msg,
                    }],
                    "elapsed": result.get("execution_time", 0.0),
                    "attempts": 1,
                })
                
            elif intent == "leakgraph":
                logger.info(f"[Background Job] Running LeakGraph pipeline for {job_id}")
                agent = self.agents["leakgraph"]
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                }
                result = await agent.run(message, base_context)
                response_text = result.get("response", "")
                success = result.get("success", True)
                error_msg = result.get("error")
                
                status = "completed" if success else "failed"
                job_manager.update_job(
                    job_id,
                    status=status,
                    progress=100,
                    final_result=response_text,
                    error=error_msg,
                    event=f"LeakGraph job finished with status: {status}."
                )
                asyncio.create_task(notify_job_status(job_id, status, f"LeakGraph job finished with status: {status}.", results=response_text))
                memory_store.add_message("assistant", response_text)
                memory_store.store_task(job_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "leakgraph",
                        "agent": "LeakGraphAgent",
                        "response": response_text,
                        "success": success,
                        "execution_time": result.get("execution_time", 0.0),
                        "error": error_msg,
                    }],
                    "elapsed": result.get("execution_time", 0.0),
                    "attempts": 1,
                })
                
            elif intent == "dorking":
                logger.info(f"[Background Job] Running Dorking pipeline for {job_id}")
                agent = self.agents["dorking"]
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "hacker_mode": True,
                }
                result = await agent.run(message, base_context)
                response_text = result.get("response", "")
                success = result.get("success", True)
                error_msg = result.get("error")
                
                status = "completed" if success else "failed"
                job_manager.update_job(
                    job_id,
                    status=status,
                    progress=100,
                    final_result=response_text,
                    error=error_msg,
                    event=f"Dorking job finished with status: {status}."
                )
                asyncio.create_task(notify_job_status(job_id, status, f"Dorking job finished with status: {status}.", results=response_text))
                memory_store.add_message("assistant", response_text)
                memory_store.store_task(job_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "dorking",
                        "agent": "DorkingAgent",
                        "response": response_text,
                        "success": success,
                        "execution_time": result.get("execution_time", 0.0),
                        "error": error_msg,
                    }],
                    "elapsed": result.get("execution_time", 0.0),
                    "attempts": 1,
                })
                
            elif intent == "drana":
                logger.info(f"[Background Job] Running Drana pipeline for {job_id}")
                agent = self.agents["drana"]
                from memory.drana_store import drana_store
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "drana_context": drana_store.get_context_string(),
                }
                result = await agent.run(message, base_context)
                response_text = result.get("response", "")
                success = result.get("success", True)
                error_msg = result.get("error")
                
                status = "completed" if success else "failed"
                job_manager.update_job(
                    job_id,
                    status=status,
                    progress=100,
                    final_result=response_text,
                    error=error_msg,
                    event=f"Drana job finished with status: {status}."
                )
                asyncio.create_task(notify_job_status(job_id, status, f"Drana job finished with status: {status}.", results=response_text))
                memory_store.add_message("assistant", response_text)
                memory_store.store_task(job_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "drana",
                        "agent": "DranaAgent",
                        "response": response_text,
                        "success": success,
                        "execution_time": result.get("execution_time", 0.0),
                        "error": error_msg,
                    }],
                    "elapsed": result.get("execution_time", 0.0),
                    "attempts": 1,
                })
                
            elif intent == "pentest":
                logger.info(f"[Background Job] Running Pentest pipeline for {job_id}")
                agent = self.agents["pentest"]
                from memory.pentest_store import pentest_store
                base_context = {
                    "chat_history": memory_store.get_context(10),
                    "recent_tasks": self._build_recent_tasks_summary(5),
                    "pentest_context": pentest_store.get_context_string(),
                }
                result = await agent.run(message, base_context)
                response_text = result.get("response", "")
                success = result.get("success", True)
                error_msg = result.get("error")
                
                status = "completed" if success else "failed"
                job_manager.update_job(
                    job_id,
                    status=status,
                    progress=100,
                    final_result=response_text,
                    error=error_msg,
                    event=f"Pentest job finished with status: {status}."
                )
                asyncio.create_task(notify_job_status(job_id, status, f"Pentest job finished with status: {status}.", results=response_text))
                memory_store.add_message("assistant", response_text)
                memory_store.store_task(job_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "pentest",
                        "agent": "PentestAgent",
                        "response": response_text,
                        "success": success,
                        "execution_time": result.get("execution_time", 0.0),
                        "error": error_msg,
                    }],
                    "elapsed": result.get("execution_time", 0.0),
                    "attempts": 1,
                })
                
            else:
                logger.info(f"[Background Job] Running Agentic Loop for {job_id}")
                await self.execute_agentic_loop(message, task_id=job_id)
                
        except asyncio.CancelledError:
            job_manager.update_job(job_id, status="cancelled", event="Job was cancelled by the user.")
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "cancelled", "Job was cancelled by the user."))
            logger.info(f"[Background Job] Job {job_id} cancelled.")
        except Exception as e:
            logger.exception(f"[Background Job] Error executing job {job_id}: {e}")
            job_manager.update_job(
                job_id,
                status="failed",
                error=str(e),
                event=f"Job failed with exception: {e}"
            )
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "failed", f"Job failed with exception: {e}"))
        finally:
            job_manager._deregister_task(job_id)

    async def _run_background_job_resume(self, job_id: str, state: dict):
        current_task = asyncio.current_task()
        from services.job_manager import get_job_manager
        job_manager = get_job_manager()
        job_manager._register_task(job_id, current_task)
        
        try:
            job_manager.update_job(job_id, status="running", event="Background job resumed.")
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "running", "Background job resumed."))
            await self.execute_agentic_loop(state.get("message", ""), pending_state=state)
        except asyncio.CancelledError:
            job_manager.update_job(job_id, status="cancelled", event="Job was cancelled by the user.")
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "cancelled", "Job was cancelled by the user."))
        except Exception as e:
            logger.exception(f"[Background Job] Error resuming job {job_id}: {e}")
            job_manager.update_job(job_id, status="failed", error=str(e), event=f"Job failed with exception: {e}")
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "failed", f"Job failed with exception: {e}"))
        finally:
            job_manager._deregister_task(job_id)

hacker_brain = HackerBrain()
