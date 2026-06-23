import sys
import argparse
import tkinter as tk
import requests
import ctypes

# Enable High-DPI awareness on Windows to prevent scaling issues
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

class GuardianOverlay:
    def __init__(self, text, api_url="http://127.0.0.1:8000"):
        self.api_url = api_url.rstrip("/")
        self.root = tk.Tk()
        self.root.title("AERIS Guardian Mode Security Alert")
        
        # Borderless, topmost window
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.98)
        
        # Center the window on the screen
        width = 500
        height = 360
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        
        # Outer container with a red border indicating warning
        self.bg_frame = tk.Frame(self.root, bg="#0A0E17", highlightbackground="#EF4444", highlightthickness=3)
        self.bg_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header title
        self.header_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.header_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        
        self.title_label = tk.Label(
            self.header_frame, 
            text="🛡️ AERIS SECURITY GUARD", 
            fg="#EF4444", 
            bg="#0A0E17", 
            font=("Segoe UI", 12, "bold")
        )
        self.title_label.pack(side=tk.LEFT)
        
        # Close/Dismiss Label (represented as X but only closeable under owner verification)
        # However, to avoid deadlock, we let user dismiss, but the ActivityMonitor loop will re-trigger
        # if they continue to focus/open the restricted resource. 
        self.close_btn = tk.Label(
            self.header_frame, 
            text="✕", 
            fg="#64748B", 
            bg="#0A0E17", 
            font=("Segoe UI", 12, "bold"), 
            cursor="hand2"
        )
        self.close_btn.pack(side=tk.RIGHT)
        self.close_btn.bind("<Button-1>", lambda e: self.close())
        self.close_btn.bind("<Enter>", lambda e: self.close_btn.config(fg="#EF4444"))
        self.close_btn.bind("<Leave>", lambda e: self.close_btn.config(fg="#64748B"))
        
        # Message Section
        self.msg_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.msg_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        # Warning icon/subtitle
        self.warning_sub = tk.Label(
            self.msg_frame,
            text="ACCESS RESTRICTED",
            fg="#F87171",
            bg="#0A0E17",
            font=("Segoe UI", 10, "bold")
        )
        self.warning_sub.pack(anchor="w", pady=(0, 5))
        
        self.msg_text = tk.Label(
            self.msg_frame, 
            text=text, 
            fg="#E2E8F0", 
            bg="#0A0E17", 
            font=("Segoe UI", 10), 
            wraplength=450,
            justify=tk.LEFT
        )
        self.msg_text.pack(anchor="w", pady=(0, 15))
        
        # Instruction/Prompt for verification
        self.prompt_label = tk.Label(
            self.msg_frame,
            text="Enter deactivation PIN or speak clearance phrase to unlock:",
            fg="#94A3B8",
            bg="#0A0E17",
            font=("Segoe UI", 9)
        )
        self.prompt_label.pack(anchor="w", pady=(0, 5))
        
        # PIN entry box
        self.pin_frame = tk.Frame(self.msg_frame, bg="#0A0E17")
        self.pin_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.entry = tk.Entry(
            self.pin_frame, 
            show="•",
            bg="#1E293B", 
            fg="#F1F5F9", 
            insertbackground="#EF4444", 
            bd=1, 
            relief=tk.FLAT, 
            font=("Segoe UI", 12, "bold"),
            highlightbackground="#475569",
            highlightthickness=1,
            justify=tk.CENTER
        )
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6, padx=(0, 10))
        self.entry.bind("<Return>", lambda e: self.verify_pin())
        self.entry.focus_set()
        
        self.verify_btn = tk.Button(
            self.pin_frame, 
            text="Verify PIN", 
            bg="#EF4444", 
            fg="#FFFFFF", 
            activebackground="#DC2626", 
            activeforeground="#FFFFFF", 
            font=("Segoe UI", 10, "bold"), 
            bd=0, 
            padx=20, 
            pady=6, 
            cursor="hand2", 
            command=self.verify_pin
        )
        self.verify_btn.pack(side=tk.RIGHT)
        
        # Feedback message label
        self.feedback_label = tk.Label(
            self.msg_frame,
            text="",
            fg="#EF4444",
            bg="#0A0E17",
            font=("Segoe UI", 9, "bold")
        )
        self.feedback_label.pack(anchor="w")
        
        # Footer Action description
        self.footer_frame = tk.Frame(self.bg_frame, bg="#0A0E17")
        self.footer_frame.pack(fill=tk.X, padx=20, pady=(10, 20))
        
        self.info_label = tk.Label(
            self.footer_frame,
            text="Voice verification is listening. Say 'Aeris, unlock' or secret phrase.",
            fg="#64748B",
            bg="#0A0E17",
            font=("Segoe UI", 8, "italic")
        )
        self.info_label.pack(side=tk.LEFT)
        
        # Start backend status check polling loop
        self.root.after(1000, self.check_backend_status)
        
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

    def safe_get(self, path, timeout=1):
        url = f"{self.api_url}{path}"
        try:
            return requests.get(url, timeout=timeout)
        except Exception:
            if "127.0.0.1" in url:
                alt_url = url.replace("127.0.0.1", "[::1]")
                try:
                    return requests.get(alt_url, timeout=timeout)
                except Exception:
                    pass
            return None

    def verify_pin(self):
        pin = self.entry.get().strip()
        if not pin:
            return
            
        try:
            resp = self.safe_post(
                "/api/guardian/verify-pin",
                json_data={"pin": pin},
                timeout=5
            )
            if resp and resp.ok:
                data = resp.json()
                if data.get("success"):
                    self.feedback_label.config(text="Clearance Verified! Unlocking...", fg="#10B981")
                    self.root.update()
                    self.root.after(800, self.close_window)
                else:
                    self.feedback_label.config(text=data.get("message", "Incorrect PIN!"), fg="#EF4444")
                    self.entry.delete(0, tk.END)
            else:
                self.feedback_label.config(text="API Server Error", fg="#EF4444")
        except Exception as e:
            self.feedback_label.config(text=f"Connection Error: {e}", fg="#EF4444")
            
    def check_backend_status(self):
        """Poll backend to check if guardian mode was disabled or overlay dismissed externally."""
        try:
            resp = self.safe_get("/api/guardian/status", timeout=1)
            if resp and resp.ok:
                data = resp.json()
                # If guardian mode is disabled, or backend says overlay is no longer active
                if not data.get("enabled", False) or not data.get("overlay_active", False):
                    self.close_window()
                    return
        except Exception:
            pass
        self.root.after(1000, self.check_backend_status)
        
    def close(self):
        """Inform backend that overlay is closed by the user."""
        try:
            self.safe_post("/api/guardian/dismiss-overlay", timeout=1)
        except Exception:
            pass
        self.close_window()
        
    def close_window(self):
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AERIS Guardian Mode Overlay")
    parser.add_argument("--text", type=str, required=True, help="Warning text to display")
    parser.add_argument("--url", type=str, default="http://127.0.0.1:8000", help="FastAPI Server Base URL")
    args = parser.parse_args()
    
    app = GuardianOverlay(args.text, api_url=args.url)
    app.run()
