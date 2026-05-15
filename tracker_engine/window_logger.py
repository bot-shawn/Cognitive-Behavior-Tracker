import subprocess
import time
import sqlite3
from datetime import datetime
import os

# --- 1. Database Setup ---
# This ensures the database is saved in the 'database' folder we created
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database', 'focus_data.db')

def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            app_name TEXT,
            category TEXT
        )
    ''')
    conn.commit()
    return conn

# --- 2. The Mac Dictionary ---
def categorize_app(app_name):
    # Categorizes the app so the logic knows if it is Deep Work or a Distraction
    work_apps = ["Code", "Code - Insiders", "Terminal", "Google Chrome", "Safari", "Preview", "Pages", "Word"]
    social_apps = ["Discord", "Messages", "Mail", "Slack", "Spotify"]
    
    if app_name in work_apps:
        return "Work"
    elif app_name in social_apps:
        return "Distraction"
    else:
        return "Neutral"

# --- 3. The Mac Window Tracker (AppleScript) ---
def get_active_mac_window():
    # Asks the Mac what app is in front without needing massive security permissions
    script = 'tell application "System Events" to get name of first application process whose frontmost is true'
    try:
        result = subprocess.check_output(['osascript', '-e', script])
        return result.decode('utf-8').strip()
    except Exception:
        return "Unknown"

# --- 4. The Main Loop ---
def start_tracking():
    print("🚀 Starting Study Session Tracker...")
    print("Press Ctrl+C in this terminal to stop.\n")
    
    conn = setup_database()
    cursor = conn.cursor()
    
    try:
        while True:
            current_app = get_active_mac_window()
            category = categorize_app(current_app)
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Print to the terminal so we can see it working
            print(f"[{current_time}] Active App: {current_app} ({category})")
            
            # Save it to the SQLite database
            cursor.execute("INSERT INTO app_logs (timestamp, app_name, category) VALUES (?, ?, ?)", 
                           (current_time, current_app, category))
            conn.commit()
            
            time.sleep(5) # Wait 5 seconds before checking again
            
    except KeyboardInterrupt:
        print("\nTracker stopped cleanly.")
        conn.close()

if __name__ == "__main__":
    start_tracking()