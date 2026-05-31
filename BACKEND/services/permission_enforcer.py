"""
AERIS — Permission Enforcer & Sandbox
Prevents dangerous or incorrect actions from voice/AI execution.
Inspired by agent runtime systems (claw-code permission_enforcer.rs).
"""
from __future__ import annotations

import os
import re
import sys
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class PermissionMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "danger-full-access"


@dataclass(frozen=True)
class PermissionResult:
    allowed: bool
    reason: str
    requires_approval: bool = False


DANGEROUS_COMMANDS = frozenset([
    # Filesystem destructive commands
    "rm -rf", "rmdir /s", "del /f", "format", "mkfs", "dd if=", "> /dev/sda", "chmod -R 777 /",
    # System control commands
    "shutdown", "reboot", "poweroff", "init 0", "init 6",
    # Registry & Services manipulation
    "reg delete", "reg add", "sc config", "sc delete", "sc create",
    # Event logs and shadow copies (ransomware indicators)
    "vssadmin delete shadows", "wevtutil cl", "wbadmin delete catalog",
    # Firewalls & Security configuration
    "netsh advfirewall", "set-mppreference",
    # Download cradles & execution mechanisms
    "curl | sh", "wget | sh", "curl | bash", "wget | bash",
    "certutil -urlcache", "certutil.exe -urlcache",
    "bitsadmin /transfer", "bitsadmin.exe /transfer",
    "invoke-webrequest", "iwr", "invoke-expression", "iex",
    "downloadstring", "downloadfile", "net.webclient",
    # Miscellaneous dangerous shell practices
    "pip install --user", "taskkill /f",
])

WRITE_COMMANDS = frozenset([
    "rm", "mv", "cp", "mkdir", "rmdir", "touch",
    "echo", "cat >", "tee", "sed -i", "awk",
    "git push", "git commit", "git reset --hard",
    "npm publish", "pip install",
])


# Define a global set of approved commands so different instances can share approvals
GLOBAL_APPROVED_COMMANDS = set()

