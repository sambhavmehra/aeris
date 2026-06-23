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

    # Start Task Scheduler
    try:
        from services.scheduler import get_scheduler
        get_scheduler().start()
        logger.info("AERIS Task Scheduler service online.")
    except Exception as e:
        logger.error(f"Failed to start Task Scheduler: {e}")

    # Start Workspace Watcher
    try:
        from services.workspace_watcher import get_workspace_watcher
        get_workspace_watcher().start()
        logger.info("AERIS Workspace Watcher service online.")
    except Exception as e:
        logger.error(f"Failed to start Workspace Watcher: {e}")

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

    # Start Telegram bot long poller if Telegram is configured
    from config import settings
    if settings.has_telegram:
        try:
            from services.telegram_poller import poll_telegram_updates
            app.state.tg_poller = asyncio.create_task(poll_telegram_updates())
            logger.info("AERIS Telegram Bot Poller service spawned in background.")
        except Exception as e:
            logger.error(f"Failed to spawn Telegram Bot Poller: {e}")

    yield

    logger.info("Shutting down AERIS API Server...")

    # Stop Workspace Watcher
    try:
        from services.workspace_watcher import get_workspace_watcher
        get_workspace_watcher().stop()
        logger.info("AERIS Workspace Watcher service stopped.")
    except Exception as e:
        logger.error(f"Failed to stop Workspace Watcher: {e}")

    # Stop Screen Monitor
    try:
        from services.screen_monitor import get_screen_monitor
        get_screen_monitor().stop_monitoring()
        logger.info("AERIS Screen Monitor service stopped.")
    except Exception as e:
        logger.error(f"Failed to stop Screen Monitor: {e}")

    # Stop Telegram bot long poller
    if hasattr(app.state, "tg_poller") and app.state.tg_poller:
        logger.info("Stopping Telegram Bot Poller service...")
        app.state.tg_poller.cancel()
        try:
            await app.state.tg_poller
        except asyncio.CancelledError:
            pass
        logger.info("Telegram Bot Poller service stopped.")

    # Stop Task Scheduler
    try:
        from services.scheduler import get_scheduler
        get_scheduler().stop()
        logger.info("AERIS Task Scheduler service stopped.")
    except Exception as e:
        logger.error(f"Failed to stop Task Scheduler: {e}")

    # Close Gemini AI Client
    try:
        from ai_engine import ai_engine
        if ai_engine._gemini_client and hasattr(ai_engine._gemini_client, "_api_client") and hasattr(ai_engine._gemini_client._api_client, "_async_httpx_client"):
            async_client = ai_engine._gemini_client._api_client._async_httpx_client
            if async_client:
                await async_client.aclose()
                logger.info("Gemini HTTPX async client closed.")
    except Exception as e:
        logger.error(f"Failed to close Gemini API client: {e}")



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

# ── PhantomTrace ethical link analytics routes ──────────────────────────────
from services.phantom_routes import router as phantom_router
app.include_router(phantom_router)

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


class OverlayQueryRequest(BaseModel):
    text: str


class CropBoxRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int


class QueryRegionRequest(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    query: str


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
    from fastapi.responses import FileResponse
    index_path = Path(__file__).resolve().parent / "dist" / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"status": "ok", "assistant": settings.ASSISTANT_NAME, "mode": "autonomous"}


@app.get("/api/status")
async def get_status():
    from memory.store import memory_store
    from memory.user_profile import user_profile_store

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
        "hacker_mode": user_profile_store.get_profile().get("hacker_mode", False),
        "current_hud": global_state_manager.current_hud,
        "active_pipeline_id": global_state_manager.active_pipeline_id,
    }


@app.get("/api/greeting")
async def api_greeting():
    from services.greeting_service import generate_dynamic_greeting

    return generate_dynamic_greeting()


class HackerAuthRequest(BaseModel):
    password: str


@app.post("/api/hacker-mode/auth")
async def hacker_mode_auth(req: HackerAuthRequest):
    from memory.user_profile import user_profile_store
    from memory.store import memory_store

    # Validate clearance password
    if req.password.strip().lower() == "sambhav":
        # Clear any pending challenge in brain
        brain._hacker_challenge_pending = False
        
        user_profile_store.update_profile(hacker_mode=True)
        return {
            "success": True,
            "message": "Security clearance granted. Hacker Brain Activated.",
            "hacker_mode": True
        }
    else:
        return {
            "success": False,
            "message": "Access Denied. Invalid security clearance key.",
            "hacker_mode": False
        }


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
        added = await memory_store.add_fact(req.fact)
        return {"success": added, "message": "Fact added" if added else "Fact not added (duplicate or sensitive)"}
    elif action == "remove_fact":
        if not req.fact:
            raise HTTPException(status_code=400, detail="fact is required for remove_fact action")
        removed = await memory_store.remove_fact(req.fact)
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


@app.get("/api/jobs/active")
async def get_active_jobs():
    from services.job_manager import get_job_manager
    return {"jobs": get_job_manager().list_active_jobs()}


@app.get("/api/watcher/pending")
async def get_pending_repairs():
    from services.workspace_watcher import get_workspace_watcher
    pending = get_workspace_watcher().get_pending_repairs()
    formatted = []
    for rid, info in pending.items():
        formatted.append({
            "repair_id": rid,
            "rel_path": str(info["rel_path"]),
            "error": info["error"],
            "timestamp": info["timestamp"]
        })
    return {"pending_repairs": formatted}


@app.post("/api/watcher/repair/{repair_id}")
async def repair_file_by_id(repair_id: str):
    from services.workspace_watcher import get_workspace_watcher
    result = await get_workspace_watcher().trigger_repair(repair_id)
    if "error" in result.lower() or "failed" in result.lower():
        raise HTTPException(status_code=400, detail=result)
    return {"success": True, "message": result}


@app.get("/api/jobs")
async def get_all_jobs_endpoint():
    from services.job_manager import get_job_manager
    return {"jobs": get_job_manager().list_all_jobs()}


@app.get("/api/jobs/{job_id}")
async def get_job_by_id(job_id: str):
    from services.job_manager import get_job_manager
    job = get_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/pause")
async def pause_job_endpoint(job_id: str):
    from services.job_manager import get_job_manager
    success = get_job_manager().pause_job(job_id)
    return {"success": success, "message": f"Job {job_id} paused" if success else "Job not found or not running"}


