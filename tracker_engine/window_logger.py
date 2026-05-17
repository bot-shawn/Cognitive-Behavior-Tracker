import subprocess
import time
import sqlite3
import os
from datetime import datetime

# --- 1. File Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database', 'focus_data.db')

# --- 2. Dictionaries ---
WORK_APPS = ["Code", "Google Chrome", "Safari", "Preview", "Pages", "Word"]
SOCIAL_APPS = ["Discord", "Messages", "Mail", "Slack", "Spotify"]

# --- 3. Database Auto-Builder ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Notice the brand new window_title column!
    c.execute('''
        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            app_name TEXT NOT NULL,
            window_title TEXT NOT NULL,
            category TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# --- 4. The macOS Bridge ---
def get_active_window_mac():
    """Uses AppleScript to grab the App Name AND the Tab/Document Title"""
    script = """
    global frontApp, windowTitle
    set windowTitle to ""
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
        try
            tell process frontApp
                set windowTitle to name of front window
            end tell
        end try
    end tell
    return frontApp & "::" & windowTitle
    """
    try:
        result = subprocess.check_output(['osascript', '-e', script]).decode('utf-8').strip()
        if "::" in result:
            app_name, window_title = result.split("::", 1)
            return app_name.strip(), window_title.strip()
        return result, ""
    except Exception:
        return "Unknown", "Unknown"

# --- 5. The Tracking Engine ---
def start_tracker():
    print("🚀 Starting Context-Aware Tracker...")
    print("Press Ctrl+C in this terminal to stop.")
    init_db() 
    
    # We bring the NLP dictionary into the tracker too!
    DISTRACTION_SITES = ["reddit", "twitter", "x", "tiktok", "instagram", "facebook", "youtube", "netflix"]

    try:
        while True:
            app_name, window_title = get_active_window_mac()
            
            # --- THE NEW SMART CATEGORY LOGIC ---
            if app_name in WORK_APPS: 
                category = "Work"
                # Double check if they are goofing off in a Work App
                if any(site in window_title.lower() for site in DISTRACTION_SITES):
                    category = "Distraction"
                    
            elif app_name in SOCIAL_APPS: 
                category = "Distraction"
            else: 
                category = "Neutral"
                
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO app_logs (timestamp, app_name, window_title, category) VALUES (?, ?, ?, ?)",
                      (timestamp, app_name, window_title, category))
            conn.commit()
            conn.close()
            
            print(f"[{timestamp}] {app_name} | {window_title[:40]} -> {category}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nTracker stopped cleanly.")
        
if __name__ == "__main__":
    start_tracker()