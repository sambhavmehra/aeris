import os
import sys
import time
import ast
import json
import logging
import random
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config import settings
from services.notification_hub import send_desktop_notification, send_telegram_notification
from ai_engine import ai_engine

logger = logging.getLogger("aeris.workspace_watcher")

class WorkspaceWatcher:
    def __init__(self):
        self.workspace_dir = Path(settings.WORKSPACE_DIR)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self._observer: Optional[Observer] = None
        self._pending_repairs: Dict[str, Dict[str, Any]] = {}
        self._debounce_times: Dict[str, float] = {}
        self._lock = threading.Lock()

    def start(self):
        """Starts the watchdog observer to watch the workspace directory recursively."""
        if self._observer:
            return
        
        logger.info(f"Starting Workspace Watcher for directory: {self.workspace_dir}")
        handler = WorkspaceEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(handler, path=str(self.workspace_dir), recursive=True)
        self._observer.start()

    def stop(self):
        """Stops the watchdog observer."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
            logger.info("Workspace Watcher stopped.")

    def get_pending_repairs(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return dict(self._pending_repairs)

    def clear_repair(self, repair_id: str):
        with self._lock:
            if repair_id in self._pending_repairs:
                del self._pending_repairs[repair_id]
                logger.info(f"Cleared pending repair ID: {repair_id}")

    def check_file_syntax(self, file_path: Path):
        """Parses python or json files to check for syntax/formatting errors."""
        # Rate-limiting / debounce check
        file_str = str(file_path)
        now = time.time()
        with self._lock:
            last_checked = self._debounce_times.get(file_str, 0)
            if now - last_checked < 1.0:
                return  # Skip duplicate triggers
            self._debounce_times[file_str] = now

        # Wait a small delay to let the writing process complete/release lock
        time.sleep(0.2)
        if not file_path.exists() or not file_path.is_file():
            return

        ext = file_path.suffix.lower()
        if ext not in (".py", ".json"):
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Failed to read file {file_path} for syntax check: {e}")
            return

        has_error = False
        error_details = {}

        if ext == ".py":
            try:
                ast.parse(content)
            except SyntaxError as se:
                has_error = True
                error_details = {
                    "type": "SyntaxError",
                    "msg": se.msg,
                    "lineno": se.lineno or 1,
                    "offset": se.offset or 0,
                    "text": se.text or "",
                }
        elif ext == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as jde:
                has_error = True
                error_details = {
                    "type": "JSONDecodeError",
                    "msg": jde.msg,
                    "lineno": jde.lineno,
                    "offset": jde.colno,
                    "text": content.splitlines()[jde.lineno - 1] if jde.lineno <= len(content.splitlines()) else "",
                }

        rel_path = file_path.relative_to(self.workspace_dir)

        if has_error:
            # Check if this file already has a registered pending error
            existing_repair_id = None
            with self._lock:
                for rid, info in self._pending_repairs.items():
                    if info["file_path"] == file_path:
                        existing_repair_id = rid
                        break
            
            if existing_repair_id:
                # Update existing error details
                with self._lock:
                    self._pending_repairs[existing_repair_id]["error"] = error_details
                    self._pending_repairs[existing_repair_id]["timestamp"] = now
                logger.info(f"Updated syntax error for {rel_path} (Repair ID: {existing_repair_id})")
                return

            # Register new repair
            repair_id = f"rep_{random.randint(100000, 999999)}"
            with self._lock:
                self._pending_repairs[repair_id] = {
                    "repair_id": repair_id,
                    "file_path": file_path,
                    "rel_path": rel_path,
                    "error": error_details,
                    "timestamp": now,
                }
            
            logger.warning(f"Syntax error detected in {rel_path} at line {error_details['lineno']}: {error_details['msg']}")
            
            # Dispatch Notifications
            self._dispatch_error_notifications(repair_id, rel_path, error_details)
        else:
            # Self-healing: If there was a pending repair for this file, clear it since it now parses cleanly
            cleared_id = None
            with self._lock:
                for rid, info in list(self._pending_repairs.items()):
                    if info["file_path"] == file_path:
                        cleared_id = rid
                        del self._pending_repairs[rid]
                        break
            
            if cleared_id:
                logger.info(f"Self-healed: file {rel_path} now parses successfully. Cleared repair ID: {cleared_id}")
                # Optional: Send a follow-up notifications confirming manual resolution
                send_desktop_notification(
                    "AERIS: Syntax Resolved",
                    f"Syntax error in {rel_path.name} was resolved manually."
                )

    def _dispatch_error_notifications(self, repair_id: str, rel_path: Path, error: dict):
        """Sends native desktop notifications and Telegram messages with inline buttons."""
        title = "AERIS: Syntax Error Detected"
        msg = f"Error in {rel_path.name} line {error['lineno']}: {error['msg']}"
        send_desktop_notification(title, msg)

        # Build Telegram alert
        telegram_msg = (
            f"⚠️ **AERIS Syntax Error Alert**\n\n"
            f"- **File**: `{rel_path}`\n"
            f"- **Line**: `{error['lineno']}`\n"
            f"- **Error**: `{error['msg']}`\n"
        )
        if error.get("text"):
            telegram_msg += f"- **Code**: `{error['text'].strip()}`\n"
            
        telegram_msg += "\nWould you like me to auto-repair it, Sir?"

        reply_markup = {
            "inline_keyboard": [
                [
                    {"text": "🔧 Auto-Repair", "callback_data": f"repair_code_{repair_id}"},
                    {"text": "❌ Ignore", "callback_data": f"ignore_code_{repair_id}"}
                ]
            ]
        }

        # Dispatch async notification safely
        import asyncio
        asyncio.create_task(send_telegram_notification(telegram_msg, reply_markup=reply_markup))

    async def trigger_repair(self, repair_id: str) -> str:
        """Invokes the AI model to repair the code syntax error and writes the fix."""
        info = None
        with self._lock:
            info = self._pending_repairs.get(repair_id)

        if not info:
            return f"Error: Repair record `{repair_id}` not found."

        file_path = info["file_path"]
        rel_path = info["rel_path"]
        error = info["error"]

        if not file_path.exists():
            self.clear_repair(repair_id)
            return f"Error: File `{rel_path}` no longer exists."

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                current_code = f.read()
        except Exception as e:
            return f"Error reading file for repair: {e}"

        prompt = (
            f"You are the AERIS Jarvis Auto-Repair system.\n"
            f"The file at `{rel_path}` contains a syntax error:\n"
            f"- Type: {error.get('type')}\n"
            f"- Message: {error.get('msg')}\n"
            f"- Line: {error.get('lineno')}\n"
            f"- Erroneous Code Context: {error.get('text')}\n\n"
            f"Here is the complete contents of the file:\n"
            f"```\n{current_code}\n```\n\n"
            f"Task: Fix the syntax error. Do NOT add new logic or rewrite the functionality. "
            f"Keep comments and formatting intact. Fix issues like missing colons, parenthesis mismatch, indentation issues, or JSON structural faults.\n\n"
            f"CRITICAL: Output ONLY the pure, raw corrected file content. Do NOT wrap it in markdown code blocks (such as ```python or ```json). "
            f"Do not include any greeting, introduction, or explanation. Your response will be written directly back to the file."
        )

        try:
            repaired_code = await ai_engine.chat(
                messages=[
                    {"role": "system", "content": "You are a code syntax repair bot. You respond ONLY with raw, complete code, no markdown blocks, no chatter."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )
            # Remove optional markdown block wrap if LLM fails instructions
            repaired_code = repaired_code.strip()
            if repaired_code.startswith("```"):
                lines = repaired_code.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                repaired_code = "\n".join(lines).strip()

        except Exception as e:
            logger.error(f"Failed to query AI for repair: {e}")
            return f"AI correction call failed: {e}"

        # Verify output syntax before writing
        ext = file_path.suffix.lower()
        test_parse_success = False
        verify_error = ""

        if ext == ".py":
            try:
                ast.parse(repaired_code)
                test_parse_success = True
            except SyntaxError as se:
                verify_error = f"AI output has syntax error: {se.msg} on line {se.lineno}"
        elif ext == ".json":
            try:
                json.loads(repaired_code)
                test_parse_success = True
            except json.JSONDecodeError as jde:
                verify_error = f"AI output has JSON error: {jde.msg} on line {jde.lineno}"

        if not test_parse_success:
            logger.error(f"AI proposed repair for {rel_path} failed syntax verification: {verify_error}")
            return f"AI generated repair failed verification: {verify_error}"

        # Write fixed file
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(repaired_code)
            
            self.clear_repair(repair_id)
            logger.info(f"Successfully auto-repaired {rel_path}.")
            
            # Announce via speech
            try:
                from services.texttospeech import speak_async
                speak_async(f"Sir, I have successfully repaired the syntax error in {rel_path.name}.")
            except Exception:
                pass
            
            return f"Successfully auto-repaired `{rel_path}`. The file now parses cleanly."
        except Exception as e:
            logger.error(f"Failed to write repaired file: {e}")
            return f"Failed to write repaired file: {e}"


class WorkspaceEventHandler(FileSystemEventHandler):
    def __init__(self, watcher: WorkspaceWatcher):
        self.watcher = watcher

    def on_modified(self, event):
        if event.is_directory:
            return
        self.watcher.check_file_syntax(Path(event.src_path))

    def on_created(self, event):
        if event.is_directory:
            return
        self.watcher.check_file_syntax(Path(event.src_path))


# Singleton instance
_workspace_watcher: Optional[WorkspaceWatcher] = None

def get_workspace_watcher() -> WorkspaceWatcher:
    global _workspace_watcher
    if _workspace_watcher is None:
        _workspace_watcher = WorkspaceWatcher()
    return _workspace_watcher


async def handle_conversational_repair(message: str) -> Optional[dict]:
    """Intercepts messages like 'repair file' or 'fix syntax' and runs the repair pipeline."""
    lower_msg = message.lower()
    triggers = ("repair", "fix syntax", "fix error", "thik karo", "theek karo", "thik kar do", "theek kar do", "rectify")
    
    if not any(t in lower_msg for t in triggers):
        return None

    watcher = get_workspace_watcher()
    pending = watcher.get_pending_repairs()

    if not pending:
        # If they explicitly ask but nothing is broken, tell them nicely
        if any(w in lower_msg for w in ("syntax", "error", "file")):
            response_text = "Sir, I have not detected any syntax errors in your workspace files."
            from memory.store import memory_store
            memory_store.add_message("user", message)
            memory_store.add_message("assistant", response_text)
            return {
                "response": response_text,
                "intent": "chat",
                "agent": "Brain",
                "success": True
            }
        return None

    # Resolve which file to repair
    chosen_repair_id = None
    chosen_info = None

    # 1. Look for filename match in query
    for rid, info in pending.items():
        fname = info["rel_path"].name.lower()
        if fname in lower_msg:
            chosen_repair_id = rid
            chosen_info = info
            break

    # 2. If exactly one file is pending, default to it
    if not chosen_repair_id and len(pending) == 1:
        chosen_repair_id = list(pending.keys())[0]
        chosen_info = pending[chosen_repair_id]

    if not chosen_repair_id:
        # Multiple files pending, ask to clarify
        files_list = ", ".join([f"`{info['rel_path']}`" for info in pending.values()])
        response_text = f"Sir, I detected syntax errors in multiple files: {files_list}. Which one would you like me to repair?"
        from memory.store import memory_store
        memory_store.add_message("user", message)
        memory_store.add_message("assistant", response_text)
        return {
            "response": response_text,
            "intent": "chat",
            "agent": "Brain",
            "success": True
        }

    # Run repair
    rel_path = chosen_info["rel_path"]
    from memory.store import memory_store
    memory_store.add_message("user", message)
    
    # Send intermediate progress message
    try:
        from engine.state_manager import global_state_manager
        global_state_manager.set_global_action(f"Sir, {rel_path.name} ko repair kar raha hoon...")
    except Exception:
        pass

    result = await watcher.trigger_repair(chosen_repair_id)
    memory_store.add_message("assistant", result)

    try:
        from engine.state_manager import global_state_manager
        global_state_manager.set_global_action("Idle")
    except Exception:
        pass

    return {
        "response": result,
        "intent": "edit_file",
        "agent": "CodeAgent",
        "success": "successfully" in result.lower(),
        "task_id": chosen_repair_id
    }
