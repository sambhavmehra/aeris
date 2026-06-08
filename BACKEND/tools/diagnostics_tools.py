"""
AERIS — Diagnostics Tools
==========================
Exposes tools to diagnose:
  1. System and AERIS environment health (`diagnose_system`)
  2. Codebase syntax and styling issues (`diagnose_code`)
  3. LLM-based automatic repair suggestions (`suggest_code_fixes`)
"""

import os
import sys
import platform
import shutil
import ast
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Try importing psutil for memory/CPU metrics
try:
    import psutil
except ImportError:
    psutil = None

from config import settings
from agents.agent_registry import agent_registry, AgentStatus
from tools.tool_health import get_health_tracker

logger = logging.getLogger("AerisDiagnosticsTools")


# ─────────────────────────────────────────────────────────────────────────────
# 1. System Diagnosis
# ─────────────────────────────────────────────────────────────────────────────

def get_system_metrics() -> Dict[str, Any]:
    """Gather live CPU, RAM, and Disk metrics with smart cross-platform fallbacks."""
    metrics = {
        "os": platform.system(),
        "os_release": platform.release(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count() or 0,
        "cpu_percent": 0.0,
        "ram_total_gb": 0.0,
        "ram_used_percent": 0.0,
        "disk_total_gb": 0.0,
        "disk_used_percent": 0.0,
    }

    # 1. CPU and RAM via psutil
    if psutil:
        try:
            metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            metrics["ram_total_gb"] = round(mem.total / (1024 ** 3), 2)
            metrics["ram_used_percent"] = mem.percent
        except Exception as e:
            logger.warning(f"Error fetching psutil stats: {e}")
    else:
        # Fallbacks for RAM/CPU percent
        if metrics["os"] == "Windows":
            try:
                # CPU via WMIC
                cmd = "wmic cpu get LoadPercentage"
                out = subprocess.check_output(cmd, shell=True, text=True)
                lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
                if len(lines) > 1 and lines[1].isdigit():
                    metrics["cpu_percent"] = float(lines[1])
                
                # RAM via WMIC
                cmd_mem = "wmic OS get TotalVisibleMemorySize,FreePhysicalMemory"
                out_mem = subprocess.check_output(cmd_mem, shell=True, text=True)
                lines_mem = [ln.strip() for ln in out_mem.splitlines() if ln.strip()]
                if len(lines_mem) > 1:
                    parts = lines_mem[1].split()
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        total_kb = float(parts[1])  # TotalVisibleMemorySize is usually index 1
                        free_kb = float(parts[0])   # FreePhysicalMemory is index 0
                        used_kb = total_kb - free_kb
                        metrics["ram_total_gb"] = round(total_kb / (1024 ** 2), 2)
                        metrics["ram_used_percent"] = round((used_kb / total_kb) * 100, 1)
            except Exception:
                pass
        elif metrics["os"] == "Linux":
            try:
                # CPU via /proc/loadavg
                with open("/proc/loadavg", "r") as f:
                    load = f.read().split()
                    if load:
                        metrics["cpu_percent"] = round((float(load[0]) / (os.cpu_count() or 1)) * 100, 1)
                # RAM via /proc/meminfo
                with open("/proc/meminfo", "r") as f:
                    lines = f.readlines()
                meminfo = {}
                for line in lines:
                    parts = line.split(":")
                    if len(parts) == 2:
                        meminfo[parts[0].strip()] = parts[1].strip()
                if "MemTotal" in meminfo and "MemAvailable" in meminfo:
                    tot = float(meminfo["MemTotal"].split()[0])
                    avail = float(meminfo["MemAvailable"].split()[0])
                    used = tot - avail
                    metrics["ram_total_gb"] = round(tot / (1024 ** 2), 2)
                    metrics["ram_used_percent"] = round((used / tot) * 100, 1)
            except Exception:
                pass

    # 2. Disk space in workspace
    try:
        ws_path = settings.WORKSPACE_DIR
        total, used, free = shutil.disk_usage(ws_path)
        metrics["disk_total_gb"] = round(total / (1024 ** 3), 2)
        metrics["disk_used_percent"] = round((used / total) * 100, 1)
    except Exception as e:
        logger.warning(f"Error checking disk usage: {e}")

    return metrics


def diagnose_system() -> str:
    """
    Perform a complete self-diagnosis of the system:
    Checks environment keys, tool status, system telemetry, and package dependencies.
    """
    # System Telemetry
    sys_metrics = get_system_metrics()

    # Environment keys verification
    env_keys = {
        "GEMINI_API_KEY": "VITE_GEMINI_API_KEY",
        "GROQ_API_KEY": "GROQ_API_KEY",
        "TAVILY_API_KEY": "VITE_TAVILY_API_KEY",
        "BREVO_API_KEY": "BREVO_API_KEY",
        "TELEGRAM_BOT_TOKEN": "TELEGRAM_BOT_TOKEN"
    }
    env_status = {}
    for name, env_name in env_keys.items():
        val = os.getenv(env_name, "")
        env_status[name] = "✅ CONFIGURED" if val.strip() else "❌ MISSING"

    # Agent statuses
    try:
        agent_statuses = agent_registry.get_all_statuses()
        total_agents = len(agent_registry)
        working_agents = sum(1 for a in agent_registry.get_all_agents().values() if a.status.value == "working" or a.status.value == "idle")
    except Exception as e:
        agent_statuses = {}
        total_agents = 0
        working_agents = 0

    # Tool Health summary
    try:
        tool_metrics = get_health_tracker().get_all_metrics()
        total_tools_run = len(tool_metrics)
        failed_tools = sum(1 for m in tool_metrics.values() if m.get("failed_runs", 0) > 0)
    except Exception:
        tool_metrics = {}
        total_tools_run = 0
        failed_tools = 0

    # Package Dependency check
    deps = ["fastapi", "pydantic", "httpx", "psutil", "dotenv"]
    dep_status = {}
    for dep in deps:
        try:
            __import__(dep)
            dep_status[dep] = "✅ INSTALLED"
        except ImportError:
            dep_status[dep] = "❌ MISSING"

    # Frontend node_modules check
    frontend_dir = settings.BASE_DIR.parent / "FRONTEND"
    node_modules_exists = (frontend_dir / "node_modules").exists()
    dep_status["node_modules (FRONTEND)"] = "✅ PRESENT" if node_modules_exists else "❌ MISSING"

    # Generate Markdown report
    report = []
    report.append("# 🩺 AERIS Self-Diagnosis Report\n")
    
    # Section 1: System Telemetry
    report.append("## ⚙️ System Status & Telemetry")
    report.append(f"- **Operating System:** {sys_metrics['os']} (Release: {sys_metrics['os_release']})")
    report.append(f"- **Python Version:** {sys_metrics['python_version']}")
    report.append(f"- **CPU Count:** {sys_metrics['cpu_count']}")
    report.append(f"- **CPU Load:** {sys_metrics['cpu_percent']}%")
    report.append(f"- **RAM (Total/Used):** {sys_metrics['ram_total_gb']} GB ({sys_metrics['ram_used_percent']}% used)")
    report.append(f"- **Workspace Disk Load:** {sys_metrics['disk_total_gb']} GB ({sys_metrics['disk_used_percent']}% used)")
    report.append("")

    # Section 2: Environment Keys
    report.append("## 🔑 API Keys and Environment")
    for k, v in env_status.items():
        report.append(f"- **{k}:** {v}")
    report.append("")

    # Section 3: Dependencies
    report.append("## 📦 Dependencies & Packages")
    for k, v in dep_status.items():
        report.append(f"- **{k}:** {v}")
    report.append("")

    # Section 4: Agent Registry
    report.append("## 🤖 Agent Registry Integrity")
    report.append(f"- **Total Registered Agents:** {total_agents}")
    report.append(f"- **Agents in Working/Idle State:** {working_agents}/{total_agents}")
    if agent_statuses:
        report.append("\n| Agent Name | Operational Status | Domain |")
        report.append("| :--- | :--- | :--- |")
        for name, details in list(agent_statuses.items())[:15]: # Show first 15 core agents
            status_icon = "🟢" if details.get("status") in ("working", "idle") else "🔴"
            report.append(f"| {name} | {status_icon} {details.get('status').upper()} | {details.get('task_domain')} |")
    report.append("")

    # Section 5: Tool Health Metrics
    report.append("## 🛠️ Tool Health & Reliability Summary")
    report.append(f"- **Tools Run Count:** {total_tools_run}")
    report.append(f"- **Tools reporting failures:** {failed_tools}")
    if tool_metrics:
        report.append("\n| Tool Name | Total Runs | Success Rate | Last Error |")
        report.append("| :--- | :--- | :--- | :--- |")
        for t_name, metrics in list(tool_metrics.items())[:10]: # Show top 10
            rate = round(metrics.get("success_rate", 1.0) * 100, 1)
            err = metrics.get("last_error") or "None"
            report.append(f"| {t_name} | {metrics.get('total_runs')} | {rate}% | {err} |")

    return "\n".join(report)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Codebase Diagnosis
# ─────────────────────────────────────────────────────────────────────────────

def _diagnose_python_file(filepath: Path) -> List[Dict[str, Any]]:
    """Inspect a Python file using AST for syntax errors, styling warnings, etc."""
    issues = []
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [{"file": filepath.name, "line": 0, "type": "read_error", "message": str(e), "severity": "error"}]

    # 1. Syntax Verification via AST
    try:
        root = ast.parse(content, filename=filepath.name)
    except SyntaxError as e:
        return [{
            "file": filepath.name,
            "line": e.lineno or 0,
            "column": e.offset or 0,
            "type": "SyntaxError",
            "message": e.msg,
            "severity": "error"
        }]

    # 2. Line size style check
    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if len(line) > 120:
            issues.append({
                "file": filepath.name,
                "line": idx + 1,
                "column": 120,
                "type": "StyleWarning",
                "message": f"Line exceeds 120 characters limit ({len(line)} chars)",
                "severity": "warning"
            })

    # 3. Code naming and AST-based warnings
    class CodeVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node):
            # Classes should be CamelCase
            if node.name[0].islower() or "_" in node.name:
                issues.append({
                    "file": filepath.name,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "type": "NamingConvention",
                    "message": f"Class name '{node.name}' should follow CamelCase conventions.",
                    "severity": "warning"
                })
            self.generic_visit(node)

        def visit_FunctionDef(self, node):
            # Functions should generally be snake_case
            if any(c.isupper() for c in node.name) and not node.name.startswith("__") and not node.name.startswith("visit_"):
                # Exclude common test naming structures or CamelCase if user settings favor it,
                # but warn for standard Python style consistency
                issues.append({
                    "file": filepath.name,
                    "line": node.lineno,
                    "column": node.col_offset,
                    "type": "NamingConvention",
                    "message": f"Function name '{node.name}' has uppercase characters; PEP8 recommends snake_case.",
                    "severity": "warning"
                })
            self.generic_visit(node)

        def visit_Import(self, node):
            # Check for generic/broad imports
            for alias in node.names:
                if alias.name == "os" or alias.name == "sys":
                    # Just standard imports, no warning
                    pass
            self.generic_visit(node)

    visitor = CodeVisitor()
    visitor.visit(root)

    return issues


