"""
Mining Missions Tab for EliteMining
Full tab for tracking mining missions with detailed progress
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Dict
import logging
from datetime import datetime, timezone

log = logging.getLogger("EliteMining.MissionsTab")


class MiningMissionsTab(ttk.Frame):
    """Full tab for tracking mining missions with progress and integration with Ring Finder"""
    
    def __init__(self, parent, ring_finder=None, cargo_monitor=None, main_app=None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.ring_finder = ring_finder
        self.cargo_monitor = cargo_monitor
        self.main_app = main_app
        self.missions = []
        
        # Track mission cards for in-place updates (mission_id -> card widgets dict)
        self._mission_cards: Dict[int, dict] = {}
        self._current_mission_ids: set = set()
        
        # Get theme
        try:
            from config import load_theme
            self.theme = load_theme()
        except:
            self.theme = "dark_gray"
        
        self._setup_colors()
        self._build_ui()
        self._register_tracker_callback()
    
    def _setup_colors(self):
        """Setup theme colors"""
        if self.theme == "elite_orange":
            self.bg_color = "#000000"
            self.fg_color = "#ff8c00"
            self.fg_bright = "#ffa500"
            self.fg_dim = "#888888"
            self.accent_bg = "#1a1a1a"
            self.progress_bg = "#333333"
            self.progress_fg = "#ff6600"
            self.delivered_fg = "#00cc00"
            self.btn_bg = "#333333"
            self.btn_fg = "#ff8c00"
            self.complete_color = "#00cc00"
        else:
            self.bg_color = "#1e1e1e"
            self.fg_color = "#e6e6e6"
            self.fg_bright = "#ffffff"
            self.fg_dim = "#888888"
            self.accent_bg = "#2d2d2d"
            self.progress_bg = "#333333"
            self.progress_fg = "#ff6600"
            self.delivered_fg = "#00cc00"
            self.btn_bg = "#333333"
            self.btn_fg = "#ffffff"
            self.complete_color = "#00cc00"
    
    def _build_ui(self):
        """Build the missions tab UI"""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        # Header frame with theme background
        header_frame = tk.Frame(self, bg=self.bg_color)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        tk.Label(
            header_frame,
            text=t('mining_missions.title'),
            font=("Segoe UI", 14, "bold"),
            bg=self.bg_color,
            fg=self.fg_bright
        ).pack(side="left")
        
        # Main content - scrollable frame for missions
        content_frame = tk.Frame(self, bg=self.bg_color)
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        # Create canvas with scrollbar
        self.canvas = tk.Canvas(content_frame, bg=self.bg_color, highlightthickness=0)
        scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.bg_color)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Bind mousewheel
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Initial refresh
        self._refresh_missions()
    
    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def _register_tracker_callback(self):
        """Register callback with mission tracker"""
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if MISSIONS_AVAILABLE:
                tracker = get_mission_tracker()
                if tracker:
                    tracker.add_callback(self._refresh_missions)
        except Exception as e:
            log.warning(f"Could not register mission tracker callback: {e}")
    
    def _refresh_missions(self):
        """Refresh the missions display - update in-place to avoid blinking"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if not MISSIONS_AVAILABLE:
                self._clear_and_show_no_missions()
                return
            
            tracker = get_mission_tracker()
            if not tracker:
                self._clear_and_show_no_missions()
                return
            
            missions = tracker.get_active_missions()
            
            if not missions:
                self._clear_and_show_no_missions()
                return
            
            # Get current cargo for progress calculation
            cargo_items = self._get_cargo_items()
            
            # Get set of current mission IDs
            new_mission_ids = {m.get('mission_id') for m in missions}
            
            # Check if missions list changed (added/removed)
            if new_mission_ids != self._current_mission_ids:
                # Missions changed - need full rebuild
                self._full_rebuild_missions(missions, cargo_items)
                self._current_mission_ids = new_mission_ids
            else:
                # Just update values in-place
                self._update_mission_values(missions, cargo_items)
                
        except Exception as e:
            log.warning(f"Error refreshing missions: {e}")
            self._clear_and_show_no_missions()
    
    def _clear_and_show_no_missions(self):
        """Clear cards and show no missions message"""
        self._mission_cards.clear()
        self._current_mission_ids.clear()
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self._show_no_missions_message()
    
    def _full_rebuild_missions(self, missions: list, cargo_items: Dict[str, int]):
        """Full rebuild of mission cards when missions list changes"""
        # Clear existing widgets
        self._mission_cards.clear()
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Create mission cards
        for i, mission in enumerate(missions):
            self._create_mission_card(mission, cargo_items, i)
    
    def _update_mission_values(self, missions: list, cargo_items: Dict[str, int]):
        """Update existing mission cards in-place without rebuilding"""
        for mission in missions:
            mission_id = mission.get('mission_id')
            if mission_id not in self._mission_cards:
                continue
            
            card_widgets = self._mission_cards[mission_id]
            commodity = mission.get('commodity', 'Unknown')
            count = mission.get('count', 0)
            delivered = mission.get('delivered', 0)
            wing = mission.get('wing', False)
            
            # Calculate actual cargo for this commodity
            actual_cargo = 0
            commodity_lower = commodity.lower()
            for cargo_name, qty in cargo_items.items():
                if commodity_lower in cargo_name.lower() or cargo_name.lower() in commodity_lower:
                    actual_cargo = qty
                    break
            
            # Calculate progress
            progress_pct = (actual_cargo / count * 100) if count > 0 else 0
            delivered_pct = (delivered / count * 100) if count > 0 else 0
            is_complete = actual_cargo >= count
            
            # Update commodity label - show "in cargo" to clarify
            wing_icon = "👥 " if wing else ""
            commodity_text = f"{wing_icon}{commodity}: {actual_cargo}/{count}t (in cargo)"
            if is_complete:
                commodity_text += " ✓"
            
            if 'commodity_label' in card_widgets:
                card_widgets['commodity_label'].configure(
                    text=commodity_text,
                    fg=self.complete_color if is_complete else self.fg_bright
                )
            
            # Update cargo progress bar
            if 'cargo_bar_fill' in card_widgets:
                bar_width_pct = min(100, progress_pct)
                bar_color = self.complete_color if is_complete else self.progress_fg
                card_widgets['cargo_bar_fill'].configure(bg=bar_color)
                card_widgets['cargo_bar_fill'].place(relwidth=bar_width_pct/100, relheight=1.0)
            
            # Update delivered label and bar
            if 'delivered_label' in card_widgets:
                card_widgets['delivered_label'].configure(text=f"Delivered: {delivered}/{count}t")
            
            if 'delivered_bar_fill' in card_widgets:
                delivered_bar_pct = min(100, delivered_pct)
                card_widgets['delivered_bar_fill'].place(relwidth=delivered_bar_pct/100, relheight=1.0)
    
    def _show_no_missions_message(self):
        """Show message when no missions are active"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        msg_frame = tk.Frame(self.scrollable_frame, bg=self.bg_color)
        msg_frame.pack(fill="x", pady=50)
        
        tk.Label(
            msg_frame,
            text=t('mining_missions.no_missions'),
            bg=self.bg_color,
            fg=self.fg_dim,
            font=("Segoe UI", 12)
        ).pack()
        
        tk.Label(
            msg_frame,
            text=t('mining_missions.no_missions_hint'),
            bg=self.bg_color,
            fg=self.fg_dim,
            font=("Segoe UI", 10)
        ).pack()
        
        # Tip about mission types
        tk.Label(
            msg_frame,
            text=t('mining_missions.tip_detection'),
            bg=self.bg_color,
            fg=self.fg_dim,
            font=("Segoe UI", 9, "italic")
        ).pack(pady=(20, 0))
    
    def _get_cargo_items(self) -> Dict[str, int]:
        """Get current cargo items for progress calculation.
        
        Reads from CargoMonitor.cargo_items which is populated from Cargo.json.
        Format: {display_name: quantity} e.g. {"Bromellite": 25, "Limpet": 50}
        """
        cargo = {}
        if self.cargo_monitor and hasattr(self.cargo_monitor, 'cargo_items'):
            # cargo_items is always {name: int_quantity}
            for name, qty in self.cargo_monitor.cargo_items.items():
                cargo[name] = qty if isinstance(qty, int) else 0
        return cargo
    
    def _create_mission_card(self, mission: dict, cargo_items: Dict[str, int], index: int):
        """Create a compact card for a single mission"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        mission_id = mission.get('mission_id')
        commodity = mission.get('commodity', 'Unknown')
        count = mission.get('count', 0)
        collected = mission.get('collected', 0)
        delivered = mission.get('delivered', 0)
        reward = mission.get('reward', 0)
        expiry = mission.get('expiry', '')
        faction = mission.get('faction', '')
        wing = mission.get('wing', False)
        destination_station = mission.get('destination_station', '')
        destination_system = mission.get('destination_system', '')
        
        # Calculate actual cargo for this commodity
        actual_cargo = 0
        commodity_lower = commodity.lower()
        for cargo_name, qty in cargo_items.items():
            if commodity_lower in cargo_name.lower() or cargo_name.lower() in commodity_lower:
                actual_cargo = qty
                break
        
        # Card frame with border - more compact
        card = tk.Frame(
            self.scrollable_frame,
            bg=self.accent_bg,
            highlightbackground=self.fg_dim,
            highlightthickness=1
        )
        card.pack(fill="x", padx=5, pady=2)
        
        # Inner padding - reduced
        inner = tk.Frame(card, bg=self.accent_bg)
        inner.pack(fill="x", padx=8, pady=6)
        
        # Row 1: Commodity, Progress, Find Hotspot button
        row1 = tk.Frame(inner, bg=self.accent_bg)
        row1.pack(fill="x")
        
        # Wing indicator + commodity name (smaller font)
        wing_icon = "👥 " if wing else ""
        progress_pct = (actual_cargo / count * 100) if count > 0 else 0
        delivered_pct = (delivered / count * 100) if count > 0 else 0
        is_complete = actual_cargo >= count
        
        # Commodity + progress on same line - show "in cargo" to clarify
        commodity_text = f"{wing_icon}{commodity}: {actual_cargo}/{count}t (in cargo)"
        if is_complete:
            commodity_text += " ✓"
        
        commodity_label = tk.Label(
            row1,
            text=commodity_text,
            bg=self.accent_bg,
            fg=self.complete_color if is_complete else self.fg_bright,
            font=("Segoe UI", 9, "bold")
        )
        commodity_label.pack(side="left")
        
        # Find Hotspot button (smaller)
        find_btn = tk.Button(
            row1,
            text="🔍 Find",
            command=lambda c=commodity: self._find_hotspot(c),
            bg=self.btn_bg,
            fg=self.btn_fg,
            font=("Segoe UI", 8),
            relief="flat",
            cursor="hand2",
            padx=5,
            pady=0
        )
        find_btn.pack(side="right")
        
        # Cargo Progress bar (thinner)
        bar_frame = tk.Frame(inner, bg=self.progress_bg, height=4)
        bar_frame.pack(fill="x", pady=(3, 2))
        bar_frame.pack_propagate(False)
        
        bar_width_pct = min(100, progress_pct)
        bar_color = self.complete_color if is_complete else self.progress_fg
        cargo_bar_fill = tk.Frame(bar_frame, bg=bar_color)
        cargo_bar_fill.place(relwidth=bar_width_pct/100, relheight=1.0)
        
        # Delivered row with label and progress bar
        delivered_row = tk.Frame(inner, bg=self.accent_bg)
        delivered_row.pack(fill="x")
        
        delivered_label = tk.Label(
            delivered_row,
            text=f"Delivered: {delivered}/{count}t",
            bg=self.accent_bg,
            fg=self.delivered_fg,
            font=("Segoe UI", 8)
        )
        delivered_label.pack(side="left")
        
        # Delivered progress bar (thinner, green)
        delivered_bar_frame = tk.Frame(inner, bg=self.progress_bg, height=3)
        delivered_bar_frame.pack(fill="x", pady=(1, 3))
        delivered_bar_frame.pack_propagate(False)
        
        delivered_bar_pct = min(100, delivered_pct)
        delivered_bar_fill = tk.Frame(delivered_bar_frame, bg=self.delivered_fg)
        delivered_bar_fill.place(relwidth=delivered_bar_pct/100, relheight=1.0)
        
        # Row 2: Destination, Time, Reward - all on one line
        row2 = tk.Frame(inner, bg=self.accent_bg)
        row2.pack(fill="x")
        
        # Destination (compact)
        if destination_station and destination_system:
            dest_text = f"📍 {destination_station}"
        elif destination_station:
            dest_text = f"📍 {destination_station}"
        elif destination_system:
            dest_text = f"📍 {destination_system}"
        else:
            dest_text = ""
        
        if dest_text:
            tk.Label(
                row2,
                text=dest_text,
                bg=self.accent_bg,
                fg="#4a9eff",
                font=("Segoe UI", 8)
            ).pack(side="left")
        
        # Time remaining
        time_text = self._format_time_remaining(expiry)
        tk.Label(
            row2,
            text=time_text,
            bg=self.accent_bg,
            fg="#ff6666" if "Expired" in time_text else self.fg_dim,
            font=("Segoe UI", 8)
        ).pack(side="left", padx=(10, 0))
        
        # Reward (right side)
        if reward:
            reward_text = f"{reward:,.0f} CR"
            tk.Label(
                row2,
                text=reward_text,
                bg=self.accent_bg,
                fg="#ffcc00",
                font=("Segoe UI", 8, "bold")
            ).pack(side="right")
        
        # Store widget references for in-place updates
        if mission_id:
            self._mission_cards[mission_id] = {
                'card': card,
                'commodity_label': commodity_label,
                'cargo_bar_fill': cargo_bar_fill,
                'delivered_label': delivered_label,
                'delivered_bar_fill': delivered_bar_fill
            }
    
    def _format_time_remaining(self, expiry: str) -> str:
        """Format expiry time as time remaining"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        if not expiry:
            return t('mining_missions.no_deadline')
        try:
            expiry_dt = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            delta = expiry_dt - now
            
            if delta.total_seconds() < 0:
                return t('mining_missions.expired')
            
            days = delta.days
            hours = delta.seconds // 3600
            minutes = (delta.seconds % 3600) // 60
            
            if days > 0:
                return t('mining_missions.time_remaining_days', days=days, hours=hours)
            elif hours > 0:
                return t('mining_missions.time_remaining_hours', hours=hours, minutes=minutes)
            else:
                return t('mining_missions.time_remaining_minutes', minutes=minutes)
        except Exception:
            return t('mining_missions.unknown_time')
    
    def _find_hotspot(self, commodity: str):
        """Open Ring Finder with the commodity pre-selected and trigger search"""
        if self.ring_finder:
            try:
                # Set commodity in Ring Finder dropdown
                if hasattr(self.ring_finder, 'mineral_var'):
                    # Try to find matching material in the dropdown
                    if hasattr(self.ring_finder, 'mineral_dropdown'):
                        values = self.ring_finder.mineral_dropdown.cget('values')
                        commodity_lower = commodity.lower()
                        matched = False
                        for val in values:
                            if commodity_lower in val.lower() or val.lower() in commodity_lower:
                                self.ring_finder.mineral_var.set(val)
                                matched = True
                                break
                        if not matched:
                            self.ring_finder.mineral_var.set(commodity)
                    else:
                        self.ring_finder.mineral_var.set(commodity)
                
                # Switch to Ring Finder tab in the MAIN notebook
                if self.main_app and hasattr(self.main_app, 'notebook'):
                    nb = self.main_app.notebook
                    for i, tab_id in enumerate(nb.tabs()):
                        tab_text = nb.tab(tab_id, "text")
                        if "Hotspot" in tab_text or "Ring" in tab_text:
                            nb.select(i)
                            break
                
                # Trigger search after a short delay
                if hasattr(self.ring_finder, '_on_search'):
                    self.ring_finder.after(300, self.ring_finder._on_search)
                    
                print(f"[MISSIONS] Searching Ring Finder for: {commodity}")
            except Exception as e:
                print(f"[MISSIONS] Error opening Ring Finder: {e}")
                import traceback
                traceback.print_exc()
    
    def set_ring_finder(self, ring_finder):
        """Set the ring finder reference"""
        self.ring_finder = ring_finder
    
    def set_cargo_monitor(self, cargo_monitor):
        """Set the cargo monitor reference"""
        self.cargo_monitor = cargo_monitor
    
    def set_main_app(self, main_app):
        """Set the main app reference for tab switching"""
        self.main_app = main_app
    
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
        
        # Unbind mousewheel
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        
        super().destroy()
