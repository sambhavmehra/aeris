import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure BACKEND is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from services.file_tools import FileToolSystem
from automation.system_automation import open_app, open_file

class TestWorkspaceFix(unittest.TestCase):
    def test_file_tool_system_workspace(self):
        """Verify FileToolSystem workspace is resolved correctly to WORKSPACE_DIR."""
        ft = FileToolSystem()
        expected_workspace = Path(settings.WORKSPACE_DIR).resolve()
        self.assertEqual(ft.workspace, expected_workspace)

    @patch("automation.system_automation.open_file")
    @patch("utils.file_tracker.resolve_tracked_file", return_value=None)
    def test_open_app_extension_redirection(self, mock_resolve, mock_open_file):
        """Verify that open_app intercepts names with extensions and routes to open_file."""
        mock_open_file.return_value = {"success": True}
        
        # Verify that direct filename in workspace or with extension is checked
        # Mock workspace check so we bypass Start Menu search and AppOpener
        with patch("os.path.exists", return_value=True):
            res = open_app("hr.xlsx")
            expected_path = str(Path(settings.WORKSPACE_DIR) / "hr.xlsx")
            mock_open_file.assert_called_with(expected_path)
            self.assertTrue(res["success"])

    @patch("automation.system_automation.open_file")
    @patch("utils.file_tracker.resolve_tracked_file", return_value=None)
    def test_open_app_no_extension_match_redirection(self, mock_resolve, mock_open_file):
        """Verify that open_app checks workspace for files with common extensions and redirects."""
        mock_open_file.return_value = {"success": True}

        # Mock os.path.exists to return True specifically for the test extension path
        def side_effect(path_arg):
            path_arg_str = str(path_arg)
            expected_test_path = str(Path(settings.WORKSPACE_DIR) / "hr.xlsx")
            return path_arg_str == expected_test_path

        with patch("os.path.exists", side_effect=side_effect):
            res = open_app("hr")
            expected_path = str(Path(settings.WORKSPACE_DIR) / "hr.xlsx")
            mock_open_file.assert_called_with(expected_path)
            self.assertTrue(res["success"])

if __name__ == "__main__":
    unittest.main()
