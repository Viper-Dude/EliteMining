# -*- coding: utf-8 -*-
"""
Hotspot Finder Module for EliteMining
Provides mining hotspot location services with live API data integration
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import glob
import threading
import requests
import time
import zlib
from typing import Dict, List, Optional, Tuple
import math
import re
from core.constants import MENU_COLORS
from local_database import LocalSystemsDatabase
from user_database import UserDatabase
from edsm_integration import EDSMIntegration
# Localization
try:
    from localization import t, get_ring_types, get_abbr, get_material, to_english
except Exception:
    # Fallback stubs if localization not initialized
    def t(key, **kwargs):
        return key
    def get_ring_types():
        return {'All':'All','Metallic':'Metallic','Rocky':'Rocky','Icy':'Icy','Metal Rich':'Metal Rich'}
    def get_abbr(name):
        return name
    def get_material(name):
        return name
    def to_english(name):
        return name

# ToolTip class for showing helpful information
class ToolTip:
    tooltips_enabled = True
    _tooltip_instances = {}
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.tooltip_timer = None
        
        if widget in ToolTip._tooltip_instances:
            old_tooltip = ToolTip._tooltip_instances[widget]
            try:
                widget.unbind("<Enter>")
                widget.unbind("<Leave>")
                if old_tooltip.tooltip_timer:
                    widget.after_cancel(old_tooltip.tooltip_timer)
            except:
                pass
        
        ToolTip._tooltip_instances[widget] = self
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)

    def on_enter(self, event=None):
        if self.tooltip_window or not self.text or not ToolTip.tooltips_enabled:
            return
        
        if self.tooltip_timer:
            self.widget.after_cancel(self.tooltip_timer)
        
        self.tooltip_timer = self.widget.after(700, self._show_tooltip)

    def _show_tooltip(self):
        if self.tooltip_window or not self.text or not ToolTip.tooltips_enabled:
            return
            
        try:
            widget_x = self.widget.winfo_rootx()
            widget_y = self.widget.winfo_rooty()
            widget_height = self.widget.winfo_height()
            
            x = widget_x + 10
            y = widget_y + widget_height + 8

            self.tooltip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tw.wm_attributes("-topmost", True)
            tw.lift()
            
            label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                            font=("Segoe UI", "8"), wraplength=250,
                            padx=4, pady=2)
            label.pack()
            tw.update()
        except Exception as e:
            self.tooltip_window = None

    def on_leave(self, event=None):
        if self.tooltip_timer:
            self.widget.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
            
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# Ring finder module - searches for ring compositions in Elite Dangerous systems


class RingFinder:
    """Mining hotspot finder with EDDB API integration"""
    
    ALL_MINERALS = "All Minerals"  # Constant for "All Minerals" filter (internal key)
    
    def _is_all_minerals(self, value: str) -> bool:
        """Check if the given value represents 'All Minerals' (handles localized values)"""
        from localization import t
        return value == RingFinder.ALL_MINERALS or value == t('ring_finder.all_minerals')
    
    def _deselect_on_empty_click(self, event) -> None:
        """Deselect all items when clicking on empty space in the results treeview"""
        item = self.results_tree.identify_row(event.y)
        if not item:
            # Clicked on empty space - deselect all
            self.results_tree.selection_remove(*self.results_tree.selection())
    
    def __init__(self, parent_frame: ttk.Frame, prospector_panel=None, app_dir: Optional[str] = None, tooltip_class=None, distance_calculator=None, user_db=None):
        self.parent = parent_frame
        self.prospector_panel = prospector_panel  # Reference to get current system
        self.systems_data = {}  # System coordinates cache
        self.current_system_coords = None
        self.app_dir = app_dir  # Store app_dir for galaxy database access
        self.db_ready = False  # Track database initialization status
        self.distance_calculator = distance_calculator  # Distance calculator for Sol distance
        
        # Use main app's ToolTip class if provided, otherwise use local one
        global ToolTip
        if tooltip_class:
            ToolTip = tooltip_class
        
        # Prepare ring type localization maps (English <-> Localized)
        try:
            ring_map = get_ring_types()
        except Exception:
            ring_map = {'All':'All','Metallic':'Metallic','Rocky':'Rocky','Icy':'Icy','Metal Rich':'Metal Rich'}
        # Ensure deterministic order
        self._ring_type_order = ['All','Metallic','Rocky','Icy','Metal Rich']
        self._ring_type_map = {k: ring_map.get(k, k) for k in self._ring_type_order}
        # Reverse mapping localized->english
        self._ring_type_rev_map = {v:k for k,v in self._ring_type_map.items()}

        # Helper to map localized material display back to English
        self._to_english = to_english
        
        # Initialize local database manager
        self.local_db = LocalSystemsDatabase()
        
        # Initialize user database for hotspot data
        # If user_db is provided (from main app), reuse it to avoid duplicate initialization
        if user_db:
            self.user_db = user_db
            
            # Initialize EDSM integration with the shared database path
            self.edsm = EDSMIntegration(self.user_db.db_path)
        elif app_dir:
            # Use provided app directory to construct database path
            data_dir = os.path.join(app_dir, "data")
            db_path = os.path.join(data_dir, "user_data.db")
            self.user_db = UserDatabase(db_path)
            
            # Initialize EDSM integration for automatic metadata fallback
            self.edsm = EDSMIntegration(db_path)
        else:
            # Fall back to default path resolution
            self.user_db = UserDatabase()
            
            # Initialize EDSM integration with default path
            self.edsm = EDSMIntegration(self.user_db.db_path)
        
        # Verify database is accessible
        self._verify_database_ready()
        
        # Always use local database since it's now bundled with the application
        self.use_local_db = True
        
        # Auto-search monitoring variables
        self.last_monitored_system = None
        self.status_json_path = None
        
        # Track previous search results for highlighting new entries
        self.previous_results = set()  # Set of (system_name, body_name) tuples
        self.highlight_timer = None  # Timer for fade-out
        self.initial_load = True  # Skip highlighting on first search
        
        # Variables directory for persistence
        from app_utils import get_variables_dir
        self.vars_dir = get_variables_dir()
        
        self.setup_ui()
        
        # Setup status monitoring AFTER UI is created (auto_search_var exists)
        self._setup_status_monitoring()
        
        # Load initial data in background
        threading.Thread(target=self._preload_data, daemon=True).start()
        
        # Note: Auto-search is triggered from main.py at startup
        # Journal scan will refresh results when it completes
        
    def _abbreviate_material_for_display(self, hotspot_text: str) -> str:
        """Abbreviate material names in hotspot display text for Ring Finder column
        
        Uses centralized abbreviations from material_utils for consistency.
        Supports multiple languages based on game settings.
        """
        from material_utils import abbreviate_material_text
        return abbreviate_material_text(hotspot_text)
    
    def _localize_hotspot_display(self, text: str) -> str:
        """Localize material names in hotspot display text.
        
        Converts English material names to localized versions.
        Handles formats like 'Void Opals (1)' or 'Platinum (2), Painite (1)'
        """
        if not text or text == "-":
            return text
        import re
        # Pattern to match material name with optional count: "Material Name (X)" or just "Material Name"
        pattern = r'([A-Za-z][A-Za-z\s]+?)(\s*\(\d+\))?(?:,\s*|$)'
        
        def replace_material(match):
            material = match.group(1).strip()
            count = match.group(2) or ""
            localized = get_material(material)
            if localized == material:
                # Try abbreviation lookup for short forms
                localized = get_abbr(material)
                if localized == material:
                    return match.group(0)  # No translation found
            return f"{localized}{count}, " if match.group(0).endswith(", ") else f"{localized}{count}"
        
        result = re.sub(pattern, replace_material, text)
        return result.rstrip(", ")
        
    def setup_ui(self):
        """Create hotspot finder UI following EliteMining patterns"""
        # Configure parent frame to expand
        self.parent.grid_columnconfigure(0, weight=1)
        self.parent.grid_rowconfigure(0, weight=1)
        
        # Main container with scrollable frame
        canvas = tk.Canvas(self.parent, bg='#2b2b2b')
        scrollbar = ttk.Scrollbar(self.parent, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        # Configure scrollable frame to expand
        self.scrollable_frame.grid_columnconfigure(0, weight=1)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Bind canvas resize to make scrollable frame fill width
        canvas.bind('<Configure>', self._on_canvas_configure)
        
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Store canvas reference for resize handling
        self.canvas = canvas
        
        # Search section with database status
        search_header = ttk.Frame(self.scrollable_frame)
        search_header.pack(fill="x", padx=10, pady=5)
        
        # Search frame title and help text
        search_title = ttk.Label(search_header, text=t('ring_finder.title'), font=("Segoe UI", 9, "bold"))
        search_title.pack(side="left")
        
        # Database status on the right
        self.status_var = tk.StringVar(value="Loading...")
        status_label = ttk.Label(search_header, textvariable=self.status_var, 
                                font=("Segoe UI", 8), foreground="#888888")
        status_label.pack(side="right")
        
        # Distance info (below title on separate line) - label in white, values in yellow
        distance_header = ttk.Frame(self.scrollable_frame)
        distance_header.pack(fill="x", padx=10, pady=(0, 5))
        
        # Get theme colors
        from config import load_theme
        rf_theme = load_theme()
        rf_bg = "#0a0a0a" if rf_theme == "elite_orange" else "#1e1e1e"
        rf_value_fg = "#ffcc00"  # Yellow for values in both themes
        
        ttk.Label(distance_header, text=t('ring_finder.distances'), font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 5))
        
        self.distance_info_var = tk.StringVar(value="➤ Sol: --- | Home: --- | Fleet Carrier: ---")
        distance_info_label = tk.Label(distance_header, textvariable=self.distance_info_var,
                                font=("Segoe UI", 9), foreground=rf_value_fg, bg=rf_bg)
        distance_info_label.pack(side="left")
        
        # Database info on same line, right-aligned
        self.db_info_var = tk.StringVar(value=t('ring_finder.total_hotspots_in_systems').format(hotspots="...", systems="..."))
        db_info_label = tk.Label(distance_header, textvariable=self.db_info_var,
                                font=("Segoe UI", 8, "italic"), foreground="#888888", bg=rf_bg)
        db_info_label.pack(side="right")
        
        search_frame = ttk.Frame(self.scrollable_frame)
        search_frame.pack(fill="x", padx=10, pady=0)
        
        # Configure grid columns - prevent column 2 from expanding
        search_frame.grid_columnconfigure(0, weight=0)
        search_frame.grid_columnconfigure(1, weight=0)
        search_frame.grid_columnconfigure(2, weight=0)
        search_frame.grid_columnconfigure(3, weight=0)
        search_frame.grid_columnconfigure(4, weight=0)
        search_frame.grid_columnconfigure(5, weight=0)
        search_frame.grid_columnconfigure(6, weight=1)  # Let column 6 take remaining space
        
        # Single smart search input
        ttk.Label(search_frame, text=t('ring_finder.reference_system')).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.system_var = tk.StringVar()
        self.system_entry = ttk.Entry(search_frame, textvariable=self.system_var, width=35)
        self.system_entry.bind('<Return>', lambda e: self.search_hotspots())
        self.system_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        # Clear selection only on focus out to prevent unwanted text selection
        self.system_entry.bind('<FocusOut>', lambda e: self.system_entry.selection_clear())
        
        # For compatibility, current_system_var points to the same system_var
        self.current_system_var = self.system_var
        
        # Create frame for buttons (to pack them tightly)
        buttons_frame = ttk.Frame(search_frame)
        buttons_frame.grid(row=0, column=2, sticky="w", padx=(5, 0))
        
        # Auto-detect button (fills current system automatically) - with app color scheme
        auto_btn = tk.Button(buttons_frame, text=t('ring_finder.use_current_system'), command=self._auto_detect_system,
                            bg="#4a3a2a", fg="#e0e0e0", 
                            activebackground="#5a4a3a", activeforeground="#ffffff",
                            relief="ridge", bd=1, padx=8, pady=4,
                            font=("Segoe UI", 8, "normal"), cursor="hand2")
        auto_btn.pack(side="left", padx=(0, 5))
        
        # Search button - with app color scheme
        self.search_btn = tk.Button(buttons_frame, text=t('ring_finder.search'), command=self.search_hotspots,
                                   bg="#2a4a2a", fg="#e0e0e0", 
                                   activebackground="#3a5a3a", activeforeground="#ffffff",
                                   relief="ridge", bd=1, padx=15, pady=4,
                                   font=("Segoe UI", 8, "normal"), cursor="hand2")
        self.search_btn.pack(side="left", padx=(0, 5))

        # Auto-search checkbox
        self.auto_search_var = tk.BooleanVar(value=False)
        
        # Load saved auto-search state
        auto_search_enabled = self._load_auto_search_state()
        self.auto_search_var.set(auto_search_enabled)
        
        # Get theme for checkbox styling
        from config import load_theme
        _cb_theme = load_theme()
        if _cb_theme == "elite_orange":
            _cb_bg = "#000000"  # Black background for orange theme
            _cb_select = "#000000"
        else:
            _cb_bg = "#1e1e1e"
            _cb_select = "#1e1e1e"
        
        self.auto_search_cb = tk.Checkbutton(buttons_frame, text=t('ring_finder.auto_search'), 
                                           variable=self.auto_search_var,
                                           command=self._save_auto_search_state,
                                           bg=_cb_bg, fg="#e0e0e0", 
                                           activebackground="#2e2e2e", activeforeground="#ffffff",
                                           selectcolor=_cb_select, relief="flat",
                                           font=("Segoe UI", 8, "normal"))
        self.auto_search_cb.pack(side="left")
        
        # Tooltip for auto-search
        ToolTip(self.auto_search_cb, 
               "Automatically search for hotspots when arriving in a new system.\n"
               "Uses your last search settings (ring type, mineral, distance).\n"
               "Updates reference system from game status.")
        
        # Auto-switch tabs checkbox (synced with main app settings)
        self.auto_switch_tabs_var = tk.BooleanVar(value=False)
        
        # Load auto-switch tabs state from main app
        self._load_auto_switch_tabs_state()
        
        self.auto_switch_tabs_cb = tk.Checkbutton(buttons_frame, text=t('ring_finder.auto_switch_tabs'), 
                                           variable=self.auto_switch_tabs_var,
                                           command=self._on_auto_switch_tabs_toggle,
                                           bg=_cb_bg, fg="#e0e0e0", 
                                           activebackground="#2e2e2e", activeforeground="#ffffff",
                                           selectcolor=_cb_select, relief="flat",
                                           font=("Segoe UI", 8, "normal"))
        self.auto_switch_tabs_cb.pack(side="left", padx=(18, 0))
        
        # Tooltip for auto-switch tabs
        ToolTip(self.auto_switch_tabs_cb, t('ring_finder.auto_switch_tooltip'))

        # Ring Type filter
        ttk.Label(search_frame, text=t('ring_finder.ring_type')).grid(row=1, column=0, sticky="w", padx=5, pady=5)
        # Default to localized 'All'
        self.material_var = tk.StringVar(value=self._ring_type_map.get('All', 'All'))
        material_combo = ttk.Combobox(search_frame, textvariable=self.material_var, width=15, state="readonly")
        material_combo['values'] = tuple(self._ring_type_map[k] for k in self._ring_type_order)
        material_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # "Any Ring" checkbox - DISABLED (hidden) - searches Spansh for rings without requiring hotspot data
        self.any_ring_var = tk.BooleanVar(value=False)
        self.any_ring_cb = tk.Checkbutton(search_frame, text=t('ring_finder.any_ring'),
                                          variable=self.any_ring_var,
                                          command=self._on_any_ring_changed,
                                          bg=_cb_bg, fg="#e0e0e0",
                                          activebackground="#2e2e2e", activeforeground="#ffffff",
                                          selectcolor=_cb_select, relief="flat",
                                          font=("Segoe UI", 8, "normal"))
        # self.any_ring_cb.grid(row=1, column=1, sticky="e", padx=(130, 0), pady=5)  # Hidden - feature disabled
        # ToolTip(self.any_ring_cb, t('ring_finder.any_ring_tooltip'))
        
        # Material filter (new - specific materials) - dynamically populated from database
        ttk.Label(search_frame, text=t('ring_finder.mineral')).grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.specific_material_var = tk.StringVar(value=t('ring_finder.all_minerals'))
        self.specific_material_combo = ttk.Combobox(search_frame, textvariable=self.specific_material_var, width=22, state="readonly")
        
        # Get materials from database and sort alphabetically (localized display)
        available_materials = self._get_available_materials()
        self.specific_material_combo['values'] = available_materials
        self.specific_material_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Add tooltips for the filters
        ToolTip(material_combo, t('ring_finder.tooltip_ring_type'))
        ToolTip(self.specific_material_combo, t('ring_finder.tooltip_mineral'))
        
        # Create a sub-frame for right-side filters (row 1-2) that will pack tightly
        right_filters_frame_row1 = ttk.Frame(search_frame)
        right_filters_frame_row1.grid(row=1, column=2, columnspan=2, sticky="w", padx=(10, 0))
        
        right_filters_frame_row2 = ttk.Frame(search_frame)
        right_filters_frame_row2.grid(row=2, column=2, columnspan=2, sticky="w", padx=(10, 0))
        
        # Distance filter (now a dropdown) - in sub-frame with fixed label width
        ttk.Label(right_filters_frame_row1, text=t('ring_finder.max_distance') + ":", width=15, anchor="e").pack(side="left", padx=(0, 5))
        self.distance_var = tk.StringVar(value="50")
        self.distance_combo = ttk.Combobox(right_filters_frame_row1, textvariable=self.distance_var, width=8, state="readonly")
        self.distance_combo['values'] = ("10", "50", "100", "150", "200", "300")
        self.distance_combo.pack(side="left")
        
        # Overlaps Only checkbox - filters to show only overlap entries
        self.overlaps_only_var = tk.BooleanVar(value=False)
        self.overlaps_only_cb = tk.Checkbutton(right_filters_frame_row1, text=t('ring_finder.overlaps_only'),
                                               variable=self.overlaps_only_var,
                                               command=self._on_overlaps_only_changed,
                                               bg=_cb_bg, fg="#e0e0e0",
                                               activebackground="#2e2e2e", activeforeground="#ffffff",
                                               selectcolor=_cb_select, relief="flat",
                                               font=("Segoe UI", 8, "normal"))
        # Dynamic padding based on language (German text is shorter after abbreviation)
        from localization import get_language
        _overlaps_padx = (16, 0) if get_language() == 'de' else (26, 0)
        self.overlaps_only_cb.pack(side="left", padx=_overlaps_padx)
        ToolTip(self.overlaps_only_cb, t('ring_finder.tooltip_overlaps'))
        
        # RES Only checkbox - filters to show only RES site entries
        self.res_only_var = tk.BooleanVar(value=False)
        self.res_only_cb = tk.Checkbutton(right_filters_frame_row1, text=t('ring_finder.res_only'),
                                          variable=self.res_only_var,
                                          command=self._on_res_only_changed,
                                          bg=_cb_bg, fg="#e0e0e0",
                                          activebackground="#2e2e2e", activeforeground="#ffffff",
                                          selectcolor=_cb_select, relief="flat",
                                          font=("Segoe UI", 8, "normal"))
        _res_padx = (25, 0) if get_language() == 'de' else (10, 0)
        self.res_only_cb.pack(side="left", padx=_res_padx)
        ToolTip(self.res_only_cb, t('ring_finder.tooltip_res'))
        
        # Max Results filter - in sub-frame with fixed label width to align dropdowns
        ttk.Label(right_filters_frame_row2, text=t('ring_finder.max_results') + ":", width=15, anchor="e").pack(side="left", padx=(0, 5))
        self.max_results_var = tk.StringVar(value="30")
        max_results_combo = ttk.Combobox(right_filters_frame_row2, textvariable=self.max_results_var, width=8, state="readonly")
        max_results_combo['values'] = ("10", "20", "30", "50", "100", t('common.all'))
        max_results_combo.pack(side="left", padx=(0, 10))
        
        # Min Hotspots filter (only active for specific materials) - in sub-frame
        ttk.Label(right_filters_frame_row2, text=t('ring_finder.min_hotspots') + ":", width=12, anchor="e").pack(side="left", padx=(0, 5))
        self.min_hotspots_var = tk.IntVar(value=1)  # Changed to IntVar for spinbox
        self.min_hotspots_spinbox = ttk.Spinbox(right_filters_frame_row2, 
                                                 textvariable=self.min_hotspots_var, 
                                                 from_=1, 
                                                 to=20, 
                                                 width=6,
                                                 state="disabled",  # Start disabled (greyed out)
                                                 wrap=False,
                                                 command=lambda: None)  # Enable arrow clicks
        self.min_hotspots_spinbox.pack(side="left")
        ToolTip(self.min_hotspots_spinbox, t('tooltips.min_hotspots'))
        
        # NOW bind material selection to enable/disable min hotspots filter (after spinbox exists!)
        self.specific_material_combo.bind('<<ComboboxSelected>>', self._on_material_changed)
        
        # Confirmed hotspots only checkbox - DISABLED FOR TESTING
        # try:
        #     self.confirmed_only_var = tk.BooleanVar(value=False)
        #     self.confirmed_checkbox = tk.Checkbutton(search_frame, 
        #                                       text="Confirmed hotspots only",
        #                                       variable=self.confirmed_only_var,
        #                                       fg="#cccccc", bg="#1e1e1e", 
        #                                       selectcolor="#333333",
        #                                       activeforeground="#ffffff",
        #                                       activebackground="#1e1e1e")
        #     self.confirmed_checkbox.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)
        #     ToolTip(self.confirmed_checkbox, "Show only rings with confirmed mining hotspots\n(automatically enabled when material filter is used)")
        # except Exception as e:
        #     print(f"Error creating confirmed hotspots checkbox: {e}")
        #     # Create fallback variables
        self.confirmed_only_var = tk.BooleanVar(value=False)
        self.confirmed_checkbox = None
        
        # Initialize checkbox state based on default material selection (with error handling)
        try:
            self._on_material_changed()  # Use the unified callback
        except Exception as e:
            print(f"Warning: Failed to initialize material change handler: {e}")
        
        # Add tooltip for distance limitation
        ToolTip(self.distance_combo, t('tooltips.max_distance'))
        
        # Search limitations info text (bottom of search controls)
        info_text = tk.Label(search_frame, 
                            text=f"ℹ {t('ring_finder.search_help')}  |  {t('ring_finder.no_data_help')}",
                            fg="#cccccc", bg=_cb_bg, font=("Segoe UI", 8, "italic"), 
                            justify="left")
        info_text.grid(row=4, column=0, columnspan=4, sticky="w", padx=5, pady=(5, 5))
        
        # Results section with help text in header
        results_header = ttk.Frame(self.scrollable_frame)
        results_header.pack(fill="x", padx=10, pady=(2, 0))
        
        ttk.Label(results_header, text=t('ring_finder.search_results'), font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(results_header, text=t('ring_finder.right_click_help'), 
                 font=("Segoe UI", 8), foreground="#666666").pack(side="right", padx=(0, 5))
        
        results_frame = ttk.Frame(self.scrollable_frame)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(2, 2))
        
        # Create frame for treeview with scrollbars
        tree_frame = ttk.Frame(results_frame, relief="solid", borderwidth=1)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(5, 2))
        
        # Configure RingFinder Treeview style based on theme
        from config import load_theme
        current_theme = load_theme()
        style = ttk.Style()
        
        if current_theme == "elite_orange":
            tree_bg = "#1e1e1e"
            tree_fg = "#ff8c00"
            header_bg = "#1a1a1a"
            selection_bg = "#ff6600"
            selection_fg = "#000000"
        else:
            tree_bg = "#1e1e1e"
            tree_fg = "#e6e6e6"
            header_bg = "#2a2a2a"
            selection_bg = "#0078d7"
            selection_fg = "#ffffff"
        
        # Main treeview styling
        style.configure("RingFinder.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=tree_bg,
                       foreground=tree_fg,
                       fieldbackground=tree_bg)
        
        # Column header styling with borders
        style.configure("RingFinder.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",
                       background=header_bg,
                       foreground=tree_fg,
                       padding=[5, 5],
                       anchor="w")
        
        # Row selection styling
        style.map("RingFinder.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])
        
        # Combobox styling for orange theme - make arrow button visible
        if current_theme == "elite_orange":
            style.configure("TCombobox",
                           fieldbackground="#1e1e1e",
                           background="#4a3000",  # Dark orange for dropdown button
                           foreground="#ff8c00",
                           arrowcolor="#ff8c00")
            style.map("TCombobox",
                     fieldbackground=[('readonly', '#1e1e1e')],
                     background=[('readonly', '#4a3000')],
                     foreground=[('readonly', '#ff8c00')],
                     arrowcolor=[('readonly', '#ff8c00')])
            
            # Spinbox styling for orange theme - make arrow buttons visible
            style.configure("TSpinbox",
                           fieldbackground="#1e1e1e",
                           background="#4a3000",  # Dark orange for arrow buttons
                           foreground="#ff8c00",
                           arrowcolor="#ff8c00")
            style.map("TSpinbox",
                     fieldbackground=[('readonly', '#1e1e1e')],
                     background=[('readonly', '#4a3000')],
                     foreground=[('readonly', '#ff8c00')],
                     arrowcolor=[('readonly', '#ff8c00')])
        
        # Results treeview with enhanced columns including source
        columns = ("Distance", "LS", "System", "Visits", "Planet/Ring", "Ring Type", "Hotspots", "Overlap", "RES Site", "Density")
        self.results_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", style="RingFinder.Treeview")
        
        # Set column widths - similar to EDTOOLS layout
        column_widths = {
            "Distance": 60,
            "LS": 80,
            "System": 170,
            "Planet/Ring": 100,
            "Ring Type": 120,
            "Hotspots": 150,  # Reduced from 200 to 150
            "Overlap": 80,
            "RES Site": 80,
            "Visits": 60,
            "Density": 110
        }
        
        # Map internal column names to localized display names
        column_display_names = {
            "Distance": t('ring_finder.col_dist'),
            "LS": t('ring_finder.col_ls'),
            "System": t('ring_finder.col_system'),
            "Visits": t('ring_finder.col_visits'),
            "Planet/Ring": t('ring_finder.col_location'),
            "Ring Type": t('ring_finder.col_type'),
            "Hotspots": t('ring_finder.col_hotspots'),
            "Overlap": t('ring_finder.col_overlap'),
            "RES Site": t('ring_finder.col_res'),
            "Density": t('ring_finder.col_density')
        }
        
        for col in columns:
            # Left-align headers - use display name if mapped, otherwise use column name
            display_name = column_display_names.get(col, col)
            self.results_tree.heading(col, text=display_name, anchor="w", command=lambda c=col: self._sort_column(c, False))
            
            # Configure columns - all left-aligned for consistency
            if col == "Distance":
                self.results_tree.column(col, width=column_widths[col], minwidth=50, anchor="w", stretch=False)
            elif col == "System":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="w", stretch=False)
            elif col == "Planet/Ring":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="w", stretch=False)
            elif col == "Ring Type":
                self.results_tree.column(col, width=column_widths[col], minwidth=80, anchor="w", stretch=False)
            elif col == "Hotspots":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="w", stretch=False)
            elif col == "Overlap":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="w", stretch=False)
            elif col == "RES Site":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="w", stretch=False)
            elif col == "Visits":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="w", stretch=False)
            elif col == "LS":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="w", stretch=False)
            elif col == "Density":
                # Hide density column - data is unreliable
                self.results_tree.column(col, width=0, minwidth=0, anchor="w", stretch=False)
        
        # Load saved column widths from config
        try:
            from config import load_ring_finder_column_widths
            saved_widths = load_ring_finder_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    # Skip Density column - always hidden
                    if col_name == "Density":
                        continue
                    try:
                        self.results_tree.column(col_name, width=width)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Ring Finder column widths: {e}")

        # Bind column resize event to save widths
        def save_ring_finder_widths(event=None):
            try:
                from config import save_ring_finder_column_widths
                widths = {}
                for col in columns:
                    try:
                        widths[col] = self.results_tree.column(col, "width")
                    except:
                        pass
                save_ring_finder_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Ring Finder column widths: {e}")
        
        self.results_tree.bind("<ButtonRelease-1>", save_ring_finder_widths)
        # Deselect when clicking empty space
        self.results_tree.bind("<Button-1>", self._deselect_on_empty_click)
        
        # Configure row tags for alternating colors (theme-aware)
        if current_theme == "elite_orange":
            self.results_tree.tag_configure('oddrow', background='#1e1e1e', foreground='#ff8c00')
            self.results_tree.tag_configure('evenrow', background='#252525', foreground='#ff8c00')
        else:
            self.results_tree.tag_configure('oddrow', background='#1e1e1e', foreground='#e6e6e6')
            self.results_tree.tag_configure('evenrow', background='#282828', foreground='#e6e6e6')
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.results_tree.xview)
        self.results_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Grid layout for treeview and scrollbars
        self.results_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        
        # Configure style for the treeview to allow tag colors
        style = ttk.Style()
        style.map('Treeview', background=[('selected', '#4a4a4a')])  # Keep selection color
        
        # Configure tag for highlighting new entries with both background and foreground
        self.results_tree.tag_configure('new_entry', background='#4d7d4d', foreground='#ffffff')  # Light green with white text
        
        # Update database info immediately and schedule a delayed update (use parent window's after method)
        self._update_database_info()
        if hasattr(self.parent, 'after'):
            self.parent.after(100, self._update_database_info)
        
        # Store sort state
        self.sort_reverse = {}
        
        # Create context menu for results
        self._create_context_menu()
        
        # Bind right-click to show context menu
        self.results_tree.bind("<Button-3>", self._show_context_menu)
    
    def _sort_column(self, col, reverse):
        """Sort treeview column"""
        # Get all rows
        data = [(self.results_tree.set(child, col), child) for child in self.results_tree.get_children('')]
        
        # Sort data - handle numeric columns specially
        if col in ["Distance", "LS", "Density"]:
            # Numeric sort - handle N/A values
            def sort_key(item):
                val = item[0]
                if val == "No data" or val == "":
                    return float('inf') if not reverse else float('-inf')
                # Remove commas and convert to float
                try:
                    return float(val.replace(',', ''))
                except:
                    return float('inf') if not reverse else float('-inf')
            data.sort(key=sort_key, reverse=reverse)
        elif col == "Hotspots":
            # Hotspots column - extract number from formats like "Plat (2)" or "LTD (3), Plat (2)"
            import re
            def sort_key(item):
                val = item[0]
                if val == "No data" or val == "" or val == "-":
                    return float('inf') if not reverse else float('-inf')
                # Try to extract first number in parentheses
                match = re.search(r'\((\d+)\)', val)
                if match:
                    return int(match.group(1))
                # Fallback: try direct number parse
                try:
                    return float(val.replace(',', ''))
                except:
                    return float('inf') if not reverse else float('-inf')
            data.sort(key=sort_key, reverse=reverse)
        else:
            # String sort
            data.sort(key=lambda x: x[0].lower(), reverse=reverse)
        
        # Rearrange items in sorted order
        for index, (val, child) in enumerate(data):
            self.results_tree.move(child, '', index)
        
        # Update sort direction for next click
        self.sort_reverse[col] = not reverse
        
        # Update heading without sort indicators
        self.results_tree.heading(col, text=col, command=lambda: self._sort_column(col, self.sort_reverse[col]))
        
    def _update_database_info(self):
        """Update the database info label with total hotspots and systems count"""
        try:
            import sqlite3
            print(f"[DB INFO] Updating database info from: {self.user_db.db_path}")
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Count total hotspots (sum of all hotspot counts across all materials)
                cursor.execute("SELECT SUM(hotspot_count) FROM hotspot_data")
                total_hotspots = cursor.fetchone()[0] or 0
                
                # Count unique systems
                cursor.execute("SELECT COUNT(DISTINCT system_name) FROM hotspot_data")
                total_systems = cursor.fetchone()[0]
                
                # Format with thousand separators
                hotspots_str = f"{total_hotspots:,}"
                systems_str = f"{total_systems:,}"
                
                info_text = t('ring_finder.total_hotspots_in_systems').format(hotspots=hotspots_str, systems=systems_str)
                print(f"[DB INFO] Setting text: {info_text}")
                self.db_info_var.set(info_text)
        except Exception as e:
            print(f"[DB INFO] Error updating database info: {e}")
            import traceback
            traceback.print_exc()
            self.db_info_var.set(t('ring_finder.total_hotspots_in_systems').format(hotspots="...", systems="..."))
    
    def _on_canvas_configure(self, event):
        """Handle canvas resize to make scrollable frame fill canvas dimensions"""
        canvas_width = event.width
        canvas_height = event.height
        # Make scrollable frame fill entire canvas area
        self.canvas.itemconfig(self.canvas.find_all()[0], width=canvas_width, height=canvas_height)
    
    def _get_available_materials(self):
        """Get alphabetically sorted list of available materials from database"""
        from localization import t
        try:
            import sqlite3
            materials = [t('ring_finder.all_minerals')]  # Always start with localized "All Minerals"
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT material_name FROM hotspot_data")
                db_materials = cursor.fetchall()
                
                # Convert database materials to display names and collect them
                display_materials = set()  # Use set to automatically deduplicate
                for (material,) in db_materials:
                    display_name = self._format_material_for_display(material)
                    display_materials.add(display_name)
                
                # Convert to sorted list
                display_materials = sorted(display_materials)
                
                # Add sorted materials to the list
                materials.extend(display_materials)
            
            return tuple(materials)
            
        except Exception as e:
            print(f"Warning: Could not load materials from database: {e}")
            # Fallback to hardcoded sorted list
            from localization import t
            return (t('ring_finder.all_minerals'), "Alexandrite", "Benitoite", "Bromellite", "Grandidierite", 
                   "Low Temp.Diamonds", "Monazite", "Musgravite", "Painite", 
                   "Platinum", "Rhodplumsite", "Serendibite", "Tritium", "Void Opals")
    
    def _on_material_changed(self, event=None):
        """Enable/disable min hotspots filter AND update confirmed checkbox based on material selection"""
        selected_material = self.specific_material_var.get()
        
        print(f"[DEBUG] Material changed to: '{selected_material}'")
        
        if self._is_all_minerals(selected_material):
            # Disable min hotspots filter for "All Minerals" - disabled state prevents interaction
            self.min_hotspots_spinbox.configure(state="disabled")
            self.min_hotspots_var.set(1)  # Reset to default (IntVar)
            
            # Enable confirmed checkbox for user control
            if hasattr(self, 'confirmed_checkbox') and self.confirmed_checkbox:
                self.confirmed_checkbox.configure(state="normal", fg="#cccccc")
        else:
            # Enable for specific materials - normal state allows arrow clicks and typing
            self.min_hotspots_spinbox.configure(state="normal")
            
            # Material selected - force confirmed hotspots and disable checkbox
            if hasattr(self, 'confirmed_only_var'):
                self.confirmed_only_var.set(True)
            if hasattr(self, 'confirmed_checkbox') and self.confirmed_checkbox:
                self.confirmed_checkbox.configure(state="disabled", fg="#888888")
    
    def _on_any_ring_changed(self):
        """Handle Any Ring checkbox change - enables Spansh search mode"""
        if self.any_ring_var.get():
            # Any Ring mode - disable controls that don't apply to Spansh search
            self.specific_material_combo.configure(state="disabled")
            self.min_hotspots_spinbox.configure(state="disabled")
            self.distance_combo.configure(state="disabled")
            self.overlaps_only_cb.configure(state="disabled")
            self.res_only_cb.configure(state="disabled")
            # Uncheck overlaps/res checkboxes since they don't apply
            self.overlaps_only_var.set(False)
            self.res_only_var.set(False)
            # Make sure a specific ring type is selected (not "All")
            ring_type = self.material_var.get()
            ring_type_english = self._ring_type_rev_map.get(ring_type, ring_type)
            if ring_type_english == 'All':
                # Default to Icy if "All" is selected
                self.material_var.set(self._ring_type_map.get('Icy', 'Icy'))
            self.status_var.set(t('ring_finder.any_ring_mode'))
        else:
            # Normal mode - restore controls
            self.specific_material_combo.configure(state="readonly")
            self.distance_combo.configure(state="readonly")
            self.overlaps_only_cb.configure(state="normal")
            self.res_only_cb.configure(state="normal")
            self._on_material_changed()  # Restore min hotspots state
            self.status_var.set("")
    
    def _format_material_for_display(self, material_name: str) -> str:
        """Format material name for display in dropdown"""
        # Normalize database names to canonical English names first
        normalize_map = {
            'LowTemperatureDiamond': 'Low Temperature Diamonds',
            'Low Temp Diamonds': 'Low Temperature Diamonds',
            'Opal': 'Void Opals',
        }
        canonical_name = normalize_map.get(material_name, material_name)
        
        # Abbreviate long names for dropdown display
        if canonical_name == 'Low Temperature Diamonds':
            return 'Low Temp.Diamonds'
        
        # Get localized display name
        try:
            display_name = get_material(canonical_name)
        except Exception:
            display_name = canonical_name
        
        return display_name
    
    def _on_overlaps_only_changed(self):
        """Handle Overlaps Only checkbox change - disable RES Only if enabled"""
        if self.overlaps_only_var.get():
            self.res_only_var.set(False)
    
    def _on_res_only_changed(self):
        """Handle RES Only checkbox change - disable Overlaps Only if enabled"""
        if self.res_only_var.get():
            self.overlaps_only_var.set(False)
        
    def _preload_data(self):
        """Preload systems data in background"""
        try:
            # Check if parent window still exists
            if not self.parent.winfo_exists():
                return
            self.status_var.set(t('ring_finder.loading_database'))
            self._load_systems_cache()
            if self.parent.winfo_exists():
                self.parent.after(0, lambda: self.status_var.set(t('ring_finder.database_ready')) if self.parent.winfo_exists() else None)
        except Exception as ex:
            try:
                error_msg = str(ex)
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda msg=error_msg: self.status_var.set(f"Error loading database: {msg}") if self.parent.winfo_exists() else None)
            except:
                pass  # Window already destroyed
    
            
    def _update_sol_distance(self, system_name: str):
        """Update distance info label using centralized Distance Calculator"""
        try:
            # Get main app to access centralized distance info
            main_app = None
            if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, 'main_app'):
                main_app = self.prospector_panel.main_app
            
            if main_app and hasattr(main_app, 'get_distance_info_text'):
                # Use centralized distance info (already calculated in Distance Calculator tab)
                distance_text = main_app.get_distance_info_text()
                self.distance_info_var.set(distance_text)
            else:
                self.distance_info_var.set("➤ Sol: --- | Home: --- | Fleet Carrier: ---")
        except Exception as e:
            self.distance_info_var.set("➤ Sol: --- | Home: --- | Fleet Carrier: ---")
    
    def _auto_detect_system(self):
        """Auto-detect current system from Elite Dangerous journal"""
        try:
            # Get current system from main app (centralized source)
            current_system = None
            if self.prospector_panel and hasattr(self.prospector_panel, 'main_app'):
                main_app = self.prospector_panel.main_app
                if hasattr(main_app, 'get_current_system'):
                    current_system = main_app.get_current_system()
            
            # Fallback to prospector panel directly
            if not current_system and self.prospector_panel and hasattr(self.prospector_panel, 'last_system'):
                current_system = self.prospector_panel.last_system
            
            if current_system:
                self.current_system_var.set(current_system)
                self._update_sol_distance(current_system)
                self.status_var.set(t('ring_finder.current_system').format(system=current_system))
                # Check if coordinates exist in cache
                coords = self.systems_data.get(current_system.lower())
                if not coords:
                    self.status_var.set(t('ring_finder.coords_not_available').format(system=current_system))
                else:
                    self.status_var.set(t('ring_finder.current_system').format(system=current_system))
                return
            
            # Fallback: read directly from Status.json
            ed_folder = os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous")
            status_file = os.path.join(ed_folder, "Status.json")
            
            if os.path.exists(status_file):
                with open(status_file, 'r', encoding='utf-8') as f:
                    status_data = json.load(f)
                    if 'SystemName' in status_data:
                        system_name = status_data['SystemName']
                        self.current_system_var.set(system_name)
                        coords = self.systems_data.get(system_name.lower())
                        if not coords:
                            # EDSM disabled - only use galaxy database for coordinates  
                            # coords = self._get_system_coords_from_edsm(system_name)
                            if coords:
                                self.systems_data[system_name.lower()] = coords
                                self.status_var.set(t('ring_finder.current_system').format(system=system_name))
                            else:
                                self.status_var.set(t('ring_finder.coords_not_available').format(system=system_name))
                        else:
                            self.status_var.set(t('ring_finder.current_system').format(system=system_name))
                        return
            
            # Last resort: check latest journal file
            journal_files = glob.glob(os.path.join(ed_folder, "Journal.*.log"))
            if journal_files:
                latest_journal = max(journal_files, key=os.path.getmtime)
                system_name = self._get_system_from_journal(latest_journal)
                if system_name:
                    self.current_system_var.set(system_name)
                    self.status_var.set(t('ring_finder.current_system').format(system=system_name))
                    return
            
            self.status_var.set(t('ring_finder.could_not_detect_system'))
            
        except Exception as e:
            self.status_var.set(f"Auto-detect failed: {e}")
    
    def _get_system_from_journal(self, journal_path: str) -> Optional[str]:
        """Extract current system from journal file"""
        try:
            # Read last few lines to find most recent system
            with open(journal_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
            # Check last 50 lines for system events
            for line in reversed(lines[-50:]):
                try:
                    event = json.loads(line.strip())
                    if event.get('event') in ['FSDJump', 'Location', 'StartJump']:
                        if 'StarSystem' in event:
                            return event['StarSystem']
                except:
                    continue
                    
        except Exception as e:
            print(f"Error reading journal: {e}")
        
        return None
    
    def _verify_database_ready(self, max_retries=3):
        """Verify database is accessible with retry logic"""
        import time
        
        for attempt in range(max_retries):
            try:
                # Test database connection
                import sqlite3
                with sqlite3.connect(self.user_db.db_path, timeout=5.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM hotspot_data LIMIT 1")
                    cursor.fetchone()
                
                print(f"[OK] Database verification successful on attempt {attempt + 1}")
                self.db_ready = True
                return True
                
            except sqlite3.OperationalError as e:
                print(f"[WARN] Database not ready (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # Wait before retry
                else:
                    print(f"[ERROR] Database verification failed after {max_retries} attempts")
                    self.db_ready = False
                    return False
            except Exception as e:
                print(f"[ERROR] Unexpected database error: {e}")
                self.db_ready = False
                return False
    
    def _load_systems_cache(self):
        """Initialize empty systems cache for coordinate lookups"""
        # Start with empty cache - coordinates will be fetched from EDSM as needed
        self.systems_data = {}
        
        # Load saved filter settings
        self._load_filter_settings()
        
        # Add traces to save settings when they change
        self.material_var.trace_add('write', lambda *args: self._save_filter_settings())
        self.specific_material_var.trace_add('write', lambda *args: self._save_filter_settings())
        self.distance_var.trace_add('write', lambda *args: self._save_filter_settings())
        self.max_results_var.trace_add('write', lambda *args: self._save_filter_settings())
        self.min_hotspots_var.trace_add('write', lambda *args: self._save_filter_settings())
    
    def _on_material_change(self, event=None):
        """Update confirmed hotspots checkbox when material filter changes"""
        try:
            specific_material = self.specific_material_var.get()
            if not self._is_all_minerals(specific_material):
                # Material selected - force confirmed hotspots and disable checkbox
                self.confirmed_only_var.set(True)
                if self.confirmed_checkbox:
                    self.confirmed_checkbox.configure(state="disabled", fg="#888888")
            else:
                # All materials - enable checkbox for user control
                if self.confirmed_checkbox:
                    self.confirmed_checkbox.configure(state="normal", fg="#cccccc")
        except Exception as e:
            print(f"Warning: Material change handler error: {e}")
    
    def _hotspot_contains_material(self, result, specific_material):
        """Check if a hotspot result contains the requested specific material"""
        if not result.get('has_hotspots', False) or not result.get('hotspot_data'):
            return False
            
        hotspot_data = result.get('hotspot_data', {})
        
        # Check the formatted hotspot display for the material
        system_name = hotspot_data.get('systemName', '')
        body_name = hotspot_data.get('bodyName', '')
        
        if hasattr(self, 'user_db'):
            hotspot_display = self.user_db.format_hotspots_for_display(system_name, body_name)
            
            # Create material abbreviation mapping for checking
            material_abbrevs = {
                'Platinum': ['Pt'],
                'Low Temperature Diamonds': ['LTDs', 'LTD'],
                'Painite': ['Pai'],
                'Alexandrite': ['Alex', 'Al'],
                'Benitoite': ['Ben'],
                'Monazite': ['Mon'],
                'Musgravite': ['Mus'],
                'Serendibite': ['Ser'],
                'Rhodplumsite': ['Rhd'],
                'Bromellite': ['Brom'],
                'Tritium': ['Tri'],
                'Void Opals': ['VO'],
                'Grandidierite': ['Grand']
            }
            
            # Check if the specific material or its abbreviation appears in the hotspot display
            if specific_material in material_abbrevs:
                for abbrev in material_abbrevs[specific_material]:
                    if abbrev in hotspot_display:
                        print(f" DEBUG: Found '{specific_material}' (as {abbrev}) in hotspot: {hotspot_display}")
                        return True
            
            # Also check for full material name (case insensitive)
            if specific_material.lower() in hotspot_display.lower():
                print(f" DEBUG: Found '{specific_material}' (full name) in hotspot: {hotspot_display}")
                return True
                
            print(f" DEBUG: '{specific_material}' not found in hotspot: {hotspot_display}")
            print(f" DEBUG: Looking for abbreviations: {material_abbrevs.get(specific_material, [])} in: {hotspot_display}")
        
        return False
    
    def _save_filter_settings(self):
        """Save current filter settings to config"""
        try:
            from config import save_ring_finder_filters
            
            # Save canonical English identifiers to settings
            max_results_value = self.max_results_var.get()
            # Convert localized "Alle" back to English "All" for storage
            if max_results_value == t('common.all'):
                max_results_value = "All"
            
            settings = {
                "ring_type": self._ring_type_rev_map.get(self.material_var.get(), self.material_var.get()),
                "specific_material": self._to_english(self.specific_material_var.get()),
                "distance": self.distance_var.get(),
                "max_results": max_results_value,
                "min_hotspots": self.min_hotspots_var.get()
            }
            
            save_ring_finder_filters(settings)
            
        except Exception:
            pass
    
    def _load_filter_settings(self):
        """Load filter settings from config"""
        try:
            from config import load_ring_finder_filters
            
            settings = load_ring_finder_filters()
            if not settings:
                return
            
            # Restore settings (convert stored English identifiers to localized display)
            if "ring_type" in settings:
                self.material_var.set(self._ring_type_map.get(settings["ring_type"], settings["ring_type"]))
            if "specific_material" in settings:
                try:
                    # Convert stored canonical name to display format (e.g., "Low Temperature Diamonds" -> "Low Temp.Diamonds")
                    display_name = self._format_material_for_display(settings["specific_material"])
                    self.specific_material_var.set(display_name)
                except Exception:
                    self.specific_material_var.set(settings["specific_material"])
            if "distance" in settings:
                self.distance_var.set(settings["distance"])
            if "max_results" in settings:
                # Convert English "All" to localized version
                saved_max = settings["max_results"]
                if saved_max == "All":
                    self.max_results_var.set(t('common.all'))
                else:
                    self.max_results_var.set(saved_max)
            if "min_hotspots" in settings:
                self.min_hotspots_var.set(settings["min_hotspots"])
            
        except Exception:
            pass
    
    def _get_all_overlaps_for_search(self, reference_system: str, reference_coords: Dict, specific_material: str) -> List[Dict]:
        """Get all overlap entries for Overlaps Only mode (no distance filter)
        
        Args:
            reference_system: Current reference system name
            reference_coords: Reference system coordinates for distance calculation
            specific_material: Material filter (or "All Minerals")
            
        Returns:
            List of all overlap hotspot entries sorted by distance
        """
        import sqlite3
        import math
        
        try:
            overlaps = []
            coord_cache = {}  # Cache for galaxy database lookups
            seen_rings = set()  # Track which rings we've already added
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Query overlap entries
                if self._is_all_minerals(specific_material):
                    cursor.execute('''
                        SELECT system_name, body_name, material_name, overlap_tag,
                               ring_type, ls_distance, density, x_coord, y_coord, z_coord, hotspot_count
                        FROM hotspot_data 
                        WHERE overlap_tag IS NOT NULL
                    ''')
                else:
                    cursor.execute('''
                        SELECT system_name, body_name, material_name, overlap_tag,
                               ring_type, ls_distance, density, x_coord, y_coord, z_coord, hotspot_count
                        FROM hotspot_data 
                        WHERE overlap_tag IS NOT NULL AND material_name = ?
                    ''', (specific_material,))
                
                rows = cursor.fetchall()
            
            for row in rows:
                system_name, body_name, material_name, overlap_tag, ring_type, ls_distance, density, x, y, z, hotspot_count = row
                
                # Skip if we've already added this ring (avoid duplicates when multiple materials have overlaps)
                ring_key = (system_name, body_name)
                if ring_key in seen_rings:
                    continue
                seen_rings.add(ring_key)
                
                # Try to get coordinates if missing
                if x is None or y is None or z is None:
                    # Check cache first
                    if system_name in coord_cache:
                        coords = coord_cache[system_name]
                    else:
                        # Try galaxy database
                        coords = self._get_system_coords_from_galaxy_db(system_name)
                        coord_cache[system_name] = coords
                    
                    if coords:
                        x, y, z = coords['x'], coords['y'], coords['z']
                
                # Calculate distance
                distance = 999.9
                if reference_coords and x is not None and y is not None and z is not None:
                    distance = math.sqrt((x - reference_coords['x'])**2 + (y - reference_coords['y'])**2 + (z - reference_coords['z'])**2)
                    distance = round(distance, 1)
                
                # Format LS distance
                ls_display = "No data"
                if ls_distance is not None and ls_distance != 0:
                    try:
                        ls_display = f"{int(float(ls_distance)):,}"
                    except:
                        pass
                else:
                    # Try to get LS from another hotspot entry for the same ring
                    try:
                        with sqlite3.connect(self.user_db.db_path) as conn2:
                            cursor2 = conn2.cursor()
                            cursor2.execute('''
                                SELECT ls_distance FROM hotspot_data 
                                WHERE system_name = ? AND body_name = ? AND ls_distance IS NOT NULL AND ls_distance > 0
                                LIMIT 1
                            ''', (system_name, body_name))
                            result = cursor2.fetchone()
                            if result and result[0]:
                                ls_display = f"{int(float(result[0])):,}"
                    except:
                        pass
                
                # Get ALL hotspots for this ring and format them for display
                hotspots_display = self._get_ring_hotspots_display(system_name, body_name)
                
                overlaps.append({
                    'systemName': system_name,
                    'bodyName': body_name,
                    'type': hotspots_display,  # Use formatted hotspots display
                    'count': hotspot_count or 0,
                    'distance': distance,
                    'ring_type': ring_type or "No data",
                    'ls': ls_display,  # Display uses 'ls' key
                    'ls_distance': ls_distance,  # Keep raw value for EDSM compatibility
                    'density': density,
                    'data_source': 'Overlap Database',
                    'overlap_tag': overlap_tag
                })
            
            # Sort by distance
            overlaps.sort(key=lambda x: x.get('distance', 999.9))
            
            # Fill missing metadata (LS distance, ring type) using EDSM
            # Limit to first 30 systems to avoid slow searches
            if overlaps:
                try:
                    self._fill_missing_metadata_edsm(overlaps, max_systems=30)
                except Exception as e:
                    print(f" DEBUG: EDSM metadata fill failed: {e}")
            
            return overlaps
            
        except Exception as e:
            print(f"Error getting overlaps for search: {e}")
            return []
    
    def _get_ring_hotspots_display(self, system_name: str, body_name: str) -> str:
        """Get formatted hotspots display for a ring (e.g., 'Plat (3), Pain (2)')
        
        Args:
            system_name: Star system name
            body_name: Ring body name
            
        Returns:
            Formatted string of all hotspots in the ring
        """
        import sqlite3
        try:
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                # Get all materials for this ring, including those with count 0
                # Also check for res_tag or overlap_tag to know if it's a known hotspot
                cursor.execute('''
                    SELECT material_name, hotspot_count, res_tag, overlap_tag 
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ?
                    ORDER BY hotspot_count DESC, material_name
                ''', (system_name, body_name))
                rows = cursor.fetchall()
            
            if not rows:
                return "-"
            
            parts = []
            for material_name, count, res_tag, overlap_tag in rows:
                abbr = self._abbreviate_material_for_display(material_name)
                if count and count > 0:
                    parts.append(f"{abbr} ({count})")
                elif res_tag or overlap_tag:
                    # CSV-imported RES/Overlap entries - show (1) as minimum
                    parts.append(f"{abbr} (1)")
                else:
                    # Other entries without count - just show material
                    parts.append(abbr)
            
            return ", ".join(parts) if parts else "-"
            
        except Exception as e:
            print(f"Error getting ring hotspots display: {e}")
            return "-"
    
    def _get_all_res_for_search(self, reference_system: str, reference_coords: Dict, specific_material: str) -> List[Dict]:
        """Get all RES site entries for RES Only mode (no distance filter)
        
        Args:
            reference_system: Current reference system name
            reference_coords: Reference system coordinates for distance calculation
            specific_material: Material filter (or "All Minerals")
            
        Returns:
            List of all RES site hotspot entries sorted by distance
        """
        import sqlite3
        import math
        
        try:
            res_sites = []
            coord_cache = {}  # Cache for galaxy database lookups
            seen_rings = set()  # Track which rings we've already added
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Query RES entries
                if self._is_all_minerals(specific_material):
                    cursor.execute('''
                        SELECT system_name, body_name, material_name, res_tag, overlap_tag,
                               ring_type, ls_distance, density, x_coord, y_coord, z_coord, hotspot_count
                        FROM hotspot_data 
                        WHERE res_tag IS NOT NULL
                    ''')
                else:
                    cursor.execute('''
                        SELECT system_name, body_name, material_name, res_tag, overlap_tag,
                               ring_type, ls_distance, density, x_coord, y_coord, z_coord, hotspot_count
                        FROM hotspot_data 
                        WHERE res_tag IS NOT NULL AND material_name = ?
                    ''', (specific_material,))
                
                rows = cursor.fetchall()
            
            for row in rows:
                system_name, body_name, material_name, res_tag, overlap_tag, ring_type, ls_distance, density, x, y, z, hotspot_count = row
                
                # Skip if we've already added this ring (avoid duplicates when multiple materials have RES)
                ring_key = (system_name, body_name)
                if ring_key in seen_rings:
                    continue
                seen_rings.add(ring_key)
                
                # Try to get coordinates if missing
                if x is None or y is None or z is None:
                    # Check cache first
                    if system_name in coord_cache:
                        coords = coord_cache[system_name]
                    else:
                        # Try galaxy database
                        coords = self._get_system_coords_from_galaxy_db(system_name)
                        coord_cache[system_name] = coords
                    
                    if coords:
                        x, y, z = coords['x'], coords['y'], coords['z']
                
                # Calculate distance
                distance = 999.9
                if reference_coords and x is not None and y is not None and z is not None:
                    distance = math.sqrt((x - reference_coords['x'])**2 + (y - reference_coords['y'])**2 + (z - reference_coords['z'])**2)
                    distance = round(distance, 1)
                
                # Format LS distance
                ls_display = "No data"
                if ls_distance is not None and ls_distance != 0:
                    try:
                        ls_display = f"{int(float(ls_distance)):,}"
                    except:
                        pass
                else:
                    # Try to get LS from another hotspot entry for the same ring
                    try:
                        with sqlite3.connect(self.user_db.db_path) as conn2:
                            cursor2 = conn2.cursor()
                            cursor2.execute('''
                                SELECT ls_distance FROM hotspot_data 
                                WHERE system_name = ? AND body_name = ? AND ls_distance IS NOT NULL AND ls_distance > 0
                                LIMIT 1
                            ''', (system_name, body_name))
                            result = cursor2.fetchone()
                            if result and result[0]:
                                ls_display = f"{int(float(result[0])):,}"
                    except:
                        pass
                
                # Get ALL hotspots for this ring and format them for display
                hotspots_display = self._get_ring_hotspots_display(system_name, body_name)
                
                # Abbreviate RES tag for display
                res_display = self._abbreviate_res_tag(res_tag)
                
                res_sites.append({
                    'systemName': system_name,
                    'bodyName': body_name,
                    'type': hotspots_display,  # Use formatted hotspots display
                    'count': hotspot_count or 0,
                    'distance': distance,
                    'ring_type': ring_type or "No data",
                    'ls': ls_display,
                    'ls_distance': ls_distance,
                    'density': density,
                    'data_source': 'RES Database',
                    'overlap_tag': overlap_tag,
                    'res_tag': res_display
                })
            
            # Sort by distance
            res_sites.sort(key=lambda x: x.get('distance', 999.9))
            
            # Fill missing metadata using EDSM
            if res_sites:
                try:
                    self._fill_missing_metadata_edsm(res_sites, max_systems=30)
                except Exception as e:
                    print(f" DEBUG: EDSM metadata fill failed: {e}")
            
            return res_sites
            
        except Exception as e:
            print(f"Error getting RES sites for search: {e}")
            return []
    
    def _abbreviate_res_tag(self, res_tag: str) -> str:
        """Abbreviate RES tag for display
        
        Args:
            res_tag: Full RES type (Hazardous, High, Low)
            
        Returns:
            Abbreviated string (Haz, High, Low)
        """
        if not res_tag:
            return ""
        
        abbreviations = {
            'Hazardous': 'HAZ',
            'hazardous': 'HAZ',
            'High': 'High',
            'high': 'High',
            'Low': 'Low',
            'low': 'Low'
        }
        
        return abbreviations.get(res_tag, res_tag)
    
    def search_hotspots(self, auto_refresh=False, highlight_body=None, highlight_system=None):
        """Search for mining hotspots using reference system as center point
        
        Args:
            auto_refresh: DEPRECATED - use highlight_body instead
            highlight_body: Specific body/ring name to highlight (e.g., '1 A Ring')
            highlight_system: Specific system name for the body (e.g., 'Synuefe XR-H d11-45')
                           Only this exact system+ring will be highlighted green. None = no highlighting.
        """
        # Store highlight info for use in _update_results (accumulate multiple highlights)
        if not hasattr(self, '_pending_highlights'):
            self._pending_highlights = set()
        if highlight_body and highlight_system:
            self._pending_highlights.add((highlight_system.lower(), highlight_body))
        self._is_auto_refresh = auto_refresh  # Keep for backwards compatibility but prefer highlight_body
        
        reference_system = self.system_var.get().strip()
        
        # Update Sol distance for reference system
        self._update_sol_distance(reference_system)
        
        # Update Sol distance for reference system
        self._update_sol_distance(reference_system)
        
        # Map localized UI selections back to English identifiers for queries
        material_filter_local = self.material_var.get()
        material_filter = self._ring_type_rev_map.get(material_filter_local, material_filter_local)
        specific_material_local = self.specific_material_var.get()
        specific_material = self._to_english(specific_material_local)
        
        # Convert dropdown display names to database names for SQL query
        if specific_material == "Low Temp Diamonds":
            specific_material = "Low Temperature Diamonds"
        
        # Get confirmed_only with error handling
        try:
            confirmed_only = self.confirmed_only_var.get()
        except AttributeError:
            print("Warning: confirmed_only_var not found, defaulting to False")
            confirmed_only = False
            
        max_distance = float(self.distance_var.get() or "100")
        max_results_str = self.max_results_var.get()
        # Handle both English "All" and localized versions (e.g., "Alle" in German)
        max_results = None if max_results_str in ('All', t('common.all')) else int(max_results_str)
        
        # Auto-enable confirmed hotspots when filtering by specific material
        if not self._is_all_minerals(specific_material):
            confirmed_only = True

        if not reference_system:
            self.status_var.set(t('ring_finder.enter_reference_system'))
            return

        # Check if search criteria changed from last search and clear relevant cache
        current_search_key = f"{reference_system}_{material_filter}_{specific_material}_{max_distance}"
        if hasattr(self, '_last_search_key') and self._last_search_key != current_search_key:
            if hasattr(self, 'local_db'):
                # Clear cache entries for the previous search context
                old_system = self._last_search_key.split('_')[0] if hasattr(self, '_last_search_key') else None
                if old_system and old_system == reference_system:
                    # Same system, different criteria - clear material-specific cache
                    self.local_db.clear_cache(f"material_")
                    print(f" DEBUG: Cleared cache due to search criteria change")
        self._last_search_key = current_search_key

        # Set reference system coordinates for distance calculations (case insensitive)
        self.current_system_coords = None

        # Try exact match first
        self.current_system_coords = self.systems_data.get(reference_system.lower())
        if not self.current_system_coords:
            # Try partial match (case insensitive)
            for sys_name, sys_coords in self.systems_data.items():
                if reference_system.lower() in sys_name.lower():
                    self.current_system_coords = sys_coords
                    break

        if not self.current_system_coords:
            # Try to get coordinates from galaxy database first
            galaxy_coords = self._get_system_coords_from_galaxy_db(reference_system)
            if galaxy_coords:
                self.current_system_coords = galaxy_coords
                print(f" DEBUG: Using galaxy database coordinates for '{reference_system}'")
            else:
                # Try visited_systems table in user database
                try:
                    visited_coords = self.user_db._get_coordinates_from_visited_systems(reference_system)
                    if visited_coords:
                        # Convert tuple (x, y, z) to dict {'x': ..., 'y': ..., 'z': ...}
                        self.current_system_coords = {'x': visited_coords[0], 'y': visited_coords[1], 'z': visited_coords[2]}
                except Exception:
                    pass
                
                if not self.current_system_coords:
                    # Use EDSM as final fallback
                    edsm_coords = self._get_system_coords_from_edsm(reference_system)
                    if edsm_coords:
                        self.current_system_coords = edsm_coords

            if not self.current_system_coords:
                self.status_var.set(t('ring_finder.coords_not_found_warning').format(system=reference_system))

        # Get min hotspots filter (only valid for specific materials)
        min_hotspots = 1  # Default
        if not self._is_all_minerals(specific_material):
            try:
                min_hotspots = int(self.min_hotspots_var.get())
                if min_hotspots < 1:
                    min_hotspots = 1
            except (ValueError, AttributeError):
                min_hotspots = 1
        
        # Disable search button
        self.search_btn.configure(state="disabled", text=t('ring_finder.searching'))
        self.status_var.set(t('ring_finder.searching'))
        
        # Check if Any Ring mode is enabled
        any_ring_mode = self.any_ring_var.get()
        
        # For Any Ring mode, use a large fixed distance (dropdown is disabled)
        # Some regions of space have limited ring data, so use large radius
        if any_ring_mode:
            max_distance = 1000.0  # Fixed 1000 LY for Any Ring mode (covers sparse regions)

        # Run search in background - pass reference system coords and max results to worker
        threading.Thread(target=self._search_worker,
                        args=(reference_system, material_filter, specific_material, confirmed_only, max_distance, self.current_system_coords, max_results, min_hotspots, any_ring_mode),
                        daemon=True).start()
        
    def _search_worker(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, reference_coords, max_results, min_hotspots: int = 1, any_ring_mode: bool = False):
        """Background worker for hotspot search"""
        try:
            # Wait for database to be ready (with timeout)
            import time
            wait_start = time.time()
            while not self.db_ready and (time.time() - wait_start) < 5.0:
                time.sleep(0.1)
            
            if not self.db_ready:
                print("⚠ Database not ready, search may return incomplete results")
            
            # Check if window still exists before accessing tkinter vars
            if not self.parent.winfo_exists():
                return
            
            # Set the reference system coords for this worker thread
            self.current_system_coords = reference_coords
            
            # Any Ring mode: Search Spansh for rings of specific type (ignoring hotspot data)
            if any_ring_mode:
                # Use max_results if set, otherwise default to 150 for more results
                spansh_max = max_results if max_results else 150
                spansh_rings = self._search_spansh_rings(reference_system, material_filter, max_distance, spansh_max, reference_coords)
                print(f" DEBUG: Any Ring mode - found {len(spansh_rings)} rings from Spansh")
                # Convert Spansh rings to hotspot format using local database lookup
                hotspots = self._convert_spansh_to_hotspots(spansh_rings, reference_coords)
                print(f" DEBUG: Any Ring mode - converted to {len(hotspots)} hotspot entries")
            # Overlaps Only mode: Show only overlap entries (ignore distance)
            elif self.overlaps_only_var.get():
                hotspots = self._get_all_overlaps_for_search(reference_system, reference_coords, specific_material)
                print(f" DEBUG: Overlaps Only mode - found {len(hotspots)} overlap locations")
            # RES Only mode: Show only RES site entries (ignore distance)
            elif self.res_only_var.get():
                hotspots = self._get_all_res_for_search(reference_system, reference_coords, specific_material)
                print(f" DEBUG: RES Only mode - found {len(hotspots)} RES locations")
            else:
                hotspots = self._get_hotspots(reference_system, material_filter, specific_material, confirmed_only, max_distance, max_results)
            
            # Apply min hotspots filter if needed (skip for overlaps/RES only mode)
            if min_hotspots > 1 and not self._is_all_minerals(specific_material) and not self.overlaps_only_var.get() and not self.res_only_var.get():
                original_count = len(hotspots)
                hotspots = [h for h in hotspots if h.get('count', 1) >= min_hotspots]
                filtered_count = len(hotspots)
                if filtered_count < original_count:
                    print(f" DEBUG: Min hotspots filter ({min_hotspots}+): {original_count} -> {filtered_count} results")
            
            # Apply max_results limit AFTER min_hotspots filtering
            if max_results and len(hotspots) > max_results:
                hotspots = hotspots[:max_results]
            
            # EDSM FALLBACK: Smart throttling to prevent hanging
            # Small searches: Query all systems
            # Large searches: Query only first 30 systems for top results
            if hotspots and len(hotspots) < 100:
                self._fill_missing_metadata_edsm(hotspots)
            elif hotspots and len(hotspots) >= 100:
                self._fill_missing_metadata_edsm(hotspots, max_systems=30)
            
            # Update UI in main thread
            self.parent.after(0, self._update_results, hotspots)
            
        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            try:
                if self.parent.winfo_exists():
                    self.parent.after(0, self._show_error, error_msg)
            except:
                pass  # Window already destroyed
        finally:
            # Re-enable search button
            try:
                if self.parent.winfo_exists():
                    self.parent.after(0, lambda: self.search_btn.configure(state="normal", text=t('ring_finder.search')) if self.parent.winfo_exists() else None)
            except:
                pass  # Window already destroyed
    
    def _fill_missing_metadata_edsm(self, hotspots: List[Dict], max_systems: int = None):
        """
        Automatically fill missing ring metadata using EDSM fallback.
        
        This runs silently in background thread before displaying results.
        Only queries EDSM for systems that have incomplete rings in THIS result set.
        
        Args:
            hotspots: List of hotspot dicts to check and potentially update
            max_systems: Optional limit on number of systems to query (for large searches)
        """
        try:
            # Build set of systems with incomplete rings in THIS result set only
            systems_needing_data = set()
            for hotspot in hotspots:
                system_name = hotspot.get('systemName')
                ring_type = hotspot.get('ring_type')
                ls_distance = hotspot.get('ls_distance')
                
                # Normalize "No data" strings to None for comparison
                if ring_type == "No data":
                    ring_type = None
                if ls_distance == "No data" or ls_distance is None:
                    ls_distance = None
                
                if ring_type is None or ls_distance is None:
                    if system_name:
                        systems_needing_data.add(system_name)
            
            if not systems_needing_data:
                # All metadata complete in this result set
                return
            
            # Apply max_systems limit if specified (for large searches)
            systems_to_query = list(systems_needing_data)
            if max_systems and len(systems_to_query) > max_systems:
                systems_to_query = systems_to_query[:max_systems]
            
            print(f"[EDSM DEBUG] Systems to query: {systems_to_query}")
            
            # Use modified EDSM query that doesn't rely on get_incomplete_rings() filtering
            stats = self.edsm.fill_missing_metadata_for_systems_direct(systems_to_query)
            
            print(f"[EDSM DEBUG] EDSM query completed, stats: {stats}")
            
            if stats.get('materials_updated', 0) > 0:
                print(f"[EDSM] ✓ Filled {stats['rings_updated']} rings ({stats['materials_updated']} materials)")
                
                # Refresh hotspot data from database to get updated metadata
                print(f"[EDSM DEBUG] Refreshing hotspot metadata from database")
                self._refresh_hotspot_metadata_from_db(hotspots)
            else:
                print(f"[EDSM] ℹ No updates applied (rings may not exist in EDSM)")
                
        except Exception as e:
            # EDSM fallback failure is non-critical - just log and continue
            print(f"[EDSM] ⚠ Fallback failed (non-critical): {e}")
            print(f"[EDSM DEBUG] Exception details: {type(e).__name__}: {str(e)}")
    
    def _refresh_hotspot_metadata_from_db(self, hotspots: List[Dict]):
        """
        Refresh metadata for hotspots from database after EDSM update.
        
        Modifies hotspot dicts in-place to include updated metadata.
        """
        try:
            print(f"[EDSM DEBUG] _refresh_hotspot_metadata_from_db called for {len(hotspots)} hotspots")
            
            import sqlite3
            conn = sqlite3.connect(self.user_db.db_path)
            cursor = conn.cursor()
            
            updated_count = 0
            
            for hotspot in hotspots:
                system_name = hotspot.get('systemName')
                body_name = hotspot.get('bodyName')
                material_name = hotspot.get('type')
                
                if not all([system_name, body_name, material_name]):
                    continue
                
                # Query updated metadata for this specific hotspot
                cursor.execute("""
                    SELECT ring_type, ls_distance, inner_radius, outer_radius, ring_mass, density
                    FROM hotspot_data
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                    LIMIT 1
                """, (system_name, body_name, material_name))
                
                row = cursor.fetchone()
                if row:
                    # Store original values for comparison
                    old_ring_type = hotspot.get('ring_type')
                    old_ls_distance = hotspot.get('ls_distance')
                    
                    # Update hotspot dict with fresh metadata
                    hotspot['ring_type'] = row[0] if row[0] else hotspot.get('ring_type')
                    hotspot['ls_distance'] = row[1] if row[1] else hotspot.get('ls_distance')
                    
                    # Format LS distance for display (whole numbers with comma separators)
                    if row[1] is not None:
                        try:
                            hotspot['ls'] = f"{int(float(row[1])):,}"
                        except (ValueError, TypeError):
                            hotspot['ls'] = row[1]
                    else:
                        hotspot['ls'] = hotspot.get('ls')
                    
                    hotspot['inner_radius'] = row[2] if row[2] else hotspot.get('inner_radius')
                    hotspot['outer_radius'] = row[3] if row[3] else hotspot.get('outer_radius')
                    hotspot['ring_mass'] = row[4] if row[4] else hotspot.get('ring_mass')
                    hotspot['density'] = row[5] if row[5] else hotspot.get('density')
                    
                    # Check if anything actually changed
                    if (old_ring_type != hotspot.get('ring_type')) or (old_ls_distance != hotspot.get('ls_distance')):
                        updated_count += 1
                        print(f"[EDSM DEBUG] Updated {system_name} {body_name}: LS {old_ls_distance} -> {hotspot.get('ls_distance')}, Type {old_ring_type} -> {hotspot.get('ring_type')}")
            
            conn.close()
            
            print(f"[EDSM DEBUG] Metadata refresh completed: {updated_count} hotspots updated")
            
        except Exception as e:
            print(f"[EDSM] ⚠ Error refreshing metadata: {e}")
            print(f"[EDSM DEBUG] Refresh exception: {type(e).__name__}: {str(e)}")
    
    def _search_spansh_rings(self, reference_system: str, ring_type: str, max_distance: float, max_results: int, reference_coords) -> List[Dict]:
        """Search Spansh API for rings of a specific type (Any Ring mode)
        
        Args:
            reference_system: Name of reference system
            ring_type: Ring type filter (Icy, Rocky, Metallic, Metal Rich)
            max_distance: Maximum distance in light years
            max_results: Maximum number of results
            reference_coords: Reference system coordinates dict
            
        Returns:
            List of hotspot-format dicts for display in results table
        """
        import requests
        
        print(f"[SPANSH] Searching for {ring_type} rings within {max_distance}ly of {reference_system}")
        
        if not reference_coords:
            print("[SPANSH] No reference coordinates available")
            return []
        
        try:
            # Build Spansh API request
            # IMPORTANT: Do NOT use any filters - they all break the API
            # - 'rings' filter limits to ~25 bodies
            # - 'ring_type' filter doesn't actually filter
            # - 'distance' filter also limits to ~25 bodies
            # Instead: Get ALL bodies sorted by distance, filter client-side
            request_size = 5000  # Request max for best coverage
            payload = {
                'reference_system': reference_system,
                'size': request_size,
                'sort': [{'distance': {'direction': 'asc'}}],
                'filters': {}  # NO FILTERS - all done client-side
            }
            
            # Add full browser-like headers to avoid rate limiting
            # The sec-* headers are required for Spansh API to return full results
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Content-Type': 'application/json',
                'Origin': 'https://spansh.co.uk',
                'Referer': 'https://spansh.co.uk/bodies',
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin'
            }
            
            print(f"[SPANSH] Searching for {ring_type} rings within {max_distance}ly of {reference_system}")
            
            response = requests.post(
                'https://spansh.co.uk/api/bodies/search',
                json=payload,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            bodies = data.get('results', [])
            total_count = data.get('count', 0)
            print(f"[SPANSH] API returned {len(bodies)} bodies (total available: {total_count})")
            
            # Convert to hotspot format, filtering by ring type CLIENT-SIDE
            # Many bodies won't have rings or won't have the ring type we want
            results = []
            seen_rings = set()  # Avoid duplicate rings
            skipped_type = 0
            skipped_dup = 0
            skipped_no_rings = 0
            
            for body in bodies:
                system_name = body.get('system_name', '')
                body_name = body.get('name', '')
                distance = body.get('distance', 0)
                ls_distance = body.get('distance_to_arrival', 0)
                rings = body.get('rings', [])
                
                # Skip bodies beyond max distance (client-side filter)
                if distance > max_distance:
                    continue
                
                # Skip bodies without rings
                if not rings:
                    skipped_no_rings += 1
                    continue
                
                for ring in rings:
                    ring_type_actual = ring.get('type', '')
                    ring_name = ring.get('name', '')
                    
                    # Filter by ring type (skip if not matching, or if "All" is selected)
                    if ring_type != 'All' and ring_type_actual != ring_type:
                        skipped_type += 1
                        continue
                    
                    # Create unique key to avoid duplicates
                    ring_key = f"{system_name}|{ring_name}"
                    if ring_key in seen_rings:
                        skipped_dup += 1
                        continue
                    seen_rings.add(ring_key)
                    
                    # Get hotspot signals if available
                    signals = ring.get('signals', [])
                    hotspot_info = ""
                    hotspot_count = 0
                    if signals:
                        # Format as "Material (count), Material (count)" like normal search
                        signal_parts = []
                        for s in signals:
                            name = s.get('name', '')
                            count = s.get('count', 1)
                            hotspot_count += count
                            if name:
                                signal_parts.append(f"{name} ({count})")
                        # Show first 3 materials
                        hotspot_info = ", ".join(signal_parts[:3])
                        if len(signal_parts) > 3:
                            hotspot_info += f" +{len(signal_parts)-3}"
                    
                    # Format as hotspot result
                    result = {
                        'system': system_name,
                        'body': body_name,
                        'ring': ring_name,
                        'ring_type': ring_type_actual,
                        'distance': round(distance, 2),
                        'ls_distance': round(ls_distance, 2) if ls_distance else None,
                        'material': hotspot_info if hotspot_info else t('ring_finder.no_hotspot_data'),
                        'count': hotspot_count if hotspot_count else 0,
                        'overlap': '',
                        'res_site': '',
                        'density': '',
                        'source': 'spansh',
                        'data_source': 'spansh'
                    }
                    results.append(result)
                    
                    # Don't break early - collect all results, limit at the end
            
            # Sort by distance
            results.sort(key=lambda x: x.get('distance', 9999))
            
            bodies_with_rings = len(bodies) - skipped_no_rings
            print(f"[SPANSH] {len(bodies)} bodies checked, {bodies_with_rings} have rings, {skipped_no_rings} without rings")
            print(f"[SPANSH] Found {len(results)} {ring_type} rings (skipped {skipped_type} wrong type, {skipped_dup} duplicates)")
            print(f"[SPANSH] Returning first {max_results} results")
            return results[:max_results]
            
        except requests.exceptions.Timeout:
            print("[SPANSH] Request timed out")
            self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_timeout')))
            return []
        except requests.exceptions.RequestException as e:
            print(f"[SPANSH] API error: {e}")
            self.parent.after(0, lambda: self.status_var.set(t('ring_finder.spansh_error')))
            return []
        except Exception as e:
            print(f"[SPANSH] Unexpected error: {e}")
            return []

    def _convert_spansh_to_hotspots(self, spansh_rings: List[Dict], reference_coords) -> List[Dict]:
        """Convert Spansh ring results to the standard hotspot format used by user database searches
        
        This makes Spansh results go through the same display logic as normal searches,
        so Hotspots, Overlaps, RES, etc. columns are populated from the local database.
        
        Args:
            spansh_rings: List of ring results from Spansh API
            reference_coords: Reference system coordinates for distance calculation
            
        Returns:
            List of hotspot-format dicts compatible with _update_results
        """
        from material_utils import abbreviate_material
        
        results = []
        
        for ring in spansh_rings:
            system_name = ring.get('system', '')
            body_name = ring.get('body', '')
            ring_name = ring.get('ring', '')
            ring_type = ring.get('ring_type', 'No data')
            distance = ring.get('distance', 0)
            ls_distance = ring.get('ls_distance')
            
            if not system_name or not ring_name:
                continue
            
            # Format LS distance for display
            ls_display = "No data"
            if ls_distance is not None and ls_distance != "No data":
                try:
                    ls_display = f"{int(float(ls_distance)):,}"
                except (ValueError, TypeError):
                    ls_display = "No data"
            
            # Look up hotspots from local database for this ring
            hotspot_display = "-"
            hotspot_count = 0
            try:
                # Strip the system name prefix from ring_name to match database format
                # Spansh returns: "Antliae Sector IR-W c1-4 A 5 A Ring"
                # Database stores: "A 5 A Ring"
                db_ring_name = ring_name
                if ring_name.lower().startswith(system_name.lower()):
                    db_ring_name = ring_name[len(system_name):].strip()
                
                db_hotspots = self.user_db.get_body_hotspots(system_name, db_ring_name)
                if db_hotspots:
                    formatted_parts = []
                    for h in db_hotspots:
                        material = h.get('material_name', '')
                        count = h.get('hotspot_count', 1)
                        hotspot_count += count
                        if material:
                            abbrev = abbreviate_material(material)
                            formatted_parts.append(f"{abbrev} ({count})")
                    
                    if formatted_parts:
                        hotspot_display = ", ".join(formatted_parts[:4])
                        if len(formatted_parts) > 4:
                            hotspot_display += f" +{len(formatted_parts)-4}"
                        print(f"[SPANSH DB LOOKUP] Formatted: {hotspot_display}")
            except Exception as e:
                print(f"[SPANSH] Error looking up hotspots for {system_name} {ring_name}: {e}")
            
            # Create result in standard format (same as _search_user_database_first)
            result = {
                'system': system_name,
                'systemName': system_name,
                'body': body_name,
                'bodyName': ring_name,  # Use ring_name as bodyName for display
                'ring': ring_name,
                'ring_type': ring_type,
                'type': hotspot_display,  # This populates Hotspots column
                'ls': ls_display,
                'ls_distance': ls_distance,
                'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                'density': "No data",
                'has_hotspots': hotspot_count > 0,
                'count': hotspot_count,
                'data_source': 'Spansh',
                'source': 'Spansh'
            }
            results.append(result)
        
        return results

    def _get_hotspots(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, max_results: int = None) -> List[Dict]:
        """Get hotspot data using user database only - no EDSM dependencies"""
        # Use user database-only approach for all searches
        user_results = self._search_user_database_first(reference_system, material_filter, specific_material, max_distance, max_results)
        
        if user_results:
            return user_results
        else:
            return []
    
    def _search_user_database_first(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, max_results: int = None) -> List[Dict]:
        """Search user database first for confirmed hotspots, return results in _update_results compatible format"""
        try:
            # Get user database hotspots
            user_hotspots = self._get_user_database_hotspots(reference_system, material_filter, specific_material, max_distance)
            
            if not user_hotspots:
                return []
            
            # Convert user database format to _update_results compatible format
            compatible_results = []
            for hotspot in user_hotspots:
                system_name = hotspot.get('systemName', '')
                body_name = hotspot.get('bodyName', '')
                material_name = hotspot.get('type', '')  # User database uses 'type' field for material name
                hotspot_count = hotspot.get('count', 1)
                
                # Skip if specific material filter doesn't match
                if not self._is_all_minerals(specific_material) and not self._material_matches(specific_material, material_name):
                    continue
                
                # Get distance (already calculated in user_hotspots)
                distance = hotspot.get('distance', 0)
                ls_distance = hotspot.get('ls_distance', "No data")  # Use actual LS distance from database
                density = hotspot.get('density', "No data")  # Use actual density from database
                
                # Format LS distance properly for display with comma separators
                if ls_distance != "No data" and ls_distance is not None:
                    try:
                        ls_distance = f"{int(float(ls_distance)):,}"
                    except (ValueError, TypeError):
                        ls_distance = "No data"
                
                # Clean up the ring name using the existing method
                raw_ring_name = body_name
                clean_ring_name = self._clean_ring_name(raw_ring_name, body_name, system_name, source="user_database")
                
                # Debug: Check conversion for Delkar 7A entries
                if system_name == "Delkar" and "7 A" in body_name:
                    hotspot_ring_type = hotspot.get('ring_type', 'Missing')
                    hotspot_material = hotspot.get('type', 'Missing')
                    print(f"CONVERSION: {system_name} {body_name} -> material: {hotspot_material} | ring_type: {hotspot_ring_type}")
                
                # Create compatible result entry
                compatible_result = {
                    'system': system_name,
                    'systemName': system_name,
                    'body': body_name,
                    'bodyName': body_name,
                    'ring': clean_ring_name,  # Use cleaned ring name
                    'ring_type': hotspot.get('ring_type', 'No data') if hotspot.get('ring_type') not in [None, 'Unknown'] else 'No data',  # Clean ring_type from database
                    'type': material_name,  # Add the material name here
                    'ls': ls_distance,
                    'ls_distance': hotspot.get('ls_distance'),  # Add raw ls_distance for EDSM compatibility
                    'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                    'mass': "No data",  # User database doesn't store ring mass
                    'radius': "No data",  # User database doesn't store ring radius
                    'density': density,  # Include density from database
                    'inner_radius': hotspot.get('inner_radius'),  # Include inner radius from database
                    'outer_radius': hotspot.get('outer_radius'),  # Include outer radius from database
                    'has_hotspots': True,
                    'hotspot_data': hotspot,
                    'count': hotspot_count,
                    'data_source': 'User Database (Confirmed)',
                    'source': 'User Database'
                }
                compatible_results.append(compatible_result)
            
            # Sort by distance
            try:
                compatible_results.sort(key=lambda x: float(x.get('distance', 999)))
            except:
                pass
            
            # Don't apply max_results here - it will be applied AFTER min_hotspots filter in _search_worker
            
            return compatible_results
            
        except Exception:
            return []
    
    def _material_matches(self, target_material: str, hotspot_material: str) -> bool:
        """Check if hotspot material matches target material, handling abbreviations and display names"""
        if not target_material or not hotspot_material:
            return False
            
        target_lower = target_material.lower().strip()
        hotspot_lower = hotspot_material.lower().strip()
        
        # Direct match (most common case with our clean database)
        if target_lower == hotspot_lower:
            return True
            
        # Handle display name to database name mapping
        display_to_db_mapping = {
            'low temperature diamonds': 'lowtemperaturediamond',
            'low temp diamonds': 'lowtemperaturediamond',  # Dropdown shows this
            'void opals': 'opal'
        }
        
        # Convert display name to database name if needed
        if target_lower in display_to_db_mapping:
            target_lower = display_to_db_mapping[target_lower]
        if hotspot_lower in display_to_db_mapping:
            hotspot_lower = display_to_db_mapping[hotspot_lower]
        
        # Direct match after mapping
        if target_lower == hotspot_lower:
            return True
            
        # Material name mappings for backward compatibility and alternative names
        material_mappings = {
            # Standard materials from our database
            'alexandrite': ['alexandrite', 'alex'],
            'benitoite': ['benitoite', 'beni'],
            'bromellite': ['bromellite', 'brom', 'bromel'],
            'grandidierite': ['grandidierite', 'grand', 'grandi'],
            'lowtemperaturediamond': ['lowtemperaturediamond', 'ltd', 'ltds', 'low temperature diamonds', 'low temp diamonds', 'diamonds'],
            'monazite': ['monazite', 'mona'],
            'musgravite': ['musgravite', 'musg', 'musgravi'],
            'opal': ['opal', 'opals', 'void opals', 'void opal', 'vo'],
            'painite': ['painite', 'pain'],
            'platinum': ['platinum', 'pt', 'plat'],
            'rhodplumsite': ['rhodplumsite', 'rhod', 'rhodplum'],
            'serendibite': ['serendibite', 'seren', 'serendi'],
            'tritium': ['tritium', 't', 'tri'],
            # Legacy materials that might still be searched for
            'palladium': ['palladium', 'pd', 'pall'],
            'osmium': ['osmium', 'os'],
            'gold': ['gold', 'au']
        }
        
        # Check material mappings
        for standard_name, variants in material_mappings.items():
            # If target matches any variant of a material
            if target_lower in variants:
                # Check if hotspot material matches any variant of the same material
                if hotspot_lower in variants:
                    return True
                
        return False
    
    def _determine_ring_type_from_material(self, material_name: str) -> str:
        """DEPRECATED: Always return 'No data' to identify wrong code paths"""
        print(f"⚠️ WARNING: Fallback ring type function called for '{material_name}' - this should not happen!")
        return "Unknown"  # Force obvious identification
            
        material_lower = material_name.lower()
        
        # Ring type mapping based on our database materials
        metallic_materials = ['platinum', 'pt', 'palladium', 'pd', 'gold', 'au']
        icy_materials = ['lowtemperaturediamond', 'ltd', 'low temperature diamonds', 'diamonds', 'bromellite', 'tritium']
        rocky_materials = ['alexandrite', 'benitoite', 'grandidierite', 'monazite', 'musgravite', 'opal', 'opals', 'void opals', 'painite', 'rhodplumsite', 'serendibite']
        
        # Check material type
        if any(m in material_lower for m in metallic_materials):
            return "Metallic"
        elif any(m in material_lower for m in icy_materials):
            return "Icy"  
        elif any(m in material_lower for m in rocky_materials):
            return "Rocky"
        else:
            return "Rocky"  # Default for unknown materials from our database
        
    def _get_edsm_bodies_with_rings(self, system_name: str, material_filter: str, specific_material: str) -> List[Dict]:
        """Get bodies with rings from EDSM and show ring composition (not hotspots)"""
        try:
            url = f"https://www.edsm.net/api-system-v1/bodies"
            params = {
                'systemName': system_name
            }
            
            # Get API key from config
            try:
                from config import _load_cfg
                cfg = _load_cfg()
                api_key = cfg.get("edsm_api_key", "")
                if api_key:
                    params['apiKey'] = api_key
            except:
                pass
            
            print(f" DEBUG: Calling EDSM bodies API for '{system_name}': {url}")
            response = requests.get(url, params=params, timeout=10)
            print(f" DEBUG: EDSM bodies API status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f" DEBUG: EDSM bodies API returned {len(data.get('bodies', []))} bodies for '{system_name}'")
                mining_opportunities = []
                
                bodies_found = len(data.get('bodies', []))
                
                # Calculate distance if we have current system coordinates
                distance = 0
                if self.current_system_coords:
                    target_coords = self.systems_data.get(system_name.lower())
                    if target_coords:
                        distance = self._calculate_distance(self.current_system_coords, target_coords)
                
                # Define accurate ring type to material mapping based on game data
                ring_materials = {
                    'Icy': {
                        'primary': ['Low Temperature Diamonds', 'Bromellite', 'Tritium'],
                        'secondary': ['Water Ice']
                    },
                    'Metallic': {
                        'primary': ['Platinum', 'Palladium', 'Gold'],
                        'secondary': ['Silver', 'Bertrandite']
                    },
                    'Metal Rich': {
                        'primary': ['Platinum', 'Painite', 'Osmium'],
                        'secondary': ['Praseodymium', 'Samarium']
                    },
                    'Rocky': {
                        'primary': ['Alexandrite', 'Benitoite', 'Monazite'],
                        'secondary': ['Musgravite', 'Grandidierite', 'Serendibite', 'Rhodplumsite', 'Opal', 'Void Opals']
                    }
                }
                
                for body in data.get('bodies', []):
                    if body.get('rings'):
                        body_name = body.get('name', '')
                        distance_ls = body.get('distanceToArrival', 0)
                        
                        rings_found = len(body['rings'])
                        
                        for ring in body['rings']:
                            ring_type = ring.get('type', 'No data')
                            ring_name = ring.get('name', f"{body_name} Ring")
                            
                            # Get ring physical data
                            ring_mass = ring.get('mass', 0)
                            inner_radius = ring.get('innerRadius', 0)
                            outer_radius = ring.get('outerRadius', 0)
                            
                            # Format mass - EDSM API returns values that need 10^10 conversion to match website
                            if ring_mass > 0:
                                # EDSM API returns values ~10 billion times larger than website Earth Masses
                                # Convert to match EDSM website display
                                mass_in_em = ring_mass / 1e10  # Divide by 10 billion to match EDSM website
                                
                                # Format like EDSM website with decimal places
                                if mass_in_em >= 1000:  # >= 1000 EM
                                    # Show in thousands 
                                    mass_thousands = mass_in_em / 1000
                                    formatted = f"{mass_thousands:.1f}K"
                                elif mass_in_em >= 100:  # >= 100 EM
                                    # Show with 1 decimal place
                                    formatted = f"{mass_in_em:.1f}"
                                elif mass_in_em >= 10:  # >= 10 EM
                                    # Show with 2 decimal places
                                    formatted = f"{mass_in_em:.2f}"
                                else:
                                    # Show with 4 decimal places for small values
                                    formatted = f"{mass_in_em:.4f}"
                                
                                # Use comma as decimal separator (European format)
                                mass_display = formatted.replace(".", ",")
                                
                                # Debug output
                                print(f" DEBUG: Ring mass {ring_mass:.2e} API units = {mass_in_em:.4f} EM -> display: {mass_display}")
                            else:
                                mass_display = "No data"
                            
                            # Clean up ring name to show only essential part
                            clean_ring_name = self._clean_ring_name(ring_name, body_name, system_name, source="spreadsheet")
                            
                            # Get materials that can be found in this ring type
                            materials_in_ring = ring_materials.get(ring_type, {})
                            all_materials = materials_in_ring.get('primary', []) + materials_in_ring.get('secondary', [])
                            
                            # If material filter is specified, check if this ring type matches exactly
                            if material_filter != "All":
                                if material_filter != ring_type:
                                    continue
                                    
                            # If specific material is selected, check if this ring type can produce it
                            if not self._is_all_minerals(specific_material):
                                if specific_material not in all_materials:
                                    continue
                            
                            # Show primary materials for this ring type
                            materials_to_show = materials_in_ring.get('primary', ['No data'])
                            
                            # Create single entry for this ring
                            mining_opportunities.append({
                                'system': system_name,
                                'body': body_name,
                                'ring': clean_ring_name,
                                'ring_type': ring_type,
                                'ls': str(int(distance_ls)) if distance_ls > 0 else "No data",
                                'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                                'mass': mass_display,
                                'radius': f"{inner_radius:,} - {outer_radius:,}" if inner_radius > 0 and outer_radius > 0 else "No data",
                                'source': 'EDSM Ring Data'
                            })
                
                return mining_opportunities
                
        except Exception as e:
            pass
        
        return []

    def _get_nearby_systems(self, reference_system: str, max_distance: float, specific_material: str = "All Minerals") -> List[Dict]:
        """Get systems within specified distance from reference system using local database or EDSM APIs"""
        
        reference_coords = self.current_system_coords
        print(f" DEBUG: Reference system: {reference_system}")
        print(f" DEBUG: Reference coords: {reference_coords}")
        print(f" DEBUG: Max distance: {max_distance} ly")
        print(f" DEBUG: Using local database: {self.use_local_db}")
        print(f" DEBUG: Material filter: {specific_material}")
        
        # Try local database first if enabled and available
        if self.use_local_db and self.local_db.is_database_available() and reference_coords:
            try:
                print(f" DEBUG: Searching local database for systems within {max_distance} ly")
                # Create cache context that includes search criteria
                cache_context = f"material_{specific_material}"
                local_results = self.local_db.find_nearby_systems(
                    reference_coords['x'], 
                    reference_coords['y'], 
                    reference_coords['z'], 
                    max_distance, 
                    limit=500,
                    cache_context=cache_context
                )
                
                if local_results:
                    print(f" DEBUG: Local database found {len(local_results)} systems")
                    
                    # Check for specific test systems
                    test_systems = ["Coalsack Sector RI-T c3-22", "Coalsack Sector AQ-O b6-10"]
                    for test_system in test_systems:
                        found_in_results = any(s['name'].lower() == test_system.lower() for s in local_results)
                        print(f" DEBUG: Test system '{test_system}' found in results: {found_in_results}")
                        if found_in_results:
                            system_data = next(s for s in local_results if s['name'].lower() == test_system.lower())
                            print(f"  ðŸ“ Coordinates: ({system_data['coordinates']['x']:.2f}, {system_data['coordinates']['y']:.2f}, {system_data['coordinates']['z']:.2f})")
                            print(f"  ðŸ“ Distance: {system_data['distance']:.2f} LY")
                    
                    # Convert to expected format
                    nearby_systems = []
                    for system in local_results:
                        nearby_systems.append({
                            'name': system['name'],
                            'distance': system['distance'],
                            'coordinates': system['coordinates']
                        })
                    
                    print(f" DEBUG: Local database distance range: {nearby_systems[0]['distance']:.2f} - {nearby_systems[-1]['distance']:.2f} ly")
                    
                    # Log first few and last few systems for debugging
                    print(" DEBUG: First 3 systems:")
                    for i, system in enumerate(nearby_systems[:3]):
                        print(f"  {i+1}. {system['name']} ({system['distance']:.2f} LY)")
                    if len(nearby_systems) > 6:
                        print(" DEBUG: Last 3 systems:")
                        for i, system in enumerate(nearby_systems[-3:]):
                            print(f"  {len(nearby_systems)-2+i}. {system['name']} ({system['distance']:.2f} LY)")
                    
                    # ENHANCEMENT: Also search user database for visited systems with coordinates
                    print(" DEBUG: Searching user database for additional visited systems...")
                    try:
                        if hasattr(self, 'user_db') and self.user_db:
                            user_systems = self.user_db._get_nearby_visited_systems(
                                reference_coords['x'], 
                                reference_coords['y'], 
                                reference_coords['z'], 
                                max_distance,
                                exclude_system=reference_system
                            )
                            
                            if user_systems:
                                print(f" DEBUG: Found {len(user_systems)} additional systems from user database")
                                
                                # Merge user systems with galaxy systems, avoiding duplicates
                                existing_names = {s['name'].lower() for s in nearby_systems}
                                for user_system in user_systems:
                                    if user_system['name'].lower() not in existing_names:
                                        nearby_systems.append(user_system)
                                        print(f"  âž• Added: {user_system['name']} ({user_system['distance']:.2f} LY) from user DB")
                                
                                # Re-sort by distance after adding user systems
                                nearby_systems.sort(key=lambda x: x['distance'])
                                print(f" DEBUG: Combined database distance range: {nearby_systems[0]['distance']:.2f} - {nearby_systems[-1]['distance']:.2f} ly")
                            else:
                                print(" DEBUG: No additional systems found in user database")
                    except Exception as e:
                        print(f" DEBUG: Error searching user database: {e}")
                    
                    return nearby_systems
                else:
                    print(f" DEBUG: Local database returned no results")
            except Exception as e:
                print(f" DEBUG: Local database search failed: {e}")
                # Fall back to API search
                
        # Fallback to existing API-based search methods (Note: Local database is much more efficient)
        print(f" DEBUG: Falling back to API-based search methods (Recommend enabling local database for better results)")
        
        # Get API key from config first
        api_key = ""
        try:
            from config import _load_cfg
            cfg = _load_cfg()
            api_key = cfg.get("edsm_api_key", "")
            if api_key:
                print(f" DEBUG: Using EDSM API key from config")
            else:
                print(f" DEBUG: No EDSM API key configured")
        except Exception as e:
            print(f" DEBUG: Could not load API key from config: {e}")
            
        reference_coords = self.current_system_coords
        print(f" DEBUG: Reference system: {reference_system}")
        print(f" DEBUG: Reference coords: {reference_coords}")
        print(f" DEBUG: Max distance: {max_distance} ly")
            
        # Try EDSM cube-systems API first (more reliable than sphere-systems)
        try:
            url = "https://www.edsm.net/api-v1/cube-systems"
            
            # Use coordinates if available, otherwise use system name
            if reference_coords:
                params = {
                    "x": reference_coords['x'],
                    "y": reference_coords['y'],
                    "z": reference_coords['z'],
                    "size": min(max_distance * 2, 200),  # EDSM max is 200 ly, cube needs size not radius
                    "showCoordinates": 1
                }
                print(f" DEBUG: Using EDSM cube-systems with coordinates and size: {min(max_distance * 2, 200)} ly")
            else:
                params = {
                    "systemName": reference_system,
                    "size": min(max_distance * 2, 200),  # EDSM max is 200 ly
                    "showCoordinates": 1
                }
                print(f" DEBUG: Using EDSM cube-systems with system name: {reference_system}")
            
            if api_key:
                params["apiKey"] = api_key
            
            print(f" DEBUG: EDSM cube-systems API call: {url}")
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            print(f" DEBUG: EDSM cube-systems Response status: {response.status_code}")
            
            systems_data = response.json()
            print(f" DEBUG: EDSM cube-systems returned data type: {type(systems_data)}")
            
            if isinstance(systems_data, list) and len(systems_data) > 0:
                print(f" DEBUG: Found {len(systems_data)} systems near {reference_system} using cube-systems API")
                
                nearby_systems = []
                test_systems = ["Coalsack Sector RI-T c3-22", "Coalsack Sector AQ-O b6-10"]
                
                for system in systems_data:
                    if 'name' in system and 'coords' in system and reference_coords:
                        system_coords = system['coords']
                        distance = self._calculate_distance(reference_coords, system_coords)
                        
                        # Check for test systems in raw EDSM data
                        if any(test_sys.lower() in system['name'].lower() for test_sys in test_systems):
                            print(f" DEBUG: Found test system in EDSM data: '{system['name']}' at {distance:.2f} LY")
                            print(f"  ðŸ“ Coordinates: ({system_coords['x']:.2f}, {system_coords['y']:.2f}, {system_coords['z']:.2f})")
                            print(f"  âœ… Within max distance ({max_distance} LY): {distance <= max_distance}")
                            print(f"  âœ… Not reference system: {system['name'].lower() != reference_system.lower()}")
                        
                        # Filter by actual distance (cube returns systems in square, we want circle)
                        if distance <= max_distance:
                            # Exclude reference system by name
                            if system['name'].lower() != reference_system.lower():
                                nearby_systems.append({
                                    'name': system['name'],
                                    'distance': distance,
                                    'coordinates': system_coords
                                })
                
                # Check if test systems made it into final results
                for test_system in test_systems:
                    found_in_final = any(s['name'].lower() == test_system.lower() for s in nearby_systems)
                    print(f" DEBUG: Test system '{test_system}' in final API results: {found_in_final}")
                
                # Sort by distance
                nearby_systems.sort(key=lambda x: x['distance'])
                print(f" DEBUG: Processed {len(nearby_systems)} nearby systems within {max_distance} ly using cube-systems API")
                if nearby_systems:
                    print(f" DEBUG: Distance range: {nearby_systems[0]['distance']:.2f} - {nearby_systems[-1]['distance']:.2f} ly")
                return nearby_systems
                
            elif isinstance(systems_data, dict):
                if 'error' in systems_data:
                    print(f" DEBUG: EDSM cube-systems API error: {systems_data['error']}")
                elif len(systems_data) == 0:
                    print(f" DEBUG: EDSM cube-systems API returned empty dict (API may have changed or require different parameters)")
                else:
                    print(f" DEBUG: EDSM cube-systems returned unexpected dict format: {systems_data}")
            else:
                print(f" DEBUG: EDSM cube-systems returned unexpected format")
                
        except Exception as e:
            print(f" DEBUG: EDSM cube-systems API failed: {e}")
            
        # Try sector-based search as secondary fallback
        try:
            if reference_coords:
                print(f" DEBUG: Trying sector-based search for region near {reference_system}")
                
                # Common sector patterns in Elite Dangerous
                sector_patterns = [
                    "Col 285 Sector", "Hyades Sector", "Pleiades Sector", 
                    "HIP", "LHS", "Wolf", "Ross", "Gliese", "LP", "LTT",
                    "BD+", "BD-", "TYC", "2MASS", "WISE", "NLTT", 
                    "Synuefe", "Bleia", "Outotz", "Dryau", "Kyloall",
                    "Col 70 Sector", "Arietis Sector", "California Sector"
                ]
                
                sector_systems = []
                
                for pattern in sector_patterns:
                    try:
                        url = "https://www.edsm.net/api-v1/systems"
                        params = {
                            "systemName": pattern,
                            "showCoordinates": 1,
                            "onlyKnownCoordinates": 1
                        }
                        
                        if api_key:
                            params["apiKey"] = api_key
                        
                        response = requests.get(url, params=params, timeout=10)
                        if response.status_code == 200:
                            systems = response.json()
                            if isinstance(systems, list):
                                print(f" DEBUG: Found {len(systems)} systems matching '{pattern}'")
                                
                                for system in systems[:500]:  # Limit to first 500 to avoid timeout
                                    if 'coords' in system and 'name' in system:
                                        system_coords = system['coords']
                                        distance = self._calculate_distance(reference_coords, system_coords)
                                        
                                        if distance <= max_distance and system['name'].lower() != reference_system.lower():
                                            sector_systems.append({
                                                'name': system['name'],
                                                'distance': distance,
                                                'coordinates': system_coords
                                            })
                                            
                                            # Stop when we have enough nearby systems
                                            if len(sector_systems) >= 100:
                                                break
                                
                                if len(sector_systems) >= 50:  # Found enough systems, break out of pattern loop
                                    break
                                    
                    except Exception as pattern_error:
                        print(f" DEBUG: Pattern '{pattern}' search failed: {pattern_error}")
                        continue
                
                if sector_systems:
                    sector_systems.sort(key=lambda x: x['distance'])
                    print(f" DEBUG: Sector-based search found {len(sector_systems)} systems within {max_distance} ly")
                    if sector_systems:
                        print(f" DEBUG: Distance range: {sector_systems[0]['distance']:.2f} - {sector_systems[-1]['distance']:.2f} ly")
                    return sector_systems
                    
        except Exception as e:
            print(f" DEBUG: Sector-based search failed: {e}")
            
        # Final fallback: Use a curated list of known systems for popular mining areas
        print(f" DEBUG: Using fallback system list for nearby systems search")
        
        known_mining_systems = [
            "Sol", "Alpha Centauri", "Wolf 359", "Lalande 21185", "Sirius", "BV Phoenicis",
            "Ross 154", "Wolf 424", "Van Maanen's Star", "Wolf 46", "Gliese 65", "Procyon",
            "61 Cygni", "Struve 2398", "Groombridge 34", "Epsilon Eridani", "Lacaille 9352",
            "Altair", "70 Ophiuchi", "Arcturus", "Vega", "Fomalhaut", "Pollux", "Deneb",
            "Rigel", "Betelgeuse", "Aldebaran", "Spica", "Antares", "Canopus", "Achernar",
            "HIP 16613", "Delkar", "Borann", "Kirre's Icebox", "LTT 1935",
            "LHS 2936", "LFT 65", "Outotz LS-K d8-3", "Col 285 Sector CC-K a38-2",
            "HIP 21991", "LHS 417", "Wolf 1301", "Hip 8396", "LHS 1832", "Wolf 562",
            "Hyades Sector EB-X d1-112", "Col 285 Sector KS-T d3-43"
        ]
        
        # Filter systems based on distance if we have coordinates
        nearby_systems = []
        reference_coords = self.current_system_coords
        
        if reference_coords:
            print(f" DEBUG: Reference coords available: {reference_coords}")
            for sys_name in known_mining_systems:
                # Skip the reference system itself
                if sys_name.lower() == reference_system.lower():
                    continue
                    
                # Get coordinates for this system
                sys_coords = self.systems_data.get(sys_name.lower())
                if not sys_coords:
                    # Try to get from EDSM
                    sys_coords = self._get_system_coords_from_edsm(sys_name)
                    if sys_coords:
                        self.systems_data[sys_name.lower()] = sys_coords
                
                if sys_coords:
                    distance = self._calculate_distance(reference_coords, sys_coords)
                    # Only include systems within the specified distance
                    if distance <= max_distance:
                        nearby_systems.append({
                            'name': sys_name,
                            'distance': distance,
                            'coordinates': sys_coords
                        })
            
            # If no systems found within range, relax the distance requirement
            if not nearby_systems and max_distance < 200:
                print(f" DEBUG: No systems found within {max_distance} LY, expanding search to find closest systems")
                # Find the closest systems regardless of distance limit
                all_systems_with_distances = []
                for sys_name in known_mining_systems:
                    if sys_name.lower() == reference_system.lower():
                        continue
                    sys_coords = self.systems_data.get(sys_name.lower())
                    if not sys_coords:
                        sys_coords = self._get_system_coords_from_edsm(sys_name)
                        if sys_coords:
                            self.systems_data[sys_name.lower()] = sys_coords
                    
                    if sys_coords:
                        distance = self._calculate_distance(reference_coords, sys_coords)
                        all_systems_with_distances.append({
                            'name': sys_name,
                            'distance': distance,
                            'coordinates': sys_coords
                        })
                
                # Take the closest 10 systems as fallback
                if all_systems_with_distances:
                    all_systems_with_distances.sort(key=lambda x: x['distance'])
                    nearby_systems = all_systems_with_distances[:10]
                    print(f" DEBUG: Using {len(nearby_systems)} closest systems as fallback (range: {nearby_systems[0]['distance']:.1f} - {nearby_systems[-1]['distance']:.1f} LY)")
                        
            # Sort by distance
            nearby_systems.sort(key=lambda x: x['distance'])
            if nearby_systems:
                print(f" DEBUG: Fallback method found {len(nearby_systems)} systems within {max_distance} LY")
            else:
                print(f" DEBUG: Fallback method found {len(nearby_systems)} systems (expanded search)")
        else:
            # If no reference coordinates, return a reasonable subset of known systems
            print(f" DEBUG: No reference coordinates available, using nearby systems from popular mining areas")
            for sys_name in known_mining_systems[:30]:
                if sys_name.lower() != reference_system.lower():
                    nearby_systems.append({
                        'name': sys_name,
                        'distance': 0.0,  # Unknown distance
                        'coordinates': {'x': 0, 'y': 0, 'z': 0}
                    })
            print(f" DEBUG: Fallback method (no coords) returning {len(nearby_systems)} popular systems")
                
        return nearby_systems

    def _clean_ring_name(self, full_ring_name: str, body_name: str, system_name: str, source: str = None) -> str:
        """Preserve spreadsheet-imported and user database ring names; clean only for journal/API data."""
        try:
            # If source is spreadsheet import or user database, return the original name
            # These sources already have properly formatted ring names
            if source in ("spreadsheet", "user_database"):
                return full_ring_name
            # Otherwise, apply cleaning for journal/API data
            # ...existing cleaning logic...
            import re
            if system_name and full_ring_name.startswith(system_name):
                cleaned = full_ring_name[len(system_name):].strip()
            else:
                cleaned = full_ring_name
            pattern1 = r'(\d+\s+[A-Za-z]\s+Ring)'
            match1 = re.search(pattern1, cleaned)
            if match1:
                result = match1.group(1)
                parts = result.split()
                if len(parts) == 3:
                    return f"{parts[0]} {parts[1].upper()} {parts[2].title()}"
                return result
            pattern2 = r'([A-Za-z]+\s+\d+\s+Ring\s+[A-Za-z])'
            match2 = re.search(pattern2, cleaned)
            if match2:
                parts = match2.group(1).split()
                if len(parts) >= 4:
                    return f"{parts[1]} {parts[3].upper()} Ring"
            pattern3 = r'^[A-Za-z]\s+Ring$'
            if re.match(pattern3, cleaned.strip()):
                parts = cleaned.strip().split()
                return f"{parts[0].upper()} Ring"
            if "Ring" in cleaned:
                result = cleaned.strip()
                result = re.sub(r'\bring\b', 'Ring', result, flags=re.IGNORECASE)
                result = re.sub(r'\b([a-z])\s+Ring\b', lambda m: f"{m.group(1).upper()} Ring", result)
                return result
            else:
                body_num = "1"
                if body_name:
                    body_match = re.search(r'(\d+)', body_name)
                    if body_match:
                        body_num = body_match.group(1)
                return f"{body_num} A Ring"
        except Exception as e:
            print(f"Error cleaning ring name: {e}")
            return full_ring_name

    def _get_fallback_hotspots(self, search_term: str, material_filter: str) -> List[Dict]:
        """Search user database for hotspots when EDSM has no results"""
        print(f" DEBUG: Searching user database for {material_filter} hotspots")
        
        try:
            # Search user database for hotspots - no distance filtering needed
            import sqlite3
            user_hotspots = []
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Search for hotspots matching the material filter
                # Use subquery to get ring metadata from ANY material in same ring, then join with specific materials
                if self._is_all_minerals(material_filter):
                    cursor.execute('''
                        SELECT h.system_name, h.body_name, h.material_name, h.hotspot_count,
                               COALESCE(h.ring_type, m.ring_type) as ring_type,
                               COALESCE(h.ls_distance, m.ls_distance) as ls_distance,
                               COALESCE(h.density, m.density) as density,
                               COALESCE(h.inner_radius, m.inner_radius) as inner_radius,
                               COALESCE(h.outer_radius, m.outer_radius) as outer_radius
                        FROM hotspot_data h
                        LEFT JOIN (
                            SELECT system_name, body_name,
                                   MAX(ring_type) as ring_type, MAX(ls_distance) as ls_distance,
                                   MAX(density) as density, MAX(inner_radius) as inner_radius, MAX(outer_radius) as outer_radius
                            FROM hotspot_data
                            WHERE ring_type IS NOT NULL OR ls_distance IS NOT NULL
                            GROUP BY system_name, body_name
                        ) m ON h.system_name = m.system_name AND h.body_name = m.body_name
                        ORDER BY h.hotspot_count DESC, h.system_name, h.body_name
                    ''')
                else:
                    cursor.execute('''
                        SELECT h.system_name, h.body_name, h.material_name, h.hotspot_count,
                               COALESCE(h.ring_type, m.ring_type) as ring_type,
                               COALESCE(h.ls_distance, m.ls_distance) as ls_distance,
                               COALESCE(h.density, m.density) as density,
                               COALESCE(h.inner_radius, m.inner_radius) as inner_radius,
                               COALESCE(h.outer_radius, m.outer_radius) as outer_radius
                        FROM hotspot_data h
                        LEFT JOIN (
                            SELECT system_name, body_name,
                                   MAX(ring_type) as ring_type, MAX(ls_distance) as ls_distance,
                                   MAX(density) as density, MAX(inner_radius) as inner_radius, MAX(outer_radius) as outer_radius
                            FROM hotspot_data
                            WHERE ring_type IS NOT NULL OR ls_distance IS NOT NULL
                            GROUP BY system_name, body_name
                        ) m ON h.system_name = m.system_name AND h.body_name = m.body_name
                        WHERE h.material_name = ?
                        ORDER BY h.hotspot_count DESC, h.system_name, h.body_name
                    ''', (material_filter,))
                
                results = cursor.fetchall()
                print(f" DEBUG: Found {len(results)} hotspot entries in user database")
                
                # DEBUG: Print first few results to see what data we're getting
                if results:
                    print(f" DEBUG: First result sample:")
                    for i, row in enumerate(results[:3]):
                        print(f"   Row {i}: system={row[0]}, body={row[1]}, material={row[2]}, count={row[3]}, ring_type={row[4]}, ls={row[5]}, density={row[6]}")
                
                # Process each hotspot result
                for system_name, body_name, material_name, hotspot_count, ring_type_db, ls_distance, density, inner_radius, outer_radius in results:
                    try:
                        # Try to get coordinates for distance, but don't fail if unavailable
                        distance = 999.9  # Default for unknown distance
                        system_coords = None
                        
                        try:
                            system_coords = self._get_system_coords(system_name)
                            if system_coords and self.current_system_coords:
                                calculated_dist = self._calculate_distance(self.current_system_coords, system_coords)
                                if calculated_dist is not None:
                                    distance = round(calculated_dist, 1)
                        except:
                            # If coordinate lookup fails, use default distance
                            distance = 999.9
                        
                        # Convert to expected format (similar to EDSM results)
                        hotspot_entry = {
                            'systemName': system_name,
                            'bodyName': body_name,
                            'type': material_name,
                            'count': hotspot_count,
                            'distance': distance,
                            'coords': system_coords,
                            'data_source': 'EDTools.cc Community Data',
                            'ring_mass': 0,  # Default values for compatibility
                            'ring_type': ring_type_db if ring_type_db else 'No data',  # Use ring_type from database
                            'ls_distance': ls_distance,  # Include LS distance from database
                            'density': density,  # Include density from database
                            'inner_radius': inner_radius,  # Include inner radius from database
                            'outer_radius': outer_radius,  # Include outer radius from database
                            'debug_id': 'SECTION_1'  # Track which section created this entry
                        }
                        
                        user_hotspots.append(hotspot_entry)
                        
                    except Exception as e:
                        print(f" DEBUG: Error processing {system_name}: {e}")
                        continue
                
                # Sort by hotspot count first (best hotspots), then by distance
                user_hotspots.sort(key=lambda x: (-x['count'], x['distance']))
                
                # Limit to reasonable number of results
                max_user_results = 50
                if len(user_hotspots) > max_user_results:
                    user_hotspots = user_hotspots[:max_user_results]
                
                return user_hotspots
                
        except Exception:
            return []
    
    def _get_user_database_hotspots(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float) -> List[Dict]:
        """Search user database for hotspots - pure user database approach without EDSM"""
        try:
            import sqlite3
            user_hotspots = []
            
            # Cache for coordinates fetched from galaxy DB (prevent duplicate lookups in same search)
            coord_cache = {}
            # Track coordinates to save back to database
            coords_to_update = []
            
            # Get reference coordinates from multiple sources FIRST
            reference_coords = self.current_system_coords
            if not reference_coords and reference_system:
                # Try user database first - check visited_systems table (most reliable for current location)
                with sqlite3.connect(self.user_db.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                        SELECT x_coord, y_coord, z_coord 
                        FROM visited_systems 
                        WHERE system_name = ? AND x_coord IS NOT NULL
                        LIMIT 1
                    ''', (reference_system,))
                    ref_result = cursor.fetchone()
                    if ref_result:
                        reference_coords = {'x': ref_result[0], 'y': ref_result[1], 'z': ref_result[2]}
                        print(f" DEBUG: Found reference system {reference_system} in visited_systems table")
                    
                    # Fallback to hotspot_data table if not in visited_systems
                    if not ref_result:
                        cursor.execute('''
                            SELECT DISTINCT x_coord, y_coord, z_coord 
                            FROM hotspot_data 
                            WHERE system_name = ? AND x_coord IS NOT NULL
                            LIMIT 1
                        ''', (reference_system,))
                        ref_result = cursor.fetchone()
                        if ref_result:
                            reference_coords = {'x': ref_result[0], 'y': ref_result[1], 'z': ref_result[2]}
                            print(f" DEBUG: Found reference system {reference_system} in hotspot_data table")
                
                # Fallback to galaxy_systems.db for reference coordinates
                if not reference_coords:
                    reference_coords = self._get_system_coords_from_galaxy_db(reference_system)
                    if reference_coords:
                        print(f" DEBUG: Found reference system {reference_system} in galaxy database")
                    else:
                        # Final fallback: Try EDSM API (for systems not in galaxy DB, e.g., after carrier jump while offline)
                        print(f" DEBUG: Reference system {reference_system} not in galaxy database, trying EDSM API...")
                        reference_coords = self._get_system_coords_from_edsm(reference_system)
                        if reference_coords:
                            print(f" DEBUG: Found reference system {reference_system} coordinates from EDSM API")
                        else:
                            print(f" DEBUG: Reference system {reference_system} not found in any database or EDSM, will show all results without distance filtering")
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get systems within range for optimization if we have reference coordinates
                systems_in_range = None
                if reference_coords and max_distance < 1000:  # Only pre-filter for specific distance searches
                    systems_in_range = self._find_systems_in_range(reference_coords, max_distance)
                    
                    if systems_in_range is None:
                        systems_in_range = [reference_system]
                        print(f" DEBUG: No systems found in range, starting with reference system '{reference_system}'")
                    
                    if systems_in_range:
                        # PRIORITY FIX: Get all systems that have hotspots in the database
                        cursor.execute('''
                            SELECT DISTINCT system_name FROM hotspot_data
                        ''')
                        systems_with_hotspots = set(row[0] for row in cursor.fetchall())
                        
                        # Separate systems into priority (has hotspots) and non-priority
                        priority_systems = [s for s in systems_in_range if s in systems_with_hotspots]
                        non_priority_systems = [s for s in systems_in_range if s not in systems_with_hotspots]
                        
                        # Cap non-priority systems to prevent search hanging, but keep ALL priority systems
                        LIMIT = 5000
                        if len(priority_systems) + len(non_priority_systems) > LIMIT:
                            slots_remaining = max(0, LIMIT - len(priority_systems))
                            non_priority_systems = non_priority_systems[:slots_remaining]
                        
                        # Combine: priority systems first, then non-priority
                        systems_in_range = priority_systems + non_priority_systems
                        
                        # Always include reference system itself (distance = 0 LY)
                        if reference_system not in systems_in_range:
                            systems_in_range.append(reference_system)
                
                # Build optimized query based on whether we have a system filter
                if systems_in_range:
                    # SQLite has a limit of 999 variables per query, so batch if needed
                    BATCH_SIZE = 999
                    all_results = []
                    
                    for i in range(0, len(systems_in_range), BATCH_SIZE):
                        batch = systems_in_range[i:i + BATCH_SIZE]
                        placeholders = ','.join(['?'] * len(batch))
                        
                        # Different query for ALL_MINERALS vs specific material
                        if self._is_all_minerals(specific_material):
                            # Show ALL rings of this type (one row per ring, combining hotspot info)
                            query = f'''
                                SELECT system_name, body_name, 
                                       GROUP_CONCAT(material_name || ' (' || hotspot_count || ')', ', ') as material_name,
                                       1 as hotspot_count,
                                       MAX(x_coord) as x_coord, MAX(y_coord) as y_coord, MAX(z_coord) as z_coord, MAX(coord_source) as coord_source, 
                                       MAX(ls_distance) as ls_distance, MAX(density) as density, MAX(ring_type) as ring_type, 
                                       MAX(inner_radius) as inner_radius, MAX(outer_radius) as outer_radius
                                FROM hotspot_data
                                WHERE system_name IN ({placeholders})
                                GROUP BY system_name, body_name
                                ORDER BY system_name, body_name
                            '''
                            cursor.execute(query, batch)
                        else:
                            # Show only rings WITH this specific material - filter by material in SQL for efficiency
                            query = f'''
                                SELECT DISTINCT system_name, body_name, material_name, hotspot_count,
                                       x_coord, y_coord, z_coord, coord_source, ls_distance, density, ring_type, inner_radius, outer_radius
                                FROM hotspot_data
                                WHERE system_name IN ({placeholders}) AND material_name = ?
                                ORDER BY 
                                    hotspot_count DESC, system_name, body_name
                            '''
                            cursor.execute(query, batch + [specific_material])
                        all_results.extend(cursor.fetchall())
                    
                    # Use results from batched queries
                    results = all_results
                else:
                    # If no systems in range found, try direct system name search first
                    search_pattern = f"%{reference_system}%"
                    
                    # Different query for ALL_MINERALS vs specific material
                    if self._is_all_minerals(specific_material):
                        # Show ALL rings of this type (one row per ring)
                        direct_search_query = '''
                            SELECT system_name, body_name, 
                                   GROUP_CONCAT(material_name || ' (' || hotspot_count || ')', ', ') as material_name,
                                   1 as hotspot_count,
                                   MAX(x_coord) as x_coord, MAX(y_coord) as y_coord, MAX(z_coord) as z_coord, MAX(coord_source) as coord_source, 
                                   MAX(ls_distance) as ls_distance, MAX(density) as density, MAX(ring_type) as ring_type, 
                                   MAX(inner_radius) as inner_radius, MAX(outer_radius) as outer_radius
                            FROM hotspot_data
                            WHERE system_name LIKE ? OR system_name = ?
                            GROUP BY system_name, body_name
                            ORDER BY system_name, body_name
                            LIMIT 1000
                        '''
                        cursor.execute(direct_search_query, (search_pattern, reference_system))
                    else:
                        # Show only rings WITH this specific material - filter by material in SQL
                        direct_search_query = '''
                            SELECT DISTINCT system_name, body_name, material_name, hotspot_count,
                                   x_coord, y_coord, z_coord, coord_source, ls_distance, density, ring_type, inner_radius, outer_radius
                            FROM hotspot_data
                            WHERE (system_name LIKE ? OR system_name = ?) AND material_name = ?
                            ORDER BY 
                                hotspot_count DESC, system_name, body_name
                            LIMIT 1000
                        '''
                        cursor.execute(direct_search_query, (search_pattern, reference_system, specific_material))
                    direct_results = cursor.fetchall()
                    
                    if direct_results:
                        results = direct_results
                    else:
                        # Update status to show no results found
                        try:
                            self.status_label.config(text=f"No systems found within search criteria for '{reference_system}'. Try adjusting your search terms.")
                        except:
                            pass
                        return []
                
                material_matches = 0
                systems_with_coords = 0
                systems_without_coords = 0
                processed_count = 0
                max_process_limit = 10000  # Hard limit to prevent infinite processing
                
                for system_name, body_name, material_name, hotspot_count, x_coord, y_coord, z_coord, coord_source, ls_distance, density, ring_type_db, inner_radius, outer_radius in results:
                    try:
                        # Safety: Stop processing if we've hit the limit
                        processed_count += 1
                        if processed_count > max_process_limit:
                            print(f" DEBUG: Hit processing limit ({max_process_limit}) - stopping to prevent hang")
                            break
                        # Filter by specific material using our smart material matching
                        if not self._is_all_minerals(specific_material) and not self._material_matches(specific_material, material_name):
                            continue
                        
                        # Use ring type from database - no fallback needed
                        ring_type = ring_type_db if ring_type_db else "No data"
                        
                        # Normalize ring type spelling (handle typo in database)
                        if ring_type == "Metalic":
                            ring_type = "Metallic"
                        
                        # Filter by ring type (skip if ring_type is "No data" and filter is set)
                        if material_filter != "All":
                            if ring_type == "No data" or ring_type != material_filter:
                                continue
                        
                        material_matches += 1
                        
                        # Calculate distance if we have coordinates for both systems
                        distance = 999.9  # Default for unknown distance
                        coords_available = False
                        system_coords = None
                        
                        if (x_coord is not None and y_coord is not None and z_coord is not None):
                            # Use coordinates from user database
                            system_coords = {'x': x_coord, 'y': y_coord, 'z': z_coord}
                            coords_available = True
                            systems_with_coords += 1
                        else:
                            # Fallback to galaxy_systems.db for coordinates (with caching)
                            if system_name not in coord_cache:
                                galaxy_coords = self._get_system_coords_from_galaxy_db(system_name)
                                
                                # If not in galaxy DB, try EDSM as final fallback
                                if not galaxy_coords:
                                    edsm_coords = self._get_system_coords_from_edsm(system_name)
                                    if edsm_coords:
                                        galaxy_coords = edsm_coords
                                        print(f" DEBUG: Used EDSM coords for {system_name}")
                                
                                coord_cache[system_name] = galaxy_coords
                            else:
                                galaxy_coords = coord_cache[system_name]
                            
                            if galaxy_coords:
                                system_coords = galaxy_coords
                                coords_available = True
                                x_coord, y_coord, z_coord = galaxy_coords['x'], galaxy_coords['y'], galaxy_coords['z']
                                systems_with_coords += 1
                                # Track coordinates to save back to database
                                coords_to_update.append((x_coord, y_coord, z_coord, system_name))
                            else:
                                systems_without_coords += 1
                        
                        # Calculate distance if we have both reference and system coordinates
                        if reference_coords and coords_available:
                            calculated_distance = self._calculate_distance(reference_coords, system_coords)
                            # Ensure distance is never None
                            distance = calculated_distance if calculated_distance is not None else 999.9
                        elif not coords_available:
                            systems_without_coords += 1
                        
                        # Apply distance filtering if reference coordinates are available
                        if reference_coords and coords_available:
                            # Safety check: ensure distance is not None before comparison
                            if distance is None:
                                print(f" DEBUG: WARNING - distance is None for {system_name}, setting to 999.9")
                                distance = 999.9
                            # Apply distance filter for systems with coordinates
                            if distance > max_distance:
                                continue  # Skip systems beyond distance limit
                        elif reference_coords:
                            # If we have reference coords but this system doesn't have coords,
                            # only include it if we need more results or user wants unfiltered search
                            if max_distance < 1000:  # If user set a specific distance limit, skip systems without coords
                                continue
                        
                        # Include this system in results
                        source_label = f"EDTools.cc ({coord_source})" if coord_source else "EDTools.cc Community Data"
                        
                        # Abbreviate material names ONLY for "All Minerals" view
                        if self._is_all_minerals(specific_material):
                            display_material_name = self._abbreviate_material_for_display(material_name)
                        else:
                            display_material_name = material_name
                        
                        # Ensure distance is never None (safety check)
                        if distance is None or distance is False:
                            distance = 999.9
                        
                        # Format distance safely
                        try:
                            formatted_distance = round(distance, 1) if distance < 999 else 999.9
                        except (TypeError, ValueError):
                            formatted_distance = 999.9
                        
                        hotspot_entry = {
                            'systemName': system_name,
                            'bodyName': body_name,
                            'type': display_material_name,
                            'count': hotspot_count if hotspot_count is not None else 1,
                            'distance': formatted_distance,
                            'coords': {'x': x_coord, 'y': y_coord, 'z': z_coord} if x_coord is not None else None,
                            'data_source': source_label,
                            'ring_mass': 0,
                            'ring_type': ring_type,  # Use ring_type from database
                            'ls_distance': ls_distance,  # Include LS distance from database
                            'density': density,  # Include density from database
                            'inner_radius': inner_radius,  # Include inner radius from database
                            'outer_radius': outer_radius,  # Include outer radius from database
                            'debug_id': 'SECTION_2'  # Track which section created this entry
                        }
                        
                        user_hotspots.append(hotspot_entry)
                        
                    except Exception:
                        continue
                
                # CRITICAL FIX: Ensure ALL distances are valid numbers before sorting
                try:
                    for h in user_hotspots:
                        if h.get('distance') is None:
                            h['distance'] = 999.9
                except Exception:
                    pass
                
                # Sort by distance first, then LS distance for practical mining workflow
                if not self._is_all_minerals(material_filter):
                    # For specific materials, prioritize by hotspot count, then distance, then LS
                    user_hotspots.sort(key=lambda x: (-x.get('count', 0), x.get('distance') or 999.9, x.get('ls_distance') or 999999))
                else:
                    # For All Minerals, sort by distance, then LS distance (closest arrival points first)
                    user_hotspots.sort(key=lambda x: (x.get('distance') or 999.9, x.get('ls_distance') or 999999))
                
                # Batch-update database with fetched coordinates (save for future searches)
                if coords_to_update:
                    try:
                        print(f" DEBUG: Saving {len(coords_to_update)} coordinate lookups to database...")
                        cursor.executemany('''
                            UPDATE hotspot_data 
                            SET x_coord = ?, y_coord = ?, z_coord = ?, coord_source = 'galaxy_systems.db'
                            WHERE system_name = ? AND x_coord IS NULL
                        ''', coords_to_update)
                        conn.commit()
                    except Exception:
                        pass
                
                return user_hotspots
                
        except Exception:
            return []
    
    def _calculate_distance(self, coord1: Dict, coord2: Dict) -> float:
        """Calculate distance between two 3D coordinates in light years"""
        if not coord1 or not coord2:
            return 0.0
        
        dx = coord1['x'] - coord2['x']
        dy = coord1['y'] - coord2['y'] 
        dz = coord1['z'] - coord2['z']
        
        return math.sqrt(dx*dx + dy*dy + dz*dz)
    
    def _get_system_coords_from_galaxy_db(self, system_name: str) -> Optional[Dict]:
        """Get system coordinates from galaxy_systems.db with retry logic"""
        try:
            import sqlite3
            from pathlib import Path
            import time
            
            # Use bundled galaxy database
            script_dir = Path(self.app_dir) if self.app_dir else Path(__file__).parent
            galaxy_db_path = script_dir / "data" / "galaxy_systems.db"
            
            if not galaxy_db_path.exists():
                print(f" DEBUG: Galaxy database not found at {galaxy_db_path}")
                return None
            
            # Retry logic for database access (may be locked after restart)
            max_retries = 2
            for attempt in range(max_retries):
                try:
                    with sqlite3.connect(str(galaxy_db_path), timeout=5.0) as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT x, y, z FROM systems WHERE name = ? COLLATE NOCASE LIMIT 1", (system_name,))
                        result = cursor.fetchone()
                        
                        if result:
                            return {'x': result[0], 'y': result[1], 'z': result[2]}
                        return None  # System not found
                        
                except sqlite3.OperationalError as e:
                    if attempt < max_retries - 1:
                        print(f" DEBUG: Galaxy DB locked, retrying... (attempt {attempt + 1})")
                        time.sleep(0.3)
                    else:
                        print(f" DEBUG: Galaxy DB access failed after retries: {e}")
                        return None
                    
        except Exception as e:
            print(f" DEBUG: Error accessing galaxy database: {e}")
            
        return None
    
    def _find_systems_in_range(self, reference_coords: Dict, max_distance: float) -> List[str]:
        """Find all systems within range using galaxy_systems.db spatial index"""
        try:
            import sqlite3
            from pathlib import Path
            
            # Use bundled galaxy database
            script_dir = Path(self.app_dir) if self.app_dir else Path(__file__).parent
            galaxy_db_path = script_dir / "data" / "galaxy_systems.db"
            
            if not galaxy_db_path.exists():
                return []
                
            systems_in_range = []
            
            with sqlite3.connect(str(galaxy_db_path)) as conn:
                cursor = conn.cursor()
                
                # Use spatial index for efficient range queries
                # Create bounding box for spatial search
                x_min = reference_coords['x'] - max_distance
                x_max = reference_coords['x'] + max_distance
                y_min = reference_coords['y'] - max_distance
                y_max = reference_coords['y'] + max_distance
                z_min = reference_coords['z'] - max_distance
                z_max = reference_coords['z'] + max_distance
                
                # Add LIMIT to prevent query timeout on large searches
                cursor.execute("""
                    SELECT name, x, y, z FROM systems 
                    WHERE x BETWEEN ? AND ? 
                    AND y BETWEEN ? AND ? 
                    AND z BETWEEN ? AND ?
                    LIMIT 50000
                """, (x_min, x_max, y_min, y_max, z_min, z_max))
                
                results = cursor.fetchall()
                
                # Calculate actual distance and filter - store as (name, distance) tuples
                systems_with_distances = []
                for name, x, y, z in results:
                    system_coords = {'x': x, 'y': y, 'z': z}
                    distance = self._calculate_distance(reference_coords, system_coords)
                    
                    if distance <= max_distance:
                        systems_with_distances.append((name, distance))
                
                # Sort by distance (closest first) before converting to name-only list
                systems_with_distances.sort(key=lambda x: x[1])
                systems_in_range = [name for name, dist in systems_with_distances]
                
                # Also check user database for visited systems within range
                try:
                    with sqlite3.connect(self.user_db.db_path) as user_conn:
                        user_cursor = user_conn.cursor()
                        
                        # Get all visited systems with coordinates
                        user_cursor.execute("""
                            SELECT system_name, x_coord, y_coord, z_coord 
                            FROM visited_systems
                            WHERE x_coord IS NOT NULL
                        """)
                        
                        user_systems_in_range = 0
                        for system_name, x, y, z in user_cursor.fetchall():
                            system_coords = {'x': x, 'y': y, 'z': z}
                            distance = self._calculate_distance(reference_coords, system_coords)
                            
                            if distance <= max_distance and system_name not in systems_in_range:
                                systems_in_range.append(system_name)
                                user_systems_in_range += 1
                            
                except Exception:
                    pass
                
                return systems_in_range
                        
        except Exception:
            pass
            
        return []
        
    def _get_system_coords_from_edsm(self, system_name: str) -> Optional[Dict]:
        """Get system coordinates from EDSM API as fallback"""
        try:
            # Use ChatGPT's recommended endpoint - api-v1/systems (plural)
            url = "https://www.edsm.net/api-v1/systems"
            params = {
                "systemName": system_name,
                "showCoordinates": 1
            }
            
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # EDSM returns a list, take the first match
                if data and len(data) > 0:
                    sys_info = data[0]
                    if 'coords' in sys_info:
                        coords = {
                            'name': sys_info.get('name', system_name),
                            'x': sys_info['coords']['x'],
                            'y': sys_info['coords']['y'],
                            'z': sys_info['coords']['z']
                        }
                        # Cache it in our local systems data for future use
                        self.systems_data[system_name.lower()] = coords
                        print(f" DEBUG: Successfully got coordinates from EDSM for '{system_name}': {coords}")
                        return coords
                    else:
                        print(f" DEBUG: No coordinates in EDSM response for '{system_name}'")
                else:
                    print(f" DEBUG: System '{system_name}' not found in EDSM - may be incomplete name or not discovered yet")
                    
        except Exception as e:
            print(f" DEBUG: Failed to get coordinates from EDSM: {e}")
            
        return None
        
    def _update_results(self, hotspots: List[Dict]):
        """Update results treeview with hotspot data"""
        # Track current results to identify new entries
        current_results = set()
        for hotspot in hotspots:
            system_name = hotspot.get("systemName", hotspot.get("system", ""))
            body_name = hotspot.get("bodyName", hotspot.get("body", ""))
            current_results.add((system_name, body_name))
        
        # Identify entries to highlight - support multiple scanned rings
        pending_highlights = getattr(self, '_pending_highlights', set())
        
        # Only reset pending highlights if this is a manual search (no new highlights being added)
        # This allows accumulating highlights when scanning multiple rings
        is_auto_scan = len(pending_highlights) > 0
        
        # Get or create sets for tracking highlights
        if not hasattr(self, '_active_highlights'):
            self._active_highlights = set()  # Rings that stay at top (position only)
        if not hasattr(self, '_green_highlights'):
            self._green_highlights = set()  # Rings that are currently green
        
        # If this is an auto-scan (has pending highlights), add them to active and green
        # If this is a manual search (no pending), clear everything
        if is_auto_scan:
            self._active_highlights.update(pending_highlights)
            self._green_highlights.update(pending_highlights)  # New scans get green
            self._pending_highlights = set()  # Clear pending after moving
        else:
            self._active_highlights = set()  # Manual search clears all
            self._green_highlights = set()
        
        self._is_auto_refresh = False  # Reset legacy flag
        
        # Build sets for position (top) and green highlighting
        top_entries = set()  # Entries that go to top
        green_entries = set()  # Entries that are green
        
        for highlight_system, highlight_body in self._active_highlights:
            # Normalize highlight_body to match database format (without system prefix)
            normalized_highlight = highlight_body
            if highlight_system and highlight_body.lower().startswith(highlight_system.lower()):
                normalized_highlight = highlight_body[len(highlight_system):].strip()
            normalized_highlight = ' '.join(normalized_highlight.split())
            
            for system_name, body_name in current_results:
                if body_name == normalized_highlight and system_name.lower() == highlight_system.lower():
                    top_entries.add((system_name, body_name))
                    # Only add to green if still in green_highlights
                    if (highlight_system, highlight_body) in self._green_highlights:
                        green_entries.add((system_name, body_name))
        
        # Store for use in row insertion
        self._current_top_entries = top_entries
        self._current_green_entries = green_entries
        
        # Clear existing results completely
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Force UI refresh
        self.results_tree.update()
        
        # Sort: green entries first, then other top entries, then rest by distance
        try:
            hotspots.sort(key=lambda x: (
                0 if (x.get('system', x.get('systemName', '')), x.get('ring', x.get('bodyName', ''))) in green_entries else (
                    1 if (x.get('system', x.get('systemName', '')), x.get('ring', x.get('bodyName', ''))) in top_entries else 2
                ),  # Green first, then top, then rest
                float(x.get('distance', 999)),           # Then: Distance (closest first)
                x.get('systemName', x.get('system', '')).lower(),  # Then: System name (alphabetical)
                x.get('bodyName', x.get('ring', '')).lower()       # Then: Ring name (alphabetical)
            ))
        except:
            pass
            
        # Add new results with hotspots column
        # Process each hotspot for UI display
        for hotspot in hotspots:
            system_name = hotspot.get("systemName", hotspot.get("system", ""))
            body_name = hotspot.get("bodyName", hotspot.get("body", ""))
            
            # Get hotspot data for this ring
            system_name = hotspot.get("system", hotspot.get("systemName", "Unknown"))
            ring_name = hotspot.get("ring", hotspot.get("bodyName", "Unknown Ring"))
            
            # Create the full ring body name (system + ring)
            full_ring_name = f"{system_name} {ring_name}"
            
            # Determine hotspot count display - check if EDSM result was enhanced with hotspot data
            data_source = hotspot.get("data_source", "")
            if hotspot.get('has_hotspots') and hotspot.get('hotspot_data'):
                # Enhanced EDSM result with hotspot data - use the hotspot format
                hotspot_data = hotspot['hotspot_data']
                system_name = hotspot_data.get('systemName', '')
                body_name = hotspot_data.get('bodyName', '')
                # DISABLED: Don't make additional database calls during UI display
                # hotspot_display = self.user_db.format_hotspots_for_display(system_name, body_name)
                # Show the full material name or abbreviated, depending on filter
                material_name = hotspot.get("type", "Unknown Material")
                
                # Convert database format to display format for special cases
                if material_name == "LowTemperatureDiamond":
                    material_name = "Low Temp Diamonds"  # Show dropdown format
                elif material_name == "Low Temperature Diamonds":
                    material_name = "Low Temp Diamonds"  # Show dropdown format
                
                # Check if material_name already contains counts (from RingFinder.ALL_MINERALS GROUP_CONCAT)
                # Format: "Material (X)" or "Material1 (X), Material2 (Y)"
                # Use regex to detect if string ends with "(number)"
                import re
                already_formatted = bool(re.search(r'\(\d+\)$', material_name.strip()))
                
                if already_formatted:
                    # Already formatted with counts - show full names
                    hotspot_count_display = material_name
                else:
                    # Not formatted - add count wrapper
                    hotspot_count = hotspot.get("count", 1)
                    hotspot_display = f"{material_name} ({hotspot_count})"
                    
                    # Show full material names (no abbreviations)
                    hotspot_count_display = hotspot_display
            elif "EDTools" in data_source:
                # EDTools data - check if it's already formatted from GROUP_CONCAT
                material_name = hotspot.get("type", "")
                import re
                already_formatted = bool(re.search(r'\(\d+\)$', material_name.strip()))
                
                if already_formatted:
                    # Material name already contains counts from GROUP_CONCAT - use it directly
                    hotspot_count_display = material_name
                else:
                    # Regular count display
                    hotspot_count_display = str(hotspot.get("count", "-"))
            elif "Overlap" in data_source or "RES" in data_source:
                # Overlap/RES data - use the pre-formatted type field which has all materials
                hotspot_count_display = hotspot.get("type", "-")
            elif "Spansh" in data_source or "spansh" in data_source:
                # Spansh data - use the pre-formatted type field which has hotspot info
                # This contains abbreviated material names with counts: "Brom (3), Gran (2)"
                hotspot_count_display = hotspot.get("type", "-")
                if hotspot_count_display == t('ring_finder.no_hotspot_data') or hotspot_count_display == "":
                    hotspot_count_display = "-"
            elif "count" in hotspot:
                # User database hotspots - show the count  
                hotspot_count_display = str(hotspot.get("count", "-"))
            else:
                # Pure EDSM ring composition data - show "-"
                hotspot_count_display = "-"
            
            # Get visit count for this system
            visit_data = self.user_db.is_system_visited(system_name)
            visit_count = visit_data.get('visit_count', 0) if visit_data else 0
            visited_status = str(visit_count)
            
            # Format density for display - use existing density column as fallback
            density_formatted = "No data"
            
            # Try to use existing density value from database first
            density_value = hotspot.get("density")
            if density_value is not None and density_value != "No data":
                try:
                    # Format the existing density value
                    if isinstance(density_value, (int, float)):
                        density_formatted = f"{float(density_value):.6f}"
                    else:
                        density_formatted = str(density_value)
                except:
                    density_formatted = "No data"
            
            # Debug: Check what's actually going to UI and identify source
            ui_ring_type = hotspot.get("ring_type", "No data")
            if system_name == "Delkar" and "7 A" in ring_name:
                hotspot_source = hotspot.get("data_source", "Unknown Source")
                hotspot_type = hotspot.get("type", "Unknown Material")
                debug_id = hotspot.get("debug_id", "NO_ID")
                # Add stack trace info to identify where this insert comes from
                import traceback
                caller_info = traceback.extract_stack()[-3].filename.split('\\')[-1] + ":" + str(traceback.extract_stack()[-3].lineno)
                print(f"UI INSERT: {ring_name} -> ring_type: {ui_ring_type} | material: {hotspot_type} | source: {hotspot_source} | ID: {debug_id} | caller: {caller_info}")
            
            # Clean up None values before display
            ls_val = hotspot.get("ls", "No data")
            if ls_val is None or ls_val == "None":
                ls_val = "No data"
            
            ring_type_val = hotspot.get("ring_type", "No data")
            if ring_type_val is None or ring_type_val == "None":
                ring_type_val = "No data"
            
            # Check if this entry should be green (newly scanned, timer not expired)
            is_green = (system_name, ring_name) in green_entries
            
            # Apply alternating row colors + green highlighting
            row_index = len(self.results_tree.get_children())
            if is_green:
                tags = ('new_entry',)
            else:
                row_tag = 'evenrow' if row_index % 2 == 0 else 'oddrow'
                tags = (row_tag,)
            
            # Get overlap display for this ring (filtered by current material selection)
            current_material_filter = self._to_english(self.specific_material_var.get())
            overlap_display = self._get_overlap_display(system_name, ring_name, current_material_filter)
            
            # Get RES display for this ring (filtered by current material selection)
            res_display = self._get_res_display(system_name, ring_name, current_material_filter)
            
            # Localize material names in hotspot display
            hotspot_count_display = self._localize_hotspot_display(hotspot_count_display)
            overlap_display = self._localize_hotspot_display(overlap_display)
            
            item_id = self.results_tree.insert("", "end", values=(
                hotspot.get('distance', 'No data'),
                ls_val,
                system_name,
                visited_status,
                ring_name,
                ring_type_val,
                hotspot_count_display,
                overlap_display,
                res_display,
                density_formatted
            ), tags=tags)
            
            # Store first green entry for scrolling
            if is_green and not hasattr(self, '_first_new_item'):
                self._first_new_item = item_id
            
        # Update status with source information 
        count = len(hotspots)
        search_term = self.system_var.get().strip()
        material_filter = self.material_var.get()
        
        if search_term:
            if material_filter != 'All':
                if count > 0:
                    status_msg = t('ring_finder.found_material_locations_near').format(count=count, material=material_filter, system=search_term)
                else:
                    status_msg = t('ring_finder.no_material_rings_found_near').format(material=material_filter, system=search_term)
            else:
                if count > 0:
                    status_msg = t('ring_finder.found_locations_near').format(count=count, system=search_term)
                else:
                    status_msg = t('ring_finder.no_rings_found_near').format(system=search_term)
        else:
            if material_filter != 'All':
                if count > 0:
                    status_msg = t('ring_finder.found_material_rings').format(count=count, material=material_filter)
                else:
                    status_msg = t('ring_finder.no_material_rings_found').format(material=material_filter)
            else:
                if count > 0:
                    status_msg = t('ring_finder.found_rings').format(count=count)
                else:
                    status_msg = t('ring_finder.no_rings_found')
            
        # Set status message
        self.status_var.set(status_msg)
        
        # Auto-scroll to first new entry if found (without selecting it)
        if hasattr(self, '_first_new_item'):
            self.results_tree.see(self._first_new_item)
            # Removed selection_set to prevent auto-selection of scanned rings
            delattr(self, '_first_new_item')
        
        # Set timer to remove green highlight after 20 seconds (reset if already running)
        if green_entries:
            if self.highlight_timer:
                self.parent.after_cancel(self.highlight_timer)
            self.highlight_timer = self.parent.after(20000, self._clear_highlights)
            
    def _show_error(self, error_msg: str):
        """Show error message and reset UI"""
        self.status_var.set(t('ring_finder.search_failed'))
        print(f"Hotspot search error: {error_msg}")
        # Clear results on error
        self.results_tree.delete(*self.results_tree.get_children())
    
    def _clear_highlights(self):
        """Remove green highlight from all items (rows stay at top until manual search)"""
        # Clear the green highlights set so they don't come back
        self._green_highlights = set()
        
        for item in self.results_tree.get_children():
            # Remove the 'new_entry' tag from all items
            tags = list(self.results_tree.item(item, 'tags'))
            if 'new_entry' in tags:
                tags.remove('new_entry')
                # Apply alternating row color instead
                row_index = self.results_tree.index(item)
                row_tag = 'evenrow' if row_index % 2 == 0 else 'oddrow'
                tags.append(row_tag)
                self.results_tree.item(item, tags=tuple(tags))
        self.highlight_timer = None
        print("DEBUG: Highlights cleared")
    
    def _create_context_menu(self):
        """Create the right-click context menu for results"""
        # Get theme-aware menu colors
        from config import load_theme
        current_theme = load_theme()
        if current_theme == "elite_orange":
            menu_bg = "#1e1e1e"
            menu_fg = "#ff8c00"
            menu_active_bg = "#ff6600"
            menu_active_fg = "#000000"
        else:
            menu_bg = MENU_COLORS["bg"]
            menu_fg = MENU_COLORS["fg"]
            menu_active_bg = MENU_COLORS["activebackground"]
            menu_active_fg = MENU_COLORS["activeforeground"]
        
        self.context_menu = tk.Menu(self.parent, tearoff=0,
                                   bg=menu_bg, fg=menu_fg,
                                   activebackground=menu_active_bg, 
                                   activeforeground=menu_active_fg,
                                   selectcolor=menu_active_bg)
        self.context_menu.add_command(label=t('context_menu.copy_system'), command=self._copy_system_name)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t('context_menu.open_inara'), command=self._open_inara)
        self.context_menu.add_command(label=t('context_menu.open_edsm'), command=self._open_edsm)
        self.context_menu.add_command(label=t('context_menu.open_spansh'), command=self._open_spansh)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t('context_menu.find_sell_station'), command=self._find_sell_station)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t('context_menu.edit_hotspots'), command=self._show_edit_hotspots_dialog)
        self.context_menu.add_command(label=t('context_menu.set_overlap'), command=self._show_overlap_dialog)
        self.context_menu.add_command(label=t('context_menu.set_res'), command=self._show_res_dialog)
        self.context_menu.add_separator()
        self.context_menu.add_command(label=t('context_menu.bookmark_location'), command=self._bookmark_selected)
    
    def _show_context_menu(self, event):
        """Show the context menu when right-clicking on results"""
        try:
            # Select the item under cursor
            item = self.results_tree.identify_row(event.y)
            if item:
                self.results_tree.selection_set(item)
                self.results_tree.focus(item)
                
                # Enable/disable "Find Sell Station" based on mineral selection
                mineral_display = self.specific_material_var.get()
                mineral = self._to_english(mineral_display)
                is_specific_mineral = not self._is_all_minerals(mineral)
                
                # Menu item index for "Find Sell Station" is 6 (after copy_system, separator, inara, edsm, spansh, separator)
                if is_specific_mineral:
                    self.context_menu.entryconfig(6, state="normal")
                else:
                    self.context_menu.entryconfig(6, state="disabled")
                
                self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()
    
    def _copy_system_name(self):
        """Copy the selected system name to clipboard"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values and len(values) > 2:
                system_name = values[2]  # System is column index 2
                self.parent.clipboard_clear()
                self.parent.clipboard_append(system_name)
                self.status_var.set(f"Copied '{system_name}' to clipboard")
    
    def _open_inara(self):
        """Open selected system in Inara"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values and len(values) > 2:
                system_name = values[2]  # System is column index 2
                import urllib.parse
                import webbrowser
                url = f"https://inara.cz/elite/starsystem/?search={urllib.parse.quote(system_name)}"
                webbrowser.open(url)
    
    def _open_edsm(self):
        """Open selected system in EDSM"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values and len(values) > 2:
                system_name = values[2]  # System is column index 2
                import urllib.parse
                import webbrowser
                url = f"https://www.edsm.net/en/system/id/0/name/{urllib.parse.quote(system_name)}"
                webbrowser.open(url)
    
    def _open_spansh(self):
        """Open selected system in Spansh"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values and len(values) > 2:
                system_name = values[2]  # System is column index 2
                import urllib.parse
                import webbrowser
                url = f"https://spansh.co.uk/search/{urllib.parse.quote(system_name)}"
                webbrowser.open(url)

    def _find_sell_station(self):
        """Open Commodity Market with selected system and mineral to find sell stations"""
        selection = self.results_tree.selection()
        if not selection:
            self.status_var.set(t('ring_finder.no_selection'))
            return
        
        item = selection[0]
        values = self.results_tree.item(item, 'values')
        if not values or len(values) < 3:
            return
        
        # Get system name from the selected row
        system_name = values[2]  # System is column index 2
        
        # Get the currently selected mineral from the dropdown (already validated in context menu)
        mineral_display = self.specific_material_var.get()
        mineral = self._to_english(mineral_display)
        
        # Get main_app through prospector_panel
        main_app = getattr(self.prospector_panel, 'main_app', None) if hasattr(self, 'prospector_panel') else None
        
        # Switch to Commodity Market tab and set up search
        if main_app:
            try:
                # Switch to Commodity Market tab
                main_app.notebook.select(2)  # Commodity Market is typically tab index 2
                
                # Set the reference system (StringVar)
                if hasattr(main_app, 'marketplace_reference_system'):
                    main_app.marketplace_reference_system.set(system_name)
                
                # Set the commodity (use localized name for dropdown)
                if hasattr(main_app, 'marketplace_commodity'):
                    from localization import get_material
                    try:
                        localized_mineral = get_material(mineral)
                    except:
                        localized_mineral = mineral
                    main_app.marketplace_commodity.set(localized_mineral)
                
                # Set sell mode (not buy mode)
                if hasattr(main_app, 'marketplace_sell_mode'):
                    main_app.marketplace_sell_mode.set(True)
                if hasattr(main_app, 'marketplace_buy_mode'):
                    main_app.marketplace_buy_mode.set(False)
                
                # Set search mode to "near system"
                if hasattr(main_app, 'marketplace_search_mode'):
                    main_app.marketplace_search_mode.set("near_system")
                
                # Set max age to 8 hours (use localized value)
                if hasattr(main_app, 'marketplace_max_age') and hasattr(main_app, '_age_map'):
                    localized_8h = main_app._age_map.get('8 hours', '8 hours')
                    main_app.marketplace_max_age.set(localized_8h)
                
                # Trigger search after a short delay to let UI update
                main_app.after(100, main_app._search_marketplace)
                
                self.status_var.set(f"Searching sell stations for {mineral} near {system_name}...")
                
            except Exception as e:
                print(f"[RING FINDER] Error opening commodity market: {e}")
                import traceback
                traceback.print_exc()
                self.status_var.set(f"Error: {e}")
        else:
            self.status_var.set("Error: Could not access main application")
    
    def _copy_system_ring(self):
        """Copy the selected system + ring to clipboard"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values and len(values) > 4:
                system_name = values[2]  # System is column index 2
                ring_name = values[4]    # Ring is column index 4
                combined = f"{system_name} - {ring_name}"
                self.parent.clipboard_clear()
                self.parent.clipboard_append(combined)
                self.status_var.set(f"Copied '{combined}' to clipboard")
    
    def _copy_all_info(self):
        """Copy all information for the selected row to clipboard"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values:
                # Create formatted string with all information
                info_parts = []
                columns = ("Distance", "System", "Ring", "Ring Type", "LS")
                for i, (col, val) in enumerate(zip(columns, values)):
                    if val and val != "No data":
                        info_parts.append(f"{col}: {val}")
                
                all_info = " | ".join(info_parts)
                self.parent.clipboard_clear()
                self.parent.clipboard_append(all_info)
                self.status_var.set(f"Copied full info to clipboard")

    def _bookmark_selected(self):
        """Bookmark the selected ring location"""
        try:
            selection = self.results_tree.selection()
            if not selection:
                self.status_var.set("No ring selected to bookmark")
                return

            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if not values or len(values) < 5:
                self.status_var.set("Invalid ring data for bookmarking")
                return

            # Extract data from columns: Distance, LS, System, Visited, Ring, Ring Type, Hotspots, Overlap, RES Site, Density
            system_name = values[2]  # System column
            ring_name = values[4]    # Ring column
            ring_type = values[5] if len(values) > 5 else ""  # Ring Type column
            hotspots = values[6] if len(values) > 6 else ""   # Hotspots column
            overlap_display = values[7] if len(values) > 7 else ""  # Overlap column
            res_display = values[8] if len(values) > 8 else ""  # RES Site column

            if not system_name or system_name in ["Unknown", ""]:
                self.status_var.set("Cannot bookmark location with unknown system")
                return

            if not ring_name or ring_name in ["Unknown", ""]:
                self.status_var.set("Cannot bookmark location with unknown ring")
                return

            # Parse materials from hotspots column (abbreviated materials like "Pt, Pai, Ale")
            materials = ""
            if hotspots and hotspots not in ["None", "No data", ""]:
                # Convert abbreviated materials back to full names for bookmark
                materials = self._expand_abbreviated_materials(hotspots)
            
            # Parse overlap info from display (e.g., "Plat 2x" -> material="Platinum", type="2x")
            target_material = ""
            overlap_type = ""
            if overlap_display and overlap_display not in ["None", "No data", ""]:
                # Parse first overlap entry (e.g., "Plat 2x" or "Plat 2x, Pain 3x")
                first_overlap = overlap_display.split(',')[0].strip()
                parts = first_overlap.rsplit(' ', 1)  # Split from right to get "Plat" and "2x"
                if len(parts) == 2:
                    abbr, otype = parts
                    target_material = self._expand_abbreviated_materials(abbr)
                    overlap_type = otype
            
            # Parse RES info from display (e.g., "HAZ Plat" -> res_site="Hazardous", res_material="Platinum")
            res_site = ""
            res_material = ""
            if res_display and res_display not in ["None", "No data", ""]:
                # Parse first RES entry (e.g., "HAZ Plat" or "HAZ Plat, High LTD")
                first_res = res_display.split(',')[0].strip()
                parts = first_res.split(' ', 1)  # Split from left to get "HAZ" and "Plat"
                if len(parts) >= 1:
                    res_abbr = parts[0]
                    # Expand RES abbreviation
                    res_map = {'HAZ': 'Hazardous', 'High': 'High', 'Low': 'Low'}
                    res_site = res_map.get(res_abbr, res_abbr)
                    # Extract RES material (separate from overlap material)
                    if len(parts) == 2:
                        res_material = self._expand_abbreviated_materials(parts[1])

            # Get access to the prospector panel's bookmark dialog
            if self.prospector_panel and hasattr(self.prospector_panel, '_show_bookmark_dialog'):
                # Show bookmark dialog with pre-filled ring data
                self.prospector_panel._show_bookmark_dialog({
                    'system': system_name,
                    'body': ring_name,  # Ring name as the body
                    'hotspot': ring_type,  # Ring type as hotspot info
                    'materials': materials,
                    'avg_yield': '',  # No yield data from ring finder
                    'target_material': target_material,
                    'overlap_type': overlap_type,
                    'res_site': res_site,
                    'res_material': res_material,
                    'last_mined': '',  # No mining date from ring finder
                    'notes': ''  # Empty notes by default
                })
                self.status_var.set(f"Bookmark dialog opened for {system_name} - {ring_name}")
            else:
                self.status_var.set("Bookmark functionality not available")

        except Exception as e:
            print(f"Error bookmarking ring location: {e}")
            self.status_var.set(f"Error bookmarking location: {e}")

    def _expand_abbreviated_materials(self, hotspots_text: str) -> str:
        """Convert abbreviated materials back to full names for bookmarks and overlap tags"""
        # Reverse mapping of abbreviations to full names
        # Includes both 3-char and 4-char abbreviations
        expansions = {
            # 4-char abbreviations (from _abbreviate_material_for_display)
            'Alex': 'Alexandrite',
            'Beni': 'Benitoite',
            'Brom': 'Bromellite',
            'Gran': 'Grandidierite',
            'LTD': 'Low Temperature Diamonds',
            'Mona': 'Monazite',
            'Musg': 'Musgravite',
            'Pain': 'Painite',
            'Plat': 'Platinum',
            'Rhod': 'Rhodplumsite',
            'Sere': 'Serendibite',
            'Trit': 'Tritium',
            'Opals': 'Void Opals',
            # 3-char legacy abbreviations
            'Pt': 'Platinum', 'Pai': 'Painite', 'Ale': 'Alexandrite', 'Tri': 'Tritium',
            'VO': 'Void Opals', 'Rho': 'Rhodplumsite',
            'Ser': 'Serendibite', 'Mon': 'Monazite', 'Mur': 'Musgravite', 'Ben': 'Benitoite',
            'Jer': 'Jadeite', 'Red': 'Red Beryl', 'Tai': 'Taaffeite', 'Gra': 'Grandidierite',
            'Opa': 'Opal', 'Osm': 'Osmium', 'Pla': 'Platinum', 'Pal': 'Palladium',
            'Gol': 'Gold', 'Sil': 'Silver', 'Ber': 'Bertrandite', 'Ind': 'Indite',
            'Gal': 'Gallite', 'Col': 'Coltan', 'Uru': 'Uruinite', 'Lep': 'Lepidolite',
            'Cob': 'Cobalt', 'Cov': 'Covite'
        }
        
        if not hotspots_text:
            return ""
            
        # Split by comma and expand each material
        materials = []
        for material in hotspots_text.split(','):
            material = material.strip()
            if material in expansions:
                materials.append(expansions[material])
            else:
                materials.append(material)  # Keep as is if not in abbreviations
                
        return ', '.join(materials)

    def _setup_status_monitoring(self):
        """Setup journal monitoring for auto-search functionality"""
        try:
            if self.prospector_panel and hasattr(self.prospector_panel, 'journal_dir'):
                # Get current system from prospector panel for initialization
                self.last_monitored_system = getattr(self.prospector_panel, 'last_system', None)
                
                # Hook into the existing journal monitoring system via cargo monitor
                if hasattr(self.prospector_panel, 'main_app') and self.prospector_panel.main_app:
                    cargo_monitor = getattr(self.prospector_panel.main_app, 'cargo_monitor', None)
                    if cargo_monitor:
                        # Add our callback to the journal monitoring
                        original_process = cargo_monitor.process_journal_event
                        def enhanced_process(line):
                            # Call original processing first
                            original_process(line)
                            # Then check for auto-search triggers
                            self._check_journal_event_for_auto_search(line)
                        cargo_monitor.process_journal_event = enhanced_process
        except Exception as e:
            pass

    def _check_journal_event_for_auto_search(self, line: str):
        """Check journal events for FSD jumps and trigger auto-search"""
        if not self.auto_search_var.get():
            return
            
        try:
            import json
            event = json.loads(line.strip())
            event_type = event.get("event", "")
            
            # Log ALL events that contain StarSystem for debugging
            if 'StarSystem' in event:
                current_system = event.get("StarSystem")
                print(f"[AUTO-SEARCH DEBUG] Event '{event_type}' has StarSystem: {current_system}, Last Monitored: {self.last_monitored_system}")
            
            # ONLY trigger on FSDJump (jump events), NOT on Scan/SAASignalsFound!
            if event_type == "FSDJump":
                current_system = event.get("StarSystem")
                print(f"[AUTO-SEARCH] FSDJump detected: {current_system}")
                if current_system and current_system != self.last_monitored_system:
                    print(f"[AUTO-SEARCH] ✓ NEW SYSTEM: {current_system} (was: {self.last_monitored_system})")
                    self.last_monitored_system = current_system
                    # Schedule auto-search in main thread
                    self.parent.after(1000, lambda: self._auto_search_new_system(current_system))
                else:
                    print(f"[AUTO-SEARCH] ✗ SAME SYSTEM: already in {current_system}")
                    
        except Exception as e:
            print(f"[AUTO-SEARCH ERROR] {e}")  # Log errors instead of silent fail

    def _auto_search_new_system(self, system_name: str):
        """Auto-populate reference system and trigger search silently"""
        try:
            import time
            self._system_jump_time = time.time()  # Track when we jumped
            # Update reference system field
            self.system_var.set(system_name)
            
            # Reset the CargoMonitor's refresh tracking so rings in new system can refresh
            if hasattr(self, 'prospector_panel') and self.prospector_panel:
                main_app = getattr(self.prospector_panel, 'main_app', None)
                if main_app and hasattr(main_app, 'cargo_monitor'):
                    cargo_monitor = main_app.cargo_monitor
                    cargo_monitor._last_refreshed_rings = set()
            
            # Trigger search with current settings - no highlighting (just location change)
            if self.search_btn['state'] == 'normal':
                self.search_hotspots()  # No highlight_body = no highlighting
                
        except Exception as e:
            # Silent fail - let user search manually if auto-search fails
            pass

    def _load_auto_search_state(self) -> bool:
        """Load auto-search enabled state from Variables folder"""
        try:
            auto_search_file = os.path.join(self.vars_dir, "autoSearch.txt")
            if os.path.exists(auto_search_file):
                with open(auto_search_file, 'r') as f:
                    content = f.read().strip()
                    return content == "1"
        except Exception as e:
            pass
        return False  # Default to disabled

    def _save_auto_search_state(self):
        """Save auto-search enabled state to Variables folder"""
        try:
            os.makedirs(self.vars_dir, exist_ok=True)
            auto_search_file = os.path.join(self.vars_dir, "autoSearch.txt")
            with open(auto_search_file, 'w') as f:
                f.write("1" if self.auto_search_var.get() else "0")
        except Exception as e:
            pass

    def _load_auto_switch_tabs_state(self):
        """Load auto-switch tabs state from main app config"""
        try:
            if self.prospector_panel and hasattr(self.prospector_panel, 'main_app'):
                main_app = self.prospector_panel.main_app
                if main_app and hasattr(main_app, 'auto_switch_tabs'):
                    self.auto_switch_tabs_var.set(bool(main_app.auto_switch_tabs.get()))
                    return
            # Fall back to config file
            from config import load_config
            cfg = load_config()
            self.auto_switch_tabs_var.set(cfg.get("auto_switch_tabs", False))
        except Exception as e:
            pass

    def _on_auto_switch_tabs_toggle(self):
        """Called when auto-switch tabs checkbox is toggled - sync with main app"""
        try:
            enabled = self.auto_switch_tabs_var.get()
            
            # Sync with main app's setting
            if self.prospector_panel and hasattr(self.prospector_panel, 'main_app'):
                main_app = self.prospector_panel.main_app
                if main_app and hasattr(main_app, 'auto_switch_tabs'):
                    main_app.auto_switch_tabs.set(1 if enabled else 0)
                    # The trace will handle saving to config
        except Exception as e:
            print(f"[AUTO-TAB] Error syncing auto-switch tabs: {e}")

    def _startup_auto_search(self, force: bool = False):
        """Perform auto-search on startup if enabled
        
        Args:
            force: If True, skip the full sync check (used when called after sync completes)
        """
        try:
            # Check if full sync is pending - if so, wait for sync to trigger us
            # This avoids running search with stale visit counts
            if not force:
                main_app = self.parent
                if hasattr(main_app, '_needs_full_sync') and main_app._needs_full_sync():
                    print("[RING FINDER] Full sync pending - deferring auto-search")
                    return
            
            # Get current system from prospector panel (most reliable)
            current_system = getattr(self.prospector_panel, 'last_system', None) if self.prospector_panel else None
            
            if current_system:
                self.status_var.set(f"Auto-search: {current_system}")
                self.system_var.set(current_system)
                self.last_monitored_system = current_system
                self.search_hotspots()
            else:
                self.status_var.set("Auto-search: No system detected")
                
        except Exception as e:
            self.status_var.set("Auto-search: Detection failed")
            
        # Clear status after 5 seconds
        self.parent.after(5000, lambda: self.status_var.set(""))

    def _get_overlap_display(self, system_name: str, body_name: str, material_filter: str = None) -> str:
        """Get formatted overlap display string for a ring
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            material_filter: If set, only show overlap for this material (not "All Minerals")
            
        Returns:
            Formatted string like "Plat 2x, Pain 3x" or empty string
        """
        try:
            overlaps = self.user_db.get_overlaps_for_ring(system_name, body_name)
            if not overlaps:
                return ""
            
            # If filtering by specific material, only show that material's overlap
            if material_filter and not self._is_all_minerals(material_filter):
                # Filter overlaps to only the selected material
                filtered_overlaps = []
                for overlap in overlaps:
                    mat_name = overlap['material_name'].lower()
                    filter_name = material_filter.lower()
                    # Match by name (handle variations like "Low Temp Diamonds" vs "Low Temperature Diamonds")
                    if mat_name == filter_name or filter_name in mat_name or mat_name in filter_name:
                        filtered_overlaps.append(overlap)
                overlaps = filtered_overlaps
            
            if not overlaps:
                return ""
            
            # Format each overlap with abbreviated material name
            display_parts = []
            for overlap in overlaps:
                material = overlap['material_name']
                tag = overlap['overlap_tag']
                # Abbreviate the material name
                abbr = self._abbreviate_material_for_display(material)
                # Handle case where abbreviation returns same string (not in dict)
                if abbr == material:
                    # Use first 4 chars as fallback abbreviation
                    abbr = material[:4] if len(material) > 4 else material
                display_parts.append(f"{abbr} {tag}")
            
            return ", ".join(display_parts)
        except Exception as e:
            print(f"Error getting overlap display: {e}")
            return ""

    def _get_res_display(self, system_name: str, body_name: str, material_filter: str = None) -> str:
        """Get formatted RES display string for a ring
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            material_filter: If set, only show RES for this material (not "All Minerals")
            
        Returns:
            Formatted string like "Haz" or "High" or empty string
        """
        try:
            res_sites = self.user_db.get_res_for_ring(system_name, body_name)
            if not res_sites:
                return ""
            
            # If filtering by specific material, only show that material's RES
            if material_filter and not self._is_all_minerals(material_filter):
                # Filter RES to only the selected material
                filtered_res = []
                for res in res_sites:
                    mat_name = res['material_name'].lower()
                    filter_name = material_filter.lower()
                    # Match by name
                    if mat_name == filter_name or filter_name in mat_name or mat_name in filter_name:
                        filtered_res.append(res)
                res_sites = filtered_res
            
            if not res_sites:
                return ""
            
            # Format RES tags with material abbreviation (RES type first, then material)
            # Handles comma-separated tags for multiple RES per material
            display_parts = []
            for res in res_sites:
                material = res['material_name']
                tag = res['res_tag']
                # Abbreviate the material name
                abbr = self._abbreviate_material_for_display(material)
                # Handle case where abbreviation returns same string (not in dict)
                if abbr == material:
                    # Use first 4 chars as fallback abbreviation
                    abbr = material[:4] if len(material) > 4 else material
                
                # Handle comma-separated tags (e.g., "Hazardous, High")
                if tag and ',' in tag:
                    # Multiple RES types for this material
                    for single_tag in tag.split(','):
                        single_tag = single_tag.strip()
                        res_abbr = self._abbreviate_res_tag(single_tag)
                        if res_abbr:
                            display_parts.append(f"{res_abbr} {abbr}")
                else:
                    res_abbr = self._abbreviate_res_tag(tag)
                    if res_abbr:
                        display_parts.append(f"{res_abbr} {abbr}")
            
            return ", ".join(display_parts)
        except Exception as e:
            print(f"Error getting RES display: {e}")
            return ""

    def _show_edit_hotspots_dialog(self):
        """Show dialog to edit hotspot counts for a ring"""
        try:
            selection = self.results_tree.selection()
            if not selection:
                self.status_var.set(t('ring_finder.no_selection'))
                return
            
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if not values or len(values) < 7:
                self.status_var.set(t('ring_finder.invalid_selection'))
                return
            
            system_name = values[2]  # System column
            ring_name = values[4]    # Ring column
            
            if not system_name or not ring_name:
                self.status_var.set(t('ring_finder.missing_info'))
                return
            
            # Get all hotspots for this ring from database
            import sqlite3
            hotspots_data = []
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT material_name, hotspot_count 
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ?
                    ORDER BY material_name
                ''', (system_name, ring_name))
                hotspots_data = cursor.fetchall()
            
            if not hotspots_data:
                self.status_var.set(t('ring_finder.no_hotspots_found'))
                return
            
            # Create dialog
            dialog = tk.Toplevel(self.parent)
            dialog.title(t('context_menu.edit_hotspots_title'))
            dialog.resizable(False, False)
            dialog.transient(self.parent.winfo_toplevel())
            
            # Set app icon
            try:
                from app_utils import get_app_icon_path
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            frame = ttk.Frame(dialog, padding=15)
            frame.pack(fill="both", expand=True)
            
            # Header
            ttk.Label(frame, text=t('context_menu.edit_hotspots_for'), font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
            ttk.Label(frame, text=f"{system_name}", font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=3, sticky="w")
            ttk.Label(frame, text=f"{ring_name}", font=("Segoe UI", 9)).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 10))
            
            # Column headers
            ttk.Label(frame, text=t('context_menu.material_header'), font=("Segoe UI", 9, "bold")).grid(row=3, column=0, sticky="w", padx=(0, 20))
            ttk.Label(frame, text=t('context_menu.count_header'), font=("Segoe UI", 9, "bold")).grid(row=3, column=1, sticky="w")
            
            # Create entry fields for each material
            entry_vars = {}
            for idx, (material_name, count) in enumerate(hotspots_data):
                row = idx + 4
                
                # Material name (display formatted)
                display_name = self._format_material_for_display(material_name)
                ttk.Label(frame, text=display_name).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 20))
                
                # Count entry
                var = tk.StringVar(value=str(count or 0))
                entry = ttk.Entry(frame, textvariable=var, width=8, justify="center")
                entry.grid(row=row, column=1, sticky="w", pady=2)
                entry_vars[material_name] = var
            
            # Buttons
            button_frame = ttk.Frame(frame)
            button_frame.grid(row=len(hotspots_data) + 5, column=0, columnspan=3, pady=(15, 0))
            
            def save():
                try:
                    with sqlite3.connect(self.user_db.db_path) as conn:
                        cursor = conn.cursor()
                        for material_name, var in entry_vars.items():
                            try:
                                new_count = int(var.get())
                                if new_count < 0:
                                    new_count = 0
                            except ValueError:
                                new_count = 0
                            
                            cursor.execute('''
                                UPDATE hotspot_data 
                                SET hotspot_count = ?
                                WHERE system_name = ? AND body_name = ? AND material_name = ?
                            ''', (new_count, system_name, ring_name, material_name))
                        conn.commit()
                    
                    self.status_var.set(t('context_menu.hotspots_updated'))
                    # Refresh the display
                    self._refresh_row_hotspots(item, system_name, ring_name)
                    dialog.destroy()
                except Exception as e:
                    self.status_var.set(f"Error: {e}")
            
            ttk.Button(button_frame, text=t('save'), command=save).pack(side="left", padx=5)
            ttk.Button(button_frame, text=t('cancel'), command=dialog.destroy).pack(side="left", padx=5)
            
            # Center dialog
            dialog.update_idletasks()
            x = self.parent.winfo_rootx() + (self.parent.winfo_width() - dialog.winfo_width()) // 2
            y = self.parent.winfo_rooty() + (self.parent.winfo_height() - dialog.winfo_height()) // 2
            dialog.geometry(f"+{x}+{y}")
            
            dialog.grab_set()
            dialog.focus_set()
            
        except Exception as e:
            print(f"Error showing edit hotspots dialog: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_row_hotspots(self, item, system_name, ring_name):
        """Refresh the hotspots display for a specific row after editing"""
        try:
            hotspots_display = self._get_ring_hotspots_display(system_name, ring_name)
            values = list(self.results_tree.item(item, 'values'))
            if len(values) > 6:
                values[6] = hotspots_display  # Hotspots column
                self.results_tree.item(item, values=values)
        except Exception as e:
            print(f"Error refreshing row hotspots: {e}")

    def _show_overlap_dialog(self):
        """Show dialog to tag overlap for selected hotspot"""
        try:
            selection = self.results_tree.selection()
            if not selection:
                self.status_var.set("No ring selected")
                return
            
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if not values or len(values) < 7:
                self.status_var.set("Invalid selection")
                return
            
            # Extract data from columns: Distance, LS, System, Visited, Ring, Ring Type, Hotspots, Overlap, Density
            system_name = values[2]  # System column
            ring_name = values[4]    # Ring column
            hotspots_str = values[6] # Hotspots column - contains materials like "Plat(3), Pain(2)"
            
            if not system_name or not ring_name:
                self.status_var.set("Cannot tag: missing system or ring info")
                return
            
            # Parse materials from hotspots string
            materials = self._parse_materials_from_hotspots(hotspots_str)
            if not materials:
                self.status_var.set("No materials found in this ring")
                return
            
            # Expand abbreviated names to full names for dropdown
            full_materials = [self._expand_abbreviated_materials(m) for m in materials]
            
            # Create dialog
            dialog = tk.Toplevel(self.parent)
            dialog.title(t('context_menu.set_overlap_title'))
            dialog.resizable(False, False)
            dialog.transient(self.parent.winfo_toplevel())
            
            # Set app icon
            try:
                from app_utils import get_app_icon_path
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            frame = ttk.Frame(dialog, padding=15)
            frame.pack(fill="both", expand=True)
            
            # Header
            ttk.Label(frame, text=t('context_menu.set_overlap_for'), font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
            ttk.Label(frame, text=f"{system_name} - {ring_name}", font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 15))
            
            # Material dropdown - use full names
            ttk.Label(frame, text=t('context_menu.mineral')).grid(row=2, column=0, sticky="w", pady=5, padx=(0, 10))
            material_var = tk.StringVar()
            material_combo = ttk.Combobox(frame, textvariable=material_var, width=25, state="readonly")
            material_combo['values'] = full_materials
            material_combo.grid(row=2, column=1, sticky="w", pady=5)
            
            # Pre-select material based on current filter
            current_filter = self._to_english(self.specific_material_var.get())
            if not self._is_all_minerals(current_filter):
                # Try to find matching material in dropdown
                for mat in full_materials:
                    if current_filter.lower() in mat.lower() or mat.lower() in current_filter.lower():
                        material_var.set(mat)
                        break
            if not material_var.get() and full_materials:
                material_var.set(full_materials[0])
            
            # Overlap selection
            ttk.Label(frame, text=t('context_menu.overlap_label')).grid(row=3, column=0, sticky="w", pady=5, padx=(0, 10))
            overlap_var = tk.StringVar(value="None")
            
            overlap_frame = tk.Frame(frame, bg="#1e1e1e")
            overlap_frame.grid(row=3, column=1, sticky="w", pady=5)
            
            # Dark themed radio buttons
            rb_style = {"bg": "#1e1e1e", "fg": "#e0e0e0", "activebackground": "#2b2b2b", 
                        "activeforeground": "#ffffff", "selectcolor": "#1e1e1e", "relief": "flat"}
            tk.Radiobutton(overlap_frame, text=t('context_menu.none'), variable=overlap_var, value="None", **rb_style).pack(side="left", padx=(0, 10))
            tk.Radiobutton(overlap_frame, text="2x", variable=overlap_var, value="2x", **rb_style).pack(side="left", padx=(0, 10))
            tk.Radiobutton(overlap_frame, text="3x", variable=overlap_var, value="3x", **rb_style).pack(side="left")
            
            # Load current overlap value when material changes
            def on_material_change(*args):
                mat = material_var.get()
                if mat:
                    # Full name is already in dropdown, use directly
                    current_tag = self.user_db.get_overlap_tag(system_name, ring_name, mat)
                    overlap_var.set(current_tag if current_tag else "None")
            
            material_var.trace_add('write', on_material_change)
            on_material_change()  # Initialize
            
            # Buttons
            button_frame = ttk.Frame(frame)
            button_frame.grid(row=4, column=0, columnspan=2, pady=(15, 0))
            
            def save():
                mat = material_var.get()
                if not mat:
                    return
                # Full name is already in dropdown, use directly
                tag = overlap_var.get()
                tag_value = tag if tag != "None" else None
                
                success = self.user_db.set_overlap_tag(system_name, ring_name, mat, tag_value)
                if success:
                    self.status_var.set(f"Overlap tagged: {mat} = {tag}")
                    # Refresh the current row's overlap display
                    self._refresh_row_overlap(item, system_name, ring_name)
                else:
                    self.status_var.set(f"Failed to save overlap tag")
                dialog.destroy()
            
            def cancel():
                dialog.destroy()
            
            save_btn = tk.Button(button_frame, text=t('dialogs.save'), command=save,
                                bg="#2a5a2a", fg="#ffffff", 
                                activebackground="#3a6a3a", activeforeground="#ffffff",
                                relief="solid", bd=1, cursor="hand2", 
                                pady=6, padx=15, font=("Segoe UI", 9))
            save_btn.pack(side="left", padx=(0, 8))
            
            cancel_btn = tk.Button(button_frame, text=t('dialogs.cancel'), command=cancel,
                                  bg="#5a2a2a", fg="#ffffff", 
                                  activebackground="#6a3a3a", activeforeground="#ffffff",
                                  relief="solid", bd=1, cursor="hand2", 
                                  pady=6, padx=15, font=("Segoe UI", 9))
            cancel_btn.pack(side="left")
            
            # Center dialog
            dialog.update_idletasks()
            w = dialog.winfo_width()
            h = dialog.winfo_height()
            parent = self.parent.winfo_toplevel()
            px = parent.winfo_x()
            py = parent.winfo_y()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
            dialog.geometry(f"+{x}+{y}")
            
            dialog.grab_set()
            dialog.focus_set()
            
        except Exception as e:
            print(f"Error showing overlap dialog: {e}")
            import traceback
            traceback.print_exc()
            self.status_var.set(f"Error: {e}")

    def _parse_materials_from_hotspots(self, hotspots_str: str) -> List[str]:
        """Parse material names from hotspots display string
        
        Args:
            hotspots_str: String like "Plat(3), Pain(2), Alex(1)" or "Platinum (3)"
            
        Returns:
            List of material names
        """
        if not hotspots_str or hotspots_str in ["-", "No data", "None"]:
            return []
        
        materials = []
        # Split by comma
        parts = hotspots_str.split(',')
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # Remove count suffix like "(3)"
            if '(' in part:
                mat = part.split('(')[0].strip()
            else:
                mat = part.strip()
            if mat:
                materials.append(mat)
        
        return materials

    def _refresh_row_overlap(self, item_id: str, system_name: str, ring_name: str):
        """Refresh the overlap column for a specific row"""
        try:
            overlap_display = self._get_overlap_display(system_name, ring_name)
            # Get current values and update overlap column (index 7)
            values = list(self.results_tree.item(item_id, 'values'))
            if len(values) >= 8:
                values[7] = overlap_display
                self.results_tree.item(item_id, values=values)
        except Exception as e:
            print(f"Error refreshing row overlap: {e}")

    def _show_res_dialog(self):
        """Show dialog to add RES site(s) for selected hotspot - supports multiple RES per material"""
        try:
            selection = self.results_tree.selection()
            if not selection:
                self.status_var.set("No ring selected")
                return
            
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if not values or len(values) < 7:
                self.status_var.set("Invalid selection")
                return
            
            # Extract data from columns: Distance, LS, System, Visited, Ring, Ring Type, Hotspots, Overlap, RES, Density
            system_name = values[2]  # System column
            ring_name = values[4]    # Ring column
            hotspots_str = values[6] # Hotspots column - contains materials like "Plat(3), Pain(2)"
            
            if not system_name or not ring_name:
                self.status_var.set("Cannot add RES: missing system or ring info")
                return
            
            # Parse materials from hotspots string
            materials = self._parse_materials_from_hotspots(hotspots_str)
            if not materials:
                self.status_var.set("No materials found in this ring")
                return
            
            # Expand abbreviated names to full names for dropdown
            full_materials = [self._expand_abbreviated_materials(m) for m in materials]
            
            # Create dialog
            dialog = tk.Toplevel(self.parent)
            dialog.title(t('context_menu.set_res_title'))
            dialog.resizable(False, False)
            dialog.transient(self.parent.winfo_toplevel())
            
            # Set app icon
            try:
                from app_utils import get_app_icon_path
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            frame = ttk.Frame(dialog, padding=15)
            frame.pack(fill="both", expand=True)
            
            # Header
            ttk.Label(frame, text=t('context_menu.set_res_for'), font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))
            ttk.Label(frame, text=f"{system_name} - {ring_name}", font=("Segoe UI", 9)).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 15))
            
            # Material dropdown - use full names
            ttk.Label(frame, text=t('context_menu.mineral')).grid(row=2, column=0, sticky="w", pady=5, padx=(0, 10))
            material_var = tk.StringVar()
            material_combo = ttk.Combobox(frame, textvariable=material_var, width=25, state="readonly")
            material_combo['values'] = full_materials
            material_combo.grid(row=2, column=1, sticky="w", pady=5)
            
            # Pre-select material based on current filter (map localized display to English)
            current_filter = self._to_english(self.specific_material_var.get())
            if not self._is_all_minerals(current_filter):
                # Try to find matching material in dropdown
                for mat in full_materials:
                    if current_filter.lower() in mat.lower() or mat.lower() in current_filter.lower():
                        material_var.set(mat)
                        break
            if not material_var.get() and full_materials:
                material_var.set(full_materials[0])
            
            # RES type selection - CHECKBOXES for multiple selection
            ttk.Label(frame, text=t('context_menu.res_type')).grid(row=3, column=0, sticky="nw", pady=5, padx=(0, 10))
            
            res_frame = tk.Frame(frame, bg="#1e1e1e")
            res_frame.grid(row=3, column=1, sticky="w", pady=5)
            
            # Checkbox variables for each RES type
            haz_var = tk.BooleanVar(value=False)
            high_var = tk.BooleanVar(value=False)
            normal_var = tk.BooleanVar(value=False)
            low_var = tk.BooleanVar(value=False)
            
            # Dark themed checkboxes
            cb_style = {"bg": "#1e1e1e", "fg": "#e0e0e0", "activebackground": "#2b2b2b", 
                        "activeforeground": "#ffffff", "selectcolor": "#333333", "relief": "flat"}
            
            tk.Checkbutton(res_frame, text="Haz", variable=haz_var, **cb_style).pack(side="left", padx=(0, 12))
            tk.Checkbutton(res_frame, text="High", variable=high_var, **cb_style).pack(side="left", padx=(0, 12))
            tk.Checkbutton(res_frame, text="Normal", variable=normal_var, **cb_style).pack(side="left", padx=(0, 12))
            tk.Checkbutton(res_frame, text="Low", variable=low_var, **cb_style).pack(side="left")
            
            # Helper label
            ttk.Label(frame, text=t('context_menu.res_multi_hint'), font=("Segoe UI", 8, "italic"), 
                     foreground="#888888").grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))
            
            # Load current RES values when material changes
            def on_material_change(*args):
                mat = material_var.get()
                if mat:
                    current_tag = self.user_db.get_res_tag(system_name, ring_name, mat)
                    # Parse comma-separated tags
                    haz_var.set(False)
                    high_var.set(False)
                    normal_var.set(False)
                    low_var.set(False)
                    if current_tag:
                        tags = [t.strip() for t in current_tag.split(',')]
                        for tag in tags:
                            if tag.lower() in ['hazardous', 'haz']:
                                haz_var.set(True)
                            elif tag.lower() == 'high':
                                high_var.set(True)
                            elif tag.lower() == 'normal':
                                normal_var.set(True)
                            elif tag.lower() == 'low':
                                low_var.set(True)
            
            material_var.trace_add('write', on_material_change)
            on_material_change()  # Initialize
            
            # Buttons
            button_frame = ttk.Frame(frame)
            button_frame.grid(row=5, column=0, columnspan=2, pady=(15, 0))
            
            def save():
                mat = material_var.get()
                if not mat:
                    return
                
                # Build comma-separated tag from checkboxes
                selected_tags = []
                if haz_var.get():
                    selected_tags.append("Hazardous")
                if high_var.get():
                    selected_tags.append("High")
                if normal_var.get():
                    selected_tags.append("Normal")
                if low_var.get():
                    selected_tags.append("Low")
                
                tag_value = ", ".join(selected_tags) if selected_tags else None
                
                success = self.user_db.set_res_tag(system_name, ring_name, mat, tag_value)
                if success:
                    if tag_value:
                        self.status_var.set(f"RES tagged: {mat} = {tag_value}")
                    else:
                        self.status_var.set(f"RES cleared for {mat}")
                    # Refresh the current row's RES display
                    self._refresh_row_res(item, system_name, ring_name)
                else:
                    self.status_var.set(f"Failed to save RES tag")
                dialog.destroy()
            
            def cancel():
                dialog.destroy()
            
            save_btn = tk.Button(button_frame, text=t('dialogs.save'), command=save,
                                bg="#2a5a2a", fg="#ffffff", 
                                activebackground="#3a6a3a", activeforeground="#ffffff",
                                relief="solid", bd=1, cursor="hand2", 
                                pady=6, padx=15, font=("Segoe UI", 9))
            save_btn.pack(side="left", padx=(0, 8))
            
            cancel_btn = tk.Button(button_frame, text=t('dialogs.cancel'), command=cancel,
                                  bg="#5a2a2a", fg="#ffffff", 
                                  activebackground="#6a3a3a", activeforeground="#ffffff",
                                  relief="solid", bd=1, cursor="hand2", 
                                  pady=6, padx=15, font=("Segoe UI", 9))
            cancel_btn.pack(side="left")
            
            # Center dialog
            dialog.update_idletasks()
            w = dialog.winfo_width()
            h = dialog.winfo_height()
            parent = self.parent.winfo_toplevel()
            px = parent.winfo_x()
            py = parent.winfo_y()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
            dialog.geometry(f"+{x}+{y}")
            
            dialog.grab_set()
            dialog.focus_set()
            
        except Exception as e:
            print(f"Error showing RES dialog: {e}")
            import traceback
            traceback.print_exc()
            self.status_var.set(f"Error: {e}")

    def _refresh_row_res(self, item_id: str, system_name: str, ring_name: str):
        """Refresh the RES column for a specific row"""
        try:
            res_display = self._get_res_display(system_name, ring_name)
            # Get current values and update RES column (index 8)
            values = list(self.results_tree.item(item_id, 'values'))
            if len(values) >= 9:
                values[8] = res_display
                self.results_tree.item(item_id, values=values)
        except Exception as e:
            print(f"Error refreshing row RES: {e}")

