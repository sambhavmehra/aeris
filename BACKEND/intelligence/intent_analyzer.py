"""
Aeris AI OS — Intent Analyzer
Implements Step 1-4 of the Intent-First Execution Pipeline.
Analyzes user objective, verifies capability, and selects tools strictly BEFORE execution.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tools.universal_registry import get_universal_registry

logger = logging.getLogger("AerisIntentAnalyzer")

@dataclass
class IntentAnalysisResult:
    is_capable: bool
    task_type: str  # e.g., 'analysis', 'execution', 'info', 'conversation'
    required_resources: List[str]  # e.g., ['camera', 'file_system', 'web']
    expected_output: str
    selected_tools: List[str]
    missing_requirements: str = ""
    permission_required: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_capable": self.is_capable,
            "task_type": self.task_type,
            "required_resources": self.required_resources,
            "expected_output": self.expected_output,
            "selected_tools": self.selected_tools,
            "missing_requirements": self.missing_requirements,
            "permission_required": self.permission_required
        }

class IntentAnalyzer:
    """
    Analyzes intent and rigorously checks system capability against registered tools.
    Prevents hallucinated tools and execution attempts when incapable.
    """
    def __init__(self):
        self._registry = get_universal_registry()

    # ── Fast-path rule table: intent keyword → (tool, task_type) ──────
    _FAST_PATH_RULES: list[tuple[list[str], str, str]] = [
        # (keyword_prefixes,            tool_name,        task_type)
        (["open folder ", "open directory ", "open path ", "navigate to "], "open_folder", "execution"),
        (["open "],                     "open_app",       "execution"),
        (["close ", "exit ", "quit "],  "close_app",      "execution"),
        (["play "],                     "play_youtube",   "execution"),
        (["system monitor", "monitor system", "system health check", "system check", "check status", "system status", "monitor"], "monitor_system", "execution"),
        (["whatsapp share", "share on whatsapp", "send on whatsapp", "whatsapp par file", "whatsapp pe file", "whatsapp file share"], "share_file_whatsapp", "execution"),
        (["record audio", "record my voice", "voice record", "audio record", "mic record"], "record_audio", "execution"),
        (["telegram file", "send file on telegram", "share file on telegram", "telegram par file", "telegram pe file", "send on telegram"], "send_file_telegram", "execution"),
        (["project status", "status of project", "build status", "builder status", "status kya hai", "kya status hai"], "check_project_status", "execution"),
        (["camera se", "camera dekho", "camera dikhao", "camera open",
          "analyze camera", "room dekho", "room dikhao", "mera room",
          "mujhe dikha camera", "camera laga", "webcam", "face dekho",
          "samne dekho", "look at me", "see my room", "see my face",
          "what do you see", "camera se dekh", "cam se dekh"],
                                        "analyze_camera", "analysis"),
        (["photo kheech", "photo le", "photo khicho", "take a photo", "take photo",
          "capture photo", "selfie le", "selfie kheech", "pic le", "picture le"],
                                        "take_camera_photo", "execution"),
        (["screenshot"],                "take_screenshot","execution"),
        (["google search ", "search google "], "google_search", "execution"),
        (["youtube search "],           "youtube_search", "execution"),
        (["system ", "mute", "unmute", "volume up", "volume down",
          "shutdown", "restart", "lock"], "system_control", "system_control"),
        (["analyze screen", "screen dekho", "what is on my screen",
          "what's on my screen"],       "analyze_screen", "analysis"),
        (["take a screenshot", "screenshot le"],  "take_screenshot", "execution"),
        (["find file ", "find my ", "search my "], "find_system_file", "execution"),
        (["find folder ", "search folder "], "find_system_folder", "execution"),
        (["read file ", "open file "],  "read_system_file", "execution"),
        (["convert "],                  "convert_file",   "execution"),
        (["generate website", "create website", "make website"],
                                        "generate_website", "execution"),
        (["build project", "create app", "generate project", "build application", "create project",
          "build app", "create system", "make project", "develop software", "make realtime chat app",
          "antigravity", "antigravity se build", "antigravity se project", "antigravity build"],
                                        "build_project", "execution"),
        (["generate diagram", "create diagram", "draw a diagram", "diagram banao",
          "generate flowchart", "create flowchart", "draw a flowchart", "visual workflow", 
          "flowchart banao", "workflow banao", "diagram generate", "generate a flowchart", "create a flowchart"],
                                        "generate_diagram_widget", "execution"),
        (["generate image", "create image", "make image", "draw a picture", "draw an image"],
                                        "generate_image", "execution"),
        (["generate code", "write code", "code likho", "code banao"],
                                        "generate_code",  "execution"),
        (["kholo", "band karo", "chalao", "bajao"],
                                        "open_app",       "execution"),
    ]

    def analyze_intent(self, objective: str) -> IntentAnalysisResult:
        """
        Runs the LLM over the user objective and available tools to strictly classify intent
        and verify capability before planning or executing anything.
        
        Fast-path: common OS commands (open/close/play/screenshot/system) bypass
        the LLM entirely to avoid false is_capable=False decisions.
        """
        actual_task = objective
        if "Task to perform:" in objective:
            actual_task = objective.split("Task to perform:")[-1].strip()

        obj_lower = actual_task.lower().strip()

        # ── FAST PATH: Rule-based bypass for well-known SIMPLE OS intents ───
        # IMPORTANT: Skip compound/multi-step commands so the LLM can decompose them.
        # e.g. "open whatsapp and search sumit" must NOT fast-path to open_app only.
        _COMPOUND_MARKERS = [" and ", " then ", " also ", " search ", " send ",
                             " type ", " write ", " after ", " find ", " click ",
                             " folder", " directory", " drive", " path",
                             " aur ", " or ", " fir ", " phir ", " ke baad "]
        is_compound = any(marker in obj_lower for marker in _COMPOUND_MARKERS)

        # Guard: skip fast-path for known app names that collide with action keywords
        _APP_NAME_GUARD = ["draw.io", "drawio", "diagrams.net"]
        is_app_name = any(app in obj_lower for app in _APP_NAME_GUARD)

        if not is_compound:
            for prefixes, tool_name, task_type in self._FAST_PATH_RULES:
                # If it's a known app name, skip diagram/image tools
                if is_app_name and tool_name in ("generate_diagram_widget", "generate_image"):
                    continue
                matched = any(
                    obj_lower.startswith(kw) or (kw.strip() in obj_lower and len(obj_lower) < 80)
                    for kw in prefixes
                )
                if matched:
                    logger.info(f"Fast-path match → tool='{tool_name}' for: {actual_task[:60]}")
                    return IntentAnalysisResult(
                        is_capable=True,
                        task_type=task_type,
                        required_resources=[],
                        expected_output=f"Execute {tool_name} for: {actual_task}",
                        selected_tools=[tool_name],
                        missing_requirements="",
                        permission_required=False,
                    )
        else:
            logger.info(f"Compound command detected, skipping fast-path: {actual_task[:60]}")

        # ── SLOW PATH: LLM-based analysis for complex/ambiguous intents ──
        tools = self._registry.get_enabled_tools()
        
        tool_descriptions = []
        for t in tools:
            params = ", ".join([p.name for p in t.input_schema.params]) if t.input_schema.params else "none"
            tool_descriptions.append(f"- {t.name}({params}): {t.description}")
            
        tools_text = "\n".join(tool_descriptions)

        system_prompt = f"""You are the AERIS Intent Analyzer. Your job is to analyze the user's objective BEFORE execution.

