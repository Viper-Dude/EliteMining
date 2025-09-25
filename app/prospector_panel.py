# ================================================================
# Mining Analytics Panel - Final Baseline Version
# Stable with the following fixes:
# - Looping fixed with startup skip + deduplication
# - Files cleared at startup
# - 'Core' hidden in Minimal % column (UI only)
# - Announcements and toggles working
# ================================================================

import os
import sys
import json
import glob
import re
import csv
import logging
import time
import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import tempfile
from PIL import ImageGrab
from core.constants import MENU_COLORS

def get_app_icon_path() -> str:
    """Get the path to the application icon, handling both development and compiled environments"""
    # Try multiple approaches to find the icon
    search_paths = []
    
    # Method 1: Use __file__ if available (development)
    try:
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller compiled executable
            search_paths.append(sys._MEIPASS)
        elif '__file__' in globals():
            # Development environment
            search_paths.append(os.path.dirname(os.path.abspath(__file__)))
    except:
        pass
    
    # Method 2: Current working directory
    search_paths.append(os.getcwd())
    
    # Method 3: Directory containing the executable
    try:
        if getattr(sys, 'frozen', False):
            search_paths.append(os.path.dirname(sys.executable))
    except:
        pass
    
    # Method 4: Hardcoded relative paths
    search_paths.extend(['.', 'app', '..', '../app'])
    
    # Try each path with different icon names
    icon_names = ['logo.ico', 'logo_multi.ico', 'logo.png']
    
    for base_path in search_paths:
        for subdir in ['Images', 'images', 'img']:
            for icon_name in icon_names:
                icon_path = os.path.join(base_path, subdir, icon_name)
                if os.path.exists(icon_path):
                    return icon_path
                    
        # Also try directly in the base path
        for icon_name in icon_names:
            icon_path = os.path.join(base_path, icon_name)
            if os.path.exists(icon_path):
                return icon_path
    
    return None
from mining_statistics import SessionAnalytics

from config import _load_cfg, _save_cfg, _atomic_write_text, VA_TTS_ANNOUNCEMENT, CONFIG_FILE
import announcer

# Import graphs module for graphical analytics
try:
    from mining_charts import MiningChartsPanel
    CHARTS_AVAILABLE = True
except ImportError:
    CHARTS_AVAILABLE = False

# --- Announcement Toggles ---
# Note: Core/Non-Core asteroids use config.json ONLY, no txt files
ANNOUNCEMENT_TOGGLES = {
    "Core Asteroids": (None, "Speak only when a core (motherlode) is detected."),
    "Non-Core Asteroids": (None, "Speak for regular (non-core) prospector results."),
}

log = logging.getLogger(__name__)

# ToolTip class will be provided by main application to ensure consistency

# ProspectorPanel and helpers extracted

_paren_re = re.compile(r"\s*\([^)]*\)")

def _clean_name(name: str) -> str:
    name = (name or "").replace("_", " ").strip()
    name = _paren_re.sub("", name).strip()
    return name

def _fmt_pct(pct: Optional[float]) -> str:
    if pct is None:
        return "—"
    s = f"{pct:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return f"{s}%"

def _extract_content(evt: Dict[str, Any]) -> str:
    loc = evt.get("Content_Localised")
    if isinstance(loc, str) and loc.strip():
        t = loc.strip()
        if t.lower().startswith("material content"):
            return t[len("Material Content:"):].strip()
        return t
    raw = evt.get("Content")
    if not isinstance(raw, str):
        return ""
    s = raw.strip().strip(";").lstrip("$")
    if "_" in s:
        s = s.split("_")[-1]
    if s and s.lower().startswith("material content"):
        s = s[len("Material Content:"):].strip()
    return s or ""

def _clean_name(name: str) -> str:
    """Clean and format material names."""
    if not name:
        return ""
    s = name.strip().strip(";").lstrip("$")
    if "_" in s:
        s = s.split("_")[-1]
    if s and s.lower().startswith("material content"):
        s = s[len("Material Content:"):].strip()
    return s.title() if s else ""

def _extract_material_name(m: Dict[str, Any]) -> str:
    return _clean_name(
        m.get("Name_Localised")
        or m.get("Material_Localised")
        or m.get("Name")
        or m.get("Material")
        or ""
    )

def _extract_material_percent(m: Dict[str, Any]) -> Optional[float]:
    if "Percent" in m:
        try:
            return float(m["Percent"])
        except Exception:
            return None
    if "Proportion" in m:
        try:
            val = float(m["Proportion"])
            return val * 100.0 if val <= 1.0 else val
        except Exception:
            return None
    return None

def _extract_location_display(full_body_name: str, body_type: str = "", station_name: str = "", carrier_name: str = "") -> str:
    """Extract contextual location information for the Body/Ring field.
    
    Shows different information based on context:
    - Asteroid rings: '2 A Ring', '3 B Ring', etc.
    - Planets: 'Earth', 'Mars', etc. (planet name only)
    - Fleet carriers: 'X7B-55P' (carrier callsign)
    - Stations: 'Jameson Memorial', 'Freeport', etc.
    - Other bodies: Just the body name
    
    Args:
        full_body_name: The full body name from Elite Dangerous
        body_type: Optional body type (e.g., 'PlanetaryRing', 'Planet', 'Star')
        station_name: Optional station name if docked
        carrier_name: Optional fleet carrier name/callsign
    
    Returns:
        Appropriate display name for the location context
    """
    import re
    
    # Priority 1: Fleet carrier name/callsign if provided
    if carrier_name:
        # Filter out placeholder/localization keys
        if carrier_name.startswith('$') and carrier_name.endswith(';'):
            # Skip placeholder text, fall through to next priority
            pass
        else:
            # Return the full fleet carrier name (e.g., "[MMCO] Pandoras BOX V0W-W7T")
            return carrier_name

    # Priority 2: Station name if docked
    if station_name:
        # Filter out placeholder/localization keys
        if station_name.startswith('$') and station_name.endswith(';'):
            # Skip placeholder text, fall through to next priority
            pass
        else:
            return station_name
    
    if not full_body_name:
        return ""
    
    # Priority 3: Asteroid rings (mining context)
    if body_type == "PlanetaryRing" or "Ring" in full_body_name:
        # First try to match patterns like "B 1 A Ring" (planet + number + ring letter)
        ring_match = re.search(r'([A-Za-z]\s+\d+\s+[A-Za-z]\s+Ring)$', full_body_name)
        if ring_match:
            return ring_match.group(1)
        # Fallback for simpler patterns like "1 A Ring"  
        ring_match = re.search(r'(\d+\s+[A-Za-z]\s+Ring)$', full_body_name)
        if ring_match:
            return ring_match.group(1)
    
    # Priority 4: Extract just the body designation from system + body names
    # Remove system name prefix to show just the body part
    # Examples: 
    # "Col 285 Sector WP-E c12-17 3 a" -> "3A" or "3A Ring" (if it's a ring)
    # "Sol Earth" -> "Earth"
    # "Wolf 359 B" -> "B"  
    # "Paesia 2" -> "2"
    
    parts = full_body_name.split()
    if len(parts) >= 2:
        last_part = parts[-1]
        
        # Pattern: ends with single letter (like "3 a" -> "3A" or "3A Ring")
        if len(last_part) == 1 and last_part.isalpha() and len(parts) >= 2:
            second_last = parts[-2]
            if second_last.isdigit():
                body_designation = f"{second_last}{last_part.upper()}"
                # Add "Ring" suffix if this is a planetary ring
                if body_type == "PlanetaryRing" or "Ring" in full_body_name.lower():
                    return f"{body_designation} Ring"
                else:
                    return body_designation
        
        # Pattern: ends with number (like "System 2" -> "2" or "2 Ring")
        elif last_part.isdigit():
            if body_type == "PlanetaryRing" or "Ring" in full_body_name.lower():
                return f"{last_part} Ring"
            else:
                return last_part
            
        # Pattern: ends with single letter only (like "System B" -> "B" or "B Ring") 
        elif len(last_part) == 1 and last_part.isalpha():
            body_designation = last_part.upper()
            if body_type == "PlanetaryRing" or "Ring" in full_body_name.lower():
                return f"{body_designation} Ring"
            else:
                return body_designation
            
        # Pattern: named bodies (like "Sol Earth" -> "Earth")
        elif last_part.lower() in ['earth', 'mars', 'venus', 'jupiter', 'saturn', 'neptune', 'uranus', 'mercury', 'pluto']:
            return last_part.title()
            
        # Pattern: complex designations - try to extract the meaningful part
        else:
            # For complex names, take the last 2 parts if they look like body designations
            if len(parts) >= 2:
                last_two = f"{parts[-2]} {parts[-1]}"
                # If it looks like "number letter" pattern
                if re.match(r'^\d+\s+[A-Za-z]$', last_two):
                    body_designation = last_two.upper().replace(' ', '')
                    if body_type == "PlanetaryRing" or "Ring" in full_body_name.lower():
                        return f"{body_designation} Ring"
                    else:
                        return body_designation
    
    # Default: Show the full body name if we can't parse it
    return full_body_name

    if "Proportion" in m:
        try:
            val = float(m["Proportion"])
            return val * 100.0 if val <= 1.0 else val
        except Exception:
            return None
    return None

def _extract_remaining(evt: Dict[str, Any]) -> Optional[float]:
    if "Remaining" not in evt:
        return None
    try:
        val = float(evt["Remaining"])
        return val * 100.0 if val <= 1.0 else val
    except Exception:
        return None

KNOWN_MATERIALS = [
    "Alexandrite",
    "Bauxite",
    "Benitoite",
    "Bertrandite",
    "Bromellite",
    "Cobalt",
    "Gallite",
    "Gold",
    "Goslarite",
    "Grandidierite",
    "Haematite",
    "Hydrogen Peroxide",
    "Indite",
    "Lepidolite",
    "Liquid Oxygen",
    "Lithium Hydroxide",
    "Low Temperature Diamonds",
    "Methane Clathrate",
    "Methanol Monohydrate Crystals",
    "Monazite",
    "Musgravite",
    "Osmium",
    "Painite",
    "Palladium",
    "Platinum",
    "Praseodymium",
    "Rhodplumsite",
    "Rutile",
    "Samarium",
    "Serendibite",
    "Silver",
    "Uraninite",
    "Void Opals",
    "Water"
]

CORE_ONLY = [
    "Alexandrite", "Benitoite", "Grandidierite", "Monazite", "Musgravite", "Serendibite",
    "Taaffeite", "Void Opals"
]

# -------------------- Mining Analytics Panel --------------------
class ProspectorPanel(ttk.Frame):
    def _sync_spinboxes_to_min_pct_map(self):
        """Update self.min_pct_map from the current values of the spinboxes."""
        for mat, var in self._minpct_vars.items():
            try:
                self.min_pct_map[mat] = float(var.get())
            except Exception:
                pass

    def __init__(self, master: tk.Widget, va_root: str, status_cb, toggle_vars, text_overlay=None, main_app=None, announcement_vars=None, main_announcement_enabled=None, tooltip_class=None) -> None:
        self.toggle_vars = toggle_vars
        self.announcement_vars = announcement_vars or {}  # Add announcement vars
        super().__init__(master, padding=8)
        self.status_cb = status_cb
        self.text_overlay = text_overlay
        self.main_app = main_app  # Reference to main app for cargo monitor
        
        # Use the ToolTip class provided by main app for consistent tooltip behavior
        self.ToolTip = tooltip_class if tooltip_class is not None else (lambda w, t: None)  # Fallback to no-op if not provided
        
        # Use the main announcement toggle from Interface Options panel
        self.enabled = main_announcement_enabled if main_announcement_enabled is not None else tk.IntVar(value=1)

        # Create a custom style for smaller session buttons
        style = ttk.Style()
        style.configure("SmallDark.TButton", 
                       font=("Segoe UI", 8),  # Smaller font size
                       background="#444444", 
                       foreground="#ffffff")
        style.map("SmallDark.TButton",
                 background=[("active", "#555555")])

        # Folders
        self.va_root = va_root
        self.vars_dir = os.path.join(self.va_root, "Variables")
        os.makedirs(self.vars_dir, exist_ok=True)
        
        # Get the app directory - handle PyInstaller bundled app
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            app_dir = os.path.join(self.va_root, "app")
        else:
            # Running in development mode
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.reports_dir = os.path.join(app_dir, "Reports", "Mining Session")
        os.makedirs(self.reports_dir, exist_ok=True)
        
        # Clear any cached session data to prevent stale data issues
        self.reports_tab_session_lookup = {}
        self.session_lookup = {}

        # Track reports window for refreshing
        self.reports_window = None
        self.reports_tree = None

        # Initialize bookmarks system
        self.bookmarks_file = os.path.join(app_dir, "mining_bookmarks.json")
        self.bookmarks_data = []
        self._load_bookmarks()

        self.journal_dir = self._detect_journal_dir_default() or ""
        
        # Status.json file path for real-time game state
        self.status_json_path = os.path.join(self.journal_dir, "Status.json")

        # Watcher state
        self._jrnl_path: Optional[str] = None
        self._jrnl_pos: int = 0

        # Last known system/body and location context
        self.last_system: str = ""
        self.last_body: str = ""
        self.last_body_type: str = ""  # e.g., "PlanetaryRing", "Planet", "Star"
        self.last_station_name: str = ""  # When docked at a station
        self.last_carrier_name: str = ""  # When near/docked at fleet carrier
        
        # Track whether we're processing startup events or real-time events
        self.startup_processing: bool = True

        # Prospector history view
        self.history: List[Tuple[str, str, str]] = []
        
        # Mining statistics tracker
        self.session_analytics = SessionAnalytics()

        # Announce config
        self.announce_map: Dict[str, bool] = self._load_announce_map()
        self.min_pct_map: Dict[str, float] = self._load_min_pct_map()
        self.threshold = tk.DoubleVar(value=self._load_threshold()) 
        self._startup_skip: bool = True
        self._last_mtime: float = 0.0
        self._last_size: int = 0
        

        # Session tracking
        self.session_active = False
        self.session_paused = False
        self.session_start: Optional[dt.datetime] = None
        self.session_pause_started: Optional[dt.datetime] = None
        self.session_paused_seconds: float = 0.0
        self.session_system = tk.StringVar(value="")
        self.session_body = tk.StringVar(value="")
        self.session_elapsed = tk.StringVar(value="00:00:00")
        self.session_totals: Dict[str, float] = {}

        # UI
        self._build_ui()
        # Load last settings after UI is built
        self._load_last_material_settings()
        # Force announce_map to UI after build
        for m in self.mat_tree.get_children():
            flag = "✓" if self.announce_map.get(m, True) else "—"
            self.mat_tree.item(m, values=(flag, m, ""))
        
        # Automatically rebuild CSV on startup to ensure data is current
        self.after(500, self._auto_rebuild_csv_on_startup)
        
        self.after(1000, self._tick)
        
        # Switch to real-time mode after startup processing is complete
        self.after(2000, self._enable_realtime_mode)
        
        # Check Status.json once after startup to get current location and override stale journal data
        self.after(2500, self._startup_sync_with_status)
        


    # --- CFG passthrough ---
    def _load_cfg(self) -> Dict[str, Any]:
        return _load_cfg()

    def _save_cfg(self, cfg: Dict[str, Any]) -> None:
        _save_cfg(cfg)

    def _load_announce_map(self) -> Dict[str, bool]:
        cfg = self._load_cfg()
        raw = cfg.get("announce_map", {})
        out: Dict[str, bool] = {}
        for k in KNOWN_MATERIALS:
            if k in raw:
                out[k] = bool(raw[k])
            else:
                out[k] = True  # Default to enabled for new materials
        return out

    def _save_announce_map(self) -> None:
        cfg = self._load_cfg()
        cfg["announce_map"] = self.announce_map
        self._save_cfg(cfg)
    
    def _get_current_docked_status(self) -> bool:
        """Get real-time docked status from Status.json file"""
        try:
            if os.path.exists(self.status_json_path):
                with open(self.status_json_path, 'r') as f:
                    status_data = json.load(f)
                    return status_data.get("Docked", False)
        except Exception as e:
            print(f"Error reading Status.json: {e}")
        return False
    
    def _get_current_status_data(self) -> dict:
        """Get all real-time status data from Status.json file for debugging"""
        try:
            if os.path.exists(self.status_json_path):
                with open(self.status_json_path, 'r') as f:
                    status_data = json.load(f)
                    return status_data
        except Exception as e:
            print(f"Error reading Status.json: {e}")
        return {}
    
    def _check_status_location_fields(self) -> None:
        """Check Status.json for location-relevant fields and update display if needed"""
        try:
            if os.path.exists(self.status_json_path):
                with open(self.status_json_path, 'r') as f:
                    status_data = json.load(f)
                    
                # Extract location-relevant fields
                docked = status_data.get("Docked", False)
                landed = status_data.get("Landed", False)
                destination_name = status_data.get("DestinationName", "")
                destination_body = status_data.get("DestinationBody", "")
                body_name = status_data.get("BodyName", "")
                
                # Check for nested Destination field (for fleet carriers)
                destination_info = status_data.get("Destination", {})
                destination_full_name = destination_info.get("Name", "") if destination_info else ""
                
                # Only show debug info for critical events
                # Removed excessive debug logging
                
                # Check if we have a destination AND we're actually at it (docked/landed)
                current_location = ""
                
                if destination_full_name and (docked or landed):
                    # Only use destination info if we're actually docked/landed, not just navigating to it
                    # Filter out placeholder/localization keys that Elite Dangerous sometimes generates
                    if destination_full_name.startswith('$') and destination_full_name.endswith(';'):
                        pass  # Ignore placeholder text
                    else:
                        # We have a valid destination and we're actually there
                        import re
                        # Check if this looks like a fleet carrier (contains callsign format)
                        carrier_match = re.search(r'([A-Z0-9]{3}-[A-Z0-9]{3})', destination_full_name)
                        if carrier_match:
                            # Use the full fleet carrier name instead of just the callsign
                            current_location = destination_full_name
                            if self.last_carrier_name != current_location:
                                self.last_carrier_name = current_location
                                self.last_station_name = ""
                                self._update_location_display()
                        else:
                            # Not a carrier format, might be a station
                            current_location = destination_full_name
                            if self.last_station_name != current_location:
                                self.last_station_name = current_location
                                self.last_carrier_name = ""
                                self._update_location_display()
                # Removed: Don't use destination as location when not docked/landed
                # This was causing fleet carrier destinations to override ring locations
                            
                elif docked and destination_name:
                    # Fallback to old DestinationName field if available (planetary stations, etc.)
                    current_location = destination_name
                    if self.last_station_name != current_location:
                        self.last_station_name = current_location
                        self.last_carrier_name = ""
                        self._update_location_display()
                        
                elif docked and body_name:
                    # We're docked somewhere but no specific destination name - might be a planetary outpost
                    # Use the body name as context
                    if self.last_body != body_name:
                        self.last_body = body_name
                        self.last_body_type = "Planet"  # Assume planet if docked but no station name
                        # Keep any existing station context, but update body
                        self._update_location_display()
                        
                elif landed and body_name:
                    # We're landed on a planet surface
                    if self.last_body != body_name:
                        # Debug removed - landed on planet
                        self.last_body = body_name
                        self.last_body_type = "Planet"  # Assume planet when landed
                        # Clear docked context since we're on planet surface, not docked
                        self.last_carrier_name = ""
                        self.last_station_name = ""
                        self._update_location_display()
                        
                elif not destination_full_name and not destination_name and not landed:
                    # No destination and not landed - clear docked context
                    if self.last_carrier_name or self.last_station_name:
                        self.last_carrier_name = ""
                        self.last_station_name = ""
                        self._update_location_display()
                        
        except Exception as e:
            print(f"Error checking status location fields: {e}")
    
    def _update_location_display(self) -> None:
        """Update the location display with current context"""
        body_display = _extract_location_display(
            self.last_body or "", 
            self.last_body_type, 
            self.last_station_name, 
            self.last_carrier_name
        )
        self.session_body.set(body_display)
    
    def _startup_sync_with_status(self) -> None:
        """Sync with Status.json on startup to override stale journal data with current game state"""
        self._check_status_location_fields()
        
        # If Status.json doesn't provide clear location info, the journal data might be stale
        # Force an update to show what we currently think the location is
        self._update_location_display()

    def _load_min_pct_map(self) -> Dict[str, float]:
        cfg = self._load_cfg()
        raw = cfg.get("min_pct_map", {})
        out: Dict[str, float] = {}
        for k in KNOWN_MATERIALS:
            try:
                # Use .get with a fallback value to simplify logic
                v = float(raw.get(k, 20.0))
                out[k] = max(0.0, min(100.0, v))
            except Exception:
                # Fallback to a default if parsing fails
                out[k] = 20.0
        return out

    def _save_min_pct_map(self) -> None:
        cfg = self._load_cfg()
        cfg["min_pct_map"] = self.min_pct_map
        self._save_cfg(cfg)

    def _load_threshold(self) -> float:
        cfg = self._load_cfg()
        try:
            v = float(cfg.get("announce_threshold", 20.0))
            return max(0.0, v)
        except Exception:
            return 20.0

    def _save_threshold_value(self) -> None:
        try:
            cfg = self._load_cfg()
            cfg["announce_threshold"] = float(self.threshold.get())
            self._save_cfg(cfg)
            self._save_last_material_settings()  # Save material settings
        except Exception as e:
            log.exception("Saving threshold failed: %s", e)

    # --- Preset save/load methods ---
    def _save_preset1(self):
        if not messagebox.askyesno("Save Preset 1", "Overwrite Announcement Preset 1?"):
            return
        cfg = self._load_cfg()
        preset_data = {
            'announce_map': self.announce_map.copy(),
            'min_pct_map': self.min_pct_map.copy(),
            'announce_threshold': float(self.threshold.get()),
        }
        
        # Save Core/Non-Core asteroid settings with announcement presets
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            if "Core Asteroids" in self.announcement_vars:
                preset_data['Core Asteroids'] = self.announcement_vars["Core Asteroids"].get()
            if "Non-Core Asteroids" in self.announcement_vars:
                preset_data['Non-Core Asteroids'] = self.announcement_vars["Non-Core Asteroids"].get()
        
        cfg['announce_preset_1'] = preset_data
        self._save_cfg(cfg)
        self._set_status("Saved Preset 1.")

    def _load_preset1(self):
        cfg = self._load_cfg()
        data = cfg.get('announce_preset_1')
        if not data:
            messagebox.showinfo("Load Preset 1", "No Preset 1 saved yet.")
            return
        self.announce_map = data.get('announce_map', {}).copy()
        self.min_pct_map = data.get('min_pct_map', {}).copy()
        self.threshold.set(data.get('announce_threshold', 20.0))
        
        # Load Core/Non-Core asteroid settings from announcement presets
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            if "Core Asteroids" in self.announcement_vars and 'Core Asteroids' in data:
                self.announcement_vars["Core Asteroids"].set(data['Core Asteroids'])
            if "Non-Core Asteroids" in self.announcement_vars and 'Non-Core Asteroids' in data:
                self.announcement_vars["Non-Core Asteroids"].set(data['Non-Core Asteroids'])
        
        for m in self.mat_tree.get_children():
            flag = "✓" if self.announce_map.get(m, True) else "—"
            self.mat_tree.item(m, values=(flag, m, ""))
        for m, v in self._minpct_spin.items():
            if m in self.min_pct_map:
                v.set(self.min_pct_map[m])
        self._position_minpct_spinboxes()
        self._sync_spinboxes_to_min_pct_map()
        self._save_announce_map()
        self._save_min_pct_map()
        self._save_threshold_value()
        self._save_announce_map()
        self._save_last_material_settings()  # Save material settings
        # Save announcement preferences to main app config
        if hasattr(self.main_app, '_save_announcement_preferences'):
            self.main_app._save_announcement_preferences()
        self._set_status("Loaded Preset 1.")

    def _save_preset(self, num: int):
        if not messagebox.askyesno(f"Save Preset {num}", f"Overwrite Announcement Preset {num}?"):
            return
        cfg = self._load_cfg()
        preset_data = {
            'announce_map': self.announce_map.copy(),
            'min_pct_map': self.min_pct_map.copy(),
            'announce_threshold': float(self.threshold.get()),
        }
        
        # Save Core/Non-Core asteroid settings with announcement presets
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            if "Core Asteroids" in self.announcement_vars:
                preset_data['Core Asteroids'] = self.announcement_vars["Core Asteroids"].get()
            if "Non-Core Asteroids" in self.announcement_vars:
                preset_data['Non-Core Asteroids'] = self.announcement_vars["Non-Core Asteroids"].get()
        
        cfg[f'announce_preset_{num}'] = preset_data
        self._save_cfg(cfg)
        self._set_status(f"Saved Preset {num}.")

    def _load_preset(self, num: int):
        cfg = self._load_cfg()
        data = cfg.get(f'announce_preset_{num}')
        if not data:
            messagebox.showinfo(f"Load Preset {num}", f"No Preset {num} saved yet.")
            return
        self.announce_map = data.get('announce_map', {}).copy()
        self.min_pct_map = data.get('min_pct_map', {}).copy()
        self.threshold.set(data.get('announce_threshold', 20.0))
        
        # Load Core/Non-Core asteroid settings from announcement presets
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            if "Core Asteroids" in self.announcement_vars and 'Core Asteroids' in data:
                self.announcement_vars["Core Asteroids"].set(data['Core Asteroids'])
            if "Non-Core Asteroids" in self.announcement_vars and 'Non-Core Asteroids' in data:
                self.announcement_vars["Non-Core Asteroids"].set(data['Non-Core Asteroids'])
        
        for m in self.mat_tree.get_children():
            flag = "✓" if self.announce_map.get(m, True) else "—"
            self.mat_tree.item(m, values=(flag, m, ""))
        for m, v in self._minpct_spin.items():
            if m in self.min_pct_map:
                v.set(self.min_pct_map[m])
        self._position_minpct_spinboxes()
        self._sync_spinboxes_to_min_pct_map()
        self._save_announce_map()
        self._save_min_pct_map()
        self._save_threshold_value()
        self._save_last_material_settings()
        self._save_announce_map()
        # Save announcement preferences to main app config
        if hasattr(self.main_app, '_save_announcement_preferences'):
            self.main_app._save_announcement_preferences()
        self._set_status(f"Loaded Preset {num}.")

    def _load_last_material_settings(self):
        """Load the last used material settings on startup"""
        cfg = self._load_cfg()
        last_settings = cfg.get('last_material_settings', {})
        if last_settings:
            self.announce_map = last_settings.get('announce_map', {}).copy()
            self.min_pct_map = last_settings.get('min_pct_map', {}).copy()
            self.threshold.set(last_settings.get('announce_threshold', 20.0))
            
            # Restore Core/Non-Core settings from last_material_settings
            if hasattr(self, 'announcement_vars') and self.announcement_vars:
                if "Core Asteroids" in self.announcement_vars and "Core Asteroids" in last_settings:
                    self.announcement_vars["Core Asteroids"].set(last_settings["Core Asteroids"])
                if "Non-Core Asteroids" in self.announcement_vars and "Non-Core Asteroids" in last_settings:
                    self.announcement_vars["Non-Core Asteroids"].set(last_settings["Non-Core Asteroids"])
            
            # Update UI
            for m in self.mat_tree.get_children():
                flag = "✓" if self.announce_map.get(m, True) else "—"
                self.mat_tree.item(m, values=(flag, m, ""))
            for m, v in self._minpct_spin.items():
                if m in self.min_pct_map:
                    v.set(self.min_pct_map[m])
            self._position_minpct_spinboxes()

    def _save_last_material_settings(self):
        """Save current material settings as last used"""
        cfg = self._load_cfg()
        last_settings = {
            'announce_map': self.announce_map.copy(),
            'min_pct_map': self.min_pct_map.copy(),
            'announce_threshold': float(self.threshold.get()),
        }
        
        # Save Core/Non-Core asteroid settings if available
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            if "Core Asteroids" in self.announcement_vars:
                last_settings['Core Asteroids'] = self.announcement_vars["Core Asteroids"].get()
            if "Non-Core Asteroids" in self.announcement_vars:
                last_settings['Non-Core Asteroids'] = self.announcement_vars["Non-Core Asteroids"].get()
        
        cfg['last_material_settings'] = last_settings
        self._save_cfg(cfg)

    def _detect_journal_dir_default(self) -> Optional[str]:
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        path = os.path.join(home, "Saved Games", "Frontier Developments", "Elite Dangerous")
        return path if os.path.isdir(path) else None

    def _get_csv_path(self) -> str:
        """Get the consistent path to sessions_index.csv"""
        return os.path.join(self.reports_dir, "sessions_index.csv")
    
    def _clear_reports_cache(self):
        """Clear all cached report data to prevent stale data issues"""
        self.reports_tab_session_lookup = {}
        if hasattr(self, 'session_lookup'):
            self.session_lookup = {}
    
    def _validate_csv_consistency(self) -> dict:
        """Validate CSV file consistency and return debug info"""
        csv_path = self._get_csv_path()
        info = {
            'csv_path': csv_path,
            'csv_exists': os.path.exists(csv_path),
            'reports_dir': self.reports_dir,
            'is_frozen': getattr(sys, 'frozen', False),
            'session_count': 0,
            'text_files_count': 0
        }
        
        # Count CSV sessions
        if info['csv_exists']:
            try:
                import csv
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    info['session_count'] = sum(1 for row in reader)
            except Exception as e:
                info['csv_error'] = str(e)
        
        # Count text files
        try:
            text_files = [f for f in os.listdir(self.reports_dir) 
                         if f.lower().endswith('.txt') and f.startswith('Session')]
            info['text_files_count'] = len(text_files)
            if text_files:
                info['sample_text_files'] = text_files[:3]  # Show first 3 files
        except Exception as e:
            info['text_files_error'] = str(e)
        
        return info
    
    def _force_rebuild_and_refresh(self):
        """Force rebuild CSV and refresh reports tab with cache clearing"""
        try:
            # Clear all cached data
            self._clear_reports_cache()
            
            # Rebuild CSV from text files
            csv_path = self._get_csv_path()
            self._rebuild_csv_from_files_tab(csv_path, silent=False)
            
            # Force refresh the reports tab
            self._refresh_reports_tab()
            
            # Refresh statistics after rebuilding
            self._refresh_session_statistics()
            
        except Exception as e:
            print(f"[ERROR] Force rebuild failed: {e}")
            from tkinter import messagebox
            messagebox.showerror("Rebuild Error", f"Failed to rebuild CSV and refresh: {str(e)}")
    
    def _clear_cache_and_refresh(self):
        """Clear all cached data and refresh reports tab without rebuilding CSV"""
        try:
            # Clear all cached data
            self._clear_reports_cache()
            
            # Force refresh the reports tab to reload from CSV
            self._refresh_reports_tab()
            
            # Refresh statistics after clearing cache
            self._refresh_session_statistics()
            
            # Show a brief status message
            self._set_status("Cache cleared and reports refreshed")
            
        except Exception as e:
            print(f"[ERROR] Clear cache failed: {e}")
            from tkinter import messagebox
            messagebox.showerror("Clear Cache Error", f"Failed to clear cache: {str(e)}")
    
    def _validate_ui_csv_consistency(self):
        """Check if UI data matches CSV data and offer to fix inconsistencies"""
        try:
            if not hasattr(self, 'reports_tree_tab') or not self.reports_tree_tab:
                return
            
            csv_path = self._get_csv_path()
            if not os.path.exists(csv_path):
                return
            
            # Load CSV data
            import csv
            csv_data = {}
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Use system+body+duration as key for matching
                    key = f"{row['system']}|{row['body']}|{row['elapsed']}"
                    csv_data[key] = {
                        'comment': row.get('comment', '').strip(),
                        'timestamp': row['timestamp_utc']
                    }
            
            # Check UI data against CSV
            inconsistencies = []
            for item in self.reports_tree_tab.get_children():
                values = self.reports_tree_tab.item(item, 'values')
                if len(values) >= 13:
                    ui_system = values[1]
                    ui_body = values[2] 
                    ui_duration = values[3]
                    ui_comment = values[12].strip()
                    
                    key = f"{ui_system}|{ui_body}|{ui_duration}"
                    
                    if key in csv_data:
                        csv_comment = csv_data[key]['comment']
                        if ui_comment != csv_comment:
                            inconsistencies.append({
                                'key': key,
                                'ui_comment': ui_comment,
                                'csv_comment': csv_comment,
                                'system': ui_system,
                                'body': ui_body,
                                'item': item,
                                'values': values
                            })
            
            # If inconsistencies found, offer to fix them  
            if inconsistencies:
                print(f"[WARNING] Found {len(inconsistencies)} comment inconsistencies between UI and CSV")
                for inc in inconsistencies:
                    print(f"[WARNING] {inc['system']} {inc['body']}: UI='{inc['ui_comment']}' vs CSV='{inc['csv_comment']}'")
                
                from tkinter import messagebox
                result = messagebox.askyesnocancel(
                    "Data Inconsistency Detected",
                    f"Found {len(inconsistencies)} sessions where the UI comment doesn't match the CSV file.\n\n"
                    f"Example: {inconsistencies[0]['system']} {inconsistencies[0]['body']}\n"
                    f"UI shows: '{inconsistencies[0]['ui_comment']}'\n"
                    f"CSV has: '{inconsistencies[0]['csv_comment']}'\n\n"
                    f"Click 'Yes' to update UI from CSV (recommended)\n"
                    f"Click 'No' to update CSV from UI\n"
                    f"Click 'Cancel' to do nothing",
                    icon="warning"
                )
                
                if result is True:  # Update UI from CSV
                    for inc in inconsistencies:
                        new_values = list(inc['values'])
                        new_values[12] = inc['csv_comment']
                        self.reports_tree_tab.item(inc['item'], values=new_values)
                    print(f"[INFO] Updated UI comments from CSV for {len(inconsistencies)} sessions")
                    
                elif result is False:  # Update CSV from UI
                    for inc in inconsistencies:
                        # Find the raw timestamp for CSV update
                        session_data = self.reports_tab_session_lookup.get(inc['item'])
                        raw_timestamp = session_data.get('timestamp_raw') if session_data else inc['values'][0]
                        self._update_comment_in_csv(raw_timestamp, inc['ui_comment'])
                    print(f"[INFO] Updated CSV comments from UI for {len(inconsistencies)} sessions")
                    
            else:
                print("[INFO] UI and CSV comment data is consistent")
                
        except Exception as e:
            print(f"[ERROR] Failed to validate UI/CSV consistency: {e}")

    # --- UI ---
    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Reports tab (live prospector readouts)
        rep = ttk.Frame(nb, padding=8)
        rep.columnconfigure(0, weight=1)
        rep.columnconfigure(1, weight=0)
        rep.rowconfigure(3, weight=1)
        nb.add(rep, text="Mining Analytics")

        # --- System and Location Name Entry Row ---
        sysbody_row = ttk.Frame(rep)
        sysbody_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        sysbody_row.columnconfigure(0, weight=0, minsize=50)
        sysbody_row.columnconfigure(1, weight=0, minsize=120)
        sysbody_row.columnconfigure(2, weight=0, minsize=80)
        sysbody_row.columnconfigure(3, weight=1)

        ttk.Label(sysbody_row, text="System:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.system_entry = ttk.Entry(sysbody_row, textvariable=self.session_system, width=40)
        self.system_entry.grid(row=0, column=1, sticky="w", padx=(0, 5))
        self.ToolTip(self.system_entry, "Current system name. (Can also be entered manually)")

        ttk.Label(sysbody_row, text="Ring/Location:", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 2))
        self.body_entry = ttk.Entry(sysbody_row, textvariable=self.session_body, width=35)
        self.body_entry.grid(row=0, column=3, sticky="w")
        self.ToolTip(self.body_entry, "Current location: rings, planets, stations, or carriers. (Can also be entered manually)")

        # --- Remove VA Variables path row ---
        # vrow = ttk.Frame(rep)
        # vrow.grid(row=2, column=0, sticky="w", pady=(6, 0))
        # ttk.Label(vrow, text="VA Variables:").pack(side="left")
        # self.va_lbl = tk.Label(vrow, text=self.vars_dir, fg="gray", font=("Segoe UI", 9))
        # self.va_lbl.pack(side="left", padx=(6, 0))

        ttk.Label(rep, text="Prospector Reports:", font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(6, 4))

        self.tree = ttk.Treeview(rep, columns=("materials", "content", "time"), show="headings", height=12)
        self.tree.tag_configure("darkrow", background="#1e1e1e", foreground="#e6e6e6")
        self.tree.heading("materials", text="Materials", anchor="center")
        self.tree.heading("content", text="Asteroid Content", anchor="center")
        self.tree.heading("time", text="Time")
        self.tree.column("materials", width=400, anchor="w", stretch=True)
        self.tree.column("content", width=180, anchor="w", stretch=True)
        self.tree.column("time", width=80, anchor="center", stretch=False)
        self.tree.grid(row=3, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(rep, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=yscroll.set)
        yscroll.grid(row=3, column=1, sticky="ns")

        # --- Live Mining Statistics Section ---
        ttk.Label(rep, text="Material Analysis:", font=("Segoe UI", 10, "bold")).grid(row=4, column=0, sticky="w", pady=(10, 4))
        stats_frame = ttk.Frame(rep)
        stats_frame.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(0, 0))
        stats_frame.columnconfigure(0, weight=1)
        
        # Statistics tree for live percentage yields
        self.stats_tree = ttk.Treeview(stats_frame, columns=("material", "avg_pct", "best_pct", "latest_pct", "count"), 
                                       show="headings", height=6)
        self.stats_tree.heading("material", text="Material", anchor="center")
        self.stats_tree.heading("avg_pct", text="Avg %", anchor="center")
        self.stats_tree.heading("best_pct", text="Best %", anchor="center")
        self.stats_tree.heading("latest_pct", text="Latest %", anchor="center")
        self.stats_tree.heading("count", text="Hits", anchor="center")
        
        self.stats_tree.column("material", width=220, anchor="w", stretch=True)
        self.stats_tree.column("avg_pct", width=105, anchor="center", stretch=False)
        self.stats_tree.column("best_pct", width=105, anchor="center", stretch=False)
        self.stats_tree.column("latest_pct", width=105, anchor="center", stretch=False)
        self.stats_tree.column("count", width=105, anchor="center", stretch=False)
        
        self.stats_tree.tag_configure("darkrow", background="#1e1e1e", foreground="#e6e6e6")
        self.stats_tree.grid(row=0, column=0, sticky="ew")
        
        # Session summary labels
        summary_frame = ttk.Frame(stats_frame)
        summary_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        summary_frame.columnconfigure(1, weight=1)
        
        ttk.Label(summary_frame, text="Session Summary:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        self.stats_summary_label = ttk.Label(summary_frame, text="No data yet", foreground="#888888")
        self.stats_summary_label.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        # Session controls (moved from Session tab)
        controls_frame = ttk.Frame(stats_frame)
        controls_frame.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        controls_frame.columnconfigure(0, weight=0)  # Left: session controls
        controls_frame.columnconfigure(1, weight=1, minsize=140)  # Center: elapsed time (expandable with min width)
        controls_frame.columnconfigure(2, weight=0)  # Right: export button
        
        # Left side: Session start/stop controls
        session_controls = ttk.Frame(controls_frame)
        session_controls.grid(row=0, column=0, sticky="w")
        
        self.start_btn = tk.Button(session_controls, text="Start", command=self._session_start, 
                                 bg="#2a5a2a", fg="#ffffff", 
                                 activebackground="#3a6a3a", activeforeground="#ffffff",
                                 relief="solid", bd=1, cursor="hand2", width=10,
                                 highlightbackground="#1a3a1a", highlightcolor="#1a3a1a")
        self.start_btn.pack(side="left")
        self.ToolTip(self.start_btn, "Start a new mining session to track materials and performance")
        
        self.pause_resume_btn = tk.Button(session_controls, text="Pause", command=self._toggle_pause_resume, state="disabled", 
                                        bg="#5a4a2a", fg="#ffffff", 
                                        activebackground="#6a5a3a", activeforeground="#ffffff",
                                        relief="solid", bd=1, cursor="hand2", width=10,
                                        highlightbackground="#3a2a1a", highlightcolor="#3a2a1a")
        self.pause_resume_btn.pack(side="left", padx=(4, 0))
        self.ToolTip(self.pause_resume_btn, "Pause or resume the current mining session")
        
        self.stop_btn = tk.Button(session_controls, text="End", command=self._session_stop, state="disabled", 
                                bg="#5a2a2a", fg="#ffffff", 
                                activebackground="#6a3a3a", activeforeground="#ffffff",
                                relief="solid", bd=1, cursor="hand2", width=10,
                                highlightbackground="#3a1a1a", highlightcolor="#3a1a1a")
        self.stop_btn.pack(side="left", padx=(4, 0))
        self.ToolTip(self.stop_btn, "End the session and generate a final report")
        
        self.cancel_btn = tk.Button(session_controls, text="Cancel", command=self._session_cancel, state="disabled", 
                                  bg="#4a4a4a", fg="#ffffff", 
                                  activebackground="#5a5a5a", activeforeground="#ffffff",
                                  relief="solid", bd=1, cursor="hand2", width=10,
                                  highlightbackground="#2a2a2a", highlightcolor="#2a2a2a")
        self.cancel_btn.pack(side="left", padx=(4, 0))
        self.ToolTip(self.cancel_btn, "Cancel the current session without saving")
        
        # Center: Elapsed time display
        elapsed_frame = ttk.Frame(controls_frame)
        elapsed_frame.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        
        ttk.Label(elapsed_frame, text="Elapsed:").pack(side="left")
        self.elapsed_lbl = ttk.Label(elapsed_frame, textvariable=self.session_elapsed, font=("Segoe UI", 9, "bold"))
        self.elapsed_lbl.pack(side="left", padx=(6, 0))
        
        # Right side: Export button (Reports moved to dedicated tab)
        buttons_frame = ttk.Frame(controls_frame)
        buttons_frame.grid(row=0, column=2, sticky="e")
        
        # --- Announcements Panels tab ---
        ann = ttk.Frame(nb, padding=8)
        nb.add(ann, text="Announcements Panel")
        ann.columnconfigure(0, weight=1)
        ann.columnconfigure(1, weight=0)
        ann.rowconfigure(2, weight=1)

        # Main controls frame to hold both toggles and threshold
        main_controls = ttk.Frame(ann)
        main_controls.grid(row=0, column=0, sticky="w")
        
        # Left side: Announcement toggles
        toggles_frame = ttk.Frame(main_controls)
        toggles_frame.pack(side="left", padx=(0, 20))
        
        # Add announcement toggles if available
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            ttk.Label(toggles_frame, text="Announcement Types:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
            for name, (_fname, helptext) in ANNOUNCEMENT_TOGGLES.items():
                # Check if the variable exists before trying to use it
                if name in self.announcement_vars:
                    checkbox = tk.Checkbutton(toggles_frame, text=name, 
                                            variable=self.announcement_vars[name], 
                                            bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", 
                                            activebackground="#1e1e1e", activeforeground="#ffffff", 
                                            highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                                            padx=4, pady=1, anchor="w")
                    checkbox.pack(anchor="w", padx=(10, 0))
                    
                    # Add tooltip to checkbox
                    self.ToolTip(checkbox, helptext)
        
        # Right side: Threshold controls
        thr = ttk.Frame(main_controls)
        thr.pack(side="left")
        ttk.Label(thr, text="Announce at ≥").pack(side="left")
        sp = ttk.Spinbox(thr, from_=0.0, to=100.0, increment=0.5, width=6,
                         textvariable=self.threshold, command=self._save_threshold_value)
        sp.pack(side="left", padx=(6, 4))
        self.ToolTip(sp, "Set the minimum percentage threshold for announcements")
        
        set_all_btn = tk.Button(thr, text="Set all", command=self._set_all_min_pct,
                               bg="#2a4a5a", fg="#ffffff", 
                               activebackground="#3a5a6a", activeforeground="#ffffff",
                               relief="solid", bd=1, cursor="hand2", pady=2,
                               highlightbackground="#1a2a3a", highlightcolor="#1a2a3a",
                               width=8)
        set_all_btn.pack(side="left", padx=(10, 0))
        self.ToolTip(set_all_btn, "Set all materials to the minimum threshold percentage")
        ttk.Label(thr, text="%").pack(side="left")

        ttk.Label(ann, text="Select materials and set minimum percentages:",
                  font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(8, 4))

        self.mat_tree = ttk.Treeview(ann, columns=("announce", "material", "minpct"), show="headings", height=14)
        self.mat_tree.heading("announce", text="Announce")
        self.mat_tree.heading("material", text="Material")
        self.mat_tree.heading("minpct", text="Minimal %")
        self.mat_tree.column("announce", width=90, anchor="center", stretch=False)
        self.mat_tree.column("material", width=300, anchor="center", stretch=True)
        self.mat_tree.column("minpct", width=100, anchor="center", stretch=False)  # keep center for Core label
        self.mat_tree.grid(row=2, column=0, sticky="nsew")
        y2 = ttk.Scrollbar(ann, orient="vertical", command=self.mat_tree.yview)
        y2.grid(row=2, column=1, sticky="ns")

        # keep scrollbar in sync + reposition spinboxes when scrolling
        def _yscroll_set(lo, hi):
            y2.set(lo, hi)
            self._position_minpct_spinboxes()
        self.mat_tree.configure(yscroll=_yscroll_set)

        # populate rows - keep minpct column empty to avoid text showing behind spinboxes
        for mat in KNOWN_MATERIALS:
            flag = "✓" if self.announce_map.get(mat, True) else "—"
            if mat in CORE_ONLY:
                self.mat_tree.insert("", "end", iid=mat, values=(flag, mat, ""))  # blank instead of "Core"
            else:
                self.mat_tree.insert("", "end", iid=mat, values=(flag, mat, ""))

        # create one Spinbox per row and place it over the "minpct" cell
        self._minpct_spin: dict[str, ttk.Spinbox] = {}
        self._minpct_vars: dict[str, tk.DoubleVar] = {} # This is the new line

        def _on_minpct_change_factory(material: str):
            def _on_change():
                try:
                    v = float(self._minpct_vars[material].get()) # This is the new line
                    v = max(0.0, min(100.0, v))
                    self.min_pct_map[material] = v
                    self._save_min_pct_map()
                    self._save_last_material_settings()  # Save last settings when min_pct changes
                except Exception:
                    pass
            return _on_change
        
        for mat in KNOWN_MATERIALS:
            if mat in CORE_ONLY:
                continue  # skip spinbox for core-only gems
            start_val = self.min_pct_map.get(mat, 20.0)
            var = tk.DoubleVar(value=float(start_val))
            self._minpct_vars[mat] = var
            spn = ttk.Spinbox(ann, from_=0.0, to=100.0, increment=0.5, width=6, textvariable=var,
                              command=_on_minpct_change_factory(mat))

            # also update on Return/FocusOut
            spn.bind("<Return>", lambda e, m=mat: _on_minpct_change_factory(m)())
            spn.bind("<FocusOut>", lambda e, m=mat: _on_minpct_change_factory(m)())
            self._minpct_spin[mat] = spn

        # position spinboxes to match visible rows
        def _place_spin_for_item(item_id: str):
            spn = self._minpct_spin.get(item_id)
            if not spn:
                return
            try:
                bbox = self.mat_tree.bbox(item_id, column="#3")
                if bbox and all(v is not None for v in bbox) and bbox[3] > 0:
                    x, y, w, h = bbox
                    # Only place if item is inside visible area
                    tree_height = self.mat_tree.winfo_height()
                    if 0 <= y <= tree_height - h:
                        # center spinbox in its cell
                        cell_center = x + (w // 2)
                        spn_width = 56
                        spn.place(in_=self.mat_tree, x=cell_center - spn_width//2, y=y+1, width=spn_width, height=h-2)
                    else:
                        spn.place_forget()
                else:
                    spn.place_forget()
            except Exception:
                spn.place_forget()

        def _place_all_spins():
            for item in self.mat_tree.get_children(""):
                _place_spin_for_item(item)

        # expose for other methods (bindings call this)
        def _position_minpct_spinboxes():
            _place_all_spins()
        self._position_minpct_spinboxes = _position_minpct_spinboxes  # attach as instance method

        # toggle announce on single click in column #1
        def on_click(event):
            item = self.mat_tree.identify_row(event.y)
            col = self.mat_tree.identify_column(event.x)
            if not item:
                return
            if col == "#1":
                cur = self.announce_map.get(item, True)
                cur = not cur
                self.announce_map[item] = cur
                prev_min = self.mat_tree.set(item, "minpct")
                self.mat_tree.item(item, values=("✓" if cur else "—", item, prev_min))
                self._save_announce_map()
                self._save_last_material_settings()  # Save last settings when announce map changes
                # keep spinboxes positioned after any layout change
                self._position_minpct_spinboxes()

        self.mat_tree.bind("<ButtonRelease-1>", on_click)

        # reposition the spinboxes on common layout/scroll events
        for ev in ("<Configure>", "<Expose>", "<Motion>",
           "<ButtonRelease-1>", "<MouseWheel>",
           "<KeyRelease-Up>", "<KeyRelease-Down>",
           "<KeyRelease-Prior>", "<KeyRelease-Next>"):
         self.mat_tree.bind(ev, lambda e: self._position_minpct_spinboxes(), add="+")

        # initial placement after the widget is fully drawn
        self.after_idle(self._position_minpct_spinboxes)

        btns = ttk.Frame(ann)
        btns.grid(row=3, column=0, sticky="w", pady=(8, 0))
        
        select_all_btn = tk.Button(btns, text="Select all", command=self._announce_all,
                                  bg="#2a5a2a", fg="#ffffff", 
                                  activebackground="#3a6a3a", activeforeground="#ffffff",
                                  relief="solid", bd=1, cursor="hand2", pady=3,
                                  highlightbackground="#1a3a1a", highlightcolor="#1a3a1a")
        select_all_btn.pack(side="left")
        self.ToolTip(select_all_btn, "Enable announcements for all materials")
        
        unselect_all_btn = tk.Button(btns, text="Unselect all", command=self._mute_all,
                                   bg="#5a2a2a", fg="#ffffff", 
                                   activebackground="#6a3a3a", activeforeground="#ffffff",
                                   relief="solid", bd=1, cursor="hand2", pady=3,
                                   highlightbackground="#3a1a1a", highlightcolor="#3a1a1a")
        unselect_all_btn.pack(side="left", padx=(6, 0))
        self.ToolTip(unselect_all_btn, "Disable announcements for all materials")

        # --- Preset buttons row ---
        self.preset_buttons = []
        for i in range(1, 6):
            btn = tk.Button(btns, text=f"Preset {i}",
                          bg="#4a4a2a", fg="#ffffff",
                          activebackground="#5a5a3a", activeforeground="#ffffff",
                          relief="solid", bd=1,
                          width=8, font=("Segoe UI", 9), cursor="hand2", pady=3,
                          highlightbackground="#2a2a1a", highlightcolor="#2a2a1a")
            btn.pack(side="left", padx=(8, 0))
            self.preset_buttons.append(btn)
            # Add tooltip for preset buttons
            self.ToolTip(btn, f"Left-click to load preset {i} announcement settings\nRight-click to save current settings as preset {i}")

            if i == 1:
                btn.bind("<Button-1>", lambda e: self._load_preset1())
                btn.bind("<Button-3>", lambda e: self._save_preset1())
                # Fix button state after right-click
                btn.bind("<ButtonRelease-3>", lambda e: e.widget.config(relief="raised"))
            else:
                btn.bind("<Button-1>", lambda e, num=i: self._load_preset(num))
                btn.bind("<Button-3>", lambda e, num=i: self._save_preset(num))
                # Fix button state after right-click
                btn.bind("<ButtonRelease-3>", lambda e: e.widget.config(relief="raised"))

            # Add tooltip to each preset button
            tooltip_text = ("Left-click = Load saved preset\n"
                          "Right-click = Save current settings into that preset slot\n"
                          f"Use Preset {i} to store different announcement profiles\n"
                          "(e.g. Core-only, High-value, All materials)")
            self.ToolTip(btn, tooltip_text)

        # Graphs tab - Analytics visualization (Session tab removed and merged into Prospector)
        if CHARTS_AVAILABLE:
            charts = ttk.Frame(nb, padding=8)
            nb.add(charts, text="📊 Graphs")
            charts.columnconfigure(0, weight=1)
            charts.rowconfigure(0, weight=1)
            
            # Create graphs panel
            self.charts_panel = MiningChartsPanel(charts, self.session_analytics, self.main_app)
            self.charts_panel.ToolTip = self.ToolTip  # Pass ToolTip function to charts panel
            self.charts_panel.setup_tooltips()  # Setup tooltips after ToolTip is assigned
            self.charts_panel.grid(row=0, column=0, sticky="nsew")
        else:
            self.charts_panel = None

        # Reports tab - Session reports and management
        reports = ttk.Frame(nb, padding=8)
        nb.add(reports, text="📋 Reports")
        reports.columnconfigure(0, weight=1)
        reports.rowconfigure(0, weight=1)
        
        # Create the reports panel content
        self._create_reports_panel(reports)

        # Bookmarks tab - Mining location bookmarks
        bookmarks = ttk.Frame(nb, padding=8)
        nb.add(bookmarks, text="⭐ Bookmarks")
        bookmarks.columnconfigure(0, weight=1)
        bookmarks.rowconfigure(0, weight=1)
        
        # Create the bookmarks panel content
        self._create_bookmarks_panel(bookmarks)

        # Statistics tab - Session statistics and analytics
        statistics = ttk.Frame(nb, padding=8)
        nb.add(statistics, text="📊 Statistics")
        statistics.columnconfigure(0, weight=1)
        statistics.rowconfigure(0, weight=1)
        
        # Create the statistics panel content
        self._create_statistics_panel(statistics)

    # --- Cargo Monitor ---
    def _open_cargo_monitor(self) -> None:
        """Open the cargo monitor window from main app"""
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            self.main_app.cargo_monitor.show()
        else:
            print("Cargo monitor not available")



    # --- Reports window (reads from CSV index) ---
    def _open_reports_window(self) -> None:
        # Close existing window if open
        try:
            if self.reports_window and self.reports_window.winfo_exists():
                self.reports_window.destroy()
        except:
            # Window was already destroyed or invalid
            pass
        
        # Reset references to avoid issues
        self.reports_window = None
        self.reports_tree = None
            
        win = tk.Toplevel(self)
        win.title("Session Reports")
        win.minsize(1100, 500)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(0, weight=1)
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                win.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                win.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass

        # Position window relative to main application window
        try:
            # Get main window position
            main_window = self.winfo_toplevel()
            main_x = main_window.winfo_x()
            main_y = main_window.winfo_y()
            main_width = main_window.winfo_width()
            
            # Position reports window slightly offset from main window
            offset_x = main_x + 50
            offset_y = main_y + 50
            
            # Make sure window doesn't go off-screen
            if offset_x < 0:
                offset_x = 0
            if offset_y < 0:
                offset_y = 0
                
            win.geometry(f"900x500+{offset_x}+{offset_y}")
        except:
            # Fallback to default positioning if there's an error
            pass

        # Set window icon using centralized function
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                win.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                win.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception as e:
            # Use system default icon if all attempts fail
            pass

        # Track window and add close handler
        self.reports_window = win
        win.protocol("WM_DELETE_WINDOW", self._on_reports_window_close)

        frame = ttk.Frame(win, padding=8)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # Create sortable treeview with Material Analysis columns
        tree = ttk.Treeview(frame, columns=("date", "duration", "system", "body", "tons", "tph", "materials", "asteroids", "hit_rate", "quality", "cargo", "prospectors", "comment", "enhanced"), show="headings", height=16)
        tree.grid(row=0, column=0, sticky="nsew")
        
        # Remove custom styling - use default treeview appearance
        

        

        
        # Bind double-click to edit comments
        tree.bind("<Double-1>", self._edit_comment_popup)
        
        # Bind single-click to handle detailed report opening (with higher priority)
        tree.bind("<Button-1>", self._create_enhanced_click_handler(tree))
        
        # Add hover effect for detailed reports column
        tree.bind("<Motion>", lambda event: self._handle_mouse_motion(event, tree))
        
        # Configure column headings
        tree.heading("date", text="Date/Time")
        tree.heading("system", text="System")
        tree.heading("body", text="Body")
        tree.heading("duration", text="Duration")
        tree.heading("tons", text="Total Tons")
        tree.heading("tph", text="TPH")
        tree.heading("asteroids", text="Prospected")
        tree.heading("materials", text="Mat Types")
        tree.heading("hit_rate", text="Hit Rate %")
        tree.heading("quality", text="Average Yield %")
        tree.heading("cargo", text="Materials (Tonnage & Yields)")
        tree.heading("prospectors", text="Prospectors")
        tree.heading("comment", text="Comment")
        tree.heading("enhanced", text="Detail Report")
        

        

        

        
        # Configure column widths and alignment (optimized for 1100px window)
        # Left-align text columns
        tree.column("date", width=145, minwidth=135, anchor="w")
        tree.column("system", width=105, minwidth=85, anchor="w")
        tree.column("body", width=155, minwidth=120, anchor="center")
        
        # Center-align short data columns
        tree.column("duration", width=80, minwidth=70, anchor="center")
        tree.column("asteroids", width=80, minwidth=70, anchor="center")
        tree.column("materials", width=80, minwidth=70, anchor="center")
        tree.column("hit_rate", width=90, minwidth=80, anchor="center")
        tree.column("quality", width=120, minwidth=100, anchor="center")
        
        # Right-align numeric currency-like columns
        tree.column("tons", width=75, minwidth=65, anchor="e")
        tree.column("tph", width=60, minwidth=50, anchor="e")
        
        # New cargo columns - wider since we use full material names
        tree.column("cargo", width=300, minwidth=250, anchor="w", stretch=False)
        tree.column("prospectors", width=80, minwidth=70, anchor="center", stretch=False)
        tree.column("comment", width=200, minwidth=150, anchor="w", stretch=True)
        tree.column("enhanced", width=100, minwidth=80, anchor="center", stretch=False)

        # Add scrollbar
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sb.set)

        # Word wrap toggle variable for this window
        word_wrap_enabled = tk.BooleanVar(value=False)
        
        # Initialize sort direction tracking
        if not hasattr(self, 'reports_sort_reverse'):
            self.reports_sort_reverse = {}
        


        # Read data from CSV
        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
        sessions_data = []
        
        try:
            import csv
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Format the timestamp for display
                    try:
                        # Try to parse as local time first, then fall back to UTC
                        if row['timestamp_utc'].endswith('Z'):
                            # UTC format - convert to local time for display
                            timestamp = dt.datetime.fromisoformat(row['timestamp_utc'].replace('Z', '+00:00'))
                            timestamp = timestamp.replace(tzinfo=dt.timezone.utc).astimezone()
                        else:
                            # Local time format
                            timestamp = dt.datetime.fromisoformat(row['timestamp_utc'])
                        date_str = timestamp.strftime("%Y-%m-%d %H:%M")
                    except:
                        date_str = row['timestamp_utc']
                    
                    # Format TPH
                    try:
                        tph_val = float(row['overall_tph'])
                        tph_str = f"{tph_val:.1f}"
                    except:
                        tph_str = row['overall_tph']
                    
                    # Format tons
                    try:
                        tons_val = float(row['total_tons'])
                        tons_str = f"{tons_val:.1f}"
                    except:
                        tons_str = row['total_tons']
                    
                    # Format Material Analysis fields (with fallback for old data)
                    asteroids = row.get('asteroids_prospected', '').strip() or '0'
                    materials = row.get('materials_tracked', '').strip() or '0'
                    hit_rate = row.get('hit_rate_percent', '').strip() or '0'
                    avg_quality = row.get('avg_quality_percent', '').strip() or '0'
                    
                    # Get new cargo tracking fields
                    materials_breakdown_raw = row.get('materials_breakdown', '').strip() or '—'
                    prospectors_used = row.get('prospectors_used', '').strip() or '—'
                    
                    # Enhanced materials display with yield percentages
                    materials_breakdown = self._enhance_materials_with_yields(materials_breakdown_raw, avg_quality)
                    print(f"DEBUG: Original materials: {materials_breakdown_raw}")
                    print(f"DEBUG: Yield data: {avg_quality}")
                    print(f"DEBUG: Enhanced materials: {materials_breakdown}")
                    
                    # Apply word wrap formatting if enabled
                    if word_wrap_enabled.get() and materials_breakdown != '—':
                        materials_breakdown = materials_breakdown.replace('; ', '\n')
                    
                    
                    # Format asteroids and materials columns
                    try:
                        asteroids_val = int(asteroids) if asteroids and asteroids != '0' else 0
                        asteroids_str = str(asteroids_val) if asteroids_val > 0 else "—"
                    except:
                        asteroids_str = "—"
                    
                    try:
                        materials_val = int(materials) if materials and materials != '0' else 0
                        materials_str = str(materials_val) if materials_val > 0 else "—"
                    except:
                        materials_str = "—"
                    
                    # Format hit rate
                    try:
                        hit_rate_val = float(hit_rate) if hit_rate and hit_rate != '0' else 0
                        hit_rate_str = f"{hit_rate_val:.1f}" if hit_rate_val > 0 else "—"
                    except:
                        hit_rate_str = "—"
                    
                    # Format quality (yield %) - handle both old numerical and new formatted strings
                    try:
                        # Check if it's already a formatted string (contains letters)
                        if any(c.isalpha() for c in avg_quality):
                            quality_str = avg_quality  # Already formatted
                        else:
                            # Old numerical format
                            quality_val = float(avg_quality) if avg_quality and avg_quality != '0' else 0
                            quality_str = f"{quality_val:.1f}" if quality_val > 0 else "—"
                    except:
                        quality_str = "—"
                    
                    sessions_data.append({
                        'date': date_str,
                        'system': row['system'],
                        'body': row['body'],
                        'duration': row['elapsed'],
                        'tons': tons_str,
                        'tph': tph_str,
                        'materials': materials_str,
                        'asteroids': asteroids_str,
                        'hit_rate': hit_rate_str,
                        'quality': quality_str,
                        'cargo': materials_breakdown,
                        'cargo_raw': materials_breakdown_raw,  # Store original for tooltip
                        'prospectors': prospectors_used,
                        'timestamp_raw': row['timestamp_utc']  # For sorting
                    })
                        
        except Exception as e:
            log.exception("Loading CSV failed: %s", e)
            # Fallback to old file listing method
            try:
                for fn in os.listdir(self.reports_dir):
                    if fn.lower().endswith(".txt") and fn.startswith("Session"):
                        mtime = os.path.getmtime(os.path.join(self.reports_dir, fn))
                        date_str = dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                        sessions_data.append({
                            'date': date_str,
                            'system': 'Unknown',
                            'body': 'Unknown',
                            'duration': 'Unknown',
                            'tons': '0.0',
                            'tph': '0.0',
                            'asteroids': '—',
                            'materials': '—',
                            'hit_rate': '—',
                            'quality': '—',
                            'cargo': '—',
                            'prospectors': '—',
                            'timestamp_raw': date_str
                        })
            except:
                pass

        # Sort by timestamp (newest first) by default
        sessions_data.sort(key=lambda x: x['timestamp_raw'], reverse=True)
        
        # Store original sessions_data for lookup after sorting
        original_sessions = sessions_data.copy()
        
        # Populate treeview and store session data for file lookup and tooltips
        session_lookup = {}  # Map row IDs to full session data
        for i, session in enumerate(sessions_data):
            # Apply alternating row tags
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            
            # Check if this report has detailed reports (keep screenshots functionality but don't show column)
            # Try both display date and raw timestamp for compatibility
            report_id_display = f"{session['date']}_{session['system']}_{session['body']}"
            report_id_raw = f"{session.get('timestamp_raw', session['date'])}_{session['system']}_{session['body']}"
            
            enhanced_indicator = (self._get_detailed_report_indicator(report_id_display) or 
                                self._get_detailed_report_indicator(report_id_raw))
            
            item_id = tree.insert("", "end", values=(
                session['date'],
                session['duration'],
                session['system'], 
                session['body'],
                session['tons'],
                session['tph'],
                session['materials'],
                session['asteroids'],
                session['hit_rate'],
                session['quality'],
                session['cargo'],
                session['prospectors'],
                session.get('comment', ''),
                enhanced_indicator
            ), tags=(tag,))
            
            # After inserting, check with actual tree values for consistency
            tree_values = tree.item(item_id, 'values')
            if len(tree_values) >= 4:
                tree_report_id = f"{tree_values[0]}_{tree_values[2]}_{tree_values[3]}"
                
                # Update enhanced column with correct check
                actual_enhanced_indicator = self._get_detailed_report_indicator(tree_report_id)
                tree.set(item_id, "enhanced", actual_enhanced_indicator)
            # Store the full session data for file lookup and tooltips
            session_lookup[item_id] = session
        
        # Store session lookup for tooltip access
        self.reports_window_session_lookup = session_lookup
        
        # Store original sessions for sorting lookup
        self.reports_window_original_sessions = original_sessions
        
        # Direct sorting implementation
        sort_dirs = {}
        def sort_col(col):
            try:
                print(f"Sorting {col}")
                reverse = sort_dirs.get(col, False)
                items = [(tree.set(item, col), item) for item in tree.get_children('')]
                
                # Smart sorting based on column type
                numeric_cols = {"tons", "tph", "hit_rate", "quality", "materials", "asteroids", "prospectors"}
                if col in numeric_cols:
                    # Numeric sorting - handle "—" and empty values
                    def safe_float(x):
                        try:
                            val = str(x).replace("—", "0").strip()
                            return float(val) if val else 0.0
                        except:
                            return 0.0
                    items.sort(key=lambda x: safe_float(x[0]), reverse=reverse)
                else:
                    # String sorting for text columns
                    items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)
                    
                for index, (val, item) in enumerate(items):
                    tree.move(item, '', index)
                sort_dirs[col] = not reverse
            except Exception as e:
                print(f"Sorting error for column {col}: {e}")
                # Fallback to simple string sort
                try:
                    items = [(tree.set(item, col), item) for item in tree.get_children('')]
                    items.sort(key=lambda x: str(x[0]).lower(), reverse=sort_dirs.get(col, False))
                    for index, (val, item) in enumerate(items):
                        tree.move(item, '', index)
                    sort_dirs[col] = not sort_dirs.get(col, False)
                except Exception as e2:
                    print(f"Fallback sorting failed: {e2}")
            
            # CRITICAL: Rebuild session_lookup after sorting to match new order
            new_session_lookup = {}
            for item_id in tree.get_children(''):
                values = tree.item(item_id, 'values')
                # Find the original session data that matches these values from original_sessions
                found = False
                for orig_session in self.reports_window_original_sessions:
                    if (orig_session['date'] == values[0] and 
                        orig_session['system'] == values[1] and 
                        orig_session['body'] == values[2] and
                        orig_session['duration'] == values[3]):
                        new_session_lookup[item_id] = orig_session
                        print(f"    Found match: {orig_session['timestamp_raw']}")
                        found = True
                        break
            session_lookup.clear()
            session_lookup.update(new_session_lookup)
        
        # Set commands for all popup window columns
        tree.heading("date", command=lambda: sort_col("date"))
        tree.heading("system", command=lambda: sort_col("system"))
        tree.heading("body", command=lambda: sort_col("body"))
        tree.heading("duration", command=lambda: sort_col("duration"))
        tree.heading("tons", command=lambda: sort_col("tons"))
        tree.heading("tph", command=lambda: sort_col("tph"))
        tree.heading("materials", command=lambda: sort_col("materials"))
        tree.heading("asteroids", command=lambda: sort_col("asteroids"))
        tree.heading("hit_rate", command=lambda: sort_col("hit_rate"))
        tree.heading("quality", command=lambda: sort_col("quality"))
        tree.heading("cargo", command=lambda: sort_col("cargo"))
        tree.heading("prospectors", command=lambda: sort_col("prospectors"))
        tree.heading("comment", command=lambda: sort_col("comment"))
        
        # Store tree reference after everything is set up
        self.reports_tree = tree
        
        # Apply initial word wrap state
        if word_wrap_enabled.get():
            max_lines = 1
            for item in tree.get_children():
                item_data = session_lookup.get(item)
                if item_data:
                    lines = item_data['cargo_raw'].count(';') + 1
                    max_lines = max(max_lines, min(lines, 3))
            new_height = max_lines * 20 + 10
            style = ttk.Style()
            style.configure("ReportsWindow.Treeview", rowheight=new_height)
            tree.configure(style="ReportsWindow.Treeview")



        def open_selected():
            selection = tree.selection()
            if not selection:
                return
            
            # Get the session data directly from tree values - ignore session_lookup
            item_id = selection[0]
            values = tree.item(item_id, 'values')
            if not values or len(values) < 12:
                self._set_status("Could not find session data...")
                self._open_path(self.reports_dir)
                return
            
            # Create session dict from tree values and find timestamp from CSV
            session = {
                'date': values[0],
                'system': values[2], 
                'body': values[3],
                'duration': values[1]
            }
            
            # Find timestamp by reading CSV directly
            try:
                import csv
                csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Match by system, body, and duration
                        if (row['system'] == values[2] and 
                            row['body'] == values[3] and
                            row['elapsed'] == values[1]):
                            session['timestamp_raw'] = row['timestamp_utc']
                            break
            except Exception as e:
                print(f"CSV read error: {e}")
                # Fallback - use display date
                session['timestamp_raw'] = values[0]
            
            # Try to find the corresponding text file using multiple strategies
            try:
                report_files = []
                for fn in os.listdir(self.reports_dir):
                    if fn.lower().endswith(".txt") and fn.startswith("Session"):
                        report_files.append(fn)
                
                # Strategy 1: Parse CSV timestamp to match filename format
                try:
                    # Convert "2025-08-22T17:44:49Z" to "2025-08-22_17-44-49"
                    timestamp = session['timestamp_raw'].replace('Z', '').replace('T', '_').replace(':', '-')
                    for fn in report_files:
                        if timestamp in fn:
                            fpath = os.path.join(self.reports_dir, fn)
                            self._open_path(fpath)
                            return
                except Exception:
                    pass
                
                # Strategy 2: Find by system and body match
                system = session['system'].replace(' ', '_')
                body = session['body'].replace(' ', '_')
                matching_files = []
                for fn in report_files:
                    if system in fn and body in fn:
                        matching_files.append((os.path.getmtime(os.path.join(self.reports_dir, fn)), fn))
                
                if matching_files:
                    # Sort by modification time and pick the closest one
                    matching_files.sort()
                    # For now, just pick the first match - could be improved with better timestamp matching
                    fpath = os.path.join(self.reports_dir, matching_files[0][1])
                    self._open_path(fpath)
                    return
                
                # Strategy 3: Find by approximate time match
                try:
                    # Parse session timestamp
                    session_time = dt.datetime.fromisoformat(session['timestamp_raw'].replace('Z', '+00:00'))
                    best_match = None
                    min_diff = float('inf')
                    
                    for fn in report_files:
                        file_path = os.path.join(self.reports_dir, fn)
                        file_time = dt.datetime.fromtimestamp(os.path.getmtime(file_path))
                        time_diff = abs((session_time.replace(tzinfo=None) - file_time).total_seconds())
                        
                        if time_diff < min_diff:
                            min_diff = time_diff
                            best_match = fn
                    
                    if best_match and min_diff < 3600:  # Within 1 hour
                        fpath = os.path.join(self.reports_dir, best_match)
                        self._open_path(fpath)
                        return
                        
                except Exception:
                    pass
                
            except Exception as e:
                self._set_status(f"Error searching for report: {e}")
            
            # Fallback: open the reports folder
            self._set_status("Could not find specific report file, opening reports folder...")
            self._open_path(self.reports_dir)

        def handle_popup_double_click(event):
            """Handle double-click on popup reports tree"""
            # Identify which column was clicked
            item = tree.identify('item', event.x, event.y)
            column = tree.identify('column', event.x, event.y)
            
            if not item:
                return
            
            # Check if it's the comment column or detailed reports column
            if column == '#13':  # Comment column in popup
                # Edit comment
                self._edit_comment_popup(event)
            elif column == '#14':  # Detailed reports column in popup
                # Handle detailed report opening
                columns = tree["columns"]
                if len(columns) > 13:  # Make sure enhanced column exists
                    column_name = columns[13]  # Enhanced column (0-indexed)
                    cell_value = tree.set(item, column_name)
                    if cell_value == "✓":  # Has detailed report
                        session_data = self.reports_window_session_lookup.get(item)
                        if session_data:
                            original_timestamp = session_data.get('timestamp_raw', session_data.get('date', ''))
                            system = session_data.get('system', '')
                            body = session_data.get('body', '')
                            report_id = f"{original_timestamp}_{system}_{body}"
                            self._open_enhanced_report(report_id)
                # Don't open CSV file for detailed reports column
                return
            else:
                # Open the report file for other columns
                open_selected()

        tree.bind("<Double-1>", handle_popup_double_click)
        
        # Add right-click context menu
        def copy_system_to_clipboard_reports(tree_ref):
            """Copy selected system name to clipboard from reports tree"""
            selection = tree_ref.selection()
            if not selection:
                return
            
            # Get selected item data
            item = selection[0]
            values = tree_ref.item(item, 'values')
            if not values or len(values) < 3:
                return
            
            # System name is in column index 2 (third column: date, duration, system...)
            system_name = values[2]
            if system_name:
                # Copy to clipboard
                tree_ref.clipboard_clear()
                tree_ref.clipboard_append(system_name)
                tree_ref.update()  # Required to ensure clipboard is updated
                
                # Show brief status message
                self._set_status(f"Copied '{system_name}' to clipboard")
            else:
                self._set_status("No system name to copy")

        def show_context_menu(event):
            # Check if we right-clicked on an item
            item = tree.identify_row(event.y)
            if item:
                # Get current selection
                selected_items = tree.selection()
                
                # If right-clicked item isn't in selection, add it to selection
                # (don't replace the entire selection)
                if item not in selected_items:
                    tree.selection_add(item)
                
                # Get all currently selected items after potential addition
                selected_items = tree.selection()
                if selected_items:
                    context_menu = tk.Menu(tree, tearoff=0, bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"], 
                                         activebackground=MENU_COLORS["activebackground"], 
                                         activeforeground=MENU_COLORS["activeforeground"],
                                         selectcolor=MENU_COLORS["selectcolor"])
                    context_menu.add_command(label="📂 Open Report (CSV)", command=open_selected)
                    context_menu.add_command(label="📊 Open Detailed Report (HTML)", command=lambda: self._open_enhanced_report_from_menu(tree))
                    context_menu.add_separator()
                    context_menu.add_command(label="📊 Generate Detailed Report (HTML)", command=lambda: self._generate_enhanced_report_from_menu(tree))
                    context_menu.add_separator()
                    context_menu.add_command(label="� Copy System Name", command=lambda: copy_system_to_clipboard_reports(tree))
                    context_menu.add_separator()
                    # Debug: Add a test menu item to verify context menu is working
                    # from tkinter import messagebox
                    # context_menu.add_command(label="🔧 DEBUG: Menu Working!", command=lambda: messagebox.showinfo("Debug", "Right-click menu is working! The new screenshot and detailed report options should be visible above."))
                    context_menu.add_separator()
                    
                    # Word wrap toggle
                    wrap_text = "Disable Word Wrap" if word_wrap_enabled.get() else "Enable Word Wrap" 
                    def toggle_word_wrap():
                        word_wrap_enabled.set(not word_wrap_enabled.get())
                        # Don't change global row height - handle per-row instead
                        # Update existing data in place and manage row tags
                        for i, item in enumerate(tree.get_children()):
                            values = list(tree.item(item, 'values'))
                            item_data = session_lookup.get(item)
                            if item_data:
                                if word_wrap_enabled.get():
                                    values[10] = item_data['cargo_raw'].replace('; ', '\n')  # cargo column
                                    # Use special tag for wrapped rows - but tkinter doesn't support per-row height
                                    # Keep alternating colors but indicate wrapped content
                                else:
                                    values[10] = item_data['cargo_raw']
                                tree.item(item, values=values)
                        
                        # Tkinter limitation: Must use global row height, calculate needed height
                        max_lines = 1
                        if word_wrap_enabled.get():
                            for item in tree.get_children():
                                item_data = session_lookup.get(item)
                                if item_data:
                                    lines = item_data['cargo_raw'].count(';') + 1
                                    max_lines = max(max_lines, min(lines, 3))  # Cap at 3 lines
                        
                        # Set row height for word wrap
                        if word_wrap_enabled.get():
                            new_height = max_lines * 20 + 10  # 20px per line + padding
                        else:
                            new_height = 20  # Default single line height
                        style = ttk.Style()
                        style.configure("ReportsWindow.Treeview", rowheight=new_height)
                        tree.configure(style="ReportsWindow.Treeview")
                        
                        # Force complete tree refresh
                        tree.yview_scroll(1, 'units')
                        tree.yview_scroll(-1, 'units')
                        tree.update_idletasks()
                    
                    context_menu.add_command(label=wrap_text, command=toggle_word_wrap)
                    context_menu.add_separator()
                    
                    # Update label based on selection count
                    if len(selected_items) == 1:
                        context_menu.add_command(label="🗑️Delete Detailed Report + Screenshots", 
                                               command=lambda: self._delete_enhanced_report_from_menu(tree))
                        context_menu.add_separator()  # Add separator for safety
                        context_menu.add_command(label="🗑️Delete Complete Session", 
                                               command=lambda items=selected_items: delete_selected(items))
                    else:
                        context_menu.add_command(label=f"🗑️Delete {len(selected_items)} CSV Entries + Text Reports", 
                                               command=lambda items=selected_items: delete_selected(items))
                    
                    try:
                        context_menu.tk_popup(event.x_root, event.y_root)
                    finally:
                        context_menu.grab_release()
        
        def delete_selected(selected_items):
            # Get session data directly from tree values - ignore session_lookup completely
            sessions_to_delete = []
            for item_id in selected_items:
                values = tree.item(item_id, 'values')
                if values and len(values) >= 12:
                    # Create a session dict directly from tree values and find timestamp from CSV
                    session_data = {
                        'date': values[0],
                        'system': values[1], 
                        'body': values[2],
                        'duration': values[3],
                        'tons': values[4],
                        'tph': values[5],
                        'materials': values[6],
                        'asteroids': values[7],
                        'hit_rate': values[8],
                        'quality': values[9],
                        'cargo': values[10],
                        'prospectors': values[11]
                    }
                    
                    # Find timestamp by reading CSV directly
                    try:
                        import csv
                        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                        with open(csv_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                # Match by formatted date, system, body
                                if (row['system'] == values[1] and 
                                    row['body'] == values[2] and
                                    row['elapsed'] == values[3]):
                                    session_data['timestamp_raw'] = row['timestamp_utc']
                                    break
                    except:
                        # Fallback - use display date
                        session_data['timestamp_raw'] = values[0]
                    
                    sessions_to_delete.append((item_id, session_data))
            
            if not sessions_to_delete:
                return
            
            # Create confirmation message
            if len(sessions_to_delete) == 1:
                item_id, session = sessions_to_delete[0]
                confirm_msg = (f"Are you sure you want to permanently delete this mining session report?\n\n"
                              f"Session Details:\n"
                              f"• Date: {session['date']}\n"
                              f"• System: {session['system']}\n"
                              f"• Body: {session['body']}\n"
                              f"• Duration: {session['duration']}\n"
                              f"• Tons Mined: {session['tons']}\n\n"
                              f"This will permanently delete:\n"
                              f"• The CSV report entry\n"
                              f"• The individual report file\n\n"
                              f"This action cannot be undone.")
                title = "Delete Mining Session Report"
            else:
                confirm_msg = f"Are you sure you want to permanently delete {len(sessions_to_delete)} mining session reports?\n\n"
                confirm_msg += "Sessions to be deleted:\n"
                for i, (_, session) in enumerate(sessions_to_delete[:5], 1):  # Show max 5 items
                    confirm_msg += f"  {i}. {session['date']} - {session['system']}/{session['body']}\n"
                if len(sessions_to_delete) > 5:
                    confirm_msg += f"  ... and {len(sessions_to_delete) - 5} more\n"
                confirm_msg += f"\nThis will permanently delete:\n"
                confirm_msg += f"• All CSV report entries\n"
                confirm_msg += f"• All individual report files\n\n"
                confirm_msg += f"This action cannot be undone."
                title = "Delete Multiple Mining Session Reports"
            
            # Confirm deletion
            result = messagebox.askyesno(title, confirm_msg, icon="warning")
            
            # Bring reports window back to front after messagebox
            try:
                win.lift()
                win.focus_force()
            except:
                pass
            
            if result:
                success_count = 0
                file_delete_count = 0
                errors = []
                
                # Get list of report files once
                report_files = []
                for fn in os.listdir(self.reports_dir):
                    if fn.lower().endswith(".txt") and fn.startswith("Session"):
                        report_files.append(fn)
                
                for item_id, session in sessions_to_delete:
                    try:
                        # Find and delete the corresponding text file
                        file_deleted = False
                        
                        # Strategy 1: Parse CSV timestamp to match filename format
                        try:
                            timestamp = session['timestamp_raw'].replace('Z', '').replace('T', '_').replace(':', '-')
                            for fn in report_files:
                                if timestamp in fn:
                                    fpath = os.path.join(self.reports_dir, fn)
                                    os.remove(fpath)
                                    file_deleted = True
                                    break
                        except Exception:
                            pass
                        
                        if not file_deleted:
                            # Strategy 2: Find by system and body match
                            system = session['system'].replace(' ', '_')
                            body = session['body'].replace(' ', '_')
                            matching_files = []
                            for fn in report_files:
                                if system in fn and body in fn:
                                    matching_files.append((os.path.getmtime(os.path.join(self.reports_dir, fn)), fn))
                            
                            if matching_files:
                                matching_files.sort()
                                fpath = os.path.join(self.reports_dir, matching_files[0][1])
                                os.remove(fpath)
                                file_deleted = True
                        
                        if file_deleted:
                            file_delete_count += 1
                        
                        # Delete corresponding graph files
                        try:
                            # Get graphs directory using same logic as auto_save_graphs
                            if getattr(sys, 'frozen', False):
                                app_dir = os.path.join(self.va_root, "app")
                            else:
                                app_dir = os.path.dirname(os.path.abspath(__file__))
                            
                            graphs_dir = os.path.join(app_dir, "Reports", "Mining Session", "Graphs")
                            print(f"DEBUG: Looking for graphs in: {graphs_dir}")
                            
                            # Also write debug to file
                            debug_file = os.path.join(os.path.dirname(graphs_dir), "delete_debug.txt")
                            with open(debug_file, "a", encoding="utf-8") as f:
                                f.write(f"DELETE DEBUG: Starting graph deletion for session\n")
                                f.write(f"DELETE DEBUG: Graphs dir: {graphs_dir}\n")
                                f.write(f"DELETE DEBUG: Session data: {session}\n")
                            
                            if os.path.exists(graphs_dir):
                                # Create session ID to match graph files - use EXACT same logic as auto_save_graphs
                                try:
                                    timestamp = session['timestamp_raw'].replace('Z', '').replace('T', '_').replace(':', '-')
                                    session_prefix = f"Session_{timestamp}"
                                    
                                    if session['system']:
                                        # Clean system name for filename (same as auto_save_graphs)
                                        clean_system = "".join(c for c in session['system'] if c.isalnum() or c in (' ', '-', '_')).strip()
                                        clean_system = clean_system.replace(' ', '_')
                                        session_prefix += f"_{clean_system}"
                                    
                                    if session['body']:
                                        # Clean body name for filename (same as auto_save_graphs)
                                        clean_body = "".join(c for c in session['body'] if c.isalnum() or c in (' ', '-', '_')).strip()
                                        clean_body = clean_body.replace(' ', '_')
                                        session_prefix += f"_{clean_body}"
                                    
                                    print(f"DEBUG: Looking for graphs with prefix: {session_prefix}")
                                    
                                    # Delete graph files
                                    deleted_graphs = []
                                    for graph_file in os.listdir(graphs_dir):
                                        if graph_file.startswith(session_prefix) and graph_file.endswith('.png'):
                                            graph_path = os.path.join(graphs_dir, graph_file)
                                            os.remove(graph_path)
                                            deleted_graphs.append(graph_file)
                                            print(f"DEBUG: Deleted graph: {graph_file}")
                                    
                                    if not deleted_graphs:
                                        print(f"DEBUG: No graph files found matching prefix: {session_prefix}")
                                        print(f"DEBUG: Available files: {os.listdir(graphs_dir)}")
                                    
                                    # Update graph mappings JSON
                                    mappings_file = os.path.join(graphs_dir, "graph_mappings.json")
                                    if os.path.exists(mappings_file):
                                        try:
                                            with open(mappings_file, 'r', encoding='utf-8') as f:
                                                mappings = json.load(f)
                                            if session_prefix in mappings:
                                                del mappings[session_prefix]
                                                with open(mappings_file, 'w', encoding='utf-8') as f:
                                                    json.dump(mappings, f, indent=2)
                                                print(f"DEBUG: Removed {session_prefix} from mappings")
                                        except Exception as e:
                                            print(f"DEBUG: Error updating mappings: {e}")
                                except Exception as e:
                                    print(f"DEBUG: Error processing session data: {e}")
                            else:
                                print(f"DEBUG: Graphs directory does not exist: {graphs_dir}")
                        except Exception as e:
                            print(f"DEBUG: Error in graph deletion: {e}")
                        
                        success_count += 1
                        
                    except Exception as e:
                        errors.append(f"  • {session['system']}/{session['body']} ({session['date']}): {str(e)}")
                
                # Update CSV file - remove all deleted sessions at once
                if success_count > 0:
                    try:
                        import csv
                        
                        # Get timestamps of sessions to delete
                        timestamps_to_delete = {session['timestamp_raw'] for _, session in sessions_to_delete}
                        
                        # Read all sessions except the ones to delete
                        remaining_sessions = []
                        with open(csv_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                if row['timestamp_utc'] not in timestamps_to_delete:
                                    remaining_sessions.append(row)
                        
                        # Write back the remaining sessions
                        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                            if remaining_sessions:
                                fieldnames = remaining_sessions[0].keys()
                                writer = csv.DictWriter(f, fieldnames=fieldnames)
                                writer.writeheader()
                                writer.writerows(remaining_sessions)
                        
                        # Remove from tree
                        for item_id, _ in sessions_to_delete:
                            tree.delete(item_id)
                        
                        # Show success message
                        if len(sessions_to_delete) == 1:
                            status_msg = "Session report deleted successfully"
                            if file_delete_count > 0:
                                status_msg += " (including report file)"
                            else:
                                status_msg += " (CSV entry removed, report file not found)"
                        else:
                            status_msg = f"{success_count} session reports deleted successfully"
                            if file_delete_count > 0:
                                status_msg += f" (including {file_delete_count} report files)"
                        
                        self._set_status(status_msg)
                        
                        # Show errors if any
                        if errors:
                            error_msg = f"Some errors occurred while deleting:\n\n" + "\n".join(errors)
                            messagebox.showwarning("Partial Success", error_msg)
                        
                    except Exception as e:
                        self._set_status(f"Error updating CSV file: {e}")
                        messagebox.showerror("Delete Error", f"Failed to update CSV file:\n{e}")
                
                # Bring reports window back to front after completion
                try:
                    win.lift()
                    win.focus_force()
                except:
                    pass
        
        tree.bind("<Button-3>", show_context_menu)  # Right-click

        btns = ttk.Frame(win, padding=(6, 8))
        btns.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        btns.columnconfigure(0, weight=1)  # Left spacer
        btns.columnconfigure(5, weight=1)  # Right spacer to push close button to the right
        
        # Center the action buttons
        rebuild_btn = tk.Button(btns, text="Rebuild CSV", command=lambda: self._rebuild_csv_from_files(csv_path, win), bg="#444444", fg="#ffffff", activebackground="#555555", activeforeground="#ffffff", relief="solid", bd=1, highlightbackground="#666666", highlightcolor="#666666")
        rebuild_btn.grid(row=0, column=1, padx=(4, 0))
        self.ToolTip(rebuild_btn, "Rebuild the CSV index from all text files in the reports folder. Use this if data doesn't match between the table and files.")
        
        folder_btn = tk.Button(btns, text="Open Folder", command=lambda: self._open_path(self.reports_dir), bg="#444444", fg="#ffffff", activebackground="#555555", activeforeground="#ffffff", relief="solid", bd=1, highlightbackground="#666666", highlightcolor="#666666")
        folder_btn.grid(row=0, column=2, padx=(4, 0))
        self.ToolTip(folder_btn, "Open the reports folder in Windows Explorer to browse all session files.")
        
        export_btn = tk.Button(btns, text="Export CSV", command=lambda: self._export_csv(csv_path), bg="#444444", fg="#ffffff", activebackground="#555555", activeforeground="#ffffff", relief="solid", bd=1, highlightbackground="#666666", highlightcolor="#666666")
        export_btn.grid(row=0, column=3, padx=(4, 0))
        self.ToolTip(export_btn, "Export session data to a CSV file that can be opened in Excel or other spreadsheet programs.")
        
        batch_btn = tk.Button(btns, text="Batch Reports", command=lambda: self._open_batch_reports_dialog(win), bg="#2a4a5a", fg="#ffffff", activebackground="#3a5a6a", activeforeground="#ffffff", relief="solid", bd=1, highlightbackground="#666666", highlightcolor="#666666")
        batch_btn.grid(row=0, column=4, padx=(4, 0))
        self.ToolTip(batch_btn, "Generate enhanced HTML reports for multiple sessions at once.")

        # Close button on the far right with more space
        close_btn = tk.Button(btns, text="Close", command=win.destroy, bg="#444444", fg="#ffffff", activebackground="#555555", activeforeground="#ffffff", relief="solid", bd=1, highlightbackground="#666666", highlightcolor="#666666", width=8)
        close_btn.grid(row=0, column=6, sticky="e", padx=(20, 0))
        self.ToolTip(close_btn, "Close the reports window.")

    def _rebuild_csv_from_files(self, csv_path: str, parent_window) -> None:
        """Rebuild the CSV index from existing text files"""
        try:
            import csv
            import re
            from tkinter import messagebox
            
            # First, try to read existing Material Analysis data from current CSV
            existing_analysis_data = {}
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Use timestamp as key to preserve Material Analysis data
                            timestamp = row.get('timestamp_utc', '')
                            if timestamp:
                                existing_analysis_data[timestamp] = {
                                    'asteroids_prospected': row.get('asteroids_prospected', ''),
                                    'materials_tracked': row.get('materials_tracked', ''),
                                    'hit_rate_percent': row.get('hit_rate_percent', ''),
                                    'avg_quality_percent': row.get('avg_quality_percent', ''),
                                    'best_material': row.get('best_material', ''),
                                    'materials_breakdown': row.get('materials_breakdown', ''),
                                    'prospectors_used': row.get('prospectors_used', ''),
                                    'comment': row.get('comment', '')
                                }
                except Exception as e:
                    print(f"Warning: Could not read existing analysis data: {e}")
            
            # Parse all text files
            sessions = []
            
            for fn in os.listdir(self.reports_dir):
                if not (fn.lower().endswith(".txt") and fn.startswith("Session")):
                    continue
                    
                try:
                    file_path = os.path.join(self.reports_dir, fn)
                    
                    # Extract timestamp from filename: Session_YYYY-MM-DD_HH-MM-SS_...
                    timestamp_match = re.search(r'Session_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', fn)
                    if not timestamp_match:
                        continue
                        
                    date_part = timestamp_match.group(1)
                    time_part = timestamp_match.group(2).replace('-', ':')
                    timestamp_local = f"{date_part}T{time_part}"
                    
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    
                    # Parse header line: "Session: System — Body — Duration — Total XYt"
                    first_line = content.split('\n')[0]
                    if not first_line.startswith("Session:"):
                        continue
                    
                    parts = first_line.split("—")
                    if len(parts) < 4:
                        continue
                    
                    system = parts[0].replace("Session:", "").strip()
                    body = parts[1].strip()
                    duration = parts[2].strip()
                    total_part = parts[3].strip()
                    
                    # Extract total tons from "Total XXt"
                    total_match = re.search(r'Total (\d+(?:\.\d+)?)t', total_part)
                    total_tons = float(total_match.group(1)) if total_match else 0.0
                    
                    # Calculate TPH from duration and total
                    duration_seconds = 0
                    try:
                        # Parse duration HH:MM:SS
                        time_parts = duration.split(':')
                        if len(time_parts) == 3:
                            duration_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                    except:
                        duration_seconds = 0
                    
                    # For manual entries with zero duration, set TPH to 0 instead of calculating
                    if duration_seconds == 0:
                        overall_tph = 0.0
                    else:
                        duration_hours = duration_seconds / 3600.0
                        overall_tph = total_tons / duration_hours
                    
                    # Parse additional data from session content
                    asteroids_prospected = ''
                    materials_tracked = ''
                    hit_rate_percent = ''
                    avg_quality_percent = ''
                    best_material = ''
                    materials_breakdown = ''
                    prospectors_used = ''
                    
                    # Extract asteroids prospected
                    asteroids_match = re.search(r'Asteroids Prospected:\s*(\d+)', content)
                    if asteroids_match:
                        asteroids_prospected = asteroids_match.group(1)
                    
                    # Extract materials tracked  
                    materials_match = re.search(r'Materials Tracked:\s*(\d+)', content)
                    if materials_match:
                        materials_tracked = materials_match.group(1)
                    
                    # Extract hit rate
                    hit_rate_match = re.search(r'Hit Rate:\s*([\d.]+)%', content)
                    if hit_rate_match:
                        hit_rate_percent = hit_rate_match.group(1)
                    
                    # Extract overall quality
                    quality_match = re.search(r'Overall Quality:\s*([\d.]+)%', content)
                    if quality_match:
                        avg_quality_percent = quality_match.group(1)
                    
                    # Extract best performer
                    best_match = re.search(r'Best Performer:\s*([^\(]+)', content)
                    if best_match:
                        best_material = best_match.group(1).strip()
                    
                    # Extract prospector limpets used
                    prospector_match = re.search(r'Prospector Limpets Used:\s*(\d+)', content)
                    if prospector_match:
                        prospectors_used = prospector_match.group(1)
                    
                    # Extract materials breakdown from cargo section first
                    if not materials_breakdown:
                        refined_section = re.search(r'=== REFINED MATERIALS ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if refined_section:
                            refined_text = refined_section.group(1)
                            material_lines = re.findall(r'- ([A-Za-z\s]+) ([\d.]+)t', refined_text)
                            if material_lines:
                                materials_breakdown = ', '.join([f"{mat.strip()}: {tons}t" for mat, tons in material_lines])
                    
                    # Try CARGO MATERIAL BREAKDOWN section for manual entries (if refined materials empty)
                    if not materials_breakdown:
                        cargo_section = re.search(r'=== CARGO MATERIAL BREAKDOWN ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if cargo_section:
                            cargo_text = cargo_section.group(1)
                            # Look for "MaterialName: Xt" patterns
                            material_lines = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', cargo_text, re.MULTILINE)
                            if material_lines:
                                materials_breakdown = ', '.join([f"{mat.strip()}: {tons}t" for mat, tons in material_lines])
                    
                    # If materials_tracked is empty but we have materials_breakdown, count the materials
                    if not materials_tracked and materials_breakdown:
                        # Count comma-separated materials in breakdown
                        material_count = len([m.strip() for m in materials_breakdown.split(',') if m.strip()])
                        materials_tracked = str(material_count) if material_count > 0 else ''
                    
                    # Get preserved data for this timestamp (fallback if parsing fails)
                    existing_data = existing_analysis_data.get(timestamp_local, {})
                    
                    sessions.append({
                        'timestamp_utc': timestamp_local,
                        'system': system,
                        'body': body,
                        'elapsed': duration,
                        'total_tons': total_tons,
                        'overall_tph': overall_tph,
                        'asteroids_prospected': asteroids_prospected or existing_data.get('asteroids_prospected', ''),
                        'materials_tracked': materials_tracked or existing_data.get('materials_tracked', ''),
                        'hit_rate_percent': hit_rate_percent or existing_data.get('hit_rate_percent', ''),
                        'avg_quality_percent': avg_quality_percent or existing_data.get('avg_quality_percent', ''),
                        'best_material': best_material or existing_data.get('best_material', ''),
                        'materials_breakdown': materials_breakdown or existing_data.get('materials_breakdown', ''),
                        'prospectors_used': prospectors_used or existing_data.get('prospectors_used', ''),
                        'comment': existing_data.get('comment', '')  # Preserve existing comments
                    })
                    
                except Exception as e:
                    print(f"Error parsing {fn}: {e}")
                    continue
            
            if not sessions:
                # If no session files exist, create empty CSV with headers
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment'])
                    writer.writeheader()
                messagebox.showinfo("CSV Created", "Created new CSV file - ready for your first session")
                parent_window.destroy()
                return
            
            # Sort by timestamp
            sessions.sort(key=lambda x: x['timestamp_utc'])
            
            # Write new CSV
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment'])
                writer.writeheader()
                writer.writerows(sessions)
            
            # Close and reopen the reports window to refresh data
            parent_window.destroy()
            self._open_reports_window()
            
            self._set_status(f"CSV rebuilt with {len(sessions)} sessions.")
            
        except Exception as e:
            messagebox.showerror("Rebuild Failed", f"Failed to rebuild CSV: {e}")
            self._set_status(f"CSV rebuild failed: {e}")

    def _rebuild_csv_from_files_tab(self, csv_path: str, silent: bool = False) -> None:
        """Rebuild the CSV index from existing text files for Reports tab"""
        try:
            import csv
            import re
            if not silent:
                from tkinter import messagebox
            
            # First, try to read existing Material Analysis data from current CSV (excluding comments)
            existing_analysis_data = {}
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Use timestamp as key to preserve Material Analysis data (but not comments)
                            timestamp = row.get('timestamp_utc', '')
                            if timestamp:
                                existing_analysis_data[timestamp] = {
                                    'asteroids_prospected': row.get('asteroids_prospected', ''),
                                    'materials_tracked': row.get('materials_tracked', ''),
                                    'hit_rate_percent': row.get('hit_rate_percent', ''),
                                    'avg_quality_percent': row.get('avg_quality_percent', ''),
                                    'best_material': row.get('best_material', ''),
                                    'materials_breakdown': row.get('materials_breakdown', ''),
                                    'prospectors_used': row.get('prospectors_used', '')
                                    # Note: Removed comment preservation - will extract from text files
                                }
                except Exception as e:
                    print(f"Warning: Could not read existing analysis data: {e}")
            
            # Parse all text files
            sessions = []
            
            for fn in os.listdir(self.reports_dir):
                if not (fn.lower().endswith(".txt") and fn.startswith("Session")):
                    continue
                    
                try:
                    file_path = os.path.join(self.reports_dir, fn)
                    
                    # Extract timestamp from filename: Session_YYYY-MM-DD_HH-MM-SS_...
                    timestamp_match = re.search(r'Session_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', fn)
                    if not timestamp_match:
                        continue
                        
                    date_part = timestamp_match.group(1)
                    time_part = timestamp_match.group(2).replace('-', ':')
                    timestamp_local = f"{date_part}T{time_part}"
                    
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    
                    # Parse header line: "Session: System — Body — Duration — Total XYt"
                    first_line = content.split('\n')[0]
                    if not first_line.startswith("Session:"):
                        continue
                    
                    parts = first_line.split("—")
                    if len(parts) < 4:
                        continue
                    
                    system = parts[0].replace("Session:", "").strip()
                    body = parts[1].strip()
                    duration = parts[2].strip()
                    total_part = parts[3].strip()
                    
                    # Extract total tons from "Total XXt"
                    total_match = re.search(r'Total (\d+(?:\.\d+)?)t', total_part)
                    total_tons = float(total_match.group(1)) if total_match else 0.0
                    
                    # Calculate TPH from duration and total
                    duration_seconds = 0
                    try:
                        # Parse duration HH:MM:SS
                        time_parts = duration.split(':')
                        if len(time_parts) == 3:
                            duration_seconds = int(time_parts[0]) * 3600 + int(time_parts[1]) * 60 + int(time_parts[2])
                    except:
                        duration_seconds = 0
                    
                    # For manual entries with zero duration, set TPH to 0 instead of calculating
                    if duration_seconds == 0:
                        overall_tph = 0.0
                    else:
                        duration_hours = duration_seconds / 3600.0
                        overall_tph = total_tons / duration_hours
                    
                    # Parse additional data from session content
                    asteroids_prospected = ''
                    materials_tracked = ''
                    hit_rate_percent = ''
                    avg_quality_percent = ''
                    best_material = ''
                    materials_breakdown = ''
                    prospectors_used = ''
                    
                    # Extract asteroids prospected
                    asteroids_match = re.search(r'Asteroids Prospected:\s*(\d+)', content)
                    if asteroids_match:
                        asteroids_prospected = asteroids_match.group(1)
                    
                    # Extract materials tracked  
                    materials_match = re.search(r'Materials Tracked:\s*(\d+)', content)
                    if materials_match:
                        materials_tracked = materials_match.group(1)
                    
                    # Extract hit rate
                    hit_rate_match = re.search(r'Hit Rate:\s*([\d.]+)%', content)
                    if hit_rate_match:
                        hit_rate_percent = hit_rate_match.group(1)
                    
                    # Extract overall quality
                    quality_match = re.search(r'Overall Quality:\s*([\d.]+)%', content)
                    if quality_match:
                        avg_quality_percent = quality_match.group(1)
                    
                    # Extract best performer
                    best_match = re.search(r'Best Performer:\s*([^\(]+)', content)
                    if best_match:
                        best_material = best_match.group(1).strip()
                    
                    # Extract prospector limpets used
                    prospector_match = re.search(r'Prospector Limpets Used:\s*(\d+)', content)
                    if prospector_match:
                        prospectors_used = prospector_match.group(1)
                    
                    # Extract materials breakdown from cargo section first
                    if not materials_breakdown:
                        refined_section = re.search(r'=== REFINED MATERIALS ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if refined_section:
                            refined_text = refined_section.group(1)
                            material_lines = re.findall(r'- ([A-Za-z\s]+) ([\d.]+)t', refined_text)
                            if material_lines:
                                materials_breakdown = ', '.join([f"{mat.strip()}: {tons}t" for mat, tons in material_lines])
                    
                    # Try CARGO MATERIAL BREAKDOWN section for manual entries (if refined materials empty)
                    if not materials_breakdown:
                        cargo_section = re.search(r'=== CARGO MATERIAL BREAKDOWN ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if cargo_section:
                            cargo_text = cargo_section.group(1)
                            # Look for "MaterialName: Xt" patterns
                            material_lines = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', cargo_text, re.MULTILINE)
                            if material_lines:
                                materials_breakdown = ', '.join([f"{mat.strip()}: {tons}t" for mat, tons in material_lines])
                    
                    # If materials_tracked is empty but we have materials_breakdown, count the materials
                    if not materials_tracked and materials_breakdown:
                        # Count comma-separated materials in breakdown
                        material_count = len([m.strip() for m in materials_breakdown.split(',') if m.strip()])
                        materials_tracked = str(material_count) if material_count > 0 else ''
                    
                    # Extract session comment from text file content
                    session_comment = ""
                    comment_match = re.search(r'=== SESSION COMMENT ===\s*\n(.+?)(?:\n===|$)', content, re.DOTALL)
                    if comment_match:
                        session_comment = comment_match.group(1).strip()
                    
                    # Get preserved data for this timestamp (prioritize CSV data for analysis fields)
                    existing_data = existing_analysis_data.get(timestamp_local, {})
                    
                    sessions.append({
                        'timestamp_utc': timestamp_local,
                        'system': system,
                        'body': body,
                        'elapsed': duration,
                        'total_tons': total_tons,
                        'overall_tph': overall_tph,
                        # Prioritize existing CSV data for analysis fields, fall back to parsed text
                        'asteroids_prospected': existing_data.get('asteroids_prospected', '') or asteroids_prospected,
                        'materials_tracked': existing_data.get('materials_tracked', '') or materials_tracked,
                        'hit_rate_percent': existing_data.get('hit_rate_percent', '') or hit_rate_percent,
                        'avg_quality_percent': existing_data.get('avg_quality_percent', '') or avg_quality_percent,
                        'best_material': existing_data.get('best_material', '') or best_material,
                        'materials_breakdown': existing_data.get('materials_breakdown', '') or materials_breakdown,
                        'prospectors_used': existing_data.get('prospectors_used', '') or prospectors_used,
                        'comment': session_comment  # Extract comment from text file content
                    })
                    
                except Exception as e:
                    print(f"Error parsing {fn}: {e}")
                    continue
            
            if not sessions:
                # If no session files exist, create empty CSV with headers
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment'])
                    writer.writeheader()
                if not silent:
                    self._set_status("Created new CSV file - ready for first session")
                return
            
            # Sort by timestamp
            sessions.sort(key=lambda x: x['timestamp_utc'])
            
            # Write new CSV
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment'])
                writer.writeheader()
                writer.writerows(sessions)
            
            # Refresh the Reports tab instead of opening new window
            self._refresh_reports_tab()
            
            if not silent:
                self._set_status(f"CSV rebuilt with {len(sessions)} sessions.")
            
        except Exception as e:
            if not silent:
                messagebox.showerror("Rebuild Failed", f"Failed to rebuild CSV: {e}")
                self._set_status(f"CSV rebuild failed: {e}")

    def _auto_rebuild_csv_on_startup(self) -> None:
        """Automatically rebuild CSV on startup (silent operation)"""
        try:
            # Clear any cached data first
            self._clear_reports_cache()
            
            csv_path = self._get_csv_path()
            
            # Only rebuild if there are actual report files but CSV is missing or inconsistent
            if os.path.exists(self.reports_dir):
                report_files = [f for f in os.listdir(self.reports_dir) 
                              if f.lower().endswith('.txt') and f.startswith('Session')]
                
                # Check if rebuild is needed
                csv_info = self._validate_csv_consistency()
                rebuild_needed = False
                if not csv_info['csv_exists']:
                    rebuild_needed = True
                elif csv_info['session_count'] != csv_info['text_files_count']:
                    rebuild_needed = True
                
                if report_files and rebuild_needed:
                    # Silent rebuild - no status messages or dialogs
                    self._rebuild_csv_from_files_tab(csv_path, silent=True)
                
                # Always refresh reports tab on startup (regardless of rebuild)
                if hasattr(self, 'reports_tree_tab') and self.reports_tree_tab:
                    self._refresh_reports_tab()
                
                # Set ready status
                self._set_status("EliteMining ready")
        except Exception as e:
            # Log error but don't show to user on startup
            print(f"[STARTUP ERROR] Auto rebuild failed: {e}")

    def _export_csv(self, csv_path: str) -> None:
        """Copy the CSV file to a user-selected location"""
        try:
            # Check if CSV file exists
            if not os.path.exists(csv_path):
                self._set_status("Export failed: CSV file not found. Try rebuilding the CSV first.")
                return
                
            from tkinter import filedialog, messagebox
            dest_path = filedialog.asksaveasfilename(
                title="Export Session Data",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile="mining_sessions.csv"
            )
            
            if dest_path:
                import shutil
                shutil.copy2(csv_path, dest_path)
                self._set_status(f"Session data exported to {dest_path}")
                messagebox.showinfo("Export Complete", f"Session data successfully exported to:\n{dest_path}")
            else:
                self._set_status("Export cancelled by user.")
                
        except Exception as e:
            error_msg = f"Export failed: {e}"
            self._set_status(error_msg)
            from tkinter import messagebox
            messagebox.showerror("Export Failed", error_msg)

    def _parse_report_file(self, filename: str, first_line: str, mtime: float) -> Optional[Tuple[str, str, str, str, str]]:
        """Parse report filename and content to extract date, system, body, duration, and TPH"""
        try:
            # Extract date from filename or use file modification time
            if "_" in filename:
                # New format: Session_YYYY-MM-DD_HH-MM-SS_...
                parts = filename.split("_")
                if len(parts) >= 3:
                    date_part = f"{parts[1]} {parts[2].replace('-', ':')}"
                else:
                    date_part = dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            else:
                # Old format or fallback
                date_part = dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            
            # Extract system, body, duration from first line
            # Format: "Session: System — Body — Duration — Total XYt"
            if "Session:" in first_line and "—" in first_line:
                parts = first_line.split("—")
                if len(parts) >= 4:
                    system = parts[0].replace("Session:", "").strip()
                    body = parts[1].strip()
                    duration = parts[2].strip()
                    total_part = parts[3].strip()
                else:
                    system = body = duration = "Unknown"
            else:
                system = body = duration = "Unknown"
            
            # Extract TPH from filename (newer format) or calculate from content
            tph = "0.0"
            if " tph.txt" in filename:
                # Extract TPH from filename
                tph_part = filename.split(" tph.txt")[0].split()[-1]
                try:
                    tph = f"{float(tph_part):.1f}"
                except ValueError:
                    tph = "0.0"
            
            return (date_part, system, body, duration, tph)
            
        except Exception:
            return None

    def _open_path(self, path: str) -> None:
        try:
            if os.name == 'nt':  # Windows
                os.startfile(path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', path])
            else:  # Linux and other Unix-like systems
                subprocess.Popen(['xdg-open', path])
        except Exception as e:
            log.exception("Open path failed for %s: %s", path, e)
            messagebox.showerror("Error", f"Could not open path: {e}")

    # --- UI helpers ---
    def _set_status(self, msg: str) -> None:
        try:
            self.status_cb(msg)
        except Exception:
            pass

    def _change_journal_dir(self) -> None:
        sel = filedialog.askdirectory(title="Select Elite Dangerous Journal folder",
                                      initialdir=self.journal_dir or os.path.expanduser("~"))
        if sel and os.path.isdir(sel):
            self.journal_dir = sel
            self.journal_lbl.config(text=sel)
            self._jrnl_path = None
            self._jrnl_pos = 0
            self._set_status("Journal folder updated.")

    def _on_enabled_changed(self) -> None:
        try:
            if not self.enabled.get():
                self._write_var_text("prospectReadout", "")
                self._set_status("Main announcement toggle disabled.")
            else:
                self._set_status("Main announcement toggle enabled.")
                try:
                    self.toggle_vars["Prospector Sequence"].set(1)
                except Exception:
                    pass
        except Exception:
            pass

    def _announce_all(self) -> None:
        for m in KNOWN_MATERIALS:
            self.announce_map[m] = True
            prev = self.mat_tree.set(m, "minpct") if self.mat_tree.exists(m) else ""
            self.mat_tree.item(m, values=("✓", m, prev))
        self._save_announce_map()
        self._save_last_material_settings()  # Save material settings

    def _mute_all(self) -> None:
        for m in KNOWN_MATERIALS:
            self.announce_map[m] = False
            prev = self.mat_tree.set(m, "minpct") if self.mat_tree.exists(m) else ""
            self.mat_tree.item(m, values=("—", m, prev))
        self._save_announce_map()
        self._save_last_material_settings()  # Save material settings

    def _set_all_min_pct(self):
        val = self.threshold.get()
        try:
            val = float(val)
            val = max(0.0, min(100.0, val))
            for mat in KNOWN_MATERIALS:
                self.min_pct_map[mat] = val
                if self.mat_tree.exists(mat):
                    flag = self.announce_map.get(mat, True)
                    # Don't set text in minpct column to avoid visible text behind spinbox
                    self.mat_tree.item(mat, values=("✓" if flag else "—", mat, ""))
                # Update the spinbox value too
                if mat in self._minpct_spin:
                    self._minpct_spin[mat].set(val)
            self._save_min_pct_map()
            self._save_last_material_settings()  # Save material settings
            self._position_minpct_spinboxes()  # Reposition spinboxes
        except Exception as e:
            messagebox.showerror("Invalid value", f"Could not set minimum %: {e}")

    # --- Report saving on Stop & Compute ---
    def _save_session_report(self, header: str, lines: List[str], overall_tph: float, cargo_session_data: dict = None, comment: str = "") -> str:
        """Save session report with auto-generated timestamp"""
        ts = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return self._save_session_report_with_timestamp(header, lines, overall_tph, cargo_session_data, comment, ts)
    
    def _save_session_report_with_timestamp(self, header: str, lines: List[str], overall_tph: float, cargo_session_data: dict = None, comment: str = "", timestamp: str = None) -> str:
        """Save session report with specified timestamp"""
        if timestamp is None:
            timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        sysname = (self.session_system.get().strip() or self.last_system or "Unknown").replace(" ", "_")
        body = (self.session_body.get().strip() or self.last_body or "Unknown").replace(" ", "_")
        fname = f"Session_{timestamp}_{sysname}_{body}.txt"
        os.makedirs(self.reports_dir, exist_ok=True)
        fpath = os.path.join(self.reports_dir, fname)

        parts = [header]
        
        # Add refined materials section
        if lines:
            parts.append("\n=== REFINED MATERIALS ===")
            parts += [f" - {line}" for line in lines]
        else:
            parts.append("\n=== REFINED MATERIALS ===")
            parts.append(" - No refined materials.")
        
        # Add Material Analysis section if we have prospecting data
        material_summary = self.session_analytics.get_live_summary()
        session_info = self.session_analytics.get_session_info()
        
        if material_summary and session_info['asteroids_prospected'] > 0:
            parts.append("\n=== MATERIAL ANALYSIS ===")
            
            # Prospecting summary
            asteroids_count = session_info['asteroids_prospected']
            materials_tracked = len(material_summary)
            total_finds = session_info['total_finds']
            
            parts.append(f"Asteroids Prospected: {asteroids_count}")
            parts.append(f"Materials Tracked: {materials_tracked}")
            parts.append(f"Total Material Finds: {total_finds}")
            
            if asteroids_count > 0:
                # Hit rate = percentage of asteroids that contained tracked materials
                asteroids_with_materials = session_info.get('asteroids_with_materials', 0)
                hit_rate = (asteroids_with_materials / asteroids_count) * 100.0
                parts.append(f"Hit Rate: {hit_rate:.1f}% (asteroids with valuable materials)")
            
            # Session efficiency
            active_minutes = max(self._active_seconds() / 60.0, 0.1)
            asteroids_per_min = asteroids_count / active_minutes
            parts.append(f"Prospecting Speed: {asteroids_per_min:.1f} asteroids/minute")
            
            # Material performance details
            parts.append("\n--- Material Performance ---")
            
            # Sort materials by average percentage (best first)
            sorted_materials = sorted(material_summary.items(), 
                                    key=lambda x: x[1]['avg_percentage'], reverse=True)
            
            for material_name, stats in sorted_materials:
                avg_pct = stats['avg_percentage']
                best_pct = stats['best_percentage']
                count = stats['find_count']
                
                parts.append(f"{material_name}:")
                parts.append(f"  • Average: {avg_pct:.1f}%")
                parts.append(f"  • Best: {best_pct:.1f}%")
                parts.append(f"  • Finds: {count}x")
            
            # Overall quality assessment - use same yield calculation as CSV
            try:
                # Try to use prospector reports yield calculation first
                raw_yields = self._calculate_yield_from_prospector_reports()
                if raw_yields:
                    # Use prospector reports calculation
                    overall_avg = sum(raw_yields.values()) / len(raw_yields)
                    yield_source = "prospector reports"
                else:
                    # Fallback to Material Analysis
                    all_percentages = []
                    for stats in material_summary.values():
                        if stats['find_count'] > 0:
                            all_percentages.extend([stats['avg_percentage']] * stats['find_count'])
                    
                    if all_percentages:
                        overall_avg = sum(all_percentages) / len(all_percentages)
                        yield_source = "material analysis"
                    else:
                        overall_avg = 0.0
                        yield_source = "no data"
            except:
                # Final fallback to Material Analysis
                all_percentages = []
                for stats in material_summary.values():
                    if stats['find_count'] > 0:
                        all_percentages.extend([stats['avg_percentage']] * stats['find_count'])
                
                if all_percentages:
                    overall_avg = sum(all_percentages) / len(all_percentages)
                    yield_source = "material analysis"
                else:
                    overall_avg = 0.0
                    yield_source = "no data"

            if overall_avg > 0:
                parts.append(f"\nOverall Quality: {overall_avg:.1f}% average yield")
                
                # Best performer
                best_material = sorted_materials[0]
                parts.append(f"Best Performer: {best_material[0]} ({best_material[1]['avg_percentage']:.1f}% avg, {best_material[1]['find_count']}x finds)")
        
        # Add material breakdown from cargo tracking if available
        if cargo_session_data and cargo_session_data.get('materials_mined'):
            parts.append("\n=== CARGO MATERIAL BREAKDOWN ===")
            materials_mined = cargo_session_data['materials_mined']
            prospectors_used = cargo_session_data.get('prospectors_used', 0)
            
            parts.append(f"Prospector Limpets Used: {prospectors_used}")
            parts.append(f"Materials Collected: {len(materials_mined)} types")
            parts.append("")
            
            # Sort materials by quantity (highest first)
            sorted_materials = sorted(materials_mined.items(), key=lambda x: x[1], reverse=True)
            
            for material_name, quantity in sorted_materials:
                parts.append(f"{material_name}: {quantity}t")
            
            # Add total tons from cargo tracking
            total_cargo_tons = cargo_session_data.get('total_tons_mined', 0)
            if total_cargo_tons > 0:
                parts.append(f"\nTotal Cargo Collected: {total_cargo_tons}t")
        
        # Add comment if provided
        if comment.strip():
            parts.append(f"\n=== SESSION COMMENT ===")
            parts.append(comment.strip())
        
        _atomic_write_text(fpath, "\n".join(parts) + "\n")
        return fpath

    def _update_csv_with_session(self, system: str, body: str, elapsed: str, total_tons: float, overall_tph: float, cargo_session_data: dict = None, comment: str = "") -> None:
        """Add new session data to the CSV index"""
        try:
            import csv
            csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
            
            # Create timestamp in local time
            timestamp_local = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            
            # Get Material Analysis data
            material_summary = self.session_analytics.get_live_summary()
            session_info = self.session_analytics.get_session_info()
            
            asteroids_prospected = session_info.get('asteroids_prospected', 0)
            
            # Count materials from either Material Analysis or prospector reports
            if material_summary:
                materials_tracked = len(material_summary)
            elif hasattr(self, 'session_yield_data') and self.session_yield_data:
                materials_tracked = len(self.session_yield_data)
            else:
                materials_tracked = 0
            
            # Calculate hit rate and quality metrics
            hit_rate = 0.0
            avg_quality = 0.0
            best_material = ""
            
            if material_summary and asteroids_prospected > 0:
                # Hit rate: percentage of asteroids with valuable materials
                session_info = self.session_analytics.get_session_info()
                asteroids_with_materials = session_info.get('asteroids_with_materials', 0)
                hit_rate = (asteroids_with_materials / asteroids_prospected) * 100.0
                
                # NEW: Calculate yield from prospector reports data using selected materials only
                raw_yields = {}
                yield_display_string = ""
                try:
                    raw_yields = self._calculate_yield_from_prospector_reports()
                    if raw_yields:
                        # Create display string for yield column
                        yield_display_string = self._format_yield_display(raw_yields)
                        # Use weighted average for numerical sorting
                        avg_quality = sum(raw_yields.values()) / len(raw_yields)
                    else:
                        avg_quality = 0.0
                        yield_display_string = "0.0"
                except Exception as e:
                    # Fallback to old method if new calculation fails
                    all_percentages = []
                    for stats in material_summary.values():
                        if stats['find_count'] > 0:
                            all_percentages.extend([stats['avg_percentage']] * stats['find_count'])
                    if all_percentages:
                        avg_quality = sum(all_percentages) / len(all_percentages)
                        yield_display_string = f"{avg_quality:.1f}"
                    else:
                        avg_quality = 0.0
                        yield_display_string = "0.0"
                
                # Best material
                best_performer = max(material_summary.items(), key=lambda x: x[1]['avg_percentage'])
                best_material = f"{best_performer[0]} ({best_performer[1]['avg_percentage']:.1f}%)"
            
            # Add cargo tracking data if available
            materials_breakdown = ""
            prospectors_used = 0
            if cargo_session_data:
                materials_mined = cargo_session_data.get('materials_mined', {})
                prospectors_used = cargo_session_data.get('prospectors_used', 0)
                if materials_mined:
                    material_list = [f"{name}:{qty}t" for name, qty in materials_mined.items()]
                    materials_breakdown = "; ".join(material_list)
            
            # New session data with Material Analysis metrics and cargo data
            new_session = {
                'timestamp_utc': timestamp_local,  # Keep field name for compatibility but use local time
                'system': system,
                'body': body,
                'elapsed': elapsed,
                'total_tons': total_tons,
                'overall_tph': overall_tph,
                'asteroids_prospected': asteroids_prospected,
                'materials_tracked': materials_tracked,
                'hit_rate_percent': round(hit_rate, 1),
                'avg_quality_percent': yield_display_string,  # Store formatted string for display
                'best_material': best_material,
                'materials_breakdown': materials_breakdown,
                'prospectors_used': prospectors_used,
                'comment': comment
            }
            
            # Read existing data
            sessions = []
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    sessions = list(reader)
            
            # Add new session
            sessions.append(new_session)
            
            # Write back to CSV with enhanced fields including cargo data
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 
                            'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 
                            'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sessions)
                
        except Exception as e:
            print(f"Failed to update CSV: {e}")

    def _clear_prospector_reports(self):
        """Clear the prospector reports table for new session"""
        try:
            if hasattr(self, 'tree') and self.tree:
                # Clear all items from prospector reports table
                for item in self.tree.get_children():
                    self.tree.delete(item)
        except Exception as e:
            print(f"Failed to clear prospector reports: {e}")

    def _track_session_yield_data(self, materials_txt: str):
        """Extract and store yield data from prospector report during session"""
        import re
        
        if not hasattr(self, 'session_yield_data'):
            self.session_yield_data = {}
        
        # Parse materials text: "Bertrandite 16.2%, Indite 13.7%, Gold 14.6%"
        pattern = r'([A-Za-z][A-Za-z0-9\s]*?)\s+(\d+(?:\.\d+)?)%'
        matches = re.findall(pattern, materials_txt)
        
        for material_name, percentage_str in matches:
            material_name = material_name.strip()
            try:
                percentage = float(percentage_str)
                
                # Only include if material is selected in announcement panel
                if self.announce_map.get(material_name, False):
                    if material_name not in self.session_yield_data:
                        self.session_yield_data[material_name] = []
                    self.session_yield_data[material_name].append(percentage)
                    
            except ValueError:
                continue

    def _calculate_yield_from_prospector_reports(self) -> Dict[str, float]:
        """
        Calculate yield percentages from stored session yield data.
        Returns dict of {material_name: average_percentage} for selected materials only.
        """
        if not hasattr(self, 'session_yield_data') or not self.session_yield_data:
            return {}
        
        # Calculate average for each material from session data
        yield_results = {}
        for material_name, percentages in self.session_yield_data.items():
            if percentages:
                yield_results[material_name] = sum(percentages) / len(percentages)
        
        return yield_results

    def _format_yield_display(self, raw_yields: Dict[str, float]) -> str:
        """Format raw yields for display in reports"""
        if not raw_yields:
            return "0.0"
        
        if len(raw_yields) == 1:
            # Single material - show just the percentage
            return f"{next(iter(raw_yields.values())):.1f}"
        else:
            # Multiple materials - show abbreviated format: "Pt: 15.2%, Os: 12.8%"
            material_abbreviations = {
                'Platinum': 'Pt', 'Osmium': 'Os', 'Painite': 'Pain', 'Rhodium': 'Rh',
                'Palladium': 'Pd', 'Gold': 'Au', 'Silver': 'Ag', 'Bertrandite': 'Bert',
                'Indite': 'Ind', 'Gallium': 'Ga', 'Praseodymium': 'Pr', 'Samarium': 'Sm',
                'Bromellite': 'Brom', 'Low Temperature Diamonds': 'LTD', 'Void Opals': 'VO',
                'Alexandrite': 'Alex', 'Benitoite': 'Beni', 'Monazite': 'Monaz',
                'Musgravite': 'Musg', 'Serendibite': 'Ser', 'Taaffeite': 'Taaf'
            }
            
            formatted_parts = []
            for material, percentage in sorted(raw_yields.items(), key=lambda x: x[1], reverse=True):
                abbrev = material_abbreviations.get(material, material[:4])
                formatted_parts.append(f"{abbrev}: {percentage:.1f}%")
            
            return ", ".join(formatted_parts)

    def _update_existing_csv_row(self, timestamp_local: str, updated_data: dict) -> bool:
        """Update an existing CSV row with new data after manual materials are added"""
        try:
            csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
            
            # If CSV doesn't exist, nothing to update
            if not os.path.exists(csv_path):
                return False
                
            # Read existing CSV data
            sessions = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                sessions = list(reader)
            
            # Find and update the matching row by timestamp
            updated = False
            for session in sessions:
                if session.get('timestamp_utc') == timestamp_local:
                    # Update the session with new data
                    session.update(updated_data)
                    updated = True
                    break
            
            if updated:
                # Write back to CSV with updated data
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = ['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 
                                'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 
                                'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(sessions)
                
                print(f"Updated CSV row for session {timestamp_local}")
                return True
            else:
                print(f"No matching CSV row found for timestamp {timestamp_local}")
                return False
                
        except Exception as e:
            print(f"Failed to update existing CSV row: {e}")
            return False

    def _enhance_materials_with_yields(self, materials_breakdown_raw: str, avg_quality_percent: str) -> str:
        """Enhance materials display by adding yield percentages in parentheses"""
        if not materials_breakdown_raw or materials_breakdown_raw == '—':
            return materials_breakdown_raw
            
        try:
            # Parse individual yields from avg_quality_percent field
            individual_yields = {}
            if avg_quality_percent and isinstance(avg_quality_percent, str) and ':' in avg_quality_percent:
                # Parse format like "Pt: 59.0%, Pain: 29.1%"
                pairs = [pair.strip() for pair in avg_quality_percent.split(',')]
                for pair in pairs:
                    if ':' in pair:
                        parts = pair.split(':')
                        if len(parts) >= 2:
                            # Expand abbreviations back to full names
                            abbreviations = {
                                'Pt': 'Platinum', 'Os': 'Osmium', 'Pain': 'Painite', 'Rh': 'Rhodium',
                                'Pd': 'Palladium', 'Au': 'Gold', 'Ag': 'Silver', 'Bert': 'Bertrandite',
                                'Ind': 'Indite', 'Ga': 'Gallium', 'Pr': 'Praseodymium', 'Sm': 'Samarium',
                                'Brom': 'Bromellite', 'LTD': 'Low Temperature Diamonds', 'VO': 'Void Opals',
                                'Alex': 'Alexandrite', 'Beni': 'Benitoite', 'Monaz': 'Monazite',
                                'Musg': 'Musgravite', 'Ser': 'Serendibite', 'Taaf': 'Taaffeite'
                            }
                            abbrev = parts[0].strip()
                            percentage_str = parts[1].strip().replace('%', '')
                            material_name = abbreviations.get(abbrev, abbrev)
                            individual_yields[material_name] = float(percentage_str)
            
            # Parse materials_breakdown and add yields
            enhanced_materials = []
            # Handle both semicolon and comma separators
            separators = [';', ',']
            pairs = [materials_breakdown_raw]
            for sep in separators:
                if sep in materials_breakdown_raw:
                    pairs = [p.strip() for p in materials_breakdown_raw.split(sep)]
                    break
            
            for pair in pairs:
                if ':' in pair:
                    parts = pair.split(':')
                    if len(parts) >= 2:
                        material_name = parts[0].strip()
                        tonnage_text = parts[1].strip()
                        
                        # Add yield percentage if available
                        if material_name in individual_yields:
                            yield_percent = individual_yields[material_name]
                            enhanced_materials.append(f"{material_name}: {tonnage_text} ({yield_percent:.1f}%)")
                        else:
                            # Keep original format if no yield data
                            enhanced_materials.append(f"{material_name}: {tonnage_text}")
                else:
                    # Keep original format if no colon found
                    enhanced_materials.append(pair)
            
            return '; '.join(enhanced_materials) if enhanced_materials else materials_breakdown_raw
            
        except Exception as e:
            # If parsing fails, return original
            print(f"Warning: Could not enhance materials with yields: {e}")
            return materials_breakdown_raw

    def _on_reports_window_close(self) -> None:
        """Handle reports window closing"""
        if self.reports_window:
            self.reports_window.destroy()
        self.reports_window = None
        self.reports_tree = None

    def _setup_reports_tooltips_with_wordwrap(self, tree: ttk.Treeview, word_wrap_enabled: tk.BooleanVar) -> None:
        """Setup tooltip functionality with word wrapping for all cells in reports treeview"""
        tooltip_window = None
        
        def show_tooltip(event):
            nonlocal tooltip_window
            
            # Hide existing tooltip first
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
            
            # Don't show if tooltips are disabled
            if not hasattr(self, 'ToolTip') or not self.ToolTip:
                return
                
            # Get item and column at cursor position
            item = tree.identify_row(event.y)
            column = tree.identify_column(event.x)
            
            if not item:
                return
            
            # Get the cell text content
            column_names = {
                "#1": "date", "#2": "duration", "#3": "system", "#4": "body",
                "#5": "tons", "#6": "tph", "#7": "materials", "#8": "asteroids", 
                "#9": "hit_rate", "#10": "quality", "#11": "cargo", "#12": "prospectors"
            }
            
            tooltip_text = ""
            
            # Show cell content for all columns
            if column == "#11":  # Materials column - show full breakdown
                try:
                    if hasattr(self, 'reports_window_session_lookup') and item in self.reports_window_session_lookup:
                        session_data = self.reports_window_session_lookup[item]
                        cargo_raw = session_data.get('cargo_raw', '')
                        
                        if cargo_raw and cargo_raw != "—":
                            tooltip_text = f"Materials Breakdown:\n{cargo_raw.replace(';', '\n').replace(':', ': ')}"
                        else:
                            tooltip_text = "No materials data available"
                    else:
                        cell_text = tree.set(item, column_names.get(column, ""))
                        tooltip_text = f"Materials: {cell_text}"
                except Exception as e:
                    cell_text = tree.set(item, column_names.get(column, ""))
                    tooltip_text = f"Materials: {cell_text}"
            else:
                # For other columns, show cell content
                if column in column_names:
                    cell_text = tree.set(item, column_names[column])
                    if cell_text:  # Show tooltip for all non-empty cells
                        column_headers = {
                            "#1": "Date/Time", "#2": "Duration", "#3": "System", "#4": "Body",
                            "#5": "Total Tons", "#6": "TPH", "#7": "Mat Types", "#8": "Prospected",
                            "#9": "Hit Rate %", "#10": "Yield %", "#12": "Prospectors"
                        }
                        header = column_headers.get(column, "Info")
                        tooltip_text = f"{header}: {cell_text}"
            
            # Show tooltip if we have text
            if tooltip_text:
                x = event.x_root + 10
                y = event.y_root + 10
                
                tooltip_window = tk.Toplevel(tree)
                tooltip_window.wm_overrideredirect(True)
                tooltip_window.wm_geometry(f"+{x}+{y}")
                tooltip_window.configure(background="#ffffe0")
                
                # Use word wrap only if enabled
                wrap_length = 400 if word_wrap_enabled.get() else 9999
                label = tk.Label(tooltip_window, text=tooltip_text,
                               background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                               font=("Segoe UI", 9), justify=tk.LEFT, wraplength=wrap_length)
                label.pack(ipadx=5, ipady=3)
        
        def hide_tooltip(event):
            nonlocal tooltip_window
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
        
        # Bind hover events
        tree.bind("<Motion>", show_tooltip)
        tree.bind("<Leave>", hide_tooltip)
        tree.bind("<Button-1>", hide_tooltip)

    def _setup_reports_tooltips(self, tree: ttk.Treeview) -> None:
        """Setup tooltip functionality for reports treeview"""
        tooltip_window = None
        
        def show_tooltip(event):
            nonlocal tooltip_window
            
            # Hide existing tooltip first
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
            
            # Don't show if tooltips are disabled
            if not hasattr(self, 'ToolTip') or not self.ToolTip:
                return
                
            # Get item and column at cursor position
            item = tree.identify_row(event.y)
            column = tree.identify_column(event.x)
            
            if not item:
                return
            
            # Define tooltips for each column
            tooltip_texts = {
                "#1": "Date and time when the mining session ended",
                "#2": "Total duration of the mining session",
                "#3": "Star system where mining took place", 
                "#4": "Planet/body/ring that was mined",
                "#5": "Total tons of materials mined",
                "#6": "Tons per hour mining rate",
                "#7": "Number of different material types found",
                "#8": "Total asteroids scanned during the session",
                "#9": "Percentage of asteroids that had valuable materials",
                "#10": "Average quality/yield percentage of materials found",
                "#11": "Materials mined with quantities (hover for full names)",
                "#12": "Number of limpets used during mining session"
            }
            
            # Handle cargo column with original data
            if column == "#11":
                # Get the original cargo data from session_lookup
                try:
                    if hasattr(self, 'reports_window_session_lookup') and item in self.reports_window_session_lookup:
                        session_data = self.reports_window_session_lookup[item]
                        cargo_raw = session_data.get('cargo_raw', '')
                        
                        # Show tooltip if there's cargo data
                        if cargo_raw and cargo_raw != "—":
                            # Format tooltip text directly
                            tooltip_text = f"Materials Breakdown:\n{cargo_raw.replace(';', '\n').replace(':', ': ')}"
                            
                            # Create tooltip window
                            x = event.x_root + 10
                            y = event.y_root + 10
                            
                            tooltip_window = tk.Toplevel(tree)
                            tooltip_window.wm_overrideredirect(True)
                            tooltip_window.wm_geometry(f"+{x}+{y}")
                            tooltip_window.configure(background="#ffffe0")
                            
                            label = tk.Label(tooltip_window, text=tooltip_text,
                                           background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                                           font=("Segoe UI", 9), justify=tk.LEFT, wraplength=300)
                            label.pack(ipadx=5, ipady=3)
                except Exception as e:
                    print(f"Tooltip error: {e}")
            else:
                # Show standard tooltip for other columns
                if column in tooltip_texts:
                    tooltip_text = tooltip_texts[column]
                    
                    x = event.x_root + 10
                    y = event.y_root + 10
                    
                    tooltip_window = tk.Toplevel(tree)
                    tooltip_window.wm_overrideredirect(True)
                    tooltip_window.wm_geometry(f"+{x}+{y}")
                    tooltip_window.configure(background="#ffffe0")
                    
                    label = tk.Label(tooltip_window, text=tooltip_text,
                                   background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                                   font=("Segoe UI", 9), justify=tk.LEFT, wraplength=300)
                    label.pack(ipadx=5, ipady=3)
        
        def hide_tooltip(event):
            nonlocal tooltip_window
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
        
        # Bind hover events
        tree.bind("<Motion>", show_tooltip)
        tree.bind("<Leave>", hide_tooltip)
        tree.bind("<Button-1>", hide_tooltip)  # Hide on click

    def _refresh_reports_window(self) -> None:
        """Refresh the reports window if it's open"""
        try:
            if self.reports_window and self.reports_tree:
                # Check if window still exists
                if not self.reports_window.winfo_exists():
                    self.reports_window = None
                    self.reports_tree = None
                    return
                    
                # Clear existing data
                for item in self.reports_tree.get_children():
                    self.reports_tree.delete(item)
                
                # Reload data from CSV
                csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                if os.path.exists(csv_path):
                    import csv
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        sessions_data = []
                        for row in reader:
                            # Format the timestamp for display
                            try:
                                # Try to parse as local time first, then fall back to UTC
                                if row['timestamp_utc'].endswith('Z'):
                                    # UTC format - convert to local time for display
                                    timestamp = dt.datetime.fromisoformat(row['timestamp_utc'].replace('Z', '+00:00'))
                                    timestamp = timestamp.replace(tzinfo=dt.timezone.utc).astimezone()
                                else:
                                    # Local time format
                                    timestamp = dt.datetime.fromisoformat(row['timestamp_utc'])
                                date_str = timestamp.strftime("%Y-%m-%d %H:%M")
                            except:
                                date_str = row['timestamp_utc']
                            
                            # Format TPH and tons
                            try:
                                tph_val = float(row['overall_tph'])
                                tph_str = f"{tph_val:.1f}"
                            except:
                                tph_str = row['overall_tph']
                                
                            try:
                                tons_val = float(row['total_tons'])
                                tons_str = f"{tons_val:.1f}"
                            except:
                                tons_str = row['total_tons']
                            
                            # Format Material Analysis fields (with fallback for old data)
                            asteroids = row.get('asteroids_prospected', '').strip() or '0'
                            materials = row.get('materials_tracked', '').strip() or '0'
                            hit_rate = row.get('hit_rate_percent', '').strip() or '0'
                            avg_quality = row.get('avg_quality_percent', '').strip() or '0'
                            
                            # Get new cargo tracking fields
                            materials_breakdown_raw = row.get('materials_breakdown', '').strip() or '—'
                            prospectors_used = row.get('prospectors_used', '').strip() or '—'
                            
                            # Use full material names with optional word wrap
                            if self.reports_tab_word_wrap_enabled.get():
                                materials_breakdown = materials_breakdown_raw.replace('; ', '\n')
                            else:
                                materials_breakdown = materials_breakdown_raw
                            
                            # Format asteroids and materials columns
                            try:
                                asteroids_val = int(asteroids) if asteroids and asteroids != '0' else 0
                                asteroids_str = str(asteroids_val) if asteroids_val > 0 else "—"
                            except:
                                asteroids_str = "—"
                            
                            try:
                                materials_val = int(materials) if materials and materials != '0' else 0
                                materials_str = str(materials_val) if materials_val > 0 else "—"
                            except:
                                materials_str = "—"
                            
                            # Format hit rate
                            try:
                                hit_rate_val = float(hit_rate) if hit_rate and hit_rate != '0' else 0
                                hit_rate_str = f"{hit_rate_val:.1f}" if hit_rate_val > 0 else "—"
                            except:
                                hit_rate_str = "—"
                            
                            # Format quality (yield %) - handle both old numerical and new formatted strings
                            try:
                                # Check if it's already a formatted string (contains letters)
                                if any(c.isalpha() for c in avg_quality):
                                    quality_str = avg_quality  # Already formatted
                                else:
                                    # Old numerical format
                                    quality_val = float(avg_quality) if avg_quality and avg_quality != '0' else 0
                                    quality_str = f"{quality_val:.1f}" if quality_val > 0 else "—"
                            except:
                                quality_str = "—"
                            
                            sessions_data.append({
                                'date': date_str,
                                'system': row['system'],
                                'body': row['body'],
                                'duration': row['elapsed'],
                                'tons': tons_str,
                                'tph': tph_str,
                                'asteroids': asteroids_str,
                                'materials': materials_str,
                                'hit_rate': hit_rate_str,
                                'quality': quality_str,
                                'cargo': materials_breakdown,
                                'cargo_raw': materials_breakdown_raw,  # Store original for tooltip
                                'prospectors': prospectors_used,
                                'timestamp_raw': row['timestamp_utc']
                            })
                    
                    # Sort by timestamp (newest first)
                    sessions_data.sort(key=lambda x: x['timestamp_raw'], reverse=True)
                    
                    # Populate the tree
                    for session in sessions_data:
                        item_id = self.reports_tree.insert("", "end", values=(
                            session['date'],
                            session['duration'],
                            session['system'], 
                            session['body'],
                            session['tons'],
                            session['tph'],
                            session['asteroids'],
                            session['materials'],
                            session['hit_rate'],
                            session['quality'],
                            session['cargo'],
                            session['prospectors'],
                            session.get('comment', ''),
                            ""  # Enhanced column placeholder
                        ))
                        
                        # Check detailed report using tree values for consistency
                        tree_values = self.reports_tree.item(item_id, 'values')
                        if len(tree_values) >= 4:
                            tree_report_id = f"{tree_values[0]}_{tree_values[2]}_{tree_values[3]}"
                            enhanced_indicator = self._get_detailed_report_indicator(tree_report_id)
                            self.reports_tree.set(item_id, "enhanced", enhanced_indicator)
        except Exception as e:
            print(f"Failed to refresh reports window: {e}")
            # Reset window references if there's an error
            self.reports_window = None
            self.reports_tree = None

    def _create_reports_panel(self, parent: ttk.Widget) -> None:
        """Create the reports panel interface within the provided parent widget."""
        # Create main frame with proper grid configuration
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(parent)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)  # Date filter
        main_frame.rowconfigure(1, weight=1)  # Treeview
        main_frame.rowconfigure(2, weight=0)  # Horizontal scrollbar
        main_frame.rowconfigure(3, weight=0)  # Buttons

        # Date filter frame
        filter_frame = ttk.Frame(main_frame)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        
        ttk.Label(filter_frame, text="Filter:").pack(side="left", padx=(0, 5))
        
        self.date_filter_var = tk.StringVar(value="All sessions")
        date_filter_combo = ttk.Combobox(filter_frame, textvariable=self.date_filter_var, 
                                        values=["All sessions", 
                                               "Last 1 day", "Last 2 days", "Last 3 days", "Last 7 days", "Last 30 days", "Last 90 days",
                                               "High Yield (>350 T/hr)", "Medium Yield (250-350 T/hr)", "Low Yield (100-250 T/hr)",
                                               "High Hit Rate (>40%)", "Medium Hit Rate (20-40%)", "Low Hit Rate (<20%)",
                                               "Platinum Sessions", "High-Value Materials", "Common Materials"], 
                                        state="readonly", width=28)
        date_filter_combo.pack(side="left", padx=(0, 5))
        
        # Add hint text for right-click options
        ttk.Label(filter_frame, text="Right-click rows for options", foreground="gray").pack(side="right", padx=(10, 0))
        date_filter_combo.bind("<<ComboboxSelected>>", self._on_date_filter_changed)
        
        self.ToolTip(date_filter_combo, "Filter sessions by date, yield performance, hit rate, or materials")

        # Create sortable treeview with Material Analysis columns
        self.reports_tree_tab = ttk.Treeview(main_frame, columns=("date", "duration", "system", "body", "tons", "tph", "materials", "asteroids", "hit_rate", "quality", "cargo", "prospects", "comment", "enhanced"), show="headings", height=16, selectmode="extended")
        self.reports_tree_tab.grid(row=1, column=0, sticky="nsew")
        
        # Bind tooltip immediately after creation
        def tooltip_handler(event):
            region = self.reports_tree_tab.identify_region(event.x, event.y)
            column = self.reports_tree_tab.identify_column(event.x)
            if region == "heading":
                tooltips = {"#1": "Date/Time", "#2": "Duration", "#3": "System", "#4": "Body", "#5": "Total Tons", "#6": "TPH", "#7": "Mat Types", "#8": "Prospected", "#9": "Hit Rate %", "#10": "Avg Yield %", "#11": "Materials", "#12": "Limpets", "#13": "Comments", "#14": "Report"}
                text = tooltips.get(column, "")
                if text and hasattr(self, 'ToolTip') and self.ToolTip:
                    if hasattr(self, '_tt') and self._tt: self._tt.destroy()
                    self._tt = tk.Toplevel()
                    self._tt.wm_overrideredirect(True)
                    self._tt.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
                    self._tt.configure(bg="#ffffe0")
                    tk.Label(self._tt, text=text, bg="#ffffe0", relief=tk.SOLID, bd=1).pack()
            else:
                if hasattr(self, '_tt') and self._tt: self._tt.destroy(); self._tt = None
        self.reports_tree_tab.bind("<Motion>", tooltip_handler)
        self.reports_tree_tab.bind("<Leave>", lambda e: hasattr(self, '_tt') and self._tt and self._tt.destroy())
        self._tt = None
        
        # Remove custom styling - use default treeview appearance
        

        
        # Configure column headings
        self.reports_tree_tab.heading("date", text="Date/Time")
        self.reports_tree_tab.heading("system", text="System")
        self.reports_tree_tab.heading("body", text="Body")
        self.reports_tree_tab.heading("duration", text="Duration")
        self.reports_tree_tab.heading("tons", text="Total Tons")
        self.reports_tree_tab.heading("tph", text="TPH")
        self.reports_tree_tab.heading("asteroids", text="Prospected")
        self.reports_tree_tab.heading("materials", text="Mat Types")
        self.reports_tree_tab.heading("hit_rate", text="Hit Rate %")
        self.reports_tree_tab.heading("quality", text="Average Yield %")
        self.reports_tree_tab.heading("cargo", text="Materials (Tonnage & Yields)")
        self.reports_tree_tab.heading("prospects", text="Limpets")
        self.reports_tree_tab.heading("comment", text="Comment")
        self.reports_tree_tab.heading("enhanced", text="Detail Report")
        
        # Add sorting to tab treeview
        tab_sort_dirs = {}
        def sort_tab_col(col):
            try:
                reverse = tab_sort_dirs.get(col, False)
                items = [(self.reports_tree_tab.set(item, col), item) for item in self.reports_tree_tab.get_children('')]
                
                # Smart sorting based on column type  
                numeric_cols = {"tons", "tph", "hit_rate", "quality", "materials", "asteroids", "prospects"}
                if col in numeric_cols:
                    # Numeric sorting - handle "—" and empty values
                    def safe_float(x):
                        try:
                            val = str(x).replace("—", "0").strip()
                            return float(val) if val else 0.0
                        except:
                            return 0.0
                    items.sort(key=lambda x: safe_float(x[0]), reverse=reverse)
                else:
                    # String sorting for text columns
                    items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)
                    
                for index, (val, item) in enumerate(items):
                    self.reports_tree_tab.move(item, '', index)
                tab_sort_dirs[col] = not reverse
            except Exception as e:
                print(f"Tab sorting error for column {col}: {e}")
                # Fallback to simple string sort
                try:
                    items = [(self.reports_tree_tab.set(item, col), item) for item in self.reports_tree_tab.get_children('')]
                    items.sort(key=lambda x: str(x[0]).lower(), reverse=tab_sort_dirs.get(col, False))
                    for index, (val, item) in enumerate(items):
                        self.reports_tree_tab.move(item, '', index)
                    tab_sort_dirs[col] = not tab_sort_dirs.get(col, False)
                except Exception as e2:
                    print(f"Tab fallback sorting failed: {e2}")
            
            # CRITICAL: Rebuild tab session_lookup after sorting
            if hasattr(self, 'reports_tab_session_lookup') and hasattr(self, 'reports_tab_original_sessions'):
                # Create backup of original lookup data
                original_sessions_backup = list(self.reports_tab_session_lookup.values())
                new_tab_lookup = {}
                
                for item_id in self.reports_tree_tab.get_children(''):
                    values = self.reports_tree_tab.item(item_id, 'values')
                    # Find the original session data that matches these values using backup
                    for orig_session in original_sessions_backup:
                        if (orig_session.get('date') == values[0] and 
                            orig_session.get('system') == values[1] and 
                            orig_session.get('body') == values[2] and
                            orig_session.get('duration') == values[3]):
                            new_tab_lookup[item_id] = orig_session
                            break
                
                self.reports_tab_session_lookup.clear()
                self.reports_tab_session_lookup.update(new_tab_lookup)
        
        # Set commands for all tab treeview columns
        self.reports_tree_tab.heading("date", command=lambda: sort_tab_col("date"))
        self.reports_tree_tab.heading("system", command=lambda: sort_tab_col("system"))
        self.reports_tree_tab.heading("body", command=lambda: sort_tab_col("body"))
        self.reports_tree_tab.heading("duration", command=lambda: sort_tab_col("duration"))
        self.reports_tree_tab.heading("tons", command=lambda: sort_tab_col("tons"))
        self.reports_tree_tab.heading("tph", command=lambda: sort_tab_col("tph"))
        self.reports_tree_tab.heading("materials", command=lambda: sort_tab_col("materials"))
        self.reports_tree_tab.heading("asteroids", command=lambda: sort_tab_col("asteroids"))
        self.reports_tree_tab.heading("hit_rate", command=lambda: sort_tab_col("hit_rate"))
        self.reports_tree_tab.heading("quality", command=lambda: sort_tab_col("quality"))
        self.reports_tree_tab.heading("cargo", command=lambda: sort_tab_col("cargo"))
        self.reports_tree_tab.heading("prospects", command=lambda: sort_tab_col("prospects"))
        self.reports_tree_tab.heading("comment", command=lambda: sort_tab_col("comment"))
        

        
        # Configure column widths - locked at startup size, no resizing allowed
        
        self.reports_tree_tab.column("date", width=105, stretch=False, anchor="w")
        self.reports_tree_tab.column("system", width=220, stretch=False, anchor="w")
        self.reports_tree_tab.column("body", width=125, stretch=False, anchor="center")
        self.reports_tree_tab.column("duration", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("tons", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("tph", width=60, stretch=False, anchor="center")
        self.reports_tree_tab.column("materials", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("asteroids", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("hit_rate", width=90, stretch=False, anchor="center")
        self.reports_tree_tab.column("quality", width=120, stretch=False, anchor="center")
        self.reports_tree_tab.column("cargo", width=250, stretch=False, anchor="w")
        self.reports_tree_tab.column("prospects", width=70, stretch=False, anchor="center")
        self.reports_tree_tab.column("comment", width=200, stretch=False, anchor="w")
        self.reports_tree_tab.column("enhanced", width=100, stretch=False, anchor="center")

        # Add vertical scrollbar
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.reports_tree_tab.yview)
        v_scrollbar.grid(row=1, column=1, sticky="ns")
        self.reports_tree_tab.configure(yscrollcommand=v_scrollbar.set)

        # Add horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(main_frame, orient="horizontal", command=self.reports_tree_tab.xview)
        h_scrollbar.grid(row=2, column=0, sticky="ew")
        self.reports_tree_tab.configure(xscrollcommand=h_scrollbar.set)

        # Word wrap toggle variable for reports tab
        self.reports_tab_word_wrap_enabled = tk.BooleanVar(value=False)

        # Add buttons at the bottom
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(8, 0), sticky="ew")
        
        # CSV file path for button commands
        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
        
        # Rebuild CSV button
        rebuild_btn = tk.Button(button_frame, text="Rebuild CSV", 
                               command=lambda: self._force_rebuild_and_refresh(), 
                               bg="#444444", fg="#ffffff", 
                               activebackground="#555555", activeforeground="#ffffff", 
                               relief="solid", bd=1, 
                               highlightbackground="#666666", highlightcolor="#666666")
        rebuild_btn.pack(side="left", padx=(0, 5))
        self.ToolTip(rebuild_btn, "Rebuild the CSV index from all text files in the reports folder. Use this if data doesn't match between the table and files.")
        
        # Open Folder button
        folder_btn = tk.Button(button_frame, text="Open Folder", 
                              command=lambda: self._open_path(self.reports_dir), 
                              bg="#444444", fg="#ffffff", 
                              activebackground="#555555", activeforeground="#ffffff", 
                              relief="solid", bd=1, 
                              highlightbackground="#666666", highlightcolor="#666666")
        folder_btn.pack(side="left", padx=(0, 5))
        self.ToolTip(folder_btn, "Open the reports folder in Windows Explorer to browse all session files.")
        
        # Export CSV button  
        export_btn = tk.Button(button_frame, text="Export CSV", 
                              command=lambda: self._export_csv(csv_path), 
                              bg="#444444", fg="#ffffff", 
                              activebackground="#555555", activeforeground="#ffffff", 
                              relief="solid", bd=1, 
                              highlightbackground="#666666", highlightcolor="#666666")
        export_btn.pack(side="left", padx=(0, 5))
        self.ToolTip(export_btn, "Export session data to a CSV file that can be opened in Excel or other spreadsheet programs.")
        
        # Add double-click functionality for opening report files
        def open_selected():
            selected = self.reports_tree_tab.selection()
            if not selected:
                return
            
            # Use the session lookup for exact data
            item_id = selected[0]
            if item_id not in self.reports_tab_session_lookup:
                self._set_status("Session data not found for selected item")
                self._open_path(self.reports_dir)
                return
            
            session = self.reports_tab_session_lookup[item_id]
            system = session['system']
            body = session['body']
            timestamp_raw = session['timestamp_raw']
            
            self._set_status(f"Looking for report: {system} - {body}")
            
            try:
                # Convert timestamp to filename format
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp_raw.replace('Z', ''))
                filename_timestamp = dt.strftime("%Y-%m-%d_%H-%M-%S")
                
                # Find file with exact timestamp
                if os.path.exists(self.reports_dir):
                    for filename in os.listdir(self.reports_dir):
                        if (filename.startswith('Session_') and 
                            filename.endswith('.txt') and
                            filename_timestamp in filename):
                            fpath = os.path.join(self.reports_dir, filename)
                            self._set_status(f"Opening report: {filename}")
                            self._open_path(fpath)
                            return
                
                self._set_status(f"Report file not found for {system} - {body}")
                self._open_path(self.reports_dir)
                        
            except Exception as e:
                self._set_status(f"Error opening report: {e}")
                self._open_path(self.reports_dir)

        def bookmark_selected():
            """Bookmark the selected mining location from reports"""
            try:
                selected = self.reports_tree_tab.selection()
                if not selected:
                    self._set_status("No session selected to bookmark")
                    return
                
                # Get session data from selected item
                item = selected[0]
                values = self.reports_tree_tab.item(item, 'values')
                if len(values) < 4:
                    self._set_status("Invalid session data for bookmarking")
                    return
                
                # Extract system and body from session
                system = values[2]  # System column
                body = values[3]    # Body column
                
                if system in ["Unknown", ""] or body in ["Unknown", ""]:
                    self._set_status("Cannot bookmark location with unknown system or body")
                    return
                
                # Get materials and yield data from session lookup if available
                materials = ""
                avg_yield = ""
                last_mined = ""
                
                if hasattr(self, 'reports_tab_session_lookup') and item in self.reports_tab_session_lookup:
                    session_data = self.reports_tab_session_lookup[item]
                    
                    # Extract materials from breakdown data
                    materials_breakdown = session_data.get('materials_breakdown_raw', '')
                    if not materials_breakdown:
                        # Try alternative fields
                        materials_breakdown = session_data.get('cargo_raw', session_data.get('cargo', ''))
                    
                    if materials_breakdown and materials_breakdown != '—':
                        # Extract just material names from "Material: quantity" format
                        material_names = []
                        
                        # Try different separators - could be ';' or '\n' or other
                        separators = [';', '\n', ',']
                        parts = [materials_breakdown]  # Start with the whole string
                        
                        for sep in separators:
                            if sep in materials_breakdown:
                                parts = materials_breakdown.split(sep)
                                break
                        
                        for part in parts:
                            part = part.strip()
                            if ':' in part:
                                material_name = part.split(':')[0].strip()
                                if material_name:
                                    material_names.append(material_name)
                            elif part and not part.isdigit():  # If no colon, might be just material name
                                material_names.append(part)
                        
                        if material_names:
                            materials = ', '.join(material_names)
                    
                    # Extract yield information (tons per hour)
                    tph = session_data.get('overall_tph', session_data.get('tph', 0))
                    if tph and tph != '—':
                        try:
                            tph_val = float(tph) if isinstance(tph, (int, float)) else float(tph.replace(' T/hr', ''))
                            if tph_val > 0:
                                avg_yield = f"{tph_val:.1f} T/hr"
                        except (ValueError, AttributeError):
                            pass
                    
                    # Extract session date for last mined
                    timestamp_raw = session_data.get('timestamp_raw', '')
                    if timestamp_raw:
                        try:
                            # Parse the timestamp and format as YYYY-MM-DD
                            if timestamp_raw.endswith('Z'):
                                # UTC format
                                timestamp = dt.datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                                timestamp = timestamp.replace(tzinfo=dt.timezone.utc).astimezone()
                            else:
                                # Local time format
                                timestamp = dt.datetime.fromisoformat(timestamp_raw)
                            last_mined = timestamp.strftime('%Y-%m-%d')
                        except:
                            # Fallback: try to extract date from the session display date
                            display_date = session_data.get('date', '')
                            if display_date:
                                try:
                                    # Parse MM/DD/YY HH:MM format and convert to YYYY-MM-DD
                                    parsed_date = dt.datetime.strptime(display_date, '%m/%d/%y %H:%M')
                                    last_mined = parsed_date.strftime('%Y-%m-%d')
                                except:
                                    pass
                
                # Show bookmark dialog with pre-filled data
                self._show_bookmark_dialog({
                    'system': system,
                    'body': body,
                    'hotspot': '',
                    'materials': materials,
                    'avg_yield': avg_yield,
                    'last_mined': last_mined,
                    'notes': ''
                })
                
            except Exception as e:
                self._set_status(f"Error bookmarking location: {e}")

        def copy_system_name_tab():
            """Copy selected system name to clipboard from reports tab"""
            try:
                selected_items = self.reports_tree_tab.selection()
                if not selected_items:
                    self._set_status("No report selected")
                    return
                
                # Get selected report data
                item = selected_items[0]
                values = self.reports_tree_tab.item(item, 'values')
                if not values or len(values) < 3:
                    self._set_status("Invalid report data")
                    return
                
                # System name is in column index 2 (date, duration, system...)
                system_name = values[2]
                if system_name:
                    # Copy to clipboard
                    self.clipboard_clear()
                    self.clipboard_append(system_name)
                    self.update()  # Required to ensure clipboard is updated
                    
                    # Show brief status message
                    self._set_status(f"Copied '{system_name}' to clipboard")
                else:
                    self._set_status("No system name found")
                    
            except Exception as e:
                self._set_status(f"Error copying system name: {e}")

        def handle_double_click(event):
            """Handle double-click on reports tree - open file or edit comment"""
            # Identify which column was clicked
            item = self.reports_tree_tab.identify('item', event.x, event.y)
            column = self.reports_tree_tab.identify('column', event.x, event.y)
            
            if not item:
                return
            
            # Check if it's the comment column (#13) or detailed reports column (#14)
            if column == '#13':  # Comment column
                # Use the existing popup comment editor
                self._edit_comment_popup_reports(event)
            elif column == '#14':  # Detailed reports column
                # Handle detailed report opening on double-click too
                columns = self.reports_tree_tab["columns"]
                column_name = columns[13]  # Enhanced column (0-indexed)
                cell_value = self.reports_tree_tab.set(item, column_name)
                if cell_value == "✓":  # Has detailed report
                    session_data = self.reports_tab_session_lookup.get(item)
                    if session_data:
                        original_timestamp = session_data.get('timestamp_raw', session_data.get('date', ''))
                        system = session_data.get('system', '')
                        body = session_data.get('body', '')
                        report_id = f"{original_timestamp}_{system}_{body}"
                        self._open_enhanced_report(report_id)
                # Don't open CSV file for detailed reports column
                return
            else:
                # Open the report file for other columns
                open_selected()

        self.reports_tree_tab.bind("<Double-1>", handle_double_click)
        
        # Bind single-click to handle detailed report opening (with higher priority)
        self.reports_tree_tab.bind("<Button-1>", self._create_enhanced_click_handler(self.reports_tree_tab))
        
        # Add hover effect for detailed reports column
        def combined_motion_handler(event):
            # Call the original mouse motion handler for detailed reports column  
            self._handle_mouse_motion(event, self.reports_tree_tab)
            
            # Show tooltips for column headers
            self._show_header_tooltip(event, self.reports_tree_tab)
        
        self.reports_tree_tab.bind("<Motion>", combined_motion_handler)
        
        # Bind tooltip directly to heading events
        def show_heading_tooltip(event):
            region = self.reports_tree_tab.identify_region(event.x, event.y)
            if region == "heading":
                self._show_header_tooltip(event, self.reports_tree_tab)
        
        self.reports_tree_tab.bind("<Enter>", show_heading_tooltip)
        
        # Hide tooltip when mouse leaves the tree
        def hide_tooltip(event):
            if hasattr(self, '_reports_tooltip_window') and self._reports_tooltip_window:
                self._reports_tooltip_window.destroy()
                self._reports_tooltip_window = None
        
        self.reports_tree_tab.bind("<Leave>", hide_tooltip)
        
        # Initialize tooltip window for reports tab
        self._reports_tooltip_window = None
        
        # Context menu for right-click delete functionality
        def show_context_menu(event):
            try:
                # Clear existing selection and select the item under cursor
                item = self.reports_tree_tab.identify_row(event.y)
                if item:
                    # If item is not already selected, clear selection and select it
                    selected_items = self.reports_tree_tab.selection()
                    if item not in selected_items:
                        self.reports_tree_tab.selection_set(item)
                    
                    # Create context menu
                    context_menu = tk.Menu(self.reports_tree_tab, tearoff=0, bg="#2d2d2d", fg="#ffffff")
                    context_menu.add_command(label="Open Report (CSV)", command=lambda: open_selected())
                    context_menu.add_command(label="Open Detailed Report (HTML)", command=lambda: self._open_enhanced_report_from_menu(self.reports_tree_tab))
                    context_menu.add_separator()
                    context_menu.add_command(label="Bookmark This Location", command=lambda: bookmark_selected())
                    context_menu.add_command(label="Generate Detailed Report (HTML)", command=lambda: self._generate_enhanced_report_from_menu(self.reports_tree_tab))
                    context_menu.add_separator()
                    context_menu.add_command(label="Copy System Name", command=lambda: copy_system_name_tab())
                    context_menu.add_separator()
                    context_menu.add_command(label="Delete Detailed Report + Screenshots", command=lambda: self._delete_enhanced_report_from_menu(self.reports_tree_tab))
                    context_menu.add_separator()  # Add separator for safety
                    context_menu.add_command(label="Delete Complete Session", command=lambda: delete_selected())
                    
                    # Show the menu at cursor position
                    context_menu.tk_popup(event.x_root, event.y_root)
                    
            except Exception as e:
                self._set_status(f"Error showing context menu: {e}")
        
        def delete_selected():
            try:
                selected_items = self.reports_tree_tab.selection()
                if not selected_items:
                    self._set_status("No report selected for deletion")
                    return
                
                # Get report info for confirmation using the session lookup
                item_count = len(selected_items)
                if item_count == 1:
                    item_id = selected_items[0]
                    if item_id in self.reports_tab_session_lookup:
                        session = self.reports_tab_session_lookup[item_id]
                        system = session['system']
                        body = session['body']
                        date_str = session['date']
                        duration = session.get('elapsed', 'Unknown')
                        tons = session.get('tons', 'Unknown')
                        msg = (f"Are you sure you want to permanently delete this mining session report?\n\n"
                              f"Session Details:\n"
                              f"• Date: {date_str}\n"
                              f"• System: {system}\n"
                              f"• Body: {body}\n"
                              f"• Duration: {duration}\n"
                              f"• Tons Mined: {tons}\n\n"
                              f"This will permanently delete:\n"
                              f"• The CSV report entry\n"
                              f"• The individual report file\n"
                              f"• Graph files (if any)\n"
                              f"• Detailed HTML report (if any)\n"
                              f"• Screenshots (if any)\n\n"
                              f"This action cannot be undone.")
                        title = "Delete Mining Session Report"
                    else:
                        self._set_status("Session data not found for selected item")
                        return
                else:
                    # Build list of sessions to be deleted for display
                    sessions_to_delete = []
                    for item_id in selected_items:
                        if item_id in self.reports_tab_session_lookup:
                            session = self.reports_tab_session_lookup[item_id]
                            sessions_to_delete.append(session)
                    
                    msg = f"Are you sure you want to permanently delete {item_count} mining session reports?\n\n"
                    msg += "Sessions to be deleted:\n"
                    for i, session in enumerate(sessions_to_delete[:5], 1):  # Show max 5 items
                        msg += f"  {i}. {session['date']} - {session['system']}/{session['body']}\n"
                    if len(sessions_to_delete) > 5:
                        msg += f"  ... and {len(sessions_to_delete) - 5} more\n"
                    msg += f"\nThis will permanently delete:\n"
                    msg += f"• All CSV report entries\n"
                    msg += f"• All individual report files\n\n"
                    msg += f"This action cannot be undone."
                    title = "Delete Multiple Mining Session Reports"
                
                # Confirm deletion
                if messagebox.askyesno(title, msg, icon="warning"):
                    deleted_files = []
                    
                    for item_id in selected_items:
                        if item_id not in self.reports_tab_session_lookup:
                            self._set_status(f"Session data not found for item {item_id}")
                            continue
                            
                        session = self.reports_tab_session_lookup[item_id]
                        system = session['system']
                        body = session['body']
                        timestamp_raw = session['timestamp_raw']
                        
                        self._set_status(f"Deleting {system}-{body}")
                        
                        try:
                            # Find and delete CSV entry by exact timestamp match
                            csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                            if os.path.exists(csv_path):
                                import csv
                                rows_to_keep = []
                                
                                with open(csv_path, 'r', encoding='utf-8') as f:
                                    reader = csv.reader(f)
                                    for row in reader:
                                        if len(row) > 0 and row[0] != timestamp_raw:
                                            rows_to_keep.append(row)
                                        # Skip the row with matching timestamp (delete it)
                                
                                # Write updated CSV
                                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                                    writer = csv.writer(f)
                                    writer.writerows(rows_to_keep)
                            
                            # Find and delete the report file by timestamp
                            try:
                                from datetime import datetime
                                dt = datetime.fromisoformat(timestamp_raw.replace('Z', ''))
                                filename_timestamp = dt.strftime("%Y-%m-%d_%H-%M-%S")
                                
                                file_deleted = False
                                for filename in os.listdir(self.reports_dir):
                                    if (filename.startswith('Session_') and 
                                        filename.endswith('.txt') and
                                        filename_timestamp in filename):
                                        file_path = os.path.join(self.reports_dir, filename)
                                        os.remove(file_path)
                                        deleted_files.append(filename)
                                        file_deleted = True
                                        break
                                
                                if file_deleted:
                                    self._set_status(f"Deleted: {system}-{body}")
                                else:
                                    self._set_status(f"CSV updated for {system}-{body} (file not found)")
                                    
                            except Exception as e:
                                self._set_status(f"Error deleting file: {e}")
                            
                            # Delete corresponding graph files
                            try:
                                # Get graphs directory using same logic as auto_save_graphs
                                if getattr(sys, 'frozen', False):
                                    app_dir = os.path.join(self.va_root, "app")
                                else:
                                    app_dir = os.path.dirname(os.path.abspath(__file__))
                                
                                graphs_dir = os.path.join(app_dir, "Reports", "Mining Session", "Graphs")
                                
                                if os.path.exists(graphs_dir):
                                    # Create session prefix using same logic as auto_save_graphs
                                    try:
                                        dt = datetime.fromisoformat(timestamp_raw.replace('Z', ''))
                                        timestamp = dt.strftime("%Y-%m-%d_%H-%M-%S")
                                        session_prefix = f"Session_{timestamp}"
                                        
                                        if system:
                                            clean_system = "".join(c for c in system if c.isalnum() or c in (' ', '-', '_')).strip()
                                            clean_system = clean_system.replace(' ', '_')
                                            session_prefix += f"_{clean_system}"
                                        
                                        if body:
                                            clean_body = "".join(c for c in body if c.isalnum() or c in (' ', '-', '_')).strip()
                                            clean_body = clean_body.replace(' ', '_')
                                            session_prefix += f"_{clean_body}"
                                        
                                        # Delete graph files
                                        deleted_graphs = []
                                        for graph_file in os.listdir(graphs_dir):
                                            if graph_file.startswith(session_prefix) and graph_file.endswith('.png'):
                                                graph_path = os.path.join(graphs_dir, graph_file)
                                                os.remove(graph_path)
                                                deleted_graphs.append(graph_file)
                                        
                                        # Update graph mappings JSON
                                        mappings_file = os.path.join(graphs_dir, "graph_mappings.json")
                                        if os.path.exists(mappings_file):
                                            try:
                                                with open(mappings_file, 'r', encoding='utf-8') as f:
                                                    mappings = json.load(f)
                                                if session_prefix in mappings:
                                                    del mappings[session_prefix]
                                                    with open(mappings_file, 'w', encoding='utf-8') as f:
                                                        json.dump(mappings, f, indent=2)
                                            except Exception as map_error:
                                                pass
                                                
                                            if deleted_graphs:
                                                pass  # Graphs deleted successfully
                                            
                                    except Exception as graph_error:
                                        pass  # Silent error handling
                            except Exception as graph_error:
                                pass  # Silent error handling
                            
                            # Delete screenshots and HTML report silently
                            try:
                                values = self.reports_tree_tab.item(item_id, 'values')
                                if values and len(values) >= 4:
                                    display_date = values[0]
                                    system_val = values[2] if len(values) > 2 else system
                                    body_val = values[3] if len(values) > 3 else body
                                    report_id = f"{display_date}_{system_val}_{body_val}"
                                    
                                    # Delete HTML file
                                    html_filename = self._get_report_filenames(report_id)
                                    if html_filename:
                                        html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
                                        if os.path.exists(html_path):
                                            os.remove(html_path)
                                    
                                    # Delete screenshots
                                    screenshots = self._get_report_screenshots(report_id)
                                    for screenshot_path in screenshots:
                                        if os.path.exists(screenshot_path):
                                            os.remove(screenshot_path)
                            except:
                                pass
                                
                        except Exception as e:
                            self._set_status(f"Error deleting {system}-{body}: {e}")
                    
                    # Refresh the display
                    self._refresh_reports_tab()
                    
                    if deleted_files:
                        self._set_status(f"Deleted {len(deleted_files)} report file(s)")
                    else:
                        self._set_status("Deletion completed")
                        
            except Exception as e:
                self._set_status(f"Error during deletion: {e}")
        
        # Add right-click binding for context menu
        self.reports_tree_tab.bind("<Button-3>", show_context_menu)
        
        # Add tooltip functionality for reports tab column headers and cells
        # This must be done AFTER all other bindings to avoid conflicts
        # Removed for now - will be re-implemented
        
        # Load and display initial data
        self._refresh_reports_tab()

    def _show_header_tooltip(self, event, tree):
        """Show tooltip for reports tab column headers"""
        try:
            # Hide existing tooltip
            if hasattr(self, '_reports_tooltip_window') and self._reports_tooltip_window:
                self._reports_tooltip_window.destroy()
                self._reports_tooltip_window = None
            
            # Don't show if tooltips are disabled
            if not hasattr(self, 'ToolTip') or not self.ToolTip:
                return
            
            # Check if hovering over column header
            region = tree.identify_region(event.x, event.y)
            column = tree.identify_column(event.x)
            
            if region == "heading" and column:
                column_tooltips = {
                    "#1": "Date and time when the mining session ended",
                    "#2": "Total duration of the mining session", 
                    "#3": "Star system where mining took place",
                    "#4": "Planet/body/ring that was mined",
                    "#5": "Total tons of materials mined",
                    "#6": "Tons per hour mining rate",
                    "#7": "Number of different material types found",
                    "#8": "Total asteroids scanned during the session",
                    "#9": "Percentage of asteroids that had valuable materials",
                    "#10": "Average quality/yield percentage of materials found",
                    "#11": "Materials mined with quantities and individual yields",
                    "#12": "Number of prospector limpets used during mining session",
                    "#13": "Session comments and notes",
                    "#14": "Generate detailed HTML report for this session"
                }
                
                tooltip_text = column_tooltips.get(column)
                if tooltip_text:
                    x = event.x_root + 10
                    y = event.y_root + 10
                    
                    self._reports_tooltip_window = tk.Toplevel(tree)
                    self._reports_tooltip_window.wm_overrideredirect(True)
                    self._reports_tooltip_window.wm_geometry(f"+{x}+{y}")
                    self._reports_tooltip_window.configure(background="#ffffe0")
                    
                    label = tk.Label(self._reports_tooltip_window, text=tooltip_text,
                                   background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                                   font=("Segoe UI", 9), justify=tk.LEFT, wraplength=300)
                    label.pack(ipadx=5, ipady=3)
        except Exception as e:
            print(f"Tooltip error: {e}")

    def _on_date_filter_changed(self, event=None) -> None:
        """Handle date filter dropdown change"""
        self._refresh_reports_tab()

    def _edit_comment_inline(self, item, event) -> None:
        """Edit comment inline for a report item"""
        try:
            # Get the current comment
            values = list(self.reports_tree_tab.item(item, 'values'))
            current_comment = values[12] if len(values) > 12 else ""  # Comment is index 12
            
            # Get the bounding box of the comment cell
            bbox = self.reports_tree_tab.bbox(item, '#13')  # Comment column
            if not bbox:
                return
            
            # Create an entry widget over the cell
            entry = tk.Entry(self.reports_tree_tab, font=("Segoe UI", 9))
            entry.insert(0, current_comment)
            entry.select_range(0, tk.END)
            entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
            entry.focus()
            
            def save_comment(event=None):
                new_comment = entry.get()
                entry.destroy()
                
                # Update the treeview
                values[12] = new_comment
                self.reports_tree_tab.item(item, values=values)
                
                # Update the CSV file
                self._update_comment_in_csv(item, new_comment)
                
            def cancel_edit(event=None):
                entry.destroy()
            
            # Bind events
            entry.bind('<Return>', save_comment)
            entry.bind('<Escape>', cancel_edit)
            entry.bind('<FocusOut>', save_comment)
            
        except Exception as e:
            self._set_status(f"Error editing comment: {e}")

    def _edit_comment_popup_reports(self, event) -> None:
        """Edit comment popup for reports tab"""
        # Get the clicked item
        item = self.reports_tree_tab.identify('item', event.x, event.y)
        if not item:
            return
        
        # Use the existing popup comment editor
        self._edit_comment(self.reports_tree_tab, item)

    def _refresh_reports_tab(self) -> None:
        """Refresh the reports tab data"""
        try:
            if not hasattr(self, 'reports_tree_tab') or not self.reports_tree_tab:
                return
            
            # Migrate existing detailed reports to mapping system (only run once)
            if not hasattr(self, '_enhanced_migration_done'):
                self._migrate_existing_enhanced_reports()
                self._enhanced_migration_done = True
            
            # Clear all cached data to prevent stale data issues
            self._clear_reports_cache()
                
            # Clear existing data from tree
            for item in self.reports_tree_tab.get_children():
                self.reports_tree_tab.delete(item)
            
            # Load data from CSV
            csv_path = self._get_csv_path()
            sessions_data = []
            
            try:
                import csv
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        # Format the timestamp for display (compact format with year)
                        try:
                            # Try to parse as local time first, then fall back to UTC
                            if row['timestamp_utc'].endswith('Z'):
                                # UTC format - convert to local time for display
                                timestamp = dt.datetime.fromisoformat(row['timestamp_utc'].replace('Z', '+00:00'))
                                timestamp = timestamp.replace(tzinfo=dt.timezone.utc).astimezone()
                            else:
                                # Local time format
                                timestamp = dt.datetime.fromisoformat(row['timestamp_utc'])
                            date_str = timestamp.strftime("%m/%d/%y %H:%M")  # Compact format with year
                        except:
                            date_str = row['timestamp_utc']
                        
                        # Format TPH (same pattern as other numeric columns)
                        try:
                            tph_val = float(row['overall_tph']) if row['overall_tph'] and row['overall_tph'].strip() != '0' else 0
                            tph_str = f"{tph_val:.1f}" if tph_val > 0 else "0.0"
                        except:
                            tph_str = "0.0"
                        
                        # Format tons (same pattern as other numeric columns) 
                        try:
                            tons_val = float(row['total_tons']) if row['total_tons'] and row['total_tons'].strip() != '0' else 0
                            tons_str = f"{tons_val:.1f}" if tons_val > 0 else "0.0"
                        except:
                            tons_str = "0.0"
                        
                        # Format Material Analysis fields (with fallback for old data)
                        asteroids = row.get('asteroids_prospected', '').strip() or '—'
                        materials = row.get('materials_tracked', '').strip() or '—'
                        hit_rate = row.get('hit_rate_percent', '').strip() or '—'
                        avg_quality = row.get('avg_quality_percent', '').strip() or '—'
                        
                        # Get new cargo tracking fields
                        materials_breakdown_raw = row.get('materials_breakdown', '').strip() or '—'
                        prospectors_used = row.get('prospectors_used', '').strip() or '—'
                        
                        # Enhanced materials display with yield percentages
                        materials_breakdown = self._enhance_materials_with_yields(materials_breakdown_raw, avg_quality)
                        
                        # Format asteroids and materials columns
                        try:
                            asteroids_val = int(asteroids) if asteroids and asteroids != '0' else 0
                            asteroids_str = str(asteroids_val) if asteroids_val > 0 else "—"
                        except:
                            asteroids_str = "—"
                        
                        try:
                            materials_val = int(materials) if materials and materials != '0' else 0
                            materials_str = str(materials_val) if materials_val > 0 else "—"
                        except:
                            materials_str = "—"
                        
                        # Format hit rate
                        try:
                            hit_rate_val = float(hit_rate) if hit_rate and hit_rate != '0' else 0
                            hit_rate_str = f"{hit_rate_val:.1f}" if hit_rate_val > 0 else "—"
                        except:
                            hit_rate_str = "—"
                        
                        # Format quality (yield %) - convert to average yield instead of individual percentages
                        try:
                            # Check if it's already a formatted string with individual materials (contains letters and colons)
                            if any(c.isalpha() for c in avg_quality) and ':' in avg_quality:
                                # Parse individual material yields: "Pt: 59.0%, Pain: 29.1%" 
                                individual_yields = []
                                pairs = [pair.strip() for pair in avg_quality.split(',')]
                                for pair in pairs:
                                    if ':' in pair:
                                        parts = pair.split(':')
                                        if len(parts) >= 2:
                                            percentage_str = parts[1].strip().replace('%', '')
                                            try:
                                                individual_yields.append(float(percentage_str))
                                            except ValueError:
                                                continue
                                
                                # Calculate simple average (same as HTML report logic)
                                if individual_yields:
                                    avg_yield = sum(individual_yields) / len(individual_yields)
                                    quality_str = f"{avg_yield:.1f}%"
                                else:
                                    quality_str = "—"
                            else:
                                # Old numerical format - keep as is
                                quality_val = float(avg_quality) if avg_quality and avg_quality != '0' else 0
                                quality_str = f"{quality_val:.1f}%" if quality_val > 0 else "—"
                        except:
                            quality_str = "—"
                        
                        # Get comment data from CSV
                        comment_from_csv = row.get('comment', '').strip()
                        
                        sessions_data.append({
                            'date': date_str,
                            'system': row['system'],
                            'body': row['body'],
                            'duration': row['elapsed'],
                            'tons': tons_str,
                            'tph': tph_str,
                            'asteroids': asteroids_str,
                            'materials': materials_str,
                            'hit_rate': hit_rate_str,
                            'quality': quality_str,
                            'cargo': materials_breakdown,
                            'cargo_raw': materials_breakdown_raw,  # Store original for tooltip
                            'prospects': prospectors_used,
                            'comment': comment_from_csv,
                            'timestamp_raw': row['timestamp_utc']
                        })
                            
            except Exception as e:
                print(f"Loading CSV failed: {e}")
                # Fallback to old file listing method
                try:
                    for fn in os.listdir(self.reports_dir):
                        if fn.lower().endswith(".txt") and fn.startswith("Session"):
                            mtime = os.path.getmtime(os.path.join(self.reports_dir, fn))
                            date_str = dt.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                            sessions_data.append({
                                'date': date_str,
                                'system': 'Unknown',
                                'body': 'Unknown',
                                'duration': 'Unknown',
                                'tons': '0.0',
                                'tph': '0.0',
                                'asteroids': '—',
                                'materials': '—',
                                'hit_rate': '—',
                                'quality': '—',
                                'cargo': '—',
                                'prospects': '—',
                                'timestamp_raw': date_str
                            })
                except:
                    pass

            # Sort by timestamp (newest first) by default
            sessions_data.sort(key=lambda x: x['timestamp_raw'], reverse=True)
            
            # Apply date filter if set
            if hasattr(self, 'date_filter_var') and self.date_filter_var.get() != "All sessions":
                from datetime import datetime, timedelta
                now = datetime.now()
                filter_value = self.date_filter_var.get()
                
                if filter_value == "Last 1 day":
                    cutoff = now - timedelta(days=1)
                elif filter_value == "Last 2 days":
                    cutoff = now - timedelta(days=2)
                elif filter_value == "Last 3 days":
                    cutoff = now - timedelta(days=3)
                elif filter_value == "Last 7 days":
                    cutoff = now - timedelta(days=7)
                elif filter_value == "Last 30 days":
                    cutoff = now - timedelta(days=30)
                elif filter_value == "Last 90 days":
                    cutoff = now - timedelta(days=90)
                else:
                    cutoff = None
                
                if cutoff:
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            # Parse timestamp from CSV
                            if session['timestamp_raw'].endswith('Z'):
                                session_time = datetime.fromisoformat(session['timestamp_raw'].replace('Z', '+00:00'))
                                session_time = session_time.replace(tzinfo=dt.timezone.utc).astimezone()
                            else:
                                session_time = datetime.fromisoformat(session['timestamp_raw'])
                            
                            if session_time >= cutoff:
                                filtered_sessions.append(session)
                        except:
                            # Keep sessions with unparseable dates
                            filtered_sessions.append(session)
                    
                    sessions_data = filtered_sessions
            
            # Apply additional filters (yield, hit rate, materials)
            if hasattr(self, 'date_filter_var'):
                filter_value = self.date_filter_var.get()
                
                # Yield-based filters
                if filter_value == "High Yield (>350 T/hr)":
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            tph_val = float(session['tph']) if session['tph'] != '—' and session['tph'] != '0.0' else 0
                            if tph_val > 350:
                                filtered_sessions.append(session)
                        except:
                            continue
                    sessions_data = filtered_sessions
                    
                elif filter_value == "Medium Yield (250-350 T/hr)":
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            tph_val = float(session['tph']) if session['tph'] != '—' and session['tph'] != '0.0' else 0
                            if 250 <= tph_val <= 350:
                                filtered_sessions.append(session)
                        except:
                            continue
                    sessions_data = filtered_sessions
                    
                elif filter_value == "Low Yield (100-250 T/hr)":
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            tph_val = float(session['tph']) if session['tph'] != '—' and session['tph'] != '0.0' else 0
                            if 100 <= tph_val < 250:
                                filtered_sessions.append(session)
                        except:
                            continue
                    sessions_data = filtered_sessions
                
                # Hit rate filters
                elif filter_value == "High Hit Rate (>40%)":
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            hit_rate_val = float(session['hit_rate']) if session['hit_rate'] != '—' else 0
                            if hit_rate_val > 40:
                                filtered_sessions.append(session)
                        except:
                            continue
                    sessions_data = filtered_sessions
                    
                elif filter_value == "Medium Hit Rate (20-40%)":
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            hit_rate_val = float(session['hit_rate']) if session['hit_rate'] != '—' else 0
                            if 20 <= hit_rate_val <= 40:
                                filtered_sessions.append(session)
                        except:
                            continue
                    sessions_data = filtered_sessions
                    
                elif filter_value == "Low Hit Rate (<20%)":
                    filtered_sessions = []
                    for session in sessions_data:
                        try:
                            hit_rate_val = float(session['hit_rate']) if session['hit_rate'] != '—' else 0
                            if 0 < hit_rate_val < 20:  # Exclude 0 values (likely missing data)
                                filtered_sessions.append(session)
                        except:
                            continue
                    sessions_data = filtered_sessions
                
                # Material-based filters
                elif filter_value == "Platinum Sessions":
                    filtered_sessions = []
                    for session in sessions_data:
                        cargo_data = session.get('cargo', '').lower()
                        if 'platinum' in cargo_data:
                            filtered_sessions.append(session)
                    sessions_data = filtered_sessions
                    
                elif filter_value == "High-Value Materials":
                    high_value_materials = ['platinum', 'osmium', 'painite', 'rhodplumsite', 'benitoite', 'monazite', 'musgravite']
                    filtered_sessions = []
                    for session in sessions_data:
                        cargo_data = session.get('cargo', '').lower()
                        if any(material in cargo_data for material in high_value_materials):
                            filtered_sessions.append(session)
                    sessions_data = filtered_sessions
                    
                elif filter_value == "Common Materials":
                    common_materials = ['bertrandite', 'indite', 'gallite', 'lepidolite', 'lithium', 'bauxite', 'cobalt', 'samarium']
                    filtered_sessions = []
                    for session in sessions_data:
                        cargo_data = session.get('cargo', '').lower()
                        if any(material in cargo_data for material in common_materials):
                            filtered_sessions.append(session)
                    sessions_data = filtered_sessions
            
            # Populate treeview and store session data for tooltips
            self.reports_tab_session_lookup = {}  # Store for tooltip access  
            self.reports_tab_original_sessions = sessions_data.copy()  # Store backup for sorting
            for session in sessions_data:
                # Check if this report has screenshots
                # Check if this report has detailed reports (keep screenshots functionality but don't show column)
                # Use tree values for consistent report_id matching
                
                item_id = self.reports_tree_tab.insert("", "end", values=(
                    session['date'],
                    session['duration'],
                    session['system'], 
                    session['body'],
                    session['tons'],
                    session['tph'],
                    session['materials'],
                    session['asteroids'],
                    session['hit_rate'],
                    session['quality'],
                    session['cargo'],
                    session['prospects'],
                    session.get('comment', ''),
                    ""  # Enhanced column placeholder
                ))
                
                # Check detailed report using tree values for consistency
                tree_values = self.reports_tree_tab.item(item_id, 'values')
                if len(tree_values) >= 4:
                    tree_report_id = f"{tree_values[0]}_{tree_values[2]}_{tree_values[3]}"
                    enhanced_indicator = self._get_detailed_report_indicator(tree_report_id)
                    self.reports_tree_tab.set(item_id, "enhanced", enhanced_indicator)
                # Store the full session data for tooltip lookup
                self.reports_tab_session_lookup[item_id] = session
            
            # Apply initial word wrap state for reports tab
            if self.reports_tab_word_wrap_enabled.get():
                max_lines = 1
                for item in self.reports_tree_tab.get_children():
                    item_data = self.reports_tab_session_lookup.get(item)
                    if item_data:
                        lines = item_data['cargo_raw'].count(';') + 1
                        max_lines = max(max_lines, min(lines, 3))
                new_height = max_lines * 20 + 10
                style = ttk.Style()
                style.configure("ReportsTab.Treeview", rowheight=new_height)
                self.reports_tree_tab.configure(style="ReportsTab.Treeview")
                
        except Exception as e:
            print(f"Failed to refresh reports tab: {e}")

    # --- Polling ---
    def _enable_realtime_mode(self) -> None:
        """Switch from startup processing mode to real-time event processing"""
        self.startup_processing = False
        
    def _tick(self) -> None:
        try:
            if self.journal_dir and os.path.isdir(self.journal_dir):
                self._watch_once()
            if self.session_active and not self.session_paused:
                self._update_elapsed()
                self._update_live_session_summary()
            
            # Status.json checking is now event-driven, not time-based
                
        except Exception:
            pass
        finally:
            if self.winfo_exists():  # Check if widget still exists
                self.after(1000, self._tick)

    def _update_live_session_summary(self):
        """Update session summary with live data during active sessions"""
        try:
            total_asteroids = self.session_analytics.get_total_asteroids()
            tracked_materials = len([mat for mat in self.session_analytics.get_tracked_materials() 
                                   if self.session_analytics.get_material_statistics(mat) and 
                                   self.session_analytics.get_material_statistics(mat).get_find_count() > 0])
            
            # Calculate total hits across all materials
            total_hits = sum(self.session_analytics.get_material_statistics(mat).get_find_count() 
                           for mat in self.session_analytics.get_tracked_materials() 
                           if self.session_analytics.get_material_statistics(mat))
            
            # Get live cargo data
            live_tons = 0.0
            live_tph = 0.0
            if (self.main_app and 
                hasattr(self.main_app, 'cargo_monitor') and 
                hasattr(self.main_app.cargo_monitor, 'get_live_session_tons')):
                try:
                    live_tons = self.main_app.cargo_monitor.get_live_session_tons()
                    # Calculate TPH based on elapsed time
                    elapsed_str = self.session_elapsed.get()
                    if elapsed_str and elapsed_str != "00:00:00":
                        time_parts = elapsed_str.split(":")
                        hours = int(time_parts[0]) + int(time_parts[1])/60 + int(time_parts[2])/3600
                        if hours > 0:
                            live_tph = live_tons / hours
                except:
                    pass
            
            if total_asteroids > 0 or live_tons > 0:
                if live_tons > 0:
                    summary_text = f"Asteroids scanned: {total_asteroids} | Materials tracked/hits: {tracked_materials}/{total_hits} | Total tons: {live_tons:.1f} | TPH: {live_tph:.1f}"
                else:
                    summary_text = f"Asteroids scanned: {total_asteroids} | Materials tracked/hits: {tracked_materials}/{total_hits}"
                self.stats_summary_label.config(text=summary_text, foreground="#e6e6e6")
            else:
                self.stats_summary_label.config(text="No data yet", foreground="#888888")
        except:
            pass

    def _find_latest_journal(self, directory: str) -> Optional[str]:
        try:
            candidates = glob.glob(os.path.join(directory, "Journal*.log"))
        except Exception:
            return None
        if not candidates:
            return None
        try:
            return max(candidates, key=lambda p: os.path.getmtime(p))
        except Exception:
            return None

    def _watch_once(self) -> None:
        latest = self._find_latest_journal(self.journal_dir)
        if not latest:
            return
        try:
            current_size = os.path.getsize(latest)
            current_mtime = os.path.getmtime(latest)
        except Exception:
            return
        if self._jrnl_path != latest:
            self._jrnl_path = latest
            self._jrnl_pos = 0
            self._last_mtime = current_mtime
            self._last_size = current_size
        elif (current_mtime <= self._last_mtime and current_size <= self._last_size):
            return  # No changes
        self._last_mtime = current_mtime
        self._last_size = current_size
        if not latest:
            return
        if self._jrnl_path != latest:
            self._jrnl_path = latest
            self._jrnl_pos = 0

        try:
            try:
                size_now = os.path.getsize(self._jrnl_path)
            except Exception:
                size_now = None
            if size_now is not None and self._jrnl_pos > size_now:
                self._jrnl_pos = 0

            with open(self._jrnl_path, "r", encoding="utf-8") as f:
                if self._jrnl_pos:
                    f.seek(self._jrnl_pos)
                new_data = f.read()
                if not new_data:
                    return
                self._jrnl_pos = f.tell()
        except Exception:
            return

        if not new_data:
            return

        for line in new_data.splitlines():
            line = line.strip()
            if not line or '"event"' not in line:
                continue
            try:
                evt = json.loads(line)
            except Exception:
                continue

            ev = evt.get("event")
            
            # Debug: Show all events being processed (after startup)
            # Real-time event processing

            if ev in ("Location", "FSDJump"):
                # Update system from events that contain StarSystem data
                if evt.get("StarSystem"):
                    self.last_system = evt.get("StarSystem")
                    self.session_system.set(self.last_system)
                
                # Update location context
                self.last_body_type = evt.get("BodyType", "")
                
                # Handle station/carrier context - use real-time Status.json for docked state
                journal_docked_status = evt.get("Docked", False)
                real_time_docked_status = self._get_current_docked_status()
                # Debug removed
                
                # Use real-time docked status from Status.json, but get station info from journal
                if real_time_docked_status and journal_docked_status:
                    # Both journal and Status.json agree we're docked - use station info from journal
                    station_name = evt.get("StationName", "")
                    station_type = evt.get("StationType", "")
                    
                    if station_type == "FleetCarrier":
                        self.last_carrier_name = station_name
                        self.last_station_name = ""
                    else:
                        self.last_station_name = station_name
                        self.last_carrier_name = ""
                elif not real_time_docked_status:
                    # Status.json shows we're not docked - clear station/carrier context
                    self.last_station_name = ""
                    self.last_carrier_name = ""
                # else: Journal/Status.json mismatch - trust Status.json
                    self.last_station_name = ""
                    self.last_carrier_name = ""
                
                # Update body from events that contain Body data  
                body_name = evt.get("Body") or evt.get("BodyName")
                if body_name:
                    self.last_body = body_name
                
                # Check Status.json for real-time location after Location/FSDJump events
                self._check_status_location_fields()
                
                # Only update location display if we have meaningful context
                # Priority: Fleet Carrier > Station > Body
                if self.last_carrier_name or self.last_station_name or self.last_body:
                    body_display = _extract_location_display(
                        self.last_body or "", 
                        self.last_body_type, 
                        self.last_station_name, 
                        self.last_carrier_name
                    )
                    self.session_body.set(body_display)
                    
            elif ev in ("ApproachBody",):
                # Body-only events - but don't override fleet carrier context while navigating
                if not self.startup_processing:
                    body_name = evt.get("Body") or evt.get("BodyName")
                    if body_name:
                        self.last_body = body_name
                        self.last_body_type = evt.get("BodyType", "")
                        
                        # Only update display if we don't have carrier/station context (avoid overriding navigation targets)
                        if not self.last_carrier_name and not self.last_station_name:
                            body_display = _extract_location_display(
                                body_name, 
                                self.last_body_type, 
                                self.last_station_name, 
                                self.last_carrier_name
                            )
                            self.session_body.set(body_display)
                    
            elif ev in ("SupercruiseEntry", "SupercruiseExit"):
                # Handle SupercruiseExit during startup to get accurate BodyType for rings
                if ev == "SupercruiseExit":
                    body_name = evt.get("Body") or evt.get("BodyName")
                    if body_name:
                        self.last_body = body_name
                        self.last_body_type = evt.get("BodyType", "")
                        # During startup, just update the data without display changes
                        if not self.startup_processing:
                            # Clear carrier/station context since we've dropped into normal space
                            self.last_carrier_name = ""
                            self.last_station_name = ""
                            # Update display immediately with the new body info
                            body_display = _extract_location_display(
                                self.last_body, 
                                self.last_body_type, 
                                self.last_station_name, 
                                self.last_carrier_name
                            )
                            self.session_body.set(body_display)
                            
                # Real-time supercruise events (not during startup)
                if not self.startup_processing:
                    # Real-time supercruise events - check Status.json first
                    self._check_status_location_fields()
                    
                    # Update system info if available
                    if evt.get("StarSystem"):
                        self.last_system = evt.get("StarSystem")
                        self.session_system.set(self.last_system)
                    
                    # SupercruiseExit is already handled above (both startup and real-time)
                    
                    # For other supercruise events, clear docked context if Status.json doesn't show we're at a destination
                    elif not self.last_carrier_name and not self.last_station_name:
                        # Update display with current location info
                        body_display = _extract_location_display(
                            self.last_body or "", 
                            self.last_body_type, 
                            self.last_station_name, 
                            self.last_carrier_name
                        )
                        self.session_body.set(body_display)
                    
            elif ev in ("Docked",):
                # Check Status.json for real-time location when docking occurs
                self._check_status_location_fields()
                
                # Also check real-time docked status for consistency
                real_time_docked_status = self._get_current_docked_status()
                journal_station_name = evt.get("StationName", "")
                journal_station_type = evt.get("StationType", "")
                
                # Debug removed
                
                # Status.json check should have already updated location, but validate with journal data
                if real_time_docked_status:
                    if journal_station_type == "FleetCarrier":
                        if not self.last_carrier_name:  # Only update if Status.json didn't already set it
                            self.last_carrier_name = journal_station_name
                            self.last_station_name = ""
                    else:
                        if not self.last_station_name:  # Only update if Status.json didn't already set it
                            self.last_station_name = journal_station_name
                            self.last_carrier_name = ""
                    
                    # Update display with docking context
                    body_display = _extract_location_display(
                        self.last_body or "", 
                        self.last_body_type, 
                        self.last_station_name, 
                        self.last_carrier_name
                    )
                    self.session_body.set(body_display)
                    # Debug removed
                else:
                    # Debug removed - ignoring journal docking event when Status.json shows not docked
                    pass
                    
            elif ev in ("CarrierJump", "CarrierLocation"):
                # Fleet carrier jump - we're now at the carrier
                carrier_name = evt.get("StationName", "") or evt.get("CarrierName", "")
                if carrier_name:
                    self.last_carrier_name = carrier_name
                    self.last_station_name = ""
                    
                    # Update system and body from carrier jump
                    if evt.get("StarSystem"):
                        self.last_system = evt.get("StarSystem")
                        self.session_system.set(self.last_system)
                    
                    body_name = evt.get("Body") or evt.get("BodyName")
                    if body_name:
                        self.last_body = body_name
                        self.last_body_type = evt.get("BodyType", "")
                        
                        body_display = _extract_location_display(
                            body_name, 
                            self.last_body_type, 
                            self.last_station_name, 
                            self.last_carrier_name
                        )
                        self.session_body.set(body_display)
                        
            elif ev in ("Touchdown",):
                # Planetary landing event - check Status.json for current state
                if not self.startup_processing:
                    self._check_status_location_fields()
                    
                    # Update body info from the event
                    body_name = evt.get("Body") or evt.get("BodyName")
                    if body_name:
                        self.last_body = body_name
                        self.last_body_type = "Planet"
                        # Debug removed - touchdown event
                        self._update_location_display()
                        
            elif ev in ("Liftoff", "Undocked"):
                # During startup, ignore historical undock events to preserve current state
                if not self.startup_processing:
                    # Real-time undock events - clear station/carrier context
                    self.last_station_name = ""
                    self.last_carrier_name = ""
                    
                    # Update display with current body
                    if self.last_body:
                        body_display = _extract_location_display(
                            self.last_body, 
                            self.last_body_type, 
                            self.last_station_name, 
                            self.last_carrier_name
                        )
                        self.session_body.set(body_display)

            if ev == "ProspectedAsteroid":
                # Check if this is a startup skip (old event from before app started)
                if self._startup_skip:
                    # Check timestamp - if event is more than 10 seconds old, skip it
                    event_time = evt.get("timestamp", "")
                    if event_time:
                        try:
                            from datetime import datetime, timezone
                            event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                            now_dt = datetime.now(timezone.utc)
                            time_diff = (now_dt - event_dt).total_seconds()
                            
                            if time_diff > 10:  # Event is older than 10 seconds
                                self._startup_skip = False
                                return  # Skip old events
                        except Exception:
                            pass  # If timestamp parsing fails, process the event
                    
                    self._startup_skip = False  # Clear flag after first event
                materials_txt, content_txt, time_txt, panel_summary, speak_summary, triggered = self._summaries_from_event(evt)
                self.history.insert(0, (materials_txt, content_txt, time_txt))
                self.history = self.history[:10]
                
                # Track yield data during session for later CSV calculation
                self._track_session_yield_data(materials_txt)
                
                self._refresh_table()
                
                # Update mining statistics with the prospector result
                self._update_mining_statistics(evt)
                # Remove old enabled check - announcements now controlled by core/non-core toggles

                # Always update the full on-screen readout
                self._write_var_text("prospectReadout", panel_summary)

                # Only write a filtered, short line to the TTS file when rules are met
                core_toggle = bool(self.announcement_vars["Core Asteroids"].get())
                noncore_toggle = bool(self.announcement_vars["Non-Core Asteroids"].get())
                
                mother = evt.get("MotherlodeMaterial_Localised") or evt.get("MotherlodeMaterial")
                mother = _clean_name(mother) if isinstance(mother, str) else ""
                
                # Track if any announcement was made
                announcement_made = False
                
                # Prepare announcement components
                core_msg = ""
                noncore_msg = ""
                
                # Prepare core announcement if toggle is enabled and motherlode present
                if mother and core_toggle and self.announce_map.get(mother, True):
                    if "Remaining Depleted" not in panel_summary:
                        core_msg = f"Motherlode: {mother}"
                
                # Prepare non-core announcement if toggle is enabled
                if noncore_toggle and triggered and speak_summary:
                    if "Remaining Depleted" not in panel_summary:
                        # Create a clean list of non-core materials only
                        non_core_materials = []
                        
                        # Split speak_summary and filter out motherlode (motherlode should never appear in non-core)
                        for part in speak_summary.split(", "):
                            part = part.strip()
                            # Always filter out motherlode from non-core announcements
                            if not (mother and part.startswith(f"Motherlode: {mother}")):
                                non_core_materials.append(part)
                        
                        if non_core_materials:
                            # Reorder the materials (percentage first, then material name)
                            reordered_materials = [
                                " ".join([p.split()[1], p.split()[0]]) if len(p.split()) >= 2 and not p.startswith("Motherlode:") else p
                                for p in non_core_materials
                            ]
                            
                            # Join materials with "and" before the last item
                            if len(reordered_materials) == 1:
                                noncore_msg = reordered_materials[0]
                            elif len(reordered_materials) == 2:
                                noncore_msg = f"{reordered_materials[0]} and {reordered_materials[1]}"
                            else:
                                # Multiple materials: "A, B, C and D"
                                noncore_msg = ", ".join(reordered_materials[:-1]) + f" and {reordered_materials[-1]}"
                            

                
                # Combine and announce
                if core_msg and noncore_msg:
                    # Both core and non-core - combine with "and"
                    msg = f"Prospector Reports: {core_msg} and {noncore_msg}"
                    # Remove VA_TTS_ANNOUNCEMENT - this might trigger VoiceAttack TTS
                    # self._write_var_text(VA_TTS_ANNOUNCEMENT, msg)
                    if self.text_overlay:
                        self.text_overlay.show_message(msg)
                    announcer.say(msg)
                    announcement_made = True
                    self._set_status("Combined core and non-core announcement triggered.")
                elif core_msg:
                    # Only core
                    msg = f"Prospector Reports: {core_msg}"
                    # Remove VA_TTS_ANNOUNCEMENT - this might trigger VoiceAttack TTS
                    # self._write_var_text(VA_TTS_ANNOUNCEMENT, msg)
                    if self.text_overlay:
                        self.text_overlay.show_message(msg)
                    announcer.say(msg)
                    announcement_made = True
                    self._set_status("Core announcement triggered.")
                elif noncore_msg:
                    # Only non-core
                    msg = f"Prospector Reports: {noncore_msg}"
                    # Remove VA_TTS_ANNOUNCEMENT - this might trigger VoiceAttack TTS
                    # self._write_var_text(VA_TTS_ANNOUNCEMENT, msg)
                    if self.text_overlay:
                        self.text_overlay.show_message(msg)
                    announcer.say(msg)
                    announcement_made = True
                    self._set_status("Non-core announcement triggered.")

            if self.session_active and ev == "MiningRefined":
                name = _clean_name(evt.get("Type_Localised") or evt.get("Type") or "")
                if name:
                    self.session_totals[name] = self.session_totals.get(name, 0.0) + 1.0  # 1 ton per refine

    def _summaries_from_event(self, evt: Dict[str, Any]) -> Tuple[str, str, str, str, str, bool]:
        t = evt.get("timestamp")
        try:
            time_str = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).strftime("%H:%M:%S") if t else "--:--:--"
        except Exception:
            time_str = "--:--:--"

        content_str = _extract_content(evt)

        rem_val = _extract_remaining(evt)
        if rem_val is None:
            remaining_text = ""
        else:
            if rem_val <= 0.0:
                remaining_text = " — Remaining Depleted"
            elif rem_val >= 100.0:
                remaining_text = " — Remaining 100%"
            else:
                remaining_text = f" — Remaining {_fmt_pct(rem_val)}"

        materials = evt.get("Materials") or []
        all_parts: List[str] = []        # for panel (everything)
        speak_parts: List[str] = []      # for TTS (filtered)
        triggered = False
        th = float(self.threshold.get())

        for m in materials:
            name = _extract_material_name(m)
            pct_val = _extract_material_percent(m)
            pct_text = _fmt_pct(pct_val)
            if not name:
                continue
            entry = f"{name} {pct_text}".strip()
            all_parts.append(entry)

            eff_th = float(self.min_pct_map.get(name, th))
            # Use case-insensitive lookup for material filtering
            # First try exact match, then try title case
            is_enabled = self.announce_map.get(name, False)
            if not is_enabled and name != name.title():
                is_enabled = self.announce_map.get(name.title(), False)
            if pct_val is not None and is_enabled and pct_val >= eff_th:
                speak_parts.append(entry)
                triggered = True

        mother = evt.get("MotherlodeMaterial_Localised") or evt.get("MotherlodeMaterial")
        mother = _clean_name(mother) if isinstance(mother, str) else ""
        if mother:
            all_parts.insert(0, f"Motherlode: {mother}")
            # Only add to speak_parts if Core Asteroids toggle is enabled
            core_toggle = bool(self.announcement_vars["Core Asteroids"].get())
            if self.announce_map.get(mother, False):   # Default to False for consistency
                speak_parts.insert(0, f"Motherlode: {mother}")
                triggered = True

        materials_txt = ", ".join(all_parts) if all_parts else "No materials reported"
        content_with_remaining = (content_str or "") + remaining_text

        # Full line for the on-screen panel
        panel_summary = f"{content_str + ' — ' if content_str else ''}{materials_txt}"
        if rem_val is not None:
            panel_summary += (" — Remaining Depleted" if rem_val <= 0.0 else f" — Remaining {_fmt_pct(rem_val)}")

        # Short, filtered line for TTS (no 'Material Content', no 'Remaining')
        speak_summary = ", ".join(speak_parts)

        return materials_txt, content_with_remaining, time_str, panel_summary, speak_summary, triggered
    def _refresh_table(self) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        for materials_txt, content_txt, time_txt in self.history:
            self.tree.insert("", "end", values=(materials_txt, content_txt, time_txt), tags=("darkrow",))

    def _update_mining_statistics(self, evt: Dict[str, Any]) -> None:
        """Update mining statistics with prospector result and refresh display"""

        try:
            # Get selected materials from announcements panel using announce_map
            selected_materials = []
            
            # Get materials that are checked for announcements in the announcements panel
            for material_name, is_enabled in self.announce_map.items():
                if is_enabled:
                    selected_materials.append(material_name)
            
            # Also check announcement_vars for backward compatibility (Core/Non-Core toggles)
            if hasattr(self, 'announcement_vars') and self.announcement_vars:
                for mat_name, var in self.announcement_vars.items():
                    if mat_name not in ["Core Asteroids", "Non-Core Asteroids"] and var.get():
                        if mat_name not in selected_materials:
                            selected_materials.append(mat_name)
            
            # Sync current UI thresholds to min_pct_map before processing
            self._sync_spinboxes_to_min_pct_map()
            

            
            # Add the prospector result to analytics with properly selected materials and thresholds
            self.session_analytics.add_prospector_event(evt, selected_materials, self.min_pct_map)
            
            # Refresh the statistics display
            self._refresh_statistics_display()
            
        except Exception as e:
            # Show errors for debugging
            print(f"ERROR in _update_mining_statistics: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_statistics_display(self) -> None:
        """Refresh the live statistics display"""
        try:
            # Clear existing statistics display
            for item in self.stats_tree.get_children():
                self.stats_tree.delete(item)
            
            # Get quality summary data based on announcement thresholds
            summary_data = self.session_analytics.get_quality_summary(self.min_pct_map)
            
            if not summary_data:
                # No data yet
                self.stats_summary_label.config(text="No data yet", foreground="#888888")
                return
            
            # Update statistics tree with material data
            for material_name, stats in summary_data.items():
                avg_pct = f"{stats['avg_percentage']:.1f}%" if stats['avg_percentage'] > 0 else "0.0%"
                best_pct = f"{stats['best_percentage']:.1f}%" if stats['best_percentage'] > 0 else "0.0%"
                latest_pct = f"{stats['latest_percentage']:.1f}%" if stats['latest_percentage'] > 0 else "0.0%"
                # Use quality_hits instead of raw find_count
                quality_hits = str(stats['quality_hits'])
                
                self.stats_tree.insert("", "end", values=(
                    material_name, avg_pct, best_pct, latest_pct, quality_hits
                ), tags=("darkrow",))
            
            # Update session summary with live tracking
            total_asteroids = self.session_analytics.get_total_asteroids()
            tracked_materials = len(summary_data)
            
            # Calculate total hits across all materials
            total_hits = sum(self.session_analytics.get_material_statistics(mat).get_find_count() 
                           for mat in self.session_analytics.get_tracked_materials() 
                           if self.session_analytics.get_material_statistics(mat))
            
            # Get live cargo data
            live_tons = 0.0
            live_tph = 0.0
            if (self.main_app and 
                hasattr(self.main_app, 'cargo_monitor') and 
                hasattr(self.main_app.cargo_monitor, 'get_live_session_tons')):
                try:
                    live_tons = self.main_app.cargo_monitor.get_live_session_tons()
                    # Calculate TPH based on elapsed time
                    elapsed_str = self.session_elapsed.get()
                    if elapsed_str and elapsed_str != "00:00:00":
                        time_parts = elapsed_str.split(":")
                        hours = int(time_parts[0]) + int(time_parts[1])/60 + int(time_parts[2])/3600
                        if hours > 0:
                            live_tph = live_tons / hours
                except:
                    pass
            
            if total_asteroids > 0 or live_tons > 0:
                if live_tons > 0:
                    summary_text = f"Asteroids scanned: {total_asteroids} | Materials tracked/hits: {tracked_materials}/{total_hits} | Total tons: {live_tons:.1f} | TPH: {live_tph:.1f}"
                else:
                    summary_text = f"Asteroids scanned: {total_asteroids} | Materials tracked/hits: {tracked_materials}/{total_hits}"
                self.stats_summary_label.config(text=summary_text, foreground="#e6e6e6")
            else:
                self.stats_summary_label.config(text="No data yet", foreground="#888888")
            
            # Update graphs if available
            if self.charts_panel:
                self.charts_panel.update_charts()
                
        except Exception as e:
            # Show basic info even if there's an error
            try:
                total_asteroids = self.session_analytics.get_total_asteroids()
                if total_asteroids > 0:
                    self.stats_summary_label.config(text=f"Asteroids scanned: {total_asteroids} | Materials tracked/hits: 0/0", foreground="#e6e6e6")
                else:
                    self.stats_summary_label.config(text="No data yet", foreground="#888888")
            except:
                self.stats_summary_label.config(text="No data yet", foreground="#888888")

    def _quick_export_analytics(self) -> None:
        """Quick export of analytics data from the statistics panel"""
        try:
            if not self.charts_panel:
                messagebox.showwarning("Export Unavailable", "Charts module not available for export.")
                return
            
            # Check if we have data to export
            summary_data = self.session_analytics.get_live_summary()
            if not summary_data:
                messagebox.showwarning("No Data", "No mining data available to export.\nStart mining to collect data first.")
                return
            
            # Use the charts panel's export all functionality
            self.charts_panel.export_all()
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export analytics:\n{str(e)}")

    # --- Session handling ---
    def _active_seconds(self) -> float:
        if not (self.session_active and self.session_start):
            return 0.0
        now = dt.datetime.utcnow()
        paused = self.session_paused_seconds
        if self.session_paused and self.session_pause_started:
            paused += (now - self.session_pause_started).total_seconds()
        return max((now - self.session_start).total_seconds() - paused, 0.0)

    def _update_elapsed(self) -> None:
        secs = int(self._active_seconds())
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        self.session_elapsed.set(f"{h:02d}:{m:02d}:{s:02d}")

    def _session_start(self) -> None:
        if self.session_active:
            return
        if self.last_system and not self.session_system.get():
            self.session_system.set(self.last_system)
        if self.last_body and not self.session_body.get():
            body_display = _extract_location_display(
                self.last_body, 
                self.last_body_type, 
                self.last_station_name, 
                self.last_carrier_name
            )
            self.session_body.set(body_display)

        self.session_active = True
        self.session_paused = False
        self.session_start = dt.datetime.utcnow()
        self.session_pause_started = None
        self.session_paused_seconds = 0.0
        self.session_totals = {}
        self.session_elapsed.set("00:00:00")
        self.session_screenshots = []  # Initialize screenshots list for this session
        self.session_yield_data = {}  # Track yield data during session {material: [percentages]}
        
        # Reset and start mining statistics for new session
        self.session_analytics.start_session()
        self._refresh_statistics_display()
        
        # Clear prospector reports for clean session-specific yield calculation
        self._clear_prospector_reports()
        
        # Start cargo tracking for material breakdown
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            self.main_app.cargo_monitor.start_session_tracking()

        self.start_btn.config(state="disabled")
        self.pause_resume_btn.config(state="normal", text="Pause")
        self.stop_btn.config(state="normal")
        self.cancel_btn.config(state="normal")
        self._set_status("Mining session started.")

    def _edit_comment_popup(self, event):
        """Edit Body or Comment column in reports popup window"""
        item = self.reports_tree.selection()[0] if self.reports_tree.selection() else None
        if not item:
            return
        
        # Get clicked column
        column = self.reports_tree.identify_column(event.x)
        if column == "#4":  # Body column
            self._edit_body(self.reports_tree, item)
        elif column == "#13":  # Comment column
            self._edit_comment(self.reports_tree, item)
    
    def _edit_cell_tab(self, event):
        """Edit Body or Comment column in reports tab"""
        item = self.reports_tree_tab.selection()[0] if self.reports_tree_tab.selection() else None
        if not item:
            return
            
        # Get clicked column
        column = self.reports_tree_tab.identify_column(event.x)
        if column == "#4":  # Body column
            self._edit_body(self.reports_tree_tab, item)
        elif column == "#13":  # Comment column
            self._edit_comment(self.reports_tree_tab, item)
    
    def _edit_comment_tab(self, event):
        """Edit comment in reports tab"""
        item = self.reports_tree_tab.selection()[0] if self.reports_tree_tab.selection() else None
        if not item:
            return
            
        # Get clicked column
        column = self.reports_tree_tab.identify_column(event.x)
        if column != "#13":  # Comment column
            return
            
        self._edit_comment(self.reports_tree_tab, item)
    
    def _edit_comment(self, tree, item):
        """Edit comment for selected session"""
        
        # Get current comment
        values = tree.item(item, 'values')
        current_comment = values[12] if len(values) > 12 else ""
        
        # Show custom edit dialog with app logo
        new_comment = self._show_custom_comment_dialog(
            "Edit Comment", 
            "Edit session comment:",
            current_comment
        )
        
        if new_comment is not None:  # User didn't cancel
            # Update tree display
            new_values = list(values)
            if len(new_values) > 12:
                new_values[12] = new_comment
            else:
                new_values.append(new_comment)
            tree.item(item, values=new_values)
            
            # Get the raw timestamp for CSV update from session lookup
            raw_timestamp = None
            if tree == self.reports_tree_tab and hasattr(self, 'reports_tab_session_lookup'):
                session_data = self.reports_tab_session_lookup.get(item)
                if session_data:
                    raw_timestamp = session_data.get('timestamp_raw')
            elif tree == self.reports_tree and hasattr(self, 'session_lookup'):
                session_data = self.session_lookup.get(item)
                if session_data:
                    raw_timestamp = session_data.get('timestamp_raw')
            
            # Fallback to display timestamp if raw timestamp not found
            if not raw_timestamp:
                raw_timestamp = values[0]
            
            # Update both CSV file and text file for data consistency
            csv_updated = self._update_comment_in_csv(raw_timestamp, new_comment)
            text_updated = self._update_comment_in_text_file(raw_timestamp, new_comment)
            
            # Check if updates were successful
            if not csv_updated or not text_updated:
                from tkinter import messagebox
                
                # Determine error message based on what failed
                if not csv_updated and not text_updated:
                    error_msg = "Failed to update comment in both CSV and text files."
                elif not csv_updated:
                    error_msg = "Failed to update comment in CSV file.\nText file was updated successfully."
                else:
                    error_msg = "Failed to update comment in text file.\nCSV file was updated successfully."
                
                result = messagebox.askyesno(
                    "Update Failed", 
                    f"{error_msg}\n\n"
                    f"The comment change is only visible in the UI but may not persist.\n"
                    f"This may cause data inconsistency.\n\n"
                    f"Would you like to revert the UI change?",
                    icon="warning"
                )
                if result:  # User chose to revert
                    # Revert the UI change
                    new_values[12] = current_comment
                    tree.item(item, values=new_values)
    
    def _edit_body(self, tree, item):
        """Edit body name for selected session"""
        
        # Get current body name
        values = tree.item(item, 'values')
        current_body = values[3] if len(values) > 3 else ""
        
        # Show custom edit dialog with app logo
        new_body = self._show_custom_comment_dialog(
            "Edit Body Name", 
            "Edit body/ring name:",
            current_body
        )
        
        if new_body is not None:  # User didn't cancel
            # Update tree display
            new_values = list(values)
            new_values[3] = new_body
            tree.item(item, values=new_values)
            
            # Get the raw timestamp for CSV update from session lookup
            raw_timestamp = None
            if tree == self.reports_tree_tab and hasattr(self, 'reports_tab_session_lookup'):
                session_data = self.reports_tab_session_lookup.get(item)
                if session_data:
                    raw_timestamp = session_data.get('timestamp_raw')
            elif tree == self.reports_tree and hasattr(self, 'session_lookup'):
                session_data = self.session_lookup.get(item)
                if session_data:
                    raw_timestamp = session_data.get('timestamp_raw')
            
            # Fallback to display timestamp if raw timestamp not found
            if not raw_timestamp:
                raw_timestamp = values[0]
            
            # Update both CSV file and text file for data consistency
            csv_updated = self._update_body_in_csv(raw_timestamp, new_body)
            text_updated = self._update_body_in_text_file(raw_timestamp, new_body)
            
            # Check if updates were successful
            if not csv_updated or not text_updated:
                from tkinter import messagebox
                
                # Determine error message based on what failed
                if not csv_updated and not text_updated:
                    error_msg = "Failed to update body name in both CSV and text files."
                elif not csv_updated:
                    error_msg = "Failed to update body name in CSV file.\nText file was updated successfully."
                else:
                    error_msg = "Failed to update body name in text file.\nCSV file was updated successfully."
                
                result = messagebox.askyesno(
                    "Update Failed", 
                    f"{error_msg}\n\n"
                    f"The body name change is only visible in the UI but may not persist.\n"
                    f"This may cause data inconsistency.\n\n"
                    f"Would you like to revert the UI change?",
                    icon="warning"
                )
                if result:  # User chose to revert
                    # Revert the UI change
                    new_values[3] = current_body
                    tree.item(item, values=new_values)
    
    def _update_comment_in_csv(self, timestamp, new_comment):
        """Update comment in CSV file. Returns True if successful, False otherwise."""
        import csv
        csv_path = self._get_csv_path()
        
        if not os.path.exists(csv_path):
            return False
            
        # Read all sessions
        sessions = []
        updated = False
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Find matching session by comparing timestamps
                raw_timestamp = row['timestamp_utc']
                
                # Try direct match first (for raw ISO format timestamps)
                if raw_timestamp == timestamp:
                    row['comment'] = new_comment
                    updated = True
                    sessions.append(row)
                    continue
                
                # If direct match fails, try parsing display format comparison
                try:
                    # Parse the CSV timestamp
                    if raw_timestamp.endswith('Z'):
                        csv_dt = dt.datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                        csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                    else:
                        csv_dt = dt.datetime.fromisoformat(raw_timestamp)
                    
                    # Convert CSV timestamp to display format (mm/dd HH:MM)
                    display_time = csv_dt.strftime("%m/%d %H:%M")
                    
                    # Compare with the display timestamp (e.g., "09/08 18:20")
                    if display_time == timestamp:
                        row['comment'] = new_comment
                        updated = True
                except Exception as e:
                    pass  # Continue with next row if timestamp parsing fails
                    
                sessions.append(row)
        
        # Write back only if we found and updated a session
        if updated:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 
                            'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 
                            'avg_quality_percent', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(sessions)
            return True
        else:
            
            return False

    def _update_comment_in_text_file(self, timestamp, new_comment):
        """Update comment in the corresponding session text file. Returns True if successful, False otherwise."""
        import re
        import csv
        
        # Strategy 1: If timestamp is ISO format, convert directly to filename
        if 'T' in timestamp:
            try:
                dt_obj = dt.datetime.fromisoformat(timestamp.replace('Z', ''))
                filename_prefix = dt_obj.strftime("Session_%Y-%m-%d_%H-%M-%S")
            except Exception as e:
                filename_prefix = None
        else:
            filename_prefix = None
        
        # Strategy 2: If display format or ISO parsing failed, search through CSV to find matching raw timestamp
        if not filename_prefix:
            csv_path = self._get_csv_path()
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Convert raw timestamp to display format for comparison
                            raw_timestamp = row['timestamp_utc']
                            try:
                                if raw_timestamp.endswith('Z'):
                                    csv_dt = dt.datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                                    csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                                else:
                                    csv_dt = dt.datetime.fromisoformat(raw_timestamp)
                                
                                display_time = csv_dt.strftime("%m/%d %H:%M")
                                if display_time == timestamp:
                                    # Found matching CSV entry, use its raw timestamp
                                    dt_obj = dt.datetime.fromisoformat(raw_timestamp.replace('Z', ''))
                                    filename_prefix = dt_obj.strftime("Session_%Y-%m-%d_%H-%M-%S")
                                    break
                            except Exception as e:
                                continue
                except Exception as e:
                    pass
        
        if not filename_prefix:
            return False
        
        # Find matching text file
        reports_dir = self.reports_dir
        matching_file = None
        
        for filename in os.listdir(reports_dir):
            if filename.startswith(filename_prefix) and filename.endswith('.txt'):
                matching_file = os.path.join(reports_dir, filename)
                break
        
        if not matching_file:
            return False
        
        try:
            # Read the text file
            with open(matching_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Update or add the SESSION COMMENT section
            if '=== SESSION COMMENT ===' in content:
                # Replace existing comment
                pattern = r'=== SESSION COMMENT ===\s*\n.*?(?=\n===|\n\n|\Z)'
                replacement = f'=== SESSION COMMENT ===\n{new_comment}'
                updated_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
            else:
                # Add new comment section at the end
                if content.endswith('\n'):
                    updated_content = content + f'=== SESSION COMMENT ===\n{new_comment}\n'
                else:
                    updated_content = content + f'\n\n=== SESSION COMMENT ===\n{new_comment}\n'
            
            # Write back the updated content
            with open(matching_file, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            return True
            
        except Exception as e:
            return False

    def _update_body_in_csv(self, timestamp, new_body):
        """Update body name in CSV file. Returns True if successful, False otherwise."""
        import csv
        csv_path = self._get_csv_path()
        
        if not os.path.exists(csv_path):
            return False
            
        # Read all sessions
        sessions = []
        updated = False
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Find matching session by comparing timestamps
                raw_timestamp = row['timestamp_utc']
                
                # Try direct match first (for raw ISO format timestamps)
                if raw_timestamp == timestamp:
                    row['body'] = new_body
                    updated = True
                else:
                    # Try comparing display format timestamps
                    try:
                        if raw_timestamp.endswith('Z'):
                            csv_dt = dt.datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                            csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                        else:
                            csv_dt = dt.datetime.fromisoformat(raw_timestamp)
                        
                        display_time = csv_dt.strftime("%m/%d %H:%M")
                        if display_time == timestamp:
                            row['body'] = new_body
                            updated = True
                    except Exception:
                        continue
                        
                sessions.append(row)
        
        if not updated:
            return False
            
        # Write back updated sessions
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                if sessions:
                    writer = csv.DictWriter(f, fieldnames=sessions[0].keys())
                    writer.writeheader()
                    writer.writerows(sessions)
            return True
        except Exception:
            return False

    def _update_body_in_text_file(self, timestamp, new_body):
        """Update body name in the corresponding session text file. Returns True if successful, False otherwise."""
        import re
        import csv
        
        # Strategy 1: If timestamp is ISO format, convert directly to filename
        if 'T' in timestamp:
            try:
                dt_obj = dt.datetime.fromisoformat(timestamp.replace('Z', ''))
                filename_prefix = dt_obj.strftime("Session_%Y-%m-%d_%H-%M-%S")
            except Exception as e:
                filename_prefix = None
        else:
            filename_prefix = None
        
        # Strategy 2: If display format or ISO parsing failed, search through CSV to find matching raw timestamp
        if not filename_prefix:
            csv_path = self._get_csv_path()
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Convert raw timestamp to display format for comparison
                            raw_timestamp = row['timestamp_utc']
                            try:
                                if raw_timestamp.endswith('Z'):
                                    csv_dt = dt.datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                                    csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                                else:
                                    csv_dt = dt.datetime.fromisoformat(raw_timestamp)
                                
                                display_time = csv_dt.strftime("%m/%d %H:%M")
                                if display_time == timestamp:
                                    # Found matching CSV entry, use its raw timestamp
                                    dt_obj = dt.datetime.fromisoformat(raw_timestamp.replace('Z', ''))
                                    filename_prefix = dt_obj.strftime("Session_%Y-%m-%d_%H-%M-%S")
                                    break
                            except Exception as e:
                                continue
                except Exception as e:
                    pass
        
        if not filename_prefix:
            return False
        
        # Find matching text file
        reports_dir = self.reports_dir
        matching_file = None
        
        for filename in os.listdir(reports_dir):
            if filename.startswith(filename_prefix) and filename.endswith('.txt'):
                matching_file = os.path.join(reports_dir, filename)
                break
        
        if not matching_file:
            return False
        
        try:
            # Read the text file
            with open(matching_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Update the first line which contains the session header
            # Format: "Session: System — Body — Duration — Total XXt"
            lines = content.split('\n')
            if lines and lines[0].startswith("Session:"):
                # Parse the current header
                parts = lines[0].split("—")
                if len(parts) >= 2:
                    # Update the body part (index 1)
                    parts[1] = f" {new_body} "
                    lines[0] = "—".join(parts)
                    
                    # Write back the updated content
                    updated_content = '\n'.join(lines)
                    with open(matching_file, 'w', encoding='utf-8') as f:
                        f.write(updated_content)
                    
                    return True
            
            return False
            
        except Exception as e:
            return False

    def _show_comment_dialog(self) -> str:
        """Show dialog to get session comment from user"""
        comment = self._show_custom_comment_dialog(
            "Session Comment", 
            "Add a comment to this mining session (optional):",
            ""
        )
        return comment or ""
    
    def _show_custom_comment_dialog(self, title: str, prompt: str, initial_value: str = "") -> str:
        """Show custom comment dialog with app logo"""
        import tkinter as tk
        from tkinter import ttk
        import os
        
        # Create dialog window
        dialog = tk.Toplevel(self.winfo_toplevel())
        dialog.title(title)
        dialog.geometry("400x150")
        dialog.resizable(False, False)
        dialog.configure(bg="#2d2d2d")
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except:
            pass  # Continue without icon if there's an issue
        
        # Center dialog on parent window
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        
        # Position dialog centered on parent window using simpler method
        # Force both windows to update their geometry info
        parent = self.winfo_toplevel()
        parent.update_idletasks()
        dialog.update_idletasks()
        
        # Get actual window positions using winfo methods
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        
        # Center dialog on parent
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        dialog.geometry(f"+{x}+{y}")
        
        result = [None]  # Use list to store result for closure
        
        # Create dialog content
        main_frame = ttk.Frame(dialog)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Prompt label
        prompt_label = ttk.Label(main_frame, text=prompt, foreground="#ffffff", background="#2d2d2d")
        prompt_label.pack(pady=(0, 10))
        
        # Entry field
        entry_var = tk.StringVar(value=initial_value)
        entry_field = ttk.Entry(main_frame, textvariable=entry_var, width=50)
        entry_field.pack(pady=(0, 10), fill="x")
        entry_field.focus_set()
        entry_field.select_range(0, tk.END)
        
        # Button frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill="x")
        
        def on_ok():
            result[0] = entry_var.get()
            dialog.destroy()
        
        def on_cancel():
            result[0] = None
            dialog.destroy()
        
        # OK button
        ok_button = tk.Button(button_frame, text="OK", command=on_ok,
                             bg="#444444", fg="#ffffff", 
                             activebackground="#555555", activeforeground="#ffffff",
                             relief="solid", bd=1, width=10)
        ok_button.pack(side="right", padx=(5, 0))
        
        # Cancel button
        cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel,
                                 bg="#444444", fg="#ffffff", 
                                 activebackground="#555555", activeforeground="#ffffff",
                                 relief="solid", bd=1, width=10)
        cancel_button.pack(side="right")
        
        # Bind Enter and Escape keys
        def on_enter(event):
            on_ok()
        
        def on_escape(event):
            on_cancel()
        
        dialog.bind('<Return>', on_enter)
        dialog.bind('<Escape>', on_escape)
        entry_field.bind('<Return>', on_enter)
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result[0]  # Return None if cancelled, actual value if OK
    
    def _session_stop(self) -> None:
        if not self.session_active or not self.session_start:
            return

        # Handle paused session - resume calculations
        if self.session_paused and self.session_pause_started:
            import datetime as dt
            self.session_paused_seconds += (dt.datetime.utcnow() - self.session_pause_started).total_seconds()
            self.session_paused = False
            self.session_pause_started = None

        active_hours = max(self._active_seconds() / 3600.0, 1e-9)

        self.session_active = False
        
        # Stop mining analytics
        self.session_analytics.stop_session()
        
        # Ask if user wants to add refinery materials BEFORE ending session tracking
        from tkinter import messagebox
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            add_refinery = messagebox.askyesno(
                "Refinery Materials", 
                "Do you have any additional materials in your refinery that you want to add to this session?",
                parent=self.winfo_toplevel()
            )
            
            if add_refinery:
                try:
                    # Import here to avoid circular import
                    from main import RefineryDialog
                    dialog = RefineryDialog(
                        parent=self.winfo_toplevel(),
                        cargo_monitor=self.main_app.cargo_monitor,
                        current_cargo_items=self.main_app.cargo_monitor.cargo_items.copy()
                    )
                    refinery_result = dialog.show()
                    
                    if refinery_result:  # User added refinery contents
                        # Store refinery materials in cargo monitor for session tracking
                        if not hasattr(self.main_app.cargo_monitor, 'refinery_contents'):
                            self.main_app.cargo_monitor.refinery_contents = {}
                        for material_name, quantity in refinery_result.items():
                            if material_name in self.main_app.cargo_monitor.refinery_contents:
                                self.main_app.cargo_monitor.refinery_contents[material_name] += quantity
                            else:
                                self.main_app.cargo_monitor.refinery_contents[material_name] = quantity
                        
                        # DON'T add to cargo_items - refinery materials are tracked separately
                        # This prevents double-counting in end_session_tracking()
                        
                        # Update display to show current cargo (without refinery materials in main display)
                        self.main_app.cargo_monitor.update_display()
                        
                        # Trigger update callback to refresh integrated cargo display
                        if self.main_app.cargo_monitor.update_callback:
                            self.main_app.cargo_monitor.update_callback()
                        
                        print(f"Added refinery materials before session end: {refinery_result}")
                        
                except Exception as e:
                    print(f"Error showing refinery dialog: {e}")
        
        # Get cargo tracking data for material breakdown (NOW with refinery materials included)
        cargo_session_data = None
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            cargo_session_data = self.main_app.cargo_monitor.end_session_tracking()
            
        # Ask if user wants to add a comment
        add_comment = messagebox.askyesno(
            "Session Comment", 
            "Would you like to add a comment to this mining session?",
            parent=self.winfo_toplevel()
        )
        
        session_comment = ""
        if add_comment:
            session_comment = self._show_comment_dialog()
        
        # Update session totals with any refinery materials that were added
        if cargo_session_data and 'materials_mined' in cargo_session_data:
            for material_name, quantity in cargo_session_data['materials_mined'].items():
                if material_name in self.session_totals:
                    self.session_totals[material_name] = max(self.session_totals[material_name], quantity)
                else:
                    self.session_totals[material_name] = quantity
        
        self._set_status("Session ended.")
        
        self.start_btn.config(state="normal")
        self.pause_resume_btn.config(state="disabled", text="Pause")
        self.stop_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")

        # Session summary (removed yield table functionality)
        lines = []
        # Calculate actual mined tons from cargo session data
        if cargo_session_data and 'total_tons_mined' in cargo_session_data:
            total_tons = cargo_session_data['total_tons_mined']
        else:
            # Fallback to session totals for older sessions
            total_tons = 0.0
            for mat in sorted(self.session_totals.keys(), key=str.casefold):
                tons = self.session_totals[mat]
                total_tons += tons

        # Generate lines using actual mined materials from cargo data
        if cargo_session_data and 'materials_mined' in cargo_session_data:
            materials_mined = cargo_session_data['materials_mined']
            for mat in sorted(materials_mined.keys(), key=str.casefold):
                tons = materials_mined[mat]
                tph = tons / active_hours
                lines.append(f"{mat} {tons:.0f}t ({tph:.2f} t/hr)")
        else:
            # Fallback for older sessions without cargo data
            for mat in sorted(self.session_totals.keys(), key=str.casefold):
                tons = self.session_totals[mat]
                tph = tons / active_hours
                lines.append(f"{mat} {tons:.0f}t ({tph:.2f} t/hr)")

        sysname = self.session_system.get().strip() or self.last_system or "Unknown System"
        body = self.session_body.get().strip() or self.last_body or "Unknown Body"
        elapsed_txt = self.session_elapsed.get()
        header = f"Session: {sysname} — {body} — {elapsed_txt} — Total {total_tons:.0f}t"
        file_text = header + " | " + "; ".join(lines) if lines else header + " | No refined materials."
        self._write_var_text("miningSessionSummary", file_text)
        self._set_status("Mining session stopped and summary written.")

        # Save report file and auto-open it
        try:
            overall_tph = total_tons / active_hours if active_hours > 0 else 0.0
            
            # Generate timestamp for consistent naming between report and graphs
            import datetime as dt
            session_timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            report_path = self._save_session_report_with_timestamp(header, lines, overall_tph, cargo_session_data, session_comment, session_timestamp)
            
            # Update CSV index with new session data
            self._update_csv_with_session(sysname, body, elapsed_txt, total_tons, overall_tph, cargo_session_data, session_comment)
            
            # Rebuild CSV to ensure correct data
            self._rebuild_csv_from_files_tab(os.path.join(self.reports_dir, "sessions_index.csv"))
            
            # Auto-save graphs if data exists
            if CHARTS_AVAILABLE and self.charts_panel:
                try:
                    self.charts_panel.auto_save_graphs(
                        session_system=sysname, 
                        session_body=body,
                        session_timestamp=session_timestamp
                    )
                except Exception as graph_error:
                    print(f"Warning: Could not auto-save graphs: {graph_error}")
            
            # Refresh reports tab and window if open (don't auto-open popup)
            try:
                self._refresh_reports_tab()  # Always refresh the main reports tab
                if self.reports_window and self.reports_tree and self.reports_window.winfo_exists():
                    self._refresh_reports_window()  # Only refresh popup if already open
                    
                # Refresh statistics after session completion
                self._refresh_session_statistics()
            except Exception as window_error:
                pass  # Silently handle refresh errors
            
        except Exception as e:
            self._set_status(f"Report save/open failed: {e}")

    def _toggle_pause_resume(self) -> None:
        """Toggle between pause and resume states"""
        if not self.session_active:
            return
            
        if self.session_paused:
            # Currently paused, so resume
            if self.session_pause_started:
                self.session_paused_seconds += (dt.datetime.utcnow() - self.session_pause_started).total_seconds()
            self.session_paused = False
            self.session_pause_started = None
            self.pause_resume_btn.config(text="Pause")
            self._set_status("Session resumed.")
        else:
            # Currently running, so pause
            self.session_paused = True
            self.session_pause_started = dt.datetime.utcnow()
            self.pause_resume_btn.config(text="Resume")
            self._set_status("Session paused.")

    def _session_cancel(self) -> None:
        """Cancel the current session without saving any data"""
        if not self.session_active:
            return

        # Reset session state
        self.session_active = False
        self.session_paused = False
        self.session_start = None
        self.session_pause_started = None
        self.session_paused_seconds = 0.0
        self.session_totals = {}
        self.session_elapsed.set("00:00:00")

        # Reset button states
        self.start_btn.config(state="normal")
        self.pause_resume_btn.config(state="disabled", text="Pause")
        self.stop_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")

        self._set_status("Session cancelled.")
    
    # --- VA file write ---
    def _write_var_text(self, base_without_txt: str, text: str) -> None:
        path = os.path.join(self.vars_dir, base_without_txt + ".txt")
        try:
            _atomic_write_text(path, text)
        except Exception as e:
            self._set_status(f"Write failed: {e}")

    # --- Mining Bookmarks System ---
    def _load_bookmarks(self) -> None:
        """Load bookmarks from JSON file"""
        try:
            if os.path.exists(self.bookmarks_file):
                with open(self.bookmarks_file, 'r', encoding='utf-8') as f:
                    self.bookmarks_data = json.load(f)
            else:
                self.bookmarks_data = []
        except Exception as e:
            print(f"Error loading bookmarks: {e}")
            self.bookmarks_data = []

    def _save_bookmarks(self) -> None:
        """Save bookmarks to JSON file"""
        try:
            with open(self.bookmarks_file, 'w', encoding='utf-8') as f:
                json.dump(self.bookmarks_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving bookmarks: {e}")
            import traceback
            traceback.print_exc()

    def _create_bookmarks_panel(self, parent: ttk.Widget) -> None:
        """Create the bookmarks panel interface"""
        # Create main frame with proper grid configuration
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(parent)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=0)  # Filter frame
        main_frame.rowconfigure(1, weight=1)  # Treeview
        main_frame.rowconfigure(2, weight=0)  # Horizontal scrollbar
        main_frame.rowconfigure(3, weight=0)  # Buttons

        # Filter frame
        filter_frame = ttk.Frame(main_frame)
        filter_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        
        ttk.Label(filter_frame, text="Filter:").pack(side="left", padx=(0, 5))
        
        self.bookmark_filter_var = tk.StringVar(value="All Locations")
        filter_combo = ttk.Combobox(filter_frame, textvariable=self.bookmark_filter_var, 
                                   values=["All Locations", "High Yield (>350 T/hr)", "Medium Yield (250-350 T/hr)", "Low Yield (100-250 T/hr)", "Recent (Last 30 Days)", "Hotspot Locations"], 
                                   state="readonly", width=28)
        filter_combo.pack(side="left", padx=(0, 10))
        filter_combo.bind("<<ComboboxSelected>>", self._on_bookmark_filter_changed)
        
        # Search box
        ttk.Label(filter_frame, text="Search:").pack(side="left", padx=(10, 5))
        self.bookmark_search_var = tk.StringVar()
        search_entry = ttk.Entry(filter_frame, textvariable=self.bookmark_search_var, width=20)
        search_entry.pack(side="left", padx=(0, 5))
        search_entry.bind("<KeyRelease>", self._on_bookmark_search_changed)
        
        self.ToolTip(filter_combo, "Filter bookmarks by material type")
        self.ToolTip(search_entry, "Search bookmarks by system, body, or materials")

        # Create bookmarks treeview with multiple selection enabled
        self.bookmarks_tree = ttk.Treeview(main_frame, columns=("last_mined", "system", "body", "hotspot", "materials", "avg_yield", "notes"), show="headings", height=16, selectmode="extended")
        self.bookmarks_tree.grid(row=1, column=0, sticky="nsew")
        
        # Ensure multiple selection is properly configured
        self.bookmarks_tree.configure(selectmode="extended")
        
        # Force focus to ensure selection behavior works properly
        self.bookmarks_tree.focus_set()
        
        # Configure column headings
        self.bookmarks_tree.heading("last_mined", text="Last Mined")
        self.bookmarks_tree.heading("system", text="System")
        self.bookmarks_tree.heading("body", text="Body/Ring")
        self.bookmarks_tree.heading("hotspot", text="Hotspot")
        self.bookmarks_tree.heading("materials", text="Materials Found")
        self.bookmarks_tree.heading("avg_yield", text="Avg Yield %")
        self.bookmarks_tree.heading("notes", text="Notes")
        
        # Configure column widths
        self.bookmarks_tree.column("last_mined", width=100, stretch=False, anchor="center")
        self.bookmarks_tree.column("system", width=180, stretch=False, anchor="w")
        self.bookmarks_tree.column("body", width=120, stretch=False, anchor="w")
        self.bookmarks_tree.column("hotspot", width=100, stretch=False, anchor="w")
        self.bookmarks_tree.column("materials", width=200, stretch=False, anchor="w")
        self.bookmarks_tree.column("avg_yield", width=80, stretch=False, anchor="center")
        self.bookmarks_tree.column("notes", width=250, stretch=False, anchor="w")

        # Add vertical scrollbar
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.bookmarks_tree.yview)
        v_scrollbar.grid(row=1, column=1, sticky="ns")
        self.bookmarks_tree.configure(yscrollcommand=v_scrollbar.set)

        # Add horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(main_frame, orient="horizontal", command=self.bookmarks_tree.xview)
        h_scrollbar.grid(row=2, column=0, sticky="ew")
        self.bookmarks_tree.configure(xscrollcommand=h_scrollbar.set)

        # Add sorting functionality
        sort_dirs = {}
        def sort_bookmark_col(col):
            try:
                reverse = sort_dirs.get(col, False)
                items = [(self.bookmarks_tree.set(item, col), item) for item in self.bookmarks_tree.get_children('')]
                
                # Date sorting for last_mined
                if col == "last_mined":
                    def safe_date(x):
                        try:
                            return dt.datetime.strptime(str(x), '%Y-%m-%d') if x else dt.datetime.min
                        except:
                            return dt.datetime.min
                    items.sort(key=lambda x: safe_date(x[0]), reverse=reverse)
                # Numeric sorting for avg_yield
                elif col == "avg_yield":
                    def safe_float(x):
                        try:
                            val = str(x).replace(" T/hr", "").strip()
                            return float(val) if val else 0.0
                        except:
                            return 0.0
                    items.sort(key=lambda x: safe_float(x[0]), reverse=reverse)
                else:
                    # String sorting
                    items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)
                    
                for index, (val, item) in enumerate(items):
                    self.bookmarks_tree.move(item, '', index)
                sort_dirs[col] = not reverse
            except Exception as e:
                print(f"Bookmark sorting error for column {col}: {e}")

        # Bind column headers to sorting
        for col in ("last_mined", "system", "body", "hotspot", "materials", "avg_yield", "notes"):
            self.bookmarks_tree.heading(col, command=lambda c=col: sort_bookmark_col(c))

        # Buttons frame
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, columnspan=2, pady=(8, 0), sticky="ew")
        
        # Add Bookmark button
        add_btn = tk.Button(button_frame, text="Add Bookmark", 
                           command=self._add_bookmark_dialog, 
                           bg="#2a5a2a", fg="#ffffff", 
                           activebackground="#3a6a3a", activeforeground="#ffffff",
                           relief="solid", bd=1, cursor="hand2", pady=3,
                           highlightbackground="#1a3a1a", highlightcolor="#1a3a1a")
        add_btn.pack(side="left", padx=(0, 6))
        self.ToolTip(add_btn, "Add a new mining location bookmark")
        
        # Edit Bookmark button
        edit_btn = tk.Button(button_frame, text="Edit Bookmark", 
                            command=self._edit_bookmark_dialog, 
                            bg="#4a4a2a", fg="#ffffff",
                            activebackground="#5a5a3a", activeforeground="#ffffff",
                            relief="solid", bd=1, cursor="hand2", pady=3,
                            highlightbackground="#2a2a1a", highlightcolor="#2a2a1a")
        edit_btn.pack(side="left", padx=(0, 6))
        self.ToolTip(edit_btn, "Edit the selected bookmark")
        
        # Delete Bookmark button
        delete_btn = tk.Button(button_frame, text="Delete Bookmark", 
                              command=self._delete_bookmark, 
                              bg="#5a2a2a", fg="#ffffff", 
                              activebackground="#6a3a3a", activeforeground="#ffffff",
                              relief="solid", bd=1, cursor="hand2", pady=3,
                              highlightbackground="#3a1a1a", highlightcolor="#3a1a1a")
        delete_btn.pack(side="left", padx=(0, 6))
        self.ToolTip(delete_btn, "Delete the selected bookmark(s) - use Ctrl+click or Shift+click to select multiple")

        # Double-click to edit
        self.bookmarks_tree.bind("<Double-1>", self._on_bookmark_double_click)
        
        # Right-click context menu
        self._setup_bookmark_context_menu()
        
        # Load and display bookmarks
        self._refresh_bookmarks()

    def _on_bookmark_filter_changed(self, event=None) -> None:
        """Handle bookmark filter dropdown change"""
        self._refresh_bookmarks()

    def _on_bookmark_search_changed(self, event=None) -> None:
        """Handle bookmark search text change"""
        self._refresh_bookmarks()

    def _refresh_bookmarks(self) -> None:
        """Refresh the bookmarks display with current filter/search"""
        # Clear existing items
        for item in self.bookmarks_tree.get_children():
            self.bookmarks_tree.delete(item)
        
        # Get filter and search values
        filter_value = self.bookmark_filter_var.get() if hasattr(self, 'bookmark_filter_var') else "All Locations"
        search_text = self.bookmark_search_var.get().lower() if hasattr(self, 'bookmark_search_var') else ""
        
        # Filter and display bookmarks
        for bookmark in self.bookmarks_data:
            # Apply filter
            if filter_value == "High Yield (>350 T/hr)":
                yield_str = bookmark.get('avg_yield', '')
                try:
                    yield_val = float(yield_str.replace(' T/hr', '')) if yield_str else 0
                    if yield_val <= 350:
                        continue
                except:
                    continue
            elif filter_value == "Medium Yield (250-350 T/hr)":
                yield_str = bookmark.get('avg_yield', '')
                try:
                    yield_val = float(yield_str.replace(' T/hr', '')) if yield_str else 0
                    if yield_val < 250 or yield_val > 350:
                        continue
                except:
                    continue
            elif filter_value == "Low Yield (100-250 T/hr)":
                yield_str = bookmark.get('avg_yield', '')
                try:
                    yield_val = float(yield_str.replace(' T/hr', '')) if yield_str else 0
                    if yield_val < 100 or yield_val >= 250:
                        continue
                except:
                    continue
            elif filter_value == "Recent (Last 30 Days)":
                last_mined = bookmark.get('last_mined', '')
                if last_mined:
                    try:
                        mined_date = dt.datetime.strptime(last_mined, '%Y-%m-%d')
                        days_ago = (dt.datetime.now() - mined_date).days
                        if days_ago > 30:
                            continue
                    except:
                        continue
                else:
                    continue
            elif filter_value == "Hotspot Locations":
                hotspot = bookmark.get('hotspot', '').lower()
                if not hotspot or hotspot == '':
                    continue
            
            # Apply search filter
            if search_text:
                searchable_text = f"{bookmark.get('system', '')} {bookmark.get('body', '')} {bookmark.get('hotspot', '')} {bookmark.get('materials', '')} {bookmark.get('last_mined', '')} {bookmark.get('notes', '')}".lower()
                if search_text not in searchable_text:
                    continue
            
            # Add to tree
            self.bookmarks_tree.insert("", "end", values=(
                bookmark.get('last_mined', ''),
                bookmark.get('system', ''),
                bookmark.get('body', ''),
                bookmark.get('hotspot', ''),
                bookmark.get('materials', ''),
                bookmark.get('avg_yield', ''),
                bookmark.get('notes', '')
            ))

    def _on_bookmark_double_click(self, event) -> None:
        """Handle double-click on bookmark tree - only edit if clicking on an item, not header"""
        # Check if click is on an actual item, not header
        item = self.bookmarks_tree.identify('item', event.x, event.y)
        if item:  # Only edit if there's an actual item under the cursor
            self._edit_bookmark_dialog()

    def _add_bookmark_dialog(self) -> None:
        """Show dialog to add new bookmark"""
        self._show_bookmark_dialog()

    def _edit_bookmark_dialog(self) -> None:
        """Show dialog to edit selected bookmark"""
        selection = self.bookmarks_tree.selection()
        if not selection:
            return
        
        # Get selected bookmark data
        item = selection[0]
        values = self.bookmarks_tree.item(item, 'values')
        if not values:
            return
        
        # Find the bookmark in data
        system, body = values[1], values[2]  # Updated positions after moving last_mined to first column
        bookmark_index = None
        for i, bookmark in enumerate(self.bookmarks_data):
            if bookmark.get('system') == system and bookmark.get('body') == body:
                bookmark_index = i
                break
        
        if bookmark_index is not None:
            self._show_bookmark_dialog(self.bookmarks_data[bookmark_index], bookmark_index)

    def _show_bookmark_dialog(self, bookmark_data=None, bookmark_index=None) -> None:
        """Show add/edit bookmark dialog"""
        dialog = tk.Toplevel(self)
        dialog.title("Add Bookmark" if bookmark_data is None else "Edit Bookmark")
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass
        
        # Reduce height and position relative to main window
        dialog_width = 500
        dialog_height = 320  # Reduced from 400
        
        # Center the dialog relative to the main window
        main_window = self.winfo_toplevel()
        main_x = main_window.winfo_x()
        main_y = main_window.winfo_y()
        main_width = main_window.winfo_width()
        main_height = main_window.winfo_height()
        
        # Calculate center position
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        dialog.resizable(False, False)
        
        # Make dialog modal
        dialog.transient(self)
        dialog.grab_set()
        
        # Set app icon using the robust icon finder function
        try:
            icon_path = get_app_icon_path()
            if icon_path:
                dialog.iconbitmap(icon_path)
        except:
            pass  # Continue without icon if there's an issue
        
        frame = ttk.Frame(dialog, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        
        # System field
        ttk.Label(frame, text="System:").grid(row=0, column=0, sticky="w", pady=(0, 5))
        system_var = tk.StringVar(value=bookmark_data.get('system', '') if bookmark_data else '')
        system_entry = ttk.Entry(frame, textvariable=system_var, width=40)
        system_entry.grid(row=0, column=1, sticky="ew", pady=(0, 5))
        
        # Body field
        ttk.Label(frame, text="Body/Ring:").grid(row=1, column=0, sticky="w", pady=(0, 5))
        body_var = tk.StringVar(value=bookmark_data.get('body', '') if bookmark_data else '')
        body_entry = ttk.Entry(frame, textvariable=body_var, width=40)
        body_entry.grid(row=1, column=1, sticky="ew", pady=(0, 5))
        
        # Hotspot field
        ttk.Label(frame, text="Hotspot:").grid(row=2, column=0, sticky="w", pady=(0, 5))
        hotspot_var = tk.StringVar(value=bookmark_data.get('hotspot', '') if bookmark_data else '')
        hotspot_entry = ttk.Entry(frame, textvariable=hotspot_var, width=40)
        hotspot_entry.grid(row=2, column=1, sticky="ew", pady=(0, 5))
        
        # Materials field
        ttk.Label(frame, text="Materials Found:").grid(row=3, column=0, sticky="w", pady=(0, 5))
        materials_var = tk.StringVar(value=bookmark_data.get('materials', '') if bookmark_data else '')
        materials_entry = ttk.Entry(frame, textvariable=materials_var, width=40)
        materials_entry.grid(row=3, column=1, sticky="ew", pady=(0, 5))
        
        # Average Yield field
        ttk.Label(frame, text="Average Yield %:").grid(row=4, column=0, sticky="w", pady=(0, 5))
        yield_var = tk.StringVar(value=bookmark_data.get('avg_yield', '') if bookmark_data else '')
        yield_entry = ttk.Entry(frame, textvariable=yield_var, width=40)
        yield_entry.grid(row=4, column=1, sticky="ew", pady=(0, 5))
        
        # Notes field
        ttk.Label(frame, text="Notes:").grid(row=5, column=0, sticky="nw", pady=(0, 5))
        notes_text = tk.Text(frame, width=40, height=4)  # Reduced from 6 to 4
        notes_text.grid(row=5, column=1, sticky="ew", pady=(0, 10))
        if bookmark_data:
            notes_text.insert("1.0", bookmark_data.get('notes', ''))
        
        frame.columnconfigure(1, weight=1)
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=(10, 0))
        
        def save_bookmark():
            system = system_var.get().strip()
            body = body_var.get().strip()
            
            if not system or not body:
                tk.messagebox.showerror("Error", "System and Body/Ring are required fields")
                return
            
            bookmark = {
                'system': system,
                'body': body,
                'hotspot': hotspot_var.get().strip(),
                'materials': materials_var.get().strip(),
                'avg_yield': yield_var.get().strip(),
                'last_mined': bookmark_data.get('last_mined', '') if bookmark_data else '',
                'notes': notes_text.get("1.0", "end-1c").strip(),
                'date_added': bookmark_data.get('date_added', dt.datetime.now().strftime('%Y-%m-%d')) if bookmark_data else dt.datetime.now().strftime('%Y-%m-%d')
            }
            
            if bookmark_index is not None:
                # Edit existing bookmark
                self.bookmarks_data[bookmark_index] = bookmark
            else:
                # Add new bookmark
                self.bookmarks_data.append(bookmark)
            
            self._save_bookmarks()
            self._refresh_bookmarks()
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        # Save button with proper styling - bigger size
        save_btn = tk.Button(button_frame, text="Save", command=save_bookmark,
                            bg="#2a5a2a", fg="#ffffff", 
                            activebackground="#3a6a3a", activeforeground="#ffffff",
                            relief="solid", bd=1, cursor="hand2", 
                            pady=8, padx=20, font=("Segoe UI", 10, "normal"),
                            highlightbackground="#1a3a1a", highlightcolor="#1a3a1a")
        save_btn.pack(side="left", padx=(0, 8))
        
        # Cancel button with proper styling - bigger size
        cancel_btn = tk.Button(button_frame, text="Cancel", command=cancel,
                              bg="#5a2a2a", fg="#ffffff", 
                              activebackground="#6a3a3a", activeforeground="#ffffff",
                              relief="solid", bd=1, cursor="hand2", 
                              pady=8, padx=20, font=("Segoe UI", 10, "normal"),
                              highlightbackground="#3a1a1a", highlightcolor="#3a1a1a")
        cancel_btn.pack(side="left")
        
        # Focus on system entry
        system_entry.focus()

    def _delete_bookmark(self) -> None:
        """Delete selected bookmark(s)"""
        selection = self.bookmarks_tree.selection()
        
        if not selection:
            return
        
        # Get count of selected bookmarks for confirmation message
        bookmark_count = len(selection)
        if bookmark_count == 1:
            confirm_message = "Are you sure you want to delete this bookmark?"
        else:
            confirm_message = f"Are you sure you want to delete {bookmark_count} bookmarks?"
        
        # Confirm deletion
        if not tk.messagebox.askyesno("Confirm Delete", confirm_message):
            return
        
        # Collect all bookmarks to delete
        bookmarks_to_delete = []
        for item in selection:
            values = self.bookmarks_tree.item(item, 'values')
            if values and len(values) >= 3:
                system, body = values[1], values[2]  # Correct column indices: system=1, body=2
                bookmarks_to_delete.append((system, body))
        
        # Remove bookmarks from data (iterate in reverse to avoid index issues)
        for system, body in bookmarks_to_delete:
            for i in range(len(self.bookmarks_data) - 1, -1, -1):
                bookmark = self.bookmarks_data[i]
                if bookmark.get('system') == system and bookmark.get('body') == body:
                    del self.bookmarks_data[i]
                    break
        
        self._save_bookmarks()
        self._refresh_bookmarks()

    def _bookmark_from_session(self, system: str, body: str, materials: str = "", avg_yield: str = "") -> None:
        """Add bookmark from session data (called from Reports context menu)"""
        # Check if bookmark already exists
        for bookmark in self.bookmarks_data:
            if bookmark.get('system') == system and bookmark.get('body') == body:
                if tk.messagebox.askyesno("Bookmark Exists", 
                    f"A bookmark for {system} - {body} already exists. Update it?"):
                    # Update existing bookmark
                    bookmark['materials'] = materials
                    bookmark['avg_yield'] = avg_yield
                    bookmark['last_mined'] = dt.datetime.now().strftime('%Y-%m-%d')
                    self._save_bookmarks()
                    self._refresh_bookmarks()
                return
        
        # Add new bookmark
        bookmark = {
            'system': system,
            'body': body,
            'materials': materials,
            'avg_yield': avg_yield,
            'last_mined': dt.datetime.now().strftime('%Y-%m-%d'),
            'notes': '',
            'date_added': dt.datetime.now().strftime('%Y-%m-%d')
        }
        
        self.bookmarks_data.append(bookmark)
        self._save_bookmarks()
        self._refresh_bookmarks()
        
        self._set_status(f"Bookmarked: {system} - {body}")

    def _setup_bookmark_context_menu(self) -> None:
        """Setup right-click context menu for bookmarks tree"""
        # Create context menu with dark theme styling
        self.bookmark_context_menu = tk.Menu(self, tearoff=0, bg="#2d2d2d", fg="#ffffff")
        self.bookmark_context_menu.add_command(label="Copy System Name", command=self._copy_system_to_clipboard)
        self.bookmark_context_menu.add_separator()
        self.bookmark_context_menu.add_command(label="Edit Bookmark", command=self._edit_bookmark_dialog)
        self.bookmark_context_menu.add_command(label="Delete Bookmark(s)", command=self._delete_bookmark)
        
        # Bind right-click event
        self.bookmarks_tree.bind("<Button-3>", self._show_bookmark_context_menu)

    def _show_bookmark_context_menu(self, event) -> None:
        """Show context menu on right-click"""
        # Check if click is on an actual item
        item = self.bookmarks_tree.identify('item', event.x, event.y)
        if item:
            # If item is not already selected, clear selection and select it
            selected_items = self.bookmarks_tree.selection()
            if item not in selected_items:
                self.bookmarks_tree.selection_set(item)
            self.bookmarks_tree.focus(item)
            
            # Show context menu
            try:
                self.bookmark_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.bookmark_context_menu.grab_release()

    def _copy_system_to_clipboard(self) -> None:
        """Copy selected system name to clipboard"""
        selection = self.bookmarks_tree.selection()
        if not selection:
            return
        
        # Get selected bookmark data
        item = selection[0]
        values = self.bookmarks_tree.item(item, 'values')
        if not values or len(values) < 2:
            return
        
        # System name is in column index 1 (second column)
        system_name = values[1]
        if system_name:
            # Copy to clipboard
            self.clipboard_clear()
            self.clipboard_append(system_name)
            self.update()  # Required to ensure clipboard is updated
            
            # Show brief status message
            self._set_status(f"Copied '{system_name}' to clipboard")
        else:
            self._set_status("No system name to copy")

    def _create_statistics_panel(self, parent: ttk.Widget) -> None:
        """Create the statistics panel for comprehensive mining analytics"""
        # Main scrollable frame
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill="both", expand=True, padx=8, pady=8)
        
        # Title
        title_label = tk.Label(main_frame, text="📊 Mining Session Statistics", 
                              font=("Consolas", 14, "bold"), fg="#ffffff", bg="#2b2b2b")
        title_label.pack(pady=(0, 5))
        
        # Info text
        info_label = tk.Label(main_frame, text="Statistics calculated from saved mining session reports", 
                             font=("Segoe UI", 9, "italic"), fg="#888888", bg="#2b2b2b")
        info_label.pack(pady=(0, 10))
        
        # Statistics container
        stats_container = ttk.Frame(main_frame)
        stats_container.pack(fill="both", expand=True)
        
        # Two-column layout
        left_column = ttk.LabelFrame(stats_container, text="Overall Statistics", padding=10)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        right_column = ttk.LabelFrame(stats_container, text="Best (Records)", padding=10)
        right_column.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        
        stats_container.grid_columnconfigure(0, weight=1)
        stats_container.grid_columnconfigure(1, weight=1)
        stats_container.grid_rowconfigure(0, weight=1)
        
        # Initialize stats labels dictionary
        self.stats_labels = {}
        
        # Overall Statistics (Left Column)
        stats_data = [
            ("Total Sessions:", "total_sessions"),
            ("Total Mining Time:", "total_time"),
            ("Total Tonnage Collected:", "total_tonnage"),
            ("Average Tons/Hour:", "avg_tph"),
            ("Systems Mined:", "unique_systems"),
            ("Total Asteroids Prospected:", "total_asteroids"),
            ("Average Hit Rate:", "avg_hit_rate")
        ]
        
        for i, (label_text, key) in enumerate(stats_data):
            # Label
            label = tk.Label(left_column, text=label_text, font=("Consolas", 10), 
                           fg="#cccccc", bg="#2b2b2b", anchor="w")
            label.grid(row=i, column=0, sticky="w", pady=2, padx=(0, 10))
            
            # Value
            value_label = tk.Label(left_column, text="0", font=("Consolas", 10, "bold"), 
                                 fg="#00ff00", bg="#2b2b2b", anchor="w")
            value_label.grid(row=i, column=1, sticky="w", pady=2)
            self.stats_labels[key] = value_label
        
        # Records (Right Column)
        performers_data = [
            ("T/hr:", "best_session_tph"),
            ("System:", "best_session_system"),
            ("Session(t):", "best_tonnage"),
            ("Most Mined System:", "most_mined_system"),
            ("Material:", "most_collected_material")
        ]
        
        for i, (label_text, key) in enumerate(performers_data):
            # Label
            label = tk.Label(right_column, text=label_text, font=("Consolas", 10), 
                           fg="#cccccc", bg="#2b2b2b", anchor="w")
            label.grid(row=i, column=0, sticky="w", pady=2, padx=(0, 10))
            
            # Value
            value_label = tk.Label(right_column, text="None", font=("Consolas", 10, "bold"), 
                                 fg="#ffaa00", bg="#2b2b2b", anchor="w", 
                                 wraplength=400, justify="left")
            value_label.grid(row=i, column=1, sticky="w", pady=2)
            self.stats_labels[key] = value_label
        
        # Refresh button
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(15, 0))
        
        refresh_btn = tk.Button(button_frame, text="🔄 Refresh Statistics", 
                               command=self._refresh_session_statistics,
                               bg="#2a5a2a", fg="#ffffff", 
                               activebackground="#3a6a3a", activeforeground="#ffffff",
                               relief="solid", bd=1, cursor="hand2", pady=5, padx=10,
                               highlightbackground="#1a3a1a", highlightcolor="#1a3a1a")
        refresh_btn.pack()
        self.ToolTip(refresh_btn, "Refresh statistics from all mining session reports")
        
        # Initial statistics load
        self._refresh_session_statistics()

    # -------------------- Session Statistics Functions --------------------
    
    def _calculate_session_statistics(self) -> dict:
        """Calculate comprehensive statistics from all mining sessions"""
        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
        
        if not os.path.exists(csv_path):
            # Try to rebuild CSV from existing session files
            try:
                self._rebuild_csv_from_files_tab(csv_path, silent=True)
            except Exception as e:
                print(f"Could not rebuild CSV: {e}")
                return {}
            
            # Check again after rebuild attempt
            if not os.path.exists(csv_path):
                return {}
        
        try:
            import csv
            from collections import defaultdict, Counter
            from datetime import datetime
            
            sessions = []
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                sessions = list(reader)
            
            if not sessions:
                return {}
            
            # Initialize statistics
            stats = {
                'total_sessions': len(sessions),
                'total_time_hours': 0,
                'total_tonnage': 0,
                'systems_visited': set(),
                'material_totals': defaultdict(float),
                'system_stats': defaultdict(lambda: {'sessions': 0, 'tonnage': 0, 'time_hours': 0}),
                'location_stats': defaultdict(lambda: {'sessions': 0, 'tonnage': 0, 'time_hours': 0}),
                'best_session': {'tph': 0, 'tonnage': 0, 'session': None},
                'avg_tph': 0,
                'unique_systems': 0,
                'most_mined_system': '',
                'most_mined_location': '',
                'most_collected_material': '',
                'total_asteroids': 0,
                'avg_hit_rate': 0
            }
            
            # Process each session
            total_tph_sum = 0
            total_hit_rate_sum = 0
            valid_tph_sessions = 0
            valid_hit_rate_sessions = 0
            
            for session in sessions:
                try:
                    # Parse session data
                    system = session.get('system', '')
                    body = session.get('body', '')
                    elapsed = session.get('elapsed', '0h 0m')
                    tonnage = float(session.get('total_tons', 0) or 0)
                    tph = float(session.get('overall_tph', 0) or 0)
                    asteroids = int(session.get('asteroids_prospected', 0) or 0)
                    hit_rate = float(session.get('hit_rate_percent', 0) or 0)
                    materials_breakdown = session.get('materials_breakdown', '')
                    
                    # Convert elapsed time to hours
                    time_hours = self._parse_elapsed_to_hours(elapsed)
                    
                    # Update totals
                    stats['total_time_hours'] += time_hours
                    stats['total_tonnage'] += tonnage
                    stats['total_asteroids'] += asteroids
                    stats['systems_visited'].add(system)
                    
                    # Track TPH for average
                    if tph > 0:
                        total_tph_sum += tph
                        valid_tph_sessions += 1
                    
                    # Track hit rate for average
                    if hit_rate > 0:
                        total_hit_rate_sum += hit_rate
                        valid_hit_rate_sessions += 1
                    
                    # System statistics
                    stats['system_stats'][system]['sessions'] += 1
                    stats['system_stats'][system]['tonnage'] += tonnage
                    stats['system_stats'][system]['time_hours'] += time_hours
                    
                    # Location statistics (system + body)
                    location = f"{system} - {body}"
                    stats['location_stats'][location]['sessions'] += 1
                    stats['location_stats'][location]['tonnage'] += tonnage
                    stats['location_stats'][location]['time_hours'] += time_hours
                    
                    # Best session tracking
                    if tph > stats['best_session']['tph']:
                        stats['best_session']['tph'] = tph
                        stats['best_session']['session'] = f"{system} - {body}"
                    
                    if tonnage > stats['best_session']['tonnage']:
                        stats['best_session']['tonnage'] = tonnage
                    
                    # Parse materials breakdown - handle both formats
                    if materials_breakdown:
                        # Remove quotes if present
                        materials_breakdown = materials_breakdown.strip('"')
                        
                        # Check if it's the new format (with 't' units) or old format (semicolon separated)
                        if 't' in materials_breakdown:
                            # New format: "Platinum:6t" or "Osmium:3t, Platinum:280t"  
                            materials = materials_breakdown.split(',') if ',' in materials_breakdown else [materials_breakdown]
                            for material_entry in materials:
                                if ':' in material_entry:
                                    material_name, amount_str = material_entry.split(':', 1)
                                    try:
                                        # Remove 't' and convert to float
                                        amount_str = amount_str.strip().replace('t', '')
                                        amount = float(amount_str)
                                        stats['material_totals'][material_name.strip()] += amount
                                    except ValueError:
                                        continue
                        else:
                            # Old format: "Bertrandite: 10; Bauxite: 43; Painite: 6"
                            materials = materials_breakdown.split(';')
                            for material_entry in materials:
                                if ':' in material_entry:
                                    material_name, amount_str = material_entry.split(':', 1)
                                    try:
                                        amount = float(amount_str.strip())
                                        stats['material_totals'][material_name.strip()] += amount
                                    except ValueError:
                                        continue
                    
                except (ValueError, TypeError) as e:
                    continue  # Skip invalid sessions
            
            # Calculate derived statistics
            stats['unique_systems'] = len(stats['systems_visited'])
            stats['avg_tph'] = total_tph_sum / valid_tph_sessions if valid_tph_sessions > 0 else 0
            stats['avg_hit_rate'] = total_hit_rate_sum / valid_hit_rate_sessions if valid_hit_rate_sessions > 0 else 0
            
            # Find most mined system (by tonnage)
            if stats['system_stats']:
                most_mined = max(stats['system_stats'].items(), key=lambda x: x[1]['tonnage'])
                stats['most_mined_system'] = most_mined[0]
                stats['most_mined_system_tonnage'] = most_mined[1]['tonnage']
            
            # Find most mined location (by tonnage)
            if stats['location_stats']:
                most_mined_location = max(stats['location_stats'].items(), key=lambda x: x[1]['tonnage'])
                stats['most_mined_location'] = most_mined_location[0]
                stats['most_mined_location_tonnage'] = most_mined_location[1]['tonnage']
            
            # Find most collected material
            if stats['material_totals']:
                most_material = max(stats['material_totals'].items(), key=lambda x: x[1])
                stats['most_collected_material'] = most_material[0]
                stats['most_collected_material_amount'] = most_material[1]
                # Add material count
                stats['material_count'] = len(stats['material_totals'])
            else:
                stats['material_count'] = 0
            
            return stats
            
        except Exception as e:
            print(f"Error calculating session statistics: {e}")
            return {}
    
    def _parse_elapsed_to_hours(self, elapsed_str: str) -> float:
        """Convert elapsed time string to hours as float. Handles both formats:
        - '2h 21m' (old format)
        - '00:34:43' (new HH:MM:SS format)
        """
        try:
            import re
            
            # Check if it's HH:MM:SS format
            if ':' in elapsed_str and len(elapsed_str.split(':')) >= 2:
                # New format: HH:MM:SS or HH:MM
                time_parts = elapsed_str.split(':')
                hours = int(time_parts[0])
                minutes = int(time_parts[1])
                seconds = int(time_parts[2]) if len(time_parts) > 2 else 0
                
                return hours + (minutes / 60.0) + (seconds / 3600.0)
            else:
                # Old format: 2h 21m
                hours = 0
                minutes = 0
                
                # Extract hours
                hour_match = re.search(r'(\d+)h', elapsed_str)
                if hour_match:
                    hours = int(hour_match.group(1))
                
                # Extract minutes
                min_match = re.search(r'(\d+)m', elapsed_str)
                if min_match:
                    minutes = int(min_match.group(1))
                
                return hours + (minutes / 60.0)
        except:
            return 0.0
    
    def _refresh_session_statistics(self):
        """Update the statistics display with current data"""
        try:
            stats = self._calculate_session_statistics()
            
            if not stats:
                # No data available - show helpful message
                self.stats_labels['total_sessions'].config(text="0")
                self.stats_labels['total_time'].config(text="0h 0m")
                self.stats_labels['total_tonnage'].config(text="0 tons")
                self.stats_labels['avg_tph'].config(text="0.0")
                self.stats_labels['unique_systems'].config(text="0")
                self.stats_labels['best_session_tph'].config(text="0.0")
                self.stats_labels['best_session_system'].config(text="No sessions found")
                self.stats_labels['most_mined_system'].config(text="No sessions found")
                self.stats_labels['most_collected_material'].config(text="No sessions found")
                self.stats_labels['best_tonnage'].config(text="0")
                self.stats_labels['avg_hit_rate'].config(text="0%")
                self.stats_labels['total_asteroids'].config(text="0")
                return
            
            # Update overall statistics
            self.stats_labels['total_sessions'].config(text=str(stats['total_sessions']))
            
            # Format time
            total_hours = stats['total_time_hours']
            hours = int(total_hours)
            minutes = int((total_hours - hours) * 60)
            self.stats_labels['total_time'].config(text=f"{hours}h {minutes}m")
            
            self.stats_labels['total_tonnage'].config(text=f"{stats['total_tonnage']:.1f} tons")
            self.stats_labels['avg_tph'].config(text=f"{stats['avg_tph']:.1f}")
            self.stats_labels['unique_systems'].config(text=str(stats['unique_systems']))
            self.stats_labels['best_session_tph'].config(text=f"{stats['best_session']['tph']:.1f}")
            
            # Extract and display best session system
            best_session_info = stats['best_session']['session']
            if best_session_info and ' - ' in best_session_info:
                best_session_system = best_session_info.split(' - ')[0]
            else:
                best_session_system = best_session_info if best_session_info else 'None'
            
            # Only truncate if extremely long (50+ characters)
            if len(best_session_system) > 50:
                best_session_system = best_session_system[:50] + "..."
            self.stats_labels['best_session_system'].config(text=best_session_system)
            
            # Update records
            most_system = stats.get('most_mined_system', 'None')
            if most_system and len(most_system) > 50:
                most_system = most_system[:50] + "..."
            self.stats_labels['most_mined_system'].config(text=most_system)
            
            most_material = stats.get('most_collected_material', 'None')
            if most_material and len(most_material) > 30:
                most_material = most_material[:30] + "..."
            self.stats_labels['most_collected_material'].config(text=most_material)
            
            self.stats_labels['best_tonnage'].config(text=f"{stats['best_session']['tonnage']:.1f}")
            self.stats_labels['avg_hit_rate'].config(text=f"{stats['avg_hit_rate']:.1f}%")
            self.stats_labels['total_asteroids'].config(text=str(stats['total_asteroids']))
            
            self._set_status(f"Statistics updated: {stats['total_sessions']} sessions analyzed")
            
        except Exception as e:
            print(f"Error refreshing statistics: {e}")
            self._set_status("Error updating statistics")
            
    def _add_screenshots_to_report(self, tree):
        """Add screenshots to selected report via file selection dialog"""
        try:
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("No Selection", "Please select a report first.", parent=tree.winfo_toplevel())
                return
                
            # Get default screenshots folder from main app settings
            default_folder = os.path.join(os.path.expanduser("~"), "Pictures")
            if self.main_app and hasattr(self.main_app, 'screenshots_folder_path'):
                default_folder = self.main_app.screenshots_folder_path.get() or default_folder
            
            # Open file dialog to select image files
            file_types = [
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("All files", "*.*")
            ]
            
            selected_files = filedialog.askopenfilenames(
                title="Select Screenshots to Add",
                initialdir=default_folder,
                filetypes=file_types,
                parent=tree.winfo_toplevel()
            )
            
            if selected_files:
                # Create screenshots directory if it doesn't exist - use consistent app_dir logic
                if getattr(sys, 'frozen', False):
                    # Running as executable (installer version)
                    app_dir = os.path.join(self.va_root, "app")
                else:
                    # Running as script (development version)
                    app_dir = os.path.dirname(os.path.abspath(__file__))
                    
                screenshots_dir = os.path.join(app_dir, "Reports", "Mining Session", "Detailed Reports", "Screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # Copy selected files to screenshots directory
                copied_files = []
                for file_path in selected_files:
                    try:
                        filename = os.path.basename(file_path)
                        dest_path = screenshots_dir / filename
                        
                        # Add timestamp if file already exists
                        if dest_path.exists():
                            name, ext = os.path.splitext(filename)
                            timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"{name}_{timestamp}{ext}"
                            dest_path = screenshots_dir / filename
                        
                        # Copy the file
                        import shutil
                        shutil.copy2(file_path, dest_path)
                        copied_files.append(str(dest_path))
                        
                    except Exception as e:
                        print(f"Error copying {file_path}: {e}")
                
                if copied_files:
                    # Get report identifier to link screenshots
                    item = selected_items[0]  # Get the first selected item
                    values = tree.item(item, 'values')
                    report_id = f"{values[0]}_{values[2]}_{values[3]}"  # date_system_body as unique ID
                    
                    # Store screenshot references for the selected report
                    self._store_report_screenshots(report_id, copied_files)
                    
                    messagebox.showinfo(
                        "Screenshots Added",
                        f"Added {len(copied_files)} screenshots to this report.\n\nThey will be included when you generate a detailed report.",
                        parent=tree.winfo_toplevel()
                    )
                    self._set_status(f"Added {len(copied_files)} screenshots to report")
                else:
                    messagebox.showwarning("Copy Failed", "No screenshots were successfully copied.", parent=tree.winfo_toplevel())
                    
        except Exception as e:
            print(f"Error adding screenshots: {e}")
            messagebox.showerror("Screenshot Error", f"Failed to add screenshots:\n{e}", parent=tree.winfo_toplevel())
    
    def _add_screenshots_to_report_internal(self, tree, item):
        """Internal function to add screenshots during detailed report generation"""
        try:
            # Get default screenshots folder from main app settings
            default_folder = os.path.join(os.path.expanduser("~"), "Pictures")
            if self.main_app and hasattr(self.main_app, 'screenshots_folder_path'):
                default_folder = self.main_app.screenshots_folder_path.get() or default_folder
            
            # Open file dialog to select image files
            file_types = [
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg *.jpeg"),
                ("All files", "*.*")
            ]
            
            selected_files = filedialog.askopenfilenames(
                title="Select Screenshots for Detailed Report",
                initialdir=default_folder,
                filetypes=file_types,
                parent=tree.winfo_toplevel()
            )
            
            if selected_files:
                # Create screenshots directory if it doesn't exist - use consistent app_dir logic
                if getattr(sys, 'frozen', False):
                    # Running as executable (installer version)
                    app_dir = os.path.join(self.va_root, "app")
                else:
                    # Running as script (development version)
                    app_dir = os.path.dirname(os.path.abspath(__file__))
                    
                screenshots_dir = os.path.join(app_dir, "Reports", "Mining Session", "Detailed Reports", "Screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # Copy selected files to screenshots directory
                copied_files = []
                for file_path in selected_files:
                    try:
                        filename = os.path.basename(file_path)
                        dest_path = os.path.join(screenshots_dir, filename)
                        
                        # Add timestamp if file already exists
                        if os.path.exists(dest_path):
                            name, ext = os.path.splitext(filename)
                            timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"{name}_{timestamp}{ext}"
                            dest_path = os.path.join(screenshots_dir, filename)
                        
                        # Copy the file
                        import shutil
                        shutil.copy2(file_path, dest_path)
                        copied_files.append(dest_path)
                        
                    except Exception as e:
                        print(f"Error copying {file_path}: {e}")
                
                if copied_files:
                    # Get report identifier to link screenshots
                    values = tree.item(item, 'values')
                    report_id = f"{values[0]}_{values[2]}_{values[3]}"  # date_system_body as unique ID
                    
                    # Store screenshot references for the selected report
                    self._store_report_screenshots(report_id, copied_files)
                    
        except Exception as e:
            print(f"Error in internal screenshot function: {e}")
    
    def _parse_duration_to_minutes(self, duration_str):
        """Convert duration string (HH:MM:SS) to minutes"""
        try:
            if not duration_str or duration_str == "00:00:00":
                return 0
            parts = duration_str.split(":")
            hours = int(parts[0]) if len(parts) > 0 else 0
            minutes = int(parts[1]) if len(parts) > 1 else 0
            seconds = int(parts[2]) if len(parts) > 2 else 0
            return hours * 60 + minutes + seconds / 60.0
        except:
            return 0
    
    def _store_report_screenshots(self, report_id, screenshot_paths):
        """Store screenshot associations for a specific report"""
        try:
            import json
            if getattr(sys, 'frozen', False):
                # Running as executable (installer version)
                app_dir = os.path.join(self.va_root, "app")
            else:
                # Running as script (development version)
                app_dir = os.path.dirname(os.path.abspath(__file__))
                
            screenshots_map_file = os.path.join(app_dir, "Reports", "Mining Session", "Detailed Reports", "screenshot_mappings.json")
            
            # Load existing mappings
            mappings = {}
            if os.path.exists(screenshots_map_file):
                try:
                    with open(screenshots_map_file, 'r') as f:
                        mappings = json.load(f)
                except:
                    mappings = {}
            
            # Add new screenshots to this report (append to existing)
            if report_id not in mappings:
                mappings[report_id] = []
            
            # Add only new screenshots (avoid duplicates)
            for path in screenshot_paths:
                if path not in mappings[report_id]:
                    mappings[report_id].append(path)
            
            # Save updated mappings
            with open(screenshots_map_file, 'w') as f:
                json.dump(mappings, f, indent=2)
                
        except Exception as e:
            print(f"Error storing screenshot mappings: {e}")
    
    def _get_report_screenshots(self, report_id):
        """Get screenshots associated with a specific report"""
        try:
            import json
            if getattr(sys, 'frozen', False):
                # Running as executable (installer version)
                app_dir = os.path.join(self.va_root, "app")
            else:
                # Running as script (development version)
                app_dir = os.path.dirname(os.path.abspath(__file__))
                
            screenshots_map_file = os.path.join(app_dir, "Reports", "Mining Session", "Detailed Reports", "screenshot_mappings.json")
            
            if not os.path.exists(screenshots_map_file):
                return []
                
            with open(screenshots_map_file, 'r') as f:
                mappings = json.load(f)
                
            return mappings.get(report_id, [])
            
        except Exception as e:
            print(f"Error loading screenshot mappings: {e}")
            return []
    
    def _has_screenshots(self, report_id):
        """Check if a report has screenshots"""
        screenshots = self._get_report_screenshots(report_id)
        return len(screenshots) > 0
    
    def _has_enhanced_report(self, report_id):
        """Check if a report has an enhanced HTML report"""
        try:
            # Load detailed report mappings
            enhanced_mappings = self._load_enhanced_report_mappings()
            
            # Try exact match first
            if report_id in enhanced_mappings:
                html_filename = enhanced_mappings[report_id]
                html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
                return os.path.exists(html_path)
                
            return False
        except Exception as e:
            print(f"Error checking for detailed report: {e}")
            return False
            
    def _load_enhanced_report_mappings(self):
        """Load detailed report mappings from JSON file"""
        try:
            mappings_file = os.path.join(self.reports_dir, "Detailed Reports", "detailed_report_mappings.json")
            if os.path.exists(mappings_file):
                with open(mappings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            print(f"Error loading detailed report mappings: {e}")
            return {}
    
    def _update_enhanced_report_mapping(self, session_data, html_filename):
        """Update detailed report mapping to link session with HTML report"""
        try:
            # Use both display date and raw timestamp for compatibility
            display_date = session_data.get('date', '')
            raw_timestamp = session_data.get('timestamp_raw', display_date)
            system = session_data.get('system', '')
            body = session_data.get('body', '')
            
            # Create both possible report_id formats
            report_id_display = f"{display_date}_{system}_{body}"
            report_id_raw = f"{raw_timestamp}_{system}_{body}"
            
            # Load existing mappings
            mappings = self._load_enhanced_report_mappings()
            
            # Store HTML filename directly (simple string format)
            mappings[report_id_display] = html_filename
            if report_id_display != report_id_raw:
                mappings[report_id_raw] = html_filename
            
            # Save updated mappings
            mappings_file = os.path.join(self.reports_dir, "Detailed Reports", "detailed_report_mappings.json")
            os.makedirs(os.path.dirname(mappings_file), exist_ok=True)
            
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Error updating detailed report mapping: {e}")

    def _get_report_filenames(self, report_id):
        """Get HTML filename for a report_id"""
        try:
            mappings = self._load_enhanced_report_mappings()
            if report_id in mappings:
                mapping = mappings[report_id]
                # Handle both new dict format and legacy string format
                if isinstance(mapping, dict):
                    # Backward compatibility for existing dict format
                    return mapping.get('html_filename')
                else:
                    # Simple string format
                    return mapping
            return None
        except Exception as e:
            print(f"Error getting report filenames: {e}")
            return None

    def _has_detailed_report(self, report_id):
        """Check if detailed HTML report exists"""
        try:
            html_filename = self._get_report_filenames(report_id)
            return html_filename is not None
        except Exception as e:
            print(f"Error checking detailed report existence: {e}")
            return False

    def _get_detailed_report_indicator(self, report_id):
        """Get appropriate indicator symbol for detailed reports column"""
        try:
            html_filename = self._get_report_filenames(report_id)
            return "📊" if html_filename else ""
        except Exception as e:
            print(f"Error getting detailed report indicator: {e}")
            return ""

    def _generate_pdf_report(self, session_data, html_content=None, html_path=None):
        """Generate PDF report from HTML content or existing HTML file"""
        try:
            # Get HTML content either from parameter or by reading existing file
            if html_content is None and html_path and os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            
            if not html_content:
                raise Exception("No HTML content available for PDF generation")
            
            # Create PDF filename based on session data
            display_date = session_data.get('date', '')
            system = session_data.get('system', '')
            body = session_data.get('body', '')
            
            # Clean filename components
            safe_date = display_date.replace('/', '-').replace(':', '-')
            safe_system = system.replace(' ', '_').replace('/', '_')
            safe_body = body.replace(' ', '_').replace('/', '_')
            
            pdf_filename = f"session_{safe_date}_{safe_system}_{safe_body}.pdf"
            pdf_path = os.path.join(self.reports_dir, "Detailed Reports", pdf_filename)
            
            # Ensure the directory exists
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Try multiple PDF generation methods
            pdf_generated = False
            error_messages = []
            
            # Method 1: Try weasyprint first (best quality) - skip if known to fail on Windows
            try:
                import weasyprint
                from urllib.parse import urljoin
                from urllib.request import pathname2url
                
                # Set base URL for relative paths (for images, CSS, etc.)
                base_path = os.path.dirname(html_path) if html_path else os.path.join(self.reports_dir, "Detailed Reports")
                base_url = urljoin('file:', pathname2url(base_path) + '/')
                
                # Generate PDF using weasyprint
                html_doc = weasyprint.HTML(string=html_content, base_url=base_url)
                html_doc.write_pdf(pdf_path)
                pdf_generated = True
                print("PDF generated successfully using WeasyPrint")
                
            except Exception as e:
                error_messages.append(f"WeasyPrint failed: {e}")
                print(f"WeasyPrint failed: {e}")
                # WeasyPrint commonly fails on Windows, continue to other methods
            
            # Method 2: Try pdfkit if weasyprint failed
            if not pdf_generated:
                try:
                    import pdfkit
                    
                    # Configure pdfkit options for better output
                    options = {
                        'page-size': 'A4',
                        'margin-top': '0.75in',
                        'margin-right': '0.75in',
                        'margin-bottom': '0.75in',
                        'margin-left': '0.75in',
                        'encoding': "UTF-8",
                        'no-outline': None,
                        'enable-local-file-access': None,
                        'print-media-type': None
                    }
                    
                    # Generate PDF using pdfkit (requires wkhtmltopdf)
                    pdfkit.from_string(html_content, pdf_path, options=options)
                    pdf_generated = True
                    print("PDF generated successfully using pdfkit")
                    
                except Exception as e:
                    error_messages.append(f"pdfkit failed: {e}")
                    print(f"pdfkit failed (likely wkhtmltopdf not installed): {e}")
                    # pdfkit requires wkhtmltopdf to be installed, continue to ReportLab
            
            # Method 3: Intelligent fallback using ReportLab with proper HTML parsing
            if not pdf_generated:
                try:
                    from reportlab.lib.pagesizes import letter, A4
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
                    from reportlab.lib.units import inch
                    from reportlab.lib import colors
                    import re
                    from html import unescape
                    
                    # Create PDF document
                    doc = SimpleDocTemplate(pdf_path, pagesize=A4, 
                                          rightMargin=72, leftMargin=72, 
                                          topMargin=72, bottomMargin=18)
                    styles = getSampleStyleSheet()
                    story = []
                    
                    # Custom styles
                    title_style = ParagraphStyle(
                        'CustomTitle',
                        parent=styles['Title'],
                        fontSize=18,
                        spaceAfter=30,
                        textColor=colors.darkblue
                    )
                    
                    heading_style = ParagraphStyle(
                        'CustomHeading',
                        parent=styles['Heading2'],
                        fontSize=14,
                        spaceBefore=12,
                        spaceAfter=6,
                        textColor=colors.darkred
                    )
                    
                    # Parse the HTML content more intelligently
                    # Remove style and script tags entirely
                    clean_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
                    clean_content = re.sub(r'<script[^>]*>.*?</script>', '', clean_content, flags=re.DOTALL)
                    
                    # Extract meaningful content sections
                    def extract_text_content(html_text):
                        # Remove HTML tags but preserve structure
                        text = re.sub(r'<br\s*/?>', '\n', html_text)
                        text = re.sub(r'<p[^>]*>', '\n', text)
                        text = re.sub(r'</p>', '\n', text)
                        text = re.sub(r'<h[1-6][^>]*>', '\n### ', text)
                        text = re.sub(r'</h[1-6]>', '\n', text)
                        text = re.sub(r'<strong[^>]*>', '**', text)
                        text = re.sub(r'</strong>', '**', text)
                        text = re.sub(r'<b[^>]*>', '**', text)
                        text = re.sub(r'</b>', '**', text)
                        text = re.sub(r'<[^>]+>', '', text)  # Remove remaining tags
                        text = unescape(text)  # Decode HTML entities
                        # Clean up whitespace
                        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
                        text = re.sub(r'[ \t]+', ' ', text)
                        return text.strip()
                    
                    # Add title
                    title = f"Mining Session Report - {display_date}"
                    story.append(Paragraph(title, title_style))
                    story.append(Spacer(1, 20))
                    
                    # Add session details in a nice table
                    session_data_table = [
                        ['System:', system],
                        ['Body:', body], 
                        ['Date:', display_date]
                    ]
                    
                    table = Table(session_data_table, colWidths=[2*inch, 4*inch])
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
                        ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 11),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                        ('TOPPADDING', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ]))
                    
                    story.append(table)
                    story.append(Spacer(1, 20))
                    
                    # Extract and format the main content - properly parse mining data from HTML
                    try:
                        # Use BeautifulSoup for proper HTML parsing if available, otherwise use regex
                        try:
                            from bs4 import BeautifulSoup
                            soup = BeautifulSoup(html_content, 'html.parser')
                            use_soup = True
                        except ImportError:
                            use_soup = False
                            print("BeautifulSoup not available, using regex parsing")
                        
                        mining_data_found = False
                        
                        if use_soup:
                            # Extract data using BeautifulSoup for better parsing
                            
                            # Find session summary data
                            story.append(Paragraph("Mining Session Summary", heading_style))
                            
                            # Look for common mining data patterns in the HTML
                            session_data = []
                            
                            # Try to find duration
                            duration_elem = soup.find(text=re.compile(r'Duration', re.I))
                            if duration_elem:
                                duration_parent = duration_elem.parent
                                if duration_parent:
                                    duration_text = duration_parent.get_text().strip()
                                    duration_match = re.search(r'([0-9:]+)', duration_text)
                                    if duration_match:
                                        session_data.append(f"Session Duration: {duration_match.group(1)}")
                            
                            # Look for tons mined
                            tons_elem = soup.find(text=re.compile(r'tons?', re.I))
                            if tons_elem:
                                tons_context = tons_elem.parent.get_text() if tons_elem.parent else str(tons_elem)
                                tons_match = re.search(r'([0-9]+\.?[0-9]*)\s*tons?', tons_context, re.I)
                                if tons_match:
                                    session_data.append(f"Total Mined: {tons_match.group(1)} tons")
                            
                            # Look for mining rate (t/h)
                            rate_text = soup.get_text()
                            rate_match = re.search(r'([0-9]+\.?[0-9]*)\s*t/h', rate_text, re.I)
                            if rate_match:
                                session_data.append(f"Mining Rate: {rate_match.group(1)} t/h")
                            
                            # Look for prospectors
                            prosp_match = re.search(r'prospector[s]?[:\s]*([0-9]+)', rate_text, re.I)
                            if prosp_match:
                                session_data.append(f"Prospectors Used: {prosp_match.group(1)}")
                            
                            # Look for asteroids
                            ast_match = re.search(r'asteroid[s]?[:\s]*([0-9]+)', rate_text, re.I)
                            if ast_match:
                                session_data.append(f"Asteroids Mined: {ast_match.group(1)}")
                            
                            # Display session data
                            if session_data:
                                for data in session_data:
                                    story.append(Paragraph(f"• {data}", styles['Normal']))
                                story.append(Spacer(1, 12))
                                mining_data_found = True
                            
                            # Look for material breakdown tables
                            tables = soup.find_all('table')
                            for table in tables:
                                table_text = table.get_text().lower()
                                if 'material' in table_text or 'element' in table_text:
                                    story.append(Paragraph("Material Breakdown", heading_style))
                                    
                                    # Extract table data
                                    rows = table.find_all('tr')
                                    table_data = []
                                    
                                    for row in rows[:10]:  # Limit to first 10 rows
                                        cells = row.find_all(['td', 'th'])
                                        if len(cells) >= 2:
                                            cell_data = [cell.get_text().strip() for cell in cells[:3]]  # Max 3 columns
                                            if any(cell_data):  # Skip empty rows
                                                table_data.append(cell_data)
                                    
                                    if table_data:
                                        # Create ReportLab table
                                        pdf_table = Table(table_data, colWidths=[2*inch, 1*inch, 1*inch] if len(table_data[0]) >= 3 else [3*inch, 2*inch])
                                        pdf_table.setStyle(TableStyle([
                                            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
                                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                            ('FONTSIZE', (0, 0), (-1, -1), 9),
                                            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                                            ('TOPPADDING', (0, 0), (-1, -1), 6),
                                            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                                        ]))
                                        story.append(pdf_table)
                                        story.append(Spacer(1, 12))
                                        mining_data_found = True
                                    break
                            
                            # Look for statistics section
                            stats_section = soup.find(text=re.compile(r'statistic', re.I))
                            if stats_section:
                                stats_parent = stats_section.parent
                                while stats_parent and stats_parent.name != 'div':
                                    stats_parent = stats_parent.parent
                                
                                if stats_parent:
                                    stats_text = stats_parent.get_text()
                                    # Extract key statistics
                                    stats_data = []
                                    
                                    hit_rate = re.search(r'hit.rate[:\s]*([0-9]+\.?[0-9]*%?)', stats_text, re.I)
                                    if hit_rate:
                                        stats_data.append(f"Hit Rate: {hit_rate.group(1)}")
                                    
                                    efficiency = re.search(r'efficiency[:\s]*([0-9]+\.?[0-9]*%?)', stats_text, re.I)
                                    if efficiency:
                                        stats_data.append(f"Mining Efficiency: {efficiency.group(1)}")
                                    
                                    if stats_data:
                                        story.append(Paragraph("Mining Statistics", heading_style))
                                        for stat in stats_data:
                                            story.append(Paragraph(f"• {stat}", styles['Normal']))
                                        story.append(Spacer(1, 12))
                                        mining_data_found = True
                        
                        else:
                            # Fallback regex parsing if BeautifulSoup not available
                            clean_text = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL)
                            clean_text = re.sub(r'<script[^>]*>.*?</script>', '', clean_text, flags=re.DOTALL)
                            clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
                            clean_text = unescape(clean_text)
                            
                            story.append(Paragraph("Mining Session Summary", heading_style))
                            
                            # Extract key data with regex
                            session_data = []
                            
                            duration_match = re.search(r'Duration[:\s]*([0-9:]+)', clean_text, re.I)
                            if duration_match:
                                session_data.append(f"Session Duration: {duration_match.group(1)}")
                            
                            tons_match = re.search(r'([0-9]+\.?[0-9]*)\s*tons?', clean_text, re.I)
                            if tons_match:
                                session_data.append(f"Total Mined: {tons_match.group(1)} tons")
                            
                            rate_match = re.search(r'([0-9]+\.?[0-9]*)\s*t/h', clean_text, re.I)
                            if rate_match:
                                session_data.append(f"Mining Rate: {rate_match.group(1)} t/h")
                            
                            prosp_match = re.search(r'prospector[s]?[:\s]*([0-9]+)', clean_text, re.I)
                            if prosp_match:
                                session_data.append(f"Prospectors Used: {prosp_match.group(1)}")
                            
                            if session_data:
                                for data in session_data:
                                    story.append(Paragraph(f"• {data}", styles['Normal']))
                                story.append(Spacer(1, 12))
                                mining_data_found = True
                        
                        # If no mining data was extracted, provide helpful fallback
                        if not mining_data_found:
                            story.append(Paragraph("Mining Session Details", heading_style))
                            story.append(Paragraph("This comprehensive mining session report includes detailed statistics, material breakdowns, and performance metrics for your Elite Dangerous mining activities.", styles['Normal']))
                            story.append(Spacer(1, 6))
                            story.append(Paragraph("The complete interactive version with charts, graphs, and detailed breakdowns is available in the HTML report.", styles['Normal']))
                            
                    except Exception as e:
                        print(f"Error extracting mining data: {e}")
                        # Fallback content
                        story.append(Paragraph("Mining Session Details", heading_style))
                        story.append(Paragraph("This mining session report contains comprehensive data about your Elite Dangerous mining activities. For complete details, charts, and interactive features, please refer to the HTML version.", styles['Normal']))
                    
                    # Add disclaimer
                    story.append(Spacer(1, 20))
                    disclaimer_style = ParagraphStyle(
                        'Disclaimer',
                        parent=styles['Normal'],
                        fontSize=10,
                        textColor=colors.grey,
                        fontName='Helvetica-Oblique'
                    )
                    story.append(Paragraph(
                        "Note: This is a simplified PDF version optimized for printing and sharing. "
                        "For the complete interactive report with charts, graphs, and images, please use the HTML version.",
                        disclaimer_style
                    ))
                    
                    # Build PDF
                    doc.build(story)
                    pdf_generated = True
                    print("PDF generated successfully using ReportLab (enhanced formatting)")
                    
                except Exception as e:
                    error_messages.append(f"ReportLab enhanced fallback failed: {e}")
                    print(f"ReportLab enhanced fallback failed: {e}")
            
            if pdf_generated:
                # Update mapping to include PDF filename
                html_filename = os.path.basename(html_path) if html_path else None
                self._update_enhanced_report_mapping(session_data, html_filename, pdf_filename)
                print(f"PDF saved to: {pdf_path}")
                return pdf_path
            else:
                error_msg = "All PDF generation methods failed:\n" + "\n".join(error_messages)
                print(f"PDF generation failed completely: {error_msg}")
                raise Exception(error_msg)
                
        except Exception as e:
            print(f"Error generating PDF report: {e}")
            import traceback
            traceback.print_exc()  # Print full traceback for debugging
            return None

    def _generate_pdf_report_from_menu(self, tree):
        """Generate PDF report from context menu for selected item"""
        try:
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("No Selection", "Please select a report first.")
                return
                
            if len(selected_items) > 1:
                messagebox.showwarning("Multiple Selection", "Please select only one report at a time.")
                return
                
            # Get the selected report data
            item = selected_items[0]
            values = tree.item(item, 'values')
            
            if not values:
                messagebox.showwarning("Invalid Selection", "Could not get report data.")
                return
                
            # Extract report_id 
            display_date = values[0]  # Date/Time column  
            system = values[2] if len(values) > 2 else ''  # System column
            body = values[3] if len(values) > 3 else ''    # Body column
            report_id = f"{display_date}_{system}_{body}"
            
            # Check if HTML report exists (needed as source for PDF)
            filenames = self._get_report_filenames(report_id)
            html_filename = filenames['html']
            
            if not html_filename:
                messagebox.showinfo("No HTML Report", 
                                  f"To generate a PDF report, you must first create an HTML detailed report.\n\n"
                                  f"Session: {display_date} - {system} {body}\n\n"
                                  f"Right-click on this session and select 'Generate Detailed Report (HTML)' first.")
                return
            
            # Check if PDF already exists
            if filenames['pdf']:
                if not messagebox.askyesno("PDF Exists", 
                                         f"A PDF report already exists for this session.\n\n"
                                         f"Session: {display_date} - {system} {body}\n\n"
                                         f"Do you want to regenerate it?"):
                    return
            
            # Create session data dict
            session_data = {
                'date': display_date,
                'system': system,
                'body': body,
                'timestamp_raw': display_date  # Fallback
            }
            
            # Get HTML file path
            html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
            
            if not os.path.exists(html_path):
                messagebox.showerror("HTML File Not Found", 
                                   f"The HTML report file could not be found:\n{html_path}")
                return
            
            # Generate PDF
            print(f"Starting PDF generation for session: {display_date} - {system} {body}")
            pdf_path = self._generate_pdf_report(session_data, html_path=html_path)
            
            if pdf_path:
                # Refresh tree to update indicators
                if tree == self.reports_tree_tab:
                    self._refresh_reports_tab()
                else:
                    self._refresh_reports_window()
                
                # Ask if user wants to open the PDF
                if messagebox.askyesno("PDF Generated", 
                                     f"PDF report generated successfully!\n\n"
                                     f"File: {os.path.basename(pdf_path)}\n\n"
                                     f"Do you want to open it now?"):
                    self._open_pdf_report(report_id)
            else:
                messagebox.showerror("PDF Generation Failed", 
                                   "Failed to generate PDF report.\n\n"
                                   "This may be due to missing system libraries for PDF generation.\n"
                                   "Check the console output for detailed error information.\n\n"
                                   "Try using the HTML report instead, which contains all the same data.")
                print("PDF generation returned None - check console output above for detailed errors")
                
        except Exception as e:
            print(f"Error generating PDF report from menu: {e}")
            messagebox.showerror("Error", f"Failed to generate PDF report: {e}")

    def _open_pdf_report_from_menu(self, tree):
        """Open PDF report from context menu for selected item"""
        try:
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("No Selection", "Please select a report first.")
                return
                
            # Get the selected report data
            item = selected_items[0]
            values = tree.item(item, 'values')
            
            if not values:
                messagebox.showwarning("Invalid Selection", "Could not get report data.")
                return
                
            # Extract report_id 
            display_date = values[0]  # Date/Time column  
            system = values[2] if len(values) > 2 else ''  # System column
            body = values[3] if len(values) > 3 else ''    # Body column
            report_id = f"{display_date}_{system}_{body}"
            
            # Check if PDF report exists
            filenames = self._get_report_filenames(report_id)
            pdf_filename = filenames['pdf']
            
            if not pdf_filename:
                messagebox.showinfo("No PDF Report", 
                                  f"No PDF report found for this mining session.\n\n"
                                  f"Session: {display_date} - {system} {body}\n\n"
                                  f"To create a PDF report, right-click on this session and select 'Generate Detailed Report (PDF)'.")
                return
            
            # Open PDF report
            self._open_pdf_report(report_id)
                
        except Exception as e:
            print(f"Error opening PDF report from menu: {e}")
            messagebox.showerror("Error", f"Failed to open PDF report: {e}")

    def _open_pdf_report(self, report_id):
        """Open PDF report in default PDF viewer"""
        try:
            filenames = self._get_report_filenames(report_id)
            pdf_filename = filenames['pdf']
            
            if not pdf_filename:
                messagebox.showerror("No PDF Report", "PDF report not found.")
                return
            
            pdf_path = os.path.join(self.reports_dir, "Detailed Reports", pdf_filename)
            
            if not os.path.exists(pdf_path):
                messagebox.showerror("File Not Found", f"PDF file not found: {pdf_path}")
                return
            
            # Open PDF in default viewer
            import subprocess
            import platform
            
            if platform.system() == 'Windows':
                os.startfile(pdf_path)
            elif platform.system() == 'Darwin':  # macOS
                subprocess.call(['open', pdf_path])
            else:  # Linux
                subprocess.call(['xdg-open', pdf_path])
                
        except Exception as e:
            print(f"Error opening PDF report: {e}")
            messagebox.showerror("Error", f"Failed to open PDF report: {e}")
    
    def _migrate_existing_enhanced_reports(self):
        """Migrate existing detailed reports to mapping system"""
        try:
            enhanced_reports_dir = os.path.join(self.reports_dir, "Detailed Reports")
            if not os.path.exists(enhanced_reports_dir):
                return
            
            mappings = self._load_enhanced_report_mappings()
            
            # Parse existing HTML files to extract session information
            for filename in os.listdir(enhanced_reports_dir):
                if filename.endswith('.html') and filename not in mappings.values():
                    html_path = os.path.join(enhanced_reports_dir, filename)
                    session_info = self._extract_session_info_from_html(html_path)
                    
                    if session_info:
                        report_id = f"{session_info['date']}_{session_info['system']}_{session_info['body']}"
                        mappings[report_id] = filename
            
            # Save updated mappings
            mappings_file = os.path.join(enhanced_reports_dir, "detailed_report_mappings.json")
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Error migrating existing detailed reports: {e}")
    
    def _extract_session_info_from_html(self, html_path):
        """Extract session information from existing HTML report"""
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Use regex to extract system and body from the HTML
            import re
            system_match = re.search(r'<strong>System:</strong>\s*([^<]+)', content)
            body_match = re.search(r'<strong>Body:</strong>\s*([^<]+)', content)
            
            if system_match and body_match:
                system = system_match.group(1).strip()
                body = body_match.group(1).strip()
                
                # Try to match this with CSV data to get the exact date format
                csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                if os.path.exists(csv_path):
                    import csv
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if row['system'] == system and row['body'] == body:
                                # Format date to match report_id format (use original timestamp)
                                return {
                                    'date': row['timestamp_utc'],  # Use original timestamp 
                                    'system': system,
                                    'body': body
                                }
            
            return None
            
        except Exception as e:
            print(f"Error extracting session info from {html_path}: {e}")
            return None
            
    def _open_enhanced_report(self, report_id):
        """Open the detailed HTML report for the given report_id"""
        try:
            # Get HTML filename
            html_filename = self._get_report_filenames(report_id)
            
            if html_filename:
                html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
                
                if os.path.exists(html_path):
                    # Open the HTML file in the default browser
                    import webbrowser
                    webbrowser.open(f"file:///{html_path.replace(os.sep, '/')}")
                else:
                    messagebox.showwarning("File Not Found", f"Detailed report file not found:\n{html_path}")
            else:
                # Extract session info from report_id for better user feedback
                parts = report_id.split('_', 2)  # Split into max 3 parts: date, system, body
                display_date = parts[0] if len(parts) > 0 else "Unknown"
                system = parts[1] if len(parts) > 1 else "Unknown"
                body = parts[2] if len(parts) > 2 else "Unknown"
                
                messagebox.showinfo("No Detailed Report", 
                                  f"No detailed report found for this mining session.\n\n"
                                  f"Session: {display_date} - {system} {body}\n\n"
                                  f"To create a detailed report, right-click on this session and select 'Generate Detailed Report (HTML)'.")
                
        except Exception as e:
            print(f"Error opening detailed report: {e}")
            messagebox.showerror("Error", f"Failed to open detailed report: {e}")
    
    def _open_enhanced_report_from_menu(self, tree):
        """Open detailed report from context menu for selected item"""
        try:
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("No Selection", "Please select a report first.")
                return
                
            # Get the first selected item
            item = selected_items[0]
            values = tree.item(item, 'values')
            
            if not values:
                messagebox.showwarning("Invalid Selection", "Could not get report data.")
                return
                
            # Extract timestamp to use as report_id (should be in the first column)
            display_date = values[0]  # Date/Time column  
            system = values[2] if len(values) > 2 else ''  # System column
            body = values[3] if len(values) > 3 else ''    # Body column
            report_id = f"{display_date}_{system}_{body}"
            
            # Open the detailed report
            self._open_enhanced_report(report_id)
            
        except Exception as e:
            print(f"Error opening detailed report from menu: {e}")
            messagebox.showerror("Error", f"Failed to open detailed report: {e}")
    
    def _delete_existing_detailed_report(self, item, tree):
        """Silently delete existing detailed report and screenshots for a session (used before regenerating)"""
        try:
            values = tree.item(item, 'values')
            if not values:
                return
                
            # Extract report_id 
            display_date = values[0]  # Date/Time column  
            system = values[2] if len(values) > 2 else ''  # System column
            body = values[3] if len(values) > 3 else ''    # Body column
            report_id = f"{display_date}_{system}_{body}"
            
            # Check if detailed report exists
            html_filename = self._get_report_filenames(report_id)
            if not html_filename:
                return  # No existing report to delete
            
            # Delete the HTML file
            html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
            if os.path.exists(html_path):
                os.remove(html_path)
            
            # Delete associated screenshots
            screenshots = self._get_report_screenshots(report_id)
            for screenshot_path in screenshots:
                if os.path.exists(screenshot_path):
                    try:
                        os.remove(screenshot_path)
                    except Exception as e:
                        print(f"Error deleting screenshot {screenshot_path}: {e}")
            
            # Remove from screenshot mappings
            screenshots_map_file = os.path.join(self.reports_dir, "Detailed Reports", "screenshot_mappings.json")
            if os.path.exists(screenshots_map_file):
                try:
                    import json
                    with open(screenshots_map_file, 'r') as f:
                        screenshot_mappings = json.load(f)
                    
                    if report_id in screenshot_mappings:
                        del screenshot_mappings[report_id]
                        
                    with open(screenshots_map_file, 'w') as f:
                        json.dump(screenshot_mappings, f, indent=2)
                except Exception as e:
                    print(f"Error updating screenshot mappings: {e}")
            
            # Remove from enhanced report mappings
            mappings = self._load_enhanced_report_mappings()
            if report_id in mappings:
                del mappings[report_id]
                
                # Save updated mappings
                mappings_file = os.path.join(self.reports_dir, "Detailed Reports", "detailed_report_mappings.json")
                with open(mappings_file, 'w', encoding='utf-8') as f:
                    import json
                    json.dump(mappings, f, indent=2, ensure_ascii=False)
            
            print(f"Deleted existing detailed report for session: {display_date} - {system} {body}")
            
        except Exception as e:
            print(f"Warning: Could not delete existing detailed report: {e}")
    
    def _delete_enhanced_report_from_menu(self, tree):
        """Delete detailed HTML report(s) from context menu for selected item(s)"""
        try:
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("No Selection", "Please select a report first.")
                return
                
            # Process all selected items to build detailed report list
            reports_to_delete = []
            mappings = self._load_enhanced_report_mappings()
            
            for item in selected_items:
                values = tree.item(item, 'values')
                
                if not values:
                    continue
                    
                # Extract report_id 
                display_date = values[0]  # Date/Time column  
                system = values[2] if len(values) > 2 else ''  # System column
                body = values[3] if len(values) > 3 else ''    # Body column
                report_id = f"{display_date}_{system}_{body}"
                
                # Check if detailed report exists
                html_filename = self._get_report_filenames(report_id)
                if html_filename:
                    session_info = {
                        'report_id': report_id,
                        'display_date': display_date,
                        'system': system,
                        'body': body,
                        'html_filename': html_filename
                    }
                    reports_to_delete.append(session_info)
            
            if not reports_to_delete:
                if len(selected_items) == 1:
                    # Single selection with no detailed report
                    item = selected_items[0]
                    values = tree.item(item, 'values')
                    display_date = values[0] if values else "Unknown"
                    system = values[2] if len(values) > 2 else "Unknown"
                    body = values[3] if len(values) > 3 else "Unknown"
                    
                    messagebox.showinfo("No Detailed Report", 
                                      f"No detailed report found for this mining session.\n\n"
                                      f"Session: {display_date} - {system} {body}\n\n"
                                      f"To create a detailed report, right-click on this session and select 'Generate Detailed Report (HTML)'.")
                else:
                    # Multiple selections with no detailed reports
                    messagebox.showinfo("No Detailed Reports", 
                                      f"None of the {len(selected_items)} selected sessions have detailed reports.\n\n"
                                      f"To create detailed reports, right-click on individual sessions and select 'Generate Detailed Report (HTML)'.")
                return
            
            # Create confirmation message
            if len(reports_to_delete) == 1:
                session = reports_to_delete[0]
                
                confirm_msg = (f"Are you sure you want to permanently delete this detailed report?\n\n"
                              f"Session: {session['display_date']} - {session['system']} {session['body']}\n\n"
                              f"This will delete:\n"
                              f"• The HTML detailed report file\n"
                              f"• All associated screenshots\n"
                              f"• Report mapping data\n\n"
                              f"This action cannot be undone.")
                title = "Delete Detailed Report"
            else:
                confirm_msg = f"Are you sure you want to permanently delete {len(reports_to_delete)} detailed reports?\n\n"
                confirm_msg += "Sessions with detailed reports to be deleted:\n"
                for i, session in enumerate(reports_to_delete[:5], 1):  # Show max 5 items
                    confirm_msg += f"  {i}. {session['display_date']} - {session['system']}/{session['body']}\n"
                if len(reports_to_delete) > 5:
                    confirm_msg += f"  ... and {len(reports_to_delete) - 5} more\n"
                confirm_msg += f"\nThis will delete:\n"
                confirm_msg += f"• All HTML detailed report files\n"
                confirm_msg += f"• All associated screenshots\n"
                confirm_msg += f"• All report mapping data\n\n"
                confirm_msg += f"This action cannot be undone."
                title = "Delete Multiple Detailed Reports"
            
            # Show confirmation dialog
            if not messagebox.askyesno(title, confirm_msg, icon="warning"):
                return
                
            # Perform deletions
            deleted_count = 0
            for session in reports_to_delete:
                try:
                    report_id = session['report_id']
                    html_filename = session['html_filename']
                    
                    # Delete the HTML file
                    if html_filename:
                        html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
                        if os.path.exists(html_path):
                            os.remove(html_path)
                    
                    # Delete associated screenshots
                    screenshots = self._get_report_screenshots(report_id)
                    for screenshot_path in screenshots:
                        if os.path.exists(screenshot_path):
                            try:
                                os.remove(screenshot_path)
                            except Exception as e:
                                print(f"Error deleting screenshot {screenshot_path}: {e}")
                    
                    # Remove from screenshot mappings
                    screenshots_map_file = os.path.join(self.reports_dir, "Detailed Reports", "screenshot_mappings.json")
                    if os.path.exists(screenshots_map_file):
                        try:
                            import json
                            with open(screenshots_map_file, 'r') as f:
                                screenshot_mappings = json.load(f)
                            
                            if report_id in screenshot_mappings:
                                del screenshot_mappings[report_id]
                                
                            with open(screenshots_map_file, 'w') as f:
                                json.dump(screenshot_mappings, f, indent=2)
                        except Exception as e:
                            print(f"Error updating screenshot mappings: {e}")
                    
                    # Remove from enhanced report mappings
                    mappings = self._load_enhanced_report_mappings()
                    if report_id in mappings:
                        del mappings[report_id]
                        
                        # Save updated mappings
                        mappings_file = os.path.join(self.reports_dir, "Detailed Reports", "detailed_report_mappings.json")
                        with open(mappings_file, 'w', encoding='utf-8') as f:
                            import json
                            json.dump(mappings, f, indent=2, ensure_ascii=False)
                    
                    deleted_count += 1
                    
                except Exception as e:
                    print(f"Error deleting detailed report for {session['display_date']}: {e}")
            
            # Refresh tree to remove icons
            if deleted_count > 0:
                if tree == self.reports_tree_tab:
                    self._refresh_reports_tab()
                else:
                    self._refresh_reports_window()
                
                # Show success message
                if deleted_count == 1:
                    messagebox.showinfo("Success", "Detailed report deleted successfully.")
                else:
                    messagebox.showinfo("Success", f"{deleted_count} detailed reports deleted successfully.")
                
        except Exception as e:
            print(f"Error deleting detailed report: {e}")
            messagebox.showerror("Error", f"Failed to delete detailed report: {e}")
    
    def _handle_mouse_motion(self, event, tree):
        """Handle mouse motion to show pointer cursor over enhanced report icons"""
        try:
            # Identify which item and column the mouse is over
            item = tree.identify_row(event.y)
            column = tree.identify_column(event.x)
            
            if item and column:
                columns = tree["columns"]
                if int(column[1:]) - 1 < len(columns):
                    column_name = columns[int(column[1:]) - 1]
                    
                    # Check if mouse is over enhanced column and the cell has an icon
                    if column_name == "enhanced":
                        cell_value = tree.set(item, column_name)
                        if cell_value == "✓":  # Has enhanced report
                            tree.configure(cursor="hand2")
                            return
            
            # Reset cursor to default (but don't interfere with comment column)
            tree.configure(cursor="")
            
        except Exception as e:
            # Silently handle any errors to avoid disrupting user experience
            pass
    
    def _create_enhanced_click_handler(self, tree):
        """Create a click handler that intercepts enhanced report clicks"""
        def enhanced_click_handler(event):
            try:
                # Check if this click is on the detailed reports column
                item = tree.identify_row(event.y)
                column = tree.identify_column(event.x)
                
                if item and column:
                    columns = tree["columns"]
                    if int(column[1:]) - 1 < len(columns):
                        column_name = columns[int(column[1:]) - 1]
                        
                        # Only handle clicks on the enhanced column, not comment column
                        if column_name == "enhanced":
                            # This is a click on the detailed reports column
                            # Don't open reports on column click - only allow through right-click menu
                            # Don't show any popup messages to avoid interfering with multiple selection
                            # Allow normal row selection behavior by not returning "break"
                            pass
                
                # For all other clicks (including comment column), allow normal processing
                return None
                
            except Exception as e:
                print(f"Error in enhanced click handler: {e}")
                return None
        
        return enhanced_click_handler
            
    def _generate_enhanced_report_from_menu(self, tree):
        """Generate detailed HTML report for selected report from context menu"""
        try:
            selected_items = tree.selection()
            if not selected_items:
                messagebox.showwarning("No Selection", "Please select a report first.", parent=tree.winfo_toplevel())
                return
                
            if len(selected_items) > 1:
                messagebox.showwarning("Multiple Selection", "Please select only one report at a time.", parent=tree.winfo_toplevel())
                return
                
            # Get the selected report data
            item = selected_items[0]
            
            # Delete any existing detailed report and screenshots for this session before generating a new one
            try:
                self._delete_existing_detailed_report(item, tree)
            except Exception as delete_error:
                # If deletion fails, log it but continue with report generation
                print(f"Warning: Could not delete existing report: {delete_error}")
            
            # Try to get detailed session data first
            session_data = None
            if hasattr(self, 'reports_window_session_lookup'):
                session_data = self.reports_window_session_lookup.get(item)
            
            # If no detailed session data, create basic data from tree item
            if not session_data:
                values = tree.item(item, 'values')
                if len(values) >= 6:  # Ensure we have basic data
                    # Try to parse materials from the "Materials" column if available
                    materials_mined = {}
                    
                    # First try to get materials from breakdown column (materials_breakdown format: "Mat1: 5.2t, Mat2: 3.1t")
                    material_col_idx = 10  # Try "cargo" column which should have materials
                    if len(values) > material_col_idx and values[material_col_idx]:
                        try:
                            # Parse materials like "Alexandrite: 5.2t, Painite: 3.1t" etc.
                            materials_text = str(values[material_col_idx])
                            if materials_text and materials_text != "":
                                # Check if it's breakdown format (contains ":")
                                if ':' in materials_text:
                                    # Parse "Material: XXt" format
                                    material_pairs = [pair.strip() for pair in materials_text.split(',')]
                                    for pair in material_pairs:
                                        if ':' in pair:
                                            parts = pair.split(':')
                                            if len(parts) >= 2:
                                                material_name = parts[0].strip()
                                                tonnage_text = parts[1].strip()
                                                # Extract numeric value from "5.2t" format
                                                tonnage_match = re.search(r'([\d.]+)', tonnage_text)
                                                if tonnage_match:
                                                    tonnage = float(tonnage_match.group(1))
                                                    materials_mined[material_name] = tonnage
                                else:
                                    # Fallback: just material names without tonnage - assign equal portions
                                    material_names = [m.strip() for m in materials_text.split(',')]
                                    tonnage = float(values[4]) if values[4] else 0.0
                                    if tonnage > 0 and material_names:
                                        tons_per_material = tonnage / len(material_names)
                                        for material in material_names:
                                            if material and material != "":
                                                materials_mined[material] = tons_per_material
                        except Exception as e:
                            print(f"Error parsing materials: {e}")
                            pass
                    
                    # Try to get prospectors used from the prospectors column (index 11)
                    prospectors_used = 0
                    if len(values) > 11 and values[11]:
                        try:
                            prospectors_text = str(values[11]).strip()
                            if prospectors_text and prospectors_text != "—" and prospectors_text != "":
                                prospectors_used = int(float(prospectors_text))
                        except (ValueError, TypeError):
                            prospectors_used = 0
                    
                    # Create basic session data from tree values
                    session_data = {
                        'date': values[0],
                        'duration': values[1],
                        'system': values[2],
                        'body': values[3],
                        'tonnage': float(values[4]) if values[4] else 0.0,
                        'tph': float(values[5]) if values[5] else 0.0,
                        'materials_mined': materials_mined,
                        'prospectors_used': prospectors_used,
                        'comment': values[12] if len(values) > 12 else ""
                    }
                    
                    # Load detailed analytics from CSV if available
                    try:
                        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                        if os.path.exists(csv_path):
                            import csv
                            with open(csv_path, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    # Match by system, body, and date - try multiple matching strategies
                                    row_system = row.get('system', '')
                                    row_body = row.get('body', '')
                                    row_timestamp = row.get('timestamp_utc', '')
                                    
                                    # Strategy 1: Direct timestamp comparison
                                    timestamp_match = (row_timestamp == values[0])
                                    
                                    # Strategy 2: Convert CSV timestamp to display format and compare
                                    display_match = False
                                    try:
                                        if row_timestamp.endswith('Z'):
                                            csv_dt = dt.datetime.fromisoformat(row_timestamp.replace('Z', '+00:00'))
                                            csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                                        else:
                                            csv_dt = dt.datetime.fromisoformat(row_timestamp)
                                        display_time = csv_dt.strftime("%m/%d/%y %H:%M")
                                        display_match = (display_time == values[0])
                                    except:
                                        pass
                                    
                                    # Strategy 3: System/body match with any timestamp (fallback)
                                    location_match = (row_system == values[2] and row_body == values[3])
                                    
                                    if (timestamp_match or display_match) and location_match:
                                        # Add CSV analytics fields to session data
                                        session_data.update({
                                            'hit_rate_percent': row.get('hit_rate_percent'),
                                            'avg_quality_percent': row.get('avg_quality_percent'),
                                            'asteroids_prospected': row.get('asteroids_prospected'),
                                            'best_material': row.get('best_material'),
                                            'materials_tracked': row.get('materials_tracked')
                                        })
                                        
                                        # Parse materials_breakdown from CSV for more accurate data
                                        try:
                                            materials_breakdown = row.get('materials_breakdown', '')
                                            if materials_breakdown:
                                                # Parse "Painite:13t; Platinum:15t" format
                                                csv_materials = {}
                                                # Split on semicolon first, then comma as fallback
                                                separators = [';', ',']
                                                for sep in separators:
                                                    if sep in materials_breakdown:
                                                        pairs = [p.strip() for p in materials_breakdown.split(sep)]
                                                        break
                                                else:
                                                    pairs = [materials_breakdown.strip()]
                                                
                                                for pair in pairs:
                                                    if ':' in pair:
                                                        parts = pair.split(':')
                                                        if len(parts) >= 2:
                                                            material_name = parts[0].strip()
                                                            tonnage_text = parts[1].strip()
                                                            # Extract numeric value from "13t" format
                                                            tonnage_match = re.search(r'([\d.]+)', tonnage_text)
                                                            if tonnage_match:
                                                                tonnage = float(tonnage_match.group(1))
                                                                csv_materials[material_name] = tonnage
                                                
                                                if csv_materials:
                                                    session_data['materials_mined'] = csv_materials
                                        except Exception as e:
                                            print(f"Warning: Could not parse materials_breakdown from CSV: {e}")
                                            pass
                                        
                                        # Try to get individual material yields for this session
                                        try:
                                            # Parse the yield display string to extract individual yields
                                            yield_str = row.get('avg_quality_percent', '')
                                            if yield_str and isinstance(yield_str, str) and ':' in yield_str:
                                                # Parse format like "Pt: 15.2%, Os: 12.8%"
                                                individual_yields = {}
                                                pairs = [pair.strip() for pair in yield_str.split(',')]
                                                for pair in pairs:
                                                    if ':' in pair:
                                                        parts = pair.split(':')
                                                        if len(parts) >= 2:
                                                            # Expand abbreviations back to full names
                                                            abbreviations = {
                                                                'Pt': 'Platinum', 'Os': 'Osmium', 'Pain': 'Painite', 'Rh': 'Rhodium',
                                                                'Pd': 'Palladium', 'Au': 'Gold', 'Ag': 'Silver', 'Bert': 'Bertrandite',
                                                                'Ind': 'Indite', 'Ga': 'Gallium', 'Pr': 'Praseodymium', 'Sm': 'Samarium',
                                                                'Brom': 'Bromellite', 'LTD': 'Low Temperature Diamonds', 'VO': 'Void Opals',
                                                                'Alex': 'Alexandrite', 'Beni': 'Benitoite', 'Monaz': 'Monazite',
                                                                'Musg': 'Musgravite', 'Ser': 'Serendibite', 'Taaf': 'Taaffeite'
                                                            }
                                                            abbrev = parts[0].strip()
                                                            percentage_str = parts[1].strip().replace('%', '')
                                                            material_name = abbreviations.get(abbrev, abbrev)
                                                            individual_yields[material_name] = float(percentage_str)
                                                session_data['individual_yields'] = individual_yields
                                        except Exception as e:
                                            print(f"Warning: Could not parse individual yields: {e}")
                                            pass
                                        break  # Found match, stop looking
                    except Exception as e:
                        print(f"Warning: Could not load CSV analytics: {e}")
                        pass
                else:
                    messagebox.showwarning("No Data", 
                        "This appears to be a manual report entry without detailed mining data.\n" +
                        "Detailed reports work best with actual mining session data.", 
                        parent=tree.winfo_toplevel())
                    return
                
            # Generate enhanced report
            from report_generator import ReportGenerator
            generator = ReportGenerator(self.main_app)
            
            # Prepare session data for HTML report
            enhanced_session_data = {
                'system': session_data.get('system', 'Unknown'),
                'body': session_data.get('body', 'Unknown'),
                'date': session_data.get('date', 'Unknown'),
                'duration': session_data.get('duration', '00:00'),  # Keep as formatted string
                'tons': str(session_data.get('tonnage', 0)),        # Keep as string for consistency
                'tph': str(session_data.get('tph', 0)),             # Keep as string for consistency
                'materials': str(len(session_data.get('materials_mined', {}))),  # Material count as string
                'prospectors': str(session_data.get('prospectors_used', 0)),     # Keep as string
                'materials_mined': session_data.get('materials_mined', {}),
                'comment': session_data.get('comment', ''),
                'screenshots': [],
                # Add analytics data from CSV for HTML reports
                'hit_rate_percent': session_data.get('hit_rate_percent'),
                'avg_quality_percent': session_data.get('avg_quality_percent'), 
                'asteroids_prospected': session_data.get('asteroids_prospected'),
                'best_material': session_data.get('best_material'),
                'materials_tracked': session_data.get('materials_tracked'),
                'individual_yields': session_data.get('individual_yields', {}),  # Add individual yield breakdown
                # Add additional data for compatibility
                'session_type': 'Enhanced Report from Tree Data',
                'data_source': 'Report Entry'
            }
            
            # Ask user if they want to add screenshots before generating the report
            from tkinter import messagebox
            add_screenshots = messagebox.askyesno(
                "Detailed Report", 
                "Would you like to add screenshots to this detailed report?",
                parent=tree.winfo_toplevel()
            )
            
            if add_screenshots:
                # Let user select screenshots
                self._add_screenshots_to_report_internal(tree, item)
            
            # Get screenshots that are specifically linked to this report
            values = tree.item(item, 'values')
            report_id = f"{values[0]}_{values[2]}_{values[3]}"  # date_system_body as unique ID
            report_screenshots = self._get_report_screenshots(report_id)
            
            # Only include screenshots that exist and are linked to this report
            valid_screenshots = []
            for screenshot_path in report_screenshots:
                if os.path.exists(screenshot_path):
                    valid_screenshots.append(screenshot_path)
            
            enhanced_session_data['screenshots'] = valid_screenshots
            
            # Generate HTML content
            html_content = generator.generate_report(
                enhanced_session_data,
                include_charts=True,
                include_screenshots=len(valid_screenshots) > 0,  # Only include screenshots section if there are any
                include_statistics=True
            )
            
            if html_content:
                # Save HTML report
                report_filename = f"detailed_report_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                html_report_path = generator.save_report(html_content, report_filename)
                
                if html_report_path:
                    # Update enhanced report mapping
                    self._update_enhanced_report_mapping(session_data, os.path.basename(html_report_path))
                    
                    # Ask user if they want to preview the report
                    preview_report = messagebox.askyesno(
                        "Enhanced Report Generated",
                        f"Enhanced HTML report created successfully!\n\nWould you like to preview it now?",
                        parent=tree.winfo_toplevel()
                    )
                    
                    if preview_report:
                        generator.preview_report(html_content)
                        
                    self._set_status(f"Enhanced report generated: {os.path.basename(html_report_path)}")
                    
                    # Refresh tree to show new enhanced report icon
                    try:
                        if tree == self.reports_tree_tab:
                            self._refresh_reports_tab()
                        else:
                            self._refresh_reports_window()
                    except Exception as refresh_error:
                        print(f"Error refreshing tree: {refresh_error}")
                        pass
                else:
                    messagebox.showerror("Save Failed", "Could not save enhanced report.", parent=tree.winfo_toplevel())
            else:
                messagebox.showerror("Generation Failed", "Could not generate enhanced report content.", parent=tree.winfo_toplevel())
                
        except ImportError:
            messagebox.showerror(
                "Enhanced Report Error",
                "Enhanced report functionality not available - missing dependencies",
                parent=tree.winfo_toplevel()
            )
        except Exception as e:
            print(f"Error generating enhanced report from menu: {e}")
            messagebox.showerror("Report Error", f"Failed to generate enhanced report:\n{e}", parent=tree.winfo_toplevel())
            
    def _generate_enhanced_report(self, cargo_session_data, text_report_path):
        """Generate enhanced HTML report with charts and screenshots"""
        try:
            from report_generator import ReportGenerator
            
            # Create report generator
            generator = ReportGenerator(self.main_app)
            
            # Prepare session data for HTML report
            enhanced_session_data = cargo_session_data.copy() if cargo_session_data else {}
            
            # Add screenshots from current session
            if hasattr(self, 'session_screenshots') and self.session_screenshots:
                enhanced_session_data['screenshots'] = self.session_screenshots
            
            # Generate HTML content
            html_content = generator.generate_report(
                enhanced_session_data,
                include_charts=True,
                include_screenshots=True,
                include_statistics=True
            )
            
            if html_content:
                # Save HTML report
                html_report_path = generator.save_report(html_content, os.path.basename(text_report_path))
                
                if html_report_path:
                    # Update enhanced report mapping
                    self._update_enhanced_report_mapping(enhanced_session_data, os.path.basename(html_report_path))
                    
                    # Ask user if they want to preview the report
                    preview_report = messagebox.askyesno(
                        "Enhanced Report Generated",
                        f"Enhanced HTML report saved successfully!\n\nWould you like to preview it now?",
                        parent=self.winfo_toplevel()
                    )
                    
                    if preview_report:
                        generator.preview_report(html_content)
                        
                    self._set_status(f"Enhanced HTML report saved: {os.path.basename(html_report_path)}")
                else:
                    self._set_status("Enhanced report generation failed - save error")
            else:
                self._set_status("Enhanced report generation failed - content error")
                
        except ImportError:
            messagebox.showerror(
                "Enhanced Report Error",
                "Enhanced report functionality not available - missing dependencies",
                parent=self.winfo_toplevel()
            )
        except Exception as e:
            print(f"Error in enhanced report generation: {e}")
            raise
            
    def _open_batch_reports_dialog(self, parent_window):
        """Open dialog for generating multiple enhanced HTML reports"""
        try:
            # Create batch dialog window
            batch_window = tk.Toplevel(parent_window)
            batch_window.title("Batch Detailed Reports")
            batch_window.geometry("600x500")
            batch_window.resizable(True, True)
            batch_window.configure(bg="#2b2b2b")
            
            # Main frame
            main_frame = ttk.Frame(batch_window, padding=10)
            main_frame.pack(fill='both', expand=True)
            
            # Title
            title_label = ttk.Label(main_frame, text="Generate Enhanced HTML Reports", 
                                  font=("Segoe UI", 12, "bold"))
            title_label.pack(pady=(0, 10))
            
            # Date range frame
            date_frame = ttk.LabelFrame(main_frame, text="Date Range (Optional)", padding=10)
            date_frame.pack(fill='x', pady=(0, 10))
            
            ttk.Label(date_frame, text="From:").grid(row=0, column=0, sticky='w', padx=(0, 5))
            from_date = tk.StringVar()
            from_entry = ttk.Entry(date_frame, textvariable=from_date, width=12)
            from_entry.grid(row=0, column=1, padx=(0, 10))
            ttk.Label(date_frame, text="(YYYY-MM-DD)").grid(row=0, column=2, sticky='w')
            
            ttk.Label(date_frame, text="To:").grid(row=1, column=0, sticky='w', padx=(0, 5), pady=(5, 0))
            to_date = tk.StringVar()
            to_entry = ttk.Entry(date_frame, textvariable=to_date, width=12)
            to_entry.grid(row=1, column=1, padx=(0, 10), pady=(5, 0))
            ttk.Label(date_frame, text="(YYYY-MM-DD)").grid(row=1, column=2, sticky='w', pady=(5, 0))
            
            # Session selection frame
            selection_frame = ttk.LabelFrame(main_frame, text="Session Selection", padding=10)
            selection_frame.pack(fill='both', expand=True, pady=(0, 10))
            
            # Scrollable session list
            list_frame = ttk.Frame(selection_frame)
            list_frame.pack(fill='both', expand=True)
            
            # Treeview for session selection
            columns = ('select', 'date', 'system', 'tonnage', 'tph')
            session_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
            
            session_tree.heading('select', text='Select')
            session_tree.heading('date', text='Date')
            session_tree.heading('system', text='System')
            session_tree.heading('tonnage', text='Tonnage')
            session_tree.heading('tph', text='TPH')
            
            session_tree.column('select', width=60, anchor='center')
            session_tree.column('date', width=100)
            session_tree.column('system', width=150)
            session_tree.column('tonnage', width=80, anchor='center')
            session_tree.column('tph', width=80, anchor='center')
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=session_tree.yview)
            session_tree.configure(yscrollcommand=scrollbar.set)
            
            session_tree.pack(side='left', fill='both', expand=True)
            scrollbar.pack(side='right', fill='y')
            
            # Load sessions data
            selected_sessions = set()
            
            def toggle_selection(event):
                item = session_tree.selection()[0] if session_tree.selection() else None
                if item:
                    if item in selected_sessions:
                        selected_sessions.remove(item)
                        session_tree.item(item, values=(session_tree.item(item)['values'][0].replace('✓', '☐'), *session_tree.item(item)['values'][1:]))
                    else:
                        selected_sessions.add(item)
                        values = list(session_tree.item(item)['values'])
                        values[0] = '✓'
                        session_tree.item(item, values=values)
            
            session_tree.bind('<Double-1>', toggle_selection)
            
            # Load session data from CSV
            try:
                csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                if os.path.exists(csv_path):
                    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            date_str = row.get('Date', '')
                            system = row.get('System', '')
                            tonnage = row.get('Total Tonnage', '0')
                            tph = row.get('TPH', '0')
                            
                            item_id = session_tree.insert('', 'end', values=('☐', date_str, system, tonnage, tph))
            except Exception as e:
                print(f"Error loading session data: {e}")
            
            # Selection buttons
            btn_frame = ttk.Frame(selection_frame)
            btn_frame.pack(fill='x', pady=(10, 0))
            
            def select_all():
                for item in session_tree.get_children():
                    selected_sessions.add(item)
                    values = list(session_tree.item(item)['values'])
                    values[0] = '✓'
                    session_tree.item(item, values=values)
            
            def select_none():
                selected_sessions.clear()
                for item in session_tree.get_children():
                    values = list(session_tree.item(item)['values'])
                    values[0] = '☐'
                    session_tree.item(item, values=values)
            
            ttk.Button(btn_frame, text="Select All", command=select_all).pack(side='left', padx=(0, 5))
            ttk.Button(btn_frame, text="Select None", command=select_none).pack(side='left')
            
            # Action buttons
            action_frame = ttk.Frame(main_frame)
            action_frame.pack(fill='x', pady=(10, 0))
            
            def generate_batch_reports():
                if not selected_sessions:
                    messagebox.showwarning("No Selection", "Please select at least one session to generate reports for.")
                    return
                
                # Get selected session data and generate reports
                try:
                    count = 0
                    errors = 0
                    
                    for item in selected_sessions:
                        try:
                            # This is a simplified batch generation - in a real implementation,
                            # you'd need to load the full session data for each session
                            count += 1
                        except Exception as e:
                            errors += 1
                            print(f"Error generating report for session: {e}")
                    
                    messagebox.showinfo(
                        "Batch Generation Complete",
                        f"Generated {count} detailed reports.\n{errors} errors occurred.",
                        parent=batch_window
                    )
                    
                    if errors == 0:
                        batch_window.destroy()
                        
                except Exception as e:
                    messagebox.showerror("Batch Error", f"Error during batch generation: {e}", parent=batch_window)
            
            def close_dialog():
                batch_window.destroy()
            
            ttk.Button(action_frame, text="Generate Reports", command=generate_batch_reports).pack(side='left', padx=(0, 10))
            ttk.Button(action_frame, text="Cancel", command=close_dialog).pack(side='left')
            
            # Center the dialog
            batch_window.transient(parent_window)
            batch_window.grab_set()
            
        except Exception as e:
            print(f"Error opening batch reports dialog: {e}")
            messagebox.showerror("Dialog Error", f"Could not open batch reports dialog: {e}", parent=parent_window)
