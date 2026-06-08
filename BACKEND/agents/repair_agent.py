"""
AERIS Repair Agent — Self-healing agent for diagnosing and repairing code,
tools, agents, workflows, and generated project issues.

Capabilities:
  - analyze_error: Classify and diagnose error types
  - repair_code: Fix syntax, import, and runtime errors in code files
  - repair_frontend: Fix Next.js/TypeScript build errors
  - repair_backend: Fix FastAPI/Python backend issues
  - repair_tool_registry: Fix broken tool registrations
  - repair_agent_registry: Fix broken agent registrations
  - repair_workflow: Fix malformed workflow JSON files
  - verify_fix: Verify that applied fixes actually work
  - generate_repair_report: Produce structured repair reports
  - diagnose_task_failure: Diagnose why an agent task failed
  - email_repair_report: Email diagnosis reports to user
"""

from __future__ import annotations

import ast
import json
import logging
import time
import traceback
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from config import settings

logger = logging.getLogger("aeris.agent.repair")


# ──────────────────────────────────────────────────────────────────────────────
# Data Structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class RepairIssue:
    """A single identified issue."""
    issue_type: str          # syntax_error, import_error, dependency_error, etc.
    file_path: str           # Affected file path
    error_msg: str           # Error message or description
    line_number: Optional[int] = None
    severity: str = "medium"  # low, medium, high, critical

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepairFix:
    """A single proposed fix."""
    file_path: str
    description: str
    original_content: Optional[str] = None
    fixed_content: Optional[str] = None
    command: Optional[str] = None       # Shell command to run (if applicable)
    risk_level: str = "low"             # low, medium, high

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RepairPlan:
    """Complete repair plan before execution."""
    repair_id: str
    issues: List[RepairIssue] = field(default_factory=list)
    proposed_fixes: List[RepairFix] = field(default_factory=list)
    risk_level: str = "low"             # Overall risk: low, medium, high
    dry_run: bool = True
    auto_apply: bool = False
    requires_approval: bool = True
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "repair_id": self.repair_id,
            "issues": [i.to_dict() for i in self.issues],
            "proposed_fixes": [f.to_dict() for f in self.proposed_fixes],
            "risk_level": self.risk_level,
            "dry_run": self.dry_run,
            "auto_apply": self.auto_apply,
            "requires_approval": self.requires_approval,
            "explanation": self.explanation,
        }


@dataclass
class RepairResult:
    """Result after executing a repair."""
    repair_id: str
    success: bool
    issues_found: int = 0
    issues_fixed: int = 0
    files_changed: List[str] = field(default_factory=list)
    commands_run: List[str] = field(default_factory=list)
    verification_status: str = "not_verified"  # not_verified, passed, failed
    remaining_risks: List[str] = field(default_factory=list)
    report: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TaskFailureDiagnosis:
    """Diagnosis of a failed agent task."""
    agent_name: str
    task_description: str
    error: str
    root_cause: str
    suggested_fix: str
    severity: str = "medium"
    is_recurring: bool = False
    occurrence_count: int = 1
    report_html: str = ""
    should_email: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────────
# Repair Memory — Personal memory for the Repair Agent
# ──────────────────────────────────────────────────────────────────────────────

