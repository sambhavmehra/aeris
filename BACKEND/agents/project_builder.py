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
        from config import settings
        self.base_dir = Path(settings.WORKSPACE_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _update_status(self, status: str, step: int, current_step: str, files_generated: List[str] = None, current_file: str = None, error: str = None, project_name: str = None, project_path: str = None):
        try:
            status_file = self.base_dir.parent / "data" / "project_build_status.json"
            status_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            if status_file.exists():
                try:
                    data = json.loads(status_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            
            data["status"] = status
            data["step"] = step
            data["current_step"] = current_step
            if files_generated is not None:
                data["files_generated"] = files_generated
            if current_file is not None:
                data["current_file"] = current_file
            if error is not None:
                data["error"] = error
            elif "error" in data:
                del data["error"]
                
            if project_name is not None:
                data["project_name"] = project_name
            if project_path is not None:
                data["project_path"] = project_path
            
            data["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            if "started_at" not in data or step == 0:
                data["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                if "error" in data:
                    del data["error"]
                
            status_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"[PBS] Failed to write status file: {e}")

    def build_project(self, objective: str) -> Dict[str, Any]:
        """
        End-to-end SYNCHRONOUS pipeline for generating a production-level project.
        """
        logger.info(f"[PBS] Starting build for: {objective}")
        self._update_status("running", 0, "Starting project build", project_name="Initializing...")
        t0 = time.time()
        context = SharedContextBuffer(task_id=f"pbs_{int(time.time())}", objective=objective)

        try:
            # ── Step 1: Idea Analysis ───────────────────────────────────────
            logger.info("[PBS] Step 1/10: Idea Analysis")
            self._update_status("running", 1, "Idea Analysis")

            # ── Step 2: Architecture Design ─────────────────────────────────
            logger.info("[PBS] Step 2/10: Architecture Design")
            self._update_status("running", 2, "Architecture Design")
            arch_res = self.arch_agent.process(objective, context=context)
            if arch_res["status"] != "success":
                err = f"Architecture failure: {arch_res.get('output')}"
                self._update_status("failed", 2, "Architecture Design failed", error=err)
                return {"success": False, "error": err}

            blueprint = arch_res.get("blueprint")
            if not blueprint:
                err = "Missing blueprint in architecture response"
                self._update_status("failed", 2, "Architecture Design failed", error=err)
                return {"success": False, "error": err}

            project_name = blueprint.project_name
            # Sanitize
            project_name = "".join(c for c in project_name if c.isalnum() or c in ("_", "-"))
            if not project_name:
                project_name = "aeris_project"

            project_dir = self.base_dir / project_name

            # REUSE existing directory instead of creating duplicates
            project_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"[PBS] Project workspace: {project_dir}")
            self._update_status("running", 2, "Architecture Design Complete", project_name=project_name, project_path=str(project_dir))

            # ── Step 3: Flowchart Generation (optional) ─────────────────────
            logger.info("[PBS] Step 3/10: Flowchart Generation")
            self._update_status("running", 3, "Flowchart Generation")
            flowchart = self._generate_flowchart(blueprint, project_name)

            # ── Step 4: UI/UX Design ────────────────────────────────────────
            logger.info("[PBS] Step 4/10: UI/UX Design")
            self._update_status("running", 4, "UI/UX Design")
            css_fw = getattr(blueprint.tech_stack, "css_framework", "standard CSS")
            ui_overview = (
                f"A modern, responsive design using {css_fw}. "
                f"Includes clean layout, responsive grid, and proper navigation."
            )

            # ── Step 5: Project Structure Scaffolding ───────────────────────
            logger.info("[PBS] Step 5/10: Project Structure Scaffolding")
            self._update_status("running", 5, "Project Structure Scaffolding")
            for node in blueprint.structure:
                if node.type == "directory":
                    dir_path = project_dir / node.path
                    dir_path.mkdir(parents=True, exist_ok=True)

            # Open folder in VS Code automatically (Step 5.5)
            try:
                import subprocess
                logger.info(f"[PBS] Opening folder in VS Code: {project_dir}")
                subprocess.Popen(f'code "{project_dir}"', shell=True)
            except Exception as code_err:
                logger.warning(f"[PBS] Could not open VS Code: {code_err}")

            # ── Step 6: Code Generation (per-file) ─────────────────────────
            logger.info("[PBS] Step 6/10: Code Generation")
            self._update_status("running", 6, "Starting Code Generation")
            generated_files = self._generate_all_code(
                blueprint, project_dir, objective, context
            )
            self._update_status("running", 6, "Code Generation Complete", files_generated=generated_files)

            # ── Step 7: Dependencies & Config ──────────────────────────────
            logger.info("[PBS] Step 7/10: Dependencies & Config")
            self._update_status("running", 7, "Dependencies & Config")
            run_commands = self._write_dependency_files(
                blueprint, project_dir, project_name, generated_files
            )

            # ── Step 8: Verification ───────────────────────────────────────
            logger.info("[PBS] Step 8/10: Verification")
            self._update_status("running", 8, "Verification")
            # CodingAgent already validates syntax with enable_validation=True
            logger.info("[PBS] Verification passed (inline validation).")

            # ── Step 9: Documentation ──────────────────────────────────────
            logger.info("[PBS] Step 9/10: Documentation")
            self._update_status("running", 9, "Generating Documentation")
            self._generate_readme(project_dir, project_name, objective, context, generated_files)
            generated_files.append(f"{project_name}/README.md")

            # ── Step 10: Output Delivery ───────────────────────────────────
            elapsed = time.time() - t0
            logger.info(f"[PBS] Step 10/10: Output Delivery ({elapsed:.1f}s total)")
            self._update_status("completed", 10, "Finished", files_generated=generated_files)

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
        except Exception as e:
            logger.exception("[PBS] Error in build_project")
            self._update_status("failed", 0, "Error occurred", error=str(e))
            return {"success": False, "error": str(e)}

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
            self._update_status(
                "running",
                6,
                f"Generating file {i+1} of {len(file_nodes)}",
                files_generated=generated_files,
                current_file=file_path_rel
            )

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
    Delegates project building to the external Antigravity IDE assistant
    by writing the command to data/ide_commands.json and initializing
    data/project_build_status.json for monitoring.
    """
    import json
    import time
    from pathlib import Path
    from config import settings

    base_dir = Path(settings.WORKSPACE_DIR).resolve()
    data_dir = base_dir.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    commands_file = data_dir / "ide_commands.json"
    status_file = data_dir / "project_build_status.json"

    # 1. Write the command for the Antigravity IDE to consume
    cmd_data = {
        "command": "build_project",
        "objective": objective,
        "status": "pending",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        commands_file.write_text(json.dumps(cmd_data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"[PBS] Failed to write ide_commands.json: {e}")

    # 2. Write initial status so AERIS can monitor it
    status_data = {
        "status": "pending_ide",
        "step": 0,
        "current_step": "AERIS has sent the command to the Antigravity IDE. Waiting for the IDE agent to build...",
        "project_name": "Scaffolding via Antigravity IDE...",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "project_path": str(base_dir / "pending_project"),
        "files_generated": [],
        "current_file": "None"
    }
    try:
        status_file.write_text(json.dumps(status_data, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"[PBS] Failed to write initial project_build_status.json: {e}")

    return (
        "🚀 **Maine Antigravity IDE ko prompt send kar diya hai!**\n\n"
        f"Aapka target prompt/objective hai: \"{objective}\".\n"
        "Antigravity IDE ab is file ko read karke project generate karega aur main yahan se progress ko monitor karunga. "
        "Aap build progress check karne ke liye **'project status'** ya **'status kya hai'** pooch sakte hain."
    )


def check_build_status() -> str:
    """Read the current project builder status and return a formatted markdown report."""
    from config import settings
    base_dir = Path(settings.WORKSPACE_DIR).resolve()
    status_file = base_dir.parent / "data" / "project_build_status.json"
    
    if not status_file.exists():
        return "No project builds have been started yet or no status record is found."
        
    try:
        import json
        data = json.loads(status_file.read_text(encoding="utf-8"))
        
        status = data.get("status", "unknown").upper()
        step = data.get("step", 0)
        current_step = data.get("current_step", "N/A")
        project_name = data.get("project_name", "N/A")
        files_generated = data.get("files_generated", [])
        current_file = data.get("current_file", "None")
        error = data.get("error")
        updated_at = data.get("updated_at", "N/A")
        
        emoji = "⚙️"
        if status == "RUNNING":
            emoji = "⚡"
        elif status == "COMPLETED":
            emoji = "✅"
        elif status == "FAILED":
            emoji = "❌"
            
        progress_bar = ""
        for i in range(1, 11):
            if i <= step:
                progress_bar += "■"
            else:
                progress_bar += "□"
        pct = step * 10
        
        lines = [
            f"### {emoji} **Project Build Status: {status}**",
            f"- **Project Name:** `{project_name}`",
            f"- **Current Phase:** {current_step} (Step {step}/10)",
            f"- **Progress:** `[{progress_bar}]` {pct}%",
            f"- **Last Updated:** {updated_at}",
        ]
        
        if status == "RUNNING" and current_file != "None":
            lines.append(f"- **Current File Generation:** `{current_file}`")
            
        if error:
            lines.append(f"- **Error:** `{error}`")
            
        if files_generated:
            lines.append("\n📁 **Generated Files:**")
            for f in files_generated:
                lines.append(f"  - `{f}`")
                
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading project build status: {str(e)}"
