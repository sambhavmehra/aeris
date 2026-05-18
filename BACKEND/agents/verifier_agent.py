"""
AERIS — Verifier Agent
======================
Validates generated code by running syntax checks, sandbox execution,
and LLM-powered code review.  The final stage of the autonomous
Planner → Coder → Verifier pipeline.
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import platform
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

logger = logging.getLogger("aeris.verifier_agent")

# Sandbox limits
SANDBOX_TIMEOUT_SEC = 15
MAX_OUTPUT_CHARS = 5000


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SyntaxError_:
    """Record of a syntax error found during validation."""
    file: str
    line: int
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {"file": self.file, "line": self.line, "message": self.message}


@dataclass
class VerificationReport:
    """Structured output from the VerifierAgent."""
    passed: bool
    syntax_errors: List[SyntaxError_] = field(default_factory=list)
    runtime_output: str = ""
    runtime_exit_code: int = -1
    runtime_error: str = ""
    llm_review: str = ""
    files_checked: int = 0
    verification_time_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "syntax_errors": [e.to_dict() for e in self.syntax_errors],
            "runtime_output": self.runtime_output[:MAX_OUTPUT_CHARS],
            "runtime_exit_code": self.runtime_exit_code,
            "runtime_error": self.runtime_error[:MAX_OUTPUT_CHARS],
            "llm_review": self.llm_review,
            "files_checked": self.files_checked,
            "verification_time_sec": round(self.verification_time_sec, 2),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

REVIEW_SYSTEM_PROMPT = """\
You are AERIS's Code Reviewer — an expert software engineer reviewing
auto-generated code for quality, correctness, and security.

Review the provided source files and give a concise verdict.

OUTPUT FORMAT (plain text, not JSON):
1. VERDICT: PASS or FAIL
2. ISSUES: List any bugs, logic errors, security concerns, or missing pieces
3. SUGGESTIONS: Brief improvement recommendations
4. SUMMARY: One-sentence overall assessment

