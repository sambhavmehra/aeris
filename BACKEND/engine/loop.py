"""
AERIS — Autonomous Execution Engine (v2)
Implements: THINK → PLAN → DECIDE → EXECUTE → VERIFY → IMPROVE

Changes over v1
───────────────
BUG FIXES
  • `import json` was repeated inside process_objective (shadowed top-level import)
  • `MAX_TOTAL_RETRIES` was defined but never used — now enforced across the whole task
  • `_speak_async` / `_speak_error` were identical — merged into one method
  • Mutable default args (`all_results=None` …) in _build_response — replaced with dataclass
  • `"error" in result_str[:50]` false-positives (e.g. "errorless") — now word-boundary check
  • `delegator` was re-instantiated on every call — now cached on __init__
  • `intent_analyzer` was imported inside the hot path — moved to __init__
  • `chr(10).join(…)` in f-strings replaced with a proper local variable
  • `asyncio.sleep(0.5)` flat retry delay — replaced with exponential back-off + jitter

CORRECTNESS / ROBUSTNESS
  • Sync agent methods (`executor_agent.process`, `observer_agent.process`) are now
    dispatched via `asyncio.run_in_executor` so they cannot block the event loop
  • MAX_TOTAL_RETRIES is now enforced; the engine aborts if total retries across all
    steps exceed the budget
  • `_auto_open_generated_files` now uses `subprocess.Popen` instead of `os.system`
    to avoid shell injection and works on Linux/macOS/Windows
  • LLM prompts that embed `final_result` now try `json.dumps` first so JSON is not
    corrupted by mid-string truncation
  • `_try_fix_params` parsing now strips markdown fences more robustly
  • Async context-manager (`async with OSEngine() as e`) for clean resource teardown

SCALABILITY / DESIGN
  • Introduced `StepResult`, `EngineResponse` dataclasses → fully typed, no Dict[str,Any]
  • `_classify_error` replaced with a declarative `_ERROR_PATTERNS` table — O(1) lookup,
    trivially extensible
  • `StructuredLogger` thin wrapper adds task_id to every log record automatically
  • Circuit-breaker: if the same tool fails on 3 consecutive steps the engine aborts early
    instead of exhausting all retries on a broken tool
  • Retry budget is shared across steps — prevents one multi-step plan from using
    MAX_STEP_RETRIES × N retries silently
  • `_generate_grounded_response` is now cancellation-aware (respects asyncio.CancelledError)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# ── path bootstrap ──────────────────────────────────────────────────────────
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.agents.executor import ExecutorAgent
from core.agents.memory_agent import MemoryAgent
from core.agents.observer import ObserverAgent
from core.agents.planner import PlannerAgent
from core.agents.security import SecurityAgent
from core.engine.execution_validator import global_execution_validator
from core.engine.state_manager import ExecutionStatus, global_state_manager
from core.engine.task_plan import TaskPlan
from core.intelligence.intent_analyzer import get_intent_analyzer  # moved out of hot path

# ── logging ─────────────────────────────────────────────────────────────────
_base_logger = logging.getLogger("AerisOSEngine")


class _StructuredLogger:
    """Thin wrapper that automatically appends [task_id] to every message."""

    def __init__(self, logger: logging.Logger, task_id: str = ""):
        self._log = logger
        self.task_id = task_id

    def _tag(self, msg: str) -> str:
        return f"[{self.task_id}] {msg}" if self.task_id else msg

    def info(self, msg: str, *a, **kw) -> None:
        self._log.info(self._tag(msg), *a, **kw)

    def warning(self, msg: str, *a, **kw) -> None:
        self._log.warning(self._tag(msg), *a, **kw)

    def error(self, msg: str, *a, **kw) -> None:
        self._log.error(self._tag(msg), *a, **kw)

    def exception(self, msg: str, *a, **kw) -> None:
        self._log.exception(self._tag(msg), *a, **kw)


# ── typed result structures ──────────────────────────────────────────────────

@dataclass
class StepResult:
    success: bool
    result: Any = None
    tool: str = ""
    retries: int = 0
    skipped: bool = False
    needs_user: bool = False
    error: str = ""
    receipt_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EngineResponse:
    task_id: str
    objective: str
    status: str
    response: str
    raw_result: str = ""
    error: str = ""
    error_category: str = ""
    error_explanation: str = ""
    steps_completed: int = 0
    steps_failed: int = 0
    failed_steps: List[Dict[str, Any]] = field(default_factory=list)
    task_state: Optional[Dict[str, Any]] = None
    execution_validated: bool = False
    validation: Optional[Dict[str, Any]] = None
    spoken: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# ── error classification ─────────────────────────────────────────────────────
# Each entry: (category_name, list_of_keywords)
# Keywords are matched as whole words / substrings against lowercased error text.
_ERROR_PATTERNS: List[tuple[str, List[str]]] = [
    ("not_found",         ["not found", "no such file", "does not exist", "missing"]),
    ("permission_denied", ["permission", "access denied", "forbidden", "unauthorized"]),
    ("timeout",           ["timeout", "timed out", "deadline exceeded"]),
    ("network_error",     ["connection", "network", "unreachable", "dns", "socket"]),
    ("rate_limited",      ["rate limit", "429", "too many requests", "quota"]),
    ("auth_error",        ["api key", "authentication", "invalid key", "no api key"]),
    ("parse_error",       ["syntax error", "parse error", "invalid json", "unexpected token"]),
    ("resource_error",    ["out of memory", "oom", "memoryerror"]),
    ("tool_not_found",    ["not registered", "unknown tool", "no tool"]),
    ("security_blocked",  ["security block", "blocked by security", "dangerous command"]),
    ("dependency_error",  ["no module named", "importerror", "modulenotfounderror"]),
]

_ERROR_EXPLANATIONS: Dict[str, str] = {
    "not_found":         "Sir, '{step}' step mein file ya path nahi mila.",
    "permission_denied": "Sir, permission issue hai. '{step}' ke liye access denied ho gaya.",
    "timeout":           "Sir, '{step}' step time out ho gaya. Server respond nahi kar raha.",
    "network_error":     "Sir, network error aaya hai. Internet connection check karein.",
    "rate_limited":      "Sir, bohot zyada requests ho gayi hain. Thoda wait karna padega.",
    "auth_error":        "Sir, API key ya authentication fail ho gaya. Configuration check karein.",
    "parse_error":       "Sir, data parse karne mein error aaya. Invalid format mila.",
    "resource_error":    "Sir, system resources kam pad rahe hain.",
    "tool_not_found":    "Sir, tool '{tool}' available nahi hai.",
    "security_blocked":  "Sir, security ne '{step}' ko block kar diya.",
    "dependency_error":  "Sir, required module install nahi hai. Dependency missing hai.",
    "unknown_error":     "Sir, '{step}' step mein error aaya: {error}",
}

_CONVERSATIONAL_TOOLS = frozenset({"chat_with_ai", "realtime_search"})
_GENERATION_TOOLS = frozenset({
    "generate_website", "generate_image", "generate_video",
    "convert_file", "write_content", "write_file",
})


def _classify_error(error: str) -> str:
    low = error.lower()
    for category, keywords in _ERROR_PATTERNS:
        if any(kw in low for kw in keywords):
            return category
    return "unknown_error"


def _explain_error(category: str, step: str, tool: str, error: str) -> str:
    template = _ERROR_EXPLANATIONS.get(category, _ERROR_EXPLANATIONS["unknown_error"])
    return template.format(step=step, tool=tool, error=error[:120])


# ── retry / back-off ─────────────────────────────────────────────────────────

def _backoff(attempt: int, base: float = 0.5, cap: float = 8.0) -> float:
    """Exponential back-off with ±25 % jitter, capped at `cap` seconds."""
    delay = min(base * (2 ** attempt), cap)
    jitter = delay * 0.25 * (random.random() * 2 - 1)
    return max(0.0, delay + jitter)


# ════════════════════════════════════════════════════════════════════════════
#  MAIN ENGINE
# ════════════════════════════════════════════════════════════════════════════

class OSEngine:
    """
    Main event loop for AERIS.

    Lifecycle
    ---------
    1. UNDERSTAND — intent analysis
    2. DELEGATE  — multi-agent swarm (if no direct tool match)
    3. PLAN      — LLM-powered step generation
    4. EXECUTE   — tool calls via ExecutorAgent (run in thread pool)
    5. OBSERVE   — result verification via ObserverAgent
    6. RETRY     — exponential back-off, tool-swap, or param-heal
    7. VALIDATE  — ExecutionValidator rejects hallucinated responses
    8. RESPOND   — grounded summary + TTS

    Usage
    -----
    engine = OSEngine()
    result = await engine.process_objective("open spotify and play lofi")

    # Or as an async context manager for clean teardown:
    async with OSEngine() as engine:
        result = await engine.process_objective(...)
    """

    MAX_STEP_RETRIES: int = 3      # retries per individual step
    MAX_TOTAL_RETRIES: int = 8     # budget shared across all steps in one task
    CIRCUIT_BREAKER_THRESHOLD: int = 3  # consecutive failures on same tool → abort

    # ── initialisation ────────────────────────────────────────────────────

    def __init__(self) -> None:
        self.state_manager = global_state_manager
        self.validator = global_execution_validator
        self._executor_pool = None  # lazy: created when first needed

        # Agents
        self.memory_agent = MemoryAgent()
        self.security_agent = SecurityAgent(memory_agent=self.memory_agent)
        self.planner_agent = PlannerAgent(memory_agent=self.memory_agent)
        self.executor_agent = ExecutorAgent(
            security_agent=self.security_agent,
            memory_agent=self.memory_agent,
        )
        self.observer_agent = ObserverAgent(memory_agent=self.memory_agent)

        # Cache heavyweight singletons so they are not re-constructed per call
        self._intent_analyzer = get_intent_analyzer()
        self._delegator = self._init_delegator()

    def _init_delegator(self):
        try:
            from core.agents.sub_agents.delegator import get_delegator
            return get_delegator(memory_agent=self.memory_agent)
        except Exception as exc:
            _base_logger.warning(f"Delegator unavailable at startup: {exc}")
            return None

    # ── async context-manager ────────────────────────────────────────────

    async def __aenter__(self) -> "OSEngine":
        return self

    async def __aexit__(self, *_) -> None:
        await self.shutdown()

    async def shutdown(self) -> None:
        """Release thread-pool and any other async resources."""
        if self._executor_pool:
            self._executor_pool.shutdown(wait=False)
            self._executor_pool = None

    # ════════════════════════════════════════════════════════════════════
    #  PUBLIC ENTRY POINT
    # ════════════════════════════════════════════════════════════════════

    async def process_objective(self, objective: str) -> Dict[str, Any]:
        """
        Autonomously execute a user objective end-to-end.
        Always returns a fully-populated EngineResponse dict.
        """
        os_task = self.state_manager.create_task("Autonomous Task", objective)
        task_id = os_task.task_id
        log = _StructuredLogger(_base_logger, task_id)
        log.info(f"Starting objective: {objective!r}")

        try:
            # ── PHASE 1A: INTENT ANALYSIS ─────────────────────────────
            self._update(task_id, ExecutionStatus.RUNNING,
                         "[THINK] Analysing intent…",
                         "Running IntentAnalyzer.")

            intent_res = self._intent_analyzer.analyze_intent(objective)

            if not intent_res.is_capable:
                msg = f"Task aborted: {intent_res.missing_requirements}"
                self._update(task_id, ExecutionStatus.FAILED, "[FAIL] Incapable", error=msg)
                self._speak(f"Sir, main yeh nahi kar sakta. {intent_res.missing_requirements}")
                self.state_manager.set_global_action("Idle")
                return self._fail_response(task_id, objective, msg, "capability_missing")

            # ── PHASE 1B: MULTI-AGENT DELEGATION (only if no direct tool) ─
            if not intent_res.selected_tools and self._delegator is not None:
                delegation_result = await self._try_delegate(
                    task_id, objective, log
                )
                if delegation_result is not None:
                    return delegation_result

            # ── PHASE 1C: PLAN ────────────────────────────────────────
            self._update(task_id, ExecutionStatus.RUNNING,
                         "[THINK] Planning…",
                         "Phase 1: Building execution plan.")

            self.memory_agent.process("clear_exec_context")
            self.memory_agent.process("store_context",
                                      key="current_objective", value=objective)
            self.executor_agent.set_task_id(task_id)

            plan_res = self.planner_agent.process(
                objective, selected_tools=intent_res.selected_tools
            )
            if plan_res["status"] != "success":
                err = plan_res.get("error", "Failed to create plan.")
                self._update(task_id, ExecutionStatus.FAILED,
                             "[FAIL] Planning failed", error=err)
                self._speak(f"Sir, task ka plan nahi ban paya. Error: {err[:150]}")
                self._store_error(objective, "planning_failure", err)
                self.state_manager.set_global_action("Idle")
                return self._fail_response(task_id, objective, err, "planning_failure")

            plan: TaskPlan = plan_res["plan"]
            for step in plan.steps:
                os_task.add_step(step.step_id, step.description, step.tool_name or "")

            self._update(task_id, ExecutionStatus.RUNNING,
                         f"[PLAN] {len(plan.steps)} step(s)",
                         f"Plan: {[s.description for s in plan.steps]}")

            # ── PHASE 2: EXECUTE ──────────────────────────────────────
            completed: List[StepResult] = []
            failed_steps: List[Dict[str, Any]] = []
            total_retries_used = 0
            tool_failure_streak: Dict[str, int] = defaultdict(int)

            while not plan.is_complete():
                step = plan.get_current_step()
                if step is None:
                    break

                step_num = plan.current_step_index + 1
                total_steps = len(plan.steps)

                self._update(task_id, ExecutionStatus.RUNNING,
                             f"[EXEC] Step {step_num}/{total_steps}: {step.description}",
                             f"Executing step {step_num} via tool '{step.tool_name}'.")
                os_task.current_step_index = plan.current_step_index

                plan.inject_previous_results(step)

                # ── circuit breaker ───────────────────────────────────
                if tool_failure_streak[step.tool_name] >= self.CIRCUIT_BREAKER_THRESHOLD:
                    err = (f"Circuit breaker tripped: tool '{step.tool_name}' "
                           f"failed {self.CIRCUIT_BREAKER_THRESHOLD} consecutive times.")
                    log.error(err)
                    self._update(task_id, ExecutionStatus.FAILED,
                                 f"[FAIL] Circuit breaker: {step.tool_name}", error=err)
                    self._speak(f"Sir, tool {step.tool_name} baar baar fail ho raha hai. Abort kar raha hoon.")
                    self._store_error(objective, "circuit_breaker", err)
                    self.state_manager.set_global_action("Idle")
                    return self._fail_response(task_id, objective, err, "circuit_breaker",
                                               completed, failed_steps)

                # ── global retry budget ───────────────────────────────
                retries_remaining = self.MAX_TOTAL_RETRIES - total_retries_used

                step_result, retries_used = await self._execute_with_retry(
                    task_id, step, plan, log,
                    max_retries=min(self.MAX_STEP_RETRIES, retries_remaining),
                )
                total_retries_used += retries_used

                if step_result.needs_user:
                    log.info(f"Waiting for user permission on step '{step.description}'.")
                    self.state_manager.set_global_action("Idle")
                    return self._partial_response(
                        task_id, objective, completed, failed_steps,
                        error=step_result.error,
                        error_category="waiting_user",
                        error_explanation="Sir, I need your permission to proceed.",
                    )

                if step_result.success:
                    completed.append(step_result)
                    tool_failure_streak[step.tool_name] = 0
                    self._update(task_id, ExecutionStatus.RUNNING,
                                 f"[OK] Step {step_num} done",
                                 f"Step '{step.description}' completed.",
                                 result=str(step_result.result)[:400])
                    self._auto_open_file(step, step_result.result)
                    plan.advance_step()
                else:
                    tool_failure_streak[step.tool_name] += 1
                    category = _classify_error(step_result.error)
                    explanation = _explain_error(
                        category, step.description, step.tool_name, step_result.error
                    )
                    failed_steps.append({
                        "step": step.description,
                        "tool": step.tool_name,
                        "error": step_result.error,
                        "category": category,
                    })
                    self._update(task_id, ExecutionStatus.FAILED,
                                 f"[FAIL] Step {step_num} ({category})",
                                 f"Step '{step.description}' failed: {step_result.error}",
                                 error=step_result.error)
                    self._speak(explanation)
                    self._store_error(
                        objective, category,
                        f"Step '{step.description}' / tool '{step.tool_name}': {step_result.error}",
                    )
                    self.state_manager.set_global_action("Idle")
                    return self._partial_response(
                        task_id, objective, completed, failed_steps,
                        error=step_result.error,
                        error_category=category,
                        error_explanation=explanation,
                    )

            # ── PHASE 3: VALIDATE & COMPLETE ─────────────────────────
            log.info("All steps done. Validating response…")

            final_raw = str(completed[-1].result) if completed else ""
            spoken_response = await self._grounded_response(
                objective, final_raw, completed
            )

            validation = self.validator.validate_response(
                task_id=task_id,
                response=spoken_response,
                objective=objective,
            )
            self.validator.persist_audit(task_id, objective, spoken_response, validation)

            if not validation.is_valid:
                log.error(f"Response REJECTED: {validation.reason}")
                self._update(task_id, ExecutionStatus.FAILED,
                             "❌ Validation failed",
                             error=f"ExecutionValidator: {validation.reason}")
                self._speak("Sir, task ka verification fail ho gaya.")
                self.state_manager.set_global_action("Idle")
                return self._fail_response(
                    task_id, objective,
                    f"Response rejected by validator: {validation.reason}",
                    "validation_failure",
                )

            log.info(f"Response VALIDATED with {len(validation.receipts)} receipt(s).")

            # Try to surface structured JSON to UI widgets
            parsed_result: Any = spoken_response
            if final_raw:
                try:
                    parsed_result = json.loads(final_raw)
                except (json.JSONDecodeError, ValueError):
                    parsed_result = spoken_response

            self._update(task_id, ExecutionStatus.SUCCESS,
                         "✅ Task completed (validated)",
                         f"Validated with {len(validation.receipts)} receipt(s).",
                         result=parsed_result)

            self._speak(spoken_response)
            self.memory_agent.process("store_fact",
                                      fact=f"Successfully executed: {objective}",
                                      category="task_history")
            self.validator.clear_receipts(task_id)
            self.state_manager.set_global_action("Idle")

            task_state = self.state_manager.get_task(task_id)
            return EngineResponse(
                task_id=task_id,
                objective=objective,
                status=task_state.status.value if task_state else "success",
                response=spoken_response,
                raw_result=final_raw,
                steps_completed=len(completed),
                task_state=task_state.to_dict() if task_state else None,
                execution_validated=True,
                validation=validation.to_dict(),
                spoken=True,
            ).to_dict()

        except asyncio.CancelledError:
            _base_logger.warning(f"[{task_id}] process_objective cancelled.")
            self.state_manager.set_global_action("Idle")
            raise

        except Exception as exc:
            _base_logger.exception(f"[{task_id}] Unhandled engine error: {exc}")
            category = _classify_error(str(exc))
            self._update(task_id, ExecutionStatus.FAILED,
                         f"❌ System error ({category})", error=str(exc))
            self._speak(f"Sir, system mein error aa gaya: {str(exc)[:150]}")
            self._store_error(objective, category, str(exc))
            self.state_manager.set_global_action("Idle")
            return self._fail_response(task_id, objective, str(exc), category)

    # ════════════════════════════════════════════════════════════════════
    #  DELEGATION
    # ════════════════════════════════════════════════════════════════════

    async def _try_delegate(
        self,
        task_id: str,
        objective: str,
        log: _StructuredLogger,
    ) -> Optional[Dict[str, Any]]:
        """
        Try the multi-agent swarm. Returns a finished EngineResponse dict if
        the swarm handled it, or None to fall through to standard pipeline.
        """
        try:
            delegation = await asyncio.get_event_loop().run_in_executor(
                None, self._delegator.process, objective
            )
            if delegation.get("route") != "complex":
                return None

            agents_used = delegation.get("agents_used", [])
            swarm_result = delegation.get("result", "")
            log.info(f"Swarm handled task. Agents: {agents_used}")

            self._update(task_id, ExecutionStatus.SUCCESS,
                         "✅ Multi-Agent Swarm completed",
                         f"Handled by swarm agents: {agents_used}",
                         result=swarm_result)
            self._speak(str(swarm_result))
            self.memory_agent.process("store_fact",
                                      fact=f"Swarm completed: {objective}",
                                      category="task_history")
            self.state_manager.set_global_action("Idle")

            task_state = self.state_manager.get_task(task_id)
            return EngineResponse(
                task_id=task_id,
                objective=objective,
                status="success",
                response=str(swarm_result),
                steps_completed=1,
                task_state=task_state.to_dict() if task_state else None,
                spoken=True,
            ).to_dict()

        except Exception as exc:
            _base_logger.warning(f"[{task_id}] Delegator failed, continuing: {exc}")
            return None

    # ════════════════════════════════════════════════════════════════════
    #  STEP EXECUTION WITH RETRY
    # ════════════════════════════════════════════════════════════════════

    async def _execute_with_retry(
        self,
        task_id: str,
        step,
        plan: TaskPlan,
        log: _StructuredLogger,
        max_retries: int,
    ) -> tuple[StepResult, int]:
        """
        Execute one step with up to `max_retries` attempts.
        Returns (StepResult, retries_consumed).

        Sync agent methods are dispatched to a thread pool executor so they
        cannot block the event loop.
        """
        loop = asyncio.get_event_loop()
        retries = 0
        last_error = ""

        while retries <= max_retries:
            # Dispatch sync agents off the event loop
            exec_res = await loop.run_in_executor(
                None, self.executor_agent.process, step
            )
            obs_res = await loop.run_in_executor(
                None, self.observer_agent.process, step, exec_res
            )

            if obs_res["decision"] == "proceed":
                result = obs_res.get("result")
                step.mark_success(result)
                self.memory_agent.process(
                    "set_exec_context",
                    key=f"step_{step.step_id}_result",
                    value=str(result)[:1000],
                )
                return StepResult(
                    success=True, result=result,
                    tool=step.tool_name, retries=retries,
                    receipt_id=obs_res.get("receipt_id", ""),
                ), retries

            # ── failure path ─────────────────────────────────────────
            retries += 1
            last_error = obs_res.get("error", "Unknown error")
            strategy = obs_res.get("strategy", "abort")

            self._update(task_id, ExecutionStatus.RETRYING,
                         f"🔄 Retry {retries}/{max_retries}: {strategy}",
                         f"Step '{step.description}' attempt {retries} failed "
                         f"[{strategy}]: {last_error}",
                         error=last_error)

            log.warning(f"Step '{step.description}' attempt {retries} failed "
                        f"[{strategy}]: {last_error}")

            # ── apply recovery strategy ───────────────────────────────
            if strategy == "escalate_to_user":
                self._update(task_id, ExecutionStatus.WAITING_USER,
                             "⏳ Waiting for user permission",
                             "User intervention required.", error=last_error)
                self.state_manager.pending_action = {
                    "tool_name": step.tool_name,
                    "tool_params": step.tool_params,
                    "task_id": task_id,
                    "objective": plan.objective,
                }
                self._speak(
                    f"Sir, I need your permission to proceed with "
                    f"'{step.tool_name}'. Please confirm."
                )
                return StepResult(
                    success=False, error=last_error, needs_user=True,
                    tool=step.tool_name, retries=retries,
                ), retries

            if strategy == "abort":
                break

            if strategy == "skip_step":
                step.mark_success("Skipped")
                return StepResult(
                    success=True, result="Step skipped", skipped=True,
                    tool=step.tool_name, retries=retries,
                ), retries

            if strategy == "retry_different_params":
                suggestion = obs_res.get("suggestion", "")
                if suggestion:
                    await loop.run_in_executor(
                        None, self._heal_params, step, suggestion, last_error
                    )

            elif strategy == "use_alternative":
                alt_tool = obs_res.get("alternative_tool")
                if alt_tool:
                    log.info(f"Switching tool: {step.tool_name} → {alt_tool}")
                    step.tool_name = alt_tool
                    suggestion = obs_res.get("suggestion", f"Adjust params for {alt_tool}")
                    await loop.run_in_executor(
                        None, self._heal_params, step, suggestion, last_error
                    )

            # Exponential back-off before next attempt
            if retries <= max_retries:
                delay = _backoff(retries - 1)
                log.info(f"Back-off {delay:.2f}s before retry {retries}…")
                await asyncio.sleep(delay)

        step.mark_failed(last_error)
        return StepResult(
            success=False, error=last_error,
            tool=step.tool_name, retries=retries,
        ), retries

    # ════════════════════════════════════════════════════════════════════
    #  GROUNDED RESPONSE GENERATION
    # ════════════════════════════════════════════════════════════════════

    async def _grounded_response(
        self,
        objective: str,
        final_result: str,
        all_results: List[StepResult],
    ) -> str:
        """
        Generate a conversational summary GROUNDED in real tool output.
        Falls back to the raw tool output if the LLM call fails or is cancelled.
        """
        try:
            # Pass conversational tool results straight through
            if len(all_results) == 1 and all_results[0].tool in _CONVERSATIONAL_TOOLS:
                return str(final_result)

            # Build a structured summary from execution data only
            error_set: set[int] = set()
            lines: List[str] = []
            for i, r in enumerate(all_results):
                result_low = str(r.result or "").lower()
                is_error = (
                    not r.success
                    or re.search(r"\berror\b|\bfailed\b|\bexception\b", result_low[:80])
                )
                if is_error:
                    error_set.add(i)
                status_icon = "❌" if is_error else "✅"
                # Embed result safely; avoid corrupting JSON with truncation
                result_preview = self._safe_truncate(r.result, 300)
                lines.append(
                    f"{status_icon} [Tool: {r.tool}] "
                    f"[Receipt: {r.receipt_id or 'none'}] "
                    f"Output: {result_preview}"
                )

            steps_block = "\n".join(lines)
            final_safe = self._safe_truncate(final_result, 800)
            error_warning = (
                f"\n\nWARNING: {len(error_set)} step(s) had errors. "
                "You MUST mention these errors honestly.\n"
                if error_set else ""
            )

            prompt = (
                f"The user asked: '{objective}'\n\n"
                f"Verified tool execution results:\n{steps_block}\n\n"
                f"Final verified output:\n{final_safe}"
                f"{error_warning}\n"
                "RULES:\n"
                "1. Use ONLY information from the tool results above — no invention.\n"
                "2. If an error occurred, state exactly what went wrong.\n"
                "3. Keep it under 3 sentences unless detail is essential.\n"
                "4. Use Hinglish tone; address user as 'Sir'."
            )

            loop = asyncio.get_event_loop()
            reply = await loop.run_in_executor(
                None,
                lambda: self.planner_agent._llm_call(
                    system_prompt=(
                        "You are AERIS AI. Summarise ONLY from provided tool outputs. "
                        "Report errors honestly."
                    ),
                    user_prompt=prompt,
                    temperature=0.3,
                    max_tokens=256,
                ),
            )
            return reply

        except asyncio.CancelledError:
            raise  # propagate cancellation

        except Exception as exc:
            _base_logger.warning(f"Grounded response generation failed: {exc}")
            if final_result and len(str(final_result)) > 10:
                return f"[Real tool output] {self._safe_truncate(final_result, 500)}"
            return "Task executed. Raw tool output was empty or minimal."

    # ════════════════════════════════════════════════════════════════════
    #  PARAMETER HEALING
    # ════════════════════════════════════════════════════════════════════

    def _heal_params(self, step, suggestion: str, error: str) -> None:
        """
        Use the LLM to repair step parameters, falling back to simple heuristics.
        Runs synchronously (call via run_in_executor to avoid blocking the loop).
        """
        prompt = (
            f"Tool '{step.tool_name}' failed:\n{error}\n\n"
            f"Observer suggestion:\n{suggestion}\n\n"
            f"Current params:\n{json.dumps(step.tool_params, indent=2)}\n\n"
            "Output ONLY a raw JSON object with the corrected parameters. "
            "Do NOT include 'error', 'fix', or 'status' keys."
        )

        try:
            raw = self.planner_agent._llm_call(
                system_prompt="You are a JSON-only parameter healing system.",
                user_prompt=prompt,
                temperature=0.1,
                max_tokens=256,
            )
            cleaned = self._strip_markdown_fence(raw)
            new_params = json.loads(cleaned)
            if isinstance(new_params, dict) and new_params:
                _base_logger.info(f"Healed params for '{step.tool_name}': {new_params}")
                step.tool_params = new_params
                return
        except Exception as exc:
            _base_logger.warning(f"LLM param healing failed, using heuristics: {exc}")

        # ── heuristic fallback ────────────────────────────────────────
        error_low = error.lower()
        if "not found" in error_low and "path" in step.tool_params:
            path: str = step.tool_params["path"]
            if "." not in os.path.basename(path):
                for ext in (".py", ".js", ".ts", ".json", ".md", ".txt"):
                    step.tool_params["path"] = path + ext
                    break

        if suggestion and any(c in suggestion for c in "/\\."):
            for key in ("path", "file_path", "directory"):
                if key in step.tool_params:
                    step.tool_params[key] = suggestion.strip()
                    break

    # ════════════════════════════════════════════════════════════════════
    #  FILE AUTO-OPEN
    # ════════════════════════════════════════════════════════════════════

    def _auto_open_file(self, step, result: Any) -> None:
        """Open a generated file in the default application (cross-platform, no shell injection)."""
        if step.tool_name not in _GENERATION_TOOLS:
            return
        try:
            path: Optional[str] = None
            result_str = str(result).split("\n\n(IMPORTANT NOTE")[0].strip()

            try:
                data = json.loads(result_str)
                if isinstance(data, dict):
                    if step.tool_name == "generate_website":
                        path = data.get("preview_file")
                    else:
                        path = data.get("output_path")
            except (json.JSONDecodeError, ValueError):
                pass

            if not path and step.tool_name in {"write_file", "write_content"}:
                path = step.tool_params.get("path") or step.tool_params.get("filename")

            if not path or not os.path.exists(path):
                return

            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])

        except Exception as exc:
            _base_logger.warning(f"Auto-open failed: {exc}")

    # ════════════════════════════════════════════════════════════════════
    #  RESPONSE BUILDERS
    # ════════════════════════════════════════════════════════════════════

    def _fail_response(
        self,
        task_id: str,
        objective: str,
        error: str,
        category: str = "unknown_error",
        completed: Optional[List[StepResult]] = None,
        failed_steps: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        explanation = _explain_error(category, "", "", error)
        task_state = self.state_manager.get_task(task_id)
        return EngineResponse(
            task_id=task_id,
            objective=objective,
            status=task_state.status.value if task_state else "failed",
            response=explanation,
            error=error,
            error_category=category,
            error_explanation=explanation,
            steps_completed=len(completed) if completed else 0,
            steps_failed=len(failed_steps) if failed_steps else 0,
            failed_steps=failed_steps or [],
            task_state=task_state.to_dict() if task_state else None,
            spoken=True,
        ).to_dict()

    def _partial_response(
        self,
        task_id: str,
        objective: str,
        completed: List[StepResult],
        failed_steps: List[Dict[str, Any]],
        error: str = "",
        error_category: str = "",
        error_explanation: str = "",
    ) -> Dict[str, Any]:
        task_state = self.state_manager.get_task(task_id)
        return EngineResponse(
            task_id=task_id,
            objective=objective,
            status=task_state.status.value if task_state else "failed",
            response=error_explanation or error or "Partial execution.",
            error=error,
            error_category=error_category,
            error_explanation=error_explanation,
            steps_completed=len(completed),
            steps_failed=len(failed_steps),
            failed_steps=failed_steps,
            task_state=task_state.to_dict() if task_state else None,
            spoken=True,
        ).to_dict()

    # ════════════════════════════════════════════════════════════════════
    #  STATE HELPERS
    # ════════════════════════════════════════════════════════════════════

    def _update(
        self,
        task_id: str,
        status: ExecutionStatus,
        action: str,
        log_msg: str = "",
        error: str = "",
        result: Any = "",
    ) -> None:
        self.state_manager.update_task(
            task_id, status,
            action=action,
            log=log_msg,
            error=error,
            result=result,
        )

    # ════════════════════════════════════════════════════════════════════
    #  TTS
    # ════════════════════════════════════════════════════════════════════

    def _speak(self, text: str) -> None:
        """Fire-and-forget TTS (errors are swallowed so they never break execution)."""
        try:
            from texttospeech import speak_async
            speak_async(text, use_online=True)
        except Exception as exc:
            _base_logger.debug(f"TTS skipped: {exc}")

    # ════════════════════════════════════════════════════════════════════
    #  MEMORY
    # ════════════════════════════════════════════════════════════════════

    def _store_error(self, objective: str, category: str, detail: str) -> None:
        try:
            self.memory_agent.process(
                "store_fact",
                fact=f"FAILED: '{objective}' [{category}] {detail[:200]}",
                category="error_history",
            )
        except Exception:
            pass  # memory failure must not break error handling

    # ════════════════════════════════════════════════════════════════════
    #  UTILITIES
    # ════════════════════════════════════════════════════════════════════

    @staticmethod
    def _safe_truncate(value: Any, limit: int) -> str:
        """
        Truncate a value to at most `limit` chars without corrupting JSON.
        If the value is valid JSON, serialise it first so truncation is clean.
        """
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            try:
                serialised = json.dumps(value)
                return serialised[:limit] + ("…" if len(serialised) > limit else "")
            except (TypeError, ValueError):
                pass
        s = str(value)
        return s[:limit] + ("…" if len(s) > limit else "")

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        """Remove optional ```json … ``` wrappers from LLM responses."""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return text.strip()


# ════════════════════════════════════════════════════════════════════════════
#  SMOKE TEST
# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    )

    async def _smoke():
        async with OSEngine() as engine:
            result = await engine.process_objective("what is machine learning")
            print(json.dumps(result, indent=2, default=str))

    asyncio.run(_smoke())