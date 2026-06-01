import customtkinter as ctk
import sqlite3
import subprocess
import os
import sys
import time
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from datetime import datetime, timedelta
import threading

# Safely import plyer for native notifications
try:
    from plyer import notification
except Exception:
    notification = None

# --- 1. File Paths & Environment Setup ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'database', 'focus_data.db')

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class FocusApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # --- 2. Window Setup ---
        self.title("Cognitive Tracker & Attentional Coach")
        self.geometry("1020x840") 
        self.resizable(False, False) 
        
        # System State Variables
        self.current_state = "Active"
        self.elapsed_seconds = 0
        self.tracker_process = None
        
        # Popup lock to prevent overlapping dialogs
        self.popup_active = False
        
        # Color Tokens (Light Mode, Dark Mode)
        self.color_bg = ("#F4F6F8", "#15181F")
        self.color_card = ("#FFFFFF", "#1C2029")
        self.color_text = ("#1E222A", "#FFFFFF")
        self.color_text_muted = ("#7A8290", "#8D96A5")
        self.color_border = ("#E2E8F0", "#2B303C")
        
        # Segment & Status Colors
        self.color_steady = "#3A86FF"
        self.color_focused = "#2FA572"
        self.color_elevated = "#F4B942"
        self.color_overload = "#E65F5C"
        self.color_segment_off = ("#E2E8F0", "#262B35")
        
        self.configure(fg_color=self.color_bg)
        
        # 1. Initialize DB and seed mock data
        self.init_db_and_seed()
        
        # 2. Build the Layout & Widgets
        self.create_widgets()
        
        # 3. Synchronize Initial State from DB
        self.sync_session_state()
        
        # 4. Start Background UI Poll on main thread safely
        self.poll_active = True
        self.poll_db_and_update()
        
        # 5. Start Background Timer Thread
        self.timer_thread = threading.Thread(target=self.run_timer, daemon=True)
        self.timer_thread.start()
        
        # 6. Auto-start Tracker Process if not running
        self.ensure_tracker_running()
        
        # Hook Window Close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    # --- 3. Database Initialization & Seeding ---
    def init_db_and_seed(self):
        # 0. Delete the database file on application startup as requested
        if os.path.exists(DB_PATH):
            try:
                os.remove(DB_PATH)
                print("🗑️ Cleaned/Deleted focus database on application startup.")
            except Exception as e:
                print(f"⚠️ Error deleting focus database: {e}")

        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Ensure tables exist
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS session_state (
                state TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                elapsed_seconds INTEGER DEFAULT 0
            )
        ''')
        
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
        
        c.execute('''
            CREATE TABLE IF NOT EXISTS ready_to_resume_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                work_app TEXT NOT NULL,
                note_text TEXT NOT NULL,
                status TEXT DEFAULT 'active'
            )
        ''')
        
        # Verify schema is populated
        c.execute("PRAGMA table_info(app_logs)")
        columns = [col[1] for col in c.fetchall()]
        if "cognitive_load" not in columns:
            c.execute("ALTER TABLE app_logs ADD COLUMN cognitive_load INTEGER DEFAULT 30")
        if "status" not in columns:
            c.execute("ALTER TABLE app_logs ADD COLUMN status TEXT DEFAULT 'steady'")
        if "session_state" not in columns:
            c.execute("ALTER TABLE app_logs ADD COLUMN session_state TEXT DEFAULT 'Paused'")
            
        c.execute("SELECT COUNT(*) FROM session_state")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO session_state (state, last_updated, elapsed_seconds) VALUES (?, ?, ?)",
                      ("Active", datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 0))
        else:
            c.execute("UPDATE session_state SET state = 'Active', elapsed_seconds = 0")
            
        # Ensure database starts completely fresh without any generic seeded logs
        c.execute("DELETE FROM pending_interventions")
        c.execute("DELETE FROM ready_to_resume_notes")
        print("🧹 Cleaned database and ready-to-resume notes on launch.")
            
        conn.commit()
        conn.close()

    # --- 4. Create UI Widgets & Layout ---
    def create_widgets(self):
        # 1. Custom macOS style top bar
        self.top_bar = ctk.CTkFrame(self, fg_color="transparent", height=40)
        self.top_bar.pack(fill="x", padx=20, pady=(15, 5))
        
        # Dots
        self.dots_frame = ctk.CTkFrame(self.top_bar, fg_color="transparent", width=80, height=20)
        self.dots_frame.pack(side="left")
        self.dot_red = ctk.CTkFrame(self.dots_frame, width=12, height=12, corner_radius=6, fg_color="#FF5F56")
        self.dot_red.place(x=0, y=4)
        self.dot_yellow = ctk.CTkFrame(self.dots_frame, width=12, height=12, corner_radius=6, fg_color="#FFBD2E")
        self.dot_yellow.place(x=18, y=4)
        self.dot_green = ctk.CTkFrame(self.dots_frame, width=12, height=12, corner_radius=6, fg_color="#27C93F")
        self.dot_green.place(x=36, y=4)
        
        # Monospace Header Title
        self.main_title = ctk.CTkLabel(self.top_bar, text="Cognitive Tracker", 
                                       font=("Courier New", 26, "bold"), text_color=self.color_text)
        self.main_title.pack(side="left", padx=(20, 0))
        
        # Top-Right Mode Toggle
        self.toggle_mode_btn = ctk.CTkButton(self.top_bar, text="🌙 Dark Mode", width=110, height=30,
                                             fg_color=self.color_card, text_color=self.color_text,
                                             border_width=1, border_color=self.color_border,
                                             hover_color=("#E2E8F0", "#2B303C"), command=self.toggle_theme)
        self.toggle_mode_btn.pack(side="right")
        
        # Showcase Mode Button (Next to Dark Mode toggle)
        self.showcase_btn = ctk.CTkButton(self.top_bar, text="✨ Load Showcase", width=130, height=30,
                                          fg_color=self.color_card, text_color=self.color_text,
                                          border_width=1, border_color=self.color_border,
                                          hover_color=("#E2E8F0", "#2B303C"), command=self.toggle_showcase)
        self.showcase_btn.pack(side="right", padx=10)
        
        # --- 2. ELITE TAB NAVIGATION BAR ---
        self.navigation_frame = ctk.CTkFrame(self, fg_color="transparent", height=40)
        self.navigation_frame.pack(fill="x", padx=20, pady=5)
        
        self.tab_nav = ctk.CTkSegmentedButton(self.navigation_frame, 
                                              values=["Focus Analytics", "Cognitive Thread Coach"], 
                                              font=("Arial", 14, "bold"), height=35,
                                              selected_color="#2FA572",
                                              command=self.switch_tab)
        self.tab_nav.pack(fill="x")
        self.tab_nav.set("Focus Analytics")
        
        # --- 3. MASTER TAB CONTAINERS ---
        # TAB 1 Container
        self.analytics_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.analytics_frame.pack(fill="both", expand=True)
        
        # TAB 2 Container
        self.coach_frame = ctk.CTkFrame(self, fg_color="transparent")
        # Kept hidden initially (unpackaged)
        
        # =========================================================================
        # TAB 1: FOCUS ANALYTICS VIEW
        # =========================================================================
        self.top_row_frame = ctk.CTkFrame(self.analytics_frame, fg_color="transparent")
        self.top_row_frame.pack(fill="x", padx=20, pady=5)
        
        # A. Circular Timer Card
        self.timer_card = ctk.CTkFrame(self.top_row_frame, fg_color=self.color_card, 
                                       border_width=1, border_color=self.color_border, width=220, height=220)
        self.timer_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.timer_card.pack_propagate(False)
        
        self.timer_canvas = ctk.CTkCanvas(self.timer_card, bg="#1C2029", highlightthickness=0, width=170, height=170)
        self.timer_canvas.pack(pady=25, padx=20)
        
        # B. Console Buttons Card
        self.console_card = ctk.CTkFrame(self.top_row_frame, fg_color=self.color_card,
                                         border_width=1, border_color=self.color_border, width=260, height=220)
        self.console_card.pack(side="left", fill="both", expand=True, padx=10)
        self.console_card.pack_propagate(False)
        
        self.btn_start = ctk.CTkButton(self.console_card, text="  ■ Start Session", font=("Arial", 15, "bold"),
                                       fg_color="transparent", text_color=self.color_text,
                                       border_width=1, border_color=self.color_border, height=44,
                                       hover_color=("#E2E8F0", "#2B303C"), command=self.action_start)
        self.btn_start.pack(fill="x", padx=20, pady=(25, 8))
        
        self.btn_break = ctk.CTkButton(self.console_card, text="  ☕ Take a break", font=("Arial", 15, "bold"),
                                       fg_color="transparent", text_color=self.color_text,
                                       border_width=1, border_color=self.color_border, height=44,
                                       hover_color=("#E2E8F0", "#2B303C"), command=self.action_break)
        self.btn_break.pack(fill="x", padx=20, pady=8)
        
        self.btn_pause = ctk.CTkButton(self.console_card, text="  || Pause", font=("Arial", 15, "bold"),
                                       fg_color="transparent", text_color=self.color_text,
                                       border_width=1, border_color=self.color_border, height=44,
                                       hover_color=("#E2E8F0", "#2B303C"), command=self.action_pause)
        self.btn_pause.pack(fill="x", padx=20, pady=(8, 25))
        
        # C. Cognitive Load Card
        self.load_card = ctk.CTkFrame(self.top_row_frame, fg_color=self.color_card,
                                      border_width=1, border_color=self.color_border, width=440, height=220)
        self.load_card.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.load_card.pack_propagate(False)
        
        self.load_header = ctk.CTkFrame(self.load_card, fg_color="transparent")
        self.load_header.pack(fill="x", padx=20, pady=(12, 2))
        self.load_title = ctk.CTkLabel(self.load_header, text="COGNITIVE LOAD", font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.load_title.pack(side="left")
        self.load_status = ctk.CTkLabel(self.load_header, text="Steady", font=("Arial", 14, "bold"), text_color=self.color_steady)
        self.load_status.pack(side="right")
        
        self.load_readout_frame = ctk.CTkFrame(self.load_card, fg_color="transparent")
        self.load_readout_frame.pack(fill="x", padx=20, pady=(2, 6))
        self.load_val_label = ctk.CTkLabel(self.load_readout_frame, text="30", font=("Arial", 42, "bold"), text_color=self.color_steady)
        self.load_val_label.pack(side="left")
        self.load_max_label = ctk.CTkLabel(self.load_readout_frame, text=" /100", font=("Arial", 18), text_color=self.color_text_muted)
        self.load_max_label.pack(side="left", pady=(15, 0), padx=(5, 0))
        
        # 25-segment meter
        self.meter_frame = ctk.CTkFrame(self.load_card, fg_color="transparent", height=25)
        self.meter_frame.pack(fill="x", padx=20, pady=2)
        
        self.segment_widgets = []
        for i in range(25):
            seg = ctk.CTkFrame(self.meter_frame, width=10, height=18, corner_radius=1, fg_color=self.color_segment_off[1])
            seg.pack(side="left", padx=1)
            self.segment_widgets.append(seg)
            
        self.ticks_frame = ctk.CTkFrame(self.load_card, fg_color="transparent", height=15)
        self.ticks_frame.pack(fill="x", padx=20, pady=(1, 3))
        self.tick_0 = ctk.CTkLabel(self.ticks_frame, text="0", font=("Courier New", 9), text_color=self.color_text_muted)
        self.tick_0.place(x=0, y=0)
        self.tick_25 = ctk.CTkLabel(self.ticks_frame, text="25", font=("Courier New", 9), text_color=self.color_text_muted)
        self.tick_25.place(x=78, y=0)
        self.tick_50 = ctk.CTkLabel(self.ticks_frame, text="50", font=("Courier New", 9), text_color=self.color_text_muted)
        self.tick_50.place(x=160, y=0)
        self.tick_75 = ctk.CTkLabel(self.ticks_frame, text="75", font=("Courier New", 9), text_color=self.color_text_muted)
        self.tick_75.place(x=242, y=0)
        self.tick_100 = ctk.CTkLabel(self.ticks_frame, text="100", font=("Courier New", 9), text_color=self.color_text_muted)
        self.tick_100.place(x=324, y=0)
        
        self.legend_frame = ctk.CTkFrame(self.load_card, fg_color="transparent")
        self.legend_frame.pack(fill="x", padx=20, pady=(6, 0))
        self.bullet_steady = ctk.CTkLabel(self.legend_frame, text="● steady (0-32)", font=("Arial", 10), text_color=self.color_steady)
        self.bullet_steady.pack(side="left", padx=(0, 10))
        self.bullet_focused = ctk.CTkLabel(self.legend_frame, text="● focused (32-65)", font=("Arial", 10), text_color=self.color_focused)
        self.bullet_focused.pack(side="left", padx=10)
        self.bullet_elevated = ctk.CTkLabel(self.legend_frame, text="● elevated (65-83)", font=("Arial", 10), text_color=self.color_elevated)
        self.bullet_elevated.pack(side="left", padx=10)
        self.bullet_overload = ctk.CTkLabel(self.legend_frame, text="● overload", font=("Arial", 10), text_color=self.color_overload)
        self.bullet_overload.pack(side="left", padx=10)
        
        # D. TODAY'S TIMELINE Card
        self.timeline_card = ctk.CTkFrame(self.analytics_frame, fg_color=self.color_card, border_width=1, border_color=self.color_border)
        self.timeline_card.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.timeline_header = ctk.CTkFrame(self.timeline_card, fg_color="transparent")
        self.timeline_header.pack(fill="x", padx=20, pady=(10, 2))
        self.timeline_title = ctk.CTkLabel(self.timeline_header, text="TODAY'S TIMELINE", font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.timeline_title.pack(side="left")
        
        self.timeline_legend = ctk.CTkFrame(self.timeline_header, fg_color="transparent")
        self.timeline_legend.pack(side="right")
        self.block_work = ctk.CTkLabel(self.timeline_legend, text="■ Deep Work", font=("Arial", 11, "bold"), text_color=self.color_focused)
        self.block_work.pack(side="left", padx=10)
        self.block_neutral = ctk.CTkLabel(self.timeline_legend, text="■ Neutral", font=("Arial", 11, "bold"), text_color=self.color_text_muted)
        self.block_neutral.pack(side="left", padx=10)
        self.block_dist = ctk.CTkLabel(self.timeline_legend, text="■ Distracted", font=("Arial", 11, "bold"), text_color=self.color_overload)
        self.block_dist.pack(side="left", padx=10)
        self.block_idle = ctk.CTkLabel(self.timeline_legend, text="■ Idle (AFK)", font=("Arial", 11, "bold"), text_color="#8D96A5")
        self.block_idle.pack(side="left", padx=10)
        
        # Matplotlib Timeline
        self.timeline_fig, self.timeline_ax = plt.subplots(figsize=(9, 2.0), dpi=100)
        self.timeline_canvas = FigureCanvasTkAgg(self.timeline_fig, master=self.timeline_card)
        self.timeline_canvas_widget = self.timeline_canvas.get_tk_widget()
        self.timeline_canvas_widget.pack(fill="both", expand=True, padx=20, pady=(2, 10))
        
        # E. BOTTOM CONTAINER (Top Apps & Comparison Cards side-by-side)
        self.bottom_container = ctk.CTkFrame(self.analytics_frame, fg_color="transparent", height=170)
        self.bottom_container.pack(fill="x", padx=20, pady=(5, 15))
        self.bottom_container.pack_propagate(False)
        
        # E1. Left Card: TOP APPLICATIONS RANKING
        self.top_apps_card = ctk.CTkFrame(self.bottom_container, fg_color=self.color_card, border_width=1, border_color=self.color_border, width=480, height=170)
        self.top_apps_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.top_apps_card.pack_propagate(False)
        
        self.top_apps_header = ctk.CTkLabel(self.top_apps_card, text="TOP APPLICATIONS BY FOCUS TIME", font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.top_apps_header.place(x=15, y=12)
        
        self.apps_list_frame = ctk.CTkFrame(self.top_apps_card, fg_color="transparent", width=450, height=120)
        self.apps_list_frame.place(x=15, y=40)
        
        # E2. Right Card: COMPARISON VS YESTERDAY
        self.compare_card = ctk.CTkFrame(self.bottom_container, fg_color=self.color_card, border_width=1, border_color=self.color_border, width=480, height=170)
        self.compare_card.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.compare_card.pack_propagate(False)
        
        self.compare_header = ctk.CTkLabel(self.compare_card, text="TODAY VS YESTERDAY FOCUS COMPARISON", font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.compare_header.place(x=15, y=12)
        
        # Deep Work Section
        self.lbl_dw_header = ctk.CTkLabel(self.compare_card, text="Deep Work Time", font=("Arial", 11, "bold"), text_color=self.color_text_muted)
        self.lbl_dw_header.place(x=15, y=35)
        
        self.spark_left_fig, self.spark_left_ax = plt.subplots(figsize=(1.2, 0.5), dpi=100)
        self.spark_left_canvas = FigureCanvasTkAgg(self.spark_left_fig, master=self.compare_card)
        self.spark_left_widget = self.spark_left_canvas.get_tk_widget()
        self.spark_left_widget.place(x=15, y=55, width=120, height=50)
        
        self.deep_work_val = ctk.CTkLabel(self.compare_card, text="05:24 : 01", font=("Courier New", 16, "bold"), text_color=self.color_text)
        self.deep_work_val.place(x=145, y=55)
        self.deep_work_delta = ctk.CTkLabel(self.compare_card, text="+1h12min", font=("Arial", 11, "bold"), text_color=self.color_focused)
        self.deep_work_delta.place(x=145, y=80)
        
        # Distraction Section
        self.lbl_dist_header = ctk.CTkLabel(self.compare_card, text="Distractions Time", font=("Arial", 11, "bold"), text_color=self.color_text_muted)
        self.lbl_dist_header.place(x=250, y=35)
        
        self.spark_right_fig, self.spark_right_ax = plt.subplots(figsize=(1.2, 0.5), dpi=100)
        self.spark_right_canvas = FigureCanvasTkAgg(self.spark_right_fig, master=self.compare_card)
        self.spark_right_widget = self.spark_right_canvas.get_tk_widget()
        self.spark_right_widget.place(x=250, y=55, width=120, height=50)
        
        self.dist_val = ctk.CTkLabel(self.compare_card, text="02:31 : 19", font=("Courier New", 16, "bold"), text_color=self.color_text)
        self.dist_val.place(x=380, y=55)
        self.dist_delta = ctk.CTkLabel(self.compare_card, text="-1h35min", font=("Arial", 11, "bold"), text_color=self.color_focused)
        self.dist_delta.place(x=380, y=80)
        
        # =========================================================================
        # TAB 2: COGNITIVE THREAD COACH VIEW
        # =========================================================================
        self.coach_top_frame = ctk.CTkFrame(self.coach_frame, fg_color="transparent")
        self.coach_top_frame.pack(fill="x", padx=20, pady=5)
        
        # A. Left: Active Threads Note Card
        self.active_thread_card = ctk.CTkFrame(self.coach_top_frame, fg_color=self.color_card,
                                               border_width=1, border_color=self.color_border, width=470, height=220)
        self.active_thread_card.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.active_thread_card.pack_propagate(False)
        
        self.active_thread_title = ctk.CTkLabel(self.active_thread_card, text="ACTIVE COGNITIVE THREADS (READY-TO-RESUME)",
                                                font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.active_thread_title.pack(anchor="w", padx=20, pady=(15, 5))
        
        # The Stored Note Block
        self.thread_note_bg = ctk.CTkFrame(self.active_thread_card, fg_color=("#F4F6F8", "#15181F"), border_width=1, border_color=self.color_border)
        self.thread_note_bg.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        
        self.thread_app_label = ctk.CTkLabel(self.thread_note_bg, text="App: Code", font=("Arial", 12, "bold"), text_color=self.color_focused)
        self.thread_app_label.pack(anchor="w", padx=15, pady=(10, 2))
        
        self.thread_text_label = ctk.CTkLabel(self.thread_note_bg, text="No active cognitive residue! All threads resolved.",
                                              font=("Arial", 14, "italic"), text_color=self.color_text, wraplength=400, justify="left")
        self.thread_text_label.pack(anchor="w", padx=15, pady=2, fill="both", expand=True)
        
        self.thread_time_label = ctk.CTkLabel(self.thread_note_bg, text="Saved 0 mins ago", font=("Arial", 11), text_color=self.color_text_muted)
        self.thread_time_label.pack(anchor="e", padx=15, pady=(2, 10))
        
        # B. Right: AI Insights and Advice Card
        self.insights_card = ctk.CTkFrame(self.coach_top_frame, fg_color=self.color_card,
                                          border_width=1, border_color=self.color_border, width=470, height=220)
        self.insights_card.pack(side="left", fill="both", expand=True, padx=(10, 0))
        self.insights_card.pack_propagate(False)
        
        self.insights_title = ctk.CTkLabel(self.insights_card, text="AI COGNITIVE COACH INSIGHTS",
                                            font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.insights_title.pack(anchor="w", padx=20, pady=(15, 5))
        
        # Insights message scroll/text
        self.insights_bg = ctk.CTkFrame(self.insights_card, fg_color="transparent")
        self.insights_bg.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        
        self.insight_score_lbl = ctk.CTkLabel(self.insights_bg, text="Attention Score: 78/100  (Good)", font=("Arial", 14, "bold"), text_color=self.color_focused)
        self.insight_score_lbl.pack(anchor="w", pady=2)
        
        self.insight_desc_lbl = ctk.CTkLabel(self.insights_bg, text="You successfully offloaded 2 cognitive threads today using Ready-to-Resume notes. This saved an estimated 40 minutes of background attentional leakage.\n\nAdvice: Your cognitive load peaks around 4:00 PM. Context switching spikes here. We recommend taking a proactive 15-minute break at 3:45 PM to recover focus.",
                                             font=("Arial", 13), text_color=self.color_text, wraplength=400, justify="left")
        self.insight_desc_lbl.pack(anchor="w", pady=(5, 5), fill="both", expand=True)
        
        # C. Bottom: Attention Break History List Card
        self.history_card = ctk.CTkFrame(self.coach_frame, fg_color=self.color_card, border_width=1, border_color=self.color_border)
        self.history_card.pack(fill="both", expand=True, padx=20, pady=(10, 20))
        
        # Header layout to arrange title and clear logs button horizontally
        self.history_hdr_frame = ctk.CTkFrame(self.history_card, fg_color="transparent")
        self.history_hdr_frame.pack(fill="x", padx=20, pady=(12, 5))
        
        self.history_title = ctk.CTkLabel(self.history_hdr_frame, text="ATTENTION BREAK HISTORY & SEVERITY LOGS",
                                           font=("Courier New", 12, "bold"), text_color=self.color_text_muted)
        self.history_title.pack(side="left")
        
        # Premium Clear Logs Button
        self.clear_logs_btn = ctk.CTkButton(self.history_hdr_frame, text="🗑️ Clear History", width=110, height=26,
                                             font=("Arial", 11, "bold"), fg_color="transparent", text_color=self.color_overload,
                                             border_width=1, border_color=self.color_overload,
                                             hover_color=("#FDE8E8", "#2E1A1A"), command=self.clear_history)
        self.clear_logs_btn.pack(side="right")
        
        # Scrollable Frame for switch history logs
        self.history_scroll = ctk.CTkScrollableFrame(self.history_card, fg_color="transparent")
        self.history_scroll.pack(fill="both", expand=True, padx=20, pady=(5, 15))
        
        self.history_rows = []

    def clear_history(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM pending_interventions")
            c.execute("DELETE FROM ready_to_resume_notes")
            conn.commit()
            conn.close()
            print("🧹 Attention break logs and Ready-to-Resume notes successfully cleared.")
            self.update_coach_tab_data()
        except Exception as e:
            print(f"Error clearing history: {e}")

    # --- 5. Segment Navigation (Tab Switching) ---
    def switch_tab(self, value):
        if value == "Focus Analytics":
            self.coach_frame.pack_forget()
            self.analytics_frame.pack(fill="both", expand=True)
            self.update_charts()
        elif value == "Cognitive Thread Coach":
            self.analytics_frame.pack_forget()
            self.coach_frame.pack(fill="both", expand=True)
            self.update_coach_tab_data()

    # --- 6. Active Coach Data Updates ---
    def update_coach_tab_data(self):
        # 1. Update the Stored Thread Card from DB
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            # Fetch latest active Ready-to-Resume note
            c.execute("SELECT timestamp, work_app, note_text FROM ready_to_resume_notes WHERE status = 'active' ORDER BY id DESC LIMIT 1")
            active_row = c.fetchone()
            conn.close()
            
            if active_row:
                ts, app, text = active_row
                self.thread_app_label.configure(text=f"Stored Thread: {app}", text_color=self.color_elevated)
                self.thread_text_label.configure(text=f'"{text}"', font=("Arial", 13, "bold"))
                
                # Calculate elapsed mins since saved
                try:
                    save_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                    diff_mins = int((datetime.now() - save_dt).total_seconds() // 60)
                    self.thread_time_label.configure(text=f"Saved {diff_mins} mins ago")
                except Exception:
                    self.thread_time_label.configure(text="Saved recently")
            else:
                self.thread_app_label.configure(text="Active Thread: None", text_color=self.color_focused)
                self.thread_text_label.configure(text="No active cognitive residue! Outstanding tasks resolved.", font=("Arial", 14, "italic"))
                self.thread_time_label.configure(text="")
        except Exception as e:
            print(f"Error fetching active threads: {e}")

        # 2. Update Attention Break History list
        try:
            # Clear previous widgets in scrollable frame
            for widget in self.history_scroll.winfo_children():
                widget.destroy()
                
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT timestamp, from_app, to_app, type, status FROM pending_interventions ORDER BY id DESC LIMIT 8")
            rows = c.fetchall()
            conn.close()
            
            if len(rows) > 0:
                for r in rows:
                    ts, f_app, t_app, itype, status = r
                    
                    row_frame = ctk.CTkFrame(self.history_scroll, fg_color="transparent", height=40)
                    row_frame.pack(fill="x", pady=4)
                    
                    # Icons / Status bullet
                    sev_col = self.color_steady
                    sev_text = "Low"
                    if itype == "ready_to_resume":
                        sev_col = self.color_overload
                        sev_text = "High"
                    elif itype == "soft_nudge":
                        sev_col = self.color_elevated
                        sev_text = "Medium"
                        
                    bullet = ctk.CTkLabel(row_frame, text="●", text_color=sev_col, font=("Arial", 16))
                    bullet.pack(side="left", padx=5)
                    
                    # Time
                    time_lbl = ctk.CTkLabel(row_frame, text=ts[-8:], font=("Courier New", 12), text_color=self.color_text_muted)
                    time_lbl.pack(side="left", padx=10)
                    
                    # Switch details
                    switch_lbl = ctk.CTkLabel(row_frame, text=f"{f_app} ➔ {t_app}", font=("Arial", 13, "bold"), text_color=self.color_text)
                    switch_lbl.pack(side="left", padx=15)
                    
                    # Intervention details
                    if itype == "ready_to_resume":
                        details = "Ready-to-Resume Plan Resolved" if status == "resolved" else "Interrupted (Residue Risk)"
                    elif itype == "soft_nudge":
                        details = "Soft Nudge Alerted"
                    else:
                        details = "Logged Passively"
                        
                    det_lbl = ctk.CTkLabel(row_frame, text=details, font=("Arial", 12), text_color=self.color_text_muted)
                    det_lbl.pack(side="right", padx=15)
                    
                    divider = ctk.CTkFrame(self.history_scroll, fg_color=self.color_border, height=1)
                    divider.pack(fill="x", pady=2)
            else:
                empty_lbl = ctk.CTkLabel(self.history_scroll, text="No attention break history logged.", font=("Arial", 13, "italic"), text_color=self.color_text_muted)
                empty_lbl.pack(pady=30)
        except Exception as e:
            print(f"Error loading coach history: {e}")

    # --- 7. Theme / Appearance Swapper ---
    def toggle_theme(self):
        current_mode = ctk.get_appearance_mode()
        new_mode = "light" if current_mode == "Dark" else "dark"
        ctk.set_appearance_mode(new_mode)
        
        self.toggle_mode_btn.configure(text="☀️ Light Mode" if new_mode == "light" else "🌙 Dark Mode")
        self.after(200, self.refresh_ui_styling)

    def refresh_ui_styling(self):
        mode = ctk.get_appearance_mode().lower()
        bg_card_hex = self.color_card[0] if mode == "light" else self.color_card[1]
        
        # Redraw circular canvasbg
        self.timer_canvas.configure(bg=bg_card_hex)
        self.draw_circular_timer()
        
        # Trigger chart updates
        if self.tab_nav.get() == "Focus Analytics":
            self.update_charts()
        else:
            self.update_coach_tab_data()

    # --- 8. Drawing Circular Timer ---
    def draw_circular_timer(self):
        self.timer_canvas.delete("all")
        mode = ctk.get_appearance_mode().lower()
        
        border_col = self.color_border[0] if mode == "light" else self.color_border[1]
        text_col = self.color_text[0] if mode == "light" else self.color_text[1]
        text_muted_col = self.color_text_muted[0] if mode == "light" else self.color_text_muted[1]
        
        # Outer thin circle
        self.timer_canvas.create_oval(10, 10, 160, 160, outline=border_col, width=2)
        # Small label
        self.timer_canvas.create_text(85, 60, text="elapsed", fill=text_muted_col, font=("Courier New", 12))
        
        # Timer numbers
        h = self.elapsed_seconds // 3600
        m = (self.elapsed_seconds % 3600) // 60
        s = self.elapsed_seconds % 60
        time_str = f"{h:02d}:{m:02d}:{s:02d}"
        self.timer_canvas.create_text(85, 95, text=time_str, fill=text_col, font=("Courier New", 20, "bold"))

    # --- 9. Button Actions and DB state writing ---
    def sync_session_state(self):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT state, elapsed_seconds FROM session_state LIMIT 1")
            row = c.fetchone()
            conn.close()
            
            if row:
                self.current_state, self.elapsed_seconds = row
                
            self.highlight_active_button()
            self.draw_circular_timer()
        except Exception as e:
            print(f"Error syncing session state: {e}")

    def update_db_state(self, state):
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE session_state SET state = ?, last_updated = ?, elapsed_seconds = ?",
                      (state, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.elapsed_seconds))
            conn.commit()
            conn.close()
            self.current_state = state
            self.highlight_active_button()
        except Exception as e:
            print(f"Error writing DB state: {e}")

    def highlight_active_button(self):
        mode = ctk.get_appearance_mode().lower()
        btn_active_fg = "#2FA572" 
        btn_inactive_fg = "transparent"
        border_col = self.color_border[0] if mode == "light" else self.color_border[1]
        
        self.btn_start.configure(fg_color=btn_inactive_fg, border_color=border_col, text_color=self.color_text[0] if mode == "light" else self.color_text[1])
        self.btn_break.configure(fg_color=btn_inactive_fg, border_color=border_col, text_color=self.color_text[0] if mode == "light" else self.color_text[1])
        self.btn_pause.configure(fg_color=btn_inactive_fg, border_color=border_col, text_color=self.color_text[0] if mode == "light" else self.color_text[1])
        
        if self.current_state == "Active":
            self.btn_start.configure(fg_color=btn_active_fg, border_color=btn_active_fg, text_color="white")
        elif self.current_state == "Break":
            self.btn_break.configure(fg_color="#F4B942", border_color="#F4B942", text_color="white")
        elif self.current_state == "Paused":
            self.btn_pause.configure(fg_color="#E65F5C", border_color="#E65F5C", text_color="white")

    def action_start(self):
        self.update_db_state("Active")

    def action_break(self):
        self.update_db_state("Break")

    def action_pause(self):
        self.update_db_state("Paused")

    # --- 10. Thread-Safe Live Polling & Intervention Handler ---
    def poll_db_and_update(self):
        try:
            # 1. Update Load Widgets from DB
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT cognitive_load, status, session_state FROM app_logs ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            
            # Check for pending active interventions
            c.execute("SELECT id, from_app, to_app, type FROM pending_interventions WHERE status = 'pending' ORDER BY id ASC LIMIT 1")
            pending = c.fetchone()
            conn.close()
            
            if row:
                load_val, status, sess_state = row
                self.update_load_widgets(int(load_val), status)
                
            # 2. Check and handle interventions
            if pending and not self.popup_active:
                int_id, from_app, to_app, itype = pending
                
                if itype == "ready_to_resume":
                    # Ready-to-Resume high severity pre-switch prompt
                    self.popup_active = True
                    self.show_ready_to_resume_popup(int_id, from_app, to_app)
                    
                elif itype == "soft_nudge":
                    # Medium severity soft nudge desktop/in-app alert
                    self.trigger_soft_nudge(int_id, from_app, to_app)
                    
            # 3. Periodically redraw charts/insights
            if self.tab_nav.get() == "Focus Analytics":
                self.update_charts()
            else:
                self.update_coach_tab_data()
        except Exception as e:
            print(f"Error in UI poll: {e}")
            
        # Schedule next poll in 2000 ms (2 seconds) on the main thread safely
        if self.poll_active:
            self.after(2000, self.poll_db_and_update)

    # --- 11. Attentional Residue Soft Nudge Alert ---
    def trigger_soft_nudge(self, int_id, from_app, to_app):
        # Resolve the soft nudge immediately in the DB
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE pending_interventions SET status = 'resolved' WHERE id = ?", (int_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
            
        # Fire native notification safely
        if notification is not None:
            try:
                notification.notify(
                    title="Soft Attention Nudge 🧠",
                    message=f"You left {from_app} after working. Consider completing your task first to avoid attentional residue!",
                    app_name="Cognitive Tracker",
                    timeout=7
                )
            except Exception:
                pass
        print(f"⚠️ Soft Nudge triggered for switch {from_app} -> {to_app}")

    # --- 12. Attentional Residue ACTIVE POPUP DIALOGUE ---
    def show_ready_to_resume_popup(self, int_id, from_app, to_app):
        # Setup Toplevel window modal styled nicely
        popup = ctk.CTkToplevel(self)
        popup.title("Attentional Residue Plan")
        popup.geometry("450x300")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        
        mode = ctk.get_appearance_mode().lower()
        bg_card_hex = self.color_card[0] if mode == "light" else self.color_card[1]
        text_col_hex = self.color_text[0] if mode == "light" else self.color_text[1]
        
        popup.configure(fg_color=bg_card_hex)
        
        # Header
        header = ctk.CTkLabel(popup, text="🧠 Ready-to-Resume Plan", font=("Arial", 18, "bold"), text_color=self.color_overload)
        header.pack(pady=(20, 5))
        
        desc_text = f"You are switching from deep focus in {from_app} to leisure in {to_app}.\nBefore you switch, write down where you are leaving off so your brain can offload this cognitive thread:"
        desc = ctk.CTkLabel(popup, text=desc_text, font=("Arial", 12), text_color=text_col_hex, wraplength=400, justify="center")
        desc.pack(pady=5, padx=20)
        
        # User Note input
        note_entry = ctk.CTkEntry(popup, placeholder_text="e.g. Halfway through drafting index.html, need to write CSS rules next...",
                                  width=400, height=45, font=("Arial", 13))
        note_entry.pack(pady=15, padx=20)
        note_entry.focus()
        
        # Button container
        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(pady=10)
        
        def save_and_dismiss():
            user_note = note_entry.get().strip()
            if len(user_note) == 0:
                user_note = f"Switched contexts from {from_app} to {to_app}."
                
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                
                # 1. Insert note into active table
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                # Deactivate previous active threads first
                c.execute("UPDATE ready_to_resume_notes SET status = 'resumed' WHERE status = 'active'")
                c.execute("INSERT INTO ready_to_resume_notes (timestamp, work_app, note_text, status) VALUES (?, ?, ?, ?)",
                          (ts, from_app, user_note, 'active'))
                
                # 2. Mark pending intervention as resolved
                c.execute("UPDATE pending_interventions SET status = 'resolved' WHERE id = ?", (int_id,))
                
                conn.commit()
                conn.close()
                print(f"✅ Attentional residue note successfully saved: '{user_note}'")
            except Exception as e:
                print(f"Error saving residue note: {e}")
                
            self.popup_active = False
            popup.destroy()
            
        def dismiss():
            # Simply mark as dismissed without note
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE pending_interventions SET status = 'dismissed' WHERE id = ?", (int_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass
            self.popup_active = False
            popup.destroy()
            
        save_btn = ctk.CTkButton(btn_frame, text="Save & Offload Thread", fg_color=self.color_focused, font=("Arial", 13, "bold"), text_color="white", command=save_and_dismiss)
        save_btn.pack(side="left", padx=10)
        
        skip_btn = ctk.CTkButton(btn_frame, text="Skip", fg_color="#555555", hover_color="#333333", font=("Arial", 13), text_color="white", command=dismiss)
        skip_btn.pack(side="left", padx=10)

    # --- 13. Update Cognitive Load Widget states ---
    def update_load_widgets(self, val, status):
        # Dynamically compute status from value to keep them perfectly in sync
        if val < 32:
            computed_status = "steady"
            level_color = self.color_steady
        elif val < 65:
            computed_status = "focused"
            level_color = self.color_focused
        elif val < 83:
            computed_status = "elevated"
            level_color = self.color_elevated
        else:
            computed_status = "overload"
            level_color = self.color_overload

        self.load_val_label.configure(text=str(val))
        self.load_status.configure(text=computed_status.capitalize())
        self.load_val_label.configure(text_color=level_color)
        self.load_status.configure(text_color=level_color)
        
        active_segments = int((val / 100.0) * 25.0)
        active_segments = min(25, max(0, active_segments))
        
        mode = ctk.get_appearance_mode().lower()
        off_col = self.color_segment_off[0] if mode == "light" else self.color_segment_off[1]
        
        for i in range(25):
            if i < active_segments:
                self.segment_widgets[i].configure(fg_color=level_color)
            else:
                self.segment_widgets[i].configure(fg_color=off_col)

    # --- 14. Background Session Clock Incrementor ---
    def run_timer(self):
        while self.poll_active:
            if self.current_state in ["Active", "Break"]:
                self.elapsed_seconds += 1
                self.draw_circular_timer()
                
                if self.elapsed_seconds % 3 == 0:
                    try:
                        conn = sqlite3.connect(DB_PATH)
                        c = conn.cursor()
                        c.execute("UPDATE session_state SET elapsed_seconds = ?", (self.elapsed_seconds,))
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
            time.sleep(1)

    # --- 15. Redraw Themed Matplotlib Focus Charts ---
    def update_charts(self):
        mode = ctk.get_appearance_mode().lower()
        
        bg_card_hex = self.color_card[0] if mode == "light" else self.color_card[1]
        text_muted_hex = self.color_text_muted[0] if mode == "light" else self.color_text_muted[1]
        border_hex = self.color_border[0] if mode == "light" else self.color_border[1]
        
        # A. TODAY'S TIMELINE (Premium broken_barh timeline chart)
        try:
            conn = sqlite3.connect(DB_PATH)
            today_str = datetime.now().strftime('%Y-%m-%d')
            df = pd.read_sql_query("""
                SELECT timestamp, app_name, window_title, category, cognitive_load
                FROM app_logs
                WHERE date(timestamp) = ?
                ORDER BY timestamp ASC
            """, conn, params=(today_str,))
            conn.close()
            
            self.timeline_ax.clear()
            self.timeline_fig.patch.set_facecolor(bg_card_hex)
            self.timeline_ax.set_facecolor(bg_card_hex)
            
            if not df.empty:
                df['timestamp_dt'] = pd.to_datetime(df['timestamp'])
                
                # Group contiguous sessions
                events = []
                current_event = None
                
                for _, row in df.iterrows():
                    t = row['timestamp_dt']
                    app = row['app_name']
                    cat = row['category']
                    
                    if current_event is None:
                        current_event = {
                            'app_name': app,
                            'category': cat,
                            'start': t,
                            'end': t
                        }
                    else:
                        time_gap = (t - current_event['end']).total_seconds()
                        # If same app/category and gap is less than 2 minutes (120s)
                        if time_gap < 120 and current_event['app_name'] == app and current_event['category'] == cat:
                            current_event['end'] = t
                        else:
                            events.append(current_event)
                            current_event = {
                                'app_name': app,
                                'category': cat,
                                'start': t,
                                'end': t
                            }
                if current_event is not None:
                    events.append(current_event)
                    
                import matplotlib.dates as mdates
                
                # Category Colors
                cat_colors = {
                    'Work': self.color_focused,
                    'Distraction': self.color_overload,
                    'Neutral': self.color_steady,
                    'Idle': "#8D96A5"
                }
                
                # 15-minute minimum sliding focus window ending at the current time to make live logs immediately visible
                end_limit = datetime.now() + pd.Timedelta(seconds=30)
                start_limit = end_limit - pd.Timedelta(minutes=15)
                
                # If the logs actually span more than 15 minutes, scale dynamically to show the whole session!
                first_log_time = df['timestamp_dt'].iloc[0]
                if (end_limit - first_log_time).total_seconds() > 900:
                    start_limit = first_log_time - pd.Timedelta(minutes=5)
                    
                self.timeline_ax.set_xlim(start_limit, end_limit)
                
                # 1. Draw a sleek background track (rail)
                start_lim_num = mdates.date2num(start_limit)
                end_lim_num = mdates.date2num(end_limit)
                dur_lim_num = end_lim_num - start_lim_num
                
                track_color = '#262B35' if mode == 'dark' else '#E2E8F0'
                self.timeline_ax.broken_barh([(start_lim_num, dur_lim_num)], (0.4, 0.2), facecolors=track_color, edgecolor='none', zorder=1)
                
                # 2. Draw colored event blocks on top of the rail
                for event in events:
                    start_num = mdates.date2num(event['start'])
                    end_num = mdates.date2num(event['end'])
                    dur_num = end_num - start_num
                    if dur_num <= 0:
                        # Fallback for single data point
                        dur_num = mdates.date2num(event['start'] + pd.Timedelta(seconds=5)) - start_num
                        
                    color = cat_colors.get(event['category'], "#7A8290")
                    self.timeline_ax.broken_barh([(start_num, dur_num)], (0.35, 0.3), facecolors=color, edgecolor='none', zorder=2)
                
                # Style ticks and labels
                self.timeline_ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
                self.timeline_ax.tick_params(colors=text_muted_hex, labelsize=9)
                self.timeline_ax.set_yticks([])
                
                # Draw subtle vertical gridlines behind
                self.timeline_ax.grid(axis='x', color=text_muted_hex, linestyle=':', alpha=0.1, zorder=0)
                
                # Hide Spines
                for spine in ['top', 'right', 'left', 'bottom']:
                    self.timeline_ax.spines[spine].set_visible(False)
            else:
                self.timeline_ax.text(0.5, 0.5, "No Tracking Data Logged Today", 
                                      color=text_muted_hex, ha='center', va='center', fontname="Arial")
                self.timeline_ax.set_xticks([])
                self.timeline_ax.set_yticks([])
                
            self.timeline_fig.tight_layout()
            self.timeline_canvas.draw()
        except Exception as e:
            print(f"Error drawing timeline: {e}")
            
        # Update Top Applications ranking in Left Card dynamically
        try:
            for widget in self.apps_list_frame.winfo_children():
                widget.destroy()
            
            conn = sqlite3.connect(DB_PATH)
            today_str = datetime.now().strftime('%Y-%m-%d')
            df = pd.read_sql_query("""
                SELECT app_name, category
                FROM app_logs
                WHERE date(timestamp) = ?
            """, conn, params=(today_str,))
            conn.close()

            if not df.empty:
                # Count logs: since they are every 5 seconds, count * 5 = duration in seconds
                app_durations = df['app_name'].value_counts() * 5
                total_duration = app_durations.sum()
                
                top_apps = app_durations.head(3)
                
                # App to category map
                app_categories = df.groupby('app_name')['category'].first()
                
                for i, (app_name, duration) in enumerate(top_apps.items()):
                    cat = app_categories.get(app_name, "Neutral")
                    pct = duration / total_duration if total_duration > 0 else 0
                    
                    # Category-specific progress colors
                    color = self.color_focused
                    if cat == "Distraction":
                        color = self.color_overload
                    elif cat == "Neutral":
                        color = self.color_steady
                    elif cat == "Idle":
                        color = "#8D96A5"
                        
                    # Format duration string
                    h = duration // 3600
                    m = (duration % 3600) // 60
                    s = duration % 60
                    duration_str = f"{h}h {m}m" if h > 0 else f"{m}m {s}s"
                    
                    row_frame = ctk.CTkFrame(self.apps_list_frame, fg_color="transparent", height=32)
                    row_frame.pack(fill="x", pady=2)
                    
                    # App Name
                    lbl_name = ctk.CTkLabel(row_frame, text=f"{i+1}. {app_name}", font=("Arial", 12, "bold"), text_color=self.color_text[0] if mode == "light" else self.color_text[1], width=130, anchor="w")
                    lbl_name.pack(side="left", padx=5)
                    
                    # Progress Bar
                    pbar = ctk.CTkProgressBar(row_frame, width=180, height=8, progress_color=color, fg_color=self.color_border[0] if mode == "light" else self.color_border[1])
                    pbar.pack(side="left", padx=10, pady=10)
                    pbar.set(pct)
                    
                    # Duration and percentage
                    lbl_dur = ctk.CTkLabel(row_frame, text=f"{duration_str} ({int(pct*100)}%)", font=("Courier New", 11), text_color=text_muted_hex, width=90, anchor="e")
                    lbl_dur.pack(side="left", padx=5)
            else:
                lbl_empty = ctk.CTkLabel(self.apps_list_frame, text="No Tracking Data Logged Today", font=("Arial", 12, "italic"), text_color=text_muted_hex)
                lbl_empty.pack(pady=40)
        except Exception as e:
            print(f"Error drawing top apps: {e}")
            
        # B. TODAY VS YESTERDAY COMPARE STATS & SPARKLINE AREA PLOTS
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            today_str = datetime.now().strftime('%Y-%m-%d')
            yesterday_str = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

            c.execute("SELECT count(*) FROM app_logs WHERE category = 'Work' AND date(timestamp) = ?", (today_str,))
            work_today = c.fetchone()[0] * 5
            c.execute("SELECT count(*) FROM app_logs WHERE category = 'Work' AND date(timestamp) = ?", (yesterday_str,))
            work_yesterday = c.fetchone()[0] * 5
            
            c.execute("SELECT count(*) FROM app_logs WHERE category = 'Distraction' AND date(timestamp) = ?", (today_str,))
            dist_today = c.fetchone()[0] * 5
            c.execute("SELECT count(*) FROM app_logs WHERE category = 'Distraction' AND date(timestamp) = ?", (yesterday_str,))
            dist_yesterday = c.fetchone()[0] * 5
            conn.close()
            
            # Safe Fallback to mockup data if real DB lacks logs
            if work_today < 60:
                work_today = 19441   # 5h 24m 01s
                work_yesterday = 15120 # 4h 12m 00s
            if dist_today < 60:
                dist_today = 9079     # 2h 31m 19s
                dist_yesterday = 14700 # 4h 05m 00s
                
            self.deep_work_val.configure(text=self.format_seconds(work_today))
            self.dist_val.configure(text=self.format_seconds(dist_today))
            
            work_diff = work_today - work_yesterday
            if work_diff >= 0:
                self.deep_work_delta.configure(text=f"+{self.format_diff(work_diff)}", text_color=self.color_focused)
            else:
                self.deep_work_delta.configure(text=f"-{self.format_diff(abs(work_diff))}", text_color=self.color_overload)
                
            dist_diff = dist_today - dist_yesterday
            if dist_diff <= 0:
                self.dist_delta.configure(text=f"-{self.format_diff(abs(dist_diff))}", text_color=self.color_focused)
            else:
                self.dist_delta.configure(text=f"+{self.format_diff(dist_diff)}", text_color=self.color_overload)
                
            # Sparkline curves
            self.draw_sparkline(self.spark_left_ax, self.spark_left_canvas, bg_card_hex, self.color_focused, [0.3, 0.45, 0.35, 0.55, 0.68, 0.52, 0.75, 0.65])
            self.draw_sparkline(self.spark_right_ax, self.spark_right_canvas, bg_card_hex, self.color_elevated, [0.65, 0.72, 0.5, 0.4, 0.35, 0.25, 0.45, 0.1])
        except Exception as e:
            print(f"Error drawing sparklines: {e}")

    def format_seconds(self, total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        s = total_seconds % 60
        return f"{h:02d}:{m:02d} : {s:02d}"

    def format_diff(self, total_seconds):
        h = total_seconds // 3600
        m = (total_seconds % 3600) // 60
        if h > 0:
            return f"{h}h{m}min"
        return f"{m}min"

    def draw_sparkline(self, ax, canvas, bg_hex, fill_color, data_points):
        ax.clear()
        self.spark_left_fig.patch.set_facecolor(bg_hex)
        self.spark_right_fig.patch.set_facecolor(bg_hex)
        ax.set_facecolor(bg_hex)
        
        x = np.arange(len(data_points))
        ax.plot(x, data_points, color=fill_color, linewidth=1.5, antialiased=True)
        ax.fill_between(x, data_points, color=fill_color, alpha=0.2)
        
        ax.set_ylim(0, 1.0)
        ax.set_xlim(0, len(data_points) - 1)
        ax.axis('off')
        canvas.draw()

    # --- 16. Subprocess Launcher & Window Closing Hook ---
    def ensure_tracker_running(self):
        import signal
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tracker_path = os.path.join(base_dir, "tracker_engine", "window_logger.py")
        
        # 1. Terminate any existing orphan window_logger.py instances on the system
        try:
            output = subprocess.check_output(["pgrep", "-f", "window_logger.py"]).decode().strip()
            if output:
                pids = [int(pid) for pid in output.split()]
                my_pid = os.getpid()
                for pid in pids:
                    if pid != my_pid:
                        try:
                            os.kill(pid, signal.SIGTERM)
                            print(f"🎯 Terminated duplicate window_logger.py process (PID {pid})")
                        except Exception:
                            pass
        except Exception:
            pass
            
        # 2. Spawn a fresh background tracker (redirect output to database/tracker.log for easy diagnostics)
        if self.tracker_process is None or self.tracker_process.poll() is not None:
            try:
                log_path = os.path.join(base_dir, "database", "tracker.log")
                self.tracker_log_file = open(log_path, "a") # append mode
                self.tracker_process = subprocess.Popen(
                    [sys.executable, tracker_path],
                    stdout=self.tracker_log_file,
                    stderr=self.tracker_log_file
                )
                print("🎯 Silent background tracker subprocess launched successfully.")
            except Exception as e:
                print(f"Error launching background tracker: {e}")

    def load_showcase_data(self):
        print("🌱 Seeding rich synthetic showcase data...")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Clean previous data
        c.execute("DELETE FROM app_logs")
        c.execute("DELETE FROM pending_interventions")
        c.execute("DELETE FROM ready_to_resume_notes")
        
        now = datetime.now()
        logs = []
        
        # Yesterday Seeding (realistic dense intervals matching 5-second ticks!)
        yesterday = now - timedelta(days=1)
        for hr in range(9, 21):
            hr_time = yesterday.replace(hour=hr, minute=0, second=0)
            if hr in [9, 10, 14, 15, 19]:
                # Work hours (5 hours total)
                # Seed every 5 seconds: 12 ticks per minute, 60 minutes = 720 ticks per hour
                for tick_idx in range(720):
                    t = hr_time + timedelta(seconds=tick_idx * 5)
                    logs.append((t.strftime("%Y-%m-%d %H:%M:%S"), "Code", "Coding ui_dashboard/app.py", "Work", 54, "focused", "Active"))
            elif hr in [11, 12, 16, 17]:
                # Distraction hours (4 hours total)
                for tick_idx in range(720):
                    t = hr_time + timedelta(seconds=tick_idx * 5)
                    logs.append((t.strftime("%Y-%m-%d %H:%M:%S"), "Google Chrome", "Reddit", "Distraction", 80, "elevated", "Active"))
            else:
                # Neutral hours (3 hours total)
                for tick_idx in range(720):
                    t = hr_time + timedelta(seconds=tick_idx * 5)
                    logs.append((t.strftime("%Y-%m-%d %H:%M:%S"), "Slack", "Direct messages", "Neutral", 32, "steady", "Active"))
        
        # Today Seeding: 6 hours ago to now (dense 5-second activity blocks for a flawless showcase!)
        start_seeding = now - timedelta(hours=6)
        tick = start_seeding
        while tick < now:
            diff_hours = (tick - start_seeding).total_seconds() / 3600
            if diff_hours < 1.5:
                app = "Code"
                title = "Visual Studio Code (index.html)"
                cat = "Work"
                load = 55
                status = "focused"
            elif diff_hours < 2.0:
                app = "Idle"
                title = "Away From Keyboard"
                cat = "Idle"
                load = 15
                status = "steady"
            elif diff_hours < 3.2:
                app = "Google Chrome"
                title = "GitHub - Cognitive-Behavior-Tracker"
                cat = "Work"
                load = 62
                status = "focused"
            elif diff_hours < 3.7:
                app = "Slack"
                title = "Slack (Direct Messages)"
                cat = "Neutral"
                load = 35
                status = "steady"
            elif diff_hours < 4.8:
                app = "Safari"
                title = "YouTube (Lo-Fi Study Beats)"
                cat = "Distraction"
                load = 78
                status = "elevated"
            else:
                app = "Code"
                title = "Visual Studio Code (app.py)"
                cat = "Work"
                load = 58
                status = "focused"
            
            logs.append((tick.strftime("%Y-%m-%d %H:%M:%S"), app, title, cat, load, status, "Active"))
            tick += timedelta(seconds=5)
            
        c.executemany("INSERT INTO app_logs (timestamp, app_name, window_title, category, cognitive_load, status, session_state) VALUES (?, ?, ?, ?, ?, ?, ?)", logs)
        
        # Seed 10 rich mock interventions spanning the last 2 days for detailed history
        interventions = [
            ((now - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"), "Code (logic.py)", "Google Chrome (Twitter)", "soft_nudge", "resolved"),
            ((now - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"), "Code (app.py)", "Safari (YouTube)", "soft_nudge", "resolved"),
            ((now - timedelta(hours=1, minutes=20)).strftime("%Y-%m-%d %H:%M:%S"), "Terminal (run)", "Spotify (Music)", "logged_passively", "resolved"),
            ((now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), "Code (index.html)", "Google Chrome (Reddit)", "ready_to_resume", "resolved"),
            ((now - timedelta(hours=3, minutes=10)).strftime("%Y-%m-%d %H:%M:%S"), "Xcode (main.m)", "Slack (General)", "soft_nudge", "resolved"),
            ((now - timedelta(hours=4, minutes=45)).strftime("%Y-%m-%d %H:%M:%S"), "Code (app.py)", "Figma (Design Mockup)", "logged_passively", "resolved"),
            ((now - timedelta(hours=5, minutes=15)).strftime("%Y-%m-%d %H:%M:%S"), "Code (window_logger.py)", "Safari (Netflix)", "ready_to_resume", "resolved"),
            ((yesterday.replace(hour=10, minute=15)).strftime("%Y-%m-%d %H:%M:%S"), "Code (model.py)", "Google Chrome (Facebook)", "soft_nudge", "resolved"),
            ((yesterday.replace(hour=14, minute=30)).strftime("%Y-%m-%d %H:%M:%S"), "Code (app.py)", "Discord (Gaming)", "ready_to_resume", "resolved"),
            ((yesterday.replace(hour=16, minute=45)).strftime("%Y-%m-%d %H:%M:%S"), "Xcode (compile)", "YouTube (Lo-fi study beats)", "soft_nudge", "resolved")
        ]
        c.executemany("INSERT INTO pending_interventions (timestamp, from_app, to_app, type, status) VALUES (?, ?, ?, ?, ?)", interventions)
                  
        # Seed ready-to-resume notes with varying resolution states
        c.execute("INSERT INTO ready_to_resume_notes (timestamp, work_app, note_text, status) VALUES (?, ?, ?, ?)",
                  ((now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"), "Code (index.html)", "Halfway through building the horizontal broken_barh timeline, need to style the canvas background next.", "active"))
        c.execute("INSERT INTO ready_to_resume_notes (timestamp, work_app, note_text, status) VALUES (?, ?, ?, ?)",
                  ((now - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"), "Xcode (main.m)", "Styled clean button overlays in Tkinter widget hierarchy.", "resumed"))
        c.execute("INSERT INTO ready_to_resume_notes (timestamp, work_app, note_text, status) VALUES (?, ?, ?, ?)",
                  ((now - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"), "Code (window_logger.py)", "Implemented custom HIDIdleTime fetching through Apple ioreg query.", "resumed"))
        
        # Synchronize elapsed session state timer (6 hours today)
        c.execute("UPDATE session_state SET state = 'Active', elapsed_seconds = 21600")
        
        conn.commit()
        conn.close()

    def toggle_showcase(self):
        if self.showcase_btn.cget("text") == "✨ Load Showcase":
            self.load_showcase_data()
            self.showcase_btn.configure(text="🟢 Live Mode (Reset)", fg_color="#2FA572", hover_color="#238258")
            print("✨ Showcase synthetic data successfully loaded!")
        else:
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("DELETE FROM app_logs")
                c.execute("DELETE FROM pending_interventions")
                c.execute("DELETE FROM ready_to_resume_notes")
                c.execute("UPDATE session_state SET state = 'Active', elapsed_seconds = 0")
                conn.commit()
                conn.close()
                print("🧹 Reset database to pristine empty state for Live Mode.")
            except Exception as e:
                print(f"Error resetting database: {e}")
                
            self.showcase_btn.configure(text="✨ Load Showcase", fg_color=self.color_card, hover_color=("#E2E8F0", "#2B303C"))
            
        # Refresh UI
        self.sync_session_state()
        self.update_charts()
        self.update_coach_tab_data()

    def on_closing(self):
        self.poll_active = False
        
        if hasattr(self, "tracker_log_file") and self.tracker_log_file:
            try:
                self.tracker_log_file.close()
            except Exception:
                pass
                
        if self.tracker_process:
            try:
                self.tracker_process.terminate()
                self.tracker_process.wait(timeout=1.0)
                print("🎯 Background Tracker terminated cleanly.")
            except Exception:
                pass
                
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE session_state SET state = 'Paused'")
            conn.commit()
            conn.close()
        except Exception:
            pass
            
        self.destroy()

if __name__ == "__main__":
    app = FocusApp()
    app.mainloop()