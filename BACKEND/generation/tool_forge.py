"""
AERIS -- Dynamic Tool Forge + Sandbox Runner
AERIS can write its own Python tools at runtime, store them, and execute
them inside a secure sandbox. Examples: doc-to-pdf, file search, image
resize, CSV analysis, code formatting, etc.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# =====================================================================
#  BUILT-IN TOOL TEMPLATES -- AERIS can generate these on-demand
# =====================================================================

TOOL_TEMPLATES: dict[str, dict] = {
    "convert_doc_to_pdf": {
        "description": "Convert a DOCX document to PDF",
        "code": textwrap.dedent("""\
            import subprocess, sys, os
            def run(input_path: str, output_path: str = "") -> dict:
                if not output_path:
                    output_path = os.path.splitext(input_path)[0] + ".pdf"
                try:
                    # Try LibreOffice first
                    out_dir = os.path.dirname(os.path.abspath(output_path)) or "."
                    subprocess.run(
                        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", out_dir, input_path],
                        capture_output=True, text=True, timeout=60,
                    )
                    return {"success": True, "output": output_path}
                except FileNotFoundError:
                    return {"success": False, "error": "LibreOffice (soffice) not found. Install it for doc-to-pdf."}
                except Exception as e:
                    return {"success": False, "error": str(e)}
        """),
    },
    "search_files": {
        "description": "Recursively search files by name pattern or content",
        "code": textwrap.dedent("""\
            import os, fnmatch

            def _default_roots(directory: str) -> list[str]:
                # If caller passes ".", try common AERIS data roots first.
                if directory in (".", "", None):
                    return ["." , "BACKEND/data", "data", "BACKEND/data/converted", "BACKEND/Screenshots"]
                return [directory]

            def run(directory: str = ".", pattern: str = "*", content_query: str = "", max_results: int = 50) -> dict:
                results = []
                content_query_l = (content_query or "").lower().strip()

                # Case-insensitive filename matching for cases like "sambhavv.pdf" vs "SambhavV.pdf"
                pattern_l = (pattern or "*").lower()

                def match_name(fname: str) -> bool:
                    return fnmatch.fnmatch(fname.lower(), pattern_l)

                def consider_file(full: str, fname: str) -> None:
                    if not match_name(fname):
                        return
                    if content_query_l:
                        try:
                            # Only attempt text matching; skip binaries / unreadable files
                            with open(full, "r", errors="ignore") as f:
                                text = f.read()
                            if content_query_l not in text.lower():
                                return
                        except Exception:
                            return
                    results.append(full)

                roots = _default_roots(directory)

                for root_dir in roots:
                    try:
                        if not os.path.exists(root_dir):
                            continue
                        for root, dirs, files in os.walk(root_dir, onerror=lambda e: None):
                            # Skip dirs that are likely inaccessible (best-effort)
                            # Also prevent os.walk from repeatedly trying protected folders.
                            pruned = []
                            for d in dirs:
                                dl = d.lower()
                                if dl in ("node_modules", ".git", "__pycache__", "venv", "windows", "system32", "program files", "program files (x86)"):
                                    pruned.append(d)
                            if pruned:
                                dirs[:] = [d for d in dirs if d not in pruned]

                            for fname in files:
                                try:
                                    full = os.path.join(root, fname)
                                    consider_file(full, fname)
                                except Exception:
                                    continue

                                if len(results) >= max_results:
                                    return {"success": True, "count": len(results), "files": results, "truncated": True}
                    except Exception:
                        # If a root traversal fails (permissions, etc), keep going with next root.
                        continue

                return {"success": True, "count": len(results), "files": results, "truncated": False}
        """),
    },
    "csv_analyzer": {
        "description": "Analyze a CSV file: row count, columns, basic stats",
        "code": textwrap.dedent("""\
            import csv, os
            def run(filepath: str) -> dict:
                if not os.path.exists(filepath):
                    return {"success": False, "error": f"File not found: {filepath}"}
                try:
                    with open(filepath, newline="", encoding="utf-8-sig") as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
                    columns = list(rows[0].keys()) if rows else []
                    return {
                        "success": True,
                        "row_count": len(rows),
                        "column_count": len(columns),
                        "columns": columns,
                        "sample_row": rows[0] if rows else {},
                    }
                except Exception as e:
                    return {"success": False, "error": str(e)}
        """),
    },
    "text_to_html": {
        "description": "Convert plain text or markdown to styled HTML",
        "code": textwrap.dedent("""\
            import os, re
            def run(input_path: str, output_path: str = "") -> dict:
                if not os.path.exists(input_path):
                    return {"success": False, "error": f"File not found: {input_path}"}
                if not output_path:
                    output_path = os.path.splitext(input_path)[0] + ".html"
                try:
                    text = open(input_path, encoding="utf-8").read()
                    # Basic markdown-ish conversion
                    lines = text.split("\\n")
                    html_lines = []
                    for line in lines:
                        if line.startswith("# "):
                            html_lines.append(f"<h1>{line[2:]}</h1>")
                        elif line.startswith("## "):
                            html_lines.append(f"<h2>{line[3:]}</h2>")
                        elif line.startswith("- "):
                            html_lines.append(f"<li>{line[2:]}</li>")
                        elif line.strip() == "":
                            html_lines.append("<br/>")
                        else:
                            html_lines.append(f"<p>{line}</p>")
                    body = "\\n".join(html_lines)
                    html = f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><style>
                    body{{font-family:Inter,system-ui,sans-serif;max-width:800px;margin:40px auto;padding:0 20px;background:#06060b;color:#e8e6f0;line-height:1.7;}}
                    h1,h2{{background:linear-gradient(135deg,#8b5cf6,#06b6d4);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}}
                    li{{margin-left:20px;color:#9896a8;}}
                    </style></head><body>{body}</body></html>'''
                    open(output_path, "w", encoding="utf-8").write(html)
                    return {"success": True, "output": output_path, "size": len(html)}
                except Exception as e:
                    return {"success": False, "error": str(e)}
        """),
    },
    "json_formatter": {
        "description": "Pretty-format a JSON file",
        "code": textwrap.dedent("""\
            import json, os
            def run(filepath: str) -> dict:
                if not os.path.exists(filepath):
                    return {"success": False, "error": f"File not found: {filepath}"}
                try:
                    data = json.loads(open(filepath, encoding="utf-8").read())
                    formatted = json.dumps(data, indent=2, ensure_ascii=False)
                    open(filepath, "w", encoding="utf-8").write(formatted)
                    return {"success": True, "keys": len(data) if isinstance(data, dict) else "array", "size": len(formatted)}
                except Exception as e:
                    return {"success": False, "error": str(e)}
        """),
    },
    "line_counter": {
        "description": "Count lines of code in a directory by file extension",
        "code": textwrap.dedent("""\
            import os
            def run(directory: str = ".", extensions: str = ".py,.js,.ts,.html,.css") -> dict:
                exts = set(e.strip() for e in extensions.split(","))
                stats = {}
                total = 0
                for root, dirs, files in os.walk(directory):
                    dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__", "venv")]
                    for fname in files:
                        ext = os.path.splitext(fname)[1]
                        if ext in exts:
                            try:
                                lines = len(open(os.path.join(root, fname), errors="ignore").readlines())
                                stats[ext] = stats.get(ext, 0) + lines
                                total += lines
                            except Exception:
                                pass
                return {"success": True, "total_lines": total, "by_extension": stats}
        """),
    },
    "duplicate_finder": {
        "description": "Find duplicate files by size and partial hash",
        "code": textwrap.dedent("""\
            import os, hashlib
            def run(directory: str = ".", min_size: int = 1024) -> dict:
                by_size = {}
                for root, dirs, files in os.walk(directory):
                    dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "__pycache__")]
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            sz = os.path.getsize(fpath)
                            if sz >= min_size:
                                by_size.setdefault(sz, []).append(fpath)
                        except OSError:
                            pass
                duplicates = []
                for sz, paths in by_size.items():
                    if len(paths) < 2:
                        continue
                    by_hash = {}
                    for p in paths:
                        try:
                            h = hashlib.md5(open(p, "rb").read(8192)).hexdigest()
                            by_hash.setdefault(h, []).append(p)
                        except Exception:
                            pass
                    for h, group in by_hash.items():
                        if len(group) >= 2:
                            duplicates.append({"hash": h, "size": sz, "files": group})
                return {"success": True, "duplicate_groups": len(duplicates), "duplicates": duplicates[:20]}
        """),
    },
}


# =====================================================================
#  DATA MODELS
# =====================================================================

@dataclass
class ForgedTool:
    tool_id: str
    name: str
    description: str
    code: str
    created_at: str
    file_path: str
    last_run: Optional[str] = None
    run_count: int = 0

    def to_dict(self) -> dict:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "file_path": self.file_path,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "run_count": self.run_count,
        }


@dataclass
class SandboxResult:
    success: bool
    output: Any = None
    error: Optional[str] = None
    execution_time_ms: float = 0
    tool_name: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "tool_name": self.tool_name,
        }


# =====================================================================
#  TOOL FORGE -- writes tools to disk
# =====================================================================

class ToolForge:
    """Creates, stores, lists, and manages dynamically generated tools."""

    def __init__(self, workspace: str | None = None) -> None:
        self.workspace = Path(workspace or os.getcwd()).resolve()
        self.tools_dir = self.workspace / "aeris_tools"
        self.tools_dir.mkdir(parents=True, exist_ok=True)
        self._registry: dict[str, ForgedTool] = {}
        self._load_existing()

    def _load_existing(self) -> None:
        """Load tools that were previously forged."""
        manifest = self.tools_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                for entry in data:
                    tool = ForgedTool(**entry)
                    self._registry[tool.name] = tool
            except Exception:
                pass

    def _save_manifest(self) -> None:
        manifest = self.tools_dir / "manifest.json"
        data = [t.to_dict() | {"code": t.code} for t in self._registry.values()]
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def forge_from_template(self, template_name: str) -> ForgedTool:
        """Create a tool from a built-in template."""
        if template_name not in TOOL_TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}. Available: {list(TOOL_TEMPLATES)}")
        tmpl = TOOL_TEMPLATES[template_name]
        return self.forge(template_name, tmpl["description"], tmpl["code"])

    def forge(self, name: str, description: str, code: str) -> ForgedTool:
        """Write a new tool script to disk and register it."""
        tool_id = uuid.uuid4().hex[:10]
        safe_name = name.replace(" ", "_").replace("-", "_").lower()
        file_path = self.tools_dir / f"{safe_name}.py"
        file_path.write_text(code, encoding="utf-8")

        tool = ForgedTool(
            tool_id=tool_id,
            name=safe_name,
            description=description,
            code=code,
            created_at=datetime.now().isoformat(),
            file_path=str(file_path),
        )
        self._registry[safe_name] = tool
        self._save_manifest()
        return tool

    def forge_custom(self, name: str, description: str, logic_prompt: str) -> ForgedTool:
        """
        Generate a completely custom tool from a natural language description.
        AERIS writes the Python code itself based on the prompt.
        """
        safe_name = name.replace(" ", "_").replace("-", "_").lower()

        prompt = f'''Write a complete python tool to accomplish the following task: "{logic_prompt}"
The tool MUST be a valid python module that contains a function `def run(**kwargs) -> dict:`. 
The tool must return a dictionary with at least a boolean 'success' key, and strings 'output' or 'error'.
Only return the pure python code text, with NO MARKDOWN formatting, NO ```python blocks. Your entire response will be saved directly into a .py file. Do not provide any explanation.'''

        try:
            from core.api_gateway.gateway import get_gateway
            from core.api_gateway.providers import TaskType
            
            messages = [
                {"role": "system", "content": "You are an expert Python developer."},
                {"role": "user", "content": prompt}
            ]
            
            gateway = get_gateway()
            
            # Use gateway.call to get raw text back for the code generation
            code = gateway.call(TaskType.CODE, messages=messages, temperature=0.1, max_tokens=2048)
            code = gateway._extract_text(code)
                
            # Strip markdown logic
            if "```python" in code:
                code = code.split("```python")[-1].split("```")[0].strip()
            elif "```" in code:
                code = code.split("```")[-1].split("```")[0].strip()
                
            if not code.strip() or "def run" not in code:
                raise Exception("LLM returned invalid or empty code")
                
        except Exception as e:
            # Fallback
            code = textwrap.dedent(f"""\
                # Auto-generated tool fallback: {safe_name}
                # Error during LLM generation: {e}
                import os

                def run(**kwargs) -> dict:
                    return {{"success": False, "error": "LLM failed to generate tool logic", "tool": "{safe_name}"}}
            """)

        return self.forge(safe_name, description, code)

    def get(self, name: str) -> Optional[ForgedTool]:
        return self._registry.get(name.lower())

    def list_tools(self) -> list[ForgedTool]:
        return list(self._registry.values())

    def list_templates(self) -> list[dict]:
        return [
            {"name": k, "description": v["description"]}
            for k, v in TOOL_TEMPLATES.items()
        ]

    def delete(self, name: str) -> bool:
        tool = self._registry.pop(name.lower(), None)
        if tool:
            try:
                Path(tool.file_path).unlink(missing_ok=True)
            except Exception:
                pass
            self._save_manifest()
            return True
        return False


# =====================================================================
#  SANDBOX RUNNER -- safely executes forged tools
# =====================================================================

class SandboxRunner:
    """
    Executes forged Python tools in a subprocess sandbox with:
     - Timeout enforcement
     - Output size limits
     - Working directory isolation
     - No network access (optional, future)
    """

    def __init__(self, timeout: int = 30, max_output: int = 500_000) -> None:
        self.timeout = timeout
        self.max_output = max_output

    def run_tool(self, tool: ForgedTool, args: dict | None = None) -> SandboxResult:
        """Execute a forged tool in a subprocess sandbox."""
        import time
        start = time.perf_counter()

        args = args or {}
        tool.run_count += 1
        tool.last_run = datetime.now().isoformat()

        # Build a runner script that imports and calls the tool's run()
        args_json = json.dumps(args)
        runner_code = textwrap.dedent(f"""\
            import sys, json, os
            sys.path.insert(0, os.path.dirname(r"{tool.file_path}"))
            
            # Load the tool module
            spec = __import__("importlib").util.spec_from_file_location("tool_mod", r"{tool.file_path}")
            mod = __import__("importlib").util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            
            # Execute
            args = json.loads(r'''{args_json}''')
            result = mod.run(**args)
            print(json.dumps(result, default=str))
        """)

        try:
            result = subprocess.run(
                [sys.executable, "-c", runner_code],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=os.path.dirname(tool.file_path),
            )

            elapsed = (time.perf_counter() - start) * 1000

            if result.returncode == 0:
                stdout = result.stdout.strip()[: self.max_output]
                try:
                    output = json.loads(stdout)
                except json.JSONDecodeError:
                    output = stdout
                return SandboxResult(
                    success=True,
                    output=output,
                    execution_time_ms=round(elapsed, 2),
                    tool_name=tool.name,
                )
            else:
                stderr = result.stderr.strip()[: self.max_output]
                return SandboxResult(
                    success=False,
                    error=stderr or "Tool execution failed",
                    execution_time_ms=round(elapsed, 2),
                    tool_name=tool.name,
                )

        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                error=f"Sandbox timeout ({self.timeout}s exceeded)",
                tool_name=tool.name,
            )
        except Exception as exc:
            return SandboxResult(
                success=False,
                error=traceback.format_exc(),
                tool_name=tool.name,
            )

    def run_raw_code(self, code: str, timeout: int | None = None) -> SandboxResult:
        """Execute arbitrary Python code in a sandbox (for testing)."""
        import time
        start = time.perf_counter()
        t = timeout or self.timeout

        try:
            result = subprocess.run(
                [sys.executable, "-c", code],
                capture_output=True,
                text=True,
                timeout=t,
            )
            elapsed = (time.perf_counter() - start) * 1000
            return SandboxResult(
                success=result.returncode == 0,
                output=result.stdout.strip()[: self.max_output] if result.returncode == 0 else None,
                error=result.stderr.strip()[: self.max_output] if result.returncode != 0 else None,
                execution_time_ms=round(elapsed, 2),
                tool_name="raw_code",
            )
        except subprocess.TimeoutExpired:
            return SandboxResult(success=False, error=f"Timeout ({t}s)", tool_name="raw_code")
        except Exception as exc:
            return SandboxResult(success=False, error=str(exc), tool_name="raw_code")
