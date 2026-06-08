import os
import sys
import time
import json
import logging
import asyncio
import subprocess
import base64
import pyautogui
from PIL import Image
from typing import Optional, Tuple, Any

from config import settings
from services.notification_hub import send_desktop_notification

logger = logging.getLogger("aeris.screen_monitor")

_screen_monitor_instance: Optional['ScreenMonitor'] = None

class ScreenMonitor:
    def __init__(self):
        self.is_monitoring = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_screenshot_pixels: Optional[list] = None
        self._overlay_process: Optional[subprocess.Popen] = None
        self._last_suggestion: Optional[dict] = None
        self._lock = asyncio.Lock()
        
    def start_monitoring(self):
        """Starts the background screen monitoring loop."""
        if self.is_monitoring:
            logger.info("Screen monitoring is already running.")
            return
        
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("AERIS Continuous Screen Monitoring service started.")
        
    def stop_monitoring(self):
        """Stops the background screen monitoring loop and cleans up the overlay window."""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
            
        self.dismiss_overlay()
        self._last_screenshot_pixels = None
        self._last_suggestion = None
        logger.info("AERIS Continuous Screen Monitoring service stopped.")
        
    def dismiss_overlay(self):
        """Terminates any open suggestion overlay window."""
        if self._overlay_process:
            try:
                self._overlay_process.terminate()
                self._overlay_process.wait(timeout=1.0)
            except Exception:
                try:
                    self._overlay_process.kill()
                except Exception:
                    pass
            self._overlay_process = None
            logger.debug("Overlay window process dismissed.")

    def _detect_screen_change(self, img: Image.Image) -> bool:
        """Downsamples screenshot to 16x16 grayscale to detect significant screen changes."""
        small = img.resize((16, 16)).convert("L")
        current_pixels = list(small.getdata())
        
        if self._last_screenshot_pixels is None:
            self._last_screenshot_pixels = current_pixels
            return True
            
        diff = sum(abs(p1 - p2) for p1, p2 in zip(self._last_screenshot_pixels, current_pixels))
        max_diff = 255 * 256
        diff_percentage = (diff / max_diff) * 100.0
        
        self._last_screenshot_pixels = current_pixels
        logger.debug(f"[ScreenMonitor] Screen pixel diff: {diff_percentage:.2f}%")
        
        # 1.5% threshold filters out minor cursor blinking/typing noise but catches window changes/scrolling
        return diff_percentage >= 1.5

    async def _monitoring_loop(self):
        """Periodically screenshots, checks for changes, and runs Gemini Vision analysis."""
        # Wait 3 seconds initially to give user time to settle
        await asyncio.sleep(3.0)
        
        while self.is_monitoring:
            try:
                # 1. Take screenshot
                loop = asyncio.get_event_loop()
                screenshot = await loop.run_in_executor(None, pyautogui.screenshot)
                
                # 2. Check if the screen has changed
                if self._detect_screen_change(screenshot):
                    logger.info("[ScreenMonitor] Change detected, running Gemini Vision analysis...")
                    
                    # Save temporary file for base64 extraction
                    temp_dir = Path(settings.DATA_DIR) / "temp"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    temp_path = temp_dir / "monitor_screenshot.png"
                    
                    await loop.run_in_executor(None, lambda: screenshot.save(temp_path))
                    
                    # Convert to base64
                    with open(temp_path, "rb") as f:
                        img_b64 = base64.b64encode(f.read()).decode("utf-8")
                        
                    # 3. Formulate prompt for screen analysis
                    prompt = """
You are a real-time system monitoring assistant for the user's desktop.
Look at the user's screen. Your job is to determine:
1. Is the user facing an issue, syntax error, compiling error, command line failure, broken link, or struggling with their current task?
2. Is there a repetitive task or sub-optimal workflow that can be optimized or automated?

If you detect any issues, errors, struggles, or optimizations:
Set `issue_detected` to true and provide:
- `suggestion`: A friendly, concise instruction/suggestion in Hindi or Hinglish, addressing the user as "Sir" (e.g. "Sir, aapke index.js file me ek syntax error hai. Line 15 par paranthesis check kijiye."). Keep it within 1-2 short sentences so it fits cleanly on a floating card.
- `implementation_plan`: A step-by-step description of how to fix or automate this (e.g., "Fix the syntax error in index.js by changing line 15 to...").
- `command_to_run`: A concrete shell command, python code script, or file edit instruction that AERIS can execute to resolve the issue. If it's a code edit, specify the changes.

If NO issue or struggle is detected, set `issue_detected` to false.

Respond ONLY with valid JSON in this structure:
{
  "issue_detected": true,
  "confidence": 0.9,
  "suggestion": "...",
  "implementation_plan": "...",
  "command_to_run": "..."
}
"""
                    from ai_engine import ai_engine
                    raw_resp = await ai_engine.vision(prompt, img_b64)
                    
                    # Parse JSON safely
                    try:
                        clean_resp = raw_resp.strip().strip("```json").strip("```").strip()
                        data = json.loads(clean_resp)
                        
                        if data.get("issue_detected") and data.get("confidence", 0.0) >= 0.7:
                            self._last_suggestion = data
                            logger.info(f"[ScreenMonitor] Issue detected! Suggestion: {data.get('suggestion')}")
                            
                            # Trigger suggestion overlay GUI
                            await self._show_suggestion_overlay(data.get("suggestion"))
                    except Exception as e:
                        logger.warning(f"[ScreenMonitor] Failed to parse vision JSON or response: {e}. Raw: {raw_resp[:200]}")
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ScreenMonitor] Error in monitoring loop: {e}")
                
            # Check interval is 15 seconds
            await asyncio.sleep(15.0)

    async def _show_suggestion_overlay(self, suggestion_text: str):
        """Launches the Tkinter GUI overlay as a separate subprocess."""
        async with self._lock:
            self.dismiss_overlay()
            
            # Form path to overlay script
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "overlay_window.py")
            
            # Start Tkinter overlay subprocess
            try:
                cmd = [sys.executable, script_path, "--text", suggestion_text, "--id", "latest"]
                self._overlay_process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL
                )
                logger.debug("Spawned suggestion overlay window subprocess.")
            except Exception as e:
                logger.error(f"Failed to spawn suggestion overlay: {e}")

    async def implement_last_suggestion(self) -> Tuple[bool, str]:
        """Triggers the execution/repair of the last generated suggestion."""
        if not self._last_suggestion:
            return False, "Sir, mere paas abhi koi active suggestion nahi hai implement karne ke liye."
            
        suggestion = self._last_suggestion
        self._last_suggestion = None  # Consume it
        self.dismiss_overlay()
        
        plan = suggestion.get("implementation_plan", "")
        cmd = suggestion.get("command_to_run", "")
        
        if not plan and not cmd:
            return False, "Sir, is suggestion ke paas koi implementation plan ya command nahi hai."
            
        logger.info(f"[ScreenMonitor] Implementing suggestion: plan='{plan}', command='{cmd}'")
        
        # Build prompt for the brain to execute the correction plan
        exec_prompt = f"Implement this correction plan on the workspace:\nPlan: {plan}\nCommand to run: {cmd}"
        
        # Let's send a desktop toast that we started implementing
        send_desktop_notification("AERIS: Implementation", "Sir, I am implementing the correction plan now...")
        
        try:
            from brain import brain
            result = await brain.process(exec_prompt)
            
            success = result.get("success", True)
            if success:
                resp_text = f"Sir, mainne correction implement kar diya hai: {result.get('response', '')}"
                send_desktop_notification("AERIS: Success", "Sir, suggestion has been successfully implemented.")
                return True, resp_text
            else:
                resp_text = f"Sir, implementation me koi dikkat aayi: {result.get('response', '')}"
                send_desktop_notification("AERIS: Failed", "Sir, suggestion implementation encountered a failure.")
                return False, resp_text
        except Exception as e:
            logger.error(f"Error during overlay implementation execution: {e}")
            send_desktop_notification("AERIS: Error", "Sir, suggestion implementation crashed.")
            return False, f"Sir, implementation execute karne me crash ho gaya: {e}"

    async def check_screen_and_suggest_now(self) -> str:
        """Immediately captures the screen, runs Gemini Vision, and generates suggestions on demand."""
        try:
            loop = asyncio.get_event_loop()
            screenshot = await loop.run_in_executor(None, pyautogui.screenshot)
            
            temp_dir = Path(settings.DATA_DIR) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / "on_demand_screenshot.png"
            
            await loop.run_in_executor(None, lambda: screenshot.save(temp_path))
            
            with open(temp_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
                
            prompt = """
You are a real-time system monitoring assistant for the user's desktop.
Look at the user's screen. Your job is to determine:
1. Is the user facing an issue, syntax error, compiling error, command line failure, broken link, or struggling with their current task?
2. Is there a repetitive task or sub-optimal workflow that can be optimized or automated?

If you detect any issues, errors, struggles, or optimizations:
Set `issue_detected` to true and provide:
- `suggestion`: A friendly, concise instruction/suggestion in Hindi or Hinglish, addressing the user as "Sir" (e.g. "Sir, aapke index.js file me ek syntax error hai. Line 15 par paranthesis check kijiye."). Keep it within 1-2 short sentences so it fits cleanly on a floating card.
- `implementation_plan`: A step-by-step description of how to fix or automate this (e.g., "Fix the syntax error in index.js by changing line 15 to...").
- `command_to_run`: A concrete shell command, python code script, or file edit instruction that AERIS can execute to resolve the issue. If it's a code edit, specify the changes.

If NO issue or struggle is detected, set `issue_detected` to false.

Respond ONLY with valid JSON in this structure:
{
  "issue_detected": true,
  "confidence": 0.9,
  "suggestion": "...",
  "implementation_plan": "...",
  "command_to_run": "..."
}
"""
            from ai_engine import ai_engine
            raw_resp = await ai_engine.vision(prompt, img_b64)
            
            try:
                clean_resp = raw_resp.strip().strip("```json").strip("```").strip()
                data = json.loads(clean_resp)
                
                if data.get("issue_detected") and data.get("confidence", 0.0) >= 0.7:
                    self._last_suggestion = data
                    await self._show_suggestion_overlay(data.get("suggestion"))
                    return f"Sir, maine aapki screen analyze ki hai aur ek suggestion mila hai: **\"{data.get('suggestion')}\"**"
                else:
                    return "Sir, maine aapki screen check ki. Abhi mujhe koi issue ya optimization nahi dikh raha hai. Sab kuch bilkul sahi chal raha hai!"
            except Exception as e:
                logger.warning(f"Failed to parse vision JSON: {e}. Raw: {raw_resp[:200]}")
                return "Sir, screen check karne me vision response parse nahi ho paya."
                
        except Exception as e:
            logger.error(f"On-demand screen check failed: {e}")
            return f"Sir, screen analyze karne me error aayi: {e}"


from pathlib import Path

def get_screen_monitor() -> ScreenMonitor:
    global _screen_monitor_instance
    if _screen_monitor_instance is None:
        _screen_monitor_instance = ScreenMonitor()
    return _screen_monitor_instance
