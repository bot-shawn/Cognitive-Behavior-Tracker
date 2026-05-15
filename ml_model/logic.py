import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from plyer import notification
import sqlite3
import time
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database', 'focus_data.db')
CSV_PATH = os.path.join(BASE_DIR, 'ml_model', 'synthetic_focus_data.csv')

def train_brain():
    print("📚 Training the Ultimate Cognitive Model...")
    df = pd.read_csv(CSV_PATH)
    
    # 1. Convert text to numbers
    df['category_num'] = df['category'].map({'Work': 0, 'Distraction': 1, 'Neutral': 0})
    
    # 2. Extract the Hour
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    
    # 3. Calculate "Time Spent" (Lag Feature)
    # This subtracts the previous row's time from the current row's time
    df['time_spent_seconds'] = df['timestamp'].diff().dt.total_seconds()
    # The very first row won't have a previous row to subtract, so we fill the blank with 0
    df['time_spent_seconds'] = df['time_spent_seconds'].fillna(0)
    
    # The AI now uses THREE clues to diagnose overload
    X = df[['category_num', 'hour', 'time_spent_seconds']]
    y = df['is_overloaded']
    
    model = DecisionTreeClassifier()
    model.fit(X, y)
    print("✅ AI Model trained on Category, Time of Day, and Duration!")
    return model

def send_nudge():
    print("🚨 Thrashing Detected! Sending OS Nudge...")
    notification.notify(
        title="Cognitive Overload Detected 🧠",
        message="Rapid context switching detected. Take a deep breath.",
        app_name="Study Assistant",
        timeout=5
    )

def run_live_analysis(model):
    print("🧠 Monitoring live brain activity...")
    last_nudge_time = 0
    
    # --- NEW: Memory for the true duration ---
    previous_app = None
    app_start_time = time.time()
    
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            # We only need the very newest row now
            df_live = pd.read_sql_query("SELECT * FROM app_logs ORDER BY id DESC LIMIT 1", conn)
            conn.close()
            
            if not df_live.empty:
                current_app = df_live['app_name'].iloc[0]
                category = df_live['category'].iloc[0]
                
                # If the user switched apps, hit reset on the stopwatch!
                if current_app != previous_app:
                    app_start_time = time.time()
                    previous_app = current_app
                    
                # Calculate true time spent continuously on THIS app
                time_spent_seconds = time.time() - app_start_time
                
                # Format for the AI Brain
                category_num = 0 if category == 'Work' else (1 if category == 'Distraction' else 0)
                hour = pd.to_datetime(df_live['timestamp'].iloc[0]).hour
                
                # Ask the AI (using a proper DataFrame to avoid warnings)
                df_predict = pd.DataFrame([[category_num, hour, time_spent_seconds]], 
                                          columns=['category_num', 'hour', 'time_spent_seconds'])
                prediction = model.predict(df_predict)[0]
                
                current_time = time.time()
                
                if prediction == 1 and (current_time - last_nudge_time > 60):
                    send_nudge()
                    last_nudge_time = current_time
                    
        except Exception:
            pass 
        
        time.sleep(5)

        
if __name__ == "__main__":
    trained_model = train_brain()
    run_live_analysis(trained_model)