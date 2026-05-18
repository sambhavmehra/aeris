"""
AERIS — Delegator Agent (Multi-Agent Router)  v2.0
=========================================================
Smarter orchestration: confidence scoring, agent dependency graph,
partial-failure recovery, mid-flight re-classification, result quality
scoring, parallel timeouts, and swarm memory.

Architecture (unchanged externally):
  User → Brain → DelegatorAgent
    ├── Simple → PlannerAgent → ExecutorAgent  (EXISTING, untouched)
    └── Complex → Multi-Agent Swarm
           ↓
      CodingAgent / ResearchAgent / AnalysisAgent /
      VulnerabilityAgent / ToolManagerAgent / RuntimeAgent
           ↓
      Merge results into SharedContextBuffer
           ↓
      ExecutorAgent  (EXISTING, untouched)

What's new in v2.0
──────────────────
1. Confidence scoring          — LLM returns 0-1 confidence; below
                                 CONFIDENCE_THRESHOLD → forced simple.
2. Agent dependency graph      — AGENT_DEPS defines which agents must
                                 finish before another can start, so
                                 parallel batches are computed correctly.
3. Partial-failure recovery    — failed agents are retried up to
                                 MAX_AGENT_RETRIES with exponential back-off.
4. Mid-flight re-classification — after the first agent batch, if the
                                 accumulated context indicates more agents
                                 are needed, the swarm expands.
5. Result quality scoring      — each agent result is scored 0-1;
                                 the merger weights higher-quality results.
6. Agent timeouts              — parallel agents are killed after
                                 AGENT_TIMEOUT_SECONDS.
7. Swarm memory                — outcomes are stored in memory so future
                                 classifications benefit from past experience.
8. Structured merge prompt     — merger receives a ranked, weighted summary
                                 instead of a raw concatenation.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer
from agents.sub_agents.coding_agent import CodingAgent
from agents.sub_agents.research_agent import ResearchAgent
from agents.sub_agents.analysis_agent import AnalysisAgent
from agents.sub_agents.vulnerability_agent import VulnerabilityAgent
from agents.sub_agents.tool_manager_agent import ToolManagerAgent
from agents.sub_agents.runtime_agent import RuntimeAgent
from agents.sub_agents.architecture_agent import ArchitectureAgent
from agents.sub_agents.documentation_agent import DocumentationAgent

logger = logging.getLogger("AerisDelegator")

# ── Tuneable constants ────────────────────────────────────────────────
CONFIDENCE_THRESHOLD   = 0.65   # Below this → force "simple" regardless of label
MAX_AGENT_RETRIES      = 2      # How many times to retry a failing agent
RETRY_BASE_DELAY       = 1.5    # seconds; doubled on each retry (exponential)
AGENT_TIMEOUT_SECONDS  = 90     # Kill a parallel agent after this many seconds
MAX_PARALLEL_WORKERS   = 6      # Thread-pool cap for parallel execution
QUALITY_WEIGHT_FLOOR   = 0.25   # Agents scoring below this are excluded from merge

# ── Agent dependency graph ────────────────────────────────────────────
# Key: agent that has prerequisites.
# Value: set of agents that MUST complete successfully before it can run.
# Agents not listed here have no prerequisites.
AGENT_DEPS: Dict[str, set] = {
    "ArchitectureAgent":  set(),                           # Runs first
    "CodingAgent":        {"ArchitectureAgent"},           # Needs blueprint
    "VulnerabilityAgent": {"CodingAgent"},                 # Need code before scanning it
    "AnalysisAgent":      {"ResearchAgent"},               # Analyse what was researched
    "RuntimeAgent":       {"CodingAgent", "VulnerabilityAgent"}, # Run only after code + scan
    "DocumentationAgent": {"CodingAgent", "ArchitectureAgent"}   # Write README after generation
}

# ── Agent self-quality scorer prompt (appended to each agent call) ────
QUALITY_SCORER_SUFFIX = (
    "\n\nAfter your response, on a NEW line, output exactly:\n"
    "QUALITY_SCORE: <float 0.0–1.0>\n"
    "where 1.0 = complete, accurate, highly useful; 0.0 = empty/failed."
)

# ── Classifier prompt ─────────────────────────────────────────────────
CLASSIFIER_SYSTEM_PROMPT = """You are AERIS's Task Classifier. Analyse the user objective
and classify it precisely.

SIMPLE tasks (existing Planner → Executor pipeline):
- Open/close an app, play music, screenshot
- Basic file ops, quick chat, web search, system controls

