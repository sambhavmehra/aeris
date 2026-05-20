"""
AERIS — Planner Agent
=====================
Thinks deeply about a user's objective and produces a structured
workspace manifest (project name, file list, tech stack, entry point,
run command).  This manifest is consumed by the CodingAgent to write
every file, then by the VerifierAgent to validate the result.

Part of the autonomous Planner → Coder → Verifier pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base_agent import BaseAgent
from ai_engine import ai_engine

logger = logging.getLogger("aeris.planner_agent")


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FileSpec:
    """Describes a single file to be generated."""
    path: str
    description: str
    language: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {"path": self.path, "description": self.description, "language": self.language}


@dataclass
class WorkspaceManifest:
    """Full blueprint produced by the PlannerAgent."""
    project_name: str
    language: str
    tech_stack: List[str]
    entry_point: str
    files: List[FileSpec]
    run_command: str
    reasoning: str
    directories: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "language": self.language,
            "tech_stack": self.tech_stack,
            "entry_point": self.entry_point,
            "files": [f.to_dict() for f in self.files],
            "run_command": self.run_command,
            "reasoning": self.reasoning,
            "directories": self.directories,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────

PLANNER_SYSTEM_PROMPT = """\
You are AERIS's Project Planner — an expert software architect embedded in a
multi-agent autonomous coding system.

Your job: given a user's objective, design a COMPLETE workspace manifest that
another agent will use to generate every source file.

RULES:
1. Output ONLY valid JSON — no markdown, no prose, no explanations outside JSON.
2. Choose the most appropriate language & framework for the objective.
3. Include ALL files needed for a working project (source, config, deps).
4. Each file MUST have a clear, actionable description of what it should contain.
5. The entry_point must be a file that can be executed to run the project.
6. The run_command must work from the project root directory.
7. Keep projects focused — 3-8 files for simple apps, up to 15 for complex ones.
8. Include a requirements.txt / package.json as appropriate.

