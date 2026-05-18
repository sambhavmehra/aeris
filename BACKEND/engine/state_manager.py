"""
AERIS — Enhanced State Manager
Full step-level tracking with timing, WebSocket broadcast support,
and real-time execution awareness.
"""
from enum import Enum
import uuid
import time
import asyncio
from typing import Dict, Any, List, Optional, Callable
import json
import logging

logger = logging.getLogger("AerisState")


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"
    WAITING_USER = "waiting_user"


class StepState:
    """Tracks a single execution step within a task."""

    def __init__(self, step_id: str, description: str, tool_name: str = ""):
        self.step_id = step_id
        self.description = description
        self.tool_name = tool_name
        self.status = ExecutionStatus.PENDING
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.retry_count = 0
        self.started_at: Optional[float] = None
        self.finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "description": self.description,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "result": str(self.result)[:300] if self.result else None,
            "error": self.error,
            "retry_count": self.retry_count,
            "duration_ms": round((self.finished_at - self.started_at) * 1000, 1)
            if self.started_at and self.finished_at
            else None,
        }


class TaskState:
    """Tracks the full lifecycle of an autonomous task."""

    def __init__(self, task_name: str, description: str):
        self.task_id = str(uuid.uuid4())
        self.task_name = task_name
        self.description = description
        self.status = ExecutionStatus.PENDING
        self.logs: List[str] = []
        self.error: Optional[str] = None
        self.retry_count = 0
        self.result: Any = None
        self.created_at = time.time()
        self.updated_at = time.time()
        # Step-level tracking
        self.steps: List[StepState] = []
        self.current_step_index: int = 0
        # What AERIS is actively doing right now
        self.current_action: str = "Initializing..."

    def add_step(self, step_id: str, description: str, tool_name: str = "") -> StepState:
        step = StepState(step_id, description, tool_name)
        self.steps.append(step)
        return step

    def update_action(self, action: str):
        """Update the human-readable current action status."""
        self.current_action = action
        self.updated_at = time.time()

    def update_status(
        self,
        status: ExecutionStatus,
        error: Optional[str] = None,
        log: Optional[str] = None,
        result: Any = None,
    ):
        self.status = status
        self.updated_at = time.time()
        if error:
            self.error = error
        if log:
            self.logs.append(f"[{time.strftime('%H:%M:%S')}] {log}")
        if result is not None:
            self.result = result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_name": self.task_name,
            "description": self.description,
            "status": self.status.value,
            "current_action": self.current_action,
            "logs": self.logs[-20:],  # Last 20 logs
            "error": self.error,
            "retry_count": self.retry_count,
            "result": str(self.result)[:500] if self.result else None,
            "steps": [s.to_dict() for s in self.steps],
            "current_step_index": self.current_step_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "elapsed_ms": round((self.updated_at - self.created_at) * 1000, 1),
        }


class StateManager:
    """Live execution state manager for AERIS.
    Provides real-time status feedback via observer callbacks (for WebSocket streaming)."""

    def __init__(self):
        self._tasks: Dict[str, TaskState] = {}
        self._current_task_id: Optional[str] = None
        self._observers: List[Callable] = []  # sync callbacks
        self._async_observers: List[Callable] = []  # async callbacks (WebSocket)
        self.global_current_action: str = "Idle"

    # ── Observers ────────────────────────────────────────────────────
    def register_observer(self, callback: Callable):
        """Register a sync callback to be notified on state changes."""
        self._observers.append(callback)

    def register_async_observer(self, callback: Callable):
        """Register an async callback (e.g., WebSocket send)."""
        self._async_observers.append(callback)

    def unregister_async_observer(self, callback: Callable):
        if callback in self._async_observers:
            self._async_observers.remove(callback)

    def _notify_observers(self, task: TaskState):
        payload = task.to_dict()
        for callback in self._observers:
            try:
                callback(payload)
            except Exception:
                pass
        # Fire-and-forget async observers
        for async_cb in self._async_observers:
            try:
                asyncio.get_event_loop().create_task(async_cb(payload))
            except RuntimeError:
                pass  # No event loop running

    def set_global_action(self, action: str):
        """Update the global real-time action status and broadcast to WebSocket."""
        self.global_current_action = action
        payload = {"type": "global_action", "action": action}
        for async_cb in self._async_observers:
            try:
                asyncio.get_event_loop().create_task(async_cb(payload))
            except RuntimeError:
                pass  # No loop

    # ── Task CRUD ────────────────────────────────────────────────────
    def create_task(self, task_name: str, description: str) -> TaskState:
        task = TaskState(task_name, description)
        self._tasks[task.task_id] = task
        self._current_task_id = task.task_id
        logger.info(f"Task created: {task.task_id} — {task_name}")
        self._notify_observers(task)
        
        # Emit to Nervous System EventBus
        try:
            from core.nervous.event_system import get_event_system, ExecutionEvent, EventType
            event_sys = get_event_system()
            evt = ExecutionEvent(
                event_type=EventType.EXECUTION_TASK_QUEUED,
                source="StateManager",
                action_id=task.task_id,
                data={"task_name": task_name, "description": description},
                severity="info"
            )
            asyncio.get_event_loop().create_task(event_sys.emit(evt))
        except Exception as e:
            logger.debug(f"Failed to emit nervous system creation event: {e}")
            
        return task

    def get_task(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def get_current_task(self) -> Optional[TaskState]:
        if self._current_task_id:
            return self._tasks.get(self._current_task_id)
        return None

    def update_task(
        self,
        task_id: str,
        status: ExecutionStatus,
        error: Optional[str] = None,
        log: Optional[str] = None,
        result: Any = None,
        action: Optional[str] = None,
    ):
        task = self.get_task(task_id)
        if task:
            task.update_status(status, error=error, log=log, result=result)
            if action:
                task.update_action(action)
            self._notify_observers(task)
            
            # Emit to Nervous System EventBus
            try:
                from core.nervous.event_system import get_event_system, ExecutionEvent, EventType
                event_sys = get_event_system()
                
                # Map state to event type
                event_type = EventType.EXECUTION_TASK_STARTED
                if status == ExecutionStatus.SUCCESS:
                    event_type = EventType.EXECUTION_TASK_COMPLETED
                elif status == ExecutionStatus.FAILED:
                    event_type = EventType.EXECUTION_TASK_FAILED
                elif status == ExecutionStatus.RETRYING:
                    event_type = EventType.EXECUTION_TASK_RETRIED
                
                evt = ExecutionEvent(
                    event_type=event_type,
                    source="StateManager",
                    action_id=task.task_id,
                    data={"status": status.value, "log": log, "action": action},
                    severity="error" if status == ExecutionStatus.FAILED else "info"
                )
                asyncio.get_event_loop().create_task(event_sys.emit(evt))
            except Exception as e:
                logger.debug(f"Failed to emit nervous system event: {e}")

    def increment_retry(self, task_id: str):
        task = self.get_task(task_id)
        if task:
            task.retry_count += 1
            task.update_status(
                ExecutionStatus.RETRYING,
                log=f"Retrying task... attempt {task.retry_count}",
            )
            self._notify_observers(task)

    def get_all_tasks(self) -> List[Dict[str, Any]]:
        return [task.to_dict() for task in self._tasks.values()]

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        return [
            task.to_dict()
            for task in self._tasks.values()
            if task.status in (
                ExecutionStatus.RUNNING, 
                ExecutionStatus.RETRYING, 
                ExecutionStatus.PENDING, 
                ExecutionStatus.WAITING_USER
            )
        ]


# Global Singleton State Manager for OS processes
global_state_manager = StateManager()
