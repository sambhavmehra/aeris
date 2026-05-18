"""
AERIS — Dynamic Tool Loader
═══════════════════════════════════════════════════════════════════════
Loads tools at runtime from multiple sources:

  1. File-based   — Python files in aeris_tools/ with a run() entry
  2. API-based    — REST endpoints described by a JSON manifest
  3. CLI-based    — Shell command templates described by a JSON manifest
  4. User scripts — Arbitrary .py files the user points to

Supports hot-loading:
  • load_tool()   — load a single tool dynamically
  • unload_tool() — remove a loaded tool
  • reload_tool() — unload + re-load
  • scan_tools_dir() — auto-discover .py files in aeris_tools/

Manifest format (aeris_tools/tool_manifest.json):
    [
      {
        "name": "my_tool",
        "description": "Does something cool",
        "source": "file_based",
        "file_path": "aeris_tools/my_tool.py",
        "risk_level": "medium",
        "category": "utility",
        "input_params": [
          {"name": "query", "type": "string", "required": true}
        ]
      },
      ...
    ]
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisDynamicLoader")

from tools.tool_interface import (
    ParamSchema,
    RiskLevel,
    ToolInputSchema,
    ToolOutputSchema,
    ToolSource,
    ToolStatus,
    UniversalToolDef,
)


# ─── Default directories ─────────────────────────────────────────────
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_DEFAULT_TOOLS_DIR = _BACKEND_DIR.parent / "aeris_tools"
_DEFAULT_MANIFEST = _DEFAULT_TOOLS_DIR / "tool_manifest.json"


class DynamicToolLoader:
    """
    Discovers, validates, and loads tools from the file system and
    external manifests into UniversalToolDef instances.
    """

    def __init__(self, tools_dir: str | Path | None = None):
        self.tools_dir = Path(tools_dir) if tools_dir else _DEFAULT_TOOLS_DIR
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self._loaded: Dict[str, UniversalToolDef] = {}

    # ── Scan & Auto-Discover ──────────────────────────────────────────

    def scan_tools_dir(self) -> List[UniversalToolDef]:
        """
        Scan the aeris_tools directory for .py files with run() functions.
        Also reads tool_manifest.json if present.
        Returns list of newly discovered tools.
        """
        discovered: List[UniversalToolDef] = []

        # 1. Manifest-based loading
        manifest_tools = self._load_manifest()
        for tool in manifest_tools:
            if tool.name not in self._loaded:
                self._loaded[tool.name] = tool
                discovered.append(tool)

        # 2. Auto-discover .py files not in manifest
        manifest_names = {t.name for t in manifest_tools}
        for py_file in self.tools_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            tool_name = py_file.stem
            if tool_name in self._loaded or tool_name in manifest_names:
                continue
            if tool_name == "manifest":
                continue

            # Validate the file has a run() function
            tool_def = self._load_py_file(py_file)
            if tool_def:
                self._loaded[tool_def.name] = tool_def
                discovered.append(tool_def)

        if discovered:
            logger.info(f"Dynamic loader discovered {len(discovered)} new tool(s): {[t.name for t in discovered]}")
        return discovered

    # ── Single Tool Operations ────────────────────────────────────────

    def load_tool_from_file(self, file_path: str | Path) -> Optional[UniversalToolDef]:
        """Load a single tool from a Python file."""
        path = Path(file_path)
        if not path.exists():
            logger.error(f"Tool file not found: {path}")
            return None
        tool = self._load_py_file(path)
        if tool:
            self._loaded[tool.name] = tool
        return tool

    def load_tool_from_manifest_entry(self, entry: Dict[str, Any]) -> Optional[UniversalToolDef]:
        """Load a tool from a manifest entry dict."""
        tool = self._parse_manifest_entry(entry)
        if tool:
            self._loaded[tool.name] = tool
        return tool

    def unload_tool(self, name: str) -> bool:
        """Remove a dynamically loaded tool."""
        if name in self._loaded:
            del self._loaded[name]
            logger.info(f"Unloaded tool: {name}")
            return True
        return False

    def reload_tool(self, name: str) -> Optional[UniversalToolDef]:
        """Unload + re-load a tool."""
        tool = self._loaded.get(name)
        if not tool or not tool.file_path:
            return None
        self.unload_tool(name)
        return self.load_tool_from_file(tool.file_path)

    def enable_tool(self, name: str) -> bool:
        tool = self._loaded.get(name)
        if tool:
            tool.status = ToolStatus.ENABLED
            return True
        return False

    def disable_tool(self, name: str) -> bool:
        tool = self._loaded.get(name)
        if tool:
            tool.status = ToolStatus.DISABLED
            return True
        return False

    # ── Getters ───────────────────────────────────────────────────────

    def get_loaded_tools(self) -> List[UniversalToolDef]:
        return list(self._loaded.values())

    def get_tool(self, name: str) -> Optional[UniversalToolDef]:
        return self._loaded.get(name)

    def list_tool_names(self) -> List[str]:
        return list(self._loaded.keys())

    # ── Internal Helpers ──────────────────────────────────────────────

    def _load_py_file(self, path: Path) -> Optional[UniversalToolDef]:
        """Validate and wrap a Python file as a UniversalToolDef."""
        try:
            spec = importlib.util.spec_from_file_location(
                f"aeris_dtool_{path.stem}", str(path)
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            if not hasattr(mod, "run"):
                logger.warning(f"Skipping {path.name}: no 'run()' function found.")
                return None

            # Extract metadata from module-level attributes
            description = getattr(mod, "__description__", f"Dynamic tool from {path.name}")
            risk = getattr(mod, "__risk_level__", "medium")
            category = getattr(mod, "__category__", "dynamic")
            version = getattr(mod, "__version__", "1.0.0")
            author = getattr(mod, "__author__", "user")
            tags = getattr(mod, "__tags__", [])

            # Build input schema from function signature
            import inspect
            sig = inspect.signature(mod.run)
            params = []
            for pname, p in sig.parameters.items():
                if pname in ("self", "cls"):
                    continue
                required = (p.default is inspect.Parameter.empty) and (p.kind != inspect.Parameter.VAR_KEYWORD)
                ptype = "string"
                if p.annotation != inspect.Parameter.empty:
                    ann = p.annotation
                    if ann == int:
                        ptype = "integer"
                    elif ann == bool:
                        ptype = "boolean"
                    elif ann == float:
                        ptype = "number"
                    elif ann in (list, List):
                        ptype = "array"
                    elif ann in (dict, Dict):
                        ptype = "object"
                default_val = p.default if p.default is not inspect.Parameter.empty else None
                params.append(ParamSchema(
                    name=pname, type=ptype,
                    required=required, default=default_val,
                ))

            tool = UniversalToolDef(
                name=path.stem,
                description=description,
                func=mod.run,
                input_schema=ToolInputSchema(params=params),
                risk_level=RiskLevel(risk) if risk in RiskLevel._value2member_map_ else RiskLevel.MEDIUM,
                category=category,
                source=ToolSource.FILE_BASED,
                status=ToolStatus.ENABLED,
                tags=tags if isinstance(tags, list) else [],
                version=version,
                author=author,
                loaded_at=datetime.now().isoformat(),
                file_path=str(path),
            )
            logger.info(f"Loaded file-based tool: {tool.name} from {path}")
            return tool

        except Exception as e:
            logger.error(f"Failed to load tool from {path}: {e}")
            return None

    def _load_manifest(self) -> List[UniversalToolDef]:
        """Parse tool_manifest.json and return tool definitions."""
        manifest = self.tools_dir / "tool_manifest.json"
        if not manifest.exists():
            return []
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                logger.warning("tool_manifest.json must be a JSON array.")
                return []
            tools = []
            for entry in data:
                tool = self._parse_manifest_entry(entry)
                if tool:
                    tools.append(tool)
            return tools
        except Exception as e:
            logger.error(f"Failed to parse tool_manifest.json: {e}")
            return []

    def _parse_manifest_entry(self, entry: Dict[str, Any]) -> Optional[UniversalToolDef]:
        """Convert a single manifest entry to a UniversalToolDef."""
        try:
            name = entry["name"]
            description = entry.get("description", "")
            source_str = entry.get("source", "file_based")
            risk_str = entry.get("risk_level", "medium")
            category = entry.get("category", "dynamic")

            # Map source string
            source = ToolSource(source_str) if source_str in ToolSource._value2member_map_ else ToolSource.FILE_BASED
            risk = RiskLevel(risk_str) if risk_str in RiskLevel._value2member_map_ else RiskLevel.MEDIUM

            # Input params
            input_params = []
            for p in entry.get("input_params", []):
                input_params.append(ParamSchema(
                    name=p["name"],
                    type=p.get("type", "string"),
                    description=p.get("description", ""),
                    required=p.get("required", True),
                    default=p.get("default"),
                ))

            # Resolve file path
            file_path = entry.get("file_path")
            if file_path and not os.path.isabs(file_path):
                file_path = str(self.tools_dir.parent / file_path)

            # Load callable for file-based tools
            func = None
            if source in (ToolSource.FILE_BASED, ToolSource.USER_SCRIPT) and file_path:
                try:
                    spec = importlib.util.spec_from_file_location(f"aeris_mtool_{name}", file_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "run"):
                        func = mod.run
                except Exception as e:
                    logger.warning(f"Could not load callable for manifest tool '{name}': {e}")

            return UniversalToolDef(
                name=name,
                description=description,
                func=func,
                input_schema=ToolInputSchema(params=input_params),
                risk_level=risk,
                category=category,
                source=source,
                status=ToolStatus.ENABLED,
                tags=entry.get("tags", []),
                version=entry.get("version", "1.0.0"),
                author=entry.get("author", "user"),
                loaded_at=datetime.now().isoformat(),
                file_path=file_path,
                endpoint_url=entry.get("endpoint_url"),
                cli_command_template=entry.get("cli_command_template"),
                mcp_server_name=entry.get("mcp_server_name"),
            )
        except Exception as e:
            logger.error(f"Failed to parse manifest entry: {e}")
            return None


# ─── Global Singleton ────────────────────────────────────────────────
_dynamic_loader: Optional[DynamicToolLoader] = None


def get_dynamic_loader() -> DynamicToolLoader:
    global _dynamic_loader
    if _dynamic_loader is None:
        _dynamic_loader = DynamicToolLoader()
    return _dynamic_loader
