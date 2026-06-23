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

class SelectionPopup(tk.Toplevel):
    def __init__(self, parent, api_url, x1, y1, x2, y2, safe_post_fn):
        super().__init__(parent)
        self.parent = parent
        self.api_url = api_url
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.safe_post = safe_post_fn
        
        # Borderless, topmost, transparent background wrapper
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.96)
        self.lift()
        self.focus_force()
        
        # Background `#0EA5E9` for 1px border
        self.config(bg="#0EA5E9")
        
        # Geometry
        width = 400
        height = 160
        
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Center of selected rectangle
        center_x = (self.x1 + self.x2) // 2
        center_y = (self.y1 + self.y2) // 2
        
        # Position centered over selection, clamp to screen boundaries
        pos_x = max(10, min(center_x - (width // 2), screen_width - width - 10))
        pos_y = max(10, min(center_y - (height // 2), screen_height - height - 10))
        
        self.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        
        # Inner container for the `#0A0E17` background
        container = tk.Frame(self, bg="#0A0E17")
        container.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        
        # Header frame
        header_frame = tk.Frame(container, bg="#0A0E17")
        header_frame.pack(fill=tk.X, padx=12, pady=(12, 8))
        
        lbl = tk.Label(
            header_frame,
            text="🔍 Is area ke baare me kya jaanna hai?",
            fg="#38BDF8",
            bg="#0A0E17",
            font=("Segoe UI", 10, "bold")
        )
        lbl.pack(side=tk.LEFT)
        
        close_btn = tk.Label(
            header_frame,
            text="✕",
            fg="#94A3B8",
            bg="#0A0E17",
            font=("Segoe UI", 11, "bold"),
            cursor="hand2"
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.on_close())
        
        # Input field
        self.entry = tk.Entry(
            container,
            bg="#1E293B",
            fg="#F1F5F9",
            insertbackground="#0EA5E9",
            relief=tk.FLAT,
            font=("Segoe UI", 10),
            highlightthickness=1,
            highlightbackground="#1E293B",
            highlightcolor="#0EA5E9"
        )
        self.entry.pack(fill=tk.X, padx=12, pady=8)
        self.entry.focus_set()
        
        # Buttons frame
        btn_frame = tk.Frame(container, bg="#0A0E17")
        btn_frame.pack(fill=tk.X, padx=12, pady=(8, 12))
        
        # Auto Analyze (Gray)
        self.analyze_btn = tk.Button(
            btn_frame,
            text="Auto Analyze",
            bg="#1E293B",
            fg="#94A3B8",
            activebackground="#334155",
            activeforeground="#F1F5F9",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=4,
            command=self.on_auto_analyze
        )
        self.analyze_btn.pack(side=tk.LEFT)
        
        # Ask Button (Cyan)
        self.ask_btn = tk.Button(
            btn_frame,
            text="Ask AERIS",
            bg="#0EA5E9",
            fg="#FFFFFF",
            activebackground="#0284C7",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief=tk.FLAT,
            bd=0,
            padx=15,
            pady=4,
            command=self.on_ask
        )
        self.ask_btn.pack(side=tk.RIGHT)
        
        # Bindings
        self.entry.bind("<Return>", lambda e: self.on_ask())
        self.bind("<Escape>", lambda e: self.on_close())
        
    def on_ask(self):
        query = self.entry.get().strip()
        if not query:
            return  # Don't send empty queries
        
        # Submit selection + query to query-region
        payload = {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2,
            "query": query
        }
        
        try:
            self.safe_post("/api/screen/query-region", payload)
        except Exception as e:
            print(f"Failed to post query region: {e}")
            
        self.on_close()
        
    def on_auto_analyze(self):
        payload = {
            "x1": self.x1,
            "y1": self.y1,
            "x2": self.x2,
            "y2": self.y2
        }
        try:
            self.safe_post("/api/screen/crop-box", payload)
        except Exception as e:
            print(f"Failed to post crop box: {e}")
            
        self.on_close()
        
    def on_close(self):
        self.parent.destroy()

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
        
        # Hide selection tool screen overlay
        self.root.withdraw()
        
        # Verify min drag size to avoid click register crashes
        if abs(x2 - x1) > 10 and abs(y2 - y1) > 10:
            # Check for pending query first by calling status endpoint
            pending_query = None
            try:
                url = f"{self.api_url}/api/screen/status"
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    status_data = resp.json()
                    pending_query = status_data.get("pending_query")
            except Exception as e:
                print(f"Failed to check pending query status: {e}")
                
            if pending_query:
                # Directly post to query-region with the pending query
                try:
                    payload = {
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "query": pending_query
                    }
                    self.safe_post("/api/screen/query-region", payload)
                except Exception as e:
                    print(f"Failed to post query region: {e}")
                self.root.destroy()
            else:
                try:
                    # Show popup input box
                    popup = SelectionPopup(self.root, self.api_url, x1, y1, x2, y2, self.safe_post)
                    # Make the popup transient to keep it linked
                    popup.transient(self.root)
                except Exception as e:
                    print(f"Failed to create popup: {e}")
                    self.root.destroy()
        else:
            self.root.destroy()
                
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AERIS Selection Tool")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="FastAPI Server Base URL")
    args = parser.parse_args()
    
    app = SelectionCanvas(api_url=args.url)
    app.run()
