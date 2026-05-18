"""
Aeris AI OS — Feedback Loop (Part 5)
═══════════════════════════════════════════════════════════════════════
Post-execution learning system. After every tool execution:
  • Updates tool success/failure stats
  • Tracks execution patterns (which tools follow which)
  • Records known issues per tool
  • Feeds data back to ToolAwareness and SelectionIntelligence
  • Enables AERIS to improve decisions automatically over time

This is the nervous system that makes AERIS learn from experience.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AerisFeedbackLoop")


@dataclass
class ExecutionRecord:
    """Single execution record for learning."""
    tool_name: str
    success: bool
    execution_time_ms: float
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    objective: str = ""
    timestamp: float = field(default_factory=time.time)
    previous_tool: Optional[str] = None    # What tool ran before this
    retry_count: int = 0


@dataclass
class ToolPattern:
    """Observed pattern: tool A frequently follows tool B."""
    from_tool: str
    to_tool: str
    count: int = 0
    success_count: int = 0

    @property
    def success_rate(self) -> float:
        return self.success_count / self.count if self.count > 0 else 0.0


class FeedbackLoop:
    """
    Post-execution learning system that:
      1. Records every execution outcome
      2. Updates tool awareness with runtime stats
      3. Tracks tool sequencing patterns
      4. Identifies recurring issues
      5. Persists learning data to disk

    Usage:
        loop = get_feedback_loop()
        loop.record(tool_name, success, exec_time, error, objective, prev_tool)
        patterns = loop.get_common_sequences("write_file")
        issues = loop.get_known_issues("run_bash")
    """

    _PERSIST_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "intelligence"

    def __init__(self):
        self._records: List[ExecutionRecord] = []
        self._tool_stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "total": 0, "success": 0, "fail": 0,
            "consecutive_failures": 0,
            "errors": [],  # Last N errors
            "avg_time_ms": 0.0,
        })
        self._patterns: Dict[str, ToolPattern] = {}  # "from->to" key
        self._known_issues: Dict[str, List[str]] = defaultdict(list)
        self._load_persisted()

    def record(
        self,
        tool_name: str,
        success: bool,
        execution_time_ms: float,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        objective: str = "",
        previous_tool: Optional[str] = None,
        retry_count: int = 0,
    ):
        """
        Record an execution outcome and update all learning data.
        This is the MAIN entry point — called after every tool execution.
        """
        record = ExecutionRecord(
            tool_name=tool_name,
            success=success,
            execution_time_ms=execution_time_ms,
            error_type=error_type,
            error_message=error_message,
            objective=objective,
            previous_tool=previous_tool,
            retry_count=retry_count,
        )
        self._records.append(record)

        # Keep bounded
        if len(self._records) > 500:
            self._records = self._records[-500:]

        # 1. Update tool stats
        self._update_stats(record)

        # 2. Update sequencing patterns
        if previous_tool:
            self._update_pattern(previous_tool, tool_name, success)

        # 3. Track known issues
        if not success and error_message:
            self._track_issue(tool_name, error_message)

        # 4. Feed back to Tool Awareness
        self._feed_to_awareness(tool_name, success, execution_time_ms, error_type)

        # 5. Feed back to System Awareness
        self._feed_to_system_awareness(tool_name, success, objective, error_message)

        # 6. Periodic persistence
        if len(self._records) % 10 == 0:
            self._persist()

    # ── Stats Updates ─────────────────────────────────────────────────

    def _update_stats(self, record: ExecutionRecord):
        stats = self._tool_stats[record.tool_name]
        stats["total"] += 1

        if record.success:
            stats["success"] += 1
            stats["consecutive_failures"] = 0
        else:
            stats["fail"] += 1
            stats["consecutive_failures"] += 1
            if record.error_message:
                stats["errors"].append({
                    "type": record.error_type,
                    "message": record.error_message[:200],
                    "time": record.timestamp,
                })
                # Keep last 10 errors
                stats["errors"] = stats["errors"][-10:]

        # Running average execution time
        n = stats["total"]
        stats["avg_time_ms"] = (
            (stats["avg_time_ms"] * (n - 1) + record.execution_time_ms) / n
        )

    def _update_pattern(self, from_tool: str, to_tool: str, success: bool):
        key = f"{from_tool}->{to_tool}"
        if key not in self._patterns:
            self._patterns[key] = ToolPattern(from_tool=from_tool, to_tool=to_tool)
        pattern = self._patterns[key]
        pattern.count += 1
        if success:
            pattern.success_count += 1

    def _track_issue(self, tool_name: str, error: str):
        issues = self._known_issues[tool_name]
        short_error = error[:150]
        # Don't duplicate similar errors
        if not any(short_error[:50] in existing for existing in issues):
            issues.append(short_error)
        # Keep last 5 unique issues
        self._known_issues[tool_name] = issues[-5:]

    def _feed_to_awareness(self, tool_name: str, success: bool,
                           execution_time_ms: float, error_type: Optional[str]):
        try:
            from intelligence.tool_awareness import get_tool_awareness
            get_tool_awareness().update_from_execution(
                tool_name, success, execution_time_ms, error_type
            )
        except Exception:
            pass

    def _feed_to_system_awareness(self, tool_name: str, success: bool,
                                   objective: str, error: Optional[str]):
        try:
            from intelligence.system_awareness import get_system_awareness
            sa = get_system_awareness()
            if success:
                sa.record_success(tool_name, objective)
            else:
                sa.record_failure(tool_name, objective, error or "Unknown error")
        except Exception:
            pass

    # ── Queries ────────────────────────────────────────────────────────

    def get_tool_stats(self, tool_name: str) -> Dict[str, Any]:
        """Get execution stats for a tool."""
        return dict(self._tool_stats.get(tool_name, {}))

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats for all tools."""
        return {name: dict(stats) for name, stats in self._tool_stats.items()}

    def get_common_sequences(self, tool_name: str) -> List[Tuple[str, int, float]]:
        """Get tools that commonly follow this tool.
        Returns: [(next_tool, count, success_rate), ...]"""
        sequences = []
        for key, pattern in self._patterns.items():
            if pattern.from_tool == tool_name and pattern.count >= 2:
                sequences.append((pattern.to_tool, pattern.count, pattern.success_rate))
        sequences.sort(key=lambda x: x[1], reverse=True)
        return sequences

    def get_known_issues(self, tool_name: str) -> List[str]:
        """Get known recurring issues for a tool."""
        return list(self._known_issues.get(tool_name, []))

    def get_consecutive_failures(self, tool_name: str) -> int:
        """Get current consecutive failure count."""
        stats = self._tool_stats.get(tool_name, {})
        return stats.get("consecutive_failures", 0)

    def should_avoid_tool(self, tool_name: str) -> Tuple[bool, str]:
        """Determine if a tool should be avoided based on recent failures.
        Returns: (should_avoid, reason)"""
        stats = self._tool_stats.get(tool_name)
        if not stats:
            return False, ""

        if stats.get("consecutive_failures", 0) >= 3:
            return True, f"{tool_name} has {stats['consecutive_failures']} consecutive failures"

        if stats["total"] >= 5:
            success_rate = stats["success"] / stats["total"]
            if success_rate < 0.3:
                return True, f"{tool_name} has only {success_rate:.0%} success rate over {stats['total']} runs"

        return False, ""

    def suggest_alternative(self, failed_tool: str, objective: str) -> Optional[str]:
        """Suggest an alternative tool when one fails repeatedly."""
        try:
            from intelligence.tool_awareness import get_tool_awareness
            awareness = get_tool_awareness()
            
            # Get the failed tool's category
            tk = awareness.get_tool_knowledge(failed_tool)
            if not tk:
                return None

            # Find other tools in the same category
            all_knowledge = awareness.get_all_knowledge()
            alternatives = []
            for name, alt_tk in all_knowledge.items():
                if name == failed_tool:
                    continue
                if alt_tk.category == tk.category:
                    avoid, _ = self.should_avoid_tool(name)
                    if not avoid:
                        alternatives.append((name, alt_tk.success_rate))

            if alternatives:
                # Pick the most reliable alternative
                alternatives.sort(key=lambda x: x[1], reverse=True)
                return alternatives[0][0]
        except Exception:
            pass
        return None

    def get_recent_failures_for_objective(self, objective: str, limit: int = 3) -> List[Dict[str, Any]]:
        """Get recent failures that match a similar objective."""
        obj_words = set(objective.lower().split())
        matches = []
        for record in reversed(self._records):
            if not record.success and record.objective:
                rec_words = set(record.objective.lower().split())
                overlap = len(obj_words & rec_words)
                if overlap >= 2:
                    matches.append({
                        "tool": record.tool_name,
                        "error": record.error_message,
                        "objective": record.objective,
                        "time": record.timestamp,
                    })
            if len(matches) >= limit:
                break
        return matches

    # ── Persistence ───────────────────────────────────────────────────

    def _persist(self):
        """Save learning data to disk."""
        try:
            self._PERSIST_DIR.mkdir(parents=True, exist_ok=True)

            # Save stats
            stats_file = self._PERSIST_DIR / "feedback_stats.json"
            stats_data = {}
            for name, stats in self._tool_stats.items():
                stats_data[name] = {
                    "total": stats["total"],
                    "success": stats["success"],
                    "fail": stats["fail"],
                    "consecutive_failures": stats["consecutive_failures"],
                    "avg_time_ms": stats["avg_time_ms"],
                    "errors": stats["errors"][-5:],
                }
            stats_file.write_text(json.dumps(stats_data, indent=2, default=str), encoding="utf-8")

            # Save patterns
            patterns_file = self._PERSIST_DIR / "feedback_patterns.json"
            patterns_data = {
                key: {"from": p.from_tool, "to": p.to_tool, "count": p.count, "success_count": p.success_count}
                for key, p in self._patterns.items()
            }
            patterns_file.write_text(json.dumps(patterns_data, indent=2), encoding="utf-8")

            # Save known issues
            issues_file = self._PERSIST_DIR / "known_issues.json"
            issues_file.write_text(json.dumps(dict(self._known_issues), indent=2), encoding="utf-8")

        except Exception as e:
            logger.warning(f"Failed to persist feedback data: {e}")

    def _load_persisted(self):
        """Load learning data from disk."""
        try:
            stats_file = self._PERSIST_DIR / "feedback_stats.json"
            if stats_file.exists():
                data = json.loads(stats_file.read_text(encoding="utf-8"))
                for name, stats in data.items():
                    self._tool_stats[name] = {
                        "total": stats.get("total", 0),
                        "success": stats.get("success", 0),
                        "fail": stats.get("fail", 0),
                        "consecutive_failures": stats.get("consecutive_failures", 0),
                        "avg_time_ms": stats.get("avg_time_ms", 0.0),
                        "errors": stats.get("errors", []),
                    }

            patterns_file = self._PERSIST_DIR / "feedback_patterns.json"
            if patterns_file.exists():
                data = json.loads(patterns_file.read_text(encoding="utf-8"))
                for key, p_data in data.items():
                    self._patterns[key] = ToolPattern(
                        from_tool=p_data["from"], to_tool=p_data["to"],
                        count=p_data["count"], success_count=p_data["success_count"],
                    )

            issues_file = self._PERSIST_DIR / "known_issues.json"
            if issues_file.exists():
                data = json.loads(issues_file.read_text(encoding="utf-8"))
                for name, issues in data.items():
                    self._known_issues[name] = issues

        except Exception as e:
            logger.warning(f"Failed to load persisted feedback data: {e}")


# ── Global Singleton ─────────────────────────────────────────────────
_feedback_loop: Optional[FeedbackLoop] = None


def get_feedback_loop() -> FeedbackLoop:
    global _feedback_loop
    if _feedback_loop is None:
        _feedback_loop = FeedbackLoop()
    return _feedback_loop
