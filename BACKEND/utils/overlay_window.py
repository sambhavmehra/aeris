import sys
import argparse
import tkinter as tk
import requests
import ctypes

# Enable High-DPI awareness on Windows to prevent scaled size issues
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

class FloatingOverlay:
    def __init__(self, text, suggestion_id=None, api_url="http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")
        self.root = tk.Tk()
        self.root.title("AERIS Screen Suggestion")
        
        # Enable borderless override
        self.root.overrideredirect(True)
        # Keep window on top of all others
        self.root.attributes("-topmost", True)
        # Semi-transparent alpha transparency
        self.root.attributes("-alpha", 0.96)
        
        self.suggestion_id = suggestion_id
        
        # Expanded dimensions & screen positioning (top-right area)
        width = 460
        height = 320
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
        
        # Body content (Scrollable text widget for interactive chat)
        self.text_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.text_frame.pack(fill=tk.BOTH, expand=True, padx=14, pady=4)
        
        self.text_widget = tk.Text(
            self.text_frame, 
            bg="#0A0E17", 
            fg="#F1F5F9", 
            insertbackground="#0EA5E9",
            bd=0, 
            font=("Segoe UI", 10), 
            wrap=tk.WORD, 
            highlightthickness=0
        )
        self.text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.scrollbar = tk.Scrollbar(self.text_frame, command=self.text_widget.yview, bg="#0A0E17")
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text_widget.config(yscrollcommand=self.scrollbar.set)
        
        # Drag binds for text widget as well
        self.text_widget.bind("<Button-1>", self.start_drag)
        self.text_widget.bind("<B1-Motion>", self.drag)
        
        # Input Frame (for follow-up chat)
        self.input_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.input_frame.pack(fill=tk.X, padx=14, pady=(4, 6))
        
        self.entry = tk.Entry(
            self.input_frame, 
            bg="#1E293B", 
            fg="#F1F5F9", 
            insertbackground="#0EA5E9", 
            bd=1, 
            relief=tk.FLAT, 
            font=("Segoe UI", 10),
            highlightbackground="#334155",
            highlightthickness=1
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4, padx=(0, 6))
        self.entry.bind("<Return>", lambda e: self.send_query())
        
        self.send_btn = tk.Button(
            self.input_frame, 
            text="Send", 
            bg="#0EA5E9", 
            fg="#FFFFFF", 
            activebackground="#0284C7", 
            activeforeground="#FFFFFF", 
            font=("Segoe UI", 9, "bold"), 
            bd=0, 
            padx=14, 
            pady=4, 
            cursor="hand2", 
            command=self.send_query
        )
        self.send_btn.pack(side=tk.RIGHT)
        
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
        
        # Initialize text contents
        self.set_text(text)
        
    def start_drag(self, event):
        self.drag_data["x"] = event.x
        self.drag_data["y"] = event.y
        
    def drag(self, event):
        deltax = event.x - self.drag_data["x"]
        deltay = event.y - self.drag_data["y"]
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")
        
    def set_text(self, text_val):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert(tk.END, text_val)
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.see(tk.END)
        
    def append_text(self, text_val):
        self.text_widget.config(state=tk.NORMAL)
        self.text_widget.insert(tk.END, text_val)
        self.text_widget.config(state=tk.DISABLED)
        self.text_widget.see(tk.END)

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

    def send_query(self):
        query_text = self.entry.get().strip()
        if not query_text:
            return
            
        self.entry.delete(0, tk.END)
        self.append_text(f"\n\n[You]: {query_text}\n\n[AERIS]: Thinking...")
        self.root.update()
        
        try:
            resp = self.safe_post(
                "/api/overlay/query", 
                json_data={"text": query_text}, 
                timeout=20
            )
            if resp.ok:
                data = resp.json()
                new_text = data.get("response", "Sir, I couldn't process that request.")
                
                # Replace "Thinking..." with actual answer
                current_val = self.text_widget.get("1.0", tk.END).strip()
                if "Thinking..." in current_val:
                    updated = current_val.replace("Thinking...", new_text)
                    self.set_text(updated)
                else:
                    self.append_text(f"\n{new_text}")
            else:
                self.append_text("\n[Error: Request failed]")
        except Exception as e:
            self.append_text(f"\n[Error: {e}]")
        
    def implement(self):
        try:
            self.safe_post("/api/overlay/implement", json_data={"suggestion_id": self.suggestion_id}, timeout=2)
        except Exception:
            pass
        self.root.destroy()
        
    def close(self):
        try:
            self.safe_post("/api/overlay/dismiss", json_data={"suggestion_id": self.suggestion_id}, timeout=2)
        except Exception:
            pass
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AERIS Suggester Floating Overlay")
    parser.add_argument("--text", type=str, required=True, help="Text suggestion to display")
    parser.add_argument("--id", type=str, default="default", help="Unique suggestion ID")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="FastAPI Server Base URL")
    args = parser.parse_args()
    
    app = FloatingOverlay(args.text, args.id, api_url=args.url)
    app.run()
