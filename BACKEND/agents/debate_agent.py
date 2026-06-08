"""
AERIS Swarm Debate Agent — "CONCORD"
====================================
Implements a multi-agent consensus debate protocol where research, coding,
and auditing agents review, criticize, and refine proposals.
"""

import json
import logging
import asyncio
from typing import Any, Dict, List, Optional
from agents.base_agent import BaseAgent
from ai_engine import ai_engine
from services.collaboration_events import collaboration_bus

logger = logging.getLogger("aeris.agent.debate")

class DebateAgent(BaseAgent):
    """
    Consensus reasoning agent that coordinates debates between other agents
    to refine output proposals.
    """

    def __init__(self):
        super().__init__(
            name="DebateAgent",
            description="Consensus review loop - debates and refines proposals between agents.",
            task_domain="debate",
            version="1.0.0",
            capabilities=[
                "Multi-Agent Consensus Debating",
                "Self-Correction & Critique Loops",
                "Realtime Step Event Streaming",
                "Consensus Transcript Formatting",
            ],
        )

    async def think(self, message: str, context: dict) -> Any:
        """Analyze the request and build a debate agenda."""
        prompt = (
            "You are the planner for AERIS's Swarm Debate Agent ('CONCORD').\n"
            "Analyze the user's request and decide how to structure the multi-agent debate.\n\n"
            f"User request: {message}\n\n"
            "Identify the topic/proposal to debate, and choose exactly two specialized agents to debate it.\n"
            "Options: ResearchAgent, CodingAgent, SecurityAgent, AuditAgent, SystemAgent.\n"
            "Examples:\n"
            "- For programming/algorithms: CodingAgent and AuditAgent\n"
            "- For cybersecurity/recon: SecurityAgent and AuditAgent\n"
            "- For general facts/decisions: ResearchAgent and AuditAgent\n\n"
            "Respond with ONLY valid JSON:\n"
            "{\n"
            "  \"topic\": \"<refined topic or question to debate>\",\n"
            "  \"agents\": [\"Agent1\", \"Agent2\"],\n"
            "  \"reasoning\": \"<rationale for agent choices>\"\n"
            "}"
        )

        try:
            raw = await ai_engine.classify(prompt)
            raw = raw.strip().strip("```json").strip("```").strip()
            plan = json.loads(raw)
        except Exception as e:
            logger.warning(f"[DebateAgent] Planner failed: {e}. Using fallbacks.")
            plan = {
                "topic": message,
                "agents": ["ResearchAgent", "AuditAgent"],
                "reasoning": "Fallback to default research and audit debate."
            }

        plan["original_message"] = message
        plan["task_id"] = context.get("task_id", f"deb_{int(asyncio.get_event_loop().time())}")
        return plan

    async def execute(self, plan: Any) -> Any:
        """Execute the debate protocol step-by-step, emitting events to the bus."""
        task_id = plan.get("task_id")
        topic = plan.get("topic")
        agents = plan.get("agents", ["ResearchAgent", "AuditAgent"])
        
        # Safe registry mapping for user-facing inputs or minor capitalization variants
        registry_map = {
            "codeagent": "CodingAgent",
            "codingagent": "CodingAgent",
            "code": "CodingAgent",
            "researchagent": "ResearchAgent",
            "research": "ResearchAgent",
            "auditagent": "AuditAgent",
            "audit": "AuditAgent",
            "securityagent": "SecurityAgent",
            "security": "SecurityAgent",
            "systemagent": "SystemAgent",
            "system": "SystemAgent"
        }

        agent_a_name = registry_map.get(agents[0].lower(), "ResearchAgent")
        agent_b_name = registry_map.get(agents[1].lower(), "AuditAgent")

        # ── Turn 1: Draft Proposal ──
        logger.info(f"[DebateAgent] Initial proposal draft started on: '{topic[:60]}'")
        await collaboration_bus.emit(task_id, "agent_start", {
            "agent": agent_a_name,
            "status": f"Drafting initial proposal for: {topic[:100]}...",
            "progress": 20
        })

        # Run Agent A
        response_a = ""
        try:
            result_a = await self.use_agent(agent_a_name, f"Please generate a comprehensive initial draft proposal/solution for the following request:\n\n{topic}")
            response_a = result_a.get("response", "Could not generate proposal.")
            success_a = result_a.get("success", False)
        except Exception as e:
            response_a = f"Error running draft agent: {e}"
            success_a = False

        await collaboration_bus.emit(task_id, "agent_progress", {
            "agent": agent_a_name,
            "status": "Draft proposal completed.",
            "response": response_a,
            "progress": 45
        })

        # ── Turn 2: Critical Audit / Critique ──
        logger.info(f"[DebateAgent] Audit critique started on the drafted proposal")
        await collaboration_bus.emit(task_id, "agent_start", {
            "agent": agent_b_name,
            "status": f"Critiquing and identifying vulnerabilities/flaws in the initial proposal...",
            "progress": 60
        })

        # Run Agent B (Auditor)
        response_b = ""
        audit_instruction = (
            f"Please conduct a critical audit of the following proposal. Highlight any logical flaws, "
            f"errors, security risks, performance issues, or edge cases. Suggest specific corrections.\n\n"
            f"=== PROPOSAL DRAFT ===\n"
            f"{response_a}\n"
            f"=== END PROPOSAL DRAFT ==="
        )
        try:
            result_b = await self.use_agent(agent_b_name, audit_instruction)
            response_b = result_b.get("response", "Could not generate critique.")
            success_b = result_b.get("success", False)
        except Exception as e:
            response_b = f"Error running audit agent: {e}"
            success_b = False

        await collaboration_bus.emit(task_id, "agent_progress", {
            "agent": agent_b_name,
            "status": "Critique and audit completed.",
            "response": response_b,
            "progress": 80
        })

        # ── Turn 3: Refinement & Re-evaluation ──
        logger.info(f"[DebateAgent] Proposal refinement started based on critique")
        await collaboration_bus.emit(task_id, "agent_start", {
            "agent": agent_a_name,
            "status": "Refining original proposal based on audit critiques...",
            "progress": 90
        })

        refine_instruction = (
            f"Refine your original proposal to resolve and incorporate the audit critiques.\n\n"
            f"=== ORIGINAL DRAFT ===\n"
            f"{response_a}\n\n"
            f"=== CRITIQUE & ISSUES ===\n"
            f"{response_b}\n\n"
            f"Please output a corrected, optimized, and finalized final version."
        )

        final_response = ""
        try:
            result_refine = await self.use_agent(agent_a_name, refine_instruction)
            final_response = result_refine.get("response", "Could not generate refined proposal.")
        except Exception as e:
            final_response = f"Error running refinement agent: {e}"

        await collaboration_bus.emit(task_id, "agent_complete", {
            "agent": agent_a_name,
            "status": "Swarm debate consensus finalized.",
            "response": final_response,
            "progress": 100
        })

        return {
            "topic": topic,
            "agent_a": agent_a_name,
            "agent_b": agent_b_name,
            "draft_proposal": response_a,
            "critique": response_b,
            "consensus_proposal": final_response
        }

    async def report(self, results: Any) -> str:
        """Create a beautiful markdown consensus transcript."""
        topic = results.get("topic")
        agent_a = results.get("agent_a")
        agent_b = results.get("agent_b")
        draft = results.get("draft_proposal")
        critique = results.get("critique")
        final = results.get("consensus_proposal")

        report_md = (
            f"# ⚖️ Swarm Debate Consensus Transcript\n\n"
            f"**Debated Topic:** {topic}\n\n"
            f"**Participant Agents:** `{agent_a}` (Proposer/Refiner) ↔ `{agent_b}` (Auditor)\n\n"
            f"---\n\n"
            f"## Phase 1: Initial Proposal Draft (`{agent_a}`)\n"
            f"```markdown\n"
            f"{draft}\n"
            f"```\n\n"
            f"## Phase 2: Audit Review & Critiques (`{agent_b}`)\n"
            f"```markdown\n"
            f"{critique}\n"
            f"```\n\n"
            f"## Phase 3: Final Consensus Refinement (`{agent_a}`)\n"
            f"Incorporated the critiques and logic improvements from `{agent_b}`.\n\n"
            f"{final}\n"
        )
        return report_md
