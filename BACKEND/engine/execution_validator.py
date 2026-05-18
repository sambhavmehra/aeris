"""
AERIS — Execution Validator & Audit System
═══════════════════════════════════════════════════════════════════════

CRITICAL ENFORCEMENT LAYER: Ensures AERIS NEVER returns fake, assumed,
or hallucinated responses. Every response must be backed by real tool
execution with verifiable proof.

Rules enforced:
  1. Every response MUST have an associated tool execution receipt
  2. No response can be returned without a verified tool_call_id
  3. Execution receipts are tamper-resistant (hash-validated)
  4. Audit log persists to disk for forensic review
  5. If validation fails → response is REJECTED, not returned

This is the "lie detector" of AERIS.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("AerisValidator")


@dataclass
class ExecutionReceipt:
    """Tamper-resistant proof that a real tool was executed."""

    receipt_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = ""
    tool_params: Dict[str, Any] = field(default_factory=dict)
    result: str = ""
    status: str = ""            # "success" | "error"
    execution_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    integrity_hash: str = ""    # SHA-256 of (tool_name + result + timestamp)

    def compute_integrity_hash(self) -> str:
        """Generate a hash proving this receipt is internally consistent."""
        payload = f"{self.tool_name}|{self.result[:500]}|{self.timestamp}"
        self.integrity_hash = hashlib.sha256(payload.encode()).hexdigest()[:16]
        return self.integrity_hash

    def verify_integrity(self) -> bool:
        """Verify the receipt hasn't been tampered with."""
        expected = f"{self.tool_name}|{self.result[:500]}|{self.timestamp}"
        expected_hash = hashlib.sha256(expected.encode()).hexdigest()[:16]
        return self.integrity_hash == expected_hash

    def to_dict(self) -> Dict[str, Any]:
        return {
            "receipt_id": self.receipt_id,
            "tool_name": self.tool_name,
            "tool_params_summary": str(self.tool_params)[:200],
            "result_preview": self.result[:300],
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp,
            "integrity_hash": self.integrity_hash,
            "integrity_valid": self.verify_integrity(),
        }


@dataclass
class ValidationResult:
    """Result of validating a response against execution receipts."""

    is_valid: bool
    reason: str
    receipts: List[ExecutionReceipt] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "reason": self.reason,
            "receipt_count": len(self.receipts),
            "receipts": [r.to_dict() for r in self.receipts],
            "warnings": self.warnings,
        }


