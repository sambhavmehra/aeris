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
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ValidationError

from ai_engine import ai_engine
from agents import ChatAgent, SecurityAgent, SystemAgent, ResearchAgent, CodeAgent, AuditAgent, ImageAgent, ObserverAgent, SearchAgent, AnalyzerAgent, OSINTAgent, EmailAgent, SchedulerAgent, DranaAgent, AntigravityAgent, DiagnosisAgent, RepairAgent, DebateAgent, InvestigationAgent, GuardianAgent, MechanicAgent, CriticAgent, ToolManagerAgent
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
# LLM Multi-Task Planning & Agentic Prompts
# ──────────────────────────────────────────────────────────────────────────────

PLANNER_PROMPT = """You are the AI Planner for AERIS.
Decompose the user's request into a sequential plan of tool calls to achieve the goal.
For each step, specify the tool to call, the arguments (as a JSON object), and a short description.

AVAILABLE TOOLS:
{tools_summary}

WORKSPACE DIRECTORY: {workspace_dir}
All file paths for write_file/read_file/edit_file MUST be relative paths (e.g. "report.txt") or within the workspace directory above.
NEVER use paths like "C:/", "D:/", "/tmp", or any absolute path outside the workspace.

KNOWN FOLDERS (use these EXACT paths when the user refers to these by name, alias, or Hinglish):
{known_folders_context}

CRITICAL RULES:
- FOLDER RESOLUTION: When the user refers to a folder using vague names, Hinglish, or aliases (e.g. "backend folder", "agents wala", "d drive pe kya hai", "download folder kholo", "services mein dekho", "wo folder dikhao"), you MUST resolve the folder name using the KNOWN FOLDERS section above. Use `list_system_dir` with the EXACT absolute path from the known folders. If the user says "open" a folder, use `open_folder` with the resolved path. Do NOT guess paths or use relative paths for folder browsing.
- When the user asks about "agents" (e.g. "kitne agent hai", "list agents", "how many agents"), use the `list_agents` tool, NOT `list_tools`.
- `list_tools` is ONLY for listing executable tool functions. `list_agents` is for listing AI agents.
- For ANY security-related request (SSL check, port scan, DNS lookup, recon, VAPT, vulnerability scan, WHOIS, subdomain enumeration), use the `security_scan` tool. NEVER use `smart_shell_generate` or `run_bash` for security scanning tasks.
- For sending email or mail notifications, ALWAYS use the `send_email` tool. Do NOT use `brevo_send_email` or `brevo_send_test_email` as they are meant for Brevo campaign/contact lists and will cause API authentication failures.
- If the user wants to schedule any task, reminder, alarm, meeting, or event, or if they confirm (e.g. saying 'yes', 'okay', 'ok', 'haan', 'sure', 'do it', 'kar do') a scheduling/reminder proposal made by the assistant in the conversation history (e.g. 'Should I put it in pending tasks and check in 30 minutes?'), you MUST use the `schedule_execution` tool.
  - If it is a confirmation to a proposal, set the 'instruction' to the task that was proposed to be scheduled (e.g. "Analyze website sambhavmehra.me"), and set 'time_spec' to the proposed time spec (e.g. "in 30 minutes").
  - Otherwise, if it is a reminder/alarm/meeting (e.g. "remind me to call Rahul"), set the 'instruction' parameter to a descriptive reminder message (e.g. "Remind user: Call Rahul").
  - If it is a system task/command (e.g. "open chrome"), set the 'instruction' parameter to the exact command/task to execute.
  - Set the 'time_spec' parameter to when it should run (e.g., 'in 1 minute', 'in 30 minutes', 'at 6pm').
- If the user wants to schedule a task/reminder or put a task in the pending tasks/list, but has NOT specified a time or delay (e.g., 'is task ko pending task mein daal le' without saying when), you MUST call `chat_with_ai` and pass the user's message, so the conversational agent can ask the user for the time. Do NOT run `schedule_execution` with a blank or guessed `time_spec`.
- If the user wants to read, write, or list files/folders located outside the workspace (e.g. absolute paths starting with a drive letter like C:\\, D:\\, or starting with ~ or /), you MUST use `read_system_file` or `list_system_dir` instead of `read_file` or `list_dir`. `read_file` and `list_dir` are strictly for relative paths inside the workspace directory.
- If you need to search the host system for a file by name, use `find_system_file`.
- For quick search, live facts, news, weather, or real-time info (e.g. looking up a person, site status, or current events), use `realtime_search` (which routes through the SearchAgent). If they request deep synthesis, comparison, academic research, or detailed reports on complex topics, use `web_research` (which routes through the ResearchAgent).
- If the user mentions 'antigravity', 'ide', or 'antigravity_agent', or requests to build/create a project using Antigravity, you MUST use the `build_project` tool to delegate it to the external Antigravity IDE assistant. Do NOT use `generate_website` or `generate_code` or `write_file` for this purpose.
- When the user asks to "open", "show", "view", or "run" a file (e.g. "usko open kr", "hr wali excel sheet open karo", "excel sheet open kr"), you MUST use the `open_file` tool.
  - DO NOT use `open_app` or `open_search` to open specific files or documents. `open_app` is strictly for starting application programs (like Chrome, Calculator) or navigating to website homepages.
  - RESOLVE PRONOUNS AND FILENAMES: Look at the RECENTLY CREATED FILES section. If the user refers to "it" ("usko"), "that file", "the excel sheet", "hr.xlsx", or "hr file", match it to the most relevant recently created file's absolute path (e.g., "D:\Sambhav Projects\AERIS\workspace\hr.xlsx"). Pass this absolute path to the `path` argument of `open_file`.
- NEVER use text-editing tools (edit_file, write_file) to modify or create binary file types like Excel sheets (.xlsx, .xls), Word files (.docx, .doc), PDFs (.pdf), or images. To create, update, or append details to Excel files, you MUST use update_excel_from_screen or export_to_excel. To extract transcripts/webpage content or take direct text and generate styled structured notes into a Word document, you MUST use extract_transcript_to_word.
  - For `update_excel_from_screen`, if the user explicitly asks to search the web/internet or if details should be looked up online, set the `source` parameter to "web". Otherwise, let it default to checking the screen, and the tool will ask the user for confirmation if not found on screen.
- Read each tool's description carefully and pick the BEST match for the user's intent.
- DYNAMIC TOOL CREATION: If a required capability or utility does not exist in the available tools list, you can propose a new, specific tool name that starts with `dynamic_` (e.g. `dynamic_calculate_fibonacci` or `dynamic_convert_currency`) and specify its required arguments and description. The system will autonomously forge, validate in a sandbox, and register the tool for execution on the fly.

ARGUMENT CONSTRUCTION RULES (VERY IMPORTANT):
- Read the parameter list under each tool carefully. Each parameter shows its TYPE and whether it is REQUIRED.
- For email tools: "to" expects an ARRAY of objects like [{{"email": "recipient@example.com", "name": "Name"}}]. "sender" expects an object {{"email": "sender@example.com", "name": "AERIS"}}. "subject" is a string. "htmlContent" is a string with HTML body.
- If the user's message does not contain a required parameter value (e.g. no recipient email), use chat_with_ai to ask the user for the missing info INSTEAD of guessing or leaving it blank.
- For write_file: "path" must be a RELATIVE path like "output.txt" or "reports/scan.md". It will be resolved within the workspace.
- NEVER fabricate placeholder values for required params. If info is missing, ask the user.

CONVERSATION CONTEXT:
{history}
{memory_context}

USER PROFILE:
{profile_context}

RECENTLY CREATED FILES:
{created_files_context}

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


async def parse_memory_command(message: str) -> Optional[str]:
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
        added = await memory_store.add_fact(fact)
        if added:
            return f"I will remember that: \"{fact}\""
        else:
            return f"I already know that or it looks like sensitive information."
            
    elif cmd in ["forget that", "forget"]:
        removed = await memory_store.remove_fact(fact)
        if removed:
            return f"I have forgotten: \"{fact}\""
        else:
            return f"I couldn't find a matching fact to forget."
            
    elif cmd == "update memory":
        added = await memory_store.add_fact(fact)
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
- "diagnose" : Run self-diagnostics checks on system hardware load, environment variables, agent status, package dependencies, or check codebase/files for syntax errors, console log checks, style conventions
- "analyze"  : Analyze files, logs, data, code outputs, system state — find patterns, errors, insights, or summarize contents
- "osint"   : Public source investigations, profile gathering, social footprint mappings, email/username lookups, dynamic pivot investigations, target intel compilation
- "email"   : Send emails, send mail, compose and send mail via SMTP/Brevo relay
- "scheduler" : Retrieve lists of background tasks, schedule reminders/alarms/meetings, or cancel tasks by ID or keyword (e.g., 'cancel meeting', 'list scheduled tasks', 'is task ko cancel kar do')
- "drana"    : Bug bounty hunting, JS recon, manual VAPT, XSS payload generation, traffic analysis
- "repair"   : Self-healing repairs for code, frontend/backend builds, broken tools, agent registry, workflow JSON, or generated project issues
- "investigation": Investigate failed tasks, errors, system issues, or general investigations, and cooperate with other agents to repair them.

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
    (["agent assemble", "assemble agents", "agent assembly", "assemble", "launch assembly"], "assemble"),
    (["scan", "port", "recon", "vulnerability", "nmap", "ssl", "hack",
      "header", "fuzz", "whois", "dns", "subdomain"], "security"),
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
      # Word / Transcript / Notes tools
      "transcript", "extract transcript", "generate notes", "word notes",
      "notes in word", "save to word", "save word", "docx notes", "notes docx",
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
      "project bana", "project banao", "app bana do", "antigravity",
      "antogravi ty", "antigravity_agent", "ide"
    ], "codepipeline"),
    # ── Diagram / flowchart / widget ─────────────────────────────────────────
    ([
      "flowchart", "flow chart", "diagram", "chart", "mind map", "mindmap",
      "architecture diagram", "system diagram", "sequence diagram",
      "er diagram", "class diagram", "network diagram",
      "widget", "visualize", "visualise", "flow banao", "chart banao",
      "diagram banao", "diagram bana", "chart bana",
    ], "diagram"),
    # ── Self / Code diagnostics ──────────────────────────────────────────────
    ([
      "diagnose", "diagnose self", "diagnose code", "system check", "self check",
      "code diagnostics", "system diagnostics", "self-diagnose", "code check",
      "diagnosis", "diagnosis check", "diagnose karo", "diagnosis karo"
    ], "diagnose"),
    # ── Analyze / inspect / diagnose ──────────────────────────────────────────
    ([
      "analyze", "analyse", "inspect", "summarize file",
      "analyze file", "analyse file", "check this file", "check this data",
      "parse this", "read and explain", "find issues in",
      "analyze karo", "analyse karo", "check karo", "dekhke batao",
      "file analyze", "log analyze", "data analyze", "analysis", "analysis karo"
    ], "analyze"),
    # ── OSINT investigations ──────────────────────────────────────────────────
    ([
      "osint", "investigate", "target intel", "email search", "username lookup",
      "social footprint", "trace target", "footprint check", "profile check",
      "target search", "profile trace", "stalk target", "stalk user", "recon target"
    ], "osint"),
    # ── Drana Agent ───────────────────────────────────────────────────────────
    ([
      "drana", "drafna", "js recon", "js analysis", "xss payload", "xss generate",
      "vapt analysis", "http analysis", "bug bounty", "pentest advice"
    ], "drana"),
    # ── Email routing ──────────────────────────────────────────────────────────
    ([
      "send email", "send mail", "email to", "mail to", "email send", "mail send",
      "compose email", "compose mail", "mail bhejo", "email bhejo", "mail bhej", "email bhej"
    ], "email"),
    # ── Repair routing ─────────────────────────────────────────────────────────
    ([
      "repair", "fix broken", "auto-repair", "self-heal", "repair code",
      "repair frontend", "repair backend", "repair workflow", "fix build",
      "repair tool", "repair agent", "fix error", "build failed",
      "not working", "broken"
    ], "repair"),
    # ── Swarm Debate routing ──────────────────────────────────────────────────
    ([
      "debate", "verify together", "cross-check", "swarm consensus",
      "consensus", "debate loop", "cross-verify", "agent debate"
    ], "debate"),
    # ── Investigation routing ─────────────────────────────────────────────────
    ([
      "investigate", "investigation", "failed task", "error log", "failure log",
      "check error", "check failure", "latest error", "latest failure",
      "investigate karo", "investigation karo", "failed log",
      "apni memory update", "memory update", "profile update", "update profile"
    ], "investigation"),
    # ── Casual Chat / Greeting / Personalization ──────────────────────────────
    ([
      "hello", "hi ", "hey", "good morning", "good afternoon", "good evening",
      "kaise ho", "how are you", "namaste", "suna", "yaar", "mast joke",
      "tell me a joke", "tell me a story", "suna de", "suna do", "sunaa de",
      "kaise hai", "kaise hain", "what is your name", "who are you",
      "who made you", "what is aeris", "aeris kya hai"
    ], "chat"),
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

    VALID_INTENTS = {"chat", "security", "system", "research", "search", "code", "image", "codepipeline", "diagram", "analyze", "osint", "email", "scheduler", "drana", "diagnose", "repair", "debate", "investigation", "assemble", "guardian", "mechanic", "critic", "tools"}

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
            "codepipeline": AntigravityAgent(),
            "diagnose": DiagnosisAgent(),
            "repair":   RepairAgent(),
            "debate":   DebateAgent(),
            "investigation": InvestigationAgent(),
            "guardian": GuardianAgent(),
            "mechanic": MechanicAgent(),
            "critic":   CriticAgent(),
            "tools":    ToolManagerAgent(),
        }
        self.antigravity_agent = self.agents["codepipeline"]
        self.audit_agent = AuditAgent()
        self.observer_agent = ObserverAgent()

        # ── Hacker Mode challenge state (for voice 2-step activation) ──
        self._hacker_challenge_pending = False
        self._guardian_challenge_pending = False

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
                VulnerabilityAgent, RuntimeAgent,
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

    async def approve_agent_delegation(self, requester_name: str, target_name: str, purpose: str) -> bool:
        """
        Evaluate and approve/deny a delegation request from one agent to another.
        Uses the LLM/ai_engine to make the authorization decision.
        """
        prompt = (
            f"You are the central AERIS Brain. An agent is requesting permission to use another agent.\n\n"
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
            from ai_engine import ai_engine
            import json
            response = await ai_engine.classify(prompt)
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[1] if "\n" in response else response[3:]
                if response.endswith("```"):
                    response = response[:-3]
                response = response.strip()
            decision = json.loads(response)
            approved = decision.get("approved", False)
            logger.info(f"[Brain] Delegation request: {requester_name} -> {target_name} ({purpose[:60]}...) | Approved: {approved} | Reason: {decision.get('reason')}")
            return approved
        except Exception as e:
            logger.warning(f"[Brain] Error evaluating delegation: {e}. Defaulting to True.")
            return True

    def _build_created_files_summary(self, limit: int = 5) -> str:
        """Format the list of recently created/modified files as a context string."""
        try:
            from utils.file_tracker import get_created_files
            records = get_created_files()
            if not records:
                return "No files created yet."
            lines = []
            for r in reversed(records[-limit:]):
                lines.append(f"- File '{r.get('filename')}' created at '{r.get('file_path')}' ({r.get('purpose')})")
            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to build created files summary: {e}")
            return "No files created yet."

    # ─────────────────────────── Intent Routing ───────────────────────────────

    def _build_history_summary(self, limit: int = 4) -> str:
        """Format last N memory messages as a compact context string for LLM prompts."""
        try:
            # Enforce last 2 turns (up to 4 messages) as raw history to preserve tone/phrasing
            history = memory_store.get_context(4)
            lines = []
            
            # Add active working facts from the memory store if any
            working_facts = memory_store.working_fact_cache
            if working_facts:
                lines.append("=== ACTIVE WORKING CONTEXT FACTS ===")
                for fact in working_facts:
                    lines.append(f"- {fact}")
                lines.append("====================================")
                lines.append("") # blank line separator
            
            if not history:
                lines.append("No prior conversation.")
            else:
                for msg in history:
                    role = msg.get("role", "user").upper()
                    content = msg.get("content", "")[:2000]
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

        # 2. Keyword fast-route (instant local mapping, bypass LLM latency)
          3. LLM classification — primary classifier, understands any language + history
          4. Keyword fallback — only if LLM fails entirely
        """
        # 1. Neural ML fast-route (high confidence only)
        if neural_core.is_intent_ready:
            try:
                label, confidence = neural_core.predict_intent_from_text(message)
                if label in self.VALID_INTENTS and confidence >= 0.85:
                     logger.info(f"[Brain] Neural fast-route -> '{label}' (conf={confidence:.2f})")
                     return label
                else:
                     logger.debug(f"[Brain] Neural not confident enough ({confidence:.2f}) for '{label}', checking keywords.")
            except Exception as e:
                logger.warning(f"[Brain] Neural routing failed: {e}")

        # 2. Keyword fast-route (instant local mapping, bypass LLM latency)
        keyword_intent = _keyword_route(message)
        if keyword_intent:
            logger.info(f"[Brain] Keyword fast-route -> '{keyword_intent}'")
            return keyword_intent

        # 3. LLM classification — primary, understands any language + conversation context
        history_summary = self._build_history_summary(3)
        recent_tasks_summary = self._build_recent_tasks_summary(3)
        try:
            raw = await ai_engine.classify(
                f"You are an intent classifier. Classify the following user message into EXACTLY ONE intent.\n\n"
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
                f"- diagnose : Run self-diagnostics checks on system hardware load, environment variables, agent status, package dependencies, or check codebase/files for syntax errors, console log checks, style conventions\n"
                f"- osint    : Public source investigations, profile gathering, social footprint mappings, email/username lookups, dynamic pivot investigations, target intel compilation\n"
                f"- email    : Send emails, send mail, compose and send mail via SMTP/Brevo relay\n"
                f"- scheduler : Retrieve lists of background tasks, schedule reminders/alarms/meetings, or cancel tasks by ID or keyword (e.g., 'cancel meeting', 'list scheduled tasks', 'is task ko cancel kar do')\n"
                f"- drana    : Bug bounty hunting, JS recon, manual VAPT, XSS payload generation, traffic analysis\n"
                f"- repair   : Self-healing repairs for code, frontend/backend builds, broken tools, agent registry, workflow JSON, or generated project issues\n"
                f"- investigation: Investigate failed tasks, errors, system issues, cooperate with other agents to repair them, or update the OWNER'S/USER'S profile (Name, Email, Role) in personal_details.json. Do NOT use this for external contacts (which should go to excel files instead).\n"
                f"- debate   : Swarm debate loop where multiple agents (proposer and auditor/critic) debate, critique, and refine a proposal/concept/code until reaching a consensus transcript.\n\n"
                f"FEW-SHOT EXAMPLES:\n"
                f"- \"search sambhav mehra on google\" -> system (reason: requests browser search visually)\n"
                f"- \"google pe python dhoondo\" -> system (reason: requests opening browser to search Google)\n"
                f"- \"search what is the weather today\" -> search (reason: requests quick realtime news/weather check in background)\n"
                f"- \"check ssl certificate for google.com\" -> security (reason: technical SSL scan)\n"
                f"- \"what is gravity?\" -> chat (reason: general knowledge definition)\n"
                f"- \"analyze log.txt and find errors\" -> analyze (reason: inspects file contents)\n"
                f"- \"write a node.js web server\" -> code (reason: requests code snippet implementation)\n"
                f"- \"send an email to boss@company.com saying I am sick\" -> email (reason: requests sending mail)\n"
                f"- \"rahul ko mail bhejo hello bolne ke liye\" -> email (reason: requests composing and sending email)\n"
                f"- \"debate the security of implementing custom hashing\" -> debate (reason: requests multi-agent debate loop)\n\n"
                f"The message may be in ANY language (English, Hindi, Hinglish, etc). Understand the MEANING, not just keywords.\n"
                f"Use the conversation history to resolve follow-up queries and pronouns (e.g., 'it', 'that', 'iska').\n"
                f"IMPORTANT: If the user message is a confirmation (e.g. 'yes', 'okay', 'ok', 'haan', 'sure', 'do it') to a scheduling or reminder proposal made by the assistant in the conversation history, you MUST classify the intent as 'scheduler'.\n\n"
                f"=== CONVERSATION HISTORY (last 3 messages) ===\n{history_summary}\n=== END HISTORY ===\n\n"
                f"=== RECENT AGENT TASK EXECUTIONS ===\n{recent_tasks_summary}\n=== END RECENT TASKS ===\n\n"
                f'Current user message: "{message}"\n\n'
                f'Respond with ONLY valid JSON: {{"intent": "<one of: chat, security, system, research, search, code, image, diagram, codepipeline, analyze, osint, email, scheduler, drana, diagnose, repair, debate>", "reason": "<brief explanation>"}}'
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

        result = None
        # Handle assemble intent
        if task.intent == "assemble":
            result = {
                "task_id": task.task_id,
                "intent": "assemble",
                "agent": "Brain",
                "response": "Initiating agent assembly sequence, Sir.",
                "success": True,
                "execution_time": 0.0,
            }
        # Handle diagram intent — generate an interactive React Flow widget
        elif task.intent == "diagram":
            try:
                from agents.diagram_agent import get_diagram_agent
                agent = get_diagram_agent()
                response = await agent.generate(task.description)
                result = {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "DiagramAgent",
                    "response": response,
                    "success": True, "execution_time": 0.0,
                }
            except Exception as e:
                logger.error(f"[Brain] DiagramAgent failed: {e}")
                result = {
                    "task_id": task.task_id, "intent": task.intent,
                    "agent": "DiagramAgent",
                    "response": f"Could not generate diagram: {e}",
                    "success": False, "execution_time": 0.0, "error": str(e),
                }

        else:
            agent = self.agents.get(task.intent, self.agents["chat"])
            try:
                res = await agent.run(task.description, context)
                result = {
                    "task_id": task.task_id,
                    "intent": task.intent,
                    "agent": agent.name,
                    "response": res.get("response", ""),
                    "success": res.get("success", True),
                    "execution_time": res.get("execution_time", 0.0),
                    "error": res.get("error"),
                }
            except Exception as e:
                logger.error(f"[Brain] Task '{task.task_id}' raised exception: {e}")
                result = {
                    "task_id": task.task_id,
                    "intent": task.intent,
                    "agent": agent.name,
                    "response": f"I encountered an error while processing this task: {str(e)}",
                    "success": False,
                    "execution_time": 0.0,
                    "error": str(e),
                }

        if not result.get("success", True):
            try:
                from utils.failure_logger import log_task_failure
                log_task_failure(
                    task_id=result.get("task_id", task.task_id),
                    step_id="",
                    tool_name=result.get("agent", "UnknownAgent"),
                    args={"description": task.description},
                    error=result.get("error") or result.get("response", "Agent task failure"),
                    agent_name=result.get("agent", "UnknownAgent"),
                    intent=task.intent
                )
                # Spawn background auto-investigation asynchronously
                asyncio.create_task(self.run_background_investigation(
                    task_id=result.get("task_id", task.task_id),
                    tool_name=result.get("agent", "UnknownAgent"),
                    error=result.get("error") or result.get("response", "Agent task failure"),
                    intent=task.intent
                ))
            except Exception as e:
                logger.warning(f"[Brain] Failed to log agent task failure: {e}")

            try:
                repair_agent = self.agents.get("repair")
                if repair_agent:
                    diag_context = dict(context or {})
                    diag_context["task_description"] = task.description
                    diagnosis = await repair_agent.diagnose_task_failure(result, diag_context)
                    if diagnosis.get("should_email", True):
                        email_agent = self.agents.get("email")
                        if email_agent:
                            await email_agent.execute({
                                "recipient": "sambhavmehra07@gmail.com",
                                "subject": f"⚠️ AERIS Task Failure: {result.get('agent', 'Unknown')}",
                                "body": diagnosis.get("report_html", "")
                            })
            except Exception as ex:
                logger.warning(f"[Brain] Post-failure diagnosis failed: {ex}")

        return result

    async def run_background_investigation(self, task_id: str, tool_name: str, error: str, intent: str = "general"):
        """Run the InvestigationAgent in the background to diagnose and heal failures."""
        logger.info(f"[Brain] Spawning background auto-investigation for failed task/tool: {tool_name}")
        try:
            investigation_agent = self.agents.get("investigation")
            if not investigation_agent:
                from agents.investigation_agent import InvestigationAgent
                investigation_agent = InvestigationAgent()
            
            message = f"failed task {tool_name} with error {error} investigate karo"
            res = await investigation_agent.run(message, {
                "failed_task_id": task_id,
                "failed_tool_name": tool_name,
                "failed_error": error,
                "failed_intent": intent
            })
            logger.info(f"[Brain] Background auto-investigation completed. Success={res.get('success', False)}")
            
            healing_success = res.get("healing_success", False)
            if res.get("success", False) and healing_success:
                logger.info(f"[Brain] Healing succeeded for failed tool {tool_name}. Clearing failure records.")
                from utils.failure_logger import clear_resolved_failures
                clear_resolved_failures(tool_name, error)
                self._clear_sent_notification(tool_name, error)
            
            # Send investigation report email to user ONLY if healing FAILED
            if res.get("success", False) and not healing_success and res.get("response"):
                if self._should_send_email_for_failure(tool_name, error):
                    email_agent = self.agents.get("email")
                    if email_agent:
                        from utils.personal_details_helper import load_personal_details
                        details = load_personal_details()
                        user_email = details.get("Email") or "sambhavmehra07@gmail.com"
                        user_name = details.get("Name") or "Sir"
                        
                        subject = f"⚠️ AERIS Investigation Report: {tool_name} failure unresolved"
                        body = f"""
                        <html>
                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                            <h2 style="color: #A30000;">AERIS Background Failure Investigation Report</h2>
                            <p>Dear {user_name},</p>
                            <p>A tool failure was encountered in <strong>{tool_name}</strong> and could not be automatically healed. Below are the details:</p>
                            <hr style="border: 0; border-top: 1px solid #eee;" />
                            <div style="background-color: #f9f9f9; padding: 15px; border-left: 4px solid #A30000; font-family: monospace; white-space: pre-wrap; margin: 15px 0;">
{res.get("response")}
                            </div>
                            <hr style="border: 0; border-top: 1px solid #eee;" />
                            <p>Best regards,<br/><strong>AERIS Central System</strong></p>
                        </body>
                        </html>
                        """
                        logger.info(f"[Brain] Sending auto-investigation report email to {user_email}...")
                        await email_agent.execute({
                            "recipient": user_email,
                            "subject": subject,
                            "body": body
                        })
        except Exception as e:
            logger.error(f"[Brain] Background auto-investigation failed: {e}")

    def _should_send_email_for_failure(self, tool_name: str, error: str) -> bool:
        """Check if we have already sent an email for this specific tool and error to avoid duplicates."""
        try:
            import hashlib
            from pathlib import Path
            from datetime import datetime
            
            notif_file = Path(settings.DATA_DIR) / "sent_notifications.json"
            
            # Normalize error message by removing digits/hex values to avoid minor variations
            normalized_error = "".join([c for c in error if not c.isdigit()]).lower()
            error_hash = hashlib.md5(f"{tool_name}:{normalized_error}".encode("utf-8")).hexdigest()
            
            notifications = {}
            if notif_file.exists() and notif_file.stat().st_size > 0:
                try:
                    notifications = json.loads(notif_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            
            # If we already sent it, return False
            if error_hash in notifications:
                logger.info(f"[Brain] Email for failure {tool_name} with error already sent. Skipping duplicate email.")
                return False
                
            # Otherwise, record it and return True
            notifications[error_hash] = {
                "tool_name": tool_name,
                "error": error,
                "timestamp": datetime.now().isoformat()
            }
            notif_file.write_text(json.dumps(notifications, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.warning(f"Failed to check duplicate email notifications: {e}")
            return True  # Fallback to sending the email if tracker fails

    def _clear_sent_notification(self, tool_name: str, error: str) -> None:
        """Clear notification registry for this tool/error once it is resolved."""
        try:
            import hashlib
            from pathlib import Path
            notif_file = Path(settings.DATA_DIR) / "sent_notifications.json"
            if notif_file.exists() and notif_file.stat().st_size > 0:
                notifications = json.loads(notif_file.read_text(encoding="utf-8"))
                normalized_error = "".join([c for c in error if not c.isdigit()]).lower()
                error_hash = hashlib.md5(f"{tool_name}:{normalized_error}".encode("utf-8")).hexdigest()
                if error_hash in notifications:
                    del notifications[error_hash]
                    notif_file.write_text(json.dumps(notifications, indent=2), encoding="utf-8")
                    logger.info(f"[Brain] Cleared sent notification tracker for {tool_name} as it got resolved.")
        except Exception as e:
            logger.warning(f"Failed to clear notification registry: {e}")

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

    async def execute_agentic_loop(self, message: str, pending_state: Optional[dict] = None, task_id: Optional[str] = None) -> dict:
        """
        Execute the agentic loop: plan -> tool call -> observe -> reflect -> final response.
        Supports resuming from pending_state if user approved a tool call.
        """
        start = time.time()
        task_id = task_id or (pending_state.get("task_id") if pending_state else f"task_{int(time.time())}")
        self._retry_counts = {}  # Reset retry counters for each new execution
        workspace_dir = str(settings.WORKSPACE_DIR)
        intent = "tool_execution"
        
        # 1. Plan / Resume Plan
        if pending_state:
            # Resume from saved state
            plan_dict = pending_state.get("plan")
            if not isinstance(plan_dict, dict):
                plan_dict = {}
            plan = AgenticPlan(**plan_dict)
            current_step_index = pending_state.get("current_step_index", 0)
            observations = [Observation(**obs) for obs in pending_state.get("observations", [])]
            logger.info(f"[Brain] Resuming agentic plan execution from step {current_step_index}")
        else:
            # Generate new plan
            # 1. Intent Classifier (small model is used by default in _classify_intent)
            intent = await self._classify_intent(message)
            logger.info(f"[Brain] Plan Generation intent classification: {intent}")

            # 2. Tool Retriever
            from tools.universal_registry import get_universal_registry
            from intelligence.selection_intelligence import get_selection_intelligence
            
            # Retrieve top 10 relevant tools using SelectionIntelligence
            selection_intel = get_selection_intelligence()
            retrieved_candidates = selection_intel.select(message, intent=intent, top_k=10)
            retrieved_names = {c.tool_name for c in retrieved_candidates}
            
            # Always ensure core utility tools are available to prevent planner getting stuck
            core_utilities = {"chat_with_ai", "run_bash", "read_file", "write_file", "edit_file", "web_research", "realtime_search", "schedule_execution", "read_system_file", "find_system_file", "find_system_folder", "list_system_dir", "open_folder"}
            selected_names = retrieved_names.union(core_utilities)
            
            registry = get_universal_registry()
            selected_tools = []
            for name in selected_names:
                tool_def = registry.get_tool(name)
                if tool_def and tool_def.is_enabled:
                    selected_tools.append(tool_def)
            
            from intelligence.context_injector import get_context_injector
            
            history = self._build_history_summary(10)
            memory_context = await memory_store.get_relevant_memory_context(message)
            
            # Build planning context package
            context_pkg = get_context_injector().build_planning_context(
                objective=message,
                memory_context=memory_context,
                selected_tool_names=list(selected_names)
            )
            
            all_tools_count = len(registry.get_enabled_tools())
            logger.info(f"[Brain] Retracted tools list from {all_tools_count} to {len(selected_tools)} (savings: {round((1 - len(selected_tools)/all_tools_count)*100, 1)}%)")
            
            from memory.user_profile import user_profile_store
            profile = user_profile_store.get_profile()
            profile_context = (
                f"User's Name: {profile.get('name', settings.USERNAME)}\n"
                f"Language Preference: {profile.get('language_preference', 'Hinglish')}\n"
                f"Tone Preference: {profile.get('tone_preference', 'natural agentic')}\n"
                f"Preferred Response Style: {profile.get('preferred_response_style', '')}"
            )
            
            # 4. Known Folders Context (for smart folder resolution in planner)
            try:
                from intelligence.folder_intelligence import get_folder_intelligence
                known_folders_context = get_folder_intelligence().get_known_folders_summary(20)
            except Exception:
                known_folders_context = "No folder index available."
            
            prompt = PLANNER_PROMPT.format(
                tools_summary=context_pkg["tools_text"],
                history=history,
                memory_context=context_pkg["full_system_prompt_section"],
                profile_context=profile_context,
                created_files_context=self._build_created_files_summary(5),
                known_folders_context=known_folders_context,
                message=message,
                workspace_dir=workspace_dir
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
            # Check pause status
            from services.job_manager import get_job_manager
            job_mgr = get_job_manager()
            job = job_mgr.get_job(task_id)
            if job and job["status"] == "paused":
                logger.info(f"[Brain] Job {task_id} is paused. Waiting for resume/cancel.")
                while True:
                    await asyncio.sleep(1)
                    job = job_mgr.get_job(task_id)
                    if not job:
                        break
                    if job["status"] == "cancelled":
                        raise asyncio.CancelledError()
                    if job["status"] in ("running", "queued"):
                        logger.info(f"[Brain] Job {task_id} resumed.")
                        job_mgr.update_job(task_id, status="running", event="Job execution resumed from pause.")
                        break

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
            
            # Check permissions first (Task 3: explicit approval check)
            from tools.universal_registry import get_universal_registry
            from tools.tool_permissions import get_permission_system
            
            tool_def = get_universal_registry().get_tool(step.tool_name)
            if not tool_def:
                if step.tool_name.startswith("dynamic_") or "create" in step.description.lower():
                    logger.info(f"[Brain] Tool '{step.tool_name}' not found. Attempting autonomous generation...")
                    try:
                        tm_agent = self.agents.get("tools")
                        if not tm_agent:
                            from agents.sub_agents.tool_manager_agent import ToolManagerAgent
                            tm_agent = ToolManagerAgent()
                        
                        forge_res = await asyncio.to_thread(
                            tm_agent.create_tool,
                            request=f"Create a tool named '{step.tool_name}' that does: {step.description}. Input arguments: {json.dumps(step.args)}",
                            tool_name=step.tool_name
                        )
                        if forge_res.get("success"):
                            logger.info(f"[Brain] Successfully forged and registered dynamic tool '{step.tool_name}'. Retrying execution...")
                            tool_def = get_universal_registry().get_tool(step.tool_name)
                    except Exception as forge_err:
                        logger.error(f"[Brain] Failed to autonomously forge tool '{step.tool_name}': {forge_err}")

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
                    # PAUSE execution and wait for user approval
                    pending_file = settings.DATA_DIR / "pending_approval.json"
                    state_to_save = {
                        "plan": plan.dict(),
                        "message": message,
                        "current_step_index": current_step_index,
                        "observations": [obs.dict() for obs in observations],
                        "tool_name_pending": step.tool_name,
                        "args_pending": step.args,
                        "task_id": task_id,
                        "agent": "Brain"
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
                
            # ── Pre-execution argument sanitizer ────────────────────────
            # Fix common planner mistakes before they cause runtime failures
            sanitized_args = dict(step.args)
            
            # Fix 1: write_file / edit_file paths — ensure they stay within workspace
            if step.tool_name in ("write_file", "edit_file", "read_file") and "path" in sanitized_args:
                raw_path = sanitized_args["path"]
                ws_dir = Path(settings.WORKSPACE_DIR)
                resolved = Path(raw_path).resolve() if Path(raw_path).is_absolute() else (ws_dir / raw_path).resolve()
                try:
                    resolved.relative_to(ws_dir.resolve())
                except ValueError:
                    # Path is outside workspace — use just the filename inside workspace
                    sanitized_args["path"] = Path(raw_path).name
                    logger.info(f"[Brain] Sanitized path: '{raw_path}' → '{sanitized_args['path']}' (kept within workspace)")
            
            # Fix 2: Check required params exist before execution
            skip_execution = False
            if tool_def and tool_def.input_schema:
                missing = [p.name for p in tool_def.input_schema.params if p.required and p.name not in sanitized_args]
                if missing:
                    obs = Observation(
                        step_id=step.step_id,
                        tool_name=step.tool_name,
                        success=False,
                        result="",
                        error=f"Missing required arguments: {', '.join(missing)}. The planner must provide these values.",
                        duration_ms=0.0
                    )
                    skip_execution = True
            
            step.args = sanitized_args
            
            # Execute tool call (only if pre-validation passed)
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
            
            # Reflection step: only run if the step failed, to self-correct
            if not obs.success:
                # Trigger background auto-investigation asynchronously
                asyncio.create_task(self.run_background_investigation(
                    task_id=task_id,
                    tool_name=step.tool_name,
                    error=obs.error or "Unknown tool execution failure",
                    intent=intent
                ))
                reflection_prompt = f"""You are the AI Reflector for AERIS — your job is to SELF-CORRECT failures.

ORIGINAL PLAN:
{json.dumps(plan.dict(), indent=2)}

OBSERVATIONS SO FAR:
{json.dumps([o.dict() for o in observations], indent=2)}

CURRENT STEP ID: {step.step_id}
WORKSPACE DIRECTORY: {workspace_dir if 'workspace_dir' in dir() else str(settings.WORKSPACE_DIR)}

Analyze the LAST observation:

IF THE STEP SUCCEEDED:
- Set should_continue = true, suggested_changes = null
- Continue with the remaining plan steps

IF THE STEP FAILED — YOU MUST SELF-CORRECT (do NOT just abort):
1. **Missing/invalid arguments**: Provide a corrected retry step with the SAME tool but FIXED args.
   - Missing "to" in email → add a step using chat_with_ai to ask the user for the recipient
   - Wrong param types → fix the types (e.g., "to" should be an array of objects [{{"email":"...", "name":"..."}}])
2. **Path errors** (workspace boundary, file not found):
   - Replace absolute paths with workspace-relative paths (e.g., "report.txt" instead of "C:/report.txt")
3. **SECURITY_BLOCKED**: Skip the blocked step and continue with remaining steps. Do NOT retry blocked tools.
4. Only set should_continue = false if the ENTIRE goal is impossible (e.g., the requested tool doesn't exist).

Respond with ONLY valid JSON:
{{
  "step_id": "{step.step_id}",
  "thought": "<your analysis of what went wrong and how to fix it>",
  "should_continue": true,
  "suggested_changes": null or [{{"step_id": "retry_1", "tool_name": "tool_name", "args": {{}}, "description": "description"}}]
}}
"""
                ref_data = await query_llm_json(reflection_prompt)
                if ref_data:
                    try:
                        # Robust fix: check if suggested_changes is a dictionary instead of a list
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
                        logger.info(f"[Brain] Reflection step {step.step_id}: {reflection.thought}")
                        
                        # Track retries to prevent infinite correction loops
                        retry_key = f"{step.step_id}_{step.tool_name}"
                        if not hasattr(self, '_retry_counts'):
                            self._retry_counts = {}
                        
                        if not reflection.should_continue:
                            # Check if reflection is aborting a failed step — give it one more chance
                            if not obs.success and self._retry_counts.get(retry_key, 0) < 2 and reflection.suggested_changes:
                                logger.info(f"[Brain] Overriding abort — applying self-correction (retry {self._retry_counts.get(retry_key, 0) + 1}/2)")
                                self._retry_counts[retry_key] = self._retry_counts.get(retry_key, 0) + 1
                                plan.steps = plan.steps[:current_step_index] + reflection.suggested_changes
                                logger.info(f"[Brain] Self-correction applied. New plan length: {len(plan.steps)}")
                            else:
                                logger.info(f"[Brain] Reflection decided to abort further steps.")
                                break
                        elif reflection.suggested_changes:
                            self._retry_counts[retry_key] = self._retry_counts.get(retry_key, 0) + 1
                            if self._retry_counts[retry_key] <= 2:
                                plan.steps = plan.steps[:current_step_index] + reflection.suggested_changes
                                logger.info(f"[Brain] Reflection updated plan steps. New plan length: {len(plan.steps)}")
                            else:
                                logger.warning(f"[Brain] Max retries reached for {retry_key}. Skipping correction.")
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

RECENTLY CREATED FILES:
{self._build_created_files_summary(5)}

EXECUTED PLAN:
{json.dumps(plan.dict(), indent=2)}

OBSERVATIONS & TOOL OUTPUTS:
{json.dumps([o.dict() for o in observations], indent=2)}

═══════════ RECENTLY ADDED ADVANCED FEATURES ═══════════
Sir (Sambhav Mehra) has recently completed the implementation of all requested advanced features! They are now fully active and verified:
- Advanced NLP Service (NLTK Sentiment, SpaCy en_core_web_sm entities, parts-of-speech, and noun phrases).
- Machine Learning Service (Scikit-Learn models: Linear Regression, KMeans, Random Forest Classifier).
- Data Analytics Service (Pandas CSV descriptive stats and Pearson correlation matrix).
- Cloud Integration Simulator (Mock bucket operations and compute VM instance provisioning).
- Enhanced Vision Engine (OpenCV filters: grayscale, blur, edge, threshold).
- Virtual Assistant Service (Speech synth TTS, turn logger, and personalized ML recommendations).

If Sir asks if these features are implemented, or asks you to check them, respond enthusiastically and proudly in Hinglish, confirming that they are 100% active, fully verified, and ready to be used. Explain how each feature/tool works and offer to run them for him (e.g. running NLP on a sentence, clustering coordinates, analyzing a CSV data file, applying OpenCV filters, or simulating cloud storage operations).

HINGLISH PERSONALIZATION RULES:
- If the user writes in Hinglish (Hindi written in Latin/Roman script, e.g., "kaise ho", "kya chal raha hai") or Hindi, you MUST naturally respond in modern, conversational Hinglish.
- Keep the language flow smooth, colloquial, and friendly (e.g., "Haan, bilkul!", "Main isko check karta hoon").
- Do not use overly formal/robotic Google-translated Hindi. Match the user's Roman-script Hindi style.
- ALWAYS address the user as "Sir" (or "sir") in all responses. NEVER address the user as "bhai", "bro", "buddy", or any other informal/colloquial terms, even if the user addresses you informally.

PROACTIVE SCHEDULING RULES (CRITICAL):
- Look at the "OBSERVATIONS & TOOL OUTPUTS" above. If any step failed, had errors, or if a web/RAG search or scraper tool returned no results, you MUST suggest to the user to put it in pending tasks to run or check again later.
- Example: "Sir, RAG search/website scrape failed. Kya main isko pending tasks mein daal du aur 30 minutes baad check karu?" (Feel free to suggest scheduling it for later).
- If the user asked you to schedule a meeting, set a reminder, or run a command after a delay, let them know you are scheduling it.
- If the user wants to schedule a task or put something in "pending tasks" but no schedule tool was executed because the time was not specified, you MUST ask the user for the time (e.g., "Sir, aap is task ko kitne baje ya kitni der baad run karna chahte hain?"). NEVER suggest or hallucinate about requiring external APIs (like Google News API) or fake commands (like "Dal Task").

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
            "agent": "AgenticLoop",
            "tasks_executed": len(observations),
            "tasks_succeeded": len(succeeded),
            "tasks_failed": len(failed),
            "execution_time": elapsed,
            "success": len(failed) == 0,
            "task_id": task_id,
            "summary": summary_actions,
        }

    async def _process_internal(self, message: str) -> dict:
        """
        Internal process logic: receive user message, check memory commands,
        check pending approvals, execute agentic loop, or run legacy flow.
        """
        lower_msg = message.lower()
        from services.guardian_mode import guardian_mode_manager
        from services.self_evolution import self_evolution_engine

        # --- Self-Evolution Interceptors ---
        if any(cmd in lower_msg for cmd in ["apply proposal", "confirm proposal", "apply upgrade", "execute upgrade", "accept proposal"]):
            success, response_text = await self_evolution_engine.execute_proposal()
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "self_evolution_execute",
                "agent": "Brain",
                "success": success,
                "task_id": f"evo_{int(time.time())}"
            }

        is_upgrade_req = (
            "tu khud kyu" in lower_msg or 
            "khud kyu nahi" in lower_msg or 
            "khud se soch" in lower_msg or 
            "self-implement" in lower_msg or
            ("implement" in lower_msg and any(w in lower_msg for w in ["iot", "sensor", "emotion", "sentiment", "nlg", "encryption", "multi-language", "language"])) or
            ("integrate" in lower_msg and any(w in lower_msg for w in ["iot", "sensor", "emotion", "sentiment", "nlg", "encryption", "multi-language", "language"])) or
            ("add" in lower_msg and any(w in lower_msg for w in ["iot", "sensor", "emotion", "sentiment", "nlg", "encryption", "multi-language", "language"]))
        )
        if is_upgrade_req:
            res = await self_evolution_engine.propose_improvement(message)
            if res.get("success"):
                response_text = res.get("report")
            else:
                response_text = f"Sir, improvement proposal generate karne mein error aaya: {res.get('error')}"
                
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "self_evolution_propose",
                "agent": "Brain",
                "success": res.get("success", False),
                "task_id": f"evo_{int(time.time())}"
            }

        # --- Guardian Mode Challenge Flow ---
        if getattr(self, "_guardian_challenge_pending", False):
            self._guardian_challenge_pending = False
            
            if any(cmd in lower_msg for cmd in ["cancel", "abort", "nevermind", "go back"]):
                response_text = "Clearance cancelled. Guardian Mode remains active, Sir."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "guardian_deactivation_cancelled",
                    "agent": "Brain",
                    "success": True,
                    "task_id": f"grd_{int(time.time())}"
                }
                
            success, msg = guardian_mode_manager.disable_guardian_mode(code=message.strip())
            if success:
                response_text = msg
            else:
                guardian_mode_manager._handle_violation(
                    viol_type="risky_action",
                    target="Clearance Code",
                    details="Invalid PIN/secret phrase deactivation attempt.",
                    hwnd=0
                )
                response_text = "Access Denied, Sir. Invalid security clearance code."
                
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "guardian_deactivation",
                "agent": "Brain",
                "success": success,
                "task_id": f"grd_{int(time.time())}"
            }

        # --- Guardian Mode Command Interceptors ---
        activation_keywords = [
            "guest mode enable karo", "guest mode enable", "guest mode on", "guest mode chalu",
            "ye main nahi hoon", "ye main nahi hu", "guardian mode activate", "enable guardian mode",
            "guardian mode on", "activate guardian mode"
        ]
        if any(cmd in lower_msg for cmd in activation_keywords):
            response_text = guardian_mode_manager.enable_guardian_mode(method="text")
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "guardian_activation",
                "agent": "Brain",
                "success": True,
                "task_id": f"grd_{int(time.time())}"
            }

        deactivation_keywords = [
            "disable guardian mode", "disable guardian", "off guardian mode", "guardian mode off",
            "turn off guardian mode", "disable guest mode", "guest mode off"
        ]
        if any(cmd in lower_msg for cmd in deactivation_keywords):
            if not guardian_mode_manager.is_active:
                response_text = "Sir, Guardian Mode already off hai."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "guardian_deactivation",
                    "agent": "Brain",
                    "success": True,
                    "task_id": f"grd_{int(time.time())}"
                }
                
            # Check if they provided code inline
            words = message.split()
            code_attempt = ""
            for word in words:
                word_clean = word.strip(" .,!?").lower()
                if word_clean.isdigit() or word_clean == guardian_mode_manager.config.get("secret_phrase", "sambhav"):
                    code_attempt = word_clean
                    break
                    
            if code_attempt:
                success, msg = guardian_mode_manager.disable_guardian_mode(code=code_attempt)
                response_text = msg
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "guardian_deactivation",
                    "agent": "Brain",
                    "success": success,
                    "task_id": f"grd_{int(time.time())}"
                }
            else:
                self._guardian_challenge_pending = True
                response_text = "Please enter your security clearance PIN or secret phrase to disable Guardian Mode."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "guardian_deactivation_challenge",
                    "agent": "Brain",
                    "success": True,
                    "task_id": f"grd_{int(time.time())}"
                }

        # --- Guardian Mode Request Gating ---
        if guardian_mode_manager.is_active:
            is_blocked_req = False
            for app in guardian_mode_manager.config.get("blocked_apps", []):
                if app.lower().replace(".exe", "") in lower_msg:
                    is_blocked_req = True
                    break
            for domain in guardian_mode_manager.config.get("blocked_domains", []):
                short_domain = domain.split(".")[0] if "." in domain else domain
                if short_domain in lower_msg:
                    is_blocked_req = True
                    break
            for folder in guardian_mode_manager.config.get("protected_folders", []):
                if folder.lower() in lower_msg:
                    is_blocked_req = True
                    break
                    
            if is_blocked_req:
                guardian_mode_manager._handle_violation(
                    viol_type="app",
                    target="Restricted Request",
                    details=f"Text request blocked under Guardian Mode: '{message}'",
                    hwnd=0
                )
                response_text = "Guardian Mode is active. This app/site/folder is private and requires owner approval."
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "guardian_blocked",
                    "agent": "Brain",
                    "success": False,
                    "task_id": f"grd_{int(time.time())}"
                }

        # Intercept Hacker Mode Toggle Commands

        # Intercept Map/HUD Clearing Commands
        if any(cmd in lower_msg for cmd in ("clear map", "clear scan map", "reset map", "clear hud", "clear graph")):
            graph_path = settings.DATA_DIR / "webweaver_graph.json"
            default_graph = {
                "nodes": [
                    {"id": "aeris_brain", "label": "AERIS Brain", "type": "host", "ip": "127.0.0.1", "status": "online"},
                    {"id": "api_gateway", "label": "FastAPI Gateway", "type": "service", "status": "online"}
                ],
                "links": [
                    {"source": "aeris_brain", "target": "api_gateway", "type": "connection", "port": 8000}
                ]
            }
            try:
                graph_path.parent.mkdir(parents=True, exist_ok=True)
                graph_path.write_text(json.dumps(default_graph, indent=2))
                response_text = "Sir, maine HUD scan map ko clear aur reset kar diya hai to default system nodes."
            except Exception as e:
                response_text = f"Sir, HUD map clear karne mein error aaya: {str(e)}"
            
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True,
                "task_id": "clear_hud_map"
            }


        # Intercept Screen Monitoring Commands
        from services.screen_monitor import get_screen_monitor
        monitor = get_screen_monitor()

        # Check if user is answering a pending question about a selected screen area
        if monitor.crop_box and not any(w in lower_msg for w in ("clear selection", "clear crop", "reset screen", "stop monitoring", "select area", "select screen", "ye dekho", "isko dekho", "ye select karo", "isko select karo", "ye area dekho", "yahan dekho", "is area ko dekho", "ye dekhao")):
            # User has an active selection and is saying something that isn't a screen command
            # Check if this could be a follow-up question about the selected area
            question_indicators = ["kya hai", "kya ho raha", "batao", "explain", "samjhao", "describe", "fix karo", "solve", "help", "error", "issue", "problem", "dikkat", "galat", "sahi", "check", "what is", "what's", "how to", "why", "isme", "isne", "yahan", "ye kya", "isko", "iske"]
            if any(q in lower_msg for q in question_indicators):
                result = await monitor.analyze_region_with_query(
                    monitor.crop_box[0], monitor.crop_box[1], 
                    monitor.crop_box[2], monitor.crop_box[3], 
                    message
                )
                response_text = result.get("response", "Sir, maine analyze kar liya hai.")
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "chat",
                    "agent": "Brain",
                    "success": True,
                    "task_id": "screen_query_region"
                }

        if any(w in lower_msg for w in ("start monitoring", "screen monitor karo", "monitor my screen", "monitor screen chalu", "screen monitor chalu", "continuously monitor", "monitor screen start")):
            monitor.start_monitoring()
            response_text = "Sir, maine continuous screen monitoring chalu kar di hai. Main aapki screen ko continuously monitor karunga aur agar koi issue ya optimization milegi toh screen par overlay show karunga."
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True,
                "task_id": "screen_monitor_start"
            }

        elif any(w in lower_msg for w in ("select area", "select screen", "crop screen", "crop area", "analyze area", "selection chalu", "selection enable", "region select", "ye dekho", "isko dekho", "ye select karo", "isko select karo", "ye area dekho", "yahan dekho", "is area ko dekho", "ye dekhao")):
            # Check if there is also a question or query mentioned in the same sentence
            has_query = False
            extracted_query = None
            
            # Common query indicators in voice mode
            query_indicators = ["kya hai", "kya ho raha", "batao", "explain", "samjhao", "describe", "fix karo", "solve", "help", "error", "issue", "problem", "dikkat", "galat", "sahi", "check", "what is", "what's", "how to", "why", "isme", "isne", "yahan", "ye kya", "isko", "iske"]
            if any(q in lower_msg for q in query_indicators):
                has_query = True
                extracted_query = message
                
            monitor.trigger_selection()
            
            if has_query:
                monitor.set_pending_query(extracted_query)
                response_text = "Sir, maine screen selection mode chalu kar diya hai. Aap area select karein, main uske baare me bataunga."
            else:
                monitor.set_pending_query(None)
                response_text = "Sir, maine screen selection mode chalu kar diya hai. Aap area select karein. Phir batayein, kya aap us area ke baare me kuch jaanna chahte hain?"
                
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True,
                "task_id": "screen_selection_start"
            }

        elif any(w in lower_msg for w in ("clear selection", "clear crop", "reset screen", "full screen", "selection clear", "crop reset", "normal screen")):
            from services.screen_monitor import get_screen_monitor
            get_screen_monitor().clear_crop_box()
            response_text = "Sir, maine screen selection reset kar di hai. Ab main poori screen monitor karunga."
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True,
                "task_id": "screen_selection_reset"
            }

        # Check for visual grounding/localization command
        # E.g. "analyze the terminal on screen", "tokay wala text analyze karo"
        elif any(w in lower_msg for w in ("on screen", "wala", "locate", "find on screen")) and any(w in lower_msg for w in ("analyze", "check", "select", "dhoondo", "dekh", "scan")):
            import re
            target_term = None
            
            # Pattern 1: (analyze|locate|find|select) <target> on screen
            m1 = re.search(r'\b(?:analyze|locate|find|select|check|scan)\s+(.+?)\s+on\s+screen\b', lower_msg)
            if m1:
                target_term = m1.group(1).strip()
                
            # Pattern 2: <target> wala (text|image|video|chiz|photo) analyze (karo|kro|kr)
            m2 = re.search(r'\b(.+?)\s+wala\s+(text|image|video|chiz|photo|button|logo|code)\s+(?:analyze|check|locate|dekh|scan)\b', lower_msg)
            if m2:
                target_term = f"{m2.group(1).strip()} {m2.group(2).strip()}"
                
            # Pattern 3: analyze <target> wala
            m3 = re.search(r'\b(?:analyze|check|locate|dekh|scan)\s+(.+?)\s+wala\b', lower_msg)
            if m3:
                target_term = f"{m3.group(1).strip()} element"

            # Pattern 4: Hinglish fallback for "wala" pattern
            if not target_term and "wala" in lower_msg:
                parts = lower_msg.split("wala")
                if len(parts) >= 2:
                    before = parts[0].strip()
                    # take the first word after wala
                    after_words = parts[1].strip().split()
                    after = after_words[0] if after_words else "element"
                    target_term = f"{before} {after}"

            if target_term:
                from services.screen_monitor import get_screen_monitor
                response_text = await get_screen_monitor().locate_and_analyze_element(target_term)
                memory_store.add_message("user", message)
                memory_store.add_message("assistant", response_text)
                return {
                    "response": response_text,
                    "intent": "chat",
                    "agent": "Brain",
                    "success": True,
                    "task_id": "screen_selection_grounding"
                }

        elif any(w in lower_msg for w in ("stop monitoring", "screen monitor band", "stop monitor", "monitoring band", "stop screen monitoring")):
            from services.screen_monitor import get_screen_monitor
            get_screen_monitor().stop_monitoring()
            response_text = "Sir, maine screen monitoring band kar di hai."
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True,
                "task_id": "screen_monitor_stop"
            }
            
        elif any(w in lower_msg for w in ("implement it", "ise implement kar do", "implement suggestion", "thik karo", "thik kar do")):
            from services.screen_monitor import get_screen_monitor
            success, response_text = await get_screen_monitor().implement_last_suggestion()
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": success,
                "task_id": "screen_monitor_implement"
            }
            
        elif any(w in lower_msg for w in ("suggest", "suggestion do", "suggest karo", "suggest kro", "check screen", "screen check")):
            from services.screen_monitor import get_screen_monitor
            response_text = await get_screen_monitor().check_screen_and_suggest_now()
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True,
                "task_id": "screen_monitor_suggest_now"
            }

        # Check if the user query requests auto-repair of workspace syntax errors
        from services.workspace_watcher import handle_conversational_repair
        repair_res = await handle_conversational_repair(message)
        if repair_res:
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
                    "agent": "Brain",
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
                    "agent": "Brain",
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
                    "agent": "Brain",
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
                    "agent": "Brain",
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
                "agent": "Brain",
                "success": True,
                "task_id": f"jobs_{int(time.time())}"
            }

        # ── Voice 2-step flow: if a challenge was pending, check for password keyword ──
        if self._hacker_challenge_pending:
            self._hacker_challenge_pending = False  # Always clear after one attempt
            
            # Allow cancelling the challenge/switching back to normal mode
            if any(cmd in lower_msg for cmd in ["off hacker mode", "switch to productivity", "switch to productivity mode", "productivity mode", "switch back", "back to normal", "normal mode", "cancel", "abort", "nevermind"]):
                return {
                    "response": "Security clearance cancelled. Main Normal Mode mein hi hoon, Sir.",
                    "intent": "chat",
                    "agent": "Brain",
                    "hacker_mode_challenge": False,
                    "hacker_mode_activated": False,
                    "success": True,
                    "tasks_executed": 1,
                    "tasks_succeeded": 1,
                    "tasks_failed": 0,
                    "execution_time": 0.0,
                    "task_id": f"hac_{int(time.time())}"
                }
                
            if "sambhav" in lower_msg:
                from memory.user_profile import user_profile_store
                user_profile_store.update_profile(hacker_mode=True)
                return {
                    "response": "Security clearance verified, Sir. Hacker Brain Mode activated. Full security, OSINT, aur Drana capabilities online hain.",
                    "intent": "hacker_mode_activation",
                    "agent": "Brain",
                    "hacker_mode_activated": True,
                    "success": True,
                    "tasks_executed": 1,
                    "tasks_succeeded": 1,
                    "tasks_failed": 0,
                    "execution_time": 0.0,
                    "task_id": f"hac_{int(time.time())}"
                }
            else:
                return {
                    "response": "Access Denied, Sir. Invalid security clearance keyword. Hacker Brain Mode activate nahi hua.",
                    "intent": "hacker_mode_activation",
                    "agent": "Brain",
                    "hacker_mode_activated": False,
                    "success": False,
                    "tasks_executed": 1,
                    "tasks_succeeded": 0,
                    "tasks_failed": 1,
                    "execution_time": 0.0,
                    "task_id": f"hac_{int(time.time())}"
                }

        # Refined trigger logic to ensure we only activate hacker mode when explicitly requested,
        # avoiding triggers on questions like "do you have hacker mode?".
        activation_keywords = [
            "on hacker mode", "switch to hacker brain", "switch to hacker mode",
            "hacker brain mode on", "activate hacker mode", "enable hacker mode",
            "turn on hacker mode", "hacker mode on", "hacker mode chalu",
            "hacker mode activate", "start hacker mode", "hacker brain mode chalu",
            "chalu karo hacker mode", "enter hacker mode", "go to hacker mode",
            "run hacker mode", "toggle hacker mode"
        ]
        is_activation_request = any(cmd in lower_msg for cmd in activation_keywords) or lower_msg.strip(" .*!#?") in ("hacker mode", "hacker brain mode", "hacker mode chalu", "hacker mode on")

        if is_activation_request and "off" not in lower_msg and "back" not in lower_msg and "normal" not in lower_msg:
            from memory.user_profile import user_profile_store
            profile = user_profile_store.get_profile()
            if profile.get("hacker_mode", False):
                return {
                    "response": "Sir, Hacker Brain Mode already active hai! Main deep security analysis ke liye completely ready hoon.",
                    "intent": "chat",
                    "agent": "Brain",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1,
                    "tasks_failed": 0,
                    "execution_time": 0.0,
                    "success": True,
                    "task_id": f"hac_{int(time.time())}"
                }
            # Voice-friendly: if keyword "sambhav" is spoken in the same command, auto-activate
            if "sambhav" in lower_msg:
                user_profile_store.update_profile(hacker_mode=True)
                return {
                    "response": "Security clearance verified, Sir. Hacker Brain Mode activated. Full security, OSINT, aur Drana capabilities online hain.",
                    "intent": "hacker_mode_activation",
                    "agent": "Brain",
                    "hacker_mode_activated": True,
                    "success": True,
                    "tasks_executed": 1,
                    "tasks_succeeded": 1,
                    "tasks_failed": 0,
                    "execution_time": 0.0,
                    "task_id": f"hac_{int(time.time())}"
                }
            # Show password challenge prompt AND set pending flag for voice 2-step flow
            self._hacker_challenge_pending = True
            return {
                "response": "To activate Hacker Brain Mode, please enter your security clearance keyword.",
                "intent": "hacker_mode_activation",
                "agent": "Brain",
                "hacker_mode_challenge": True,
                "success": True,
                "tasks_executed": 1,
                "tasks_succeeded": 1,
                "tasks_failed": 0,
                "execution_time": 0.0,
                "task_id": f"hac_{int(time.time())}"
            }

        if any(cmd in lower_msg for cmd in ["off hacker mode", "switch to productivity", "switch to productivity mode", "productivity mode", "switch back", "back to normal", "normal mode"]):
            from memory.user_profile import user_profile_store
            profile = user_profile_store.get_profile()
            if not profile.get("hacker_mode", False):
                return {
                    "response": "Sir, aap already Productivity Mode mein hain.",
                    "intent": "chat",
                    "agent": "Brain",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1,
                    "tasks_failed": 0,
                    "execution_time": 0.0,
                    "success": True,
                    "task_id": f"hac_{int(time.time())}"
                }
            user_profile_store.update_profile(hacker_mode=False)
            return {
                "response": "Productivity Mode active ho gaya hai, Sir. Daily tasks, scheduling aur coding help ke liye system online hai.",
                "intent": "hacker_mode_deactivation",
                "agent": "Brain",
                "hacker_mode_deactivated": True,
                "success": True,
                "tasks_executed": 1,
                "tasks_succeeded": 1,
                "tasks_failed": 0,
                "execution_time": 0.0,
                "task_id": f"hac_{int(time.time())}"
            }

        # If hacker mode is active, delegate all message processing directly to HackerBrain
        from memory.user_profile import user_profile_store
        if user_profile_store.get_profile().get("hacker_mode", False):
            try:
                from hacker_brain import hacker_brain
                return await hacker_brain.process(message)
            except Exception as e:
                logger.exception("Failed to run hacker_brain, falling back to normal brain.")

        # Check if the query intent is security/osint/drana in normal mode
        intent = await self._classify_intent(message)
        if intent in ("security", "osint", "drana"):
            return {
                "response": "Sir, yeh security assessment/OSINT/Drana capability restricted hai. Kripya Hacker Brain Mode activate karein.",
                "intent": "chat",
                "agent": "Brain",
                "success": False,
                "tasks_executed": 0,
                "tasks_succeeded": 0,
                "tasks_failed": 0,
                "execution_time": 0.0,
                "task_id": f"restricted_{int(time.time())}"
            }

        # 1. Intercept memory commands
        mem_cmd_res = await parse_memory_command(message)
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
                        task_id = state.get("task_id")
                        from services.job_manager import get_job_manager
                        if get_job_manager().get_job(task_id):
                            asyncio.create_task(self._run_background_job_resume(task_id, state))
                            response_text = f"Sir, I have resumed the background job `{task_id}`."
                            memory_store.add_message("assistant", response_text)
                            return {
                                "response": response_text,
                                "intent": state.get("intent", "chat"),
                                "agent": "Brain",
                                "success": True,
                                "task_id": task_id,
                                "is_background": True
                            }
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

            # ── Direct OSINT Agent routing ─────────────────────────────────────
            # If intent is OSINT, bypass the generic agentic loop and run
            # the specialised multi-stage OSINTAgent pipeline directly.
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
                    "agent": "Brain",
                    "success": True,
                    "task_id": job_id,
                    "is_background": True
                }
            if intent == "osint":
                logger.info("[Brain] Routing OSINT intent directly to OSINTAgent")
                agent = self.agents["osint"]
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
                    "response":       final_response,
                    "intent":         "osint",
                    "agent":          "OSINTAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed":   0 if success else 1,
                    "execution_time": elapsed,
                    "success":        success,
                    "task_id":        task_id,
                    "attempts":       1,
                }

            # ── Direct Investigation Agent routing ──────────────────────────────
            # If intent is investigation, bypass the generic agentic loop and run
            # the InvestigationAgent pipeline directly.
            if intent == "investigation":
                logger.info("[Brain] Routing Investigation intent directly to InvestigationAgent")
                agent = self.agents["investigation"]
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
                        "agent": "InvestigationAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "investigation",
                        "agent": "InvestigationAgent",
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
                    "intent":         "investigation",
                    "agent":          "InvestigationAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed":   0 if success else 1,
                    "execution_time": elapsed,
                    "success":        success,
                    "task_id":        task_id,
                    "attempts":       1,
                }

            # ── Direct Repair Agent routing ─────────────────────────────────────
            # If intent is repair, bypass the generic agentic loop and run
            # the RepairAgent pipeline directly.
            if intent == "repair":
                logger.info("[Brain] Routing Repair intent directly to RepairAgent")
                agent = self.agents["repair"]
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
                        "agent": "RepairAgent",
                        "tasks": 1,
                        "execution_time": elapsed,
                        "attempts": 1,
                    },
                )
                task_id = f"task_{len(memory_store.task_results) + 1}"
                memory_store.store_task(task_id, {
                    "tasks": [{
                        "task_id": "t1",
                        "intent": "repair",
                        "agent": "RepairAgent",
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
                    "intent":         "repair",
                    "agent":          "RepairAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed":   0 if success else 1,
                    "execution_time": elapsed,
                    "success":        success,
                    "task_id":        task_id,
                    "attempts":       1,
                }

            # ── Direct Drana Agent routing ─────────────────────────────────────
            # If intent is drana, bypass the generic agentic loop and run
            # the DranaAgent pipeline directly.
            if intent == "drana":
                logger.info("[Brain] Routing Drana intent directly to DranaAgent")
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
                    "response":       final_response,
                    "intent":         "drana",
                    "agent":          "DranaAgent",
                    "tasks_executed": 1,
                    "tasks_succeeded": 1 if success else 0,
                    "tasks_failed":   0 if success else 1,
                    "execution_time": elapsed,
                    "success":        success,
                    "task_id":        task_id,
                    "attempts":       1,
                }

            return await self.execute_agentic_loop(message)
        except Exception as e:
            logger.exception(f"Agentic loop failed: {e}. Falling back to legacy process.")
            # Remove last user message since legacy_process will add it again
            if memory_store.chat_history and memory_store.chat_history[-1]["content"] == message:
                memory_store.chat_history.pop()
            return await self.legacy_process(message)

    async def process(self, message: str) -> dict:
        """
        Main entry point: receive user message, check memory commands,
        check pending approvals, execute agentic loop, or run legacy flow.
        """
        result = await self._process_internal(message)
        try:
            if isinstance(result, dict) and "response" in result:
                self._schedule_fact_extraction(message, result["response"])
        except Exception as e:
            logger.warning(f"Failed to schedule background fact extraction: {e}")
        return result

    def _schedule_fact_extraction(self, message: str, response: str) -> None:
        """Helper to run async background fact extraction in a non-blocking way."""
        async def run_extraction():
            try:
                combined_text = (message + " " + response).lower()
                heavy_keywords = ["app", "website", "search", "code", "run", "error", "file", "install", "docker", "vulnerability", "scan", "script", "log", "analyze", "diagnose", "osint"]
                if any(kw in combined_text for kw in heavy_keywords):
                    from intelligence.fact_extractor import FactExtractor
                    # Extract user prompt facts
                    user_facts = await FactExtractor.extract_facts_async("user", message)
                    if user_facts:
                        memory_store.add_working_facts(user_facts)
                    # Extract assistant response facts
                    assistant_facts = await FactExtractor.extract_facts_async("assistant", response)
                    if assistant_facts:
                        memory_store.add_working_facts(assistant_facts)
            except Exception as ex:
                logger.warning(f"Error in background fact extraction: {ex}")

        try:
            asyncio.create_task(run_extraction())
        except Exception as err:
            logger.warning(f"Failed to create background task for fact extraction: {err}")

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

    def _is_long_running_task(self, message: str, intent: str) -> bool:
        lower_msg = message.lower()
        if any(phrase in lower_msg for phrase in [
            "background job", "background task", "run in background", 
            "background research", "background scan", "background project",
            "bg run", "in background", "background mein", "background me"
        ]):
            return True
        # Auto-detect long building/creation/scaffolding/scanning objectives
        if any(phrase in lower_msg for phrase in [
            "build an app", "build a website", "build a project", "create an app", 
            "create a website", "create a project", "scaffold a", "scaffold an",
            "make a full", "make a complete", "deep scan", "vulnerability scan", "security audit"
        ]):
            return True
        return intent in ("codepipeline", "research", "code")

    async def _run_background_job(self, job_id: str, message: str, intent: str):
        current_task = asyncio.current_task()
        from services.job_manager import get_job_manager
        job_manager = get_job_manager()
        job_manager._register_task(job_id, current_task)
        
        # Automatically launch default browser to the dashboard URL
        try:
            import webbrowser
            from config import settings
            port = getattr(settings, "API_PORT", 8000)
            url = f"http://localhost:{port}/dashboard/{job_id}"
            webbrowser.open(url)
            logger.info(f"[Background Job] Auto-opened browser dashboard: {url}")
        except Exception as e:
            logger.error(f"Failed to auto-open dashboard browser: {e}")
            
        try:
            job_manager.update_job(job_id, status="running", event="Background job execution started.")
            from services.notification_hub import notify_job_status
            asyncio.create_task(notify_job_status(job_id, "running", "Background job execution started."))
            
            if intent == "osint":
                logger.info(f"[Background Job] Running OSINT pipeline for {job_id}")
                agent = self.agents["osint"]
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
                
            elif intent == "code" or (intent == "tool_execution" and any(w in message.lower() for w in ("build", "create", "scaffold", "develop"))):
                logger.info(f"[Background Job] Running Swarm Delegator for {job_id}")
                from agents.sub_agents.delegator import get_delegator
                delegator = get_delegator()
                loop = asyncio.get_event_loop()
                
                job_manager.update_job(
                    job_id,
                    current_agent="DelegatorAgent",
                    event="Swarm Delegator started for app building mission."
                )
                
                # Run delegator in executor to avoid blocking the async event loop
                delegation_result = await loop.run_in_executor(None, delegator.process, message)
                
                response_text = str(delegation_result.get("result", "Swarm execution completed."))
                agents_used = delegation_result.get("agents_used", [])
                status = "completed" if delegation_result.get("route") == "complex" or delegation_result.get("success", True) else "failed"
                
                job_manager.update_job(
                    job_id,
                    status=status,
                    progress=100,
                    final_result=response_text,
                    event=f"Swarm Delegator completed. Agents used: {', '.join(agents_used)}."
                )
                from services.notification_hub import notify_job_status
                asyncio.create_task(notify_job_status(job_id, status, f"Swarm job completed: {status}.", results=response_text))
                memory_store.add_message("assistant", response_text)
                
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


# ── Global singleton ──────────────────────────────────────────────────────────
brain = Brain()
