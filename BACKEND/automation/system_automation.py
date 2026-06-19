"""
AERIS -- System Automation Engine
Open/close apps, play YouTube, system controls, Google/YouTube search,
screenshots, content writing -- ported from Raven's Automation.py.
"""
from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys

# Add backend directory to sys.path to resolve module imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import logging

logger = logging.getLogger("aeris.automation")


@dataclass(frozen=True)
class AutomationResult:
    """Standardized response for all system automation executions (adopted from claw-code concepts)."""
    success: bool
    action: str
    response: str = ""
    error: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"success": self.success, "action": self.action}
        if self.response:
            d["response"] = self.response
        if self.error:
            d["error"] = self.error
        d.update(self.details)
        return d


# ── Global pending shell commands storage ────────────────────────────
# Used to track shell commands awaiting user permission
_PENDING_SHELL_COMMANDS: dict[str, dict[str, Any]] = {}

# ── Last screenshot path storage ──────────────────────────────────────
# Store the actual path of the most recent screenshot for user queries
_LAST_SCREENSHOT_PATH: Optional[str] = None
_LAST_SCREENSHOT_OPEN: bool = False  # Whether user asked for it (so we know if they want the path)

def get_pending_shell_command(key: str) -> Optional[dict[str, Any]]:
    """Retrieve a pending shell command by key."""
    return _PENDING_SHELL_COMMANDS.get(key)

def store_pending_shell_command(command: str, command_type: str, description: str = "") -> str:
    """Store a pending shell command and return a unique key."""
    import hashlib
    key = hashlib.md5(f"{command}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
    _PENDING_SHELL_COMMANDS[key] = {
        "command": command,
        "type": command_type,  # "bash" or "smart_shell"
        "description": description,
        "timestamp": datetime.now().isoformat()
    }
    return key

def execute_pending_shell_command(key: str) -> dict:
    """Execute a pending shell command after user confirms."""
    pending = _PENDING_SHELL_COMMANDS.pop(key, None)
    if not pending:
        return AutomationResult(
            success=False,
            action="bash",
            error="Pending command not found or already executed"
        ).to_dict()
    
    command = pending["command"]
    cmd_type = pending["type"]
    
    try:
        from file_tools import FileToolSystem
        from shell_gpt_bridge import smart_shell
        
        ft = FileToolSystem()
        
        if cmd_type == "bash":
            # Execute bash command directly  
            r = ft.bash(command)
            if r.success:
                return AutomationResult(
                    success=True,
                    action="bash",
                    response=f"✅ **Command Executed (Approved):**\n```bash\n{command}\n```\n\n**Output:**\n```text\n{r.output}\n```"
                ).to_dict()
            return AutomationResult(success=False, action="bash", error=r.output).to_dict()
        
        elif cmd_type == "smart_shell":
            # Execute smart shell command
            result = smart_shell.execute_command(command)
            if result.exit_code == 0 or result.executed:
                return AutomationResult(
                    success=True,
                    action="smart_shell",
                    response=f"✅ **Smart Shell Command Executed (Approved):**\n**Command:** `{command}`\n**Description:** {pending.get('description', 'N/A')}\n\n**Output:**\n```text\n{result.output[:3000]}\n```"
                ).to_dict()
            else:
                return AutomationResult(
                    success=False,
                    action="smart_shell",
                    response=f"Command `{command}` failed: {result.error}",
                    error=result.error
                ).to_dict()
    except Exception as e:
        return AutomationResult(success=False, action=cmd_type, error=str(e)).to_dict()


# ── App Management ───────────────────────────────────────────────────

def _get_latest_project_path() -> Optional[str]:
    """Helper to resolve the latest generated project folder path."""
    try:
        from config import settings
        from pathlib import Path
        import json
        
        base_dir = Path(settings.WORKSPACE_DIR).resolve()
        status_file = base_dir.parent / "data" / "project_build_status.json"
        
        if status_file.exists():
            try:
                data = json.loads(status_file.read_text(encoding="utf-8"))
                project_path = data.get("project_path")
                if project_path:
                    path_obj = Path(project_path)
                    # If it's the default 'pending_project' placeholder or doesn't exist, scan the workspace directory
                    if "pending_project" in str(project_path) or not path_obj.exists():
                        if base_dir.exists():
                            subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
                            if subdirs:
                                # Sort by modification time to find the latest modified directory
                                latest_dir = max(subdirs, key=lambda d: d.stat().st_mtime)
                                return str(latest_dir)
                    else:
                        return str(project_path)
            except Exception as read_err:
                import logging
                logging.getLogger("aeris.automation").warning(f"Failed to read project_build_status.json: {read_err}")
        
        # Fallback to scanning the workspace directory directly
        if base_dir.exists():
            subdirs = [d for d in base_dir.iterdir() if d.is_dir()]
            if subdirs:
                latest_dir = max(subdirs, key=lambda d: d.stat().st_mtime)
                return str(latest_dir)
    except Exception as e:
        import logging
        logging.getLogger("aeris.automation").warning(f"Error in _get_latest_project_path: {e}")
    return None


def open_folder(path: str) -> dict:
    """Open a folder in the file explorer. Supports vague/Hinglish references via FolderIntelligence."""
    import os, platform, subprocess
    try:
        path_lower = path.lower().strip()
        # Intercept project folder opening request
        if path_lower in ("project", "latest_project", "current_project", "latest project", "current project", "pending_project") or "pending_project" in path:
            latest_path = _get_latest_project_path()
            if latest_path and os.path.exists(latest_path):
                path = latest_path
            else:
                from config import settings
                path = str(settings.WORKSPACE_DIR)

        # Resolve the path to handle environment variables and user home directory
        path = os.path.expandvars(os.path.expanduser(path))
        if not os.path.exists(path):
            # ── Smart resolution via FolderIntelligence ──
            try:
                from intelligence.folder_intelligence import get_folder_intelligence
                fi = get_folder_intelligence()
                match = fi.resolve(path_lower)
                if match and match.confidence >= 0.5 and os.path.exists(match.path):
                    logger.info(f"[open_folder] FolderIntelligence resolved '{path}' -> {match.path} "
                               f"(confidence={match.confidence:.2f})")
                    path = match.path
                    fi.set_context(path)
                elif "project" in path_lower:
                    from config import settings
                    path = str(settings.WORKSPACE_DIR)
                else:
                    return {"success": False, "action": "open_folder", "error": f"Path not found: {path}"}
            except Exception as fi_err:
                logger.warning(f"[open_folder] FolderIntelligence failed: {fi_err}")
                if "project" in path_lower:
                    from config import settings
                    path = str(settings.WORKSPACE_DIR)
                else:
                    return {"success": False, "action": "open_folder", "error": f"Path not found: {path}"}
        else:
            # Path exists — track context for future pronoun resolution
            try:
                from intelligence.folder_intelligence import get_folder_intelligence
                get_folder_intelligence().set_context(path)
            except Exception:
                pass
            
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"success": True, "action": "open_folder", "target": path}
    except Exception as e:
        return {"success": False, "action": "open_folder", "error": str(e)}


