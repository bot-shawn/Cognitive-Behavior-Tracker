import csv
import random
from datetime import datetime, timedelta
import os

# --- 1. Setup ---
# Save the data in the ml_model folder so the brain can read it later
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "synthetic_focus_data.csv")

# The exact same dictionary from your tracker
WORK_APPS = ["Code", "Google Chrome", "Safari", "Preview", "Pages", "Word"]
SOCIAL_APPS = ["Discord", "Messages", "Mail", "Slack", "Spotify"]

def generate_data():
    print("Generating 30 days of synthetic study session data...")
    
    # Start date: 30 days ago
    current_time = datetime.now() - timedelta(days=30)
    
    data = []
    
    # We will simulate 30 "Study Sessions" (one per day)
    for day in range(30):
        # Each study session lasts about 2 hours
        session_end = current_time + timedelta(hours=2)
        
        while current_time < session_end:
            # 1. Determine the user's "State" for this chunk of time
            # 70% chance they are doing Deep Work, 30% chance they are in Cognitive Overload
            is_overloaded = random.random() < 0.30
            
            # 2. Simulate 5 minutes of clicking based on their state
            chunk_end = current_time + timedelta(minutes=5)
            
            while current_time < chunk_end:
                if not is_overloaded:
                    # DEEP WORK: They stay on the same work app for a long time
                    app = random.choice(WORK_APPS)
                    category = "Work"
                    # They don't switch apps for 1 to 3 minutes
                    time_spent = timedelta(seconds=random.randint(60, 180)) 
                else:
                    # COGNITIVE OVERLOAD (THRASHING): They rapidly switch apps
                    app_pool = WORK_APPS + SOCIAL_APPS
                    app = random.choice(app_pool)
                    category = "Work" if app in WORK_APPS else "Distraction"
                    # They switch apps every 5 to 15 seconds (High task-switching!)
                    time_spent = timedelta(seconds=random.randint(5, 15))
                
                # Record the log (matching our SQLite database structure)
                data.append([
                    current_time.strftime("%Y-%m-%d %H:%M:%S"), 
                    app, 
                    category,
                    1 if is_overloaded else 0 # 1 = Overloaded (Target variable for ML)
                ])
                
                current_time += time_spent
                
        # Jump to the next day
        current_time += timedelta(hours=22)

    # --- 3. Save to CSV ---
    with open(CSV_PATH, mode='w', newline='') as file:
        writer = csv.writer(file)
        # We add the "is_overloaded" label so the ML model knows the "answer"
        writer.writerow(["timestamp", "app_name", "category", "is_overloaded"])
        writer.writerows(data)
        
    print(f"✅ Successfully generated {len(data)} fake interactions!")
    print(f"Saved to: {CSV_PATH}")

if __name__ == "__main__":
    generate_data()