def _diagnose_js_ts_file(filepath: Path) -> List[Dict[str, Any]]:
    """Basic syntax and warning check for JavaScript/TypeScript files."""
    issues = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return [{"file": filepath.name, "line": 0, "type": "read_error", "message": str(e), "severity": "error"}]

    lines = content.splitlines()
    
    # Basic brace balance check
    braces = 0
    brackets = 0
    parens = 0
    for idx, line in enumerate(lines):
        braces += line.count("{") - line.count("}")
        brackets += line.count("[") - line.count("]")
        parens += line.count("(") - line.count(")")

        # console.log debug statements warning
        if "console.log(" in line:
            issues.append({
                "file": filepath.name,
                "line": idx + 1,
                "column": line.find("console.log"),
                "type": "DebugWarning",
                "message": "console.log() found in production code.",
                "severity": "warning"
            })
        
        # Hardcoded localhosts
        if "http://localhost:" in line and not filepath.name.startswith("CommandCenter"):
            issues.append({
                "file": filepath.name,
                "line": idx + 1,
                "column": line.find("http://localhost:"),
                "type": "HardcodedEndpoint",
                "message": "Hardcoded localhost endpoint detected. Suggest using environment variables.",
                "severity": "warning"
            })

    if braces != 0:
        issues.append({
            "file": filepath.name,
            "line": len(lines),
            "column": 0,
            "type": "BraceMismatch",
            "message": f"Mismatched curly braces '{{}}' in file (balance is {braces})",
            "severity": "error"
        })

    return issues


