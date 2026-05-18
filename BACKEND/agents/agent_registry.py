"""
AERIS — Universal Agent Registry

Central intelligence layer that tracks all agents (Core + Swarm Sub-Agents),
their capabilities, health status, and hierarchical relationships.

Usage:
    from agents.agent_registry import agent_registry
    agent_registry.get_all_statuses()
    agent_registry.get_agent("SystemAgent")
    agent_registry.find_agent_for_capability("Screenshot Analysis")
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aeris.agent_registry")


# ─────────────────────────────────────────────────────────────────────────────
# Agent Status Enum
# ─────────────────────────────────────────────────────────────────────────────

class AgentStatus(str, Enum):
    WORKING = "working"
    IDLE    = "idle"
    ERROR   = "error"
    OFFLINE = "offline"


# ─────────────────────────────────────────────────────────────────────────────
# Agent Info — metadata snapshot for each registered agent
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentInfo:
    """Metadata record stored in the registry for each agent."""
    name: str
    description: str
    task_domain: str                        # e.g. "chat", "system", "code"
    version: str                            # e.g. "1.0.0"
    capabilities: List[str]                 # human-readable feature list
    status: AgentStatus = AgentStatus.IDLE
    parent: Optional[str] = None            # name of parent agent (for sub-agents)
    children: List[str] = field(default_factory=list)
    last_health_check: float = 0.0
    error_message: str = ""
    instance: Any = None                    # reference to the actual agent object

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "task_domain": self.task_domain,
            "version": self.version,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "parent": self.parent,
            "children": self.children,
            "last_health_check": self.last_health_check,
            "error_message": self.error_message,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Universal Agent Registry
# ─────────────────────────────────────────────────────────────────────────────

class UniversalAgentRegistry:
    """
    Singleton registry for all AERIS agents.

    Supports hierarchical parent-child relationships (Core Agent → Sub-Agents)
    and provides capability-based lookups for intelligent routing.
    """

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}

    # ── Registration ──────────────────────────────────────────────────────

    def register(
        self,
        agent_instance: Any,
        parent: Optional[str] = None,
    ) -> None:
        """
        Register an agent instance.

        The agent must have these attributes on its class:
          - name:         str
          - description:  str
          - task_domain:  str  (default: "general")
          - version:      str  (default: "1.0.0")
          - capabilities: list (default: [])
        """
        name = getattr(agent_instance, "name", agent_instance.__class__.__name__)
        info = AgentInfo(
            name=name,
            description=getattr(agent_instance, "description", ""),
            task_domain=getattr(agent_instance, "task_domain", "general"),
            version=getattr(agent_instance, "version", "1.0.0"),
            capabilities=list(getattr(agent_instance, "capabilities", [])),
            status=AgentStatus.IDLE,
            parent=parent,
            instance=agent_instance,
        )

        self._agents[name] = info

        # Link to parent
        if parent and parent in self._agents:
            if name not in self._agents[parent].children:
                self._agents[parent].children.append(name)

        logger.info(
            f"Registered agent: {name} (domain={info.task_domain}, "
            f"capabilities={len(info.capabilities)}, parent={parent or 'ROOT'})"
        )

    # ── Lookup ────────────────────────────────────────────────────────────

    def get_agent(self, name: str) -> Optional[AgentInfo]:
        """Get agent metadata by name."""
        return self._agents.get(name)

    def get_instance(self, name: str) -> Optional[Any]:
        """Get the live agent instance by name."""
        info = self._agents.get(name)
        return info.instance if info else None

    def get_all_agents(self) -> Dict[str, AgentInfo]:
        """Return all registered agents."""
        return dict(self._agents)

    def get_core_agents(self) -> List[AgentInfo]:
        """Return only root-level (non sub-agent) agents."""
        return [a for a in self._agents.values() if a.parent is None]

    def get_sub_agents(self, parent_name: str) -> List[AgentInfo]:
        """Return children of a given parent agent."""
        return [
            self._agents[child]
            for child in self._agents.get(parent_name, AgentInfo(name="", description="", task_domain="", version="", capabilities=[])).children
            if child in self._agents
        ]

    # ── Capability-based routing ──────────────────────────────────────────

    def find_agent_for_capability(self, capability: str) -> Optional[AgentInfo]:
        """Find the first agent whose capabilities list matches (case-insensitive)."""
        cap_lower = capability.lower()
        for info in self._agents.values():
            for cap in info.capabilities:
                if cap_lower in cap.lower() or cap.lower() in cap_lower:
                    return info
        return None

    def get_all_capabilities(self) -> Dict[str, List[str]]:
        """Return a map of agent_name → capabilities for all agents."""
        return {
            name: info.capabilities
            for name, info in self._agents.items()
        }

    # ── Health & Status ───────────────────────────────────────────────────

    def update_status(self, name: str, status: AgentStatus, error: str = "") -> None:
        """Update an agent's operational status."""
        if name in self._agents:
            self._agents[name].status = status
            self._agents[name].error_message = error
            self._agents[name].last_health_check = time.time()

    def run_health_checks(self) -> Dict[str, dict]:
        """
        Run health_check() on every registered agent that implements it.
        Returns a status map.
        """
        results = {}
        for name, info in self._agents.items():
            agent = info.instance
            if agent and hasattr(agent, "health_check"):
                try:
                    healthy = agent.health_check()
                    status = AgentStatus.WORKING if healthy else AgentStatus.ERROR
                    self.update_status(name, status)
                    results[name] = {"status": status.value, "healthy": healthy}
                except Exception as e:
                    self.update_status(name, AgentStatus.ERROR, str(e))
                    results[name] = {"status": "error", "healthy": False, "error": str(e)}
            else:
                # No health_check method — assume working
                self.update_status(name, AgentStatus.WORKING)
                results[name] = {"status": "working", "healthy": True}
        return results

    def get_all_statuses(self) -> Dict[str, dict]:
        """
        Return a hierarchical status map:
        {
          "ChatAgent": {"status": "working", "capabilities": [...], "children": {}},
          "ProjectBuilder": {"status": "working", "capabilities": [...], "children": {
              "AnalysisAgent": {"status": "working", ...},
              "CodingAgent": {"status": "working", ...},
          }},
        }
        """
        result = {}
        for name, info in self._agents.items():
            if info.parent is not None:
                continue  # Skip children; they'll be nested under parent
            entry = {
                "status": info.status.value,
                "task_domain": info.task_domain,
                "capabilities": info.capabilities,
                "version": info.version,
                "error": info.error_message or None,
                "children": {},
            }
            for child_name in info.children:
                child = self._agents.get(child_name)
                if child:
                    entry["children"][child_name] = {
                        "status": child.status.value,
                        "task_domain": child.task_domain,
                        "capabilities": child.capabilities,
                        "version": child.version,
                        "error": child.error_message or None,
                    }
            result[name] = entry
        return result

    # ── Summary for LLM / Chat Agent ─────────────────────────────────────

    def get_capabilities_summary(self) -> str:
        """
        Generate a human-readable summary of all agents and their capabilities.
        Suitable for injecting into the ChatAgent's system prompt.
        """
        lines = ["## AERIS Agent Capabilities\n"]
        for info in sorted(self._agents.values(), key=lambda a: (a.parent or "", a.name)):
            if info.parent:
                continue
            status_icon = "✅" if info.status in (AgentStatus.WORKING, AgentStatus.IDLE) else "❌"
            lines.append(f"### {status_icon} {info.name} (v{info.version})")
            lines.append(f"*Domain:* {info.task_domain} | *Status:* {info.status.value}")
            if info.capabilities:
                for cap in info.capabilities:
                    lines.append(f"  - {cap}")
            if info.children:
                lines.append(f"  **Sub-Agents:**")
                for child_name in info.children:
                    child = self._agents.get(child_name)
                    if child:
                        child_icon = "✅" if child.status in (AgentStatus.WORKING, AgentStatus.IDLE) else "❌"
                        caps = ", ".join(child.capabilities[:3]) if child.capabilities else "—"
                        lines.append(f"    - {child_icon} {child.name}: {caps}")
            lines.append("")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._agents)

    def __repr__(self) -> str:
        core = len([a for a in self._agents.values() if a.parent is None])
        sub = len(self._agents) - core
        return f"<AgentRegistry: {core} core agents, {sub} sub-agents>"


# ── Global singleton ──────────────────────────────────────────────────────────
agent_registry = UniversalAgentRegistry()
