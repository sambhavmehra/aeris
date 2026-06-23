# -*- coding: utf-8 -*-
"""
AERIS Self-Evolution System Verification Script
"""
import sys
import os
import json
import asyncio
from pathlib import Path

# Add BACKEND to path
backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

async def run_tests():
    print("=== AERIS SELF-EVOLUTION TESTS ===")
    
    # 1. Import engine
    print("[*] Importing self_evolution_engine...")
    from services.self_evolution import self_evolution_engine
    
    # Cleanup previous states
    if self_evolution_engine.proposal_file.exists():
        os.remove(self_evolution_engine.proposal_file)
        
    print(f"[+] Initial check: proposal file exists = {self_evolution_engine.proposal_file.exists()}")
    
    # 2. Test Propose Improvement (IoT simulation helper)
    print("[*] Requesting self-improvement proposal for: 'IoT devices simulator tool'...")
    res = await self_evolution_engine.propose_improvement("Create a tool to simulate smart IoT devices status, named auto_helper_iot_test")
    
    print(f"[+] Proposal result success: {res.get('success')}")
    if not res.get("success"):
        print(f"[-] Error: {res.get('error')}")
        return
        
    # Check proposal file content
    assert self_evolution_engine.proposal_file.exists(), "Proposal JSON should be written to disk"
    proposal_data = json.loads(self_evolution_engine.proposal_file.read_text(encoding="utf-8"))
    
    print(f"[+] Proposal generated keys: {list(proposal_data.keys())}")
    assert proposal_data["feature_name"] == "auto_helper_iot_test", "Feature name should match prompt request"
    assert "code" in proposal_data, "Code should be in JSON"
    assert "registration_code" in proposal_data, "Registration code should be in JSON"
    
    # 3. Test Execute Proposal
    print("[*] Executing proposal (writing tool and registering)...")
    
    # Backup tool_registry.py content
    registry_path = self_evolution_engine.tools_dir / "tool_registry.py"
    original_registry_content = registry_path.read_text(encoding="utf-8")
    
    tool_file = self_evolution_engine.tools_dir / "auto_helper_iot_test.py"
    
    try:
        success, msg = await self_evolution_engine.execute_proposal()
        print(f"[+] Execution result: success={success}, msg={msg}")
        assert success, "Execution should succeed"
        
        # Verify tool file creation
        assert tool_file.exists(), "Permanent tool file should be written to disk"
        print(f"[+] Created file exists: {tool_file.exists()}")
        
        # Verify import check
        print("[*] Testing importing new tool dynamically...")
        import tools.tool_registry
        print(f"[+] Dynamic reload completed successfully.")
        
    except Exception as e:
        print(f"[-] Test failed: {e}")
        if registry_path.exists():
            print("--- MODIFIED tool_registry.py LAST 30 LINES ---")
            lines = registry_path.read_text(encoding="utf-8").splitlines()
            for i in range(max(0, len(lines) - 30), len(lines)):
                print(f"{i+1:4d}: {repr(lines[i])}")
        raise e
    finally:
        # Cleanup created files to keep workspace clean
        print("[*] Cleaning up test tool files...")
        if tool_file.exists():
            os.remove(tool_file)
        if registry_path.exists():
            registry_path.write_text(original_registry_content, encoding="utf-8")
        if self_evolution_engine.proposal_file.exists():
            os.remove(self_evolution_engine.proposal_file)
            
    print("\n=== ALL SELF-EVOLUTION TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
