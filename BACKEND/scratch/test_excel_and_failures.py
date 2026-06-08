"""
Test script for verifying Excel tools, failure logging, and the Investigation Agent.
"""
import os
import sys
import json
import asyncio
from pathlib import Path

# Ensure backend directory is in the path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Mock configuration settings to load correctly
from config import settings
from tools.excel_tools import export_to_excel, update_excel_from_screen
from utils.failure_logger import log_task_failure
from agents.investigation_agent import InvestigationAgent

async def run_tests():
    print("--- 1. Testing Excel Styled Exports ---")
    file_path = "test_contacts.xlsx"
    resolved_path = Path(settings.WORKSPACE_DIR) / file_path
    if resolved_path.exists():
        resolved_path.unlink()

    sample_data = [
        {"Name": "Sandeep Kumar", "Role": "HR Manager", "Email": "sandeep.k@company.com", "Phone": 9876543210},
        {"Name": "Rahul Verma", "Role": "Software Engineer", "Email": "rahul.v@company.com", "Phone": 9812345678}
    ]

    print("Exporting sample data to Excel...")
    result = export_to_excel(file_path, sample_data)
    print(result)
    assert resolved_path.exists(), "Excel file was not created!"
    print("Excel file created successfully and verified.")

    print("\n--- 2. Testing update_excel_from_screen with Manual Details ---")
    # This should update/append details for Sandeep (existing) and add a new person (non-existing)
    print("Updating Sandeep's details (should update row)...")
    res1 = await update_excel_from_screen(
        excel_path_or_keyword="test_contacts.xlsx",
        target_name="Sandeep Kumar",
        manual_details={"Name": "Sandeep Kumar", "Role": "Senior HR Manager", "Email": "sandeep.senior@company.com"}
    )
    print(res1)

    print("Adding Priya's details (should append new row)...")
    res2 = await update_excel_from_screen(
        excel_path_or_keyword="test_contacts.xlsx",
        target_name="Priya Sharma",
        manual_details={"Name": "Priya Sharma", "Role": "HR Specialist", "Email": "priya.s@company.com"}
    )
    print(res2)

    import pandas as pd
    df = pd.read_excel(resolved_path)
    print("Updated excel sheet content:")
    print(df)
    
    # Assert Priya was appended and Sandeep updated
    assert len(df) == 3, f"Expected 3 rows, found {len(df)}"
    sandeep_row = df[df["Name"] == "Sandeep Kumar"]
    assert sandeep_row["Role"].values[0] == "Senior HR Manager", "Sandeep's Role was not updated!"
    print("Excel manual details and incremental updates verified.")

    print("\n--- 3. Testing smart file naming based on Role ---")
    # We will pass target name Sandeep and role HR without specifying file name. It should write to hr.xlsx
    hr_path = Path(settings.WORKSPACE_DIR) / "hr.xlsx"
    if hr_path.exists():
        hr_path.unlink()

    print("Updating with HR role without file path...")
    res3 = await update_excel_from_screen(
        target_name="Sandeep Kumar",
        manual_details={"Name": "Sandeep Kumar", "Role": "HR", "Email": "sandeep@hr.com"}
    )
    print(res3)
    assert hr_path.exists(), "hr.xlsx was not automatically created!"
    print("hr.xlsx created automatically based on Role HR.")

    print("\n--- 4. Testing Failure Logging ---")
    json_path = backend_dir / "failed_tools.json"
    txt_path = backend_dir / "failed_log.txt"

    # Reset failure files
    if json_path.exists():
        json_path.unlink()
    if txt_path.exists():
        txt_path.unlink()

    print("Logging a mock task failure...")
    log_task_failure(
        task_id="task_test_123",
        step_id="step_1",
        tool_name="write_file",
        args={"path": "C:/restricted.txt", "content": "hello"},
        error="SECURITY_BLOCKED: Path outside workspace boundary.",
        agent_name="ToolExecutorService",
        intent="file_write"
    )

    assert json_path.exists(), "failed_tools.json was not created!"
    assert txt_path.exists(), "failed_log.txt was not created!"

    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    print("JSON Failure entry:")
    print(json.dumps(json_data, indent=2))
    assert len(json_data["failed_tools"]) == 1, "Expected 1 failed tool entry!"
    
    with open(txt_path, "r", encoding="utf-8") as f:
        txt_content = f.read()
    print("Txt Log entry:")
    print(txt_content)
    assert "write_file" in txt_content, "write_file was not found in txt logs!"
    print("Failure logging verified successfully.")

    print("\n--- 5. Testing Investigation Agent ---")
    agent = InvestigationAgent()
    print("Running Investigation Agent on the latest mock failure...")
    # Mock surrounding agents for registration context
    context = {
        "surrounding_agents_summary": "RepairAgent (repair): code self-healing\nSystemAgent (system): run terminal commands"
    }
    
    # Run the agent pipeline
    response = await agent.run("latest failed task check karo aur investigate karo", context)
    print("Investigation response status:", response["success"])
    print("Response message:")
    print(response["response"].encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))
    assert response["success"], "Investigation agent failed to run!"
    print("Investigation Agent successfully tested and verified.")

    print("\n--- 6. Testing Investigation Agent Memory Update ---")
    memory_req = "apni memory update kr. Name: Sambhav Mehra, Email: sambhavmehra07@gmail.com, Phone: 9876543210, Age: 20, Role: Owner"
    resp_mem = await agent.run(memory_req, {})
    print("Memory Update response status:", resp_mem["success"])
    print("Memory Update message:")
    print(resp_mem["response"].encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8"))
    
    # Check if personal_details.json was created/updated correctly
    from utils.personal_details_helper import load_personal_details
    details = load_personal_details()
    print("Loaded personal details:", details)
    assert details["Name"] == "Sambhav Mehra", "Name was not saved correctly!"
    assert details["Email"] == "sambhavmehra07@gmail.com", "Email was not saved correctly!"
    assert details["Phone"] == "9876543210", "Phone was not saved correctly!"
    assert details["Age"] == "20", "Age was not saved correctly!"
    assert details["Role"] == "Owner", "Role was not saved correctly!"
    print("Investigation Agent Memory Update successfully tested and verified.")

    print("\n--- 7. Testing Background Auto-Investigation on Brain ---")
    from brain import Brain
    brain = Brain()
    # Let's run background investigation directly to see if it finishes without error
    await brain.run_background_investigation(
        task_id="task_bg_test_999",
        tool_name="write_file",
        error="SECURITY_BLOCKED: Path outside workspace boundary.",
        intent="general"
    )
    print("Background Auto-Investigation run completed successfully.")

    print("\n--- 8. Testing Created Files Tracker ---")
    from utils.file_tracker import get_created_files
    created = get_created_files()
    print("Recently created files recorded in tracker:")
    for c in created:
        print(f"- {c['filename']}: {c['purpose']} at {c['timestamp']}")
    
    # We should have at least hr.xlsx or test_contacts.xlsx in there
    filenames = [c["filename"] for c in created]
    assert "hr.xlsx" in filenames or "test_contacts.xlsx" in filenames, "Excel files were not logged in file tracker!"
    print("Created Files Tracker successfully verified.")


if __name__ == "__main__":
    asyncio.run(run_tests())
