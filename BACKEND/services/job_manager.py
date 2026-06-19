import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
import asyncio

logger = logging.getLogger("aeris.job_manager")

class BackgroundJobManager:
    def __init__(self):
        from config import settings
        self.file_path = Path(settings.BASE_DIR) / "data" / "background_jobs.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._websocket_clients = set()

    def _load_jobs(self) -> List[Dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_jobs(self, jobs: List[Dict[str, Any]]):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(jobs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save background jobs: {e}")

    def _inject_approval_state(self, job: dict) -> dict:
        """Helper to dynamically inject pending approval details if this job is paused for security check."""
        if not job or job.get("status") != "paused":
            return job
        
        from config import settings
        pending_file = Path(settings.BASE_DIR) / "data" / "pending_approval.json"
        if pending_file.exists():
            try:
                with open(pending_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    if state.get("task_id") == job.get("job_id"):
                        job = dict(job) # Copy to avoid mutating underlying dict
                        job["requires_approval"] = True
                        job["tool_name_pending"] = state.get("tool_name_pending")
                        job["args_pending"] = state.get("args_pending")
            except Exception:
                pass
        return job

    def register_websocket(self, websocket):
        self._websocket_clients.add(websocket)
        logger.info(f"[JobManager] Registered websocket client. Total: {len(self._websocket_clients)}")

    def deregister_websocket(self, websocket):
        self._websocket_clients.discard(websocket)
        logger.info(f"[JobManager] Deregistered websocket client. Total: {len(self._websocket_clients)}")

    async def broadcast_job_update(self, job: dict):
        if not self._websocket_clients:
            return
        import json
        job = self._inject_approval_state(job)
        payload = {"type": "job_update", "job": job}
        message = json.dumps(payload)
        
        disconnected = []
        for ws in list(self._websocket_clients):
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        
        for ws in disconnected:
            self._websocket_clients.discard(ws)

    def _broadcast_sync(self, job: dict):
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(self.broadcast_job_update(job))
        except RuntimeError:
            pass # No running loop

    def create_job(self, request: str) -> Dict[str, Any]:
        now = datetime.now()
        job_id = f"job_{int(time.time())}"
        job = {
            "job_id": job_id,
            "request": request,
            "status": "queued",
            "current_agent": "Brain",
            "progress": 0,
            "started_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "completed_at": None,
            "partial_results": [],
            "final_result": None,
            "error": None,
            "event_log": [
                {
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "event": "Job created and queued.",
                    "agent": "Brain"
                }
            ]
        }
        jobs = self._load_jobs()
        jobs.append(job)
        self._save_jobs(jobs)
        logger.info(f"Created background job {job_id} for request: '{request[:60]}...'")
        self._broadcast_sync(job)
        return job

    def update_job(self, job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        jobs = self._load_jobs()
        updated_job = None
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        for job in jobs:
            if job["job_id"] == job_id:
                # Update any matching field
                for field in ["status", "current_agent", "progress", "final_result", "error"]:
                    if field in kwargs and kwargs[field] is not None:
                        job[field] = kwargs[field]
                
                # Append to partial results if provided
                if "partial_result" in kwargs and kwargs["partial_result"] is not None:
                    if isinstance(job.get("partial_results"), list):
                        job["partial_results"].append(kwargs["partial_result"])
                    else:
                        job["partial_results"] = [kwargs["partial_result"]]

                # Set completed_at if status completes/fails/cancels
                if "status" in kwargs and kwargs["status"] in ("completed", "failed", "cancelled"):
                    job["completed_at"] = timestamp

                # Log event
                if "event" in kwargs and kwargs["event"] is not None:
                    job["event_log"].append({
                        "timestamp": timestamp,
                        "event": kwargs["event"],
                        "agent": job.get("current_agent", "Brain")
                    })

                job["updated_at"] = timestamp
                updated_job = job
                break

        if updated_job:
            self._save_jobs(jobs)
            self._broadcast_sync(updated_job)
        return updated_job

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        jobs = self._load_jobs()
        for job in jobs:
            if job["job_id"] == job_id:
                return self._inject_approval_state(job)
        return None

    def list_active_jobs(self) -> List[Dict[str, Any]]:
        jobs = self._load_jobs()
        return [self._inject_approval_state(job) for job in jobs if job["status"] in ("queued", "running", "paused")]

    def list_all_jobs(self) -> List[Dict[str, Any]]:
        return [self._inject_approval_state(job) for job in self._load_jobs()]

    def cancel_job(self, job_id: str) -> bool:
        task = self._active_tasks.get(job_id)
        if task:
            task.cancel()
            self.update_job(job_id, status="cancelled", event="User requested cancellation.")
            return True
        else:
            job = self.get_job(job_id)
            if job and job["status"] in ("queued", "running", "paused"):
                self.update_job(job_id, status="cancelled", event="User cancelled stagnant/stuck job.")
                return True
        return False

    def pause_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if job and job["status"] in ("running", "queued"):
            self.update_job(job_id, status="paused", event="Job paused by user.")
            return True
        return False

    def resume_job(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if job and job["status"] == "paused":
            self.update_job(job_id, status="queued", event="Job resumed by user.")
            return True
        return False

    def _register_task(self, job_id: str, task: asyncio.Task):
        self._active_tasks[job_id] = task

    def _deregister_task(self, job_id: str):
        if job_id in self._active_tasks:
            del self._active_tasks[job_id]

# Singleton instance
_job_manager: Optional[BackgroundJobManager] = None

def get_job_manager() -> BackgroundJobManager:
    global _job_manager
    if _job_manager is None:
        _job_manager = BackgroundJobManager()
    return _job_manager
