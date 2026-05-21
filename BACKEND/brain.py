"""
AERIS Brain — Hybrid Multi-Task Orchestrator.

Routing pipeline (fastest to slowest):
  1. Neural ML fast-route  → local PyTorch (zero latency, <1ms)
  2. Keyword rules         → hard-coded patterns (fallback for edge-cases)
  3. LLM Multi-Task Plan   → Groq / Gemini generates a full task execution plan

Execution:
  - Each task in the plan is routed to the correct sub-agent (chat, security,
    system, research, code).
  - Sequential execution injects context from previous steps into the next.
  - Parallel execution runs independent tasks concurrently.
  - Memory is saved after every run for conversational context.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ValidationError

from ai_engine import ai_engine
from agents import ChatAgent, SecurityAgent, SystemAgent, ResearchAgent, CodeAgent, AuditAgent, ImageAgent, ObserverAgent, SearchAgent, AnalyzerAgent, OSINTAgent
from agents.agent_registry import agent_registry, AgentStatus
from memory.store import memory_store
from neural.core import neural_core
from config import settings

logger = logging.getLogger("aeris.brain")

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas for multi-task plan & Agentic Loop
# ──────────────────────────────────────────────────────────────────────────────

class BrainTask(BaseModel):
    task_id: str
    intent: str       # chat | security | system | research | code
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
# LLM Multi-Task Planning & Agentic Prompts
# ──────────────────────────────────────────────────────────────────────────────

PLANNER_PROMPT = """You are the AI Planner for AERIS.
Decompose the user's request into a sequential plan of tool calls to achieve the goal.
For each step, specify the tool to call, the arguments (as a JSON object), and a short description.

AVAILABLE TOOLS:
{tools_summary}

CRITICAL RULES:
- When the user asks about "agents" (e.g. "kitne agent hai", "list agents", "how many agents"), use the `list_agents` tool, NOT `list_tools`.
- `list_tools` is ONLY for listing executable tool functions. `list_agents` is for listing AI agents.
- For ANY security-related request (SSL check, port scan, DNS lookup, recon, VAPT, vulnerability scan, WHOIS, subdomain enumeration), use the `security_scan` tool. NEVER use `smart_shell_generate` or `run_bash` for security scanning tasks.
- Read each tool's description carefully and pick the BEST match for the user's intent.

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
    # Match "remember that", "remember", "forget that", "forget", "update memory"
    # optionally followed by a colon and spaces
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

MULTI_TASK_PROMPT = """You are the routing brain of AERIS (Autonomous Enhanced Reasoning Intelligence System).
Your ONLY job: decompose the user's message into an ordered execution plan.

AVAILABLE INTENTS:
- "chat"     : Casual conversation, greetings, general knowledge, jokes, math, definitions
- "security" : Port scanning, recon, vulnerability testing, VAPT, DNS lookup, SSL checks, zero-day analysis
- "system"   : Open/close apps, run shell commands, file operations, OS info, system control
- "research" : Deep academic research, synthesis of complex technical topics, multi-source information gathering
- "search"   : Realtime internet search, current events, news, live prices, trending topics, quick web lookups, weather, user location (where am i), scraping
- "code"     : Write code, debug, explain code, refactor, generate scripts
- "image"    : Generate, create, or draw images/pictures/photos from a text description
- "diagram"  : Create flowcharts, system diagrams, architecture charts, mind maps, flow charts, graphs, charts, widgets
- "codepipeline" : Build an entire project/app autonomously, scaffold a workspace, create a full codebase
- "analyze"  : Analyze files, logs, data, code outputs, system state — find patterns, errors, insights, or summarize contents
- "osint"   : Public source investigations, profile gathering, social footprint mappings, email/username lookups, dynamic pivot investigations, target intel compilation

=== CONVERSATION HISTORY (last 3 messages) ===
{history}
=== END HISTORY ===

=== RECENT AGENT TASK EXECUTIONS ===
{recent_tasks}
=== END RECENT TASKS ===

CURRENT USER MESSAGE: "{message}"

IMPORTANT: Use the conversation history to resolve pronouns ("it", "that", "iska", "uska") and understand follow-up queries.
If the current message is a follow-up to a previous security/osint task (e.g., "investigate it", "stalk that user", "check its social profile"), resolve the target from history.

Respond with ONLY valid JSON, no markdown, no extra text:
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

RULES:
- If the message has only ONE request, output exactly ONE task.
- If the message has MULTIPLE requests, split into multiple tasks with correct dependencies.
- Set is_parallel=true ONLY if tasks are completely independent.
- "description" MUST be self-contained — replace pronouns with the actual resolved target/subject from history.
- When unsure between "chat" and "research", prefer "research".
- For investigations, profile traces, social mapping, footprint checks, or email/username lookups, choose "osint".
"""