def open_app(app_name: str) -> dict:
    """Open an application using multiple fallback strategies."""
    app_key = app_name.lower().strip()
    
    # Intercept tracked file queries
    from utils.file_tracker import resolve_tracked_file
    resolved_path = resolve_tracked_file(app_name)
    if resolved_path:
        logger.info(f"[open_app] Intercepted file query '{app_name}' resolving to '{resolved_path}'. Redirecting to open_file.")
        return open_file(resolved_path)

    # ── Failsafe Interception for Files ──
    from config import settings
    from pathlib import Path
    workspace_root = Path(settings.WORKSPACE_DIR)
    
    # Try resolving relative path directly
    try:
        direct_path = (workspace_root / app_name).resolve()
        # Ensure it doesn't escape workspace
        direct_path.relative_to(workspace_root.resolve())
        if direct_path.exists() and direct_path.is_file():
            logger.info(f"[open_app] App name '{app_name}' is an existing file in workspace. Redirecting to open_file.")
            return open_file(str(direct_path))
    except Exception:
        pass

    # Check if a file with common extensions exists in workspace
    for ext in (".xlsx", ".xls", ".docx", ".doc", ".pdf", ".txt", ".csv"):
        try:
            test_path = (workspace_root / f"{app_name}{ext}").resolve()
            test_path.relative_to(workspace_root.resolve())
            if test_path.exists() and test_path.is_file():
                logger.info(f"[open_app] Found file '{test_path.name}' in workspace. Redirecting to open_file.")
                return open_file(str(test_path))
        except Exception:
            pass

    # If it definitely looks like a file extension, run a quick system search
    has_ext = any(app_key.endswith(ext) for ext in (".xlsx", ".xls", ".docx", ".doc", ".pdf", ".txt", ".csv", ".png", ".jpg"))
    if has_ext:
        try:
            from services.file_tools import FileToolSystem
            ft = FileToolSystem()
            search_res = ft.find_system_file(app_name)
            if search_res.success and search_res.output and "No matching files found" not in search_res.output:
                first_match = search_res.output.splitlines()[0]
                logger.info(f"[open_app] Found file via system search: '{first_match}'. Redirecting to open_file.")
                return open_file(first_match)
        except Exception as e:
            logger.warning(f"[open_app] Failed to run find_system_file for '{app_name}': {e}")
        
    # Intercept project open request
    if app_key in ("project", "latest project", "current project", "antigravity project", "the project", "project folder", "project directory", "latest project folder", "current project folder"):
        latest_path = _get_latest_project_path()
        if latest_path and os.path.exists(latest_path):
            return open_folder(latest_path)
        else:
            from config import settings
            return open_folder(str(settings.WORKSPACE_DIR))
            
    # ── Strategy 1: AppOpener ──────────────────────────────────────
    try:
        from AppOpener import open as appopen
        appopen(app_name, match_closest=True, output=True, throw_error=True)
        return {"success": True, "action": "open", "target": app_name}
    except Exception:

        pass  # Try next strategy

    # ── Strategy 2: Win32 known executable ────────────────────────
    import platform, subprocess
    if platform.system() == "Windows":
        known_exes = {
            "chrome": "chrome", "edge": "msedge", "notepad": "notepad",
            "cmd": "cmd", "powershell": "powershell", "vscode": "code"
        }
        exe = known_exes.get(app_key)
        if exe:
            try:
                subprocess.Popen(["cmd", "/c", "start", "", exe], shell=False, creationflags=subprocess.DETACHED_PROCESS)
                return {"success": True, "action": "open_win32", "target": app_name}
            except Exception:
                pass

    # ── Strategy 3: Windows Search (Keyboard Automation) ───────────
    if platform.system() == "Windows":
        try:
            import pyautogui, time
            pyautogui.FAILSAFE = False
            pyautogui.hotkey("win")          # Open Start Menu
            time.sleep(0.7)
            pyautogui.write(app_name, interval=0.05)
            time.sleep(0.8)
            pyautogui.press("enter")
            time.sleep(1.5)
            return {"success": True, "action": "open_search", "target": app_name, "response": f"Opened {app_name} via Windows Search."}
        except Exception as e:
            return {"success": False, "action": "open", "error": f"Failed to open {app_name}: {e}"}

    # Fallback to web search if not Windows or all else fails
    try:
        import webbrowser
        webbrowser.open(f"https://www.google.com/search?q={app_name}")
        return {"success": True, "action": "open_web", "target": app_name}
    except Exception as e:
        return {"success": False, "action": "open", "error": str(e)}

def close_app(app_name: str) -> dict:
    """Close an application."""
    try:
        from AppOpener import close
        close(app_name, match_closest=True, output=True, throw_error=True)
        return {"success": True, "action": "close", "target": app_name}
    except Exception as e:
        # Try taskkill on Windows
        if platform.system() == "Windows":
            try:
                os.system(f'taskkill /IM "{app_name}.exe" /F 2>nul')
                return {"success": True, "action": "close_force", "target": app_name}
            except Exception:
                pass
        return {"success": False, "action": "close", "error": str(e)}


def close_all_apps(exceptions: str | list[str] | None = None) -> dict:
    """Close all running user-facing applications (except core system & dev tools).
    
    Args:
        exceptions: App names to keep open. Can be a comma-separated string
                    or a list of strings. Core apps (Explorer, VS Code, Terminal,
                    Python, Node) are always excluded.
    """
    if platform.system() == "Windows":
        try:
            # Build exclusion regex from defaults + user exceptions
            always_exclude = ["explorer", "Code", "WindowsTerminal", "python", "node", "pwsh", "cmd"]
            
            if exceptions:
                if isinstance(exceptions, str):
                    extras = [e.strip() for e in exceptions.split(",") if e.strip()]
                else:
                    extras = [str(e).strip() for e in exceptions if str(e).strip()]
                always_exclude.extend(extras)
            
            exclude_pattern = "|".join(always_exclude)
            
            ps_script = (
                f"Get-Process | Where-Object {{ $_.MainWindowHandle -ne 0 "
                f"-and $_.ProcessName -notmatch '(?i)({exclude_pattern})' }} "
                f"| ForEach-Object {{ $_.CloseMainWindow() | Out-Null }}"
            )
            os.system(f'powershell -command "{ps_script}"')
            return {"success": True, "action": "close_all_apps", "response": "🔄 Closed all non-essential running apps."}
        except Exception as e:
            return {"success": False, "action": "close_all_apps", "error": str(e)}
    else:
        return {"success": False, "action": "close_all_apps", "error": "Only supported on Windows"}


# ── Media ────────────────────────────────────────────────────────────

_VISIBLE_YOUTUBE_KEYWORDS = [
    "on youtube",
    "youtube pe",
    "youtube par",
    "youtube pr",
    "youtube me",
    "youtube mein",
    "youtube open",
    "youtube kholo",
    "youtube khol kar",
    "youtube open karke",
]


def _should_open_youtube_visible(query: str) -> bool:
    query_lower = query.lower().strip()
    return any(keyword in query_lower for keyword in _VISIBLE_YOUTUBE_KEYWORDS)


def _strip_visible_youtube_keywords(query: str) -> str:
    cleaned = query
    for keyword in _VISIBLE_YOUTUBE_KEYWORDS:
        cleaned = cleaned.replace(keyword, "")
        cleaned = cleaned.replace(keyword.title(), "")
    return " ".join(cleaned.split()).strip()


def play_music_background(query: str) -> dict:
    """Play music/song in background via Chrome extension (no visible browser window).
    Sends the song name to the backend WebSocket bridge which routes it to the extension.
    This is the DEFAULT handler for 'play X' commands."""
    try:
        import requests
        resp = requests.post(
            "http://127.0.0.1:8000/api/music/play",
            json={"song": query},
            timeout=5,
        )
        data = resp.json()
        if data.get("success"):
            return {"success": True, "action": "play_background", "query": query,
                    "response": f"🎵 Playing **{query}** in background via extension."}
        return {
            "success": False,
            "action": "play_background_unavailable",
            "query": query,
            "error": data.get("error", "Background music extension not connected"),
            "response": "Sir, my background music extension is not connected right now. Please ensure the AERIS Chrome extension is active, or say 'play on youtube' for visible playback."
        }
    except Exception as e:
        return {
            "success": False,
            "action": "play_background_unavailable",
            "query": query,
            "error": str(e),
            "response": "Sir, I couldn't reach the background player. Please ensure the extension is active, or explicitly specify 'play on youtube'."
        }


def play_on_youtube_visible(query: str) -> dict:
    """Open YouTube visibly in the browser and play a song/video.
    Used when the user explicitly says 'play X on YouTube'."""
    try:
        from pywhatkit import playonyt
        playonyt(query)
        return {"success": True, "action": "play_visible", "query": query,
                "response": f"▶️ Playing **{query}** on YouTube (visible)."}
    except ImportError:
        webbrowser.open(f"https://www.youtube.com/results?search_query={query}")
        return {"success": True, "action": "play_search", "query": query,
                "response": f"▶️ Searching **{query}** on YouTube."}
    except Exception as e:
        return {"success": False, "action": "play", "error": str(e)}


# Keep backward-compatible alias — play routes to visible YouTube browser playback
def play_youtube(query: str) -> dict:
    """Default play handler — plays on YouTube (visible)."""
    return play_on_youtube_visible(query)


# ── Web Search ───────────────────────────────────────────────────────

def google_search(query: str) -> dict:
    """Open a Google search in the default browser."""
    try:
        import urllib.parse
        encoded = urllib.parse.quote_plus(query)
        webbrowser.open(f"https://www.google.com/search?q={encoded}")
        return {"success": True, "action": "google_search", "query": query,
                "response": f"🔍 Searching Google for **\"{query}\"** — opening in your browser now."}
    except Exception as e:
        return {"success": False, "action": "google_search", "error": str(e)}


# App-specific search URL templates
_APP_SEARCH_URLS = {
    "youtube":  "https://www.youtube.com/results?search_query={q}",
    "amazon":   "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "google":   "https://www.google.com/search?q={q}",
    "twitter":  "https://twitter.com/search?q={q}",
    "x":        "https://x.com/search?q={q}",
    "reddit":   "https://www.reddit.com/search/?q={q}",
    "github":   "https://github.com/search?q={q}",
    "linkedin": "https://www.linkedin.com/search/results/all/?keywords={q}",
    "spotify":  "https://open.spotify.com/search/{q}",
    "netflix":  "https://www.netflix.com/search?q={q}",
    "instagram":"https://www.instagram.com/explore/tags/{q}/",
    "bing":     "https://www.bing.com/search?q={q}",
    "duckduckgo": "https://duckduckgo.com/?q={q}",
    "quora":    "https://www.quora.com/search?q={q}",
    "stack overflow": "https://stackoverflow.com/search?q={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={q}",
}


def app_search(app_name: str, query: str) -> dict:
    """Open an app/website and search for a keyword within it."""
    import urllib.parse
    app_key = app_name.lower().strip()
    encoded_q = urllib.parse.quote_plus(query)

    url_template = _APP_SEARCH_URLS.get(app_key)
    if url_template:
        url = url_template.format(q=encoded_q)
    else:
        # Generic: open the app first via AppOpener, then do a Google search about app+query
        try:
            open_app(app_name)
        except Exception:
            pass
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(app_name + ' ' + query)}"

    try:
        webbrowser.open(url)
        return {
            "success": True,
            "action": "app_search",
            "app": app_name,
            "query": query,
            "url": url,
            "response": f"🔍 Opening **{app_name.title()}** and searching for **\"{query}\"**.",
        }
    except Exception as e:
        return {"success": False, "action": "app_search", "error": str(e)}


