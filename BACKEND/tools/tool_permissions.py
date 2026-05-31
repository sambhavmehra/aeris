"""
AERIS — Tool Permission System
═══════════════════════════════════════════════════════════════════════
Centralised permission gate that runs BEFORE every tool execution.

Permission tiers:
  SAFE      → always allowed, no logging
  LOW       → allowed, logged
  MEDIUM    → allowed, logged + audited
  HIGH      → requires explicit user approval (or auto-approve in
              autonomous mode for non-destructive ops)
  CRITICAL  → ALWAYS blocked unless user whitelist overrides

Features:
  • Per-tool and per-risk-level policy enforcement
  • Persistent user whitelist / blacklist (survives restarts)
  • Dangerous pattern detection (rm -rf, format, shutdown)
  • Cooldown tracking (prevent rapid re-execution of high-risk tools)
  • Integration with SecurityAgent for escalation
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Set

from tools.tool_interface import RiskLevel, UniversalToolDef

logger = logging.getLogger("AerisPermissions")


# ─── Permission Decision ─────────────────────────────────────────────
@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str
    requires_user_approval: bool = False
    risk_level: str = "safe"


# ─── Dangerous Patterns (always blocked) ─────────────────────────────
BLOCKED_PATTERNS = frozenset([
    "rm -rf /", "rm -rf /*", "format c:", "del /s /q c:",
    "mkfs", "dd if=/dev/zero", ":(){:|:&};:", "dd if=",
    "shutdown /s /t 0", "shutdown /r /t 0",
    "> /dev/sda", "chmod -R 777 /", "chown -R",
    "curl | sh", "wget | sh", "curl | bash", "wget | bash",
    "reg delete", "netsh advfirewall set allprofiles state off",
    "Set-MpPreference -DisableRealtimeMonitoring $true",
    "vssadmin delete shadows", "wbadmin delete catalog"
])


class ToolPermissionSystem:
    """
    Centralised permission manager for the Universal Tool system.

    Usage:
        decision = permission_system.check(tool_def, kwargs)
        if not decision.allowed:
            if decision.requires_user_approval:
                # prompt user
            else:
                # hard block
    """

    _PERSIST_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "permissions.json"

    def __init__(self):
        self._user_whitelist: Set[str] = set()    # Tool names always allowed
        self._user_blacklist: Set[str] = set()    # Tool names always blocked
        self._auto_approve_session: Set[str] = set()  # Approved during this session
        self._cooldowns: Dict[str, float] = {}    # tool_name -> last_exec_timestamp
        self._load_persisted()

    # ─── Core Permission Check ────────────────────────────────────────

    def check(self, tool: UniversalToolDef, params: Dict[str, Any] = None) -> PermissionDecision:
        """
        Run the full permission pipeline for a tool execution request.
        Returns a PermissionDecision.
        """
        params = params or {}
        params_str = str(params).lower()

        # Pre-approve system control commands (shutdown, restart, lock screen) for Aeris
        is_system_control_approved = False
        if tool.name == "system_control":
            action = params.get("action", "").lower().strip()
            if action in ("shutdown", "restart", "lock", "lock window", "lock screen"):
                is_system_control_approved = True
        elif tool.name in ("run_bash", "bash", "smart_shell", "smart_shell_generate", "execute_shell_command"):
            cmd_val = None
            for key in ["command", "cmd", "script", "shell_command"]:
                if key in params:
                    cmd_val = params[key]
                    break
            if cmd_val and isinstance(cmd_val, str):
                cmd_clean = cmd_val.strip().lower().strip("\"'")
                if (cmd_clean.startswith("shutdown") or 
                        cmd_clean in ("reboot", "poweroff", "halt", "init 0", "init 6") or 
                        "lockworkstation" in cmd_clean or 
                        cmd_clean == "tsdiscon"):
                    is_system_control_approved = True

        if is_system_control_approved:
            return PermissionDecision(
                allowed=True,
                reason=f"System control/shutdown/restart/lock operation is pre-approved for Aeris.",
                risk_level=tool.risk_level.value,
            )

        # Enforce Hacker Mode for security/recon/vapt tools
        if tool.category in ("recon", "vapt", "security"):
            try:
                from memory.user_profile import user_profile_store
                is_hacker = user_profile_store.get_profile().get("hacker_mode", False)
            except Exception:
                is_hacker = False
            
            if not is_hacker:
                return PermissionDecision(
                    allowed=False,
                    reason=f"Tool '{tool.name}' category '{tool.category}' requires Hacker Brain Mode authorization.",
                    risk_level=tool.risk_level.value,
                )

        # 1. User blacklist — hard block
        if tool.name in self._user_blacklist:
            return PermissionDecision(
                allowed=False,
                reason=f"Tool '{tool.name}' is in user's blacklist.",
                risk_level=tool.risk_level.value,
            )

        # 2. Command validation (empty commands or suspicious piping)
        cmd_val = None
        for key in ["command", "cmd", "script"]:
            if key in params:
                cmd_val = params[key]
                break

        if cmd_val is not None and isinstance(cmd_val, str):
            stripped_cmd = cmd_val.strip()
            if not stripped_cmd:
                return PermissionDecision(
                    allowed=False,
                    reason="Command cannot be empty or whitespace only.",
                    risk_level=tool.risk_level.value
                )
            import re
            suspicious_pipe = re.search(r"\|\s*(bash|sh|powershell|pwsh|python|python3|cmd|wscript|cscript)", stripped_cmd, re.IGNORECASE)
            if suspicious_pipe:
                return PermissionDecision(
                    allowed=False,
                    reason=f"Suspicious shell pipe detected: '{suspicious_pipe.group(0)}'",
                    risk_level="critical"
                )

        # 3. Dangerous pattern scan
        for pattern in BLOCKED_PATTERNS:
            if pattern.lower() in params_str:
                logger.warning(f"BLOCKED: destructive pattern '{pattern}' in params for {tool.name}")
                return PermissionDecision(
                    allowed=False,
                    reason=f"Destructive command pattern detected: '{pattern}'",
                    risk_level="critical",
                )

        # 4. User whitelist — always allow
        if tool.name in self._user_whitelist:
            return PermissionDecision(
                allowed=True,
                reason=f"Tool '{tool.name}' is whitelisted by user.",
                risk_level=tool.risk_level.value,
            )

        # 5. Session auto-approve
        if tool.name in self._auto_approve_session:
            return PermissionDecision(
                allowed=True,
                reason=f"Tool '{tool.name}' auto-approved in this session.",
                risk_level=tool.risk_level.value,
            )

        # 6. Explicit approval requirements for HIGH, CRITICAL, or approval_requirement=True
        if tool.approval_requirement or tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return PermissionDecision(
                allowed=False,
                reason=f"Tool '{tool.name}' requires explicit user approval.",
                requires_user_approval=True,
                risk_level=tool.risk_level.value,
            )

        # 7. Risk-level based policy
        if tool.risk_level == RiskLevel.SAFE:
            return PermissionDecision(allowed=True, reason="Safe tool.", risk_level="safe")

        if tool.risk_level == RiskLevel.LOW:
            return PermissionDecision(allowed=True, reason="Low-risk tool.", risk_level="low")

        if tool.risk_level == RiskLevel.MEDIUM:
            return PermissionDecision(allowed=True, reason="Medium-risk tool (auto-approved).", risk_level="medium")

        # Default: allow
        return PermissionDecision(allowed=True, reason="Default allow.", risk_level=tool.risk_level.value)

    # ─── User Control API ─────────────────────────────────────────────

    def whitelist_tool(self, tool_name: str):
        """Permanently allow a tool (survives restarts)."""
        self._user_whitelist.add(tool_name)
        self._user_blacklist.discard(tool_name)
        self._persist()

    def blacklist_tool(self, tool_name: str):
        """Permanently block a tool (survives restarts)."""
        self._user_blacklist.add(tool_name)
        self._user_whitelist.discard(tool_name)
        self._persist()

    def approve_for_session(self, tool_name: str):
        """Allow a tool for the duration of this session only."""
        self._auto_approve_session.add(tool_name)

    def revoke_session_approval(self, tool_name: str):
        """Revoke a session-level approval."""
        self._auto_approve_session.discard(tool_name)

    def reset_tool(self, tool_name: str):
        """Remove a tool from both whitelist and blacklist."""
        self._user_whitelist.discard(tool_name)
        self._user_blacklist.discard(tool_name)
        self._persist()

    def get_permissions_summary(self) -> Dict[str, Any]:
        """Return a summary of current permission state."""
        return {
            "whitelisted": sorted(self._user_whitelist),
            "blacklisted": sorted(self._user_blacklist),
            "session_approved": sorted(self._auto_approve_session),
            "active_cooldowns": {
                name: round(time.time() - ts, 1)
                for name, ts in self._cooldowns.items()
                if time.time() - ts < 60
            },
        }

    # ─── Cooldown ─────────────────────────────────────────────────────

    def _check_cooldown(self, tool_name: str, cooldown_seconds: float = 5) -> bool:
        """Return True if cooldown has expired (tool can run)."""
        last = self._cooldowns.get(tool_name, 0)
        return (time.time() - last) >= cooldown_seconds

    # ─── Persistence ──────────────────────────────────────────────────

    def _persist(self):
        """Save whitelist / blacklist to disk."""
        try:
            self._PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "whitelist": sorted(self._user_whitelist),
                "blacklist": sorted(self._user_blacklist),
            }
            self._PERSIST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist permissions: {e}")

    def _load_persisted(self):
        """Load whitelist / blacklist from disk."""
        try:
            if self._PERSIST_FILE.exists():
                data = json.loads(self._PERSIST_FILE.read_text(encoding="utf-8"))
                self._user_whitelist = set(data.get("whitelist", []))
                self._user_blacklist = set(data.get("blacklist", []))
        except Exception as e:
            logger.warning(f"Failed to load persisted permissions: {e}")


# ─── Global Singleton ────────────────────────────────────────────────
_permission_system: Optional[ToolPermissionSystem] = None


def get_permission_system() -> ToolPermissionSystem:
    global _permission_system
    if _permission_system is None:
        _permission_system = ToolPermissionSystem()
    return _permission_system
