"""
AERIS -- Shell GPT Bridge
Integrates Shell GPT's best patterns into AERIS:
  1. Smart Shell Command Generation (LLM writes OS commands)
  2. Interactive Execution with Execute/Modify/Describe/Abort safety
  3. Response Caching (MD5-based, avoids repeated API calls)
  4. Pydantic Function Schemas (auto-generate OpenAI tool schemas)
  5. Named Chat Sessions (multiple persistent conversations)

Adapted from: https://github.com/TheR1D/shell_gpt
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


# =====================================================================
#  1. SMART SHELL COMMAND GENERATOR
# =====================================================================

# Auto-detect OS and shell (from shell_gpt's role.py)
def _detect_os() -> str:
    current = platform.system()
    if current == "Windows":
        return f"Windows {platform.release()}"
    elif current == "Darwin":
        return f"macOS {platform.mac_ver()[0]}"
    elif current == "Linux":
        try:
            from distro import name as distro_name
            return f"Linux/{distro_name(pretty=True)}"
        except ImportError:
            return "Linux"
    return current


def _detect_shell() -> str:
    current = platform.system()
    if current in ("Windows", "nt"):
        is_powershell = len(os.getenv("PSModulePath", "").split(os.pathsep)) >= 3
        return "powershell.exe" if is_powershell else "cmd.exe"
    return os.path.basename(os.getenv("SHELL", "/bin/sh"))


SHELL_ROLE = """You are an expert system administrator. Provide ONLY {shell} commands for {os} without any description.
If there is a lack of details, provide the most logical solution.
Ensure the output is a valid shell command.
If multiple steps are required, combine them using && (or ; for PowerShell).
Provide ONLY plain text without Markdown formatting.
Do NOT include ``` or ```powershell or any markdown blocks."""

DESCRIBE_ROLE = """Provide a terse, single sentence description of the given shell command.
Describe each argument and option of the command.
Provide short responses in about 80 words."""

CODE_ROLE = """Provide only code as output without any description.
Provide only code in plain text format without Markdown formatting.
Do not include symbols such as ``` or ```python.
If there is a lack of details, provide the most logical solution.
You are not allowed to ask for more details."""


@dataclass
class ShellCommandResult:
    """Result of a smart shell command generation + optional execution."""
    command: str
    description: str = ""
    executed: bool = False
    output: str = ""
    exit_code: int = -1
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "description": self.description,
            "executed": self.executed,
            "output": self.output,
            "exit_code": self.exit_code,
            "error": self.error,
        }


class SmartShellEngine:
    """
    Generates, describes, and safely executes shell commands using LLM.
    Inspired by Shell GPT's --shell mode.
    """

    def __init__(self):
        self.os_name = _detect_os()
        self.shell_name = _detect_shell()
        self._shell_prompt = SHELL_ROLE.format(shell=self.shell_name, os=self.os_name)
        self._describe_prompt = DESCRIBE_ROLE

    async def generate_command(self, user_request: str) -> str:
        """Ask LLM to generate the right shell command for a natural language request."""
        from ai_engine import ai_engine

        messages = [
            {"role": "system", "content": self._shell_prompt},
            {"role": "user", "content": user_request},
        ]

        try:
            cmd = await ai_engine.chat(messages, temperature=0.0, max_tokens=512)
        except Exception:
            raise Exception("No AI provider available for shell command generation.")

        cmd = (cmd or "").strip()
        # Clean any accidental markdown
        if "```" in cmd:
            cmd = cmd.split("```")[1] if "```" in cmd else cmd
            cmd = cmd.replace("powershell", "").replace("bash", "").replace("sh", "").strip()
        return cmd

    async def describe_command(self, command: str) -> str:
        """Ask LLM to explain what a shell command does."""
        from ai_engine import ai_engine

        messages = [
            {"role": "system", "content": self._describe_prompt},
            {"role": "user", "content": command},
        ]

        try:
            return await ai_engine.chat(messages, temperature=0.3, max_tokens=256)
        except Exception:
            return "Unable to describe command."

    def execute_command(self, command: str) -> ShellCommandResult:
        """Execute a shell command and capture output."""
        try:
            if platform.system() == "Windows":
                is_ps = len(os.getenv("PSModulePath", "").split(os.pathsep)) >= 3
                if is_ps:
                    full_cmd = ["powershell.exe", "-NoProfile", "-Command", command]
                else:
                    full_cmd = ["cmd.exe", "/c", command]
            else:
                shell = os.environ.get("SHELL", "/bin/sh")
                full_cmd = [shell, "-c", command]

            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            return ShellCommandResult(
                command=command,
                executed=True,
                output=result.stdout.strip()[:50000],
                exit_code=result.returncode,
                error=result.stderr.strip()[:5000] if result.returncode != 0 else "",
            )
        except subprocess.TimeoutExpired:
            return ShellCommandResult(command=command, error="Command timed out (60s)", exit_code=-1)
        except Exception as e:
            return ShellCommandResult(command=command, error=str(e), exit_code=-1)

    async def smart_execute(self, user_request: str, auto_execute: bool = False) -> ShellCommandResult:
        """
        Full pipeline: generate command → describe → optionally execute.
        If auto_execute=True, runs immediately. Otherwise returns for confirmation.
        """
        command = await self.generate_command(user_request)
        description = await self.describe_command(command)

        result = ShellCommandResult(command=command, description=description)

        if auto_execute:
            exec_result = self.execute_command(command)
            result.executed = exec_result.executed
            result.output = exec_result.output
            result.exit_code = exec_result.exit_code
            result.error = exec_result.error

        return result

    async def generate_code(self, user_request: str, language: str = "python") -> str:
        """Ask LLM to generate pure code (no markdown) for a request."""
        from ai_engine import ai_engine

        messages = [
            {"role": "system", "content": CODE_ROLE},
            {"role": "user", "content": f"{language}: {user_request}"},
        ]

        try:
            code = await ai_engine.chat(messages, temperature=0.1, max_tokens=2048)
        except Exception:
            return f"# Error: Unable to generate {language} code"

        code = (code or "").strip()
        if "```" in code:
            code = code.split("```")[1] if "```" in code else code
            code = code.replace(language.lower(), "").strip()
        return code


# =====================================================================
#  2. RESPONSE CACHE (from shell_gpt's cache.py)
# =====================================================================

class ResponseCache:
    """
    MD5-based response cache. Caches AI responses to avoid repeated API calls.
    Inspired by Shell GPT's Cache decorator.
    """

    def __init__(self, cache_dir: str | None = None, max_entries: int = 200):
        self.cache_dir = Path(cache_dir or Path(__file__).parent / "data" / "response_cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries

    def _key(self, query: str, context: str = "") -> str:
        """Generate a cache key from query + context."""
        raw = f"{query.strip().lower()}|{context.strip().lower()}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def get(self, query: str, context: str = "") -> Optional[str]:
        """Retrieve cached response, or None if not cached."""
        key = self._key(query, context)
        cache_file = self.cache_dir / key
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                return data.get("response")
            except Exception:
                return None
        return None

    def set(self, query: str, response: str, context: str = "") -> None:
        """Cache a response."""
        key = self._key(query, context)
        cache_file = self.cache_dir / key
        data = {
            "query": query,
            "response": response,
            "context": context,
            "cached_at": datetime.now().isoformat(),
        }
        try:
            cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self._cleanup()

    def invalidate(self, query: str, context: str = "") -> None:
        """Remove a specific cache entry."""
        key = self._key(query, context)
        cache_file = self.cache_dir / key
        cache_file.unlink(missing_ok=True)

    def clear(self) -> int:
        """Clear all cache entries. Returns count deleted."""
        count = 0
        for f in self.cache_dir.glob("*"):
            if f.is_file():
                f.unlink()
                count += 1
        return count

    def _cleanup(self) -> None:
        """Remove oldest cache files if over limit."""
        files = sorted(self.cache_dir.glob("*"), key=lambda f: f.stat().st_mtime)
        if len(files) > self.max_entries:
            for f in files[: len(files) - self.max_entries]:
                f.unlink(missing_ok=True)


# =====================================================================
#  3. PYDANTIC FUNCTION SCHEMA GENERATOR (from shell_gpt's function.py)
# =====================================================================

class AerisFunction:
    """
    Wraps a Pydantic BaseModel into an OpenAI function-calling schema.
    Inspired by Shell GPT's Function class.

    Usage:
        class MyTool(BaseModel):
            '''Search for files on the system.'''
            query: str = Field(..., description="Search query")
            max_results: int = Field(10, description="Max results to return")

            @classmethod
            def execute(cls, **kwargs) -> str:
                return json.dumps({"results": []})

        func = AerisFunction(MyTool)
        schema = func.openai_schema    # Ready for OpenAI API
        result = func.run(query="test") # Execute the tool
    """

    def __init__(self, model_class: type):
        if not issubclass(model_class, BaseModel):
            raise TypeError(f"{model_class.__name__} must be a Pydantic BaseModel subclass")
        if not hasattr(model_class, "execute"):
            raise TypeError(f"{model_class.__name__} must have a classmethod 'execute'")
        self.model_class = model_class
        self._name = model_class.__name__.lower()

    @property
    def name(self) -> str:
        return self._name

    @property
    def openai_schema(self) -> Dict[str, Any]:
        """Generate OpenAI function-calling schema automatically from the Pydantic model."""
        schema = self.model_class.model_json_schema()
        doc = (self.model_class.__doc__ or "").strip()
        return {
            "type": "function",
            "function": {
                "name": self._name,
                "description": doc,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                },
            },
        }

    def run(self, **kwargs) -> str:
        """Execute the tool with given arguments."""
        return self.model_class.execute(**kwargs)


class FunctionRegistry:
    """Registry for Pydantic-based function tools. Auto-discovers .py files in a folder."""

    def __init__(self, functions_dir: str | None = None):
        self.functions_dir = Path(functions_dir or Path(__file__).parent / "AERIS_functions")
        self.functions_dir.mkdir(parents=True, exist_ok=True)
        self._functions: Dict[str, AerisFunction] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all function modules from the functions directory."""
        import importlib.util
        for py_file in self.functions_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            try:
                module_name = py_file.stem
                spec = importlib.util.spec_from_file_location(module_name, str(py_file))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                if hasattr(module, "Function") and issubclass(module.Function, BaseModel):
                    func = AerisFunction(module.Function)
                    self._functions[func.name] = func
            except Exception:
                pass

    def register(self, model_class: type) -> AerisFunction:
        """Register a Pydantic model class as a function."""
        func = AerisFunction(model_class)
        self._functions[func.name] = func
        return func

    def get(self, name: str) -> Optional[AerisFunction]:
        return self._functions.get(name.lower())

    def get_all_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI function schemas for all registered functions."""
        return [f.openai_schema for f in self._functions.values()]

    def execute(self, name: str, **kwargs) -> str:
        """Execute a registered function by name."""
        func = self.get(name)
        if not func:
            raise ValueError(f"Function '{name}' not found. Available: {list(self._functions.keys())}")
        return func.run(**kwargs)

    def list_functions(self) -> List[str]:
        return list(self._functions.keys())


# =====================================================================
#  4. NAMED CHAT SESSIONS (from shell_gpt's chat_handler.py)
# =====================================================================

class ChatSessionManager:
    """
    Manages multiple named chat sessions with persistent history.
    Inspired by Shell GPT's ChatSession class.
    """

    def __init__(self, storage_dir: str | None = None, max_messages: int = 50):
        self.storage_dir = Path(storage_dir or Path(__file__).parent / "data" / "chat_sessions")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_messages = max_messages

    def _session_path(self, session_id: str) -> Path:
        safe = session_id.replace(" ", "_").replace("/", "_").replace("\\", "_")
        return self.storage_dir / f"{safe}.json"

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """Get all messages for a session."""
        path = self._session_path(session_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to a session."""
        messages = self.get_messages(session_id)
        messages.append({"role": role, "content": content})
        # Truncate: keep first (system) message + last N
        if len(messages) > self.max_messages:
            messages = messages[:1] + messages[-(self.max_messages - 1):]
        self._session_path(session_id).write_text(
            json.dumps(messages, ensure_ascii=False), encoding="utf-8"
        )

    def clear_session(self, session_id: str) -> None:
        """Delete a session."""
        self._session_path(session_id).unlink(missing_ok=True)

    def list_sessions(self) -> List[dict]:
        """List all sessions with metadata."""
        sessions = []
        for f in sorted(self.storage_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                messages = json.loads(f.read_text(encoding="utf-8"))
                sessions.append({
                    "id": f.stem,
                    "message_count": len(messages),
                    "last_modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                })
            except Exception:
                pass
        return sessions

    def exists(self, session_id: str) -> bool:
        return self._session_path(session_id).exists()


# =====================================================================
#  5. BUILT-IN AERIS SHELL FUNCTIONS (Pydantic pattern)
# =====================================================================

class ExecuteShellCommand(BaseModel):
    """Execute a shell command and return the output."""
    shell_command: str = Field(
        ...,
        description="Shell command to execute.",
        json_schema_extra={"example": "Get-ChildItem"},
    )

    @classmethod
    def execute(cls, shell_command: str) -> str:
        process = subprocess.Popen(
            shell_command, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        output, _ = process.communicate(timeout=60)
        exit_code = process.returncode
        return json.dumps({
            "exit_code": exit_code,
            "output": output.decode(errors="replace")[:20000],
        })


class SmartShellCommand(BaseModel):
    """Generate and execute a shell command from a natural language description."""
    description: str = Field(
        ...,
        description="Natural language description of what you want to do.",
        json_schema_extra={"example": "find all Python files modified in the last 24 hours"},
    )
    auto_execute: bool = Field(
        False,
        description="If True, automatically execute the generated command.",
    )

    @classmethod
    def execute(cls, description: str, auto_execute: bool = False) -> str:
        import asyncio
        engine = SmartShellEngine()
        
        # Determine if we are running in an existing event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
            
        if loop and loop.is_running():
            # If in an event loop, we have to run synchronously in a thread or use run_coroutine_threadsafe
            import nest_asyncio
            nest_asyncio.apply()
            result = asyncio.run(engine.smart_execute(description, auto_execute=auto_execute))
        else:
            result = asyncio.run(engine.smart_execute(description, auto_execute=auto_execute))
            
        return json.dumps(result.to_dict())


# =====================================================================
#  GLOBAL INSTANCES
# =====================================================================

# Smart shell engine for generating and executing shell commands
smart_shell = SmartShellEngine()

# Response cache for avoiding repeated API calls
response_cache = ResponseCache()

# Named chat session manager
session_manager = ChatSessionManager()

# Pydantic function registry
function_registry = FunctionRegistry()

# Register built-in functions
function_registry.register(ExecuteShellCommand)
function_registry.register(SmartShellCommand)