def youtube_search(query: str) -> dict:
    """Search YouTube."""
    return app_search("youtube", query)



# ── System Controls ──────────────────────────────────────────────────

def system_control(action: str) -> dict:
    """Execute system-level controls (volume, shutdown, etc)."""
    action = action.lower().strip()

    if platform.system() != "Windows":
        return {"success": False, "action": action, "error": "System controls only on Windows"}

    try:
        import keyboard  # type: ignore

        controls = {
            "mute": lambda: keyboard.press_and_release("volume mute"),
            "unmute": lambda: keyboard.press_and_release("volume mute"),
            "volume up": lambda: keyboard.press_and_release("volume up"),
            "volume down": lambda: keyboard.press_and_release("volume down"),
            "shutdown": lambda: os.system("shutdown /s /t 5"),
            "restart": lambda: os.system("shutdown /r /t 5"),
            "lock": lambda: os.system("rundll32.exe user32.dll,LockWorkStation"),
            "lock window": lambda: os.system("rundll32.exe user32.dll,LockWorkStation"),
            "close_all_tabs": lambda: keyboard.press_and_release("ctrl+shift+w"),
            "close all tabs": lambda: keyboard.press_and_release("ctrl+shift+w"),
        }

        handler = controls.get(action)
        if handler:
            handler()
            return {"success": True, "action": action}
        else:
            return {"success": False, "action": action, "error": f"Unknown system action: {action}"}

    except ImportError:
        # keyboard module not available
        if action == "shutdown":
            os.system("shutdown /s /t 5")
            return {"success": True, "action": action}
        elif action == "restart":
            os.system("shutdown /r /t 5")
            return {"success": True, "action": action}
        elif action in ("lock", "lock window"):
            os.system("rundll32.exe user32.dll,LockWorkStation")
            return {"success": True, "action": action}
        return {"success": False, "action": action, "error": "keyboard module not installed"}


# ── App & Media Controls (Keyboard Emulation) ────────────────────────

def youtube_control(action: str) -> dict:
    """Control YouTube playback in browser using keyboard shortcuts."""
    action = action.lower().strip()
    try:
        import keyboard  # type: ignore
        
        # We can try to focus browser window on Windows, but standard keyboard shortcuts 
        # usually work if browser is the active window (or global media keys)
        if any(word in action for word in ("play", "pause", "stop", "resume")):
            keyboard.press_and_release("space")
            keyboard.press_and_release("play/pause media")
        elif "mute" in action or "unmute" in action:
            keyboard.press_and_release("m")
        elif "exit" in action or "close" in action or "quit" in action:
            if "fullscreen" in action:
                keyboard.press_and_release("esc")
        elif "full" in action or "screen" in action:
            keyboard.press_and_release("f")
        elif "volume up" in action or "louder" in action or "increase volume" in action:
            keyboard.press_and_release("up")
        elif "volume down" in action or "quieter" in action or "decrease volume" in action:
            keyboard.press_and_release("down")
        elif "next" in action or "change" in action or "another" in action:
            keyboard.press_and_release("shift+n")
        elif "previous" in action or "back" in action and "skip" not in action:
            keyboard.press_and_release("shift+p")
        elif "forward" in action or "skip" in action:
            keyboard.press_and_release("l") # l skips 10 sec
        elif "rewind" in action or "backward" in action:
            keyboard.press_and_release("j") # j rewinds 10 sec
        elif "caption" in action or "subtitle" in action:
            keyboard.press_and_release("c")
        else:
            return {"success": False, "action": "youtube_control", "error": f"Unknown action: {action}"}
        
        return {"success": True, "action": "youtube_control", "command": action, "response": f"▶️ YouTube: {action.title()} applied."}
    except ImportError:
        return {"success": False, "action": "youtube_control", "error": "keyboard module not installed"}
    except Exception as e:
        return {"success": False, "action": "youtube_control", "error": str(e)}


def slide_control(action: str) -> dict:
    """Control slides/presentations."""
    action = action.lower().strip()
    try:
        import keyboard  # type: ignore
        if action in ("next", "next slide"):
            keyboard.press_and_release("right")
        elif action in ("previous", "previous slide"):
            keyboard.press_and_release("left")
        elif action in ("fullscreen", "slideshow"):
            keyboard.press_and_release("f5")
        elif action in ("exit fullscreen", "exit slideshow"):
            keyboard.press_and_release("esc")
        else:
            return {"success": False, "action": "slide_control", "error": f"Unknown action: {action}"}
        return {"success": True, "action": "slide_control", "command": action}
    except Exception as e:
        return {"success": False, "action": "slide_control", "error": str(e)}


def media_control(action: str) -> dict:
    """Global system media control."""
    action = action.lower().strip()
    try:
        import keyboard  # type: ignore
        if any(word in action for word in ("play", "pause", "stop", "resume")):
            keyboard.press_and_release("play/pause media")
        elif "next" in action or "change" in action or "skip" in action:
            keyboard.press_and_release("next track")
        elif "previous" in action or "back" in action:
            keyboard.press_and_release("previous track")
        elif "volume up" in action or "louder" in action:
            keyboard.press_and_release("volume up")
        elif "volume down" in action or "quieter" in action:
            keyboard.press_and_release("volume down")
        elif "mute" in action or "unmute" in action:
            keyboard.press_and_release("volume mute")
        elif "full" in action or "screen" in action:
            keyboard.press_and_release("f")
        elif "exit" in action or "close" in action:
            keyboard.press_and_release("esc")
        else:
            return {"success": False, "action": "media_control", "error": f"Unknown action: {action}"}
        return {"success": True, "action": "media_control", "command": action, "response": f"🎵 Media: {action.title()} applied."}
    except Exception as e:
        return {"success": False, "action": "media_control", "error": str(e)}


def browser_control(action: str) -> dict:
    """Control web browser tabs using standard keyboard shortcuts."""
    action = action.lower().strip()
    try:
        import keyboard  # type: ignore
        
        if "new" in action or "open" in action:
            keyboard.press_and_release("ctrl+t")
        elif "close" in action or "kill" in action:
            keyboard.press_and_release("ctrl+w")
        elif "reopen" in action or "restore" in action:
            keyboard.press_and_release("ctrl+shift+t")
        elif "next" in action or "switch" in action or "right" in action:
            keyboard.press_and_release("ctrl+tab")
        elif "previous" in action or "left" in action or "back" in action:
            keyboard.press_and_release("ctrl+shift+tab")
        elif "refresh" in action or "reload" in action:
            keyboard.press_and_release("ctrl+r")
        else:
            return {"success": False, "action": "browser_control", "error": f"Unknown action: {action}"}
        
        return {"success": True, "action": "browser_control", "command": action, "response": f"🌐 Browser: {action.title()} applied."}
    except Exception as e:
        return {"success": False, "action": "browser_control", "error": str(e)}



# ── Screenshot ───────────────────────────────────────────────────────

