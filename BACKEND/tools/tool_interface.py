"""
AERIS — Universal Tool Interface Standard
═══════════════════════════════════════════════════════════════════════
Defines the universal contract that ALL tools must satisfy — whether
they are local Python functions, CLI wrappers, REST API proxies, MCP
servers, file-based scripts, or user-contributed plugins.

Every tool is described by:
  • name            – unique identifier (snake_case)
  • description     – what the tool does (shown to LLM + user)
  • input_schema    – JSON-Schema describing expected kwargs
  • output_schema   – JSON-Schema describing return shape
  • execution_method – how the tool runs

This file contains ONLY data-models and ABCs — zero side-effects.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import abc
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# ─── Risk / Permission Levels ────────────────────────────────────────
class RiskLevel(str, Enum):
    SAFE     = "safe"       # Read-only, no side effects
    LOW      = "low"        # Minor side effects (open browser tab)
    MEDIUM   = "medium"     # Modifies files, runs commands
    HIGH     = "high"       # Destructive (delete, shutdown, reboot)
    CRITICAL = "critical"   # System-level danger (rm -rf, format)


# ─── Tool Source / Type ──────────────────────────────────────────────
class ToolSource(str, Enum):
    BUILTIN     = "builtin"       # Hardcoded in tool_registry.py
    FILE_BASED  = "file_based"    # .py file in aeris_tools/
    API_BASED   = "api_based"     # REST / gRPC endpoint
    CLI_BASED   = "cli_based"     # Wraps a shell command
    MCP_SERVER  = "mcp_server"    # External MCP server
    PLUGIN      = "plugin"        # Loaded from plugins/ directory
    FORGED      = "forged"        # AI-generated at runtime via ToolForge
    USER_SCRIPT = "user_script"   # User-provided Python / script file


class ToolStatus(str, Enum):
    ENABLED  = "enabled"
    DISABLED = "disabled"
    ERROR    = "error"      # Failed to load / verify


# ─── JSON-Schema helpers ─────────────────────────────────────────────
@dataclass(frozen=True)
class ParamSchema:
    """Describes a single parameter in an input/output schema."""
    name: str
    type: str = "string"            # "string" | "integer" | "boolean" | "object" | "array"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[str]] = None

    def to_json_schema(self) -> Dict[str, Any]:
        schema: Dict[str, Any] = {"type": self.type, "description": self.description}
        if self.default is not None:
            schema["default"] = self.default
        if self.enum:
            schema["enum"] = self.enum
        return schema


@dataclass
class ToolInputSchema:
    """Full input schema (list of parameters)."""
    params: List[ParamSchema] = field(default_factory=list)

    def to_json_schema(self) -> Dict[str, Any]:
        properties = {p.name: p.to_json_schema() for p in self.params}
        required = [p.name for p in self.params if p.required]
        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    @property
    def required_param_names(self) -> List[str]:
        return [p.name for p in self.params if p.required]


@dataclass
class ToolOutputSchema:
    """Expected output shape (informational — used by LLM for planning)."""
    description: str = "Unstructured string result"
    fields: List[ParamSchema] = field(default_factory=list)

    def to_json_schema(self) -> Dict[str, Any]:
        if not self.fields:
            return {"type": "string", "description": self.description}
        properties = {f.name: f.to_json_schema() for f in self.fields}
        return {
            "type": "object",
            "description": self.description,
            "properties": properties,
        }


# ─── Universal Tool Definition ───────────────────────────────────────
@dataclass
class UniversalToolDef:
    """
    The single source of truth for every tool in AERIS.

    This replaces the old `ToolDefinition` by adding:
      – input_schema / output_schema  (structured JSON-Schema)
      – source (builtin | file | api | cli | mcp | plugin | forged)
      – status (enabled | disabled | error)
      – tags for fuzzy matching by the Tool Selector
      – version tracking
    """
    name: str
    description: str
    func: Optional[Callable] = None           # None for API/MCP tools
    input_schema: ToolInputSchema = field(default_factory=ToolInputSchema)
    output_schema: ToolOutputSchema = field(default_factory=ToolOutputSchema)
    risk_level: RiskLevel = RiskLevel.SAFE
    category: str = "general"
    source: ToolSource = ToolSource.BUILTIN
    status: ToolStatus = ToolStatus.ENABLED
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = "aeris"
    timeout: int = 30
    approval_requirement: bool = False
    # Runtime metadata (populated after load)
    loaded_at: Optional[str] = None
    file_path: Optional[str] = None           # For file-based tools
    endpoint_url: Optional[str] = None        # For API-based tools
    cli_command_template: Optional[str] = None # For CLI-based tools
    mcp_server_name: Optional[str] = None     # For MCP tools

    # ── Convenience properties ────────────────────────────────────────

    @property
    def required_params(self) -> List[str]:
        return self.input_schema.required_param_names

    @property
    def is_enabled(self) -> bool:
        return self.status == ToolStatus.ENABLED

    @property
    def is_callable(self) -> bool:
        return self.func is not None and self.status == ToolStatus.ENABLED

    # ── Serialisation ─────────────────────────────────────────────────

    def to_json_schema(self) -> Dict[str, Any]:
        """Expose the tool's details in a standard JSON Schema layout."""
        return {
            "name": self.name,
            "description": self.description,
            "args": self.input_schema.to_json_schema(),
            "risk_level": self.risk_level.value,
            "timeout": self.timeout,
            "approval_requirement": self.approval_requirement,
        }

    def to_metadata(self) -> Dict[str, Any]:
        """Compact metadata for the LLM planner (backwards-compatible)."""
        return {
            "name": self.name,
            "description": self.description,
            "required_params": self.required_params,
            "risk_level": self.risk_level.value,
            "category": self.category,
            "timeout": self.timeout,
            "approval_requirement": self.approval_requirement,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """Full serialisation for APIs / admin dashboards."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.to_json_schema(),
            "output_schema": self.output_schema.to_json_schema(),
            "risk_level": self.risk_level.value,
            "category": self.category,
            "source": self.source.value,
            "status": self.status.value,
            "tags": self.tags,
            "version": self.version,
            "author": self.author,
            "timeout": self.timeout,
            "approval_requirement": self.approval_requirement,
            "loaded_at": self.loaded_at,
            "file_path": self.file_path,
            "endpoint_url": self.endpoint_url,
            "cli_command_template": self.cli_command_template,
            "mcp_server_name": self.mcp_server_name,
        }

    def to_llm_string(self) -> str:
        """One-line LLM-friendly description."""
        params_str = ", ".join(self.required_params) if self.required_params else "none"
        return f"- {self.name}({params_str}): {self.description} [risk: {self.risk_level.value}]"


# ─── Structured Execution Result ─────────────────────────────────────
@dataclass
class ToolExecutionResult:
    """Unified structured output from any tool execution (Task 1 & 2)."""
    tool_name: str
    success: bool
    
    # Task 1: Output Unification
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Task 2: Execution Trace
    step_id: str = ""
    parent_task_id: str = ""
    retry_count: int = 0
    tool_version: str = "1.0.0"
    execution_time_ms: float = 0.0
    
    # Core Tracking
    source: ToolSource = ToolSource.BUILTIN
    receipt_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "stdout": self.stdout[:5000],
            "stderr": self.stderr[:5000],
            "exit_code": self.exit_code,
            "error_type": self.error_type,
            "metadata": self.metadata,
            "step_id": self.step_id,
            "parent_task_id": self.parent_task_id,
            "retry_count": self.retry_count,
            "tool_version": self.tool_version,
            "execution_time_ms": self.execution_time_ms,
            "source": self.source.value,
            "receipt_id": self.receipt_id,
        }

    @property
    def result(self) -> Any:
        """Alias for stdout to maintain backward compatibility."""
        return self.stdout

    @property
    def error(self) -> Optional[str]:
        """Alias for stderr to maintain backward compatibility."""
        return self.stderr if self.stderr else None


# ─── Abstract Tool Adapter ──────────────────────────────────────────
class ToolAdapter(abc.ABC):
    """
    Base class for adapters that bridge non-callable tool sources
    (API endpoints, CLI commands, MCP servers) into the universal
    execution interface.
    """

    @abc.abstractmethod
    def execute(self, tool: UniversalToolDef, **kwargs) -> ToolExecutionResult:
        """Execute the tool with the given kwargs and return a structured result."""

    @abc.abstractmethod
    def health_check(self, tool: UniversalToolDef) -> bool:
        """Return True if the tool's backing service is reachable."""
