import customtkinter as ctk
import subprocess
import os
import sys

# --- 1. App Styling ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class FocusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # --- 2. Window Setup ---
        self.title("Study Session Assistant")
        self.geometry("400x300")
        self.resizable(False, False) 
        
        self.is_tracking = False
        self.tracker_process = None  # This will hold our background tracker

        # --- 3. UI Elements ---
        self.title_label = ctk.CTkLabel(self, text="Cognitive Tracker", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=(30, 10))

        self.status_label = ctk.CTkLabel(self, text="Status: Ready to Focus", text_color="gray", font=("Arial", 14))
        self.status_label.pack(pady=10)

        self.toggle_btn = ctk.CTkButton(
            self, 
            text="Start Session", 
            command=self.toggle_session, 
            fg_color="#2FA572", 
            hover_color="#1E7A52",
            height=40,
            font=("Arial", 16, "bold")
        )
        self.toggle_btn.pack(pady=30)

    # --- 4. The Brain Bridge (Start/Stop Logic) ---
    def toggle_session(self):
        # Dynamically find the tracker script no matter whose computer this is on
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        script_path = os.path.join(base_dir, "tracker_engine", "window_logger.py")

        if not self.is_tracking:
            # START THE SESSION
            self.is_tracking = True
            self.status_label.configure(text="Status: 🟢 Tracking Active", text_color="#2FA572")
            self.toggle_btn.configure(text="Stop Session", fg_color="#D9534F", hover_color="#C9302C")
            
            # Launch the tracker secretly in the background using the active Virtual Environment
            try:
                self.tracker_process = subprocess.Popen([sys.executable, script_path])
                print("Background tracker launched successfully.")
            except Exception as e:
                print(f"Failed to start tracker: {e}")
                
        else:
            # STOP THE SESSION
            self.is_tracking = False
            self.status_label.configure(text="Status: Session Ended", text_color="gray")
            self.toggle_btn.configure(text="Start Session", fg_color="#2FA572", hover_color="#1E7A52")
            
            # Safely kill the background tracker
            if self.tracker_process:
                self.tracker_process.terminate()
                self.tracker_process = None
                print("Background tracker terminated.")

# Run the UI
if __name__ == "__main__":
    app = FocusApp()
    app.mainloop()