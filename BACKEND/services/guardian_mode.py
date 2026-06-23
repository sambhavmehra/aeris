# -*- coding: utf-8 -*-
"""
AERIS — Guardian Mode Service
=============================
Provides a restricted security and privacy mode. Monitors and blocks unauthorized
processes, websites, and folders. Supports PIN and voice verification using Gemini.
"""

import os
import sys
import time
import json
import logging
import asyncio
import ctypes
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import psutil
from config import settings
from services.notification_hub import send_desktop_notification, send_telegram_notification

logger = logging.getLogger("aeris.guardian")

# ---------------------------------------------------------------------------
#  Audit Logger
# ---------------------------------------------------------------------------
class AuditLogger:
    """Logs all Guardian Mode security and activity events locally in JSON format."""
    
    def __init__(self, data_dir: Path):
        self.log_file = data_dir / "guardian_audit.json"
        
    def log_event(self, event_type: str, target: str, action: str, attempt: int, details: str):
        """Append a new timestamped event to the audit log."""
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "event_type": event_type,
            "target": target,
            "action": action,
            "attempt": attempt,
            "details": details
        }
        
        try:
            logs = []
            if self.log_file.exists():
                try:
                    logs = json.loads(self.log_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            
            logs.append(log_entry)
            # Limit log size to last 1000 entries
            if len(logs) > 1000:
                logs = logs[-1000:]
                
            self.log_file.write_text(json.dumps(logs, indent=2), encoding="utf-8")
            logger.info(f"[Guardian Audit] {event_type} - {target}: {action} ({details})")
        except Exception as e:
            logger.error(f"Failed to write to guardian audit log: {e}")
            
    def get_logs(self) -> List[Dict[str, Any]]:
        """Retrieve all audit logs."""
        if not self.log_file.exists():
            return []
        try:
            return json.loads(self.log_file.read_text(encoding="utf-8"))
        except Exception:
            return []

# ---------------------------------------------------------------------------
#  Config Manager
# ---------------------------------------------------------------------------
class ConfigManager:
    """Manages the configuration options for Guardian Mode."""
    
    def __init__(self, data_dir: Path):
        self.config_file = data_dir / "guardian_config.json"
        self.config: Dict[str, Any] = {
            "enabled": False,
            "blocked_apps": [
                "WhatsApp.exe", "Telegram.exe", "Discord.exe", "Signal.exe",
                "whatsapp", "telegram", "discord", "signal",
                "mssecurities", "keepass", "bitwarden", "outlook.exe"
            ],
            "blocked_domains": [
                "web.whatsapp.com", "mail.google.com", "instagram.com", "facebook.com",
                "paypal.com", "paytm.com", "binance.com", "coinbase.com", "banking"
            ],
            "protected_folders": [
                "Documents", "Pictures", "Downloads", "Desktop", "credentials", "private"
            ],
            "allowed_apps": [
                "notepad.exe", "calc.exe", "explorer.exe", "chrome.exe", "msedge.exe", "vlc.exe"
            ],
            "warning_limit": 0,
            "lock_after_attempts": 3,
            "owner_verification_method": "voice_pin",
            "pin": "1234",
            "secret_phrase": "sambhav"
        }
        self.load()
        
    def load(self):
        """Load configuration from disk."""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text(encoding="utf-8"))
                self.config.update(data)
            except Exception as e:
                logger.error(f"Failed to load guardian config: {e}")
                
    def save(self):
        """Save current configuration to disk."""
        try:
            self.config_file.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to save guardian config: {e}")
            
    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)
        
    def update(self, updates: Dict[str, Any]):
        self.config.update(updates)
        self.save()