OUTPUT SCHEMA (return exactly this JSON shape):
{
  "project_name": "<snake_case name>",
  "language": "<primary language>",
  "tech_stack": ["<framework>", "<lib1>", ...],
  "entry_point": "<main file path>",
  "files": [
    {"path": "<relative path>", "description": "<what this file should contain>", "language": "<lang>"}
  ],
  "directories": ["<dir1>", "<dir2>"],
  "run_command": "<command to run the project>",
  "reasoning": "<brief explanation of architectural decisions>"
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Agent
# ─────────────────────────────────────────────────────────────────────────────

class PlannerAgent(BaseAgent):
    """
    Autonomous Planner Agent — analyses an objective and produces a
    WorkspaceManifest with the full project blueprint.
    """

    def __init__(self):
        super().__init__(
            name="PlannerAgent",
            description="Designs workspace blueprints for autonomous code generation.",
            task_domain="planning",
            version="1.0.0",
            capabilities=[
                "Project Architecture Design",
                "Tech Stack Selection",
                "File Structure Planning",
                "Dependency Analysis",
            ],
        )
        self.base_dir = (Path(__file__).resolve().parent.parent.parent / "workspace").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── BaseAgent interface ──────────────────────────────────────────────

    async def think(self, message: str, context: dict) -> Any:
        """Analyse the objective and return a WorkspaceManifest."""
        return await self.plan_workspace(message)

    async def execute(self, plan: Any) -> Any:
        """Create workspace directories on disk from the manifest."""
        if isinstance(plan, WorkspaceManifest):
            return self.scaffold_workspace(plan)
        return plan

    async def report(self, results: Any) -> str:
        """Format the manifest into a human-readable summary."""
        if isinstance(results, dict) and "manifest" in results:
            m = results["manifest"]
            files_list = "\n".join(f"  • {f['path']} — {f['description']}" for f in m.get("files", []))
            return (
                f"📐 **Workspace Planned: {m['project_name']}**\n"
                f"Language: {m['language']} | Stack: {', '.join(m.get('tech_stack', []))}\n"
                f"Entry: `{m['entry_point']}` | Run: `{m['run_command']}`\n\n"
                f"**Files:**\n{files_list}\n\n"
                f"**Reasoning:** {m.get('reasoning', 'N/A')}"
            )
        return str(results)

    # ── Core planning logic ──────────────────────────────────────────────

    async def plan_workspace(self, objective: str) -> WorkspaceManifest:
        """
        Call the LLM to produce a structured workspace manifest from a
        free-form objective string.
        """
        logger.info(f"[PlannerAgent] Planning workspace for: {objective[:100]}")

        user_prompt = (
            f"Design a complete project workspace for the following objective:\n\n"
            f"OBJECTIVE: {objective}\n\n"
            f"Think carefully about the best architecture, then output the JSON manifest."
        )

        raw = await ai_engine.chat(
            messages=[
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.25,
            max_tokens=2048,
            response_format={"type": "json_object"}
        )

        manifest = self._parse_manifest(raw, objective)
        logger.info(
            f"[PlannerAgent] Manifest ready: {manifest.project_name} "
            f"({len(manifest.files)} files, {manifest.language})"
        )
        return manifest

    def scaffold_workspace(self, manifest: WorkspaceManifest) -> Dict[str, Any]:
        """
        Create the project directory and all sub-directories on disk.
        Returns metadata about the created workspace.
        """
        project_dir = self.base_dir / manifest.project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        # Create declared directories
        for d in manifest.directories:
            (project_dir / d).mkdir(parents=True, exist_ok=True)

        # Create parent directories for all files
        for f in manifest.files:
            parent = (project_dir / f.path).parent
            parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"[PlannerAgent] Workspace scaffolded at: {project_dir}")

        return {
            "project_path": str(project_dir),
            "project_name": manifest.project_name,
            "manifest": manifest.to_dict(),
        }

    # ── Parsing ──────────────────────────────────────────────────────────

    def _parse_manifest(self, raw: str, objective: str) -> WorkspaceManifest:
        """Parse LLM output into a WorkspaceManifest, with fallback."""
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:])
            if cleaned.rstrip().endswith("```"):
                cleaned = cleaned.rstrip()[:-3].strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("[PlannerAgent] JSON parse failed, using fallback manifest.")
            return self._fallback_manifest(objective)

        # Sanitise project name
        project_name = data.get("project_name", "aeris_project")
        project_name = "".join(c for c in project_name if c.isalnum() or c in ("_", "-"))
        if not project_name:
            project_name = "aeris_project"

        files = []
        for f in data.get("files", []):
            if isinstance(f, dict) and f.get("path"):
                files.append(FileSpec(
                    path=f["path"],
                    description=f.get("description", ""),
                    language=f.get("language", ""),
                ))

        if not files:
            return self._fallback_manifest(objective)

        return WorkspaceManifest(
            project_name=project_name,
            language=data.get("language", "python"),
            tech_stack=data.get("tech_stack", []),
            entry_point=data.get("entry_point", files[0].path),
            files=files,
            run_command=data.get("run_command", f"python {files[0].path}"),
            reasoning=data.get("reasoning", ""),
            directories=data.get("directories", []),
        )

    @staticmethod
    def _fallback_manifest(objective: str) -> WorkspaceManifest:
        """Generate a minimal fallback manifest when LLM parsing fails."""
        return WorkspaceManifest(
            project_name="aeris_project",
            language="python",
            tech_stack=["python3"],
            entry_point="main.py",
            files=[
                FileSpec(path="main.py", description=f"Main entry point: {objective}", language="python"),
                FileSpec(path="requirements.txt", description="Python dependencies", language="text"),
            ],
            run_command="python main.py",
            reasoning="Fallback: LLM output could not be parsed.",
            directories=[],
        )
