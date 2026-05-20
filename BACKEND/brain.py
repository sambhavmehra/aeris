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
from agents import ChatAgent, SecurityAgent, SystemAgent, ResearchAgent, CodeAgent, AuditAgent, ImageAgent, ObserverAgent, SearchAgent, AnalyzerAgent
from agents.agent_registry import agent_registry, AgentStatus
from memory.store import memory_store
from neural.core import neural_core
from config import settings

logger = logging.getLogger("aeris.brain")

# ──────────────────────────────────────────────────────────────────────────────
# Pydantic schemas for multi-task plan
# ──────────────────────────────────────────────────────────────────────────────

class BrainTask(BaseModel):
    task_id: str
    intent: str       # chat | security | system | research | code
    description: str  # Refined instruction for the agent
    dependencies: List[str] = []  # task_ids this task depends on


class BrainPlan(BaseModel):
    tasks: List[BrainTask]
    is_parallel: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# LLM Multi-Task Planning Prompt
# ──────────────────────────────────────────────────────────────────────────────

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

=== CONVERSATION HISTORY (last 3 messages) ===
{history}
=== END HISTORY ===

=== RECENT AGENT TASK EXECUTIONS ===
{recent_tasks}
=== END RECENT TASKS ===

CURRENT USER MESSAGE: "{message}"

IMPORTANT: Use the conversation history to resolve pronouns ("it", "that", "iska", "uska") and understand follow-up queries.
If the current message is a follow-up to a previous security task (e.g., "scan it", "check its SSL"), classify it as "security" and resolve the target from history.

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
]


def _keyword_route(text: str) -> Optional[str]:
    """Return an intent from keyword rules, or None if no match."""
    lower = text.lower()
    for keywords, intent in _KEYWORD_MAP:
        for kw in keywords:
            if kw in lower:
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
    VALID_INTENTS = {"chat", "security", "system", "research", "search", "code", "image", "codepipeline", "diagram", "analyze"}

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
          1. Neural ML — only at very high confidence (95%+) for instant routing
          2. LLM classification — primary classifier, understands any language + history
          3. Keyword fallback — only if LLM fails entirely
        """
        # 1. Neural ML fast-route (very high confidence only)
        if neural_core.is_intent_ready:
            try:
                label, confidence = neural_core.predict_intent_from_text(message)
                if label in self.VALID_INTENTS and confidence >= 0.95:
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
                f"- system   : Open/close apps, run shell commands, file operations, OS info, system control, browser navigation, playing music/videos\n"
                f"- research : Deep academic/technical research, multi-source synthesis of complex topics, research papers\n"
                f"- search   : Realtime web search, current events, breaking news, live prices, trending topics, quick internet lookups, weather, user location/where am i, web scraping\n"
                f"- code     : Write code, debug, explain code, refactor, generate scripts\n"
                f"- image    : Generate, create, draw, or produce images/pictures/photos/art from a text description\n"
                f"- diagram  : Create flowcharts, system diagrams, architecture charts, mind maps, charts, graphs, widgets — ANY visual data structure or flow diagram\n"
                f"- codepipeline : Build an entire project/app autonomously, scaffold a workspace, generate a full codebase\n"
                f"- analyze  : Analyze files, logs, data, code outputs, system state — find patterns, errors, insights, or summarize contents of files\n\n"
                f"The message may be in ANY language (English, Hindi, Hinglish, etc). Understand the MEANING, not just keywords.\n"
                f"Use the conversation history to resolve follow-up queries and pronouns (e.g., 'it', 'that', 'iska').\n\n"
                f"=== CONVERSATION HISTORY (last 3 messages) ===\n{history_summary}\n=== END HISTORY ===\n\n"
                f"=== RECENT AGENT TASK EXECUTIONS ===\n{recent_tasks_summary}\n=== END RECENT TASKS ===\n\n"
                f'Current user message: "{message}"\n\n'
                f'Respond with ONLY valid JSON: {{"intent": "<one of: chat, security, system, research, search, code, image, diagram, codepipeline, analyze>", "reason": "<brief explanation>"}}'
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

    async def process(self, message: str) -> dict:
        """
        Main entry point: receive user message, route, execute, audit, and return response.
        """
        start = time.time()
        logger.info(f"[Brain] Processing: {message[:120]}")

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
