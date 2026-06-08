import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure BACKEND is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import settings
from tools.excel_tools import update_excel_from_screen

class TestExcelVerification(unittest.IsolatedAsyncioTestCase):
    @patch("pyautogui.screenshot")
    @patch("ai_engine.ai_engine.vision")
    async def test_clarification_fallback(self, mock_vision, mock_screenshot):
        """Verify that update_excel_from_screen returns a clarification request if details are not on screen."""
        # Mock screen monitoring screenshot
        mock_screenshot.return_value = MagicMock()
        
        # Mock vision model outputting not found
        mock_vision.return_value = '{"found": false}'
        
        # Run the excel update without source="web"
        # Since details won't be on screen, it should clarify instead of doing web search
        res = await update_excel_from_screen(
            target_name="Rahul",
            excel_path_or_keyword="test_contacts.xlsx"
        )
        
        self.assertIn("Sir, mujhe screen par 'Rahul' ki details nahi mili", res)
        self.assertIn("web search karoon", res)

    @patch("pyautogui.screenshot")
    @patch("ai_engine.ai_engine.vision")
    @patch("services.chat_engine.realtime_search")
    @patch("ai_engine.ai_engine.chat")
    async def test_web_search_forced(self, mock_chat, mock_search, mock_vision, mock_screenshot):
        """Verify that update_excel_from_screen performs a web search if source='web' is passed."""
        mock_screenshot.return_value = MagicMock()
        mock_vision.return_value = '{"found": false}'
        
        # Mock web search results
        mock_search.return_value = "Rahul is a developer at Google. Email: rahul@google.com"
        
        # Mock LLM extraction
        mock_chat.return_value = '{"Name": "Rahul", "Role": "Developer", "Email": "rahul@google.com", "Company": "Google"}'
        
        # Delete existing test file if present
        test_file_path = Path(settings.WORKSPACE_DIR) / "test_contacts.xlsx"
        if test_file_path.exists():
            test_file_path.unlink()

        # Run with source="web"
        res = await update_excel_from_screen(
            target_name="Rahul",
            excel_path_or_keyword="test_contacts.xlsx",
            source="web"
        )
        
        # Verify it successfully updated Excel
        self.assertIn("successfully updated", res)
        self.assertTrue(test_file_path.exists())
        
        # Clean up
        if test_file_path.exists():
            test_file_path.unlink()

if __name__ == "__main__":
    unittest.main()
