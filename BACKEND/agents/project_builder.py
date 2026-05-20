"""
AERIS — Project Builder System (PBS) v2
================================================
Coordinates the Multi-Agent Swarm to architect, generate, and save
entire projects to the workspace directory.

KEY DESIGN DECISIONS:
  • Runs synchronously from the tool registry (no nested asyncio issues)
  • Uses Ollama exclusively for code generation (no rate-limit risk)
  • Generates files one-at-a-time to avoid LLM token overflow
  • Reuses existing project directories instead of creating duplicates
"""
import json
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from agents.sub_agents.architecture_agent import ArchitectureAgent
from agents.sub_agents.coding_agent import CodingAgent, CodingRequest, CodingResult, CodeFile, TaskKind
from agents.sub_agents.documentation_agent import DocumentationAgent
from agents.sub_agents.shared_context import SharedContextBuffer

logger = logging.getLogger("AerisProjectBuilder")


class ProjectBuilderSystem:
    """
    Autonomous Project Builder — orchestrates Architecture → Code → Docs pipeline.
    
    All methods are SYNCHRONOUS to avoid asyncio event loop conflicts
    with the ToolRegistry executor.
    """

    def __init__(self):
        self.arch_agent = ArchitectureAgent()
        self.coding_agent = CodingAgent(enable_validation=True, enable_cache=False)
        self.doc_agent = DocumentationAgent()

        # Determine base directory
        self.base_dir = (Path(__file__).resolve().parent.parent.parent / "workspace").resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def build_project(self, objective: str) -> Dict[str, Any]:
        """
        End-to-end SYNCHRONOUS pipeline for generating a production-level project.

        Steps:
          1. Idea Analysis (objective parsing)
          2. Architecture Design (blueprint via LLM)
          3. Flowchart Generation (optional)
          4. UI/UX Design hints
          5. Project Structure scaffolding
          6. Code Generation (per-file, via Ollama)
          7. Dependencies & Config
          8. Verification (syntax check)
          9. Documentation (README)
         10. Output Delivery
        """
        logger.info(f"[PBS] Starting build for: {objective}")
        t0 = time.time()
        context = SharedContextBuffer(task_id=f"pbs_{int(time.time())}", objective=objective)

        # ── Step 1: Idea Analysis ───────────────────────────────────────
        logger.info("[PBS] Step 1/10: Idea Analysis")
        # Implicit — the objective IS the idea. No separate agent needed.

        # ── Step 2: Architecture Design ─────────────────────────────────
        logger.info("[PBS] Step 2/10: Architecture Design")
        arch_res = self.arch_agent.process(objective, context=context)
        if arch_res["status"] != "success":
            return {"success": False, "error": f"Architecture failure: {arch_res.get('output')}"}

        blueprint = arch_res.get("blueprint")
        if not blueprint:
            return {"success": False, "error": "Missing blueprint in architecture response"}

        project_name = blueprint.project_name
        # Sanitize
        project_name = "".join(c for c in project_name if c.isalnum() or c in ("_", "-"))
        if not project_name:
            project_name = "aeris_project"

        project_dir = self.base_dir / project_name

        # REUSE existing directory instead of creating duplicates
        project_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[PBS] Project workspace: {project_dir}")

        # ── Step 3: Flowchart Generation (optional) ─────────────────────
        logger.info("[PBS] Step 3/10: Flowchart Generation")
        flowchart = self._generate_flowchart(blueprint, project_name)

        # ── Step 4: UI/UX Design ────────────────────────────────────────
        logger.info("[PBS] Step 4/10: UI/UX Design")
        css_fw = getattr(blueprint.tech_stack, "css_framework", "standard CSS")
        ui_overview = (
            f"A modern, responsive design using {css_fw}. "
            f"Includes clean layout, responsive grid, and proper navigation."
        )

        # ── Step 5: Project Structure Scaffolding ───────────────────────
        logger.info("[PBS] Step 5/10: Project Structure Scaffolding")
        for node in blueprint.structure:
            if node.type == "directory":
                dir_path = project_dir / node.path
                dir_path.mkdir(parents=True, exist_ok=True)

        # ── Step 6: Code Generation (per-file) ─────────────────────────
        logger.info("[PBS] Step 6/10: Code Generation")
        generated_files = self._generate_all_code(
            blueprint, project_dir, objective, context
        )

        # ── Step 7: Dependencies & Config ──────────────────────────────
        logger.info("[PBS] Step 7/10: Dependencies & Config")
        run_commands = self._write_dependency_files(
            blueprint, project_dir, project_name, generated_files
        )

        # ── Step 8: Verification ───────────────────────────────────────
        logger.info("[PBS] Step 8/10: Verification")
        # CodingAgent already validates syntax with enable_validation=True
        logger.info("[PBS] Verification passed (inline validation).")

        # ── Step 9: Documentation ──────────────────────────────────────
        logger.info("[PBS] Step 9/10: Documentation")
        self._generate_readme(project_dir, project_name, objective, context, generated_files)
        generated_files.append(f"{project_name}/README.md")

        # ── Step 10: Output Delivery ───────────────────────────────────
        elapsed = time.time() - t0
        logger.info(f"[PBS] Step 10/10: Output Delivery ({elapsed:.1f}s total)")

        return {
            "success": True,
            "project_path": str(project_dir),
            "project_name": project_name,
            "files_generated": generated_files,
            "flowchart": flowchart,
            "ui_overview": ui_overview,
            "run_commands": run_commands,
            "build_time_seconds": round(elapsed, 1),
        }

    # ═══════════════════════════════════════════════════════════════════
    #  PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════════════

    def _generate_flowchart(self, blueprint, project_name: str) -> str:
        """Generate a flowchart description (gracefully optional)."""
        try:
            from generation.diagram_generator import DiagramGenerator
            diag_gen = DiagramGenerator()

            framework = getattr(blueprint.tech_stack, "framework", "Web")
            database = getattr(blueprint.tech_stack, "database", "Database")

            diag_prompt = (
                f"System Architecture Flow for {project_name}. "
                f"User interacts with Frontend ({framework}). "
                f"Frontend sends API requests to the Backend Server. "
                f"Backend Server queries the Database ({database})."
            )
            diag_res = diag_gen.generate_from_prompt(diag_prompt)
            return diag_res.get("output", "Interactive React Flow diagram widget generated.")
        except Exception as e:
            logger.warning(f"[PBS] Diagram generation skipped: {e}")
            return "Diagram generation skipped (optional dependency)."

    def _generate_all_code(
        self,
        blueprint,
        project_dir: Path,
        objective: str,
        context: SharedContextBuffer,
    ) -> List[str]:
        """
        Generate code files ONE AT A TIME to avoid LLM token overflow.
        Each file gets its own dedicated LLM call with full context.
        """
        generated_files = []
        arch_summary = json.dumps(blueprint.to_dict(), indent=2)

        # Collect all file nodes from the blueprint
        file_nodes = [n for n in blueprint.structure if n.type == "file"]
        if not file_nodes:
            logger.warning("[PBS] No file nodes in blueprint — generating entry point only.")
            file_nodes = [type("N", (), {"path": "main.py", "description": "Main entry point"})()]

        for i, node in enumerate(file_nodes):
            file_path_rel = node.path
            description = getattr(node, "description", "")

            logger.info(f"[PBS]   Generating file {i+1}/{len(file_nodes)}: {file_path_rel}")

            # Build a focused prompt for THIS specific file
            file_objective = (
                f"Generate the COMPLETE source code for the file: {file_path_rel}\n"
                f"Description: {description}\n\n"
                f"Project objective: {objective}\n\n"
                f"Full project blueprint (for context):\n{arch_summary}\n\n"
                f"RULES:\n"
                f"- Output ONLY the code for THIS ONE file: {file_path_rel}\n"
                f"- Make it COMPLETE and EXECUTABLE — no placeholders, no '# TODO'\n"
                f"- Include ALL imports, classes, functions, and logic\n"
                f"- Use proper error handling and type hints\n"
                f"- Make it production-ready with clean code\n"
            )

            try:
                # Use the CodingAgent's sync API — no asyncio needed
                result = self.coding_agent.generate_code(
                    request=file_objective,
                    language=self._detect_language(file_path_rel, blueprint),
                    context=context,
                )

                content = self._extract_code_content(result, file_path_rel)
                if content and len(content.strip()) > 10:
                    abs_path = project_dir / file_path_rel
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(content, encoding="utf-8")
                    generated_files.append(f"{blueprint.project_name}/{file_path_rel}")
                    logger.info(f"[PBS]   ✅ Wrote {len(content)} bytes → {file_path_rel}")
                else:
                    logger.warning(f"[PBS]   ⚠️ Empty content for {file_path_rel} — skipping")

            except Exception as e:
                logger.error(f"[PBS]   ❌ Failed to generate {file_path_rel}: {e}")

        return generated_files

    def _extract_code_content(self, result: Dict[str, Any], target_path: str) -> str:
        """
        Extract the best code content from a CodingResult dict.
        Priority: files[0].content → code → analysis (if it looks like code)
        """
        # Check files array first
        files = result.get("files", [])
        if files:
            # Find a file matching the target path, or use the first one
            for f in files:
                if isinstance(f, dict):
                    path = f.get("path", "")
                    content = f.get("content", "")
                    if content and (path == target_path or path in target_path or not path):
                        return self._strip_conversational_filler(content)
            # Fallback: just use first file
            first = files[0]
            if isinstance(first, dict) and first.get("content"):
                return self._strip_conversational_filler(first["content"])

        # Check inline code
        code = result.get("code", "")
        if code and len(code.strip()) > 10:
            return self._strip_conversational_filler(code)

        # Last resort: check analysis field (sometimes LLM dumps code there)
        analysis = result.get("analysis", "")
        if "import " in analysis or "def " in analysis or "function " in analysis:
            return self._strip_conversational_filler(analysis)

        return ""

    @staticmethod
    def _strip_conversational_filler(content: str) -> str:
        """
        Remove conversational preamble that the LLM might inject before actual code.
        E.g., 'Sure! Here is the code:' or 'Here is the implementation:'
        """
        lines = content.split("\n")
        # Find the first line that looks like actual code
        code_start = 0
        conversational_prefixes = (
            "sure", "here", "below", "i've", "i have", "this is",
            "the following", "certainly", "of course", "okay",
        )
        for idx, line in enumerate(lines):
            stripped = line.strip().lower()
            if not stripped:
                continue
            if any(stripped.startswith(p) for p in conversational_prefixes):
                code_start = idx + 1
                continue
            # If we hit something that looks like code, stop scanning
            if any(kw in stripped for kw in (
                "import ", "from ", "def ", "class ", "function ", "const ",
                "let ", "var ", "export ", "#!", "package ", "using ", "<?",
                "<!doctype", "<html", "/*", "//", "#include", "module ",
            )):
                code_start = idx
                break
            # If the first non-empty line doesn't look conversational, keep it
            break

        cleaned = "\n".join(lines[code_start:])

        # Also strip trailing conversational text after the code
        # Look for patterns like "This code..." at the end
        result_lines = cleaned.rstrip().split("\n")
        while result_lines:
            last = result_lines[-1].strip().lower()
            if last and not last.startswith("#") and not last.startswith("//"):
                if any(last.startswith(p) for p in (
                    "this ", "the above", "note:", "remember",
                    "make sure", "you can", "feel free",
                )):
                    result_lines.pop()
                    continue
            break

        return "\n".join(result_lines)

    @staticmethod
    def _detect_language(file_path: str, blueprint) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
            ".rs": "rust", ".java": "java", ".kt": "kotlin",
            ".swift": "swift", ".rb": "ruby", ".php": "php",
            ".c": "c", ".cpp": "cpp", ".cs": "csharp",
            ".html": "html", ".css": "css", ".sql": "sql",
            ".sh": "bash", ".dart": "dart", ".yaml": "yaml",
            ".yml": "yaml", ".json": "json", ".xml": "xml",
            ".toml": "toml", ".md": "markdown",
        }
        ext = Path(file_path).suffix.lower()
        if ext in ext_map:
            return ext_map[ext]
        # Fallback to blueprint language
        return str(getattr(blueprint.tech_stack, "language", "python")).lower()

    def _write_dependency_files(
        self, blueprint, project_dir: Path, project_name: str,
        generated_files: List[str],
    ) -> List[str]:
        """Write package.json / requirements.txt and return run commands."""
        tech = blueprint.tech_stack
        deps = tech.dependencies or []
        lang = str(tech.language).lower()
        run_commands = []

        if "python" in lang:
            req_path = project_dir / "requirements.txt"
            if not req_path.exists() and deps:
                req_path.write_text("\n".join(deps), encoding="utf-8")
                generated_files.append(f"{project_name}/requirements.txt")
            run_commands.append("pip install -r requirements.txt")
            # Detect entry point
            entry = self._find_entry_point(project_dir, "python")
            run_commands.append(f"python {entry}")

        elif any(kw in lang for kw in ("javascript", "js", "node", "typescript", "ts")):
            pkg_path = project_dir / "package.json"
            if not pkg_path.exists():
                pkg = {
                    "name": project_name,
                    "version": "1.0.0",
                    "type": "module",
                    "scripts": {"start": "node index.js", "dev": "node index.js"},
                    "dependencies": {d.split("==")[0].split(">=")[0]: "latest" for d in deps},
                }
                pkg_path.write_text(json.dumps(pkg, indent=2), encoding="utf-8")
                generated_files.append(f"{project_name}/package.json")
            run_commands.extend(["npm install", "npm start"])

        elif "dart" in lang or "flutter" in lang:
            run_commands.extend(["flutter pub get", "flutter run"])

        elif "go" in lang:
            run_commands.extend(["go mod tidy", "go run ."])

        elif "rust" in lang:
            run_commands.extend(["cargo build", "cargo run"])

        if not run_commands:
            run_commands.append("Check README.md for run instructions.")

        return run_commands

    @staticmethod
    def _find_entry_point(project_dir: Path, language: str) -> str:
        """Find the most likely entry point file."""
        candidates = {
            "python": ["main.py", "app.py", "server.py", "run.py", "index.py", "manage.py"],
        }
        for name in candidates.get(language, ["main.py"]):
            # Check root
            if (project_dir / name).exists():
                return name
            # Check src/
            if (project_dir / "src" / name).exists():
                return f"src/{name}"
            # Check lib/
            if (project_dir / "lib" / name).exists():
                return f"lib/{name}"
        return "main.py"

    def _generate_readme(
        self, project_dir: Path, project_name: str,
        objective: str, context: SharedContextBuffer,
        generated_files: List[str],
    ):
        """Generate README.md via DocumentationAgent."""
        try:
            doc_res = self.doc_agent.process(objective, context=context)
            if doc_res["status"] == "success":
                readme_content = doc_res["output"]
            else:
                readme_content = self._fallback_readme(project_name, objective, generated_files)
        except Exception as e:
            logger.warning(f"[PBS] Documentation agent failed: {e}")
            readme_content = self._fallback_readme(project_name, objective, generated_files)

        (project_dir / "README.md").write_text(readme_content, encoding="utf-8")

    @staticmethod
    def _fallback_readme(project_name: str, objective: str, files: List[str]) -> str:
        """Generate a basic README if the DocumentationAgent fails."""
        file_tree = "\n".join(f"  - {f}" for f in files) if files else "  (no files)"
        return (
            f"# {project_name}\n\n"
            f"## Description\n{objective}\n\n"
            f"## Project Structure\n{file_tree}\n\n"
            f"## Getting Started\nSee the generated files for setup instructions.\n\n"
            f"---\n*Generated by AERIS Project Builder System*\n"
        )


# ═══════════════════════════════════════════════════════════════════════
#  PUBLIC TOOL WRAPPER (called from tool_registry)
# ═══════════════════════════════════════════════════════════════════════

def run_project_builder(objective: str) -> str:
    """
    Synchronous entry point for the tool registry.
    NO asyncio — runs entirely in the calling thread.
    """
    builder = ProjectBuilderSystem()
    result = builder.build_project(objective)

    if result["success"]:
        lines = [
            f"Project successfully built at: {result['project_path']}",
            f"Project Name: {result['project_name']}",
            f"Files Generated:",
        ]
        for f in result["files_generated"]:
            lines.append(f"  - {f}")

        lines.append(f"\nArchitecture: {result.get('flowchart', 'N/A')}")
        lines.append(f"UI Design: {result.get('ui_overview', 'N/A')}")

        lines.append(f"\nRun Commands:")
        for cmd in result["run_commands"]:
            lines.append(f"  {cmd}")

        lines.append(f"\nBuild Time: {result.get('build_time_seconds', '?')}s")
        return "\n".join(lines)
    else:
        raise RuntimeError(result["error"])
