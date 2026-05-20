import sys
sys.path.append('.')
import asyncio
from BRAIN import brain
from agents.agent_registry import agent_registry

async def test():
    # Send the query
    res = await brain.process("mere liye ek tic-tac-toe game banao Python mein")
    
    # We write it to a file to avoid unicode print issues
    with open('test_brain_output.txt', 'w', encoding='utf-8') as f:
        f.write(res["response"])
    print("Done! Wrote to test_brain_output.txt")

asyncio.run(test())
