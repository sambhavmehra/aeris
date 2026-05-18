"""
Aeris AI OS — MCP Tool Bridge
Allows Aeris to dynamically discover and connect to external tools/APIs.
Inspired by claw-code's mcp_tool_bridge.rs.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class McpServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class McpTool:
    qualified_name: str
    server_name: str
    description: str
    input_schema: dict = field(default_factory=dict)


@dataclass
class McpServer:
    name: str
    transport: str                  # "stdio" | "http" | "websocket"
    status: McpServerStatus = McpServerStatus.DISCONNECTED
    tools: list[McpTool] = field(default_factory=list)
    last_error: Optional[str] = None
    connected_at: Optional[str] = None


@dataclass
class McpToolResult:
    tool_name: str
    success: bool
    output: Any = None
    error: Optional[str] = None


class McpToolRegistry:
    """
    Registry that tracks external MCP-style tool servers.
    Allows Aeris to dynamically discover/invoke tools from external systems
    without rewriting core logic.
    """

    def __init__(self) -> None:
        self._servers: dict[str, McpServer] = {}

    def register_server(self, name: str, transport: str = "http") -> McpServer:
        server = McpServer(name=name, transport=transport)
        self._servers[name] = server
        return server

    def connect(self, server_name: str) -> bool:
        server = self._servers.get(server_name)
        if not server:
            return False
        server.status = McpServerStatus.CONNECTED
        server.connected_at = datetime.now().isoformat()
        return True

    def disconnect(self, server_name: str) -> bool:
        server = self._servers.get(server_name)
        if not server:
            return False
        server.status = McpServerStatus.DISCONNECTED
        server.tools.clear()
        return True

    def register_tool(self, server_name: str, tool: McpTool) -> bool:
        server = self._servers.get(server_name)
        if not server:
            return False
        server.tools.append(tool)
        return True

    def discover_tools(self, server_name: str) -> list[McpTool]:
        server = self._servers.get(server_name)
        if not server or server.status != McpServerStatus.CONNECTED:
            return []
        return list(server.tools)

    def list_all_tools(self) -> list[McpTool]:
        all_tools: list[McpTool] = []
        for server in self._servers.values():
            if server.status == McpServerStatus.CONNECTED:
                all_tools.extend(server.tools)
        return all_tools

    def dispatch(self, qualified_name: str, arguments: dict | None = None) -> McpToolResult:
        for server in self._servers.values():
            for tool in server.tools:
                if tool.qualified_name == qualified_name:
                    # In production, this forwards to the MCP server's transport
                    return McpToolResult(
                        tool_name=qualified_name,
                        success=True,
                        output=f"MCP tool '{qualified_name}' dispatched with args={arguments}",
                    )
        return McpToolResult(
            tool_name=qualified_name,
            success=False,
            error=f"MCP tool '{qualified_name}' not found in any connected server",
        )

    def list_servers(self) -> list[dict]:
        return [
            {
                "name": s.name,
                "transport": s.transport,
                "status": s.status.value,
                "tool_count": len(s.tools),
                "connected_at": s.connected_at,
            }
            for s in self._servers.values()
        ]


# Global singleton
_global_mcp: Optional[McpToolRegistry] = None


def get_mcp_registry() -> McpToolRegistry:
    global _global_mcp
    if _global_mcp is None:
        _global_mcp = McpToolRegistry()
    return _global_mcp
