"""
AERIS API Server - FastAPI entry point.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from brain import brain
from config import settings
from engine.state_manager import global_state_manager
from neural.core import neural_core
from tools.tool_registry import global_tool_registry as tool_registry
from tools.universal_registry import get_universal_registry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("aeris.api")

# Initialization readiness flags (used by /api/status)
_neural_ready: bool = False
_neural_init_error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _neural_ready, _neural_init_error

    logger.info("Initializing AERIS API Server...")
    logger.info("Registered %s total tools in registry.", len(tool_registry))

    from tools.mcp_bridge import get_mcp_registry
    from tools.tool_health import get_health_tracker

    try:
        universal_reg = get_universal_registry()
        mcp_reg = get_mcp_registry()
        get_health_tracker()
        logger.info(
            "Advanced tool subsystem online: %s universal tools, %s MCP servers.",
            len(universal_reg.get_all_tools()),
            len(mcp_reg.list_servers()),
        )
    except Exception as e:
        # Do not block server start if tool subsystem fails.
        logger.exception("Tool subsystem initialization failed")
        # Keep going.

    logger.info("Initializing Neural Engine...")
    try:
        neural_core.initialize()
        _neural_ready = True
        _neural_init_error = None
    except Exception as e:
        _neural_ready = False
        _neural_init_error = str(e)
        logger.exception("Neural Engine initialization failed; starting in degraded mode.")
    yield
    logger.info("Shutting down AERIS API Server...")


class AERISOSEngine:
    """Compatibility OS engine facade backed by the current AERIS brain/router."""

    async def process_objective(self, objective: str) -> dict[str, Any]:
        result = await brain.process(objective)
        return {
            "task_id": result.get("task_id", ""),
            "objective": objective,
            "status": "completed" if result.get("success", True) else "failed",
            "response": result.get("response", ""),
            "raw_result": result,
            "success": result.get("success", True),
        }


app = FastAPI(title="AERIS Backend API", lifespan=lifespan)
os_engine = AERISOSEngine()
music_extension_ws: Optional[WebSocket] = None
overlay_extension_ws_clients: list[WebSocket] = []
extension_v2_ws_clients: list[WebSocket] = []
_rag_engine = None

_IMAGES_DIR = Path(__file__).resolve().parent / "data" / "generated_images"
_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(_IMAGES_DIR)), name="images")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str = ""
    transcript: str = ""


class OSExecuteRequest(BaseModel):
    objective: str


class RunToolRequest(BaseModel):
    tool_name: str = ""
    args: dict[str, Any] = {}


class ShellRequest(BaseModel):
    command: str = ""
    request: str = ""


class CacheClearRequest(BaseModel):
    query: str = ""


class SessionMessageRequest(BaseModel):
    role: str
    content: str


class ImageGenerateRequest(BaseModel):
    prompt: str
    filename: str = ""
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    model: str = ""


class RAGSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class RAGIndexRequest(BaseModel):
    directory: str = "."
    max_files: int = 300


class PlayMusicRequest(BaseModel):
    song: str


class OverlayRequest(BaseModel):
    text: str


class ExtensionV2RegisterRequest(BaseModel):
    extension_id: str = "extension-v2"
    client_name: str = "Extension V2"
    version: str = "1.0.0"
    metadata: dict[str, Any] = {}


class TriageRequest(BaseModel):
    findings: list[dict[str, Any]]
    headers: dict[str, str] = {}
    tech_stack: list[str] = []


class ZeroDayScanRequest(BaseModel):
    target: str
    urls: list[str] = []
    enable_smuggling: bool = True
    enable_ssti: bool = True
    enable_prototype: bool = True
    enable_cache: bool = True
    enable_jwt: bool = True


class ThreatIntelRequest(BaseModel):
    max_items: int = 120
    days: int = 30
    force_refresh: bool = False
    query: str = ""


class MemoryUpdateRequest(BaseModel):
    action: Optional[str] = None  # "clear", "add_fact", "remove_fact", "update_summary", "update_project_memory"
    fact: Optional[str] = None
    summary: Optional[str] = None
    key: Optional[str] = None
    value: Any = None


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    language_preference: Optional[str] = None
    tone_preference: Optional[str] = None
    common_tasks: Optional[list[str]] = None
    preferred_response_style: Optional[str] = None



def _get_rag_engine():
    global _rag_engine
    if _rag_engine is None:
        from services.rag_engine import RAGVoiceEngine

        _rag_engine = RAGVoiceEngine()
    return _rag_engine


@app.get("/")
async def health_check():
    return {"status": "ok", "assistant": settings.ASSISTANT_NAME, "mode": "autonomous"}


@app.get("/api/status")
async def get_status():
    from memory.store import memory_store

    reg = get_universal_registry()
    return {
        "status": "online",
        "mode": "autonomous_agent",
        "agents": list(brain.agents.keys()),
        "tools_count": len(tool_registry),
        "os_tools_loaded": len(reg.get_tool_names()),
        "memory_messages": len(memory_store.chat_history),
        "active_tasks": len(global_state_manager.get_active_tasks()),
        "extension_v2_clients": len(extension_v2_ws_clients),
        "neural_ready": _neural_ready,
        "initialization_error": _neural_init_error,
    }


@app.get("/api/greeting")
async def api_greeting():
    from services.greeting_service import generate_dynamic_greeting

    return generate_dynamic_greeting()


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        message = req.message or req.transcript
        if not message.strip():
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        return await brain.process(message)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Chat endpoint error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents")
async def get_agents():
    return {name: {"description": agent.description} for name, agent in brain.agents.items()}


@app.get("/api/tools")
async def get_tools():
    reg = get_universal_registry()
    return {t.name: {"description": t.description, "category": t.category, "risk": t.risk_level.value} for t in reg.get_enabled_tools()}


@app.post("/api/tools/execute")
async def api_execute_tool(request: RunToolRequest):
    try:
        reg = get_universal_registry()
        result = await reg.execute_async(request.tool_name, **request.args)
        return {"success": True, "tool_name": request.tool_name, "result": result}
    except Exception as e:
        logger.exception("Tool execution error")
        return {"success": False, "tool_name": request.tool_name, "error": str(e)}


@app.get("/api/chat/history")
async def get_chat_history():
    from memory.store import memory_store

    return {"history": memory_store.chat_history}


@app.post("/api/chat/clear")
async def clear_chat():
    from memory.store import memory_store

    memory_store.clear_history()
    return {"status": "success", "message": "Chat history cleared"}


@app.get("/api/memory")
async def get_memory():
    from memory.store import memory_store
    return {
        "short_term_summary": memory_store.short_term_summary,
        "long_term_facts": memory_store.long_term_facts,
        "project_memory": memory_store.project_memory,
        "vector_hooks": memory_store.vector_hooks
    }


@app.post("/api/memory")
async def update_memory(req: MemoryUpdateRequest):
    from memory.store import memory_store
    action = req.action
    if action == "clear":
        memory_store.clear_all()
        return {"success": True, "message": "All memory cleared"}
    elif action == "add_fact":
        if not req.fact:
            raise HTTPException(status_code=400, detail="fact is required for add_fact action")
        added = memory_store.add_fact(req.fact)
        return {"success": added, "message": "Fact added" if added else "Fact not added (duplicate or sensitive)"}
    elif action == "remove_fact":
        if not req.fact:
            raise HTTPException(status_code=400, detail="fact is required for remove_fact action")
        removed = memory_store.remove_fact(req.fact)
        return {"success": removed, "message": "Fact removed" if removed else "Fact not found"}
    elif action == "update_summary":
        if req.summary is None:
            raise HTTPException(status_code=400, detail="summary is required for update_summary action")
        memory_store.update_summary(req.summary)
        return {"success": True, "message": "Summary updated"}
    elif action == "update_project_memory":
        if not req.key:
            raise HTTPException(status_code=400, detail="key is required for update_project_memory action")
        memory_store.update_project_memory(req.key, req.value)
        return {"success": True, "message": f"Project memory for {req.key} updated"}
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")


@app.get("/api/profile")
async def get_profile():
    from memory.user_profile import user_profile_store
    return user_profile_store.get_profile()


@app.post("/api/profile")
async def update_profile(req: ProfileUpdateRequest):
    from memory.user_profile import user_profile_store
    update_data = {k: v for k, v in req.dict(exclude_unset=True).items() if v is not None}
    updated = user_profile_store.update_profile(**update_data)
    return {"success": True, "profile": updated}


@app.post("/api/os/execute")
async def os_execute(req: OSExecuteRequest):
    return await os_engine.process_objective(req.objective)


@app.get("/api/os/status")
async def os_status():
    current = global_state_manager.get_current_task()
    return {
        "active_tasks": global_state_manager.get_active_tasks(),
        "all_tasks": global_state_manager.get_all_tasks(),
        "current_task": current.to_dict() if hasattr(current, "to_dict") else current,
    }


@app.get("/api/os/tools")
async def os_tools():
    return {"tools": [t.to_full_dict() for t in get_universal_registry().get_enabled_tools()]}


@app.get("/api/os/memory")
async def os_memory():
    from memory.store import memory_store

    return {"chat_history": memory_store.chat_history, "task_results": memory_store.task_results}


@app.get("/api/execute/capabilities")
async def execute_capabilities():
    reg = get_universal_registry()
    categories = sorted({t.category for t in reg.get_enabled_tools()})
    return {"types": ["chat", "os_engine", "tool", "shell", "rag", "image"], "categories": categories}


@app.post("/api/execute")
async def unified_execute(req: dict[str, Any] = Body(...)):
    try:
        exec_type = req.get("type") or req.get("intent") or "chat"
        payload = req.get("payload")
        if payload is None:
            # Handle flat payload structure by excluding known top-level keys
            payload = {k: v for k, v in req.items() if k not in ("type", "intent")}

        if exec_type == "chat":
            return await brain.process(payload.get("message") or payload.get("transcript") or "")
        if exec_type in {"os", "os_engine"}:
            return await os_engine.process_objective(payload.get("objective") or payload.get("message") or "")
        if exec_type == "tool":
            name = payload.get("tool_name") or payload.get("name")
            args = payload.get("args") or payload.get("params") or {}
            reg = get_universal_registry()
            result = await reg.execute_async(name, **args)
            return {"success": True, "tool": name, "result": result}
        if exec_type == "shell":
            reg = get_universal_registry()
            result = await reg.execute_async("run_bash", command=payload.get("command", ""))
            return {"success": True, "result": result}
        if exec_type == "rag":
            return await rag_search(RAGSearchRequest(query=payload.get("query", ""), top_k=payload.get("top_k", 5)))
        if exec_type == "image":
            return await api_generate_image(ImageGenerateRequest(**payload))
        raise HTTPException(status_code=400, detail=f"Unsupported execute type: {exec_type}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unified execute error")
        return {"success": False, "error": str(e)}


@app.get("/api/gateway/health")
async def gateway_health():
    return {
        "status": "ok",
        "providers": {
            "groq": {"configured_keys": len(settings.GROQ_API_KEYS), "primary_model": settings.GROQ_PRIMARY_MODEL},
            "gemini": {"configured": settings.has_gemini, "model": settings.GEMINI_MODEL},
        },
    }


@app.get("/api/gateway/logs")
async def gateway_logs(n: int = 30):
    return {"status": "ok", "calls": [], "note": "AERIS does not persist provider call logs yet."}


@app.post("/api/shell/generate")
async def api_generate_shell(request: ShellRequest):
    from services.shell_gpt_bridge import smart_shell

    cmd = await smart_shell.generate_command(request.request or request.command)
    desc = await smart_shell.describe_command(cmd)
    return {"command": cmd, "description": desc, "os": smart_shell.os_name, "shell": smart_shell.shell_name}


@app.post("/api/shell/describe")
async def api_describe_shell(request: ShellRequest):
    from services.shell_gpt_bridge import smart_shell

    return {"command": request.command, "description": await smart_shell.describe_command(request.command)}


@app.post("/api/shell/execute")
async def api_execute_shell(request: ShellRequest):
    from services.shell_gpt_bridge import smart_shell

    return smart_shell.execute_command(request.command).to_dict()


@app.get("/api/cache/status")
async def cache_status():
    from services.shell_gpt_bridge import response_cache

    files = list(response_cache.cache_dir.glob("*"))
    return {"cache_dir": str(response_cache.cache_dir), "entries": len(files), "max_entries": response_cache.max_entries}


@app.post("/api/cache/clear")
async def cache_clear(request: CacheClearRequest):
    from services.shell_gpt_bridge import response_cache

    if request.query:
        response_cache.invalidate(request.query)
        return {"cleared": "specific", "query": request.query}
    return {"cleared": "all", "entries_removed": response_cache.clear()}


@app.get("/api/sessions")
async def list_sessions():
    from services.shell_gpt_bridge import session_manager

    return {"sessions": session_manager.list_sessions()}


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    from services.shell_gpt_bridge import session_manager

    messages = session_manager.get_messages(session_id)
    return {"session_id": session_id, "message_count": len(messages), "messages": messages}


@app.post("/api/sessions/{session_id}/message")
async def add_session_message(session_id: str, request: SessionMessageRequest):
    from services.shell_gpt_bridge import session_manager

    session_manager.add_message(session_id, request.role, request.content)
    return {"success": True, "session_id": session_id}


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    from services.shell_gpt_bridge import session_manager

    session_manager.clear_session(session_id)
    return {"deleted": True, "session_id": session_id}


@app.get("/api/functions")
async def list_functions():
    from services.shell_gpt_bridge import function_registry

    return {
        "count": len(function_registry.list_functions()),
        "functions": function_registry.list_functions(),
        "schemas": function_registry.get_all_schemas(),
    }


@app.post("/api/functions/{name}/execute")
async def execute_function(name: str, request: RunToolRequest):
    from services.shell_gpt_bridge import function_registry

    result = function_registry.execute(name, **request.args)
    if asyncio.iscoroutine(result):
        result = await result
    return {"success": True, "function": name, "result": result}


@app.post("/api/images/generate")
async def api_generate_image(request: ImageGenerateRequest):
    from generation.image_generator import ImageGenerator

    return ImageGenerator().generate(
        prompt=request.prompt,
        filename=request.filename,
        negative_prompt=request.negative_prompt,
        width=request.width,
        height=request.height,
        model=request.model,
    )


@app.get("/api/images/list")
async def api_list_images():
    from generation.image_generator import ImageGenerator

    return {"images": ImageGenerator().list_generated()}


@app.get("/api/images/models")
async def api_image_models():
    from generation.image_generator import ImageGenerator

    return {"models": ImageGenerator().get_available_models()}


@app.post("/api/rag/process")
async def rag_process(request: ChatRequest):
    result = await _get_rag_engine().process(request.message or request.transcript)
    return result.to_dict()


@app.post("/api/rag/search")
async def rag_search(request: RAGSearchRequest):
    return {"query": request.query, "results": _get_rag_engine().search_knowledge(request.query, request.top_k)}


@app.post("/api/rag/index")
async def rag_index(request: RAGIndexRequest):
    return _get_rag_engine().indexer.index_directory(request.directory, request.max_files)


@app.get("/api/rag/stats")
async def rag_stats():
    return _get_rag_engine().get_stats()


@app.get("/api/rag/memory")
async def rag_memory():
    return {"context": _get_rag_engine().memory.get_context_window(last_n=20)}


# ── Security Intelligence Endpoints (VulnSage) ─────────────────────────────

@app.get("/api/security/threat-intel")
async def get_threat_intel(force_refresh: bool = False, max_items: int = 120, days: int = 30):
    """Return live CVE + CISA KEV threat intelligence. Cached for 24 hours."""
    try:
        from intelligence.threat_intel import get_threat_intel_agent
        agent = get_threat_intel_agent()
        data = agent.collect_latest(max_items=max_items, days=days, force_refresh=force_refresh)
        return {"success": True, **data}
    except Exception as exc:
        logger.exception("Threat intel fetch failed")
        return {"success": False, "error": str(exc)}


@app.get("/api/security/threat-intel/summary")
async def get_threat_intel_summary():
    """Quick summary of cached threat intel without fetching fresh data."""
    try:
        from intelligence.threat_intel import get_threat_intel_agent
        return {"success": True, **get_threat_intel_agent().get_summary()}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/api/security/threat-intel/critical")
async def get_critical_cves(limit: int = 20):
    """Return Critical/High CVEs from the threat intel cache."""
    try:
        from intelligence.threat_intel import get_threat_intel_agent
        return {"success": True, "items": get_threat_intel_agent().get_critical_cves(limit=limit)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/api/security/threat-intel/exploited")
async def get_known_exploited(limit: int = 20):
    """Return actively exploited CVEs from CISA KEV."""
    try:
        from intelligence.threat_intel import get_threat_intel_agent
        return {"success": True, "items": get_threat_intel_agent().get_known_exploited(limit=limit)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/api/security/threat-intel/search")
async def search_threat_intel(q: str, limit: int = 10):
    """Search cached threat intel for a keyword or CVE ID."""
    try:
        from intelligence.threat_intel import get_threat_intel_agent
        return {"success": True, "query": q, "items": get_threat_intel_agent().search(q, limit=limit)}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.post("/api/security/triage")
async def api_triage_findings(request: TriageRequest):
    """Re-triage a list of findings with AI contextual analysis."""
    try:
        from intelligence.ai_triage import get_auto_triage
        triage = get_auto_triage()
        triaged = await triage.triage_async(
            request.findings,
            headers=request.headers,
            tech_stack=request.tech_stack,
        )
        upgrades = sum(1 for orig, tri in zip(request.findings, triaged)
                       if tri.get("severity") != orig.get("severity"))
        return {"success": True, "findings": triaged, "total": len(triaged), "severity_changes": upgrades}
    except Exception as exc:
        logger.exception("Triage endpoint error")
        return {"success": False, "error": str(exc)}


@app.post("/api/security/zero-day-scan")
async def api_zero_day_scan(request: ZeroDayScanRequest):
    """Run advanced zero-day probes against a target URL."""
    if not request.target:
        raise HTTPException(status_code=400, detail="target URL is required")
    try:
        from intelligence.zeroday_hunter import get_zeroday_hunter
        hunter = get_zeroday_hunter()
        result = await hunter.run_async(
            target=request.target,
            urls=request.urls or [request.target],
            enable_smuggling=request.enable_smuggling,
            enable_ssti=request.enable_ssti,
            enable_prototype=request.enable_prototype,
            enable_cache=request.enable_cache,
            enable_jwt=request.enable_jwt,
        )
        return {"success": True, **result}
    except Exception as exc:
        logger.exception("Zero-day scan error")
        return {"success": False, "error": str(exc)}


@app.post("/api/security/narrative")
async def api_generate_narrative(request: dict[str, Any] = Body(...)):
    """Generate an AI executive threat narrative from a list of findings."""
    try:
        from intelligence.threat_narrative import get_narrative_generator
        narrator = get_narrative_generator()
        domain_info = request.get("domain_info", {"domain": "unknown"})
        vulnerabilities = request.get("findings", [])
        narr = await narrator.generate_async(domain_info, vulnerabilities)
        return {"success": True, **narr}
    except Exception as exc:
        logger.exception("Narrative generation error")
        return {"success": False, "error": str(exc)}


@app.post("/api/extension-v2/register")
async def register_extension_v2(request: ExtensionV2RegisterRequest):
    return {"success": True, **request.model_dump()}


@app.post("/api/extension-v2/status")
async def extension_v2_status():
    return {
        "extension_v2_connected": bool(extension_v2_ws_clients),
        "extension_v2_clients": len(extension_v2_ws_clients),
        "overlay_clients": len(overlay_extension_ws_clients),
        "total_overlay_clients": len(overlay_extension_ws_clients) + len(extension_v2_ws_clients),
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            result = await brain.process(data.get("message") or data.get("transcript") or "")
            await websocket.send_json({"type": "chat_response", **result})
    except WebSocketDisconnect:
        return


@app.websocket("/ws/music")
async def music_websocket_endpoint(websocket: WebSocket):
    global music_extension_ws
    await websocket.accept()
    music_extension_ws = websocket
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        music_extension_ws = None


@app.post("/api/music/play")
async def api_play_music(request: PlayMusicRequest):
    if music_extension_ws is None:
        return {"success": False, "error": "Chrome extension not connected"}
    await music_extension_ws.send_json({"action": "play", "song": request.song})
    return {"success": True, "message": f"Playing {request.song}"}


@app.post("/api/music/pause")
async def api_pause_music():
    if music_extension_ws is None:
        return {"success": False, "error": "Chrome extension not connected"}
    await music_extension_ws.send_json({"action": "pause"})
    return {"success": True}


@app.post("/api/music/resume")
async def api_resume_music():
    if music_extension_ws is None:
        return {"success": False, "error": "Chrome extension not connected"}
    await music_extension_ws.send_json({"action": "resume"})
    return {"success": True}


async def _broadcast_overlay(payload: dict[str, Any]):
    dead = []
    for ws in overlay_extension_ws_clients + extension_v2_ws_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in overlay_extension_ws_clients:
            overlay_extension_ws_clients.remove(ws)
        if ws in extension_v2_ws_clients:
            extension_v2_ws_clients.remove(ws)


@app.websocket("/ws/overlay")
async def overlay_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    overlay_extension_ws_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if websocket in overlay_extension_ws_clients:
            overlay_extension_ws_clients.remove(websocket)


@app.websocket("/ws/extension-v2")
async def extension_v2_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    extension_v2_ws_clients.append(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "identify":
                await websocket.send_json({"type": "identify_ack", "status": "connected", "server_version": "AERIS"})
            elif isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        if websocket in extension_v2_ws_clients:
            extension_v2_ws_clients.remove(websocket)


@app.post("/api/overlay/display")
async def api_display_overlay(request: OverlayRequest):
    await _broadcast_overlay({"action": "display", "text": request.text})
    return {"success": True}


@app.post("/api/overlay/scan")
async def api_trigger_scan():
    await _broadcast_overlay({"action": "scanner", "type": "scan"})
    return {"success": True}


# ── Voice Endpoints ─────────────────────────────────────────────────────────

class VoiceProcessRequest(BaseModel):
    transcript: str
    speak: bool = True  # Whether to auto-speak the response via TTS


@app.post("/api/voice/process")
async def api_voice_process(req: VoiceProcessRequest):
    """
    Process a voice command transcript from the frontend.
    The frontend handles STT via Web Speech API and sends the text here.
    The backend routes it through Brain and optionally speaks the response.
    """
    if not req.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")

    try:
        from services.voice_orchestrator import get_voice_orchestrator

        orchestrator = get_voice_orchestrator()
        result = await orchestrator.process_voice(
            transcript=req.transcript,
            speak_response=req.speak,
        )
        return result.to_dict()
    except Exception as e:
        logger.exception("Voice process error")
        return {"success": False, "error": str(e), "transcript": req.transcript}


@app.post("/api/voice/stop")
async def api_voice_stop():
    """Instantly stop TTS playback."""
    try:
        from services.texttospeech import stop_speaking

        stop_speaking()
        return {"success": True, "message": "TTS stop signal sent"}
    except Exception as e:
        logger.warning(f"Voice stop error: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/voice/status")
async def api_voice_status():
    """Return current voice engine status (speaking, echo cooldown, etc.)."""
    try:
        from services.texttospeech import is_currently_speaking

        speaking = is_currently_speaking()
        return {"success": True, "is_speaking": speaking}
    except Exception as e:
        return {"success": True, "is_speaking": False, "note": str(e)}


# ── Code Pipeline Endpoints ─────────────────────────────────────────────────

class CodePipelineRequest(BaseModel):
    objective: str
    language: str = "python"


# In-flight pipeline state keyed by pipeline_id
_pipeline_state: dict[str, dict] = {}
_pipeline_queues: dict[str, asyncio.Queue] = {}


@app.post("/api/codepipeline/run")
async def start_code_pipeline(req: CodePipelineRequest):
    """Launch the autonomous Planner → Coder → Verifier pipeline."""
    import uuid
    pipeline_id = f"pipe_{uuid.uuid4().hex[:12]}"
    _pipeline_state[pipeline_id] = {"status": "pending", "objective": req.objective, "language": req.language}
    _pipeline_queues[pipeline_id] = asyncio.Queue()

    # Start pipeline in background task
    asyncio.create_task(_run_pipeline(pipeline_id, req.objective, req.language))
    return {"success": True, "pipeline_id": pipeline_id}


async def _run_pipeline(pipeline_id: str, objective: str, language: str):
    """Background coroutine that orchestrates the 3-agent pipeline."""
    q = _pipeline_queues.get(pipeline_id)
    if not q:
        return

    try:
        from agents.planner_agent import PlannerAgent
        from agents.verifier_agent import VerifierAgent
        from agents.sub_agents.coding_agent import CodingAgent, CodingRequest, TaskKind

        # ── Stage 1: Planner ─────────────────────────────────────────
        await q.put({"stage": "planner", "status": "running", "message": "Designing workspace blueprint..."})
        planner = PlannerAgent()
        manifest = await planner.plan_workspace(objective)
        scaffold = planner.scaffold_workspace(manifest)

        await q.put({
            "stage": "planner", "status": "done",
            "message": f"Workspace planned: {manifest.project_name}",
            "manifest": manifest.to_dict(),
        })

        # ── Stage 2: Coder ───────────────────────────────────────────
        await q.put({"stage": "coder", "status": "running", "message": "Generating source files..."})
        coder = CodingAgent(enable_validation=True, enable_cache=False)
        project_path = scaffold["project_path"]
        written_files = []

        import json as _json
        arch_summary = _json.dumps(manifest.to_dict(), indent=2)

        for i, file_spec in enumerate(manifest.files):
            file_path_rel = file_spec.path
            await q.put({
                "stage": "coder", "status": "running",
                "message": f"Writing {file_path_rel}...",
                "file": file_path_rel,
                "progress_current": i + 1,
                "progress_total": len(manifest.files),
            })

            file_objective = (
                f"Generate the COMPLETE source code for: {file_path_rel}\n"
                f"Description: {file_spec.description}\n"
                f"Project objective: {objective}\n"
                f"Blueprint:\n{arch_summary}\n\n"
                f"RULES:\n"
                f"- Output ONLY the code for THIS ONE file: {file_path_rel}\n"
                f"- Make it COMPLETE and EXECUTABLE\n"
                f"- Include ALL imports, classes, functions\n"
            )

            try:
                result = await coder.generate_code_async(
                    request=file_objective,
                    language=file_spec.language or language,
                )
                content = _extract_best_code(result, file_path_rel)
                if content and len(content.strip()) > 10:
                    abs_path = Path(project_path) / file_path_rel
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(content, encoding="utf-8")
                    written_files.append({"path": file_path_rel, "content": content})

                    await q.put({
                        "stage": "coder", "status": "running",
                        "message": f"Wrote {file_path_rel}",
                        "written_file": {"path": file_path_rel, "content": content},
                        "progress_current": i + 1,
                        "progress_total": len(manifest.files),
                    })
            except Exception as e:
                logger.warning(f"[Pipeline] Failed to generate {file_path_rel}: {e}")

        await q.put({
            "stage": "coder", "status": "done",
            "message": f"Generated {len(written_files)} files",
        })

        # ── Stage 3: Verifier ────────────────────────────────────────
        await q.put({"stage": "verifier", "status": "running", "message": "Running verification..."})
        verifier = VerifierAgent()
        report = await verifier.verify_workspace(
            workspace_path=project_path,
            entry_point=manifest.entry_point,
            language=language,
        )

        await q.put({
            "stage": "verifier", "status": "done",
            "message": f"Verification {'PASSED' if report.passed else 'FAILED'}",
            "report": report.to_dict(),
        })

        # ── Complete ─────────────────────────────────────────────────
        await q.put({
            "stage": "complete", "status": "done",
            "message": "Pipeline finished successfully",
            "project_path": project_path,
        })
        _pipeline_state[pipeline_id] = {"status": "complete", "project_path": project_path}

    except Exception as e:
        logger.exception(f"[Pipeline] Fatal error: {e}")
        await q.put({"stage": "error", "status": "error", "message": str(e)})
        _pipeline_state[pipeline_id] = {"status": "error", "error": str(e)}


def _extract_best_code(result: dict, target_path: str) -> str:
    """Extract the best code content from a CodingResult dict."""
    files = result.get("files", [])
    if files:
        for f in files:
            if isinstance(f, dict) and f.get("content"):
                return f["content"]
    code = result.get("code", "")
    if code and len(code.strip()) > 10:
        return code
    analysis = result.get("analysis", "")
    if "import " in analysis or "def " in analysis or "function " in analysis:
        return analysis
    return ""


class MCPConnectRequest(BaseModel):
    server_name: str
    env_vars: Optional[dict[str, str]] = None
    extra_args: Optional[list[str]] = None


@app.post("/api/mcp/connect")
async def mcp_connect(req: MCPConnectRequest):
    try:
        from starlette.concurrency import run_in_threadpool
        from tools.mcp_installer import install_mcp_server
        
        res_str = await run_in_threadpool(
            install_mcp_server,
            server_name=req.server_name,
            env_vars=req.env_vars,
            extra_args=req.extra_args
        )
        
        import json
        result = json.loads(res_str)
        return result
    except Exception as e:
        logger.exception("MCP connection endpoint error")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/codepipeline/{pipeline_id}")
async def codepipeline_ws(websocket: WebSocket, pipeline_id: str):
    """Stream pipeline stage events to the frontend in real-time."""
    await websocket.accept()
    q = _pipeline_queues.get(pipeline_id)
    if not q:
        await websocket.send_json({"stage": "error", "message": "Pipeline not found"})
        await websocket.close()
        return

    try:
        while True:
            msg = await asyncio.wait_for(q.get(), timeout=120)
            await websocket.send_json(msg)
            if msg.get("stage") in ("complete", "error"):
                break
    except asyncio.TimeoutError:
        await websocket.send_json({"stage": "error", "message": "Pipeline timed out"})
    except WebSocketDisconnect:
        pass
    finally:
        _pipeline_queues.pop(pipeline_id, None)


@app.get("/api/codepipeline/workspaces")
async def list_codepipeline_workspaces():
    """List all generated project directories."""
    base = (Path(__file__).resolve().parent.parent / "workspace").resolve()
    if not base.exists():
        return {"workspaces": []}
    projects = []
    for d in sorted(base.iterdir()):
        if d.is_dir():
            files = list(d.rglob("*"))
            source_files = [f for f in files if f.is_file() and not any(
                s in f.parts for s in ("__pycache__", "node_modules", ".git")
            )]
            projects.append({
                "name": d.name,
                "path": str(d),
                "file_count": len(source_files),
            })
    return {"workspaces": projects}


@app.websocket("/ws/{path:path}")
async def ws_catchall(websocket: WebSocket, path: str):
    await websocket.close(code=1008, reason=f"Unknown WebSocket endpoint: /ws/{path}")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting server on port %s", settings.API_PORT)
    uvicorn.run("api:app", host="0.0.0.0", port=settings.API_PORT, reload=True)
