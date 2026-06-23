"""
AERIS — Guardian Agent (System Watchdog)
========================================
Specialized management agent dedicated to monitoring agent states, system loads,
handling task timeouts, and executing automated agent failovers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from agents.agent_registry import agent_registry, AgentStatus
from tools.diagnostics_tools import get_system_metrics

logger = logging.getLogger("aeris.agent.guardian")

PLAN_PROMPT = """You are AERIS's Guardian Agent (Watchdog).
Your job is to determine how to investigate system stability, check running processes, restart frozen agents, coordinate agent failovers, or check/audit local Guardian Mode configurations and logs.

Available actions:
- monitor_registry: Audit the Universal Agent Registry for any crashed or ERROR status agents.
- audit_system_load: Scan current CPU, RAM, and Disk space for bottleneck thresholds.
- handle_failover(agent_name: str): Marks a crashed agent as OFFLINE and determines an alternative routing path.
- check_scheduler_queue: Review background scheduler execution queue to find stuck processes.
- get_guardian_status: Retrieve the status, configuration, active blocks, and violation counts of local Guardian Mode.
- get_guardian_logs: Retrieve the security audit logs and violation attempts of local Guardian Mode.

User request: {message}

Rules:
- If the user wants to check all agent health or statuses -> use monitor_registry.
- If the user wants to check CPU load, memory warnings, or server capacity -> use audit_system_load.
- If a specific agent (e.g. CodeAgent) is crashed or in error -> use handle_failover.
- If the user wants to check stuck background tasks -> use check_scheduler_queue.
- If the user wants to check/status/config of local Guardian/Guest Mode -> use get_guardian_status.
- If the user wants to see security logs/audit/violations of local Guardian/Guest Mode -> use get_guardian_logs.

Respond with ONLY valid JSON:
{{
  "actions": [
    {{"name": "action_name", "params": {{"param": "value"}}}}
  ],
  "explanation": "Brief explanation of watch actions and focus"
}}
"""

REPORT_PROMPT = """You are AERIS's System Watchdog & Guardian.
You have gathered diagnostic metrics and status changes from the agent workforce.
Format these inputs into a clean, high-priority markdown report. Highlight errors in RED, warning signs in YELLOW, and stable components in GREEN.

User query/concern: {message}
Raw metrics:
{results}
"""

class GuardianAgent(BaseAgent):
    """System watchdog agent for monitoring agent health and system performance."""

    def __init__(self):
        super().__init__(
            name="GuardianAgent",
            description="Monitors agent registry states, manages system CPU/RAM limits, and triggers agent recovery/failover procedures.",
            task_domain="guardian",
            version="1.0.0",
            capabilities=[
                "Agent Registry Auditing",
                "System Resource Safeguard",
                "Automated Agent Recovery",
                "Process Watchdog Monitoring"
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        prompt = PLAN_PROMPT.format(message=message)
        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"): raw = raw[:-3]
                raw = raw.strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Guardian plan parsing failed: {e}. Falling back to default registry audit.")
            return {"actions": [{"name": "monitor_registry", "params": {}}], "explanation": "Fallback status check"}

    async def execute(self, plan: Any) -> Any:
        results = []
        for step in plan.get("actions", []):
            name = step.get("name")
            params = step.get("params", {})
            try:
                self.log(f"Guardian running watch action: {name}")
                if name == "monitor_registry":
                    agent_registry.run_health_checks()
                    statuses = agent_registry.get_all_statuses()
                    crashed = [k for k, v in statuses.items() if v.get("status") in ("error", "offline")]
                    results.append({
                        "action": name,
                        "success": True,
                        "total_agents": len(agent_registry),
                        "crashed_count": len(crashed),
                        "crashed_agents": crashed,
                        "statuses": statuses
                    })
                elif name == "audit_system_load":
                    metrics = get_system_metrics()
                    # Trigger alert thresholds
                    alerts = []
                    if metrics.get("cpu_percent", 0.0) > 85.0:
                        alerts.append("🔥 CPU utilization exceeds 85%!")
                    if metrics.get("ram_used_percent", 0.0) > 90.0:
                        alerts.append("🚨 RAM utilization exceeds 90%!")
                    if metrics.get("disk_used_percent", 0.0) > 95.0:
                        alerts.append("⚠️ Disk space is almost full (>95%)!")
                    results.append({
                        "action": name,
                        "success": True,
                        "metrics": metrics,
                        "alerts": alerts
                    })
                elif name == "handle_failover":
                    tgt = params.get("agent_name", "")
                    info = agent_registry.get_agent(tgt)
                    if info:
                        agent_registry.update_status(tgt, AgentStatus.OFFLINE, "Marked offline by GuardianAgent watchdog.")
                        # Suggest failover
                        domain = info.task_domain
                        alternatives = [k for k, v in agent_registry.get_all_agents().items() if v.task_domain == domain and k != tgt]
                        results.append({
                            "action": name,
                            "success": True,
                            "agent_offline": tgt,
                            "task_domain": domain,
                            "failover_alternatives": alternatives
                        })
                    else:
                        results.append({"action": name, "success": False, "error": f"Agent {tgt} not registered."})
                elif name == "check_scheduler_queue":
                    from services.scheduler import get_scheduler
                    tasks = get_scheduler().list_tasks("pending")
                    stuck_tasks = []
                    now = time.time()
                    for t in tasks:
                        # Simple heuristic: if scheduled time exists and is older than 5 mins in past and still pending, it is stuck
                        t_time = t.get("scheduled_time", "")
                        # Parse time if possible or track runtime duration
                        # Since we list simple tasks, just report all pending tasks
                        pass
                    results.append({
                        "action": name,
                        "success": True,
                        "pending_count": len(tasks),
                        "queue": tasks
                    })
                elif name == "get_guardian_status":
                    from services.guardian_mode import guardian_mode_manager
                    results.append({
                        "action": name,
                        "success": True,
                        "enabled": guardian_mode_manager.is_active,
                        "config": guardian_mode_manager.config.config,
                        "attempt_counters": guardian_mode_manager.attempt_counters
                    })
                elif name == "get_guardian_logs":
                    from services.guardian_mode import guardian_mode_manager
                    results.append({
                        "action": name,
                        "success": True,
                        "logs": guardian_mode_manager.audit_logger.get_logs()[-20:]
                    })
            except Exception as e:
                self.log(f"Error running action {name}: {e}", "ERROR")
                results.append({"action": name, "success": False, "error": str(e)})
        return results

    async def report(self, results: Any) -> str:
        prompt = REPORT_PROMPT.format(message="", results=json.dumps(results, indent=2))
        try:
            return await ai_engine.chat([
                {"role": "system", "content": "You are AERIS's System Watchdog & Guardian. Respond in clean, high-priority cybersecurity debrief markdown."},
                {"role": "user", "content": prompt}
            ], max_tokens=1500)
        except Exception as e:
            return f"## Guardian Watchdog Status Report\n\n```json\n{json.dumps(results, indent=2)}\n```"