class RepairMemory:
    """Personal memory for the Repair Agent — learns from past failures."""

    def __init__(self):
        self._file_path = settings.DATA_DIR / "repair_memory.json"
        self._data = self._load()

    def _load(self) -> dict:
        """Load memory from disk."""
        try:
            if self._file_path.exists():
                data = json.loads(self._file_path.read_text(encoding="utf-8"))
                logger.info(f"Loaded repair memory: {len(data.get('failure_patterns', []))} patterns, {len(data.get('personal_notes', []))} notes")
                return data
        except Exception as e:
            logger.warning(f"Failed to load repair memory: {e}")
        return {
            "failure_patterns": [],
            "known_fixes": {},
            "user_preferences": {
                "auto_email_on_failure": True,
                "preferred_fix_style": "conservative",
            },
            "personal_notes": [],
            "stats": {
                "total_repairs": 0,
                "successful_repairs": 0,
                "failed_repairs": 0,
                "most_common_error": None,
            },
            "last_updated": None,
        }

    def save(self) -> None:
        """Persist memory to disk."""
        try:
            self._data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(
                json.dumps(self._data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save repair memory: {e}")

    def add_failure_pattern(self, diagnosis: dict) -> None:
        """Store a failure pattern. Increments occurrences if same error seen before."""
        patterns = self._data.get("failure_patterns", [])
        error_msg = diagnosis.get("error", "")
        agent_name = diagnosis.get("agent_name", "")

        # Check for existing pattern
        for pattern in patterns:
            if pattern.get("error_msg", "") == error_msg and pattern.get("agent", "") == agent_name:
                pattern["occurrences"] = pattern.get("occurrences", 1) + 1
                pattern["last_seen"] = datetime.now(timezone.utc).isoformat()
                if diagnosis.get("suggested_fix"):
                    pattern["fix_applied"] = diagnosis["suggested_fix"]
                self.save()
                return

        # New pattern
        patterns.append({
            "agent": agent_name,
            "error_type": diagnosis.get("error_type", "unknown"),
            "error_msg": error_msg,
            "root_cause": diagnosis.get("root_cause", ""),
            "fix_applied": diagnosis.get("suggested_fix", ""),
            "occurrences": 1,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        })
        self._data["failure_patterns"] = patterns
        self.save()

    def is_recurring_pattern(self, error_msg: str) -> Tuple[bool, int]:
        """Check if this error has been seen before. Returns (is_recurring, count)."""
        for pattern in self._data.get("failure_patterns", []):
            if pattern.get("error_msg", "") == error_msg:
                count = pattern.get("occurrences", 1)
                return (count > 1, count)
        return (False, 0)

    def get_known_fix(self, error_type: str) -> Optional[str]:
        """Retrieve a known fix for an error type from memory."""
        return self._data.get("known_fixes", {}).get(error_type)

    def add_known_fix(self, error_type: str, fix: str) -> None:
        """Store a known fix for an error type."""
        if "known_fixes" not in self._data:
            self._data["known_fixes"] = {}
        self._data["known_fixes"][error_type] = fix
        self.save()

    def add_personal_note(self, note: str) -> None:
        """Add a personal note to memory."""
        if not note or not note.strip():
            return
        notes = self._data.get("personal_notes", [])
        note = note.strip()
        if note not in notes:
            notes.append(note)
            self._data["personal_notes"] = notes
            self.save()
            logger.info(f"Repair memory: added personal note")

    def get_notes(self) -> List[str]:
        """Get all personal notes."""
        return self._data.get("personal_notes", [])

    def update_preference(self, key: str, value: Any) -> None:
        """Update a user preference."""
        if "user_preferences" not in self._data:
            self._data["user_preferences"] = {}
        self._data["user_preferences"][key] = value
        self.save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        return self._data.get("user_preferences", {}).get(key, default)

    def increment_stats(self, key: str) -> None:
        """Increment a stats counter."""
        if "stats" not in self._data:
            self._data["stats"] = {}
        self._data["stats"][key] = self._data["stats"].get(key, 0) + 1
        self.save()

    def get_data(self) -> dict:
        """Get the full memory data (for API exposure)."""
        return dict(self._data)

    def get_context_for_prompt(self) -> str:
        """Format memory as context for LLM prompts."""
        parts = []
        patterns = self._data.get("failure_patterns", [])
        if patterns:
            recent = sorted(patterns, key=lambda p: p.get("last_seen", ""), reverse=True)[:5]
            lines = []
            for p in recent:
                lines.append(f"- [{p.get('agent', '?')}] {p.get('error_type', '?')}: {p.get('error_msg', '?')[:100]} (seen {p.get('occurrences', 1)}x)")
            parts.append("Recent failure patterns:\n" + "\n".join(lines))

        notes = self._data.get("personal_notes", [])
        if notes:
            parts.append("Personal notes:\n" + "\n".join(f"- {n}" for n in notes[-5:]))

        fixes = self._data.get("known_fixes", {})
        if fixes:
            lines = [f"- {k}: {v[:80]}" for k, v in list(fixes.items())[:5]]
            parts.append("Known fixes:\n" + "\n".join(lines))

        return "\n\n".join(parts) if parts else "No repair memory yet."


# ──────────────────────────────────────────────────────────────────────────────
# Repair Agent
# ──────────────────────────────────────────────────────────────────────────────

class RepairAgent(BaseAgent):
    """Self-healing agent that diagnoses and repairs code, tools, agents,
    workflows, and builds across the AERIS ecosystem."""

    ISSUE_TYPES = [
        "syntax_error", "import_error", "dependency_error", "runtime_error",
        "config_error", "tool_registry_error", "agent_registry_error",
        "frontend_build_error", "backend_api_error", "workflow_error",
    ]

    def __init__(self):
        super().__init__(
            name="RepairAgent",
            description="Self-healing agent that diagnoses and repairs code, tools, agents, workflows, and builds",
            task_domain="repair",
            version="1.0.0",
            capabilities=[
                "analyze_error",
                "repair_code",
                "repair_frontend",
                "repair_backend",
                "repair_tool_registry",
                "repair_agent_registry",
                "repair_workflow",
                "verify_fix",
                "generate_repair_report",
                "diagnose_task_failure",
                "email_repair_report",
            ],
        )
        self._memory = RepairMemory()
        self._status_file = settings.DATA_DIR / "repair_status.json"
        self._history_file = settings.DATA_DIR / "repair_history.json"

    # ─── Repair Status / History persistence ──────────────────────────────

    def _load_status(self) -> dict:
        try:
            if self._status_file.exists():
                return json.loads(self._status_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_status(self, data: dict) -> None:
        try:
            self._status_file.parent.mkdir(parents=True, exist_ok=True)
            self._status_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save repair status: {e}")

    def _update_repair_status(self, repair_id: str, status: dict) -> None:
        all_status = self._load_status()
        all_status[repair_id] = {
            **status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._save_status(all_status)

    def _load_history(self) -> list:
        try:
            if self._history_file.exists():
                return json.loads(self._history_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def _save_history(self, data: list) -> None:
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            self._history_file.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save repair history: {e}")

    def _append_history(self, record: dict) -> None:
        history = self._load_history()
        history.append({
            **record,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 100 records
        if len(history) > 100:
            history = history[-100:]
        self._save_history(history)

    # ─── Utility: gather context ──────────────────────────────────────────

    def _gather_watcher_repairs(self) -> List[dict]:
        """Get pending repairs from workspace watcher."""
        try:
            from services.workspace_watcher import get_workspace_watcher
            watcher = get_workspace_watcher()
            return list(watcher.get_pending_repairs().values())
        except Exception as e:
            logger.warning(f"Could not get watcher repairs: {e}")
            return []

    def _gather_agent_health(self) -> dict:
        """Get health status of all agents."""
        try:
            from agents.agent_registry import agent_registry
            return agent_registry.run_health_checks()
        except Exception as e:
            logger.warning(f"Could not get agent health: {e}")
            return {}

    def _check_file_syntax(self, file_path: str) -> Optional[dict]:
        """Check a Python file for syntax errors."""
        try:
            path = Path(file_path)
            if not path.exists():
                return {"type": "file_not_found", "msg": f"File not found: {file_path}"}
            if path.suffix == ".py":
                source = path.read_text(encoding="utf-8")
                ast.parse(source)
                return None  # No errors
            elif path.suffix == ".json":
                source = path.read_text(encoding="utf-8")
                json.loads(source)
                return None
        except SyntaxError as e:
            return {
                "type": "syntax_error",
                "msg": str(e),
                "lineno": e.lineno,
                "offset": e.offset,
                "text": e.text,
            }
        except json.JSONDecodeError as e:
            return {
                "type": "json_error",
                "msg": str(e),
                "lineno": e.lineno,
            }
        except Exception as e:
            return {"type": "unknown_error", "msg": str(e)}

    # ─── BaseAgent Pipeline: think → execute → report ─────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Analyze the repair request and produce a RepairPlan."""
        repair_id = f"rep_{uuid.uuid4().hex[:8]}"
        self.log(f"Starting repair analysis: {message[:100]}...")

        self._update_repair_status(repair_id, {
            "status": "analyzing",
            "message": message[:200],
            "progress": 10,
        })

        # Gather system context
        watcher_repairs = self._gather_watcher_repairs()
        agent_health = self._gather_agent_health()
        memory_context = self._memory.get_context_for_prompt()

        # Check if a specific file target is provided in context
        target_path = context.get("target_path", "")

        # Build analysis prompt
        system_prompt = (
            "You are the Repair Agent for AERIS (Autonomous Enhanced Reasoning Intelligence System).\n"
            "Your job is to diagnose issues and produce a structured repair plan.\n\n"
            "ISSUE TYPES you can classify:\n"
            "- syntax_error: Python/JS/JSON syntax issues\n"
            "- import_error: Missing or wrong imports\n"
            "- dependency_error: Missing packages or version mismatches\n"
            "- runtime_error: Crashes during execution\n"
            "- config_error: Bad configuration in .env or config files\n"
            "- tool_registry_error: Broken tool registration\n"
            "- agent_registry_error: Agent registration or health failures\n"
            "- frontend_build_error: Next.js/TypeScript build failures\n"
            "- backend_api_error: FastAPI endpoint errors\n"
            "- workflow_error: Malformed workflow JSON files\n\n"
            "SAFETY RULES:\n"
            "- NEVER suggest deleting files\n"
            "- NEVER suggest destructive shell commands\n"
            "- Mark risky fixes with risk_level='high'\n"
            "- Keep fixes scoped to affected files only\n"
        )

        user_prompt = (
            f"USER REPAIR REQUEST: {message}\n\n"
            f"TARGET PATH: {target_path or 'Not specified'}\n\n"
            f"WORKSPACE WATCHER PENDING REPAIRS ({len(watcher_repairs)}):\n"
            f"{json.dumps(watcher_repairs[:5], indent=2, default=str) if watcher_repairs else 'None'}\n\n"
            f"AGENT HEALTH STATUS:\n"
            f"{json.dumps({k: v.get('status', '?') for k, v in list(agent_health.items())[:10]}, indent=2) if agent_health else 'All healthy'}\n\n"
            f"REPAIR MEMORY CONTEXT:\n{memory_context}\n\n"
            f"Respond with ONLY valid JSON:\n"
            f'{{\n'
            f'  "issues": [\n'
            f'    {{"issue_type": "<type>", "file_path": "<path>", "error_msg": "<msg>", "line_number": null, "severity": "medium"}}\n'
            f'  ],\n'
            f'  "proposed_fixes": [\n'
            f'    {{"file_path": "<path>", "description": "<what to fix>", "command": null, "risk_level": "low"}}\n'
            f'  ],\n'
            f'  "risk_level": "low",\n'
            f'  "explanation": "<brief explanation of diagnosis>"\n'
            f'}}'
        )

        # Check episodic memory for matching past errors and fixes
        learned_fix = None
        try:
            from services.episodic_memory import recall_similar_episode
            episode = await recall_similar_episode(message, threshold=0.8)
            if episode:
                learned_fix = episode
                self.log(f"Found semantically similar past error: '{episode['error_msg']}' (similarity: {episode['similarity']:.2f})")
        except Exception as episodic_err:
            logger.warning(f"Failed to query episodic memory in think: {episodic_err}")

        # If target path is specified, check it for syntax errors first
        file_error = None
        if target_path:
            file_error = self._check_file_syntax(target_path)

        try:
            raw = await ai_engine.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            raw = raw.strip().strip("```json").strip("```").strip()
            plan_data = json.loads(raw)
        except Exception as e:
            logger.warning(f"LLM repair analysis failed: {e}. Using manual fallback.")
            plan_data = {
                "issues": [],
                "proposed_fixes": [],
                "risk_level": "medium",
                "explanation": f"LLM analysis failed ({e}). Manual inspection required.",
            }

        # Merge learned fix from episodic memory
        if learned_fix:
            plan_data.setdefault("issues", []).insert(0, {
                "issue_type": learned_fix.get("metadata", {}).get("error_type", "runtime_error"),
                "file_path": target_path or "Workspace/EpisodicMemory",
                "error_msg": f"Matching error signature from memory: {learned_fix['error_msg']}",
                "line_number": None,
                "severity": learned_fix.get("metadata", {}).get("severity", "medium"),
            })
            plan_data.setdefault("proposed_fixes", []).insert(0, {
                "file_path": target_path or "Workspace/EpisodicMemory",
                "description": f"[LEARNED FIX] {learned_fix['fix_applied']}",
                "command": None,
                "risk_level": "low",
            })
            plan_data["explanation"] = (
                f"[Learned Fix Applied] Match found in Episodic Memory with similarity {learned_fix['similarity']:.2f}. "
                f"Previous resolution: {learned_fix['fix_applied']}. "
                f"{plan_data.get('explanation', '')}"
            )

        # Merge file syntax errors if found
        if file_error:
            plan_data.setdefault("issues", []).insert(0, {
                "issue_type": file_error.get("type", "syntax_error"),
                "file_path": target_path,
                "error_msg": file_error.get("msg", "Unknown error"),
                "line_number": file_error.get("lineno"),
                "severity": "high",
            })

        # Build structured plan
        issues = [RepairIssue(**i) for i in plan_data.get("issues", [])]
        fixes = [RepairFix(**f) for f in plan_data.get("proposed_fixes", [])]
        risk = plan_data.get("risk_level", "medium")

        plan = RepairPlan(
            repair_id=repair_id,
            issues=issues,
            proposed_fixes=fixes,
            risk_level=risk,
            dry_run=context.get("dry_run", True),
            auto_apply=context.get("auto_apply", False),
            requires_approval=(risk in ("medium", "high")),
            explanation=plan_data.get("explanation", ""),
        )

        self._update_repair_status(repair_id, {
            "status": "plan_ready",
            "progress": 40,
            "plan": plan.to_dict(),
        })

        self.log(f"Repair plan created: {len(issues)} issues, {len(fixes)} fixes, risk={risk}")
        return plan

    async def execute(self, plan: Any) -> Any:
        """Execute the repair plan (with permission checks)."""
        if not isinstance(plan, RepairPlan):
            return RepairResult(
                repair_id="unknown",
                success=False,
                report="Invalid repair plan provided.",
            )

        from engine.state_manager import global_state_manager
        import asyncio
        global_state_manager.current_hud = "repaircenter"

        try:
            repair_id = plan.repair_id
            self.log(f"Executing repair plan {repair_id}...")

            self._update_repair_status(repair_id, {
                "status": "repairing",
                "progress": 50,
            })

            # If dry_run, skip execution
            if plan.dry_run:
                self.log(f"Dry run mode — skipping execution.")
                result = RepairResult(
                    repair_id=repair_id,
                    success=True,
                    issues_found=len(plan.issues),
                    issues_fixed=0,
                    report="DRY RUN — No changes applied. Review the repair plan above.",
                )
                self._update_repair_status(repair_id, {
                    "status": "complete_dry_run",
                    "progress": 100,
                    "result": result.to_dict(),
                })
                return result

            # If requires_approval and not auto_apply, halt
            if plan.requires_approval and not plan.auto_apply:
                self.log(f"Repair requires approval — halting execution.")
                result = RepairResult(
                    repair_id=repair_id,
                    success=True,
                    issues_found=len(plan.issues),
                    issues_fixed=0,
                    report="APPROVAL REQUIRED — Review the repair plan and approve to proceed.",
                )
                self._update_repair_status(repair_id, {
                    "status": "awaiting_approval",
                    "progress": 50,
                    "result": result.to_dict(),
                })
                return result

            # Permission check
            from services.permission_enforcer import PermissionEnforcer, PermissionMode
            enforcer = PermissionEnforcer(
                mode=PermissionMode.WORKSPACE_WRITE,
                workspace_root=str(settings.WORKSPACE_DIR),
            )

            files_changed = []
            commands_run = []
            fixes_applied = 0

            for fix in plan.proposed_fixes:
                # File write permission check
                if fix.file_path and fix.fixed_content:
                    perm = enforcer.check_file_write(fix.file_path)
                    if not perm.allowed:
                        logger.warning(f"Permission denied for file write: {fix.file_path} — {perm.reason}")
                        continue

                    try:
                        target = Path(fix.file_path)
                        if target.exists():
                            # Backup original if not already done
                            fix.original_content = target.read_text(encoding="utf-8")
                        target.write_text(fix.fixed_content, encoding="utf-8")
                        files_changed.append(fix.file_path)
                        fixes_applied += 1
                        self.log(f"Applied fix to: {fix.file_path}")
                    except Exception as e:
                        logger.error(f"Failed to apply fix to {fix.file_path}: {e}")

                # Shell command execution (with permission check)
                if fix.command:
                    perm = enforcer.check_bash(fix.command)
                    if not perm.allowed:
                        logger.warning(f"Permission denied for command: {fix.command} — {perm.reason}")
                        commands_run.append(f"BLOCKED: {fix.command}")
                        continue

                    # Only log the command, don't auto-execute
                    commands_run.append(f"SUGGESTED: {fix.command}")
                    self.log(f"Suggested command: {fix.command}")

            # Verify fixes
            verification_status = "not_verified"
            remaining_risks = []
            for fix in plan.proposed_fixes:
                if fix.file_path and fix.file_path in files_changed:
                    check = self._check_file_syntax(fix.file_path)
                    if check:
                        remaining_risks.append(f"{fix.file_path}: {check.get('msg', 'Unknown issue')}")
                        verification_status = "failed"
                    else:
                        verification_status = "passed"

            result = RepairResult(
                repair_id=repair_id,
                success=fixes_applied > 0 or plan.dry_run,
                issues_found=len(plan.issues),
                issues_fixed=fixes_applied,
                files_changed=files_changed,
                commands_run=commands_run,
                verification_status=verification_status,
                remaining_risks=remaining_risks,
            )

            self._update_repair_status(repair_id, {
                "status": "complete",
                "progress": 100,
                "result": result.to_dict(),
            })

            # Update memory stats
            self._memory.increment_stats("total_repairs")
            if result.success:
                self._memory.increment_stats("successful_repairs")
            else:
                self._memory.increment_stats("failed_repairs")

            # Append to history
            self._append_history({
                "repair_id": repair_id,
                "issues_found": result.issues_found,
                "issues_fixed": result.issues_fixed,
                "files_changed": result.files_changed,
                "success": result.success,
                "verification": result.verification_status,
            })

            return result
        finally:
            await asyncio.sleep(5)
            if global_state_manager.current_hud == "repaircenter":
                global_state_manager.current_hud = None

    async def report(self, results: Any) -> str:
        """Format a human-readable repair report."""
        if not isinstance(results, RepairResult):
            return str(results)

        r = results
        status_icon = "✅" if r.success else "❌"
        verify_icon = {"passed": "✅", "failed": "❌", "not_verified": "⏳"}.get(r.verification_status, "⏳")

        report_lines = [
            f"# {status_icon} AERIS Repair Report — `{r.repair_id}`\n",
            f"**Issues Found:** {r.issues_found}",
            f"**Issues Fixed:** {r.issues_fixed}",
            f"**Verification:** {verify_icon} {r.verification_status}\n",
        ]

        if r.files_changed:
            report_lines.append("### Files Changed")
            for f in r.files_changed:
                report_lines.append(f"- `{f}`")
            report_lines.append("")

        if r.commands_run:
            report_lines.append("### Commands")
            for c in r.commands_run:
                report_lines.append(f"- `{c}`")
            report_lines.append("")

        if r.remaining_risks:
            report_lines.append("### ⚠️ Remaining Risks")
            for risk in r.remaining_risks:
                report_lines.append(f"- {risk}")
            report_lines.append("")

        if r.report:
            report_lines.append(f"\n{r.report}")

        final_report = "\n".join(report_lines)
        results.report = final_report
        return final_report

    # ─── Task Failure Diagnosis ───────────────────────────────────────────

    async def diagnose_task_failure(self, task_result: dict, context: dict = None) -> dict:
        """Diagnose why an agent task failed and produce a report.
        
        Called by the Brain when any agent's run() returns success=False.
        Generates a diagnosis, optionally emails it, and saves to memory.
        """
        agent_name = task_result.get("agent", "Unknown")
        error = task_result.get("error", task_result.get("response", "No error details"))
        task_desc = context.get("task_description", "") if context else ""
        intent = task_result.get("intent", "unknown")

        self.log(f"Diagnosing task failure: {agent_name} — {error[:100]}")

        # Check memory for recurring patterns
        is_recurring, occurrence_count = self._memory.is_recurring_pattern(error)
        known_fix = self._memory.get_known_fix(intent)

        # LLM-powered diagnosis
        prompt = (
            f"You are the AERIS Repair Agent diagnosing a task failure.\n\n"
            f"FAILED AGENT: {agent_name}\n"
            f"TASK INTENT: {intent}\n"
            f"TASK DESCRIPTION: {task_desc}\n"
            f"ERROR: {error}\n\n"
            f"{'KNOWN FIX FROM MEMORY: ' + known_fix if known_fix else ''}\n"
            f"{'⚠️ RECURRING PATTERN: This error has occurred ' + str(occurrence_count) + ' time(s) before!' if is_recurring else ''}\n\n"
            f"Analyze this failure and respond with ONLY valid JSON:\n"
            f'{{\n'
            f'  "root_cause": "<what caused this failure>",\n'
            f'  "suggested_fix": "<specific steps to fix this>",\n'
            f'  "severity": "low|medium|high|critical",\n'
            f'  "error_type": "<one of: syntax_error, import_error, dependency_error, runtime_error, config_error, tool_registry_error, agent_registry_error, frontend_build_error, backend_api_error, workflow_error>"\n'
            f'}}'
        )

        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip().strip("```json").strip("```").strip()
            analysis = json.loads(raw)
        except Exception as e:
            logger.warning(f"LLM diagnosis failed: {e}")
            analysis = {
                "root_cause": f"Could not determine (LLM analysis failed: {e})",
                "suggested_fix": "Manual investigation required.",
                "severity": "medium",
                "error_type": "runtime_error",
            }

        # Build HTML email report
        recurring_warning = (
            f"<p style='color: #ff6d00; font-weight: bold;'>⚠️ RECURRING PATTERN — "
            f"This error has occurred {occurrence_count + 1} time(s)!</p>"
            if is_recurring else ""
        )

        report_html = f"""
        <div style="font-family: 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; background: #0a0f1e; color: #e0e0e0; padding: 24px; border-radius: 12px; border: 1px solid rgba(0,255,255,0.2);">
            <h2 style="color: #00ffff; margin-top: 0;">⚠️ AERIS Task Failure Report</h2>
            {recurring_warning}
            <table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
                <tr><td style="padding: 8px; color: #888; width: 120px;">Agent</td><td style="padding: 8px; color: #ff4444; font-weight: bold;">{agent_name}</td></tr>
                <tr><td style="padding: 8px; color: #888;">Intent</td><td style="padding: 8px;">{intent}</td></tr>
                <tr><td style="padding: 8px; color: #888;">Severity</td><td style="padding: 8px; color: {'#ff4444' if analysis.get('severity') in ('high', 'critical') else '#ffab00'};">{analysis.get('severity', 'medium').upper()}</td></tr>
                <tr><td style="padding: 8px; color: #888;">Error Type</td><td style="padding: 8px;">{analysis.get('error_type', 'unknown')}</td></tr>
                <tr><td style="padding: 8px; color: #888;">Time</td><td style="padding: 8px;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</td></tr>
            </table>
            <h3 style="color: #00ffff;">Error Details</h3>
            <pre style="background: #111827; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 12px; border: 1px solid rgba(0,255,255,0.1);">{error[:500]}</pre>
            <h3 style="color: #00ffff;">🔍 Root Cause</h3>
            <p>{analysis.get('root_cause', 'Unknown')}</p>
            <h3 style="color: #00e676;">💡 Suggested Fix</h3>
            <p>{analysis.get('suggested_fix', 'Manual investigation required.')}</p>
            <hr style="border-color: rgba(0,255,255,0.1); margin: 20px 0;">
            <p style="font-size: 11px; color: #666;">This report was generated by AERIS Repair Agent (MEDIC) v1.0.0</p>
        </div>
        """

        diagnosis = TaskFailureDiagnosis(
            agent_name=agent_name,
            task_description=task_desc,
            error=error,
            root_cause=analysis.get("root_cause", "Unknown"),
            suggested_fix=analysis.get("suggested_fix", "Manual investigation required."),
            severity=analysis.get("severity", "medium"),
            is_recurring=is_recurring,
            occurrence_count=occurrence_count + 1,
            report_html=report_html,
            should_email=self._memory.get_preference("auto_email_on_failure", True),
        )

        # Save failure pattern to memory
        self._memory.add_failure_pattern({
            "agent_name": agent_name,
            "error_type": analysis.get("error_type", "unknown"),
            "error": error,
            "root_cause": analysis.get("root_cause", ""),
            "suggested_fix": analysis.get("suggested_fix", ""),
        })

        # Save to episodic vector memory
        try:
            from services.episodic_memory import add_episode
            await add_episode(
                error_msg=error,
                fix_applied=analysis.get("suggested_fix", "Manual investigation required."),
                metadata={
                    "agent_name": agent_name,
                    "error_type": analysis.get("error_type", "unknown"),
                    "intent": intent,
                    "root_cause": analysis.get("root_cause", ""),
                    "severity": analysis.get("severity", "medium")
                }
            )
        except Exception as episodic_err:
            logger.warning(f"Failed to save episodic vector memory: {episodic_err}")

        # Add to repair history
        self._append_history({
            "type": "task_failure_diagnosis",
            "repair_id": f"diag_{uuid.uuid4().hex[:8]}",
            "agent": agent_name,
            "intent": intent,
            "error_type": analysis.get("error_type", "unknown"),
            "severity": analysis.get("severity", "medium"),
            "root_cause": analysis.get("root_cause", ""),
            "suggested_fix": analysis.get("suggested_fix", ""),
            "is_recurring": is_recurring,
            "occurrence_count": occurrence_count + 1,
        })

        return diagnosis.to_dict()

    # ─── Public accessors for API ─────────────────────────────────────────

    def get_status(self, repair_id: str) -> Optional[dict]:
        """Get the status of a specific repair."""
        all_status = self._load_status()
        return all_status.get(repair_id)

    def get_history(self) -> list:
        """Get the repair history."""
        return self._load_history()

    def get_memory(self) -> dict:
        """Get the repair agent's personal memory."""
        return self._memory.get_data()

    def add_memory_note(self, note: str) -> None:
        """Add a personal note to the repair agent's memory."""
        self._memory.add_personal_note(note)