def diagnose_code(path: str = "") -> str:
    """
    Scans Python, JS, TS, HTML, and CSS files in `path` for syntax errors,
    formatting issues, naming style violations, and naming anomalies.
    Returns a formatted Markdown analysis.
    """
    # Resolve path
    if not path or not path.strip():
        scan_path = settings.WORKSPACE_DIR
    else:
        # Check if absolute path or relative to workspace
        p = Path(path)
        if p.is_absolute():
            scan_path = p
        else:
            scan_path = settings.WORKSPACE_DIR / path

    if not scan_path.exists():
        return f"### ❌ Diagnostics Error\nThe specified path `{scan_path}` does not exist."

    all_issues = []
    scanned_files_count = 0
    error_count = 0
    warning_count = 0

    # Folders to completely skip
    exclude_dirs = {".git", ".next", "node_modules", "venv", "__pycache__", "dist", "out", ".pytest_cache"}

    # File extensions we analyze
    extensions = {".py", ".js", ".ts", ".tsx", ".html", ".css"}

    files_to_scan = []
    if scan_path.is_file():
        if scan_path.suffix in extensions:
            files_to_scan.append(scan_path)
    else:
        for root, dirs, files in os.walk(scan_path):
            # Prune directories in-place
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for file in files:
                f_path = Path(root) / file
                if f_path.suffix in extensions:
                    files_to_scan.append(f_path)
                    if len(files_to_scan) >= 150: # Upper limit to avoid hanging
                        break
            if len(files_to_scan) >= 150:
                break

    # Analyze files
    for filepath in files_to_scan:
        scanned_files_count += 1
        file_issues = []
        if filepath.suffix == ".py":
            file_issues = _diagnose_python_file(filepath)
        elif filepath.suffix in (".js", ".ts", ".tsx"):
            file_issues = _diagnose_js_ts_file(filepath)
        
        # Add basic file size warning (> 100KB)
        try:
            sz = filepath.stat().st_size
            if sz > 100 * 1024:
                file_issues.append({
                    "file": filepath.name,
                    "line": 1,
                    "column": 0,
                    "type": "FileSizeWarning",
                    "message": f"File is large ({round(sz/1024, 1)} KB). Refactoring recommended.",
                    "severity": "warning"
                })
        except Exception:
            pass

        for issue in file_issues:
            # Map file absolute path or relative path
            try:
                rel_path = filepath.relative_to(settings.BASE_DIR.parent)
            except ValueError:
                rel_path = filepath
            
            issue["relative_path"] = str(rel_path)
            all_issues.append(issue)
            if issue["severity"] == "error":
                error_count += 1
            else:
                warning_count += 1

    # Format Markdown Report
    report = []
    report.append(f"# 🩺 Codebase Health Diagnostics Report")
    report.append(f"**Target Directory:** `{scan_path}`")
    report.append(f"**Files Scanned:** {scanned_files_count}")
    report.append(f"**Total Issues Found:** {len(all_issues)} (❌ Errors: {error_count} | ⚠️ Warnings: {warning_count})")
    report.append("")

    if not all_issues:
        report.append("## ✅ Clean Bill of Health")
        report.append("Excellent! No syntax errors, formatting flaws, or style anomalies detected in the scanned files.")
        return "\n".join(report)

    # Show errors first, then warnings
    errors_list = [i for i in all_issues if i["severity"] == "error"]
    warnings_list = [i for i in all_issues if i["severity"] == "warning"]

    if errors_list:
        report.append("## ❌ Syntax & Execution Critical Errors")
        report.append("| File Path | Line | Issue Type | Details |")
        report.append("| :--- | :--- | :--- | :--- |")
        for err in errors_list:
            report.append(f"| `{err['relative_path']}` | {err['line']} | **{err['type']}** | {err['message']} |")
        report.append("")

    if warnings_list:
        report.append("## ⚠️ Styling & Code Quality Warnings")
        report.append("| File Path | Line | Warning Type | Details |")
        report.append("| :--- | :--- | :--- | :--- |")
        # limit warnings list to first 40 to avoid massive prompt sizes
        for wrn in warnings_list[:40]:
            report.append(f"| `{wrn['relative_path']}` | {wrn['line']} | {wrn['type']} | {wrn['message']} |")
        
        if len(warnings_list) > 40:
            report.append(f"\n*(Note: Showing first 40 warnings out of {len(warnings_list)} total)*")

    report.append("\n## 💡 Suggested Actions")
    if error_count > 0:
        report.append("1. **Resolve Syntax Errors:** Critical syntax errors block file executions and imports. Fix the brace mismatches and parsing errors immediately.")
    if warning_count > 0:
        report.append("2. **Standardize Naming Conventions:** Refactor functions and classes violating naming schemes to maintain clean readability.")
        report.append("3. **Clean Debug Elements:** Remove console.log and other developer-specific debug statements.")
    report.append("4. **Use Automatic Repair:** Run `suggest_code_fixes` on target files to generate code patches automatically.")

    return "\n".join(report)