def take_screenshot(filename: str | None = None, open_file: bool = True) -> dict:
    """Take a screenshot and save it. Optionally open it afterwards.
    
    Args:
        filename: Optional custom filename (defaults to timestamp-based name)
        open_file: Whether to automatically open the screenshot (default: True)
                   Set to False when taking screenshots for analysis
    """
    global _LAST_SCREENSHOT_PATH, _LAST_SCREENSHOT_OPEN
    
    try:
        screenshots_dir = os.path.join(os.getcwd(), "Screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        elif not filename.endswith(('.png', '.jpg')):
            filename += ".png"

        filepath = os.path.join(screenshots_dir, filename)

        if platform.system() == "Windows":
            from PIL import ImageGrab  # type: ignore
            screenshot = ImageGrab.grab()
            screenshot.save(filepath)
        elif platform.system() == "Darwin":
            subprocess.run(["screencapture", filepath], check=True)
        else:
            subprocess.run(["gnome-screenshot", "-f", filepath], check=True)

        # Store the actual path for user queries (with proper OS-aware path)
        _LAST_SCREENSHOT_PATH = filepath
        _LAST_SCREENSHOT_OPEN = open_file

        # Only open file if requested (default True for normal screenshots)
        if open_file:
            try:
                import webbrowser
                from pathlib import Path
                webbrowser.open(Path(filepath).absolute().as_uri())
            except Exception:
                pass

        return {"success": True, "action": "screenshot", "path": filepath, "response": "Sir, screenshot liya gaya hai. (Screenshot taken successfully.)", "open_file": open_file}
    except Exception as e:
        return {"success": False, "action": "screenshot", "error": str(e)}


# ── Content Writing ──────────────────────────────────────────────────

def write_content(topic: str) -> dict:
    """Generate written content using AI and save to file."""
    try:
        from chat_engine import chat
        content = chat(f"Write detailed, professional content about: {topic}")

        data_dir = os.path.join(os.getcwd(), "data")
        os.makedirs(data_dir, exist_ok=True)

        safe_name = topic.lower().replace(" ", "_")[:50]
        filepath = os.path.join(data_dir, f"{safe_name}.txt")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        # Try to open the file
        try:
            if platform.system() == "Windows":
                os.startfile(filepath)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", filepath])
            else:
                subprocess.Popen(["xdg-open", filepath])
        except Exception:
            pass

        return {"success": True, "action": "content", "topic": topic, "path": filepath, "preview": content[:200], "response": f"Content written. (Note to Assistant: DO NOT announce the file path unless explicitly asked. The path is {filepath})"}
    except Exception as e:
        return {"success": False, "action": "content", "error": str(e)}


# ── Open File ────────────────────────────────────────────────────────

def open_file(path: str, app: str = "") -> dict:
    """Open a file using its default application, or a specific app.

    Args:
        path: Absolute or relative path to the file. Supports ~, %USERPROFILE%, env vars.
        app:  Optional app name to open the file with (e.g. 'notepad', 'code', 'excel').
              Leave empty to use the OS default for that file type.
    """
    try:
        path = os.path.expandvars(os.path.expanduser(path.strip()))

        if not os.path.exists(path):
            # Try to resolve path using file tracker resolver
            from utils.file_tracker import resolve_tracked_file
            resolved = resolve_tracked_file(path)
            if resolved and os.path.exists(resolved):
                logger.info(f"[open_file] Resolved query '{path}' to tracked file '{resolved}'.")
                path = resolved
            else:
                # Try relative to workspace directory
                from config import settings
                workspace_path = os.path.join(str(settings.WORKSPACE_DIR), path)
                if os.path.exists(workspace_path):
                    path = workspace_path
                else:
                    return {"success": False, "action": "open_file",
                            "error": f"File not found: {path}"}

        app_key = app.lower().strip() if app else ""

        if platform.system() == "Windows":
            _APP_EXES = {
                "notepad":   "notepad.exe",
                "notepad++": "notepad++.exe",
                "code":      "code",
                "vscode":    "code",
                "wordpad":   "wordpad.exe",
                "excel":     "excel.exe",
                "word":      "winword.exe",
                "paint":     "mspaint.exe",
                "vlc":       "vlc.exe",
            }
            exe = _APP_EXES.get(app_key, app_key) if app_key else None

            if exe:
                try:
                    subprocess.Popen(
                        [exe, path],
                        creationflags=subprocess.DETACHED_PROCESS
                    )
                    return {
                        "success": True, "action": "open_file",
                        "path": path, "app": exe,
                        "response": f"✅ Opened **{os.path.basename(path)}** in **{exe}**."
                    }
                except Exception:
                    pass  # fall through to os.startfile

            os.startfile(path)

        elif platform.system() == "Darwin":
            cmd = ["open", "-a", app, path] if app_key else ["open", path]
            subprocess.Popen(cmd)
        else:
            subprocess.Popen(["xdg-open", path])

        return {
            "success": True, "action": "open_file", "path": path,
            "response": f"✅ Opened **{os.path.basename(path)}**."
        }
    except Exception as e:
        return {"success": False, "action": "open_file", "error": str(e)}


# ── NLP & Text Analysis Tools ────────────────────────────────────────

def nlp_summarize(text: str) -> dict:
    """Advanced NLP tool to summarize text concisely."""
    try:
        from chat_engine import chat
        prompt = f"Analyze and provide a highly concise, structured summary of the following text. Extract the main ideas, key bullet points, and the core conclusion. Do not write an intro, just give the summary.\n\nText:\n{text}"
        response = chat(prompt)
        return {"success": True, "action": "nlp_summarize", "response": f"📝 **Advanced NLP Summary:**\n\n{response}"}
    except Exception as e:
        return {"success": False, "action": "nlp_summarize", "error": str(e)}


def nlp_translate(language: str, text: str) -> dict:
    """Advanced NLP tool for high-accuracy translation."""
    try:
        from chat_engine import chat
        prompt = f"You are a professional linguist. Translate the following text into strictly fluent and culturally accurate {language}. ONLY output the translation, no extra text.\n\nText:\n{text}"
        response = chat(prompt)
        return {"success": True, "action": "nlp_translate", "language": language, "response": f"🌍 **Translation ({language}):**\n\n{response}"}
    except Exception as e:
        return {"success": False, "action": "nlp_translate", "error": str(e)}


def nlp_sentiment(text: str) -> dict:
    """Advanced NLP tool for sentiment and emotion analysis."""
    try:
        from chat_engine import chat
        prompt = (f"You are an expert psychologist and sentiment analyst. Analyze the following text and provide a structured "
                  f"sentiment profile. Include:\n- **Overall Sentiment** (Positive/Negative/Neutral/Mixed)\n"
                  f"- **Primary Emotion** (e.g., Joy, Anger, Sadness, Fear, Surprise)\n"
                  f"- **Confidence Score** (0-100%)\n- **Brief Explanation**.\n\nText:\n{text}")
        response = chat(prompt)
        return {"success": True, "action": "nlp_sentiment", "response": f"🧠 **Sentiment Analysis Profile:**\n\n{response}"}
    except Exception as e:
        return {"success": False, "action": "nlp_sentiment", "error": str(e)}


def nlp_rewrite(text: str) -> dict:
    """Advanced NLP tool for grammar fixing and text enhancement."""
    try:
        from chat_engine import chat
        prompt = f"You are an expert editor. Fix all grammar, spelling, and phrasing issues in the following text. Make it sound professional, natural, and eloquent. ONLY output the rewritten text, no extra conversational filler.\n\nText:\n{text}"
        response = chat(prompt)
        return {"success": True, "action": "nlp_rewrite", "response": f"✨ **Rewritten Text:**\n\n{response}"}
    except Exception as e:
        return {"success": False, "action": "nlp_rewrite", "error": str(e)}


# ── Task Scheduler (Native + Hindi) ──────────────────────────────────

def schedule_task(prompt: str) -> dict:
    """Schedule a task or reminder, natively handling Hindi/English commands."""
    try:
        from chat_engine import chat
        import json, re, threading, time
        
        # Use LLM to extract task and time
        extraction_prompt = (
            f"Extract the exact task description and the time delay from the following prompt. "
            f"The prompt may be in English or Hindi, or Hinglish (like 'mujhe yaad dilana'). "
            f"Calculate the delay in seconds from right now. "
            f"Return ONLY a JSON object with keys 'task' (string) and 'delay_seconds' (integer). "
            f"If no specific time is given or implied, default to 10 seconds. "
            f"Prompt: {prompt}"
        )
        response = chat(extraction_prompt)
        
        try:
            match = re.search(r'\{.*\}', response, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = {"task": prompt, "delay_seconds": 10}
        except Exception:
            data = {"task": prompt, "delay_seconds": 10}
            
        task_desc = data.get("task", prompt)
        delay = data.get("delay_seconds", 10)

        # Background thread to wait and remind
        def reminder_thread():
            time.sleep(delay)
            if platform.system() == "Windows":
                try:
                    from win11toast import toast
                    toast("🔔 Task Reminder", task_desc)
                except ImportError:
                    # Fallback to VBScript msgbox if win11toast isn't available
                    vbs_path = os.path.join(os.environ.get("TEMP", "C:/Windows/Temp"), "AERIS_rem.vbs")
                    with open(vbs_path, "w") as f:
                        f.write(f'MsgBox "{task_desc}", 64, "AERIS Reminder"')
                    os.system(f'cscript //nologo "{vbs_path}"')
            print(f"\\n\\n>>> 🔔 REMINDER: {task_desc} <<<\\n\\n")
            
        threading.Thread(target=reminder_thread, daemon=True).start()
        
        return {"success": True, "action": "schedule", "task": task_desc, "delay_seconds": delay, "response": f"⏰ Scheduled reminder for: **{task_desc}** in {delay} seconds."}
    except Exception as e:
        return {"success": False, "action": "schedule", "error": str(e)}

def monitor_system() -> dict:
    """Monitor system health: CPU, memory, disk, battery, and top processes."""
    try:
        import psutil
        import shutil
        import platform
        import os
        
        # CPU Info
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count_logical = psutil.cpu_count(logical=True)
        cpu_count_physical = psutil.cpu_count(logical=False)
        
        # Memory Info
        mem = psutil.virtual_memory()
        mem_total = mem.total / (1024 ** 3)
        mem_used = mem.used / (1024 ** 3)
        mem_free = mem.available / (1024 ** 3)
        mem_percent = mem.percent
        
        # Disk Info
        disks = []
        if platform.system() == "Windows":
            drives = []
            for partition in psutil.disk_partitions():
                if partition.opts and 'cdrom' not in partition.opts and partition.fstype:
                    drives.append(partition.mountpoint)
            if not drives:
                drives = ["C:\\"]
        else:
            drives = ["/"]
            
        for drive in drives:
            try:
                total, used, free = shutil.disk_usage(drive)
                disks.append({
                    "drive": drive,
                    "total_gb": round(total / (1024 ** 3), 2),
                    "used_gb": round(used / (1024 ** 3), 2),
                    "free_gb": round(free / (1024 ** 3), 2),
                    "used_pct": round((used / total) * 100, 2)
                })
            except Exception:
                pass
                
        # Battery Info
        battery_info = {}
        try:
            battery = psutil.sensors_battery()
            if battery:
                battery_info = {
                    "percent": battery.percent,
                    "power_plugged": battery.power_plugged,
                    "secsleft": battery.secsleft
                }
        except Exception:
            pass
            
        # Top 5 Processes by CPU usage
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                processes.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "cpu_percent": proc.info['cpu_percent'] or 0.0,
                    "memory_percent": round(proc.info['memory_percent'] or 0.0, 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        # Sort by CPU usage and get top 5
        processes = sorted(processes, key=lambda x: x["cpu_percent"], reverse=True)[:5]
        
        details = {
            "cpu": {
                "percent": cpu_percent,
                "cores_logical": cpu_count_logical,
                "cores_physical": cpu_count_physical
            },
            "memory": {
                "percent": mem_percent,
                "total_gb": round(mem_total, 2),
                "used_gb": round(mem_used, 2),
                "free_gb": round(mem_free, 2)
            },
            "disks": disks,
            "battery": battery_info,
            "top_processes": processes
        }
        
        # Build report
        response_lines = [
            "🖥️ **AERIS System Monitoring Report:**",
            f"- **CPU Usage:** {cpu_percent}% ({cpu_count_logical} Cores)",
            f"- **RAM Usage:** {mem_percent}% ({round(mem_used, 1)}GB / {round(mem_total, 1)}GB Used)",
        ]
        
        if battery_info:
            plugged_status = "Plugged in" if battery_info["power_plugged"] else "Discharging"
            response_lines.append(f"- **Battery:** {battery_info['percent']}% ({plugged_status})")
            
        response_lines.append("\n📁 **Disk Storage:**")
        for d in disks:
            response_lines.append(f"  • **{d['drive']}** {d['used_pct']}% used ({d['free_gb']}GB free / {d['total_gb']}GB total)")
            
        response_lines.append("\n🔥 **Top CPU Processes:**")
        for p in processes:
            response_lines.append(f"  • `{p['name']}` (PID: {p['pid']}) - CPU: {p['cpu_percent']}% | RAM: {p['memory_percent']}%")
            
        return {
            "success": True,
            "action": "monitor_system",
            "details": details,
            "response": "\n".join(response_lines)
        }
    except Exception as e:
        return {"success": False, "action": "monitor_system", "error": str(e)}


def share_file_whatsapp(contact_name: str, file_path: str) -> dict:
    """Share any file via WhatsApp Web to a contact by name using clipboard and key emulation."""
    import os
    import subprocess
    import pyautogui
    import time
    import webbrowser
    
    resolved_path = os.path.expandvars(os.path.expanduser(file_path.strip()))
    if not os.path.exists(resolved_path):
        return {
            "success": False,
            "action": "share_file_whatsapp",
            "error": f"File not found: {file_path}"
        }
        
    abs_path = os.path.abspath(resolved_path)
    
    # Step 1: Copy file to clipboard as FileDropList using PowerShell
    cmd = f'powershell -NoProfile -Command "Set-Clipboard -Path \'{abs_path}\'"'
    try:
        subprocess.run(cmd, shell=True, check=True)
    except Exception as e:
        return {
            "success": False,
            "action": "share_file_whatsapp",
            "error": f"Failed to copy file to clipboard: {str(e)}"
        }
        
    try:
        webbrowser.open("https://web.whatsapp.com")
        print("[*] Opening WhatsApp Web... Waiting for page to load (8s)...")
        time.sleep(8.0)
        
        # Focus search bar
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(0.5)
        
        # Clear search and write contact name
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        time.sleep(0.2)
        pyautogui.write(contact_name, interval=0.05)
        time.sleep(2.0)
        
        # Open Chat
        pyautogui.press("enter")
        time.sleep(1.0)
        
        # Paste File
        pyautogui.hotkey("ctrl", "v")
        time.sleep(2.0)
        
        # Send File
        pyautogui.press("enter")
        time.sleep(1.0)
        
        return {
            "success": True,
            "action": "share_file_whatsapp",
            "contact": contact_name,
            "path": abs_path,
            "response": f"✅ File `{os.path.basename(abs_path)}` shared successfully with **{contact_name}** on WhatsApp."
        }
    except Exception as e:
        return {
            "success": False,
            "action": "share_file_whatsapp",
            "error": f"WhatsApp sharing failed: {str(e)}"
        }


def record_audio(duration: int = 5) -> dict:
    """Record microphone audio and save it to disk."""
    try:
        import pyaudio
        import wave
        from datetime import datetime
        import os
        
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        CHUNK = 1024
        
        p = pyaudio.PyAudio()
        
        stream = p.open(format=FORMAT, channels=CHANNELS,
                        rate=RATE, input=True,
                        frames_per_buffer=CHUNK)
                        
        print(f"[*] Recording audio for {duration} seconds...")
        frames = []
        for i in range(0, int(RATE / CHUNK * duration)):
            data = stream.read(CHUNK)
            frames.append(data)
            
        print("[*] Recording finished.")
        
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        recordings_dir = os.path.join(os.getcwd(), "Recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"recording_{timestamp}.wav"
        filepath = os.path.join(recordings_dir, filename)
        
        wf = wave.open(filepath, 'wb')
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        wf.close()
        
        return {
            "success": True,
            "action": "record_audio",
            "path": filepath,
            "filename": filename,
            "response": f"🎤 Audio recorded successfully for {duration} seconds: `{filename}`"
        }
    except Exception as e:
        return {"success": False, "action": "record_audio", "error": f"Audio recording failed: {str(e)}"}


def send_file_telegram(file_path: str, caption: str | None = None) -> dict:
    """Send any captured file (photo, document, audio recording) to the user's Telegram."""
    from config import settings
    import httpx
    import os
    
    if not settings.has_telegram():
        return {
            "success": False,
            "action": "send_file_telegram",
            "error": "Telegram bot token or Chat ID is not configured in .env file."
        }
        
    resolved_path = os.path.expandvars(os.path.expanduser(file_path.strip()))
    if not os.path.exists(resolved_path):
        return {
            "success": False,
            "action": "send_file_telegram",
            "error": f"File not found on system: {file_path}"
        }
        
    filename = os.path.basename(resolved_path).lower()
    is_photo = filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))
    method = "sendPhoto" if is_photo else "sendDocument"
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    
    try:
        with open(resolved_path, "rb") as f:
            files = {
                "photo" if is_photo else "document": (os.path.basename(resolved_path), f)
            }
            data = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
            }
            if caption:
                data["caption"] = caption
                
            resp = httpx.post(url, data=data, files=files, timeout=30.0)
            if resp.status_code == 200:
                return {
                    "success": True,
                    "action": "send_file_telegram",
                    "path": resolved_path,
                    "response": f"📤 Sent file `{os.path.basename(resolved_path)}` successfully to Telegram."
                }
            else:
                return {
                    "success": False,
                    "action": "send_file_telegram",
                    "error": f"Telegram API returned status {resp.status_code}: {resp.text}"
                }
    except Exception as e:
        return {
            "success": False,
            "action": "send_file_telegram",
            "error": f"Failed to send file to Telegram: {str(e)}"
        }


def read_whatsapp_messages(contact_name: str = "") -> dict:
    """Read the latest messages from a WhatsApp contact or the active chat.
    
    Args:
        contact_name: Optional name of the contact to read messages from.
                      If empty, reads the currently active chat.
    """
    import subprocess
    import pyautogui
    import time
    import webbrowser
    from chat_engine import chat
    
    try:
        # Open WhatsApp Web
        webbrowser.open("https://web.whatsapp.com")
        print("[*] Opening WhatsApp Web... Waiting for page to load (8s)...")
        time.sleep(8.0)
        
        if contact_name:
            # Focus search bar
            pyautogui.hotkey("ctrl", "alt", "/")
            time.sleep(0.5)
            
            # Clear search and write contact name
            pyautogui.hotkey("ctrl", "a")
            pyautogui.press("backspace")
            time.sleep(0.2)
            pyautogui.write(contact_name, interval=0.05)
            time.sleep(2.0)
            
            # Open Chat
            pyautogui.press("enter")
            time.sleep(1.5)
            
        # Click neutral spot in chat window to focus it (middle-right area)
        pyautogui.click(800, 500)
        time.sleep(0.5)
        
        # Select all text on page and copy
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.3)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.5)
        
        # Click again to clear selection
        pyautogui.click(800, 500)
        
        # Retrieve clipboard content via PowerShell
        cmd = 'powershell -NoProfile -Command "Get-Clipboard"'
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8")
        clipboard_text = result.stdout.strip()
        
        if not clipboard_text:
            return {
                "success": False,
                "action": "read_whatsapp_messages",
                "error": "Failed to copy messages or clipboard is empty."
            }
            
        # Analyze with LLM
        analysis_prompt = (
            f"Analyze the following raw WhatsApp page text. "
            f"Identify the chat history for '{contact_name or 'the currently active chat'}' and extract "
            f"the latest messages (sender, timestamp, content). "
            f"Provide a concise, user-friendly summary of the messages. "
            f"Respond in a natural assistant tone (Hinglish/English is fine).\n\n"
            f"Raw text:\n{clipboard_text[:12000]}"
        )
        summary = chat(analysis_prompt)
        
        return {
            "success": True,
            "action": "read_whatsapp_messages",
            "contact": contact_name or "active_chat",
            "response": summary
        }
    except Exception as e:
        return {
            "success": False,
            "action": "read_whatsapp_messages",
            "error": f"Failed to read WhatsApp messages: {str(e)}"
        }


