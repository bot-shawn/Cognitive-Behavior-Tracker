import subprocess
import time
import sqlite3
import os
import sys
from datetime import datetime
import pandas as pd

# --- 1. File Paths & Environment setup ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database', 'focus_data.db')

if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

# --- 2. Dictionaries & Config ---
WORK_APPS = ["Code", "Google Chrome", "Safari", "Preview", "Pages", "Word", "Terminal", "iTerm", "Xcode"]
SOCIAL_APPS = ["Discord", "Messages", "Mail", "Slack", "Spotify", "WhatsApp", "Zoom", "Teams"]
DISTRACTION_SITES = ["reddit", "twitter", "x", "tiktok", "instagram", "facebook", "youtube", "netflix", "shorts", "twitch"]
DEEP_WORK_SITES = ["docs.google", "github", "stackoverflow", "canvas", "ucsd", "localhost", "deepmind", "openai"]

# --- 3. Database Auto-Builder & Migration ---
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Create the app_logs table if it does not exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS app_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            app_name TEXT NOT NULL,
            window_title TEXT NOT NULL,
            category TEXT NOT NULL,
            cognitive_load INTEGER DEFAULT 30,
            status TEXT DEFAULT 'steady',
            session_state TEXT DEFAULT 'Paused'
        )
    ''')
    
    # Create the session_state table if it does not exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS session_state (
            state TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            elapsed_seconds INTEGER DEFAULT 0
        )
    ''')
    
    # Run migrations if columns are missing
    c.execute("PRAGMA table_info(app_logs)")
    columns = [col[1] for col in c.fetchall()]
    
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    if "cognitive_load" not in columns:
        c.execute("ALTER TABLE app_logs ADD COLUMN cognitive_load INTEGER DEFAULT 30")
    if "status" not in columns:
        c.execute("ALTER TABLE app_logs ADD COLUMN status TEXT DEFAULT 'steady'")
    if "session_state" not in columns:
        c.execute("ALTER TABLE app_logs ADD COLUMN session_state TEXT DEFAULT 'Paused'")
        
    # Ensure there is exactly one row in session_state
    c.execute("SELECT COUNT(*) FROM session_state")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO session_state (state, last_updated, elapsed_seconds) VALUES (?, ?, ?)",
                  ("Paused", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0))
                  
    conn.commit()
    conn.close()

# --- 4. The macOS Active Window Bridge ---
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