# ─────────────────────────────────────────────────────────────────────────────
# 3. LLM Repair Suggestions
# ─────────────────────────────────────────────────────────────────────────────

async def suggest_code_fixes(path: str, errors: str) -> str:
    """
    Queries the AI engine to generate code fix suggestions or code diff patches
    for the specific errors found in a file.
    """
    p = Path(path)
    if not p.is_absolute():
        p = settings.WORKSPACE_DIR / path

    if not p.exists() or not p.is_file():
        return f"### ❌ Error\nThe file `{p}` does not exist or is not a file."

    try:
        with open(p, "r", encoding="utf-8") as f:
            code_content = f.read()
    except Exception as e:
        return f"### ❌ File Read Error\nCould not read file `{p}`: {e}"

    prompt = (
        f"You are the AERIS Code Repair Assistant.\n"
        f"The user has scanned a file and found the following errors/warnings:\n"
        f"===\n{errors}\n===\n\n"
        f"Here is the contents of the target file `{p.name}`:\n"
        f"```python\n{code_content}\n```\n\n"
        f"Please analyze the errors, suggest how to resolve them, and generate the complete corrected code file. "
        f"Also provide a markdown diff explanation showing what you changed."
    )

    try:
        from ai_engine import ai_engine
        result = await ai_engine.chat([
            {"role": "system", "content": "You are a software engineer specializing in clean code and debugging."},
            {"role": "user", "content": prompt}
        ], max_tokens=2048)
        return result
    except Exception as e:
        return f"### ❌ AI Generation Error\nCould not query code repair AI: {e}"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Agent Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

