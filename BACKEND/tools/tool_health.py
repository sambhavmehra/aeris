"""
AERIS — Tool Health Tracker
═══════════════════════════════════════════════════════════════════════
Tracks the health and reliability of tools in the Universal Registry.
Records metrics like success rate, average execution time, and failure
patterns to assist the ToolSelector in choosing reliable tools.
═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("AerisToolHealth")

@dataclass
class ToolMetrics:
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    total_execution_time_ms: float = 0.0
    last_error: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        if self.total_runs == 0:
            return 1.0 # Optimistic default
        return self.successful_runs / self.total_runs
        
    @property
    def avg_execution_time_ms(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.total_execution_time_ms / self.total_runs

    def to_dict(self) -> dict:
        return {
            "total_runs": self.total_runs,
            "successful_runs": self.successful_runs,
            "failed_runs": self.failed_runs,
            "success_rate": self.success_rate,
            "avg_execution_time_ms": self.avg_execution_time_ms,
            "last_error": self.last_error,
        }

class ToolHealthTracker:
    """Tracks and persists tool health metrics."""

    _PERSIST_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "tool_health.json"

    def __init__(self):
        self._metrics: Dict[str, ToolMetrics] = {}
        self._load_persisted()

    def record_execution(self, tool_name: str, success: bool, execution_time_ms: float, error_type: Optional[str] = None):
        """Record the outcome of a tool execution."""
        if tool_name not in self._metrics:
            self._metrics[tool_name] = ToolMetrics()
            
        metrics = self._metrics[tool_name]
        metrics.total_runs += 1
        metrics.total_execution_time_ms += execution_time_ms
        
        if success:
            metrics.successful_runs += 1
        else:
            metrics.failed_runs += 1
            if error_type:
                metrics.last_error = error_type

        # Periodically persist
        if metrics.total_runs % 5 == 0:
             self._persist()

    def get_metrics(self, tool_name: str) -> ToolMetrics:
        """Get metrics for a specific tool."""
        return self._metrics.get(tool_name, ToolMetrics())

    def get_all_metrics(self) -> Dict[str, dict]:
        """Get a summary of all metrics."""
        return {name: m.to_dict() for name, m in self._metrics.items()}

    def _persist(self):
        try:
            self._PERSIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {name: m.to_dict() for name, m in self._metrics.items()}
            self._PERSIST_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist tool health metrics: {e}")

    def _load_persisted(self):
        try:
            if self._PERSIST_FILE.exists():
                data = json.loads(self._PERSIST_FILE.read_text(encoding="utf-8"))
                for name, m_data in data.items():
                    metrics = ToolMetrics(
                        total_runs=m_data.get("total_runs", 0),
                        successful_runs=m_data.get("successful_runs", 0),
                        failed_runs=m_data.get("failed_runs", 0),
                        total_execution_time_ms=m_data.get("total_runs", 0) * m_data.get("avg_execution_time_ms", 0),
                        last_error=m_data.get("last_error")
                    )
                    self._metrics[name] = metrics
        except Exception as e:
            logger.warning(f"Failed to load persisted tool health: {e}")

# Global Singleton
_health_tracker: Optional[ToolHealthTracker] = None

def get_health_tracker() -> ToolHealthTracker:
    global _health_tracker
    if _health_tracker is None:
        _health_tracker = ToolHealthTracker()
    return _health_tracker
