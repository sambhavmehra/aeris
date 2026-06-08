"""
AERIS Autonomous Task Scheduler & Reminders Engine
===================================================
Background asyncio workers that persist, check, and execute
user-scheduled tasks or AI-scheduled follow-ups automatically.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import random
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ai_engine import ai_engine
from config import settings

logger = logging.getLogger("aeris.scheduler")

class TaskScheduler:
    def __init__(self):
        self.file_path = Path(settings.BASE_DIR) / "data" / "scheduled_tasks.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None

    def _load_tasks(self) -> list[dict]:
        if not self.file_path.exists():
            return []
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_tasks(self, tasks: list[dict]):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(tasks, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save scheduled tasks: {e}")

    async def schedule(self, instruction: str, time_spec: str) -> dict:
        """Parse natural language time spec and add to task database."""
        now = datetime.now()
        prompt = (
            f"You are the time parser for AERIS scheduler.\n"
            f"Current local time: {now.strftime('%Y-%m-%d %H:%M:%S')} (weekday: {now.strftime('%A')}).\n"
            f"Parse the time specification: '{time_spec}'\n\n"
            f"Understand Hindi/Hinglish (like '30 min baad', 'shaam 6 baje', 'aaj raat') and English (like 'in 1 hour', 'tomorrow at 9am').\n"
            f"Calculate the target date and time when the task should run.\n"
            f"Return ONLY a JSON object with 'target_datetime' (format: YYYY-MM-DD HH:MM:SS) and 'delay_seconds' (integer delay from now)."
        )

        target_str = None
        try:
            raw = await ai_engine.chat(
                messages=[
                    {"role": "system", "content": "You are a precise time parser. Respond ONLY with valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            data = json.loads(raw.strip())
            target_str = data.get("target_datetime")
            # Validate format
            datetime.strptime(target_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            logger.warning(f"Failed to parse time_spec '{time_spec}' using LLM: {e}. Falling back to 60 seconds.")
            target_time = now + timedelta(seconds=60)
            target_str = target_time.strftime("%Y-%m-%d %H:%M:%S")

        # Deduplication guard: check if identical pending task is already scheduled around the same time (within 60 seconds)
        tasks = self._load_tasks()
        try:
            target_dt = datetime.strptime(target_str, "%Y-%m-%d %H:%M:%S")
            for t in tasks:
                if t.get("status") == "pending" and t.get("instruction") == instruction:
                    existing_dt = datetime.strptime(t["scheduled_time"], "%Y-%m-%d %H:%M:%S")
                    if abs((existing_dt - target_dt).total_seconds()) < 60:
                        logger.info(f"Duplicate task detected: '{instruction}' already scheduled at {t['scheduled_time']}. Skipping.")
                        return t
        except Exception as e:
            logger.warning(f"Error checking duplicate tasks: {e}")

        task_id = f"sch_{int(time.time())}_{random.randint(1000, 9999)}"
        new_task = {
            "task_id": task_id,
            "instruction": instruction,
            "scheduled_time": target_str,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "pending"
        }

        tasks.append(new_task)
        self._save_tasks(tasks)

        logger.info(f"Scheduled task {task_id} successfully: '{instruction}' at {target_str}")
        return new_task

    def list_tasks(self, status: Optional[str] = None) -> list[dict]:
        """List all scheduled tasks, optionally filtered by status (pending, completed, failed, cancelled)."""
        tasks = self._load_tasks()
        if status:
            return [t for t in tasks if t.get("status") == status.lower()]
        return tasks

    def cancel_task(self, task_spec: str) -> bool:
        """Cancel a pending scheduled task by ID or instruction matching."""
        tasks = self._load_tasks()
        found = False
        spec = task_spec.strip().lower()
        cancelled_id = None
        for t in tasks:
            if t.get("status") != "pending":
                continue
            if t.get("task_id") == task_spec or spec in t.get("instruction", "").lower():
                t["status"] = "cancelled"
                t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                found = True
                cancelled_id = t.get("task_id")
                break
        if found:
            self._save_tasks(tasks)
            logger.info(f"Cancelled task {cancelled_id} successfully.")
        return found

    def _cleanup_stale_tasks(self):
        """On startup, mark any tasks left in 'running' status as 'failed'."""
        tasks = self._load_tasks()
        changed = False
        for t in tasks:
            if t.get("status") == "running":
                t["status"] = "failed"
                t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                t["error"] = "Task was interrupted by system shutdown or crash."
                changed = True
        if changed:
            self._save_tasks(tasks)
            logger.info("Cleaned up stale running tasks from previous session.")

    def start(self):
        if self._running:
            return
        self._cleanup_stale_tasks()
        self._running = True
        self._loop_task = asyncio.create_task(self._scheduler_loop())
        logger.info("AERIS Task Scheduler service started.")

    def stop(self):
        self._running = False
        if self._loop_task:
            self._loop_task.cancel()
            self._loop_task = None
        logger.info("AERIS Task Scheduler service stopped.")

    async def _scheduler_loop(self):
        while self._running:
            try:
                await self._check_and_run_tasks()
            except Exception as e:
                logger.error(f"Error in check_and_run_tasks loop: {e}")
            await asyncio.sleep(5)  # Check every 5 seconds

    async def _check_and_run_tasks(self):
        tasks = self._load_tasks()
        now = datetime.now()
        changed = False

        for task in tasks:
            if task.get("status") != "pending":
                continue

            try:
                scheduled_time = datetime.strptime(task["scheduled_time"], "%Y-%m-%d %H:%M:%S")
            except Exception:
                continue

            if now >= scheduled_time:
                task["status"] = "running"
                changed = True
                asyncio.create_task(self._execute_scheduled_task(task))

        if changed:
            self._save_tasks(tasks)

    async def _execute_scheduled_task(self, task: dict):
        instruction = task["instruction"]
        logger.info(f"Executing scheduled task {task['task_id']}: '{instruction}'")
        
        # Check if this is a notification/reminder rather than a system command
        is_reminder = False
        reminder_content = instruction
        prefixes = ("remind user:", "reminder:", "alarm:", "meeting:", "remind:")
        inst_lower = instruction.lower().strip()
        for p in prefixes:
            if inst_lower.startswith(p):
                is_reminder = True
                reminder_content = instruction[len(p):].strip()
                break

        # Check if this is a power command (shutdown, restart, etc.)
        is_power_command = any(word in inst_lower for word in ["shutdown", "shut down", "restart", "reboot", "turn off"])

        try:
            # 1. Announce execution via TTS (non-blocking) - Only for tasks, skip for reminders
            from services.texttospeech import speak_async
            if not is_reminder:
                speak_async(f"Sir, scheduled task run kar raha hoon: {instruction}")

            # 2. Trigger Windows toast notification
            if platform.system() == "Windows":
                try:
                    from win11toast import toast
                    if is_reminder:
                        toast("⏰ AERIS Reminder", reminder_content)
                    else:
                        toast("⏰ AERIS Scheduled Task", instruction)
                except Exception:
                    pass

            # 3. Add task trace to chat memory
            from memory.store import memory_store
            memory_store.add_message("user", f"[Scheduled Task]: {instruction}")

            # If it is a power command, delete from database BEFORE executing
            if is_power_command:
                logger.info(f"Power command detected for task {task['task_id']}: '{instruction}'. Removing from database before execution.")
                tasks = self._load_tasks()
                tasks = [t for t in tasks if t["task_id"] != task["task_id"]]
                self._save_tasks(tasks)

            if is_reminder:
                # Direct reminder display, bypass brain planning loop
                response_text = f"Sir, aapka scheduled reminder: '{reminder_content}'."
            else:
                # 4. Lazy import brain to avoid circular dependencies
                from brain import brain
                result = await brain.process(instruction)
                response_text = result.get("response", "Task completed.")

            # Remove completed task from the database (if not already done for power command)
            if not is_power_command:
                tasks = self._load_tasks()
                tasks = [t for t in tasks if t["task_id"] != task["task_id"]]
                self._save_tasks(tasks)

            # Add response to the chat memory so it appears on the chat screen
            memory_store.add_message("assistant", response_text)

            # 5. Announce results
            speak_async(response_text)

        except Exception as e:
            logger.error(f"Failed to execute scheduled task {task['task_id']}: {e}")
            
            # Keep failed task in the database and update its status (only if it wasn't deleted)
            tasks = self._load_tasks()
            task_exists = any(t["task_id"] == task["task_id"] for t in tasks)
            if task_exists:
                for t in tasks:
                    if t["task_id"] == task["task_id"]:
                        t["status"] = "failed"
                        t["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        t["error"] = str(e)
                        break
                self._save_tasks(tasks)

            # Add failure message to the chat memory so it shows on the chat screen
            error_msg = f"Sir, scheduled task '{instruction}' fail ho gaya: {str(e)}"
            from memory.store import memory_store
            memory_store.add_message("assistant", error_msg)

            from services.texttospeech import speak_async
            speak_async(error_msg)


# Singleton instance
_scheduler: Optional[TaskScheduler] = None

def get_scheduler() -> TaskScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = TaskScheduler()
    return _scheduler
