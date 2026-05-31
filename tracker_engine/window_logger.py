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
    
    # 1. Create the app_logs table if it does not exist
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
    
    # 2. Create the session_state table if it does not exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS session_state (
            state TEXT NOT NULL,
            last_updated TEXT NOT NULL,
            elapsed_seconds INTEGER DEFAULT 0
        )
    ''')
    
    # 3. Create the pending_interventions table if it does not exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS pending_interventions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            from_app TEXT NOT NULL,
            to_app TEXT NOT NULL,
            type TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')
    
    # 4. Create the ready_to_resume_notes table if it does not exist
    c.execute('''
        CREATE TABLE IF NOT EXISTS ready_to_resume_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            work_app TEXT NOT NULL,
            note_text TEXT NOT NULL,
            status TEXT DEFAULT 'active'
        )
    ''')
    
    # Run migrations if columns are missing in app_logs
    c.execute("PRAGMA table_info(app_logs)")
    columns = [col[1] for col in c.fetchall()]
    
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

def get_system_idle_seconds_mac():
    """Uses macOS ioreg command to get the system idle time in seconds"""
    try:
        output = subprocess.check_output("ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF; exit}'", shell=True).decode().strip()
        if output:
            return int(output) / 1_000_000_000
    except Exception:
        pass
    return 0.0

# --- 4. The macOS Active Window Bridge ---
def get_active_window_mac():
    """Uses AppleScript to grab the App Name AND the Tab/Document Title (with Chrome/Safari direct URL scripting to bypass Accessibility constraints)"""
    # 1. Get the frontmost application process name
    front_app_script = """
    tell application "System Events"
        set frontApp to name of first application process whose frontmost is true
    end tell
    return frontApp
    """
    try:
        app_name = subprocess.check_output(['osascript', '-e', front_app_script]).decode('utf-8').strip()
    except Exception:
        app_name = "Unknown"
        
    window_title = ""
    # 2. Direct scripting for Google Chrome (Title and URL)
    if "Google Chrome" in app_name:
        chrome_script = """
        tell application "Google Chrome"
            if exists window 1 then
                tell active tab of window 1
                    return title & "::" & URL
                end tell
            end if
        end tell
        """
        try:
            res = subprocess.check_output(['osascript', '-e', chrome_script]).decode('utf-8').strip()
            if "::" in res:
                title, url = res.split("::", 1)
                window_title = f"{title} ({url})"
            else:
                window_title = res
        except Exception:
            pass
            
    # 3. Direct scripting for Safari (Title and URL)
    elif "Safari" in app_name:
        safari_script = """
        tell application "Safari"
            if exists window 1 then
                tell current tab of window 1
                    return name & "::" & URL
                end tell
            end if
        end tell
        """
        try:
            res = subprocess.check_output(['osascript', '-e', safari_script]).decode('utf-8').strip()
            if "::" in res:
                title, url = res.split("::", 1)
                window_title = f"{title} ({url})"
            else:
                window_title = res
        except Exception:
            pass
            
    # 4. Fallback for other non-browser applications (System Events window title query)
    if not window_title and app_name != "Unknown":
        sys_script = f"""
        tell application "System Events"
            try
                tell process "{app_name}"
                    set winName to name of front window
                    return winName
                end tell
            on error
                return ""
            end try
        end tell
        """
        try:
            window_title = subprocess.check_output(['osascript', '-e', sys_script]).decode('utf-8').strip()
        except Exception:
            window_title = ""
            
    return app_name, window_title

def get_descriptive_name(app, title):
    if not title or title.strip() == "" or title.strip().lower() == "unknown":
        return app
    # Clean up title if it contains tabs
    short_title = title.split(" - ")[0].split(" | ")[0].strip()
    if len(short_title) > 30:
        short_title = short_title[:27] + "..."
    return f"{app} ({short_title})"

# --- 5. The Dynamic Tracking & ML Engine ---
def start_tracker():
    print("🚀 Starting Context-Aware Tracker & Attentional Residue Engine...")
    init_db()
    
    # Train the Decision Tree model at startup
    try:
        from ml_model.logic import train_brain
        model = train_brain()
        print("🧠 ML Model successfully loaded and trained.")
    except Exception as e:
        print(f"⚠️ Warning: Could not train ML model ({e}). Using heuristics only.")
        model = None
        
    # Initialize cognitive load to a clean, calm default start value (steady focus)
    current_load = 30
        
    app_history = []  # Keep track of recent applications for context-switching detection
    last_app = None
    app_switch_time = time.time()
    last_log_time = 0
    
    # Attentional Residue Tracking metrics
    continuous_work_seconds = 0
    prev_category = "Neutral"
    prev_app_name = "None"
    prev_window_title = "None"
    
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
                if current_time_sec - last_log_time >= 5.0:
                    current_load = max(10.0, current_load - 0.5)
                    last_log_time = current_time_sec
                    continuous_work_seconds = 0
                    prev_category = "Neutral"
                time.sleep(1)
                continue
                
            elif session_state == "Break":
                if current_time_sec - last_log_time >= 5.0:
                    current_load = max(0.0, current_load - 4.0)
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    continuous_work_seconds = 0
                    prev_category = "Neutral"
                    
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    c.execute("INSERT INTO app_logs (timestamp, app_name, window_title, category, cognitive_load, status, session_state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (timestamp, "Break", "Resting", "Neutral", int(current_load), "steady", "Break"))
                    conn.commit()
                    conn.close()
                    
                    last_log_time = current_time_sec
                time.sleep(1)
                continue
                
            # 3. Active Mode Tracking
            if current_time_sec - last_log_time >= 5.0:
                idle_secs = get_system_idle_seconds_mac()
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if idle_secs >= 60:
                    app_name = "Idle"
                    window_title = "Away From Keyboard"
                    category = "Idle"
                    # Decay load during idle
                    current_load = max(10.0, current_load - 2.0)
                    continuous_work_seconds = 0
                else:
                    app_name, window_title = get_active_window_mac()
                    
                    # A. Raw Category Classification
                    category = "Neutral"
                    if app_name in WORK_APPS:
                        category = "Work"
                        if any(site in window_title.lower() for site in DISTRACTION_SITES):
                            category = "Distraction"
                    elif app_name in SOCIAL_APPS:
                        category = "Distraction"
                    
                # B. Attentional Residue Switch Interceptor
                # Triggered when switching from Work -> Distraction
                if prev_category == "Work" and category == "Distraction":
                    conn = sqlite3.connect(DB_PATH)
                    c = conn.cursor()
                    
                    from_desc = get_descriptive_name(prev_app_name, prev_window_title)
                    to_desc = get_descriptive_name(app_name, window_title)
                    
                    # 2+ minutes of continuous deep work -> High Severity -> Ready to Resume popup (Low threshold for responsive testing!)
                    if continuous_work_seconds >= 120:
                        c.execute("INSERT INTO pending_interventions (timestamp, from_app, to_app, type, status) VALUES (?, ?, ?, ?, ?)",
                                  (timestamp, from_desc, to_desc, "ready_to_resume", "pending"))
                        print(f"🚨 [HIGH SEVERITY SWITCH] {from_desc} -> {to_desc} after {continuous_work_seconds}s. Ready-to-Resume queued!")
                        continuous_work_seconds = 0
                        
                    # 30 seconds to 2 minutes of work -> Medium Severity -> Soft Nudge inside GUI
                    elif continuous_work_seconds >= 30:
                        c.execute("INSERT INTO pending_interventions (timestamp, from_app, to_app, type, status) VALUES (?, ?, ?, ?, ?)",
                                  (timestamp, from_desc, to_desc, "soft_nudge", "pending"))
                        print(f"⚠️ [MEDIUM SEVERITY SWITCH] {from_desc} -> {to_desc} after {continuous_work_seconds}s. Soft Nudge queued.")
                        continuous_work_seconds = 0
                        
                    else:
                        # Less than 30 seconds -> Low Severity -> Log passively
                        print(f"ℹ️ [LOW SEVERITY SWITCH] Left work after short burst ({continuous_work_seconds}s). Passive log only.")
                        
                    conn.commit()
                    conn.close()
                    
                # C. App switches & Context-Switching Tracking
                if app_name != last_app:
                    app_switch_time = time.time()
                    last_app = app_name
                    app_history.append((app_name, time.time()))
                    if len(app_history) > 4:
                        app_history.pop(0)
                        
                time_spent_seconds = time.time() - app_switch_time
                
                # D. Heuristic Cognitive Load Modeling
                if category == "Distraction":
                    current_load = min(100.0, current_load + 6.0)
                    continuous_work_seconds = max(0, continuous_work_seconds - 5) # Distractions drain deep work duration
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
                    if current_load > 40:
                        current_load = max(40.0, current_load - 1.0)
                    elif current_load < 40:
                        current_load = min(40.0, current_load + 1.0)
                    continuous_work_seconds = max(0, continuous_work_seconds - 5)
                    
                # E. Context Switching Penalty
                if len(app_history) >= 3:
                    switches_in_20s = sum(1 for _, t in app_history if time.time() - t < 20)
                    if switches_in_20s >= 3:
                        current_load = min(100.0, current_load + 5.0)
                        print("⚠️ Context switching penalty applied!")
                        
                # F. NLP Checking & Machine Learning Overload Prediction
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
                    current_load = max(current_load, 83.0)
                    
                # G. Map Score to Status
                load_int = int(current_load)
                if load_int < 32:
                    status = "steady"
                elif load_int < 65:
                    status = "focused"
                elif load_int < 83:
                    status = "elevated"
                else:
                    status = "overload"
                    
                # H. Write to Database
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("INSERT INTO app_logs (timestamp, app_name, window_title, category, cognitive_load, status, session_state) VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (timestamp, app_name, window_title, category, load_int, status, "Active"))
                conn.commit()
                conn.close()
                
                # Keep trace of previous state for the next tick's switch detection
                prev_category = category
                prev_app_name = app_name
                prev_window_title = window_title
                
                print(f"[{timestamp}] {app_name} | {window_title[:30]} -> {category} | Load: {load_int}/100 ({status}) | WorkSec: {continuous_work_seconds}s")
                last_log_time = current_time_sec
                
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nTracker stopped cleanly.")

if __name__ == "__main__":
    start_tracker()