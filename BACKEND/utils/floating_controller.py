import sys
import argparse
import tkinter as tk
import requests
import ctypes

# Enable High-DPI awareness on Windows to prevent scaled coordinates / size issues
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

class FloatingController:
    def __init__(self, api_url="http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")
        self.root = tk.Tk()
        self.root.title("AERIS Monitor Control")
        
        # Borderless, topmost, transparent alpha
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        
        # Dimensions & screen position (top-center area)
        width = 320
        height = 42
        screen_width = self.root.winfo_screenwidth()
        x = (screen_width - width) // 2
        y = 10
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Drag state
        self.drag_data = {"x": 0, "y": 0}
        
        # Outer container with modern neon highlight border
        self.bg_frame = tk.Frame(self.root, bg="#0A0E17", highlightbackground="#0EA5E9", highlightthickness=1.5)
        self.bg_frame.pack(fill=tk.BOTH, expand=True)
        
        # Draggable header label
        self.title_lbl = tk.Label(
            self.bg_frame, 
            text="🌌 AERIS", 
            fg="#0EA5E9", 
            bg="#0A0E17", 
            font=("Segoe UI", 8, "bold"),
            cursor="fleur"
        )
        self.title_lbl.pack(side=tk.LEFT, padx=(10, 6))
        self.title_lbl.bind("<Button-1>", self.start_drag)
        self.title_lbl.bind("<B1-Motion>", self.drag)
        
        # Separator line
        self.sep = tk.Label(self.bg_frame, text="|", fg="#334155", bg="#0A0E17", font=("Segoe UI", 9))
        self.sep.pack(side=tk.LEFT)
        
        # Button configurations
        buttons = [
            ("✂️ Select", self.action_select, "#0EA5E9"),
            ("🔄 Full", self.action_full, "#38BDF8"),
            ("🤖 Scan", self.action_scan, "#10B981"),
            ("⏹️ Stop", self.action_stop, "#EF4444")
        ]
        
        for text, command, color in buttons:
            btn = tk.Label(
                self.bg_frame, 
                text=text, 
                fg="#F1F5F9", 
                bg="#1E293B", 
                font=("Segoe UI", 8, "bold"),
                padx=8,
                pady=4,
                cursor="hand2"
            )
            btn.pack(side=tk.LEFT, padx=4, pady=4)
            btn.bind("<Button-1>", lambda e, cmd=command: cmd())
            btn.bind("<Enter>", lambda e, b=btn, col=color: b.config(bg=col, fg="#FFFFFF"))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#1E293B", fg="#F1F5F9"))
            
        # Drag bind for outer frame as well
        self.bg_frame.bind("<Button-1>", self.start_drag)
        self.bg_frame.bind("<B1-Motion>", self.drag)
        
    def start_drag(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y
        
    def drag(self, event):
        deltax = event.x - self.drag_data["x"]
        deltay = event.y - self.drag_data["y"]
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
        
    def safe_post(self, path, json_data=None, timeout=2):
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

    def action_select(self):
        try:
            self.safe_post("/api/screen/select", timeout=2)
        except Exception as e:
            print(f"Failed to trigger selection canvas at {self.api_url}: {e}")
            
    def action_full(self):
        try:
            self.safe_post("/api/screen/clear-crop", timeout=2)
        except Exception as e:
            print(f"Failed to clear crop box at {self.api_url}: {e}")
            
    def action_scan(self):
        try:
            self.safe_post("/api/chat", json_data={"message": "suggest"}, timeout=2)
        except Exception as e:
            print(f"Failed to trigger suggestion check at {self.api_url}: {e}")
            
    def action_stop(self):
        try:
            self.safe_post("/api/chat", json_data={"message": "stop monitoring"}, timeout=2)
        except Exception as e:
            print(f"Failed to stop monitoring at {self.api_url}: {e}")
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AERIS Floating Controller")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="FastAPI Server Base URL")
    args = parser.parse_args()
    
    app = FloatingController(api_url=args.url)
    app.run()
