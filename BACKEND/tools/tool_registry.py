"""
AERIS — Comprehensive Tool Registry
Registers ALL available tools from every subsystem:
  - File operations (read, write, edit, delete, glob, grep)
  - Bash execution
  - System automation (open/close apps, volume, screenshot, etc.)
  - Web search & research
  - RAG knowledge search
  - Vision (screen analysis, OCR, camera)
  - Website generation
  - Content writing

Each tool has: name, description, callable, required_params, risk_level.
"""
from __future__ import annotations

import logging
import os
import sys
import inspect
from typing import Callable, Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger("AerisToolRegistry")

# Ensure backend is on path
_backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)


class RiskLevel(str, Enum):
    SAFE = "safe"           # Read-only, no side effects
    LOW = "low"             # Minor side effects (open browser tab)
    MEDIUM = "medium"       # Modifies files, runs commands
    HIGH = "high"           # Destructive (delete, shutdown, reboot)
    CRITICAL = "critical"   # System-level danger (rm -rf, format)


class ToolDefinition:
    """Full metadata + callable for a registered tool."""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        required_params: List[str],
        risk_level: RiskLevel = RiskLevel.SAFE,
        category: str = "general",
        timeout: int = 30,
        approval_requirement: bool = False,
        optional_params: List[str] = None,
    ):
        self.name = name
        self.description = description
        self.func = func
        self.required_params = required_params
        self.risk_level = risk_level
        self.category = category
        self.timeout = timeout
        self.approval_requirement = approval_requirement
        self.optional_params = optional_params or []

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "required_params": self.required_params,
            "risk_level": self.risk_level.value,
            "category": self.category,
            "timeout": self.timeout,
            "approval_requirement": self.approval_requirement,
        }

    def to_json_schema(self) -> Dict[str, Any]:
        properties = {p: {"type": "string", "description": ""} for p in self.required_params}
        return {
            "name": self.name,
            "description": self.description,
            "args": {
                "type": "object",
                "properties": properties,
                "required": self.required_params,
            },
            "risk_level": self.risk_level.value,
            "timeout": self.timeout,
            "approval_requirement": self.approval_requirement,
        }