# ──────────────────────────────────────────────────────────────────────────────
# Keyword hard-coded fast routes (bypass LLM even if neural is not confident)
# ──────────────────────────────────────────────────────────────────────────────

_KEYWORD_MAP: List[Tuple[List[str], str]] = [
    (["scan", "port", "recon", "vulnerability", "nmap", "ssl", "hack",
      "header", "fuzz", "vapt", "whois", "dns", "subdomain"], "security"),
    # ── System / OS automation ─────────────────────────────────────────────
    ([
      # App control
      "open ", "close ", "run ", "execute ", "shutdown", "restart",
      "screenshot", "kill process", "list files", "list directory",
      "system info", "disk space", "os info", "volume",
      # Browser search — must open a real browser window
      "search on browser", "search the browser", "search on google",
      "google search", "search google", "open browser", "open chrome",
      "open edge", "browse to", "go to website",
      "on google", "in google", "google pe", "google par", "open google", "google open",
      "google par search", "google pe search", "google par dhoondo", "google pe dhoondo",
      # YouTube / music playback — open YouTube visibly
      "play ", "play a song", "play music", "play video",
      "youtube search", "search on youtube", "search youtube",
      "open youtube", "youtube pe", "youtube par",
     ], "system"),
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
      # Hindi / Hinglish code keywords — must come before image block
      "game banao", "code banao", "program banao", "script banao",
      "function banao", "api banao", "app banao", "website banao",
      "code likho", "program likho", "algorithm banao",
      "python mein", "javascript mein", "java mein",
      "mein banao", "mein bana do", "mein bana de",
    ], "code"),
    # ── Image generation ──────────────────────────────────────────────────────
    ([
      "generate image", "create image", "make image", "draw ",
      "generate a picture", "create a picture", "make a picture",
      "generate photo", "create photo", "make photo",
      "image of ", "picture of ", "photo of ",
      # Hindi / Hinglish — image-specific only (no generic "banao")
      "photo de", "photo bana", "image bana", "tasveer",
      "phot de", "phot bana",
    ], "image"),
    # ── Autonomous code pipeline ──────────────────────────────────────────────
    ([
      "build a project", "build me a project", "build me an app",
      "create a project", "scaffold a project", "autonomous code",
      "create a workspace", "create workspace", "build an entire",
      "generate a full project", "full project", "code pipeline",
      "project bana", "project banao", "app bana do",
    ], "codepipeline"),
    # ── Diagram / flowchart / widget ─────────────────────────────────────────
    ([
      "flowchart", "flow chart", "diagram", "chart", "mind map", "mindmap",
      "architecture diagram", "system diagram", "sequence diagram",
      "er diagram", "class diagram", "network diagram",
      "widget", "visualize", "visualise", "flow banao", "chart banao",
      "diagram banao", "diagram bana", "chart bana",
    ], "diagram"),
    # ── Analyze / inspect / diagnose ──────────────────────────────────────────
    ([
      "analyze ", "analyse ", "inspect ", "diagnose", "summarize file",
      "analyze file", "analyse file", "check this file", "check this data",
      "parse this", "read and explain", "find issues in",
      "analyze karo", "analyse karo", "check karo", "dekhke batao",
      "file analyze", "log analyze", "data analyze",
    ], "analyze"),
    # ── OSINT investigations ──────────────────────────────────────────────────
    ([
      "osint", "investigate", "target intel", "email search", "username lookup",
      "social footprint", "trace target", "footprint check", "profile check",
      "target search", "profile trace", "stalk target", "stalk user", "recon target"
    ], "osint"),
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
                    logger.debug(f"[Brain] Keyword route → {intent} (kw='{kw}')")
                    return intent
            elif " " in kw or "-" in kw:
                if kw in lower:
                    logger.debug(f"[Brain] Keyword route → {intent} (kw='{kw}')")
                    return intent
            else:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, lower):
                    logger.debug(f"[Brain] Keyword route → {intent} (kw='{kw}')")
                    return intent
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Brain
# ──────────────────────────────────────────────────────────────────────────────

