"""
AERIS AI OS — llama-3.3-70b-versatile (Sub-Agent) [ADVANCED]
====================================================
Specialised agent for code generation, analysis, refactoring, and debugging.

Upgrades over v1:
  • Task auto-classification (generate / analyse / debug / refactor / test / explain)
  • Language-aware sub-prompts (Python, JS/TS, Go, Rust, Java, SQL, Shell, …)
  • Retry with exponential back-off + jitter on transient failures
  • Dynamic token budgeting based on task complexity
  • Unified diff output for refactor tasks (preserves originals)
  • Optional post-generation syntax validation (ast / subprocess)
  • Async-native execution with sync shim for backward compatibility
  • Per-call telemetry (latency, estimated token usage, success rate)
  • Typed dataclasses for all inputs and outputs — no raw dicts leaking out
  • Conversation-history aware (multi-turn follow-ups)
  • In-memory LRU result cache keyed on (objective_hash, context_hash)
  • Pipeline / chaining helpers: pipe() chains two agents sequentially
  • Security hint injection for sensitive operations
  • Structured error taxonomy with retry hints
"""

from __future__ import annotations

import ast
import asyncio
import difflib
import functools
import hashlib
import json
import logging
import random
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple, Union

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

class SharedContextBuffer:
    def __init__(self):
        self._data = []
    def post(self, sender: str, content: Any, message_type: str = "result", task: str = ""):
        self._data.append({"sender": sender, "content": content, "type": message_type, "task": task})
    def get_latest_result(self, sender: str) -> Any:
        for item in reversed(self._data):
            if item["sender"] == sender and item["type"] == "result":
                return item["content"]
        return None

logger = logging.getLogger("AERISCodingAgent")


# ─────────────────────────────────────────────────────────────────────────────
# Enumerations & Constants
# ─────────────────────────────────────────────────────────────────────────────

class TaskKind(Enum):
    GENERATE  = auto()   # Write new code from scratch
    ANALYSE   = auto()   # Review existing code
    DEBUG     = auto()   # Fix a traceback / error
    REFACTOR  = auto()   # Improve structure without changing behaviour
    TEST      = auto()   # Write unit/integration tests
    EXPLAIN   = auto()   # Plain-English explanation of code
    DOCUMENT  = auto()   # Docstrings, README snippets
    SECURITY  = auto()   # Security audit / hardening advice
    UNKNOWN   = auto()   # Fall-through — use general prompt


# Keywords used to auto-detect task kind from the objective string
_TASK_SIGNALS: Dict[TaskKind, List[str]] = {
    TaskKind.GENERATE:  ["generate", "create", "write", "build", "implement", "scaffold"],
    TaskKind.ANALYSE:   ["analyse", "analyze", "review", "evaluate", "assess", "inspect"],
    TaskKind.DEBUG:     ["debug", "fix", "traceback", "error", "exception", "broken"],
    TaskKind.REFACTOR:  ["refactor", "clean", "restructure", "improve", "optimise", "optimize"],
    TaskKind.TEST:      ["test", "unit test", "pytest", "jest", "coverage", "mock"],
    TaskKind.EXPLAIN:   ["explain", "what does", "how does", "describe", "summarise"],
    TaskKind.DOCUMENT:  ["document", "docstring", "readme", "comments", "annotate"],
    TaskKind.SECURITY:  ["security", "vulnerability", "cve", "inject", "xss", "audit"],
}

# Supported language identifiers and their display names
_LANGUAGES: Dict[str, str] = {
    "python": "Python", "py": "Python",
    "javascript": "JavaScript", "js": "JavaScript",
    "typescript": "TypeScript", "ts": "TypeScript",
    "go": "Go", "golang": "Go",
    "rust": "Rust", "rs": "Rust",
    "java": "Java",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "c": "C", "cpp": "C++", "c++": "C++",
    "csharp": "C#", "c#": "C#",
    "sql": "SQL",
    "bash": "Bash", "shell": "Bash", "sh": "Bash",
    "ruby": "Ruby", "rb": "Ruby",
    "php": "PHP",
    "html": "HTML", "css": "CSS",
}

