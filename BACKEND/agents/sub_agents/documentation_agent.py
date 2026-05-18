"""
AERIS — Documentation Agent
Responsible for writing project READMEs, setup instructions, and inline documentation.
"""

import re
import logging
from typing import Any, Dict, Optional, Tuple

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
CODE_SUMMARY_MAX_CHARS: int = 1_500
DEFAULT_QUALITY_SCORE: float = 0.90
QUALITY_SCORE_PATTERN = re.compile(r"QUALITY_SCORE:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)

DOC_SYSTEM_PROMPT = """\
You are AERIS's Documentation Agent.
Your job is to generate a comprehensive, professional README.md for a newly generated project.

The README MUST include the following sections (skip any section only if the information is
genuinely unavailable — do NOT invent details):

1. Project Title & Description
2. Architecture & Tech Stack
3. Folder Structure
4. Setup & Installation Instructions
5. How to Run the Project

Rules:
- Use clean Markdown formatting.
- Be precise and factual; never hallucinate file names, commands, or dependencies.
- At the very end of your response, on its own line, output a self-assessed quality score:

QUALITY_SCORE: 0.95
"""


# ── Agent ────────────────────────────────────────────────────────────────────
class DocumentationAgent(BaseAgent):
    """Generates project README and inline documentation from shared context."""

    def __init__(
        self,
        memory_agent=None,
        fallback_score: float = DEFAULT_QUALITY_SCORE,
    ) -> None:
        super().__init__(name="DocumentationAgent", memory_agent=memory_agent)
        self.fallback_score = max(0.0, min(1.0, fallback_score))

    # ── Public API ────────────────────────────────────────────────────────────
    def process(
        self,
        objective: str,
        context: Optional[SharedContextBuffer] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        logger.info("[%s] Generating documentation…", self.name)

        user_prompt = self._build_user_prompt(objective, context)

        try:
            raw = self._llm_call(
                DOC_SYSTEM_PROMPT,
                user_prompt,
                temperature=0.3,
                max_tokens=2_048,
            )
        except Exception as exc:
            logger.exception("[%s] LLM call failed.", self.name)
            return {"status": "error", "output": str(exc), "quality_score": 0.0}

        content, score = self._parse_llm_output(raw)

        if context:
            context.post(
                sender=self.name,
                content=content,
                message_type="result",
                task="documentation",
            )

        logger.info("[%s] Documentation complete (quality_score=%.2f).", self.name, score)
        return {"status": "success", "output": content, "quality_score": score}

    # ── Private helpers ───────────────────────────────────────────────────────
    def _build_user_prompt(
        self,
        objective: str,
        context: Optional[SharedContextBuffer],
    ) -> str:
        parts: list[str] = [f"OBJECTIVE: {objective}"]

        if context:
            arch = context.get_latest_result("ArchitectureAgent")
            if arch:
                parts.append(f"PROJECT BLUEPRINT:\n{arch}")

            code = context.get_latest_result("CodingAgent")
            if code:
                summary = str(code)[:CODE_SUMMARY_MAX_CHARS]
                parts.append(f"GENERATED CODE SUMMARY:\n{summary}")

        return "\n\n".join(parts)

    def _parse_llm_output(self, raw: str) -> Tuple[str, float]:
        """
        Splits the raw LLM response into (content, quality_score).
        Falls back to `self.fallback_score` if no valid score is found.
        """
        match = QUALITY_SCORE_PATTERN.search(raw)
        if match:
            content = raw[: match.start()].strip()
            try:
                score = float(match.group(1))
                score = max(0.0, min(1.0, score))   # clamp to valid range
            except ValueError:
                logger.warning("[%s] Could not parse quality score; using fallback.", self.name)
                score = self.fallback_score
        else:
            logger.warning("[%s] QUALITY_SCORE token not found; using fallback.", self.name)
            content = raw.strip()
            score = self.fallback_score

        return content, score