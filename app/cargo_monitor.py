"""Cargo hold monitor: reads Cargo.json, Status.json and the journal, and tracks session cargo and materials."""

import glob
import json
import logging
import os
import queue
import re
import threading
import time
import tkinter as tk

from config import _load_cfg
from journal_parser import JournalParser
from journal_reader import journal_resume_offset, read_complete_journal_lines
from localization import t
from ui.dialogs import centered_yesno_dialog
from ui.refinery_dialog import RefineryDialog
from user_database import UserDatabase

log = logging.getLogger("EliteMining")


class CargoMonitor:
    """
    Cargo monitoring system that reads Elite Dangerous game data.
    
    The main app uses App._update_integrated_cargo_display().

    Cargo data:
    - self.cargo_items: Refined minerals/cargo
    - self.materials_collected: Engineering materials (Raw)
    """
    def __init__(self, update_callback=None, capacity_changed_callback=None, ship_info_changed_callback=None, app_dir=None):
        # Threading safety
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._stop_event = threading.Event()  # For clean thread shutdown
        
        self.max_cargo = 200  # Will be auto-detected from journal
        self.current_cargo = 0
        self.cargo_items = {}  # Dict of item_name: quantity (current cargo hold)
        self.refinery_contents = {}  # Dict of refinery material adjustments
        self.materials_collected = {}  # Dict of engineering material_name: quantity (Raw materials only)
        
        # Multi-session cumulative tracking (for accurate reports when cargo is transferred)
        self.session_minerals_mined = {}  # Dict of refined material: total tons mined (includes transferred)
        self.session_materials_collected = {}  # Dict of engineering material: total pieces collected (includes discarded)
        
        # Localized material names for display (maps English -> Localized)
        self.materials_localized_names = {}  # Dict of English name -> Localized name for display
        
        self.update_callback = update_callback  # Callback to notify main app of changes
        self.capacity_changed_callback = capacity_changed_callback  # Callback when cargo capacity changes
        self.ship_info_changed_callback = ship_info_changed_callback  # Callback when ship info changes
        
        # Engineering materials grade mapping (Raw materials from mining)
        # Grades: 1=Very Common, 2=Common, 3=Standard, 4=Rare
        # Note: Some materials marked "Planet only" in wiki may still drop from asteroids
        self.MATERIAL_GRADES = {
            # Grade 1 - Very Common
            "Carbon": 1,
            "Iron": 1,
            "Lead": 1,
            "Nickel": 1,
            "Phosphorus": 1,
            "Rhenium": 1,
            "Sulphur": 1,
            # Grade 2 - Common
            "Arsenic": 2,
            "Chromium": 2,
            "Germanium": 2,
            "Manganese": 2,
            "Vanadium": 2,
            "Zinc": 2,
            "Zirconium": 2,
            # Grade 3 - Standard
            "Boron": 3,
            "Cadmium": 3,
            "Mercury": 3,
            "Molybdenum": 3,
            "Niobium": 3,
            "Tin": 3,
            "Tungsten": 3,
            # Grade 4 - Rare
            "Antimony": 4,
            "Polonium": 4,
            "Ruthenium": 4,
            "Selenium": 4,
            "Technetium": 4,
            "Tellurium": 4,
            "Yttrium": 4
        }

        self.journal_monitor_active = False
        self.last_journal_file = None
        self.last_file_size = 0
        self._journal_listeners = []
        
        # Elite Dangerous journal directory - load from config or use default
        cfg = _load_cfg()
        saved_dir = cfg.get("journal_dir", None)
        
        if saved_dir and os.path.exists(saved_dir):
            self.journal_dir = saved_dir
        elif hasattr(self, 'prospector_panel'):
            # Use prospector panel's language-aware detection
            detected = self.prospector_panel._detect_journal_dir_default()
            self.journal_dir = detected if detected else os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous")
        else:
            # Fallback to English path
            self.journal_dir = os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous")
        
        # Cargo.json file path for detailed cargo data
        self.cargo_json_path = os.path.join(self.journal_dir, "Cargo.json")
        self.last_cargo_mtime = 0
        
        # Session tracking for mining reports
        self.session_start_snapshot = None
        self.last_mining_activity = None
        self.session_end_dialog_shown = False
        self.mining_activity_timeout = 300  # 5 minutes of inactivity to trigger session end
        
        # Multi-session refinery tracking - prevent multiple prompts for same cargo empty
        self.refinery_prompt_shown_for_this_transfer = False
        self.last_emptied_materials = {}  # Track materials that were just emptied for refinery quick-add
        
        # Transfer event tracking - prevent tracking cargo increases immediately after transfers
        self.last_transfer_time = 0  # Timestamp of last CargoTransfer event
        self.transfer_exclusion_window = 3.0  # Seconds to ignore cargo increases after transfer
        
        # Status.json file path for current ship data  
        self.status_json_path = os.path.join(self.journal_dir, "Status.json")
        
        # Ship information tracking (from LoadGame/Loadout events)
        self.ship_id = None
        self.commander_id = None
        self.ship_name = ""  # User-defined ship name (e.g., "Jewel of Parhoon")
        self.ship_ident = ""  # User-defined ship ID (e.g., "HR-17F")
        self.ship_type = ""  # Ship type (e.g., "Type_9_Heavy", "Python")
        
        # Elite Dangerous ship type mapping (journal code → proper display name)
        self.ship_type_map = {
            # Small ships
            "adder": "Adder",
            "cobramkiii": "Cobra Mk III",
            "cobramkiv": "Cobra Mk IV",
            "cobramkv": "Cobra Mk V",
            "diamondbackxl": "Diamondback Explorer",
            "diamondback": "Diamondback Scout",
            "eagle": "Eagle",
            "empire_eagle": "Imperial Eagle",
            "empire_courier": "Imperial Courier",
            "hauler": "Hauler",
            "sidewinder": "Sidewinder",
            "smallcombat01_nx": "Kestrel Mk II",
            "viper": "Viper Mk III",
            "viper_mkiv": "Viper Mk IV",
            
            # Medium ships
            "asp": "Asp Explorer",
            "asp_scout": "Asp Scout",
            "federation_dropship_mkii": "Federal Assault Ship",
            "federation_dropship": "Federal Dropship",
            "federation_gunship": "Federal Gunship",
            "ferdelance": "Fer-de-Lance",
            "independant_trader": "Keelback",
            "krait_mkii": "Krait Mk II",
            "krait_light": "Krait Phantom",
            "mamba": "Mamba",
            "python": "Python",
            "python_nx": "Python Mk II",
            "type6": "Type-6 Transporter",
            "type7": "Type-7 Transporter",
            "typex": "Alliance Chieftain",
            "typex_2": "Alliance Crusader",
            "typex_3": "Alliance Challenger",
            "vulture": "Vulture",
            
            # Large ships
            "anaconda": "Anaconda",
            "anacondamkii": "Anaconda Mk II",
            "belugaliner": "Beluga Liner",
            "cutter": "Imperial Cutter",
            "dolphin": "Dolphin",
            "empire_trader": "Imperial Clipper",
            "federation_corvette": "Federal Corvette",
            "mandalay": "Mandalay",
            "mediumtransport01": "Lynx Highliner",
            "orca": "Orca",
            "panthermkii": "Panther Clipper Mk II",
            "type8": "Type-8 Transporter",
            "type9": "Type-9 Heavy",
            "type9_military": "Type-10 Defender",
            "lakonminer": "Type-11 Prospector",
            "corsair": "Corsair",
            "explorer_nx": "Caspian Explorer",
        }
        
        # Initialize user database and journal parser for real-time hotspot tracking
        if app_dir:
            # Use provided app directory to construct database path
            data_dir = os.path.join(app_dir, "data")
            db_path = os.path.join(data_dir, "user_data.db")
            print(f"DEBUG: CargoMonitor using explicit database path: {db_path}")
            # import os removed (already imported globally)
            print(f"DEBUG: Current working directory: {os.getcwd()}")
            self.user_db = UserDatabase(db_path)
        else:
            # Fall back to default path resolution
            print("DEBUG: CargoMonitor using default database path resolution")
            self.user_db = UserDatabase()
            print(f"DEBUG: CargoMonitor actual database path: {self.user_db.db_path}")
        self.current_system = None  # Track current system for hotspot detection
        self._update_in_progress = False  # Flag to skip background tasks when update is starting
        
        # Initialize JournalParser for proper Scan and SAASignalsFound processing
        # Add callbacks: hotspot added + game start + reserve updated
        self.journal_parser = JournalParser(self.journal_dir, self.user_db, self._on_hotspot_added, self._on_game_start, self._on_reserve_updated)

        # Attach fleet carrier tracker to journal parser so it reads live carrier_data
        try:
            from fleet_carrier_tracker import get_fleet_carrier_tracker
            get_fleet_carrier_tracker().set_journal_parser(self.journal_parser)
        except Exception as _fce:
            print(f"[FC] Could not attach fleet carrier tracker: {_fce}")
        
        # Flag to track pending Ring Finder refreshes
        self._pending_ring_finder_refresh = False
        
        # Auto-refresh delay timer for ring scans (prevent rapid-fire searches)
        self._auto_refresh_timer = None
        self._auto_refresh_delay = 2000  # 2 seconds - reduced since EDSM fallback now happens immediately
        
        # List to accumulate bodies to highlight when scanning multiple rings quickly
        self._pending_highlight_bodies = []  # List of (system, body) tuples
        
        # EDSM fallback cache to prevent duplicate queries for same system
        self._edsm_fallback_cache = set()  # Track systems already processed
        self._edsm_cache_clear_timer = None  # Timer to clear cache periodically
        
        # Track if this is the first ring scan (no delay needed) vs subsequent scans (delay needed)
        self._first_ring_scan_in_system = True  # Reset when changing systems
        
        # Start journal monitoring regardless of window state
        self.start_journal_monitoring()
        
        # Start background cargo and journal monitoring
        self._start_background_monitoring()
        
        # Try to initialize cargo capacity from Status.json on startup
        self.refresh_ship_capacity()
    
    def _on_game_start(self):
        """Callback triggered when LoadGame event is detected (game started)
        
        Forces a refresh of current location in case Location event was missed during startup
        """
        try:
            print("[GAME START] LoadGame detected - refreshing current system...")
            
            # Re-read the most recent system from journal files
            most_recent_system = self.journal_parser.get_most_recent_system()
            
            if most_recent_system:
                print(f"[GAME START] Found current system: {most_recent_system}")
                self.current_system = most_recent_system
                
                # Update UI displays
                self._update_system_display()
                
                # Update Ring Finder if it exists (only if auto-search is enabled)
                if (hasattr(self, 'ring_finder') and self.ring_finder
                        and getattr(self.ring_finder, 'auto_search_var', None) and self.ring_finder.auto_search_var.get()):
                    self.ring_finder.system_var.set(most_recent_system)
        except Exception as e:
            log.error(f"[GAME START] Error handling LoadGame: {e}")
    
    def _on_reserve_updated(self, system_name: str):
        """Callback triggered when reserve levels are updated in database
        
        Refreshes Ring Finder UI if it's showing results for the updated system
        
        Args:
            system_name: System that had reserve levels updated
        """
        try:
            # Check if Ring Finder is showing results and if it includes this system
            if hasattr(self, 'ring_finder') and self.ring_finder:
                # Refresh using cached data to update reserve column
                if hasattr(self.ring_finder, '_search_cache') and self.ring_finder._search_cache:
                    # Check if updated system is in current results
                    system_in_results = any(
                        h.get('system', '').lower() == system_name.lower() or 
                        h.get('systemName', '').lower() == system_name.lower()
                        for h in self.ring_finder._search_cache
                    )
                    if system_in_results:
                        print(f"[RESERVE] Refreshing Ring Finder UI for {system_name}")
                        self.ring_finder._update_results(self.ring_finder._search_cache)
        except Exception as e:
            log.error(f"[RESERVE] Error refreshing UI: {e}")
                
        except Exception as e:
            log.error(f"[GAME START] Error refreshing location: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_hotspot_added(self, is_new_discovery: bool = False, normalized_system: str = None, normalized_body: str = None):
        """Callback triggered when new hotspot data is added to database
        
        Args:
            is_new_discovery: True if these are newly discovered hotspots (not already in database)
            normalized_system: The normalized system name (e.g., "HIP 39383" not "HIP 39383 BC")
            normalized_body: The normalized body name (e.g., "BC 3 A Ring" not "3 A Ring")
        """
        try:
            # Access main app through main_app_ref if this is called from CargoMonitor
            main_app = getattr(self, 'main_app_ref', self)
            
            # Check if Ring Finder exists and is properly initialized
            ring_finder_ready = (hasattr(main_app, 'ring_finder') and 
                                 main_app.ring_finder is not None and
                                 hasattr(main_app.ring_finder, '_update_database_info'))
            
            if not ring_finder_ready:
                main_app._pending_ring_finder_refresh = True
                return
                
            # Ring Finder exists - refresh it now
            main_app._refresh_ring_finder(is_new_discovery=is_new_discovery)

            # Auto-search refresh: Only if NEW hotspots were discovered AND not during catchup scan
            refresh_args = None
            if is_new_discovery and not getattr(self, '_catchup_scan_in_progress', False):
                # Use normalized system/body names if provided, otherwise fall back to stored values
                scanned_system = normalized_system or getattr(self, '_current_saa_system', None)
                scanned_body = normalized_body or getattr(self, '_current_saa_body', None)
                if scanned_system:
                    refresh_args = (scanned_system, scanned_body, True)

            # IMMEDIATE EDSM FALLBACK: Fill missing metadata for newly scanned system
            # This ensures auto-refresh shows complete data after the 5-second delay
            edsm_system = None
            if hasattr(main_app, 'ring_finder') and main_app.ring_finder and self.current_system:
                # Check cache to avoid duplicate EDSM queries for same system
                if self.current_system not in self._edsm_fallback_cache:
                    # Add to cache immediately
                    self._edsm_fallback_cache.add(self.current_system)

                    # Schedule cache cleanup after 30 seconds
                    if self._edsm_cache_clear_timer:
                        main_app.after_cancel(self._edsm_cache_clear_timer)
                    self._edsm_cache_clear_timer = main_app.after(30000, lambda: self._edsm_fallback_cache.clear())
                    if hasattr(main_app.ring_finder, 'edsm'):
                        edsm_system = self.current_system
                else:
                    print(f"⚡ EDSM fallback skipped for {self.current_system} (already processed)")

            if edsm_system or refresh_args:
                # The EDSM lookup is a web request (up to 15 s), so it runs on the background worker.
                # The auto-refresh waits behind it, and behind any earlier lookup, so it shows the filled data.
                edsm = main_app.ring_finder.edsm if edsm_system else None

                def lookup_then_refresh():
                    if edsm_system:
                        try:
                            stats = edsm.fill_missing_metadata_for_systems_direct([edsm_system])
                            if stats.get('materials_updated', 0) > 0:
                                print(f"[OK] EDSM immediate fallback: Updated {stats['rings_updated']} rings, {stats['materials_updated']} materials")
                            else:
                                print(f"ℹ EDSM immediate fallback: No updates needed for {edsm_system}")
                        except Exception as e:
                            log.error(f"⚠ EDSM immediate fallback failed: {e}")
                    if refresh_args:
                        main_app.after(0, self._check_auto_refresh_ring_finder, *refresh_args)

                self._queue_background_job(lookup_then_refresh)

        except Exception as e:
            # Log error but don't break other functionality
            log.warning(f"Warning: Failed to refresh Ring Finder after hotspot add: {e}")
    
    def _check_auto_refresh_ring_finder(self, scanned_system: str, scanned_body: str = None, hotspots_were_new: bool = False):
        """Check if Ring Finder should auto-refresh after ring scan
        
        Args:
            scanned_system: System name where ring was scanned
            scanned_body: Body/ring name
            hotspots_were_new: True if hotspots were newly discovered (not already in database)
        """
        try:
            # CRITICAL: Only refresh if NEW hotspots were actually discovered
            # Existing hotspots or proximity re-scans should NOT trigger refresh
            if not hotspots_were_new:
                return
            
            # Access main app to get Ring Finder
            main_app = getattr(self, 'main_app_ref', self)
            
            # Check if Ring Finder exists and auto-search is enabled
            if not (hasattr(main_app, 'ring_finder') and 
                   main_app.ring_finder is not None and
                   hasattr(main_app.ring_finder, 'auto_search_var')):
                return
            
            ring_finder = main_app.ring_finder
            
            # Only refresh if auto-search is enabled
            if not ring_finder.auto_search_var.get():
                return
            
            # Only refresh if scanning in the same system as current search
            current_reference_system = ring_finder.system_var.get().strip()
            
            # If reference system is empty, populate it with scanned system
            if not current_reference_system:
                ring_finder.system_var.set(scanned_system)
                current_reference_system = scanned_system
            elif not (current_reference_system.lower() == scanned_system.lower() or
                      scanned_system.lower().startswith(current_reference_system.lower()) or
                      current_reference_system.lower().startswith(scanned_system.lower())):
                # Different system - reset first scan flag but don't refresh
                self._first_ring_scan_in_system = True
                self._pending_highlight_bodies = []  # Clear pending highlights for new system
                return
            
            # Add this body to the pending highlights (accumulate, don't replace)
            if scanned_body:
                body_tuple = (scanned_system, scanned_body)
                if body_tuple not in self._pending_highlight_bodies:
                    self._pending_highlight_bodies.append(body_tuple)
            
            # Cancel existing timer and restart (debounce)
            # This ensures we wait for a brief pause in scanning before refreshing
            if self._auto_refresh_timer:
                main_app.after_cancel(self._auto_refresh_timer)
                self._auto_refresh_timer = None
            
            # Use 2s delay to allow grouping multiple ring scans together
            delay = 2000  # 2 seconds delay
            delay_text = "in 2s"
            
            # Track first scan for future use if needed
            if self._first_ring_scan_in_system:
                self._first_ring_scan_in_system = False
            
            # Set status message - must be on main thread
            pending_count = len(self._pending_highlight_bodies)
            if pending_count > 1:
                main_app.after(0, lambda: ring_finder.status_var.set(f"Found {pending_count} new rings - search {delay_text}"))
            else:
                main_app.after(0, lambda: ring_finder.status_var.set(f"Found new hotspots - search {delay_text}"))
            
            # Capture the accumulated bodies for the closure
            bodies_to_highlight = list(self._pending_highlight_bodies)
            
            # Schedule the actual refresh with appropriate delay
            def do_delayed_refresh():
                try:
                    # All UI updates must be on main thread
                    ring_finder.status_var.set(f"Found new hotspots - updating results")
                    
                    # Pass ALL accumulated bodies so they all get highlighted
                    ring_finder.search_hotspots(highlight_bodies=bodies_to_highlight)
                    self._auto_refresh_timer = None  # Clear timer reference
                    self._pending_highlight_bodies = []  # Clear after successful refresh
                except Exception:
                    log.exception("Delayed Ring Finder auto-refresh failed")
            
            # Schedule refresh with delay - already on main thread via after()
            self._auto_refresh_timer = main_app.after(delay, do_delayed_refresh)
            
        except Exception:
            # Never break journal processing, but leave a trace
            log.exception("Ring Finder auto-refresh scheduling failed")

    def get_ship_info_string(self) -> str:
        """
        Get formatted ship information string for display.
        
        Returns:
            Formatted ship info (e.g., "Jewel of Parhoon (HR-17F) - Type-9 Heavy")
            or empty string if no ship data available
        """
        if not self.ship_name and not self.ship_type:
            return ""
        
        # Ship type is already formatted if it came from Ship_Localised
        ship_type_display = self.ship_type if self.ship_type else ""
        
        # Build ship info string
        parts = []
        # Use ShipName if it's a custom name (differs from ship type), else fall back to ShipIdent
        display_name = ""
        if self.ship_name and self.ship_name.lower() != ship_type_display.lower():
            display_name = self.ship_name
        elif self.ship_ident:
            display_name = self.ship_ident
        if display_name:
            formatted_name = display_name.title()
            formatted_name = formatted_name.replace("Mk Ii", "Mk II").replace("Mk Iii", "Mk III")
            formatted_name = formatted_name.replace("Mk Iv", "Mk IV").replace("Mk V", "Mk V")
            formatted_name = formatted_name.replace("Mk Vi", "Mk VI").replace("Mk Vii", "Mk VII")
            parts.append(formatted_name)
        # Ship ident (ID) removed from display - not needed for analytics
        # Users don't need to see (VIPD68) style IDs in reports/analytics
        if ship_type_display and ship_type_display not in ["", "Unknown"]:
            parts.append(f"- {ship_type_display}" if parts else ship_type_display)
        
        return " ".join(parts) if parts else ""

    def read_cargo_json(self):
        """Read detailed cargo data from Cargo.json file"""
        try:
            if not os.path.exists(self.cargo_json_path):
                return False
                
            # Check if file has been modified
            current_mtime = os.path.getmtime(self.cargo_json_path)
            if current_mtime <= self.last_cargo_mtime:
                return False  # No changes
                
            self.last_cargo_mtime = current_mtime
            
            with open(self.cargo_json_path, 'r', encoding='utf-8') as f:
                cargo_data = json.load(f)
            
            # Extract cargo information
            count = cargo_data.get("Count", 0)
            inventory = cargo_data.get("Inventory", [])
            
            # Build new cargo dict and track changes
            new_cargo = {}
            for item in inventory:
                name = item.get("Name", "").lower()
                name_localized = item.get("Name_Localised", "")
                item_count = item.get("Count", 0)
                stolen = item.get("Stolen", 0)
                
                # Use localized name if available, otherwise clean up internal name
                # ALWAYS normalize to Title Case to prevent duplicates from capitalization variations
                if name_localized:
                    display_name = name_localized.title()
                else:
                    display_name = name.replace("_", " ").title()

                # Normalize "Low Temp. Diamonds" variant to canonical form so cargo
                # tracking doesn't split the same material into two dict keys
                if display_name.lower() in ('low temp. diamonds', 'low temp diamonds'):
                    display_name = 'Low Temperature Diamonds'

                if display_name and item_count > 0:
                    new_cargo[display_name] = item_count
                    
                    # Track session minerals ONLY if:
                    # 1. Mining session is active
                    # 2. NOT within exclusion window after transfer
                    # 3. Quantity increased (actual mining)
                    # 4. Not limpets/drones
                    time_since_transfer = time.time() - self.last_transfer_time
                    within_exclusion_window = time_since_transfer < self.transfer_exclusion_window
                    
                    if (self.session_start_snapshot and 
                        not within_exclusion_window and
                        "limpet" not in display_name.lower() and 
                        "drone" not in display_name.lower()):
                        
                        old_qty = self.cargo_items.get(display_name, 0)
                        if item_count > old_qty:
                            added = item_count - old_qty
                            self.session_minerals_mined[display_name] = self.session_minerals_mined.get(display_name, 0) + added
                            print(f"[DEBUG] read_cargo_json tracked {added}t of {display_name}, session total: {self.session_minerals_mined[display_name]}t")
                    elif within_exclusion_window:
                        print(f"[DEBUG] read_cargo_json SKIPPED tracking {display_name} (within {time_since_transfer:.1f}s of transfer)")
            
            # Update cargo items
            self.cargo_items = new_cargo
            self.current_cargo = count

            # Update mining mission progress from cargo
            self._update_mission_progress_from_cargo()

            # The update callback touches Tk widgets and must run on the main thread.
            # Tcl/Tk is not thread-safe and this can be reached from the
            # background journal-monitor thread.
            main_app = getattr(self, 'main_app_ref', None)
            if main_app is not None and threading.current_thread() is not threading.main_thread():
                main_app.after(0, self._finish_read_cargo_json)
            else:
                self._finish_read_cargo_json()

            return True

        except Exception as e:
            return False

    def _finish_read_cargo_json(self):
        """UI-touching tail of read_cargo_json — must run on the main thread."""
        if self.update_callback:
            self.update_callback()
    
    def _update_mission_progress_from_cargo(self):
        """Update mining mission progress based on current cargo contents"""
        try:
            from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
            if MISSIONS_AVAILABLE and self.cargo_items:
                tracker = get_mission_tracker()
                if tracker:
                    # Build cargo dict with just names and quantities
                    cargo_dict = {}
                    for name, data in self.cargo_items.items():
                        if isinstance(data, dict):
                            cargo_dict[name] = data.get('Count', 0)
                        else:
                            cargo_dict[name] = data
                    tracker.update_progress_from_cargo(cargo_dict)
        except Exception as e:
            log.error(f"[MISSIONS] Error updating progress: {e}")
    
    def force_cargo_update(self):
        """Force read the latest cargo data from Cargo.json and journal"""
        
        # First, try to read from Cargo.json (most accurate)
        if self.read_cargo_json():
            return
        
        # Fallback to journal events (less detailed)
        self.cargo_items.clear()
        self.current_cargo = 0
        
        # Re-read the entire current journal file to find the latest Cargo event
        try:
            if self.last_journal_file and os.path.exists(self.last_journal_file):
                with open(self.last_journal_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Process all lines to find the most recent Cargo and Loadout events
                latest_cargo = None
                latest_loadout = None
                
                for line in lines:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            event_type = event.get("event", "")
                            if event_type == "Cargo":
                                latest_cargo = event
                            elif event_type == "Loadout":
                                latest_loadout = event
                        except:
                            continue
                
                # Process the latest events we found
                if latest_loadout:
                    self.process_journal_event(json.dumps(latest_loadout))
                
                if latest_cargo:
                    inventory = latest_cargo.get("Inventory", [])
                    count = latest_cargo.get("Count", 0)
                    
                    if inventory:
                        for item in inventory:
                            name = item.get("Name", "").replace("$", "").replace("_name;", "")
                            name_localized = item.get("Name_Localised", name)
                            item_name = name_localized if name_localized else name.replace("_", " ").title()
                            item_count = item.get("Count", 0)
                            if item_name and item_count > 0:
                                self.cargo_items[item_name] = item_count
                        
                        self.current_cargo = sum(self.cargo_items.values())
                        
                        # Notify main app of changes
                        if self.update_callback:
                            self.update_callback()
                        
                    else:
                        self.current_cargo = count  # At least show the total
                        
                        # Notify main app of changes
                        if self.update_callback:
                            self.update_callback()

        except Exception as e:
            log.warning("Forced cargo refresh failed: %s", e)

    def set_max_cargo(self, max_cargo: int):
        """Set maximum cargo capacity"""
        self.max_cargo = max_cargo
    
    def update_cargo(self, item_name: str, quantity: int):
        """Update cargo item quantity and track session minerals"""
        old_quantity = self.cargo_items.get(item_name, 0)
        
        if quantity <= 0:
            self.cargo_items.pop(item_name, None)
        else:
            self.cargo_items[item_name] = quantity
            
            # Track session cumulative total for multi-session mode
            # Only count increases (mining), not decreases (selling/transferring)
            # Only track if a mining session is active
            if (self.session_start_snapshot and 
                quantity > old_quantity and 
                "limpet" not in item_name.lower() and 
                "drone" not in item_name.lower()):
                added = quantity - old_quantity
                self.session_minerals_mined[item_name] = self.session_minerals_mined.get(item_name, 0) + added
                print(f"[DEBUG] Tracked {added}t of {item_name}, session total now: {self.session_minerals_mined[item_name]}t")
                print(f"[DEBUG] Full session_minerals_mined: {self.session_minerals_mined}")
                
                # Reset refinery prompt flag when mining resumes (cargo increasing)
                self.refinery_prompt_shown_for_this_transfer = False
        
        self.current_cargo = sum(self.cargo_items.values())
        
        # Record mining activity for session end detection
        self.record_mining_activity()
        
        # Notify main app of changes
        if self.update_callback:
            self.update_callback()
    
    def set_total_cargo(self, total: int):
        """Set total cargo directly (for manual updates)"""
        self.current_cargo = total
        
        # Notify main app of changes
        if self.update_callback:
            self.update_callback()

    def clear_cargo(self):
        """Clear all cargo items"""
        self.cargo_items.clear()
        self.current_cargo = 0
    
    def reset_materials(self):
        """Reset materials counters and session tracking (called when mining session starts)"""
        self.materials_collected.clear()
        self.session_minerals_mined.clear()
        self.session_materials_collected.clear()
        
        # Take snapshot of current cargo as baseline - don't count pre-existing cargo
        # This ensures only NEW materials mined after session start are tracked
        # (Already handled by cargo_items being preserved, tracking only counts increases)
        
        print("[CargoMonitor] Materials counters and session tracking reset")
        print(f"[CargoMonitor] Session baseline: {len(self.cargo_items)} items, {self.current_cargo}t total")
    
    def start_journal_monitoring(self):
        """Start monitoring Elite Dangerous journal files"""
        self.journal_monitor_active = True
        self._journal_initializing = True
        self.find_latest_journal(skip_existing=True)
    
    def _start_background_monitoring(self):
        """Start background cargo and journal monitoring"""
        self.last_status_mtime = 0
        self.last_capacity_check = 0
        self.last_heartbeat = time.time()  # Track thread health
        
        def background_monitor():
            while not self._stop_event.is_set():
                # The thread must survive a pause in monitoring
                if not self.journal_monitor_active:
                    time.sleep(0.5)
                    continue
                try:
                    # Heartbeat: Log every 60 seconds to verify thread is alive
                    current_time = time.time()
                    if current_time - self.last_heartbeat > 60:
                        self.last_heartbeat = current_time
                        with self._lock:  # Thread-safe access to materials_collected
                            materials_count = len(self.materials_collected)
                        logging.debug(f"[HEARTBEAT] Background monitor alive - Materials: {materials_count}")
                    
                    # Check Status.json first for ship changes (faster than journal)
                    self._check_status_for_ship_changes()
                    
                    # Periodic capacity validation (every 30 seconds during mining)
                    current_time = time.time()
                    if current_time - self.last_capacity_check > 30:
                        self.last_capacity_check = current_time
                        if not self._validate_cargo_capacity():
                            # Try multiple refresh methods
                            if not self.refresh_ship_capacity():
                                self._force_loadout_scan()
                    
                    # Check for Cargo.json updates (most accurate)
                    self.read_cargo_json()
                    
                    self._poll_journal()
                        
                except Exception as e:
                    logging.error(f"[BACKGROUND_MONITOR] ERROR: {e}")
                    import traceback
                    logging.error(traceback.format_exc())
                
                time.sleep(0.5)  # Keep standard 0.5s interval
        
        # Start background thread
        monitor_thread = threading.Thread(target=background_monitor, daemon=True)
        monitor_thread.start()
        
    def _check_status_for_ship_changes(self):
        """Monitor Status.json for real-time ship capacity changes"""
        try:
            if os.path.exists(self.status_json_path):
                current_mtime = os.path.getmtime(self.status_json_path)
                if current_mtime > self.last_status_mtime:
                    self.last_status_mtime = current_mtime
                    
                    with open(self.status_json_path, 'r') as f:
                        status_data = json.load(f)
                    
                    # Check for cargo capacity changes (validate it's reasonable)
                    new_capacity = status_data.get("CargoCapacity")
                    if new_capacity and new_capacity > 0 and new_capacity != self.max_cargo:
                        # Sanity check: capacity should be between 2-2048 tons for valid ships
                        if 2 <= new_capacity <= 2048:
                            old_capacity = self.max_cargo
                            self.max_cargo = new_capacity

                            # Notify main app of capacity change
                            if self.capacity_changed_callback:
                                self.capacity_changed_callback(self.max_cargo)
                                
                            # Force refresh cargo data after ship change
                            self.read_cargo_json()

        except json.JSONDecodeError:
            pass  # Game is mid-write; the next change re-reads it
        except Exception:
            log.exception("Status.json check failed")
    
    def read_status_json_cargo(self):
        """Read current cargo weight from Status.json (real-time data)"""
        try:
            if os.path.exists(self.status_json_path):
                with open(self.status_json_path, 'r') as f:
                    status_data = json.load(f)
                
                # Status.json contains current cargo weight (real-time)
                current_cargo_weight = status_data.get("Cargo", 0)
                cargo_capacity = status_data.get("CargoCapacity", self.max_cargo)
                
                print(f"Status.json cargo: {current_cargo_weight}t / {cargo_capacity}t")
                
                # If we have real-time cargo weight but no detailed breakdown,
                # we can at least show the correct total
                if current_cargo_weight > 0 and not self.cargo_items:
                    # Set the total without item breakdown
                    self.current_cargo = current_cargo_weight
                    self.max_cargo = cargo_capacity
                    return True
                elif current_cargo_weight == 0:
                    # If Status.json shows 0 cargo, clear everything
                    self.cargo_items.clear()
                    self.current_cargo = 0
                    self.max_cargo = cargo_capacity
                    return True
                    
                return False
        except Exception as e:
            log.error(f"Error reading Status.json: {e}")
            return False
    
    def stop_journal_monitoring(self):
        """Stop journal monitoring"""
        self.journal_monitor_active = False
        """Start monitoring Elite Dangerous journal files"""
        self.journal_monitor_active = True
        self.find_latest_journal()
    
    def stop_journal_monitoring(self):
        """Stop journal monitoring"""
        self.journal_monitor_active = False
    
    def cleanup(self):
        """Clean up CargoMonitor resources for safe shutdown"""
        print("[CargoMonitor] Starting cleanup...")
        
        # Signal threads to stop
        self._stop_event.set()
        
        # Stop journal monitoring
        self.journal_monitor_active = False

        print("[CargoMonitor] Cleanup completed")
    
    def _poll_journal(self):
        if getattr(self, '_journal_initializing', False):
            self.find_latest_journal(skip_existing=True)
            return
        with self._lock:
            current = self.last_journal_file
        if current and os.path.normcase(os.path.abspath(os.path.dirname(current))) != os.path.normcase(os.path.abspath(self.journal_dir)):
            with self._lock:
                self.last_journal_file = None
                self.last_file_size = 0
            self._journal_initializing = True
            self.find_latest_journal(skip_existing=True)
            return
        # A new journal only appears when the game restarts, so listing the folder every tick is wasted work
        now = time.time()
        if current and os.path.exists(current) and now - getattr(self, '_journal_list_time', 0) < 5:
            paths = [current]
        else:
            self._journal_list_time = now
            journal_files = glob.glob(os.path.join(self.journal_dir, "Journal.*.log"))
            if current:
                paths = [current] + sorted(path for path in journal_files if path > current)
            else:
                paths = sorted(journal_files)
        for path in paths:
            if not os.path.exists(path):
                continue
            with self._lock:
                if getattr(self, '_reading_journal', False):
                    return
                if path != self.last_journal_file:
                    logging.info(f"[JOURNAL_ROTATION] Detected new journal file: {os.path.basename(path)}")
                    self.last_journal_file = path
                    self.last_file_size = 0
            if not self.read_new_journal_entries():
                if os.path.exists(path):
                    break

    def find_latest_journal(self, skip_existing=False):
        """Attach to the latest journal, skipping history only during startup."""
        try:
            journal_files = glob.glob(os.path.join(self.journal_dir, "Journal.*.log"))
            if not journal_files:
                if skip_existing:
                    self._journal_initializing = False
                return
            latest_file = max(journal_files)
            with self._lock:
                if getattr(self, '_reading_journal', False):
                    return
                if latest_file == self.last_journal_file and not skip_existing:
                    return
                offset = journal_resume_offset(latest_file) if skip_existing else 0
                self.last_journal_file = latest_file
                self.last_file_size = offset
                self._journal_initializing = False
            self.scan_journal_for_cargo_capacity(latest_file)
        except Exception as e:
            log.error(f"Error finding journal files: {e}")

    def scan_journal_for_cargo_capacity(self, journal_file):
        """Scan existing journal file for the most recent CargoCapacity, current system location, and ring metadata"""
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            ship_found = False
            commander_found = False
            for line in reversed(lines):
                try:
                    event = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                event_type = event.get("event", "")
                if not commander_found and event_type in ("Commander", "LoadGame") and event.get("FID"):
                    self.commander_id = event["FID"]
                    commander_found = True
                if not ship_found and event_type in ("LoadGame", "Loadout"):
                    self._update_ship_info(event)
                    ship_found = True
                if ship_found and commander_found:
                    break

            # Detect game language from Fileheader (first few lines)
            for line in lines[:10]:
                try:
                    event = json.loads(line.strip())
                    if event.get("event") == "Fileheader":
                        language = event.get("language", "English/UK")
                        from material_utils import set_game_language
                        if 'German' in language:
                            set_game_language('de')
                        elif 'French' in language:
                            set_game_language('fr')
                        elif 'Spanish' in language:
                            set_game_language('es')
                        elif 'Russian' in language:
                            set_game_language('ru')
                        else:
                            set_game_language('en')
                        print(f"[DEBUG] Game language detected: {language}")
                        break
                except:
                    pass
            
            cargo_found = False
            location_found = False
            scans_processed = 0
            max_scans = 50  # Limit scan events to process (performance)

            # Look for the most recent Loadout, LoadGame, Location/FSDJump, and Scan events
            for line in reversed(lines):  # Start from the end (most recent)
                try:
                    event = json.loads(line.strip())
                    event_type = event.get("event", "")
                    
                    # Look for cargo capacity (existing logic)
                    if not cargo_found and event_type == "Loadout":
                        # Check for CargoCapacity at root level
                        if "CargoCapacity" in event:
                            old_capacity = self.max_cargo
                            self.max_cargo = event["CargoCapacity"]
                            
                            # Notify main app of capacity change
                            if old_capacity != self.max_cargo and self.capacity_changed_callback:
                                self.capacity_changed_callback(self.max_cargo)
                            cargo_found = True
                            continue
                        
                        # Check in Ship data as fallback
                        ship_data = event.get("Ship", {})
                        if "CargoCapacity" in ship_data:
                            old_capacity = self.max_cargo
                            self.max_cargo = ship_data["CargoCapacity"]
                            
                            # Notify main app of capacity change
                            if old_capacity != self.max_cargo and self.capacity_changed_callback:
                                self.capacity_changed_callback(self.max_cargo)
                            cargo_found = True
                            continue
                    
                    # Look for current system location (existing logic)
                    elif not location_found and event_type in ["FSDJump", "Location", "CarrierJump"]:
                        system_name = event.get("StarSystem", "")
                        print(f"DEBUG: Found {event_type} event with system: {system_name}")
                        if system_name:
                            self.current_system = system_name
                            location_found = True
                            
                            # Update Ring Finder reference system if it exists (only if auto-search is enabled)
                            if (hasattr(self, 'ring_finder') and self.ring_finder
                                    and getattr(self.ring_finder, 'auto_search_var', None) and self.ring_finder.auto_search_var.get()):
                                self.ring_finder.system_var.set(system_name)
                            
                            # NOTE: Do NOT update last_known_system here!
                            # Visit counting logic depends on comparing current system to last_known_system
                            # which is initialized from the database. Updating it here would prevent
                            # detection of offline carrier jumps (Location event after FC jump while logged out)
                            
                            # Update distance calculator home/FC distances in main app
                            if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, '_update_home_fc_distances'):
                                try:
                                    self.main_app_ref._update_home_fc_distances()
                                except:
                                    pass
                            continue

                    # Process Scan events for ring metadata (new logic)
                    elif event_type == "Scan" and scans_processed < max_scans:
                        self._process_scan_event(event)
                        scans_processed += 1
                        continue

                    # Stop scanning once cargo and location are found
                    # (Scan events are handled by background journal catchup thread)
                    if cargo_found and location_found:
                        break
                except json.JSONDecodeError:
                    continue  # Skip invalid JSON lines
            if self.ship_info_changed_callback:
                self.ship_info_changed_callback()
        except Exception:
            log.exception("Journal capacity/ship scan failed")

    def check_session_end(self):
        """Check if mining session has ended and show refinery dialog if needed"""
        import time
        from tkinter import messagebox
        
        # Check if multi-session mode is enabled
        is_multi_session = False
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        # Skip session-end refinery prompt in multi-session mode
        # (refinery materials are already captured after each transfer/sale)
        if is_multi_session:
            return
        
        # Only check if we have had mining activity and enough time has passed
        if (self.last_mining_activity and 
            not self.session_end_dialog_shown and 
            self.cargo_items and  # Only if we have cargo items detected
            len(self.cargo_items) > 0):
            
            time_since_activity = time.time() - self.last_mining_activity
            
            # If 5 minutes have passed since last mining activity
            if time_since_activity >= self.mining_activity_timeout:
                self.session_end_dialog_shown = True
                
                # Get the main app window for proper positioning.
                parent_window = None
                if hasattr(self, 'prospector_panel') and self.prospector_panel:
                    parent_window = self.prospector_panel.winfo_toplevel()
                
                # Show refinery dialog
                try:
                    dialog = RefineryDialog(
                        parent=parent_window,
                        cargo_monitor=self,
                        current_cargo_items=self.cargo_items.copy()
                    )
                    result = dialog.show()
                    
                    if result:  # User added refinery contents
                        # Store refinery contents for integration with reports
                        self.refinery_contents = result.copy()
                        
                        # Add refinery materials to actual cargo items for live display
                        for material_name, refinery_qty in result.items():
                            if material_name in self.cargo_items:
                                self.cargo_items[material_name] += refinery_qty
                            else:
                                self.cargo_items[material_name] = refinery_qty
                        
                        # Update current cargo total
                        self.current_cargo = sum(self.cargo_items.values())
                        
                        # Calculate totals
                        refinery_total = sum(result.values())

                        # Notify main app of changes
                        if self.update_callback:
                            self.update_callback()
                        
                        # Show confirmation
                        print(f"Refinery contents applied: {len(result)} materials, {refinery_total} tons total")
                        from app_utils import centered_message
                        centered_message(parent_window, "Refinery Contents Added",
                                         f"Added {refinery_total} tons from refinery.\n"
                                         f"New total: {self.current_cargo} tons\n\n"
                                         f"These materials will be included in mining reports and statistics.")
                    
                except Exception as e:
                    log.error(f"Error showing refinery dialog: {e}")
    
    def record_mining_activity(self):
        """Record that mining activity occurred (call when cargo changes)"""
        import time
        self.last_mining_activity = time.time()
        self.session_end_dialog_shown = False  # Reset dialog flag if activity resumes
    
    def _prompt_for_refinery_contents_multi_session(self):
        """
        Prompt user to add refinery contents when cargo is emptied in multi-session mode.
        Called after CargoTransfer or MarketSell events that empty the cargo hold.
        Single sessions skip this dialog - refinery is handled when the session ends.
        """
        print(f"[DEBUG] _prompt_for_refinery_contents_multi_session called")
        print(f"[DEBUG] refinery_prompt_shown_for_this_transfer: {self.refinery_prompt_shown_for_this_transfer}")
        print(f"[DEBUG] session_start_snapshot: {self.session_start_snapshot is not None}")
        print(f"[DEBUG] current_cargo: {self.current_cargo}")
        
        # Check if multi-session mode is enabled
        is_multi_session = False
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        # Show dialog ONLY for multi-session mode (single sessions handle refinery at session end)
        if not is_multi_session:
            print("[DEBUG] Skipping refinery prompt - single session mode (refinery handled at session end)")
            return
        
        # Prevent multiple prompts for the same cargo empty event
        if self.refinery_prompt_shown_for_this_transfer:
            print("[DEBUG] Skipping - already shown prompt for this transfer")
            return
        
        # Don't show prompt if no mining session active
        if not self.session_start_snapshot:
            print("[DEBUG] Skipping - no active mining session")
            return
        
        print("[DEBUG] Showing refinery prompt...")
        try:
            from tkinter import messagebox
            import tkinter as tk
            
            # Get main app window (NOT prospector_panel subframe!)
            parent_window = None
            if hasattr(self, 'prospector_panel') and self.prospector_panel:
                # Get the actual top-level window, not the panel widget
                parent_window = self.prospector_panel.winfo_toplevel()
            
            # Ask if user wants to add refinery materials - use parent directly
            add_refinery = centered_yesno_dialog(
                parent_window,
                "Refinery Materials",
                "Do you have any additional materials in your refinery that you want to add to this session?"
            )
            
            # Mark that we've shown the prompt for this transfer
            self.refinery_prompt_shown_for_this_transfer = True
            
            if add_refinery:
                try:
                    # Open refinery dialog with materials that were just emptied
                    dialog = RefineryDialog(
                        parent=parent_window,
                        cargo_monitor=self,
                        current_cargo_items=self.last_emptied_materials  # Use materials that were just emptied
                    )
                    refinery_result = dialog.show()
                    
                    if refinery_result:  # User added refinery contents
                        # Add refinery materials to cumulative session tracking
                        for material_name, quantity in refinery_result.items():
                            # Add to session_minerals_mined for report totals
                            self.session_minerals_mined[material_name] = \
                                self.session_minerals_mined.get(material_name, 0) + quantity
                            print(f"[Refinery Multi-Session] Added {quantity}t of {material_name}, " + 
                                  f"session total now: {self.session_minerals_mined[material_name]}t")
                        
                        # Calculate totals
                        refinery_total = sum(refinery_result.values())
                        print(f"[Refinery Multi-Session] Total added from refinery: {refinery_total}t")
                        
                        # Show confirmation
                        from app_utils import centered_message
                        centered_message(parent_window, "Refinery Contents Added",
                                         f"Added {refinery_total} tons from refinery.\n\n"
                                         f"These materials will be included in your multi-session mining report.")
                        
                        # DON'T call update_callback here - it triggers report generation!
                        # In multi-session mode, reports are only generated when ending the session
                        # Just update the display statistics instead
                        if hasattr(self, 'prospector_panel') and self.prospector_panel:
                            self.prospector_panel._update_statistics_display()
                        
                except Exception as e:
                    log.error(f"Error showing refinery dialog in multi-session: {e}")
                    
        except Exception as e:
            log.error(f"Error prompting for refinery contents: {e}")
    
    def read_new_journal_entries(self):
        with self._lock:
            if getattr(self, '_reading_journal', False):
                return False
            self._reading_journal = True
        try:
            return self._read_new_journal_entries()
        finally:
            with self._lock:
                self._reading_journal = False

    def _read_new_journal_entries(self):
        """Read new entries from the journal file with retry logic for file locking issues"""
        max_retries = 3
        retry_delay = 0.1  # 100ms delay between retries
        
        for attempt in range(max_retries):
            try:
                with self._lock:
                    new_lines, position = read_complete_journal_lines(self.last_journal_file, self.last_file_size)
                    self.last_file_size = position

                events = []
                for line in new_lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except ValueError:
                        continue
                if events:
                    self._dispatch_journal_events(events)

                return True
                        
            except PermissionError as e:
                # File is locked by another application - retry
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"Journal file locked by another application after {max_retries} retries (other apps scanning journals?)")
            except FileNotFoundError:
                # The next poll will discover the replacement journal.
                print(f"Journal file not found (rotated to new file): {self.last_journal_file}")
                return False
            except Exception as e:
                log.error(f"Error reading journal entries: {e}")
                return False
        return False
    
    def add_journal_listener(self, callback):
        """Receive each batch of new live journal events (parsed dicts) on the main thread"""
        if callback not in self._journal_listeners:
            self._journal_listeners.append(callback)

    def _dispatch_journal_events(self, events):
        main_app = getattr(self, 'main_app_ref', None)
        if main_app is not None and threading.current_thread() is not threading.main_thread():
            main_app.after(0, self._deliver_journal_events, events)
            return
        self._deliver_journal_events(events)

    def _queue_cache_upserts(self, event):
        """Store PowerPlay and system status from a jump/location event off the UI thread.
        One worker keeps the writes in journal order."""
        if not self.journal_parser.eddn_cache_path:
            return
        self._queue_background_job(event)

    def _queue_background_job(self, job):
        """Queue a jump/location event to store, or a callable to run, on the one background worker"""
        if getattr(self, '_cache_jobs', None) is None:
            self._cache_jobs = queue.Queue()
            threading.Thread(target=self._run_cache_jobs, name="JournalCacheWrites", daemon=True).start()
        self._cache_jobs.put(job)

    def _run_cache_jobs(self):
        while True:
            job = self._cache_jobs.get()
            try:
                if callable(job):
                    job()
                else:
                    self._store_cache_event(job)
            except Exception:
                log.exception("Journal background job failed")

    def _store_cache_event(self, event):
        main_app = getattr(self, 'main_app_ref', None)
        try:
            pp_result = self.journal_parser._upsert_pp_from_event(event)
            if pp_result and main_app is not None and hasattr(main_app, 'sysfinder_tree'):
                main_app.after(0, main_app._fetch_sysfinder_pp_complete, pp_result['system_name'], pp_result, True)
        except Exception:
            log.exception("[PP] Journal cache write failed")
        try:
            info = self.journal_parser._upsert_system_info_from_event(event)
            if info and main_app is not None and hasattr(main_app, 'sysfinder_tree'):
                main_app.after(0, main_app._sysfinder_apply_system_info, info['system_name'], info)
        except Exception:
            log.exception("[SYSTEM_INFO] Journal cache write failed")

    def _deliver_journal_events(self, events):
        # Cargo handles the whole batch before listeners, so they see up-to-date cargo totals
        for event in events:
            try:
                self._process_journal_event_impl(event)
            except Exception:
                log.exception("Cargo monitor failed on journal event")
        for listener in list(self._journal_listeners):
            try:
                listener(events)
            except Exception:
                log.exception(f"Journal listener {getattr(listener, '__qualname__', listener)} failed")

    def process_journal_event(self, line: str):
        """Process a single journal event.

        Dispatches to the main thread when called from the background monitor
        thread — this method touches Tk widgets directly (cargo_text,
        capacity_label, etc.), and Tcl/Tk is not thread-safe: calling it from
        a non-main thread can hang or corrupt the interpreter.
        """
        main_app = getattr(self, 'main_app_ref', None)
        if main_app is not None and threading.current_thread() is not threading.main_thread():
            main_app.after(0, self._process_journal_event_impl, line)
            return
        self._process_journal_event_impl(line)

    def _update_ship_info(self, event):
        self.ship_id = event.get("ShipID")
        if event.get("event") == "LoadGame":
            self.commander_id = event.get("FID")
        self.ship_name = event.get("ShipName", "")
        self.ship_ident = event.get("ShipIdent", "")
        # Prefer Ship_Localised, use mapping for Ship field if needed
        if "Ship_Localised" in event:
            self.ship_type = event["Ship_Localised"]
        elif "Ship" in event:
            ship_id = event["Ship"].lower()
            self.ship_type = self.ship_type_map.get(ship_id, event["Ship"].replace("_", " ").title())

    def _process_scan_event(self, event):
        self.journal_parser.process_scan(event, fetch_reserves=False)
        system_name = event.get("StarSystem")
        main_app = getattr(self, 'main_app_ref', None)
        if (self.journal_parser.is_live_monitoring and system_name
                and not event.get("ReserveLevel")
                and any(ring.get("Name") and ring.get("RingClass")
                        and ring["Name"] not in self.journal_parser.system_reserve_levels
                        for ring in event.get("Rings", []))
                and main_app is not None):
            main_app.after(0, main_app._fetch_reserve_levels_for_system, system_name)

    def _process_journal_event_impl(self, line):
        try:
            event = line if isinstance(line, dict) else json.loads(line)
            event_type = event.get("event", "")
            market_handler = getattr(getattr(self, 'main_app_ref', None), 'market_handler', None)
            if market_handler is not None:
                market_handler.process_journal_event(event)
            self.journal_parser.process_carrier_event(event)
            
            # Track ship information from LoadGame and Loadout events
            if event_type in ["LoadGame", "Loadout"]:
                self._update_ship_info(event)
                
                # Notify main app to update ship info display
                if self.update_callback:
                    self.update_callback()
                
                # Notify ship info changed callback
                if self.ship_info_changed_callback:
                    self.ship_info_changed_callback()
            
            if event_type == "Loadout":
                # Get ship cargo capacity from loadout
                
                # First check for direct CargoCapacity in root of event
                if "CargoCapacity" in event:
                    old_capacity = self.max_cargo
                    self.max_cargo = event["CargoCapacity"]
                    
                    # Notify main app of capacity change
                    if old_capacity != self.max_cargo and self.capacity_changed_callback:
                        self.capacity_changed_callback(self.max_cargo)
                    return
                
                # Look for total cargo capacity in ship data
                ship_data = event.get("Ship", {})
                if ship_data:
                    # Some loadouts include direct cargo capacity
                    if "CargoCapacity" in ship_data:
                        old_capacity = self.max_cargo
                        self.max_cargo = ship_data["CargoCapacity"]
                        
                        # Notify main app of capacity change
                        if old_capacity != self.max_cargo and self.capacity_changed_callback:
                            self.capacity_changed_callback(self.max_cargo)
                        return
                
                # Fallback: calculate from modules
                modules = event.get("Modules", [])
                total_capacity = 0
                for module in modules:
                    item = module.get("Item", "").lower()
                    if "cargorack" in item:
                        capacity = self.extract_cargo_capacity(module)
                        if capacity > 0:
                            total_capacity += capacity
                
                if total_capacity > 0:
                    old_capacity = self.max_cargo
                    self.max_cargo = total_capacity
                    
                    # Notify main app of capacity change
                    if old_capacity != self.max_cargo and self.capacity_changed_callback:
                        self.capacity_changed_callback(self.max_cargo)

            elif event_type in ["ShipyardSwap", "StoredShips", "LoadGame", "ShipyardBuy", "ShipyardSell", 
                                "ShipyardTransfer", "SwitchToMainShip", "VehicleSwitch", "Commander", "Location"]:
                # Handle ship changes - aggressive capacity refresh
                
                # Multiple refresh attempts to ensure we get the right capacity
                refresh_success = False
                
                # 1. Try Status.json first (fastest)
                refresh_success = self.refresh_ship_capacity()
                
                # 2. If that fails, try scanning recent journal for Loadout events
                if not refresh_success:
                    self._force_loadout_scan()
                    refresh_success = self._validate_cargo_capacity()
                
                # 3. If still no valid capacity, clear data and force a fresh read
                if not refresh_success:
                    self.cargo_items.clear()
                    self.current_cargo = 0
                    self.max_cargo = 200  # Reset to default
                    
                
            elif event_type == "Cargo":
                # Handle cargo events - check if we have detailed inventory
                inventory = event.get("Inventory", [])
                count = event.get("Count", 0)
                
                if inventory:
                    # We have detailed inventory - use it!
                    # Track changes before clearing
                    new_cargo = {}
                    for item in inventory:
                        name = item.get("Name", "").replace("$", "").replace("_name;", "")
                        name_localized = item.get("Name_Localised", name)
                        # ALWAYS normalize to Title Case to prevent duplicates from capitalization variations
                        if name_localized:
                            item_name = name_localized.title()
                        else:
                            item_name = name.replace("_", " ").title()

                        # Normalize "Low Temp. Diamonds" variant to canonical form so cargo
                        # tracking doesn't split the same material into two dict keys
                        if item_name.lower() in ('low temp. diamonds', 'low temp diamonds'):
                            item_name = 'Low Temperature Diamonds'

                        item_count = item.get("Count", 0)
                        if item_name and item_count > 0:
                            new_cargo[item_name] = item_count
                            
                            # Track session minerals if quantity increased (skip limpets/drones)
                            # Only track if a mining session is active
                            if (self.session_start_snapshot and 
                                "limpet" not in item_name.lower() and 
                                "drone" not in item_name.lower()):
                                old_qty = self.cargo_items.get(item_name, 0)
                                if item_count > old_qty:
                                    added = item_count - old_qty
                                    self.session_minerals_mined[item_name] = self.session_minerals_mined.get(item_name, 0) + added
                                    print(f"[DEBUG] Cargo event tracked {added}t of {item_name}, session total: {self.session_minerals_mined[item_name]}t")
                    
                    # Update cargo items
                    self.cargo_items = new_cargo
                    self.current_cargo = sum(self.cargo_items.values())

                elif count > 0:
                    # We only have total count - update current cargo but keep existing items
                    if count != self.current_cargo:
                        self.current_cargo = count

            elif event_type == "MarketSell":
                # Handle selling items
                type_name = event.get("Type", "").replace("$", "").replace("_name;", "")
                type_localized = event.get("Type_Localised", type_name)
                item_name = type_localized if type_localized else type_name.replace("_", " ").title()
                count = event.get("Count", 0)
                
                if item_name in self.cargo_items:
                    new_qty = max(0, self.cargo_items[item_name] - count)
                    if new_qty > 0:
                        self.cargo_items[item_name] = new_qty
                    else:
                        del self.cargo_items[item_name]
                    
                    self.current_cargo = sum(self.cargo_items.values())

                    # Notify prospector panel for multi-session tracking
                    if self.update_callback:
                        self.update_callback(event_type="MarketSell", count=count)
                    
                    # Check if MINERAL cargo (non-limpets) is now empty and prompt for refinery materials
                    # Calculate cargo excluding limpets/drones
                    has_minerals = any(item for item in self.cargo_items.keys() 
                                      if "limpet" not in item.lower() and "drone" not in item.lower())
                    mineral_cargo = sum(qty for item, qty in self.cargo_items.items() 
                                       if "limpet" not in item.lower() and "drone" not in item.lower())
                    print(f"[DEBUG] MarketSell - total_cargo: {self.current_cargo}, mineral_cargo: {mineral_cargo}, has_minerals: {has_minerals}, cargo_items: {list(self.cargo_items.keys())}, session_start_snapshot: {self.session_start_snapshot is not None}")
                    
                    # Multi-session mode only: Prompt for refinery when cargo is emptied
                    # Single sessions handle refinery when the session ends via "End" button
                    if mineral_cargo == 0 and self.session_start_snapshot and not self.refinery_prompt_shown_for_this_transfer:
                        self._prompt_for_refinery_contents_multi_session()
            
            elif event_type == "CargoTransfer":
                # Handle cargo transfer (e.g., to Fleet Carrier)
                # CargoTransfer has a different structure: { "Transfers": [ { "Type": "...", "Count": N, "Direction": "..." } ] }
                transfers = event.get("Transfers", [])
                total_transferred = 0
                
                # Mark transfer time to prevent read_cargo_json from tracking immediately after
                self.last_transfer_time = time.time()
                print(f"[DEBUG] CargoTransfer detected - marking timestamp {self.last_transfer_time} to exclude tracking")
                
                # Store minerals before they're removed for refinery quick-add
                minerals_before_transfer = {item: qty for item, qty in self.cargo_items.items() 
                                           if "limpet" not in item.lower() and "drone" not in item.lower()}
                
                for transfer in transfers:
                    direction = transfer.get("Direction", "")
                    type_name = transfer.get("Type", "").replace("$", "").replace("_name;", "")
                    item_name = type_name.replace("_", " ").title()
                    count = transfer.get("Count", 0)
                    
                    if direction == "toship":
                        # Transfer FROM carrier TO ship - this is buying/retrieving, NOT mining
                        # Update cargo but DON'T add to session_minerals_mined
                        print(f"[DEBUG] CargoTransfer FROM carrier: '{item_name}' x{count}t (ignoring for mining stats)")
                        if item_name in self.cargo_items:
                            self.cargo_items[item_name] += count
                        else:
                            self.cargo_items[item_name] = count
                        # Don't add to mining stats, but continue processing to update display properly
                        
                    elif direction == "tocarrier":
                        # Transfer FROM ship TO carrier - count for multi-session tracking
                        print(f"[DEBUG] CargoTransfer TO carrier: '{item_name}' x{count}t (direction: {direction})")
                        
                        # Skip limpets/drones - they're not minerals
                        if "limpet" not in item_name.lower() and "drone" not in item_name.lower():
                            total_transferred += count
                            print(f"[DEBUG] CargoTransfer counted: {count}t of {item_name}")
                        else:
                            print(f"[DEBUG] CargoTransfer skipped limpet/drone: {count}t")
                        
                        if item_name in self.cargo_items:
                            new_qty = max(0, self.cargo_items[item_name] - count)
                            if new_qty > 0:
                                self.cargo_items[item_name] = new_qty
                            else:
                                del self.cargo_items[item_name]
                
                # Update cargo display after any transfer (toship or tocarrier)
                self.current_cargo = sum(self.cargo_items.values())
                
                # Notify main app to update mineral analysis table
                print(f"[DEBUG] CargoTransfer complete - notifying main app with cargo_items: {self.cargo_items}")
                if self.update_callback:
                    self.update_callback()
                
                # Only count minerals transferred TO carrier for multi-session tracking
                if total_transferred > 0:
                    
                    # DON'T notify prospector panel - transfers are not mining!
                    # Multi-session tracking should only count actual mining via read_cargo_json increases
                    # The live display counter should not show transfer tonnage as "mined"
                    
                    # Check if MINERAL cargo (non-limpets) is now empty and prompt for refinery materials
                    # Calculate cargo excluding limpets/drones
                    has_minerals = any(item for item in self.cargo_items.keys() 
                                      if "limpet" not in item.lower() and "drone" not in item.lower())
                    mineral_cargo = sum(qty for item, qty in self.cargo_items.items() 
                                       if "limpet" not in item.lower() and "drone" not in item.lower())
                    print(f"[DEBUG] CargoTransfer - total_cargo: {self.current_cargo}, mineral_cargo: {mineral_cargo}, has_minerals: {has_minerals}, cargo_items: {list(self.cargo_items.keys())}, session_start_snapshot: {self.session_start_snapshot is not None}")
                    
                    # Multi-session mode only: Prompt for refinery when cargo is emptied
                    # Single sessions handle refinery when the session ends via "End" button
                    if mineral_cargo == 0 and self.session_start_snapshot and not self.refinery_prompt_shown_for_this_transfer:
                        self._prompt_for_refinery_contents_multi_session()
                        
                elif transfers:  # Transfers occurred but all were limpets
                    print(f"[DEBUG] CargoTransfer: Only limpets transferred - not counting")
            
            elif event_type == "EjectCargo":
                # Handle cargo ejection (dumping/abandoning)
                type_name = event.get("Type", "").replace("$", "").replace("_name;", "")
                type_localized = event.get("Type_Localised", type_name)
                item_name = type_localized if type_localized else type_name.replace("_", " ").title()
                count = event.get("Count", 0)
                
                # Try to find the item in cargo (exact match or case-insensitive)
                found_key = None
                if item_name in self.cargo_items:
                    found_key = item_name
                else:
                    # Try case-insensitive match or partial match for drones/limpets
                    for key in self.cargo_items.keys():
                        if (key.lower() == item_name.lower() or 
                            ("drone" in type_name.lower() and "limpet" in key.lower()) or
                            ("limpet" in item_name.lower() and "limpet" in key.lower())):
                            found_key = key
                            break
                
                if found_key:
                    new_qty = max(0, self.cargo_items[found_key] - count)
                    if new_qty > 0:
                        self.cargo_items[found_key] = new_qty
                    else:
                        del self.cargo_items[found_key]
                    
                    self.current_cargo = sum(self.cargo_items.values())

                    # Subtract ejected cargo from multi-session tracking
                    # This ensures ejected materials don't count in session totals
                    if found_key in self.session_minerals_mined:
                        self.session_minerals_mined[found_key] = max(0, self.session_minerals_mined[found_key] - count)
                        if self.session_minerals_mined[found_key] == 0:
                            del self.session_minerals_mined[found_key]
                        print(f"[DEBUG] Ejected {count}t of {found_key}, session_minerals_mined updated: {self.session_minerals_mined.get(found_key, 0)}t remaining")
                    
                    # Notify prospector panel for multi-session tracking (counts as LOSS)
                    if self.update_callback:
                        self.update_callback(event_type="EjectCargo", count=count)
                        
            elif event_type in ["ModuleBuy", "ModuleSell", "ModuleSwap", "ModuleRetrieve", "ModuleStore"]:
                # Handle module changes that might affect cargo capacity
                slot = event.get("Slot", "").lower()
                item = event.get("Item", "").lower() if event.get("Item") else ""
                stored_item = event.get("StoredItem", "").lower() if event.get("StoredItem") else ""
                
                # Check if cargo rack modules are involved
                is_cargo_related = any(keyword in text for text in [slot, item, stored_item] 
                                     for keyword in ["cargorack", "cargo", "internal"])
                
                if is_cargo_related:
                    print(f"DEBUG: Cargo module change detected - Event: {event_type}, Slot: {slot}, Item: {item}")
                    
                    # Force immediate capacity refresh
                    refresh_success = self.refresh_ship_capacity()
                    
                    # If Status.json doesn't have updated capacity yet, try journal scan
                    if not refresh_success:
                        self._force_loadout_scan()

            elif event_type == "FSDJump":
                # Player jumped to a new system in their own ship - count as visit
                system_name = event.get("StarSystem", "")
                star_pos = event.get("StarPos", [])
                event_ts = event.get("timestamp", "")
                
                if system_name:
                    coords = None
                    if len(star_pos) >= 3:
                        coords = (star_pos[0], star_pos[1], star_pos[2])
                    
                    # Use centralized method to update displays AND record visit
                    # Pass event timestamp to prevent double-counting if catchup also processes this
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'update_current_system'):
                        self.main_app_ref.update_current_system(system_name, coords, count_visit=True, event_timestamp=event_ts)
                    else:
                        self.current_system = system_name
                    
                    print(f"[JUMP] FSDJump: Arrived at {system_name}")
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'eddn_sender'):
                        self.main_app_ref.eddn_sender.send_journal_event("FSDJump", event, background=True)
                    self._queue_cache_upserts(event)

            elif event_type == "CarrierJump":
                # Player is docked on Fleet Carrier that jumped - player arrived at new system
                # CarrierJump only fires when player is docked, so this is a real arrival - count as visit
                system_name = event.get("StarSystem", "")
                star_pos = event.get("StarPos", [])
                event_ts = event.get("timestamp", "")
                
                if system_name:
                    coords = None
                    if len(star_pos) >= 3:
                        coords = (star_pos[0], star_pos[1], star_pos[2])
                    
                    # Update current system and count as visit (player arrived at new system)
                    # CarrierJump only fires when player is docked, so it's a real arrival like FSDJump
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'update_current_system'):
                        self.main_app_ref.update_current_system(system_name, coords, count_visit=True, event_timestamp=event_ts)
                    else:
                        self.current_system = system_name
                    
                    print(f"[CARRIER] CarrierJump: Now at {system_name}")
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'eddn_sender'):
                        self.main_app_ref.eddn_sender.send_journal_event("CarrierJump", event, background=True)
                    self._queue_cache_upserts(event)
            
            elif event_type == "Location":
                # Game loaded - check if this is offline carrier jump or normal login
                # If Location shows different system than last visited, count as visit (offline carrier jump)
                system_name = event.get("StarSystem", "")
                star_pos = event.get("StarPos", [])
                event_ts = event.get("timestamp", "")
                
                if system_name:
                    coords = None
                    if len(star_pos) >= 3:
                        coords = (star_pos[0], star_pos[1], star_pos[2])
                    
                    # Check if this is an offline carrier jump by comparing with last visited system
                    count_visit = False
                    try:
                        if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'cargo_monitor'):
                            user_db = self.main_app_ref.cargo_monitor.user_db
                            if user_db:
                                last_visited = user_db.get_last_visited_system()
                                # If Location shows different system than last visited, it's an offline carrier jump
                                if last_visited and last_visited != system_name:
                                    count_visit = True
                                    print(f"[LOCATION] Offline carrier jump detected: {last_visited} -> {system_name}")
                    except Exception as e:
                        print(f"[LOCATION] Could not check for offline carrier jump: {e}")
                    
                    # Update system and count visit only if it's an offline carrier jump
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'update_current_system'):
                        self.main_app_ref.update_current_system(system_name, coords, count_visit=count_visit, event_timestamp=event_ts)
                    else:
                        self.current_system = system_name
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'eddn_sender'):
                        self.main_app_ref.eddn_sender.send_journal_event("Location", event, background=True)
                    self._queue_cache_upserts(event)

            elif event_type == "Scan":
                # Process Scan events through JournalParser to store ring info
                try:
                    self._process_scan_event(event)
                except Exception as scan_err:
                    log.warning(f"Warning: Failed to process Scan event: {scan_err}")
                        
            elif event_type == "SAASignalsFound":
                # Process ring scans through JournalParser for complete hotspot data with ring info
                try:
                    body_name = event.get("BodyName", "")
                    
                    # IMPORTANT: For rings, extract system name from body name (most reliable)
                    # Ring body names always start with system name: "Sol 1 A Ring" = system "Sol"
                    # current_system can be stale if FSDJump event was missed
                    scanned_system = None
                    
                    if body_name:
                        import re
                        # Match pattern for ring: ends with " X Ring" where X is letter(s)
                        # Examples: "Sol 1 A Ring", "Kovantani 3 A Ring", "Col 359 Sector JW-V d2-32 2 A Ring"
                        match = re.match(r'^(.+?)\s+(?:[A-Z]\s+)?\d+(?:\s+[A-Z])?\s+[A-Z]+\s+Ring$', body_name, re.IGNORECASE)
                        if match:
                            scanned_system = match.group(1).strip()
                            print(f"🔍 Extracted system name from ring body: {scanned_system}")
                    
                    # Fallback to current_system only if extraction failed
                    if not scanned_system:
                        scanned_system = self.current_system
                        print(f"🔍 Using current_system as fallback: {scanned_system}")
                    
                    # Also update current_system to keep it in sync
                    if scanned_system and scanned_system != self.current_system:
                        print(f"🔄 Updating current_system: {self.current_system} -> {scanned_system}")
                        self.current_system = scanned_system
                    
                    print(f"🔍 Processing SAASignalsFound: {body_name} in {scanned_system}")
                    
                    # Store context for hotspot callback to use
                    self._current_saa_system = scanned_system
                    self._current_saa_body = body_name
                    
                    self.journal_parser.process_saa_signals_found(event, scanned_system)
                    
                    # Show notification in status (if available)
                    
                    print(f"[OK] SAASignalsFound processed successfully")
                    
                except Exception as saa_err:
                    log.warning(f"Warning: Failed to process SAASignalsFound event: {saa_err}")
            
            elif event_type == "MaterialCollected":
                # Track engineering materials collected (Raw materials only)
                try:
                    category = event.get("Category", "")
                    # Use internal Name (always English) for lookup, but get localized name for display
                    material_name_internal = event.get("Name", "").strip()
                    material_name_display = event.get("Name_Localised", material_name_internal).strip()
                    count = event.get("Count", 1)
                    
                    logging.info(f"[MaterialCollected] Raw event data: Category={category}, Name={material_name_display}, Count={count}")
                    
                    if category == "Raw":
                        # Normalize internal material name to Title Case for matching against MATERIAL_GRADES
                        material_name = material_name_internal.title()
                        
                        logging.debug(f"[MaterialCollected] Checking material: '{material_name}' (after title())")
                        
                        # Only track materials in our predefined list
                        if material_name in self.MATERIAL_GRADES:
                            self.materials_collected[material_name] = self.materials_collected.get(material_name, 0) + count
                            # Track session cumulative total for multi-session mode
                            self.session_materials_collected[material_name] = self.session_materials_collected.get(material_name, 0) + count
                            # Store localized name for display
                            self.materials_localized_names[material_name] = material_name_display.title()
                            logging.info(f"[MaterialCollected] ✓ Added {count}x {material_name} (Display: {material_name_display}) (Total: {self.materials_collected[material_name]})")
                            logging.debug(f"[MaterialCollected] Current materials_collected: {self.materials_collected}")

                            # Notify main app to update integrated display
                            if self.update_callback:
                                self.update_callback()
                                logging.debug("[MaterialCollected] Called update_callback for integrated display")
                            else:
                                logging.warning("[MaterialCollected] WARNING: No update_callback registered!")
                        else:
                            logging.warning(f"[MaterialCollected] ✗ Material '{material_name}' not in tracked list. Available: {list(self.MATERIAL_GRADES.keys())[:5]}...")
                    else:
                        logging.debug(f"[MaterialCollected] ✗ Skipping non-Raw category: {category}")
                except Exception as mat_err:
                    logging.error(f"[MaterialCollected] Failed to process event: {mat_err}")
                    import traceback
                    logging.error(traceback.format_exc())

        except json.JSONDecodeError:
            pass  # Skip invalid JSON lines
        except Exception:
            log.exception("Journal event processing failed")
    
    def extract_cargo_capacity(self, module):
        """Extract cargo capacity from a module entry"""
        try:
            item = module.get("Item", "")
            
            # Method 1: Extract from cargo rack module names
            if "cargorack" in item.lower():
                # Extract size from names like:
                # - "int_cargorack_size6_class1"
                # - "Int_CargoRack_Size4_Class1"
                size_match = re.search(r'size(\d+)', item.lower())
                if size_match:
                    size = int(size_match.group(1))
                    # Standard cargo rack capacities
                    capacity_map = {
                        1: 2,    # Size 1 = 2 tons
                        2: 4,    # Size 2 = 4 tons  
                        3: 8,    # Size 3 = 8 tons
                        4: 16,   # Size 4 = 16 tons
                        5: 32,   # Size 5 = 32 tons
                        6: 64,   # Size 6 = 64 tons
                        7: 128,  # Size 7 = 128 tons
                        8: 256   # Size 8 = 256 tons
                    }
                    return capacity_map.get(size, 0)
            
            # Method 2: Check for engineering modifications
            engineering = module.get("Engineering", {})
            if engineering:
                modifiers = engineering.get("Modifiers", [])
                for mod in modifiers:
                    if mod.get("Label") == "CargoCapacity":
                        return int(mod.get("Value", 0))
            
            # Method 3: Check for direct capacity value (some modules have this)
            if "capacity" in module:
                return int(module.get("capacity", 0))
                        
            return 0
        except Exception as e:
            log.error(f"Error extracting cargo capacity: {e}")
            return 0
    
    def refresh_ship_capacity(self):
        """Force refresh ship cargo capacity from Status.json with validation"""
        try:
            if os.path.exists(self.status_json_path):
                with open(self.status_json_path, 'r') as f:
                    status_data = json.load(f)
                    
                # Check if we have cargo capacity info and validate it
                new_capacity = status_data.get("CargoCapacity")
                if new_capacity and new_capacity > 0:
                    # Sanity check: capacity should be between 2-2048 tons
                    if 2 <= new_capacity <= 2048:
                        old_capacity = self.max_cargo
                        self.max_cargo = new_capacity
                        
                        if old_capacity != self.max_cargo:
                            
                            # Notify main app of capacity change
                            if self.capacity_changed_callback:
                                self.capacity_changed_callback(self.max_cargo)
                            
                            # Force update cargo data after capacity change
                            self.read_cargo_json()
                            self._force_cargo_refresh()
                            
                            return True
                    else:
                        # Invalid capacity detected - try to recover from journal
                        self._recover_capacity_from_journal()
                        
        except Exception as e:
            # If Status.json fails, try to recover from journal
            self._recover_capacity_from_journal()
        return False
    
    def _recover_capacity_from_journal(self):
        """Recover capacity info from journal when Status.json fails"""
        try:
            if self.last_journal_file and os.path.exists(self.last_journal_file):
                self.scan_journal_for_cargo_capacity(self.last_journal_file)
            else:
                self.find_latest_journal()
        except Exception:
            log.exception("Capacity recovery from journal failed")
    
    def _force_loadout_scan(self):
        """Aggressively scan journal for recent Loadout events"""
        try:
            if self.last_journal_file and os.path.exists(self.last_journal_file):
                with open(self.last_journal_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Look through last 100 lines for any Loadout event
                for line in reversed(lines[-100:]):
                    try:
                        event = json.loads(line.strip())
                        if event.get("event") == "Loadout":
                            self.process_journal_event(line.strip())
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception:
            log.exception("Forced Loadout scan failed")

    def _force_cargo_refresh(self):
        """Force immediate cargo data refresh from all sources"""
        try:
            # Clear current data to force fresh read
            
            # Read from Cargo.json first (most accurate)
            self.read_cargo_json()
            
            # If no data from Cargo.json, try reading latest journal entries
            if not self.cargo_items and self.last_journal_file:
                self.read_new_journal_entries()

        except Exception:
            log.exception("Forced cargo refresh failed")
    
    def start_session_tracking(self):
        """Start tracking cargo changes for a mining session"""
        # Validate and refresh cargo capacity before starting session
        if not self._validate_cargo_capacity():
            # Attempt to get correct capacity
            self.refresh_ship_capacity()
        
        # Clear multi-session cumulative tracking for fresh session start
        self.session_minerals_mined.clear()
        self.session_materials_collected.clear()
            
        self.session_start_snapshot = {
            'timestamp': time.time(),
            'total_cargo': self.current_cargo,
            'cargo_items': self.cargo_items.copy(),
            'prospector_count': self._get_prospector_count(),
            'max_cargo': self.max_cargo,  # Store capacity at session start
            'initial_refinery_contents': self.refinery_contents.copy()  # Preserve existing refinery materials
        }
        
        # Clear refinery contents for new session AFTER preserving them
        self.refinery_contents = {}
        
        print(f"[SESSION] Started mining session - Cargo: {self.current_cargo}/{self.max_cargo}t, Prospectors: {self._get_prospector_count()}")
        
        return self.session_start_snapshot
    
    def _validate_cargo_capacity(self):
        """Validate current cargo capacity is reasonable"""
        if not (2 <= self.max_cargo <= 2048):
            return False
        return True

    def end_session_tracking(self):
        """End session tracking and return session data"""
        if not self.session_start_snapshot:
            return None
            
        end_snapshot = {
            'timestamp': time.time(),
            'total_cargo': self.current_cargo,
            'cargo_items': self.cargo_items.copy(),
            'prospector_count': self._get_prospector_count()
        }
        
        # Check if multi-session mode is active
        is_multi_session = False
        if (hasattr(self, 'prospector_panel') and 
            self.prospector_panel and 
            hasattr(self.prospector_panel, 'multi_session_var')):
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        # Calculate materials mined during session
        materials_mined = {}
        
        if is_multi_session:
            # Multi-session mode: Use cumulative session tracking
            # This includes materials that were mined and then transferred/sold
            materials_mined = self.session_minerals_mined.copy()
            print(f"[SESSION END] Multi-session mode: Using session_minerals_mined: {materials_mined}")
        else:
            # Normal mode: Compare current cargo to session start
            start_items = self.session_start_snapshot['cargo_items']
            end_items = end_snapshot['cargo_items']
            
            # Find materials that increased during the session
            for item_name, end_qty in end_items.items():
                # Skip limpets and non-materials
                if ("limpet" in item_name.lower() or 
                    "scrap" in item_name.lower() or 
                    "data" in item_name.lower()):
                    continue
                    
                start_qty = start_items.get(item_name, 0)
                if end_qty > start_qty:
                    materials_mined[item_name] = end_qty - start_qty
        
        # Add refinery contents that user manually added (not already in cargo)
        # Refinery materials are additional to cargo - they represent bins that weren't collected yet
        if hasattr(self, 'refinery_contents') and self.refinery_contents:
            for material_name, refinery_qty in self.refinery_contents.items():
                if material_name in materials_mined:
                    materials_mined[material_name] += refinery_qty
                else:
                    materials_mined[material_name] = refinery_qty
            print(f"[SESSION] Added refinery contents to report: {self.refinery_contents}")
        
        # Clear refinery contents after session to prevent reuse in next session
        if hasattr(self, 'refinery_contents'):
            self.refinery_contents = {}
        
        # Calculate prospector limpets used (start count - end count)
        prospectors_used = max(0, self.session_start_snapshot['prospector_count'] - end_snapshot['prospector_count'])
        
        # Build session type header suffix for reports
        session_type_suffix = "(Multi-Session)" if is_multi_session else "(Single Session)"
        
        session_data = {
            'start_snapshot': self.session_start_snapshot,
            'end_snapshot': end_snapshot,
            'materials_mined': materials_mined,
            'engineering_materials': self.materials_collected.copy(),  # Add engineering materials
            'prospectors_used': prospectors_used,
            'total_tons_mined': sum(materials_mined.values()),
            'session_duration': end_snapshot['timestamp'] - self.session_start_snapshot['timestamp'],
            'session_type': session_type_suffix  # Add session type for HTML reports
        }
        
        # Log session end
        duration_mins = session_data['session_duration'] / 60
        print(f"[SESSION] Ended mining session - Duration: {duration_mins:.1f}min, Mined: {session_data['total_tons_mined']:.1f}t, "
              f"Prospectors used: {prospectors_used}, Materials: {len(materials_mined)}")
        
        # Clear the session tracking
        self.session_start_snapshot = None
        
        # Clear multi-session cumulative tracking (data already saved to session_data)
        self.session_minerals_mined.clear()
        self.session_materials_collected.clear()
        
        # Reset engineering materials after session ends (data already saved to session_data)
        self.materials_collected.clear()
        
        # Update display to show materials cleared
        if self.update_callback:
            self.update_callback()
        
        return session_data

    def get_live_session_tons(self):
        """Get tons mined so far in current session"""
        if not self.session_start_snapshot:
            return 0.0
        
        # Check if multi-session mode is active via prospector panel
        is_multi_session = False
        if (hasattr(self, 'prospector_panel') and 
            self.prospector_panel and 
            hasattr(self.prospector_panel, 'multi_session_var')):
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        if is_multi_session:
            # Multi-session mode: Use cumulative session tracking
            # Sum all minerals from session_minerals_mined (already includes refinery)
            materials_mined = sum(self.session_minerals_mined.values())
        else:
            # Normal mode: Compare current cargo to session start (existing behavior)
            materials_mined = 0.0
            start_items = self.session_start_snapshot['cargo_items']
            current_items = self.cargo_items
            
            # Calculate materials that increased during the session
            for item_name, current_qty in current_items.items():
                # Skip limpets and non-materials
                if ("limpet" in item_name.lower() or 
                    "scrap" in item_name.lower() or 
                    "data" in item_name.lower()):
                    continue
                    
                start_qty = start_items.get(item_name, 0)
                if current_qty > start_qty:
                    materials_mined += current_qty - start_qty
            
            # Also check if any materials were present at start but increased
            for item_name, start_qty in start_items.items():
                if ("limpet" in item_name.lower() or 
                    "scrap" in item_name.lower() or 
                    "data" in item_name.lower()):
                    continue
                    
                current_qty = current_items.get(item_name, 0)
                if current_qty > start_qty:
                    # Already counted above, skip
                    continue
            
            # Add refinery contents only in normal mode
            if hasattr(self, 'refinery_contents') and self.refinery_contents:
                materials_mined += sum(self.refinery_contents.values())
        
        return round(materials_mined, 1)

    def get_live_session_materials(self):
        """Get per-material tons mined so far in current session
        
        Returns:
            dict: Material name -> tons mined (e.g., {'Platinum': 12.3, 'Painite': 8.5})
        """
        if not self.session_start_snapshot:
            return {}
        
        # Check if multi-session mode is active via prospector panel
        is_multi_session = False
        if (hasattr(self, 'prospector_panel') and 
            self.prospector_panel and 
            hasattr(self.prospector_panel, 'multi_session_var')):
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        materials_mined = {}
        
        if is_multi_session:
            # Multi-session mode: Use cumulative session tracking (already includes refinery)
            for material_name, total_mined in self.session_minerals_mined.items():
                materials_mined[material_name] = round(total_mined, 1)
        else:
            # Normal mode: Compare current cargo to session start (existing behavior)
            start_items = self.session_start_snapshot['cargo_items']
            current_items = self.cargo_items
            
            # Calculate materials that increased during the session
            for item_name, current_qty in current_items.items():
                # Skip limpets and non-materials
                if ("limpet" in item_name.lower() or 
                    "scrap" in item_name.lower() or 
                    "data" in item_name.lower()):
                    continue
                
                # Normalize material name to match KNOWN_MATERIALS (handles all languages)
                from journal_parser import JournalParser
                normalized_name = JournalParser.normalize_material_name(item_name)
                    
                start_qty = start_items.get(item_name, 0)
                if current_qty > start_qty:
                    materials_mined[normalized_name] = round(current_qty - start_qty, 1)
            
            # Add refinery contents only in normal mode
            if hasattr(self, 'refinery_contents') and self.refinery_contents:
                for material_name, refinery_qty in self.refinery_contents.items():
                    if material_name in materials_mined:
                        materials_mined[material_name] += refinery_qty
                    else:
                        materials_mined[material_name] = refinery_qty
                    materials_mined[material_name] = round(materials_mined[material_name], 1)
        
        return materials_mined

    def get_live_session_engineering_materials(self):
        """Get per-material engineering materials collected in current session
        
        Returns:
            dict: Material name -> pieces collected (e.g., {'Carbon': 150, 'Iron': 80})
        """
        # Check if multi-session mode is active via prospector panel
        is_multi_session = False
        if (hasattr(self, 'prospector_panel') and 
            self.prospector_panel and 
            hasattr(self.prospector_panel, 'multi_session_var')):
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        if is_multi_session:
            # Multi-session mode: Use cumulative session tracking
            return self.session_materials_collected.copy()
        else:
            # Normal mode: Use current materials_collected
            return self.materials_collected.copy()

    def _get_prospector_count(self):
        """Get current limpet count from cargo"""
        limpet_count = 0
        for item_name, qty in self.cargo_items.items():
            if "limpet" in item_name.lower():
                limpet_count += qty
        return limpet_count

    def adjust_limpet_count(self):
        """Show dialog to manually adjust limpet count and update Cargo.json
        
        This is useful when the game's Cargo.json gets out of sync during
        fast-paced mining (rapid limpet launches + material collection).
        
        Follows DIALOG_GUIDELINES.md for proper centering and theming.
        """
        try:
            from config import load_theme
            from app_utils import get_app_icon_path
            
            # Get current limpet count
            current_count = self._get_prospector_count()
            
            # Find the parent window - prefer main app if available
            if hasattr(self, 'main_app_ref') and self.main_app_ref:
                parent = self.main_app_ref
            else:
                parent = None
            
            # Theme colors (per DIALOG_GUIDELINES.md)
            theme = load_theme()
            if theme == "elite_orange":
                bg_color = "#000000"
                fg_color = "#ff8c00"
                btn_bg = "#1a1a1a"
                btn_fg = "#ff9900"
                entry_bg = "#1a1a1a"
            else:
                bg_color = "#1e1e1e"
                fg_color = "#569cd6"
                btn_bg = "#2a3a4a"
                btn_fg = "#e0e0e0"
                entry_bg = "#2a2a2a"
            
            # Create dialog
            dialog = tk.Toplevel(parent)
            dialog.withdraw()  # Hide immediately to prevent blinking on wrong monitor
            dialog.title(t('dialogs.adjust_limpets_title'))
            dialog.configure(bg=bg_color)
            dialog.resizable(False, False)
            dialog.minsize(300, 0)
            # dialog.transient(parent)  # Disabled - causes focus issues
            
            # Set app icon
            try:
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            # Main content frame
            frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=15)
            frame.pack(fill="both", expand=True)
            
            # Info label
            tk.Label(frame, 
                    text=t('dialogs.adjust_limpets_info').format(count=current_count),
                    bg=bg_color, fg=fg_color, 
                    font=("Segoe UI", 10)).pack(pady=(0, 10))
            
            # Instruction label
            tk.Label(frame, 
                    text=t('dialogs.adjust_limpets_prompt'),
                    bg=bg_color, fg=fg_color, 
                    font=("Segoe UI", 10)).pack(pady=(0, 5))
            
            # Entry for new count
            entry_frame = tk.Frame(frame, bg=bg_color)
            entry_frame.pack(pady=5)
            
            count_var = tk.StringVar(value=str(current_count))
            entry = tk.Entry(entry_frame, textvariable=count_var, 
                           width=8, font=("Segoe UI", 12),
                           bg=entry_bg, fg=fg_color,
                           insertbackground=fg_color,
                           justify="center")
            entry.pack()
            entry.select_range(0, tk.END)
            entry.focus_set()
            
            # Result variable
            result = {"value": None}
            
            def on_ok():
                try:
                    value = int(count_var.get())
                    if 0 <= value <= 999:
                        result["value"] = value
                        dialog.destroy()
                    else:
                        entry.configure(bg="#4a2020")  # Red tint for error
                except ValueError:
                    entry.configure(bg="#4a2020")
            
            def on_cancel():
                dialog.destroy()
            
            # Button frame
            btn_frame = tk.Frame(frame, bg=bg_color)
            btn_frame.pack(pady=(15, 0))
            
            tk.Button(btn_frame, text=t('dialogs.ok'), command=on_ok,
                     bg=btn_bg, fg=btn_fg, padx=20, pady=3,
                     font=("Segoe UI", 10)).pack(side="left", padx=5)
            
            tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel,
                     bg=btn_bg, fg=btn_fg, padx=20, pady=3,
                     font=("Segoe UI", 10)).pack(side="left", padx=5)
            
            # Bind Enter key
            entry.bind('<Return>', lambda e: on_ok())
            dialog.bind('<Escape>', lambda e: on_cancel())
            
            # Center dialog on parent (per DIALOG_GUIDELINES.md)
            dialog.update_idletasks()
            if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, '_center_dialog_on_parent'):
                self.main_app_ref._center_dialog_on_parent(dialog)
            else:
                # Fallback centering
                dialog.geometry(f"+{parent.winfo_x() + 100}+{parent.winfo_y() + 100}" if parent else "")

            # Show dialog AFTER centering to prevent blinking on wrong monitor
            dialog.deiconify()

            # Force dialog to stay on top and have focus
            dialog.attributes('-topmost', True)
            dialog.lift()
            dialog.focus_force()

            try:
                dialog.grab_set()
            except:
                pass
            
            # Keep dialog on top while open
            def keep_on_top():
                try:
                    if dialog.winfo_exists():
                        dialog.lift()
                        dialog.after(100, keep_on_top)
                except:
                    pass
            dialog.after(100, keep_on_top)
            
            # Wait for dialog to close
            dialog.wait_window()
            
            # Process result
            if result["value"] is not None and result["value"] != current_count:
                success = self._update_limpet_count_in_cargo_json(result["value"])
                if success:
                    print(f"[LIMPET] Adjusted limpet count from {current_count} to {result['value']}")
                    # Force re-read of Cargo.json
                    self.last_cargo_mtime = 0
                    self.read_cargo_json()
                    # Also update integrated display if available
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, '_update_integrated_cargo_display'):
                        self.main_app_ref._update_integrated_cargo_display()
                else:
                    log.error(f"[LIMPET] Failed to update Cargo.json")
                    
        except Exception as e:
            log.error(f"[LIMPET] Error adjusting limpet count: {e}")
            import traceback
            traceback.print_exc()

    def _update_limpet_count_in_cargo_json(self, new_count: int) -> bool:
        """Update the limpet count in Cargo.json file
        
        Args:
            new_count: The new limpet count to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(self.cargo_json_path):
                print(f"[LIMPET] Cargo.json not found at: {self.cargo_json_path}")
                return False
            
            # Read current Cargo.json
            with open(self.cargo_json_path, 'r', encoding='utf-8') as f:
                cargo_data = json.load(f)
            
            inventory = cargo_data.get("Inventory", [])
            limpet_found = False
            old_count = 0
            
            # Find and update limpet entry
            for item in inventory:
                name = item.get("Name", "").lower()
                if "drone" in name or "limpet" in name:
                    old_count = item.get("Count", 0)
                    item["Count"] = new_count
                    limpet_found = True
                    break
            
            # If no limpet entry exists and new_count > 0, add one
            if not limpet_found and new_count > 0:
                inventory.append({
                    "Name": "drones",
                    "Name_Localised": "Limpet",
                    "Count": new_count,
                    "Stolen": 0
                })
                old_count = 0
            
            # If limpet exists but new_count is 0, remove the entry
            if limpet_found and new_count == 0:
                inventory = [item for item in inventory 
                            if "drone" not in item.get("Name", "").lower() 
                            and "limpet" not in item.get("Name", "").lower()]
            
            # Update total count
            cargo_data["Inventory"] = inventory
            cargo_data["Count"] = sum(item.get("Count", 0) for item in inventory)
            
            # Write back to Cargo.json
            with open(self.cargo_json_path, 'w', encoding='utf-8') as f:
                json.dump(cargo_data, f, indent=2)
            
            # Update internal cargo items
            limpet_key = None
            for item_name in list(self.cargo_items.keys()):
                if "limpet" in item_name.lower():
                    limpet_key = item_name
                    break
            
            if limpet_key:
                if new_count > 0:
                    self.cargo_items[limpet_key] = new_count
                else:
                    del self.cargo_items[limpet_key]
            elif new_count > 0:
                self.cargo_items["Limpet"] = new_count
            
            # Update current cargo total
            self.current_cargo = sum(self.cargo_items.values())
            
            print(f"[LIMPET] Updated Cargo.json: {old_count} -> {new_count} limpets")
            return True
            
        except Exception as e:
            log.error(f"[LIMPET] Error updating Cargo.json: {e}")
            import traceback
            traceback.print_exc()
            return False

    def show_refinery_dialog(self):
        """Show the refinery adjustment dialog and store the results"""
        try:
            dialog = RefineryDialog(
                parent=getattr(self, 'main_app_ref', None),
                cargo_monitor=self,
                current_cargo_items=self.cargo_items.copy()
            )
            result = dialog.show()
            
            if result:  # User added refinery contents
                self.refinery_contents = result.copy()
                total_refinery = sum(result.values())
                print(f"Refinery contents applied: {len(result)} materials, {total_refinery} tons total")
                
                # Add refinery materials to actual cargo items for live display
                for material_name, refinery_qty in result.items():
                    if material_name in self.cargo_items:
                        self.cargo_items[material_name] += refinery_qty
                    else:
                        self.cargo_items[material_name] = refinery_qty
                
                # Update current cargo total
                self.current_cargo = sum(self.cargo_items.values())

                # Notify main app of changes
                if self.update_callback:
                    self.update_callback()
                
                # Auto-update CSV if we have a prospector panel reference and manual materials were added
                print(f"DEBUG: About to call _update_csv_after_refinery_addition with materials: {result}")
                self._update_csv_after_refinery_addition(result)
            else:
                print("Refinery dialog cancelled")
                
        except Exception as e:
            log.error(f"Error showing refinery dialog: {e}")
            import traceback
            traceback.print_exc()

    def _update_csv_after_refinery_addition(self, refinery_materials: dict):
        """Update the most recent session file and CSV row after manual materials are added"""
        try:
            import re
            # import os removed (already imported globally)
            
            # Check if we have access to the prospector panel (try multiple paths)
            prospector_panel = None
            print(f"DEBUG REFINERY: hasattr prospector_panel = {hasattr(self, 'prospector_panel')}")
            print(f"DEBUG REFINERY: hasattr main_app_ref = {hasattr(self, 'main_app_ref')}")
            if hasattr(self, 'prospector_panel') and self.prospector_panel:
                prospector_panel = self.prospector_panel
                print("DEBUG REFINERY: Using self.prospector_panel")
            elif hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'prospector_panel'):
                prospector_panel = self.main_app_ref.prospector_panel
                print("DEBUG REFINERY: Using main_app_ref.prospector_panel")
            
            if not prospector_panel:
                print("No prospector panel reference - cannot auto-update CSV")
                return
                
            reports_dir = prospector_panel.reports_dir
            print(f"DEBUG REFINERY: reports_dir = {reports_dir}")
            
            if not os.path.exists(reports_dir):
                print("Reports directory not found - cannot auto-update CSV")
                return
                
            # Find the most recent session text file
            session_files = [f for f in os.listdir(reports_dir) 
                           if f.startswith("Session_") and f.endswith(".txt")]
            
            if not session_files:
                print("No session files found - cannot auto-update CSV")
                return
                
            # Sort by modification time to get the most recent
            session_files.sort(key=lambda f: os.path.getmtime(os.path.join(reports_dir, f)), reverse=True)
            most_recent_file = session_files[0]
            session_path = os.path.join(reports_dir, most_recent_file)
            
            print(f"Updating most recent session file: {most_recent_file}")
            
            # Read the current session file content
            with open(session_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Use only the new refinery materials (don't accumulate from existing section)
            updated_materials = {}
            total_added = 0.0
            
            # Add new refinery materials directly (replacing any existing section, not accumulating)
            for material_name, quantity in refinery_materials.items():
                updated_materials[material_name] = quantity
                total_added += quantity
            
            # Update session header with new total (only add if no existing REFINED CARGO TRACKING)
            cargo_section_match = re.search(r'=== REFINED CARGO TRACKING ===(.*?)(?:===|\Z)', content, re.DOTALL)
            header_match = re.search(r'^(Session: .* — .* — .* — Total )(\d+(?:\.\d+)?)t', content, re.MULTILINE)
            if header_match and not cargo_section_match:
                # Only update header if this is the first time adding refinery
                old_total = float(header_match.group(2))
                new_total = old_total + total_added
                new_header = f"{header_match.group(1)}{new_total:.0f}t"
                content = content.replace(header_match.group(0), new_header)
            
            # Update or add REFINED CARGO TRACKING section
            cargo_breakdown_text = "\n=== REFINED CARGO TRACKING ===\n"
            
            cargo_breakdown_text += f"Refined Materials: {len(updated_materials)} types\n\n"
            
            # Sort materials by quantity (highest first)
            sorted_materials = sorted(updated_materials.items(), key=lambda x: x[1], reverse=True)
            for material_name, quantity in sorted_materials:
                cargo_breakdown_text += f"{material_name}: {quantity:.1f}t\n"
            
            cargo_breakdown_text += f"\nTotal Refined: {sum(updated_materials.values()):.1f}t"
            
            # Replace or add the cargo breakdown section
            if cargo_section_match:
                # Replace existing section
                old_section = cargo_section_match.group(0)
                content = content.replace(old_section, cargo_breakdown_text)
            else:
                # Add new section before any session comment
                comment_match = re.search(r'\n=== SESSION COMMENT ===', content)
                if comment_match:
                    content = content.replace(comment_match.group(0), cargo_breakdown_text + comment_match.group(0))
                else:
                    content += cargo_breakdown_text
            
            # Write updated content back to file
            with open(session_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Extract timestamp from filename for CSV update
            import re
            timestamp_match = re.search(r'Session_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', most_recent_file)
            if timestamp_match:
                date_part = timestamp_match.group(1)
                time_part = timestamp_match.group(2).replace('-', ':')
                timestamp_local = f"{date_part}T{time_part}"
                
                # Calculate updated CSV data
                materials_breakdown = ', '.join([f"{mat}: {qty:.1f}t" for mat, qty in sorted_materials])
                material_count = len(updated_materials)
                new_total_tons = sum(updated_materials.values())
                
                # Update CSV row
                updated_csv_data = {
                    'total_tons': new_total_tons,
                    'materials_tracked': str(material_count) if material_count > 0 else '',
                    'materials_breakdown': materials_breakdown
                }
                
                if prospector_panel._update_existing_csv_row(timestamp_local, updated_csv_data):
                    print(f"Successfully updated CSV and session file with {len(refinery_materials)} manual materials")
                    
                    # Refresh reports displays if they exist
                    try:
                        prospector_panel._refresh_reports_tab()
                    except Exception as e:
                        log.error(f"Error refreshing reports displays: {e}")
                else:
                    log.error("Failed to update CSV row")
            else:
                print("Could not extract timestamp from session filename")
                
        except Exception as e:
            log.error(f"Error updating CSV after refinery addition: {e}")
            import traceback
            traceback.print_exc()