# Approximate token budgets per task kind
_TOKEN_BUDGET: Dict[TaskKind, int] = {
    TaskKind.GENERATE:  4096,
    TaskKind.ANALYSE:   2048,
    TaskKind.DEBUG:     2048,
    TaskKind.REFACTOR:  4096,
    TaskKind.TEST:      3072,
    TaskKind.EXPLAIN:   1024,
    TaskKind.DOCUMENT:  2048,
    TaskKind.SECURITY:  2048,
    TaskKind.UNKNOWN:   2048,
}

# Max retry attempts on transient LLM failures
MAX_RETRIES    = 3
BASE_DELAY_SEC = 1.0   # first back-off delay
MAX_DELAY_SEC  = 16.0  # cap
CACHE_SIZE     = 128   # LRU slots


# ─────────────────────────────────────────────────────────────────────────────
# Typed I/O Dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CodeFile:
    """A single generated or modified source file."""
    path: str
    content: str
    language: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"path": self.path, "content": self.content, "language": self.language}


@dataclass
class CodingResult:
    """Structured output from any CodingAgent operation."""
    status: str                          # "success" | "error"
    task_kind: TaskKind = TaskKind.UNKNOWN
    language: str = ""
    analysis: str = ""                   # Human-readable findings
    suggestion: str = ""                 # High-level suggestion
    code: str = ""                       # Inline code snippet (if any)
    diff: str = ""                       # Unified diff (refactor tasks)
    files: List[CodeFile] = field(default_factory=list)
    tests: str = ""                      # Generated test code
    security_notes: List[str] = field(default_factory=list)
    error: str = ""                      # Set when status == "error"
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status":         self.status,
            "task_kind":      self.task_kind.name,
            "language":       self.language,
            "analysis":       self.analysis,
            "suggestion":     self.suggestion,
            "code":           self.code,
            "diff":           self.diff,
            "files":          [f.to_dict() for f in self.files],
            "tests":          self.tests,
            "security_notes": self.security_notes,
            "error":          self.error,
            "metrics":        self.metrics,
        }


@dataclass
class CodingRequest:
    """Everything needed to describe a coding task."""
    objective: str
    language: str = "python"
    original_code: str = ""              # For debug / refactor / analyse
    error_trace: str = ""                # For debug tasks
    conversation_history: List[Dict] = field(default_factory=list)  # Multi-turn
    task_kind: Optional[TaskKind] = None # Override auto-detection
    context: Optional[SharedContextBuffer] = None
    allow_execution: bool = False        # Run the generated code in sandbox


