import sys
sys.path.append('.')
import asyncio
import os
from brain import brain

async def test():
    print("=======================================")
    print("Testing OSINTAgent Routing & Execution")
    print("=======================================")
    
    # Test 1: Username Investigation (routes to OSINTAgent)
    print("\n--- Test 1: Username Footprint Check ---")
    query_1 = "Investigate @sambhav_mehra"
    print(f"Query: {query_1}")
    res_1 = await brain.process(query_1)
    
    print(f"Intent classified: {res_1.get('intent')}")
    print(f"Agent assigned: {res_1.get('agent')}")
    print(f"Success status: {res_1.get('success')}")
    
    with open('test_osint_username_output.txt', 'w', encoding='utf-8') as f:
        f.write(res_1.get("response", ""))
    print("Wrote Test 1 response to test_osint_username_output.txt")
    
    # Test 2: Domain Infrastructure check & pivot
    print("\n--- Test 2: Domain Infrastructure Recon ---")
    query_2 = "Trace target sambhav.me"
    print(f"Query: {query_2}")
    res_2 = await brain.process(query_2)
    
    print(f"Intent classified: {res_2.get('intent')}")
    print(f"Agent assigned: {res_2.get('agent')}")
    print(f"Success status: {res_2.get('success')}")
    
    with open('test_osint_domain_output.txt', 'w', encoding='utf-8') as f:
        f.write(res_2.get("response", ""))
    print("Wrote Test 2 response to test_osint_domain_output.txt")
    
    print("\nOSINT testing completed!")

if __name__ == "__main__":
    asyncio.run(test())
