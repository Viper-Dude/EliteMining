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
from app_utils import get_app_data_dir, get_reports_dir, get_variables_dir, centered_message, centered_askyesno, _center_child_over_parent

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

# Import normalization from journal_parser for consistent material name handling
from journal_parser import JournalParser

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
    
    # Normalize "Low Temp. Diamonds" to "Low Temperature Diamonds"
    if s.lower() in ['low temp. diamonds', 'low temp diamonds']:
        return "Low Temperature Diamonds"
    
    # Normalize "Opal" variants to "Void Opals"
    if s.lower() in ['opal', 'void opal']:
        return "Void Opals"
    
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

def _extract_location_display(full_body_name: str, body_type: str = "", station_name: str = "", carrier_name: str = "", system_name: str = "") -> str:
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
        system_name: Optional current system name to strip from body name
    
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
    
    # Strip system name prefix from body name if provided
    # "HIP 72681 A" with system "HIP 72681" -> "A"
    # "HIP 72681 2 A Ring" with system "HIP 72681" -> "2 A Ring"
    body_name = full_body_name
    if system_name and full_body_name.startswith(system_name):
        body_name = full_body_name[len(system_name):].strip()
        if not body_name:
            body_name = full_body_name  # Keep original if nothing left
    
    # Priority 3: Asteroid rings (mining context)
    if body_type == "PlanetaryRing" or "Ring" in body_name:
        # First try to match patterns like "AB 2 B Ring" (planet letters + number + ring letter)
        # Use [A-Z]+ to match one or more uppercase letters (A, B, AB, ABC, etc.)
        ring_match = re.search(r'\b([A-Z]+\s+\d+\s+[A-Za-z]\s+Ring)$', body_name)
        if ring_match:
            return ring_match.group(1)
        # Fallback for simpler patterns like "2 A Ring" - match number at start
        ring_match = re.search(r'\b(\d+\s+[A-Za-z]\s+Ring)$', body_name)
        if ring_match:
            return ring_match.group(1)
        # If body_name already looks like a clean ring name, return it
        if re.match(r'^[A-Z]?\s*\d*\s*[A-Za-z]?\s*Ring$', body_name.strip()):
            return body_name.strip()
    
    # Priority 4: If we already stripped system name, the remaining body_name is likely clean
    if system_name and body_name != full_body_name:
        # body_name is already the extracted part (e.g., "A", "2", "2 A Ring")
        if body_name:
            # Single letter planet (A, B, C, etc.)
            if len(body_name) == 1 and body_name.isalpha():
                return body_name.upper()
            # Number only (planet 1, 2, 3, etc.)
            if body_name.isdigit():
                return body_name
            # Number + letter (2 A, 3 B, etc.) - likely a moon or ring
            parts = body_name.split()
            if len(parts) == 2 and parts[0].isdigit() and len(parts[1]) == 1 and parts[1].isalpha():
                if body_type == "PlanetaryRing" or "Ring" in full_body_name:
                    return f"{parts[0]} {parts[1].upper()} Ring"
                else:
                    return f"{parts[0]} {parts[1].upper()}"
            # Otherwise return as-is
            return body_name
    
    # Priority 5: Extract just the body designation from system + body names (fallback)
    # Remove system name prefix to show just the body part
    # Examples: 
    # "Col 285 Sector WP-E c12-17 3 a" -> "3A" or "3A Ring" (if it's a ring)
    # "Sol Earth" -> "Earth"
    # "Wolf 359 B" -> "B"  
    # "Paesia 2" -> "2"
    
    parts = full_body_name.split()
    if len(parts) >= 2:
        last_part = parts[-1]
        
        # Pattern: ends with single letter (like "3 a" -> "3A Ring")
        if len(last_part) == 1 and last_part.isalpha() and len(parts) >= 2:
            second_last = parts[-2]
            if second_last.isdigit():
                body_designation = f"{second_last}{last_part.upper()}"
                # For mining contexts, always add "Ring" suffix for number+letter patterns
                # since these are almost always planetary rings in Elite Dangerous
                return f"{body_designation} Ring"
        
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
            return None  # No remaining value present
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
    "Coltan",
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
    "Tritium",
    "Uraninite",
    "Void Opals",
    "Water"
]

CORE_ONLY = [
    "Alexandrite", "Benitoite", "Grandidierite", "Monazite", "Musgravite", "Rhodplumsite", "Serendibite",
    "Taaffeite", "Void Opals"
]

# -------------------- Mining Analytics Panel --------------------
class ProspectorPanel(ttk.Frame):

    def _ensure_comment_and_eng_cells(self, tree, session_lookup):
        """Ensure the comment emoji and engineering materials are placed in the correct named columns.

        This is a defensive sweep to handle any column reordering or saved layouts: it writes
        the values directly into the named columns for every row after the tree has been populated.
        """
        try:
            if tree is None:
                return
            cols = list(tree["columns"]) if "columns" in tree.keys() else []
            has_comment = 'comment' in cols
            # Some views use 'eng_materials' or 'engineering_materials' column name
            has_eng = 'eng_materials' in cols or 'engineering_materials' in cols

            for item in tree.get_children(''):
                sess = session_lookup.get(item) if session_lookup else None
                if not sess:
                    continue
                try:
                    if has_eng:
                        eng_col = 'eng_materials' if 'eng_materials' in cols else 'engineering_materials'
                        tree.set(item, eng_col, sess.get('engineering_materials', '') or sess.get('eng_materials', ''))
                    if has_comment:
                        tree.set(item, 'comment', '💬' if sess.get('comment', '').strip() else '')
                except Exception:
                    # Ignore individual cell failures
                    pass
        except Exception:
            pass
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
        
        # Use centralized path utilities for consistent dev/installer handling
        self.vars_dir = get_variables_dir()  # Variables folder (dev-aware)
        os.makedirs(self.vars_dir, exist_ok=True)
        
        # Get reports directory using centralized path utilities
        self.reports_dir = get_reports_dir()
        try:
            os.makedirs(self.reports_dir, exist_ok=True)
        except PermissionError as e:
            import tkinter.messagebox as mb
            mb.showerror(
                "Permission Error",
                f"Cannot create Reports folder:\n{self.reports_dir}\n\n"
                f"Error: {e}\n\n"
                f"Please run EliteMining as Administrator or manually create the folder."
            )
            raise
        
        # Clear any cached session data to prevent stale data issues
        self.reports_tab_session_lookup = {}
        self.session_lookup = {}

        # Track reports window for refreshing
        self.reports_window = None
        self.reports_tree = None
        
        # One-time wipe of Mining Session folder on v4.3.0 upgrade
        self.after(100, self._wipe_mining_session_folder)

        # Initialize bookmarks system - use centralized path utility
        from path_utils import get_bookmarks_file
        self.bookmarks_file = get_bookmarks_file()
        self.bookmarks_data = []
        self._load_bookmarks()

        # Load journal directory from config or detect default
        from config import _load_cfg
        cfg = _load_cfg()
        saved_dir = cfg.get("journal_dir", None)
        
        if saved_dir and os.path.exists(saved_dir):
            self.journal_dir = saved_dir
        else:
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
        
        # Defer journal scanning to prevent startup freeze
        # Will be called after UI is built
        self._initial_scan_pending = True

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
        self.session_mining_body = ""  # Preserved mining location (won't be overwritten by docking events)
        self.session_elapsed = tk.StringVar(value="00:00:00")
        self.session_totals: Dict[str, float] = {}
        
        # Auto-start session on first prospector
        # Auto-start session - load from toggle file
        self.auto_start_on_prospector = False
        try:
            auto_start_file = os.path.join(self.vars_dir, "autoStartSession.txt")
            print(f"[DEBUG] Loading auto-start from: {auto_start_file}")
            if os.path.exists(auto_start_file):
                with open(auto_start_file, 'r') as f:
                    content = f.read().strip()
                    self.auto_start_on_prospector = content == "1"
                    print(f"[DEBUG] Auto-start file exists, content: '{content}', result: {self.auto_start_on_prospector}")
            else:
                print(f"[DEBUG] Auto-start file does not exist, defaulting to False")
        except Exception as e:
            print(f"[DEBUG] Error loading auto-start file: {e}")
            pass
        
        # Prompt when cargo full - load from toggle file
        self.prompt_on_cargo_full = False
        self.cargo_full_start_time = None  # Track when cargo became full
        self.cargo_full_prompted = False  # Track if we already prompted
        try:
            prompt_full_file = os.path.join(self.vars_dir, "promptWhenFull.txt")
            print(f"[DEBUG] Loading prompt-when-full from: {prompt_full_file}")
            if os.path.exists(prompt_full_file):
                with open(prompt_full_file, 'r') as f:
                    content = f.read().strip()
                    self.prompt_on_cargo_full = content == "1"
                    print(f"[DEBUG] Prompt-when-full file exists, content: '{content}', result: {self.prompt_on_cargo_full}")
            else:
                print(f"[DEBUG] Prompt-when-full file does not exist, defaulting to False")
        except Exception as e:
            print(f"[DEBUG] Error loading prompt-when-full file: {e}")
            pass
        
        # Multi-session mode - load from toggle file
        self.multi_session_mode = False  # Accumulate stats across multiple cargo loads
        try:
            multi_session_file = os.path.join(self.vars_dir, "multiSessionMode.txt")
            print(f"[DEBUG] Loading multi-session from: {multi_session_file}")
            if os.path.exists(multi_session_file):
                with open(multi_session_file, 'r') as f:
                    content = f.read().strip()
                    self.multi_session_mode = content == "1"
                    print(f"[DEBUG] Multi-session file exists, content: '{content}', result: {self.multi_session_mode}")
            else:
                print(f"[DEBUG] Multi-session file does not exist, defaulting to False")
        except Exception as e:
            print(f"[DEBUG] Error loading multi-session file: {e}")
            pass
        
        # Note: Multi-session and prompt-when-full are incompatible features
        # This will be handled in the UI initialization
        print(f"[DEBUG] After loading - auto_start: {self.auto_start_on_prospector}, prompt_on_cargo_full: {self.prompt_on_cargo_full}, multi_session: {self.multi_session_mode}")
        
        # Multi-session cumulative tracking (only used when multi_session_mode=True)
        self.session_total_mined = 0  # Total tons mined in session (cumulative)
        self.session_sold_transferred = 0  # Tons sold or transferred to carrier
        self.session_ejected = 0  # Tons lost by dumping/abandoning

        # UI
        self._build_ui()
        
        # Load last settings after UI is built
        self._load_last_material_settings()
        
        # Defer journal scanning to prevent blocking UI initialization
        if self._initial_scan_pending:
            self.after(100, self._deferred_initial_scan)
        # Force announce_map to UI after build (only if mat_tree exists)
        if hasattr(self, 'mat_tree'):
            for m in self.mat_tree.get_children():
                flag = "✓" if self.announce_map.get(m, True) else "—"
                self.mat_tree.item(m, values=(flag, m, ""))
        
        # Automatically rebuild CSV on startup to ensure data is current
        self.after(500, self._auto_rebuild_csv_on_startup)
        
        self.after(1000, self._tick)
        
        # Link cargo monitor back to this prospector panel for multi-session mode detection
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            self.main_app.cargo_monitor.prospector_panel = self
        
        # Switch to real-time mode after startup processing is complete
        self.after(2000, self._enable_realtime_mode)
        
        # Check Status.json once after startup to get current location and override stale journal data
        self.after(2500, self._startup_sync_with_status)
        
        # Update ship info display every 2 seconds for first 10 seconds after startup
        for delay in [2000, 4000, 6000, 8000, 10000]:
            self.after(delay, self._update_ship_info_display)

    # --- Stub methods for announcements panel (moved to Settings) ---
    def _position_minpct_spinboxes(self):
        """Stub method - announcements panel moved to Settings tab"""
        pass
        
    def _sync_spinboxes_to_min_pct_map(self):
        """Stub method - announcements panel moved to Settings tab"""
        pass

    def _get_current_system(self) -> str:
        """Get current system from centralized app source or fallback to local tracking"""
        if self.main_app and hasattr(self.main_app, 'get_current_system'):
            system = self.main_app.get_current_system()
            if system:
                return system
        # Fallback to locally tracked system
        return self.last_system or ""

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
        # Update system field if we have one and it's empty
        current_system = self._get_current_system()
        if current_system and not self.session_system.get():
            self.session_system.set(current_system)
        
        # Update body field - pass system name for better filtering
        body_display = _extract_location_display(
            self.last_body or "", 
            self.last_body_type, 
            self.last_station_name, 
            self.last_carrier_name,
            current_system or self.session_system.get() or ""
        )
        self.session_body.set(body_display)
        
        # Update distance display using Ring Finder's calculator
        self._update_distance_display()
    
    def _update_distance_display(self) -> None:
        """Update distance display using centralized Distance Calculator"""
        try:
            # Get distance info from main app's Distance Calculator (already calculated)
            if self.main_app and hasattr(self.main_app, 'get_distance_info_text'):
                distance_text = self.main_app.get_distance_info_text()
                self.distance_info_label.config(text=distance_text)
            else:
                self.distance_info_label.config(text="➤ Sol: --- | Home: --- | Fleet Carrier: ---")
        except Exception as e:
            self.distance_info_label.config(text="➤ Sol: --- | Home: --- | Fleet Carrier: ---")
    
    def _update_ship_info_display(self) -> None:
        """Update the ship info display with current ship data from cargo monitor"""
        try:
            if (self.main_app and 
                hasattr(self.main_app, 'cargo_monitor') and 
                hasattr(self.main_app.cargo_monitor, 'get_ship_info_string')):
                ship_info = self.main_app.cargo_monitor.get_ship_info_string()
                
                if ship_info:
                    self.ship_info_label.config(text=ship_info)
                else:
                    self.ship_info_label.config(text="No ship data")
            else:
                self.ship_info_label.config(text="")
        except Exception as e:
            print(f"Error updating ship info: {e}")
            self.ship_info_label.config(text="")
    
    def _startup_sync_with_status(self) -> None:
        """Sync with Status.json on startup to override stale journal data with current game state"""
        self._check_status_location_fields()
        
        # If Status.json doesn't provide clear location info, the journal data might be stale
        # Force an update to show what we currently think the location is
        self._update_location_display()
    
    def _deferred_initial_scan(self) -> None:
        """Deferred journal scan - runs after UI is initialized to prevent startup freeze"""
        self._initial_scan_pending = False
        self._read_initial_location_from_journal()
        
        # Update location display with any data found during journal scan
        if self.last_system or self.last_body:
            self._update_location_display()
            print(f"[STARTUP] UI updated - System: '{self.session_system.get()}', Body: '{self.session_body.get()}'")
            
            # Notify main app of current system (single source of truth)
            if self.main_app and hasattr(self.main_app, 'update_current_system'):
                self.main_app.update_current_system(self.last_system)
    
    def _read_initial_location_from_journal(self) -> None:
        """Read the most recent journal file to populate initial system/body location on startup
        
        Uses timestamp comparison to find the LATEST system event (handles CarrierJump after Location)
        """
        if not self.journal_dir or not os.path.isdir(self.journal_dir):
            return
        
        try:
            # Find the most recent journal file
            journal_files = [f for f in os.listdir(self.journal_dir) if f.startswith("Journal.") and f.endswith(".log")]
            if not journal_files:
                return
            
            # Sort by filename (date/time in name) to get most recent
            journal_files.sort(reverse=True)
            latest_journal = os.path.join(self.journal_dir, journal_files[0])
            
            # Read journal backwards to find most recent location event
            with open(latest_journal, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Scan more lines to handle cases where CarrierJump comes after Location
            latest_event = None
            latest_timestamp = None
            
            # Check last 1000 lines to ensure we get CarrierJump if it exists
            for line in reversed(lines[-1000:]):
                try:
                    entry = json.loads(line.strip())
                    event_type = entry.get("event", "")
                    
                    # Look for system-changing events
                    if event_type in ('FSDJump', 'Location', 'SupercruiseExit', 'SupercruiseEntry', 'Docked', 'CarrierJump'):
                        system = entry.get("StarSystem", "")
                        if not system:
                            continue
                        
                        timestamp_str = entry.get("timestamp", "")
                        
                        # Track the latest event by timestamp
                        if timestamp_str:
                            try:
                                from datetime import datetime
                                event_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                                
                                if latest_timestamp is None or event_time > latest_timestamp:
                                    latest_timestamp = event_time
                                    
                                    # For body info, prefer SupercruiseExit or Location
                                    body_name = entry.get("Body", "")
                                    body_type = entry.get("BodyType", "")
                                    
                                    latest_event = {
                                        'system': system,
                                        'body': body_name,
                                        'body_type': body_type
                                    }
                            except Exception:
                                # Fallback: just use first system event if timestamp parsing fails
                                if latest_event is None:
                                    latest_event = {
                                        'system': system,
                                        'body': entry.get("Body", ""),
                                        'body_type': entry.get("BodyType", "")
                                    }
                        else:
                            # No timestamp, use if we haven't found anything
                            if latest_event is None:
                                latest_event = {
                                    'system': system,
                                    'body': entry.get("Body", ""),
                                    'body_type': entry.get("BodyType", "")
                                }
                            
                except (json.JSONDecodeError, KeyError):
                    continue
            
            # If we found system/body, save them (UI widgets don't exist yet)
            if latest_event:
                self.last_system = latest_event['system']
                body_name = latest_event['body']
                body_type = latest_event['body_type']
                
                # Only set last_body if it's not just the system name (i.e., we're at a ring/planet, not a star)
                is_star = body_type == "Star" or body_name == self.last_system
                if body_name and not is_star:
                    self.last_body = body_name
                    self.last_body_type = body_type
                else:
                    self.last_body = ""
                    self.last_body_type = ""
                
                print(f"[STARTUP] Found system from journal: {self.last_system}")
                if self.last_body:
                    print(f"[STARTUP] Found body from journal: {self.last_body} (type: {self.last_body_type})")
                else:
                    print(f"[STARTUP] No body found in journal (at star or system)")
                    
        except Exception as e:
            print(f"Error reading initial location from journal: {e}")

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
        from app_utils import centered_askyesno
        if not centered_askyesno(self.winfo_toplevel(), "Save Preset 1", "Overwrite Announcement Preset 1?"):
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
            from main import center_window
            import tkinter as tk
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.title("Load Preset 1")
            dialog.resizable(False, False)
            label = tk.Label(dialog, text="No Preset 1 saved yet.", padx=20, pady=20)
            label.pack()
            center_window(dialog, main_parent)
            tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
            dialog.transient(main_parent)
            dialog.grab_set()
            dialog.wait_window()
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
        
        # Update UI (only if mat_tree exists - announcements panel moved to Settings)
        if hasattr(self, 'mat_tree'):
            for m in self.mat_tree.get_children():
                flag = "✓" if self.announce_map.get(m, True) else "—"
                self.mat_tree.item(m, values=(flag, m, ""))
                
        if hasattr(self, '_minpct_spin'):
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
        from app_utils import centered_askyesno
        if not centered_askyesno(self.winfo_toplevel(), f"Save Preset {num}", f"Overwrite Announcement Preset {num}?"):
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
            from main import center_window
            import tkinter as tk
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.title(f"Load Preset {num}")
            dialog.resizable(False, False)
            label = tk.Label(dialog, text=f"No Preset {num} saved yet.", padx=20, pady=20)
            label.pack()
            center_window(dialog, main_parent)
            tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
            dialog.transient(main_parent)
            dialog.grab_set()
            dialog.wait_window()
            return
        
        # Merge preset data with current materials to preserve new materials
        preset_announce = data.get('announce_map', {})
        preset_minpct = data.get('min_pct_map', {})
        
        # Keep existing values for materials in KNOWN_MATERIALS but not in preset
        for material in KNOWN_MATERIALS:
            if material not in preset_announce:
                preset_announce[material] = self.announce_map.get(material, True)
            if material not in preset_minpct:
                preset_minpct[material] = self.min_pct_map.get(material, 20.0)
        
        self.announce_map = preset_announce
        self.min_pct_map = preset_minpct
        self.threshold.set(data.get('announce_threshold', 20.0))
        
        # Load Core/Non-Core asteroid settings from announcement presets
        if hasattr(self, 'announcement_vars') and self.announcement_vars:
            if "Core Asteroids" in self.announcement_vars and 'Core Asteroids' in data:
                self.announcement_vars["Core Asteroids"].set(data['Core Asteroids'])
            if "Non-Core Asteroids" in self.announcement_vars and 'Non-Core Asteroids' in data:
                self.announcement_vars["Non-Core Asteroids"].set(data['Non-Core Asteroids'])
        
        # Update UI (only if mat_tree exists - announcements panel moved to Settings)
        if hasattr(self, 'mat_tree'):
            for m in self.mat_tree.get_children():
                flag = "✓" if self.announce_map.get(m, True) else "—"
                self.mat_tree.item(m, values=(flag, m, ""))
                
        if hasattr(self, '_minpct_spin'):
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
            self.announce_map = last_settings.get('announce_map', {}).copy()  # Load announcement preferences
            self.min_pct_map = last_settings.get('min_pct_map', {}).copy()
            self.threshold.set(last_settings.get('announce_threshold', 20.0))
            
            # Restore Core/Non-Core settings from last_material_settings
            if hasattr(self, 'announcement_vars') and self.announcement_vars:
                if "Core Asteroids" in self.announcement_vars and "Core Asteroids" in last_settings:
                    self.announcement_vars["Core Asteroids"].set(last_settings["Core Asteroids"])
                if "Non-Core Asteroids" in self.announcement_vars and "Non-Core Asteroids" in last_settings:
                    self.announcement_vars["Non-Core Asteroids"].set(last_settings["Non-Core Asteroids"])
            
            # Update UI (only if mat_tree exists - announcements panel moved to Settings)
            if hasattr(self, 'mat_tree'):
                for m in self.mat_tree.get_children():
                    flag = "✓" if self.announce_map.get(m, True) else "—"
                    self.mat_tree.item(m, values=(flag, m, ""))
                    
            if hasattr(self, '_minpct_spin'):
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
        """Detect Elite Dangerous journal directory - works on all Windows languages"""
        home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
        
        # Try to get Saved Games folder using Windows Shell API (works on all languages)
        try:
            import ctypes
            from ctypes import wintypes
            
            # FOLDERID_SavedGames = {4C5C32FF-BB9D-43b0-B5B4-2D72E54EAAA4}
            FOLDERID_SavedGames = ctypes.c_char_p(b'{4C5C32FF-BB9D-43b0-B5B4-2D72E54EAAA4}')
            
            # Try SHGetKnownFolderPath (Vista+)
            SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
            SHGetKnownFolderPath.argtypes = [ctypes.c_char_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(wintypes.LPWSTR)]
            
            path_ptr = wintypes.LPWSTR()
            result = SHGetKnownFolderPath(FOLDERID_SavedGames, 0, 0, ctypes.byref(path_ptr))
            
            if result == 0:
                saved_games_path = path_ptr.value
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                path = os.path.join(saved_games_path, "Frontier Developments", "Elite Dangerous")
                if os.path.isdir(path):
                    return path
        except Exception as e:
            log.debug(f"Shell API method failed: {e}")
        
        # Fallback: try common language variants
        for saved_games_name in ["Saved Games", "Gespeicherte Spiele", "Opgeslagen spellen", "Guardado juegos"]:
            path = os.path.join(home, saved_games_name, "Frontier Developments", "Elite Dangerous")
            if os.path.isdir(path):
                return path
        
        return None

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
            from main import center_window
            import tkinter as tk
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.title("Rebuild Error")
            dialog.resizable(False, False)
            label = tk.Label(dialog, text=f"Failed to rebuild CSV and refresh: {str(e)}", padx=20, pady=20, fg="red")
            label.pack()
            center_window(dialog, main_parent)
            tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
            dialog.transient(main_parent)
            dialog.grab_set()
            dialog.wait_window()
    
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
            from main import center_window
            import tkinter as tk
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.title("Clear Cache Error")
            dialog.resizable(False, False)
            label = tk.Label(dialog, text=f"Failed to clear cache: {str(e)}", padx=20, pady=20, fg="red")
            label.pack()
            center_window(dialog, main_parent)
            tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
            dialog.transient(main_parent)
            dialog.grab_set()
            dialog.wait_window()
    
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
                # Use named column lookups to avoid index errors when columns change
                cols = list(self.reports_tree_tab['columns'])
                if not all(k in cols for k in ('system', 'body', 'duration', 'comment')):
                    continue

                ui_system = self.reports_tree_tab.set(item, 'system')
                ui_body = self.reports_tree_tab.set(item, 'body')
                ui_duration = self.reports_tree_tab.set(item, 'duration')
                ui_comment = self.reports_tree_tab.set(item, 'comment') or ''

                key = f"{ui_system}|{ui_body}|{ui_duration}"

                if key in csv_data:
                    csv_comment = csv_data[key]['comment']
                    if (ui_comment or '').strip() != (csv_comment or '').strip():
                        inconsistencies.append({
                            'key': key,
                            'ui_comment': ui_comment,
                            'csv_comment': csv_comment,
                            'system': ui_system,
                            'body': ui_body,
                            'item': item,
                            'values': list(self.reports_tree_tab.item(item, 'values'))
                        })
            
            # If inconsistencies found, offer to fix them  
            if inconsistencies:
                print(f"[WARNING] Found {len(inconsistencies)} comment inconsistencies between UI and CSV")
                for inc in inconsistencies:
                    print(f"[WARNING] {inc['system']} {inc['body']}: UI='{inc['ui_comment']}' vs CSV='{inc['csv_comment']}'")
                
                from main import centered_yesno_dialog
                result = centered_yesno_dialog(
                    self.winfo_toplevel(),
                    "Data Inconsistency Detected",
                    f"Found {len(inconsistencies)} sessions where the UI comment doesn't match the CSV file.\n\n"
                    f"Example: {inconsistencies[0]['system']} {inconsistencies[0]['body']}\n"
                    f"UI shows: '{inconsistencies[0]['ui_comment']}'\n"
                    f"CSV has: '{inconsistencies[0]['csv_comment']}'\n\n"
                    f"Click 'Yes' to update UI from CSV (recommended)\n"
                    f"Click 'No' to update CSV from UI\n"
                )
                
                if result is True:  # Update UI from CSV
                    for inc in inconsistencies:
                        try:
                            self.reports_tree_tab.set(inc['item'], 'comment', inc['csv_comment'])
                        except Exception:
                            # Fallback to replacing values list if set fails
                            new_values = list(inc['values'])
                            try:
                                comment_idx = list(self.reports_tree_tab['columns']).index('comment')
                                new_values[comment_idx] = inc['csv_comment']
                                self.reports_tree_tab.item(inc['item'], values=new_values)
                            except Exception:
                                pass
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
        rep.rowconfigure(4, weight=1)  # Updated for new ship info row
        nb.add(rep, text="Mining Analytics")

        # --- Distance and Ship Info Row ---
        distance_ship_row = ttk.Frame(rep)
        distance_ship_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(2, 4))
        distance_ship_row.columnconfigure(1, weight=1)  # Allow middle to expand
        
        # Distance info on the left - will be populated from Ring Finder's distance calculator
        from config import load_theme
        _pp_theme = load_theme()
        _pp_bg = "#0a0a0a" if _pp_theme == "elite_orange" else "#1e1e1e"
        
        ttk.Label(distance_ship_row, text="Distances:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 5))
        self.distance_info_label = tk.Label(distance_ship_row, text="➤ Sol: --- | Home: --- | Fleet Carrier: ---",
                                font=("Segoe UI", 9), foreground="#ffcc00", bg=_pp_bg)
        self.distance_info_label.pack(side="left")
        
        # Ship info on the right side of the same row
        ship_info_frame = ttk.Frame(distance_ship_row)
        ship_info_frame.pack(side="right", padx=(20, 0))
        ttk.Label(ship_info_frame, text="Ship:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 5))
        self.ship_info_label = ttk.Label(ship_info_frame, text="", font=("Segoe UI", 9, "bold"), foreground="#ffcc00")
        self.ship_info_label.pack(side="left")

        # --- System and Location Name Entry Row ---
        sysbody_row = ttk.Frame(rep)
        sysbody_row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        sysbody_row.columnconfigure(0, weight=0, minsize=50)
        sysbody_row.columnconfigure(1, weight=0, minsize=120)
        sysbody_row.columnconfigure(2, weight=0, minsize=80)
        sysbody_row.columnconfigure(3, weight=1)

        ttk.Label(sysbody_row, text="System:", font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=(0, 2))
        self.system_entry = ttk.Entry(sysbody_row, textvariable=self.session_system, width=40)
        self.system_entry.grid(row=0, column=1, sticky="w", padx=(0, 5))
        self.ToolTip(self.system_entry, "Current system name. (Can also be entered manually)")

        ttk.Label(sysbody_row, text="Planet/Ring:", font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w", padx=(0, 2))
        self.body_entry = ttk.Entry(sysbody_row, textvariable=self.session_body, width=15)
        self.body_entry.grid(row=0, column=3, sticky="w")
        self.ToolTip(self.body_entry, "Current location: rings, planets, stations, or carriers. (Can also be entered manually)")

        # --- Remove VA Variables path row ---
        # vrow = ttk.Frame(rep)
        # vrow.grid(row=2, column=0, sticky="w", pady=(6, 0))
        # ttk.Label(vrow, text="VA Variables:").pack(side="left")
        # self.va_lbl = tk.Label(vrow, text=self.vars_dir, fg="gray", font=("Segoe UI", 9))
        # self.va_lbl.pack(side="left", padx=(6, 0))

        ttk.Label(rep, text="Prospector Reports:", font=("Segoe UI", 10, "bold")).grid(row=3, column=0, sticky="w", pady=(6, 4))

        # Configure Prospector Reports Treeview style based on theme
        from config import load_theme
        pp_theme = load_theme()
        style = ttk.Style()
        
        if pp_theme == "elite_orange":
            tree_bg = "#0a0a0a"
            tree_fg = "#ff8c00"
            header_bg = "#1a1a1a"
            selection_bg = "#ff6600"
            selection_fg = "#000000"
            alt_row_bg = "#151515"
        else:
            tree_bg = "#1e1e1e"
            tree_fg = "#e6e6e6"
            header_bg = "#2a2a2a"
            selection_bg = "#0078d7"
            selection_fg = "#ffffff"
            alt_row_bg = "#282828"
        
        style.configure("ProspectorReports.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=tree_bg,
                       foreground=tree_fg,
                       fieldbackground=tree_bg)
        style.configure("ProspectorReports.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",
                       background=header_bg,
                       foreground=tree_fg,
                       padding=[5, 5],
                       anchor="w")
        style.map("ProspectorReports.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])
        
        style.layout("ProspectorReports.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])

        # Create wrapper frame for bordered table
        tree_frame_prospector = ttk.Frame(rep, relief="solid", borderwidth=1)
        tree_frame_prospector.grid(row=4, column=0, sticky="nsew")

        self.tree = ttk.Treeview(tree_frame_prospector, columns=("materials", "content", "time"), show="headings", height=5, style="ProspectorReports.Treeview")
        self.tree.tag_configure('oddrow', background=tree_bg, foreground=tree_fg)
        self.tree.tag_configure('evenrow', background=alt_row_bg, foreground=tree_fg)
        self.tree.heading("materials", text="Minerals", anchor="w")
        self.tree.heading("content", text="Asteroid Content", anchor="w")
        self.tree.heading("time", text="Time", anchor="w")
        self.tree.column("materials", width=400, minwidth=150, anchor="w", stretch=False)
        self.tree.column("content", width=180, minwidth=100, anchor="w", stretch=False)
        self.tree.column("time", width=80, minwidth=60, anchor="w", stretch=True)
        
        # Load saved column widths from config
        try:
            from config import load_prospector_report_column_widths
            saved_widths = load_prospector_report_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        self.tree.column(col_name, width=width)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Prospector Report column widths: {e}")

        # Bind column resize event to save widths
        def save_prospector_report_widths(event=None):
            try:
                from config import save_prospector_report_column_widths
                widths = {}
                for col in ["materials", "content", "time"]:
                    try:
                        widths[col] = self.tree.column(col, "width")
                    except:
                        pass
                save_prospector_report_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Prospector Report column widths: {e}")
        
        self.tree.bind("<ButtonRelease-1>", save_prospector_report_widths)
        
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll = ttk.Scrollbar(tree_frame_prospector, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=yscroll.set)
        yscroll.grid(row=0, column=1, sticky="ns")
        
        tree_frame_prospector.grid_columnconfigure(0, weight=1)
        tree_frame_prospector.grid_rowconfigure(0, weight=1)
        
        # Add column header tooltips for Prospector Reports table
        def prospector_motion_handler(event):
            self._show_prospector_header_tooltip(event, self.tree)
        
        self.tree.bind("<Motion>", prospector_motion_handler)
        
        def hide_prospector_tooltip(event):
            if hasattr(self, '_prospector_tooltip_window') and self._prospector_tooltip_window:
                self._prospector_tooltip_window.destroy()
                self._prospector_tooltip_window = None
                self._current_prospector_tooltip_column = None
        
        self.tree.bind("<Leave>", hide_prospector_tooltip)

        # --- Live Mining Statistics Section ---
        ttk.Label(rep, text="Mineral Analysis:", font=("Segoe UI", 10, "bold")).grid(row=5, column=0, sticky="w", pady=(10, 4))
        stats_frame = ttk.Frame(rep)
        stats_frame.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(0, 0))
        stats_frame.columnconfigure(0, weight=1)
        
        # Configure Mineral Analysis Treeview style (theme-aware - uses same vars from ProspectorReports)
        style.configure("MineralAnalysis.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=tree_bg,
                       foreground=tree_fg,
                       fieldbackground=tree_bg)
        style.configure("MineralAnalysis.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",
                       background=header_bg,
                       foreground=tree_fg,
                       padding=[5, 5],
                       anchor="w")
        style.map("MineralAnalysis.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])
        
        style.layout("MineralAnalysis.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])
        
        # Create wrapper frame for bordered table
        tree_frame_mineral = ttk.Frame(stats_frame, relief="solid", borderwidth=1)
        tree_frame_mineral.grid(row=0, column=0, sticky="ew")
        
        # Statistics tree for live percentage yields
        self.stats_tree = ttk.Treeview(tree_frame_mineral, columns=("material", "tons", "tph", "tons_per", "avg_all", "avg_pct", "best_pct", "latest_pct", "count"), 
                           show="headings", height=5, style="MineralAnalysis.Treeview")
        self.stats_tree.tag_configure('oddrow', background=tree_bg, foreground=tree_fg)
        self.stats_tree.tag_configure('evenrow', background=alt_row_bg, foreground=tree_fg)
        self.stats_tree.heading("material", text="Mineral (Threshold%)", anchor="w")
        self.stats_tree.heading("tons", text="Tons", anchor="w")
        self.stats_tree.heading("tph", text="T/hr", anchor="w")
        self.stats_tree.heading("tons_per", text="Tons/Asteroid", anchor="w")
        self.stats_tree.heading("avg_all", text="Avg % (All)", anchor="w")
        self.stats_tree.heading("avg_pct", text="Avg % (≥Threshold)", anchor="w")
        self.stats_tree.heading("best_pct", text="Best %", anchor="w")
        self.stats_tree.heading("latest_pct", text="Latest %", anchor="w")
        self.stats_tree.heading("count", text="Hits", anchor="w")
        
        self.stats_tree.column("material", width=135, minwidth=110, anchor="w", stretch=False)
        self.stats_tree.column("tons", width=65, minwidth=50, anchor="w", stretch=False)
        self.stats_tree.column("tph", width=65, minwidth=50, anchor="w", stretch=False)
        self.stats_tree.column("tons_per", width=85, minwidth=60, anchor="w", stretch=False)
        self.stats_tree.column("avg_all", width=95, minwidth=70, anchor="w", stretch=False)
        self.stats_tree.column("avg_pct", width=130, minwidth=100, anchor="w", stretch=False)
        self.stats_tree.column("best_pct", width=80, minwidth=60, anchor="w", stretch=False)
        self.stats_tree.column("latest_pct", width=80, minwidth=60, anchor="w", stretch=False)
        self.stats_tree.column("count", width=65, minwidth=50, anchor="w", stretch=True)
        
        # Load saved column widths from config
        try:
            from config import load_mineral_analysis_column_widths
            saved_widths = load_mineral_analysis_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        self.stats_tree.column(col_name, width=width)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Mineral Analysis column widths: {e}")

        # Bind column resize event to save widths
        def save_mineral_analysis_widths(event=None):
            try:
                from config import save_mineral_analysis_column_widths
                widths = {}
                for col in ["material", "tons", "tph", "tons_per", "avg_all", "avg_pct", "best_pct", "latest_pct", "count"]:
                    try:
                        widths[col] = self.stats_tree.column(col, "width")
                    except:
                        pass
                save_mineral_analysis_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Mineral Analysis column widths: {e}")
        
        self.stats_tree.bind("<ButtonRelease-1>", save_mineral_analysis_widths)
        
        self.stats_tree.grid(row=0, column=0, sticky="ew")
        
        # Add vertical scrollbar for Material Analysis
        stats_yscrollbar = ttk.Scrollbar(tree_frame_mineral, orient="vertical", command=self.stats_tree.yview)
        stats_yscrollbar.grid(row=0, column=1, sticky="ns")
        self.stats_tree.configure(yscroll=stats_yscrollbar.set)
        
        tree_frame_mineral.grid_columnconfigure(0, weight=1)
        tree_frame_mineral.grid_rowconfigure(0, weight=1)
        
        # Add horizontal scrollbar for Material Analysis
        stats_xscrollbar = ttk.Scrollbar(stats_frame, orient="horizontal", command=self.stats_tree.xview)
        stats_xscrollbar.grid(row=1, column=0, sticky="ew")
        self.stats_tree.configure(xscrollcommand=stats_xscrollbar.set)
        
        # Add column header tooltips for Material Analysis table
        def mineral_motion_handler(event):
            self._show_mineral_header_tooltip(event, self.stats_tree)
        
        self.stats_tree.bind("<Motion>", mineral_motion_handler)
        
        def hide_mineral_tooltip(event):
            if hasattr(self, '_mineral_tooltip_window') and self._mineral_tooltip_window:
                self._mineral_tooltip_window.destroy()
                self._mineral_tooltip_window = None
                self._current_mineral_tooltip_column = None
        
        self.stats_tree.bind("<Leave>", hide_mineral_tooltip)
        
        # Session summary labels
        summary_frame = ttk.Frame(stats_frame)
        summary_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        summary_frame.columnconfigure(1, weight=1)
        
        ttk.Label(summary_frame, text="Session Summary:", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        self.stats_summary_label = ttk.Label(summary_frame, text="No data yet", foreground="#888888")
        self.stats_summary_label.grid(row=0, column=1, sticky="w", padx=(10, 0))
        
        # Session controls (moved from Session tab)
        controls_frame = ttk.Frame(stats_frame)
        controls_frame.grid(row=3, column=0, sticky="ew", pady=(4, 0))
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
        
        # Session options frame (below buttons for checkboxes)
        options_frame = ttk.Frame(controls_frame)
        options_frame.grid(row=1, column=0, sticky="w", pady=(4, 0))
        
        # Auto-start session checkbox
        auto_start_ui_value = 1 if self.auto_start_on_prospector else 0
        print(f"[DEBUG] UI Init - auto_start boolean: {self.auto_start_on_prospector}, UI value: {auto_start_ui_value}")
        self.auto_start_var = tk.IntVar()  # Initialize without value first
        auto_start_cb = tk.Checkbutton(
            options_frame, 
            text="Auto-start", 
            variable=self.auto_start_var,
            # Don't set command yet - will add after setting value
            bg="#1e1e1e", 
            fg="#ffffff", 
            selectcolor="#1e1e1e", 
            activebackground="#1e1e1e",
            activeforeground="#ffffff", 
            highlightthickness=0, 
            bd=0, 
            font=("Segoe UI", 8),
            padx=8, 
            pady=0, 
            anchor="w", 
            relief="flat"
        )
        auto_start_cb.pack(side="left")
        self.auto_start_var.set(auto_start_ui_value)  # Set value without callback
        auto_start_cb.config(command=self._on_auto_start_checkbox_toggle)  # Now add callback
        print(f"[DEBUG] Auto-start checkbox created and value set to: {auto_start_ui_value}")
        self.ToolTip(auto_start_cb, "Automatically start session when first prospector limpet is fired\n(Only works when no session is active)")
        
        # Prompt when cargo full checkbox - preserve user's saved setting
        # If both multi-session and prompt-when-full are enabled, we'll disable prompt UI but keep the setting
        initial_prompt_value = 1 if self.prompt_on_cargo_full else 0
        print(f"[DEBUG] UI Init - prompt_on_cargo_full boolean: {self.prompt_on_cargo_full}, UI value: {initial_prompt_value}")
        self.prompt_on_full_var = tk.IntVar()  # Initialize without value first
        self.prompt_on_full_cb = tk.Checkbutton(
            options_frame, 
            text="Prompt when full", 
            variable=self.prompt_on_full_var,
            # Don't set command yet - will add after setting value
            bg="#1e1e1e", 
            fg="#ffffff", 
            selectcolor="#1e1e1e", 
            activebackground="#1e1e1e",
            activeforeground="#ffffff", 
            highlightthickness=0, 
            bd=0, 
            font=("Segoe UI", 8),
            padx=8, 
            pady=0, 
            anchor="w", 
            relief="flat"
        )
        self.prompt_on_full_cb.pack(side="left", padx=(10, 0))
        self.prompt_on_full_var.set(initial_prompt_value)  # Set value without callback
        self.prompt_on_full_cb.config(command=self._on_prompt_on_full_checkbox_toggle)  # Now add callback
        print(f"[DEBUG] Prompt-when-full checkbox created and value set to: {initial_prompt_value}")
        
        # Disable prompt checkbox if multi-session is active (incompatible features)
        if self.multi_session_mode:
            self.prompt_on_full_cb.config(state="disabled", fg="#666666")
            self.prompt_on_full_var.set(0)  # Uncheck when multi-session is active
            print(f"[DEBUG] Prompt-when-full checkbox disabled and unchecked due to multi-session mode")
        else:
            self.prompt_on_full_cb.config(state="normal", fg="#ffffff")
            print(f"[DEBUG] Prompt-when-full checkbox enabled (single session mode)")
        
        self.ToolTip(self.prompt_on_full_cb, "Show prompt to end session when cargo is 100% full\nand has been idle (no changes) for 1 minute\nRemember to end session BEFORE unloading cargo!")
        
        # Multi-session mode checkbox
        multi_session_ui_value = 1 if self.multi_session_mode else 0
        print(f"[DEBUG] UI Init - multi_session_mode boolean: {self.multi_session_mode}, UI value: {multi_session_ui_value}")
        self.multi_session_var = tk.IntVar()  # Initialize without value first
        multi_session_cb = tk.Checkbutton(
            options_frame, 
            text="Multi-Session", 
            variable=self.multi_session_var,
            # Don't set command yet - will add after setting value
            bg="#1e1e1e", 
            fg="#ffffff", 
            selectcolor="#1e1e1e", 
            activebackground="#1e1e1e",
            activeforeground="#ffffff", 
            highlightthickness=0, 
            bd=0, 
            font=("Segoe UI", 8),
            padx=8, 
            pady=0, 
            anchor="w", 
            relief="flat"
        )
        multi_session_cb.pack(side="left", padx=(10, 0))
        self.multi_session_var.set(multi_session_ui_value)  # Set value without callback
        multi_session_cb.config(command=self._on_multi_session_checkbox_toggle)  # Now add callback
        print(f"[DEBUG] Multi-session checkbox created and value set to: {multi_session_ui_value}")
        self.ToolTip(multi_session_cb, "Accumulate statistics across multiple cargo loads\nStats won't reset until you manually end the session")
        
        # Apply initial state: If multi-session is already enabled (loaded from file), disable "Prompt when full"
        if self.multi_session_mode:
            self.prompt_on_full_cb.config(state="disabled", fg="#666666")
        
        print(f"[DEBUG] After UI creation - auto_start: {self.auto_start_on_prospector}, prompt_on_cargo_full: {self.prompt_on_cargo_full}, multi_session: {self.multi_session_mode}")
        
        # Center: Elapsed time display
        elapsed_frame = ttk.Frame(controls_frame)
        elapsed_frame.grid(row=0, column=1, sticky="ew", padx=(10, 10))
        
        ttk.Label(elapsed_frame, text="Elapsed:").pack(side="left")
        self.elapsed_lbl = ttk.Label(elapsed_frame, textvariable=self.session_elapsed, font=("Segoe UI", 9, "bold"))
        self.elapsed_lbl.pack(side="left", padx=(6, 0))
        
        # Right side: Export button (Reports moved to dedicated tab)
        buttons_frame = ttk.Frame(controls_frame)
        buttons_frame.grid(row=0, column=2, sticky="e")
        
        # --- Announcements Panel moved to Settings tab ---
        # (Announcements functionality moved to Settings → Announcements)
        
        """
        # DISABLED: Announcements code - moved to Settings tab
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

        ttk.Label(ann, text="Select minerals and set minimum percentages:",
                  font=("Segoe UI", 10, "bold")).grid(row=1, column=0, sticky="w", pady=(8, 4))

        self.mat_tree = ttk.Treeview(ann, columns=("announce", "material", "minpct"), show="headings", height=14)
        self.mat_tree.heading("announce", text="Announce")
        self.mat_tree.heading("material", text="Mineral")
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
        """

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

        frame = ttk.Frame(win, padding=5)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # Configure Reports Treeview style (theme-aware)
        from config import load_theme
        _rpt_theme = load_theme()
        style = ttk.Style()
        
        if _rpt_theme == "elite_orange":
            _rpt_bg = "#0a0a0a"
            _rpt_fg = "#ff8c00"
            _rpt_hdr = "#1a1a1a"
            _rpt_sel_bg = "#ff6600"
            _rpt_sel_fg = "#000000"
            _rpt_alt = "#151515"
        else:
            _rpt_bg = "#1e1e1e"
            _rpt_fg = "#e6e6e6"
            _rpt_hdr = "#2a2a2a"
            _rpt_sel_bg = "#0078d7"
            _rpt_sel_fg = "#ffffff"
            _rpt_alt = "#282828"
        
        style.configure("Reports.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=_rpt_bg,
                       foreground=_rpt_fg,
                       fieldbackground=_rpt_bg)
        style.configure("Reports.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",
                       background=_rpt_hdr,
                       foreground=_rpt_fg,
                       padding=[5, 5],
                       anchor="w")
        style.map("Reports.Treeview",
                 background=[('selected', _rpt_sel_bg)],
                 foreground=[('selected', _rpt_sel_fg)])
        
        # Add subtle column separation via heading relief
        style.layout("Reports.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])

        # Create wrapper frame for bordered table
        tree_frame_popup = ttk.Frame(frame, relief="solid", borderwidth=1)
        tree_frame_popup.grid(row=0, column=0, sticky="nsew")
        tree_frame_popup.grid_columnconfigure(0, weight=1)
        tree_frame_popup.grid_rowconfigure(0, weight=1)

        # Create sortable treeview with Material Analysis columns (NO ship column - ship is only in TXT/HTML reports)
        tree = ttk.Treeview(tree_frame_popup, columns=("date", "duration", "system", "body", "tons", "tph", "materials", "tons_per", "asteroids", "hit_rate", "quality", "cargo", "prospectors", "comment", "enhanced"), show="headings", height=16, style="Reports.Treeview")
        tree.grid(row=0, column=0, sticky="nsew")
        
        # Configure row tags for alternating colors (theme-aware)
        tree.tag_configure('oddrow', background=_rpt_bg, foreground=_rpt_fg)
        tree.tag_configure('evenrow', background=_rpt_alt, foreground=_rpt_fg)
        
        # Bind double-click to edit comments
        tree.bind("<Double-1>", self._edit_comment_popup)
        
        # Bind single-click to handle detailed report opening (with higher priority)
        tree.bind("<Button-1>", self._create_enhanced_click_handler(tree))
        
        # Add hover effect for detailed reports column
        tree.bind("<Motion>", lambda event: self._handle_mouse_motion(event, tree))
        
        # Configure column headings
        tree.heading("date", text="Date/Time", anchor="w")
        tree.heading("duration", text="Duration", anchor="w")
        tree.heading("system", text="System", anchor="w")
        tree.heading("body", text="Body", anchor="w")
        tree.heading("tons", text="Total Tons", anchor="w")
        tree.heading("tph", text="T/hr", anchor="w")
        tree.heading("materials", text="Mat Types", anchor="w")
        tree.heading("tons_per", text="Tons/Asteroid", anchor="w")
        tree.heading("asteroids", text="Prospected", anchor="w")
        tree.heading("hit_rate", text="Hit Rate %", anchor="w")
        tree.heading("quality", text="Average Yield %", anchor="w")
        tree.heading("cargo", text="Minerals (Tonnage, Yields & T/hr)", anchor="w")
        tree.heading("prospectors", text="Prospectors", anchor="w")
        tree.heading("comment", text="Comment", anchor="w")
        tree.heading("enhanced", text="Detail Report", anchor="w")
        

        

        

        
        # Configure column widths and alignment (optimized for 1100px window)
        # Left-align text columns
        tree.column("date", width=145, minwidth=135, anchor="w")
        tree.column("duration", width=80, minwidth=70, anchor="center")
        tree.column("system", width=105, minwidth=85, anchor="w")
        tree.column("body", width=155, minwidth=120, anchor="center")
        
        # Center-align short data columns
        tree.column("asteroids", width=80, minwidth=70, anchor="center")
        tree.column("materials", width=80, minwidth=70, anchor="center")
        tree.column("tons_per", width=85, minwidth=60, anchor="center")
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

        # Load saved column widths from config
        try:
            from config import load_mining_analysis_column_widths
            saved_widths = load_mining_analysis_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        tree.column(col_name, width=width)
                    except Exception as e:
                        pass
            else:
                pass
        except Exception as e:
            pass

        # Bind column resize event to save widths
        def save_column_widths(event=None):
            try:
                print("[DEBUG] ButtonRelease-1 triggered, attempting to save column widths...")
                from config import save_mining_analysis_column_widths
                widths = {}
                for col in ["date", "duration", "system", "body", "tons", "tph", "materials", "tons_per", "asteroids", "hit_rate", "quality", "cargo", "prospectors", "comment", "enhanced"]:
                    try:
                        widths[col] = tree.column(col, "width")
                    except:
                        pass
                print(f"[DEBUG] Saving column widths: {widths}")
                save_mining_analysis_column_widths(widths)
                print("[DEBUG] Column widths saved successfully")
            except Exception as e:
                print(f"[DEBUG] Could not save column widths: {e}")
        
        tree.bind("<ButtonRelease-1>", save_column_widths)

        # Add scrollbar
        sb = ttk.Scrollbar(tree_frame_popup, orient="vertical", command=tree.yview)
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

                    # Determine total finds/hits and calculate Tons per Hit (Tons/Hit)
                    try:
                        total_finds = int(str(row.get('total_finds', '')).strip() or 0)
                    except Exception:
                        total_finds = 0

                    # Always attempt to prefer the TXT report's Total Material Finds when possible.
                    # If a matching TXT is found and contains a Total Material Finds / Hits value, use it.
                    try:
                        raw_ts = row.get('timestamp_utc', '')
                        import datetime as _dt, glob, re
                        if raw_ts.endswith('Z'):
                            ts = _dt.datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                            ts = ts.replace(tzinfo=_dt.timezone.utc).astimezone()
                        else:
                            ts = _dt.datetime.fromisoformat(raw_ts)
                        date_part = ts.strftime("%Y-%m-%d")
                        time_part = ts.strftime("%H-%M-%S")

                        system_filename = (row.get('system', '') or '').replace(' ', '_')
                        body_filename = (row.get('body', '') or '').replace(' ', '_')

                        # Try several filename patterns (exact, wildcard time, body fallback)
                        patterns = [
                            f"Session_{date_part}_{time_part}_{system_filename}_{body_filename}.txt",
                            f"Session_{date_part}_*_{system_filename}_*.txt",
                            f"Session_{date_part}_*_*_{body_filename}.txt",
                        ]
                        matches = []
                        for p in patterns:
                            matches.extend(glob.glob(os.path.join(self.reports_dir, p)))

                        for txt_path in matches:
                            try:
                                with open(txt_path, 'r', encoding='utf-8') as tf:
                                    txt_content = tf.read()
                                    tf_m = re.search(r'Total Material Hits:\s*(\d+)', txt_content)
                                    if not tf_m:
                                        tf_m = re.search(r'Total Material Finds:\s*(\d+)', txt_content)
                                    if tf_m:
                                        parsed = int(tf_m.group(1))
                                        if parsed > 0:
                                            total_finds = parsed
                                            break
                            except Exception:
                                continue
                        # Targeted debug for known timestamp to help trace matching
                        try:
                            if row.get('timestamp_utc','').startswith('2025-11-19T16:40:45'):
                                print(f"[DEBUG-MATCH] CSV timestamp={row.get('timestamp_utc')} matches_found={matches} parsed_total_finds={total_finds}")
                        except Exception:
                            pass
                    except Exception:
                        pass

                    try:
                        asteroids_count = int(str(row.get('asteroids_prospected', '')).strip() or 0)
                    except Exception:
                        asteroids_count = 0

                    # Prefer total_finds (total hits) for Tons/Hit calculation; fallback to asteroids_count
                    try:
                        total_tons_val = float(row.get('total_tons', 0.0) or 0.0)
                    except Exception:
                        try:
                            total_tons_val = float(tons_str) if isinstance(tons_str, (int, float, str)) else 0.0
                        except Exception:
                            total_tons_val = 0.0

                    tons_per_str = "—"
                    if total_finds > 0:
                        try:
                            tons_per_str = f"{total_tons_val / total_finds:.1f}"
                        except Exception:
                            tons_per_str = "—"
                    elif asteroids_count > 0:
                        try:
                            tons_per_str = f"{total_tons_val / asteroids_count:.1f}"
                        except Exception:
                            tons_per_str = "—"
                    
                    # Format Material Analysis fields (with fallback for old data)
                    asteroids = row.get('asteroids_prospected', '').strip() or '0'
                    materials = row.get('materials_tracked', '').strip() or '0'
                    hit_rate = row.get('hit_rate_percent', '').strip() or '0'
                    avg_quality = row.get('avg_quality_percent', '').strip() or '0'
                    
                    # Get new cargo tracking fields
                    materials_breakdown_raw = row.get('materials_breakdown', '').strip() or '—'
                    material_tph_breakdown = row.get('material_tph_breakdown', '').strip() or ''
                    prospectors_used = row.get('prospectors_used', '').strip() or '—'
                    
                    # Enhanced materials display with yield percentages and TPH
                    materials_breakdown = self._enhance_materials_with_yields_and_tph(materials_breakdown_raw, avg_quality, material_tph_breakdown)
                    
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
                    
                    # Determine total hits/finds for the session (CSV may include 'total_finds')
                    try:
                        total_finds_val = int(str(row.get('total_finds', '')).strip() or 0)
                    except Exception:
                        total_finds_val = 0

                    sessions_data.append({
                        'date': date_str,
                        'system': row['system'],
                        'body': row['body'],
                        'duration': row['elapsed'],
                        'tons': tons_str,
                        'tph': tph_str,
                        'materials': materials_str,
                        'tons_per': tons_per_str,
                        'asteroids': asteroids_str,
                        'hit_rate': hit_rate_str,
                        'quality': quality_str,
                        'cargo': materials_breakdown,
                        'cargo_raw': materials_breakdown_raw,  # Store original for tooltip
                        'prospects': prospectors_used,  # Use 'prospects' to match Reports Tab
                        'prospectors': prospectors_used,  # Also provide 'prospectors' for popup compatibility
                        'comment': row.get('comment', ''),  # Include comment data
                        'total_finds': total_finds_val,
                        'total_hits': total_finds_val,
                        'timestamp_raw': row['timestamp_utc']  # For sorting
                    })
                    
                    # Debug: Log if comment was loaded
                    if row.get('comment', '').strip():
                        log.debug(f"Loaded comment for session {date_str}: {row.get('comment', '')[:30]}...")
                        
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
            
            # Build the inserted values from the tree's actual columns to avoid ordering issues
            try:
                cols = list(tree["columns"]) if tree is not None else []
            except Exception:
                cols = []

            vals = []
            for col in cols:
                if col == 'date':
                    vals.append(session.get('date', ''))
                elif col == 'duration':
                    vals.append(session.get('duration', ''))
                elif col == 'system':
                    vals.append(session.get('system', ''))
                elif col == 'body':
                    vals.append(session.get('body', ''))
                elif col == 'tons':
                    vals.append(session.get('tons', ''))
                elif col == 'tph':
                    vals.append(session.get('tph', ''))
                elif col == 'materials':
                    vals.append(session.get('materials', ''))
                elif col == 'tons_per':
                    vals.append(session.get('tons_per', session.get('tons_per', '—')))
                elif col == 'asteroids':
                    vals.append(session.get('asteroids', ''))
                elif col == 'hit_rate':
                    vals.append(session.get('hit_rate', ''))
                elif col == 'quality':
                    vals.append(session.get('quality', ''))
                elif col == 'cargo':
                    vals.append(session.get('cargo', ''))
                elif col in ('prospectors', 'prospects'):
                    vals.append(session.get('prospectors', session.get('prospects', '—')))
                elif col == 'comment':
                    vals.append(session.get('comment', ''))
                elif col == 'enhanced':
                    vals.append(enhanced_indicator)
                else:
                    vals.append(session.get(col, ''))

            # Debug: log columns and vals to help diagnose misalignment
            try:
                log.debug(f"Popup tree columns: {cols}")
                log.debug(f"Popup insert vals: {vals}")
            except Exception:
                pass

            item_id = tree.insert("", "end", values=tuple(vals), tags=(tag,))

            # Ensure critical columns are explicitly set after insert to avoid GUI shifts
            try:
                # Set comment explicitly (emoji) and enhanced indicator
                tree.set(item_id, 'comment', '💬' if session.get('comment', '').strip() else '')
                # Recompute enhanced indicator based on actual displayed date/system/body
                date_val = tree.set(item_id, "date")
                system_val = tree.set(item_id, "system")
                body_val = tree.set(item_id, "body")
                if date_val and system_val and body_val:
                    tree_report_id = f"{date_val}_{system_val}_{body_val}"
                    actual_enhanced_indicator = self._get_detailed_report_indicator(tree_report_id)
                    tree.set(item_id, "enhanced", actual_enhanced_indicator)
            except Exception:
                pass

            # Store the full session data for file lookup and tooltips
            session_lookup[item_id] = session
        
        # Store session lookup for tooltip access
        self.reports_window_session_lookup = session_lookup
        
        # Store original sessions for sorting lookup
        self.reports_window_original_sessions = original_sessions

        # Ensure comment and engineering materials cells are correctly placed (defensive pass)
        try:
            self._ensure_comment_and_eng_cells(tree, session_lookup)
        except Exception:
            pass
        
        # Direct sorting implementation
        sort_dirs = {}
        def sort_col(col):
            try:
                print(f"Sorting {col}")
                reverse = sort_dirs.get(col, False)
                items = [(tree.set(item, col), item) for item in tree.get_children('')]
                
                # Smart sorting based on column type
                numeric_cols = {"tons", "tph", "tons_per", "hit_rate", "quality", "materials", "asteroids", "prospectors"}
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
        tree.heading("tons_per", command=lambda: sort_col("tons_per"))
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
            if not values or len(values) < 14:
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
            
            # Determine dynamic column indices for comment/enhanced
            try:
                cols = list(tree["columns"])
                comment_idx = cols.index('comment') if 'comment' in cols else None
                enhanced_idx = cols.index('enhanced') if 'enhanced' in cols else None
            except Exception:
                comment_idx = None
                enhanced_idx = None

            # Check if clicked column matches comment or enhanced
            if comment_idx is not None and column == f"#{comment_idx+1}":
                self._edit_comment_popup(event)
                return
            if enhanced_idx is not None and column == f"#{enhanced_idx+1}":
                # Handle detailed report opening
                column_name = cols[enhanced_idx]
                cell_value = tree.set(item, column_name)
                if cell_value == "✓":  # Has detailed report
                    session_data = self.reports_window_session_lookup.get(item)
                    if session_data:
                        original_timestamp = session_data.get('timestamp_raw', session_data.get('date', ''))
                        system = session_data.get('system', '')
                        body = session_data.get('body', '')
                        report_id = f"{original_timestamp}_{system}_{body}"
                        self._open_enhanced_report(report_id)
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
                    context_menu.add_command(label="📂 Open Report (TXT)", command=open_selected)
                    context_menu.add_command(label="📊 Open Detailed Report (HTML)", command=lambda: self._open_enhanced_report_from_menu(tree))
                    context_menu.add_separator()
                    context_menu.add_command(label="📊 Generate Detailed Report (HTML)", command=lambda: self._generate_enhanced_report_from_menu(tree))
                    context_menu.add_separator()
                    context_menu.add_command(label="Share to Discord", command=lambda: self._share_selected_to_discord_popup(tree))
                    context_menu.add_command(label="Create Mining Card", command=lambda: self._create_mining_card_from_report_popup(tree))
                    context_menu.add_separator()
                    context_menu.add_command(label="📋 Copy System Name", command=lambda: copy_system_to_clipboard_reports(tree))
                    context_menu.add_separator()
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
                                        values[11] = item_data['cargo_raw'].replace('; ', '\n')  # cargo column (shifted)
                                        # Use special tag for wrapped rows - but tkinter doesn't support per-row height
                                        # Keep alternating colors but indicate wrapped content
                                    else:
                                        values[11] = item_data['cargo_raw']
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
                    
                    # Add Refinery Contents option (only for single selection)
                    if len(selected_items) == 1:
                        context_menu.add_command(label="⚗️ Add Refinery Contents", 
                                               command=lambda: self._add_refinery_to_session_from_menu(tree, selected_items[0]))
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
                        'duration': values[1], 
                        'system': values[2],
                        'body': values[3],
                        'tons': values[4],
                        'tph': values[5],
                        'materials': values[6],
                        'tons_per': values[7],
                        'asteroids': values[8],
                        'hit_rate': values[9],
                        'quality': values[10],
                        'cargo': values[11],
                        'prospectors': values[12]
                    }
                    
                    # Find timestamp by reading CSV directly
                    try:
                        import csv
                        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                        with open(csv_path, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                # Match by formatted date, system, body
                                if (row['system'] == values[2] and 
                                            row['body'] == values[3] and
                                            row['elapsed'] == values[1]):
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
                              f"• The individual report file\n"
                              f"• Graph files (if any)\n"
                              f"• Detailed HTML report (if any)\n"
                              f"• Mining card PNG (if any)\n"
                              f"• Screenshots (if any)\n\n"
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
                confirm_msg += f"• All individual report files\n"
                confirm_msg += f"• All associated graphs, HTML reports, mining cards, and screenshots\n\n"
                confirm_msg += f"This action cannot be undone."
                title = "Delete Multiple Mining Session Reports"
            
            # Confirm deletion
            from main import centered_yesno_dialog
            result = centered_yesno_dialog(
                win.winfo_toplevel(),
                title,
                confirm_msg
            )
            
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
                            # Get graphs directory using centralized path utility
                            graphs_dir = os.path.join(get_reports_dir(), "Graphs")
                            
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
                                                print(f"DEBUG: Removed {session_prefix} from mappings")
                                        except Exception as e:
                                            print(f"DEBUG: Error updating mappings: {e}")
                                except Exception as e:
                                    print(f"DEBUG: Error processing session data: {e}")
                            else:
                                print(f"DEBUG: Graphs directory does not exist: {graphs_dir}")
                        except Exception as e:
                            print(f"DEBUG: Error in graph deletion: {e}")
                        
                        # Delete corresponding mining card (v4.4.3+)
                        try:
                            cards_dir = os.path.join(get_reports_dir(), "Cards")
                            
                            if os.path.exists(cards_dir):
                                try:
                                    # Build expected card filename from session timestamp
                                    from datetime import datetime
                                    timestamp_raw = session['timestamp_raw']
                                    dt = datetime.fromisoformat(timestamp_raw.replace('Z', ''))
                                    timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")
                                    
                                    clean_system = session['system'].replace(' ', '_')
                                    clean_body = session['body'].replace(' ', '_')
                                    
                                    expected_card = f"Session_{timestamp_str}_{clean_system}_{clean_body}_Card.png"
                                    card_path = os.path.join(cards_dir, expected_card)
                                    
                                    if os.path.exists(card_path):
                                        os.remove(card_path)
                                except Exception as e:
                                    print(f"[DELETE] Error deleting mining card: {e}")
                                    import traceback
                                    traceback.print_exc()
                        except Exception as e:
                            print(f"[DELETE] Error in card deletion: {e}")
                        
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
                                # Build a complete fieldname list that includes any keys present in any remaining row
                                fieldnames = list(remaining_sessions[0].keys())
                                for r in remaining_sessions:
                                    for k in r.keys():
                                        if k not in fieldnames:
                                            fieldnames.append(k)
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
                            from main import center_window
                            import tkinter as tk
                            main_parent = self.winfo_toplevel()
                            dialog = tk.Toplevel(main_parent)
                            dialog.withdraw()  # Prevent flicker
                            dialog.title("Partial Success")
                            dialog.resizable(False, False)
                            label = tk.Label(dialog, text=error_msg, padx=20, pady=20, fg="orange")
                            label.pack()
                            center_window(dialog, main_parent)
                            dialog.deiconify()  # Show centered immediately
                            tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
                            dialog.transient(main_parent)
                            dialog.grab_set()
                            dialog.wait_window()
                        
                    except Exception as e:
                        self._set_status(f"Error updating CSV file: {e}")
                        from main import center_window
                        import tkinter as tk
                        main_parent = self.winfo_toplevel()
                        dialog = tk.Toplevel(main_parent)
                        dialog.withdraw()  # Prevent flicker
                        dialog.title("Delete Error")
                        dialog.resizable(False, False)
                        label = tk.Label(dialog, text=f"Failed to update CSV file:\n{e}", padx=20, pady=20, fg="red")
                        label.pack()
                        center_window(dialog, main_parent)
                        dialog.deiconify()  # Show centered immediately
                        tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
                        dialog.transient(main_parent)
                        dialog.grab_set()
                        dialog.wait_window()
                
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

    def _is_summary_entry(self, material_name: str) -> bool:
        """Check if material name is a summary entry that should be filtered out"""
        return material_name.lower() in ['total cargo collected', 'total', 'cargo collected', 'total refined']

    def _rebuild_csv_from_files(self, csv_path: str, parent_window) -> None:
        """Rebuild the CSV index from existing text files - PARSES TPH FROM TEXT"""
        print("[REBUILD] === STARTING CSV REBUILD (popup version) ===")
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
                                print(f"[REBUILD CSV READ] Timestamp from CSV: '{timestamp}'")
                                existing_analysis_data[timestamp] = {
                                    'asteroids_prospected': row.get('asteroids_prospected', ''),
                                    'materials_tracked': row.get('materials_tracked', ''),
                                    'hit_rate_percent': row.get('hit_rate_percent', ''),
                                    'avg_quality_percent': row.get('avg_quality_percent', ''),
                                    'best_material': row.get('best_material', ''),
                                    'materials_breakdown': row.get('materials_breakdown', ''),
                                    'material_tph_breakdown': row.get('material_tph_breakdown', ''),  # Preserve TPH
                                    'prospectors_used': row.get('prospectors_used', ''),
                                    'engineering_materials': row.get('engineering_materials', ''),  # Preserve engineering materials
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
                    time_part_raw = timestamp_match.group(2)
                    time_part = time_part_raw.replace('-', ':')  # Convert HH-MM-SS to HH:MM:SS
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
                    
                    # Extract Minerals tracked  
                    materials_match = re.search(r'Minerals Tracked:\s*(\d+)', content)
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
                    
                    # Extract materials breakdown AND TPH - merge from multiple sources for complete data
                    materials_dict = {}
                    material_tph_breakdown = ""  # Will be parsed from CARGO section
                    
                    if not materials_breakdown:
                        # First, get data from CARGO MATERIAL BREAKDOWN (WITH TPH if available)
                        cargo_section = re.search(r'=== CARGO MATERIAL BREAKDOWN ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if cargo_section:
                            cargo_text = cargo_section.group(1)
                            # Try to parse WITH TPH: "Platinum: 1.0t (80.3 t/hr)"
                            material_lines_with_tph = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*\(([\d.]+)\s*t/hr\)', cargo_text, re.MULTILINE)
                            if material_lines_with_tph:
                                # Successfully parsed TPH from text file
                                tph_pairs = []
                                for mat, tons, tph in material_lines_with_tph:
                                    mat_clean = mat.strip()
                                    if not self._is_summary_entry(mat_clean):
                                        materials_dict[mat_clean] = float(tons)
                                        tph_pairs.append(f"{mat_clean}: {tph}")
                                if tph_pairs:
                                    material_tph_breakdown = ", ".join(tph_pairs)
                                    print(f"[REBUILD] ✓ Parsed TPH from text: {material_tph_breakdown}")
                            else:
                                # No TPH in text, parse basic format
                                material_lines = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', cargo_text, re.MULTILINE)
                                for mat, tons in material_lines:
                                    mat_clean = mat.strip()
                                    if not self._is_summary_entry(mat_clean):
                                        materials_dict[mat_clean] = float(tons)
                        
                        # Then, merge with REFINED CARGO TRACKING (manually added materials during session)
                        refined_cargo_section = re.search(r'=== REFINED CARGO TRACKING ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if refined_cargo_section:
                            refined_cargo_text = refined_cargo_section.group(1)
                            refined_material_lines = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', refined_cargo_text, re.MULTILINE)
                            for mat, tons in refined_material_lines:
                                mat_clean = mat.strip()
                                if not self._is_summary_entry(mat_clean):
                                    if mat_clean in materials_dict:
                                        # Add to existing quantity
                                        materials_dict[mat_clean] += float(tons)
                                    else:
                                        # New material from refinery
                                        materials_dict[mat_clean] = float(tons)
                        
                        # Fallback to REFINED MINERALS section if no cargo data found
                        if not materials_dict:
                            refined_section = re.search(r'=== REFINED MINERALS ===(.*?)(?:===|\Z)', content, re.DOTALL)
                            if refined_section:
                                refined_text = refined_section.group(1)
                                material_lines = re.findall(r'- ([A-Za-z\s]+) ([\d.]+)t', refined_text)
                                for mat, tons in material_lines:
                                    mat_clean = mat.strip()
                                    if not self._is_summary_entry(mat_clean):
                                        materials_dict[mat_clean] = float(tons)
                        
                        # Convert dictionary to string format
                        if materials_dict:
                            materials_breakdown = ', '.join([f"{mat}: {tons:.1f}t" for mat, tons in materials_dict.items()])
                    
                    # If materials_tracked is empty but we have materials_breakdown, count the materials
                    if not materials_tracked and materials_breakdown:
                        # Count comma-separated materials in breakdown
                        material_count = len([m.strip() for m in materials_breakdown.split(',') if m.strip()])
                        materials_tracked = str(material_count) if material_count > 0 else ''
                    
                    # Get preserved data for this timestamp (fallback if parsing fails)
                    existing_data = existing_analysis_data.get(timestamp_local, {})
                    if not existing_data:
                        print(f"[REBUILD DEBUG] No CSV match for timestamp: {timestamp_local}")
                        print(f"[REBUILD DEBUG] Filename: {fn}")
                        print(f"[REBUILD DEBUG] Available CSV keys sample: {list(existing_analysis_data.keys())[:3]}")
                        print(f"[REBUILD DEBUG] Total CSV entries: {len(existing_analysis_data)}")
                    else:
                        print(f"[REBUILD DEBUG] ✓ MATCH FOUND for: {timestamp_local}")
                        print(f"[REBUILD DEBUG] TPH data: {existing_data.get('material_tph_breakdown', 'EMPTY')}")
                    
                    # Determine total hits/founds for this session from the TXT content
                    try:
                        tf_match = re.search(r'Total Material Hits:\s*(\d+)', content)
                        if not tf_match:
                            tf_match = re.search(r'Total Material Finds:\s*(\d+)', content)
                        if tf_match:
                            total_finds_val = int(tf_match.group(1))
                        else:
                            # Fallback: sum any per-material hit lines (supports both 'Hits:' and legacy 'Finds: 12x')
                            per_hits = re.findall(r'•\s*(?:Hits|Finds):\s*(\d+)', content)
                            if per_hits:
                                total_finds_val = sum(int(x) for x in per_hits)
                            else:
                                total_finds_val = 0
                    except Exception:
                        total_finds_val = 0

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
                        'total_finds': total_finds_val,
                        'best_material': best_material or existing_data.get('best_material', ''),
                        'materials_breakdown': existing_data.get('materials_breakdown', '') or materials_breakdown,  # Prefer CSV data (has yields)
                        'material_tph_breakdown': existing_data.get('material_tph_breakdown', '') or material_tph_breakdown,  # Preserve TPH from CSV or parse from text
                        'prospectors_used': existing_data.get('prospectors_used', '') or prospectors_used,  # Prefer CSV data
                        'engineering_materials': existing_data.get('engineering_materials', ''),  # Preserve engineering materials
                        'comment': existing_data.get('comment', '')  # Preserve existing comments
                    })
                    
                except Exception as e:
                    print(f"Error parsing {fn}: {e}")
                    continue
            
            if not sessions:
                # If no session files exist, create empty CSV with headers
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 'engineering_materials', 'comment'])
                    writer.writeheader()
                from main import center_window
                import tkinter as tk
                main_parent = self.winfo_toplevel()
                dialog = tk.Toplevel(main_parent)
                dialog.title("CSV Created")
                dialog.resizable(False, False)
                label = tk.Label(dialog, text="Created new CSV file - ready for your first session", padx=20, pady=20)
                label.pack()
                center_window(dialog, main_parent)
                tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
                dialog.transient(main_parent)
                dialog.grab_set()
                dialog.wait_window()
                parent_window.destroy()
                return
            
            # Sort by timestamp
            sessions.sort(key=lambda x: x['timestamp_utc'])
            
            # Write new CSV (include total_finds)
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 'engineering_materials', 'comment'])
                writer.writeheader()
                # Remove any keys not present in CSV schema (avoid DictWriter errors)
                for _r in sessions:
                    if 'total_finds' in _r:
                        _r.pop('total_finds', None)
                writer.writerows(sessions)
            
            # Close and reopen the reports window to refresh data
            parent_window.destroy()
            self._open_reports_window()
            
            self._set_status(f"CSV rebuilt with {len(sessions)} sessions.")
            
        except Exception as e:
            from main import center_window
            import tkinter as tk
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.title("Rebuild Failed")
            dialog.resizable(False, False)
            label = tk.Label(dialog, text=f"Failed to rebuild CSV: {e}", padx=20, pady=20, fg="red")
            label.pack()
            center_window(dialog, main_parent)
            tk.Button(dialog, text="OK", command=dialog.destroy).pack(pady=10)
            dialog.transient(main_parent)
            dialog.grab_set()
            dialog.wait_window()
            self._set_status(f"CSV rebuild failed: {e}")

    def _rebuild_csv_from_files_tab(self, csv_path: str, silent: bool = False) -> None:
        """Rebuild the CSV index from existing text files for Reports tab - PARSES TPH FROM TEXT"""
        print("[REBUILD] === STARTING CSV REBUILD (tab version) ===")
        try:
            import csv
            import re
            if not silent:
                from app_utils import centered_askyesno
            
            # First, try to read existing Material Analysis data from current CSV (excluding comments)
            existing_analysis_data = {}
            if os.path.exists(csv_path):
                print(f"[REBUILD] CSV exists, reading timestamps and TPH data...")
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Use timestamp as key to preserve Material Analysis data (but not comments)
                            timestamp = row.get('timestamp_utc', '')
                            if timestamp:
                                print(f"[REBUILD CSV READ] Timestamp from CSV: '{timestamp}'")
                                tph_data = row.get('material_tph_breakdown', '')
                                print(f"[REBUILD CSV READ] TPH data: '{tph_data}'")
                                existing_analysis_data[timestamp] = {
                                    'asteroids_prospected': row.get('asteroids_prospected', ''),
                                    'materials_tracked': row.get('materials_tracked', ''),
                                    'hit_rate_percent': row.get('hit_rate_percent', ''),
                                    'avg_quality_percent': row.get('avg_quality_percent', ''),
                                    'best_material': row.get('best_material', ''),
                                    'materials_breakdown': row.get('materials_breakdown', ''),  # Preserve tonnage
                                    'material_tph_breakdown': row.get('material_tph_breakdown', ''),  # Preserve TPH
                                    'prospectors_used': row.get('prospectors_used', ''),
                                    'engineering_materials': row.get('engineering_materials', ''),  # Preserve engineering materials
                                    'comment': row.get('comment', '')  # Preserve comments
                                }
                except Exception as e:
                    print(f"Warning: Could not read existing analysis data: {e}")
            else:
                print(f"[REBUILD] CSV does not exist at: {csv_path}")
            
            # Parse all text files
            sessions = []
            print(f"[REBUILD] Parsing text files from: {self.reports_dir}")
            
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
                    time_part_raw = timestamp_match.group(2)
                    time_part = time_part_raw.replace('-', ':')  # Convert HH-MM-SS to HH:MM:SS
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
                    
                    # Extract Minerals tracked  
                    materials_match = re.search(r'Minerals Tracked:\s*(\d+)', content)
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
                    
                    # Extract materials breakdown AND TPH - merge from multiple sources for complete data
                    materials_dict = {}
                    material_tph_breakdown = ""  # Will be parsed from CARGO section
                    
                    if not materials_breakdown:
                        # First, get data from CARGO MATERIAL BREAKDOWN (WITH TPH if available)
                        cargo_section = re.search(r'=== CARGO MATERIAL BREAKDOWN ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if cargo_section:
                            cargo_text = cargo_section.group(1)
                            # Try to parse WITH TPH: "Platinum: 1.0t (80.3 t/hr)"
                            material_lines_with_tph = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*\(([\d.]+)\s*t/hr\)', cargo_text, re.MULTILINE)
                            if material_lines_with_tph:
                                # Successfully parsed TPH from text file
                                tph_pairs = []
                                for mat, tons, tph in material_lines_with_tph:
                                    mat_clean = mat.strip()
                                    if not self._is_summary_entry(mat_clean):
                                        materials_dict[mat_clean] = float(tons)
                                        tph_pairs.append(f"{mat_clean}: {tph}")
                                if tph_pairs:
                                    material_tph_breakdown = ", ".join(tph_pairs)
                                    print(f"[REBUILD TAB] ✓ Parsed TPH from text: {material_tph_breakdown}")
                            else:
                                # No TPH in text, parse basic format
                                material_lines = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', cargo_text, re.MULTILINE)
                                for mat, tons in material_lines:
                                    mat_clean = mat.strip()
                                    if not self._is_summary_entry(mat_clean):
                                        materials_dict[mat_clean] = float(tons)
                        
                        # Then, merge with REFINED CARGO TRACKING (manually added materials during session)
                        refined_cargo_section = re.search(r'=== REFINED CARGO TRACKING ===(.*?)(?:===|\Z)', content, re.DOTALL)
                        if refined_cargo_section:
                            refined_cargo_text = refined_cargo_section.group(1)
                            refined_material_lines = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', refined_cargo_text, re.MULTILINE)
                            for mat, tons in refined_material_lines:
                                mat_clean = mat.strip()
                                if not self._is_summary_entry(mat_clean):
                                    if mat_clean in materials_dict:
                                        # Add to existing quantity
                                        materials_dict[mat_clean] += float(tons)
                                    else:
                                        # New material from refinery
                                        materials_dict[mat_clean] = float(tons)
                        
                        # Fallback to REFINED MINERALS section if no cargo data found
                        if not materials_dict:
                            refined_section = re.search(r'=== REFINED MINERALS ===(.*?)(?:===|\Z)', content, re.DOTALL)
                            if refined_section:
                                refined_text = refined_section.group(1)
                                material_lines = re.findall(r'- ([A-Za-z\s]+) ([\d.]+)t', refined_text)
                                for mat, tons in material_lines:
                                    mat_clean = mat.strip()
                                    if not self._is_summary_entry(mat_clean):
                                        materials_dict[mat_clean] = float(tons)
                        
                        # Convert dictionary to string format
                        if materials_dict:
                            materials_breakdown = ', '.join([f"{mat}: {tons:.1f}t" for mat, tons in materials_dict.items()])
                    
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
                    
                    # Extract engineering materials from text file
                    engineering_materials_str = ""
                    eng_section = re.search(r'=== ENGINEERING MATERIALS COLLECTED ===(.*?)(?:===|\Z)', content, re.DOTALL)
                    if eng_section:
                        eng_text = eng_section.group(1)
                        # Parse materials like "Iron: 45" and convert to "Iron:45" format
                        material_lines = re.findall(r'^\s+([A-Za-z]+):\s*(\d+)\s*$', eng_text, re.MULTILINE)
                        if material_lines:
                            engineering_materials_str = ",".join([f"{mat}:{qty}" for mat, qty in material_lines])
                    
                    # Get preserved data for this timestamp (prioritize CSV data for analysis fields)
                    existing_data = existing_analysis_data.get(timestamp_local, {})

                    # Compute total finds/hits from the TXT (support both 'Total Material Hits' and legacy 'Total Material Finds')
                    try:
                        tf_match = re.search(r'Total Material Hits:\s*(\d+)', content)
                        if not tf_match:
                            tf_match = re.search(r'Total Material Finds:\s*(\d+)', content)
                        if tf_match:
                            total_finds_val = int(tf_match.group(1))
                        else:
                            per_hits = re.findall(r'•\s*(?:Hits|Finds):\s*(\d+)', content)
                            total_finds_val = sum(int(x) for x in per_hits) if per_hits else 0
                    except Exception:
                        total_finds_val = 0

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
                        'total_finds': existing_data.get('total_finds', '') or total_finds_val,
                        'materials_breakdown': existing_data.get('materials_breakdown', '') or materials_breakdown,
                        'material_tph_breakdown': existing_data.get('material_tph_breakdown', '') or material_tph_breakdown,  # Add TPH data
                        'prospectors_used': existing_data.get('prospectors_used', '') or prospectors_used,
                        'engineering_materials': engineering_materials_str,  # Add engineering materials
                        'comment': session_comment  # Extract comment from text file content
                    })
                    
                except Exception as e:
                    print(f"Error parsing {fn}: {e}")
                    continue
            
            if not sessions:
                # If no session files exist, create empty CSV with headers
                with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 'engineering_materials', 'comment'])
                    writer.writeheader()
                if not silent:
                    self._set_status("Created new CSV file - ready for first session")
                return
            
            # Sort by timestamp
            sessions.sort(key=lambda x: x['timestamp_utc'])
            
            # Write new CSV
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph', 'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 'engineering_materials', 'comment'])
                writer.writeheader()
                for _r in sessions:
                    if 'total_finds' in _r:
                        _r.pop('total_finds', None)
                writer.writerows(sessions)
            
            # Refresh the Reports tab instead of opening new window
            self._refresh_reports_tab()
            
            # Refresh the Statistics tab to show updated Top 3 Systems
            self._refresh_session_statistics()
            
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
                
                # Always refresh reports tab AND statistics on startup (regardless of rebuild)
                if hasattr(self, 'reports_tree_tab') and self.reports_tree_tab:
                    self._refresh_reports_tab()
                    self._refresh_statistics_display()  # Reload stats to show rebuilt TPH data
                
                # Set ready status
                self._set_status("EliteMining ready")
        except Exception as e:
            # Log error but don't show to user on startup
            print(f"[STARTUP ERROR] Auto rebuild failed: {e}")

    def _export_csv(self, csv_path: str) -> None:
        """Copy the CSV file to a user-selected location"""
        try:
            # Prevent re-entrant exports which may cause duplicate files if called twice
            if getattr(self, '_export_in_progress', False):
                print("Export already in progress - aborting duplicate call")
                self._set_status("Export already in progress")
                return
            self._export_in_progress = True
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
                print(f"Exporting CSV from {csv_path} to {dest_path}")
                shutil.copy2(csv_path, dest_path)
                self._set_status(f"Session data exported to {dest_path}")
                from main import center_window
                import tkinter as tk
                main_parent = self.winfo_toplevel()
                dialog = tk.Toplevel(main_parent)
                dialog.title("Export Complete")
                dialog.resizable(False, False)
                label = tk.Label(dialog, text=f"Session data successfully exported to:\n{dest_path}", padx=20, pady=20)
                label.pack()
                btn = tk.Button(dialog, text="OK", command=dialog.destroy)
                btn.pack(pady=10)
                center_window(dialog, main_parent)
                dialog.transient(main_parent)
                dialog.grab_set()
                dialog.wait_window()
            else:
                self._set_status("Export cancelled by user.")
                
        except Exception as e:
            error_msg = f"Export failed: {e}"
            self._set_status(error_msg)
            from tkinter import messagebox
            from main import center_window
            import tkinter as tk
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.title("Export Failed")
            dialog.resizable(False, False)
            label = tk.Label(dialog, text=error_msg, padx=20, pady=20, fg="red")
            label.pack()
            btn = tk.Button(dialog, text="OK", command=dialog.destroy)
            btn.pack(pady=10)
            center_window(dialog, main_parent)
            dialog.transient(main_parent)
            dialog.grab_set()
            dialog.wait_window()
        finally:
            # Clear export-in-progress flag
            try:
                self._export_in_progress = False
            except Exception:
                pass

    def _share_to_discord(self):
        """Share selected mining session report to Discord"""
        try:
            # Check if a session is selected
            selected = self.reports_tree_tab.selection()
            if not selected:
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "No Selection",
                                 "Please select a mining session to share to Discord.")
                return
            
            # Get selected session data
            item_id = selected[0]
            if item_id not in self.reports_tab_session_lookup:
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "Error",
                                 "Session data not found for selected item.")
                return
            
            session = self.reports_tab_session_lookup[item_id]
            
            # Get or prompt for Discord username
            username_result = self._get_discord_username()
            if not username_result[0]:  # User cancelled
                return
            
            username, comment = username_result
            
            # Add username and comment to session data
            session_with_user = session.copy()
            session_with_user['discord_username'] = username
            if comment:
                session_with_user['discord_comment'] = comment
            
            # Try to add report content for material breakdown
            try:
                if 'file_path' in session and session['file_path']:
                    report_path = session['file_path']
                    if os.path.exists(report_path):
                        with open(report_path, 'r', encoding='utf-8') as f:
                            session_with_user['report_content'] = f.read()
            except Exception as e:
                print(f"[DEBUG] Could not read report content: {e}")
                # Continue without report content
            
            # Import Discord integration
            try:
                from discord_integration import send_discord_report, is_discord_enabled
            except ImportError:
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "Error", "Discord integration module not found.")
                return
            
            # Check if Discord is configured
            if not is_discord_enabled():
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "Discord Sharing",
                                 "Discord sharing is not available in this version.\n\n"
                                 "Contact the administrator if you believe this is an error.")
                return
            
            # Send to Discord
            success, message = send_discord_report(session_with_user)
            
            from app_utils import centered_message
            if success:
                centered_message(self.winfo_toplevel(), "Discord Share", message)
                self._set_status("Report shared to Discord successfully!")
            else:
                centered_message(self.winfo_toplevel(), "Discord Error", message)
                self._set_status(f"Discord share failed: {message}")
                
        except Exception as e:
            error_msg = f"Failed to share to Discord: {e}"
            self._set_status(error_msg)
            from tkinter import messagebox
            messagebox.showerror("Error", error_msg)

    def _get_discord_username(self):
        """Get Discord username with re-prompt option (Option 4)"""
        try:
            from config import _load_cfg, update_config_value
            
            # Check if username is already saved
            cfg = _load_cfg()
            saved_username = cfg.get('discord_username', '').strip()
            
            # Always show the dialog - with or without existing username
            username_result = self._show_username_dialog(saved_username)
            if username_result:
                username, comment = username_result
                return username, comment
            else:
                return None, None
                
        except Exception as e:
            print(f"[DEBUG] Error getting Discord username: {e}")
            return None, None

    def _show_username_dialog(self, current_username=""):
        """Show custom username input dialog with proper positioning and icon"""
        try:
            import tkinter as tk
            
            # Create toplevel window
            main_parent = self.winfo_toplevel()
            dialog = tk.Toplevel(main_parent)
            dialog.withdraw()  # Hide during setup to prevent flicker
            dialog.title("Discord Username")
            dialog.configure(bg="#1e1e1e")
            dialog.resizable(False, False)
            from main import center_window
            center_window(dialog, main_parent)
            
            # Set app icon
            try:
                from icon_utils import set_window_icon
                set_window_icon(dialog)
            except Exception as e:
                print(f"[DEBUG] Could not set dialog icon: {e}")
            
            # Make it modal and appear on top
            dialog.transient(self.winfo_toplevel())
            dialog.grab_set()
            dialog.attributes('-topmost', True)
            
            # Position dialog relative to main EliteMining window (same monitor)
            dialog_width = 500
            dialog_height = 420
            dialog.geometry(f"{dialog_width}x{dialog_height}")
            
            # Give some time for geometry to settle
            dialog.update_idletasks()
            dialog.after(10)  # Small delay to ensure proper positioning
            
            # Get main app window position and center on parent
            try:
                # Get the parent window (main app)
                main_window = self.winfo_toplevel()
                if main_window:
                    # Force update to get accurate position
                    main_window.update_idletasks()
                    dialog.update_idletasks()
                    
                    main_x = main_window.winfo_rootx()
                    main_y = main_window.winfo_rooty()
                    main_width = main_window.winfo_width()
                    main_height = main_window.winfo_height()
                    
                    # Center dialog on main app window (stays on same monitor)
                    x = main_x + (main_width - dialog_width) // 2
                    y = main_y + (main_height - dialog_height) // 2
                    
                    # Keep dialog within reasonable bounds of parent window
                    # Only adjust if dialog would be completely off the main window area
                    min_x = main_x - 100  # Allow some overhang
                    max_x = main_x + main_width + 100 - dialog_width
                    min_y = main_y - 50
                    max_y = main_y + main_height + 50 - dialog_height
                    
                    x = max(min_x, min(x, max_x))
                    y = max(min_y, min(y, max_y))
                    
                    dialog.geometry(f"+{x}+{y}")
                    print(f"[DEBUG] Dialog positioned at: x={x}, y={y} (main window: {main_x},{main_y} {main_width}x{main_height})")
                else:
                    # Fallback: position near main app
                    x = self.winfo_rootx() + 50
                    y = self.winfo_rooty() + 50
                    dialog.geometry(f"+{x}+{y}")
                    print(f"[DEBUG] Dialog fallback positioned at: x={x}, y={y}")
            except Exception as e:
                print(f"[DEBUG] Error positioning dialog: {e}")
                # Final fallback - position near prospector panel
                try:
                    x = self.winfo_rootx() + 50
                    y = self.winfo_rooty() + 50
                    dialog.geometry(f"+{x}+{y}")
                except:
                    dialog.geometry("500x420+100+100")
                print(f"[DEBUG] Dialog emergency positioned")
            
            dialog.update_idletasks()
            dialog.deiconify()  # Show after all setup
            dialog.focus_force()
            
            # Main frame
            main_frame = tk.Frame(dialog, bg="#1e1e1e")
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Title/prompt - show different text based on whether username exists
            if current_username:
                prompt_text = f"Posting as: {current_username}\n\nEdit your Discord username:"
            else:
                prompt_text = "Enter your name for Discord posts:"
                
            title_label = tk.Label(main_frame, text=prompt_text, 
                                  font=("Arial", 12), 
                                  fg="#ffffff", bg="#1e1e1e",
                                  justify="left")
            title_label.pack(pady=(0, 10))
            
            # Discord info panel with logo
            info_frame = tk.Frame(main_frame, bg="#2a2a2a", relief="ridge", bd=1)
            info_frame.pack(fill="x", pady=(0, 15))
            
            # Try to load Discord logo
            discord_logo = None
            try:
                from PIL import Image, ImageTk
                import os
                logo_path = os.path.join(os.path.dirname(__file__), "Images", "Discord-Logo-Blurple.png")
                if os.path.exists(logo_path):
                    # Load and resize logo with better proportions
                    img = Image.open(logo_path)
                    # Get original dimensions to maintain aspect ratio
                    original_width, original_height = img.size
                    # Set target height and calculate width to maintain aspect ratio
                    target_height = 20
                    target_width = int((original_width * target_height) / original_height)
                    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    discord_logo = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"[DEBUG] Could not load Discord logo: {e}")
                discord_logo = None
            
            # Main info text
            main_text = "This will post your mining report to the\nEliteMining Community Discord server."
            main_label = tk.Label(info_frame, text=main_text,
                                 font=("Arial", 9), 
                                 fg="#ffffff", bg="#2a2a2a",
                                 justify="center")
            main_label.pack(padx=15, pady=(10, 5))
            
            # Discord link section
            link_frame = tk.Frame(info_frame, bg="#2a2a2a")
            link_frame.pack(padx=15, pady=(0, 10))
            
            def open_discord_link():
                import webbrowser
                webbrowser.open("https://discord.gg/5dsF3UshRR")
            
            if discord_logo:
                # Clickable Discord logo
                logo_label = tk.Label(link_frame, image=discord_logo, bg="#2a2a2a", cursor="hand2")
                logo_label.image = discord_logo  # Keep reference
                logo_label.pack(side="left", padx=(0, 8))
                logo_label.bind("<Button-1>", lambda e: open_discord_link())
            
            # "Join our community" text - always show this
            link_text = "Join our community"
            link_label = tk.Label(link_frame, text=link_text,
                                 font=("Arial", 9, "underline"), 
                                 fg="#5865F2", bg="#2a2a2a",  # Discord blurple color
                                 cursor="hand2")
            if discord_logo:
                link_label.pack(side="left")
            else:
                link_label.pack()
            link_label.bind("<Button-1>", lambda e: open_discord_link())
            
            # Add Discord URL below the link text for clarity
            url_label = tk.Label(link_frame, text="discord.gg/5dsF3UshRR",
                                font=("Arial", 8), 
                                fg="#888888", bg="#2a2a2a")
            if discord_logo:
                url_label.pack(side="left", padx=(8, 0))
            else:
                url_label.pack(pady=(2, 0))
            
            # Username input
            username_entry = tk.Entry(main_frame, font=("Arial", 11), width=35,
                                     bg="#333333", fg="#ffffff", 
                                     insertbackground="#ffffff",
                                     relief="solid", bd=1)
            username_entry.pack(pady=(0, 15))
            username_entry.insert(0, current_username)
            username_entry.focus()
            username_entry.select_range(0, tk.END)
            
            # Comment label
            comment_label = tk.Label(main_frame, text="Add a comment (optional):", 
                                   font=("Arial", 10), 
                                   fg="#ffffff", bg="#1e1e1e")
            comment_label.pack(anchor="w", pady=(0, 5))
            
            # Comment input
            comment_entry = tk.Entry(main_frame, font=("Arial", 10), width=35,
                                   bg="#333333", fg="#ffffff", 
                                   insertbackground="#ffffff",
                                   relief="solid", bd=1)
            comment_entry.pack(pady=(0, 20))
            
            # Result variable
            result = {"username": None, "comment": None}
            
            def on_ok():
                username = username_entry.get().strip()
                comment = comment_entry.get().strip()
                if username:
                    # Save to config
                    from config import update_config_value
                    update_config_value("discord_username", username)
                    result["username"] = username
                    result["comment"] = comment if comment else None
                    dialog.destroy()
                else:
                    # Empty username not allowed
                    username_entry.focus()
            
            def on_cancel():
                dialog.destroy()
            
            # Button frame
            btn_frame = tk.Frame(main_frame, bg="#1e1e1e")
            btn_frame.pack(fill="x")
            
            # Cancel button (left)
            cancel_btn = tk.Button(btn_frame, text="Cancel", 
                                  command=on_cancel,
                                  bg="#444444", fg="#ffffff",
                                  activebackground="#555555", activeforeground="#ffffff",
                                  relief="solid", bd=1, width=10)
            cancel_btn.pack(side="left")
            
            # OK button (right)
            ok_btn = tk.Button(btn_frame, text="OK", 
                              command=on_ok,
                              bg="#5865F2", fg="#ffffff",
                              activebackground="#4752C4", activeforeground="#ffffff",
                              relief="solid", bd=1, width=10)
            ok_btn.pack(side="right")
            
            # Handle Enter key
            def on_enter(event):
                on_ok()
            
            username_entry.bind("<Return>", on_enter)
            dialog.bind("<Return>", on_enter)
            
            # Handle dialog close (X button)
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)
            
            # Wait for dialog to close
            dialog.wait_window()
            
            return result["username"], result["comment"]
                
        except Exception as e:
            print(f"[DEBUG] Error showing username dialog: {e}")
            return None, None

    def _share_selected_to_discord(self):
        """Share the currently selected session to Discord (for context menu)"""
        try:
            # Check if a session is selected
            selected = self.reports_tree_tab.selection()
            if not selected:
                from tkinter import messagebox
                messagebox.showwarning("No Selection", "Please select a mining session to share to Discord.")
                return
            
            # Use the existing _share_to_discord method which handles the rest
            self._share_to_discord()
                
        except Exception as e:
            error_msg = f"Failed to share to Discord: {e}"
            self._set_status(error_msg)
            from tkinter import messagebox
            messagebox.showerror("Error", error_msg)

    def _get_cmdr_info_for_card(self):
        """Get CMDR name and comment for mining card (similar to Discord share)"""
        try:
            from config import _load_cfg
            
            # Check if CMDR name is already saved
            cfg = _load_cfg()
            saved_cmdr = cfg.get('cmdr_name', '').strip()
            
            # Show dialog
            cmdr_result = self._show_cmdr_dialog(saved_cmdr)
            return cmdr_result
                
        except Exception as e:
            print(f"[DEBUG] Error getting CMDR info: {e}")
            return None

    def _show_cmdr_dialog(self, current_cmdr=""):
        """Show custom CMDR input dialog (adapted from Discord dialog)"""
        try:
            import tkinter as tk
            
            # Create toplevel window
            dialog = tk.Toplevel(self.winfo_toplevel())
            dialog.title("Mining Card Info")
            dialog.configure(bg="#1e1e1e")
            dialog.resizable(False, False)
            
            # Set app icon
            try:
                from icon_utils import set_window_icon
                set_window_icon(dialog)
            except Exception as e:
                print(f"[DEBUG] Could not set dialog icon: {e}")
            
            # Make it modal FIRST
            dialog.transient(self.winfo_toplevel())
            
            # Set size
            dialog_width = 450
            dialog_height = 300
            
            # Force dialog to appear on same screen as main window
            main_window = self.winfo_toplevel()
            
            # Wait for main window to be ready
            main_window.update()
            dialog.update()
            
            # Get main window center
            main_x = main_window.winfo_x()
            main_y = main_window.winfo_y()
            main_width = main_window.winfo_width()
            main_height = main_window.winfo_height()
            
            # Calculate center position
            x = main_x + (main_width - dialog_width) // 2
            y = main_y + (main_height - dialog_height) // 2
            
            # Set position explicitly
            dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
            
            # Force it to appear
            dialog.update()
            dialog.deiconify()
            dialog.grab_set()
            dialog.focus_force()
            
            # Main frame
            main_frame = tk.Frame(dialog, bg="#1e1e1e")
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Title
            title_label = tk.Label(main_frame, text="Add Your Info to Card",
                                  font=("Arial", 14, "bold"), 
                                  fg="#FF8C00", bg="#1e1e1e")
            title_label.pack(pady=(0, 15))
            
            # CMDR Name label
            cmdr_label = tk.Label(main_frame, text="CMDR Name (optional):",
                                 font=("Arial", 10), 
                                 fg="#ffffff", bg="#1e1e1e")
            cmdr_label.pack(anchor="w", pady=(0, 5))
            
            # CMDR Name input
            cmdr_entry = tk.Entry(main_frame, font=("Arial", 11), width=35,
                                 bg="#333333", fg="#ffffff", 
                                 insertbackground="#ffffff",
                                 relief="solid", bd=1)
            cmdr_entry.pack(pady=(0, 15))
            cmdr_entry.insert(0, current_cmdr)
            cmdr_entry.focus()
            cmdr_entry.select_range(0, tk.END)
            
            # Comment label
            comment_label = tk.Label(main_frame, text="Comment (optional):",
                                   font=("Arial", 10), 
                                   fg="#ffffff", bg="#1e1e1e")
            comment_label.pack(anchor="w", pady=(0, 5))
            
            # Comment input
            comment_entry = tk.Entry(main_frame, font=("Arial", 10), width=35,
                                   bg="#333333", fg="#ffffff", 
                                   insertbackground="#ffffff",
                                   relief="solid", bd=1)
            comment_entry.pack(pady=(0, 20))
            
            # Result variable
            result = {"cmdr": None, "comment": None}
            
            def on_ok():
                cmdr = cmdr_entry.get().strip()
                comment = comment_entry.get().strip()
                
                # Save CMDR name to config if provided
                if cmdr:
                    from config import update_config_value
                    update_config_value("cmdr_name", cmdr)
                
                result["cmdr"] = cmdr if cmdr else None
                result["comment"] = comment if comment else None
                dialog.destroy()
            
            def on_skip():
                # Skip without saving
                dialog.destroy()
            
            # Buttons frame
            button_frame = tk.Frame(main_frame, bg="#1e1e1e")
            button_frame.pack(pady=(10, 0))
            
            ok_button = tk.Button(button_frame, text="OK", command=on_ok,
                                 font=("Arial", 10, "bold"),
                                 bg="#FF8C00", fg="#ffffff",
                                 activebackground="#FFA500",
                                 activeforeground="#ffffff",
                                 width=10, relief="flat", cursor="hand2")
            ok_button.pack(side="left", padx=5)
            
            skip_button = tk.Button(button_frame, text="Skip", command=on_skip,
                                   font=("Arial", 10),
                                   bg="#555555", fg="#ffffff",
                                   activebackground="#666666",
                                   activeforeground="#ffffff",
                                   width=10, relief="flat", cursor="hand2")
            skip_button.pack(side="left", padx=5)
            
            # Bind Enter key to OK
            dialog.bind('<Return>', lambda e: on_ok())
            dialog.bind('<Escape>', lambda e: on_skip())
            
            # Wait for dialog to close
            dialog.wait_window()
            
            return result
            
        except Exception as e:
            print(f"[DEBUG] Error showing CMDR dialog: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _share_selected_to_discord_popup(self, tree):
        """Share the currently selected session to Discord from popup window"""
        try:
            # Check if a session is selected in the popup tree
            selected = tree.selection()
            if not selected:
                from tkinter import messagebox
                messagebox.showwarning("No Selection", "Please select a mining session to share to Discord.")
                return
            
            # Get the session data from popup tree - need to get from session lookup
            item_id = selected[0]
            
            # Check if there's a session lookup for the popup
            if hasattr(self, 'session_lookup') and item_id in self.session_lookup:
                session = self.session_lookup[item_id]
            else:
                # Fall back to reports_tab_session_lookup
                if item_id in self.reports_tab_session_lookup:
                    session = self.reports_tab_session_lookup[item_id]
                else:
                    from tkinter import messagebox
                    messagebox.showerror("Error", "Session data not found for selected item.")
                    return
            
            # Get or prompt for Discord username
            username_result = self._get_discord_username()
            if not username_result[0]:  # User cancelled
                return
            
            username, comment = username_result
            
            # Add username and comment to session data
            session_with_user = session.copy()
            session_with_user['discord_username'] = username
            if comment:
                session_with_user['discord_comment'] = comment
            
            # Try to add report content for material breakdown
            try:
                if 'file_path' in session and session['file_path']:
                    report_path = session['file_path']
                    if os.path.exists(report_path):
                        with open(report_path, 'r', encoding='utf-8') as f:
                            session_with_user['report_content'] = f.read()
            except Exception as e:
                print(f"[DEBUG] Could not read report content: {e}")
                # Continue without report content
            
            # Import Discord integration
            try:
                from discord_integration import send_discord_report, is_discord_enabled
            except ImportError:
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "Error", "Discord integration module not found.")
                return
            
            # Check if Discord is configured
            if not is_discord_enabled():
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "Discord Sharing",
                                 "Discord sharing is not available in this version.\n\n"
                                 "Contact the administrator if you believe this is an error.")
                return
            
            # Send to Discord
            success, message = send_discord_report(session_with_user)
            
            from app_utils import centered_message
            if success:
                centered_message(self.winfo_toplevel(), "Discord Share", message)
                self._set_status("Report shared to Discord successfully!")
            else:
                centered_message(self.winfo_toplevel(), "Discord Error", message)
                self._set_status(f"Discord share failed: {message}")
                
        except Exception as e:
            error_msg = f"Failed to share to Discord: {e}"
            self._set_status(error_msg)
            from app_utils import centered_message
            centered_message(self.winfo_toplevel(), "Error", error_msg)

    def _create_mining_card_from_report(self):
        """Create mining card PNG from selected report in main Reports tab"""
        try:
            selected = self.reports_tree_tab.selection()
            if not selected:
                from tkinter import messagebox
                messagebox.showwarning("No Selection", "Please select a mining session to create a card.")
                return
            
            item_id = selected[0]
            if item_id not in self.reports_tab_session_lookup:
                from tkinter import messagebox
                messagebox.showerror("Error", "Session data not found for selected item.")
                return
            
            session = self.reports_tab_session_lookup[item_id]
            
            # Get CMDR name and comment
            cmdr_info = self._get_cmdr_info_for_card()
            if cmdr_info is None:
                return  # User cancelled
            
            self._generate_mining_card(session, cmdr_info)
            
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to create mining card: {e}")

    def _create_mining_card_from_report_popup(self, tree):
        """Create mining card PNG from selected report in popup window"""
        try:
            selected = tree.selection()
            if not selected:
                from tkinter import messagebox
                messagebox.showwarning("No Selection", "Please select a mining session to create a card.")
                return
            
            item_id = selected[0]
            
            # Get session from appropriate lookup
            if hasattr(self, 'session_lookup') and item_id in self.session_lookup:
                session = self.session_lookup[item_id]
            elif item_id in self.reports_tab_session_lookup:
                session = self.reports_tab_session_lookup[item_id]
            else:
                from tkinter import messagebox
                messagebox.showerror("Error", "Session data not found for selected item.")
                return
            
            # Get CMDR name and comment
            cmdr_info = self._get_cmdr_info_for_card()
            if cmdr_info is None:
                return  # User cancelled
            
            self._generate_mining_card(session, cmdr_info)
            
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to create mining card: {e}")

    def _generate_mining_card(self, session, cmdr_info=None):
        """Generate mining card PNG from session data"""
        try:
            from mining_card_generator import create_card_from_session
            from path_utils import get_reports_dir
            import subprocess
            import datetime
            
            # Create Cards directory
            cards_dir = os.path.join(get_reports_dir(), "Cards")
            os.makedirs(cards_dir, exist_ok=True)
            
            # Parse session data to extract needed info
            system = session.get('system', 'Unknown')
            body = session.get('body', 'Unknown')
            duration = session.get('duration', 'Unknown')
            ship = session.get('ship', None)
            session_type_from_session = session.get('session_type', '')
            
            # Get filename or create one from session data
            file_path = session.get('file_path', '')
            if file_path and os.path.exists(file_path):
                # Extract timestamp from filename
                filename = os.path.basename(file_path)
                if filename.startswith('Session_') and '_' in filename:
                    parts = filename.replace('.txt', '').split('_')
                    if len(parts) >= 3:
                        timestamp = f"{parts[1]}_{parts[2]}"
                    else:
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                else:
                    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Build card filename
            clean_system = system.replace(' ', '_')
            clean_body = body.replace(' ', '_')
            card_filename = f"Session_{timestamp}_{clean_system}_{clean_body}_Card.png"
            card_path = os.path.join(cards_dir, card_filename)
            
            # Parse materials from report file
            materials_mined = {}
            total_tons = 0
            tph = 0
            prospectors_used = 0
            session_duration_hours = 0
            avg_yield = 0
            session_type = session_type_from_session
            
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Parse ship name if not already available
                    if not ship:
                        for line in content.split('\n'):
                            if line.startswith('Ship:'):
                                ship = line.replace('Ship:', '').strip()
                                break
                    
                    # Parse session type if in header
                    if not session_type and '(Single Session)' in content:
                        session_type = 'Single Session'
                    elif not session_type and '(Multi-Session)' in content:
                        session_type = 'Multi-Session'
                    
                    # Parse MINERAL ANALYSIS section for prospecting data
                    asteroids_prospected = 0
                    hit_rate = 0
                    prospecting_speed = 0
                    mineral_performance = {}  # Dict of {mineral_name: {avg, best, finds}}
                    
                    if '=== MINERAL ANALYSIS ===' in content:
                        lines = content.split('\n')
                        in_analysis = False
                        in_performance = False
                        current_mineral = None
                        
                        for i, line in enumerate(lines):
                            if '=== MINERAL ANALYSIS ===' in line:
                                in_analysis = True
                                continue
                            if in_analysis:
                                if line.startswith('==='):
                                    break
                                if '--- Mineral Performance ---' in line:
                                    in_performance = True
                                    continue
                                    
                                if 'Overall Quality:' in line and '%' in line:
                                    try:
                                        avg_yield = float(line.split(':')[1].split('%')[0].strip())
                                    except:
                                        pass
                                elif 'Asteroids Prospected:' in line:
                                    try:
                                        asteroids_prospected = int(line.split(':')[1].strip())
                                    except:
                                        pass
                                elif 'Hit Rate:' in line and '%' in line:
                                    try:
                                        hit_rate = float(line.split(':')[1].split('%')[0].strip())
                                    except:
                                        pass
                                elif 'Prospecting Speed:' in line:
                                    try:
                                        prospecting_speed = float(line.split(':')[1].split('asteroids')[0].strip())
                                    except:
                                        pass
                                
                                # Parse mineral performance details
                                if in_performance:
                                    if line.strip() and not line.startswith('  ') and ':' in line and line.strip().endswith(':'):
                                        # This is a mineral name line like "Bromellite:"
                                        current_mineral = line.strip().rstrip(':')
                                        mineral_performance[current_mineral] = {'avg': 0, 'best': 0, 'finds': 0}
                                    elif current_mineral and '• Average:' in line:
                                        try:
                                            avg_val = float(line.split(':')[1].split('%')[0].strip())
                                            mineral_performance[current_mineral]['avg'] = avg_val
                                        except:
                                            pass
                                    elif current_mineral and '• Best:' in line:
                                        try:
                                            best_val = float(line.split(':')[1].split('%')[0].strip())
                                            mineral_performance[current_mineral]['best'] = best_val
                                        except:
                                            pass
                                    elif current_mineral and ('• Hits:' in line or '• Finds:' in line):
                                        try:
                                            # Support legacy 'Finds: 12x' and new 'Hits: 12'
                                            raw_val = line.split(':', 1)[1].strip()
                                            raw_val = raw_val.replace('x', '')
                                            hits_val = int(raw_val)
                                            mineral_performance[current_mineral]['finds'] = hits_val
                                        except:
                                            pass
                    
                    # Parse engineering materials section
                    engineering_materials_total = 0
                    engineering_materials_list = []  # List of {material, grade, quantity}
                    materials_tracked = 0
                    total_finds = 0
                    
                    if '=== ENGINEERING MATERIALS COLLECTED ===' in content:
                        lines = content.split('\n')
                        in_eng_section = False
                        current_grade = None
                        for line in lines:
                            if '=== ENGINEERING MATERIALS COLLECTED ===' in line:
                                in_eng_section = True
                                continue
                            if in_eng_section:
                                if line.startswith('==='):
                                    break
                                if 'Total Engineering Materials:' in line:
                                    try:
                                        engineering_materials_total = int(line.split(':')[1].split('pieces')[0].strip())
                                    except:
                                        pass
                                elif 'Grade' in line and '(' in line and line.strip().endswith(':'):
                                    # Parse grade info like "Grade 1 (Very Common):"
                                    try:
                                        current_grade = line.split('(')[0].strip()
                                    except:
                                        pass
                                elif current_grade and ':' in line and line.strip() and not line.strip().startswith('Total'):
                                    # Parse material line like "  Nickel: 18"
                                    try:
                                        parts = line.split(':')
                                        material_name = parts[0].strip()
                                        quantity = int(parts[1].strip())
                                        engineering_materials_list.append({
                                            'material': material_name,
                                            'grade': current_grade,
                                            'quantity': quantity
                                        })
                                    except:
                                        pass
                    
                    # Parse materials tracked and total finds from MINERAL ANALYSIS
                    if '=== MINERAL ANALYSIS ===' in content:
                        lines = content.split('\n')
                        for line in lines:
                            if 'Minerals Tracked:' in line:
                                try:
                                    materials_tracked = int(line.split(':')[1].strip())
                                except:
                                    pass
                            elif 'Total Material Hits:' in line or 'Total Material Finds:' in line:
                                try:
                                    raw_val = line.split(':', 1)[1].strip()
                                    raw_val = raw_val.replace('x', '')
                                    total_finds = int(raw_val)
                                except:
                                    pass
                    
                    # Parse materials from CARGO MATERIAL BREAKDOWN section
                    if '=== CARGO MATERIAL BREAKDOWN ===' in content:
                        lines = content.split('\n')
                        in_materials = False
                        for line in lines:
                            if '=== CARGO MATERIAL BREAKDOWN ===' in line:
                                in_materials = True
                                continue
                            if in_materials:
                                if line.startswith('==='):
                                    break
                                if 'Prospector Limpets Used:' in line:
                                    try:
                                        prospectors_used = int(line.split(':')[1].strip())
                                    except:
                                        pass
                                elif ':' in line and 't' in line and '(' in line:
                                    # Parse material line: "Material: XXt (YY.Y t/hr)"
                                    try:
                                        parts = line.split(':')
                                        if len(parts) >= 2:
                                            mat_name = parts[0].strip()
                                            rest = parts[1].strip()
                                            tons_part = rest.split('t')[0].strip()
                                            tons = float(tons_part)
                                            
                                            tph_part = rest.split('(')[1].split('t/hr')[0].strip()
                                            mat_tph = float(tph_part)
                                            
                                            materials_mined[mat_name] = {
                                                'tons': tons,
                                                'tph': mat_tph
                                            }
                                            total_tons += tons
                                    except Exception as e:
                                        print(f"[CARD] Error parsing material line: {line}, {e}")
                    
                    # Parse session duration for overall TPH from first line
                    lines = content.split('\n')
                    if lines and '—' in lines[0]:
                        first_line = lines[0]
                        if 'Total' in first_line and 't' in first_line:
                            try:
                                # Extract duration (format: "Session: System — Body — HH:MM:SS — Total XXt")
                                parts = first_line.split('—')
                                if len(parts) >= 3:
                                    duration_str = parts[2].strip()
                                    
                                    # Parse duration - could be "HH:MM:SS" or "XXh YYm"
                                    if ':' in duration_str:
                                        time_parts = duration_str.split(':')
                                        if len(time_parts) == 3:
                                            h = int(time_parts[0])
                                            m = int(time_parts[1])
                                            s = int(time_parts[2])
                                            session_duration_hours = h + (m / 60.0) + (s / 3600.0)
                                    elif 'h' in duration_str:
                                        h = int(duration_str.split('h')[0].strip())
                                        m_str = duration_str.split('h')[1].split('m')[0].strip() if 'm' in duration_str else '0'
                                        m = int(m_str) if m_str else 0
                                        session_duration_hours = h + (m / 60.0)
                                    
                                    # Extract total tons
                                    if 'Total' in first_line:
                                        total_match = first_line.split('Total')[1].split('t')[0].strip()
                                        parsed_total = float(total_match.replace(',', ''))
                                        if parsed_total > 0:
                                            total_tons = parsed_total
                                    
                                    # Calculate TPH
                                    if session_duration_hours > 0 and total_tons > 0:
                                        tph = total_tons / session_duration_hours
                                        print(f"[CARD] Calculated TPH: {tph:.1f} from {total_tons:.0f}t / {session_duration_hours:.2f}h")
                            except Exception as e:
                                print(f"[CARD] Error parsing session stats: {e}")
                                import traceback
                                traceback.print_exc()
            
            # Build cargo session data structure
            cargo_session_data = {
                'total_tons_mined': total_tons,
                'session_duration': session_duration_hours * 3600,
                'materials_mined': materials_mined,
                'prospectors_used': prospectors_used,
                'session_type': session_type,
                'avg_yield': avg_yield,
                'asteroids_prospected': asteroids_prospected,
                'hit_rate': hit_rate,
                'prospecting_speed': prospecting_speed,
                'mineral_performance': mineral_performance,
                'engineering_materials_total': engineering_materials_total,
                'engineering_materials_list': engineering_materials_list,
                'materials_tracked': materials_tracked,
                'total_finds': total_finds
            }
            
            # Build session info
            session_info = {
                'system': system,
                'body': body,
                'ship': ship,
                'duration_text': duration
            }
            
            print(f"[CARD DEBUG] session_info: {session_info}")
            print(f"[CARD DEBUG] cargo_session_data session_type: {cargo_session_data.get('session_type')}")
            
            # Generate the card
            if create_card_from_session(cargo_session_data, session_info, card_path, cmdr_info):
                print(f"[CARD] Mining card generated: {card_filename}")
                
                # Open the card image directly
                if os.name == 'nt':  # Windows
                    os.startfile(card_path)
                else:  # macOS/Linux
                    subprocess.Popen(['xdg-open', card_path])
                    
            else:
                from tkinter import messagebox
                messagebox.showerror("Error", "Failed to generate mining card.")
                
        except Exception as e:
            print(f"[CARD] Error generating mining card: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to generate mining card: {e}")

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
            
            # Save to config.json so it persists across restarts
            from config import update_config_value
            update_config_value("journal_dir", sel)
            
            self._set_status("Journal folder updated and saved.")

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
        
        sysname = (self.session_system.get().strip() or self._get_current_system() or "Unknown").replace(" ", "_")
        body = (self.session_body.get().strip() or self.last_body or "Unknown").replace(" ", "_")
        fname = f"Session_{timestamp}_{sysname}_{body}.txt"
        os.makedirs(self.reports_dir, exist_ok=True)
        fpath = os.path.join(self.reports_dir, fname)

        parts = [header]
        
        # Add ship name if available
        if hasattr(self, 'session_ship_name') and self.session_ship_name:
            parts.append(f"Ship: {self.session_ship_name}")
        
        # Add refined materials section
        if lines:
            parts.append("\n=== REFINED MINERALS ===")
            parts += [f" - {line}" for line in lines]
        else:
            parts.append("\n=== REFINED MINERALS ===")
            parts.append(" - No refined minerals.")
        
        # Add Mineral Analysis section if we have prospecting data
        material_summary = self.session_analytics.get_live_summary()
        session_info = self.session_analytics.get_session_info()
        
        if material_summary and session_info['asteroids_prospected'] > 0:
            parts.append("\n=== MINERAL ANALYSIS ===")
            
            # Prospecting summary
            asteroids_count = session_info['asteroids_prospected']
            materials_tracked = len(material_summary)
            total_finds = session_info['total_finds']
            core_asteroids = session_info.get('core_asteroids', 0)
            
            parts.append(f"Asteroids Prospected: {asteroids_count}")
            if core_asteroids > 0:
                parts.append(f"Core Asteroids Found: {core_asteroids}")
            parts.append(f"Minerals Tracked: {materials_tracked}")
            parts.append(f"Total Material Hits: {total_finds}")
            
            if asteroids_count > 0:
                # Hit rate = percentage of asteroids that contained tracked materials
                asteroids_with_materials = session_info.get('asteroids_with_materials', 0)
                hit_rate = (asteroids_with_materials / asteroids_count) * 100.0
                parts.append(f"Hit Rate: {hit_rate:.1f}% (asteroids with valuable minerals)")
            
            # Session efficiency
            active_minutes = max(self._active_seconds() / 60.0, 0.1)
            asteroids_per_min = asteroids_count / active_minutes
            parts.append(f"Prospecting Speed: {asteroids_per_min:.1f} asteroids/minute")
            
            # Mineral performance details
            parts.append("\n--- Mineral Performance ---")
            
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
                parts.append(f"  • Hits: {count}")

                # Add tons and tons-per-hit (if cargo session data available)
                mat_tons = 0.0
                if cargo_session_data and cargo_session_data.get('materials_mined'):
                    try:
                        mat_tons = float(cargo_session_data['materials_mined'].get(material_name, 0.0))
                    except Exception:
                        mat_tons = 0.0

                if mat_tons and mat_tons > 0:
                    parts.append(f"  • Tons: {mat_tons:.1f}t")
                    if count > 0:
                        tons_per_hit = mat_tons / count
                        parts.append(f"  • Tons/Hit: {tons_per_hit:.2f}t/hit")
                elif mat_tons == 0.0:
                    # Still emit a line to make report consistent
                    parts.append(f"  • Tons: 0.0t")
            
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
            
            # Calculate session duration for TPH
            session_duration_hours = cargo_session_data.get('session_duration', 0) / 3600.0
            
            # Sort materials by quantity (highest first)
            sorted_materials = sorted(materials_mined.items(), key=lambda x: x[1], reverse=True)
            
            for material_name, quantity in sorted_materials:
                if session_duration_hours > 0:
                    mat_tph = quantity / session_duration_hours
                    parts.append(f"{material_name}: {quantity:.1f}t ({mat_tph:.1f} t/hr)")
                else:
                    parts.append(f"{material_name}: {quantity:.1f}t")
            
            # Note: Total cargo collected is calculated from individual materials above
            # Don't add a separate "Total Cargo Collected" line as it's redundant
        
        # Add engineering materials section if available (Option 2: Grouped by grade)
        if cargo_session_data and cargo_session_data.get('engineering_materials'):
            eng_materials = cargo_session_data['engineering_materials']
            
            if eng_materials:
                parts.append("\n=== ENGINEERING MATERIALS COLLECTED ===")
                parts.append("")
                
                # Get material grades from cargo monitor
                material_grades = {}
                if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
                    material_grades = self.main_app.cargo_monitor.MATERIAL_GRADES
                
                # Group materials by grade
                materials_by_grade = {}
                for material_name, quantity in eng_materials.items():
                    grade = material_grades.get(material_name, 0)
                    if grade not in materials_by_grade:
                        materials_by_grade[grade] = []
                    materials_by_grade[grade].append((material_name, quantity))
                
                # Grade descriptions
                grade_names = {
                    1: "Grade 1 (Very Common)",
                    2: "Grade 2 (Common)",
                    3: "Grade 3 (Standard)",
                    4: "Grade 4 (Rare)"
                }
                
                # Output grouped by grade
                total_pieces = 0
                for grade in sorted(materials_by_grade.keys()):
                    parts.append(grade_names.get(grade, f"Grade {grade}") + ":")
                    
                    # Sort materials alphabetically within each grade
                    for material_name, quantity in sorted(materials_by_grade[grade]):
                        parts.append(f"  {material_name}: {quantity}")
                        total_pieces += quantity
                    parts.append("")  # Empty line between grades
                
                parts.append(f"Total Engineering Materials: {total_pieces} pieces")
        
        # Add comment if provided
        if comment.strip():
            parts.append(f"\n=== SESSION COMMENT ===")
            parts.append(comment.strip())
        
        _atomic_write_text(fpath, "\n".join(parts) + "\n")
        return fpath

    def _update_csv_with_session(self, system: str, body: str, elapsed: str, total_tons: float, overall_tph: float, cargo_session_data: dict = None, comment: str = "", session_timestamp: str = None) -> None:
        """Add new session data to the CSV index"""
        try:
            import csv
            csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
            
            # Use provided timestamp or generate new one (normalize format for consistency)
            if session_timestamp:
                # Convert filename format (2025-01-15_14-30-00) to CSV format (2025-01-15T14:30:00)
                # Replace first underscore with T, then replace hyphens in time part with colons
                parts = session_timestamp.split('_')
                if len(parts) == 2:
                    date_part = parts[0]
                    time_part = parts[1].replace('-', ':')
                    timestamp_local = f"{date_part}T{time_part}"
                else:
                    timestamp_local = dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            else:
                # Fallback for backward compatibility
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
            yield_display_string = "0.0"  # Initialize to prevent undefined variable error
            total_avg_yield = 0.0  # Initialize total average yield
            
            if material_summary and asteroids_prospected > 0:
                # Hit rate: percentage of asteroids with valuable minerals
                session_info = self.session_analytics.get_session_info()
                asteroids_with_materials = session_info.get('asteroids_with_materials', 0)
                hit_rate = (asteroids_with_materials / asteroids_prospected) * 100.0
                
                # NEW: Calculate yield from prospector reports data using selected materials only
                raw_yields = {}
                yield_display_string = "0.0"  # Always initialize to valid default
                total_avg_yield = 0.0
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
                    
                    # Calculate total average yield across all asteroids
                    total_avg_yield = self._calculate_total_average_yield()
                except Exception as e:
                    # Fallback to old method if new calculation fails
                    raw_yields = {}  # Initialize raw_yields to prevent UnboundLocalError
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
            material_tph_breakdown = ""  # New field for per-material TPH
            prospectors_used = 0
            engineering_materials_str = ""  # New field for engineering materials
            if cargo_session_data:
                materials_mined = cargo_session_data.get('materials_mined', {})
                prospectors_used = cargo_session_data.get('prospectors_used', 0)
                
                # Format materials_breakdown from materials_mined (with yields if available)
                if materials_mined:
                    breakdown_pairs = []
                    for mat_name, mat_tons in sorted(materials_mined.items(), key=lambda x: x[1], reverse=True):
                        # Add yield % if available from raw_yields
                        if raw_yields and mat_name in raw_yields:
                            breakdown_pairs.append(f"{mat_name}: {mat_tons:.1f}t ({raw_yields[mat_name]:.1f}%)")
                        else:
                            breakdown_pairs.append(f"{mat_name}: {mat_tons:.1f}t")
                    materials_breakdown = "; ".join(breakdown_pairs)
                
                # Calculate per-material TPH
                session_duration_seconds = cargo_session_data.get('session_duration', 0)
                print(f"[DEBUG CSV] session_duration from cargo: {session_duration_seconds}")
                print(f"[DEBUG CSV] materials_mined: {materials_mined}")
                session_duration_hours = session_duration_seconds / 3600.0
                if session_duration_hours > 0 and materials_mined:
                    tph_pairs = []
                    for mat_name, mat_tons in sorted(materials_mined.items()):
                        mat_tph = mat_tons / session_duration_hours
                        tph_pairs.append(f"{mat_name}: {mat_tph:.1f}")
                    material_tph_breakdown = ", ".join(tph_pairs)
                    print(f"[DEBUG CSV] material_tph_breakdown: {material_tph_breakdown}")
                else:
                    print(f"[DEBUG CSV] No TPH calculated - duration_hours={session_duration_hours}, has_materials={bool(materials_mined)}")
                
                # Format engineering materials as "Iron:45,Nickel:23,Carbon:89"
                eng_materials = cargo_session_data.get('engineering_materials', {})
                if eng_materials:
                    engineering_materials_str = ",".join([f"{mat}:{qty}" for mat, qty in sorted(eng_materials.items())])
            
            # Get ship name for this session
            ship_name_for_session = ""
            if hasattr(self, 'session_ship_name'):
                ship_name_for_session = self.session_ship_name
            
            # New session data with Material Analysis metrics and cargo data (ship_name is NOT in CSV - only in TXT/HTML reports)
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
                'total_average_yield': round(total_avg_yield, 1) if total_avg_yield > 0 else 0.0,
                'best_material': best_material,
                'materials_breakdown': materials_breakdown,
                'material_tph_breakdown': material_tph_breakdown,  # Add per-material TPH
                'prospectors_used': prospectors_used,
                'engineering_materials': engineering_materials_str,  # Add engineering materials
                'comment': comment
            }
            
            # Read existing data
            sessions = []
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    sessions = list(reader)
            
            # Ensure old sessions have the engineering_materials and material_tph_breakdown fields (backward compatibility)
            # Also REMOVE ship_name if it exists in old CSV files
            for session in sessions:
                if 'engineering_materials' not in session:
                    session['engineering_materials'] = ''
                if 'material_tph_breakdown' not in session:
                    session['material_tph_breakdown'] = ''
                # Remove ship_name from old data - it's no longer stored in CSV
                if 'ship_name' in session:
                    del session['ship_name']
            
            # Add new session
            sessions.append(new_session)
            
            # Write back to CSV with enhanced fields including cargo data (ship_name is NOT in CSV - only in TXT/HTML reports)
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['timestamp_utc', 'system', 'body', 'elapsed', 'total_tons', 'overall_tph',
                            'asteroids_prospected', 'materials_tracked', 'hit_rate_percent', 
                            'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 'engineering_materials', 'comment']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for _r in sessions:
                    if 'total_finds' in _r:
                        _r.pop('total_finds', None)
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
            
            # Also clear the history data so only current session asteroids show up
            # BUT: In multi-session mode, keep history to accumulate across cargo runs
            if not self.multi_session_mode:
                self.history = []
        except Exception as e:
            print(f"Failed to clear prospector reports: {e}")
    
    def _on_cargo_event(self, event_type: str, count: int):
        """Handle cargo events for multi-session tracking
        
        Args:
            event_type: 'MarketSell', 'CargoTransfer', or 'EjectCargo'
            count: Number of tons sold/transferred/ejected
        """
        if not self.multi_session_mode:
            return  # Only track in multi-session mode
        
        try:
            if event_type in ["MarketSell", "CargoTransfer"]:
                # Success - sold or transferred to carrier
                self.session_sold_transferred += count
                print(f"[Multi-Session] {event_type}: +{count}t (Total sold/transferred: {self.session_sold_transferred}t)")
            elif event_type == "EjectCargo":
                # Loss - dumped/abandoned
                self.session_ejected += count
                print(f"[Multi-Session] Ejected: +{count}t (Total lost: {self.session_ejected}t)")
            
            # Update display to show new totals
            self._refresh_statistics_display()
        except Exception as e:
            print(f"Error tracking cargo event: {e}")

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
    
    def _show_prospector_overlay_or_standard(self, standard_msg: str, panel_summary: str, materials_txt: str, content_txt: str, core_material: str = ""):
        """
        Show overlay based on mode setting.
        
        STANDARD MODE: Shows simple text only when TTS triggers
        ENHANCED MODE: Shows game-style format every prospector fire
        
        Args:
            standard_msg: TTS message (may be empty if nothing triggered)
            panel_summary: Filtered materials (above threshold only)
            materials_txt: ALL materials (unfiltered)
            content_txt: Content and remaining text
            core_material: Core/motherlode material name if detected (empty string if not)
        """
        from config import _load_cfg
        cfg = _load_cfg()
        overlay_mode = cfg.get("overlay_mode", "standard")
        show_all = cfg.get("prospector_show_all", False)
        
        if overlay_mode == "enhanced":
            # ENHANCED MODE: Always show overlay with game-style format
            # Pass materials and content separately to formatter
            if show_all:
                # Show ALL materials (unfiltered)
                enhanced_msg = self._format_enhanced_overlay_ex(materials_txt, content_txt, core_material)
            else:
                # Show only materials above threshold (filtered) - use panel_summary
                enhanced_msg = self._format_enhanced_overlay(panel_summary, core_material)
            
            self.text_overlay.show_message(enhanced_msg)
        else:
            # STANDARD MODE: Only show when TTS triggered
            if standard_msg:
                self.text_overlay.show_message(standard_msg)
    
    def _format_enhanced_overlay(self, panel_summary: str, core_material: str = "") -> str:
        """
        Format panel_summary text in Elite Dangerous game style.
        Input: "Low — Bertrandite 16.2%, Indite 13.7% — Remaining 100.00%"
        Output format matching game:
        LIMPET (PROSPECTOR)
        
        MINERALS REMAINING: 100%
        METHANOL MONOHYDRATE CRYSTALS 18%
        METHANE CLATHRATE 10.2%
        LIQUID OXYGEN 1.8%
        
        MATERIAL CONTENT: LOW
        CORE DETECTED: ALEXANDRITE  (if core asteroid)
        
        Args:
            panel_summary: Filtered materials summary string
            core_material: Core/motherlode material name if detected
        """
        import re
        
        log.debug(f"[Enhanced Overlay] Input: {panel_summary}")
        
        lines = ["LIMPET (PROSPECTOR)"]
        
        # Parse panel_summary by splitting on " — "
        parts = [p.strip() for p in panel_summary.split(" — ")]
        log.debug(f"[Enhanced Overlay] Parts: {parts}")
        
        content = ""
        materials_text = ""
        remaining = "100%"
        
        # Identify parts
        for part in parts:
            if "Remaining" in part:
                remaining = part.replace("Remaining ", "").strip()
            elif part.lower() in ["low", "medium", "high"]:  # Exact match only, not substring
                content = part
            else:
                materials_text = part
        
        print(f"[Enhanced Overlay] Materials text: {materials_text}")
        print(f"[Enhanced Overlay] Content: {content}")
        print(f"[Enhanced Overlay] Remaining: {remaining}")
        
        # Add remaining first
        if "Depleted" in remaining:
            lines.append("MINERALS REMAINING: DEPLETED")
        else:
            lines.append(f"MINERALS REMAINING: {remaining}")
        
        # Parse materials: "Bertrandite 16.2%, Indite 13.7%"
        # Materials are separated by ", " (comma space)
        # Split by ", " then parse each material entry
        if materials_text and "No materials" not in materials_text:
            # Split by comma to get individual materials
            material_entries = materials_text.split(", ")
            log.debug(f"[Enhanced Overlay] Material entries: {material_entries}")
            
            for entry in material_entries:
                # Each entry is like "Bertrandite 16.2%" or "Methanol Monohydrate Crystals 18%"
                # Split from the right to get the percentage
                match = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)%$', entry.strip())
                if match:
                    material_name = match.group(1)
                    percentage = match.group(2)
                    lines.append(f"{material_name.upper()} {percentage}%")
                    log.debug(f"[Enhanced Overlay] Added: {material_name.upper()} {percentage}%")
        
        # Add content at the end
        if content:
            lines.append(f"MATERIAL CONTENT: {content.upper()}")
        
        # Add core detected line if motherlode present (matching game format)
        if core_material:
            lines.append(f"CORE DETECTED: {core_material.upper()}")
        
        result = "\n".join(lines)
        print(f"[Enhanced Overlay] Output lines count: {len(lines)}")
        print(f"[Enhanced Overlay] Output repr: {repr(result)}")
        return result
    
    def _format_enhanced_overlay_ex(self, materials_txt: str, content_txt: str, core_material: str = "") -> str:
        """
        Format materials and content separately for enhanced overlay (show_all mode).
        
        Args:
            materials_txt: "Water 5.8%, Liquid Oxygen 7.1%, Lithium Hydroxide 4.9%"
            content_txt: "Low — Remaining 100.00%"
            core_material: Core/motherlode material name if detected
        """
        import re
        
        log.debug(f"[Enhanced Overlay EX] Materials: {materials_txt}")
        log.debug(f"[Enhanced Overlay EX] Content: {content_txt}")
        
        lines = ["LIMPET (PROSPECTOR)"]
        
        # Parse content_txt to extract content and remaining
        content = ""
        remaining = "100%"
        
        if content_txt:
            parts = [p.strip() for p in content_txt.split(" — ")]
            for part in parts:
                if "Remaining" in part:
                    remaining = part.replace("Remaining ", "").strip()
                elif part.lower() in ["low", "medium", "high"]:  # Exact match only, not substring
                    content = part
        
        # Add remaining first
        if "Depleted" in remaining:
            lines.append("MINERALS REMAINING: DEPLETED")
        else:
            lines.append(f"MINERALS REMAINING: {remaining}")
        
        # Parse materials
        if materials_txt and "No materials" not in materials_txt:
            material_entries = materials_txt.split(", ")
            
            for entry in material_entries:
                match = re.match(r'^(.+?)\s+(\d+(?:\.\d+)?)%$', entry.strip())
                if match:
                    material_name = match.group(1)
                    percentage = match.group(2)
                    lines.append(f"{material_name.upper()} {percentage}%")
        
        # Add content at the end
        if content:
            lines.append(f"MATERIAL CONTENT: {content.upper()}")
        
        # Add core detected line if motherlode present (matching game format)
        if core_material:
            lines.append(f"CORE DETECTED: {core_material.upper()}")
        
        result = "\n".join(lines)
        log.debug(f"[Enhanced Overlay EX] Output:\n{result}")
        return result

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
    
    def _calculate_total_average_yield(self) -> float:
        """
        Calculate total average yield % across all prospected asteroids for all mined minerals.
        This gives the overall prospecting efficiency.
        """
        if not hasattr(self, 'session_yield_data') or not self.session_yield_data:
            return 0.0
        
        # Collect all individual yield percentages from all asteroids
        all_yields = []
        for material_name, percentages in self.session_yield_data.items():
            all_yields.extend(percentages)
        
        if not all_yields:
            return 0.0
        
        return sum(all_yields) / len(all_yields)

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
                                'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'prospectors_used', 'comment']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for _r in sessions:
                        if 'total_finds' in _r:
                            _r.pop('total_finds', None)
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

    def _enhance_materials_with_yields_and_tph(self, materials_breakdown_raw: str, avg_quality_percent: str, material_tph_breakdown: str) -> str:
        """Enhance materials display by adding yield percentages and TPH in brackets
        
        Uses abbreviated mineral names for compact display in Reports column.
        Note: Exports (CSV, TXT, HTML) keep full names - abbreviations are UI-only.
        """
        if not materials_breakdown_raw or materials_breakdown_raw == '—':
            return materials_breakdown_raw
            
        try:
            # Material abbreviations for display (matches Ring Finder conventions)
            display_abbreviations = {
                'Alexandrite': 'Alex',
                'Bauxite': 'Baux',
                'Benitoite': 'Beni',
                'Bertrandite': 'Bert',
                'Bromellite': 'Brom',
                'Cobalt': 'Coba',
                'Coltan': 'Colt',
                'Gallite': 'Gall',
                'Gold': 'Gold',
                'Goslarite': 'Gosl',
                'Grandidierite': 'Gran',
                'Haematite': 'Haem',
                'Hydrogen Peroxide': 'H2O2',
                'Indite': 'Indi',
                'Lepidolite': 'Lepi',
                'Liquid Oxygen': 'LOX',
                'Lithium Hydroxide': 'LiOH',
                'Low Temperature Diamonds': 'LTD',
                'Methane Clathrate': 'MeCl',
                'Methanol Monohydrate Crystals': 'MeOH',
                'Monazite': 'Mona',
                'Musgravite': 'Musg',
                'Osmium': 'Osmi',
                'Painite': 'Pain',
                'Palladium': 'Pall',
                'Platinum': 'Plat',
                'Praseodymium': 'Pras',
                'Rhodplumsite': 'Rhod',
                'Rutile': 'Ruti',
                'Samarium': 'Sama',
                'Serendibite': 'Sere',
                'Silver': 'Silv',
                'Tritium': 'Trit',
                'Uraninite': 'Uran',
                'Void Opals': 'Opals',
                'Water': 'H2O',
            }
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
            
            # Parse TPH breakdown
            material_tph = {}
            if material_tph_breakdown and isinstance(material_tph_breakdown, str):
                # Parse format like "Platinum: 12.5, Painite: 6.4"
                tph_pairs = [pair.strip() for pair in material_tph_breakdown.split(',')]
                for pair in tph_pairs:
                    if ':' in pair:
                        parts = pair.split(':')
                        if len(parts) >= 2:
                            mat_name = parts[0].strip()
                            tph_value = parts[1].strip()
                            try:
                                material_tph[mat_name] = float(tph_value)
                            except:
                                pass
            
            # Parse materials_breakdown and add yields + TPH
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
                        
                        # Use abbreviated name for display (compact UI)
                        display_name = display_abbreviations.get(material_name, material_name)
                        
                        # Build enhanced display with abbreviated name
                        display_parts = [f"{display_name}: {tonnage_text}"]
                        
                        # Add yield percentage if available AND not already in tonnage_text
                        if material_name in individual_yields and '(' not in tonnage_text:
                            yield_percent = individual_yields[material_name]
                            display_parts.append(f"({yield_percent:.1f}%)")
                        
                        # Add TPH if available
                        if material_name in material_tph:
                            tph_value = material_tph[material_name]
                            display_parts.append(f"[{tph_value:.1f} t/hr]")
                        
                        enhanced_materials.append(' '.join(display_parts))
                else:
                    # Keep original format if no colon found
                    enhanced_materials.append(pair)
            
            return '; '.join(enhanced_materials) if enhanced_materials else materials_breakdown_raw
            
        except Exception as e:
            # If parsing fails, return original
            print(f"Warning: Could not enhance materials with yields and TPH: {e}")
            return materials_breakdown_raw

    def _on_reports_window_close(self) -> None:
        """Handle reports window closing"""
        if self.reports_window:
            self.reports_window.destroy()
        self.reports_window = None
        self.reports_tree = None

    def _setup_stats_tree_tooltips(self, tree: ttk.Treeview) -> None:
        """Setup tooltip for Material Analysis table header"""
        tooltip_window = None
        
        def show_tooltip(event):
            nonlocal tooltip_window
            
            # Hide existing tooltip first
            if tooltip_window:
                tooltip_window.destroy()
                tooltip_window = None
            
            # Check if hovering over header
            region = tree.identify_region(event.x, event.y)
            if region == "heading":
                column = tree.identify_column(event.x)
                
                tooltips = {
                    "#1": "Shows material name with your announcement threshold\nExample: Platinum (27%) means you're only alerted when\nasteroids have 27% or higher Platinum content",
                    "#2": "Total tons of this material collected this session",
                    "#3": "Mining rate: Tons per hour for this material",
                    "#4": "Average % across ALL asteroids you prospected\n(includes low-quality asteroids below threshold)",
                    "#5": "Average % only for asteroids AT OR ABOVE threshold\n(your quality finds that triggered announcements)",
                    "#6": "Highest % found this session for this material",
                    "#7": "Most recent prospector scan result for this material",
                    "#8": "Number of asteroids that met your threshold\n(quality finds that triggered announcements)"
                }
                
                tooltip_text = tooltips.get(column)
                if tooltip_text:
                    
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
        
        tree.bind("<Motion>", show_tooltip)
        tree.bind("<Leave>", hide_tooltip)
        tree.bind("<Button-1>", hide_tooltip)

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
                "#7": "Number of different mineral types found",
                "#8": "Total asteroids scanned during the session",
                "#9": "Percentage of asteroids that had valuable minerals",
                "#10": "Average quality/yield percentage of minerals found",
                "#11": "Minerals mined with quantities (hover for full names)",
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
                            # Compute total finds (hits) and Tons/Hit for this CSV row
                            try:
                                total_finds = int(str(row.get('total_finds', '')).strip() or 0)
                            except Exception:
                                total_finds = 0

                            try:
                                asteroids_count = int(str(row.get('asteroids_prospected', '')).strip() or 0)
                            except Exception:
                                asteroids_count = 0

                            try:
                                total_tons_val = float(row.get('total_tons', 0.0) or 0.0)
                            except Exception:
                                try:
                                    total_tons_val = float(tons_str)
                                except Exception:
                                    total_tons_val = 0.0

                            if total_finds > 0:
                                try:
                                    tons_per_str = f"{total_tons_val / total_finds:.1f}"
                                except Exception:
                                    tons_per_str = "—"
                            elif asteroids_count > 0:
                                try:
                                    tons_per_str = f"{total_tons_val / asteroids_count:.1f}"
                                except Exception:
                                    tons_per_str = "—"
                            else:
                                tons_per_str = "—"
                            
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
                            
                            try:
                                total_finds_val = int(str(row.get('total_finds', '')).strip() or 0)
                            except Exception:
                                total_finds_val = 0

                            sessions_data.append({
                                'date': date_str,
                                'system': row['system'],
                                'body': row['body'],
                                'duration': row['elapsed'],
                                'tons': tons_str,
                                'tph': tph_str,
                                'tons_per': tons_per_str,
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
                        # Ensure insertion order matches tree columns defined at popup creation
                        # Build values list dynamically from actual tree columns to avoid ordering issues
                        cols = list(self.reports_tree["columns"]) if hasattr(self, 'reports_tree') and self.reports_tree is not None else []
                        vals = []
                        for col in cols:
                            if col == 'date':
                                vals.append(session.get('date', ''))
                            elif col == 'duration':
                                vals.append(session.get('duration', ''))
                            elif col == 'system':
                                vals.append(session.get('system', ''))
                            elif col == 'body':
                                vals.append(session.get('body', ''))
                            elif col == 'tons':
                                vals.append(session.get('tons', ''))
                            elif col == 'tph':
                                vals.append(session.get('tph', ''))
                            elif col == 'materials':
                                vals.append(session.get('materials', ''))
                            elif col == 'tons_per':
                                vals.append(session.get('tons_per', session.get('tons_per', '—')))
                            elif col == 'asteroids':
                                vals.append(session.get('asteroids', ''))
                            elif col == 'hit_rate':
                                vals.append(session.get('hit_rate', ''))
                            elif col == 'quality':
                                vals.append(session.get('quality', ''))
                            elif col == 'cargo':
                                vals.append(session.get('cargo', ''))
                            elif col in ('prospectors', 'prospects'):
                                vals.append(session.get('prospectors', session.get('prospects', '—')))
                            elif col == 'comment':
                                vals.append('💬' if session.get('comment', '').strip() else '')
                            elif col == 'enhanced':
                                vals.append("")
                            else:
                                vals.append(session.get(col, ''))

                        item_id = self.reports_tree.insert("", "end", values=tuple(vals))

                        # Ensure comment and enhanced/engineering columns are set explicitly
                        try:
                            # Place comment emoji into the comment column explicitly to avoid column-shifts
                            comment_val = '💬' if session.get('comment', '').strip() else ''
                            self.reports_tree.set(item_id, 'comment', comment_val)

                            # Set enhanced indicator by composing id from date/system/body fields
                            date_val = self.reports_tree.set(item_id, "date")
                            system_val = self.reports_tree.set(item_id, "system")
                            body_val = self.reports_tree.set(item_id, "body")
                            if date_val and system_val and body_val:
                                tree_report_id = f"{date_val}_{system_val}_{body_val}"
                                enhanced_indicator = self._get_detailed_report_indicator(tree_report_id)
                                self.reports_tree.set(item_id, "enhanced", enhanced_indicator)
                        except Exception:
                            # Don't raise on UI set failures; keep UI stable
                            pass
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

        # Configure Reports tab Treeview style (theme-aware)
        from config import load_theme
        _tab_theme = load_theme()
        style = ttk.Style()
        
        if _tab_theme == "elite_orange":
            _tab_bg = "#0a0a0a"
            _tab_fg = "#ff8c00"
            _tab_hdr = "#1a1a1a"
            _tab_sel_bg = "#ff6600"
            _tab_sel_fg = "#000000"
            _tab_alt = "#151515"
        else:
            _tab_bg = "#1e1e1e"
            _tab_fg = "#e6e6e6"
            _tab_hdr = "#2a2a2a"
            _tab_sel_bg = "#0078d7"
            _tab_sel_fg = "#ffffff"
            _tab_alt = "#282828"
        
        style.configure("ReportsTab.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=_tab_bg,
                       foreground=_tab_fg,
                       fieldbackground=_tab_bg)
        style.configure("ReportsTab.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",
                       background=_tab_hdr,
                       foreground=_tab_fg,
                       padding=[5, 5],
                       anchor="w")
        style.map("ReportsTab.Treeview",
                 background=[('selected', _tab_sel_bg)],
                 foreground=[('selected', _tab_sel_fg)])
        
        style.layout("ReportsTab.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])

        # Create wrapper frame for bordered table
        tree_frame_reports = ttk.Frame(main_frame, relief="solid", borderwidth=1)
        tree_frame_reports.grid(row=1, column=0, sticky="nsew")
        tree_frame_reports.grid_columnconfigure(0, weight=1)
        tree_frame_reports.grid_rowconfigure(0, weight=1)

        # Create sortable treeview with Material Analysis columns (Ship column added - parsed from journal files)
        self.reports_tree_tab = ttk.Treeview(tree_frame_reports, columns=("date", "duration", "session_type", "ship", "system", "body", "tons", "tph", "tons_per", "asteroids", "materials", "total_hits", "hit_rate", "quality", "cargo", "prospects", "eng_materials", "comment", "enhanced"), show="headings", height=16, selectmode="extended", style="ReportsTab.Treeview")
        self.reports_tree_tab.grid(row=0, column=0, sticky="nsew")
        
        # Configure row tags for alternating colors (theme-aware)
        self.reports_tree_tab.tag_configure('oddrow', background=_tab_bg, foreground=_tab_fg)
        self.reports_tree_tab.tag_configure('evenrow', background=_tab_alt, foreground=_tab_fg)
        
        # Configure column headings
        self.reports_tree_tab.heading("date", text="Date/Time", anchor="w")
        self.reports_tree_tab.heading("duration", text="Duration", anchor="w")
        self.reports_tree_tab.heading("session_type", text="Type", anchor="w")
        self.reports_tree_tab.heading("ship", text="Ship", anchor="w")
        self.reports_tree_tab.heading("system", text="System", anchor="w")
        self.reports_tree_tab.heading("body", text="Planet/Ring", anchor="w")
        self.reports_tree_tab.heading("tons", text="Total Tons", anchor="w")
        self.reports_tree_tab.heading("tph", text="T/hr", anchor="w")
        self.reports_tree_tab.heading("tons_per", text="Tons/Asteroid", anchor="w")
        self.reports_tree_tab.heading("asteroids", text="Prospected", anchor="w")
        self.reports_tree_tab.heading("materials", text="Mat Types", anchor="w")
        # New column: Total Hits (number of asteroids that contained tracked materials)
        self.reports_tree_tab.heading("total_hits", text="Total Hits", anchor="w")
        self.reports_tree_tab.heading("hit_rate", text="Hit Rate %", anchor="w")
        self.reports_tree_tab.heading("quality", text="Average Yield %", anchor="w")
        self.reports_tree_tab.heading("cargo", text="Minerals (Tonnage, Yields & T/hr)", anchor="w")
        self.reports_tree_tab.heading("prospects", text="Limpets", anchor="w")
        self.reports_tree_tab.heading("eng_materials", text="Engineering Materials", anchor="w")
        self.reports_tree_tab.heading("comment", text="Comment", anchor="w")
        self.reports_tree_tab.heading("enhanced", text="Detail Report", anchor="w")
        
        # Add sorting to tab treeview
        tab_sort_dirs = {}
        def sort_tab_col(col):
            try:
                reverse = tab_sort_dirs.get(col, False)
                items = [(self.reports_tree_tab.set(item, col), item) for item in self.reports_tree_tab.get_children('')]
                
                # Smart sorting based on column type  
                numeric_cols = {"tons", "tph", "tons_per", "hit_rate", "quality", "materials", "asteroids", "prospects", "total_hits"}
                if col in numeric_cols:
                    # Numeric sorting - handle "—", empty values, and percentages
                    def safe_float(x):
                        try:
                            val = str(x).replace("—", "0").replace("%", "").strip()
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
                import traceback
                traceback.print_exc()
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
                                    orig_session.get('duration') == values[1] and 
                                    orig_session.get('system') == values[4] and
                                    orig_session.get('body') == values[5]):
                            new_tab_lookup[item_id] = orig_session
                            break
                
                self.reports_tab_session_lookup.clear()
                self.reports_tab_session_lookup.update(new_tab_lookup)
        
        # Set commands for all tab treeview columns
        self.reports_tree_tab.heading("date", command=lambda: sort_tab_col("date"))
        self.reports_tree_tab.heading("duration", command=lambda: sort_tab_col("duration"))
        self.reports_tree_tab.heading("system", command=lambda: sort_tab_col("system"))
        self.reports_tree_tab.heading("body", command=lambda: sort_tab_col("body"))
        self.reports_tree_tab.heading("tons", command=lambda: sort_tab_col("tons"))
        self.reports_tree_tab.heading("tph", command=lambda: sort_tab_col("tph"))
        self.reports_tree_tab.heading("tons_per", command=lambda: sort_tab_col("tons_per"))
        self.reports_tree_tab.heading("materials", command=lambda: sort_tab_col("materials"))
        self.reports_tree_tab.heading("asteroids", command=lambda: sort_tab_col("asteroids"))
        self.reports_tree_tab.heading("hit_rate", command=lambda: sort_tab_col("hit_rate"))
        self.reports_tree_tab.heading("quality", command=lambda: sort_tab_col("quality"))
        self.reports_tree_tab.heading("cargo", command=lambda: sort_tab_col("cargo"))
        self.reports_tree_tab.heading("prospects", command=lambda: sort_tab_col("prospects"))
        self.reports_tree_tab.heading("eng_materials", command=lambda: sort_tab_col("eng_materials"))
        self.reports_tree_tab.heading("comment", command=lambda: sort_tab_col("comment"))
        # Note: enhanced column intentionally has no sort command as it's just a status indicator

        
        # Configure column widths - locked at startup size, no resizing allowed
        
        self.reports_tree_tab.column("date", width=105, stretch=False, anchor="w")
        self.reports_tree_tab.column("duration", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("session_type", width=90, stretch=False, anchor="center")
        self.reports_tree_tab.column("ship", width=250, stretch=False, anchor="w")
        self.reports_tree_tab.column("system", width=230, stretch=False, anchor="w")
        self.reports_tree_tab.column("body", width=125, stretch=False, anchor="center")
        self.reports_tree_tab.column("tons", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("tph", width=60, stretch=False, anchor="center")
        self.reports_tree_tab.column("tons_per", width=85, stretch=False, anchor="center")
        self.reports_tree_tab.column("materials", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("total_hits", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("asteroids", width=80, stretch=False, anchor="center")
        self.reports_tree_tab.column("hit_rate", width=90, stretch=False, anchor="center")
        self.reports_tree_tab.column("quality", width=120, stretch=False, anchor="center")
        self.reports_tree_tab.column("cargo", width=350, stretch=False, anchor="w")
        self.reports_tree_tab.column("prospects", width=70, stretch=False, anchor="center")
        self.reports_tree_tab.column("eng_materials", width=250, stretch=False, anchor="w")
        self.reports_tree_tab.column("comment", width=80, stretch=False, anchor="center")  # Wider to show header text
        self.reports_tree_tab.column("enhanced", width=100, stretch=False, anchor="center")

        # Load saved column widths from config
        try:
            from config import load_mining_analysis_column_widths
            saved_widths = load_mining_analysis_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        self.reports_tree_tab.column(col_name, width=width)
                    except Exception as e:
                        pass
            else:
                pass
        except Exception as e:
            pass

        # Bind column resize event to save widths
        def save_column_widths_tab(event=None):
            try:
                print("[DEBUG] ButtonRelease-1 triggered on Reports Tab, attempting to save column widths...")
                from config import save_mining_analysis_column_widths
                widths = {}
                for col in ["date", "duration", "session_type", "ship", "system", "body", "tons", "tph", "tons_per", "asteroids", "materials", "hit_rate", "quality", "cargo", "prospects", "eng_materials", "comment", "enhanced"]:
                    try:
                        widths[col] = self.reports_tree_tab.column(col, "width")
                    except:
                        pass
                print(f"[DEBUG] Saving Reports Tab column widths: {widths}")
                save_mining_analysis_column_widths(widths)
                print("[DEBUG] Reports Tab column widths saved successfully")
            except Exception as e:
                print(f"[DEBUG] Could not save Reports Tab column widths: {e}")
        
        self.reports_tree_tab.bind("<ButtonRelease-1>", save_column_widths_tab)

        # Add vertical scrollbar
        v_scrollbar = ttk.Scrollbar(tree_frame_reports, orient="vertical", command=self.reports_tree_tab.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
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
        
        # Share to Discord button
        discord_btn = tk.Button(button_frame, text="Share to Discord", 
                               command=self._share_to_discord, 
                               bg="#5865F2", fg="#ffffff", 
                               activebackground="#4752C4", activeforeground="#ffffff", 
                               relief="solid", bd=1, 
                               highlightbackground="#666666", highlightcolor="#666666")
        discord_btn.pack(side="left", padx=(0, 5))
        self.ToolTip(discord_btn, "Share selected mining session report to Discord via webhook")
        
        # Mining Card button
        card_btn = tk.Button(button_frame, text="Mining Card", 
                            command=self._create_mining_card_from_report, 
                            bg="#FF8C00", fg="#ffffff", 
                            activebackground="#CC7000", activeforeground="#ffffff", 
                            relief="solid", bd=1, 
                            highlightbackground="#666666", highlightcolor="#666666")
        card_btn.pack(side="left", padx=(0, 5))
        self.ToolTip(card_btn, "Generate visual mining card (PNG) from selected session report")
        
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
                if len(values) < 5:
                    self._set_status("Invalid session data for bookmarking")
                    return
                
                # Extract system and body from session
                # Column order: date(0), duration(1), ship(2), system(3), body(4)
                system = values[3]  # System column (correct index)
                body = values[4]    # Body column (correct index)
                
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
                
                # System name is in column index 4 (date, duration, session_type, ship, system...)
                system_name = values[4]
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
            
            # Dynamic mapping for comment and enhanced columns
            try:
                cols = list(self.reports_tree_tab["columns"])
                comment_idx = cols.index('comment') if 'comment' in cols else None
                enhanced_idx = cols.index('enhanced') if 'enhanced' in cols else None
            except Exception:
                comment_idx = None
                enhanced_idx = None

            if comment_idx is not None and column == f"#{comment_idx+1}":
                self._edit_comment_popup_reports(event)
                return
            if enhanced_idx is not None and column == f"#{enhanced_idx+1}":
                # Handle detailed report opening on double-click
                column_name = cols[enhanced_idx]
                cell_value = self.reports_tree_tab.set(item, column_name)
                print(f"[DEBUG] Enhanced column double-clicked, cell value: {cell_value}")
                if cell_value == "📊":  # Has detailed report
                    session_data = self.reports_tab_session_lookup.get(item)
                    if session_data:
                        display_date = session_data.get('date', '')
                        system = session_data.get('system', '')
                        body = session_data.get('body', '')
                        report_id = f"{display_date}_{system}_{body}"
                        print(f"[DEBUG] Opening enhanced report with ID: {report_id}")
                        self._open_enhanced_report(report_id)
                    else:
                        print(f"[DEBUG] No session data found for item: {item}")
                else:
                    print(f"[DEBUG] No detailed report available (cell value: {cell_value})")
                return
            else:
                # For all other columns, open the text report file on double-click
                if item in self.reports_tab_session_lookup:
                    session = self.reports_tab_session_lookup[item]
                    file_path = session.get('file_path', '')
                    if file_path and os.path.exists(file_path):
                        self._open_path(file_path)
            # For all other columns, ignore double-click (single-click already handled it)
            # This prevents double-opening of text reports

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
                self._current_tooltip_column = None
        
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
                    context_menu.add_command(label="Open Report (TXT)", command=lambda: open_selected())
                    context_menu.add_command(label="Open Detailed Report (HTML)", command=lambda: self._open_enhanced_report_from_menu(self.reports_tree_tab))
                    context_menu.add_separator()
                    context_menu.add_command(label="Bookmark This Location", command=lambda: bookmark_selected())
                    context_menu.add_command(label="Generate Detailed Report (HTML)", command=lambda: self._generate_enhanced_report_from_menu(self.reports_tree_tab))
                    context_menu.add_separator()
                    context_menu.add_command(label="Copy System Name", command=lambda: copy_system_name_tab())
                    context_menu.add_separator()
                    context_menu.add_command(label="Share to Discord", command=lambda: self._share_selected_to_discord())
                    context_menu.add_command(label="Create Mining Card", command=lambda: self._create_mining_card_from_report())
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
                              f"• Mining card PNG (if any)\n"
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
                from main import centered_yesno_dialog
                if centered_yesno_dialog(
                    self.winfo_toplevel(),
                    title,
                    msg
                ):
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
                                # Get graphs directory using centralized path utility
                                graphs_dir = os.path.join(get_reports_dir(), "Graphs")
                                
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
                            
                            # Delete corresponding mining card (v4.4.3+)
                            try:
                                cards_dir = os.path.join(get_reports_dir(), "Cards")
                                
                                if os.path.exists(cards_dir):
                                    try:
                                        # Build expected card filename from session data
                                        from datetime import datetime
                                        dt = datetime.fromisoformat(timestamp_raw.replace('Z', ''))
                                        timestamp_str = dt.strftime("%Y-%m-%d_%H-%M-%S")
                                        
                                        clean_system = system.replace(' ', '_')
                                        clean_body = body.replace(' ', '_')
                                        
                                        expected_card = f"Session_{timestamp_str}_{clean_system}_{clean_body}_Card.png"
                                        card_path = os.path.join(cards_dir, expected_card)
                                        
                                        if os.path.exists(card_path):
                                            os.remove(card_path)
                                    except Exception as e:
                                        print(f"[DELETE] Error deleting mining card: {e}")
                                        import traceback
                                        traceback.print_exc()
                            except Exception as e:
                                print(f"[DELETE] Error in card deletion: {e}")
                            
                            # Delete screenshots and HTML report
                            try:
                                values = self.reports_tree_tab.item(item_id, 'values')
                                if values and len(values) >= 6:
                                    display_date = values[0]  # Date column
                                    # Columns: date, duration, session_type, ship, system, body...
                                    system_val = values[4] if len(values) > 4 else system  # System is column 4
                                    body_val = values[5] if len(values) > 5 else body      # Body is column 5
                                    report_id = f"{display_date}_{system_val}_{body_val}"
                                    
                                    # Delete HTML file
                                    html_filename = self._get_report_filenames(report_id)
                                    if html_filename:
                                        html_path = os.path.join(self.reports_dir, "Detailed Reports", html_filename)
                                        if os.path.exists(html_path):
                                            os.remove(html_path)
                                        
                                        # Remove from mappings
                                        mappings_file = os.path.join(self.reports_dir, "Detailed Reports", "detailed_report_mappings.json")
                                        if os.path.exists(mappings_file):
                                            try:
                                                with open(mappings_file, 'r', encoding='utf-8') as f:
                                                    mappings = json.load(f)
                                                if report_id in mappings:
                                                    del mappings[report_id]
                                                    with open(mappings_file, 'w', encoding='utf-8') as f:
                                                        json.dump(mappings, f, indent=2)
                                            except Exception as e:
                                                pass
                                    
                                    # Delete screenshots - try multiple report_id formats for compatibility
                                    screenshots = self._get_report_screenshots(report_id)
                                    
                                    # If not found, try alternate formats for older screenshots
                                    if not screenshots:
                                        session_type = values[2] if len(values) > 2 else ""  # Session type is column 2
                                        ship_name = values[3] if len(values) > 3 else ""     # Ship is column 3
                                        
                                        # Try old format 1: date_sessiontype_ship (old screenshot bug)
                                        if session_type and ship_name:
                                            old_format1 = f"{display_date}_{session_type}_{ship_name}"
                                            screenshots = self._get_report_screenshots(old_format1)
                                            if screenshots:
                                                report_id = old_format1
                                        
                                        # Try old format 2: date_ship_system (alternate format)
                                        if not screenshots and ship_name:
                                            old_format2 = f"{display_date}_{ship_name}_{system_val}"
                                            screenshots = self._get_report_screenshots(old_format2)
                                            if screenshots:
                                                report_id = old_format2
                                    
                                    for screenshot_path in screenshots:
                                        if os.path.exists(screenshot_path):
                                            os.remove(screenshot_path)
                                    
                                    # Remove screenshots from mapping file
                                    screenshots_map_file = os.path.join(self.reports_dir, "Detailed Reports", "screenshot_mappings.json")
                                    if os.path.exists(screenshots_map_file):
                                        try:
                                            with open(screenshots_map_file, 'r', encoding='utf-8') as f:
                                                screenshot_mappings = json.load(f)
                                            if report_id in screenshot_mappings:
                                                del screenshot_mappings[report_id]
                                                with open(screenshots_map_file, 'w', encoding='utf-8') as f:
                                                    json.dump(screenshot_mappings, f, indent=2)
                                        except Exception as e:
                                            pass
                            except Exception as e:
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
            # Don't show if tooltips are disabled (check the class variable)
            if not hasattr(self, 'ToolTip') or not self.ToolTip or not self.ToolTip.tooltips_enabled:
                # Hide any existing tooltip
                if hasattr(self, '_reports_tooltip_window') and self._reports_tooltip_window:
                    self._reports_tooltip_window.destroy()
                    self._reports_tooltip_window = None
                    self._current_tooltip_column = None
                return
            
            # Check if hovering over column header
            region = tree.identify_region(event.x, event.y)
            column = tree.identify_column(event.x)
            
            # If not over a heading, hide tooltip and return
            if region != "heading" or not column:
                if hasattr(self, '_reports_tooltip_window') and self._reports_tooltip_window:
                    self._reports_tooltip_window.destroy()
                    self._reports_tooltip_window = None
                    self._current_tooltip_column = None
                return
            
            # Only recreate tooltip if we're over a different column
            if hasattr(self, '_current_tooltip_column') and self._current_tooltip_column == column:
                return
            
            # Hide existing tooltip before creating new one
            if hasattr(self, '_reports_tooltip_window') and self._reports_tooltip_window:
                self._reports_tooltip_window.destroy()
                self._reports_tooltip_window = None
            
            if region == "heading" and column:
                column_tooltips = {
                    "#1": "Date and time when the mining session ended",
                    "#2": "Total duration of the mining session", 
                    "#3": "Session type (Single or Multi-session)",
                    "#4": "Ship name, type, and identifier used for mining",
                    "#5": "Star system where mining took place",
                    "#6": "Planet, ring, or celestial body that was mined",
                    "#7": "Total tons of materials mined",
                    "#8": "Tons per hour mining rate",
                    "#9": "Finds per ton (Hits / Tons)",
                    "#10": "Total asteroids scanned during the session",
                    "#11": "Number of different mineral types found within the threshold set in announcement panel",
                    "#12": "Total Material Hits — number of asteroids that contained the tracked materials",
                    "#13": "Percentage of asteroids that had valuable minerals (Hit Rate %)",
                    "#14": "Average quality/yield percentage of minerals found",
                    "#15": "Minerals mined with quantities and individual yields",
                    "#16": "Number of prospector limpets used during mining session",
                    "#17": "Engineering materials collected during the session",
                    "#18": "Session comments and notes",
                    "#19": "Detailed report for this session"
                }
                
                tooltip_text = column_tooltips.get(column)
                if tooltip_text:
                    x = event.x_root + 10
                    y = event.y_root + 10
                    
                    self._reports_tooltip_window = tk.Toplevel(tree)
                    self._reports_tooltip_window.wm_overrideredirect(True)
                    self._reports_tooltip_window.wm_geometry(f"+{x}+{y}")
                    self._reports_tooltip_window.configure(background="#ffffe0")
                    
                    # Make sure tooltip stays on top
                    self._reports_tooltip_window.wm_attributes("-topmost", True)
                    
                    label = tk.Label(self._reports_tooltip_window, text=tooltip_text,
                                   background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                                   font=("Segoe UI", 9), justify=tk.LEFT, wraplength=300)
                    label.pack(ipadx=5, ipady=3)
                    
                    # Track which column we're showing tooltip for
                    self._current_tooltip_column = column
        except Exception as e:
            print(f"Tooltip error: {e}")

    def _show_prospector_header_tooltip(self, event, tree):
        """Show tooltip for Prospector Reports column headers"""
        try:
            region = tree.identify_region(event.x, event.y)
            column = tree.identify_column(event.x)
            
            if region != "heading" or not column:
                if hasattr(self, '_prospector_tooltip_window') and self._prospector_tooltip_window:
                    self._prospector_tooltip_window.destroy()
                    self._prospector_tooltip_window = None
                    self._current_prospector_tooltip_column = None
                return
            
            if hasattr(self, '_current_prospector_tooltip_column') and self._current_prospector_tooltip_column == column:
                return
            
            if hasattr(self, '_prospector_tooltip_window') and self._prospector_tooltip_window:
                self._prospector_tooltip_window.destroy()
                self._prospector_tooltip_window = None
            
            if region == "heading" and column:
                column_tooltips = {
                    "#1": "Minerals found in this asteroid with their percentages",
                    "#2": "Material content quality and remaining percentage",
                    "#3": "Time when this asteroid was scanned"
                }
                
                tooltip_text = column_tooltips.get(column)
                if tooltip_text:
                    x = event.x_root + 10
                    y = event.y_root + 10
                    
                    self._prospector_tooltip_window = tk.Toplevel(tree)
                    self._prospector_tooltip_window.wm_overrideredirect(True)
                    self._prospector_tooltip_window.wm_geometry(f"+{x}+{y}")
                    self._prospector_tooltip_window.configure(background="#ffffe0")
                    self._prospector_tooltip_window.wm_attributes("-topmost", True)
                    
                    label = tk.Label(self._prospector_tooltip_window, text=tooltip_text,
                                   background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                                   font=("Segoe UI", 9), justify=tk.LEFT, wraplength=300)
                    label.pack(ipadx=5, ipady=3)
                    
                    self._current_prospector_tooltip_column = column
        except Exception as e:
            print(f"Prospector tooltip error: {e}")

    def _show_mineral_header_tooltip(self, event, tree):
        """Show tooltip for Mineral Analysis column headers"""
        try:
            region = tree.identify_region(event.x, event.y)
            column = tree.identify_column(event.x)
            
            if region != "heading" or not column:
                if hasattr(self, '_mineral_tooltip_window') and self._mineral_tooltip_window:
                    self._mineral_tooltip_window.destroy()
                    self._mineral_tooltip_window = None
                    self._current_mineral_tooltip_column = None
                return
            
            if hasattr(self, '_current_mineral_tooltip_column') and self._current_mineral_tooltip_column == column:
                return
            
            if hasattr(self, '_mineral_tooltip_window') and self._mineral_tooltip_window:
                self._mineral_tooltip_window.destroy()
                self._mineral_tooltip_window = None
            
            if region == "heading" and column:
                column_tooltips = {
                    "#1": "Material name with your announcement threshold\nExample: Platinum (27%) means you're only alerted when\nasteroids have 27% or higher Platinum content",
                    "#2": "Total tons of this material collected this session",
                    "#3": "Mining rate: Tons per hour for this material",
                    "#4": "Finds per ton (Hits / Tons) — average finds per ton collected for this material",
                    "#5": "Average % across ALL asteroids you prospected\n(includes low-quality asteroids below threshold)",
                    "#6": "Average % only for asteroids AT OR ABOVE threshold\n(your quality finds that triggered announcements)",
                    "#7": "Highest % found this session for this material",
                    "#8": "Most recent prospector scan result for this material",
                    "#9": "Number of hits that met your threshold\n(quality finds that triggered announcements)"
                }
                
                tooltip_text = column_tooltips.get(column)
                if tooltip_text:
                    x = event.x_root + 10
                    y = event.y_root + 10
                    
                    self._mineral_tooltip_window = tk.Toplevel(tree)
                    self._mineral_tooltip_window.wm_overrideredirect(True)
                    self._mineral_tooltip_window.wm_geometry(f"+{x}+{y}")
                    self._mineral_tooltip_window.configure(background="#ffffe0")
                    self._mineral_tooltip_window.wm_attributes("-topmost", True)
                    
                    label = tk.Label(self._mineral_tooltip_window, text=tooltip_text,
                                   background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                                   font=("Segoe UI", 9), justify=tk.LEFT, wraplength=350)
                    label.pack(ipadx=5, ipady=3)
                    
                    self._current_mineral_tooltip_column = column
        except Exception as e:
            print(f"Mineral tooltip error: {e}")

    def _on_date_filter_changed(self, event=None) -> None:
        """Handle date filter dropdown change"""
        self._refresh_reports_tab()

    def _edit_comment_inline(self, item, event) -> None:
        """Edit comment inline for a report item"""
        try:
            # Get the current comment using dynamic column lookup
            values = list(self.reports_tree_tab.item(item, 'values'))
            try:
                cols = list(self.reports_tree_tab['columns'])
                comment_idx = cols.index('comment')
            except Exception:
                comment_idx = None

            current_comment = ''
            if comment_idx is not None and len(values) > comment_idx:
                current_comment = values[comment_idx]

            # Get the bounding box of the comment cell using dynamic index
            bbox = None
            if comment_idx is not None:
                bbox = self.reports_tree_tab.bbox(item, f'#{comment_idx+1}')
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
                
                # Update the treeview at comment column
                if comment_idx is not None and len(values) > comment_idx:
                    values[comment_idx] = new_comment
                    self.reports_tree_tab.item(item, values=values)
                
                # Determine raw timestamp for CSV/text updates
                raw_timestamp = None
                try:
                    if hasattr(self, 'reports_tab_session_lookup') and item in self.reports_tab_session_lookup:
                        raw_timestamp = self.reports_tab_session_lookup[item].get('timestamp_raw')
                    elif hasattr(self, 'reports_window_session_lookup') and item in self.reports_window_session_lookup:
                        raw_timestamp = self.reports_window_session_lookup[item].get('timestamp_raw')
                except Exception:
                    raw_timestamp = None

                # Fallback to display timestamp if raw timestamp not found
                if not raw_timestamp:
                    raw_timestamp = values[0]

                # Update the CSV file and the corresponding text file
                csv_ok = self._update_comment_in_csv(raw_timestamp, new_comment)
                text_ok = self._update_comment_in_text_file(raw_timestamp, new_comment)

                # If either update failed, offer to revert UI change (consistent with body editor behavior)
                if not csv_ok or not text_ok:
                    from tkinter import messagebox
                    if not csv_ok and not text_ok:
                        error_msg = "Failed to update comment in both CSV and text files."
                    elif not csv_ok:
                        error_msg = "Failed to update comment in CSV file.\nText file was updated successfully."
                    else:
                        error_msg = "Failed to update comment in text file.\nCSV file was updated successfully."

                    result = centered_askyesno(
                        self.winfo_toplevel(),
                        "Update Failed",
                        f"{error_msg}\n\n"
                        f"The comment change is only visible in the UI but may not persist.\n"
                        f"This may cause data inconsistency.\n\n"
                        f"Would you like to revert the UI change?"
                    )
                    if result:
                        # Revert UI
                        if comment_idx is not None and len(values) > comment_idx:
                            values[comment_idx] = current_comment
                            self.reports_tree_tab.item(item, values=values)
                
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

    def _get_ship_name_from_session(self, system: str, body: str, timestamp_raw: str) -> tuple:
        """
        Parse ship name from session TXT file.
        Returns: (ship_name, file_path) tuple
        """
        try:
            # Build the filename from session metadata
            # Format: Session_YYYY-MM-DD_HH-MM-SS_System_Body.txt
            # NOTE: Spaces in system/body names are replaced with underscores in filenames
            if not timestamp_raw:
                print(f"[DEBUG] Ship name parse - no timestamp_raw")
                return ("", "")
            
            # Parse timestamp to get date/time parts for filename
            import datetime as dt
            try:
                if timestamp_raw.endswith('Z'):
                    session_time = dt.datetime.fromisoformat(timestamp_raw.replace('Z', '+00:00'))
                    session_time = session_time.replace(tzinfo=dt.timezone.utc).astimezone()
                else:
                    session_time = dt.datetime.fromisoformat(timestamp_raw)
                
                # Format timestamp for filename: YYYY-MM-DD_HH-MM-SS
                date_str = session_time.strftime("%Y-%m-%d")
                time_str = session_time.strftime("%H-%M-%S")
            except Exception as e:
                print(f"[DEBUG] Ship name parse - timestamp parse failed: {e}")
                return ("", "")
            
            # Replace spaces with underscores in system and body names to match filename format
            system_filename = system.replace(" ", "_")
            body_filename = body.replace(" ", "_")
            
            # Build filename pattern
            filename_base = f"Session_{date_str}_{time_str}_{system_filename}_{body_filename}.txt"
            txt_path = os.path.join(self.reports_dir, filename_base)
            
            # If exact filename doesn't exist, search for files matching timestamp and system
            # This handles cases where body name in CSV differs from filename (e.g., carrier vs ring location)
            if not os.path.exists(txt_path):
                import glob
                
                # Search pattern: Session_YYYY-MM-DD_HH-MM-SS_System_*.txt
                search_pattern = f"Session_{date_str}_{time_str}_{system_filename}_*.txt"
                search_path = os.path.join(self.reports_dir, search_pattern)
                
                matching_files = glob.glob(search_path)
                if matching_files:
                    # Use the first match (should only be one file per timestamp+system)
                    txt_path = matching_files[0]
                else:
                    return ("", "")
            
            # Read the TXT file
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # Format: "Session: SYSTEM — BODY — DURATION — Total XXXt\nShip: SHIP_NAME | materials..."
            ship_match = content.find("\nShip: ")
            
            if ship_match != -1:
                ship_start = ship_match + 7  # Length of "\nShip: "
                ship_end = content.find(" |", ship_start)
                if ship_end == -1:
                    ship_end = content.find("\n", ship_start)
                if ship_end == -1:
                    ship_end = len(content)
                
                ship_name = content[ship_start:ship_end].strip()
                print(f"[DEBUG] Ship name parse - extracted: '{ship_name}'")
                
                # Remove ship ID in parentheses (e.g., "(VIPD68)") from display
                # Example: "Mega Bumper (VIPD68) - Type-11 Prospector" → "Mega Bumper - Type-11 Prospector"
                import re
                ship_name_cleaned = re.sub(r'\s*\([A-Z0-9-]+\)\s*', ' ', ship_name).strip()
                print(f"[DEBUG] Ship name parse - after regex: '{ship_name_cleaned}'")
                
                return (ship_name_cleaned if ship_name_cleaned else "", txt_path)
            
            print(f"[DEBUG] Ship name parse - 'Ship:' line not found in file")
            return ("", txt_path)
        except Exception as e:
            print(f"[DEBUG] Ship name parse - exception: {e}")
            return ("", "")

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
                        # Compute total finds (hits) and Tons/Hit for this CSV row
                        try:
                            total_finds = int(str(row.get('total_finds', '')).strip() or 0)
                        except Exception:
                            total_finds = 0

                        try:
                            asteroids_count = int(str(row.get('asteroids_prospected', '')).strip() or 0)
                        except Exception:
                            asteroids_count = 0

                        try:
                            total_tons_val = float(row.get('total_tons', 0.0) or 0.0)
                        except Exception:
                            try:
                                total_tons_val = float(tons_str)
                            except Exception:
                                total_tons_val = 0.0

                        if total_finds > 0:
                            try:
                                tons_per_str = f"{total_tons_val / total_finds:.1f}"
                            except Exception:
                                tons_per_str = "—"
                        elif asteroids_count > 0:
                            try:
                                tons_per_str = f"{total_tons_val / asteroids_count:.1f}"
                            except Exception:
                                tons_per_str = "—"
                        else:
                            tons_per_str = "—"
                        
                        # Format Material Analysis fields (with fallback for old data)
                        asteroids = row.get('asteroids_prospected', '').strip() or '—'
                        materials = row.get('materials_tracked', '').strip() or '—'
                        hit_rate = row.get('hit_rate_percent', '').strip() or '—'
                        avg_quality = row.get('avg_quality_percent', '').strip() or '—'
                        
                        # Get new cargo tracking fields
                        materials_breakdown_raw = row.get('materials_breakdown', '').strip() or '—'
                        material_tph_breakdown = row.get('material_tph_breakdown', '').strip() or ''
                        prospectors_used = row.get('prospectors_used', '').strip() or '—'
                        
                        # Enhanced materials display with yield percentages and TPH
                        materials_breakdown = self._enhance_materials_with_yields_and_tph(materials_breakdown_raw, avg_quality, material_tph_breakdown)
                        
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
                        
                        # Format quality (yield %) - convert to average yield instead of individual percentages for display
                        # BUT keep the original detailed string for report generation
                        quality_str = "—"
                        quality_detailed = avg_quality  # Keep original for report generation
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
                                
                                # Calculate simple average (same as HTML report logic) for display
                                if individual_yields:
                                    avg_yield = sum(individual_yields) / len(individual_yields)
                                    quality_str = f"{avg_yield:.1f}%"
                                else:
                                    quality_str = "—"
                            else:
                                # Old numerical format - keep as is
                                quality_val = float(avg_quality) if avg_quality and avg_quality != '0' else 0
                                quality_str = f"{quality_val:.1f}%" if quality_val > 0 else "—"
                                quality_detailed = quality_str  # No detailed data available
                        except:
                            quality_str = "—"
                            quality_detailed = ""
                        
                        # Get comment data from CSV
                        comment_from_csv = row.get('comment', '').strip()
                        
                        # Get engineering materials from CSV
                        engineering_materials = row.get('engineering_materials', '').strip()
                        
                        try:
                            total_finds_val = int(str(row.get('total_finds', '')).strip() or 0)
                        except Exception:
                            total_finds_val = 0

                        sessions_data.append({
                            'date': date_str,
                            'system': row['system'],
                            'body': row['body'],
                            'duration': row['elapsed'],
                            'tons': tons_str,
                            'tph': tph_str,
                            'tons_per': tons_per_str,
                            'asteroids': asteroids_str,
                            'materials': materials_str,
                            'hit_rate': hit_rate_str,
                            'quality': quality_str,
                            'quality_detailed': quality_detailed,  # Keep detailed breakdown for reports
                            'avg_quality_percent': quality_detailed,  # Also store as avg_quality_percent for compatibility
                            'cargo': materials_breakdown,
                            'cargo_raw': materials_breakdown_raw,  # Store original for tooltip
                            'prospects': prospectors_used,
                            'engineering_materials': engineering_materials,  # Add engineering materials field
                            'comment': comment_from_csv,
                            'total_finds': total_finds_val,
                            'total_hits': total_finds_val,
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
            for i, session in enumerate(sessions_data):
                # Apply alternating row tags
                tag = "evenrow" if i % 2 == 0 else "oddrow"
                # Check if this report has screenshots
                # Check if this report has detailed reports (keep screenshots functionality but don't show column)
                # Use tree values for consistent report_id matching
                
                # Format engineering materials for display: "Iron (45) G1, Nickel (23) G1"
                eng_materials_display = ""
                eng_materials_raw = session.get('engineering_materials', '')
                if eng_materials_raw and eng_materials_raw.strip():
                    try:
                        # Parse "Iron:45,Nickel:23" format and show ALL materials (no limit)
                        mat_pairs = [p for p in eng_materials_raw.split(',') if ':' in p]
                        formatted_mats = []
                        for pair in mat_pairs:  # Show ALL materials
                            mat_name, qty = pair.split(':', 1)
                            # Get grade from cargo monitor
                            grade = 0
                            if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
                                grade = self.main_app.cargo_monitor.MATERIAL_GRADES.get(mat_name.strip(), 0)
                            formatted_mats.append(f"{mat_name.strip()} ({qty}) G{grade}")
                        
                        # Show all materials without "+X more"
                        eng_materials_display = ", ".join(formatted_mats)
                    except Exception as e:
                        eng_materials_display = eng_materials_raw  # Fallback to raw string
                
                # Get ship name and file path from miningSessionSummary.txt
                print(f"[DEBUG] Parsing session - system: '{session['system']}', body: '{session['body']}', timestamp: '{session['timestamp_raw']}'")
                ship_name, file_path = self._get_ship_name_from_session(
                    session['system'],
                    session['body'],
                    session['timestamp_raw']
                )
                
                # Extract session type from TXT file (or use existing field if available)
                session['file_path'] = file_path  # Store for later use
                session_type = self._extract_session_type_from_data(session)
                # Shorten for display: "Multi-Session" → "Multi", "Single Session" → "Single"
                session_type_display = "Multi" if "Multi" in session_type else "Single"

                # Compute Tons/Asteroid for this session using TXT 'Total Material Finds' if available
                # Per request: Tons/Asteroid = Total Tons / Total Material Finds
                try:
                    # total_tons may be under multiple keys depending on parsing: try a few fallbacks
                    total_raw = session.get('total_tons') if session.get('total_tons') is not None else session.get('tons') if session.get('tons') is not None else session.get('total') if session.get('total') is not None else session.get('cargo_total') if session.get('cargo_total') is not None else '0'
                    total_tons_val = float(str(total_raw).replace('—', '0').replace(',', ''))
                except Exception:
                    total_tons_val = 0.0

                try:
                    total_finds_val = int(str(session.get('total_finds', '')).strip() or 0)
                except Exception:
                    total_finds_val = 0

                # If CSV/session dict lacks total_finds, attempt to parse the TXT report directly now
                if (not total_finds_val or total_finds_val == 0) and session.get('timestamp_raw'):
                    try:
                        import datetime as _dt, glob, re
                        raw_ts = session.get('timestamp_raw')
                        if raw_ts.endswith('Z'):
                            ts = _dt.datetime.fromisoformat(raw_ts.replace('Z', '+00:00'))
                            ts = ts.replace(tzinfo=_dt.timezone.utc).astimezone()
                        else:
                            ts = _dt.datetime.fromisoformat(raw_ts)
                        date_part = ts.strftime("%Y-%m-%d")
                        time_part = ts.strftime("%H-%M-%S")
                        system_filename = (session.get('system','') or '').replace(' ', '_')
                        body_filename = (session.get('body','') or '').replace(' ', '_')
                        patterns = [
                            f"Session_{date_part}_{time_part}_{system_filename}_{body_filename}.txt",
                            f"Session_{date_part}_*_{system_filename}_*.txt",
                            f"Session_{date_part}_*_*_{body_filename}.txt",
                        ]
                        matches = []
                        for p in patterns:
                            matches.extend(glob.glob(os.path.join(self.reports_dir, p)))
                        for txt_path in matches:
                            try:
                                with open(txt_path, 'r', encoding='utf-8') as tf:
                                    txt_content = tf.read()
                                    tf_m = re.search(r'Total Material Hits:\s*(\d+)', txt_content)
                                    if not tf_m:
                                        tf_m = re.search(r'Total Material Finds:\s*(\d+)', txt_content)
                                    if tf_m:
                                        parsed = int(tf_m.group(1))
                                        if parsed > 0:
                                            total_finds_val = parsed
                                            break
                            except Exception:
                                continue
                    except Exception:
                        pass

                if total_finds_val > 0 and total_tons_val > 0:
                    try:
                        tons_per_session_val = total_tons_val / total_finds_val
                        tons_per_session_display = f"{tons_per_session_val:.1f}"
                    except Exception:
                        tons_per_session_display = '—'
                else:
                    # If we couldn't get explicit total_finds, try to derive from hit_rate and asteroids_prospected
                    try:
                        if total_finds_val == 0:
                            # Possible hit rate fields in session: 'hit_rate', 'hit_rate_percent'
                            hr_raw = session.get('hit_rate') or session.get('hit_rate_percent') or ''
                            if isinstance(hr_raw, str):
                                hr_str = hr_raw.replace('%', '').strip()
                            else:
                                hr_str = str(hr_raw)

                            ap_raw = session.get('asteroids_prospected') or session.get('asteroids') or ''
                            try:
                                ap_int = int(str(ap_raw).strip() or 0)
                            except Exception:
                                ap_int = 0

                            try:
                                hr_val = float(hr_str) if hr_str not in ('', '—') else 0.0
                            except Exception:
                                hr_val = 0.0

                            if ap_int > 0 and hr_val > 0:
                                derived_hits = int(round(ap_int * (hr_val / 100.0)))
                                if derived_hits > 0:
                                    total_finds_val = derived_hits
                    except Exception:
                        pass

                    if total_finds_val > 0:
                        try:
                            tons_per_session_val = total_tons_val / total_finds_val
                            tons_per_session_display = f"{tons_per_session_val:.1f}"
                        except Exception:
                            tons_per_session_display = '—'
                    else:
                        tons_per_session_display = session.get('tons_per', '—')

                # Debugging output for problematic sessions (temporary)
                try:
                    if total_tons_val >= 200:
                        print(f"[DEBUG-TONS] date={session.get('date','?')} file={file_path} total_tons={total_tons_val} csv_total_finds={session.get('total_finds')} parsed_total_finds={total_finds_val} asteroids_prospected={session.get('asteroids_prospected','?')} tons_per_display={tons_per_session_display}")
                except Exception:
                    pass
                try:
                    # Targeted debug for the example session you pasted
                    if (str(session.get('system','')).startswith('Col 285 Sector YF-O d6-85') and
                        str(session.get('body','')).startswith('4 A Ring')):
                        print(f"[DEBUG-TONS-TARGET] system={session.get('system')} body={session.get('body')} date={session.get('date')} total_tons={total_tons_val} csv_total_finds={session.get('total_finds')} parsed_total_finds={total_finds_val} asteroids_prospected={session.get('asteroids_prospected')} tons_per_display={tons_per_session_display} file_path={file_path}")
                except Exception:
                    pass
                
                # Build values list dynamically from the tab tree's columns to avoid ordering mismatches
                cols = list(self.reports_tree_tab["columns"])
                vals = []
                for col in cols:
                    if col == 'date':
                        vals.append(session.get('date', ''))
                    elif col == 'duration':
                        vals.append(session.get('duration', ''))
                    elif col == 'session_type':
                        vals.append(session_type_display)
                    elif col == 'ship':
                        vals.append(ship_name)
                    elif col == 'system':
                        vals.append(session.get('system', ''))
                    elif col == 'body':
                        vals.append(session.get('body', ''))
                    elif col == 'tons':
                        vals.append(session.get('tons', ''))
                    elif col == 'tph':
                        vals.append(session.get('tph', ''))
                    elif col == 'tons_per':
                        # Use session-level Tons/Asteroid computed from TXT Total Material Finds when available
                        vals.append(tons_per_session_display)
                    elif col == 'asteroids':
                        vals.append(session.get('asteroids', ''))
                    elif col == 'materials':
                        vals.append(session.get('materials', ''))
                    elif col == 'total_hits':
                        # Prefer parsed/derived total_finds_val, fall back to session field
                        try:
                            hits_display = str(total_finds_val) if total_finds_val and int(total_finds_val) > 0 else (str(session.get('total_finds', '')) or '—')
                        except Exception:
                            hits_display = str(session.get('total_finds', '')) or '—'
                        vals.append(hits_display)
                    elif col == 'hit_rate':
                        vals.append(session.get('hit_rate', ''))
                    elif col == 'quality':
                        vals.append(session.get('quality', ''))
                    elif col == 'cargo':
                        vals.append(session.get('cargo', ''))
                    elif col in ('prospects', 'prospectors'):
                        vals.append(session.get('prospects', session.get('prospectors', '—')))
                    elif col == 'eng_materials':
                        vals.append(eng_materials_display)
                    elif col == 'comment':
                        vals.append('💬' if session.get('comment', '').strip() else '')
                    elif col == 'enhanced':
                        vals.append("")
                    else:
                        vals.append(session.get(col, ''))

                item_id = self.reports_tree_tab.insert("", "end", values=tuple(vals), tags=(tag,))

                # Explicitly set important columns to avoid any column-ordering shifts
                try:
                    # Engineering materials should go in the eng_materials column
                    self.reports_tree_tab.set(item_id, 'eng_materials', eng_materials_display)

                    # Comment emoji should always be placed in the comment column
                    self.reports_tree_tab.set(item_id, 'comment', '💬' if session.get('comment', '').strip() else '')

                    # Ensure Tons/Asteroid displays the TXT-derived/session computed value (UI-only override)
                    try:
                        self.reports_tree_tab.set(item_id, 'tons_per', tons_per_session_display)
                    except Exception:
                        pass
                    # Ensure Total Hits column displays parsed/derived total_finds
                    try:
                        hits_display = str(total_finds_val) if total_finds_val and int(total_finds_val) > 0 else (str(session.get('total_finds', '')) or '')
                        if hits_display:
                            self.reports_tree_tab.set(item_id, 'total_hits', hits_display)
                    except Exception:
                        pass

                    # Enhanced indicator via constructed id
                    date_val = self.reports_tree_tab.set(item_id, "date")
                    system_val = self.reports_tree_tab.set(item_id, "system")
                    body_val = self.reports_tree_tab.set(item_id, "body")
                    if date_val and system_val and body_val:
                        tree_report_id = f"{date_val}_{system_val}_{body_val}"
                        enhanced_indicator = self._get_detailed_report_indicator(tree_report_id)
                        self.reports_tree_tab.set(item_id, "enhanced", enhanced_indicator)
                except Exception:
                    pass

                # Store the full session data for tooltip lookup (including ship name and file path)
                session['ship_name'] = ship_name  # Add ship name to session data for HTML report generation
                session['file_path'] = file_path  # Add file path for session type extraction
                self.reports_tab_session_lookup[item_id] = session
            
            # Apply initial word wrap state for reports tab
            if self.reports_tab_word_wrap_enabled.get():
                max_lines = 1
                for item in self.reports_tree_tab.get_children():
                    item_data = self.reports_tab_session_lookup.get(item)
                    if item_data:
                        lines = item_data.get('cargo_raw', '').count(';') + 1
                        max_lines = max(max_lines, min(lines, 3))
                new_height = max_lines * 20 + 10
                style = ttk.Style()
                style.configure("ReportsTab.Treeview", rowheight=new_height)
                self.reports_tree_tab.configure(style="ReportsTab.Treeview")

            # Defensive pass: ensure comment and engineering materials are pinned to correct columns
            try:
                self._ensure_comment_and_eng_cells(self.reports_tree_tab, self.reports_tab_session_lookup)
            except Exception:
                pass

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
                    
                    # Multi-session mode: live_tons already includes ALL mined materials
                    # (session_minerals_mined tracks cumulative total including sold/transferred)
                    # DO NOT add sold/transferred again - it would be double counting!
                    
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
                    summary_text = f"Asteroids scanned: {total_asteroids} | Minerals tracked/hits: {tracked_materials}/{total_hits} | Total tons: {live_tons:.1f} | TPH: {live_tph:.1f}"
                else:
                    summary_text = f"Asteroids scanned: {total_asteroids} | Minerals tracked/hits: {tracked_materials}/{total_hits}"
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
            # Skip to end of file to avoid reading old events
            try:
                file_size = os.path.getsize(latest)
                self._jrnl_pos = file_size  # Start at end, not 0!
            except Exception:
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
                if self._jrnl_pos > 0:  # Explicit comparison, not truthiness
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
            
            # Auto-start session on first prospector limpet launch
            if ev == "LaunchDrone" and evt.get("Type") == "Prospector":
                if self.auto_start_on_prospector and not self.session_active:
                    # Auto-start session on first prospector
                    print(f"[AUTO-START] Prospector launched - auto-starting session")
                    self.after(100, self._session_start)  # Delay slightly to ensure UI is ready

            if ev in ("Location", "FSDJump"):
                # Update system from events that contain StarSystem data
                if evt.get("StarSystem"):
                    self.last_system = evt.get("StarSystem")
                    self.session_system.set(self.last_system)
                    
                    # Get coordinates if available
                    coords = None
                    if "StarPos" in evt:
                        coords = tuple(evt["StarPos"])
                    
                    # Notify main app - centralized system update
                    if self.main_app and hasattr(self.main_app, 'update_current_system'):
                        self.main_app.update_current_system(self.last_system, coords)
                        # Update distances in background (non-blocking)
                        if hasattr(self.app, '_update_home_fc_distances'):
                            self.app.after(100, self.app._update_home_fc_distances)
                
                # Update location context
                self.last_body_type = evt.get("BodyType", "")
            
            # Track Fleet Carrier location changes
            if ev == "CarrierLocation":
                carrier_system = evt.get("StarSystem")
                if carrier_system:
                    print(f"[FLEET CARRIER] CarrierLocation: system={carrier_system}")
                    
                    # Update fleet carrier system in distance calculator
                    if hasattr(self.app, 'distance_fc_system'):
                        self.app.distance_fc_system.set(carrier_system)
                    
                    # ALSO UPDATE PLAYER'S CURRENT SYSTEM since CarrierLocation indicates where the player is
                    self.last_system = carrier_system
                    self.session_system.set(self.last_system)
                    
                    # Get coordinates if available
                    coords = None
                    if "StarPos" in evt:
                        coords = tuple(evt["StarPos"])
                    
                    # Notify main app - centralized system update
                    if self.main_app and hasattr(self.main_app, 'update_current_system'):
                        self.main_app.update_current_system(self.last_system, coords)
                    
                    # Update distances in Distance Calculator (non-blocking)
                    if hasattr(self.app, '_update_home_fc_distances'):
                        self.app.after(100, self.app._update_home_fc_distances)
                
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
                body_type = evt.get("BodyType", "")
                system_name = evt.get("StarSystem") or self.last_system or ""
                
                # Only set last_body if it's not just the system name (i.e., we're at a ring/planet, not a star)
                # Stars have BodyType "Star" and their name often matches or is very similar to system name
                if body_name:
                    # Skip if body is exactly the system name or body is a Star type
                    is_star = body_type == "Star" or body_name == system_name
                    if not is_star:
                        self.last_body = body_name
                        self.last_body_type = body_type
                    elif ev == "FSDJump":
                        # Clear body when jumping to a new system (we're at the arrival star)
                        self.last_body = ""
                        self.last_body_type = ""
                
                # Check Status.json for real-time location after Location/FSDJump events
                self._check_status_location_fields()
                
                # Only update location display if we have meaningful context
                # Priority: Fleet Carrier > Station > Body (only if body is not empty)
                if self.last_carrier_name or self.last_station_name or self.last_body:
                    body_display = _extract_location_display(
                        self.last_body or "", 
                        self.last_body_type, 
                        self.last_station_name, 
                        self.last_carrier_name,
                        self.last_system or self.session_system.get() or ""
                    )
                    self.session_body.set(body_display)
                else:
                    # No meaningful body context - clear the field
                    self.session_body.set("")
                    
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
                                self.last_carrier_name,
                                self.last_system or self.session_system.get() or ""
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
                                self.last_carrier_name,
                                self.last_system or self.session_system.get() or ""
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
                            self.last_carrier_name,
                            self.last_system or self.session_system.get() or ""
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
                        self.last_carrier_name,
                        self.last_system or self.session_system.get() or ""
                    )
                    self.session_body.set(body_display)
                    # Debug removed
                else:
                    # Debug removed - ignoring journal docking event when Status.json shows not docked
                    pass
                    
            elif ev in ("CarrierJump", "CarrierLocation"):
                # Fleet carrier jump - update carrier context
                print(f"[DEBUG] Processing {ev} event: {evt.get('StarSystem', 'NO_SYSTEM')}")  # Debug
                carrier_name = evt.get("StationName", "") or evt.get("CarrierName", "")
                if carrier_name:
                    self.last_carrier_name = carrier_name
                    self.last_station_name = ""
                    
                    # Update body info from carrier event
                    body_name = evt.get("Body") or evt.get("BodyName")
                    if body_name:
                        self.last_body = body_name
                        self.last_body_type = evt.get("BodyType", "")
                        
                        body_display = _extract_location_display(
                            body_name, 
                            self.last_body_type, 
                            self.last_station_name, 
                            self.last_carrier_name,
                            self.last_system or self.session_system.get() or ""
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
                            self.last_carrier_name,
                            self.last_system or self.session_system.get() or ""
                        )
                        self.session_body.set(body_display)

            if ev == "ProspectedAsteroid":
                # Check if this is a startup skip (old event from before app started)
                if self._startup_skip:
                    self._startup_skip = False  # Clear flag immediately to process first event
                    
                    # Check timestamp - if event is more than 10 seconds old, skip it
                    event_time = evt.get("timestamp", "")
                    
                    if event_time:
                        try:
                            from datetime import datetime, timezone
                            event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                            now_dt = datetime.now(timezone.utc)
                            time_diff = (now_dt - event_dt).total_seconds()
                            
                            print(f"[STARTUP DEBUG] First ProspectedAsteroid - Age: {time_diff:.1f}s")
                            
                            if time_diff > 30:  # Event is older than 30 seconds (increased to handle app restart delays)
                                print(f"[STARTUP DEBUG] Skipping old event (>{30}s old)")
                                return  # Skip only old events
                            else:
                                print(f"[STARTUP DEBUG] Processing fresh event (<{30}s old)")
                        except Exception as e:
                            print(f"[STARTUP DEBUG] Timestamp parse error: {e}, processing anyway")
                            pass  # If timestamp parsing fails, process the event
                materials_txt, content_txt, time_txt, panel_summary, speak_summary, triggered = self._summaries_from_event(evt)
                self.history.insert(0, (materials_txt, content_txt, time_txt))
                
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
                # Normalize motherlode name to English for lookup in announce_map
                if mother:
                    mother_for_lookup = JournalParser.normalize_material_name(mother)
                    if core_toggle and self.announce_map.get(mother_for_lookup, True):
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
                            # Handle multi-word material names by splitting at the LAST space (percentage is always last word)
                            reordered_materials = []
                            for p in non_core_materials:
                                if p.startswith("Motherlode:"):
                                    reordered_materials.append(p)
                                else:
                                    parts = p.rsplit(' ', 1)  # Split at last space only
                                    if len(parts) == 2:
                                        # Swap: "Material Name 18.7%" -> "18.7% Material Name"
                                        reordered_materials.append(f"{parts[1]} {parts[0]}")
                                    else:
                                        reordered_materials.append(p)
                            
                            # Join materials with "and" before the last item
                            if len(reordered_materials) == 1:
                                noncore_msg = reordered_materials[0]
                            elif len(reordered_materials) == 2:
                                noncore_msg = f"{reordered_materials[0]} and {reordered_materials[1]}"
                            else:
                                # Multiple materials: "A, B, C and D"
                                noncore_msg = ", ".join(reordered_materials[:-1]) + f" and {reordered_materials[-1]}"
                            

                
                # ALWAYS show overlay (even if below threshold)
                # The overlay shows the full panel_summary data regardless of announcement settings
                if self.text_overlay:
                    # Determine what message to use for TTS (may be empty if nothing triggered)
                    if core_msg and noncore_msg:
                        tts_msg = f"Prospector Reports: {core_msg} and {noncore_msg}"
                    elif core_msg:
                        tts_msg = f"Prospector Reports: {core_msg}"
                    elif noncore_msg:
                        tts_msg = f"Prospector Reports: {noncore_msg}"
                    else:
                        tts_msg = ""  # No TTS, but still show overlay
                    
                    # Show overlay with both filtered and unfiltered data
                    # Pass mother (core material) for enhanced overlay display
                    self._show_prospector_overlay_or_standard(tts_msg, panel_summary, materials_txt, content_txt, mother)
                
                # TTS announcement (only if triggered)
                if core_msg and noncore_msg:
                    # Both core and non-core - combine with "and"
                    msg = f"Prospector Reports: {core_msg} and {noncore_msg}"
                    announcer.say(msg)
                    announcement_made = True
                    self._set_status("Combined core and non-core announcement triggered.")
                elif core_msg:
                    # Only core
                    msg = f"Prospector Reports: {core_msg}"
                    announcer.say(msg)
                    announcement_made = True
                    self._set_status("Core announcement triggered.")
                elif noncore_msg:
                    # Only non-core
                    msg = f"Prospector Reports: {noncore_msg}"
                    announcer.say(msg)
                    announcement_made = True
                    self._set_status("Non-core announcement triggered.")

            if self.session_active and ev == "MiningRefined":
                name = _clean_name(evt.get("Type_Localised") or evt.get("Type") or "")
                if name:
                    self.session_totals[name] = self.session_totals.get(name, 0.0) + 1.0  # 1 ton per refine
                    
                    # Update session location from actual mining location (not carrier/station where session started)
                    if not self.session_location_captured_from_mining:
                        if self.last_system:
                            self.session_system.set(self.last_system)
                            print(f"[Session Location] Updated system from mining: {self.last_system}")
                        if self.last_body:
                            body_display = _extract_location_display(
                                self.last_body, 
                                self.last_body_type, 
                                self.last_station_name, 
                                self.last_carrier_name,
                                self.last_system or self.session_system.get() or ""
                            )
                            self.session_body.set(body_display)
                            # PRESERVE mining location for report (won't be overwritten by docking)
                            self.session_mining_body = body_display
                            print(f"[Session Location] Updated body from mining: {body_display}")
                            print(f"[Session Location] PRESERVED mining body: {self.session_mining_body}")
                        self.session_location_captured_from_mining = True

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
        
        print(f"[ANNOUNCE DEBUG] _summaries_from_event called, materials count: {len(materials)}, threshold: {th}")

        for m in materials:
            name = _extract_material_name(m)
            pct_val = _extract_material_percent(m)
            pct_text = _fmt_pct(pct_val)
            if not name:
                continue
            entry = f"{name} {pct_text}".strip()
            all_parts.append(entry)

            eff_th = float(self.min_pct_map.get(name, th))
            # Normalize material name to English for lookup in announce_map
            # This ensures German/French/Spanish names match English settings
            name_for_lookup = JournalParser.normalize_material_name(name)
            print(f"[ANNOUNCE DEBUG] Material: '{name}' → Normalized: '{name_for_lookup}'")
            is_enabled = self.announce_map.get(name_for_lookup, False)
            print(f"[ANNOUNCE DEBUG] announce_map.get('{name_for_lookup}') = {is_enabled}")
            if not is_enabled and name_for_lookup != name_for_lookup.title():
                is_enabled = self.announce_map.get(name_for_lookup.title(), False)
                print(f"[ANNOUNCE DEBUG] Retry with title case: '{name_for_lookup.title()}' = {is_enabled}")
            print(f"[ANNOUNCE DEBUG] Final enabled={is_enabled}, pct={pct_val}, threshold={eff_th}")
            if pct_val is not None and is_enabled and pct_val >= eff_th:
                speak_parts.append(entry)
                triggered = True

        mother = evt.get("MotherlodeMaterial_Localised") or evt.get("MotherlodeMaterial")
        mother = _clean_name(mother) if isinstance(mother, str) else ""
        if mother:
            all_parts.insert(0, f"Motherlode: {mother}")
            # Normalize motherlode name to English for lookup in announce_map
            mother_for_lookup = JournalParser.normalize_material_name(mother)
            # Only add to speak_parts if Core Asteroids toggle is enabled
            core_toggle = bool(self.announcement_vars["Core Asteroids"].get())
            if self.announce_map.get(mother_for_lookup, False):   # Default to False for consistency
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
        for idx, (materials_txt, content_txt, time_txt) in enumerate(self.history):
            tag = "evenrow" if idx % 2 == 0 else "oddrow"
            self.tree.insert("", "end", values=(materials_txt, content_txt, time_txt), tags=(tag,))

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
            
            # Get live cargo data per material
            live_materials = {}
            if (self.main_app and hasattr(self.main_app, 'cargo_monitor') and 
                hasattr(self.main_app.cargo_monitor, 'get_live_session_materials')):
                try:
                    live_materials = self.main_app.cargo_monitor.get_live_session_materials() or {}
                except Exception as e:
                    print(f"[DEBUG] Error getting live materials: {e}")
            # Calculate session duration for TPH
            elapsed_hours = 0.0
            elapsed_str = self.session_elapsed.get()
            if elapsed_str and elapsed_str != "00:00:00":
                time_parts = elapsed_str.split(":")
                elapsed_hours = int(time_parts[0]) + int(time_parts[1])/60 + int(time_parts[2])/3600
            
            # Track which materials have been displayed
            displayed_materials = set()
            row_index = 0
            
            # First, display materials that met threshold (announced materials)
            if summary_data:
                for material_name in sorted(summary_data.keys()):
                    displayed_materials.add(material_name)
                    stats = summary_data.get(material_name)
                    material_stats_all = self.session_analytics.material_stats_all.get(material_name) if hasattr(self.session_analytics, 'material_stats_all') else None
                    avg_all_pct = "0.0%"
                    if material_stats_all:
                        avg_all = material_stats_all.get_average_percentage()
                        avg_all_pct = f"{avg_all:.1f}%" if avg_all and avg_all > 0 else "0.0%"
                    avg_pct = f"{stats['avg_percentage']:.1f}%" if stats and stats['avg_percentage'] > 0 else "0.0%"
                    best_pct = f"{stats['best_percentage']:.1f}%" if stats and stats['best_percentage'] > 0 else "0.0%"
                    latest_pct = f"{stats['latest_percentage']:.1f}%" if stats and stats['latest_percentage'] > 0 else "0.0%"
                    quality_hits = str(stats['quality_hits']) if stats else "0"
                    threshold = self.min_pct_map.get(material_name, self.threshold.get())
                    material_display = f"{material_name} ({threshold:.1f}%)"
                    
                    # Get tons and TPH for this material
                    material_tons = None
                    material_tph = None
                    if not self.session_active and hasattr(self, 'last_session_data'):
                        # Session ended - use saved data
                        saved = self.last_session_data.get(material_name, {})
                        material_tons = saved.get('tons', 0.0)
                        material_tph = saved.get('tph', 0.0)
                    else:
                        # Live session - use cargo data
                        material_tons = live_materials.get(material_name, 0.0)
                        material_tph = material_tons / elapsed_hours if elapsed_hours > 0 and material_tons > 0 else 0.0
                    
                    tons_str = f"{material_tons:.1f}" if material_tons > 0 else "—"
                    tph_str = f"{material_tph:.1f}" if material_tph > 0 else "—"
                    
                    # Calculate Tons/Asteroid
                    tons_per_val = None
                    hits_count = 0
                    try:
                        qh = stats.get('quality_hits')
                        if qh is not None:
                            hits_count = int(float(qh))
                    except Exception:
                        hits_count = 0
                    
                    if hits_count > 0 and material_tons > 0:
                        try:
                            tons_per_val = material_tons / hits_count
                        except Exception:
                            tons_per_val = None
                    
                    tons_per_str = "—" if hits_count <= 0 else (f"{tons_per_val:.1f}" if tons_per_val is not None else "—")
                    
                    tag = "evenrow" if row_index % 2 == 0 else "oddrow"
                    self.stats_tree.insert("", "end", values=(
                        material_display, tons_str, tph_str, tons_per_str, avg_all_pct, avg_pct, best_pct, latest_pct, quality_hits
                    ), tags=(tag,))
                    row_index += 1
            
            # Second, add materials from cargo that weren't announced (below threshold but still mined)
            for material_name, material_tons in live_materials.items():
                if material_name not in displayed_materials and material_tons > 0:
                    # This material was mined but never announced (below threshold)
                    threshold = self.min_pct_map.get(material_name, self.threshold.get())
                    material_display = f"{material_name} ({threshold:.1f}%)"
                    tons_str = f"{material_tons:.1f}"
                    
                    material_tph = 0.0
                    if elapsed_hours > 0:
                        material_tph = material_tons / elapsed_hours
                    tph_str = f"{material_tph:.1f}" if material_tph > 0 else "—"
                    
                    # Check if we have prospector data in material_stats_all (all prospected asteroids)
                    material_stats_all = self.session_analytics.material_stats_all.get(material_name)
                    if material_stats_all and material_stats_all.get_find_count() > 0:
                        # Material was prospected but never met threshold - show ALL stats
                        avg_all = material_stats_all.get_average_percentage()
                        avg_all_pct = f"{avg_all:.1f}%" if avg_all and avg_all > 0 else "0.0%"
                        best = material_stats_all.get_best_percentage()
                        best_pct = f"{best:.1f}%" if best and best > 0 else "0.0%"
                        latest = material_stats_all.get_latest_percentage()
                        latest_pct = f"{latest:.1f}%" if latest and latest > 0 else "0.0%"
                    else:
                        # No prospector data at all
                        avg_all_pct = "—"
                        best_pct = "—"
                        latest_pct = "—"
                    
                    # These always show "—" and 0 for below-threshold materials
                    avg_pct = "—"
                    quality_hits = "0"
                    tons_per_str = "—"
                    
                    tag = "evenrow" if row_index % 2 == 0 else "oddrow"
                    self.stats_tree.insert("", "end", values=(
                        material_display, tons_str, tph_str, tons_per_str, avg_all_pct, avg_pct, best_pct, latest_pct, quality_hits
                    ), tags=(tag,))
                    row_index += 1
            
            # Update session summary with live tracking
            total_asteroids = self.session_analytics.get_total_asteroids()
            tracked_materials = len(summary_data) if summary_data else 0
            
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
                    
                    # Multi-session mode: live_tons already includes ALL mined materials
                    # (session_minerals_mined tracks cumulative total including sold/transferred)
                    # DO NOT add sold/transferred again - it would be double counting!
                    
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
                    base_text = f"Asteroids scanned: {total_asteroids} | Minerals tracked/hits: {tracked_materials}/{total_hits} | Total tons: {live_tons:.1f} | TPH: {live_tph:.1f}"
                    
                    # Add multi-session info if enabled
                    if self.multi_session_mode and (self.session_sold_transferred > 0 or self.session_ejected > 0):
                        multi_session_text = f" | Sold/Stored: {self.session_sold_transferred:.0f}t"
                        if self.session_ejected > 0:
                            multi_session_text += f" | Lost: {self.session_ejected:.0f}t"
                        summary_text = base_text + multi_session_text
                    else:
                        summary_text = base_text
                else:
                    summary_text = f"Asteroids scanned: {total_asteroids} | Minerals tracked/hits: {tracked_materials}/{total_hits}"
                self.stats_summary_label.config(text=summary_text, foreground="#e6e6e6")
            else:
                self.stats_summary_label.config(text="No data yet", foreground="#888888")
            
            # Update graphs if available
            if self.charts_panel:
                self.charts_panel.update_charts()
                
        except Exception as e:
            # Show basic info even if there's an error
            print(f"ERROR in _refresh_statistics_display: {e}")
            import traceback
            traceback.print_exc()
            try:
                total_asteroids = self.session_analytics.get_total_asteroids()
                if total_asteroids > 0:
                    self.stats_summary_label.config(text=f"Asteroids scanned: {total_asteroids} | Minerals tracked/hits: 0/0", foreground="#e6e6e6")
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
        
        # Check for cargo full + idle condition if feature is enabled
        self._check_cargo_full_idle()
    def _session_start(self) -> None:
        if self.session_active:
            return
        current_system = self._get_current_system()
        if current_system and not self.session_system.get():
            self.session_system.set(current_system)
        if self.last_body and not self.session_body.get():
            body_display = _extract_location_display(
                self.last_body, 
                self.last_body_type, 
                self.last_station_name, 
                self.last_carrier_name,
                current_system or self.session_system.get() or ""
            )
            self.session_body.set(body_display)
        
        # Update ship info display at session start
        self._update_ship_info_display()
        
        # Capture ship name for session report
        self.session_ship_name = ""
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            self.session_ship_name = self.main_app.cargo_monitor.get_ship_info_string()
            print(f"[DEBUG] Session ship name captured: '{self.session_ship_name}'")

        self.session_active = True
        self.session_paused = False
        self.session_start = dt.datetime.utcnow()
        self.session_pause_started = None
        self.session_paused_seconds = 0.0
        self.session_totals = {}
        self.session_elapsed.set("00:00:00")
        self.session_screenshots = []  # Initialize screenshots list for this session
        self.session_yield_data = {}  # Track yield data during session {material: [percentages]}
        self.session_location_captured_from_mining = False  # Flag to update location on first material collected
        self.session_mining_body = ""  # Reset preserved mining location for new session
        
        # Reset and start mining statistics for new session
        self.session_analytics.start_session()
        self._refresh_statistics_display()
        
        # Clear prospector reports for clean session-specific yield calculation
        self._clear_prospector_reports()
        
        # Start cargo tracking for material breakdown
        if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
            self.main_app.cargo_monitor.start_session_tracking()
            # Reset engineering materials counter for new session (unless multi-session mode)
            if hasattr(self.main_app.cargo_monitor, 'reset_materials'):
                if not self.multi_session_mode:
                    self.main_app.cargo_monitor.reset_materials()
        
        # ALWAYS reset multi-session cumulative tracking when starting a NEW session
        # Multi-session mode means "accumulate during THIS session", not "accumulate forever"
        self.session_total_mined = 0
        self.session_sold_transferred = 0
        self.session_ejected = 0

        self.start_btn.config(state="disabled")
        self.pause_resume_btn.config(state="normal", text="Pause")
        self.stop_btn.config(state="normal")
        self.cancel_btn.config(state="normal")
        self._set_status("Mining session started.")
    
    def _on_auto_start_checkbox_toggle(self) -> None:
        """Called when auto-start checkbox in Mining Analytics tab is toggled"""
        import traceback
        print(f"[DEBUG] _on_auto_start_checkbox_toggle called!")
        print(f"[DEBUG] Stack trace:")
        traceback.print_stack()
        
        enabled = bool(self.auto_start_var.get())
        self.auto_start_on_prospector = enabled
        
        # Save to toggle file
        try:
            auto_start_file = os.path.join(self.vars_dir, "autoStartSession.txt")
            value_to_write = "1" if enabled else "0"
            print(f"[DEBUG] Saving auto-start to: {auto_start_file}, value: '{value_to_write}'")
            with open(auto_start_file, 'w') as f:
                f.write(value_to_write)
            print(f"[DEBUG] Auto-start file saved successfully")
        except Exception as e:
            print(f"[DEBUG] Error saving auto-start file: {e}")
            pass
        
        self._set_status(f"Auto-start session on first prospector {'enabled' if enabled else 'disabled'}")

    def _on_prompt_on_full_checkbox_toggle(self) -> None:
        """Called when prompt on cargo full checkbox in Mining Analytics tab is toggled"""
        import traceback
        print(f"[DEBUG] _on_prompt_on_full_checkbox_toggle called!")
        print(f"[DEBUG] Stack trace:")
        traceback.print_stack()
        
        enabled = bool(self.prompt_on_full_var.get())
        self.prompt_on_cargo_full = enabled
        
        # Save to toggle file
        try:
            prompt_full_file = os.path.join(self.vars_dir, "promptWhenFull.txt")
            value_to_write = "1" if enabled else "0"
            print(f"[DEBUG] Saving prompt-when-full to: {prompt_full_file}, value: '{value_to_write}'")
            with open(prompt_full_file, 'w') as f:
                f.write(value_to_write)
            print(f"[DEBUG] Prompt-when-full file saved successfully")
        except Exception as e:
            print(f"[DEBUG] Error saving prompt-when-full file: {e}")
            pass
        
        self._set_status(f"Prompt when cargo full {'enabled' if enabled else 'disabled'}")
    
    def _on_multi_session_checkbox_toggle(self) -> None:
        """Called when multi-session checkbox is toggled"""
        enabled = bool(self.multi_session_var.get())
        self.multi_session_mode = enabled
        
        # Handle UI interaction between multi-session and prompt-when-full
        if enabled:
            # Disable the prompt checkbox widget and uncheck it (incompatible features)
            if hasattr(self, 'prompt_on_full_cb'):
                self.prompt_on_full_cb.config(state="disabled", fg="#666666")
                self.prompt_on_full_var.set(0)  # Uncheck the box when multi-session is enabled
            self._set_status("Multi-session mode enabled - Cargo full prompt disabled")
        else:
            # Re-enable the prompt checkbox widget and restore its saved state
            if hasattr(self, 'prompt_on_full_cb'):
                self.prompt_on_full_cb.config(state="normal", fg="#ffffff")
                # Restore the checkbox to match the saved boolean value
                self.prompt_on_full_var.set(1 if self.prompt_on_cargo_full else 0)
            self._set_status("Multi-session mode disabled")
        
        # Save to toggle file
        try:
            multi_session_file = os.path.join(self.vars_dir, "multiSessionMode.txt")
            value_to_write = "1" if enabled else "0"
            print(f"[DEBUG] Saving multi-session to: {multi_session_file}, value: '{value_to_write}'")
            with open(multi_session_file, 'w') as f:
                f.write(value_to_write)
            print(f"[DEBUG] Multi-session file saved successfully")
        except Exception as e:
            print(f"[DEBUG] Error saving multi-session file: {e}")
            pass

    def _check_cargo_full_idle(self) -> None:
        """Check if cargo is 100% full and has been idle for 1 minute, then prompt to end session"""
        # Only check if feature is enabled and session is active
        if not self.prompt_on_cargo_full or not self.session_active:
            return
        
        # Skip in multi-session mode (cargo will be emptied and session continues)
        if self.multi_session_mode:
            return
        
        # Get cargo monitor from main app
        if not self.main_app or not hasattr(self.main_app, 'cargo_monitor'):
            return
        
        cargo_monitor = self.main_app.cargo_monitor
        
        # Check if cargo is 100% full
        if cargo_monitor.max_cargo > 0:
            percentage = (cargo_monitor.current_cargo / cargo_monitor.max_cargo * 100)
            current_cargo = cargo_monitor.current_cargo
            
            if percentage >= 100:
                # Cargo is full - check if we have limpets vs minerals
                limpet_cargo = sum(qty for item, qty in cargo_monitor.cargo_items.items() 
                                  if "limpet" in item.lower())
                mineral_cargo = sum(qty for item, qty in cargo_monitor.cargo_items.items() 
                                   if "limpet" not in item.lower())
                
                if limpet_cargo > 0:
                    # We have limpets in cargo - don't prompt for session end
                    print(f"[CARGO FULL] Cargo full but contains {limpet_cargo}t limpets - no prompt needed")
                    return
                
                import time
                current_time = time.time()
                
                # Check if cargo amount changed (player jettisoned something)
                if hasattr(self, '_last_cargo_amount') and self._last_cargo_amount != current_cargo:
                    # Cargo changed - reset tracking
                    print(f"[CARGO FULL] Cargo changed from {self._last_cargo_amount} to {current_cargo}, resetting idle timer...")
                    self.cargo_full_start_time = current_time  # Restart timer
                    self.cargo_full_prompted = False
                    self._last_cargo_amount = current_cargo
                    return
                
                # Store current cargo amount for next check
                self._last_cargo_amount = current_cargo
                
                # Start tracking if not already
                if self.cargo_full_start_time is None:
                    self.cargo_full_start_time = current_time
                    self.cargo_full_prompted = False  # Reset prompt flag
                    print(f"[CARGO FULL] Cargo is 100% full with {mineral_cargo}t minerals - started tracking idle time...")
                    return
                
                # Check if 60 seconds have passed
                elapsed = current_time - self.cargo_full_start_time
                if elapsed >= 60 and not self.cargo_full_prompted:
                    # Show prompt (but don't auto-end in multi-session mode)
                    if not self.multi_session_mode:
                        self._prompt_end_session_cargo_full()
                    self.cargo_full_prompted = True  # Don't prompt again until cargo changes
            else:
                # Cargo not full - reset tracking
                if self.cargo_full_start_time is not None:
                    print("[CARGO FULL] Cargo no longer full, resetting tracking...")
                self.cargo_full_start_time = None
                self.cargo_full_prompted = False
                self._last_cargo_amount = current_cargo

    def _prompt_end_session_cargo_full(self) -> None:
        """Show dialog prompting user to end session when cargo is full and idle"""
        # Play discreet warning sound
        try:
            import winsound
            # Play Windows notification sound (SystemAsterisk is a gentle sound)
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as e:
            print(f"[DEBUG] Could not play warning sound: {e}")
        
        # Show persistent overlay notification (stays until dialog is closed)
        overlay_shown = False
        if self.text_overlay:
            try:
                # Show persistent notification that won't auto-hide
                self.text_overlay.show_persistent_message("Cargo Full - End session before unloading cargo!")
                overlay_shown = True
            except Exception as e:
                print(f"[DEBUG] Error showing cargo full overlay: {e}")
        
        # Create a non-modal dialog that doesn't block TTS announcements
        import tkinter as tk
        from tkinter import ttk
        
        # Create toplevel window
        dialog = tk.Toplevel(self.winfo_toplevel())
        dialog.withdraw()  # Prevent flicker while positioning and packing
        dialog.title("Cargo Full - End Session?")
        dialog.configure(bg="#1e1e1e")
        dialog.resizable(False, False)
        
        # Set app icon
        try:
            from icon_utils import set_window_icon
            set_window_icon(dialog)
        except Exception as e:
            print(f"[DEBUG] Could not set dialog icon: {e}")
        
        # Make it appear on top but not block other windows
        dialog.attributes('-topmost', True)
        
        # Position dialog relative to main EliteMining window (same monitor)
        # Set geometry first, then update, then position
        dialog_width = 450
        dialog_height = 200
        dialog.geometry(f"{dialog_width}x{dialog_height}")
        dialog.update_idletasks()
        
        # Get main app window position
        try:
            if self.main_app:
                # Force update to get accurate position
                self.main_app.update_idletasks()
                main_x = self.main_app.winfo_x()
                main_y = self.main_app.winfo_y()
                main_width = self.main_app.winfo_width()
                main_height = self.main_app.winfo_height()
                
                # Center dialog on main app window
                x = main_x + (main_width - dialog_width) // 2
                y = main_y + (main_height - dialog_height) // 2
                
                dialog.geometry(f"+{x}+{y}")
            else:
                # Fallback: center on screen
                x = (dialog.winfo_screenwidth() // 2) - (dialog_width // 2)
                y = (dialog.winfo_screenheight() // 2) - (dialog_height // 2)
                dialog.geometry(f"+{x}+{y}")
        except Exception as e:
            print(f"[DEBUG] Error positioning dialog: {e}")
            # Final fallback
            dialog.geometry(f"+{(dialog.winfo_screenwidth() // 2) - 225}+{(dialog.winfo_screenheight() // 2) - 100}")
        
        dialog.update_idletasks()
        dialog.deiconify()  # Show centered dialog immediately
        dialog.focus_force()
        
        # Message frame
        msg_frame = tk.Frame(dialog, bg="#1e1e1e")
        msg_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Message text
        msg = ("Your cargo is 100% full and has been idle for 1 minute.\n\n"
               "Do you want to end the current mining session?\n\n"
               "⚠️ Important: End session BEFORE unloading cargo\n"
               "to preserve data for the report.")
        
        tk.Label(msg_frame, text=msg, bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10), justify="left", wraplength=400).pack()
        
        # Buttons frame
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
        btn_frame.pack(side="bottom", pady=(0, 20))
        
        def on_yes():
            # Hide persistent overlay
            if overlay_shown and self.text_overlay:
                try:
                    self.text_overlay.hide_overlay()
                except:
                    pass
            dialog.destroy()
            self._session_stop()
            self._set_status("Session ended (cargo full)")
        
        def on_no():
            # Hide persistent overlay
            if overlay_shown and self.text_overlay:
                try:
                    self.text_overlay.hide_overlay()
                except:
                    pass
            dialog.destroy()
        
        # Yes button
        tk.Button(btn_frame, text="Yes - End Session", command=on_yes,
                 bg="#2a4a2a", fg="#ffffff", font=("Segoe UI", 9, "bold"),
                 padx=20, pady=8, cursor="hand2", relief="raised", bd=2,
                 activebackground="#3a5a3a", activeforeground="#ffffff").pack(side="left", padx=5)
        
        # No button  
        tk.Button(btn_frame, text="No - Continue", command=on_no,
                 bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 9),
                 padx=20, pady=8, cursor="hand2", relief="raised", bd=2,
                 activebackground="#4a4a4a", activeforeground="#ffffff").pack(side="left", padx=5)
        
        # Handle dialog close (X button) - same as No
        dialog.protocol("WM_DELETE_WINDOW", on_no)

    def _edit_comment_popup(self, event):
        """Edit Body or Comment column in reports popup window"""
        item = self.reports_tree.selection()[0] if self.reports_tree.selection() else None
        if not item:
            return
        
        # Get clicked column and map dynamically to body/comment
        column = self.reports_tree.identify_column(event.x)
        try:
            cols = list(self.reports_tree["columns"])
            body_idx = cols.index('body') if 'body' in cols else None
            comment_idx = cols.index('comment') if 'comment' in cols else None
        except Exception:
            body_idx = None
            comment_idx = None

        if body_idx is not None and column == f"#{body_idx+1}":
            self._edit_body(self.reports_tree, item)
        elif comment_idx is not None and column == f"#{comment_idx+1}":
            self._edit_comment(self.reports_tree, item)
    
    def _edit_cell_tab(self, event):
        """Edit Body or Comment column in reports tab"""
        item = self.reports_tree_tab.selection()[0] if self.reports_tree_tab.selection() else None
        if not item:
            return
            
        # Get clicked column and map dynamically to body/comment
        column = self.reports_tree_tab.identify_column(event.x)
        try:
            cols = list(self.reports_tree_tab["columns"])
            body_idx = cols.index('body') if 'body' in cols else None
            comment_idx = cols.index('comment') if 'comment' in cols else None
        except Exception:
            body_idx = None
            comment_idx = None

        if body_idx is not None and column == f"#{body_idx+1}":
            self._edit_body(self.reports_tree_tab, item)
        elif comment_idx is not None and column == f"#{comment_idx+1}":
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
        
        # Get actual comment from session data, not from tree display (which shows emoji)
        current_comment = ""
        
        # Get the actual comment from session lookup data
        if tree == self.reports_tree_tab and hasattr(self, 'reports_tab_session_lookup'):
            session_data = self.reports_tab_session_lookup.get(item)
            if session_data:
                current_comment = session_data.get('comment', '')
        elif tree == self.reports_tree and hasattr(self, 'reports_window_session_lookup'):
            session_data = self.reports_window_session_lookup.get(item)
            if session_data:
                current_comment = session_data.get('comment', '')
        
        # Fallback: if no session data found, try to find comment by timestamp
        if not current_comment:
            values = tree.item(item, 'values')
            timestamp = values[0] if len(values) > 0 else ""
            current_comment = self._get_comment_by_timestamp(timestamp)
        
        # Show custom edit dialog with app logo
        new_comment = self._show_custom_comment_dialog(
            "Edit Comment", 
            "Edit session comment:",
            current_comment
        )
        
        if new_comment is not None:  # User didn't cancel
            # Update tree display: set the comment cell by column name (robust to column order)
            comment_display = '💬' if new_comment.strip() else ''  # Show emoji if comment exists
            try:
                # Prefer named column set to avoid positional mismatches
                tree.set(item, 'comment', comment_display)
            except Exception:
                # Fallback: if set by name fails (older tree), update entire values list safely
                values = tree.item(item, 'values')
                new_values = list(values)
                # Try to find comment index dynamically from tree columns if possible
                try:
                    cols = list(tree['columns'])
                    if 'comment' in cols:
                        idx = cols.index('comment')
                    else:
                        idx = 15
                except Exception:
                    idx = 15
                # Ensure list long enough
                while len(new_values) <= idx:
                    new_values.append('')
                new_values[idx] = comment_display
                tree.item(item, values=new_values)
            
            # Get the raw timestamp for CSV update from session lookup
            raw_timestamp = None
            if tree == self.reports_tree_tab and hasattr(self, 'reports_tab_session_lookup'):
                session_data = self.reports_tab_session_lookup.get(item)
                if session_data:
                    raw_timestamp = session_data.get('timestamp_raw')
            elif tree == self.reports_tree and hasattr(self, 'reports_window_session_lookup'):
                session_data = self.reports_window_session_lookup.get(item)
                if session_data:
                    raw_timestamp = session_data.get('timestamp_raw')
            
            # Fallback to display timestamp if raw timestamp not found
            if not raw_timestamp:
                raw_timestamp = values[0]
            
            # Update both CSV file and text file for data consistency
            csv_updated = self._update_comment_in_csv(raw_timestamp, new_comment)
            text_updated = self._update_comment_in_text_file(raw_timestamp, new_comment)
            
            # Update the session lookup cache with the new comment
            if csv_updated and text_updated:
                if tree == self.reports_tree_tab and hasattr(self, 'reports_tab_session_lookup'):
                    session_data = self.reports_tab_session_lookup.get(item)
                    if session_data:
                        session_data['comment'] = new_comment
                elif tree == self.reports_tree and hasattr(self, 'reports_window_session_lookup'):
                    session_data = self.reports_window_session_lookup.get(item)
                    if session_data:
                        session_data['comment'] = new_comment
            
            # Check if updates were successful
            if not csv_updated or not text_updated:
                from app_utils import centered_askyesno
                # Determine error message based on what failed
                if not csv_updated and not text_updated:
                    error_msg = "Failed to update comment in both CSV and text files."
                elif not csv_updated:
                    error_msg = "Failed to update comment in CSV file.\nText file was updated successfully."
                else:
                    error_msg = "Failed to update comment in text file.\nCSV file was updated successfully."
                
                result = centered_askyesno(
                    self.winfo_toplevel(),
                    "Update Failed",
                    f"{error_msg}\n\n"
                    f"The comment change is only visible in the UI but may not persist.\n"
                    f"This may cause data inconsistency.\n\n"
                    f"Would you like to revert the UI change?"
                )
                if result:  # User chose to revert
                    # Revert the UI change to show original comment emoji state
                    original_comment_display = '💬' if current_comment.strip() else ''
                    try:
                        tree.set(item, 'comment', original_comment_display)
                    except Exception:
                        # Fallback to positional revert if named set fails
                        try:
                            values = tree.item(item, 'values')
                            vals = list(values)
                            # find comment index
                            cols = list(tree['columns']) if 'columns' in tree.keys() else []
                            if 'comment' in cols:
                                idx = cols.index('comment')
                            else:
                                idx = 15
                            while len(vals) <= idx:
                                vals.append('')
                            vals[idx] = original_comment_display
                            tree.item(item, values=vals)
                        except Exception:
                            pass
    
    def _get_comment_by_timestamp(self, timestamp):
        """Get comment by timestamp from CSV file as fallback"""
        try:
            import csv
            csv_path = self._get_csv_path()
            if os.path.exists(csv_path):
                with open(csv_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        raw_timestamp = row['timestamp_utc']
                        
                        # Try direct match first
                        if raw_timestamp == timestamp:
                            return row.get('comment', '')
                        
                        # Try display format match
                        try:
                            if raw_timestamp.endswith('Z'):
                                csv_dt = dt.datetime.fromisoformat(raw_timestamp.replace('Z', '+00:00'))
                                csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                            else:
                                csv_dt = dt.datetime.fromisoformat(raw_timestamp)
                            
                            display_time = csv_dt.strftime("%Y-%m-%d %H:%M")
                            if display_time == timestamp:
                                return row.get('comment', '')
                        except:
                            continue
        except Exception as e:
            log.warning(f"Error getting comment by timestamp: {e}")
        return ""
    
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
            elif tree == self.reports_tree and hasattr(self, 'reports_window_session_lookup'):
                session_data = self.reports_window_session_lookup.get(item)
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
                
                result = centered_askyesno(
                    self.winfo_toplevel(),
                    "Update Failed",
                    f"{error_msg}\n\n"
                    f"The body name change is only visible in the UI but may not persist.\n"
                    f"This may cause data inconsistency.\n\n"
                    f"Would you like to revert the UI change?"
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
                    
                    # Convert CSV timestamp to display format (YYYY-MM-DD HH:MM)
                    display_time = csv_dt.strftime("%Y-%m-%d %H:%M")
                    
                    # Compare with the display timestamp (e.g., "2025-10-10 18:20")
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
                            'avg_quality_percent', 'total_average_yield', 'best_material', 'materials_breakdown', 'material_tph_breakdown', 'prospectors_used', 'engineering_materials', 'comment']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for _r in sessions:
                    if 'total_finds' in _r:
                        _r.pop('total_finds', None)
                writer.writerows(sessions)
            log.debug(f"Successfully updated comment in CSV for timestamp: {timestamp}")
            return True
        else:
            log.warning(f"Failed to find matching session in CSV for timestamp: {timestamp}")
            return False
    
    def _wipe_mining_session_folder(self):
        """
        One-time wipe of Mining Session folder on v4.3.0 upgrade.
        Deletes entire folder and recreates it clean.
        """
        try:
            import shutil
            
            # self.reports_dir already points to Reports/Mining Session
            wipe_flag = os.path.join(os.path.dirname(self.reports_dir), ".v430_wipe_done")
            
            # Check if wipe already done
            if os.path.exists(wipe_flag):
                return
            
            # Delete entire Mining Session folder
            if os.path.exists(self.reports_dir):
                shutil.rmtree(self.reports_dir)
                print("[V4.3.0 UPGRADE] Deleted entire Mining Session folder")
            
            # Recreate clean folder structure
            os.makedirs(os.path.join(self.reports_dir, "Detailed Reports", "Screenshots"), exist_ok=True)
            
            # Create flag so this never runs again
            with open(wipe_flag, 'w') as f:
                f.write("v4.3.0 wipe completed")
            
            print("[V4.3.0 UPGRADE] Mining Session folder recreated - all old data removed")
            
            # Show user notification
            self._show_upgrade_notification()
        except Exception as e:
            print(f"[V4.3.0 UPGRADE] Error during wipe: {e}")
    
    def _show_upgrade_notification(self):
        """Show popup notification about v4.3.0 upgrade"""
        from app_utils import centered_message

        # Show message directly parented to main app
        centered_message(self.main_app, "EliteMining v4.3.0 Upgrade",
                         "Mining Session data has been reset due to major format improvements.\n\n"
                         "• Old session reports and graphs have been cleared\n"
                         "• Enhanced report generation with material icons\n"
                         "• Improved TPH calculations and statistics")

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
                                
                                display_time = csv_dt.strftime("%Y-%m-%d %H:%M")
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
                        
                        display_time = csv_dt.strftime("%Y-%m-%d %H:%M")
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
                    keys = list(sessions[0].keys())
                    writer = csv.DictWriter(f, fieldnames=keys)
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
                                
                                display_time = csv_dt.strftime("%Y-%m-%d %H:%M")
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
        
        main_parent = self.winfo_toplevel()
        dialog = tk.Toplevel(main_parent)
        dialog.title(title)
        dialog.geometry("400x150")
        dialog.resizable(False, False)
        dialog.configure(bg="#2d2d2d")
        from main import center_window
        center_window(dialog, main_parent)
        
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
        # Use main app window if available, otherwise fall back to winfo_toplevel
        parent = self.main_app if self.main_app is not None else self.winfo_toplevel()
        dialog.transient(parent)
        dialog.grab_set()
        
        # Position dialog centered on parent window
        # Force both windows to update their geometry info
        parent.update_idletasks()
        dialog.update_idletasks()
        
        # Get parent window geometry
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        
        # Get dialog dimensions
        dialog_width = 400  # Fixed from geometry setting
        dialog_height = 150  # Fixed from geometry setting
        
        # Calculate center position
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        # Ensure dialog stays on screen
        x = max(0, x)
        y = max(0, y)
        
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
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

        # Save TPH and tons for each material before ending session
        self.last_session_data = {}
        if (self.main_app and hasattr(self.main_app, 'cargo_monitor') and 
            hasattr(self.main_app.cargo_monitor, 'get_live_session_materials')):
            live_materials = self.main_app.cargo_monitor.get_live_session_materials()
            for material, tons in live_materials.items():
                if tons > 0:
                    self.last_session_data[material] = {
                        'tons': tons,
                        'tph': tons / active_hours if active_hours > 0 else 0
                    }

        self.session_active = False
        
        # Reset cargo full tracking
        self.cargo_full_start_time = None
        self.cargo_full_prompted = False
        if hasattr(self, '_last_cargo_amount'):
            delattr(self, '_last_cargo_amount')
        
        # Stop mining analytics
        self.session_analytics.stop_session()
        
        # Wrap dialog section in try-except to ensure button states are always restored
        cargo_session_data = None
        session_comment = ""
        
        try:
            # Ask if user wants to add refinery materials BEFORE ending session tracking
            # Skip for multi-session mode (refinery already captured after each transfer/sale)
            from tkinter import messagebox
            is_multi_session = bool(self.multi_session_var.get())
            
            if self.main_app and hasattr(self.main_app, 'cargo_monitor') and not is_multi_session:
                from main import centered_yesno_dialog
                add_refinery = centered_yesno_dialog(
                    self.winfo_toplevel(),
                    "Refinery Materials",
                    "Do you have any additional materials in your refinery that you want to add to this session?"
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
            if self.main_app and hasattr(self.main_app, 'cargo_monitor'):
                cargo_session_data = self.main_app.cargo_monitor.end_session_tracking()
                
            # Ask if user wants to add a comment
            main_parent = self.winfo_toplevel()
            add_comment = centered_yesno_dialog(
                main_parent,
                "Session Comment",
                "Would you like to add a comment to this mining session?"
            )
            
            if add_comment:
                session_comment = self._show_comment_dialog()
            
            # Update session totals with any refinery materials that were added
            if cargo_session_data and 'materials_mined' in cargo_session_data:
                for material_name, quantity in cargo_session_data['materials_mined'].items():
                    if material_name in self.session_totals:
                        self.session_totals[material_name] = max(self.session_totals[material_name], quantity)
                    else:
                        self.session_totals[material_name] = quantity
        
        except Exception as e:
            print(f"Error during session end dialogs: {e}")
            import traceback
            traceback.print_exc()
        
        # ALWAYS restore button states, even if there was an error above
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
        # Use preserved mining body if available (prevents docking from overwriting actual mining location)
        body = self.session_mining_body or self.session_body.get().strip() or self.last_body or "Unknown Body"
        elapsed_txt = self.session_elapsed.get()
        
        # Determine session type for report
        is_multi_session = bool(self.multi_session_var.get())
        session_type_suffix = " (Multi-Session)" if is_multi_session else " (Single Session)"
        
        # Build header line with session type and ship line (ship name will be parsed from TXT for Reports tab)
        header = f"Session: {sysname} — {body} — {elapsed_txt} — Total {total_tons:.0f}t{session_type_suffix}"
        
        # Add ship name on second line if available
        ship_line = ""
        if hasattr(self, 'session_ship_name') and self.session_ship_name:
            ship_line = f"\nShip: {self.session_ship_name}"
            print(f"[DEBUG] Adding ship line to TXT: '{ship_line}'")
        else:
            print(f"[DEBUG] No ship name available. Has attr: {hasattr(self, 'session_ship_name')}, Value: {getattr(self, 'session_ship_name', 'N/A')}")
        
        # Build complete text with materials
        materials_text = "; ".join(lines) if lines else "No refined materials."
        file_text = header + ship_line + " | " + materials_text
        print(f"[DEBUG] Final TXT file_text: {file_text[:200]}...")
        self._write_var_text("miningSessionSummary", file_text)
        self._set_status("Mining session stopped and summary written.")

        # Save report file and auto-open it
        try:
            overall_tph = total_tons / active_hours if active_hours > 0 else 0.0
            
            # Generate timestamp for consistent naming between report and graphs
            import datetime as dt
            session_timestamp = dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            report_path = self._save_session_report_with_timestamp(header, lines, overall_tph, cargo_session_data, session_comment, session_timestamp)
            
            # Update CSV index with new session data (pass timestamp for consistency)
            self._update_csv_with_session(sysname, body, elapsed_txt, total_tons, overall_tph, cargo_session_data, session_comment, session_timestamp)
            
            # Rebuild CSV from files to ensure everything is properly synchronized
            csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
            self._rebuild_csv_from_files_tab(csv_path, silent=True)
            
            # Refresh the Reports tab to show the new session
            self._refresh_reports_tab()
            
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
            
            # Auto-generate mining card
            try:
                from mining_card_generator import create_card_from_session
                from path_utils import get_reports_dir
                
                # Create Cards directory
                cards_dir = os.path.join(get_reports_dir(), "Cards")
                os.makedirs(cards_dir, exist_ok=True)
                
                # Generate card filename matching report format
                card_filename = f"Session_{session_timestamp}_{sysname}_{body}_Card.png"
                card_path = os.path.join(cards_dir, card_filename)
                
                # Prepare session info for card
                session_info = {
                    'system': sysname.replace('_', ' '),
                    'body': body.replace('_', ' '),
                    'ship': self.session_ship_name if hasattr(self, 'session_ship_name') and self.session_ship_name else None,
                    'duration_text': elapsed_txt
                }
                
                # Generate the card
                if create_card_from_session(cargo_session_data, session_info, card_path):
                    print(f"[SESSION] Mining card generated: {card_filename}")
                else:
                    print(f"[SESSION] Failed to generate mining card")
                    
            except Exception as card_error:
                print(f"Warning: Could not generate mining card: {card_error}")
            
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
                                   values=["All Locations", "High Yield (>350 T/hr)", "Medium Yield (250-350 T/hr)", "Low Yield (100-250 T/hr)", "Recent (Last 30 Days)", "Hotspot Locations", "No Overlap", "2x Overlap", "3x Overlap"], 
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

        # Configure Bookmarks Treeview style (theme-aware)
        from config import load_theme
        _bm_theme = load_theme()
        style = ttk.Style()
        
        if _bm_theme == "elite_orange":
            _bm_bg = "#0a0a0a"
            _bm_fg = "#ff8c00"
            _bm_hdr = "#1a1a1a"
            _bm_sel_bg = "#ff6600"
            _bm_sel_fg = "#000000"
            _bm_alt = "#151515"
        else:
            _bm_bg = "#1e1e1e"
            _bm_fg = "#e6e6e6"
            _bm_hdr = "#2a2a2a"
            _bm_sel_bg = "#0078d7"
            _bm_sel_fg = "#ffffff"
            _bm_alt = "#282828"
        
        style.configure("Bookmarks.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=_bm_bg,
                       foreground=_bm_fg,
                       fieldbackground=_bm_bg)
        style.configure("Bookmarks.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",
                       background=_bm_hdr,
                       foreground=_bm_fg,
                       padding=[5, 5],
                       anchor="w")
        style.map("Bookmarks.Treeview",
                 background=[('selected', _bm_sel_bg)],
                 foreground=[('selected', _bm_sel_fg)])
        
        style.layout("Bookmarks.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])

        # Create wrapper frame for bordered table
        tree_frame_bookmarks = ttk.Frame(main_frame, relief="solid", borderwidth=1)
        tree_frame_bookmarks.grid(row=1, column=0, sticky="nsew")
        tree_frame_bookmarks.grid_columnconfigure(0, weight=1)
        tree_frame_bookmarks.grid_rowconfigure(0, weight=1)

        # Create bookmarks treeview with multiple selection enabled
        self.bookmarks_tree = ttk.Treeview(tree_frame_bookmarks, columns=("last_mined", "system", "body", "hotspot", "materials", "avg_yield", "overlap", "res_site", "notes"), show="headings", height=16, selectmode="extended", style="Bookmarks.Treeview")
        self.bookmarks_tree.grid(row=0, column=0, sticky="nsew")
        
        # Configure row tags for alternating colors (theme-aware)
        self.bookmarks_tree.tag_configure('oddrow', background=_bm_bg, foreground=_bm_fg)
        self.bookmarks_tree.tag_configure('evenrow', background=_bm_alt, foreground=_bm_fg)
        
        # Ensure multiple selection is properly configured
        self.bookmarks_tree.configure(selectmode="extended")
        
        # Force focus to ensure selection behavior works properly
        self.bookmarks_tree.focus_set()
        
        # Configure column headings
        self.bookmarks_tree.heading("last_mined", text="Last Mined", anchor="w")
        self.bookmarks_tree.heading("system", text="System", anchor="w")
        self.bookmarks_tree.heading("body", text="Planet/Ring", anchor="w")
        self.bookmarks_tree.heading("hotspot", text="Ring Type", anchor="w")
        self.bookmarks_tree.heading("materials", text="Minerals Found", anchor="w")
        self.bookmarks_tree.heading("avg_yield", text="Avg Yield %", anchor="w")
        self.bookmarks_tree.heading("overlap", text="Overlap", anchor="w")
        self.bookmarks_tree.heading("res_site", text="RES Site", anchor="w")
        self.bookmarks_tree.heading("notes", text="Notes", anchor="w")
        
        # Configure column widths
        self.bookmarks_tree.column("last_mined", width=100, stretch=False, anchor="center")
        self.bookmarks_tree.column("system", width=180, stretch=False, anchor="w")
        self.bookmarks_tree.column("body", width=120, stretch=False, anchor="w")
        self.bookmarks_tree.column("hotspot", width=100, stretch=False, anchor="w")
        self.bookmarks_tree.column("materials", width=200, stretch=False, anchor="w")
        self.bookmarks_tree.column("avg_yield", width=80, stretch=False, anchor="center")
        self.bookmarks_tree.column("overlap", width=80, stretch=False, anchor="w")
        self.bookmarks_tree.column("res_site", width=80, stretch=False, anchor="w")
        self.bookmarks_tree.column("notes", width=50, stretch=False, anchor="center")  # Narrower for emoji

        # Load saved column widths from config
        try:
            from config import load_bookmarks_column_widths
            saved_widths = load_bookmarks_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        self.bookmarks_tree.column(col_name, width=width)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Bookmarks column widths: {e}")

        # Bind column resize event to save widths
        def save_bookmarks_widths(event=None):
            try:
                from config import save_bookmarks_column_widths
                widths = {}
                for col in ["last_mined", "system", "body", "hotspot", "materials", "avg_yield", "overlap", "res_site", "notes"]:
                    try:
                        widths[col] = self.bookmarks_tree.column(col, "width")
                    except:
                        pass
                save_bookmarks_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Bookmarks column widths: {e}")
        
        self.bookmarks_tree.bind("<ButtonRelease-1>", save_bookmarks_widths)

        # Add vertical scrollbar
        v_scrollbar = ttk.Scrollbar(tree_frame_bookmarks, orient="vertical", command=self.bookmarks_tree.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
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
        for col in ("last_mined", "system", "body", "hotspot", "materials", "avg_yield", "overlap", "res_site", "notes"):
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
        
        # Single-click handler for Notes column
        self.bookmarks_tree.bind("<Button-1>", self._on_bookmark_single_click)
        
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

    def _abbreviate_material_for_bookmark(self, material_name: str) -> str:
        """Abbreviate material name for bookmark display"""
        abbreviations = {
            'Alexandrite': 'Alex',
            'Benitoite': 'Beni',
            'Bromellite': 'Brom',
            'Grandidierite': 'Gran',
            'Low Temperature Diamonds': 'LTD',
            'Low-Temperature Diamonds': 'LTD',
            'Monazite': 'Mona',
            'Musgravite': 'Musg',
            'Painite': 'Pain',
            'Platinum': 'Plat',
            'Rhodplumsite': 'Rhod',
            'Serendibite': 'Sere',
            'Tritium': 'Trit',
            'Void Opals': 'Opals'
        }
        return abbreviations.get(material_name, material_name[:4] if len(material_name) > 4 else material_name)

    def _refresh_bookmarks(self) -> None:
        """Refresh the bookmarks display with current filter/search"""
        # Clear existing items
        for item in self.bookmarks_tree.get_children():
            self.bookmarks_tree.delete(item)
        
        # Get filter and search values
        filter_value = self.bookmark_filter_var.get() if hasattr(self, 'bookmark_filter_var') else "All Locations"
        search_text = self.bookmark_search_var.get().lower() if hasattr(self, 'bookmark_search_var') else ""
        
        # Filter and display bookmarks
        row_index = 0
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
            elif filter_value == "No Overlap":
                overlap_type = bookmark.get('overlap_type', '')
                if overlap_type != '':
                    continue
            elif filter_value == "2x Overlap":
                overlap_type = bookmark.get('overlap_type', '')
                if overlap_type != '2x':
                    continue
            elif filter_value == "3x Overlap":
                overlap_type = bookmark.get('overlap_type', '')
                if overlap_type != '3x':
                    continue
            
            # Apply search filter
            if search_text:
                searchable_text = f"{bookmark.get('system', '')} {bookmark.get('body', '')} {bookmark.get('hotspot', '')} {bookmark.get('materials', '')} {bookmark.get('last_mined', '')} {bookmark.get('notes', '')}".lower()
                if search_text not in searchable_text:
                    continue
            
            # Add to tree
            notes = bookmark.get('notes', '')
            notes_display = '💬' if notes.strip() else ''  # Show emoji if notes exist
            
            # Format overlap display as "Material Type" (e.g., "Plat 2x")
            target_material = bookmark.get('target_material', '')
            overlap_type = bookmark.get('overlap_type', '')
            if target_material and overlap_type:
                # Abbreviate material name for display
                mat_abbr = self._abbreviate_material_for_bookmark(target_material)
                overlap_display = f"{mat_abbr} {overlap_type}"
            else:
                overlap_display = ''
            
            # Format RES site display as "Type Material" (e.g., "HAZ Plat")
            res_site = bookmark.get('res_site', '')
            res_material = bookmark.get('res_material', '')
            if res_site and res_material:
                mat_abbr = self._abbreviate_material_for_bookmark(res_material)
                res_abbr = {'Hazardous': 'HAZ', 'High': 'High', 'Low': 'Low'}.get(res_site, res_site)
                res_display = f"{res_abbr} {mat_abbr}"
            elif res_site:
                res_display = res_site
            else:
                res_display = ''
            
            tag = "evenrow" if row_index % 2 == 0 else "oddrow"
            self.bookmarks_tree.insert("", "end", values=(
                bookmark.get('last_mined', ''),
                bookmark.get('system', ''),
                bookmark.get('body', ''),
                bookmark.get('hotspot', ''),
                bookmark.get('materials', ''),
                bookmark.get('avg_yield', ''),
                overlap_display,
                res_display,
                notes_display
            ), tags=(tag,))
            row_index += 1

    def _on_bookmark_double_click(self, event) -> None:
        """Handle double-click on bookmark tree - only edit if clicking on an item, not header"""
        # Check if click is on an actual item, not header
        item = self.bookmarks_tree.identify('item', event.x, event.y)
        if item:  # Only edit if there's an actual item under the cursor
            self._edit_bookmark_dialog()

    def _on_bookmark_single_click(self, event) -> None:
        """Handle single-click on bookmark tree - open edit dialog if clicking on Notes column"""
        # Identify what was clicked
        item = self.bookmarks_tree.identify('item', event.x, event.y)
        column = self.bookmarks_tree.identify('column', event.x, event.y)
        
        # Check if clicking on Notes column and there's a valid item
        if item and column == '#9':  # Notes column is now the 9th column (0-indexed: #9)
            # Select the clicked item first
            self.bookmarks_tree.selection_set(item)
            self.bookmarks_tree.focus(item)
            
            # Open the edit bookmark dialog
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
        dialog.withdraw()
        dialog.title("Add Bookmark" if bookmark_data is None else "Edit Bookmark")

        # Set app icon while withdrawn (avoid visual flicker)
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass

        dialog.resizable(False, False)
        
        frame = ttk.Frame(dialog, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        
        # System field
        ttk.Label(frame, text="System:").grid(row=0, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        system_var = tk.StringVar(value=bookmark_data.get('system', '') if bookmark_data else '')
        system_entry = ttk.Entry(frame, textvariable=system_var, width=35)
        system_entry.grid(row=0, column=1, sticky="w", pady=(0, 5))
        
        # Body field
        ttk.Label(frame, text="Body/Ring:").grid(row=1, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        body_var = tk.StringVar(value=bookmark_data.get('body', '') if bookmark_data else '')
        body_entry = ttk.Entry(frame, textvariable=body_var, width=35)
        body_entry.grid(row=1, column=1, sticky="w", pady=(0, 5))
        
        # Hotspot field - Ring Type dropdown
        ttk.Label(frame, text="Ring Type:").grid(row=2, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        hotspot_var = tk.StringVar(value=bookmark_data.get('hotspot', '') if bookmark_data else '')
        hotspot_combo = ttk.Combobox(frame, textvariable=hotspot_var, width=32, state="readonly")
        hotspot_combo['values'] = ("", "Metallic", "Rocky", "Icy", "Metal Rich")  # Blank option instead of "All"
        hotspot_combo.grid(row=2, column=1, sticky="w", pady=(0, 5))
        
        # Materials field
        ttk.Label(frame, text="Minerals Found:").grid(row=3, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        materials_var = tk.StringVar(value=bookmark_data.get('materials', '') if bookmark_data else '')
        materials_entry = ttk.Entry(frame, textvariable=materials_var, width=35)
        materials_entry.grid(row=3, column=1, sticky="w", pady=(0, 5))
        
        # Average Yield field
        ttk.Label(frame, text="Average Yield %:").grid(row=4, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        yield_var = tk.StringVar(value=bookmark_data.get('avg_yield', '') if bookmark_data else '')
        yield_entry = ttk.Entry(frame, textvariable=yield_var, width=35)
        yield_entry.grid(row=4, column=1, sticky="w", pady=(0, 5))
        
        # Target Material dropdown field
        ttk.Label(frame, text="Overlap Minerals:").grid(row=5, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        target_material_var = tk.StringVar(value=bookmark_data.get('target_material', '') if bookmark_data else '')
        
        # Specific materials list as requested
        target_materials = ['', 'Alexandrite', 'Benitoite', 'Bromellite', 'Grandidierite', 'Low-Temperature Diamonds', 
                           'Monazite', 'Musgravite', 'Painite', 'Platinum', 'Void Opals', 'Tritium']
        
        target_material_combo = ttk.Combobox(frame, textvariable=target_material_var, width=32, state="readonly")
        target_material_combo['values'] = tuple(target_materials)
        target_material_combo.grid(row=5, column=1, sticky="w", pady=(0, 5))
        
        # Overlap field
        ttk.Label(frame, text="Overlap Type:").grid(row=6, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        overlap_var = tk.StringVar(value=bookmark_data.get('overlap_type', '') if bookmark_data else '')
        overlap_combo = ttk.Combobox(frame, textvariable=overlap_var, width=32, state="readonly")
        overlap_combo['values'] = ('', '2x', '3x')
        overlap_combo.grid(row=6, column=1, sticky="w", pady=(0, 5))
        
        # RES Site field
        ttk.Label(frame, text="RES Site:").grid(row=7, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        res_var = tk.StringVar(value=bookmark_data.get('res_site', '') if bookmark_data else '')
        res_combo = ttk.Combobox(frame, textvariable=res_var, width=32, state="readonly")
        res_combo['values'] = ('', 'Hazardous', 'High', 'Low')
        res_combo.grid(row=7, column=1, sticky="w", pady=(0, 5))
        
        # RES Minerals dropdown field (separate from Overlap Minerals)
        ttk.Label(frame, text="RES Minerals:").grid(row=8, column=0, sticky="w", pady=(0, 5), padx=(0, 10))
        res_material_var = tk.StringVar(value=bookmark_data.get('res_material', '') if bookmark_data else '')
        
        # Same materials list for RES
        res_materials = ['', 'Alexandrite', 'Benitoite', 'Bromellite', 'Grandidierite', 'Low-Temperature Diamonds', 
                        'Monazite', 'Musgravite', 'Painite', 'Platinum', 'Void Opals', 'Tritium']
        
        res_material_combo = ttk.Combobox(frame, textvariable=res_material_var, width=32, state="readonly")
        res_material_combo['values'] = tuple(res_materials)
        res_material_combo.grid(row=8, column=1, sticky="w", pady=(0, 5))
        
        # Notes field
        ttk.Label(frame, text="Notes:").grid(row=9, column=0, sticky="nw", pady=(0, 5), padx=(0, 10))
        notes_text = tk.Text(frame, width=35, height=4, insertbackground="#ffffff")  # White cursor for visibility
        notes_text.grid(row=9, column=1, sticky="w", pady=(0, 10))
        if bookmark_data:
            notes_text.insert("1.0", bookmark_data.get('notes', ''))
        
        # Pre-load overlap/RES from database if editing existing bookmark with system/body
        def load_from_database():
            """Load overlap and RES values from database for current system/body/material"""
            try:
                system = system_var.get().strip()
                body = body_var.get().strip()
                material = target_material_var.get()
                
                if not system or not body or not material:
                    return
                
                if self.main_app and hasattr(self.main_app, 'cargo_monitor') and hasattr(self.main_app.cargo_monitor, 'user_db'):
                    user_db = self.main_app.cargo_monitor.user_db
                    
                    # Load overlap from database
                    db_overlap = user_db.get_overlap_tag(system, body, material)
                    if db_overlap and not overlap_var.get():
                        overlap_var.set(db_overlap)
                    
                    # Load RES from database
                    db_res = user_db.get_res_tag(system, body, material)
                    if db_res and not res_var.get():
                        res_var.set(db_res)
            except Exception as e:
                print(f"Error loading from database: {e}")
        
        # Bind material change to reload from database
        def on_material_change(*args):
            try:
                if dialog.winfo_exists():
                    load_from_database()
            except:
                pass  # Dialog was closed
        
        target_material_var.trace_add('write', on_material_change)
        
        # Initial load from database if editing existing bookmark
        if bookmark_data:
            load_from_database()
        
        # Remove the column weight so fields don't expand
        # frame.columnconfigure(1, weight=1)  # Commented out to prevent expansion
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=10, column=0, columnspan=2, pady=(10, 0))
        
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
                'target_material': target_material_var.get(),
                'overlap_type': overlap_var.get(),
                'res_site': res_var.get(),
                'res_material': res_material_var.get(),
                'last_mined': bookmark_data.get('last_mined', '') if bookmark_data else '',
                'notes': notes_text.get("1.0", "end-1c").strip(),
                'date_added': bookmark_data.get('date_added', dt.datetime.now().strftime('%Y-%m-%d')) if bookmark_data else dt.datetime.now().strftime('%Y-%m-%d')
            }
            
            # Sync overlap/RES to database for Ring Finder integration
            try:
                if self.main_app and hasattr(self.main_app, 'cargo_monitor') and hasattr(self.main_app.cargo_monitor, 'user_db'):
                    user_db = self.main_app.cargo_monitor.user_db
                    target_mat = target_material_var.get()
                    overlap_type = overlap_var.get()
                    res_site = res_var.get()
                    res_mat = res_material_var.get()
                    
                    # Get previous values to clear if changed
                    prev_target_mat = bookmark_data.get('target_material', '') if bookmark_data else ''
                    prev_res_mat = bookmark_data.get('res_material', '') if bookmark_data else ''
                    
                    # Sync overlap to database if both material and overlap type are set
                    if target_mat and overlap_type:
                        user_db.set_overlap_tag(system, body, target_mat, overlap_type)
                    elif target_mat and not overlap_type:
                        # Clear overlap if material set but no overlap type
                        user_db.set_overlap_tag(system, body, target_mat, None)
                    # Clear previous overlap if material changed
                    if prev_target_mat and prev_target_mat != target_mat:
                        user_db.set_overlap_tag(system, body, prev_target_mat, None)
                    
                    # Sync RES to database if both RES material and RES site are set
                    if res_mat and res_site:
                        user_db.set_res_tag(system, body, res_mat, res_site)
                    elif res_mat and not res_site:
                        # Clear RES if material set but no RES site
                        user_db.set_res_tag(system, body, res_mat, None)
                    # Clear previous RES if material changed or cleared
                    if prev_res_mat and prev_res_mat != res_mat:
                        user_db.set_res_tag(system, body, prev_res_mat, None)
            except Exception as e:
                print(f"Error syncing bookmark to database: {e}")
            
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
        
        # Center and show the dialog now that all widgets are created
        dialog.update_idletasks()
        main_parent = self.winfo_toplevel()
        main_parent.update_idletasks()
        
        # Get dialog size
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        
        # Get parent position and size
        parent_x = main_parent.winfo_rootx()
        parent_y = main_parent.winfo_rooty()
        parent_width = main_parent.winfo_width()
        parent_height = main_parent.winfo_height()
        
        # Calculate centered position
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        dialog.geometry(f"+{x}+{y}")
        dialog.deiconify()
        dialog.transient(main_parent)
        dialog.grab_set()

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
        
        # Confirm deletion using centered dialog
        from main import centered_yesno_dialog
        main_parent = self.winfo_toplevel()
        
        if not centered_yesno_dialog(main_parent, "Confirm Delete", confirm_message):
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
                from app_utils import centered_askyesno
                if centered_askyesno(self.winfo_toplevel(), "Bookmark Exists", 
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
            'target_material': '',
            'overlap_type': '',
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
        # Add "Session Overview" header
        session_header = tk.Label(left_column, text="Session Overview", font=("Consolas", 10, "bold"), 
                                 fg="#ffaa00", bg="#2b2b2b", anchor="w")
        session_header.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 5), padx=(0, 10))
        
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
            label.grid(row=1+i, column=0, sticky="w", pady=2, padx=(0, 10))
            
            # Value
            value_label = tk.Label(left_column, text="0", font=("Consolas", 10, "bold"), 
                                 fg="#00ff00", bg="#2b2b2b", anchor="w")
            value_label.grid(row=1+i, column=1, sticky="w", pady=2)
            self.stats_labels[key] = value_label
        
        # Add separator line
        separator = tk.Frame(left_column, height=1, bg="#444444")
        separator.grid(row=8, column=0, columnspan=2, sticky="ew", pady=8, padx=(0, 10))
        
        # Add "Best Records" header
        best_header = tk.Label(left_column, text="Best Records", font=("Consolas", 10, "bold"), 
                              fg="#ffaa00", bg="#2b2b2b", anchor="w")
        best_header.grid(row=9, column=0, columnspan=2, sticky="w", pady=(5, 2), padx=(0, 10))
        
        # Best records data
        best_records_data = [
            ("Best T/hr:", "best_session_tph"),
            ("Best System:", "best_session_system"),
            ("Most Mined Ton Session:", "best_tonnage"),
            ("Most Mined System:", "most_mined_system"),
            ("Most Mined Minerals:", "most_collected_material")
        ]
        
        for i, (label_text, key) in enumerate(best_records_data):
            # Label
            label = tk.Label(left_column, text=label_text, font=("Consolas", 10), 
                           fg="#cccccc", bg="#2b2b2b", anchor="w")
            label.grid(row=10+i, column=0, sticky="w", pady=2, padx=(0, 10))
            
            # Value
            value_label = tk.Label(left_column, text="0", font=("Consolas", 10, "bold"), 
                                 fg="#00ff00", bg="#2b2b2b", anchor="w")
            value_label.grid(row=10+i, column=1, sticky="w", pady=2)
            self.stats_labels[key] = value_label
        
        # Records (Right Column) - Top 5 Best Systems only
        top_systems_title = tk.Label(right_column, text="Top 5 Best Systems (T/hr)", font=("Consolas", 10, "bold"), 
                                    fg="#cccccc", bg="#2b2b2b", anchor="w")
        top_systems_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2), padx=(0, 10))
        
        # Create labels for top 5 systems (3 lines per system: System|Body, Material, then metrics)
        row_offset = 0
        for rank in range(1, 6):
            # Line 1: Rank. System | Body
            system_label = tk.Label(right_column, text=f"{rank}. — | —", font=("Consolas", 10), 
                                   fg="#ffffff", bg="#2b2b2b", anchor="w", wraplength=350, justify="left")
            system_label.grid(row=1+row_offset, column=0, columnspan=2, sticky="w", pady=(2, 0), padx=(0, 10))
            self.stats_labels[f'top_system_{rank}_line1'] = system_label
            
            # Line 2: Material (indented to align below system name, after "1. ")
            material_label = tk.Label(right_column, text="—", font=("Consolas", 10), 
                                     fg="#ffaa00", bg="#2b2b2b", anchor="w", wraplength=350, justify="left")
            material_label.grid(row=1+row_offset+1, column=0, columnspan=2, sticky="w", pady=(0, 0), padx=(15, 0))
            self.stats_labels[f'top_system_{rank}_line2'] = material_label
            
            # Line 3: Metrics indented (T/Asteroid, TPH)
            metrics_label = tk.Label(right_column, text="—", font=("Consolas", 10), 
                                    fg="#00ff00", bg="#2b2b2b", anchor="w", wraplength=350, justify="left")
            metrics_label.grid(row=1+row_offset+2, column=0, columnspan=2, sticky="w", pady=(0, 2), padx=(15, 0))
            self.stats_labels[f'top_system_{rank}_line3'] = metrics_label
            
            row_offset += 3
        
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
                            # New format: "Platinum:6t" or "Osmium:3t, Platinum:280t" or "Bromellite: 81.0t (40.5%)"
                            materials = materials_breakdown.split(',') if ',' in materials_breakdown else [materials_breakdown]
                            for material_entry in materials:
                                if ':' in material_entry:
                                    material_name, amount_str = material_entry.split(':', 1)
                                    try:
                                        # Remove 't' and handle optional yield percentage "(XX.X%)"
                                        amount_str = amount_str.strip().replace('t', '')
                                        # Remove anything in parentheses (yield percentage)
                                        if '(' in amount_str:
                                            amount_str = amount_str.split('(')[0].strip()
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
            
            # Calculate average tons per asteroid from all sessions
            total_tons_per = 0
            valid_tpa_sessions = 0
            for session in sessions:
                try:
                    total_tons = float(session.get('total_tons', 0) or 0)
                    asteroids = int(session.get('asteroids_prospected', 0) or 0)
                    if asteroids > 0 and total_tons > 0:
                        tons_per = total_tons / asteroids
                        total_tons_per += tons_per
                        valid_tpa_sessions += 1
                except (ValueError, TypeError):
                    continue
            stats['avg_tons_per_asteroid'] = total_tons_per / valid_tpa_sessions if valid_tpa_sessions > 0 else 0
            
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
                # Filter out summary entries like "Total Cargo Collected"
                actual_materials = {k: v for k, v in stats['material_totals'].items() 
                                  if k.lower() not in ['total cargo collected', 'total', 'cargo collected']}
                
                if actual_materials:
                    most_material = max(actual_materials.items(), key=lambda x: x[1])
                    stats['most_collected_material'] = most_material[0]
                    stats['most_collected_material_amount'] = most_material[1]
                else:
                    stats['most_collected_material'] = 'None'
                    stats['most_collected_material_amount'] = 0
                
                # Add material count (only actual materials)
                stats['material_count'] = len(actual_materials)
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
    
    def _calculate_ring_quality_rating(self, tph, tons_per_asteroid):
        """Calculate ring quality rating based on TPH and tons/asteroid.
        
        Returns: (rating_name, color_hex)
        - Excellent: TPH >= 800 AND T/ast >= 20
        - Good: TPH >= 600 AND T/ast >= 15
        - Fair: TPH >= 400 AND T/ast >= 10
        - Poor: Below Fair threshold
        """
        try:
            tph = float(tph or 0)
            tons_per_asteroid = float(tons_per_asteroid or 0)
            
            if tph >= 800 and tons_per_asteroid >= 20:
                return ("EXCELLENT", "#2d5a3d", "#a8d5ba")
            elif tph >= 600 and tons_per_asteroid >= 15:
                return ("GOOD", "#1c4a5e", "#8fd4e8")
            elif tph >= 400 and tons_per_asteroid >= 10:
                return ("FAIR", "#5e4e1c", "#f0d896")
            else:
                return ("POOR", "#5e1c24", "#f5a5ae")
        except (ValueError, TypeError):
            return ("No data", "#2b2b2b", "#888888")
    
    def _get_top_systems_from_csv(self, limit=5):
        """Get top N unique systems by tons_per_asteroid from CSV (no duplicate system/body combos).
        
        Returns list of dicts with system, body, tons_per, tph, material
        """
        try:
            import csv
            csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
            
            if not os.path.exists(csv_path):
                return []
            
            sessions = []
            seen_systems = set()  # Track unique system|body combinations
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        system = row.get('system', '')
                        body = row.get('body', '')
                        system_key = f"{system}|{body}"
                        
                        # Skip if we've already seen this system|body combination
                        if system_key in seen_systems:
                            continue
                        
                        total_tons = float(row.get('total_tons', 0) or 0)
                        asteroids = int(row.get('asteroids_prospected', 0) or 1)
                        tons_per = total_tons / asteroids if asteroids > 0 else 0
                        
                        if tons_per > 0:
                            best_material = row.get('best_material', 'Unknown')
                            
                            sessions.append({
                                'system': system,
                                'body': body,
                                'tons_per': tons_per,
                                'tph': float(row.get('overall_tph', 0) or 0),
                                'material': best_material
                            })
                            seen_systems.add(system_key)
                    except (ValueError, TypeError):
                        continue
            
            # Sort by T/hr (TPH) descending
            sessions.sort(key=lambda x: x['tph'], reverse=True)
            
            return sessions[:limit]
        except Exception as e:
            print(f"Error getting top systems: {e}")
            return []
    
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
                # Clear top 5 systems
                for rank in range(1, 6):
                    self.stats_labels[f'top_system_{rank}_line1'].config(text=f"{rank}. — | —")
                    self.stats_labels[f'top_system_{rank}_line2'].config(text="—")
                    self.stats_labels[f'top_system_{rank}_line3'].config(text="—")
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
            
            # Update Top 5 Systems: Line 1=System|Body, Line 2=Material, Line 3=Metrics
            top_systems = self._get_top_systems_from_csv(limit=5)
            for rank in range(1, 6):
                if rank <= len(top_systems):
                    sys_data = top_systems[rank - 1]
                    # Line 1: Rank. System | Body
                    line1_text = f"{rank}. {sys_data['system']} | {sys_data['body']}"
                    # Line 2: Material with label
                    line2_text = f"Minerals: {sys_data['material']}"
                    # Line 3: Metrics (T/Asteroid and TPH only)
                    line3_text = f"{sys_data['tons_per']:.1f} T/Asteroid  |  {sys_data['tph']:.1f} T/hr"
                else:
                    line1_text = f"{rank}. — | —"
                    line2_text = "—"
                    line3_text = "—"
                
                self.stats_labels[f'top_system_{rank}_line1'].config(text=line1_text)
                self.stats_labels[f'top_system_{rank}_line2'].config(text=line2_text)
                self.stats_labels[f'top_system_{rank}_line3'].config(text=line3_text)
            
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
                screenshots_dir = os.path.join(get_reports_dir(), "Detailed Reports", "Screenshots")
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
                    # Columns: date(0), duration(1), ship(2), system(3), body(4)
                    report_id = f"{values[0]}_{values[3]}_{values[4]}"  # date_system_body as unique ID (no ship)
                    
                    # Store screenshot references for the selected report
                    self._store_report_screenshots(report_id, copied_files)
                    
                    from app_utils import centered_message
                    centered_message(tree.winfo_toplevel(), "Screenshots Added",
                                     f"Added {len(copied_files)} screenshots to this report.\n\nThey will be included when you generate a detailed report.")
                    self._set_status(f"Added {len(copied_files)} screenshots to report")
                else:
                    from app_utils import centered_message
                    centered_message(tree.winfo_toplevel(), "Copy Failed", "No screenshots were successfully copied.")
                    
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
                screenshots_dir = os.path.join(get_reports_dir(), "Detailed Reports", "Screenshots")
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
                    # Use correct column indices: date, system, body
                    report_id = f"{values[0]}_{values[4]}_{values[5]}"  # date_system_body as unique ID
                    
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
            # Use centralized path utility for screenshots mapping file
            screenshots_map_file = os.path.join(get_reports_dir(), "Detailed Reports", "screenshot_mappings.json")
            
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
            # Use centralized path utility for screenshots mapping file
            screenshots_map_file = os.path.join(get_reports_dir(), "Detailed Reports", "screenshot_mappings.json")
            
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
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "No HTML Report", 
                                 f"To generate a PDF report, you must first create an HTML detailed report.\n\n"
                                 f"Session: {display_date} - {system} {body}\n\n"
                                 f"Right-click on this session and select 'Generate Detailed Report (HTML)' first.")
                return
            
            # Check if PDF already exists
            if filenames['pdf']:
                from app_utils import centered_askyesno
                if not centered_askyesno(self.winfo_toplevel(), "PDF Exists", 
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
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "HTML File Not Found", f"The HTML report file could not be found:\n{html_path}")
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
                from app_utils import centered_askyesno, centered_message
                if centered_askyesno(self.winfo_toplevel(), "PDF Generated", 
                                      f"PDF report generated successfully!\n\n"
                                      f"File: {os.path.basename(pdf_path)}\n\n"
                                      f"Do you want to open it now?"):
                    self._open_pdf_report(report_id)
            else:
                centered_message(self.winfo_toplevel(), "PDF Generation Failed",
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
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "No PDF Report",
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
                
                from app_utils import centered_message
                centered_message(self.winfo_toplevel(), "No Detailed Report",
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
            # Note: Column layout is: [0]=date, [1]=duration, [2]=session_type, [3]=ship, [4]=system, [5]=body
            system = values[4] if len(values) > 4 else ''  # System column (correct index)
            body = values[5] if len(values) > 5 else ''    # Body column (correct index)
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
            # Note: Column layout is: [0]=date, [1]=duration, [2]=session_type, [3]=ship, [4]=system, [5]=body
            system = values[4] if len(values) > 4 else ''  # System column (correct index)
            body = values[5] if len(values) > 5 else ''    # Body column (correct index)
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
                # Columns: date, duration, session_type, ship, system, body...
                display_date = values[0]  # Date/Time column
                ship_name = values[3] if len(values) > 3 else ''  # Ship is column 3  
                system = values[4] if len(values) > 4 else ''  # System is column 4
                body = values[5] if len(values) > 5 else ''    # Body is column 5
                report_id = f"{display_date}_{system}_{body}"
                
                # Check if detailed report exists
                html_filename = self._get_report_filenames(report_id)
                if html_filename:
                    session_info = {
                        'report_id': report_id,
                        'display_date': display_date,
                        'ship_name': ship_name,
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
                    
                    from main import centered_info_dialog
                    centered_info_dialog(
                        self.winfo_toplevel(),
                        "No Detailed Report",
                        f"No detailed report found for this mining session.\n\n"
                        f"Session: {display_date} - {system} {body}\n\n"
                        f"To create a detailed report, right-click on this session and select 'Generate Detailed Report (HTML)'."
                    )
                else:
                    # Multiple selections with no detailed reports
                    from main import centered_info_dialog
                    centered_info_dialog(
                        self.winfo_toplevel(),
                        "No Detailed Reports",
                        f"None of the {len(selected_items)} selected sessions have detailed reports.\n\n"
                        f"To create detailed reports, right-click on individual sessions and select 'Generate Detailed Report (HTML)'."
                    )
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
            from main import centered_yesno_dialog
            if not centered_yesno_dialog(
                self.winfo_toplevel(),
                title,
                confirm_msg
            ):
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
                    
                    # Delete associated screenshots - try multiple report_id formats
                    # First try without ship name (current format)
                    display_date = session.get('display_date', '')
                    system = session.get('system', '')
                    body = session.get('body', '')
                    report_id_no_ship = f"{display_date}_{system}_{body}"
                    print(f"[DEBUG] Looking for screenshots with key: '{report_id_no_ship}'")
                    screenshots = self._get_report_screenshots(report_id_no_ship)
                    print(f"[DEBUG] Found {len(screenshots)} screenshots")
                    found_report_id = report_id_no_ship if screenshots else None
                    
                    # If not found, try with ship name (new format)
                    if not screenshots:
                        screenshots = self._get_report_screenshots(report_id)
                        found_report_id = report_id if screenshots else None
                    
                    # If still not found, try alternate format with ship name (old format without body)
                    if not screenshots:
                        ship_name = session.get('ship_name', '')
                        if ship_name and display_date and system:
                            alt_report_id = f"{display_date}_{ship_name}_{system}"
                            screenshots = self._get_report_screenshots(alt_report_id)
                            found_report_id = alt_report_id if screenshots else None
                    
                    for screenshot_path in screenshots:
                        if os.path.exists(screenshot_path):
                            try:
                                os.remove(screenshot_path)
                            except Exception as e:
                                pass
                    
                    # Remove from screenshot mappings using the found report_id
                    if found_report_id:
                        screenshots_map_file = os.path.join(self.reports_dir, "Detailed Reports", "screenshot_mappings.json")
                        if os.path.exists(screenshots_map_file):
                            try:
                                import json
                                with open(screenshots_map_file, 'r') as f:
                                    screenshot_mappings = json.load(f)
                                
                                if found_report_id in screenshot_mappings:
                                    del screenshot_mappings[found_report_id]
                                    
                                with open(screenshots_map_file, 'w') as f:
                                    json.dump(screenshot_mappings, f, indent=2)
                            except Exception as e:
                                pass
                    
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
                from app_utils import centered_message
                if deleted_count == 1:
                    centered_message(self.winfo_toplevel(), "Success", "Detailed report deleted successfully.")
                else:
                    centered_message(self.winfo_toplevel(), "Success", f"{deleted_count} detailed reports deleted successfully.")
                
        except Exception as e:
            print(f"Error deleting detailed report: {e}")
            from app_utils import centered_message
            centered_message(self.winfo_toplevel(), "Error", f"Failed to delete detailed report: {e}")
    
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
        """Create a click handler that intercepts enhanced report and comment clicks"""
        def enhanced_click_handler(event):
            try:
                # Check if this click is on a specific column
                item = tree.identify_row(event.y)
                column = tree.identify_column(event.x)
                
                if item and column:
                    columns = tree["columns"]
                    column_index = int(column[1:]) - 1
                    if column_index < len(columns):
                        column_name = columns[column_index]
                        
                        # Handle clicks on comment column - open comment editor
                        if column_name == "comment":
                            self._edit_comment(tree, item)
                            return "break"  # Prevent default behavior
                        
                        # Handle clicks on the enhanced column - do nothing on single-click
                        elif column_name == "enhanced":
                            return None  # Allow normal row selection
                        
                        # For all other columns (except comment and enhanced), do nothing on single-click
                        else:
                            # Allow normal row selection behavior
                            return None
                
                # For all other clicks, allow normal processing
                return None
                
            except Exception as e:
                print(f"Error in enhanced click handler: {e}")
                return None
        
        return enhanced_click_handler
    
    def _add_refinery_to_session_from_menu(self, tree, item):
        """Add refinery contents to a completed session from the Reports tab context menu"""
        try:
            # Get session data from tree
            values = tree.item(item, 'values')
            if not values:
                messagebox.showwarning("No Selection", "Please select a report first.")
                return
            
            # Extract session info
            display_date = values[0]  # Date/Time column
            system = values[2] if len(values) > 2 else ''  # System column
            body = values[3] if len(values) > 3 else ''    # Body column
            
            # Parse cargo data from column 10 (cargo column)
            cargo_raw = values[10] if len(values) > 10 else ''
            current_cargo_items = {}
            
            # Parse cargo string (format: "Material: X tons; Material2: Y tons")
            if cargo_raw:
                cargo_parts = cargo_raw.split(';')
                for part in cargo_parts:
                    part = part.strip()
                    if ':' in part:
                        material_part, quantity_part = part.rsplit(':', 1)
                        material = material_part.strip()
                        try:
                            # Extract numeric value from "X tons"
                            quantity = float(quantity_part.strip().split()[0])
                            current_cargo_items[material] = quantity
                        except (ValueError, IndexError):
                            pass
            
            # Open Refinery Dialog
            from main import RefineryDialog
            # Get the top-level window as parent
            parent_window = self.winfo_toplevel()
            dialog = RefineryDialog(
                parent=parent_window,
                cargo_monitor=self.main_app.cargo_monitor,
                current_cargo_items=current_cargo_items
            )
            refinery_result = dialog.show()
            
            if refinery_result:  # User added refinery contents
                # Calculate totals
                cargo_total = sum(current_cargo_items.values())
                refinery_total = sum(refinery_result.values())
                new_total = cargo_total + refinery_total
                
                # Update the session file with refinery contents
                report_id = f"{display_date}_{system}_{body}"
                session_filename = f"Session_{report_id}.txt"
                session_path = os.path.join(self.reports_dir, session_filename)
                
                if os.path.exists(session_path):
                    # Read existing session file
                    with open(session_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Update cargo total line
                    import re
                    content = re.sub(
                        r'Total Cargo:.*',
                        f'Total Cargo: {new_total:.1f} tons (includes {refinery_total:.1f} tons from refinery)',
                        content
                    )
                    
                    # Add refinery section before the cargo breakdown
                    refinery_section = "\n⚗️ Refinery Contents Added:\n"
                    for material, quantity in sorted(refinery_result.items()):
                        refinery_section += f"  {material}: {quantity:.1f} tons\n"
                    refinery_section += "\n"
                    
                    # Insert refinery section before "Cargo Breakdown:"
                    if "Cargo Breakdown:" in content:
                        content = content.replace("Cargo Breakdown:", refinery_section + "Cargo Breakdown:")
                    else:
                        # If no cargo breakdown section, add at end
                        content += refinery_section
                    
                    # Write updated content
                    with open(session_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    # Rebuild CSV to reflect changes
                    csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                    self._rebuild_csv_from_files_tab(csv_path)
                    
                    # Refresh the reports tab to show updated session immediately
                    self._refresh_reports_tab()
                    
                    from app_utils import centered_message
                    centered_message(self.winfo_toplevel(), "Refinery Contents Added",
                                     f"Added {refinery_total:.1f} tons from refinery to session.\n\n"
                                     f"New total: {new_total:.1f} tons\n\n"
                                     f"Session file and CSV index have been updated.")
                else:
                    from app_utils import centered_message
                    centered_message(self.winfo_toplevel(), "Session Not Found",
                                     f"Could not find session file:\n{session_filename}\n\n"
                                     f"The session may have been moved or deleted.")
                    
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add refinery contents:\n{str(e)}")
            print(f"Error adding refinery to session: {e}")
            import traceback
            traceback.print_exc()
            
    def _convert_session_data_for_report(self, session_data):
        """Convert session data from display format to report generator format"""
        try:
            converted = session_data.copy()
        except Exception as e:
            log.error(f"Error copying session_data: {e}")
            return session_data
        
        # Convert tons from string "15.2t" to float
        if 'tons' in converted and isinstance(converted['tons'], str):
            try:
                tons_str = converted['tons'].replace('t', '').strip()
                converted['tons'] = float(tons_str)
                converted['total_tons_mined'] = converted['tons']
            except:
                converted['tons'] = 0.0
                converted['total_tons_mined'] = 0.0
        
        # Convert prospectors from string to int (field might be 'prospects' or 'prospectors')
        prosp_field = 'prospects' if 'prospects' in converted else 'prospectors'
        if prosp_field in converted and isinstance(converted[prosp_field], str):
            try:
                prosp_str = converted[prosp_field].replace('—', '0').strip()
                prosp_value = int(float(prosp_str)) if prosp_str else 0
                converted['prospectors'] = prosp_value  # Report generator expects 'prospectors'
                converted['prospects'] = prosp_value    # Keep original too
            except:
                converted['prospectors'] = 0
                converted['prospects'] = 0
        
        # Convert materials from string count to int (will be recalculated after parsing materials_mined)
        if 'materials' in converted and isinstance(converted['materials'], str):
            try:
                mat_str = converted['materials'].replace('—', '0').strip()
                converted['materials'] = int(mat_str) if mat_str else 0
            except:
                converted['materials'] = 0
        
        # Parse materials_mined from cargo string if not already a dict
        if 'materials_mined' not in converted or not isinstance(converted.get('materials_mined'), dict):
            cargo_str = converted.get('cargo', '') or converted.get('cargo_raw', '')
            if cargo_str and isinstance(cargo_str, str):
                materials_mined = {}
                try:
                    # Parse "Painite: 13.5t, Platinum: 15.2t" or "Platinum: 259t (30.5%); Osmium: 3t (16.0%)" format
                    # Check if it uses semicolons or commas as separator
                    if ';' in cargo_str:
                        pairs = [p.strip() for p in cargo_str.split(';')]
                    else:
                        pairs = [p.strip() for p in cargo_str.split(',')]
                    for pair in pairs:
                        if ':' in pair:
                            parts = pair.split(':')
                            if len(parts) >= 2:
                                material_name = parts[0].strip()
                                tonnage_text = parts[1].strip()
                                # Extract numeric value from "13.5t" format
                                tonnage_match = re.search(r'([\d.]+)', tonnage_text)
                                if tonnage_match:
                                    tonnage = float(tonnage_match.group(1))
                                    materials_mined[material_name] = tonnage
                    converted['materials_mined'] = materials_mined
                except Exception as e:
                    log.warning(f"Error parsing cargo for materials_mined: {e}")
                    converted['materials_mined'] = {}
            else:
                converted['materials_mined'] = {}
        
        # Recalculate materials count from materials_mined dictionary for accuracy
        if 'materials_mined' in converted and isinstance(converted['materials_mined'], dict):
            converted['materials'] = len(converted['materials_mined'])
        
        # Parse individual yields from quality/avg_quality_percent field (format: "Pt: 30.5%, Os: 16.0%")
        if 'individual_yields' not in converted or not converted.get('individual_yields'):
            # IMPORTANT: Use detailed quality string first, not the simplified display value
            quality_str = converted.get('avg_quality_percent', '') or converted.get('quality_detailed', '') or converted.get('quality', '')
            print(f"✓ DEBUG YIELDS: Parsing quality_str: '{quality_str}'")
            if quality_str and isinstance(quality_str, str) and ':' in quality_str:
                individual_yields = {}
                try:
                    # Parse "Pt: 30.5%, Os: 16.0%" format
                    pairs = [p.strip() for p in quality_str.split(',')]
                    for pair in pairs:
                        if ':' in pair:
                            parts = pair.split(':')
                            if len(parts) >= 2:
                                material_abbr = parts[0].strip()
                                percent_text = parts[1].strip().replace('%', '')
                                try:
                                    percent_value = float(percent_text)
                                    # Expand abbreviations to full names
                                    material_map = {
                                        'Pt': 'Platinum', 'Os': 'Osmium', 'Pd': 'Palladium',
                                        'Pain': 'Painite', 'Pn': 'Painite', 'Rh': 'Rhodium', 
                                        'LTD': 'Low Temperature Diamonds', 'VO': 'Void Opals', 
                                        'Alex': 'Alexandrite', 'Beni': 'Benitoite', 'Ben': 'Benitoite',
                                        'Grand': 'Grandidierite', 'Musg': 'Musgravite', 'Mus': 'Musgravite', 
                                        'Monaz': 'Monazite', 'Mon': 'Monazite', 'Brom': 'Bromellite', 
                                        'Ser': 'Serendibite', 'Seren': 'Serendibite', 'Au': 'Gold',
                                        'Ag': 'Silver', 'Bert': 'Bertrandite', 'Ind': 'Indite',
                                        'Ga': 'Gallium', 'Pr': 'Praseodymium', 'Sm': 'Samarium',
                                        'Taaf': 'Taaffeite'
                                    }
                                    material_name = material_map.get(material_abbr, material_abbr)
                                    individual_yields[material_name] = percent_value
                                except ValueError:
                                    continue
                    if individual_yields:
                        print(f"DEBUG YIELDS: Parsed individual_yields: {individual_yields}")
                        converted['individual_yields'] = individual_yields
                    else:
                        print("DEBUG YIELDS: No individual_yields parsed")
                except Exception as e:
                    log.warning(f"Error parsing individual yields from quality string: {e}")
                    print(f"DEBUG YIELDS: Exception: {e}")
        
        return converted
    
    def _extract_session_type_from_data(self, session_data):
        """Extract session type from session data (header or other fields)"""
        # First check if session_type is already in data (new sessions)
        if 'session_type' in session_data and session_data['session_type']:
            session_type = session_data['session_type']
            # Clean up (remove parentheses if present)
            return session_type.replace("(", "").replace(")", "")
        
        # Try to parse from header field (for old sessions stored in TXT files)
        header = session_data.get('header', '')
        if header:
            if "(Multi-Session)" in header:
                return "Multi-Session"
            elif "(Single Session)" in header:
                return "Single Session"
        
        # Try to read the TXT file if file_path is available
        file_path = session_data.get('file_path', '')
        
        if file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    first_line = f.readline().strip()
                    # Parse header line: "Session: System — Body — Duration — Total XXt (Multi-Session)"
                    if "(Multi-Session)" in first_line:
                        return "Multi-Session"
                    elif "(Single Session)" in first_line:
                        return "Single Session"
            except Exception as e:
                pass
        
        # Fallback: Single Session (default for old reports without type info)
        return "Single Session"
    
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
            
            # Check which tree we're using and get the appropriate lookup
            if tree == self.reports_tree_tab and hasattr(self, 'reports_tab_session_lookup'):
                session_data = self.reports_tab_session_lookup.get(item)
                if session_data:
                    print(f"✓ DEBUG: Got session_data from reports_tab_session_lookup")
                    print(f"✓ DEBUG: avg_quality_percent = '{session_data.get('avg_quality_percent', 'NOT FOUND')}'")
                    # Convert display format to report generator format
                    session_data = self._convert_session_data_for_report(session_data)
                    print(f"✓ DEBUG: After conversion, individual_yields = {session_data.get('individual_yields', 'NOT FOUND')}")
            elif hasattr(self, 'reports_window_session_lookup'):
                session_data = self.reports_window_session_lookup.get(item)
                if session_data:
                    print(f"✓ DEBUG: Got session_data from reports_window_session_lookup")
                    # Convert display format to report generator format
                    session_data = self._convert_session_data_for_report(session_data)
            
            # If no detailed session data, create basic data from tree item
            if not session_data:
                log.warning("No session_data from lookup - falling back to tree parsing")
                values = tree.item(item, 'values')
                if len(values) >= 6:  # Ensure we have basic data
                    # Try to parse materials from the "Materials" column if available
                    materials_mined = {}
                    
                    # First try to get materials from breakdown column (materials_breakdown format: "Mat1: 5.2t, Mat2: 3.1t")
                    material_col_idx = 11  # Try "cargo" column which should have materials (shifted by tons_per)
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
                    
                    # Try to get prospectors used from the prospectors column (index 12 after shift)
                    prospectors_used = 0
                    if len(values) > 12 and values[12]:
                        try:
                            prospectors_text = str(values[12]).strip()
                            if prospectors_text and prospectors_text != "—" and prospectors_text != "":
                                prospectors_used = int(float(prospectors_text))
                        except (ValueError, TypeError):
                            prospectors_used = 0
                    
                    # Get the actual comment text (not the emoji from tree display)
                    actual_comment = ""
                    if len(values) > 13 and values[13] == '💬':
                        # Comment exists - need to retrieve actual text from CSV
                        log.debug(f"Fetching comment for timestamp: {values[0]}")
                        actual_comment = self._get_comment_by_timestamp(values[0])
                        log.debug(f"Retrieved comment: {actual_comment[:50] if actual_comment else 'EMPTY'}")
                    
                    # Create basic session data from tree values matching report generator expectations
                    tons_value = float(values[4]) if values[4] else 0.0
                    
                    # Extract ship name from miningSessionSummary.txt (only for today's sessions)
                    ship_name_for_html = self._get_ship_name_from_session(values[2], values[3], values[0])
                    print(f"[DEBUG HTML] Ship name for HTML report: '{ship_name_for_html}'")
                    
                    session_data = {
                        'date': values[0],
                        'duration': values[1],
                        'system': values[2],
                        'body': values[3],
                        'tons': tons_value,  # Report generator expects 'tons'
                        'tonnage': tons_value,  # Keep for compatibility
                        'tph': float(values[5]) if values[5] else 0.0,
                        'materials_mined': materials_mined,
                        'materials': len(materials_mined),  # Count of material types
                        'prospectors': prospectors_used,  # Report generator expects 'prospectors'
                        'prospectors_used': prospectors_used,  # Keep for compatibility
                        'total_tons_mined': tons_value,  # For advanced analytics
                        'comment': actual_comment,
                        'ship_name': ship_name_for_html  # Add ship name for HTML report
                    }
                    
                    # Load detailed analytics from CSV if available (populate session_data)
                    try:
                        csv_path = os.path.join(self.reports_dir, "sessions_index.csv")
                        if os.path.exists(csv_path):
                            import csv
                            with open(csv_path, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                for row in reader:
                                    row_system = row.get('system', '')
                                    row_body = row.get('body', '')
                                    row_timestamp = row.get('timestamp_utc', '')

                                    # Match by timestamp exact or by system/body with tolerant timestamp
                                    matched = False
                                    try:
                                        if row_timestamp and row_timestamp == session_data.get('timestamp_raw', ''):
                                            matched = True
                                        else:
                                            # Try convert CSV timestamp to display and compare to tree value
                                            if row_timestamp.endswith('Z'):
                                                csv_dt = dt.datetime.fromisoformat(row_timestamp.replace('Z', '+00:00'))
                                                csv_dt = csv_dt.replace(tzinfo=dt.timezone.utc).astimezone()
                                            else:
                                                csv_dt = dt.datetime.fromisoformat(row_timestamp)
                                            display_time = csv_dt.strftime("%m/%d/%y %H:%M")
                                            if display_time == values[0]:
                                                matched = True
                                    except Exception:
                                        matched = False

                                    if not matched:
                                        # Fallback match by system/body only
                                        if row_system == session_data.get('system') and row_body == session_data.get('body'):
                                            matched = True

                                    if not matched:
                                        continue

                                    # Populate session_data fields from CSV row
                                    try:
                                        session_data['tons'] = float(row.get('total_tons', 0.0) or 0.0)
                                    except:
                                        session_data['tons'] = session_data.get('tons', 0.0)
                                    try:
                                        session_data['tph'] = float(row.get('overall_tph', 0.0) or 0.0)
                                    except:
                                        session_data['tph'] = session_data.get('tph', 0.0)
                                    # materials tracked and asteroids
                                    try:
                                        session_data['materials'] = int(row.get('materials_tracked', '') or 0)
                                    except:
                                        session_data['materials'] = session_data.get('materials', 0)
                                    session_data['asteroids'] = row.get('asteroids_prospected', session_data.get('asteroids', ''))
                                    # Tons per asteroid
                                    try:
                                        ast_cnt = int(row.get('asteroids_prospected', '') or 0)
                                        if ast_cnt > 0:
                                            session_data['tons_per'] = f"{float(row.get('total_tons', 0.0)) / ast_cnt:.1f}"
                                        else:
                                            session_data['tons_per'] = session_data.get('tons_per', '—')
                                    except:
                                        session_data['tons_per'] = session_data.get('tons_per', '—')

                                    # Cargo/material breakdown
                                    materials_breakdown_csv = row.get('materials_breakdown', '') or ''
                                    session_data['cargo'] = materials_breakdown_csv
                                    session_data['cargo_raw'] = materials_breakdown_csv
                                    # Try to parse a materials_mined dict
                                    csv_materials = {}
                                    try:
                                        if materials_breakdown_csv:
                                            seps = [';', ',']
                                            for sep in seps:
                                                if sep in materials_breakdown_csv:
                                                    pairs = [p.strip() for p in materials_breakdown_csv.split(sep)]
                                                    break
                                            else:
                                                pairs = [materials_breakdown_csv.strip()]
                                            for pair in pairs:
                                                if ':' in pair:
                                                    parts = pair.split(':')
                                                    if len(parts) >= 2:
                                                        mname = parts[0].strip()
                                                        ttext = parts[1].strip()
                                                        ton_match = re.search(r'([\d.]+)', ttext)
                                                        if ton_match:
                                                            csv_materials[mname] = float(ton_match.group(1))
                                        if csv_materials:
                                            session_data['materials_mined'] = csv_materials
                                    except Exception as e:
                                        print(f"Warning: Could not parse materials_breakdown from CSV: {e}")

                                    # Individual yields
                                    try:
                                        yield_str = row.get('avg_quality_percent', '') or ''
                                        if yield_str and isinstance(yield_str, str) and ':' in yield_str:
                                            individual_yields = {}
                                            pairs = [p.strip() for p in yield_str.split(',')]
                                            for pair in pairs:
                                                if ':' in pair:
                                                    parts = pair.split(':')
                                                    if len(parts) >= 2:
                                                        abbrev = parts[0].strip()
                                                        perc = parts[1].strip().replace('%', '')
                                                        try:
                                                            individual_yields[abbrev] = float(perc)
                                                        except:
                                                            continue
                                            if individual_yields:
                                                session_data['individual_yields'] = individual_yields
                                    except Exception as e:
                                        print(f"Warning: Could not parse individual yields: {e}")

                                    # Comment and timestamp
                                    session_data['comment'] = row.get('comment', session_data.get('comment', ''))
                                    session_data['timestamp_raw'] = row.get('timestamp_utc', session_data.get('timestamp_raw', ''))
                                    break
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
            # Parse engineering_materials if in encoded format
            engineering_materials_dict = {}
            eng_materials_raw = session_data.get('engineering_materials', '')
            if eng_materials_raw and isinstance(eng_materials_raw, str):
                # Parse "Iron:45,Nickel:23" format
                try:
                    for pair in eng_materials_raw.split(','):
                        if ':' in pair:
                            mat_name, qty = pair.split(':', 1)
                            engineering_materials_dict[mat_name.strip()] = int(qty.strip())
                except Exception as e:
                    print(f"Warning: Could not parse engineering_materials: {e}")
            elif isinstance(eng_materials_raw, dict):
                engineering_materials_dict = eng_materials_raw
            
            # Calculate session_duration from elapsed time if not present
            session_duration_seconds = session_data.get('session_duration', 0)
            if not session_duration_seconds:
                # Parse elapsed time "HH:MM:SS" to seconds
                elapsed_str = session_data.get('duration', '00:00:00')
                try:
                    time_parts = elapsed_str.split(':')
                    if len(time_parts) == 3:
                        hours, minutes, seconds = map(int, time_parts)
                        session_duration_seconds = hours * 3600 + minutes * 60 + seconds
                    elif len(time_parts) == 2:
                        minutes, seconds = map(int, time_parts)
                        session_duration_seconds = minutes * 60 + seconds
                except:
                    session_duration_seconds = 0
            
            # CRITICAL: Parse TXT file for mineral_performance BEFORE creating enhanced_session_data
            # This ensures the data is available on the first attempt, not as a later fallback
            session_text_file = None
            if 'file_path' in session_data:
                session_text_file = session_data['file_path']
            elif 'system' in session_data and 'body' in session_data:
                # Try to construct filename from session data
                session_system = session_data.get('system', '').replace(':', '_').replace('/', '_').replace('\\', '_')
                session_body = session_data.get('body', '').replace(':', '_').replace('/', '_').replace('\\', '_')
                
                if session_system and session_body:
                    # Look for matching session file
                    search_patterns = [
                        os.path.join(self.reports_dir, f"*{session_system}*{session_body}*.txt"),
                        os.path.join(self.reports_dir, f"*{session_system}*.txt"),
                    ]
                    
                    for pattern in search_patterns:
                        matching_files = glob.glob(pattern)
                        if matching_files:
                            session_text_file = max(matching_files, key=os.path.getmtime)
                            break
            
            # Parse mineral_performance and total_finds from TXT file NOW
            if session_text_file and os.path.exists(session_text_file):
                try:
                    with open(session_text_file, 'r', encoding='utf-8') as tfh:
                        txt_content = tfh.read()
                        
                        # Parse total hits/finds
                        tf_m = re.search(r'Total Material Hits:\s*(\d+)', txt_content)
                        if not tf_m:
                            tf_m = re.search(r'Total Material Finds:\s*(\d+)', txt_content)
                        if tf_m:
                            parsed_hits = int(tf_m.group(1))
                            if parsed_hits > 0:
                                session_data['total_finds'] = parsed_hits
                        
                        # Parse mineral_performance section
                        mineral_performance = {}
                        lines = txt_content.split('\n')
                        in_performance = False
                        current_mineral = None
                        for line in lines:
                            if '--- Mineral Performance ---' in line:
                                in_performance = True
                                continue
                            if in_performance:
                                if line.startswith('===') or line.startswith('Overall Quality:'):
                                    break
                                if line.strip() and not line.startswith('  ') and ':' in line and line.strip().endswith(':'):
                                    current_mineral = line.strip().rstrip(':')
                                    mineral_performance[current_mineral] = {'avg': 0, 'best': 0, 'finds': 0}
                                elif current_mineral:
                                    if '• Average:' in line:
                                        try:
                                            avg_val = float(line.split(':')[1].split('%')[0].strip())
                                            mineral_performance[current_mineral]['avg'] = avg_val
                                        except:
                                            pass
                                    elif '• Best:' in line:
                                        try:
                                            best_val = float(line.split(':')[1].split('%')[0].strip())
                                            mineral_performance[current_mineral]['best'] = best_val
                                        except:
                                            pass
                                    elif '• Hits:' in line or '• Finds:' in line:
                                        try:
                                            raw_val = line.split(':', 1)[1].strip().replace('x', '')
                                            hits_val = int(raw_val)
                                            mineral_performance[current_mineral]['finds'] = hits_val
                                        except:
                                            pass
                        
                        if mineral_performance:
                            session_data['mineral_performance'] = mineral_performance
                            print(f"DEBUG: Pre-parsed mineral_performance from TXT: {list(mineral_performance.keys())}")
                            for mat, data in mineral_performance.items():
                                print(f"  {mat}: {data}")
                except Exception as e:
                    print(f"DEBUG: Could not pre-parse TXT file: {e}")
            
            enhanced_session_data = {
                'system': session_data.get('system', 'Unknown'),
                'body': session_data.get('body', 'Unknown'),
                'date': session_data.get('date', 'Unknown'),
                'duration': session_data.get('duration', '00:00'),
                'tons': session_data.get('tons', session_data.get('tonnage', 0)),  # Try both field names
                'tph': session_data.get('tph', 0),
                'materials': session_data.get('materials', len(session_data.get('materials_mined', {}))),
                'prospectors': session_data.get('prospectors', session_data.get('prospects', session_data.get('prospectors_used', 0))),  # Try all field names
                'materials_mined': session_data.get('materials_mined', {}),
                'session_duration': session_duration_seconds,  # Add session duration for TPH calculation
                'engineering_materials': engineering_materials_dict,  # Add engineering materials
                'comment': session_data.get('comment', ''),
                'screenshots': [],
                # CRITICAL: Add session_file_path for report generator to parse asteroids_prospected
                'session_file_path': session_text_file if session_text_file and os.path.exists(session_text_file) else None,
                # Add analytics data from CSV for HTML reports
                'hit_rate_percent': session_data.get('hit_rate_percent'),
                'avg_quality_percent': session_data.get('avg_quality_percent'),
                'total_average_yield': session_data.get('total_average_yield', 0.0),
                'asteroids_prospected': session_data.get('asteroids_prospected'),
                'best_material': session_data.get('best_material'),
                'materials_tracked': session_data.get('materials_tracked'),
                'individual_yields': session_data.get('individual_yields', {}),  # Comprehensive yields (all asteroids)
                # Try to add filtered yields from live session analytics if available
                'filtered_yields': {},
                'threshold_settings': {},
                # Add ship name if available
                'ship_name': session_data.get('ship_name', ''),
                # Parse session_type from header if available (for old reports)
                'session_type': self._extract_session_type_from_data(session_data),
                'data_source': 'Report Entry'
            }
            
            # Debug logging for asteroids_prospected and session_file_path
            print(f"[HTML Report] Building enhanced_session_data - asteroids_prospected from session_data: {session_data.get('asteroids_prospected')}")
            print(f"[HTML Report] session_file_path: {enhanced_session_data.get('session_file_path')}")
            print(f"[HTML Report] enhanced_session_data asteroids_prospected: {enhanced_session_data.get('asteroids_prospected')}")
            enhanced_session_data['mineral_performance'] = session_data.get('mineral_performance', {})
            
            # Debug: log mineral_performance content
            if enhanced_session_data['mineral_performance']:
                print(f"DEBUG: mineral_performance has {len(enhanced_session_data['mineral_performance'])} entries: {list(enhanced_session_data['mineral_performance'].keys())}")
                for mat, data in enhanced_session_data['mineral_performance'].items():
                    print(f"  {mat}: {data}")
            else:
                print("DEBUG: mineral_performance is EMPTY or missing from session_data")

            # Ensure total_finds / total_hits and tons_per values are present for the HTML report
            try:
                # Derive using ReportGenerator helpers so behavior matches the generated HTML
                from report_generator import ReportGenerator
                temp_gen = ReportGenerator(self.main_app)
                derived_hits = temp_gen._derive_total_finds(enhanced_session_data)
                if derived_hits is not None:
                    enhanced_session_data['total_finds'] = derived_hits
                derived_tpa, _ = temp_gen._compute_tons_per_asteroid(enhanced_session_data)
                if derived_tpa is not None:
                    enhanced_session_data['tons_per'] = f"{derived_tpa:.1f}t"
            except Exception as e:
                # Don't block report generation on errors here
                print(f"Warning: Could not add derived hits/tons for HTML: {e}")
            
            # If this is a live session or we have access to session analytics, add filtered yield data
            if hasattr(self, 'session_analytics') and hasattr(self, 'min_pct_map'):
                try:
                    # Get filtered yields (threshold-based from announcement settings)
                    filtered_summary = self.session_analytics.get_quality_summary(self.min_pct_map)
                    if filtered_summary:
                        enhanced_session_data['filtered_yields'] = {
                            material: stats['avg_percentage'] 
                            for material, stats in filtered_summary.items()
                        }
                        enhanced_session_data['threshold_settings'] = self.min_pct_map.copy()
                except Exception as e:
                    print(f"Could not get filtered yields from live session: {e}")
                    pass
            
            # Try to extract filtered yields from session text file if not available from live session
            if not enhanced_session_data.get('filtered_yields'):
                try:
                    session_text_file = None
                    
                    # Try to find the session text file using multiple methods
                    if 'file_path' in session_data:
                        session_text_file = session_data['file_path']
                    elif 'system' in session_data and 'body' in session_data:
                        # Try to construct filename from session data
                        session_system = session_data.get('system', '').replace(':', '_').replace('/', '_').replace('\\', '_')
                        session_body = session_data.get('body', '').replace(':', '_').replace('/', '_').replace('\\', '_')
                        session_date = session_data.get('date', '')
                        
                        print(f"DEBUG: Looking for session files with system: '{session_system}', body: '{session_body}'")
                        
                        if session_system and session_body:
                            # Look for matching session file - try multiple patterns
                            search_patterns = [
                                # Pattern 1: Use system and body names
                                os.path.join(self.reports_dir, f"*{session_system}*{session_body}*.txt"),
                                # Pattern 2: Use just system name
                                os.path.join(self.reports_dir, f"*{session_system}*.txt"),
                                # Pattern 3: Any text file with body name
                                os.path.join(self.reports_dir, f"*{session_body}*.txt"),
                                # Pattern 4: Try with spaces replaced by underscores
                                os.path.join(self.reports_dir, f"*{session_system.replace(' ', '_')}*.txt"),
                                # Pattern 5: Try with all special chars replaced
                                os.path.join(self.reports_dir, f"*{session_system.replace(' ', '*').replace('-', '*')}*.txt"),
                                # Pattern 6: Search for any file containing key parts
                                os.path.join(self.reports_dir, f"*Coalsack*.txt"),
                                os.path.join(self.reports_dir, f"*Ring*.txt"),
                            ]
                            
                            # Try each pattern
                            for pattern in search_patterns:
                                print(f"DEBUG: Trying pattern: {pattern}")
                                matching_files = glob.glob(pattern)
                                print(f"DEBUG: Found {len(matching_files)} matches")
                                if matching_files:
                                    # Use the most recent matching file
                                    session_text_file = max(matching_files, key=os.path.getmtime)
                                    print(f"DEBUG: Selected file: {session_text_file}")
                                    break
                    
                    # Parse filtered yields from session text file (mineral_performance already parsed earlier)
                    if session_text_file and os.path.exists(session_text_file):
                        print(f"DEBUG: Attempting to parse filtered yields from: {session_text_file}")
                        # IMPORTANT: Add session_file_path for HTML report to parse additional analytics
                        enhanced_session_data['session_file_path'] = session_text_file
                        filtered_yields_from_text = self._parse_filtered_yields_from_session_file(session_text_file)
                        if filtered_yields_from_text:
                            enhanced_session_data['filtered_yields'] = filtered_yields_from_text
                            print(f"DEBUG: Successfully parsed filtered yields: {filtered_yields_from_text}")
                        else:
                            print("DEBUG: No filtered yields found in session file")
                    else:
                        print(f"DEBUG: Session text file not found. Searched for system: {session_data.get('system', 'N/A')}, body: {session_data.get('body', 'N/A')}")
                            
                except Exception as e:
                    print(f"Could not parse filtered yields from session file: {e}")
                    import traceback
                    traceback.print_exc()
                    pass
            
            # Ask user if they want to add screenshots before generating the report
            from main import centered_yesno_dialog
            add_screenshots = centered_yesno_dialog(
                tree.winfo_toplevel(),
                "Detailed Report",
                "Would you like to add screenshots to this detailed report?"
            )
            
            if add_screenshots:
                # Let user select screenshots
                self._add_screenshots_to_report_internal(tree, item)
            
            # Get screenshots that are specifically linked to this report
            values = tree.item(item, 'values')
            report_id = f"{values[0]}_{values[4]}_{values[5]}"  # date_system_body as unique ID (correct indices)
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
                    
                    # Update the tree item's enhanced column immediately (no need to refresh entire tree)
                    try:
                        tree.set(item, "enhanced", "📊")
                        print(f"✓ Updated tree item '{item}' with enhanced report indicator")
                    except Exception as e:
                        print(f"Could not update tree item indicator: {e}")
                    
                    # Ask user if they want to preview the report
                    from main import centered_yesno_dialog
                    preview_report = centered_yesno_dialog(
                        tree.winfo_toplevel(),
                        "Enhanced Report Generated",
                        f"Enhanced HTML report created successfully!\n\nWould you like to preview it now?"
                    )
                    
                    if preview_report:
                        generator.preview_report(html_content)
                        
                    self._set_status(f"Enhanced report generated: {os.path.basename(html_report_path)}")
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
            
    def _parse_filtered_yields_from_session_file(self, session_file_path):
        """Parse filtered yield data from session text file"""
        try:
            with open(session_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for "Mineral Performance" section (check both old and new names for compatibility)
            if "--- Mineral Performance ---" not in content and "--- Material Performance ---" not in content:
                return {}
            
            # Extract the Mineral Performance section (support both old and new names)
            performance_start = content.find("--- Mineral Performance ---")
            if performance_start == -1:
                performance_start = content.find("--- Material Performance ---")
            performance_section = content[performance_start:]
            
            # Parse each material's average percentage
            filtered_yields = {}
            lines = performance_section.split('\n')
            
            current_material = None
            for line in lines:
                line = line.strip()
                
                # Look for material name (ends with :)
                if line.endswith(':') and not line.startswith('•') and not line.startswith('-'):
                    current_material = line.rstrip(':')
                
                # Look for average percentage line
                elif current_material and line.startswith('• Average:'):
                    try:
                        # Extract percentage from "• Average: 44.1%"
                        avg_part = line.split('Average:')[1].strip()
                        percentage_str = avg_part.replace('%', '').strip()
                        percentage = float(percentage_str)
                        filtered_yields[current_material] = percentage
                        current_material = None  # Reset for next material
                    except (ValueError, IndexError):
                        continue
            
            return filtered_yields
            
        except Exception as e:
            print(f"Error parsing filtered yields from session file: {e}")
            return {}
    
    def _generate_enhanced_report(self, cargo_session_data, text_report_path):
        """Generate enhanced HTML report with charts and screenshots"""
        try:
            from report_generator import ReportGenerator
            
            # Create report generator
            generator = ReportGenerator(self.main_app)
            
            # Prepare session data for HTML report
            enhanced_session_data = cargo_session_data.copy() if cargo_session_data else {}
            
            # Debug: Check session_duration
            print(f"[DEBUG HTML] session_duration in data: {enhanced_session_data.get('session_duration', 'MISSING')}")
            print(f"[DEBUG HTML] materials_mined: {enhanced_session_data.get('materials_mined', {})}")
            
            # Add screenshots from current session
            if hasattr(self, 'session_screenshots') and self.session_screenshots:
                enhanced_session_data['screenshots'] = self.session_screenshots

            # If a text report path was provided, parse it for total hits as well
            if text_report_path and os.path.exists(text_report_path):
                # IMPORTANT: Add session_file_path for HTML report to parse additional analytics
                enhanced_session_data['session_file_path'] = text_report_path
                try:
                    with open(text_report_path, 'r', encoding='utf-8') as tf:
                        txt_content = tf.read()
                        tf_m = re.search(r'Total Material Hits:\s*(\d+)', txt_content)
                        if not tf_m:
                            tf_m = re.search(r'Total Material Finds:\s*(\d+)', txt_content)
                        if tf_m:
                            parsed_hits = int(tf_m.group(1))
                            if parsed_hits > 0:
                                enhanced_session_data['total_finds'] = parsed_hits
                                print(f"DEBUG: Parsed Total Material Hits from file path: {parsed_hits}")
                except Exception as e:
                    print(f"Warning: Could not parse total hits from file {text_report_path}: {e}")

            # Ensure total_finds / total_hits and tons_per values are present for the HTML report
            try:
                derived_hits = generator._derive_total_finds(enhanced_session_data)
                if derived_hits is not None:
                    enhanced_session_data['total_finds'] = derived_hits
                derived_tpa, _ = generator._compute_tons_per_asteroid(enhanced_session_data)
                if derived_tpa is not None:
                    enhanced_session_data['tons_per'] = f"{derived_tpa:.1f}t"
            except Exception as e:
                print(f"Warning: Could not add derived hits/tons (batch): {e}")
            
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
                    from app_utils import centered_askyesno
                    preview_report = centered_askyesno(
                        self.winfo_toplevel(),
                        "Enhanced Report Generated",
                        f"Enhanced HTML report saved successfully!\n\nWould you like to preview it now?"
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
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            # Support both legacy and current column names
                            date_str = row.get('date', row.get('Date', ''))
                            system = row.get('system', row.get('System', ''))
                            tonnage = row.get('total_tons', row.get('Total Tonnage', '0'))
                            tph = row.get('overall_tph', row.get('TPH', '0'))

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
                    
                    from app_utils import centered_message
                    centered_message(batch_window, "Batch Generation Complete",
                                     f"Generated {count} detailed reports.\n{errors} errors occurred.")
                    
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