# ─────────────────────────────────────────────────────────────────────────────
# Telemetry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _Metrics:
    calls: int = 0
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    retries: int = 0

    @property
    def success_rate(self) -> float:
        return self.successes / self.calls if self.calls else 0.0

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / self.calls if self.calls else 0.0

    def snapshot(self) -> Dict[str, Any]:
        return {
            "calls":          self.calls,
            "successes":      self.successes,
            "failures":       self.failures,
            "retries":        self.retries,
            "success_rate":   round(self.success_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


# ─────────────────────────────────────────────────────────────────────────────
# System Prompt Builder
# ─────────────────────────────────────────────────────────────────────────────

_BASE_SYSTEM = """\
You are AERIS's llama-3.3-70b-versatile — a specialised AI programmer embedded in a
multi-agent orchestration system.

CORE RULES (non-negotiable):
1. Output ONLY valid JSON matching the schema below — no prose outside JSON.
2. Every code block must be COMPLETE and EXECUTABLE as-is.
3. Include ALL imports, dependencies, and type hints.
4. Use idiomatic style for the target language.
5. Apply proper error handling and input validation.
6. If context from other agents is provided, actively incorporate it.
7. Do NOT truncate code with comments like "# ... rest of function ...".

OUTPUT SCHEMA (always return exactly this JSON shape):
{{
  "analysis":       "<string — findings, complexity notes, root cause>",
  "suggestion":     "<string — high-level recommendation>",
  "code":           "<string — inline snippet or empty string>",
  "diff":           "<string — unified diff or empty string>",
  "files":          [{{"path": "<filename>", "content": "<full source>", "language": "<lang>"}}],
  "tests":          "<string — test code or empty string>",
  "security_notes": ["<issue>", ...]
}}
"""

_LANG_HINTS: Dict[str, str] = {
    "Python": (
        "Use type hints, dataclasses, and pathlib. "
        "Prefer f-strings. Raise specific exceptions. "
        "Follow PEP 8. Add Google-style docstrings."
    ),
    "JavaScript": (
        "Use ESM imports. Prefer const/let over var. "
        "Use async/await over raw Promises. "
        "Add JSDoc comments."
    ),
    "TypeScript": (
        "Use strict TypeScript. Define interfaces and enums. "
        "Avoid `any`. Use utility types (Partial, Required, etc.)."
    ),
    "Go": (
        "Follow effective-Go idioms. Return (value, error) tuples. "
        "Use context.Context for cancellation. Group imports."
    ),
    "Rust": (
        "Use Result<T, E> and ? operator. Avoid unwrap in library code. "
        "Derive Debug, Clone where applicable. Use lifetimes explicitly."
    ),
    "SQL": (
        "Write ANSI-compliant SQL unless a specific dialect is specified. "
        "Use CTEs instead of nested subqueries. Add index hints as comments."
    ),
    "Bash": (
        "Start with #!/usr/bin/env bash. Set -euo pipefail. "
        "Quote all variables. Use [[ ]] for conditionals."
    ),
}

_TASK_ADDENDA: Dict[TaskKind, str] = {
    TaskKind.GENERATE: (
        "Generate complete, production-ready code. "
        "Output one file per logical module in the `files` array."
    ),
    TaskKind.ANALYSE: (
        "Identify bugs, code smells, performance bottlenecks, and "
        "anti-patterns. Rank issues by severity (critical/major/minor). "
        "Put detailed findings in `analysis`."
    ),
    TaskKind.DEBUG: (
        "Identify the root cause from the traceback + code. "
        "Put the corrected code in `files` or `code`. "
        "Explain the fix in `analysis`."
    ),
    TaskKind.REFACTOR: (
        "Return a unified diff in `diff` AND the full refactored files in "
        "`files`. Preserve all public APIs and behaviour."
    ),
    TaskKind.TEST: (
        "Generate comprehensive tests covering happy path, edge cases, and "
        "failure modes. Use the idiomatic test framework for the language. "
        "Put tests in `tests`."
    ),
    TaskKind.EXPLAIN: (
        "Explain what the code does in plain English. "
        "Put the explanation in `analysis`. "
        "Highlight non-obvious or tricky parts."
    ),
    TaskKind.DOCUMENT: (
        "Add docstrings/JSDoc/rustdoc to all public functions and classes. "
        "Return the documented code in `files`."
    ),
    TaskKind.SECURITY: (
        "Audit for OWASP Top-10, injection, insecure defaults, and "
        "sensitive data exposure. List each finding in `security_notes` "
        "with severity and remediation. Provide hardened code in `files`."
    ),
}


def _build_system_prompt(task_kind: TaskKind, language: str) -> str:
    lang_display = _LANGUAGES.get(language.lower(), language.capitalize())
    lang_hint = _LANG_HINTS.get(lang_display, f"Write idiomatic {lang_display}.")
    task_addendum = _TASK_ADDENDA.get(task_kind, "")
    return (
        _BASE_SYSTEM
        + f"\nTARGET LANGUAGE: {lang_display}\nLANGUAGE STYLE RULES: {lang_hint}"
        + (f"\nTASK-SPECIFIC INSTRUCTIONS: {task_addendum}" if task_addendum else "")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Simple LRU cache (Python 3.8-compatible, thread-safe enough for agent use)
# ─────────────────────────────────────────────────────────────────────────────

class _LRUCache:
    def __init__(self, max_size: int = CACHE_SIZE):
        self._cache: Dict[str, Any] = {}
        self._order: List[str] = []
        self._max = max_size

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            self._order.remove(key)
            self._order.append(key)
            return self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._order.remove(key)
        elif len(self._order) >= self._max:
            evict = self._order.pop(0)
            del self._cache[evict]
        self._cache[key] = value
        self._order.append(key)

    def invalidate(self, key: str) -> None:
        if key in self._cache:
            self._order.remove(key)
            del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()
        self._order.clear()

    def __len__(self) -> int:
        return len(self._cache)


# ─────────────────────────────────────────────────────────────────────────────
# Syntax Validator
# ─────────────────────────────────────────────────────────────────────────────

class ValidationError(Exception):
    """Raised when generated code fails syntax validation."""


def _validate_syntax(code: str, language: str) -> Tuple[bool, str]:
    """
    Validate code syntax for supported languages.
    Returns (ok: bool, message: str).
    """
    lang = language.lower()

    if lang in ("python", "py"):
        try:
            ast.parse(code)
            return True, "Python AST parse: OK"
        except SyntaxError as exc:
            return False, f"Python SyntaxError at line {exc.lineno}: {exc.msg}"

    if lang in ("javascript", "js", "typescript", "ts"):
        # Requires node on PATH — graceful skip if unavailable
        if _command_available("node"):
            try:
                result = subprocess.run(
                    ["node", "--input-type=module", "--check"],
                    input=code.encode(),
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return True, "Node.js syntax check: OK"
                return False, result.stderr.decode()[:300]
            except Exception:
                pass
        return True, "JS/TS syntax check skipped (node not available)"

    if lang in ("bash", "shell", "sh"):
        if _command_available("bash"):
            try:
                result = subprocess.run(
                    ["bash", "-n"],
                    input=code.encode(),
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return True, "Bash syntax check: OK"
                return False, result.stderr.decode()[:300]
            except Exception:
                pass
        return True, "Bash syntax check skipped"

    # No validator for this language — skip silently
    return True, f"No validator available for '{language}'"


def _command_available(cmd: str) -> bool:
    import platform
    check_cmd = "where" if platform.system() == "Windows" else "which"
    return subprocess.call(
        [check_cmd, cmd],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Diff Generator
# ─────────────────────────────────────────────────────────────────────────────

def _unified_diff(original: str, refactored: str,
                  filename: str = "code") -> str:
    """Generate a human-readable unified diff between two code strings."""
    orig_lines = original.splitlines(keepends=True)
    refact_lines = refactored.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        orig_lines, refact_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
    ))
    return "".join(diff_lines) if diff_lines else "(no changes)"


# ─────────────────────────────────────────────────────────────────────────────
# Task Classifier
# ─────────────────────────────────────────────────────────────────────────────

def _classify_task(objective: str) -> TaskKind:
    """
    Infer the TaskKind from the objective string using keyword matching.
    Precedence follows the order of _TASK_SIGNALS.
    """
    lower = objective.lower()
    for kind, keywords in _TASK_SIGNALS.items():
        if any(kw in lower for kw in keywords):
            return kind
    return TaskKind.UNKNOWN


# ─────────────────────────────────────────────────────────────────────────────
# Cache Key
# ─────────────────────────────────────────────────────────────────────────────

def _cache_key(request: CodingRequest) -> str:
    payload = json.dumps({
        "objective": request.objective,
        "language":  request.language,
        "original":  request.original_code[:200],
        "trace":     request.error_trace[:200],
    }, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


# ─────────────────────────────────────────────────────────────────────────────
# Advanced llama-3.3-70b-versatile
# ─────────────────────────────────────────────────────────────────────────────

class CodingAgent(BaseAgent):
    """
    Advanced sub-agent for code generation, analysis, debugging, and more.

    Key improvements over v1:
      - Auto-classifies tasks; selects system prompt accordingly
      - Retries with exponential back-off + jitter
      - LRU cache avoids redundant LLM calls
      - Generates unified diffs for refactor tasks
      - Validates Python/JS/Bash syntax post-generation
      - Tracks per-instance telemetry
      - Fully async with sync shim
      - Typed I/O via CodingRequest / CodingResult
    """

    def __init__(self, memory_agent=None, enable_cache: bool = True,
                 enable_validation: bool = True):
        super().__init__(name="CodingAgent", description="Specialised agent for code generation, analysis, refactoring, and debugging.",
                         task_domain="code", version="2.0.0",
                         capabilities=[
                             "Code Generation (Python, JS, Go, Rust, Java, etc.)",
                             "Code Analysis and Review",
                             "Debugging and Error Fixing",
                             "Refactoring with Unified Diffs",
                             "Unit Test Generation",
                             "Code Explanation",
                             "Documentation Generation",
                             "Security Audit and Hardening",
                             "Website Scaffolding",
                             "Mermaid Diagram Generation",
                         ])
        self._memory_agent = memory_agent
        self._cache = _LRUCache() if enable_cache else None
        self._enable_validation = enable_validation
        self._metrics = _Metrics()

    def log(self, message: str, level: str = "INFO"):
        lvl = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(lvl, message)

    # ── BaseAgent Abstract Method Implementations ────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Analyze the user message and build a CodingRequest."""
        language = context.get("language", "python") if context else "python"
        task_kind = _classify_task(message)
        req = CodingRequest(
            objective=message,
            language=language,
            task_kind=task_kind,
            original_code=context.get("code", "") if context else "",
            error_trace=context.get("error_trace", "") if context else "",
        )
        return req

    async def execute(self, plan: Any) -> Any:
        """Execute the coding plan via the async pipeline."""
        if isinstance(plan, CodingRequest):
            return await self.process_async(plan)
        # Fallback: treat plan as a raw objective string
        req = CodingRequest(objective=str(plan))
        return await self.process_async(req)

    async def report(self, results: Any) -> str:
        """Format CodingResult into a human-readable response."""
        if isinstance(results, CodingResult):
            parts = []
            if results.analysis:
                parts.append(results.analysis)
            if results.suggestion:
                parts.append(f"**Suggestion:** {results.suggestion}")
            if results.code:
                parts.append(f"```\n{results.code}\n```")
            if results.files:
                for f in results.files:
                    parts.append(f"**{f.path}**\n```{f.language}\n{f.content}\n```")
            if results.diff:
                parts.append(f"**Diff:**\n```diff\n{results.diff}\n```")
            if results.tests:
                parts.append(f"**Tests:**\n```\n{results.tests}\n```")
            if results.security_notes:
                notes = "\n".join(f"  • {n}" for n in results.security_notes)
                parts.append(f"**Security Notes:**\n{notes}")
            if results.error:
                parts.append(f"⚠️ **Error:** {results.error}")
            return "\n\n".join(parts) if parts else "Code task completed."
        return str(results)

    # ── Public Sync API (backward-compatible) ────────────────────────────────

    def process(self, objective: str,
                context: Optional[SharedContextBuffer] = None,
                language: str = "python",
                **kwargs) -> Dict[str, Any]:
        """Sync wrapper — delegates to async run."""
        req = CodingRequest(objective=objective, language=language, context=context)
        result = asyncio.run(self.process_async(req))
        return result.to_dict()

    def generate_code(self, request: str, language: str = "python",
                      context: Optional[SharedContextBuffer] = None) -> Dict[str, Any]:
        req = CodingRequest(
            objective=f"Generate {language} code: {request}",
            language=language,
            task_kind=TaskKind.GENERATE,
            context=context,
        )
        return asyncio.run(self.process_async(req)).to_dict()

    def analyze_code(self, code: str, language: str = "python",
                     context: Optional[SharedContextBuffer] = None) -> Dict[str, Any]:
        req = CodingRequest(
            objective="Analyse this code for bugs, performance, and improvements.",
            language=language,
            original_code=code,
            task_kind=TaskKind.ANALYSE,
            context=context,
        )
        return asyncio.run(self.process_async(req)).to_dict()

    def debug_error(self, error_trace: str, code: str = "",
                    language: str = "python",
                    context: Optional[SharedContextBuffer] = None) -> Dict[str, Any]:
        req = CodingRequest(
            objective=f"Debug this error:\n{error_trace}",
            language=language,
            original_code=code,
            error_trace=error_trace,
            task_kind=TaskKind.DEBUG,
            context=context,
        )
        return asyncio.run(self.process_async(req)).to_dict()

    def refactor_code(self, code: str, instructions: str = "",
                      language: str = "python",
                      context: Optional[SharedContextBuffer] = None) -> Dict[str, Any]:
        req = CodingRequest(
            objective=f"Refactor this code. {instructions}",
            language=language,
            original_code=code,
            task_kind=TaskKind.REFACTOR,
            context=context,
        )
        return asyncio.run(self.process_async(req)).to_dict()

    def write_tests(self, code: str, language: str = "python",
                    framework: str = "",
                    context: Optional[SharedContextBuffer] = None) -> Dict[str, Any]:
        req = CodingRequest(
            objective=f"Write comprehensive tests{f' using {framework}' if framework else ''}.",
            language=language,
            original_code=code,
            task_kind=TaskKind.TEST,
            context=context,
        )
        return asyncio.run(self.process_async(req)).to_dict()

    def security_audit(self, code: str, language: str = "python",
                       context: Optional[SharedContextBuffer] = None) -> Dict[str, Any]:
        req = CodingRequest(
            objective="Perform a full security audit.",
            language=language,
            original_code=code,
            task_kind=TaskKind.SECURITY,
            context=context,
        )
        return asyncio.run(self.process_async(req)).to_dict()

    def pipeline(self, *agents) -> "_Pipeline":
        """
        Create an agent pipeline.

        Usage:
            result = coding_agent.pipeline(research_agent, coding_agent).run(objective)
        """
        return _Pipeline([self] + list(agents))

    def get_metrics(self) -> Dict[str, Any]:
        """Return a snapshot of this agent's telemetry."""
        return {**self._metrics.snapshot(), "cache_size": len(self._cache) if self._cache else 0}

    def clear_cache(self) -> None:
        if self._cache:
            self._cache.clear()

    # ── Core Async Pipeline ──────────────────────────────────────────────────

    async def process_async(self, req: CodingRequest) -> CodingResult:
        """
        Main async execution path.
        1. Classify task
        2. Check cache
        3. Build prompt
        4. LLM call with retry
        5. Parse + validate
        6. Generate diff (refactor tasks)
        7. Post to shared context
        8. Return CodingResult
        """
        start_ms = time.monotonic() * 1000
        self._metrics.calls += 1

        # 1 — task kind
        task_kind = req.task_kind or _classify_task(req.objective)
        language  = req.language or "python"

        self.log(f"[{task_kind.name}] [{language}] {req.objective[:80]}")

        # 2 — cache lookup
        cache_key = _cache_key(req)
        if self._cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self.log("Cache hit — returning cached result.")
                cached.metrics["from_cache"] = True
                return cached

        # 3 — build prompt
        system_prompt  = _build_system_prompt(task_kind, language)
        user_prompt    = self._build_user_prompt(req, task_kind)
        max_tokens     = _TOKEN_BUDGET.get(task_kind, 2048)

        # 4 — LLM with retry
        raw = await self._llm_with_retry(system_prompt, user_prompt, max_tokens)
        if raw is None:
            self._metrics.failures += 1
            return CodingResult(
                status="error",
                task_kind=task_kind,
                error="LLM call failed after all retries.",
                metrics=self._make_metrics_snapshot(start_ms),
            )

        # 5 — parse + validate
        parsed  = self._parse_response(raw)
        result  = self._build_result(parsed, task_kind, language)

        if self._enable_validation:
            result = self._run_validation(result, language)

        # 6 — diff for refactor
        if task_kind == TaskKind.REFACTOR and req.original_code and result.files:
            new_code   = result.files[0].content
            result.diff = _unified_diff(
                req.original_code, new_code,
                filename=result.files[0].path or f"code.{language}",
            )

        # 7 — record metrics
        result.metrics = self._make_metrics_snapshot(start_ms)
        result.status  = "success"

        # 8 — push to shared context
        if req.context:
            req.context.post(
                sender=self.name,
                content=result.to_dict(),
                message_type="result",
                task=task_kind.name.lower(),
            )

        # cache it
        if self._cache:
            self._cache.set(cache_key, result)

        self._metrics.successes += 1
        self.log(f"Task completed in {result.metrics.get('latency_ms', 0):.0f}ms")
        return result

    # ── Internal Helpers ─────────────────────────────────────────────────────

    def _build_user_prompt(self, req: CodingRequest, task_kind: TaskKind) -> str:
        parts: List[str] = []

        parts.append(f"OBJECTIVE: {req.objective}")

        if req.original_code:
            lang_tag = req.language or ""
            parts.append(f"\nCODE:\n```{lang_tag}\n{req.original_code}\n```")

        if req.error_trace:
            parts.append(f"\nERROR TRACEBACK:\n```\n{req.error_trace}\n```")

        # Inject shared-context findings
        if req.context:
            for sender, label in [
                ("ResearchAgent",      "RESEARCH CONTEXT"),
                ("AnalysisAgent",      "ANALYSIS CONTEXT"),
                ("VulnerabilityAgent", "SECURITY REQUIREMENTS"),
                ("DataAgent",          "DATA CONTEXT"),
            ]:
                finding = req.context.get_latest_result(sender=sender)
                if finding:
                    parts.append(f"\n{label} (from {sender}):\n{str(finding)[:1500]}")

        # Multi-turn history
        if req.conversation_history:
            history_str = "\n".join(
                f"{m['role'].upper()}: {m['content'][:400]}"
                for m in req.conversation_history[-6:]  # last 3 exchanges
            )
            parts.append(f"\nCONVERSATION HISTORY (recent):\n{history_str}")

        # Security hint for sensitive task kinds
        if task_kind in (TaskKind.SECURITY, TaskKind.GENERATE):
            parts.append(
                "\nSECURITY REMINDER: Always sanitise inputs, use parameterised "
                "queries, avoid eval/exec, and never hardcode secrets."
            )

        return "\n".join(parts)

    async def _llm_with_retry(self, system: str, user: str,
                              max_tokens: int) -> Optional[str]:
        """Call the LLM with exponential back-off on transient errors."""
        delay = BASE_DELAY_SEC
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw = await ai_engine.chat(
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    temperature=0.15,
                    max_tokens=max_tokens,
                )
                return raw
            except Exception as exc:
                error_str = str(exc).lower()
                # Only retry on rate-limit / transient errors
                is_transient = any(kw in error_str for kw in
                                   ("rate limit", "timeout", "503", "502", "overload"))
                if attempt == MAX_RETRIES or not is_transient:
                    self.log(f"LLM call failed (attempt {attempt}): {exc}", "ERROR")
                    return None
                jitter = random.uniform(0, delay * 0.3)
                wait   = min(delay + jitter, MAX_DELAY_SEC)
                self.log(
                    f"Transient error (attempt {attempt}/{MAX_RETRIES}), "
                    f"retrying in {wait:.1f}s: {exc}", "WARNING"
                )
                self._metrics.retries += 1
                await asyncio.sleep(wait)
                delay = min(delay * 2, MAX_DELAY_SEC)
        return None

    def _parse_response(self, raw: str) -> Dict[str, Any]:
        """Strip code fences, then parse JSON. Fall back to raw-text wrapping."""
        cleaned = raw.strip()

        # Strip markdown code fences
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])            # drop opening fence line
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Graceful degradation: wrap raw text in schema shape
        return {
            "analysis":       cleaned,
            "suggestion":     "",
            "code":           "",
            "diff":           "",
            "files":          [],
            "tests":          "",
            "security_notes": [],
        }

    def _build_result(self, parsed: Dict[str, Any],
                      task_kind: TaskKind, language: str) -> CodingResult:
        """Map the parsed LLM dict to a typed CodingResult."""
        raw_files = parsed.get("files") or []
        files = [
            CodeFile(
                path=f.get("path", "output"),
                content=f.get("content", ""),
                language=f.get("language", language),
            )
            for f in raw_files
            if isinstance(f, dict)
        ]
        return CodingResult(
            status="pending",          # finalised by caller
            task_kind=task_kind,
            language=language,
            analysis=str(parsed.get("analysis", "")),
            suggestion=str(parsed.get("suggestion", "")),
            code=str(parsed.get("code", "")),
            diff=str(parsed.get("diff", "")),
            files=files,
            tests=str(parsed.get("tests", "")),
            security_notes=list(parsed.get("security_notes") or []),
        )

    def _run_validation(self, result: CodingResult, language: str) -> CodingResult:
        """
        Validate syntax of all generated code files.
        Appends validation notes to result.analysis.
        """
        validation_notes: List[str] = []

        # Validate inline code snippet
        if result.code:
            ok, msg = _validate_syntax(result.code, language)
            if not ok:
                validation_notes.append(f"Inline snippet validation: {msg}")

        # Validate each file
        for cf in result.files:
            lang = cf.language or language
            ok, msg = _validate_syntax(cf.content, lang)
            if not ok:
                validation_notes.append(f"{cf.path}: {msg}")

        # Validate tests
        if result.tests:
            ok, msg = _validate_syntax(result.tests, language)
            if not ok:
                validation_notes.append(f"Test file validation: {msg}")

        if validation_notes:
            note_block = "\n\n[VALIDATION WARNINGS]\n" + "\n".join(f"  • {n}" for n in validation_notes)
            result.analysis += note_block
            self.log(f"Validation issues: {validation_notes}", "WARNING")

        return result

    def _make_metrics_snapshot(self, start_ms: float) -> Dict[str, Any]:
        elapsed = time.monotonic() * 1000 - start_ms
        self._metrics.total_latency_ms += elapsed
        return {
            "latency_ms":   round(elapsed, 1),
            "success_rate": round(self._metrics.success_rate, 4),
            "retries":      self._metrics.retries,
            "from_cache":   False,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Helper
# ─────────────────────────────────────────────────────────────────────────────

class _Pipeline:
    """
    Minimal agent pipeline.

    Passes the output of each agent as context to the next.
    Usage:
        result = coding_agent.pipeline(research_agent, coding_agent).run("Build a REST API")
    """

    def __init__(self, agents: List[Any]):
        self._agents = agents

    def run(self, objective: str, **kwargs) -> Dict[str, Any]:
        context = SharedContextBuffer()
        result: Dict[str, Any] = {}
        for agent in self._agents:
            result = agent.process(objective, context=context, **kwargs)
        return result

    async def run_async(self, objective: str, **kwargs) -> Dict[str, Any]:
        context = SharedContextBuffer()
        result: Dict[str, Any] = {}
        for agent in self._agents:
            if hasattr(agent, "process_async"):
                req = CodingRequest(objective=objective, context=context, **kwargs)
                r = await agent.process_async(req)
                result = r.to_dict()
            else:
                result = agent.process(objective, context=context, **kwargs)
        return result