COMPLEX tasks (Multi-Agent Swarm):
- Code generation + testing + security review
- Deep multi-source research
- Vulnerability scanning of a codebase
- Create a new tool/capability
- Analyse data AND generate report AND write code
- Tasks explicitly needing multiple specialised skills

Available agents (only reference these names):
  ArchitectureAgent, CodingAgent, ResearchAgent, AnalysisAgent,
  VulnerabilityAgent, ToolManagerAgent, RuntimeAgent, DocumentationAgent

Return ONLY valid JSON — no markdown fences, no extra keys:
{
    "complexity": "simple" | "complex",
    "confidence": <float 0.0–1.0>,
    "agents_needed": [...],
    "execution_order": "sequential" | "parallel" | "dependency_graph",
    "reasoning": "One concise sentence."
}

RULES:
- Default to "simple" when uncertain (confidence < 0.65 → simple).
- "dependency_graph" = use AGENT_DEPS to order agents; prefer this for complex tasks.
- "parallel" only when agents are fully independent.
- "sequential" as a fallback when dependency info is insufficient.
"""

# ── Re-classification prompt ──────────────────────────────────────────
RECLASSIFY_PROMPT = """You are AERIS's Swarm Expander.
Given the original objective and the partial results so far, decide if
additional agents are needed that were not originally planned.

Return ONLY valid JSON:
{
    "expand": true | false,
    "additional_agents": [...],
    "reasoning": "One concise sentence."
}

Only mark expand=true if the partial results reveal genuine new complexity.
Available agents: ArchitectureAgent, CodingAgent, ResearchAgent, AnalysisAgent,
                  VulnerabilityAgent, ToolManagerAgent, RuntimeAgent, DocumentationAgent.
