import sys
from AppOpener import close, open as appopen
from webbrowser import open as webopen
from pywhatkit import search, playonyt
from dotenv import dotenv_values
from bs4 import BeautifulSoup
import asyncio
from rich import print
import webbrowser
import subprocess
import requests
import keyboard
import psutil
import os
from PIL import ImageGrab  # For taking screenshots
from datetime import datetime
import platform

env_vars = dotenv_values(".env")
classes = [
    "zCubwf", "hgKELc", "LTKOO sY7ric", "Z0LcW", "gsrt vk_bk FzvWSb YwPhnf", "pclqee", "tw-Data-text tw-text-small tw-ta", 
    "IZ6rdc", "O5uR6d LTKOO", "vIzY6d", "webanswers-webanswers_table__webanswers-table", "dDoNo ikb4Bb gsrt", "sXLaOe",
     "LMkfKe", "VQF4g", "qv3Wpe", "kno-rdesc", "SPZz6b"
]   

useragent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.75 Safari/537.36"

professional_responses = [
    "Your satisfaction is my top priority. Feel free to reach out if there's anything else I can help you with.",
    "I'm at your service for any additional questions or support you may need—don't hesitate to ask.",
]

messages = []

SystemChatbot = [{"role": "system", "content": f"Hello, I am {os.environ.get('Username', 'User')}, You're a content writer. You have to write content like letters, codes, applications, essays, notes, songs, poems etc."}]

def TakeScreenshot(filename=None):
    """Take a screenshot and save it with optional custom filename"""
    try:
        # Create Screenshots directory if it doesn't exist
        screenshots_dir = os.path.join(os.getcwd(), "Screenshots")
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
            print(f"Created directory: {screenshots_dir}")
        
        # Generate filename if not provided
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
        elif not filename.endswith(('.png', '.jpg', '.jpeg')):
            filename += ".png"
        
        # Full path for the screenshot
        screenshot_path = os.path.join(screenshots_dir, filename)
        
        # Take screenshot based on platform
        if platform.system() == "Windows":
            # Use PIL ImageGrab for Windows
            screenshot = ImageGrab.grab()
            screenshot.save(screenshot_path)
        elif platform.system() == "Darwin":  # macOS
            # Use screencapture command on macOS
            subprocess.run(['screencapture', screenshot_path], check=True)
        else:  # Linux
            # Use gnome-screenshot or import command on Linux
            try:
                subprocess.run(['gnome-screenshot', '-f', screenshot_path], check=True)
            except subprocess.CalledProcessError:
                try:
                    subprocess.run(['import', screenshot_path], check=True)
                except subprocess.CalledProcessError:
                    print("Error: No screenshot tool found. Please install gnome-screenshot or ImageMagick")
                    return False
        
        print(f"Screenshot saved successfully: {screenshot_path}")
        
        # Optionally open the screenshot
        try:
            if sys.platform.startswith('win'):
                os.startfile(screenshot_path)
            elif sys.platform.startswith('darwin'):
                subprocess.Popen(['open', screenshot_path])
            else:
                subprocess.Popen(['xdg-open', screenshot_path])
        except Exception as e:
            print(f"Screenshot saved but couldn't open automatically: {e}")
        
        return True
        
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return False

def GoogleSearch(Topic):
    search(Topic)  # Use pywhatkit's search function to perform a Google search.
    return True  # Indicate success.

