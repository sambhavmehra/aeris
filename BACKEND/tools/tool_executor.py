"""
AERIS — Universal Tool Executor Service
═══════════════════════════════════════════════════════════════════════
The orchestrator that safely executes any tool in the Universal Registry.

Execution Flow:
  1. Lookup tool in UniversalToolRegistry
  2. Validate parameters against ToolInputSchema
  3. Check permissions via ToolPermissionSystem
  4. Resolve execution adapter via ToolAdapters
  5. Execute tool and catch errors
  6. Generate ExecutionReceipt via ExecutionValidator (Enforcement Layer)
  7. Return ToolExecutionResult

This replaces the old `global_tool_registry.execute()` method with a
robust, modular, and universally applicable pipeline.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from tools.tool_adapters import get_adapter_for
from tools.tool_interface import RiskLevel, ToolExecutionResult, ToolSource, UniversalToolDef
from tools.tool_permissions import get_permission_system
from tools.universal_registry import get_universal_registry
from engine.execution_validator import global_execution_validator

logger = logging.getLogger("AerisToolExecutor")


class ToolExecutorService:
    """
    Safely executes tools from the Universal Tool Registry, enforcing
    permissions, parameter schemas, and generating execution receipts.
    """

    def __init__(self):
        self.registry = get_universal_registry()
        self.permissions = get_permission_system()

    def execute(self, tool_name: str, task_id: str = "sys_manual", 
                step_id: str = "", parent_task_id: str = "", retry_count: int = 0,
                sandbox: bool = False, **kwargs) -> ToolExecutionResult:
        """
        Execute a tool by name, enforcing all safety and validation rules.
        Requires a task_id to generate a valid ExecutionReceipt.
        """
        start_time = time.perf_counter()

        # 1. Lookup Tool
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return self._fail(
                tool_name=tool_name,
                task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                error=f"Tool '{tool_name}' not found in registry.",
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )

        if not tool.is_enabled:
            return self._fail(
                tool_name=tool_name,
                task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                error=f"Tool '{tool_name}' is currently disabled.",
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )

        # 2. Consistency Guard (Schema Enforcement & Hallucination Cleanup)
        try:
            from intelligence.consistency_guard import get_consistency_guard
            is_valid, kwargs, schema_errors = get_consistency_guard().enforce_schema(tool_name, kwargs)
            if not is_valid:
                return self._fail(
                    tool_name=tool_name,
                    task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                    error=f"Schema violation for '{tool_name}': {schema_errors}",
                    elapsed_ms=(time.perf_counter() - start_time) * 1000,
                )
        except Exception as e:
            logger.warning(f"Consistency guard failed: {e}")

        # 3. Validate Parameters
        missing_params = [p for p in tool.required_params if p not in kwargs]
        if missing_params:
            return self._fail(
                tool_name=tool_name,
                task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                error=f"Missing required parameters for '{tool_name}': {missing_params}",
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )

        # 4. Safety Awareness (Contextual Risk Assessment)
        try:
            from intelligence.safety_awareness import get_safety_awareness
            safety = get_safety_awareness().evaluate_execution(tool_name, kwargs)
            if not safety.is_safe:
                req_str = " (Requires Approval)" if safety.requires_user_approval else ""
                return self._fail(
                    tool_name=tool_name,
                    task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                    error=f"SECURITY_BLOCKED: {safety.reason}{req_str}",
                    elapsed_ms=(time.perf_counter() - start_time) * 1000,
                )
        except Exception as e:
            logger.warning(f"Safety awareness failed: {e}")

        # 5. Permission Check
        decision = self.permissions.check(tool, kwargs)
        if not decision.allowed:
            if decision.requires_user_approval:
                error_msg = f"SECURITY_BLOCKED: {decision.reason} (Requires Approval)"
            else:
                error_msg = f"SECURITY_BLOCKED: {decision.reason}"
                
            return self._fail(
                tool_name=tool_name,
                task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                error=error_msg,
                elapsed_ms=(time.perf_counter() - start_time) * 1000,
            )

        # Dry run check (for safe evaluations)
        import os
        if getattr(self, "dry_run", False) or os.environ.get("AERIS_EVAL_DRY_RUN") == "true":
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            result = ToolExecutionResult(
                tool_name=tool.name,
                success=True,
                stdout=f"Dry-run execution of '{tool.name}' succeeded with args: {kwargs}",
                exit_code=0,
                execution_time_ms=round(elapsed_ms, 2),
                source=tool.source,
                step_id=step_id,
                parent_task_id=parent_task_id,
                retry_count=retry_count,
                tool_version=tool.version,
            )
            receipt = global_execution_validator.create_receipt(
                task_id=task_id,
                tool_name=tool.name,
                tool_params=kwargs,
                result=result.stdout,
                status="success",
                execution_time_ms=result.execution_time_ms,
            )
            result.receipt_id = receipt.receipt_id
            self._update_global_state(tool.name)
            return result

        # 6. Resolve Execution Adapter
        if tool.source == ToolSource.BUILTIN:
            # Execute Python function directly
            result = self._execute_builtin(tool, kwargs, task_id, start_time, step_id, parent_task_id, retry_count)
        else:
            # Use dynamic adapter
            # Enforce sandbox if risk level requires it (e.g., HIGH risk files)
            force_sandbox = sandbox or (tool.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL) and tool.source == ToolSource.FILE_BASED)
            adapter = get_adapter_for(tool, sandbox=force_sandbox)
            if not adapter:
                return self._fail(
                    tool_name=tool_name,
                    task_id=task_id, step_id=step_id, parent_task_id=parent_task_id, retry_count=retry_count,
                    error=f"No execution adapter found for source type: {tool.source}",
                    elapsed_ms=(time.perf_counter() - start_time) * 1000,
                )
            
            try:
                result = adapter.execute(tool, **kwargs)
                # Attach tracing information
                result.step_id = step_id
                result.parent_task_id = parent_task_id
                result.retry_count = retry_count
                result.tool_version = tool.version
            except Exception as e:
                result = ToolExecutionResult(
                    tool_name=tool.name,
                    success=False,
                    stderr=f"Adapter execution failed: {e}",
                    exit_code=-1,
                    error_type="adapter_error",
                    source=tool.source,
                    step_id=step_id,
                    parent_task_id=parent_task_id,
                    retry_count=retry_count,
                    tool_version=tool.version,
                )

        # 7. Generate Execution Receipt (Enforcement Layer)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        result.execution_time_ms = round(elapsed_ms, 2)
        
        status_str = "success" if result.success else "error"
        output_str = result.stderr if not result.success else str(result.stdout)
        
        receipt = global_execution_validator.create_receipt(
            task_id=task_id,
            tool_name=tool.name,
            tool_params=kwargs,
            result=output_str,
            status=status_str,
            execution_time_ms=result.execution_time_ms,
        )
        
        result.receipt_id = receipt.receipt_id
        
        # 6. Global State Update & Health Tracking
        self._update_global_state(tool.name)
        try:
            from tools.tool_health import get_health_tracker
            get_health_tracker().record_execution(
                tool.name, result.success, result.execution_time_ms, result.error_type
            )
        except Exception as e:
            logger.warning(f"Could not record health metrics: {e}")
            
        # 9. Feedback Loop (Learning)
        try:
            from intelligence.feedback_loop import get_feedback_loop
            # Try to infer objective from current task
            objective = ""
            prev_tool = None
            try:
                from engine.state_manager import global_state_manager
                task = global_state_manager.get_current_task()
                if task:
                    objective = task.description
                    if task.current_step_index > 0 and len(task.steps) >= task.current_step_index:
                        prev_tool = task.steps[task.current_step_index - 1].tool_name
            except Exception:
                pass

            get_feedback_loop().record(
                tool_name=tool.name,
                success=result.success,
                execution_time_ms=result.execution_time_ms,
                error_type=result.error_type,
                error_message=result.stderr if not result.success else None,
                objective=objective,
                previous_tool=prev_tool,
                retry_count=retry_count
            )
        except Exception as e:
            logger.warning(f"Feedback loop recording failed: {e}")

        return result

    def _execute_builtin(self, tool: UniversalToolDef, kwargs: Dict[str, Any], task_id: str, start_time: float,
                         step_id: str, parent_task_id: str, retry_count: int) -> ToolExecutionResult:
        """Safely execute a hardcoded builtin Python tool."""
        try:
            if not tool.func:
                raise ValueError("Builtin tool has no function attached.")
            
            import asyncio
            import inspect

            output = tool.func(**kwargs)

            # Handle async tool functions (e.g. smart_shell_generate)
            if inspect.isawaitable(output):
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    # We're inside an already-running event loop — schedule as a task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        output = pool.submit(asyncio.run, output).result(timeout=tool.timeout or 60)
                else:
                    output = asyncio.run(output)

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            
            return ToolExecutionResult(
                tool_name=tool.name,
                success=True,
                stdout=str(output),
                exit_code=0,
                execution_time_ms=round(elapsed_ms, 2),
                source=ToolSource.BUILTIN,
                step_id=step_id,
                parent_task_id=parent_task_id,
                retry_count=retry_count,
                tool_version=tool.version,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return ToolExecutionResult(
                tool_name=tool.name,
                success=False,
                stderr=str(e),
                exit_code=-1,
                error_type="builtin_execution_error",
                execution_time_ms=round(elapsed_ms, 2),
                source=ToolSource.BUILTIN,
                step_id=step_id,
                parent_task_id=parent_task_id,
                retry_count=retry_count,
                tool_version=tool.version,
            )

    def _fail(self, tool_name: str, task_id: str, step_id: str, parent_task_id: str, retry_count: int,
              error: str, elapsed_ms: float) -> ToolExecutionResult:
        """Helper to return a failure result and log a failure receipt."""
        # Generate receipt to prove we tried and failed/blocked
        receipt = global_execution_validator.create_receipt(
            task_id=task_id,
            tool_name=tool_name,
            tool_params={},
            result=f"FAILED_BEFORE_EXECUTION: {error}",
            status="error",
            execution_time_ms=round(elapsed_ms, 2),
        )
        return ToolExecutionResult(
            tool_name=tool_name,
            success=False,
            stderr=error,
            exit_code=-1,
            error_type="pre_execution_failure",
            execution_time_ms=round(elapsed_ms, 2),
            receipt_id=receipt.receipt_id,
            step_id=step_id,
            parent_task_id=parent_task_id,
            retry_count=retry_count,
        )

    def _update_global_state(self, name: str):
        """Update the UI state string so the user knows what AERIS is doing."""
        action_str = "Executing tool..."
        if "search" in name: action_str = "Searching..."
        elif "analyze" in name: action_str = "Analyzing data..."
        elif "read" in name: action_str = "Reading file..."
        elif "close" in name: action_str = "Closing apps..."
        elif "smart_shell" in name: action_str = "Sir, shell command generate kar raha hoon..."
        elif "generate" in name:
            if "image" in name: action_str = "Generating image..."
            elif "video" in name: action_str = "Generating video..."
            else: action_str = "Writing code..."
        elif "write" in name or "edit" in name: action_str = "Writing code..."

        try:
            from engine.state_manager import global_state_manager
            global_state_manager.set_global_action(action_str)
        except Exception:
            pass


# ── Global Singleton ─────────────────────────────────────────────────
_executor_service: Optional[ToolExecutorService] = None


def get_executor_service() -> ToolExecutorService:
    global _executor_service
    if _executor_service is None:
        _executor_service = ToolExecutorService()
    return _executor_service
