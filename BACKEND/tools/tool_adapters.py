"""
AERIS — Tool Adapters
═══════════════════════════════════════════════════════════════════════
Concrete adapters that bridge different tool sources into the universal
execution interface defined by tool_interface.py.

Supported adapters:
  • CLIToolAdapter    — wraps shell / PowerShell commands
  • APIToolAdapter    — wraps REST API endpoints
  • FileToolAdapter   — loads & runs .py files from aeris_tools/
  • MCPToolAdapter    — dispatches to external MCP servers

Each adapter converts raw external output into a ToolExecutionResult.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("AerisToolAdapters")

from tools.tool_interface import (
    ToolAdapter,
    ToolExecutionResult,
    ToolSource,
    UniversalToolDef,
)


# ═════════════════════════════════════════════════════════════════════
#  CLI Tool Adapter — wraps command-line tools
# ═════════════════════════════════════════════════════════════════════

class CLIToolAdapter(ToolAdapter):
    """
    Executes tools defined as shell / PowerShell command templates.

    The tool's ``cli_command_template`` can contain ``{param_name}``
    placeholders that are filled from kwargs.  Example:
        "ffmpeg -i {input_path} -vf scale={width}:{height} {output_path}"
    """

    DEFAULT_TIMEOUT = 60
    MAX_OUTPUT_BYTES = 500_000

    def execute(self, tool: UniversalToolDef, **kwargs) -> ToolExecutionResult:
        template = tool.cli_command_template
        if not template:
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr="No cli_command_template defined for CLI tool.",
                source=ToolSource.CLI_BASED,
            )

        # Fill placeholders
        try:
            command = template.format(**kwargs)
        except KeyError as e:
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=f"Missing parameter for CLI template: {e}",
                source=ToolSource.CLI_BASED,
            )

        start = time.perf_counter()
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=self.DEFAULT_TIMEOUT,
            )
            elapsed = (time.perf_counter() - start) * 1000

            if result.returncode == 0:
                output = result.stdout.strip()[:self.MAX_OUTPUT_BYTES]
                return ToolExecutionResult(
                    tool_name=tool.name, success=True,
                    stdout=output,
                    stderr="",
                    exit_code=0,
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.CLI_BASED,
                )
            else:
                return ToolExecutionResult(
                    tool_name=tool.name, success=False,
                    stdout=result.stdout.strip()[:self.MAX_OUTPUT_BYTES],
                    stderr=result.stderr.strip()[:self.MAX_OUTPUT_BYTES] or f"Exit code {result.returncode}",
                    exit_code=result.returncode,
                    error_type="subprocess_error",
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.CLI_BASED,
                )
        except subprocess.TimeoutExpired:
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=f"CLI timeout ({self.DEFAULT_TIMEOUT}s)",
                exit_code=-1,
                error_type="timeout_error",
                source=ToolSource.CLI_BASED,
            )
        except Exception as e:
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=str(e),
                exit_code=-1,
                error_type="system_error",
                source=ToolSource.CLI_BASED,
            )

    def health_check(self, tool: UniversalToolDef) -> bool:
        """CLI tools are always 'healthy' if the template exists."""
        return bool(tool.cli_command_template)


# ═════════════════════════════════════════════════════════════════════
#  API Tool Adapter — wraps REST endpoints
# ═════════════════════════════════════════════════════════════════════

class APIToolAdapter(ToolAdapter):
    """
    Calls a REST API endpoint and returns the response.

    The tool's ``endpoint_url`` is the base URL.
    kwargs are sent as JSON body in a POST request.
    """

    DEFAULT_TIMEOUT = 30

    def execute(self, tool: UniversalToolDef, **kwargs) -> ToolExecutionResult:
        url = tool.endpoint_url
        if not url:
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr="No endpoint_url defined for API tool.",
                source=ToolSource.API_BASED,
            )

        start = time.perf_counter()
        try:
            import httpx
            with httpx.Client(timeout=self.DEFAULT_TIMEOUT) as client:
                resp = client.post(url, json=kwargs)
            elapsed = (time.perf_counter() - start) * 1000

            if resp.status_code < 400:
                try:
                    data = resp.json()
                except Exception:
                    data = resp.text[:2000]
                return ToolExecutionResult(
                    tool_name=tool.name, success=True,
                    stdout=json.dumps(data) if isinstance(data, dict) else str(data),
                    exit_code=resp.status_code,
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.API_BASED,
                )
            else:
                return ToolExecutionResult(
                    tool_name=tool.name, success=False,
                    stderr=f"HTTP {resp.status_code}: {resp.text[:500]}",
                    exit_code=resp.status_code,
                    error_type="http_error",
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.API_BASED,
                )
        except ImportError:
            # Fallback to urllib
            return self._fallback_request(tool, kwargs, start)
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=str(e),
                exit_code=-1,
                error_type="network_error",
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.API_BASED,
            )

    def _fallback_request(self, tool: UniversalToolDef, kwargs: dict, start: float) -> ToolExecutionResult:
        """Fallback using urllib when httpx is not installed."""
        import urllib.request
        import urllib.error

        url = tool.endpoint_url
        body = json.dumps(kwargs).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.DEFAULT_TIMEOUT) as resp:
                elapsed = (time.perf_counter() - start) * 1000
                data = resp.read().decode("utf-8")[:2000]
                return ToolExecutionResult(
                    tool_name=tool.name, success=True,
                    stdout=data,
                    exit_code=200,
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.API_BASED,
                )
        except urllib.error.HTTPError as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=f"HTTP {e.code}: {e.reason}",
                exit_code=e.code,
                error_type="http_error",
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.API_BASED,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=str(e),
                exit_code=-1,
                error_type="network_error",
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.API_BASED,
            )

    def health_check(self, tool: UniversalToolDef) -> bool:
        """Ping the endpoint URL with a HEAD request."""
        if not tool.endpoint_url:
            return False
        try:
            import httpx
            resp = httpx.head(tool.endpoint_url, timeout=5)
            return resp.status_code < 500
        except Exception:
            return False


# ═════════════════════════════════════════════════════════════════════
#  File-Based Tool Adapter — loads .py from aeris_tools/
# ═════════════════════════════════════════════════════════════════════

class FileToolAdapter(ToolAdapter):
    """
    Loads a Python file that contains a ``run(**kwargs) -> dict`` function
    and executes it in-process (or in a subprocess sandbox if configured).
    """

    SANDBOX_TIMEOUT = 30
    MAX_OUTPUT = 500_000

    def __init__(self, use_sandbox: bool = False):
        self.use_sandbox = use_sandbox

    def execute(self, tool: UniversalToolDef, **kwargs) -> ToolExecutionResult:
        file_path = tool.file_path
        if not file_path or not os.path.isfile(file_path):
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=f"Tool file not found: {file_path}",
                source=ToolSource.FILE_BASED,
            )

        if self.use_sandbox:
            return self._execute_sandboxed(tool, kwargs)
        return self._execute_inline(tool, kwargs)

    def _execute_inline(self, tool: UniversalToolDef, kwargs: dict) -> ToolExecutionResult:
        """Load and run the module in the current process."""
        start = time.perf_counter()
        try:
            spec = importlib.util.spec_from_file_location(
                f"aeris_tool_{tool.name}", tool.file_path
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "run"):
                return ToolExecutionResult(
                    tool_name=tool.name, success=False,
                    stderr=f"Tool file {tool.file_path} has no 'run()' function.",
                    source=ToolSource.FILE_BASED,
                )

            result = mod.run(**kwargs)
            elapsed = (time.perf_counter() - start) * 1000

            # Normalise result
            if isinstance(result, dict):
                success = result.get("success", True)
                output = result.get("output", result.get("result", json.dumps(result)))
                error = result.get("error", "")
            else:
                success = True
                output = str(result)
                error = ""

            return ToolExecutionResult(
                tool_name=tool.name, success=success,
                stdout=str(output) if output else "",
                stderr=str(error) if error else "",
                exit_code=0 if success else 1,
                error_type="tool_error" if not success else None,
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.FILE_BASED,
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                exit_code=-1,
                error_type="execution_exception",
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.FILE_BASED,
            )

    def _execute_sandboxed(self, tool: UniversalToolDef, kwargs: dict) -> ToolExecutionResult:
        """Run in a subprocess for isolation."""
        import textwrap

        args_json = json.dumps(kwargs)
        runner = textwrap.dedent(f"""\
            import sys, json, os
            sys.path.insert(0, os.path.dirname(r"{tool.file_path}"))
            spec = __import__("importlib").util.spec_from_file_location("tool_mod", r"{tool.file_path}")
            mod = __import__("importlib").util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod.run(**json.loads(r'''{args_json}'''))
            print(json.dumps(result, default=str))
        """)

        start = time.perf_counter()
        try:
            # Redact sensitive environment variables to prevent leakage
            safe_env = os.environ.copy()
            sensitive_patterns = ["key", "secret", "password", "token", "auth", "credential", "url", "db_"]
            for key in list(safe_env.keys()):
                k_lower = key.lower()
                if any(pattern in k_lower for pattern in sensitive_patterns):
                    safe_env[key] = "[REDACTED_FOR_SECURITY]"

            proc = subprocess.run(
                [sys.executable, "-c", runner],
                capture_output=True, text=True,
                timeout=self.SANDBOX_TIMEOUT,
                cwd=os.path.dirname(tool.file_path),
                env=safe_env,
            )
            elapsed = (time.perf_counter() - start) * 1000

            if proc.returncode == 0:
                stdout = proc.stdout.strip()[:self.MAX_OUTPUT]
                try:
                    data = json.loads(stdout)
                    success = data.get("success", True)
                    output = data.get("output", data.get("result", stdout))
                    error = data.get("error", "")
                except json.JSONDecodeError:
                    success = True
                    output = stdout
                    error = ""
                return ToolExecutionResult(
                    tool_name=tool.name, success=success,
                    stdout=str(output) if output else "",
                    stderr=str(error) if error else proc.stderr.strip()[:self.MAX_OUTPUT],
                    exit_code=0 if success else 1,
                    error_type="sandbox_tool_error" if not success else None,
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.FILE_BASED,
                )
            else:
                return ToolExecutionResult(
                    tool_name=tool.name, success=False,
                    stdout=proc.stdout.strip()[:self.MAX_OUTPUT],
                    stderr=proc.stderr.strip()[:self.MAX_OUTPUT],
                    exit_code=proc.returncode,
                    error_type="sandbox_crash",
                    execution_time_ms=round(elapsed, 2),
                    source=ToolSource.FILE_BASED,
                )
        except subprocess.TimeoutExpired:
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=f"Sandbox timeout ({self.SANDBOX_TIMEOUT}s)",
                exit_code=-1,
                error_type="sandbox_timeout",
                source=ToolSource.FILE_BASED,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=str(e),
                exit_code=-1,
                error_type="sandbox_system_error",
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.FILE_BASED,
            )

    def health_check(self, tool: UniversalToolDef) -> bool:
        return bool(tool.file_path) and os.path.isfile(tool.file_path)


# ═════════════════════════════════════════════════════════════════════
#  MCP Tool Adapter — dispatches to MCP servers
# ═════════════════════════════════════════════════════════════════════

class MCPToolAdapter(ToolAdapter):
    """
    Bridges AERIS's universal tool system to external MCP-protocol
    servers via the existing McpToolRegistry.
    """

    def execute(self, tool: UniversalToolDef, **kwargs) -> ToolExecutionResult:
        start = time.perf_counter()
        try:
            from tools.mcp_bridge import get_mcp_registry
            mcp = get_mcp_registry()

            real_tool_name = tool.name
            if tool.mcp_server_name and tool.name.startswith(f"{tool.mcp_server_name}_"):
                real_tool_name = tool.name[len(tool.mcp_server_name) + 1:]
            qualified_name = f"{tool.mcp_server_name}.{real_tool_name}" if tool.mcp_server_name else tool.name
            mcp_result = mcp.dispatch(qualified_name, kwargs)
            elapsed = (time.perf_counter() - start) * 1000

            return ToolExecutionResult(
                tool_name=tool.name,
                success=mcp_result.success,
                stdout=str(mcp_result.output) if mcp_result.output else "",
                stderr=str(mcp_result.error) if mcp_result.error else "",
                exit_code=0 if mcp_result.success else 1,
                error_type="mcp_error" if not mcp_result.success else None,
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.MCP_SERVER,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolExecutionResult(
                tool_name=tool.name, success=False,
                stderr=str(e),
                exit_code=-1,
                error_type="mcp_system_error",
                execution_time_ms=round(elapsed, 2),
                source=ToolSource.MCP_SERVER,
            )

    def health_check(self, tool: UniversalToolDef) -> bool:
        try:
            from tools.mcp_bridge import get_mcp_registry
            mcp = get_mcp_registry()
            servers = mcp.list_servers()
            for s in servers:
                if s["name"] == tool.mcp_server_name and s["status"] == "connected":
                    return True
            return False
        except Exception:
            return False


# ═════════════════════════════════════════════════════════════════════
#  Adapter Factory — returns the correct adapter for a tool's source
# ═════════════════════════════════════════════════════════════════════

_cli_adapter = CLIToolAdapter()
_api_adapter = APIToolAdapter()
_file_adapter_inline = FileToolAdapter(use_sandbox=False)
_file_adapter_sandbox = FileToolAdapter(use_sandbox=True)
_mcp_adapter = MCPToolAdapter()


def get_adapter_for(tool: UniversalToolDef, sandbox: bool = False) -> Optional[ToolAdapter]:
    """Return the correct adapter based on a tool's source type."""
    if tool.source == ToolSource.CLI_BASED:
        return _cli_adapter
    elif tool.source == ToolSource.API_BASED:
        return _api_adapter
    elif tool.source in (ToolSource.FILE_BASED, ToolSource.FORGED, ToolSource.USER_SCRIPT):
        return _file_adapter_sandbox if sandbox else _file_adapter_inline
    elif tool.source == ToolSource.MCP_SERVER:
        return _mcp_adapter
    return None  # Builtin / plugin tools use their own func callable
