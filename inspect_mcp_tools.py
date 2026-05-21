import asyncio
import json
import sys
from pathlib import Path

# Add BACKEND to path
sys.path.append(str(Path(__file__).resolve().parent / "BACKEND"))

from tools.universal_registry import get_universal_registry
from tools.mcp_bridge import get_mcp_registry

async def main():
    mcp_reg = get_mcp_registry()
    
    # Wait a bit for stdio subprocess connections to complete
    await asyncio.sleep(2)
    
    reg = get_universal_registry()
    tool = reg.get_tool("brevo_send_email")
    if tool:
        print(f"Tool Name: {tool.name}")
        print(f"Description: {tool.description}")
        print(f"Input Schema Params:")
        for p in tool.input_schema.params:
            print(f"  - {p.name}: required={p.required}")
        # print full metadata
        print("Metadata:")
        print(json.dumps(tool.to_metadata(), indent=2))
    else:
        print("brevo_send_email tool not found. Current tools: ", reg.get_tool_names())
        print("MCP servers: ", [s.name for s in mcp_reg.list_servers()])

if __name__ == "__main__":
    asyncio.run(main())