@dataclass
class PermissionEnforcer:
    mode: PermissionMode = PermissionMode.WORKSPACE_WRITE
    workspace_root: Path = field(default_factory=lambda: Path.cwd())
    approved_commands: set[str] = field(default_factory=set)

    # ── File write boundary ──────────────────────────────────────────
    def check_file_write(self, target_path: str) -> PermissionResult:
        resolved = Path(target_path).resolve()
        workspace = self.workspace_root.resolve()

        if self.mode == PermissionMode.READ_ONLY:
            return PermissionResult(False, "Read-only mode: all writes are blocked")

        # Symlink escape detection
        try:
            resolved.relative_to(workspace)
        except ValueError:
            return PermissionResult(
                False,
                f"Path escapes workspace boundary: {resolved} is outside {workspace}",
            )

        return PermissionResult(True, "Write allowed within workspace")

    # ── Bash command validation ──────────────────────────────────────
    def check_bash(self, command: str) -> PermissionResult:
        lowered = command.lower().strip()

        # Pre-approve shutdown, restart, and lock screen commands for Aeris
        cmd_clean = command.strip().lower().strip("\"'")
        is_pre_approved = (
            cmd_clean.startswith("shutdown") or 
            cmd_clean in ("reboot", "poweroff", "halt", "init 0", "init 6") or 
            "lockworkstation" in cmd_clean or 
            cmd_clean == "tsdiscon"
        )
        if is_pre_approved:
            return PermissionResult(True, "Command pre-approved (shutdown/restart/lock)")

        # Check for directory traversal attempts (escaping via '..')
        import shlex
        try:
            tokens = shlex.split(command, posix=False)
        except Exception:
            tokens = command.split()

        for token in tokens:
            t_clean = token.strip("\"'")
            if t_clean == ".." or t_clean.startswith("../") or t_clean.startswith("..\\") or "/../" in t_clean or "\\..\\" in t_clean:
                return PermissionResult(
                    False,
                    f"BLOCKED: Directory traversal escape detected in token '{token}'."
                )

        # Check for absolute path escapes
        for token in tokens:
            t_clean = token.strip("\"'")
            
            is_abs = False
            if len(t_clean) >= 3 and t_clean[1] == ":" and t_clean[2] in ("\\", "/"):
                is_abs = True
            elif t_clean.startswith("/") and not t_clean.startswith("//"):
                # On Windows, distinguish command switches from paths by checking for directory segments (>= 2 slashes)
                if os.name != "nt" or (t_clean.count("/") + t_clean.count("\\") >= 2):
                    if not t_clean.startswith("/http") and not t_clean.startswith("/ftp"):
                        is_abs = True
                    
            if is_abs:
                try:
                    resolved = Path(t_clean).resolve()
                    workspace = self.workspace_root.resolve()
                    
                    whitelisted = [
                        Path("C:/Windows").resolve(),
                        Path("C:/Program Files").resolve(),
                        Path("C:/Program Files (x86)").resolve(),
                        Path(sys.executable).parent.resolve(),
                        Path(os.path.expandvars("%APPDATA%")).resolve(),
                        Path(os.path.expandvars("%LOCALAPPDATA%")).resolve(),
                        Path(os.path.expandvars("%TEMP%")).resolve(),
                        Path(os.path.expandvars("%TMP%")).resolve(),
                    ]
                    
                    is_inside = False
                    try:
                        resolved.relative_to(workspace)
                        is_inside = True
                    except ValueError:
                        pass
                        
                    if not is_inside:
                        for wl_path in whitelisted:
                            try:
                                resolved.relative_to(wl_path)
                                is_inside = True
                                break
                            except ValueError:
                                pass
                                
                    if not is_inside:
                        return PermissionResult(
                            False,
                            f"BLOCKED: Path '{token}' escapes workspace boundary '{workspace}'"
                        )
                except Exception:
                    pass

        # Always block destructive commands
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in lowered:
                return PermissionResult(
                    False,
                    f"BLOCKED: destructive command detected — '{dangerous}'",
                )

        if self.mode == PermissionMode.READ_ONLY:
            for write_cmd in WRITE_COMMANDS:
                if lowered.startswith(write_cmd) or f" {write_cmd} " in f" {lowered} ":
                    return PermissionResult(
                        False,
                        f"Read-only mode: write command '{write_cmd}' is blocked",
                    )
            return PermissionResult(True, "Read-only safe command")

        if self.mode == PermissionMode.WORKSPACE_WRITE:
            # Removed interactive approval requirement for WRITE_COMMANDS in WORKSPACE_WRITE mode
            # because ToolPermissionSystem already handles risk-level auto-approvals for autonomous mode.
            return PermissionResult(True, "Command allowed in workspace-write mode")

        # FULL_ACCESS
        return PermissionResult(True, "Full access mode — command allowed")

    # ── Tool-level gating ────────────────────────────────────────────
    def check_tool(self, tool_name: str) -> PermissionResult:
        if self.mode == PermissionMode.READ_ONLY:
            read_safe = {"read_file", "glob_search", "grep_search", "web_search", "web_fetch"}
            if tool_name.lower() not in read_safe:
                return PermissionResult(False, f"Read-only mode: tool '{tool_name}' is blocked")
        return PermissionResult(True, f"Tool '{tool_name}' allowed")

    def approve_command(self, command: str) -> None:
        self.approved_commands.add(command)
        GLOBAL_APPROVED_COMMANDS.add(command)


# ── Sandbox executor ─────────────────────────────────────────────────
@dataclass
class SandboxExecutor:
    enforcer: PermissionEnforcer = field(default_factory=PermissionEnforcer)
    timeout_seconds: int = 30
    max_output_bytes: int = 1_000_000  # 1MB cap

    def execute_bash(self, command: str, cwd: Optional[str] = None) -> dict:
        check = self.enforcer.check_bash(command)
        if not check.allowed:
            return {
                "success": False,
                "blocked": True,
                "requires_approval": check.requires_approval,
                "reason": check.reason,
                "stdout": "",
                "stderr": "",
                "exit_code": -1,
            }

        work_dir = cwd or str(self.enforcer.workspace_root)
        
        # Redact sensitive environment variables to prevent leakage (similar to Claude's sandbox)
        safe_env = os.environ.copy()
        sensitive_patterns = ["key", "secret", "password", "token", "auth", "credential", "url", "db_"]
        for key in list(safe_env.keys()):
            k_lower = key.lower()
            if any(pattern in k_lower for pattern in sensitive_patterns):
                safe_env[key] = "[REDACTED_FOR_SECURITY]"

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                cwd=work_dir,
                env=safe_env,
            )
            stdout = result.stdout[: self.max_output_bytes]
            stderr = result.stderr[: self.max_output_bytes]
            return {
                "success": result.returncode == 0,
                "blocked": False,
                "requires_approval": False,
                "reason": "",
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "blocked": False,
                "requires_approval": False,
                "reason": f"Command timed out after {self.timeout_seconds}s",
                "stdout": "",
                "stderr": "TimeoutExpired",
                "exit_code": -1,
            }
        except Exception as exc:
            return {
                "success": False,
                "blocked": False,
                "requires_approval": False,
                "reason": str(exc),
                "stdout": "",
                "stderr": str(exc),
                "exit_code": -1,
            }
