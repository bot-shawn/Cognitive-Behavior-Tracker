# Cognitive-Behavior-Tracker

### quick notes (delete after project complete)
You would need a vitural environment to work on this because we have many packages that we need to use.
to create a virtual environment (Do this only the first time)
python3 -m venv venv   # (Mac)
python -m venv venv    # (Windows)

this is to activate it, you have to do it everytime you work on it
source venv/bin/activate   # (Mac)
venv\Scripts\activate      # (Windows)

run pip install -r requirements.txt
to install all the needed package to the virtual environment, only need to do once.

### Mac User Troubleshooting (Tkinter Error)
If you are using a Mac and installed Python via Homebrew, you might get a `ModuleNotFoundError: No module named '_tkinter'` error when running the UI. 

This is because Homebrew does not install the Python graphics engine by default. To fix this, leave your virtual environment running and execute:
`brew install python-tk@3.13`


## Overview
In an environment of constant digital distractions, individuals struggle to allocate their attention effectively. While existing tools provide descriptive weekly analytics, they fail to explain *why* attention breaks down in the moment.

This project is a 100% local behavioral analytics desktop application. This platform acts as an active **Study Session Assistant** to diagnose and prevent mental fatigue in real-time.

### Core Features
* **Session-Based Tracking:** Users initiate focused study blocks (e.g., 2 hours). The app tracks attention patterns and categorizes application usage only during these active sessions.
* **Cognitive State Detection:** Uses a local machine learning engine (trained on synthetic baseline data) to identify when a user shifts from "Deep Work" into "Cognitive Overload" (thrashing between contexts).
* **Personalized Interventions:** Triggers native OS nudges (e.g., a 2-minute reset prompt) when high task-switching is detected to prevent burnout.

---

## Tech Stack
This project uses an "All-Python" multithreaded architecture.

* **Frontend UI:** `customtkinter` (Modern, dark-mode desktop UI) & `matplotlib` (Live focus graphs)
* **Data Collection:** `sqlite3` (Local database) & OS window trackers (`pygetwindow` for Windows / `AppKit` for macOS)
* **Cognitive Engine / ML:** `pandas` & `scikit-learn` (with synthetic bootstrapping for Day-1 intelligence)
* **Interventions:** `plyer` (Native OS desktop notifications)

---

## Repository Structure
Our codebase is divided into three main workspaces running concurrently during an active session:

```text
Cognitive-Behavior-Tracker/
│
├── tracker_engine/          # (Data Engineer's workspace)
│   └── window_logger.py     # Captures active window & writes to SQLite
│
├── ml_model/                # (Cognitive Modeler's workspace)
│   ├── synthetic_data.py    # Generates 30 days of fake data to train the ML
│   └── logic.py             # Reads SQLite, calculates Scattered Score
│
├── ui_dashboard/            # (HCI/Frontend Dev's workspace)
│   └── app.py               # Renders Tkinter UI, Start/Stop controls, triggers nudges
│
├── database/                # (Storage)
│   └── schema.sql           # SQLite table structures
│
├── README.md                
├── .gitignore               # Ignores local databases and virtual environments
└── requirements.txt         # Project dependencies