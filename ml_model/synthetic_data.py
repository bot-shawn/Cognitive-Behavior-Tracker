import csv
import random
from datetime import datetime, timedelta
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "synthetic_focus_data.csv")

WORK_APPS = ["Code", "Google Chrome", "Safari", "Preview", "Pages", "Word"]
SOCIAL_APPS = ["Discord", "Messages", "Mail", "Slack", "Spotify"]

def generate_data():
    print("Generating 30 days of SMART synthetic data...")
    current_time = datetime.now() - timedelta(days=30)
    data = []
    
    for day in range(30):
        session_end = current_time + timedelta(hours=2)
        
        while current_time < session_end:
            # --- THE NEW COGNITIVE RULE ---
            # If they are studying between Midnight and 5 AM, they are highly likely to be burned out
            current_hour = current_time.hour
            if current_hour >= 0 and current_hour <= 5:
                overload_chance = 0.70  # 70% chance of thrashing late at night
            else:
                overload_chance = 0.20  # 20% chance during the day
                
            is_overloaded = random.random() < overload_chance
            
            chunk_end = current_time + timedelta(minutes=5)
            
            while current_time < chunk_end:
                if not is_overloaded:
                    app = random.choice(WORK_APPS)
                    category = "Work"
                    time_spent = timedelta(seconds=random.randint(60, 180)) 
                else:
                    app_pool = WORK_APPS + SOCIAL_APPS
                    app = random.choice(app_pool)
                    category = "Work" if app in WORK_APPS else "Distraction"
                    time_spent = timedelta(seconds=random.randint(5, 15))
                
                data.append([
                    current_time.strftime("%Y-%m-%d %H:%M:%S"), 
                    app, 
                    category,
                    1 if is_overloaded else 0 
                ])
                
                current_time += time_spent
                
        # Randomize the start of the next study session (between 12 to 24 hours later)
        current_time += timedelta(hours=random.randint(12, 24))

    with open(CSV_PATH, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["timestamp", "app_name", "category", "is_overloaded"])
        writer.writerows(data)
        
    print(f"Successfully generated {len(data)} time-aware interactions!")

if __name__ == "__main__":
    generate_data()