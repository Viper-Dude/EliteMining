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
    
    def __init__(self, parent_frame: ttk.Frame, prospector_panel=None, app_dir: Optional[str] = None):
        self.parent = parent_frame
        self.prospector_panel = prospector_panel  # Reference to get current system
        self.systems_data = {}  # System coordinates cache
        self.current_system_coords = None
        
        # Initialize local database manager
        self.local_db = LocalSystemsDatabase()
        
        # Initialize user database for hotspot data with correct app directory
        if app_dir:
            # Use provided app directory to construct database path
            data_dir = os.path.join(app_dir, "data")
            db_path = os.path.join(data_dir, "user_data.db")
            print(f"DEBUG: RingFinder using explicit database path: {db_path}")
            self.user_db = UserDatabase(db_path)
        else:
            # Fall back to default path resolution
            print("DEBUG: RingFinder using default database path resolution")
            self.user_db = UserDatabase()
            print(f"DEBUG: RingFinder actual database path: {self.user_db.db_path}")
        
        # Always use local database since it's now bundled with the application
        self.use_local_db = True
        
        self.setup_ui()
        # Load initial data in background
        threading.Thread(target=self._preload_data, daemon=True).start()
        
    def _abbreviate_material_for_display(self, hotspot_text: str) -> str:
        """Abbreviate material names in hotspot display text for Ring Finder column"""
        abbreviations = {
            'Platinum': 'Pt',
            'Palladium': 'Pd', 
            'Gold': 'Au',
            'Silver': 'Ag',
            'Osmium': 'Os',
            'Painite': 'Pai',
            'Alexandrite': 'Ale',
            'Rhodplumsite': 'Rhd',
            'Bixbite': 'Bix',
            'Grandidierite': 'Grd',
            'Monazite': 'Mon',
            'Musgravite': 'Mus',
            'Serendibite': 'Ser',
            'Taaffeite': 'Taa',
            'Jadeite': 'Jad',
            'Red Beryl': 'RBe',
            'Bromellite': 'Bro',
            'Tritium': 'Tri',
            'tritium': 'Tri',  # Handle lowercase variant
            'Bertrandite': 'Ber',
            'Indite': 'Ind',
            'Low Temperature Diamonds': 'LTD',
            'Low Temp. Diamonds': 'LTD',
            'Low Tem Diamond': 'LTD',  # Handle abbreviated form
            'Void Opals': 'VO',
            'Opals': 'VO'
        }
        
        # Replace full material names with abbreviations in the display text
        result = hotspot_text
        for full_name, abbr in abbreviations.items():
            result = result.replace(full_name, abbr)
        
        return result
        
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
        search_title = ttk.Label(search_header, text="Ring Search", font=("Segoe UI", 9, "bold"))
        search_title.pack(side="left")
        
        # Database status on the right
        self.status_var = tk.StringVar(value="Loading...")
        status_label = ttk.Label(search_header, textvariable=self.status_var, 
                                font=("Segoe UI", 8), foreground="#888888")
        status_label.pack(side="right")
        
        search_frame = ttk.Frame(self.scrollable_frame)
        search_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        # Single smart search input
        ttk.Label(search_frame, text="Reference System:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.system_var = tk.StringVar()
        self.system_entry = ttk.Entry(search_frame, textvariable=self.system_var, width=25)
        self.system_entry.bind('<Return>', lambda e: self.search_hotspots())
        self.system_entry.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # For compatibility, current_system_var points to the same system_var
        self.current_system_var = self.system_var
        
        # Auto-detect button (fills current system automatically) - with app color scheme
        auto_btn = tk.Button(search_frame, text="Use Current System", command=self._auto_detect_system,
                            bg="#4a3a2a", fg="#e0e0e0", 
                            activebackground="#5a4a3a", activeforeground="#ffffff",
                            relief="ridge", bd=1, padx=8, pady=4,
                            font=("Segoe UI", 8, "normal"), cursor="hand2")
        auto_btn.grid(row=0, column=2, padx=10, pady=5)
        
        # Search button - with app color scheme
        self.search_btn = tk.Button(search_frame, text="Search", command=self.search_hotspots,
                                   bg="#2a4a2a", fg="#e0e0e0", 
                                   activebackground="#3a5a3a", activeforeground="#ffffff",
                                   relief="ridge", bd=1, padx=8, pady=4,
                                   font=("Segoe UI", 8, "normal"), cursor="hand2")
        self.search_btn.grid(row=0, column=3, padx=10, pady=5)

        # Ring Type filter
        ttk.Label(search_frame, text="Ring Type:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.material_var = tk.StringVar(value="All")
        material_combo = ttk.Combobox(search_frame, textvariable=self.material_var, width=22, state="readonly")
        material_combo['values'] = ("All", "Metallic", "Rocky", "Icy", "Metal Rich")
        material_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # Distance filter (now a dropdown)
        ttk.Label(search_frame, text="Max Distance (LY):").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        self.distance_var = tk.StringVar(value="50")
        distance_combo = ttk.Combobox(search_frame, textvariable=self.distance_var, width=8, state="readonly")
        distance_combo['values'] = ("10", "50", "100")
        distance_combo.grid(row=1, column=3, sticky="w", padx=5, pady=5)
        
        # Max Results filter
        ttk.Label(search_frame, text="Max Results:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.max_results_var = tk.StringVar(value="30")
        max_results_combo = ttk.Combobox(search_frame, textvariable=self.max_results_var, width=8, state="readonly")
        max_results_combo['values'] = ("10", "20", "30", "50", "All")
        max_results_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Add tooltip for distance limitation
        ToolTip(distance_combo, "Maximum search radius in light years\nEDSM API limits searches to 100 LY maximum\nRecommended: 10-50 LY for better performance")
        
        # Search limitations info text (bottom of search controls)
        info_text = tk.Label(search_frame, 
                            text="ℹ Search covers populated systems within the bubble • Ring data from EDSM may be incomplete • Please allow time between searches",
                            fg="#cccccc", bg="#1e1e1e", font=("Segoe UI", 8, "italic"), 
                            justify="left")
        info_text.grid(row=3, column=0, columnspan=4, sticky="w", padx=5, pady=(5, 10))
        
        # Results section
        results_frame = ttk.LabelFrame(self.scrollable_frame, text="Search Results")
        results_frame.pack(fill="both", expand=True, padx=10, pady=(5, 2))
        
        # Create frame for treeview with scrollbars
        tree_frame = ttk.Frame(results_frame)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(5, 2))
        
        # Results treeview with enhanced columns including source
        columns = ("Distance", "LS", "System", "Visited", "Ring", "Ring Type", "Hotspots", "Mass (EM)", "Radius (Inner/Outer)")
        self.results_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        # Set column widths - similar to EDTOOLS layout
        column_widths = {
            "Distance": 50,
            "LS": 80,
            "System": 220,
            "Ring": 100,
            "Ring Type": 120,
            "Hotspots": 200,
            "Visited": 60,
            "Mass (EM)": 110,
            "Radius (Inner/Outer)": 180
        }
        
        for col in columns:
            self.results_tree.heading(col, text=col, command=lambda c=col: self._sort_column(c, False))
            
            # Configure columns with minwidth and stretch like reports tab
            if col == "Distance":
                self.results_tree.column(col, width=column_widths[col], minwidth=70, anchor="center", stretch=True)
            elif col == "System":
                self.results_tree.column(col, width=column_widths[col], minwidth=230, anchor="w", stretch=True)
            elif col == "Ring":
                self.results_tree.column(col, width=column_widths[col], minwidth=100, anchor="center", stretch=False)
            elif col == "Ring Type":
                self.results_tree.column(col, width=column_widths[col], minwidth=80, anchor="center", stretch=False)
            elif col == "Hotspots":
                self.results_tree.column(col, width=column_widths[col], minwidth=320, anchor="center", stretch=True)
            elif col == "Visited":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="center", stretch=False)
            elif col == "LS":
                self.results_tree.column(col, width=column_widths[col], minwidth=60, anchor="center", stretch=False)
            elif col == "Mass (EM)":
                self.results_tree.column(col, width=column_widths[col], minwidth=90, anchor="center", stretch=False)
            elif col == "Radius (Inner/Outer)":
                self.results_tree.column(col, width=column_widths[col], minwidth=180, anchor="center", stretch=False)
        
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
        if col in ["Distance", "Hotspots", "LS", "Density"]:
            # Numeric sort - handle N/A values
            def sort_key(item):
                val = item[0]
                if val == "N/A" or val == "":
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
        
        # Update heading to show sort direction
        heading_text = col + (" ↓" if reverse else " ↑")
        self.results_tree.heading(col, text=heading_text, command=lambda: self._sort_column(col, self.sort_reverse[col]))
        
    def _on_canvas_configure(self, event):
        """Handle canvas resize to make scrollable frame fill canvas dimensions"""
        canvas_width = event.width
        canvas_height = event.height
        # Make scrollable frame fill entire canvas area
        self.canvas.itemconfig(self.canvas.find_all()[0], width=canvas_width, height=canvas_height)
        
    def _preload_data(self):
        """Preload systems data in background"""
        try:
            self.status_var.set("Loading systems database...")
            self._load_systems_cache()
            self.parent.after(0, lambda: self.status_var.set("Ready - EDSM database loaded"))
        except Exception as e:
            self.parent.after(0, lambda: self.status_var.set(f"Error loading database: {e}"))
    
            
    def _auto_detect_system(self):
        """Auto-detect current system from Elite Dangerous journal"""
        try:
            if self.prospector_panel and hasattr(self.prospector_panel, 'last_system'):
                current_system = self.prospector_panel.last_system
                if current_system:
                    self.current_system_var.set(current_system)
                    self.status_var.set(f"Current system: {current_system}")
                    # Check if coordinates exist or get them from EDSM
                    coords = self.systems_data.get(current_system.lower())
                    if not coords:
                        coords = self._get_system_coords_from_edsm(current_system)
                        if coords:
                            self.systems_data[current_system.lower()] = coords
                            self.status_var.set(f"Current system: {current_system}")
                        else:
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
                            coords = self._get_system_coords_from_edsm(system_name)
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
    
    def _load_systems_cache(self):
        """Initialize empty systems cache for coordinate lookups"""
        # Start with empty cache - coordinates will be fetched from EDSM as needed
        self.systems_data = {}
    
    def search_hotspots(self):
        """Search for mining hotspots using reference system as center point"""
        reference_system = self.system_var.get().strip()
        material_filter = self.material_var.get()
        max_distance = min(float(self.distance_var.get() or "100"), 100.0)
        max_results_str = self.max_results_var.get()
        max_results = None if max_results_str == "All" else int(max_results_str)
        
        if not reference_system:
            self.status_var.set("Please enter a reference system or use 'Use Current System'")
            return
        
        # Check if search criteria changed from last search and clear relevant cache
        current_search_key = f"{reference_system}_{material_filter}_{max_distance}"
        if hasattr(self, '_last_search_key') and self._last_search_key != current_search_key:
            if hasattr(self, 'local_db'):
                # Clear cache entries for the previous search context
                old_system = self._last_search_key.split('_')[0] if hasattr(self, '_last_search_key') else None
                if old_system and old_system == reference_system:
                    # Same system, different criteria - clear material-specific cache
                    self.local_db.clear_cache(f"material_")
                    print(f"🧹 DEBUG: Cleared cache due to search criteria change")
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
            # Try to get coordinates from EDSM as fallback
            self.current_system_coords = self._get_system_coords_from_edsm(reference_system)
            if not self.current_system_coords:
                self.status_var.set(f"Warning: '{reference_system}' coordinates not found - distances may be inaccurate")
        
        # Disable search button
        self.search_btn.configure(state="disabled", text="Searching...")
        self.status_var.set("Searching for rings...")
        
        # Run search in background - pass reference system coords and max results to worker
        threading.Thread(target=self._search_worker, 
                        args=(reference_system, material_filter, max_distance, self.current_system_coords, max_results), 
                        daemon=True).start()
        
    def _search_worker(self, reference_system: str, material_filter: str, max_distance: float, reference_coords, max_results):
        """Background worker for hotspot search"""
        try:
            # Set the reference system coords for this worker thread
            self.current_system_coords = reference_coords
            hotspots = self._get_hotspots(reference_system, material_filter, max_distance, max_results)
            
            # Update UI in main thread
            self.parent.after(0, self._update_results, hotspots)
            
        except Exception as e:
            error_msg = f"Search failed: {str(e)}"
            self.parent.after(0, self._show_error, error_msg)
        finally:
            # Re-enable search button
            self.parent.after(0, lambda: self.search_btn.configure(state="normal", text="Ring Search"))
    
    def _get_hotspots(self, reference_system: str, material_filter: str, max_distance: float, max_results: int = None) -> List[Dict]:
        """Get hotspot data using reference system as center point for distance calculations and mining searches"""
        print(f"🔍 DEBUG: Searching for {material_filter} within {max_distance} LY of {reference_system}")
        
        # Try EDSM Bodies API for rings data using reference system and nearby systems
        edsm_results = []
        try:
            # First, search the reference system itself
            print(f"🌟 DEBUG: Searching reference system '{reference_system}' for material '{material_filter}'")
            edsm_results = self._get_edsm_bodies_with_rings(reference_system, material_filter)
            print(f"📡 DEBUG: Reference system search returned {len(edsm_results)} results")
            if len(edsm_results) == 0:
                print(f"⚠️ DEBUG: No mining data found for reference system '{reference_system}'")
            
            # Then search nearby systems within range
            if self.current_system_coords and max_distance > 0:
                print(f"🎯 DEBUG: Searching nearby systems within {max_distance} LY")
                nearby_systems = self._get_nearby_systems(reference_system, max_distance, material_filter)
                print(f"🗺️ DEBUG: Found {len(nearby_systems)} nearby systems to check")
                
                # Early stopping: stop when we have enough results
                total_results = len(edsm_results)
                systems_checked = 0
                
                # Limit to prevent too many API calls and implement early stopping
                max_systems_to_check = 100 if not max_results else min(100, max_results * 3)  # Check up to 3x desired results
                
                for nearby_system in nearby_systems[:max_systems_to_check]:
                    # Skip the reference system to avoid duplicates (it was already searched)
                    if nearby_system['name'].lower() == reference_system.lower():
                        print(f"⏭️ DEBUG: Skipping reference system '{nearby_system['name']}' to avoid duplicates")
                        continue
                    
                    # Update progress
                    systems_checked += 1
                    if systems_checked % 5 == 0:  # Update every 5 systems
                        progress_msg = f"Searching system {systems_checked} of {min(len(nearby_systems), max_systems_to_check)}... Found {total_results} results"
                        self.parent.after(0, lambda msg=progress_msg: self.status_var.set(msg))
                    
                    try:
                        print(f"🔎 DEBUG: Processing nearby system: {nearby_system['name']} at {nearby_system['distance']:.1f} LY")
                        nearby_results = self._get_edsm_bodies_with_rings(nearby_system['name'], material_filter)
                        print(f"📊 DEBUG: Nearby system '{nearby_system['name']}' returned {len(nearby_results)} results")
                        # Update distance for nearby results
                        for result in nearby_results:
                            result['distance'] = f"{nearby_system['distance']:.1f}"
                        edsm_results.extend(nearby_results)
                        total_results += len(nearby_results)
                        print(f"📈 DEBUG: Running total: {total_results} results")
                        
                        # Add delay to avoid EDSM rate limiting
                        time.sleep(0.5)
                        
                        # Early stopping: if we have enough results, stop searching
                        if max_results and total_results >= max_results:
                            break
                            
                    except Exception as e:
                        continue
            
        except Exception as e:
            pass
        
        # Use EDSM results as base and enhance with hotspot data
        combined_results = edsm_results

        # Enhance EDSM results with user database hotspot information
        print(f"🎯 DEBUG: Enhancing EDSM ring data with user database hotspots")
        try:
            # Get all user hotspots within range for lookup
            user_hotspots = self._get_user_database_hotspots(reference_system, "All Materials", max_distance)
            print(f"💎 DEBUG: Found {len(user_hotspots)} user database hotspots for enhancement")
            
            # Create a lookup map for user hotspots by system-ring combination
            hotspot_lookup = {}
            for hotspot in user_hotspots:
                system_name = hotspot.get('systemName', '')
                body_name = hotspot.get('bodyName', '')
                key = f"{system_name}-{body_name}".lower()
                hotspot_lookup[key] = hotspot
            
            # Enhance EDSM results with hotspot data
            for edsm_result in combined_results:
                system_name = edsm_result.get('systemName', edsm_result.get('system', ''))
                ring_name = edsm_result.get('ring', edsm_result.get('bodyName', ''))
                
                # Try multiple key formats to match
                lookup_keys = [
                    f"{system_name}-{ring_name}".lower(),
                    f"{system_name}-{system_name} {ring_name}".lower()
                ]
                
                for key in lookup_keys:
                    if key in hotspot_lookup:
                        # Found matching hotspot data - enhance the EDSM result
                        edsm_result['has_hotspots'] = True
                        edsm_result['hotspot_data'] = hotspot_lookup[key]
                        break
            
            print(f"🔀 DEBUG: Enhanced {len(combined_results)} EDSM results with hotspot data")
            
        except Exception as e:
            print(f"⚠️ DEBUG: User database search failed: {e}")

        # Apply max results limit if specified
        if max_results and len(combined_results) > max_results:
            combined_results = combined_results[:max_results]

        print(f"🎯 DEBUG: Final return: {len(combined_results)} results")
        return combined_results
        
    def _get_edsm_bodies_with_rings(self, system_name: str, material_filter: str) -> List[Dict]:
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
            
            print(f"🔍 DEBUG: Calling EDSM bodies API for '{system_name}': {url}")
            response = requests.get(url, params=params, timeout=10)
            print(f"📡 DEBUG: EDSM bodies API status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"📊 DEBUG: EDSM bodies API returned {len(data.get('bodies', []))} bodies for '{system_name}'")
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
                        'secondary': ['Musgravite', 'Grandidierite', 'Serendibite', 'Rhodplumsite', 'Opal']
                    }
                }
                
                for body in data.get('bodies', []):
                    if body.get('rings'):
                        body_name = body.get('name', '')
                        distance_ls = body.get('distanceToArrival', 0)
                        
                        rings_found = len(body['rings'])
                        
                        for ring in body['rings']:
                            ring_type = ring.get('type', 'Unknown')
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
                                print(f"🔍 DEBUG: Ring mass {ring_mass:.2e} API units = {mass_in_em:.4f} EM -> display: {mass_display}")
                            else:
                                mass_display = "N/A"
                            
                            # Clean up ring name to show only essential part
                            clean_ring_name = self._clean_ring_name(ring_name, body_name, system_name)
                            
                            # Get materials that can be found in this ring type
                            materials_in_ring = ring_materials.get(ring_type, {})
                            all_materials = materials_in_ring.get('primary', []) + materials_in_ring.get('secondary', [])
                            
                            # If material filter is specified, check if this ring type matches exactly
                            if material_filter != "All":
                                if material_filter != ring_type:
                                    continue
                            
                            # Show primary materials for this ring type
                            materials_to_show = materials_in_ring.get('primary', ['Unknown'])
                            
                            # Create single entry for this ring
                            mining_opportunities.append({
                                'system': system_name,
                                'body': body_name,
                                'ring': clean_ring_name,
                                'ring_type': ring_type,
                                'ls': str(int(distance_ls)) if distance_ls > 0 else "N/A",
                                'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                                'mass': mass_display,
                                'radius': f"{inner_radius:,} - {outer_radius:,}" if inner_radius > 0 and outer_radius > 0 else "N/A",
                                'source': 'EDSM Ring Data'
                            })
                
                return mining_opportunities
                
        except Exception as e:
            pass
        
        return []

    def _get_nearby_systems(self, reference_system: str, max_distance: float, material_filter: str = "All") -> List[Dict]:
        """Get systems within specified distance from reference system using local database or EDSM APIs"""
        
        reference_coords = self.current_system_coords
        print(f"🔍 DEBUG: Reference system: {reference_system}")
        print(f"📍 DEBUG: Reference coords: {reference_coords}")
        print(f"🔍 DEBUG: Max distance: {max_distance} ly")
        print(f"🗄️ DEBUG: Using local database: {self.use_local_db}")
        print(f"🎯 DEBUG: Material filter: {material_filter}")
        
        # Try local database first if enabled and available
        if self.use_local_db and self.local_db.is_database_available() and reference_coords:
            try:
                print(f"🗄️ DEBUG: Searching local database for systems within {max_distance} ly")
                # Create cache context that includes search criteria
                cache_context = f"material_{material_filter}"
                local_results = self.local_db.find_nearby_systems(
                    reference_coords['x'], 
                    reference_coords['y'], 
                    reference_coords['z'], 
                    max_distance, 
                    limit=100,
                    cache_context=cache_context
                )
                
                if local_results:
                    print(f"✅ DEBUG: Local database found {len(local_results)} systems")
                    # Convert to expected format
                    nearby_systems = []
                    for system in local_results:
                        nearby_systems.append({
                            'name': system['name'],
                            'distance': system['distance'],
                            'coordinates': system['coordinates']
                        })
                    
                    print(f"🎯 DEBUG: Local database distance range: {nearby_systems[0]['distance']:.2f} - {nearby_systems[-1]['distance']:.2f} ly")
                    return nearby_systems
                else:
                    print(f"⚠️ DEBUG: Local database returned no results")
            except Exception as e:
                print(f"❌ DEBUG: Local database search failed: {e}")
                # Fall back to API search
                
        # Fallback to existing API-based search methods (Note: Local database is much more efficient)
        print(f"🌐 DEBUG: Falling back to API-based search methods (Recommend enabling local database for better results)")
        
        # Get API key from config first
        api_key = ""
        try:
            from config import _load_cfg
            cfg = _load_cfg()
            api_key = cfg.get("edsm_api_key", "")
            if api_key:
                print(f"🔑 DEBUG: Using EDSM API key from config")
            else:
                print(f"⚠️ DEBUG: No EDSM API key configured")
        except Exception as e:
            print(f"❌ DEBUG: Could not load API key from config: {e}")
            
        reference_coords = self.current_system_coords
        print(f"🔍 DEBUG: Reference system: {reference_system}")
        print(f"� DEBUG: Reference coords: {reference_coords}")
        print(f"🔍 DEBUG: Max distance: {max_distance} ly")
            
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
                print(f"🌐 DEBUG: Using EDSM cube-systems with coordinates and size: {min(max_distance * 2, 200)} ly")
            else:
                params = {
                    "systemName": reference_system,
                    "size": min(max_distance * 2, 200),  # EDSM max is 200 ly
                    "showCoordinates": 1
                }
                print(f"🌐 DEBUG: Using EDSM cube-systems with system name: {reference_system}")
            
            if api_key:
                params["apiKey"] = api_key
            
            print(f"🔄 DEBUG: EDSM cube-systems API call: {url}")
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            print(f"📡 DEBUG: EDSM cube-systems Response status: {response.status_code}")
            
            systems_data = response.json()
            print(f"📊 DEBUG: EDSM cube-systems returned data type: {type(systems_data)}")
            
            if isinstance(systems_data, list) and len(systems_data) > 0:
                print(f"✅ DEBUG: Found {len(systems_data)} systems near {reference_system} using cube-systems API")
                
                nearby_systems = []
                
                for system in systems_data:
                    if 'name' in system and 'coords' in system and reference_coords:
                        system_coords = system['coords']
                        distance = self._calculate_distance(reference_coords, system_coords)
                        
                        # Filter by actual distance (cube returns systems in square, we want circle)
                        if distance <= max_distance:
                            # Exclude reference system by name
                            if system['name'].lower() != reference_system.lower():
                                nearby_systems.append({
                                    'name': system['name'],
                                    'distance': distance,
                                    'coordinates': system_coords
                                })
                
                # Sort by distance
                nearby_systems.sort(key=lambda x: x['distance'])
                print(f"✅ DEBUG: Processed {len(nearby_systems)} nearby systems within {max_distance} ly using cube-systems API")
                if nearby_systems:
                    print(f"🎯 DEBUG: Distance range: {nearby_systems[0]['distance']:.2f} - {nearby_systems[-1]['distance']:.2f} ly")
                return nearby_systems
                
            elif isinstance(systems_data, dict):
                if 'error' in systems_data:
                    print(f"❌ DEBUG: EDSM cube-systems API error: {systems_data['error']}")
                elif len(systems_data) == 0:
                    print(f"⚠️ DEBUG: EDSM cube-systems API returned empty dict (API may have changed or require different parameters)")
                else:
                    print(f"⚠️ DEBUG: EDSM cube-systems returned unexpected dict format: {systems_data}")
            else:
                print(f"⚠️ DEBUG: EDSM cube-systems returned unexpected format")
                
        except Exception as e:
            print(f"❌ DEBUG: EDSM cube-systems API failed: {e}")
            
        # Try sector-based search as secondary fallback
        try:
            if reference_coords:
                print(f"🔍 DEBUG: Trying sector-based search for region near {reference_system}")
                
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
                                print(f"📡 DEBUG: Found {len(systems)} systems matching '{pattern}'")
                                
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
                        print(f"⚠️ DEBUG: Pattern '{pattern}' search failed: {pattern_error}")
                        continue
                
                if sector_systems:
                    sector_systems.sort(key=lambda x: x['distance'])
                    print(f"✅ DEBUG: Sector-based search found {len(sector_systems)} systems within {max_distance} ly")
                    if sector_systems:
                        print(f"🎯 DEBUG: Distance range: {sector_systems[0]['distance']:.2f} - {sector_systems[-1]['distance']:.2f} ly")
                    return sector_systems
                    
        except Exception as e:
            print(f"❌ DEBUG: Sector-based search failed: {e}")
            
        # Final fallback: Use a curated list of known systems for popular mining areas
        print(f"� DEBUG: Using fallback system list for nearby systems search")
        
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
            print(f"🎯 DEBUG: Reference coords available: {reference_coords}")
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
                print(f"⚠️ DEBUG: No systems found within {max_distance} LY, expanding search to find closest systems")
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
                    print(f"🎯 DEBUG: Using {len(nearby_systems)} closest systems as fallback (range: {nearby_systems[0]['distance']:.1f} - {nearby_systems[-1]['distance']:.1f} LY)")
                        
            # Sort by distance
            nearby_systems.sort(key=lambda x: x['distance'])
            if nearby_systems:
                print(f"🎯 DEBUG: Fallback method found {len(nearby_systems)} systems within {max_distance} LY")
            else:
                print(f"🎯 DEBUG: Fallback method found {len(nearby_systems)} systems (expanded search)")
        else:
            # If no reference coordinates, return a reasonable subset of known systems
            print(f"⚠️ DEBUG: No reference coordinates available, using nearby systems from popular mining areas")
            for sys_name in known_mining_systems[:30]:
                if sys_name.lower() != reference_system.lower():
                    nearby_systems.append({
                        'name': sys_name,
                        'distance': 0.0,  # Unknown distance
                        'coordinates': {'x': 0, 'y': 0, 'z': 0}
                    })
            print(f"🎯 DEBUG: Fallback method (no coords) returning {len(nearby_systems)} popular systems")
                
        return nearby_systems

    def _clean_ring_name(self, full_ring_name: str, body_name: str, system_name: str) -> str:
        """Clean ring name to show only body number and ring letter (e.g., '2 A Ring')"""
        try:
            # If ring_name is from EDSM API, it might be like "Paesia 2 A Ring" or "HIP 23716 2 A Ring"
            # We want to extract just "2 A Ring"
            
            # Remove system name prefix if present
            if system_name and full_ring_name.startswith(system_name):
                cleaned = full_ring_name[len(system_name):].strip()
            else:
                cleaned = full_ring_name
            
            # Handle body name extraction - look for patterns like "2 A Ring", "A 3 Ring A", etc.
            # Common patterns in Elite Dangerous:
            # - "2 A Ring" (simple body number + ring letter)
            # - "A 3 Ring A" (star designation + body number + ring letter)
            # - "AB 1 Ring A" (binary star + body number + ring letter)
            
            # Try to extract just the essential part
            import re
            
            # Pattern 1: Extract "X Y Ring" where X is body identifier and Y is ring letter
            pattern1 = r'(\d+\s+[A-Za-z]\s+Ring)'
            match1 = re.search(pattern1, cleaned)
            if match1:
                result = match1.group(1)
                # Ensure proper capitalization: "2 A Ring"
                parts = result.split()
                if len(parts) == 3:  # ["2", "a", "Ring"]
                    return f"{parts[0]} {parts[1].upper()} {parts[2].title()}"
                return result
            
            # Pattern 2: Extract "Y X Ring Y" and return "X Ring Y" 
            pattern2 = r'([A-Za-z]+\s+\d+\s+Ring\s+[A-Za-z])'
            match2 = re.search(pattern2, cleaned)
            if match2:
                parts = match2.group(1).split()
                if len(parts) >= 4:  # ["A", "3", "Ring", "A"]
                    return f"{parts[1]} {parts[3].upper()} Ring"  # "3 A Ring"
            
            # Pattern 3: If it already looks clean (like "A Ring"), keep it but fix capitalization
            pattern3 = r'^[A-Za-z]\s+Ring$'
            if re.match(pattern3, cleaned.strip()):
                parts = cleaned.strip().split()
                return f"{parts[0].upper()} Ring"
            
            # Fallback: if none of the patterns match, try to extract meaningful part
            if "Ring" in cleaned:
                # Try to fix capitalization of any existing format
                result = cleaned.strip()
                # Replace "ring" with "Ring"
                result = re.sub(r'\bring\b', 'Ring', result, flags=re.IGNORECASE)
                # Capitalize single letters before "Ring"
                result = re.sub(r'\b([a-z])\s+Ring\b', lambda m: f"{m.group(1).upper()} Ring", result)
                return result
            else:
                # Generate a simple ring name based on body
                body_num = "1"
                if body_name:
                    # Try to extract number from body name
                    body_match = re.search(r'(\d+)', body_name)
                    if body_match:
                        body_num = body_match.group(1)
                return f"{body_num} A Ring"
                
        except Exception as e:
            print(f"Error cleaning ring name: {e}")
            return full_ring_name  # Return original if cleaning fails

    def _get_fallback_hotspots(self, search_term: str, material_filter: str) -> List[Dict]:
        """Search user database for hotspots when EDSM has no results"""
        print(f"🔍 DEBUG: Searching user database for {material_filter} hotspots")
        
        try:
            # Search user database for hotspots - no distance filtering needed
            import sqlite3
            user_hotspots = []
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Search for hotspots matching the material filter
                if material_filter == "All Materials":
                    cursor.execute('''
                        SELECT DISTINCT system_name, body_name, material_name, hotspot_count
                        FROM hotspot_data
                        ORDER BY hotspot_count DESC, system_name, body_name
                    ''')
                else:
                    cursor.execute('''
                        SELECT DISTINCT system_name, body_name, material_name, hotspot_count
                        FROM hotspot_data
                        WHERE material_name = ?
                        ORDER BY hotspot_count DESC, system_name, body_name
                    ''', (material_filter,))
                
                results = cursor.fetchall()
                print(f"📊 DEBUG: Found {len(results)} hotspot entries in user database")
                
                # Process each hotspot result
                for system_name, body_name, material_name, hotspot_count in results:
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
                            'ring_type': 'Unknown'
                        }
                        
                        user_hotspots.append(hotspot_entry)
                        
                    except Exception as e:
                        print(f"⚠️ DEBUG: Error processing {system_name}: {e}")
                        continue
                
                # Sort by hotspot count first (best hotspots), then by distance
                user_hotspots.sort(key=lambda x: (-x['count'], x['distance']))
                
                # Limit to reasonable number of results
                max_user_results = 50
                if len(user_hotspots) > max_user_results:
                    user_hotspots = user_hotspots[:max_user_results]
                    print(f"📝 DEBUG: Limited user database results to {max_user_results}")
                
                print(f"✅ DEBUG: Returning {len(user_hotspots)} user database hotspots")
                return user_hotspots
                
        except Exception as e:
            print(f"❌ DEBUG: User database search failed: {e}")
            return []
    
    def _get_user_database_hotspots(self, reference_system: str, material_filter: str, max_distance: float) -> List[Dict]:
        """Search user database for hotspots within distance range (using stored coordinates)"""
        print(f"💎 DEBUG: Searching user database for all available hotspots within {max_distance} LY of {reference_system}")
        
        try:
            import sqlite3
            user_hotspots = []
            edsm_lookups = 0
            max_edsm_lookups = 10  # Further reduced for distance searches under 50 LY
            
            with sqlite3.connect(self.user_db.db_path) as conn:
                cursor = conn.cursor()
                
                # Get hotspots with their stored coordinates
                cursor.execute('''
                    SELECT DISTINCT system_name, body_name, material_name, hotspot_count,
                           x_coord, y_coord, z_coord, coord_source
                    FROM hotspot_data
                    ORDER BY 
                        CASE WHEN x_coord IS NOT NULL THEN 0 ELSE 1 END,  -- Prioritize systems with coordinates
                        hotspot_count DESC, system_name, body_name
                ''')
                
                results = cursor.fetchall()
                print(f"💎 DEBUG: Found {len(results)} total hotspot entries in user database")
                
                # Get reference coordinates
                reference_coords = self.current_system_coords or self._get_system_coords_from_edsm(reference_system)
                if not reference_coords:
                    print(f"💎 DEBUG: Cannot get coordinates for reference system {reference_system}")
                    return []
                
                systems_with_stored_coords = 0
                systems_needing_lookup = 0
                
                for system_name, body_name, material_name, hotspot_count, x_coord, y_coord, z_coord, coord_source in results:
                    try:
                        system_coords = None
                        
                        # First try stored coordinates in hotspot_data
                        if x_coord is not None and y_coord is not None and z_coord is not None:
                            system_coords = {'name': system_name, 'x': x_coord, 'y': y_coord, 'z': z_coord}
                            systems_with_stored_coords += 1
                        
                        # If no stored coordinates, try cached coordinates
                        elif system_name.lower() in self.systems_data:
                            system_coords = self.systems_data[system_name.lower()]
                            systems_with_stored_coords += 1
                        
                        # Last resort: EDSM lookup (with limit to prevent endless processing)
                        elif edsm_lookups < max_edsm_lookups:
                            system_coords = self._get_system_coords_from_edsm(system_name)
                            if system_coords:
                                self.systems_data[system_name.lower()] = system_coords
                                systems_with_stored_coords += 1
                            edsm_lookups += 1
                            systems_needing_lookup += 1
                            
                            # Show progress for EDSM lookups
                            if edsm_lookups % 10 == 0:
                                print(f"💎 DEBUG: EDSM lookups progress: {edsm_lookups}/{max_edsm_lookups}")
                        else:
                            # Skip systems without coordinates once we hit the limit
                            continue
                        
                        # Calculate distance if we have coordinates
                        if system_coords:
                            distance = self._calculate_distance(reference_coords, system_coords)
                            
                            # Apply distance filter - only include systems within range
                            if distance <= max_distance:
                                source_label = f"EDTools.cc ({coord_source})" if coord_source else "EDTools.cc Community Data"
                                hotspot_entry = {
                                    'systemName': system_name,
                                    'bodyName': body_name,
                                    'type': material_name,
                                    'count': hotspot_count,
                                    'distance': round(distance, 1),
                                    'coords': system_coords,
                                    'data_source': source_label,
                                    'ring_mass': 0,
                                    'ring_type': 'Unknown'
                                }
                                
                                user_hotspots.append(hotspot_entry)
                        
                    except Exception as e:
                        print(f"💎 DEBUG: Error processing {system_name}: {e}")
                        continue
                
                # Sort by distance (closest first)
                user_hotspots.sort(key=lambda x: x['distance'])
                
                print(f"💎 DEBUG: Coordinate sources - Stored: {systems_with_stored_coords}, EDSM lookups: {edsm_lookups}")
                print(f"💎 DEBUG: Returning {len(user_hotspots)} user database hotspots within range")
                return user_hotspots
                
        except Exception as e:
            print(f"💎 DEBUG: User database search failed: {e}")
            return []
    
    def _calculate_distance(self, coord1: Dict, coord2: Dict) -> float:
        """Calculate distance between two 3D coordinates in light years"""
        if not coord1 or not coord2:
            return 0.0
        
        dx = coord1['x'] - coord2['x']
        dy = coord1['y'] - coord2['y'] 
        dz = coord1['z'] - coord2['z']
        
        return math.sqrt(dx*dx + dy*dy + dz*dz)
        
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
                        print(f"✅ DEBUG: Successfully got coordinates from EDSM for '{system_name}': {coords}")
                        return coords
                    else:
                        print(f"❌ DEBUG: No coordinates in EDSM response for '{system_name}'")
                else:
                    print(f"❌ DEBUG: Empty response from EDSM for '{system_name}'")
                    
        except Exception as e:
            print(f"❌ DEBUG: Failed to get coordinates from EDSM: {e}")
            
        return None
        
    def _update_results(self, hotspots: List[Dict]):
        """Update results treeview with hotspot data"""
        # Clear existing results
        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
            
        # Sort by distance if available
        try:
            hotspots.sort(key=lambda x: float(x.get('distance', 0)))
        except:
            pass
            
        # Add new results with hotspots column
        for hotspot in hotspots:
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
                hotspot_display = self.user_db.format_hotspots_for_display(system_name, body_name)
                hotspot_count_display = self._abbreviate_material_for_display(hotspot_display)
            elif "EDTools" in data_source:
                # EDTools data - show the count
                hotspot_count_display = str(hotspot.get("count", "-"))
            elif "count" in hotspot:
                # User database hotspots - show the count  
                hotspot_count_display = str(hotspot.get("count", "-"))
            else:
                # Pure EDSM ring composition data - show "-"
                hotspot_count_display = "-"
            
            # Check if player has visited this system
            visited_status = "Yes" if self.user_db.has_visited_system(system_name) else "No"
            
            self.results_tree.insert("", "end", values=(
                hotspot.get("distance", "N/A"),
                hotspot.get("ls", "N/A"),
                system_name,
                visited_status,
                ring_name,
                hotspot.get("ring_type", "N/A"),
                hotspot_count_display,
                hotspot.get("mass", "N/A"),
                hotspot.get("radius", "N/A")
            ))
            
        # Update status with source information 
        count = len(hotspots)
        search_term = self.system_var.get().strip()
        material_filter = self.material_var.get()
        
        if search_term:
            if material_filter != 'All':
                status_msg = f"Found {count} {material_filter} ring{'s' if count != 1 else ''} near '{search_term}'"
            else:
                status_msg = f"Found {count} ring{'s' if count != 1 else ''} near '{search_term}'"
        else:
            if material_filter != 'All':
                status_msg = f"Found {count} {material_filter} ring{'s' if count != 1 else ''}"
            else:
                status_msg = f"Found {count} ring{'s' if count != 1 else ''}"
            
        # Add EDSM source indication
        if count > 0:
            status_msg += f" (ring composition from EDSM)"
        
        self.status_var.set(status_msg)
            
    def _show_error(self, error_msg: str):
        """Show error message and reset UI"""
        self.status_var.set("Search failed - using fallback data")
        print(f"Hotspot search error: {error_msg}")
        # Try fallback search
        try:
            fallback_results = self._get_fallback_hotspots(
                self.system_var.get().strip(), 
                self.material_var.get()
            )
            self._update_results(fallback_results)
        except Exception as e:
            print(f"Fallback also failed: {e}")
            messagebox.showerror("Search Error", f"Both API and fallback failed: {error_msg}")
    
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
                    if val and val != "N/A":
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
            if hotspots and hotspots not in ["None", "N/A", ""]:
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
                    'notes': f'Ring Finder bookmark - {ring_type}' if ring_type else 'Ring Finder bookmark'
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