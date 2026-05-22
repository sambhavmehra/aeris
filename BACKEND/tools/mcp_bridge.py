"""
AERIS — MCP (Model Context Protocol) Bridge
═══════════════════════════════════════════════════════════════════════
Connects AERIS to external MCP-protocol servers, enabling the use of
any MCP-compliant tool as a first-class AERIS tool.

Supports two transports:
  • stdio  — launches a subprocess and communicates via stdin/stdout
  • sse    — connects to an HTTP SSE endpoint (Server-Sent Events)

Configuration is loaded from data/mcp_servers.json. Each entry defines
a server name, transport, command/url, and optional environment vars.

Example mcp_servers.json:
  [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {},
      "enabled": true,
      "auto_connect": true
    },
    {
      "name": "web-search",
      "transport": "sse",
      "url": "http://localhost:3001/sse",
      "enabled": true,
      "auto_connect": true
    }
  ]
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisMCPBridge")


# ═════════════════════════════════════════════════════════════════════
#  Data Models
# ═════════════════════════════════════════════════════════════════════

def parse_mcp_input_schema(schema_dict: dict) -> Any:
    from tools.tool_interface import ToolInputSchema, ParamSchema
    if not isinstance(schema_dict, dict):
        return ToolInputSchema()
    
    properties = schema_dict.get("properties", {})
    required_list = schema_dict.get("required", [])
    
    params = []
    for param_name, param_info in properties.items():
        if isinstance(param_info, dict):
            param_type = param_info.get("type", "string")
            param_desc = param_info.get("description", "")
            param_default = param_info.get("default")
            param_enum = param_info.get("enum")
            if param_type not in ("string", "integer", "boolean", "object", "array"):
                param_type = "string"
            is_req = param_name in required_list
            params.append(ParamSchema(
                name=param_name,
                type=param_type,
                description=param_desc,
                required=is_req,
                default=param_default,
                enum=param_enum
            ))
    return ToolInputSchema(params=params)


@dataclass
class MCPToolDefinition:
    """Describes a single tool exposed by an MCP server."""
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    server_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server_name": self.server_name,
        }


@dataclass
class MCPDispatchResult:
    """The result of calling a tool on an MCP server."""
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    transport: str = "stdio"          # "stdio" | "sse"
    command: List[str] = field(default_factory=list)   # For stdio
    url: str = ""                     # For SSE
    env: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    auto_connect: bool = True
    timeout_seconds: int = 30

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        return cls(
            name=data.get("name", "unknown"),
            transport=data.get("transport", "stdio"),
            command=data.get("command", []),
            url=data.get("url", ""),
            env=data.get("env", {}),
            enabled=data.get("enabled", True),
            auto_connect=data.get("auto_connect", True),
            timeout_seconds=data.get("timeout_seconds", 30),
        )


# ═════════════════════════════════════════════════════════════════════
#  JSON-RPC Helpers (MCP is built on JSON-RPC 2.0)
# ═════════════════════════════════════════════════════════════════════

def _jsonrpc_request(method: str, params: Optional[Dict] = None, req_id: Optional[str] = None) -> str:
    """Build a JSON-RPC 2.0 request string."""
    msg = {
        "jsonrpc": "2.0",
        "method": method,
        "id": req_id or str(uuid.uuid4()),
    }
    if params is not None:
        msg["params"] = params
    return json.dumps(msg)


def _parse_jsonrpc_response(raw: str) -> Dict[str, Any]:
    """Parse a JSON-RPC 2.0 response."""
    try:
        data = json.loads(raw.strip())
        return data
    except json.JSONDecodeError:
        return {"error": {"code": -32700, "message": f"Parse error: {raw[:200]}"}}


# ═════════════════════════════════════════════════════════════════════
#  MCP Server Connection (stdio transport)
# ═════════════════════════════════════════════════════════════════════

class MCPStdioConnection:
    """
    Manages a single MCP server subprocess using stdio transport.
    Sends JSON-RPC messages via stdin and reads responses from stdout.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._connected = False
        self._server_info: Dict[str, Any] = {}
        self._tools: List[MCPToolDefinition] = []

    @property
    def connected(self) -> bool:
        return self._connected and self.process is not None and self.process.poll() is None

    def connect(self) -> bool:
        """Launch the MCP server subprocess and perform initialization handshake."""
        if self.connected:
            return True

        if not self.config.command:
            logger.error(f"MCP server '{self.config.name}': no command specified.")
            return False

        try:
            # Expand environment variable placeholders like ${VAR}
            resolved_env = {
                k: os.path.expandvars(v) if isinstance(v, str) else v
                for k, v in self.config.env.items()
            }
            env = {**os.environ, **resolved_env}

            # On Windows, npx/npm/node are .cmd wrappers that need shell=True
            is_windows = sys.platform == "win32"
            command = list(self.config.command)

            # Auto-fix common Windows command issues
            if is_windows and command:
                cmd_base = command[0].lower()
                if cmd_base in ("npx", "npm", "node", "yarn", "pnpm") and not cmd_base.endswith(".cmd"):
                    command[0] = command[0] + ".cmd"

            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
                shell=is_windows,
            )
            logger.info(f"MCP server '{self.config.name}': subprocess started (PID {self.process.pid}).")

            # MCP Initialize handshake
            init_result = self._send_request("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "AERIS",
                    "version": "1.0.0",
                },
            })

            if init_result and "error" not in init_result:
                self._server_info = init_result.get("result", {})
                # Send initialized notification
                self._send_notification("notifications/initialized")
                self._connected = True
                logger.info(f"MCP server '{self.config.name}': connected successfully.")
                # Discover tools
                self._discover_tools()
                return True
            else:
                err = init_result.get("error", {}).get("message", "Unknown error") if init_result else "No response"
                logger.error(f"MCP server '{self.config.name}': initialization failed — {err}")
                self.disconnect()
                return False

        except FileNotFoundError:
            logger.error(f"MCP server '{self.config.name}': command not found — {self.config.command}")
            return False
        except Exception as e:
            logger.error(f"MCP server '{self.config.name}': connection failed — {e}")
            self.disconnect()
            return False

    def disconnect(self):
        """Shut down the MCP server subprocess."""
        self._connected = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        self._tools = []
        logger.info(f"MCP server '{self.config.name}': disconnected.")

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Send a JSON-RPC request and wait for the response."""
        with self._lock:
            if not self.process or not self.process.stdin or not self.process.stdout:
                return None

            req_id = str(uuid.uuid4())
            message = _jsonrpc_request(method, params, req_id)

            try:
                self.process.stdin.write(message + "\n")
                self.process.stdin.flush()

                # Read response (line-delimited JSON-RPC)
                response_line = self.process.stdout.readline()
                if not response_line:
                    return None

                return _parse_jsonrpc_response(response_line)

            except (BrokenPipeError, OSError) as e:
                logger.error(f"MCP server '{self.config.name}': pipe error — {e}")
                self._connected = False
                return None

    def _send_notification(self, method: str, params: Optional[Dict] = None):
        """Send a JSON-RPC notification (no response expected)."""
        if not self.process or not self.process.stdin:
            return
        msg = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params:
            msg["params"] = params
        try:
            self.process.stdin.write(json.dumps(msg) + "\n")
            self.process.stdin.flush()
        except Exception:
            pass

    def _discover_tools(self):
        """Query the server for available tools."""
        result = self._send_request("tools/list")
        if result and "result" in result:
            tools_data = result["result"].get("tools", [])
            self._tools = []
            for td in tools_data:
                self._tools.append(MCPToolDefinition(
                    name=td.get("name", ""),
                    description=td.get("description", ""),
                    input_schema=td.get("inputSchema", {}),
                    server_name=self.config.name,
                ))
            logger.info(
                f"MCP server '{self.config.name}': discovered {len(self._tools)} tool(s) — "
                f"{[t.name for t in self._tools]}"
            )

    def get_tools(self) -> List[MCPToolDefinition]:
        return list(self._tools)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPDispatchResult:
        """Invoke a tool on the MCP server."""
        start = time.perf_counter()

        if not self.connected:
            return MCPDispatchResult(
                success=False,
                error=f"MCP server '{self.config.name}' is not connected.",
            )

        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })

        elapsed = (time.perf_counter() - start) * 1000

        if result is None:
            return MCPDispatchResult(
                success=False,
                error=f"No response from MCP server '{self.config.name}'.",
                execution_time_ms=elapsed,
            )

        if "error" in result:
            err = result["error"]
            return MCPDispatchResult(
                success=False,
                error=err.get("message", str(err)),
                execution_time_ms=elapsed,
            )

        # MCP tool/call returns { content: [{ type, text }], isError?: bool }
        tool_result = result.get("result", {})
        is_error = tool_result.get("isError", False)

        content_parts = tool_result.get("content", [])
        output_parts = []
        for part in content_parts:
            if part.get("type") == "text":
                output_parts.append(part.get("text", ""))
            elif part.get("type") == "image":
                output_parts.append(f"[Image: {part.get('mimeType', 'unknown')}]")
            elif part.get("type") == "resource":
                output_parts.append(f"[Resource: {part.get('uri', 'unknown')}]")
            else:
                output_parts.append(json.dumps(part))

        output_text = "\n".join(output_parts) if output_parts else str(tool_result)

        return MCPDispatchResult(
            success=not is_error,
            output=output_text,
            error=output_text if is_error else None,
            execution_time_ms=elapsed,
        )


# ═════════════════════════════════════════════════════════════════════
#  MCP Server Connection (SSE transport)
# ═════════════════════════════════════════════════════════════════════

class MCPSSEConnection:
    """
    Manages a connection to an MCP server over HTTP SSE transport.
    Uses simple HTTP POST for requests and parses SSE for responses.
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._connected = False
        self._session_url: Optional[str] = None
        self._tools: List[MCPToolDefinition] = []

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Connect to an SSE-based MCP server."""
        if not self.config.url:
            logger.error(f"MCP server '{self.config.name}': no URL specified for SSE transport.")
            return False

        try:
            import urllib.request
            import urllib.error

            # Attempt to reach the SSE endpoint
            base_url = self.config.url.rstrip("/")

            # Try initialize via POST
            init_payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "initialize",
                "id": str(uuid.uuid4()),
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "AERIS", "version": "1.0.0"},
                },
            }).encode("utf-8")

            # SSE MCP typically has a /message endpoint
            message_url = base_url.replace("/sse", "/message")
            if message_url == base_url:
                message_url = base_url + "/message"

            self._session_url = message_url

            req = urllib.request.Request(
                message_url,
                data=init_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "result" in data:
                    self._connected = True
                    logger.info(f"MCP SSE server '{self.config.name}': connected at {message_url}")
                    self._discover_tools()
                    return True
                else:
                    logger.error(f"MCP SSE server '{self.config.name}': init failed — {data}")
                    return False

        except Exception as e:
            logger.warning(f"MCP SSE server '{self.config.name}': connection failed — {e}")
            return False

    def disconnect(self):
        self._connected = False
        self._tools = []
        self._session_url = None

    def _send_request(self, method: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Send a JSON-RPC request over HTTP POST."""
        if not self._session_url:
            return None

        try:
            import urllib.request

            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": method,
                "id": str(uuid.uuid4()),
                "params": params or {},
            }).encode("utf-8")

            req = urllib.request.Request(
                self._session_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except Exception as e:
            logger.error(f"MCP SSE '{self.config.name}': request failed — {e}")
            return None

    def _discover_tools(self):
        """Query for available tools."""
        result = self._send_request("tools/list")
        if result and "result" in result:
            tools_data = result["result"].get("tools", [])
            self._tools = [
                MCPToolDefinition(
                    name=td.get("name", ""),
                    description=td.get("description", ""),
                    input_schema=td.get("inputSchema", {}),
                    server_name=self.config.name,
                )
                for td in tools_data
            ]
            logger.info(
                f"MCP SSE server '{self.config.name}': discovered {len(self._tools)} tool(s)."
            )

    def get_tools(self) -> List[MCPToolDefinition]:
        return list(self._tools)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPDispatchResult:
        """Invoke a tool on the SSE MCP server."""
        start = time.perf_counter()

        if not self.connected:
            return MCPDispatchResult(
                success=False,
                error=f"MCP SSE server '{self.config.name}' is not connected.",
            )

        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        elapsed = (time.perf_counter() - start) * 1000

        if result is None:
            return MCPDispatchResult(success=False, error="No response.", execution_time_ms=elapsed)

        if "error" in result:
            return MCPDispatchResult(
                success=False,
                error=result["error"].get("message", str(result["error"])),
                execution_time_ms=elapsed,
            )

        tool_result = result.get("result", {})
        is_error = tool_result.get("isError", False)
        content_parts = tool_result.get("content", [])
        output_parts = [
            part.get("text", json.dumps(part))
            for part in content_parts
        ]
        output_text = "\n".join(output_parts) if output_parts else str(tool_result)

        return MCPDispatchResult(
            success=not is_error,
            output=output_text,
            error=output_text if is_error else None,
            execution_time_ms=elapsed,
        )


# ═════════════════════════════════════════════════════════════════════
#  MCP Tool Registry — Central Hub
# ═════════════════════════════════════════════════════════════════════

class McpToolRegistry:
    """
    Central registry that manages connections to all configured MCP
    servers and provides tool discovery and dispatch.
    """

    _CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "mcp_servers.json"

    def __init__(self):
        self._servers: Dict[str, Any] = {}           # name -> connection object
        self._configs: Dict[str, MCPServerConfig] = {}
        self._tool_index: Dict[str, str] = {}        # "server.tool" -> server_name
        self._load_config()
        self._auto_connect()

    # ── Config Loading ────────────────────────────────────────────────

    def _load_config(self):
        """Load server configurations from mcp_servers.json."""
        if not self._CONFIG_FILE.exists():
            logger.info(
                f"No MCP config found at {self._CONFIG_FILE}. "
                f"MCP bridge will run with zero servers. "
                f"Create mcp_servers.json to add MCP servers."
            )
            return

        try:
            data = json.loads(self._CONFIG_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.warning("mcp_servers.json must be a JSON array.")
                return

            for entry in data:
                config = MCPServerConfig.from_dict(entry)
                if config.enabled:
                    self._configs[config.name] = config
                    logger.info(f"Loaded MCP server config: {config.name} ({config.transport})")
        except Exception as e:
            logger.error(f"Failed to load MCP server config: {e}")

    def _auto_connect(self):
        """Connect to all servers that have auto_connect enabled."""
        for name, config in self._configs.items():
            if config.auto_connect:
                self.connect_server(name)

    # ── Server Management ─────────────────────────────────────────────

    def connect_server(self, name: str) -> bool:
        """Connect to a specific MCP server by name."""
        config = self._configs.get(name)
        if not config:
            logger.error(f"No config found for MCP server '{name}'.")
            return False

        if name in self._servers and self._servers[name].connected:
            logger.info(f"MCP server '{name}' is already connected.")
            return True

        if config.transport == "stdio":
            conn = MCPStdioConnection(config)
        elif config.transport == "sse":
            conn = MCPSSEConnection(config)
        else:
            logger.error(f"Unknown transport '{config.transport}' for MCP server '{name}'.")
            return False

        success = conn.connect()
        if success:
            self._servers[name] = conn
            # Index tools
            for tool in conn.get_tools():
                qualified = f"{name}.{tool.name}"
                self._tool_index[qualified] = name
            
            # Register tools in Universal & Global registry
            try:
                from tools.universal_registry import get_universal_registry
                from tools.tool_interface import UniversalToolDef, ToolSource, ToolStatus, ToolOutputSchema, RiskLevel
                from tools.tool_registry import global_tool_registry, RiskLevel as OldRiskLevel
                universal_reg = get_universal_registry()
                for tool in conn.get_tools():
                    input_schema = parse_mcp_input_schema(tool.input_schema)
                    registry_name = f"{name}_{tool.name}"
                    
                    utool = UniversalToolDef(
                        name=registry_name,
                        description=tool.description or f"MCP tool {tool.name} from {name} server",
                        input_schema=input_schema,
                        output_schema=ToolOutputSchema(description="Unstructured string result"),
                        risk_level=RiskLevel.MEDIUM,
                        category="mcp",
                        source=ToolSource.MCP_SERVER,
                        status=ToolStatus.ENABLED,
                        mcp_server_name=name
                    )
                    universal_reg.register_tool(utool)
                    
                    # Also register wrapper in old registry
                    def make_wrapper(t_name, u_reg):
                        async def mcp_tool_wrapper(**kwargs):
                            return await u_reg.execute_async(t_name, **kwargs)
                        return mcp_tool_wrapper
                    
                    required_params = [p.name for p in input_schema.params if p.required]
                    global_tool_registry.register(
                        registry_name,
                        utool.description,
                        make_wrapper(registry_name, universal_reg),
                        required_params,
                        OldRiskLevel.MEDIUM,
                        "mcp"
                    )
                logger.info(f"Registered {len(conn.get_tools())} tools from MCP server '{name}' to Universal/Global Registry.")
            except Exception as e:
                logger.error(f"Failed to register MCP tools of '{name}' to registries: {e}")
            
            return True
        return False

    def disconnect_server(self, name: str) -> bool:
        """Disconnect a specific MCP server."""
        conn = self._servers.get(name)
        if conn:
            conn.disconnect()
            # Remove from tool index
            to_remove = [k for k, v in self._tool_index.items() if v == name]
            for k in to_remove:
                del self._tool_index[k]
            del self._servers[name]
            
            # Unregister tools
            try:
                from tools.universal_registry import get_universal_registry
                from tools.tool_registry import global_tool_registry
                universal_reg = get_universal_registry()
                
                tools_to_remove = [t_name for t_name, t in list(universal_reg._tools.items()) if getattr(t, 'mcp_server_name', None) == name or t_name.startswith(f"{name}_")]
                for t_name in tools_to_remove:
                    universal_reg.unregister_tool(t_name)
                    global_tool_registry._tools.pop(t_name, None)
                logger.info(f"Unregistered tools of MCP server '{name}' from Universal/Global Registry.")
            except Exception as e:
                logger.error(f"Failed to unregister tools of MCP server '{name}': {e}")
            
            return True
        return False

    def reconnect_server(self, name: str) -> bool:
        """Reconnect a server (disconnect + connect)."""
        self.disconnect_server(name)
        return self.connect_server(name)

    # ── Queries ───────────────────────────────────────────────────────

    def list_servers(self) -> List[Dict[str, Any]]:
        """Return status of all configured MCP servers."""
        servers = []
        for name, config in self._configs.items():
            conn = self._servers.get(name)
            status = "connected" if conn and conn.connected else "disconnected"
            tool_count = len(conn.get_tools()) if conn and conn.connected else 0
            servers.append({
                "name": name,
                "transport": config.transport,
                "status": status,
                "tool_count": tool_count,
                "command": config.command if config.transport == "stdio" else None,
                "url": config.url if config.transport == "sse" else None,
            })

        # Also include servers that connected but weren't in config
        for name, conn in self._servers.items():
            if name not in self._configs:
                servers.append({
                    "name": name,
                    "transport": "unknown",
                    "status": "connected" if conn.connected else "disconnected",
                    "tool_count": len(conn.get_tools()),
                })

        return servers

    def list_tools(self) -> List[MCPToolDefinition]:
        """Return all tools from all connected servers."""
        tools = []
        for conn in self._servers.values():
            if conn.connected:
                tools.extend(conn.get_tools())
        return tools

    def get_server_tools(self, server_name: str) -> List[MCPToolDefinition]:
        """Return tools for a specific server."""
        conn = self._servers.get(server_name)
        if conn and conn.connected:
            return conn.get_tools()
        return []

    # ── Tool Dispatch ─────────────────────────────────────────────────

    def dispatch(self, qualified_name: str, arguments: Dict[str, Any]) -> MCPDispatchResult:
        """
        Dispatch a tool call to the appropriate MCP server.

        qualified_name format: "server_name.tool_name"
        """
        # Parse the qualified name
        if "." in qualified_name:
            server_name, tool_name = qualified_name.split(".", 1)
        else:
            # Try to find the tool in any connected server
            tool_name = qualified_name
            server_name = self._find_server_for_tool(tool_name)
            if not server_name:
                return MCPDispatchResult(
                    success=False,
                    error=f"Tool '{qualified_name}' not found on any connected MCP server.",
                )

        conn = self._servers.get(server_name)
        if not conn or not conn.connected:
            return MCPDispatchResult(
                success=False,
                error=f"MCP server '{server_name}' is not connected.",
            )

        return conn.call_tool(tool_name, arguments)

    def _find_server_for_tool(self, tool_name: str) -> Optional[str]:
        """Find which server hosts a tool by name (unqualified)."""
        for conn_name, conn in self._servers.items():
            if conn.connected:
                for tool in conn.get_tools():
                    if tool.name == tool_name:
                        return conn_name
        return None

    # ── Dynamic Server Addition ───────────────────────────────────────

    def add_server(self, config: MCPServerConfig) -> bool:
        """
        Add and optionally connect a new MCP server at runtime.
        Does NOT persist to config file (call save_config() for that).
        """
        self._configs[config.name] = config
        if config.auto_connect:
            return self.connect_server(config.name)
        return True

    def remove_server(self, name: str) -> bool:
        """Remove a server completely (disconnect + remove config)."""
        self.disconnect_server(name)
        self._configs.pop(name, None)
        return True

    def save_config(self):
        """Persist current server configs to mcp_servers.json."""
        try:
            self._CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = []
            for config in self._configs.values():
                entry = {
                    "name": config.name,
                    "transport": config.transport,
                    "enabled": config.enabled,
                    "auto_connect": config.auto_connect,
                    "timeout_seconds": config.timeout_seconds,
                }
                if config.transport == "stdio":
                    entry["command"] = config.command
                elif config.transport == "sse":
                    entry["url"] = config.url
                if config.env:
                    entry["env"] = config.env
                data.append(entry)

            self._CONFIG_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
            logger.info(f"MCP config saved to {self._CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Failed to save MCP config: {e}")

    # ── Health Check ──────────────────────────────────────────────────

    def health_check(self, server_name: str) -> Dict[str, Any]:
        """Check the health of a specific MCP server."""
        conn = self._servers.get(server_name)
        if not conn:
            return {"server": server_name, "healthy": False, "reason": "not_configured"}
        if not conn.connected:
            return {"server": server_name, "healthy": False, "reason": "disconnected"}

        # Try pinging by listing tools
        try:
            tools = conn.get_tools()
            return {
                "server": server_name,
                "healthy": True,
                "tool_count": len(tools),
            }
        except Exception as e:
            return {"server": server_name, "healthy": False, "reason": str(e)}

    def health_check_all(self) -> List[Dict[str, Any]]:
        """Check health of all configured servers."""
        return [self.health_check(name) for name in self._configs]

    # ── Shutdown ──────────────────────────────────────────────────────

    def shutdown(self):
        """Disconnect all servers gracefully."""
        for name in list(self._servers.keys()):
            self.disconnect_server(name)
        logger.info("MCP bridge shut down — all servers disconnected.")


# ═════════════════════════════════════════════════════════════════════
#  Global Singleton
# ═════════════════════════════════════════════════════════════════════

_mcp_registry: Optional[McpToolRegistry] = None


def get_mcp_registry() -> McpToolRegistry:
    """Return the global MCP tool registry singleton."""
    global _mcp_registry
    if _mcp_registry is None:
        _mcp_registry = McpToolRegistry()
    return _mcp_registry
