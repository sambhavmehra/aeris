"""
AERIS Failure Logger Utility
Logs tool execution failures and agentic task failures to:
  - failed_tools.json (structured JSON list)
  - failed_log.txt (human-readable text log)
"""
import os
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("aeris.utils.failure_logger")
_log_lock = threading.Lock()


def get_backend_root() -> Path:
    """Helper to resolve the BACKEND directory root."""
    return Path(__file__).resolve().parent.parent


def log_task_failure(
    task_id: str,
    step_id: str,
    tool_name: str,
    args: dict,
    error: str,
    agent_name: str = "Unknown",
    intent: str = "unknown"
) -> None:
    """
    Log a tool or task execution failure in a thread-safe manner.
    Appends structured entry to failed_tools.json and text block to failed_log.txt.
    """
    with _log_lock:
        backend_dir = get_backend_root()
        json_path = backend_dir / "failed_tools.json"
        txt_path = backend_dir / "failed_log.txt"

        timestamp = datetime.now(timezone.utc).isoformat()

        # Create structured entry
        entry = {
            "timestamp": timestamp,
            "task_id": task_id or "sys_manual",
            "step_id": step_id or "",
            "agent_name": agent_name,
            "intent": intent,
            "tool_name": tool_name,
            "arguments": args or {},
            "error": error or "Unknown execution error"
        }

        # 1. Update failed_tools.json
        try:
            data = {"failed_tools": []}
            if json_path.exists() and json_path.stat().st_size > 0:
                try:
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    if not isinstance(data, dict) or "failed_tools" not in data:
                        data = {"failed_tools": []}
                except (json.JSONDecodeError, ValueError) as je:
                    logger.warning(f"Failed to parse failed_tools.json: {je}. Resetting file.")
                    data = {"failed_tools": []}

            data.setdefault("failed_tools", []).append(entry)
            json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Error writing to failed_tools.json: {e}")

        # 2. Update failed_log.txt
        try:
            log_block = (
                f"======================================================================\n"
                f"TIMESTAMP:   {timestamp}\n"
                f"TASK ID:     {entry['task_id']}\n"
                f"STEP ID:     {entry['step_id']}\n"
                f"AGENT/INTENT:{entry['agent_name']} / {entry['intent']}\n"
                f"TOOL NAME:   {entry['tool_name']}\n"
                f"ARGUMENTS:   {json.dumps(entry['arguments'], default=str)}\n"
                f"ERROR MSG:   {entry['error']}\n"
                f"======================================================================\n\n"
            )
            # If the file contains only the placeholder {all errors from previous steps}, overwrite it
            if txt_path.exists() and txt_path.stat().st_size > 0:
                try:
                    content = txt_path.read_text(encoding="utf-8").strip()
                    if content == "{all errors from previous steps}":
                        txt_path.write_text(log_block, encoding="utf-8")
                        return
                except Exception:
                    pass

            with open(txt_path, "a", encoding="utf-8") as f:
                f.write(log_block)
        except Exception as e:
            logger.error(f"Error writing to failed_log.txt: {e}")


def clear_resolved_failures(tool_name: str, error_snippet: str = "") -> None:
    """
    Remove any logged failures for tool_name where the error message matches error_snippet.
    If error_snippet is empty, removes all failures for tool_name.
    """
    with _log_lock:
        backend_dir = get_backend_root()
        json_path = backend_dir / "failed_tools.json"
        txt_path = backend_dir / "failed_log.txt"

        # 1. Update failed_tools.json
        removed_tasks = set()
        if json_path.exists() and json_path.stat().st_size > 0:
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                failures = data.get("failed_tools", [])
                
                # Filter out failures that match
                remaining = []
                for f in failures:
                    f_tool = f.get("tool_name", "")
                    f_err = f.get("error", "")
                    if f_tool == tool_name and (not error_snippet or error_snippet.lower() in f_err.lower()):
                        removed_tasks.add(f.get("task_id", ""))
                        continue
                    remaining.append(f)
                
                data["failed_tools"] = remaining
                json_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
                logger.info(f"Cleared resolved failures for {tool_name} from failed_tools.json")
            except Exception as e:
                logger.error(f"Error updating failed_tools.json: {e}")

        # 2. Update failed_log.txt
        if txt_path.exists() and txt_path.stat().st_size > 0:
            try:
                content = txt_path.read_text(encoding="utf-8")
                blocks = content.split("======================================================================\n")
                new_blocks = []
                for block in blocks:
                    if not block.strip():
                        continue
                    # Check if this block describes a removed task or a matching tool failure
                    is_match = False
                    for task_id in removed_tasks:
                        if task_id and f"TASK ID:     {task_id}" in block:
                            is_match = True
                            break
                    if f"TOOL NAME:   {tool_name}" in block:
                        if not error_snippet or error_snippet.lower() in block.lower():
                            is_match = True
                            
                    if not is_match:
                        new_blocks.append(block)
                
                if new_blocks:
                    txt_path.write_text(
                        "======================================================================\n" + 
                        "======================================================================\n".join(new_blocks),
                        encoding="utf-8"
                    )
                else:
                    # Write placeholder if empty
                    txt_path.write_text("{all errors from previous steps}", encoding="utf-8")
            except Exception as e:
                logger.error(f"Error updating failed_log.txt: {e}")