class ToolRegistry:
    """Centralized registry for all available tools in AERIS."""

    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}

    def __len__(self) -> int:
        return len(self._tools)

    def register(
        self,
        name: str,
        description: str,
        func: Callable,
        required_params: List[str] = None,
        risk_level: RiskLevel = RiskLevel.SAFE,
        category: str = "general",
        timeout: int = 30,
        approval_requirement: bool = False,
        optional_params: List[str] = None,
    ):
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            func=func,
            required_params=required_params or [],
            risk_level=risk_level,
            category=category,
            timeout=timeout,
            approval_requirement=approval_requirement,
            optional_params=optional_params or [],
        )

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    # Compatibility alias: some parts of the codebase expect ToolRegistry.get(...)
    def get(self, name: str) -> Optional[ToolDefinition]:
        return self.get_tool(name)

    def get_all_metadata(self) -> List[Dict[str, Any]]:
        """Return metadata for all tools (used by LLM planner)."""
        return [t.to_metadata() for t in self._tools.values()]

    def get_tools_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [t.to_metadata() for t in self._tools.values() if t.category == category]

    def get_tools_description(self, category: str | None = None) -> str:
        """Return a compact tool list for prompts, optionally filtered by category."""
        tools = self._tools.values()
        if category:
            tools = [t for t in tools if t.category == category]
        lines = []
        for t in tools:
            params = ", ".join(t.required_params) if t.required_params else "none"
            lines.append(f"- {t.name}({params}): {t.description} [risk: {t.risk_level.value}]")
        return "\n".join(lines)

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    def list_all(self) -> List[ToolDefinition]:
        """Return all registered tool definitions."""
        return list(self._tools.values())

    def get_risk_level(self, name: str) -> RiskLevel:
        tool = self._tools.get(name)
        return tool.risk_level if tool else RiskLevel.MEDIUM

    def execute(self, name: str, **kwargs) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found in registry. Available: {list(self._tools.keys())}")

        # Validate required params
        for param in tool.required_params:
            if param not in kwargs:
                raise ValueError(f"Missing required parameter '{param}' for tool '{name}'")

        action_str = "Executing tool..."
        if "search" in name: action_str = "Searching..."
        elif "analyze" in name: action_str = "Analyzing data..."
        elif "read" in name: action_str = "Reading file..."
        elif "close" in name: action_str = "Closing apps..."
        elif "smart_shell" in name: action_str = "Generating shell command..."
        elif "describe_shell" in name: action_str = "Explaining command..."
        elif "generate_code" in name: action_str = "Generating code..."
        elif "cache" in name: action_str = "Clearing cache..."
        elif "generate" in name:
            if "image" in name: action_str = "Generating image..."
            elif "video" in name: action_str = "Generating video..."
            else: action_str = "Writing code..."
        elif "write" in name or "edit" in name: action_str = "Writing code..."
        
        try:
            from engine.state_manager import global_state_manager
            global_state_manager.set_global_action(action_str)
            
            current_task = global_state_manager.get_current_task()
            if current_task:
                global_state_manager.update_task(
                    current_task.task_id, 
                    current_task.status, 
                    action=action_str, 
                )
        except Exception:
            pass

        try:
            result = tool.func(**kwargs)
            return result
        finally:
            try:
                from engine.state_manager import global_state_manager
                global_state_manager.set_global_action("Idle")
            except Exception:
                pass

    async def execute_async(self, name: str, **kwargs) -> Any:
        """Async-compatible execution wrapper for tools that call async services."""
        result = self.execute(name, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    def format_for_llm(self) -> str:
        """Format all tools as a compact text description for the LLM system prompt."""
        lines = []
        for t in self._tools.values():
            params_str = ", ".join(t.required_params) if t.required_params else "none"
            lines.append(f"- {t.name}({params_str}): {t.description} [risk: {t.risk_level.value}]")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
#  Global Registry + Tool Registration
# ═══════════════════════════════════════════════════════════════════

global_tool_registry = ToolRegistry()


def _register_all_tools():
    """Register every available tool from every AERIS subsystem."""
    reg = global_tool_registry

    # ── 2. File Operations ──────────────────────────────────────────
    try:
        from services.file_tools import FileToolSystem
        _ft = FileToolSystem()

        def read_file(path: str) -> str:
            r = _ft.read_file(path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def write_file(path: str, content: str) -> str:
            r = _ft.write_file(path, content)
            if not r.success:
                raise RuntimeError(r.output)
            try:
                from utils.file_tracker import record_file_creation
                record_file_creation(path, "Written content via write_file tool")
            except Exception:
                pass
            return r.output

        def edit_file(path: str, old_text: str, new_text: str) -> str:
            r = _ft.edit_file(path, old_text, new_text)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def delete_file(path: str) -> str:
            r = _ft.delete_file(path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def list_dir(path: str = ".") -> str:
            r = _ft.glob_search(path + "/*" if not path.endswith("*") else path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def grep_search(query: str, path: str = ".") -> str:
            r = _ft.grep_search(query, path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def run_bash(command: str, **kwargs) -> str:
            r = _ft.bash(command)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        reg.register("read_file", "Read contents of a file.", read_file, ["path"], RiskLevel.SAFE, "file")
        reg.register("write_file", "Write FULL generated content to a file. DO NOT just write a single keyword. If asked for a poem, shayari, code, or essay, you MUST generate the complete actual text in the 'content' parameter.", write_file, ["path", "content"], RiskLevel.MEDIUM, "file")
        reg.register("edit_file", "Replace specific text in a file.", edit_file, ["path", "old_text", "new_text"], RiskLevel.MEDIUM, "file")
        reg.register("delete_file", "Delete a file or directory.", delete_file, ["path"], RiskLevel.HIGH, "file", approval_requirement=True)
        reg.register("list_dir", "List directory contents.", list_dir, ["path"], RiskLevel.SAFE, "file")
        reg.register("grep_search", "Search for text patterns in files.", grep_search, ["query", "path"], RiskLevel.SAFE, "file")
        reg.register("run_bash", "Execute a terminal/shell command.", run_bash, ["command"], RiskLevel.HIGH, "system", approval_requirement=True)
        logger.info("Registered file & bash tools")
    except Exception as e:
        logger.warning(f"Failed to register file tools: {e}")

    # ── 3. System Automation ─────────────────────────────────────────
    try:
        from automation.system_automation import (
            open_folder, open_app, close_app, close_all_apps, play_youtube,
            play_music_background, play_on_youtube_visible,
            google_search, youtube_search, system_control, take_screenshot, write_content,
            open_file, monitor_system, share_file_whatsapp, read_whatsapp_messages, record_audio, send_file_telegram,
        )

        reg.register("open_folder", "Open a folder or directory in the file explorer.", open_folder, ["path"], RiskLevel.LOW, "automation")
        reg.register("open_app", "Open an application or website.", open_app, ["app_name"], RiskLevel.LOW, "automation")
        reg.register("close_app", "Close a running application.", close_app, ["app_name"], RiskLevel.LOW, "automation")
        reg.register("close_all_apps", "Close all background applications keeping system critical layers alive. Pass exceptions as comma-separated string if any.", close_all_apps, ["exceptions"], RiskLevel.MEDIUM, "automation")
        reg.register("play_youtube", "Play music/song/audio visibly in your default browser on YouTube.", play_youtube, ["query"], RiskLevel.LOW, "automation")
        reg.register("play_on_youtube_visible", "Open YouTube visibly in the browser and play a song/video. ONLY use this when the user EXPLICITLY says 'on YouTube' / 'YouTube pe' / 'YouTube par' / 'YouTube open karke'. Otherwise use play_youtube.", play_on_youtube_visible, ["query"], RiskLevel.LOW, "automation")
        reg.register("google_search", "Open a Google search in the browser.", google_search, ["query"], RiskLevel.SAFE, "automation")
        reg.register("youtube_search", "Search YouTube in the browser.", youtube_search, ["query"], RiskLevel.SAFE, "automation")
        reg.register("system_control", "System controls: mute, volume, shutdown, restart, lock.", system_control, ["action"], RiskLevel.HIGH, "system", approval_requirement=True)
        reg.register("take_screenshot", "Capture a screenshot of the screen and SAVE it to disk. Use this ONLY when user explicitly says 'take screenshot' or 'screenshot le lo'. Do NOT use this for screen analysis.", take_screenshot, [], RiskLevel.SAFE, "system")
        reg.register("write_content", "Generate AI-written content and save to file.", write_content, ["topic"], RiskLevel.LOW, "content")
        reg.register(
            "open_file",
            "Open an existing file on disk using its default app or a specified app. "
            "Use 'app' parameter to force a specific program (e.g. 'notepad', 'code', 'excel', 'vlc'). "
            "Use this AFTER write_file to open the file for the user. "
            "Example: open_file(path='C:/shayari.txt', app='notepad').",
            open_file,
            ["path"],
            RiskLevel.LOW,
            "automation",
        )
        reg.register("monitor_system", "Monitor system health metrics: CPU, RAM, Disk, battery, and top active processes.", monitor_system, [], RiskLevel.SAFE, "system")
        reg.register("share_file_whatsapp", "Share any file via WhatsApp Web to a contact by name.", share_file_whatsapp, ["contact_name", "file_path"], RiskLevel.MEDIUM, "automation")
        reg.register("read_whatsapp_messages", "Read the latest messages from a WhatsApp contact or the active chat.", read_whatsapp_messages, [], RiskLevel.LOW, "automation", optional_params=["contact_name"])
        reg.register("record_audio", "Record audio from your microphone for a given duration (in seconds) and save it to disk.", record_audio, ["duration"], RiskLevel.MEDIUM, "system")
        reg.register("send_file_telegram", "Send any captured file (photo, document, or audio recording) to your Telegram chat.", send_file_telegram, ["file_path"], RiskLevel.MEDIUM, "system", optional_params=["caption"])
        
        # Excel Tools
        try:
            from tools.excel_tools import export_to_excel, update_excel_from_screen
            reg.register(
                "export_to_excel",
                "Create a premium styled Excel spreadsheet from a list of rows (data) and save it to file_path. Inputs: file_path (string), data (list of dictionaries), columns (optional list of column header strings).",
                export_to_excel,
                ["file_path", "data"],
                RiskLevel.MEDIUM,
                "automation",
                optional_params=["columns"]
            )
            reg.register(
                "update_excel_from_screen",
                "Updates or appends details for a person/entity to a styled Excel sheet. It intelligently maps the role of the target to the sheet name (e.g. 'hr.xlsx') if no sheet name is specified. It captures the screen to scrape details if they are visible. If the data source is specified by the user as web search or internet search, set the source parameter to 'web'. Inputs: excel_path_or_keyword (optional string path or keyword like 'hr'), target_name (optional string name of the target like 'Sandeep'), manual_details (optional dict/string details), source (optional string: 'web' or 'screen').",
                update_excel_from_screen,
                [],
                RiskLevel.MEDIUM,
                "automation",
                optional_params=["excel_path_or_keyword", "target_name", "manual_details", "source"]
            )
            logger.info("Registered Excel tools in global registry")
        except Exception as ex_err:
            logger.warning(f"Failed to register Excel tools: {ex_err}")
            
        # Word Tools
        try:
            from tools.word_tools import extract_transcript_to_word
            reg.register(
                "extract_transcript_to_word",
                "Extracts a transcript/content from a link (YouTube video or article URL) or accepts direct text, generates styled professional meeting/topic notes using AI, saves them as a Word document (.docx) to disk, and automatically opens it. Inputs: url (optional string), text (optional string), output_path (optional string), notes_style (optional string: 'detailed', 'summary', 'key_takeaways').",
                extract_transcript_to_word,
                [],
                RiskLevel.MEDIUM,
                "automation",
                optional_params=["url", "text", "output_path", "notes_style"]
            )
            logger.info("Registered Word tools in global registry")
        except Exception as w_err:
            logger.warning(f"Failed to register Word tools: {w_err}")
            
        logger.info("Registered automation tools")
    except Exception as e:
        logger.warning(f"Failed to register automation tools: {e}")

    # ── 4. Research ──────────────────────────────────────────────────
    try:
        from agents.research_agent import ResearchAgent
        _researcher = ResearchAgent()

        async def web_research(query: str, depth: str = "basic") -> str:
            return await _researcher.research(query, depth)

        def scrape_website(url: str) -> str:
            result = _researcher.scrape_website(url)
            if result.get("success"):
                return result["content"]
            raise RuntimeError(result.get("error", "Scrape failed"))

        reg.register("web_research", "Research a topic using web search + AI synthesis.", web_research, ["query"], RiskLevel.SAFE, "research", timeout=90)
        reg.register("scrape_website", "Scrape text content from a URL.", scrape_website, ["url"], RiskLevel.LOW, "research")
        logger.info("Registered research tools")
    except Exception as e:
        logger.warning(f"Failed to register research tools: {e}")

    # ── 5. RAG Knowledge ─────────────────────────────────────────────
    try:
        from services.rag_engine import RAGVoiceEngine
        _rag = RAGVoiceEngine()

        def rag_search(query: str) -> str:
            _rag.ensure_indexed()
            results = _rag.search_knowledge(query, top_k=5)
            if not results:
                return "No matching documents found in the local knowledge base."
            lines = []
            for r in results:
                lines.append(f"[{r['source']}] (score: {r['score']})\n{r['content'][:200]}")
            return "\n\n".join(lines)

        def rag_index(directory: str = ".") -> str:
            result = _rag.indexer.index_directory(directory)
            return f"Indexed {result['indexed_files']} files ({result['total_chunks']} chunks) from {result['directory']}"

        reg.register("rag_search", "Semantic search across indexed workspace files.", rag_search, ["query"], RiskLevel.SAFE, "knowledge")
        reg.register("rag_index", "Index a directory for RAG retrieval.", rag_index, ["directory"], RiskLevel.LOW, "knowledge", timeout=90)
        logger.info("Registered RAG tools")
    except Exception as e:
        logger.warning(f"Failed to register RAG tools: {e}")

    # ── 6. Vision ────────────────────────────────────────────────────
    try:
        from services.vision_engine import VisionEngine
        _vision = VisionEngine()

        def analyze_screen(prompt: str = "Analyze this screen in extreme detail. Identify the application or website currently open, read all visible text, code, titles, and menus. Describe the layout, any active notifications or popups, and the general context of what the user is currently working on or viewing. Provide a comprehensive structured report.") -> str:
            return _vision.analyze_screen(prompt)

        def analyze_camera(prompt: str = "Describe what you see from the camera.") -> str:
            return _vision.analyze_camera(prompt)

        def ocr_screen() -> str:
            return _vision.ocr_screen()

        def detect_faces() -> str:
            result = _vision.detect_faces()
            if result["success"]:
                return f"Detected {result['faces_detected']} face(s)."
            return result.get("error", "Face detection failed.")

        def take_camera_photo() -> str:
            result = _vision.take_camera_photo()
            if not result.get("success"):
                raise RuntimeError(result.get("error", "Camera photo failed"))
            import json
            return json.dumps(result, indent=2)

        reg.register("analyze_screen", "AI analysis of the current screen content.", analyze_screen, [], RiskLevel.SAFE, "vision", timeout=60)
        reg.register("analyze_camera", "AI analysis of camera feed. Use this to SEE/LOOK through the camera and describe what's visible (e.g. 'room dekho', 'camera se dekho').", analyze_camera, [], RiskLevel.SAFE, "vision", timeout=60)
        reg.register("ocr_screen", "Extract text from the screen using OCR.", ocr_screen, [], RiskLevel.SAFE, "vision", timeout=60)
        reg.register("detect_faces", "Detect faces from camera for biometric recognition.", detect_faces, [], RiskLevel.SAFE, "vision", timeout=60)
        reg.register("take_camera_photo", "Take a photo using the webcam/camera and SAVE it as an image file. Use this when user says 'photo kheech', 'photo le', 'take a photo', 'capture photo'. Returns the saved file path. Do NOT use take_screenshot for camera photos.", take_camera_photo, [], RiskLevel.SAFE, "vision", timeout=60)
        logger.info("Registered vision tools")
    except Exception as e:
        logger.warning(f"Failed to register vision tools: {e}")

    # ── 7. Website Generation ────────────────────────────────────────
    try:
        from generation.website_generator import WebsiteGenerator
        _webgen = WebsiteGenerator()

        def generate_website(prompt: str) -> str:
            result = _webgen.generate(prompt, "auto")
            import json
            payload = result.to_dict()
            payload["preview_file"] = os.path.join(result.output_dir, "index.html")
            payload["file_paths"] = [
                os.path.join(result.output_dir, f["path"])
                for f in result.files
                if f.get("content") != "[binary image]"
            ]
            return json.dumps(payload, indent=2)

        reg.register(
            "generate_website",
            "Generate a website, web app, or full-stack project from a text prompt. "
            "Supports 3 modes: (1) Framework projects (React, Next.js, Vue, Svelte, Angular, Express, Flask, Django) — "
            "generates complete multi-file projects with package.json via CodingAgent. "
            "(2) Functional apps (todo, calculator, chat, etc.) — generates working vanilla HTML/CSS/JS. "
            "(3) Showcase/informational sites — uses fast template engine. "
            "Returns JSON with output_dir, preview_file, and generated file paths.",
            generate_website,
            ["prompt"],
            RiskLevel.MEDIUM,
            "generation",
            timeout=120,
        )
        
        try:
            from generation.diagram_generator import DiagramGenerator
            _diag_gen = DiagramGenerator()
            
            def generate_diagram_widget(prompt: str) -> str:
                result = _diag_gen.generate_from_prompt(prompt)
                import json
                return json.dumps(result, indent=2)
                
            reg.register(
                "generate_diagram_widget",
                "Generate a visual workflow, flowchart, sequence diagram, or any diagram from a natural language description. The AI auto-detects the best diagram type, generates proper Mermaid code with styling, and renders it as an animated widget in the AERIS UI. Just describe what you want to visualize.",
                generate_diagram_widget,
                ["prompt"],
                RiskLevel.SAFE,
                "generation"
            )
            logger.info("Registered intelligent diagram widget generator")
        except Exception as e:
            logger.warning(f"Failed to register diagram generator: {e}")
            
        logger.info("Registered website generation tool")
    except Exception as e:
        logger.warning(f"Failed to register website tools: {e}")

    # ── 8. Chat & Realtime Search (AI conversation tools) ──────────
    try:
        import services.chat_engine as _chat_engine

        def chat_with_ai(message: str) -> str:
            """Send a message to the AI and get a proper conversational response."""
            if not message or not message.strip():
                return "No message provided. Please specify what you'd like to know."
            return _chat_engine.chat(message)

        def realtime_search(query: str) -> str:
            """Search for real-time information (news, weather, prices, etc.)."""
            if not query or not query.strip():
                return "No search query provided."
            return _chat_engine.realtime_search(query)

        def control_ai_voice(action: str) -> str:
            """Mute or unmute the AI's proactive voice features."""
            from agents.proactive_agent import agent as proactive_system
            if getattr(proactive_system, "_user_context", None) is not None:
                if action.lower() == "mute":
                    proactive_system._user_context["is_muted"] = True
                    return "Sir, main shant ho gaya hoon. Ab se main tab tak nahi bolunga jab tak aap nahi kahoge."
                elif action.lower() == "unmute":
                    proactive_system._user_context["is_muted"] = False
                    return "Sir, main wapas active ho gaya hoon."
            return f"Action {action} applied to AI voice system."

        reg.register(
            "chat_with_ai",
            "Send a conversational message to the AI assistant and get an intelligent response. Use for general questions, explanations, greetings, and any query that can be answered by an AI.",
            chat_with_ai,
            ["message"],
            RiskLevel.SAFE,
            "conversation",
        )
        reg.register(
            "realtime_search",
            "Search for real-time, up-to-date information like news, weather, prices, or current events.",
            realtime_search,
            ["query"],
            RiskLevel.SAFE,
            "search",
        )
        async def schedule_execution(instruction: str, time_spec: str) -> dict:
            """Schedule any instruction/task or reminder to be automatically executed at a later time."""
            from services.scheduler import get_scheduler
            new_task = await get_scheduler().schedule(instruction, time_spec)
            return {
                "success": True,
                "task_id": new_task["task_id"],
                "scheduled_time": new_task["scheduled_time"],
                "response": f"⏰ Scheduled task successfully: **'{instruction}'** at {new_task['scheduled_time']}."
            }

        def list_scheduled_tasks(status: str = None) -> list[dict]:
            """Retrieve the list of background scheduled tasks, optionally filtered by status (pending, completed, failed, cancelled)."""
            from services.scheduler import get_scheduler
            return get_scheduler().list_tasks(status)

        def cancel_scheduled_task(task_spec: str) -> dict:
            """Cancel a pending scheduled task by matching its ID or a substring of its instruction (e.g. 'study', 'meeting')."""
            from services.scheduler import get_scheduler
            success = get_scheduler().cancel_task(task_spec)
            if success:
                return {"success": True, "message": f"Successfully cancelled task matching '{task_spec}'."}
            return {"success": False, "message": f"Could not find any pending task matching '{task_spec}'."}

        reg.register(
            "control_ai_voice",
            "Mute or unmute the AI's proactive conversational voice. Use this ONLY when the user explicitly asks you to 'shut up', 'be quiet', 'stop speaking', or 'resume speaking'. Provide 'mute' or 'unmute' as the action parameter.",
            control_ai_voice,
            ["action"],
            RiskLevel.SAFE,
            "conversation",
        )
        reg.register(
            "schedule_execution",
            "Schedule any natural language task/command or reminder to be automatically executed in the background at a later time (e.g. 'open chrome at 3pm', 'check google.com ssl certificate in 1 hour', 'remind me to call Rahul in 20 minutes').",
            schedule_execution,
            ["instruction", "time_spec"],
            RiskLevel.MEDIUM,
            "automation",
            timeout=90,
        )
        reg.register(
            "list_scheduled_tasks",
            "Retrieve the list of background scheduled tasks, optionally filtered by status (pending, completed, failed, cancelled).",
            list_scheduled_tasks,
            [],
            RiskLevel.SAFE,
            "automation",
            optional_params=["status"],
        )
        reg.register(
            "cancel_scheduled_task",
            "Cancel a pending scheduled task by matching its ID or a substring of its instruction (e.g. 'study', 'meeting').",
            cancel_scheduled_task,
            ["task_spec"],
            RiskLevel.MEDIUM,
            "automation",
        )
        logger.info("Registered chat, realtime search, and scheduler tools")
    except Exception as e:
        logger.warning(f"Failed to register chat tools: {e}")

    # ── 9. System-wide File Access ───────────────────────────────────
    try:
        from services.file_tools import FileToolSystem
        _sft = FileToolSystem()

        def read_system_file(path: str) -> str:
            r = _sft.read_system_file(path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def list_system_dir(path: str) -> str:
            r = _sft.list_system_dir(path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def get_file_info(path: str) -> str:
            r = _sft.get_file_info(path)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def find_system_file(filename: str, search_dir: str = "~") -> str:
            r = _sft.find_system_file(filename, search_dir)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        def find_system_folder(foldername: str, search_dir: str = "~") -> str:
            r = _sft.find_system_folder(foldername, search_dir)
            if not r.success:
                raise RuntimeError(r.output)
            return r.output

        reg.register(
            "read_system_file",
            "Read any file on the system by its absolute path. Use ~ for the user's home directory. NEVER output placeholders like 'Replace $HOME...'.",
            read_system_file,
            ["path"],
            RiskLevel.SAFE,
            "file",
        )
        reg.register(
            "list_system_dir",
            "List contents of any directory on the system. Use ~ for the user's home directory. NEVER output placeholders like 'Replace $HOME...'. Shows files with sizes and subdirectories with item counts.",
            list_system_dir,
            ["path"],
            RiskLevel.SAFE,
            "file",
        )
        reg.register(
            "get_file_info",
            "Get detailed metadata about any file or directory: size, created/modified dates, type, etc. Use ~ for the user's home directory. NEVER output placeholders like 'Replace $HOME...'.",
            get_file_info,
            ["path"],
            RiskLevel.SAFE,
            "file",
        )
        reg.register(
            "find_system_file",
            "Search the entire host system for a file by name. Provide the EXACT filename to search for. STRIP OUT any conversational words like 'my', 'meri', 'file', 'dhund', etc. For example, if user says 'meri sambhavv.pdf ki file dhund na', filename should ONLY be 'sambhavv.pdf'.",
            find_system_file,
            ["filename"],
            RiskLevel.SAFE,
            "file",
        )
        reg.register(
            "find_system_folder",
            "Search the entire host system for a directory/folder by name. Provide the EXACT folder/directory name to search for. STRIP OUT conversational words. For example, if user says 'sambhav_project ka folder dhund', foldername should ONLY be 'sambhav_project'.",
            find_system_folder,
            ["foldername"],
            RiskLevel.SAFE,
            "file",
        )
        logger.info("Registered system-wide file access tools")
    except Exception as e:
        logger.warning(f"Failed to register system file tools: {e}")

    # ── 10. File Conversion ──────────────────────────────────────────
    try:
        from services.file_converter import FileConverter
        _converter = FileConverter()

        def convert_file(input_path: str, target_format: str, output_path: str = "") -> str:
            result = _converter.convert(input_path, target_format, output_path)
            if not result.get("success"):
                raise RuntimeError(result.get("error", "Conversion failed"))
            import json
            return json.dumps(result, indent=2)

        def list_conversions() -> str:
            return "Supported conversions:\n" + "\n".join(f"  • {c}" for c in _converter.get_supported_conversions())

        reg.register(
            "convert_file",
            "Convert a file from one format to another. Supports: doc/docx→pdf, pdf→docx/txt/json, csv↔json, xlsx→csv/json, md→html, html→pdf, image format conversions. Provide input_path, target_format, and optionally output_path. Use ~ for home directory.",
            convert_file,
            ["input_path", "target_format"],
            RiskLevel.MEDIUM,
            "file",
        )
        reg.register(
            "list_conversions",
            "List all supported file format conversions.",
            list_conversions,
            [],
            RiskLevel.SAFE,
            "file",
        )
        logger.info("Registered file conversion tools")
    except Exception as e:
        logger.warning(f"Failed to register file conversion tools: {e}")

    # ── 10.5 PDF Reports ─────────────────────────────────────────────
    try:
        from services.file_converter import FileConverter
        _report_converter = FileConverter()

        def generate_pdf_report(title: str, markdown_content: str) -> str:
            """
            Generate a styled PDF report from markdown_content.
            Returns the exact saved PDF file path.
            """
            from pathlib import Path
            import re
            import uuid

            # Save reports under BACKEND/data/reports
            backend_root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            reports_dir = backend_root / "data" / "reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", (title or "report").strip())[:80]
            run_id = uuid.uuid4().hex[:10]

            md_path = reports_dir / f"{safe_title}_{run_id}.md"
            html_path = reports_dir / f"{safe_title}_{run_id}.html"
            pdf_path = reports_dir / f"{safe_title}_{run_id}.pdf"

            md_path.write_text(markdown_content or "", encoding="utf-8")

            md_to_html = _report_converter.convert(str(md_path), "html", str(html_path))
            if not md_to_html.get("success"):
                raise RuntimeError(md_to_html.get("error", "md→html conversion failed"))

            html_to_pdf = _report_converter.convert(str(html_path), "pdf", str(pdf_path))
            if not html_to_pdf.get("success"):
                raise RuntimeError(html_to_pdf.get("error", "html→pdf conversion failed"))

            return str(pdf_path)

        reg.register(
            "generate_pdf_report",
            "Generate a downloadable PDF report ONLY when the user explicitly asks for a PDF report. Inputs: title, markdown_content. The markdown_content should contain the full report body. Returns the exact saved PDF file path.",
            generate_pdf_report,
            ["title", "markdown_content"],
            RiskLevel.MEDIUM,
            "file",
        )
        logger.info("Registered generate_pdf_report tool")
    except Exception as e:
        logger.warning(f"Failed to register generate_pdf_report tool: {e}")

    # ── 11. Image Generation ─────────────────────────────────────────
    try:
        from generation.image_generator import ImageGenerator
        _img_gen = ImageGenerator()

        def generate_image(prompt: str, filename: str = "") -> str:
            result = _img_gen.generate(prompt, filename)
            if not result.get("success"):
                raise RuntimeError(result.get("error", "Image generation failed"))
            import json
            return json.dumps(result, indent=2) + "\n\n(IMPORTANT NOTE FOR ASSISTANT: Always explicitly tell the user the file path where the image was saved.)"

        def list_generated_images() -> str:
            images = _img_gen.list_generated()
            if not images:
                return "No generated images found."
            lines = [f"Generated images ({len(images)} total):"]
            for img in images[:20]:
                lines.append(f"  • {img['filename']} ({img['size_bytes']} bytes) - {img['created_at']}")
            return "\n".join(lines)

        reg.register(
            "generate_image",
            "Generate an AI image from a text prompt using Stable Diffusion. Provide a descriptive prompt of what you want the image to look like.",
            generate_image,
            ["prompt"],
            RiskLevel.LOW,
            "generation",
        )
        reg.register(
            "list_generated_images",
            "List all previously generated AI images with their paths and metadata.",
            list_generated_images,
            [],
            RiskLevel.SAFE,
            "generation",
        )
        logger.info("Registered image generation tools")
    except Exception as e:
        logger.warning(f"Failed to register image generation tools: {e}")

    # ── 12. Video Generation ─────────────────────────────────────────
    try:
        from generation.video_generator import VideoGenerator
        _vid_gen = VideoGenerator()

        def generate_video(prompt: str, filename: str = "") -> str:
            result = _vid_gen.generate(prompt, filename)
            if not result.get("success"):
                raise RuntimeError(result.get("error", "Video generation failed"))
            import json
            return json.dumps(result, indent=2) + "\n\n(IMPORTANT NOTE FOR ASSISTANT: Always explicitly tell the user the file path where the video was saved.)"

        def list_generated_videos() -> str:
            videos = _vid_gen.list_generated()
            if not videos:
                return "No generated videos found."
            lines = [f"Generated videos ({len(videos)} total):"]
            for vid in videos[:20]:
                lines.append(f"  • {vid['filename']} ({vid['size_bytes']} bytes) - {vid['created_at']}")
            return "\n".join(lines)

        reg.register(
            "generate_video",
            "Generate an AI video/animation from a text prompt. Provide a descriptive prompt of what you want the video to look like.",
            generate_video,
            ["prompt"],
            RiskLevel.LOW,
            "generation",
        )
        reg.register(
            "list_generated_videos",
            "List all previously generated AI videos with their metadata.",
            list_generated_videos,
            [],
            RiskLevel.SAFE,
            "generation",
        )
        logger.info("Registered video generation tools")
    except Exception as e:
        logger.warning(f"Failed to register video generation tools: {e}")

    # ── 13. Vision — analyze any image by path ───────────────────────
    try:
        from services.vision_engine import VisionEngine
        _vision_any = VisionEngine()

        def analyze_image_file(path: str, prompt: str = "Describe this image in detail.") -> str:
            return _vision_any.analyze_image(path, prompt)

        reg.register(
            "analyze_image_file",
            "Analyze any image file on the system by its path. Uses AI vision to describe contents.",
            analyze_image_file,
            ["path"],
            RiskLevel.SAFE,
            "vision",
        )
        logger.info("Registered image analysis tool")
    except Exception as e:
        logger.warning(f"Failed to register image analysis tool: {e}")

    # ── 13.5 Project Builder System ─────────────────────────────────────
    try:
        from agents.project_builder import run_project_builder, check_build_status

        reg.register(
            "build_project",
            "Use this tool when the user asks to build a complete project, application, or system. This will trigger a multi-agent swarm (Architecture, Coding, Documentation) to scaffold the folder structure, write all files, and install dependencies into a dedicated workspace.",
            run_project_builder,
            ["objective"],
            RiskLevel.HIGH,
            "generation",
        )
        
        reg.register(
            "check_project_status",
            "Use this tool to check the current progress and status of the background project builder swarm (PBS). Returns detailed statistics, progress percentage, and generated files list.",
            check_build_status,
            [],
            RiskLevel.SAFE,
            "generation",
        )
        logger.info("Registered Project Builder and Status tools")
    except Exception as e:
        logger.warning(f"Failed to register Project Builder tool: {e}")

    # ── 14. Dynamic Tool Forge ──────────────────────────────────────────
    try:
        from generation.tool_forge import ToolForge
        _forge = ToolForge()

        def dynamic_tool_forge(task_description: str) -> str:
            import uuid
            safe_name = "tool_" + str(uuid.uuid4().hex[:8])
            result = _forge.forge_custom(safe_name, f"Generated for task: {task_description}", task_description)
            if hasattr(result, 'tool_id'):
                return f"Successfully forged and saved tool: {result.name}. The new tool enables this capability immediately."
            from engine.state_manager import global_state_manager
            global_state_manager.set_global_action("Idle")
            return f"Failed to forge tool: {result}"

        reg.register(
            "dynamic_tool_forge",
            "Creates and registers a completely new Python tool on-the-fly using AI if a capability is missing. ONLY use this if the user EXPLICITLY asked to make/generate a tool, or if they confirmed to do so. Provide a detailed prompt of what the tool should accomplish in 'task_description'.",
            dynamic_tool_forge,
            ["task_description"],
            RiskLevel.CRITICAL,
            "generation",
            approval_requirement=True,
        )
        logger.info("Registered dynamic tool forge tool")
    except Exception as e:
        logger.warning(f"Failed to register dynamic tool forge: {e}")

    # ── 15. Shell GPT Bridge — Smart Shell, Caching, Functions ─────────
    try:
        from services.shell_gpt_bridge import smart_shell, response_cache, session_manager, function_registry

        async def smart_shell_generate(request: str) -> str:
            """Generate a shell command from natural language, describe it, and execute it."""
            result = await smart_shell.smart_execute(request, auto_execute=True)
            import json
            return json.dumps(result.to_dict(), indent=2)

        async def smart_shell_preview(request: str) -> str:
            """Generate a shell command from natural language WITHOUT executing it. Returns the command and its description."""
            command = await smart_shell.generate_command(request)
            description = await smart_shell.describe_command(command)
            import json
            return json.dumps({
                "command": command,
                "description": description,
                "os": smart_shell.os_name,
                "shell": smart_shell.shell_name,
                "executed": False,
            }, indent=2)

        async def describe_shell_command(command: str) -> str:
            """Explain what a specific shell/terminal command does in plain language."""
            description = await smart_shell.describe_command(command)
            return f"Command: {command}\nDescription: {description}"

        async def generate_code(request: str, language: str = "python", **kwargs) -> str:
            """Generate pure code (no markdown) from a natural language description."""
            return await smart_shell.generate_code(request, language)

        def clear_response_cache() -> str:
            """Clear the AI response cache to force fresh responses."""
            count = response_cache.clear()
            return f"Cleared {count} cached responses."

        def list_chat_sessions() -> str:
            """List all named chat sessions."""
            sessions = session_manager.list_sessions()
            if not sessions:
                return "No saved chat sessions."
            import json
            return json.dumps(sessions, indent=2)

        def list_tools(**kwargs) -> str:
            """List all available tools in the system."""
            from tools.universal_registry import get_universal_registry
            reg = get_universal_registry()
            lines = ["Available Tools:"]
            for t in reg.get_enabled_tools():
                params = ", ".join([p.name for p in t.input_schema.params]) if t.input_schema.params else "none"
                lines.append(f"  • {t.name}({params}): {t.description}")
            return "\n".join(lines)

        def list_agents(**kwargs) -> str:
            """List all active AI agents and their capabilities."""
            from agents.agent_registry import agent_registry
            return agent_registry.get_capabilities_summary()

        reg.register(
            "smart_shell_generate",
            "Generate the perfect shell/PowerShell/bash command from a natural language description and execute it. Use when user wants to do something on the system but doesn't give the exact command (e.g. 'find large files', 'kill node processes', 'show disk usage', 'list all running services'). The AI figures out the correct command automatically.",
            smart_shell_generate,
            ["request"],
            RiskLevel.HIGH,
            "shell",
        )
        reg.register(
            "smart_shell_preview",
            "Generate a shell command from natural language but DO NOT execute it — only preview the command and its description. Use when user says 'what command would...', 'how to...', or you want to show the command before running.",
            smart_shell_preview,
            ["request"],
            RiskLevel.SAFE,
            "shell",
        )
        reg.register(
            "describe_shell_command",
            "Explain what a specific shell/terminal command does, including all its flags and arguments. Use when user asks 'what does X command do?' or 'explain this command'.",
            describe_shell_command,
            ["command"],
            RiskLevel.SAFE,
            "shell",
        )
        reg.register(
            "generate_code",
            "Generate pure code from a natural language description. Returns clean code as a string. THIS DOES NOT SAVE THE CODE TO A FILE. To save the code, you MUST use the write_file tool to write this generated code to a file.",
            generate_code,
            ["request"],
            RiskLevel.SAFE,
            "generation",
        )
        reg.register(
            "clear_response_cache",
            "Clear the AI response cache to force fresh responses for previously cached queries.",
            clear_response_cache,
            [],
            RiskLevel.LOW,
            "system",
        )
        reg.register(
            "list_chat_sessions",
            "List all saved named chat sessions with their message counts and last modified dates.",
            list_chat_sessions,
            [],
            RiskLevel.SAFE,
            "conversation",
        )
        reg.register(
            "list_tools",
            "List all available executable tools (functions) in the system with their descriptions and parameters. This lists tools NOT agents. Do NOT use this when the user asks about agents — use list_agents instead.",
            list_tools,
            [],
            RiskLevel.SAFE,
            "system",
        )
        reg.register(
            "list_agents",
            "List all AI agents (ChatAgent, CodeAgent, SecurityAgent, etc.), sub-agents, and their capabilities. Use this when the user asks 'kitne agent hai', 'agent ki list', 'how many agents', 'what agents do you have', or any question about AI agents. Do NOT confuse with list_tools.",
            list_agents,
            [],
            RiskLevel.SAFE,
            "system",
        )
        logger.info("Registered Shell GPT Bridge tools (smart shell, caching, code generation)")
    except Exception as e:
        logger.warning(f"Failed to register Shell GPT Bridge tools: {e}")

    # —— 16. Workflow, Security, and Navigation —— #
    try:
        from automation.workflow_engine import WorkflowEngine
        from services.security_layer import SecurityLayer
        from automation.navigation_engine import NavigationEngine

        _workflow = WorkflowEngine()
        _security = SecurityLayer()
        _navigation = NavigationEngine()

        def list_workflows() -> str:
            import json
            return json.dumps(_workflow.list_workflows(), indent=2)

        def run_workflow(workflow_id: str) -> str:
            import json
            return json.dumps(_workflow.run_workflow(workflow_id), indent=2)

        def security_status() -> str:
            import json
            return json.dumps({"locked": _security.is_locked()}, indent=2)

        def open_map(location: str = "") -> str:
            import json
            return json.dumps(_navigation.open_map(location or None), indent=2)

        def get_directions(origin: str, destination: str, mode: str = "driving") -> str:
            import json
            return json.dumps(_navigation.get_directions(origin, destination, mode), indent=2)

        reg.register("list_workflows", "List available AERIS workflows.", list_workflows, [], RiskLevel.SAFE, "automation")
        reg.register("run_workflow", "Execute a saved workflow by its workflow_id.", run_workflow, ["workflow_id"], RiskLevel.MEDIUM, "automation")
        reg.register("security_status", "Check whether AERIS's local security layer is locked.", security_status, [], RiskLevel.SAFE, "system")
        reg.register("open_map", "Open Google Maps focused on a location.", open_map, ["location"], RiskLevel.LOW, "navigation")
        reg.register("get_directions", "Open directions between an origin and destination in Google Maps.", get_directions, ["origin", "destination"], RiskLevel.LOW, "navigation")
        logger.info("Registered workflow, security, and navigation tools")
    except Exception as e:
        logger.warning(f"Failed to register workflow/security/navigation tools: {e}")

    # —— 16.5. Security Agent Gateway —— #
    # Exposes SecurityAgent capabilities as a tool so the agentic loop
    # can route security queries (SSL, port scan, DNS, recon, VAPT, etc.)
    # through the correct agent instead of falling back to smart_shell_generate.
    try:
        import asyncio as _asyncio

        def security_scan(request: str) -> str:
            """Run a full security assessment through the SecurityAgent."""
            from agents.security_agent import SecurityAgent as _SecAgent
            from memory.store import memory_store as _mem

            agent = _SecAgent()
            context = {"chat_history": _mem.get_context(5)}

            async def _run():
                result = await agent.run(request, context)
                return result.get("response", "Security scan completed but no output was returned.")

            try:
                loop = _asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(_asyncio.run, _run()).result(timeout=120)
            else:
                return _asyncio.run(_run())

        reg.register(
            "security_scan",
            "Run a cybersecurity assessment on a target domain, IP, or URL. Covers: SSL/TLS check, "
            "port scanning, DNS lookup, subdomain enumeration, WHOIS, HTTP header analysis, "
            "vulnerability assessment (VAPT), and zero-day detection. "
            "Use this for ANY security-related request like 'check SSL for google.com', "
            "'scan ports on 192.168.1.1', 'DNS lookup for example.com', 'full recon on target.com'. "
            "Do NOT use smart_shell_generate for security tasks — use this tool instead.",
            security_scan,
            ["request"],
            RiskLevel.SAFE,
            "security",
        )
        logger.info("Registered SecurityAgent gateway tool")
    except Exception as e:
        logger.warning(f"Failed to register SecurityAgent gateway: {e}")

    # —— 16.6. Email Agent Gateway —— #
    try:
        async def send_email(recipient: str, body: str, subject: str = "AERIS Notification") -> str:
            """
            Send an email message to a recipient using the configured SMTP settings.
            Supports resolving names like 'me', 'sambhav', 'sambhav mehra' to 'sambhavmehra07@gmail.com'.
            """
            from agents.email_agent import EmailAgent
            agent = EmailAgent()
            plan = {
                "recipient": recipient,
                "subject": subject,
                "body": body
            }
            results = await agent.execute(plan)
            return await agent.report(results)

        reg.register(
            "send_email",
            "Send an email message to a recipient using the configured SMTP settings. "
            "Inputs: recipient (required, name or email address), body (required, plain text content), "
            "subject (optional, defaults to 'AERIS Notification').",
            send_email,
            ["recipient", "body"],
            RiskLevel.MEDIUM,
            "email",
            optional_params=["subject"]
        )
        logger.info("Registered EmailAgent gateway tool")
    except Exception as e:
        logger.warning(f"Failed to register EmailAgent gateway: {e}")

    # -- 17. Computer Use (Vision UI Automation) -- #
    try:
        from automation.computer_use import ComputerUseEngine
        _cu_engine = ComputerUseEngine()

        def computer_use_task(instruction: str) -> str:
            """
            Takes control of the computer to perform UI actions using AI Vision.
            Can open apps, type, click, and read the screen.
            """
            from engine.state_manager import global_state_manager
            global_state_manager.set_global_action("UI Automation")
            res = _cu_engine.execute_task(instruction, max_steps=5)
            global_state_manager.set_global_action("Idle")
            
            if res.success:
                return f"Task completed successfully. Verification: {res.verification}"
            else:
                return f"Task failed. Error: {res.error}. The AI vision might need more specific instructions or the app may be in an unexpected state."

        reg.register(
            "computer_use_task",
            "Takes control of the computer to interact with graphical applications using AI Vision. Use this for WhatsApp messaging, clicking UI elements, or reading the screen. Provide a very detailed instruction of what to look for and what to do.",
            computer_use_task,
            ["instruction"],
            RiskLevel.HIGH,
            "automation",
            timeout=180,
            approval_requirement=True,
        )
        logger.info("Registered Computer Use tool")
    except Exception as e:
        logger.warning(f"Failed to register Computer Use tool: {e}")

    # —— 18. MCP Dynamic Installer —— #
    try:
        import tools.mcp_installer
        logger.info("Registered MCP Installer tools")
    except Exception as e:
        logger.warning(f"Failed to register MCP Installer tools: {e}")

    # ── 19. Recon & Security Scanning ────────────────────────────────
    try:
        from tools.recon_tools import dns_lookup, whois_lookup, port_scan, header_analysis, ssl_check, subdomain_enum

        reg.register("dns_lookup", "Perform a DNS lookup for a domain.", dns_lookup, ["domain"], RiskLevel.SAFE, "recon")
        reg.register("whois_lookup", "Perform WHOIS lookup.", whois_lookup, ["domain"], RiskLevel.SAFE, "recon")
        reg.register("port_scan", "Scan common ports on a target IP or domain.", port_scan, ["target"], RiskLevel.LOW, "recon")
        reg.register("header_analysis", "Analyze HTTP headers for a URL.", header_analysis, ["url"], RiskLevel.SAFE, "recon")
        reg.register("ssl_check", "Check SSL certificate for a domain.", ssl_check, ["domain"], RiskLevel.SAFE, "recon")
        reg.register("subdomain_enum", "Enumerate common subdomains.", subdomain_enum, ["domain"], RiskLevel.LOW, "recon")
        logger.info("Registered missing recon tools for SecurityAgent")
    except Exception as e:
        logger.warning(f"Failed to register recon tools: {e}")

    # ── 20. Diagnostics & Health Assessment ──────────────────────────
    try:
        from tools.diagnostics_tools import diagnose_system, diagnose_code, suggest_code_fixes, diagnose_agent

        reg.register(
            "diagnose_system",
            "Perform a complete system check including hardware resource loads, API keys status, package dependencies, and agent health.",
            diagnose_system,
            [],
            RiskLevel.SAFE,
            "diagnostics",
        )
        reg.register(
            "diagnose_agent",
            "Diagnose a specific agent by its name (e.g. 'SecurityAgent', 'ChatAgent'). Checks capabilities, child sub-agents, and runs a dry-run test.",
            diagnose_agent,
            ["agent_name"],
            RiskLevel.SAFE,
            "diagnostics",
        )
        reg.register(
            "diagnose_code",
            "Scan files in the codebase recursively for syntax errors, console log checks, naming anomalies, and large file warnings. Provide path parameter if checking a subfolder.",
            diagnose_code,
            [],
            RiskLevel.SAFE,
            "diagnostics",
            optional_params=["path"]
        )
        reg.register(
            "suggest_code_fixes",
            "Generate automatic repair solutions, clean code corrections, and Git patch diffs for code warnings or errors. Requires path and errors parameters.",
            suggest_code_fixes,
            ["path", "errors"],
            RiskLevel.MEDIUM,
            "diagnostics",
        )
        logger.info("Registered diagnostics tools")
    except Exception as e:
        logger.warning(f"Failed to register diagnostics tools: {e}")

    # ── 21. Advanced Features (NLP, ML, CV, Analytics, Cloud, Assistant) ──
    try:
        # 21.1. NLP Tools
        from services.nlp_service import nlp_service
        def nlp_analyze_text(text: str) -> str:
            """Perform named entity recognition, sentiment analysis, and tokenization."""
            import json
            return json.dumps(nlp_service.analyze_text(text), indent=2)

        reg.register(
            "nlp_analyze_text",
            "Perform sentiment analysis, named entity recognition, key phrase extraction, and tokenization on a text using SpaCy and NLTK.",
            nlp_analyze_text,
            ["text"],
            RiskLevel.SAFE,
            "research"
        )

        # 21.2. ML Tools
        from services.ml_service import ml_service
        def ml_predict_linear(x_vals: List[float], y_vals: List[float], target_x: float) -> str:
            """Train a Linear Regression model and predict output for a target X value."""
            import json
            return json.dumps(ml_service.predict_linear_regression(x_vals, y_vals, target_x), indent=2)

        def ml_cluster_kmeans(coordinates: List[List[float]], n_clusters: int = 2) -> str:
            """Perform K-Means clustering on coordinates."""
            import json
            return json.dumps(ml_service.cluster_kmeans(coordinates, n_clusters), indent=2)

        def ml_classify_data(train_features: List[List[float]], train_labels: List[Any], test_features: List[List[float]]) -> str:
            """Train a Random Forest classifier and predict labels for test features."""
            import json
            return json.dumps(ml_service.classify_data(train_features, train_labels, test_features), indent=2)

        reg.register("ml_predict_linear", "Perform linear regression modeling and predict output for a target X.", ml_predict_linear, ["x_vals", "y_vals", "target_x"], RiskLevel.SAFE, "research")
        reg.register("ml_cluster_kmeans", "Group coordinates or points using K-Means clustering algorithm.", ml_cluster_kmeans, ["coordinates"], RiskLevel.SAFE, "research", optional_params=["n_clusters"])
        reg.register("ml_classify_data", "Train a classifier and predict class labels for test features.", ml_classify_data, ["train_features", "train_labels", "test_features"], RiskLevel.SAFE, "research")

        # 21.3. Data Analytics Tools
        from services.analytics_service import analytics_service
        def analytics_summarize_csv(csv_path: str) -> str:
            """Generate descriptive statistics and metadata overview for a CSV file using Pandas."""
            import json
            return json.dumps(analytics_service.summarize_csv(csv_path), indent=2)

        def analytics_correlation_csv(csv_path: str) -> str:
            """Calculate the Pearson correlation matrix for numerical columns in a CSV file using Pandas."""
            import json
            return json.dumps(analytics_service.calculate_correlation(csv_path), indent=2)

        reg.register("analytics_summarize_csv", "Generate descriptive statistics, column types, and data head preview for a CSV file.", analytics_summarize_csv, ["csv_path"], RiskLevel.SAFE, "research")
        reg.register("analytics_correlation_csv", "Compute Pearson correlation matrix of numerical columns in a CSV file.", analytics_correlation_csv, ["csv_path"], RiskLevel.SAFE, "research")

        # 21.4. Cloud Tools
        from services.cloud_service import cloud_service
        def cloud_bucket_operation(action: str, file_path: str = "", bucket_name: str = "aeris-default-bucket", object_name: str = "") -> str:
            """Simulate AWS S3/Cloud Storage operations: create_bucket, upload_file, download_file, list_bucket, delete_file."""
            import json
            return json.dumps(cloud_service.storage_operation(action, file_path, bucket_name, object_name), indent=2)

        def cloud_provision_instance(instance_type: str = "t3.micro", region: str = "us-east-1") -> str:
            """Simulate provisioning a virtual machine instance in the cloud."""
            import json
            return json.dumps(cloud_service.provision_instance(instance_type, region), indent=2)

        reg.register("cloud_bucket_operation", "Simulate cloud storage operations: create_bucket, upload_file, download_file, list_bucket, delete_file.", cloud_bucket_operation, ["action"], RiskLevel.MEDIUM, "system", optional_params=["file_path", "bucket_name", "object_name"])
        reg.register("cloud_provision_instance", "Simulate compute VM provisioning in the cloud (e.g. EC2/Compute Engine).", cloud_provision_instance, [], RiskLevel.MEDIUM, "system", optional_params=["instance_type", "region"])

        # 21.5. Computer Vision filter tool
        def vision_apply_filter(image_path: str, filter_type: str) -> str:
            """Apply a computer vision filter to an image using OpenCV (grayscale, blur, edge, threshold)."""
            import json
            from services.vision_engine import VisionEngine
            v = VisionEngine()
            return json.dumps(v.apply_cv_filter(image_path, filter_type), indent=2)

        reg.register("vision_apply_filter", "Apply filters (grayscale, blur, edge, threshold) to an image file using OpenCV.", vision_apply_filter, ["image_path", "filter_type"], RiskLevel.MEDIUM, "vision")

        # 21.6. Assistant log/recommendation tool
        from services.virtual_assistant_service import assistant_service
        def assistant_recommend_personalized() -> str:
            """Get personalized assistant recommendations based on behavior interaction log history."""
            import json
            return json.dumps(assistant_service.get_personalized_recommendations(), indent=2)

        reg.register("assistant_recommend_personalized", "Analyze system history and generate machine learning personalized tips/recommendations.", assistant_recommend_personalized, [], RiskLevel.SAFE, "conversation")

        logger.info("Registered Advanced Features & Capabilities tools (NLP, ML, CV, Analytics, Cloud, Assistant)")
    except Exception as e:
        logger.warning(f"Failed to register advanced feature tools: {e}")

    logger.info(f"Tool registry initialized with {len(reg.get_tool_names())} tools.")

# Register all tools on module load
_register_all_tools()
