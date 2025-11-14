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
    
    ALL_MINERALS = "All Minerals"  # Constant for "All Minerals" filter
    
    def __init__(self, parent_frame: ttk.Frame, prospector_panel=None, app_dir: Optional[str] = None, tooltip_class=None, distance_calculator=None):
        print("DEBUG: RingFinder.__init__ called")
        self.parent = parent_frame
        self.prospector_panel = prospector_panel  # Reference to get current system
        self.systems_data = {}  # System coordinates cache
        self.current_system_coords = None
        self.app_dir = app_dir  # Store app_dir for galaxy database access
        self.db_ready = False  # Track database initialization status
        self.distance_calculator = distance_calculator  # Distance calculator for Sol distance
        print(f"DEBUG: distance_calculator = {distance_calculator}")
        
        # Use main app's ToolTip class if provided, otherwise use local one
        global ToolTip
        if tooltip_class:
            ToolTip = tooltip_class
        
        # Initialize local database manager
        self.local_db = LocalSystemsDatabase()
        
        # Initialize user database for hotspot data with correct app directory
        if app_dir:
            # Use provided app directory to construct database path
            data_dir = os.path.join(app_dir, "data")
            db_path = os.path.join(data_dir, "user_data.db")
            print(f"DEBUG: RingFinder using explicit database path: {db_path}")
            print(f"DEBUG: Current working directory: {os.getcwd()}")
            self.user_db = UserDatabase(db_path)
            
            # Initialize EDSM integration for automatic metadata fallback
            self.edsm = EDSMIntegration(db_path)
        else:
            # Fall back to default path resolution
            print("DEBUG: RingFinder using default database path resolution")
            self.user_db = UserDatabase()
            print(f"DEBUG: RingFinder actual database path: {self.user_db.db_path}")
            
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
        
        # Schedule startup auto-search if enabled (after database loads)
        if self.auto_search_var.get():
            self.parent.after(3000, self._startup_auto_search)  # 3 second delay
        
    def _abbreviate_material_for_display(self, hotspot_text: str) -> str:
        """Abbreviate material names in hotspot display text for Ring Finder column
        
        Uses recognizable 3-4 character abbreviations for better readability
        while saving space in the 'All Materials' view.
        """
        abbreviations = {
            # Current materials in database (13 materials)
            'Alexandrite': 'Alex',
            'Benitoite': 'Beni',
            'Bromellite': 'Brom',
            'Grandidierite': 'Gran',
            'Low Temp Diamonds': 'LTD',
            'Low Temperature Diamonds': 'LTD',  # Database version
            'Monazite': 'Mona',
            'Musgravite': 'Musg',
            'Painite': 'Pain',
            'Platinum': 'Plat',
            'Rhodplumsite': 'Rhod',
            'Serendibite': 'Sere',
            'Tritium': 'Trit',
            'Void Opals': 'Opals',
        }
        
        # Replace full material names with abbreviations in the display text
        result = hotspot_text
        for full_name, abbr in abbreviations.items():
            result = result.replace(full_name, abbr)
        
        return result
        
    def setup_ui(self):
        """Create hotspot finder UI following EliteMining patterns"""
        print("DEBUG: setup_ui called")
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
        search_title = ttk.Label(search_header, text="Search For Hotspots", font=("Segoe UI", 9, "bold"))
        search_title.pack(side="left")
        
        # Database status on the right
        self.status_var = tk.StringVar(value="Loading...")
        status_label = ttk.Label(search_header, textvariable=self.status_var, 
                                font=("Segoe UI", 8), foreground="#888888")
        status_label.pack(side="right")
        
        # Distance info (below title on separate line) - label in white, values in yellow
        distance_header = ttk.Frame(self.scrollable_frame)
        distance_header.pack(fill="x", padx=10, pady=(0, 5))
        
        ttk.Label(distance_header, text="Distances:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 5))
        
        self.distance_info_var = tk.StringVar(value="➤ Sol: --- | Home: --- | Fleet Carrier: ---")
        distance_info_label = tk.Label(distance_header, textvariable=self.distance_info_var,
                                font=("Segoe UI", 9), foreground="#ffaa00", bg="#1e1e1e")
        distance_info_label.pack(side="left")
        
        # Database info on same line, right-aligned
        self.db_info_var = tk.StringVar(value="Total: ... hotspots in ... systems")
        db_info_label = tk.Label(distance_header, textvariable=self.db_info_var,
                                font=("Segoe UI", 8, "italic"), foreground="#888888", bg="#1e1e1e")
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
        ttk.Label(search_frame, text="Reference System:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.system_var = tk.StringVar()
        self.system_entry = ttk.Entry(search_frame, textvariable=self.system_var, width=35)
        self.system_entry.bind('<Return>', lambda e: self.search_hotspots())
        self.system_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # For compatibility, current_system_var points to the same system_var
        self.current_system_var = self.system_var
        
        # Create frame for buttons (to pack them tightly)
        buttons_frame = ttk.Frame(search_frame)
        buttons_frame.grid(row=0, column=2, sticky="w", padx=(5, 0))
        
        # Auto-detect button (fills current system automatically) - with app color scheme
        auto_btn = tk.Button(buttons_frame, text="Use Current System", command=self._auto_detect_system,
                            bg="#4a3a2a", fg="#e0e0e0", 
                            activebackground="#5a4a3a", activeforeground="#ffffff",
                            relief="ridge", bd=1, padx=8, pady=4,
                            font=("Segoe UI", 8, "normal"), cursor="hand2")
        auto_btn.pack(side="left", padx=(0, 5))
        
        # Search button - with app color scheme
        self.search_btn = tk.Button(buttons_frame, text="Search", command=self.search_hotspots,
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
        
        self.auto_search_cb = tk.Checkbutton(buttons_frame, text="Auto-Search", 
                                           variable=self.auto_search_var,
                                           command=self._save_auto_search_state,
                                           bg="#1e1e1e", fg="#e0e0e0", 
                                           activebackground="#2e2e2e", activeforeground="#ffffff",
                                           selectcolor="#1e1e1e", relief="flat",
                                           font=("Segoe UI", 8, "normal"))
        self.auto_search_cb.pack(side="left")
        
        # Tooltip for auto-search
        ToolTip(self.auto_search_cb, 
               "Automatically search for hotspots when arriving in a new system.\n"
               "Uses your last search settings (ring type, mineral, distance).\n"
               "Updates reference system from game status.")

        # Ring Type filter
        ttk.Label(search_frame, text="Ring Type:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.material_var = tk.StringVar(value="All")
        material_combo = ttk.Combobox(search_frame, textvariable=self.material_var, width=22, state="readonly")
        material_combo['values'] = ("All", "Metallic", "Rocky", "Icy", "Metal Rich")
        material_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # Material filter (new - specific materials) - dynamically populated from database
        ttk.Label(search_frame, text="Mineral:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.specific_material_var = tk.StringVar(value=RingFinder.ALL_MINERALS)
        specific_material_combo = ttk.Combobox(search_frame, textvariable=self.specific_material_var, width=22, state="readonly")
        
        # Get materials from database and sort alphabetically
        available_materials = self._get_available_materials()
        specific_material_combo['values'] = available_materials
        specific_material_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Add tooltips for the filters
        ToolTip(material_combo, "Filter by ring type:\n- Metallic: Platinum, Gold, Silver\n- Icy: LTDs, Tritium, Bromellite\n- Rocky: Alexandrite, Benitoite, Opals\n- Metal Rich: Painite, Osmium")
        ToolTip(specific_material_combo, "Filter by specific material:\nAutomatically shows only confirmed hotspots\n(no theoretical ring data)")
        
        # Create a sub-frame for right-side filters (row 1-2) that will pack tightly
        right_filters_frame_row1 = ttk.Frame(search_frame)
        right_filters_frame_row1.grid(row=1, column=2, columnspan=2, sticky="w", padx=(10, 0))
        
        right_filters_frame_row2 = ttk.Frame(search_frame)
        right_filters_frame_row2.grid(row=2, column=2, columnspan=2, sticky="w", padx=(10, 0))
        
        # Distance filter (now a dropdown) - in sub-frame with fixed label width
        ttk.Label(right_filters_frame_row1, text="Max Distance (LY):", width=15, anchor="e").pack(side="left", padx=(0, 5))
        self.distance_var = tk.StringVar(value="50")
        distance_combo = ttk.Combobox(right_filters_frame_row1, textvariable=self.distance_var, width=8, state="readonly")
        distance_combo['values'] = ("10", "50", "100", "150", "200", "300")
        distance_combo.pack(side="left")
        
        # Max Results filter - in sub-frame with fixed label width to align dropdowns
        ttk.Label(right_filters_frame_row2, text="Max Results:", width=15, anchor="e").pack(side="left", padx=(0, 5))
        self.max_results_var = tk.StringVar(value="30")
        max_results_combo = ttk.Combobox(right_filters_frame_row2, textvariable=self.max_results_var, width=8, state="readonly")
        max_results_combo['values'] = ("10", "20", "30", "50", "100", "All")
        max_results_combo.pack(side="left", padx=(0, 10))
        
        # Min Hotspots filter (only active for specific materials) - in sub-frame
        ttk.Label(right_filters_frame_row2, text="Min Hotspots:", width=12, anchor="e").pack(side="left", padx=(0, 5))
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
        ToolTip(self.min_hotspots_spinbox, "Minimum hotspot count filter\nOnly shows rings with X or more hotspots\n(Only active when specific mineral is selected)")
        
        # NOW bind material selection to enable/disable min hotspots filter (after spinbox exists!)
        specific_material_combo.bind('<<ComboboxSelected>>', self._on_material_changed)
        
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
        ToolTip(distance_combo, "Maximum search radius in light years\nRecommended: 10-50 LY for better performance\nLarger distances may take longer to search")
        
        # Search limitations info text (bottom of search controls)
        info_text = tk.Label(search_frame, 
                            text="ℹ Search covers bubble systems. Data grows as you scan and import history  |  'No data' = Information not available",
                            fg="#cccccc", bg="#1e1e1e", font=("Segoe UI", 8, "italic"), 
                            justify="left")
        info_text.grid(row=4, column=0, columnspan=4, sticky="w", padx=5, pady=(5, 5))
        
        # Results section with help text in header
        results_header = ttk.Frame(self.scrollable_frame)
        results_header.pack(fill="x", padx=10, pady=(2, 0))
        
        ttk.Label(results_header, text="Search Results", font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Label(results_header, text="Right-click rows for options", 
                 font=("Segoe UI", 8), foreground="#666666").pack(side="right", padx=(0, 5))
        
        results_frame = ttk.Frame(self.scrollable_frame)
        results_frame.pack(fill="both", expand=True, padx=10, pady=(2, 2))
        
        # Create frame for treeview with scrollbars
        tree_frame = ttk.Frame(results_frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(5, 2))
        
        # Results treeview with enhanced columns including source
        columns = ("Distance", "LS", "System", "Visited", "Planet/Ring", "Ring Type", "Hotspots", "Density")
        self.results_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        # Set column widths - similar to EDTOOLS layout
        column_widths = {
            "Distance": 60,
            "LS": 80,
            "System": 170,
            "Planet/Ring": 100,
            "Ring Type": 120,
            "Hotspots": 150,  # Reduced from 200 to 150
            "Visited": 60,
            "Density": 110
        }
        
        for col in columns:
            self.results_tree.heading(col, text=col, command=lambda c=col: self._sort_column(c, False))
            
            # Configure columns with minwidth and stretch like reports tab
            if col == "Distance":
                self.results_tree.column(col, width=column_widths[col], minwidth=50, anchor="center", stretch=False)
            elif col == "System":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="w", stretch=False)
            elif col == "Planet/Ring":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="center", stretch=False)
            elif col == "Ring Type":
                self.results_tree.column(col, width=column_widths[col], minwidth=80, anchor="center", stretch=False)
            elif col == "Hotspots":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="center", stretch=False)
            elif col == "Visited":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="center", stretch=False)
            elif col == "LS":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="center", stretch=False)
            elif col == "Density":
                self.results_tree.column(col, width=column_widths[col], minwidth=90, anchor="center", stretch=True)
        
        # Load saved column widths from config
        try:
            from config import load_ring_finder_column_widths
            saved_widths = load_ring_finder_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
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
        
        print("DEBUG: setup_ui completed successfully")
    
    def _sort_column(self, col, reverse):
        """Sort treeview column"""
        # Get all rows
        data = [(self.results_tree.set(child, col), child) for child in self.results_tree.get_children('')]
        
        # Sort data - handle numeric columns specially
        if col in ["Distance", "Hotspots", "LS", "Density"]:
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
                
                info_text = f"Total: {hotspots_str} hotspots in {systems_str} systems"
                print(f"[DB INFO] Setting text: {info_text}")
                self.db_info_var.set(info_text)
        except Exception as e:
            print(f"[DB INFO] Error updating database info: {e}")
            import traceback
            traceback.print_exc()
            self.db_info_var.set("Total: ... hotspots in ... systems")
    
    def _on_canvas_configure(self, event):
        """Handle canvas resize to make scrollable frame fill canvas dimensions"""
        canvas_width = event.width
        canvas_height = event.height
        # Make scrollable frame fill entire canvas area
        self.canvas.itemconfig(self.canvas.find_all()[0], width=canvas_width, height=canvas_height)
    
    def _get_available_materials(self):
        """Get alphabetically sorted list of available materials from database"""
        try:
            import sqlite3
            materials = [RingFinder.ALL_MINERALS]  # Always start with RingFinder.ALL_MINERALS
            
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
            return (RingFinder.ALL_MINERALS, "Alexandrite", "Benitoite", "Bromellite", "Grandidierite", 
                   "Low Temp Diamonds", "Monazite", "Musgravite", "Painite", 
                   "Platinum", "Rhodplumsite", "Serendibite", "Tritium", "Void Opals")
    
    def _on_material_changed(self, event=None):
        """Enable/disable min hotspots filter AND update confirmed checkbox based on material selection"""
        selected_material = self.specific_material_var.get()
        
        print(f"[DEBUG] Material changed to: '{selected_material}'")
        
        if selected_material == RingFinder.ALL_MINERALS:
            # Disable min hotspots filter for "All Minerals" - disabled state prevents interaction
            self.min_hotspots_spinbox.configure(state="disabled")
            self.min_hotspots_var.set(1)  # Reset to default (IntVar)
            print(f"[DEBUG] Min Hotspots DISABLED")
            
            # Enable confirmed checkbox for user control
            if hasattr(self, 'confirmed_checkbox') and self.confirmed_checkbox:
                self.confirmed_checkbox.configure(state="normal", fg="#cccccc")
        else:
            # Enable for specific materials - normal state allows arrow clicks and typing
            self.min_hotspots_spinbox.configure(state="normal")
            print(f"[DEBUG] Min Hotspots ENABLED")
            
            # Material selected - force confirmed hotspots and disable checkbox
            if hasattr(self, 'confirmed_only_var'):
                self.confirmed_only_var.set(True)
            if hasattr(self, 'confirmed_checkbox') and self.confirmed_checkbox:
                self.confirmed_checkbox.configure(state="disabled", fg="#888888")
    
    def _format_material_for_display(self, material_name: str) -> str:
        """Format material name for display in dropdown"""
        # Convert database names to user-friendly display names
        display_mapping = {
            'Low Temperature Diamonds': 'Low Temp Diamonds',  # Shorten for dropdown
            'LowTemperatureDiamond': 'Low Temp Diamonds',     # Handle old format
            'Opal': 'Void Opals'  # Since these are void opal hotspots
        }
        
        return display_mapping.get(material_name, material_name)
        
    def _preload_data(self):
        """Preload systems data in background"""
        try:
            self.status_var.set("Loading systems database...")
            self._load_systems_cache()
            self.parent.after(0, lambda: self.status_var.set("Ready - Community database loaded"))
        except Exception as e:
            self.parent.after(0, lambda: self.status_var.set(f"Error loading database: {e}"))
    
            
    def _update_sol_distance(self, system_name: str):
        """Update distance info label for reference system (Sol, Home, FC)"""
        if not self.distance_calculator or not system_name:
            self.distance_info_var.set("➤ Sol: --- | Home: --- | FC: ---")
            return
        
        try:
            # Get main app to access Distance Calculator variables
            main_app = None
            if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, 'main_app'):
                main_app = self.prospector_panel.main_app
            
            if not main_app:
                self.distance_info_var.set("➤ Sol: --- | Home: --- | Fleet Carrier: ---")
                return
            
            # Get Sol distance
            sol_dist, _ = self.distance_calculator.get_distance_to_sol(system_name)
            sol_text = f"{sol_dist:.2f} LY" if sol_dist is not None else "---"
            
            # Get Home distance - use SAME variable as Distance Calculator
            home_system = main_app.distance_home_system.get().strip() if hasattr(main_app, 'distance_home_system') else ""
            if home_system:
                home_dist, _, _ = self.distance_calculator.get_distance_between_systems(system_name, home_system)
                home_text = f"{home_dist:.2f} LY" if home_dist is not None else "---"
            else:
                home_text = "---"
            
            # Get FC distance - use SAME variable as Distance Calculator
            fc_system = main_app.distance_fc_system.get().strip() if hasattr(main_app, 'distance_fc_system') else ""
            if fc_system:
                fc_dist, _, _ = self.distance_calculator.get_distance_between_systems(system_name, fc_system)
                fc_text = f"{fc_dist:.2f} LY" if fc_dist is not None else "---"
            else:
                fc_text = "---"
            
            # Update label (values only)
            self.distance_info_var.set(f"➤ Sol: {sol_text} | Home: {home_text} | Fleet Carrier: {fc_text}")
        except Exception as e:
            print(f"Warning: Failed to calculate distances: {e}")
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
                self.status_var.set(f"Current system: {current_system}")
                # Check if coordinates exist in cache
                coords = self.systems_data.get(current_system.lower())
                if not coords:
                    self.status_var.set(f"Current system: {current_system} (coordinates not available)")
                else:
                    self.status_var.set(f"Current system: {current_system}")
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
                                self.status_var.set(f"Current system: {system_name}")
                            else:
                                self.status_var.set(f"Current system: {system_name} (coordinates not available)")
                        else:
                            self.status_var.set(f"Current system: {system_name}")
                        return
            
            # Last resort: check latest journal file
            journal_files = glob.glob(os.path.join(ed_folder, "Journal.*.log"))
            if journal_files:
                latest_journal = max(journal_files, key=os.path.getmtime)
                system_name = self._get_system_from_journal(latest_journal)
                if system_name:
                    self.current_system_var.set(system_name)
                    self.status_var.set(f"Current system: {system_name}")
                    return
            
            self.status_var.set("Could not detect current system - Elite Dangerous not running?")
            
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
                
                print(f"✓ Database verification successful on attempt {attempt + 1}")
                self.db_ready = True
                return True
                
            except sqlite3.OperationalError as e:
                print(f"⚠ Database not ready (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(0.5)  # Wait before retry
                else:
                    print(f"❌ Database verification failed after {max_retries} attempts")
                    self.db_ready = False
                    return False
            except Exception as e:
                print(f"❌ Unexpected database error: {e}")
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
            if specific_material != RingFinder.ALL_MINERALS:
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
            
            settings = {
                "ring_type": self.material_var.get(),
                "specific_material": self.specific_material_var.get(),
                "distance": self.distance_var.get(),
                "max_results": self.max_results_var.get(),
                "min_hotspots": self.min_hotspots_var.get()
            }
            
            save_ring_finder_filters(settings)
            print(f"DEBUG: Saved ring finder settings: {settings}")
            
        except Exception as e:
            print(f"DEBUG: Error saving ring finder settings: {e}")
    
    def _load_filter_settings(self):
        """Load filter settings from config"""
        try:
            from config import load_ring_finder_filters
            
            settings = load_ring_finder_filters()
            if not settings:
                return
            
            # Restore settings
            if "ring_type" in settings:
                self.material_var.set(settings["ring_type"])
            if "specific_material" in settings:
                self.specific_material_var.set(settings["specific_material"])
            if "distance" in settings:
                self.distance_var.set(settings["distance"])
            if "max_results" in settings:
                self.max_results_var.set(settings["max_results"])
            if "min_hotspots" in settings:
                self.min_hotspots_var.set(settings["min_hotspots"])
            
            print(f"DEBUG: Loaded ring finder settings: {settings}")
            
        except Exception as e:
            print(f"DEBUG: Error loading ring finder settings: {e}")
    
    def search_hotspots(self, auto_refresh=False):
        """Search for mining hotspots using reference system as center point
        
        Args:
            auto_refresh: True if called from auto-refresh after scanning, False for manual search
        """
        self._is_auto_refresh = auto_refresh
        print(f"[SEARCH DEBUG] search_hotspots() called (auto_refresh={auto_refresh})")
        
        reference_system = self.system_var.get().strip()
        print(f"[SEARCH DEBUG] Reference system: '{reference_system}'")
        
        # Update Sol distance for reference system
        self._update_sol_distance(reference_system)
        
        material_filter = self.material_var.get()
        specific_material = self.specific_material_var.get()
        
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
        max_results = None if max_results_str == "All" else int(max_results_str)
        
        # Auto-enable confirmed hotspots when filtering by specific material
        if specific_material != RingFinder.ALL_MINERALS:
            confirmed_only = True
            print(f" DEBUG: Material filter active - auto-enabling confirmed hotspots only")

        print(f" SEARCH DEBUG: Ring Type='{material_filter}', Material='{specific_material}', Confirmed Only={confirmed_only}")
        # self._log_debug(f"SEARCH: RingType='{material_filter}', Material='{specific_material}', ConfirmedOnly={confirmed_only}, ReferenceSystem='{reference_system}', MaxDistance={max_distance}")

        if not reference_system:
            self.status_var.set("Please enter a reference system or use 'Use Current System'")
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
            # Try to get coordinates from galaxy database first, then EDSM as last resort
            galaxy_coords = self._get_system_coords_from_galaxy_db(reference_system)
            if galaxy_coords:
                self.current_system_coords = galaxy_coords
                print(f" DEBUG: Using galaxy database coordinates for '{reference_system}'")
            else:
                # Only use EDSM as final fallback
                # EDSM disabled - only use galaxy database as fallback
                # self.current_system_coords = self._get_system_coords_from_edsm(reference_system)
                if self.current_system_coords:
                    print(f" DEBUG: Using EDSM coordinates for '{reference_system}' (galaxy db not available)")

            if not self.current_system_coords:
                self.status_var.set(f"Warning: '{reference_system}' coordinates not found - distances may be inaccurate")

        # Get min hotspots filter (only valid for specific materials)
        min_hotspots = 1  # Default
        if specific_material != RingFinder.ALL_MINERALS:
            try:
                min_hotspots = int(self.min_hotspots_var.get())
                if min_hotspots < 1:
                    min_hotspots = 1
            except (ValueError, AttributeError):
                min_hotspots = 1
        
        # Disable search button
        self.search_btn.configure(state="disabled", text="Searching...")
        self.status_var.set("⏳ Searching for rings...")

        # Run search in background - pass reference system coords and max results to worker
        threading.Thread(target=self._search_worker,
                        args=(reference_system, material_filter, specific_material, confirmed_only, max_distance, self.current_system_coords, max_results, min_hotspots),
                        daemon=True).start()
        
    def _search_worker(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, reference_coords, max_results, min_hotspots: int = 1):
        """Background worker for hotspot search"""
        try:
            # Wait for database to be ready (with timeout)
            import time
            wait_start = time.time()
            while not self.db_ready and (time.time() - wait_start) < 5.0:
                time.sleep(0.1)
            
            if not self.db_ready:
                print("⚠ Database not ready, search may return incomplete results")
            
            # Set the reference system coords for this worker thread
            self.current_system_coords = reference_coords
            hotspots = self._get_hotspots(reference_system, material_filter, specific_material, confirmed_only, max_distance, max_results)
            
            # Apply min hotspots filter if needed
            if min_hotspots > 1 and specific_material != RingFinder.ALL_MINERALS:
                original_count = len(hotspots)
                hotspots = [h for h in hotspots if h.get('count', 1) >= min_hotspots]
                filtered_count = len(hotspots)
                if filtered_count < original_count:
                    print(f" DEBUG: Min hotspots filter ({min_hotspots}+): {original_count} -> {filtered_count} results")
            
            # Apply max_results limit AFTER min_hotspots filtering
            if max_results and len(hotspots) > max_results:
                print(f" DEBUG: Limiting results from {len(hotspots)} to {max_results} (after min_hotspots filter)")
                hotspots = hotspots[:max_results]
            
            # EDSM FALLBACK: Smart throttling to prevent hanging
            # Small searches: Query all systems
            # Large searches: Query only first 30 systems for top results
            if hotspots and len(hotspots) < 100:
                print(f"[AUTO-REFRESH DEBUG] Running EDSM fallback for all {len(hotspots)} hotspots")
                self._fill_missing_metadata_edsm(hotspots)
            elif hotspots and len(hotspots) >= 100:
                print(f"[AUTO-REFRESH DEBUG] Large search ({len(hotspots)} hotspots) - limiting EDSM to first 30 systems")
                self._fill_missing_metadata_edsm(hotspots, max_systems=30)
            else:
                print(f"[AUTO-REFRESH DEBUG] No hotspots found, skipping EDSM fallback")
            
            # Update UI in main thread
            self.parent.after(0, self._update_results, hotspots)
            
        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            self.parent.after(0, self._show_error, error_msg)
        finally:
            # Re-enable search button
            self.parent.after(0, lambda: self.search_btn.configure(state="normal", text="Search"))
    
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
            print(f"[EDSM DEBUG] Starting EDSM fallback check for {len(hotspots)} hotspots (max_systems={max_systems})")
            
            # Build set of systems with incomplete rings in THIS result set only
            systems_needing_data = set()
            for hotspot in hotspots:
                system_name = hotspot.get('systemName')
                ring_type = hotspot.get('ring_type')
                ls_distance = hotspot.get('ls_distance')
                
                print(f"[EDSM DEBUG] Hotspot: {system_name} - Ring Type: {ring_type}, LS: {ls_distance}")
                
                if ring_type is None or ls_distance is None:
                    if system_name:
                        systems_needing_data.add(system_name)
                        print(f"[EDSM DEBUG] System {system_name} needs metadata (missing ring_type={ring_type is None}, ls_distance={ls_distance is None})")
            
            if not systems_needing_data:
                # All metadata complete in this result set
                print(f"[EDSM DEBUG] All metadata complete, no EDSM query needed")
                return
            
            # Apply max_systems limit if specified (for large searches)
            systems_to_query = list(systems_needing_data)
            if max_systems and len(systems_to_query) > max_systems:
                systems_to_query = systems_to_query[:max_systems]
                print(f"[EDSM] {len(systems_needing_data)} systems need metadata, limiting to first {max_systems} systems")
            else:
                print(f"[EDSM] {len(systems_needing_data)} systems in results need metadata, querying EDSM...")
            
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
    
    def _get_hotspots(self, reference_system: str, material_filter: str, specific_material: str, confirmed_only: bool, max_distance: float, max_results: int = None) -> List[Dict]:
        """Get hotspot data using user database only - no EDSM dependencies"""
        print(f"DEBUG: Searching user database for {material_filter} rings with {specific_material}, confirmed_only={confirmed_only}")
        # self._log_debug(f"_get_hotspots: Searching user database for RingType='{material_filter}', Material='{specific_material}', ConfirmedOnly={confirmed_only}, ReferenceSystem='{reference_system}', MaxDistance={max_distance}")
        
        # Use user database-only approach for all searches
        print(f"DEBUG: Using user database-only approach")
        user_results = self._search_user_database_first(reference_system, material_filter, specific_material, max_distance, max_results)
        
        if user_results:
            # Get user database results
            return user_results
        else:
            print(f"DEBUG: No results found in user database for {specific_material}")
            # self._log_debug(f"ZERO_RESULTS: No results found for RingType='{material_filter}', Material='{specific_material}', ReferenceSystem='{reference_system}', MaxDistance={max_distance}")
            return []
    
    def _search_user_database_first(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float, max_results: int = None) -> List[Dict]:
        """Search user database first for confirmed hotspots, return results in _update_results compatible format"""
        try:
            print(f" DEBUG: User database-first search for {specific_material} within {max_distance} LY")
            
            # Get user database hotspots
            user_hotspots = self._get_user_database_hotspots(reference_system, material_filter, specific_material, max_distance)
            print(f" DEBUG: Found {len(user_hotspots)} user database hotspots")
            
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
                if specific_material != RingFinder.ALL_MINERALS and not self._material_matches(specific_material, material_name):
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
            
            print(f" DEBUG: Converted {len(compatible_results)} user database hotspots to compatible format")
            return compatible_results
            
        except Exception as e:
            print(f" DEBUG: User database-first search failed: {e}")
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
                            if specific_material != RingFinder.ALL_MINERALS:
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
                if material_filter == RingFinder.ALL_MINERALS:
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
                                distance = self._calculate_distance(self.current_system_coords, system_coords)
                                distance = round(distance, 1)
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
                    print(f" DEBUG: Limited user database results to {max_user_results}")
                
                print(f" DEBUG: Returning {len(user_hotspots)} user database hotspots")
                return user_hotspots
                
        except Exception as e:
            print(f" DEBUG: User database search failed: {e}")
            return []
    
    def _get_user_database_hotspots(self, reference_system: str, material_filter: str, specific_material: str, max_distance: float) -> List[Dict]:
        """Search user database for hotspots - pure user database approach without EDSM"""
        print(f"DEBUG: Searching user database only for ring type '{material_filter}' with material '{specific_material}'")
        
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
                        print(f"🔍 [PRIORITY] Found {len(systems_with_hotspots)} systems with hotspots in database")
                        
                        # Separate systems into priority (has hotspots) and non-priority
                        priority_systems = [s for s in systems_in_range if s in systems_with_hotspots]
                        non_priority_systems = [s for s in systems_in_range if s not in systems_with_hotspots]
                        
                        print(f"🔍 [PRIORITY] {len(priority_systems)} priority systems (have hotspots)")
                        print(f"🔍 [PRIORITY] {len(non_priority_systems)} non-priority systems")
                        
                        # Cap non-priority systems to prevent search hanging, but keep ALL priority systems
                        LIMIT = 5000
                        if len(priority_systems) + len(non_priority_systems) > LIMIT:
                            slots_remaining = max(0, LIMIT - len(priority_systems))
                            non_priority_systems = non_priority_systems[:slots_remaining]
                            print(f"🔍 [PRIORITY] Keeping all {len(priority_systems)} priority systems + {len(non_priority_systems)} non-priority = {len(priority_systems) + len(non_priority_systems)} total")
                        
                        # Combine: priority systems first, then non-priority
                        systems_in_range = priority_systems + non_priority_systems
                        
                        # Always include reference system itself (distance = 0 LY)
                        if reference_system not in systems_in_range:
                            systems_in_range.append(reference_system)
                            print(f" DEBUG: Added reference system '{reference_system}' to search list (0 LY)")
                        
                        print(f" DEBUG: Pre-filtered to {len(systems_in_range)} systems within {max_distance} LY (prioritized hotspot systems)")
                
                # Build optimized query based on whether we have a system filter
                if systems_in_range:
                    # SQLite has a limit of 999 variables per query, so batch if needed
                    BATCH_SIZE = 999
                    all_results = []
                    
                    for i in range(0, len(systems_in_range), BATCH_SIZE):
                        batch = systems_in_range[i:i + BATCH_SIZE]
                        placeholders = ','.join(['?'] * len(batch))
                        
                        # Different query for ALL_MINERALS vs specific material
                        if specific_material == RingFinder.ALL_MINERALS:
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
                    if specific_material == RingFinder.ALL_MINERALS:
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
                        print(f" DEBUG: Found {len(results)} systems matching '{reference_system}'")
                    else:
                        print(f"❌ No systems found matching '{reference_system}' - search complete")
                        # Update status to show no results found
                        try:
                            self.status_label.config(text=f"No systems found within search criteria for '{reference_system}'. Try adjusting your search terms.")
                        except:
                            pass
                        return []
                
                print(f" DEBUG: Found {len(results)} total hotspot entries, will filter by material using smart matching")
                
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
                        if specific_material != RingFinder.ALL_MINERALS and not self._material_matches(specific_material, material_name):
                            continue
                        
                        # Use ring type from database - no fallback needed
                        ring_type = ring_type_db if ring_type_db else "No data"
                        
                        # Normalize ring type spelling (handle typo in database)
                        if ring_type == "Metalic":
                            ring_type = "Metallic"
                        
                        # Filter by ring type
                        if material_filter != "All" and ring_type != material_filter:
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
                            distance = self._calculate_distance(reference_coords, system_coords)
                        elif not coords_available:
                            systems_without_coords += 1
                        
                        # Apply distance filtering if reference coordinates are available
                        if reference_coords and coords_available:
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
                        if specific_material == RingFinder.ALL_MINERALS:
                            display_material_name = self._abbreviate_material_for_display(material_name)
                        else:
                            display_material_name = material_name
                        
                        hotspot_entry = {
                            'systemName': system_name,
                            'bodyName': body_name,
                            'type': display_material_name,
                            'count': hotspot_count,
                            'distance': round(distance, 1) if distance < 999 else 999.9,
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
                        
                    except Exception as e:
                        print(f" DEBUG: Error processing {system_name}: {e}")
                        continue
                
                # Sort by distance first, then LS distance for practical mining workflow
                if material_filter != RingFinder.ALL_MINERALS:
                    # For specific materials, prioritize by hotspot count, then distance, then LS
                    user_hotspots.sort(key=lambda x: (-x['count'], x['distance'], x.get('ls_distance', 999999)))
                else:
                    # For All Minerals, sort by distance, then LS distance (closest arrival points first)
                    user_hotspots.sort(key=lambda x: (x['distance'], x.get('ls_distance', 999999)))
                
                print(f" DEBUG: Material matches: {material_matches}")
                print(f" DEBUG: Applied filters - Ring Type: '{material_filter}', Material: '{specific_material}'")
                print(f" DEBUG: Systems with coordinates: {systems_with_coords}, without coordinates: {systems_without_coords}")
                print(f" DEBUG: Distance filter: {max_distance} LY from {reference_system or 'current system'}")
                
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
                        print(f" DEBUG: Successfully saved {len(coords_to_update)} coordinates to database")
                    except Exception as update_error:
                        print(f" DEBUG: Error saving coordinates to database: {update_error}")
                
                print(f" DEBUG: Returning {len(user_hotspots)} user database hotspots after filtering")
                return user_hotspots
                
        except Exception as e:
            print(f" DEBUG: User database search failed: {e}")
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
            
            print(f"🔍 [DEBUG 300LY] _find_systems_in_range called with max_distance={max_distance}")
            print(f"🔍 [DEBUG 300LY] Reference coords: {reference_coords}")
            
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
                
                print(f"🔍 [DEBUG 300LY] Bounding box: X[{x_min:.2f}, {x_max:.2f}] Y[{y_min:.2f}, {y_max:.2f}] Z[{z_min:.2f}, {z_max:.2f}]")
                
                # Add LIMIT to prevent query timeout on large searches
                cursor.execute("""
                    SELECT name, x, y, z FROM systems 
                    WHERE x BETWEEN ? AND ? 
                    AND y BETWEEN ? AND ? 
                    AND z BETWEEN ? AND ?
                    LIMIT 50000
                """, (x_min, x_max, y_min, y_max, z_min, z_max))
                
                results = cursor.fetchall()
                print(f"🔍 [DEBUG 300LY] Galaxy database returned {len(results)} systems from cube query")
                
                # Calculate actual distance and filter - store as (name, distance) tuples
                systems_with_distances = []
                col_359_found = False
                for name, x, y, z in results:
                    system_coords = {'x': x, 'y': y, 'z': z}
                    distance = self._calculate_distance(reference_coords, system_coords)
                    
                    # Debug for Col 359 system
                    if "Col 359 Sector IG-X d1-90" in name:
                        col_359_found = True
                        print(f"🔍 [DEBUG 300LY] Found 'Col 359 Sector IG-X d1-90' in cube results at distance {distance:.2f} LY")
                        print(f"🔍 [DEBUG 300LY] System coords: X={x:.2f}, Y={y:.2f}, Z={z:.2f}")
                    
                    if distance <= max_distance:
                        systems_with_distances.append((name, distance))
                        if "Col 359 Sector IG-X d1-90" in name:
                            print(f"🔍 [DEBUG 300LY] ✅ 'Col 359 Sector IG-X d1-90' PASSED distance filter ({distance:.2f} <= {max_distance})")
                    else:
                        if "Col 359 Sector IG-X d1-90" in name:
                            print(f"🔍 [DEBUG 300LY] ❌ 'Col 359 Sector IG-X d1-90' FAILED distance filter ({distance:.2f} > {max_distance})")
                
                if not col_359_found:
                    print(f"🔍 [DEBUG 300LY] ⚠️ 'Col 359 Sector IG-X d1-90' NOT FOUND in cube query results")
                
                # Sort by distance (closest first) before converting to name-only list
                systems_with_distances.sort(key=lambda x: x[1])
                systems_in_range = [name for name, dist in systems_with_distances]
                        
                print(f"🔍 [DEBUG 300LY] Found {len(systems_in_range)} systems within {max_distance} LY using galaxy database (sorted by distance)")
                
                # Debug: Check if Col 359 is in final list
                if "Col 359 Sector IG-X d1-90" in systems_in_range:
                    print(f"🔍 [DEBUG 300LY] ✅ 'Col 359 Sector IG-X d1-90' IS in final systems_in_range list")
                else:
                    print(f"🔍 [DEBUG 300LY] ❌ 'Col 359 Sector IG-X d1-90' NOT in final systems_in_range list")
                
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
                        
                        if user_systems_in_range > 0:
                            print(f" DEBUG: Added {user_systems_in_range} systems from user database (visited systems)")
                            
                except Exception as user_e:
                    print(f" DEBUG: Error checking user database for systems in range: {user_e}")
                
                return systems_in_range
                        
        except Exception as e:
            print(f" DEBUG: Error finding systems in range: {e}")
            
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
        print(f"DEBUG: _update_results called with {len(hotspots)} hotspots")
        # self._log_debug(f"_update_results called with {len(hotspots)} hotspots")
        if len(hotspots) == 0:
            # self._log_debug("_update_results: ZERO_RESULTS - No hotspots to display for current search.")
            print(f"DEBUG: ZERO_RESULTS - No hotspots to display for current search.")
        
        # Track current results to identify new entries
        current_results = set()
        for hotspot in hotspots:
            system_name = hotspot.get("systemName", hotspot.get("system", ""))
            body_name = hotspot.get("bodyName", hotspot.get("body", ""))
            current_results.add((system_name, body_name))
        
        # Identify new entries (only highlight during auto-refresh, not manual searches)
        is_auto = hasattr(self, '_is_auto_refresh') and self._is_auto_refresh
        print(f"DEBUG: is_auto_refresh={is_auto}, hasattr={hasattr(self, '_is_auto_refresh')}, value={getattr(self, '_is_auto_refresh', None)}")
        
        if is_auto:
            new_entries = current_results - self.previous_results
            self._is_auto_refresh = False  # Reset flag
            print(f"DEBUG: AUTO-REFRESH - Comparing {len(current_results)} current vs {len(self.previous_results)} previous")
        else:
            new_entries = set()
        print(f"DEBUG: Found {len(new_entries)} new entries to highlight")
        
        # Clear existing results completely
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        
        # Force UI refresh
        self.results_tree.update()
        
        # Debug: Check what hotspots are being processed
        delkar_7a_entries = [h for h in hotspots if h.get('systemName') == 'Delkar' and '7 A' in h.get('bodyName', '')]
        if delkar_7a_entries:
            print(f"DEBUG: Processing {len(delkar_7a_entries)} Delkar 7A hotspots in _update_results:")
            for i, entry in enumerate(delkar_7a_entries):
                material = entry.get('type', 'No data')
                ring_type = entry.get('ring_type', 'Missing')
                source = entry.get('data_source', 'No data')
                # Check all ring-related fields
                hotspot_data = entry.get('hotspot_data', {})
                body_name = entry.get('bodyName', 'No data')
                distance = entry.get('distance', 'No data')
                print(f"  [{i+1}] Material: {material} | Ring Type: {ring_type} | Body: {body_name} | Distance: {distance} | Source: {source}")
                if hotspot_data:
                    print(f"      Hotspot Data Ring Type: {hotspot_data.get('ring_type', 'Missing')}")
        
        print(f"DEBUG: Total hotspots to process: {len(hotspots)}")
        
        print(f"DEBUG: Updating UI with {len(hotspots)} fresh results")
        
        # Debug: Check ring types in hotspots data
        delkar_7a_entries = [h for h in hotspots if h.get('systemName') == 'Delkar' and '7 A' in h.get('bodyName', '')]
        if delkar_7a_entries:
            print(f"DEBUG: Delkar 7A entries found: {len(delkar_7a_entries)}")
            for i, entry in enumerate(delkar_7a_entries):
                material = entry.get('type', 'No data')
                ring_type = entry.get('ring_type', 'Missing')
                source = entry.get('data_source', 'No data')
                print(f"  [{i+1}] {material} -> ring_type: {ring_type} | source: {source}")
                
            # Check for duplicates
            unique_materials = set()
            duplicates = []
            for entry in delkar_7a_entries:
                material = entry.get('type')
                if material in unique_materials:
                    duplicates.append(material)
                else:
                    unique_materials.add(material)
            if duplicates:
                print(f"DEBUG: Duplicate materials found: {duplicates}")
            
        # Sort by distance, then system name, then ring name for predictable ordering
        try:
            hotspots.sort(key=lambda x: (
                float(x.get('distance', 999)),           # Primary: Distance (closest first)
                x.get('systemName', x.get('system', '')).lower(),  # Secondary: System name (alphabetical)
                x.get('bodyName', x.get('ring', '')).lower()       # Tertiary: Ring name (alphabetical)
            ))
        except:
            pass
            
        # Add new results with hotspots column
        # Process each hotspot for UI display
        loop_counter = 0
        for hotspot in hotspots:
            loop_counter += 1
            system_name = hotspot.get("systemName", hotspot.get("system", ""))
            body_name = hotspot.get("bodyName", hotspot.get("body", ""))
            
            # Debug each loop iteration for Delkar 7 A
            if system_name == "Delkar" and "7 A" in body_name:
                hotspot_ring_type = hotspot.get("ring_type", "Missing")
                hotspot_material = hotspot.get("type", "Missing")
                hotspot_source = hotspot.get("data_source", "Missing")
                print(f"LOOP {loop_counter}: Processing {system_name} {body_name} -> ring_type: {hotspot_ring_type} | material: {hotspot_material} | source: {hotspot_source}")
            
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
            elif "count" in hotspot:
                # User database hotspots - show the count  
                hotspot_count_display = str(hotspot.get("count", "-"))
            else:
                # Pure EDSM ring composition data - show "-"
                hotspot_count_display = "-"
            
            # Check if player has visited this system
            visited_status = "Yes" if self.user_db.has_visited_system(system_name) else "No"
            
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
            
            # Check if this is a new entry and apply highlighting
            is_new = (system_name, ring_name) in new_entries
            tags = ('new_entry',) if is_new else ()
            
            item_id = self.results_tree.insert("", "end", values=(
                hotspot.get("distance", "No data"),
                ls_val,
                system_name,
                visited_status,
                ring_name,
                ring_type_val,
                hotspot_count_display,
                density_formatted
            ), tags=tags)
            
            # Store first new entry for scrolling
            if is_new and not hasattr(self, '_first_new_item'):
                self._first_new_item = item_id
            
        # Update status with source information 
        count = len(hotspots)
        search_term = self.system_var.get().strip()
        material_filter = self.material_var.get()
        
        if search_term:
            if material_filter != 'All':
                if count > 0:
                    status_msg = f"Found {count} {material_filter} location{'s' if count != 1 else ''} near '{search_term}'"
                else:
                    status_msg = f"No {material_filter} rings found within search criteria for '{search_term}'"
            else:
                if count > 0:
                    status_msg = f"Found {count} location{'s' if count != 1 else ''} near '{search_term}'"
                else:
                    status_msg = f"No rings found within search criteria for '{search_term}'"
        else:
            if material_filter != 'All':
                if count > 0:
                    status_msg = f"Found {count} {material_filter} ring{'s' if count != 1 else ''}"
                else:
                    status_msg = f"No {material_filter} rings found within current search parameters"
            else:
                if count > 0:
                    status_msg = f"Found {count} ring{'s' if count != 1 else ''}"
                else:
                    status_msg = f"No rings found within current search parameters"
            
        # Set status message
        self.status_var.set(status_msg)
        
        # Update previous results for next comparison
        self.previous_results = current_results
        
        # Auto-scroll to first new entry if found
        if hasattr(self, '_first_new_item'):
            self.results_tree.see(self._first_new_item)
            self.results_tree.selection_set(self._first_new_item)
            delattr(self, '_first_new_item')
        
        # Set timer to remove highlight after 10 seconds (reset if already running)
        if new_entries:
            if self.highlight_timer:
                self.parent.after_cancel(self.highlight_timer)
            self.highlight_timer = self.parent.after(10000, self._clear_highlights)
            
    def _show_error(self, error_msg: str):
        """Show error message and reset UI"""
        self.status_var.set("Search failed - check your search criteria")
        print(f"Hotspot search error: {error_msg}")
        # Clear results on error
        self.results_tree.delete(*self.results_tree.get_children())
    
    def _clear_highlights(self):
        """Remove highlight tags from all items (called after 10 seconds)"""
        for item in self.results_tree.get_children():
            # Remove the 'new_entry' tag from all items
            tags = list(self.results_tree.item(item, 'tags'))
            if 'new_entry' in tags:
                tags.remove('new_entry')
                self.results_tree.item(item, tags=tuple(tags))
        self.highlight_timer = None
        print("DEBUG: Highlights cleared")
    
    def _create_context_menu(self):
        """Create the right-click context menu for results"""
        self.context_menu = tk.Menu(self.parent, tearoff=0,
                                   bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                                   activebackground=MENU_COLORS["activebackground"], 
                                   activeforeground=MENU_COLORS["activeforeground"],
                                   selectcolor=MENU_COLORS["selectcolor"])
        self.context_menu.add_command(label="Copy System Name", command=self._copy_system_name)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Bookmark This Location", command=self._bookmark_selected)
    
    def _show_context_menu(self, event):
        """Show the context menu when right-clicking on results"""
        try:
            # Select the item under cursor
            item = self.results_tree.identify_row(event.y)
            if item:
                self.results_tree.selection_set(item)
                self.results_tree.focus(item)
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

            # Extract data from columns: Distance, LS, System, Visited, Ring, Ring Type, Hotspots, etc.
            system_name = values[2]  # System column
            ring_name = values[4]    # Ring column
            ring_type = values[5] if len(values) > 5 else ""  # Ring Type column
            hotspots = values[6] if len(values) > 6 else ""   # Hotspots column

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

            # Get access to the prospector panel's bookmark dialog
            if self.prospector_panel and hasattr(self.prospector_panel, '_show_bookmark_dialog'):
                # Show bookmark dialog with pre-filled ring data
                self.prospector_panel._show_bookmark_dialog({
                    'system': system_name,
                    'body': ring_name,  # Ring name as the body
                    'hotspot': ring_type,  # Ring type as hotspot info
                    'materials': materials,
                    'avg_yield': '',  # No yield data from ring finder
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
        """Convert abbreviated materials back to full names for bookmarks"""
        # Reverse mapping of abbreviations to full names
        expansions = {
            'Pt': 'Platinum', 'Pai': 'Painite', 'Ale': 'Alexandrite', 'Tri': 'Tritium',
            'LTD': 'Low Temperature Diamonds', 'VO': 'Void Opals', 'Rho': 'Rhodplumsite',
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
                
                print(f"[AUTO-SEARCH] Setup complete, monitoring journal events")
        except Exception as e:
            print(f"[AUTO-SEARCH] Failed to setup monitoring: {e}")

    def _check_journal_event_for_auto_search(self, line: str):
        """Check journal events for FSD jumps and trigger auto-search"""
        if not self.auto_search_var.get():
            return
            
        try:
            import json
            event = json.loads(line.strip())
            event_type = event.get("event", "")
            
            if event_type == "FSDJump":
                current_system = event.get("StarSystem")
                if current_system and current_system != self.last_monitored_system:
                    self.last_monitored_system = current_system
                    # Schedule auto-search in main thread
                    self.parent.after(1000, lambda: self._auto_search_new_system(current_system))
                    
        except Exception as e:
            pass  # Silent fail

    def _auto_search_new_system(self, system_name: str):
        """Auto-populate reference system and trigger search silently"""
        try:
            # Update reference system field
            self.system_var.set(system_name)
            
            # Trigger search with current settings - but only if not already searching
            if self.search_btn['state'] == 'normal':
                self.search_hotspots()
                
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

    def _startup_auto_search(self):
        """Perform auto-search on startup if enabled"""
        try:
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