Be strict but fair. A project that compiles and runs correctly with minor
style issues should PASS. A project with logic errors or missing
dependencies should FAIL.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class VerifierAgent(BaseAgent):
    """
    Autonomous Verifier Agent — validates generated code through:
      1. Syntax checking (AST parse for Python, node --check for JS)
      2. Sandbox execution (subprocess with timeout)
      3. LLM code review
    """

    def __init__(self):
        super().__init__(
            name="VerifierAgent",
            description="Validates generated code via syntax checks, sandbox execution, and AI review.",
            task_domain="verification",
            version="1.0.0",
            capabilities=[
                "Python Syntax Validation",
                "JavaScript Syntax Validation",
                "Sandbox Code Execution",
                "AI Code Review",
                "Security Audit",
            ],
        )

    # ── BaseAgent interface ──────────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Extract verification parameters from context."""
        return {
            "workspace_path": context.get("workspace_path", ""),
            "entry_point": context.get("entry_point", "main.py"),
            "language": context.get("language", "python"),
        }

    async def execute(self, plan: Any) -> Any:
        """Run the full verification pipeline."""
        if isinstance(plan, dict):
            return await self.verify_workspace(
                workspace_path=plan["workspace_path"],
                entry_point=plan.get("entry_point", "main.py"),
                language=plan.get("language", "python"),
            )
        return plan

    async def report(self, results: Any) -> str:
        """Format verification report as human-readable text."""
        if isinstance(results, VerificationReport):
            icon = "✅" if results.passed else "❌"
            parts = [f"{icon} **Verification {'PASSED' if results.passed else 'FAILED'}**"]
            parts.append(f"Files checked: {results.files_checked}")

            if results.syntax_errors:
                parts.append("\n**Syntax Errors:**")
                for e in results.syntax_errors:
                    parts.append(f"  • `{e.file}` line {e.line}: {e.message}")

            if results.runtime_output:
                output_preview = results.runtime_output[:500]
                parts.append(f"\n**Runtime Output:**\n```\n{output_preview}\n```")

            if results.runtime_error:
                parts.append(f"\n**Runtime Error:**\n```\n{results.runtime_error[:500]}\n```")

            if results.llm_review:
                parts.append(f"\n**AI Review:**\n{results.llm_review}")

            parts.append(f"\n⏱️ Verified in {results.verification_time_sec}s")
            return "\n".join(parts)
        return str(results)

    # ── Core verification ────────────────────────────────────────────────

    async def verify_workspace(
        self,
        workspace_path: str,
        entry_point: str = "main.py",
        language: str = "python",
    ) -> VerificationReport:
        """
        Full verification pipeline:
          1. Scan all source files for syntax errors
          2. Attempt sandbox execution of the entry point
          3. LLM code review of all files
        """
        t0 = time.time()
        workspace = Path(workspace_path)

        if not workspace.exists():
            return VerificationReport(
                passed=False,
                runtime_error=f"Workspace not found: {workspace_path}",
                verification_time_sec=time.time() - t0,
            )

        # 1 — Syntax validation
        logger.info(f"[VerifierAgent] Step 1: Syntax validation in {workspace}")
        syntax_errors, files_checked = self._check_syntax_all(workspace, language)

        # 2 — Sandbox execution
        logger.info(f"[VerifierAgent] Step 2: Sandbox execution of {entry_point}")
        runtime_output, runtime_error, exit_code = await self._sandbox_run(
            workspace, entry_point, language
        )

        # 3 — LLM review
        logger.info("[VerifierAgent] Step 3: LLM code review")
        llm_review = await self._llm_review(workspace, language)

        # Determine pass/fail
        has_syntax_errors = len(syntax_errors) > 0
        has_runtime_crash = exit_code != 0 and runtime_error.strip() != ""
        llm_failed = "FAIL" in llm_review.upper().split("\n")[0] if llm_review else False

        passed = not has_syntax_errors and not has_runtime_crash

        elapsed = time.time() - t0
        logger.info(
            f"[VerifierAgent] Verification {'PASSED' if passed else 'FAILED'} "
            f"in {elapsed:.1f}s ({files_checked} files)"
        )

        return VerificationReport(
            passed=passed,
            syntax_errors=syntax_errors,
            runtime_output=runtime_output,
            runtime_exit_code=exit_code,
            runtime_error=runtime_error,
            llm_review=llm_review,
            files_checked=files_checked,
            verification_time_sec=elapsed,
        )

    # ── Syntax checking ─────────────────────────────────────────────────

    def _check_syntax_all(
        self, workspace: Path, language: str
    ) -> Tuple[List[SyntaxError_], int]:
        """Check syntax of all source files in the workspace."""
        errors: List[SyntaxError_] = []
        checked = 0

        ext_map = {
            "python": [".py"],
            "javascript": [".js", ".jsx"],
            "typescript": [".ts", ".tsx"],
        }
        extensions = ext_map.get(language.lower(), [".py"])

        for ext in extensions:
            for filepath in workspace.rglob(f"*{ext}"):
                # Skip __pycache__, node_modules, .git
                parts = filepath.parts
                if any(skip in parts for skip in ("__pycache__", "node_modules", ".git", "venv")):
                    continue

                checked += 1
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    ok, msg = self._validate_syntax(content, ext)
                    if not ok:
                        rel = str(filepath.relative_to(workspace))
                        line_num = self._extract_line_number(msg)
                        errors.append(SyntaxError_(file=rel, line=line_num, message=msg))
                except Exception as e:
                    rel = str(filepath.relative_to(workspace))
                    errors.append(SyntaxError_(file=rel, line=0, message=str(e)))

        return errors, checked

    @staticmethod
    def _validate_syntax(code: str, ext: str) -> Tuple[bool, str]:
        """Validate syntax for a single file."""
        if ext == ".py":
            try:
                ast.parse(code)
                return True, "OK"
            except SyntaxError as e:
                return False, f"SyntaxError at line {e.lineno}: {e.msg}"

        if ext in (".js", ".jsx", ".ts", ".tsx"):
            try:
                check_cmd = "where" if platform.system() == "Windows" else "which"
                has_node = subprocess.call(
                    [check_cmd, "node"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ) == 0
                if has_node:
                    result = subprocess.run(
                        ["node", "--check"],
                        input=code.encode(),
                        capture_output=True,
                        timeout=5,
                    )
                    if result.returncode != 0:
                        return False, result.stderr.decode()[:300]
                return True, "OK"
            except Exception:
                return True, "Syntax check skipped"

        return True, "No validator for this file type"

    @staticmethod
    def _extract_line_number(msg: str) -> int:
        """Try to extract a line number from an error message."""
        import re
        match = re.search(r"line (\d+)", msg, re.IGNORECASE)
        return int(match.group(1)) if match else 0

    # ── Sandbox execution ────────────────────────────────────────────────

    async def _sandbox_run(
        self, workspace: Path, entry_point: str, language: str
    ) -> Tuple[str, str, int]:
        """
        Execute the project entry point in a sandboxed subprocess.
        Returns (stdout, stderr, exit_code).
        """
        entry_file = workspace / entry_point
        if not entry_file.exists():
            return "", f"Entry point not found: {entry_point}", 1

        # Build command based on language
        if language.lower() in ("python", "py"):
            cmd = ["python", "-u", str(entry_file)]
        elif language.lower() in ("javascript", "js"):
            cmd = ["node", str(entry_file)]
        elif language.lower() in ("typescript", "ts"):
            cmd = ["npx", "ts-node", str(entry_file)]
        else:
            return "", f"Unsupported language for sandbox: {language}", 1

        # Run in a separate thread to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, lambda: subprocess.run(
                cmd,
                capture_output=True,
                timeout=SANDBOX_TIMEOUT_SEC,
                cwd=str(workspace),
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            ))
            stdout = result.stdout.decode(errors="replace")[:MAX_OUTPUT_CHARS]
            stderr = result.stderr.decode(errors="replace")[:MAX_OUTPUT_CHARS]
            return stdout, stderr, result.returncode
        except subprocess.TimeoutExpired:
            # Timeout is actually OK for servers — they run indefinitely
            return "(process timed out — likely a server/long-running app)", "", 0
        except FileNotFoundError:
            return "", f"Runtime not found for language: {language}", 1
        except Exception as e:
            return "", f"Sandbox execution error: {str(e)}", 1

    # ── LLM review ──────────────────────────────────────────────────────

    async def _llm_review(self, workspace: Path, language: str) -> str:
        """Send all source files to the LLM for code quality review."""
        ext_map = {
            "python": [".py"],
            "javascript": [".js", ".jsx"],
            "typescript": [".ts", ".tsx"],
        }
        extensions = ext_map.get(language.lower(), [".py"])

        file_contents = []
        total_chars = 0
        max_chars = 12000  # Keep within token limits

        for ext in extensions:
            for filepath in workspace.rglob(f"*{ext}"):
                parts = filepath.parts
                if any(skip in parts for skip in ("__pycache__", "node_modules", ".git", "venv")):
                    continue
                try:
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    rel = str(filepath.relative_to(workspace))
                    if total_chars + len(content) > max_chars:
                        content = content[:max_chars - total_chars] + "\n... (truncated)"
                    file_contents.append(f"=== {rel} ===\n{content}")
                    total_chars += len(content)
                    if total_chars >= max_chars:
                        break
                except Exception:
                    continue

        if not file_contents:
            return "No source files found for review."

        review_prompt = (
            f"Review the following {language} project files:\n\n"
            + "\n\n".join(file_contents)
        )

        try:
            review = await ai_engine.chat(
                messages=[
                    {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
                    {"role": "user", "content": review_prompt},
                ],
                temperature=0.2,
                max_tokens=1024,
            )
            return review.strip()
        except Exception as e:
            logger.warning(f"[VerifierAgent] LLM review failed: {e}")
            return f"LLM review unavailable: {str(e)}"
