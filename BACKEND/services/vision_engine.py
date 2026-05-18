"""
AERIS AI OS - Vision Engine
Screen capture and camera analysis using Groq vision models.
"""
import logging
import os
import base64

logger = logging.getLogger(__name__)


class VisionEngine:
    """AI-powered screen and camera analysis"""

    def __init__(self):
        pass

    def _init_client(self):
        pass

    async def analyze_screen(self, prompt=None):
        """Capture and analyze the current screen with comprehensive detail
        Note: Overlay is now triggered by system_automation.py before calling this method
        """
        if prompt is None:
            prompt = """Analyze this screen in EXTREME DETAIL and provide a COMPREHENSIVE STRUCTURED REPORT:

1. **Application Identification**: What application/website is open? What is the full title or URL?

2. **Primary Content**: What is the main content being displayed? Describe the central focus area in detail.

3. **All Visible Text**: Read and transcribe EVERY visible piece of text including:
   - Headers, titles, and main text
   - Button labels
   - Menu items
   - Navigation elements
   - Input field labels and placeholders
   - Status messages or notifications
   - Any data, numbers, or metrics shown

4. **Visual Layout**: Describe the page/window structure:
   - Where is content positioned (top, center, bottom)?
   - Any sidebars, toolbars, or panels?
   - Color scheme and visual hierarchy

5. **UI Elements**: List all interactive elements (buttons, toggles, dropdowns, forms):
   - What actions are available?
   - Are any elements highlighted or selected?

6. **Data & Information**: What data/information is being presented?
   - Lists, tables, or dashboards?
   - User information or settings?
   - Live data or real-time updates?

7. **Status & Indicators**: Any status bars, loading indicators, notifications, or alerts?

8. **Context & Purpose**: What is the user likely doing right now? What is the overall purpose of this screen?

Provide a VERY DETAILED, point-by-point structured analysis. Do not omit any visible text or important UI element."""
        
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()
            path = os.path.join("data", "vision_screen.png")
            screenshot.save(path)
            return await self._analyze_image(path, prompt)
        except Exception as e:
            return f"Screen capture error: {e}"

    async def analyze_camera(self, prompt="Describe what you see from the camera."):
        """Capture and analyze camera feed"""
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return "Camera not available"
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return "Failed to capture camera frame"
            path = os.path.join("data", "vision_camera.png")
            cv2.imwrite(path, frame)
            return await self._analyze_image(path, prompt)
        except Exception as e:
            return f"Camera error: {e}"

    def take_camera_photo(self):
        """Capture a photo from the webcam and save it to disk. Returns the saved file path."""
        try:
            import cv2
            from datetime import datetime
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return {"success": False, "error": "Camera not available"}
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return {"success": False, "error": "Failed to capture camera frame"}
            
            screenshots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"camera_photo_{timestamp}.png"
            filepath = os.path.join(screenshots_dir, filename)
            cv2.imwrite(filepath, frame)
            logger.info(f"Camera photo saved: {filepath}")
            return {"success": True, "path": filepath, "output": f"Photo captured and saved at {filepath}"}
        except Exception as e:
            return {"success": False, "error": f"Camera photo error: {e}"}

    async def analyze_image(self, image_path, prompt="Describe this image in detail."):
        """Analyze a specific image file"""
        if not os.path.exists(image_path):
            return f"Image not found: {image_path}"
        return await self._analyze_image(image_path, prompt)

    async def _analyze_image(self, image_path, prompt):
        """Send image to AI Engine for analysis"""
        try:
            from ai_engine import ai_engine
            import base64
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")
            return await ai_engine.vision(prompt, img_b64)
        except Exception as e:
            logger.error(f"Vision analysis error: {e}")
            return f"Vision analysis failed: {e}"

    def ocr_screen(self):
        """Extract text from screen using EasyOCR"""
        try:
            import pyautogui
            import easyocr
            screenshot = pyautogui.screenshot()
            path = os.path.join("data", "ocr_screen.png")
            screenshot.save(path)

            reader = easyocr.Reader(["en"], gpu=False)
            results = reader.readtext(path)
            text = " ".join([r[1] for r in results])
            return text if text.strip() else "No text detected on screen."
        except Exception as e:
            return f"OCR error: {e}"

    def detect_faces(self):
        """Detect faces from the camera feed for biometric recognition"""
        try:
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return {"success": False, "error": "Camera not available"}
            ret, frame = cap.read()
            cap.release()
            if not ret:
                return {"success": False, "error": "Failed to capture camera frame"}
            
            # Use basic haarcascade for face detection
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            face_cascade = cv2.CascadeClassifier(cascade_path)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)
            
            # Could integrate with DeepFace here for actual identification (biometrics)
            return {
                "success": True, 
                "faces_detected": len(faces),
                "bounding_boxes": faces.tolist() if len(faces) > 0 else []
            }
        except Exception as e:
            return {"success": False, "error": f"Face detection error: {e}"}
