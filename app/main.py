#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EliteMining - Elite Dangerous Mining Assistant
Copyright (C) 2024-2026 Viper-Dude

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
"""
from ui.striped_treeview import StripedTreeview
from ui.themed_checkbox import ThemedCheckbutton, ThemedRadiobutton
from ui.theme import modern_color
from ui.color_swatches import ColorSwatchPicker
from ui.segmented_selector import SegmentedSelector
from ui.stepper import Stepper
from ui.themed_slider import ThemedSlider, slider_colors

import os
import sys
import logging

# Set DPI awareness BEFORE importing tkinter to prevent scaling issues
# Use System DPI awareness (1) for better compatibility with saved geometry
try:
    import ctypes
    # Use System DPI awareness - safer for multi-monitor and geometry restoration
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        # Fallback to older method
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass  # Non-Windows or older Windows version

# Initialize logging for installer version (per-session logs with auto-cleanup)
from logging_setup import setup_logging, install_exception_hooks, LOG_FORMAT, SafeRotatingFileHandler
log_file = setup_logging()  # Only activates when running as packaged executable
if log_file:
    try:
        print(f"[OK] Logging enabled: {log_file}")
    except UnicodeEncodeError:
        print(f"Logging enabled: {log_file}")

# Determine app directory for both PyInstaller and script execution
if hasattr(sys, '_MEIPASS'):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

import json
import glob
import re
import shutil
import datetime as dt
import logging
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Dict, Optional, Any, List
import sys
import threading
import time
import zipfile
import announcer

# Initialize localization system FIRST - before other imports that depend on it
try:
    from localization import init as init_localization, t as _t, get_language, get_station_types, get_sort_options, get_age_options, get_material, to_english
    init_localization()
    print(f"[MAIN] Localization initialized. Language: {get_language()}")
    print(f"[MAIN] Test translation: tabs.mining_session = {_t('tabs.mining_session')}")
    
    def t(key, **kwargs):
        """Safe translation function that won't crash if localization fails"""
        try:
            result = _t(key, **kwargs)
            return result
        except Exception as ex:
            log.error(f"[MAIN] t() error for {key}: {ex}")
            return key.split('.')[-1]  # Return last part of key as fallback
except Exception as e:
    print(f"[WARNING] Could not initialize localization: {e}")
    def t(key, **kwargs):
        """Fallback translation - returns last part of key"""
        return key.split('.')[-1]

# Now import modules that depend on localization
from ring_finder import RingFinder
from marketplace_api import MarketplaceAPI
from config import _load_cfg, _save_cfg, flush_config, load_saved_va_folder, save_va_folder, load_window_geometry, save_window_geometry
from version import get_version, UPDATE_CHECK_URL, UPDATE_CHECK_INTERVAL
from update_checker import UpdateChecker
from journal_parser import JournalParser
from app_utils import get_app_icon_path, set_window_icon, get_app_data_dir, get_variables_dir, get_ship_presets_dir, compact_classic_button, create_action_button

# Import UI components from ui module
from ui.entry_context_menu import show_entry_context_menu
from ui.theme import THEME_ELITE_ORANGE, THEME_DARK_GRAY, get_theme_colors, next_theme
from ui.tooltip import ToolTip
from ui.dialogs import centered_yesno_dialog, center_window, centered_info_dialog, set_translate_func

# Set up translation for dialogs module
set_translate_func(t)
from path_utils import get_ship_presets_dir, get_reports_dir


SHIP_TYPES = (
    'Adder',
    'Alliance Challenger',
    'Alliance Chieftain',
    'Alliance Crusader',
    'Anaconda',
    'Anaconda Mk II',
    'Asp Explorer',
    'Asp Scout',
    'Beluga Liner',
    'Caspian Explorer',
    'Cobra Mk III',
    'Cobra Mk IV',
    'Cobra Mk V',
    'Corsair',
    'Diamondback Explorer',
    'Diamondback Scout',
    'Dolphin',
    'Eagle Mk II',
    'Federal Assault Ship',
    'Federal Corvette',
    'Federal Dropship',
    'Federal Gunship',
    'Fer-de-Lance',
    'Hauler',
    'Imperial Clipper',
    'Imperial Courier',
    'Imperial Cutter',
    'Imperial Eagle',
    'Keelback',
    'Kestrel Mk II',
    'Krait Mk II',
    'Krait Phantom',
    'Mamba',
    'Mandalay',
    'Orca',
    'Panther Clipper Mk II',
    'Python',
    'Python Mk II',
    'Sidewinder Mk I',
    'Type-6 Transporter',
    'Type-7 Transporter',
    'Type-8 Transporter',
    'Type-9 Heavy',
    'Type-10 Defender',
    'Type-11 Prospector',
    'Viper Mk III',
    'Viper Mk IV',
    'Vulture',
)


from overlays import (
    TextOverlay, CargoTextOverlay,
    _foreground_window_title, is_game_focused, _find_game_window_rect, get_game_monitor_offset,
)


APP_TITLE = "EliteMining"
APP_VERSION = "v5.7.4"
PRESET_INDENT = "   "  # spaces used to indent preset names

LOG_FILE = os.path.join(os.path.expanduser("~"), "EliteMining.log")

if not log_file:
    _handler = SafeRotatingFileHandler(LOG_FILE, maxBytes=512*1024, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[_handler], format=LOG_FORMAT)
install_exception_hooks()
log = logging.getLogger("EliteMining")

# --- Safe text write (atomic) ---
def _atomic_write_text(path: str, text: str) -> None:
    """
    Write small text files atomically so VoiceAttack never reads partial content.
    """
    try:
        folder = os.path.dirname(path) or "."
        os.makedirs(folder, exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
        # On Windows, replace is atomic for same-volume paths (Python 3.8+).
        os.replace(tmp_path, path)
    except PermissionError:
        # File likely locked by VoiceAttack - direct write as fallback
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        # Clean up temp file if it exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    except Exception as e:
        try:
            # Best effort fallback (non-atomic)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        # Clean up temp file if it exists
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
        log.exception("Atomic write failed for %s: %s", path, e)

# --- Firegroup letters and NATO mapping (files use NATO words) ---
from core.constants import (
    FIREGROUPS, NATO, NATO_REVERSE,
    VA_VARS, VA_TTS_ANNOUNCEMENT, TOOL_ORDER,
    ANNOUNCEMENT_TOGGLES, TOGGLES, PRESET_EXCLUDED_TOGGLES, SOUND_EVENT_CATEGORIES, TIMERS, MENU_COLORS, MINING_MATERIALS
)

# -------------------- Config helpers (persist VA folder, window geometry, etc.) --------------------

# -------------------- VA folder detection --------------------
def detect_va_folder_interactive(parent: tk.Tk) -> Optional[str]:
    saved = load_saved_va_folder()
    if saved:
        return saved
    
    # For installer/frozen mode, use executable location
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # Structure: ...\EliteMining\Configurator\EliteMining.exe
        # Need: ...\EliteMining
        if os.path.basename(exe_dir).lower() == 'configurator':
            app_root = os.path.dirname(exe_dir)  # Go up to EliteMining folder
            save_va_folder(app_root)
            return app_root
    else:
        # Dev mode: running from source - use project root (parent of 'app' folder)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(script_dir).lower() == 'app':
            dev_root = os.path.dirname(script_dir)  # Go up to project root
            print(f"[DEV MODE] Using project root: {dev_root}")
            save_va_folder(dev_root)
            return dev_root
    
    # Try VA install locations
    candidates = [
        r"D:\SteamLibrary\steamapps\common\VoiceAttack 2\Apps\EliteMining",
        r"D:\SteamLibrary\steamapps\common\VoiceAttack\Apps\EliteMining",
        r"C:\Program Files (x86)\VoiceAttack\Apps\EliteMining",
    ]
    for c in candidates:
        if os.path.isdir(c):
            save_va_folder(c)
            return c
    
    # Ask user to select folder
    folder = filedialog.askdirectory(parent=parent, title="Select your EliteMining installation folder")
    if folder and os.path.isdir(folder):
        save_va_folder(folder)
        return folder
    return None

from cargo_monitor import CargoMonitor
from route_tab import RouteTab

from prospector_panel import ProspectorPanel

# -------------------- Main GUI --------------------

from column_visibility_helper import ColumnVisibilityMixin, displayed_column
from voiceattack_controls_tab import VoiceAttackControlsTabMixin
from commodity_market_tab import CommodityMarketTabMixin
from distance_calculator_tab import DistanceCalculatorTabMixin
from star_systems_tab import StarSystemsTabMixin

class App(tk.Tk, ColumnVisibilityMixin, VoiceAttackControlsTabMixin, CommodityMarketTabMixin, DistanceCalculatorTabMixin, StarSystemsTabMixin):
    def _set_dark_title_bar(self):
        """Placeholder - title bar uses default Windows styling (light/white)"""
        # Dark title bar was too black - keeping default Windows title bar
        pass
    
    def __init__(self) -> None:
        try:
            super().__init__()
            
            # Prevent window from stealing focus on startup (important for gaming)
            # Window starts hidden and is shown later without grabbing focus
            self.withdraw()

            # --- Show splash screen immediately so user sees something during init ---
            self._splash = None
            self._splash_photo = None  # prevent GC
            self._splash_status_var = None
            self._startup_dialog_active = False
            try:
                from PIL import Image, ImageTk
                from config import load_window_geometry
                _saved_geom = load_window_geometry()
                _geom_str = _saved_geom.get("geometry", "")
                _app_x, _app_y, _app_w, _app_h = 0, 0, 1350, 780
                if _geom_str:
                    import re as _re
                    _gm = _re.match(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', _geom_str)
                    if _gm:
                        _app_w, _app_h, _app_x, _app_y = int(_gm.group(1)), int(_gm.group(2)), int(_gm.group(3)), int(_gm.group(4))
                self._splash = tk.Toplevel(self)
                self._splash.overrideredirect(True)
                self._splash.attributes('-topmost', True)
                # Use module-level app_dir (local 'app_dir' assigned later in __init__ shadows the global)
                _app_dir = globals()['app_dir']
                if getattr(sys, 'frozen', False):
                    _splash_img_path = os.path.join(os.path.dirname(_app_dir), "app", "Images", "EliteMining_splash.png")
                else:
                    _splash_img_path = os.path.join(_app_dir, "Images", "EliteMining_splash.png")
                _pil_img = Image.open(_splash_img_path)
                _max_w, _max_h = 950, 560
                _pil_img.thumbnail((_max_w, _max_h), Image.LANCZOS)
                _sw, _sh = _pil_img.size
                self._splash_photo = ImageTk.PhotoImage(_pil_img)
                _sx = _app_x + (_app_w - _sw) // 2
                _sy = _app_y + (_app_h - _sh) // 2
                self._splash.configure(bg="#000000")
                tk.Label(self._splash, image=self._splash_photo, bd=0, bg="#000000").pack()
                self._splash_status_var = tk.StringVar(value="Starting EliteMining...")
                tk.Label(self._splash, textvariable=self._splash_status_var, bg="#000000",
                         fg="#cccccc", font=("Segoe UI", 9)).pack(pady=(0, 6))
                self._splash.update_idletasks()
                _sw = max(_sw, self._splash.winfo_reqwidth())
                _sh = self._splash.winfo_reqheight()
                _sx = _app_x + (_app_w - _sw) // 2
                _sy = _app_y + (_app_h - _sh) // 2
                self._splash.geometry(f"{_sw}x{_sh}+{_sx}+{_sy}")
                # Click anywhere to dismiss early
                self._splash.bind("<Button-1>", lambda e: self._dismiss_splash())
                self._splash.update()
            except Exception as _e:
                print(f"[SPLASH] Could not load splash image: {_e}")
                if self._splash:
                    try:
                        self._splash.destroy()
                    except Exception:
                        pass
                self._splash = None

            # Check and migrate config if needed on startup
            self._check_config_migration()
        except Exception as e:
            # Log error to file BEFORE showing dialog
            import traceback
            error_details = traceback.format_exc()
            try:
                crash_log_path = os.path.join(app_dir, "init_crash_log.txt")
                with open(crash_log_path, "w", encoding="utf-8") as f:
                    f.write(f"EliteMining Initialization Crash\n")
                    f.write(f"Time: {dt.datetime.now()}\n")
                    f.write(f"Error: {str(e)}\n\n")
                    f.write(error_details)
            except:
                pass
            
            # Try to show error dialog
            try:
                messagebox.showerror(
                    "EliteMining - Initialization Error",
                    f"Failed to initialize EliteMining:\n\n{str(e)}\n\n"
                    f"Crash log saved to:\n{crash_log_path}\n\n"
                    f"Please report this error."
                )
            except:
                pass
            raise

        # --- UI scale factor (applied to fonts/row heights below) ---
        from config import load_ui_scale
        self.ui_scale = load_ui_scale()  # 1.0 = 100%

        def _scaled_font(base_size, weight="normal"):
            size = round(base_size * self.ui_scale)
            return ("Segoe UI", size) if weight == "normal" else ("Segoe UI", size, weight)

        def _scaled_px(base_px):
            return round(base_px * self.ui_scale)

        self._scaled_font = _scaled_font
        self._scaled_px = _scaled_px

        # Scale Tk's named default fonts too — ttk.Entry/Combobox render their
        # text via TkTextFont/TkDefaultFont regardless of style.configure(font=...)
        if self.ui_scale != 1.0:
            import tkinter.font as tkfont
            for _font_name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkTooltipFont"):
                try:
                    _f = tkfont.nametofont(_font_name)
                    _f.configure(size=round(_f.cget("size") * self.ui_scale))
                except Exception:
                    pass

        # --- Force clam theme for Treeview so dark styling works on Windows ---
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass


        # --- Dark style for Spinbox ---
        style.configure("TSpinbox",
                        fieldbackground="#1e1e1e",
                        background="#1e1e1e",
                        foreground="#ffffff",
                        arrowcolor="#ffffff")

        # NOTE: TEntry and Treeview styling moved to after theme_colors is defined (see below)

        # --- Dark style for Scrollbars ---
        style.configure("Vertical.TScrollbar",
                        background="#000000",
                        troughcolor="#000000",
                        bordercolor="#000000",
                        arrowcolor="#ffffff",
                        width=12)
        
        # Configure just the thumb (draggable box)
        style.element_create("Vertical.Scrollbar.thumb", "from", "clam")
        style.layout("Vertical.TScrollbar", [
            ('Vertical.Scrollbar.trough', {'children': [
                ('Vertical.Scrollbar.thumb', {'expand': '1'})
            ]})
        ])
        style.configure("Vertical.Scrollbar.thumb", background="#4a4a4a")
        style.map("Vertical.TScrollbar", 
                  background=[("active", "#000000")])
        style.map("Vertical.Scrollbar.thumb",
                  background=[("active", "#666666")])

        # NOTE: darkrow tag configured later after tree is created

        # --- Green accent button style (like ring finder buttons) ---
        style.configure("Accent.TButton",
                        background="#2a4a2a",     # Green tint
                        foreground="#e0e0e0",
                        borderwidth=1,
                        relief="raised",
                        font=_scaled_font(9))
        style.map("Accent.TButton",
                  background=[("active", "#3a5a3a"), ("pressed", "#1a3a1a")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
                  relief=[("pressed", "sunken")])

        # Default button style
        style.configure("TButton",
                        font=_scaled_font(9))


        # --- Force clam theme for Notebook to allow tab styling ---
        try:
            style.theme_use("clam")
        except Exception as e:
            log.error("Theme switch failed: %s", e)

        # Configure horizontal scrollbar too
        style.configure("Horizontal.TScrollbar",
                        background="#000000",
                        troughcolor="#000000",
                        bordercolor="#000000",
                        arrowcolor="#ffffff",
                        width=12)
        
        style.element_create("Horizontal.Scrollbar.thumb", "from", "clam")
        style.layout("Horizontal.TScrollbar", [
            ('Horizontal.Scrollbar.trough', {'children': [
                ('Horizontal.Scrollbar.thumb', {'expand': '1'})
            ]})
        ])
        style.configure("Horizontal.Scrollbar.thumb", background="#4a4a4a")
        style.map("Horizontal.TScrollbar", 
                  background=[("active", "#000000")])
        style.map("Horizontal.Scrollbar.thumb",
                  background=[("active", "#666666")])

        # NOTE: TNotebook styling moved below after theme colors are loaded


        # --- Theme setup based on config ---
        from config import load_theme
        self.current_theme = load_theme()  # 'elite_orange' or 'dark_gray'
        
        # Get centralized theme colors (defined at top of file)
        theme = get_theme_colors(self.current_theme)
        
        # Extract commonly used colors for convenience
        dark_bg = theme["bg"]
        dark_fg = theme["fg"]
        accent = theme["bg_accent"]
        btn_fg = theme["btn_fg"]
        selection_bg = theme["selection_bg"]
        selection_fg = theme["selection_fg"]
        
        # Store full theme colors for access elsewhere
        self.theme_colors = theme
        
        style.configure(".", background=dark_bg, foreground=dark_fg)
        style.configure("TLabel", background=dark_bg, foreground=dark_fg)
        style.configure("TFrame", background=dark_bg)
        
        # Theme-aware Notebook tab styling
        style.configure("TNotebook", background=accent, borderwidth=0)
        style.configure("TNotebook.Tab",
                        background=accent,
                        foreground=dark_fg,
                        padding=[_scaled_px(8), _scaled_px(4)],
                        relief="raised",
                        borderwidth=1,
                        font=_scaled_font(9))
        style.map("TNotebook.Tab",
                   background=[("selected", dark_bg)],
                   foreground=[("selected", dark_fg)])

        # Custom dark button style
        style.configure("Dark.TButton", background="#333333", foreground=btn_fg, font=_scaled_font(9, "bold"))
        style.configure("Small.TButton", padding=(4, 0), font=_scaled_font(8))
        style.map("Dark.TButton",
                   background=[("active", "#444444"), ("disabled", "#1a1a1a")],
                   foreground=[("disabled", "#666666")])

        style.configure("TCheckbutton", background=dark_bg, foreground=dark_fg)
        style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
        style.configure("TCombobox", fieldbackground=dark_bg, background=accent, foreground=dark_fg, font=_scaled_font(9))
        style.map("TCombobox",
                   fieldbackground=[("disabled", dark_bg), ("readonly", dark_bg)],
                   foreground=[("disabled", "#666666"), ("readonly", dark_fg)])

        self.bind_class("Treeview", "<Escape>", lambda e: e.widget.selection_remove(*e.widget.selection()), add="+")
        for widget_class in ("Entry", "TEntry", "TCombobox"):
            self.bind_class(widget_class, "<Button-3>", show_entry_context_menu, add="+")

        # Apply dark theme to classic widgets too
        self.option_add("*Listbox.background", dark_bg)
        self.option_add("*Listbox.foreground", dark_fg)
        self.option_add("*Entry.background", accent)
        self.option_add("*Entry.foreground", dark_fg)
        self.option_add("*Text.background", dark_bg)
        self.option_add("*Text.foreground", dark_fg)
        self.option_add("*TMenubutton.background", dark_bg)
        self.option_add("*TMenubutton.foreground", dark_fg)
        self.option_add("*Checkbutton.background", dark_bg)
        self.option_add("*Checkbutton.foreground", dark_fg)
        self.option_add("*Checkbutton.selectColor", "#333333")
        self.option_add("*Checkbutton.activeBackground", dark_bg)
        self.option_add("*Checkbutton.activeForeground", dark_fg)

        # --- Dark style for Entry fields (theme-aware) ---
        style.configure("TEntry",
                        fieldbackground=dark_bg,
                        foreground=dark_fg,
                        insertcolor=dark_fg,
                        font=_scaled_font(9))

        # Global Treeview styling (theme-aware)
        style.configure("Treeview",
                        background=dark_bg,
                        fieldbackground=dark_bg,
                        foreground=dark_fg,
                        borderwidth=0,
                        font=_scaled_font(9),
                        rowheight=_scaled_px(25))  # Base row height scaled by ui_scale
        style.map("Treeview",
                   background=[("selected", selection_bg)],
                   foreground=[("selected", selection_fg)])

        style.configure("Treeview.Heading",
                        background=accent,
                        foreground=dark_fg,
                        relief="raised",
                        font=_scaled_font(9, "bold"))
        style.map("Treeview.Heading",
                   background=[("active", "#333333"), ("pressed", dark_bg)],
                   foreground=[("active", dark_fg), ("pressed", dark_fg)])

        if self.current_theme in ("modern", "modern_slate", "modern_orange"):
            self._apply_modern_styles(style, theme, _scaled_font, _scaled_px)
            try:
                from ui.modern_widgets import install_modern_buttons
                install_modern_buttons()
            except Exception:
                log.exception("Modern button install failed")
            self.option_add("*TCombobox*Listbox.background", theme["panel"])
            self.option_add("*TCombobox*Listbox.foreground", theme["fg"])
            self.option_add("*TCombobox*Listbox.selectBackground", theme["selection_bg"])
            self.option_add("*TCombobox*Listbox.selectForeground", theme["selection_fg"])

        self.title(f"{APP_TITLE} — {APP_VERSION}")
        self.resizable(True, True)
        self.minsize(1050, 680)  # Minimum width to fit all status bar info
        
        # Withdraw window initially to prevent flash on wrong monitor
        self.withdraw()
        
        # Set window class name for better Windows integration (PowerToys compatibility)
        try:
            self.wm_class("EliteMining", "EliteMining")
        except:
            pass
        
        # Set additional window attributes for better Windows tool compatibility
        try:
            # Make window more recognizable to Windows tools like PowerToys
            self.attributes('-toolwindow', False)  # Show in taskbar
            # Don't use focus_force() - it steals focus from game when app starts
        except Exception as e:
            log.error(f"Window attributes setup failed: {e}")

        # Don't restore geometry here - will be done after widgets load
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Two-column layout: balanced dashboard + narrower presets sidebar
        self.columnconfigure(0, weight=2, minsize=300)   # Dashboard content (tabs) - balanced
        self.columnconfigure(1, weight=1, minsize=250)   # Ship Presets sidebar - narrower
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)      # CMDR info / buttons row
        self.rowconfigure(2, weight=0)      # Status bar

        # Resolve installation folder (VA or standalone)
        self.va_root = detect_va_folder_interactive(self)
        if not self.va_root:
            messagebox.showerror("Installation folder not found", "No EliteMining installation folder selected.")
            self.destroy()
            return
        
        # Use centralized path utilities for consistent dev/installer handling
        self.vars_dir = get_variables_dir()  # Variables folder (dev-aware)
        self.settings_dir = get_ship_presets_dir()  # Ship Presets (dev-aware)
        
        # Load commodities database for trade market tab
        self.commodities_data = {}
        try:
            # Use get_app_data_dir() for installer compatibility
            if getattr(sys, 'frozen', False):
                commodities_path = os.path.join(get_app_data_dir(), 'data', 'commodities.json')
            else:
                commodities_path = os.path.join(os.path.dirname(__file__), 'data', 'commodities.json')
            with open(commodities_path, 'r', encoding='utf-8') as f:
                self.commodities_data = json.load(f)
            log.info(f"Loaded {len(self.commodities_data)} commodity categories")
        except Exception as e:
            log.error(f"Failed to load commodities.json: {e}")
            self.commodities_data = {}
            
        # Initialize cargo monitor with correct app directory (after va_root is set)
        self._set_splash_status("Preparing hotspot database...")
        app_dir = get_app_data_dir() if getattr(sys, 'frozen', False) else None
        self.cargo_monitor = CargoMonitor(update_callback=self._on_cargo_changed,
                                        capacity_changed_callback=self._on_cargo_capacity_detected,
                                        ship_info_changed_callback=self._on_ship_info_changed,
                                        app_dir=app_dir)
        # Set the main app reference so cargo monitor can access prospector panel later
        self.cargo_monitor.main_app_ref = self
        self.cargo_monitor.add_journal_listener(self._on_journal_pledge_events)
        self._set_splash_status("Preparing interface...")

        # Centralized current system tracking (single source of truth)
        self.current_system = ""
        self.current_system_coords = None
        
        # Only create Variables folder if it's in a VA installation path
        if 'VoiceAttack' in self.va_root or os.path.exists(os.path.join(self.va_root, '..', 'VoiceAttack.exe')):
            os.makedirs(self.vars_dir, exist_ok=True)
        
        os.makedirs(self.settings_dir, exist_ok=True)

        # Set window icon using centralized function
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                self.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                self.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception as e:
            log.error("Icon load failed: %s", e)


        # Model vars
        self.tool_fg: Dict[str, tk.StringVar] = {t: tk.StringVar(value="") for t in TOOL_ORDER}
        self.tool_btn: Dict[str, tk.IntVar] = {t: tk.IntVar(value=0) for t in TOOL_ORDER if VA_VARS[t]["btn"] is not None}
        self.toggle_vars: Dict[str, tk.IntVar] = {name: tk.IntVar(value=0) for name in TOGGLES}
        self.timer_vars: Dict[str, tk.Variable] = {
            name: (tk.DoubleVar(value=0.0) if name in self._DECIMAL_TIMERS else tk.IntVar(value=0))
            for name in TIMERS}
        
        # Additional mining control variables (initialized once, not recreated in _build_timers_tab)
        self.laser_extra_repeat_var = tk.IntVar(value=1)
        self.prospector_delay_var = tk.DoubleVar(value=2.6)
        self.thrust_upduration_var = tk.DoubleVar(value=1.5)
        self.thrust_closed_var = tk.DoubleVar(value=1.6)
        self.thrust_open_var = tk.DoubleVar(value=3.8)
        self._ship_diff_widgets = []  # (widget, colour option, normal value, preset data paths[, only-if callable])
        self._ship_diff_tint_pending = False
        
        # Announcement toggles (moved from TOGGLES to Text Overlay section)
        self.announcement_vars: Dict[str, tk.IntVar] = {name: tk.IntVar(value=0) for name in ANNOUNCEMENT_TOGGLES}
        
        # Load saved announcement values before setting up traces
        self._load_announcement_settings()
        
        # Main announcement toggle (master control for all announcements)
        self.main_announcement_enabled = tk.IntVar(value=1)  # Default enabled
        self._load_main_announcement_preference()
        self.main_announcement_enabled.trace('w', self._on_main_announcement_toggle)
        
        # Tracing will be set up after loading from .txt files
        
        # Tooltip enable/disable
        self.tooltips_enabled = tk.IntVar(value=1)  # Default enabled
        self._load_tooltip_preference()
        self.tooltips_enabled.trace('w', self._on_tooltip_toggle)
        
        # Stay on top toggle
        self.stay_on_top = tk.IntVar(value=0)  # Default disabled
        self._load_stay_on_top_preference()
        self.stay_on_top.trace('w', self._on_stay_on_top_toggle)
        
        # Auto-scan journals on startup
        self.auto_scan_journals = tk.IntVar(value=1)  # Default enabled
        self._load_auto_scan_preference()
        self.auto_scan_journals.trace('w', self._on_auto_scan_toggle)
        
        # Auto-search hotspots after FSD jump (syncs with ring_finder)
        self.auto_search_enabled = tk.BooleanVar(value=False)
        self._load_auto_search_preference()
        
        # Auto-switch tabs on ring entry/exit
        self.auto_switch_tabs = tk.IntVar(value=1)  # Default enabled
        self._load_auto_switch_tabs_preference()
        self.auto_switch_tabs.trace('w', self._on_auto_switch_tabs_toggle)
        self._last_ui_activity = time.monotonic()
        for sequence in ('<KeyPress>', '<ButtonPress>', '<MouseWheel>', '<Motion>'):
            self.bind_all(sequence, self._record_ui_activity, add='+')

        # Show Ring Finder Auto Prices on the text overlay (syncs with ring_finder)
        self.auto_prices_overlay = tk.IntVar(value=1 if _load_cfg().get("auto_prices_overlay", False) else 0)
        self.auto_prices_overlay.trace('w', self._on_auto_prices_overlay_toggle)
        self.auto_prices_overlay_duration = tk.IntVar(value=int(_load_cfg().get("auto_prices_overlay_duration", 20)))
        self.auto_prices_overlay_duration.trace('w', self._on_auto_prices_overlay_duration_change)

        # Auto-start session on first prospector launch
        self.auto_start_session = tk.IntVar(value=1)  # Default enabled
        self._load_auto_start_preference()
        self.auto_start_session.trace('w', self._on_auto_start_toggle)
        
        # Prompt to end session when cargo full and idle
        self.prompt_on_cargo_full = tk.IntVar(value=1)  # Default enabled
        self._load_prompt_on_full_preference()
        self.prompt_on_cargo_full.trace('w', self._on_prompt_on_full_toggle)
        
        # Text overlay enable/disable, transparency, and color
        self.text_overlay_enabled = tk.IntVar(value=1)  # Default enabled
        self.text_overlay_transparency = tk.IntVar(value=90)  # Default 90% (0.9 alpha)
        self.text_overlay_color = tk.StringVar(value="White")  # Default white
        self.text_overlay_duration = tk.IntVar(value=7)  # Default 7 seconds (range: 5-30)
        self.overlay_mode = tk.StringVar(value="enhanced")  # "standard" or "enhanced" prospector overlay
        self.prospector_show_all = tk.IntVar(value=0)  # 0=threshold only, 1=all materials
        
        # EDDN sending enable/disable
        self.eddn_send_enabled = tk.IntVar(value=1)  # Default enabled to contribute to community
        
        # Color options optimized for colorblind accessibility - subdued brightness
        self.color_options = {
            "White": "#E8E8E8",        # Soft white - high contrast but not harsh
            "Yellow": "#D4D400",       # Muted yellow, works for most colorblind types
            "Orange": "#CC7000",       # Deuteranopia/Protanopia friendly, less bright
            "Light Blue": "#6BB6D6",   # Tritanopia friendly, softer contrast
            "Light Green": "#7ACC7A",  # Gentle green, readable
            "Light Gray": "#B8B8B8",   # Subtle but readable
            "Cyan": "#00CCCC",         # Softer cyan, colorblind friendly
            "Magenta": "#CC00CC"       # Muted magenta, distinct from most backgrounds
        }
        
        # Text size options for overlay
        self.text_overlay_size = tk.StringVar(value="Normal")  # Default normal size
        self.size_options = {
            "Small": 10,      # Small text (reduced from 12)
            "Normal": 13,     # Normal text
            "Large": 15       # Large text
        }
        
        # Initialize text overlay for TTS announcements (before loading preferences)
        self.text_overlay = TextOverlay()
        self.cargo_text_overlay = CargoTextOverlay()
        
        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Cargo monitor preferences
        self.cargo_max_capacity = tk.IntVar(value=200)
        self.cargo_show_in_overlay = tk.BooleanVar(value=True)
        self.overlay_only_game_focused = tk.BooleanVar(value=True)
        self.cargo_text_overlay.focus_blocked = lambda: self.overlay_only_game_focused.get() and not is_game_focused()
        self.hide_overlays_in_supercruise = tk.BooleanVar(value=False)
        self.overlay_only_mining_session = tk.BooleanVar(value=False)
        self._in_supercruise = False  # Track current supercruise state

        self._load_cargo_preferences()
        pending_capacity = getattr(self, '_pending_detected_capacity', None)
        if pending_capacity is not None:
            self._pending_detected_capacity = None
            try:
                self._on_cargo_capacity_detected(pending_capacity)
            except Exception:
                log.exception("Applying detected cargo capacity at startup failed")

        self._load_text_overlay_preference()
        self.text_overlay_enabled.trace('w', self._on_text_overlay_toggle)
        self.text_overlay_transparency.trace('w', self._on_transparency_change)
        self.text_overlay_color.trace('w', self._on_color_change)
        self.text_overlay_size.trace('w', self._on_size_change)
        self.text_overlay_duration.trace('w', self._on_duration_change)
        self.overlay_mode.trace('w', self._on_overlay_mode_change)
        self.prospector_show_all.trace('w', self._on_show_all_change)
        
        # Cargo monitor traces
        self.cargo_max_capacity.trace('w', self._on_cargo_capacity_change)
        self.cargo_show_in_overlay.trace('w', self._on_cargo_overlay_toggle)
        self.hide_overlays_in_supercruise.trace('w', lambda *a: self._save_cargo_preferences())

        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Initialize update checker with app directory (not settings dir)
        update_dir = get_app_data_dir()
        self.update_checker = UpdateChecker(get_version(), UPDATE_CHECK_URL, update_dir)
        
        # Marketplace finder removed - using external sites ( edtools.cc) instead
        # No local database needed - simpler and more reliable
        
        # Initialize EDDN sender for sharing data back to community
        from eddn_sender import EDDNSender
        self.eddn_sender = EDDNSender(
            commander_name="EliteMining User",  # Will be updated from journal
            app_name="EliteMining",
            app_version=get_version()
        )
        self.eddn_sender.set_enabled(self.eddn_send_enabled.get() == 1)
        print(f"[OK] EDDN sender {'enabled' if self.eddn_send_enabled.get() == 1 else 'disabled'}")
        
        # Initialize EDDN listener for real-time market data
        from eddn_listener import EDDNListener
        eddn_cache_path = os.path.join(get_app_data_dir(), "data", "marketplace_cache.db")
        os.makedirs(os.path.dirname(eddn_cache_path), exist_ok=True)
        self.eddn_listener = EDDNListener(eddn_cache_path)
        self.cargo_monitor.start_carrier_names(eddn_cache_path)
        self.eddn_listener.start()
        print(f"[OK] EDDN listener started (real-time market data) -> {eddn_cache_path}")
        
        # Make the EDDN cache path available to MarketplaceAPI and SystemFinderAPI
        from marketplace_api import MarketplaceAPI
        MarketplaceAPI.EDDN_CACHE_PATH = eddn_cache_path
        from system_finder_api import SystemFinderAPI
        SystemFinderAPI.EDDN_CACHE_PATH = eddn_cache_path
        import service_status
        service_status.status_callback = self._queue_search_service_status

        # Wire the EDDN cache path into the live journal parser so every FSDJump the player
        # makes is also written directly to system_powerplay (no EDDN round-trip needed).
        # Then backfill from recent journal files so searches have PP data immediately.
        if hasattr(self, 'cargo_monitor') and self.cargo_monitor and \
                hasattr(self.cargo_monitor, 'journal_parser') and self.cargo_monitor.journal_parser:
            self.cargo_monitor.journal_parser.eddn_cache_path = eddn_cache_path

            def _backfill_pp():
                try:
                    jp = self.cargo_monitor.journal_parser
                    count = jp.scan_recent_journals_for_powerplay()
                    if count:
                        print(f"[OK] Journal PP backfill: {count} systems loaded from local journals")
                except Exception as e:
                    log.warning(f"[WARN] Journal PP backfill failed: {e}")

            threading.Thread(target=_backfill_pp, daemon=True).start()

            # The worker only stores its answer; _apply_startup_pledge picks it up. Any Tk
            # call from a worker fails until mainloop runs, and building the window takes longer.
            self._journal_pledge_result = []

            def _lookup_pledge():
                try:
                    pledge = self.cargo_monitor.journal_parser.latest_pledged_power()
                except Exception as e:
                    log.warning(f"[WARN] Journal pledge lookup failed: {e}")
                    pledge = None
                self._journal_pledge_result.append(pledge)

            threading.Thread(target=_lookup_pledge, daemon=True).start()

        # Initialize API uploader for session/hotspot sharing
        from api_uploader import APIUploader
        self.api_uploader = APIUploader()
        if self.api_uploader.enabled:
            print(f"[OK] API uploader enabled - endpoint: {self.api_uploader.api_url}")
            # Retry any queued uploads from previous sessions
            self.after(3000, lambda: self.api_uploader.retry_queued_uploads(background=True))
        else:
            print(f"API uploader disabled")
        
        # Initialize market handler for Market.json processing
        from market_handler import MarketHandler
        self.market_handler = MarketHandler(self.eddn_sender)
        
        # Initialize VoiceAttack variables manager
        from va_variables import VAVariablesManager
        self.va_variables = None  # Will be initialized after UI is built
        
        # Build UI - ProspectorPanel will scan latest journal and populate current_system
        self._set_splash_status("Building interface...")
        self._build_ui()
        self._ship_presets_ready = True
        self.after_idle(self._handle_ship_info_changed)

        # Watch for Market.json changes to send to EDDN
        # Must be AFTER _build_ui() so prospector_panel.journal_dir is available
        from file_watcher import get_file_watcher
        file_watcher = get_file_watcher()
        journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
        if journal_dir and os.path.exists(journal_dir):
            file_watcher.add_watch(journal_dir, self._on_journal_file_change)
            print(f"[OK] Watching journal directory for Market.json updates")
            # Prime EDDN sender with LoadGame from the latest journal — required so
            # gameversion/gamebuild are populated before the first Market.json event arrives.
            if self.eddn_sender.prime_from_journal(journal_dir):
                print(f"[OK] EDDN sender primed from journal (CMDR={self.eddn_sender.commander_name}, version={self.eddn_sender.game_version})")
            else:
                print(f"[WARN] EDDN sender could not find LoadGame in recent journals — commodity uploads will be deferred until next LoadGame")
            # Process existing Market.json on startup — covers the case where the player
            # was already docked at a market before EliteMining was launched.
            market_path = os.path.join(journal_dir, 'Market.json')
            if os.path.exists(market_path) and hasattr(self, 'market_handler'):
                threading.Thread(target=self.market_handler.process_market_file,
                                 args=(market_path,), daemon=True).start()
                print(f"[OK] Queued existing Market.json for startup processing")
        else:
            print(f"[WARN] Could not set up EDDN file watcher - journal_dir not available")
        
        # Clean up legacy files from older versions
        self._cleanup_legacy_files()
        
        # Set current system from ProspectorPanel's scan (already done during UI build)
        # ProspectorPanel._read_initial_location_from_journal() scans the latest file efficiently
        # Use that result instead of doing another expensive full-file scan
        # Note: prospector_panel.last_system may not be populated yet - check is done in _check_offline_arrival()
        if hasattr(self, 'prospector_panel') and self.prospector_panel and self.prospector_panel.last_system:
            self.current_system = self.prospector_panel.last_system
        
        # Initialize VoiceAttack variables after UI is built
        self.after(500, self._initialize_va_variables)
        
        # Check for updates after UI is ready (automatic check once per day)
        self.after(4000, self._check_for_updates_startup)  # Check after splash is dismissed (splash=2s)
        
        # Full journal scan runs first (only call once!)
        # Location refresh and distance calculation happens AFTER scan completes
        self.after(5000, self._background_journal_catchup)
        
        # Check for VA profile updates AFTER everything is loaded and settled
        # Use longer delay to ensure UI is fully responsive
        # Only run in installed (frozen) mode - skip during dev/VS Code runs
        if getattr(sys, 'frozen', False):
            self.after(12000, self._check_va_profile_update)
        
        # Set flag after window is fully displayed
        self._app_fully_loaded = False
        def mark_loaded():
            self._app_fully_loaded = True
        self.after(5000, mark_loaded)

        # Grace period: prevent game-focus check from hiding overlay during startup
        self._overlay_startup_grace = True
        def end_grace():
            self._overlay_startup_grace = False
        self.after(7000, end_grace)

        # Dismiss splash after a short delay once mainloop starts
        # (splash has been visible since the very start of __init__)
        self.after(2000, self._dismiss_splash)

        # Scheduled last, so it runs from mainloop with every tab already built
        self.after(0, self._apply_startup_pledge)

        # Safety: re-apply cargo overlay state after full init settles
        # Guards against any startup race where overlay ends up hidden despite being enabled
        self.after(3500, self._reapply_cargo_overlay_state)
        self.after(6000, self._reapply_cargo_overlay_state)  # Second pass after grace period ends

    def _set_splash_status(self, text: str) -> None:
        """Update the splash screen's status line, forcing an immediate repaint
        even though mainloop() hasn't started yet (update() pumps pending events)."""
        if self._splash and self._splash_status_var:
            try:
                self._splash_status_var.set(text)
                self._splash.update()
            except Exception:
                pass

    def _dismiss_splash(self):
        """Dismiss the startup splash screen and reveal the main window."""
        if self._splash:
            try:
                self._splash.destroy()
            except Exception:
                pass
            self._splash = None
            self._splash_photo = None
            self._splash_status_var = None
        # Restore geometry and reveal main window
        self._ui_scale_resize_ratio = 1.0
        self._restore_window_geometry()
        self.lift()
        # Now that the window has its real, restored position, it's safe to check
        # for pending database migrations and show any related notice dialogs
        # (centering on self would use stale/default geometry before this point)
        self.after(200, self._run_database_migrations)
        # Re-trigger sash initialization
        self._sash_initialized = False
        self._sidebar_sash_initialized = False
        self.after(300, self._reinitialize_sash_positions)
        # Apply stay-on-top AFTER splash is gone and window is fully visible
        self.after(500, self._apply_stay_on_top_after_init)

    def _cleanup_legacy_files(self):
        """Remove legacy files from older versions that are no longer used"""
        from path_utils import get_app_data_dir
        
        # Legacy files to clean up (removed in v4.6.7+)
        legacy_files = [
            # Old incremental journal scan state files (now using full scan)
            os.path.join(get_app_data_dir(), "last_app_close.json"),
            os.path.join(get_app_data_dir(), "last_journal_scan.json"),
            # Also check app directory for dev installs
            os.path.join(os.path.dirname(__file__), "last_app_close.json"),
            os.path.join(os.path.dirname(__file__), "last_journal_scan.json"),
            os.path.join(os.path.dirname(__file__), "journal_scan_state.py"),
            os.path.join(os.path.dirname(__file__), "incremental_journal_scanner.py"),
        ]
        
        for filepath in legacy_files:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"[CLEANUP] Removed legacy file: {os.path.basename(filepath)}")
            except Exception as e:
                # Silently ignore errors (file in use, permissions, etc.)
                pass

    def _trigger_ring_auto_search(self):
        """Trigger ring finder auto-search at startup if enabled"""
        if hasattr(self, 'ring_finder') and self.ring_finder:
            if hasattr(self.ring_finder, 'auto_search_var') and self.ring_finder.auto_search_var.get():
                print("[STARTUP] Triggering ring finder auto-search...")
                self.ring_finder._startup_auto_search(force=True)
        
        # Fetch reserve levels for current system (after ring finder search completes)
        if hasattr(self, 'cargo_monitor') and self.cargo_monitor and self.cargo_monitor.current_system:
            current_sys = self.cargo_monitor.current_system
            print(f"[STARTUP] Fetching reserve levels for current system: {current_sys}")
            
            # Update status bar
            if hasattr(self, 'ring_finder') and self.ring_finder:
                self.ring_finder.status_var.set(f"Fetching reserve levels for {current_sys}...")
            
            def completed(reserve_levels, error):
                if getattr(self, 'current_system', current_sys) != current_sys:
                    return
                if hasattr(self, 'ring_finder') and self.ring_finder:
                    if error:
                        self.ring_finder.status_var.set("Error fetching reserve levels")
                    elif reserve_levels:
                        self.ring_finder.status_var.set(f"Fetched {len(reserve_levels)} reserve levels for {current_sys}")
                    else:
                        self.ring_finder.status_var.set(f"No reserve levels found for {current_sys}")

            self._fetch_reserve_levels_for_system(current_sys, on_complete=completed)

    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for the application"""
        # Ctrl+T for toggling Stay on Top (same as PowerToys default)
        self.bind_all("<Control-t>", lambda e: self._toggle_stay_on_top_shortcut())
        # Alt+T as alternative
        self.bind_all("<Alt-t>", lambda e: self._toggle_stay_on_top_shortcut())
        
        # Initialize TTS announcer
        announcer.load_saved_settings()

    def _toggle_stay_on_top_shortcut(self):
        """Toggle stay on top via keyboard shortcut"""
        current = self.stay_on_top.get()
        self.stay_on_top.set(1 - current)  # Toggle between 0 and 1

    def _build_ui(self):
        """Build the main user interface"""
        # Create horizontal paned window for resizable sidebar
        self.main_paned = ttk.PanedWindow(self, orient="horizontal")
        self.main_paned.grid(row=0, column=0, columnspan=2, sticky="nsew")
        
        # Left pane: tabs container
        # Bottom padding reduced to 0 to align with sidebar/status bar
        # Modern: matching bottom gap on both columns so they end level, clear of the footer
        content_frame = ttk.Frame(self.main_paned, padding=(10, 6, 6, 8 if self.current_theme in ("modern", "modern_slate", "modern_orange") else 0))
        self.main_paned.add(content_frame, weight=3)  # Add to paned window with higher weight
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=0)

        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        
        # Theme toggle button - will be placed in actions row below
        from config import load_theme
        _current_theme = load_theme()
        _theme_btn_text = t('sidebar.' + self._THEME_STR_KEYS.get(_current_theme, "dark_theme")) + " ▾"
        # Style button to match current theme
        if _current_theme == "elite_orange":
            _btn_bg, _btn_fg = "#1a1a1a", "#ff8c00"
            _btn_active_bg, _btn_active_fg = "#ff8c00", "#000000"
        elif _current_theme in ("modern", "modern_slate", "modern_orange"):
            _btn_bg, _btn_fg = modern_color("#262C34"), modern_color("#E6EAF0")
            _btn_active_bg, _btn_active_fg = modern_color("#FF9A32"), modern_color("#14171B")
        else:
            _btn_bg, _btn_fg = "#2d2d2d", "#ffffff"
            _btn_active_bg, _btn_active_fg = "#3d3d3d", "#ffffff"
        
        # Store theme button config for later placement in actions row
        self._theme_btn_config = {
            "text": _theme_btn_text,
            "bg": _btn_bg,
            "fg": _btn_fg,
            "activebackground": _btn_active_bg,
            "activeforeground": _btn_active_fg
        }
        
        # Clear focus when switching tabs to prevent entries from being auto-selected
        def _clear_entry_focus(event=None):
            try:
                # Focus the notebook itself to remove selection from entry widgets
                self.notebook.focus_set()
                # Clear selection from System Finder entry if it exists
                if hasattr(self, 'sysfinder_ref_entry'):
                    self.sysfinder_ref_entry.selection_clear()
                
                if self.notebook.select() == str(getattr(self, '_bookmarks_tab', '')):
                    self.prospector_panel._sync_bookmark_last_mined()
                    self.prospector_panel._refresh_bookmarks()

                # Sync Settings tab with ring_finder state when Settings tab is selected
                if self.notebook.select() == str(getattr(self, '_settings_tab', '')):
                    # Sync auto-search checkbox with ring_finder
                    if hasattr(self, 'ring_finder') and self.ring_finder and hasattr(self.ring_finder, 'auto_search_var'):
                        ring_finder_state = self.ring_finder.auto_search_var.get()
                        if self.auto_search_enabled.get() != ring_finder_state:
                            self.auto_search_enabled.set(ring_finder_state)
            except Exception:
                pass
        self.notebook.bind('<<NotebookTabChanged>>', _clear_entry_focus)

        # Mining Session tab (moved from Dashboard, with all its sub-tabs)
        mining_session_tab = ttk.Frame(self.notebook, padding=8)
        self._build_mining_session_tab(mining_session_tab)
        self.notebook.add(mining_session_tab, text=t('tabs.mining'))

        # Distance Calculator tab (build FIRST so distance_calculator exists for other tabs)
        distance_tab = ttk.Frame(self.notebook, padding=8)
        self._build_distance_calculator_tab(distance_tab)
        
        # Hotspots Finder tab (depends on distance_calculator)
        ring_finder_tab = ttk.Frame(self.notebook, padding=8)
        self._setup_ring_finder(ring_finder_tab)
        self.notebook.add(ring_finder_tab, text=t('tabs.hotspots_finder'))

        # Commodity Market tab
        marketplace_tab = ttk.Frame(self.notebook, padding=8)
        self._build_marketplace_tab(marketplace_tab)
        self.notebook.add(marketplace_tab, text=t('tabs.commodity_market'))
        self.route_tab = RouteTab(self)
        self.notebook.add(self.route_tab, text=t('tabs.route'))
        
        # System Finder tab
        self.system_finder_tab = system_finder_tab = ttk.Frame(self.notebook, padding=8)
        self._build_system_finder_tab(system_finder_tab)
        self.notebook.add(system_finder_tab, text=t('tabs.system_finder'))

        # Fleet Carrier tab - live FC status from journal events
        fleet_carrier_tab = None
        try:
            fc_frame = ttk.Frame(self.notebook, padding=0)
            self._build_fleet_carrier_tab(fc_frame)
            self.notebook.add(fc_frame, text=t('fleet_carrier.tab_title'))
            fleet_carrier_tab = fc_frame
        except Exception as _fce:
            print(f"[DEBUG] Could not create Fleet Carrier tab: {_fce}")

        # Add Distance Calculator tab now (built earlier but added here for correct order)
        self.notebook.add(distance_tab, text=t('tabs.distance_calculator'))

        # VoiceAttack Controls tab (combined Firegroups + Mining Controls)
        voiceattack_tab = ttk.Frame(self.notebook, padding=8)
        self._build_voiceattack_controls_tab(voiceattack_tab)
        self.notebook.add(voiceattack_tab, text=t('tabs.voiceattack_controls'))
        
        # Bookmarks tab - Mining location bookmarks
        bookmarks_tab = ttk.Frame(self.notebook, padding=8)
        self._bookmarks_tab = bookmarks_tab
        self._build_bookmarks_tab(bookmarks_tab)
        self.notebook.add(bookmarks_tab, text=t('tabs.bookmarks'))
        
        # Auto-populate marketplace system after UI is built
        self.after(3000, self._populate_marketplace_system)

        # Settings tab (simplified with remaining sub-tabs)
        settings_tab = ttk.Frame(self.notebook, padding=8)
        self._settings_tab = settings_tab
        self._build_settings_notebook(settings_tab)
        self.notebook.add(settings_tab, text=t('tabs.settings'))

        self._main_tabs = {
            'mining_session': mining_session_tab,
            'hotspots_finder': ring_finder_tab,
            'commodity_market': marketplace_tab,
            'route': self.route_tab,
            'system_finder': system_finder_tab,
            'fleet_carrier': fleet_carrier_tab,
            'distance_calculator': distance_tab,
            'voiceattack': voiceattack_tab,
            'bookmarks': bookmarks_tab,
            'settings': settings_tab,
        }

        # About tab removed - now accessible via version button in sidebar

        # Actions row (global)
        actions = ttk.Frame(self)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(10, 10), pady=(4, 6))
        self._actions_frame = actions

        # Create the sidebar (Ship Presets + Cargo Monitor)
        self._create_main_sidebar()

        # Configure column weights for proper spacing
        actions.grid_columnconfigure(0, weight=0)  # Info frame fixed (left)
        actions.grid_columnconfigure(1, weight=1)  # Expandable space in middle
        actions.grid_columnconfigure(2, weight=0)  # Buttons fixed (right)

        # CMDR/System info container (right side) - uses frame for mixed colors
        # Use black background for orange theme
        from config import load_theme
        _info_theme = load_theme()
        _info_bg = "#000000" if _info_theme == "elite_orange" else (modern_color("#14171B") if _info_theme in ("modern", "modern_slate", "modern_orange") else "#1e1e1e")
        _info_val = modern_color("#FF9A32") if _info_theme in ("modern", "modern_slate", "modern_orange") else "#ffcc00"
        # Modern: labels regular weight, only the values bold
        _info_lbl_font = self._scaled_font(9) if _info_theme in ("modern", "modern_slate", "modern_orange") else self._scaled_font(9, "bold")

        info_frame = tk.Frame(actions, bg=_info_bg)
        info_frame.grid(row=0, column=0, sticky="w")

        # EliteMining logo (resized to fit status bar)
        try:
            from PIL import Image, ImageTk
            from path_utils import get_images_dir
            logo_path = os.path.join(get_images_dir(), "EliteMining_txt_logo_transp_resize.png")
            if os.path.exists(logo_path) and _info_theme not in ("modern", "modern_slate", "modern_orange"):  # Modern footer starts at the CMDR text
                logo_img = Image.open(logo_path)
                # Resize to fit status bar height (smaller to avoid stretched look)
                target_height = 16
                aspect_ratio = logo_img.width / logo_img.height
                target_width = int(target_height * aspect_ratio)
                logo_img = logo_img.resize((target_width, target_height), Image.LANCZOS)
                self._status_logo = ImageTk.PhotoImage(logo_img)
                logo_label = tk.Label(info_frame, image=self._status_logo, bg=_info_bg)
                logo_label.grid(row=0, column=0, sticky="e", padx=(0, 6))
        except Exception as e:
            print(f"Could not load status bar logo: {e}")

        # Labels for mixed colors (white labels, yellow values)
        self.cmdr_label_prefix = tk.Label(info_frame, text=t('status_bar.cmdr'), fg="white", bg=_info_bg, font=_info_lbl_font)
        self.cmdr_label_value = tk.Label(info_frame, text="", fg=_info_val, bg=_info_bg, font=self._scaled_font(9, "bold"))
        self.system_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=_info_lbl_font)
        self.system_label_value = tk.Label(info_frame, text="", fg=_info_val, bg=_info_bg, font=self._scaled_font(9, "bold"))
        self.visits_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=_info_lbl_font)
        self.visits_label_value = tk.Label(info_frame, text="", fg=_info_val, bg=_info_bg, font=self._scaled_font(9, "bold"), cursor="hand2")
        self.route_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=_info_lbl_font)
        self.route_label_value = tk.Label(info_frame, text="", fg=_info_val, bg=_info_bg, font=self._scaled_font(9, "bold"))
        # Make visits clickable to edit
        self.visits_label_value.bind("<Button-1>", lambda e: self._show_edit_visits_dialog_for_current_system())
        self.visits_label_prefix.bind("<Button-1>", lambda e: self._show_edit_visits_dialog_for_current_system())
        self.visits_label_prefix.config(cursor="hand2")
        ToolTip(self.visits_label_value, t('status_bar.click_to_edit_visits'))
        ToolTip(self.visits_label_prefix, t('status_bar.click_to_edit_visits'))
        
        # Grid them horizontally (tighter spacing) - shift columns to make room for logo
        self.cmdr_label_prefix.grid(row=0, column=1, sticky="e")
        self.cmdr_label_value.grid(row=0, column=2, sticky="w")
        self.system_label_prefix.grid(row=0, column=3, sticky="e")
        self.system_label_value.grid(row=0, column=4, sticky="w")
        self.visits_label_prefix.grid(row=0, column=5, sticky="e")
        self.visits_label_value.grid(row=0, column=6, sticky="w")
        self.route_label_prefix.grid(row=0, column=7, sticky="e")
        self.route_label_value.grid(row=0, column=8, sticky="w")
        _ind_frame = tk.Frame(actions, bg=_info_bg)
        _ind_frame.grid(row=0, column=1, sticky="e", padx=(0, 12))
        self._footer_service_statuses = dict.fromkeys(('eddn', 'spansh', 'market'), 'checking')
        self._journal_scan_label = tk.Label(_ind_frame, text='', fg="#888888", bg=_info_bg, font=self._scaled_font(8))
        self._journal_scan_label.pack(side="left", padx=(0, 10))
        self._footer_services_label = tk.Label(
            _ind_frame, text='', fg="#888888", bg=_info_bg,
            font=self._scaled_font(8), cursor="hand2")
        self._footer_services_label.pack(side="left")
        _tip_colors = None
        if self.current_theme in ("modern", "modern_slate", "modern_orange"):
            _tip_theme = get_theme_colors(self.current_theme)
            _tip_colors = (_tip_theme["panel"], _tip_theme["fg"], _tip_theme["border"])
        self._footer_services_tip = ToolTip(self._footer_services_label, '', anchor_above=True, colors=_tip_colors)
        self._footer_services_label.bind('<Button-1>', self._show_service_status)
        self._update_footer_indicator('market', 'checking')
        
        # Load CMDR name in background
        self.after(500, self._update_cmdr_system_display)

        self._sidebar_visible = True

        if self.current_theme in ("modern", "modern_slate", "modern_orange"):
            self.after(600, self._modern_recolor_all)
            _recolor_pending = []
            _recolored_tabs = set()

            def _recolor_tab(e):
                # Only recolor the newly selected tab (full-app walk on every switch was laggy), debounced
                if _recolor_pending:
                    return
                try:
                    tab = e.widget.nametowidget(e.widget.select())
                except Exception:
                    tab = None
                if tab is not None:
                    if str(tab) in _recolored_tabs:
                        return
                    _recolored_tabs.add(str(tab))

                def _run():
                    _recolor_pending.clear()
                    self._modern_recolor_all(tab)
                _recolor_pending.append(self.after(50, _run))
            self.bind_all("<<NotebookTabChanged>>", _recolor_tab, add="+")

            def _recolor_new_popup(e):
                # Popups are built after the startup pass; recolor each one as it first appears
                w = e.widget
                if w.winfo_class() == "Toplevel" and w is not self and not getattr(w, "_modern_recolored", False):
                    w._modern_recolored = True
                    try:
                        for opt in ("bg",):
                            if str(w.cget(opt)).lower() in self._MODERN_REMAP:
                                w.configure(bg=self._MODERN_REMAP[str(w.cget(opt)).lower()])
                    except tk.TclError:
                        pass
                    w.after_idle(lambda: self._modern_recolor_all(w))
            # Class binding: fires only for Toplevels, not for every widget mapped on a tab switch
            self.bind_class("Toplevel", "<Map>", _recolor_new_popup, add="+")

            if self.current_theme == "modern_orange":
                def _orange_check_text(e):
                    # Checkbutton/Radiobutton text set to white at build time (any tab, built at any time)
                    w = e.widget
                    try:
                        if str(w.cget("fg")).lower() in ("white", "#ffffff", "#e0e0e0", "#e6e6e6", "#e6eaf0"):
                            w.configure(fg=modern_color("#FF9A32"))
                    except tk.TclError:
                        pass
                self.bind_class("Checkbutton", "<Map>", _orange_check_text, add="+")
                self.bind_class("Radiobutton", "<Map>", _orange_check_text, add="+")

        # Import existing values from VoiceAttack profile
        self.after(100, self._import_all_from_txt)
        # Set up tracing AFTER loading from .txt files
        self.after(200, self._setup_announcement_tracing)

        # Clear selection on ring finder and distance calculator entries after UI stabilized
        try:
            if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_entry'):
                self.after(300, lambda: self.ring_finder.system_entry.selection_clear())
        except Exception:
            pass
        
        # Clear selection on system finder entry after UI stabilized
        try:
            if hasattr(self, 'sysfinder_ref_entry'):
                self.after(300, lambda: self.sysfinder_ref_entry.selection_clear())
        except Exception:
            pass
        
        # Initialize color menu display after UI is built
        self.after(200, self._update_color_menu_display)
        
        # Update journal label after everything is initialized
        self.after(150, self._update_journal_label)
        
        # Note: Window geometry is handled by _restore_window_geometry() called later
        # Don't override here as it breaks saved geometry on restart
        
        # Start on Hotspots Finder tab by default
        self.after(100, lambda: self.switch_to_tab('hotspots_finder'))
        
        # Start VoiceAttack command watcher (delay to ensure all components are ready)
        self.after(2000, self._start_va_command_watcher)
        
        # Start Variables folder watcher for live VA sync (after import completes)
        self.after(3000, self._start_variables_watcher)

    def _create_integrated_cargo_monitor(self, parent_frame):
        """
        Create integrated cargo monitor in the bottom pane.
        
        ✅ THIS IS THE PRIMARY CARGO DISPLAY - Default view in main app window!
        
        Display method: _update_integrated_cargo_display()
        Data source: self.cargo_monitor (CargoMonitor instance)
        Location: Bottom pane of main EliteMining window
        """
        parent_frame.columnconfigure(0, weight=1)
        parent_frame.rowconfigure(0, weight=1)
        
        # Configure LabelFrame font to match Ship Presets title
        style = ttk.Style()
        style.configure("Cargo.TLabelframe.Label", font=self._scaled_font(9, "bold"))

        # Create a LabelFrame to provide visual border around cargo monitor
        cargo_frame = ttk.LabelFrame(parent_frame, text=t('sidebar.cargo_monitor'), padding=6, style="Cargo.TLabelframe")
        cargo_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=(2, round(6 * self.ui_scale)))  # sticky="nsew" - expand in all directions
        self._cargo_frame = cargo_frame
        cargo_frame.columnconfigure(0, weight=1)
        cargo_frame.rowconfigure(1, weight=1)  # Content row expands
        
        # Simple header without buttons
        header_frame = ttk.Frame(cargo_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header_frame.columnconfigure(2, weight=1)
        
        # Title and summary in one line
        title_label = ttk.Label(header_frame, text=t('sidebar.cargo_status'), font=self._scaled_font(9, "bold"))
        title_label.grid(row=0, column=0, sticky="w")

        self.integrated_cargo_summary = ttk.Label(header_frame, text="0/200t (0%) - Empty",
                                                 font=self._scaled_font(9))
        self.integrated_cargo_summary.grid(row=0, column=1, sticky="w", padx=(6, 0))

        _info_icon = ttk.Label(header_frame, text="\u24d8", foreground=self.theme_colors['fg_muted'], cursor="hand2",
                               font=self._scaled_font(10))
        _info_icon.grid(row=0, column=2, sticky="w", padx=(6, 2))
        self._cargo_info_tip = ToolTip(_info_icon, "")
        if self.current_theme in ("modern", "modern_slate", "modern_orange"):
            from ui.modern_widgets import RoundedProgressBar
            self._cargo_bar = RoundedProgressBar(header_frame, height=self._scaled_px(10))
            self._cargo_bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        
        # Content area - expandable
        content_frame = ttk.Frame(cargo_frame)
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)  # Text widget row expands
        
        # Cargo text widget (theme-aware)
        _cargo_bg = self.theme_colors["bg"]
        _cargo_fg = self.theme_colors["fg"]
        self.integrated_cargo_text = tk.Text(
            content_frame,
            bg=_cargo_bg,
            fg=_cargo_fg,
            font=("Consolas", round(9 * self.ui_scale), "normal"),  # Monospace font for proper alignment
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="none",  # No wrap - fixed-width columnar lines must not break
            height=6,  # Minimum height - will expand with pane
            width=45   # Width for complete cargo info
        )
        self.integrated_cargo_text.grid(row=0, column=0, sticky="nsew")
        
        self.integrated_cargo_text.tag_configure("limpet_clickable",
                                                 foreground=self.theme_colors.get("fg", "#e0e0e0"))
        self.integrated_cargo_text.tag_bind("limpet_clickable", "<Button-1>",
                                            lambda e: self.cargo_monitor.adjust_limpet_count())
        self.integrated_cargo_text.tag_bind("limpet_clickable", "<Enter>",
                                            lambda e: self.integrated_cargo_text.configure(cursor="hand2"))
        self.integrated_cargo_text.tag_bind("limpet_clickable", "<Leave>",
                                            lambda e: self.integrated_cargo_text.configure(cursor=""))
        self.integrated_cargo_text.tag_configure("cargo_item", font=("Consolas", round(10 * self.ui_scale), "normal"))
        self.integrated_cargo_text.tag_configure("section_header", font=("Consolas", round(10 * self.ui_scale), "bold"))
        self.integrated_cargo_text.tag_configure("material_item", font=("Consolas", round(10 * self.ui_scale), "normal"))
        self.integrated_cargo_text.tag_configure("small_italic", font=self._scaled_font(8, "italic"), foreground="#888888", justify="left")

        # Thin scrollbar
        integrated_scrollbar = ttk.Scrollbar(content_frame, orient="vertical", 
                                           command=self.integrated_cargo_text.yview)
        integrated_scrollbar.grid(row=0, column=1, sticky="ns")
        self.integrated_cargo_text.configure(yscrollcommand=integrated_scrollbar.set)
        content_frame.columnconfigure(1, weight=0)
        
        # Set up periodic update for integrated display
        self._update_integrated_cargo_display()
        self.after(1000, self._periodic_integrated_cargo_update)
        
    def _update_integrated_cargo_display(self):
        """
        Update the INTEGRATED cargo display with data from cargo monitor.
        
        ✅ PRIMARY DISPLAY METHOD - This is what users see in the main app window!
        
        Location: Bottom pane of main EliteMining window
        Widgets: self.integrated_cargo_text, self.integrated_cargo_summary
        """
        if not hasattr(self, 'integrated_cargo_summary'):
            return
            
        # Update summary
        cargo = self.cargo_monitor
        percentage = (cargo.current_cargo / cargo.max_cargo * 100) if cargo.max_cargo > 0 else 0
        
        summary_text = f"{cargo.current_cargo}/{cargo.max_cargo}t ({percentage:.0f}%)"
        self.integrated_cargo_summary.configure(text=summary_text)
        if hasattr(self, '_cargo_bar'):
            self._cargo_bar['value'] = min(percentage, 100)
        
        # Build the new content first, then skip the update if nothing changed
        # This prevents scrollbar jitter from delete+reinsert on every tick
        content_chunks = []

        def append_content(text, tags=()):
            content_chunks.append((text, tags))
        
        if not cargo.cargo_items:
            if cargo.current_cargo > 0:
                append_content(f"📊 {cargo.current_cargo}t {t('sidebar.total')}\n💡 {t('sidebar.no_item_details')}")
            else:
                append_content(f"📦 {t('sidebar.empty_cargo')}\n⛏️ {t('sidebar.start_mining')}")
        else:
            sorted_items = sorted(cargo.cargo_items.items(), key=lambda x: (x[0].lower() != 'limpet', -x[1]))
            for i, (item_name, quantity) in enumerate(sorted_items):
                display_name = item_name.replace('_', ' ').replace('$', '').title()
                if display_name in ['Low Temp. Diamonds', 'Low Temperature Diamonds']:
                    display_name = 'LTD'
                is_limpet = "limpet" in item_name.lower()
                if is_limpet:
                    display_name = t('sidebar.limpet')
                icon = "●"
                name_field = f"{display_name:<12}"[:12]
                quantity_text = f"{quantity:>4}t"
                line = f"{icon} {name_field} {quantity_text}"
                append_content(line, ("limpet_clickable", "cargo_item") if is_limpet else ("cargo_item",))
                if i < len(sorted_items) - 1:
                    append_content("\n")
        
        if cargo.materials_collected:
            sep_chars = 28
            append_content("\n" + "─" * sep_chars)
            append_content("\n")
            append_content(t('mining_session.engineering_materials'), ("section_header",))
            append_content("\n")
            sorted_materials = sorted(cargo.materials_collected.items(), key=lambda x: x[0])
            for i, (material_name, quantity) in enumerate(sorted_materials):
                grade = cargo.MATERIAL_GRADES.get(material_name, 0)
                display_name = cargo.materials_localized_names.get(material_name, material_name)[:12]
                grade_text = f"(G{grade})"
                line = f"{display_name} {grade_text} {quantity:>3}"
                append_content(line, ("material_item",))
                if i < len(sorted_materials) - 1:
                    append_content("\n")
        
        has_limpets = any("limpet" in name.lower() for name in cargo.cargo_items.keys())
        if hasattr(self, '_cargo_info_tip'):
            self._cargo_info_tip.text = t('sidebar.refinery_note').strip() + (
                "\n" + t('sidebar.limpet_click_help').strip() if has_limpets else "")
        else:
            sep_chars = 28
            append_content("\n" + "─" * sep_chars)
            append_content("\n" + t('sidebar.refinery_note'), ("small_italic",))
            if has_limpets:
                append_content("\n" + t('sidebar.limpet_click_help'), ("small_italic",))
        
        new_content_str = "".join(text for text, tags in content_chunks)
        
        # Compare with current content — skip full rewrite if unchanged
        try:
            self.integrated_cargo_text.configure(state="normal")
            current_content = self.integrated_cargo_text.get(1.0, "end-1c")
            if current_content == new_content_str:
                self.integrated_cargo_text.configure(state="disabled")
                return
        except Exception:
            pass
        
        # Content changed — do full rewrite
        # Save current scroll position before updating
        try:
            scroll_position = self.integrated_cargo_text.yview()
        except:
            scroll_position = None
        
        self.integrated_cargo_text.delete(1.0, tk.END)

        for text, tags in content_chunks:
            self.integrated_cargo_text.insert(tk.END, text, tags)

        self.integrated_cargo_text.configure(state="disabled")
        
        # Restore scroll position to prevent jumping
        if scroll_position:
            try:
                self.integrated_cargo_text.yview_moveto(scroll_position[0])
            except:
                pass
        
    def refresh_overlays(self):
        """Rebuild the cargo overlay and re-assert topmost on both overlays (recovers one the game window buried)."""
        log.info("[OVERLAY] refresh_overlays")
        try:
            if hasattr(self, 'cargo_text_overlay') and self.cargo_text_overlay.overlay_enabled and self.text_overlay_enabled.get():
                cov = self.cargo_text_overlay
                sc_hidden, session_hidden = getattr(cov, '_sc_hidden', False), getattr(cov, '_session_hidden', False)
                cov.reinstate()
                cov._sc_hidden, cov._session_hidden = sc_hidden, session_hidden
                cov.update_cargo(self.cargo_monitor)
            if hasattr(self, 'text_overlay') and self.text_overlay.overlay_enabled and not self.text_overlay._is_showing:
                self.text_overlay.reinstate()
            for ov in (getattr(self, 'cargo_text_overlay', None), getattr(self, 'text_overlay', None)):
                if ov and ov.overlay_window:
                    ov.overlay_window.wm_attributes("-topmost", False)
                    ov.overlay_window.wm_attributes("-topmost", True)
                    ov.overlay_window.lift()
        except Exception as e:
            log.debug(f"refresh_overlays: {e}")

    def _log_overlay_error_once(self, where):
        """Log a failure in the 2 s overlay loop with its traceback, once per distinct error (the loop would otherwise flood the log)."""
        exc = sys.exc_info()[1]
        key = (where, type(exc).__name__, str(exc))
        seen = self.__dict__.setdefault('_overlay_errors_seen', set())
        if key in seen or len(seen) >= 50:
            return
        seen.add(key)
        log.exception(f"[OVERLAY] periodic update failed ({where}); further identical errors are not logged")

    def _periodic_integrated_cargo_update(self):
        """Periodically update the integrated cargo display"""
        try:
            self._update_integrated_cargo_display()
        except Exception:
            self._log_overlay_error_once("cargo display update")
        
        # Journal replay misses supercruise if no entry event is in the current session, so seed it once from Status.json
        if not getattr(self, '_sc_seeded', False):
            self._sc_seeded = True
            try:
                with open(self.cargo_monitor.status_json_path, 'r', encoding='utf-8') as f:
                    self._in_supercruise = bool(json.load(f).get("Flags", 0) & 16)
                log.info(f"[OVERLAY] supercruise seeded from Status.json: {self._in_supercruise}")
            except Exception as e:
                log.info(f"[OVERLAY] supercruise seed failed: {e}")

        # Check game focus FIRST — set _game_hidden flags before any overlay updates
        try:
            if self.overlay_only_game_focused.get():
                game_active = is_game_focused()
                if game_active != getattr(self, '_prev_game_active', True):
                    log.info(f"[OVERLAY] game focus {'regained' if game_active else 'lost'}"
                             + ("" if game_active else f" (foreground: '{_foreground_window_title()}')"))
                if game_active and getattr(self, '_prev_game_active', True) is False:
                    self.after(0, self.refresh_overlays)
                self._prev_game_active = game_active
                # Cargo overlay
                if hasattr(self, 'cargo_text_overlay') and self.cargo_text_overlay.overlay_enabled and self.text_overlay_enabled.get():
                    if game_active:
                        if self.cargo_text_overlay._game_hidden:
                            self.cargo_text_overlay._game_hidden = False
                        # Always ensure alpha is restored when game is active
                        if self.cargo_text_overlay.overlay_window and not getattr(self.cargo_text_overlay, '_session_hidden', False) and not getattr(self.cargo_text_overlay, '_sc_hidden', False):
                            self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 1)
                    else:
                        if not self.cargo_text_overlay._game_hidden and (not getattr(self, '_overlay_startup_grace', False) or _find_game_window_rect() is None):
                            self.cargo_text_overlay._game_hidden = True
                            if self.cargo_text_overlay.overlay_window:
                                self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 0)
                # Text overlay — always track game focus, only manage window if showing
                if hasattr(self, 'text_overlay') and self.text_overlay.overlay_enabled:
                    if game_active:
                        self.text_overlay._game_hidden = False
                    else:
                        # Drop the message: re-showing a withdrawn window renders it oversized/offscreen, and
                        # leaving _is_showing set made the next message reuse that broken window
                        if not self.text_overlay._game_hidden and self.text_overlay._is_showing and self.text_overlay.overlay_window:
                            self.text_overlay._hide_window()
                            self.text_overlay._is_showing = False
                        self.text_overlay._game_hidden = True
            else:
                # Setting disabled — still require the game to be running
                game_running = _find_game_window_rect() is not None
                if hasattr(self, 'cargo_text_overlay'):
                    if game_running:
                        self.cargo_text_overlay._game_hidden = False
                    elif not self.cargo_text_overlay._game_hidden:
                        self.cargo_text_overlay._game_hidden = True
                        if self.cargo_text_overlay.overlay_window:
                            self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 0)
                if hasattr(self, 'text_overlay'):
                    if game_running:
                        self.text_overlay._game_hidden = False
                    elif not self.text_overlay._game_hidden:
                        self.text_overlay._game_hidden = True
                        if self.text_overlay._is_showing and self.text_overlay.overlay_window:
                            self.text_overlay._hide_window()
                            self.text_overlay._is_showing = False
        except Exception:
            self._log_overlay_error_once("game focus check")

        # Hide overlays in supercruise if setting is enabled
        try:
            if self.hide_overlays_in_supercruise.get() and self._in_supercruise:
                if hasattr(self, 'cargo_text_overlay') and self.cargo_text_overlay.overlay_window:
                    if not getattr(self.cargo_text_overlay, '_sc_hidden', False):
                        self.cargo_text_overlay._sc_hidden = True
                        log.info("[OVERLAY] cargo hidden for supercruise")
                        self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 0)
                if hasattr(self, 'text_overlay') and self.text_overlay._is_showing and self.text_overlay.overlay_window \
                        and not getattr(self.text_overlay, '_sc_exempt', False):
                    if not getattr(self.text_overlay, '_sc_hidden', False):
                        self.text_overlay._sc_hidden = True
                        self.text_overlay._hide_window()
            else:
                # Restore overlays when leaving supercruise
                if hasattr(self, 'cargo_text_overlay') and getattr(self.cargo_text_overlay, '_sc_hidden', False):
                    self.cargo_text_overlay._sc_hidden = False
                    if self.cargo_text_overlay.overlay_enabled and not self.cargo_text_overlay._game_hidden:
                        self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 1)
                if hasattr(self, 'text_overlay') and getattr(self.text_overlay, '_sc_hidden', False):
                    self.text_overlay._sc_hidden = False
                    if self.text_overlay._is_showing and not self.text_overlay._game_hidden:
                        self.text_overlay._show_on_top()
        except Exception:
            self._log_overlay_error_once("supercruise hide/restore")

        # Hide overlays when no mining session is active (if setting enabled)
        try:
            _session_active = hasattr(self, 'prospector_panel') and self.prospector_panel and getattr(self.prospector_panel, 'session_active', False)
            if self.overlay_only_mining_session.get() and not _session_active:
                # Always set the flag regardless of whether the window exists yet
                if hasattr(self, 'cargo_text_overlay'):
                    self.cargo_text_overlay._session_hidden = True
                    if self.cargo_text_overlay.overlay_window:
                        self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 0)
                if hasattr(self, 'text_overlay'):
                    self.text_overlay._session_hidden = True
                    if self.text_overlay._is_showing and self.text_overlay.overlay_window \
                            and not getattr(self.text_overlay, '_sc_exempt', False):
                        self.text_overlay._hide_window()
            else:
                # Session is active (or setting disabled) — restore and keep overlays visible each cycle
                if hasattr(self, 'cargo_text_overlay'):
                    self.cargo_text_overlay._session_hidden = False
                    if self.cargo_text_overlay.overlay_enabled and not self.cargo_text_overlay._game_hidden and not getattr(self.cargo_text_overlay, '_sc_hidden', False) \
                            and not self.cargo_text_overlay.focus_blocked():
                        if self.cargo_text_overlay.overlay_window:
                            self.cargo_text_overlay.overlay_window.wm_attributes("-alpha", 1)
                if hasattr(self, 'text_overlay') and getattr(self.text_overlay, '_session_hidden', False):
                    self.text_overlay._session_hidden = False
                    if self.text_overlay._is_showing and not self.text_overlay._game_hidden and not getattr(self.text_overlay, '_sc_hidden', False):
                        if self.text_overlay.overlay_window:
                            self.text_overlay._show_on_top()
        except Exception:
            self._log_overlay_error_once("session hide/restore")

        # Update cargo text overlay data (respects _game_hidden — won't deiconify if hidden)
        try:
            if hasattr(self, 'cargo_text_overlay') and self.cargo_text_overlay.overlay_enabled and self.text_overlay_enabled.get():
                tph = None
                if self.prospector_panel and self.prospector_panel.session_active:
                    tph = getattr(self.prospector_panel, 'live_tph', 0.0)
                self.cargo_text_overlay.update_cargo(self.cargo_monitor, tph)
        except Exception:
            self._log_overlay_error_once("cargo overlay update")

        # Schedule next update
        self.after(2000, self._periodic_integrated_cargo_update)  # Every 2 seconds
    
    # =========================================================================
    # VoiceAttack Variables Folder Watcher
    # =========================================================================
    def _start_variables_watcher(self):
        """Start watching the Variables folder for changes made by VoiceAttack"""
        self._vars_watcher_running = True
        self._vars_last_check = {}
        
        # Build list of files to watch from TIMERS, TOGGLES, etc.
        self._watched_files = set()
        for name, (fname, _, _, _) in TIMERS.items():
            self._watched_files.add(fname.lower())
        for name, (fname, _) in TOGGLES.items():
            self._watched_files.add(fname.lower())
        for tool, cfg in VA_VARS.items():
            if cfg["fg"]:
                self._watched_files.add(cfg["fg"].lower() + ".txt")
            if cfg["btn"]:
                self._watched_files.add(cfg["btn"].lower() + ".txt")
        # Add extra files
        self._watched_files.add("laserminingextra_count.txt")
        self._watched_files.add("delayprospector.txt")
        self._watched_files.add("thrustscoopopen.txt")
        self._watched_files.add("thrustscoopclosed.txt")
        self._watched_files.add("thrustupduration.txt")
        
        self._write_sound_levels()
        self._write_var_text("soundPlaying", "0")

        # Get initial file timestamps
        self._update_vars_timestamps()
        
        # Start periodic check
        self._check_variables_changes()
        print(f"[VARS WATCHER] Watching {len(self._watched_files)} files in: {self.vars_dir}")
    
    def _update_vars_timestamps(self):
        """Update cached timestamps for watched files"""
        try:
            for fname in os.listdir(self.vars_dir):
                if fname.lower() in self._watched_files:
                    fpath = os.path.join(self.vars_dir, fname)
                    try:
                        self._vars_last_check[fname.lower()] = os.path.getmtime(fpath)
                    except:
                        pass
        except Exception as e:
            pass
    
    def _check_variables_changes(self):
        """Check for file changes in Variables folder"""
        if not getattr(self, '_vars_watcher_running', False):
            return
        
        try:
            changes_detected = False
            for fname in os.listdir(self.vars_dir):
                if fname.lower() in self._watched_files:
                    fpath = os.path.join(self.vars_dir, fname)
                    try:
                        mtime = os.path.getmtime(fpath)
                        last_mtime = self._vars_last_check.get(fname.lower(), 0)
                        if mtime > last_mtime:
                            changes_detected = True
                            self._vars_last_check[fname.lower()] = mtime
                    except:
                        pass
            
            if changes_detected:
                # Debounce - wait 200ms before importing
                if hasattr(self, '_vars_import_scheduled'):
                    self.after_cancel(self._vars_import_scheduled)
                self._vars_import_scheduled = self.after(200, self._on_variables_changed)
        except Exception as e:
            pass
        
        # Schedule next check (every 500ms)
        self.after(500, self._check_variables_changes)
    
    def _on_variables_changed(self):
        """Handle changes detected in Variables folder"""
        print("[VARS WATCHER] Changes detected - refreshing values from VoiceAttack")
        self._import_all_from_txt()
        self._ship_check_modified()

    # =========================================================================
    # VoiceAttack Command Watcher
    # =========================================================================
    def _start_va_command_watcher(self):
        """Start watching for VoiceAttack commands via text file"""
        self._va_command_file = os.path.join(self.va_root, "Variables", "eliteMiningCommand.txt")
        self._va_last_command = ""
        self._va_command_watcher_running = True
        
        # Write exe path so VoiceAttack can find it to launch
        self._write_exe_path()
        
        self._check_va_command()
        log.info(f"VA command watcher started: {self._va_command_file}")
        print(f"[VA WATCHER] Watching: {self._va_command_file}")
    
    def _write_exe_path(self):
        """Write the EliteMining executable path to a file for VoiceAttack to use"""
        try:
            # Determine the exe path
            if getattr(sys, 'frozen', False):
                exe_path = sys.executable
            else:
                # For dev mode, point to the script location
                exe_path = os.path.abspath(__file__)
            
            # Write to Variables folder
            path_file = os.path.join(self.va_root, "Variables", "eliteMiningExePath.txt")
            with open(path_file, 'w', encoding='utf-8') as f:
                f.write(exe_path)
            print(f"[VA] Wrote exe path: {exe_path}")
        except Exception as e:
            log.error(f"Failed to write exe path: {e}")
    
    def _check_va_command(self):
        """Check for new VoiceAttack commands (called periodically)"""
        if not getattr(self, '_va_command_watcher_running', False):
            return
        
        try:
            if os.path.exists(self._va_command_file):
                with open(self._va_command_file, 'r', encoding='utf-8') as f:
                    command = f.read().strip()
                
                # Only process if there's a new non-empty command
                if command and command != self._va_last_command:
                    print(f"[VA COMMAND] Received: {command}")
                    self._va_last_command = command
                    self._execute_va_command(command)
                    
                    # Clear the file after processing
                    try:
                        with open(self._va_command_file, 'w', encoding='utf-8') as f:
                            f.write('')
                        self._va_last_command = ""  # Reset so same command can be sent again
                    except:
                        pass
        except Exception as e:
            log.debug(f"VA command check error: {e}")
        
        # Check again in 250ms (fast response)
        self.after(250, self._check_va_command)
    
    def _execute_va_command(self, command: str):
        """Execute a VoiceAttack command"""
        log.info(f"VA command received: {command}")
        
        try:
            parts = command.upper().split(':')
            cmd_type = parts[0] if parts else ""
            
            if cmd_type == "TAB":
                # Tab switching: TAB:MINING, TAB:HOTSPOTS, etc.
                tab_name = parts[1] if len(parts) > 1 else ""
                self._va_switch_tab(tab_name)
                
            elif cmd_type == "PRESET":
                # Preset handling: PRESET:LOAD:1, PRESET:SAVE:1
                action = parts[1] if len(parts) > 1 else ""
                num = int(parts[2]) if len(parts) > 2 else 1
                self._va_handle_preset(action, num)
                
            elif cmd_type == "SESSION":
                # Session control: SESSION:START, SESSION:END, SESSION:RESET
                action = parts[1] if len(parts) > 1 else ""
                self._va_handle_session(action)
                
            elif cmd_type == "SETTINGS":
                # Settings commands: SETTINGS:IMPORT, SETTINGS:APPLY
                action = parts[1] if len(parts) > 1 else ""
                self._va_handle_settings(action)
                
            elif cmd_type == "ANNOUNCEMENT":
                # Announcement presets: ANNOUNCEMENT:LOAD:1
                action = parts[1] if len(parts) > 1 else ""
                num = int(parts[2]) if len(parts) > 2 else 1
                self._va_handle_announcement_preset(action, num)
                
            elif cmd_type == "APP":
                # App control: APP:CLOSE, APP:MINIMIZE, APP:RESTORE
                action = parts[1] if len(parts) > 1 else ""
                self._va_handle_app(action)
                
            elif cmd_type == "SIDEBAR":
                action = parts[1] if len(parts) > 1 else ""
                if action in ("SHOW", "HIDE") and self._sidebar_visible != (action == "SHOW"):
                    self._toggle_sidebar_visibility()
                elif action == "SWAP" and self._sidebar_visible:
                    self._swap_sidebar_panes()

            elif cmd_type == "SEARCH":
                action = parts[1] if len(parts) > 1 else ""
                if action == "BEST_MINING_SYSTEM":
                    self.switch_to_tab('hotspots_finder')
                    self.ring_finder._bm_show_view()

            elif cmd_type == "BOOKMARK":
                action = parts[1] if len(parts) > 1 else ""
                if action == "ADD":
                    self.switch_to_tab('bookmarks')
                    self.prospector_panel._show_bookmark_dialog({
                        'system': self.prospector_panel.last_system,
                        'body': self.prospector_panel.last_body,
                    })

            elif cmd_type == "OVERLAY":
                # Overlay control: OVERLAY:ENABLE, OVERLAY:DISABLE, OVERLAY:STANDARD,
                # OVERLAY:ENHANCED, OVERLAY:CARGO:ON, OVERLAY:CARGO:OFF
                action = ":".join(parts[1:]) if len(parts) > 1 else ""
                self._va_handle_overlay(action)
                
            else:
                log.warning(f"Unknown VA command: {command}")
                
        except Exception as e:
            log.error(f"Error executing VA command '{command}': {e}")
    
    def _va_switch_tab(self, tab_name: str):
        """Switch to specified tab"""
        mining_tabs = {
            'REPORTS': '_reports_tab_frame',
            'STATISTICS': '_statistics_tab_frame',
            'MISSIONS': '_missions_tab_frame',
        }
        if tab_name in mining_tabs:
            panel = self.prospector_panel
            frame = getattr(panel, mining_tabs[tab_name], None)
            if frame is not None:
                self.switch_to_tab('mining_session')
                panel.nb.select(frame)
            return

        tab_mapping = {
            'MINING': 'mining_session',
            'HOTSPOTS': 'hotspots_finder',
            'MARKET': 'commodity_market',
            'ROUTE': 'route',
            'SYSTEMS': 'system_finder',
            'DISTANCE': 'distance_calculator',
            'VOICEATTACK': 'voiceattack',
            'BOOKMARKS': 'bookmarks',
            'SETTINGS': 'settings',
            'FLEETCARRIER': 'fleet_carrier',
        }
        
        internal_name = tab_mapping.get(tab_name)
        if internal_name:
            self.switch_to_tab(internal_name)
            self._set_status(f"Switched to {tab_name.title()} tab")
            log.info(f"VA: Switched to tab {internal_name}")
        else:
            log.warning(f"VA: Unknown tab name: {tab_name}")
    
    def _va_handle_preset(self, action: str, num: int):
        """Handle ship preset commands"""
        if action == "LOAD":
            # Load ship preset
            if hasattr(self, '_load_preset_by_number'):
                self._load_preset_by_number(num)
                self._set_status(f"Loaded ship preset {num}")
            elif hasattr(self, 'preset_tree'):
                # Fallback: try to select and load from tree
                self._set_status(f"Ship preset {num} (tree method not implemented)")
        elif action == "SAVE":
            self._set_status(f"Save preset via voice not supported")
    
    def _va_handle_session(self, action: str):
        """Handle mining session commands"""
        if not hasattr(self, 'prospector_panel') or not self.prospector_panel:
            log.warning("VA: Prospector panel not available")
            return
        
        # Auto-switch to Mining Session tab for session commands
        self.switch_to_tab('mining_session')
            
        if action == "START":
            if hasattr(self.prospector_panel, '_session_start'):
                self.prospector_panel._session_start()
                self._set_status("Mining session started")
        elif action == "STOP" or action == "END":
            # Stop/End = save session data
            if hasattr(self.prospector_panel, '_session_stop'):
                self.prospector_panel._session_stop()
                self._set_status("Mining session ended and saved")
        elif action == "PAUSE":
            # Pause/Resume toggle
            if hasattr(self.prospector_panel, '_toggle_pause_resume'):
                self.prospector_panel._toggle_pause_resume()
                # Check if now paused or resumed
                if getattr(self.prospector_panel, 'session_paused', False):
                    self._set_status("Mining session paused")
                else:
                    self._set_status("Mining session resumed")
        elif action == "CANCEL":
            # Cancel = discard session data
            if hasattr(self.prospector_panel, '_session_cancel'):
                self.prospector_panel._session_cancel()
                self._set_status("Mining session cancelled")
    
    def _va_handle_settings(self, action: str):
        """Handle settings commands (import/apply)"""
        if action == "IMPORT":
            if hasattr(self, '_import_all_from_txt'):
                self._import_all_from_txt()
                self._set_status("Imported settings from game")
        elif action == "APPLY":
            if hasattr(self, '_save_all_to_txt'):
                self._save_all_to_txt()
                self._set_status("Applied settings to game")
    
    def _va_handle_announcement_preset(self, action: str, num: int):
        """Handle announcement preset commands"""
        if action == "LOAD":
            if hasattr(self, '_ann_load_preset'):
                self._ann_load_preset(num)
                self._set_status(f"Loaded announcement preset {num}")
    
    def _va_handle_app(self, action: str):
        """Handle app control commands"""
        if action == "CLOSE":
            # Gracefully close the app
            print("[VA COMMAND] Closing EliteMining...")
            self._set_status("Closing EliteMining...")
            self.after(500, self._close_app_gracefully)
        elif action == "MINIMIZE":
            self.iconify()
            self._set_status("EliteMining minimized")
        elif action == "RESTORE":
            self.deiconify()
            self.lift()
            self.focus_force()
            self._set_status("EliteMining restored")
    
    def _va_handle_overlay(self, action: str):
        """Handle overlay control commands from VoiceAttack.
        
        Commands: OVERLAY:TEXT:ON, OVERLAY:TEXT:OFF,
                  OVERLAY:STANDARD:ON, OVERLAY:STANDARD:OFF,
                  OVERLAY:ENHANCED:ON, OVERLAY:ENHANCED:OFF,
                  OVERLAY:CARGO:ON, OVERLAY:CARGO:OFF
        """
        if action == "TEXT:ON":
            self.text_overlay_enabled.set(1)
            self._set_status("Text overlay enabled")
            log.info("VA: Text overlay enabled")
        elif action == "TEXT:OFF":
            self.text_overlay_enabled.set(0)
            self._set_status("Text overlay disabled")
            log.info("VA: Text overlay disabled")
        elif action == "STANDARD:ON":
            self.overlay_mode.set("standard")
            if hasattr(self, '_overlay_standard_var'):
                self._overlay_standard_var.set(1)
                self._overlay_enhanced_var.set(0)
            self._set_status("Overlay mode: Standard Text")
            log.info("VA: Standard overlay enabled")
        elif action == "STANDARD:OFF":
            self.overlay_mode.set("enhanced")
            if hasattr(self, '_overlay_standard_var'):
                self._overlay_standard_var.set(0)
                self._overlay_enhanced_var.set(1)
            self._set_status("Overlay mode: Enhanced Prospector")
            log.info("VA: Standard overlay disabled (switched to enhanced)")
        elif action == "ENHANCED:ON":
            self.overlay_mode.set("enhanced")
            if hasattr(self, '_overlay_standard_var'):
                self._overlay_standard_var.set(0)
                self._overlay_enhanced_var.set(1)
            self._set_status("Overlay mode: Enhanced Prospector")
            log.info("VA: Enhanced overlay enabled")
        elif action == "ENHANCED:OFF":
            self.overlay_mode.set("standard")
            if hasattr(self, '_overlay_standard_var'):
                self._overlay_standard_var.set(1)
                self._overlay_enhanced_var.set(0)
            self._set_status("Overlay mode: Standard Text")
            log.info("VA: Enhanced overlay disabled (switched to standard)")
        elif action == "CARGO:ON":
            self.cargo_show_in_overlay.set(True)
            self._set_status("Cargo status overlay enabled")
            log.info("VA: Cargo overlay enabled")
        elif action == "CARGO:OFF":
            self.cargo_show_in_overlay.set(False)
            self._set_status("Cargo status overlay disabled")
            log.info("VA: Cargo overlay disabled")
        else:
            log.warning(f"VA: Unknown overlay action: {action}")
    
    def _close_app_gracefully(self):
        """Close the app gracefully, saving state"""
        try:
            # Stop the command watcher
            self._va_command_watcher_running = False
            # Trigger normal close
            self.destroy()
        except Exception as e:
            log.error(f"Error during graceful close: {e}")
            self.destroy()
    
    # =========================================================================

    def _on_cargo_changed(self, event_type=None, count=0):
        """Callback when cargo monitor data changes - update integrated display
        
        Args:
            event_type: Optional event type (MarketSell, CargoTransfer, EjectCargo)
            count: Number of tons involved in the event
        """
        try:
            self._update_integrated_cargo_display()
            
            # Forward cargo events to prospector panel for multi-session tracking
            if event_type and count > 0 and hasattr(self, 'prospector_panel') and self.prospector_panel:
                if hasattr(self.prospector_panel, '_on_cargo_event'):
                    self.prospector_panel._on_cargo_event(event_type, count)
            
            # Also refresh prospector panel statistics and ship info
            if hasattr(self, 'prospector_panel') and self.prospector_panel:
                if hasattr(self.prospector_panel, '_refresh_statistics_display'):
                    self.prospector_panel._refresh_statistics_display()
                # Update ship info display when ship data changes
                if hasattr(self.prospector_panel, '_update_ship_info_display'):
                    self.prospector_panel._update_ship_info_display()
        except Exception as e:
            log.error(f"[DEBUG] Error in _on_cargo_changed: {e}")
            import traceback
            traceback.print_exc()

    def _refresh_ring_finder(self, is_new_discovery: bool = False):
        """Refresh Ring Finder database info and cache after hotspot added
        
        Args:
            is_new_discovery: True if newly discovered hotspots (should trigger auto-refresh)
        """
        try:
            if hasattr(self, 'ring_finder') and self.ring_finder:
                # Update database info counter
                if hasattr(self.ring_finder, '_update_database_info'):
                    self.ring_finder._update_database_info()
                
                # Clear any cached results to ensure fresh data in next search
                if hasattr(self.ring_finder, 'local_db') and hasattr(self.ring_finder.local_db, 'clear_cache'):
                    self.ring_finder.local_db.clear_cache()
                    
                # Clear the pending refresh flag
                if hasattr(self, '_pending_ring_finder_refresh'):
                    self._pending_ring_finder_refresh = False
                
                # Pass is_new_discovery info to auto-refresh check
                if is_new_discovery and hasattr(self.cargo_monitor, '_check_auto_refresh_ring_finder'):
                    # This will be called with the is_new_discovery flag
                    pass
        except Exception as e:
            log.warning(f"Warning: Ring Finder refresh failed: {e}")

    # ---------- Comprehensive Dashboard with Sub-tabs ----------
    def _build_mining_session_tab(self, frame: ttk.Frame) -> None:
        """Build the mining session control tab"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        # Create the ProspectorPanel within this frame
        try:
            self.prospector_panel = ProspectorPanel(frame, self.va_root, self._set_status, self.toggle_vars, self.text_overlay, self, self.announcement_vars, self.main_announcement_enabled, ToolTip)
            self.prospector_panel.grid(row=0, column=0, sticky="nsew")
            
            # Set auto-start preference after panel is created
            # Note: Auto-start is now handled exclusively by prospector panel via txt files
            # No need to override from config.json
            
            # Set prompt on cargo full preference after panel is created
            # Note: Prompt-when-full is now handled exclusively by prospector panel via txt files
            # No need to override from config.json
            
        except Exception as e:
            # Log detailed error
            import traceback
            error_details = traceback.format_exc()
            crash_log_path = os.path.join(app_dir, "prospector_init_crash.txt")
            try:
                with open(crash_log_path, "w", encoding="utf-8") as f:
                    f.write(f"ProspectorPanel Initialization Crash\n")
                    f.write(f"Time: {dt.datetime.now()}\n")
                    f.write(f"VoiceAttack Root: {self.va_root}\n")
                    f.write(f"Error: {str(e)}\n\n")
                    f.write(error_details)
            except:
                pass
            
            # Show error to user
            messagebox.showerror(
                "EliteMining - Mining Session Error",
                f"Failed to initialize Mining Session tab:\n\n{str(e)}\n\n"
                f"Log file: {crash_log_path}\n\n"
                f"Try running as Administrator."
            )
            raise
        
        # Set default journal folder and update label after a short delay to ensure prospector panel is fully initialized
        self.after(50, self._set_default_journal_folder)

    # ---------- Interface Options tab ----------
    def _build_settings_notebook(self, frame: ttk.Frame) -> None:
        """Build the Settings tab with sub-tabs for different setting categories"""
        # Title row with help link
        settings_title_row = ttk.Frame(frame)
        settings_title_row.pack(fill="x", pady=(0, 5))
        ttk.Label(settings_title_row, text=t('tabs.settings'), font=self._scaled_font(9, "bold")).pack(side="left")
        from ui.help_link import create_help_link
        create_help_link(settings_title_row, "settings-tab", t('settings.help_tooltip'), ToolTip).pack(side="left", padx=(6, 0))

        # Create a notebook for settings sub-tabs
        self.settings_notebook = ttk.Notebook(frame)
        self.settings_notebook.pack(fill="both", expand=True)

        # === ANNOUNCEMENTS SUB-TAB ===
        announcements_tab = ttk.Frame(self.settings_notebook, padding=8)
        self._build_announcements_tab(announcements_tab)
        self.settings_notebook.add(announcements_tab, text=t('settings.announcements'))

        # === GENERAL SETTINGS SUB-TAB ===
        general_tab = ttk.Frame(self.settings_notebook, padding=8)
        self._build_interface_options_tab(general_tab)
        self.settings_notebook.add(general_tab, text=t('settings.general_settings'))

    # ---------- About tab ----------
    def _build_about_tab(self, frame: ttk.Frame) -> None:
        """Build the About tab with app info, links, and credits"""
        import webbrowser
        from version import __version__, __build_date__
        from config import load_theme
        
        # Theme-aware background color
        _about_theme = load_theme()
        _about_bg = "#000000" if _about_theme == "elite_orange" else "#1e1e1e"
        
        # Main container - use grid for proper anchoring
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)  # Content area expands
        frame.rowconfigure(1, weight=0)  # Bottom support section stays fixed
        
        # Main content container - centered, scrollable area
        main_container = tk.Frame(frame, bg=_about_bg)
        main_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=(20, 10))
        
        # Center content frame
        center_frame = tk.Frame(main_container, bg=_about_bg)
        center_frame.pack(expand=True)
        
        # App title and version
        title_frame = tk.Frame(center_frame, bg=_about_bg)
        title_frame.pack(pady=(0, 10))
        
        # Try to load text logo image
        try:
            from path_utils import get_images_dir
            from PIL import Image, ImageTk
            import os
            logo_path = os.path.join(get_images_dir(), "EliteMining_txt_logo_transp_resize.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                # Resize to reasonable width (260px) maintaining aspect ratio
                orig_width, orig_height = img.size
                new_width = 260
                new_height = int(orig_height * (new_width / orig_width))
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                self._about_text_logo = ImageTk.PhotoImage(img)
                logo_label = tk.Label(title_frame, image=self._about_text_logo, bg=_about_bg)
                logo_label.pack(pady=(0, 5))
            else:
                # Fallback to text
                tk.Label(title_frame, text="EliteMining", font=self._scaled_font(18, "bold"), 
                         fg="#ffcc00", bg=_about_bg).pack()
        except Exception:
            # Fallback to text on error
            tk.Label(title_frame, text="EliteMining", font=self._scaled_font(18, "bold"), 
                     fg="#ffcc00", bg=_about_bg).pack()
        
        tk.Label(title_frame, text=f"Version {__version__}", font=self._scaled_font(10), 
                 fg="#888888", bg=_about_bg).pack()
        
        # Description
        tk.Label(center_frame, text=t('about.description'), 
                 font=self._scaled_font(11), fg="#e0e0e0", bg=_about_bg).pack(pady=(10, 20))
        
        # Separator
        tk.Frame(center_frame, height=1, bg="#444444", width=400).pack(pady=10)
        
        # Copyright and license
        tk.Label(center_frame, text=t('about.copyright'), 
                 font=self._scaled_font(10), fg="#e0e0e0", bg=_about_bg).pack()
        tk.Label(center_frame, text=t('about.license'), 
                 font=self._scaled_font(9), fg="#888888", bg=_about_bg).pack()
        
        # Separator
        tk.Frame(center_frame, height=1, bg="#444444", width=400).pack(pady=15)
        
        # Links section
        links_frame = tk.Frame(center_frame, bg=_about_bg)
        links_frame.pack(pady=10)
        
        # Define links
        links = [
            (t('about.discord'), "https://discord.gg/5dsF3UshRR"),
            (t('about.reddit'), "https://www.reddit.com/r/EliteDangerous/comments/1oflji3/elitemining_free_mining_hotspot_finder_app/"),
            (t('about.github'), "https://github.com/Viper-Dude/EliteMining"),
            (t('about.documentation'), "https://github.com/Viper-Dude/EliteMining#readme"),
            (t('about.report_bug'), "https://github.com/Viper-Dude/EliteMining/issues/new"),
        ]
        
        def open_link(url):
            webbrowser.open(url)
        
        # Theme-aware button colors
        _btn_bg = "#1a1a1a" if _about_theme == "elite_orange" else "#2a3a4a"
        _btn_fg = "#ff9900" if _about_theme == "elite_orange" else "#e0e0e0"
        _btn_active_bg = "#2a2a2a" if _about_theme == "elite_orange" else "#3a4a5a"
        _btn_active_fg = "#ffcc00" if _about_theme == "elite_orange" else "#ffffff"
        _btn_border = "#ff6600" if _about_theme == "elite_orange" else "#555555"
        
        for label, url in links:
            btn = tk.Button(links_frame, text=label, 
                           command=lambda u=url: open_link(u),
                           bg=_btn_bg, fg=_btn_fg, activebackground=_btn_active_bg,
                           activeforeground=_btn_active_fg, relief="ridge", bd=1, 
                           padx=12, pady=4, font=self._scaled_font(9), cursor="hand2",
                           width=12, highlightbackground=_btn_border, highlightthickness=1)
            btn.pack(side="left", padx=5)
        
        # Separator
        tk.Frame(center_frame, height=1, bg="#444444", width=400).pack(pady=15)
        
        # Credits section
        credits_frame = tk.Frame(center_frame, bg=_about_bg)
        credits_frame.pack(pady=10)
        
        tk.Label(credits_frame, text="Credits", font=self._scaled_font(10, "bold"), 
                 fg="#ffcc00", bg=_about_bg).pack()
        
        credits = [
            "EliteVA by Somfic",
            "Ardent API by Iain Collins",
            "EDCD/EDDN Community",
        ]
        
        for credit in credits:
            tk.Label(credits_frame, text=f"- {credit}", font=self._scaled_font(9), 
                     fg="#aaaaaa", bg=_about_bg).pack(anchor="w", padx=20)
        
        # Support/Donate section - anchored at bottom right of frame
        support_frame = tk.Frame(frame, bg=_about_bg)
        support_frame.grid(row=1, column=0, sticky="se", padx=20, pady=(5, 15))
        
        # Support text on the left
        support_text = tk.Label(
            support_frame,
            text=t('about.donation_text'),
            wraplength=350,
            justify="left",
            fg="#cccccc",
            bg=_about_bg,
            font=self._scaled_font(9, "italic"),
        )
        support_text.pack(side="left")
        
        # PayPal donate button on the right
        try:
            from path_utils import get_app_data_dir
            paypal_img = tk.PhotoImage(file=os.path.join(get_app_data_dir(), "Images", "paypal.png"))
            if paypal_img.width() > 50:
                scale = max(1, paypal_img.width() // 50)
                paypal_img = paypal_img.subsample(scale, scale)
            paypal_btn = tk.Label(support_frame, image=paypal_img, cursor="hand2", bg=_about_bg)
            paypal_btn.image = paypal_img
            paypal_btn.pack(side="left", padx=(15, 0))
            def open_paypal(event=None):
                webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=NZQTA4TGPDSC6")
            paypal_btn.bind("<Button-1>", open_paypal)
        except Exception as e:
            log.error(f"About tab PayPal widget failed: {e}")

    def _build_bookmarks_tab(self, frame: ttk.Frame) -> None:
        """Build the Bookmarks tab - Mining location bookmarks"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        # Use the prospector panel's bookmarks functionality
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel._create_bookmarks_panel(frame)

    def _build_tts_controls(self, parent) -> None:
        """Announcement voice and volume (also used as the default for Speak (TTS) events)"""
        _bg = "#000000" if self.current_theme == "elite_orange" else "#1e1e1e"
        _slider_trough = "#1a1a1a" if self.current_theme == "elite_orange" else "#444444"
        _slider_active = "#ff6600" if self.current_theme == "elite_orange" else "#444444"
        _slider_fg = "#ff8c00" if self.current_theme == "elite_orange" else "#ffffff"
        _btn_kw = dict(bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a", activeforeground="#ffffff",
                       relief="ridge", bd=1, font=self._scaled_font(8, "normal"), cursor="hand2")

        box = tk.Frame(parent, bg=_bg)
        box.grid(row=1, column=0, rowspan=2, sticky="sw", padx=(round(500 * self.ui_scale), 0), pady=(0, round(40 * self.ui_scale)))
        try:
            voice_values = announcer.list_voices()
        except Exception as e:
            log.error(f"Error getting voice list: {e}")
            voice_values = []
        if not hasattr(self, 'voice_choice'):
            self.voice_choice = tk.StringVar(value="")

        voice_label = tk.Label(box, text=t('settings.tts_voice'), bg=_bg, fg="#ffffff", font=self._scaled_font(9))
        voice_label.grid(row=1, column=0, sticky="w")
        ToolTip(voice_label, t('settings.tts_config_desc'))
        self.voice_combo = ttk.Combobox(box, textvariable=self.voice_choice, state="readonly", width=10,
                                        font=self._scaled_font(9), values=voice_values)
        self.voice_combo.grid(row=1, column=1, sticky="ew", padx=(8, 0))

        def _test_voice_interface():
            try:
                announcer.say(t('settings.tts_test_message'))
            except Exception as e:
                log.error(f"Error testing voice: {e}")
        tk.Button(box, text=t('settings.test_voice'), command=_test_voice_interface, **_btn_kw).grid(row=1, column=2, sticky="w", padx=(8, 0))

        def _fix_tts_interface():
            try:
                announcer.diagnose_tts()
                success = announcer.reinitialize_tts()
                if success:
                    announcer.say(t('settings.tts_reset_message'))
                    print("[INTERFACE] TTS engine reinitialized successfully")
                    self._refresh_voice_list()
                else:
                    log.error("[INTERFACE] Failed to reinitialize TTS engine")
            except Exception as e:
                log.error(f"[INTERFACE] Error reinitializing TTS: {e}")
        fix_tts_btn = tk.Button(box, text=t('settings.reset_tts'), command=_fix_tts_interface, **_btn_kw)
        fix_tts_btn.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 6))
        ToolTip(fix_tts_btn, t('tooltips.fix_tts'))

        if not hasattr(self, 'voice_volume'):
            try:
                self.voice_volume = tk.IntVar(value=announcer.get_volume())
            except Exception:
                self.voice_volume = tk.IntVar(value=80)

        def _on_volume_change(v):
            try:
                announcer.set_volume(int(float(v)))
                from config import update_config_value
                update_config_value("tts_volume", int(float(v)))
            except Exception as e:
                log.error(f"Error changing TTS volume: {e}")

        tk.Label(box, text=t('settings.tts_volume'), bg=_bg, fg="#ffffff", font=self._scaled_font(9)).grid(row=0, column=0, sticky="w", pady=(0, 6))
        # Slider with its value to the right ("100%") instead of floating above it
        vol_row = tk.Frame(box, bg=_bg)
        vol_row.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 6))
        ThemedSlider(vol_row, 0, 100, self.voice_volume, command=_on_volume_change, length=self._scaled_px(160),
                     bg=_bg, fg=_slider_fg, font=self._scaled_font(9), show_value=False,
                     scale=self._scaled_px(100) / 100, **slider_colors(self.current_theme)).pack(side="left")
        vol_text = tk.StringVar()
        def _sync_vol_text(*_a):
            try:
                vol_text.set(f"{int(self.voice_volume.get())}%")
            except (tk.TclError, ValueError):
                pass
        self.voice_volume.trace_add("write", _sync_vol_text)
        _sync_vol_text()
        tk.Label(vol_row, textvariable=vol_text, bg=_bg, fg=_slider_fg, font=self._scaled_font(9),
                 width=4, anchor="e").pack(side="left", padx=(6, 0))

        try:
            cfg = _load_cfg()
            saved_voice = cfg.get("tts_voice")
            if saved_voice and saved_voice in voice_values:
                self.voice_choice.set(saved_voice)
                try:
                    announcer.set_voice(saved_voice)
                except Exception as e:
                    log.error(f"Error setting saved voice: {e}")
            elif voice_values:
                self.voice_choice.set(voice_values[0])
            self.voice_volume.set(cfg.get("tts_volume", 80))
        except Exception:
            if voice_values:
                self.voice_choice.set(voice_values[0])

        def _on_voice_change_interface(event=None):
            try:
                sel = self.voice_choice.get()
                announcer.set_voice(sel)
                from config import update_config_value
                update_config_value("tts_voice", sel)
            except Exception as e:
                log.error(f"Error changing TTS voice: {e}")
        self.voice_combo.bind("<<ComboboxSelected>>", _on_voice_change_interface)

        # Refresh voice list after a short delay to ensure announcer is fully initialized
        self.after(100, self._refresh_voice_list)

    def _build_announcements_tab(self, frame: ttk.Frame) -> None:
        """Build the Announcements settings tab with full material functionality"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)
        
        # Active preset tracking
        self._active_preset_num = None
        self._active_preset_snapshot = None  # Snapshot of settings when preset was loaded

        # Active ship preset tracking
        self._active_ship_preset_name = None
        self._active_ship_preset_snapshot = None  # Snapshot of settings when preset was loaded
        self._active_ship_announcement_slot = None  # Linked announcement preset slot for the active ship preset

        # Basic announcement controls
        from ui.help_link import create_help_link
        announcement_heading = ttk.Frame(frame)
        announcement_heading.grid(row=0, column=0, sticky="nw", pady=(0, 10))
        ttk.Label(announcement_heading, text=t('settings.announcement_settings'), font=self._scaled_font(12, "bold")).pack(side="left")
        create_help_link(announcement_heading, "announcement-panel", t('common.help_tooltip'), ToolTip).pack(side="left", padx=(6, 0))

        # Check if prospector panel is available for advanced controls
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            # Import materials for full functionality
            try:
                from prospector_panel import ANNOUNCEMENT_TOGGLES, KNOWN_MATERIALS, CORE_ONLY
                
                # Main controls frame
                main_controls = ttk.Frame(frame)
                main_controls.grid(row=1, column=0, sticky="ew", pady=(0, 2))
                frame.columnconfigure(0, weight=1)
                
                # Left side: Announcement toggles
                toggles_frame = ttk.Frame(main_controls)
                toggles_frame.pack(side="left", padx=(0, 20))
                
                # Get theme for checkbox styling
                from config import load_theme
                _ann_cb_theme = load_theme()
                if _ann_cb_theme == "elite_orange":
                    _ann_cb_bg = "#000000"  # Black background for orange theme
                    _ann_cb_select = "#000000"
                else:
                    _ann_cb_bg = "#1e1e1e"
                    _ann_cb_select = "#1e1e1e"
                
                # Add announcement toggles if available
                if hasattr(self, 'announcement_vars') and self.announcement_vars:
                    ttk.Label(toggles_frame, text=t('settings.announcement_types'), font=self._scaled_font(9, "bold")).pack(anchor="w")
                    
                    # Localized display names and help texts for announcement toggles
                    toggle_display = {
                        "Core Asteroids": (t('settings.core_asteroids'), t('settings.core_asteroids_help')),
                        "Non-Core Asteroids": (t('settings.non_core_asteroids'), t('settings.non_core_asteroids_help'))
                    }
                    
                    self._ann_toggle_checks = {}
                    self._ann_toggle_base_fg = {}
                    for name, (_fname, helptext) in ANNOUNCEMENT_TOGGLES.items():
                        # Check if the variable exists before trying to use it
                        if name in self.announcement_vars:
                            # Get localized display name and help text
                            display_name, localized_help = toggle_display.get(name, (name, helptext))
                            checkbox = ThemedCheckbutton(toggles_frame, text=display_name, 
                                                    variable=self.announcement_vars[name], 
                                                    bg=_ann_cb_bg, fg="#ffffff", selectcolor=_ann_cb_select, 
                                                    activebackground=_ann_cb_bg, activeforeground="#ffffff", 
                                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                                    padx=4, pady=1, anchor="w")
                            checkbox.pack(anchor="w", padx=(10, 0))
                            self._ann_toggle_checks[name] = checkbox
                            ToolTip(checkbox, localized_help)
                
                # Right side: Threshold controls
                thr = ttk.Frame(main_controls)
                thr.pack(side="left")
                ttk.Label(thr, text=t('settings.announce_at')).pack(side="left")
                # Use theme-aware colors for spinbox
                _ann_spinbox_fg = "#ff8c00" if self.current_theme == "elite_orange" else "#ffffff"
                def _ann_threshold_changed(event=None):
                    try:
                        value = round(max(0.0, min(100.0, float(self.prospector_panel.threshold.get()))), 1)
                    except (ValueError, tk.TclError):
                        value = _load_cfg().get('announce_threshold', 20.0)
                    self.prospector_panel.threshold.set(value)
                    self.prospector_panel._save_threshold_value()
                    self._ann_check_modified()
                sp = Stepper(thr, 0.0, 100.0, self.prospector_panel.threshold, increment=0.5, width=5,
                             command=_ann_threshold_changed, bg=ttk.Style().lookup("TFrame", "background") or "#1e1e1e",
                             fg=_ann_spinbox_fg, font=self._scaled_font(9), scale=self._scaled_px(100) / 100,
                             accent=slider_colors(self.current_theme)["accent"])
                sp.pack(side="left", padx=(6, 4))
                self._ann_threshold_spin = sp
                ttk.Label(thr, text="%").pack(side="left")  # unit sits next to its value
                ToolTip(sp.entry, t('tooltips.announcement_threshold'))
                
                announcement_button = create_action_button if getattr(self, 'current_theme', '') in ('modern', 'modern_slate', 'modern_orange') else tk.Button
                set_all_btn = announcement_button(thr, text=t('settings.set_all'), command=self._ann_set_all_threshold,
                                       bg="#2a4a5a", fg="#ffffff", 
                                       activebackground="#3a5a6a", activeforeground="#ffffff",
                                       relief="solid", bd=1, cursor="hand2", pady=2, padx=8)
                set_all_btn.pack(side="left", padx=(10, 0))
                ToolTip(set_all_btn, t('tooltips.set_all_threshold'))
                self._build_tts_controls(frame)

                # Materials section label - fixed position to always stay visible
                ttk.Label(frame, text=t('settings.select_minerals'),
                          font=self._scaled_font(10, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 2))

                # Create the full material tree with functionality
                materials_frame = ttk.Frame(frame)
                materials_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
                materials_frame.columnconfigure(0, weight=1)
                materials_frame.rowconfigure(0, weight=1)
                
                # Make rows 0-2 fixed height (don't shrink), only row 3 is expandable
                frame.rowconfigure(0, weight=0, minsize=40)  # Top controls row
                frame.rowconfigure(1, weight=0, minsize=40)  # Main controls row  
                frame.rowconfigure(2, weight=0, minsize=30)  # Label row - always visible
                frame.rowconfigure(3, weight=1)  # Tree row - expandable

                # Configure Announcements Treeview style to match other tables
                style = ttk.Style()
                from config import load_theme
                ann_theme = load_theme()
                if ann_theme == "elite_orange":
                    ann_fg = "#ff8c00"
                    ann_bg = "#1e1e1e"
                else:
                    ann_fg = "#e6e6e6"
                    ann_bg = "#1e1e1e"
                
                style.configure("Announcements.Treeview",
                               background=ann_bg,
                               fieldbackground=ann_bg,
                               foreground=ann_fg,
                               font=self._scaled_font(9),
                               rowheight=self._scaled_px(28))
                style.configure("Announcements.Treeview.Heading",
                               foreground=ann_fg,
                               font=self._scaled_font(9, "bold"))

                # Material tree
                self.ann_mat_tree = StripedTreeview(materials_frame, columns=("announce", "material", "minpct"), show="headings", height=18, style="Announcements.Treeview", selectmode="none")
                self.ann_mat_tree.heading("announce", text=t('settings.announce'))
                self.ann_mat_tree.heading("material", text=t('settings.mineral'))
                self.ann_mat_tree.heading("minpct", text=t('settings.minimal_pct'))

                # minwidth is derived from the actual rendered header text width (at the
                # scaled heading font) rather than a fixed guess, so headers can never be
                # squeezed below what their own label needs, at any UI scale or language.
                import tkinter.font as _ann_tkfont
                _ann_heading_font = _ann_tkfont.Font(font=self._scaled_font(9, "bold"))
                _ann_header_pad = self._scaled_px(24)  # header cell padding + sort-arrow space

                def _ann_min_for(col_name):
                    header_text = self.ann_mat_tree.heading(col_name, "text")
                    return _ann_heading_font.measure(header_text) + _ann_header_pad

                _ann_minwidths = {
                    "announce": _ann_min_for("announce"),
                    "material": _ann_min_for("material"),
                    "minpct": _ann_min_for("minpct"),
                }
                self.ann_mat_tree.column("announce", width=max(self._scaled_px(90), _ann_minwidths["announce"]),
                                          minwidth=_ann_minwidths["announce"], anchor="center", stretch=False)
                self.ann_mat_tree.column("material", width=max(self._scaled_px(300), _ann_minwidths["material"]),
                                          minwidth=_ann_minwidths["material"], anchor="center", stretch=False)
                self.ann_mat_tree.column("minpct", width=max(self._scaled_px(100), _ann_minwidths["minpct"]),
                                          minwidth=_ann_minwidths["minpct"], anchor="center", stretch=False)
                self.ann_mat_tree.grid(row=0, column=0, sticky="nsew")

                ann_scrollbar = ttk.Scrollbar(materials_frame, orient="vertical", command=self.ann_mat_tree.yview)
                ann_scrollbar.grid(row=0, column=1, sticky="ns")
                self.ann_mat_tree.configure(yscrollcommand=ann_scrollbar.set)
                ann_hscrollbar = ttk.Scrollbar(materials_frame, orient="horizontal", command=lambda *a: (self.ann_mat_tree.xview(*a), self.ann_mat_tree.after_idle(_ann_position_minpct_spinboxes)))
                ann_hscrollbar.grid(row=1, column=0, sticky="ew")
                # Show the horizontal scrollbar only when the columns are wider than the table
                def _ann_xscroll_set(lo, hi):
                    if float(lo) <= 0.0 and float(hi) >= 1.0:
                        ann_hscrollbar.grid_remove()
                    else:
                        ann_hscrollbar.grid()
                    ann_hscrollbar.set(lo, hi)
                self.ann_mat_tree.configure(xscrollcommand=_ann_xscroll_set)

                # Columns are fixed-width (stretch=False) so drags stick; fill the
                # table once with the Mineral column on first layout only.
                _ann_filled = [False]
                # Restore saved widths (never below the header-based minimum)
                try:
                    from config import load_announcement_column_widths
                    _ann_saved = load_announcement_column_widths()
                    for _c, _w in (_ann_saved or {}).items():
                        if _c in _ann_minwidths:
                            self.ann_mat_tree.column(_c, width=max(int(_w), _ann_minwidths[_c]))
                            _ann_filled[0] = True
                except Exception as e:
                    print(f"[DEBUG] Could not load Announcement column widths: {e}")

                def _ann_save_widths(event=None):
                    try:
                        from config import save_announcement_column_widths
                        save_announcement_column_widths(
                            {c: int(self.ann_mat_tree.column(c, "width")) for c in ("announce", "material", "minpct")})
                    except Exception as e:
                        print(f"[DEBUG] Could not save Announcement column widths: {e}")
                self.ann_mat_tree.bind("<ButtonRelease-1>", _ann_save_widths, add='+')

                def _ann_fill_once(event):
                    if _ann_filled[0] or event.width < 200:
                        return
                    _ann_filled[0] = True
                    others = sum(int(self.ann_mat_tree.column(c, "width")) for c in ("announce", "minpct"))
                    free = event.width - others - self._scaled_px(4)
                    if free > int(self.ann_mat_tree.column("material", "width")):
                        self.ann_mat_tree.column("material", width=free)
                self.ann_mat_tree.bind("<Configure>", _ann_fill_once, add='+')

                # Configure alternating row colors
                self.ann_mat_tree.tag_configure('oddrow', background='#1e1e1e')
                self.ann_mat_tree.tag_configure('evenrow', background='#252525')

                # Create spinboxes for per-material thresholds
                self._ann_minpct_spin = {}
                self._ann_minpct_vars = {}

                # Stepper field colours follow the active theme instead of fixed white/grey.
                if self.current_theme in ('modern', 'modern_slate', 'modern_orange'):
                    _ann_field_bg, _ann_field_btn = modern_color("#14171B"), modern_color("#262C34")
                else:
                    _ann_field_bg, _ann_field_btn = "#151515", "#2d2d2d"
                _ann_diff_fg = self._preset_diff_fg()

                # Values changed since the active preset was last saved or loaded get an
                # accent colour (no active preset = no tint). Deferred so bulk changes
                # (Set all, presets) cost one pass.
                _ann_tint_pending = [False]
                def _ann_apply_tint():
                    _ann_tint_pending[0] = False
                    _snap = getattr(self, '_active_preset_snapshot', None)
                    _saved = (_snap or {}).get('min_pct_map') if getattr(self, '_active_preset_num', None) is not None else None
                    for _m, _sp in self._ann_minpct_spin.items():
                        try:
                            _val = round(float(self._ann_minpct_vars[_m].get()), 1)
                        except Exception:
                            continue
                        _changed = _saved is not None and _m in _saved and _val != _saved[_m]
                        _fg = _ann_diff_fg if _changed else _ann_spinbox_fg
                        try:
                            _sp.configure(fg=_fg, insertbackground=_fg)
                        except tk.TclError:
                            pass
                    _snap_on = _snap if getattr(self, '_active_preset_num', None) is not None else None
                    # "Announce at" threshold
                    _thr = getattr(self, '_ann_threshold_spin', None)
                    if _thr is not None:
                        try:
                            _chg = (_snap_on is not None and 'announce_threshold' in _snap_on
                                    and round(float(self.prospector_panel.threshold.get()), 1) != _snap_on['announce_threshold'])
                        except Exception:
                            _chg = False
                        _fg = _ann_diff_fg if _chg else _ann_spinbox_fg
                        try:
                            _thr.configure(fg=_fg, insertbackground=_fg)
                        except tk.TclError:
                            pass
                    # Core / Non-Core Asteroids checkboxes
                    for _name, _cb in getattr(self, '_ann_toggle_checks', {}).items():
                        try:
                            _now = str(_cb.cget("fg"))
                            if _now != _ann_diff_fg:
                                self._ann_toggle_base_fg[_name] = _now
                            _chg = (_snap_on is not None and _name in _snap_on
                                    and bool(self.announcement_vars[_name].get()) != bool(_snap_on[_name]))
                            _cb.configure(fg=_ann_diff_fg if _chg else self._ann_toggle_base_fg.get(_name, _now))
                        except (tk.TclError, KeyError):
                            pass
                    # Announce column: a table cell can't be coloured alone, so the whole row is
                    _tree = getattr(self, 'ann_mat_tree', None)
                    if _tree is not None:
                        try:
                            _tree.tag_configure('ann_changed', foreground=_ann_diff_fg)
                            _snap_map = (_snap_on or {}).get('announce_map', {})
                            for _m in KNOWN_MATERIALS:
                                _chg = (_snap_on is not None
                                        and bool(self.prospector_panel.announce_map.get(_m, True)) != bool(_snap_map.get(_m, True)))
                                _tags = tuple(_tree.item(_m, 'tags'))
                                if _chg and 'ann_changed' not in _tags:
                                    _tree.item(_m, tags=_tags + ('ann_changed',))
                                elif not _chg and 'ann_changed' in _tags:
                                    _tree.item(_m, tags=tuple(x for x in _tags if x != 'ann_changed'))
                        except tk.TclError:
                            pass
                def _ann_queue_tint(*_a):
                    if not _ann_tint_pending[0]:
                        _ann_tint_pending[0] = True
                        self.after_idle(_ann_apply_tint)
                self._ann_queue_tint = _ann_queue_tint  # also fired when the preset snapshot changes
                self.prospector_panel.threshold.trace_add("write", _ann_queue_tint)
                for _tv in getattr(self, 'announcement_vars', {}).values():
                    _tv.trace_add("write", _ann_queue_tint)

                def _on_ann_minpct_change_factory(material):
                    def _on_change():
                        try:
                            v = float(self._ann_minpct_vars[material].get())
                            v = round(max(0.0, min(100.0, v)), 1)
                            self._ann_minpct_vars[material].set(v)  # Update UI with validated value
                            self.prospector_panel.min_pct_map[material] = v
                            self.prospector_panel._save_min_pct_map()
                            self._ann_check_modified()
                        except ValueError:
                            # Reset to current saved value on invalid input
                            self._ann_minpct_vars[material].set(self.prospector_panel.min_pct_map.get(material, 0.0))
                    return _on_change

                # Populate with materials and create spinboxes
                row_idx = 0
                for mat in KNOWN_MATERIALS:
                    flag = self._ann_flag(self.prospector_panel.announce_map.get(mat, True))
                    row_tag = 'evenrow' if row_idx % 2 == 0 else 'oddrow'
                    # Get localized material name for display
                    from localization import get_material
                    display_mat = get_material(mat)
                    if mat in CORE_ONLY:
                        self.ann_mat_tree.insert("", "end", iid=mat, values=(flag, display_mat, t('settings.core_only')), tags=(row_tag,))
                    else:
                        self.ann_mat_tree.insert("", "end", iid=mat, values=(flag, display_mat, ""), tags=(row_tag,))
                        
                        # Create spinbox for non-core materials
                        v = self.prospector_panel.min_pct_map.get(mat, 0.0)
                        self._ann_minpct_vars[mat] = tk.DoubleVar(value=v)
                        
                        self._ann_minpct_spin[mat] = Stepper(
                            self.ann_mat_tree, 0.0, 100.0, self._ann_minpct_vars[mat], increment=0.5, width=5,
                            command=_on_ann_minpct_change_factory(mat), bg=_ann_field_bg, field_bg=_ann_field_bg,
                            button_bg=_ann_field_btn, fg=_ann_spinbox_fg, font=self._scaled_font(9),
                            scale=self._scaled_px(100) / 100, accent=slider_colors(self.current_theme)["accent"])
                        self._ann_minpct_vars[mat].trace_add("write", _ann_queue_tint)
                    row_idx += 1

                _ann_queue_tint()

                # Click on treeview (not on spinbox) to clear spinbox focus
                def _clear_spinbox_focus(event):
                    # Check if click is not on a spinbox
                    widget = event.widget.winfo_containing(event.x_root, event.y_root)
                    if not isinstance(getattr(widget, 'master', None), Stepper):
                        frame.focus_set()
                self.ann_mat_tree.bind("<Button-1>", _clear_spinbox_focus, add='+')

                # Add double-click handler to toggle announcement
                def _ann_toggle_announce(event):
                    if self.ann_mat_tree.identify_region(event.x, event.y) != "cell":
                        return  # headers and column dividers are not toggles
                    item = self.ann_mat_tree.identify_row(event.y)
                    if item and item in KNOWN_MATERIALS:
                        col = self.ann_mat_tree.identify_column(event.x)
                        if col == "#1":  # First column (announce)
                            try:
                                # Toggle
                                current_state = self.prospector_panel.announce_map.get(item, True)
                                new_state = not current_state
                                self.prospector_panel.announce_map[item] = new_state
                                self.prospector_panel._save_announce_map()
                                
                                # Update display immediately
                                flag = self._ann_flag(new_state)
                                current = self.ann_mat_tree.item(item, "values")
                                self.ann_mat_tree.item(item, values=(flag, current[1], current[2]))
                                print(f"Toggled {item}: {current_state} → {new_state}")
                                self._ann_check_modified()
                            except Exception as e:
                                log.error(f"Error toggling {item}: {e}")

                # Single click on the checkbox toggles (no double-click needed)
                self.ann_mat_tree.bind("<Button-1>", _ann_toggle_announce, add='+')

                # Position spinboxes
                def _ann_position_minpct_spinboxes():
                    try:
                        for material, spinbox in self._ann_minpct_spin.items():
                            if material in CORE_ONLY:
                                continue
                                
                            # Get the bounding box of the item
                            bbox = self.ann_mat_tree.bbox(material, "#3")  # Third column
                            if bbox:
                                x, y, width, height = bbox
                                # Scale-aware width that grows a little with the column; inset
                                # top/bottom so neighbouring boxes read as separate fields.
                                spinbox_width = min(max(width - self._scaled_px(8), 1),
                                                    max(self._scaled_px(96), int(width * 0.5)))
                                pad_y = self._scaled_px(3)
                                x_offset = (width - spinbox_width) // 2
                                spinbox.place(in_=self.ann_mat_tree, x=x + x_offset, y=y + pad_y,
                                              width=spinbox_width, height=max(height - 2 * pad_y, 1))
                            else:
                                spinbox.place_forget()
                    except Exception:
                        pass

                # Position spinboxes initially and on scroll
                self.ann_mat_tree.update_idletasks()
                _ann_position_minpct_spinboxes()
                
                def _ann_yscroll_set(lo, hi):
                    ann_scrollbar.set(lo, hi)
                    _ann_position_minpct_spinboxes()
                self.ann_mat_tree.configure(yscroll=_ann_yscroll_set)

                # Keep spinboxes under the Minimal % column while a divider is dragged,
                # after release, and when the table is resized.
                def _ann_reposition_later(event=None):
                    self.ann_mat_tree.after_idle(_ann_position_minpct_spinboxes)
                self.ann_mat_tree.bind("<B1-Motion>", _ann_reposition_later, add='+')
                self.ann_mat_tree.bind("<ButtonRelease-1>", _ann_reposition_later, add='+')
                self.ann_mat_tree.bind("<Configure>", _ann_reposition_later, add='+')

                # Buttons frame
                btns = ttk.Frame(frame)
                btns.grid(row=4, column=0, sticky="w", pady=(8, 0))
                self._ann_preset_notice = ttk.Label(frame, text="", font=self._scaled_font(8))
                self._ann_preset_notice.grid(row=5, column=0, sticky="w", pady=(2, 0))
                
                select_all_btn = announcement_button(btns, text=t('settings.select_all'), command=self._ann_select_all,
                                          bg="#2a5a2a", fg="#ffffff", 
                                          activebackground="#3a6a3a", activeforeground="#ffffff",
                                          relief="solid", bd=1, cursor="hand2", pady=3)
                select_all_btn.pack(side="left")
                ToolTip(select_all_btn, t('tooltips.select_all_materials'))
                
                unselect_all_btn = announcement_button(btns, text=t('settings.unselect_all'), command=self._ann_unselect_all,
                                           bg="#5a2a2a", fg="#ffffff", 
                                           activebackground="#6a3a3a", activeforeground="#ffffff",
                                           relief="solid", bd=1, cursor="hand2", pady=3)
                unselect_all_btn.pack(side="left", padx=(6, 0))
                ToolTip(unselect_all_btn, t('tooltips.unselect_all_materials'))
                
                # Store preset buttons for dynamic updates
                if not hasattr(self, 'preset_buttons'):
                    self.preset_buttons = {}
                
                # Load custom preset names from config
                cfg = self.prospector_panel._load_cfg() if hasattr(self, 'prospector_panel') else {}
                preset_names = cfg.get('preset_names', {})
                
                # Add preset buttons
                _preset_is_orange = hasattr(self, 'current_theme') and self.current_theme == "elite_orange"
                _preset_btn_bg = "#4a4a2a" if _preset_is_orange else "#3a3a3a"
                _preset_btn_hover = "#5a5a3a" if _preset_is_orange else "#4a4a4a"
                _preset_btn_hl = "#2a2a1a" if _preset_is_orange else "#2a2a2a"
                for i in range(1, 7):  # Preset 1 to 6
                    # Get custom name or use default
                    custom_name = preset_names.get(str(i), t('settings.preset_button').format(num=i))
                    
                    preset_btn = tk.Button(btns, text=custom_name,
                                         bg=_preset_btn_bg, fg="#ffffff",
                                         activebackground=_preset_btn_hover, activeforeground="#ffffff",
                                         relief="raised", bd=1,
                                         width=13, font=self._scaled_font(9), cursor="hand2", pady=3,
                                         highlightbackground=_preset_btn_hl, highlightcolor=_preset_btn_hl)
                    preset_btn.pack(side="left", padx=(8, 0))
                    
                    # Store button reference
                    self.preset_buttons[i] = preset_btn
                    
                    # Bind left and right click events
                    preset_btn.bind("<Button-1>", lambda e, num=i: self._ann_load_preset(num))
                    # Right-click opens Load / Save / Rename so a stray click can't overwrite a preset
                    preset_btn.bind("<Button-3>", lambda e, num=i: self._ann_show_preset_menu(num, e))

                    # Ctrl+Click (left or right) or Middle-click to rename preset
                    preset_btn.bind("<Button-2>", lambda e, num=i: self._rename_preset(num))
                    preset_btn.bind("<Control-Button-1>", lambda e, num=i: self._rename_preset(num))
                    preset_btn.bind("<Control-Button-3>", lambda e, num=i: self._rename_preset(num))
                    
                    # Fix button state after clicks (prevent stuck sunken appearance)
                    preset_btn.bind("<ButtonRelease-1>", lambda e: self._ann_update_preset_buttons())
                    preset_btn.bind("<ButtonRelease-2>", lambda e: self._ann_update_preset_buttons())
                    preset_btn.bind("<ButtonRelease-3>", lambda e: self._ann_update_preset_buttons())
                    preset_btn.bind("<Control-ButtonRelease-1>", lambda e: self._ann_update_preset_buttons())
                    preset_btn.bind("<Control-ButtonRelease-3>", lambda e: self._ann_update_preset_buttons())
                    
                    # Add tooltip
                    ToolTip(preset_btn, t('settings.preset_actions'))
                
                # Restore active preset and reload its settings on startup
                try:
                    active_num = cfg.get('active_preset_num')
                    if active_num is not None:
                        preset_key = f'announce_preset_{active_num}'
                        data = cfg.get(preset_key)
                        if data:
                            preset_announce = data.get('announce_map', {}).copy()
                            preset_minpct = data.get('min_pct_map', {}).copy()
                            for material in KNOWN_MATERIALS:
                                if material not in preset_announce:
                                    preset_announce[material] = self.prospector_panel.announce_map.get(material, True)
                                if material not in preset_minpct:
                                    preset_minpct[material] = self.prospector_panel.min_pct_map.get(material, 20.0)
                            self.prospector_panel.announce_map = preset_announce
                            self.prospector_panel.min_pct_map = preset_minpct
                            self.prospector_panel.threshold.set(data.get('announce_threshold', 20.0))
                            if hasattr(self, 'announcement_vars') and self.announcement_vars:
                                if "Core Asteroids" in self.announcement_vars and 'Core Asteroids' in data:
                                    self.announcement_vars["Core Asteroids"].set(data['Core Asteroids'])
                                if "Non-Core Asteroids" in self.announcement_vars and 'Non-Core Asteroids' in data:
                                    self.announcement_vars["Non-Core Asteroids"].set(data['Non-Core Asteroids'])
                            if hasattr(self, '_ann_minpct_vars'):
                                for mat, var in self._ann_minpct_vars.items():
                                    if mat in self.prospector_panel.min_pct_map:
                                        var.set(self.prospector_panel.min_pct_map[mat])
                            self._ann_update_display()
                        self._active_preset_num = active_num
                        self._active_preset_snapshot = self._ann_get_current_snapshot()
                        self._ann_update_preset_buttons()
                except Exception:
                    pass
                
            except ImportError:
                # Fallback if imports fail
                ttk.Label(frame, text="Announcement settings require the Mining Session to be initialized.\nPlease restart the application if this persists.", 
                         font=self._scaled_font(10), foreground="orange").grid(row=1, column=0, sticky="w", padx=20, pady=20)
        else:
            # Simple message if prospector panel not available
            ttk.Label(frame, text="Announcement settings will be available after the Mining Session initializes.\nPlease restart the application if this persists.", 
                     font=self._scaled_font(10), foreground="orange").grid(row=1, column=0, sticky="w", padx=20, pady=20)

    def _ann_get_current_snapshot(self):
        """Get a snapshot of current announcement settings for comparison"""
        if not hasattr(self, 'prospector_panel') or not self.prospector_panel:
            return None
        try:
            snapshot = {
                'announce_map': self.prospector_panel.announce_map.copy(),
                'min_pct_map': {k: round(v, 1) for k, v in self.prospector_panel.min_pct_map.items()},
                'announce_threshold': round(self.prospector_panel.threshold.get(), 1),
            }
            if hasattr(self, 'announcement_vars') and self.announcement_vars:
                if "Core Asteroids" in self.announcement_vars:
                    snapshot['Core Asteroids'] = self.announcement_vars["Core Asteroids"].get()
                if "Non-Core Asteroids" in self.announcement_vars:
                    snapshot['Non-Core Asteroids'] = self.announcement_vars["Non-Core Asteroids"].get()
            return snapshot
        except Exception:
            return None

    def _ann_is_preset_modified(self):
        """Check if current settings differ from the loaded preset snapshot"""
        if self._active_preset_num is None or self._active_preset_snapshot is None:
            return False
        current = self._ann_get_current_snapshot()
        if current is None:
            return False
        return current != self._active_preset_snapshot

    def _ann_set_active_preset(self, num):
        """Set the active preset and take a snapshot"""
        self._active_preset_num = num
        self._active_preset_snapshot = self._ann_get_current_snapshot()
        # Save to config — immediate attempt plus a delayed retry to beat the save throttle.
        # _save_announce_map/_save_min_pct_map fire just before this, so the immediate
        # save is often throttled (only cache-updated). The retry at 800 ms runs after
        # the 0.5 s throttle but within the 2 s cache TTL, so the load returns the full
        # in-memory cache (including all preset data) and the disk write succeeds.
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                cfg = self.prospector_panel._load_cfg()
                cfg['active_preset_num'] = num
                self.prospector_panel._save_cfg(cfg)
            except Exception:
                log.exception("Saving active announcement preset failed")

            def _retry_save():
                try:
                    cfg2 = self.prospector_panel._load_cfg()
                    cfg2['active_preset_num'] = num
                    self.prospector_panel._save_cfg(cfg2)
                except Exception:
                    log.exception("Retry saving active announcement preset failed")
            self.after(800, _retry_save)
        self._ann_update_preset_buttons()

    def _ann_clear_active_preset(self):
        """Clear active preset tracking"""
        self._active_preset_num = None
        self._active_preset_snapshot = None
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                cfg = self.prospector_panel._load_cfg()
                cfg.pop('active_preset_num', None)
                self.prospector_panel._save_cfg(cfg)
            except Exception:
                log.exception("Clearing active announcement preset failed")
        self._ann_update_preset_buttons()

    def _ann_update_preset_buttons(self):
        """Update all preset button visuals based on active state"""
        try:
            self._ann_queue_tint()  # refresh the per-mineral "changed since save" colouring
        except Exception:
            pass
        if not hasattr(self, 'preset_buttons'):
            return
        
        cfg = {}
        preset_names = {}
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                cfg = self.prospector_panel._load_cfg()
                preset_names = cfg.get('preset_names', {})
            except Exception:
                pass
        
        is_modified = self._ann_is_preset_modified()
        
        # Theme-aware colors
        is_orange = hasattr(self, 'current_theme') and self.current_theme == "elite_orange"
        if getattr(self, 'current_theme', '') in ('modern', 'modern_slate', 'modern_orange'):
            from ui.theme import get_theme_colors
            colors = get_theme_colors(self.current_theme)
            active_bg = colors['btn_bg_hover']
            active_hover = colors['btn_bg_hover']
            inactive_bg = colors['btn_bg']
            inactive_hover = colors['btn_bg_hover']
        elif is_orange:
            active_bg = "#5a3a0a"
            active_hover = "#6a4a1a"
            inactive_bg = "#4a4a2a"
            inactive_hover = "#5a5a3a"
        else:
            active_bg = "#2a4a6a"
            active_hover = "#3a5a7a"
            inactive_bg = "#3a3a3a"
            inactive_hover = "#4a4a4a"
        
        for i, btn in self.preset_buttons.items():
            base_name = preset_names.get(str(i), t('settings.preset_button').format(num=i))
            
            if i == self._active_preset_num:
                # Active preset — highlighted
                if is_modified:
                    diff_fg = self._preset_diff_fg()
                    btn.config(text=f"{base_name} *", bg=active_bg, fg=diff_fg,
                              activebackground=active_hover, activeforeground=diff_fg,
                              relief="raised")
                else:
                    btn.config(text=base_name, bg=active_bg, fg="#ffffff",
                              activebackground=active_hover, activeforeground="#ffffff",
                              relief="raised")
            else:
                # Inactive preset — default style
                btn.config(text=base_name, bg=inactive_bg, fg="#ffffff",
                          activebackground=inactive_hover, activeforeground="#ffffff",
                          relief="raised")

    def _ann_show_preset_menu(self, num, event):
        """Right-click menu for an announcement preset button."""
        from core.constants import get_menu_colors
        mc = get_menu_colors(self.current_theme)
        menu = tk.Menu(self, tearoff=0, bg=mc["bg"], fg=mc["fg"],
                       activebackground=mc["activebackground"], activeforeground=mc["activeforeground"],
                       font=self._scaled_font(9))
        menu.add_command(label=t('settings.preset_menu_load'), command=lambda: self._ann_load_preset(num))
        menu.add_command(label=t('settings.preset_menu_save'), command=lambda: self._ann_save_preset(num))
        menu.add_separator()
        menu.add_command(label=t('settings.preset_menu_rename'), command=lambda: self._rename_preset(num))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    @staticmethod
    def _ann_flag(enabled):
        """Checkbox-style glyph for the Announce column."""
        return "☑" if enabled else "☐"

    def _ann_check_modified(self):
        """Check if preset was modified and update button visuals"""
        self._ann_update_preset_buttons()

    def _ann_select_all(self):
        """Enable announcements for all materials"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS
                for mat in KNOWN_MATERIALS:
                    self.prospector_panel.announce_map[mat] = True
                self.prospector_panel._save_announce_map()
                self._ann_update_display()
                self._ann_check_modified()
            except Exception as e:
                log.error(f"Error in _ann_select_all: {e}")
    
    def _ann_unselect_all(self):
        """Disable announcements for all materials"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS
                for mat in KNOWN_MATERIALS:
                    self.prospector_panel.announce_map[mat] = False
                self.prospector_panel._save_announce_map()
                self._ann_update_display()
                self._ann_check_modified()
            except Exception as e:
                log.error(f"Error in _ann_unselect_all: {e}")
    
    def _ann_set_all_threshold(self):
        """Set all materials to the current threshold percentage"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS, CORE_ONLY
                threshold_val = self.prospector_panel.threshold.get()
                for mat in KNOWN_MATERIALS:
                    if mat not in CORE_ONLY:  # Only set threshold for non-core materials
                        self.prospector_panel.min_pct_map[mat] = threshold_val
                        # Update the spinbox if it exists
                        if hasattr(self, '_ann_minpct_vars') and mat in self._ann_minpct_vars:
                            self._ann_minpct_vars[mat].set(threshold_val)
                self.prospector_panel._save_min_pct_map()
                self._ann_check_modified()
            except Exception as e:
                log.error(f"Error in _ann_set_all_threshold: {e}")
            
    def _ann_update_display(self):
        """Update the announcements display"""
        if hasattr(self, 'ann_mat_tree') and hasattr(self, 'prospector_panel'):
            try:
                from prospector_panel import KNOWN_MATERIALS
                for mat in KNOWN_MATERIALS:
                    flag = self._ann_flag(self.prospector_panel.announce_map.get(mat, True))
                    current = self.ann_mat_tree.item(mat, "values")
                    if current:
                        self.ann_mat_tree.item(mat, values=(flag, current[1], current[2]))
            except Exception as e:
                log.error(f"Error in _ann_update_display: {e}")

    def _ann_save_preset(self, num):
        """Save current announcement settings as preset num"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                cfg = self.prospector_panel._load_cfg()
                preset_data = {
                    'announce_map': self.prospector_panel.announce_map.copy(),
                    'min_pct_map': self.prospector_panel.min_pct_map.copy(),
                    'announce_threshold': self.prospector_panel.threshold.get()
                }
                
                # Save Core/Non-Core settings if available
                if hasattr(self, 'announcement_vars') and self.announcement_vars:
                    if "Core Asteroids" in self.announcement_vars:
                        preset_data['Core Asteroids'] = self.announcement_vars["Core Asteroids"].get()
                    if "Non-Core Asteroids" in self.announcement_vars:
                        preset_data['Non-Core Asteroids'] = self.announcement_vars["Non-Core Asteroids"].get()
                
                cfg[f'announce_preset_{num}'] = preset_data
                self.prospector_panel._save_cfg(cfg)
                self._ann_set_active_preset(num)
                self._show_notice(self._ann_preset_notice, t('settings.preset_saved').format(num=num))
                
                # Visual feedback - flash button green then restore active style
                if hasattr(self, 'preset_buttons') and num in self.preset_buttons:
                    btn = self.preset_buttons[num]
                    btn.config(bg="#2a5a2a")
                    self.after(300, self._ann_update_preset_buttons)
            except Exception as e:
                log.error(f"Error saving preset {num}: {e}")

    def _ann_load_preset(self, num):
        """Load announcement settings from preset num"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS, CORE_ONLY
                cfg = self.prospector_panel._load_cfg()
                data = cfg.get(f'announce_preset_{num}')
                if not data:
                    from app_utils import centered_message
                    centered_message(self, t('settings.preset_load_title').format(num=num), t('settings.preset_empty').format(num=num))
                    return
                
                # Merge preset data with current materials to preserve new materials
                preset_announce = data.get('announce_map', {}).copy()
                preset_minpct = data.get('min_pct_map', {}).copy()
                
                # Fill in any missing materials with defaults
                for material in KNOWN_MATERIALS:
                    if material not in preset_announce:
                        preset_announce[material] = self.prospector_panel.announce_map.get(material, True)
                    if material not in preset_minpct:
                        preset_minpct[material] = self.prospector_panel.min_pct_map.get(material, 20.0)
                
                self.prospector_panel.announce_map = preset_announce
                self.prospector_panel.min_pct_map = preset_minpct
                self.prospector_panel.threshold.set(data.get('announce_threshold', 20.0))
                
                # Load Core/Non-Core settings if available
                if hasattr(self, 'announcement_vars') and self.announcement_vars:
                    if "Core Asteroids" in self.announcement_vars and 'Core Asteroids' in data:
                        self.announcement_vars["Core Asteroids"].set(data['Core Asteroids'])
                    if "Non-Core Asteroids" in self.announcement_vars and 'Non-Core Asteroids' in data:
                        self.announcement_vars["Non-Core Asteroids"].set(data['Non-Core Asteroids'])
                
                # Update spinboxes
                if hasattr(self, '_ann_minpct_vars'):
                    for mat, var in self._ann_minpct_vars.items():
                        if mat in self.prospector_panel.min_pct_map:
                            var.set(self.prospector_panel.min_pct_map[mat])
                
                self.prospector_panel._save_announce_map()
                self.prospector_panel._save_min_pct_map()
                self.prospector_panel._save_threshold_value()
                self._ann_update_display()
                self._ann_set_active_preset(num)
                self._show_notice(self._ann_preset_notice, t('settings.preset_loaded').format(num=num))
            except Exception as e:
                log.error(f"Error loading preset {num}: {e}")

    def _rename_preset(self, num):
        """Rename a preset with a custom name"""
        try:
            from config import load_theme
            from app_utils import get_app_icon_path
            
            cfg = self.prospector_panel._load_cfg() if hasattr(self, 'prospector_panel') else {}
            preset_names = cfg.get('preset_names', {})
            current_name = preset_names.get(str(num), t('settings.preset_button').format(num=num))
            
            # Theme colors
            theme = load_theme()
            bg = "#000000" if theme == "elite_orange" else "#1e1e1e"
            fg = "#ff8c00" if theme == "elite_orange" else "#e0e0e0"
            btn_bg = "#2a2a2a" if theme == "elite_orange" else "#3a3a3a"
            btn_fg = "#ff9900" if theme == "elite_orange" else "#ffffff"
            
            # Create dialog
            dialog = tk.Toplevel(self)
            dialog.withdraw()  # Hide initially to prevent blinking on wrong monitor
            dialog.title(t('settings.rename_preset').format(num=num))
            dialog.configure(bg=bg)
            dialog.resizable(False, False)
            
            # Set icon
            try:
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            # Main frame
            frame = tk.Frame(dialog, bg=bg, padx=20, pady=15)
            frame.pack(fill="both", expand=True)
            
            # Label
            tk.Label(frame, text=t('settings.enter_preset_name').format(num=num),
                    bg=bg, fg=fg,
                    font=self._scaled_font(10)).pack(pady=(0, 10))
            
            # Entry field
            name_var = tk.StringVar(value=current_name)
            entry = tk.Entry(frame, textvariable=name_var, 
                           width=25, font=self._scaled_font(10),
                           bg="#2a2a2a", fg="#ffffff",
                           insertbackground="#ffffff")
            entry.pack(pady=5)
            
            def save_name():
                new_name = name_var.get().strip()
                if new_name:
                    # Save to config
                    if 'preset_names' not in cfg:
                        cfg['preset_names'] = {}
                    cfg['preset_names'][str(num)] = new_name
                    self.prospector_panel._save_cfg(cfg)
                    
                    # Update button text with proper active styling
                    self._ann_update_preset_buttons()
                    
                    self._show_notice(self._ann_preset_notice, t('settings.preset_renamed').format(num=num, name=new_name))
                dialog.destroy()
            
            # Buttons
            btn_frame = tk.Frame(dialog, bg=bg)
            btn_frame.pack(pady=10)
            
            tk.Button(btn_frame, text=t('common.save'), command=save_name,
                     bg=btn_bg, fg=btn_fg, width=8,
                     activebackground="#4a4a4a", activeforeground=btn_fg,
                     font=self._scaled_font(9), relief="flat").pack(side="left", padx=5)
            tk.Button(btn_frame, text=t('common.cancel'), command=dialog.destroy,
                     bg=btn_bg, fg=btn_fg, width=8,
                     activebackground="#4a4a4a", activeforeground=btn_fg,
                     font=self._scaled_font(9), relief="flat").pack(side="left", padx=5)
            
            # Enter key to save
            entry.bind("<Return>", lambda e: save_name())
            
            from ui.dialogs import center_window
            dialog.bind("<Escape>", lambda e: dialog.destroy())
            dialog.update_idletasks()
            center_window(dialog, self)
            dialog.deiconify()
            dialog.attributes('-topmost', True)
            dialog.lift()
            dialog.focus_force()
            try:
                dialog.grab_set()
            except tk.TclError:
                pass
            entry.select_range(0, tk.END)
            entry.focus_set()

            def keep_on_top():
                if dialog.winfo_exists():
                    dialog.lift()
                    dialog.after(100, keep_on_top)
            keep_on_top()

        except Exception as e:
            log.error(f"Error renaming preset {num}: {e}")

    def _build_interface_options_tab(self, frame: ttk.Frame) -> None:
        # Theme-aware background color
        from config import load_theme
        _gs_theme = load_theme()
        _gs_bg = "#000000" if _gs_theme == "elite_orange" else "#1e1e1e"
        
        # Create a canvas and scrollbar for scrollable content
        canvas = tk.Canvas(frame, bg=_gs_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel to canvas for scrolling
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Bind mousewheel to canvas and all child widgets
        from app_utils import bind_mousewheel_recursive
        
        # Bind to canvas and scrollable_frame initially
        canvas.bind("<MouseWheel>", _on_mousewheel)
        scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
        
        # Rebind to all children after content is built
        def _bind_all_children():
            bind_mousewheel_recursive(scrollable_frame, _on_mousewheel)
        frame.after(100, _bind_all_children)

        # Now build content in scrollable_frame instead of frame
        scrollable_frame.columnconfigure(0, weight=1)
        ttk.Label(scrollable_frame, text=t('settings.interface_options'), font=self._scaled_font(12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        r = 1
        
        # ========== GENERAL INTERFACE SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.general_interface'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator1 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator1.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Tooltips option
        ThemedCheckbutton(scrollable_frame, text=t('settings.enable_tooltips'), variable=self.tooltips_enabled, 
                      bg=_gs_bg, fg="#ffffff", selectcolor=_gs_bg, activebackground=_gs_bg, 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground=_gs_bg, 
                      highlightcolor=_gs_bg, takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.tooltips_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Stay on top option
        ThemedCheckbutton(scrollable_frame, text=t('settings.stay_on_top'), variable=self.stay_on_top, 
                      bg=_gs_bg, fg="#ffffff", selectcolor=_gs_bg, activebackground=_gs_bg, 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground=_gs_bg, 
                      highlightcolor=_gs_bg, takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.stay_on_top_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Theme toggle option
        theme_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        theme_frame.grid(row=r, column=0, sticky="w")
        
        tk.Label(theme_frame, text=t('settings.theme') + ":", bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left", padx=(4, 10))
        
        current_theme_text = t("settings." + self._THEME_STR_KEYS[self.current_theme])
        self.theme_label = tk.Label(theme_frame, text=current_theme_text, bg=_gs_bg, fg="#ffcc00", font=self._scaled_font(9, "bold"))
        self.theme_label.pack(side="left", padx=(0, 15))
        
        _settings_theme_btn_text = t('settings.' + self._THEME_STR_KEYS.get(_gs_theme, "dark_theme")) + " ▾"
        # Style to match current theme
        if _gs_theme == "elite_orange":
            _sbtn_bg, _sbtn_fg = "#1a1a1a", "#ff8c00"
            _sbtn_active_bg, _sbtn_active_fg = "#ff8c00", "#000000"
        elif _gs_theme in ("modern", "modern_slate", "modern_orange"):
            _sbtn_bg, _sbtn_fg = modern_color("#262C34"), modern_color("#E6EAF0")
            _sbtn_active_bg, _sbtn_active_fg = modern_color("#FF9A32"), modern_color("#14171B")
        else:
            _sbtn_bg, _sbtn_fg = "#333333", "#ffffff"
            _sbtn_active_bg, _sbtn_active_fg = "#444444", "#ffffff"
        theme_toggle_settings = tk.Button(
            theme_frame,
            text=_settings_theme_btn_text,
            command=lambda: self._show_theme_menu(theme_toggle_settings),
            bg=_sbtn_bg,
            fg=_sbtn_fg,
            activebackground=_sbtn_active_bg,
            activeforeground=_sbtn_active_fg,
            relief="flat",
            bd=1,
            padx=8,
            pady=2,
            font=self._scaled_font(9),
            cursor="hand2"
        )
        theme_toggle_settings.pack(side="left")
        r += 1
        
        tk.Label(scrollable_frame, text=t("settings.theme_description"), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # UI scale option
        from config import load_ui_scale, save_ui_scale
        scale_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        scale_frame.grid(row=r, column=0, sticky="w")

        tk.Label(scale_frame, text=t('settings.ui_scale') + ":", bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left", padx=(4, 10))

        _ui_scale_options = {"100%": 1.0, "110%": 1.1, "120%": 1.2, "130%": 1.3, "150%": 1.5}
        _ui_scale_reverse = {v: k for k, v in _ui_scale_options.items()}
        _current_ui_scale = load_ui_scale()
        _current_ui_scale_display = _ui_scale_reverse.get(_current_ui_scale, "100%")

        self.ui_scale_var = tk.StringVar(value=_current_ui_scale_display)
        ui_scale_combo = ttk.Combobox(scale_frame, textvariable=self.ui_scale_var, width=10,
                                       values=list(_ui_scale_options.keys()), state="readonly")
        ui_scale_combo.pack(side="left", padx=(0, 15))

        def _on_ui_scale_change(event=None):
            selected = self.ui_scale_var.get()
            if _ui_scale_options.get(selected, 1.0) == load_ui_scale():
                return
            save_ui_scale(_ui_scale_options.get(selected, 1.0))

            from app_utils import centered_askyesno
            if centered_askyesno(scrollable_frame.winfo_toplevel(),
                t('settings.restart_required'),
                t('settings.restart_required_msg') + "\n\n" + t('settings.restart_now_prompt')):
                # Geometry was saved under the OLD scale; restart resizes to match the new one.
                self._restart_app(geometry_ui_scale=_current_ui_scale)

        ui_scale_combo.bind('<<ComboboxSelected>>', _on_ui_scale_change)
        r += 1

        tk.Label(scrollable_frame, text=t('settings.ui_scale_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # Language selector option
        lang_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        lang_frame.grid(row=r, column=0, sticky="w")
        
        tk.Label(lang_frame, text=t('settings.language') + ":", bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left", padx=(4, 10))
        
        # Import config functions once at the start
        from config import _load_cfg as load_config_func, _save_cfg as save_config_func
        
        # Get current language and available languages
        try:
            from localization import get_language, get_available_languages
            current_lang = get_language()
            available_langs = get_available_languages()
        except ImportError:
            current_lang = 'en'
            available_langs = ['en']
        
        # Language display names (no auto-detect - user chooses explicitly)
        lang_names = {
            'en': 'English',
            'de': 'Deutsch (German)',
            'fr': 'Français (French)',
            'es': 'Español (Spanish)',
            'ru': 'Русский (Russian)',
            'pt': 'Português (Portuguese)'
        }
        
        # Show current language as highlighted label (like Theme display)
        current_lang_display = lang_names.get(current_lang, 'English')
        # Try to load saved preference to show correct display
        saved_lang = current_lang
        try:
            cfg = load_config_func()
            saved_lang = cfg.get('language', 'en')  # Default to English
            # Convert 'auto' to 'en' for backwards compatibility
            if saved_lang == 'auto':
                saved_lang = 'en'
            if saved_lang in lang_names:
                current_lang_display = lang_names.get(saved_lang, 'English')
        except:
            current_lang_display = 'English'
        
        self.lang_display_label = tk.Label(lang_frame, text=current_lang_display, bg=_gs_bg, fg="#ffcc00", font=self._scaled_font(9, "bold"))
        self.lang_display_label.pack(side="left", padx=(0, 15))
        
        # Create language variable and combobox
        self.language_var = tk.StringVar(value=current_lang_display)
        lang_combo = ttk.Combobox(lang_frame, textvariable=self.language_var, width=20, state="readonly")
        
        # Build values list - available languages only (no auto-detect)
        lang_values = []
        for code in available_langs:
            if code in lang_names:
                lang_values.append(lang_names[code])
        lang_combo['values'] = tuple(lang_values)
        lang_combo.pack(side="left", padx=(0, 15))
        
        # Reverse mapping for saving
        self._lang_name_to_code = {v: k for k, v in lang_names.items()}
        
        def _on_language_change(event=None):
            selected_name = self.language_var.get()
            selected_code = self._lang_name_to_code.get(selected_name, 'en')
            if selected_code == load_config_func().get('language', 'en'):
                return

            # Update display label
            self.lang_display_label.config(text=selected_name)
            
            # Save to config
            try:
                cfg = load_config_func()
                cfg['language'] = selected_code
                save_config_func(cfg)
            except Exception as e:
                log.error(f"Error saving language setting: {e}")
            
            # Show restart prompt with option to restart now
            from app_utils import centered_askyesno
            if centered_askyesno(scrollable_frame.winfo_toplevel(),
                t('settings.restart_required'),
                t('settings.restart_required_msg') + "\n\n" + t('settings.restart_now_prompt')):
                # User chose to restart now
                self._restart_app()
        
        lang_combo.bind('<<ComboboxSelected>>', _on_language_change)
        r += 1
        
        tk.Label(scrollable_frame, text=t('settings.choose_language_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== EDDN SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.eddn'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator
        separator_eddn = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_eddn.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # EDDN send enable/disable
        ThemedCheckbutton(scrollable_frame, text="✓ " + t('settings.send_eddn'), variable=self.eddn_send_enabled, 
                      command=self._on_eddn_send_toggle,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.send_eddn_desc'), 
                 wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== TEXT OVERLAY DISPLAY SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.text_overlay'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator2 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator2.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        _sub_fg = "#ff8c00" if _gs_theme == "elite_orange" else "#cccccc"
        _slider_trough = "#1a1a1a" if _gs_theme == "elite_orange" else "#444444"
        _slider_active = "#ff6600" if _gs_theme == "elite_orange" else "#444444"
        _slider_fg = "#ff8c00" if _gs_theme == "elite_orange" else "#ffffff"
        _cb_kw = dict(bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9),
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e",
                      highlightcolor="#1e1e1e", takefocus=False)
        _label_w = 30  # label width in characters - keeps every label/control pair in the groups below aligned

        def _sub_heading(row, text):
            tk.Label(scrollable_frame, text=text, bg=_gs_bg, fg=_sub_fg,
                     font=self._scaled_font(9, "bold")).grid(row=row, column=0, sticky="w", pady=(10, 2))

        def _labelled_row(row, label_text, indent=0):
            frame = tk.Frame(scrollable_frame, bg=_gs_bg)
            frame.grid(row=row, column=0, sticky="w", padx=(indent, 0), pady=(4, 0))
            tk.Label(frame, text=label_text, width=_label_w, anchor="w", bg=_gs_bg, fg="#ffffff",
                     font=self._scaled_font(9)).pack(side="left")
            return frame

        def _slider_row(row, label_text, variable, from_, to, unit, indent=0):
            frame = _labelled_row(row, label_text, indent)
            scale = ThemedSlider(frame, from_, to, variable, length=self._scaled_px(140), bg=_gs_bg, fg=_slider_fg,
                                 font=self._scaled_font(9), scale=self._scaled_px(100) / 100,
                                 **slider_colors(_gs_theme))
            scale.pack(side="left")
            tk.Label(frame, text=unit, bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left")
            return scale

        def _desc(row, text):
            tk.Label(scrollable_frame, text=text, wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                     font=self._scaled_font(8, "italic")).grid(row=row, column=0, sticky="w", pady=(0, 6))

        # ----- General: applies to every overlay -----
        _sub_heading(r, t('settings.overlay_group_general'))
        r += 1
        # Text overlay enable/disable + Hide in Supercruise + mining session + game focus on one row
        text_overlay_row = tk.Frame(scrollable_frame, bg=_gs_bg)
        text_overlay_row.grid(row=r, column=0, sticky="w")
        ThemedCheckbutton(text_overlay_row, text=t('settings.enable_text_overlay'), variable=self.text_overlay_enabled,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9),
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e",
                      highlightcolor="#1e1e1e", takefocus=False).pack(side="left")
        self._sc_checkbox = ThemedCheckbutton(text_overlay_row, text=t('settings.hide_overlays_in_supercruise'), variable=self.hide_overlays_in_supercruise,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9),
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e",
                      highlightcolor="#1e1e1e", takefocus=False)
        self._sc_checkbox.pack(side="left", padx=(8, 0))

        def _on_mining_session_toggle(*a):
            if self.overlay_only_mining_session.get():
                self.hide_overlays_in_supercruise.set(False)
                self._sc_checkbox.config(state="disabled", fg="#666666")
            else:
                if bool(self.text_overlay_enabled.get()):
                    self._sc_checkbox.config(state="normal", fg="#ffffff")
            self._save_cargo_preferences()

        self._mining_session_cb = ThemedCheckbutton(text_overlay_row, text=t('settings.overlay_only_mining_session'), variable=self.overlay_only_mining_session,
                      command=_on_mining_session_toggle,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9),
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e",
                      highlightcolor="#1e1e1e", takefocus=False)
        self._mining_session_cb.pack(side="left", padx=(8, 0))
        _focused_cb = ThemedCheckbutton(text_overlay_row, text=t('settings.overlay_only_game_focused'), variable=self.overlay_only_game_focused,
                      command=self._save_cargo_preferences, **_cb_kw)
        _focused_cb.pack(side="left", padx=(8, 0))
        # Apply initial state — grey out supercruise checkbox if mining session is already enabled
        if self.overlay_only_mining_session.get():
            self._sc_checkbox.config(state="disabled", fg="#666666")
        r += 1
        _desc(r, t('settings.text_overlay_desc'))
        r += 1

        # ----- Appearance: brightness, color, size -----
        _sub_heading(r, t('settings.overlay_group_appearance'))
        r += 1
        self.transparency_scale = _slider_row(r, t('settings.text_brightness'), self.text_overlay_transparency, 10, 100, "%")
        r += 1

        # Text color selection with actual colors shown
        color_frame = _labelled_row(r, t('settings.text_color'))

        # Localized color names mapping
        color_display_names = {
            "White": t('settings.color_white'),
            "Yellow": t('settings.color_yellow'),
            "Orange": t('settings.color_orange'),
            "Light Blue": t('settings.color_light_blue'),
            "Light Green": t('settings.color_light_green'),
            "Light Gray": t('settings.color_light_gray'),
            "Cyan": t('settings.color_cyan'),
            "Magenta": t('settings.color_magenta')
        }
        self._color_display_to_internal = {v: k for k, v in color_display_names.items()}

        self.color_menu = ColorSwatchPicker(
            color_frame, self.color_options, self.text_overlay_color, names=color_display_names,
            bg=_gs_bg, ring=slider_colors(_gs_theme)["accent"], font=self._scaled_font(9),
            scale=self._scaled_px(100) / 100)
        self.color_menu.pack(side="left")
        r += 1

        # Text size selection with localized options
        size_frame = _labelled_row(r, t('settings.text_size'))

        self.size_combo = SegmentedSelector(
            size_frame,
            [("Small", t('settings.text_size_small')), ("Normal", t('settings.text_size_normal')),
             ("Large", t('settings.text_size_large'))],
            self.text_overlay_size, bg=_gs_bg, accent=slider_colors(_gs_theme)["accent"],
            font=self._scaled_font(8), scale=self._scaled_px(100) / 100)
        self.size_combo.pack(side="left")
        r += 1
        _desc(r, t('settings.overlay_appearance_desc'))
        r += 1

        # ----- Prospector & Cargo overlay -----
        _sub_heading(r, t('settings.overlay_group_prospector_cargo'))
        r += 1
        # Overlay mode selection (Standard / Enhanced Prospector / Cargo Status) - all on one line
        mode_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        mode_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(mode_frame, text=t('settings.overlay_mode'), bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left")

        self._overlay_standard_var = tk.IntVar(value=1 if self.overlay_mode.get() == "standard" else 0)
        self._overlay_enhanced_var = tk.IntVar(value=1 if self.overlay_mode.get() == "enhanced" else 0)

        def _on_standard_cb(*a):
            if self._overlay_standard_var.get():
                self._overlay_enhanced_var.set(0)
                self.overlay_mode.set("standard")
            else:
                if not self._overlay_enhanced_var.get():
                    self._overlay_standard_var.set(1)

        def _on_enhanced_cb(*a):
            if self._overlay_enhanced_var.get():
                self._overlay_standard_var.set(0)
                self.overlay_mode.set("enhanced")
            else:
                if not self._overlay_standard_var.get():
                    self._overlay_enhanced_var.set(1)

        _std_cb = ThemedCheckbutton(mode_frame, text=t('settings.overlay_standard'), variable=self._overlay_standard_var,
                      command=_on_standard_cb, **_cb_kw)
        _std_cb.pack(side="left", padx=(8, 0))
        _enh_cb = ThemedCheckbutton(mode_frame, text=t('settings.overlay_enhanced'), variable=self._overlay_enhanced_var,
                      command=_on_enhanced_cb, **_cb_kw)
        _enh_cb.pack(side="left", padx=(8, 0))
        _cargo_cb = ThemedCheckbutton(mode_frame, text=t('settings.cargo_overlay'), variable=self.cargo_show_in_overlay,
                      **_cb_kw)
        _cargo_cb.pack(side="left", padx=(8, 0))
        self._overlay_mode_cbs = [_std_cb, _enh_cb, _cargo_cb, _focused_cb]
        r += 1
        _desc(r, t('settings.overlay_mode_desc'))
        r += 1
        # Display duration slider
        self.duration_scale = _slider_row(r, t('settings.display_duration'), self.text_overlay_duration, 5, 30, t('settings.seconds'))
        r += 1
        _desc(r, t('settings.duration_desc'))
        r += 1

        # ----- Auto Prices overlay (Ring Finder) -----
        _sub_heading(r, t('settings.overlay_group_auto_prices'))
        r += 1
        self._auto_prices_overlay_cb = ThemedCheckbutton(scrollable_frame, text=t('settings.overlay_show_auto_prices'),
                                                      variable=self.auto_prices_overlay, **_cb_kw)
        self._auto_prices_overlay_cb.grid(row=r, column=0, sticky="w")
        r += 1
        # Same saved setting as "In-system prices only" in Rank Minerals / Find Best Mining System
        from config import load_pp_mode, save_pp_mode
        self.auto_prices_in_system = tk.BooleanVar(value=load_pp_mode())
        _in_system_cb = ThemedCheckbutton(scrollable_frame, text=t('settings.overlay_auto_prices_in_system'), variable=self.auto_prices_in_system,
                      command=lambda: save_pp_mode(self.auto_prices_in_system.get()), **_cb_kw)
        _in_system_cb.grid(row=r, column=0, sticky="w")
        self._auto_prices_in_system_cb = _in_system_cb
        # The setting is also changed from the Ring Finder menu and the Rank Minerals / Find Best
        # dialogs - re-read it whenever this tab is shown so the checkbox never shows a stale value
        _in_system_cb.bind("<Map>", lambda e: self.auto_prices_in_system.set(load_pp_mode()))
        r += 1
        self.auto_prices_duration_scale = _slider_row(r, t('settings.overlay_auto_prices_duration'),
                                                      self.auto_prices_overlay_duration, 10, 60, t('settings.seconds'), indent=24)
        # Always enabled: it also sets when Auto Prices returns the Hotspots Finder to Hotspots
        _dur_frame = self.auto_prices_duration_scale.master
        for _w in (_dur_frame, *_dur_frame.winfo_children()):
            ToolTip(_w, t('settings.overlay_auto_prices_duration_tooltip'), wraplength=360)
        r += 1

        # Apply initial greyed-out state for overlay sub-controls if master toggle is off
        self._apply_overlay_enabled_state()

        # ========== JOURNAL FILES SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.journal_files'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator4 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator4.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Journal folder path setting
        journal_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        journal_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(journal_frame, text=t('settings.journal_location'), bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left")
        
        # Initialize journal label (will be updated after prospector panel creation)
        self.journal_lbl = tk.Label(journal_frame, text="(not set)", fg="gray", bg=_gs_bg, font=self._scaled_font(9))
        self.journal_lbl.pack(side="left", padx=(6, 0))
        
        journal_btn = tk.Button(journal_frame, text=t('settings.change'), command=self._change_journal_dir,
                               bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                               activeforeground="#ffffff", relief="ridge", bd=1, 
                               font=self._scaled_font(8, "normal"), cursor="hand2")
        journal_btn.pack(side="left", padx=(8, 0))
        ToolTip(journal_btn, t('tooltips.journal_folder'))
        
        import_btn = tk.Button(journal_frame, text=t('settings.import_history'), command=self._import_journal_history,
                              bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                              activeforeground="#ffffff", relief="ridge", bd=1,
                              font=self._scaled_font(8, "normal"), cursor="hand2")
        import_btn.pack(side="left", padx=(8, 0))
        ToolTip(import_btn, t('tooltips.import_history'))
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.journal_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Import prompt preference checkbox
        self.ask_import_on_path_change = tk.IntVar()
        import_prompt_check = ThemedCheckbutton(
            scrollable_frame,
            text=t('settings.ask_import_prompt'),
            variable=self.ask_import_on_path_change,
            command=self._save_import_prompt_preference,
            bg=_gs_bg,
            fg="#ffffff",
            selectcolor="#34495e",
            activebackground="#1e1e1e",
            activeforeground="#ffffff",
            font=self._scaled_font(9)
        )
        import_prompt_check.grid(row=r, column=0, sticky="w", pady=(0, 4))
        
        # Load preference
        cfg = _load_cfg()
        self.ask_import_on_path_change.set(1 if cfg.get("ask_import_on_path_change", True) else 0)
        r += 1
        
        # Auto-scan journals on startup checkbox
        ThemedCheckbutton(scrollable_frame, text=t('settings.auto_scan_journals'), variable=self.auto_scan_journals, 
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.auto_scan_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== AUTOMATION SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.automation_title'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator line
        separator_automation = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_automation.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Auto-search hotspots after FSD jump checkbox
        def _on_auto_search_toggle():
            enabled = self.auto_search_enabled.get()
            # Sync with ring_finder
            if hasattr(self, 'ring_finder') and self.ring_finder and hasattr(self.ring_finder, 'auto_search_var'):
                self.ring_finder.auto_search_var.set(enabled)
                self.ring_finder._on_auto_search_toggle()
            self._set_status(f"Auto-search hotspots {'enabled' if enabled else 'disabled'}")
        
        ThemedCheckbutton(scrollable_frame, text=t('settings.auto_search_hotspots'), variable=self.auto_search_enabled, 
                      command=_on_auto_search_toggle,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.auto_search_hotspots_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Auto-switch tabs checkbox
        ThemedCheckbutton(scrollable_frame, text=t('settings.auto_switch_tabs'), variable=self.auto_switch_tabs, 
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=self._scaled_font(9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.auto_switch_tabs_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== SCREENSHOTS FOLDER SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.screenshots_folder_title'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator line
        separator_screenshots = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_screenshots.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Screenshots folder path setting
        screenshots_folder_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        screenshots_folder_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(screenshots_folder_frame, text=t('settings.screenshots_folder_label'), bg=_gs_bg, fg="#ffffff", font=self._scaled_font(9)).pack(side="left")
        
        # Create StringVar for screenshots folder path
        self.screenshots_folder_path = tk.StringVar()
        self.screenshots_folder_path.set(_load_cfg().get('screenshots_folder', os.path.join(os.path.expanduser("~"), "Pictures")))
        
        # Initialize screenshots folder label (will be updated with actual path)
        self.screenshots_folder_lbl = tk.Label(screenshots_folder_frame, text=self.screenshots_folder_path.get(), fg="gray", bg=_gs_bg, font=self._scaled_font(9))
        self.screenshots_folder_lbl.pack(side="left", padx=(6, 0))
        
        screenshots_btn = tk.Button(screenshots_folder_frame, text=t('settings.change'), command=self._change_screenshots_folder,
                                  bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                  activeforeground="#ffffff", relief="ridge", bd=1, 
                                  font=self._scaled_font(8, "normal"), cursor="hand2")
        screenshots_btn.pack(side="left", padx=(8, 0))
        ToolTip(screenshots_btn, t('tooltips.screenshots_folder'))
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.screenshots_folder_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== BACKUP & RESTORE SECTION ==========
        from ui.help_link import create_help_link
        backup_heading = ttk.Frame(scrollable_frame)
        backup_heading.grid(row=r, column=0, sticky="w", pady=(5, 8))
        ttk.Label(backup_heading, text=t('settings.backup_restore_title'), font=self._scaled_font(10, "bold")).pack(side="left")
        create_help_link(backup_heading, "backup--restore", t('common.help_tooltip'), ToolTip).pack(side="left", padx=(6, 0))
        r += 1
        
        # Add a subtle separator line
        separator6 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator6.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Backup and Restore buttons frame
        backup_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        backup_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        
        backup_btn = tk.Button(backup_frame, text="📦 " + t('settings.backup_button'), command=self._show_backup_dialog,
                              bg="#2a3a4a", fg="#e0e0e0", 
                              activebackground="#3a4a5a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=12, pady=4,
                              font=self._scaled_font(9, "normal"), cursor="hand2")
        compact_classic_button(backup_btn)
        backup_btn.pack(side="left", padx=(0, 8))
        _backup_tooltip = t('tooltips.backup')
        ToolTip(backup_btn, _backup_tooltip)
        
        restore_btn = tk.Button(backup_frame, text="📂 " + t('settings.restore_button'), command=self._show_restore_dialog,
                               bg="#4a3a2a", fg="#e0e0e0", 
                               activebackground="#5a4a3a", activeforeground="#ffffff",
                               relief="ridge", bd=1, padx=12, pady=4,
                               font=self._scaled_font(9, "normal"), cursor="hand2")
        compact_classic_button(restore_btn)
        restore_btn.pack(side="left")
        ToolTip(restore_btn, t('tooltips.restore'))
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.backup_restore_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== VOICEATTACK PROFILE SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.va_profile_section'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1

        separator_va = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_va.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1

        va_keybind_btn = tk.Button(scrollable_frame, text=t('settings.va_keybind_preserve_button'),
                                  command=self._manual_va_keybind_preserve,
                                  bg="#2a3a4a", fg="#e0e0e0",
                                  activebackground="#3a4a5a", activeforeground="#ffffff",
                                  relief="ridge", bd=1, padx=12, pady=4,
                                  font=self._scaled_font(9, "normal"), cursor="hand2")
        compact_classic_button(va_keybind_btn)
        va_keybind_btn.grid(row=r, column=0, sticky="w", pady=(4, 0))
        ToolTip(va_keybind_btn, t('tooltips.va_keybind_preserve'))
        r += 1
        tk.Label(scrollable_frame, text=t('settings.va_keybind_preserve_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== UPDATES SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.updates_title'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator5 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator5.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Check for updates button
        update_btn = tk.Button(scrollable_frame, text=t('settings.check_for_updates'), command=self._manual_update_check,
                              bg="#2a4a2a", fg="#e0e0e0", 
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=12, pady=4,
                              font=self._scaled_font(9, "normal"), cursor="hand2")
        update_btn.grid(row=r, column=0, sticky="w", pady=(4, 0))
        r += 1
        tk.Label(scrollable_frame, text=t('settings.updates_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=self._scaled_font(8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1



    def _create_main_sidebar(self) -> None:
        """Create the main Ship Presets and Cargo Monitor sidebar"""
        # Create the sidebar frame - add to main paned window
        # Reduced bottom padding (6,6,10,0) so cargo monitor aligns with app bottom
        sidebar = ttk.Frame(self.main_paned, padding=(6, 6, 10, 8 if self.current_theme in ("modern", "modern_slate", "modern_orange") else 0))
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)  # Paned window expands
        sidebar.rowconfigure(1, weight=0)  # Theme button row fixed
        
        # Add both panes to the horizontal paned window
        # Content frame was already created in _build_ui, add it first
        # Then add sidebar
        self.main_paned.add(sidebar, weight=1)
        
        # Flag to prevent saving sash position until initial layout is complete
        self._sash_initialized = False
        self._sidebar_sash_initialized = False
        self._startup_resize_settled = False

        # Store sidebar reference for later sash setup
        self._sidebar_frame = sidebar
        
        # Set initial main sash position after window is displayed
        def _set_initial_sash(retry_count=0):
            try:
                self.update_idletasks()
                total_width = self.winfo_width()
                
                if total_width < 400:
                    if retry_count < 10:
                        self.after(200, lambda: _set_initial_sash(retry_count + 1))
                        return
                    else:
                        return
                
                # Minimum widths
                from config import load_ui_scale
                _scale = load_ui_scale()
                min_content_width = 600
                min_sidebar_width = self._scaled_px(280)
                default_sidebar_width = round(300 * _scale)
                max_sidebar_width = round(500 * _scale)

                # Try to restore saved position first
                from config import load_main_sash_position
                saved_pos = load_main_sash_position()

                # Saved position is an absolute pixel value laid out under the
                # previous UI scale - rescale it to match a changed window size.
                if saved_pos is not None and self._ui_scale_resize_ratio != 1.0:
                    saved_pos = round(saved_pos * self._ui_scale_resize_ratio)

                # Validate saved position ensures both areas have minimum width,
                # and reject an oversized sidebar (e.g. stale value from a much
                # wider/differently-scaled window) in favor of the sane default.
                if (saved_pos is not None and
                    saved_pos >= min_content_width and
                    saved_pos <= total_width - min_sidebar_width and
                    total_width - saved_pos <= max_sidebar_width):
                    self._constrain_sidebar_width(saved_pos)
                    log.debug(f"Main sash position restored: {saved_pos}")
                else:
                    # Default: sidebar ~300px wide (scaled with the UI scale)
                    sash_pos = total_width - default_sidebar_width
                    # Ensure minimums
                    sash_pos = max(sash_pos, min_content_width)
                    sash_pos = min(sash_pos, total_width - min_sidebar_width)
                    self._constrain_sidebar_width(sash_pos)
                    log.info(f"Main sash position using default: {sash_pos} (saved_pos={saved_pos})")

                # Mark sash as initialized - now saving is allowed
                self._sash_initialized = True

                # Now set up the sidebar sash after main sash is done
                self.after(100, _set_sidebar_sash)

            except Exception as e:
                log.exception(f"Error setting main sash: {e}")
        
        # Set sidebar sash AFTER main sash is set
        def _set_sidebar_sash(retry_count=0):
            try:
                self.update_idletasks()
                paned_window = self.sidebar_paned
                total_height = paned_window.winfo_height()
                sidebar_width = self._sidebar_frame.winfo_width()
                
                # If height is too small, the sidebar isn't laid out yet - retry
                if total_height < 100 or sidebar_width < 50:
                    if retry_count < 15:
                        self.after(200, lambda: _set_sidebar_sash(retry_count + 1))
                        return
                    else:
                        return
                
                if self.current_theme in ("modern", "modern_slate", "modern_orange"):
                    if self._apply_modern_sidebar_sash():
                        self._sidebar_sash_initialized = True
                        self.after(200, lambda: setattr(self, '_startup_resize_settled', True))
                    return

                # Minimum heights for each pane
                min_presets_height = 150
                min_cargo_height = 120
                
                # Try to restore saved sash position first
                from config import load_sidebar_sash_position
                saved_pos = load_sidebar_sash_position()

                # Saved position is an absolute pixel value laid out under the
                # previous UI scale - rescale it to match a changed window size.
                if saved_pos is not None and self._ui_scale_resize_ratio != 1.0:
                    saved_pos = round(saved_pos * self._ui_scale_resize_ratio)

                # Validate saved position ensures both panes have minimum height
                if (saved_pos is not None and
                    saved_pos >= min_presets_height and
                    saved_pos <= total_height - min_cargo_height):
                    paned_window.sashpos(0, self._sidebar_sash_position(saved_pos))
                    log.debug(f"Sidebar sash position restored: {saved_pos}")
                else:
                    # Default: give 60% to presets, 40% to cargo monitor
                    sash_pos = int(total_height * 0.6)
                    # Ensure minimum heights
                    sash_pos = max(sash_pos, min_presets_height)
                    sash_pos = min(sash_pos, total_height - min_cargo_height)
                    paned_window.sashpos(0, self._sidebar_sash_position(sash_pos))
                    log.info(f"Sidebar sash position using default: {sash_pos} (saved_pos={saved_pos})")

                self._sidebar_sash_initialized = True
                # From here on, treat further resizes as live user drags.
                self.after(200, lambda: setattr(self, '_startup_resize_settled', True))
            except Exception as e:
                log.exception(f"Error setting sidebar sash: {e}")
        
        # Delay to ensure window geometry is fully applied
        self.after(500, _set_initial_sash)
        
        self._main_sash_dragging = False

        def _on_main_sash_pressed(event):
            self._main_sash_dragging = self.main_paned.identify(event.x, event.y) in (0, "0")

        def _on_main_sash_dragged(event):
            if self._main_sash_dragging:
                self._constrain_sidebar_width(event.x)
                return "break"

        self.main_paned.bind("<ButtonPress-1>", _on_main_sash_pressed)
        self.main_paned.bind("<B1-Motion>", _on_main_sash_dragged)

        # Save main sash position when it changes (only after initialization)
        def _on_main_sash_moved(event):
            self._main_sash_dragging = False
            if not getattr(self, '_sash_initialized', False):
                return  # Don't save during initial layout
            try:
                from config import save_main_sash_position
                pos = self._constrain_sidebar_width()
                if pos is not None and pos > 200:  # Only save valid positions
                    save_main_sash_position(pos)
                    log.debug(f"Main sash position saved: {pos}")
            except Exception:
                log.exception("Failed to save main sash position")
        self.main_paned.bind("<ButtonRelease-1>", _on_main_sash_moved)

        # Keep the sidebar pinned to the right during outer-window resize drags.
        # ttk.PanedWindow stores the sash as an absolute pixel offset; while the
        # OS window border is actively being dragged, Tk can transiently clamp
        # that offset near 0 (sidebar appears to jump to the left) and never
        # re-corrects itself once the drag ends. Recompute the sash from the
        # current sidebar width shortly after each resize settles.
        self._resize_sash_job = None

        def _on_root_configure(event):
            if event.widget is not self:
                return
            if not getattr(self, '_sash_initialized', False):
                return
            # Skip the brief window after startup/UI-scale-triggered resize where
            # _set_initial_sash/_set_sidebar_sash already computed the correct
            # scaled sash - this handler is only for live manual window drags.
            if not getattr(self, '_startup_resize_settled', False):
                return
            if self._resize_sash_job is not None:
                self.after_cancel(self._resize_sash_job)
            self._resize_sash_job = self.after(150, _restore_sash_after_resize)

        def _restore_sash_after_resize():
            self._resize_sash_job = None
            try:
                if not self._sidebar_visible:
                    return
                total_width = self.main_paned.winfo_width()
                if total_width < 400:
                    return
                sidebar_width = getattr(self, '_last_sidebar_width', self._scaled_px(300))
                self._constrain_sidebar_width(total_width - sidebar_width)

            except Exception:
                log.exception("Failed to restore sash position after resize")

        self.bind("<Configure>", _on_root_configure)

        # Create vertical paned window for split layout
        paned_window = ttk.PanedWindow(sidebar, orient="vertical")
        paned_window.grid(row=0, column=0, sticky="nsew")
        self.sidebar_paned = paned_window  # Store reference for sash positioning
        
        # Top pane - Presets section
        presets_pane = ttk.Frame(paned_window)
        self._presets_pane = presets_pane
        paned_window.add(presets_pane, weight=5)
        presets_pane.columnconfigure(0, weight=1)
        presets_pane.rowconfigure(2, weight=1)  # Row 2 (preset list) expands
        presets_pane.rowconfigure(3, weight=0)  # Row 3 (buttons) stays at bottom

        # Ship Presets title
        presets_header = ttk.Frame(presets_pane)
        presets_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        presets_title = ttk.Label(presets_header, text=t('sidebar.ship_presets'), font=self._scaled_font(9, "bold"))
        presets_title.pack(side="left")
        presets_info = ttk.Label(presets_header, text="\u24d8", foreground=self.theme_colors['fg_muted'],
                                 cursor="hand2", font=self._scaled_font(10))
        presets_info.pack(side="left", padx=(6, 2))
        ToolTip(presets_info, t('sidebar.right_click_options'))
        self._ship_preset_notice = ttk.Label(presets_header, text="", foreground=self.theme_colors['fg_muted'],
                                             font=self._scaled_font(8))
        self._ship_preset_notice.pack(side="left", padx=(4, 0))

        # Set minimum height for presets pane to prevent collapse
        presets_pane.configure(height=200)
        presets_pane.grid_propagate(True)

        # Configure treeview style for selection highlight (theme-aware)
        style = ttk.Style()

        # Configure Ship Presets treeview font and row height
        if self.current_theme == "elite_orange":
            style.configure("ShipPresets.Treeview",
                           font=self._scaled_font(10),
                           background="#1e1e1e",
                           foreground="#ff8c00",
                           fieldbackground="#1e1e1e",
                           rowheight=self._scaled_px(22))
            style.map("ShipPresets.Treeview",
                     background=[("selected", "#ff8c00")],
                     foreground=[("selected", "#000000")])
        elif self.current_theme in ("modern", "modern_slate", "modern_orange"):
            style.configure("ShipPresets.Treeview",
                           font=self._scaled_font(10),
                           background=modern_color("#1D2228"),
                           foreground=modern_color("#E6EAF0"),
                           fieldbackground=modern_color("#1D2228"),
                           borderwidth=0, bordercolor=modern_color("#1D2228"), lightcolor=modern_color("#1D2228"), darkcolor=modern_color("#1D2228"),
                           rowheight=self._scaled_px(24))
            style.map("ShipPresets.Treeview",
                     background=[("selected", modern_color("#383838"))],
                     foreground=[("selected", "#FFFFFF")])
        else:
            style.configure("ShipPresets.Treeview",
                           font=self._scaled_font(10),
                           background="#1e1e1e",
                           foreground="#e0e0e0",
                           fieldbackground="#1e1e1e",
                           rowheight=self._scaled_px(22))
            style.map("ShipPresets.Treeview",
                     background=[("selected", "#404040")],
                     foreground=[("selected", "#ffffff")])

        # Scrollable preset list - hierarchical treeview with ship groups
        # Modern theme: list sits inside an untitled (rounded) LabelFrame
        _pl_parent, _pl_row = presets_pane, 2
        if self.current_theme in ("modern", "modern_slate", "modern_orange"):
            _pl_parent = ttk.LabelFrame(presets_pane, padding=2)
            _pl_parent.grid(row=2, column=0, columnspan=2, sticky="nsew")
            _pl_parent.columnconfigure(0, weight=1)
            _pl_parent.rowconfigure(0, weight=1)
            _pl_row = 0
        self.preset_list = StripedTreeview(_pl_parent, columns=("name",), show="tree", selectmode="browse", style="ShipPresets.Treeview")
        self.preset_list.column("#0", anchor="w", stretch=True, width=280, minwidth=220)
        self.preset_list.column("name", width=0, stretch=False)  # Hidden column to store full preset name
        self.preset_list.grid(row=_pl_row, column=0, sticky="nsew")
        self.preset_list.bind("<Double-1>", self._on_preset_double_click)
        self.preset_list.bind("<Return>", lambda e: self._load_selected_preset())
        # Save expand/collapse state when user clicks arrow icons (delay to ensure state is updated)
        self.preset_list.bind("<<TreeviewOpen>>", lambda e: self.after(10, self._save_preset_expanded_state))
        self.preset_list.bind("<<TreeviewClose>>", lambda e: self.after(10, self._save_preset_expanded_state))
        # Deselect when clicking empty space
        self.preset_list.bind("<Button-1>", lambda e: self._deselect_on_empty_click(e, self.preset_list))

        # Add scrollbar to preset list
        preset_scrollbar = ttk.Scrollbar(_pl_parent, orient="vertical", command=self.preset_list.yview)
        preset_scrollbar.grid(row=_pl_row, column=1, sticky="ns")
        self.preset_list.configure(yscrollcommand=preset_scrollbar.set)
        presets_pane.columnconfigure(1, weight=0)
        
        # Configure row tags for alternating colors (theme-aware)
        self._configure_preset_list_row_colors()
        
        # Get theme-aware menu colors
        from core.constants import get_menu_colors
        menu_colors = get_menu_colors(self.current_theme)
        
        # Context menu with theme-aware colors (for presets)
        self._preset_menu = tk.Menu(self, tearoff=0, 
                                  bg=menu_colors["bg"], fg=menu_colors["fg"], 
                                  activebackground=menu_colors["activebackground"], 
                                  activeforeground=menu_colors["activeforeground"],
                                  selectcolor=menu_colors["selectcolor"])
        self._preset_menu.add_command(label=t('context_menu.save_as_new'), command=self._save_as_new)
        self._preset_menu.add_command(label=t('context_menu.overwrite'), command=self._overwrite_selected)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label=t('context_menu.edit'), command=self._edit_selected_preset)
        self._preset_menu.add_command(label=t('context_menu.duplicate'), command=self._duplicate_selected_preset)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label=t('context_menu.export'), command=self._export_selected_preset)
        self._preset_menu.add_command(label=t('context_menu.import'), command=self._import_preset_file)
        self._preset_menu.add_command(label=t('reports.open_folder'), command=self._open_ship_presets_folder)
        self._preset_menu.add_separator()
        self._ann_preset_submenu = tk.Menu(self._preset_menu, tearoff=0,
                                  bg=menu_colors["bg"], fg=menu_colors["fg"],
                                  activebackground=menu_colors["activebackground"],
                                  activeforeground=menu_colors["activeforeground"],
                                  selectcolor=menu_colors["selectcolor"])
        self._preset_menu.add_cascade(label=t('context_menu.announcement_preset') + "  ▸", menu=self._ann_preset_submenu)
        self._ann_preset_menu_var = tk.IntVar(value=0)
        self._ship_auto_load_var = tk.BooleanVar(value=False)
        self._preset_menu.add_checkbutton(
            label=t('context_menu.auto_load_ship_preset'),
            variable=self._ship_auto_load_var,
            command=self._toggle_ship_preset_auto_load)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label=t('context_menu.expand_all'), command=self._expand_all_preset_groups)
        self._preset_menu.add_command(label=t('context_menu.collapse_all'), command=self._collapse_all_preset_groups)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label=t('context_menu.delete'), command=self._delete_selected)
        
        # Context menu for empty space (limited options)
        self._preset_empty_menu = tk.Menu(self, tearoff=0, 
                                  bg=menu_colors["bg"], fg=menu_colors["fg"], 
                                  activebackground=menu_colors["activebackground"], 
                                  activeforeground=menu_colors["activeforeground"],
                                  selectcolor=menu_colors["selectcolor"])
        self._preset_empty_menu.add_command(label=t('context_menu.save_as_new'), command=self._save_as_new)
        self._preset_empty_menu.add_command(label=t('context_menu.import'), command=self._import_preset_file)
        self._preset_empty_menu.add_command(label=t('reports.open_folder'), command=self._open_ship_presets_folder)
        self._preset_empty_menu.add_separator()
        self._preset_empty_menu.add_command(label=t('context_menu.expand_all'), command=self._expand_all_preset_groups)
        self._preset_empty_menu.add_command(label=t('context_menu.collapse_all'), command=self._collapse_all_preset_groups)
        
        self.preset_list.bind("<Button-3>", self._show_preset_menu)

        # Bottom pane - Cargo Monitor
        cargo_pane = ttk.Frame(paned_window)
        self._cargo_pane = cargo_pane
        from config import load_sidebar_cargo_on_top
        self._sidebar_default_cargo_on_top = self.current_theme in ("modern", "modern_slate", "modern_orange")
        self._sidebar_cargo_on_top = load_sidebar_cargo_on_top(self._sidebar_default_cargo_on_top)
        if self._sidebar_cargo_on_top:
            paned_window.insert(0, cargo_pane, weight=0)
        else:
            paned_window.add(cargo_pane, weight=1)
        
        # Configure cargo pane - allow vertical expansion
        cargo_pane.columnconfigure(0, weight=1)
        cargo_pane.rowconfigure(0, weight=1)  # Allow row to expand
        
        self._create_integrated_cargo_monitor(cargo_pane)

        # Theme toggle button below cargo monitor (styled to match current theme)
        theme_btn_frame = ttk.Frame(self._actions_frame)
        theme_btn_frame.grid(row=0, column=2, sticky="e")

        # Get theme-appropriate colors (subtle styling)
        if self.current_theme == "elite_orange":
            _tbtn_bg, _tbtn_fg = "#2a2a2a", "#d4a020"  # Darker bg, muted yellow-orange text
            _tbtn_active_bg, _tbtn_active_fg = "#3a3a3a", "#ffcc00"
        else:
            _tbtn_bg, _tbtn_fg = "#252525", "#999999"  # Darker bg, muted gray text
            _tbtn_active_bg, _tbtn_active_fg = "#353535", "#cccccc"

        self.theme_toggle_btn = tk.Button(
            theme_btn_frame,
            text=self._theme_btn_config["text"],
            command=lambda: self._show_theme_menu(self.theme_toggle_btn),
            bg=_tbtn_bg,
            fg=_tbtn_fg,
            activebackground=_tbtn_active_bg,
            activeforeground=_tbtn_active_fg,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            font=self._scaled_font(8),
            cursor="hand2"
        )
        self.theme_toggle_btn.pack(side="left")

        self.sidebar_toggle_btn = tk.Button(
            theme_btn_frame,
            text=t('sidebar.sidebar_btn'),
            command=self._show_sidebar_menu,
            bg=_tbtn_bg,
            fg=_tbtn_fg,
            activebackground=_tbtn_active_bg,
            activeforeground=_tbtn_active_fg,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            font=self._scaled_font(8),
            cursor="hand2"
        )
        self.sidebar_toggle_btn.pack(side="left", before=self.theme_toggle_btn, padx=(0, 6))

        # Language flag buttons (next to theme button)
        self._create_language_flags(theme_btn_frame)

        # Version button (opens About dialog)
        self._create_version_button(theme_btn_frame)

        # Refresh the preset list
        self._refresh_preset_list()

        # Restore active ship preset from config, if its file still exists
        try:
            from config import load_active_ship_preset
            active_name = load_active_ship_preset()
            if active_name and os.path.exists(self._settings_path(active_name)):
                self._load_ship_preset(active_name)
        except Exception:
            pass

        # Save sidebar sash position when it changes (only after initialization)
        def _on_sidebar_sash_moved(event):
            if not getattr(self, '_sidebar_sash_initialized', False):
                return  # Don't save during initial layout
            if self.current_theme in ("modern", "modern_slate", "modern_orange"):
                self._save_modern_sidebar_sash()  # Cargo is the top pane here; separate saved value
                return
            try:
                from config import save_sidebar_sash_position
                pos = self._sidebar_sash_position(paned_window.sashpos(0))
                if pos > 100:  # Only save valid positions
                    save_sidebar_sash_position(pos)
                    log.debug(f"Sidebar sash position saved: {pos}")
            except Exception:
                log.exception("Failed to save sidebar sash position")
        paned_window.bind("<ButtonRelease-1>", _on_sidebar_sash_moved)

    def _apply_modern_sidebar_sash(self) -> bool:
        """Modern theme: Cargo is the top pane. Restore its saved height (own config key, rescaled like the
        classic one after a UI Scale change), else use its natural height; the rest goes to Ship Presets.
        Returns False if the sidebar isn't laid out yet."""
        paned = self.sidebar_paned
        paned.update_idletasks()
        total_height = paned.winfo_height()
        if total_height < 100:
            return False
        min_cargo = self._scaled_px(80)
        max_cargo = total_height - self._scaled_px(150)
        from config import load_modern_sidebar_sash_position
        saved_pos = load_modern_sidebar_sash_position()
        if saved_pos is not None and self._ui_scale_resize_ratio != 1.0:
            saved_pos = round(saved_pos * self._ui_scale_resize_ratio)
        if saved_pos is not None and min_cargo <= saved_pos <= max_cargo:
            pos = saved_pos
            log.debug(f"Modern sidebar sash restored: {pos}")
        else:
            pos = min(max(self._cargo_pane.winfo_reqheight(), self._scaled_px(120)), max_cargo)
            log.info(f"Modern sidebar sash using natural height: {pos} (saved_pos={saved_pos})")
        paned.sashpos(0, self._sidebar_sash_position(pos))
        return True

    def _save_modern_sidebar_sash(self) -> None:
        """Persist the Modern sidebar's Cargo pane height (only sane values, only after initial layout)."""
        try:
            if not getattr(self, '_sidebar_sash_initialized', False) or not hasattr(self, 'sidebar_paned'):
                return
            paned = self.sidebar_paned
            total_height = paned.winfo_height()
            pos = self._sidebar_sash_position(paned.sashpos(0))
            if total_height >= 100 and self._scaled_px(80) <= pos <= total_height - self._scaled_px(150):
                from config import save_modern_sidebar_sash_position
                save_modern_sidebar_sash_position(pos)
                log.debug(f"Modern sidebar sash position saved: {pos}")
        except Exception:
            log.exception("Failed to save Modern sidebar sash position")

    def _save_sash_positions_now(self) -> None:
        """Force-save current sash positions, bypassing the ButtonRelease-1 trigger.
        Used as a shutdown safety net so a resize just before close isn't lost."""
        try:
            if getattr(self, '_sash_initialized', False) and hasattr(self, 'main_paned'):
                from config import save_main_sash_position
                pos = self._constrain_sidebar_width()
                if pos is not None and pos > 200:
                    save_main_sash_position(pos)
                    log.info(f"Main sash position saved on close: {pos}")
        except Exception:
            log.exception("Failed to save main sash position on close")

        try:
            if self.current_theme in ("modern", "modern_slate", "modern_orange"):
                self._save_modern_sidebar_sash()
            elif getattr(self, '_sidebar_sash_initialized', False) and hasattr(self, 'sidebar_paned'):
                from config import save_sidebar_sash_position
                pos = self._sidebar_sash_position(self.sidebar_paned.sashpos(0))
                if pos > 100:
                    save_sidebar_sash_position(pos)
                    log.info(f"Sidebar sash position saved on close: {pos}")
        except Exception:
            log.exception("Failed to save sidebar sash position on close")

    def _reinitialize_sash_positions(self):
        """Re-apply saved sash positions after window geometry is fully restored.
        Called after splash screen dismissal when the initial sash setup may have
        timed out due to the window being withdrawn."""
        try:
            self.update_idletasks()
            # --- Main horizontal sash (content | sidebar) ---
            total_width = self.winfo_width()
            if total_width > 400 and hasattr(self, 'main_paned'):
                from config import load_main_sash_position
                saved_pos = load_main_sash_position()
                if saved_pos is not None and self._ui_scale_resize_ratio != 1.0:
                    saved_pos = round(saved_pos * self._ui_scale_resize_ratio)
                from config import load_ui_scale
                min_content_width = 600
                min_sidebar_width = self._scaled_px(280)
                max_sidebar_width = round(500 * load_ui_scale())
                if (saved_pos is not None and
                    saved_pos >= min_content_width and
                    saved_pos <= total_width - min_sidebar_width and
                    total_width - saved_pos <= max_sidebar_width):
                    self._constrain_sidebar_width(saved_pos)
                    log.debug(f"Main sash position re-applied: {saved_pos}")
                self._constrain_sidebar_width()
                self._sash_initialized = True

            # --- Sidebar vertical sash (presets | cargo) ---
            if hasattr(self, 'sidebar_paned') and self.current_theme in ("modern", "modern_slate", "modern_orange"):
                if self._apply_modern_sidebar_sash():
                    self._sidebar_sash_initialized = True
            elif hasattr(self, 'sidebar_paned'):
                paned = self.sidebar_paned
                total_height = paned.winfo_height()
                if total_height > 100:
                    from config import load_sidebar_sash_position
                    saved_pos = load_sidebar_sash_position()
                    if saved_pos is not None and self._ui_scale_resize_ratio != 1.0:
                        saved_pos = round(saved_pos * self._ui_scale_resize_ratio)
                    min_presets_height = 150
                    min_cargo_height = 120
                    if (saved_pos is not None and
                        saved_pos >= min_presets_height and
                        saved_pos <= total_height - min_cargo_height):
                        paned.sashpos(0, self._sidebar_sash_position(saved_pos))
                        log.debug(f"Sidebar sash position re-applied: {saved_pos}")
                    self._sidebar_sash_initialized = True

        except Exception as e:
            log.exception(f"Error reinitializing sash positions: {e}")
        
    def _refresh_voice_list(self):
        """Refresh the TTS voice dropdown list"""
        try:
            if hasattr(self, 'voice_combo'):
                voice_values = announcer.list_voices()
                self.voice_combo['values'] = voice_values
                
                # Set saved voice or default
                cfg = _load_cfg()
                saved_voice = cfg.get("tts_voice")
                if saved_voice and saved_voice in voice_values:
                    self.voice_choice.set(saved_voice)
                    # Apply the saved voice to announcer
                    try:
                        announcer.set_voice(saved_voice)
                    except Exception:
                        log.exception("Could not apply saved voice")
                elif voice_values and not self.voice_choice.get():
                    self.voice_choice.set(voice_values[0])
                    
        except Exception:
            log.exception("Voice list refresh failed")

    def _update_pulsewave_dependency(self, reset_value=True):
        """Enable/disable Continuous Pulsewave based on Pulse Wave Analyser state"""
        try:
            if "Pulse Wave Analyser" not in self.toggle_vars or "Continuous Pulsewave" not in self.toggle_checkboxes:
                return
            pwa_enabled = self.toggle_vars["Pulse Wave Analyser"].get() == 1
            cp_checkbox = self.toggle_checkboxes["Continuous Pulsewave"]
            if pwa_enabled:
                cp_checkbox.configure(state="normal")
            else:
                cp_checkbox.configure(state="disabled")
                if reset_value:
                    self.toggle_vars["Continuous Pulsewave"].set(0)
        except Exception as e:
            log.error(f"Error updating pulsewave dependency: {e}")

    def _update_fsdjump_dependencies(self):
        """Enable/disable Open System Map and its timers based on FSD Jump Sequence / Open System Map state"""
        try:
            if "FSD Jump Sequence" not in self.toggle_vars or "Open System Map" not in self.toggle_checkboxes:
                return
            master_enabled = self.toggle_vars["FSD Jump Sequence"].get() == 1
            checkbox = self.toggle_checkboxes["Open System Map"]
            checkbox.configure(state="normal" if master_enabled else "disabled")

            osm_enabled = master_enabled and self.toggle_vars["Open System Map"].get() == 1
            spinboxes = getattr(self, "fsdjump_timer_spinboxes", {})
            if "FSD System Map Timer" in spinboxes:
                spinboxes["FSD System Map Timer"].configure(state="normal" if osm_enabled else "disabled")
            if "FSD Jump Pause Timer" in spinboxes:
                pause_enabled = master_enabled and not osm_enabled
                spinboxes["FSD Jump Pause Timer"].configure(state="normal" if pause_enabled else "disabled")
        except Exception as e:
            log.error(f"Error updating FSD jump dependency: {e}")

    _DECIMAL_TIMERS = {"Continuous Prospector Sequence Timer"}

    def _update_prospector_dependencies(self):
        """Enable/disable dependent toggles based on Prospector Sequence state"""
        try:
            if "Prospector Sequence" not in self.toggle_vars or "Prospector Sequence" not in self.toggle_checkboxes:
                return
            
            # Get master toggle state
            master_enabled = self.toggle_vars["Prospector Sequence"].get() == 1
            
            # Update dependent checkboxes
            for dependent in ["Prospector Sound Effect", "Thrust Up", "Continuous Prospector Sequence"]:
                if dependent in self.toggle_checkboxes:
                    checkbox = self.toggle_checkboxes[dependent]
                    if master_enabled:
                        checkbox.configure(state="normal")
                    else:
                        checkbox.configure(state="disabled")
                        # NOTE: Don't uncheck/reset values - preserve user's setting
                        # They just can't be changed while Prospector Sequence is off

            if hasattr(self, 'cpst_spinbox') and hasattr(self, 'prospector_cooldown_spinbox'):
                cont_on = master_enabled and self.toggle_vars.get("Continuous Prospector Sequence") is not None \
                    and self.toggle_vars["Continuous Prospector Sequence"].get() == 1
                self.cpst_spinbox.configure(state="normal" if cont_on else "disabled")
                self.cpst_label.configure(fg=self._cpst_fg if cont_on else "#666666")
                self.prospector_cooldown_spinbox.configure(state="normal" if master_enabled else "disabled")
                self.prospector_cooldown_label.configure(fg=self._cpst_fg if master_enabled else "#666666")
        except Exception as e:
            log.error(f"Error updating prospector dependencies: {e}")

    # ---------- Status helper ----------
    def _set_status(self, msg: str, clear_after: int = 8000) -> None:
        """Routine confirmations are logged only; useful feedback is shown next to its own controls."""
        log.info("[Status] %s", msg)

    def _set_journal_scan_status(self, msg: str, clear_after: int = 5000) -> None:
        self._show_notice(getattr(self, '_journal_scan_label', None), msg, clear_after)

    def _ship_preset_done(self, key: str) -> None:
        self._show_notice(getattr(self, '_ship_preset_notice', None), t('sidebar.preset_' + key))

    def _show_notice(self, label, msg: str, clear_after: int = 6000, fg=None) -> None:
        """Show a short transient message in an inline label, then clear it."""
        try:
            if not label.winfo_exists():
                return
            kw = {'text': msg}
            if fg:
                kw['fg'] = fg
            label.config(**kw)
            token = object()
            label._notice_token = token
            if clear_after:
                def _clear():
                    try:
                        if label.winfo_exists() and getattr(label, '_notice_token', None) is token:
                            label.config(text="")
                    except Exception:
                        pass
                self.after(clear_after, _clear)
        except Exception:
            pass

    # ---------- TXT Read/Write ----------
    def _index_vars_dir(self) -> Dict[str, str]:
        idx: Dict[str, str] = {}
        try:
            for fn in os.listdir(self.vars_dir):
                if fn.lower().endswith(".txt"):
                    idx[fn.lower()] = os.path.join(self.vars_dir, fn)
        except Exception:
            pass
        return idx

    def _read_var_text(self, base_without_txt: str) -> Optional[str]:
        idx = self._index_vars_dir()
        key = (base_without_txt + ".txt").lower()
        path = idx.get(key)
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception:
                return None
        return None

    def _write_var_text(self, base_without_txt: str, text: str) -> None:
        idx = self._index_vars_dir()
        key = (base_without_txt + ".txt").lower()
        path = idx.get(key, os.path.join(self.vars_dir, base_without_txt + ".txt"))
        _atomic_write_text(path, text)
    
    def _write_jumps_left(self, jumps: int) -> None:
        """Write jumpsleft.txt - wrapper for VA variables"""
        try:
            if hasattr(self, 'va_variables') and self.va_variables:
                self.va_variables.update_jumps_left(jumps)
            else:
                # Fallback: write directly to file
                jumps_file = os.path.join(self.vars_dir, "jumpsleft.txt")
                _atomic_write_text(jumps_file, str(jumps))
        except Exception as e:
            log.error(f"[ROUTE] Error writing jumpsleft: {e}")
    
    def _save_laser_extra_repeat(self) -> None:
        """Save laser mining extra repeat count to txt file"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            count = self.laser_extra_repeat_var.get()
            txt_path = os.path.join(self.vars_dir, "laserminingextra_count.txt")
            print(f"[SAVE DEBUG] Writing laser_extra to: {txt_path}")
            _atomic_write_text(txt_path, str(count))
            
            # Update status label
            times_text = t('voiceattack.time') if count == 1 else t('voiceattack.times')
            self.laser_extra_status_label.config(text=f"({t('voiceattack.will_run')} {count} {times_text})")

            print(f"[LASER EXTRA] Saved repeat count: {count}")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[LASER EXTRA] Error saving repeat count: {e}")
    
    def _save_prospector_delay(self) -> None:
        """Save prospector delay to delayprospector.txt"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            delay = self.prospector_delay_var.get()
            txt_path = os.path.join(self.vars_dir, "delayprospector.txt")
            # Always use period (.) as decimal separator for VoiceAttack compatibility
            delay_str = f"{delay:.1f}".replace(',', '.')
            _atomic_write_text(txt_path, delay_str)

            print(f"[PROSPECTOR DELAY] Saved delay: {delay_str} seconds")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[PROSPECTOR DELAY] Error saving delay: {e}")
    
    def _list_sound_events(self) -> dict:
        """{event: ["British Female", ...]} from Sound_Packs/<pack>/<pack>_<voice>/*.wav; fills self._sound_label_map"""
        root = os.path.join(get_app_data_dir(), "Sound_Packs")
        events = {}
        self._sound_label_map = {}
        try:
            for pack in sorted(os.listdir(root)):
                for voice in ("Female", "Male"):
                    folder = os.path.join(root, pack, f"{pack}_{voice}")
                    if not os.path.isdir(folder):
                        continue
                    for f in os.listdir(folder):
                        if f.lower().endswith(".wav"):
                            label = f"{pack.replace('_', ' ')} {voice}"
                            self._sound_label_map[label] = (pack, voice)
                            events.setdefault(os.path.splitext(f)[0], []).append(label)
        except OSError:
            pass
        return dict(sorted(events.items()))

    def _write_sound_event_paths(self) -> None:
        """Write soundPath_<event> (full wav path, "none" when Off or the file is missing)"""
        root = os.path.join(get_app_data_dir(), "Sound_Packs")
        for event, var in self.sound_event_vars.items():
            path = "none"
            if var.get() == t('voiceattack.sound_event_tts'):
                path = "tts"
            elif var.get() in self._sound_label_map:
                pack, voice = self._sound_label_map[var.get()]
                candidate = os.path.join(root, pack, f"{pack}_{voice}", f"{event}.wav")
                if os.path.isfile(candidate):
                    path = candidate
            self._write_var_text(f"soundPath_{event}", path)

    def _test_sound_event(self, event: str) -> None:
        """Play/speak the current choice for an event using the volume/balance sliders"""
        announcer.stop()
        if self.sound_event_vars[event].get() == t('voiceattack.sound_event_tts'):
            self._speak_sound_event(event)
            return
        pack, voice = self._sound_label_map.get(self.sound_event_vars[event].get(), ("", ""))
        path = os.path.join(get_app_data_dir(), "Sound_Packs", pack, f"{pack}_{voice}", f"{event}.wav")
        if os.path.isfile(path):
            self._play_wav_scaled(path, self.sound_volume.get() * self._WAV_VOLUME_FACTOR, self.sound_balance.get())

    @staticmethod
    def _play_wav_scaled(path: str, volume: int, balance: int) -> None:
        """Play a wav with volume (0-100) and balance (-100..100) applied, like VoiceAttack does"""
        import wave, array, io, threading, winsound
        try:
            with wave.open(path, "rb") as w:
                channels, width, rate = w.getnchannels(), w.getsampwidth(), w.getframerate()
                frames = w.readframes(w.getnframes())
            if width != 2 or channels not in (1, 2):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
            samples = array.array("h")
            samples.frombytes(frames)
            if channels == 1:
                samples = array.array("h", [x for s in samples for x in (s, s)])
            vol, bal = volume / 100.0, balance / 100.0
            gains = (vol * (1 - max(0.0, bal)), vol * (1 - max(0.0, -bal)))
            scaled = array.array("h", (int(s * gains[i & 1]) for i, s in enumerate(samples)))
            buf = io.BytesIO()
            with wave.open(buf, "wb") as out:
                out.setnchannels(2)
                out.setsampwidth(2)
                out.setframerate(rate)
                out.writeframes(scaled.tobytes())
            threading.Thread(target=winsound.PlaySound, args=(buf.getvalue(), winsound.SND_MEMORY), daemon=True).start()
        except Exception as e:
            print(f"[SOUND TEST] {e}")

    def _speak_sound_event(self, event: str) -> None:
        announcer.say(self.sound_event_names[event], self.sound_event_tts_vars[event].get() or None,
                      self.sound_volume.get())

    def _poll_sound_trigger(self) -> None:
        """VoiceAttack writes the event name to soundTrigger.txt for events set to TTS"""
        try:
            path = os.path.join(get_variables_dir(), "soundTrigger.txt")
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8") as f:
                    event = f.read().strip()
                if event:
                    self._write_var_text("soundTrigger", "")
                    if event in self.sound_event_tts_vars and self.sound_event_vars[event].get() == t('voiceattack.sound_event_tts'):
                        self._speak_sound_event(event)
        except Exception as e:
            print(f"[SOUND TRIGGER] {e}")
        self.after(300, self._poll_sound_trigger)

    def _sync_voice_feedback_enabled(self) -> None:
        """Grey out the volume, balance and sound event controls while Voice Feedback is off"""
        enabled = bool(self.toggle_vars["Voice Feedback"].get())
        for widget, on_state in self._vf_controls:
            widget.configure(state=on_state if enabled else "disabled")
        for sync in self._vf_tts_syncs:
            sync()

    def _on_voice_set_toggle(self, category: str, label: str) -> None:
        """Voice set checkboxes are exclusive per section; none ticked = custom per-event choices"""
        from config import update_config_value
        active = label if self._voice_set_vars[(category, label)].get() else ""
        if active:
            self._voice_set_active[category] = active
        else:
            self._voice_set_active.pop(category, None)
        for (cat, other), sv in self._voice_set_vars.items():
            if cat == category:
                sv.set(other == active)
        update_config_value("sound_voice_sets", dict(self._voice_set_active))
        off_label = t('voiceattack.sound_event_off')
        tts_label = t('voiceattack.sound_event_tts')
        custom = _load_cfg().get("sound_events", {})
        self._updating_sound_events = True
        try:
            for event, var in self.sound_event_vars.items():
                if SOUND_EVENT_CATEGORIES.get(event, "other") != category:
                    continue
                packs = self._sound_event_packs[event]
                if active:
                    value = active if active in packs or active == tts_label else off_label
                else:
                    saved = custom.get(event)
                    value = off_label if saved == "" else tts_label if saved == "tts" else saved if saved in packs else packs[0]
                var.set(value)
        finally:
            self._updating_sound_events = False
        self._save_sound_events()

    def _clear_voice_set(self, category: str) -> None:
        """Editing a dropdown makes the section custom: untick its voice set and keep the rows as they are"""
        if category not in self._voice_set_active:
            return
        from config import update_config_value
        del self._voice_set_active[category]
        for (cat, _label), sv in self._voice_set_vars.items():
            if cat == category:
                sv.set(False)
        update_config_value("sound_voice_sets", dict(self._voice_set_active))
        self._save_sound_events()

    def _reset_sound_events(self, category: str = None) -> None:
        """Reset a section (or all) to the default voice for every event and untick its voice set"""
        if not centered_yesno_dialog(self, t('voiceattack.sound_reset_title'),
                                     t('voiceattack.sound_reset_confirm')):
            return
        from config import update_config_value
        default_tts = _load_cfg().get("tts_voice") or ""
        self._updating_sound_events = True
        try:
            for event, var in self.sound_event_vars.items():
                if category and SOUND_EVENT_CATEGORIES.get(event, "other") != category:
                    continue
                packs = self._sound_event_packs[event]
                var.set(next((p for p in packs if p.endswith(" Female")), packs[0]))
                if default_tts:
                    self.sound_event_tts_vars[event].set(default_tts)
        finally:
            self._updating_sound_events = False
        for cat in ([category] if category else list(self._voice_set_active)):
            self._voice_set_active.pop(cat, None)
        for (cat, _label), sv in self._voice_set_vars.items():
            if not category or cat == category:
                sv.set(False)
        update_config_value("sound_voice_sets", dict(self._voice_set_active))
        self._save_sound_events()

    def _save_sound_events(self) -> None:
        """Persist per-event choice ("" = Off, "tts", or "<pack> <voice>") and TTS voice, and write the path variables"""
        if getattr(self, '_updating_sound_events', False):
            return
        from config import update_config_values
        off_label = t('voiceattack.sound_event_off')
        tts_label = t('voiceattack.sound_event_tts')
        active = getattr(self, '_voice_set_active', {})
        existing = _load_cfg().get("sound_events", {})
        events = {}
        for e, v in self.sound_event_vars.items():
            if SOUND_EVENT_CATEGORIES.get(e, "other") in active:
                if e in existing:
                    events[e] = existing[e]
            else:
                events[e] = "" if v.get() == off_label else "tts" if v.get() == tts_label else v.get()
        update_config_values({
            "sound_events": events,
            "sound_event_tts": {e: vv.get() for e, vv in self.sound_event_tts_vars.items()},
        })
        self._write_sound_event_paths()

    _SOUND_LEVEL_FILES = {"sound_volume": "soundVolume", "sound_balance": "soundBalance"}
    _WAV_VOLUME_FACTOR = 0.5  # recorded sounds play slightly lower so TTS (capped at 100) matches them
    _VOICE_CONFIG_KEYS = {"Voice Feedback": "voice_feedback"}

    def _write_sound_levels(self) -> None:
        """Write sound volume (0-100) and balance (-100..100) for VoiceAttack's Variable volume/balance"""
        from config import update_config_values
        levels = {}
        for var_name, fname in self._SOUND_LEVEL_FILES.items():
            var = getattr(self, var_name, None)
            if var is not None:
                out = round(var.get() * self._WAV_VOLUME_FACTOR) if var_name == "sound_volume" else var.get()
                self._write_var_text(fname, str(out))
                levels[var_name] = var.get()
        if levels:
            update_config_values(levels)

    def _save_toggle(self, toggle_name: str) -> None:
        """Save a toggle to file immediately on change"""
        if toggle_name in self._VOICE_CONFIG_KEYS:
            from config import update_config_value
            update_config_value(self._VOICE_CONFIG_KEYS[toggle_name], self.toggle_vars[toggle_name].get())
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            if toggle_name not in TOGGLES:
                return
            fname, _help = TOGGLES[toggle_name]
            base = os.path.splitext(fname)[0]
            
            if toggle_name == "Auto Honk":
                val = "enabled" if self.toggle_vars[toggle_name].get() else "disabled"
                self._write_var_text(base, val)
            elif toggle_name == "Headtracker Docking Control":
                self._write_var_text(base, "1" if self.toggle_vars[toggle_name].get() else "0")
            else:
                self._write_var_text(base, str(self.toggle_vars[toggle_name].get()))
            
            print(f"[TOGGLE] Auto-saved {toggle_name}: {self.toggle_vars[toggle_name].get()}")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[TOGGLE] Error auto-saving {toggle_name}: {e}")
    
    def _save_firegroup(self, tool: str) -> None:
        """Save a firegroup assignment to file immediately on change"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            cfg = VA_VARS.get(tool)
            if not cfg or cfg["fg"] is None:
                return
            
            fg_name = cfg["fg"]
            letter = self.tool_fg[tool].get()
            if letter:
                self._write_var_text(fg_name, NATO.get(letter, letter))
                print(f"[FIREGROUP] Auto-saved {tool}: {letter}")
                self._ship_check_modified()
        except Exception as e:
            log.error(f"[FIREGROUP] Error auto-saving {tool}: {e}")
    
    def _save_fire_button(self, tool: str) -> None:
        """Save a fire button assignment to file immediately on change"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            cfg = VA_VARS.get(tool)
            if not cfg or cfg["btn"] is None:
                return
            
            btn_name = cfg["btn"]
            v = self.tool_btn[tool].get()
            if v in (1, 2):
                self._write_var_text(btn_name, "primary" if v == 1 else "secondary")
                print(f"[FIRE BUTTON] Auto-saved {tool}: {'primary' if v == 1 else 'secondary'}")
                self._ship_check_modified()
        except Exception as e:
            log.error(f"[FIRE BUTTON] Error auto-saving {tool}: {e}")
    
    def _make_stepper(self, parent, lo, hi, variable, bg, fg, increment=1, command=None):
        """Themed number stepper used for the VoiceAttack Controls timers"""
        return Stepper(parent, lo, hi, variable, increment=increment, command=command, bg=bg, fg=fg,
                       font=self._scaled_font(9), scale=self._scaled_px(100) / 100,
                       accent=slider_colors(self.current_theme)["accent"])

    def _save_timer(self, timer_name: str, filename: str, lo: int, hi: int) -> None:
        """Save any timer to file immediately on change"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            delay = self.timer_vars[timer_name].get()
            if timer_name in self._DECIMAL_TIMERS:
                delay = round(delay, 1)
            # Clamp to valid range
            delay = max(lo, min(hi, delay))
            self.timer_vars[timer_name].set(delay)

            # Write to file
            base = os.path.splitext(filename)[0]
            self._write_var_text(base, str(delay))
            print(f"[TIMER] Auto-saved {timer_name}: {delay} seconds")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[TIMER] Error auto-saving {timer_name}: {e}")
    
    def _save_thrust_upduration(self) -> None:
        """Save thrust key hold duration to thrustUpduration.txt"""
        if getattr(self, '_importing', False):
            return
        try:
            delay = self.thrust_upduration_var.get()
            txt_path = os.path.join(self.vars_dir, "thrustUpduration.txt")
            delay_str = f"{delay:.1f}".replace(',', '.')
            _atomic_write_text(txt_path, delay_str)
            print(f"[THRUST UPDURATION] Saved: {delay_str} seconds")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[THRUST UPDURATION] Error saving: {e}")

    def _save_thrust_closed(self) -> None:
        """Save thrust closed timing to thrustScoopClosed.txt"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            delay = self.thrust_closed_var.get()
            txt_path = os.path.join(self.vars_dir, "thrustScoopClosed.txt")
            # Always use period (.) as decimal separator for VoiceAttack compatibility
            delay_str = f"{delay:.1f}".replace(',', '.')
            _atomic_write_text(txt_path, delay_str)
            print(f"[THRUST CLOSED] Saved timing: {delay_str} seconds")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[THRUST CLOSED] Error saving timing: {e}")
    
    def _save_thrust_open(self) -> None:
        """Save thrust open timing to thrustScoopOpen.txt"""
        # Skip save during import to prevent feedback loop
        if getattr(self, '_importing', False):
            return
        try:
            delay = self.thrust_open_var.get()
            txt_path = os.path.join(self.vars_dir, "thrustScoopOpen.txt")
            # Always use period (.) as decimal separator for VoiceAttack compatibility
            delay_str = f"{delay:.1f}".replace(',', '.')
            _atomic_write_text(txt_path, delay_str)
            print(f"[THRUST OPEN] Saved timing: {delay_str} seconds")
            self._ship_check_modified()
        except Exception as e:
            log.error(f"[THRUST OPEN] Error saving timing: {e}")
    
    def _initialize_va_variables(self) -> None:
        """Initialize VoiceAttack variables manager"""
        try:
            from va_variables import VAVariablesManager
            journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
            self.va_variables = VAVariablesManager(self.vars_dir, journal_dir)
            self.va_variables.initialize_jumps_left()
            print("✅ Initialized VoiceAttack variables (jumpsleft.txt)")
            
            # Start polling for route status (CMDR/system display updates)
            self.after(2000, self._poll_route_status)
        except Exception as e:
            log.error(f"Error initializing VA variables: {e}")
    
    def _latest_journal_for_route(self, journal_dir: str):
        # CargoMonitor already tracks the newest journal; list the folder only when it can't help
        monitor = getattr(self, 'cargo_monitor', None)
        current = getattr(monitor, 'last_journal_file', None)
        if current and os.path.exists(current) and                 os.path.normcase(os.path.abspath(os.path.dirname(current))) == os.path.normcase(os.path.abspath(journal_dir)):
            return current
        journal_files = [f for f in os.listdir(journal_dir) if f.startswith('Journal.') and f.endswith('.log')]
        return os.path.join(journal_dir, max(journal_files)) if journal_files else None

    def _poll_route_status(self) -> None:
        """Poll journal and NavRoute for changes (runs every 2 seconds)"""
        try:
            journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
            if not journal_dir or not os.path.exists(journal_dir):
                self.after(2000, self._poll_route_status)
                return
            
            route_changed = False
            navroute_file_changed = False
            
            # Check NavRoute.json for changes (modification time)
            navroute_path = os.path.join(journal_dir, "NavRoute.json")
            
            if os.path.exists(navroute_path):
                try:
                    mtime = os.path.getmtime(navroute_path)
                    cached_mtime = getattr(self, '_navroute_mtime', 0)
                    
                    if mtime != cached_mtime:
                        self._navroute_mtime = mtime
                        navroute_file_changed = True
                except Exception as e:
                    log.error(f"[ROUTE] Error checking NavRoute: {e}")
                if navroute_file_changed:
                    try:
                        with open(navroute_path, 'r', encoding='utf-8') as nf:
                            if not json.load(nf).get('Route', []):
                                if getattr(self, '_cached_route_jumps', None) != 0:
                                    self._cached_route_jumps = 0
                                    self._write_jumps_left(0)
                                    route_changed = True
                    except Exception:
                        pass
            
            # Always scan journal for FSDTarget (authoritative source)
            if True:
                # Check latest journal for FSDTarget
                latest_journal = self._latest_journal_for_route(journal_dir)
                if latest_journal:
                    try:
                        with open(latest_journal, 'r', encoding='utf-8') as f:
                            f.seek(0, 2)
                            file_size = f.tell()
                            f.seek(max(0, file_size - 5120))  # Last 5KB
                            lines = f.readlines()
                            
                            # Scan backwards for latest route-related event
                            for line in reversed(lines):
                                if not line.strip():
                                    continue
                                try:
                                    event = json.loads(line)
                                    event_type = event.get('event')
                                    
                                    # Priority order: FSDTarget > NavRoute > FSDJump > NavRouteClear
                                    if event_type == 'FSDTarget':
                                        jumps = event.get('RemainingJumpsInRoute')
                                        if jumps is not None:
                                            # Check if we've arrived at final destination
                                            # If current system matches last system in route, set jumps to 0
                                            if jumps > 0 and os.path.exists(navroute_path):
                                                try:
                                                    with open(navroute_path, 'r', encoding='utf-8') as nf:
                                                        navroute_data = json.load(nf)
                                                        route = navroute_data.get('Route', [])
                                                        if route:
                                                            final_system = route[-1].get('StarSystem', '')
                                                            current_system = self.get_current_system()
                                                            if current_system and final_system and current_system == final_system:
                                                                # Arrived at final destination - route complete
                                                                jumps = 0
                                                except Exception:
                                                    pass
                                            
                                            cached_jumps = getattr(self, '_cached_route_jumps', None)
                                            if cached_jumps != jumps:
                                                self._cached_route_jumps = jumps
                                                self._write_jumps_left(jumps)
                                                route_changed = True
                                        break
                                    elif event_type == 'NavRoute':
                                        # New route plotted - first entry is current system
                                        if os.path.exists(navroute_path):
                                            try:
                                                with open(navroute_path, 'r', encoding='utf-8') as nf:
                                                    navroute_data = json.load(nf)
                                                    route = navroute_data.get('Route', [])
                                                    jumps = max(0, len(route) - 1) if route else 0
                                                    cached_jumps = getattr(self, '_cached_route_jumps', None)
                                                    if cached_jumps != jumps:
                                                        self._cached_route_jumps = jumps
                                                        self._write_jumps_left(jumps)
                                                        route_changed = True
                                            except Exception:
                                                pass
                                        break
                                    elif event_type == 'FSDJump':
                                        # FSDJump doesn't have count - continue scanning for FSDTarget
                                        continue
                                    elif event_type in ['NavRouteClear', 'Docked', 'Touchdown']:
                                        cached_jumps = getattr(self, '_cached_route_jumps', None)
                                        if cached_jumps != 0:
                                            self._cached_route_jumps = 0
                                            self._write_jumps_left(0)
                                            route_changed = True
                                        break
                                except json.JSONDecodeError:
                                    continue
                    except Exception:
                        pass
            
            # Update display if route changed
            if route_changed and hasattr(self, 'cmdr_label_value'):
                self.after(0, self._update_cmdr_system_display)
        
        except Exception as e:
            log.error(f"Error polling route status: {e}")
        
        # Schedule next poll
        self.after(2000, self._poll_route_status)

    def _update_cmdr_system_display(self) -> None:
        """Update commander name and current system display"""
        try:
            cmdr_name = ""
            current_system = ""
            
            # Get CMDR name from journal
            if hasattr(self, 'prospector_panel') and self.prospector_panel.journal_dir:
                if not hasattr(self, '_cached_cmdr_name'):
                    from journal_parser import JournalParser
                    parser = JournalParser(self.prospector_panel.journal_dir)
                    self._cached_cmdr_name = parser.get_commander_name()
                
                cmdr_name = self._cached_cmdr_name or ""
            
            # Get current system from centralized source
            current_system = self.get_current_system() or ""
            
            # Get remaining jumps from cached value (set by _poll_route_status)
            jumps_remaining = getattr(self, '_cached_route_jumps', 0) or 0
            
            # Get visit count for CURRENT system from database
            visits_count = 0
            if current_system and hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db') and self.cargo_monitor.user_db:
                try:
                    visit_data = self.cargo_monitor.user_db.is_system_visited(current_system)
                    if visit_data:
                        visits_count = visit_data.get('visit_count', 0)
                except Exception:
                    pass
            
            # Update individual labels (white prefix, yellow value)
            self.cmdr_label_value.config(text=cmdr_name)
            
            if current_system:
                self.system_label_prefix.config(text=t('status_bar.current_system') + " ")
                self.system_label_value.config(text=current_system)
            else:
                self.system_label_prefix.config(text="")
                self.system_label_value.config(text="")
            
            self.visits_label_prefix.config(text=t('status_bar.visits') + " ")
            self.visits_label_value.config(text=str(visits_count))
            
            self.route_label_prefix.config(text=t('status_bar.systems_in_route') + " ")
            self.route_label_value.config(text=str(jumps_remaining))
            
        except Exception as e:
            log.error(f"Error updating CMDR/system display: {e}")

    def _show_edit_visits_dialog_for_current_system(self):
        """Show dialog to edit visit count for the current system"""
        try:
            current_system = self.get_current_system()
            if not current_system:
                return
            
            # Get current visit data
            visit_data = None
            current_count = 0
            if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                visit_data = self.cargo_monitor.user_db.is_system_visited(current_system)
                current_count = visit_data.get('visit_count', 0) if visit_data else 0
            
            # Create dialog
            dialog = tk.Toplevel(self)
            dialog.withdraw()  # Hide initially to prevent blinking on wrong monitor
            dialog.title(t('context_menu.edit_visits_title'))
            dialog.resizable(False, False)
            dialog.transient(self)
            
            # Set app icon
            try:
                from app_utils import get_app_icon_path
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except:
                pass
            
            # Theme colors
            if self.current_theme == "elite_orange":
                bg_color = "#000000"
                fg_color = "#ff8c00"
                entry_bg = "#1a1a1a"
                entry_fg = "#ffffff"
            else:
                bg_color = "#1e1e1e"
                fg_color = "#e0e0e0"
                entry_bg = "#2b2b2b"
                entry_fg = "#ffffff"
            
            dialog.configure(bg=bg_color)
            
            # Main frame
            frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=15)
            frame.pack(fill="both", expand=True)
            
            # System name label
            tk.Label(frame, text=t('context_menu.edit_visits_for'), 
                    bg=bg_color, fg=fg_color, font=self._scaled_font(9)).pack(anchor="w")
            
            tk.Label(frame, text=current_system, 
                    bg=bg_color, fg=fg_color, font=self._scaled_font(11, "bold")).pack(anchor="w", pady=(0, 15))
            
            # Visit count entry
            count_frame = tk.Frame(frame, bg=bg_color)
            count_frame.pack(fill="x", pady=5)
            
            tk.Label(count_frame, text=t('context_menu.visit_count_label'), 
                    bg=bg_color, fg=fg_color, font=self._scaled_font(9)).pack(side="left")
            
            count_var = tk.StringVar(value=str(current_count))
            count_entry = tk.Entry(count_frame, textvariable=count_var, width=10,
                                  bg=entry_bg, fg=entry_fg, insertbackground=fg_color,
                                  relief="solid", bd=1, font=self._scaled_font(10))
            count_entry.pack(side="left", padx=(10, 0))
            count_entry.select_range(0, tk.END)
            
            # Buttons
            btn_frame = tk.Frame(frame, bg=bg_color)
            btn_frame.pack(fill="x", pady=(20, 0))
            
            def save_and_close():
                try:
                    new_count = int(count_var.get())
                    if new_count < 0:
                        new_count = 0
                    
                    if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                        self.cargo_monitor.user_db.update_visit_count(current_system, new_count)
                        self._set_status(t('context_menu.visits_updated'), 3000)
                        # Refresh the status bar display
                        self._update_cmdr_system_display()
                except ValueError:
                    pass  # Invalid input - ignore
                
                dialog.destroy()
            
            def cancel():
                dialog.destroy()
            
            save_btn = tk.Button(btn_frame, text=t('dialogs.save'), command=save_and_close,
                                bg="#2a5a2a", fg="#ffffff", 
                                activebackground="#3a6a3a", activeforeground="#ffffff",
                                relief="solid", bd=1, cursor="hand2", 
                                pady=6, padx=15, font=self._scaled_font(9))
            save_btn.pack(side="right", padx=(8, 0))
            
            cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=cancel,
                                  bg="#5a2a2a", fg="#ffffff", 
                                  activebackground="#6a3a3a", activeforeground="#ffffff",
                                  relief="solid", bd=1, cursor="hand2", 
                                  pady=6, padx=15, font=self._scaled_font(9))
            cancel_btn.pack(side="right")
            
            # Center dialog
            dialog.update_idletasks()
            w = dialog.winfo_width()
            h = dialog.winfo_height()
            px = self.winfo_x()
            py = self.winfo_y()
            pw = self.winfo_width()
            ph = self.winfo_height()
            x = px + (pw // 2) - (w // 2)
            y = py + (ph // 2) - (h // 2)
            dialog.geometry(f"+{x}+{y}")
            dialog.deiconify()  # Show dialog after centering
            
            dialog.grab_set()
            count_entry.focus_set()
            
            # Bind Enter to save
            dialog.bind("<Return>", lambda e: save_and_close())
            dialog.bind("<Escape>", lambda e: cancel())
            
        except Exception as e:
            log.error(f"Error showing edit visits dialog: {e}")

    def _import_all_from_txt(self) -> None:
        """Import all VoiceAttack settings from Variables folder on startup"""
        print("[STARTUP] Importing VoiceAttack settings from Variables folder...")
        print(f"[STARTUP] Variables path: {self.vars_dir}")
        
        # Set flag to prevent auto-save during import
        self._importing = True
        
        found: List[str] = []
        missing: List[str] = []
        try:
            # Firegroups + buttons
            for tool in TOOL_ORDER:
                fg_name = VA_VARS[tool]["fg"]
                btn_name = VA_VARS[tool]["btn"]

                if fg_name:
                    raw = self._read_var_text(fg_name)
                    if raw is not None:
                        val = NATO_REVERSE.get(raw.upper(), raw.upper())
                        if val in FIREGROUPS:
                            self.tool_fg[tool].set(val)
                            found.append(fg_name)
                        else:
                            missing.append(fg_name)
                    else:
                        missing.append(fg_name)

                if btn_name:
                    rawb = self._read_var_text(btn_name)
                    if rawb is not None:
                        s = rawb.strip().lower()
                        btn = 1 if s == "primary" else 2 if s == "secondary" else None
                        if btn is None:
                            try:
                                num = int(s)
                                if num in (1, 2):
                                    btn = num
                            except Exception:
                                btn = None
                        if btn in (1, 2):
                            self.tool_btn[tool].set(btn)
                            found.append(btn_name)
                        else:
                            missing.append(btn_name)
                    else:
                        missing.append(btn_name)

            # Toggles
            for name, (fname, _help) in TOGGLES.items():
                base = os.path.splitext(fname)[0]
                raw = self._read_var_text(base)
                if raw is not None:
                    try:
                        if name == "Auto Honk":
                            self.toggle_vars[name].set(1 if raw.strip().lower() == "enabled" else 0)
                        elif name == "Headtracker Docking Control":
                            self.toggle_vars[name].set(1 if raw.strip() == "1" else 0)
                        else:
                            self.toggle_vars[name].set(int(raw))
                        found.append(fname)
                    except Exception:
                        missing.append(fname)
                else:
                    missing.append(fname)

            # Timers
            for name, (fname, lo, hi, _help) in TIMERS.items():
                base = os.path.splitext(fname)[0]
                raw = self._read_var_text(base)
                if raw is not None:
                    try:
                        val = float(raw) if name in self._DECIMAL_TIMERS else int(raw)
                        if lo <= val <= hi:
                            self.timer_vars[name].set(val)
                            found.append(fname)
                        else:
                            missing.append(fname)
                    except Exception:
                        missing.append(fname)
                else:
                    missing.append(fname)

            # Announcement Toggles  
            for name, (fname, _help) in ANNOUNCEMENT_TOGGLES.items():
                # Skip items with no txt file (config.json only)
                if fname is None:
                    continue
                    
                base = os.path.splitext(fname)[0]
                raw = self._read_var_text(base)
                if raw is not None:
                    try:
                        value = int(raw)
                        self.announcement_vars[name].set(value)
                        found.append(fname)
                    except Exception:
                        missing.append(fname)
                else:
                    missing.append(fname)

            # Laser Mining Extra Repeat Count
            if hasattr(self, 'laser_extra_repeat_var'):
                repeat_count_file = "laserminingextra_count"
                print(f"[IMPORT DEBUG] vars_dir = {self.vars_dir}")
                raw = self._read_var_text(repeat_count_file)
                print(f"[IMPORT DEBUG] Read {repeat_count_file}: '{raw}'")
                if raw is not None:
                    try:
                        count = int(raw)
                        # Clamp to valid range (1-10)
                        count = max(1, min(10, count))
                        self.laser_extra_repeat_var.set(count)
                        # Update status label
                        if hasattr(self, 'laser_extra_status_label'):
                            times_text = t('voiceattack.time') if count == 1 else t('voiceattack.times')
                            self.laser_extra_status_label.config(text=f"({t('voiceattack.will_run')} {count} {times_text})")
                        found.append(f"{repeat_count_file}.txt")
                        print(f"[IMPORT] Loaded laser extra repeat count: {count}")
                    except Exception as e:
                        missing.append(f"{repeat_count_file}.txt")
                        log.error(f"[IMPORT] Error loading laser extra repeat count: {e}")
                else:
                    missing.append(f"{repeat_count_file}.txt")

            # Prospector Delay
            if hasattr(self, 'prospector_delay_var'):
                prospector_delay_file = "delayprospector"
                raw = self._read_var_text(prospector_delay_file)
                if raw is not None:
                    try:
                        delay = float(raw)
                        # Clamp to valid range (0.0-6.0)
                        delay = max(0.0, min(6.0, delay))
                        self.prospector_delay_var.set(delay)
                        found.append(f"{prospector_delay_file}.txt")
                        print(f"[IMPORT] Loaded prospector delay: {delay:.1f}s")
                    except Exception as e:
                        missing.append(f"{prospector_delay_file}.txt")
                        log.error(f"[IMPORT] Error loading prospector delay: {e}")
                else:
                    missing.append(f"{prospector_delay_file}.txt")

            # Thrust Key Hold Duration
            if hasattr(self, 'thrust_upduration_var'):
                thrust_upduration_file = "thrustUpduration"
                raw = self._read_var_text(thrust_upduration_file)
                if raw is not None:
                    try:
                        delay = float(raw)
                        delay = max(0.5, min(3.5, delay))
                        self.thrust_upduration_var.set(delay)
                        found.append(f"{thrust_upduration_file}.txt")
                        print(f"[IMPORT] Loaded thrust upduration: {delay:.1f}s")
                    except Exception as e:
                        missing.append(f"{thrust_upduration_file}.txt")
                        log.error(f"[IMPORT] Error loading thrust upduration: {e}")
                else:
                    missing.append(f"{thrust_upduration_file}.txt")

            # Thrust Closed Timing
            if hasattr(self, 'thrust_closed_var'):
                thrust_closed_file = "thrustScoopClosed"
                raw = self._read_var_text(thrust_closed_file)
                if raw is not None:
                    try:
                        delay = float(raw)
                        # Clamp to valid range (0.0-5.0)
                        delay = max(0.0, min(5.0, delay))
                        self.thrust_closed_var.set(delay)
                        found.append(f"{thrust_closed_file}.txt")
                        print(f"[IMPORT] Loaded thrust closed: {delay:.1f}s")
                    except Exception as e:
                        missing.append(f"{thrust_closed_file}.txt")
                        log.error(f"[IMPORT] Error loading thrust closed: {e}")
                else:
                    missing.append(f"{thrust_closed_file}.txt")

            # Thrust Open Timing
            if hasattr(self, 'thrust_open_var'):
                thrust_open_file = "thrustScoopOpen"
                raw = self._read_var_text(thrust_open_file)
                if raw is not None:
                    try:
                        delay = float(raw)
                        # Clamp to valid range (1.0-5.0)
                        delay = max(1.0, min(5.0, delay))
                        self.thrust_open_var.set(delay)
                        found.append(f"{thrust_open_file}.txt")
                        print(f"[IMPORT] Loaded thrust open: {delay:.1f}s")
                    except Exception as e:
                        missing.append(f"{thrust_open_file}.txt")
                        log.error(f"[IMPORT] Error loading thrust open: {e}")
                else:
                    missing.append(f"{thrust_open_file}.txt")

            msg = f"Imported {len(found)} VoiceAttack values"
            if missing:
                msg += f"; {len(missing)} missing/invalid"
            self._set_status(msg, 5000)  # Show for 5 seconds
            
            # Print import summary to console prominently
            print(f"")
            print(f"========== VOICEATTACK IMPORT COMPLETE ==========")
            print(f"[STARTUP] Imported {len(found)} values from Variables folder")
            if missing:
                print(f"[STARTUP] Missing files: {missing}")
        except Exception as e:
            log.error(f"[STARTUP] Import failed with error: {e}")
            import traceback
            traceback.print_exc()
            messagebox.showerror("Import failed", str(e))
        finally:
            # Clear import flag
            self._importing = False

    def _save_all_to_txt(self) -> None:
        try:
            # Firegroups + buttons
            for tool in TOOL_ORDER:
                fg_name = VA_VARS[tool]["fg"]
                btn_name = VA_VARS[tool]["btn"]

                if fg_name:
                    letter = self.tool_fg[tool].get()
                    if letter in FIREGROUPS:
                        self._write_var_text(fg_name, NATO.get(letter, letter))

                if btn_name:
                    v = self.tool_btn[tool].get()
                    if v in (1, 2):
                        self._write_var_text(btn_name, "primary" if v == 1 else "secondary")

            # Toggles
            for name, (fname, _help) in TOGGLES.items():
                base = os.path.splitext(fname)[0]
                if name == "Auto Honk":
                    val = "enabled" if self.toggle_vars[name].get() else "disabled"
                    self._write_var_text(base, val)
                elif name == "Headtracker Docking Control":
                    self._write_var_text(base, "1" if self.toggle_vars[name].get() else "0")
                else:
                    self._write_var_text(base, str(self.toggle_vars[name].get()))

            # Announcement Toggles - now handled by config.json only, skip .txt files
            # Save announcement preferences to config.json
            self._save_announcement_preferences()

            # Timers (clamped to allowed range)
            for name, spec in TIMERS.items():
                fname, lo, hi, _help = spec
                base = os.path.splitext(fname)[0]
                try:
                    raw = self.timer_vars[name].get()
                    raw = round(raw, 1) if name in self._DECIMAL_TIMERS else int(raw)
                except Exception:
                    raw = lo
                val = max(lo, min(hi, raw))
                self.timer_vars[name].set(val)
                self._write_var_text(base, str(val))

            # Laser Mining Extra Repeat Count
            if hasattr(self, 'laser_extra_repeat_var'):
                try:
                    count = self.laser_extra_repeat_var.get()
                    # Clamp to valid range (1-10)
                    count = max(1, min(10, count))
                    self._write_var_text("laserminingextra_count", str(count))
                    print(f"[SAVE] Saved laser extra repeat count: {count}")
                except Exception as e:
                    log.error(f"[SAVE] Error saving laser extra repeat count: {e}")

            self._set_status("Settings saved to VoiceAttack Variables.")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    # ---------- Presets (Settings folder) ----------
    def _open_ship_presets_folder(self) -> None:
        os.startfile(self.settings_dir)

    def _settings_path(self, name: str) -> str:
        return os.path.join(self.settings_dir, f"{name}.json")

    def _configure_preset_list_row_colors(self) -> None:
        """Configure row colors for preset list based on current theme"""
        if self.current_theme == "elite_orange":
            self.preset_list.tag_configure('oddrow', background='#1e1e1e', foreground='#ff8c00', font=self._scaled_font(9))
            self.preset_list.tag_configure('evenrow', background='#252525', foreground='#ff8c00', font=self._scaled_font(9))
            self.preset_list.tag_configure('group', background='#1a1a1a', foreground='#ffcc00', font=self._scaled_font(9, "bold"))
            self.preset_list.tag_configure('active_preset', background='#5a3a0a', foreground='#ffcc00', font=self._scaled_font(9, "bold"))
        elif self.current_theme in ("modern", "modern_slate", "modern_orange"):
            self.preset_list.tag_configure('oddrow', background=modern_color('#1D2228'), foreground=modern_color('#E6EAF0'), font=self._scaled_font(9))
            self.preset_list.tag_configure('evenrow', background=modern_color('#232A31'), foreground=modern_color('#E6EAF0'), font=self._scaled_font(9))
            self.preset_list.tag_configure('group', background=modern_color('#1D2228'), foreground=modern_color('#FFB347'), font=self._scaled_font(9, "bold"))
            self.preset_list.tag_configure('active_preset', background=modern_color('#4A3520'), foreground='#FFFFFF', font=self._scaled_font(9, "bold"))
        else:
            self.preset_list.tag_configure('oddrow', background='#1e1e1e', foreground='#e6e6e6', font=self._scaled_font(9))
            self.preset_list.tag_configure('evenrow', background='#282828', foreground='#e6e6e6', font=self._scaled_font(9))
            self.preset_list.tag_configure('group', background='#1a1a1a', foreground='#aaaaaa', font=self._scaled_font(9, "bold"))
            self.preset_list.tag_configure('active_preset', background='#2a4a6a', foreground='#ffffff', font=self._scaled_font(9, "bold"))

    def _parse_preset_ship_type(self, preset_name: str) -> tuple:
        """Parse preset name to extract ship type and build variant.
        
        Examples:
            'Adder Test' -> ('Adder', 'Test')
            'Type-11 Prospector HAZ' -> ('Type-11 Prospector', 'HAZ')
            'Imperial Cutter 4x lasers' -> ('Imperial Cutter', '4x lasers')
            'Python Mk II Core Mining' -> ('Python Mk II', 'Core Mining')
        
        Returns:
            (ship_type, variant) tuple
        """
        # Known ship types (must match the dropdown list, longest first for proper matching)
        known_ships = sorted(SHIP_TYPES, key=len, reverse=True)
        
        # Try to match against known ship names
        name_to_check = preset_name
        for ship in known_ships:
            if name_to_check.lower().startswith(ship.lower()):
                # Found a matching ship
                variant = name_to_check[len(ship):].strip()
                # Clean up variant (remove leading separators)
                if variant.startswith("-") or variant.startswith("_"):
                    variant = variant[1:].strip()
                return (ship, variant if variant else "")
        
        # No known ship type found - use full name as group
        return (preset_name, "")
    
    def _expand_all_preset_groups(self) -> None:
        """Expand all ship type groups in the preset list"""
        for item in self.preset_list.get_children():
            self.preset_list.item(item, open=True)
        self._save_preset_expanded_state()
    
    def _collapse_all_preset_groups(self) -> None:
        """Collapse all ship type groups in the preset list"""
        for item in self.preset_list.get_children():
            self.preset_list.item(item, open=False)
        self._save_preset_expanded_state()
    
    def _save_preset_expanded_state(self) -> None:
        """Save which preset groups are expanded to config"""
        from config import save_preset_expanded_groups
        expanded = []
        for item in self.preset_list.get_children():
            if self.preset_list.item(item, "open"):
                group_text = self.preset_list.item(item, "text")
                if group_text.startswith("📁 "):
                    expanded.append(group_text[2:].strip())
        save_preset_expanded_groups(expanded)
    
    def _refresh_preset_list(self) -> None:
        """Refresh preset list with grouped hierarchy by ship type"""
        from config import load_preset_expanded_groups
        
        # Remember which groups were expanded before refresh
        expanded_groups = set()
        for item in self.preset_list.get_children():
            if self.preset_list.item(item, "open"):
                # Get the group name (remove the folder emoji prefix)
                group_text = self.preset_list.item(item, "text")
                if group_text.startswith("📁 "):
                    expanded_groups.add(group_text[2:].strip())
        
        # If no groups exist yet (first load), load from config or default to all collapsed
        first_load = len(expanded_groups) == 0 and len(self.preset_list.get_children()) == 0
        if first_load:
            saved_expanded = load_preset_expanded_groups()
            if saved_expanded:
                expanded_groups = set(saved_expanded)
        
        for item in self.preset_list.get_children():
            self.preset_list.delete(item)
        
        # Collect all preset names
        names = []
        try:
            for fn in os.listdir(self.settings_dir):
                if fn.lower().endswith(".json"):
                    names.append(os.path.splitext(fn)[0])
        except OSError:
            log.exception("Could not list ship preset files")
        
        # Group by ship type
        groups = {}
        for name in sorted(names, key=str.casefold):
            ship_type, variant = self._parse_preset_ship_type(name)
            if ship_type not in groups:
                groups[ship_type] = []
            groups[ship_type].append((name, variant))
        
        # Insert groups and presets
        row_idx = 0
        for ship_type in sorted(groups.keys(), key=str.casefold):
            presets = groups[ship_type]
            
            # Determine if this group should be expanded
            # Preserve previous state or use saved config state
            should_expand = ship_type in expanded_groups
            
            # Create group header (not selectable for loading)
            group_id = self.preset_list.insert("", "end", text=f"📁 {ship_type}", 
                                               open=should_expand, tags=('group',))
            
            # Add presets under this group
            for full_name, variant in presets:
                row_tag = 'evenrow' if row_idx % 2 == 0 else 'oddrow'
                # Display variant (or "Default" if empty), store full name in values
                display_text = variant if variant else "Default"
                self.preset_list.insert(group_id, "end", text=f"      {display_text}",
                                        values=(full_name,), tags=(row_tag,))
                row_idx += 1

        self._ship_update_preset_row_highlight()

    def _select_preset_by_name(self, preset_name: str, *, collapse_ship_key: Optional[str] = None) -> bool:
        """Find and select a preset by its full name in the hierarchical tree.
        Returns True if found, False otherwise."""
        groups = self.preset_list.get_children()
        for group_id in groups:
            for item_id in self.preset_list.get_children(group_id):
                values = self.preset_list.item(item_id, "values")
                if values and values[0] == preset_name:
                    if collapse_ship_key:
                        previous_group_text = f"📁 {collapse_ship_key}"
                        for other_group_id in groups:
                            if other_group_id != group_id and self.preset_list.item(other_group_id, "text").casefold() == previous_group_text:
                                self.preset_list.item(other_group_id, open=False)
                                break
                    self.preset_list.item(group_id, open=True)
                    self.preset_list.selection_set(item_id)
                    self.preset_list.see(item_id)
                    self.preset_list.focus(item_id)
                    return True
        return False
    
    def _deselect_on_empty_click(self, event, tree: ttk.Treeview) -> None:
        """Deselect all items when clicking on empty space in a treeview"""
        item = tree.identify_row(event.y)
        if not item:
            # Clicked on empty space - deselect all
            tree.selection_remove(*tree.selection())
    
    def _on_preset_double_click(self, event) -> Optional[str]:
        """Handle double-click on preset list - load preset or toggle group"""
        item = self.preset_list.identify_row(event.y)
        if not item:
            return
        
        # Check if this is a group header (has children)
        children = self.preset_list.get_children(item)
        if children:
            # It's a group - toggle expand/collapse
            if self.preset_list.item(item, "open"):
                self.preset_list.item(item, open=False)
            else:
                self.preset_list.item(item, open=True)
            self._save_preset_expanded_state()
        else:
            # It's a preset - load it
            self._load_selected_preset()
        return "break"

    def _current_mapping(self) -> Dict[str, Any]:
        # Exclude Core/Non-Core settings from ship presets
        announcement_settings = {}
        for k, v in self.announcement_vars.items():
            if k not in ("Core Asteroids", "Non-Core Asteroids"):
                announcement_settings[k] = v.get()
        
        preset_data = {
            "Firegroups": {
                t: {"fg": self.tool_fg[t].get(),
                    "btn": (self.tool_btn[t].get() if t in self.tool_btn else None)}
                for t in TOOL_ORDER
            },
            "Toggles": {k: v.get() for k, v in self.toggle_vars.items() if k not in PRESET_EXCLUDED_TOGGLES},
            "Announcements": announcement_settings,
            "Timers": {k: v.get() for k, v in self.timer_vars.items()},
        }
        
        # Add laser mining extra repeat count if available
        if hasattr(self, 'laser_extra_repeat_var'):
            preset_data["LaserExtraRepeatCount"] = self.laser_extra_repeat_var.get()
        
        # Add prospector delay if available
        if hasattr(self, 'prospector_delay_var'):
            preset_data["ProspectorDelay"] = self.prospector_delay_var.get()

        # Add linked announcement preset slot
        if self._active_ship_announcement_slot:
            preset_data["AnnouncementPresetSlot"] = self._active_ship_announcement_slot
        
        # Add thrust timing values if available
        if hasattr(self, 'thrust_upduration_var'):
            preset_data["ThrustUpDuration"] = self.thrust_upduration_var.get()
        if hasattr(self, 'thrust_closed_var'):
            preset_data["ThrustClosed"] = self.thrust_closed_var.get()
        if hasattr(self, 'thrust_open_var'):
            preset_data["ThrustOpen"] = self.thrust_open_var.get()
        
        return preset_data

    def _apply_mapping(self, data: Dict[str, Any]) -> None:
        for tool, spec in data.get("Firegroups", {}).items():
            fg = spec.get("fg")
            if isinstance(fg, str) and fg in FIREGROUPS and tool in self.tool_fg:
                self.tool_fg[tool].set(fg)
            btn = spec.get("btn")
            if tool in self.tool_btn and isinstance(btn, int) and btn in (1, 2):
                self.tool_btn[tool].set(btn)
        toggles_data = data.get("Toggles", {}).copy()
        for old_key in ("Target", "Auto Deselect Target"):
            if old_key in toggles_data:
                toggles_data.setdefault("Auto Deselect Prospector", toggles_data.pop(old_key))
        for k, v in toggles_data.items():
            if k in self.toggle_vars and k not in PRESET_EXCLUDED_TOGGLES:
                self.toggle_vars[k].set(int(v))
        # Toggles missing from an older preset default to off, so a discarded
        # in-memory change doesn't survive after re-loading the preset
        for k in self.toggle_vars:
            if k not in toggles_data and k not in PRESET_EXCLUDED_TOGGLES:
                self.toggle_vars[k].set(0)
        
        # Handle announcements: if section exists, load it; if not, set all to disabled (0)
        # BUT exclude Core/Non-Core settings from ship presets
        announcements_data = data.get("Announcements", {})
        if announcements_data:
            # Load announcement settings from preset (excluding Core/Non-Core)
            for k, v in announcements_data.items():
                if k in self.announcement_vars and k not in ("Core Asteroids", "Non-Core Asteroids"):
                    self.announcement_vars[k].set(int(v))
        else:
            # No announcements in preset (old preset): set non-Core/Non-Core to disabled for consistency
            for k in self.announcement_vars:
                if k not in ("Core Asteroids", "Non-Core Asteroids"):
                    self.announcement_vars[k].set(0)
        
        for k, v in data.get("Timers", {}).items():
            # Migrate old timer key to new key
            if k == "Delay before selecting prospector target after laser mining":
                k = "Delay before targeting the prospector after launching"
            if k == "Duration for additional laser periods (per cycle)":
                k = "Duration for repeated mining cycles (per cycle)"
            if k == "Boost Interval (For Core Mining Boost sequense )":
                k = "Boost Interval (Core Mining)"
            if k in self.timer_vars:
                self.timer_vars[k].set(float(v) if k in self._DECIMAL_TIMERS else int(v))

        # Load laser mining extra repeat count if available
        if "LaserExtraRepeatCount" in data and hasattr(self, 'laser_extra_repeat_var'):
            try:
                count = int(data["LaserExtraRepeatCount"])
                # Clamp to valid range (1-10)
                count = max(1, min(10, count))
                self.laser_extra_repeat_var.set(count)
                # Update the status label
                if hasattr(self, 'laser_extra_status_label'):
                    times_text = t('voiceattack.time') if count == 1 else t('voiceattack.times')
                    self.laser_extra_status_label.config(text=f"({t('voiceattack.will_run')} {count} {times_text})")
                print(f"[PRESET] Loaded laser extra repeat count: {count}")
            except Exception as e:
                log.error(f"[PRESET] Error loading laser extra repeat count: {e}")
        
        # Load linked announcement preset slot
        self._active_ship_announcement_slot = data.get("AnnouncementPresetSlot") or None

        # Load prospector delay if available
        if "ProspectorDelay" in data and hasattr(self, 'prospector_delay_var'):
            try:
                delay = float(data["ProspectorDelay"])
                # Clamp to valid range (0.0-6.0)
                delay = max(0.0, min(6.0, delay))
                self.prospector_delay_var.set(delay)
                self._save_prospector_delay()
                print(f"[PRESET] Loaded prospector delay: {delay:.1f}s")
            except Exception as e:
                log.error(f"[PRESET] Error loading prospector delay: {e}")
        
        # Load thrust key hold duration if available
        if "ThrustUpDuration" in data and hasattr(self, 'thrust_upduration_var'):
            try:
                delay = float(data["ThrustUpDuration"])
                delay = max(0.5, min(3.5, delay))
                self.thrust_upduration_var.set(delay)
                self._save_thrust_upduration()
                print(f"[PRESET] Loaded thrust up duration: {delay:.1f}s")
            except Exception as e:
                log.error(f"[PRESET] Error loading thrust up duration: {e}")

        # Load thrust closed timing if available
        if "ThrustClosed" in data and hasattr(self, 'thrust_closed_var'):
            try:
                delay = float(data["ThrustClosed"])
                # Clamp to valid range (0.0-5.0)
                delay = max(0.0, min(5.0, delay))
                self.thrust_closed_var.set(delay)
                self._save_thrust_closed()
                print(f"[PRESET] Loaded thrust closed timing: {delay:.1f}s")
            except Exception as e:
                log.error(f"[PRESET] Error loading thrust closed timing: {e}")
        
        # Load thrust open timing if available
        if "ThrustOpen" in data and hasattr(self, 'thrust_open_var'):
            try:
                delay = float(data["ThrustOpen"])
                # Clamp to valid range (1.0-5.0)
                delay = max(1.0, min(5.0, delay))
                self.thrust_open_var.set(delay)
                self._save_thrust_open()
                print(f"[PRESET] Loaded thrust open timing: {delay:.1f}s")
            except Exception as e:
                log.error(f"[PRESET] Error loading thrust open timing: {e}")
        
        # IMPORTANT: Save all loaded values to Variables folder immediately
        self._save_all_to_txt()
        self._ship_preset_done('loaded')

    def _ask_new_preset_name(self, preselect_ship: Optional[str] = None) -> Optional[str]:
        return self._ask_edit_preset_name(preselect_ship or "", "", "", creating=True)

    def _get_selected_preset(self) -> Optional[str]:
        """Get the selected preset name (not group headers)"""
        sel = self.preset_list.selection()
        if not sel:
            return None
        item_id = sel[0]
        
        # Check if this is a group header (has children)
        children = self.preset_list.get_children(item_id)
        if children:
            # It's a group, not a preset
            return None
        
        # Get the full preset name from values
        values = self.preset_list.item(item_id, "values")
        if values:
            return values[0]  # Full preset name stored in values
        return None

    def _save_as_new(self) -> None:
        # Detect current ship from cargo monitor (active ship in game)
        current_ship = None
        if hasattr(self, 'cargo_monitor') and self.cargo_monitor and self.cargo_monitor.ship_type:
            current_ship = self.cargo_monitor.ship_type
        
        # Fallback: use selected folder in preset list
        if not current_ship:
            selection = self.preset_list.selection()
            if selection:
                selected_item = selection[0]
                parent = self.preset_list.parent(selected_item)
                if parent:  # Item is inside a folder
                    folder_text = self.preset_list.item(parent, "text")
                    if folder_text.startswith("📁 "):
                        current_ship = folder_text[2:].strip()
        
        name = self._ask_new_preset_name(preselect_ship=current_ship)
        if not name:
            return
        path = self._settings_path(name)
        if os.path.exists(path):
            messagebox.showerror("Name exists", f"A preset named '{name}' already exists.")
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._current_mapping(), f, indent=2)
        self._refresh_preset_list()
        # Select the newly created preset
        self._select_preset_by_name(name)
        self._ship_set_active_preset(name)
        self._ship_preset_done('saved')

    def _write_preset_file(self, name: str) -> None:
        """Write current settings to an existing preset file"""
        path = self._settings_path(name)
        new_data = self._current_mapping()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2)
        self._ship_set_active_preset(name)

    def _overwrite_selected(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            from app_utils import centered_message
            centered_message(self, "No preset selected", "Choose a preset to overwrite.")
            return

        # Confirm overwrite
        from app_utils import centered_askyesno
        if not centered_askyesno(self, "Confirm Overwrite",
                      f"This will overwrite preset '{sel}' with current settings.\n\n"
                      f"This action cannot be undone.\n\n"
                      f"Continue?"):
            return

        self._write_preset_file(sel)
        self._ship_preset_done('updated')

    def _edit_selected_preset(self) -> None:
        """Edit the selected preset - change ship type and build name"""
        old_name = self._get_selected_preset()
        if not old_name:
            from app_utils import centered_message
            centered_message(self, "No preset selected", "Choose a preset to edit.")
            return
        
        # Parse current name to get ship type and variant
        detected_ship, detected_variant = self._parse_preset_ship_type(old_name)
        
        # Show edit dialog (reuse import dialog logic)
        new_name = self._ask_edit_preset_name(detected_ship, detected_variant, old_name)
        if not new_name or new_name == old_name:
            return
        
        # Check if new name already exists
        new_path = self._settings_path(new_name)
        if os.path.exists(new_path):
            messagebox.showerror("Edit failed", f"A preset named '{new_name}' already exists.")
            return
        
        # Rename the file
        old_path = self._settings_path(old_name)
        try:
            os.rename(old_path, new_path)
            self._update_ship_auto_load_assignments(old_name, new_name)
            if old_name == self._active_ship_preset_name:
                self._active_ship_preset_name = new_name
                from config import save_active_ship_preset
                save_active_ship_preset(new_name)
            self._refresh_preset_list()
            self._select_preset_by_name(new_name)
            self._ship_preset_done('updated')
        except Exception as e:
            messagebox.showerror("Edit failed", str(e))

    def _ask_edit_preset_name(self, detected_ship: str, detected_variant: str, original_name: str, *, importing: bool = False, creating: bool = False) -> Optional[str]:
        """Choose the ship type and build name for a preset."""
        # Complete Elite Dangerous ship list (alphabetical)
        ship_types = (*SHIP_TYPES, "Other")

        dialog = tk.Toplevel(self)
        dialog.withdraw()
        title_key = 'new_ship_preset' if creating else 'import_ship_preset' if importing else 'edit_ship_preset'
        dialog.title(t('dialogs.' + title_key))
        bg = self.theme_colors['bg']
        fg = self.theme_colors['fg']
        entry_bg = self.theme_colors['bg_accent']
        dialog.configure(bg=bg)
        width, height = (480, 280) if importing else (550, 300)
        dialog.geometry(f"{self._scaled_px(width)}x{self._scaled_px(height)}")
        dialog.resizable(not importing, not importing)
        if not importing:
            dialog.minsize(self._scaled_px(480), self._scaled_px(280))

        # Theme-aware accent color
        if self.current_theme == "elite_orange":
            accent_color = "#ff8c00"
            accent_fg = "#000000"
        else:
            accent_color = "#4a9eff"
            accent_fg = "#ffffff"

        # Configure theme style for combobox
        style = ttk.Style(dialog)
        style.configure("Preset.TCombobox",
                       fieldbackground=entry_bg,
                       background=entry_bg,
                       foreground=fg,
                       selectbackground=accent_color,
                       selectforeground=accent_fg)
        style.map("Preset.TCombobox",
                 fieldbackground=[("readonly", entry_bg)],
                 selectbackground=[("readonly", accent_color)],
                 selectforeground=[("readonly", accent_fg)])

        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass

        result = None

        # Title
        title_label = tk.Label(dialog, text=t("dialogs." + title_key),
                              bg=bg, fg=accent_color,
                              font=self._scaled_font(12, "bold"))
        title_label.pack(pady=(15, 5))

        # Show current name
        if not creating:
            orig_label = tk.Label(dialog, text=t('dialogs.preset_original' if importing else 'dialogs.preset_current').format(name=original_name),
                                  bg=bg, fg=self.theme_colors['fg_muted'],
                                  font=self._scaled_font(9))
            orig_label.pack(pady=(0, 10))

        # Ship Type selection
        type_frame = tk.Frame(dialog, bg=bg)
        type_frame.pack(fill="x", padx=25, pady=(0, 10))

        tk.Label(type_frame, text=t("dialogs.preset_ship_type"), bg=bg, fg=fg,
                font=self._scaled_font(10)).pack(side=tk.LEFT)

        # Find best match for detected ship
        ship_var = tk.StringVar()
        if detected_ship in ship_types:
            ship_var.set(detected_ship)
        else:
            # Try case-insensitive match
            for s in ship_types:
                if s.lower() == detected_ship.lower():
                    ship_var.set(s)
                    break
            else:
                ship_var.set(ship_types[0])

        ship_combo = ttk.Combobox(type_frame, textvariable=ship_var, values=ship_types,
                                  state="readonly", width=28, font=self._scaled_font(10),
                                  style="Preset.TCombobox")
        ship_combo.pack(side=tk.LEFT, padx=(15, 0))

        # Build name entry
        name_frame = tk.Frame(dialog, bg=bg)
        name_frame.pack(fill="x", padx=25, pady=10)

        tk.Label(name_frame, text=t("dialogs.preset_build_name"), bg=bg, fg=fg,
                font=self._scaled_font(10)).pack(side=tk.LEFT)

        name_entry = tk.Entry(name_frame, font=self._scaled_font(10), width=30,
                             bg=entry_bg, fg=fg, insertbackground=accent_color,
                             selectbackground=accent_color, selectforeground=accent_fg,
                             relief="flat", bd=2)
        name_entry.pack(side=tk.LEFT, padx=(10, 0))
        if detected_variant:
            name_entry.insert(0, detected_variant)

        # Preview
        preview_frame = tk.Frame(dialog, bg=bg)
        preview_frame.pack(fill="x", padx=25, pady=10)

        tk.Label(preview_frame, text=t("dialogs.preset_preview"), bg=bg, fg="#888888",
                font=self._scaled_font(9)).pack(side=tk.LEFT)

        preview_label = tk.Label(preview_frame, text="", bg=bg, fg=accent_color,
                                font=self._scaled_font(10, "bold"))
        preview_label.pack(side=tk.LEFT, padx=(10, 0))

        def update_preview(*args):
            ship = ship_var.get()
            name = name_entry.get().strip()
            if name:
                preview_label.config(text=f"{ship} {name}")
            else:
                preview_label.config(text=f"{ship}")

        ship_var.trace("w", update_preview)
        name_entry.bind("<KeyRelease>", update_preview)
        update_preview()

        # Buttons frame
        btn_frame = tk.Frame(dialog, bg=bg)
        btn_frame.pack(pady=15)

        def on_ok():
            nonlocal result
            ship = ship_var.get()
            name = name_entry.get().strip()
            if name:
                result = f"{ship} {name}"
            else:
                result = ship
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        ok_btn = tk.Button(btn_frame, text=t("common.import" if importing else "common.save"), command=on_ok,
                          bg=accent_color, fg=accent_fg, font=self._scaled_font(10, "bold"),
                          activebackground=accent_color, activeforeground=accent_fg,
                          width=10, cursor="hand2")
        ok_btn.pack(side=tk.LEFT, padx=5)

        cancel_btn = tk.Button(btn_frame, text=t('common.cancel'), command=on_cancel,
                              bg="#3a3a3a", fg=fg, font=self._scaled_font(10),
                              activebackground="#4a4a4a", activeforeground=fg,
                              width=10, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT, padx=5)

        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())

        dialog.update_idletasks()
        center_window(dialog, self.winfo_toplevel())
        dialog.deiconify()

        # Force dialog to stay on top and have focus
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except:
            pass

        name_entry.focus_set()

        # Keep dialog on top while open
        def keep_on_top():
            try:
                if dialog.winfo_exists():
                    # A lift while the native dropdown is open buries it.
                    popdown = dialog.tk.call('ttk::combobox::PopdownWindow', str(ship_combo))
                    if not dialog.tk.getboolean(dialog.tk.call('winfo', 'ismapped', popdown)):
                        dialog.lift()
                    dialog.after(100, keep_on_top)
            except:
                pass
        dialog.after(100, keep_on_top)

        dialog.wait_window()
        return result

    def _queue_search_service_status(self, service: str, status: str):
        def update():
            if service == 'market':
                self._update_market_api_status(status)
            elif service == 'spansh':
                self.ring_finder._update_spansh_status(status)
        try:
            self.after(0, update)
        except (RuntimeError, tk.TclError):
            pass

    def _check_market_api_status(self):
        """Check market API status in background and update indicator"""
        def _background_check():
            import requests
            def _schedule(status):
                try:
                    self.after(0, lambda: self._update_market_api_status(status))
                except RuntimeError:
                    pass  # Tkinter loop already stopped — app is shutting down
            try:
                # Test Ardent API
                ardent_url = "https://api.ardent-insight.com/v2/system/name/Sol/commodity/name/platinum/nearby/imports?minVolume=1&maxDaysAgo=2&maxDistance=50"
                try:
                    response = requests.get(ardent_url, timeout=5)
                    print(f"[MARKET API] Ardent status code: {response.status_code}")
                    if response.status_code == 200:
                        _schedule("online")
                        return
                except Exception as e:
                    log.error(f"[MARKET API] Ardent exception: {e}")
                _schedule("offline")
            except Exception:
                _schedule("offline")
        
        threading.Thread(target=_background_check, daemon=True).start()
        self.after(300000, self._check_market_api_status)
    
    def _update_market_api_status(self, status: str):
        self._update_footer_indicator('market', status)

    def _load_selected_preset(self) -> None:
        sel = self._get_selected_preset()
        if sel:
            self._load_ship_preset(sel)

    def _load_ship_preset(self, sel: str) -> bool:
        if self._ship_is_preset_modified():
            result = self._show_unsaved_ship_preset_dialog()
            if result == "yes":  # Save changes to the currently active preset
                self._write_preset_file(self._active_ship_preset_name)
            elif result == "no":  # Discard changes
                pass
            else:  # Cancel - don't switch
                return False

        try:
            with open(self._settings_path(sel), "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_mapping(data)
            slot = data.get("AnnouncementPresetSlot")
            if slot:
                self._ann_load_preset(slot)
            self._ship_set_active_preset(sel)
            return True
        except Exception as e:
            messagebox.showerror("Load failed", str(e))
            return False

    def _ship_get_current_snapshot(self):
        """Get a snapshot of current ship preset settings for comparison"""
        try:
            return self._current_mapping()
        except Exception:
            return None

    def _ship_is_preset_modified(self):
        """Check if current settings differ from the loaded ship preset snapshot"""
        if self._active_ship_preset_name is None or self._active_ship_preset_snapshot is None:
            return False
        current = self._ship_get_current_snapshot()
        if current is None:
            return False
        return current != self._active_ship_preset_snapshot

    def _ship_set_active_preset(self, name):
        """Set the active ship preset and take a snapshot"""
        self._active_ship_preset_name = name
        self._active_ship_preset_snapshot = self._ship_get_current_snapshot()
        from config import save_active_ship_preset
        save_active_ship_preset(name)
        self._ship_update_preset_row_highlight()

    def _ship_clear_active_preset(self):
        """Clear active ship preset tracking"""
        self._active_ship_preset_name = None
        self._active_ship_preset_snapshot = None
        from config import save_active_ship_preset
        save_active_ship_preset(None)
        self._ship_update_preset_row_highlight()

    def _ship_update_preset_row_highlight(self):
        """Update the active ship preset's row highlight in the preset tree"""
        self._ship_queue_diff_tint()
        if not hasattr(self, 'preset_list'):
            return

        is_modified = self._ship_is_preset_modified()

        row_idx = 0
        for group_id in self.preset_list.get_children():
            for item_id in self.preset_list.get_children(group_id):
                values = self.preset_list.item(item_id, "values")
                full_name = values[0] if values else None
                base_text = self.preset_list.item(item_id, "text")
                display_text = base_text[:-2] if base_text.endswith(" *") else base_text

                if full_name == self._active_ship_preset_name:
                    tag = 'active_preset'
                    self.preset_list.item(item_id, text=f"{display_text} *" if is_modified else display_text, tags=(tag,))
                    self.after_idle(lambda i=item_id: self.preset_list.selection_remove(i) if i in self.preset_list.selection() else None)
                else:
                    tag = 'evenrow' if row_idx % 2 == 0 else 'oddrow'
                    self.preset_list.item(item_id, text=display_text, tags=(tag,))
                row_idx += 1

    def _ship_check_modified(self):
        """Check if ship preset was modified and update row highlight"""
        self._ship_update_preset_row_highlight()

    def _preset_diff_fg(self):
        """Text colour for values changed since the active preset was saved or loaded."""
        if self.current_theme == "modern_orange":
            return "#5CC8FF"  # nearly all text is orange here, so the accent orange would not stand out
        if self.current_theme == "modern_slate":
            return "#FF9A32"  # Slate's own accent is light grey, the same as its text, so use the plain orange
        if self.current_theme == "modern":
            return modern_color("#FF9A32")
        return "#ffffff" if self.current_theme == "elite_orange" else "#ffcc00"

    def _ship_register_diff_widgets(self, root):
        """Track the checkboxes and spinboxes under root whose values are saved in ship presets."""
        paths = {str(v): ("Toggles", k) for k, v in self.toggle_vars.items() if k not in PRESET_EXCLUDED_TOGGLES}
        paths.update({str(v): ("Timers", k) for k, v in self.timer_vars.items()})
        for attr, key in (('laser_extra_repeat_var', "LaserExtraRepeatCount"), ('prospector_delay_var', "ProspectorDelay"),
                          ('thrust_upduration_var', "ThrustUpDuration"), ('thrust_closed_var', "ThrustClosed"),
                          ('thrust_open_var', "ThrustOpen")):
            if hasattr(self, attr):
                paths[str(getattr(self, attr))] = (key,)

        def walk(widget):
            for child in widget.winfo_children():
                option = {"Checkbutton": "variable", "Spinbox": "textvariable", "Entry": "textvariable"}.get(child.winfo_class())
                path = paths.get(str(child.cget(option))) if option else None
                if path:
                    self._ship_diff_widgets.append((child, "fg", child.cget("fg"), (path,)))
                walk(child)
        walk(root)
        self._ship_queue_diff_tint()

    def _ship_queue_diff_tint(self):
        if not self._ship_diff_tint_pending:
            self._ship_diff_tint_pending = True
            self.after_idle(self._ship_apply_diff_tint)

    def _ship_apply_diff_tint(self):
        """Colour controls whose value differs from the active ship preset (no active preset = no colour)."""
        self._ship_diff_tint_pending = False
        saved = self._active_ship_preset_snapshot if self._active_ship_preset_name else None
        current = self._ship_get_current_snapshot() if saved else None
        diff_fg = self._preset_diff_fg()
        missing = object()

        def lookup(data, path):
            for key in path:
                if not isinstance(data, dict) or key not in data:
                    return missing
                data = data[key]
            return data

        diff_combo_style = "FgDiff.TCombobox"
        ttk.Style(self).map(diff_combo_style, foreground=[("disabled", "#666666"), ("!disabled", diff_fg)])
        for widget, option, base, paths, *only_if in self._ship_diff_widgets:
            changed = current is not None and any(
                lookup(saved, path) is not missing and lookup(saved, path) != lookup(current, path) for path in paths)
            if changed and only_if and not only_if[0]():
                changed = False
            value = (diff_combo_style if option == "style" else diff_fg) if changed else base
            try:
                widget.configure(**{option: value})
            except tk.TclError:
                pass

    def _populate_announcement_preset_submenu(self, preset_full_name: str) -> None:
        """Rebuild the Announcement Preset submenu for the right-clicked ship preset"""
        self._ann_preset_submenu.delete(0, "end")

        current_slot = 0
        if preset_full_name == self._active_ship_preset_name:
            current_slot = self._active_ship_announcement_slot or 0
        else:
            try:
                with open(self._settings_path(preset_full_name), "r", encoding="utf-8") as f:
                    data = json.load(f)
                current_slot = data.get("AnnouncementPresetSlot") or 0
            except Exception:
                pass
        self._ann_preset_menu_var.set(current_slot)

        cfg = self.prospector_panel._load_cfg() if hasattr(self, 'prospector_panel') else {}
        preset_names = cfg.get('preset_names', {})

        for i in range(1, 7):
            name = preset_names.get(str(i), t('settings.preset_button').format(num=i))
            self._ann_preset_submenu.add_radiobutton(
                label=name, variable=self._ann_preset_menu_var, value=i,
                command=lambda i=i: self._set_preset_announcement_link(preset_full_name, i))
        self._ann_preset_submenu.add_separator()
        self._ann_preset_submenu.add_radiobutton(
            label=t('context_menu.no_announcement_preset'), variable=self._ann_preset_menu_var, value=0,
            command=lambda: self._set_preset_announcement_link(preset_full_name, None))

    def _set_preset_announcement_link(self, preset_full_name: str, slot: Optional[int]) -> None:
        """Link or unlink an announcement preset slot to a ship preset"""
        if preset_full_name == self._active_ship_preset_name:
            # Active preset: update in-memory state so it's tracked like any other setting
            self._active_ship_announcement_slot = slot
            self._ship_check_modified()
            if slot:
                self._ann_load_preset(slot)
            return

        path = self._settings_path(preset_full_name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Update failed", str(e))
            return

        if slot:
            data["AnnouncementPresetSlot"] = slot
        else:
            data.pop("AnnouncementPresetSlot", None)

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            messagebox.showerror("Update failed", str(e))
            return

    def _delete_selected(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            return
        from app_utils import centered_askyesno
        if centered_askyesno(self, "Delete preset", f"Delete preset '{sel}'?"):
            try:
                os.remove(self._settings_path(sel))
                self._update_ship_auto_load_assignments(sel, None)
                if sel == self._active_ship_preset_name:
                    self._ship_clear_active_preset()
                self._refresh_preset_list()
                self._ship_preset_done('deleted')
            except Exception as e:
                messagebox.showerror("Delete failed", str(e))

    def _duplicate_selected_preset(self) -> None:
        """Duplicate the selected preset with a new name, then open edit dialog"""
        sel = self._get_selected_preset()
        if not sel:
            return
        
        # Generate a unique copy name
        base_name = f"{sel} - Copy"
        new_name = base_name
        counter = 2
        while os.path.exists(self._settings_path(new_name)):
            new_name = f"{base_name} {counter}"
            counter += 1
            
        try:
            # Load the existing preset data
            with open(self._settings_path(sel), "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Save it with the new name
            new_path = self._settings_path(new_name)
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
            self._refresh_preset_list()
            self._select_preset_by_name(new_name)
            self._ship_preset_done('duplicated')
            
            # Immediately open edit dialog so user can set proper ship type and build name
            self.after(100, self._edit_selected_preset)
        except Exception as e:
            messagebox.showerror("Duplicate failed", str(e))

    def _export_selected_preset(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            from app_utils import centered_message
            centered_message(self, "No preset selected", "Choose a preset to export.")
            return
        src = self._settings_path(sel)
        if not os.path.exists(src):
            messagebox.showerror("Export failed", "Preset file not found.")
            return
        dest = filedialog.asksaveasfilename(
            title="Export preset",
            initialfile=f"{sel}.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")]
        )
        if not dest:
            return
        try:
            shutil.copy2(src, dest)
            self._ship_preset_done('exported')
        except Exception as e:
            messagebox.showerror("Export failed", str(e))

    def _import_preset_file(self) -> None:
        # Remember last import directory
        if not hasattr(self, '_last_import_dir'):
            self._last_import_dir = self.settings_dir
        
        path = filedialog.askopenfilename(
            title="Import preset (.json)",
            filetypes=[("JSON preset", "*.json"), ("All files", "*.*")],
            initialdir=self._last_import_dir
        )
        if not path:
            return
        
        # Remember the directory for next time
        self._last_import_dir = os.path.dirname(path)
        
        # Read and validate the JSON first
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Import failed", f"Could not read preset file:\n{e}")
            return
        
        # Get the original filename as a hint
        original_name = os.path.splitext(os.path.basename(path))[0]
        
        # Try to auto-detect ship type from original name
        detected_ship, detected_variant = self._parse_preset_ship_type(original_name)
        
        # Ask user to confirm/set ship type and build name
        new_name = self._ask_import_preset_name(detected_ship, detected_variant, original_name)
        if not new_name:
            return
        
        dest = self._settings_path(new_name)
        
        # Check if preset already exists
        if os.path.exists(dest):
            from app_utils import centered_askyesno
            if not centered_askyesno(self, "Preset Exists", 
                                      f"A preset named '{new_name}' already exists.\n\n"
                                      f"Do you want to overwrite it?"):
                return
        
        try:
            # Save with the new name
            with open(dest, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self._refresh_preset_list()
            self._select_preset_by_name(new_name)
            self._ship_preset_done('imported')
        except Exception as e:
            messagebox.showerror("Import preset failed", str(e))

    def _ask_import_preset_name(self, detected_ship: str, detected_variant: str, original_name: str) -> Optional[str]:
        return self._ask_edit_preset_name(detected_ship, detected_variant, original_name, importing=True)
    def _show_preset_menu(self, event) -> None:
        """Show context menu for presets or empty space"""
        try:
            item = self.preset_list.identify_row(event.y)
            
            if not item:
                # Clicked on empty space - show limited menu
                self.preset_list.selection_remove(*self.preset_list.selection())
                self._preset_empty_menu.tk_popup(event.x_root, event.y_root)
                return
            
            # Check if this is a group header (has children)
            children = self.preset_list.get_children(item)
            if children:
                # It's a group header - show limited menu
                self.preset_list.selection_set(item)
                self.preset_list.focus(item)
                self._preset_empty_menu.tk_popup(event.x_root, event.y_root)
                return
            
            # It's a preset - show full menu
            self.preset_list.selection_set(item)
            self.preset_list.focus(item)
            values = self.preset_list.item(item, "values")
            if values:
                self._populate_announcement_preset_submenu(values[0])
                ship_key = self._parse_preset_ship_type(values[0])[0].casefold()
                self._ship_auto_load_var.set(
                    self._load_ship_preset_auto_load().get(ship_key) == values[0])
            self._preset_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._preset_menu.grab_release()
            self._preset_empty_menu.grab_release()

    # ---------- Tooltip preference handling ----------
    def _load_tooltip_preference(self) -> None:
        """Load tooltip enabled state from config"""
        cfg = _load_cfg()
        enabled = cfg.get("tooltips_enabled", True)  # Default to enabled
        self.tooltips_enabled.set(1 if enabled else 0)
        ToolTip.set_enabled(enabled)

    def _save_tooltip_preference(self) -> None:
        """Save tooltip enabled state to config"""
        from config import update_config_value
        update_config_value("tooltips_enabled", bool(self.tooltips_enabled.get()))
    
    def _save_import_prompt_preference(self) -> None:
        """Save import prompt preference to config"""
        from config import update_config_value
        update_config_value("ask_import_on_path_change", bool(self.ask_import_on_path_change.get()))

    def _on_tooltip_toggle(self, *args) -> None:
        """Called when tooltip checkbox is toggled"""
        enabled = bool(self.tooltips_enabled.get())
        ToolTip.set_enabled(enabled)
        self._save_tooltip_preference()

    def _on_main_announcement_toggle(self, *args) -> None:
        """Called when main announcement toggle is changed"""
        # Save the preference
        from config import update_config_value
        update_config_value("main_announcement_enabled", bool(self.main_announcement_enabled.get()))
        
        # The prospector panel will automatically respond to changes through the shared variable
        # No need to explicitly call anything since it's using the same IntVar reference

    def _load_main_announcement_preference(self) -> None:
        """Load main announcement toggle state from config"""
        cfg = _load_cfg()
        enabled = cfg.get("main_announcement_enabled", True)  # Default to enabled
        self.main_announcement_enabled.set(1 if enabled else 0)

    def _load_announcement_settings(self) -> None:
        """Load announcement toggle settings from config.json only"""
        try:
            cfg = _load_cfg()
            announcement_settings = cfg.get("announcements", {})
            
            for name in ANNOUNCEMENT_TOGGLES:
                if name in announcement_settings:
                    try:
                        value = int(announcement_settings[name])
                        self.announcement_vars[name].set(value)
                    except Exception:
                        pass
        except Exception:
            pass

    # ---------- Stay on top preference handling ----------
    def _load_stay_on_top_preference(self) -> None:
        """Load stay on top state from config"""
        cfg = _load_cfg()
        enabled = cfg.get("stay_on_top", False)  # Default to disabled
        self.stay_on_top.set(1 if enabled else 0)
        # Don't apply immediately - will be applied after window is fully created
        # (See _apply_stay_on_top_after_init called in main())
    
    def _apply_stay_on_top_after_init(self) -> None:
        """Apply stay-on-top setting after window is fully initialized"""
        try:
            enabled = bool(self.stay_on_top.get())
            self.wm_attributes("-topmost", enabled)
            if enabled:
                print("[STAY ON TOP] Applied at startup: enabled")
        except Exception as e:
            log.error(f"[STAY ON TOP] Failed to apply at startup: {e}")

    def _save_stay_on_top_preference(self) -> None:
        """Save stay on top state to config"""
        from config import update_config_value
        update_config_value("stay_on_top", bool(self.stay_on_top.get()))

    # ---------- Announcement preference handling ----------
    def _save_announcement_preferences(self) -> None:
        """Save announcement settings to config.json and sync to .txt files for VoiceAttack"""
        try:
            from config import update_config_value
            announcements = {name: var.get() for name, var in self.announcement_vars.items()}
            update_config_value("announcements", announcements)
            
            # Also sync to .txt files for VoiceAttack compatibility (skip items with None filename - config.json only)
            for name, (fname, _help) in ANNOUNCEMENT_TOGGLES.items():
                # Skip items with no txt file (config.json only)
                if fname is None:
                    continue
                    
                base = os.path.splitext(fname)[0]
                value = str(self.announcement_vars[name].get())
                self._write_var_text(base, value)
            
            # Also save material settings to maintain consistency
            if hasattr(self, 'prospector_panel') and self.prospector_panel:
                self.prospector_panel._save_last_material_settings()
        except Exception as e:
            log.error(f"Error saving announcement preferences: {e}")

    def _on_announcement_change(self, *args) -> None:
        """Called when any announcement setting changes - auto-save to config"""
        self._save_announcement_preferences()
        self._ann_update_preset_buttons()

    def _on_stay_on_top_toggle(self, *args) -> None:
        """Called when stay on top checkbox is toggled"""
        enabled = bool(self.stay_on_top.get())
        try:
            self.wm_attributes("-topmost", enabled)
            # Bring window to front without stealing focus (doesn't work perfectly with all apps)
            if enabled:
                self.lift()
                # Don't use focus_force() - it steals focus from the game
            self._save_stay_on_top_preference()
            self._set_status(f"Stay on top {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            log.error(f"Error setting stay on top: {e}")
            self._set_status("Error changing stay on top setting")
    
    def _load_auto_scan_preference(self) -> None:
        """Load auto-scan journals preference from config"""
        cfg = _load_cfg()
        enabled = cfg.get("auto_scan_journals", True)  # Default to enabled
        self.auto_scan_journals.set(1 if enabled else 0)
        print(f"Loaded auto-scan preference: {enabled}")
    
    def _save_auto_scan_preference(self) -> None:
        """Save auto-scan journals preference to config"""
        from config import update_config_value
        update_config_value("auto_scan_journals", bool(self.auto_scan_journals.get()))
        print(f"Saved auto-scan preference: {bool(self.auto_scan_journals.get())}")
    
    def _on_auto_scan_toggle(self, *args) -> None:
        """Called when auto-scan checkbox is toggled"""
        enabled = bool(self.auto_scan_journals.get())
        self._save_auto_scan_preference()
        self._set_status(f"Auto-scan on startup {'enabled' if enabled else 'disabled'}")
    
    def _load_auto_search_preference(self) -> None:
        """Load auto-search hotspots preference from Variables folder (syncs with ring_finder)"""
        try:
            import os
            vars_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Variables")
            auto_search_file = os.path.join(vars_dir, "autoSearch.txt")
            if os.path.exists(auto_search_file):
                with open(auto_search_file, 'r') as f:
                    content = f.read().strip()
                    self.auto_search_enabled.set(content == "1")
                    print(f"Loaded auto-search preference: {content == '1'}")
                    return
        except Exception as e:
            pass
        self.auto_search_enabled.set(False)
        print(f"Loaded auto-search preference: False (default)")
    
    def _record_ui_activity(self, event=None) -> None:
        # Overlays sit over the game as app windows; cursor movement there while
        # the game has focus is not app use and must not block auto switching.
        try:
            if self.focus_get() is None:
                return
        except (KeyError, tk.TclError):
            pass
        self._last_ui_activity = time.monotonic()

    def _can_auto_switch_tabs(self) -> bool:
        if not self.auto_switch_tabs.get():
            return False
        idle = time.monotonic() - self._last_ui_activity
        if idle < 10:
            log.info(f"[AUTO-TAB] Skipped: app used {idle:.0f}s ago (needs 10s idle)")
            return False
        if self.grab_current() is not None:
            log.info("[AUTO-TAB] Skipped: a dialog is open")
            return False
        controls = [getattr(self, name, None) for name in (
            '_marketplace_search_control', '_trade_search_control',
            '_systems_search_control', '_traders_search_control')]
        controls.append(getattr(getattr(self, 'multi_mineral_tab', None), '_search_control', None))
        if any(control is not None and control.running for control in controls):
            log.info("[AUTO-TAB] Skipped: a search is running")
            return False
        if getattr(getattr(self, 'ring_finder', None), '_search_in_progress', False):
            log.info("[AUTO-TAB] Skipped: a Hotspots Finder search is running")
            return False
        return True

    def _load_auto_switch_tabs_preference(self) -> None:
        """Load auto-switch tabs preference from config"""
        cfg = _load_cfg()
        enabled = cfg.get("auto_switch_tabs", True)  # Default to enabled
        self.auto_switch_tabs.set(1 if enabled else 0)
        print(f"Loaded auto-switch tabs preference: {enabled}")
    
    def _save_auto_switch_tabs_preference(self) -> None:
        """Save auto-switch tabs preference to config"""
        from config import update_config_value
        update_config_value("auto_switch_tabs", bool(self.auto_switch_tabs.get()))
        print(f"Saved auto-switch tabs preference: {bool(self.auto_switch_tabs.get())}")
    
    def _on_auto_switch_tabs_toggle(self, *args) -> None:
        """Called when auto-switch tabs checkbox is toggled"""
        enabled = bool(self.auto_switch_tabs.get())
        self._save_auto_switch_tabs_preference()
        self._set_status(f"Auto-switch tabs on ring entry/exit {'enabled' if enabled else 'disabled'}")
        
        # Sync with Ring Finder checkbox if it exists
        if hasattr(self, 'ring_finder') and self.ring_finder:
            if hasattr(self.ring_finder, 'auto_switch_tabs_var'):
                self.ring_finder.auto_switch_tabs_var.set(enabled)
    
    def _on_auto_prices_overlay_toggle(self, *args) -> None:
        """Save Auto Prices overlay preference and sync the Ring Finder checkbox"""
        from config import update_config_value
        enabled = bool(self.auto_prices_overlay.get())
        update_config_value("auto_prices_overlay", enabled)
        ring_finder = getattr(self, 'ring_finder', None)
        if ring_finder and hasattr(ring_finder, 'prices_overlay_var') and ring_finder.prices_overlay_var.get() != enabled:
            ring_finder.prices_overlay_var.set(enabled)

    def _on_auto_prices_overlay_duration_change(self, *args) -> None:
        """Save how long the Auto Prices overlay stays on screen"""
        from config import update_config_value
        duration = int(self.auto_prices_overlay_duration.get())
        update_config_value("auto_prices_overlay_duration", duration)

        # Show a preview message if overlay is enabled to test duration
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(t('settings.auto_prices_duration_preview').format(seconds=duration),
                                           duration_ms=duration * 1000, ignore_sc_hide=True)

    def switch_to_tab(self, tab_name: str) -> None:
        """Switch to a main tab by its key in self._main_tabs (e.g. 'route', 'system_finder')."""
        try:
            frame = getattr(self, '_main_tabs', {}).get(tab_name)
            if frame is not None:
                self.notebook.select(frame)
                log.info(f"[AUTO-TAB] Switched to tab: {tab_name}")
        except Exception as e:
            log.error(f"[AUTO-TAB] Error switching to tab {tab_name}: {e}")
    
    def _load_auto_start_preference(self) -> None:
        """Load auto-start session preference from config"""
        cfg = _load_cfg()
        enabled = cfg.get("auto_start_session", False)  # Default to disabled
        self.auto_start_session.set(1 if enabled else 0)
        print(f"Loaded auto-start session preference: {enabled}")
    
    def _save_auto_start_preference(self) -> None:
        """Save auto-start session preference to config"""
        from config import update_config_value
        update_config_value("auto_start_session", bool(self.auto_start_session.get()))
        print(f"Saved auto-start session preference: {bool(self.auto_start_session.get())}")
    
    def _on_auto_start_toggle(self, *args) -> None:
        """Called when auto-start session checkbox is toggled"""
        enabled = bool(self.auto_start_session.get())
        self._save_auto_start_preference()
        # Auto-start is now handled exclusively by prospector panel via txt files
        # No need to sync from config.json
        
        self._set_status(f"Auto-start session setting handled by prospector panel")

    def _load_prompt_on_full_preference(self) -> None:
        """Load prompt on cargo full preference from config"""
        cfg = _load_cfg()
        enabled = cfg.get("prompt_on_cargo_full", False)  # Default to disabled
        self.prompt_on_cargo_full.set(1 if enabled else 0)
        print(f"Loaded prompt on cargo full preference: {enabled}")
    
    def _save_prompt_on_full_preference(self) -> None:
        """Save prompt on cargo full preference to config"""
        from config import update_config_value
        update_config_value("prompt_on_cargo_full", bool(self.prompt_on_cargo_full.get()))
        print(f"Saved prompt on cargo full preference: {bool(self.prompt_on_cargo_full.get())}")
    
    def _on_prompt_on_full_toggle(self, *args) -> None:
        """Called when prompt on cargo full checkbox is toggled"""
        enabled = bool(self.prompt_on_cargo_full.get())
        self._save_prompt_on_full_preference()
        # Prompt-when-full is now handled exclusively by prospector panel via txt files
        # No need for main.py to interfere with this setting
        
        self._set_status(f"Prompt-when-full setting handled by prospector panel")
    
    def _on_eddn_send_toggle(self) -> None:
        """Called when EDDN send checkbox is toggled"""
        enabled = bool(self.eddn_send_enabled.get())
        if hasattr(self, 'eddn_sender'):
            self.eddn_sender.set_enabled(enabled)
            status_msg = "EDDN sharing enabled - Contributing to community" if enabled else "EDDN sharing disabled"
            self._set_status(status_msg)
            print(f"[OK] {status_msg}")
    
    def _on_api_upload_toggle(self) -> None:
        """Called when API upload checkbox is toggled"""
        enabled = bool(self.api_upload_enabled.get())
        from config import save_api_upload_enabled
        save_api_upload_enabled(enabled)
        self._update_api_status()
        status_msg = "API upload enabled" if enabled else "API upload disabled"
        self._set_status(status_msg)
    
    def _save_api_settings(self) -> None:
        """Save API upload settings to config"""
        from config import save_api_upload_settings
        try:
            settings = {
                "enabled": bool(self.api_upload_enabled.get()),
                "endpoint_url": self.api_endpoint_url.get().strip(),
                "api_key": self.api_key.get().strip(),
                "cmdr_name": self.api_cmdr_name.get().strip()
            }
            save_api_upload_settings(settings)
            self._update_api_status()
            from app_utils import centered_message
            centered_message(self, "Saved", "API upload settings saved successfully!")
        except ValueError as e:
            messagebox.showerror("Error", str(e))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
    
    def _test_api_connection(self) -> None:
        """Test connection to API server without blocking Tk."""
        if getattr(self, '_api_test_in_progress', False):
            return
        from api_uploader import APIUploader
        try:
            self._save_api_settings()
            uploader = APIUploader()
        except Exception as e:
            self._finish_api_connection_test(f"Error: {e}")
            return

        self._api_test_in_progress = True

        def worker():
            try:
                success, message = uploader.test_connection()
                result = f"{'✓' if success else '✗'} {message}"
            except Exception as e:
                result = f"Error: {e}"
            if not getattr(self, '_network_closing', False):
                try:
                    self.after(0, self._finish_api_connection_test, result)
                except (RuntimeError, tk.TclError):
                    pass

        threading.Thread(target=worker, daemon=True).start()

    def _finish_api_connection_test(self, message):
        self._api_test_in_progress = False
        if not getattr(self, '_network_closing', False) and self.winfo_exists():
            from app_utils import centered_message
            centered_message(self, "Connection Test", message)

    def _bulk_upload_api_data(self) -> None:
        """Bulk upload all sessions and hotspots"""
        if not self.api_upload_enabled.get():
            messagebox.showwarning("Upload Disabled", "Please enable API upload first.")
            return
        
        # Confirm action
        from app_utils import centered_askyesno
        result = centered_askyesno(self, "Bulk Upload",
                                   "This will upload all mining sessions and hotspots to the server.\n\n"
                                   "This may take several minutes depending on your data.\n\n"
                                   "Continue?")
        
        if not result:
            return
        
        # TODO: Implement bulk upload in Phase 5
        # For now, show a placeholder
        from app_utils import centered_message
        centered_message(self, "Coming Soon",
                         "Bulk upload functionality will be implemented in Phase 5.\n\n"
                         "For now, new sessions will be uploaded automatically when you end a mining session.")
    
    def _update_api_status(self) -> None:
        """Update API status label"""
        if hasattr(self, 'api_status_label'):
            from config import load_api_upload_settings
            settings = load_api_upload_settings()
            
            if settings["enabled"]:
                # Check if configured
                if settings["api_key"] and settings["cmdr_name"]:
                    self.api_status_label.configure(
                        text="✓ API upload enabled and configured",
                        fg="#00ff00"
                    )
                else:
                    self.api_status_label.configure(
                        text="⚠ API upload enabled but not configured (add CMDR name and API key)",
                        fg="#ffaa00"
                    )
            else:
                self.api_status_label.configure(
                    text="API upload disabled",
                    fg="gray"
                )
    
    def _on_journal_file_change(self, file_path: str):
        """Called when a file in journal directory changes"""
        file_name = os.path.basename(file_path).lower()
        log.debug(f"File watcher triggered for: {file_name}")
        
        # NavRoute.json changed = check if route cleared
        if file_name == 'navroute.json':
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    navroute_data = json.load(f)
                    route = navroute_data.get('Route', [])
                    if len(route) == 0:
                        # Empty route = cleared
                        self._write_jumps_left(0)
                        print("[jumpsleft] NavRoute cleared (empty), set to 0")
                    else:
                        # Route has systems - will be updated by FSDTarget event
                        print(f"[jumpsleft] NavRoute updated ({len(route)} systems)")
            except json.JSONDecodeError:
                # Game truncates the file before rewriting it; the next change event has the real data
                pass
            except Exception as e:
                log.error(f"Error reading NavRoute.json: {e}")
            return
        
        # Process Market.json for EDDN sending
        if file_name == 'market.json' and hasattr(self, 'market_handler'):
            self.market_handler.process_market_file(file_path)
        

    # ---------- Journal folder preference handling ----------
    def _rewatch_journal_dir(self, old_dir, new_dir):
        """Move the Market.json/NavRoute.json watch to a newly selected journal folder"""
        try:
            from file_watcher import get_file_watcher
            watcher = get_file_watcher()
            if old_dir:
                watcher.remove_watch(old_dir)
            if new_dir and os.path.isdir(new_dir):
                watcher.add_watch(new_dir, self._on_journal_file_change)
                self.cargo_monitor.backfill_carrier_names(self.eddn_listener.database_path, new_dir)
        except Exception as e:
            log.error(f"Could not move journal folder watch: {e}")

    def _import_journal_history(self):
        """Import journal history from existing journal files"""
        try:
            journal_dir = self.cargo_monitor.journal_dir
            if not os.path.exists(journal_dir):
                centered_info_dialog(self, t('common.warning'), t('dialogs.journal_dir_not_found'))
                return

            from config import load_theme
            from ui.theme import get_theme_colors
            colors = get_theme_colors(load_theme())

            # Create progress window
            progress = tk.Toplevel(self)
            progress.withdraw()
            progress.title(t('dialogs.importing_journal'))
            progress.resizable(False, False)
            progress.configure(bg=colors["bg"])
            set_window_icon(progress)

            tk.Label(progress, text=t('dialogs.processing_journal_files'), bg=colors["bg"], fg=colors["fg"],
                     font=self._scaled_font(10)).pack(padx=60, pady=(25, 10))
            progress_var = tk.StringVar(value=t('dialogs.import_starting'))
            tk.Label(progress, textvariable=progress_var, bg=colors["bg"], fg=colors["fg_dim"],
                     font=self._scaled_font(9)).pack(padx=60, pady=(0, 25))

            progress.update_idletasks()
            center_window(progress, self)
            progress.deiconify()
            progress.attributes('-topmost', True)
            progress.lift()
            progress.focus_force()
            try:
                progress.grab_set()
            except Exception:
                pass

            def finish(stats, error):
                if progress.winfo_exists():
                    progress.destroy()
                if error is not None:
                    centered_info_dialog(self, t('common.error'), t('dialogs.import_error').format(error=error))
                    return
                centered_info_dialog(self, t('dialogs.import_complete_title'),
                                     t('dialogs.import_complete_body').format(
                                         systems=stats['systems_visited'],
                                         hotspots=stats['hotspots_found'],
                                         files=stats['files_processed']))

            def process_files():
                stats, error = None, None
                try:
                    # Use JournalParser class which already handles everything correctly
                    from journal_parser import JournalParser

                    # Get user_db from cargo_monitor which has it
                    user_db = self.cargo_monitor.user_db if hasattr(self.cargo_monitor, 'user_db') else self.user_db
                    parser = JournalParser(journal_dir, user_db)

                    def progress_callback(current_file, total_files, _stats):
                        text = t('dialogs.import_progress').format(current=current_file, total=total_files)
                        self.after(0, lambda: progress.winfo_exists() and progress_var.set(text))

                    stats = parser.parse_all_journals(progress_callback)
                except Exception as e:
                    log.exception("Journal history import failed")
                    error = e
                self.after(0, finish, stats, error)

            # Run in thread to keep UI responsive
            threading.Thread(target=process_files, daemon=True).start()

        except Exception as e:
            log.exception("Could not start journal history import")
            centered_info_dialog(self, t('common.error'), t('dialogs.import_error').format(error=e))

    def _change_journal_dir(self) -> None:
        """Change the Elite Dangerous journal folder"""
        from tkinter import filedialog
    # import os removed (already imported globally)
        
        # Get current directory from prospector panel if available
        current_dir = None
        if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, 'journal_dir'):
            current_dir = self.prospector_panel.journal_dir
        
        sel = filedialog.askdirectory(
            title="Select Elite Dangerous Journal folder",
            initialdir=current_dir or os.path.expanduser("~")
        )
        
        if sel and os.path.isdir(sel):
            # Update prospector panel if it exists
            if hasattr(self, 'prospector_panel'):
                self.prospector_panel.journal_dir = sel
                self.prospector_panel._journal_attached = False
            
            # Update cargo_monitor to keep them synchronized
            if hasattr(self, 'cargo_monitor'):
                self.cargo_monitor.journal_dir = sel
                # Update dependent paths in cargo_monitor
                self.cargo_monitor.cargo_json_path = os.path.join(sel, "Cargo.json")
                self.cargo_monitor.status_json_path = os.path.join(sel, "Status.json")
            
            self._rewatch_journal_dir(current_dir, sel)

            # Save to config.json so it persists across restarts
            from config import update_config_value
            update_config_value("journal_dir", sel)
            
            # Update the UI label
            if hasattr(self, 'journal_lbl'):
                self.journal_lbl.config(text=sel)
            
            self._set_status("Journal folder updated and saved.")
            
            # Show import prompt (if not disabled)
            self._show_journal_import_prompt(sel)

    def _show_journal_import_prompt(self, new_path: str) -> None:
        """Show dialog asking if user wants to import journal history from new path"""
        from config import _load_cfg, update_config_value
        
        # Check if user disabled this prompt
        cfg = _load_cfg()
        if not cfg.get("ask_import_on_path_change", True):
            return  # User disabled the prompt
        
        # Create modal dialog
        dialog = tk.Toplevel(self)
        dialog.withdraw()  # Hide initially to prevent blinking on wrong monitor
        dialog.title(t('dialogs.import_journal_question'))
        dialog.configure(bg="#2c3e50")
        dialog.geometry("550x350")  # Increased size to accommodate long paths
        dialog.resizable(False, False)
        # dialog.transient(self)  # Disabled - causes focus issues
        
        # Set app icon (consistent across app)
        set_window_icon(dialog)
        
        # CENTER ON PARENT (SAME MONITOR!)
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        dialog.deiconify()  # Show dialog after centering
        
        # Force dialog to stay on top and have focus
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        
        try:
            dialog.grab_set()  # Grab focus after showing
        except:
            pass
        
        # Title label
        title_label = tk.Label(
            dialog, 
            text="Import Journal History?",
            bg="#2c3e50", 
            fg="#ecf0f1", 
            font=self._scaled_font(12, "bold")
        )
        title_label.pack(pady=(20, 10))
        
        # Info text
        info_text = (
            f"You've changed to a new journal folder:\n\n"
            f"{new_path}\n\n"
            f"Would you like to scan these journal files for\n"
            f"hotspot data to add to your database?"
        )
        
        info_label = tk.Label(
            dialog,
            text=info_text,
            bg="#2c3e50",
            fg="#bdc3c7",
            font=self._scaled_font(10),
            justify="center",
            wraplength=500  # Wrap long paths
        )
        info_label.pack(pady=10)
        
        # Checkbox for "don't ask again"
        dont_ask_var = tk.IntVar(value=0)
        checkbox = ThemedCheckbutton(
            dialog,
            text="Don't ask me again when changing paths",
            variable=dont_ask_var,
            bg="#2c3e50",
            fg="#bdc3c7",
            selectcolor="#34495e",
            activebackground="#2c3e50",
            activeforeground="#ecf0f1",
            font=self._scaled_font(9)
        )
        checkbox.pack(pady=10)
        
        # Button frame
        btn_frame = tk.Frame(dialog, bg="#2c3e50")
        btn_frame.pack(pady=20)
        
        result = {"import": False, "dont_ask": False}
        
        def on_import():
            result["import"] = True
            result["dont_ask"] = bool(dont_ask_var.get())
            dialog.destroy()
        
        def on_skip():
            result["import"] = False
            result["dont_ask"] = bool(dont_ask_var.get())
            dialog.destroy()
        
        # Import button
        import_btn = tk.Button(
            btn_frame,
            text="Import Now",
            command=on_import,
            bg="#27ae60",
            fg="white",
            font=self._scaled_font(10, "bold"),
            width=12,
            height=1,
            relief=tk.FLAT,
            cursor="hand2"
        )
        import_btn.pack(side=tk.LEFT, padx=10)
        
        # Skip button
        skip_btn = tk.Button(
            btn_frame,
            text="Skip",
            command=on_skip,
            bg="#95a5a6",
            fg="white",
            font=self._scaled_font(10),
            width=12,
            height=1,
            relief=tk.FLAT,
            cursor="hand2"
        )
        skip_btn.pack(side=tk.LEFT, padx=10)
        
        # Bind Escape key to skip
        dialog.bind('<Escape>', lambda e: on_skip())
        
        # Keep dialog on top while open
        def keep_on_top():
            try:
                if dialog.winfo_exists():
                    dialog.lift()
                    dialog.after(100, keep_on_top)
            except:
                pass
        dialog.after(100, keep_on_top)
        
        # Wait for user response
        dialog.wait_window()
        
        # Save "don't ask again" preference
        if result["dont_ask"]:
            update_config_value("ask_import_on_path_change", False)
        
        # Trigger import if requested
        if result["import"]:
            self._import_journal_history()

    def _update_journal_label(self) -> None:
        """Update the journal folder label in Interface Options"""
        if hasattr(self, 'journal_lbl') and hasattr(self, 'prospector_panel'):
            journal_dir = getattr(self.prospector_panel, 'journal_dir', None)
            
            if journal_dir and os.path.exists(journal_dir):
                # Show the full path
                self.journal_lbl.config(text=journal_dir, fg="#ffffff")
            else:
                self.journal_lbl.config(text="(not set)", fg="gray")
                
    def _set_default_journal_folder(self) -> None:
        """Set the default Elite Dangerous journal folder if it exists"""
        if hasattr(self, 'prospector_panel'):
            # Check common Elite Dangerous journal locations
            possible_dirs = [
                os.path.join(os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous"),
                os.path.join(os.path.expanduser("~"), "Documents", "Frontier Developments", "Elite Dangerous")
            ]
            
            # Check if no journal dir is already set
            current_dir = getattr(self.prospector_panel, 'journal_dir', None)
            
            if not current_dir:
                # Try to find the default directory
                for default_dir in possible_dirs:
                    if os.path.exists(default_dir):
                        self.prospector_panel.journal_dir = default_dir
                        
                        # Also update cargo_monitor if it exists
                        if hasattr(self, 'cargo_monitor'):
                            self.cargo_monitor.journal_dir = default_dir
                            self.cargo_monitor.cargo_json_path = os.path.join(default_dir, "Cargo.json")
                            self.cargo_monitor.status_json_path = os.path.join(default_dir, "Status.json")
                        
                        self._rewatch_journal_dir(None, default_dir)

                        # Save to config
                        from config import update_config_value
                        update_config_value("journal_dir", default_dir)
                        break
                        
            # Always update the label after checking/setting
            self._update_journal_label()
            
    def _change_screenshots_folder(self) -> None:
        """Change the default screenshots folder"""
        try:
            # Start from current folder if set, otherwise use Pictures
            current_folder = self.screenshots_folder_path.get() or os.path.join(os.path.expanduser("~"), "Pictures")
            if not os.path.isdir(current_folder):
                current_folder = os.path.expanduser("~")
                
            folder = filedialog.askdirectory(
                title="Select Default Screenshots folder",
                initialdir=current_folder
            )
            
            if folder:
                self.screenshots_folder_path.set(folder)
                # Update the label text to match new path
                if hasattr(self, 'screenshots_folder_lbl'):
                    self.screenshots_folder_lbl.config(text=folder)
                
                # Save to config
                cfg = _load_cfg()
                cfg['screenshots_folder'] = folder
                _save_cfg(cfg)
                
                self._set_status("Screenshots folder updated.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error updating screenshots folder: {e}")

    # ---------- Text overlay preference handling ----------
    def _load_text_overlay_preference(self) -> None:
        """Load text overlay enabled state and transparency from config"""
        cfg = _load_cfg()
        enabled = cfg.get("text_overlay_enabled", True)  # Default to enabled
        transparency = cfg.get("text_overlay_transparency", 90)  # Default to 90%
        color = cfg.get("text_overlay_color", "White")  # Default to white
        size = cfg.get("text_overlay_size", "Normal")  # Default to normal size
        duration = cfg.get("text_overlay_duration", 7)  # Default to 7 seconds
        overlay_mode = cfg.get("overlay_mode", "enhanced")  # Default to enhanced mode
        show_all = cfg.get("prospector_show_all", False)  # Default to threshold only
        
        self.text_overlay_enabled.set(1 if enabled else 0)
        self.text_overlay_transparency.set(transparency)
        self.text_overlay_color.set(color)
        self.text_overlay_size.set(size)
        self.text_overlay_duration.set(duration)
        self.overlay_mode.set(overlay_mode)
        self.prospector_show_all.set(1 if show_all else 0)
        
        self.text_overlay.set_enabled(enabled)
        self.text_overlay.set_transparency(transparency)
        # Set color after transparency to ensure proper brightness calculation
        color_hex = self.color_options.get(color, "#FFFFFF")
        self.text_overlay.set_color(color_hex)
        # Position is always upper left
        self.text_overlay.set_position("upper_left")
        # Set font size
        size_value = self.size_options.get(size, 14)
        self.text_overlay.set_font_size(size_value)
        # Set display duration
        self.text_overlay.set_display_duration(duration)

        # Sync cargo text overlay with same visual settings
        self.cargo_text_overlay.set_transparency(transparency)
        self.cargo_text_overlay.set_color(color_hex)
        self.cargo_text_overlay.set_font_size(size_value)

    def _save_text_overlay_preference(self) -> None:
        """Save text overlay enabled state, transparency, color, and settings to config"""
        from config import update_config_values
        updates = {
            "text_overlay_enabled": bool(self.text_overlay_enabled.get()),
            "text_overlay_transparency": int(self.text_overlay_transparency.get()),
            "text_overlay_color": str(self.text_overlay_color.get()),
            "text_overlay_size": str(self.text_overlay_size.get()),
            "text_overlay_duration": int(self.text_overlay_duration.get()),
            "overlay_mode": str(self.overlay_mode.get()),
            "prospector_show_all": bool(self.prospector_show_all.get())
        }
        update_config_values(updates)

    def _apply_overlay_enabled_state(self) -> None:
        """Grey out or restore all overlay sub-controls based on the master toggle state."""
        enabled = bool(self.text_overlay_enabled.get())
        state = "normal" if enabled else "disabled"
        fg = "#ffffff" if enabled else "#666666"

        for cb in getattr(self, '_overlay_mode_cbs', []):
            cb.config(state=state, fg=fg)

        if hasattr(self, '_mining_session_cb'):
            self._mining_session_cb.config(state=state, fg=fg)

        if hasattr(self, '_auto_prices_overlay_cb'):
            self._auto_prices_overlay_cb.config(state=state, fg=fg)
        if hasattr(self, '_auto_prices_in_system_cb'):
            self._auto_prices_in_system_cb.config(state=state, fg=fg)

        if hasattr(self, '_sc_checkbox'):
            if not enabled:
                self._sc_checkbox.config(state="disabled", fg="#666666")
            elif self.overlay_only_mining_session.get():
                self._sc_checkbox.config(state="disabled", fg="#666666")
            else:
                self._sc_checkbox.config(state="normal", fg="#ffffff")

        if hasattr(self, 'transparency_scale'):
            self.transparency_scale.config(state=state)
        if hasattr(self, 'duration_scale'):
            self.duration_scale.config(state=state)
        if hasattr(self, 'color_menu'):
            self.color_menu.config(state=state)
        if hasattr(self, 'size_combo'):
            self.size_combo.config(state="normal" if enabled else "disabled")

    def _on_text_overlay_toggle(self, *args) -> None:
        """Called when text overlay checkbox is toggled (master toggle for all overlays)"""
        enabled = bool(self.text_overlay_enabled.get())
        self.text_overlay.set_enabled(enabled)
        # Master toggle: also hide cargo overlay when text overlay is disabled
        if not enabled and hasattr(self, 'cargo_text_overlay'):
            self.cargo_text_overlay.set_enabled(False)
        elif enabled and hasattr(self, 'cargo_text_overlay') and self.cargo_show_in_overlay.get():
            self.cargo_text_overlay.set_enabled(True)
            self.cargo_text_overlay.reinstate()
            self.cargo_text_overlay.update_cargo(self.cargo_monitor)
        self._apply_overlay_enabled_state()
        self._save_text_overlay_preference()
        
    def _on_transparency_change(self, *args) -> None:
        """Called when brightness slider is changed"""
        transparency = int(self.text_overlay_transparency.get())
        self.text_overlay.set_transparency(transparency)
        self.cargo_text_overlay.set_transparency(transparency)
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled to test brightness
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(f"Text Brightness: {transparency}%")

    def _on_color_change(self, *args) -> None:
        """Called when color selection is changed"""
        color_name = self.text_overlay_color.get()
        color_hex = self.color_options.get(color_name, "#FFFFFF")
        self.text_overlay.set_color(color_hex)
        self.cargo_text_overlay.set_color(color_hex)
        self._save_text_overlay_preference()
        
        # Update the option menu button to show the selected color
        self._update_color_menu_display()
        
        # Show a preview message if overlay is enabled to test color
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(f"Color: {color_name}")

    def _on_size_change(self, *args) -> None:
        """Called when text size selection is changed"""
        size_name = self.text_overlay_size.get()
        size_value = self.size_options.get(size_name, 12)
        self.text_overlay.set_font_size(size_value)
        self.cargo_text_overlay.set_font_size(size_value)
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled to test size
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(f"Text Size: {size_name}")

    def _on_duration_change(self, *args) -> None:
        """Called when display duration slider is changed"""
        duration = int(self.text_overlay_duration.get())
        self.text_overlay.set_display_duration(duration)
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled to test duration
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(f"Display Duration: {duration} seconds - This message will stay for {duration} seconds!")

    def _on_overlay_mode_change(self, *args) -> None:
        """Called when overlay mode (standard/enhanced) is changed"""
        mode = self.overlay_mode.get()
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled
        if self.text_overlay.overlay_enabled:
            mode_name = "Enhanced Prospector" if mode == "enhanced" else "Standard Text"
            self.text_overlay.show_message(f"Overlay Mode: {mode_name}")

    def _on_show_all_change(self, *args) -> None:
        """Called when show all materials checkbox is changed"""
        show_all = bool(self.prospector_show_all.get())
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled
        if self.text_overlay.overlay_enabled:
            filter_mode = "All Materials" if show_all else "Threshold Only"
            self.text_overlay.show_message(f"Prospector Filter: {filter_mode}")

    def _update_color_menu_display(self):
        """Redraw the colour swatches so the selected colour is ringed"""
        try:
            self.color_menu.refresh()
        except Exception as e:
            log.error(f"Error updating color menu display: {e}")

    # ---------- Cargo Monitor Methods ----------
    def _load_cargo_preferences(self) -> None:
        """Load cargo monitor preferences from config"""
        cfg = _load_cfg()
        self.cargo_max_capacity.set(cfg.get("cargo_max_capacity", 200))
        self.cargo_show_in_overlay.set(cfg.get("cargo_show_in_overlay", True))
        self.overlay_only_game_focused.set(cfg.get("overlay_only_game_focused", True))
        self.hide_overlays_in_supercruise.set(cfg.get("hide_overlays_in_supercruise", False))
        self.overlay_only_mining_session.set(cfg.get("overlay_only_mining_session", False))
        # Apply saved cargo overlay state
        self.cargo_text_overlay.set_enabled(cfg.get("cargo_show_in_overlay", True))
    
    def _save_cargo_preferences(self) -> None:
        """Save cargo monitor preferences to config"""
        from config import update_config_values
        updates = {
            "cargo_max_capacity": int(self.cargo_max_capacity.get()),
            "cargo_show_in_overlay": bool(self.cargo_show_in_overlay.get()),
            "overlay_only_game_focused": bool(self.overlay_only_game_focused.get()),
            "hide_overlays_in_supercruise": bool(self.hide_overlays_in_supercruise.get()),
            "overlay_only_mining_session": bool(self.overlay_only_mining_session.get())
        }
        update_config_values(updates)

    def _on_cargo_capacity_change(self, *args) -> None:
        """Called when cargo capacity is changed manually in UI"""
        capacity = int(self.cargo_max_capacity.get())
        self.cargo_monitor.set_max_cargo(capacity)
        self._save_cargo_preferences()
    
    def _on_cargo_capacity_detected(self, detected_capacity: int) -> None:
        """Called when CargoMonitor detects cargo capacity from Elite Dangerous"""
        if not hasattr(self, 'cargo_max_capacity'):
            # The startup scan runs before the capacity setting exists; it is applied after the
            # preferences load. Not after(0): splash update() would re-run it forever.
            self._pending_detected_capacity = detected_capacity
            return
        current_capacity = int(self.cargo_max_capacity.get())
        if detected_capacity != current_capacity and detected_capacity > 0:
            # Update the UI setting to match the detected capacity
            self.cargo_max_capacity.set(detected_capacity)
            # Save the detected capacity to config
            self._save_cargo_preferences()
            log.info(f"Auto-updated cargo capacity: {current_capacity}t -> {detected_capacity}t")
    
    def _on_ship_info_changed(self) -> None:
        """Called when CargoMonitor detects ship info change (LoadGame/Loadout events)"""
        self.after(0, self._handle_ship_info_changed)

    def _handle_ship_info_changed(self) -> None:
        if not getattr(self, '_ship_presets_ready', False):
            return
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel._update_ship_info_display()
        ship_key = self._current_ship_preset_key()
        ship_identity = (ship_key, self.cargo_monitor.commander_id, self.cargo_monitor.ship_id)
        previous_ship = getattr(self, '_last_auto_load_ship', None)
        if not ship_key or ship_identity == previous_ship:
            return
        self._last_auto_load_ship = ship_identity
        name = self._load_ship_preset_auto_load().get(ship_key)
        if name and os.path.exists(self._settings_path(name)) and self._load_ship_preset(name):
            previous_ship_key = previous_ship[0] if previous_ship else None
            self._select_preset_by_name(name, collapse_ship_key=previous_ship_key)

    def _current_ship_preset_key(self) -> Optional[str]:
        ship_type = self.cargo_monitor.ship_type
        return self._parse_preset_ship_type(ship_type)[0].casefold() if ship_type else None

    def _load_ship_preset_auto_load(self) -> dict:
        from config import load_ship_preset_auto_load, save_ship_preset_auto_load
        assignments = load_ship_preset_auto_load()
        by_type = {self._parse_preset_ship_type(name)[0].casefold(): name
                   for name in assignments.values()}
        if by_type != assignments:
            save_ship_preset_auto_load(by_type)
        return by_type

    def _toggle_ship_preset_auto_load(self) -> None:
        from config import save_ship_preset_auto_load
        name = self._get_selected_preset()
        if not name:
            return
        ship_key = self._parse_preset_ship_type(name)[0].casefold()
        assignments = self._load_ship_preset_auto_load()
        if self._ship_auto_load_var.get():
            assignments[ship_key] = name
        else:
            assignments.pop(ship_key, None)
        save_ship_preset_auto_load(assignments)

    def _update_ship_auto_load_assignments(self, old_name: str, new_name: Optional[str]) -> None:
        from config import save_ship_preset_auto_load
        assignments = self._load_ship_preset_auto_load()
        for ship_key, name in list(assignments.items()):
            if name == old_name:
                del assignments[ship_key]
                if new_name:
                    assignments[self._parse_preset_ship_type(new_name)[0].casefold()] = new_name
        save_ship_preset_auto_load(assignments)
    

    def _on_cargo_overlay_toggle(self, *args) -> None:
        """Called when cargo monitor overlay checkbox is toggled"""
        enabled = bool(self.cargo_show_in_overlay.get()) and bool(self.text_overlay_enabled.get())
        self.cargo_text_overlay.set_enabled(enabled)
        if enabled:
            self.cargo_text_overlay.reinstate()
            self.cargo_text_overlay.update_cargo(self.cargo_monitor)
        self._save_cargo_preferences()

    def _reapply_cargo_overlay_state(self) -> None:
        """Safety net: re-apply cargo overlay enabled state after full startup.
        Guards against race conditions on first launch after an update where
        the overlay ends up hidden despite being enabled in settings."""
        try:
            if not hasattr(self, 'cargo_text_overlay') or not hasattr(self, 'cargo_show_in_overlay'):
                return
            if _find_game_window_rect() is None:
                return
            if self.cargo_show_in_overlay.get() and self.text_overlay_enabled.get():
                # Don't restore if session-only mode and no session is active
                if self.overlay_only_mining_session.get():
                    session_active = hasattr(self, 'prospector_panel') and self.prospector_panel and getattr(self.prospector_panel, 'session_active', False)
                    if not session_active:
                        return
                self.cargo_text_overlay.set_enabled(True)
                # Reset _game_hidden so the next periodic cycle re-evaluates
                self.cargo_text_overlay._game_hidden = False
                self.cargo_text_overlay._session_hidden = False
                self.cargo_text_overlay.update_cargo(self.cargo_monitor)
        except Exception as e:
            log.debug(f"_reapply_cargo_overlay_state: {e}")

    # ---------- Window geometry save/restore ----------
    def _restore_window_geometry(self) -> None:
        wcfg = load_window_geometry()
        geom = wcfg.get("geometry")
        zoomed = wcfg.get("zoomed", False)
        
        # Default window size - larger for better first-run experience
        DEFAULT_WIDTH = 1350
        DEFAULT_HEIGHT = 780
        
        # Old default size (upgrade users from old default)
        OLD_DEFAULT_WIDTH = 1220
        OLD_DEFAULT_HEIGHT = 700
        
        if geom:
            try:
                # Parse geometry string: WIDTHxHEIGHT+X+Y
                import re
                match = re.match(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', geom)
                if match:
                    width, height, x, y = map(int, match.groups())

                    # Upgrade old default size to new default size
                    if width == OLD_DEFAULT_WIDTH and height == OLD_DEFAULT_HEIGHT:
                        print(f"[WINDOW] Upgrading old default size to new: {DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
                        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT

                    # If UI scale changed since geometry was last saved, scale window size to match
                    from config import load_ui_scale
                    saved_scale = wcfg.get("ui_scale", 1.0)
                    current_scale = load_ui_scale()
                    if saved_scale and current_scale and saved_scale != current_scale:
                        ratio = current_scale / saved_scale
                        width = round(width * ratio)
                        height = round(height * ratio)
                        # Keep the window on-screen after scaling up
                        screen_width = self.winfo_screenwidth()
                        screen_height = self.winfo_screenheight()
                        width = min(width, screen_width)
                        height = min(height, screen_height)
                        # Remember the ratio so saved sash positions (also stored
                        # as absolute pixels) can be rescaled to match.
                        self._ui_scale_resize_ratio = ratio

                    # For multi-monitor setups, allow negative and large positive coordinates
                    # Only reset if window is EXTREMELY far off-screen (likely corrupt data)
                    # Allow coordinates up to 10000 pixels in any direction for multi-monitor
                    if x < -10000 or x > 10000 or y < -10000 or y > 10000:
                        # Position is corrupt, center on primary screen
                        screen_width = self.winfo_screenwidth()
                        screen_height = self.winfo_screenheight()
                        x = (screen_width - width) // 2
                        y = (screen_height - height) // 2
                        geom = f"{width}x{height}+{x}+{y}"
                    else:
                        geom = f"{width}x{height}+{x}+{y}"
                    
                    self.geometry(geom)
                else:
                    # Geometry string doesn't have position, use default centered
                    self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
                    self.update_idletasks()
                    screen_width = self.winfo_screenwidth()
                    screen_height = self.winfo_screenheight()
                    x = (screen_width - DEFAULT_WIDTH) // 2
                    y = (screen_height - DEFAULT_HEIGHT) // 2
                    self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+{x}+{y}")
                
                # Restore zoomed/maximized state
                if zoomed:
                    self.state("zoomed")
                    
                # Show window after geometry is set - without stealing focus from game
                self.attributes('-topmost', False)
                self.deiconify()
                
                # On Windows, try to show without activating (prevent focus steal)
                try:
                    import ctypes
                    hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                    SW_SHOWNOACTIVATE = 4
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                except:
                    pass
            except Exception:
                # If saved geometry fails, center on screen with default size
                self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
                self.update_idletasks()
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                x = (screen_width - DEFAULT_WIDTH) // 2
                y = (screen_height - DEFAULT_HEIGHT) // 2
                self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+{x}+{y}")
                self.attributes('-topmost', False)
                self.deiconify()
                try:
                    import ctypes
                    hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                    SW_SHOWNOACTIVATE = 4
                    ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
                except:
                    pass
        else:
            print(f"[DEBUG] No saved geometry, using defaults")
            # No saved geometry, center on screen with default size
            self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
            self.update_idletasks()
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = (screen_width - DEFAULT_WIDTH) // 2
            y = (screen_height - DEFAULT_HEIGHT) // 2
            self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+{x}+{y}")
            
            # Show window after geometry is set - without stealing focus
            self.attributes('-topmost', False)
            self.deiconify()
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                SW_SHOWNOACTIVATE = 4
                ctypes.windll.user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            except:
                pass
        
        # After window shown, clear text selections (but don't focus - would steal from game)
        try:
            self.after(150, lambda: (self.ring_finder.system_entry.selection_clear() if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_entry') else None))
            self.after(150, lambda: (self.sysfinder_ref_entry.selection_clear() if hasattr(self, 'sysfinder_ref_entry') else None))
        except Exception:
            pass
        self.after(50, lambda: self.state("zoomed") if zoomed else None)

    def _check_config_migration(self):
        """Check if config needs migration and perform it if necessary"""
        import logging
        from datetime import datetime
        
        log = logging.getLogger("EliteMining.Migration")
        
        try:
            from config import _load_cfg, needs_config_migration, migrate_config, _save_cfg, CONFIG_FILE
            
            # Log migration check start
            log.info(f"=== CONFIG MIGRATION CHECK START === {datetime.now().isoformat()}")
            log.info(f"Config file path: {CONFIG_FILE}")
            
            cfg = _load_cfg()
            current_version = cfg.get("config_version", "0.0.0")
            log.info(f"Current config version: {current_version}")
            
            if needs_config_migration(cfg):
                log.info(f"Migration needed from {current_version}")
                
                # Create backup
                import shutil
                backup_path = CONFIG_FILE + f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    shutil.copy2(CONFIG_FILE, backup_path)
                    log.info(f"Config backup created: {backup_path}")
                except Exception as backup_error:
                    log.error(f"Failed to create backup: {backup_error}")
                
                # Perform migration
                migrated_cfg = migrate_config(cfg)
                log.info(f"About to save migrated config to: {CONFIG_FILE}")
                _save_cfg(migrated_cfg)
                log.info(f"Config saved successfully")
                
                # Clear config cache to force fresh reload
                import config
                config._cached_config = {}
                config._last_load_time = 0
                log.info(f"Config cache cleared to force fresh reload")
                
                new_version = migrated_cfg.get("config_version", "unknown")
                log.info(f"Config successfully migrated from {current_version} to {new_version}")
                
                # Add small delay before verification
                import time
                time.sleep(0.1)
                
                # Verify migration
                log.info(f"Verifying migration by reading from: {CONFIG_FILE}")
                verification_cfg = _load_cfg()
                verification_version = verification_cfg.get("config_version", "failed")
                if verification_version == new_version:
                    log.info(f"Migration verification successful: {verification_version}")
                else:
                    log.error(f"Migration verification failed: expected {new_version}, got {verification_version}")
                    log.error(f"Verification read from: {CONFIG_FILE}")
                    
            else:
                log.info(f"Config is up to date at version {current_version}")
            
            # Also run layout migration (separate from config version migration)
            try:
                from config import migrate_layout_settings
                migrate_layout_settings()
            except Exception as layout_error:
                log.warning(f"Layout migration failed: {layout_error}")
                
            log.info(f"=== CONFIG MIGRATION CHECK END === {datetime.now().isoformat()}")

            # Database migrations are scheduled from _dismiss_splash(), after window
            # geometry is restored - centering dialogs on self here would use stale geometry

        except Exception as e:
            log.error(f"Config migration check failed: {e}", exc_info=True)
            # Continue startup even if migration fails

    def _show_startup_dialog(self, dialog_fn, *args, **kwargs):
        """Run a blocking startup dialog while flagging it active, so other
        startup flows (e.g. VA profile update) can wait for it to close first."""
        self._startup_dialog_active = True
        try:
            return dialog_fn(*args, **kwargs)
        finally:
            self._startup_dialog_active = False

    def _run_database_migrations(self):
        """Run any pending database migrations"""
        import logging
        log = logging.getLogger("EliteMining.Migration")
        
        try:
            # Import all migrations
            from migrations.fix_metalic_typo import (
                is_migration_needed as metalic_needed,
                get_database_path,
                run_migration as run_metalic_migration
            )
            
            db_path = get_database_path()
            
            # Run Metalic typo fix migration (v4.82)
            if metalic_needed(db_path):
                log.info("[MIGRATION] Running 'Metalic' typo fix...")
                success = run_metalic_migration(db_path)
                if success:
                    log.info("[MIGRATION] ✓ 'Metalic' typo fix completed")
                    print("[MIGRATION v4.82] Fixed 'Metalic' -> 'Metallic' typo in database")
                else:
                    log.warning("[MIGRATION] 'Metalic' typo fix failed")
            else:
                log.debug("[MIGRATION] 'Metalic' typo fix not needed or already applied")

            # Show a one-time notice if the hotspot dataset merge (user_database.py) added new hotspots
            try:
                notice = getattr(self.cargo_monitor.user_db, 'last_hotspot_merge_notice', None)
                if notice:
                    backup_line = f"\n\nA backup of your previous database was saved to:\n{notice['backup_path']}" if notice.get('backup_path') else ""
                    self._show_startup_dialog(
                        centered_info_dialog,
                        self,
                        "Hotspot Database Updated",
                        f"Added {notice['inserted']} new community hotspots to your database.\n"
                        f"Your existing hotspots and visit history were not changed.{backup_line}"
                    )
                    self.cargo_monitor.user_db.last_hotspot_merge_notice = None
            except Exception as notice_error:
                log.warning(f"Could not show hotspot merge notice: {notice_error}")

        except Exception as e:
            log.error(f"Database migrations failed: {e}", exc_info=True)
            # Continue startup even if migration fails

    def _run_database_migrations_old(self):
        """Run any pending database migrations with progress dialog (OLD - DISABLED)"""
        import logging
        log = logging.getLogger("EliteMining.Migration")
        
        try:
            from migrations.fix_visit_counts import is_migration_needed, get_database_path, run_migration
            from app_utils import get_app_icon_path
            
            db_path = get_database_path()
            
            # Check if migration is needed before showing dialog
            if not is_migration_needed(db_path):
                log.info("No database migrations needed")
                return
            
            log.info("Database migration needed, showing progress dialog...")
            
            # Ensure main window is updated before creating dialog
            self.update_idletasks()
            
            # Create progress dialog - use center_window for proper positioning
            progress_dialog = tk.Toplevel(self)
            progress_dialog.withdraw()  # Hide until positioned
            progress_dialog.title(t('dialogs.database_update'))
            progress_dialog.transient(self)
            progress_dialog.resizable(False, False)
            progress_dialog.configure(bg="#2c3e50")
            
            # Set app icon
            try:
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    progress_dialog.iconbitmap(icon_path)
            except Exception:
                pass
            
            # Dialog content frame
            frame = ttk.Frame(progress_dialog, padding=20)
            frame.pack(fill="both", expand=True)
            
            # Title label
            ttk.Label(
                frame, 
                text="Updating Database (one-time migration)",
                font=self._scaled_font(11, "bold")
            ).pack(pady=(0, 15))
            
            # Status label
            status_var = tk.StringVar(value="Initializing...")
            ttk.Label(
                frame,
                textvariable=status_var,
                font=self._scaled_font(9)
            ).pack(pady=(0, 10))
            
            # Progress bar
            progress_bar = ttk.Progressbar(
                frame, 
                length=350, 
                mode='determinate'
            )
            progress_bar.pack(pady=(0, 10))
            
            # Center dialog on parent window (main app)
            # Force update to get accurate geometry
            self.update()
            progress_dialog.update_idletasks()
            
            # Get main window position and size
            main_x = self.winfo_x()
            main_y = self.winfo_y()
            main_width = self.winfo_width()
            main_height = self.winfo_height()
            
            # Get dialog size
            dialog_width = progress_dialog.winfo_reqwidth()
            dialog_height = progress_dialog.winfo_reqheight()
            
            # Calculate centered position
            x = main_x + (main_width - dialog_width) // 2
            y = main_y + (main_height - dialog_height) // 2
            
            # Apply position
            progress_dialog.geometry(f"+{x}+{y}")
            
            # Show dialog
            progress_dialog.deiconify()
            progress_dialog.lift()
            progress_dialog.focus_force()
            progress_dialog.grab_set()
            progress_dialog.update()
            
            # Progress callback
            def update_progress(current, total, message):
                progress_bar['value'] = current
                status_var.set(message)
                progress_dialog.update()
            
            # Run migration
            success, message = run_migration(update_progress)
            
            if success:
                log.info(f"Database migration completed: {message}")
                # Mark that migration completed - background scan can skip redundant work
                self._migration_completed = True
            else:
                log.warning(f"Database migration issue: {message}")
            
            # Close dialog
            progress_dialog.grab_release()
            progress_dialog.destroy()
            
            # Notify user about changes
            if success and "Fixed" in message:
                # Check if running as frozen exe (installed version)
                import sys
                if getattr(sys, 'frozen', False):
                    # Installed version - don't auto-restart (causes Tcl/Tk issues)
                    centered_info_dialog(
                        self,
                        "Database Updated",
                        "Visit counts have been corrected.\n\n"
                        "Please restart EliteMining to apply changes."
                    )
                else:
                    # Dev version - can restart safely
                    restart = centered_yesno_dialog(
                        self,
                        "Database Updated",
                        "Visit counts have been corrected.\n\n"
                        "Restart EliteMining now to apply changes?"
                    )
                    if restart:
                        self._restart_app()
                
        except ImportError:
            # Migration module not found - skip silently
            log.debug("Migration module not found, skipping")
        except Exception as e:
            log.error(f"Database migration failed: {e}")
            # Try to close dialog if it exists
            try:
                progress_dialog.grab_release()
                progress_dialog.destroy()
            except:
                pass
            # Continue startup even if migration fails

    def _constrain_sidebar_width(self, position=None):
        if len(self.main_paned.panes()) < 2:
            return
        total_width = self.main_paned.winfo_width()
        if total_width < 400:
            return
        min_width = self._scaled_px(280)
        max_width = min(self._scaled_px(500), max(min_width, total_width - 600))
        if position is None:
            position = self.main_paned.sashpos(0)
        position = min(max(position, total_width - max_width), total_width - min_width)
        self.main_paned.sashpos(0, position)
        self._last_sidebar_width = total_width - position
        return position

    def _sidebar_sash_position(self, position):
        # Keep saved heights tied to the same pane when the order is reversed.
        if self._sidebar_cargo_on_top != self._sidebar_default_cargo_on_top:
            return self.sidebar_paned.winfo_height() - position
        return position

    def _swap_sidebar_panes(self) -> None:
        from config import save_sidebar_cargo_on_top
        paned = self.sidebar_paned
        position = paned.sashpos(0)
        height = paned.winfo_height()
        self._sidebar_cargo_on_top = not self._sidebar_cargo_on_top
        top_pane = self._cargo_pane if self._sidebar_cargo_on_top else self._presets_pane
        paned.insert(0, top_pane)
        paned.update_idletasks()
        paned.sashpos(0, height - position)
        save_sidebar_cargo_on_top(self._sidebar_cargo_on_top)
        self._save_sash_positions_now()

    def _show_sidebar_menu(self) -> None:
        tc = self.theme_colors
        menu = tk.Menu(self, tearoff=0, bg=tc["bg_accent"], fg=tc["fg"],
                       activebackground=tc["selection_bg"], activeforeground=tc["selection_fg"],
                       bd=0, relief="flat", font=self._scaled_font(9))
        key = 'sidebar.hide_sidebar' if self._sidebar_visible else 'sidebar.show_sidebar'
        menu.add_command(label=t(key), command=self._toggle_sidebar_visibility)
        menu.add_command(label=t('sidebar.swap_panels'), command=self._swap_sidebar_panes,
                         state=tk.NORMAL if self._sidebar_visible else tk.DISABLED)
        button = self.sidebar_toggle_btn
        x = button.winfo_rootx()
        y = button.winfo_rooty() - menu.yposition(tk.END) - 30 if button.winfo_rooty() > 300 else button.winfo_rooty() + button.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _toggle_sidebar_visibility(self) -> None:
        """Show or hide the Ship Presets + Cargo Monitor sidebar column"""
        if self._sidebar_visible:
            try:
                from config import save_main_sash_position
                self._sidebar_last_sash_pos = self._constrain_sidebar_width()
                if self._sidebar_last_sash_pos is not None:
                    save_main_sash_position(self._sidebar_last_sash_pos)
            except Exception:
                self._sidebar_last_sash_pos = None
            self.main_paned.forget(self._sidebar_frame)
            self._sidebar_visible = False
        else:
            sidebar_width = getattr(self, '_last_sidebar_width', self._scaled_px(300))

            # Use the last actual width instead of the children's wider size request on reinsert.
            self._sidebar_frame.grid_propagate(False)
            self._sidebar_frame.configure(width=self._sidebar_frame.winfo_width())
            self.main_paned.add(self._sidebar_frame, weight=0)
            self._sidebar_visible = True
            self.main_paned.update_idletasks()
            self._constrain_sidebar_width(self.main_paned.winfo_width() - sidebar_width)
            self.main_paned.pane(self._sidebar_frame, weight=1)
            self._sidebar_frame.grid_propagate(True)
            self.main_paned.update_idletasks()

    _MODERN_REMAP = {"#1e1e1e": modern_color("#14171B"), "#1a1a1a": modern_color("#14171B"), "#2d2d2d": modern_color("#1D2228"), "#2b2b2b": modern_color("#1D2228"),
                     "#252525": modern_color("#1D2228"), "#282828": modern_color("#1D2228"), "#2a2a2a": modern_color("#1D2228"),
                     "#444444": modern_color("#343B44"), "#333333": modern_color("#2A3038"), "#3a3a3a": modern_color("#2A3038"),
                     "#2e2e2e": modern_color("#232A31"), "#4a4a4a": modern_color("#323941"),
                     "#2c3e50": modern_color("#1D2228"), "#34495e": modern_color("#2A3038")}
    _MODERN_CONTENT_CLASSES = ("Text", "Listbox", "Entry", "Spinbox")
    _MODERN_RECOLOR_CLASSES = ("Frame", "Label", "Labelframe", "Checkbutton", "Radiobutton", "Canvas",
                               "Text", "Listbox", "Entry", "Spinbox", "Toplevel", "Scale", "Message", "Menubutton")
    _MODERN_COLOR_OPTIONS = ("bg", "activebackground", "selectcolor", "troughcolor", "highlightbackground",
                             "buttonbackground", "disabledbackground", "readonlybackground")

    _MODERN_TREE_TAG_REMAP = {"#1e1e1e": modern_color("#1D2228"), "#252525": modern_color("#232A31"), "#282828": modern_color("#232A31"),
                              "#2a2a2a": modern_color("#232A31"), "#2d2d2d": modern_color("#232A31")}

    def _modern_restyle_trees(self, trees) -> None:
        """Treeview colors live in ttk styles, so restyle each distinct style used by a tree once."""
        style = ttk.Style()
        seen = set()
        for tree in trees:
            name = str(tree.cget("style")) or "Treeview"
            if name not in seen:
                seen.add(name)
                try:
                    style.configure(name, background=modern_color("#1D2228"), fieldbackground=modern_color("#1D2228"), foreground=modern_color("#E6EAF0"),
                                    bordercolor=modern_color("#343B44"), lightcolor=modern_color("#343B44"), darkcolor=modern_color("#343B44"))
                    style.configure(name + ".Heading", background=modern_color("#14171B"), foreground=modern_color("#E6EAF0"),
                                    relief="groove", borderwidth=1,
                                    bordercolor=modern_color("#343B44"), lightcolor=modern_color("#343B44"), darkcolor=modern_color("#343B44"))
                    style.map(name, background=[("selected", modern_color("#4A3520"))], foreground=[("selected", "#FFFFFF")])
                except tk.TclError:
                    pass
            for tag in ("oddrow", "evenrow", "oddrow_spansh", "evenrow_spansh"):
                try:
                    cur = str(tree.tag_configure(tag, "background")).lower()
                except (tk.TclError, AttributeError):
                    continue
                new = self._MODERN_TREE_TAG_REMAP.get(cur)
                if new:
                    try:
                        tree.tag_configure(tag, background=new)
                    except tk.TclError:
                        pass

    def _modern_recolor_all(self, root=None) -> None:
        """Modern theme: remap leftover hardcoded dark-gray backgrounds on classic tk widgets
        (tabs/dialogs that still use inline colors) to the Modern palette. Exact-match only."""
        trees = []

        def walk(widget):
            for child in widget.winfo_children():
                try:
                    cls = child.winfo_class()
                    if cls == "Treeview":
                        trees.append(child)
                    if cls in ("Label", "TLabel"):
                        # Yellow value text becomes the Modern orange accent (exact yellows only)
                        for opt in ("fg", "foreground"):
                            try:
                                color = str(child.cget(opt)).lower()
                                if color in ("#ffcc00", "#ffd700") or (self.current_theme == "modern_orange" and
                                        color in ("white", "#ffffff", "#e0e0e0", "#e6e6e6", "#e6eaf0")):
                                    child.configure(**{opt: modern_color("#FF9A32")})
                            except tk.TclError:
                                pass
                    if cls in ("Checkbutton", "Radiobutton") and self.current_theme == "modern_orange":
                        try:
                            if str(child.cget("fg")).lower() in ("white", "#ffffff", "#e0e0e0", "#e6e6e6", "#e6eaf0"):
                                child.configure(fg=modern_color("#FF9A32"))
                        except tk.TclError:
                            pass
                    if cls == "Labelframe":
                        try:
                            child.configure(relief="flat", bd=0, highlightthickness=1,
                                            highlightbackground=modern_color("#343B44"), highlightcolor=modern_color("#343B44"))
                        except tk.TclError:
                            pass
                    if cls == "TLabel":
                        try:
                            if str(child.cget("background")).lower() in self._MODERN_REMAP:
                                try:
                                    _pbg = str(child.master.cget("bg"))
                                except (tk.TclError, AttributeError):
                                    _pbg = modern_color("#14171B")
                                child.configure(background=_pbg)
                        except tk.TclError:
                            pass
                    if cls == "Scale":
                        try:
                            child.configure(troughcolor=modern_color("#434B55"), activebackground=modern_color("#FF9A32"),
                                            sliderrelief="raised", bd=2)
                        except tk.TclError:
                            pass
                    if cls in ("Spinbox", "Entry", "Text", "Listbox"):
                        for opt, old, new in (("highlightbackground", "#ffffff", modern_color("#343B44")),
                                              ("highlightbackground", "#000000", modern_color("#343B44")),
                                              ("highlightcolor", "#ffffff", modern_color("#FF9A32"))):
                            try:
                                if str(child.cget(opt)).lower() == old:
                                    child.configure(**{opt: new})
                            except tk.TclError:
                                pass
                    if cls in self._MODERN_RECOLOR_CLASSES:
                        content = cls in self._MODERN_CONTENT_CLASSES
                        for opt in self._MODERN_COLOR_OPTIONS:
                            try:
                                cur = str(child.cget(opt)).lower()
                            except tk.TclError:
                                continue
                            new = self._MODERN_REMAP.get(cur)
                            if new:
                                if content and cur == "#1e1e1e":
                                    new = modern_color("#1D2228")
                                child.configure(**{opt: new})
                    walk(child)
                except tk.TclError:
                    continue
        try:
            walk(root or self)
            self._modern_restyle_trees(trees)
        except Exception:
            log.exception("Modern recolor failed")

    def _update_footer_indicator(self, kind: str, status: str) -> None:
        if not hasattr(self, '_footer_services_label'):
            return
        self._footer_service_statuses[kind] = status
        statuses = self._footer_service_statuses.values()
        if 'checking' in statuses:
            overall, color = 'checking', '#888888'
        elif all(value == 'online' for value in statuses):
            overall, color = 'online', '#4FB87A'
        elif all(value == 'offline' for value in statuses):
            overall, color = 'offline', '#C06060'
        else:
            overall, color = 'partial', '#D9A441'
        self._footer_services_label.config(
            text=t('status_bar.services_' + overall), fg=color)
        self._footer_services_tip.text = '\n'.join(
            t('system_finder.service_' + value).format(service=service)
            for key, service in (('eddn', 'EDDN'), ('spansh', 'Spansh'),
                                 ('market', t('status_bar.market_api')))
            for value in (self._footer_service_statuses[key],))
        window = self._footer_services_tip.tooltip_window
        if window is not None:
            for label in window.winfo_children():
                label.config(text=self._footer_services_tip.text)

    def _show_service_status(self, event=None) -> None:
        self._footer_services_tip.on_leave()
        centered_info_dialog(self, t('status_bar.service_status'), self._footer_services_tip.text)

    _THEME_STR_KEYS = {"elite_orange": "orange_theme", "dark_gray": "dark_theme", "modern": "modern_theme", "modern_slate": "modern_slate_theme", "modern_orange": "modern_orange_theme"}

    def _apply_modern_styles(self, style, theme, _scaled_font, _scaled_px) -> None:
        """Extra ttk styling for the Modern theme only (flat tabs with orange underline, flat tables)."""
        bg, panel, border = theme["bg"], theme["panel"], theme["border"]
        fg, accent = theme["fg"], theme["accent"]

        def _tab_img(underline):
            img = tk.PhotoImage(width=8, height=8)
            img.put(panel if underline else bg, to=(0, 0, 8, 8))
            if underline:
                img.put(accent, to=(0, 5, 8, 8))
            return img
        self._modern_tab_imgs = (_tab_img(False), _tab_img(True))
        try:
            style.element_create("Modern.Tab.bg", "image", self._modern_tab_imgs[0],
                                 ("selected", self._modern_tab_imgs[1]), border=(0, 0, 0, 3), sticky="nswe")
            style.layout("TNotebook.Tab", [("Modern.Tab.bg", {"sticky": "nswe", "children": [
                ("Notebook.padding", {"side": "top", "sticky": "nswe", "children": [
                    ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
        except tk.TclError as e:
            log.warning(f"Modern tab layout failed: {e}")

        style.configure("TNotebook", background=bg, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure("TNotebook.Tab", background=bg, foreground=theme["fg_dim"], borderwidth=0,
                        padding=[_scaled_px(8), _scaled_px(6)], font=_scaled_font(9))
        style.map("TNotebook.Tab",
                  foreground=[("selected", "#FFFFFF"), ("active", fg)],
                  background=[("selected", panel), ("active", panel)],
                  expand=[("selected", [0, 0, 0, 0])])

        style.configure("Treeview", background=theme["tree_bg"], fieldbackground=theme["tree_bg"],
                        foreground=fg, borderwidth=0, rowheight=_scaled_px(26))
        style.configure("Treeview.Heading", background=bg, foreground=fg, relief="groove",
                        borderwidth=1, padding=(_scaled_px(6), _scaled_px(5)), font=_scaled_font(9, "bold"))
        style.map("Treeview.Heading", background=[("active", theme["btn_bg_hover"])])
        style.configure("TCombobox", fieldbackground=panel, background=theme["btn_bg"], foreground=fg,
                        bordercolor=border, lightcolor=border, darkcolor=border, arrowcolor=fg)
        style.map("TCombobox", fieldbackground=[("readonly", panel), ("disabled", bg)])
        style.configure("TEntry", fieldbackground=panel, foreground=fg, bordercolor=border,
                        lightcolor=border, darkcolor=border, insertcolor=fg)
        style.configure("TButton", background=theme["btn_bg"], foreground=fg, bordercolor=border,
                        lightcolor=theme["btn_bg"], darkcolor=theme["btn_bg"], focuscolor=theme["btn_bg"],
                        relief="flat", padding=(_scaled_px(10), _scaled_px(4)))
        style.map("TButton", background=[("active", theme["btn_bg_hover"]), ("disabled", panel)],
                  foreground=[("disabled", theme["btn_fg_disabled"])])
        style.configure("Accent.TButton", background=accent, foreground=theme["accent_fg"], bordercolor=accent,
                        lightcolor=accent, darkcolor=accent, relief="flat", font=_scaled_font(10, "bold"),
                        padding=(_scaled_px(16), _scaled_px(5)))
        style.map("Accent.TButton", background=[("active", modern_color("#FFB05A")), ("pressed", modern_color("#E88A28"))],
                  foreground=[("active", theme["accent_fg"]), ("pressed", theme["accent_fg"])])
        style.configure("TCheckbutton", background=bg, foreground=fg)
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure("Modern.Cargo.Horizontal.TProgressbar", troughcolor=modern_color("#2A3038"), background=accent,
                        bordercolor=bg, lightcolor=accent, darkcolor=accent, thickness=_scaled_px(8))
        for _orient in ("Vertical", "Horizontal"):
            style.configure(_orient + ".TScrollbar", background=modern_color("#323941"), troughcolor=panel, bordercolor=panel,
                            lightcolor=modern_color("#323941"), darkcolor=modern_color("#323941"), arrowcolor=fg)
            style.configure(_orient + ".Scrollbar.thumb", background=modern_color("#323941"))
            style.map(_orient + ".TScrollbar", background=[("active", modern_color("#434B55"))],
                      lightcolor=[("active", modern_color("#434B55"))], darkcolor=[("active", modern_color("#434B55"))])
            style.map(_orient + ".Scrollbar.thumb", background=[("active", modern_color("#434B55"))])

        # Subtle borders instead of clam's bright light/dark edges
        for _name in ("TFrame", "TNotebook", "Treeview", "Treeview.Heading", "TEntry", "TCombobox"):
            style.configure(_name, bordercolor=border, lightcolor=border, darkcolor=border)
        style.configure("TLabelframe", background=bg, bordercolor=border, lightcolor=border, darkcolor=border)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)

        # Rounded ttk buttons (neutral + accent), 9-slice images per state
        try:
            from ui.modern_widgets import make_pill_image
            self._modern_btn_imgs = {
                "n": make_pill_image(theme["btn_bg"], border), "a": make_pill_image(theme["btn_bg_hover"], accent),
                "p": make_pill_image(modern_color("#1D2228"), accent), "d": make_pill_image(panel, border),
                "an": make_pill_image(accent, accent), "aa": make_pill_image(modern_color("#FFB05A"), modern_color("#FFB05A")),
                "ap": make_pill_image(modern_color("#E88A28"), modern_color("#E88A28")),
            }
            im = self._modern_btn_imgs
            style.element_create("Modern.Button.bg", "image", im["n"], ("disabled", im["d"]), ("pressed", im["p"]),
                                 ("active", im["a"]), border=(6, 6, 6, 6), padding=(0, 0, 0, 0), sticky="nswe")
            style.element_create("Modern.AccentButton.bg", "image", im["an"], ("pressed", im["ap"]),
                                 ("active", im["aa"]), border=(6, 6, 6, 6), padding=(0, 0, 0, 0), sticky="nswe")
            for _sname, _el in (("TButton", "Modern.Button.bg"), ("Accent.TButton", "Modern.AccentButton.bg")):
                style.layout(_sname, [(_el, {"sticky": "nswe", "children": [
                    ("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})]})])
        except Exception as e:
            log.warning(f"Modern rounded ttk buttons failed: {e}")

        # Rounded LabelFrame border (9-slice image, transparent outside the corners)
        try:
            from PIL import Image, ImageDraw, ImageTk

            def _rgb(hex_color):
                h = hex_color.lstrip("#")
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            size, radius, scale = 24, 6, 4
            big = size * scale
            mask = Image.new("L", (big, big), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, big - 1, big - 1), radius=radius * scale, fill=255)
            inner = Image.new("L", (big, big), 0)
            ImageDraw.Draw(inner).rounded_rectangle((scale, scale, big - 1 - scale, big - 1 - scale),
                                                    radius=radius * scale - scale, fill=255)
            img = Image.new("RGBA", (big, big), _rgb(border) + (255,))
            img.paste(_rgb(bg) + (255,), mask=inner)
            img.putalpha(mask)
            img = img.resize((size, size), Image.LANCZOS)
            self._modern_frame_img = ImageTk.PhotoImage(img)
            style.element_create("Modern.Labelframe.border", "image", self._modern_frame_img,
                                 border=(radius, radius, radius, radius), padding=(3, 3, 3, 3), sticky="nswe")
            style.layout("TLabelframe", [("Modern.Labelframe.border", {"sticky": "nswe"})])
        except Exception as e:
            log.warning(f"Modern rounded frame failed: {e}")

    def _show_theme_menu(self, button) -> None:
        """Pop up a menu listing all themes above/below the clicked button"""
        from ui.theme import THEME_ORDER
        tc = self.theme_colors
        menu = tk.Menu(self, tearoff=0, bg=tc["bg_accent"], fg=tc["fg"],
                       activebackground=tc["selection_bg"], activeforeground=tc["selection_fg"],
                       bd=0, relief="flat", font=self._scaled_font(9))
        for name in THEME_ORDER:
            label = t('sidebar.' + self._THEME_STR_KEYS[name])
            if name == self.current_theme:
                label = "✓ " + label
            menu.add_command(label=label, command=lambda n=name: self._toggle_theme(n))
        x = button.winfo_rootx()
        y = button.winfo_rooty() - menu.yposition(tk.END) - 30 if button.winfo_rooty() > 300 else button.winfo_rooty() + button.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _toggle_theme(self, new_theme=None) -> None:
        """Switch to the chosen theme (or cycle to the next one)"""
        from config import save_theme
        from app_utils import centered_askyesno

        if new_theme is None:
            new_theme = next_theme(self.current_theme)
        if new_theme == self.current_theme:
            return

        save_theme(new_theme)

        if centered_askyesno(self,
            t('settings.restart_required'),
            t('settings.restart_required_msg') + "\n\n" + t('settings.restart_now_prompt')):
            self._restart_app()

    def _create_language_flags(self, parent_frame) -> None:
        """Create a single language flag button that shows dropdown on click"""
        from localization import get_language
        from path_utils import get_app_data_dir
        
        # Get current language
        current_lang = get_language()
        
        # Flag image files
        self._lang_flag_files = {
            'en': 'united-kingdom.png',
            'de': 'german-flag.png'
        }
        
        # Language names for menu
        self._lang_names = {
            'en': 'English',
            'de': 'Deutsch'
        }
        
        # Load flag images
        self._flag_images = {}
        images_dir = os.path.join(get_app_data_dir(), "Images")
        
        for lang_code, filename in self._lang_flag_files.items():
            flag_path = os.path.join(images_dir, filename)
            if os.path.exists(flag_path):
                try:
                    img = tk.PhotoImage(file=flag_path)
                    # Subsample to reduce size (divide by factor)
                    # 512px -> ~21px = subsample by 24
                    if img.width() > 100:
                        scale = img.width() // 21
                        img = img.subsample(scale, scale)
                    self._flag_images[lang_code] = img
                except Exception as e:
                    log.error(f"Error loading flag image {filename}: {e}")
        
        # Determine current flag
        current_image = self._flag_images.get(current_lang, self._flag_images.get('en'))
        
        # Create flag button with image
        if current_image:
            self._current_lang_label = tk.Label(
                parent_frame,
                image=current_image,
                bg="#1e1e1e",
                cursor="hand2",
                bd=0,
                highlightthickness=0
            )
            self._current_lang_label.image = current_image  # Keep reference
        else:
            # Fallback to text if no image
            self._current_lang_label = tk.Label(
                parent_frame,
                text=current_lang.upper(),
                font=self._scaled_font(9, "bold"),
                bg="#2a4a6a",
                fg="#ffffff",
                padx=8,
                pady=3,
                cursor="hand2",
                relief="raised",
                bd=1
            )
        
        self._current_lang_label.pack(side="left", padx=(8, 0))
        
        # Bind click to show language menu
        self._current_lang_label.bind("<Button-1>", self._show_language_menu)
        
        # Hover effect (subtle) - use add='+' to not override ToolTip bindings
        _flag_modern = self.current_theme in ("modern", "modern_slate", "modern_orange")
        def on_enter_flag(e):
            if _flag_modern:
                self._flag_rest_bg = str(self._current_lang_label.cget("bg"))
                self._current_lang_label.config(bg=self.theme_colors["btn_bg"])
            else:
                self._current_lang_label.config(bg="#2a2a2a")
        def on_leave_flag(e):
            if _flag_modern:
                self._current_lang_label.config(bg=getattr(self, "_flag_rest_bg", self.theme_colors["bg"]))
            else:
                self._current_lang_label.config(bg="#1e1e1e")
        self._current_lang_label.bind("<Enter>", on_enter_flag, add='+')
        self._current_lang_label.bind("<Leave>", on_leave_flag, add='+')
        
        # Add tooltip AFTER bindings
        ToolTip(self._current_lang_label, t('tooltips.change_language'))
    
    def _create_version_button(self, parent_frame) -> None:
        """Create a clickable version button that opens the About dialog"""
        from version import get_version
        
        version = get_version()
        
        # Get theme-appropriate colors
        if self.current_theme == "elite_orange":
            _vbtn_bg = "#1a1a1a"
            _vbtn_fg = "#888888"
            _vbtn_hover_fg = "#ffcc00"
        else:
            _vbtn_bg = "#1e1e1e"
            _vbtn_fg = "#777777"
            _vbtn_hover_fg = "#ffffff"
        
        self._version_label = tk.Label(
            parent_frame,
            text="About",
            font=self._scaled_font(8),
            bg=_vbtn_bg,
            fg=_vbtn_fg,
            cursor="hand2",
            padx=4
        )
        self._version_label.pack(side="left", padx=(8, 6))
        
        # Bind click to show About dialog
        self._version_label.bind("<Button-1>", lambda e: self._show_about_dialog())
        
        # Hover effect
        def on_enter_version(e):
            self._version_label.config(fg=_vbtn_hover_fg)
        def on_leave_version(e):
            self._version_label.config(fg=_vbtn_fg)
        self._version_label.bind("<Enter>", on_enter_version, add='+')
        self._version_label.bind("<Leave>", on_leave_version, add='+')
        
        # Add tooltip
        ToolTip(self._version_label, t('tooltips.about'))
    
    def _show_about_dialog(self) -> None:
        """Show the About dialog as a popup window"""
        import webbrowser
        from version import __version__, __build_date__
        from config import load_theme
        from app_utils import get_app_icon_path
        
        # Theme-aware colors
        _about_theme = load_theme()
        _about_bg = "#000000" if _about_theme == "elite_orange" else "#1e1e1e"
        _btn_bg = "#1a1a1a" if _about_theme == "elite_orange" else "#2a3a4a"
        _btn_fg = "#ff9900" if _about_theme == "elite_orange" else "#e0e0e0"
        _btn_active_bg = "#2a2a2a" if _about_theme == "elite_orange" else "#3a4a5a"
        _btn_active_fg = "#ffcc00" if _about_theme == "elite_orange" else "#ffffff"
        
        # Create dialog
        dialog = tk.Toplevel(self)
        dialog.withdraw()  # Hide initially to prevent blinking on wrong monitor
        dialog.title(t('tabs.about'))
        dialog.configure(bg=_about_bg)
        dialog.resizable(False, False)
        dialog.transient(self)
        
        # Set icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except:
            pass
        
        # Main container
        main_frame = tk.Frame(dialog, bg=_about_bg, padx=30, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Try to load text logo image
        try:
            from path_utils import get_images_dir
            from PIL import Image, ImageTk
            import os
            logo_path = os.path.join(get_images_dir(), "EliteMining_txt_logo_transp_resize.png")
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                # Resize to reasonable width
                orig_width, orig_height = img.size
                new_width = 220
                new_height = int(orig_height * (new_width / orig_width))
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                self._about_dialog_logo = ImageTk.PhotoImage(img)
                logo_label = tk.Label(main_frame, image=self._about_dialog_logo, bg=_about_bg)
                logo_label.pack(pady=(0, 5))
            else:
                tk.Label(main_frame, text="EliteMining", font=self._scaled_font(16, "bold"), 
                         fg="#ffcc00", bg=_about_bg).pack()
        except Exception:
            tk.Label(main_frame, text="EliteMining", font=self._scaled_font(16, "bold"), 
                     fg="#ffcc00", bg=_about_bg).pack()
        
        # Version
        tk.Label(main_frame, text=f"Version {__version__}", font=self._scaled_font(10), 
                 fg="#888888", bg=_about_bg).pack(pady=(0, 10))
        
        # Description
        tk.Label(main_frame, text=t('about.description'), 
                 font=self._scaled_font(10), fg="#e0e0e0", bg=_about_bg).pack(pady=(0, 10))
        
        # Separator
        tk.Frame(main_frame, height=1, bg="#444444", width=350).pack(pady=8)
        
        # Copyright and license
        tk.Label(main_frame, text=t('about.copyright'), 
                 font=self._scaled_font(9), fg="#e0e0e0", bg=_about_bg).pack()
        tk.Label(main_frame, text=t('about.license'), 
                 font=self._scaled_font(8), fg="#888888", bg=_about_bg).pack()
        
        # Separator
        tk.Frame(main_frame, height=1, bg="#444444", width=350).pack(pady=8)
        
        # Links section (horizontal row)
        links_frame = tk.Frame(main_frame, bg=_about_bg)
        links_frame.pack(pady=8)
        
        # Row 1: Discord, Reddit, GitHub
        links_row1 = [
            (t('about.discord'), "https://discord.gg/5dsF3UshRR"),
            (t('about.reddit'), "https://www.reddit.com/r/EliteDangerous/comments/1oflji3/elitemining_free_mining_hotspot_finder_app/"),
            (t('about.github'), "https://github.com/Viper-Dude/EliteMining"),
        ]
        
        def open_link(url):
            webbrowser.open(url)
        
        for label, url in links_row1:
            btn = tk.Button(links_frame, text=label, 
                           command=lambda u=url: open_link(u),
                           bg=_btn_bg, fg=_btn_fg, activebackground=_btn_active_bg,
                           activeforeground=_btn_active_fg, relief="ridge", bd=1, 
                           padx=8, pady=2, font=self._scaled_font(8), cursor="hand2")
            btn.pack(side="left", padx=3)
        
        # Row 2: Docs, Report Bug
        links_frame2 = tk.Frame(main_frame, bg=_about_bg)
        links_frame2.pack(pady=(4, 8))
        
        links_row2 = [
            (t('about.documentation'), "https://github.com/Viper-Dude/EliteMining#readme"),
            (t('about.report_bug'), "https://github.com/Viper-Dude/EliteMining/issues/new"),
            (t('about.patch_notes'), f"https://github.com/Viper-Dude/EliteMining/blob/main/docs/PATCHNOTES_v{__version__}.md"),
        ]
        
        for label, url in links_row2:
            btn = tk.Button(links_frame2, text=label, 
                           command=lambda u=url: open_link(u),
                           bg=_btn_bg, fg=_btn_fg, activebackground=_btn_active_bg,
                           activeforeground=_btn_active_fg, relief="ridge", bd=1, 
                           padx=8, pady=2, font=self._scaled_font(8), cursor="hand2")
            btn.pack(side="left", padx=3)
        
        # Separator
        tk.Frame(main_frame, height=1, bg="#444444", width=350).pack(pady=8)
        
        # Credits (compact)
        credits_text = "Credits: EliteVA (Somfic) • Ardent API (Iain Collins) • EDCD/EDDN"
        tk.Label(main_frame, text=credits_text, font=self._scaled_font(8), 
                 fg="#888888", bg=_about_bg, wraplength=380).pack(pady=(0, 10))
        
        # Support/Donate row
        support_frame = tk.Frame(main_frame, bg=_about_bg)
        support_frame.pack(pady=(5, 0))
        
        tk.Label(support_frame, text="☕ " + t('about.donation_text'),
                 font=self._scaled_font(8, "italic"), fg="#aaaaaa", bg=_about_bg,
                 wraplength=380, justify="center").pack(pady=(0, 8))
        
        # PayPal button with logo image
        try:
            from path_utils import get_app_data_dir
            paypal_img_path = os.path.join(get_app_data_dir(), "Images", "paypal.png")
            if os.path.exists(paypal_img_path):
                paypal_img = tk.PhotoImage(file=paypal_img_path)
                # Scale to ~45px width
                if paypal_img.width() > 45:
                    scale = max(1, paypal_img.width() // 45)
                    paypal_img = paypal_img.subsample(scale, scale)
                self._about_dialog_paypal_img = paypal_img  # Keep reference
                paypal_btn = tk.Label(support_frame, image=paypal_img, cursor="hand2", bg=_about_bg)
                paypal_btn.pack()
                paypal_btn.bind("<Button-1>", lambda e: webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=NZQTA4TGPDSC6"))
            else:
                raise FileNotFoundError("PayPal image not found")
        except Exception:
            # Fallback to text button
            paypal_btn = tk.Button(support_frame, text="PayPal", 
                                  command=lambda: webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=NZQTA4TGPDSC6"),
                                  bg="#0070ba", fg="#ffffff", activebackground="#0060aa",
                                  relief="flat", bd=0, padx=8, pady=1, font=self._scaled_font(8), cursor="hand2")
            paypal_btn.pack()
        
        # Close button
        close_btn = tk.Button(main_frame, text=t('common.close'), 
                             command=dialog.destroy,
                             bg=_btn_bg, fg=_btn_fg, activebackground=_btn_active_bg,
                             activeforeground=_btn_active_fg, relief="ridge", bd=1, 
                             padx=20, pady=3, font=self._scaled_font(9), cursor="hand2")
        close_btn.pack(pady=(15, 0))
        
        # Center on parent - IMPORTANT: Always center dialogs on parent window!
        dialog.update_idletasks()
        self._center_dialog_on_parent(dialog)
        dialog.deiconify()  # Show dialog after centering
        dialog.grab_set()  # Grab focus after showing
        
        # Focus dialog
        dialog.focus_set()

    def _center_dialog_on_parent(self, dialog) -> None:
        """Center a dialog window on the main application window.
        
        IMPORTANT: Always use this method when creating popup dialogs to ensure
        consistent positioning across all dialogs in the application.
        
        Usage:
            dialog = tk.Toplevel(self)
            # ... add widgets to dialog ...
            dialog.update_idletasks()  # Required to get accurate dimensions
            self._center_dialog_on_parent(dialog)
        """
        # Force geometry update to get accurate dimensions (idletasks only —
        # a full update() can let the WM briefly paint the withdrawn dialog
        # at its default position before geometry is applied, causing a flash
        # on multi-monitor setups)
        dialog.update_idletasks()
        
        # Get main window position and size
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        
        # Get dialog size - try reqwidth first, fall back to actual width
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        
        # If reqwidth returned too small, use actual dimensions
        if dialog_width < 50:
            dialog_width = dialog.winfo_width()
        if dialog_height < 50:
            dialog_height = dialog.winfo_height()
        
        # If still too small, use reasonable defaults
        if dialog_width < 50:
            dialog_width = 400
        if dialog_height < 50:
            dialog_height = 300
        
        # Calculate centered position relative to main window
        # DO NOT apply screen bounds - we want it on the same monitor as main window
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        
        # Apply position with explicit size
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

    def _show_language_menu(self, event):
        """Show popup menu with language options"""
        if self.current_theme in ("modern", "modern_slate", "modern_orange"):
            menu = tk.Menu(self, tearoff=0, bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                          activebackground=MENU_COLORS["activebackground"],
                          activeforeground=MENU_COLORS["activeforeground"],
                          font=self._scaled_font(10))
        else:
            menu = tk.Menu(self, tearoff=0, bg="#2a2a2a", fg="#ffffff", 
                          activebackground="#4a4a4a", activeforeground="#ffffff",
                          font=self._scaled_font(10))
        
        from localization import get_language
        current_lang = get_language()
        
        for lang_code, lang_name in self._lang_names.items():
            # Add checkmark for current language
            label = f"{lang_name}" + ("  ✓" if lang_code == current_lang else "")
            
            # Try to add image to menu item
            img = self._flag_images.get(lang_code)
            if img:
                menu.add_command(label=label, image=img, compound="left",
                               command=lambda lc=lang_code: self._change_language(lc))
            else:
                menu.add_command(label=label, 
                               command=lambda lc=lang_code: self._change_language(lc))
        
        # Show menu at button position (above the button)
        try:
            menu.tk_popup(event.widget.winfo_rootx(), 
                         event.widget.winfo_rooty() - len(self._lang_names) * 28)
        finally:
            menu.grab_release()
    
    def _change_language(self, lang_code: str):
        """Change language and prompt for restart"""
        from localization import get_language

        # Don't do anything if same language
        old_lang = get_language()
        if lang_code == old_lang:
            return

        # Save to config
        try:
            cfg = _load_cfg()
            cfg['language'] = lang_code
            _save_cfg(cfg)
        except Exception as e:
            log.error(f"Error saving language setting: {e}")
            return

        # Update the flag display with new image
        new_image = self._flag_images.get(lang_code)
        if new_image:
            self._current_lang_label.config(image=new_image)
            self._current_lang_label.image = new_image
        else:
            self._current_lang_label.config(text=lang_code.upper())

        from app_utils import centered_askyesno
        if centered_askyesno(self,
            t('settings.restart_required'),
            t('settings.restart_required_msg') + "\n\n" + t('settings.restart_now_prompt')):
            self._restart_app()

    def _restart_app(self, geometry_ui_scale=None) -> None:
        """Restart the application to apply a settings change.

        geometry_ui_scale: if given, tag the saved geometry with this scale
        (the scale the CURRENT window size was laid out under) instead of the
        live one, so the next launch can detect the mismatch and resize.
        """
        import sys
        import os
        import subprocess

        # Restarting exits without going through _on_close, so ask about unsaved preset changes here
        if not self._confirm_unsaved_presets():
            return

        # Save window geometry before restart
        try:
            from config import save_window_geometry
            is_zoomed = self.state() == "zoomed"
            if is_zoomed:
                self.state("normal")
                self.update_idletasks()
            geometry = self.geometry()
            geom_payload = {"geometry": geometry, "zoomed": is_zoomed}
            geom_payload["ui_scale"] = self.ui_scale if geometry_ui_scale is None else geometry_ui_scale
            save_window_geometry(geom_payload)
            log.info(f"Window geometry saved before restart: {geometry} (zoomed={is_zoomed})")
        except Exception as e:
            log.exception(f"Error saving window geometry before restart: {e}")

        self._save_sash_positions_now()

        # Save any pending data before restart
        try:
            if hasattr(self, 'prospector_panel') and self.prospector_panel.session_active:
                self.prospector_panel._session_stop()
        except Exception as e:
            log.error(f"Error saving session before restart: {e}")

        # Close the single-instance mutex handle so the relaunched process can acquire it.
        # Created with bInitialOwner=False, so it's never "owned" by a thread -
        # closing the handle (not ReleaseMutex) is what frees the name.
        try:
            import win32api
            global mutex
            if mutex:
                win32api.CloseHandle(mutex)
                mutex = None
        except Exception as e:
            log.warning(f"Warning: Could not close single-instance mutex before restart: {e}")

        flush_config()

        executable = sys.executable
        exe_dir = os.path.dirname(executable)
        pid = os.getpid()
        if getattr(sys, 'frozen', False):
            launch_cmd = f'"{executable}"'
        else:
            script = os.path.abspath(sys.argv[0])
            launch_cmd = f'"{executable}" "{script}"'

        import tempfile
        log_path = os.path.join(tempfile.gettempdir(), "EliteMining_restart_log.txt")
        bat_path = os.path.join(tempfile.gettempdir(), f"EliteMining_restart_{pid}.bat")
        bat_contents = (
            "@echo off\n"
            f'echo [%date% %time%] restart script started, waiting for pid {pid} > "{log_path}"\n'
            f'cd /d "{exe_dir}"\n'
            ":wait\n"
            f'tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul\n'
            "if not errorlevel 1 (\n"
            "  ping 127.0.0.1 -n 2 >nul\n"
            "  goto wait\n"
            ")\n"
            f'echo [%date% %time%] pid {pid} gone, waiting grace period >> "{log_path}"\n'
            "ping 127.0.0.1 -n 2 >nul\n"
            f'echo [%date% %time%] launching: {launch_cmd} >> "{log_path}"\n'
            f'echo [%date% %time%] PYINSTALLER_RESET_ENVIRONMENT=%PYINSTALLER_RESET_ENVIRONMENT% >> "{log_path}"\n'
            f'{launch_cmd}\n'
            f'echo [%date% %time%] launch exit code: %errorlevel% >> "{log_path}"\n'
            f'del "%~f0"\n'
        )
        with open(bat_path, "w") as f:
            f.write(bat_contents)

        # PyInstaller onefile: the bootloader tracks internal env vars so a
        # self-spawned child reuses this process's _MEI extraction dir instead
        # of unpacking its own. That dir is removed once this process exits,
        # so the relaunched exe must be told to treat itself as a fresh
        # top-level instance and unpack into its own new temp dir.
        # https://pyinstaller.org/en/stable/advanced-topics.html
        restart_env = os.environ.copy()
        restart_env['PYINSTALLER_RESET_ENVIRONMENT'] = '1'

        subprocess.Popen(
            ['cmd', '/c', bat_path],
            cwd=exe_dir,
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=restart_env
        )

        self.destroy()
        sys.exit(0)

    def _show_session_active_dialog(self) -> str:
        """Show a themed dialog when closing with an active mining session.
        
        Returns:
            'yes' - Stop session and save
            'no' - Cancel session (lose data)
            'cancel' - Keep session running (don't close)
        """
        from localization import t
        from config import load_theme
        from icon_utils import get_app_icon_path
        
        result = [None]  # Use list to allow modification in nested function
        
        # Create themed dialog
        dialog = tk.Toplevel(self)
        dialog.withdraw()  # Hide initially to prevent flicker on wrong monitor
        dialog.title(t('dialogs.session_active_title'))
        # dialog.transient(self)  # Disabled - causes focus issues
        try:
            dialog.grab_set()
        except:
            pass
        dialog.resizable(False, False)
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path:
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass
        
        # Get theme colors
        theme = load_theme()
        if theme == "elite_orange":
            bg_color = "#0a0a0a"
            fg_color = "#ff8c00"
            fg_bright = "#ffa500"
            btn_bg = "#1a1a1a"
            btn_fg = "#ff8c00"
            warning_color = "#ffcc00"
        else:
            bg_color = "#1e1e1e"
            fg_color = "#e6e6e6"
            fg_bright = "#ffffff"
            btn_bg = "#333333"
            btn_fg = "#ffffff"
            warning_color = "#ffcc00"
        
        dialog.configure(bg=bg_color)
        
        # Main frame
        main_frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=15)
        main_frame.pack(fill="both", expand=True)
        
        # Warning icon and message row
        msg_frame = tk.Frame(main_frame, bg=bg_color)
        msg_frame.pack(fill="x", pady=(0, 15))
        
        # Warning icon (using text emoji)
        tk.Label(
            msg_frame,
            text="⚠️",
            font=self._scaled_font(24),
            bg=bg_color,
            fg=warning_color
        ).pack(side="left", padx=(0, 15))
        
        # Message text
        msg_text_frame = tk.Frame(msg_frame, bg=bg_color)
        msg_text_frame.pack(side="left", fill="x", expand=True)
        
        tk.Label(
            msg_text_frame,
            text=t('dialogs.session_active_message'),
            font=self._scaled_font(11, "bold"),
            bg=bg_color,
            fg=fg_bright
        ).pack(anchor="w")
        
        # Options list
        options_frame = tk.Frame(main_frame, bg=bg_color)
        options_frame.pack(fill="x", pady=(0, 15))
        
        options = [
            (f"• {t('dialogs.yes')} = {t('dialogs.session_active_yes')}", fg_color),
            (f"• {t('dialogs.no')} = {t('dialogs.session_active_no')}", fg_color),
            (f"• {t('dialogs.cancel')} = {t('dialogs.session_active_cancel')}", fg_color),
        ]
        
        for opt_text, opt_color in options:
            tk.Label(
                options_frame,
                text=opt_text,
                font=self._scaled_font(9),
                bg=bg_color,
                fg=opt_color
            ).pack(anchor="w", pady=1)
        
        # Button frame
        btn_frame = tk.Frame(main_frame, bg=bg_color)
        btn_frame.pack(fill="x")
        
        def on_yes():
            result[0] = "yes"
            dialog.destroy()
        
        def on_no():
            result[0] = "no"
            dialog.destroy()
        
        def on_cancel():
            result[0] = "cancel"
            dialog.destroy()
        
        # Buttons with consistent styling
        btn_style = {
            "font": ("Segoe UI", 9),
            "width": 10,
            "relief": "flat",
            "cursor": "hand2",
            "bg": btn_bg,
            "fg": btn_fg,
            "activebackground": fg_color,
            "activeforeground": bg_color,
        }
        
        yes_btn = tk.Button(btn_frame, text=t('dialogs.yes'), command=on_yes, **btn_style)
        yes_btn.pack(side="left", padx=(0, 10))
        
        no_btn = tk.Button(btn_frame, text=t('dialogs.no'), command=on_no, **btn_style)
        no_btn.pack(side="left", padx=(0, 10))
        
        cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel, **btn_style)
        cancel_btn.pack(side="left")
        
        # Handle window close button (X)
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        
        # Bind keyboard
        dialog.bind("<Escape>", lambda e: on_cancel())
        
        # Center dialog on main window
        dialog.update_idletasks()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")
        
        # Show dialog now that it's centered
        dialog.deiconify()
        
        # Force dialog to stay on top and have focus
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        
        # Focus yes button
        yes_btn.focus_set()
        
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
        
        return result[0] if result[0] else "cancel"

    def _show_unsaved_ship_preset_dialog(self, title=None, message=None) -> str:
        """Show a themed dialog when closing with unsaved ship preset changes.

        title/message default to the ship preset texts; pass others to reuse it for announcement presets.

        Returns:
            'yes' - Save changes
            'no' - Discard changes
            'cancel' - Keep app open (don't close)
        """
        from localization import t
        from icon_utils import get_app_icon_path

        result = [None]  # Use list to allow modification in nested function

        # Create themed dialog
        dialog = tk.Toplevel(self)
        dialog.withdraw()  # Hide initially to prevent flicker on wrong monitor
        dialog.title(title or t('dialogs.unsaved_preset_title'))
        # dialog.transient(self)  # Disabled - causes focus issues
        try:
            dialog.grab_set()
        except:
            pass
        dialog.resizable(False, False)

        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path:
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass

        # Get theme colors
        theme = self.current_theme
        if theme == "elite_orange":
            bg_color = "#0a0a0a"
            fg_color = "#ff8c00"
            fg_bright = "#ffa500"
            btn_bg = "#1a1a1a"
            btn_fg = "#ff8c00"
            warning_color = "#ffcc00"
        else:
            bg_color = "#1e1e1e"
            fg_color = "#e6e6e6"
            fg_bright = "#ffffff"
            btn_bg = "#333333"
            btn_fg = "#ffffff"
            warning_color = "#ffcc00"

        dialog.configure(bg=bg_color)

        # Main frame
        main_frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=15)
        main_frame.pack(fill="both", expand=True)

        # Warning icon and message row
        msg_frame = tk.Frame(main_frame, bg=bg_color)
        msg_frame.pack(fill="x", pady=(0, 15))

        # Warning icon (using text emoji)
        tk.Label(
            msg_frame,
            text="⚠️",
            font=self._scaled_font(24),
            bg=bg_color,
            fg=warning_color
        ).pack(side="left", padx=(0, 15))

        # Message text
        msg_text_frame = tk.Frame(msg_frame, bg=bg_color)
        msg_text_frame.pack(side="left", fill="x", expand=True)

        tk.Label(
            msg_text_frame,
            text=message or t('dialogs.unsaved_preset_message').format(name=self._active_ship_preset_name),
            font=self._scaled_font(11, "bold"),
            bg=bg_color,
            fg=fg_bright,
            wraplength=320,
            justify="left"
        ).pack(anchor="w")

        # Options list
        options_frame = tk.Frame(main_frame, bg=bg_color)
        options_frame.pack(fill="x", pady=(0, 15))

        options = [
            (f"• {t('dialogs.yes')} = {t('dialogs.unsaved_preset_yes')}", fg_color),
            (f"• {t('dialogs.no')} = {t('dialogs.unsaved_preset_no')}", fg_color),
            (f"• {t('dialogs.cancel')} = {t('dialogs.unsaved_preset_cancel')}", fg_color),
        ]

        for opt_text, opt_color in options:
            tk.Label(
                options_frame,
                text=opt_text,
                font=self._scaled_font(9),
                bg=bg_color,
                fg=opt_color
            ).pack(anchor="w", pady=1)

        # Button frame
        btn_frame = tk.Frame(main_frame, bg=bg_color)
        btn_frame.pack(fill="x")

        def on_yes():
            result[0] = "yes"
            dialog.destroy()

        def on_no():
            result[0] = "no"
            dialog.destroy()

        def on_cancel():
            result[0] = "cancel"
            dialog.destroy()

        # Buttons with consistent styling
        btn_style = {
            "font": ("Segoe UI", 9),
            "width": 10,
            "relief": "flat",
            "cursor": "hand2",
            "bg": btn_bg,
            "fg": btn_fg,
            "activebackground": fg_color,
            "activeforeground": bg_color,
        }

        yes_btn = tk.Button(btn_frame, text=t('dialogs.yes'), command=on_yes, **btn_style)
        yes_btn.pack(side="left", padx=(0, 10))

        no_btn = tk.Button(btn_frame, text=t('dialogs.no'), command=on_no, **btn_style)
        no_btn.pack(side="left", padx=(0, 10))

        cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel, **btn_style)
        cancel_btn.pack(side="left")

        # Handle window close button (X)
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        # Bind keyboard
        dialog.bind("<Escape>", lambda e: on_cancel())

        # Center dialog on main window
        dialog.update_idletasks()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()

        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")

        # Show dialog now that it's centered
        dialog.deiconify()

        # Force dialog to stay on top and have focus
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()

        # Focus yes button
        yes_btn.focus_set()

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

        return result[0] if result[0] else "cancel"

    def _confirm_unsaved_presets(self) -> bool:
        """Ask about unsaved ship and announcement preset changes. Returns False if the user cancels."""
        if self._ship_is_preset_modified():
            result = self._show_unsaved_ship_preset_dialog()
            if result == "yes":
                self._write_preset_file(self._active_ship_preset_name)
            elif result != "no":
                return False
        if self._ann_is_preset_modified():
            num = self._active_preset_num
            names = self.prospector_panel._load_cfg().get('preset_names', {})
            name = names.get(str(num), t('settings.preset_button').format(num=num))
            result = self._show_unsaved_ship_preset_dialog(
                title=t('dialogs.unsaved_ann_preset_title'),
                message=t('dialogs.unsaved_ann_preset_message').format(name=name))
            if result == "yes":
                self._ann_save_preset(num)
            elif result != "no":
                return False
        return True

    def _on_close(self) -> None:
        # Check if mining session is active
        if hasattr(self, 'prospector_panel') and self.prospector_panel.session_active:
            result = self._show_session_active_dialog()

            if result == "yes":  # Stop and save
                self.prospector_panel._session_stop()
            elif result == "no":  # Cancel session
                self.prospector_panel._session_cancel()
            else:  # Cancel - Don't close
                return

        # Check if the active ship or announcement preset has unsaved changes
        if not self._confirm_unsaved_presets():
            return

        try:
            is_zoomed = (self.state() == "zoomed")
            if is_zoomed:
                self.state("normal")
                self.update_idletasks()
            geom = self.geometry()
            save_window_geometry({"geometry": geom, "zoomed": is_zoomed})
            log.info(f"Window geometry saved on close: {geom} (zoomed={is_zoomed})")
        except Exception:
            log.exception("Failed to save window geometry on close")

        # Safety net: sash positions normally save on <ButtonRelease-1>, but that
        # event may never fire if the window closes mid-drag or via a resize that
        # doesn't release over the paned widget. Capture current positions here too.
        self._save_sash_positions_now()

        # Save marketplace filter settings
        try:
            cfg = _load_cfg()
            cfg['marketplace_large_pad_only'] = self.marketplace_large_pad_only.get()
            cfg['marketplace_exclude_carriers'] = self.marketplace_exclude_carriers.get()
            _save_cfg(cfg)
        except Exception:
            log.exception("Saving marketplace filters on close failed")
        
        self._network_closing = True
        if hasattr(self, 'eddn_sender'):
            self.eddn_sender.stop()
        if hasattr(self, 'api_uploader'):
            self.api_uploader.stop()

        # Clean up text overlay
        if hasattr(self, 'text_overlay'):
            self.text_overlay.destroy()
        
        # Clean up cargo text overlay
        if hasattr(self, 'cargo_text_overlay'):
            self.cargo_text_overlay.destroy()
            
        # Clean up cargo monitor with enhanced resource management
        if hasattr(self, 'cargo_monitor'):
            self.cargo_monitor.cleanup()  # Enhanced cleanup method
            
        # Clean up TTS system
        try:
            from announcer import cleanup_tts
            cleanup_tts()
        except:
            pass
            
        # Clean up file watcher
        try:
            from file_watcher import cleanup_file_watcher
            cleanup_file_watcher()
        except:
            pass
            
        # Clean up matplotlib resources
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except:
            pass
        
        # EDDN listener removed - no longer needed

        # Flush any config changes still only in the in-memory cache (throttle window)
        try:
            flush_config()
        except Exception:
            pass

        self.destroy()

    def _setup_announcement_tracing(self):
        """Set up tracing for announcement variables after loading is complete"""
        for var in self.announcement_vars.values():
            var.trace('w', self._on_announcement_change)  # Save to config.json
        
        # Set up traces again after prospector panel is created
        self.after(500, self._setup_delayed_announcement_tracing)

    def _setup_delayed_announcement_tracing(self):
        """Set up announcement tracing again after prospector panel is ready"""
        for var in self.announcement_vars.values():
            # Clear existing traces first
            for trace_id in var.trace_vinfo():
                var.trace_vdelete("w", trace_id[1])
            # Set up fresh traces
            var.trace('w', self._on_announcement_change)

    # ---------- Backup and Restore functionality ----------
    def _show_backup_dialog(self) -> None:
        """Show backup dialog with options to select what to backup"""
        try:
            dialog = tk.Toplevel(self)
            dialog.withdraw()  # Hide initially to prevent blinking on wrong monitor
            dialog.title(t('dialogs.backup_title'))
            dialog.geometry("450x600")
            dialog.resizable(True, True)
            dialog.minsize(450, 600)
            dialog.configure(bg="#1e1e1e")
            
            # Set app icon if available
            try:
                icon_path = get_app_icon_path()
                if icon_path and os.path.exists(icon_path):
                    if icon_path.endswith('.ico'):
                        dialog.iconbitmap(icon_path)
                    elif icon_path.endswith('.png'):
                        dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
            except Exception:
                pass
            
            # Center on parent, then make transient so it stays on top of main window
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            dialog.transient(self)
            dialog.deiconify()
            dialog.grab_set()
            
            # Title
            title_label = tk.Label(dialog, text="📦 " + t('dialogs.backup_title'), 
                                 font=self._scaled_font(14, "bold"),
                                 bg="#1e1e1e", fg="#ff9800")
            title_label.pack(pady=15)
            
            # Instructions
            inst_label = tk.Label(dialog, text=t('dialogs.backup_instructions'),
                                font=self._scaled_font(10),
                                bg="#1e1e1e", fg="#aaaaaa")
            inst_label.pack(pady=(0, 20))
            
            # Backup options frame
            options_frame = tk.Frame(dialog, bg="#1e1e1e")
            options_frame.pack(pady=10)
            
            # Backup option variables - all default to unticked
            backup_presets = tk.IntVar(value=0)
            backup_reports = tk.IntVar(value=0)
            backup_bookmarks = tk.IntVar(value=0)
            backup_va_profile = tk.IntVar(value=0)
            backup_userdb = tk.IntVar(value=0)
            backup_journals = tk.IntVar(value=0)
            backup_config = tk.IntVar(value=0)
            backup_all = tk.IntVar(value=0)
            
            def on_all_change():
                """Toggle all checkboxes on/off based on Backup Everything state"""
                new_value = backup_all.get()
                backup_presets.set(new_value)
                backup_reports.set(new_value)
                backup_bookmarks.set(new_value)
                backup_va_profile.set(new_value)
                backup_userdb.set(new_value)
                backup_journals.set(new_value)
                backup_config.set(new_value)
            
            # All checkbox
            all_cb = ThemedCheckbutton(options_frame, text="📂 " + t('dialogs.backup_everything'),
                                  variable=backup_all,
                                  command=on_all_change,
                                  bg="#1e1e1e", fg="#ffffff",
                                  selectcolor="#2a2a2a",
                                  activebackground="#2a2a2a",
                                  activeforeground="#ffffff",
                                  font=self._scaled_font(10, "bold"))
            all_cb.pack(anchor="w", pady=5)
            
            # Separator
            sep = tk.Frame(options_frame, height=1, bg="#ff9800")
            sep.pack(fill="x", pady=10)
            
            # Individual checkboxes
            presets_cb = ThemedCheckbutton(options_frame, text="⚙️ " + t('dialogs.ship_presets'),
                                      variable=backup_presets,
                                      bg="#1e1e1e", fg="#ffffff",
                                      selectcolor="#2a2a2a",
                                      activebackground="#2a2a2a",
                                      activeforeground="#ffffff",
                                      font=self._scaled_font(10))
            presets_cb.pack(anchor="w", pady=2)
            
            reports_cb = ThemedCheckbutton(options_frame, text="📊 " + t('dialogs.mining_reports'),
                                      variable=backup_reports,
                                      bg="#1e1e1e", fg="#ffffff",
                                      selectcolor="#2a2a2a",
                                      activebackground="#2a2a2a",
                                      activeforeground="#ffffff",
                                      font=self._scaled_font(10))
            reports_cb.pack(anchor="w", pady=2)
            
            bookmarks_cb = ThemedCheckbutton(options_frame, text="🔖 " + t('dialogs.mining_bookmarks'),
                                        variable=backup_bookmarks,
                                        bg="#1e1e1e", fg="#ffffff",
                                        selectcolor="#2a2a2a",
                                        activebackground="#2a2a2a",
                                        activeforeground="#ffffff",
                                        font=self._scaled_font(10))
            bookmarks_cb.pack(anchor="w", pady=2)
            
            va_profile_cb = ThemedCheckbutton(options_frame, text="🎤 " + t('dialogs.voiceattack_profile'),
                                         variable=backup_va_profile,
                                         bg="#1e1e1e", fg="#ffffff",
                                         selectcolor="#2a2a2a",
                                         activebackground="#2a2a2a",
                                         activeforeground="#ffffff",
                                         font=self._scaled_font(10))
            va_profile_cb.pack(anchor="w", pady=2)
            
            userdb_cb = ThemedCheckbutton(options_frame, text="💾 " + t('dialogs.user_database'),
                                       variable=backup_userdb,
                                       bg="#1e1e1e", fg="#ffffff",
                                       selectcolor="#2a2a2a",
                                       activebackground="#2a2a2a",
                                       activeforeground="#ffffff",
                                       font=self._scaled_font(10))
            userdb_cb.pack(anchor="w", pady=2)
            
            journals_cb = ThemedCheckbutton(options_frame, text="📝 " + t('dialogs.journal_files'),
                                        variable=backup_journals,
                                        bg="#1e1e1e", fg="#ffffff",
                                        selectcolor="#2a2a2a",
                                        activebackground="#2a2a2a",
                                        activeforeground="#ffffff",
                                        font=self._scaled_font(10))
            journals_cb.pack(anchor="w", pady=2)
            
            config_cb = ThemedCheckbutton(options_frame, text="🔧 " + t('dialogs.configuration'),
                                      variable=backup_config,
                                      bg="#1e1e1e", fg="#ffffff",
                                      selectcolor="#2a2a2a",
                                      activebackground="#2a2a2a",
                                      activeforeground="#ffffff",
                                      font=self._scaled_font(10))
            config_cb.pack(anchor="w", pady=2)
            
            # Buttons frame
            btn_frame = tk.Frame(dialog, bg="#1e1e1e")
            btn_frame.pack(pady=20)
            
            def on_create_backup():
                # Get selected options
                include_presets = backup_presets.get() or backup_all.get()
                include_reports = backup_reports.get() or backup_all.get()
                include_bookmarks = backup_bookmarks.get() or backup_all.get()
                include_va_profile = backup_va_profile.get() or backup_all.get()
                include_userdb = backup_userdb.get() or backup_all.get()
                include_journals = backup_journals.get() or backup_all.get()
                include_config = backup_config.get() or backup_all.get()
                
                if not (include_presets or include_reports or include_bookmarks or include_va_profile or include_userdb or include_journals or include_config):
                    messagebox.showwarning(t('dialogs.no_selection'), t('dialogs.no_selection_msg'))
                    return
                
                dialog.destroy()
                self._create_backup(include_presets, include_reports, include_bookmarks, include_va_profile, include_userdb, include_journals, include_config)
            
            def on_cancel():
                dialog.destroy()
            
            create_btn = tk.Button(btn_frame, text=t('dialogs.create_backup'), command=on_create_backup,
                                 bg="#27ae60", fg="white", font=self._scaled_font(10, "bold"),
                                 width=15, cursor="hand2")
            create_btn.pack(side=tk.LEFT, padx=5)
            
            cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel,
                                 bg="#e74c3c", fg="white", font=self._scaled_font(10, "bold"),
                                 width=15, cursor="hand2")
            cancel_btn.pack(side=tk.LEFT, padx=5)
            
            # Bind escape key
            dialog.bind('<Escape>', lambda e: on_cancel())
            
            dialog.wait_window()
            
        except Exception as e:
            messagebox.showerror("Backup Dialog Error", f"Failed to show backup dialog: {str(e)}")

    def _create_backup(self, include_presets: bool, include_reports: bool, include_bookmarks: bool, include_va_profile: bool, include_userdb: bool = False, include_journals: bool = False, include_config: bool = False) -> None:
        """Create backup zip file with selected data"""
        try:
            # Ask for backup location
            timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Create descriptive name based on what's included
            parts = []
            if include_presets:
                parts.append("Ship Presets")
            if include_reports:
                parts.append("Reports")
            if include_bookmarks:
                parts.append("Bookmarks")
            if include_va_profile:
                parts.append("VA Profile")
            if include_userdb:
                parts.append("UserDB")
            if include_journals:
                parts.append("Journals")
            if include_config:
                parts.append("Config")
            
            if len(parts) == 7:
                content_desc = "Full"
            else:
                content_desc = "_".join(parts)
            
            default_name = f"EliteMining_Backup_{content_desc}_{timestamp}.zip"
            
            backup_path = filedialog.asksaveasfilename(
                title=t('dialogs.save_backup_as'),
                defaultextension=".zip",
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
                initialfile=default_name
            )
            
            if not backup_path:
                return
            
            # Create backup zip
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Get the correct app data directory
                app_data_dir = self._get_app_data_dir()
                
                # Debug: Show what directory we're using
                print(f"BACKUP DEBUG: app_data_dir = '{app_data_dir}'")
                print(f"BACKUP DEBUG: Frozen = {getattr(sys, 'frozen', False)}")
                print(f"BACKUP DEBUG: sys.executable = '{sys.executable if getattr(sys, 'frozen', False) else 'N/A'}'")
                
                # Add ship presets
                if include_presets:
                    # Use dedicated path function for correct installer/dev paths
                    settings_dir = get_ship_presets_dir()
                    print(f"BACKUP DEBUG: Looking for presets in: '{settings_dir}'")
                    print(f"BACKUP DEBUG: Presets folder exists: {os.path.exists(settings_dir)}")
                    if os.path.exists(settings_dir):
                        preset_count = 0
                        for file_name in os.listdir(settings_dir):
                            if file_name.endswith('.json'):
                                file_path = os.path.join(settings_dir, file_name)
                                zipf.write(file_path, f"Settings/{file_name}")
                                preset_count += 1
                                print(f"BACKUP DEBUG: Added preset: {file_name}")
                        print(f"BACKUP DEBUG: Total presets backed up: {preset_count}")
                    else:
                        print(f"BACKUP DEBUG: Presets folder NOT FOUND!")
                        # Try alternate paths
                        alt_path = os.path.join(app_data_dir, "Ship Presets")
                        print(f"BACKUP DEBUG: Trying alternate path: '{alt_path}' - Exists: {os.path.exists(alt_path)}")
                
                # Add mining reports
                if include_reports:
                    # Use dedicated path function - gets Reports root, not Mining Session subdirectory
                    reports_root = os.path.dirname(get_reports_dir())  # Get Reports folder (parent of Mining Session)
                    print(f"BACKUP DEBUG: Looking for reports in: '{reports_root}'")
                    print(f"BACKUP DEBUG: Reports folder exists: {os.path.exists(reports_root)}")
                    if os.path.exists(reports_root):
                        report_count = 0
                        for root, dirs, files in os.walk(reports_root):
                            for file_name in files:
                                # Include all report types: CSV, TXT, JSON, PNG (graphs/cards), HTML
                                if file_name.endswith(('.csv', '.txt', '.json', '.png', '.html')):
                                    file_path = os.path.join(root, file_name)
                                    rel_path = os.path.relpath(file_path, os.path.dirname(reports_root))
                                    zipf.write(file_path, rel_path)
                                    report_count += 1
                                    print(f"BACKUP DEBUG: Added report: {rel_path}")
                        print(f"BACKUP DEBUG: Total report files backed up: {report_count}")
                    else:
                        print(f"BACKUP DEBUG: Reports folder NOT FOUND!")
                        # Try alternate path
                        alt_path = os.path.join(app_data_dir, "Reports")
                        print(f"BACKUP DEBUG: Trying alternate path: '{alt_path}' - Exists: {os.path.exists(alt_path)}")
                
                # Add mining bookmarks
                if include_bookmarks:
                    bookmarks_file = os.path.join(app_data_dir, "mining_bookmarks.json")
                    print(f"BACKUP DEBUG: Looking for bookmarks at: '{bookmarks_file}'")
                    print(f"BACKUP DEBUG: Bookmarks file exists: {os.path.exists(bookmarks_file)}")
                    
                    if os.path.exists(bookmarks_file):
                        zipf.write(bookmarks_file, "mining_bookmarks.json")
                        print(f"BACKUP DEBUG: Bookmarks file backed up successfully")
                        # Also back up BookmarkScreenshots folder
                        from path_utils import get_bookmark_screenshots_dir
                        ss_root = get_bookmark_screenshots_dir()
                        if os.path.exists(ss_root):
                            for dirpath, dirnames, filenames in os.walk(ss_root):
                                for filename in filenames:
                                    full_path = os.path.join(dirpath, filename)
                                    arcname = os.path.join("BookmarkScreenshots",
                                                           os.path.relpath(full_path, ss_root))
                                    zipf.write(full_path, arcname)
                            print(f"BACKUP DEBUG: BookmarkScreenshots folder backed up")
                    else:
                        print(f"BACKUP DEBUG: Bookmarks file NOT FOUND!")
                        # List what's actually in app_data_dir
                        if os.path.exists(app_data_dir):
                            files = os.listdir(app_data_dir)
                            print(f"BACKUP DEBUG: Files in app_data_dir: {files[:10]}")  # First 10 files
                
                # Add VoiceAttack profile
                if include_va_profile:
                    import glob
                    va_profile_path = None
                    
                    # VoiceAttack profile is in the installer dir at \Apps\EliteMining\
                    if getattr(sys, 'frozen', False):
                        # Running as executable - profile is in parent directory
                        exe_dir = os.path.dirname(sys.executable)
                        parent_dir = os.path.dirname(exe_dir)
                        
                        # Look for versioned profile pattern first
                        profile_pattern = os.path.join(parent_dir, "EliteMining v*-Profile.vap")
                        profile_files = glob.glob(profile_pattern)
                        
                        if profile_files:
                            va_profile_path = profile_files[0]
                        else:
                            # Fallback to old naming
                            old_path = os.path.join(parent_dir, "EliteMining-Profile.vap")
                            if os.path.exists(old_path):
                                va_profile_path = old_path
                    else:
                        # Running in development - profile is in project root
                        project_root = os.path.dirname(app_data_dir)
                        profile_dir = os.path.join(project_root, "Voiceattack Profile")
                        if not os.path.isdir(profile_dir):
                            profile_dir = project_root
                        profile_pattern = os.path.join(profile_dir, "EliteMining v*-Profile.vap")
                        profile_files = glob.glob(profile_pattern)
                        
                        if profile_files:
                            va_profile_path = profile_files[0]
                        else:
                            # Fallback
                            old_path = os.path.join(profile_dir, "EliteMining-Profile.vap")
                            if os.path.exists(old_path):
                                va_profile_path = old_path
                    
                    if va_profile_path and os.path.exists(va_profile_path):
                        # Use original filename in backup
                        zipf.write(va_profile_path, os.path.basename(va_profile_path))
                        if not getattr(sys, 'frozen', False):
                            print(f"DEBUG: Successfully added VoiceAttack profile to backup: {os.path.basename(va_profile_path)}")
                    else:
                        if not getattr(sys, 'frozen', False):
                            print(f"DEBUG: VoiceAttack profile not found")
                
                # Add user database
                if include_userdb:
                    userdb_path = os.path.join(app_data_dir, "data", "user_data.db")
                    if os.path.exists(userdb_path):
                        import sqlite3
                        import tempfile
                        from contextlib import closing
                        with tempfile.TemporaryDirectory() as backup_dir:
                            snapshot = os.path.join(backup_dir, "user_data.db")
                            with closing(sqlite3.connect(userdb_path)) as source, closing(sqlite3.connect(snapshot)) as target:
                                source.backup(target)
                            zipf.write(snapshot, "data/user_data.db")
                
                # Add journal files
                if include_journals:
                    # Get journal folder from prospector panel
                    journal_folder = None
                    if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, 'journal_dir'):
                        journal_folder = self.prospector_panel.journal_dir
                    
                    if journal_folder and os.path.isdir(journal_folder):
                        journal_files = [f for f in os.listdir(journal_folder) if f.endswith('.log')]
                        
                        if journal_files:
                            journal_count = 0
                            journal_size = 0
                            
                            for journal_file in journal_files:
                                journal_path = os.path.join(journal_folder, journal_file)
                                if os.path.isfile(journal_path):
                                    zipf.write(journal_path, f"Journals/{journal_file}")
                                    journal_count += 1
                                    journal_size += os.path.getsize(journal_path)
                            
                            if not getattr(sys, 'frozen', False):  # Only show debug in development
                                print(f"DEBUG: Backed up {journal_count} journal files ({journal_size / 1024 / 1024:.1f} MB) from {journal_folder}")
                        else:
                            messagebox.showwarning("No Journal Files", f"No journal (.log) files found in:\n{journal_folder}")
                    else:
                        messagebox.showwarning("Journal Folder Not Set", 
                                             "Journal folder is not configured in Interface Options.\n\n"
                                             "Please set your journal folder first, then try again.")
                
                # Add configuration file
                if include_config:
                    from config import CONFIG_FILE
                    flush_config()
                    if os.path.exists(CONFIG_FILE):
                        zipf.write(CONFIG_FILE, "config.json")
                
                # Add manifest file with backup info
                manifest = {
                    "backup_date": dt.datetime.now().isoformat(),
                    "app_version": APP_VERSION,
                    "included": {
                        "ship_presets": include_presets,
                        "mining_reports": include_reports,
                        "mining_bookmarks": include_bookmarks,
                        "va_profile": include_va_profile,
                        "user_database": include_userdb,
                        "journal_files": include_journals,
                        "configuration": include_config
                    }
                }
                zipf.writestr("backup_manifest.json", json.dumps(manifest, indent=2))
            
            from app_utils import centered_message
            centered_message(self, "Backup Complete", f"Backup created successfully!\n\nLocation: {backup_path}")
            self._set_status(f"Backup created: {os.path.basename(backup_path)}")
            
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Failed to create backup: {str(e)}")

    def _show_restore_dialog(self) -> None:
        """Show restore dialog to select backup file and options"""
        try:
            # Ask for backup file
            backup_path = filedialog.askopenfilename(
                title=t('dialogs.select_backup_file'),
                filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")]
            )
            
            if not backup_path:
                return
            
            # Check if it's a valid backup
            try:
                with zipfile.ZipFile(backup_path, 'r') as zipf:
                    file_list = zipf.namelist()
                    
                    # Check for manifest (optional for older backups)
                    manifest = None
                    if "backup_manifest.json" in file_list:
                        manifest_data = zipf.read("backup_manifest.json")
                        manifest = json.loads(manifest_data.decode('utf-8'))
                    
                    # Determine what's available in backup
                    has_presets = any(f.startswith("Settings/") and f.endswith(".json") for f in file_list)
                    has_reports = any(f.startswith("Reports/") for f in file_list)
                    has_bookmarks = "mining_bookmarks.json" in file_list
                    # Check for versioned or old profile naming
                    has_va_profile = any(f.endswith("-Profile.vap") or f == "EliteMining-Profile.vap" for f in file_list)
                    has_userdb = "data/user_data.db" in file_list
                    has_journals = any(f.startswith("Journals/") and f.endswith(".log") for f in file_list)
                    has_config = "config.json" in file_list
                    
                    if not (has_presets or has_reports or has_bookmarks or has_va_profile or has_userdb or has_journals or has_config):
                        messagebox.showerror(t('dialogs.invalid_backup'), t('dialogs.invalid_backup_msg'))
                        return
                    
                    self._show_restore_options_dialog(backup_path, has_presets, has_reports, has_bookmarks, has_va_profile, has_userdb, has_journals, manifest, has_config)
                    
            except zipfile.BadZipFile:
                messagebox.showerror(t('dialogs.invalid_file'), t('dialogs.invalid_zip_msg'))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read backup file: {str(e)}")
                
        except Exception as e:
            messagebox.showerror("Restore Dialog Error", f"Failed to show restore dialog: {str(e)}")

    def _show_restore_options_dialog(self, backup_path: str, has_presets: bool, has_reports: bool, 
                                   has_bookmarks: bool, has_va_profile: bool, has_userdb: bool = False, has_journals: bool = False, manifest: Optional[Dict] = None, has_config: bool = False) -> None:
        """Show dialog to select what to restore from backup"""
        try:
            dialog = tk.Toplevel(self)
            dialog.withdraw()  # Hide initially to prevent blinking on wrong monitor
            dialog.title(t('dialogs.restore_title'))
            dialog.geometry("450x750")
            dialog.resizable(True, True)
            dialog.minsize(450, 750)
            dialog.configure(bg="#1e1e1e")
            
            # Set app icon if available
            try:
                icon_path = get_app_icon_path()
                if icon_path and os.path.exists(icon_path):
                    if icon_path.endswith('.ico'):
                        dialog.iconbitmap(icon_path)
                    elif icon_path.endswith('.png'):
                        dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
            except Exception:
                pass
            
            # Center on parent, then make transient so it stays on top of main window
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            dialog.transient(self)
            dialog.deiconify()
            dialog.grab_set()
            
            # Title
            title_label = tk.Label(dialog, text=t('dialogs.restore_title'), 
                                 font=self._scaled_font(14, "bold"),
                                 bg="#1e1e1e", fg="#ff9800")
            title_label.pack(pady=15)
            
            # Backup info
            if manifest:
                backup_date = manifest.get("backup_date", "Unknown")
                app_version = manifest.get("app_version", "Unknown")
                info_text = f"{t('dialogs.backup_date')}: {backup_date[:19].replace('T', ' ')}\n{t('dialogs.app_version')}: {app_version}"
            else:
                info_text = f"{t('dialogs.backup_file')}: {os.path.basename(backup_path)}"
                
            info_label = tk.Label(dialog, text=info_text,
                                font=self._scaled_font(9),
                                bg="#1e1e1e", fg="#aaaaaa")
            info_label.pack(pady=(0, 10))
            
            # Instructions
            inst_label = tk.Label(dialog, text=t('dialogs.restore_instructions'),
                                font=self._scaled_font(10),
                                bg="#1e1e1e", fg="#aaaaaa")
            inst_label.pack(pady=(0, 20))
            
            # Restore options frame
            options_frame = tk.Frame(dialog, bg="#1e1e1e")
            options_frame.pack(pady=10)
            
            # Restore option variables - all default to unticked
            restore_presets = tk.IntVar(value=0)
            restore_reports = tk.IntVar(value=0)
            restore_bookmarks = tk.IntVar(value=0)
            restore_va_profile = tk.IntVar(value=0)
            restore_userdb = tk.IntVar(value=0)
            restore_journals = tk.IntVar(value=0)
            restore_config = tk.IntVar(value=0)
            restore_all = tk.IntVar(value=0)
            
            def on_restore_all_change():
                """Toggle all available checkboxes on/off based on Restore Everything state"""
                new_value = restore_all.get()
                if has_presets:
                    restore_presets.set(new_value)
                if has_reports:
                    restore_reports.set(new_value)
                if has_bookmarks:
                    restore_bookmarks.set(new_value)
                if has_va_profile:
                    restore_va_profile.set(new_value)
                if has_userdb:
                    restore_userdb.set(new_value)
                if has_journals:
                    restore_journals.set(new_value)
                if has_config:
                    restore_config.set(new_value)
            
            # Restore Everything checkbox
            all_cb = ThemedCheckbutton(options_frame, text=t('dialogs.restore_everything'),
                                  variable=restore_all,
                                  command=on_restore_all_change,
                                  bg="#1e1e1e", fg="#ffffff",
                                  selectcolor="#2a2a2a",
                                  activebackground="#2a2a2a",
                                  activeforeground="#ffffff",
                                  font=self._scaled_font(10, "bold"))
            all_cb.pack(anchor="w", pady=5)
            
            # Separator
            sep = tk.Frame(options_frame, height=1, bg="#ff9800")
            sep.pack(fill="x", pady=10)
            
            # Checkboxes for available items
            if has_presets:
                presets_cb = ThemedCheckbutton(options_frame, text=t('dialogs.ship_presets'),
                                          variable=restore_presets,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=self._scaled_font(10))
                presets_cb.pack(anchor="w", pady=2)
            
            if has_reports:
                reports_cb = ThemedCheckbutton(options_frame, text=t('dialogs.mining_reports'),
                                          variable=restore_reports,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=self._scaled_font(10))
                reports_cb.pack(anchor="w", pady=2)
            
            if has_bookmarks:
                bookmarks_cb = ThemedCheckbutton(options_frame, text=t('dialogs.mining_bookmarks'),
                                            variable=restore_bookmarks,
                                            bg="#1e1e1e", fg="#ffffff",
                                            selectcolor="#2a2a2a",
                                            activebackground="#2a2a2a",
                                            activeforeground="#ffffff",
                                            font=self._scaled_font(10))
                bookmarks_cb.pack(anchor="w", pady=2)
            
            if has_va_profile:
                va_profile_cb = ThemedCheckbutton(options_frame, text=t('dialogs.voiceattack_profile'),
                                             variable=restore_va_profile,
                                             bg="#1e1e1e", fg="#ffffff",
                                             selectcolor="#2a2a2a",
                                             activebackground="#2a2a2a",
                                             activeforeground="#ffffff",
                                             font=self._scaled_font(10))
                va_profile_cb.pack(anchor="w", pady=2)
            
            if has_userdb:
                userdb_cb = ThemedCheckbutton(options_frame, text=t('dialogs.user_database'),
                                          variable=restore_userdb,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=self._scaled_font(10))
                userdb_cb.pack(anchor="w", pady=2)
            
            if has_journals:
                journals_cb = ThemedCheckbutton(options_frame, text=t('dialogs.journal_files'),
                                           variable=restore_journals,
                                           bg="#1e1e1e", fg="#ffffff",
                                           selectcolor="#2a2a2a",
                                           activebackground="#2a2a2a",
                                           activeforeground="#ffffff",
                                           font=self._scaled_font(10))
                journals_cb.pack(anchor="w", pady=2)
            
            if has_config:
                config_cb = ThemedCheckbutton(options_frame, text=t('dialogs.configuration'),
                                          variable=restore_config,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=self._scaled_font(10))
                config_cb.pack(anchor="w", pady=2)
            
            # Warning label
            warning_label = tk.Label(dialog, 
                                   text=t('dialogs.restore_warning'),
                                   font=self._scaled_font(9, "bold"),
                                   bg="#1e1e1e", fg="#e74c3c")
            warning_label.pack(pady=(20, 5))
            
            # Restart info label
            restart_label = tk.Label(dialog, 
                                   text=t('dialogs.restart_info'),
                                   font=self._scaled_font(9),
                                   bg="#1e1e1e", fg="#888888")
            restart_label.pack(pady=(0, 10))
            
            # Buttons frame
            btn_frame = tk.Frame(dialog, bg="#1e1e1e")
            btn_frame.pack(pady=20)
            
            def on_restore():
                # Check if anything is selected
                restore_any = False
                if has_presets and restore_presets.get():
                    restore_any = True
                if has_reports and restore_reports.get():
                    restore_any = True
                if has_bookmarks and restore_bookmarks.get():
                    restore_any = True
                if has_va_profile and restore_va_profile.get():
                    restore_any = True
                if has_userdb and restore_userdb.get():
                    restore_any = True
                if has_journals and restore_journals.get():
                    restore_any = True
                if has_config and restore_config.get():
                    restore_any = True
                
                if not restore_any:
                    messagebox.showwarning(t('dialogs.no_selection'), t('dialogs.no_selection_msg'))
                    return
                
                # Confirm action
                from app_utils import centered_askyesno
                result = centered_askyesno(self, t('dialogs.confirm_restore'), 
                                           t('dialogs.confirm_restore_msg'))
                if not result:
                    return
                
                dialog.destroy()
                self._restore_from_backup(backup_path,
                                        restore_presets.get() if has_presets else False,
                                        restore_reports.get() if has_reports else False,
                                        restore_bookmarks.get() if has_bookmarks else False,
                                        restore_va_profile.get() if has_va_profile else False,
                                        restore_userdb.get() if has_userdb else False,
                                        restore_journals.get() if has_journals else False,
                                        restore_config.get() if has_config else False)
            
            def on_cancel():
                dialog.destroy()
            
            restore_btn = tk.Button(btn_frame, text=t('dialogs.restore_button'), command=on_restore,
                                  bg="#27ae60", fg="white", font=self._scaled_font(10, "bold"),
                                  width=18, cursor="hand2")
            restore_btn.pack(side=tk.LEFT, padx=10)
            
            cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel,
                                 bg="#e74c3c", fg="white", font=self._scaled_font(10, "bold"),
                                 width=18, cursor="hand2")
            cancel_btn.pack(side=tk.LEFT, padx=10)
            
            # Bind escape key
            dialog.bind('<Escape>', lambda e: on_cancel())
            
            dialog.wait_window()
            
        except Exception as e:
            messagebox.showerror("Restore Options Error", f"Failed to show restore options: {str(e)}")

    def _restore_from_backup(self, backup_path: str, restore_presets: bool, 
                           restore_reports: bool, restore_bookmarks: bool, restore_va_profile: bool, restore_userdb: bool = False, restore_journals: bool = False, restore_config: bool = False) -> None:
        """Restore selected items from backup zip file"""
        try:
            app_data_dir = self._get_app_data_dir()
            restored_items = []
            restart_required = False
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                restart_required = ((restore_config and "config.json" in zipf.namelist()) or
                                    (restore_userdb and "data/user_data.db" in zipf.namelist()))
                if restart_required and hasattr(self, 'prospector_panel') and self.prospector_panel.session_active:
                    self.prospector_panel._session_stop()
                # Restore ship presets
                if restore_presets:
                    settings_dir = os.path.join(app_data_dir, "Ship Presets")
                    os.makedirs(settings_dir, exist_ok=True)
                    
                    preset_files = [f for f in zipf.namelist() if f.startswith("Settings/") and f.endswith(".json")]
                    for file_path in preset_files:
                        file_name = os.path.basename(file_path)
                        target_path = os.path.join(settings_dir, file_name)
                        with open(target_path, 'wb') as f:
                            f.write(zipf.read(file_path))
                    
                    if preset_files:
                        restored_items.append(f"{len(preset_files)} Ship Presets")
                        self._refresh_preset_list()  # Refresh preset list
                
                # Restore mining reports
                if restore_reports:
                    reports_dir = os.path.join(app_data_dir, "Reports")
                    os.makedirs(reports_dir, exist_ok=True)
                    
                    report_files = [f for f in zipf.namelist() if f.startswith("Reports/")]
                    for file_path in report_files:
                        target_path = os.path.join(app_data_dir, file_path)
                        target_dir = os.path.dirname(target_path)
                        os.makedirs(target_dir, exist_ok=True)
                        with open(target_path, 'wb') as f:
                            f.write(zipf.read(file_path))
                    
                    if report_files:
                        restored_items.append(f"{len(report_files)} Report Files")
                
                # Restore mining bookmarks
                if restore_bookmarks and "mining_bookmarks.json" in zipf.namelist():
                    target_path = os.path.join(app_data_dir, "mining_bookmarks.json")
                    with open(target_path, 'wb') as f:
                        f.write(zipf.read("mining_bookmarks.json"))
                    restored_items.append("Mining Bookmarks")
                    # Restore BookmarkScreenshots folder
                    from path_utils import get_bookmark_screenshots_dir
                    ss_root = get_bookmark_screenshots_dir()
                    ss_entries = [n for n in zipf.namelist() if n.startswith("BookmarkScreenshots/")]
                    for entry in ss_entries:
                        rel = entry[len("BookmarkScreenshots/"):]
                        if not rel:
                            continue
                        dest = os.path.join(ss_root, rel)
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with open(dest, 'wb') as f:
                            f.write(zipf.read(entry))
                    # Refresh bookmarks display
                    if hasattr(self, 'prospector_panel') and self.prospector_panel:
                        self.prospector_panel._load_bookmarks()
                        self.prospector_panel._refresh_bookmarks()
                
                # Restore VoiceAttack profile
                if restore_va_profile:
                    profile_files = [name for name in zipf.namelist()
                                     if os.path.basename(name) == name and name.endswith("-Profile.vap")]
                    profile_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(app_data_dir)
                    if getattr(sys, 'frozen', False) and os.path.basename(profile_dir).lower() == "configurator":
                        profile_dir = os.path.dirname(profile_dir)
                    if not getattr(sys, 'frozen', False):
                        dev_profile_dir = os.path.join(profile_dir, "Voiceattack Profile")
                        if os.path.isdir(dev_profile_dir):
                            profile_dir = dev_profile_dir
                    os.makedirs(profile_dir, exist_ok=True)
                    for profile_name in profile_files:
                        with open(os.path.join(profile_dir, profile_name), 'wb') as f:
                            f.write(zipf.read(profile_name))
                    if profile_files:
                        restored_items.append("VoiceAttack Profile")

                # Restore user database
                if restore_userdb and "data/user_data.db" in zipf.namelist():
                    userdb_dir = os.path.join(app_data_dir, "data")
                    os.makedirs(userdb_dir, exist_ok=True)
                    target_path = os.path.join(userdb_dir, "user_data.db")
                    import sqlite3
                    import tempfile
                    from contextlib import closing
                    with tempfile.TemporaryDirectory() as restore_dir:
                        snapshot = os.path.join(restore_dir, "user_data.db")
                        with open(snapshot, 'wb') as f:
                            f.write(zipf.read("data/user_data.db"))
                        with closing(sqlite3.connect(snapshot)) as source, closing(sqlite3.connect(target_path)) as target:
                            source.backup(target)
                    restored_items.append("User Database")
                
                # Restore journal files
                if restore_journals:
                    journal_files = [f for f in zipf.namelist() if f.startswith("Journals/") and f.endswith(".log")]
                    
                    if journal_files:
                        # Ask user where to restore journals
                        restore_location = filedialog.askdirectory(
                            title="Select where to restore journal files",
                            initialdir=os.path.expanduser("~")
                        )
                        
                        if restore_location:
                            os.makedirs(restore_location, exist_ok=True)
                            journal_count = 0
                            
                            for file_path in journal_files:
                                file_name = os.path.basename(file_path)
                                target_path = os.path.join(restore_location, file_name)
                                
                                with open(target_path, 'wb') as f:
                                    f.write(zipf.read(file_path))
                                journal_count += 1
                            
                            restored_items.append(f"Journal Files ({journal_count} files)")
                
                # Restore configuration through the shared cache before restarting.
                if restore_config and "config.json" in zipf.namelist():
                    restored_config = json.loads(zipf.read("config.json").decode("utf-8-sig"))
                    _save_cfg(restored_config)
                    flush_config()
                    restored_items.append("Configuration")
            
            if restored_items:
                items_text = ", ".join(restored_items)
                from app_utils import centered_message
                message = t('dialogs.restore_success_msg') + "\n" + items_text
                if restart_required:
                    message += "\n\n" + t('settings.restore_restart')
                centered_message(self, t('dialogs.restore_success'), message)
                self._set_status(f"Restored from backup: {items_text}")
                if restart_required:
                    self._restart_app()
            else:
                messagebox.showwarning("Nothing Restored", "No items were restored from the backup.")
                
        except Exception as e:
            messagebox.showerror("Restore Failed", f"Failed to restore from backup: {str(e)}")

    def _get_app_icon_path(self) -> Optional[str]:
        """Get the app icon path for dialogs - uses centralized app utilities"""
        return get_app_icon_path()

    def _get_app_data_dir(self) -> str:
        """Get the application data directory - uses centralized app utilities"""
        return get_app_data_dir()

    def _setup_ring_finder(self, parent_frame):
        """Setup the ring finder tab"""
        try:
            # Pass the correct app directory to Ring Finder for proper database path
            # Only use va_root path in installer mode, None in dev mode for consistent database location
            app_dir = os.path.join(self.va_root, "app") if getattr(sys, 'frozen', False) and hasattr(self, 'va_root') and self.va_root else None
            # Pass shared user_db from CargoMonitor to avoid duplicate database initialization
            self.ring_finder = RingFinder(parent_frame, self.prospector_panel, app_dir, ToolTip, self.distance_calculator, self.cargo_monitor.user_db)
            
            # Sync auto-search state from file so both checkboxes match at startup
            if hasattr(self, 'auto_search_enabled') and hasattr(self.ring_finder, 'auto_search_var'):
                file_state = self.ring_finder.auto_search_var.get()
                self.auto_search_enabled.set(file_state)
            
            # Check if there were any pending hotspot additions while Ring Finder was being created
            if getattr(self, '_pending_ring_finder_refresh', False):
                self._refresh_ring_finder()
            
            # Update mining missions tab with references (it's created before ring_finder)
            if hasattr(self, 'prospector_panel') and self.prospector_panel:
                if hasattr(self.prospector_panel, 'missions_tab') and self.prospector_panel.missions_tab:
                    self.prospector_panel.missions_tab.set_ring_finder(self.ring_finder)
                    self.prospector_panel.missions_tab.set_main_app(self)
                    self.prospector_panel.missions_tab.set_cargo_monitor(self.cargo_monitor)
                
        except Exception as e:
            import traceback
            log.error(f"Ring finder setup failed: {e}")
            traceback.print_exc()

    # ==================== FLEET CARRIER TAB ====================
    def _build_fleet_carrier_tab(self, frame: ttk.Frame) -> None:
        """Build the Fleet Carrier tab - live FC status from journal events"""
        from fleet_carrier_tab import FleetCarrierTab
        from fleet_carrier_tracker import get_fleet_carrier_tracker
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.fleet_carrier_tab = FleetCarrierTab(frame)
        self.fleet_carrier_tab.grid(row=0, column=0, sticky="nsew")
        self.fleet_carrier_tab.set_tracker(get_fleet_carrier_tracker())

    PP_FETCH_MAX_BATCH = 10
    PP_FETCH_DELAY_SECS = 1.5

    def _on_journal_pledge_events(self, events):
        for event in events:
            power = JournalParser.pledged_power_from_event(event)
            if power:
                self._apply_journal_pledge(power, event.get('timestamp', ''))

    def _apply_startup_pledge(self):
        """Apply the startup journal pledge lookup once its worker has finished."""
        result = getattr(self, '_journal_pledge_result', None)
        if result is None:
            return  # no journal reader
        if not result:
            self.after(250, self._apply_startup_pledge)
            return
        if result[0]:
            self._apply_journal_pledge(*result[0])

    def _apply_journal_pledge(self, power, timestamp):
        """Set My Power from a journal pledge event. Only an event newer than the last
        one applied changes it, so a manual pick stays until the next login."""
        from config import (load_player_power, save_player_power,
                            load_player_power_journal_time, save_player_power_journal_time)
        if timestamp and timestamp <= load_player_power_journal_time():
            return
        if timestamp:
            save_player_power_journal_time(timestamp)
        if power == load_player_power():
            return
        save_player_power(power)
        log.info(f"Pledged power from journal: {power}")
        var = getattr(self, 'sysfinder_my_power_var', None)
        if var is not None:
            shown = 'Select your pledge...' if power == JournalParser.NOT_PLEDGED else power
            var.set(self._sysfinder_option_label(shown))
            if getattr(self, '_sysfinder_ref_status', None):
                self._update_sysfinder_ref_labels(self._sysfinder_ref_status)
        ring_finder = getattr(self, 'ring_finder', None)
        if ring_finder is not None and hasattr(ring_finder, '_mm_sync_power'):
            ring_finder._mm_sync_power()

    def _save_player_power(self):
        """Persist the My Power dropdown selection to config"""
        from config import save_player_power
        save_player_power(self._sysfinder_option_value(self.sysfinder_my_power_var.get()))
        if getattr(self, '_sysfinder_ref_status', None):
            self._update_sysfinder_ref_labels(self._sysfinder_ref_status)
        ring_finder = getattr(self, 'ring_finder', None)
        if ring_finder is not None and hasattr(ring_finder, '_mm_power_var'):
            ring_finder._mm_sync_power()

    def _check_for_updates_startup(self):
        """Check for updates on startup (automatic check) - checks every time app starts"""
        current_version = get_version()
        logging.info(f"[UPDATE_CHECK] Starting update check... Current version: {current_version}")
        print(f"Checking for updates... Current version: {current_version}")
        
        self.update_checker.check_for_updates_async(self)

    def _manual_update_check(self):
        """Manually check for updates (from menu)"""
        self.update_checker.manual_check(self)
    
    def _check_va_profile_update(self):
        """Check for VoiceAttack profile updates on startup"""
        import threading
        
        def do_check():
            result = self._check_va_profile_update_impl()
            if result:
                # Schedule dialog on main thread
                version_info, profile_path = result
                self.after(0, lambda: self._show_va_profile_update_dialog(
                    version_info.get('current'), 
                    version_info.get('new'), 
                    profile_path
                ))
        
        # Run check in background thread to avoid blocking UI
        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()
    
    def _check_va_profile_update_impl(self):
        """Implementation of VA profile update check - runs in background thread"""
        # DEBUG: Write to file for troubleshooting
        debug_file = None
        try:
            from path_utils import get_app_data_dir
            debug_file = os.path.join(get_app_data_dir(), "va_profile_check_debug.txt")
            with open(debug_file, 'w') as f:
                f.write("=== VA Profile Check Debug Log ===\n")
        except:
            pass
        
        def debug_log(msg):
            if debug_file:
                try:
                    with open(debug_file, 'a') as f:
                        f.write(f"{msg}\n")
                except:
                    pass
            logging.info(f"[VA_PROFILE] {msg}")
        
        try:
            import os  # Ensure os is available throughout this function
            debug_log("Check started")
            
            # Determine VA folder - use configured root or try to find it
            va_folder = None
            if hasattr(self, 'va_root') and self.va_root:
                va_folder = self.va_root
                debug_log(f"Using configured VA root: {va_folder}")
            else:
                debug_log("No va_root attribute, trying standard location")
                # Try to find VA Apps/EliteMining folder for testing
                # Standard VA location: C:\Users\<user>\AppData\Local\VoiceAttack.com\VoiceAttack\Apps\EliteMining
                local_appdata = os.getenv('LOCALAPPDATA')
                if local_appdata:
                    test_path = os.path.join(local_appdata, 'VoiceAttack.com', 'VoiceAttack', 'Apps', 'EliteMining')
                    if os.path.exists(test_path):
                        va_folder = test_path
                        debug_log(f"Found VA folder at standard location: {test_path}")
            
            if not va_folder or not os.path.exists(va_folder):
                debug_log(f"No VA folder found, exiting (va_folder={va_folder})")
                return
            
            debug_log(f"VA folder confirmed: {va_folder}")
            
            from path_utils import get_app_data_dir
            import json
            import glob
            import re
            
            # State file to track installed profile version
            state_file = os.path.join(get_app_data_dir(), "va_profile_state.json")
            
            # Get the new profile file that came with this installation
            # va_folder is already the EliteMining folder
            # Look for versioned profile: EliteMining v*-Profile.vap
            profile_pattern = os.path.join(va_folder, "EliteMining v*-Profile.vap")
            profile_files = glob.glob(profile_pattern)
            
            if not profile_files:
                # Fallback to old naming convention
                old_profile = os.path.join(va_folder, "EliteMining-Profile.vap")
                if os.path.exists(old_profile):
                    profile_files = [old_profile]
            
            if not profile_files:
                debug_log(f"No profile file found in: {va_folder}")
                return
            
            debug_log(f"Found {len(profile_files)} profile file(s): {profile_files}")
            
            # If multiple profile files, pick the one with highest version
            def extract_version(filepath):
                """Extract version number from profile filename"""
                basename = os.path.basename(filepath)
                match = re.search(r'v([\d.]+)-Profile\.vap', basename)
                if match:
                    return match.group(1)
                return "0"
            
            # Sort by version (highest first) and pick the newest
            from packaging import version as pkg_version
            try:
                profile_files.sort(key=lambda f: pkg_version.parse(extract_version(f)), reverse=True)
            except:
                # Fallback to string sort if packaging not available
                profile_files.sort(key=lambda f: extract_version(f), reverse=True)
            
            new_profile_path = profile_files[0]
            debug_log(f"Using profile: {new_profile_path}")
            
            # Parse new profile to get its version
            try:
                from va_profile_parser import VAProfileParser
                parser = VAProfileParser()
                tree = parser.parse(new_profile_path)
                new_version = parser.get_profile_version(tree)
                debug_log(f"Profile version: {new_version}")
                
                if new_version == "unknown":
                    debug_log("Could not extract version from profile, exiting")
                    return
                
                # Load last known installed version from state file
                installed_version = None
                if os.path.exists(state_file):
                    try:
                        with open(state_file, 'r') as f:
                            state = json.load(f)
                            installed_version = state.get('installed_version')
                        debug_log(f"State file exists, installed_version: {installed_version}")
                    except Exception as e:
                        debug_log(f"Error reading state file: {e}")
                else:
                    debug_log("No state file found (first run)")
                
                debug_log(f"Installed: {installed_version}, Available: {new_version}")
                
                # Helper to check if new version is actually newer
                def is_newer_version(new_ver, old_ver):
                    """Return True only if new_ver > old_ver using proper version comparison"""
                    try:
                        return pkg_version.parse(new_ver) > pkg_version.parse(old_ver)
                    except:
                        return new_ver != old_ver
                
                # Check if this is truly a first install or an existing user
                if installed_version is None:
                    # No state file - check if old profile exists (existing user from pre-v4.76)
                    # Old naming convention: EliteMining-Profile.vap (no version in filename)
                    # New naming convention: EliteMining v4.76-Profile.vap (version in filename)
                    old_profile = os.path.join(va_folder, "EliteMining-Profile.vap")
                    
                    if os.path.exists(old_profile):
                        # Old profile exists - this is an existing user upgrading from v4.75 or earlier
                        debug_log(f"Found old profile format: {old_profile}")
                        try:
                            old_tree = parser.parse(old_profile)
                            old_version = parser.get_profile_version(old_tree)
                            debug_log(f"Old profile version: {old_version}")
                            
                            if old_version != "unknown":
                                # Return info to show update dialog
                                debug_log(f"Upgrade from old profile: {old_version} -> {new_version}")
                                return ({'current': old_version, 'new': new_version}, new_profile_path)
                            else:
                                # Couldn't parse old version - show dialog anyway for existing users
                                debug_log("Existing user (old profile, version unknown) - showing dialog")
                                return ({'current': None, 'new': new_version}, new_profile_path)
                        except Exception as e:
                            debug_log(f"Error parsing old profile: {e} - showing dialog anyway")
                            return ({'current': None, 'new': new_version}, new_profile_path)
                    else:
                        # No old profile - true first install (only new versioned profile exists)
                        debug_log("True first install - creating state file silently")
                        self._save_va_profile_state(state_file, new_version)
                elif is_newer_version(new_version, installed_version):
                    # New version is actually newer - show update dialog with keybind preservation
                    debug_log(f"Update available: {installed_version} -> {new_version}")
                    return ({'current': installed_version, 'new': new_version}, new_profile_path)
                else:
                    debug_log(f"Profile up to date (installed: {installed_version}, available: {new_version})")
                    
            except Exception as e:
                logging.error(f"[VA_PROFILE] Error checking new profile version: {e}")
                
        except Exception as e:
            logging.error(f"[VA_PROFILE] Error checking for profile update: {e}")
        
        return None  # No update needed
    
    def _save_va_profile_state(self, state_file, version):
        """Save the installed VA profile version to state file"""
        import json
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            with open(state_file, 'w') as f:
                json.dump({'installed_version': version}, f)
        except Exception as e:
            logging.error(f"[VA_PROFILE] Error saving state: {e}")
    
    def _show_va_profile_update_dialog(self, current_version, new_version, profile_path):
        """Show dialog for VA profile update with keybind preservation option"""
        # Defer dialog to ensure UI is fully ready
        def show_when_ready():
            try:
                # Check if app is fully loaded and window is mapped
                if not getattr(self, '_app_fully_loaded', False) or not self.winfo_ismapped():
                    # Not ready yet, try again later
                    self.after(1000, show_when_ready)
                    return
                    
                # Additional safety: make sure window is visible and has size
                if self.winfo_width() < 100 or self.winfo_height() < 100:
                    self.after(1000, show_when_ready)
                    return

                # Wait for any other startup dialog (e.g. hotspot database notice) to close first
                if getattr(self, '_startup_dialog_active', False):
                    self.after(1000, show_when_ready)
                    return

                self._show_va_profile_update_dialog_impl(current_version, new_version, profile_path)
            except Exception as e:
                logging.error(f"[VA_PROFILE] Error showing dialog: {e}")
        
        self.after(2000, show_when_ready)
    
    def _show_va_profile_update_dialog_impl(self, current_version, new_version, profile_path):
        """Implementation of VA profile update dialog"""
        try:
            logging.info(f"[VA_PROFILE] Showing update dialog: {current_version} -> {new_version}")
            
            # Ensure window is fully ready - use multiple update calls
            for _ in range(3):
                self.update()
                self.update_idletasks()
            
            from app_utils import centered_askyesno

            # Show update message with keybind preservation info
            current_display = current_version if current_version else "Unknown"
            message = t("voiceattack.profile_update_message").format(
                current=current_display,
                new=new_version
            )
            
            result = centered_askyesno(
                self,
                t("voiceattack.profile_update_title"),
                message,
                require_answer=True
            )
            
            logging.info(f"[VA_PROFILE] Update dialog answer: {'Yes' if result else 'No'}")
            if result:
                self._va_profile_auto_merge(current_version, new_version, profile_path)
            else:
                self._mark_va_profile_handled(new_version)

        except Exception as e:
            logging.error(f"[VA_PROFILE] Error showing update dialog: {e}")

    def _mark_va_profile_handled(self, new_version):
        """Save the new version only once the update flow has finished, so an interrupted update is offered again"""
        if not new_version:
            return
        from path_utils import get_app_data_dir
        state_file = os.path.join(get_app_data_dir(), "va_profile_state.json")
        self._save_va_profile_state(state_file, new_version)
        logging.info(f"[VA_PROFILE] Saved new version to state: {new_version}")

    def _va_profile_auto_merge(self, current_version, new_version, profile_path):
        """Read the player's current bindings from VoiceAttack's data file; any failure falls back to the export flow"""
        import threading
        from app_utils import centered_askyesno

        try:
            from va_process_manager import VAProcessManager
            while VAProcessManager.is_running():
                closed = centered_askyesno(self, t("voiceattack.close_va_title"), t("voiceattack.close_va_message"),
                                           require_answer=True)
                logging.info(f"[VA_PROFILE] Close VoiceAttack prompt answer: {'Yes' if closed else 'No'}")
                if not closed:
                    self._va_profile_export_merge(new_version, profile_path)
                    return
            include_live = True
        except Exception as e:
            # Without a running check, read only the backups VoiceAttack has finished writing
            logging.warning(f"[VA_PROFILE] Could not check whether VoiceAttack is running: {e}")
            include_live = False

        logging.info(f"[VA_PROFILE] Reading VoiceAttack bindings (live file allowed: {include_live})")

        def worker():
            try:
                from va_profile_reader import read_profile_bindings
                read = read_profile_bindings(installed_version=current_version, include_live=include_live)
            except Exception as e:
                logging.error(f"[VA_PROFILE] Reading VoiceAttack bindings failed: {e}")
                read = None
            self.after(0, lambda: self._va_profile_auto_merge_complete(read, new_version, profile_path))

        threading.Thread(target=worker, daemon=True).start()

    def _va_profile_auto_merge_complete(self, read, new_version, profile_path):
        import shutil
        from app_utils import centered_askyesno, centered_message

        if read is None:
            import va_profile_reader
            tie = (va_profile_reader.last_failure or "").startswith(va_profile_reader.TIE_PREFIX)
            logging.info(f"[VA_PROFILE] Reading VoiceAttack bindings failed ({'profiles tie' if tie else 'other'}), "
                         "falling back to export")
            centered_message(self, t("voiceattack.profile_update_title"),
                             t("voiceattack.profiles_tie_message" if tie else "voiceattack.read_failed_message"))
            self._va_profile_export_merge(new_version, profile_path)
            return

        try:
            chosen = next((p for p in read.candidates if p.id == read.profile_id), None)
            bound = chosen.bound if chosen else 0
            logging.info(f"[VA_PROFILE] Read '{read.profile_name}' ({read.reason}) with {bound} shortcuts "
                         f"from {os.path.basename(read.backup_path)}")
            # Ask only when the profile was a guess among several; otherwise the success dialog names it
            if read.guessed:
                confirm = t("voiceattack.confirm_read_message").format(name=read.profile_name, count=bound)
                confirmed = centered_askyesno(self, t("voiceattack.confirm_read_title"), confirm,
                                              yes_text=t("voiceattack.yes_recommended"), require_answer=True)
                logging.info(f"[VA_PROFILE] Profile confirmation answer: {'Yes' if confirmed else 'No'}")
                if not confirmed:
                    self._va_profile_export_merge(new_version, profile_path)
                    return
            try:
                self._merge_profiles_with_keybinds(read.xml_path, profile_path, new_version,
                                                   source_name=read.profile_name)
                self._mark_va_profile_handled(new_version)
            except Exception as e:
                logging.error(f"[VA_PROFILE] Merge from VoiceAttack data failed: {e}")
                centered_message(self, t("voiceattack.profile_update_title"), t("voiceattack.read_failed_message"))
                self._va_profile_export_merge(new_version, profile_path)
        finally:
            shutil.rmtree(os.path.dirname(read.xml_path), ignore_errors=True)

    def _va_profile_export_merge(self, new_version, profile_path):
        """Fallback: the player exports the current profile as XML and selects it"""
        logging.info("[VA_PROFILE] Export flow started")
        try:
            self._va_profile_export_merge_steps(new_version, profile_path)
        finally:
            self._mark_va_profile_handled(new_version)

    def _va_profile_export_merge_steps(self, new_version, profile_path):
        from app_utils import centered_message
        from tkinter import filedialog

        # Get the EliteMining folder path for instructions
        elitemining_folder = self.va_root if hasattr(self, 'va_root') and self.va_root else profile_path.rsplit(os.sep, 1)[0]
        suggested_filename = "EliteMining_old-Profile.vap"

        # Ask user to select their exported XML profile
        export_instructions = t("voiceattack.export_instructions").format(
            folder=elitemining_folder,
            filename=suggested_filename
        )

        centered_message(self, t("voiceattack.export_step_title"), export_instructions)

        # Open file dialog starting in the EliteMining folder
        old_profile_path = filedialog.askopenfilename(
            parent=self,
            title=t("voiceattack.select_exported_profile"),
            filetypes=[("VoiceAttack Profile", "*.vap"), ("All files", "*.*")],
            initialdir=elitemining_folder
        )
        logging.info(f"[VA_PROFILE] Exported profile {'selected' if old_profile_path else 'not selected'}")

        if old_profile_path:
            # Try to merge keybinds
            try:
                self._merge_profiles_with_keybinds(old_profile_path, profile_path, new_version)
            except Exception as e:
                logging.error(f"[VA_PROFILE] Merge failed: {e}")
                centered_message(
                    self,
                    "Merge Failed",
                    f"Could not merge keybinds automatically:\n{e}\n\n"
                    f"Please import the new profile manually from:\n{profile_path}"
                )
        else:
            # User cancelled - show manual instructions
            manual_instructions = f"""Manual update:

Import the new profile from:
{profile_path}

Your keybinds will need to be reconfigured manually."""
            centered_message(self, "Manual Update", manual_instructions)

    def _merge_profiles_with_keybinds(self, old_profile_path, new_profile_path, new_version, source_name=None):
        """Merge keybinds from old profile into new profile"""
        from va_profile_parser import VAProfileParser
        from va_keybind_extractor import VAKeybindExtractor
        from va_keybind_applier import VAKeybindApplier
        from app_utils import centered_message
        from path_utils import get_app_data_dir
        import shutil
        from datetime import datetime
        
        logging.info(f"[VA_PROFILE] Merging keybinds from {old_profile_path} to {new_profile_path}")
        
        parser = VAProfileParser()
        extractor = VAKeybindExtractor()
        applier = VAKeybindApplier()
        
        # Step 1: Parse old profile and extract keybinds
        old_tree = parser.parse(old_profile_path)
        keybinds = extractor.extract(old_tree)
        keybind_count = len(keybinds)
        logging.info(f"[VA_PROFILE] Extracted {keybind_count} keybinds from old profile")
        
        if keybind_count == 0 and not extractor.skipped:
            centered_message(
                self,
                t("voiceattack.no_keybinds_title"),
                t("voiceattack.no_keybinds_message")
            )
            return
        
        # Step 2: Parse new profile
        new_tree = parser.parse(new_profile_path)
        
        # Step 3: Apply keybinds to new profile
        merged_tree = applier.apply(new_tree, keybinds)
        
        # Step 4: Create backup of original new profile
        backup_dir = os.path.join(get_app_data_dir(), "Backups")
        os.makedirs(backup_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Step 5: Save merged profile (overwrite the new profile in place)
        # IMPORTANT: Save as uncompressed XML so user can import it in VoiceAttack
        parser.save(merged_tree, new_profile_path, compress=False)
        logging.info(f"[VA_PROFILE] Merged profile saved to: {new_profile_path}")
        
        # Step 6: Show success message with applied count and the bindings that were not applied
        result = applier.last_result
        not_applied = list(result.not_applied) + list(extractor.skipped)
        not_applied_text = ""
        if not_applied:
            max_listed = 15
            lines = [
                "  - {}: {}".format(name.split(";")[0].strip(), t(f"voiceattack.merge_reason_{reason}"))
                for name, reason in not_applied[:max_listed]
            ]
            if len(not_applied) > max_listed:
                lines.append(t("voiceattack.merge_not_applied_more").format(n=len(not_applied) - max_listed))
            not_applied_text = "\n\n" + t("voiceattack.merge_not_applied_header").format(
                n=len(not_applied), list="\n".join(lines)
            )
        logging.info(f"[VA_PROFILE] Merge applied {len(result.applied)} of {keybind_count} keybinds, "
                     f"{len(not_applied)} not applied")
        centered_message(
            self,
            t("voiceattack.merge_success_title"),
            t("voiceattack.merge_success_message").format(
                count=len(result.applied),
                source=t("voiceattack.merge_source").format(name=source_name) if source_name else "",
                not_applied=not_applied_text,
                path=new_profile_path
            )
        )
    
    def _newest_shipped_va_profile(self):
        """Newest 'EliteMining v*-Profile.vap' in the EliteMining folder, or None"""
        import glob
        from va_profile_parser import VAProfileParser

        folder = self.va_root if hasattr(self, 'va_root') and self.va_root else None
        if not folder:
            return None

        def key(path):
            version = VAProfileParser.version_from_name(os.path.basename(path))
            try:
                return tuple(int(p) for p in version.split('.'))
            except (AttributeError, ValueError):
                return ()

        files = glob.glob(os.path.join(folder, "EliteMining v*-Profile.vap"))
        return max(files, key=key) if files else None

    def _manual_va_keybind_preserve(self):
        """Triggered from Settings tab - read the current shortcuts from VoiceAttack and merge them into the newest profile"""
        profile_path = self._newest_shipped_va_profile()
        if profile_path:
            logging.info(f"[VA_PROFILE] Manual shortcut merge into {os.path.basename(profile_path)}")
            self._va_profile_auto_merge(None, None, profile_path)
        else:
            self._manual_va_keybind_preserve_files()

    def _manual_va_keybind_preserve_files(self):
        """No shipped profile found: the player picks the exported old profile and the new profile"""
        try:
            from app_utils import centered_message
            from tkinter import filedialog

            elitemining_folder = self.va_root if hasattr(self, 'va_root') and self.va_root else os.path.expanduser("~")
            suggested_filename = "EliteMining_old-Profile.vap"

            # Step 1: Show instructions to export old profile
            export_instructions = t("voiceattack.export_instructions").format(
                folder=elitemining_folder,
                filename=suggested_filename
            )
            centered_message(self, t("voiceattack.export_step_title"), export_instructions)

            # Step 2: Select old profile (with custom keybinds)
            old_profile_path = filedialog.askopenfilename(
                parent=self,
                title=t("voiceattack.select_exported_profile"),
                filetypes=[("VoiceAttack Profile", "*.vap"), ("All files", "*.*")],
                initialdir=elitemining_folder
            )
            if not old_profile_path:
                return

            # Step 3: Select new profile (the target to apply keybinds to)
            new_profile_path = filedialog.askopenfilename(
                parent=self,
                title=t("voiceattack.select_new_profile"),
                filetypes=[("VoiceAttack Profile", "*.vap"), ("All files", "*.*")],
                initialdir=elitemining_folder
            )
            if not new_profile_path:
                return

            # Step 4: Merge
            try:
                self._merge_profiles_with_keybinds(old_profile_path, new_profile_path, None)
            except Exception as e:
                logging.error(f"[VA_PROFILE] Manual merge failed: {e}")
                from app_utils import centered_message as cm
                cm(self, "Merge Failed", f"Could not merge keybinds:\n{e}\n\nVerify both profile files are valid.")
        except Exception as e:
            logging.error(f"[VA_PROFILE] Error in manual keybind preserve: {e}")

    def _background_journal_catchup(self):
        """Background scan of journals at startup.
        
        First install: Full scan of all journals
        Subsequent runs: Scan only last 6 months of journals
        
        This runs on a background thread so it doesn't block the UI.
        
        NOTE: If the visit counts migration ran, it already scanned all journals
        for visits, so we only need to scan for hotspots/ring data here.
        """
        import threading
        import glob
        from datetime import datetime, timedelta
        
        # Skip if update is in progress (app will restart anyway)
        if getattr(self, '_update_in_progress', False):
            print("[JOURNAL] Skipping scan - update in progress")
            return
        
        # Check if migration already ran this session (it scans all journals)
        migration_ran = getattr(self, '_migration_completed', False)
        
        def catchup_scan():
            full_scan_pending = False
            try:
                # Check again in case update started while we were waiting
                if getattr(self, '_update_in_progress', False):
                    print("[JOURNAL] Scan cancelled - update in progress")
                    return
                
                # If migration already ran, skip the visit counting parts
                # Migration already fixed visit counts from ALL journals
                if migration_ran:
                    print("[JOURNAL] Migration already ran - skipping redundant visit scan")
                    # Still trigger location refresh (journal scan for current system + FC)
                    if hasattr(self, '_distance_refresh_locations'):
                        self.after(500, self._distance_refresh_locations)
                    return
                    
                self.after(0, lambda: self._set_journal_scan_status(t('status_bar.journal_scanning'), 0))
                
                # Get journal directory
                journal_dir = self.cargo_monitor.journal_dir
                if not journal_dir or not os.path.isdir(journal_dir):
                    print("[JOURNAL] No journal directory found")
                    self.after(0, lambda: self._set_journal_scan_status(t('status_bar.journal_no_folder')))
                    return
                
                # Get ALL journals
                pattern = os.path.join(journal_dir, "Journal.*.log")
                all_journals = sorted(glob.glob(pattern))
                
                if not all_journals:
                    print("[JOURNAL] No journal files found")
                    log.info("No journal files found")
                    self.after(0, lambda: self._set_journal_scan_status(t('status_bar.journal_no_files')))
                    return
                
                # Determine if this is first install or migration needed
                scan_type = self._is_first_install()  # Returns 'first_install', 'migration', or 'none'
                
                if scan_type in ('first_install', 'migration'):
                    # First install or migration: scan ALL journals - show progress dialog
                    journals_to_scan = all_journals
                    print(f"[STARTUP] {scan_type} - full scan of {len(journals_to_scan)} journals...")
                    log.info(f"Startup: {scan_type} - full scan of {len(journals_to_scan)} journals")
                    
                    # Show progress dialog (runs on main thread)
                    self.after(0, lambda j=journals_to_scan, st=scan_type: self._run_full_scan_with_dialog(j, st))
                    full_scan_pending = True
                    return  # Don't continue - dialog handles the scan
                else:
                    # Subsequent runs: only scan journal content written since the last
                    # successful scan. The 180-day window is kept purely as a safety net
                    # for when no checkpoint exists yet or the checkpointed file is gone.
                    checkpoint = self._load_journal_scan_checkpoint()
                    journals_to_scan, resume_offsets = self._get_new_journals_since_checkpoint(all_journals, checkpoint)
                    if journals_to_scan is not None and not self._fc_carrier_data_has_history():
                        # Checkpoint exists but the Fleet Carrier location/jump history
                        # cache is empty (missing/deleted last_carrier_data.json) - the
                        # incremental scan alone would never backfill it, so fall back
                        # to the 180-day scan once to rebuild it from journal content.
                        journals_to_scan = None
                    if journals_to_scan is None:
                        cutoff_date = datetime.now() - timedelta(days=180)
                        journals_to_scan = self._filter_journals_by_date(all_journals, cutoff_date)
                        resume_offsets = {}
                        print(f"[STARTUP] Regular scan (no checkpoint): {len(journals_to_scan)} of {len(all_journals)} journals (last 6 months)")
                        log.info(f"Startup: Regular scan (no checkpoint) - {len(journals_to_scan)} of {len(all_journals)} journals (last 6 months)")
                    else:
                        print(f"[STARTUP] Regular scan: {len(journals_to_scan)} new journal file(s) since last scan")
                        log.info(f"Startup: Regular scan - {len(journals_to_scan)} new journal file(s) since last scan")
                    self.after(0, lambda n=len(journals_to_scan): self._set_journal_scan_status(t('status_bar.journal_scanning_count').format(n=n) if n else t('status_bar.journal_up_to_date'), 0 if n else 3000))

                scanned_checkpoint = self._process_journals_for_catchup(journals_to_scan, is_full_sync=False, resume_offsets=resume_offsets)
                if scanned_checkpoint:
                    self._save_journal_scan_checkpoint(*scanned_checkpoint)

                # Historical catch-up is done — from here on, FSDJump/Location events reaching
                # the live journal watcher are genuinely live (current PP2.0-era session), so it's
                # now safe to enable live-only inference (see journal_parser._upsert_pp_from_event).
                if hasattr(self, 'cargo_monitor') and self.cargo_monitor and self.cargo_monitor.journal_parser:
                    self.cargo_monitor.journal_parser.is_live_monitoring = True

            except Exception as e:
                log.error(f"[JOURNAL] ERROR: {e}")
                self.after(0, lambda: self._set_journal_scan_status(t('status_bar.journal_scan_failed')))
                import traceback
                traceback.print_exc()
            finally:
                if not full_scan_pending:
                    self.cargo_monitor.journal_parser.finish_carrier_catchup()
        
        # Run on background thread
        thread = threading.Thread(target=catchup_scan, daemon=True)
        thread.start()
    
    def _is_first_install(self) -> str:
        """Check if this is a first install or if migration is needed
        
        Returns:
            'first_install' - No visits recorded (new user)
            'migration' - Has visits but needs full rescan (update)
            'none' - No scan needed
        """
        try:
            if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                user_db = self.cargo_monitor.user_db
                if user_db:
                    # Check if database has any visits recorded
                    count = user_db.get_total_visits_count()
                    print(f"[STARTUP] Visit count in database: {count}")
                    if count == 0:
                        print("[STARTUP] No visits in database - first install")
                        return 'first_install'
                    
                    # Check if full scan was done for this version using JSON file
                    try:
                        from path_utils import get_app_data_dir
                        from version import get_version
                        import json
                        
                        scan_status_file = os.path.join(get_app_data_dir(), "last_full_scan.json")
                        current_version = get_version()
                        print(f"[STARTUP] Checking scan status file: {scan_status_file}")
                        
                        if os.path.exists(scan_status_file):
                            with open(scan_status_file, 'r') as f:
                                scan_data = json.load(f)
                                last_scan_version = scan_data.get('version', '')
                                
                                # Full scan already done for some version - no need to rescan
                                # The v4.7.2 migration features (CSV imports, hotspot merge) 
                                # are handled separately in user_database.py with their own tracking.
                                # Only the first full scan matters, subsequent updates don't need full rescan.
                                if last_scan_version:
                                    print(f"[STARTUP] Full scan already done (v{last_scan_version}), no migration needed")
                                    return 'none'
                                else:
                                    print(f"[STARTUP] Empty scan version, needs migration")
                                    return 'migration'
                        else:
                            # No scan status file = needs full scan (update from pre-v4.7.2)
                            print(f"[STARTUP] No scan status file found, needs migration for v{current_version}")
                            return 'migration'
                            
                    except Exception as e:
                        log.error(f"[STARTUP] Scan status check error: {e}")
                        # If we can't check, assume needs migration
                        return 'migration'
                    
                    return 'none'  # Has visits and scan already done
        except Exception as e:
            log.error(f"[STARTUP] _is_first_install exception: {e}")
        return 'first_install'  # Assume first install if we can't determine

    def _get_journal_scan_state_path(self) -> str:
        """Path to the incremental journal catch-up checkpoint file"""
        from path_utils import get_app_data_dir
        return os.path.join(get_app_data_dir(), "journal_scan_state.json")

    def _load_journal_scan_checkpoint(self) -> dict:
        """Load the last-processed journal filename/byte-offset checkpoint"""
        import json
        path = self._get_journal_scan_state_path()
        try:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            log.error(f"[JOURNAL] Failed to read scan checkpoint: {e}")
        return {}

    def _save_journal_scan_checkpoint(self, last_file: str, last_offset: int) -> None:
        """Persist the newest journal filename and its byte size after a scan"""
        import json
        path = self._get_journal_scan_state_path()
        try:
            with open(path, 'w') as f:
                json.dump({"last_file": last_file, "last_offset": last_offset}, f)
        except Exception as e:
            log.error(f"[JOURNAL] Failed to save scan checkpoint: {e}")

    def _fc_carrier_data_has_history(self) -> bool:
        """Whether the persisted Fleet Carrier cache already has a location or jump history.

        Used to detect a desync between journal_scan_state.json (incremental scan
        checkpoint) and last_carrier_data.json (FC cache) - e.g. the FC cache was
        deleted/never written even though a scan checkpoint already exists.
        """
        try:
            cd = self.cargo_monitor.journal_parser.carrier_data
        except AttributeError:
            return True
        if not cd:
            return True
        return bool(cd.get('system') or cd.get('jump_history'))

    def _get_new_journals_since_checkpoint(self, all_journals: list, checkpoint: dict):
        """Return (journals_to_scan, resume_offsets) for files newer than the checkpoint.

        Returns (None, {}) if the checkpoint is missing or its file is no longer
        on disk, signaling the caller to fall back to the 180-day safety net scan.
        """
        last_file = checkpoint.get('last_file')
        if not last_file:
            return None, {}

        last_path = None
        for p in all_journals:
            if os.path.basename(p) == last_file:
                last_path = p
                break
        if last_path is None:
            return None, {}

        idx = all_journals.index(last_path)
        last_offset = checkpoint.get('last_offset', 0)
        resume_offsets = {}
        journals_to_scan = []

        try:
            current_size = os.path.getsize(last_path)
        except OSError:
            current_size = 0
        if current_size < last_offset:
            last_offset = 0
        if current_size > last_offset:
            journals_to_scan.append(last_path)
            resume_offsets[last_path] = last_offset

        journals_to_scan.extend(all_journals[idx + 1:])
        return journals_to_scan, resume_offsets

    def _run_full_scan_with_dialog(self, journals, scan_type='first_install'):
        """Run full journal scan with a progress dialog

        Args:
            journals: List of journal files to scan
            scan_type: 'first_install' or 'migration'
        """
        import threading
        from localization import t
        from app_utils import get_app_icon_path

        # Wait for any other startup dialog (hotspot notice, VA profile update) to close
        # first - this dialog grabs input and can't be closed by the user, so showing it
        # alongside another modal leaves that other dialog stuck and unclickable
        if getattr(self, "_startup_dialog_active", False):
            self.after(1000, lambda: self._run_full_scan_with_dialog(journals, scan_type))
            return
        self._startup_dialog_active = True

        # Get theme colors
        if self.current_theme == "elite_orange":
            bg_color = "#000000"
            fg_color = "#ff8c00"
            text_color = "#ffffff"
            dim_color = "#888888"
        else:
            bg_color = "#1e1e1e"
            fg_color = "#569cd6"
            text_color = "#ffffff"
            dim_color = "#888888"
        
        # Choose text based on scan type
        if scan_type == 'migration':
            title_key = 'dialogs.migration_title'
            scanning_key = 'dialogs.migration_scanning'
            patience_key = 'dialogs.migration_patience'
        else:
            title_key = 'dialogs.first_install_title'
            scanning_key = 'dialogs.first_install_scanning'
            patience_key = 'dialogs.first_install_patience'
        
        # Create progress dialog
        progress_dialog = tk.Toplevel(self)
        progress_dialog.withdraw()  # Hide while setting up
        progress_dialog.title(t(title_key))
        progress_dialog.resizable(False, False)
        progress_dialog.transient(self)
        progress_dialog.configure(bg=bg_color)
        
        # Set app icon (same method as other dialogs)
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                progress_dialog.iconbitmap(icon_path)
        except Exception:
            pass
        
        # Prevent closing
        progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        
        # Title label
        title_label = tk.Label(
            progress_dialog,
            text="⏳ " + t(scanning_key),
            font=self._scaled_font(11, "bold"),
            bg=bg_color,
            fg=fg_color
        )
        title_label.pack(pady=(20, 5))
        
        # Subtitle / patience message
        subtitle_label = tk.Label(
            progress_dialog,
            text=t(patience_key),
            font=self._scaled_font(9, "italic"),
            bg=bg_color,
            fg=dim_color
        )
        subtitle_label.pack(pady=(0, 10))
        
        # Configure progress bar style for orange theme
        style = ttk.Style()
        if self.current_theme == "elite_orange":
            style.configure("Migration.Horizontal.TProgressbar", 
                          background="#ff8c00", 
                          troughcolor="#333333",
                          bordercolor="#ff6600",
                          lightcolor="#ff9933",
                          darkcolor="#ff6600")
        
        # Progress bar
        progress_var = tk.DoubleVar(value=0)
        progress_bar = ttk.Progressbar(
            progress_dialog, 
            variable=progress_var, 
            maximum=100,
            length=350,
            mode='determinate',
            style="Migration.Horizontal.TProgressbar"
        )
        progress_bar.pack(pady=10)
        
        # Status label
        status_var = tk.StringVar(value=t('dialogs.please_wait'))
        status_label = tk.Label(
            progress_dialog,
            textvariable=status_var,
            font=self._scaled_font(9),
            bg=bg_color,
            fg=dim_color
        )
        status_label.pack(pady=(5, 15))
        
        # Center dialog on parent window AFTER widgets are added
        # Force update to get accurate geometry (same as database update dialog)
        self.update()
        progress_dialog.update_idletasks()
        
        # Get main window position and size
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        
        # Get dialog size
        dialog_width = progress_dialog.winfo_reqwidth()
        dialog_height = progress_dialog.winfo_reqheight()
        
        # Calculate centered position
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        
        # Apply position
        progress_dialog.geometry(f"+{x}+{y}")
        
        # Show dialog
        progress_dialog.deiconify()
        progress_dialog.lift()
        progress_dialog.focus_force()
        progress_dialog.grab_set()
        progress_dialog.update()
        
        def update_progress(current, total, message):
            """Update progress from background thread"""
            pct = (current / total) * 100 if total > 0 else 0
            progress_var.set(pct)
            status_var.set(message)
            progress_dialog.update()
        
        def run_scan():
            """Run the scan in background thread"""
            try:
                total = len(journals)
                # For migration, reset visit counts first then rebuild
                is_migration = (scan_type == 'migration')
                self._process_journals_for_catchup_with_progress(
                    journals, 
                    is_full_sync=True,
                    is_migration=is_migration,
                    progress_callback=lambda c, m: self.after(0, lambda: update_progress(c, total, m))
                )
            except Exception as e:
                log.error(f"[FULL SCAN] Error: {e}")
            finally:
                # Historical catch-up is done — safe to enable live-only PP inference now
                # (see journal_parser._upsert_pp_from_event).
                if hasattr(self, 'cargo_monitor') and self.cargo_monitor and self.cargo_monitor.journal_parser:
                    self.cargo_monitor.journal_parser.is_live_monitoring = True
                    self.cargo_monitor.journal_parser.finish_carrier_catchup()
                # Close dialog when done
                self.after(0, lambda: self._close_full_scan_dialog(progress_dialog))
        
        # Run scan in background thread
        thread = threading.Thread(target=run_scan, daemon=True)
        thread.start()
    
    def _close_full_scan_dialog(self, dialog):
        """Close the full scan progress dialog"""
        try:
            dialog.grab_release()
            dialog.destroy()
        except:
            pass
        self._startup_dialog_active = False
    
    def _process_journals_for_catchup_with_progress(self, journals, is_full_sync=False, is_migration=False, progress_callback=None):
        """Process journals with progress callback for first install/migration dialog
        
        Args:
            journals: List of journal files to process
            is_full_sync: If True, this is a full sync of all journals
            is_migration: If True, RESET visit counts before scanning (fixes wrong counts)
            progress_callback: Optional callback(current, message) for progress
        """
        import json
        from localization import t
        import sqlite3
        
        visits_added = 0
        hotspots_added = 0
        scan_failures = 0
        missions_found = 0
        
        # For MIGRATION: Reset all visit counts AND dates first, then rebuild
        # This is essential to fix inflated counts from previous buggy versions
        # We must reset last_visit_date too, otherwise add_visited_system will skip old entries
        if is_migration:
            try:
                user_db = self.cargo_monitor.user_db
                if user_db:
                    with sqlite3.connect(user_db.db_path) as conn:
                        conn.execute('''
                            UPDATE visited_systems 
                            SET visit_count = 0, 
                                first_visit_date = '', 
                                last_visit_date = ''
                        ''')
                        conn.commit()
                    print("[MIGRATION] Reset all visit counts and dates before rescan")
            except Exception as e:
                log.error(f"[MIGRATION] Failed to reset visit data: {e}")
        
        # Start batch mode for mission tracker
        mission_tracker = None
        
        # Suppress fleet carrier UI notifications during scan
        self.cargo_monitor.journal_parser._suppress_carrier_notifications = True
        try:
            try:
                from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                if MISSIONS_AVAILABLE:
                    mission_tracker = get_mission_tracker()
                    if mission_tracker:
                        mission_tracker.start_batch()
            except:
                pass
        
            total = len(journals)
            for idx, journal_path in enumerate(journals):
                # Update progress with localized message
                if progress_callback and idx % 10 == 0:
                    msg = t('dialogs.processing_journal', current=idx + 1, total=total)
                    progress_callback(idx, msg)
            
                try:
                    with open(journal_path, 'r', encoding='utf-8') as f:
                        current_system = None
                    
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                        
                            try:
                                event = json.loads(line)
                                event_type = event.get('event', '')
                                self.cargo_monitor.journal_parser.process_carrier_event(event)
                            
                                # CarrierJump is a commander arrival; CarrierLocation only tracks the carrier.
                                if event_type in ('FSDJump', 'CarrierJump'):
                                    system_name = event.get('StarSystem', '')
                                    if system_name:
                                        timestamp = event.get('timestamp', '')
                                        system_address = event.get('SystemAddress')
                                        star_pos = event.get('StarPos', [])
                                        coordinates = tuple(star_pos) if len(star_pos) >= 3 else None
                                    
                                        # Use single source of truth for visit recording
                                        if self.record_system_visit(system_name, timestamp, coordinates, system_address):
                                            visits_added += 1
                                        current_system = system_name
                            

                                elif event_type == 'Location':
                                    system_name = event.get('StarSystem', '')
                                    if system_name:
                                        current_system = system_name

                                elif event_type == 'Scan':
                                    try:
                                        self.cargo_monitor.journal_parser.process_scan(event)
                                        hotspots_added += 1
                                    except:
                                        scan_failures += 1
                            
                                elif event_type == 'SAASignalsFound':
                                    try:
                                        self.cargo_monitor.journal_parser.process_saa_signals_found(event, current_system)
                                        hotspots_added += 1
                                    except:
                                        scan_failures += 1
                            
                                elif event_type == 'MissionAccepted':
                                    try:
                                        from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                                        if MISSIONS_AVAILABLE:
                                            tracker = get_mission_tracker()
                                            if tracker and tracker.process_event(event):
                                                missions_found += 1
                                    except:
                                        pass
                            
                                elif event_type in ['MissionCompleted', 'MissionAbandoned', 'CargoDepot']:
                                    try:
                                        from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                                        if MISSIONS_AVAILABLE:
                                            tracker = get_mission_tracker()
                                            if tracker:
                                                tracker.process_event(event)
                                    except:
                                        pass
                                    
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    continue
        
            # End batch mode
            if mission_tracker:
                try:
                    mission_tracker.end_batch()
                except:
                    pass
        
            # Final progress update
            if progress_callback:
                msg = t('dialogs.scan_complete', visits=visits_added, hotspots=hotspots_added)
                progress_callback(total, msg)
        
            print(f"[FIRST INSTALL] Scan complete: {total} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} missions")
            log.info(f"First install scan complete: {total} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} missions")
            if scan_failures:
                log.warning("First install scan: %d hotspot events could not be saved", scan_failures)
        finally:
            # Re-enable carrier notifications and fire a single update
            self.cargo_monitor.journal_parser._suppress_carrier_notifications = False
            self.cargo_monitor.journal_parser._notify_carrier_updated()
        
        # Sync FC location to distance calculator from the now-correct carrier_data
        def _sync_fc_location():
            try:
                cd = self.cargo_monitor.journal_parser.carrier_data
                fc_system = cd.get('system') if cd else None
                if fc_system and hasattr(self, 'distance_fc_system'):
                    self.distance_fc_system.set(fc_system)
            except Exception:
                pass
        self.after(0, _sync_fc_location)
        
        # Mark full scan as complete using JSON file
        try:
            from path_utils import get_app_data_dir
            from version import get_version
            from datetime import datetime
            import json
            
            app_dir = get_app_data_dir()
            scan_status_file = os.path.join(app_dir, "last_full_scan.json")
            
            scan_data = {
                "version": get_version(),
                "scan_date": datetime.now().isoformat(),
                "journals_scanned": total,
                "visits_added": visits_added,
                "hotspots_added": hotspots_added
            }
            
            with open(scan_status_file, 'w') as f:
                json.dump(scan_data, f, indent=2)
            
            print(f"[FIRST INSTALL] Full scan status saved: {scan_status_file}")
        except Exception as e:
            log.error(f"[FIRST INSTALL] Failed to save scan status: {e}")
        
        # Update UI components
        if hasattr(self, 'ring_finder') and self.ring_finder:
            self.after(0, self.ring_finder._update_database_info)
        if hasattr(self, '_update_cmdr_system_display'):
            self.after(0, self._update_cmdr_system_display)
        if hasattr(self, '_update_home_fc_distances'):
            self.after(100, self._update_home_fc_distances)
    
    def _filter_journals_by_date(self, journals: list, cutoff_date) -> list:
        """Filter journals to only include those after cutoff date.
        
        Uses the date embedded in the journal filename (Journal.YYYY-MM-DDTHHMMSS.01.log)
        rather than file modification time, which can be unreliable.
        """
        from datetime import datetime
        import re
        
        filtered = []
        # Pattern to extract date from filename: Journal.YYYY-MM-DD or Journal.YYMMDD
        # Format 1: Journal.2023-08-18T161752.01.log (current format)
        # Format 2: Journal.230818123456.01.log (old format, if any)
        date_pattern_iso = re.compile(r'Journal\.(\d{4}-\d{2}-\d{2})T')
        date_pattern_old = re.compile(r'Journal\.(\d{6,8})')
        
        for journal_path in journals:
            try:
                filename = os.path.basename(journal_path)
                
                # Try ISO format first (YYYY-MM-DD)
                match = date_pattern_iso.search(filename)
                if match:
                    date_str = match.group(1)
                    file_date = datetime.strptime(date_str, "%Y-%m-%d")
                    if file_date >= cutoff_date:
                        filtered.append(journal_path)
                    continue
                
                # Try old format (YYMMDD or YYYYMMDD)
                match = date_pattern_old.search(filename)
                if match:
                    date_str = match.group(1)
                    if len(date_str) == 6:
                        file_date = datetime.strptime(date_str, "%y%m%d")
                    else:
                        file_date = datetime.strptime(date_str, "%Y%m%d")
                    if file_date >= cutoff_date:
                        filtered.append(journal_path)
                    continue
                
                # Can't parse date, include it to be safe
                filtered.append(journal_path)
            except Exception:
                # Include if we can't determine date
                filtered.append(journal_path)
        
        return filtered
    
    def _process_journals_for_catchup(self, journals, is_full_sync=False, resume_offsets=None):
        """Process journal files for catchup scan

        Processes hotspots/ring data, visits, and missions from journal files.

        Args:
            journals: List of journal file paths to process
            is_full_sync: If True, this is a full sync (all journals)
            resume_offsets: Optional dict mapping journal path -> byte offset to
                seek to before reading, for a file that was partially scanned
                on a previous run
        """
        import json
        
        scanned_checkpoint = None
        checkpoint_valid = True
        visits_added = 0
        hotspots_added = 0
        missions_found = 0
        
        # Set flag to prevent auto-refresh triggers during catchup scan
        self.cargo_monitor._catchup_scan_in_progress = True
        
        # Suppress fleet carrier UI notifications during scan
        self.cargo_monitor.journal_parser._suppress_carrier_notifications = True
        try:
            # Start batch mode for mission tracker to avoid UI spam during scan
            mission_tracker = None
            try:
                from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                if MISSIONS_AVAILABLE:
                    mission_tracker = get_mission_tracker()
                    if mission_tracker:
                        mission_tracker.start_batch()
            except:
                pass
        
            for idx, journal_path in enumerate(journals):
                # Update progress in status bar
                if idx % 25 == 0:  # Update every 25 files
                    progress = t('status_bar.journal_scanning_progress').format(done=idx, total=len(journals))
                    self.after(0, lambda p=progress: self._set_journal_scan_status(p, 0))

                try:
                    with open(journal_path, 'rb') as f:
                        if resume_offsets and journal_path in resume_offsets:
                            try:
                                offset = resume_offsets[journal_path]
                                if offset <= os.fstat(f.fileno()).st_size:
                                    f.seek(offset)
                            except Exception:
                                pass
                        current_system = None

                        position = f.tell()
                        for line in f:
                            if not line.endswith(b'\n'):
                                try:
                                    json.loads(line)
                                except (ValueError, UnicodeError):
                                    break
                            position = f.tell()
                            line = line.decode('utf-8', errors='replace').strip()
                            if not line:
                                continue
                        
                            try:
                                event = json.loads(line)
                                event_type = event.get('event', '')
                                self.cargo_monitor.journal_parser.process_carrier_event(event)
                            
                                # CarrierJump is a commander arrival; CarrierLocation only tracks the carrier.
                                if event_type in ('FSDJump', 'CarrierJump'):
                                    system_name = event.get('StarSystem', '')
                                    if system_name:
                                        timestamp = event.get('timestamp', '')
                                        system_address = event.get('SystemAddress')
                                        star_pos = event.get('StarPos', [])
                                        coordinates = tuple(star_pos) if len(star_pos) >= 3 else None
                                    
                                        # Use single source of truth for visit recording
                                        if self.record_system_visit(system_name, timestamp, coordinates, system_address):
                                            visits_added += 1
                                        current_system = system_name
                            

                                elif event_type == 'Location':
                                    # Location = game loaded, just track current system for context
                                    system_name = event.get('StarSystem', '')
                                    if system_name:
                                        current_system = system_name


                            
                                # Process Scan events for ring/hotspot data
                                elif event_type == 'Scan':
                                    try:
                                        self.cargo_monitor.journal_parser.process_scan(event)
                                        hotspots_added += 1
                                    except Exception as e:
                                        log.error(f"Error processing Scan event: {e}")
                            
                                # Process SAASignalsFound for hotspots
                                elif event_type == 'SAASignalsFound':
                                    try:
                                        self.cargo_monitor.journal_parser.process_saa_signals_found(event, current_system)
                                        hotspots_added += 1
                                    except Exception as e:
                                        log.error(f"Error processing SAASignalsFound event: {e}")
                            
                                # Process mining missions
                                elif event_type == 'MissionAccepted':
                                    try:
                                        from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                                        if MISSIONS_AVAILABLE:
                                            tracker = get_mission_tracker()
                                            if tracker:
                                                if tracker.process_event(event):
                                                    missions_found += 1
                                    except:
                                        pass
                            
                                elif event_type == 'MissionCompleted':
                                    try:
                                        from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                                        if MISSIONS_AVAILABLE:
                                            tracker = get_mission_tracker()
                                            if tracker:
                                                tracker.process_event(event)
                                    except:
                                        pass
                            
                                elif event_type == 'MissionAbandoned':
                                    try:
                                        from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                                        if MISSIONS_AVAILABLE:
                                            tracker = get_mission_tracker()
                                            if tracker:
                                                tracker.process_event(event)
                                    except:
                                        pass
                            
                                elif event_type == 'CargoDepot':
                                    try:
                                        from mining_missions import get_mission_tracker, MISSIONS_AVAILABLE
                                        if MISSIONS_AVAILABLE:
                                            tracker = get_mission_tracker()
                                            if tracker:
                                                tracker.process_event(event)
                                    except:
                                        pass
                                    
                            except json.JSONDecodeError:
                                continue
                            except:
                                continue
                        if checkpoint_valid:
                            scanned_checkpoint = (os.path.basename(journal_path), position)
                except Exception as e:
                    checkpoint_valid = False
                    log.error(f"[JOURNAL] Error reading {os.path.basename(journal_path)}: {e}")
                    continue
        
            # End batch mode for mission tracker
            if mission_tracker:
                try:
                    mission_tracker.end_batch()
                except:
                    pass
        finally:
            # Clear catchup scan flag
            self.cargo_monitor._catchup_scan_in_progress = False
            # Re-enable carrier notifications and fire a single update
            self.cargo_monitor.journal_parser._suppress_carrier_notifications = False
            self.cargo_monitor.journal_parser._notify_carrier_updated()
        
        # Sync FC location to distance calculator from the now-correct carrier_data
        def _sync_fc_location():
            try:
                cd = self.cargo_monitor.journal_parser.carrier_data
                fc_system = cd.get('system') if cd else None
                if fc_system and hasattr(self, 'distance_fc_system'):
                    self.distance_fc_system.set(fc_system)
            except Exception:
                pass
        self.after(0, _sync_fc_location)
        
        print(f"[JOURNAL] Scan complete: {len(journals)} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} mining missions")
        log.info(f"Journal scan complete: {len(journals)} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} mining missions")
        
        self.after(0, lambda: self._set_journal_scan_status(t('status_bar.journal_scan_done_count').format(n=len(journals))))
        
        # Refresh mining missions tab after scan (batch mode already notified callbacks)
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            if hasattr(self.prospector_panel, 'missions_tab') and self.prospector_panel.missions_tab:
                self.after(100, self.prospector_panel.missions_tab._refresh_missions)
        
        # Update UI components after scan (ring search already ran, just update database info)
        if hasattr(self, 'ring_finder') and self.ring_finder:
            self.after(0, self.ring_finder._update_database_info)
        if hasattr(self, '_update_cmdr_system_display'):
            self.after(0, self._update_cmdr_system_display)
        
        # Ensure current system has a visit record (safety net for carrier jumps, etc.)
        # Uses current system as reference - if player is HERE, visits must be >= 1
        self.after(50, self._ensure_current_system_visited)
        
        # Distance calculation runs AFTER journal scan is complete (now has accurate visit data)
        if hasattr(self, '_distance_refresh_locations'):
            print("[JOURNAL] Triggering location refresh and distance calculation...")
            self.after(200, self._distance_refresh_locations)
        
        # Ring finder auto-search runs AFTER journal scan is complete
        self.after(200, self._trigger_ring_auto_search)
        
        # Also trigger System A ↔ B calculation if both fields are populated
        if hasattr(self, '_calculate_distances'):
            self.after(300, self._auto_calculate_if_populated)

        return scanned_checkpoint

    def _auto_calculate_if_populated(self):
        """Auto-calculate System A ↔ B distance if both fields have values"""
        try:
            system_a = self.distance_system_a.get().strip()
            system_b = self.distance_system_b.get().strip()
            
            if system_a and system_b:
                self._calculate_distances()
        except Exception:
            pass

    def _ensure_current_system_visited(self):
        """Ensure current system has a visit record.
        
        This ONLY creates a record if the system has NEVER been visited.
        It does NOT increment the count - that only happens on FSDJump events.
        
        Purpose: Safety net for ALL edge cases where player is in a system
        but has no visit record:
        - Fleet Carrier jump (docked or undocked, your carrier or another player's)
        - Game startup (Location event)
        - Any missed or unprocessed arrival events
        - First time running the app
        
        Logic: If player is HERE, visits must be >= 1
        """
        try:
            current_system = self.get_current_system()
            if not current_system:
                return
            
            user_db = None
            if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                user_db = self.cargo_monitor.user_db
            
            if not user_db:
                return
            
            # Check if system was EVER visited
            visit_data = user_db.is_system_visited(current_system)
            
            if not visit_data:
                # System never visited - create initial record with count=1
                # Use a minimal timestamp so future actual visits will be newer
                self.record_system_visit(current_system, "0001-01-01T00:00:00Z")
            
            # Refresh the display (shows current count)
            self._update_cmdr_system_display()
            
        except Exception:
            log.exception("Recording current system visit failed")

    def get_current_system(self) -> Optional[str]:
        """Centralized method to get current system - single source of truth"""
        # Return cached value if available
        if self.current_system:
            return self.current_system
        
        # Try to get from prospector panel (already scanned on startup)
        if hasattr(self, 'prospector_panel') and self.prospector_panel.last_system:
            self.current_system = self.prospector_panel.last_system
            return self.current_system
        
        return None
    
    def _set_current_system_from_journal(self) -> None:
        """Set current system from journal after UI is built (robust against FC jumps/docked)"""
        try:
            from journal_parser import JournalParser
            
            # Get journal directory from prospector panel
            if not hasattr(self, 'prospector_panel') or not self.prospector_panel:
                return
            
            journal_dir = self.prospector_panel.journal_dir
            if not journal_dir or not os.path.isdir(journal_dir):
                return
            
            parser = JournalParser(journal_dir)
            last_system, location_timestamp = parser.get_last_known_system_with_timestamp()
            
            if last_system:
                # Store the location timestamp for offline carrier jump detection
                self._location_event_timestamp = location_timestamp
                
                # Use update_current_system to notify all components
                # This is startup/refresh - NOT a visit
                self.update_current_system(last_system, count_visit=False)
                
                # Note: Reserve levels will be fetched automatically when journal monitoring
                # processes the Location event or when user scans a ring
                
        except Exception:
            log.exception("Reading last known system from journal failed")
    
    def record_system_visit(self, system_name: str, event_timestamp: str, coordinates: Optional[tuple] = None, system_address: Optional[int] = None) -> bool:
        """Single source of truth for recording system visits.
        
        This method handles all visit recording logic:
        - Uses journal event timestamp for duplicate detection
        - Calls add_visited_system which checks if visit_date > last_visit
        
        Args:
            system_name: Name of the star system
            event_timestamp: ISO timestamp from the journal event (REQUIRED)
            coordinates: Optional (x, y, z) coordinates
            system_address: Optional system address from journal
            
        Returns:
            True if visit was recorded, False if skipped (duplicate/error)
        """
        if not system_name or not event_timestamp:
            return False
        
        try:
            user_db = None
            if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                user_db = self.cargo_monitor.user_db
            elif hasattr(self, 'user_db'):
                user_db = self.user_db
                
            if user_db:
                user_db.add_visited_system(
                    system_name=system_name,
                    visit_date=event_timestamp,
                    system_address=system_address,
                    coordinates=coordinates
                )
                return True
        except Exception as e:
            # Called once per jump during journal imports; log each distinct error once.
            if getattr(self, '_visit_last_error', None) != repr(e):
                self._visit_last_error = repr(e)
                log.warning("Recording system visit failed: %s", e)
        return False
    
    def _fetch_reserve_levels_for_system(self, system_name: str, on_complete=None) -> None:
        """Fetch reserve levels in the background, sharing overlapping requests."""
        if getattr(self, '_network_closing', False):
            return
        monitor = getattr(self, 'cargo_monitor', None)
        jp = getattr(monitor, 'journal_parser', None)
        if jp is None:
            return
        pending = getattr(self, '_reserve_requests', None)
        if pending is None:
            pending = self._reserve_requests = {}
        if system_name in pending:
            if on_complete:
                pending[system_name].append(on_complete)
            return
        pending[system_name] = [on_complete] if on_complete else []

        def complete(reserve_levels, error):
            callbacks = pending.pop(system_name, [])
            if getattr(self, '_network_closing', False):
                return
            jp.system_reserve_levels.update(reserve_levels)
            for callback in callbacks:
                callback(reserve_levels, error)

        def fetch_worker():
            reserve_levels, error = {}, None
            try:
                reserve_levels = jp._fetch_system_reserve_levels_from_spansh(system_name)
                if (reserve_levels and not getattr(self, '_network_closing', False)
                        and monitor.user_db):
                    monitor.user_db.bulk_update_reserve_levels(system_name, reserve_levels)
            except Exception as e:
                error = str(e)
                log.warning("Error fetching reserve levels for %s: %s", system_name, e)
            if not getattr(self, '_network_closing', False):
                try:
                    self.after(0, complete, reserve_levels, error)
                except (RuntimeError, tk.TclError):
                    pass

        threading.Thread(target=fetch_worker, daemon=True).start()

    def update_current_system(self, system_name: str, coords: Optional[tuple] = None, count_visit: bool = True, event_timestamp: Optional[str] = None) -> None:
        """Centralized method to update current system - notifies all interested components
        
        Args:
            system_name: Name of the current system
            coords: Optional (x, y, z) coordinates
            count_visit: Whether to count this as a visit. Set False for Location events
                         (game startup) which shouldn't count as arrivals.
            event_timestamp: Optional ISO timestamp from the journal event. If provided,
                             uses this for visit recording to prevent duplicate counting.
                             If None, uses current UTC time.
        """
        if not system_name:
            return
        
        # Check if this is actually a NEW system (not same as before)
        previous_system = getattr(self, 'current_system', None)
        is_different_system = previous_system != system_name
            
        # Update central cache
        self.current_system = system_name
        self.current_system_coords = coords
        
        # Count visit if we're in a different system than before AND count_visit is True
        # This includes first arrival (when previous_system is None)
        # count_visit should be False for Location events (game startup) since those
        # aren't actual arrivals - just loading into a system you were already in
        if is_different_system and count_visit:
            # Use event timestamp if provided, otherwise generate current UTC time
            if event_timestamp:
                timestamp = event_timestamp
            else:
                import datetime
                timestamp = datetime.datetime.utcnow().isoformat() + "Z"
            
            # Use single source of truth for visit recording
            self.record_system_visit(system_name, timestamp, coords)
        
        # SAFETY NET: Ensure visit count is at least 1 when player is in a system
        # This handles ALL edge cases where player arrived without a proper jump event:
        # - Fleet Carrier jump where commander IS onboard (count_visit=True)
        # - Traveling on another player's Fleet Carrier
        # - Any missed or unprocessed arrival events
        # Logic: If player is HERE, visits must be >= 1
        # IMPORTANT: Only run safety net when count_visit=True (means commander actually arrived)
        if is_different_system and count_visit:
            self.after(50, self._ensure_current_system_visited)
        
        # Fetch reserve levels from Spansh when entering a different system
        # This updates the database with reserve data for any existing hotspot entries
        if is_different_system and hasattr(self, 'cargo_monitor') and self.cargo_monitor:
            self.after(100, lambda: self._fetch_reserve_levels_for_system(system_name))
        
        # Notify all components that use current system
        # 1. Update ring finder reference system (only if auto-search is enabled)
        if (hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_var')
                and getattr(self.ring_finder, 'auto_search_var', None) and self.ring_finder.auto_search_var.get()):
            self.ring_finder.system_var.set(system_name)
            if coords:
                self.ring_finder.current_system_coords = coords
        
        # 2. Update distance calculator display
        if hasattr(self, 'distance_current_system'):
            self.distance_current_system.set(system_name)
            self._update_home_fc_distances()
        
        # 3. Update Mining Analytics (prospector panel) session system
        if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, 'session_system'):
            self.prospector_panel.session_system.set(system_name)
        
        # 4. Update CMDR/System display in actions bar (including visit count)
        # Use a delay to ensure database write is committed
        if hasattr(self, 'system_label_value'):
            self.after(100, self._update_cmdr_system_display)
        
        # 5. Refresh visit count display after database update
        if hasattr(self, 'distance_visits_label'):
            self.after(150, lambda: self._refresh_visit_count(system_name))
        
        # 5. Update System Finder current system display and reference field
        if hasattr(self, 'sysfinder_reference_system'):
            self.sysfinder_reference_system.set(system_name)
            self._confirm_sysfinder_reference()
        
        # Clear any selection that might have been applied and set neutral focus
        try:
            self.after(50, lambda: (self.ring_finder.system_entry.selection_clear() if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_entry') else None))
            self.after(50, lambda: (self.sysfinder_ref_entry.selection_clear() if hasattr(self, 'sysfinder_ref_entry') else None))
        except Exception:
            pass
        
        print(f"[SYSTEM] Updated current system: {system_name}")


if __name__ == "__main__":
    mutex = None
    if getattr(sys, 'frozen', False):
        # Single instance check - also lets the installer detect a running instance
        # via AppMutex without the slow Restart Manager scan.
        import win32event
        import win32api
        import winerror

        mutex_name = "Global\\EliteMining_SingleInstance_Mutex"

        try:
            mutex = win32event.CreateMutex(None, False, mutex_name)
            last_error = win32api.GetLastError()

            if last_error == winerror.ERROR_ALREADY_EXISTS:
                # Another instance is already running
                import tkinter.messagebox as messagebox
                messagebox.showerror(
                    "EliteMining Already Running",
                    "EliteMining is already running.\n\n"
                    "Only one instance can run at a time to prevent duplicate announcements and conflicts.\n\n"
                    "Please close the other instance first."
                )
                sys.exit(0)
        except Exception as e:
            print(f"Warning: Could not create mutex for single instance check: {e}")
            # Continue anyway - better to run than to fail completely

    # Clean up any restart flag from previous run
    try:
        import sys
        if getattr(sys, 'frozen', False):
            flag_file = os.path.join(os.path.dirname(sys.executable), ".restart_pending")
            if os.path.exists(flag_file):
                os.remove(flag_file)
    except:
        pass
    
    try:
        app = App()
        # Splash is now created inside App.__init__ and dismissed via after() + click.
        # If splash failed to load, restore geometry immediately.
        if not app._splash:
            app._restore_window_geometry()
            app.after(500, app._apply_stay_on_top_after_init)

        # Force dark title bar after window is fully created
        app.after(200, app._set_dark_title_bar)

        app.mainloop()
    except KeyboardInterrupt:
        # Graceful exit on Ctrl+C or stale terminal interrupt signal
        sys.exit(0)
    except Exception as e:
        # Show error dialog with full traceback
        import traceback
        error_details = traceback.format_exc()
        
        # Log to file
        try:
            with open(os.path.join(app_dir, "crash_log.txt"), "w") as f:
                f.write(f"EliteMining Crash Report\n")
                f.write(f"Time: {dt.datetime.now()}\n")
                f.write(f"Error: {str(e)}\n\n")
                f.write(error_details)
        except:
            pass
        
        # Show error to user
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "EliteMining - Critical Error",
            f"EliteMining failed to start:\n\n{str(e)}\n\n"
            f"A crash log has been saved to:\n{os.path.join(app_dir, 'crash_log.txt')}\n\n"
            f"Please report this error to the developer."
        )
        sys.exit(1)
