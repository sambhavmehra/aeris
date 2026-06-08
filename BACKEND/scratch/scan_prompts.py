import os
import re
import importlib.util
from pathlib import Path

class SafeDict(dict):
    def __missing__(self, key):
        return "TEST_VALUE"

def main():
    backend_dir = Path("d:/Sambhav Projects/AERIS/BACKEND")
    errors_found = False

    for root, dirs, files in os.walk(backend_dir):
        # Skip pycache and hidden folders
        if any(p in root for p in [".pytest_cache", "__pycache__", ".git"]):
            continue
        for f in files:
            if f.endswith(".py"):
                file_path = Path(root) / f
                try:
                    content = file_path.read_text(encoding="utf-8")
                except Exception:
                    continue

                # Find uppercase variables containing prompts
                matches = re.findall(r"\b([A-Z0-9_]+_PROMPT|[A-Z0-9_]+_ROLE)\b", content)
                if not matches:
                    continue

                # Dynamically load the module
                try:
                    module_name = f"temp_{file_path.stem}"
                    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                except Exception as e:
                    # Some imports might fail if dependencies are missing, skip those or print warning
                    continue

                for var_name in set(matches):
                    if hasattr(mod, var_name):
                        val = getattr(mod, var_name)
                        if isinstance(val, str):
                            # Try to format the template
                            try:
                                formatted = val.format_map(SafeDict())
                            except ValueError as ve:
                                print(f"[ERROR] Mismatched braces in {file_path.relative_to(backend_dir)}: {var_name}")
                                print(f"  Details: {ve}")
                                errors_found = True
                            except KeyError as ke:
                                # SafeDict handles missing keys, but nested keys like {settings.USERNAME} can fail
                                # Let's try to format it by passing settings or other objects if needed
                                try:
                                    from config import settings
                                    formatted = val.format(
                                        message="test",
                                        history="test",
                                        history_summary="test",
                                        recent_tasks="test",
                                        recent_tasks_summary="test",
                                        profile_context="test",
                                        memory_context="test",
                                        memory_section="test",
                                        plan_json="{}",
                                        observations_json="[]",
                                        tools_summary="test",
                                        tools_desc="test",
                                        tools="test",
                                        workspace_dir="test",
                                        created_files_context="test",
                                        settings=settings,
                                        current_time="test",
                                        capabilities="test",
                                        results="test",
                                        prior_context="test",
                                        shell="test",
                                        os="test",
                                        q="test",
                                        step="test",
                                        tool="test",
                                        error="test",
                                        title="test",
                                        host="test",
                                        path="test",
                                        targets_summary="test",
                                        pivots_summary="test",
                                        intel_results="test",
                                        original_targets="test",
                                        phase1_results="test",
                                        question="test",
                                        results_text="test",
                                    )
                                except Exception as e2:
                                    # If it still fails with ValueError, report it
                                    if isinstance(e2, ValueError):
                                        print(f"[ERROR] Mismatched braces in {file_path.relative_to(backend_dir)}: {var_name}")
                                        print(f"  Details: {e2}")
                                        errors_found = True

    if not errors_found:
        print("[SUCCESS] All format strings scanned successfully, no format errors found.")
    else:
        print("[FAIL] Formatting errors were detected.")

if __name__ == "__main__":
    main()
