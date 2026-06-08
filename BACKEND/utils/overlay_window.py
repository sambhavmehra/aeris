import sys
import argparse
import tkinter as tk
import requests

class FloatingOverlay:
    def __init__(self, text, suggestion_id=None):
        self.root = tk.Tk()
        self.root.title("AERIS Screen Suggestion")
        
        # Enable borderless override
        self.root.overrideredirect(True)
        # Keep window on top of all others
        self.root.attributes("-topmost", True)
        # Semi-transparent alpha transparency
        self.root.attributes("-alpha", 0.94)
        
        self.suggestion_id = suggestion_id
        
        # Dimensions & screen positioning (top-right area)
        width = 400
        height = 200
        screen_width = self.root.winfo_screenwidth()
        x = screen_width - width - 30
        y = 60
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Outer container with border highlight
        self.bg_frame = tk.Frame(self.root, bg="#0A0E17", highlightbackground="#0EA5E9", highlightthickness=2)
        self.bg_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header (draggable area)
        self.header_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.header_frame.pack(fill=tk.X, padx=14, pady=(10, 4))
        
        # Make the header frame and title drag the entire window
        self.header_frame.bind("<Button-1>", self.start_drag)
        self.header_frame.bind("<B1-Motion>", self.drag)
        
        self.title_label = tk.Label(
            self.header_frame, 
            text="⚡ AERIS SUGGESTION", 
            fg="#38BDF8", 
            bg="#0A0E17", 
            font=("Segoe UI", 10, "bold")
        )
        self.title_label.pack(side=tk.LEFT)
        self.title_label.bind("<Button-1>", self.start_drag)
        self.title_label.bind("<B1-Motion>", self.drag)
        
        # Close Button
        self.close_btn = tk.Label(
            self.header_frame, 
            text="✕", 
            fg="#94A3B8", 
            bg="#0A0E17", 
            font=("Segoe UI", 12, "bold"), 
            cursor="hand2"
        )
        self.close_btn.pack(side=tk.RIGHT)
        self.close_btn.bind("<Button-1>", lambda e: self.close())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg="#EF4444"))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg="#94A3B8"))
        
        # Body content
        self.text_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.text_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        
        self.text_label = tk.Label(
            self.text_frame, 
            text=text, 
            fg="#F1F5F9", 
            bg="#0A0E17", 
            font=("Segoe UI", 10), 
            justify=tk.LEFT, 
            wraplength=370, 
            anchor="nw"
        )
        self.text_label.pack(fill=tk.BOTH, expand=True)
        self.text_label.bind("<Button-1>", self.start_drag)
        self.text_label.bind("<B1-Motion>", self.drag)
        
        # Footer Action Buttons
        self.footer_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.footer_frame.pack(fill=tk.X, padx=14, pady=(4, 12))
        
        # Dismiss button
        self.dsm_btn = tk.Button(
            self.footer_frame, 
            text="Dismiss", 
            bg="#1E293B", 
            fg="#94A3B8", 
            activebackground="#334155", 
            activeforeground="#F1F5F9", 
            font=("Segoe UI", 9, "bold"), 
            bd=0, 
            padx=16, 
            pady=6, 
            cursor="hand2", 
            command=self.close
        )
        self.dsm_btn.pack(side=tk.LEFT)
        
        # Implement button
        self.imp_btn = tk.Button(
            self.footer_frame, 
            text="Implement", 
            bg="#0EA5E9", 
            fg="#FFFFFF", 
            activebackground="#0284C7", 
            activeforeground="#FFFFFF", 
            font=("Segoe UI", 9, "bold"), 
            bd=0, 
            padx=18, 
            pady=6, 
            cursor="hand2", 
            command=self.implement
        )
        self.imp_btn.pack(side=tk.RIGHT)
        
        self.drag_data = {"x": 0, "y": 0}
        
    def start_drag(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y
        
    def drag(self, event):
        deltax = event.x - self.drag_data["x"]
        deltay = event.y - self.drag_data["y"]
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
        
    def implement(self):
        try:
            requests.post("http://127.0.0.1:8000/api/overlay/implement", json={"suggestion_id": self.suggestion_id}, timeout=2)
        except Exception:
            pass
        self.root.destroy()
        
    def close(self):
        try:
            requests.post("http://127.0.0.1:8000/api/overlay/dismiss", json={"suggestion_id": self.suggestion_id}, timeout=2)
        except Exception:
            pass
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AERIS Suggester Floating Overlay")
    parser.add_argument("--text", type=str, required=True, help="Text suggestion to display")
    parser.add_argument("--id", type=str, default="default", help="Unique suggestion ID")
    args = parser.parse_args()
    
    app = FloatingOverlay(args.text, args.id)
    app.run()
