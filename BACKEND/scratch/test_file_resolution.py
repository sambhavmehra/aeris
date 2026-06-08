import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure BACKEND is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.file_tracker import resolve_tracked_file, record_file_creation
from automation.system_automation import open_app, open_file

class TestFileResolution(unittest.TestCase):
    def setUp(self):
        # Setup mock tracker entries in a temporary file or mock get_created_files
        self.tracker_patcher = patch("utils.file_tracker.get_created_files")
        self.mock_get_created_files = self.tracker_patcher.start()
        
        # Mock tracker records
        self.mock_get_created_files.return_value = [
            {
                "timestamp": "2026-06-06T00:00:00Z",
                "file_path": "D:\\Sambhav Projects\\AERIS\\workspace\\sandeep_info.xlsx",
                "filename": "sandeep_info.xlsx",
                "purpose": "Sandeep details export"
            },
            {
                "timestamp": "2026-06-06T00:01:00Z",
                "file_path": "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx",
                "filename": "hr.xlsx",
                "purpose": "HR details export"
            }
        ]
        
    def tearDown(self):
        self.tracker_patcher.stop()

    def test_pronoun_resolution(self):
        """Verify that pronouns resolve to the latest file path."""
        # 'usko' should resolve to the latest (hr.xlsx)
        path = resolve_tracked_file("usko")
        self.assertEqual(path, "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx")
        
        # 'it' should resolve to the latest (hr.xlsx)
        path_it = resolve_tracked_file("it")
        self.assertEqual(path_it, "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx")

    def test_keyword_resolution(self):
        """Verify that keywords match filenames or purposes correctly."""
        # 'hr' should resolve to hr.xlsx
        path = resolve_tracked_file("hr")
        self.assertEqual(path, "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx")
        
        # Shorthand matching (e.g. "hr wali sheet") should clean fillers and resolve to hr.xlsx
        path_sh = resolve_tracked_file("hr wali sheet")
        self.assertEqual(path_sh, "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx")
        
        # 'sandeep' should resolve to sandeep_info.xlsx
        path_sandeep = resolve_tracked_file("sandeep")
        self.assertEqual(path_sandeep, "D:\\Sambhav Projects\\AERIS\\workspace\\sandeep_info.xlsx")

    @patch("automation.system_automation.open_file")
    def test_open_app_interception(self, mock_open_file):
        """Verify that open_app intercepts tracked file queries and routes to open_file."""
        mock_open_file.return_value = {"success": True, "action": "open_file"}
        
        # Call open_app with file pronoun
        res = open_app("usko")
        
        # Verify redirect
        mock_open_file.assert_called_once_with("D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx")
        self.assertTrue(res["success"])

    @patch("os.path.exists")
    @patch("platform.system")
    @patch("os.startfile")
    def test_open_file_path_resolution(self, mock_startfile, mock_platform, mock_exists):
        """Verify that open_file resolves missing paths using the tracker."""
        mock_platform.return_value = "Windows"
        
        # Setup exists mocks:
        # The query path "hr" doesn't exist, but the resolved path "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx" does exist.
        def exists_side_effect(p):
            if p == "hr":
                return False
            if p == "D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx":
                return True
            return False
            
        mock_exists.side_effect = exists_side_effect
        
        # Try to open "hr"
        res = open_file("hr")
        
        # Assert startfile was called with the resolved tracker path
        mock_startfile.assert_called_once_with("D:\\Sambhav Projects\\AERIS\\workspace\\hr.xlsx")
        self.assertTrue(res["success"])

if __name__ == "__main__":
    unittest.main()
