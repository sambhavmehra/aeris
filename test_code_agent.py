import asyncio
from backend.agents.code_agent import CodingAgent, CodingResult, TaskKind

async def test():
    agent = CodingAgent(enable_cache=False)
    
    raw_llm = """{ "analysis": "The game of Tic-Tac-Toe is a simple console-based game where two players, X and O, take turns marking a square on a 3x3 grid.", "suggestion": "Implement a Tic-Tac-Toe game using Python with a simple console-based interface.", "code": "", "diff": "", "files": [ { "path": "tic_tac_toe.py", "content": \"\"\" from dataclasses import dataclass\\nfrom enum import Enum\\nfrom pathlib import Path\\nfrom typing import List, Tuple\\n\"\"\" } ] }"""

    # simulate parse
    parsed = agent._parse_response(raw_llm)
    res = agent._build_result(parsed, TaskKind.GENERATE, "python")
    
    print("ANALYSIS:", repr(res.analysis))
    print("FILES:", res.files)
    
    rep = await agent.report(res)
    print("REPORT:", repr(rep))

asyncio.run(test())