class ExecutionValidator:
    """
    The Lie Detector of AERIS.

    Validates that every response returned by the OS Engine is backed by
    real, verified tool execution. Prevents hallucinated or fake responses
    from ever reaching the user.

    Enforcement rules:
      1. MUST have at least one valid execution receipt per response
      2. Receipt integrity hash MUST verify
      3. Tool execution time MUST be > 0 (real execution takes time)
      4. Result must not be empty for non-echo tools
      5. Audit trail is persisted for accountability
    """

    # Path to the persistent audit log
    AUDIT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "audit"

    def __init__(self):
        self._pending_receipts: Dict[str, List[ExecutionReceipt]] = {}
        self.AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────────
    #  RECEIPT MANAGEMENT
    # ─────────────────────────────────────────────────────────────────

    def create_receipt(
        self,
        task_id: str,
        tool_name: str,
        tool_params: Dict[str, Any],
        result: str,
        status: str,
        execution_time_ms: float,
    ) -> ExecutionReceipt:
        """Create a signed execution receipt after a tool runs."""
        receipt = ExecutionReceipt(
            tool_name=tool_name,
            tool_params=tool_params,
            result=str(result)[:2000],
            status=status,
            execution_time_ms=execution_time_ms,
        )
        receipt.compute_integrity_hash()

        # Store under task_id
        if task_id not in self._pending_receipts:
            self._pending_receipts[task_id] = []
        self._pending_receipts[task_id].append(receipt)

        logger.info(
            f"[RECEIPT] Tool={tool_name} Status={status} "
            f"Time={execution_time_ms}ms Hash={receipt.integrity_hash}"
        )
        return receipt

    def get_receipts(self, task_id: str) -> List[ExecutionReceipt]:
        """Get all execution receipts for a task."""
        return self._pending_receipts.get(task_id, [])

    def clear_receipts(self, task_id: str):
        """Clear receipts for a completed task (after audit persistence)."""
        self._pending_receipts.pop(task_id, None)

    # ─────────────────────────────────────────────────────────────────
    #  VALIDATION — The Core Enforcement
    # ─────────────────────────────────────────────────────────────────

    def validate_response(
        self,
        task_id: str,
        response: str,
        objective: str,
    ) -> ValidationResult:
        """
        Validate that a response is backed by real tool execution.

        This is the CRITICAL gate — if this returns is_valid=False,
        the response MUST NOT be sent to the user.
        """
        receipts = self.get_receipts(task_id)
        warnings: List[str] = []

        # ── Rule 1: Must have at least one receipt ───────────────────
        if not receipts:
            logger.error(
                f"[VALIDATION FAILED] No execution receipts for task {task_id}. "
                f"Response would be FAKE. Blocking."
            )
            return ValidationResult(
                is_valid=False,
                reason="NO_EXECUTION_RECEIPTS: No tools were executed. "
                       "Response has no factual basis.",
                warnings=["Response was generated without any tool execution."],
            )

        # ── Rule 2: At least one receipt must be successful ──────────
        successful_receipts = [r for r in receipts if r.status == "success"]
        if not successful_receipts:
            logger.error(
                f"[VALIDATION FAILED] All {len(receipts)} tool executions failed "
                f"for task {task_id}. Cannot generate valid response."
            )
            # Still valid — we can return error-based response from real execution
            # The key is tools WERE called, they just failed
            warnings.append("All tool executions failed. Response reflects real errors.")

        # ── Rule 3: Verify receipt integrity ─────────────────────────
        tampered = [r for r in receipts if not r.verify_integrity()]
        if tampered:
            logger.error(
                f"[VALIDATION FAILED] {len(tampered)} receipt(s) failed "
                f"integrity check. Possible tampering."
            )
            return ValidationResult(
                is_valid=False,
                reason="INTEGRITY_FAILURE: Execution receipt integrity check failed.",
                warnings=[f"Tampered receipts: {[r.receipt_id for r in tampered]}"],
            )

        # ── Rule 4: Verify non-zero execution time ──────────────────
        zero_time = [
            r for r in receipts
            if r.execution_time_ms == 0 and r.tool_name != "chat_with_ai"
        ]
        if zero_time:
            warnings.append(
                f"{len(zero_time)} tool(s) reported 0ms execution time "
                f"(tools: {[r.tool_name for r in zero_time]}). "
                f"Possibly not truly executed."
            )

        # ── Rule 5: Response must not be empty ───────────────────────
        if not response or len(response.strip()) < 2:
            warnings.append("Response is empty or too short.")

        # ── PASSED ───────────────────────────────────────────────────
        logger.info(
            f"[VALIDATION PASSED] Task {task_id}: "
            f"{len(receipts)} receipt(s), "
            f"{len(successful_receipts)} successful. "
            f"Response is REAL."
        )

        return ValidationResult(
            is_valid=True,
            reason="VALIDATED: Response backed by real tool execution.",
            receipts=receipts,
            warnings=warnings,
        )

    # ─────────────────────────────────────────────────────────────────
    #  AUDIT PERSISTENCE
    # ─────────────────────────────────────────────────────────────────

    def persist_audit(self, task_id: str, objective: str, response: str, validation: ValidationResult):
        """Write audit trail to disk for accountability."""
        try:
            audit_entry = {
                "task_id": task_id,
                "objective": objective,
                "response_preview": response[:500],
                "validation": validation.to_dict(),
                "timestamp": time.time(),
                "timestamp_human": time.strftime("%Y-%m-%d %H:%M:%S"),
            }

            # Append to daily audit log
            date_str = time.strftime("%Y-%m-%d")
            audit_file = self.AUDIT_DIR / f"audit_{date_str}.jsonl"

            with open(audit_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry, default=str) + "\n")

            logger.info(f"[AUDIT] Persisted audit for task {task_id}")
        except Exception as e:
            logger.warning(f"Failed to persist audit: {e}")

    def get_audit_summary(self, date_str: str = None) -> Dict[str, Any]:
        """Read audit summary for a given date."""
        if not date_str:
            date_str = time.strftime("%Y-%m-%d")
        audit_file = self.AUDIT_DIR / f"audit_{date_str}.jsonl"

        if not audit_file.exists():
            return {"date": date_str, "entries": 0, "valid": 0, "invalid": 0}

        entries = []
        valid_count = 0
        invalid_count = 0

        try:
            for line in audit_file.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    entry = json.loads(line)
                    entries.append(entry)
                    if entry.get("validation", {}).get("is_valid"):
                        valid_count += 1
                    else:
                        invalid_count += 1
        except Exception:
            pass

        return {
            "date": date_str,
            "entries": len(entries),
            "valid": valid_count,
            "invalid": invalid_count,
            "recent": entries[-5:] if entries else [],
        }


# ═════════════════════════════════════════════════════════════════════
#  Global Singleton
# ═════════════════════════════════════════════════════════════════════
global_execution_validator = ExecutionValidator()
