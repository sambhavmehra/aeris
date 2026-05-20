"""Inspect sub_agents/coding_agent.py around the report() method."""
path = r'd:\Sambhav Projects\AERIS\BACKEND\agents\sub_agents\coding_agent.py'
content = open(path, encoding='utf-8').read()

idx = content.find('async def report')
# Write a slice to file so we can read it without emoji encoding issues
with open('sub_agent_report_region.txt', 'w', encoding='utf-8') as f:
    f.write(content[idx:idx+800])

print('Wrote sub_agent_report_region.txt')
# Also find next method boundary
for needle in ['    def process', '    def generate', '    def analyze',
               '    def debug', '    def pipeline', '    def get_metrics',
               '    def clear', '    # ─', '    # ─\u2500']:
    pos = content.find(needle, idx + 50)
    if pos != -1:
        print(f'Next "{needle.strip()}" at char {pos}')
        break