AVAILABLE SYSTEM TOOLS:
{tools_text}

HARDWARE/RESOURCES IMPLICATIONS:
- Analyzing screen -> Requires computer_use_task or vision_engine
- Managing files -> Requires system_wide_file_access
- Complex web browsing -> Requires web_research or real_time_search

YOUR TASK:
Output ONLY valid JSON matching this schema:
{{
    "is_capable": boolean, (Can the system actually perform this request given the EXACT available tools?)
    "task_type": string, (e.g. 'execution', 'analysis', 'info_retrieval', 'conversation', 'system_control')
    "required_resources": [string], (e.g. 'camera', 'file_system', 'web', 'shell', 'gui')
    "expected_output": string, (Briefly describe what the final output should look like)
    "selected_tools": [string], (List the EXACT tool names from the available list that are needed. NO HALLUCINATIONS)
    "missing_requirements": string, (If is_capable is false, explain why. E.g., 'No tool exists to drive a car')
    "permission_required": boolean (Set to true if this requires sensitive actions like formatting a drive, camera, etc.)
}}

RULES:
1. NEVER guess or invent a tool name. Use ONLY the exact names from AVAILABLE SYSTEM TOOLS.
2. If the user asks for something outside the scope of available tools (and it can't be done via chat or shell), set "is_capable": false.
3. If it requires graphical app manipulation (WhatsApp, Discord, Spotify UI), use 'computer_use_task'. Do not invent CLIs.
4. If it's a conversation or knowledge question, use 'chat_with_ai' or 'realtime_search'.
5. IMPORTANT: 'open <app>' is ALWAYS handled by 'open_app'. It is capable for any app name.
6. IMPORTANT: If the user wants to open a folder/directory (e.g. 'open project folder', 'open D drive'), use 'open_folder' or 'run_bash' to open explorer.
7. IMPORTANT: If the user wants you to modify yourself, update your code, upgrade, evolve, learn something new, or become something (e.g. 'hacker ban ja', 'khud ko update kar'): you are CAPABLE. Use 'read_file' to read your own source code (from the backend/ directory), then 'edit_file' or 'write_file' to modify it. NEVER open VS Code or any editor app — you modify code DIRECTLY using file tools. Your source code lives in the backend/ directory.
8. IMPORTANT: If the user wants to generate visual workflows, flowcharts, or diagrams, you are CAPABLE. Use 'generate_diagram_widget' with a descriptive prompt — the AI will auto-detect the best diagram type, generate Mermaid code, and render it as an animated widget in the UI.
9. IMPORTANT: If the user wants to merge/integrate another project or learn from external code, you are CAPABLE. Use 'find_system_file' or 'list_dir' to locate the project, 'read_file' to read its code, then 'edit_file'/'write_file' to merge relevant parts into your own codebase.
10. IMPORTANT: MULTI-AGENT SWARM AWARENESS. You are CAPABLE of handling extremely complex tasks because you possess an autonomous Multi-Agent Swarm. If the user asks for "deep research", "full-stack code generation", "vulnerability scanning", "data analysis", "creating new tools", or "dynamic execution", you MUST set "is_capable": true. The system will automatically route these to specialized agents (CodingAgent, ResearchAgent, etc.).
11. IMPORTANT: If the user asks to "build a project", "create an app", "generate a full system", or "scaffold an application", you MUST select the 'build_project' tool, which uses the Project Builder System (PBS) to orchestrate a multi-agent swarm for generating and saving complete projects to /Aeris_Projects/.
"""
        user_prompt = f"Objective: {actual_task}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            from ai_engine import ai_engine
            import asyncio
            
            def run_sync(coro):
                try:
                    return asyncio.run(coro)
                except RuntimeError:
                    import nest_asyncio
                    nest_asyncio.apply()
                    return asyncio.run(coro)

            raw_response = run_sync(ai_engine.chat(
                messages,
                temperature=0.1,
                max_tokens=512,
                response_format={"type": "json_object"}
            ))
            
            # Clean JSON
            cleaned = raw_response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)
            
            # Validate selected tools exist
            valid_tools = [t for t in data.get("selected_tools", []) if self._registry.get_tool(t)]
            
            is_capable = data.get("is_capable", False)
            if not valid_tools and data.get("task_type") != "conversation":
                # If no valid tools but required, mark incapable
                # UNLESS it's just a conversation where maybe chat_with_ai was missed
                if "chat_with_ai" not in data.get("selected_tools", []):
                    is_capable = False
                    
            if not is_capable and not data.get("missing_requirements"):
                missing = "System lacks the specific tools to perform this task directly."
            else:
                missing = data.get("missing_requirements", "")

            return IntentAnalysisResult(
                is_capable=is_capable,
                task_type=data.get("task_type", "unknown"),
                required_resources=data.get("required_resources", []),
                expected_output=data.get("expected_output", ""),
                selected_tools=valid_tools,
                missing_requirements=missing,
                permission_required=data.get("permission_required", False)
            )

        except Exception as e:
            logger.error(f"Intent analysis failed: {e}")
            # Safe fallback
            return IntentAnalysisResult(
                is_capable=True,  # Default to capable to let planner try
                task_type="execution",
                required_resources=[],
                expected_output="Unknown",
                selected_tools=[],
                missing_requirements="",
                permission_required=False
            )

_analyzer_instance = None

def get_intent_analyzer() -> IntentAnalyzer:
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = IntentAnalyzer()
    return _analyzer_instance