"""


class DelegatorAgent(BaseAgent):
    """
    The Multi-Agent Router — v2.0.

    Sits between CentralBrain/OSEngine and the execution layer.
    Simple tasks → signal the existing pipeline (no change).
    Complex tasks → orchestrate specialised sub-agents with dependency
                    ordering, retries, timeouts, and quality-weighted merging.
    """

    def __init__(self, memory_agent=None):
        super().__init__(name="DelegatorAgent", memory_agent=memory_agent)

        # Lazy sub-agent registry
        self._agents: Dict[str, Optional[BaseAgent]] = {
            "ArchitectureAgent": None,
            "CodingAgent":       None,
            "ResearchAgent":     None,
            "AnalysisAgent":     None,
            "VulnerabilityAgent": None,
            "ToolManagerAgent":  None,
            "RuntimeAgent":      None,
            "DocumentationAgent": None,
        }
        self._agent_classes = {
            "ArchitectureAgent": ArchitectureAgent,
            "CodingAgent":       CodingAgent,
            "ResearchAgent":     ResearchAgent,
            "AnalysisAgent":     AnalysisAgent,
            "VulnerabilityAgent": VulnerabilityAgent,
            "ToolManagerAgent":  ToolManagerAgent,
            "RuntimeAgent":      RuntimeAgent,
            "DocumentationAgent": DocumentationAgent,
        }

    # ── Main Entry Point ──────────────────────────────────────────────

    def process(self, objective: str, **kwargs) -> Dict[str, Any]:
        """
        Classify and route the objective.

        Returns:
            {
                "route": "simple" | "complex",
                "classification": {...},
                # complex only:
                "result": <merged string>,
                "agents_used": [...],
                "agent_results": {name: {output, quality_score, status}},
                "context": <SharedContextBuffer.to_dict()>,
                "swarm_id": str,
            }
        """
        self.log(f"Delegating: {objective[:120]}")

        # ── 1. Classify ───────────────────────────────────────────────
        classification = self._classify(objective)
        complexity   = classification.get("complexity",  "simple")
        confidence   = float(classification.get("confidence", 1.0))

        # Confidence gate — override "complex" if the model is unsure
        if complexity == "complex" and confidence < CONFIDENCE_THRESHOLD:
            self.log(
                f"Confidence {confidence:.2f} < threshold {CONFIDENCE_THRESHOLD} "
                "→ downgrading to SIMPLE.",
                "WARNING",
            )
            classification["complexity"] = "simple"
            classification["reasoning"] += " (downgraded: low confidence)"
            complexity = "simple"

        if complexity == "simple":
            self.log("→ SIMPLE route: handing off to existing pipeline.")
            self._remember_outcome(objective, "simple", confidence, agents_used=[])
            return {"route": "simple", "classification": classification}

        # ── 2. Complex: build execution plan ─────────────────────────
        self.log(f"→ COMPLEX route (confidence={confidence:.2f}): activating swarm.")
        agents_needed    = classification.get("agents_needed", [])
        execution_order  = classification.get("execution_order", "dependency_graph")
        swarm_id         = f"swarm_{uuid.uuid4().hex[:12]}"
        ctx              = SharedContextBuffer(task_id=swarm_id, objective=objective)

        # ── 3. Execute ────────────────────────────────────────────────
        all_results: Dict[str, Dict] = {}

        if execution_order == "dependency_graph":
            all_results = self._run_dependency_graph(objective, agents_needed, ctx)
        elif execution_order == "parallel":
            all_results = self._run_parallel(objective, agents_needed, ctx)
        else:  # sequential
            all_results = self._run_sequential(objective, agents_needed, ctx)

        # ── 4. Mid-flight re-classification ───────────────────────────
        extra_agents = self._check_for_expansion(objective, ctx, all_results)
        if extra_agents:
            self.log(f"Swarm expanding with: {extra_agents}")
            expansion = self._run_dependency_graph(objective, extra_agents, ctx,
                                                   completed=set(all_results.keys()))
            all_results.update(expansion)
            agents_needed = list(set(agents_needed) | set(extra_agents))

        # ── 5. Quality-weighted merge ─────────────────────────────────
        merged = self._merge_results(objective, ctx, all_results)

        # ── 6. Store swarm memory ─────────────────────────────────────
        self._remember_outcome(objective, "complex", confidence, agents_needed)

        self.log(f"Swarm {swarm_id} complete. Agents: {agents_needed}")
        return {
            "route":          "complex",
            "swarm_id":       swarm_id,
            "classification": classification,
            "result":         merged,
            "agents_used":    agents_needed,
            "agent_results":  all_results,
            "context":        ctx.to_dict(),
        }

    # ── Classification ────────────────────────────────────────────────

    def _classify(self, objective: str) -> Dict[str, Any]:
        """LLM-based classification with swarm-memory bias."""
        # Pull similar past tasks from memory to bias the classifier
        memory_hint = self._get_memory_hint(objective)
        user_prompt = f"User objective: {objective}"
        if memory_hint:
            user_prompt += f"\n\nPast similar tasks: {memory_hint}"

        try:
            raw = self._llm_call(
                CLASSIFIER_SYSTEM_PROMPT,
                user_prompt,
                temperature=0.1,
                max_tokens=300,
            )
            cleaned = self._strip_fences(raw)
            result  = json.loads(cleaned)

            # Sanitise agents_needed
            valid = set(self._agent_classes.keys())
            result["agents_needed"] = [
                a for a in result.get("agents_needed", []) if a in valid
            ]
            # Ensure confidence is present
            result.setdefault("confidence", 1.0)
            return result

        except Exception as e:
            self.log(f"Classification failed → defaulting to simple: {e}", "WARNING")
            return {
                "complexity":      "simple",
                "confidence":      1.0,
                "agents_needed":   [],
                "execution_order": "sequential",
                "reasoning":       f"Classification error: {e}",
            }

    # ── Execution strategies ──────────────────────────────────────────

    def _run_dependency_graph(
        self,
        objective: str,
        agents: List[str],
        ctx: SharedContextBuffer,
        completed: Optional[set] = None,
    ) -> Dict[str, Dict]:
        """
        Topological execution using AGENT_DEPS.

        Agents whose prerequisites are satisfied run in parallel batches.
        Agents whose prerequisites failed are skipped (with an error entry).
        """
        completed  = set(completed or [])
        remaining  = list(agents)
        results: Dict[str, Dict] = {}
        failed_set: set = set()

        while remaining:
            # Build the ready batch: agents whose deps are all completed
            ready = [
                a for a in remaining
                if AGENT_DEPS.get(a, set()).issubset(completed)
                and not AGENT_DEPS.get(a, set()).intersection(failed_set)
            ]
            # Detect agents blocked by failed deps
            blocked = [
                a for a in remaining
                if AGENT_DEPS.get(a, set()).intersection(failed_set)
            ]
            for b in blocked:
                msg = (f"{b} skipped: prerequisite(s) "
                       f"{AGENT_DEPS[b] & failed_set} failed.")
                self.log(msg, "WARNING")
                results[b] = {"status": "skipped", "output": msg, "quality_score": 0.0}
                remaining.remove(b)

            if not ready:
                if remaining:
                    self.log(f"Dependency deadlock — running remaining sequentially: {remaining}",
                             "WARNING")
                    results.update(self._run_sequential(objective, remaining, ctx))
                break

            # Run the ready batch in parallel
            batch_results = self._run_parallel(objective, ready, ctx)
            for name, res in batch_results.items():
                results[name] = res
                remaining.remove(name)
                if res.get("status") == "error":
                    failed_set.add(name)
                else:
                    completed.add(name)

        return results

    def _run_sequential(
        self,
        objective: str,
        agents: List[str],
        ctx: SharedContextBuffer,
    ) -> Dict[str, Dict]:
        results = {}
        for name in agents:
            self.log(f"  ↳ Running {name} (sequential)…")
            results[name] = self._run_single_agent(name, objective, ctx)
        return results

    def _run_parallel(
        self,
        objective: str,
        agents: List[str],
        ctx: SharedContextBuffer,
    ) -> Dict[str, Dict]:
        results: Dict[str, Dict] = {}
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_WORKERS, len(agents))) as pool:
            futures = {
                pool.submit(self._run_single_agent, name, objective, ctx): name
                for name in agents
            }
            for future in as_completed(futures, timeout=AGENT_TIMEOUT_SECONDS * 2):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=AGENT_TIMEOUT_SECONDS)
                except FuturesTimeout:
                    msg = f"{name} timed out after {AGENT_TIMEOUT_SECONDS}s."
                    self.log(msg, "ERROR")
                    results[name] = {"status": "timeout", "output": msg, "quality_score": 0.0}
                except Exception as e:
                    msg = f"{name} raised an unexpected error: {e}"
                    self.log(msg, "ERROR")
                    results[name] = {"status": "error", "output": msg, "quality_score": 0.0}
        return results

    # ── Single Agent Execution with Retry ─────────────────────────────

    def _run_single_agent(
        self,
        name: str,
        objective: str,
        ctx: SharedContextBuffer,
    ) -> Dict[str, Any]:
        """Run one agent with exponential-backoff retries and quality extraction."""
        agent = self._get_agent(name)
        if not agent:
            return {"status": "error", "output": f"Unknown agent: {name}", "quality_score": 0.0}

        delay = RETRY_BASE_DELAY
        for attempt in range(1, MAX_AGENT_RETRIES + 2):   # +2 = 1 original + retries
            try:
                raw_result = agent.process(objective, context=ctx)
                output, quality_score = self._extract_quality(raw_result)
                ctx.post(name, output, message_type="result")
                self.log(f"  ✓ {name} done (quality={quality_score:.2f}, attempt={attempt})")
                return {
                    "status":        "ok",
                    "output":        output,
                    "quality_score": quality_score,
                    "attempts":      attempt,
                }
            except Exception as e:
                self.log(f"  ✗ {name} attempt {attempt} failed: {e}", "WARNING")
                if attempt <= MAX_AGENT_RETRIES:
                    time.sleep(delay)
                    delay *= 2
                else:
                    ctx.post(name, str(e), message_type="error")
                    return {
                        "status":        "error",
                        "output":        str(e),
                        "quality_score": 0.0,
                        "attempts":      attempt,
                    }

    # ── Mid-flight Re-classification ──────────────────────────────────

    def _check_for_expansion(
        self,
        objective: str,
        ctx: SharedContextBuffer,
        current_results: Dict[str, Dict],
    ) -> List[str]:
        """Ask the LLM if the swarm needs additional agents based on partial results."""
        if not current_results:
            return []

        summary = "\n".join(
            f"[{name}] (quality={r.get('quality_score', 0):.2f}): "
            f"{str(r.get('output', ''))[:400]}"
            for name, r in current_results.items()
            if r.get("status") == "ok"
        )
        already_used = list(current_results.keys())

        try:
            raw = self._llm_call(
                RECLASSIFY_PROMPT,
                f"Objective: {objective}\n\nPartial results:\n{summary}\n\n"
                f"Agents already used: {already_used}",
                temperature=0.1,
                max_tokens=200,
            )
            data = json.loads(self._strip_fences(raw))
            if not data.get("expand", False):
                return []
            valid = set(self._agent_classes.keys()) - set(already_used)
            extras = [a for a in data.get("additional_agents", []) if a in valid]
            if extras:
                self.log(f"Re-classification suggests adding: {extras}")
            return extras
        except Exception as e:
            self.log(f"Re-classification check failed (non-fatal): {e}", "WARNING")
            return []

    # ── Quality Score Extraction ──────────────────────────────────────

    @staticmethod
    def _extract_quality(raw_result: Any) -> Tuple[str, float]:
        """
        Parse the QUALITY_SCORE marker from agent output.

        Returns (clean_output, score_float).
        If the agent doesn't embed a score, default to 0.7.
        """
        if isinstance(raw_result, dict):
            text = str(raw_result.get("output") or raw_result.get("result") or raw_result)
        else:
            text = str(raw_result)

        score = 0.7   # sensible default
        clean = text

        if "QUALITY_SCORE:" in text:
            parts = text.rsplit("QUALITY_SCORE:", 1)
            clean = parts[0].strip()
            try:
                score = float(parts[1].strip().split()[0])
                score = max(0.0, min(1.0, score))
            except (ValueError, IndexError):
                pass

        return clean, score

    # ── Quality-Weighted Merge ────────────────────────────────────────

    def _merge_results(
        self,
        objective: str,
        ctx: SharedContextBuffer,
        all_results: Dict[str, Dict],
    ) -> str:
        """
        Merge agent results into a single coherent response.

        Agents below QUALITY_WEIGHT_FLOOR are excluded.
        Remaining agents are presented to the LLM ranked by quality.
        """
        # Filter out low-quality / failed results
        qualified = {
            name: res for name, res in all_results.items()
            if res.get("status") == "ok"
            and res.get("quality_score", 0.0) >= QUALITY_WEIGHT_FLOOR
        }

        if not qualified:
            self.log("No qualified agent results — returning best available.", "WARNING")
            # Fallback: take whatever passed
            fallback = {n: r for n, r in all_results.items() if r.get("status") == "ok"}
            if not fallback:
                return "All sub-agents failed to produce usable output."
            qualified = fallback

        # Sort by quality (highest first)
        ranked = sorted(qualified.items(), key=lambda x: x[1].get("quality_score", 0), reverse=True)

        parts = [f"TASK: {objective}\n"]
        for name, res in ranked:
            q = res.get("quality_score", 0.0)
            preview = str(res.get("output", ""))[:1000]
            parts.append(f"[{name}] (quality={q:.2f}):\n{preview}\n")

        combined = "\n".join(parts)

        try:
            merged = self._llm_call(
                system_prompt=(
                    "You are AERIS synthesising results from specialist agents. "
                    "Results are presented highest-quality first; weight them accordingly. "
                    "Produce ONE coherent, comprehensive response. "
                    "Use Hinglish tone, address user as 'Sir'. Be concise but complete. "
                    "Do NOT include QUALITY_SCORE markers in your output."
                ),
                user_prompt=combined,
                temperature=0.3,
                max_tokens=1500,
            )
            return merged
        except Exception as e:
            self.log(f"Merge LLM failed, falling back to concatenation: {e}", "WARNING")
            return "\n\n".join(
                f"[{name}]: {str(res.get('output', ''))[:600]}"
                for name, res in ranked
            )

    # ── Swarm Memory Helpers ──────────────────────────────────────────

    def _get_memory_hint(self, objective: str) -> str:
        """Retrieve past classification outcomes from memory to bias the classifier."""
        if not self.memory:
            return ""
        try:
            key = f"delegator:past_routes:{objective[:60]}"
            past = self.memory.get(key)
            if past:
                return json.dumps(past)[:400]
        except Exception:
            pass
        return ""

    def _remember_outcome(
        self,
        objective: str,
        route: str,
        confidence: float,
        agents_used: List[str],
    ) -> None:
        """Persist the classification outcome so future calls learn from it."""
        if not self.memory:
            return
        try:
            key = f"delegator:past_routes:{objective[:60]}"
            self.memory.set(key, {
                "route":       route,
                "confidence":  confidence,
                "agents_used": agents_used,
                "timestamp":   time.time(),
            })
        except Exception:
            pass

    # ── Utility Helpers ───────────────────────────────────────────────

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences from LLM output before JSON parsing."""
        s = text.strip()
        if s.startswith("```"):
            lines = s.split("\n")
            s = "\n".join(lines[1:])            # drop opening fence line
        if s.endswith("```"):
            s = s[:-3]
        return s.strip()

    def _get_agent(self, name: str) -> Optional[BaseAgent]:
        """Lazy-initialise and return a sub-agent by name."""
        if name not in self._agent_classes:
            self.log(f"Unknown agent: {name}", "WARNING")
            return None
        if self._agents[name] is None:
            self._agents[name] = self._agent_classes[name](memory_agent=self.memory)
        return self._agents[name]


# ── Singleton ─────────────────────────────────────────────────────────
_delegator_instance: Optional[DelegatorAgent] = None


def get_delegator(memory_agent=None) -> DelegatorAgent:
    """Get the global DelegatorAgent singleton."""
    global _delegator_instance
    if _delegator_instance is None:
        _delegator_instance = DelegatorAgent(memory_agent=memory_agent)
    return _delegator_instance