import os
import sys
import asyncio
import unittest
from unittest.mock import MagicMock, patch

# Ensure BACKEND is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.personal_details_helper import load_personal_details
from agents.investigation_agent import InvestigationAgent

class TestOwnerProfile(unittest.IsolatedAsyncioTestCase):
    def test_load_owner_profile(self):
        """Verify that personal_details.json loads owner profile details."""
        details = load_personal_details()
        self.assertEqual(details.get("Name"), "Sambhav Mehra")
        self.assertEqual(details.get("Email"), "sambhavmehra07@gmail.com")
        self.assertEqual(details.get("Role"), "Owner")

    @patch("ai_engine.ai_engine.chat")
    async def test_memory_update_rejection_for_external_contacts(self, mock_chat):
        """Verify that updating profile details with external contacts is rejected."""
        # Mock LLM response to indicate it's not the owner
        mock_chat.return_value = '{"is_owner": false}'
        
        agent = InvestigationAgent()
        plan = {
            "investigation_type": "memory_update",
            "message": "Sandeep Kumar, email sandeep.k@company.com, role HR Specialist",
            "target": "Sandeep details"
        }
        
        result = await agent.execute(plan)
        
        # Verify rejection
        self.assertFalse(result["success"])
        self.assertIn("external contact", result["error"])
        self.assertIn("Excel", result["response"])

    @patch("ai_engine.ai_engine.chat")
    @patch("utils.personal_details_helper.save_personal_details")
    async def test_memory_update_acceptance_for_owner(self, mock_save, mock_chat):
        """Verify that updating profile details with owner details is accepted."""
        # Mock LLM responses:
        # First chat call (validation): is_owner = True
        # Second chat call (extraction): returns details
        mock_chat.side_effect = [
            '{"is_owner": true}',
            '{"Name": "Sambhav Mehra", "Email": "sambhavmehra07@gmail.com", "Phone": "9876543210", "Age": "20", "Role": "Owner"}'
        ]
        
        mock_save.return_value = {
            "Name": "Sambhav Mehra",
            "Email": "sambhavmehra07@gmail.com",
            "Role": "Owner"
        }
        
        agent = InvestigationAgent()
        plan = {
            "investigation_type": "memory_update",
            "message": "my new email is sambhavmehra07@gmail.com",
            "target": "owner email update"
        }
        
        result = await agent.execute(plan)
        
        # Verify acceptance
        self.assertTrue(result["success"])
        mock_save.assert_called_once()
        self.assertEqual(result["updated_fields"]["Name"], "Sambhav Mehra")

if __name__ == "__main__":
    unittest.main()
