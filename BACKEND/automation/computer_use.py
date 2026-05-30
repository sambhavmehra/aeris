"""
AERIS — Computer Use Engine (Vision-Based UI Automation)
Like Claude's "Computer Use" — AERIS can SEE the screen, understand
UI elements, locate click targets by coordinates, and autonomously
interact with any application using pyautogui.

Architecture:
  1. Capture screenshot
  2. Send to AI Vision → get structured element map
  3. Parse click/type coordinates
  4. Execute pyautogui actions
  5. Verify result with follow-up screenshot
"""
from __future__ import annotations

import json
import logging
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("AerisComputerUse")


@dataclass
class UIAction:
    """A single UI action to execute on screen."""
    action_type: str  # "click", "double_click", "right_click", "type", "hotkey", "scroll", "drag"
    x: int = 0
    y: int = 0
    text: str = ""
    keys: list = field(default_factory=list)
    scroll_amount: int = 0
    confidence: float = 0.0
    description: str = ""
    drag_to_x: int = 0
    drag_to_y: int = 0

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "x": self.x, "y": self.y,
            "text": self.text,
            "keys": self.keys,
            "scroll_amount": self.scroll_amount,
            "confidence": self.confidence,
            "description": self.description,
        }


@dataclass
class ComputerUseResult:
    """Result of a computer use operation."""
    success: bool
    actions_taken: List[UIAction]
    screenshot_before: str = ""
    screenshot_after: str = ""
    vision_analysis: str = ""
    error: Optional[str] = None
    verification: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "actions_taken": [a.to_dict() for a in self.actions_taken],
            "screenshot_before": self.screenshot_before,
            "screenshot_after": self.screenshot_after,
            "vision_analysis": self.vision_analysis,
            "error": self.error,
            "verification": self.verification,
        }


