import sys
import argparse
import tkinter as tk
import requests
import ctypes

# Enable High-DPI awareness on Windows to prevent scaled coordinates bug
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

class SelectionCanvas:
    def __init__(self, api_url="http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")
        self.root = tk.Tk()
        self.root.title("AERIS Selection Tool")
        
        # Borderless, full-screen, topmost
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.35)  # Dim screen
        self.root.config(bg="#020617")
        
        # Geometry covering full screen
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.root.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        
        # Canvas for drawing selection box
        self.canvas = tk.Canvas(self.root, bg="#020617", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Instruction Label
        self.lbl = tk.Label(
            self.canvas, 
            text="✂️ DRAG MOUSE TO SELECT SCREEN REGION  |  [ESC] TO CANCEL", 
            fg="#38BDF8", 
            bg="#020617", 
            font=("Segoe UI", 12, "bold")
        )
        self.lbl.place(x=self.screen_width//2, y=50, anchor="center")
        
        # State variables
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        
        # Bindings
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        
    def on_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        # Create an initial rectangle
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, 
            outline="#0EA5E9", width=2, dash=(4, 4)
        )
        
    def on_drag(self, event):
        cur_x = event.x
        cur_y = event.y
        # Update rectangle coordinates
        self.canvas.coords(self.rect_id, self.start_x, self.start_y, cur_x, cur_y)
        
    def safe_post(self, path, json_data, timeout=2):
        url = f"{self.api_url}{path}"
        try:
            return requests.post(url, json=json_data, timeout=timeout)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if "127.0.0.1" in url:
                alt_url = url.replace("127.0.0.1", "[::1]")
                try:
                    return requests.post(alt_url, json=json_data, timeout=timeout)
                except Exception:
                    pass
            elif "[::1]" in url:
                alt_url = url.replace("[::1]", "127.0.0.1")
                try:
                    return requests.post(alt_url, json=json_data, timeout=timeout)
                except Exception:
                    pass
            raise e

    def on_release(self, event):
        end_x = event.x
        end_y = event.y
        
        # Form normal bounding box coordinates
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
        
        self.root.destroy()
        
        # Verify min drag size to avoid click register crashes
        if abs(x2 - x1) > 10 and abs(y2 - y1) > 10:
            try:
                self.safe_post(
                    "/api/screen/crop-box", 
                    json_data={"x1": x1, "y1": y1, "x2": x2, "y2": y2}, 
                    timeout=2
                )
            except Exception as e:
                print(f"Failed to post crop coordinates to {self.api_url}: {e}")
                
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AERIS Selection Tool")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="FastAPI Server Base URL")
    args = parser.parse_args()
    
    app = SelectionCanvas(api_url=args.url)
    app.run()