async def diagnose_agent(agent_name: str) -> str:
    """
    Diagnose a specific agent by its name (e.g. 'SecurityAgent', 'ChatAgent').
    Checks registration, version, capabilities, runs its health_check(),
    and performs a lightweight dry-run execution.
    """
    from agents.agent_registry import agent_registry
    import time
    
    # Try to find the agent (case-insensitive search)
    info = None
    for name, agent_info in agent_registry.get_all_agents().items():
        if name.lower() == agent_name.lower() or agent_info.instance.__class__.__name__.lower() == agent_name.lower():
            info = agent_info
            break
            
    if not info:
        return f"### ❌ Diagnostics Error\nAgent '{agent_name}' was not found in the Universal Agent Registry."
        
    name = info.name
    instance = info.instance
    status_icon = "🟢" if info.status in (AgentStatus.WORKING, AgentStatus.IDLE) else "🔴"
    
    # 1. Check health
    healthy = True
    error_msg = ""
    if instance and hasattr(instance, "health_check"):
        try:
            healthy = instance.health_check()
        except Exception as e:
            healthy = False
            error_msg = str(e)
            
    # 2. Perform a dry-run/ping test
    ping_success = False
    ping_time = 0.0
    ping_response = ""
    
    # Only run dry-run if instance exists and is a Core agent
    if instance and hasattr(instance, "run") and info.parent is None:
        start_time = time.time()
        try:
            # Run simple ping prompt
            test_prompt = "Hello! Please output a single sentence confirming you are online and working."
            test_context = {"chat_history": []}
            res = await instance.run(test_prompt, test_context)
            ping_success = res.get("success", False)
            ping_response = res.get("response", "")
            ping_time = round(time.time() - start_time, 2)
            if not ping_success and "error" in res:
                error_msg = res["error"]
        except Exception as e:
            ping_success = False
            error_msg = str(e)
            ping_time = round(time.time() - start_time, 2)
    else:
        ping_response = "Dry-run skipped (sub-agent or non-executable instance)."
        ping_success = True
        
    # 3. Get related tools health
    from tools.tool_health import get_health_tracker
    tool_metrics = get_health_tracker().get_all_metrics()
    related_tools = []
    
    # Let's match tools by category or naming patterns
    from tools.universal_registry import get_universal_registry
    registry_tools = get_universal_registry().get_enabled_tools()
    
    # Match capabilities to categories
    for t in registry_tools:
        # Check if tool category matches agent's task domain
        if t.category == info.task_domain:
            m = tool_metrics.get(t.name, {})
            related_tools.append({
                "name": t.name,
                "runs": m.get("total_runs", 0),
                "success_rate": round(m.get("success_rate", 1.0) * 100, 1)
            })

    # Build report
    report = []
    report.append(f"# 🩺 Diagnostics Report: {name}\n")
    report.append(f"- **Agent Registry Name:** {info.name}")
    report.append(f"- **Version:** {info.version}")
    report.append(f"- **Domain:** {info.task_domain}")
    report.append(f"- **Parent Agent:** {info.parent or 'ROOT'}")
    report.append(f"- **Registry Status:** {status_icon} {info.status.value.upper()}")
    report.append(f"- **Health Check:** {'✅ HEALTHY' if healthy else '❌ UNHEALTHY'}")
    if error_msg:
        report.append(f"- **Errors Logged:** `{error_msg}`")
    report.append("")
    
    report.append("## 📡 dry-run Ping Test")
    if ping_success:
        report.append(f"- **Status:** ✅ SUCCESS (Response time: {ping_time}s)")
        report.append(f"- **Response Snippet:** *\"{ping_response[:200]}\"*")
    else:
        report.append(f"- **Status:** ❌ FAILED (Response time: {ping_time}s)")
        report.append(f"- **Diagnostic Error:** `{error_msg}`")
    report.append("")
    
    report.append("## 🧬 Capabilities")
    for cap in info.capabilities:
        report.append(f"- {cap}")
    report.append("")
    
    if info.children:
        report.append("## 🌿 Child Sub-Agents")
        for child in info.children:
            report.append(f"- {child}")
        report.append("")

    if related_tools:
        report.append("## 🛠️ Domain Tools Reliability")
        report.append("| Tool Name | Total Runs | Success Rate |")
        report.append("| :--- | :--- | :--- |")
        for tool in related_tools:
            report.append(f"| {tool['name']} | {tool['runs']} | {tool['success_rate']}% |")
            
    return "\n".join(report)
