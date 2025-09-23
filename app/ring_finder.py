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

# Try to import ZeroMQ for EDDN support
try:
    import zmq
    EDDN_AVAILABLE = True
except ImportError:
    EDDN_AVAILABLE = False


class RingFinder:
    """Mining hotspot finder with EDDB API integration"""
    
    def __init__(self, parent_frame: ttk.Frame, prospector_panel=None):
        self.parent = parent_frame
        self.prospector_panel = prospector_panel  # Reference to get current system
        self.cache = {}  # API response cache
        self.cache_timeout = 3600  # 1 hour cache
        self.systems_data = {}  # System coordinates cache
        self.current_system_coords = None
        
        self.setup_ui()
        # Load initial data in background
        threading.Thread(target=self._preload_data, daemon=True).start()
        
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
        
        # Distance filter
        ttk.Label(search_frame, text="Max Distance (LY):").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        self.distance_var = tk.StringVar(value="50")
        distance_entry = ttk.Entry(search_frame, textvariable=self.distance_var, width=8)
        distance_entry.grid(row=1, column=3, sticky="w", padx=5, pady=5)
        
        # Max Results filter
        ttk.Label(search_frame, text="Max Results:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.max_results_var = tk.StringVar(value="20")
        max_results_combo = ttk.Combobox(search_frame, textvariable=self.max_results_var, width=8, state="readonly")
        max_results_combo['values'] = ("10", "20", "30", "50", "All")
        max_results_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Ring Type filter
        ttk.Label(search_frame, text="Ring Type:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.material_var = tk.StringVar(value="All")
        material_combo = ttk.Combobox(search_frame, textvariable=self.material_var, width=22, state="readonly")
        material_combo['values'] = ("All", "Metallic", "Rocky", "Icy", "Metal Rich")
        material_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        
        # Distance filter
        ttk.Label(search_frame, text="Max Distance (LY):").grid(row=1, column=2, sticky="w", padx=10, pady=5)
        self.distance_var = tk.StringVar(value="50")
        distance_entry = ttk.Entry(search_frame, textvariable=self.distance_var, width=8)
        distance_entry.grid(row=1, column=3, sticky="w", padx=5, pady=5)
        
        # Max Results filter
        ttk.Label(search_frame, text="Max Results:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.max_results_var = tk.StringVar(value="20")
        max_results_combo = ttk.Combobox(search_frame, textvariable=self.max_results_var, width=8, state="readonly")
        max_results_combo['values'] = ("10", "20", "30", "50", "All")
        max_results_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        
        # Add tooltip for distance limitation
        ToolTip(distance_entry, "Maximum search radius in light years\nEDSM API limits searches to 100 LY maximum\nRecommended: 20-50 LY for better performance")
        
        # Search limitations info text (bottom of search controls)
        info_text = tk.Label(search_frame, 
                            text="ℹ Search uses EDSM database which may have incomplete ring data • Please allow time between searches",
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
        columns = ("Distance", "System", "Ring", "Ring Type", "LS")
        self.results_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)
        
        # Set column widths - similar to EDTOOLS layout
        column_widths = {
            "Distance": 70,
            "System": 140,
            "Ring": 100,
            "Ring Type": 80,
            "LS": 70
        }
        
        for col in columns:
            self.results_tree.heading(col, text=col, command=lambda c=col: self._sort_column(c, False))
            self.results_tree.column(col, width=column_widths[col], anchor="center" if col in ["Distance", "LS", "Ring Type"] else "w")
        
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
    
    def _get_hotspots(self, reference_system: str, material_filter: str, max_distance: float) -> List[Dict]:
        """Toggle EDDN connection on/off"""
        if not EDDN_AVAILABLE:
            messagebox.showerror("EDDN Error", "ZeroMQ not available. Install with: pip install pyzmq")
            return
            
        if not self.eddn_active:
            # Start EDDN listener
            try:
                self._start_eddn_listener()
                self.eddn_status_var.set("Connected")
                self.eddn_toggle_btn.config(text="Disconnect EDDN")
                # Update status label color to green (if supported)
                try:
                    for widget in self.scrollable_frame.winfo_children():
                        if isinstance(widget, ttk.LabelFrame) and widget.cget('text') == "Live Community Data (EDDN)":
                            for child in widget.winfo_children():
                                if isinstance(child, ttk.Label) and child.cget('textvariable'):
                                    if str(child.cget('textvariable')) == str(self.eddn_status_var):
                                        child.config(foreground="green")
                                        break
                            break
                except:
                    pass
            except Exception as e:
                print(f"Failed to start EDDN: {e}")
                messagebox.showerror("EDDN Error", f"Failed to connect to EDDN: {e}")
        else:
            # Stop EDDN listener
            self._stop_eddn_listener()
            self.eddn_status_var.set("Disconnected")
            self.eddn_toggle_btn.config(text="Connect to EDDN")
            # Update status label color to red
            try:
                for widget in self.scrollable_frame.winfo_children():
                    if isinstance(widget, ttk.LabelFrame) and widget.cget('text') == "Live Community Data (EDDN)":
                        for child in widget.winfo_children():
                            if isinstance(child, ttk.Label) and child.cget('textvariable'):
                                if str(child.cget('textvariable')) == str(self.eddn_status_var):
                                    child.config(foreground="red")
                                    break
                        break
            except:
                pass
    
    def _test_eddn_data(self):
        """Add test EDDN data for demonstration purposes"""
        if not EDDN_AVAILABLE:
            messagebox.showinfo("EDDN Test", "ZeroMQ not available. Install with: pip install pyzmq")
            return
        
        # Simulate some EDDN hotspot discoveries
        test_data = [
            {
                'system': 'Borann',
                'body': 'Borann A 2',
                'materials': ['LowTemperatureDiamond'],
                'timestamp': '2025-09-21T08:00:00Z',
                'commander': 'TestCommander1'
            },
            {
                'system': 'Hyades Sector DB-X d1-112',
                'body': 'Hyades Sector DB-X d1-112 2',
                'materials': ['Platinum'],
                'timestamp': '2025-09-21T08:15:00Z',
                'commander': 'TestCommander2'
            },
            {
                'system': 'Kirre',
                'body': 'Kirre 1',
                'materials': ['VoidOpal'],
                'timestamp': '2025-09-21T08:30:00Z',
                'commander': 'TestCommander3'
            }
        ]
        
        # Add test data to cache
        if not hasattr(self, 'eddn_hotspots'):
            self.eddn_hotspots = []
        
        for data in test_data:
            hotspot_entry = {
                'system': data['system'],
                'body': data['body'],
                'materials': data['materials'],
                'timestamp': data['timestamp'],
                'commander': data['commander'],
                'source': 'EDDN_Live'
            }
            self.eddn_hotspots.append(hotspot_entry)
        
        print(f"Added {len(test_data)} test EDDN hotspots")
        messagebox.showinfo("EDDN Test", f"Added {len(test_data)} test mining hotspot discoveries!\n\nNow search for 'Borann', 'Hyades', or 'Kirre' to see EDDN Live results.")
        
        # Activate EDDN mode for testing
        if not self.eddn_active:
            self.eddn_active = True
            self.eddn_status_var.set("Test Data Active")
        
        # Update status if connected
        if hasattr(self, 'eddn_status_var'):
            current_status = self.eddn_status_var.get()
            if "Test Data" not in current_status:
                self.eddn_status_var.set(f"Test Data ({len(self.eddn_hotspots)} cached)")
            else:
                self.eddn_status_var.set(f"Test Data ({len(self.eddn_hotspots)} cached)")
        
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
        """Handle canvas resize to make scrollable frame fill width"""
        canvas_width = event.width
        self.canvas.itemconfig(self.canvas.find_all()[0], width=canvas_width)
        
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
                    # Check if coordinates exist
                    coords = self.systems_data.get(current_system.lower())
                    if not coords:
                        self.status_var.set(f"Current system: {current_system} (coordinates not available)")
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
                        if coords:
                            self.status_var.set(f"Current system: {system_name}")
                        else:
                            self.status_var.set(f"Current system: {system_name} (coordinates not available)")
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
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid"""
        if cache_key not in self.cache:
            return False
        
        age = time.time() - self.cache[cache_key]['timestamp']
        return age < self.cache_timeout
    
    def search_hotspots(self):
        """Search for mining hotspots using reference system as center point"""
        reference_system = self.system_var.get().strip()
        material_filter = self.material_var.get()
        max_distance = float(self.distance_var.get() or "100")
        max_results_str = self.max_results_var.get()
        max_results = None if max_results_str == "All" else int(max_results_str)
        
        if not reference_system:
            self.status_var.set("Please enter a reference system or use 'Use Current System'")
            return
        
        # Set reference system coordinates for distance calculations (case insensitive)
        self.current_system_coords = None
        print(f"Looking for reference system: '{reference_system}'")
        
        # Try exact match first
        self.current_system_coords = self.systems_data.get(reference_system.lower())
        if self.current_system_coords:
            print(f"Found exact match: {reference_system}")
        else:
            # Try partial match (case insensitive)
            for sys_name, sys_coords in self.systems_data.items():
                if reference_system.lower() in sys_name.lower():
                    self.current_system_coords = sys_coords
                    print(f"Found reference system match: {sys_name} for '{reference_system}'")
                    break
            
        if not self.current_system_coords:
            print(f"No coordinates found for reference system: {reference_system}")
            # Try to get coordinates from EDSM as fallback
            print(f"Attempting to get coordinates from EDSM for: {reference_system}")
            self.current_system_coords = self._get_system_coords_from_edsm(reference_system)
            if self.current_system_coords:
                print(f"Retrieved coordinates from EDSM: {self.current_system_coords}")
            else:
                print(f"EDSM also failed to provide coordinates for: {reference_system}")
                self.status_var.set(f"Warning: '{reference_system}' coordinates not found - distances may be inaccurate")
        
        # Disable search button
        self.search_btn.configure(state="disabled", text="Searching...")
        self.status_var.set("Searching hotspot database...")
        
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
        cache_key = f"bodies_{reference_system}_{material_filter}_{max_distance}_{max_results}"
        
        # Check cache first
        if self._is_cache_valid(cache_key):
            cached_results = self.cache[cache_key]['data']
            if max_results and len(cached_results) >= max_results:
                return cached_results[:max_results]
        else:
            cached_results = []
        
        # Try EDSM Bodies API for rings data using reference system and nearby systems
        edsm_results = []
        print(f"Searching EDSM for ring composition data in system: {reference_system}")
        try:
            # First, search the reference system itself
            edsm_results = self._get_edsm_bodies_with_rings(reference_system, material_filter)
            
            # Then search nearby systems within range
            if self.current_system_coords and max_distance > 0:
                nearby_systems = self._get_nearby_systems(reference_system, max_distance)
                print(f"Found {len(nearby_systems)} systems within {max_distance} LY of {reference_system}")
                
                # Early stopping: stop when we have enough results
                total_results = len(edsm_results)
                systems_checked = 0
                
                # Limit to prevent too many API calls and implement early stopping
                max_systems_to_check = 100 if not max_results else min(100, max_results * 3)  # Check up to 3x desired results
                
                for nearby_system in nearby_systems[:max_systems_to_check]:
                    # Update progress
                    systems_checked += 1
                    if systems_checked % 5 == 0:  # Update every 5 systems
                        progress_msg = f"Searching system {systems_checked} of {min(len(nearby_systems), max_systems_to_check)}... Found {total_results} results"
                        self.parent.after(0, lambda msg=progress_msg: self.status_var.set(msg))
                    
                    try:
                        nearby_results = self._get_edsm_bodies_with_rings(nearby_system['name'], material_filter)
                        # Update distance for nearby results
                        for result in nearby_results:
                            result['distance'] = f"{nearby_system['distance']:.1f}"
                        edsm_results.extend(nearby_results)
                        total_results += len(nearby_results)
                        
                        # Early stopping: if we have enough results, stop searching
                        if max_results and total_results >= max_results:
                            print(f"✓ Early stopping: Found {total_results} results, stopping search")
                            break
                            
                    except Exception as e:
                        print(f"Failed to query {nearby_system['name']}: {e}")
                        continue
            
            print(f"✓ EDSM Bodies: {len(edsm_results)} rings with potential {material_filter if material_filter != 'All' else 'mining materials'} found")
        except Exception as e:
            print(f"✗ EDSM Bodies failed: {e}")
        
        # Use EDSM results only
        combined_results = edsm_results
        
        # Apply max results limit if specified
        if max_results and len(combined_results) > max_results:
            combined_results = combined_results[:max_results]
            print(f"✓ Limited results to {max_results} as requested")
        
        # Cache results if we have new data
        if combined_results:
            self.cache[cache_key] = {
                'data': combined_results,
                'timestamp': time.time()
            }
        
        print(f"Returning {len(combined_results)} total results (0 EDDN + 0 local)")
        return combined_results or cached_results
        
    def _update_systems_from_edsm(self, search_term: str, max_distance: float):
        """Update systems database using EDSM API with retry logic"""
        import time
        
        for attempt in range(2):  # Try twice
            try:
                # Get systems around current system using systemName instead of coordinates
                if self.current_system_coords:
                    current_system_name = self.current_system_var.get().strip()
                    
                    # If current system is empty, use search term as reference
                    if not current_system_name:
                        current_system_name = search_term.strip()
                    
                    # Skip if we still don't have a system name
                    if not current_system_name:
                        print("No reference system provided for EDSM API")
                        return
                    
                    # Try sphere-systems API with system name
                    url = "https://www.edsm.net/api-v1/sphere-systems"
                    params = {
                        "systemName": current_system_name,
                        "radius": min(max_distance, 100),  # Reduced radius
                        "showCoordinates": 1
                    }
                    
                    # Check for API key in config (optional)
                    try:
                        from config import _load_cfg
                        cfg = _load_cfg()
                        api_key = cfg.get("edsm_api_key")
                        if api_key:
                            params["apikey"] = api_key
                    except:
                        api_key = None
                    
                    response = requests.get(url, params=params, timeout=15)
                    if response.status_code == 200:
                        systems_data = response.json()
                        
                        # Handle both dict and list responses
                        if isinstance(systems_data, dict):
                            if not systems_data:  # Empty dict means no results
                                print(f"EDSM returned no systems within {max_distance} LY of {current_system_name}")
                                return
                            # If dict with data, it might be an error response
                            if 'error' in systems_data:
                                print(f"EDSM API error: {systems_data.get('error', 'Unknown error')}")
                                return
                            # Skip this attempt if unexpected dict format
                            continue
                        
                        # Ensure systems_data is a list
                        if not isinstance(systems_data, list):
                            print(f"EDSM returned unexpected data type: {type(systems_data)}")
                            continue
                        
                        if not systems_data:
                            print("EDSM returned empty systems list")
                            return
                        
                        # Update systems database
                        count = 0
                        systems_to_process = systems_data[:300] if len(systems_data) > 300 else systems_data
                        for system in systems_to_process:
                            if 'coords' in system and 'name' in system:
                                system_name = system['name'].lower()
                                self.systems_data[system_name] = {
                                    'name': system['name'],
                                    'x': system['coords']['x'],
                                    'y': system['coords']['y'],
                                    'z': system['coords']['z']
                                }
                                count += 1
                        
                        status_msg = f"Added {count} systems from EDSM"
                        if api_key:
                            status_msg += " (using API key)"
                        print(status_msg)
                        return  # Success, exit function
                    else:
                        print(f"EDSM returned status {response.status_code}")
                
                break  # Exit retry loop if we get here
                        
            except Exception as e:
                print(f"EDSM attempt {attempt + 1} failed: {e}")
                if attempt == 0:
                    time.sleep(1)  # Wait before retry
                else:
                    raise  # Re-raise on final attempt
        
    def _get_edsm_bodies_with_rings(self, system_name: str, material_filter: str) -> List[Dict]:
        """Get bodies with rings from EDSM and show ring composition (not hotspots)"""
        try:
            print(f"Querying EDSM Bodies API for: {system_name}")
            url = f"https://www.edsm.net/api-system-v1/bodies"
            params = {'systemName': system_name}
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                mining_opportunities = []
                
                bodies_found = len(data.get('bodies', []))
                print(f"EDSM returned {bodies_found} bodies for {system_name}")
                
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
                        print(f"  Body {body_name}: {rings_found} rings")
                        
                        for ring in body['rings']:
                            ring_type = ring.get('type', 'Unknown')
                            ring_name = ring.get('name', f"{body_name} Ring")
                            
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
                            
                            # If material filter is specified, check if this ring type matches exactly
                            if material_filter != "All":
                                if material_filter != ring_type:
                                    continue
                            
                            # Create single entry for this ring
                            mining_opportunities.append({
                                'system': system_name,
                                'body': body_name,
                                'ring': clean_ring_name,
                                'ring_type': ring_type,
                                'ls': str(int(distance_ls)) if distance_ls > 0 else "N/A",
                                'distance': f"{distance:.1f}" if distance > 0 else "0.0",
                                'source': 'EDSM Ring Data'
                            })
                
                print(f"EDSM Bodies: Found {len(mining_opportunities)} rings with {material_filter if material_filter != 'All' else 'all ring types'}")
                return mining_opportunities
                
        except Exception as e:
            print(f"EDSM Bodies API failed: {e}")
        
        return []

    def _get_nearby_systems(self, reference_system: str, max_distance: float) -> List[Dict]:
        """Get systems within specified distance from reference system using EDSM API"""
        try:
            print(f"Searching EDSM for systems within {max_distance} LY of {reference_system}...")
            
            # Use EDSM sphere-systems API to find nearby systems
            url = "https://www.edsm.net/api-v1/sphere-systems"
            params = {
                "systemName": reference_system,
                "radius": min(max_distance, 100),  # EDSM max radius is 100 LY
                "showCoordinates": 1
            }
            
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                systems_data = response.json()
                if systems_data:
                    nearby_systems = []
                    
                    # Get reference system coordinates for distance calculation
                    reference_coords = self.current_system_coords
                    
                    for system in systems_data:
                        if 'coords' in system and 'name' in system:
                            system_coords = {
                                'x': system['coords']['x'],
                                'y': system['coords']['y'], 
                                'z': system['coords']['z']
                            }
                            
                            # Calculate distance
                            if reference_coords:
                                distance = self._calculate_distance(reference_coords, system_coords)
                            else:
                                distance = 0.0
                                
                            # Exclude reference system itself
                            if distance > 0.1:  # Small threshold to avoid floating point issues
                                nearby_systems.append({
                                    'name': system['name'],
                                    'distance': distance,
                                    'coordinates': system_coords
                                })
                                
                                # Cache system coordinates for future use
                                self.systems_data[system['name'].lower()] = system_coords
                    
                    # Sort by distance (closest first)
                    nearby_systems.sort(key=lambda x: x['distance'])
                    
                    print(f"EDSM found {len(nearby_systems)} systems within {max_distance} LY")
                    if nearby_systems:
                        print(f"Closest: {nearby_systems[0]['name']} ({nearby_systems[0]['distance']:.1f} LY)")
                        if len(nearby_systems) > 5:
                            print(f"Farthest: {nearby_systems[-1]['name']} ({nearby_systems[-1]['distance']:.1f} LY)")
                    
                    return nearby_systems
                else:
                    print("EDSM returned no systems data")
            else:
                print(f"EDSM API error: {response.status_code}")
                
        except Exception as e:
            print(f"Error finding nearby systems via EDSM: {e}")
            
        # Fallback to local database search if EDSM fails
        print("Falling back to local systems database...")
        return self._get_nearby_systems_local(reference_system, max_distance)
    
    def _get_nearby_systems_local(self, reference_system: str, max_distance: float) -> List[Dict]:
        """Fallback method: Get systems from local database"""
        try:
            # Get coordinates of reference system
            reference_coords = self.systems_data.get(reference_system.lower())
            if not reference_coords:
                print(f"No coordinates found for reference system: {reference_system}")
                return []
            
            nearby_systems = []
            print(f"Searching local database for systems within {max_distance} LY of {reference_system}...")
            
            # Search through all known systems
            for system_name, coords in self.systems_data.items():
                if coords and len(coords) >= 3:
                    distance = self._calculate_distance(reference_coords, coords)
                    if 0 < distance <= max_distance:  # Exclude reference system itself (distance 0)
                        nearby_systems.append({
                            'name': system_name.title(),
                            'distance': distance,
                            'coordinates': coords
                        })
            
            # Sort by distance (closest first)
            nearby_systems.sort(key=lambda x: x['distance'])
            
            print(f"Local database found {len(nearby_systems)} systems within range")
            return nearby_systems
            
        except Exception as e:
            print(f"Error finding nearby systems in local database: {e}")
            return []

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
        """No fallback hotspots - EDSM only"""
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
            url = "https://www.edsm.net/api-v1/system"
            params = {
                "systemName": system_name,
                "showCoordinates": 1
            }
            
            print(f"Querying EDSM for coordinates: {system_name}")
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and 'coords' in data:
                    coords = {
                        'name': data.get('name', system_name),
                        'x': data['coords']['x'],
                        'y': data['coords']['y'],
                        'z': data['coords']['z']
                    }
                    # Cache it in our local systems data for future use
                    self.systems_data[system_name.lower()] = coords
                    return coords
                    
        except Exception as e:
            print(f"Failed to get coordinates from EDSM: {e}")
            
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
            
        # Add new results without hotspots column
        for hotspot in hotspots:
            self.results_tree.insert("", "end", values=(
                hotspot.get("distance", "N/A"),
                hotspot["system"],
                hotspot["ring"],
                hotspot.get("ring_type", "N/A"),
                hotspot.get("ls", "N/A")
            ))
            
        # Update status with source information 
        count = len(hotspots)
        search_term = self.system_var.get().strip()
        material_filter = self.material_var.get()
        
        if search_term:
            status_msg = f"Found {count} ring{'s' if count != 1 else ''} containing {material_filter if material_filter != 'All' else 'mining materials'} near '{search_term}'"
        else:
            status_msg = f"Found {count} ring{'s' if count != 1 else ''} containing {material_filter if material_filter != 'All' else 'mining materials'}"
            
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
        """Start EDDN listener in a separate thread"""
        if not EDDN_AVAILABLE:
            return
        self.eddn_active = True
        self.eddn_thread = threading.Thread(target=self._eddn_listener, daemon=True)
        self.eddn_thread.start()
        print("EDDN listener started")
    
    def _stop_eddn_listener(self):
        """Stop EDDN listener"""
        self.eddn_active = False
        if hasattr(self, 'eddn_socket'):
            try:
                self.eddn_socket.close()
            except:
                pass
        print("EDDN listener stopped")
    
    def _eddn_listener(self):
        """Listen to EDDN stream for live mining hotspot data"""
        if not EDDN_AVAILABLE:
            return
            
        try:
            context = zmq.Context()
            self.eddn_socket = context.socket(zmq.SUB)
            self.eddn_socket.setsockopt(zmq.SUBSCRIBE, b"")
            self.eddn_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
            self.eddn_socket.connect("tcp://eddn.edcd.io:9500")
            
            print("Connected to EDDN stream")
            
            while self.eddn_active:
                try:
                    message = self.eddn_socket.recv_multipart(zmq.NOBLOCK)
                    
                    # Decompress and parse message
                    if len(message) >= 2:
                        compressed_data = message[0]
                        data = zlib.decompress(compressed_data)
                        json_data = json.loads(data.decode('utf-8'))
                        
                        # Process fssbodysignals messages for mining hotspots
                        if (json_data.get('$schemaRef') and 
                            'fssbodysignals' in json_data['$schemaRef']):
                            self._process_eddn_hotspot(json_data)
                            
                except zmq.Again:
                    # Timeout - continue loop
                    continue
                except Exception as e:
                    print(f"EDDN message processing error: {e}")
                    continue
                    
        except Exception as e:
            print(f"EDDN connection error: {e}")
        finally:
            try:
                self.eddn_socket.close()
                context.term()
            except:
                pass
    
    def _process_eddn_hotspot(self, message_data):
        """Process EDDN fssbodysignals message for mining hotspots"""
        try:
            header = message_data.get('header', {})
            message = message_data.get('message', {})
            
            # Extract system and body information - use StarSystem not SystemName
            system_name = message.get('StarSystem')  # Fixed: was SystemName
            body_name = message.get('BodyName')
            signals = message.get('Signals', [])
            
            if not system_name or not signals:
                return
                
            # Look for mining hotspot signals
            hotspot_materials = []
            for signal in signals:
                signal_type = signal.get('Type', '')
                # Look for mining hotspot signals (examples: $SAA_SignalType_Painite;, $SAA_SignalType_LTD;, etc)
                if ('$SAA_SignalType_' in signal_type and 
                    any(material in signal_type for material in [
                        'Platinum', 'LowTemperatureDiamond', 'LTD', 'Painite', 
                        'VoidOpal', 'Alexandrite', 'Benitoite', 'Grandidierite',
                        'Monazite', 'Musgravite', 'Serendibite', 'Tritium'
                    ])):
                    # Extract material name from signal type
                    material = signal_type.replace('$SAA_SignalType_', '').replace(';', '')
                    if material == 'LTD':
                        material = 'LowTemperatureDiamond'
                    hotspot_materials.append(material)
            
            if hotspot_materials:
                # Store the hotspot data temporarily
                self._cache_eddn_hotspot(system_name, body_name, hotspot_materials, header)
                print(f"EDDN: New hotspot data for {system_name} - {body_name}: {', '.join(hotspot_materials)}")
                
        except Exception as e:
            print(f"Error processing EDDN hotspot data: {e}")
    
    def _cache_eddn_hotspot(self, system_name, body_name, materials, header):
        """Cache EDDN hotspot data for integration with search results"""
        try:
            timestamp = header.get('gatewayTimestamp', '')
            commander = header.get('uploaderID', 'Unknown')
            
            # Create hotspot entry
            hotspot_entry = {
                'system': system_name,
                'body': body_name,
                'materials': materials,
                'timestamp': timestamp,
                'commander': commander,
                'source': 'EDDN_Live'
            }
            
            # Add to live data cache (limit size to prevent memory issues)
            if not hasattr(self, 'eddn_hotspots'):
                self.eddn_hotspots = []
            
            self.eddn_hotspots.append(hotspot_entry)
            
            # Keep only recent data (last 1000 entries)
            if len(self.eddn_hotspots) > 1000:
                self.eddn_hotspots = self.eddn_hotspots[-1000:]
                
        except Exception as e:
            print(f"Error caching EDDN hotspot: {e}")
    
    def _get_eddn_hotspots(self, search_term: str, material_filter: str) -> List[Dict]:
        """Get hotspots from EDDN live data"""
        if not hasattr(self, 'eddn_hotspots') or not self.eddn_hotspots:
            return []
        
        results = []
        search_lower = search_term.lower() if search_term else ""
        
        for hotspot in self.eddn_hotspots:
            # Filter by system name if provided
            if search_term and search_lower not in hotspot['system'].lower():
                continue
            
            # Filter by material if provided
            if material_filter != "All" and material_filter != "All Materials":
                material_match = False
                for material in hotspot['materials']:
                    if material_filter == "Low Temperature Diamond" and material == "LowTemperatureDiamond":
                        material_match = True
                        break
                    elif material_filter == "Void Opal" and material == "VoidOpal":
                        material_match = True
                        break
                    elif material_filter == material:
                        material_match = True
                        break
                
                if not material_match:
                    continue
            
            # Convert to standard format
            for material in hotspot['materials']:
                # Convert material names for display
                display_material = material
                if material == "LowTemperatureDiamond":
                    display_material = "Low Temperature Diamond"
                elif material == "VoidOpal":
                    display_material = "Void Opal"
                
                results.append({
                    'system': hotspot['system'],
                    'body': hotspot['body'],
                    'ring': f"{hotspot['body']} Ring",  # Standardize ring naming
                    'material': display_material,  # For compatibility
                    'hotspots': "1",  # EDDN doesn't provide hotspot count
                    'ls': "Unknown",  # EDDN doesn't provide distance from star
                    'density': "Unknown",  # EDDN doesn't provide density
                    'distance': 0,  # Distance calculation would require coordinates
                    'source': 'EDDN Live',
                    'timestamp': hotspot['timestamp']
                })
        
        return results
    
    def _create_context_menu(self):
        """Create the right-click context menu for results"""
        self.context_menu = tk.Menu(self.parent, tearoff=0,
                                   bg="#2c3e50", fg="#ecf0f1",
                                   activebackground="#3498db", activeforeground="#ffffff",
                                   selectcolor="#e67e22")
        self.context_menu.add_command(label="Copy System Name", command=self._copy_system_name)
    
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
            if values and len(values) > 1:
                system_name = values[1]  # System is column index 1
                self.parent.clipboard_clear()
                self.parent.clipboard_append(system_name)
                self.status_var.set(f"Copied '{system_name}' to clipboard")
    
    def _copy_system_ring(self):
        """Copy the selected system + ring to clipboard"""
        selection = self.results_tree.selection()
        if selection:
            item = selection[0]
            values = self.results_tree.item(item, 'values')
            if values and len(values) > 2:
                system_name = values[1]  # System is column index 1
                ring_name = values[2]    # Ring is column index 2
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