class Brain:
    """
    Hybrid multi-task orchestrator for AERIS.

    Routing order (fastest → most powerful):
      1. Neural ML (local PyTorch, <1ms, if confidence > 80%)
      2. Keyword rules (instant string matching, edge-case safety net)
      3. LLM multi-task planner (Groq primary, Gemini fallback)
    """

    NEURAL_CONFIDENCE_THRESHOLD = 0.80
    VALID_INTENTS = {"chat", "security", "system", "research", "search", "code", "image", "codepipeline", "diagram", "analyze", "osint"}

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

            logger.info(f"[Brain] Registered {len(agent_registry)} agents in AgentRegistry (Core + Sub-Agents).")
        except Exception as e:
            logger.warning(f"[Brain] Sub-agent registration partial: {e}")

        # ── Run initial health check ──
        agent_registry.run_health_checks()
        logger.info(f"[Brain] Initialized with {len(self.agents)} core agents, 1 Auditor, 1 Observer.")

    # ─────────────────────────── System Health ────────────────────────────────

    def get_system_health(self) -> dict:
        """
        Return the full health status of all agents (core + sub-agents).
        Used by the ChatAgent to answer "what can you do?" and health queries.
        """
        agent_registry.run_health_checks()
        return {
            "total_agents": len(agent_registry),
            "statuses": agent_registry.get_all_statuses(),
            "summary": agent_registry.get_capabilities_summary(),
        }

    def get_capabilities_for_prompt(self) -> str:
        """Return a capabilities summary string for injection into LLM prompts."""
        return agent_registry.get_capabilities_summary()

    # ─────────────────────────── Intent Routing ───────────────────────────────

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
            logger.warning(f"Failed to build task summary: {e}")
            return "No recent tasks executed."

    async def _classify_intent(self, message: str) -> str:
        """
        Single-intent classification with conversation context.

        Priority:
          1. Neural ML — only at high confidence (85%+) for instant routing
          2. LLM classification — primary classifier, understands any language + history
          3. Keyword fallback — only if LLM fails entirely
        """
        # 1. Neural ML fast-route (high confidence only)
        if neural_core.is_intent_ready:
            try:
                label, confidence = neural_core.predict_intent_from_text(message)
                if label in self.VALID_INTENTS and confidence >= 0.85:
                    logger.info(f"[Brain] Neural fast-route -> '{label}' (conf={confidence:.2f})")
                    return label
                else:
                    logger.debug(f"[Brain] Neural not confident enough ({confidence:.2f}) for '{label}', using LLM.")
            except Exception as e:
                logger.warning(f"[Brain] Neural routing failed: {e}")

        # 2. LLM classification — primary, understands any language + conversation context
        history_summary = self._build_history_summary(3)
        recent_tasks_summary = self._build_recent_tasks_summary(3)
        try:
            raw = await ai_engine.classify(
                f"You are an intent classifier. Classify the following user message into EXACTLY ONE intent.\n\n"
                f"INTENTS:\n"
                f"- chat     : Casual conversation, greetings, general knowledge, jokes, math, definitions\n"
                f"- security : Port scanning, recon, vulnerability testing, VAPT, DNS lookup, SSL checks, zero-day analysis\n"
                f"- system   : Open/close apps, run shell commands, file operations, OS info, system control, browser navigation (opening browser to search Google/YouTube), playing music/videos\n"
                f"- research : Deep academic/technical research, multi-source synthesis of complex topics, research papers\n"
                f"- search   : Realtime background web search (not opening a browser window), current events, breaking news, live prices, trending topics, quick internet lookups, weather, user location/where am i, web scraping\n"
                f"- code     : Write code, debug, explain code, refactor, generate scripts\n"
                f"- image    : Generate, create, draw, or produce images/pictures/photos/art from a text description\n"
                f"- diagram  : Create flowcharts, system diagrams, architecture charts, mind maps, charts, graphs, widgets — ANY visual data structure or flow diagram\n"
                f"- codepipeline : Build an entire project/app autonomously, scaffold a workspace, generate a full codebase\n"
                f"- analyze  : Analyze files, logs, data, code outputs, system state — find patterns, errors, insights, or summarize contents of files\n"
                f"- osint    : Public source investigations, profile gathering, social footprint mappings, email/username lookups, dynamic pivot investigations, target intel compilation\n\n"
                f"FEW-SHOT EXAMPLES:\n"
                f"- \"search sambhav mehra on google\" -> system (reason: requests browser search visually)\n"
                f"- \"google pe python dhoondo\" -> system (reason: requests opening browser to search Google)\n"
                f"- \"search what is the weather today\" -> search (reason: requests quick realtime news/weather check in background)\n"
                f"- \"check ssl certificate for google.com\" -> security (reason: technical SSL scan)\n"
                f"- \"what is gravity?\" -> chat (reason: general knowledge definition)\n"
                f"- \"analyze log.txt and find errors\" -> analyze (reason: inspects file contents)\n"
                f"- \"write a node.js web server\" -> code (reason: requests code snippet implementation)\n\n"
                f"The message may be in ANY language (English, Hindi, Hinglish, etc). Understand the MEANING, not just keywords.\n"
                f"Use the conversation history to resolve follow-up queries and pronouns (e.g., 'it', 'that', 'iska').\n\n"
                f"=== CONVERSATION HISTORY (last 3 messages) ===\n{history_summary}\n=== END HISTORY ===\n\n"
                f"=== RECENT AGENT TASK EXECUTIONS ===\n{recent_tasks_summary}\n=== END RECENT TASKS ===\n\n"
                f'Current user message: "{message}"\n\n'
                f'Respond with ONLY valid JSON: {{"intent": "<one of: chat, security, system, research, search, code, image, diagram, codepipeline, analyze, osint>", "reason": "<brief explanation>"}}'
            )
            raw = raw.strip().strip("```json").strip("```").strip()
            data = json.loads(raw)
            intent = data.get("intent", "chat")
            if intent in self.VALID_INTENTS:
                logger.info(f"[Brain] LLM classify -> '{intent}' (reason: {data.get('reason', 'n/a')[:60]})")
                return intent
        except Exception as e:
            logger.warning(f"[Brain] LLM classify failed: {e}")

        # 3. Keyword fallback — only if LLM failed
        keyword_intent = _keyword_route(message)
        if keyword_intent:
            logger.info(f"[Brain] Keyword fallback -> '{keyword_intent}'")
            return keyword_intent

        logger.warning("[Brain] All classifiers failed. Defaulting to 'chat'.")
        return "chat"

    async def _plan_multi_task(self, message: str) -> BrainPlan:
        """
        Use LLM to parse complex, multi-step queries into a BrainPlan.
        Injects conversation history to resolve follow-up queries and pronouns.
        Falls back to a single-task plan on any error.
        """
        history_summary = self._build_history_summary(3)
        recent_tasks_summary = self._build_recent_tasks_summary(3)
        try:
            raw = await ai_engine.classify(
                MULTI_TASK_PROMPT.format(message=message, history=history_summary, recent_tasks=recent_tasks_summary)
            )
            raw = raw.strip().strip("```json").strip("```").strip()
            plan = BrainPlan(**json.loads(raw))
            # Validate all intents
            for t in plan.tasks:
                if t.intent not in self.VALID_INTENTS:
                    t.intent = "chat"
            logger.info(f"[Brain] Multi-task plan: {len(plan.tasks)} task(s), parallel={plan.is_parallel}")
            return plan
        except Exception as e:
            logger.warning(f"[Brain] Multi-task plan failed ({e}), building single-task fallback.")
            intent = await self._classify_intent(message)
            return BrainPlan(
                tasks=[BrainTask(task_id="t1", intent=intent, description=message)],
                is_parallel=False,
            )

    def _is_complex_query(self, message: str) -> bool:
        """
        Heuristic: is this a multi-step query?
        Long messages or messages with conjunctions are treated as complex.
        """
        lower = message.lower()
        multi_step_signals = [" and then ", " after that ", " also ", " additionally ",
                              " furthermore ", " then ", " next ", " followed by ",
                              # Hindi / Hinglish conjunctions for multi-step requests
                              " or ", " aur ", " phir ", " uske baad ", " krke ", " karke ",
                              " kar ke ", " karne ke baad ", " fir ", " bhi ",
                              " convert ", " convert kr", " convert kar",]
        if any(sig in lower for sig in multi_step_signals):
            return True
        if len(message) > 150:
            return True
        return False

    # ─────────────────────────── Task Execution ───────────────────────────────

    async def _run_task(
        self,
        task: BrainTask,
        context: dict,
        step_idx: int,
        total: int,
    ) -> dict:
        """Execute a single BrainTask through the appropriate agent."""
        logger.info(f"[Brain] Task {step_idx + 1}/{total}: intent='{task.intent}' — {task.description[:80]}")

        # Handle diagram intent — generate an interactive React Flow widget
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
                logger.error(f"[Brain] DiagramAgent failed: {e}")
                return {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "DiagramAgent",
                    "response": f"Could not generate diagram: {e}",
                    "success": False, "execution_time": 0.0, "error": str(e),
                }

        # Handle codepipeline intent — run the autonomous pipeline
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
                        logger.warning(f"[Brain] Pipeline: failed {fs.path}: {e}")

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
                logger.error(f"[Brain] CodePipeline failed: {e}")
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
            logger.error(f"[Brain] Task '{task.task_id}' raised exception: {e}")
            return {
                "task_id": task.task_id,
                "intent": task.intent,
                "agent": agent.name,
                "response": f"I encountered an error while processing this task: {str(e)}",
                "success": False,
                "execution_time": 0.0,
                "error": str(e),
            }

    # ─────────────────────────── Plan Execution ───────────────────────────────

    async def _execute_plan(self, plan: BrainPlan, base_context: dict) -> List[dict]:
        """Execute all tasks in a BrainPlan — sequentially or in parallel."""
        results: List[dict] = []
        total = len(plan.tasks)

        if plan.is_parallel and total > 1:
            logger.info("[Brain] Running tasks in PARALLEL.")
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
            logger.info("[Brain] Running tasks SEQUENTIALLY.")
            accumulated_context = ""
            for i, task in enumerate(plan.tasks):
                # Inject context from previous successful steps
                ctx = dict(base_context)
                if accumulated_context:
                    ctx["prior_step_context"] = accumulated_context

                result = await self._run_task(task, ctx, i, total)
                results.append(result)

                if result["success"]:
                    snippet = result["response"][:600]
                    accumulated_context += f"\n--- [{task.intent.upper()}] ---\n{snippet}\n"

                    # Extract file paths from results so downstream tasks can use them directly
                    import re
                    paths_found = re.findall(r'[A-Za-z]:\\[^\s\n\r\'"<>|]+\.\w+', snippet)
                    if paths_found:
                        accumulated_context += f"\n[FILE_PATHS_FOUND]: {'; '.join(paths_found)}\n"
                        logger.info(f"[Brain] Extracted file paths for downstream tasks: {paths_found}")

        return results

    # ─────────────────────────── Public API ───────────────────────────────────

    async def execute_agentic_loop(self, message: str, pending_state: Optional[dict] = None) -> dict:
        """
        Execute the agentic loop: plan -> tool call -> observe -> reflect -> final response.
        Supports resuming from pending_state if user approved a tool call.
        """
        start = time.time()
        task_id = pending_state.get("task_id") if pending_state else f"task_{int(time.time())}"
        
        # 1. Plan / Resume Plan
        if pending_state:
            # Resume from saved state
            plan_dict = pending_state.get("plan")
            plan = AgenticPlan(**plan_dict)
            current_step_index = pending_state.get("current_step_index", 0)
            observations = [Observation(**obs) for obs in pending_state.get("observations", [])]
            logger.info(f"[Brain] Resuming agentic plan execution from step {current_step_index}")
        else:
            # Generate new plan
            from tools.universal_registry import get_universal_registry
            tools_summary = get_universal_registry().format_for_llm()
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
            
            prompt = PLANNER_PROMPT.format(
                tools_summary=tools_summary,
                history=history,
                memory_context=memory_context,
                profile_context=profile_context,
                message=message
            )
            
            plan_data = await query_llm_json(prompt)
            if not plan_data or "steps" not in plan_data:
                raise ValueError("LLM failed to generate a valid plan structure.")
            
            plan = AgenticPlan(**plan_data)
            current_step_index = 0
            observations = []
            logger.info(f"[Brain] Generated new agentic plan with {len(plan.steps)} step(s)")

        # 2. Loop Execution
        while current_step_index < len(plan.steps):
            step = plan.steps[current_step_index]
            
            # Check permissions first (Task 3: explicit approval check)
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
                    # PAUSE execution and wait for user approval
                    pending_file = settings.DATA_DIR / "pending_approval.json"
                    state_to_save = {
                        "plan": plan.dict(),
                        "message": message,
                        "current_step_index": current_step_index,
                        "observations": [obs.dict() for obs in observations],
                        "tool_name_pending": step.tool_name,
                        "args_pending": step.args,
                        "task_id": task_id
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
                        "agent": "Brain",
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
                    # Hard block: record as failure immediately
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
                
            # Execute tool call
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
            
            # Reflection step
            if current_step_index < len(plan.steps) or not obs.success:
                reflection_prompt = f"""You are the AI Reflector for AERIS.
Analyze the results of the plan execution so far.

ORIGINAL PLAN:
{json.dumps(plan.dict(), indent=2)}

OBSERVATIONS SO FAR:
{json.dumps([o.dict() for o in observations], indent=2)}

CURRENT STEP ID: {step.step_id}

Evaluate the last tool call: did it succeed? Did it yield the required info?
Determine whether to continue with the original plan, stop, or suggest modifications.

Respond with ONLY valid JSON matching this schema:
{{
  "step_id": "{step.step_id}",
  "thought": "<your reasoning about the results and next step>",
  "should_continue": true,
  "suggested_changes": null
}}
"""
                ref_data = await query_llm_json(reflection_prompt)
                if ref_data:
                    try:
                        reflection = Reflection(**ref_data)
                        logger.info(f"[Brain] Reflection step {step.step_id}: {reflection.thought}")
                        if not reflection.should_continue:
                            logger.info(f"[Brain] Reflection decided to abort further steps.")
                            break
                        if reflection.suggested_changes:
                            plan.steps = plan.steps[:current_step_index] + reflection.suggested_changes
                            logger.info(f"[Brain] Reflection updated plan steps. New plan length: {len(plan.steps)}")
                    except Exception as re_err:
                        logger.warning(f"Failed to parse reflection JSON: {re_err}")
                        
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
        
        final_prompt = f"""You are AERIS, a real agentic assistant.
Provide the final response to the user's request based on the plan execution results.

USER MESSAGE: "{message}"

CONVERSATION HISTORY:
{history}

USER PROFILE:
{profile_context}

MEMORY CONTEXT:
{memory_context}

EXECUTED PLAN:
{json.dumps(plan.dict(), indent=2)}

OBSERVATIONS & TOOL OUTPUTS:
{json.dumps([o.dict() for o in observations], indent=2)}

HINGLISH PERSONALIZATION RULES:
- If the user writes in Hinglish (Hindi written in Latin/Roman script, e.g., "kaise ho", "kya chal raha hai") or Hindi, you MUST naturally respond in modern, conversational Hinglish.
- Keep the language flow smooth, colloquial, and friendly (e.g., "Haan, bilkul!", "Main isko check karta hoon").
- Do not use overly formal/robotic Google-translated Hindi. Match the user's Roman-script Hindi style.

Respond with ONLY valid JSON matching this schema:
{{
  "text": "<your conversational answer to the user>",
  "summary_of_actions": "<brief summary of tools called and what was accomplished>"
}}
"""
        # Check if any step was blocked by security
        is_blocked = False
        blocked_reason = ""
        for obs in observations:
            if obs.error and "SECURITY_BLOCKED" in obs.error:
                is_blocked = True
                blocked_reason = obs.error
                break

        if is_blocked:
            text_resp = f"🛡️ SECURITY_BLOCKED: The request was blocked because it contains dangerous or destructive commands: {blocked_reason}"
            summary_actions = f"Blocked execution of tool due to security policy."
        else:
            final_data = await query_llm_json(final_prompt)
            if not final_data or "text" not in final_data:
                text_resp = "I have completed the requested actions."
                summary_actions = "Execution complete."
            else:
                final_response = FinalResponse(**final_data)
                text_resp = final_response.text
                summary_actions = final_response.summary_of_actions

            
        elapsed = round(time.time() - start, 2)
        succeeded = [o for o in observations if o.success]
        failed = [o for o in observations if not o.success]
        
        primary_tool = observations[0].tool_name if observations else "none"
        
        # Save message to memory store
        memory_store.add_message("assistant", text_resp)
        
        return {
            "response": text_resp,
            "intent": primary_tool,
            "agent": "AgenticLoop",
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
        Main entry point: receive user message, check memory commands,
        check pending approvals, execute agentic loop, or run legacy flow.
        """
        # 1. Intercept memory commands
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

        # 2. Check pending approvals
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
                        return await self.execute_agentic_loop(state.get("message", ""), pending_state=state)
                    except Exception as e:
                        logger.exception("Failed to resume agentic loop after approval. Falling back to legacy process.")
                        return await self.legacy_process(message)
                elif clean_msg in ["no", "n", "cancel", "stop", "abort"]:
                    try:
                        pending_file.unlink()
                    except Exception:
                        pass
                    
                    return {
                        "response": "Execution cancelled. The tool execution request was rejected.",
                        "intent": "chat",
                        "agent": "Brain",
                        "tasks_executed": 0,
                        "tasks_succeeded": 0,
                        "tasks_failed": 0,
                        "execution_time": 0.0,
                        "success": False,
                        "task_id": state.get("task_id", f"task_{int(time.time())}")
                    }
                else:
                    # Cancel approval on any other input and execute new command
                    try:
                        pending_file.unlink()
                    except Exception:
                        pass

        # 3. Normal execution: try agentic loop
        try:
            memory_store.add_message("user", message)
            return await self.execute_agentic_loop(message)
        except Exception as e:
            logger.exception(f"Agentic loop failed: {e}. Falling back to legacy process.")
            # Remove last user message since legacy_process will add it again
            if memory_store.chat_history and memory_store.chat_history[-1]["content"] == message:
                memory_store.chat_history.pop()
            return await self.legacy_process(message)

    async def legacy_process(self, message: str) -> dict:
        """
        Legacy processing fallback pipeline (classify -> route -> agent -> audit).
        """
        start = time.time()
        logger.info(f"[Brain] Fallback Legacy Processing: {message[:120]}")

        # 1. Log user message
        memory_store.add_message("user", message)

        # 2. Build base context (last 10 messages)
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

        # Try delegator for complex queries first
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
                    
                    # Audit the swarm response
                    audit_result = await self.audit_agent.think(message, {"task_results": [{"response": final_response, "intent": "swarm"}]})
                    if not audit_result.get("passed", True):
                        logger.warning(f"[Brain] Swarm Audit FAILED: {audit_result.get('feedback')}")
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
                logger.warning(f"[Brain] Delegator swarm failed, falling back to multi-task plan: {e}")

        while attempt < max_retries:
            attempt += 1
            logger.info(f"[Brain] Execution Attempt {attempt}/{max_retries}")
            
            # 3. Plan
            if self._is_complex_query(current_message):
                plan = await self._plan_multi_task(current_message)
                is_fast_route = False
            else:
                intent = await self._classify_intent(current_message)
                plan = BrainPlan(
                    tasks=[BrainTask(task_id="t1", intent=intent, description=current_message)],
                    is_parallel=False,
                )
                # If it's a simple command or a specialized pipeline, skip the audit
                if intent in ["chat", "system", "codepipeline", "diagram", "image"] and attempt == 1:
                    is_fast_route = True

            # 4. Execute
            task_results = await self._execute_plan(plan, base_context)

            # 5. Audit (only if not fast-routed)
            if not is_fast_route and len(task_results) > 0 and attempt < max_retries:
                audit_result = await self.audit_agent.think(message, {"task_results": task_results})
                if not audit_result.get("passed", True):
                    feedback = audit_result.get("feedback", "Unknown error")
                    suggestion = audit_result.get("suggested_action", "")
                    logger.warning(f"[Brain] Audit FAILED: {feedback} | Suggestion: {suggestion}")
                    
                    # Update message for next attempt
                    current_message = f"{message}\n\n[SYSTEM]: Your previous attempt failed. Feedback: {feedback}. Suggestion: {suggestion}. Please try again and correct the mistake."
                    continue # Retry loop
                else:
                    logger.info("[Brain] Audit PASSED.")
                    break # Success, exit loop
            else:
                break # Fast route or max retries reached, exit loop

        # 6. Aggregate response
        elapsed = round(time.time() - start, 2)
        succeeded = [r for r in task_results if r.get("success")]
        failed = [r for r in task_results if not r.get("success")]

        # Combine all task responses into a single reply
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

        # Add note if it took multiple attempts
        if attempt > 1:
            final_response += f"\n\n*(Note: This required {attempt} attempts to self-correct and verify)*"

        # 7. Store in memory
        primary_agent = task_results[0].get("agent", "Brain") if task_results else "Brain"
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

        # 8. Return enriched response
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


# ── Global singleton ──────────────────────────────────────────────────────────
brain = Brain()