# --- 5. The Dynamic Tracking & ML Engine ---
def start_tracker():
    print("🚀 Starting Context-Aware Tracker & ML Engine...")
    init_db()
    
    # Train the Decision Tree model at startup
    try:
        from ml_model.logic import train_brain
        model = train_brain()
        print("🧠 ML Model successfully loaded and trained.")
    except Exception as e:
        print(f"⚠️ Warning: Could not train ML model ({e}). Using heuristics only.")
        model = None
        
    # Fetch initial cognitive load from last DB record, or default to 30
    current_load = 30
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT cognitive_load FROM app_logs ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        if row:
            current_load = int(row[0])
        conn.close()
    except Exception:
        pass
        
    app_history = []  # Keep track of recent applications for context-switching detection
    last_app = None
    app_switch_time = time.time()
    last_log_time = 0
    
    # Track continuous deep work duration in seconds
    continuous_work_seconds = 0
    
    try:
        while True:
            # 1. Read Current Session State from DB (controlled by GUI)
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT state, elapsed_seconds FROM session_state LIMIT 1")
                state_row = c.fetchone()
                conn.close()
            except Exception as e:
                print(f"Error querying session state: {e}")
                state_row = None
                
            session_state = "Paused"
            elapsed_seconds = 0
            if state_row:
                session_state, elapsed_seconds = state_row
                
            current_time_sec = time.time()
            
            # 2. Check if we should log based on state
            if session_state == "Paused":
                # Paused: Decay load very slowly, do not add normal window logs
                if current_time_sec - last_log_time >= 5.0:
                    current_load = max(10.0, current_load - 0.5)
                    last_log_time = current_time_sec
                    continuous_work_seconds = 0
                time.sleep(1)
                continue
                
            elif session_state == "Break":
                # Break Mode: Rapid load recovery!
                if current_time_sec - last_log_time >= 5.0:
                    current_load = max(0.0, current_load - 4.0)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    continuous_work_seconds = 0
                    
                    # Log break entry
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("INSERT INTO app_logs (timestamp, app_name, window_title, category, cognitive_load, status, session_state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (timestamp, "Break", "Resting", "Neutral", int(current_load), "steady", "Break"))
                    conn.commit()
                    conn.close()
                    
                    print(f"[{timestamp}] [BREAK MODE] Recovering... Load: {int(current_load)} | status: steady")
                    last_log_time = current_time_sec
                time.sleep(1)
                continue
                
            # 3. Active Mode Tracking
            if current_time_sec - last_log_time >= 5.0:
                app_name, window_title = get_active_window_mac()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # A. Raw Category Classification
                category = "Neutral"
                if app_name in WORK_APPS:
                    category = "Work"
                    # Check if visiting a distraction website inside a work browser
                    if any(site in window_title.lower() for site in DISTRACTION_SITES):
                        category = "Distraction"
                elif app_name in SOCIAL_APPS:
                    category = "Distraction"
                    
                # B. Context-Switching Tracking
                if app_name != last_app:
                    app_switch_time = time.time()
                    last_app = app_name
                    # Save history: tuple of (app_name, timestamp)
                    app_history.append((app_name, time.time()))
                    if len(app_history) > 4:
                        app_history.pop(0)
                        
                time_spent_seconds = time.time() - app_switch_time
                
                # C. Heuristic Cognitive Load Modeling
                if category == "Distraction":
                    # Distraction spikes cognitive load and fragments focus
                    current_load = min(100.0, current_load + 6.0)
                    continuous_work_seconds = 0
                elif category == "Work":
                    continuous_work_seconds += 5
                    # Under 20 mins: Keep in the focus zone (45-55)
                    if continuous_work_seconds < 1200:
                        if current_load < 40:
                            current_load += 2.0
                        elif current_load > 60:
                            current_load -= 2.0
                    else:
                        # Over 20 mins: Fatigue starts accumulating
                        current_load = min(100.0, current_load + 1.2)
                else: # Neutral
                    # Slow decay towards neutral baseline (40)
                    if current_load > 40:
                        current_load = max(40.0, current_load - 1.0)
                    elif current_load < 40:
                        current_load = min(40.0, current_load + 1.0)
                    continuous_work_seconds = max(0, continuous_work_seconds - 5)
                    
                # D. Context Switching Penalty
                # If we have switched 3+ times in the last 20 seconds, apply penalty
                if len(app_history) >= 3:
                    switches_in_20s = sum(1 for _, t in app_history if time.time() - t < 20)
                    if switches_in_20s >= 3:
                        current_load = min(100.0, current_load + 5.0)
                        print("⚠️ Context switching penalty applied!")
                        
                # E. NLP Checking & Machine Learning Overload Prediction
                is_scrolling = 1 if any(site in window_title.lower() for site in DISTRACTION_SITES) else 0
                is_deep_work = 1 if any(site in window_title.lower() for site in DEEP_WORK_SITES) else 0
                
                category_num = 1 if category == 'Distraction' else 0
                hour = datetime.now().hour
                
                ml_prediction = 0
                if model is not None:
                    try:
                        df_predict = pd.DataFrame([[category_num, hour, time_spent_seconds, is_scrolling, is_deep_work]], 
                                                  columns=['category_num', 'hour', 'time_spent_seconds', 'is_scrolling', 'is_deep_work'])
                        ml_prediction = model.predict(df_predict)[0]
                    except Exception:
                        pass
                        
                # If ML predicts overload, ensure load is elevated or overload
                if ml_prediction == 1:
                    current_load = max(current_load, 83.0)  # Immediately push into overload range
                    
                # F. Map Score to Status
                load_int = int(current_load)
                if load_int < 32:
                    status = "steady"
                elif load_int < 65:
                    status = "focused"
                elif load_int < 83:
                    status = "elevated"
                else:
                    status = "overload"
                    
                # G. Write to Database
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("INSERT INTO app_logs (timestamp, app_name, window_title, category, cognitive_load, status, session_state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (timestamp, app_name, window_title, category, load_int, status, "Active"))
                conn.commit()
                conn.close()
                
                print(f"[{timestamp}] {app_name} | {window_title[:30]} -> {category} | Load: {load_int}/100 ({status})")
                last_log_time = current_time_sec
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nTracker stopped cleanly.")

if __name__ == "__main__":
    start_tracker()