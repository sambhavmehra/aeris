"""
Patch sub_agents/coding_agent.py: replace the trivial report() method
with a proper one that renders code inline and suppresses raw JSON.
"""

path = r'd:\Sambhav Projects\AERIS\BACKEND\agents\sub_agents\coding_agent.py'
content = open(path, encoding='utf-8').read()

# Old report() in the sub-agent is minimal (lines 509-512):
# async def report(self, results: Any) -> str:
#     if isinstance(results, dict):
#         return results.get("code", str(results))
#     return str(results)

START_SIG = '    async def report(self, results: Any) -> str:\n'
END_SIG   = '    # -- Public Sync API (backward-compatible)'

start_idx = content.find(START_SIG)
end_idx   = content.find(END_SIG)

if start_idx == -1:
    print('ERROR: Could not find report() start')
    exit(1)
if end_idx == -1:
    print('ERROR: Could not find end sentinel')
    exit(1)

print(f'Found report() at char {start_idx}-{end_idx}')

NEW_REPORT = '''\
    async def report(self, results: Any) -> str:
        """Format CodingResult (or raw dict) into clean Markdown for the UI."""
        # Handle typed CodingResult objects
        if hasattr(results, 'files') and hasattr(results, 'analysis'):
            parts = []
            # Analysis — suppress raw JSON blobs
            if results.analysis:
                a = results.analysis.strip()
                if not (a.startswith('{') or a.startswith('[')):
                    if '```' in a:
                        parts.append(a)
                    else:
                        sentences = a.split('. ')
                        brief = '. '.join(sentences[:3]).strip()
                        if brief and not brief.endswith('.'):
                            brief += '.'
                        if brief:
                            parts.append(brief)
            # Files — always render inline
            if results.files:
                for cf in results.files:
                    if cf.content and len(cf.content.strip()) > 10:
                        lang = (cf.language or results.language or 'text').strip()
                        header = f'\\n**`{cf.path}`**' if cf.path else ''
                        parts.append(f'{header}\\n```{lang}\\n{cf.content.rstrip()}\\n```')
            elif results.code and len(results.code.strip()) > 10:
                lang = (results.language or 'python').strip()
                parts.append(f'```{lang}\\n{results.code.rstrip()}\\n```')
            if results.error:
                parts.append(f'\\n**Error:** {results.error}')
            return '\\n'.join(parts) if parts else 'Code task completed.'

        # Handle dict results (e.g. from generate_code which returns .to_dict())
        if isinstance(results, dict):
            parts = []
            # Render files
            for ff in results.get('files') or []:
                if isinstance(ff, dict) and ff.get('content') and len(ff['content'].strip()) > 10:
                    lang = (ff.get('language') or results.get('language') or 'text').strip()
                    path_label = f'\\n**`{ff["path"]}`**' if ff.get('path') else ''
                    parts.append(f'{path_label}\\n```{lang}\\n{ff["content"].rstrip()}\\n```')
            # Inline code
            if not parts and results.get('code') and len(results['code'].strip()) > 10:
                lang = (results.get('language') or 'python').strip()
                parts.append(f'```{lang}\\n{results["code"].rstrip()}\\n```')
            # Analysis (non-JSON)
            analysis = (results.get('analysis') or '').strip()
            if analysis and not (analysis.startswith('{') or analysis.startswith('[')):
                if '```' in analysis:
                    parts.insert(0, analysis)
                else:
                    brief = '. '.join(analysis.split('. ')[:3]).strip()
                    if brief and not brief.endswith('.'):
                        brief += '.'
                    if brief:
                        parts.insert(0, brief)
            if results.get('error'):
                parts.append(f'\\n**Error:** {results["error"]}')
            return '\\n'.join(parts) if parts else 'Code task completed.'

        return str(results)

'''

new_content = content[:start_idx] + NEW_REPORT + content[end_idx:]
open(path, 'w', encoding='utf-8').write(new_content)
print('Done!')

# Verify
updated = open(path, encoding='utf-8').read()
ok = 'Handle typed CodingResult objects' in updated
print('Verified:', ok)