@app.post("/api/jobs/{job_id}/resume")
async def resume_job_endpoint(job_id: str):
    from services.job_manager import get_job_manager
    from brain import brain
    from config import settings
    import json
    from pathlib import Path

    job_mgr = get_job_manager()
    
    # Check if there is pending approval to resume from
    pending_file = settings.DATA_DIR / "pending_approval.json"
    state = None
    if pending_file.exists():
        try:
            with open(pending_file, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            pass

    success = job_mgr.resume_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job not found or not in paused state")

    if state and state.get("task_id") == job_id:
        tool_name = state.get("tool_name_pending")
        if tool_name:
            from tools.tool_permissions import get_permission_system
            get_permission_system().approve_for_session(tool_name)
            
        try:
            pending_file.unlink()
        except Exception:
            pass
            
        # Spawn the task based on the saving core
        agent_core = state.get("agent", "Brain")
        if agent_core == "HackerBrain":
            from hacker_brain import hacker_brain
            asyncio.create_task(hacker_brain._run_background_job_resume(job_id, state))
        else:
            asyncio.create_task(brain._run_background_job_resume(job_id, state))
            
        return {"success": True, "message": f"Job {job_id} resumed from security approval."}
    
    return {"success": True, "message": f"Job {job_id} resumed."}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str):
    from services.job_manager import get_job_manager
    success = get_job_manager().cancel_job(job_id)
    return {"success": success, "message": f"Job {job_id} cancelled" if success else "Job not found or not running"}


