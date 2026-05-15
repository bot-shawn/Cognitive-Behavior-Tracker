import customtkinter as ctk
import subprocess
import os
import sys
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime

# --- 1. App Styling ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class FocusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # --- 2. Window Setup ---
        self.title("Study Session Assistant")
        self.geometry("600x600") 
        self.resizable(False, False) 
        
        self.is_tracking = False
        self.tracker_process = None
        self.logic_process = None 
        self.session_start_time = None # NEW: Remember when we started

        # --- 3. UI Elements ---
        self.title_label = ctk.CTkLabel(self, text="Cognitive Tracker", font=("Arial", 24, "bold"))
        self.title_label.pack(pady=(20, 5))

        self.status_label = ctk.CTkLabel(self, text="Status: Ready to Focus", text_color="gray", font=("Arial", 14))
        self.status_label.pack(pady=5)

        self.toggle_btn = ctk.CTkButton(
            self, text="Start Session", command=self.toggle_session, 
            fg_color="#2FA572", hover_color="#1E7A52", height=40, font=("Arial", 16, "bold")
        )
        self.toggle_btn.pack(pady=15)

        # --- 4. The Matplotlib Graph Setup ---
        self.fig, self.ax = plt.subplots(figsize=(6, 3), dpi=100)
        self.fig.patch.set_facecolor('#242424') 
        self.ax.set_facecolor('#242424')
        self.ax.tick_params(colors='white')
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(pady=10, padx=20, fill="both", expand=True)

        self.update_graph()

    # --- 5. The Brain Bridge ---
    def toggle_session(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tracker_path = os.path.join(base_dir, "tracker_engine", "window_logger.py")
        logic_path = os.path.join(base_dir, "ml_model", "logic.py")

        if not self.is_tracking:
            # START THE SESSION
            self.is_tracking = True
            self.session_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.status_label.configure(text="Status: 🟢 Tracking Active", text_color="#2FA572")
            self.toggle_btn.configure(text="Stop Session", fg_color="#D9534F", hover_color="#C9302C")
            
            try:
                self.tracker_process = subprocess.Popen([sys.executable, tracker_path])
                self.logic_process = subprocess.Popen([sys.executable, logic_path])
            except Exception as e:
                print(f"Error launching engines: {e}")
                
        else:
            # STOP THE SESSION
            self.is_tracking = False
            self.status_label.configure(text="Status: Session Ended", text_color="gray")
            self.toggle_btn.configure(text="Start Session", fg_color="#2FA572", hover_color="#1E7A52")
            
            if self.tracker_process: self.tracker_process.terminate()
            if self.logic_process: self.logic_process.terminate()
            
            # NEW: Show the data breakdown!
            self.show_summary_popup()

    # --- 6. The Session Summary Popup (NEW) ---
    def show_summary_popup(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "database", "focus_data.db")
        
        try:
            # Connect to database and pull ONLY the data from this specific session
            conn = sqlite3.connect(db_path)
            query = f"SELECT category FROM app_logs WHERE timestamp >= '{self.session_start_time}'"
            df_session = pd.read_sql_query(query, conn)
            conn.close()
            
            if len(df_session) == 0:
                return # Don't show popup if they clicked start/stop instantly
                
            # Do the math
            total_clicks = len(df_session)
            work_clicks = len(df_session[df_session['category'] == 'Work'])
            focus_score = int((work_clicks / total_clicks) * 100)
            
            # Build the Popup Window
            popup = ctk.CTkToplevel(self)
            popup.title("Session Complete")
            popup.geometry("300x200")
            popup.resizable(False, False)
            
            # Make sure the popup stays on top of the main app
            popup.attributes("-topmost", True)
            
            title = ctk.CTkLabel(popup, text="Session Summary", font=("Arial", 20, "bold"))
            title.pack(pady=(20, 10))
            
            score_color = "#2FA572" if focus_score >= 70 else "#D9534F"
            score_label = ctk.CTkLabel(popup, text=f"Deep Work: {focus_score}%", font=("Arial", 18), text_color=score_color)
            score_label.pack(pady=5)
            
            data_label = ctk.CTkLabel(popup, text=f"Total Data Points Logged: {total_clicks}", font=("Arial", 12), text_color="gray")
            data_label.pack(pady=5)
            
            close_btn = ctk.CTkButton(popup, text="Close", command=popup.destroy, fg_color="#555555", hover_color="#333333")
            close_btn.pack(pady=15)
            
        except Exception as e:
            print(f"Failed to generate summary: {e}")

    # --- 7. The Live Graph Animator ---
    def update_graph(self):
        if self.is_tracking:
            try:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                db_path = os.path.join(base_dir, "database", "focus_data.db")
                conn = sqlite3.connect(db_path)
                
                df = pd.read_sql_query("SELECT timestamp, category FROM app_logs ORDER BY id DESC LIMIT 15", conn)
                conn.close()

                if len(df) > 1:
                    df = df.sort_values(by='timestamp')
                    df['score'] = df['category'].map({'Work': 100, 'Distraction': 0, 'Neutral': 50})
                    df['time_clean'] = df['timestamp'].str[-8:]

                    self.ax.clear()
                    self.ax.plot(df['time_clean'], df['score'], color='#2FA572', marker='o', linewidth=2)
                    
                    self.ax.set_ylim(-10, 110)
                    self.ax.set_yticks([0, 50, 100])
                    self.ax.set_yticklabels(["Distracted", "Neutral", "Deep Work"], color='white')
                    self.ax.tick_params(axis='x', rotation=30, labelsize=8)
                    self.ax.set_title("Live Focus Trajectory", color='white', fontweight='bold')
                    
                    self.fig.tight_layout()
                    self.canvas.draw()
            except Exception:
                pass 

        self.after(5000, self.update_graph)

if __name__ == "__main__":
    app = FocusApp()
    app.mainloop()