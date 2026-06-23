# -*- coding: utf-8 -*-
"""
AERIS Guardian Mode Verification Script
"""
import sys
import os
import asyncio
from pathlib import Path

# Add BACKEND to path
backend_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_path))

async def run_tests():
    print("=== AERIS GUARDIAN MODE TESTS ===")
    
    # 1. Import manager
    print("[*] Importing guardian_mode_manager...")
    from services.guardian_mode import guardian_mode_manager
    
    # Reset state to ensure clean test
    if guardian_mode_manager.is_active:
        guardian_mode_manager.stop_monitoring()
        guardian_mode_manager.is_active = False
        guardian_mode_manager.config.update({"enabled": False})
        
    print(f"[+] Initial state: active={guardian_mode_manager.is_active}")
    assert not guardian_mode_manager.is_active, "Should be disabled by default"
    
    # 2. Test configuration defaults
    print("[*] Verifying config defaults...")
    blocked_apps = guardian_mode_manager.config.get("blocked_apps")
    print(f"[+] Blocked apps config: {blocked_apps}")
    assert "WhatsApp.exe" in blocked_apps, "WhatsApp.exe should be in blocked apps list"
    
    # 3. Test enable toggling
    print("[*] Enabling Guardian Mode...")
    msg = guardian_mode_manager.enable_guardian_mode(method="test")
    print(f"[+] Enable message: {msg}")
    assert guardian_mode_manager.is_active, "Should be enabled now"
    
    # 4. Test violation handling and policy engine
    print("[*] Simulating violation 1 (App: WhatsApp.exe)...")
    guardian_mode_manager._handle_violation(
        viol_type="app",
        target="WhatsApp.exe",
        details="Simulated manual violation for testing",
        hwnd=0,
        proc_name="WhatsApp.exe"
    )
    
    # Check attempt counter
    attempts = guardian_mode_manager.attempt_counters.get("app:whatsapp.exe", 0)
    print(f"[+] Attempt counter: {attempts}")
    assert attempts == 1, "Attempt counter should be 1"
    
    # Check audit log
    logs = guardian_mode_manager.audit_logger.get_logs()
    last_log = logs[-1]
    print(f"[+] Last audit log event: {last_log}")
    assert last_log["event_type"] == "violation_app", "Log event type should match violation"
    assert last_log["action"] == "close", "First violation action should be 'close'"
    
    # Simulate violation 2 (App: WhatsApp.exe)
    print("[*] Simulating violation 2 (App: WhatsApp.exe)...")
    guardian_mode_manager._handle_violation(
        viol_type="app",
        target="WhatsApp.exe",
        details="Simulated manual violation 2 for testing",
        hwnd=0,
        proc_name="WhatsApp.exe"
    )
    attempts = guardian_mode_manager.attempt_counters.get("app:whatsapp.exe", 0)
    logs = guardian_mode_manager.audit_logger.get_logs()
    last_log = logs[-1]
    print(f"[+] Attempt counter: {attempts}")
    print(f"[+] Last audit log event: {last_log}")
    assert attempts == 2, "Attempt counter should be 2"
    assert last_log["action"] == "close", "Second violation action should be 'close'"
    
    # Simulate violation 3 (App: WhatsApp.exe)
    print("[*] Simulating violation 3 (App: WhatsApp.exe)...")
    # Backup lock method to prevent actual screen lock during automated tests
    original_lock = guardian_mode_manager.action_engine.lock_session
    locked_called = False
    
    def mock_lock(target):
        nonlocal locked_called
        locked_called = True
        print(f"[+] Mock Lock Session called for: {target}")
        
    guardian_mode_manager.action_engine.lock_session = mock_lock
    
    guardian_mode_manager._handle_violation(
        viol_type="app",
        target="WhatsApp.exe",
        details="Simulated manual violation 3 for testing",
        hwnd=0,
        proc_name="WhatsApp.exe"
    )
    attempts = guardian_mode_manager.attempt_counters.get("app:whatsapp.exe", 0)
    logs = guardian_mode_manager.audit_logger.get_logs()
    last_log = logs[-1]
    print(f"[+] Attempt counter: {attempts}")
    print(f"[+] Last audit log event: {last_log}")
    assert locked_called, "Lock session should have been triggered"
    assert last_log["action"] == "lock", "Third violation action should be 'lock'"
    
    # Restore lock method
    guardian_mode_manager.action_engine.lock_session = original_lock
    
    # 5. Test disable toggling (incorrect PIN)
    print("[*] Trying to disable Guardian Mode with incorrect PIN...")
    success, msg = guardian_mode_manager.disable_guardian_mode(code="9999")
    print(f"[+] Result: success={success}, msg={msg}")
    assert not success, "Should fail with incorrect PIN"
    assert guardian_mode_manager.is_active, "Should still be active"
    
    # Test disable toggling (correct PIN)
    print("[*] Trying to disable Guardian Mode with correct PIN...")
    correct_pin = guardian_mode_manager.config.get("pin")
    success, msg = guardian_mode_manager.disable_guardian_mode(code=correct_pin)
    print(f"[+] Result: success={success}, msg={msg}")
    assert success, "Should succeed with correct PIN"
    assert not guardian_mode_manager.is_active, "Should be disabled now"
    
    # Test disable toggling (secret phrase)
    print("[*] Testing deactivation via secret phrase...")
    guardian_mode_manager.enable_guardian_mode()
    secret = guardian_mode_manager.config.get("secret_phrase")
    success, msg = guardian_mode_manager.disable_guardian_mode(code=secret)
    print(f"[+] Result: success={success}, msg={msg}")
    assert success, "Should succeed with secret phrase"
    assert not guardian_mode_manager.is_active, "Should be disabled now"
    
    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
