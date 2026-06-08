import os
import sys
import json
import unittest
import shutil
from pathlib import Path

# Ensure BACKEND is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from utils.failure_logger import log_task_failure, clear_resolved_failures
from brain import Brain

class TestHealingNotifications(unittest.TestCase):
    def setUp(self):
        self.backend_dir = Path(__file__).resolve().parent.parent
        self.json_path = self.backend_dir / "failed_tools.json"
        self.txt_path = self.backend_dir / "failed_log.txt"
        self.notif_file = Path(settings.DATA_DIR) / "sent_notifications.json"

        # Back up existing files if they exist
        self.backup_json = None
        self.backup_txt = None
        self.backup_notif = None

        if self.json_path.exists():
            self.backup_json = self.json_path.read_text(encoding="utf-8")
            self.json_path.unlink()
        if self.txt_path.exists():
            self.backup_txt = self.txt_path.read_text(encoding="utf-8")
            self.txt_path.unlink()
        if self.notif_file.exists():
            self.backup_notif = self.notif_file.read_text(encoding="utf-8")
            self.notif_file.unlink()

    def tearDown(self):
        # Restore backups
        if self.backup_json is not None:
            self.json_path.write_text(self.backup_json, encoding="utf-8")
        elif self.json_path.exists():
            self.json_path.unlink()

        if self.backup_txt is not None:
            self.txt_path.write_text(self.backup_txt, encoding="utf-8")
        elif self.txt_path.exists():
            self.txt_path.unlink()

        if self.backup_notif is not None:
            self.notif_file.write_text(self.backup_notif, encoding="utf-8")
        elif self.notif_file.exists():
            self.notif_file.unlink()

    def test_clear_resolved_failures(self):
        """Verify that resolved failures are removed from logs successfully."""
        # 1. Log a failure
        log_task_failure(
            task_id="task_temp_1",
            step_id="s1",
            tool_name="write_file",
            args={"path": "test.txt"},
            error="Path outside workspace boundary",
            agent_name="TestAgent"
        )
        
        # Verify it was logged
        self.assertTrue(self.json_path.exists())
        self.assertTrue(self.txt_path.exists())
        
        content_json = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(content_json["failed_tools"]), 1)
        self.assertIn("write_file", self.txt_path.read_text(encoding="utf-8"))

        # 2. Clear the resolved failure
        clear_resolved_failures("write_file", "workspace boundary")

        # Verify it was cleared
        content_json_cleared = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.assertEqual(len(content_json_cleared["failed_tools"]), 0)
        self.assertEqual(self.txt_path.read_text(encoding="utf-8").strip(), "{all errors from previous steps}")

    def test_duplicate_alert_prevention(self):
        """Verify that duplicate emails are blocked and notifications are tracked correctly."""
        brain = Brain()
        
        # 1. First time alert is triggered -> should return True (send email)
        res1 = brain._should_send_email_for_failure("write_file", "restricted path block error")
        self.assertTrue(res1)
        self.assertTrue(self.notif_file.exists())

        # 2. Second time with same tool and error -> should return False (skip email)
        res2 = brain._should_send_email_for_failure("write_file", "restricted path block error")
        self.assertFalse(res2)

        # 3. Clear the notification registry (simulates healing)
        brain._clear_sent_notification("write_file", "restricted path block error")
        
        # 4. Third time after clearing -> should return True (re-alert on new occurrence)
        res3 = brain._should_send_email_for_failure("write_file", "restricted path block error")
        self.assertTrue(res3)

if __name__ == "__main__":
    unittest.main()