# ---------------------------------------------------------------------------
#  Voice Matcher
# ---------------------------------------------------------------------------
class VoiceMatcher:
    """Handles owner voice registration and verification via Gemini audio similarity."""
    
    def __init__(self, data_dir: Path):
        self.ref_file = data_dir / "owner_voice_ref.wav"
        self.data_dir = data_dir
        
    def has_reference(self) -> bool:
        return self.ref_file.exists()
        
    def register_voice(self, audio_bytes: bytes) -> bool:
        """Register the owner's voice reference file."""
        try:
            self.ref_file.write_bytes(audio_bytes)
            logger.info("Owner voice reference registered successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to save voice reference: {e}")
            return False
            
    async def compare_voice(self, current_audio_bytes: bytes) -> Tuple[bool, float]:
        """Compare the speaker in the current voice command with the owner reference."""
        if not self.has_reference():
            logger.warning("Voice comparison requested but no reference voice exists.")
            return False, 0.0
            
        if not settings.has_gemini:
            logger.warning("Gemini API not configured. Cannot perform voice comparison.")
            return False, 0.0
            
        # Write current audio to a temp file
        temp_file = self.data_dir / "temp" / f"current_voice_{int(time.time())}.wav"
        temp_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            temp_file.write_bytes(current_audio_bytes)
            
            # Use Google GenAI SDK to compare
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            ref_bytes = self.ref_file.read_bytes()
            curr_bytes = temp_file.read_bytes()
            
            prompt = (
                "Analyze the two audio clips. Do they belong to the exact same speaker? "
                "Look at speaker voice characteristics like pitch, tone, tempo, and accent. "
                "Respond ONLY with a valid JSON object containing keys: 'match' (true/false) "
                "and 'confidence' (float between 0.0 and 1.0 representing similarity)."
            )
            
            loop = asyncio.get_event_loop()
            
            def _call_gemini():
                response = client.models.generate_content(
                    model=settings.GEMINI_MODEL,
                    contents=[
                        types.Part.from_bytes(data=ref_bytes, mime_type="audio/wav"),
                        types.Part.from_bytes(data=curr_bytes, mime_type="audio/wav"),
                        prompt
                    ]
                )
                return response.text.strip() if response.text else ""
                
            raw_text = await loop.run_in_executor(None, _call_gemini)
            
            try:
                # Clean code blocks
                clean = raw_text.strip().strip("```json").strip("```").strip()
                data = json.loads(clean)
                match = bool(data.get("match", False))
                confidence = float(data.get("confidence", 0.0))
                
                logger.info(f"Gemini Voice Matching Result: match={match}, confidence={confidence}")
                return match, confidence
            except Exception as pe:
                logger.warning(f"Failed to parse Gemini voice match response: {pe}. Raw: {raw_text}")
                # Fallback check: length comparison or similar simple check
                return False, 0.0
                
        except Exception as e:
            logger.error(f"Voice comparison failed: {e}")
            return False, 0.0
        finally:
            # Clean up temp file
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass

# ---------------------------------------------------------------------------
#  Action Engine
# ---------------------------------------------------------------------------
class ActionEngine:
    """Executes defensive actions like showing warnings, closing processes, and locking Windows."""
    
    def __init__(self, config_manager: ConfigManager, data_dir: Path):
        self.config = config_manager
        self.data_dir = data_dir
        self._overlay_proc: Optional[subprocess.Popen] = None
        
    def show_warning(self, msg: str, target: str):
        """Displays a native Windows toast notification and launches the Tkinter overlay."""
        # 1. Native Toast
        send_desktop_notification("AERIS Security Alert", f"Sir, access restricted: {msg}")
        
        # 2. Spawn Tkinter warning overlay if not already active
        if self._overlay_proc is None or self._overlay_proc.poll() is not None:
            script_path = Path(__file__).resolve().parent.parent / "utils" / "guardian_overlay.py"
            api_port = settings.API_PORT
            api_host = settings.API_HOST
            if api_host in ("0.0.0.0", "::"):
                api_host = "127.0.0.1"
            api_url = f"http://{api_host}:{api_port}"
            
            try:
                cmd = [sys.executable, str(script_path), "--text", msg, "--url", api_url]
                self._overlay_proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"Spawned guardian overlay for restriction: {target}")
            except Exception as e:
                logger.error(f"Failed to spawn guardian overlay: {e}")
                
    def dismiss_overlay(self):
        """Dismisses the open overlay window."""
        if self._overlay_proc:
            try:
                self._overlay_proc.terminate()
                self._overlay_proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._overlay_proc.kill()
                except Exception:
                    pass
            self._overlay_proc = None
            logger.info("Guardian overlay window dismissed.")
            
    def close_access(self, hwnd: int, process_name: Optional[str] = None):
        """Closes a restricted tab/window or terminates the restricted process."""
        # Send WM_CLOSE to window
        if hwnd:
            try:
                # 0x0010 is WM_CLOSE
                ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)
                logger.info(f"Sent WM_CLOSE to window handle {hwnd}")
            except Exception as e:
                logger.error(f"Failed to send WM_CLOSE to window: {e}")
                
        # Additionally terminate the process if process name is provided
        if process_name:
            proc_lower = process_name.lower()
            terminated = False
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'] and proc.info['name'].lower() == proc_lower:
                        proc.kill()
                        terminated = True
                except Exception:
                    pass
            if terminated:
                logger.info(f"Killed restricted process: {process_name}")
                
    def lock_session(self, target: str):
        """Locks the Windows workstation and sends a high-priority Telegram alert."""
        logger.warning(f"Locking Windows session due to critical/repeated attempts on {target}!")
        
        # 1. Lock Workstation
        try:
            ctypes.windll.user32.LockWorkStation()
        except Exception as e:
            logger.error(f"Failed to lock Workstation: {e}")
            
        # 2. Telegram Notify
        telegram_msg = (
            f"🚨 **AERIS GUARDIAN ALERT** 🚨\n\n"
            f"Sir, Guardian Mode has **LOCKED** the computer session.\n"
            f"- **Target violation**: `{target}`\n"
            f"- **Action**: Session Locked\n"
            f"- **Time**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
        )
        asyncio.create_task(send_telegram_notification(telegram_msg))
        
        # 3. Native Toast fallback
        send_desktop_notification("AERIS Lock Screen", "Guardian Mode locked the workstation.")