@app.get("/dashboard/{job_id}")
async def get_dashboard_page(job_id: str):
    from fastapi.responses import HTMLResponse
    from services.job_manager import get_job_manager
    
    job = get_job_manager().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AERIS Mission Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #08090f;
            --panel-bg: rgba(18, 20, 32, 0.7);
            --border-color: rgba(0, 242, 254, 0.15);
            --accent-cyan: #00f2fe;
            --accent-purple: #9d4edd;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --status-running: #00f2fe;
            --status-paused: #f59e0b;
            --status-completed: #10b981;
            --status-failed: #ef4444;
            --status-cancelled: #6b7280;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            background-color: var(--bg-color);
            color: var(--text-primary);
            font-family: 'Outfit', sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem 1rem;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(157, 78, 221, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(0, 242, 254, 0.05) 0%, transparent 40%);
        }

        .container {
            width: 100%;
            max-width: 900px;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1rem;
        }

        .logo-section {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }

        .logo-glow {
            width: 16px;
            height: 16px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            border-radius: 50%;
            box-shadow: 0 0 12px var(--accent-cyan);
            animation: pulse 2s infinite alternate;
        }

        h1 {
            font-size: 1.75rem;
            font-weight: 800;
            letter-spacing: -0.025em;
            background: linear-gradient(to right, #fff, var(--text-secondary));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .job-id-badge {
            font-family: 'JetBrains Mono', monospace;
            background: rgba(255, 255, 255, 0.05);
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
            color: var(--accent-cyan);
            border: 1px solid var(--border-color);
        }

        .card {
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 1rem;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }

        .status-section {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.35rem 0.85rem;
            border-radius: 9999px;
            font-weight: 600;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border: 1px solid transparent;
        }

        .status-badge.running {
            background: rgba(0, 242, 254, 0.1);
            color: var(--status-running);
            border-color: rgba(0, 242, 254, 0.25);
            box-shadow: 0 0 15px rgba(0, 242, 254, 0.25);
        }
        
        .status-badge.paused {
            background: rgba(245, 158, 11, 0.1);
            color: var(--status-paused);
            border-color: rgba(245, 158, 11, 0.25);
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.25);
        }

        .status-badge.completed {
            background: rgba(16, 185, 129, 0.1);
            color: var(--status-completed);
            border-color: rgba(16, 185, 129, 0.25);
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.25);
        }

        .status-badge.failed {
            background: rgba(239, 68, 68, 0.1);
            color: var(--status-failed);
            border-color: rgba(239, 68, 68, 0.25);
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.25);
        }

        .status-badge.cancelled {
            background: rgba(107, 114, 128, 0.1);
            color: var(--status-cancelled);
            border-color: rgba(107, 114, 128, 0.25);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: currentColor;
        }

        .status-badge.running .status-dot {
            animation: pulse 1.5s infinite alternate;
        }

        .agent-info {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-secondary);
        }

        .agent-name {
            font-weight: 600;
            color: var(--accent-purple);
        }

        .progress-container {
            margin-bottom: 1.5rem;
        }

        .progress-bar-bg {
            background: rgba(255, 255, 255, 0.05);
            height: 10px;
            border-radius: 9999px;
            width: 100%;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.03);
        }

        .progress-bar-fill {
            height: 100%;
            border-radius: 9999px;
            background: linear-gradient(to right, var(--accent-purple), var(--accent-cyan));
            width: 0%;
            transition: width 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 10px var(--accent-cyan);
        }

        .progress-labels {
            display: flex;
            justify-content: space-between;
            margin-top: 0.5rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }

        .progress-pct {
            font-weight: 600;
            color: var(--text-primary);
        }

        .controls-section {
            display: flex;
            gap: 1rem;
            margin-top: 1.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
            padding-top: 1.5rem;
        }

        .btn {
            flex: 1;
            padding: 0.75rem 1.5rem;
            border-radius: 0.5rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            font-size: 0.95rem;
            border: 1px solid transparent;
        }

        .btn-pause {
            background: rgba(245, 158, 11, 0.1);
            color: var(--status-paused);
            border-color: rgba(245, 158, 11, 0.2);
        }
        
        .btn-pause:hover:not(:disabled) {
            background: var(--status-paused);
            color: #000;
            box-shadow: 0 0 15px rgba(245, 158, 11, 0.4);
        }

        .btn-resume {
            background: rgba(16, 185, 129, 0.1);
            color: var(--status-completed);
            border-color: rgba(16, 185, 129, 0.2);
        }

        .btn-resume:hover:not(:disabled) {
            background: var(--status-completed);
            color: #000;
            box-shadow: 0 0 15px rgba(16, 185, 129, 0.4);
        }

        .btn-cancel {
            background: rgba(239, 68, 68, 0.1);
            color: var(--status-failed);
            border-color: rgba(239, 68, 68, 0.2);
        }

        .btn-cancel:hover:not(:disabled) {
            background: var(--status-failed);
            color: #fff;
            box-shadow: 0 0 15px rgba(239, 68, 68, 0.4);
        }

        .btn:disabled {
            opacity: 0.35;
            cursor: not-allowed;
        }

        .request-card {
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 1.25rem;
            border-radius: 0.75rem;
            margin-bottom: 0.5rem;
        }

        .request-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }

        .request-text {
            font-size: 1.05rem;
            color: var(--text-primary);
            line-height: 1.5;
        }

        .log-section {
            display: flex;
            flex-direction: column;
            height: 380px;
        }

        .log-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .log-title {
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
        }

        .connection-status {
            font-size: 0.75rem;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 0.35rem;
        }

        .connection-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background-color: var(--status-failed);
        }

        .connection-status.connected .connection-dot {
            background-color: var(--status-completed);
            box-shadow: 0 0 6px var(--status-completed);
        }

        .log-terminal {
            flex: 1;
            background: #040508;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 0.5rem;
            padding: 1rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.875rem;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 0.65rem;
            scroll-behavior: smooth;
        }

        .log-item {
            display: flex;
            flex-direction: column;
            border-left: 2px solid rgba(255, 255, 255, 0.1);
            padding-left: 0.75rem;
            transition: border-color 0.2s ease;
        }

        .log-item.coder { border-left-color: var(--accent-cyan); }
        .log-item.architect { border-left-color: var(--accent-purple); }
        .log-item.qa { border-left-color: #f59e0b; }
        .log-item.docs { border-left-color: #10b981; }

        .log-meta {
            display: flex;
            gap: 0.5rem;
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-bottom: 0.15rem;
        }

        .log-timestamp {
            color: rgba(255, 255, 255, 0.3);
        }

        .log-agent {
            font-weight: 600;
            text-transform: uppercase;
        }

        .log-message {
            color: #e2e8f0;
            line-height: 1.4;
            white-space: pre-wrap;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.75; }
            100% { transform: scale(1.05); opacity: 1; }
        }

        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.01);
        }
        ::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 999px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo-section">
                <div class="logo-glow"></div>
                <h1>AERIS Mission OS</h1>
            </div>
            <div class="job-id-badge" id="job-id-display">JOB ID: ...</div>
        </header>

        <div class="card request-card">
            <div class="request-label">Active Mission Objective</div>
            <div class="request-text" id="request-text">Loading mission objective...</div>
        </div>

        <div class="card" id="approval-card" style="display: none; border-color: #f59e0b; background: rgba(245, 158, 11, 0.04); margin-bottom: 0.5rem; animation: pulse 2s infinite alternate;">
            <div class="request-label" style="color: #f59e0b; display: flex; align-items: center; gap: 0.5rem; font-weight: 600;">
                <span>🛡️ Security Authorization Required</span>
            </div>
            <div style="margin-top: 0.75rem;">
                <p style="font-size: 0.95rem; line-height: 1.5; color: #f8fafc;">
                    This mission is paused because executing tool <strong id="approval-tool-name" style="color: #00f2fe;">...</strong> requires your explicit approval.
                </p>
                <div style="margin-top: 0.85rem; background: #040508; border: 1px solid rgba(255,255,255,0.05); padding: 0.75rem; border-radius: 0.5rem; font-family: 'JetBrains Mono', monospace; font-size: 0.825rem; overflow-x: auto;">
                    <span style="color: #94a3b8;">Arguments:</span>
                    <pre id="approval-tool-args" style="color: #00f2fe; margin-top: 0.25rem; white-space: pre-wrap; font-family: inherit;">{}</pre>
                </div>
                <p style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.85rem;">
                    Click the <strong>"Resume Mission"</strong> button below to authorize and execute this step, or <strong>"Abort Mission"</strong> to cancel the job.
                </p>
            </div>
        </div>

        <div class="card">
            <div class="status-section">
                <div class="status-badge" id="status-badge">
                    <div class="status-dot"></div>
                    <span id="status-text">loading</span>
                </div>
                <div class="agent-info">
                    <span>Active Agent:</span>
                    <span class="agent-name" id="agent-name">Brain</span>
                </div>
            </div>

            <div class="progress-container">
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" id="progress-fill"></div>
                </div>
                <div class="progress-labels">
                    <span>Step Execution Progress</span>
                    <span class="progress-pct" id="progress-pct">0%</span>
                </div>
            </div>

            <div class="controls-section">
                <button class="btn btn-pause" id="btn-pause" onclick="controlJob('pause')">
                    Pause Mission
                </button>
                <button class="btn btn-resume" id="btn-resume" onclick="controlJob('resume')" style="display:none;">
                    Resume Mission
                </button>
                <button class="btn btn-cancel" id="btn-cancel" onclick="controlJob('cancel')">
                    Abort Mission
                </button>
            </div>
        </div>

        <div class="card log-section">
            <div class="log-header">
                <div class="log-title">Live Execution Timeline</div>
                <div class="connection-status" id="connection-status">
                    <div class="connection-dot"></div>
                    <span id="connection-text">Connecting WebSocket</span>
                </div>
            </div>
            <div class="log-terminal" id="log-terminal">
                <!-- Log entries will be added here -->
            </div>
        </div>
    </div>

    <script>
        const jobId = window.location.pathname.split('/').pop();
        document.getElementById('job-id-display').textContent = jobId;

        let socket = null;
        let pollingInterval = null;
        let lastUpdated = 0;

        async function fetchInitialData() {
            try {
                const response = await fetch(`/api/jobs/${jobId}`);
                if (response.ok) {
                    const job = await response.json();
                    updateUI(job);
                } else {
                    document.getElementById('request-text').textContent = 'Error: Job not found.';
                }
            } catch (err) {
                console.error('Failed to fetch initial job state:', err);
            }
        }

        function updateUI(job) {
            if (!job) return;
            
            document.getElementById('request-text').textContent = job.request;
            
            const badge = document.getElementById('status-badge');
            badge.className = 'status-badge ' + job.status;
            document.getElementById('status-text').textContent = job.status;
            
            document.getElementById('agent-name').textContent = job.current_agent || 'Brain';
            
            const pct = job.progress || 0;
            document.getElementById('progress-fill').style.width = pct + '%';
            document.getElementById('progress-pct').textContent = pct + '%';

            // Update security approval card display
            const approvalCard = document.getElementById('approval-card');
            if (approvalCard) {
                if (job.requires_approval) {
                    approvalCard.style.display = 'block';
                    document.getElementById('approval-tool-name').textContent = job.tool_name_pending || 'unknown';
                    try {
                        document.getElementById('approval-tool-args').textContent = JSON.stringify(job.args_pending || {}, null, 2);
                    } catch(e) {
                        document.getElementById('approval-tool-args').textContent = '{}';
                    }
                } else {
                    approvalCard.style.display = 'none';
                }
            }
            
            const btnPause = document.getElementById('btn-pause');
            const btnResume = document.getElementById('btn-resume');
            const btnCancel = document.getElementById('btn-cancel');
            
            if (job.status === 'running' || job.status === 'queued') {
                btnPause.style.display = 'flex';
                btnResume.style.display = 'none';
                btnPause.disabled = false;
                btnCancel.disabled = false;
            } else if (job.status === 'paused') {
                btnPause.style.display = 'none';
                btnResume.style.display = 'flex';
                btnResume.disabled = false;
                btnCancel.disabled = false;
            } else {
                btnPause.style.display = 'flex';
                btnResume.style.display = 'none';
                btnPause.disabled = true;
                btnResume.disabled = true;
                btnCancel.disabled = true;
            }
            
            const terminal = document.getElementById('log-terminal');
            terminal.innerHTML = '';
            
            if (job.event_log && job.event_log.length > 0) {
                job.event_log.forEach(log => {
                    const item = document.createElement('div');
                    const agentClass = (log.agent || 'brain').toLowerCase();
                    item.className = `log-item ${agentClass}`;
                    
                    const meta = document.createElement('div');
                    meta.className = 'log-meta';
                    
                    const ts = document.createElement('span');
                    ts.className = 'log-timestamp';
                    ts.textContent = log.timestamp;
                    
                    const ag = document.createElement('span');
                    ag.className = 'log-agent';
                    ag.textContent = log.agent || 'Brain';
                    
                    meta.appendChild(ts);
                    meta.appendChild(ag);
                    
                    const msg = document.createElement('div');
                    msg.className = 'log-message';
                    msg.textContent = log.event;
                    
                    item.appendChild(meta);
                    item.appendChild(msg);
                    terminal.appendChild(item);
                });
                terminal.scrollTop = terminal.scrollHeight;
            }
        }

        async function controlJob(action) {
            try {
                const response = await fetch(`/api/jobs/${jobId}/${action}`, { method: 'POST' });
                if (response.ok) {
                    setTimeout(fetchInitialData, 200);
                }
            } catch (err) {
                console.error(`Failed to trigger ${action} control:`, err);
            }
        }

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/jobs`;
            
            socket = new WebSocket(wsUrl);
            
            socket.onopen = () => {
                const statusEl = document.getElementById('connection-status');
                statusEl.className = 'connection-status connected';
                document.getElementById('connection-text').textContent = 'Live Feed Connected';
                clearInterval(pollingInterval);
                pollingInterval = null;
            };
            
            socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'job_update' && data.job && data.job.job_id === jobId) {
                        updateUI(data.job);
                    }
                } catch (err) {
                    console.error('Error parsing websocket payload:', err);
                }
            };
            
            socket.onclose = () => {
                handleWebSocketDisconnect();
            };
            
            socket.onerror = () => {
                handleWebSocketDisconnect();
            };
        }

        function handleWebSocketDisconnect() {
            const statusEl = document.getElementById('connection-status');
            statusEl.className = 'connection-status';
            document.getElementById('connection-text').textContent = 'Reconnecting / Polling';
            
            if (!pollingInterval) {
                pollingInterval = setInterval(fetchInitialData, 1000);
            }
        }

        fetchInitialData();
        connectWebSocket();
        
        setInterval(() => {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type: 'ping' }));
            }
        }, 15000);
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


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


@app.websocket("/ws/voice")
async def voice_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("Voice stream WebSocket connected.")

    import json
    from services.voice_stream import is_silent, transcribe_audio, generate_voice_pcm
    from services.voice_profiles import get_voice_profile
    
    # State tracking
    audio_buffer = bytearray()
    silent_frames = 0
    has_spoken = False
    active_tts_task = None
    is_sleeping = False  # Always active/listening
    
    # Heuristics for VAD:
    # Assuming frontend sends audio in chunks of 4096 samples (8192 bytes = 0.256s at 16kHz)
    # 6 silent frames is ~1.5s
    SILENCE_LIMIT = 6

    # Inform frontend we are active
    await websocket.send_json({"type": "status_change", "is_sleeping": False})

    async def speak_response(text: str, agent_id: str):
        nonlocal active_tts_task
        try:
            profile = get_voice_profile(agent_id) if agent_id else {}
            voice = profile.get("voice", "hi-IN-MadhurNeural")
            pitch = profile.get("pitch", "+5Hz")
            rate = profile.get("rate", "+13%")
            
            # Send TTS start event
            await websocket.send_json({"type": "speak_start"})
            
            # Generate PCM chunks and send to client
            async for pcm_chunk in generate_voice_pcm(text, voice=voice, pitch=pitch, rate=rate):
                await websocket.send_bytes(pcm_chunk)
                await asyncio.sleep(0.001)
                
            # Send TTS end event
            await websocket.send_json({"type": "speak_end"})
        except asyncio.CancelledError:
            logger.info("TTS streaming task cancelled.")
            try:
                await websocket.send_json({"type": "speak_end", "reason": "interrupted"})
            except Exception:
                pass
        except Exception as e:
            logger.exception(f"Error in speak_response: {e}")
            try:
                await websocket.send_json({"type": "speak_end", "reason": "error"})
            except Exception:
                pass

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            
            if "bytes" in message:
                pcm_chunk = message["bytes"]
                
                # Check VAD silence
                silent = is_silent(pcm_chunk, threshold=1000)
                is_speaking = active_tts_task is not None and not active_tts_task.done()
                
                if silent:
                    if has_spoken:
                        silent_frames += 1
                        if silent_frames >= SILENCE_LIMIT:
                            logger.info(f"VAD: Silence limit reached. Transcribing {len(audio_buffer)} bytes...")
                            
                            samples_to_transcribe = bytes(audio_buffer)
                            audio_buffer.clear()
                            silent_frames = 0
                            has_spoken = False
                            
                            async def process_utterance(audio_bytes):
                                nonlocal active_tts_task
                                text = await transcribe_audio(audio_bytes)
                                if not text:
                                    logger.info("VAD: No speech recognized.")
                                    return
                                    
                                await websocket.send_json({"type": "transcription", "text": text})
                                
                                from services.guardian_mode import guardian_mode_manager
                                lower_text = text.lower()
                                
                                # Voice registration command handler
                                if "register my voice" in lower_text or "register owner voice" in lower_text or "record my voice profile" in lower_text:
                                    success = guardian_mode_manager.voice_matcher.register_voice(audio_bytes)
                                    if success:
                                        response_text = "Sir, your voice profile has been registered successfully as the owner."
                                    else:
                                        response_text = "Failed to register voice profile, Sir."
                                        
                                    await websocket.send_json({
                                        "type": "chat_response",
                                        "response": response_text,
                                        "intent": "guardian_voice_register",
                                        "agent": "Guardian"
                                    })
                                    if response_text:
                                        active_tts_task = asyncio.create_task(speak_response(response_text, "guardian"))
                                    return
                                
                                # Check if they are trying to unlock/deactivate or access restricted app/folder/website
                                is_deactivation_cmd = any(cmd in lower_text for cmd in ["unlock", "disable guardian", "guardian mode off", "productivity mode", "normal mode", "ye main hoon"])
                                
                                # Check if asking for blocked resources
                                is_blocked_resource = False
                                for app in guardian_mode_manager.config.get("blocked_apps", []):
                                    if app.lower().replace(".exe", "") in lower_text:
                                        is_blocked_resource = True
                                        break
                                for domain in guardian_mode_manager.config.get("blocked_domains", []):
                                    short_domain = domain.split(".")[0] if "." in domain else domain
                                    if short_domain in lower_text:
                                        is_blocked_resource = True
                                        break
                                for folder in guardian_mode_manager.config.get("protected_folders", []):
                                    if folder.lower() in lower_text:
                                        is_blocked_resource = True
                                        break
                                        
                                if guardian_mode_manager.is_active:
                                    if is_deactivation_cmd or is_blocked_resource:
                                        verified, voice_msg = await guardian_mode_manager.verify_voice_deactivation(audio_bytes)
                                        if verified:
                                            response_text = voice_msg
                                        else:
                                            # Voice mismatch - trigger violation
                                            guardian_mode_manager._handle_violation(
                                                viol_type="risky_action",
                                                target="Voice Authentication",
                                                details=f"Unauthorized user attempted voice unlock/access with command: '{text}'",
                                                hwnd=0
                                            )
                                            response_text = "Access Denied, Sir. Voice matching failed."
                                            
                                        await websocket.send_json({
                                            "type": "chat_response",
                                            "response": response_text,
                                            "intent": "guardian_violation" if not verified else "guardian_deactivation",
                                            "agent": "Guardian"
                                        })
                                        if response_text:
                                            active_tts_task = asyncio.create_task(speak_response(response_text, "guardian"))
                                        return
                                        
                                elif not guardian_mode_manager.is_active and is_blocked_resource:
                                    # If reference voice profile exists, check it
                                    if guardian_mode_manager.voice_matcher.has_reference():
                                        matched, confidence = await guardian_mode_manager.voice_matcher.compare_voice(audio_bytes)
                                        if not matched or confidence < 0.75:
                                            # Voice mismatch - enable Guardian Mode (guest mode) automatically!
                                            msg = guardian_mode_manager.enable_guardian_mode(method="auto_voice_mismatch")
                                            response_text = f"Security Alert: Voice mismatch detected. Guest Mode has been enabled automatically. Access to {text} is blocked."
                                            guardian_mode_manager._handle_violation(
                                                viol_type="app",
                                                target="WhatsApp" if "whatsapp" in lower_text else text,
                                                details=f"Voice mismatch on restricted resource request. Guest Mode enabled automatically.",
                                                hwnd=0
                                            )
                                            
                                            await websocket.send_json({
                                                "type": "chat_response",
                                                "response": response_text,
                                                "intent": "guardian_activation",
                                                "agent": "Guardian"
                                            })
                                            if response_text:
                                                active_tts_task = asyncio.create_task(speak_response(response_text, "guardian"))
                                            return

                                from memory.user_profile import user_profile_store
                                from hacker_brain import hacker_brain
                                is_hacker = user_profile_store.get_profile().get("hacker_mode", False)
                                current_brain = hacker_brain if is_hacker else brain
                                
                                result = await current_brain.process(text)
                                response_text = result.get("response", "")
                                intent = result.get("intent", "chat")
                                agent = result.get("agent", "Brain")
                                
                                await websocket.send_json({
                                    "type": "chat_response", 
                                    "response": response_text,
                                    "intent": intent,
                                    "agent": agent
                                })
                                
                                if response_text:
                                    active_tts_task = asyncio.create_task(speak_response(response_text, agent.lower().replace("agent", "")))
                                    
                            asyncio.create_task(process_utterance(samples_to_transcribe))
                else:
                    if is_speaking:
                        logger.info("VAD: User spoke while assistant speaking. Interrupting!")
                        if active_tts_task:
                            active_tts_task.cancel()
                            active_tts_task = None
                        await websocket.send_json({"type": "interrupted"})
                        
                    silent_frames = 0
                    has_spoken = True
                    if len(audio_buffer) < 960000:
                        audio_buffer.extend(pcm_chunk)
                        
            elif "text" in message:
                text_data = message["text"]
                try:
                    data = json.loads(text_data)
                    msg_type = data.get("type")
                    
                    if msg_type == "ping":
                        await websocket.send_json({"type": "pong"})
                        
                    elif msg_type == "interrupt":
                        logger.info("Client requested explicit interruption.")
                        if active_tts_task and not active_tts_task.done():
                            active_tts_task.cancel()
                            active_tts_task = None
                        await websocket.send_json({"type": "interrupted"})
                        audio_buffer.clear()
                        silent_frames = 0
                        has_spoken = False
                        
                    elif msg_type == "process_text":
                        text = data.get("text", "")
                        if active_tts_task and not active_tts_task.done():
                            active_tts_task.cancel()
                            active_tts_task = None
                            
                        from memory.user_profile import user_profile_store
                        from hacker_brain import hacker_brain
                        is_hacker = user_profile_store.get_profile().get("hacker_mode", False)
                        current_brain = hacker_brain if is_hacker else brain
                        
                        result = await current_brain.process(text)
                        response_text = result.get("response", "")
                        intent = result.get("intent", "chat")
                        agent = result.get("agent", "Brain")
                        
                        await websocket.send_json({
                            "type": "chat_response", 
                            "response": response_text,
                            "intent": intent,
                            "agent": agent
                        })
                        if response_text:
                            active_tts_task = asyncio.create_task(speak_response(response_text, agent.lower().replace("agent", "")))
                except json.JSONDecodeError:
                    pass
                    
    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected.")
    finally:
        if active_tts_task and not active_tts_task.done():
            active_tts_task.cancel()


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


@app.post("/api/overlay/implement")
async def api_overlay_implement():
    from services.screen_monitor import get_screen_monitor
    asyncio.create_task(get_screen_monitor().implement_last_suggestion())
    return {"success": True}


@app.post("/api/overlay/dismiss")
async def api_overlay_dismiss():
    from services.screen_monitor import get_screen_monitor
    get_screen_monitor().dismiss_overlay()
    return {"success": True}


# ── Screen Selection & Crop Region Endpoints ───────────────────────────────

@app.post("/api/screen/select")
async def api_screen_select():
    from services.screen_monitor import get_screen_monitor
    get_screen_monitor().trigger_selection()
    return {"success": True, "message": "Selection canvas triggered."}


@app.post("/api/screen/crop-box")
async def api_screen_crop_box(req: CropBoxRequest):
    from services.screen_monitor import get_screen_monitor
    monitor = get_screen_monitor()
    monitor.set_crop_box(req.x1, req.y1, req.x2, req.y2)
    # Immediately trigger on-demand analysis of the crop box
    asyncio.create_task(monitor.check_screen_and_suggest_now())
    return {
        "success": True, 
        "crop_box": [req.x1, req.y1, req.x2, req.y2],
        "message": "Crop box coordinates updated and analysis triggered."
    }


@app.post("/api/screen/query-region")
async def api_screen_query_region(req: QueryRegionRequest):
    """Capture a specific screen region and answer the user's question about it."""
    from services.screen_monitor import get_screen_monitor
    monitor = get_screen_monitor()
    result = await monitor.analyze_region_with_query(req.x1, req.y1, req.x2, req.y2, req.query)
    return result


@app.post("/api/screen/clear-crop")
async def api_screen_clear_crop():
    from services.screen_monitor import get_screen_monitor
    monitor = get_screen_monitor()
    monitor.clear_crop_box()
    return {"success": True, "message": "Crop box cleared, full screen monitoring restored."}


@app.get("/api/screen/status")
async def api_screen_status():
    from services.screen_monitor import get_screen_monitor
    monitor = get_screen_monitor()
    return {
        "is_monitoring": monitor.is_monitoring,
        "crop_box": monitor.crop_box,
        "pending_query": getattr(monitor, "_pending_query", None)
    }


# ── Guardian Mode Endpoints ──────────────────────────────────────────────────

class GuardianVerifyPinRequest(BaseModel):
    pin: str

class GuardianUpdateRequest(BaseModel):
    blocked_apps: Optional[list[str]] = None
    blocked_domains: Optional[list[str]] = None
    protected_folders: Optional[list[str]] = None
    allowed_apps: Optional[list[str]] = None
    warning_limit: Optional[int] = None
    lock_after_attempts: Optional[int] = None
    pin: Optional[str] = None
    secret_phrase: Optional[str] = None

@app.get("/api/guardian/status")
async def get_guardian_status():
    from services.guardian_mode import guardian_mode_manager
    return {
        "enabled": guardian_mode_manager.is_active,
        "overlay_active": guardian_mode_manager.overlay_active,
        "config": guardian_mode_manager.config.config,
        "attempt_counters": guardian_mode_manager.attempt_counters
    }

@app.post("/api/guardian/toggle")
async def toggle_guardian(request: dict[str, Any]):
    from services.guardian_mode import guardian_mode_manager
    action = request.get("action", "")
    code = request.get("code")
    
    if action == "enable":
        msg = guardian_mode_manager.enable_guardian_mode(method="api")
        return {"success": True, "message": msg}
    elif action == "disable":
        success, msg = guardian_mode_manager.disable_guardian_mode(code=code)
        return {"success": success, "message": msg}
    return {"success": False, "message": "Invalid action."}

@app.post("/api/guardian/verify-pin")
async def verify_guardian_pin(request: GuardianVerifyPinRequest):
    from services.guardian_mode import guardian_mode_manager
    pin = request.pin
    stored_pin = guardian_mode_manager.config.get("pin", "1234")
    if pin == stored_pin:
        guardian_mode_manager.disable_guardian_mode(bypass_auth=True)
        return {"success": True, "message": "PIN verified. Unlocked successfully."}
    return {"success": False, "message": "Incorrect PIN!"}

@app.post("/api/guardian/dismiss-overlay")
async def dismiss_guardian_overlay():
    from services.guardian_mode import guardian_mode_manager
    guardian_mode_manager.overlay_active = False
    return {"success": True}

@app.post("/api/guardian/update-config")
async def update_guardian_config(request: GuardianUpdateRequest):
    from services.guardian_mode import guardian_mode_manager
    updates = {k: v for k, v in request.dict().items() if v is not None}
    guardian_mode_manager.config.update(updates)
    return {"success": True, "config": guardian_mode_manager.config.config}

@app.get("/api/guardian/logs")
async def get_guardian_logs():
    from services.guardian_mode import guardian_mode_manager
    return {"logs": guardian_mode_manager.audit_logger.get_logs()}


@app.post("/api/overlay/query")
async def api_overlay_query(request: OverlayQueryRequest):
    from services.screen_monitor import get_screen_monitor
    import base64
    monitor = get_screen_monitor()
    
    # 1. Load active suggestion context if any
    suggestion = ""
    if monitor._last_suggestion:
        suggestion = monitor._last_suggestion.get("suggestion", "")
        
    # 2. Check if a cropped screenshot is available
    img_b64 = None
    temp_dir = Path(settings.DATA_DIR) / "temp"
    temp_path = temp_dir / "monitor_screenshot.png"
    if not temp_path.exists():
        temp_path = temp_dir / "on_demand_screenshot.png"
        
    if temp_path.exists():
        try:
            with open(temp_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            pass
            
    # 3. Formulate prompt
    if img_b64:
        prompt = f"""
The user is looking at the selected area of their screen.
We previously suggested: "{suggestion}".
The user is now asking this follow-up question: "{request.text}".

Look at the image of their screen selection and answer their question clearly, concisely, and directly in Hindi or Hinglish. Keep it short and readable, fitting within a small card.
"""
        from ai_engine import ai_engine
        raw_resp = await ai_engine.vision(prompt, img_b64)
        answer = raw_resp.strip()
    else:
        # Fallback to text only
        prompt = f"""
The user is looking at a screen suggestion: "{suggestion}".
They ask: "{request.text}".
Provide a concise, direct answer in Hinglish. Keep it short.
"""
        from ai_engine import ai_engine
        answer = await ai_engine.chat([{"role": "user", "content": prompt}])
        
    return {"success": True, "response": answer}


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

    global_state_manager.current_hud = "codepipeline"
    global_state_manager.active_pipeline_id = pipeline_id
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
    finally:
        await asyncio.sleep(5)
        if global_state_manager.current_hud == "codepipeline":
            global_state_manager.current_hud = None
        if global_state_manager.active_pipeline_id == pipeline_id:
            global_state_manager.active_pipeline_id = None


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


@app.get("/api/mcp/servers")
async def get_mcp_servers():
    try:
        from starlette.concurrency import run_in_threadpool
        from tools.mcp_installer import list_connected_servers
        res_str = await run_in_threadpool(list_connected_servers)
        import json
        return json.loads(res_str)
    except Exception as e:
        logger.exception("MCP list endpoint error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/servers")
async def mcp_servers_connect(req: MCPConnectRequest):
    return await mcp_connect(req)


@app.delete("/api/mcp/servers/{name}")
async def mcp_servers_disconnect(name: str):
    try:
        from starlette.concurrency import run_in_threadpool
        from tools.mcp_installer import disconnect_mcp_server
        res_str = await run_in_threadpool(disconnect_mcp_server, server_name=name)
        import json
        return json.loads(res_str)
    except Exception as e:
        logger.exception("MCP disconnect endpoint error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mcp/servers/{name}/reconnect")
async def mcp_servers_reconnect(name: str):
    try:
        from starlette.concurrency import run_in_threadpool
        from tools.mcp_bridge import get_mcp_registry
        
        def do_reconnect():
            registry = get_mcp_registry()
            success = registry.reconnect_server(name)
            if success:
                conn = registry._servers.get(name)
                if conn and conn.connected:
                    return {"success": True, "message": f"Successfully reconnected to MCP server '{name}'."}
            return {"success": False, "error": f"Failed to reconnect to MCP server '{name}'."}

        return await run_in_threadpool(do_reconnect)
    except Exception as e:
        logger.exception("MCP reconnect endpoint error")
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
    base = Path(settings.WORKSPACE_DIR).resolve()
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


# ── Assembly and Voice Multi-Agent Endpoints ───────────────────────────────

class AgentSpeakRequest(BaseModel):
    agent_id: str
    text: str


@app.get("/api/assembly/stream")
async def api_assembly_stream():
    """Streams Server-Sent Events for the agent assembly sequence."""
    from fastapi.responses import StreamingResponse
    from services.assembly_engine import AssemblyEngine
    engine = AssemblyEngine()
    return StreamingResponse(
        engine.run_assembly(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/disassembly/stream")
async def api_disassembly_stream():
    """Streams Server-Sent Events for the agent disassembly sequence."""
    from fastapi.responses import StreamingResponse
    from services.assembly_engine import AssemblyEngine
    engine = AssemblyEngine()
    return StreamingResponse(
        engine.run_disassembly(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/voice/agent-speak")
async def api_agent_speak(req: AgentSpeakRequest):
    """Speaks text using a specific agent's voice profile."""
    try:
        from services.voice_profiles import get_voice_profile
        from services.texttospeech import text_to_speech
        import threading
        
        profile = get_voice_profile(req.agent_id)
        voice = profile.get("voice", "hi-IN-MadhurNeural")
        pitch = profile.get("pitch", "+0Hz")
        rate = profile.get("rate", "+0%")
        
        # Fire in a background thread to return response immediately
        t = threading.Thread(
            target=text_to_speech,
            args=(req.text, voice, 3, 300, pitch, rate),
            daemon=True,
            name=f"aeris-agent-{req.agent_id}-speak"
        )
        t.start()
        return {"success": True, "agent_id": req.agent_id, "voice": voice, "message": f"Speaking in {req.agent_id}'s voice."}
    except Exception as e:
        logger.exception("Agent speak error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/collaboration/stream")
async def api_collaboration_stream(task_id: str):
    """Streams real-time collaboration events for a given task_id."""
    from services.collaboration_events import collaboration_bus
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        collaboration_bus.stream(task_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


_last_net_bytes = 0
_last_net_time = 0

@app.get("/api/diagnostics/telemetry")
async def get_diagnostics_telemetry():
    global _last_net_bytes, _last_net_time
    import time
    
    cpu = 0.0
    ram = 0.0
    disk = 0.0
    net_rate = 0.0
    
    try:
        try:
            import psutil
        except ImportError:
            psutil = None
            
        cpu = psutil.cpu_percent(interval=None) if psutil else 15.0
        mem = psutil.virtual_memory() if psutil else None
        ram = mem.percent if mem else 40.0
        
        import shutil
        total, used, free = shutil.disk_usage(str(settings.WORKSPACE_DIR))
        disk = round((used / total) * 100, 1)
        
        if psutil:
            io = psutil.net_io_counters()
            total_bytes = io.bytes_sent + io.bytes_recv
            now = time.time()
            if _last_net_time > 0:
                elapsed = now - _last_net_time
                if elapsed > 0:
                    net_rate = (total_bytes - _last_net_bytes) / elapsed / 1024.0
            
            _last_net_bytes = total_bytes
            _last_net_time = now
        else:
            import random
            net_rate = round(100.0 + random.random() * 800.0, 1)
    except Exception as e:
        logger.warning(f"Error fetching telemetry API: {e}")
        
    return {
        "cpu_percent": round(cpu, 1),
        "ram_used_percent": round(ram, 1),
        "disk_used_percent": round(disk, 1),
        "net_data_rate_kb": round(net_rate, 1)
    }


class CodeDiagnoseRequest(BaseModel):
    path: str = ""


@app.post("/api/diagnostics/system")
async def api_diagnose_system():
    from tools.diagnostics_tools import diagnose_system
    try:
        report = diagnose_system()
        return {"success": True, "report": report}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/diagnostics/code")
async def api_diagnose_code(req: CodeDiagnoseRequest):
    from tools.diagnostics_tools import diagnose_code
    try:
        report = diagnose_code(req.path)
        return {"success": True, "report": report}
    except Exception as e:
        return {"success": False, "error": str(e)}


class AgentDiagnoseRequest(BaseModel):
    agent_name: str


@app.post("/api/diagnostics/agent")
async def api_diagnose_agent(req: AgentDiagnoseRequest):
    from tools.diagnostics_tools import diagnose_agent
    try:
        report = await diagnose_agent(req.agent_name)
        return {"success": True, "report": report}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Repair Agent Endpoints ─────────────────────────────────────────────────

class RepairAnalyzeRequest(BaseModel):
    description: str
    target_path: Optional[str] = None

class RepairRunRequest(BaseModel):
    repair_plan: dict
    dry_run: bool = False
    auto_apply: bool = False

class MemoryNoteRequest(BaseModel):
    note: str

async def _run_repair_job(job_id: str, plan: Any):
    from services.job_manager import get_job_manager
    from services.collaboration_events import collaboration_bus
    manager = get_job_manager()
    manager.update_job(job_id, status="running", event="Starting repair process...")
    try:
        # Get RepairAgent instance from brain
        repair_agent = brain.agents.get("repair")
        if not repair_agent:
            raise ValueError("RepairAgent not found in brain.")
        
        # Emit event
        await collaboration_bus.emit(plan.repair_id, "info", {"message": "Applying repairs..."})
        
        result = await repair_agent.execute(plan)
        
        # Emit event
        await collaboration_bus.emit(plan.repair_id, "complete", {"message": "Repair completed.", "result": result.to_dict()})
        
        manager.update_job(
            job_id, 
            status="completed" if result.success else "failed", 
            progress=100,
            final_result=result.to_dict(),
            event="Repair completed successfully." if result.success else f"Repair failed: {result.report}"
        )
    except Exception as e:
        logger.exception("Error executing repair background job")
        await collaboration_bus.emit(plan.repair_id, "error", {"message": str(e)})
        manager.update_job(job_id, status="failed", progress=100, error=str(e), event=f"Repair failed: {e}")

@app.post("/api/repair/analyze")
async def api_repair_analyze(req: RepairAnalyzeRequest):
    repair_agent = brain.agents.get("repair")
    if not repair_agent:
        raise HTTPException(status_code=500, detail="RepairAgent not found in brain.")
    try:
        plan = await repair_agent.think(req.description, {"target_path": req.target_path})
        return plan.to_dict()
    except Exception as e:
        logger.exception("Error analyzing repair request")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/repair/run")
async def api_repair_run(req: RepairRunRequest):
    from services.job_manager import get_job_manager
    from agents.repair_agent import RepairPlan, RepairIssue, RepairFix
    
    rplan = req.repair_plan
    try:
        plan = RepairPlan(
            repair_id=rplan["repair_id"],
            issues=[RepairIssue(**i) for i in rplan.get("issues", [])],
            proposed_fixes=[RepairFix(**f) for f in rplan.get("proposed_fixes", [])],
            risk_level=rplan.get("risk_level", "low"),
            dry_run=req.dry_run,
            auto_apply=req.auto_apply,
            requires_approval=rplan.get("requires_approval", True),
            explanation=rplan.get("explanation", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid repair plan payload: {e}")
    
    manager = get_job_manager()
    job = manager.create_job(f"Repair Execution: {plan.repair_id}")
    job_id = job["job_id"]
    
    task = asyncio.create_task(_run_repair_job(job_id, plan))
    manager._register_task(job_id, task)
    
    return {"success": True, "repair_id": plan.repair_id, "job_id": job_id}

@app.get("/api/repair/status/{repair_id}")
async def api_repair_status(repair_id: str):
    repair_agent = brain.agents.get("repair")
    if not repair_agent:
        raise HTTPException(status_code=500, detail="RepairAgent not found in brain.")
    status = repair_agent.get_status(repair_id)
    if not status:
        raise HTTPException(status_code=404, detail="Repair status not found.")
    return status

@app.get("/api/repair/history")
async def api_repair_history():
    repair_agent = brain.agents.get("repair")
    if not repair_agent:
        raise HTTPException(status_code=500, detail="RepairAgent not found in brain.")
    return repair_agent.get_history()

@app.get("/api/repair/memory")
async def api_repair_memory():
    repair_agent = brain.agents.get("repair")
    if not repair_agent:
        raise HTTPException(status_code=500, detail="RepairAgent not found in brain.")
    return repair_agent.get_memory()

@app.post("/api/repair/memory/note")
async def api_repair_memory_note(req: MemoryNoteRequest):
    repair_agent = brain.agents.get("repair")
    if not repair_agent:
        raise HTTPException(status_code=500, detail="RepairAgent not found in brain.")
    repair_agent.add_memory_note(req.note)
    return {"success": True}


# ── WebWeaver HUD Endpoints ──────────────────────────────────────────────────

class WebWeaverNodeRequest(BaseModel):
    id: str
    label: str
    type: str = "host"
    ip: Optional[str] = None
    status: str = "online"
    parent_id: Optional[str] = None
    link_type: str = "connection"
    port: Optional[int] = None


@app.get("/api/webweaver/graph")
async def get_webweaver_graph():
    import json
    graph_path = settings.DATA_DIR / "webweaver_graph.json"
    if not graph_path.exists():
        graph_path.parent.mkdir(parents=True, exist_ok=True)
        default_graph = {
            "nodes": [
                {"id": "aeris_brain", "label": "AERIS Brain", "type": "host", "ip": "127.0.0.1", "status": "online"},
                {"id": "api_gateway", "label": "FastAPI Gateway", "type": "service", "status": "online"}
            ],
            "links": [
                {"source": "aeris_brain", "target": "api_gateway", "type": "connection", "port": 8000}
            ]
        }
        graph_path.write_text(json.dumps(default_graph, indent=2))
        return default_graph
    try:
        return json.loads(graph_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to read webweaver graph: {e}")
        return {"nodes": [], "links": []}


@app.post("/api/webweaver/node")
async def add_webweaver_node(req: WebWeaverNodeRequest):
    import json
    graph_path = settings.DATA_DIR / "webweaver_graph.json"
    
    # Ensure file exists
    await get_webweaver_graph()
    
    try:
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        
        # Check if node already exists, if so update it
        node_exists = False
        for node in graph["nodes"]:
            if node["id"] == req.id:
                node["label"] = req.label
                node["type"] = req.type
                if req.ip:
                    node["ip"] = req.ip
                node["status"] = req.status
                node_exists = True
                break
        
        if not node_exists:
            graph["nodes"].append({
                "id": req.id,
                "label": req.label,
                "type": req.type,
                "ip": req.ip,
                "status": req.status
            })
            
        # Add link if parent_id is specified
        if req.parent_id:
            link_exists = False
            for link in graph["links"]:
                if link["source"] == req.parent_id and link["target"] == req.id:
                    link["type"] = req.link_type
                    if req.port:
                        link["port"] = req.port
                    link_exists = True
                    break
            if not link_exists:
                graph["links"].append({
                    "source": req.parent_id,
                    "target": req.id,
                    "type": req.link_type,
                    "port": req.port
                })
                
        graph_path.write_text(json.dumps(graph, indent=2))
        return {"success": True, "graph": graph}
    except Exception as e:
        logger.exception("Failed to write to webweaver graph")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/webweaver/clear")
async def clear_webweaver_graph():
    import json
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
        return {"success": True, "graph": default_graph}
    except Exception as e:
        logger.exception("Failed to clear webweaver graph")
        raise HTTPException(status_code=500, detail=str(e))



@app.websocket("/ws/jobs")
async def jobs_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    from services.job_manager import get_job_manager
    mgr = get_job_manager()
    mgr.register_websocket(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if isinstance(data, dict) and data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        mgr.deregister_websocket(websocket)
    except Exception:
        mgr.deregister_websocket(websocket)


@app.websocket("/ws/{path:path}")
async def ws_catchall(websocket: WebSocket, path: str):
    await websocket.close(code=1008, reason=f"Unknown WebSocket endpoint: /ws/{path}")


# Serve static files from Next.js export in unified mode
from fastapi.responses import FileResponse
_DIST_DIR = Path(__file__).resolve().parent / "dist"

if _DIST_DIR.exists():
    _NEXT_DIR = _DIST_DIR / "_next"
    if _NEXT_DIR.exists():
        app.mount("/_next", StaticFiles(directory=str(_NEXT_DIR)), name="next_assets")
    
    @app.get("/{catchall:path}")
    async def serve_spa(catchall: str):
        # Do not intercept backend paths
        if (
            catchall.startswith("api")
            or catchall.startswith("ws")
            or catchall.startswith("images")
            or catchall.startswith("phantom")
        ):
            raise HTTPException(status_code=404, detail="Not Found")
            
        file_path = _DIST_DIR / catchall
        if file_path.is_file():
            return FileResponse(str(file_path))
            
        html_path = _DIST_DIR / f"{catchall}.html"
        if html_path.is_file():
            return FileResponse(str(html_path))
            
        index_path = _DIST_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
            
        raise HTTPException(status_code=404, detail="Not Found")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting server on port %s", settings.API_PORT)
    uvicorn.run(
        "api:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=True,
        reload_excludes=["*.json", "*.md", "*.log", "data/*", "data/**/*", "memory.json", "hacker_memory.json"]
    )
