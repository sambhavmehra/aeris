"""
Patch code_agent.py: replace the report() method with an improved version
that renders code inline, suppresses raw JSON from analysis, and handles
all result shapes properly.
"""
import re

path = r'd:\Sambhav Projects\AERIS\BACKEND\agents\code_agent.py'
content = open(path, encoding='utf-8').read()

# ── Locate the report() method by its exact signature ────────────────────────
# Start marker: the `async def report` line
START_SIG = '    async def report(self, results: Any) -> str:\n'
# End marker: the next method at the same indentation level
END_SIG = '    # \u2500\u2500 Public Sync API (backward-compatible)'

start_idx = content.find(START_SIG)
end_idx   = content.find(END_SIG)

if start_idx == -1 or end_idx == -1:
    print('ERROR: Could not locate report() boundaries.')
    print('  start_idx:', start_idx)
    print('  end_idx  :', end_idx)
    exit(1)

print(f'Found report() at char {start_idx}\u2013{end_idx}')

NEW_REPORT = '''\
    async def report(self, results: Any) -> str:
        """Format CodingResult into a clean Markdown response; auto-save files."""
        if isinstance(results, CodingResult):
            saved_files: List[str] = []
            workspace = self._get_workspace()

            # ── Auto-save generated files ─────────────────────────────────────
            for cf in results.files:
                if cf.content and len(cf.content.strip()) > 10:
                    try:
                        file_path = workspace / cf.path
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text(cf.content, encoding="utf-8")
                        saved_files.append(cf.path)
                        self.log(f"Saved generated file: {file_path}")
                    except Exception as exc:
                        self.log(f"Failed to save {cf.path}: {exc}", "ERROR")

            parts: List[str] = []

            # ── Analysis ──────────────────────────────────────────────────────
            if results.analysis:
                a = results.analysis.strip()
                # Suppress raw JSON blobs
                if a.startswith("{") or a.startswith("["):
                    pass
                elif "```" in a:
                    # LLM replied with markdown — render as-is
                    parts.append(a)
                else:
                    sentences = a.split(". ")
                    brief = ". ".join(sentences[:3]).strip()
                    if brief and not brief.endswith("."):
                        brief += "."
                    if brief:
                        parts.append(brief)

            # ── Suggestion ────────────────────────────────────────────────────
            if results.suggestion and not results.suggestion.strip().startswith("{"):
                parts.append(f"\\n**Suggestion:** {results.suggestion}")

            # ── Code output (always rendered inline for the UI) ──────────────
            if results.files:
                for cf in results.files:
                    if cf.content and len(cf.content.strip()) > 10:
                        lang = (cf.language or results.language or "text").strip()
                        header = f"\\n**`{cf.path}`**" if cf.path else ""
                        parts.append(
                            f"{header}\\n```{lang}\\n{cf.content.rstrip()}\\n```"
                        )
                if saved_files:
                    parts.append(f"\\n> \U0001f4c2 Saved to `{workspace}`")
            elif results.code and len(results.code.strip()) > 10:
                lang = (results.language or "python").strip()
                parts.append(f"```{lang}\\n{results.code.rstrip()}\\n```")

            # ── Diff ─────────────────────────────────────────────────────────
            if results.diff:
                parts.append(f"\\n**Diff:**\\n```diff\\n{results.diff}\\n```")

            # ── Tests ─────────────────────────────────────────────────────────
            if results.tests:
                parts.append(f"\\n**Tests:**\\n```\\n{results.tests}\\n```")

            # ── Security notes ────────────────────────────────────────────────
            if results.security_notes:
                notes = "\\n".join(f"  \u26a0\ufe0f {n}" for n in results.security_notes)
                parts.append(f"\\n**\U0001f512 Security Notes:**\\n{notes}")

            # ── Error ─────────────────────────────────────────────────────────
            if results.error:
                parts.append(f"\\n**Error:** {results.error}")

            return "\\n".join(parts) if parts else "\u2705 Code task completed."
        return str(results)

'''

new_content = content[:start_idx] + NEW_REPORT + content[end_idx:]

open(path, 'w', encoding='utf-8').write(new_content)
print('Done! report() method updated successfully.')

# Verify
updated = open(path, encoding='utf-8').read()
if '# \u2500\u2500 Code output (always rendered inline for the UI)' in updated:
    print('Verification: new block present \u2705')
else:
    print('Verification: FAILED \u274c')
