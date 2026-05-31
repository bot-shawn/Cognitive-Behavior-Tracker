import pandas as pd
from sklearn.tree import DecisionTreeClassifier
from plyer import notification
import sqlite3
import time
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database', 'focus_data.db')
CSV_PATH = os.path.join(BASE_DIR, 'ml_model', 'synthetic_focus_data.csv')

# --- THE COGNITIVE NLP DICTIONARIES ---
SCROLL_SITES = ["reddit", "twitter", "x", "tiktok", "instagram", "facebook", "youtube", "shorts"]
DEEP_WORK_SITES = ["docs.google", "github", "stackoverflow", "canvas", "ucsd", "localhost"]

def train_brain():
    print("📚 Training Cognitive NLP Model...")
    df = pd.read_csv(CSV_PATH)
    
    df['category_num'] = df['category'].map({'Work': 0, 'Distraction': 1, 'Neutral': 0, 'Idle': 0}).fillna(0)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['hour'] = df['timestamp'].dt.hour
    df['time_spent_seconds'] = df['timestamp'].diff().dt.total_seconds().fillna(0)
    
    # Simulate NLP features for the synthetic data so the AI learns to weigh them heavily
    df['is_scrolling'] = df['category'].apply(lambda x: 1 if x == 'Distraction' else 0)
    df['is_deep_work'] = df['category'].apply(lambda x: 1 if x == 'Work' else 0)
    
    # The AI now uses 5 distinct clues to make a decision
    X = df[['category_num', 'hour', 'time_spent_seconds', 'is_scrolling', 'is_deep_work']]
    y = df['is_overloaded']
    
    model = DecisionTreeClassifier()
    model.fit(X, y)
    print("AI Model trained with Deep Work & Scroll Detection!")
    return model

def send_nudge(reason="Rapid context switching detected."):
    print(f"Overload Detected: {reason}")
    notification.notify(
        title="Cognitive Overload Detected 🧠",
        message=f"{reason} Take a deep breath.",
        app_name="Study Assistant",
        timeout=5
    )

def run_live_analysis(model):
    print("🧠 Monitoring live brain activity...")
    last_nudge_time = 0
    previous_app = None
    app_start_time = time.time()
    
    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            df_live = pd.read_sql_query("SELECT * FROM app_logs ORDER BY id DESC LIMIT 1", conn)
            conn.close()
            
            if not df_live.empty:
                current_app = df_live['app_name'].iloc[0]
                # Safely grab the window title (fallback to empty string if missing)
                window_title = df_live.get('window_title', pd.Series([''])).iloc[0].lower()
                category = df_live['category'].iloc[0]
                
                if current_app != previous_app:
                    app_start_time = time.time()
                    previous_app = current_app
                    
                time_spent_seconds = time.time() - app_start_time
                
                # --- Natural Language Processing (NLP) Checks ---
                is_scrolling = 1 if any(site in window_title for site in SCROLL_SITES) else 0
                is_deep_work = 1 if any(site in window_title for site in DEEP_WORK_SITES) else 0
                
                category_num = 0 if category == 'Work' else (1 if category == 'Distraction' else 0)
                hour = pd.to_datetime(df_live['timestamp'].iloc[0]).hour
                
                # Format exactly to match the 5 clues the AI was trained on
                df_predict = pd.DataFrame([[category_num, hour, time_spent_seconds, is_scrolling, is_deep_work]], 
                                          columns=['category_num', 'hour', 'time_spent_seconds', 'is_scrolling', 'is_deep_work'])
                
                prediction = model.predict(df_predict)[0]
                current_time = time.time()
                
                if prediction == 1 and (current_time - last_nudge_time > 60):
                    # Dynamic intervention message based on exact behavior
                    reason = "Infinite scroll loop detected." if is_scrolling else "Rapid context switching detected."
                    send_nudge(reason)
                    last_nudge_time = current_time
                    
        except Exception:
            pass 
        
        time.sleep(5) 

if __name__ == "__main__":
    trained_model = train_brain()
    run_live_analysis(trained_model)