# ═════════════════════════════════════════════════════════════════════
#  MASTER EXECUTOR -- routes decisions to the right handler
# ═════════════════════════════════════════════════════════════════════

def execute_decision(decision: str) -> dict:
    """Execute a decision and record it to the transcript store."""
    result = _execute_decision_inner(decision)
    from system_automation import _transcripts
    _transcripts.record(decision, result)
    return result

def _execute_decision_inner(decision: str) -> dict:
    """Execute a single decision string from the AI decision maker."""
    decision = decision.strip()
    d_lower = decision.lower()

    if d_lower.startswith("open "):
        return open_app(decision[5:].strip())

    elif d_lower.startswith("close "):
        target = decision[6:].strip()
        if target in ("all apps", "all applications", "everything"):
            return close_all_apps()
        return close_app(target)

    elif d_lower.startswith("schedule "):
        return schedule_task(decision[9:].strip())

    elif d_lower.startswith("play "):
        return play_youtube(decision[5:].strip())

    elif d_lower.startswith("google search "):
        return google_search(decision[14:].strip())

    elif d_lower.startswith("youtube search "):
        return youtube_search(decision[15:].strip())

    elif d_lower.startswith("app search "):
        # Expected format: "app search <app_name> | <query>"
        body = decision[11:].strip()  # after "app search "
        if "|" in body:
            parts = body.split("|", 1)
            app_name = parts[0].strip()
            query = parts[1].strip()
        else:
            return google_search(body)
        return app_search(app_name, query)

    elif d_lower.startswith("youtube control "):
        return youtube_control(decision[16:].strip())

    elif d_lower.startswith("slide control "):
        return slide_control(decision[14:].strip())

    elif d_lower.startswith("media control "):
        return media_control(decision[14:].strip())
        
    elif d_lower.startswith("browser control "):
        return browser_control(decision[16:].strip())

    elif d_lower.startswith("system "):
        return system_control(decision[7:].strip())

    elif d_lower.startswith("screenshot path"):
        # User is asking for the path of the last screenshot
        global _LAST_SCREENSHOT_PATH
        if _LAST_SCREENSHOT_PATH:
            return {
                "success": True,
                "action": "screenshot_path",
                "path": _LAST_SCREENSHOT_PATH,
                "response": f"Sir, screenshot yeh path pe save hai:\n`{_LAST_SCREENSHOT_PATH}`"
            }
        else:
            return {
                "success": False,
                "action": "screenshot_path",
                "error": "Koi screenshot nahi liya gaya abhi tak. (No screenshot taken yet.)"
            }

    elif d_lower.startswith("screenshot"):
        fname = decision[10:].strip() if len(decision) > 10 else None
        # Regular screenshot always opens the file (open_file=True by default)
        return take_screenshot(fname or None, open_file=True)

    elif d_lower.startswith("content "):
        return write_content(decision[8:].strip())

    elif d_lower.startswith("monitor system") or d_lower == "monitor":
        return monitor_system()

    elif d_lower.startswith("whatsapp share "):
        # Expected: "whatsapp share <contact_name> | <file_path>"
        body = decision[15:].strip()
        if "|" in body:
            parts = body.split("|", 1)
            contact = parts[0].strip()
            path = parts[1].strip()
            return share_file_whatsapp(contact, path)
        else:
            return {"success": False, "action": "share_file_whatsapp", "error": "Use format: whatsapp share <contact_name> | <file_path>"}

    elif d_lower.startswith("whatsapp read ") or d_lower == "whatsapp read" or d_lower.startswith("read whatsapp"):
        contact = ""
        if d_lower.startswith("whatsapp read "):
            contact = decision[14:].strip()
        elif d_lower.startswith("read whatsapp "):
            contact = decision[14:].strip()
        return read_whatsapp_messages(contact)

    elif d_lower.startswith("record audio"):
        duration = 5
        body = decision[12:].strip()
        if body.isdigit():
            duration = int(body)
        return record_audio(duration)

    elif d_lower.startswith("telegram file "):
        # Expected: "telegram file <file_path> | <caption_optional>"
        body = decision[14:].strip()
        caption = None
        if "|" in body:
            parts = body.split("|", 1)
            path = parts[0].strip()
            caption = parts[1].strip()
        else:
            path = body
        return send_file_telegram(path, caption)

    elif d_lower.startswith("check project status") or d_lower == "project status":
        try:
            from agents.project_builder import check_build_status
            report = check_build_status()
            return {"success": True, "action": "check_project_status", "response": report}
        except Exception as e:
            return {"success": False, "action": "check_project_status", "error": str(e)}

    elif d_lower.startswith("general "):
        from chat_engine import chat
        answer = chat(decision[8:].strip())
        return {"success": True, "action": "chat", "response": answer}

    elif d_lower.startswith("realtime "):
        from chat_engine import realtime_search
        answer = realtime_search(decision[9:].strip())
        return {"success": True, "action": "realtime", "response": answer}

    elif d_lower.startswith("read file "):
        path = decision[10:].strip()
        try:
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            r = ft.read_system_file(path)
            if r.success:
                return {"success": True, "action": "read_file", "path": path, "response": r.output[:2000]}
            return {"success": False, "action": "read_file", "error": r.output}
        except Exception as e:
            return {"success": False, "action": "read_file", "error": str(e)}

    elif d_lower.startswith("rag search "):
        query = decision[11:].strip()
        try:
            from rag_engine import RAGVoiceEngine
            # Initialize RAG on current directory and ensure it's indexed
            rag_engine = RAGVoiceEngine()
            rag_engine.ensure_indexed(max_files=150)
            results = rag_engine.search_knowledge(query, top_k=3)
            
            if results:
                formatted_response = f"🔍 **Semantic RAG Search Results for '{query}':**\n\n"
                for i, r in enumerate(results, 1):
                    formatted_response += f"**Result {i}:** `{r['source']}` *(Score: {r['score']})*\n```text\n{r['content'].strip()}...\n```\n\n"
                return AutomationResult(success=True, action="rag_search", response=formatted_response).to_dict()
            return AutomationResult(success=True, action="rag_search", response=f"No relevant contextual files found for '{query}'.").to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="rag_search", error=str(e)).to_dict()

    elif d_lower.startswith("list dir "):
        path = decision[9:].strip()
        try:
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            r = ft.list_system_dir(path)
            if r.success:
                return {"success": True, "action": "list_dir", "path": path, "response": r.output}
            return {"success": False, "action": "list_dir", "error": r.output}
        except Exception as e:
            return {"success": False, "action": "list_dir", "error": str(e)}

    elif d_lower.startswith("convert file "):
        # Parse: "convert file <path> to <format>"
        parts = decision[13:].strip()
        if " to " in parts.lower():
            idx = parts.lower().rindex(" to ")
            input_path = parts[:idx].strip()
            target_format = parts[idx + 4:].strip()
        else:
            return {"success": False, "action": "convert_file", "error": "Use format: convert file <path> to <format>"}
        try:
            from file_converter import FileConverter
            converter = FileConverter()
            result = converter.convert(input_path, target_format)
            if result.get("success"):
                return {"success": True, "action": "convert_file", "response": f"File converted successfully! (Path hidden unless requested)", "details": result}
            return {"success": False, "action": "convert_file", "error": result.get("error")}
        except Exception as e:
            return {"success": False, "action": "convert_file", "error": str(e)}

    elif d_lower.startswith("generate image "):
        prompt = decision[15:].strip()
        try:
            from image_generator import ImageGenerator
            gen = ImageGenerator()
            result = gen.generate(prompt)
            if result.get("success"):
                return {"success": True, "action": "generate_image", "response": f"Image generated! (Path hidden unless requested)", "details": result}
            return {"success": False, "action": "generate_image", "error": result.get("error")}
        except Exception as e:
            return {"success": False, "action": "generate_image", "error": str(e)}

    elif d_lower.startswith("generate video "):
        prompt = decision[15:].strip()
        try:
            from video_generator import VideoGenerator
            gen = VideoGenerator()
            result = gen.generate(prompt)
            if result.get("success"):
                return {"success": True, "action": "generate_video", "response": f"Video generated! (Path hidden unless requested)", "details": result}
            return {"success": False, "action": "generate_video", "error": result.get("error")}
        except Exception as e:
            return {"success": False, "action": "generate_video", "error": str(e)}

    elif d_lower.startswith("file info "):
        path = decision[10:].strip()
        try:
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            r = ft.get_file_info(path)
            if r.success:
                return {"success": True, "action": "file_info", "path": path, "response": r.output}
            return {"success": False, "action": "file_info", "error": r.output}
        except Exception as e:
            return {"success": False, "action": "file_info", "error": str(e)}

    elif d_lower.startswith("scrape website "):
        url = decision[15:].strip()
        try:
            from research_agent import ResearchAgent
            researcher = ResearchAgent()
            result = researcher.scrape_website(url)
            if result.get("success"):
                raw_content = result.get("content", "")
                # Synthesize with LLM into rich markdown report
                try:
                    from chat_engine import chat
                    summary = chat(
                        f"You are a web analyst. The following raw text was scraped from: {url}\n\n"
                        f"Create a detailed, well-structured summary report in Markdown format. "
                        f"Include the following sections as relevant:\n"
                        f"## 🌐 Overview\n## 🔑 Key Details\n## 📋 Main Content / Services\n"
                        f"## 📞 Contact & Links (if found)\n## 💡 Key Takeaways\n\n"
                        f"Raw scraped content (up to 4000 chars):\n\n{raw_content[:4000]}"
                    )
                    full_response = (
                        f"## 🕷️ Web Scrape Report\n"
                        f"**Source:** [{url}]({url})\n\n"
                        f"---\n\n"
                        f"{summary}"
                    )
                    return {"success": True, "action": "scrape_website", "url": url, "response": full_response}
                except Exception:
                    # Fallback: return raw content formatted
                    formatted = (
                        f"## 🕷️ Scraped Content\n"
                        f"**Source:** {url}\n\n"
                        f"---\n\n"
                        f"{raw_content[:3000]}"
                    )
                    return {"success": True, "action": "scrape_website", "url": url, "response": formatted}
            return {"success": False, "action": "scrape_website", "error": result.get("error")}
        except Exception as e:
            return {"success": False, "action": "scrape_website", "error": str(e)}

    elif d_lower.startswith("generate code "):
        prompt = decision[14:].strip()
        try:
            from chat_engine import chat
            from tool_forge import SandboxRunner
            
            # 1. Ask LLM to write pure Python script responding to the prompt
            code_response = chat(f"You are a master Python developer. Write a pure Python script to fulfill this request: '{prompt}'. "
                                 f"IMPORTANT: Return ONLY the raw Python code. Do not include markdown blocks, triple backticks, or any conversational text. "
                                 f"Do not write ```python at the top. Ensure it uses standard libraries or prints its output cleanly.")
            
            # Clean up the output in case the LLM ignored formatting rules
            clean_code = code_response
            if "```python" in clean_code:
                clean_code = clean_code.split("```python")[1].split("```")[0]
            elif "```" in clean_code:
                clean_code = clean_code.split("```")[1].split("```")[0]
            clean_code = clean_code.strip()
            
            # 2. Run the generated code in the sandbox securely
            runner = SandboxRunner(timeout=45, max_output=500_000)
            sandbox_result = runner.run_raw_code(clean_code)
            
            # 3. Format response
            if sandbox_result.success:
                formatted = f"⚡ **Code Executed Successfully!**\n\n**Generated Code:**\n```python\n{clean_code[:1000]}...\n```\n\n**Output:**\n```text\n{sandbox_result.output}\n```"
                return AutomationResult(success=True, action="generate_code", response=formatted, details={"code": clean_code}).to_dict()
            else:
                formatted = f"❌ **Code Execution Failed!**\n\n**Error:**\n```text\n{sandbox_result.error}\n```\n\n**Generated Code:**\n```python\n{clean_code[:1000]}...\n```"
                return AutomationResult(success=False, action="generate_code", response=formatted, error=sandbox_result.error).to_dict()
                
        except Exception as e:
            return AutomationResult(success=False, action="generate_code", error=str(e)).to_dict()

    elif d_lower.startswith("bash "):
        command = decision[5:].strip()
        try:
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            
            # ── PERMISSION GATE: Check if command requires approval ──
            perm_check = ft.enforcer.check_bash(command)
            
            # If command is blocked entirely, return error
            if not perm_check.allowed and "BLOCKED" in perm_check.reason:
                return AutomationResult(
                    success=False, 
                    action="bash", 
                    error=perm_check.reason
                ).to_dict()
            
            # If command requires approval, ask first (don't execute yet) ──────
            if perm_check.requires_approval:
                pending_key = store_pending_shell_command(command, "bash", "Bash command")
                formatted = (
                    f"🔒 **Shell Command Requires Permission:**\n\n"
                    f"**Command:** `{command}`\n\n"
                    f"This command writes to files or makes system changes. "
                    f"Sir, kya main yeh command execute kar dun? "
                    f"(Kripaya 'haan' ya 'yes' se confirm karein)"
                )
                return AutomationResult(
                    success=False,  # Not yet successful
                    action="bash",
                    response=formatted,
                    details={"requires_approval": True, "command": command, "pending_key": pending_key, "pending_execution": True}
                ).to_dict()
            
            # Command approved or read-only, execute it ──────────────────────────
            r = ft.bash(command)
            if r.success:
                return AutomationResult(success=True, action="bash", response=f"⚡ **Command Executed:**\n```bash\n{command}\n```\n\n**Output:**\n```text\n{r.output}\n```").to_dict()
            return AutomationResult(success=False, action="bash", error=r.output).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="bash", error=str(e)).to_dict()

    elif d_lower.startswith("smart shell "):
        user_request = decision[12:].strip()
        try:
            from shell_gpt_bridge import smart_shell
            
            # ── STEP 1: Generate the command FIRST ────────────────────────
            command = smart_shell.generate_command(user_request)
            description = smart_shell.describe_command(command)
            
            # ── STEP 2: Check if command needs permission ─────────────────
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            perm_check = ft.enforcer.check_bash(command)
            
            # If command is blocked entirely, return error
            if not perm_check.allowed and "BLOCKED" in perm_check.reason:
                return AutomationResult(
                    success=False, 
                    action="smart_shell", 
                    error=perm_check.reason,
                    details={"command": command, "description": description}
                ).to_dict()
            
            # If command requires approval, ASK FIRST ────────────────────────
            if perm_check.requires_approval:
                pending_key = store_pending_shell_command(command, "smart_shell", description)
                formatted = (
                    f"🔒 **Smart Shell Command - Permission Required:**\n\n"
                    f"**Your Request:** {user_request}\n\n"
                    f"**Generated Command:**\n```bash\n{command}\n```\n\n"
                    f"**What it does:** {description}\n\n"
                    f"This command will make system changes. "
                    f"Sir, kya main yeh execute kar dun? "
                    f"(Kripaya 'haan' ya 'yes' se confirm karein)"
                )
                return AutomationResult(
                    success=False,  # Not yet successful - awaiting permission
                    action="smart_shell",
                    response=formatted,
                    details={
                        "requires_approval": True,
                        "command": command,
                        "description": description,
                        "user_request": user_request,
                        "pending_key": pending_key,
                        "pending_execution": True
                    }
                ).to_dict()
            
            # ── STEP 3: Command approved, execute it ──────────────────────
            result = smart_shell.execute_command(command)
            
            if result.exit_code == 0 or result.executed:
                formatted = (
                    f"🧠 **Smart Shell Command Executed:**\n\n"
                    f"**Request:** {user_request}\n"
                    f"**Command:** `{result.command}`\n"
                    f"**Description:** {result.description}\n\n"
                    f"**Output:**\n```text\n{result.output[:3000]}\n```"
                )
                return AutomationResult(success=True, action="smart_shell", response=formatted).to_dict()
            else:
                return AutomationResult(
                    success=False, action="smart_shell",
                    response=f"Command `{result.command}` failed: {result.error}",
                    error=result.error
                ).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="smart_shell", error=str(e)).to_dict()

    elif d_lower.startswith("describe command "):
        command = decision[17:].strip()
        try:
            from shell_gpt_bridge import smart_shell
            description = smart_shell.describe_command(command)
            formatted = (
                f"📖 **Command Description:**\n\n"
                f"**Command:** `{command}`\n\n"
                f"{description}"
            )
            return AutomationResult(success=True, action="describe_command", response=formatted).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="describe_command", error=str(e)).to_dict()

    elif d_lower.startswith("execute pending shell "):
        # Handler for executing a previously approved shell command
        pending_key = decision[22:].strip()
        try:
            return execute_pending_shell_command(pending_key)
        except Exception as e:
            return AutomationResult(success=False, action="execute_pending", error=str(e)).to_dict()

    elif d_lower.startswith("nlp summarize "):
        return nlp_summarize(decision[14:].strip())

    elif d_lower.startswith("nlp translate "):
        body = decision[14:].strip()
        if "|" in body:
            parts = body.split("|", 1)
            lang = parts[0].strip()
            text = parts[1].strip()
            return nlp_translate(lang, text)
        else:
            return {"success": False, "action": "nlp_translate", "error": "Invalid format. Expected: nlp translate <language> | <text>"}

    elif d_lower.startswith("nlp sentiment "):
        return nlp_sentiment(decision[14:].strip())

    elif d_lower.startswith("nlp rewrite "):
        return nlp_rewrite(decision[12:].strip())

    elif d_lower.startswith("deep research "):
        query = decision[14:].strip()
        try:
            from deep_research import DeepResearchEngine
            engine = DeepResearchEngine()
            result = engine.research(query, max_sources=5, depth="standard")
            if result.success:
                return AutomationResult(success=True, action="deep_research", response=result.to_response()).to_dict()
            return AutomationResult(success=False, action="deep_research", error=result.error or "Research failed").to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="deep_research", error=str(e)).to_dict()

    elif d_lower.startswith("organize files "):
        directory = decision[15:].strip()
        try:
            from file_organizer import FileOrganizer
            organizer = FileOrganizer()
            result = organizer.organize(directory)
            if result.success:
                return AutomationResult(success=True, action="organize_files", response=result.to_response()).to_dict()
            return AutomationResult(success=False, action="organize_files", error="\n".join(result.errors)).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="organize_files", error=str(e)).to_dict()

    elif d_lower.startswith("computer use "):
        instruction = decision[13:].strip()
        try:
            from computer_use import ComputerUseEngine
            engine = ComputerUseEngine()
            result = engine.execute_task(instruction, max_steps=5)
            if result.success:
                actions_desc = ", ".join(a.description for a in result.actions_taken) if result.actions_taken else "No actions"
                response = (
                    f"🖥️ **Computer Use Complete**\n\n"
                    f"**Actions taken:** {actions_desc}\n\n"
                    f"**Verification:** {result.verification or 'N/A'}"
                )
                return AutomationResult(success=True, action="computer_use", response=response).to_dict()
            return AutomationResult(success=False, action="computer_use", error=result.error or "Computer use failed").to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="computer_use", error=str(e)).to_dict()

    elif d_lower.startswith("morning briefing"):
        try:
            from proactive_agent import get_proactive_agent
            agent = get_proactive_agent()
            briefing = agent.generate_morning_briefing()
            return AutomationResult(success=True, action="morning_briefing", response=briefing).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="morning_briefing", error=str(e)).to_dict()

    elif d_lower.startswith("code search "):
        query = decision[12:].strip()
        try:
            from rag_engine import RAGVoiceEngine
            rag = RAGVoiceEngine()
            rag.ensure_indexed(max_files=200)
            code_results = rag.search_code(query)
            if code_results:
                formatted = f"🔍 **Code Search Results for '{query}':**\n\n"
                for i, r in enumerate(code_results, 1):
                    formatted += (
                        f"**{i}. [{r['type'].upper()}] `{r['name']}`**\n"
                        f"  📄 File: `{r['file']}` (line {r['line']})\n"
                        f"  📝 Signature: `{r['signature']}`\n"
                    )
                    if r.get('docstring'):
                        formatted += f"  💡 Docs: {r['docstring'][:150]}\n"
                    if r.get('calls'):
                        formatted += f"  ➡️ Calls: {', '.join(r['calls'][:5])}\n"
                    if r.get('callers'):
                        formatted += f"  ⬅️ Called by: {', '.join(r['callers'][:5])}\n"
                    formatted += "\n"
                return AutomationResult(success=True, action="code_search", response=formatted).to_dict()
            return AutomationResult(success=True, action="code_search", response=f"No code entities found matching '{query}'.").to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="code_search", error=str(e)).to_dict()

    elif d_lower.startswith("find file "):
        filename = decision[10:].strip()
        try:
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            r = ft.find_system_file(filename)
            if r.success:
                files = r.output.strip().split("\n")
                if files and files[0] != "No matching files found.":
                    formatted = f"📁 **Found {len(files)} match(es) for '{filename}':**\n\n"
                    for i, f in enumerate(files[:10], 1):
                        formatted += f"  {i}. `{f}`\n"
                    return AutomationResult(success=True, action="find_file", response=formatted).to_dict()
                return AutomationResult(success=True, action="find_file", response=f"No files matching '{filename}' were found.").to_dict()
            return AutomationResult(success=False, action="find_file", error=r.output).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="find_file", error=str(e)).to_dict()

    elif d_lower.startswith("find folder "):
        foldername = decision[12:].strip()
        try:
            from file_tools import FileToolSystem
            ft = FileToolSystem()
            r = ft.find_system_folder(foldername)
            if r.success:
                folders = r.output.strip().split("\n")
                if folders and folders[0] != "No matching folders found.":
                    formatted = f"📁 **Found {len(folders)} match(es) for folder '{foldername}':**\n\n"
                    for i, f in enumerate(folders[:10], 1):
                        formatted += f"  {i}. `{f}`\n"
                    return AutomationResult(success=True, action="find_folder", response=formatted).to_dict()
                return AutomationResult(success=True, action="find_folder", response=f"No folders matching '{foldername}' were found.").to_dict()
            return AutomationResult(success=False, action="find_folder", error=r.output).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="find_folder", error=str(e)).to_dict()

    elif d_lower.startswith("analyze screen"):
        try:
            print("[SYSTEM_AUTOMATION] Analyze screen triggered")
            # Step 1: Show blue overlay on screen (visual feedback)
            try:
                import requests
                import time
                print("[SYSTEM_AUTOMATION] Calling POST /api/overlay/scan to trigger blue overlay")
                # Send overlay request and give it time to render
                response = requests.post("http://127.0.0.1:8000/api/overlay/scan", timeout=5)
                print("[SYSTEM_AUTOMATION] Overlay scan API response:", response.status_code, response.text)
                time.sleep(0.3)  # Give overlay time to appear
            except Exception as e:
                print(f"[OVERLAY] Failed to trigger overlay: {e}")
                pass  # Continue even if overlay fails
            
            # Step 2: Take screenshot for analysis (don't open it)
            from vision_engine import VisionEngine
            engine = VisionEngine()
            result_text = engine.analyze_screen()
            return AutomationResult(
                success=True, action="analyze_screen",
                response=f"🖥️ **Screen Analysis:**\n\n{result_text}",
            ).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="analyze_screen", error=str(e)).to_dict()

    elif d_lower.startswith("scan"):
        # "scan" or "scan screen" or "scan my screen"
        try:
            # Step 1: Show blue overlay on screen (visual feedback)
            try:
                import requests
                import time
                # Send overlay request and give it time to render
                requests.post("http://127.0.0.1:8000/api/overlay/scan", timeout=5)
                time.sleep(0.3)  # Give overlay time to appear
            except Exception as e:
                print(f"[OVERLAY] Failed to trigger overlay: {e}")
                pass  # Continue even if overlay fails
            
            # Step 2: Take screenshot for analysis (don't open it)
            from vision_engine import VisionEngine
            engine = VisionEngine()
            result_text = engine.analyze_screen()
            return AutomationResult(
                success=True, action="scan_screen",
                response=f"🖥️ **Screen Scan Complete:**\n\n{result_text}",
            ).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="scan_screen", error=str(e)).to_dict()

    elif d_lower.startswith("analyze image "):
        path = decision[14:].strip()
        try:
            from vision_engine import VisionEngine
            engine = VisionEngine()
            result_text = engine.analyze_image(path)
            return AutomationResult(
                success=True, action="analyze_image",
                response=f"🖼️ **Image Analysis** (`{path}`):\n\n{result_text}",
            ).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="analyze_image", error=str(e)).to_dict()

    elif d_lower.startswith("generate website "):
        prompt = decision[17:].strip()
        try:
            from website_generator import WebsiteGenerator
            gen = WebsiteGenerator()
            result = gen.generate(prompt)
            page_list = ", ".join(f"`{p}.html`" for p in result.pages)
            lang_info = ""
            if result.language != "en":
                from website_generator import _LANG_NAMES
                lang_name = _LANG_NAMES.get(result.language, result.language)
                lang_info = f"**Language:** {lang_name}\n"
            img_count = sum(1 for f in result.files if f.get("lang") == "image")
            img_info = f"**Images:** AI-generated hero + Unsplash context images\n" if img_count else "**Images:** Unsplash context-aware images\n"
            formatted = (
                f"🌐 **Website Generated Successfully!**\n\n"
                f"**Project:** {result.title}\n"
                f"**Type:** {result.site_type.title()}\n"
                f"**Theme:** {result.theme.title()}\n"
                f"{lang_info}"
                f"**Pages:** {page_list}\n"
                f"{img_info}"
                f"**Files:** {len(result.files)} files created\n\n"
                f"📂 **Location:** `{result.output_dir}`\n\n"
                f"The website has been opened in your browser. "
                f"All pages are fully responsive with modern animations, glassmorphism effects, "
                f"context-aware images, and interactive elements."
            )
            return AutomationResult(
                success=True,
                action="generate_website",
                response=formatted,
                details=result.to_dict(),
            ).to_dict()
        except Exception as e:
            return AutomationResult(success=False, action="generate_website", error=str(e)).to_dict()

    elif d_lower == "exit":
        return {"success": True, "action": "exit", "response": "Goodbye! See you later."}

    else:
        # Default: treat as general chat (with response caching)
        from chat_engine import chat
        try:
            from shell_gpt_bridge import response_cache
            cached = response_cache.get(decision)
            if cached:
                return {"success": True, "action": "chat_cached", "response": cached}
        except Exception:
            pass
        answer = chat(decision)
        try:
            from shell_gpt_bridge import response_cache
            response_cache.set(decision, answer)
        except Exception:
            pass
        return {"success": True, "action": "chat", "response": answer}

# ── Local Persistent History (Claw-Code architecture) ────────────────

class TranscriptStore:
    """Maintains a rolling transcript of local system decisions executed."""
    def __init__(self, max_history: int = 25):
        self.history: list[dict] = []
        self.max_history = max_history

    def record(self, decision: str, result: dict) -> None:
        self.history.append({"decision": decision, "result": result, "timestamp": datetime.now().isoformat()})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

# Global store for process session
_transcripts = TranscriptStore()


async def execute_all(decisions: list[str]) -> list[dict]:
    """Execute all decisions from the AI decision maker."""
    results = []
    for decision in decisions:
        result = execute_decision(decision)
        results.append(result)
    return results
