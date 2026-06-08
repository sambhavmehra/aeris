import os
import sys
import asyncio
import unittest
from PIL import Image
from unittest.mock import MagicMock, patch

# Ensure BACKEND is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.screen_monitor import ScreenMonitor, get_screen_monitor
from brain import brain

class TestScreenMonitor(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.monitor = ScreenMonitor()
        
    def tearDown(self):
        self.monitor.stop_monitoring()

    def test_screen_change_detection(self):
        """Verify that screen change detection works based on pixel differences."""
        # Create two identical images
        img1 = Image.new("RGB", (100, 100), color="white")
        img2 = Image.new("RGB", (100, 100), color="white")
        
        # Initial screenshot sets the base frame
        has_changed_1 = self.monitor._detect_screen_change(img1)
        self.assertTrue(has_changed_1)
        
        # Second identical screenshot shouldn't register a change
        has_changed_2 = self.monitor._detect_screen_change(img2)
        self.assertFalse(has_changed_2)
        
        # Third screenshot with substantial change (different color)
        img3 = Image.new("RGB", (100, 100), color="black")
        has_changed_3 = self.monitor._detect_screen_change(img3)
        self.assertTrue(has_changed_3)

    @patch("subprocess.Popen")
    def test_overlay_window_spawning(self, mock_popen):
        """Verify that overlay window subprocess is spawned with correct arguments."""
        # Mock Popen
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        # Trigger overlay display
        asyncio.run(self.monitor._show_suggestion_overlay("Test Suggestion"))
        
        # Check Popen was called
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertIn("overlay_window.py", args[1])
        self.assertEqual(args[3], "Test Suggestion")
        
        # Verify dismissal terminates the process
        self.monitor.dismiss_overlay()
        mock_process.terminate.assert_called_once()

    async def test_brain_command_intercept(self):
        """Verify that the brain intercepts screen monitoring activation/deactivation commands."""
        # Mock start_monitoring
        with patch.object(ScreenMonitor, "start_monitoring") as mock_start:
            # We must patch get_screen_monitor to return our mocked class or use mock_start
            with patch("services.screen_monitor.get_screen_monitor") as mock_get:
                from unittest.mock import AsyncMock
                mock_inst = MagicMock()
                mock_inst.check_screen_and_suggest_now = AsyncMock(return_value="Mocked response")
                mock_get.return_value = mock_inst
                
                # Test activation command
                resp1 = await brain.process("meri screen continuously monitor karo")
                self.assertIn("screen_monitor_start", resp1.get("task_id", ""))
                mock_inst.start_monitoring.assert_called_once()
                mock_inst.reset_mock()
                
                # Test specific phrase activation
                resp1_alt = await brain.process("start monitoring to my screen")
                self.assertIn("screen_monitor_start", resp1_alt.get("task_id", ""))
                mock_inst.start_monitoring.assert_called_once()
                
                # Test deactivation command
                resp2 = await brain.process("screen monitor band karo")
                self.assertIn("screen_monitor_stop", resp2.get("task_id", ""))
                mock_inst.stop_monitoring.assert_called_once()
                mock_inst.reset_mock()
                
                # Test on-demand suggestion command
                resp3 = await brain.process("suggest karo")
                self.assertIn("screen_monitor_suggest_now", resp3.get("task_id", ""))
                mock_inst.check_screen_and_suggest_now.assert_called_once()

    @patch("pyautogui.screenshot")
    @patch("ai_engine.ai_engine.vision")
    @patch("subprocess.Popen")
    async def test_check_screen_and_suggest_now(self, mock_popen, mock_vision, mock_screenshot):
        """Verify that check_screen_and_suggest_now triggers immediately and opens overlay."""
        mock_screenshot.return_value = Image.new("RGB", (100, 100), color="white")
        mock_vision.return_value = '{"issue_detected": true, "confidence": 0.9, "suggestion": "Test suggest", "implementation_plan": "..."}'
        mock_popen.return_value = MagicMock()
        
        resp = await self.monitor.check_screen_and_suggest_now()
        
        self.assertIn("Test suggest", resp)
        mock_popen.assert_called_once()

if __name__ == "__main__":
    unittest.main()