def Content(Topic):
    def OpenNotepad(file):
        try:
            if sys.platform.startswith('win'):
                # Windows
                default_text_editor = "notepad.exe"
                subprocess.Popen([default_text_editor, file])
            elif sys.platform.startswith('darwin'):
                # macOS
                subprocess.Popen(['open', file])
            else:
                # Linux/Unix
                subprocess.Popen(['xdg-open', file])
            print(f"Opened file: {file}")
            return True
        except Exception as e:
            print(f"Error opening file {file}: {e}")
            return False

    def ContentWriterAI(prompt):
        try:
            messages.append({"role": "user", "content": f"{prompt}"})

            try:
                from ai_engine import ai_engine
                import asyncio
                Answer = asyncio.run(ai_engine.chat(SystemChatbot + messages, temperature=0.7, max_tokens=2048))
                if isinstance(Answer, dict) and "content" in Answer:
                    Answer = Answer["content"]
                elif hasattr(Answer, 'content'):
                    Answer = Answer.content
                Answer = str(Answer).replace("</s>", "")
                messages.append({"role": "assistant", "content": Answer})
                return Answer
            except Exception as api_error:
                print(f"API error: {api_error}")
                return f"Error generating content: {api_error}"
                
        except Exception as e:
            print(f"Error in ContentWriterAI: {e}")
            return f"Error: {e}"

    try:
        # Handle the Topic properly
        Topic_cleaned = Topic.replace("Content ", "").strip()
        if not Topic_cleaned:
            return False
            
        print(f"Generating content for: {Topic_cleaned}")
        ContentByAI = ContentWriterAI(Topic_cleaned)
        
        # Ensure Data directory exists
        data_dir = os.path.join(os.getcwd(), "Data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        # Create a safe filename
        safe_filename = Topic_cleaned.lower().replace(' ', '_')[:50]  # Limit length and replace spaces
        file_path = os.path.join(data_dir, f"{safe_filename}.txt")
        
        # Write content to file
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(ContentByAI)
            file.close()
        print(f"Content saved to: {file_path}")
        
        # Open the file
        success = OpenNotepad(file_path)
        return success
        
    except Exception as e:
        print(f"Error in Content function: {e}")
        return False

def YouTubeSearch(Topic):
    Url4Search = f"https://www.youtube.com/results?search_query={Topic}"  # Construct the YouTube search URL.
    webbrowser.open(Url4Search)
    return True  # Indicate success.

def YouTubeVideoControl(action):
    """Control YouTube videos with keyboard shortcuts"""
    try:
        if action == "play" or action == "pause":
            keyboard.press_and_release("space")  # Play/Pause toggle
        elif action == "mute":
            keyboard.press_and_release("m")  # Mute/Unmute
        elif action == "fullscreen":
            keyboard.press_and_release("f")  # Toggle fullscreen
        elif action == "exit fullscreen":
            keyboard.press_and_release("esc")  # Exit fullscreen
        elif action == "volume up":
            keyboard.press_and_release("up")  # Increase volume
        elif action == "volume down":
            keyboard.press_and_release("down")  # Decrease volume
        elif action == "forward" or action == "skip":
            keyboard.press_and_release("right")  # Skip forward 5 seconds
        elif action == "backward" or action == "rewind":
            keyboard.press_and_release("left")  # Skip backward 5 seconds
        elif action == "next":
            keyboard.press_and_release("shift+n")  # Next video
        elif action == "previous":
            keyboard.press_and_release("shift+p")  # Previous video
        elif action == "speed up":
            keyboard.press_and_release("shift+>")  # Increase playback speed
        elif action == "speed down":
            keyboard.press_and_release("shift+<")  # Decrease playback speed
        elif action == "normal speed":
            keyboard.press_and_release("shift+?")  # Reset to normal speed
        elif action == "captions":
            keyboard.press_and_release("c")  # Toggle captions
        elif action == "beginning":
            keyboard.press_and_release("home")  # Go to beginning
        elif action == "end":
            keyboard.press_and_release("end")  # Go to end
        else:
            print(f"Unknown YouTube control action: {action}")
            return False
        
        print(f"YouTube control executed: {action}")
        return True
    except Exception as e:
        print(f"Error controlling YouTube: {e}")
        return False

def SlideControl(action):
    """Control presentation slides (PowerPoint, Google Slides, etc.)"""
    try:
        if action == "next" or action == "next slide":
            keyboard.press_and_release("right")  # Next slide
        elif action == "previous" or action == "previous slide":
            keyboard.press_and_release("left")  # Previous slide
        elif action == "first" or action == "first slide":
            keyboard.press_and_release("home")  # Go to first slide
        elif action == "last" or action == "last slide":
            keyboard.press_and_release("end")  # Go to last slide
        elif action == "fullscreen" or action == "slideshow":
            keyboard.press_and_release("f5")  # Start slideshow
        elif action == "exit fullscreen" or action == "exit slideshow":
            keyboard.press_and_release("esc")  # Exit slideshow
        elif action == "black screen":
            keyboard.press_and_release("b")  # Black screen
        elif action == "white screen":
            keyboard.press_and_release("w")  # White screen
        elif action == "page up":
            keyboard.press_and_release("page up")  # Page up
        elif action == "page down":
            keyboard.press_and_release("page down")  # Page down
        else:
            print(f"Unknown slide control action: {action}")
            return False
        
        print(f"Slide control executed: {action}")
        return True
    except Exception as e:
        print(f"Error controlling slides: {e}")
        return False

def MediaControl(action):
    """General media control for various applications"""
    try:
        if action == "play pause":
            keyboard.press_and_release("ctrl+alt+space")  # Global play/pause
        elif action == "next track":
            keyboard.press_and_release("ctrl+alt+right")  # Next track
        elif action == "previous track":
            keyboard.press_and_release("ctrl+alt+left")  # Previous track
        elif action == "volume up":
            keyboard.press_and_release("volume up")  # System volume up
        elif action == "volume down":
            keyboard.press_and_release("volume down")  # System volume down
        elif action == "mute":
            keyboard.press_and_release("volume mute")  # System mute
        else:
            print(f"Unknown media control action: {action}")
            return False
        
        print(f"Media control executed: {action}")
        return True
    except Exception as e:
        print(f"Error controlling media: {e}")
        return False
            
def PlayYoutube(query):
    playonyt(query)  # Use pywhatkit's playonyt function to play the video.
    return True  # Indicate success.    

def OpenApp(app, sess=requests.session()):
    try:
        appopen(app, match_closest=True, output=True, throw_error=True)  # Attempt to open the app.
        return True  # Indicate success.
    
    except:
        # Nested function to extract links from HTML content.
        def extract_links(html):
            if html is None:
                return []
            
            soup = BeautifulSoup(html, 'html.parser')  # Parse the HTML content.
            links = soup.find_all('a', {'jsname': 'UWckNb'})  # Find relevant links.
            return [link.get('href') for link in links]  # Return the links.
         
        def search_google(query):
            url = f"https://www.google.com/search?q={query}"  # Construct the Google search URL.
            headers = {'User-Agent': useragent}  # Set the predefined user agent.
            response = sess.get(url, headers=headers)  # Perform the GET request.
            
            if response.status_code == 200:  # Return the HTML content.
                return response.text
            else:
                print("Failed to retrieve search results.")  # Print an error message.
            return None
        
        html = search_google(app)

        if html:
            links = extract_links(html)
            if links:  # Guard against empty list (IndexError)
                webopen(links[0])  # Open the first result in a web browser.
        return True  # Indicate success.
        
def CloseApp(app):
    if app.lower() == "yourself":
        print("Cannot close the assistant itself.")  # Prevent the assistant from closing itself.
        return False
    
    if app.lower() == "all tabs":
        # Close all web browser processes (e.g., Chrome, Edge)
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                # Check if the process is a web browser (e.g., Chrome, Edge)
                if "chrome" in proc.info['name'].lower() or "edge" in proc.info['name'].lower():
                    proc.terminate()  # Terminate the process (close the tab/window)
                print(f"Closed {proc.info['name']} process with PID {proc.info['pid']}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return True  # Indicate success

    # Check if the app name is a specific app, like 'youtube'
    if "youtube" in app.lower():
        try:
            # Assuming you are closing a browser tab related to YouTube
            webbrowser.open('about:blank')  # Close the tab or browser.
            print(f"Closed {app} successfully.")
            return True
        except Exception as e:
            print(f"Failed to close {app}: {e}")
            return False
    else:
        try:
            close(app, match_closest=True, output=True, throw_error=True)  # Attempt to close the app
            return True  # Indicate success
        except Exception as e:
            print(f"Failed to close {app}: {e}")
            return False

def System(command):
    # Nested function to mute the system volume.
    def mute():
        keyboard.press_and_release("volume mute")  # Simulate the mute key press.

    # Nested function to unmute the system volume.
    def unmute():
        keyboard.press_and_release("volume mute")  # Simulate the unmute key press.

    # Nested function to increase the system volume.
    def volume_up():
        keyboard.press_and_release("volume up")  # Simulate the volume up key press.

    # Nested function to decrease the system volume.
    def volume_down():
        keyboard.press_and_release("volume down")  # Simulate the volume down key press.

    # Nested function to shutdown the system.
    def shutdown():
        os.system("shutdown /s /t 1")  # Execute shutdown command.

    # Nested function to restart the system.
    def restart():
        os.system("shutdown /r /t 1")  # Execute restart command.

    # Nested function to lock the system.
    def lock():
        os.system("rundll32.exe user32.dll,LockWorkStation")  # Execute lock command.

    if command == "mute":
        mute()
    elif command == "unmute":
        unmute()
    elif command == "volume up":
        volume_up()
    elif command == "volume down":
        volume_down()
    elif command in ("shutdown", "shut down"):
        shutdown()
    elif command == "restart":
        restart()
    elif command == "lock window":
        lock()
    return True                 
                     
async def TranslateAndExecute(commands: list[str]):
    """Translate and execute commands with improved error handling"""
    funcs = []  # List to store asynchronous tasks.
    
    for command in commands:
        print(f"Processing command: {command}")
        try:
            if command.startswith("open "):  # Handle "open" commands.
                if "open it" in command or "open file" == command:  # Ignore "open it" commands.
                    print(f"Skipping generic open command: {command}")
                    continue
                
                app_name = command.removeprefix("open ").strip()
                print(f"Opening app: {app_name}")
                fun = asyncio.to_thread(OpenApp, app_name)  # Schedule app opening.
                funcs.append(fun)

            elif command.startswith("close "):  # Handle "close" commands.
                app_name = command.removeprefix("close ").strip()
                print(f"Closing app: {app_name}")
                fun = asyncio.to_thread(CloseApp, app_name)  # Schedule app closing.
                funcs.append(fun)

            elif command.startswith("play "):  # Handle "play" commands.
                query = command.removeprefix("play ").strip()
                print(f"Playing on YouTube: {query}")
                fun = asyncio.to_thread(PlayYoutube, query)  # Schedule YouTube playback.
                funcs.append(fun) 
            
            elif command.startswith("content "):  # Handle "content" commands.
                query = command.strip()  # Keep the whole command
                print(f"Generating content: {query}")
                fun = asyncio.to_thread(Content, query)  # Schedule content creation.
                funcs.append(fun)          
                
            elif command.startswith("google search "):  # Handle "google search" commands.
                query = command.removeprefix("google search ").strip()
                print(f"Searching Google: {query}")
                fun = asyncio.to_thread(GoogleSearch, query)  # Schedule Google search.
                funcs.append(fun)         
                 
            elif command.startswith("youtube search "):  # Handle "youtube search" commands.
                query = command.removeprefix("youtube search ").strip()
                print(f"Searching YouTube: {query}")
                fun = asyncio.to_thread(YouTubeSearch, query)  # Schedule YouTube search.
                funcs.append(fun)  
                
            elif command.startswith("system "):  # Handle "system" commands.
                action = command.removeprefix("system ").strip()
                print(f"System command: {action}")
                fun = asyncio.to_thread(System, action)  # Schedule system control.
                funcs.append(fun)
                
            elif command.startswith("screenshot") or command.startswith("take screenshot"):  # Handle screenshot commands
                if "screenshot " in command:
                    # Extract custom filename if provided
                    filename = command.split("screenshot ", 1)[1].strip()
                    if filename:
                        print(f"Taking screenshot with filename: {filename}")
                        fun = asyncio.to_thread(TakeScreenshot, filename)
                    else:
                        print("Taking screenshot with default filename")
                        fun = asyncio.to_thread(TakeScreenshot)
                else:
                    print("Taking screenshot with default filename")
                    fun = asyncio.to_thread(TakeScreenshot)
                funcs.append(fun)
                
            elif command.startswith("youtube control "):  # Handle YouTube control commands
                action = command.removeprefix("youtube control ").strip()
                print(f"YouTube control: {action}")
                fun = asyncio.to_thread(YouTubeVideoControl, action)
                funcs.append(fun)
                
            elif command.startswith("slide control "):  # Handle slide control commands
                action = command.removeprefix("slide control ").strip()
                print(f"Slide control: {action}")
                fun = asyncio.to_thread(SlideControl, action)
                funcs.append(fun)
                
            elif command.startswith("media control "):  # Handle media control commands
                action = command.removeprefix("media control ").strip()
                print(f"Media control: {action}")
                fun = asyncio.to_thread(MediaControl, action)
                funcs.append(fun)                  
            
            elif command.startswith("analyze screen"):  # Handle screen analysis
                print("Analyzing screen...")
                from vision_engine import VisionEngine
                fun = VisionEngine().analyze_screen()
                funcs.append(fun)
                
            elif command.startswith("analyze image "):  # Handle image path analysis
                path = command.removeprefix("analyze image ").strip()
                print(f"Analyzing image at {path}...")
                from vision_engine import VisionEngine
                fun = VisionEngine().analyze_image(path)
                funcs.append(fun)

            else:
                print(f"No function found for command: {command}")
        except Exception as cmd_error:
            print(f"Error processing command '{command}': {cmd_error}")
            
    if not funcs:
        print("No valid commands to execute")
        yield False
        return
        
    try:
        results = await asyncio.gather(*funcs, return_exceptions=True)
        
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"Command {i} failed with error: {result}")
                yield False
            else:
                print(f"Command {i} result: {result}")
                yield result
    except Exception as e:
        print(f"Error executing commands: {e}")
        yield False

async def Automation(commands: list[str]):
    """Execute automation commands with proper error handling"""
    if not commands:
        print("No commands provided to Automation function")
        return False
        
    print(f"Executing automation commands: {commands}")
    
    try:
        async for result in TranslateAndExecute(commands):
            if isinstance(result, str):
                print(f"Command result: {result}")
            elif isinstance(result, bool):
                if not result:
                    print(f"Command execution failed")
        return True
    except Exception as e:
        print(f"Error in Automation function: {e}")
        return False
