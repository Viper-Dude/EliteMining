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
from logging_setup import setup_logging
log_file = setup_logging()  # Only activates when running as packaged executable
if log_file:
    try:
        print(f"✓ Logging enabled: {log_file}")
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
from logging.handlers import RotatingFileHandler
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
            print(f"[MAIN] t() error for {key}: {ex}")
            return key.split('.')[-1]  # Return last part of key as fallback
except Exception as e:
    print(f"[WARNING] Could not initialize localization: {e}")
    def t(key, **kwargs):
        """Fallback translation - returns last part of key"""
        return key.split('.')[-1]

# Now import modules that depend on localization
from ring_finder import RingFinder
from marketplace_api import MarketplaceAPI
from config import _load_cfg, _save_cfg, load_saved_va_folder, save_va_folder, load_window_geometry, save_window_geometry, load_cargo_window_position, save_cargo_window_position
from version import get_version, UPDATE_CHECK_URL, UPDATE_CHECK_INTERVAL
from update_checker import UpdateChecker
from user_database import UserDatabase
from journal_parser import JournalParser
from app_utils import get_app_icon_path, set_window_icon, get_app_data_dir, get_variables_dir, get_ship_presets_dir

# Import UI components from ui module
from ui.theme import THEME_ELITE_ORANGE, THEME_DARK_GRAY, get_theme_colors
from ui.tooltip import ToolTip
from ui.dialogs import centered_yesno_dialog, center_window, centered_info_dialog, set_translate_func

# Set up translation for dialogs module
set_translate_func(t)
from path_utils import get_ship_presets_dir, get_reports_dir

# --- Text Overlay class for TTS announcements ---
class TextOverlay:
    def __init__(self):
        self.overlay_window = None
        self.overlay_enabled = False
        self.display_duration = 7000  # 7 seconds in milliseconds
        self.fade_timer = None
        self.transparency = 0.9  # Default transparency (90%)
        self.text_color = "#FFFFFF"  # Default white color
        self.position = "upper_left"  # Fixed position
        self.font_size = 12  # Default font size (Normal)
        
    def create_overlay(self):
        """Create the overlay window"""
        if self.overlay_window:
            return
            
        self.overlay_window = tk.Toplevel()
        self.overlay_window.title(t('dialogs.mining_announcements'))
        self.overlay_window.wm_overrideredirect(True)  # Remove window decorations
        self.overlay_window.wm_attributes("-topmost", True)  # Always on top
        
        # Make window background completely transparent
        self.overlay_window.wm_attributes("-transparentcolor", "#000001")  # Use almost-black as transparent
        self.overlay_window.configure(bg="#000001")  # This color becomes transparent
        
        # Position based on setting
        self._set_window_position()
        
        # Create canvas with transparent background
        self.canvas = tk.Canvas(
            self.overlay_window,
            bg="#000001",  # Same as transparent color - will be invisible
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Hide initially
        self.overlay_window.withdraw()
        
        # Apply current color and brightness settings
        # self._update_text_color() # No text item yet
        
    def show_message(self, message: str):
        """Display a message in the overlay"""
        if not self.overlay_enabled:
            return
            
        if not self.overlay_window:
            self.create_overlay()
            
        self._draw_text(message)
        
        # CRITICAL: Reposition window every time before showing (Windows can reset position)
        self._set_window_position()
        
        # Show window
        self.overlay_window.deiconify()
        
        # Cancel any existing timer
        if self.fade_timer:
            self.overlay_window.after_cancel(self.fade_timer)
            
        # Schedule hide after display duration
        self.fade_timer = self.overlay_window.after(self.display_duration, self.hide_overlay)
        
    def show_persistent_message(self, message: str):
        """Display a message that stays visible until manually hidden (for cargo full prompt)"""
        if not self.overlay_enabled:
            return
            
        if not self.overlay_window:
            self.create_overlay()
            
        self._draw_text(message)
        self.overlay_window.deiconify()
        
        # Cancel any existing timer - this message stays until manually hidden
        if self.fade_timer:
            self.overlay_window.after_cancel(self.fade_timer)
            self.fade_timer = None

    def _draw_text(self, message: str):
        """Draw text with outline on canvas"""
        self.canvas.delete("all")
        
        font_spec = ("Segoe UI", self.font_size, "normal")
        text_color = self._get_current_color()
        
        # Draw outline (shadow)
        # Offset by 2 pixels to ensure outline is not clipped
        base_x, base_y = 2, 2
        offsets = [(-1, -1), (1, -1), (-1, 1), (1, 1), (0, 1), (0, -1), (1, 0), (-1, 0)]
        for ox, oy in offsets:
            self.canvas.create_text(
                base_x + ox, base_y + oy,
                text=message,
                font=font_spec,
                fill="black",
                anchor="nw",
                justify="left"
            )
            
        # Draw main text
        self.text_item = self.canvas.create_text(
            base_x, base_y,
            text=message,
            font=font_spec,
            fill=text_color,
            anchor="nw",
            justify="left"
        )
    
    def hide_overlay(self):
        """Hide the overlay window"""
        if self.overlay_window:
            self.overlay_window.withdraw()
            
    def set_enabled(self, enabled: bool):
        """Enable or disable the text overlay"""
        self.overlay_enabled = enabled
        if not enabled and self.overlay_window:
            self.hide_overlay()
            
    def set_transparency(self, transparency_percent: int):
        """Set text brightness (10-100%)"""
        self.transparency = transparency_percent / 100.0
        if self.overlay_window:
            self._update_text_color()
    
    def set_color(self, color_hex: str):
        """Set the base text color"""
        self.text_color = color_hex
        if self.overlay_window:
            self._update_text_color()
    
    def _get_current_color(self):
        """Calculate text color based on brightness setting"""
        # Parse the base color
        base_color = self.text_color.lstrip('#')
        r = int(base_color[0:2], 16)
        g = int(base_color[2:4], 16) 
        b = int(base_color[4:6], 16)
        
        # Use transparency setting to control brightness (0.1 to 1.0)
        brightness_factor = self.transparency
        
        # Calculate new RGB values
        new_r = int(r * brightness_factor)
        new_g = int(g * brightness_factor)
        new_b = int(b * brightness_factor)
        
        # Ensure we get the full color values
        new_r = min(255, max(0, new_r))
        new_g = min(255, max(0, new_g))
        new_b = min(255, max(0, new_b))
        
        return f"#{new_r:02x}{new_g:02x}{new_b:02x}"

    def _update_text_color(self):
        """Update text color of existing text item"""
        if hasattr(self, 'canvas') and hasattr(self, 'text_item'):
            try:
                final_color = self._get_current_color()
                self.canvas.itemconfig(self.text_item, fill=final_color)
            except Exception as e:
                print(f"Error updating text color: {e}")
    
    def set_position(self, position: str):
        """Set overlay position - always upper left"""
        self.position = "upper_left"  # Always use upper left
        if self.overlay_window:
            self._set_window_position()
    
    def set_font_size(self, size: int):
        """Set text font size"""
        self.font_size = size
        if self.overlay_window and hasattr(self, 'canvas'):
            try:
                # Update all text items (shadows and main text)
                font_spec = ("Segoe UI", size, "normal")
                self.canvas.itemconfig("all", font=font_spec)
            except Exception as e:
                print(f"Error setting font size: {e}")
    
    def set_display_duration(self, seconds: int):
        """Set how long text stays on screen (5-30 seconds)"""
        self.display_duration = seconds * 1000  # Convert to milliseconds
        # If a message is currently showing, don't interrupt it
        # The new duration will apply to the next message
    
    def _set_window_position(self):
        """Set window position - always upper left"""
        if not self.overlay_window:
            return
            
        # Fixed position: upper left
        window_width = 750
        window_height = 300
        x_pos = 20
        y_pos = 100
        
        self.overlay_window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
    
    def show_prospector_overlay(self, evt_data: dict, show_all: bool = False, threshold: float = 0.0, 
                               announce_map: dict = None, min_pct_map: dict = None):
        """
        Display enhanced prospector overlay in game style format.
        
        Args:
            evt_data: Prospector event data from journal
            show_all: If True, show all materials; if False, filter by threshold
            threshold: Default threshold percentage
            announce_map: Dictionary of material names -> enabled status
            min_pct_map: Dictionary of material names -> custom thresholds
        """
        print(f"[ENHANCED OVERLAY] Called with show_all={show_all}, threshold={threshold}")
        
        if not self.overlay_enabled:
            print("[ENHANCED OVERLAY] Overlay not enabled, returning")
            return
            
        if not self.overlay_window:
            self.create_overlay()
        
        # Extract data from event
        materials = evt_data.get("Materials", [])
        motherlode = evt_data.get("MotherlodeMaterial_Localised") or evt_data.get("MotherlodeMaterial")
        content = evt_data.get("Content_Localised") or evt_data.get("Content", "")
        remaining = evt_data.get("Remaining")
        
        print(f"[ENHANCED OVERLAY] Materials count: {len(materials)}, Motherlode: {motherlode}")
        
        # Clean up content string (remove "Material Content: " prefix if present)
        if content and content.lower().startswith("material content"):
            content = content[len("Material Content:"):].strip()
        
        # Format header line with distance if available
        # TODO: Add distance from prospector data when available in journal
        header = "LIMPET (PROSPECTOR)"
        
        # Build the message lines
        lines = [header, ""]  # Empty line after header
        
        # Add motherlode if present (always in cyan)
        if motherlode:
            motherlode_clean = self._clean_material_name(motherlode)
            lines.append(f"MOTHERLODE DETECTED: {motherlode_clean.upper()}")
            lines.append("")  # Empty line after motherlode
        
        # Add remaining percentage
        if remaining is not None:
            if remaining <= 0.0:
                lines.append("MINERALS REMAINING: DEPLETED")
            elif remaining >= 100.0:
                lines.append("MINERALS REMAINING: 100.00%")
            else:
                lines.append(f"MINERALS REMAINING: {remaining:.2f}%")
        else:
            lines.append("MINERALS REMAINING: 100.00%")
        
        # Process materials
        material_lines = []
        for m in materials:
            # Extract material name and percentage
            name = m.get("Name_Localised") or m.get("Name", "")
            name = self._clean_material_name(name)
            pct = m.get("Proportion")
            
            if not name or pct is None:
                continue
            
            # Convert proportion to percentage
            pct_value = pct * 100.0
            
            # Check if we should display this material
            if not show_all:
                # Filter by threshold
                eff_threshold = min_pct_map.get(name, threshold) if min_pct_map else threshold
                is_enabled = announce_map.get(name, False) if announce_map else True
                
                # Also try title case for material name lookup
                if not is_enabled and name != name.title():
                    is_enabled = announce_map.get(name.title(), False) if announce_map else False
                
                # Skip if below threshold or not enabled
                if not is_enabled or pct_value < eff_threshold:
                    continue
            
            # Format material line
            material_lines.append(f"{name.upper()} {pct_value:.2f}%")
        
        # Add material lines
        lines.extend(material_lines)
        
        # Add content line if present
        if content:
            lines.append("")  # Empty line before content
            lines.append(f"MATERIAL CONTENT: {content.upper()}")
        
        # Join all lines
        message = "\n".join(lines)
        
        print(f"[ENHANCED OVERLAY] Displaying {len(lines)} lines")
        print(f"[ENHANCED OVERLAY] Message:\n{message}")
        
        # Show the overlay
        self.show_message(message)
    
    def _clean_material_name(self, name: str) -> str:
        """Clean up material name (remove $, underscores, etc.)"""
        if not name:
            return ""
        # Remove common prefixes
        if name.startswith("$"):
            name = name[1:]
        if name.endswith("_name;"):
            name = name[:-6]
        # Replace underscores with spaces
        name = name.replace("_", " ")
        # Title case
        return name.title()
            
    def destroy(self):
        """Clean up the overlay"""
        if self.overlay_window:
            if self.fade_timer:
                self.overlay_window.after_cancel(self.fade_timer)
            self.overlay_window.destroy()
            self.overlay_window = None

APP_TITLE = "EliteMining"
APP_VERSION = "v4.82"
PRESET_INDENT = "   "  # spaces used to indent preset names

LOG_FILE = os.path.join(os.path.expanduser("~"), "EliteMining.log")

# Create a custom handler that silently handles rotation errors
class SafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that silently handles rotation errors (file locked by another process)"""
    def doRollover(self):
        try:
            super().doRollover()
        except (PermissionError, OSError):
            # File is locked by another process, just continue writing to current file
            pass

_handler = SafeRotatingFileHandler(LOG_FILE, maxBytes=512*1024, backupCount=3, encoding="utf-8")
logging.basicConfig(level=logging.INFO, handlers=[_handler],
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    except Exception as e:
        try:
            # Best effort fallback (non‑atomic)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        log.exception("Atomic write failed for %s: %s", path, e)

# --- Firegroup letters and NATO mapping (files use NATO words) ---
from core.constants import (
    FIREGROUPS, NATO, NATO_REVERSE,
    VA_VARS, VA_TTS_ANNOUNCEMENT, TOOL_ORDER,
    ANNOUNCEMENT_TOGGLES, TOGGLES, TIMERS, MENU_COLORS, MINING_MATERIALS
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

# --- Refinery Contents Dialog class ---
class RefineryDialog:
    def __init__(self, parent, cargo_monitor, current_cargo_items=None):
        self.parent = parent
        self.cargo_monitor = cargo_monitor
        self.current_cargo_items = current_cargo_items or {}
        
        # Load existing refinery contents from cargo monitor
        if cargo_monitor and hasattr(cargo_monitor, 'refinery_contents'):
            self.refinery_contents = cargo_monitor.refinery_contents.copy()
        else:
            self.refinery_contents = {}
            
        self.result = None
        
        # Create dialog window (withdraw first to avoid flicker)
        self.dialog = tk.Toplevel(parent)
        self.dialog.withdraw()
        self.dialog.title(t('refinery_dialog.title'))
        self.dialog.geometry("600x750")
        self.dialog.configure(bg="#1e1e1e")
        self.dialog.resizable(True, True)  # Allow resizing so user can adjust if needed
        
        # Set icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                self.dialog.iconbitmap(icon_path)
            elif icon_path and os.path.exists(icon_path):
                self.dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception as e:
            print(f"[RefineryDialog] Could not set icon: {e}")
            pass  # Silently handle icon loading errors
        
        # Center the dialog on parent window
        self.dialog.update_idletasks()
        
        # Calculate dynamic width based on materials
        material_count = len(self.current_cargo_items) if hasattr(self, 'current_cargo_items') and self.current_cargo_items else 0
        
        # Auto-width for up to 3-4 materials
        if material_count <= 4:
            # Calculate width based on longest material name
            max_name_length = 0
            if hasattr(self, 'current_cargo_items') and self.current_cargo_items:
                max_name_length = max(len(name) for name in self.current_cargo_items.keys())
            
            # Base width + material name width + button space
            base_width = 450
            name_width = max_name_length * 8  # ~8 pixels per character
            button_width = 220  # Space for quantity buttons
            calculated_width = max(base_width, min(800, base_width + name_width + button_width))
            dialog_width = calculated_width
        else:
            dialog_width = 750  # Default width for many materials
        
        if parent:
            parent.update_idletasks()
            # Get parent window position and size
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
            
            # Calculate dynamic height based on material count
            base_height = 750
            if material_count > 2:
                # Add 60px for each row of materials (2 materials per row)
                extra_rows = (material_count - 2 + 1) // 2  # Round up
                dialog_height = min(950, base_height + (extra_rows * 60))
            else:
                dialog_height = base_height
            
            x = parent_x + (parent_width - dialog_width) // 2
            y = parent_y + (parent_height - dialog_height) // 2
        else:
            # Fallback to screen center
            base_height = 750
            if material_count > 2:
                extra_rows = (material_count - 2 + 1) // 2
                dialog_height = min(950, base_height + (extra_rows * 60))
            else:
                dialog_height = base_height
            x = (self.dialog.winfo_screenwidth() // 2) - (dialog_width // 2)
            y = (self.dialog.winfo_screenheight() // 2) - (dialog_height // 2)
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        self._create_ui()
        # Now show dialog centered and make it modal
        self.dialog.deiconify()
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.attributes('-topmost', True)
        self.dialog.lift()
        self.dialog.focus_force()
        
    def _create_ui(self):
        """Create the refinery dialog UI"""
        from core.constants import MINING_MATERIALS
        
        # Main frame
        main_frame = tk.Frame(self.dialog, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = tk.Label(main_frame, text="⚗️ " + t('refinery_dialog.title'), 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Manual add section (moved to top for dropdown space)
        manual_frame = tk.LabelFrame(main_frame, text="🔍 " + t('refinery_dialog.add_other_minerals'), 
                                   bg="#1e1e1e", fg="#ffffff", 
                                   font=("Segoe UI", 10, "bold"))
        manual_frame.pack(fill="x", pady=(0, 15))
        
        manual_inner = tk.Frame(manual_frame, bg="#1e1e1e")
        manual_inner.pack(fill="x", padx=10, pady=10)
        
        # Configure grid columns for proper spacing
        manual_inner.columnconfigure(1, weight=1)  # Material dropdown column
        manual_inner.columnconfigure(3, weight=0)  # Quantity entry column
        
        # Material selection
        tk.Label(manual_inner, text=t('refinery_dialog.material_label'), bg="#1e1e1e", fg="#ffffff").grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        self.material_var = tk.StringVar(value=t('refinery_dialog.select_material'))
        
        # Material selection button using standard app styling
        material_btn = tk.Button(manual_inner, textvariable=self.material_var,
                               command=self._open_material_selector,
                               bg="#4a9eff", fg="#ffffff", 
                               font=("Segoe UI", 9))
        material_btn.grid(row=0, column=1, padx=5, sticky="w")
        
        # Quantity entry
        tk.Label(manual_inner, text=t('refinery_dialog.quantity_label'), bg="#1e1e1e", fg="#ffffff").grid(row=0, column=2, sticky="w", padx=(10, 5))
        
        self.quantity_var = tk.StringVar()
        quantity_entry = tk.Entry(manual_inner, textvariable=self.quantity_var, width=8,
                                bg="#2d2d2d", fg="#ffffff", 
                                insertbackground="#ffffff",  # Cursor color
                                selectbackground="#404040",   # Selection background
                                selectforeground="#ffffff",   # Selection text
                                relief="sunken", bd=1)
        quantity_entry.grid(row=0, column=3, padx=5)
        
        tk.Label(manual_inner, text=t('refinery_dialog.tons'), bg="#1e1e1e", fg="#ffffff").grid(row=0, column=4, sticky="w", padx=(5, 0))
        
        # Add button
        add_btn = tk.Button(manual_inner, text=t('refinery_dialog.add_button'), 
                          command=self._add_manual_material,
                          bg="#4a9eff", fg="#ffffff", 
                          font=("Segoe UI", 9, "bold"))
        add_btn.grid(row=0, column=5, padx=(10, 0))

        # Session summary
        if self.cargo_monitor:
            summary_frame = tk.Frame(main_frame, bg="#2d2d2d", relief="raised", bd=1)
            summary_frame.pack(fill="x", pady=(0, 15))
            
            cargo_total = getattr(self.cargo_monitor, 'current_cargo', 0)
            capacity = getattr(self.cargo_monitor, 'max_cargo', 0)
            
            summary_label = tk.Label(summary_frame, 
                                   text="📦 " + t('refinery_dialog.cargo_hold_detected', total=cargo_total),
                                   bg="#2d2d2d", fg="#ffffff", 
                                   font=("Segoe UI", 10))
            summary_label.pack(pady=8)
        
        # Quick add from cargo section
        if self.current_cargo_items:
            cargo_frame = tk.LabelFrame(main_frame, text="📦 " + t('refinery_dialog.quick_add_cargo'), 
                                      bg="#1e1e1e", fg="#ffffff", 
                                      font=("Segoe UI", 10, "bold"))
            cargo_frame.pack(fill="x", pady=(0, 15))
            
            cargo_inner = tk.Frame(cargo_frame, bg="#1e1e1e")
            cargo_inner.pack(fill="x", padx=10, pady=10)
            
            # Create quick-add buttons for materials in cargo
            row = 0
            col = 0
            for material, quantity in self.current_cargo_items.items():
                # Normalize material name for comparison
                normalized_material = material.replace("LowTemperatureDiamonds", "Low Temperature Diamonds")
                if normalized_material in MINING_MATERIALS:  # Only show known mining materials
                    # Use the normalized name for display
                    display_material = normalized_material
                    material_frame = tk.Frame(cargo_inner, bg="#1e1e1e")
                    material_frame.grid(row=row, column=col, padx=5, pady=5, sticky="w")
                    
                    # Material label - use normalized name
                    mat_label = tk.Label(material_frame, text=f"{display_material}:", 
                                       bg="#1e1e1e", fg="#ffffff", 
                                       font=("Segoe UI", 9))
                    mat_label.pack(side="left")
                    
                    # Quick add buttons - use normalized name
                    for amount in [1, 4, 6, 8, 10]:
                        btn = tk.Button(material_frame, text=f"+{amount}t", 
                                      command=lambda m=display_material, a=amount: self._quick_add_material(m, a),
                                      bg="#404040", fg="#ffffff", 
                                      font=("Segoe UI", 8), width=6)
                        btn.pack(side="left", padx=2)
                    
                    col += 1
                    if col > 1:  # 2 columns
                        col = 0
                        row += 1
        
        # Current refinery contents
        contents_frame = tk.LabelFrame(main_frame, text="⚗️ " + t('refinery_dialog.current_refinery'), 
                                     bg="#1e1e1e", fg="#ffffff", 
                                     font=("Segoe UI", 10, "bold"))
        contents_frame.pack(fill="x", pady=(0, 15))
        
        # Scrollable list of refinery contents - with fixed height
        list_frame = tk.Frame(contents_frame, bg="#1e1e1e")
        list_frame.pack(fill="x", padx=10, pady=10)
        
        self.contents_listbox = tk.Listbox(list_frame, bg="#2d2d2d", fg="#ffffff", 
                                         selectbackground="#404040", 
                                         font=("Segoe UI", 9), height=6)
        self.contents_listbox.pack(side="left", fill="x", expand=True)
        
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.contents_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.contents_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Edit and Remove buttons
        button_container = tk.Frame(contents_frame, bg="#1e1e1e")
        button_container.pack(pady=(0, 10))
        
        edit_btn = tk.Button(button_container, text=t('refinery_dialog.edit_selected'), 
                           command=self._edit_selected,
                           bg="#4a9eff", fg="#ffffff")
        edit_btn.pack(side="left", padx=(0, 5))
        
        remove_btn = tk.Button(button_container, text=t('refinery_dialog.remove_selected'), 
                             command=self._remove_selected,
                             bg="#ff6b6b", fg="#ffffff")
        remove_btn.pack(side="left")
        
        # Summary section
        self.summary_frame = tk.Frame(main_frame, bg="#2d2d2d", relief="raised", bd=1)
        self.summary_frame.pack(fill="x", pady=(0, 15))
        
        self.summary_label = tk.Label(self.summary_frame, 
                                    text=t('dialogs.refinery_total', count=0),
                                    bg="#2d2d2d", fg="#ffffff", 
                                    font=("Segoe UI", 10, "bold"))
        self.summary_label.pack(pady=8)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="#1e1e1e")
        button_frame.pack(fill="x")
        
        clear_btn = tk.Button(button_frame, text=t('refinery_dialog.clear_all'), 
                            command=self._clear_all,
                            bg="#666666", fg="#ffffff")
        clear_btn.pack(side="left")
        
        cancel_btn = tk.Button(button_frame, text=t('dialogs.cancel'), 
                             command=self._cancel,
                             bg="#666666", fg="#ffffff")
        cancel_btn.pack(side="right", padx=(5, 0))
        
        apply_btn = tk.Button(button_frame, text=t('refinery_dialog.apply_to_session'), 
                            command=self._apply,
                            bg="#4caf50", fg="#ffffff", 
                            font=("Segoe UI", 9, "bold"))
        apply_btn.pack(side="right", padx=(5, 0))
        
        # Update display to show any existing refinery contents
        self._update_display()
        self._update_summary()
    
    def _quick_add_material(self, material, amount):
        """Add material from quick-add buttons"""
        # Check refinery capacity limit (10t max)
        current_total = sum(self.refinery_contents.values())
        if current_total + amount > 10.0:
            remaining_capacity = 10.0 - current_total
            messagebox.showerror(t('refinery_dialog.capacity_exceeded_title'), 
                               t('refinery_dialog.capacity_exceeded_msg', 
                                 current=current_total, available=remaining_capacity, amount=amount))
            return
            
        if material in self.refinery_contents:
            self.refinery_contents[material] += amount
        else:
            self.refinery_contents[material] = amount
        self._update_display()
        
        # Trigger CSV update if this is being used after session end
        self._check_and_trigger_csv_update({material: amount})
    
    def _add_manual_material(self):
        """Add material from manual entry"""
        material = self.material_var.get()
        
        # Check if material is selected
        if not material or material == t('refinery_dialog.select_material'):
            messagebox.showerror(t('dialogs.error'), t('refinery_dialog.select_material_error'))
            return
            
        try:
            quantity_str = self.quantity_var.get().strip()
            if not quantity_str:
                messagebox.showerror(t('dialogs.error'), t('refinery_dialog.invalid_quantity'))
                return
                
            quantity = float(quantity_str)
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            
            # Check refinery capacity limit (10t max)
            current_total = sum(self.refinery_contents.values())
            if current_total + quantity > 10.0:
                remaining_capacity = 10.0 - current_total
                messagebox.showerror(t('refinery_dialog.capacity_exceeded_title'), 
                                   t('refinery_dialog.capacity_exceeded_msg',
                                     current=current_total, available=remaining_capacity, amount=quantity))
                return
                
            if material in self.refinery_contents:
                self.refinery_contents[material] += quantity
            else:
                self.refinery_contents[material] = quantity
                
            self.quantity_var.set("")  # Clear entry
            self._update_display()
            
            # Trigger CSV update if this is being used after session end
            self._check_and_trigger_csv_update({material: quantity})
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid positive number for quantity.")
    
    def _check_and_trigger_csv_update(self, added_materials: dict):
        """Check if we should trigger CSV update when materials are added manually"""
        # DISABLED: Refinery materials are now handled in end_session_tracking()
        # This function was causing double-writes and cross-session data contamination
        # The materials are stored in refinery_contents and added to the report at session end
        pass

    def _remove_selected(self):
        """Remove selected material from refinery contents"""
        selection = self.contents_listbox.curselection()
        if selection:
            index = selection[0]
            materials = list(self.refinery_contents.keys())
            if index < len(materials):
                material = materials[index]
                del self.refinery_contents[material]
                self._update_display()
    
    def _edit_selected(self):
        """Edit the quantity of selected material"""
        selection = self.contents_listbox.curselection()
        if not selection:
            messagebox.showwarning(t('dialogs.warning'), t('refinery_dialog.select_material_error'))
            return
            
        index = selection[0]
        materials = list(self.refinery_contents.keys())
        if index < len(materials):
            material = materials[index]
            current_qty = self.refinery_contents[material]
            
            # Create custom edit dialog with dark theme and proper positioning
            new_qty = self._show_edit_quantity_dialog(material, current_qty)
            
            if new_qty is not None:
                if new_qty == 0:
                    # Remove if quantity is 0
                    del self.refinery_contents[material]
                else:
                    # Update quantity
                    self.refinery_contents[material] = new_qty
                self._update_display()
                
    def _show_edit_quantity_dialog(self, material, current_qty):
        """Show a custom dark-themed edit quantity dialog positioned near parent"""
        # Create dialog window
        edit_dialog = tk.Toplevel(self.dialog)
        edit_dialog.title(t('refinery_dialog.edit_quantity_title'))
        edit_dialog.geometry("400x200")
        edit_dialog.configure(bg="#1e1e1e")
        edit_dialog.resizable(False, False)
        edit_dialog.transient(self.dialog)
        edit_dialog.grab_set()
        
        # Set app icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                edit_dialog.iconbitmap(icon_path)
            elif icon_path:
                edit_dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except:
            pass  # Silently handle icon loading errors
        
        # Position near parent dialog (not on distant monitor)
        self.dialog.update_idletasks()
        edit_dialog.update_idletasks()
        
        # Calculate center position relative to parent dialog
        parent_x = self.dialog.winfo_x()
        parent_y = self.dialog.winfo_y()
        parent_width = self.dialog.winfo_width()
        parent_height = self.dialog.winfo_height()
        
        dialog_width = 400
        dialog_height = 200
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        edit_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # Create UI with dark theme
        main_frame = tk.Frame(edit_dialog, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = tk.Label(main_frame, text=t('refinery_dialog.edit_quantity_prompt', material=material), 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Current quantity info
        info_label = tk.Label(main_frame, text=t('refinery_dialog.current_quantity', qty=current_qty), 
                             bg="#1e1e1e", fg="#cccccc", 
                             font=("Segoe UI", 10))
        info_label.pack(pady=(0, 10))
        
        # New quantity entry
        entry_frame = tk.Frame(main_frame, bg="#1e1e1e")
        entry_frame.pack(pady=(0, 20))
        
        tk.Label(entry_frame, text=t('refinery_dialog.new_quantity'), bg="#1e1e1e", fg="#ffffff",
                font=("Segoe UI", 10)).pack(side="left")
        
        quantity_var = tk.StringVar(value=str(current_qty))
        quantity_entry = tk.Entry(entry_frame, textvariable=quantity_var, width=10,
                                bg="#2d2d2d", fg="#ffffff", 
                                insertbackground="#ffffff",
                                selectbackground="#404040",
                                selectforeground="#ffffff",
                                font=("Segoe UI", 10),
                                relief="sunken", bd=1)
        quantity_entry.pack(side="left", padx=(10, 5))
        
        tk.Label(entry_frame, text=t('refinery_dialog.tons'), bg="#1e1e1e", fg="#ffffff",
                font=("Segoe UI", 10)).pack(side="left")
        
        # Focus and select all text
        quantity_entry.focus_set()
        quantity_entry.select_range(0, tk.END)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="#1e1e1e")
        button_frame.pack()
        
        result = [None]  # Use list to store result (mutable)
        
        def ok_clicked():
            try:
                value = float(quantity_var.get())
                if value < 0:
                    messagebox.showerror("Invalid Input", "Quantity cannot be negative.", parent=edit_dialog)
                    return
                result[0] = value
                edit_dialog.destroy()
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid number.", parent=edit_dialog)
        
        def cancel_clicked():
            result[0] = None
            edit_dialog.destroy()
        
        # OK button
        ok_btn = tk.Button(button_frame, text=t('common.ok'), command=ok_clicked,
                          bg="#4caf50", fg="#ffffff", 
                          font=("Segoe UI", 9, "bold"), width=8)
        ok_btn.pack(side="left", padx=(0, 10))
        
        # Cancel button  
        cancel_btn = tk.Button(button_frame, text=t('common.cancel'), command=cancel_clicked,
                              bg="#666666", fg="#ffffff", 
                              font=("Segoe UI", 9), width=8)
        cancel_btn.pack(side="left")
        
        # Bind Enter key to OK and Escape to Cancel
        edit_dialog.bind('<Return>', lambda e: ok_clicked())
        edit_dialog.bind('<Escape>', lambda e: cancel_clicked())
        
        # Wait for dialog to close and return result
        edit_dialog.wait_window()
        return result[0]
    
    def _clear_all(self):
        """Clear all refinery contents"""
        self.refinery_contents.clear()
        self._update_display()
    
    def _update_display(self):
        """Update the contents listbox and summary"""
        self.contents_listbox.delete(0, tk.END)
        
        for material, quantity in self.refinery_contents.items():
            self.contents_listbox.insert(tk.END, f"{material}: {quantity} tons")
        
        self._update_summary()
    
    def _update_summary(self):
        """Update the summary label"""
        total = sum(self.refinery_contents.values())
        self.summary_label.configure(text=t('refinery_dialog.refinery_total', total=total))
        
        # Update final calculation if we have cargo data
        if self.cargo_monitor:
            cargo_total = getattr(self.cargo_monitor, 'current_cargo', 0)
            final_total = cargo_total + total
            
            summary_text = t('refinery_dialog.refinery_total', total=total) + "\n"
            summary_text += t('refinery_dialog.final_total', cargo=cargo_total, refinery=total, total=final_total)
            self.summary_label.configure(text=summary_text)
    
    def _cancel(self):
        """Cancel the dialog"""
        self.result = None
        self.dialog.destroy()
    
    def _apply(self):
        """Apply the refinery contents"""
        self.result = self.refinery_contents.copy()
        # Rebuild CSV after materials are applied
        if hasattr(self.cargo_monitor, 'main_app_ref') and hasattr(self.cargo_monitor.main_app_ref, 'prospector_panel'):
            prospector_panel = self.cargo_monitor.main_app_ref.prospector_panel
            csv_path = os.path.join(prospector_panel.reports_dir, "sessions_index.csv")
            prospector_panel.after(100, lambda: prospector_panel._rebuild_csv_from_files_tab(csv_path))
        self.dialog.destroy()
    
    def show(self):
        """Show the dialog and return the result"""
        self.dialog.wait_window()
        return self.result
    
    def _open_material_selector(self):
        """Open a material selection window"""
        from core.constants import MINING_MATERIALS
        
        # Create selection window
        selector = tk.Toplevel(self.dialog)
        selector.title(t('refinery_dialog.select_material_title'))
        selector.geometry("400x500")
        selector.configure(bg="#1e1e1e")
        selector.resizable(False, False)
        selector.transient(self.dialog)
        selector.grab_set()
        
        # Set icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                selector.iconbitmap(icon_path)
            elif icon_path:
                selector.iconphoto(False, tk.PhotoImage(file=icon_path))
        except:
            pass  # Silently handle icon loading errors
        
        # Center on parent
        selector.update_idletasks()
        x = self.dialog.winfo_x() + (self.dialog.winfo_width() // 2) - 200
        y = self.dialog.winfo_y() + (self.dialog.winfo_height() // 2) - 250
        selector.geometry(f"400x500+{x}+{y}")
        
        # Title
        title_label = tk.Label(selector, text=t('refinery_dialog.select_mining_material'), 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=15)
        
        # Search frame
        search_frame = tk.Frame(selector, bg="#1e1e1e")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        tk.Label(search_frame, text=t('refinery_dialog.search'), bg="#1e1e1e", fg="#ffffff").pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=search_var, bg="#404040", fg="#ffffff")
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # Materials listbox
        list_frame = tk.Frame(selector, bg="#1e1e1e")
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        materials_list = tk.Listbox(list_frame, bg="#2d2d2d", fg="#ffffff",
                                  selectbackground="#404040", 
                                  font=("Segoe UI", 9),
                                  yscrollcommand=scrollbar.set)
        materials_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=materials_list.yview)
        
        # Populate list with localized material names
        materials = list(MINING_MATERIALS.keys())
        for material in sorted(materials):
            materials_list.insert(tk.END, get_material(material))
        
        # Search function
        def filter_materials(*args):
            search_term = search_var.get().lower()
            materials_list.delete(0, tk.END)
            for material in sorted(materials):
                localized = get_material(material)
                if search_term in localized.lower():
                    materials_list.insert(tk.END, localized)
        
        search_var.trace('w', filter_materials)
        
        # Buttons
        btn_frame = tk.Frame(selector, bg="#1e1e1e")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        def select_material():
            selection = materials_list.curselection()
            if selection:
                selected = materials_list.get(selection[0])
                self.material_var.set(selected)
            selector.destroy()
        
        def cancel_selection():
            selector.destroy()
        
        select_btn = tk.Button(btn_frame, text=t('common.select'), command=select_material,
                             bg="#4a9eff", fg="#ffffff", font=("Segoe UI", 9, "bold"))
        select_btn.pack(side="right", padx=(5, 0))
        
        cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=cancel_selection,
                             bg="#666666", fg="#ffffff", font=("Segoe UI", 9))
        cancel_btn.pack(side="right")
        
        # Double-click to select
        materials_list.bind("<Double-Button-1>", lambda e: select_material())
        
        # Focus search entry
        search_entry.focus_set()

# --- Cargo Hold Monitor class ---
class CargoMonitor:
    """
    Cargo monitoring system that reads Elite Dangerous game data.
    
    ⚠️ CRITICAL: This class has TWO SEPARATE DISPLAY METHODS:
    
    1. POPUP WINDOW (Optional, rarely used):
       - Method: update_display() - line ~1850
       - Widgets: self.cargo_text, self.cargo_summary
       - Used only when popup window is opened
    
    2. INTEGRATED DISPLAY (PRIMARY - Default in main app):
       - Method: _update_integrated_cargo_display() - line ~3570
       - Widgets: self.integrated_cargo_text, self.integrated_cargo_summary
       - Located in: EliteMiningApp._create_integrated_cargo_monitor()
       - THIS IS THE ONE USERS SEE BY DEFAULT!
    
    ⚠️ WHEN MODIFYING DISPLAY: Update BOTH methods to keep them in sync!
    
    Both modes share the same underlying data:
    - self.cargo_items: Refined minerals/cargo
    - self.materials_collected: Engineering materials (Raw)
    """
    def __init__(self, update_callback=None, capacity_changed_callback=None, ship_info_changed_callback=None, app_dir=None):
        # Threading safety
        self._lock = threading.RLock()  # Reentrant lock for thread safety
        self._stop_event = threading.Event()  # For clean thread shutdown
        
        self.cargo_window = None
        self.cargo_label = None
        self.position = "upper_right"
        self.display_mode = "progress"  # "progress", "detailed", "compact"
        self.transparency = 90
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
        
        # Load saved window position
        saved_pos = load_cargo_window_position()
        self.window_x = saved_pos["x"]
        self.window_y = saved_pos["y"]
        
        self.enabled = False
        self.journal_monitor_active = False
        self.last_journal_file = None
        self.last_file_size = 0
        
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
            "belugaliner": "Beluga Liner",
            "cutter": "Imperial Cutter",
            "dolphin": "Dolphin",
            "empire_trader": "Imperial Clipper",
            "federation_corvette": "Federal Corvette",
            "mandalay": "Mandalay",
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
        # Add callback to notify Ring Finder when new hotspots are added
        self.journal_parser = JournalParser(self.journal_dir, self.user_db, self._on_hotspot_added)
        
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
        
        # Start a separate update check that works without the cargo window
        self._start_background_monitoring()
        
        # Try to initialize cargo capacity from Status.json on startup
        self.refresh_ship_capacity()
        logging.basicConfig(filename="debug_log.txt", level=logging.DEBUG, format='%(asctime)s %(levelname)s %(message)s')
    
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
            if is_new_discovery and not getattr(self, '_catchup_scan_in_progress', False):
                # Use normalized system/body names if provided, otherwise fall back to stored values
                scanned_system = normalized_system or getattr(self, '_current_saa_system', None)
                scanned_body = normalized_body or getattr(self, '_current_saa_body', None)
                if scanned_system:
                    self._check_auto_refresh_ring_finder(scanned_system, scanned_body, hotspots_were_new=True)
            
            # IMMEDIATE EDSM FALLBACK: Fill missing metadata for newly scanned system
            # This ensures auto-refresh shows complete data after the 5-second delay
            if hasattr(main_app, 'ring_finder') and main_app.ring_finder and self.current_system:
                # Check cache to avoid duplicate EDSM queries for same system
                if self.current_system not in self._edsm_fallback_cache:
                    print(f"🔧 Running immediate EDSM fallback for newly scanned system: {self.current_system}")
                    try:
                        # Add to cache immediately
                        self._edsm_fallback_cache.add(self.current_system)
                        
                        # Schedule cache cleanup after 30 seconds
                        if self._edsm_cache_clear_timer:
                            main_app.after_cancel(self._edsm_cache_clear_timer)
                        self._edsm_cache_clear_timer = main_app.after(30000, lambda: self._edsm_fallback_cache.clear())
                        
                        # Run EDSM fallback for the current system immediately
                        if hasattr(main_app.ring_finder, 'edsm'):
                            stats = main_app.ring_finder.edsm.fill_missing_metadata_for_systems_direct([self.current_system])
                            if stats.get('materials_updated', 0) > 0:
                                print(f"✓ EDSM immediate fallback: Updated {stats['rings_updated']} rings, {stats['materials_updated']} materials")
                            else:
                                print(f"ℹ EDSM immediate fallback: No updates needed for {self.current_system}")
                    except Exception as e:
                        print(f"⚠ EDSM immediate fallback failed: {e}")
                else:
                    print(f"⚡ EDSM fallback skipped for {self.current_system} (already processed)")
                    
        except Exception as e:
            # Log error but don't break other functionality
            print(f"Warning: Failed to refresh Ring Finder after hotspot add: {e}")
    
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
                    # Clear status after 3 seconds
                    ring_finder.parent.after(3000, lambda: ring_finder.status_var.set(""))
                    self._auto_refresh_timer = None  # Clear timer reference
                    self._pending_highlight_bodies = []  # Clear after successful refresh
                except Exception as e:
                    pass  # Silent fail in delayed refresh
            
            # Schedule refresh with delay - already on main thread via after()
            self._auto_refresh_timer = main_app.after(delay, do_delayed_refresh)
            
        except Exception as e:
            # Silent fail - don't break journal processing
            pass

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
        if self.ship_name:
            # Capitalize properly and fix Mk II formatting
            formatted_name = self.ship_name.title()
            formatted_name = formatted_name.replace("Mk Ii", "Mk II").replace("Mk Iii", "Mk III")
            formatted_name = formatted_name.replace("Mk Iv", "Mk IV").replace("Mk V", "Mk V")
            formatted_name = formatted_name.replace("Mk Vi", "Mk VI").replace("Mk Vii", "Mk VII")
            parts.append(formatted_name)
        # Ship ident (ID) removed from display - not needed for analytics
        # Users don't need to see (VIPD68) style IDs in reports/analytics
        if ship_type_display and ship_type_display not in ["", "Unknown"]:
            parts.append(f"- {ship_type_display}")
        
        return " ".join(parts) if parts else ""
    
    def create_window(self):
        """Create the cargo monitor as a separate window (not overlay)"""
        if self.cargo_window:
            return
            
        self.cargo_window = tk.Toplevel()
        self.cargo_window.title(t('dialogs.cargo_monitor_title'))
        
        # Set app icon using centralized function
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                self.cargo_window.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                self.cargo_window.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception as e:
            # Use system default icon if all attempts fail
            pass
        
        self.cargo_window.resizable(True, True)  # Make resizable
        self.cargo_window.wm_attributes("-topmost", True)  # Always on top
        
        # Set window size and position using saved position
        self.cargo_window.geometry(f"500x400+{self.window_x}+{self.window_y}")
        
        # Set minimum window size to prevent it from shrinking too small
        self.cargo_window.minsize(500, 400)
        
        # Set window style
        self.cargo_window.configure(bg="#1e1e1e")
        
        # Window close behavior
        self.cargo_window.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Make window draggable by title bar only
        self.cargo_window.bind("<Button-1>", self.start_drag)
        self.cargo_window.bind("<B1-Motion>", self.do_drag)
        
        # Main frame with scrollable text area
        main_frame = tk.Frame(self.cargo_window, bg="#1e1e1e", padx=10, pady=8)
        main_frame.pack(fill="both", expand=True)
        
        # Title label
        title_label = tk.Label(main_frame, text="🚛 " + t('dialogs.cargo_hold_monitor'), 
                              bg="#1e1e1e", fg="#00FF00", 
                              font=("Segoe UI", 10, "bold"))
        title_label.pack(anchor="w")
        
        # Cargo summary label
        self.cargo_summary = tk.Label(
            main_frame,
            text="Cargo: 0/200t (0%)",
            bg="#1e1e1e",
            fg="#00FF00",
            font=("Segoe UI", 10, "normal"),
            justify="left",
            anchor="w"
        )
        self.cargo_summary.pack(anchor="w", pady=(5, 0))
        
        # Separator line
        separator = tk.Frame(main_frame, height=1, bg="#444444")
        separator.pack(fill="x", pady=(5, 5))
        
        # Scrollable cargo list
        list_frame = tk.Frame(main_frame, bg="#1e1e1e")
        list_frame.pack(fill="both", expand=True)
        
        # Create scrollable text widget for cargo contents
        self.cargo_text = tk.Text(
            list_frame,
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 9, "normal"),  # Monospace font for proper alignment
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="none",
            height=10,
            width=30
        )
        
        # Scrollbar for the text widget
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.cargo_text.yview)
        self.cargo_text.configure(yscrollcommand=scrollbar.set)
        
        # Pack text widget and scrollbar
        self.cargo_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Status label for journal monitoring
        self.status_label = tk.Label(
            main_frame,
            text="🔍 " + t('dialogs.monitoring_journal'),
            bg="#1e1e1e",
            fg="#888888",
            font=("Segoe UI", 8, "italic")
        )
        self.status_label.pack(anchor="w", pady=(5, 0))
        
        # Capacity status label
        self.capacity_label = tk.Label(
            main_frame,
            text="⚙️ " + t('dialogs.waiting_loadout'),
            bg="#1e1e1e",
            fg="#666666",
            font=("Segoe UI", 8, "italic")
        )
        self.capacity_label.pack(anchor="w", pady=(2, 0))
        
        # Refinery note - discrete version
        refinery_note = tk.Label(
            main_frame,
            text="ℹ️ " + t('dialogs.refinery_note'),
            bg="#1e1e1e",
            fg="#888888",
            font=("Segoe UI", 7, "italic"),
            wraplength=480,
            justify="left"
        )
        refinery_note.pack(anchor="w", pady=(5, 0))
        
        # Close button
        close_frame = tk.Frame(main_frame, bg="#1e1e1e")
        close_frame.pack(anchor="w", pady=(10, 0))
        
        close_btn = tk.Button(close_frame, text="✕ " + t('common.close'), 
                             command=self.close_window,
                             bg="#444444", fg="#ffffff",
                             activebackground="#555555", activeforeground="#ffffff",
                             font=("Segoe UI", 10, "bold"), relief="flat")
        close_btn.pack()
        
        self.set_position(self.position)
        
        # Force the window size and position after all setup is complete
        self.cargo_window.after(10, lambda: self.cargo_window.geometry(f"500x400+{self.window_x}+{self.window_y}"))
        
        self.update_display()
        
        # Enable live monitoring for Spansh API calls
        self.journal_parser.is_live_monitoring = True
        
        # Start periodic journal checking
        self.check_journal_updates()
    
    def clear_cargo(self):
        """Clear all cargo items"""
        self.cargo_items.clear()
        self.current_cargo = 0
        self.update_display()
    
    def reset_cargo_hold(self):
        """Reset cargo hold to actual game state using real-time Status.json data"""
        print("Resetting cargo hold...")
        
        # Temporarily stop journal monitoring to prevent interference
        old_monitor_state = getattr(self, 'journal_monitor_active', False)
        self.journal_monitor_active = False
        print(f"Reset: Temporarily stopped journal monitoring (was {old_monitor_state})")
        
        # Clear all cargo items and reset counters
        self.cargo_items.clear()
        self.current_cargo = 0
        
        # Reset file timestamps to force fresh read
        self.last_cargo_mtime = 0
        self.last_file_size = 0
        
        success = False
        status_cargo_weight = 0
        
        # Get real-time cargo weight from Status.json (always current)
        if self.read_status_json_cargo():
            status_cargo_weight = self.current_cargo
            success = True
            print(f"Reset: Status.json shows {status_cargo_weight}t total cargo (real-time)")
        
        # Try to get detailed items from Cargo.json, but validate against Status.json
        cargo_json_weight = 0
        if self.read_cargo_json():
            # Calculate total weight from Cargo.json items
            try:
                cargo_json_weight = 0
                for name, item in self.cargo_items.items():
                    if isinstance(item, dict):
                        count = item.get('Count', 0)
                        cargo_json_weight += count
                    elif isinstance(item, (int, float)):
                        cargo_json_weight += item
                    else:
                        print(f"Warning: Unknown cargo item format: {type(item)}")
                
                print(f"Reset: Cargo.json shows {cargo_json_weight}t total cargo")
            except Exception as e:
                print(f"Error calculating Cargo.json weight: {e}")
                cargo_json_weight = 0
            
            # Check if Cargo.json data matches Status.json (within 1 ton tolerance)
            if abs(cargo_json_weight - status_cargo_weight) <= 1:
                print("Reset: Cargo.json data matches Status.json - using detailed items")
                success = True
            else:
                print(f"Reset: Cargo.json data is outdated ({cargo_json_weight}t vs {status_cargo_weight}t)")
                print("Reset: Clearing outdated Cargo.json data, using Status.json weight only")
                # Clear the outdated detailed items but keep the accurate weight
                self.cargo_items.clear()
                self.current_cargo = status_cargo_weight
                success = True
        
        # If we only have weight but no detailed items, show a placeholder entry
        if success and not self.cargo_items and self.current_cargo > 0:
            self.cargo_items['Unknown Cargo'] = {
                'Name': 'Unknown Cargo',
                'Count': self.current_cargo,
                'Description': 'Open cargo hold in Elite Dangerous to see details'
            }
            print(f"Reset: Created placeholder for {self.current_cargo}t of unknown cargo")
        
        # If no data from either source, try journal as last resort
        if not success or (not self.cargo_items and self.current_cargo == 0):
            print("Reset: Trying journal data as fallback...")
            self.force_cargo_update()
            if self.cargo_items or self.current_cargo > 0:
                success = True
                print("Reset: Loaded cargo from journal")
        
        # Update display with force refresh
        self.update_display()
        
        # Force refresh the display by clearing any cached display elements
        if hasattr(self, 'item_vars'):
            self.item_vars.clear()
        
        # Update display again to ensure changes are shown
        self.update_display()
        
        # Notify main app
        if self.update_callback:
            self.update_callback()
        
        status_msg = f"Cargo reset: {len(self.cargo_items)} items, {self.current_cargo}t total"
        print(status_msg)
        
        # Wait a moment then restart journal monitoring to prevent immediate override
        import threading
        def restart_monitoring():
            import time
            time.sleep(3)  # Wait 3 seconds before restarting monitoring
            self.journal_monitor_active = old_monitor_state
            print(f"Reset: Journal monitoring restarted (set to {old_monitor_state})")
        
        if old_monitor_state:
            thread = threading.Thread(target=restart_monitoring, daemon=True)
            thread.start()
            print("Reset: Scheduled journal monitoring restart in 3 seconds")
        
        return success
    
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
            self.update_display()
            
            # Update mining mission progress from cargo
            self._update_mission_progress_from_cargo()
            
            # Notify main app of changes
            if self.update_callback:
                self.update_callback()
            
            if hasattr(self, 'status_label'):
                self.status_label.configure(text=f"✅ Cargo.json: {len(self.cargo_items)} items, {self.current_cargo}t")
            
            return True
            
        except Exception as e:
            return False
    
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
            print(f"[MISSIONS] Error updating progress: {e}")
    
    def force_cargo_update(self):
        """Force read the latest cargo data from Cargo.json and journal"""
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="🔄 " + t('dialogs.forcing_update'))
        
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
                        self.update_display()
                        
                        # Notify main app of changes
                        if self.update_callback:
                            self.update_callback()
                        
                        if hasattr(self, 'status_label'):
                            self.status_label.configure(text=f"✅ Cargo loaded: {len(self.cargo_items)} items, {self.current_cargo}t")
                    else:
                        self.current_cargo = count  # At least show the total
                        self.update_display()
                        
                        # Notify main app of changes
                        if self.update_callback:
                            self.update_callback()
                        
                        if hasattr(self, 'status_label'):
                            self.status_label.configure(text=f"⚠️ {count}t detected - need detailed data (open cargo in game)")
                else:
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text="❌ " + t('dialogs.no_cargo_data'))
                        
        except Exception as e:
            if hasattr(self, 'status_label'):
                self.status_label.configure(text="❌ " + t('dialogs.journal_read_error'))
    
    def show_cargo_instructions(self):
        """Show instructions for getting detailed cargo data"""
        instructions = f"""🔍 HOW TO GET DETAILED CARGO DATA
        
📋 Current Status: Your cargo monitor shows {self.current_cargo}/{self.max_cargo} tons total, 
but Elite Dangerous is only providing the total count without 
the detailed breakdown of items.

✅ TO GET DETAILED CARGO INVENTORY:

1. 🎮 Make sure Elite Dangerous is running
2. 🗂️ Press "4" key to open your right panel
3. 📦 Click on "CARGO" tab to view your cargo hold
4. ⏱️ Wait 2-3 seconds for Elite to log the data
5. 🔄 Click "Force Update" in this cargo monitor

🔧 ALTERNATIVE METHODS:
• Buy/sell any item at a station (triggers detailed cargo event)
• Jettison 1 unit of cargo (triggers update, then scoop it back)
• Dock/undock at a station
• Transfer cargo between ship and SRV

💡 WHY THIS HAPPENS:
Elite Dangerous sometimes only writes simplified cargo events 
that show total weight but not individual items. Opening the 
cargo panel forces Elite to write detailed inventory data.

📊 YOUR CURRENT DATA:
• Ship Capacity: {self.max_cargo} tons (✅ detected correctly)
• Current Total: {self.current_cargo} tons (✅ detected correctly)  
• Item Details: {"✅ Available - " + str(len(self.cargo_items)) + " items" if self.cargo_items else "❌ Not available (need detailed cargo event)"}

🎯 Try opening your cargo hold in Elite, then click Force Update!"""

        # Create help window
        try:
            help_window = tk.Toplevel(self.cargo_window)
            help_window.title(t('dialogs.cargo_monitor_help'))
            help_window.geometry("600x500")
            help_window.configure(bg="#2c3e50")
            
            # Make it stay on top
            help_window.attributes('-topmost', True)
            
            # Add text widget with scrollbar
            text_frame = tk.Frame(help_window, bg="#2c3e50")
            text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            scrollbar = ttk.Scrollbar(text_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            text_widget = tk.Text(text_frame, bg="#34495e", fg="#ecf0f1", 
                                 font=("Segoe UI", 9), wrap=tk.WORD,
                                 yscrollcommand=scrollbar.set)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=text_widget.yview)
            
            text_widget.insert(tk.END, instructions)
            text_widget.config(state=tk.DISABLED)
            
            # Add close button
            close_btn = tk.Button(help_window, text="✅ " + t('dialogs.got_it'), 
                                 command=help_window.destroy,
                                 bg="#27ae60", fg="white", 
                                 font=("Segoe UI", 10, "bold"))
            close_btn.pack(pady=10)
        except Exception as e:
            print(f"Error showing help window: {e}")
    
    def start_drag(self, event):
        """Start dragging the window"""
        self.start_x = event.x_root
        self.start_y = event.y_root
    
    def do_drag(self, event):
        """Handle window dragging"""
        if self.cargo_window:
            x = self.cargo_window.winfo_x() + (event.x_root - self.start_x)
            y = self.cargo_window.winfo_y() + (event.y_root - self.start_y)
            self.cargo_window.geometry(f"+{x}+{y}")
            self.window_x = x
            self.window_y = y
            self.start_x = event.x_root
            self.start_y = event.y_root
    
    def show(self):
        """Show the cargo monitor"""
        self.enabled = True
        if not self.cargo_window:
            self.create_window()
        self.cargo_window.deiconify()
        self.update_display()
    
    def hide(self):
        """Hide the cargo monitor"""
        self.enabled = False
        if self.cargo_window:
            # Save current window position before hiding
            self._save_window_position()
            self.cargo_window.withdraw()
    
    def set_position(self, position: str):
        """Set window position"""
        self.position = position
        if not self.cargo_window:
            return
            
        screen_width = self.cargo_window.winfo_screenwidth()
        screen_height = self.cargo_window.winfo_screenheight()
        
        # Get current window size or use default
        try:
            current_geometry = self.cargo_window.geometry()
            # Parse current geometry (format: "500x400+x+y")
            size_part = current_geometry.split('+')[0]
            width, height = size_part.split('x')
            window_width = int(width)
            window_height = int(height)
        except:
            # Use default size if parsing fails
            window_width = 500
            window_height = 400
            
        # Enforce minimum size
        window_width = max(window_width, 500)  # Minimum 500px wide
        window_height = max(window_height, 400)  # Minimum 400px tall
        
        if position == "upper_right":
            x = screen_width - window_width - 50
            y = 50
        elif position == "upper_left":
            x = 50
            y = 50
        elif position == "lower_right":
            x = screen_width - window_width - 50
            y = screen_height - window_height - 100
        elif position == "lower_left":
            x = 50
            y = screen_height - window_height - 100
        else:  # custom position
            x = self.window_x
            y = self.window_y
            
        self.cargo_window.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def _save_window_position(self):
        """Save current window position to config"""
        if self.cargo_window:
            try:
                # Get current window geometry
                current_geometry = self.cargo_window.geometry()
                # Parse position from geometry string (format: "500x400+x+y")
                if '+' in current_geometry:
                    parts = current_geometry.split('+')
                    if len(parts) >= 3:
                        x = int(parts[1])
                        y = int(parts[2])
                        save_cargo_window_position(x, y)
            except Exception as e:
                pass
    
    def _on_close(self):
        """Handle window close event - save position and hide window"""
        self._save_window_position()
        self.hide()
    
    def set_display_mode(self, mode: str):
        """Set display mode: progress, detailed, compact"""
        self.display_mode = mode
        self.update_display()
    
    def set_max_cargo(self, max_cargo: int):
        """Set maximum cargo capacity"""
        self.max_cargo = max_cargo
        self.update_display()
    
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
        self.update_display()
        
        # Record mining activity for session end detection
        self.record_mining_activity()
        
        # Notify main app of changes
        if self.update_callback:
            self.update_callback()
    
    def set_total_cargo(self, total: int):
        """Set total cargo directly (for manual updates)"""
        self.current_cargo = total
        self.update_display()
        
        # Notify main app of changes
        if self.update_callback:
            self.update_callback()
    
    def update_display(self):
        """
        Update the POPUP WINDOW display with exact cargo contents.
        
        ⚠️ WARNING: This is for the OPTIONAL popup window, NOT the main app display!
        ⚠️ Most users use the INTEGRATED display instead (see _update_integrated_cargo_display)
        ⚠️ When modifying display logic, update BOTH methods!
        """
        if not hasattr(self, 'cargo_summary') or not hasattr(self, 'cargo_text'):
            return
            
        percentage = (self.current_cargo / self.max_cargo * 100) if self.max_cargo > 0 else 0
        
        # Update summary line
        status_color = ""
        if percentage > 95:
            status_color = " 🔴 FULL!"
        elif percentage > 85:
            status_color = " 🟡 Nearly Full"
        elif percentage > 50:
            status_color = " 🟢 Good"
            
        summary_text = f"Total: {self.current_cargo}/{self.max_cargo} tons ({percentage:.1f}%){status_color}"
        self.cargo_summary.configure(text=summary_text)
        
        # Update detailed cargo list
        self.cargo_text.configure(state="normal")  # Enable editing temporarily
        self.cargo_text.delete(1.0, tk.END)
        
        # Display Cargo Hold section
        if not self.cargo_items:
            self.cargo_text.insert(tk.END, "CARGO DETECTED BUT NO ITEM DETAILS\n\n")
            
            if self.current_cargo > 0:
                self.cargo_text.insert(tk.END, f"🔍 Total cargo detected: {self.current_cargo} tons\n")
                self.cargo_text.insert(tk.END, f"⚙️ Ship capacity: {self.max_cargo} tons\n\n")
                self.cargo_text.insert(tk.END, "❌ Elite Dangerous is only providing total weight\n")
                self.cargo_text.insert(tk.END, "    without detailed item breakdown.\n\n")
                self.cargo_text.insert(tk.END, "✅ TO GET DETAILED CARGO:\n")
                self.cargo_text.insert(tk.END, "1. Open Elite Dangerous\n")
                self.cargo_text.insert(tk.END, "2. Press '4' key → Right Panel\n")
                self.cargo_text.insert(tk.END, "3. Click 'CARGO' tab\n")
                self.cargo_text.insert(tk.END, "4. Wait 2-3 seconds\n")
                self.cargo_text.insert(tk.END, "5. Click 'Force Update' here\n\n")
                self.cargo_text.insert(tk.END, "💡 Alternative: Buy/sell anything at a station\n")
                self.cargo_text.insert(tk.END, "   or jettison 1 unit of cargo (then scoop it back)")
            else:
                self.cargo_text.insert(tk.END, f"🔸 {t('sidebar.empty_cargo')}\n\n")
                self.cargo_text.insert(tk.END, "📋 To see your actual cargo:\n")
                self.cargo_text.insert(tk.END, "1. Open Elite Dangerous\n")
                self.cargo_text.insert(tk.END, "2. Open your cargo hold (4 key)\n") 
                self.cargo_text.insert(tk.END, "3. Click 'Force Update' button")
        else:
            # Sort items by quantity (highest first)
            sorted_items = sorted(self.cargo_items.items(), key=lambda x: x[1], reverse=True)
            
            # Configure clickable limpet tag (theme-aware color + hand cursor)
            limpet_color = "#ff8c00" if self.current_theme == "elite_orange" else "#e0e0e0"
            self.cargo_text.tag_configure("limpet_clickable", 
                                         foreground=limpet_color)
            self.cargo_text.tag_bind("limpet_clickable", "<Button-1>", 
                                    lambda e: self.adjust_limpet_count())
            self.cargo_text.tag_bind("limpet_clickable", "<Enter>", 
                                    lambda e: self.cargo_text.configure(cursor="hand2"))
            self.cargo_text.tag_bind("limpet_clickable", "<Leave>", 
                                    lambda e: self.cargo_text.configure(cursor=""))
            
            # Add each cargo item with type icons - single line format with proper alignment
            for i, (item_name, quantity) in enumerate(sorted_items, 1):
                # Format item name (remove underscores, capitalize) 
                display_name = item_name.replace('_', ' ').replace('$', '').title()
                # Limit name length for better alignment
                if len(display_name) > 12:
                    display_name = display_name[:12]
                
                # Check if this is a limpet
                is_limpet = "limpet" in item_name.lower()
                
                # Add type-specific icons (no space after - we'll add it in formatting)
                icon = ""
                if is_limpet:
                    icon = "🤖"  # Robot for limpets
                elif any(mineral in item_name.lower() for mineral in ['painite', 'diamond', 'opal', 'alexandrite', 'serendibite', 'benitoite']):
                    icon = "💎"  # Diamond for precious materials
                elif any(metal in item_name.lower() for metal in ['gold', 'silver', 'platinum', 'palladium', 'osmium']):
                    icon = "🥇"  # Medal for metals
                else:
                    icon = "📦"  # Box for other cargo
                
                # Single line format with proper alignment: Icon + Name + Quantity
                line = f"{icon} {display_name:<12} {quantity:>5}t\n"
                
                # Make limpet lines clickable
                if is_limpet:
                    self.cargo_text.insert(tk.END, line, "limpet_clickable")
                else:
                    self.cargo_text.insert(tk.END, line)
            
            # Add total at bottom
            self.cargo_text.insert(tk.END, "─" * 30 + "\n")
            self.cargo_text.insert(tk.END, f"Total Items: {len(self.cargo_items)}\n")
            self.cargo_text.insert(tk.END, f"Total Weight: {self.current_cargo} tons")
        
        # Display Engineering Materials section
        if self.materials_collected:
            self.cargo_text.insert(tk.END, "\n\n")
            self.cargo_text.insert(tk.END, "Engineering Materials 🔩\n")
            self.cargo_text.insert(tk.END, "─" * 30 + "\n")
            
            # Sort materials alphabetically
            sorted_materials = sorted(self.materials_collected.items(), key=lambda x: x[0])
            
            for material_name, quantity in sorted_materials:
                # Get grade for this material
                grade = self.MATERIAL_GRADES.get(material_name, 0)
                
                # Use localized name for display if available, otherwise use English name
                localized_name = self.materials_localized_names.get(material_name, material_name)
                display_name = localized_name[:20]
                line = f"{display_name} (G{grade}){' ' * (24 - len(display_name))}{quantity:>4}"
                self.cargo_text.insert(tk.END, f"{line}\n")
            
            # Add materials total
            self.cargo_text.insert(tk.END, "─" * 30 + "\n")
            self.cargo_text.insert(tk.END, f"Total Materials: {len(self.materials_collected)}\n")
            self.cargo_text.insert(tk.END, f"Total Pieces: {sum(self.materials_collected.values())}")
        
        # Make text widget read-only
        self.cargo_text.configure(state="disabled")
        
        # Only auto-scroll if user was already at bottom (don't fight manual scrolling)
        # Check if scrollbar is at or near bottom (within 5% of end)
        try:
            yview = self.cargo_text.yview()
            # yview returns (top, bottom) as fractions 0.0 to 1.0
            # Only scroll to end if bottom is at least 0.95 (user is near bottom)
            if yview[1] >= 0.95:
                self.cargo_text.see(tk.END)
        except:
            # If check fails, default to scrolling to end
            self.cargo_text.see(tk.END)
        
        # Update window size to fit content (but keep resizable)
        self.cargo_window.update_idletasks()
    
    def close_window(self):
        """Close the cargo monitor window"""
        if self.cargo_window:
            # Save current window position before closing
            self._save_window_position()
            self.cargo_window.destroy()
            self.cargo_window = None
            self.journal_monitor_active = False
    
    def clear_cargo(self):
        """Clear all cargo items"""
        self.cargo_items.clear()
        self.current_cargo = 0
        self.update_display()
    
    def reset_materials(self):
        """Reset materials counters and session tracking (called when mining session starts)"""
        self.materials_collected.clear()
        self.session_minerals_mined.clear()
        self.session_materials_collected.clear()
        
        # Take snapshot of current cargo as baseline - don't count pre-existing cargo
        # This ensures only NEW materials mined after session start are tracked
        # (Already handled by cargo_items being preserved, tracking only counts increases)
        
        if hasattr(self, 'cargo_window') and self.cargo_window:
            self.update_display()
        print("[CargoMonitor] Materials counters and session tracking reset")
        print(f"[CargoMonitor] Session baseline: {len(self.cargo_items)} items, {self.current_cargo}t total")
    
    def start_journal_monitoring(self):
        """Start monitoring Elite Dangerous journal files"""
        self.journal_monitor_active = True
        self.find_latest_journal()
    
    def _start_background_monitoring(self):
        """Start background monitoring that works without cargo window"""
        self.last_status_mtime = 0
        self.last_capacity_check = 0
        self.last_heartbeat = time.time()  # Track thread health
        
        def background_monitor():
            while self.journal_monitor_active and not self._stop_event.is_set():
                try:
                    # Heartbeat: Log every 60 seconds to verify thread is alive
                    current_time = time.time()
                    if current_time - self.last_heartbeat > 60:
                        self.last_heartbeat = current_time
                        with self._lock:  # Thread-safe access to materials_collected
                            materials_count = len(self.materials_collected)
                        logging.info(f"[HEARTBEAT] Background monitor alive - Materials: {materials_count}")
                    
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
                    
                    # Check if journal file has grown (new entries) OR if a newer journal file exists
                    if self.last_journal_file and os.path.exists(self.last_journal_file):
                        current_size = os.path.getsize(self.last_journal_file)
                        
                        # Also check if there's a NEWER journal file (daily rotation)
                        journal_files = glob.glob(os.path.join(self.journal_dir, "Journal.*.log"))
                        if journal_files:
                            latest_file = max(journal_files, key=os.path.getmtime)
                            if latest_file != self.last_journal_file:
                                logging.info(f"[JOURNAL_ROTATION] Detected new journal file: {os.path.basename(latest_file)}")
                                self.last_journal_file = latest_file
                                self.last_file_size = 0  # Start reading from beginning of new file
                                continue  # Skip to next iteration to process new file
                        
                        if current_size > self.last_file_size:
                            self.read_new_journal_entries()
                            self.last_file_size = current_size
                    else:
                        # Check for new journal file
                        self.find_latest_journal()
                        
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
                            
                            if hasattr(self, 'capacity_label'):
                                self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {self.max_cargo} tons")
                            if hasattr(self, 'status_label'):
                                self.status_label.configure(text=f"🔄 Ship changed: {old_capacity}t → {self.max_cargo}t")
                            
                            self.update_display()
                            
                            # Notify main app of capacity change
                            if self.capacity_changed_callback:
                                self.capacity_changed_callback(self.max_cargo)
                                
                            # Force refresh cargo data after ship change
                            self.read_cargo_json()
                            
        except Exception as e:
            pass  # Silent fail in background monitoring
    
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
            print(f"Error reading Status.json: {e}")
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
        
        # Close cargo window if open
        if self.cargo_window:
            try:
                self.cargo_window.destroy()
                self.cargo_window = None
            except:
                pass
        
        print("[CargoMonitor] Cleanup completed")
    
    def find_latest_journal(self):
        """Find the most recent journal file"""
        try:
            if not os.path.exists(self.journal_dir):
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="❌ " + t('dialogs.ed_folder_not_found'))
                return
                
            journal_files = glob.glob(os.path.join(self.journal_dir, "Journal.*.log"))
            if not journal_files:
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="❌ " + t('dialogs.no_journal_files'))
                return
                
            # Get the most recent journal file
            latest_file = max(journal_files, key=os.path.getmtime)
            self.last_journal_file = latest_file
            self.last_file_size = os.path.getsize(latest_file)
            
            if hasattr(self, 'status_label'):
                filename = os.path.basename(latest_file)
                self.status_label.configure(text=f"📊 Monitoring: {filename}")
            
            # Scan for existing cargo capacity in the journal
            self.scan_journal_for_cargo_capacity(latest_file)
            
        except Exception as e:
            print(f"Error finding journal files: {e}")
            if hasattr(self, 'status_label'):
                self.status_label.configure(text="❌ " + t('dialogs.journal_monitor_error'))
    
    def scan_journal_for_cargo_capacity(self, journal_file):
        """Scan existing journal file for the most recent CargoCapacity, current system location, and ring metadata"""
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
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
                    
                    # Capture ship info from LoadGame or Loadout events
                    if event_type in ["LoadGame", "Loadout"]:
                        if not self.ship_name:  # Only capture if not already set
                            self.ship_name = event.get("ShipName", "")
                            self.ship_ident = event.get("ShipIdent", "")
                            # Prefer Ship_Localised, use mapping for Ship field if needed
                            if "Ship_Localised" in event:
                                self.ship_type = event["Ship_Localised"]
                            elif "Ship" in event:
                                ship_id = event["Ship"].lower()
                                self.ship_type = self.ship_type_map.get(ship_id, event["Ship"].replace("_", " ").title())
                    
                    # Look for cargo capacity (existing logic)
                    if not cargo_found and event_type == "Loadout":
                        # Check for CargoCapacity at root level
                        if "CargoCapacity" in event:
                            old_capacity = self.max_cargo
                            self.max_cargo = event["CargoCapacity"]
                            if hasattr(self, 'capacity_label'):
                                self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {self.max_cargo} tons")
                            self.update_display()
                            
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
                            if hasattr(self, 'capacity_label'):
                                self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {self.max_cargo} tons")
                            self.update_display()
                            
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
                        self.journal_parser.process_scan(event)
                        scans_processed += 1
                        continue
                    
                    # Stop scanning if we found cargo and location (but continue processing scans)
                    if cargo_found and location_found and scans_processed >= max_scans:
                        break
                except json.JSONDecodeError:
                    continue  # Skip invalid JSON lines
        except Exception as e:
            pass
    
    def check_journal_updates(self):
        """Check for journal file updates and cargo changes"""
        if not self.journal_monitor_active or not self.cargo_window:
            return
            
        try:
            # First priority: Check for Cargo.json updates (most accurate)
            self.read_cargo_json()
            
            # Check if journal file has grown (new entries)
            if self.last_journal_file and os.path.exists(self.last_journal_file):
                current_size = os.path.getsize(self.last_journal_file)
                if current_size > self.last_file_size:
                    self.read_new_journal_entries()
                    self.last_file_size = current_size
            else:
                # Check for new journal file
                self.find_latest_journal()
                
        except Exception as e:
            print(f"Error checking updates: {e}")
        
        # Schedule next check
        if self.cargo_window:
            self.cargo_window.after(1000, self.check_journal_updates)  # Check every second
            
        # Check for session end (after scheduling next check)
        self.check_session_end()
    
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
                
                # Get parent window (prefer main app over cargo window for proper positioning)
                parent_window = None
                if hasattr(self, 'prospector_panel') and self.prospector_panel:
                    parent_window = self.prospector_panel.winfo_toplevel()
                elif self.cargo_window:
                    parent_window = self.cargo_window
                
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
                        
                        # Update display with adjustment info
                        if hasattr(self, 'cargo_text') and self.cargo_text:
                            self.cargo_text.insert(tk.END, f"\n⚗️ REFINERY ADJUSTMENT:\n")
                            for material, quantity in result.items():
                                self.cargo_text.insert(tk.END, f"   +{material}: {quantity} tons\n")
                            self.cargo_text.insert(tk.END, f"📊 Total Added: {refinery_total} tons from refinery\n")
                            self.cargo_text.see(tk.END)
                        
                        # Update all displays to reflect new cargo totals
                        self.update_display()
                        
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
                    print(f"Error showing refinery dialog: {e}")
    
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
            elif self.cargo_window:
                parent_window = self.cargo_window
            
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
                    print(f"Error showing refinery dialog in multi-session: {e}")
                    
        except Exception as e:
            print(f"Error prompting for refinery contents: {e}")
    
    def read_new_journal_entries(self):
        """Read new entries from the journal file with retry logic for file locking issues"""
        max_retries = 3
        retry_delay = 0.1  # 100ms delay between retries
        
        for attempt in range(max_retries):
            try:
                with open(self.last_journal_file, 'r', encoding='utf-8') as f:
                    f.seek(self.last_file_size)  # Start from where we left off
                    new_lines = f.readlines()
                    
                for line in new_lines:
                    line = line.strip()
                    if line:
                        self.process_journal_event(line)
                
                # Success - exit retry loop
                return
                        
            except PermissionError as e:
                # File is locked by another application - retry
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"Journal file locked by another application after {max_retries} retries (other apps scanning journals?)")
            except FileNotFoundError:
                # Journal file was deleted/rotated - this is normal, find new journal
                print(f"Journal file not found (rotated to new file): {self.last_journal_file}")
                self.find_latest_journal()
                return
            except Exception as e:
                print(f"Error reading journal entries: {e}")
                return
    
    def process_journal_event(self, line: str):
        """Process a single journal event"""
        try:
            event = json.loads(line)
            event_type = event.get("event", "")
            
            # Track ship information from LoadGame and Loadout events
            if event_type in ["LoadGame", "Loadout"]:
                # Extract ship name, ident, and type
                self.ship_name = event.get("ShipName", "")
                self.ship_ident = event.get("ShipIdent", "")
                # Prefer Ship_Localised, use mapping for Ship field if needed
                if "Ship_Localised" in event:
                    self.ship_type = event["Ship_Localised"]
                elif "Ship" in event:
                    ship_id = event["Ship"].lower()
                    self.ship_type = self.ship_type_map.get(ship_id, event["Ship"].replace("_", " ").title())
                
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
                    if hasattr(self, 'capacity_label'):
                        self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {self.max_cargo} tons")
                    self.update_display()
                    
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
                        if hasattr(self, 'capacity_label'):
                            self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {self.max_cargo} tons")
                        self.update_display()
                        
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
                    if hasattr(self, 'capacity_label'):
                        self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {total_capacity} tons")
                    self.update_display()
                    
                    # Notify main app of capacity change
                    if old_capacity != self.max_cargo and self.capacity_changed_callback:
                        self.capacity_changed_callback(self.max_cargo)
            

            
            elif event_type in ["ShipyardSwap", "StoredShips", "LoadGame", "ShipyardBuy", "ShipyardSell", 
                                "ShipyardTransfer", "SwitchToMainShip", "VehicleSwitch", "Commander", "Location"]:
                # Handle ship changes - aggressive capacity refresh
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="🚀 " + t('dialogs.ship_changed'))
                
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
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text="⚠️ " + t('dialogs.capacity_failed'))
                    self.cargo_items.clear()
                    self.current_cargo = 0
                    self.max_cargo = 200  # Reset to default
                    self.update_display()
                    
                    # Schedule delayed retry
                    if hasattr(self, 'cargo_window') and self.cargo_window:
                        self.cargo_window.after(2000, self._delayed_capacity_refresh)
                
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
                    self.update_display()
                    
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text=f"📊 Detailed cargo: {len(self.cargo_items)} items, {self.current_cargo}t")
                        
                elif count > 0:
                    # We only have total count - update current cargo but keep existing items
                    if count != self.current_cargo:
                        self.current_cargo = count
                        self.update_display()
                        
                        if hasattr(self, 'status_label'):
                            self.status_label.configure(text=f"📊 Cargo total: {self.current_cargo}t (no details)")
                
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
                    self.update_display()
                    
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text=f"💰 Sold {count}x {item_name}")
                    
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
                self.update_display()
                
                # Notify main app to update mineral analysis table
                print(f"[DEBUG] CargoTransfer complete - notifying main app with cargo_items: {self.cargo_items}")
                if self.update_callback:
                    self.update_callback()
                
                # Only count minerals transferred TO carrier for multi-session tracking
                if total_transferred > 0:
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text=f"📦 Transferred {total_transferred}t to carrier")
                    
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
                    self.update_display()
                    
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text=f"🗑️ Ejected {count}x {item_name}")
                    
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
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text="⚙️ " + t('dialogs.cargo_module_changed'))
                    
                    # Force immediate capacity refresh
                    refresh_success = self.refresh_ship_capacity()
                    
                    # If Status.json doesn't have updated capacity yet, try journal scan
                    if not refresh_success:
                        self._force_loadout_scan()
                    
                    # Final fallback - force a delayed refresh to catch Status.json updates
                    if hasattr(self, 'cargo_window') and self.cargo_window:
                        self.cargo_window.after(1000, self._delayed_capacity_refresh)

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
            
            elif event_type == "CarrierLocation":
                # CarrierLocation tells us where YOUR carrier is
                # This is informational - it does NOT count as a visit because:
                # - If carrier jumped while online, CarrierJump event already counted
                # - If carrier jumped while offline, this just tells us where it is now
                # We only use this to update the current system display
                carrier_type = event.get("CarrierType", "")
                system_name = event.get("StarSystem", "")
                
                if system_name and carrier_type == "FleetCarrier":
                    # Update current system display but DON'T count as visit
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, 'update_current_system'):
                        self.main_app_ref.update_current_system(system_name, None, count_visit=False)
                        
            elif event_type == "Scan":
                # Process Scan events through JournalParser to store ring info
                try:
                    self.journal_parser.process_scan(event)
                except Exception as scan_err:
                    print(f"Warning: Failed to process Scan event: {scan_err}")
                        
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
                    if hasattr(self, 'status_label') and body_name:
                        signals = event.get("Signals", [])
                        if signals:
                            first_signal = signals[0]
                            material_name = first_signal.get("Type_Localised", first_signal.get("Type", ""))
                            count = first_signal.get("Count", 0)
                            self.status_label.configure(
                                text=f"🔍 Ring scan: {material_name} ({count}) in {body_name}"
                            )
                    
                    print(f"✓ SAASignalsFound processed successfully")
                    
                except Exception as saa_err:
                    print(f"Warning: Failed to process SAASignalsFound event: {saa_err}")
            
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
                            
                            # Update popup window display if it exists
                            if hasattr(self, 'cargo_window') and self.cargo_window:
                                self.update_display()
                                logging.debug("[MaterialCollected] Updated popup window display")
                            
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
        except Exception as e:
            pass
    
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
            print(f"Error extracting cargo capacity: {e}")
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
                            if hasattr(self, 'capacity_label'):
                                self.capacity_label.configure(text=f"⚙️ Ship cargo capacity: {self.max_cargo} tons")
                            if hasattr(self, 'status_label'):
                                self.status_label.configure(text=f"🔄 Updated cargo capacity: {old_capacity}t → {self.max_cargo}t")
                            self.update_display()
                            
                            # Notify main app of capacity change
                            if self.capacity_changed_callback:
                                self.capacity_changed_callback(self.max_cargo)
                            
                            # Force update cargo data after capacity change
                            self.read_cargo_json()
                            self._force_cargo_refresh()
                            
                            return True
                    else:
                        # Invalid capacity detected - try to recover from journal
                        if hasattr(self, 'status_label'):
                            self.status_label.configure(text=f"⚠️ Invalid capacity {new_capacity}t - checking journal...")
                        self._recover_capacity_from_journal()
                        
        except Exception as e:
            # If Status.json fails, try to recover from journal
            if hasattr(self, 'status_label'):
                self.status_label.configure(text="⚠️ " + t('dialogs.status_json_error'))
            self._recover_capacity_from_journal()
        return False
    
    def _recover_capacity_from_journal(self):
        """Recover capacity info from journal when Status.json fails"""
        try:
            if self.last_journal_file and os.path.exists(self.last_journal_file):
                self.scan_journal_for_cargo_capacity(self.last_journal_file)
            else:
                self.find_latest_journal()
        except Exception as e:
            pass  # Silent recovery attempt
    
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
        except Exception as e:
            pass
    
    def _delayed_capacity_refresh(self):
        """Delayed capacity refresh as last resort"""
        try:
            if hasattr(self, 'status_label'):
                self.status_label.configure(text="🔄 " + t('dialogs.retrying_capacity'))
            
            # Try all methods again
            if self.refresh_ship_capacity() or self._validate_cargo_capacity():
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="✅ " + t('dialogs.capacity_detected'))
            else:
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="⚠️ " + t('dialogs.default_capacity'))
        except Exception as e:
            pass
    
    def _force_cargo_refresh(self):
        """Force immediate cargo data refresh from all sources"""
        try:
            # Clear current data to force fresh read
            old_items = self.cargo_items.copy()
            old_cargo = self.current_cargo
            
            # Read from Cargo.json first (most accurate)
            self.read_cargo_json()
            
            # If no data from Cargo.json, try reading latest journal entries
            if not self.cargo_items and self.last_journal_file:
                self.read_new_journal_entries()
            
            # Update display if we got new data
            if self.cargo_items != old_items or self.current_cargo != old_cargo:
                self.update_display()
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text=f"🔄 Cargo refreshed: {self.current_cargo}t")
                    
        except Exception as e:
            pass  # Silent fail
    
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
            if hasattr(self, 'status_label'):
                self.status_label.configure(text=f"⚠️ Invalid capacity {self.max_cargo}t - refreshing...")
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
        if hasattr(self, 'cargo_window') and self.cargo_window:
            self.update_display()
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
            elif self.cargo_window:
                parent = self.cargo_window
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
            dialog.title(t('dialogs.adjust_limpets_title'))
            dialog.configure(bg=bg_color)
            dialog.resizable(False, False)
            dialog.transient(parent)
            dialog.grab_set()
            
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
                    self.update_display()
                    # Also update integrated display if available
                    if hasattr(self, 'main_app_ref') and hasattr(self.main_app_ref, '_update_integrated_cargo_display'):
                        self.main_app_ref._update_integrated_cargo_display()
                else:
                    print(f"[LIMPET] Failed to update Cargo.json")
                    
        except Exception as e:
            print(f"[LIMPET] Error adjusting limpet count: {e}")
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
            print(f"[LIMPET] Error updating Cargo.json: {e}")
            import traceback
            traceback.print_exc()
            return False

    def show_refinery_dialog(self):
        """Show the refinery adjustment dialog and store the results"""
        try:
            dialog = RefineryDialog(
                parent=self.cargo_window if self.cargo_window else None,
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
                
                # Update display with adjustment info
                if hasattr(self, 'cargo_text') and self.cargo_text:
                    self.cargo_text.insert(tk.END, f"\n⚗️ REFINERY MATERIALS ADDED:\n")
                    for material, quantity in result.items():
                        self.cargo_text.insert(tk.END, f"   +{material}: {quantity} tons\n")
                    self.cargo_text.insert(tk.END, f"📊 Total Added: {total_refinery} tons from refinery\n")
                    self.cargo_text.see(tk.END)
                
                # Update all displays to reflect new cargo totals
                self.update_display()
                
                # Notify main app of changes
                if self.update_callback:
                    self.update_callback()
                
                # Auto-update CSV if we have a prospector panel reference and manual materials were added
                print(f"DEBUG: About to call _update_csv_after_refinery_addition with materials: {result}")
                self._update_csv_after_refinery_addition(result)
            else:
                print("Refinery dialog cancelled")
                
        except Exception as e:
            print(f"Error showing refinery dialog: {e}")
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
                        if hasattr(prospector_panel, 'reports_window') and prospector_panel.reports_window:
                            prospector_panel._refresh_reports_window()
                    except Exception as e:
                        print(f"Error refreshing reports displays: {e}")
                else:
                    print("Failed to update CSV row")
            else:
                print("Could not extract timestamp from session filename")
                
        except Exception as e:
            print(f"Error updating CSV after refinery addition: {e}")
            import traceback
            traceback.print_exc()

from prospector_panel import ProspectorPanel

# -------------------- Main GUI --------------------

from column_visibility_helper import ColumnVisibilityMixin


class App(tk.Tk, ColumnVisibilityMixin):
    def _set_dark_title_bar(self):
        """Placeholder - title bar uses default Windows styling (light/white)"""
        # Dark title bar was too black - keeping default Windows title bar
        pass
    
    def __init__(self) -> None:
        try:
            super().__init__()

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
                        font=("Segoe UI", 9, "normal"))
        style.map("Accent.TButton",
                  background=[("active", "#3a5a3a"), ("pressed", "#1a3a1a")],
                  foreground=[("active", "#ffffff"), ("pressed", "#ffffff")],
                  relief=[("pressed", "sunken")])

        # Default button style
        style.configure("TButton",
                        font=("Segoe UI", 9))


        # --- Force clam theme for Notebook to allow tab styling ---
        try:
            style.theme_use("clam")
        except Exception as e:
            print("Theme switch failed:", e)

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
                        padding=[8, 4],
                        relief="raised",
                        borderwidth=1)
        style.map("TNotebook.Tab",
                   background=[("selected", dark_bg)],
                   foreground=[("selected", dark_fg)])

        # Custom dark button style
        style.configure("Dark.TButton", background="#333333", foreground=btn_fg, font=("Segoe UI", 9, "bold"))
        style.map("Dark.TButton",
                   background=[("active", "#444444"), ("disabled", "#1a1a1a")],
                   foreground=[("disabled", "#666666")])

        style.configure("TCheckbutton", background=dark_bg, foreground=dark_fg)
        style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
        style.configure("TCombobox", fieldbackground=dark_bg, background=accent, foreground=dark_fg)
        style.map("TCombobox", fieldbackground=[("readonly", dark_bg)], foreground=[("readonly", dark_fg)])

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
                        font=("Segoe UI", 9))

        # Global Treeview styling (theme-aware)
        style.configure("Treeview",
                        background=dark_bg,
                        fieldbackground=dark_bg,
                        foreground=dark_fg,
                        borderwidth=0,
                        font=("Segoe UI", 9))
        style.map("Treeview",
                   background=[("selected", selection_bg)],
                   foreground=[("selected", selection_fg)])

        style.configure("Treeview.Heading",
                        background=accent,
                        foreground=dark_fg,
                        relief="raised",
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading",
                   background=[("active", "#333333"), ("pressed", dark_bg)],
                   foreground=[("active", dark_fg), ("pressed", dark_fg)])

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
            print(f"Window attributes setup failed: {e}")

        # Don't restore geometry here - will be done after widgets load
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Two-column layout: balanced dashboard + narrower presets sidebar
        self.columnconfigure(0, weight=2, minsize=300)   # Dashboard content (tabs) - balanced
        self.columnconfigure(1, weight=1, minsize=250)   # Ship Presets sidebar - narrower
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)      # Status bar

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
        app_dir = get_app_data_dir() if getattr(sys, 'frozen', False) else None
        self.cargo_monitor = CargoMonitor(update_callback=self._on_cargo_changed, 
                                        capacity_changed_callback=self._on_cargo_capacity_detected,
                                        ship_info_changed_callback=self._on_ship_info_changed,
                                        app_dir=app_dir)
        # Set the main app reference so cargo monitor can access prospector panel later
        self.cargo_monitor.main_app_ref = self
        
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
            print("Icon load failed:", e)


        # Model vars
        self.tool_fg: Dict[str, tk.StringVar] = {t: tk.StringVar(value="") for t in TOOL_ORDER}
        self.tool_btn: Dict[str, tk.IntVar] = {t: tk.IntVar(value=0) for t in TOOL_ORDER if VA_VARS[t]["btn"] is not None}
        self.toggle_vars: Dict[str, tk.IntVar] = {name: tk.IntVar(value=0) for name in TOGGLES}
        self.timer_vars: Dict[str, tk.IntVar] = {name: tk.IntVar(value=0) for name in TIMERS}
        
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
        
        # Auto-switch tabs on ring entry/exit
        self.auto_switch_tabs = tk.IntVar(value=1)  # Default enabled
        self._load_auto_switch_tabs_preference()
        self.auto_switch_tabs.trace('w', self._on_auto_switch_tabs_toggle)
        
        # Auto-start session on first prospector launch
        self.auto_start_session = tk.IntVar(value=1)  # Default enabled
        self._load_auto_start_preference()
        self.auto_start_session.trace('w', self._on_auto_start_toggle)
        
        # Prompt to end session when cargo full and idle
        self.prompt_on_cargo_full = tk.IntVar(value=1)  # Default enabled
        self._load_prompt_on_full_preference()
        self.prompt_on_cargo_full.trace('w', self._on_prompt_on_full_toggle)
        
        # Text overlay enable/disable, transparency, and color
        self.text_overlay_enabled = tk.IntVar(value=0)  # Default disabled
        self.text_overlay_transparency = tk.IntVar(value=90)  # Default 90% (0.9 alpha)
        self.text_overlay_color = tk.StringVar(value="White")  # Default white
        self.text_overlay_duration = tk.IntVar(value=7)  # Default 7 seconds (range: 5-30)
        self.overlay_mode = tk.StringVar(value="standard")  # "standard" or "enhanced" prospector overlay
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
            "Normal": 12,     # Normal text (was Small)
            "Large": 16       # Large text (was Normal)
        }
        
        # Initialize text overlay for TTS announcements (before loading preferences)
        self.text_overlay = TextOverlay()
        
        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Cargo monitor preferences
        self.cargo_enabled = tk.BooleanVar(value=False)
        self.cargo_display_mode = tk.StringVar(value="progress")
        self.cargo_position = tk.StringVar(value="Upper Right")
        self.cargo_max_capacity = tk.IntVar(value=200)
        self.cargo_transparency = tk.IntVar(value=90)
        self.cargo_show_in_overlay = tk.BooleanVar(value=False)

        self._load_cargo_preferences()
        
        self._load_text_overlay_preference()
        self.text_overlay_enabled.trace('w', self._on_text_overlay_toggle)
        self.text_overlay_transparency.trace('w', self._on_transparency_change)
        self.text_overlay_color.trace('w', self._on_color_change)
        self.text_overlay_size.trace('w', self._on_size_change)
        self.text_overlay_duration.trace('w', self._on_duration_change)
        self.overlay_mode.trace('w', self._on_overlay_mode_change)
        self.prospector_show_all.trace('w', self._on_show_all_change)
        
        # Cargo monitor traces
        self.cargo_enabled.trace('w', self._on_cargo_toggle)
        self.cargo_display_mode.trace('w', self._on_cargo_display_change)
        self.cargo_position.trace('w', self._on_cargo_position_change)
        self.cargo_max_capacity.trace('w', self._on_cargo_capacity_change)
        self.cargo_transparency.trace('w', self._on_cargo_transparency_change)

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
        
        # Initialize API uploader for session/hotspot sharing
        from api_uploader import APIUploader
        self.api_uploader = APIUploader()
        if self.api_uploader.enabled:
            print(f"[OK] API uploader enabled - endpoint: {self.api_uploader.api_url}")
            # Retry any queued uploads from previous sessions
            self.after(3000, lambda: self.api_uploader.retry_queued_uploads())
        else:
            print(f"API uploader disabled")
        
        # Initialize market handler for Market.json processing
        from market_handler import MarketHandler
        self.market_handler = MarketHandler(self.eddn_sender)
        
        # Initialize VoiceAttack variables manager
        from va_variables import VAVariablesManager
        self.va_variables = None  # Will be initialized after UI is built
        
        # Watch for Market.json changes to send to EDDN
        from file_watcher import get_file_watcher
        file_watcher = get_file_watcher()
        journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
        if journal_dir and os.path.exists(journal_dir):
            file_watcher.add_watch(journal_dir, self._on_journal_file_change)
            print(f"[OK] Watching journal directory for Market.json updates")

        # Build UI - ProspectorPanel will scan latest journal and populate current_system
        self._build_ui()
        
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
        self.after(1000, self._check_for_updates_startup)  # Check after 1 second
        
        # Early distance calculation using cached data (before journal scan)
        self.after(2000, self._update_home_fc_distances)
        
        # Full journal scan runs first (only call once!)
        # Ring finder auto-search will be triggered AFTER journal scan completes
        self.after(3000, self._background_journal_catchup)
        
        # Check for VA profile updates AFTER everything is loaded and settled
        self.after(5000, self._check_va_profile_update)

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
            
            try:
                reserve_levels = self.cargo_monitor.journal_parser._fetch_system_reserve_levels_from_spansh(current_sys)
                self.cargo_monitor.journal_parser.system_reserve_levels = reserve_levels
                if reserve_levels:
                    print(f"[STARTUP] Fetched {len(reserve_levels)} reserve levels")
                    
                    # Bulk update existing database entries with reserve levels
                    if hasattr(self.cargo_monitor, 'user_db'):
                        updated_count = self.cargo_monitor.user_db.bulk_update_reserve_levels(current_sys, reserve_levels)
                        if updated_count > 0:
                            print(f"[STARTUP] Updated {updated_count} database entries with reserve levels")
                    
                    if hasattr(self, 'ring_finder') and self.ring_finder:
                        self.ring_finder.status_var.set(f"Fetched {len(reserve_levels)} reserve levels for {current_sys}")
                else:
                    print(f"[STARTUP] No reserve levels found for {current_sys}")
                    if hasattr(self, 'ring_finder') and self.ring_finder:
                        self.ring_finder.status_var.set(f"No reserve levels found for {current_sys}")
            except Exception as e:
                print(f"[STARTUP] Error fetching reserve levels: {e}")
                if hasattr(self, 'ring_finder') and self.ring_finder:
                    self.ring_finder.status_var.set(f"Error fetching reserve levels")

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
        content_frame = ttk.Frame(self.main_paned, padding=(10, 6, 6, 0))
        self.main_paned.add(content_frame, weight=3)  # Add to paned window with higher weight
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=0)

        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")
        
        # Theme toggle button - will be placed in actions row below
        from config import load_theme
        _current_theme = load_theme()
        # Button shows what you'll switch TO (opposite of current)
        _theme_btn_text = t('sidebar.dark_theme') if _current_theme == "elite_orange" else t('sidebar.orange_theme')
        # Style button to match current theme
        if _current_theme == "elite_orange":
            _btn_bg, _btn_fg = "#1a1a1a", "#ff8c00"
            _btn_active_bg, _btn_active_fg = "#ff8c00", "#000000"
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
        
        # System Finder tab
        system_finder_tab = ttk.Frame(self.notebook, padding=8)
        self._build_system_finder_tab(system_finder_tab)
        self.notebook.add(system_finder_tab, text=t('tabs.system_finder'))
        
        # Add Distance Calculator tab now (built earlier but added here for correct order)
        self.notebook.add(distance_tab, text=t('tabs.distance_calculator'))

        # VoiceAttack Controls tab (combined Firegroups + Mining Controls)
        voiceattack_tab = ttk.Frame(self.notebook, padding=8)
        self._build_voiceattack_controls_tab(voiceattack_tab)
        self.notebook.add(voiceattack_tab, text=t('tabs.voiceattack_controls'))
        
        # Bookmarks tab - Mining location bookmarks
        bookmarks_tab = ttk.Frame(self.notebook, padding=8)
        self._build_bookmarks_tab(bookmarks_tab)
        self.notebook.add(bookmarks_tab, text=t('tabs.bookmarks'))
        
        # Auto-populate marketplace system after UI is built
        self.after(3000, self._populate_marketplace_system)

        # Settings tab (simplified with remaining sub-tabs)
        settings_tab = ttk.Frame(self.notebook, padding=8)
        self._build_settings_notebook(settings_tab)
        self.notebook.add(settings_tab, text=t('tabs.settings'))

        # About tab removed - now accessible via version button in sidebar

        # Actions row (global)
        actions = ttk.Frame(content_frame)
        actions.grid(row=1, column=0, sticky="w", pady=(8, 0))

        # Create the sidebar (Ship Presets + Cargo Monitor)
        self._create_main_sidebar()

        # Configure column weights for proper spacing
        actions.grid_columnconfigure(0, weight=0)  # Left side fixed
        actions.grid_columnconfigure(1, weight=1)  # Expandable space in middle
        actions.grid_columnconfigure(2, weight=0)  # Info frame fixed
        actions.grid_columnconfigure(3, weight=0)  # Theme button fixed
        
        # CMDR/System info container (right side) - uses frame for mixed colors
        # Use black background for orange theme
        from config import load_theme
        _info_theme = load_theme()
        _info_bg = "#000000" if _info_theme == "elite_orange" else "#1e1e1e"
        
        info_frame = tk.Frame(actions, bg=_info_bg)
        info_frame.grid(row=0, column=2, sticky="e", padx=(10, 5))
        
        # EliteMining logo (resized to fit status bar)
        try:
            from PIL import Image, ImageTk
            from path_utils import get_images_dir
            logo_path = os.path.join(get_images_dir(), "EliteMining_txt_logo_transp_resize.png")
            if os.path.exists(logo_path):
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
        self.cmdr_label_prefix = tk.Label(info_frame, text=t('status_bar.cmdr'), fg="white", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.cmdr_label_value = tk.Label(info_frame, text="", fg="#ffcc00", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.system_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.system_label_value = tk.Label(info_frame, text="", fg="#ffcc00", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.visits_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.visits_label_value = tk.Label(info_frame, text="", fg="#ffcc00", bg=_info_bg, font=("Segoe UI", 9, "bold"), cursor="hand2")
        self.route_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.route_label_value = tk.Label(info_frame, text="", fg="#ffcc00", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.total_systems_label_prefix = tk.Label(info_frame, text="", fg="white", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        self.total_systems_label_value = tk.Label(info_frame, text="", fg="#ffcc00", bg=_info_bg, font=("Segoe UI", 9, "bold"))
        
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
        self.total_systems_label_prefix.grid(row=0, column=9, sticky="e")
        self.total_systems_label_value.grid(row=0, column=10, sticky="w")
        
        # Help indicator for Tot Syst (updates on game restart)
        self.total_systems_help = tk.Label(info_frame, text="(?)", fg="gray", bg=_info_bg, font=("Segoe UI", 9))
        self.total_systems_help.grid(row=0, column=11, sticky="w")
        ToolTip(self.total_systems_help, t('status_bar.total_systems_tooltip'))
        
        # Load CMDR name in background
        self.after(500, self._update_cmdr_system_display)

        # Status bar - span both columns
        self.status = tk.StringVar(value=f"{APP_TITLE} {APP_VERSION} | Installation: {self.va_root}")
        sb = ttk.Label(self, textvariable=self.status, relief=tk.SUNKEN, anchor="w")
        sb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(2, 6))

        # Import existing values
        self.after(100, self._import_all_from_txt)
        # Set up tracing AFTER loading from .txt files
        self.after(200, self._setup_announcement_tracing)

        # Ensure focus is on a neutral button to prevent initial Entry highlights
        try:
            self.after(300, lambda: self.import_btn.focus_set())
        except Exception:
            pass

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
        
        # Create a LabelFrame to provide visual border around cargo monitor
        cargo_frame = ttk.LabelFrame(parent_frame, text="🚛 " + t('sidebar.cargo_monitor'), padding=6)
        cargo_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=(2, 0))  # sticky="nsew" - expand in all directions
        cargo_frame.columnconfigure(0, weight=1)
        cargo_frame.rowconfigure(1, weight=1)  # Content row expands
        
        # Simple header without buttons
        header_frame = ttk.Frame(cargo_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header_frame.columnconfigure(1, weight=1)
        
        # Title and summary in one line
        title_label = ttk.Label(header_frame, text=t('sidebar.cargo_status'), font=("Segoe UI", 10, "bold"))
        title_label.grid(row=0, column=0, sticky="w")
        
        self.integrated_cargo_summary = ttk.Label(header_frame, text="0/200t (0%) - Empty", 
                                                 font=("Segoe UI", 10))
        self.integrated_cargo_summary.grid(row=0, column=1, sticky="w", padx=(6, 0))
        
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
            font=("Consolas", 9, "normal"),  # Monospace font for proper alignment
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",  # Enable word wrap for better text flow
            height=6,  # Minimum height - will expand with pane
            width=45   # Width for complete cargo info
        )
        self.integrated_cargo_text.grid(row=0, column=0, sticky="nsew")
        
        # Thin scrollbar
        integrated_scrollbar = ttk.Scrollbar(content_frame, orient="vertical", 
                                           command=self.integrated_cargo_text.yview)
        integrated_scrollbar.grid(row=0, column=1, sticky="ns")
        self.integrated_cargo_text.configure(yscrollcommand=integrated_scrollbar.set)
        content_frame.columnconfigure(1, weight=0)
        
        # Compact status at bottom - single line (hidden but functional)
        self.integrated_status_label = ttk.Label(
            cargo_frame,
            text="",  # Hidden text but label remains functional
            font=("Segoe UI", 7)  # Even smaller font
        )
        self.integrated_status_label.grid(row=2, column=0, sticky="w")
        
        # Set up periodic update for integrated display
        self._update_integrated_cargo_display()
        self.after(1000, self._periodic_integrated_cargo_update)
        
    def _update_integrated_cargo_display(self):
        """
        Update the INTEGRATED cargo display with data from cargo monitor.
        
        ✅ PRIMARY DISPLAY METHOD - This is what users see in the main app window!
        ⚠️ When modifying display logic, also update update_display() for popup window!
        
        Location: Bottom pane of main EliteMining window
        Widgets: self.integrated_cargo_text, self.integrated_cargo_summary
        """
        if not hasattr(self, 'integrated_cargo_summary'):
            return
            
        # Update summary
        cargo = self.cargo_monitor
        percentage = (cargo.current_cargo / cargo.max_cargo * 100) if cargo.max_cargo > 0 else 0
        
        status_color = ""
        if percentage > 95:
            status_color = " 🔴"
        elif percentage > 85:
            status_color = " 🟡"
        elif percentage > 50:
            status_color = " 🟢"
            
        summary_text = f"{cargo.current_cargo}/{cargo.max_cargo}t ({percentage:.0f}%){status_color}"
        self.integrated_cargo_summary.configure(text=summary_text)
        
        # Save current scroll position before updating
        try:
            scroll_position = self.integrated_cargo_text.yview()
        except:
            scroll_position = None
        
        # Update cargo list - very compact format
        self.integrated_cargo_text.configure(state="normal")
        self.integrated_cargo_text.delete(1.0, tk.END)
        
        if not cargo.cargo_items:
            if cargo.current_cargo > 0:
                self.integrated_cargo_text.insert(tk.END, f"📊 {cargo.current_cargo}t {t('sidebar.total')}\n💡 {t('sidebar.no_item_details')}")
            else:
                self.integrated_cargo_text.insert(tk.END, f"📦 {t('sidebar.empty_cargo')}\n⛏️ {t('sidebar.start_mining')}")
        else:
            # Vertical list with better alignment - show ALL items
            sorted_items = sorted(cargo.cargo_items.items(), key=lambda x: x[1], reverse=True)
            
            # Configure clickable limpet tag (theme-aware color + hand cursor)
            self.integrated_cargo_text.tag_configure("limpet_clickable", 
                                                     foreground=self.theme_colors.get("fg", "#e0e0e0"))
            self.integrated_cargo_text.tag_bind("limpet_clickable", "<Button-1>", 
                                                lambda e: self.cargo_monitor.adjust_limpet_count())
            self.integrated_cargo_text.tag_bind("limpet_clickable", "<Enter>", 
                                                lambda e: self.integrated_cargo_text.configure(cursor="hand2"))
            self.integrated_cargo_text.tag_bind("limpet_clickable", "<Leave>", 
                                                lambda e: self.integrated_cargo_text.configure(cursor=""))
            
            # Show all items
            for i, (item_name, quantity) in enumerate(sorted_items):
                # Clean up item name for display - use full name, not truncated
                display_name = item_name.replace('_', ' ').replace('$', '').title()
                
                # Abbreviate only "Low Temperature Diamonds" to prevent truncation
                if display_name in ['Low Temp. Diamonds', 'Low Temperature Diamonds']:
                    display_name = 'LTD'
                
                # Localize limpet to Drohne for German
                is_limpet = "limpet" in item_name.lower()
                if is_limpet:
                    display_name = t('sidebar.limpet')
                
                # Simple icons with better spacing
                if is_limpet:
                    icon = "🤖"
                elif any(m in item_name.lower() for m in ['painite', 'diamond', 'opal']):
                    icon = "💎"
                elif any(m in item_name.lower() for m in ['gold', 'silver', 'platinum', 'osmium', 'praseodymi']):
                    icon = "🥇"
                else:
                    icon = "📦"
                
                # Use precise character positioning with monospace font
                # Format: Icon(2) + Space(1) + Name(12) + Quantity(right-aligned)
                name_field = f"{display_name:<12}"[:12]  # Exactly 12 characters, truncated if needed
                quantity_text = f"{quantity}t"
                
                line = f"{icon} {name_field} {quantity_text:>5}"
                
                # Mark start position for limpet lines (to make clickable)
                if is_limpet:
                    start_pos = self.integrated_cargo_text.index(tk.END)
                    self.integrated_cargo_text.insert(tk.END, line, "limpet_clickable")
                else:
                    self.integrated_cargo_text.insert(tk.END, line)
                
                # Add newline for all but the last item
                if i < len(sorted_items) - 1:
                    self.integrated_cargo_text.insert(tk.END, "\n")
        
        # Display Engineering Materials section
        if cargo.materials_collected:
            # Fixed separator width to match cargo line: icon(2) + space(1) + name(12) + space(1) + qty(5) = 21 + extra padding
            sep_chars = 24
            self.integrated_cargo_text.insert(tk.END, "\n" + "─" * sep_chars)
            self.integrated_cargo_text.insert(tk.END, "\n" + t('mining_session.engineering_materials') + " 🔩\n")
            
            # Sort materials alphabetically
            sorted_materials = sorted(cargo.materials_collected.items(), key=lambda x: x[0])
            
            for i, (material_name, quantity) in enumerate(sorted_materials):
                # Get grade for this material
                grade = cargo.MATERIAL_GRADES.get(material_name, 0)
                
                # Use localized name for display if available, otherwise use English name
                display_name = cargo.materials_localized_names.get(material_name, material_name)[:12]
                grade_text = f"(G{grade})"
                line = f"{display_name:<12} {grade_text} {quantity:>3}"
                self.integrated_cargo_text.insert(tk.END, line)
                
                # Add newline for all but the last item
                if i < len(sorted_materials) - 1:
                    self.integrated_cargo_text.insert(tk.END, "\n")
        
        
        # Add refinery note at the very bottom with proper spacing
        # Fixed separator width to match cargo/engineering materials line
        sep_chars = 24
        self.integrated_cargo_text.insert(tk.END, "\n" + "─" * sep_chars)
        
        # Configure tag for small italic text - left aligned
        self.integrated_cargo_text.tag_configure("small_italic", font=("Segoe UI", 8, "italic"), foreground="#888888", justify="left")
        
        # Insert refinery note with formatting - get position before inserting
        note_start_index = self.integrated_cargo_text.index(tk.INSERT)
        self.integrated_cargo_text.insert(tk.END, "\n" + t('sidebar.refinery_note'))
        
        # Add limpet help text if limpets are present
        has_limpets = any("limpet" in name.lower() for name in cargo.cargo_items.keys())
        if has_limpets:
            self.integrated_cargo_text.insert(tk.END, "\n" + t('sidebar.limpet_click_help'))
        
        note_end_index = self.integrated_cargo_text.index(tk.INSERT)
        
        # Apply formatting to the note text only
        try:
            self.integrated_cargo_text.tag_add("small_italic", note_start_index, note_end_index)
        except tk.TclError:
            # If tagging fails, just continue without formatting
            pass
        
        self.integrated_cargo_text.configure(state="disabled")
        
        # Restore scroll position to prevent jumping
        if scroll_position:
            try:
                self.integrated_cargo_text.yview_moveto(scroll_position[0])
            except:
                pass
        
        # Update status - more compact
        try:
            if hasattr(cargo, 'status_label') and cargo.status_label:
                status_text = cargo.status_label.cget('text')
                # Shorten status text
                if "Monitoring:" in status_text:
                    status_text = "📊 " + status_text.split(":")[-1].strip()
                elif "detected" in status_text:
                    status_text = status_text.replace("Cargo loaded:", "✅").replace(" items,", "i,")
                self.integrated_status_label.configure(text=status_text[:50] + "..." if len(status_text) > 50 else status_text)
        except:
            pass
    
    def _periodic_integrated_cargo_update(self):
        """Periodically update the integrated cargo display"""
        try:
            self._update_integrated_cargo_display()
        except Exception as e:
            pass  # Silently handle any update errors
        
        # Schedule next update
        self.after(2000, self._periodic_integrated_cargo_update)  # Every 2 seconds
    
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
                
            else:
                log.warning(f"Unknown VA command: {command}")
                
        except Exception as e:
            log.error(f"Error executing VA command '{command}': {e}")
    
    def _va_switch_tab(self, tab_name: str):
        """Switch to specified tab"""
        tab_mapping = {
            'MINING': 'mining_session',
            'HOTSPOTS': 'hotspots_finder',
            'MARKET': 'commodity_market',
            'SYSTEMS': 'system_finder',
            'DISTANCE': 'distance_calculator',
            'VOICEATTACK': 'voiceattack',
            'BOOKMARKS': 'bookmarks',
            'SETTINGS': 'settings',
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
            print(f"[DEBUG] Error in _on_cargo_changed: {e}")
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
            print(f"Warning: Ring Finder refresh failed: {e}")

    def reset_cargo_hold(self):
        """
        Reset cargo hold to actual game state by calling cargo monitor reset.
        
        This method provides UI feedback and delegates to the CargoMonitor's reset functionality.
        Works for both popup window and integrated cargo displays.
        """
        if hasattr(self, 'cargo_monitor') and self.cargo_monitor is not None:
            success = self.cargo_monitor.reset_cargo_hold()
            if success:
                item_count = len(self.cargo_monitor.cargo_items)
                total_weight = self.cargo_monitor.current_cargo
                from app_utils import centered_message
                centered_message(self, "Reset Complete", 
                                 f"Cargo hold reset to actual game state.\n\n"
                                 f"Found: {item_count} item types\n"
                                 f"Total: {total_weight} tons")
            else:
                messagebox.showwarning("Reset Issue", 
                    "Cargo hold was cleared but no game data was found.\n"
                    "Make sure Elite Dangerous is running and you have opened your cargo hold in-game.")
        else:
            messagebox.showwarning("No Cargo Monitor", "Cargo monitor is not available.")

    def _validate_cargo_monitor(self):
        """Validate that cargo monitor is properly initialized - for debugging"""
        if not hasattr(self, 'cargo_monitor'):
            print("ERROR: App instance missing cargo_monitor attribute")
            return False
        if self.cargo_monitor is None:
            print("ERROR: cargo_monitor is None")
            return False
        if not hasattr(self.cargo_monitor, 'reset_cargo_hold'):
            print("ERROR: cargo_monitor missing reset_cargo_hold method")
            return False
        return True

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

    # ---------- Firegroups tab ----------
    def _build_fg_tab(self, frame: ttk.Frame) -> None:
        # Columns sized for aligned labels & radios
        frame.grid_columnconfigure(0, weight=0, minsize=230)
        frame.grid_columnconfigure(1, weight=0, minsize=120)
        frame.grid_columnconfigure(2, weight=0, minsize=150)
        frame.grid_columnconfigure(3, weight=1,  minsize=150)

        # Tool name translation mapping
        tool_translations = {
            "Mining lasers/MVR:": "voiceattack.tool_mining_lasers",
            "Discovery scanner:": "voiceattack.tool_discovery_scanner",
            "Prospector limpet:": "voiceattack.tool_prospector",
            "Pulse wave analyser:": "voiceattack.tool_pulse_wave",
            "Seismic charge launcher:": "voiceattack.tool_seismic",
            "Weapons:": "voiceattack.tool_weapons",
            "Sub-surface displacement missile:": "voiceattack.tool_ssm",
        }

        header = ttk.Label(frame, text=t('voiceattack.assign_firegroups'),
                           font=("Segoe UI", 11, "bold"))
        header.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        ttk.Label(frame, text=t('voiceattack.firegroup')).grid(row=1, column=1, sticky="w", padx=(0, 6))
        ttk.Label(frame, text=t('voiceattack.primary_fire')).grid(row=1, column=2, sticky="w")
        ttk.Label(frame, text=t('voiceattack.secondary_fire')).grid(row=1, column=3, sticky="w")

        row = 2
        for tool in TOOL_ORDER:
            cfg = VA_VARS[tool]
            # Get localized tool name
            display_tool = t(tool_translations.get(tool, tool)) if tool in tool_translations else tool
            ttk.Label(frame, text=display_tool).grid(row=row, column=0, sticky="w", pady=3)

            if cfg["fg"] is not None:
                cb = ttk.Combobox(frame, values=FIREGROUPS, width=6, textvariable=self.tool_fg[tool], state="readonly")
                cb.grid(row=row, column=1, sticky="w")
            else:
                ttk.Label(frame, text="—").grid(row=row, column=1, sticky="w")

            if cfg["btn"] is not None:
                tk.Radiobutton(frame, text=t('voiceattack.primary'), value=1, variable=self.tool_btn[tool], bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), padx=4, pady=2, anchor="w").grid(row=row, column=2, sticky="w")
                tk.Radiobutton(frame, text=t('voiceattack.secondary'), value=2, variable=self.tool_btn[tool], bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), padx=4, pady=2, anchor="w").grid(row=row, column=3, sticky="w")
            else:
                ttk.Label(frame, text="—").grid(row=row, column=2, sticky="w")
                ttk.Label(frame, text="—").grid(row=row, column=3, sticky="w")
            row += 1

        # Tip card with bullets - use theme colors
        theme_bg = self.theme_colors["bg"]
        theme_fg = self.theme_colors["fg"]
        card = tk.Frame(frame, bg=theme_bg, borderwidth=0, relief="flat", highlightthickness=0, highlightbackground=theme_bg)
        card.grid(row=row, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        card.columnconfigure(0, weight=1)

        # Important notice (always yellow for visibility)
        important_label = tk.Label(
            card, 
            text=t('voiceattack.important_firegroups'),
            font=("Segoe UI", 9, "bold"), 
            anchor="w", 
            bg=theme_bg, 
            fg="#ffcc00",
            wraplength=600,
            justify="left"
        )
        important_label.grid(row=0, column=0, sticky="w", padx=8, pady=(60, 8))

        tip_header = tk.Label(card, text=t('voiceattack.tips_help'), font=("Segoe UI", 9, "bold"), anchor="w", bg=theme_bg, fg=theme_fg, borderwidth=0, relief="flat", highlightthickness=0)
        tip_header.grid(row=1, column=0, sticky="w", padx=8, pady=(10, 2))

        tips = [
            t('voiceattack.tip_core_mining'),
            t('voiceattack.tip_collector'),
            t('voiceattack.tip_clear_jump'),
            t('voiceattack.tip_stop_all'),
        ]
        r = 2
        for tip in tips:
            lbl = tk.Label(
                card,
                text=f"• {tip}",
                wraplength=600,
                justify="left",
                fg=theme_fg,
                bg=theme_bg,
                font=("Segoe UI", 9),
            )
            lbl.grid(row=r, column=0, sticky="w", padx=16, pady=1)
            r += 1

        def _on_cfg_resize(evt):
            wrap = max(320, min(evt.width - 60, 1000))
            for child in card.winfo_children():
                if isinstance(child, tk.Label) and child is not tip_header:
                    child.config(wraplength=wrap)
        frame.bind("<Configure>", _on_cfg_resize)

    # ---------- Interface Options tab ----------
    def _build_settings_notebook(self, frame: ttk.Frame) -> None:
        """Build the Settings tab with sub-tabs for different setting categories"""
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
                tk.Label(title_frame, text="EliteMining", font=("Segoe UI", 18, "bold"), 
                         fg="#ffcc00", bg=_about_bg).pack()
        except Exception:
            # Fallback to text on error
            tk.Label(title_frame, text="EliteMining", font=("Segoe UI", 18, "bold"), 
                     fg="#ffcc00", bg=_about_bg).pack()
        
        tk.Label(title_frame, text=f"Version {__version__}", font=("Segoe UI", 10), 
                 fg="#888888", bg=_about_bg).pack()
        
        # Description
        tk.Label(center_frame, text=t('about.description'), 
                 font=("Segoe UI", 11), fg="#e0e0e0", bg=_about_bg).pack(pady=(10, 20))
        
        # Separator
        tk.Frame(center_frame, height=1, bg="#444444", width=400).pack(pady=10)
        
        # Copyright and license
        tk.Label(center_frame, text=t('about.copyright'), 
                 font=("Segoe UI", 10), fg="#e0e0e0", bg=_about_bg).pack()
        tk.Label(center_frame, text=t('about.license'), 
                 font=("Segoe UI", 9), fg="#888888", bg=_about_bg).pack()
        
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
                           padx=12, pady=4, font=("Segoe UI", 9), cursor="hand2",
                           width=12, highlightbackground=_btn_border, highlightthickness=1)
            btn.pack(side="left", padx=5)
        
        # Separator
        tk.Frame(center_frame, height=1, bg="#444444", width=400).pack(pady=15)
        
        # Credits section
        credits_frame = tk.Frame(center_frame, bg=_about_bg)
        credits_frame.pack(pady=10)
        
        tk.Label(credits_frame, text="Credits", font=("Segoe UI", 10, "bold"), 
                 fg="#ffcc00", bg=_about_bg).pack()
        
        credits = [
            "EliteVA by Somfic",
            "Ardent API by Iain Collins",
            "EDData API by gOOvER | CMDR Shyvin",
            "EDCD/EDDN Community",
        ]
        
        for credit in credits:
            tk.Label(credits_frame, text=f"- {credit}", font=("Segoe UI", 9), 
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
            font=("Segoe UI", 9, "italic"),
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
            print(f"About tab PayPal widget failed: {e}")

    def _build_voiceattack_controls_tab(self, frame: ttk.Frame) -> None:
        """Build the VoiceAttack Controls tab with Mining Controls and Firegroups"""
        # Create a notebook for VoiceAttack sub-tabs
        self.voiceattack_notebook = ttk.Notebook(frame)
        self.voiceattack_notebook.pack(fill="both", expand=True)

        # === MINING CONTROLS SUB-TAB ===
        mining_controls_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_timers_tab(mining_controls_tab)
        self.voiceattack_notebook.add(mining_controls_tab, text=t('voiceattack.mining_controls'))

        # === FIREGROUPS & FIRE BUTTONS SUB-TAB ===
        firegroups_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_fg_tab(firegroups_tab)
        self.voiceattack_notebook.add(firegroups_tab, text=t('voiceattack.firegroups'))

    def _build_bookmarks_tab(self, frame: ttk.Frame) -> None:
        """Build the Bookmarks tab - Mining location bookmarks"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        # Use the prospector panel's bookmarks functionality
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel._create_bookmarks_panel(frame)

    def _build_announcements_tab(self, frame: ttk.Frame) -> None:
        """Build the Announcements settings tab with full material functionality"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Basic announcement controls
        ttk.Label(frame, text=t('settings.announcement_settings'), font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        
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
                    ttk.Label(toggles_frame, text=t('settings.announcement_types'), font=("Segoe UI", 9, "bold")).pack(anchor="w")
                    
                    # Localized display names and help texts for announcement toggles
                    toggle_display = {
                        "Core Asteroids": (t('settings.core_asteroids'), t('settings.core_asteroids_help')),
                        "Non-Core Asteroids": (t('settings.non_core_asteroids'), t('settings.non_core_asteroids_help'))
                    }
                    
                    for name, (_fname, helptext) in ANNOUNCEMENT_TOGGLES.items():
                        # Check if the variable exists before trying to use it
                        if name in self.announcement_vars:
                            # Get localized display name and help text
                            display_name, localized_help = toggle_display.get(name, (name, helptext))
                            checkbox = tk.Checkbutton(toggles_frame, text=display_name, 
                                                    variable=self.announcement_vars[name], 
                                                    bg=_ann_cb_bg, fg="#ffffff", selectcolor=_ann_cb_select, 
                                                    activebackground=_ann_cb_bg, activeforeground="#ffffff", 
                                                    highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                                                    padx=4, pady=1, anchor="w")
                            checkbox.pack(anchor="w", padx=(10, 0))
                            ToolTip(checkbox, localized_help)
                
                # Right side: Threshold controls
                thr = ttk.Frame(main_controls)
                thr.pack(side="left")
                ttk.Label(thr, text=t('settings.announce_at')).pack(side="left")
                sp = ttk.Spinbox(thr, from_=0.0, to=100.0, increment=0.5, width=6,
                                 textvariable=self.prospector_panel.threshold, 
                                 command=self.prospector_panel._save_threshold_value)
                sp.pack(side="left", padx=(6, 4))
                ToolTip(sp, t('tooltips.announcement_threshold'))
                
                set_all_btn = tk.Button(thr, text=t('settings.set_all'), command=self._ann_set_all_threshold,
                                       bg="#2a4a5a", fg="#ffffff", 
                                       activebackground="#3a5a6a", activeforeground="#ffffff",
                                       relief="solid", bd=1, cursor="hand2", pady=2, padx=8)
                set_all_btn.pack(side="left", padx=(10, 0))
                ToolTip(set_all_btn, t('tooltips.set_all_threshold'))
                ttk.Label(thr, text="%").pack(side="left")

                # Materials section label
                ttk.Label(frame, text=t('settings.select_minerals'),
                          font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(0, 2))

                # Create the full material tree with functionality
                materials_frame = ttk.Frame(frame)
                materials_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
                materials_frame.columnconfigure(0, weight=1)
                materials_frame.rowconfigure(0, weight=1)
                frame.rowconfigure(3, weight=1)

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
                               font=("Segoe UI", 9))
                style.configure("Announcements.Treeview.Heading",
                               foreground=ann_fg,
                               font=("Segoe UI", 9, "bold"))

                # Material tree
                self.ann_mat_tree = ttk.Treeview(materials_frame, columns=("announce", "material", "minpct"), show="headings", height=18, style="Announcements.Treeview")
                self.ann_mat_tree.heading("announce", text=t('settings.announce'))
                self.ann_mat_tree.heading("material", text=t('settings.mineral'))
                self.ann_mat_tree.heading("minpct", text=t('settings.minimal_pct'))
                self.ann_mat_tree.column("announce", width=90, anchor="center", stretch=False)
                self.ann_mat_tree.column("material", width=300, anchor="center", stretch=True)
                self.ann_mat_tree.column("minpct", width=100, anchor="center", stretch=False)
                self.ann_mat_tree.grid(row=0, column=0, sticky="nsew")
                
                ann_scrollbar = ttk.Scrollbar(materials_frame, orient="vertical", command=self.ann_mat_tree.yview)
                ann_scrollbar.grid(row=0, column=1, sticky="ns")
                self.ann_mat_tree.configure(yscrollcommand=ann_scrollbar.set)

                # Configure alternating row colors
                self.ann_mat_tree.tag_configure('oddrow', background='#1e1e1e')
                self.ann_mat_tree.tag_configure('evenrow', background='#252525')

                # Create spinboxes for per-material thresholds
                self._ann_minpct_spin = {}
                self._ann_minpct_vars = {}

                def _on_ann_minpct_change_factory(material):
                    def _on_change():
                        try:
                            v = float(self._ann_minpct_vars[material].get())
                            v = max(0.0, min(100.0, v))
                            self.prospector_panel.min_pct_map[material] = v
                            self.prospector_panel._save_min_pct_map()
                        except ValueError:
                            pass
                    return _on_change

                # Populate with materials and create spinboxes
                row_idx = 0
                for mat in KNOWN_MATERIALS:
                    flag = "✓" if self.prospector_panel.announce_map.get(mat, True) else "—"
                    row_tag = 'evenrow' if row_idx % 2 == 0 else 'oddrow'
                    # Get localized material name for display
                    from localization import get_material
                    display_mat = get_material(mat)
                    if mat in CORE_ONLY:
                        self.ann_mat_tree.insert("", "end", iid=mat, values=(flag, display_mat, ""), tags=(row_tag,))
                    else:
                        self.ann_mat_tree.insert("", "end", iid=mat, values=(flag, display_mat, ""), tags=(row_tag,))
                        
                        # Create spinbox for non-core materials
                        v = self.prospector_panel.min_pct_map.get(mat, 0.0)
                        self._ann_minpct_vars[mat] = tk.DoubleVar(value=v)
                        
                        self._ann_minpct_spin[mat] = ttk.Spinbox(
                            self.ann_mat_tree,
                            from_=0.0,
                            to=100.0,
                            increment=0.5,
                            width=4,
                            textvariable=self._ann_minpct_vars[mat],
                            command=_on_ann_minpct_change_factory(mat)
                        )
                    row_idx += 1

                # Add double-click handler to toggle announcement
                def _ann_toggle_announce(event):
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
                                flag = "✓" if new_state else "—"
                                current = self.ann_mat_tree.item(item, "values")
                                self.ann_mat_tree.item(item, values=(flag, current[1], current[2]))
                                print(f"Toggled {item}: {current_state} → {new_state}")
                            except Exception as e:
                                print(f"Error toggling {item}: {e}")

                self.ann_mat_tree.bind("<Double-1>", _ann_toggle_announce)

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
                                # Position the spinbox with fixed width instead of cell width
                                spinbox_width = 60  # Fixed width for spinbox
                                # Center the spinbox in the cell
                                x_offset = (width - spinbox_width) // 2
                                spinbox.place(in_=self.ann_mat_tree, x=x + x_offset, y=y, width=spinbox_width, height=height)
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

                # Buttons frame
                btns = ttk.Frame(frame)
                btns.grid(row=4, column=0, sticky="w", pady=(8, 0))
                
                select_all_btn = tk.Button(btns, text=t('settings.select_all'), command=self._ann_select_all,
                                          bg="#2a5a2a", fg="#ffffff", 
                                          activebackground="#3a6a3a", activeforeground="#ffffff",
                                          relief="solid", bd=1, cursor="hand2", pady=3)
                select_all_btn.pack(side="left")
                ToolTip(select_all_btn, t('tooltips.select_all_materials'))
                
                unselect_all_btn = tk.Button(btns, text=t('settings.unselect_all'), command=self._ann_unselect_all,
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
                for i in range(1, 7):  # Preset 1 to 6
                    # Get custom name or use default
                    custom_name = preset_names.get(str(i), f"Preset {i}")
                    
                    preset_btn = tk.Button(btns, text=custom_name,
                                         bg="#4a4a2a", fg="#ffffff",
                                         activebackground="#5a5a3a", activeforeground="#ffffff",
                                         relief="solid", bd=1,
                                         width=13, font=("Segoe UI", 9), cursor="hand2", pady=3,
                                         highlightbackground="#2a2a1a", highlightcolor="#2a2a1a")
                    preset_btn.pack(side="left", padx=(8, 0))
                    
                    # Store button reference
                    self.preset_buttons[i] = preset_btn
                    
                    # Bind left and right click events
                    if i == 1:
                        preset_btn.bind("<Button-1>", lambda e: self._ann_load_preset1())
                        preset_btn.bind("<Button-3>", lambda e: self._ann_save_preset1())
                    else:
                        preset_btn.bind("<Button-1>", lambda e, num=i: self._ann_load_preset(num))
                        preset_btn.bind("<Button-3>", lambda e, num=i: self._ann_save_preset(num))
                    
                    # Ctrl+Click (left or right) or Middle-click to rename preset
                    preset_btn.bind("<Button-2>", lambda e, num=i: self._rename_preset(num))
                    preset_btn.bind("<Control-Button-1>", lambda e, num=i: self._rename_preset(num))
                    preset_btn.bind("<Control-Button-3>", lambda e, num=i: self._rename_preset(num))
                    
                    # Fix button state after right-click
                    preset_btn.bind("<ButtonRelease-3>", lambda e: e.widget.config(relief="raised"))
                    
                    # Add tooltip
                    ToolTip(preset_btn, f"Left-click: Load | Right-click: Save | Ctrl+Click: Rename")
                
            except ImportError:
                # Fallback if imports fail
                ttk.Label(frame, text="Announcement settings require the Mining Session to be initialized.\nPlease restart the application if this persists.", 
                         font=("Segoe UI", 10), foreground="orange").grid(row=1, column=0, sticky="w", padx=20, pady=20)
        else:
            # Simple message if prospector panel not available
            ttk.Label(frame, text="Announcement settings will be available after the Mining Session initializes.\nPlease restart the application if this persists.", 
                     font=("Segoe UI", 10), foreground="orange").grid(row=1, column=0, sticky="w", padx=20, pady=20)

    def _ann_select_all(self):
        """Enable announcements for all materials"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS
                for mat in KNOWN_MATERIALS:
                    self.prospector_panel.announce_map[mat] = True
                self.prospector_panel._save_announce_map()
                self._ann_update_display()
            except Exception as e:
                print(f"Error in _ann_select_all: {e}")
    
    def _ann_unselect_all(self):
        """Disable announcements for all materials"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS
                for mat in KNOWN_MATERIALS:
                    self.prospector_panel.announce_map[mat] = False
                self.prospector_panel._save_announce_map()
                self._ann_update_display()
            except Exception as e:
                print(f"Error in _ann_unselect_all: {e}")
    
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
            except Exception as e:
                print(f"Error in _ann_set_all_threshold: {e}")
            
    def _ann_update_display(self):
        """Update the announcements display"""
        if hasattr(self, 'ann_mat_tree') and hasattr(self, 'prospector_panel'):
            try:
                from prospector_panel import KNOWN_MATERIALS
                for mat in KNOWN_MATERIALS:
                    flag = "✓" if self.prospector_panel.announce_map.get(mat, True) else "—"
                    current = self.ann_mat_tree.item(mat, "values")
                    if current:
                        self.ann_mat_tree.item(mat, values=(flag, current[1], current[2]))
            except Exception as e:
                print(f"Error in _ann_update_display: {e}")

    def _ann_save_preset1(self):
        """Save current announcement settings as preset 1"""
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
                
                cfg['announce_preset_1'] = preset_data
                self.prospector_panel._save_cfg(cfg)
                self._set_status("Saved Preset 1.")
            except Exception as e:
                print(f"Error saving preset 1: {e}")

    def _ann_load_preset1(self):
        """Load announcement settings from preset 1"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                cfg = self.prospector_panel._load_cfg()
                data = cfg.get('announce_preset_1')
                if not data:
                    from app_utils import centered_message
                    centered_message(self, "Load Preset 1", "No Preset 1 saved yet.")
                    return
                
                self.prospector_panel.announce_map = data.get('announce_map', {}).copy()
                self.prospector_panel.min_pct_map = data.get('min_pct_map', {}).copy()
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
                self._ann_update_display()
                self._set_status("Loaded Preset 1.")
            except Exception as e:
                print(f"Error loading preset 1: {e}")

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
                self._set_status(f"Saved Preset {num}.")
            except Exception as e:
                print(f"Error saving preset {num}: {e}")

    def _ann_load_preset(self, num):
        """Load announcement settings from preset num"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            try:
                from prospector_panel import KNOWN_MATERIALS, CORE_ONLY
                cfg = self.prospector_panel._load_cfg()
                data = cfg.get(f'announce_preset_{num}')
                if not data:
                    from app_utils import centered_message
                    centered_message(self, f"Load Preset {num}", f"No Preset {num} saved yet.")
                    return
                
                # Merge preset data with current materials to preserve new materials
                preset_announce = data.get('announce_map', {})
                preset_minpct = data.get('min_pct_map', {})
                
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
                self._ann_update_display()
                self._set_status(f"Loaded Preset {num}.")
            except Exception as e:
                print(f"Error loading preset {num}: {e}")

    def _rename_preset(self, num):
        """Rename a preset with a custom name"""
        try:
            from config import load_theme
            from app_utils import get_app_icon_path
            
            cfg = self.prospector_panel._load_cfg() if hasattr(self, 'prospector_panel') else {}
            preset_names = cfg.get('preset_names', {})
            current_name = preset_names.get(str(num), f"Preset {num}")
            
            # Theme colors
            theme = load_theme()
            bg = "#000000" if theme == "elite_orange" else "#1e1e1e"
            fg = "#ff8c00" if theme == "elite_orange" else "#e0e0e0"
            btn_bg = "#2a2a2a" if theme == "elite_orange" else "#3a3a3a"
            btn_fg = "#ff9900" if theme == "elite_orange" else "#ffffff"
            
            # Create dialog
            dialog = tk.Toplevel(self)
            dialog.title(t('settings.rename_preset').format(num=num))
            dialog.configure(bg=bg)
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.grab_set()
            
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
                    font=("Segoe UI", 10)).pack(pady=(0, 10))
            
            # Entry field
            name_var = tk.StringVar(value=current_name)
            entry = tk.Entry(frame, textvariable=name_var, 
                           width=25, font=("Segoe UI", 10),
                           bg="#2a2a2a", fg="#ffffff",
                           insertbackground="#ffffff")
            entry.pack(pady=5)
            entry.select_range(0, tk.END)
            
            def save_name():
                new_name = name_var.get().strip()
                if new_name:
                    # Save to config
                    if 'preset_names' not in cfg:
                        cfg['preset_names'] = {}
                    cfg['preset_names'][str(num)] = new_name
                    self.prospector_panel._save_cfg(cfg)
                    
                    # Update button text
                    if hasattr(self, 'preset_buttons') and num in self.preset_buttons:
                        self.preset_buttons[num].config(text=new_name)
                    
                    self._set_status(t('settings.preset_renamed').format(num=num, name=new_name))
                dialog.destroy()
            
            # Buttons
            btn_frame = tk.Frame(dialog, bg=bg)
            btn_frame.pack(pady=10)
            
            tk.Button(btn_frame, text=t('common.save'), command=save_name,
                     bg=btn_bg, fg=btn_fg, width=8,
                     activebackground="#4a4a4a", activeforeground=btn_fg,
                     font=("Segoe UI", 9), relief="flat").pack(side="left", padx=5)
            tk.Button(btn_frame, text=t('common.cancel'), command=dialog.destroy,
                     bg=btn_bg, fg=btn_fg, width=8,
                     activebackground="#4a4a4a", activeforeground=btn_fg,
                     font=("Segoe UI", 9), relief="flat").pack(side="left", padx=5)
            
            # Enter key to save
            entry.bind("<Return>", lambda e: save_name())
            
            # CRITICAL: Center on parent window
            dialog.update_idletasks()
            self._center_dialog_on_parent(dialog)
            
            entry.focus_set()
            
        except Exception as e:
            print(f"Error renaming preset {num}: {e}")

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

        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        # Now build content in scrollable_frame instead of frame
        scrollable_frame.columnconfigure(0, weight=1)
        ttk.Label(scrollable_frame, text=t('settings.interface_options'), font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        r = 1
        
        # ========== GENERAL INTERFACE SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.general_interface'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator1 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator1.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Tooltips option
        tk.Checkbutton(scrollable_frame, text=t('settings.enable_tooltips'), variable=self.tooltips_enabled, 
                      bg=_gs_bg, fg="#ffffff", selectcolor=_gs_bg, activebackground=_gs_bg, 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground=_gs_bg, 
                      highlightcolor=_gs_bg, takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.tooltips_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Stay on top option
        tk.Checkbutton(scrollable_frame, text=t('settings.stay_on_top'), variable=self.stay_on_top, 
                      bg=_gs_bg, fg="#ffffff", selectcolor=_gs_bg, activebackground=_gs_bg, 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground=_gs_bg, 
                      highlightcolor=_gs_bg, takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.stay_on_top_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Theme toggle option
        theme_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        theme_frame.grid(row=r, column=0, sticky="w")
        
        tk.Label(theme_frame, text=t('settings.theme') + ":", bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left", padx=(4, 10))
        
        current_theme_text = "Elite Orange" if self.current_theme == "elite_orange" else "Dark Gray"
        self.theme_label = tk.Label(theme_frame, text=current_theme_text, bg=_gs_bg, fg="#ffcc00", font=("Segoe UI", 9, "bold"))
        self.theme_label.pack(side="left", padx=(0, 15))
        
        # Button shows what you'll switch TO (opposite of current)
        _settings_theme_btn_text = t('settings.dark_theme') if _gs_theme == "elite_orange" else t('settings.orange_theme')
        # Style to match current theme
        if _gs_theme == "elite_orange":
            _sbtn_bg, _sbtn_fg = "#1a1a1a", "#ff8c00"
            _sbtn_active_bg, _sbtn_active_fg = "#ff8c00", "#000000"
        else:
            _sbtn_bg, _sbtn_fg = "#333333", "#ffffff"
            _sbtn_active_bg, _sbtn_active_fg = "#444444", "#ffffff"
        theme_toggle_settings = tk.Button(
            theme_frame,
            text=_settings_theme_btn_text,
            command=self._toggle_theme,
            bg=_sbtn_bg,
            fg=_sbtn_fg,
            activebackground=_sbtn_active_bg,
            activeforeground=_sbtn_active_fg,
            relief="flat",
            bd=1,
            padx=8,
            pady=2,
            font=("Segoe UI", 9),
            cursor="hand2"
        )
        theme_toggle_settings.pack(side="left")
        r += 1
        
        tk.Label(scrollable_frame, text="Switch between Elite Orange and Dark Gray themes (requires restart)", wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Language selector option
        lang_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        lang_frame.grid(row=r, column=0, sticky="w")
        
        tk.Label(lang_frame, text=t('settings.language') + ":", bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left", padx=(4, 10))
        
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
        
        self.lang_display_label = tk.Label(lang_frame, text=current_lang_display, bg=_gs_bg, fg="#ffcc00", font=("Segoe UI", 9, "bold"))
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
            
            # Update display label
            self.lang_display_label.config(text=selected_name)
            
            # Save to config
            try:
                cfg = load_config_func()
                cfg['language'] = selected_code
                save_config_func(cfg)
            except Exception as e:
                print(f"Error saving language setting: {e}")
            
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
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== EDDN SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.eddn'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator
        separator_eddn = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_eddn.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # EDDN send enable/disable
        tk.Checkbutton(scrollable_frame, text="✓ " + t('settings.send_eddn'), variable=self.eddn_send_enabled, 
                      command=self._on_eddn_send_toggle,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.send_eddn_desc'), 
                 wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== TEXT OVERLAY DISPLAY SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.text_overlay'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator2 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator2.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Text overlay enable/disable
        tk.Checkbutton(scrollable_frame, text=t('settings.enable_text_overlay'), variable=self.text_overlay_enabled, 
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.text_overlay_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 8))
        r += 1
        
        # Text brightness slider
        transparency_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        transparency_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(transparency_frame, text=t('settings.text_brightness'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        _slider_trough = "#1a1a1a" if _gs_theme == "elite_orange" else "#444444"
        _slider_active = "#ff6600" if _gs_theme == "elite_orange" else "#444444"
        _slider_fg = "#ff8c00" if _gs_theme == "elite_orange" else "#ffffff"
        self.transparency_scale = tk.Scale(transparency_frame, from_=10, to=100, orient="horizontal", 
                                         variable=self.text_overlay_transparency, bg=_gs_bg, fg=_slider_fg, 
                                         activebackground=_slider_active, highlightthickness=0, length=120,
                                         troughcolor=_slider_trough, font=("Segoe UI", 8),
                                         sliderrelief="flat", sliderlength=20)
        self.transparency_scale.pack(side="left", padx=(8, 0))
        tk.Label(transparency_frame, text="%", bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.text_brightness_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Text color selection with actual colors shown
        color_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        color_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(color_frame, text=t('settings.text_color'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
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
        
        # Create display variable with localized name
        current_color_display = color_display_names.get(self.text_overlay_color.get(), t('settings.color_white'))
        self._color_display_var = tk.StringVar(value=current_color_display)
        
        # Create custom OptionMenu with colored options
        self.color_menu = tk.OptionMenu(color_frame, self._color_display_var, *color_display_names.values())
        self.color_menu.configure(
            bg=_gs_bg, 
            fg="#ffffff", 
            activebackground="#444444",
            activeforeground="#ffffff",
            highlightthickness=0,
            relief="raised",
            bd=1,
            font=("Segoe UI", 8)
        )
        self.color_menu.pack(side="left", padx=(8, 0))
        
        # Style the dropdown menu items with their actual colors
        menu = self.color_menu['menu']
        menu.configure(bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"], 
                      activebackground=MENU_COLORS["activebackground"])
        
        # Clear existing items and add colored ones with localized labels
        menu.delete(0, 'end')
        for internal_name, color_hex in self.color_options.items():
            display_name = color_display_names.get(internal_name, internal_name)
            # For very light colors, use black text for readability
            text_color = "#000000" if internal_name in ["White", "Yellow", "Light Gray", "Light Green", "Light Blue", "Cyan"] else "#000000"
            
            def set_color(disp=display_name, internal=internal_name):
                self._color_display_var.set(disp)
                self.text_overlay_color.set(internal)
            
            menu.add_command(
                label=display_name,
                command=set_color,
                background=color_hex,
                foreground=text_color,
                activebackground=color_hex,
                activeforeground=text_color,
                font=("Segoe UI", 9, "bold")
            )
        r += 1
        tk.Label(scrollable_frame, text=t('settings.text_color_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Text size selection with localized options
        size_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        size_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(size_frame, text=t('settings.text_size'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Localized size options
        size_display_names = [t('settings.text_size_small'), t('settings.text_size_normal'), t('settings.text_size_large')]
        self._size_display_to_internal = {
            t('settings.text_size_small'): "Small",
            t('settings.text_size_normal'): "Normal",
            t('settings.text_size_large'): "Large"
        }
        self._size_internal_to_display = {v: k for k, v in self._size_display_to_internal.items()}
        
        # Convert current value to display name
        current_size_display = self._size_internal_to_display.get(self.text_overlay_size.get(), t('settings.text_size_normal'))
        self._size_display_var = tk.StringVar(value=current_size_display)
        
        self.size_combo = ttk.Combobox(size_frame, textvariable=self._size_display_var, 
                                      values=size_display_names, 
                                      state="readonly", width=12, font=("Segoe UI", 8))
        self.size_combo.pack(side="left", padx=(8, 0))
        
        # Sync display var to internal var
        def _on_size_change(event=None):
            display_val = self._size_display_var.get()
            internal_val = self._size_display_to_internal.get(display_val, "Normal")
            self.text_overlay_size.set(internal_val)
        self.size_combo.bind('<<ComboboxSelected>>', _on_size_change)
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.text_size_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Display duration slider
        duration_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        duration_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(duration_frame, text=t('settings.display_duration'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        self.duration_scale = tk.Scale(duration_frame, from_=5, to=30, orient="horizontal", 
                                     variable=self.text_overlay_duration, bg=_gs_bg, fg=_slider_fg, 
                                     activebackground=_slider_active, highlightthickness=0, length=140,
                                     troughcolor=_slider_trough, font=("Segoe UI", 8),
                                     sliderrelief="flat", sliderlength=20)
        self.duration_scale.pack(side="left", padx=(8, 0))
        tk.Label(duration_frame, text=t('settings.seconds'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.duration_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Overlay mode selection (Standard vs Enhanced Prospector)
        mode_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        mode_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(mode_frame, text=t('settings.overlay_mode'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Radio buttons for mode selection
        tk.Radiobutton(mode_frame, text=t('settings.overlay_standard'), value="standard", variable=self.overlay_mode,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9),
                      padx=4, pady=2, anchor="w").pack(side="left", padx=(8, 0))
        tk.Radiobutton(mode_frame, text=t('settings.overlay_enhanced'), value="enhanced", variable=self.overlay_mode,
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9),
                      padx=4, pady=2, anchor="w").pack(side="left", padx=(8, 0))
        r += 1
        tk.Label(scrollable_frame, text=t('settings.overlay_mode_desc'),
                 wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Show all materials checkbox (for enhanced mode) - HIDDEN but functionality preserved
        # tk.Checkbutton(scrollable_frame, text="Enhanced Mode: Show All Materials (uncheck to only show materials above threshold)",
        #               variable=self.prospector_show_all,
        #               bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
        #               activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9),
        #               padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e",
        #               highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        # r += 1
        # tk.Label(scrollable_frame, text="Only affects Enhanced mode - controls whether to display all materials or filter by threshold",
        #          wraplength=760, justify="left", fg="gray", bg=_gs_bg,
        #          font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        # r += 1
        
        # ========== TEXT-TO-SPEECH AUDIO SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.tts_settings'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator3 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator3.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # TTS Voice selection (moved from announcements panel)
        tk.Label(scrollable_frame, text=t('settings.tts_voice'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w", pady=(4, 4))
        r += 1
        
        voice_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        voice_frame.grid(row=r, column=0, sticky="w", pady=(0, 4))
        
        # Get voice list from announcer
        try:
            voice_values = announcer.list_voices()
        except Exception as e:
            print(f"Error getting voice list: {e}")
            voice_values = []
        
        # Initialize voice choice variable if not exists
        if not hasattr(self, 'voice_choice'):
            self.voice_choice = tk.StringVar(value="")
            
        self.voice_combo = ttk.Combobox(voice_frame, textvariable=self.voice_choice, 
                                       state="readonly", width=35, font=("Segoe UI", 8),
                                       values=voice_values)
        self.voice_combo.pack(side="left")
        
        # Test voice button
        def _test_voice_interface():
            try:
                announcer.say("This is a test of the selected voice.")
            except Exception as e:
                print(f"Error testing voice: {e}")
        
        test_btn = tk.Button(voice_frame, text=t('settings.test_voice'), command=_test_voice_interface,
                            bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                            activeforeground="#ffffff", relief="ridge", bd=1, 
                            font=("Segoe UI", 8, "normal"), cursor="hand2")
        test_btn.pack(side="left", padx=(8, 0))
        
        r += 1
        # Volume control
        vol_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        vol_frame.grid(row=r, column=0, sticky="w", pady=(6, 4))
        
        tk.Label(vol_frame, text=t('settings.tts_volume'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Initialize voice volume variable if not exists
        if not hasattr(self, 'voice_volume'):
            try:
                self.voice_volume = tk.IntVar(value=announcer.get_volume())
            except:
                self.voice_volume = tk.IntVar(value=80)
        
        def _on_volume_change(v):
            try:
                announcer.set_volume(int(float(v)))
                # Save to config
                from config import update_config_value
                update_config_value("tts_volume", int(float(v)))
            except Exception as e:
                print(f"Error changing TTS volume: {e}")
        
        vol_slider = tk.Scale(vol_frame, from_=0, to=100, orient="horizontal", 
                             variable=self.voice_volume, bg=_gs_bg, fg=_slider_fg,
                             activebackground=_slider_active, highlightthickness=0, 
                             troughcolor=_slider_trough, font=("Segoe UI", 8),
                             command=_on_volume_change, length=200,
                             sliderrelief="flat", sliderlength=20)
        vol_slider.pack(side="left", padx=(8, 0))
        
        # TTS Fix button
        def _fix_tts_interface():
            try:
                # Run diagnosis
                announcer.diagnose_tts()
                # Try to reinitialize
                success = announcer.reinitialize_tts()
                if success:
                    announcer.say("TTS engine reinitialized successfully")
                    print("[INTERFACE] TTS engine reinitialized successfully")
                    # Refresh voice list
                    self._refresh_voice_list()
                else:
                    print("[INTERFACE] Failed to reinitialize TTS engine")
            except Exception as e:
                print(f"[INTERFACE] Error reinitializing TTS: {e}")
        
        fix_tts_btn = tk.Button(vol_frame, text="Reset Speech Recognition", command=_fix_tts_interface,
                               bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                               activeforeground="#ffffff", relief="ridge", bd=1, 
                               font=("Segoe UI", 8, "normal"), cursor="hand2")
        fix_tts_btn.pack(side="left", padx=(8, 0), pady=(15, 0))
        ToolTip(fix_tts_btn, t('tooltips.fix_tts'))
        r += 1
        
        # Load saved voice preference
        try:
            cfg = _load_cfg()
            saved_voice = cfg.get("tts_voice")
            if saved_voice and saved_voice in voice_values:
                self.voice_choice.set(saved_voice)
                # Apply the saved voice to announcer immediately
                try:
                    announcer.set_voice(saved_voice)
                except Exception as e:
                    print(f"Error setting saved voice: {e}")
            elif voice_values:
                self.voice_choice.set(voice_values[0])
                
            # Load saved volume
            saved_volume = cfg.get("tts_volume", 80)
            self.voice_volume.set(saved_volume)
        except:
            if voice_values:
                self.voice_choice.set(voice_values[0])
        
        def _on_voice_change_interface(event=None):
            try:
                sel = self.voice_choice.get()
                announcer.set_voice(sel)
                # Save to config
                from config import update_config_value
                update_config_value("tts_voice", sel)
            except Exception as e:
                print(f"Error changing TTS voice: {e}")
        
        self.voice_combo.bind("<<ComboboxSelected>>", _on_voice_change_interface)
        
        # Refresh voice list after a short delay to ensure announcer is fully initialized
        self.after(100, self._refresh_voice_list)
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.tts_config_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== JOURNAL FILES SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.journal_files'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator4 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator4.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Journal folder path setting
        journal_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        journal_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(journal_frame, text=t('settings.journal_location'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Initialize journal label (will be updated after prospector panel creation)
        self.journal_lbl = tk.Label(journal_frame, text="(not set)", fg="gray", bg=_gs_bg, font=("Segoe UI", 9))
        self.journal_lbl.pack(side="left", padx=(6, 0))
        
        journal_btn = tk.Button(journal_frame, text=t('settings.change'), command=self._change_journal_dir,
                               bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                               activeforeground="#ffffff", relief="ridge", bd=1, 
                               font=("Segoe UI", 8, "normal"), cursor="hand2")
        journal_btn.pack(side="left", padx=(8, 0))
        ToolTip(journal_btn, t('tooltips.journal_folder'))
        
        import_btn = tk.Button(journal_frame, text=t('settings.import_history'), command=self._import_journal_history,
                              bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                              activeforeground="#ffffff", relief="ridge", bd=1,
                              font=("Segoe UI", 8, "normal"), cursor="hand2")
        import_btn.pack(side="left", padx=(8, 0))
        ToolTip(import_btn, t('tooltips.import_history'))
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.journal_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Import prompt preference checkbox
        self.ask_import_on_path_change = tk.IntVar()
        import_prompt_check = tk.Checkbutton(
            scrollable_frame,
            text=t('settings.ask_import_prompt'),
            variable=self.ask_import_on_path_change,
            command=self._save_import_prompt_preference,
            bg=_gs_bg,
            fg="#ffffff",
            selectcolor="#34495e",
            activebackground="#1e1e1e",
            activeforeground="#ffffff",
            font=("Segoe UI", 9)
        )
        import_prompt_check.grid(row=r, column=0, sticky="w", pady=(0, 4))
        
        # Load preference
        cfg = _load_cfg()
        self.ask_import_on_path_change.set(1 if cfg.get("ask_import_on_path_change", True) else 0)
        r += 1
        
        # Auto-scan journals on startup checkbox
        tk.Checkbutton(scrollable_frame, text=t('settings.auto_scan_journals'), variable=self.auto_scan_journals, 
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text=t('settings.auto_scan_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Auto-switch tabs on ring entry/exit checkbox
        tk.Checkbutton(scrollable_frame, text="Auto-switch Tabs on Ring Entry/Exit", variable=self.auto_switch_tabs, 
                      bg=_gs_bg, fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Automatically switch to Mining Session tab when dropping into a ring, and to Hotspots Finder when entering supercruise or jumping to another system", wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== SCREENSHOTS FOLDER SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.screenshots_folder_title'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator line
        separator_screenshots = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_screenshots.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Screenshots folder path setting
        screenshots_folder_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        screenshots_folder_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(screenshots_folder_frame, text=t('settings.screenshots_folder_label'), bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Create StringVar for screenshots folder path
        self.screenshots_folder_path = tk.StringVar()
        self.screenshots_folder_path.set(_load_cfg().get('screenshots_folder', os.path.join(os.path.expanduser("~"), "Pictures")))
        
        # Initialize screenshots folder label (will be updated with actual path)
        self.screenshots_folder_lbl = tk.Label(screenshots_folder_frame, text=self.screenshots_folder_path.get(), fg="gray", bg=_gs_bg, font=("Segoe UI", 9))
        self.screenshots_folder_lbl.pack(side="left", padx=(6, 0))
        
        screenshots_btn = tk.Button(screenshots_folder_frame, text=t('settings.change'), command=self._change_screenshots_folder,
                                  bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                  activeforeground="#ffffff", relief="ridge", bd=1, 
                                  font=("Segoe UI", 8, "normal"), cursor="hand2")
        screenshots_btn.pack(side="left", padx=(8, 0))
        ToolTip(screenshots_btn, t('tooltips.screenshots_folder'))
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.screenshots_folder_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== EDSM API KEY SECTION - DISABLED ==========
        # ttk.Label(scrollable_frame, text="EDSM API Key", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        # r += 1
        # 
        # # Add separator line
        # separator_edsm = tk.Frame(scrollable_frame, height=1, bg="#444444")
        # separator_edsm.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        # r += 1
        # 
        # # EDSM signup instructions
        # instructions_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        # instructions_frame.grid(row=r, column=0, sticky="w", pady=(4, 4))
        # 
        # tk.Label(instructions_frame, text="1. Sign up at EDSM:", bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(anchor="w")
        # 
        # # EDSM link
        # import webbrowser
        # edsm_link = tk.Label(instructions_frame, text="https://www.edsm.net/", bg=_gs_bg, fg="#4da6ff", font=("Segoe UI", 9, "underline"), cursor="hand2")
        # edsm_link.pack(anchor="w", padx=(15, 0))
        # edsm_link.bind("<Button-1>", lambda e: webbrowser.open("https://www.edsm.net/"))
        # 
        # tk.Label(instructions_frame, text="2. Log in → Account settings → API key", bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        # tk.Label(instructions_frame, text="3. Paste the key here:", bg=_gs_bg, fg="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        # 
        # r += 1
        # 
        # # EDSM API key input
        # api_key_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        # api_key_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        # 
        # # Initialize EDSM API key variable
        # if not hasattr(self, 'edsm_api_key'):
        #     self.edsm_api_key = tk.StringVar()
        #     self.edsm_api_key.set(_load_cfg().get('edsm_api_key', ''))
        # 
        # api_key_entry = tk.Entry(api_key_frame, textvariable=self.edsm_api_key, bg="#2d2d2d", fg="#ffffff", 
        #                         font=("Consolas", 9), width=45, show="*")
        # api_key_entry.grid(row=0, column=0, padx=(0, 8))
        # 
        # # Save button
        # def _save_api_key():
        #     key = self.edsm_api_key.get().strip()
        #     from config import update_config_value
        #     update_config_value("edsm_api_key", key)
        #     messagebox.showinfo("Saved", "EDSM API key saved successfully!")
        # 
        # save_btn = tk.Button(api_key_frame, text="Save", command=_save_api_key,
        #                     bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
        #                     activeforeground="#ffffff", relief="ridge", bd=1, 
        #                     font=("Segoe UI", 8, "normal"), cursor="hand2")
        # save_btn.grid(row=0, column=1)
        # 
        # r += 1
        # tk.Label(scrollable_frame, text="Required for Ring Finder to search nearby systems for comprehensive results.", 
        #          wraplength=760, justify="left", fg="gray", bg=_gs_bg,
        #          font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        # r += 1

        # ========== API UPLOAD SECTION ==========
        r += 1
        ttk.Label(scrollable_frame, text=t('settings.api_upload_title'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator line
        separator_api = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_api.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # COMING SOON notice
        coming_soon_frame = tk.Frame(scrollable_frame, bg="#3a3a00", relief="solid", bd=1)
        coming_soon_frame.grid(row=r, column=0, sticky="ew", pady=(0, 10))
        tk.Label(coming_soon_frame, text="🚧 " + t('settings.api_coming_soon'), 
                bg="#3a3a00", fg="#ffff00", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 4))
        tk.Label(coming_soon_frame, text=t('settings.api_coming_soon_desc1'), 
                bg="#3a3a00", fg="#ffffff", font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        tk.Label(coming_soon_frame, text=t('settings.api_coming_soon_desc2'), 
                bg="#3a3a00", fg="#ffffff", font=("Segoe UI", 8)).pack(anchor="w", padx=10)
        tk.Label(coming_soon_frame, text=t('settings.api_coming_soon_desc3'), 
                bg="#3a3a00", fg="#ffffff", font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 8))
        r += 1
        
        # API Upload enable/disable with consent message (DISABLED FOR NOW)
        api_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        api_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        
        # Initialize API variables
        if not hasattr(self, 'api_upload_enabled'):
            from config import load_api_upload_settings
            api_settings = load_api_upload_settings()
            # Force disabled for this release
            self.api_upload_enabled = tk.IntVar(value=0)
            self.api_endpoint_url = tk.StringVar(value=api_settings["endpoint_url"])
            self.api_key = tk.StringVar(value=api_settings["api_key"])
            self.api_cmdr_name = tk.StringVar(value=api_settings["cmdr_name"])
        
        api_check = tk.Checkbutton(api_frame, text=t('settings.api_enable_upload'), 
                                   variable=self.api_upload_enabled,
                                   command=self._on_api_upload_toggle,
                                   bg=_gs_bg, fg="#888888", selectcolor="#1e1e1e", 
                                   activebackground="#1e1e1e", activeforeground="#888888", 
                                   highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                                   padx=4, pady=2, anchor="w", state="disabled")
        api_check.pack(anchor="w")
        r += 1
        
        # Consent message
        consent_frame = tk.Frame(scrollable_frame, bg="#2a2a2a", relief="solid", bd=1)
        consent_frame.grid(row=r, column=0, sticky="ew", pady=(4, 8), padx=(20, 0))
        tk.Label(consent_frame, text="ℹ️ " + t('settings.api_consent_title'), 
                bg="#2a2a2a", fg="#ffcc00", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8, pady=(6, 2))
        tk.Label(consent_frame, text="  • " + t('settings.api_consent_sessions'), 
                bg="#2a2a2a", fg="#cccccc", font=("Segoe UI", 8)).pack(anchor="w", padx=8)
        tk.Label(consent_frame, text="  • " + t('settings.api_consent_hotspots'), 
                bg="#2a2a2a", fg="#cccccc", font=("Segoe UI", 8)).pack(anchor="w", padx=8)
        tk.Label(consent_frame, text="  • " + t('settings.api_consent_materials'), 
                bg="#2a2a2a", fg="#cccccc", font=("Segoe UI", 8)).pack(anchor="w", padx=8, pady=(0, 6))
        r += 1
        
        # CMDR Name (DISABLED)
        cmdr_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        cmdr_frame.grid(row=r, column=0, sticky="w", pady=(4, 4))
        tk.Label(cmdr_frame, text=t('settings.api_cmdr_name'), bg=_gs_bg, fg="#888888", font=("Segoe UI", 9)).pack(side="left")
        cmdr_entry = tk.Entry(cmdr_frame, textvariable=self.api_cmdr_name, 
                             bg="#2d2d2d", fg="#888888", font=("Segoe UI", 9), width=30, state="disabled")
        cmdr_entry.pack(side="left", padx=(8, 0))
        r += 1
        
        # API Endpoint URL (DISABLED)
        endpoint_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        endpoint_frame.grid(row=r, column=0, sticky="w", pady=(4, 4))
        tk.Label(endpoint_frame, text=t('settings.api_endpoint'), bg=_gs_bg, fg="#888888", font=("Segoe UI", 9)).pack(side="left")
        endpoint_entry = tk.Entry(endpoint_frame, textvariable=self.api_endpoint_url, 
                                 bg="#2d2d2d", fg="#888888", font=("Segoe UI", 9), width=50, state="disabled")
        endpoint_entry.pack(side="left", padx=(8, 0))
        r += 1
        
        # API Key (DISABLED)
        apikey_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        apikey_frame.grid(row=r, column=0, sticky="w", pady=(4, 8))
        tk.Label(apikey_frame, text=t('settings.api_key'), bg=_gs_bg, fg="#888888", font=("Segoe UI", 9)).pack(side="left")
        apikey_entry = tk.Entry(apikey_frame, textvariable=self.api_key, 
                               bg="#2d2d2d", fg="#888888", font=("Segoe UI", 9), width=50, show="*", state="disabled")
        apikey_entry.pack(side="left", padx=(8, 0))
        
        # Show/hide API key button (DISABLED)
        def _toggle_api_key_visibility():
            return  # Disabled
        
        show_btn = tk.Button(apikey_frame, text="👁️", command=_toggle_api_key_visibility,
                            bg="#2a2a2a", fg="#888888", activebackground="#3a3a3a",
                            activeforeground="#888888", relief="ridge", bd=1, 
                            font=("Segoe UI", 8), cursor="hand2", width=3, state="disabled")
        show_btn.pack(side="left", padx=(4, 0))
        r += 1
        
        # Buttons frame
        api_buttons_frame = tk.Frame(scrollable_frame, bg=_gs_bg)
        api_buttons_frame.grid(row=r, column=0, sticky="w", pady=(4, 4))
        
        # Test Connection button (DISABLED)
        test_btn = tk.Button(api_buttons_frame, text=t('settings.api_test_connection'), command=self._test_api_connection,
                            bg="#2a2a2a", fg="#888888", activebackground="#3a3a3a",
                            activeforeground="#888888", relief="ridge", bd=1, padx=10, pady=3,
                            font=("Segoe UI", 8, "normal"), cursor="hand2", state="disabled")
        test_btn.pack(side="left", padx=(0, 8))
        ToolTip(test_btn, t('tooltips.test_upload'))
        
        # Save Settings button (DISABLED)
        save_api_btn = tk.Button(api_buttons_frame, text=t('settings.api_save_settings'), command=self._save_api_settings,
                                bg="#2a2a2a", fg="#888888", activebackground="#3a3a3a",
                                activeforeground="#888888", relief="ridge", bd=1, padx=10, pady=3,
                                font=("Segoe UI", 8, "normal"), cursor="hand2", state="disabled")
        save_api_btn.pack(side="left", padx=(0, 8))
        
        # Bulk Upload button (DISABLED)
        bulk_upload_btn = tk.Button(api_buttons_frame, text=t('settings.api_bulk_upload'), command=self._bulk_upload_api_data,
                                    bg="#2a2a2a", fg="#888888", activebackground="#3a3a3a",
                                    activeforeground="#888888", relief="ridge", bd=1, padx=10, pady=3,
                                    font=("Segoe UI", 8, "normal"), cursor="hand2", state="disabled")
        bulk_upload_btn.pack(side="left")
        ToolTip(bulk_upload_btn, t('tooltips.bulk_upload'))
        r += 1
        
        # Status label
        self.api_status_label = tk.Label(scrollable_frame, text="", 
                                         bg=_gs_bg, fg="gray", font=("Segoe UI", 8))
        self.api_status_label.grid(row=r, column=0, sticky="w", pady=(4, 4))
        self._update_api_status()
        r += 1
        
        tk.Label(scrollable_frame, text=t('settings.api_desc'), 
                wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== BACKUP & RESTORE SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.backup_restore_title'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
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
                              font=("Segoe UI", 9, "normal"), cursor="hand2")
        backup_btn.pack(side="left", padx=(0, 8))
        _backup_tooltip = t('tooltips.backup')
        print(f"[DEBUG TOOLTIP] tooltips.backup = {repr(_backup_tooltip)}")
        ToolTip(backup_btn, _backup_tooltip)
        
        restore_btn = tk.Button(backup_frame, text="📂 " + t('settings.restore_button'), command=self._show_restore_dialog,
                               bg="#4a3a2a", fg="#e0e0e0", 
                               activebackground="#5a4a3a", activeforeground="#ffffff",
                               relief="ridge", bd=1, padx=12, pady=4,
                               font=("Segoe UI", 9, "normal"), cursor="hand2")
        restore_btn.pack(side="left")
        ToolTip(restore_btn, t('tooltips.restore'))
        
        r += 1
        tk.Label(scrollable_frame, text=t('settings.backup_restore_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== UPDATES SECTION ==========
        ttk.Label(scrollable_frame, text=t('settings.updates_title'), font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
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
                              font=("Segoe UI", 9, "normal"), cursor="hand2")
        update_btn.grid(row=r, column=0, sticky="w", pady=(4, 0))
        r += 1
        tk.Label(scrollable_frame, text=t('settings.updates_desc'), wraplength=760, justify="left", fg="gray", bg=_gs_bg,
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1



    def _create_main_sidebar(self) -> None:
        """Create the main Ship Presets and Cargo Monitor sidebar"""
        # Create the sidebar frame - add to main paned window
        # Reduced bottom padding (6,6,10,0) so cargo monitor aligns with app bottom
        sidebar = ttk.Frame(self.main_paned, padding=(6, 6, 10, 0))
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
                min_content_width = 600
                min_sidebar_width = 200  # Reduced from 280 - allow narrower sidebar
                
                # Try to restore saved position first
                from config import load_main_sash_position
                saved_pos = load_main_sash_position()
                
                # Validate saved position ensures both areas have minimum width
                if (saved_pos is not None and 
                    saved_pos >= min_content_width and 
                    saved_pos <= total_width - min_sidebar_width):
                    self.main_paned.sashpos(0, saved_pos)
                else:
                    # Default: sidebar ~300px wide
                    sash_pos = total_width - 300
                    # Ensure minimums
                    sash_pos = max(sash_pos, min_content_width)
                    sash_pos = min(sash_pos, total_width - min_sidebar_width)
                    self.main_paned.sashpos(0, sash_pos)
                
                # Mark sash as initialized - now saving is allowed
                self._sash_initialized = True
                
                # Now set up the sidebar sash after main sash is done
                self.after(100, _set_sidebar_sash)
                    
            except Exception as e:
                print(f"Error setting main sash: {e}")
        
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
                
                # Minimum heights for each pane
                min_presets_height = 150
                min_cargo_height = 120
                
                # Try to restore saved sash position first
                from config import load_sidebar_sash_position
                saved_pos = load_sidebar_sash_position()
                
                # Validate saved position ensures both panes have minimum height
                if (saved_pos is not None and 
                    saved_pos >= min_presets_height and 
                    saved_pos <= total_height - min_cargo_height):
                    paned_window.sashpos(0, saved_pos)
                else:
                    # Default: give 60% to presets, 40% to cargo monitor
                    sash_pos = int(total_height * 0.6)
                    # Ensure minimum heights
                    sash_pos = max(sash_pos, min_presets_height)
                    sash_pos = min(sash_pos, total_height - min_cargo_height)
                    paned_window.sashpos(0, sash_pos)
                
                self._sidebar_sash_initialized = True
            except Exception as e:
                print(f"Error setting sidebar sash: {e}")
        
        # Delay to ensure window geometry is fully applied
        self.after(500, _set_initial_sash)
        
        # Save main sash position when it changes (only after initialization)
        def _on_main_sash_moved(event):
            if not getattr(self, '_sash_initialized', False):
                return  # Don't save during initial layout
            try:
                from config import save_main_sash_position
                pos = self.main_paned.sashpos(0)
                if pos > 200:  # Only save valid positions
                    save_main_sash_position(pos)
            except Exception:
                pass
        self.main_paned.bind("<ButtonRelease-1>", _on_main_sash_moved)

        # Create vertical paned window for split layout
        paned_window = ttk.PanedWindow(sidebar, orient="vertical")
        paned_window.grid(row=0, column=0, sticky="nsew")
        self.sidebar_paned = paned_window  # Store reference for sash positioning
        
        # Top pane - Presets section
        presets_pane = ttk.Frame(paned_window)
        paned_window.add(presets_pane, weight=5)
        presets_pane.columnconfigure(0, weight=1)
        presets_pane.rowconfigure(2, weight=1)  # Row 2 (preset list) expands
        presets_pane.rowconfigure(3, weight=0)  # Row 3 (buttons) stays at bottom

        # Ship Presets title
        presets_title = ttk.Label(presets_pane, text="⚙️ " + t('sidebar.ship_presets'), font=("Segoe UI", 10, "bold"))
        presets_title.grid(row=0, column=0, sticky="w", pady=(0, 2))
        
        # Set minimum height for presets pane to prevent collapse
        presets_pane.configure(height=200)
        presets_pane.grid_propagate(True)
        
        # Help text for preset operations
        help_text = ttk.Label(presets_pane, text=t('sidebar.right_click_options'), 
                             font=("Segoe UI", 8), foreground="#666666")
        help_text.grid(row=1, column=0, sticky="w", pady=(0, 6))
        
        # Configure treeview style for selection highlight (theme-aware)
        style = ttk.Style()
        
        # Configure Ship Presets treeview font and row height
        if self.current_theme == "elite_orange":
            style.configure("ShipPresets.Treeview",
                           font=("Segoe UI", 10),
                           background="#1e1e1e",
                           foreground="#ff8c00",
                           fieldbackground="#1e1e1e",
                           rowheight=22)
            style.map("ShipPresets.Treeview",
                     background=[("selected", "#ff8c00")],
                     foreground=[("selected", "#000000")])
        else:
            style.configure("ShipPresets.Treeview",
                           font=("Segoe UI", 10),
                           background="#1e1e1e",
                           foreground="#e0e0e0",
                           fieldbackground="#1e1e1e",
                           rowheight=22)
            style.map("ShipPresets.Treeview",
                     background=[("selected", "#404040")],
                     foreground=[("selected", "#ffffff")])
        
        # Scrollable preset list - hierarchical treeview with ship groups
        self.preset_list = ttk.Treeview(presets_pane, columns=("name",), show="tree", selectmode="browse", style="ShipPresets.Treeview")
        self.preset_list.column("#0", anchor="w", stretch=True, width=280, minwidth=220)
        self.preset_list.column("name", width=0, stretch=False)  # Hidden column to store full preset name
        self.preset_list.grid(row=2, column=0, sticky="nsew")
        self.preset_list.bind("<Double-1>", self._on_preset_double_click)
        self.preset_list.bind("<Return>", lambda e: self._load_selected_preset())
        # Save expand/collapse state when user clicks arrow icons (delay to ensure state is updated)
        self.preset_list.bind("<<TreeviewOpen>>", lambda e: self.after(10, self._save_preset_expanded_state))
        self.preset_list.bind("<<TreeviewClose>>", lambda e: self.after(10, self._save_preset_expanded_state))
        # Deselect when clicking empty space
        self.preset_list.bind("<Button-1>", lambda e: self._deselect_on_empty_click(e, self.preset_list))

        # Add scrollbar to preset list
        preset_scrollbar = ttk.Scrollbar(presets_pane, orient="vertical", command=self.preset_list.yview)
        preset_scrollbar.grid(row=2, column=1, sticky="ns")
        self.preset_list.configure(yscrollcommand=preset_scrollbar.set)
        presets_pane.columnconfigure(1, weight=0)
        
        # Configure row tags for alternating colors (theme-aware)
        self._configure_preset_list_row_colors()
        
        # Import/Apply buttons at the bottom of presets pane
        preset_buttons_frame = ttk.Frame(presets_pane)
        preset_buttons_frame.grid(row=3, column=0, columnspan=2, sticky="s", pady=(6, 4))
        
        import_btn = tk.Button(
            preset_buttons_frame, 
            text="⬇ " + t('common.import'), 
            command=self._import_all_from_txt,
            bg="#3a3a3a",
            fg="#e0e0e0", 
            activebackground="#4a4a4a", 
            activeforeground="#ffffff",
            relief="ridge",
            bd=1,                   
            padx=8,                
            pady=2,
            font=("Segoe UI", 8, "normal"),  
            cursor="hand2"
        )
        import_btn.grid(row=0, column=0, padx=(0, 4))
        self.import_btn = import_btn
        ToolTip(import_btn, t('tooltips.import_va'))
        
        apply_btn = tk.Button(
            preset_buttons_frame, 
            text="⬆ " + t('common.apply'), 
            command=self._save_all_to_txt,
            bg="#2a4a2a",
            fg="#e0e0e0", 
            activebackground="#3a5a3a", 
            activeforeground="#ffffff",
            relief="ridge",
            bd=1,                   
            padx=8,                
            pady=2,
            font=("Segoe UI", 8, "normal"),  
            cursor="hand2"
        )
        apply_btn.grid(row=0, column=1, padx=(4, 0))
        ToolTip(apply_btn, t('tooltips.apply_va'))

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
        self._preset_menu.add_command(label=t('context_menu.rename'), command=self._rename_selected_preset)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label=t('context_menu.export'), command=self._export_selected_preset)
        self._preset_menu.add_command(label=t('context_menu.import'), command=self._import_preset_file)
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
        self._preset_empty_menu.add_separator()
        self._preset_empty_menu.add_command(label=t('context_menu.expand_all'), command=self._expand_all_preset_groups)
        self._preset_empty_menu.add_command(label=t('context_menu.collapse_all'), command=self._collapse_all_preset_groups)
        
        self.preset_list.bind("<Button-3>", self._show_preset_menu)

        # Bottom pane - Cargo Monitor
        cargo_pane = ttk.Frame(paned_window)
        paned_window.add(cargo_pane, weight=1)  # weight=1 - allow expansion when sash moved
        
        # Configure cargo pane - allow vertical expansion
        cargo_pane.columnconfigure(0, weight=1)
        cargo_pane.rowconfigure(0, weight=1)  # Allow row to expand
        
        self._create_integrated_cargo_monitor(cargo_pane)

        # Theme toggle button below cargo monitor (styled to match current theme)
        theme_btn_frame = ttk.Frame(sidebar)
        theme_btn_frame.grid(row=1, column=0, sticky="e", pady=(6, 6))
        
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
            command=self._toggle_theme,
            bg=_tbtn_bg,
            fg=_tbtn_fg,
            activebackground=_tbtn_active_bg,
            activeforeground=_tbtn_active_fg,
            relief="solid",
            bd=1,
            padx=6,
            pady=1,
            font=("Segoe UI", 8),
            cursor="hand2"
        )
        self.theme_toggle_btn.pack(side="left")
        
        # Language flag buttons (next to theme button)
        self._create_language_flags(theme_btn_frame)
        
        # Version button (opens About dialog)
        self._create_version_button(theme_btn_frame)

        # Refresh the preset list
        self._refresh_preset_list()
        
        # Save sidebar sash position when it changes (only after initialization)
        def _on_sidebar_sash_moved(event):
            if not getattr(self, '_sidebar_sash_initialized', False):
                return  # Don't save during initial layout
            try:
                from config import save_sidebar_sash_position
                pos = paned_window.sashpos(0)
                if pos > 100:  # Only save valid positions
                    save_sidebar_sash_position(pos)
            except Exception:
                pass
        paned_window.bind("<ButtonRelease-1>", _on_sidebar_sash_moved)
        
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
                    except Exception as e:
                        pass
                elif voice_values and not self.voice_choice.get():
                    self.voice_choice.set(voice_values[0])
                    
        except Exception as e:
            pass

    # ---------- Timers/Toggles tab ----------
    def _build_timers_tab(self, frame: ttk.Frame) -> None:
        # Theme-aware background color
        from config import load_theme
        _mc_theme = load_theme()
        _mc_bg = "#000000" if _mc_theme == "elite_orange" else "#1e1e1e"
        
        # Create a canvas and scrollbar for scrollable content
        canvas = tk.Canvas(frame, bg=_mc_bg, highlightthickness=0)
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

        # Bind mousewheel to canvas - only when mouse is over canvas
        def _on_mousewheel_mc(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel_mc))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # Now build content in scrollable_frame instead of frame
        scrollable_frame.columnconfigure(0, weight=1)
        
        # Timer name translation mapping (English key -> translation key)
        timer_translations = {
            "Duration for firing mining lasers (first period)": "voiceattack.timer_laser_first",
            "Pause between laser periods for weapon recharge/cooldown": "voiceattack.timer_pause",
            "Duration for second laser period (If Laser Mining Extra is enabled)": "voiceattack.timer_laser_extra",
            "Delay before selecting prospector target after laser mining": "voiceattack.timer_target",
            "Delay before retracting cargo scoop after mining sequence": "voiceattack.timer_cargoscoop",
            "Boost Interval (For Core Mining Boost sequense )": "voiceattack.timer_boost",
        }
        
        # Timer help text translation mapping
        timer_help_translations = {
            "Duration for firing mining lasers (first period)": "voiceattack.help_timer_laser_first",
            "Pause between laser periods for weapon recharge/cooldown": "voiceattack.help_timer_pause",
            "Duration for second laser period (If Laser Mining Extra is enabled)": "voiceattack.help_timer_laser_extra",
            "Delay before selecting prospector target after laser mining": "voiceattack.help_timer_target",
            "Delay before retracting cargo scoop after mining sequence": "voiceattack.help_timer_cargoscoop",
            "Boost Interval (For Core Mining Boost sequense )": "voiceattack.help_timer_boost",
        }
        
        # Timers section
        ttk.Label(scrollable_frame, text=t('voiceattack.timers'), font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        r = 1
        for name, spec in TIMERS.items():
            _fname, lo, hi, helptext = spec
            rowf = ttk.Frame(scrollable_frame)
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            # Spinbox first
            sp = ttk.Spinbox(rowf, from_=lo, to=hi, width=5, textvariable=self.timer_vars[name])
            sp.pack(side="left")
            
            # Get localized timer name
            display_name = t(timer_translations.get(name, name)) if name in timer_translations else name
            
            # Label second with tooltip
            label = ttk.Label(rowf, text=f"{display_name} [{lo}..{hi}] {t('voiceattack.seconds')}")
            label.pack(side="left", padx=(6, 0))
            
            # Add tooltip with localized help text
            localized_help = t(timer_help_translations.get(name, name)) if name in timer_help_translations else helptext
            ToolTip(label, localized_help)
            
            r += 1
        
        # Add some spacing between sections
        ttk.Separator(scrollable_frame, orient='horizontal').grid(row=r, column=0, sticky="ew", pady=(20, 10))
        r += 1
        
        # Toggles section with tip on same row
        toggles_header = ttk.Frame(scrollable_frame)
        toggles_header.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        toggles_header.columnconfigure(1, weight=1)  # Make middle column expand
        
        # Theme-aware colors for toggles
        _toggle_bg = "#000000" if self.current_theme == "elite_orange" else "#1e1e1e"
        _toggle_fg = "#ff8c00" if self.current_theme == "elite_orange" else "#ffffff"
        _toggle_tip_fg = "#ffa500"
        
        # Toggle help text translation mapping
        toggle_help_translations = {
            "Auto Honk": "voiceattack.help_auto_honk",
            "Cargo Scoop": "voiceattack.help_cargo_scoop",
            "Headtracker Docking Control": "voiceattack.help_headtracker",
            "Laser Mining Extra": "voiceattack.help_laser_extra",
            "Night Vision": "voiceattack.help_night_vision",
            "FSD Jump Sequence": "voiceattack.help_fsd_jump",
            "Power Settings": "voiceattack.help_power",
            "Prospector Sequence": "voiceattack.help_prospector_sequence",
            "Prospector Sound Effect": "voiceattack.help_prospector_sound",
            "Target Prospector": "voiceattack.help_target_prospector",
            "Thrust Up": "voiceattack.help_thrust_up",
            "Pulse Wave Analyser": "voiceattack.help_pulse_wave",
            "Target": "voiceattack.help_target",
        }
        
        ttk.Label(toggles_header, text=t('voiceattack.toggles'), font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(toggles_header, text=t('voiceattack.tip_stop_commands'), 
                 fg=_toggle_tip_fg, bg=_toggle_bg, font=("Segoe UI", 8, "italic")).grid(row=0, column=1, sticky="")
        r += 1
        
        # Store checkbox widgets for dependent toggles
        self.toggle_checkboxes = {}
        
        for name, (_fname, helptext) in TOGGLES.items():
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            # Indent dependent toggles
            indent = 20 if name in ["Prospector Sound Effect", "Target Prospector", "Thrust Up"] else 0
            if indent > 0:
                tk.Label(rowf, text="", bg=_toggle_bg, width=2).pack(side="left")
            
            checkbox = tk.Checkbutton(rowf, text=f"{t('voiceattack.enable')} {name}", variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            
            # Store checkbox reference for dependency control
            self.toggle_checkboxes[name] = checkbox
            
            # Add callback for Prospector Sequence to control dependent toggles
            if name == "Prospector Sequence":
                self.toggle_vars[name].trace_add("write", lambda *args: self._update_prospector_dependencies())
            
            # Get localized help text
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            
            # Add tooltip to checkbox
            ToolTip(checkbox, display_help)
            
            _help_fg = "#888888" if self.current_theme == "elite_orange" else "gray"
            tk.Label(rowf, text=display_help, fg=_help_fg, bg=_toggle_bg,
                     font=("Segoe UI", 8, "italic")).pack(side="left", padx=(10, 0))
            r += 1
        
        # Initialize dependent toggle states
        self._update_prospector_dependencies()

    def _update_prospector_dependencies(self):
        """Enable/disable dependent toggles based on Prospector Sequence state"""
        try:
            if "Prospector Sequence" not in self.toggle_vars or "Prospector Sequence" not in self.toggle_checkboxes:
                return
            
            # Get master toggle state
            master_enabled = self.toggle_vars["Prospector Sequence"].get() == 1
            
            # Update dependent checkboxes
            for dependent in ["Prospector Sound Effect", "Target Prospector", "Thrust Up"]:
                if dependent in self.toggle_checkboxes:
                    checkbox = self.toggle_checkboxes[dependent]
                    if master_enabled:
                        checkbox.configure(state="normal")
                    else:
                        checkbox.configure(state="disabled")
                        # Also uncheck them when disabled
                        self.toggle_vars[dependent].set(0)
        except Exception as e:
            print(f"Error updating prospector dependencies: {e}")

    # ---------- Status helper ----------
    def _set_status(self, msg: str, clear_after: int = 5000) -> None:
        try:
            self.status.set(msg)
            if clear_after:
                self.after(clear_after, lambda: self.status.set(""))
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
            print(f"[ROUTE] Error writing jumpsleft: {e}")
    
    def _initialize_va_variables(self) -> None:
        """Initialize VoiceAttack variables manager"""
        try:
            from va_variables import VAVariablesManager
            journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
            self.va_variables = VAVariablesManager(self.vars_dir, journal_dir)
            self.va_variables.initialize_jumps_left()
            print("✅ Initialized VoiceAttack variables (jumpsleft.txt)")
            
            # Start polling for VA variables
            self.after(2000, self._poll_va_variables)
            
            # Start polling for route status (CMDR/system display updates)
            self.after(2000, self._poll_route_status)
        except Exception as e:
            log.error(f"Error initializing VA variables: {e}")
    
    def _poll_va_variables(self) -> None:
        """Poll for VoiceAttack variable updates"""
        try:
            if self.va_variables:
                self.va_variables.poll_route_status()
        except Exception as e:
            log.error(f"Error polling VA variables: {e}")
        finally:
            self.after(2000, self._poll_va_variables)
    
    def _initialize_jumps_left(self) -> None:
        """Initialize jumpsleft.txt by checking for active route in current journal"""
        try:
            journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
            if not journal_dir or not os.path.exists(journal_dir):
                self._write_jumps_left(0)
                return
            
            # Find most recent journal file
            journal_files = [f for f in os.listdir(journal_dir) if f.startswith('Journal.') and f.endswith('.log')]
            if not journal_files:
                self._write_jumps_left(0)
                return
            
            journal_files.sort(reverse=True)
            latest_journal = os.path.join(journal_dir, journal_files[0])
            
            # Scan backwards through journal to find most recent FSDTarget or NavRouteClear
            jumps_remaining = 0
            try:
                with open(latest_journal, 'r', encoding='utf-8') as f:
                    # Read last 50KB to find recent route info
                    f.seek(0, 2)
                    file_size = f.tell()
                    f.seek(max(0, file_size - 51200))
                    lines = f.readlines()
                    
                    # Scan backwards for most recent route event
                    for line in reversed(lines):
                        if not line.strip():
                            continue
                        try:
                            event = json.loads(line)
                            event_type = event.get('event')
                            
                            if event_type == 'FSDTarget':
                                jumps_remaining = event.get('RemainingJumpsInRoute', 0)
                                break
                            elif event_type == 'NavRouteClear':
                                jumps_remaining = 0
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                log.error(f"Error reading journal for route info: {e}")
            
            self._write_jumps_left(jumps_remaining)
            
        except Exception as e:
            log.error(f"Error initializing jumpsleft: {e}")
            self._write_jumps_left(0)
    
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
                    print(f"[ROUTE] Error checking NavRoute: {e}")
            
            # Always scan journal for FSDTarget (authoritative source)
            if True:
                # Check latest journal for FSDTarget
                journal_files = [f for f in os.listdir(journal_dir) if f.startswith('Journal.') and f.endswith('.log')]
                if journal_files:
                    journal_files.sort(reverse=True)
                    latest_journal = os.path.join(journal_dir, journal_files[0])
                    
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
            
            # Get total systems visited from journal Statistics event (game's official count)
            # Note: This updates when docking, quitting, or periodically - not after every jump
            total_systems = 0
            if hasattr(self, 'prospector_panel') and self.prospector_panel.journal_dir:
                try:
                    from journal_parser import JournalParser
                    parser = JournalParser(self.prospector_panel.journal_dir)
                    total_systems = parser.get_systems_visited() or 0
                except:
                    pass
            
            self.total_systems_label_prefix.config(text=t('status_bar.total_systems') + " ")
            self.total_systems_label_value.config(text=str(total_systems))
            
        except Exception as e:
            print(f"Error updating CMDR/system display: {e}")

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
                    bg=bg_color, fg=fg_color, font=("Segoe UI", 9)).pack(anchor="w")
            
            tk.Label(frame, text=current_system, 
                    bg=bg_color, fg=fg_color, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 15))
            
            # Visit count entry
            count_frame = tk.Frame(frame, bg=bg_color)
            count_frame.pack(fill="x", pady=5)
            
            tk.Label(count_frame, text=t('context_menu.visit_count_label'), 
                    bg=bg_color, fg=fg_color, font=("Segoe UI", 9)).pack(side="left")
            
            count_var = tk.StringVar(value=str(current_count))
            count_entry = tk.Entry(count_frame, textvariable=count_var, width=10,
                                  bg=entry_bg, fg=entry_fg, insertbackground=fg_color,
                                  relief="solid", bd=1, font=("Segoe UI", 10))
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
                                pady=6, padx=15, font=("Segoe UI", 9))
            save_btn.pack(side="right", padx=(8, 0))
            
            cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=cancel,
                                  bg="#5a2a2a", fg="#ffffff", 
                                  activebackground="#6a3a3a", activeforeground="#ffffff",
                                  relief="solid", bd=1, cursor="hand2", 
                                  pady=6, padx=15, font=("Segoe UI", 9))
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
            
            dialog.grab_set()
            count_entry.focus_set()
            
            # Bind Enter to save
            dialog.bind("<Return>", lambda e: save_and_close())
            dialog.bind("<Escape>", lambda e: cancel())
            
        except Exception as e:
            print(f"Error showing edit visits dialog: {e}")

    def _import_all_from_txt(self) -> None:
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
                        val = int(raw)
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

            msg = f"Imported {len(found)} values"
            if missing:
                msg += f"; {len(missing)} missing/invalid: {', '.join(missing[:3])}"
                if len(missing) > 3:
                    msg += f" +{len(missing)-3} more"
            self._set_status(msg)
            
            # Also print to console for debugging
            if missing:
                print(f"Missing/invalid files: {missing}")
        except Exception as e:
            messagebox.showerror("Import failed", str(e))

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
                    raw = int(self.timer_vars[name].get())
                except Exception:
                    raw = lo
                val = max(lo, min(hi, raw))
                self.timer_vars[name].set(val)
                self._write_var_text(base, str(val))

            self._set_status("Settings saved to VoiceAttack Variables.")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    # ---------- Presets (Settings folder) ----------
    def _settings_path(self, name: str) -> str:
        return os.path.join(self.settings_dir, f"{name}.json")

    def _configure_preset_list_row_colors(self) -> None:
        """Configure row colors for preset list based on current theme"""
        if self.current_theme == "elite_orange":
            self.preset_list.tag_configure('oddrow', background='#1e1e1e', foreground='#ff8c00', font=("Segoe UI", 9))
            self.preset_list.tag_configure('evenrow', background='#252525', foreground='#ff8c00', font=("Segoe UI", 9))
            self.preset_list.tag_configure('group', background='#1a1a1a', foreground='#ffcc00', font=("Segoe UI", 9, "bold"))
        else:
            self.preset_list.tag_configure('oddrow', background='#1e1e1e', foreground='#e6e6e6', font=("Segoe UI", 9))
            self.preset_list.tag_configure('evenrow', background='#282828', foreground='#e6e6e6', font=("Segoe UI", 9))
            self.preset_list.tag_configure('group', background='#1a1a1a', foreground='#aaaaaa', font=("Segoe UI", 9, "bold"))
    
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
        known_ships = [
            "Alliance Challenger", "Alliance Chieftain", "Alliance Crusader",
            "Asp Explorer", "Asp Scout",
            "Beluga Liner",
            "Caspian Explorer",
            "Cobra Mk III", "Cobra Mk IV", "Cobra Mk V",
            "Corsair",
            "Diamondback Explorer", "Diamondback Scout",
            "Dolphin",
            "Eagle Mk II",
            "Federal Assault Ship", "Federal Corvette", "Federal Dropship", "Federal Gunship",
            "Fer-de-Lance",
            "Hauler",
            "Imperial Clipper", "Imperial Courier", "Imperial Cutter", "Imperial Eagle",
            "Keelback",
            "Krait Mk II", "Krait Phantom",
            "Mamba", "Mandalay",
            "Orca",
            "Panther Clipper Mk II",
            "Python Mk II", "Python",
            "Sidewinder Mk I",
            "Type-11 Prospector", "Type-10 Defender", "Type-9 Heavy", 
            "Type-8 Transporter", "Type-7 Transporter", "Type-6 Transporter",
            "Viper Mk III", "Viper Mk IV",
            "Vulture",
            "Anaconda", "Adder",  # Short names last
        ]
        
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
        except Exception:
            pass
        
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
    
    def _select_preset_by_name(self, preset_name: str) -> bool:
        """Find and select a preset by its full name in the hierarchical tree.
        Returns True if found, False otherwise."""
        # Search through all groups and their children
        for group_id in self.preset_list.get_children():
            for item_id in self.preset_list.get_children(group_id):
                values = self.preset_list.item(item_id, "values")
                if values and values[0] == preset_name:
                    # Found it - expand group, select, and scroll to it
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
    
    def _on_preset_double_click(self, event) -> None:
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

    def _current_mapping(self) -> Dict[str, Any]:
        # Exclude Core/Non-Core settings from ship presets
        announcement_settings = {}
        for k, v in self.announcement_vars.items():
            if k not in ("Core Asteroids", "Non-Core Asteroids"):
                announcement_settings[k] = v.get()
        
        return {
            "Firegroups": {
                t: {"fg": self.tool_fg[t].get(),
                    "btn": (self.tool_btn[t].get() if t in self.tool_btn else None)}
                for t in TOOL_ORDER
            },
            "Toggles": {k: v.get() for k, v in self.toggle_vars.items() if k != "FSD Jump Sequence"},
            "Announcements": announcement_settings,
            "Timers": {k: v.get() for k, v in self.timer_vars.items()},
        }

    def _apply_mapping(self, data: Dict[str, Any]) -> None:
        for t, spec in data.get("Firegroups", {}).items():
            fg = spec.get("fg")
            if isinstance(fg, str) and fg in FIREGROUPS and t in self.tool_fg:
                self.tool_fg[t].set(fg)
            btn = spec.get("btn")
            if t in self.tool_btn and isinstance(btn, int) and btn in (1, 2):
                self.tool_btn[t].set(btn)
        for k, v in data.get("Toggles", {}).items():
            # Skip FSD Jump Sequence - it's not saved in presets
            if k in self.toggle_vars and k != "FSD Jump Sequence":
                self.toggle_vars[k].set(int(v))
        
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
            if k in self.timer_vars:
                self.timer_vars[k].set(int(v))
        self._set_status("Preset loaded (not yet written to Variables).")

    def _ask_preset_name(self, initial: Optional[str] = None) -> Optional[str]:
        """Custom dark dialog for preset names"""
        dialog = tk.Toplevel(self)
        dialog.title(t('dialogs.preset_name'))
        dialog.configure(bg="#2c3e50")
        dialog.geometry("400x150")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = None
        
        # Label
        label = tk.Label(dialog, text="Enter a name for this preset:", 
                        bg="#2c3e50", fg="#ecf0f1", font=("Segoe UI", 9))
        label.pack(pady=(20, 10))
        
        # Entry
        entry = tk.Entry(dialog, font=("Segoe UI", 9), width=30)
        entry.pack(pady=5)
        if initial:
            entry.insert(0, initial)
            entry.selection_range(0, tk.END)
        
        # Buttons frame
        btn_frame = tk.Frame(dialog, bg="#2c3e50")
        btn_frame.pack(pady=20)
        
        def on_ok():
            nonlocal result
            result = entry.get().strip()
            dialog.destroy()
            
        def on_cancel():
            dialog.destroy()
            
        ok_btn = tk.Button(btn_frame, text=t('common.ok'), command=on_ok,
                          bg="#27ae60", fg="white", font=("Segoe UI", 9),
                          width=10)
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text=t('common.cancel'), command=on_cancel,
                              bg="#e74c3c", fg="white", font=("Segoe UI", 9),
                              width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind Enter/Escape
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        entry.bind('<Return>', lambda e: on_ok())
        
        entry.focus_set()
        dialog.wait_window()
        return result if result else None

    def _ask_new_preset_name(self, preselect_ship: Optional[str] = None) -> Optional[str]:
        """Dialog for creating new preset with Ship Type dropdown and custom name"""
        # Complete Elite Dangerous ship list (alphabetical)
        ship_types = [
            "Adder",
            "Alliance Challenger",
            "Alliance Chieftain",
            "Alliance Crusader",
            "Anaconda",
            "Asp Explorer",
            "Asp Scout",
            "Beluga Liner",
            "Caspian Explorer",
            "Cobra Mk III",
            "Cobra Mk IV",
            "Cobra Mk V",
            "Corsair",
            "Diamondback Explorer",
            "Diamondback Scout",
            "Dolphin",
            "Eagle Mk II",
            "Federal Assault Ship",
            "Federal Corvette",
            "Federal Dropship",
            "Federal Gunship",
            "Fer-de-Lance",
            "Hauler",
            "Imperial Clipper",
            "Imperial Courier",
            "Imperial Cutter",
            "Imperial Eagle",
            "Keelback",
            "Krait Mk II",
            "Krait Phantom",
            "Mamba",
            "Mandalay",
            "Orca",
            "Panther Clipper Mk II",
            "Python",
            "Python Mk II",
            "Sidewinder Mk I",
            "Type-6 Transporter",
            "Type-7 Transporter",
            "Type-8 Transporter",
            "Type-9 Heavy",
            "Type-10 Defender",
            "Type-11 Prospector",
            "Viper Mk III",
            "Viper Mk IV",
            "Vulture",
            "Other"
        ]
        
        dialog = tk.Toplevel(self)
        dialog.withdraw()  # Hide while setting up
        dialog.title(t('dialogs.new_ship_preset'))
        dialog.configure(bg="#1e1e1e")
        dialog.geometry("450x240")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
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
                       fieldbackground="#2d2d2d",
                       background="#2d2d2d",
                       foreground="#ffffff",
                       selectbackground=accent_color,
                       selectforeground=accent_fg)
        style.map("Preset.TCombobox",
                 fieldbackground=[("readonly", "#2d2d2d")],
                 selectbackground=[("readonly", accent_color)],
                 selectforeground=[("readonly", accent_fg)])
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
            elif icon_path and icon_path.endswith('.png'):
                dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception:
            pass
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = None
        
        # Title
        title_label = tk.Label(dialog, text="💾 Create New Ship Preset", 
                              bg="#1e1e1e", fg="#ff8c00", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=(15, 15))
        
        # Ship Type selection
        type_frame = tk.Frame(dialog, bg="#1e1e1e")
        type_frame.pack(fill="x", padx=25, pady=(0, 10))
        
        tk.Label(type_frame, text="Ship Type:", bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10)).pack(side=tk.LEFT)
        
        # Pre-select ship if provided
        default_ship = preselect_ship if preselect_ship and preselect_ship in ship_types else ship_types[0]
        ship_var = tk.StringVar(value=default_ship)
        ship_combo = ttk.Combobox(type_frame, textvariable=ship_var, values=ship_types, 
                                  state="readonly", width=28, font=("Segoe UI", 10),
                                  style="Preset.TCombobox")
        ship_combo.pack(side=tk.LEFT, padx=(15, 0))
        
        # Custom name entry
        name_frame = tk.Frame(dialog, bg="#1e1e1e")
        name_frame.pack(fill="x", padx=25, pady=10)
        
        tk.Label(name_frame, text="Build Name:", bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10)).pack(side=tk.LEFT)
        
        name_entry = tk.Entry(name_frame, font=("Segoe UI", 10), width=30,
                             bg="#2d2d2d", fg="#ffffff", insertbackground=accent_color,
                             selectbackground=accent_color, selectforeground=accent_fg,
                             relief="flat", bd=2)
        name_entry.pack(side=tk.LEFT, padx=(10, 0))
        
        # Preview
        preview_frame = tk.Frame(dialog, bg="#1e1e1e")
        preview_frame.pack(fill="x", padx=25, pady=10)
        
        tk.Label(preview_frame, text="Preview:", bg="#1e1e1e", fg="#888888", 
                font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        preview_label = tk.Label(preview_frame, text="", bg="#1e1e1e", fg=accent_color, 
                                font=("Segoe UI", 10, "bold"))
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
        update_preview()  # Initial preview
        
        # Buttons frame
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
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
            
        ok_btn = tk.Button(btn_frame, text="💾 Save", command=on_ok,
                          bg=accent_color, fg=accent_fg, font=("Segoe UI", 10, "bold"),
                          activebackground=accent_color, activeforeground=accent_fg,
                          width=10, cursor="hand2")
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text=t('common.cancel'), command=on_cancel,
                              bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10),
                              activebackground="#4a4a4a", activeforeground="#ffffff",
                              width=10, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind Enter/Escape
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        # Show dialog
        dialog.deiconify()
        name_entry.focus_set()
        dialog.wait_window()
        return result if result else None

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
        # Detect current ship folder selection
        current_ship = None
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
        self._set_status(f"Saved new preset '{name}'.")

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
            
        with open(self._settings_path(sel), "w", encoding="utf-8") as f:
            json.dump(self._current_mapping(), f, indent=2)
        self._set_status(f"Overwrote preset '{sel}'.")

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
            self._refresh_preset_list()
            self._select_preset_by_name(new_name)
            self._set_status(f"Updated preset to '{new_name}'.")
        except Exception as e:
            messagebox.showerror("Edit failed", str(e))

    def _ask_edit_preset_name(self, detected_ship: str, detected_variant: str, original_name: str) -> Optional[str]:
        """Dialog for editing preset - change ship type and build name"""
        # Complete Elite Dangerous ship list (alphabetical)
        ship_types = [
            "Adder",
            "Alliance Challenger", "Alliance Chieftain", "Alliance Crusader",
            "Anaconda",
            "Asp Explorer", "Asp Scout",
            "Beluga Liner",
            "Caspian Explorer",
            "Cobra Mk III", "Cobra Mk IV", "Cobra Mk V",
            "Corsair",
            "Diamondback Explorer", "Diamondback Scout",
            "Dolphin",
            "Eagle Mk II",
            "Federal Assault Ship", "Federal Corvette", "Federal Dropship", "Federal Gunship",
            "Fer-de-Lance",
            "Hauler",
            "Imperial Clipper", "Imperial Courier", "Imperial Cutter", "Imperial Eagle",
            "Keelback",
            "Krait Mk II", "Krait Phantom",
            "Mamba", "Mandalay",
            "Orca",
            "Panther Clipper Mk II",
            "Python", "Python Mk II",
            "Sidewinder Mk I",
            "Type-6 Transporter", "Type-7 Transporter", "Type-8 Transporter",
            "Type-9 Heavy", "Type-10 Defender", "Type-11 Prospector",
            "Viper Mk III", "Viper Mk IV",
            "Vulture",
            "Other"
        ]
        
        dialog = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title(t('dialogs.edit_ship_preset'))
        dialog.configure(bg="#1e1e1e")
        dialog.geometry("480x280")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
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
                       fieldbackground="#2d2d2d",
                       background="#2d2d2d",
                       foreground="#ffffff",
                       selectbackground=accent_color,
                       selectforeground=accent_fg)
        style.map("Preset.TCombobox",
                 fieldbackground=[("readonly", "#2d2d2d")],
                 selectbackground=[("readonly", accent_color)],
                 selectforeground=[("readonly", accent_fg)])
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = None
        
        # Title
        title_label = tk.Label(dialog, text="✏️ Edit Ship Preset", 
                              bg="#1e1e1e", fg=accent_color, 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=(15, 5))
        
        # Show current name
        orig_label = tk.Label(dialog, text=f"Current: {original_name}", 
                             bg="#1e1e1e", fg="#888888", 
                             font=("Segoe UI", 9))
        orig_label.pack(pady=(0, 10))
        
        # Ship Type selection
        type_frame = tk.Frame(dialog, bg="#1e1e1e")
        type_frame.pack(fill="x", padx=25, pady=(0, 10))
        
        tk.Label(type_frame, text="Ship Type:", bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10)).pack(side=tk.LEFT)
        
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
                                  state="readonly", width=28, font=("Segoe UI", 10),
                                  style="Preset.TCombobox")
        ship_combo.pack(side=tk.LEFT, padx=(15, 0))
        
        # Build name entry
        name_frame = tk.Frame(dialog, bg="#1e1e1e")
        name_frame.pack(fill="x", padx=25, pady=10)
        
        tk.Label(name_frame, text="Build Name:", bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10)).pack(side=tk.LEFT)
        
        name_entry = tk.Entry(name_frame, font=("Segoe UI", 10), width=30,
                             bg="#2d2d2d", fg="#ffffff", insertbackground=accent_color,
                             selectbackground=accent_color, selectforeground=accent_fg,
                             relief="flat", bd=2)
        name_entry.pack(side=tk.LEFT, padx=(10, 0))
        if detected_variant:
            name_entry.insert(0, detected_variant)
        
        # Preview
        preview_frame = tk.Frame(dialog, bg="#1e1e1e")
        preview_frame.pack(fill="x", padx=25, pady=10)
        
        tk.Label(preview_frame, text="New Name:", bg="#1e1e1e", fg="#888888", 
                font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        preview_label = tk.Label(preview_frame, text="", bg="#1e1e1e", fg=accent_color, 
                                font=("Segoe UI", 10, "bold"))
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
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
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
            
        ok_btn = tk.Button(btn_frame, text="✏️ Save", command=on_ok,
                          bg=accent_color, fg=accent_fg, font=("Segoe UI", 10, "bold"),
                          activebackground=accent_color, activeforeground=accent_fg,
                          width=10, cursor="hand2")
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text=t('common.cancel'), command=on_cancel,
                              bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10),
                              activebackground="#4a4a4a", activeforeground="#ffffff",
                              width=10, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        dialog.deiconify()
        name_entry.focus_set()
        dialog.wait_window()
        return result

    def _rename_selected_preset(self) -> None:
        """Rename the selected preset - just call the Edit function"""
        # Rename uses the same Edit dialog - Edit handles the full workflow
        self._edit_selected_preset()

    # ==================== DISTANCE CALCULATOR TAB ====================
    
    def _build_distance_calculator_tab(self, frame: ttk.Frame) -> None:
        """Build the Distance Calculator tab"""
        from edsm_distance import get_distance_calculator
        from fleet_carrier_tracker import get_fleet_carrier_tracker
        from config import (load_home_system, save_home_system,
                           load_fleet_carrier_system, save_fleet_carrier_system,
                           load_distance_calculator_systems, load_theme)
        
        # Theme-aware background color
        _dc_theme = load_theme()
        _dc_bg = "#000000" if _dc_theme == "elite_orange" else "#1e1e1e"
        
        # Get calculator instance
        self.distance_calculator = get_distance_calculator()
        self.fc_tracker = get_fleet_carrier_tracker()
        
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Configuration section (moved to top)
        config_frame = ttk.LabelFrame(main_container, text=t('distance_calculator.configuration'), padding=10)
        config_frame.pack(fill="x", pady=(0, 10))
        
        # Configure column weights: label, input (limited expand), button, distance info, visits
        config_frame.columnconfigure(0, weight=0, minsize=120)  # Label column (fixed)
        config_frame.columnconfigure(1, weight=0, minsize=250)  # Input column (fixed width)
        config_frame.columnconfigure(2, weight=0)  # Button column (fixed)
        config_frame.columnconfigure(3, weight=1)  # Distance info column (expands)
        config_frame.columnconfigure(4, weight=0, minsize=80)  # Visits column (fixed)
        
        # Current System Display (always updated, read-only)
        row = 0
        ttk.Label(config_frame, text=t('distance_calculator.current_system'), font=("Segoe UI", 9, "bold")).grid(row=row, column=0, sticky="w", pady=3)
        self.distance_current_system = tk.StringVar(value="---")
        # Clear selection when current system updates (prevents auto-selection of readonly entry)
        try:
            self.distance_current_system.trace_add('write', lambda *args: (self.distance_current_display.selection_clear() if hasattr(self, 'distance_current_display') else None, self.import_btn.focus_set() if hasattr(self, 'import_btn') else None))
        except Exception:
            try:
                self.distance_current_system.trace('w', lambda *args: (self.distance_current_display.selection_clear() if hasattr(self, 'distance_current_display') else None, self.import_btn.focus_set() if hasattr(self, 'import_btn') else None))
            except Exception:
                pass
        current_display = tk.Entry(config_frame, textvariable=self.distance_current_system, 
                                   bg="#2d2d2d", fg="#00ff00", font=("Segoe UI", 9, "bold"),
                       state="readonly", readonlybackground="#2d2d2d", takefocus=False)
        current_display.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
        ToolTip(current_display, t('tooltips.current_system'))
        # Make the display available for selection-clear later
        self.distance_current_display = current_display
        # Avoid the Current System entry being selected when displayed
        try:
            current_display.bind('<Map>', lambda e: current_display.selection_clear())
            current_display.bind('<Visibility>', lambda e: current_display.selection_clear())
            current_display.bind('<FocusIn>', lambda e: current_display.selection_clear())
        except Exception:
            pass
        # Remove highlight from Current System entry
        config_frame.after(100, lambda: current_display.selection_clear())
        
        # Current system Sol distance label
        self.current_sol_label = tk.Label(config_frame, text="", 
                                         font=("Segoe UI", 9), fg="#ffcc00", bg="#1e1e1e", anchor="w")
        self.current_sol_label.grid(row=row, column=3, sticky="w", padx=(5, 0), pady=3)
        
        # Visits count label (separate column, aligned vertically)
        self.distance_visits_label = tk.Label(config_frame, text="", 
                                              font=("Segoe UI", 9), fg="#ffcc00", bg="#1e1e1e", anchor="e")
        self.distance_visits_label.grid(row=row, column=4, sticky="e", padx=(5, 0), pady=3)
        
        # Home System
        row += 1
        ttk.Label(config_frame, text=t('distance_calculator.home_system'), font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self.distance_home_system = tk.StringVar(value=load_home_system())
        home_entry = tk.Entry(config_frame, textvariable=self.distance_home_system, 
                             bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 9),
                             insertbackground="#ffffff")
        home_entry.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
        home_entry.bind("<Return>", self._distance_set_home)  # Bind Enter key
        ToolTip(home_entry, t('tooltips.home_system'))
        
        # Distance to Home (from current) and to Sol
        home_info_frame = tk.Frame(config_frame, bg="#1e1e1e")
        home_info_frame.grid(row=row, column=3, sticky="w", padx=(5, 0), pady=3)
        
        self.distance_to_home_label = tk.Label(home_info_frame, text="", 
                                               font=("Segoe UI", 9), fg="#ffcc00", bg="#1e1e1e", anchor="w")
        self.distance_to_home_label.pack(side="left")
        
        self.home_sol_label = tk.Label(home_info_frame, text="", 
                                       font=("Segoe UI", 9), fg="#888888", bg="#1e1e1e", anchor="w")
        self.home_sol_label.pack(side="left", padx=(10, 0))
        
        # Home visits label (column 4, aligned with current system visits)
        self.home_visits_label = tk.Label(config_frame, text="", 
                                          font=("Segoe UI", 9), fg="#ffcc00", bg="#1e1e1e", anchor="e")
        self.home_visits_label.grid(row=row, column=4, sticky="e", padx=(5, 0), pady=3)
        
        # Fleet Carrier System (auto-detected, read-only)
        row += 1
        ttk.Label(config_frame, text=t('distance_calculator.fleet_carrier'), font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self.distance_fc_system = tk.StringVar(value="")  # Will be auto-detected
        fc_entry = tk.Entry(config_frame, textvariable=self.distance_fc_system, 
                           bg="#2d2d2d", fg="#ffaa00", font=("Segoe UI", 9),
                           state="readonly", readonlybackground="#2d2d2d")
        fc_entry.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
        ToolTip(fc_entry, t('tooltips.fleet_carrier'))
        
        # Distance to FC (from current) and to Sol
        fc_info_frame = tk.Frame(config_frame, bg="#1e1e1e")
        fc_info_frame.grid(row=row, column=3, sticky="w", padx=(5, 0), pady=3)
        
        self.distance_to_fc_label = tk.Label(fc_info_frame, text="", 
                                             font=("Segoe UI", 9), fg="#ffcc00", bg="#1e1e1e", anchor="w")
        self.distance_to_fc_label.pack(side="left")
        
        self.fc_sol_label = tk.Label(fc_info_frame, text="", 
                                     font=("Segoe UI", 9), fg="#888888", bg="#1e1e1e", anchor="w")
        self.fc_sol_label.pack(side="left", padx=(10, 0))
        
        # FC visits label (column 4, aligned with other visits)
        self.fc_visits_label = tk.Label(config_frame, text="", 
                                        font=("Segoe UI", 9), fg="#ffcc00", bg="#1e1e1e", anchor="e")
        self.fc_visits_label.grid(row=row, column=4, sticky="e", padx=(5, 0), pady=3)
        
        # Refresh locations button (current system + FC)
        row += 1
        auto_fc_btn = tk.Button(config_frame, text=t('distance_calculator.refresh_locations'), 
                               command=self._distance_refresh_locations,
                               bg="#2a3a4a", fg="#e0e0e0", activebackground="#3a4a5a",
                               activeforeground="#ffffff", relief="ridge", bd=1, padx=8, pady=3,
                               font=("Segoe UI", 8, "normal"), cursor="hand2")
        auto_fc_btn.grid(row=row, column=0, columnspan=4, pady=(8, 0))
        ToolTip(auto_fc_btn, t('tooltips.refresh_locations'))
        
        # Calculator section
        calc_frame = ttk.LabelFrame(main_container, text=t('distance_calculator.system_calculator'), padding=10)
        calc_frame.pack(fill="x", pady=(0, 10))
        
        # Configure column weights: label, input (fixed), buttons
        calc_frame.columnconfigure(0, weight=0, minsize=80)   # Label column (fixed)
        calc_frame.columnconfigure(1, weight=0, minsize=250)  # Input column (fixed width)
        calc_frame.columnconfigure(2, weight=1)  # Button column (expands instead)
        
        # Load saved systems
        saved_system_a, saved_system_b = load_distance_calculator_systems()
        
        # System A input
        row = 0
        ttk.Label(calc_frame, text=t('distance_calculator.system_a'), font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self.distance_system_a = tk.StringVar(value=saved_system_a)
        system_a_entry = tk.Entry(calc_frame, textvariable=self.distance_system_a, 
                                  bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 9),
                                  insertbackground="#ffffff")
        system_a_entry.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
        system_a_entry.bind("<Return>", lambda e: self._calculate_distances())
        system_a_entry.bind("<FocusOut>", lambda e: self._save_distance_systems())
        
        use_current_btn = tk.Button(calc_frame, text=t('distance_calculator.use_current'), command=self._distance_use_current_system,
                                   bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                   activeforeground="#ffffff", relief="ridge", bd=1, 
                                   font=("Segoe UI", 8, "normal"), cursor="hand2", width=14)
        use_current_btn.grid(row=row, column=2, pady=3, padx=(5, 0), sticky="w")
        ToolTip(use_current_btn, t('tooltips.use_current'))
        
        # System B input
        row += 1
        ttk.Label(calc_frame, text=t('distance_calculator.system_b'), font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", pady=3)
        self.distance_system_b = tk.StringVar(value=saved_system_b)
        system_b_entry = tk.Entry(calc_frame, textvariable=self.distance_system_b, 
                                  bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 9),
                                  insertbackground="#ffffff")
        system_b_entry.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
        system_b_entry.bind("<Return>", lambda e: self._calculate_distances())
        system_b_entry.bind("<FocusOut>", lambda e: self._save_distance_systems())
        
        # Quick buttons for System B
        buttons_frame = tk.Frame(calc_frame, bg="#1e1e1e")
        buttons_frame.grid(row=row, column=2, pady=3, padx=(5, 0), sticky="w")
        
        use_home_btn = tk.Button(buttons_frame, text=t('distance_calculator.home'), command=self._distance_use_home,
                                bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                activeforeground="#ffffff", relief="ridge", bd=1, 
                                font=("Segoe UI", 8, "normal"), cursor="hand2", width=6)
        use_home_btn.pack(side="left", padx=(0, 2))
        ToolTip(use_home_btn, t('tooltips.use_home'))
        
        use_fc_btn = tk.Button(buttons_frame, text=t('distance_calculator.fc'), command=self._distance_use_fc,
                              bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                              activeforeground="#ffffff", relief="ridge", bd=1, 
                              font=("Segoe UI", 8, "normal"), cursor="hand2", width=4)
        use_fc_btn.pack(side="left")
        ToolTip(use_fc_btn, t('tooltips.use_fc'))
        
        # Calculate button (or auto-calculate on change)
        row += 1
        calc_btn = tk.Button(calc_frame, text=t('distance_calculator.calculate_distance'), command=self._calculate_distances,
                   bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                   activeforeground="#ffffff", relief="ridge", bd=1, padx=12, pady=4,
                   font=("Segoe UI", 9, "bold"), cursor="hand2")
        calc_btn.grid(row=row, column=0, columnspan=3, pady=(8, 3))
        ToolTip(calc_btn, t('tooltips.calculate_distance'))

        # Set focus to the Calculate Distance button after UI is built
        calc_frame.after(100, calc_btn.focus_set)
        
        # Status/Loading indicator
        row += 1
        self.distance_status_label = tk.Label(calc_frame, text="", 
                                              font=("Segoe UI", 8, "italic"), fg="#888888", bg=_dc_bg)
        self.distance_status_label.grid(row=row, column=0, columnspan=2, pady=(0, 5))
        
        # EDSM API status indicator
        self.edsm_status_label = tk.Label(calc_frame, text="⚫ EDSM: checking...", 
                                          font=("Segoe UI", 8), fg="#888888", bg=_dc_bg, anchor="e")
        self.edsm_status_label.grid(row=row, column=2, pady=(0, 5), sticky="e", padx=(5, 0))
        ToolTip(self.edsm_status_label, t('tooltips.edsm_status'))
        
        # Start EDSM status check
        self.after(500, self._check_edsm_status)
        
        # Results section
        results_frame = ttk.LabelFrame(main_container, text=t('distance_calculator.results'), padding=10)
        results_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        # Distance A ↔ B
        row = 0
        self.distance_ab_label = tk.Label(results_frame, text=f"➤ {t('distance_calculator.distance')} A ↔ B: ---", 
                                         font=("Segoe UI", 11, "bold"), fg="#ffcc00", bg=_dc_bg, anchor="w")
        self.distance_ab_label.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # Separator
        row += 1
        separator = tk.Frame(results_frame, height=1, bg="#444444")
        separator.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        # System A Info with system name on same line (left column)
        row += 1
        self.distance_system_a_name = tk.Label(results_frame, text=t('distance_calculator.system_a_info') + " ---", 
                                               font=("Segoe UI", 9, "bold"), fg="#ffaa00", bg=_dc_bg, anchor="w")
        self.distance_system_a_name.grid(row=row, column=0, sticky="w", padx=(0, 20), pady=(5, 0))
        
        # System B Info with system name on same line (right column)
        self.distance_system_b_name = tk.Label(results_frame, text=t('distance_calculator.system_b_info') + " ---", 
                                               font=("Segoe UI", 9, "bold"), fg="#ffaa00", bg=_dc_bg, anchor="w")
        self.distance_system_b_name.grid(row=row, column=1, sticky="w", pady=(5, 0))
        
        # Distance to Sol - side by side
        row += 1
        self.distance_a_sol_label = tk.Label(results_frame, text=t('distance_calculator.distance_to_sol') + " ---", 
                                             font=("Segoe UI", 9), fg="#ffffff", bg=_dc_bg, anchor="w")
        self.distance_a_sol_label.grid(row=row, column=0, sticky="w", padx=(10, 20))
        
        self.distance_b_sol_label = tk.Label(results_frame, text=t('distance_calculator.distance_to_sol') + " ---", 
                                             font=("Segoe UI", 9), fg="#ffffff", bg=_dc_bg, anchor="w")
        self.distance_b_sol_label.grid(row=row, column=1, sticky="w", padx=(10, 0))
        
        # Visits count - side by side
        row += 1
        self.distance_a_visits_label = tk.Label(results_frame, text=t('distance_calculator.visits') + " ---", 
                                                font=("Segoe UI", 9), fg="#ffffff", bg=_dc_bg, anchor="w")
        self.distance_a_visits_label.grid(row=row, column=0, sticky="w", padx=(10, 20))
        
        self.distance_b_visits_label = tk.Label(results_frame, text=t('distance_calculator.visits') + " ---", 
                                                font=("Segoe UI", 9), fg="#ffffff", bg=_dc_bg, anchor="w")
        self.distance_b_visits_label.grid(row=row, column=1, sticky="w", padx=(10, 0))
        
        # Coordinates - side by side
        row += 1
        self.distance_a_coords_label = tk.Label(results_frame, text=t('distance_calculator.coordinates') + " ---", 
                                                font=("Segoe UI", 9), fg="#ffffff", bg=_dc_bg, anchor="w")
        self.distance_a_coords_label.grid(row=row, column=0, sticky="w", padx=(10, 20))
        
        self.distance_b_coords_label = tk.Label(results_frame, text=t('distance_calculator.coordinates') + " ---", 
                                                font=("Segoe UI", 9), fg="#ffffff", bg=_dc_bg, anchor="w")
        self.distance_b_coords_label.grid(row=row, column=1, sticky="w", padx=(10, 0))
        
        results_frame.columnconfigure(0, weight=1)
        results_frame.columnconfigure(1, weight=1)
        
        # Auto-calculate on startup (delayed to allow init)
        self.after(1000, self._distance_auto_calculate_on_startup)
    
    def _distance_auto_calculate_on_startup(self):
        """Auto-detect Fleet Carrier on startup (runs in background thread)
        
        Note: Distance calculations and UI updates happen after journal scan completes.
        """
        import threading
        
        def startup_thread():
            try:
                # Auto-detect Fleet Carrier location from journals
                if hasattr(self, 'prospector_panel') and self.prospector_panel.journal_dir:
                    try:
                        self.fc_tracker.set_journal_directory(self.prospector_panel.journal_dir)
                        carrier_system = self.fc_tracker.scan_journals_for_carrier()
                        if carrier_system:
                            self.after(0, lambda: self.distance_fc_system.set(carrier_system))
                            print(f"Auto-detected Fleet Carrier in: {carrier_system}")
                    except Exception as e:
                        print(f"Error auto-detecting FC on startup: {e}")
                
                # Distance updates are triggered after journal scan completes
                # See _process_journals_for_catchup() which calls _update_home_fc_distances
                
            except Exception as e:
                print(f"Error in FC detection on startup: {e}")
        
        # Start background thread
        threading.Thread(target=startup_thread, daemon=True).start()
    
    def _distance_use_current_system(self):
        """Fill System A with current system"""
        try:
            # Get current system from centralized source
            current_system = self.get_current_system()
            
            if current_system:
                self.distance_system_a.set(current_system)
                self._set_status(f"Current system: {current_system}")
                self.distance_status_label.config(text=f"Using current system: {current_system}", fg="#4da6ff")
                # Update Home/FC distances
                self._update_home_fc_distances()
            else:
                from app_utils import centered_message
                centered_message(self, "No Current System", "No current system detected.\n\nMake sure Elite Dangerous is running and you're in a system.")
                self.distance_status_label.config(text="⚠ No current system detected", fg="#ffaa00")
        except Exception as e:
            print(f"Error getting current system: {e}")
            messagebox.showerror("Error", f"Failed to get current system: {e}")
    
    def _distance_use_home(self):
        """Fill System B with home system"""
        home = self.distance_home_system.get().strip()
        if home:
            self.distance_system_b.set(home)
        else:
            from app_utils import centered_message
            centered_message(self, "No Home System", "Please set your home system first in Configuration section below.")
    
    def _distance_use_fc(self):
        """Fill System B with fleet carrier system"""
        fc = self.distance_fc_system.get().strip()
        if fc:
            self.distance_system_b.set(fc)
        else:
            from app_utils import centered_message
            centered_message(self, "No Fleet Carrier", "Please set your fleet carrier location first, or use Auto-detect.")
    
    def _distance_set_home(self, event=None):
        """Save home system to config (called by Enter key)"""
        from config import save_home_system
        home = self.distance_home_system.get().strip()
        if home:
            save_home_system(home)
            self._set_status(f"Home system set to: {home}")
            # Update distances (provides visual confirmation)
            self._update_home_fc_distances()
    
    def _distance_refresh_locations(self):
        """Refresh current system and fleet carrier from journals"""
        try:
            # Set journal directory for tracker
            if hasattr(self, 'prospector_panel') and self.prospector_panel.journal_dir:
                self.fc_tracker.set_journal_directory(self.prospector_panel.journal_dir)
                
                # Show scanning message
                self._set_status("Scanning journals...")
                
                # Run in background thread to avoid UI freeze
                import threading
                def scan_thread():
                    try:
                        results = []
                        
                        # 1. Refresh current system from journals
                        from journal_parser import JournalParser
                        parser = JournalParser(self.prospector_panel.journal_dir)
                        current_system = parser.get_last_known_system()
                        
                        # 2. Scan for fleet carrier
                        carrier_system = self.fc_tracker.scan_journals_for_carrier()
                        carrier_info = self.fc_tracker.get_carrier_info() if carrier_system else None
                        
                        # Update UI on main thread
                        def update_ui():
                            if current_system:
                                # This is a refresh/scan - NOT a visit
                                self.update_current_system(current_system, count_visit=False)
                                results.append(f"System: {current_system}")
                            
                            if carrier_system:
                                self.distance_fc_system.set(carrier_system)
                                carrier_name = carrier_info.get('carrier_name') if carrier_info else None
                                if carrier_name:
                                    results.append(f"FC '{carrier_name}': {carrier_system}")
                                else:
                                    results.append(f"FC: {carrier_system}")
                            
                            # Update distances after detection
                            self._update_home_fc_distances()
                            
                            # Refresh Mining Analytics distance display if it exists
                            if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, '_update_distance_display'):
                                self.prospector_panel._update_distance_display()
                            
                            # Show results
                            if results:
                                self._set_status(" | ".join(results))
                            else:
                                self._set_status("No locations found in journals")
                        
                        self.after(0, update_ui)
                    except Exception as e:
                        self.after(0, lambda: self._set_status(f"Error: {e}"))
                
                threading.Thread(target=scan_thread, daemon=True).start()
            else:
                messagebox.showwarning("No Journal Directory", 
                                     "Journal directory not set. Please configure it in Settings → General Settings → Journal Files.")
        except Exception as e:
            print(f"Error refreshing locations: {e}")
            messagebox.showerror("Error", f"Failed to scan journals: {e}")
    
    def _save_distance_systems(self):
        """Save System A and B to config"""
        try:
            from config import save_distance_calculator_systems
            system_a = self.distance_system_a.get().strip()
            system_b = self.distance_system_b.get().strip()
            save_distance_calculator_systems(system_a, system_b)
        except Exception as e:
            print(f"Error saving distance calculator systems: {e}")
    
    def _calculate_distances(self):
        """Calculate distances between systems - runs in background thread"""
        system_a = self.distance_system_a.get().strip()
        system_b = self.distance_system_b.get().strip()
        
        # Update system info labels with system names on same line
        self.distance_system_a_name.config(text=f"{t('distance_calculator.system_a_info')} {system_a if system_a else '---'}")
        self.distance_system_b_name.config(text=f"{t('distance_calculator.system_b_info')} {system_b if system_b else '---'}")
        
        if not system_a and not system_b:
            self.distance_status_label.config(text="⚠ Please enter at least one system name", fg="#ffaa00")
            return
        
        # Save systems to config
        self._save_distance_systems()
        
        # Show calculating status
        self.distance_status_label.config(text="🔍 Querying EDSM...", fg="#4da6ff")
        self._set_status("Calculating distances...")
        
        # Reset labels
        self.distance_ab_label.config(text=f"➤ {t('distance_calculator.distance')} {system_a or 'A'} ↔ {system_b or 'B'}: ...", fg="#cccccc")
        self.distance_a_sol_label.config(text=t('distance_calculator.distance_to_sol') + " ---", fg="#ffffff")
        self.distance_a_coords_label.config(text=t('distance_calculator.coordinates') + " ---", fg="#ffffff")
        self.distance_b_sol_label.config(text=t('distance_calculator.distance_to_sol') + " ---", fg="#ffffff")
        self.distance_b_coords_label.config(text=t('distance_calculator.coordinates') + " ---", fg="#ffffff")
        
        # Run calculation in background thread
        def _background_calc():
            try:
                # Get system info from EDSM
                sys_a_info = None
                sys_b_info = None
                
                if system_a:
                    sys_a_info = self.distance_calculator.get_system_coordinates(system_a)
                
                if system_b:
                    sys_b_info = self.distance_calculator.get_system_coordinates(system_b)
                
                # Update UI on main thread
                self.after(0, lambda: self._apply_distance_results(system_a, system_b, sys_a_info, sys_b_info))
                    
            except Exception as e:
                self.after(0, lambda: self._show_distance_error(str(e)))
        
        threading.Thread(target=_background_calc, daemon=True).start()
    
    def _apply_distance_results(self, system_a, system_b, sys_a_info, sys_b_info):
        """Apply distance calculation results to UI - called on main thread"""
        try:
            # Show errors if systems not found
            if system_a and not sys_a_info:
                self.distance_a_sol_label.config(text=f"➤ System '{system_a}' not found in EDSM", fg="#ff6666")
                self._set_status(f"System A '{system_a}' not found")
            
            if system_b and not sys_b_info:
                self.distance_b_sol_label.config(text=f"➤ System '{system_b}' not found in EDSM", fg="#ff6666")
                self._set_status(f"System B '{system_b}' not found")
            
            # Calculate distance between A and B
            if sys_a_info and sys_b_info:
                distance_ab = self.distance_calculator.calculate_distance(sys_a_info, sys_b_info)
                if distance_ab is not None:
                    self.distance_ab_label.config(text=f"➤ {t('distance_calculator.distance')} {system_a} ↔ {system_b}: {distance_ab:.2f} LY", fg="#ffcc00")
                else:
                    self.distance_ab_label.config(text=f"➤ {t('distance_calculator.distance')} {system_a} ↔ {system_b}: ---", fg="#ff6666")
            else:
                self.distance_ab_label.config(text=f"➤ {t('distance_calculator.distance')} {system_a or 'A'} ↔ {system_b or 'B'}: ---", fg="#cccccc")
            
            # System A info
            if sys_a_info:
                sol_dist_a, _ = self.distance_calculator.get_distance_to_sol(system_a)
                self.distance_a_sol_label.config(
                    text=f"{t('distance_calculator.distance_to_sol')} {sol_dist_a:.2f} LY" if sol_dist_a is not None else t('distance_calculator.distance_to_sol') + " ---",
                    fg="#ffffff"
                )
                self.distance_a_coords_label.config(
                    text=f"{t('distance_calculator.coordinates')} X: {sys_a_info['x']:.2f}, Y: {sys_a_info['y']:.2f}, Z: {sys_a_info['z']:.2f}",
                    fg="#ffffff"
                )
                # System A visits count
                if hasattr(self, 'distance_a_visits_label') and hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                    try:
                        visit_data = self.cargo_monitor.user_db.is_system_visited(system_a)
                        visits_count = visit_data.get('visit_count', 0) if visit_data else 0
                        self.distance_a_visits_label.config(text=f"{t('distance_calculator.visits')} {visits_count}", fg="#ffffff")
                    except:
                        self.distance_a_visits_label.config(text=t('distance_calculator.visits') + " ---", fg="#ffffff")
            
            # System B info
            if sys_b_info:
                sol_dist_b, _ = self.distance_calculator.get_distance_to_sol(system_b)
                self.distance_b_sol_label.config(
                    text=f"{t('distance_calculator.distance_to_sol')} {sol_dist_b:.2f} LY" if sol_dist_b is not None else t('distance_calculator.distance_to_sol') + " ---",
                    fg="#ffffff"
                )
                self.distance_b_coords_label.config(
                    text=f"{t('distance_calculator.coordinates')} X: {sys_b_info['x']:.2f}, Y: {sys_b_info['y']:.2f}, Z: {sys_b_info['z']:.2f}",
                    fg="#ffffff"
                )
                # System B visits count
                if hasattr(self, 'distance_b_visits_label') and hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                    try:
                        visit_data = self.cargo_monitor.user_db.is_system_visited(system_b)
                        visits_count = visit_data.get('visit_count', 0) if visit_data else 0
                        self.distance_b_visits_label.config(text=f"{t('distance_calculator.visits')} {visits_count}", fg="#ffffff")
                    except:
                        self.distance_b_visits_label.config(text=t('distance_calculator.visits') + " ---", fg="#ffffff")
            
            # Update status based on results
            if sys_a_info and sys_b_info:
                self.distance_status_label.config(text=t('distance_calculator.calculation_complete'), fg="#00ff00")
            elif sys_a_info or sys_b_info:
                self.distance_status_label.config(text="⚠ One system not found", fg="#ffaa00")
            else:
                self.distance_status_label.config(text="✗ Systems not found in EDSM", fg="#ff6666")
            
            # Calculate distances to Home and FC from current position
            self._update_home_fc_distances()
            
            self._set_status("Distance calculation complete")
            
        except Exception as e:
            self._show_distance_error(str(e))
    
    def _show_distance_error(self, error_msg: str):
        """Show distance calculation error - called on main thread"""
        print(f"Error calculating distances: {error_msg}")
        self.distance_status_label.config(text=f"✗ Error: {error_msg[:50]}", fg="#ff6666")
        self._set_status("Distance calculation failed")
    
    def _refresh_visit_count(self, system_name):
        """Refresh the visit count display for a system"""
        if hasattr(self, 'distance_visits_label') and system_name:
            visits_count = 0
            if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db') and self.cargo_monitor.user_db:
                try:
                    visit_data = self.cargo_monitor.user_db.is_system_visited(system_name)
                    if visit_data:
                        visits_count = visit_data.get('visit_count', 0)
                except:
                    pass
            self.distance_visits_label.config(text=f"{t('distance_calculator.visits_label')} {visits_count}")
    
    def _update_home_fc_distances(self):
        """Update distance displays for Home and FC from current system"""
        # Run in background thread to avoid blocking UI during network calls
        def _background_update():
            try:
                current_system = self.distance_current_system.get().strip()
                if not current_system:
                    self.after(0, lambda: self._clear_distance_labels())
                    return
                
                # Calculate distance from current system to Sol
                sol_distance = None
                if hasattr(self, 'current_sol_label'):
                    sol_distance, _ = self.distance_calculator.get_distance_to_sol(current_system)
                
                # Calculate distance to Home
                home_system = self.distance_home_system.get().strip()
                home_distance = None
                home_sol_distance = None
                home_visits = 0
                if home_system:
                    home_distance, home_info, current_info = self.distance_calculator.get_distance_between_systems(
                        current_system, home_system
                    )
                    home_sol_distance, _ = self.distance_calculator.get_distance_to_sol(home_system)
                    
                    if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                        try:
                            visit_data = self.cargo_monitor.user_db.is_system_visited(home_system)
                            home_visits = visit_data.get('visit_count', 0) if visit_data else 0
                        except:
                            pass
                
                # Calculate distance to FC
                fc_system = self.distance_fc_system.get().strip()
                fc_distance = None
                fc_sol_distance = None
                fc_visits = 0
                if fc_system:
                    fc_distance, fc_info, current_info = self.distance_calculator.get_distance_between_systems(
                        current_system, fc_system
                    )
                    fc_sol_distance, _ = self.distance_calculator.get_distance_to_sol(fc_system)
                    
                    if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                        try:
                            visit_data = self.cargo_monitor.user_db.is_system_visited(fc_system)
                            fc_visits = visit_data.get('visit_count', 0) if visit_data else 0
                        except:
                            pass
                
                # Update UI on main thread with all calculated values
                self.after(0, lambda: self._apply_distance_updates(
                    sol_distance, home_distance, home_sol_distance, home_visits,
                    fc_distance, fc_sol_distance, fc_visits
                ))
                
            except Exception as e:
                print(f"Error updating home/FC distances: {e}")
        
        # Start background thread
        threading.Thread(target=_background_update, daemon=True).start()
    
    def _clear_distance_labels(self):
        """Clear all distance labels - called on UI thread"""
        self.distance_to_home_label.config(text="")
        self.home_sol_label.config(text="")
        self.distance_to_fc_label.config(text="")
        self.fc_sol_label.config(text="")
        if hasattr(self, 'current_sol_label'):
            self.current_sol_label.config(text="")
    
    def _apply_distance_updates(self, sol_distance, home_distance, home_sol_distance, home_visits,
                                 fc_distance, fc_sol_distance, fc_visits):
        """Apply distance calculations to UI labels - called on UI thread"""
        try:
            # Update current system Sol distance
            if hasattr(self, 'current_sol_label'):
                if sol_distance is not None:
                    self.current_sol_label.config(text=f"➤ {sol_distance:.2f} LY from Sol", fg="#ffcc00")
                else:
                    self.current_sol_label.config(text="")
            
            # Update Home distances
            if home_distance is not None:
                self.distance_to_home_label.config(text=f"➤ {home_distance:.2f} {t('distance_calculator.from_current')}", fg="#ffcc00")
            else:
                self.distance_to_home_label.config(text="")
            
            if home_sol_distance is not None:
                self.home_sol_label.config(text=f"({t('distance_calculator.sol_distance')} {home_sol_distance:.2f} LY)", fg="#888888")
            else:
                self.home_sol_label.config(text="")
            
            if hasattr(self, 'home_visits_label'):
                if home_visits > 0:
                    self.home_visits_label.config(text=f"{t('distance_calculator.visits_label')} {home_visits}")
                else:
                    self.home_visits_label.config(text="")
            
            # Update FC distances
            if fc_distance is not None:
                self.distance_to_fc_label.config(text=f"➤ {fc_distance:.2f} {t('distance_calculator.from_current')}", fg="#ffcc00")
            else:
                self.distance_to_fc_label.config(text="")
            
            if fc_sol_distance is not None:
                self.fc_sol_label.config(text=f"({t('distance_calculator.sol_distance')} {fc_sol_distance:.2f} LY)", fg="#888888")
            else:
                self.fc_sol_label.config(text="")
            
            if hasattr(self, 'fc_visits_label'):
                if fc_visits > 0:
                    self.fc_visits_label.config(text=f"{t('distance_calculator.visits_label')} {fc_visits}")
                else:
                    self.fc_visits_label.config(text="")
            
            # Notify Mining Session and Ring Finder to update their distance displays
            if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, '_update_distance_display'):
                self.prospector_panel._update_distance_display()
            
            if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, '_update_sol_distance'):
                current_system = self.distance_current_system.get().strip()
                self.ring_finder._update_sol_distance(current_system)
                
        except Exception as e:
            print(f"Error applying distance updates: {e}")
    
    def get_distance_info_text(self) -> str:
        """Get formatted distance info string for display in other tabs
        
        Returns distance info in format: "➤ Sol: X.XX LY | Home: Y.YY LY | Fleet Carrier: Z.ZZ LY"
        This provides a centralized way for Mining Session and Ring Finder to display
        distance information without recalculating.
        """
        try:
            # Extract distances from the Distance Calculator labels
            sol_text = self.current_sol_label.cget("text") if hasattr(self, 'current_sol_label') else ""
            home_text = self.distance_to_home_label.cget("text") if hasattr(self, 'distance_to_home_label') else ""
            fc_text = self.distance_to_fc_label.cget("text") if hasattr(self, 'distance_to_fc_label') else ""
            
            # Parse distances from label text (format: "➤ XX.XX LY from Sol/current")
            sol_ly = "---"
            home_ly = "---"
            fc_ly = "---"
            
            if sol_text and "LY" in sol_text:
                # Extract number from "➤ XX.XX LY from Sol"
                sol_ly = sol_text.split("LY")[0].replace("➤", "").strip()
            
            if home_text and "LY" in home_text:
                # Extract number from "➤ XX.XX LY from current"
                home_ly = home_text.split("LY")[0].replace("➤", "").strip()
            
            if fc_text and "LY" in fc_text:
                # Extract number from "➤ XX.XX LY from current"
                fc_ly = fc_text.split("LY")[0].replace("➤", "").strip()
            
            return f"➤ {t('mining_session.sol')} {sol_ly} LY | {t('mining_session.home')} {home_ly} LY | {t('mining_session.fleet_carrier')} {fc_ly} LY"
            
        except Exception as e:
            return f"➤ {t('mining_session.sol')} --- | {t('mining_session.home')} --- | {t('mining_session.fleet_carrier')} ---"
    
    def _check_edsm_status(self):
        """Check EDSM API status in background and update indicator"""
        def _background_check():
            import requests
            try:
                response = requests.get("https://www.edsm.net/api-v1/system", 
                                       params={"systemName": "Sol", "showCoordinates": 1}, 
                                       timeout=3)
                if response.status_code == 200 and response.text.strip():
                    self.after(0, lambda: self._update_edsm_status("online"))
                elif response.status_code >= 500:
                    # Server errors (500+) = offline
                    self.after(0, lambda: self._update_edsm_status("offline"))
                elif response.status_code >= 400:
                    # Client errors (400+) = slow/error
                    self.after(0, lambda: self._update_edsm_status("error"))
                else:
                    self.after(0, lambda: self._update_edsm_status("error"))
            except (requests.Timeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout):
                # All timeout types = offline (server not responding)
                self.after(0, lambda: self._update_edsm_status("offline"))
            except requests.exceptions.RequestException:
                # Other connection errors = offline
                self.after(0, lambda: self._update_edsm_status("offline"))
            except Exception:
                # Unexpected errors = offline
                self.after(0, lambda: self._update_edsm_status("offline"))
        
        threading.Thread(target=_background_check, daemon=True).start()
    
    def _update_edsm_status(self, status: str):
        """Update EDSM status label - called on UI thread"""
        if not hasattr(self, 'edsm_status_label'):
            return
            
        if status == "online":
            self.edsm_status_label.config(text="🟢 EDSM: Online", fg="#00ff00")
        elif status == "error":
            self.edsm_status_label.config(text="🟡 EDSM: Slow", fg="#ffaa00")
        else:
            self.edsm_status_label.config(text="🔴 EDSM: Offline", fg="#ff4444")
    
    def _check_eddata_status(self):
        """Check EDDATA API status in background and update indicator"""
        def _background_check():
            import requests
            try:
                # Test primary EDDATA API first
                primary_url = "https://api.eddata.dev/v2/system/name/Sol/commodity/name/platinum/nearby/imports?minVolume=1&maxDaysAgo=2&maxDistance=50"
                try:
                    response = requests.get(primary_url, timeout=5)
                    if response.status_code == 200:
                        self.after(0, lambda: self._update_eddata_status("online"))
                        return
                except:
                    pass  # Try fallback
                
                # If primary fails, test fallback Ardent API
                fallback_url = "https://api.ardent-insight.com/v2/system/name/Sol/commodity/name/platinum/nearby/imports?minVolume=1&maxDaysAgo=2&maxDistance=50"
                try:
                    response = requests.get(fallback_url, timeout=5)
                    if response.status_code == 200:
                        # Fallback is working (yellow = using fallback)
                        self.after(0, lambda: self._update_eddata_status("error"))
                        return
                except:
                    pass
                
                # Both failed = offline
                self.after(0, lambda: self._update_eddata_status("offline"))
                
            except Exception:
                self.after(0, lambda: self._update_eddata_status("offline"))
        
        threading.Thread(target=_background_check, daemon=True).start()
    
    def _update_eddata_status(self, status: str):
        """Update EDDATA status labels - called on UI thread"""
        status_text = ""
        status_color = ""
        
        if status == "online":
            status_text = "🟢 EDDATA: Online"
            status_color = "#00ff00"
        elif status == "error":
            status_text = "🟡 EDDATA: Fallback"
            status_color = "#ffaa00"
        else:
            status_text = "🔴 EDDATA: Offline"
            status_color = "#ff4444"
        
        # Update both commodity tab status labels
        if hasattr(self, 'eddata_mining_status_label'):
            self.eddata_mining_status_label.config(text=status_text, fg=status_color)
        if hasattr(self, 'eddata_trade_status_label'):
            self.eddata_trade_status_label.config(text=status_text, fg=status_color)
    
    # ==================== END DISTANCE CALCULATOR ====================

    def _load_selected_preset(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            return
        try:
            with open(self._settings_path(sel), "r", encoding="utf-8") as f:
                data = json.load(f)
            self._apply_mapping(data)
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def _delete_selected(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            return
        from app_utils import centered_askyesno
        if centered_askyesno(self, "Delete preset", f"Delete preset '{sel}'?"):
            try:
                os.remove(self._settings_path(sel))
                self._refresh_preset_list()
                self._set_status(f"Deleted preset '{sel}'.")
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
            self._set_status(f"Duplicated preset '{sel}' - edit to rename.")
            
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
            self._set_status(f"Exported preset to '{dest}'.")
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
            self._set_status(f"Imported preset '{new_name}'. Double-click to load.")
        except Exception as e:
            messagebox.showerror("Import preset failed", str(e))

    def _ask_import_preset_name(self, detected_ship: str, detected_variant: str, original_name: str) -> Optional[str]:
        """Dialog for importing preset - select ship type and build name"""
        # Complete Elite Dangerous ship list (alphabetical)
        ship_types = [
            "Adder",
            "Alliance Challenger", "Alliance Chieftain", "Alliance Crusader",
            "Anaconda",
            "Asp Explorer", "Asp Scout",
            "Beluga Liner",
            "Caspian Explorer",
            "Cobra Mk III", "Cobra Mk IV", "Cobra Mk V",
            "Corsair",
            "Diamondback Explorer", "Diamondback Scout",
            "Dolphin",
            "Eagle Mk II",
            "Federal Assault Ship", "Federal Corvette", "Federal Dropship", "Federal Gunship",
            "Fer-de-Lance",
            "Hauler",
            "Imperial Clipper", "Imperial Courier", "Imperial Cutter", "Imperial Eagle",
            "Keelback",
            "Krait Mk II", "Krait Phantom",
            "Mamba", "Mandalay",
            "Orca",
            "Panther Clipper Mk II",
            "Python", "Python Mk II",
            "Sidewinder Mk I",
            "Type-6 Transporter", "Type-7 Transporter", "Type-8 Transporter",
            "Type-9 Heavy", "Type-10 Defender", "Type-11 Prospector",
            "Viper Mk III", "Viper Mk IV",
            "Vulture",
            "Other"
        ]
        
        dialog = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title(t('dialogs.import_ship_preset'))
        dialog.configure(bg="#1e1e1e")
        dialog.geometry("480x280")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
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
                       fieldbackground="#2d2d2d",
                       background="#2d2d2d",
                       foreground="#ffffff",
                       selectbackground=accent_color,
                       selectforeground=accent_fg)
        style.map("Preset.TCombobox",
                 fieldbackground=[("readonly", "#2d2d2d")],
                 selectbackground=[("readonly", accent_color)],
                 selectforeground=[("readonly", accent_fg)])
        
        # Set app icon
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass
        
        # Center on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        result = None
        
        # Title
        title_label = tk.Label(dialog, text="📥 Import Ship Preset", 
                              bg="#1e1e1e", fg=accent_color, 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=(15, 5))
        
        # Show original filename
        orig_label = tk.Label(dialog, text=f"Original: {original_name}", 
                             bg="#1e1e1e", fg="#888888", 
                             font=("Segoe UI", 9))
        orig_label.pack(pady=(0, 10))
        
        # Ship Type selection
        type_frame = tk.Frame(dialog, bg="#1e1e1e")
        type_frame.pack(fill="x", padx=25, pady=(0, 10))
        
        tk.Label(type_frame, text="Ship Type:", bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10)).pack(side=tk.LEFT)
        
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
                                  state="readonly", width=28, font=("Segoe UI", 10),
                                  style="Preset.TCombobox")
        ship_combo.pack(side=tk.LEFT, padx=(15, 0))
        
        # Build name entry
        name_frame = tk.Frame(dialog, bg="#1e1e1e")
        name_frame.pack(fill="x", padx=25, pady=10)
        
        tk.Label(name_frame, text="Build Name:", bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10)).pack(side=tk.LEFT)
        
        name_entry = tk.Entry(name_frame, font=("Segoe UI", 10), width=30,
                             bg="#2d2d2d", fg="#ffffff", insertbackground=accent_color,
                             selectbackground=accent_color, selectforeground=accent_fg,
                             relief="flat", bd=2)
        name_entry.pack(side=tk.LEFT, padx=(10, 0))
        if detected_variant:
            name_entry.insert(0, detected_variant)
        
        # Preview
        preview_frame = tk.Frame(dialog, bg="#1e1e1e")
        preview_frame.pack(fill="x", padx=25, pady=10)
        
        tk.Label(preview_frame, text="New Name:", bg="#1e1e1e", fg="#888888", 
                font=("Segoe UI", 9)).pack(side=tk.LEFT)
        
        preview_label = tk.Label(preview_frame, text="", bg="#1e1e1e", fg=accent_color, 
                                font=("Segoe UI", 10, "bold"))
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
        btn_frame = tk.Frame(dialog, bg="#1e1e1e")
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
            
        ok_btn = tk.Button(btn_frame, text="📥 Import", command=on_ok,
                          bg=accent_color, fg=accent_fg, font=("Segoe UI", 10, "bold"),
                          activebackground=accent_color, activeforeground=accent_fg,
                          width=10, cursor="hand2")
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text=t('common.cancel'), command=on_cancel,
                              bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10),
                              activebackground="#4a4a4a", activeforeground="#ffffff",
                              width=10, cursor="hand2")
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        
        dialog.deiconify()
        name_entry.focus_set()
        dialog.wait_window()
        return result

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
        # Apply the setting immediately
        try:
            self.wm_attributes("-topmost", enabled)
        except Exception:
            pass

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
            print(f"Error saving announcement preferences: {e}")

    def _on_announcement_change(self, *args) -> None:
        """Called when any announcement setting changes - auto-save to config"""
        self._save_announcement_preferences()

    def _on_stay_on_top_toggle(self, *args) -> None:
        """Called when stay on top checkbox is toggled"""
        enabled = bool(self.stay_on_top.get())
        try:
            self.wm_attributes("-topmost", enabled)
            # Force window to update and become visible to Windows tools
            if enabled:
                self.lift()
                self.focus_force()
            self._save_stay_on_top_preference()
            self._set_status(f"Stay on top {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            print(f"Error setting stay on top: {e}")
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
    
    def switch_to_tab(self, tab_name: str) -> None:
        """Switch to a specific tab by name
        
        Args:
            tab_name: One of 'mining_session', 'hotspots_finder', 'commodity_market', 
                      'distance_calculator', 'voiceattack', 'bookmarks', 'settings', 'about'
        """
        try:
            if not hasattr(self, 'notebook'):
                return
            
            # Map tab names to their indices (based on order added in _build_content_area)
            tab_indices = {
                'mining_session': 0,
                'hotspots_finder': 1,
                'commodity_market': 2,
                'system_finder': 3,
                'distance_calculator': 4,
                'voiceattack': 5,
                'bookmarks': 6,
                'settings': 7,
                'about': 8
            }
            
            if tab_name in tab_indices:
                self.notebook.select(tab_indices[tab_name])
                print(f"[AUTO-TAB] Switched to tab: {tab_name}")
        except Exception as e:
            print(f"[AUTO-TAB] Error switching to tab {tab_name}: {e}")
    
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
        """Test connection to API server"""
        from api_uploader import APIUploader
        try:
            # Save settings first
            self._save_api_settings()
            
            # Test connection
            uploader = APIUploader()
            success, message = uploader.test_connection()
            
            from app_utils import centered_message
            if success:
                centered_message(self, "Connection Test", f"✓ {message}")
            else:
                centered_message(self, "Connection Test", f"✗ {message}")
        except Exception as e:
            from app_utils import centered_message
            centered_message(self, "Connection Test", f"Error: {e}")
    
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
            except Exception as e:
                log.error(f"Error reading NavRoute.json: {e}")
            return
        
        # Process Market.json for EDDN sending
        if file_name == 'market.json' and hasattr(self, 'market_handler'):
            self.market_handler.process_market_file(file_path)
        
        # Process journal files for LoadGame and location tracking
        elif file_name.startswith('journal.') and file_name.endswith('.log') and hasattr(self, 'market_handler'):
            try:
                # Read last line of journal to get latest event
                with open(file_path, 'r', encoding='utf-8') as f:
                    # Seek to end and read backwards to get last complete line
                    f.seek(0, 2)  # Go to end
                    file_size = f.tell()
                    if file_size > 0:
                        # Read last 2KB to get recent events
                        f.seek(max(0, file_size - 2048))
                        lines = f.readlines()
                        
                        # Get the very last event first for immediate response
                        last_event = None
                        for line in reversed(lines):
                            if line.strip():
                                try:
                                    last_event = json.loads(line)
                                    break
                                except json.JSONDecodeError:
                                    continue
                        
                        # Process the most recent event immediately for route tracking
                        if last_event:
                            event_type = last_event.get('event')
                            log.debug(f"Latest journal event: {event_type}")
                            if event_type == 'FSDTarget':
                                jumps_remaining = last_event.get('RemainingJumpsInRoute')
                                if jumps_remaining is not None:
                                    self._write_jumps_left(jumps_remaining)
                                    log.info(f"Route update: {jumps_remaining} jumps remaining")
                                    print(f"[jumpsleft] Updated to {jumps_remaining}")
                            elif event_type in ['NavRouteClear', 'Docked', 'Touchdown']:
                                self._write_jumps_left(0)
                                log.info(f"Route cleared/completed: {event_type}")
                                print(f"[jumpsleft] Reset to 0 ({event_type})")
                        
                        # Process last few events for EDDN
                        for line in lines[-10:]:  # Last 10 events
                            if line.strip():
                                try:
                                    event = json.loads(line)
                                    self.market_handler.process_journal_event(event)
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                log.error(f"Error processing journal for EDDN: {e}")

    # ---------- Journal folder preference handling ----------
    def _import_journal_history(self):
        """Import journal history from existing journal files"""
        try:
            journal_dir = self.cargo_monitor.journal_dir
            if not os.path.exists(journal_dir):
                messagebox.showwarning("Invalid Path", "Journal directory not found.")
                return
                
            # Create progress window
            progress = tk.Toplevel(self)
            progress.title(t('dialogs.importing_journal'))
            progress.geometry("400x200")
            progress.resizable(False, False)
            progress.configure(bg="#1e1e1e")
            progress.transient(self)
            progress.grab_set()
            
            # Position relative to main window
            self.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - 200
            y = self.winfo_y() + (self.winfo_height() // 2) - 100
            progress.geometry(f"400x200+{x}+{y}")
            
            # Set icon
            set_window_icon(progress)
            
            tk.Label(progress, text="Processing journal files...", bg="#1e1e1e", fg="#ffffff").pack(pady=20)
            progress_var = tk.StringVar(value="Starting...")
            progress_label = tk.Label(progress, textvariable=progress_var, bg="#1e1e1e", fg="#cccccc")
            progress_label.pack(pady=10)
            
            def process_files():
                # Use JournalParser class which already handles everything correctly
                from journal_parser import JournalParser
                
                # Get user_db from cargo_monitor which has it
                user_db = self.cargo_monitor.user_db if hasattr(self.cargo_monitor, 'user_db') else self.user_db
                parser = JournalParser(journal_dir, user_db)
                
                # Progress callback to update UI
                def progress_callback(current_file, total_files, stats):
                    progress_var.set(f"Processing file {current_file}/{total_files}...")
                    progress.update()
                
                # Parse all journals
                stats = parser.parse_all_journals(progress_callback)
                
                # Close progress window
                progress.destroy()
                
                # Show results
                from app_utils import centered_message
                centered_message(self, "Import Complete",
                                 f"Successfully imported:\n"
                                 f"• {stats['systems_visited']} visited systems\n"
                                 f"• {stats['hotspots_found']} hotspots\n"
                                 f"• Processed {stats['files_processed']} journal files")
            
            # Run in thread to keep UI responsive
            threading.Thread(target=process_files, daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("Import Error", f"Error importing journal history: {e}")
    
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
                self.prospector_panel._jrnl_path = None
                self.prospector_panel._jrnl_pos = 0
            
            # Update cargo_monitor to keep them synchronized
            if hasattr(self, 'cargo_monitor'):
                self.cargo_monitor.journal_dir = sel
                # Update dependent paths in cargo_monitor
                self.cargo_monitor.cargo_json_path = os.path.join(sel, "Cargo.json")
                self.cargo_monitor.status_json_path = os.path.join(sel, "Status.json")
            
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
        dialog.title(t('dialogs.import_journal_question'))
        dialog.configure(bg="#2c3e50")
        dialog.geometry("550x350")  # Increased size to accommodate long paths
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Set app icon (consistent across app)
        set_window_icon(dialog)
        
        # CENTER ON PARENT (SAME MONITOR!)
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Title label
        title_label = tk.Label(
            dialog, 
            text="Import Journal History?",
            bg="#2c3e50", 
            fg="#ecf0f1", 
            font=("Segoe UI", 12, "bold")
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
            font=("Segoe UI", 10),
            justify="center",
            wraplength=500  # Wrap long paths
        )
        info_label.pack(pady=10)
        
        # Checkbox for "don't ask again"
        dont_ask_var = tk.IntVar(value=0)
        checkbox = tk.Checkbutton(
            dialog,
            text="Don't ask me again when changing paths",
            variable=dont_ask_var,
            bg="#2c3e50",
            fg="#bdc3c7",
            selectcolor="#34495e",
            activebackground="#2c3e50",
            activeforeground="#ecf0f1",
            font=("Segoe UI", 9)
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
            font=("Segoe UI", 10, "bold"),
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
            font=("Segoe UI", 10),
            width=12,
            height=1,
            relief=tk.FLAT,
            cursor="hand2"
        )
        skip_btn.pack(side=tk.LEFT, padx=10)
        
        # Bind Escape key to skip
        dialog.bind('<Escape>', lambda e: on_skip())
        
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
            self._set_status(f"Error updating screenshots folder: {e}")

    # ---------- Text overlay preference handling ----------
    def _load_text_overlay_preference(self) -> None:
        """Load text overlay enabled state and transparency from config"""
        cfg = _load_cfg()
        enabled = cfg.get("text_overlay_enabled", False)  # Default to disabled
        transparency = cfg.get("text_overlay_transparency", 90)  # Default to 90%
        color = cfg.get("text_overlay_color", "White")  # Default to white
        size = cfg.get("text_overlay_size", "Normal")  # Default to normal size
        duration = cfg.get("text_overlay_duration", 7)  # Default to 7 seconds
        overlay_mode = cfg.get("overlay_mode", "standard")  # Default to standard mode
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

    def _on_text_overlay_toggle(self, *args) -> None:
        """Called when text overlay checkbox is toggled"""
        enabled = bool(self.text_overlay_enabled.get())
        self.text_overlay.set_enabled(enabled)
        self._save_text_overlay_preference()
        
    def _on_transparency_change(self, *args) -> None:
        """Called when brightness slider is changed"""
        transparency = int(self.text_overlay_transparency.get())
        self.text_overlay.set_transparency(transparency)
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled to test brightness
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(f"Text Brightness: {transparency}%")

    def _on_color_change(self, *args) -> None:
        """Called when color selection is changed"""
        color_name = self.text_overlay_color.get()
        color_hex = self.color_options.get(color_name, "#FFFFFF")
        self.text_overlay.set_color(color_hex)
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
        """Update the color menu button to show the selected color"""
        try:
            color_name = self.text_overlay_color.get()
            color_hex = self.color_options.get(color_name, "#FFFFFF")
            
            # For very light colors, use black text for readability on the button
            if color_name in ["White", "Yellow", "Light Gray", "Light Green", "Light Blue", "Cyan"]:
                text_color = "#000000"
            else:
                text_color = "#000000"
            
            # Update the option menu button appearance
            self.color_menu.configure(
                bg=color_hex,
                fg=text_color,
                activebackground=color_hex,
                activeforeground=text_color
            )
        except Exception as e:
            print(f"Error updating color menu display: {e}")

    # ---------- Cargo Monitor Methods ----------
    def _load_cargo_preferences(self) -> None:
        """Load cargo monitor preferences from config"""
        cfg = _load_cfg()
        self.cargo_enabled.set(cfg.get("cargo_enabled", False))
        self.cargo_display_mode.set(cfg.get("cargo_display_mode", "Progress Bar"))
        self.cargo_position.set(cfg.get("cargo_position", "Upper Right"))
        self.cargo_max_capacity.set(cfg.get("cargo_max_capacity", 200))
        self.cargo_transparency.set(cfg.get("cargo_transparency", 90))
        self.cargo_show_in_overlay.set(cfg.get("cargo_show_in_overlay", False))
    
    def _save_cargo_preferences(self) -> None:
        """Save cargo monitor preferences to config"""
        from config import update_config_values
        updates = {
            "cargo_enabled": bool(self.cargo_enabled.get()),
            "cargo_display_mode": str(self.cargo_display_mode.get()),
            "cargo_position": str(self.cargo_position.get()),
            "cargo_max_capacity": int(self.cargo_max_capacity.get()),
            "cargo_transparency": int(self.cargo_transparency.get()),
            "cargo_show_in_overlay": bool(self.cargo_show_in_overlay.get())
        }
        update_config_values(updates)
    
    def _on_cargo_toggle(self, *args) -> None:
        """Called when cargo monitor checkbox is toggled"""
        enabled = bool(self.cargo_enabled.get())
        if enabled:
            self.cargo_monitor.show()
        else:
            self.cargo_monitor.hide()
        self._save_cargo_preferences()
    
    def _on_cargo_display_change(self, *args) -> None:
        """Called when cargo display mode is changed"""
        mode_name = self.cargo_display_mode.get()
        mode_map = {"Progress Bar": "progress", "Detailed List": "detailed", "Compact": "compact"}
        mode = mode_map.get(mode_name, "progress")
        self.cargo_monitor.set_display_mode(mode)
        self._save_cargo_preferences()
    
    def _on_cargo_position_change(self, *args) -> None:
        """Called when cargo position is changed"""
        position_name = self.cargo_position.get()
        position_map = {
            "Upper Right": "upper_right",
            "Upper Left": "upper_left", 
            "Lower Right": "lower_right",
            "Lower Left": "lower_left",
            "Custom": "custom"
        }
        position = position_map.get(position_name, "upper_right")
        self.cargo_monitor.set_position(position)
        self._save_cargo_preferences()
    
    def _on_cargo_capacity_change(self, *args) -> None:
        """Called when cargo capacity is changed manually in UI"""
        capacity = int(self.cargo_max_capacity.get())
        self.cargo_monitor.set_max_cargo(capacity)
        self._save_cargo_preferences()
    
    def _on_cargo_capacity_detected(self, detected_capacity: int) -> None:
        """Called when CargoMonitor detects cargo capacity from Elite Dangerous"""
        current_capacity = int(self.cargo_max_capacity.get())
        if detected_capacity != current_capacity and detected_capacity > 0:
            # Update the UI setting to match the detected capacity
            self.cargo_max_capacity.set(detected_capacity)
            # Save the detected capacity to config
            self._save_cargo_preferences()
            print(f"🔄 Auto-updated cargo capacity: {current_capacity}t → {detected_capacity}t")
    
    def _on_ship_info_changed(self) -> None:
        """Called when CargoMonitor detects ship info change (LoadGame/Loadout events)"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel._update_ship_info_display()
    
    def _on_cargo_transparency_change(self, *args) -> None:
        """Called when cargo transparency is changed"""
        transparency = int(self.cargo_transparency.get())
        self.cargo_monitor.set_transparency(transparency)
        self._save_cargo_preferences()

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
                    
                # Show window after geometry is set
                self.deiconify()
            except Exception:
                # If saved geometry fails, center on screen with default size
                self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}")
                self.update_idletasks()
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                x = (screen_width - DEFAULT_WIDTH) // 2
                y = (screen_height - DEFAULT_HEIGHT) // 2
                self.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+{x}+{y}")
                self.deiconify()
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
            
            # Show window after geometry is set
            self.deiconify()
        
        # After window shown, ensure no input selection remains and focus a neutral button
        try:
            self.after(150, lambda: self.import_btn.focus_set() if hasattr(self, 'import_btn') else None)
            self.after(150, lambda: (self.ring_finder.system_entry.selection_clear() if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_entry') else None))
            self.after(150, lambda: (self.sysfinder_ref_entry.selection_clear() if hasattr(self, 'sysfinder_ref_entry') else None))
            self.after(150, lambda: (self.distance_current_display.selection_clear() if hasattr(self, 'distance_current_display') else None))
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
            
            # Run database migrations
            self.after(500, self._run_database_migrations)
                
        except Exception as e:
            log.error(f"Config migration check failed: {e}", exc_info=True)
            # Continue startup even if migration fails

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
                    print("[MIGRATION v4.82] ✓ Fixed 'Metalic' → 'Metallic' typo in database")
                else:
                    log.warning("[MIGRATION] 'Metalic' typo fix failed")
            else:
                log.info("[MIGRATION] 'Metalic' typo fix not needed or already applied")
            
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
                font=("Segoe UI", 11, "bold")
            ).pack(pady=(0, 15))
            
            # Status label
            status_var = tk.StringVar(value="Initializing...")
            ttk.Label(
                frame,
                textvariable=status_var,
                font=("Segoe UI", 9)
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

    def _toggle_theme(self) -> None:
        """Toggle between Elite Orange and Dark Gray themes"""
        from config import save_theme
        from app_utils import get_app_icon_path
        import tkinter as tk
        from tkinter import ttk
        
        # Remember old theme for cancel
        old_theme = self.current_theme
        
        # Toggle theme
        if self.current_theme == "elite_orange":
            new_theme = "dark_gray"
            theme_name = t('dialogs.theme_dark_gray')
        else:
            new_theme = "elite_orange"
            theme_name = t('dialogs.theme_elite_orange')
        
        # Save new theme
        save_theme(new_theme)
        
        # Create custom centered dialog
        dialog = tk.Toplevel(self)
        dialog.title(t('dialogs.theme_changed'))
        dialog.transient(self)
        dialog.grab_set()
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
        
        # Dialog content
        frame = ttk.Frame(dialog, padding=20)
        frame.pack(fill="both", expand=True)
        
        # Show theme change message with OK button
        ttk.Label(frame, text=f"{t('dialogs.theme_changed_to')} {theme_name}.", 
                  font=("Segoe UI", 10, "bold")).pack(pady=(0, 5))
        ttk.Label(frame, text=t('settings.restart_message'),
                  font=("Segoe UI", 9)).pack(pady=(0, 15))
        
        # Button frame
        btn_frame = ttk.Frame(frame)
        btn_frame.pack()
        
        def on_ok():
            dialog.destroy()
        
        def on_cancel():
            # Revert theme change
            save_theme(old_theme)
            dialog.destroy()
        
        ok_btn = ttk.Button(btn_frame, text=t('common.ok'), command=on_ok, width=10)
        ok_btn.pack(side="left", padx=(0, 10))
        cancel_btn = ttk.Button(btn_frame, text=t('common.cancel'), command=on_cancel, width=10)
        cancel_btn.pack(side="left")
        ok_btn.focus_set()
        dialog.bind("<Return>", lambda e: on_ok())
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
                    print(f"Error loading flag image {filename}: {e}")
        
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
                font=("Segoe UI", 9, "bold"),
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
        def on_enter_flag(e):
            self._current_lang_label.config(bg="#2a2a2a")
        def on_leave_flag(e):
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
            font=("Segoe UI", 8),
            bg=_vbtn_bg,
            fg=_vbtn_fg,
            cursor="hand2",
            padx=4
        )
        self._version_label.pack(side="left", padx=(8, 0))
        
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
        dialog.title(t('tabs.about'))
        dialog.configure(bg=_about_bg)
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
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
                tk.Label(main_frame, text="EliteMining", font=("Segoe UI", 16, "bold"), 
                         fg="#ffcc00", bg=_about_bg).pack()
        except Exception:
            tk.Label(main_frame, text="EliteMining", font=("Segoe UI", 16, "bold"), 
                     fg="#ffcc00", bg=_about_bg).pack()
        
        # Version
        tk.Label(main_frame, text=f"Version {__version__}", font=("Segoe UI", 10), 
                 fg="#888888", bg=_about_bg).pack(pady=(0, 10))
        
        # Description
        tk.Label(main_frame, text=t('about.description'), 
                 font=("Segoe UI", 10), fg="#e0e0e0", bg=_about_bg).pack(pady=(0, 10))
        
        # Separator
        tk.Frame(main_frame, height=1, bg="#444444", width=350).pack(pady=8)
        
        # Copyright and license
        tk.Label(main_frame, text=t('about.copyright'), 
                 font=("Segoe UI", 9), fg="#e0e0e0", bg=_about_bg).pack()
        tk.Label(main_frame, text=t('about.license'), 
                 font=("Segoe UI", 8), fg="#888888", bg=_about_bg).pack()
        
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
                           padx=8, pady=2, font=("Segoe UI", 8), cursor="hand2")
            btn.pack(side="left", padx=3)
        
        # Row 2: Docs, Report Bug
        links_frame2 = tk.Frame(main_frame, bg=_about_bg)
        links_frame2.pack(pady=(4, 8))
        
        links_row2 = [
            (t('about.documentation'), "https://github.com/Viper-Dude/EliteMining#readme"),
            (t('about.report_bug'), "https://github.com/Viper-Dude/EliteMining/issues/new"),
        ]
        
        for label, url in links_row2:
            btn = tk.Button(links_frame2, text=label, 
                           command=lambda u=url: open_link(u),
                           bg=_btn_bg, fg=_btn_fg, activebackground=_btn_active_bg,
                           activeforeground=_btn_active_fg, relief="ridge", bd=1, 
                           padx=8, pady=2, font=("Segoe UI", 8), cursor="hand2")
            btn.pack(side="left", padx=3)
        
        # Separator
        tk.Frame(main_frame, height=1, bg="#444444", width=350).pack(pady=8)
        
        # Credits (compact)
        credits_text = "Credits: EliteVA (Somfic) • Ardent API (Iain Collins) • EDData API (gOOvER | CMDR Shyvin) • EDCD/EDDN"
        tk.Label(main_frame, text=credits_text, font=("Segoe UI", 8), 
                 fg="#888888", bg=_about_bg, wraplength=380).pack(pady=(0, 10))
        
        # Support/Donate row
        support_frame = tk.Frame(main_frame, bg=_about_bg)
        support_frame.pack(pady=(5, 0))
        
        tk.Label(support_frame, text="☕ " + t('about.donation_text')[:50] + "...", 
                 font=("Segoe UI", 8, "italic"), fg="#aaaaaa", bg=_about_bg).pack(side="left")
        
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
                paypal_btn.pack(side="left", padx=(10, 0))
                paypal_btn.bind("<Button-1>", lambda e: webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=NZQTA4TGPDSC6"))
            else:
                raise FileNotFoundError("PayPal image not found")
        except Exception:
            # Fallback to text button
            paypal_btn = tk.Button(support_frame, text="PayPal", 
                                  command=lambda: webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=NZQTA4TGPDSC6"),
                                  bg="#0070ba", fg="#ffffff", activebackground="#0060aa",
                                  relief="flat", bd=0, padx=8, pady=1, font=("Segoe UI", 8), cursor="hand2")
            paypal_btn.pack(side="left", padx=(10, 0))
        
        # Close button
        close_btn = tk.Button(main_frame, text=t('common.close'), 
                             command=dialog.destroy,
                             bg=_btn_bg, fg=_btn_fg, activebackground=_btn_active_bg,
                             activeforeground=_btn_active_fg, relief="ridge", bd=1, 
                             padx=20, pady=3, font=("Segoe UI", 9), cursor="hand2")
        close_btn.pack(pady=(15, 0))
        
        # Center on parent - IMPORTANT: Always center dialogs on parent window!
        dialog.update_idletasks()
        self._center_dialog_on_parent(dialog)
        
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
        # Force geometry update to get accurate dimensions
        dialog.update()
        
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
        menu = tk.Menu(self, tearoff=0, bg="#2a2a2a", fg="#ffffff", 
                      activebackground="#4a4a4a", activeforeground="#ffffff",
                      font=("Segoe UI", 10))
        
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
        """Change language and prompt for restart with Cancel option"""
        from localization import get_language
        from app_utils import get_app_icon_path
        from config import load_theme
        
        # Don't do anything if same language
        old_lang = get_language()
        if lang_code == old_lang:
            return
        
        # Save old flag image reference
        old_image = self._flag_images.get(old_lang)
        
        # Save to config
        try:
            cfg = _load_cfg()
            cfg['language'] = lang_code
            _save_cfg(cfg)
        except Exception as e:
            print(f"Error saving language setting: {e}")
            return
        
        # Update the flag display with new image
        new_image = self._flag_images.get(lang_code)
        if new_image:
            self._current_lang_label.config(image=new_image)
            self._current_lang_label.image = new_image
        else:
            self._current_lang_label.config(text=lang_code.upper())
        
        # Get theme colors
        theme = load_theme()
        if theme == "elite_orange":
            bg_color = "#1e1e1e"
            fg_color = "#ff9800"
        else:
            bg_color = "#1e1e1e"
            fg_color = "#e6e6e6"
        
        # Create dialog with OK and Cancel
        dialog = tk.Toplevel(self)
        dialog.withdraw()
        dialog.title(t('settings.restart_required'))
        dialog.resizable(False, False)
        dialog.configure(bg=bg_color)
        dialog.transient(self)
        
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except:
            pass
        
        frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=20)
        frame.pack(fill="both", expand=True)
        
        tk.Label(frame, text=t('dialogs.language_changed'), 
                font=("Segoe UI", 10, "bold"), bg=bg_color, fg=fg_color).pack(pady=(0, 5))
        tk.Label(frame, text=t('settings.restart_message'),
                font=("Segoe UI", 9), bg=bg_color, fg=fg_color).pack(pady=(0, 15))
        
        btn_frame = tk.Frame(frame, bg=bg_color)
        btn_frame.pack()
        
        def on_ok():
            dialog.destroy()
        
        def on_cancel():
            # Revert language change
            try:
                cfg = _load_cfg()
                cfg['language'] = old_lang
                _save_cfg(cfg)
            except:
                pass
            # Revert flag display
            if old_image:
                self._current_lang_label.config(image=old_image)
                self._current_lang_label.image = old_image
            else:
                self._current_lang_label.config(text=old_lang.upper())
            dialog.destroy()
        
        ok_btn = tk.Button(btn_frame, text=t('common.ok'), width=10, command=on_ok,
                          bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10),
                          activebackground="#4a4a4a", activeforeground="#ffffff", cursor="hand2")
        ok_btn.pack(side="left", padx=(0, 10))
        cancel_btn = tk.Button(btn_frame, text=t('common.cancel'), width=10, command=on_cancel,
                              bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10),
                              activebackground="#4a4a4a", activeforeground="#ffffff", cursor="hand2")
        cancel_btn.pack(side="left")
        
        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())
        
        # Center on parent
        dialog.update_idletasks()
        dialog_width = dialog.winfo_reqwidth()
        dialog_height = dialog.winfo_reqheight()
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()
        x = main_x + (main_width - dialog_width) // 2
        y = main_y + (main_height - dialog_height) // 2
        dialog.geometry(f"+{x}+{y}")
        
        dialog.deiconify()
        dialog.grab_set()
        ok_btn.focus_set()
        dialog.wait_window()

    def _restart_app(self) -> None:
        """Restart the application - shows message for frozen executables"""
        import sys
        import os
        import subprocess
        from tkinter import messagebox
        
        # Save window geometry before restart
        try:
            from config import save_window_geometry
            is_zoomed = self.state() == "zoomed"
            if is_zoomed:
                self.state("normal")
                self.update_idletasks()
            geometry = self.geometry()
            save_window_geometry({"geometry": geometry, "zoomed": is_zoomed})
        except Exception as e:
            print(f"Error saving window geometry before restart: {e}")
        
        # Save any pending data before restart
        try:
            if hasattr(self, 'prospector_panel') and self.prospector_panel.session_active:
                self.prospector_panel._session_stop()
        except Exception as e:
            print(f"Error saving session before restart: {e}")
        
        # Get the executable path
        executable = sys.executable
        
        if getattr(sys, 'frozen', False):
            # For frozen executables, show restart message
            messagebox.showinfo(
                "Restart Required",
                "Please restart EliteMining to apply changes.\n\n"
                "The application will now close."
            )
        else:
            # Running from Python script - direct restart works fine
            script = os.path.abspath(sys.argv[0])
            subprocess.Popen([executable, script])
        
        # Close the current window and exit cleanly
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
        dialog.title(t('dialogs.session_active_title'))
        dialog.transient(self)
        dialog.grab_set()
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
            font=("Segoe UI", 24),
            bg=bg_color,
            fg=warning_color
        ).pack(side="left", padx=(0, 15))
        
        # Message text
        msg_text_frame = tk.Frame(msg_frame, bg=bg_color)
        msg_text_frame.pack(side="left", fill="x", expand=True)
        
        tk.Label(
            msg_text_frame,
            text=t('dialogs.session_active_message'),
            font=("Segoe UI", 11, "bold"),
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
                font=("Segoe UI", 9),
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
        
        # Focus yes button
        yes_btn.focus_set()
        
        # Wait for dialog to close
        dialog.wait_window()
        
        return result[0] if result[0] else "cancel"

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
        
        try:
            is_zoomed = (self.state() == "zoomed")
            if is_zoomed:
                self.state("normal")
                self.update_idletasks()
            geom = self.geometry()
            save_window_geometry({"geometry": geom, "zoomed": is_zoomed})
        except Exception:
            pass
        
        # Save marketplace filter settings
        try:
            cfg = _load_cfg()
            cfg['marketplace_large_pad_only'] = self.marketplace_large_pad_only.get()
            cfg['marketplace_exclude_carriers'] = self.marketplace_exclude_carriers.get()
            _save_cfg(cfg)
        except Exception:
            pass
        
        # Clean up text overlay
        if hasattr(self, 'text_overlay'):
            self.text_overlay.destroy()
            
        # Clean up cargo monitor with enhanced resource management
        if hasattr(self, 'cargo_monitor'):
            self.cargo_monitor.hide()
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
            
        self.destroy()

    def _setup_announcement_tracing(self):
        """Set up tracing for announcement variables after loading is complete"""
        for var in self.announcement_vars.values():
            var.trace('w', self._on_announcement_change)  # Save to config.json
            var.trace('w', lambda *args: self._save_prospector_settings())
        
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
            var.trace('w', lambda *args: self._save_prospector_settings())

    def _save_prospector_settings(self):
        """Save prospector settings when announcement checkboxes change"""
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel._save_last_material_settings()

    # ---------- Backup and Restore functionality ----------
    def _show_backup_dialog(self) -> None:
        """Show backup dialog with options to select what to backup"""
        try:
            dialog = tk.Toplevel(self)
            dialog.title(t('dialogs.backup_title'))
            dialog.geometry("450x600")
            dialog.resizable(True, True)
            dialog.minsize(450, 600)
            dialog.configure(bg="#1e1e1e")
            dialog.transient(self)
            dialog.grab_set()
            
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
            
            # Center on parent
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
            # Title
            title_label = tk.Label(dialog, text="📦 " + t('dialogs.backup_title'), 
                                 font=("Segoe UI", 14, "bold"),
                                 bg="#1e1e1e", fg="#ff9800")
            title_label.pack(pady=15)
            
            # Instructions
            inst_label = tk.Label(dialog, text=t('dialogs.backup_instructions'),
                                font=("Segoe UI", 10),
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
            
            # All checkbox
            all_cb = tk.Checkbutton(options_frame, text="📂 " + t('dialogs.backup_everything'),
                                  variable=backup_all,
                                  command=on_all_change,
                                  bg="#1e1e1e", fg="#ffffff",
                                  selectcolor="#2a2a2a",
                                  activebackground="#2a2a2a",
                                  activeforeground="#ffffff",
                                  font=("Segoe UI", 10, "bold"))
            all_cb.pack(anchor="w", pady=5)
            
            # Separator
            sep = tk.Frame(options_frame, height=1, bg="#ff9800")
            sep.pack(fill="x", pady=10)
            
            # Individual checkboxes
            presets_cb = tk.Checkbutton(options_frame, text="⚙️ " + t('dialogs.ship_presets'),
                                      variable=backup_presets,
                                      bg="#1e1e1e", fg="#ffffff",
                                      selectcolor="#2a2a2a",
                                      activebackground="#2a2a2a",
                                      activeforeground="#ffffff",
                                      font=("Segoe UI", 10))
            presets_cb.pack(anchor="w", pady=2)
            
            reports_cb = tk.Checkbutton(options_frame, text="📊 " + t('dialogs.mining_reports'),
                                      variable=backup_reports,
                                      bg="#1e1e1e", fg="#ffffff",
                                      selectcolor="#2a2a2a",
                                      activebackground="#2a2a2a",
                                      activeforeground="#ffffff",
                                      font=("Segoe UI", 10))
            reports_cb.pack(anchor="w", pady=2)
            
            bookmarks_cb = tk.Checkbutton(options_frame, text="🔖 " + t('dialogs.mining_bookmarks'),
                                        variable=backup_bookmarks,
                                        bg="#1e1e1e", fg="#ffffff",
                                        selectcolor="#2a2a2a",
                                        activebackground="#2a2a2a",
                                        activeforeground="#ffffff",
                                        font=("Segoe UI", 10))
            bookmarks_cb.pack(anchor="w", pady=2)
            
            va_profile_cb = tk.Checkbutton(options_frame, text="🎤 " + t('dialogs.voiceattack_profile'),
                                         variable=backup_va_profile,
                                         bg="#1e1e1e", fg="#ffffff",
                                         selectcolor="#2a2a2a",
                                         activebackground="#2a2a2a",
                                         activeforeground="#ffffff",
                                         font=("Segoe UI", 10))
            va_profile_cb.pack(anchor="w", pady=2)
            
            userdb_cb = tk.Checkbutton(options_frame, text="💾 " + t('dialogs.user_database'),
                                       variable=backup_userdb,
                                       bg="#1e1e1e", fg="#ffffff",
                                       selectcolor="#2a2a2a",
                                       activebackground="#2a2a2a",
                                       activeforeground="#ffffff",
                                       font=("Segoe UI", 10))
            userdb_cb.pack(anchor="w", pady=2)
            
            journals_cb = tk.Checkbutton(options_frame, text="📝 " + t('dialogs.journal_files'),
                                        variable=backup_journals,
                                        bg="#1e1e1e", fg="#ffffff",
                                        selectcolor="#2a2a2a",
                                        activebackground="#2a2a2a",
                                        activeforeground="#ffffff",
                                        font=("Segoe UI", 10))
            journals_cb.pack(anchor="w", pady=2)
            
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
                
                if not (include_presets or include_reports or include_bookmarks or include_va_profile or include_userdb or include_journals):
                    messagebox.showwarning(t('dialogs.no_selection'), t('dialogs.no_selection_msg'))
                    return
                
                dialog.destroy()
                self._create_backup(include_presets, include_reports, include_bookmarks, include_va_profile, include_userdb, include_journals)
            
            def on_cancel():
                dialog.destroy()
            
            create_btn = tk.Button(btn_frame, text=t('dialogs.create_backup'), command=on_create_backup,
                                 bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
                                 width=15, cursor="hand2")
            create_btn.pack(side=tk.LEFT, padx=5)
            
            cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel,
                                 bg="#e74c3c", fg="white", font=("Segoe UI", 10, "bold"),
                                 width=15, cursor="hand2")
            cancel_btn.pack(side=tk.LEFT, padx=5)
            
            # Bind escape key
            dialog.bind('<Escape>', lambda e: on_cancel())
            
            dialog.wait_window()
            
        except Exception as e:
            messagebox.showerror("Backup Dialog Error", f"Failed to show backup dialog: {str(e)}")

    def _create_backup(self, include_presets: bool, include_reports: bool, include_bookmarks: bool, include_va_profile: bool, include_userdb: bool = False, include_journals: bool = False) -> None:
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
            
            if len(parts) == 6:
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
                        project_root = os.path.dirname(os.path.dirname(app_data_dir))
                        profile_pattern = os.path.join(project_root, "EliteMining v*-Profile.vap")
                        profile_files = glob.glob(profile_pattern)
                        
                        if profile_files:
                            va_profile_path = profile_files[0]
                        else:
                            # Fallback
                            old_path = os.path.join(project_root, "EliteMining-Profile.vap")
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
                        zipf.write(userdb_path, "data/user_data.db")
                
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
                        "journal_files": include_journals
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
                    
                    if not (has_presets or has_reports or has_bookmarks or has_va_profile or has_userdb or has_journals):
                        messagebox.showerror(t('dialogs.invalid_backup'), t('dialogs.invalid_backup_msg'))
                        return
                    
                    self._show_restore_options_dialog(backup_path, has_presets, has_reports, has_bookmarks, has_va_profile, has_userdb, has_journals, manifest)
                    
            except zipfile.BadZipFile:
                messagebox.showerror(t('dialogs.invalid_file'), t('dialogs.invalid_zip_msg'))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read backup file: {str(e)}")
                
        except Exception as e:
            messagebox.showerror("Restore Dialog Error", f"Failed to show restore dialog: {str(e)}")

    def _show_restore_options_dialog(self, backup_path: str, has_presets: bool, has_reports: bool, 
                                   has_bookmarks: bool, has_va_profile: bool, has_userdb: bool = False, has_journals: bool = False, manifest: Optional[Dict] = None) -> None:
        """Show dialog to select what to restore from backup"""
        try:
            dialog = tk.Toplevel(self)
            dialog.title(t('dialogs.restore_title'))
            dialog.geometry("450x680")
            dialog.resizable(True, True)
            dialog.minsize(450, 680)
            dialog.configure(bg="#1e1e1e")
            dialog.transient(self)
            dialog.grab_set()
            
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
            
            # Center on parent
            dialog.update_idletasks()
            x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
            y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
            dialog.geometry(f"+{x}+{y}")
            
            # Title
            title_label = tk.Label(dialog, text=t('dialogs.restore_title'), 
                                 font=("Segoe UI", 14, "bold"),
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
                                font=("Segoe UI", 9),
                                bg="#1e1e1e", fg="#aaaaaa")
            info_label.pack(pady=(0, 10))
            
            # Instructions
            inst_label = tk.Label(dialog, text=t('dialogs.restore_instructions'),
                                font=("Segoe UI", 10),
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
            
            # Restore Everything checkbox
            all_cb = tk.Checkbutton(options_frame, text=t('dialogs.restore_everything'),
                                  variable=restore_all,
                                  command=on_restore_all_change,
                                  bg="#1e1e1e", fg="#ffffff",
                                  selectcolor="#2a2a2a",
                                  activebackground="#2a2a2a",
                                  activeforeground="#ffffff",
                                  font=("Segoe UI", 10, "bold"))
            all_cb.pack(anchor="w", pady=5)
            
            # Separator
            sep = tk.Frame(options_frame, height=1, bg="#ff9800")
            sep.pack(fill="x", pady=10)
            
            # Checkboxes for available items
            if has_presets:
                presets_cb = tk.Checkbutton(options_frame, text=t('dialogs.ship_presets'),
                                          variable=restore_presets,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=("Segoe UI", 10))
                presets_cb.pack(anchor="w", pady=2)
            
            if has_reports:
                reports_cb = tk.Checkbutton(options_frame, text=t('dialogs.mining_reports'),
                                          variable=restore_reports,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=("Segoe UI", 10))
                reports_cb.pack(anchor="w", pady=2)
            
            if has_bookmarks:
                bookmarks_cb = tk.Checkbutton(options_frame, text=t('dialogs.mining_bookmarks'),
                                            variable=restore_bookmarks,
                                            bg="#1e1e1e", fg="#ffffff",
                                            selectcolor="#2a2a2a",
                                            activebackground="#2a2a2a",
                                            activeforeground="#ffffff",
                                            font=("Segoe UI", 10))
                bookmarks_cb.pack(anchor="w", pady=2)
            
            if has_va_profile:
                va_profile_cb = tk.Checkbutton(options_frame, text=t('dialogs.voiceattack_profile'),
                                             variable=restore_va_profile,
                                             bg="#1e1e1e", fg="#ffffff",
                                             selectcolor="#2a2a2a",
                                             activebackground="#2a2a2a",
                                             activeforeground="#ffffff",
                                             font=("Segoe UI", 10))
                va_profile_cb.pack(anchor="w", pady=2)
            
            if has_userdb:
                userdb_cb = tk.Checkbutton(options_frame, text=t('dialogs.user_database'),
                                          variable=restore_userdb,
                                          bg="#1e1e1e", fg="#ffffff",
                                          selectcolor="#2a2a2a",
                                          activebackground="#2a2a2a",
                                          activeforeground="#ffffff",
                                          font=("Segoe UI", 10))
                userdb_cb.pack(anchor="w", pady=2)
            
            if has_journals:
                journals_cb = tk.Checkbutton(options_frame, text=t('dialogs.journal_files'),
                                           variable=restore_journals,
                                           bg="#1e1e1e", fg="#ffffff",
                                           selectcolor="#2a2a2a",
                                           activebackground="#2a2a2a",
                                           activeforeground="#ffffff",
                                           font=("Segoe UI", 10))
                journals_cb.pack(anchor="w", pady=2)
            
            # Warning label
            warning_label = tk.Label(dialog, 
                                   text=t('dialogs.restore_warning'),
                                   font=("Segoe UI", 9, "bold"),
                                   bg="#1e1e1e", fg="#e74c3c")
            warning_label.pack(pady=(20, 5))
            
            # Restart info label
            restart_label = tk.Label(dialog, 
                                   text=t('dialogs.restart_info'),
                                   font=("Segoe UI", 9),
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
                                        restore_journals.get() if has_journals else False)
            
            def on_cancel():
                dialog.destroy()
            
            restore_btn = tk.Button(btn_frame, text=t('dialogs.restore_button'), command=on_restore,
                                  bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
                                  width=18, cursor="hand2")
            restore_btn.pack(side=tk.LEFT, padx=10)
            
            cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=on_cancel,
                                 bg="#e74c3c", fg="white", font=("Segoe UI", 10, "bold"),
                                 width=18, cursor="hand2")
            cancel_btn.pack(side=tk.LEFT, padx=10)
            
            # Bind escape key
            dialog.bind('<Escape>', lambda e: on_cancel())
            
            dialog.wait_window()
            
        except Exception as e:
            messagebox.showerror("Restore Options Error", f"Failed to show restore options: {str(e)}")

    def _restore_from_backup(self, backup_path: str, restore_presets: bool, 
                           restore_reports: bool, restore_bookmarks: bool, restore_va_profile: bool, restore_userdb: bool = False, restore_journals: bool = False) -> None:
        """Restore selected items from backup zip file"""
        try:
            app_data_dir = self._get_app_data_dir()
            restored_items = []
            
            with zipfile.ZipFile(backup_path, 'r') as zipf:
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
                
                # Restore VoiceAttack profile
                if restore_va_profile and "EliteMining-Profile.vap" in zipf.namelist():
                    # Use same path detection logic as backup
                    if getattr(sys, 'frozen', False):
                        # Running as executable - profile should go to same directory as executable or parent
                        exe_dir = os.path.dirname(sys.executable)
                        va_profile_path = os.path.join(exe_dir, "EliteMining-Profile.vap")
                        
                        # Check if we need to place it in parent directory instead
                        if not os.path.exists(os.path.join(exe_dir, "EliteMining-Profile.vap")) and os.path.basename(exe_dir) == "Configurator":
                            parent_dir = os.path.dirname(exe_dir)
                            va_profile_path = os.path.join(parent_dir, "EliteMining-Profile.vap")
                    else:
                        # Running in development - profile goes to project root
                        va_profile_path = os.path.join(os.path.dirname(app_data_dir), "EliteMining-Profile.vap")
                    
                    # Create target directory if needed
                    target_dir = os.path.dirname(va_profile_path)
                    os.makedirs(target_dir, exist_ok=True)
                    
                    with open(va_profile_path, 'wb') as f:
                        f.write(zipf.read("EliteMining-Profile.vap"))
                    restored_items.append("VoiceAttack Profile")
                
                # Restore user database
                if restore_userdb and "data/user_data.db" in zipf.namelist():
                    userdb_dir = os.path.join(app_data_dir, "data")
                    os.makedirs(userdb_dir, exist_ok=True)
                    target_path = os.path.join(userdb_dir, "user_data.db")
                    with open(target_path, 'wb') as f:
                        f.write(zipf.read("data/user_data.db"))
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
            
            if restored_items:
                items_text = ", ".join(restored_items)
                from app_utils import centered_message
                centered_message(self, "Restore Complete", f"Successfully restored:\n{items_text}")
                self._set_status(f"Restored from backup: {items_text}")
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
            print(f"Ring finder setup failed: {e}")
            traceback.print_exc()

    def _build_marketplace_tab(self, frame: ttk.Frame) -> None:
        """Build the Commodity Market tab with sub-tabs for Mining and Trade commodities"""
        # Create sub-notebook for Mining vs Trade commodities
        sub_notebook = ttk.Notebook(frame)
        sub_notebook.pack(fill="both", expand=True)
        
        # Mining Commodities sub-tab
        mining_tab = ttk.Frame(sub_notebook, padding=8)
        self._build_mining_commodities_tab(mining_tab)
        sub_notebook.add(mining_tab, text=t('tabs.mining_commodities'))
        
        # Trade Commodities sub-tab
        trade_tab = ttk.Frame(sub_notebook, padding=8)
        self._build_trade_commodities_tab(trade_tab)
        sub_notebook.add(trade_tab, text=t('tabs.trade_commodities'))
    
    def _build_mining_commodities_tab(self, frame: ttk.Frame) -> None:
        """Build the Mining Commodities sub-tab - matches original Commodity Market design"""
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search section
        search_frame = ttk.LabelFrame(main_container, text=t('marketplace.search_title'), padding=10)
        search_frame.pack(fill="x", pady=(0, 10))
        
        # Configure grid weights
        search_frame.columnconfigure(1, weight=1)
        
        # Load marketplace preferences from config
        cfg = _load_cfg()
        self.marketplace_search_mode = tk.StringVar(value=cfg.get('marketplace_search_mode', 'near_system'))
        self.marketplace_sell_mode = tk.BooleanVar(value=cfg.get('marketplace_sell_mode', True))
        self.marketplace_buy_mode = tk.BooleanVar(value=cfg.get('marketplace_buy_mode', False))
        
        # Get theme for checkbox/radiobutton styling
        from config import load_theme
        _mkt_cb_theme = load_theme()
        if _mkt_cb_theme == "elite_orange":
            _mkt_cb_bg = "#000000"  # Black background for orange theme
            _mkt_cb_select = "#000000"
        else:
            _mkt_cb_bg = "#1e1e1e"
            _mkt_cb_select = "#1e1e1e"
        
        # Row 0: Search Mode (Near/Galaxy) + Sell/Buy
        row0_frame = tk.Frame(search_frame, bg=_mkt_cb_bg)
        row0_frame.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        rb1 = tk.Radiobutton(row0_frame, text=t('marketplace.near_system'), variable=self.marketplace_search_mode,
                      value="near_system", bg=_mkt_cb_bg, fg="#ffffff", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        rb1.pack(side="left", padx=(0, 15))
        rb1.config(takefocus=0)
        ToolTip(rb1, t('tooltips.near_system_search'))
        
        rb2 = tk.Radiobutton(row0_frame, text=t('marketplace.galaxy_wide'), variable=self.marketplace_search_mode,
                      value="galaxy_wide", bg=_mkt_cb_bg, fg="#ffffff", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        rb2.pack(side="left", padx=(0, 20))
        rb2.config(takefocus=0)
        ToolTip(rb2, t('tooltips.galaxy_wide_search'))
        
        ttk.Separator(row0_frame, orient="vertical").pack(side="left", fill="y", padx=(0, 15))
        
        sell_cb = tk.Checkbutton(row0_frame, text=t('marketplace.sell'), variable=self.marketplace_sell_mode,
                      command=self._on_sell_mode_toggle, bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        sell_cb.pack(side="left", padx=(0, 10))
        ToolTip(sell_cb, t('tooltips.sell_mode'))
        
        buy_cb = tk.Checkbutton(row0_frame, text=t('marketplace.buy'), variable=self.marketplace_buy_mode,
                      command=self._on_buy_mode_toggle, bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        buy_cb.pack(side="left")
        ToolTip(buy_cb, t('tooltips.buy_mode'))
        
        # Row 1: Reference System + Commodity
        row1_frame = tk.Frame(search_frame, bg=_mkt_cb_bg)
        row1_frame.grid(row=1, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        # Fixed-width label for perfect alignment with Station: below
        ttk.Label(row1_frame, text=t('marketplace.ref_system'), width=12).pack(side="left", padx=(0, 5))
        self.marketplace_reference_system = tk.StringVar(value=cfg.get('marketplace_reference_system', ''))
        self.marketplace_ref_entry = ttk.Entry(row1_frame, textvariable=self.marketplace_reference_system, width=30)
        self.marketplace_ref_entry.pack(side="left", padx=(0, 5))
        self.marketplace_ref_entry.bind("<Return>", lambda e: self._search_marketplace())
        
        self.marketplace_use_current_btn = tk.Button(row1_frame, text=t('marketplace.use_current'), 
                                    command=self._use_current_system_marketplace,
                                    bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                                    relief="ridge", bd=1, padx=6, pady=2, font=("Segoe UI", 8), cursor="hand2",
                                    highlightbackground=_mkt_cb_bg, highlightcolor=_mkt_cb_bg)
        self.marketplace_use_current_btn.pack(side="left", padx=(0, 35))
        
        # Commodity label with consistent spacing
        ttk.Label(row1_frame, text=t('marketplace.commodity')).pack(side="left", padx=(0, 8))
        
        # Commodity list with localization
        self._commodity_order = ["Alexandrite", "Bauxite", "Benitoite", "Bertrandite", "Bromellite", 
                             "Cobalt", "Coltan", "Gallite", "Gold", "Grandidierite", "Indite", 
                             "Lepidolite", "Low Temperature Diamonds", "Monazite", "Musgravite", 
                             "Osmium", "Painite", "Palladium", "Platinum", "Praseodymium", 
                             "Rhodplumsite", "Rutile", "Samarium", "Serendibite", "Silver", 
                             "Tritium", "Uraninite", "Void Opals"]
        
        # Helper to format commodity display names (abbreviate long names)
        def format_commodity_display(name):
            localized = get_material(name)
            # Use abbreviated display for Low Temperature Diamonds
            if name == "Low Temperature Diamonds" or localized == "Low Temperature Diamonds":
                return "Low Temp. Diamonds"
            return localized
        
        self._commodity_map = {k: format_commodity_display(k) for k in self._commodity_order}
        self._commodity_rev_map = {v: k for k, v in self._commodity_map.items()}
        # Also map the full name for reverse lookup
        self._commodity_rev_map["Low Temperature Diamonds"] = "Low Temperature Diamonds"
        
        saved_commodity = cfg.get('marketplace_commodity', 'Alexandrite')
        self.marketplace_commodity = tk.StringVar(value=self._commodity_map.get(saved_commodity, saved_commodity))
        sorted_commodities = [self._commodity_map[k] for k in self._commodity_order]
        commodity_combo = ttk.Combobox(row1_frame, textvariable=self.marketplace_commodity,
                                     values=sorted_commodities, state="readonly", width=20)
        commodity_combo.pack(side="left")
        commodity_combo.bind("<Return>", lambda e: self._search_marketplace())
        commodity_combo.bind("<<ComboboxSelected>>", lambda e: self._save_marketplace_preferences())
        
        # Row 2: All filters (aligned with Row 1)
        row2_frame = tk.Frame(search_frame, bg=_mkt_cb_bg)
        row2_frame.grid(row=2, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        # Station type localization maps
        station_type_map = get_station_types()
        self._station_type_order = ['All', 'Orbital', 'Surface', 'Fleet Carrier', 'Megaship', 'Stronghold']
        self._station_type_map = {k: station_type_map.get(k, k) for k in self._station_type_order}
        self._station_type_rev_map = {v: k for k, v in self._station_type_map.items()}
        
        # Sort options localization maps (full map for all modes)
        self._sort_options_map = get_sort_options()
        self._sort_rev_map = {v: k for k, v in self._sort_options_map.items()}
        
        # Age options localization maps
        age_options_map = get_age_options()
        self._age_order = ['Any', '1 hour', '8 hours', '16 hours', '1 day', '2 days']
        self._age_map = {k: age_options_map.get(k, k) for k in self._age_order}
        self._age_rev_map = {v: k for k, v in self._age_map.items()}
        
        # Station label with same width as "Ref. System:" for perfect alignment
        station_label = ttk.Label(row2_frame, text=t('marketplace.station'), width=12)
        station_label.pack(side="left", padx=(0, 5))
        saved_station = cfg.get('marketplace_station_type', 'All')
        self.marketplace_station_type = tk.StringVar(value=self._station_type_map.get(saved_station, saved_station))
        station_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_station_type,
                                values=[self._station_type_map[k] for k in self._station_type_order],
                                state="readonly", width=12)
        station_combo.pack(side="left", padx=(0, 15))
        ToolTip(station_combo, t('tooltips.station_type_filter'))
        
        def on_station_type_change(*args):
            selected = self.marketplace_station_type.get()
            english_val = self._station_type_rev_map.get(selected, selected)
            if english_val == "Fleet Carrier":
                self.marketplace_exclude_carriers.set(False)
            self._save_marketplace_preferences()
        self.marketplace_station_type.trace_add("write", on_station_type_change)
        
        self.marketplace_exclude_carriers = tk.BooleanVar(value=cfg.get('marketplace_exclude_carriers', True))
        exclude_cb = tk.Checkbutton(row2_frame, text=t('marketplace.exclude_carriers'), variable=self.marketplace_exclude_carriers,
                      command=self._save_marketplace_preferences,
                      bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        exclude_cb.pack(side="left", padx=(0, 10))
        ToolTip(exclude_cb, t('tooltips.exclude_carriers'))
        
        self.marketplace_large_pad_only = tk.BooleanVar(value=cfg.get('marketplace_large_pad_only', False))
        large_pad_cb = tk.Checkbutton(row2_frame, text=t('marketplace.large_pads'), variable=self.marketplace_large_pad_only,
                      command=self._save_marketplace_preferences,
                      bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        large_pad_cb.pack(side="left", padx=(0, 30))
        ToolTip(large_pad_cb, t('tooltips.large_pads'))
        
        # Sort by label with adjustable spacing
        ttk.Label(row2_frame, text=t('marketplace.sort_by')).pack(side="left", padx=(0, 8))  # Aligned with Commodity above
        saved_sort = cfg.get('marketplace_order_by', 'Distance')
        # Determine initial sort options based on sell mode (default)
        initial_sort_order = ['Best price (highest)', 'Distance', 'Best demand', 'Last update']
        self.marketplace_order_by = tk.StringVar(value=self._sort_options_map.get(saved_sort, saved_sort))
        self.marketplace_order_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_order_by,
                                     values=[self._sort_options_map.get(k, k) for k in initial_sort_order],
                                     state="readonly", width=20)
        self.marketplace_order_combo.pack(side="left", padx=(29, 0))  # Adjust first number to move dropdown
        self.marketplace_order_combo.bind("<<ComboboxSelected>>", lambda e: self._save_marketplace_preferences())
        ToolTip(self.marketplace_order_combo, t('tooltips.sort_by'))
        
        # Row 3: Search button and Max Age
        row3_frame = tk.Frame(search_frame, bg=_mkt_cb_bg)
        row3_frame.grid(row=3, column=0, columnspan=5, sticky="ew")
        
        search_btn = tk.Button(row3_frame, text="🔍 " + t('marketplace.search'), 
                              command=self._search_marketplace,
                              bg="#2a4a2a", fg="#e0e0e0", 
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=10, pady=4,
                              font=("Segoe UI", 9, "bold"), cursor="hand2")
        search_btn.pack(side="left")
        
        # EDDATA API status indicator (pack FIRST on right side to claim far right position)
        self.eddata_mining_status_label = tk.Label(row3_frame, text="⚫ EDDATA: checking...", 
                                          font=("Segoe UI", 8), fg="#888888", bg=_mkt_cb_bg)
        self.eddata_mining_status_label.pack(side="right", padx=(0, 10))
        ToolTip(self.eddata_mining_status_label, t('tooltips.eddata_status'))
        
        # Start EDDATA status check
        self.after(1000, self._check_eddata_status)
        
        # Max Age with left padding to align under Sort by above
        _max_age_fg = "#ff8c00" if _mkt_cb_theme == "elite_orange" else "#e0e0e0"
        max_age_label = tk.Label(row3_frame, text=t('marketplace.max_age'), bg=_mkt_cb_bg, fg=_max_age_fg)
        max_age_label.pack(side="left", padx=(399, 8))  # Left padding to align with Sort by
        saved_age = cfg.get('marketplace_max_age', '8 hours')
        self.marketplace_max_age = tk.StringVar(value=self._age_map.get(saved_age, saved_age))
        age_combo = ttk.Combobox(row3_frame, textvariable=self.marketplace_max_age,
                                values=[self._age_map[k] for k in self._age_order],
                                state="readonly", width=10)
        age_combo.pack(side="left", padx=(17, 0))  # Add left padding here
        age_combo.bind("<<ComboboxSelected>>", lambda e: self._save_marketplace_preferences())
        ToolTip(age_combo, t('tooltips.max_age'))
        
        # EDTools button hidden (keep for future reference)
        # edtools_btn = tk.Button(search_frame, text="🔍 Search EDTools.cc", 
        #                        command=self._open_edtools_market,
        #                        bg="#2a4a2a", fg="#e0e0e0")
        # edtools_btn.grid(row=4, column=0, columnspan=5, pady=(5, 5))
        
        # Results section with help text on same line as label
        results_header = tk.Frame(main_container, bg=_mkt_cb_bg)
        results_header.pack(fill="x", pady=(10, 0))
        
        tk.Label(results_header, text=t('marketplace.search_results'), 
                bg=_mkt_cb_bg, fg="#ffffff", 
                font=("Segoe UI", 10, "bold")).pack(side="left")
        
        tk.Label(results_header, text="  •  " + t('marketplace.right_click_options'),
                bg=_mkt_cb_bg, fg="#888888",
                font=("Segoe UI", 8)).pack(side="left")
        
        # Status label (moved to header, right side)
        self.marketplace_total_label = tk.Label(results_header, text=t('marketplace.enter_system_commodity'),
                                               bg=_mkt_cb_bg, fg="gray", font=("Segoe UI", 8))
        self.marketplace_total_label.pack(side="right")
        
        results_frame = tk.Frame(main_container, bg="#2d2d2d", relief="sunken", bd=1)
        results_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        # Create results table
        self._create_marketplace_results_table(results_frame)
        
        # Add tooltips
        ToolTip(self.marketplace_ref_entry, t('tooltips.reference_system'))
        ToolTip(self.marketplace_use_current_btn, t('tooltips.use_current_market'))
        ToolTip(search_btn, t('tooltips.search_market'))
        ToolTip(commodity_combo, t('tooltips.select_commodity'))
        
        # Initialize dropdown options based on current buy/sell mode
        self._update_marketplace_order_options()
        
        # Load saved preferences
        self._load_marketplace_preferences()
    
    def _build_trade_commodities_tab(self, frame: ttk.Frame) -> None:
        """Build the Trade Commodities sub-tab with category selection"""
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search section
        search_frame = ttk.LabelFrame(main_container, text=t('marketplace.search_title'), padding=10)
        search_frame.pack(fill="x", pady=(0, 10))
        
        # Configure grid weights
        search_frame.columnconfigure(1, weight=1)
        
        # Load marketplace preferences from config
        cfg = _load_cfg()
        self.trade_search_mode = tk.StringVar(value=cfg.get('trade_search_mode', 'near_system'))
        self.trade_sell_mode = tk.BooleanVar(value=cfg.get('trade_sell_mode', True))
        self.trade_buy_mode = tk.BooleanVar(value=cfg.get('trade_buy_mode', False))
        
        # Get theme for checkbox/radiobutton styling
        from config import load_theme
        _trade_cb_theme = load_theme()
        if _trade_cb_theme == "elite_orange":
            _trade_cb_bg = "#000000"
            _trade_cb_select = "#000000"
        else:
            _trade_cb_bg = "#1e1e1e"
            _trade_cb_select = "#1e1e1e"
        
        # Row 0: Search Mode (Near/Galaxy) + Sell/Buy
        row0_frame = tk.Frame(search_frame, bg=_trade_cb_bg)
        row0_frame.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        rb1 = tk.Radiobutton(row0_frame, text=t('marketplace.near_system'), variable=self.trade_search_mode,
                      value="near_system", bg=_trade_cb_bg, fg="#ffffff", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        rb1.pack(side="left", padx=(0, 15))
        rb1.config(takefocus=0)
        ToolTip(rb1, t('tooltips.near_system_search'))
        
        rb2 = tk.Radiobutton(row0_frame, text=t('marketplace.galaxy_wide'), variable=self.trade_search_mode,
                      value="galaxy_wide", bg=_trade_cb_bg, fg="#ffffff", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        rb2.pack(side="left", padx=(0, 20))
        rb2.config(takefocus=0)
        ToolTip(rb2, t('tooltips.galaxy_wide_search'))
        
        ttk.Separator(row0_frame, orient="vertical").pack(side="left", fill="y", padx=(0, 15))
        
        sell_cb = tk.Checkbutton(row0_frame, text=t('marketplace.sell'), variable=self.trade_sell_mode,
                      command=self._on_trade_sell_mode_toggle, bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        sell_cb.pack(side="left", padx=(0, 10))
        ToolTip(sell_cb, t('tooltips.sell_mode'))
        
        buy_cb = tk.Checkbutton(row0_frame, text=t('marketplace.buy'), variable=self.trade_buy_mode,
                      command=self._on_trade_buy_mode_toggle, bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        buy_cb.pack(side="left")
        ToolTip(buy_cb, t('tooltips.buy_mode'))
        
        # Row 1: Reference System + Category + Commodity
        row1_frame = tk.Frame(search_frame, bg=_trade_cb_bg)
        row1_frame.grid(row=1, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        ttk.Label(row1_frame, text=t('marketplace.ref_system'), width=12).pack(side="left", padx=(0, 5))
        self.trade_reference_system = tk.StringVar(value=cfg.get('trade_reference_system', ''))
        self.trade_ref_entry = ttk.Entry(row1_frame, textvariable=self.trade_reference_system, width=30)
        self.trade_ref_entry.pack(side="left", padx=(0, 5))
        self.trade_ref_entry.bind("<Return>", lambda e: self._search_trade_market())
        
        self.trade_use_current_btn = tk.Button(row1_frame, text=t('marketplace.use_current'), 
                                    command=self._use_current_system_trade,
                                    bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                                    relief="ridge", bd=1, padx=6, pady=2, font=("Segoe UI", 8), cursor="hand2",
                                    highlightbackground=_trade_cb_bg, highlightcolor=_trade_cb_bg)
        self.trade_use_current_btn.pack(side="left", padx=(0, 15))
        
        # Category dropdown
        ttk.Label(row1_frame, text=t('marketplace.category')).pack(side="left", padx=(0, 8))
        
        # Get sorted category list from commodities data
        self._trade_categories = sorted(self.commodities_data.keys()) if self.commodities_data else []
        saved_category = cfg.get('trade_category', self._trade_categories[0] if self._trade_categories else 'Chemicals')
        self.trade_category = tk.StringVar(value=saved_category)
        category_combo = ttk.Combobox(row1_frame, textvariable=self.trade_category,
                                     values=self._trade_categories, state="readonly", width=18)
        category_combo.pack(side="left", padx=(0, 15))
        category_combo.bind("<<ComboboxSelected>>", self._on_trade_category_changed)
        
        # Commodity dropdown (populated based on category)
        ttk.Label(row1_frame, text=t('marketplace.commodity')).pack(side="left", padx=(0, 8))
        self.trade_commodity = tk.StringVar()
        self.trade_commodity_combo = ttk.Combobox(row1_frame, textvariable=self.trade_commodity,
                                                 values=[], state="readonly", width=20)
        self.trade_commodity_combo.pack(side="left")
        self.trade_commodity_combo.bind("<Return>", lambda e: self._search_trade_market())
        self.trade_commodity_combo.bind("<<ComboboxSelected>>", lambda e: self._save_trade_preferences())
        
        # Populate initial commodity list
        self._update_trade_commodity_list()
        
        # Row 2: All filters (same as mining tab)
        row2_frame = tk.Frame(search_frame, bg=_trade_cb_bg)
        row2_frame.grid(row=2, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        # Station type
        station_type_map = get_station_types()
        self._trade_station_type_order = ['All', 'Orbital', 'Surface', 'Fleet Carrier', 'Megaship', 'Stronghold']
        self._trade_station_type_map = {k: station_type_map.get(k, k) for k in self._trade_station_type_order}
        self._trade_station_type_rev_map = {v: k for k, v in self._trade_station_type_map.items()}
        
        # Sort options
        self._trade_sort_options_map = get_sort_options()
        self._trade_sort_rev_map = {v: k for k, v in self._trade_sort_options_map.items()}
        
        # Age options
        age_options_map = get_age_options()
        self._trade_age_order = ['Any', '1 hour', '8 hours', '16 hours', '1 day', '2 days']
        self._trade_age_map = {k: age_options_map.get(k, k) for k in self._trade_age_order}
        self._trade_age_rev_map = {v: k for k, v in self._trade_age_map.items()}
        
        station_label = ttk.Label(row2_frame, text=t('marketplace.station'), width=12)
        station_label.pack(side="left", padx=(0, 5))
        saved_station = cfg.get('trade_station_type', 'All')
        self.trade_station_type = tk.StringVar(value=self._trade_station_type_map.get(saved_station, saved_station))
        station_combo = ttk.Combobox(row2_frame, textvariable=self.trade_station_type,
                                values=[self._trade_station_type_map[k] for k in self._trade_station_type_order],
                                state="readonly", width=12)
        station_combo.pack(side="left", padx=(0, 15))
        ToolTip(station_combo, t('tooltips.station_type_filter'))
        
        def on_trade_station_type_change(*args):
            selected = self.trade_station_type.get()
            english_val = self._trade_station_type_rev_map.get(selected, selected)
            if english_val == "Fleet Carrier":
                self.trade_exclude_carriers.set(False)
            self._save_trade_preferences()
        self.trade_station_type.trace_add("write", on_trade_station_type_change)
        
        self.trade_exclude_carriers = tk.BooleanVar(value=cfg.get('trade_exclude_carriers', True))
        exclude_cb = tk.Checkbutton(row2_frame, text=t('marketplace.exclude_carriers'), variable=self.trade_exclude_carriers,
                      command=self._save_trade_preferences,
                      bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        exclude_cb.pack(side="left", padx=(0, 10))
        ToolTip(exclude_cb, t('tooltips.exclude_carriers'))
        
        self.trade_large_pad_only = tk.BooleanVar(value=cfg.get('trade_large_pad_only', False))
        large_pad_cb = tk.Checkbutton(row2_frame, text=t('marketplace.large_pads'), variable=self.trade_large_pad_only,
                      command=self._save_trade_preferences,
                      bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        large_pad_cb.pack(side="left", padx=(0, 11))
        ToolTip(large_pad_cb, t('tooltips.large_pads'))
        
        # Sort by
        ttk.Label(row2_frame, text=t('marketplace.sort_by')).pack(side="left", padx=(0, 8))  # Aligned with Commodity above
        saved_sort = cfg.get('trade_order_by', 'Distance')
        initial_sort_order = ['Best price (highest)', 'Distance', 'Best demand', 'Last update']
        self.trade_order_by = tk.StringVar(value=self._trade_sort_options_map.get(saved_sort, saved_sort))
        self.trade_order_combo = ttk.Combobox(row2_frame, textvariable=self.trade_order_by,
                                     values=[self._trade_sort_options_map.get(k, k) for k in initial_sort_order],
                                     state="readonly", width=18)
        self.trade_order_combo.pack(side="left", padx=(11, 0))
        self.trade_order_combo.bind("<<ComboboxSelected>>", lambda e: self._save_trade_preferences())
        ToolTip(self.trade_order_combo, t('tooltips.sort_by'))
        
        # Row 3: Search button and Max Age
        row3_frame = tk.Frame(search_frame, bg=_trade_cb_bg)
        row3_frame.grid(row=3, column=0, columnspan=5, sticky="ew")
        
        search_btn = tk.Button(row3_frame, text="🔍 " + t('marketplace.search'), 
                              command=self._search_trade_market,
                              bg="#2a4a2a", fg="#e0e0e0", 
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=10, pady=4,
                              font=("Segoe UI", 9, "bold"), cursor="hand2")
        search_btn.pack(side="left")
        
        # EDDATA API status indicator (pack FIRST on right side to claim far right position)
        self.eddata_trade_status_label = tk.Label(row3_frame, text="⚫ EDDATA: checking...", 
                                          font=("Segoe UI", 8), fg="#888888", bg=_trade_cb_bg)
        self.eddata_trade_status_label.pack(side="right", padx=(0, 10))
        ToolTip(self.eddata_trade_status_label, t('tooltips.eddata_status'))
        
        # Max Age
        _max_age_fg = "#ff8c00" if _trade_cb_theme == "elite_orange" else "#e0e0e0"
        max_age_label = tk.Label(row3_frame, text=t('marketplace.max_age'), bg=_trade_cb_bg, fg=_max_age_fg)
        max_age_label.pack(side="left", padx=(376, 0))
        saved_age = cfg.get('trade_max_age', '8 hours')
        self.trade_max_age = tk.StringVar(value=self._trade_age_map.get(saved_age, saved_age))
        age_combo = ttk.Combobox(row3_frame, textvariable=self.trade_max_age,
                                values=[self._trade_age_map[k] for k in self._trade_age_order],
                                state="readonly", width=10)
        age_combo.pack(side="left", padx=(12, 0))
        age_combo.bind("<<ComboboxSelected>>", lambda e: self._save_trade_preferences())
        ToolTip(age_combo, t('tooltips.max_age'))
        
        # Results section
        results_header = tk.Frame(main_container, bg=_trade_cb_bg)
        results_header.pack(fill="x", pady=(10, 0))
        
        tk.Label(results_header, text=t('marketplace.search_results'), 
                bg=_trade_cb_bg, fg="#ffffff", 
                font=("Segoe UI", 10, "bold")).pack(side="left")
        
        tk.Label(results_header, text="  •  " + t('marketplace.right_click_options'),
                bg=_trade_cb_bg, fg="#888888",
                font=("Segoe UI", 8)).pack(side="left")
        
        # Status label
        self.trade_total_label = tk.Label(results_header, text=t('marketplace.enter_system_commodity'),
                                               bg=_trade_cb_bg, fg="gray", font=("Segoe UI", 8))
        self.trade_total_label.pack(side="right")
        
        results_frame = tk.Frame(main_container, bg="#2d2d2d", relief="sunken", bd=1)
        results_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        # Create results table
        self._create_trade_results_table(results_frame)
        
        # Add tooltips
        ToolTip(self.trade_ref_entry, t('tooltips.reference_system'))
        ToolTip(self.trade_use_current_btn, t('tooltips.use_current_market'))
        ToolTip(search_btn, t('tooltips.search_market'))
        ToolTip(category_combo, t('tooltips.select_category'))
        ToolTip(self.trade_commodity_combo, t('tooltips.select_commodity'))
        
        # Initialize dropdown options based on current buy/sell mode
        self._update_trade_order_options()
        
        # Load saved preferences
        self._load_trade_preferences()
    
    # ==================== SYSTEM FINDER TAB ====================
    def _build_system_finder_tab(self, frame: ttk.Frame) -> None:
        """Build the System Finder tab - search nearby systems by criteria"""
        from system_finder_api import (
            SECURITY_OPTIONS, ALLEGIANCE_OPTIONS, GOVERNMENT_OPTIONS,
            STATE_OPTIONS, ECONOMY_OPTIONS, POPULATION_OPTIONS
        )
        from config import load_theme
        
        # Get theme colors
        sf_theme = load_theme()
        if sf_theme == "elite_orange":
            sf_bg = "#0a0a0a"
            sf_menu_bg = "#1e1e1e"
            sf_menu_fg = "#ff8c00"
            sf_menu_active_bg = "#ff6600"
            sf_menu_active_fg = "#000000"
        else:
            sf_bg = "#1e1e1e"
            sf_menu_bg = "#2d2d2d"
            sf_menu_fg = "#e0e0e0"
            sf_menu_active_bg = "#3a3a3a"
            sf_menu_active_fg = "#ffffff"
        
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search section
        search_frame = ttk.LabelFrame(main_container, text=t('system_finder.title'), padding=10)
        search_frame.pack(fill="x", pady=(0, 10))
        
        # Configure grid weights
        for i in range(4):
            search_frame.columnconfigure(i, weight=1)
        
        # Row 0: Reference system, Use Current System button, and Search button
        row = 0
        ttk.Label(search_frame, text=t('system_finder.reference_system') + ":").grid(
            row=row, column=0, sticky="e", padx=(0, 5), pady=3)
        
        # Frame to hold entry, buttons side by side
        ref_frame = ttk.Frame(search_frame)
        ref_frame.grid(row=row, column=1, columnspan=3, sticky="w", padx=5, pady=3)
        
        self.sysfinder_reference_system = tk.StringVar()
        self.sysfinder_ref_entry = ttk.Entry(
            ref_frame, textvariable=self.sysfinder_reference_system, width=30
        )
        self.sysfinder_ref_entry.pack(side="left")
        
        # Use Current System button - right next to entry (like ring finder)
        self.sysfinder_use_current_btn = tk.Button(
            ref_frame, text=t('ring_finder.use_current_system'),
            command=self._use_current_system_sysfinder,
            bg="#4a3a2a", fg="#e0e0e0",
            activebackground="#5a4a3a", activeforeground="#ffffff",
            relief="ridge", bd=1, padx=8, pady=4,
            font=("Segoe UI", 8, "normal"), cursor="hand2"
        )
        self.sysfinder_use_current_btn.pack(side="left", padx=(5, 0))
        
        # Search button - moved to Row 0 for faster access
        self.sysfinder_search_btn = tk.Button(
            ref_frame, text=t('system_finder.search'),
            command=self._search_systems,
            bg="#2a4a2a", fg="#e0e0e0",
            activebackground="#3a5a3a", activeforeground="#ffffff",
            relief="ridge", bd=1, padx=15, pady=4,
            font=("Segoe UI", 8, "normal"), cursor="hand2"
        )
        self.sysfinder_search_btn.pack(side="left", padx=(10, 0))
        
        # Row 1: Allegiance and Population
        row = 1
        ttk.Label(search_frame, text=t('system_finder.allegiance') + ":").grid(
            row=row, column=0, sticky="e", padx=(0, 5), pady=3)
        
        self.sysfinder_allegiance = tk.StringVar(value="Any")
        allegiance_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_allegiance,
            values=ALLEGIANCE_OPTIONS, width=15, state="readonly"
        )
        allegiance_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(search_frame, text=t('system_finder.population') + ":").grid(
            row=row, column=2, sticky="e", padx=(15, 5), pady=3)
        
        # Population options (Inara-style thresholds - no localization needed)
        self.sysfinder_population = tk.StringVar(value="Any")
        pop_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_population,
            values=POPULATION_OPTIONS, width=22, state="readonly"
        )
        pop_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        
        # Row 2: Government and Security
        row = 2
        ttk.Label(search_frame, text=t('system_finder.government') + ":").grid(
            row=row, column=0, sticky="e", padx=(0, 5), pady=3)
        
        self.sysfinder_government = tk.StringVar(value="Any")
        gov_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_government,
            values=GOVERNMENT_OPTIONS, width=15, state="readonly"
        )
        gov_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(search_frame, text=t('system_finder.security') + ":").grid(
            row=row, column=2, sticky="e", padx=(15, 5), pady=3)
        
        self.sysfinder_security = tk.StringVar(value="Any")
        security_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_security,
            values=SECURITY_OPTIONS, width=22, state="readonly"
        )
        security_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        
        # Row 3: Economy and State
        row = 3
        ttk.Label(search_frame, text=t('system_finder.economy') + ":").grid(
            row=row, column=0, sticky="e", padx=(0, 5), pady=3)
        
        self.sysfinder_economy = tk.StringVar(value="Any")
        economy_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_economy,
            values=ECONOMY_OPTIONS, width=15, state="readonly"
        )
        economy_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(search_frame, text=t('system_finder.state') + ":").grid(
            row=row, column=2, sticky="e", padx=(15, 5), pady=3)
        
        self.sysfinder_state = tk.StringVar(value="Any")
        state_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_state,
            values=STATE_OPTIONS, width=18, state="readonly"
        )
        state_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        
        # Row 4: Reference system info display (shows info about the "Reference System")
        # Split into 2 rows: Row 1 = System name, Row 2 = Properties
        row = 4
        ref_info_frame = tk.Frame(search_frame, bg=sf_bg)
        ref_info_frame.grid(row=row, column=0, columnspan=4, pady=(8, 3), sticky="ew")
        
        # Store background color for later updates
        self._sysfinder_ref_bg = sf_bg
        
        # Reference system info - using multiple labels for white/yellow styling
        # Labels in white, values in yellow (like CMDR status line)
        font_label = ("Segoe UI", 9)
        font_value = ("Segoe UI", 9, "bold")
        
        # Row 1: System name (centered)
        row1_container = tk.Frame(ref_info_frame, bg=sf_bg)
        row1_container.pack(anchor="center")
        
        tk.Label(row1_container, text="Current System:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_system = tk.Label(row1_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_system.pack(side="left")
        
        # Row 2: Properties (centered)
        row2_container = tk.Frame(ref_info_frame, bg=sf_bg)
        row2_container.pack(anchor="center")
        
        tk.Label(row2_container, text="Security:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_sec = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_sec.pack(side="left")
        
        tk.Label(row2_container, text=" | Allegiance:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_alleg = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_alleg.pack(side="left")
        
        tk.Label(row2_container, text=" | Government:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_gov = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_gov.pack(side="left")
        
        tk.Label(row2_container, text=" | Economy:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_eco = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_eco.pack(side="left")
        
        tk.Label(row2_container, text=" | Population:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_pop = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_pop.pack(side="left")
        
        tk.Label(row2_container, text=" | State:", font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_state = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_state.pack(side="left")
        
        # Add trace to update info when reference system changes (with debounce)
        self._sysfinder_ref_update_pending = None
        def on_ref_system_change(*args):
            # Cancel any pending update
            if self._sysfinder_ref_update_pending:
                self.after_cancel(self._sysfinder_ref_update_pending)
            # Schedule new update after 500ms debounce
            system = self.sysfinder_reference_system.get().strip()
            if system:
                self._sysfinder_ref_update_pending = self.after(500, lambda: self._update_sysfinder_ref_info(system))
            else:
                # Reset all values to "-"
                self.sysfinder_ref_val_system.config(text=" Enter system")
                self.sysfinder_ref_val_sec.config(text=" -")
                self.sysfinder_ref_val_alleg.config(text=" -")
                self.sysfinder_ref_val_gov.config(text=" -")
                self.sysfinder_ref_val_eco.config(text=" -")
                self.sysfinder_ref_val_pop.config(text=" -")
                self.sysfinder_ref_val_state.config(text=" -")
        self.sysfinder_reference_system.trace_add('write', on_ref_system_change)
        
        # Results section
        results_frame = ttk.LabelFrame(main_container, text="", padding=5)
        results_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        # Status/count label
        self.sysfinder_status_label = ttk.Label(results_frame, text="")
        self.sysfinder_status_label.pack(anchor="w", pady=(0, 5))
        
        # Store theme colors for context menu (before creating it)
        self._sysfinder_menu_bg = sf_menu_bg
        self._sysfinder_menu_fg = sf_menu_fg
        self._sysfinder_menu_active_bg = sf_menu_active_bg
        self._sysfinder_menu_active_fg = sf_menu_active_fg
        
        # Create results table
        self._create_sysfinder_results_table(results_frame)
        
        # Create context menu
        self._create_sysfinder_context_menu()
        
        # Auto-populate current system after a delay
        self.after(2000, self._populate_sysfinder_system)
        
        # Remove focus from entry field (prevent highlight on tab switch)
        # Focus the frame instead of the entry
        frame.focus_set()
    
    def _create_sysfinder_results_table(self, parent_frame):
        """Create results table for system finder"""
        table_frame = ttk.Frame(parent_frame, relief="solid", borderwidth=1)
        table_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Define columns (faction removed - users can right-click → Inara for details)
        columns = ("system", "distance", "security", "allegiance", "state", "population", "economy")
        
        # Configure treeview style based on theme
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
        
        style.configure("SystemFinder.Treeview",
                       rowheight=25,
                       background=tree_bg,
                       foreground=tree_fg,
                       fieldbackground=tree_bg,
                       font=("Segoe UI", 9))
        style.configure("SystemFinder.Treeview.Heading",
                       background=header_bg,
                       foreground=tree_fg,
                       font=("Segoe UI", 9, "bold"))
        style.map("SystemFinder.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])
        
        self.sysfinder_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings", height=15, style="SystemFinder.Treeview"
        )
        
        # Column headings
        self.sysfinder_tree.heading("system", text=t('system_finder.col_system'), 
                                    command=lambda: self._sort_sysfinder_column("system", False))
        self.sysfinder_tree.heading("distance", text=t('system_finder.col_distance'), 
                                    command=lambda: self._sort_sysfinder_column("distance", True))
        self.sysfinder_tree.heading("security", text=t('system_finder.col_security'), 
                                    command=lambda: self._sort_sysfinder_column("security", False))
        self.sysfinder_tree.heading("allegiance", text=t('system_finder.col_allegiance'), 
                                    command=lambda: self._sort_sysfinder_column("allegiance", False))
        self.sysfinder_tree.heading("state", text=t('system_finder.col_state'), 
                                    command=lambda: self._sort_sysfinder_column("state", False))
        self.sysfinder_tree.heading("population", text=t('system_finder.col_population'), 
                                    command=lambda: self._sort_sysfinder_column("population", True))
        self.sysfinder_tree.heading("economy", text=t('system_finder.col_economy'), 
                                    command=lambda: self._sort_sysfinder_column("economy", False))
        
        # Column widths
        self.sysfinder_tree.column("system", width=150, minwidth=100)
        self.sysfinder_tree.column("distance", width=70, minwidth=50, anchor="center")
        self.sysfinder_tree.column("security", width=80, minwidth=60, anchor="center")
        self.sysfinder_tree.column("allegiance", width=90, minwidth=70, anchor="center")
        self.sysfinder_tree.column("state", width=90, minwidth=70, anchor="center")
        self.sysfinder_tree.column("population", width=100, minwidth=70, anchor="center")
        self.sysfinder_tree.column("economy", width=120, minwidth=80, anchor="center")
        
        # Setup column visibility for system finder
        self.setup_column_visibility(
            tree=self.sysfinder_tree,
            columns=columns,
            default_widths={"system": 150, "distance": 70, "security": 80, "allegiance": 90, "state": 90, "population": 100, "economy": 120},
            config_key='system_finder'
        )
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.sysfinder_tree.yview)
        self.sysfinder_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar (like Ring Finder)
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.sysfinder_tree.xview)
        self.sysfinder_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure row tags for alternating colors (like Ring Finder)
        self.sysfinder_tree.tag_configure('oddrow', background='#1e1e1e')
        self.sysfinder_tree.tag_configure('evenrow', background='#1a1a1a')
        
        # Grid layout for treeview and scrollbars (like Ring Finder)
        self.sysfinder_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        # Register context menu handler for system finder
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['system_finder'] = self._show_sysfinder_context_menu
        # Note: Right-click binding handled by column visibility mixin
        
        # Store sort direction
        self._sysfinder_sort_reverse = {}
    
    def _create_sysfinder_context_menu(self):
        """Create context menu for system finder results with theme colors"""
        menu_bg = getattr(self, '_sysfinder_menu_bg', '#1e1e1e')
        menu_fg = getattr(self, '_sysfinder_menu_fg', '#ff8c00')
        menu_active_bg = getattr(self, '_sysfinder_menu_active_bg', '#ff6600')
        menu_active_fg = getattr(self, '_sysfinder_menu_active_fg', '#000000')
        
        self.sysfinder_context_menu = tk.Menu(self, tearoff=0, 
            bg=menu_bg, fg=menu_fg, 
            activebackground=menu_active_bg, activeforeground=menu_active_fg,
            selectcolor=menu_active_bg)
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.copy_system'),
            command=self._copy_sysfinder_system
        )
        self.sysfinder_context_menu.add_separator()
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.open_inara'),
            command=self._open_sysfinder_inara
        )
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.open_edsm'),
            command=self._open_sysfinder_edsm
        )
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.open_spansh'),
            command=self._open_sysfinder_spansh
        )
    
    def _show_sysfinder_context_menu(self, event):
        """Show context menu on right-click"""
        try:
            item = self.sysfinder_tree.identify_row(event.y)
            if item:
                self.sysfinder_tree.selection_set(item)
                self.sysfinder_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.sysfinder_context_menu.grab_release()
    
    def _copy_sysfinder_system(self):
        """Copy selected system name to clipboard"""
        selection = self.sysfinder_tree.selection()
        if selection:
            item = self.sysfinder_tree.item(selection[0])
            system_name = item['values'][0]
            self.clipboard_clear()
            self.clipboard_append(system_name)
            self._set_status(f"Copied: {system_name}", 3000)
    
    def _open_sysfinder_inara(self):
        """Open selected system in Inara"""
        selection = self.sysfinder_tree.selection()
        if selection:
            item = self.sysfinder_tree.item(selection[0])
            system_name = item['values'][0]
            import urllib.parse
            import webbrowser
            url = f"https://inara.cz/elite/starsystem/?search={urllib.parse.quote(system_name)}"
            webbrowser.open(url)
    
    def _open_sysfinder_edsm(self):
        """Open selected system in EDSM"""
        selection = self.sysfinder_tree.selection()
        if selection:
            item = self.sysfinder_tree.item(selection[0])
            system_name = item['values'][0]
            import urllib.parse
            import webbrowser
            url = f"https://www.edsm.net/en/system/id/0/name/{urllib.parse.quote(system_name)}"
            webbrowser.open(url)
    
    def _open_sysfinder_spansh(self):
        """Open selected system in Spansh"""
        selection = self.sysfinder_tree.selection()
        if selection:
            item = self.sysfinder_tree.item(selection[0])
            system_name = item['values'][0]
            import urllib.parse
            import webbrowser
            # Spansh uses /search/ endpoint for system lookup
            url = f"https://spansh.co.uk/search/{urllib.parse.quote(system_name)}"
            webbrowser.open(url)

    def _use_current_system_sysfinder(self):
        """Use current system from journal for system finder"""
        try:
            current = self.get_current_system()
            if current:
                self.sysfinder_reference_system.set(current)
                self._set_status(f"Using current system: {current}", 3000)
                # Update reference system info display
                self._update_sysfinder_ref_info(current)
            else:
                self._set_status("Could not determine current system", 3000)
        except Exception as e:
            logging.error(f"[SYSTEM_FINDER] Error getting current system: {e}")
    
    def _populate_sysfinder_system(self):
        """Auto-populate system finder with current system"""
        try:
            current = self.get_current_system()
            if current and hasattr(self, 'sysfinder_reference_system'):
                if not self.sysfinder_reference_system.get():
                    self.sysfinder_reference_system.set(current)
                    # Update reference system info display
                    self._update_sysfinder_ref_info(current)
                    # Remove selection/focus from entry field
                    if hasattr(self, 'sysfinder_ref_entry'):
                        self.sysfinder_ref_entry.selection_clear()
                        self.focus_set()  # Move focus to main window
        except Exception:
            pass
    
    def _update_sysfinder_ref_info(self, system_name: str):
        """Update the reference system info display with system status"""
        if not system_name or not hasattr(self, 'sysfinder_ref_val_system'):
            return
        
        # Show loading state
        self.sysfinder_ref_val_system.config(text=f" {system_name}")
        self.sysfinder_ref_val_sec.config(text=" ...")
        self.sysfinder_ref_val_alleg.config(text=" ...")
        self.sysfinder_ref_val_gov.config(text=" ...")
        self.sysfinder_ref_val_eco.config(text=" ...")
        self.sysfinder_ref_val_pop.config(text=" ...")
        self.sysfinder_ref_val_state.config(text=" ...")
        
        def fetch_info():
            try:
                from system_finder_api import SystemFinderAPI
                print(f"[REF_INFO DEBUG] Fetching info for: {system_name}")
                status = SystemFinderAPI.get_system_status(system_name)
                print(f"[REF_INFO DEBUG] API returned: {status}")
                
                if status:
                    # Extract values
                    security = status.get('security') or '-'
                    allegiance = status.get('allegiance') or '-'
                    government = status.get('government') or '-'
                    population = status.get('population', 0)
                    state = status.get('state') or 'Normal'
                    if state == 'None':
                        state = 'Normal'
                    economy = status.get('economy', {})
                    if isinstance(economy, dict):
                        economy_str = economy.get('primary') or '-'
                    else:
                        economy_str = economy or '-'
                    
                    # Format population with suffix
                    if population >= 1_000_000_000:
                        pop_str = f"{population / 1_000_000_000:.1f}B"
                    elif population >= 1_000_000:
                        pop_str = f"{population / 1_000_000:.1f}M"
                    elif population >= 1_000:
                        pop_str = f"{population / 1_000:.1f}K"
                    elif population > 0:
                        pop_str = str(population)
                    else:
                        pop_str = "-"
                    
                    # Update each value label on main thread
                    def update_labels():
                        self.sysfinder_ref_val_system.config(text=f" {system_name}")
                        self.sysfinder_ref_val_sec.config(text=f" {security}")
                        self.sysfinder_ref_val_alleg.config(text=f" {allegiance}")
                        self.sysfinder_ref_val_gov.config(text=f" {government}")
                        self.sysfinder_ref_val_eco.config(text=f" {economy_str}")
                        self.sysfinder_ref_val_pop.config(text=f" {pop_str}")
                        self.sysfinder_ref_val_state.config(text=f" {state}")
                    self.after(0, update_labels)
                else:
                    # No data available
                    def update_no_data():
                        self.sysfinder_ref_val_system.config(text=f" {system_name}")
                        self.sysfinder_ref_val_sec.config(text=" -")
                        self.sysfinder_ref_val_alleg.config(text=" -")
                        self.sysfinder_ref_val_gov.config(text=" -")
                        self.sysfinder_ref_val_eco.config(text=" -")
                        self.sysfinder_ref_val_pop.config(text=" -")
                        self.sysfinder_ref_val_state.config(text=" -")
                    self.after(0, update_no_data)
                
            except Exception as e:
                logging.error(f"[SYSTEM_FINDER] Error fetching ref system info: {e}")
                def update_error():
                    self.sysfinder_ref_val_system.config(text=f" {system_name}")
                    self.sysfinder_ref_val_sec.config(text=" Error")
                    self.sysfinder_ref_val_alleg.config(text=" -")
                    self.sysfinder_ref_val_gov.config(text=" -")
                    self.sysfinder_ref_val_eco.config(text=" -")
                    self.sysfinder_ref_val_pop.config(text=" -")
                    self.sysfinder_ref_val_state.config(text=" -")
                self.after(0, update_error)
        
        # Run in background thread to avoid blocking UI
        import threading
        thread = threading.Thread(target=fetch_info, daemon=True)
        thread.start()
    
    def _search_systems(self):
        """Search for systems matching criteria"""
        reference = self.sysfinder_reference_system.get().strip()
        if not reference:
            self.sysfinder_status_label.config(text=t('system_finder.no_system_entered'))
            return
        
        # Disable search button during search
        self.sysfinder_search_btn.config(state="disabled")
        self.sysfinder_status_label.config(text=t('system_finder.searching'))
        self.config(cursor="wait")
        self.update()
        
        # Run search in background thread
        thread = threading.Thread(target=self._search_systems_worker, daemon=True)
        thread.start()
    
    def _search_systems_worker(self):
        """Background worker for system search - uses Spansh API with server-side filtering"""
        try:
            from system_finder_api import SystemFinderAPI
            
            reference = self.sysfinder_reference_system.get().strip()
            
            print(f"[SYSTEM_FINDER DEBUG] Starting Spansh search near: {reference}")
            
            def progress_callback(current, total, message):
                self.after(0, lambda: self.sysfinder_status_label.config(text=message))
            
            # Build filters (all values are direct English, no mapping needed)
            filters = {
                'allegiance': self.sysfinder_allegiance.get(),
                'government': self.sysfinder_government.get(),
                'security': self.sysfinder_security.get(),
                'economy': self.sysfinder_economy.get(),
                'state': self.sysfinder_state.get(),
                'population': self.sysfinder_population.get(),
            }
            
            print(f"[SYSTEM_FINDER DEBUG] Filters: {filters}")
            
            # Check if any filters are active
            has_filters = any(v != 'Any' for v in filters.values())
            
            # Use new Spansh-based search with server-side filtering
            systems = SystemFinderAPI.search_systems(
                reference_system=reference,
                filters=filters,
                max_results=100,
                progress_callback=progress_callback
            )
            
            print(f"[SYSTEM_FINDER DEBUG] Spansh returned {len(systems) if systems else 0} systems")
            if systems and len(systems) > 0:
                print(f"[SYSTEM_FINDER DEBUG] First system sample: {systems[0]}")
            
            if not systems:
                self.after(0, self._sysfinder_search_complete, [], None, has_filters)
                return
            
            self.after(0, self._sysfinder_search_complete, systems, None, has_filters)
            
        except Exception as e:
            logging.error(f"[SYSTEM_FINDER] Search error: {e}")
            import traceback
            traceback.print_exc()
            self.after(0, self._sysfinder_search_complete, [], str(e), False)
    
    def _sysfinder_search_complete(self, results: list, error: str = None, had_filters: bool = False):
        """Handle search completion - update UI"""
        self.sysfinder_search_btn.config(state="normal")
        self.config(cursor="")
        
        # Clear existing results
        for item in self.sysfinder_tree.get_children():
            self.sysfinder_tree.delete(item)
        
        if error:
            self.sysfinder_status_label.config(text=f"Error: {error}")
            return
        
        if not results:
            if had_filters:
                # Filters were applied but no matches found
                self.sysfinder_status_label.config(text=t('system_finder.no_filter_results'))
            else:
                self.sysfinder_status_label.config(text=t('system_finder.no_results'))
            return
        
        # Update status
        self.sysfinder_status_label.config(
            text=t('system_finder.results_count').format(count=len(results))
        )
        
        # Populate results with alternating row colors
        for idx, system in enumerate(results):
            # Determine row tag for alternating colors
            row_tag = 'oddrow' if idx % 2 == 0 else 'evenrow'
            
            # Format population
            pop = system.get('population', 0)
            if pop >= 1_000_000_000:
                pop_str = f"{pop / 1_000_000_000:.1f}B"
            elif pop >= 1_000_000:
                pop_str = f"{pop / 1_000_000:.1f}M"
            elif pop >= 1000:
                pop_str = f"{pop / 1000:.1f}K"
            elif pop > 0:
                pop_str = str(pop)
            else:
                pop_str = "0"
            
            # Format economy - use "-" for missing data
            economy = system.get('economy', {})
            if isinstance(economy, dict):
                eco_str = economy.get('primary') or '-'
            else:
                eco_str = str(economy) if economy else '-'
            
            # Format distance
            distance = system.get('distance', 0)
            dist_str = f"{distance:.1f} ly" if distance else "0 ly"
            
            # Normalize state - show 'Normal' for systems without active state
            state_val = system.get('state', 'Normal')
            if not state_val or state_val == '-' or state_val == 'None':
                state_val = 'Normal'
            
            self.sysfinder_tree.insert("", "end", values=(
                system.get('systemName', '-'),
                dist_str,
                system.get('security', '-'),
                system.get('allegiance', '-'),
                state_val,
                pop_str,
                eco_str
            ), tags=(row_tag,))
    
    def _sort_sysfinder_column(self, column: str, numeric: bool):
        """Sort system finder results by column"""
        try:
            items = [(self.sysfinder_tree.set(item, column), item) 
                     for item in self.sysfinder_tree.get_children('')]
            
            # Toggle sort direction
            reverse = self._sysfinder_sort_reverse.get(column, False)
            self._sysfinder_sort_reverse[column] = not reverse
            
            if numeric:
                # Parse numeric values (handle "123.4 ly", "1.5B", "2.3M", etc.)
                def parse_value(val):
                    val = val.strip()
                    if not val:
                        return 0
                    # Remove ' ly' suffix for distance
                    val = val.replace(' ly', '').strip()
                    # Handle B/M/K suffixes
                    if val.endswith('B'):
                        return float(val[:-1]) * 1_000_000_000
                    elif val.endswith('M'):
                        return float(val[:-1]) * 1_000_000
                    elif val.endswith('K'):
                        return float(val[:-1]) * 1000
                    try:
                        return float(val)
                    except:
                        return 0
                
                items.sort(key=lambda x: parse_value(x[0]), reverse=reverse)
            else:
                items.sort(key=lambda x: x[0].lower(), reverse=reverse)
            
            # Rearrange items
            for index, (val, item) in enumerate(items):
                self.sysfinder_tree.move(item, '', index)
                
        except Exception as e:
            logging.error(f"[SYSTEM_FINDER] Sort error: {e}")

    def _create_marketplace_results_table(self, parent_frame):
        """Create results table for marketplace search"""
        table_frame = ttk.Frame(parent_frame, relief="solid", borderwidth=1)
        table_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Define columns with LS (light-seconds from star)
        columns = ("location", "type", "pad", "distance", "ls", "demand", "price", "updated")
        
        # Configure Marketplace Treeview style (theme-aware)
        from config import load_theme
        _mkt_theme = load_theme()
        style = ttk.Style()
        
        if _mkt_theme == "elite_orange":
            _mkt_bg = "#1e1e1e"
            _mkt_fg = "#ff8c00"
            _mkt_hdr = "#1a1a1a"
            _mkt_sel_bg = "#ff6600"
            _mkt_sel_fg = "#000000"
        else:
            _mkt_bg = "#1e1e1e"
            _mkt_fg = "#e6e6e6"
            _mkt_hdr = "#2a2a2a"
            _mkt_sel_bg = "#0078d7"
            _mkt_sel_fg = "#ffffff"
        
        # Main treeview styling
        style.configure("Marketplace.Treeview",
                       rowheight=25,
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=_mkt_bg,
                       foreground=_mkt_fg,
                       fieldbackground=_mkt_bg,
                       font=("Segoe UI", 9))
        
        # Column header styling with borders
        style.configure("Marketplace.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",  # Creates visible column separators
                       background=_mkt_hdr,
                       foreground=_mkt_fg,
                       padding=[5, 5],
                       anchor="w",
                       font=("Segoe UI", 9, "bold"))  # Left-align all headers
        
        # Row selection styling
        style.map("Marketplace.Treeview",
                 background=[('selected', _mkt_sel_bg)],
                 foreground=[('selected', _mkt_sel_fg)])
        
        # Add subtle column separation via heading relief
        style.layout("Marketplace.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])
        
        # Create Treeview with custom style
        self.marketplace_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15, style="Marketplace.Treeview")
        
        # Define headings with sorting - explicitly set anchor to left-align header text
        numeric_columns = {"distance", "ls", "demand", "price", "updated"}
        for col in columns:
            is_numeric = col in numeric_columns
            self.marketplace_tree.heading(col, text=self._get_column_title(col), 
                                         anchor="w",
                                         command=lambda c=col, n=is_numeric: self._sort_marketplace_column(c, n))
        
        # Track sort state
        self.marketplace_sort_column = None
        self.marketplace_sort_reverse = False
        
        # Set column widths - Add extra padding to create visual separation
        # Using slightly increased widths and padding to create column spacing effect
        self.marketplace_tree.column("location", width=255, minwidth=150, anchor="w", stretch=False)
        self.marketplace_tree.column("type", width=95, minwidth=70, anchor="w", stretch=False)
        self.marketplace_tree.column("pad", width=45, minwidth=40, anchor="w", stretch=False)
        self.marketplace_tree.column("distance", width=70, minwidth=55, anchor="w", stretch=False)
        self.marketplace_tree.column("ls", width=70, minwidth=50, anchor="w", stretch=False)
        self.marketplace_tree.column("demand", width=75, minwidth=55, anchor="w", stretch=False)
        self.marketplace_tree.column("price", width=125, minwidth=80, anchor="w", stretch=False)
        self.marketplace_tree.column("updated", width=95, minwidth=70, anchor="w", stretch=True)
        
        # Setup column visibility for mining commodities
        self.setup_column_visibility(
            tree=self.marketplace_tree,
            columns=columns,
            default_widths={"location": 255, "type": 95, "pad": 45, "distance": 70, "ls": 70, "demand": 75, "price": 125, "updated": 95},
            config_key='mining_commodities'
        )
        
        # Load saved column widths from config
        try:
            from config import load_commodity_market_column_widths
            saved_widths = load_commodity_market_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        self.marketplace_tree.column(col_name, width=width)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Commodity Market column widths: {e}")

        # Bind column resize event to save widths
        def save_marketplace_widths(event=None):
            try:
                from config import save_commodity_market_column_widths
                widths = {}
                for col in columns:
                    try:
                        widths[col] = self.marketplace_tree.column(col, "width")
                    except:
                        pass
                save_commodity_market_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Commodity Market column widths: {e}")
        
        self.marketplace_tree.bind("<ButtonRelease-1>", save_marketplace_widths)
        # Deselect when clicking empty space
        self.marketplace_tree.bind("<Button-1>", lambda e: self._deselect_on_empty_click(e, self.marketplace_tree))
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.marketplace_tree.yview)
        self.marketplace_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.marketplace_tree.xview)
        self.marketplace_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure row tags for visible borders (alternating with subtle lines)
        self.marketplace_tree.tag_configure('oddrow', background='#1e1e1e')
        self.marketplace_tree.tag_configure('evenrow', background='#252525')
        
        # Grid layout for treeview and scrollbars (like Ring Finder)
        self.marketplace_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        # Add right-click context menu
        self._create_marketplace_context_menu()
        # Register context menu handler for mining commodities
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['mining_commodities'] = self._show_marketplace_context_menu
        # Note: Right-click binding handled by column visibility mixin
    
    def _get_column_title(self, col):
        """Get display title for column - dynamically changes based on buy/sell mode"""
        # Check mode for demand/stock label
        is_buy_mode = self.marketplace_buy_mode.get() if hasattr(self, 'marketplace_buy_mode') else False
        
        titles = {
            "location": t('marketplace.location'),
            "type": t('marketplace.type'),
            "pad": t('marketplace.pad'),
            "distance": t('marketplace.distance'),
            "ls": "LS",
            "demand": t('marketplace.supply') if is_buy_mode else t('marketplace.demand'),  # Dynamic based on mode
            "price": t('marketplace.price'),
            "updated": t('marketplace.updated')
        }
        return titles.get(col, col)
    
    def _update_marketplace_column_headers(self):
        """Update column headers when mode changes"""
        if hasattr(self, 'marketplace_tree'):
            numeric_columns = {"distance", "ls", "demand", "price", "updated"}
            for col in ("location", "type", "pad", "distance", "ls", "demand", "price", "updated"):
                is_numeric = col in numeric_columns
                self.marketplace_tree.heading(col, text=self._get_column_title(col), 
                                            anchor="w",
                                            command=lambda c=col, n=is_numeric: self._sort_marketplace_column(c, n))
    
    def _create_marketplace_context_menu(self):
        """Create right-click context menu for marketplace results"""
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
        
        self.marketplace_context_menu = tk.Menu(self, tearoff=0,
                                               bg=menu_bg, fg=menu_fg,
                                               activebackground=menu_active_bg,
                                               activeforeground=menu_active_fg,
                                               selectcolor=menu_active_bg)
        self.marketplace_context_menu.add_command(label=t('context_menu.open_inara'), command=self._open_inara_from_menu)
        self.marketplace_context_menu.add_command(label=t('context_menu.open_edsm'), command=self._open_edsm_from_menu)
        self.marketplace_context_menu.add_command(label=t('context_menu.open_spansh'), command=self._open_spansh_from_menu)
        self.marketplace_context_menu.add_separator()
        self.marketplace_context_menu.add_command(label=t('context_menu.find_hotspots'), command=self._find_hotspots_from_marketplace)
        self.marketplace_context_menu.add_separator()
        self.marketplace_context_menu.add_command(label=t('context_menu.copy_system'), command=self._copy_marketplace_system)
    
    def _create_trade_context_menu(self):
        """Create right-click context menu for trade commodities results (without Find Hotspots)"""
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
        
        self.trade_context_menu = tk.Menu(self, tearoff=0,
                                          bg=menu_bg, fg=menu_fg,
                                          activebackground=menu_active_bg,
                                          activeforeground=menu_active_fg,
                                          selectcolor=menu_active_bg)
        self.trade_context_menu.add_command(label=t('context_menu.open_inara'), command=self._open_inara_from_trade_menu)
        self.trade_context_menu.add_command(label=t('context_menu.open_edsm'), command=self._open_edsm_from_trade_menu)
        self.trade_context_menu.add_command(label=t('context_menu.open_spansh'), command=self._open_spansh_from_trade_menu)
        self.trade_context_menu.add_separator()
        self.trade_context_menu.add_command(label=t('context_menu.copy_system'), command=self._copy_trade_system)
    
    def _open_inara_from_menu(self):
        """Open Inara station search from context menu"""
        selection = self.marketplace_tree.selection()
        if selection:
            try:
                item = selection[0]
                values = self.marketplace_tree.item(item, 'values')
                if values and len(values) > 0:
                    location = values[0]  # "System / Station"
                    if ' / ' in location:
                        system_name, station_name = location.split(' / ', 1)
                        # URL encode station name using quote_plus (converts spaces to +)
                        import urllib.parse
                        encoded_station = urllib.parse.quote_plus(station_name.strip())
                        url = f"https://inara.cz/elite/stations/?search={encoded_station}"
                        import webbrowser
                        webbrowser.open(url)
                        print(f"[MARKETPLACE] Opening Inara for station: {station_name}")
            except Exception as e:
                print(f"[MARKETPLACE] Error opening Inara: {e}")
    
    def _open_edsm_from_menu(self):
        """Open EDSM station search from context menu"""
        selection = self.marketplace_tree.selection()
        if selection:
            try:
                item = selection[0]
                values = self.marketplace_tree.item(item, 'values')
                if values and len(values) > 0:
                    location = values[0]  # "System / Station"
                    if ' / ' in location:
                        system_name, station_name = location.split(' / ', 1)
                        # URL encode station name using quote (no + for EDSM)
                        import urllib.parse
                        encoded_station = urllib.parse.quote(station_name.strip())
                        url = f"https://www.edsm.net/en/search/stations/index/name/{encoded_station}/"
                        import webbrowser
                        webbrowser.open(url)
                        print(f"[MARKETPLACE] Opening EDSM for station: {station_name}")
            except Exception as e:
                print(f"[MARKETPLACE] Error opening EDSM: {e}")
    
    def _open_spansh_from_menu(self):
        """Open Spansh system search from context menu"""
        selection = self.marketplace_tree.selection()
        if selection:
            try:
                item = selection[0]
                values = self.marketplace_tree.item(item, 'values')
                if values and len(values) > 0:
                    location = values[0]  # "System / Station"
                    if ' / ' in location:
                        system_name, station_name = location.split(' / ', 1)
                        import urllib.parse
                        import webbrowser
                        url = f"https://spansh.co.uk/search/{urllib.parse.quote(system_name.strip())}"
                        webbrowser.open(url)
                        print(f"[MARKETPLACE] Opening Spansh for system: {system_name}")
            except Exception as e:
                print(f"[MARKETPLACE] Error opening Spansh: {e}")

    def _show_marketplace_context_menu(self, event):
        """Show context menu on right-click"""
        try:
            # Select item under cursor
            item = self.marketplace_tree.identify_row(event.y)
            if item:
                self.marketplace_tree.selection_set(item)
                self.marketplace_tree.focus(item)
                self.marketplace_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.marketplace_context_menu.grab_release()
    
    def _copy_marketplace_system(self):
        """Copy system name from location column (format: 'System / Station')"""
        selection = self.marketplace_tree.selection()
        if selection:
            item = selection[0]
            values = self.marketplace_tree.item(item, 'values')
            if values and len(values) > 0:
                location = values[0]  # Location is first column
                # Extract system name (before the " / ")
                if " / " in location:
                    system_name = location.split(" / ")[0]
                    self.clipboard_clear()
                    self.clipboard_append(system_name)
                    self.marketplace_total_label.config(text=t('marketplace.copied_to_clipboard').format(system=system_name))
    
    def _find_hotspots_from_marketplace(self):
        """Open Hotspots Finder with the selected commodity to find mining locations"""
        # Get the currently selected commodity from the dropdown
        commodity_display = self.marketplace_commodity.get()
        
        # Convert localized name to English for ring finder
        commodity_english = self._commodity_rev_map.get(commodity_display, commodity_display)
        
        if not commodity_english:
            self.marketplace_total_label.config(text=t('marketplace.select_commodity'))
            return
        
        # Get the system from the selected row
        selection = self.marketplace_tree.selection()
        system_name = None
        if selection:
            item = selection[0]
            values = self.marketplace_tree.item(item, 'values')
            if values and len(values) > 0:
                location = values[0]  # Location is first column "System / Station"
                if " / " in location:
                    system_name = location.split(" / ")[0].strip()
        
        # Switch to Hotspots Finder tab
        try:
            self.notebook.select(1)  # Hotspots Finder is typically tab index 1
            
            # Set the mineral in ring finder
            if hasattr(self, 'ring_finder'):
                # Get localized mineral name for the dropdown
                from localization import get_material
                try:
                    localized_mineral = get_material(commodity_english)
                except:
                    localized_mineral = commodity_english
                
                # Set the mineral dropdown
                self.ring_finder.specific_material_var.set(localized_mineral)
                
                # Set reference system from selected row
                if system_name and hasattr(self.ring_finder, 'system_var'):
                    self.ring_finder.system_var.set(system_name)
                
                # Set Min Hotspots = 1
                if hasattr(self.ring_finder, 'min_hotspots_var'):
                    self.ring_finder.min_hotspots_var.set("1")
                
                # Set Max Distance = 100 LY
                if hasattr(self.ring_finder, 'distance_var'):
                    self.ring_finder.distance_var.set("100")
                
                # Set Max Results = All
                if hasattr(self.ring_finder, 'max_results_var'):
                    self.ring_finder.max_results_var.set("All")
                
                # Trigger search after a short delay to let UI update
                self.after(100, self.ring_finder.search_hotspots)
                
                print(f"[MARKETPLACE] Searching hotspots for {commodity_english} near {system_name or 'current system'}")
                
        except Exception as e:
            print(f"[MARKETPLACE] Error opening hotspots finder: {e}")
            import traceback
            traceback.print_exc()
    
    def _open_inara_from_trade_menu(self):
        """Open Inara station search from Trade context menu"""
        selection = self.trade_tree.selection()
        if selection:
            try:
                item = selection[0]
                values = self.trade_tree.item(item, 'values')
                if values and len(values) > 0:
                    location = values[0]  # "System / Station"
                    if ' / ' in location:
                        system_name, station_name = location.split(' / ', 1)
                        import urllib.parse
                        encoded_station = urllib.parse.quote_plus(station_name.strip())
                        url = f"https://inara.cz/elite/stations/?search={encoded_station}"
                        import webbrowser
                        webbrowser.open(url)
                        print(f"[TRADE] Opening Inara for station: {station_name}")
            except Exception as e:
                print(f"[TRADE] Error opening Inara: {e}")
    
    def _open_edsm_from_trade_menu(self):
        """Open EDSM station search from Trade context menu"""
        selection = self.trade_tree.selection()
        if selection:
            try:
                item = selection[0]
                values = self.trade_tree.item(item, 'values')
                if values and len(values) > 0:
                    location = values[0]  # "System / Station"
                    if ' / ' in location:
                        system_name, station_name = location.split(' / ', 1)
                        import urllib.parse
                        encoded_station = urllib.parse.quote(station_name.strip())
                        url = f"https://www.edsm.net/en/search/stations/index/name/{encoded_station}/"
                        import webbrowser
                        webbrowser.open(url)
                        print(f"[TRADE] Opening EDSM for station: {station_name}")
            except Exception as e:
                print(f"[TRADE] Error opening EDSM: {e}")
    
    def _open_spansh_from_trade_menu(self):
        """Open Spansh system search from Trade context menu"""
        selection = self.trade_tree.selection()
        if selection:
            try:
                item = selection[0]
                values = self.trade_tree.item(item, 'values')
                if values and len(values) > 0:
                    location = values[0]  # "System / Station"
                    if ' / ' in location:
                        system_name, station_name = location.split(' / ', 1)
                        import urllib.parse
                        import webbrowser
                        url = f"https://spansh.co.uk/search/{urllib.parse.quote(system_name.strip())}"
                        webbrowser.open(url)
                        print(f"[TRADE] Opening Spansh for system: {system_name}")
            except Exception as e:
                print(f"[TRADE] Error opening Spansh: {e}")
    
    def _show_trade_context_menu(self, event):
        """Show context menu on right-click in Trade Commodities table"""
        try:
            # Select item under cursor
            item = self.trade_tree.identify_row(event.y)
            if item:
                self.trade_tree.selection_set(item)
                self.trade_tree.focus(item)
                self.trade_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.trade_context_menu.grab_release()
    
    def _copy_trade_system(self):
        """Copy system name from Trade Commodities location column"""
        selection = self.trade_tree.selection()
        if selection:
            item = selection[0]
            values = self.trade_tree.item(item, 'values')
            if values and len(values) > 0:
                location = values[0]  # Location is first column
                # Extract system name (before the " / ")
                if " / " in location:
                    system_name = location.split(" / ")[0]
                    self.clipboard_clear()
                    self.clipboard_append(system_name)
                    self.trade_total_label.config(text=t('marketplace.copied_to_clipboard').format(system=system_name))
    
    def _populate_marketplace_system(self):
        """Auto-populate marketplace system on startup (same as ring finder)"""
        try:
            if hasattr(self, 'ring_finder'):
                self.ring_finder._auto_detect_system()
                detected_system = self.ring_finder.system_var.get()
                if detected_system:
                    self.marketplace_reference_system.set(detected_system)
        except:
            pass
    
    def _on_sell_mode_toggle(self):
        """Handle sell checkbox toggle - ensure only one mode is active"""
        if self.marketplace_sell_mode.get():
            # If sell is checked, uncheck buy
            self.marketplace_buy_mode.set(False)
        else:
            # If sell is unchecked, check buy (must have one mode active)
            self.marketplace_buy_mode.set(True)
        
        # Update column headers to reflect mode change
        self._update_marketplace_column_headers()
        
        # Update order by dropdown options for sell mode
        self._update_marketplace_order_options()
        
        # Save preference
        self._save_marketplace_preferences()
    
    def _on_buy_mode_toggle(self):
        """Handle buy checkbox toggle - ensure only one mode is active"""
        if self.marketplace_buy_mode.get():
            # If buy is checked, uncheck sell
            self.marketplace_sell_mode.set(False)
        else:
            # If buy is unchecked, check sell (must have one mode active)
            self.marketplace_sell_mode.set(True)
        
        # Update column headers to reflect mode change
        self._update_marketplace_column_headers()
        
        # Update order by dropdown options for buy mode
        self._update_marketplace_order_options()
        
        # Save preference
        self._save_marketplace_preferences()
    
    def _update_marketplace_order_options(self):
        """Update Order by dropdown options based on buy/sell mode"""
        if hasattr(self, 'marketplace_order_combo'):
            is_buy_mode = self.marketplace_buy_mode.get()
            current_value = self.marketplace_order_by.get()
            # Get English value for comparison
            current_english = self._sort_rev_map.get(current_value, current_value)
            
            if is_buy_mode:
                # Buy mode options (English keys)
                options_keys = ["Best price (lowest)", "Distance", "Best supply", "Last update"]
            else:
                # Sell mode options (English keys)
                options_keys = ["Best price (highest)", "Distance", "Best demand", "Last update"]
            
            # Convert to localized values
            options = [self._sort_options_map.get(k, k) for k in options_keys]
            self.marketplace_order_combo['values'] = options
            
            # Update current selection if it was one of the changing options
            if "Best price" in current_english or "price" in current_english.lower():
                self.marketplace_order_by.set(options[0])
            elif "supply" in current_english.lower() or "demand" in current_english.lower():
                self.marketplace_order_by.set(options[2])
            # Distance and Last update remain the same
    
    def _convert_age_to_days(self, age_str):
        """Convert max age string to days for API (API expects integer days, rounds up sub-day values)"""
        import math
        age_map = {
            "Any": 30,
            "1 hour": 1,    # API doesn't support hours, use 1 day minimum
            "8 hours": 1,   # API doesn't support hours, use 1 day minimum
            "16 hours": 1,  # API doesn't support hours, use 1 day minimum
            "1 day": 1,
            "2 days": 2
        }
        return age_map.get(age_str, 1)  # Default to 1 day
    
    def _filter_results_by_age(self, results, max_age_str):
        """Filter results by max age locally (for accurate hour-level filtering)
        
        The API only supports maxDaysAgo (integer days), so for hour-based filters
        we need to filter the results locally using the updatedAt timestamp.
        """
        from datetime import datetime, timezone, timedelta
        
        # Map age string to hours
        age_hours_map = {
            "Any": None,       # No filtering
            "1 hour": 1,
            "8 hours": 8,
            "16 hours": 16,
            "1 day": 24,
            "2 days": 48
        }
        
        max_hours = age_hours_map.get(max_age_str)
        if max_hours is None:
            return results  # No age filtering
        
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=max_hours)
        
        filtered = []
        for result in results:
            updated_at = result.get('updatedAt')
            if not updated_at:
                continue  # Skip results without timestamp
            
            try:
                # Parse ISO timestamp (e.g., "2024-11-03T12:30:00Z" or "2024-11-03T12:30:00.000Z")
                updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                if updated_time >= cutoff_time:
                    filtered.append(result)
            except Exception:
                # If parsing fails, include the result (conservative)
                filtered.append(result)
        
        return filtered
    
    def _use_current_system_marketplace(self):
        """Use current system from journal/hotspots finder for marketplace search"""
        try:
            # Use ring finder's auto-detect logic
            if hasattr(self, 'ring_finder'):
                self.ring_finder._auto_detect_system()
                detected_system = self.ring_finder.system_var.get()
                if detected_system:
                    self.marketplace_reference_system.set(detected_system)
                    return
            
            # Fallback: No ring finder available
            self._set_status("Ring finder not available. Enter system manually.")
            
        except Exception as e:
            print(f"Error getting current system: {e}")
            self._set_status("Error detecting current system. Enter system manually.")
    
    # Removed _toggle_search_mode() - reference system now always visible for both modes
    
    def _open_edtools_market(self):
        """Open edtools.cc commodity search in browser with pre-selected commodity"""
        import webbrowser
        import urllib.parse
        
        commodity = self.marketplace_commodity.get()
        system = self.marketplace_reference_system.get().strip()
        
        # edtools.cc commodity ID mapping (format: c_ID=on)
        # IDs verified from edtools.cc multi-commodity page
        edtools_commodity_ids = {
            "Platinum": "46",
            "Painite": "83",
            "Osmium": "97",
            "Low Temperature Diamonds": "276",
            "Rhodplumsite": "343",
            "Serendibite": "344",
            "Monazite": "345",
            "Musgravite": "346",
            "Benitoite": "347",
            "Grandidierite": "348",
            "Alexandrite": "349",
            "Void Opals": "350",
            # Additional common mining commodities (IDs to be verified if needed)
            "Bauxite": "396",
            "Bertrandite": "371",
            "Bromellite": "352",
            "Cobalt": "397",
            "Coltan": "398",
            "Gallite": "372",
            "Gold": "399",
            "Indite": "373",
            "Lepidolite": "354",
            "Palladium": "401",
            "Praseodymium": "374",
            "Rutile": "375",
            "Samarium": "376",
            "Silver": "402",
            "Tritium": "403",
            "Uraninite": "377"
        }
        
        # Build URL with system and commodity
        url = "https://edtools.cc/multi"
        params = []
        
        if system:
            params.append(f"s={urllib.parse.quote(system)}")
        
        # Map abbreviated commodity names back to full names for API
        commodity_mapping = {
            "LTD": "Low Temperature Diamonds"
        }
        commodity_full = commodity_mapping.get(commodity, commodity)
        
        # Add commodity using c_ID=on format
        if commodity_full and commodity_full in edtools_commodity_ids:
            commodity_id = edtools_commodity_ids[commodity_full]
            params.append(f"c_{commodity_id}=on")
        
        if params:
            url += "?" + "&".join(params)
        
        webbrowser.open(url)
        self._set_status(f"Opening edtools.cc for {commodity} near {system if system else 'Sol'}...")
        
    def _export_marketplace_results(self):
        """Export marketplace search results to CSV"""
        try:
            import csv
            from tkinter import filedialog
            
            # Get all items from tree
            items = []
            for child in self.marketplace_tree.get_children():
                values = self.marketplace_tree.item(child)['values']
                items.append(values)
            
            if not items:
                self.marketplace_total_label.config(text=t('marketplace.no_results_to_export'))
                return
            
            # Ask for save location
            file_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv")],
                title="Export Marketplace Results"
            )
            
            if file_path:
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    
                    # Write headers
                    headers = ["Location", "Station Type", "Pad", "St dist", "Distance", "Demand", "Price", "Updated"]
                    writer.writerow(headers)
                    
                    # Write data
                    writer.writerows(items)
                
                self.marketplace_total_label.config(text=t('marketplace.export_success').format(count=len(items), path=file_path))
            
        except Exception as e:
            self.marketplace_total_label.config(text=t('marketplace.export_failed').format(error=str(e)))
    
    def _clear_marketplace_cache(self):
        """Clear marketplace cache - no longer needed (using external sites)"""
        self.marketplace_total_label.config(text=t('marketplace.cache_not_needed'))
    
    def _load_marketplace_preferences(self):
        """Load all marketplace preferences from config and apply them"""
        from config import _load_cfg
        cfg = _load_cfg()
        
        # Load search mode
        if 'marketplace_search_mode' in cfg:
            self.marketplace_search_mode.set(cfg['marketplace_search_mode'])
        
        # Load buy/sell mode
        if 'marketplace_sell_mode' in cfg:
            self.marketplace_sell_mode.set(cfg['marketplace_sell_mode'])
        if 'marketplace_buy_mode' in cfg:
            self.marketplace_buy_mode.set(cfg['marketplace_buy_mode'])
        
        # Load commodity (convert English to localized)
        if 'marketplace_commodity' in cfg:
            commodity_english = cfg['marketplace_commodity']
            commodity_localized = self._commodity_map.get(commodity_english, commodity_english)
            if commodity_localized in self._commodity_map.values():
                self.marketplace_commodity.set(commodity_localized)
        
        # Load station type (convert English to localized)
        if 'marketplace_station_type' in cfg:
            station_type_english = cfg['marketplace_station_type']
            station_type_localized = self._station_type_map.get(station_type_english, station_type_english)
            if station_type_localized in self._station_type_map.values():
                self.marketplace_station_type.set(station_type_localized)
        
        # Load checkboxes
        if 'marketplace_exclude_carriers' in cfg:
            self.marketplace_exclude_carriers.set(cfg['marketplace_exclude_carriers'])
        if 'marketplace_large_pad_only' in cfg:
            self.marketplace_large_pad_only.set(cfg['marketplace_large_pad_only'])
        
        # Load order by (convert English to localized)
        if 'marketplace_order_by' in cfg:
            order_by_english = cfg['marketplace_order_by']
            order_by_localized = self._sort_options_map.get(order_by_english, order_by_english)
            if order_by_localized in self._sort_options_map.values():
                self.marketplace_order_by.set(order_by_localized)
        
        # Load max age (convert English to localized)
        if 'marketplace_max_age' in cfg:
            max_age_english = cfg['marketplace_max_age']
            max_age_localized = self._age_map.get(max_age_english, max_age_english)
            if max_age_localized in self._age_map.values():
                self.marketplace_max_age.set(max_age_localized)
    
    def _save_marketplace_preferences(self):
        """Save all marketplace preferences to config"""
        from config import update_config_values
        # Convert localized values back to English for saving
        station_type_english = self._station_type_rev_map.get(self.marketplace_station_type.get(), self.marketplace_station_type.get())
        order_by_english = self._sort_rev_map.get(self.marketplace_order_by.get(), self.marketplace_order_by.get())
        max_age_english = self._age_rev_map.get(self.marketplace_max_age.get(), self.marketplace_max_age.get())
        commodity_english = self._commodity_rev_map.get(self.marketplace_commodity.get(), self.marketplace_commodity.get())
        updates = {
            "marketplace_search_mode": str(self.marketplace_search_mode.get()),
            "marketplace_sell_mode": bool(self.marketplace_sell_mode.get()),
            "marketplace_buy_mode": bool(self.marketplace_buy_mode.get()),
            "marketplace_reference_system": str(self.marketplace_reference_system.get()),
            "marketplace_commodity": commodity_english,
            "marketplace_station_type": station_type_english,
            "marketplace_exclude_carriers": bool(self.marketplace_exclude_carriers.get()),
            "marketplace_large_pad_only": bool(self.marketplace_large_pad_only.get()),
            "marketplace_order_by": order_by_english,
            "marketplace_max_age": max_age_english
        }
        update_config_values(updates)
    
    # ==================== TRADE COMMODITIES TAB HELPERS ====================
    def _on_trade_category_changed(self, event=None):
        """Update commodity list when category changes"""
        self._update_trade_commodity_list()
        self._save_trade_preferences()
    
    def _update_trade_commodity_list(self):
        """Populate commodity dropdown based on selected category"""
        category = self.trade_category.get()
        if category in self.commodities_data:
            commodities = sorted(self.commodities_data[category])
            self.trade_commodity_combo['values'] = commodities
            # Select first commodity if current value not in new list
            current = self.trade_commodity.get()
            if current not in commodities and commodities:
                self.trade_commodity.set(commodities[0])
    
    def _on_trade_sell_mode_toggle(self):
        """Handle sell mode toggle for trade tab"""
        if not self.trade_sell_mode.get():
            self.trade_sell_mode.set(True)
        else:
            self.trade_buy_mode.set(False)
        self._update_trade_order_options()
        self._save_trade_preferences()
    
    def _on_trade_buy_mode_toggle(self):
        """Handle buy mode toggle for trade tab"""
        if not self.trade_buy_mode.get():
            self.trade_buy_mode.set(True)
        else:
            self.trade_sell_mode.set(False)
        self._update_trade_order_options()
        self._save_trade_preferences()
    
    def _update_trade_order_options(self):
        """Update sort options based on sell/buy mode for trade tab"""
        if self.trade_sell_mode.get():
            sort_order = ['Best price (highest)', 'Distance', 'Best demand', 'Last update']
        else:
            sort_order = ['Best price (lowest)', 'Distance', 'Best stock', 'Last update']
        self.trade_order_combo['values'] = [self._trade_sort_options_map.get(k, k) for k in sort_order]
    
    def _use_current_system_trade(self):
        """Fill trade reference system with current system"""
        if self.current_system:
            self.trade_reference_system.set(self.current_system)
            self._save_trade_preferences()
    
    def _load_trade_preferences(self):
        """Load all trade preferences from config and apply them"""
        from config import _load_cfg
        cfg = _load_cfg()
        
        # Load search mode
        if 'trade_search_mode' in cfg:
            self.trade_search_mode.set(cfg['trade_search_mode'])
        
        # Load buy/sell mode
        if 'trade_sell_mode' in cfg:
            self.trade_sell_mode.set(cfg['trade_sell_mode'])
        if 'trade_buy_mode' in cfg:
            self.trade_buy_mode.set(cfg['trade_buy_mode'])
        
        # Load category and update commodity list
        if 'trade_category' in cfg:
            category = cfg['trade_category']
            if category in self._trade_categories:
                self.trade_category.set(category)
                self._update_trade_commodity_list()
        
        # Load commodity
        if 'trade_commodity' in cfg:
            commodity = cfg['trade_commodity']
            # Check if commodity is in current category's list
            current_values = self.trade_commodity_combo['values']
            if commodity in current_values:
                self.trade_commodity.set(commodity)
        
        # Load station type (convert English to localized)
        if 'trade_station_type' in cfg:
            station_type_english = cfg['trade_station_type']
            station_type_localized = self._trade_station_type_map.get(station_type_english, station_type_english)
            if station_type_localized in self._trade_station_type_map.values():
                self.trade_station_type.set(station_type_localized)
        
        # Load checkboxes
        if 'trade_exclude_carriers' in cfg:
            self.trade_exclude_carriers.set(cfg['trade_exclude_carriers'])
        if 'trade_large_pad_only' in cfg:
            self.trade_large_pad_only.set(cfg['trade_large_pad_only'])
        
        # Load order by (convert English to localized)
        if 'trade_order_by' in cfg:
            order_by_english = cfg['trade_order_by']
            order_by_localized = self._trade_sort_options_map.get(order_by_english, order_by_english)
            if order_by_localized in self._trade_sort_options_map.values():
                self.trade_order_by.set(order_by_localized)
        
        # Load max age (convert English to localized)
        if 'trade_max_age' in cfg:
            max_age_english = cfg['trade_max_age']
            max_age_localized = self._trade_age_map.get(max_age_english, max_age_english)
            if max_age_localized in self._trade_age_map.values():
                self.trade_max_age.set(max_age_localized)
    
    def _save_trade_preferences(self):
        """Save all trade preferences to config"""
        from config import update_config_values
        station_type_english = self._trade_station_type_rev_map.get(self.trade_station_type.get(), self.trade_station_type.get())
        order_by_english = self._trade_sort_rev_map.get(self.trade_order_by.get(), self.trade_order_by.get())
        max_age_english = self._trade_age_rev_map.get(self.trade_max_age.get(), self.trade_max_age.get())
        updates = {
            "trade_search_mode": str(self.trade_search_mode.get()),
            "trade_sell_mode": bool(self.trade_sell_mode.get()),
            "trade_buy_mode": bool(self.trade_buy_mode.get()),
            "trade_reference_system": str(self.trade_reference_system.get()),
            "trade_category": str(self.trade_category.get()),
            "trade_commodity": str(self.trade_commodity.get()),
            "trade_station_type": station_type_english,
            "trade_exclude_carriers": bool(self.trade_exclude_carriers.get()),
            "trade_large_pad_only": bool(self.trade_large_pad_only.get()),
            "trade_order_by": order_by_english,
            "trade_max_age": max_age_english
        }
        update_config_values(updates)
    
    def _search_trade_market(self):
        """Search for trade commodity prices using same backend as mining commodities"""
        try:
            self._save_trade_preferences()
            
            commodity = self.trade_commodity.get()
            search_mode = self.trade_search_mode.get()
            
            if not commodity:
                self.trade_total_label.config(text=t('marketplace.select_commodity'))
                return
            
            if search_mode == "near_system":
                ref_system = self.trade_reference_system.get().strip()
                if not ref_system:
                    self.trade_total_label.config(text=t('marketplace.enter_system'))
                    return
            
            # Show searching status
            is_buy_mode = self.trade_buy_mode.get()
            if is_buy_mode:
                self.trade_total_label.config(text=t('marketplace.searching_buying'))
            else:
                self.trade_total_label.config(text=t('marketplace.searching_selling'))
            self.config(cursor="watch")
            self.update()
            
            # Run search in background thread to prevent UI freeze
            import threading
            def search_thread():
                try:
                    # Convert max age to days
                    max_age_str = self._trade_age_rev_map.get(self.trade_max_age.get(), self.trade_max_age.get())
                    max_days_ago = self._convert_age_to_days(max_age_str)
                    
                    # Determine buy/sell mode
                    is_buy_mode = self.trade_buy_mode.get()
                    is_sell_mode = self.trade_sell_mode.get()
                    
                    # Get exclude carriers setting
                    exclude_carriers = self.trade_exclude_carriers.get()
                    
                    # Call appropriate API based on search mode and buy/sell mode
                    if search_mode == "galaxy_wide":
                        if is_buy_mode:
                            results = MarketplaceAPI.search_sellers_galaxy_wide(commodity, max_days_ago, exclude_carriers)
                        else:
                            results = MarketplaceAPI.search_buyers_galaxy_wide(commodity, max_days_ago, exclude_carriers)
                    else:
                        reference_system = self.trade_reference_system.get().strip()
                        if is_buy_mode:
                            results = MarketplaceAPI.search_sellers(commodity, reference_system, None, max_days_ago, exclude_carriers)
                        else:
                            results = MarketplaceAPI.search_buyers(commodity, reference_system, None, max_days_ago)
                    
                    # Update UI in main thread with results
                    self.after(0, lambda: self._process_trade_search_results(results, search_mode, is_buy_mode, max_age_str))
                except Exception as e:
                    log.error(f"Trade search failed: {e}")
                    self.after(0, lambda: self._trade_search_error(str(e)))
            
            thread = threading.Thread(target=search_thread, daemon=True)
            thread.start()
            
        except Exception as e:
            log.error(f"Trade search failed: {e}")
            self.trade_total_label.config(text=f"Error: {str(e)}")
            self.config(cursor="")
    
    def _process_trade_search_results(self, results: list, search_mode: str, is_buy_mode: bool, max_age_str: str):
        """Process and display trade search results (runs on main thread)"""
        try:
            # Apply filters
            station_type_filter = self._trade_station_type_rev_map.get(self.trade_station_type.get(), self.trade_station_type.get())
            original_count = len(results)
            
            # Filter out stations with 0 demand/stock
            if is_buy_mode:
                results = [r for r in results if r.get('stock', 0) > 0]
            else:
                results = [r for r in results if r.get('demand', 0) > 0]
            
            # Filter by Fleet Carriers
            exclude_carriers = self.trade_exclude_carriers.get()
            if exclude_carriers and station_type_filter != "Fleet Carrier":
                results = [r for r in results if "FleetCarrier" not in (r.get('stationType') or '')]
            
            # Filter by Station Type
            if station_type_filter == "Orbital":
                # Debug: Print unique station types to understand API format
                unique_types = set(r.get('stationType', 'None') for r in results[:50])
                print(f"[DEBUG Trade Filter] Sample station types before orbital filter: {unique_types}")
                
                # Orbital stations - use substring match but exclude Surface types
                orbital_keywords = ["Coriolis", "Orbis", "Ocellus", "Outpost", "AsteroidBase", "Asteroid", "Dodec"]
                surface_keywords = ["Crater", "OnFoot", "Planetary", "Surface"]
                results = [r for r in results 
                          if any(keyword in (r.get('stationType') or '') for keyword in orbital_keywords)
                          and not any(surface_kw in (r.get('stationType') or '') for surface_kw in surface_keywords)]
                
                print(f"[DEBUG Trade Filter] After orbital filter: {len(results)} stations")
            elif station_type_filter == "Surface":
                # Surface stations - use substring match for variants
                surface_keywords = ["Crater", "OnFoot", "Planetary", "Surface"]
                results = [r for r in results if any(keyword in (r.get('stationType') or '') for keyword in surface_keywords)]
            elif station_type_filter == "Fleet Carrier":
                # Fleet Carriers - use substring match
                results = [r for r in results if "FleetCarrier" in (r.get('stationType') or '') or "Carrier" in (r.get('stationType') or '')]
            elif station_type_filter == "Megaship":
                # MegaShips - use substring match
                results = [r for r in results if "Mega" in (r.get('stationType') or '') or "MegaShip" in (r.get('stationType') or '')]
            elif station_type_filter == "Stronghold":
                # Stronghold Carriers - use substring match
                results = [r for r in results if "Stronghold" in (r.get('stationType') or '')]
            
            # Filter by Landing Pad Size
            large_pad_only = self.trade_large_pad_only.get()
            if large_pad_only:
                results = [r for r in results if r.get('maxLandingPadSize') == 3]
            
            # Filter by Max Age
            results = self._filter_results_by_age(results, max_age_str)
            
            if results:
                # Sort results
                order_by = self._trade_sort_rev_map.get(self.trade_order_by.get(), self.trade_order_by.get())
                
                if "Distance" in order_by:
                    results_sorted = sorted(results, key=lambda x: x.get('distance', 999999), reverse=False)
                elif "Best price" in order_by:
                    if is_buy_mode:
                        results_sorted = sorted(results, key=lambda x: x.get('sellPrice', 999999), reverse=False)
                    else:
                        results_sorted = sorted(results, key=lambda x: x.get('sellPrice', 0), reverse=True)
                elif "supply" in order_by or "demand" in order_by:
                    results_sorted = sorted(results, key=lambda x: x.get('demand', 0), reverse=True)
                elif "Last update" in order_by:
                    results_sorted = sorted(results, key=lambda x: x.get('updatedAt', ''), reverse=True)
                else:
                    results_sorted = sorted(results, key=lambda x: x.get('distance', 999999), reverse=False)
                
                # Display results using trade table (separate from mining table)
                if search_mode == "galaxy_wide":
                    reference_system = self.trade_reference_system.get().strip()
                    if reference_system:
                        self._display_trade_results(results_sorted[:30])
                        self.trade_total_label.config(text=t('marketplace.calculating_distances'))
                        self.config(cursor="watch")
                        self.update_idletasks()
                        
                        import threading
                        def calculate_distances_thread():
                            try:
                                top_30 = results_sorted[:30]
                                top_30_with_dist = MarketplaceAPI.add_distances_to_results(top_30, reference_system)
                                self.after(0, lambda: self._update_trade_with_distances(top_30_with_dist, len(results)))
                            except Exception as e:
                                print(f"[TRADE] Distance calculation error: {e}")
                                self.after(0, lambda: self._restore_trade_cursor(len(results)))
                        
                        thread = threading.Thread(target=calculate_distances_thread, daemon=True)
                        thread.start()
                    else:
                        self._display_trade_results(results_sorted[:30])
                        self.trade_total_label.config(text=t('marketplace.found_stations_top30_price').format(count=len(results)))
                        self.config(cursor="")
                elif search_mode == "near_system":
                    self._display_trade_results(results_sorted[:30])
                    self.trade_total_label.config(text=t('marketplace.found_stations_top30_price').format(count=len(results)))
                    self.config(cursor="")
            else:
                self._clear_trade_results()
                self.config(cursor="")
                if original_count > 0:
                    self.trade_total_label.config(text=t('marketplace.no_results_after_filter'))
                else:
                    self.trade_total_label.config(text=t('marketplace.no_results'))
                    
        except Exception as e:
            log.error(f"Trade search results processing failed: {e}")
            self.trade_total_label.config(text=f"Error: {str(e)}")
            self.config(cursor="")
    
    def _trade_search_error(self, error_msg: str):
        """Handle trade search error (runs on main thread)"""
        self.trade_total_label.config(text=f"Error: {error_msg}")
        self.config(cursor="")
    
    def _update_trade_with_distances(self, results_with_distances: list, total_count: int):
        """Update trade results with calculated distances"""
        self._display_trade_results(results_with_distances)
        self.trade_total_label.config(text=t('marketplace.found_stations_top30_price').format(count=total_count))
        self.config(cursor="")
    
    def _restore_trade_cursor(self, total_count: int):
        """Restore cursor after distance calculation error"""
        self.trade_total_label.config(text=t('marketplace.found_stations_top30_price').format(count=total_count))
        self.config(cursor="")
    
    def _perform_trade_search(self, commodity: str, search_mode: str):
        """Perform the actual trade commodity search"""
        # This function is no longer used - _search_trade_market() handles everything
        pass
    
    def _create_trade_results_table(self, parent_frame):
        """Create results table for trade commodities - separate from mining table"""
        # Create own table frame
        table_frame = tk.Frame(parent_frame, bg="#1a1a1a")
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Column definitions - same structure as marketplace with LS column
        columns = ("location", "type", "pad", "distance", "ls", "demand", "price", "updated")
        
        # Create separate Treeview for trade tab
        self.trade_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15, style="Marketplace.Treeview")
        
        # Define headings with sorting
        numeric_columns = {"distance", "ls", "demand", "price", "updated"}
        for col in columns:
            is_numeric = col in numeric_columns
            self.trade_tree.heading(col, text=self._get_column_title(col), 
                                    anchor="w",
                                    command=lambda c=col, n=is_numeric: self._sort_trade_column(c, n))
        
        # Track sort state
        self.trade_sort_column = None
        self.trade_sort_reverse = False
        
        # Set column widths
        self.trade_tree.column("location", width=255, minwidth=150, anchor="w", stretch=False)
        self.trade_tree.column("type", width=95, minwidth=70, anchor="w", stretch=False)
        self.trade_tree.column("pad", width=45, minwidth=40, anchor="w", stretch=False)
        self.trade_tree.column("distance", width=70, minwidth=55, anchor="w", stretch=False)
        self.trade_tree.column("ls", width=70, minwidth=50, anchor="w", stretch=False)
        self.trade_tree.column("demand", width=75, minwidth=55, anchor="w", stretch=False)
        self.trade_tree.column("price", width=125, minwidth=80, anchor="w", stretch=False)
        self.trade_tree.column("updated", width=95, minwidth=70, anchor="w", stretch=True)
        
        # Setup column visibility for trade commodities
        self.setup_column_visibility(
            tree=self.trade_tree,
            columns=columns,
            default_widths={"location": 255, "type": 95, "pad": 45, "distance": 70, "ls": 70, "demand": 75, "price": 125, "updated": 95},
            config_key='trade_commodities'
        )
        
        # Load saved column widths from config
        try:
            from config import load_trade_commodities_column_widths
            saved_widths = load_trade_commodities_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        self.trade_tree.column(col_name, width=width)
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Trade Commodities column widths: {e}")

        # Bind column resize event to save widths
        def save_trade_widths(event=None):
            try:
                from config import save_trade_commodities_column_widths
                widths = {}
                for col in columns:
                    try:
                        widths[col] = self.trade_tree.column(col, "width")
                    except:
                        pass
                save_trade_commodities_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Trade Commodities column widths: {e}")
        
        self.trade_tree.bind("<ButtonRelease-1>", save_trade_widths)
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.trade_tree.xview)
        self.trade_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure row tags for alternating colors
        self.trade_tree.tag_configure('oddrow', background='#1e1e1e')
        self.trade_tree.tag_configure('evenrow', background='#252525')
        
        # Grid layout for treeview and scrollbars (like Mining Commodities)
        self.trade_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        # Add right-click context menu
        self._create_trade_context_menu()
        # Register context menu handler for trade commodities
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['trade_commodities'] = self._show_trade_context_menu
        # Note: Right-click binding handled by column visibility mixin
    
    def _sort_trade_column(self, col: str, is_numeric: bool):
        """Sort trade results table by column"""
        # Toggle sort direction
        if self.trade_sort_column == col:
            self.trade_sort_reverse = not self.trade_sort_reverse
        else:
            self.trade_sort_column = col
            self.trade_sort_reverse = False
        
        # Get all items
        items = [(self.trade_tree.set(item, col), item) for item in self.trade_tree.get_children('')]
        
        # Sort items
        if is_numeric:
            def parse_value(val):
                try:
                    # Handle "?" for unknown values
                    if val == '?':
                        return 999999
                    # Remove commas and spaces, handle distance like "123 LY"
                    val = val.replace(' LY', '').replace(',', '').strip()
                    return float(val) if val and val != '-' else 999999
                except:
                    return 999999
            items.sort(key=lambda x: parse_value(x[0]), reverse=self.trade_sort_reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=self.trade_sort_reverse)
        
        # Rearrange items
        for index, (val, item) in enumerate(items):
            self.trade_tree.move(item, '', index)
    
    def _display_trade_results(self, results: list):
        """Display trade search results in trade table"""
        # Clear existing results
        for item in self.trade_tree.get_children():
            self.trade_tree.delete(item)
        
        # Determine mode for correct field handling
        is_buy_mode = self.trade_buy_mode.get()
        
        # Display results
        for result in results:
            # LOCATION (System + Station)
            location = f"{result.get('systemName', 'Unknown')} / {result.get('stationName', 'Unknown')[:25]}"
            
            # TYPE (Station type)
            api_type = result.get('stationType')
            if api_type is None or api_type == '':
                api_type = 'Unknown'
            
            if api_type == 'AsteroidBase':
                station_type = 'Orbital/Asteroid'
            elif api_type in ['Coriolis', 'Orbis', 'Ocellus', 'Outpost', 'Dodec']:
                station_type = f'Orbital/{api_type}'
            elif api_type == 'CraterOutpost':
                station_type = 'Surface/Crater'
            elif api_type == 'CraterPort':
                station_type = 'Surface/Port'
            elif api_type == 'SurfaceStation':
                station_type = 'Surface Station'
            elif api_type == 'OnFootSettlement':
                station_type = 'Surface/OnFoot'
            elif api_type == 'FleetCarrier':
                station_type = 'Carrier'
            elif api_type == 'StrongholdCarrier':
                station_type = 'Stronghold'
            elif api_type == 'MegaShip':
                station_type = 'MegaShip'
            else:
                station_type = api_type
            
            # PAD (Landing pad size)
            pad_size = result.get('maxLandingPadSize')
            if isinstance(pad_size, int):
                pad_map = {0: '?', 1: 'S', 2: 'M', 3: 'L'}
                pad = pad_map.get(pad_size, '?')
            elif isinstance(pad_size, str):
                pad = pad_size.upper()
            else:
                pad = '?'
            
            # DISTANCE
            if 'distance' in result and result['distance'] is not None:
                distance = f"{result['distance']:.1f}"
            else:
                distance = "-"
            
            # LS (Station distance from star)
            station_ls = result.get('distanceToArrival')
            if station_ls is not None:
                # 0 is valid for fleet carriers at arrival point
                ls = f"{int(station_ls):,}"
            else:
                ls = "?"
            
            # DEMAND/STOCK
            if is_buy_mode:
                volume = f"{result.get('stock', 0):,}" if result.get('stock', 0) > 0 else "0"
            else:
                volume = f"{result.get('demand', 0):,}" if result.get('demand', 0) > 0 else "0"
            
            # PRICE
            if is_buy_mode:
                price = f"{result.get('buyPrice', 0):,} CR"
            else:
                price = f"{result.get('sellPrice', 0):,} CR"
            
            # UPDATED (Data age)
            updated_at = result.get('updatedAt', '')
            if updated_at:
                try:
                    from datetime import datetime, timezone
                    updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    now = datetime.now(timezone.utc)
                    diff = now - updated_time
                    total_minutes = diff.total_seconds() / 60
                    if total_minutes < 60:
                        updated = f"{int(total_minutes)}m"
                    elif total_minutes < 1440:
                        updated = f"{int(total_minutes / 60)}h"
                    else:
                        updated = f"{int(total_minutes / 1440)}d"
                except Exception:
                    updated = '-'
            else:
                updated = '-'
            
            # Insert row
            self.trade_tree.insert('', 'end', values=(
                f" {location} ",
                f" {station_type} ",
                f" {pad} ",
                f" {distance} ",
                f" {ls} ",
                f" {volume} ",
                f" {price} ",
                f" {updated} "
            ))
    
    def _clear_trade_results(self):
        """Clear trade results table"""
        if hasattr(self, 'trade_tree'):
            for item in self.trade_tree.get_children():
                self.trade_tree.delete(item)
    
    # ==================== UNUSED MARKETPLACE SEARCH METHODS (Kept for reference) ====================
    # These methods are no longer used - marketplace now uses external websites (Inara, edtools.cc)
    # Kept here temporarily in case rollback is needed
    
    def _search_marketplace(self):
        """Search for commodity prices using Ardent API"""
        try:
            # Save current search parameters
            self._save_marketplace_preferences()
            
            # Convert localized commodity name to English for API
            commodity_display = self.marketplace_commodity.get()
            commodity = self._commodity_rev_map.get(commodity_display, commodity_display)
            search_mode = self.marketplace_search_mode.get()
            
            # Validation
            if not commodity:
                self.marketplace_total_label.config(text=t('marketplace.select_commodity'))
                return
            
            # Mode-specific validation
            if search_mode == "near_system":
                reference_system = self.marketplace_reference_system.get().strip()
                if not reference_system:
                    self.marketplace_total_label.config(text=t('marketplace.enter_reference_system'))
                    return
            
            # Convert max age to days
            max_age_str = self._age_rev_map.get(self.marketplace_max_age.get(), self.marketplace_max_age.get())
            max_days_ago = self._convert_age_to_days(max_age_str)
            
            # Determine buy/sell mode
            is_buy_mode = self.marketplace_buy_mode.get()
            is_sell_mode = self.marketplace_sell_mode.get()
            
            # Get exclude carriers setting
            exclude_carriers = self.marketplace_exclude_carriers.get()
            
            # Show searching status
            if is_buy_mode:
                self.marketplace_total_label.config(text=t('marketplace.searching_buying'))
            else:
                self.marketplace_total_label.config(text=t('marketplace.searching_selling'))
            self.update()
            
            # Call appropriate API based on search mode and buy/sell mode
            if search_mode == "galaxy_wide":
                # Galaxy-wide search
                if is_buy_mode:
                    results = MarketplaceAPI.search_sellers_galaxy_wide(commodity, max_days_ago, exclude_carriers)
                else:
                    results = MarketplaceAPI.search_buyers_galaxy_wide(commodity, max_days_ago, exclude_carriers)
            else:
                # Near system search (within 500 LY)
                reference_system = self.marketplace_reference_system.get().strip()
                if is_buy_mode:
                    results = MarketplaceAPI.search_sellers(commodity, reference_system, None, max_days_ago, exclude_carriers)
                else:
                    results = MarketplaceAPI.search_buyers(commodity, reference_system, None, max_days_ago)
            
            # Apply filters
            exclude_carriers = self.marketplace_exclude_carriers.get()
            station_type_filter = self._station_type_rev_map.get(self.marketplace_station_type.get(), self.marketplace_station_type.get())
            
            # Track original count before filtering for better error messages
            original_count = len(results)
            
            # Filter out stations with 0 demand/stock (belt and suspenders - API should handle this via minVolume but add safety check)
            if is_buy_mode:
                # Buy mode (exports endpoint): filter out stations with 0 stock
                results = [r for r in results if r.get('stock', 0) > 0]
            else:
                # Sell mode (imports endpoint): filter out stations with 0 demand
                results = [r for r in results if r.get('demand', 0) > 0]
            
            # Filter by Fleet Carriers (applies to both buy and sell modes)
            if exclude_carriers and station_type_filter != "Fleet Carrier":
                results = [r for r in results if "FleetCarrier" not in (r.get('stationType') or '')]
            
            # Filter by Station Type (Surface/Orbital/Carrier/MegaShip/Stronghold)
            # NOTE: Stations with null stationType (Unknown) are only shown when filter is "All"
            # This is correct behavior - we can't categorize stations without metadata
            if station_type_filter == "Orbital":
                # Orbital stations - use substring match but exclude Surface types
                orbital_keywords = ["Coriolis", "Orbis", "Ocellus", "Outpost", "AsteroidBase", "Asteroid", "Dodec"]
                surface_keywords = ["Crater", "OnFoot", "Planetary", "Surface"]
                results = [r for r in results 
                          if any(keyword in (r.get('stationType') or '') for keyword in orbital_keywords)
                          and not any(surface_kw in (r.get('stationType') or '') for surface_kw in surface_keywords)]
            elif station_type_filter == "Surface":
                # Surface stations - use substring match for variants
                surface_keywords = ["Crater", "OnFoot", "Planetary", "Surface"]
                results = [r for r in results if any(keyword in (r.get('stationType') or '') for keyword in surface_keywords)]
            elif station_type_filter == "Fleet Carrier":
                # Fleet Carriers - use substring match
                results = [r for r in results if "FleetCarrier" in (r.get('stationType') or '') or "Carrier" in (r.get('stationType') or '')]
            elif station_type_filter == "Megaship":
                # MegaShips - use substring match
                results = [r for r in results if "Mega" in (r.get('stationType') or '') or "MegaShip" in (r.get('stationType') or '')]
            elif station_type_filter == "Stronghold":
                # Stronghold Carriers - use substring match
                results = [r for r in results if "Stronghold" in (r.get('stationType') or '')]
            
            # Filter by Landing Pad Size (Large only if checked)
            large_pad_only = self.marketplace_large_pad_only.get()
            
            if large_pad_only:
                # Only show stations with Large pads (maxLandingPadSize == 3)
                results = [r for r in results if r.get('maxLandingPadSize') == 3]
            
            # Filter by Max Age (local filtering for hour-based options since API only supports days)
            # This provides accurate hour-level filtering that the API cannot do
            results = self._filter_results_by_age(results, max_age_str)
            
            if results:
                # Sort results based on "Order by" selection
                order_by = self._sort_rev_map.get(self.marketplace_order_by.get(), self.marketplace_order_by.get())
                
                if "Distance" in order_by:
                    # Sort by distance (nearest first)
                    results_sorted = sorted(results, key=lambda x: x.get('distance', 999999), reverse=False)
                elif "Best price" in order_by:
                    # Sort by price - depends on buy/sell mode
                    if is_buy_mode:
                        # Buy mode: lowest sellPrice first (cheapest to buy from)
                        results_sorted = sorted(results, key=lambda x: x.get('sellPrice', 999999), reverse=False)
                    else:
                        # Sell mode: highest sellPrice first (best price to sell to)
                        results_sorted = sorted(results, key=lambda x: x.get('sellPrice', 0), reverse=True)
                elif "supply" in order_by or "demand" in order_by:
                    # Sort by supply/demand (highest first)
                    results_sorted = sorted(results, key=lambda x: x.get('demand', 0), reverse=True)
                elif "Last update" in order_by:
                    # Sort by most recent update (newest first)
                    results_sorted = sorted(results, key=lambda x: x.get('updatedAt', ''), reverse=True)
                else:
                    # Default: sort by distance
                    results_sorted = sorted(results, key=lambda x: x.get('distance', 999999), reverse=False)
                
                # For galaxy-wide mode, calculate distances for top 30 results in background
                if search_mode == "galaxy_wide":
                    reference_system = self.marketplace_reference_system.get().strip()
                    if reference_system:
                        # Show results immediately without distances
                        self._display_marketplace_results(results_sorted[:30])
                        self.marketplace_total_label.config(text=t('marketplace.calculating_distances'))
                        self.config(cursor="watch")
                        self.update_idletasks()
                        
                        # Start distance calculation in background thread
                        import threading
                        def calculate_distances_thread():
                            try:
                                top_30 = results_sorted[:30]
                                top_30_with_dist = MarketplaceAPI.add_distances_to_results(top_30, reference_system)
                                # Update UI in main thread
                                self.after(0, lambda: self._update_marketplace_with_distances(top_30_with_dist, len(results)))
                            except Exception as e:
                                print(f"[MARKETPLACE] Distance calculation error: {e}")
                                self.after(0, lambda: self._restore_marketplace_cursor(len(results)))
                        
                        thread = threading.Thread(target=calculate_distances_thread, daemon=True)
                        thread.start()
                        # Results already displayed above, skip default display
                    else:
                        # No reference system - show without distances
                        self._display_marketplace_results(results_sorted[:30])
                        self.marketplace_total_label.config(text=t('marketplace.found_stations_top30_price').format(count=len(results)))
                elif search_mode == "near_system":
                    # Near system: show top 30 by price (already sorted by distance in API)
                    self._display_marketplace_results(results_sorted[:30])
                    self.marketplace_total_label.config(text=t('marketplace.found_stations_top30_price').format(count=len(results)))
            else:
                # No results after filtering - clear the table and show message
                self._clear_marketplace_results()
                
                # Check if we had results before filtering
                if original_count > 0:
                    # We had results but filtered them all out
                    if exclude_carriers:
                        self.marketplace_total_label.config(
                            text=t('marketplace.all_fleet_carriers').format(count=original_count)
                        )
                    else:
                        self.marketplace_total_label.config(
                            text=t('marketplace.no_match_filters').format(count=original_count)
                        )
                else:
                    # No results from API at all
                    self.marketplace_total_label.config(text=t('marketplace.no_results'))
                
        except Exception as e:
            self.marketplace_total_label.config(text=t('marketplace.search_failed').format(error=str(e)))
    
    def _marketplace_search_worker(self, commodity, reference_system, max_dist, station_type, max_results, price_age):
        """Background worker for marketplace search to prevent UI hanging"""
        try:
            # Clear existing results on UI thread
            self.after(0, self._clear_marketplace_results)
            
            # Perform search with timeout
            results = []
            try:
                # Use a simplified search with fewer API calls - ignore max_dist (user can sort results)
                results = self._quick_marketplace_search(commodity, reference_system, max_results * 2, None, price_age)
            except Exception as search_error:
                self.after(0, lambda: self.marketplace_total_label.config(
                    text=f"❌ Search failed: {str(search_error)}"
                ))
                return
            
            if not results:
                self.after(0, lambda: self.marketplace_total_label.config(
                    text="❌ No selling stations found"
                ))
                return
            
            # Filter by station type
            if station_type == "Large Landing Pads":
                results = [r for r in results if self._has_large_pads(r.get('station_type', ''))]
            elif station_type == "Medium Landing Pads":
                results = [r for r in results if self._has_medium_pads(r.get('station_type', ''))]
            elif station_type == "Small Landing Pads":
                results = [r for r in results if self._has_small_pads(r.get('station_type', ''))]
            elif station_type == "Fleet Carriers Only":
                results = [r for r in results if "Fleet Carrier" in r.get('station_type', '')]
            elif station_type == "Surface Stations Only":
                results = [r for r in results if self._is_surface_station(r.get('station_type', ''))]
            elif station_type == "Space Stations Only":
                results = [r for r in results if self._is_space_station(r.get('station_type', ''))]
            elif station_type == "Odyssey Settlements Only":
                results = [r for r in results if "Odyssey Settlement" in r.get('station_type', '')]
            elif station_type == "Regular Stations (No Carriers)":
                results = [r for r in results if "Fleet Carrier" not in r.get('station_type', '')]
            
            # Remove duplicates - prioritize newest data first, then best price
            unique_results = {}
            for result in results:
                station_key = f"{result['system_name']}_{result['station_name']}"
                
                if station_key not in unique_results:
                    unique_results[station_key] = result
                else:
                    # Compare by update time first (newer is better)
                    current_updated = result.get('updated', 'Unknown')
                    existing_updated = unique_results[station_key].get('updated', 'Unknown')
                    
                    # Convert update strings to comparable values (hours as numbers)
                    def parse_update_time(update_str):
                        if 'h' in update_str:
                            return float(update_str.replace('h', ''))
                        elif 'd' in update_str:
                            return float(update_str.replace('d', '')) * 24  # Convert days to hours
                        else:
                            return float('inf')  # Unknown = very old
                    
                    current_age = parse_update_time(current_updated)
                    existing_age = parse_update_time(existing_updated)
                    
                    # Keep the newer data (smaller age number)
                    if current_age < existing_age:
                        unique_results[station_key] = result
                    elif current_age == existing_age:
                        # If same age, keep the higher price
                        if result['sell_price'] > unique_results[station_key]['sell_price']:
                            unique_results[station_key] = result
            
            # Convert back to list
            results = list(unique_results.values())
            
            # Filter by distance
            results = [r for r in results if r['system_distance'] <= max_dist]
            
            # Limit results
            results = results[:max_results]
            
            if not results:
                self.after(0, lambda: self.marketplace_total_label.config(
                    text="❌ No results found within specified criteria"
                ))
                return
            
            # Update UI on main thread
            self.after(0, lambda: self._populate_marketplace_results(results, commodity))
            
        except Exception as e:
            error_msg = f"❌ Search failed: {str(e)}"
            self.after(0, lambda: self.marketplace_total_label.config(text=error_msg))
            print(f"Marketplace search error: {e}")
    
    def _quick_marketplace_search(self, commodity, reference_system, max_results, max_dist, price_age):
        """Fast search using nearby systems from user database with price age filtering"""
        from datetime import datetime, timedelta
        
        # Convert price age to hours for filtering
        age_hours = self._convert_price_age_to_hours(price_age)
        print(f"DEBUG: Price age filter: {price_age} = {age_hours} hours")
        
        # Get reference system coordinates from database (marketplace_finder removed)
        ref_coords = self._get_system_coords_from_db(reference_system)
        if not ref_coords:
            raise Exception(f"Could not find coordinates for {reference_system} (use external sites instead)")
        
        # Get nearby systems from the user database (much faster than API calls)
        nearby_systems = self._get_nearby_systems_from_db(reference_system, max_dist)
        
        # Debug: Check what the database search returned
        print(f"DEBUG: Database returned {len(nearby_systems)} nearby systems")
        if len(nearby_systems) > 0:
            print(f"DEBUG: First 5 systems from DB: {nearby_systems[:5]}")
        else:
            print("DEBUG: Database search returned empty - will use fallback list")
        
        # If no nearby systems from DB, fall back to a comprehensive list of known trading systems
        if not nearby_systems:
            nearby_systems = [
                reference_system, "Sol", "Shinrarta Dezhra", "Diaguandri", "LHS 3447",
                # Major trading hubs
                "Jameson Memorial", "Ray Gateway", "Ohm City", "Abraham Lincoln", 
                "Daedalus", "Columbus", "Li Qing Jao", "M.Gorbachev",
                # Common mining/trading systems  
                "NADUR", "HR 5900", "COL 285 SECTOR UE-G C11-5", "KHAN GUBII",
                "COL 285 SECTOR YK-E C12-33", "COL 285 SECTOR AL-O D6-68",
                "COL 285 SECTOR NF-W A45-1", "COL 285 SECTOR KD-O B21-1", 
                "COL 285 SECTOR XK-E C12-33", "COL 285 SECTOR SA-W A45-1",
                "ASSIONES", "PAESIA", "DELKAR", "BORANN", "HYADES SECTOR DB-X D1-112",
                "HIP 69643", "BIBRIGES", "SAN YAMURT",
                # Additional trading systems
                "WITCH HEAD SECTOR DL-Y D17", "WITCH HEAD SECTOR GW-W C1-4",
                "LP 40-239", "GCRV 1568", "LTT 1345", "WOLF 562", "DECIAT",
                "MAIA", "MEROPE", "ELECTRA", "TAYGETA", "ASTEROPE", "CELAENO",
                # Industrial systems
                "CEOS", "SOTHIS", "ROBIGO", "QUINCE", "RHEA", "DRACONIS",
                # More bubble systems
                "ACHENAR", "ALIOTH", "BETA HYDRI", "ETA CASSIOPEIAE", "PROCYON",
                "SIRIUS", "VEGA", "ALTAIR", "FOMALHAUT", "ARCTURUS"
            ]
        
        print(f"DEBUG: Searching {len(nearby_systems)} systems for {commodity}...")
        
        # Limit systems to check - only closest 30 systems
        systems_to_check = nearby_systems[:30]
        print(f"DEBUG: Will check {len(systems_to_check)} systems (limited from {len(nearby_systems)} total)")
        
        results = []
        systems_checked = 0
        total_systems = len(systems_to_check)
        last_ui_update = 0
        
        for system_name in systems_to_check:
            systems_checked += 1
            
            # Update progress only every 5 systems to avoid UI spam
            if systems_checked - last_ui_update >= 5 or systems_checked == total_systems:
                last_ui_update = systems_checked
                self.after(0, lambda s=systems_checked, t=total_systems: 
                          self.marketplace_total_label.config(
                              text=f"🔍 Searching systems... ({s}/{t})"
                          ))
            
            # Stop early if we have enough results
            if len(results) >= max_results * 3:
                print(f"DEBUG: Found enough results ({len(results)}), stopping search early")
                break
            
            try:
                # Get system coordinates from database (marketplace_finder removed)
                system_coords = self._get_system_coords_from_db(system_name)
                if not system_coords:
                    continue
                
                # Calculate distance manually
                distance = ((ref_coords['x'] - system_coords['x'])**2 + 
                           (ref_coords['y'] - system_coords['y'])**2 + 
                           (ref_coords['z'] - system_coords['z'])**2)**0.5
                
                if max_dist != float('inf') and distance > max_dist:
                    continue
                
                # Debug first 10 systems
                if systems_checked <= 10:
                    print(f"DEBUG: Checking system {systems_checked}: {system_name} at {distance:.2f} LY")
                
                # marketplace_finder removed - this search function is obsolete (use external sites)
                continue
                
                # Filter stations by market data age first
                valid_stations = []
                for station in stations:
                    if not station.get('haveMarket') or not station.get('marketId'):
                        continue
                    
                    # Check market update time if age filtering is enabled
                    if age_hours is not None:
                        update_time = station.get('updateTime', {}).get('market')
                        if update_time:
                            try:
                                # Parse EDSM timestamp format: '2025-11-01 07:42:55'
                                market_time = datetime.strptime(update_time, '%Y-%m-%d %H:%M:%S')
                                age = (datetime.now() - market_time).total_seconds() / 3600
                                
                                if age > age_hours:
                                    if systems_checked <= 5:
                                        print(f"DEBUG:   Station {station.get('name')} excluded: {age:.1f}h > {age_hours}h")
                                    continue  # Skip stations with old market data
                                    
                            except:
                                # If we can't parse the time, include the station
                                pass
                    
                    valid_stations.append(station)
                
                if not valid_stations:
                    continue
                
                # Check ALL valid stations in the system
                for station in valid_stations:
                    try:
                        market_data = self.marketplace_finder.get_station_market_data(station['marketId'])
                        if not market_data or 'commodities' not in market_data:
                            continue
                    except:
                        continue  # Skip this station if API call fails
                    
                    # Look for the commodity
                    for commodity_data in market_data['commodities']:
                        comm_name = commodity_data.get('name', '')
                        if commodity.lower() in comm_name.lower():
                            sell_price = commodity_data.get('sellPrice', 0)
                            
                            # Clean debug output for HR 5900 specifically (remove after testing)
                            if "HR 5900" in system_name or "5900" in system_name:
                                print(f"DEBUG: HR 5900 - Found {comm_name} at {station.get('name')} - Price: {sell_price}")
                                update_time = station.get('updateTime', {}).get('market', '')
                                if update_time:
                                    print(f"DEBUG: HR 5900 - Raw timestamp: {update_time}")
                                    try:
                                        from datetime import datetime
                                        market_time = datetime.strptime(update_time, '%Y-%m-%d %H:%M:%S')
                                        age = (datetime.now() - market_time).total_seconds() / 3600
                                        days = age / 24
                                        print(f"DEBUG: HR 5900 - Age: {age:.1f}h ({days:.1f}d) -> Display: {int(days)}d")
                                    except Exception as e:
                                        print(f"DEBUG: HR 5900 - Timestamp parse error: {e}")
                            
                            if sell_price > 0:
                                # Get demand and skip stations with zero demand
                                demand = commodity_data.get('demand', 0)
                                if demand <= 0:
                                    continue  # Skip stations with no demand
                                
                                # Get market update time for the UPDATED column
                                update_time = station.get('updateTime', {}).get('market', '')
                                if update_time:
                                    try:
                                        from datetime import datetime
                                        market_time = datetime.strptime(update_time, '%Y-%m-%d %H:%M:%S')
                                        age = (datetime.now() - market_time).total_seconds() / 3600
                                        if age < 24:
                                            updated_str = f"{age:.0f}h"
                                        else:
                                            days = age / 24
                                            # Use floor division to match how most sites show age
                                            # 1.7 days shows as "1d", not "2d"
                                            updated_str = f"{int(days)}d"
                                    except:
                                        updated_str = "Unknown"
                                else:
                                    updated_str = "Unknown"
                                
                                result = {
                                    'system_name': system_name.title(),  # Ensure proper capitalization
                                    'system_distance': distance,
                                    'station_name': station.get('name'),
                                    'station_type': station.get('type'),
                                    'arrival_distance': station.get('distanceToArrival', 0),
                                    'commodity_name': comm_name,
                                    'sell_price': sell_price,
                                    'demand': demand,  # Use the demand variable we already have
                                    'updated': updated_str,
                                }
                                results.append(result)
                                
                                # Stop early if we have enough results
                                if len(results) >= max_results:
                                    break
                    
                    if len(results) >= max_results:
                        break
                        
            except Exception as e:
                print(f"Search error for {system_name}: {e}")
                continue
            
            # Early exit if we have enough results
            if len(results) >= max_results:
                break
        
        # Sort by distance
        results.sort(key=lambda x: x['system_distance'])
        return results
    
    def _get_nearby_systems_from_db(self, reference_system, max_dist):
        """Get nearby systems from database or EDSM API"""
        try:
            # Use galaxy_systems.db which has all known systems
            from path_utils import get_app_data_dir
            import os
            galaxy_db_path = os.path.join(os.path.dirname(__file__), 'data', 'galaxy_systems.db')
            
            import sqlite3
            with sqlite3.connect(galaxy_db_path) as conn:
                cursor = conn.cursor()
                
                # Get reference system coordinates from galaxy database (table is named 'systems')
                cursor.execute('''
                    SELECT x, y, z FROM systems 
                    WHERE name = ? COLLATE NOCASE
                ''', (reference_system,))
                
                ref_row = cursor.fetchone()
                if not ref_row:
                    # Database empty - use EDSM API
                    return self._get_nearby_systems_from_edsm(reference_system, max_dist)
                
                ref_x, ref_y, ref_z = ref_row
                
                # Get nearby systems from galaxy database
                if max_dist == float('inf'):
                    max_dist_sql = 1000  # Large but finite number for SQL
                else:
                    max_dist_sql = max_dist
                
                # Get nearby systems sorted by distance
                cursor.execute('''
                    SELECT name, x, y, z,
                           SQRT(POWER(x - ?, 2) + POWER(y - ?, 2) + POWER(z - ?, 2)) as distance
                    FROM systems 
                    WHERE distance <= ?
                    ORDER BY distance
                    LIMIT 100
                ''', (ref_x, ref_y, ref_z, max_dist_sql))
                
                nearby = cursor.fetchall()
                if nearby:
                    return [row[0] for row in nearby]
                else:
                    # Database has no nearby systems - use EDSM API
                    return self._get_nearby_systems_from_edsm(reference_system, max_dist)
                    
        except Exception as e:
            pass
        
        # Final fallback to EDSM API
        return self._get_nearby_systems_from_edsm(reference_system, max_dist)
    
    def _get_nearby_systems_from_edsm(self, reference_system, max_dist):
        """Get nearby systems from EDSM sphere-systems API (marketplace_finder removed)"""
        print(f"DEBUG: marketplace_finder removed - use external sites (Inara/edtools.cc) instead")
        return []
    
    def _get_system_coords_from_db(self, system_name):
        """Get system coordinates from galaxy database"""
        try:
            if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, 'user_db'):
                db_path = self.cargo_monitor.user_db.db_path
                
                import sqlite3
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    
                    # Check if galaxy_systems table exists first
                    cursor.execute("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='galaxy_systems'
                    """)
                    
                    if not cursor.fetchone():
                        # Table doesn't exist, return None to use EDSM fallback
                        return None
                    
                    cursor.execute('''
                        SELECT x, y, z FROM galaxy_systems 
                        WHERE name = ? COLLATE NOCASE
                    ''', (system_name,))
                    
                    row = cursor.fetchone()
                    if row:
                        return {'x': row[0], 'y': row[1], 'z': row[2]}
        except Exception as e:
            # Silently fall back to EDSM - don't print error messages
            pass
        
        return None
    
    def _get_station_priority(self, station_type):
        """Get priority order for station types (lower number = higher priority)"""
        priority_order = {
            'Coriolis Starport': 1,
            'Orbis Starport': 2, 
            'Ocellus Starport': 3,
            'Asteroid Base': 4,
            'Planetary Port': 5,
            'Planetary Outpost': 6,
            'Outpost': 7,
            'Fleet Carrier': 8,
            'Odyssey Settlement': 9
        }
        
        for station_name, priority in priority_order.items():
            if station_name in station_type:
                return priority
        
        return 10  # Unknown types last
    
    def _convert_price_age_to_hours(self, price_age):
        """Convert price age string to hours, return None for 'Any'"""
        age_map = {
            "Any": None,
            "1 hour": 1,
            "8 hours": 8,
            "16 hours": 16,
            "1 day": 24,
            "2 days": 48,
            "3 days": 72,
            "7 days": 168,
            "14 days": 336,
            "30 days": 720,
            "180 days": 4320
        }
        return age_map.get(price_age, None)
    
    def _check_landing_pad(self, station_type: str, required_pad: str) -> bool:
        """Check if station has required landing pad size"""
        large_stations = ["Coriolis", "Orbis", "Ocellus", "Asteroid Base", "Planetary Port"]
        medium_stations = ["Outpost", "Planetary Outpost"]
        
        if required_pad == "Large":
            return any(s in station_type for s in large_stations)
        elif required_pad == "Medium":
            return any(s in station_type for s in medium_stations) or any(s in station_type for s in large_stations)
        else:  # Small
            return True  # All stations have small pads
    
    def _clear_marketplace_results(self):
        """Clear marketplace results tree"""
        for item in self.marketplace_tree.get_children():
            self.marketplace_tree.delete(item)
    
    def _display_marketplace_results(self, results):
        """Display marketplace results (already sorted by user's selected criteria)"""
        self._clear_marketplace_results()
        
        # Results are already sorted by the search function based on user's "Sort by" selection
        # DO NOT re-sort here - just display them as provided
        
        commodity = self.marketplace_commodity.get()
        self._populate_marketplace_results(results, commodity)
    
    def _populate_marketplace_results(self, results, commodity):
        """Populate marketplace results in UI"""
        try:
            # Determine mode for correct field handling
            is_buy_mode = self.marketplace_buy_mode.get()
            
            # Populate results (sorted by distance - closest first)
            for result in results:
                # LOCATION (System + Station) - API uses camelCase
                location = f"{result['systemName']} / {result['stationName'][:25]}"
                
                # TYPE (Station type) - Show category/specific type
                # Handle null/None values from API (some stations lack metadata)
                api_type = result.get('stationType')
                if api_type is None or api_type == '':
                    api_type = 'Unknown'
                
                # Orbital starports - show as "Orbital/Type"
                if api_type == 'AsteroidBase':
                    station_type = 'Orbital/Asteroid Base'
                elif api_type in ['Coriolis', 'Orbis', 'Ocellus', 'Outpost', 'Dodec']:
                    station_type = f'Orbital/{api_type}'
                elif api_type == 'CraterOutpost':
                    station_type = 'Surface/Crater Outpost'
                elif api_type == 'CraterPort':
                    station_type = 'Surface/Crater Port'
                elif api_type == 'SurfaceStation':
                    station_type = 'Surface Station'
                elif api_type == 'OnFootSettlement':
                    station_type = 'Surface/OnFoot Settlement'
                elif api_type == 'FleetCarrier':
                    station_type = 'Carrier'
                elif api_type == 'StrongholdCarrier':
                    station_type = 'Stronghold'
                elif api_type == 'MegaShip':
                    station_type = 'MegaShip'
                elif api_type == 'Unknown':
                    # Station lacks metadata in EDData API - show as Unknown
                    station_type = 'Unknown'
                else:
                    station_type = api_type  # Fallback to original name
                
                # PAD (Landing pad size) - Ardent API returns integer: 0=?, 1=S, 2=M, 3=L
                pad_size = result.get('maxLandingPadSize')
                
                # Map integer to letter (based on actual Elite Dangerous pad sizes)
                if isinstance(pad_size, int):
                    pad_map = {0: '?', 1: 'S', 2: 'M', 3: 'L'}
                    pad = pad_map.get(pad_size, '?')
                elif isinstance(pad_size, str):
                    # Fallback if API ever sends strings
                    pad = pad_size.upper()
                else:
                    pad = '?'
                
                # DISTANCE (System distance) - calculate for both modes
                if 'distance' in result:
                    distance = f"{result['distance']:.1f}"
                else:
                    distance = "Unknown"  # No distance available
                
                # LS (Station distance from star) - from distanceToArrival field
                station_ls = result.get('distanceToArrival')
                if station_ls is not None:
                    # 0 is valid for fleet carriers at arrival point
                    ls = f"{int(station_ls):,}"
                else:
                    ls = "?"
                
                # DEMAND/STOCK - depends on mode
                if is_buy_mode:
                    # Buy mode (exports endpoint): use 'stock' field
                    volume = f"{result.get('stock', 0):,}" if result.get('stock', 0) > 0 else "0"
                else:
                    # Sell mode (imports endpoint): use 'demand' field
                    volume = f"{result.get('demand', 0):,}" if result.get('demand', 0) > 0 else "0"
                
                # PRICE - depends on mode
                # NOTE: Ardent API exports endpoint has price in 'buyPrice' field (backwards naming!)
                if is_buy_mode:
                    # Buy mode (exports endpoint): Use 'buyPrice' (what YOU pay to buy FROM them)
                    # API has backwards field naming - sellPrice is 0, actual price is in buyPrice
                    price = f"{result.get('buyPrice', 0):,}"
                else:
                    # Sell mode (imports endpoint): Use 'sellPrice' (what YOU get when selling TO them)
                    price = f"{result.get('sellPrice', 0):,} CR"
                
                # UPDATED (Data age) - show hours/days ago
                updated_at = result.get('updatedAt', 'Unknown')
                if updated_at and updated_at != 'Unknown':
                    try:
                        # Parse ISO timestamp (e.g., "2024-11-03T12:30:00Z")
                        from datetime import datetime, timezone
                        updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        diff = now - updated_time
                        
                        # Convert to minutes, hours, or days
                        total_minutes = diff.total_seconds() / 60
                        if total_minutes < 60:
                            updated = f"{int(total_minutes)}m"
                        elif total_minutes < 1440:  # Less than 24 hours
                            hours = int(total_minutes / 60)
                            updated = f"{hours}h"
                        else:
                            days = int(total_minutes / 1440)
                            updated = f"{days}d"
                    except Exception as e:
                        updated = 'Unknown'
                else:
                    updated = 'Unknown'
                
                # Insert with alternating row tags for visual separation
                row_index = len(self.marketplace_tree.get_children())
                tag = 'evenrow' if row_index % 2 == 0 else 'oddrow'
                
                # Add subtle visual separator using spacing
                self.marketplace_tree.insert("", "end", values=(
                    f" {location} ",
                    f" {station_type} ",
                    f" {pad} ",
                    f" {distance} ",
                    f" {ls} ",
                    f" {volume} ",
                    f" {price} ",
                    f" {updated} "
                ), tags=(tag,))
            
            # Update status (like hotspots finder format)
            if results:
                if is_buy_mode:
                    # Buy mode: find lowest sellPrice (cheapest to buy from)
                    best_price = min(results, key=lambda x: x.get('sellPrice', 999999))
                    price_value = best_price.get('sellPrice', 0)
                    mode_text = "to buy from"
                else:
                    # Sell mode: find highest sellPrice (best to sell to)
                    best_price = max(results, key=lambda x: x.get('sellPrice', 0))
                    price_value = best_price.get('sellPrice', 0)
                    mode_text = "to sell to"
                
                # Different message for galaxy-wide vs near system
                if 'distance' in best_price:
                    self.marketplace_total_label.config(
                        text=f"Found {len(results)} stations {mode_text}. "
                             f"Best price: {price_value:,} CR/t at {best_price['stationName']} "
                             f"({best_price['distance']:.1f} LY)"
                    )
                else:
                    self.marketplace_total_label.config(
                        text=f"Found {len(results)} stations {mode_text}. "
                             f"Best price: {price_value:,} CR/t at {best_price['stationName']} "
                             f"in {best_price.get('systemName', 'Unknown')}"
                    )
            
        except Exception as e:
            self.marketplace_total_label.config(text=f"❌ Error displaying results: {str(e)}")
            print(f"Error populating results: {e}")
    
    def _get_landing_pad_size(self, station_type):
        """Get landing pad size abbreviation from station type"""
        if not station_type:
            return "?"
        
        # Large pad stations
        large_pad_types = [
            "Coriolis Starport", "Orbis Starport", "Ocellus Starport",
            "Asteroid Base", "Planetary Port", "Planetary Outpost"
        ]
        
        # Small pad stations (outposts)
        small_pad_types = ["Outpost"]
        
        # Fleet carriers (large pads)
        if "Fleet Carrier" in station_type:
            return "L"
        
        # Check for large pad stations
        for large_type in large_pad_types:
            if large_type in station_type:
                return "L"
        
        # Check for small pad stations
        for small_type in small_pad_types:
            if small_type in station_type:
                return "S"
        
        # Default to medium for most other stations
        return "M"
    

    
    def _show_marketplace_context_menu(self, event):
        """Show the context menu when right-clicking on marketplace results"""
        try:
            # Select the item under cursor
            item = self.marketplace_tree.identify_row(event.y)
            if item:
                self.marketplace_tree.selection_set(item)
                self.marketplace_tree.focus(item)
                self.marketplace_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.marketplace_context_menu.grab_release()
    
    def _copy_marketplace_system_name(self):
        """Copy the selected system name to clipboard"""
        selection = self.marketplace_tree.selection()
        if selection:
            item = selection[0]
            values = self.marketplace_tree.item(item, 'values')
            if values and len(values) > 0:
                # Location format is "System / Station", extract system name
                location = values[0]  # Location is column index 0
                system_name = location.split(' / ')[0] if ' / ' in location else location
                self.clipboard_clear()
                self.clipboard_append(system_name)
                self.marketplace_total_label.config(text=f"✅ Copied '{system_name}' to clipboard")
    
    def _sort_marketplace_column(self, column, numeric):
        """Sort marketplace results by column"""
        try:
            # Get all items from the tree
            items = [(self.marketplace_tree.item(item, 'values'), item) for item in self.marketplace_tree.get_children()]
            
            if not items:
                return
            
            # Check if we're clicking the same column
            if self.marketplace_sort_column == column:
                # Reverse the sort direction
                self.marketplace_sort_reverse = not self.marketplace_sort_reverse
            else:
                # New column, start with ascending
                self.marketplace_sort_column = column
                self.marketplace_sort_reverse = False
            
            # Get column index - column IDs, not display names
            column_ids = ("location", "type", "pad", "distance", "ls", "demand", "price", "updated")
            
            # Map display names to column IDs
            display_to_id = {
                "Location": "location",
                "Station Type": "type", 
                "Pad": "pad",
                "Distance": "distance",
                "LS": "ls",
                "Demand": "demand",
                "Price": "price",
                "Updated": "updated"
            }
            
            # Get the column ID from display name
            col_id = display_to_id.get(column, column)
            col_index = column_ids.index(col_id)
            
            # Define sort function based on column type
            if numeric:
                def sort_key(item):
                    value = item[0][col_index]
                    try:
                        if col_id == "ls":
                            # Handle LS column with commas: "88,009" or "?"
                            if value.strip() == '?':
                                return 999999
                            # Remove commas and convert to number
                            return float(value.replace(',', '').strip())
                        elif col_id == "distance":
                            # Remove " LY" suffix and convert to float
                            return float(value.replace(" LY", ""))
                        elif col_id == "price":
                            # Remove " CR" suffix and commas
                            return float(value.replace(" CR", "").replace(",", ""))
                        elif col_id == "demand":
                            # Remove commas
                            return float(value.replace(",", "")) if value != "0" else 0
                        elif col_id == "updated":
                            # Convert time format to comparable number (minutes)
                            if "m" in value:
                                return float(value.replace("m", ""))
                            elif "h" in value:
                                return float(value.replace("h", "")) * 60  # Convert hours to minutes
                            elif "d" in value:
                                return float(value.replace("d", "")) * 1440  # Convert days to minutes
                            else:
                                return float('inf')  # Unknown times go to end
                        else:
                            return float(value.replace(",", "")) if value.replace(",", "").replace(".", "").isdigit() else 0
                    except:
                        return 0 if not self.marketplace_sort_reverse else float('inf')
            else:
                def sort_key(item):
                    # String sorting
                    return item[0][col_index].lower()
            
            # Sort items
            items.sort(key=sort_key, reverse=self.marketplace_sort_reverse)
            
            # Clear tree and re-insert sorted items
            for values, item in items:
                self.marketplace_tree.move(item, '', 'end')
            
            # Update column headers to show sort direction
            display_names = ["Location", "Station Type", "Pad", "Distance", "Demand", "Price", "Updated"]
            for col_name in display_names:
                if col_name == column:
                    arrow = " ↓" if self.marketplace_sort_reverse else " ↑"
                    self.marketplace_tree.heading(display_to_id[col_name], text=col_name + arrow)
                else:
                    self.marketplace_tree.heading(display_to_id[col_name], text=col_name)
                    
        except Exception as e:
            print(f"Error sorting marketplace column: {e}")
            self.marketplace_total_label.config(text=f"❌ Sort error: {str(e)}")
    
    def _update_marketplace_with_distances(self, results_with_distances, total_results):
        """Update marketplace display after distance calculation completes (called from thread)"""
        try:
            # Re-sort results based on current sort order after distances are added
            order_by = self.marketplace_order_by.get()
            
            if "Distance" in order_by:
                # Sort by distance (nearest first)
                results_sorted = sorted(results_with_distances, key=lambda x: x.get('distance', 999999), reverse=False)
            elif "Best price" in order_by:
                # Keep original price sorting
                results_sorted = results_with_distances
            else:
                # For other sort orders, keep original
                results_sorted = results_with_distances
            
            # Re-display results with distances
            self._display_marketplace_results(results_sorted)
            self.marketplace_total_label.config(text=t('marketplace.found_stations_top30_distance').format(count=total_results))
            self.config(cursor="")
        except Exception as e:
            print(f"[MARKETPLACE] Error updating with distances: {e}")
            self.config(cursor="")
    
    def _restore_marketplace_cursor(self, total_results):
        """Restore cursor if distance calculation fails"""
        self.marketplace_total_label.config(text=t('marketplace.found_stations_top30').format(count=total_results))
        self.config(cursor="")
    
    def _has_large_pads(self, station_type):
        """Check if station has large landing pads"""
        large_pad_stations = [
            "Coriolis Starport", "Orbis Starport", "Ocellus Starport",
            "Asteroid Base", "Planetary Outpost", "Planetary Port"
        ]
        return any(pad_type in station_type for pad_type in large_pad_stations)
    
    def _has_medium_pads(self, station_type):
        """Check if station has medium landing pads (most stations)"""
        return not self._has_large_pads(station_type) and "Fleet Carrier" not in station_type
    
    def _has_small_pads(self, station_type):
        """Check if station has small landing pads (outposts)"""
        small_pad_stations = ["Outpost", "Planetary Outpost"]
        return any(pad_type in station_type for pad_type in small_pad_stations)
    
    def _is_surface_station(self, station_type):
        """Check if station is on planetary surface"""
        surface_stations = ["Planetary Outpost", "Planetary Port", "Odyssey Settlement"]
        return any(surface_type in station_type for surface_type in surface_stations)
    
    def _is_space_station(self, station_type):
        """Check if station is in space"""
        space_stations = [
            "Coriolis Starport", "Orbis Starport", "Ocellus Starport",
            "Asteroid Base", "Outpost"
        ]
        return any(space_type in station_type for space_type in space_stations)

    def _check_for_updates_startup(self):
        """Check for updates on startup (automatic check) - checks every time app starts"""
        current_version = get_version()
        logging.info(f"[UPDATE_CHECK] Starting update check... Current version: {current_version}")
        print(f"Checking for updates... Current version: {current_version}")
        
        # Show update check in main window status bar (bottom left)
        try:
            if hasattr(self, 'status'):
                # Save current status
                current_status = self.status.get()
                
                # Show checking message
                self.status.set("🔍 Checking for updates...")
                logging.info("[UPDATE_CHECK] Status bar updated: Checking for updates...")
                
                # Restore original status after 3 seconds
                def restore_status():
                    try:
                        if hasattr(self, 'status'):
                            self.status.set(current_status)
                            logging.info("[UPDATE_CHECK] Status bar restored")
                    except:
                        pass
                
                self.after(3000, restore_status)
        except Exception as e:
            logging.error(f"[UPDATE_CHECK] Could not update status bar: {e}")
            print(f"Could not update status bar for update check: {e}")
        
        self.update_checker.check_for_updates_async(self)

    def _manual_update_check(self):
        """Manually check for updates (from menu)"""
        self.update_checker.manual_check(self)
    
    def _check_va_profile_update(self):
        """Check for VoiceAttack profile updates on startup"""
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
                                # Show update dialog with old version
                                debug_log(f"Upgrade from old profile: {old_version} -> {new_version}")
                                self._show_va_profile_update_dialog(old_version, new_version, new_profile_path)
                            else:
                                # Couldn't parse old version - show dialog anyway for existing users
                                debug_log("Existing user (old profile, version unknown) - showing dialog")
                                self._show_va_profile_update_dialog(None, new_version, new_profile_path)
                        except Exception as e:
                            debug_log(f"Error parsing old profile: {e} - showing dialog anyway")
                            self._show_va_profile_update_dialog(None, new_version, new_profile_path)
                    else:
                        # No old profile - true first install (only new versioned profile exists)
                        debug_log("True first install - creating state file silently")
                        self._save_va_profile_state(state_file, new_version)
                elif installed_version != new_version:
                    # Version changed - show update dialog with keybind preservation
                    debug_log(f"Update available: {installed_version} -> {new_version}")
                    self._show_va_profile_update_dialog(installed_version, new_version, new_profile_path)
                else:
                    debug_log(f"Profile up to date: {new_version}")
                    
            except Exception as e:
                logging.error(f"[VA_PROFILE] Error checking new profile version: {e}")
                
        except Exception as e:
            logging.error(f"[VA_PROFILE] Error checking for profile update: {e}")
    
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
        try:
            from app_utils import centered_askyesno, centered_message
            from path_utils import get_app_data_dir
            from tkinter import filedialog
            import json
            
            # Show update message with keybind preservation info
            message = t("voiceattack.profile_update_message").format(
                current=current_version,
                new=new_version
            )
            
            result = centered_askyesno(
                self,
                t("voiceattack.profile_update_title"),
                message
            )
            
            if result:
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
            
            # Save the new version to state file (user has been notified)
            state_file = os.path.join(get_app_data_dir(), "va_profile_state.json")
            self._save_va_profile_state(state_file, new_version)
            logging.info(f"[VA_PROFILE] Saved new version to state: {new_version}")
                
        except Exception as e:
            logging.error(f"[VA_PROFILE] Error showing update dialog: {e}")
    
    def _merge_profiles_with_keybinds(self, old_profile_path, new_profile_path, new_version):
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
        
        if keybind_count == 0:
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
        
        # Step 6: Show success message
        centered_message(
            self,
            t("voiceattack.merge_success_title"),
            t("voiceattack.merge_success_message").format(
                count=keybind_count,
                path=new_profile_path
            )
        )
    
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
            try:
                # Check again in case update started while we were waiting
                if getattr(self, '_update_in_progress', False):
                    print("[JOURNAL] Scan cancelled - update in progress")
                    return
                
                # If migration already ran, skip the visit counting parts
                # Migration already fixed visit counts from ALL journals
                if migration_ran:
                    print("[JOURNAL] Migration already ran - skipping redundant visit scan")
                    self.after(0, lambda: self._set_status("Ready", 3000))
                    return
                    
                self.after(0, lambda: self._set_status("Scanning journal history...", 0))
                
                # Get journal directory
                journal_dir = self.cargo_monitor.journal_dir
                if not journal_dir or not os.path.isdir(journal_dir):
                    print("[JOURNAL] No journal directory found")
                    self.after(0, lambda: self._set_status("No journal folder found", 5000))
                    return
                
                # Get ALL journals
                pattern = os.path.join(journal_dir, "Journal.*.log")
                all_journals = sorted(glob.glob(pattern))
                
                if not all_journals:
                    print("[JOURNAL] No journal files found")
                    log.info("No journal files found")
                    self.after(0, lambda: self._set_status("No journal files found", 5000))
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
                    return  # Don't continue - dialog handles the scan
                else:
                    # Subsequent runs: scan last 6 months silently
                    cutoff_date = datetime.now() - timedelta(days=180)
                    journals_to_scan = self._filter_journals_by_date(all_journals, cutoff_date)
                    print(f"[STARTUP] Regular scan: {len(journals_to_scan)} of {len(all_journals)} journals (last 6 months)")
                    log.info(f"Startup: Regular scan - {len(journals_to_scan)} of {len(all_journals)} journals (last 6 months)")
                    self.after(0, lambda n=len(journals_to_scan): self._set_status(f"Scanning {n} journals...", 0))
                
                self._process_journals_for_catchup(journals_to_scan, is_full_sync=False)
                
            except Exception as e:
                print(f"[JOURNAL] ERROR: {e}")
                self.after(0, lambda: self._set_status("Journal scan failed", 5000))
                import traceback
                traceback.print_exc()
        
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
                        print(f"[STARTUP] Scan status check error: {e}")
                        # If we can't check, assume needs migration
                        return 'migration'
                    
                    return 'none'  # Has visits and scan already done
        except Exception as e:
            print(f"[STARTUP] _is_first_install exception: {e}")
        return 'first_install'  # Assume first install if we can't determine
    
    def _run_full_scan_with_dialog(self, journals, scan_type='first_install'):
        """Run full journal scan with a progress dialog
        
        Args:
            journals: List of journal files to scan
            scan_type: 'first_install' or 'migration'
        """
        import threading
        from localization import t
        from app_utils import get_app_icon_path
        
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
            font=("Segoe UI", 11, "bold"),
            bg=bg_color,
            fg=fg_color
        )
        title_label.pack(pady=(20, 5))
        
        # Subtitle / patience message
        subtitle_label = tk.Label(
            progress_dialog,
            text=t(patience_key),
            font=("Segoe UI", 9, "italic"),
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
            font=("Segoe UI", 9),
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
                print(f"[FULL SCAN] Error: {e}")
            finally:
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
        self._set_status("Journal scan complete", 5000)
    
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
                print(f"[MIGRATION] Failed to reset visit data: {e}")
        
        # Start batch mode for mission tracker
        mission_tracker = None
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
                            
                            # Process visits - ONLY FSDJump counts as a player visit
                            # CarrierJump is for FC location tracking, not visit counting
                            if event_type == 'FSDJump':
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
                            
                            elif event_type == 'CarrierJump':
                                # CarrierJump just tracks current system context, not visits
                                system_name = event.get('StarSystem', '')
                                if system_name:
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
                                    pass
                            
                            elif event_type == 'SAASignalsFound':
                                try:
                                    self.cargo_monitor.journal_parser.process_saa_signals_found(event, current_system)
                                    hotspots_added += 1
                                except:
                                    pass
                            
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
        
        print(f"[FIRST INSTALL] ✓ Scan complete: {total} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} missions")
        log.info(f"First install scan complete: {total} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} missions")
        
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
            print(f"[FIRST INSTALL] Failed to save scan status: {e}")
        
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
    
    def _process_journals_for_catchup(self, journals, is_full_sync=False):
        """Process journal files for catchup scan
        
        Processes hotspots/ring data, visits, and missions from journal files.
        
        Args:
            journals: List of journal file paths to process
            is_full_sync: If True, this is a full sync (all journals)
        """
        import json
        
        visits_added = 0
        hotspots_added = 0
        missions_found = 0
        
        # Set flag to prevent auto-refresh triggers during catchup scan
        self.cargo_monitor._catchup_scan_in_progress = True
        
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
                progress = f"Scanning journals... {idx}/{len(journals)}"
                self.after(0, lambda p=progress: self._set_status(p, 0))
            
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
                            
                            # Process visits - ONLY FSDJump counts as a player visit
                            # CarrierJump is for FC location tracking, not visit counting
                            # Visit counting uses current system as reference (safety net)
                            if event_type == 'FSDJump':
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
                            
                            elif event_type == 'CarrierJump':
                                # CarrierJump just tracks current system context, not visits
                                system_name = event.get('StarSystem', '')
                                if system_name:
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
                                except:
                                    pass
                            
                            # Process SAASignalsFound for hotspots
                            elif event_type == 'SAASignalsFound':
                                try:
                                    self.cargo_monitor.journal_parser.process_saa_signals_found(event, current_system)
                                    hotspots_added += 1
                                except:
                                    pass
                            
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
            except Exception as e:
                print(f"[JOURNAL] Error reading {os.path.basename(journal_path)}: {e}")
                continue
        
        # End batch mode for mission tracker
        if mission_tracker:
            try:
                mission_tracker.end_batch()
            except:
                pass
        
        # Clear catchup scan flag
        self.cargo_monitor._catchup_scan_in_progress = False
        
        print(f"[JOURNAL] ✓ Scan complete: {len(journals)} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} mining missions")
        log.info(f"Journal scan complete: {len(journals)} files, {visits_added} visits, {hotspots_added} hotspots, {missions_found} mining missions")
        
        # Show completion in status bar
        self.after(0, lambda: self._set_status(f"Journal scan complete: {len(journals)} files processed"))
        
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
        if hasattr(self, '_update_home_fc_distances'):
            print("[JOURNAL] Triggering distance calculation...")
            self.after(100, self._update_home_fc_distances)
        
        # Ring finder auto-search runs AFTER journal scan is complete
        self.after(200, self._trigger_ring_auto_search)
        
        # Also trigger System A ↔ B calculation if both fields are populated
        if hasattr(self, '_calculate_distances'):
            self.after(300, self._auto_calculate_if_populated)

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
            pass

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
            pass
    
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
        except Exception:
            pass
        return False
    
    def _fetch_reserve_levels_for_system(self, system_name: str) -> None:
        """Fetch reserve levels from Spansh API and update database for a system
        
        Called when entering a new system to ensure reserve level data is available.
        Runs in background thread to avoid blocking UI.
        """
        import threading
        
        def fetch_worker():
            try:
                if not hasattr(self, 'cargo_monitor') or not self.cargo_monitor:
                    return
                    
                jp = self.cargo_monitor.journal_parser
                if not jp:
                    return
                
                print(f"[RESERVE] Fetching reserve levels for {system_name}...")
                reserve_levels = jp._fetch_system_reserve_levels_from_spansh(system_name)
                jp.system_reserve_levels = reserve_levels
                
                if reserve_levels:
                    print(f"[RESERVE] Fetched {len(reserve_levels)} reserve levels for {system_name}")
                    
                    # Bulk update existing database entries with reserve levels
                    if hasattr(self.cargo_monitor, 'user_db') and self.cargo_monitor.user_db:
                        updated_count = self.cargo_monitor.user_db.bulk_update_reserve_levels(system_name, reserve_levels)
                        if updated_count > 0:
                            print(f"[RESERVE] Updated {updated_count} database entries with reserve levels")
                else:
                    print(f"[RESERVE] No reserve levels found for {system_name}")
                    
            except Exception as e:
                print(f"[RESERVE] Error fetching reserve levels: {e}")
        
        # Run in background thread to avoid blocking UI
        thread = threading.Thread(target=fetch_worker, daemon=True)
        thread.start()
    
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
        # 1. Update ring finder reference system
        if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_var'):
            self.ring_finder.system_var.set(system_name)
            if coords:
                self.ring_finder.current_system_coords = coords
        
        # 2. Update distance calculator display
        if hasattr(self, 'distance_current_system'):
            self.distance_current_system.set(system_name)
            # Trigger distance updates to home/FC
            self.after(0, self._update_home_fc_distances)
        
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
            self._update_sysfinder_ref_info(system_name)
        
        # Clear any selection that might have been applied and set neutral focus
        try:
            self.after(50, lambda: (self.ring_finder.system_entry.selection_clear() if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, 'system_entry') else None))
            self.after(50, lambda: (self.sysfinder_ref_entry.selection_clear() if hasattr(self, 'sysfinder_ref_entry') else None))
            self.after(50, lambda: (self.distance_current_display.selection_clear() if hasattr(self, 'distance_current_display') else None))
            self.after(50, lambda: (self.import_btn.focus_set() if hasattr(self, 'import_btn') else None))
        except Exception:
            pass
        
        print(f"[SYSTEM] Updated current system: {system_name}")


if __name__ == "__main__":
    # Single instance check - TEMPORARILY DISABLED FOR TESTING
    # import win32event
    # import win32api
    # import winerror
    
    # mutex_name = "Global\\EliteMining_SingleInstance_Mutex"
    # mutex = None
    
    # try:
    #     mutex = win32event.CreateMutex(None, False, mutex_name)
    #     last_error = win32api.GetLastError()
    #     
    #     if last_error == winerror.ERROR_ALREADY_EXISTS:
    #         # Another instance is already running
    #         import tkinter.messagebox as messagebox
    #         messagebox.showerror(
    #             "EliteMining Already Running",
    #             "EliteMining is already running.\n\n"
    #             "Only one instance can run at a time to prevent duplicate announcements and conflicts.\n\n"
    #             "Please close the other instance first."
    #         )
    #         sys.exit(0)
    # except Exception as e:
    #     print(f"Warning: Could not create mutex for single instance check: {e}")
    #     # Continue anyway - better to run than to fail completely
    
    print("[DEBUG] Single instance check DISABLED for testing - multiple instances allowed")
    
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
        # Restore geometry after all widgets are created
        app.after(100, app._restore_window_geometry)
        # Force dark title bar after window is fully created
        app.after(200, app._set_dark_title_bar)
        app.mainloop()
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
