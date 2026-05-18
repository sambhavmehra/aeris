"""
AERIS — Architecture Agent
Responsible for designing project blueprints (folder structure, files, tech stack).
"""
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from agents.base_agent import BaseAgent
from agents.sub_agents.shared_context import SharedContextBuffer

# ── Types ──────────────────────────────────────────────────────────────────────

ProjectType = Literal["web_app", "api", "mobile", "cli", "ai", "library", "data_pipeline"]

@dataclass
class StructureNode:
    path: str
    type: Literal["file", "directory"]
    description: str

@dataclass
class TechStack:
    language: str
    framework: str
    dependencies: List[str] = field(default_factory=list)

@dataclass
class ProjectBlueprint:
    project_name: str
    project_type: ProjectType
    tech_stack: TechStack
    structure: List[StructureNode]
    quality_score: float = 0.9

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectBlueprint":
        tech = data["tech_stack"]
        return cls(
            project_name=data["project_name"],
            project_type=data["project_type"],
            tech_stack=TechStack(
                language=tech["language"],
                framework=tech["framework"],
                dependencies=tech.get("dependencies", []),
            ),
            structure=[
                StructureNode(
                    path=node["path"],
                    type=node["type"],
                    description=node.get("description", ""),
                )
                for node in data.get("structure", [])
            ],
            quality_score=float(data.get("QUALITY_SCORE", 0.9)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "project_type": self.project_type,
            "tech_stack": {
                "language": self.tech_stack.language,
                "framework": self.tech_stack.framework,
                "dependencies": self.tech_stack.dependencies,
            },
            "structure": [
                {"path": n.path, "type": n.type, "description": n.description}
                for n in self.structure
            ],
            "QUALITY_SCORE": self.quality_score,
        }

# ── Prompt ─────────────────────────────────────────────────────────────────────

ARCHITECTURE_SYSTEM_PROMPT = """You are AERIS's Architecture Agent.
Design a complete, production-ready project blueprint based on the user's objective.

Output MUST be a single valid JSON object — no markdown, no commentary — matching this schema exactly:
{
    "project_name": "snake_case_name",
    "project_type": "web_app | api | mobile | cli | ai | library | data_pipeline",
    "tech_stack": {
        "language": "...",
        "framework": "...",
        "dependencies": ["pkg==version", "..."]
    },
    "structure": [
        {"path": "src/main.py",   "type": "file",      "description": "Entry point"},
        {"path": "src/utils",     "type": "directory",  "description": "Shared utilities"}
    ],
    "QUALITY_SCORE": 0.95
}

Rules:
- project_name must be snake_case, no spaces.
- dependencies must include version pins where possible.
- structure must include at minimum: entry point, config, tests directory, and README.
- QUALITY_SCORE reflects blueprint completeness and coherence (0.0–1.0).
- Return ONLY the JSON object. No prose, no markdown fences.
"""

# ── Agent ──────────────────────────────────────────────────────────────────────

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)```\s*$", re.DOTALL)

REQUIRED_BLUEPRINT_KEYS = {"project_name", "project_type", "tech_stack", "structure"}
VALID_PROJECT_TYPES = {"web_app", "api", "mobile", "cli", "ai", "library", "data_pipeline"}


class ArchitectureAgent(BaseAgent):
    """Designs a complete project blueprint from a plain-English objective."""

    MAX_RETRIES = 2

    def __init__(self, memory_agent=None):
        super().__init__(name="ArchitectureAgent", memory_agent=memory_agent)

    # ── BaseAgent Abstract Methods ─────────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        return message

    async def execute(self, plan: Any) -> Any:
        return self.process(plan)

    async def report(self, results: Any) -> str:
        if isinstance(results, dict):
            return results.get("output", str(results))
        return str(results)

    # ── Public API ─────────────────────────────────────────────────────────────

    def process(
        self,
        objective: str,
        context: Optional[SharedContextBuffer] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Design a project blueprint for *objective*.

        Returns a result dict with keys:
            status        : "success" | "error"
            output        : Pretty-printed JSON string of the blueprint
            blueprint     : ProjectBlueprint instance  (only on success)
            quality_score : float
            error         : str  (only on error)
        """
        if not objective or not objective.strip():
            return self._error_result("Objective must not be empty.")

        self.log(f"Designing architecture for: {objective[:120]!r}")

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                blueprint = self._generate_blueprint(objective, attempt)
                result = self._build_success_result(blueprint)
                self._post_to_context(context, blueprint)
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                self.log(
                    f"Attempt {attempt}/{self.MAX_RETRIES} failed — {type(exc).__name__}: {exc}",
                    "WARNING",
                )
                last_exc = exc

        self.log("All retries exhausted.", "ERROR")
        return self._error_result(str(last_exc))

    # ── Private helpers ────────────────────────────────────────────────────────

    def _generate_blueprint(self, objective: str, attempt: int) -> ProjectBlueprint:
        """Call the LLM, strip fences, parse JSON, validate, and return a typed blueprint."""
        hint = "" if attempt == 1 else "\n[IMPORTANT: Return ONLY a valid JSON object, no markdown.]"
        raw = self._llm_call(
            ARCHITECTURE_SYSTEM_PROMPT,
            f"OBJECTIVE: {objective}{hint}",
            temperature=0.2,
            max_tokens=2048,
        )
        data = self._parse_json(raw)
        self._validate(data)
        return ProjectBlueprint.from_dict(data)

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        """Strip optional markdown fences then parse JSON."""
        cleaned = text.strip()
        match = _JSON_FENCE_RE.match(cleaned)
        if match:
            cleaned = match.group(1).strip()
        return json.loads(cleaned)

    @staticmethod
    def _validate(data: Dict[str, Any]) -> None:
        """Raise ValueError for any schema violation."""
        missing = REQUIRED_BLUEPRINT_KEYS - data.keys()
        if missing:
            raise ValueError(f"Blueprint missing required keys: {missing}")

        project_type = data.get("project_type", "")
        if project_type not in VALID_PROJECT_TYPES:
            raise ValueError(
                f"Invalid project_type {project_type!r}. "
                f"Must be one of {VALID_PROJECT_TYPES}."
            )

        tech = data.get("tech_stack", {})
        for field_name in ("language", "framework"):
            if not tech.get(field_name):
                raise ValueError(f"tech_stack.{field_name} is missing or empty.")

        structure = data.get("structure", [])
        if not structure:
            raise ValueError("Blueprint structure must not be empty.")

        for node in structure:
            if node.get("type") not in ("file", "directory"):
                raise ValueError(
                    f"Structure node {node.get('path')!r} has invalid type {node.get('type')!r}."
                )

        score = data.get("QUALITY_SCORE", 0.0)
        if not (0.0 <= float(score) <= 1.0):
            raise ValueError(f"QUALITY_SCORE {score} is out of range [0, 1].")

    @staticmethod
    def _build_success_result(blueprint: ProjectBlueprint) -> Dict[str, Any]:
        return {
            "status": "success",
            "output": json.dumps(blueprint.to_dict(), indent=2),
            "blueprint": blueprint,
            "quality_score": blueprint.quality_score,
        }

    def _post_to_context(
        self, context: Optional[SharedContextBuffer], blueprint: ProjectBlueprint
    ) -> None:
        if context:
            context.post(
                sender=self.name,
                content=blueprint.to_dict(),
                message_type="result",
                task="architecture_blueprint",
            )

    @staticmethod
    def _error_result(message: str) -> Dict[str, Any]:
        return {
            "status": "error",
            "output": message,
            "error": message,
            "quality_score": 0.0,
        }