import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from tools.tool_registry import global_tool_registry, _register_all_tools
_register_all_tools()

# Set console encoding to UTF-8
sys.stdout.reconfigure(encoding='utf-8')

print("TOTAL TOOLS REGISTERED:", len(global_tool_registry))
categories = {}
for name, t in global_tool_registry._tools.items():
    categories.setdefault(t.category, []).append((name, t.description))

for cat, tools in sorted(categories.items()):
    print(f"\nCategory: {cat.upper()}")
    for name, desc in tools:
        print(f"  - {name}: {desc}")
