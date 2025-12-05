"""
Mining Missions Panel Widget for EliteMining
Collapsible panel showing active mining missions with progress tracking
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable
import logging
from datetime import datetime, timezone

log = logging.getLogger("EliteMining.MissionsPanel")


class MiningMissionsPanel(ttk.Frame):
    """Collapsible panel showing active mining missions with progress"""
    
    def __init__(self, parent, on_find_hotspot: Optional[Callable] = None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.on_find_hotspot = on_find_hotspot  # Callback to open Ring Finder with commodity
        self.collapsed = False
        self.missions = []
        
        self._build_ui()
        self._register_tracker_callback()
    
    def _build_ui(self):
        """Build the missions panel UI"""
        # Get theme colors
        try:
            from config import load_theme
            theme = load_theme()
        except:
            theme = "dark_gray"
        
        if theme == "elite_orange":
            self.bg_color = "#0a0a0a"
            self.fg_color = "#ff8c00"
            self.header_bg = "#1a1a1a"
            self.progress_bg = "#333333"
            self.progress_fg = "#ff6600"
        else:
            self.bg_color = "#1e1e1e"
            self.fg_color = "#e6e6e6"
            self.header_bg = "#2d2d2d"
            self.progress_bg = "#333333"
            self.progress_fg = "#4a9eff"
        
        # Header frame with collapse toggle
        self.header_frame = tk.Frame(self, bg=self.header_bg)
        self.header_frame.pack(fill="x", pady=(0, 2))
        
        self.toggle_btn = tk.Label(
            self.header_frame, 
            text="▼", 
            bg=self.header_bg, 
            fg=self.fg_color,
            font=("Segoe UI", 9),
            cursor="hand2"
        )
        self.toggle_btn.pack(side="left", padx=(5, 2))
        self.toggle_btn.bind("<Button-1>", self._toggle_collapse)
        
        self.header_label = tk.Label(
            self.header_frame,
            text="📋 Mining Missions (0)",
            bg=self.header_bg,
            fg=self.fg_color,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2"
        )
        self.header_label.pack(side="left", padx=2)
        self.header_label.bind("<Button-1>", self._toggle_collapse)
        
        # Content frame (collapsible)
        self.content_frame = tk.Frame(self, bg=self.bg_color)
        self.content_frame.pack(fill="x", padx=5, pady=2)
        
        # Placeholder for no missions
        self.no_missions_label = tk.Label(
            self.content_frame,
            text="No active mining missions",
            bg=self.bg_color,
            fg="#666666",
            font=("Segoe UI", 8, "italic")
        )
        self.no_missions_label.pack(pady=5)
        
        # Container for mission items
        self.missions_container = tk.Frame(self.content_frame, bg=self.bg_color)
        self.missions_container.pack(fill="x")
        
        # Initial refresh
        self._refresh_missions()
    
    def _register_tracker_callback(self):
        """Register callback with mission tracker for updates"""
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if MISSIONS_AVAILABLE:
                tracker = get_mission_tracker()
                if tracker:
                    tracker.add_callback(self._refresh_missions)
        except Exception as e:
            log.warning(f"Could not register mission tracker callback: {e}")
    
    def _toggle_collapse(self, event=None):
        """Toggle collapsed state"""
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.toggle_btn.config(text="▶")
            self.content_frame.pack_forget()
        else:
            self.toggle_btn.config(text="▼")
            self.content_frame.pack(fill="x", padx=5, pady=2)
    
    def _refresh_missions(self):
        """Refresh the missions display"""
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if not MISSIONS_AVAILABLE:
                return
            
            tracker = get_mission_tracker()
            if not tracker:
                return
            
            missions = tracker.get_active_missions()
            
            # Update header
            count = len(missions)
            self.header_label.config(text=f"📋 Mining Missions ({count})")
            
            # Clear existing mission widgets
            for widget in self.missions_container.winfo_children():
                widget.destroy()
            
            if not missions:
                self.no_missions_label.pack(pady=5)
                return
            else:
                self.no_missions_label.pack_forget()
            
            # Create mission widgets
            for mission in missions:
                self._create_mission_widget(mission)
                
        except Exception as e:
            log.warning(f"Error refreshing missions: {e}")
    
    def _create_mission_widget(self, mission: dict):
        """Create a widget for a single mission"""
        commodity = mission.get('commodity', 'Unknown')
        count = mission.get('count', 0)
        collected = mission.get('collected', 0)
        reward = mission.get('reward', 0)
        expiry = mission.get('expiry', '')
        destination_station = mission.get('destination_station', '')
        destination_system = mission.get('destination_system', '')
        is_wing = mission.get('wing', False)
        
        # Mission frame
        mission_frame = tk.Frame(self.missions_container, bg=self.bg_color)
        mission_frame.pack(fill="x", pady=2)
        
        # Top row: commodity name, wing indicator, and progress
        top_row = tk.Frame(mission_frame, bg=self.bg_color)
        top_row.pack(fill="x")
        
        # Icon and commodity (with wing indicator if applicable)
        wing_indicator = " 👥" if is_wing else ""
        commodity_label = tk.Label(
            top_row,
            text=f"⛏️ {commodity}{wing_indicator}:",
            bg=self.bg_color,
            fg=self.fg_color,
            font=("Segoe UI", 9, "bold")
        )
        commodity_label.pack(side="left")
        
        # Progress text
        progress_pct = (collected / count * 100) if count > 0 else 0
        progress_text = f"{collected}/{count} ({progress_pct:.0f}%)"
        progress_label = tk.Label(
            top_row,
            text=progress_text,
            bg=self.bg_color,
            fg="#00ff00" if collected >= count else self.fg_color,
            font=("Segoe UI", 9)
        )
        progress_label.pack(side="left", padx=(5, 0))
        
        # Find Hotspot button
        if self.on_find_hotspot:
            find_btn = tk.Button(
                top_row,
                text="🔍",
                command=lambda c=commodity: self._on_find_hotspot_click(c),
                bg="#333333",
                fg="#ffffff",
                font=("Segoe UI", 8),
                relief="flat",
                cursor="hand2",
                padx=3,
                pady=0
            )
            find_btn.pack(side="right", padx=2)
        
        # Progress bar
        bar_frame = tk.Frame(mission_frame, bg=self.progress_bg, height=6)
        bar_frame.pack(fill="x", pady=(2, 0))
        bar_frame.pack_propagate(False)
        
        # Calculate bar width
        bar_width_pct = min(100, progress_pct)
        bar_fill = tk.Frame(bar_frame, bg=self.progress_fg if collected < count else "#00aa00")
        bar_fill.place(relwidth=bar_width_pct/100, relheight=1.0)
        
        # Middle row: delivery location
        if destination_station or destination_system:
            location_row = tk.Frame(mission_frame, bg=self.bg_color)
            location_row.pack(fill="x")
            
            # Format: "📍 Station @ System" or just system if no station
            if destination_station and destination_system:
                location_text = f"📍 {destination_station} @ {destination_system}"
            elif destination_station:
                location_text = f"📍 {destination_station}"
            else:
                location_text = f"📍 {destination_system}"
                
            location_label = tk.Label(
                location_row,
                text=location_text,
                bg=self.bg_color,
                fg="#4a9eff",
                font=("Segoe UI", 8)
            )
            location_label.pack(side="left")
        
        # Bottom row: deadline and reward
        bottom_row = tk.Frame(mission_frame, bg=self.bg_color)
        bottom_row.pack(fill="x")
        
        # Time remaining
        time_text = self._format_time_remaining(expiry)
        time_label = tk.Label(
            bottom_row,
            text=time_text,
            bg=self.bg_color,
            fg="#888888",
            font=("Segoe UI", 8)
        )
        time_label.pack(side="left")
        
        # Reward
        reward_text = f"{reward:,.0f} CR" if reward else ""
        reward_label = tk.Label(
            bottom_row,
            text=reward_text,
            bg=self.bg_color,
            fg="#ffcc00",
            font=("Segoe UI", 8)
        )
        reward_label.pack(side="right")
    
    def _format_time_remaining(self, expiry: str) -> str:
        """Format expiry time as time remaining"""
        if not expiry:
            return ""
        try:
            expiry_dt = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = expiry_dt - now
            
            if delta.total_seconds() < 0:
                return "⚠️ Expired"
            
            days = delta.days
            hours = delta.seconds // 3600
            
            if days > 0:
                return f"⏱️ {days}d {hours}h"
            elif hours > 0:
                minutes = (delta.seconds % 3600) // 60
                return f"⏱️ {hours}h {minutes}m"
            else:
                minutes = delta.seconds // 60
                return f"⏱️ {minutes}m"
        except Exception:
            return ""
    
    def _on_find_hotspot_click(self, commodity: str):
        """Handle Find Hotspot button click"""
        if self.on_find_hotspot:
            self.on_find_hotspot(commodity)
    
    def update_cargo(self, cargo_items: dict):
        """Update mission progress from cargo"""
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if MISSIONS_AVAILABLE:
                tracker = get_mission_tracker()
                if tracker:
                    tracker.update_progress_from_cargo(cargo_items)
        except Exception as e:
            log.warning(f"Error updating cargo for missions: {e}")
    
    def destroy(self):
        """Clean up callbacks on destroy"""
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if MISSIONS_AVAILABLE:
                tracker = get_mission_tracker()
                if tracker:
                    tracker.remove_callback(self._refresh_missions)
        except:
            pass
        super().destroy()
