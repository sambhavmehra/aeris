"""
AERIS — Multi-Agent Sub-Agent System
============================================
Specialized sub-agents that extend AERIS's capabilities without
modifying the existing OSEngine, PlannerAgent, or ExecutorAgent.

Architecture:
  User → Brain → DelegatorAgent
    ├── Simple → PlannerAgent → ExecutorAgent  (EXISTING, untouched)
    └── Complex → Multi-Agent Swarm
           ↓
      CodingAgent / ResearchAgent / AnalysisAgent / VulnerabilityAgent / ToolManagerAgent / RuntimeAgent
           ↓
      Merge results
           ↓
      ExecutorAgent  (EXISTING, untouched)
"""

from agents.sub_agents.delegator import DelegatorAgent, get_delegator
from agents.sub_agents.coding_agent import CodingAgent
from agents.sub_agents.research_agent import ResearchAgent
from agents.sub_agents.analysis_agent import AnalysisAgent
from agents.sub_agents.vulnerability_agent import VulnerabilityAgent
from agents.sub_agents.tool_manager_agent import ToolManagerAgent
from agents.sub_agents.runtime_agent import RuntimeAgent
from agents.sub_agents.architecture_agent import ArchitectureAgent
from agents.sub_agents.documentation_agent import DocumentationAgent

__all__ = [
    "DelegatorAgent",
    "get_delegator",
    "CodingAgent",
    "ResearchAgent",
    "AnalysisAgent",
    "VulnerabilityAgent",
    "ToolManagerAgent",
    "RuntimeAgent",
    "ArchitectureAgent",
    "DocumentationAgent",
]