class ComputerUseEngine:
    """
    Autonomous screen interaction engine.
    AERIS can see the screen and interact with any UI element.
    """

    DATA_DIR = Path(__file__).parent / "data" / "computer_use"
    MAX_RETRIES = 3

    def __init__(self):
        from config import settings
        self.DATA_DIR = settings.DATA_DIR / "computer_use"
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        from ai_engine import ai_engine
        self._ai_engine = ai_engine
        self._action_history: List[Dict[str, Any]] = []

    def _vision_sync(self, prompt: str, image_b64: str) -> str:
        """Synchronous wrapper around AIEngine's async vision method."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(asyncio.run, self._ai_engine.vision(prompt, image_b64)).result()
            return loop.run_until_complete(self._ai_engine.vision(prompt, image_b64))
        except RuntimeError:
            return asyncio.run(self._ai_engine.vision(prompt, image_b64))

    # ═════════════════════════════════════════════════════════════════
    #  PUBLIC API
    # ═════════════════════════════════════════════════════════════════

    def execute_task(self, instruction: str, max_steps: int = 5) -> ComputerUseResult:
        """
        Execute a multi-step computer use task.
        Example: "Click the search bar in Chrome and type 'python tutorials'"
        """
        actions_taken = []
        screenshot_before = ""

        try:
            import pyautogui
            pyautogui.FAILSAFE = False   # Disabled: AI vision moves mouse to corners during analysis
            pyautogui.PAUSE = 0.5       # Slightly longer pause for reliable UI settling

            for step in range(max_steps):
                # 1. Capture current screen
                screenshot_path = self._capture_screen(f"step_{step}")
                if step == 0:
                    screenshot_before = screenshot_path

                # 2. Ask AI to analyze screen and determine next action
                remaining_instruction = instruction
                if actions_taken:
                    completed = ", ".join(a.description for a in actions_taken)
                    remaining_instruction = (
                        f"Original task: {instruction}\n"
                        f"Actions already completed: {completed}\n"
                        f"What is the NEXT action to take? If the task is complete, respond with DONE."
                    )

                action = self._analyze_and_plan(screenshot_path, remaining_instruction)

                if action is None or action.action_type == "done":
                    break

                # 3. Execute the action
                self._execute_action(action)
                actions_taken.append(action)
                time.sleep(0.5)  # Wait for UI to update

            # 4. Final verification screenshot
            screenshot_after = self._capture_screen("final")
            verification = self._verify_completion(screenshot_after, instruction)

            self._record_history(instruction, actions_taken, True)

            return ComputerUseResult(
                success=True,
                actions_taken=actions_taken,
                screenshot_before=screenshot_before,
                screenshot_after=screenshot_after,
                verification=verification,
            )

        except Exception as e:
            logger.error(f"ComputerUse error: {e}")
            self._record_history(instruction, actions_taken, False, str(e))
            return ComputerUseResult(
                success=False,
                actions_taken=actions_taken,
                error=str(e),
            )

    def click_element(self, description: str) -> ComputerUseResult:
        """Find and click a specific UI element by description."""
        return self.execute_task(f"Find and click on: {description}", max_steps=2)

    def type_in_field(self, field_description: str, text: str) -> ComputerUseResult:
        """Find a text field and type text into it."""
        return self.execute_task(
            f"Click on the text field described as '{field_description}', then type: {text}",
            max_steps=3,
        )

    def find_element(self, description: str) -> Dict[str, Any]:
        """Find a UI element on screen and return its coordinates."""
        try:
            screenshot_path = self._capture_screen("find")
            action = self._analyze_and_plan(
                screenshot_path,
                f"Find the UI element: {description}. Return its X,Y coordinates. Do NOT click it.",
            )
            if action:
                return {
                    "success": True,
                    "x": action.x, "y": action.y,
                    "confidence": action.confidence,
                    "description": action.description,
                }
            return {"success": False, "error": "Element not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═════════════════════════════════════════════════════════════════
    #  SCREEN CAPTURE
    # ═════════════════════════════════════════════════════════════════

    def _capture_screen(self, label: str = "capture") -> str:
        """Take a screenshot and save it."""
        import pyautogui
        pyautogui.FAILSAFE = False   # Prevent corner-triggered crashes during automated capture
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cu_{label}_{timestamp}.png"
        filepath = str(self.DATA_DIR / filename)
        screenshot = pyautogui.screenshot()
        screenshot.save(filepath)
        return filepath

    # ═════════════════════════════════════════════════════════════════
    #  AI VISION ANALYSIS
    # ═════════════════════════════════════════════════════════════════

    def _analyze_and_plan(self, screenshot_path: str, instruction: str) -> Optional[UIAction]:
        """Send screenshot to AI vision via APIGateway and get the next action."""
        try:
            import base64
            with open(screenshot_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            prompt = (
                f"You are an AI that controls a computer by looking at screenshots.\n"
                f"The user wants: {instruction}\n\n"
                f"Analyze this screenshot and determine the SINGLE NEXT action to take.\n"
                f"If the task is already complete, respond with: {{\"action\": \"done\"}}\n\n"
                f"Otherwise respond with ONLY a JSON object:\n"
                f'{{"action": "click|double_click|right_click|type|hotkey|scroll", '
                f'"x": <pixel_x>, "y": <pixel_y>, '
                f'"text": "<text_to_type_if_action_is_type>", '
                f'"keys": ["<key1>", "<key2>"] (for hotkey only), '
                f'"scroll_amount": <int_for_scroll>, '
                f'"confidence": <0.0_to_1.0>, '
                f'"description": "<what_this_action_does>"}}\n\n'
                f"RULES:\n"
                f"- Coordinates must be precise pixel positions of the target element center\n"
                f"- For typing, click the field first in one action, then type in the next\n"
                f"- Only return ONE action at a time\n"
                f"- Set confidence to how sure you are (0.0 = guess, 1.0 = certain)"
            )

            raw = self._vision_sync(prompt, img_b64)
            return self._parse_action(raw)

        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return None

    def _parse_action(self, raw_response: str) -> Optional[UIAction]:
        """Parse the AI's JSON response into a UIAction."""
        try:
            import re
            # Extract JSON from response
            match = re.search(r'\{.*\}', raw_response, re.DOTALL)
            if not match:
                return None
            data = json.loads(match.group(0))

            action_type = data.get("action", "").lower()
            if action_type == "done":
                return UIAction(action_type="done", description="Task complete")

            return UIAction(
                action_type=action_type,
                x=int(data.get("x", 0)),
                y=int(data.get("y", 0)),
                text=data.get("text", ""),
                keys=data.get("keys", []),
                scroll_amount=int(data.get("scroll_amount", 0)),
                confidence=float(data.get("confidence", 0.5)),
                description=data.get("description", ""),
            )
        except Exception as e:
            logger.error(f"Failed to parse action: {e}, raw: {raw_response[:200]}")
            return None

    # ═════════════════════════════════════════════════════════════════
    #  ACTION EXECUTION
    # ═════════════════════════════════════════════════════════════════

    def _execute_action(self, action: UIAction):
        """Execute a single UI action using pyautogui."""
        import pyautogui

        logger.info(f"Executing: {action.action_type} at ({action.x}, {action.y}) - {action.description}")

        if action.action_type == "click":
            pyautogui.click(action.x, action.y)
        elif action.action_type == "double_click":
            pyautogui.doubleClick(action.x, action.y)
        elif action.action_type == "right_click":
            pyautogui.rightClick(action.x, action.y)
        elif action.action_type == "type":
            if action.x and action.y:
                pyautogui.click(action.x, action.y)
                time.sleep(0.2)
            pyautogui.write(action.text, interval=0.05)  # write() handles Unicode better than typewrite()
        elif action.action_type == "hotkey":
            if action.keys:
                pyautogui.hotkey(*action.keys)
        elif action.action_type == "scroll":
            pyautogui.scroll(action.scroll_amount, action.x or None, action.y or None)
        elif action.action_type == "drag":
            pyautogui.moveTo(action.x, action.y)
            pyautogui.drag(action.drag_to_x - action.x, action.drag_to_y - action.y, duration=0.5)
        else:
            logger.warning(f"Unknown action type: {action.action_type}")

    # ═════════════════════════════════════════════════════════════════
    #  VERIFICATION
    # ═════════════════════════════════════════════════════════════════

    def _verify_completion(self, screenshot_path: str, original_task: str) -> str:
        """Take a final screenshot and verify the task was completed via APIGateway."""
        try:
            import base64
            with open(screenshot_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            prompt = (
                f"The user asked the AI to: '{original_task}'\n\n"
                f"Look at this screenshot of the result. Was the task completed successfully?\n"
                f"Provide a brief assessment."
            )

            return self._vision_sync(prompt, img_b64)
        except Exception as e:
            return f"Verification failed: {e}"

    # ═════════════════════════════════════════════════════════════════
    #  HISTORY & STATE
    # ═════════════════════════════════════════════════════════════════

    def _record_history(self, task: str, actions: List[UIAction], success: bool, error: str = ""):
        self._action_history.append({
            "task": task,
            "actions": [a.to_dict() for a in actions],
            "success": success,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        })
        # Keep last 50
        self._action_history = self._action_history[-50:]

    def get_history(self) -> List[Dict]:
        return self._action_history