# ---------------------------------------------------------------------------
#  Policy Engine
# ---------------------------------------------------------------------------
class PolicyEngine:
    """Evaluates violation types and attempt counts to decide corresponding actions."""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        
    def decide_action(self, attempt: int) -> str:
        """
        Decide the action based on the violation attempt count.
        Returns: "warn", "close", "lock"
        """
        warning_limit = self.config.get("warning_limit", 1)
        lock_limit = self.config.get("lock_after_attempts", 3)
        
        if attempt <= warning_limit:
            return "warn"
        elif attempt < lock_limit:
            return "close"
        else:
            return "lock"

# ---------------------------------------------------------------------------
#  Guardian Mode Manager (Central Coordinator)
# ---------------------------------------------------------------------------
class GuardianModeManager:
    """Coordinates the Guardian Mode lifecycle: config, activity monitor, policy, actions, and verification."""
    
    def __init__(self):
        self.data_dir = settings.DATA_DIR
        self.config = ConfigManager(self.data_dir)
        self.audit_logger = AuditLogger(self.data_dir)
        self.voice_matcher = VoiceMatcher(self.data_dir)
        self.action_engine = ActionEngine(self.config, self.data_dir)
        self.policy_engine = PolicyEngine(self.config)
        
        # Runtime states
        self.is_active = self.config.get("enabled", False)
        self.overlay_active = False
        self.attempt_counters: Dict[str, int] = {}  # Tracks counts per restricted target
        self.baseline_partitions = self._get_logical_drives()
        
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Initialize monitoring if enabled at startup
        if self.is_active:
            self.start_monitoring()
            
    def _get_logical_drives(self) -> List[str]:
        """Returns active drive letters (e.g. ['C:\\', 'D:\\'])."""
        try:
            return [p.mountpoint for p in psutil.disk_partitions()]
        except Exception:
            return []
            
    def start_monitoring(self):
        """Launch the background Activity Monitor loop."""
        if self._monitor_task and not self._monitor_task.done():
            return
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Guardian Mode Activity Monitor started.")
        
    def stop_monitoring(self):
        """Cancel the background Activity Monitor loop."""
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        self.action_engine.dismiss_overlay()
        self.overlay_active = False
        logger.info("Guardian Mode Activity Monitor stopped.")
        
    def enable_guardian_mode(self, method: str = "text") -> str:
        """Enable Guardian Mode."""
        if self.is_active:
            return "Sir, Guardian Mode already active hai."
            
        self.is_active = True
        self.config.update({"enabled": True})
        self.attempt_counters.clear()
        self.baseline_partitions = self._get_logical_drives()
        self.start_monitoring()
        
        self.audit_logger.log_event(
            event_type="enable",
            target="system",
            action="activated",
            attempt=0,
            details=f"Activated via {method} command."
        )
        return "Guardian Mode active ho gaya hai, Sir. Restrictive policies apply ho gayi hain."
        
    def disable_guardian_mode(self, code: Optional[str] = None, bypass_auth: bool = False) -> Tuple[bool, str]:
        """Disable Guardian Mode with PIN or deactivation key verification."""
        if not self.is_active:
            return True, "Sir, Guardian Mode already off hai."
            
        if not bypass_auth:
            stored_pin = self.config.get("pin", "1234")
            secret_phrase = self.config.get("secret_phrase", "sambhav")
            
            # Check if code matches PIN or secret phrase
            if not code or code.strip() not in (stored_pin, secret_phrase):
                self.audit_logger.log_event(
                    event_type="auth_failure",
                    target="system",
                    action="rejected",
                    attempt=0,
                    details="Incorrect deactivation PIN/passphrase attempt."
                )
                return False, "Access Denied, Sir. Invalid security clearance."
                
        self.is_active = False
        self.config.update({"enabled": False})
        self.stop_monitoring()
        
        self.audit_logger.log_event(
            event_type="disable",
            target="system",
            action="deactivated",
            attempt=0,
            details="Deactivated successfully via verified clearance."
        )
        return True, "Guardian Mode has been disabled, Sir. Welcome back to Normal Mode."
        
    async def verify_voice_deactivation(self, audio_bytes: bytes) -> Tuple[bool, str]:
        """Verify owner voice reference similarity to disable Guardian Mode."""
        if not self.is_active:
            return True, "Sir, Guardian Mode already off hai."
            
        if not self.voice_matcher.has_reference():
            return False, "Sir, voice profile registered nahi hai. Please register reference voice first."
            
        matched, confidence = await self.voice_matcher.compare_voice(audio_bytes)
        if matched and confidence >= 0.75:
            self.disable_guardian_mode(bypass_auth=True)
            return True, f"Security clearance verified (Similarity: {confidence:.2f}), Sir. Guardian Mode deactivated."
        else:
            self.audit_logger.log_event(
                event_type="auth_failure",
                target="voice",
                action="rejected",
                attempt=0,
                details=f"Voice similarity too low (Score: {confidence:.2f})."
            )
            return False, f"Access Denied, Sir. Voice matching failed (Score: {confidence:.2f})."

    # ---------------------------------------------------------------------------
    #  Activity Monitor Background Loop
    # ---------------------------------------------------------------------------
    async def _monitoring_loop(self):
        """Asynchronous background loop to watch processes, browser windows, folders, and USB drives."""
        # Enable DPI-awareness for ctypes window calls
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
                
        GetWindowText = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
        GetForegroundWindow = ctypes.windll.user32.GetForegroundWindow
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId
        
        while self.is_active:
            try:
                # If warning overlay is currently active, pause monitor checks to allow input/response
                if self.overlay_active:
                    await asyncio.sleep(1.0)
                    continue
                    
                # 1. Fetch active window details
                hwnd = GetForegroundWindow()
                active_title = ""
                pid = ctypes.c_ulong()
                
                if hwnd:
                    length = GetWindowTextLength(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        GetWindowText(hwnd, buff, length + 1)
                        active_title = buff.value
                        
                    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    
                active_proc_name = ""
                if pid.value:
                    try:
                        active_proc_name = psutil.Process(pid.value).name()
                    except Exception:
                        pass
                        
                # 2. Check logical partitions change (USB storage insertion)
                current_drives = self._get_logical_drives()
                new_drives = set(current_drives) - set(self.baseline_partitions)
                if new_drives:
                    self.baseline_partitions = current_drives
                    target_usb = ", ".join(new_drives)
                    self._handle_violation(
                        viol_type="risky_action",
                        target=f"USB Storage Connected ({target_usb})",
                        details=f"New drive {target_usb} mounted.",
                        hwnd=0,
                        proc_name=None
                    )
                    continue

                # 3. Check Blocked App Violation (Process matches config)
                blocked_apps = [a.lower() for a in self.config.get("blocked_apps", [])]
                if active_proc_name and active_proc_name.lower() in blocked_apps:
                    self._handle_violation(
                        viol_type="app",
                        target=active_proc_name,
                        details=f"Blocked app '{active_proc_name}' active in foreground.",
                        hwnd=hwnd,
                        proc_name=active_proc_name
                    )
                    await asyncio.sleep(1.0)
                    continue
                    
                # 4. Check Blocked Website Violation (Active browser tab title)
                is_browser = active_proc_name and active_proc_name.lower() in ("chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe")
                if is_browser and active_title:
                    blocked_domains = [d.lower() for d in self.config.get("blocked_domains", [])]
                    for domain in blocked_domains:
                        if domain in active_title.lower():
                            self._handle_violation(
                                viol_type="website",
                                target=domain,
                                details=f"Blocked domain '{domain}' detected in browser title: '{active_title}'.",
                                hwnd=hwnd,
                                proc_name=None
                            )
                            break
                    if self.overlay_active:
                        await asyncio.sleep(1.0)
                        continue
                        
                # 5. Check Protected Folder Violation (Active File Explorer folder title)
                is_explorer = active_proc_name and active_proc_name.lower() == "explorer.exe"
                if is_explorer and active_title:
                    protected_folders = [f.lower() for f in self.config.get("protected_folders", [])]
                    for folder in protected_folders:
                        # Exclude general titles like "This PC", "Network", or "File Explorer"
                        if folder in active_title.lower() and active_title.lower() not in ("this pc", "network", "file explorer", "quick access"):
                            self._handle_violation(
                                viol_type="folder",
                                target=folder,
                                details=f"Protected folder keyword '{folder}' detected in Explorer title: '{active_title}'.",
                                hwnd=hwnd,
                                proc_name=None
                            )
                            break
                    if self.overlay_active:
                        await asyncio.sleep(1.0)
                        continue
                        
                # 6. Check Risky System Action Violation
                risky_indicators = ["registry editor", "local security policy", "control panel", "cmd.exe", "powershell.exe"]
                for indicator in risky_indicators:
                    if indicator in active_title.lower() or (active_proc_name and indicator in active_proc_name.lower()):
                        # Only trigger if it is an admin or command window (not normal apps)
                        is_terminal = "cmd" in active_title.lower() or "powershell" in active_title.lower()
                        is_admin = "administrator:" in active_title.lower()
                        
                        if is_terminal and not is_admin:
                            continue  # Allow normal terminals, block admin terminals
                            
                        self._handle_violation(
                            viol_type="risky_action",
                            target=indicator,
                            details=f"Risky system tool '{indicator}' active: '{active_title}'.",
                            hwnd=hwnd,
                            proc_name=active_proc_name if active_proc_name in ("cmd.exe", "powershell.exe") else None
                        )
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Guardian Monitor loop: {e}")
                
            await asyncio.sleep(1.0)
            
    def _handle_violation(self, viol_type: str, target: str, details: str, hwnd: int, proc_name: Optional[str] = None):
        """Processes a detected violation according to the policy engine thresholds."""
        # Increment attempt counter
        count_key = f"{viol_type}:{target.lower()}"
        self.attempt_counters[count_key] = self.attempt_counters.get(count_key, 0) + 1
        attempt = self.attempt_counters[count_key]
        
        # Decide Action
        action = self.policy_engine.decide_action(attempt)
        
        # Log to Audit file
        self.audit_logger.log_event(
            event_type=f"violation_{viol_type}",
            target=target,
            action=action,
            attempt=attempt,
            details=details
        )
        
        # Execute Action
        if action == "warn":
            self.overlay_active = True
            msg = f"Guardian Mode is active. Access to {target} is private and requires owner verification."
            self.action_engine.show_warning(msg, target)
        elif action == "close":
            # Send warning and close window/process
            self.overlay_active = True
            msg = f"Access denied. Access to {target} is restricted under Guest Mode. Please enter PIN or verify voice to unlock."
            self.action_engine.show_warning(msg, target)
            self.action_engine.close_access(hwnd, proc_name)
        elif action == "lock":
            # Critical escalation - lock workstation
            self.action_engine.dismiss_overlay()
            self.overlay_active = False
            self.action_engine.lock_session(target)
            self.attempt_counters[count_key] = 0 # Reset counter after locking
            
# ---------------------------------------------------------------------------
#  Global Singleton
# ---------------------------------------------------------------------------
guardian_mode_manager = GuardianModeManager()
