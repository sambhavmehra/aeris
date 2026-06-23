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
from pathlib import Path
from typing import Optional, Tuple, Any

from config import settings
from services.notification_hub import send_desktop_notification

logger = logging.getLogger("aeris.screen_monitor")

_screen_monitor_instance: Optional['ScreenMonitor'] = None

class ScreenMonitor:
    def __init__(self):
        self.is_monitoring = False
        self.crop_box: Optional[Tuple[int, int, int, int]] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_screenshot_pixels: Optional[list] = None
        self._overlay_process: Optional[subprocess.Popen] = None
        self._floating_process: Optional[subprocess.Popen] = None
        self._selection_process: Optional[subprocess.Popen] = None
        self._last_suggestion: Optional[dict] = None
        self._lock = asyncio.Lock()
        self._pending_query: Optional[str] = None
        
    def start_monitoring(self):
        """Starts the background screen monitoring loop."""
        if self.is_monitoring:
            logger.info("Screen monitoring is already running.")
            return
        
        self.is_monitoring = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        self.start_floating_controller()  # Launch global desktop controller
        logger.info("AERIS Continuous Screen Monitoring service started.")
        
    def stop_monitoring(self):
        """Stops the background screen monitoring loop and cleans up the overlay window."""
        self.is_monitoring = False
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
            
        self.dismiss_overlay()
        self.stop_floating_controller()
        self.clear_crop_box()
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

    def set_crop_box(self, x1: int, y1: int, x2: int, y2: int):
        """Sets a bounding box region to crop screenshots and analyze."""
        self.crop_box = (x1, y1, x2, y2)
        logger.info(f"ScreenMonitor crop box set to: {self.crop_box}")
        send_desktop_notification("AERIS: Selection Set", f"Sir, crop box set to coordinates {self.crop_box}")

    def clear_crop_box(self):
        """Resets the crop box to capture full screen."""
        self.crop_box = None
        logger.info("ScreenMonitor crop box cleared")
        send_desktop_notification("AERIS: Selection Reset", "Sir, monitoring region reset to full screen.")

    def set_pending_query(self, query: Optional[str]):
        """Sets a pending query for the next screen selection."""
        self._pending_query = query
        logger.info(f"Pending screen query set: {query}")

    def get_and_clear_pending_query(self) -> Optional[str]:
        """Gets and clears the pending query."""
        q = self._pending_query
        self._pending_query = None
        return q

    def trigger_selection(self):
        """Launches the Tkinter selection canvas tool subprocess."""
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "selection_tool.py")
        
        api_port = settings.API_PORT
        api_host = settings.API_HOST
        if api_host in ("0.0.0.0", "::"):
            api_host = "127.0.0.1"
        api_url = f"http://{api_host}:{api_port}"
        
        try:
            cmd = [sys.executable, script_path, "--url", api_url]
            self._selection_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Spawned selection canvas overlay subprocess.")
        except Exception as e:
            logger.error(f"Failed to spawn selection tool: {e}")

    def start_floating_controller(self):
        """Launches the Tkinter floating controller subprocess."""
        script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "floating_controller.py")
        
        api_port = settings.API_PORT
        api_host = settings.API_HOST
        if api_host in ("0.0.0.0", "::"):
            api_host = "127.0.0.1"
        api_url = f"http://{api_host}:{api_port}"
        
        try:
            cmd = [sys.executable, script_path, "--url", api_url]
            self._floating_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            logger.info("Spawned floating controller toolbar subprocess.")
        except Exception as e:
            logger.error(f"Failed to spawn floating controller: {e}")

    def stop_floating_controller(self):
        """Terminates the Tkinter floating controller subprocess."""
        if self._floating_process:
            try:
                self._floating_process.terminate()
                self._floating_process.wait(timeout=1.0)
            except Exception:
                try:
                    self._floating_process.kill()
                except Exception:
                    pass
            self._floating_process = None
            logger.info("Floating controller toolbar dismissed.")

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

    async def _analyze_image(self, screenshot: Image.Image) -> Optional[dict]:
        """Runs Gemini Vision analysis. Fallback to web search search if requested by vision model."""
        loop = asyncio.get_event_loop()
        temp_dir = Path(settings.DATA_DIR) / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / "monitor_screenshot.png"
        
        await loop.run_in_executor(None, lambda: screenshot.save(temp_path))
        
        with open(temp_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        prompt = """
You are a real-time system monitoring assistant for the user's desktop.
Look at the user's screen. Your job is to determine:
1. Is the user facing an issue, syntax error, compiling error, command line failure, broken link, or struggling with their current task?
2. Is there a logo, concept, brand, tool, or library shown that requires external search/fact-checking to explain or suggest a fix?
3. Is there a repetitive task or sub-optimal workflow that can be optimized or automated?

If you detect any issues, errors, struggles, or optimizations:
Set `issue_detected` to true and provide:
- `suggestion`: A friendly, concise instruction/suggestion in Hindi or Hinglish, addressing the user as "Sir". Keep it within 1-2 short sentences so it fits cleanly on a floating card.
- `implementation_plan`: A step-by-step description of how to fix or automate this.
- `command_to_run`: A concrete shell command, python code script, or file edit instruction that AERIS can execute to resolve the issue.
- `web_search_query`: If you see a specific error message, tool, library, logo, brand, or concept that you lack full up-to-date context on, provide a targeted search query string to look up online. Otherwise, omit this field or leave it as null/empty.

If NO issue or struggle is detected, set `issue_detected` to false.

Respond ONLY with valid JSON in this structure:
{
  "issue_detected": true,
  "confidence": 0.9,
  "suggestion": "...",
  "implementation_plan": "...",
  "command_to_run": "...",
  "web_search_query": "..."
}
"""
        from ai_engine import ai_engine
        raw_resp = await ai_engine.vision(prompt, img_b64)
        
        try:
            clean_resp = raw_resp.strip().strip("```json").strip("```").strip()
            data = json.loads(clean_resp)
            
            # Check if web search is requested for context enrichment
            web_query = data.get("web_search_query")
            if data.get("issue_detected") and web_query and web_query.strip():
                logger.info(f"[ScreenMonitor] Vision requested search for context: '{web_query}'")
                from brain import brain
                search_res = await brain.process(f"search {web_query}")
                search_info = search_res.get("response", "")
                
                logger.info("[ScreenMonitor] Context retrieved. Re-evaluating screen with search context...")
                
                enrich_prompt = f"""
You are a real-time system monitoring assistant.
You recently analyzed the screen and wanted details on "{web_query}".
We ran a web search and found this information:
=== SEARCH DATA ===
{search_info}
=== END SEARCH DATA ===

Now, look at the screen image again. Combine your visual observations with the search data to generate the final suggestions.
Respond ONLY with valid JSON in this structure:
{{
  "issue_detected": true,
  "confidence": 0.9,
  "suggestion": "...",
  "implementation_plan": "...",
  "command_to_run": "..."
}}
"""
                raw_resp = await ai_engine.vision(enrich_prompt, img_b64)
                clean_resp = raw_resp.strip().strip("```json").strip("```").strip()
                data = json.loads(clean_resp)
                
            return data
        except Exception as e:
            logger.warning(f"[ScreenMonitor] Failed to parse vision JSON or response: {e}. Raw: {raw_resp[:200]}")
            return None

    async def _monitoring_loop(self):
        """Periodically screenshots, checks for changes, and runs Gemini Vision analysis."""
        # Wait 3 seconds initially to give user time to settle
        await asyncio.sleep(3.0)
        
        while self.is_monitoring:
            # Skip checking if user is currently using the screen selection tool
            if self._selection_process and self._selection_process.poll() is None:
                await asyncio.sleep(1.0)
                continue
                
            try:
                # 1. Take screenshot
                loop = asyncio.get_event_loop()
                screenshot = await loop.run_in_executor(None, pyautogui.screenshot)
                
                # Crop if selection area is active
                if self.crop_box:
                    screenshot = screenshot.crop(self.crop_box)
                
                # 2. Check if the screen has changed
                if self._detect_screen_change(screenshot):
                    logger.info("[ScreenMonitor] Change detected, running Gemini Vision analysis...")
                    
                    data = await self._analyze_image(screenshot)
                    
                    if data and data.get("issue_detected") and data.get("confidence", 0.0) >= 0.7:
                        self._last_suggestion = data
                        logger.info(f"[ScreenMonitor] Issue detected! Suggestion: {data.get('suggestion')}")
                        
                        # Trigger suggestion overlay GUI
                        await self._show_suggestion_overlay(data.get("suggestion"))
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[ScreenMonitor] Error in monitoring loop: {e}")
                
            # Reduced check interval to 5.0 seconds as requested
            await asyncio.sleep(5.0)

    async def _show_suggestion_overlay(self, suggestion_text: str):
        """Launches the Tkinter GUI overlay as a separate subprocess."""
        async with self._lock:
            self.dismiss_overlay()
            
            # Form path to overlay script
            script_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "utils", "overlay_window.py")
            
            api_port = settings.API_PORT
            api_host = settings.API_HOST
            if api_host in ("0.0.0.0", "::"):
                api_host = "127.0.0.1"
            api_url = f"http://{api_host}:{api_port}"
            
            # Start Tkinter overlay subprocess
            try:
                cmd = [sys.executable, script_path, "--text", suggestion_text, "--id", "latest", "--url", api_url]
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
            
            if self.crop_box:
                screenshot = screenshot.crop(self.crop_box)
                
            data = await self._analyze_image(screenshot)
            
            if data and data.get("issue_detected") and data.get("confidence", 0.0) >= 0.7:
                self._last_suggestion = data
                await self._show_suggestion_overlay(data.get("suggestion"))
                return f"Sir, maine aapki screen analyze ki hai aur ek suggestion mila hai: **\"{data.get('suggestion')}\"**"
            else:
                return "Sir, maine aapki screen check ki. Abhi mujhe koi issue ya optimization nahi dikh raha hai. Sab kuch bilkul sahi chal raha hai!"
                
        except Exception as e:
            logger.error(f"On-demand screen check failed: {e}")
            return f"Sir, screen analyze karne me error aayi: {e}"

    async def analyze_region_with_query(self, x1: int, y1: int, x2: int, y2: int, query: str) -> dict:
        """Capture a specific screen region and answer the user's question about it."""
        try:
            logger.info(f"[ScreenMonitor] Analyzing region ({x1}, {y1}) to ({x2}, {y2}) with query: '{query}'")
            loop = asyncio.get_event_loop()
            screenshot = await loop.run_in_executor(None, pyautogui.screenshot)
            
            # Crop to coordinates
            cropped_img = screenshot.crop((x1, y1, x2, y2))
            
            temp_dir = Path(settings.DATA_DIR) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            # Save to monitor_screenshot.png so overlays/other commands can reference the last cropped image
            temp_path = temp_dir / "monitor_screenshot.png"
            
            await loop.run_in_executor(None, lambda: cropped_img.save(temp_path))
            
            with open(temp_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
                
            prompt = f"""
The user has selected a specific area of their screen.
They are asking this question about it: "{query}"

Look at the image of their screen selection and answer their question clearly, concisely, and directly.
Respond in Hindi or Hinglish. Address the user as "Sir". Keep it short and readable, fitting within a small card.
"""
            from ai_engine import ai_engine
            raw_resp = await ai_engine.vision(prompt, img_b64)
            clean_resp = raw_resp.strip()
            
            # Show the answer in the suggestion overlay window
            await self._show_suggestion_overlay(clean_resp)
            
            # Also keep it in _last_suggestion for implementation/dismiss if needed
            self._last_suggestion = {
                "issue_detected": True,
                "confidence": 1.0,
                "suggestion": clean_resp,
                "implementation_plan": f"Answer user query: {query}",
                "command_to_run": ""
            }
            
            return {
                "success": True,
                "response": clean_resp,
                "crop_box": [x1, y1, x2, y2]
            }
            
        except Exception as e:
            logger.error(f"Region analysis with query failed: {e}")
            return {
                "success": False,
                "response": f"Sir, region query fail ho gaya: {e}"
            }

    async def locate_and_analyze_element(self, description: str) -> str:
        """Locates a screen region by matching its content description via Gemini Vision, crops it, and runs on-demand analysis."""
        try:
            logger.info(f"[ScreenMonitor] Locating element on screen matching: '{description}'")
            loop = asyncio.get_event_loop()
            screenshot = await loop.run_in_executor(None, pyautogui.screenshot)
            width, height = screenshot.size
            
            temp_dir = Path(settings.DATA_DIR) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_path = temp_dir / "locate_screenshot.png"
            
            await loop.run_in_executor(None, lambda: screenshot.save(temp_path))
            
            with open(temp_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
                
            locator_prompt = f"""
Analyze the user's screen screenshot.
Your task is to locate the visual element, text block, image, video player, code snippet, button, logo, or region that corresponds to the description: "{description}".

Return the exact coordinates (x1, y1, x2, y2) of the bounding box of that element in screen pixel coordinates.
The screen resolution is {width}x{height} (width x height).
Ensure your coordinates are within these bounds (0 <= x1, x2 <= {width} and 0 <= y1, y2 <= {height}).

Respond ONLY with valid JSON in this format:
{{
  "found": true,
  "box": [x1, y1, x2, y2],
  "reason": "..."
}}
If you cannot find anything matching the description, set "found" to false.
"""
            from ai_engine import ai_engine
            raw_resp = await ai_engine.vision(locator_prompt, img_b64)
            
            try:
                clean_resp = raw_resp.strip().strip("```json").strip("```").strip()
                data = json.loads(clean_resp)
                
                if data.get("found") and data.get("box"):
                    box = data.get("box")
                    x1, y1, x2, y2 = box[0], box[1], box[2], box[3]
                    
                    # Crop and verify size
                    if abs(x2 - x1) > 5 and abs(y2 - y1) > 5:
                        self.set_crop_box(x1, y1, x2, y2)
                        
                        # Immediately capture and analyze the cropped region
                        cropped = screenshot.crop((x1, y1, x2, y2))
                        analysis = await self._analyze_image(cropped)
                        
                        if analysis and analysis.get("issue_detected") and analysis.get("confidence", 0.0) >= 0.7:
                            self._last_suggestion = analysis
                            await self._show_suggestion_overlay(analysis.get("suggestion"))
                            return f"Sir, maine screen par '{description}' ko locate karke select kiya hai coordinate {box} par, aur ek suggestion mila hai: **\"{analysis.get('suggestion')}\"**"
                        else:
                            return f"Sir, maine screen par '{description}' ko select kiya coordinate {box} par. Lekin us region me abhi koi active issue ya optimization nahi dikh raha hai."
                
                return f"Sir, mujhe screen par '{description}' se match karta hua koi element nahi mila."
            except Exception as e:
                logger.warning(f"Failed to parse location/analysis response: {e}. Raw: {raw_resp[:200]}")
                return "Sir, coordinate location process me response parse nahi ho paya."
                
        except Exception as e:
            logger.error(f"Locate and analyze failed: {e}")
            return f"Sir, screen element locate karne me error aayi: {e}"

def get_screen_monitor() -> ScreenMonitor:
    global _screen_monitor_instance
    if _screen_monitor_instance is None:
        _screen_monitor_instance = ScreenMonitor()
    return _screen_monitor_instance
