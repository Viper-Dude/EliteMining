#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EliteMining - Elite Dangerous Mining Assistant
Copyright (C) 2024-2025 Viper-Dude

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

# Initialize logging for installer version (per-session logs with auto-cleanup)
from logging_setup import setup_logging
log_file = setup_logging()  # Only activates when running as packaged executable
if log_file:
    print(f"✓ Logging enabled: {log_file}")

# Determine app directory for both PyInstaller and script execution
if hasattr(sys, '_MEIPASS'):
    app_dir = os.path.dirname(sys.executable)
else:
    app_dir = os.path.dirname(os.path.abspath(__file__))

# Legacy debug log (kept for compatibility, but logging_setup.py is now primary)
log_path = os.path.join(app_dir, "debug_log.txt")
import json
import glob
import re
import shutil
import datetime as dt
import logging
import logging
from logging.handlers import RotatingFileHandler
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, Optional, Any, List
import sys
import threading
import time
import zipfile
import announcer
from ring_finder import RingFinder
# from marketplace_finder import MarketplaceFinder  # No longer used - using external sites
from marketplace_api import MarketplaceAPI
from config import _load_cfg, _save_cfg, load_saved_va_folder, save_va_folder, load_window_geometry, save_window_geometry, load_cargo_window_position, save_cargo_window_position
from version import get_version, UPDATE_CHECK_URL, UPDATE_CHECK_INTERVAL
from update_checker import UpdateChecker
from user_database import UserDatabase
from journal_parser import JournalParser
from app_utils import get_app_icon_path, set_window_icon, get_app_data_dir, get_variables_dir, get_ship_presets_dir
from path_utils import get_ship_presets_dir, get_reports_dir

# --- Simple Tooltip class with global enable/disable ---
class ToolTip:
    tooltips_enabled = True  # Global tooltip enable/disable flag
    _tooltip_instances = {}  # Store references to prevent garbage collection
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.tooltip_timer = None  # For delay timer
        
        # Remove any existing tooltip for this widget
        if widget in ToolTip._tooltip_instances:
            old_tooltip = ToolTip._tooltip_instances[widget]
            try:
                widget.unbind("<Enter>")
                widget.unbind("<Leave>")
                # Cancel any existing timer
                if old_tooltip.tooltip_timer:
                    widget.after_cancel(old_tooltip.tooltip_timer)
            except:
                pass
        
        # Store this instance to prevent garbage collection
        ToolTip._tooltip_instances[widget] = self
        
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)
        self.tooltip_window = None

    def on_enter(self, event=None):
        if self.tooltip_window or not self.text or not ToolTip.tooltips_enabled:
            return
        
        # Cancel any existing timer
        if self.tooltip_timer:
            self.widget.after_cancel(self.tooltip_timer)
        
        # Start a timer to show tooltip after 700ms delay (best practice)
        self.tooltip_timer = self.widget.after(700, self._show_tooltip)

    def _show_tooltip(self):
        """Actually create and show the tooltip window"""
        if self.tooltip_window or not self.text or not ToolTip.tooltips_enabled:
            return
            
        try:
            # Get widget position and size
            widget_x = self.widget.winfo_rootx()
            widget_y = self.widget.winfo_rooty()
            widget_width = self.widget.winfo_width()
            widget_height = self.widget.winfo_height()
            
            # Get the main window bounds for positioning reference
            root_window = self.widget.winfo_toplevel()
            root_x = root_window.winfo_x()
            root_y = root_window.winfo_y()
            root_width = root_window.winfo_width()
            root_height = root_window.winfo_height()
            
            # Tooltip dimensions
            tooltip_width = 250
            tooltip_height = 60
            
            # Check if widget is in the bottom area of the window (like the Import/Apply buttons)
            widget_relative_y = widget_y - root_y
            if widget_relative_y > root_height * 0.8:  # If widget is in bottom 20% of window
                # Position tooltip to the right of the widget at same level
                x = widget_x + widget_width + 15
                y = widget_y + (widget_height // 2) - (tooltip_height // 2)  # Center vertically with widget
            else:
                # Default position: below and slightly right of the widget
                x = widget_x + 10
                y = widget_y + widget_height + 8
            
            # Horizontal positioning adjustments
            if x + tooltip_width > root_x + root_width:
                x = widget_x + widget_width - tooltip_width - 10
            
            # Ensure tooltip stays within reasonable bounds of the main window
            x = max(root_x - 50, min(x, root_x + root_width + 50))
            y = max(root_y + 20, min(y, root_y + root_height - 20))

            self.tooltip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            
            # Ensure tooltip appears on top
            tw.wm_attributes("-topmost", True)
            tw.lift()
            
            label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                            font=("Segoe UI", "8"), wraplength=250,
                            padx=4, pady=2)
            label.pack()
            
            # Make sure it's visible
            tw.update()
        except Exception as e:
            self.tooltip_window = None

    def on_leave(self, event=None):
        # Cancel the timer if mouse leaves before tooltip appears
        if self.tooltip_timer:
            self.widget.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
            
        # Hide tooltip if it's currently showing
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        """Enable or disable all tooltips globally"""
        cls.tooltips_enabled = enabled

# --- Text Overlay class for TTS announcements ---
class TextOverlay:
    def __init__(self):
        self.overlay_window = None
        self.overlay_enabled = False
        self.display_duration = 7000  # 7 seconds in milliseconds
        self.fade_timer = None
        self.transparency = 0.9  # Default transparency (90%)
        self.text_color = "#FFFFFF"  # Default white color
        self.position = "upper_right"  # Default position
        self.font_size = 14  # Default font size (Normal)
        
    def create_overlay(self):
        """Create the overlay window"""
        if self.overlay_window:
            return
            
        self.overlay_window = tk.Toplevel()
        self.overlay_window.title("Mining Announcements")
        self.overlay_window.wm_overrideredirect(True)  # Remove window decorations
        self.overlay_window.wm_attributes("-topmost", True)  # Always on top
        
        # Make window background completely transparent
        self.overlay_window.wm_attributes("-transparentcolor", "#000001")  # Use almost-black as transparent
        self.overlay_window.configure(bg="#000001")  # This color becomes transparent
        
        # Position based on setting
        self._set_window_position()
        
        # Create text label with transparent background
        self.text_label = tk.Label(
            self.overlay_window,
            text="",
            bg="#000001",  # Same as transparent color - will be invisible
            fg=self.text_color,  # Use current color (will be updated with brightness)
            font=("Segoe UI", 11, "normal"),  # Fixed smaller size
            wraplength=0,  # Disable wrapping - let newlines control line breaks
            justify="left",
            relief="flat",
            bd=0,
            highlightthickness=0
        )
        self.text_label.pack(anchor="nw", padx=10, pady=5)
        
        # Hide initially
        self.overlay_window.withdraw()
        
        # Apply current color and brightness settings
        self._update_text_color()
        
    def _get_background_color(self):
        """Calculate background color based on transparency setting"""
        # At 10% transparency -> very light background
        # At 100% transparency -> dark background
        alpha_factor = self.transparency
        if alpha_factor < 0.3:  # Very transparent - use light gray
            gray_value = int(64 + (1.0 - alpha_factor) * 64)  # Light gray
        else:  # More opaque - use darker
            gray_value = int(30 + alpha_factor * 30)  # Dark gray
        return f"#{gray_value:02x}{gray_value:02x}{gray_value:02x}"
        
    def show_message(self, message: str):
        """Display a message in the overlay"""
        if not self.overlay_enabled:
            return
            
        if not self.overlay_window:
            self.create_overlay()
            
        # Update text
        self.text_label.config(text=message)
        
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
            
        # Update text and show window
        self.text_label.config(text=message)
        self.overlay_window.deiconify()
        
        # Cancel any existing timer - this message stays until manually hidden
        if self.fade_timer:
            self.overlay_window.after_cancel(self.fade_timer)
            self.fade_timer = None
    
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
        """Set text brightness (10-100%) - affects text brightness, background stays transparent"""
        self.transparency = transparency_percent / 100.0
        if self.overlay_window and hasattr(self, 'text_label'):
            try:
                # Apply brightness to the current color
                self._update_text_color()
            except Exception as e:
                print(f"Error setting text brightness: {e}")
    
    def set_color(self, color_hex: str):
        """Set the base text color"""
        self.text_color = color_hex
        if self.overlay_window and hasattr(self, 'text_label'):
            try:
                # Apply current brightness to the new color
                self._update_text_color()
            except Exception as e:
                print(f"Error setting text color: {e}")
    
    def _update_text_color(self):
        """Update text color by applying current brightness to base color"""
        # Parse the base color
        base_color = self.text_color.lstrip('#')
        r = int(base_color[0:2], 16)
        g = int(base_color[2:4], 16) 
        b = int(base_color[4:6], 16)
        
        # For crystal clear text, use full brightness instead of transparency-based dimming
        brightness_factor = 1.0  # Always use full brightness for clear text
        
        # Calculate new RGB values
        new_r = int(r * brightness_factor)
        new_g = int(g * brightness_factor)
        new_b = int(b * brightness_factor)
        
        # Ensure we get the full color values
        new_r = min(255, max(0, new_r))
        new_g = min(255, max(0, new_g))
        new_b = min(255, max(0, new_b))
        
        final_color = f"#{new_r:02x}{new_g:02x}{new_b:02x}"
        self.text_label.configure(fg=final_color)
    
    def set_position(self, position: str):
        """Set overlay position ('upper_right' or 'upper_left')"""
        self.position = position
        if self.overlay_window:
            self._set_window_position()
    
    def set_font_size(self, size: int):
        """Set text font size"""
        self.font_size = size
        if self.overlay_window and hasattr(self, 'text_label'):
            try:
                # Use Segoe UI (original font) with normal weight
                family = "Segoe UI"
                style = "normal"
                self.text_label.configure(font=(family, size, style))
            except Exception as e:
                print(f"Error setting font size: {e}")
    
    def set_display_duration(self, seconds: int):
        """Set how long text stays on screen (5-30 seconds)"""
        self.display_duration = seconds * 1000  # Convert to milliseconds
        # If a message is currently showing, don't interrupt it
        # The new duration will apply to the next message
    
    def _set_window_position(self):
        """Set window position based on current position setting"""
        if not self.overlay_window:
            return
            
        screen_width = self.overlay_window.winfo_screenwidth()
        window_width = 750  # Wider for long material names like "Low Temperature Diamonds"
        window_height = 300  # Larger for enhanced overlay with different font sizes
        
        if self.position == "upper_left":
            # Upper left: absolute position
            x_pos = 20
            y_pos = 100
        else:  # upper_right (default)
            # Upper right with margin
            x_pos = screen_width - window_width - 20
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
APP_VERSION = "v4.4.6"
PRESET_INDENT = "   "  # spaces used to indent preset names

LOG_FILE = os.path.join(os.path.expanduser("~"), "EliteMining.log")
_handler = RotatingFileHandler(LOG_FILE, maxBytes=512*1024, backupCount=3, encoding="utf-8")
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
        
        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Add Refinery Contents")
        self.dialog.geometry("600x650")
        self.dialog.configure(bg="#1e1e1e")
        self.dialog.resizable(True, True)  # Allow resizing so user can adjust if needed
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Force window to appear on top
        self.dialog.attributes('-topmost', True)
        self.dialog.lift()
        self.dialog.focus_force()
        
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
            base_height = 650
            if material_count > 2:
                # Add 60px for each row of materials (2 materials per row)
                extra_rows = (material_count - 2 + 1) // 2  # Round up
                dialog_height = min(850, base_height + (extra_rows * 60))
            else:
                dialog_height = base_height
            
            x = parent_x + (parent_width - dialog_width) // 2
            y = parent_y + (parent_height - dialog_height) // 2
        else:
            # Fallback to screen center
            base_height = 650
            if material_count > 2:
                extra_rows = (material_count - 2 + 1) // 2
                dialog_height = min(850, base_height + (extra_rows * 60))
            else:
                dialog_height = base_height
            x = (self.dialog.winfo_screenwidth() // 2) - (dialog_width // 2)
            y = (self.dialog.winfo_screenheight() // 2) - (dialog_height // 2)
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        self._create_ui()
        
    def _create_ui(self):
        """Create the refinery dialog UI"""
        from core.constants import MINING_MATERIALS
        
        # Main frame
        main_frame = tk.Frame(self.dialog, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = tk.Label(main_frame, text="⚗️ Add Refinery Contents", 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Manual add section (moved to top for dropdown space)
        manual_frame = tk.LabelFrame(main_frame, text="🔍 Add Other Minerals", 
                                   bg="#1e1e1e", fg="#ffffff", 
                                   font=("Segoe UI", 10, "bold"))
        manual_frame.pack(fill="x", pady=(0, 15))
        
        manual_inner = tk.Frame(manual_frame, bg="#1e1e1e")
        manual_inner.pack(fill="x", padx=10, pady=10)
        
        # Configure grid columns for proper spacing
        manual_inner.columnconfigure(1, weight=1)  # Material dropdown column
        manual_inner.columnconfigure(3, weight=0)  # Quantity entry column
        
        # Material selection
        tk.Label(manual_inner, text="Material:", bg="#1e1e1e", fg="#ffffff").grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        self.material_var = tk.StringVar(value="Select Material...")
        
        # Material selection button using standard app styling
        material_btn = tk.Button(manual_inner, textvariable=self.material_var,
                               command=self._open_material_selector,
                               bg="#4a9eff", fg="#ffffff", 
                               font=("Segoe UI", 9))
        material_btn.grid(row=0, column=1, padx=5, sticky="w")
        
        # Quantity entry
        tk.Label(manual_inner, text="Quantity:", bg="#1e1e1e", fg="#ffffff").grid(row=0, column=2, sticky="w", padx=(10, 5))
        
        self.quantity_var = tk.StringVar()
        quantity_entry = tk.Entry(manual_inner, textvariable=self.quantity_var, width=8,
                                bg="#2d2d2d", fg="#ffffff", 
                                insertbackground="#ffffff",  # Cursor color
                                selectbackground="#404040",   # Selection background
                                selectforeground="#ffffff",   # Selection text
                                relief="sunken", bd=1)
        quantity_entry.grid(row=0, column=3, padx=5)
        
        tk.Label(manual_inner, text="tons", bg="#1e1e1e", fg="#ffffff").grid(row=0, column=4, sticky="w", padx=(5, 0))
        
        # Add button
        add_btn = tk.Button(manual_inner, text="+ Add", 
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
                                   text=f"📦 Cargo Hold Detected: {cargo_total} tons",
                                   bg="#2d2d2d", fg="#ffffff", 
                                   font=("Segoe UI", 10))
            summary_label.pack(pady=8)
        
        # Quick add from cargo section
        if self.current_cargo_items:
            cargo_frame = tk.LabelFrame(main_frame, text="📦 Quick Add from Current Cargo", 
                                      bg="#1e1e1e", fg="#ffffff", 
                                      font=("Segoe UI", 10, "bold"))
            cargo_frame.pack(fill="x", pady=(0, 15))
            
            cargo_inner = tk.Frame(cargo_frame, bg="#1e1e1e")
            cargo_inner.pack(fill="x", padx=10, pady=10)
            
            # Create quick-add buttons for materials in cargo
            row = 0
            col = 0
            for material, quantity in self.current_cargo_items.items():
                if material in MINING_MATERIALS:  # Only show known mining materials
                    material_frame = tk.Frame(cargo_inner, bg="#1e1e1e")
                    material_frame.grid(row=row, column=col, padx=5, pady=5, sticky="w")
                    
                    # Material label
                    mat_label = tk.Label(material_frame, text=f"{material}:", 
                                       bg="#1e1e1e", fg="#ffffff", 
                                       font=("Segoe UI", 9))
                    mat_label.pack(side="left")
                    
                    # Quick add buttons
                    for amount in [1, 4, 6, 8, 10]:
                        btn = tk.Button(material_frame, text=f"+{amount}t", 
                                      command=lambda m=material, a=amount: self._quick_add_material(m, a),
                                      bg="#404040", fg="#ffffff", 
                                      font=("Segoe UI", 8), width=6)
                        btn.pack(side="left", padx=2)
                    
                    col += 1
                    if col > 1:  # 2 columns
                        col = 0
                        row += 1
        
        # Current refinery contents
        contents_frame = tk.LabelFrame(main_frame, text="⚗️ Current Refinery Contents", 
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
        
        edit_btn = tk.Button(button_container, text="Edit Selected", 
                           command=self._edit_selected,
                           bg="#4a9eff", fg="#ffffff")
        edit_btn.pack(side="left", padx=(0, 5))
        
        remove_btn = tk.Button(button_container, text="Remove Selected", 
                             command=self._remove_selected,
                             bg="#ff6b6b", fg="#ffffff")
        remove_btn.pack(side="left")
        
        # Summary section
        self.summary_frame = tk.Frame(main_frame, bg="#2d2d2d", relief="raised", bd=1)
        self.summary_frame.pack(fill="x", pady=(0, 15))
        
        self.summary_label = tk.Label(self.summary_frame, 
                                    text="Refinery Total: 0 tons",
                                    bg="#2d2d2d", fg="#ffffff", 
                                    font=("Segoe UI", 10, "bold"))
        self.summary_label.pack(pady=8)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="#1e1e1e")
        button_frame.pack(fill="x")
        
        clear_btn = tk.Button(button_frame, text="Clear All", 
                            command=self._clear_all,
                            bg="#666666", fg="#ffffff")
        clear_btn.pack(side="left")
        
        cancel_btn = tk.Button(button_frame, text="Cancel", 
                             command=self._cancel,
                             bg="#666666", fg="#ffffff")
        cancel_btn.pack(side="right", padx=(5, 0))
        
        apply_btn = tk.Button(button_frame, text="Apply to Session", 
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
            messagebox.showerror("Refinery Capacity Exceeded", 
                               f"Refinery capacity is 10t maximum.\n"
                               f"Current: {current_total}t\n"
                               f"Available: {remaining_capacity}t\n"
                               f"Cannot add {amount}t")
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
        if not material or material == "Select Material...":
            messagebox.showerror("No Material Selected", "Please select a material before adding.")
            return
            
        try:
            quantity_str = self.quantity_var.get().strip()
            if not quantity_str:
                messagebox.showerror("No Quantity Entered", "Please enter a quantity.")
                return
                
            quantity = float(quantity_str)
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            
            # Check refinery capacity limit (10t max)
            current_total = sum(self.refinery_contents.values())
            if current_total + quantity > 10.0:
                remaining_capacity = 10.0 - current_total
                messagebox.showerror("Refinery Capacity Exceeded", 
                                   f"Refinery capacity is 10t maximum.\n"
                                   f"Current: {current_total}t\n"
                                   f"Available: {remaining_capacity}t\n"
                                   f"Cannot add {quantity}t")
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
    # import os removed (already imported globally)
        # Only trigger updates if we have a cargo monitor reference and it has the update function
        if hasattr(self, 'cargo_monitor') and hasattr(self.cargo_monitor, '_update_csv_after_refinery_addition'):
            # Check if there are recent session files that might need updating
            try:
                prospector_panel = getattr(self.cargo_monitor, 'main_app_ref', None)
                if prospector_panel and hasattr(prospector_panel, 'prospector_panel'):
                    reports_dir = prospector_panel.prospector_panel.reports_dir
                    if os.path.exists(reports_dir):
                        session_files = [f for f in os.listdir(reports_dir) 
                                       if f.startswith("Session_") and f.endswith(".txt")]
                        if session_files:
                            # Trigger the update with accumulated refinery contents
                            self.cargo_monitor._update_csv_after_refinery_addition(self.refinery_contents.copy())
            except Exception as e:
                print(f"Error checking for CSV update: {e}")

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
            messagebox.showwarning("No Selection", "Please select a material to edit.")
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
        edit_dialog.title("Edit Material Quantity")
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
        title_label = tk.Label(main_frame, text=f"Edit {material} Quantity", 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Current quantity info
        info_label = tk.Label(main_frame, text=f"Current quantity: {current_qty} tons", 
                             bg="#1e1e1e", fg="#cccccc", 
                             font=("Segoe UI", 10))
        info_label.pack(pady=(0, 10))
        
        # New quantity entry
        entry_frame = tk.Frame(main_frame, bg="#1e1e1e")
        entry_frame.pack(pady=(0, 20))
        
        tk.Label(entry_frame, text="New quantity:", bg="#1e1e1e", fg="#ffffff",
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
        
        tk.Label(entry_frame, text="tons", bg="#1e1e1e", fg="#ffffff",
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
        ok_btn = tk.Button(button_frame, text="OK", command=ok_clicked,
                          bg="#4caf50", fg="#ffffff", 
                          font=("Segoe UI", 9, "bold"), width=8)
        ok_btn.pack(side="left", padx=(0, 10))
        
        # Cancel button  
        cancel_btn = tk.Button(button_frame, text="Cancel", command=cancel_clicked,
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
        self.summary_label.configure(text=f"Refinery Total: {total} tons")
        
        # Update final calculation if we have cargo data
        if self.cargo_monitor:
            cargo_total = getattr(self.cargo_monitor, 'current_cargo', 0)
            final_total = cargo_total + total
            
            summary_text = f"Refinery Total: +{total} tons\n"
            summary_text += f"Final Total: {cargo_total} + {total} = {final_total} tons"
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
        selector.title("Select Material")
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
        title_label = tk.Label(selector, text="Select Mining Material", 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=15)
        
        # Search frame
        search_frame = tk.Frame(selector, bg="#1e1e1e")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        tk.Label(search_frame, text="Search:", bg="#1e1e1e", fg="#ffffff").pack(side="left")
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
        
        # Populate list
        materials = list(MINING_MATERIALS.keys())
        for material in sorted(materials):
            materials_list.insert(tk.END, material)
        
        # Search function
        def filter_materials(*args):
            search_term = search_var.get().lower()
            materials_list.delete(0, tk.END)
            for material in sorted(materials):
                if search_term in material.lower():
                    materials_list.insert(tk.END, material)
        
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
        
        select_btn = tk.Button(btn_frame, text="Select", command=select_material,
                             bg="#4a9eff", fg="#ffffff", font=("Segoe UI", 9, "bold"))
        select_btn.pack(side="right", padx=(5, 0))
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=cancel_selection,
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
        
        # Engineering materials grade mapping (Raw materials from mining only)
        self.MATERIAL_GRADES = {
            "Antimony": 2,
            "Arsenic": 2,
            "Boron": 3,
            "Cadmium": 3,
            "Carbon": 1,
            "Chromium": 2,
            "Germanium": 2,
            "Iron": 1,
            "Lead": 1,
            "Manganese": 2,
            "Nickel": 1,
            "Niobium": 3,
            "Phosphorus": 1,
            "Polonium": 4,
            "Rhenium": 1,
            "Selenium": 4,
            "Sulphur": 1,
            "Tin": 3,
            "Tungsten": 3,
            "Vanadium": 2,
            "Zinc": 2,
            "Zirconium": 2
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
        
        # Initialize JournalParser for proper Scan and SAASignalsFound processing
        # Add callback to notify Ring Finder when new hotspots are added
        self.journal_parser = JournalParser(self.journal_dir, self.user_db, self._on_hotspot_added)
        
        # Flag to track pending Ring Finder refreshes
        self._pending_ring_finder_refresh = False
        
        # Auto-refresh delay timer for ring scans (prevent rapid-fire searches)
        self._auto_refresh_timer = None
        self._auto_refresh_delay = 2000  # 2 seconds - reduced since EDSM fallback now happens immediately
        
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
    
    def _on_hotspot_added(self):
        """Callback triggered when new hotspot data is added to database"""
        try:
            # Access main app through main_app_ref if this is called from CargoMonitor
            main_app = getattr(self, 'main_app_ref', self)
            
            # Check if Ring Finder exists and is properly initialized
            ring_finder_ready = (hasattr(main_app, 'ring_finder') and 
                                 main_app.ring_finder is not None and
                                 hasattr(main_app.ring_finder, '_update_database_info'))
            
            if not ring_finder_ready:
                main_app._pending_ring_finder_refresh = True
                print("✓ Hotspot added to database (Ring Finder refresh pending)")
                return
                
            # Ring Finder exists - refresh it now
            print("✓ Hotspot added - refreshing Ring Finder database info")
            main_app._refresh_ring_finder()
            
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
    
    def _check_auto_refresh_ring_finder(self, scanned_system: str):
        """Check if Ring Finder should auto-refresh after ring scan - no delay for first scan, 2s delay for subsequent scans"""
        try:
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
                print(f"🔍 Auto-refresh: Reference system was empty, set to {scanned_system}")
            elif current_reference_system.lower() != scanned_system.lower():
                # Different system - reset first scan flag but don't refresh
                self._first_ring_scan_in_system = True
                return
            
            # Cancel any existing timer (reset approach)
            if self._auto_refresh_timer:
                main_app.after_cancel(self._auto_refresh_timer)
                self._auto_refresh_timer = None
            
            # Determine delay: 0 for first scan, 2s for subsequent scans
            if self._first_ring_scan_in_system:
                delay = 0  # Immediate refresh for first ring scan
                delay_text = "immediately"
                self._first_ring_scan_in_system = False  # Mark that first scan is done
            else:
                delay = self._auto_refresh_delay  # 2 second delay for subsequent scans
                delay_text = "in 2s"
            
            print(f"🔍 Auto-refresh: New hotspots found in {scanned_system} - {'updating' if delay == 0 else 'scheduling search'} {delay_text}")
            
            # Set status message
            if delay == 0:
                ring_finder.status_var.set(f"Found new hotspots - updating results")
            else:
                ring_finder.status_var.set(f"Found new hotspots - search in 2s")
            
            # Schedule the actual refresh with appropriate delay
            def do_delayed_refresh():
                try:
                    if delay > 0:  # Only update status if there was a delay
                        ring_finder.status_var.set(f"Found new hotspots - updating results")
                    ring_finder.search_hotspots()
                    # Clear status after 3 seconds
                    ring_finder.parent.after(3000, lambda: ring_finder.status_var.set(""))
                    self._auto_refresh_timer = None  # Clear timer reference
                except Exception as e:
                    print(f"Auto-refresh error: {e}")
            
            # Schedule refresh with appropriate delay (0 = immediate, >0 = delayed)
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
        self.cargo_window.title("Elite Mining - Cargo Monitor")
        
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
        title_label = tk.Label(main_frame, text="🚛 Cargo Hold Monitor", 
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
            font=("Consolas", 10, "normal"),
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
            text="🔍 Monitoring Elite Dangerous journal...",
            bg="#1e1e1e",
            fg="#888888",
            font=("Segoe UI", 8, "italic")
        )
        self.status_label.pack(anchor="w", pady=(5, 0))
        
        # Capacity status label
        self.capacity_label = tk.Label(
            main_frame,
            text="⚙️ Waiting for ship loadout...",
            bg="#1e1e1e",
            fg="#666666",
            font=("Segoe UI", 8, "italic")
        )
        self.capacity_label.pack(anchor="w", pady=(2, 0))
        
        # Refinery note - discrete version
        refinery_note = tk.Label(
            main_frame,
            text="ℹ️ Note: Refinery hopper contents excluded",
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
        
        close_btn = tk.Button(close_frame, text="✕ Close", 
                             command=self.close_window,
                             bg="#444444", fg="#ffffff",
                             activebackground="#555555", activeforeground="#ffffff",
                             font=("Segoe UI", 10, "bold"), relief="flat")
        close_btn.pack()
        
        self.set_position(self.position)
        
        # Force the window size and position after all setup is complete
        self.cargo_window.after(10, lambda: self.cargo_window.geometry(f"500x400+{self.window_x}+{self.window_y}"))
        
        self.update_display()
        
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
            
            # Notify main app of changes
            if self.update_callback:
                self.update_callback()
            
            if hasattr(self, 'status_label'):
                self.status_label.configure(text=f"✅ Cargo.json: {len(self.cargo_items)} items, {self.current_cargo}t")
            
            return True
            
        except Exception as e:
            return False
    
    def force_cargo_update(self):
        """Force read the latest cargo data from Cargo.json and journal"""
        if hasattr(self, 'status_label'):
            self.status_label.configure(text="🔄 Forcing cargo update...")
        
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
                        self.status_label.configure(text="❌ No cargo data - open cargo hold in Elite")
                        
        except Exception as e:
            if hasattr(self, 'status_label'):
                self.status_label.configure(text="❌ Error reading journal file")
    
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
            help_window.title("Cargo Monitor Help")
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
                                 font=("Consolas", 10), wrap=tk.WORD,
                                 yscrollcommand=scrollbar.set)
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.config(command=text_widget.yview)
            
            text_widget.insert(tk.END, instructions)
            text_widget.config(state=tk.DISABLED)
            
            # Add close button
            close_btn = tk.Button(help_window, text="✅ Got It!", 
                                 command=help_window.destroy,
                                 bg="#27ae60", fg="white", 
                                 font=("Arial", 12, "bold"))
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
                self.cargo_text.insert(tk.END, "�🔸 Empty cargo hold\n\n")
                self.cargo_text.insert(tk.END, "📋 To see your actual cargo:\n")
                self.cargo_text.insert(tk.END, "1. Open Elite Dangerous\n")
                self.cargo_text.insert(tk.END, "2. Open your cargo hold (4 key)\n") 
                self.cargo_text.insert(tk.END, "3. Click 'Force Update' button")
        else:
            # Sort items by quantity (highest first)
            sorted_items = sorted(self.cargo_items.items(), key=lambda x: x[1], reverse=True)
            
            # Add each cargo item with type icons - single line format with proper alignment
            for i, (item_name, quantity) in enumerate(sorted_items, 1):
                # Format item name (remove underscores, capitalize) 
                display_name = item_name.replace('_', ' ').replace('$', '').title()
                # Limit name length for better alignment
                if len(display_name) > 12:
                    display_name = display_name[:12]
                
                # Add type-specific icons (no space after - we'll add it in formatting)
                icon = ""
                if "limpet" in item_name.lower():
                    icon = "🤖"  # Robot for limpets
                elif any(mineral in item_name.lower() for mineral in ['painite', 'diamond', 'opal', 'alexandrite', 'serendibite', 'benitoite']):
                    icon = "💎"  # Diamond for precious materials
                elif any(metal in item_name.lower() for metal in ['gold', 'silver', 'platinum', 'palladium', 'osmium']):
                    icon = "🥇"  # Medal for metals
                else:
                    icon = "📦"  # Box for other cargo
                
                # Single line format with proper alignment: Icon + Name + Quantity
                line = f"{icon} {display_name:<12} {quantity:>4}t"
                self.cargo_text.insert(tk.END, f"{line}\n")
            
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
        
        # Auto-scroll to bottom to see new items
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
                    self.status_label.configure(text="❌ Elite Dangerous folder not found")
                return
                
            journal_files = glob.glob(os.path.join(self.journal_dir, "Journal.*.log"))
            if not journal_files:
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="❌ No journal files found")
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
                self.status_label.configure(text="❌ Journal monitoring error")
    
    def scan_journal_for_cargo_capacity(self, journal_file):
        """Scan existing journal file for the most recent CargoCapacity, current system location, and ring metadata"""
        try:
            with open(journal_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
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
                        if system_name:
                            self.current_system = system_name
                            location_found = True
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
                        messagebox.showinfo("Refinery Contents Added", 
                                          f"Added {refinery_total} tons from refinery.\n"
                                          f"New total: {self.current_cargo} tons\n\n"
                                          f"These materials will be included in mining reports and statistics.",
                                          parent=parent_window)
                    
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
            add_refinery = messagebox.askyesno(
                "Refinery Materials", 
                "Do you have any additional materials in your refinery that you want to add to this session?",
                parent=parent_window
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
                        messagebox.showinfo("Refinery Contents Added", 
                                          f"Added {refinery_total} tons from refinery.\n\n"
                                          f"These materials will be included in your multi-session mining report.",
                                          parent=parent_window)
                        
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
                    self.status_label.configure(text="🚀 Ship changed - updating cargo capacity...")
                
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
                        self.status_label.configure(text="⚠️ Capacity detection failed - waiting for game data...")
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
                
                if item_name in self.cargo_items:
                    new_qty = max(0, self.cargo_items[item_name] - count)
                    if new_qty > 0:
                        self.cargo_items[item_name] = new_qty
                    else:
                        del self.cargo_items[item_name]
                    
                    self.current_cargo = sum(self.cargo_items.values())
                    self.update_display()
                    
                    if hasattr(self, 'status_label'):
                        self.status_label.configure(text=f"🗑️ Ejected {count}x {item_name}")
                    
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
                        self.status_label.configure(text="⚙️ Cargo module changed - updating capacity...")
                    
                    # Force immediate capacity refresh
                    refresh_success = self.refresh_ship_capacity()
                    
                    # If Status.json doesn't have updated capacity yet, try journal scan
                    if not refresh_success:
                        self._force_loadout_scan()
                    
                    # Final fallback - force a delayed refresh to catch Status.json updates
                    if hasattr(self, 'cargo_window') and self.cargo_window:
                        self.cargo_window.after(1000, self._delayed_capacity_refresh)

            elif event_type in ["FSDJump", "Location", "CarrierJump"]:
                # Track current system for hotspot detection
                system_name = event.get("StarSystem", "")
                print(f"DEBUG: Processing {event_type} event for system: {system_name}")
                
                if system_name:
                    self.current_system = system_name
                    
                    # Also add to visited systems database
                    timestamp = event.get("timestamp", "")
                    system_address = event.get("SystemAddress")
                    star_pos = event.get("StarPos", [])
                    
                    print(f"DEBUG: Event data - timestamp: {timestamp}, system_address: {system_address}, star_pos: {star_pos}")
                    
                    coordinates = None
                    if len(star_pos) >= 3:
                        coordinates = (star_pos[0], star_pos[1], star_pos[2])
                        print(f"DEBUG: Parsed coordinates: {coordinates}")
                    
                    try:
                        print(f"DEBUG: Attempting to add visited system: {system_name}")
                        self.user_db.add_visited_system(
                            system_name=system_name,
                            visit_date=timestamp,
                            system_address=system_address,
                            coordinates=coordinates
                        )
                        print(f"DEBUG: Successfully added visited system: {system_name}")
                    except Exception as e:
                        print(f"Error adding visited system: {e}")
                        print(f"DEBUG: Full error details - system: {system_name}, timestamp: {timestamp}, address: {system_address}, coords: {coordinates}")
                else:
                    print(f"DEBUG: No system name found in {event_type} event")
                        
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
                    print(f"🔍 Processing SAASignalsFound: {body_name} in {self.current_system}")
                    
                    self.journal_parser.process_saa_signals_found(event, self.current_system)
                    
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
                    
                    # Auto-search refresh: Check if Ring Finder should update results
                    print(f"[AUTO-REFRESH DEBUG] SAASignalsFound processing complete, checking auto-refresh for system: {self.current_system}")
                    self._check_auto_refresh_ring_finder(self.current_system)
                    
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
                self.status_label.configure(text="⚠️ Status.json error - checking journal...")
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
                self.status_label.configure(text="🔄 Retrying capacity detection...")
            
            # Try all methods again
            if self.refresh_ship_capacity() or self._validate_cargo_capacity():
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="✅ Capacity detected successfully")
            else:
                if hasattr(self, 'status_label'):
                    self.status_label.configure(text="⚠️ Using default capacity - open cargo in game to update")
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
        
        # Add refinery contents to materials_mined (not just totals)
        # Check current refinery contents
        if hasattr(self, 'refinery_contents') and self.refinery_contents:
            for material_name, refinery_qty in self.refinery_contents.items():
                if material_name in materials_mined:
                    materials_mined[material_name] += refinery_qty
                else:
                    materials_mined[material_name] = refinery_qty
        
        # Clear refinery contents after adding to prevent reuse in next session
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
            print("[DEBUG] get_live_session_materials: No session snapshot!")
            return {}
        
        # Check if multi-session mode is active via prospector panel
        is_multi_session = False
        if (hasattr(self, 'prospector_panel') and 
            self.prospector_panel and 
            hasattr(self.prospector_panel, 'multi_session_var')):
            is_multi_session = bool(self.prospector_panel.multi_session_var.get())
        
        print(f"[DEBUG] get_live_session_materials: is_multi_session={is_multi_session}")
        print(f"[DEBUG] session_minerals_mined={self.session_minerals_mined}")
        print(f"[DEBUG] current cargo_items={self.cargo_items}")
        
        materials_mined = {}
        
        if is_multi_session:
            # Multi-session mode: Use cumulative session tracking (already includes refinery)
            for material_name, total_mined in self.session_minerals_mined.items():
                materials_mined[material_name] = round(total_mined, 1)
            print(f"[DEBUG] Multi-session materials_mined result: {materials_mined}")
        else:
            # Normal mode: Compare current cargo to session start (existing behavior)
            start_items = self.session_start_snapshot['cargo_items']
            current_items = self.cargo_items
            
            print(f"[DEBUG] Single-session start_items: {start_items}")
            print(f"[DEBUG] Single-session current_items: {current_items}")
            
            # Calculate materials that increased during the session
            for item_name, current_qty in current_items.items():
                # Skip limpets and non-materials
                if ("limpet" in item_name.lower() or 
                    "scrap" in item_name.lower() or 
                    "data" in item_name.lower()):
                    continue
                    
                start_qty = start_items.get(item_name, 0)
                if current_qty > start_qty:
                    materials_mined[item_name] = round(current_qty - start_qty, 1)
            print(f"[DEBUG] Single-session materials_mined result: {materials_mined}")
            
            # Add refinery contents only in normal mode
            if hasattr(self, 'refinery_contents') and self.refinery_contents:
                for material_name, refinery_qty in self.refinery_contents.items():
                    if material_name in materials_mined:
                        materials_mined[material_name] += refinery_qty
                    else:
                        materials_mined[material_name] = refinery_qty
                    materials_mined[material_name] = round(materials_mined[material_name], 1)
        
        print(f"[DEBUG] FINAL materials_mined (with refinery): {materials_mined}")
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
            
            # Check if we have access to the prospector panel
            if not hasattr(self, 'main_app_ref') or not hasattr(self.main_app_ref, 'prospector_panel'):
                print("No prospector panel reference - cannot auto-update CSV")
                return
                
            prospector_panel = self.main_app_ref.prospector_panel
            reports_dir = prospector_panel.reports_dir
            
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
            
            # Parse existing material breakdown and add new materials
            updated_materials = {}
            total_added = 0.0
            
            # Check if there's already a REFINED CARGO TRACKING section
            cargo_section_match = re.search(r'=== REFINED CARGO TRACKING ===(.*?)(?:===|\Z)', content, re.DOTALL)
            if cargo_section_match:
                # Parse existing materials
                cargo_text = cargo_section_match.group(1)
                existing_materials = re.findall(r'^([A-Za-z\s]+):\s*([\d.]+)t\s*$', cargo_text, re.MULTILINE)
                for mat_name, quantity in existing_materials:
                    # Filter out summary entries like "Total Cargo Collected"
                    mat_name_clean = mat_name.strip()
                    if mat_name_clean.lower() not in ['total cargo collected', 'total', 'cargo collected']:
                        updated_materials[mat_name_clean] = float(quantity)
            
            # Add new refinery materials
            for material_name, quantity in refinery_materials.items():
                if material_name in updated_materials:
                    updated_materials[material_name] += quantity
                else:
                    updated_materials[material_name] = quantity
                total_added += quantity
            
            # Update session header with new total
            header_match = re.search(r'^(Session: .* — .* — .* — Total )(\d+(?:\.\d+)?)t', content, re.MULTILINE)
            if header_match:
                old_total = float(header_match.group(2))
                new_total = old_total + total_added
                new_header = f"{header_match.group(1)}{new_total:.0f}t"
                content = content.replace(header_match.group(0), new_header)
            
            # Update or add REFINED CARGO TRACKING section
            cargo_breakdown_text = "\n=== REFINED CARGO TRACKING ===\n"
            prospectors_line = ""
            if "Prospector Limpets Used:" in content:
                prospector_match = re.search(r'Prospector Limpets Used:\s*(\d+)', content)
                if prospector_match:
                    cargo_breakdown_text += f"Prospector Limpets Used: {prospector_match.group(1)}\n"
            
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

class App(tk.Tk):
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

        # --- Dark style for Entry fields ---
        style.configure("TEntry",
                        fieldbackground="#1e1e1e",
                        foreground="#ffffff",
                        insertcolor="#ffffff")

        style.configure("Treeview",
                        background="#1e1e1e",
                        fieldbackground="#1e1e1e",
                        foreground="#e6e6e6",
                        borderwidth=0)
        style.map("Treeview",
                   background=[("selected", "#444444")],
                   foreground=[("selected", "#ffffff")])

        style.configure("Treeview.Heading",
                        background="#333333",
                        foreground="#ffffff",
                        relief="raised")
        style.map("Treeview.Heading",
                   background=[("active", "#444444"), ("pressed", "#222222")],
                   foreground=[("active", "#ffffff"), ("pressed", "#ffffff")])

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

        # If Treeview exists, configure darkrow tag
        try:
            self.tree.tag_configure("darkrow", background="#1e1e1e", foreground="#e6e6e6")
        except Exception:
            pass

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

        style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
        style.configure("TNotebook.Tab",
                        background="#444444",
                        foreground="#ffffff",
                        padding=[8, 4],
                        relief="raised",
                        borderwidth=1)
        style.map("TNotebook.Tab",
                   background=[("selected", "#555555")],
                   foreground=[("selected", "#ffffff")])


        # --- Dark theme setup with custom Dark.TButton style ---
        try:
            self.tk.call("source", os.path.join(get_app_data_dir(), "sun-valley.tcl"))
            self.tk.call("set_theme", "dark")
        except Exception:
            dark_bg = "#1e1e1e"
            dark_fg = "#e6e6e6"
            accent = "#2d2d2d"
            style.configure(".", background=dark_bg, foreground=dark_fg)
            style.configure("TLabel", background=dark_bg, foreground=dark_fg)
            style.configure("TFrame", background=dark_bg)
            style.configure("TNotebook", background=accent)
            style.configure("TNotebook.Tab", background=accent, foreground=dark_fg)
            style.map("TNotebook.Tab", background=[("selected", dark_bg)])

            # Custom dark button style
            style.configure("Dark.TButton", background="#444444", foreground="#ffffff", font=("Segoe UI", 9, "bold"))
            style.map("Dark.TButton",
                       background=[("active", "#555555"), ("disabled", "#2a2a2a")],
                       foreground=[("disabled", "#666666")])

            style.configure("TCheckbutton", background=dark_bg, foreground=dark_fg)
            style.configure("TRadiobutton", background=dark_bg, foreground=dark_fg)
            style.configure("TCombobox", fieldbackground=dark_bg, background=accent, foreground="#ffffff")
            style.map("TCombobox", fieldbackground=[("readonly", dark_bg)], foreground=[("readonly", "#ffffff")])

            # Apply dark theme to classic widgets too
            self.option_add("*Listbox.background", dark_bg)
            self.option_add("*Listbox.foreground", dark_fg)
            self.option_add("*Entry.background", "#ffffff")  # White background for better readability
            self.option_add("*Entry.foreground", "#000000")  # Black text for contrast
            self.option_add("*Text.background", dark_bg)
            self.option_add("*Text.foreground", dark_fg)
            self.option_add("*TMenubutton.background", dark_bg)
            self.option_add("*TMenubutton.foreground", dark_fg)

        self.title(f"{APP_TITLE} — {APP_VERSION}")
        self.resizable(True, True)
        self.minsize(850, 680)  # Increased height to ensure status bar is visible
        
        # Set window class name for better Windows integration (PowerToys compatibility)
        try:
            self.wm_class("EliteMining", "EliteMining")
        except:
            pass
        
        # Set additional window attributes for better Windows tool compatibility
        try:
            # Make window more recognizable to Windows tools like PowerToys
            self.attributes('-toolwindow', False)  # Show in taskbar
            self.focus_force()  # Ensure window gets focus
        except Exception as e:
            print(f"Window attributes setup failed: {e}")

        # Restore window geometry
        self._restore_window_geometry()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Two-column layout: balanced dashboard + narrower presets sidebar
        self.columnconfigure(0, weight=2, minsize=300)   # Dashboard content (tabs) - balanced
        self.columnconfigure(1, weight=1, minsize=300)   # Ship Presets sidebar - narrower
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
            
        # Initialize cargo monitor with correct app directory (after va_root is set)
        app_dir = get_app_data_dir() if getattr(sys, 'frozen', False) else None
        self.cargo_monitor = CargoMonitor(update_callback=self._on_cargo_changed, 
                                        capacity_changed_callback=self._on_cargo_capacity_detected,
                                        ship_info_changed_callback=self._on_ship_info_changed,
                                        app_dir=app_dir)
        # Set the main app reference so cargo monitor can access prospector panel later
        self.cargo_monitor.main_app_ref = self
        
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
        
        # Position options for overlay placement
        self.text_overlay_position = tk.StringVar(value="Upper Right")  # Default upper right
        self.position_options = {
            "Upper Right": "upper_right",
            "Upper Left": "upper_left"
        }
        
        # Text size options for overlay
        self.text_overlay_size = tk.StringVar(value="Normal")  # Default normal size
        self.size_options = {
            "Small": 12,      # Small text
            "Normal": 16,     # Normal text
            "Large": 20       # Large text (increased from 18)
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
        self.text_overlay_position.trace('w', self._on_position_change)
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
        print(f"✅ EDDN sender {'enabled' if self.eddn_send_enabled.get() == 1 else 'disabled'}")
        
        # Initialize market handler for Market.json processing
        from market_handler import MarketHandler
        self.market_handler = MarketHandler(self.eddn_sender)
        
        # Watch for Market.json changes to send to EDDN
        from file_watcher import get_file_watcher
        file_watcher = get_file_watcher()
        journal_dir = self.prospector_panel.journal_dir if hasattr(self, 'prospector_panel') else None
        if journal_dir and os.path.exists(journal_dir):
            file_watcher.add_watch(journal_dir, self._on_journal_file_change)
            print(f"✅ Watching journal directory for Market.json updates")

        # Build UI
        self._build_ui()
        
        # Check for updates after UI is ready (automatic check once per day)
        self.after(1000, self._check_for_updates_startup)  # Check after 1 second
        
        # Auto-scan new journal entries after startup
        self.after(2000, self._auto_scan_journals_startup)  # Check after 2 seconds

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
        # Left pane: tabs container
        content_frame = ttk.Frame(self, padding=(10, 6, 6, 6))
        content_frame.grid(row=0, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        content_frame.rowconfigure(1, weight=0)

        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # Mining Session tab (moved from Dashboard, with all its sub-tabs)
        mining_session_tab = ttk.Frame(self.notebook, padding=8)
        self._build_mining_session_tab(mining_session_tab)
        self.notebook.add(mining_session_tab, text="Mining Session")

        # VoiceAttack Controls tab (combined Firegroups + Mining Controls)
        voiceattack_tab = ttk.Frame(self.notebook, padding=8)
        self._build_voiceattack_controls_tab(voiceattack_tab)
        self.notebook.add(voiceattack_tab, text="VoiceAttack Controls")

        # Hotspots Finder tab
        ring_finder_tab = ttk.Frame(self.notebook, padding=8)
        self._setup_ring_finder(ring_finder_tab)
        self.notebook.add(ring_finder_tab, text="Hotspots Finder")

        # Commodity Market tab
        marketplace_tab = ttk.Frame(self.notebook, padding=8)
        self._build_marketplace_tab(marketplace_tab)
        self.notebook.add(marketplace_tab, text="Commodity Market")
        
        # Auto-populate marketplace system after UI is built
        self.after(3000, self._populate_marketplace_system)

        # Settings tab (simplified with remaining sub-tabs)
        settings_tab = ttk.Frame(self.notebook, padding=8)
        self._build_settings_notebook(settings_tab)
        self.notebook.add(settings_tab, text="Settings")

        # Actions row (global)
        actions = ttk.Frame(content_frame)
        actions.grid(row=1, column=0, sticky="w", pady=(8, 0))

        # Create the sidebar (Ship Presets + Cargo Monitor)
        self._create_main_sidebar()
        
        import_btn = tk.Button(
            actions, 
            text="⬇ Import from Game", 
            command=self._import_all_from_txt,
            bg="#3a3a3a",           # Subtle dark gray
            fg="#e0e0e0", 
            activebackground="#4a4a4a", 
            activeforeground="#ffffff",
            relief="ridge",         # Subtle raised effect
            bd=1,                   
            padx=14,                
            pady=6,
            font=("Segoe UI", 9, "normal"),  
            cursor="hand2"
        )
        import_btn.grid(row=0, column=0, sticky="w")
        ToolTip(import_btn, "Import current game settings\nThis reads your current in-game configuration")
        
        apply_btn = tk.Button(
            actions, 
            text="⬆ Apply to Game", 
            command=self._save_all_to_txt,
            bg="#2a4a2a",           # Subtle green tint
            fg="#e0e0e0", 
            activebackground="#3a5a3a", 
            activeforeground="#ffffff",
            relief="ridge",         # Subtle raised effect
            bd=1,                   
            padx=14,                
            pady=6,
            font=("Segoe UI", 9, "normal"),  
            cursor="hand2"
        )
        apply_btn.grid(row=0, column=1, sticky="w", padx=(10, 0))
        ToolTip(apply_btn, "Send your current settings to the game via VoiceAttack\nThis writes configuration to variable files that VoiceAttack uses")

        # Configure column weights for proper spacing
        actions.grid_columnconfigure(2, weight=1)  # Expandable space

        # Status bar - span both columns
        self.status = tk.StringVar(value=f"{APP_TITLE} {APP_VERSION} | Installation: {self.va_root}")
        sb = ttk.Label(self, textvariable=self.status, relief=tk.SUNKEN, anchor="w")
        sb.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(2, 6))

        # Import existing values
        self.after(100, self._import_all_from_txt)
        # Set up tracing AFTER loading from .txt files
        self.after(200, self._setup_announcement_tracing)
        
        # Initialize color menu display after UI is built
        self.after(200, self._update_color_menu_display)
        
        # Update journal label after everything is initialized
        self.after(150, self._update_journal_label)
        
        # Reset window size for better tab layout - smaller window size
        self.after(50, lambda: self.geometry("1100x650"))

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
        cargo_frame = ttk.LabelFrame(parent_frame, text="🚛 Cargo Monitor", padding=6)
        cargo_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        cargo_frame.columnconfigure(0, weight=1)
        cargo_frame.rowconfigure(1, weight=1)
        
        # Simple header without buttons
        header_frame = ttk.Frame(cargo_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header_frame.columnconfigure(1, weight=1)
        
        # Title and summary in one line
        title_label = ttk.Label(header_frame, text="Cargo Status:", font=("Segoe UI", 10, "bold"))
        title_label.grid(row=0, column=0, sticky="w")
        
        self.integrated_cargo_summary = ttk.Label(header_frame, text="0/200t (0%) - Empty", 
                                                 font=("Segoe UI", 10))
        self.integrated_cargo_summary.grid(row=0, column=1, sticky="w", padx=(6, 0))
        
        # Compact content area - much smaller height
        content_frame = ttk.Frame(cargo_frame)
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)
        
        # Cargo text widget with bigger font and better alignment
        self.integrated_cargo_text = tk.Text(
            content_frame,
            bg="#1e1e1e",
            fg="#ffffff",
            font=("Consolas", 9, "normal"),  # Monospace font for perfect alignment
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",  # Enable word wrap for better text flow
            height=8,  # Increased from 3 to 8 lines for more cargo display space
            width=45   # Further increased width to show complete cargo info
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
        
        # Update cargo list - very compact format
        self.integrated_cargo_text.configure(state="normal")
        self.integrated_cargo_text.delete(1.0, tk.END)
        
        if not cargo.cargo_items:
            if cargo.current_cargo > 0:
                self.integrated_cargo_text.insert(tk.END, f"📊 {cargo.current_cargo}t total\n💡 No item details")
            else:
                self.integrated_cargo_text.insert(tk.END, "📦 Empty cargo hold\n⛏️ Start mining!")
        else:
            # Vertical list with better alignment - show ALL items
            sorted_items = sorted(cargo.cargo_items.items(), key=lambda x: x[1], reverse=True)
            
            # Show all items
            for i, (item_name, quantity) in enumerate(sorted_items):
                # Clean up item name for display - use full name, not truncated
                display_name = item_name.replace('_', ' ').replace('$', '').title()
                
                # Simple icons with better spacing
                if "limpet" in item_name.lower():
                    icon = "🤖"
                elif any(m in item_name.lower() for m in ['painite', 'diamond', 'opal']):
                    icon = "💎"
                elif any(m in item_name.lower() for m in ['gold', 'silver', 'platinum', 'osmium', 'praseodymi']):
                    icon = "🥇"
                else:
                    icon = "📦"
                
                # Use precise character positioning with monospace font
                # Format: Icon(2) + Space(1) + Name(15) + Quantity(right-aligned)
                name_field = f"{display_name:<15}"[:15]  # Exactly 15 characters, truncated if needed
                quantity_text = f"{quantity}t"
                
                line = f"{icon} {name_field} {quantity_text:>4}"
                self.integrated_cargo_text.insert(tk.END, line)
                
                # Add newline for all but the last item
                if i < len(sorted_items) - 1:
                    self.integrated_cargo_text.insert(tk.END, "\n")
        
        # Display Engineering Materials section
        if cargo.materials_collected:
            self.integrated_cargo_text.insert(tk.END, "\n\n" + "─" * 25)
            self.integrated_cargo_text.insert(tk.END, "\nEngineering Materials 🔩\n")
            
            # Sort materials alphabetically
            sorted_materials = sorted(cargo.materials_collected.items(), key=lambda x: x[0])
            
            for i, (material_name, quantity) in enumerate(sorted_materials):
                # Get grade for this material
                grade = cargo.MATERIAL_GRADES.get(material_name, 0)
                
                # Use localized name for display if available, otherwise use English name
                display_name = cargo.materials_localized_names.get(material_name, material_name)[:13]
                grade_text = f"(G{grade})"
                line = f"{display_name:<13} {grade_text} {quantity:>4}"
                self.integrated_cargo_text.insert(tk.END, line)
                
                # Add newline for all but the last item
                if i < len(sorted_materials) - 1:
                    self.integrated_cargo_text.insert(tk.END, "\n")
        
        
        # Add refinery note at the very bottom with proper spacing
        self.integrated_cargo_text.insert(tk.END, "\n\n" + "─" * 25)
        
        # Configure tag for small italic text - left aligned
        self.integrated_cargo_text.tag_configure("small_italic", font=("Consolas", 8, "italic"), foreground="#888888", justify="left")
        
        # Insert refinery note with formatting - get position before inserting
        note_start_index = self.integrated_cargo_text.index(tk.INSERT)
        self.integrated_cargo_text.insert(tk.END, "\nNote: Contents in Refinery not included in totals")
        note_end_index = self.integrated_cargo_text.index(tk.INSERT)
        
        # Apply formatting to the note text only
        try:
            self.integrated_cargo_text.tag_add("small_italic", note_start_index, note_end_index)
        except tk.TclError:
            # If tagging fails, just continue without formatting
            pass
        
        self.integrated_cargo_text.configure(state="disabled")
        
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

    def _refresh_ring_finder(self):
        """Refresh Ring Finder database info and cache after hotspot added"""
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
                messagebox.showinfo("Reset Complete", 
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

        header = ttk.Label(frame, text="Assign Firegroups (A–H) and Primary / Secondary Fire Buttons",
                           font=("Segoe UI", 11, "bold"))
        header.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="Firegroup").grid(row=1, column=1, sticky="w", padx=(0, 6))
        ttk.Label(frame, text="Primary Fire Button").grid(row=1, column=2, sticky="w")
        ttk.Label(frame, text="Secondary Fire Button").grid(row=1, column=3, sticky="w")

        row = 2
        for tool in TOOL_ORDER:
            cfg = VA_VARS[tool]
            ttk.Label(frame, text=tool).grid(row=row, column=0, sticky="w", pady=3)

            if cfg["fg"] is not None:
                cb = ttk.Combobox(frame, values=FIREGROUPS, width=6, textvariable=self.tool_fg[tool], state="readonly")
                cb.grid(row=row, column=1, sticky="w")
            else:
                ttk.Label(frame, text="—").grid(row=row, column=1, sticky="w")

            if cfg["btn"] is not None:
                tk.Radiobutton(frame, text="Primary", value=1, variable=self.tool_btn[tool], bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), padx=4, pady=2, anchor="w").grid(row=row, column=2, sticky="w")
                tk.Radiobutton(frame, text="Secondary", value=2, variable=self.tool_btn[tool], bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), padx=4, pady=2, anchor="w").grid(row=row, column=3, sticky="w")
            else:
                ttk.Label(frame, text="—").grid(row=row, column=2, sticky="w")
                ttk.Label(frame, text="—").grid(row=row, column=3, sticky="w")
            row += 1

        # Tip card (light grey) with bullets
        card = tk.Frame(frame, bg="#1e1e1e", borderwidth=0, relief="flat", highlightthickness=0, highlightbackground="#1e1e1e")
        card.grid(row=row, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        card.columnconfigure(0, weight=1)

        tip_header = tk.Label(card, text="Tips/help:", font=("Segoe UI", 9, "bold"), anchor="w", bg="#1e1e1e", fg="#ffffff", borderwidth=0, relief="flat", highlightthickness=0)
        tip_header.grid(row=0, column=0, sticky="w", padx=8, pady=(20, 2))

        tips = [
            "For core mining, Set Pulse Wave Analyser and Prospector Limpet to the same firegroup with different Fire Buttons.",
            "Set your collector limpets to the same firegroup as your mining lasers and MVR.",
        ]
        r = 1
        for tip in tips:
            lbl = tk.Label(
                card,
                text=f"• {tip}",
                wraplength=600,
                justify="left",
                fg="#ffffff",
                bg="#1e1e1e",
                font=("Segoe UI", 9),
            )
            lbl.grid(row=r, column=0, sticky="w", padx=16, pady=1)
            r += 1

        # Useful Links section
        links_header = tk.Label(card, text="Useful Links:", font=("Segoe UI", 9, "bold"), anchor="w", bg="#1e1e1e", fg="#ffffff", borderwidth=0, relief="flat", highlightthickness=0)
        links_header.grid(row=r, column=0, sticky="w", padx=8, pady=(15, 2))
        r += 1

        # Create links with click functionality
        import webbrowser
        
        def open_miners_tool():
            webbrowser.open("https://edtools.cc/miner")
        
        def open_edmining():
            webbrowser.open("https://edmining.com/")
        
        def open_elite_miners_reddit():
            webbrowser.open("https://www.reddit.com/r/EliteMiners/")
        
        def open_discord():
            webbrowser.open("https://discord.gg/5dsF3UshRR")
        
        # Miners Tool link
        miners_link = tk.Label(
            card,
            text="• Miners Tool (edtools.cc/miner) - Mining optimization tools",
            wraplength=600,
            justify="left",
            fg="#e0e0e0",
            bg="#1e1e1e",
            font=("Segoe UI", 9, "italic"),
            cursor="hand2"
        )
        miners_link.grid(row=r, column=0, sticky="w", padx=16, pady=1)
        miners_link.bind("<Button-1>", lambda e: open_miners_tool())
        ToolTip(miners_link, "Click to open Miners Tool website\nHelps with mining optimization and route planning")
        r += 1
        
        # EDMining link
        edmining_link = tk.Label(
            card,
            text="• EDMining (edmining.com) - Mining database and tools",
            wraplength=600,
            justify="left",
            fg="#e0e0e0",
            bg="#1e1e1e",
            font=("Segoe UI", 9, "italic"),
            cursor="hand2"
        )
        edmining_link.grid(row=r, column=0, sticky="w", padx=16, pady=1)
        edmining_link.bind("<Button-1>", lambda e: open_edmining())
        ToolTip(edmining_link, "Click to open EDMining website\nComprehensive mining database and community tools")
        r += 1
        
        # Elite Miners Reddit link
        reddit_link = tk.Label(
            card,
            text="• Elite Miners Reddit (r/EliteMiners) - Mining community",
            wraplength=600,
            justify="left",
            fg="#e0e0e0",
            bg="#1e1e1e",
            font=("Segoe UI", 9, "italic"),
            cursor="hand2"
        )
        reddit_link.grid(row=r, column=0, sticky="w", padx=16, pady=1)
        reddit_link.bind("<Button-1>", lambda e: open_elite_miners_reddit())
        ToolTip(reddit_link, "Click to open Elite Miners Reddit community\nDiscussions, tips, and support from fellow miners")
        r += 1
        
        # EliteMining Discord link with icon
        discord_frame = tk.Frame(card, bg="#1e1e1e")
        discord_frame.grid(row=r, column=0, sticky="w", padx=16, pady=1)
        
        try:
            discord_icon_path = os.path.join(get_app_data_dir(), "Images", "Discord-Symbol-Blurple.png")
            if os.path.exists(discord_icon_path):
                from PIL import Image, ImageTk
                discord_img = Image.open(discord_icon_path)
                discord_img = discord_img.resize((16, 16), Image.Resampling.LANCZOS)
                discord_photo = ImageTk.PhotoImage(discord_img)
                
                discord_icon = tk.Label(discord_frame, image=discord_photo, bg="#1e1e1e", cursor="hand2")
                discord_icon.image = discord_photo  # Keep a reference
                discord_icon.grid(row=0, column=0, sticky="w")
                discord_icon.bind("<Button-1>", lambda e: open_discord())
                ToolTip(discord_icon, "Click to join EliteMining Discord server\nCommunity chat, support, and mining discussions")
                
                discord_text = tk.Label(
                    discord_frame,
                    text=" EliteMining Discord - Join our community chat",
                    wraplength=580,
                    justify="left",
                    fg="#e0e0e0",
                    bg="#1e1e1e",
                    font=("Segoe UI", 9, "italic"),
                    cursor="hand2"
                )
                discord_text.grid(row=0, column=1, sticky="w")
                discord_text.bind("<Button-1>", lambda e: open_discord())
                ToolTip(discord_text, "Click to join EliteMining Discord server\nCommunity chat, support, and mining discussions")
            else:
                # Fallback to text-only link if icon not found
                discord_text_only = tk.Label(
                    card,
                    text="• EliteMining Discord - Join our community chat",
                    wraplength=600,
                    justify="left",
                    fg="#e0e0e0",
                    bg="#1e1e1e",
                    font=("Segoe UI", 9, "italic"),
                    cursor="hand2"
                )
                discord_text_only.grid(row=r, column=0, sticky="w", padx=16, pady=1)
                discord_text_only.bind("<Button-1>", lambda e: open_discord())
                ToolTip(discord_text_only, "Click to join EliteMining Discord server\nCommunity chat, support, and mining discussions")
        except Exception as e:
            # Fallback to text-only link if any error occurs
            print(f"[DEBUG] Discord icon loading failed: {e}")
            import traceback
            traceback.print_exc()
            discord_text_only = tk.Label(
                card,
                text="• EliteMining Discord - Join our community chat",
                wraplength=600,
                justify="left",
                fg="#e0e0e0",
                bg="#1e1e1e",
                font=("Segoe UI", 9, "italic"),
                cursor="hand2"
            )
            discord_text_only.grid(row=r, column=0, sticky="w", padx=16, pady=1)
            discord_text_only.bind("<Button-1>", lambda e: open_discord())
            ToolTip(discord_text_only, "Click to join EliteMining Discord server\nCommunity chat, support, and mining discussions")
        
        r += 1

        # --- Add spacer row to push logos section to bottom of Tip card ---
        card.rowconfigure(r, weight=1)
        r += 1
        
        # --- Support message and logos at bottom ---
        support_frame = tk.Frame(card, bg="#1e1e1e")
        support_frame.grid(row=r, column=0, sticky="sew", padx=8, pady=(5, 12))
        support_frame.columnconfigure(0, weight=0)  # Logo fixed width
        support_frame.columnconfigure(1, weight=1)  # Text expands
        support_frame.columnconfigure(2, weight=0)  # PayPal fixed width
        
        # --- EliteMining logo on the left ---
        try:
            # import os removed (already imported globally)
            import sys
            
            # Use consistent path detection like config.py
            if getattr(sys, 'frozen', False):
                # Running as compiled executable - images are in app folder
                exe_dir = os.path.dirname(sys.executable)
                parent_dir = os.path.dirname(exe_dir)
                logo_path = os.path.join(parent_dir, 'app', 'Images', 'EliteMining_txt_logo_transp_resize.png')
            else:
                # Running in development mode
                logo_path = os.path.join(os.path.dirname(__file__), 'Images', 'EliteMining_txt_logo_transp_resize.png')
            
            try:
                from PIL import Image, ImageTk
                if os.path.exists(logo_path):
                    img = Image.open(logo_path)
                    # Resize with much smaller height for compact appearance
                    img = img.resize((200, 35), Image.Resampling.LANCZOS)
                    self.logo_photo = ImageTk.PhotoImage(img)
                    logo_label = tk.Label(support_frame, image=self.logo_photo, bg="#1e1e1e", cursor="hand2")
                    logo_label.grid(row=0, column=0, sticky="s", padx=(0, 15), pady=(15, 0))
                    
                    # Make logo clickable to open GitHub
                    def open_github(event=None):
                        webbrowser.open("https://github.com/Viper-Dude/EliteMining")
                    logo_label.bind("<Button-1>", open_github)
            except ImportError:
                # Fallback to tkinter PhotoImage with subsample for resizing
                if os.path.exists(logo_path):
                    self.logo_photo = tk.PhotoImage(file=logo_path)
                    # Subsample to make it smaller (roughly equivalent to 200x70)
                    scale_factor = max(1, self.logo_photo.width() // 200)
                    self.logo_photo = self.logo_photo.subsample(scale_factor, scale_factor)
                    logo_label = tk.Label(support_frame, image=self.logo_photo, bg="#1e1e1e", cursor="hand2")
                    logo_label.grid(row=0, column=0, sticky="s", padx=(0, 15), pady=(15, 0))
                    
                    # Make logo clickable to open GitHub
                    def open_github(event=None):
                        webbrowser.open("https://github.com/Viper-Dude/EliteMining")
                    logo_label.bind("<Button-1>", open_github)
                else:
                    # Show text fallback if file doesn't exist - also make it clickable
                    logo_text = tk.Label(support_frame, text="EliteMining", font=("Segoe UI", 12, "bold"), fg="#cccccc", bg="#1e1e1e", cursor="hand2")
                    logo_text.grid(row=0, column=0, sticky="s", padx=(0, 15), pady=(15, 0))
                    
                    def open_github(event=None):
                        webbrowser.open("https://github.com/Viper-Dude/EliteMining")
                    logo_text.bind("<Button-1>", open_github)
        except Exception as e:
            # Show text fallback if loading failed - also make it clickable
            logo_text = tk.Label(support_frame, text="EliteMining", font=("Segoe UI", 12, "bold"), fg="#cccccc", bg="#1e1e1e", cursor="hand2")
            logo_text.grid(row=0, column=0, sticky="sw", padx=(0, 25), pady=(0, 0))
            
            def open_github(event=None):
                webbrowser.open("https://github.com/Viper-Dude/EliteMining")
            logo_text.bind("<Button-1>", open_github)
        
        # Support text in the center - aligned to bottom
        support_text = tk.Label(
            support_frame,
            text="This software is totally free, but if you want to support the\ndeveloper and future updates, your contribution would be greatly appreciated.",
            wraplength=300,
            justify="left",
            fg="#cccccc",
            bg="#1e1e1e",
            font=("Segoe UI", 7, "italic"),
        )
        support_text.grid(row=0, column=1, sticky="s", padx=(10, 5), pady=(15, 0))

        # --- PayPal donate button on the right ---
        import webbrowser
        try:
            paypal_img = tk.PhotoImage(file=os.path.join(get_app_data_dir(), "Images", "paypal.png"))
            if paypal_img.width() > 50:
                scale = max(1, paypal_img.width() // 50)
                paypal_img = paypal_img.subsample(scale, scale)
            btn = tk.Label(support_frame, image=paypal_img, cursor="hand2", bg="#1e1e1e")
            btn.image = paypal_img
            btn.grid(row=0, column=2, sticky="s", padx=(10, 8), pady=(15, 0))
            def open_paypal(event=None):
                webbrowser.open("https://www.paypal.com/donate/?hosted_button_id=NZQTA4TGPDSC6")
            btn.bind("<Button-1>", open_paypal)
        except Exception as e:
            print("PayPal widget failed:", e)

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
        self.settings_notebook.add(announcements_tab, text="Announcements")

        # === GENERAL SETTINGS SUB-TAB ===
        general_tab = ttk.Frame(self.settings_notebook, padding=8)
        self._build_interface_options_tab(general_tab)
        self.settings_notebook.add(general_tab, text="General Settings")

    def _build_voiceattack_controls_tab(self, frame: ttk.Frame) -> None:
        """Build the VoiceAttack Controls tab with Firegroups and Mining Controls"""
        # Create a notebook for VoiceAttack sub-tabs
        self.voiceattack_notebook = ttk.Notebook(frame)
        self.voiceattack_notebook.pack(fill="both", expand=True)

        # === FIREGROUPS & FIRE BUTTONS SUB-TAB ===
        firegroups_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_fg_tab(firegroups_tab)
        self.voiceattack_notebook.add(firegroups_tab, text="Firegroups & Fire Buttons")

        # === MINING CONTROLS SUB-TAB ===
        mining_controls_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_timers_tab(mining_controls_tab)
        self.voiceattack_notebook.add(mining_controls_tab, text="Mining Controls")

    def _build_announcements_tab(self, frame: ttk.Frame) -> None:
        """Build the Announcements settings tab with full material functionality"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(2, weight=1)

        # Basic announcement controls
        ttk.Label(frame, text="Announcement Settings", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        # Check if prospector panel is available for advanced controls
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            # Import materials for full functionality
            try:
                from prospector_panel import ANNOUNCEMENT_TOGGLES, KNOWN_MATERIALS, CORE_ONLY
                
                # Main controls frame
                main_controls = ttk.Frame(frame)
                main_controls.grid(row=1, column=0, sticky="ew", pady=(0, 10))
                frame.columnconfigure(0, weight=1)
                
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
                            ToolTip(checkbox, helptext)
                
                # Right side: Threshold controls
                thr = ttk.Frame(main_controls)
                thr.pack(side="left")
                ttk.Label(thr, text="Announce at ≥").pack(side="left")
                sp = ttk.Spinbox(thr, from_=0.0, to=100.0, increment=0.5, width=6,
                                 textvariable=self.prospector_panel.threshold, 
                                 command=self.prospector_panel._save_threshold_value)
                sp.pack(side="left", padx=(6, 4))
                ToolTip(sp, "Set the minimum percentage threshold for announcements")
                
                set_all_btn = tk.Button(thr, text="Set all", command=self._ann_set_all_threshold,
                                       bg="#2a4a5a", fg="#ffffff", 
                                       activebackground="#3a5a6a", activeforeground="#ffffff",
                                       relief="solid", bd=1, cursor="hand2", pady=2, padx=8)
                set_all_btn.pack(side="left", padx=(10, 0))
                ToolTip(set_all_btn, "Set all materials to the minimum threshold percentage")
                ttk.Label(thr, text="%").pack(side="left")

                # Materials section label
                ttk.Label(frame, text="Select minerals and set minimum percentages:",
                          font=("Segoe UI", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(8, 4))

                # Create the full material tree with functionality
                materials_frame = ttk.Frame(frame)
                materials_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
                materials_frame.columnconfigure(0, weight=1)
                materials_frame.rowconfigure(0, weight=1)
                frame.rowconfigure(3, weight=1)

                # Material tree
                self.ann_mat_tree = ttk.Treeview(materials_frame, columns=("announce", "material", "minpct"), show="headings", height=14)
                self.ann_mat_tree.heading("announce", text="Announce")
                self.ann_mat_tree.heading("material", text="Mineral")
                self.ann_mat_tree.heading("minpct", text="Minimal %")
                self.ann_mat_tree.column("announce", width=90, anchor="center", stretch=False)
                self.ann_mat_tree.column("material", width=300, anchor="center", stretch=True)
                self.ann_mat_tree.column("minpct", width=100, anchor="center", stretch=False)
                self.ann_mat_tree.grid(row=0, column=0, sticky="nsew")
                
                ann_scrollbar = ttk.Scrollbar(materials_frame, orient="vertical", command=self.ann_mat_tree.yview)
                ann_scrollbar.grid(row=0, column=1, sticky="ns")
                self.ann_mat_tree.configure(yscrollcommand=ann_scrollbar.set)

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
                for mat in KNOWN_MATERIALS:
                    flag = "✓" if self.prospector_panel.announce_map.get(mat, True) else "—"
                    if mat in CORE_ONLY:
                        self.ann_mat_tree.insert("", "end", iid=mat, values=(flag, mat, ""))
                    else:
                        self.ann_mat_tree.insert("", "end", iid=mat, values=(flag, mat, ""))
                        
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
                
                select_all_btn = tk.Button(btns, text="Select all", command=self._ann_select_all,
                                          bg="#2a5a2a", fg="#ffffff", 
                                          activebackground="#3a6a3a", activeforeground="#ffffff",
                                          relief="solid", bd=1, cursor="hand2", pady=3)
                select_all_btn.pack(side="left")
                ToolTip(select_all_btn, "Enable announcements for all materials")
                
                unselect_all_btn = tk.Button(btns, text="Unselect all", command=self._ann_unselect_all,
                                           bg="#5a2a2a", fg="#ffffff", 
                                           activebackground="#6a3a3a", activeforeground="#ffffff",
                                           relief="solid", bd=1, cursor="hand2", pady=3)
                unselect_all_btn.pack(side="left", padx=(6, 0))
                ToolTip(unselect_all_btn, "Disable announcements for all materials")
                
                # Add preset buttons
                for i in range(1, 6):  # Preset 1 to 5
                    preset_btn = tk.Button(btns, text=f"Preset {i}",
                                         bg="#4a4a2a", fg="#ffffff",
                                         activebackground="#5a5a3a", activeforeground="#ffffff",
                                         relief="solid", bd=1,
                                         width=8, font=("Segoe UI", 9), cursor="hand2", pady=3,
                                         highlightbackground="#2a2a1a", highlightcolor="#2a2a1a")
                    preset_btn.pack(side="left", padx=(8, 0))
                    
                    # Bind left and right click events
                    if i == 1:
                        preset_btn.bind("<Button-1>", lambda e: self._ann_load_preset1())
                        preset_btn.bind("<Button-3>", lambda e: self._ann_save_preset1())
                    else:
                        preset_btn.bind("<Button-1>", lambda e, num=i: self._ann_load_preset(num))
                        preset_btn.bind("<Button-3>", lambda e, num=i: self._ann_save_preset(num))
                    
                    # Fix button state after right-click
                    preset_btn.bind("<ButtonRelease-3>", lambda e: e.widget.config(relief="raised"))
                    
                    # Add tooltip
                    tooltip_text = ("Left-click = Load saved preset\n"
                                  "Right-click = Save current settings into that preset slot\n"
                                  f"Use Preset {i} to store different announcement profiles\n"
                                  "(e.g. Core-only, High-value, All materials)")
                    ToolTip(preset_btn, tooltip_text)
                
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
                    from tkinter import messagebox
                    messagebox.showinfo("Load Preset 1", "No Preset 1 saved yet.")
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
                    from tkinter import messagebox
                    messagebox.showinfo(f"Load Preset {num}", f"No Preset {num} saved yet.")
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

    def _build_interface_options_tab(self, frame: ttk.Frame) -> None:
        # Create a canvas and scrollbar for scrollable content
        canvas = tk.Canvas(frame, bg="#1e1e1e", highlightthickness=0)
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
        ttk.Label(scrollable_frame, text="Interface Options", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 10))
        r = 1
        
        # ========== GENERAL INTERFACE SECTION ==========
        ttk.Label(scrollable_frame, text="General Interface", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator1 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator1.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Tooltips option
        tk.Checkbutton(scrollable_frame, text="Enable Tooltips", variable=self.tooltips_enabled, 
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Show helpful tooltips when hovering over buttons and controls", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Stay on top option
        tk.Checkbutton(scrollable_frame, text="Stay on Top", variable=self.stay_on_top, 
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Keep application window always on top of other windows", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== EDDN SECTION ==========
        ttk.Label(scrollable_frame, text="EDDN", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator
        separator_eddn = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_eddn.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # EDDN send enable/disable
        tk.Checkbutton(scrollable_frame, text="✓ Send Event Information to EDDN", variable=self.eddn_send_enabled, 
                      command=self._on_eddn_send_toggle,
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Share market data with the Elite Dangerous community via EDDN (Elite Dangerous Data Network)", 
                 wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== TEXT OVERLAY DISPLAY SECTION ==========
        ttk.Label(scrollable_frame, text="Text Overlay Display", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator2 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator2.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Text overlay enable/disable
        tk.Checkbutton(scrollable_frame, text="Enable Text Overlay", variable=self.text_overlay_enabled, 
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Announcements text overlay (same text that goes to TTS)", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 8))
        r += 1
        
        # Text brightness slider
        transparency_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        transparency_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(transparency_frame, text="Text Brightness:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        self.transparency_scale = tk.Scale(transparency_frame, from_=10, to=100, orient="horizontal", 
                                         variable=self.text_overlay_transparency, bg="#1e1e1e", fg="#ffffff", 
                                         activebackground="#444444", highlightthickness=0, length=120,
                                         troughcolor="#444444", font=("Segoe UI", 8))
        self.transparency_scale.pack(side="left", padx=(8, 0))
        tk.Label(transparency_frame, text="%", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        r += 1
        tk.Label(scrollable_frame, text="Adjust text brightness/opacity", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Text color selection with actual colors shown
        color_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        color_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(color_frame, text="Text Color:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Create custom OptionMenu with colored options
        self.color_menu = tk.OptionMenu(color_frame, self.text_overlay_color, *self.color_options.keys())
        self.color_menu.configure(
            bg="#1e1e1e", 
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
        
        # Clear existing items and add colored ones
        menu.delete(0, 'end')
        for color_name, color_hex in self.color_options.items():
            # For very light colors, use black text for readability
            text_color = "#000000" if color_name in ["White", "Yellow", "Light Gray", "Light Green", "Light Blue", "Cyan"] else "#000000"
            menu.add_command(
                label=color_name,
                command=lambda value=color_name: self.text_overlay_color.set(value),
                background=color_hex,
                foreground=text_color,
                activebackground=color_hex,
                activeforeground=text_color,
                font=("Segoe UI", 9, "bold")
            )
        r += 1
        tk.Label(scrollable_frame, text="Choose text color ", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Text size selection
        size_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        size_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(size_frame, text="Text Size:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        self.size_combo = ttk.Combobox(size_frame, textvariable=self.text_overlay_size, 
                                      values=list(self.size_options.keys()), 
                                      state="readonly", width=12, font=("Segoe UI", 8))
        self.size_combo.pack(side="left", padx=(8, 0))
        r += 1
        tk.Label(scrollable_frame, text="Choose text size for better readability", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Display duration slider
        duration_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        duration_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(duration_frame, text="Display Duration:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        self.duration_scale = tk.Scale(duration_frame, from_=5, to=30, orient="horizontal", 
                                     variable=self.text_overlay_duration, bg="#1e1e1e", fg="#ffffff", 
                                     activebackground="#444444", highlightthickness=0, length=140,
                                     troughcolor="#444444", font=("Segoe UI", 8))
        self.duration_scale.pack(side="left", padx=(8, 0))
        tk.Label(duration_frame, text="seconds", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        r += 1
        tk.Label(scrollable_frame, text="How long text stays visible on screen (5-30 seconds)", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Position selection
        position_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        position_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(position_frame, text="Position:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        self.position_combo = ttk.Combobox(position_frame, textvariable=self.text_overlay_position, 
                                          values=list(self.position_options.keys()), 
                                          state="readonly", width=12, font=("Segoe UI", 8))
        self.position_combo.pack(side="left", padx=(8, 0))
        r += 1
        tk.Label(scrollable_frame, text="Choose overlay position on screen", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Overlay mode selection (Standard vs Enhanced Prospector)
        mode_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        mode_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(mode_frame, text="Overlay Mode:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Radio buttons for mode selection
        tk.Radiobutton(mode_frame, text="Standard Text", value="standard", variable=self.overlay_mode,
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9),
                      padx=4, pady=2, anchor="w").pack(side="left", padx=(8, 0))
        tk.Radiobutton(mode_frame, text="Enhanced Prospector", value="enhanced", variable=self.overlay_mode,
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9),
                      padx=4, pady=2, anchor="w").pack(side="left", padx=(8, 0))
        r += 1
        tk.Label(scrollable_frame, text="Standard: Simple text (only when announced) | Enhanced: Game-style display (every prospector fire)",
                 wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 6))
        r += 1
        
        # Show all materials checkbox (for enhanced mode) - HIDDEN but functionality preserved
        # tk.Checkbutton(scrollable_frame, text="Enhanced Mode: Show All Materials (uncheck to only show materials above threshold)",
        #               variable=self.prospector_show_all,
        #               bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e",
        #               activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9),
        #               padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e",
        #               highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        # r += 1
        # tk.Label(scrollable_frame, text="Only affects Enhanced mode - controls whether to display all materials or filter by threshold",
        #          wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
        #          font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        # r += 1
        
        # ========== TEXT-TO-SPEECH AUDIO SECTION ==========
        ttk.Label(scrollable_frame, text="Text-to-Speech Audio", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator3 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator3.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # TTS Voice selection (moved from announcements panel)
        tk.Label(scrollable_frame, text="TTS Voice:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w", pady=(4, 4))
        r += 1
        
        voice_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
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
        
        test_btn = tk.Button(voice_frame, text="▶ Test Voice", command=_test_voice_interface,
                            bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                            activeforeground="#ffffff", relief="ridge", bd=1, 
                            font=("Segoe UI", 8, "normal"), cursor="hand2")
        test_btn.pack(side="left", padx=(8, 0))
        
        r += 1
        # Volume control
        vol_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        vol_frame.grid(row=r, column=0, sticky="w", pady=(6, 4))
        
        tk.Label(vol_frame, text="Volume:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
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
                             variable=self.voice_volume, bg="#1e1e1e", fg="#ffffff",
                             activebackground="#444444", highlightthickness=0, 
                             troughcolor="#444444", font=("Segoe UI", 8),
                             command=_on_volume_change, length=200)
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
        ToolTip(fix_tts_btn, "Reinitialize Text-to-Speech engine.\nUse this if TTS stops working or after recycling Windows voices.")
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
        tk.Label(scrollable_frame, text="Configure Text-to-Speech voice and volume for announcements", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # ========== JOURNAL FILES SECTION ==========
        ttk.Label(scrollable_frame, text="Journal Files", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator4 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator4.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Journal folder path setting
        journal_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        journal_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(journal_frame, text="Journal folder:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Initialize journal label (will be updated after prospector panel creation)
        self.journal_lbl = tk.Label(journal_frame, text="(not set)", fg="gray", bg="#1e1e1e", font=("Segoe UI", 9))
        self.journal_lbl.pack(side="left", padx=(6, 0))
        
        journal_btn = tk.Button(journal_frame, text="Change…", command=self._change_journal_dir,
                               bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                               activeforeground="#ffffff", relief="ridge", bd=1, 
                               font=("Segoe UI", 8, "normal"), cursor="hand2")
        journal_btn.pack(side="left", padx=(8, 0))
        ToolTip(journal_btn, "Select the Elite Dangerous Journal folder\nUsually located in: Documents\\Frontier Developments\\Elite Dangerous")
        
        import_btn = tk.Button(journal_frame, text="Import History", command=self._import_journal_history,
                              bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                              activeforeground="#ffffff", relief="ridge", bd=1,
                              font=("Segoe UI", 8, "normal"), cursor="hand2")
        import_btn.pack(side="left", padx=(8, 0))
        ToolTip(import_btn, "Import visited systems and hotspots from existing journal files")
        
        r += 1
        tk.Label(scrollable_frame, text="Path to Elite Dangerous journal files for prospector monitoring", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
        # Import prompt preference checkbox
        self.ask_import_on_path_change = tk.IntVar()
        import_prompt_check = tk.Checkbutton(
            scrollable_frame,
            text="Ask to import history when changing journal folder",
            variable=self.ask_import_on_path_change,
            command=self._save_import_prompt_preference,
            bg="#1e1e1e",
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
        tk.Checkbutton(scrollable_frame, text="Auto-scan Journals on Startup", variable=self.auto_scan_journals, 
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Automatically check for new mining data in Elite Dangerous journals when the app starts. Disable if you prefer manual imports via Settings → Import History", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== SCREENSHOTS FOLDER SECTION ==========
        ttk.Label(scrollable_frame, text="Screenshots Folder", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add separator line
        separator_screenshots = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator_screenshots.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Screenshots folder path setting
        screenshots_folder_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        screenshots_folder_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        tk.Label(screenshots_folder_frame, text="Screenshots folder:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(side="left")
        
        # Create StringVar for screenshots folder path
        self.screenshots_folder_path = tk.StringVar()
        self.screenshots_folder_path.set(_load_cfg().get('screenshots_folder', os.path.join(os.path.expanduser("~"), "Pictures")))
        
        # Initialize screenshots folder label (will be updated with actual path)
        self.screenshots_folder_lbl = tk.Label(screenshots_folder_frame, text=self.screenshots_folder_path.get(), fg="gray", bg="#1e1e1e", font=("Segoe UI", 9))
        self.screenshots_folder_lbl.pack(side="left", padx=(6, 0))
        
        screenshots_btn = tk.Button(screenshots_folder_frame, text="Change…", command=self._change_screenshots_folder,
                                  bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                  activeforeground="#ffffff", relief="ridge", bd=1, 
                                  font=("Segoe UI", 8, "normal"), cursor="hand2")
        screenshots_btn.pack(side="left", padx=(8, 0))
        ToolTip(screenshots_btn, "Select the default folder for importing screenshots\nUsually located in: Documents\\Pictures")
        
        r += 1
        tk.Label(scrollable_frame, text="Default folder for selecting screenshots when adding them to reports", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
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
        # instructions_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        # instructions_frame.grid(row=r, column=0, sticky="w", pady=(4, 4))
        # 
        # tk.Label(instructions_frame, text="1. Sign up at EDSM:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(anchor="w")
        # 
        # # EDSM link
        # import webbrowser
        # edsm_link = tk.Label(instructions_frame, text="https://www.edsm.net/", bg="#1e1e1e", fg="#4da6ff", font=("Segoe UI", 9, "underline"), cursor="hand2")
        # edsm_link.pack(anchor="w", padx=(15, 0))
        # edsm_link.bind("<Button-1>", lambda e: webbrowser.open("https://www.edsm.net/"))
        # 
        # tk.Label(instructions_frame, text="2. Log in → Account settings → API key", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        # tk.Label(instructions_frame, text="3. Paste the key here:", bg="#1e1e1e", fg="#ffffff", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        # 
        # r += 1
        # 
        # # EDSM API key input
        # api_key_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
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
        #          wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
        #          font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        # r += 1

        # ========== BACKUP & RESTORE SECTION ==========
        r += 1
        ttk.Label(scrollable_frame, text="Backup & Restore", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator6 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator6.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Backup and Restore buttons frame
        backup_frame = tk.Frame(scrollable_frame, bg="#1e1e1e")
        backup_frame.grid(row=r, column=0, sticky="w", pady=(4, 0))
        
        backup_btn = tk.Button(backup_frame, text="📦 Backup", command=self._show_backup_dialog,
                              bg="#2a3a4a", fg="#e0e0e0", 
                              activebackground="#3a4a5a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=12, pady=4,
                              font=("Segoe UI", 9, "normal"), cursor="hand2")
        backup_btn.pack(side="left", padx=(0, 8))
        ToolTip(backup_btn, "Create backup of Ship Presets, Reports, Bookmarks, and VoiceAttack Profile\nBackup is saved as a timestamped zip file")
        
        restore_btn = tk.Button(backup_frame, text="📂 Restore", command=self._show_restore_dialog,
                               bg="#4a3a2a", fg="#e0e0e0", 
                               activebackground="#5a4a3a", activeforeground="#ffffff",
                               relief="ridge", bd=1, padx=12, pady=4,
                               font=("Segoe UI", 9, "normal"), cursor="hand2")
        restore_btn.pack(side="left")
        ToolTip(restore_btn, "Restore from backup zip file\nSelect which data to restore and handle conflicts")
        
        r += 1
        tk.Label(scrollable_frame, text="Backup and restore ship presets, reports, and bookmarks", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # ========== UPDATES SECTION ==========
        ttk.Label(scrollable_frame, text="Updates", font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="w", pady=(5, 8))
        r += 1
        
        # Add a subtle separator line
        separator5 = tk.Frame(scrollable_frame, height=1, bg="#444444")
        separator5.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        r += 1
        
        # Check for updates button
        update_btn = tk.Button(scrollable_frame, text="Check for Updates", command=self._manual_update_check,
                              bg="#2a4a2a", fg="#e0e0e0", 
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=12, pady=4,
                              font=("Segoe UI", 9, "normal"), cursor="hand2")
        update_btn.grid(row=r, column=0, sticky="w", pady=(4, 0))
        r += 1
        tk.Label(scrollable_frame, text="Check GitHub for newer versions of EliteMining", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1



    def _create_main_sidebar(self) -> None:
        """Create the main Ship Presets and Cargo Monitor sidebar"""
        # Create the sidebar frame
        sidebar = ttk.Frame(self, padding=(6, 6, 10, 6))
        sidebar.grid(row=0, column=1, sticky="nsew")
        sidebar.columnconfigure(0, weight=1)
        sidebar.rowconfigure(0, weight=1)

        # Create vertical paned window for split layout
        paned_window = ttk.PanedWindow(sidebar, orient="vertical")
        paned_window.grid(row=0, column=0, sticky="nsew")
        
        # Top pane - Presets section
        presets_pane = ttk.Frame(paned_window)
        paned_window.add(presets_pane, weight=5)
        presets_pane.columnconfigure(0, weight=1)
        presets_pane.rowconfigure(2, weight=1)  # Row 2 will be the preset list

        # Ship Presets title
        presets_title = ttk.Label(presets_pane, text="⚙️ Ship Presets", font=("Segoe UI", 11, "bold"))
        presets_title.grid(row=0, column=0, sticky="w", pady=(0, 2))
        
        # Help text for preset operations
        help_text = ttk.Label(presets_pane, text="Right click preset for options", 
                             font=("Segoe UI", 8), foreground="#666666")
        help_text.grid(row=1, column=0, sticky="w", pady=(0, 6))
        
        # Scrollable preset list
        self.preset_list = ttk.Treeview(presets_pane, columns=("name",), show="headings", selectmode="browse")
        self.preset_list.heading("name", text="Configuration Presets", anchor="w")
        self.preset_list.column("name", anchor="w", stretch=True, width=400, minwidth=350)
        self.preset_list.grid(row=2, column=0, sticky="nsew")
        self.preset_list.bind("<Double-1>", lambda e: self._load_selected_preset())
        self.preset_list.bind("<Return>", lambda e: self._load_selected_preset())

        # Add scrollbar to preset list
        preset_scrollbar = ttk.Scrollbar(presets_pane, orient="vertical", command=self.preset_list.yview)
        preset_scrollbar.grid(row=2, column=1, sticky="ns")
        self.preset_list.configure(yscrollcommand=preset_scrollbar.set)
        presets_pane.columnconfigure(1, weight=0)

        # Context menu with dark theme
        self._preset_menu = tk.Menu(self, tearoff=0, 
                                  bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"], 
                                  activebackground=MENU_COLORS["activebackground"], 
                                  activeforeground=MENU_COLORS["activeforeground"],
                                  selectcolor=MENU_COLORS["selectcolor"])
        self._preset_menu.add_command(label="Save as New", command=self._save_as_new)
        self._preset_menu.add_command(label="Overwrite", command=self._overwrite_selected)
        self._preset_menu.add_command(label="Duplicate", command=self._duplicate_selected_preset)
        self._preset_menu.add_command(label="Rename", command=self._rename_selected_preset)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label="Export…", command=self._export_selected_preset)
        self._preset_menu.add_command(label="Import…", command=self._import_preset_file)
        self._preset_menu.add_separator()
        self._preset_menu.add_command(label="Delete", command=self._delete_selected)
        self.preset_list.bind("<Button-3>", self._show_preset_menu)

        # Bottom pane - Cargo Monitor
        cargo_pane = ttk.Frame(paned_window)
        paned_window.add(cargo_pane, weight=5)
        self._create_integrated_cargo_monitor(cargo_pane)

        # Refresh the preset list
        self._refresh_preset_list()
        
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
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(100, weight=1)  # Allow bottom content to expand
        
        # DEBUG: Print TIMERS order
        print("DEBUG: TIMERS keys order:", list(TIMERS.keys()))
        print("DEBUG: timer_vars keys order:", list(self.timer_vars.keys()))
        
        # Timers section
        ttk.Label(frame, text="Timers", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        r = 1
        for name, spec in TIMERS.items():
            _fname, lo, hi, helptext = spec
            rowf = ttk.Frame(frame)
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            # Spinbox first
            sp = ttk.Spinbox(rowf, from_=lo, to=hi, width=5, textvariable=self.timer_vars[name])
            sp.pack(side="left")
            
            # Label second with tooltip
            label = ttk.Label(rowf, text=f"{name} [{lo}..{hi}] seconds")
            label.pack(side="left", padx=(6, 0))
            
            # Add tooltip with the help text
            ToolTip(label, helptext)
            
            r += 1
        
        # Add some spacing between sections
        ttk.Separator(frame, orient='horizontal').grid(row=r, column=0, sticky="ew", pady=(20, 10))
        r += 1
        
        # Toggles section
        ttk.Label(frame, text="Toggles", font=("Segoe UI", 11, "bold")).grid(row=r, column=0, sticky="w")
        r += 1
        
        for name, (_fname, helptext) in TOGGLES.items():
            checkbox = tk.Checkbutton(frame, text=f"Enable {name}", variable=self.toggle_vars[name], 
                                    bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", 
                                    activebackground="#1e1e1e", activeforeground="#ffffff", 
                                    highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.grid(row=r, column=0, sticky="w")
            
            # Add tooltip to checkbox
            ToolTip(checkbox, helptext)
            r += 1
        
        # Add logo at bottom right
        r += 1
        logo_frame = tk.Frame(frame, bg="#1e1e1e")
        logo_frame.grid(row=r, column=0, sticky="se", pady=(40, 5), padx=(0, 10))
        
        import sys
        
        # Use consistent path detection like config.py
        if getattr(sys, 'frozen', False):
            # Running as compiled executable - images are in app folder
            exe_dir = os.path.dirname(sys.executable)
            parent_dir = os.path.dirname(exe_dir)
            logo_path = os.path.join(parent_dir, 'app', 'Images', 'EliteMining_txt_logo_transp_resize.png')
        else:
            # Running in development mode
            logo_path = os.path.join(os.path.dirname(__file__), 'Images', 'EliteMining_txt_logo_transp_resize.png')
        
        try:
            from PIL import Image, ImageTk
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                # Resize with much smaller height for compact appearance
                img = img.resize((200, 35), Image.Resampling.LANCZOS)
                self.timers_logo_photo = ImageTk.PhotoImage(img)
                logo_label = tk.Label(logo_frame, image=self.timers_logo_photo, bg="#1e1e1e", cursor="hand2")
                logo_label.pack()
                
                # Make logo clickable to open GitHub
                def open_github(event=None):
                    import webbrowser
                    webbrowser.open("https://github.com/Viper-Dude/EliteMining")
                logo_label.bind("<Button-1>", open_github)
        except ImportError:
            # Fallback to tkinter PhotoImage with subsample for resizing
            if os.path.exists(logo_path):
                self.timers_logo_photo = tk.PhotoImage(file=logo_path)
                # Subsample to make it smaller
                self.timers_logo_photo = self.timers_logo_photo.subsample(2, 2)
                logo_label = tk.Label(logo_frame, image=self.timers_logo_photo, bg="#1e1e1e", cursor="hand2")
                logo_label.pack()
                
                def open_github(event=None):
                    import webbrowser
                    webbrowser.open("https://github.com/Viper-Dude/EliteMining")
                logo_label.bind("<Button-1>", open_github)
        except Exception as e:
            # Silently fail if logo can't be loaded
            pass

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
                msg += f"; {len(missing)} missing/invalid"
            self._set_status(msg)
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

    def _refresh_preset_list(self) -> None:
        for item in self.preset_list.get_children():
            self.preset_list.delete(item)
        names = []
        try:
            for fn in os.listdir(self.settings_dir):
                if fn.lower().endswith(".json"):
                    names.append(os.path.splitext(fn)[0])
        except Exception:
            pass
        for n in sorted(names, key=str.casefold):
            self.preset_list.insert("", "end", values=(PRESET_INDENT + n,))

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
            "Toggles": {k: v.get() for k, v in self.toggle_vars.items()},
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
            if k in self.toggle_vars:
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
        dialog.title("Preset Name")
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
                        bg="#2c3e50", fg="#ecf0f1", font=("Arial", 10))
        label.pack(pady=(20, 10))
        
        # Entry
        entry = tk.Entry(dialog, font=("Arial", 10), width=30)
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
            
        ok_btn = tk.Button(btn_frame, text="OK", command=on_ok,
                          bg="#27ae60", fg="white", font=("Arial", 10),
                          width=10)
        ok_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(btn_frame, text="Cancel", command=on_cancel,
                              bg="#e74c3c", fg="white", font=("Arial", 10),
                              width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind Enter/Escape
        dialog.bind('<Return>', lambda e: on_ok())
        dialog.bind('<Escape>', lambda e: on_cancel())
        entry.bind('<Return>', lambda e: on_ok())
        
        entry.focus_set()
        dialog.wait_window()
        return result if result else None

    def _get_selected_preset(self) -> Optional[str]:
        sel = self.preset_list.selection()
        if not sel:
            return None
        item_id = sel[0]
        raw = self.preset_list.item(item_id, "values")[0]
        return raw.strip()

    def _save_as_new(self) -> None:
        name = self._ask_preset_name()
        if not name:
            return
        path = self._settings_path(name)
        if os.path.exists(path):
            messagebox.showerror("Name exists", f"A preset named '{name}' already exists.")
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._current_mapping(), f, indent=2)
        self._refresh_preset_list()
        self._set_status(f"Saved new preset '{name}'.")

    def _overwrite_selected(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            messagebox.showinfo("No preset selected", "Choose a preset to overwrite.")
            return
        
        # Confirm overwrite
        if not messagebox.askyesno("Confirm Overwrite", 
                                  f"This will overwrite preset '{sel}' with current settings.\n\n"
                                  f"This action cannot be undone.\n\n"
                                  f"Continue?"):
            return
            
        with open(self._settings_path(sel), "w", encoding="utf-8") as f:
            json.dump(self._current_mapping(), f, indent=2)
        self._set_status(f"Overwrote preset '{sel}'.")

    def _rename_selected_preset(self) -> None:
        old = self._get_selected_preset()
        if not old:
            messagebox.showinfo("No preset selected", "Choose a preset to rename.")
            return
            
        # Confirm rename action
        if not messagebox.askyesno("Confirm Rename", 
                                  f"Rename preset '{old}'?\n\n"
                                  f"You'll be asked for the new name next."):
            return
            
        new = self._ask_preset_name(initial=old)
        if not new or new == old:
            return
        old_path = self._settings_path(old)
        new_path = self._settings_path(new)
        if os.path.exists(new_path):
            messagebox.showerror("Rename failed", f"A preset named '{new}' already exists.")
            return
        try:
            os.rename(old_path, new_path)
            self._refresh_preset_list()
            for item in self.preset_list.get_children():
                raw = self.preset_list.item(item, "values")[0].strip()
                if raw == new:
                    self.preset_list.selection_set(item)
                    self.preset_list.see(item)
                    self.preset_list.item(item, values=(PRESET_INDENT + new,))
                    break
            self._set_status(f"Renamed preset to '{new}'.")
        except Exception as e:
            messagebox.showerror("Rename failed", str(e))

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
        if messagebox.askyesno("Delete preset", f"Delete preset '{sel}'?"):
            try:
                os.remove(self._settings_path(sel))
                self._refresh_preset_list()
                self._set_status(f"Deleted preset '{sel}'.")
            except Exception as e:
                messagebox.showerror("Delete failed", str(e))

    def _duplicate_selected_preset(self) -> None:
        """Duplicate the selected preset with a new name"""
        sel = self._get_selected_preset()
        if not sel:
            return
        
        # Ask for new name, suggesting a default
        new_name = self._ask_preset_name(f"{sel} - Copy")
        if not new_name:
            return
            
        new_path = self._settings_path(new_name)
        if os.path.exists(new_path):
            messagebox.showerror("Name exists", f"A preset named '{new_name}' already exists.")
            return
            
        try:
            # Load the existing preset data
            with open(self._settings_path(sel), "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Save it with the new name
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
                
            self._refresh_preset_list()
            self._set_status(f"Duplicated preset '{sel}' as '{new_name}'.")
        except Exception as e:
            messagebox.showerror("Duplicate failed", str(e))

    def _export_selected_preset(self) -> None:
        sel = self._get_selected_preset()
        if not sel:
            messagebox.showinfo("No preset selected", "Choose a preset to export.")
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
        path = filedialog.askopenfilename(
            title="Import preset (.json)",
            filetypes=[("JSON preset", "*.json"), ("All files", "*.*")],
            initialdir=self.settings_dir
        )
        if not path:
            return
            
        base = os.path.basename(path)
        name = os.path.splitext(base)[0]
        dest = os.path.join(self.settings_dir, base)
        
        # Check if preset already exists
        if os.path.exists(dest):
            if not messagebox.askyesno("Preset Exists", 
                                      f"A preset named '{name}' already exists.\n\n"
                                      f"Do you want to overwrite it?"):
                return
        
        try:
            shutil.copy2(path, dest)
            self._refresh_preset_list()
            self._set_status(f"Imported preset '{name}'. Double-click to load.")
        except Exception as e:
            messagebox.showerror("Import preset failed", str(e))

    def _show_preset_menu(self, event) -> None:
        try:
            item = self.preset_list.identify_row(event.y)
            if item:
                self.preset_list.selection_set(item)
                self.preset_list.focus(item)
            self._preset_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._preset_menu.grab_release()

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
            print(f"✅ {status_msg}")
    
    def _on_journal_file_change(self, file_path: str):
        """Called when a file in journal directory changes"""
        file_name = os.path.basename(file_path).lower()
        
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
                        # Process last few events
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
            progress.title("Importing Journal History")
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
                messagebox.showinfo(
                    "Import Complete", 
                    f"Successfully imported:\n"
                    f"• {stats['systems_visited']} visited systems\n"
                    f"• {stats['hotspots_found']} hotspots\n"
                    f"• Processed {stats['files_processed']} journal files"
                )
            
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
        dialog.title("Import Journal History?")
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
        position = cfg.get("text_overlay_position", "Upper Right")  # Default to upper right
        size = cfg.get("text_overlay_size", "Normal")  # Default to normal size
        duration = cfg.get("text_overlay_duration", 7)  # Default to 7 seconds
        overlay_mode = cfg.get("overlay_mode", "standard")  # Default to standard mode
        show_all = cfg.get("prospector_show_all", False)  # Default to threshold only
        
        self.text_overlay_enabled.set(1 if enabled else 0)
        self.text_overlay_transparency.set(transparency)
        self.text_overlay_color.set(color)
        self.text_overlay_position.set(position)
        self.text_overlay_size.set(size)
        self.text_overlay_duration.set(duration)
        self.overlay_mode.set(overlay_mode)
        self.prospector_show_all.set(1 if show_all else 0)
        
        self.text_overlay.set_enabled(enabled)
        self.text_overlay.set_transparency(transparency)
        # Set color after transparency to ensure proper brightness calculation
        color_hex = self.color_options.get(color, "#FFFFFF")
        self.text_overlay.set_color(color_hex)
        # Set position
        position_value = self.position_options.get(position, "upper_right")
        self.text_overlay.set_position(position_value)
        # Set font size
        size_value = self.size_options.get(size, 14)
        self.text_overlay.set_font_size(size_value)
        # Set display duration
        self.text_overlay.set_display_duration(duration)

    def _save_text_overlay_preference(self) -> None:
        """Save text overlay enabled state, transparency, color, and position to config"""
        from config import update_config_values
        updates = {
            "text_overlay_enabled": bool(self.text_overlay_enabled.get()),
            "text_overlay_transparency": int(self.text_overlay_transparency.get()),
            "text_overlay_color": str(self.text_overlay_color.get()),
            "text_overlay_position": str(self.text_overlay_position.get()),
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

    def _on_position_change(self, *args) -> None:
        """Called when position selection is changed"""
        position_name = self.text_overlay_position.get()
        position_value = self.position_options.get(position_name, "upper_right")
        self.text_overlay.set_position(position_value)
        self._save_text_overlay_preference()
        
        # Show a preview message if overlay is enabled to test position
        if self.text_overlay.overlay_enabled:
            self.text_overlay.show_message(f"Position: {position_name}")

    def _on_size_change(self, *args) -> None:
        """Called when text size selection is changed"""
        size_name = self.text_overlay_size.get()
        size_value = self.size_options.get(size_name, 14)
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
        
        if geom:
            try:
                # Parse geometry string: WIDTHxHEIGHT+X+Y
                import re
                match = re.match(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', geom)
                if match:
                    width, height, x, y = map(int, match.groups())
                    
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
                
                self.geometry(geom)
            except Exception as e:
                # If saved geometry fails, center on screen with default size
                self.geometry("1100x650")
                self.update_idletasks()
                screen_width = self.winfo_screenwidth()
                screen_height = self.winfo_screenheight()
                x = (screen_width - 1100) // 2
                y = (screen_height - 650) // 2
                self.geometry(f"1100x650+{x}+{y}")
        else:
            # No saved geometry, center on screen with default size
            self.geometry("1100x650")
            self.update_idletasks()
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = (screen_width - 1100) // 2
            y = (screen_height - 650) // 2
            self.geometry(f"1100x650+{x}+{y}")
        
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
                
            log.info(f"=== CONFIG MIGRATION CHECK END === {datetime.now().isoformat()}")
                
        except Exception as e:
            log.error(f"Config migration check failed: {e}", exc_info=True)
            # Continue startup even if migration fails

    def _on_close(self) -> None:
        # Check if mining session is active
        if hasattr(self, 'prospector_panel') and self.prospector_panel.session_active:
            from tkinter import messagebox
            result = messagebox.askyesnocancel(
                "Mining Session Active",
                "A mining session is currently running.\n\n"
                "• Yes = Stop session and save data\n"
                "• No = Cancel session (lose data)\n" 
                "• Cancel = Keep session running",
                icon="warning"
            )
            
            if result is True:  # Yes - Stop and save
                self.prospector_panel._session_stop()
            elif result is False:  # No - Cancel session
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
            dialog.title("Create Backup")
            dialog.geometry("450x480")
            dialog.resizable(False, False)
            dialog.configure(bg="#2c3e50")
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
            title_label = tk.Label(dialog, text="📦 Create Backup", 
                                 font=("Segoe UI", 14, "bold"),
                                 bg="#2c3e50", fg="#ecf0f1")
            title_label.pack(pady=15)
            
            # Instructions
            inst_label = tk.Label(dialog, text="Select what to include in the backup:",
                                font=("Segoe UI", 10),
                                bg="#2c3e50", fg="#bdc3c7")
            inst_label.pack(pady=(0, 20))
            
            # Backup options frame
            options_frame = tk.Frame(dialog, bg="#2c3e50")
            options_frame.pack(pady=10)
            
            # Backup option variables
            backup_presets = tk.IntVar(value=1)
            backup_reports = tk.IntVar(value=1)
            backup_bookmarks = tk.IntVar(value=1)
            backup_va_profile = tk.IntVar(value=1)
            backup_userdb = tk.IntVar(value=0)
            backup_journals = tk.IntVar(value=0)
            backup_all = tk.IntVar(value=0)
            
            def on_all_change():
                if backup_all.get():
                    backup_presets.set(1)
                    backup_reports.set(1)
                    backup_bookmarks.set(1)
                    backup_va_profile.set(1)
                    backup_userdb.set(1)
                    backup_journals.set(1)
                    # Disable individual checkboxes
                    presets_cb.config(state="disabled")
                    reports_cb.config(state="disabled")
                    bookmarks_cb.config(state="disabled")
                    va_profile_cb.config(state="disabled")
                    userdb_cb.config(state="disabled")
                    journals_cb.config(state="disabled")
                else:
                    # Enable individual checkboxes
                    presets_cb.config(state="normal")
                    reports_cb.config(state="normal")
                    bookmarks_cb.config(state="normal")
                    va_profile_cb.config(state="normal")
                    userdb_cb.config(state="normal")
                    journals_cb.config(state="normal")
            
            # All checkbox
            all_cb = tk.Checkbutton(options_frame, text="📂 Backup Everything",
                                  variable=backup_all,
                                  command=on_all_change,
                                  bg="#2c3e50", fg="#ecf0f1",
                                  selectcolor="#34495e",
                                  activebackground="#34495e",
                                  activeforeground="#ecf0f1",
                                  font=("Segoe UI", 10, "bold"))
            all_cb.pack(anchor="w", pady=5)
            
            # Separator
            sep = tk.Frame(options_frame, height=1, bg="#7f8c8d")
            sep.pack(fill="x", pady=10)
            
            # Individual checkboxes
            presets_cb = tk.Checkbutton(options_frame, text="⚙️ Ship Presets",
                                      variable=backup_presets,
                                      bg="#2c3e50", fg="#ecf0f1",
                                      selectcolor="#34495e",
                                      activebackground="#34495e",
                                      activeforeground="#ecf0f1",
                                      font=("Segoe UI", 10))
            presets_cb.pack(anchor="w", pady=2)
            
            reports_cb = tk.Checkbutton(options_frame, text="📊 Mining Reports",
                                      variable=backup_reports,
                                      bg="#2c3e50", fg="#ecf0f1",
                                      selectcolor="#34495e",
                                      activebackground="#34495e",
                                      activeforeground="#ecf0f1",
                                      font=("Segoe UI", 10))
            reports_cb.pack(anchor="w", pady=2)
            
            bookmarks_cb = tk.Checkbutton(options_frame, text="🔖 Mining Bookmarks",
                                        variable=backup_bookmarks,
                                        bg="#2c3e50", fg="#ecf0f1",
                                        selectcolor="#34495e",
                                        activebackground="#34495e",
                                        activeforeground="#ecf0f1",
                                        font=("Segoe UI", 10))
            bookmarks_cb.pack(anchor="w", pady=2)
            
            va_profile_cb = tk.Checkbutton(options_frame, text="🎤 VoiceAttack Profile",
                                         variable=backup_va_profile,
                                         bg="#2c3e50", fg="#ecf0f1",
                                         selectcolor="#34495e",
                                         activebackground="#34495e",
                                         activeforeground="#ecf0f1",
                                         font=("Segoe UI", 10))
            va_profile_cb.pack(anchor="w", pady=2)
            
            userdb_cb = tk.Checkbutton(options_frame, text="💾 User Database (Hotspots)",
                                       variable=backup_userdb,
                                       bg="#2c3e50", fg="#ecf0f1",
                                       selectcolor="#34495e",
                                       activebackground="#34495e",
                                       activeforeground="#ecf0f1",
                                       font=("Segoe UI", 10))
            userdb_cb.pack(anchor="w", pady=2)
            
            journals_cb = tk.Checkbutton(options_frame, text="📝 Journal Files",
                                        variable=backup_journals,
                                        bg="#2c3e50", fg="#ecf0f1",
                                        selectcolor="#34495e",
                                        activebackground="#34495e",
                                        activeforeground="#ecf0f1",
                                        font=("Segoe UI", 10))
            journals_cb.pack(anchor="w", pady=2)
            
            # Buttons frame
            btn_frame = tk.Frame(dialog, bg="#2c3e50")
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
                    messagebox.showwarning("No Selection", "Please select at least one item to backup.")
                    return
                
                dialog.destroy()
                self._create_backup(include_presets, include_reports, include_bookmarks, include_va_profile, include_userdb, include_journals)
            
            def on_cancel():
                dialog.destroy()
            
            create_btn = tk.Button(btn_frame, text="✅ Create Backup", command=on_create_backup,
                                 bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
                                 width=15, cursor="hand2")
            create_btn.pack(side=tk.LEFT, padx=5)
            
            cancel_btn = tk.Button(btn_frame, text="❌ Cancel", command=on_cancel,
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
                title="Save Backup As",
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
                                if file_name.endswith(('.csv', '.txt', '.json')):
                                    file_path = os.path.join(root, file_name)
                                    rel_path = os.path.relpath(file_path, os.path.dirname(reports_root))
                                    zipf.write(file_path, rel_path)
                                    report_count += 1
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
                    # VoiceAttack profile is in the installer dir at \Apps\EliteMining\
                    if getattr(sys, 'frozen', False):
                        # Running as executable - profile is in the same directory as the executable
                        exe_dir = os.path.dirname(sys.executable)
                        va_profile_path = os.path.join(exe_dir, "EliteMining-Profile.vap")
                        
                        # Also check if we're in the Configurator subdirectory (installed version)
                        if not os.path.exists(va_profile_path):
                            # Check parent directory (Apps\EliteMining\)
                            parent_dir = os.path.dirname(exe_dir)
                            va_profile_path = os.path.join(parent_dir, "EliteMining-Profile.vap")
                            
                            # If still not found, check if we're in VoiceAttack\Apps\EliteMining\Configurator\
                            # and need to go up to VoiceAttack\Apps\EliteMining\
                            if not os.path.exists(va_profile_path):
                                # Go up one more level from Configurator to Apps\EliteMining
                                grandparent_dir = os.path.dirname(parent_dir)  
                                if os.path.basename(grandparent_dir) == "Apps":
                                    # We're in VoiceAttack\Apps\EliteMining\Configurator
                                    va_profile_path = os.path.join(parent_dir, "EliteMining-Profile.vap")
                    else:
                        # Running in development - profile is in project root
                        va_profile_path = os.path.join(os.path.dirname(app_data_dir), "EliteMining-Profile.vap")
                    
                    if not getattr(sys, 'frozen', False):  # Only show debug in development
                        print(f"DEBUG: Executable location: {sys.executable if getattr(sys, 'frozen', False) else 'Development mode'}")
                        print(f"DEBUG: Looking for VoiceAttack profile at: {va_profile_path}")
                        print(f"DEBUG: Profile exists: {os.path.exists(va_profile_path)}")
                    
                    if os.path.exists(va_profile_path):
                        zipf.write(va_profile_path, "EliteMining-Profile.vap")
                        if not getattr(sys, 'frozen', False):  # Only show debug in development
                            print(f"DEBUG: Successfully added VoiceAttack profile to backup")
                    else:
                        if not getattr(sys, 'frozen', False):  # Only show debug in development
                            print(f"DEBUG: VoiceAttack profile not found at expected location")
                
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
            
            messagebox.showinfo("Backup Complete", 
                              f"Backup created successfully!\n\nLocation: {backup_path}")
            self._set_status(f"Backup created: {os.path.basename(backup_path)}")
            
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Failed to create backup: {str(e)}")

    def _show_restore_dialog(self) -> None:
        """Show restore dialog to select backup file and options"""
        try:
            # Ask for backup file
            backup_path = filedialog.askopenfilename(
                title="Select Backup File",
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
                    has_va_profile = "EliteMining-Profile.vap" in file_list
                    has_userdb = "data/user_data.db" in file_list
                    has_journals = any(f.startswith("Journals/") and f.endswith(".log") for f in file_list)
                    
                    if not (has_presets or has_reports or has_bookmarks or has_va_profile or has_userdb or has_journals):
                        messagebox.showerror("Invalid Backup", "This doesn't appear to be a valid EliteMining backup file.")
                        return
                    
                    self._show_restore_options_dialog(backup_path, has_presets, has_reports, has_bookmarks, has_va_profile, has_userdb, has_journals, manifest)
                    
            except zipfile.BadZipFile:
                messagebox.showerror("Invalid File", "Selected file is not a valid ZIP archive.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to read backup file: {str(e)}")
                
        except Exception as e:
            messagebox.showerror("Restore Dialog Error", f"Failed to show restore dialog: {str(e)}")

    def _show_restore_options_dialog(self, backup_path: str, has_presets: bool, has_reports: bool, 
                                   has_bookmarks: bool, has_va_profile: bool, has_userdb: bool = False, has_journals: bool = False, manifest: Optional[Dict] = None) -> None:
        """Show dialog to select what to restore from backup"""
        try:
            dialog = tk.Toplevel(self)
            dialog.title("Restore from Backup")
            dialog.geometry("450x550")
            dialog.resizable(False, False)
            dialog.configure(bg="#2c3e50")
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
            title_label = tk.Label(dialog, text="📂 Restore from Backup", 
                                 font=("Segoe UI", 14, "bold"),
                                 bg="#2c3e50", fg="#ecf0f1")
            title_label.pack(pady=15)
            
            # Backup info
            if manifest:
                backup_date = manifest.get("backup_date", "Unknown")
                app_version = manifest.get("app_version", "Unknown")
                info_text = f"Backup Date: {backup_date[:19].replace('T', ' ')}\nApp Version: {app_version}"
            else:
                info_text = f"Backup File: {os.path.basename(backup_path)}"
                
            info_label = tk.Label(dialog, text=info_text,
                                font=("Segoe UI", 9),
                                bg="#2c3e50", fg="#bdc3c7")
            info_label.pack(pady=(0, 10))
            
            # Instructions
            inst_label = tk.Label(dialog, text="Select what to restore:",
                                font=("Segoe UI", 10),
                                bg="#2c3e50", fg="#bdc3c7")
            inst_label.pack(pady=(0, 20))
            
            # Restore options frame
            options_frame = tk.Frame(dialog, bg="#2c3e50")
            options_frame.pack(pady=10)
            
            # Restore option variables
            restore_presets = tk.IntVar(value=1 if has_presets else 0)
            restore_reports = tk.IntVar(value=1 if has_reports else 0)
            restore_bookmarks = tk.IntVar(value=1 if has_bookmarks else 0)
            restore_va_profile = tk.IntVar(value=1 if has_va_profile else 0)
            restore_userdb = tk.IntVar(value=0)  # Default to unchecked for safety
            restore_journals = tk.IntVar(value=0)  # Default to unchecked for safety
            
            # Checkboxes for available items
            if has_presets:
                presets_cb = tk.Checkbutton(options_frame, text="⚙️ Ship Presets",
                                          variable=restore_presets,
                                          bg="#2c3e50", fg="#ecf0f1",
                                          selectcolor="#34495e",
                                          activebackground="#34495e",
                                          activeforeground="#ecf0f1",
                                          font=("Segoe UI", 10))
                presets_cb.pack(anchor="w", pady=2)
            
            if has_reports:
                reports_cb = tk.Checkbutton(options_frame, text="📊 Mining Reports",
                                          variable=restore_reports,
                                          bg="#2c3e50", fg="#ecf0f1",
                                          selectcolor="#34495e",
                                          activebackground="#34495e",
                                          activeforeground="#ecf0f1",
                                          font=("Segoe UI", 10))
                reports_cb.pack(anchor="w", pady=2)
            
            if has_bookmarks:
                bookmarks_cb = tk.Checkbutton(options_frame, text="🔖 Mining Bookmarks",
                                            variable=restore_bookmarks,
                                            bg="#2c3e50", fg="#ecf0f1",
                                            selectcolor="#34495e",
                                            activebackground="#34495e",
                                            activeforeground="#ecf0f1",
                                            font=("Segoe UI", 10))
                bookmarks_cb.pack(anchor="w", pady=2)
            
            if has_va_profile:
                va_profile_cb = tk.Checkbutton(options_frame, text="🎤 VoiceAttack Profile",
                                             variable=restore_va_profile,
                                             bg="#2c3e50", fg="#ecf0f1",
                                             selectcolor="#34495e",
                                             activebackground="#34495e",
                                             activeforeground="#ecf0f1",
                                             font=("Segoe UI", 10))
                va_profile_cb.pack(anchor="w", pady=2)
            
            if has_userdb:
                userdb_cb = tk.Checkbutton(options_frame, text="💾 User Database (Hotspots)",
                                          variable=restore_userdb,
                                          bg="#2c3e50", fg="#ecf0f1",
                                          selectcolor="#34495e",
                                          activebackground="#34495e",
                                          activeforeground="#ecf0f1",
                                          font=("Segoe UI", 10))
                userdb_cb.pack(anchor="w", pady=2)
            
            if has_journals:
                journals_cb = tk.Checkbutton(options_frame, text="📝 Journal Files",
                                           variable=restore_journals,
                                           bg="#2c3e50", fg="#ecf0f1",
                                           selectcolor="#34495e",
                                           activebackground="#34495e",
                                           activeforeground="#ecf0f1",
                                           font=("Segoe UI", 10))
                journals_cb.pack(anchor="w", pady=2)
            
            # Warning label
            warning_label = tk.Label(dialog, 
                                   text="⚠️ Warning: This will overwrite existing files!",
                                   font=("Segoe UI", 9, "bold"),
                                   bg="#2c3e50", fg="#e74c3c")
            warning_label.pack(pady=(20, 5))
            
            # Restart info label
            restart_label = tk.Label(dialog, 
                                   text="ℹ️ Restart the app after restoring backups",
                                   font=("Segoe UI", 9),
                                   bg="#2c3e50", fg="#95a5a6")
            restart_label.pack(pady=(0, 10))
            
            # Buttons frame
            btn_frame = tk.Frame(dialog, bg="#2c3e50")
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
                    messagebox.showwarning("No Selection", "Please select at least one item to restore.")
                    return
                
                # Confirm action
                result = messagebox.askyesno("Confirm Restore", 
                                           "Are you sure you want to restore the selected items?\n\n"
                                           "This will overwrite existing files!")
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
            
            restore_btn = tk.Button(btn_frame, text="✅ Restore", command=on_restore,
                                  bg="#27ae60", fg="white", font=("Segoe UI", 10, "bold"),
                                  width=15, cursor="hand2")
            restore_btn.pack(side=tk.LEFT, padx=5)
            
            cancel_btn = tk.Button(btn_frame, text="❌ Cancel", command=on_cancel,
                                 bg="#e74c3c", fg="white", font=("Segoe UI", 10, "bold"),
                                 width=15, cursor="hand2")
            cancel_btn.pack(side=tk.LEFT, padx=5)
            
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
                messagebox.showinfo("Restore Complete", 
                                  f"Successfully restored:\n{items_text}")
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
            self.ring_finder = RingFinder(parent_frame, self.prospector_panel, app_dir, ToolTip)
            
            # Check if there were any pending hotspot additions while Ring Finder was being created
            if getattr(self, '_pending_ring_finder_refresh', False):
                self._refresh_ring_finder()
                
        except Exception as e:
            print(f"Ring finder setup failed: {e}")

    def _build_marketplace_tab(self, frame: ttk.Frame) -> None:
        """Build the Commodity Market tab - matches Hotspots Finder design"""
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search section
        search_frame = ttk.LabelFrame(main_container, text="Search For Commodity Prices", padding=10)
        search_frame.pack(fill="x", pady=(0, 10))
        
        # Configure grid weights
        search_frame.columnconfigure(1, weight=1)
        
        self.marketplace_search_mode = tk.StringVar(value="near_system")
        self.marketplace_sell_mode = tk.BooleanVar(value=True)
        self.marketplace_buy_mode = tk.BooleanVar(value=False)
        
        # Row 0: Search Mode (Near/Galaxy) + Sell/Buy
        row0_frame = tk.Frame(search_frame, bg="#1e1e1e")
        row0_frame.grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        rb1 = tk.Radiobutton(row0_frame, text="Near System (500 LY)", variable=self.marketplace_search_mode,
                      value="near_system", bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e",
                      activebackground="#1e1e1e", activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        rb1.pack(side="left", padx=(0, 15))
        rb1.config(takefocus=0)
        
        rb2 = tk.Radiobutton(row0_frame, text="Galaxy-Wide (Top 30)", variable=self.marketplace_search_mode,
                      value="galaxy_wide", bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e",
                      activebackground="#1e1e1e", activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        rb2.pack(side="left", padx=(0, 20))
        rb2.config(takefocus=0)
        
        ttk.Separator(row0_frame, orient="vertical").pack(side="left", fill="y", padx=(0, 15))
        
        sell_cb = tk.Checkbutton(row0_frame, text="Sell", variable=self.marketplace_sell_mode,
                      command=self._on_sell_mode_toggle, bg="#1e1e1e", fg="#e0e0e0", selectcolor="#2d2d2d",
                      activebackground="#1e1e1e", activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        sell_cb.pack(side="left", padx=(0, 10))
        ToolTip(sell_cb, "Search for stations buying this commodity (where you can sell)")
        
        buy_cb = tk.Checkbutton(row0_frame, text="Buy", variable=self.marketplace_buy_mode,
                      command=self._on_buy_mode_toggle, bg="#1e1e1e", fg="#e0e0e0", selectcolor="#2d2d2d",
                      activebackground="#1e1e1e", activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        buy_cb.pack(side="left")
        ToolTip(buy_cb, "Search for stations selling this commodity (where you can buy)")
        
        # Row 1: Reference System + Commodity
        row1_frame = tk.Frame(search_frame, bg="#1e1e1e")
        row1_frame.grid(row=1, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        ttk.Label(row1_frame, text="Ref. System:").pack(side="left", padx=(0, 5))
        self.marketplace_reference_system = tk.StringVar(value="")
        self.marketplace_ref_entry = ttk.Entry(row1_frame, textvariable=self.marketplace_reference_system, width=30)
        self.marketplace_ref_entry.pack(side="left", padx=(0, 5))
        self.marketplace_ref_entry.bind("<Return>", lambda e: self._search_marketplace())
        
        self.marketplace_use_current_btn = tk.Button(row1_frame, text="Use Current", 
                                    command=self._use_current_system_marketplace,
                                    bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                                    relief="ridge", bd=1, padx=6, pady=2, font=("Segoe UI", 8), cursor="hand2")
        self.marketplace_use_current_btn.pack(side="left", padx=(0, 20))
        
        ttk.Label(row1_frame, text="Commodity:").pack(side="left", padx=(0, 5))
        self.marketplace_commodity = tk.StringVar(value="Alexandrite")
        sorted_commodities = ["Alexandrite", "Bauxite", "Benitoite", "Bertrandite", "Bromellite", 
                             "Cobalt", "Coltan", "Gallite", "Gold", "Grandidierite", "Indite", 
                             "Lepidolite", "LTD", "Monazite", "Musgravite", 
                             "Osmium", "Painite", "Palladium", "Platinum", "Praseodymium", 
                             "Rhodplumsite", "Rutile", "Samarium", "Serendibite", "Silver", 
                             "Tritium", "Uraninite", "Void Opals"]
        commodity_combo = ttk.Combobox(row1_frame, textvariable=self.marketplace_commodity,
                                     values=sorted_commodities, state="readonly", width=18)
        commodity_combo.pack(side="left")
        commodity_combo.bind("<Return>", lambda e: self._search_marketplace())
        
        # Row 2: All filters
        row2_frame = tk.Frame(search_frame, bg="#1e1e1e")
        row2_frame.grid(row=2, column=0, columnspan=5, sticky="w", pady=(0, 10))
        
        ttk.Label(row2_frame, text="Station:").pack(side="left", padx=(0, 5))
        self.marketplace_station_type = tk.StringVar(value="All")
        station_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_station_type,
                                values=["All", "Orbital Only", "Surface Only", "Fleet Carrier", "Megaship", "Stronghold"],
                                state="readonly", width=12)
        station_combo.pack(side="left", padx=(0, 15))
        ToolTip(station_combo, "Filter by station type: Orbital, Surface, Fleet Carrier, Megaship, or Stronghold")
        
        def on_station_type_change(*args):
            if self.marketplace_station_type.get() == "Fleet Carrier":
                self.marketplace_exclude_carriers.set(False)
        self.marketplace_station_type.trace_add("write", on_station_type_change)
        
        cfg = _load_cfg()
        self.marketplace_exclude_carriers = tk.BooleanVar(value=cfg.get('marketplace_exclude_carriers', True))
        exclude_cb = tk.Checkbutton(row2_frame, text="Exclude Carriers", variable=self.marketplace_exclude_carriers,
                      bg="#1e1e1e", fg="#e0e0e0", selectcolor="#2d2d2d",
                      activebackground="#1e1e1e", activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        exclude_cb.pack(side="left", padx=(0, 10))
        ToolTip(exclude_cb, "Exclude Fleet Carriers from search results")
        
        self.marketplace_large_pad_only = tk.BooleanVar(value=cfg.get('marketplace_large_pad_only', False))
        large_pad_cb = tk.Checkbutton(row2_frame, text="Large Pads", variable=self.marketplace_large_pad_only,
                      bg="#1e1e1e", fg="#e0e0e0", selectcolor="#2d2d2d",
                      activebackground="#1e1e1e", activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=("Segoe UI", 9))
        large_pad_cb.pack(side="left", padx=(0, 15))
        ToolTip(large_pad_cb, "Show only stations with Large landing pads")
        
        ttk.Label(row2_frame, text="Sort by:").pack(side="left", padx=(0, 5))
        self.marketplace_order_by = tk.StringVar(value="Distance")
        self.marketplace_order_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_order_by,
                                     values=["Best price", "Distance", "Best supply/demand", "Last update"],
                                     state="readonly", width=15)
        self.marketplace_order_combo.pack(side="left", padx=(0, 10))
        ToolTip(self.marketplace_order_combo, "Sort results by price, distance, supply/demand, or data freshness")
        
        ttk.Label(row2_frame, text="Max age:").pack(side="left", padx=(0, 5))
        self.marketplace_max_age = tk.StringVar(value="8 hours")
        age_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_max_age,
                                values=["Any", "1 hour", "8 hours", "16 hours", "1 day", "2 days"],
                                state="readonly", width=10)
        age_combo.pack(side="left", padx=(0, 15))
        ToolTip(age_combo, "Filter by how recent the market data is")
        
        # Row 3: Search button
        row3_frame = tk.Frame(search_frame, bg="#1e1e1e")
        row3_frame.grid(row=3, column=0, columnspan=5, sticky="w")
        
        search_btn = tk.Button(row3_frame, text="🔍 Search", 
                              command=self._search_marketplace,
                              bg="#2a4a2a", fg="#e0e0e0", 
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, padx=10, pady=4,
                              font=("Segoe UI", 9, "bold"), cursor="hand2")
        search_btn.pack(side="left")
        
        # EDTools button hidden (keep for future reference)
        # edtools_btn = tk.Button(search_frame, text="🔍 Search EDTools.cc", 
        #                        command=self._open_edtools_market,
        #                        bg="#2a4a2a", fg="#e0e0e0")
        # edtools_btn.grid(row=4, column=0, columnspan=5, pady=(5, 5))
        
        # Results section with help text on same line as label
        results_header = tk.Frame(main_container, bg="#1e1e1e")
        results_header.pack(fill="x", pady=(10, 0))
        
        tk.Label(results_header, text="Search Results", 
                bg="#1e1e1e", fg="#ffffff", 
                font=("Segoe UI", 10, "bold")).pack(side="left")
        
        tk.Label(results_header, text="  •  Right-click rows for options",
                bg="#1e1e1e", fg="#888888",
                font=("Segoe UI", 8)).pack(side="left")
        
        # Status label (moved to header, right side)
        self.marketplace_total_label = tk.Label(results_header, text="Enter system and commodity, then click Search",
                                               bg="#1e1e1e", fg="gray", font=("TkDefaultFont", 8))
        self.marketplace_total_label.pack(side="right")
        
        results_frame = tk.Frame(main_container, bg="#2d2d2d", relief="sunken", bd=1)
        results_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        # Create results table
        self._create_marketplace_results_table(results_frame)
        
        # Add tooltips
        ToolTip(self.marketplace_ref_entry, "Enter reference system for distance-based search")
        ToolTip(self.marketplace_use_current_btn, "Use current system from journal")
        ToolTip(search_btn, "Search for commodity prices")
        ToolTip(commodity_combo, "Select commodity to search")
    
    def _create_marketplace_results_table(self, parent_frame):
        """Create results table for marketplace search"""
        table_frame = ttk.Frame(parent_frame)
        table_frame.pack(fill="both", expand=True)
        
        # Define columns (removed St Dist due to API data inaccuracies)
        columns = ("location", "type", "pad", "distance", "demand", "price", "updated")
        
        # Create Treeview
        self.marketplace_tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=15)
        
        # Define headings with sorting
        numeric_columns = {"distance", "demand", "price", "updated"}
        for col in columns:
            is_numeric = col in numeric_columns
            self.marketplace_tree.heading(col, text=self._get_column_title(col), 
                                         command=lambda c=col, n=is_numeric: self._sort_marketplace_column(c, n))
        
        # Track sort state
        self.marketplace_sort_column = None
        self.marketplace_sort_reverse = False
        
        # Set column widths - Location left-aligned, all others centered
        self.marketplace_tree.column("location", width=250, minwidth=150, anchor="w", stretch=False)
        self.marketplace_tree.column("type", width=90, minwidth=70, anchor="center", stretch=False)
        self.marketplace_tree.column("pad", width=40, minwidth=40, anchor="center", stretch=False)
        self.marketplace_tree.column("distance", width=65, minwidth=55, anchor="center", stretch=False)
        self.marketplace_tree.column("demand", width=70, minwidth=55, anchor="center", stretch=False)
        self.marketplace_tree.column("price", width=120, minwidth=80, anchor="center", stretch=False)
        self.marketplace_tree.column("updated", width=90, minwidth=70, anchor="center", stretch=False)
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.marketplace_tree.yview)
        self.marketplace_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.marketplace_tree.xview)
        self.marketplace_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Grid layout for treeview and scrollbars (like Ring Finder)
        self.marketplace_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        # Add right-click context menu
        self._create_marketplace_context_menu()
        self.marketplace_tree.bind("<Button-3>", self._show_marketplace_context_menu)
    
    def _get_column_title(self, col):
        """Get display title for column - dynamically changes based on buy/sell mode"""
        # Check mode for demand/stock label
        is_buy_mode = self.marketplace_buy_mode.get() if hasattr(self, 'marketplace_buy_mode') else False
        
        titles = {
            "location": "Location",
            "type": "Type",
            "pad": "Pad",
            "distance": "Distance",
            "demand": "Stock" if is_buy_mode else "Demand",  # Dynamic based on mode
            "price": "Price",
            "updated": "Updated"
        }
        return titles.get(col, col)
    
    def _update_marketplace_column_headers(self):
        """Update column headers when mode changes"""
        if hasattr(self, 'marketplace_tree'):
            numeric_columns = {"distance", "demand", "price", "updated"}
            for col in ("location", "type", "pad", "distance", "demand", "price", "updated"):
                is_numeric = col in numeric_columns
                self.marketplace_tree.heading(col, text=self._get_column_title(col), 
                                            command=lambda c=col, n=is_numeric: self._sort_marketplace_column(c, n))
    
    def _create_marketplace_context_menu(self):
        """Create right-click context menu for marketplace results"""
        self.marketplace_context_menu = tk.Menu(self, tearoff=0,
                                               bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                                               activebackground=MENU_COLORS["activebackground"],
                                               activeforeground=MENU_COLORS["activeforeground"],
                                               selectcolor=MENU_COLORS["selectcolor"])
        self.marketplace_context_menu.add_command(label="Open in Inara", command=self._open_inara_from_menu)
        self.marketplace_context_menu.add_command(label="Open in EDSM", command=self._open_edsm_from_menu)
        self.marketplace_context_menu.add_separator()
        self.marketplace_context_menu.add_command(label="Copy System Name", command=self._copy_marketplace_system)
    
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
                    self.marketplace_total_label.config(text=f"✓ Copied '{system_name}' to clipboard")
    
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
    
    def _update_marketplace_order_options(self):
        """Update Order by dropdown options based on buy/sell mode"""
        if hasattr(self, 'marketplace_order_combo'):
            is_buy_mode = self.marketplace_buy_mode.get()
            current_value = self.marketplace_order_by.get()
            
            if is_buy_mode:
                # Buy mode options
                options = ["Best price (lowest)", "Distance", "Best supply", "Last update"]
            else:
                # Sell mode options
                options = ["Best price (highest)", "Distance", "Best demand", "Last update"]
            
            self.marketplace_order_combo['values'] = options
            
            # Update current selection if it was one of the changing options
            if "Best price" in current_value:
                self.marketplace_order_by.set(options[0])
            elif "supply" in current_value or "demand" in current_value:
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
                self.marketplace_total_label.config(text="No results to export")
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
                
                self.marketplace_total_label.config(text=f"✅ Exported {len(items)} results to {file_path}")
            
        except Exception as e:
            self.marketplace_total_label.config(text=f"❌ Export failed: {str(e)}")
    
    def _clear_marketplace_cache(self):
        """Clear marketplace cache - no longer needed (using external sites)"""
        self.marketplace_total_label.config(text="ℹ️ Cache not needed (using external sites)")
    
    # ==================== UNUSED MARKETPLACE SEARCH METHODS (Kept for reference) ====================
    # These methods are no longer used - marketplace now uses external websites (Inara, edtools.cc)
    # Kept here temporarily in case rollback is needed
    
    def _search_marketplace(self):
        """Search for commodity prices using Ardent API"""
        try:
            commodity = self.marketplace_commodity.get()
            search_mode = self.marketplace_search_mode.get()
            
            # Validation
            if not commodity:
                self.marketplace_total_label.config(text="❌ Please select a commodity")
                return
            
            # Mode-specific validation
            if search_mode == "near_system":
                reference_system = self.marketplace_reference_system.get().strip()
                if not reference_system:
                    self.marketplace_total_label.config(text="❌ Please enter a reference system")
                    return
            
            # Convert max age to days
            max_age_str = self.marketplace_max_age.get()
            max_days_ago = self._convert_age_to_days(max_age_str)
            
            # Determine buy/sell mode
            is_buy_mode = self.marketplace_buy_mode.get()
            is_sell_mode = self.marketplace_sell_mode.get()
            
            # Get exclude carriers setting
            exclude_carriers = self.marketplace_exclude_carriers.get()
            
            # Show searching status
            mode_text = "buying from" if is_buy_mode else "selling to"
            self.marketplace_total_label.config(text=f"🔍 Searching for stations {mode_text}...")
            self.update()
            
            # Call appropriate API based on search mode and buy/sell mode
            if search_mode == "galaxy_wide":
                # Galaxy-wide search
                if is_buy_mode:
                    results = MarketplaceAPI.search_sellers_galaxy_wide(commodity, max_days_ago, exclude_carriers)
                else:
                    results = MarketplaceAPI.search_buyers_galaxy_wide(commodity, max_days_ago)
            else:
                # Near system search (within 500 LY)
                reference_system = self.marketplace_reference_system.get().strip()
                if is_buy_mode:
                    results = MarketplaceAPI.search_sellers(commodity, reference_system, None, max_days_ago, exclude_carriers)
                else:
                    results = MarketplaceAPI.search_buyers(commodity, reference_system, None, max_days_ago)
            
            # Apply filters
            exclude_carriers = self.marketplace_exclude_carriers.get()
            station_type_filter = self.marketplace_station_type.get()
            
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
                results = [r for r in results if "FleetCarrier" not in r.get('stationType', '')]
            
            # Filter by Station Type (Surface/Orbital/Carrier/MegaShip/Stronghold)
            if station_type_filter == "Orbital Only":
                # Orbital stations: Coriolis, Orbis, Ocellus, Outpost, AsteroidBase (EXACT MATCH only)
                # BUG FIX: Use exact match to prevent CraterOutpost matching "Outpost" substring
                orbital_types = ["Coriolis", "Orbis", "Ocellus", "Outpost", "AsteroidBase"]
                results = [r for r in results if r.get('stationType', '') in orbital_types]
            elif station_type_filter == "Surface Only":
                # Surface stations: CraterOutpost, CraterPort, OnFootSettlement, etc. (substring match for variants)
                # Use startswith/contains for surface types since they have variants (CraterOutpost, CraterPort, OnFootSettlement, OnFootStation)
                surface_types = ["Crater", "OnFoot", "Planetary"]
                results = [r for r in results if any(r.get('stationType', '').startswith(t) for t in surface_types)]
            elif station_type_filter == "Fleet Carrier":
                # Fleet Carriers only
                results = [r for r in results if "FleetCarrier" in r.get('stationType', '')]
            elif station_type_filter == "Megaship":
                # MegaShips only
                results = [r for r in results if r.get('stationType', '') == "MegaShip"]
            elif station_type_filter == "Stronghold":
                # Stronghold Carriers only
                results = [r for r in results if "StrongholdCarrier" in r.get('stationType', '')]
            
            # Filter by Landing Pad Size (Large only if checked)
            large_pad_only = self.marketplace_large_pad_only.get()
            
            if large_pad_only:
                # Only show stations with Large pads (maxLandingPadSize == 3)
                results = [r for r in results if r.get('maxLandingPadSize') == 3]
            
            if results:
                # Sort results based on "Order by" selection
                order_by = self.marketplace_order_by.get()
                
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
                        self.marketplace_total_label.config(text="⏳ Calculating distances...")
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
                        self.marketplace_total_label.config(text=f"✓ Found {len(results)} stations (showing top 30 by price)")
                elif search_mode == "near_system":
                    # Near system: show top 30 by price (already sorted by distance in API)
                    self._display_marketplace_results(results_sorted[:30])
                    self.marketplace_total_label.config(text=f"✓ Found {len(results)} stations (showing top 30 by price)")
            else:
                # No results after filtering - clear the table and show message
                self._clear_marketplace_results()
                
                # Check if we had results before filtering
                if original_count > 0:
                    # We had results but filtered them all out
                    if exclude_carriers:
                        self.marketplace_total_label.config(
                            text=f"⚠️ Found {original_count} stations but all are Fleet Carriers. Uncheck 'Exclude Fleet Carriers' to see them."
                        )
                    else:
                        self.marketplace_total_label.config(
                            text=f"⚠️ Found {original_count} stations but none match your filters (station type/pad size)."
                        )
                else:
                    # No results from API at all
                    self.marketplace_total_label.config(text="❌ No results found")
                
        except Exception as e:
            self.marketplace_total_label.config(text=f"❌ Search failed: {str(e)}")
    
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
        """Display marketplace results from Ardent API (sorted by distance by default)"""
        self._clear_marketplace_results()
        
        # Sort by distance (closest first) for display
        results_sorted = sorted(results, key=lambda x: x.get('distance', 999999))
        
        commodity = self.marketplace_commodity.get()
        self._populate_marketplace_results(results_sorted, commodity)
    
    def _populate_marketplace_results(self, results, commodity):
        """Populate marketplace results in UI"""
        try:
            # Determine mode for correct field handling
            is_buy_mode = self.marketplace_buy_mode.get()
            
            # Populate results (sorted by distance - closest first)
            for result in results:
                # LOCATION (System + Station) - API uses camelCase
                location = f"{result['systemName']} / {result['stationName'][:25]}"
                
                # TYPE (Station type) - Simplified to Orbital/Surface matching filter
                api_type = result.get('stationType', 'Unknown')
                
                # Determine if orbital or surface
                orbital_types = ['Coriolis', 'Orbis', 'Ocellus', 'Outpost', 'AsteroidBase']
                surface_keywords = ['Crater', 'OnFoot', 'Planetary', 'Surface']
                
                if api_type in orbital_types:
                    station_type = 'Orbital'
                elif any(keyword in api_type for keyword in surface_keywords):
                    station_type = 'Surface'
                elif api_type == 'FleetCarrier':
                    station_type = 'Carrier'
                elif api_type == 'StrongholdCarrier':
                    station_type = 'Stronghold'
                elif api_type == 'MegaShip':
                    station_type = 'MegaShip'
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
                
                self.marketplace_tree.insert("", "end", values=(
                    location,
                    station_type,
                    pad,
                    distance,
                    volume,
                    price,
                    updated
                ))
            
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
            column_ids = ("location", "type", "pad", "distance", "demand", "price", "updated")
            
            # Map display names to column IDs
            display_to_id = {
                "Location": "location",
                "Station Type": "type", 
                "Pad": "pad",
                "Distance": "distance",
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
                        if col_id == "distance":
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
            # Re-display results with distances
            self._display_marketplace_results(results_with_distances)
            self.marketplace_total_label.config(text=f"✓ Found {total_results} stations (showing top 30 with distances)")
            self.config(cursor="")
        except Exception as e:
            print(f"[MARKETPLACE] Error updating with distances: {e}")
            self.config(cursor="")
    
    def _restore_marketplace_cursor(self, total_results):
        """Restore cursor if distance calculation fails"""
        self.marketplace_total_label.config(text=f"✓ Found {total_results} stations (showing top 30)")
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
        """Check for updates on startup (automatic check)"""
        print(f"Checking for updates... Current version: {get_version()}")
        if self.update_checker.should_check_for_updates(UPDATE_CHECK_INTERVAL):
            print("Update check: Time limit passed, checking for updates...")
            self.update_checker.check_for_updates_async(self)
        else:
            print("Update check: Skipping - checked recently")

    def _manual_update_check(self):
        """Manually check for updates (from menu)"""
        self.update_checker.manual_check(self)
    
    def _auto_scan_journals_startup(self):
        """Auto-scan new journal entries on startup, with welcome dialog for first-time users"""
        import threading
        import glob
        from incremental_journal_scanner import IncrementalJournalScanner
        from journal_scan_state import JournalScanState
        
        # Check if auto-scan is enabled in settings
        cfg = _load_cfg()
        auto_scan_enabled = cfg.get("auto_scan_journals", True)
        
        if not auto_scan_enabled:
            print("[JOURNAL] Auto-scan disabled by user preference")
            self._set_status("Auto-scan disabled - enable in Settings if desired", 10000)
            return
        
        print("[JOURNAL] Starting auto-scan on startup...")
        self._set_status("Checking journals for new mining data...", 3000)
        
        # Check if this is first run (no state file)
        state = JournalScanState()
        last_journal = state.get_last_journal_file()
        is_first_run = not last_journal
        
        print(f"DEBUG: First run check - last_journal={last_journal}, is_first_run={is_first_run}")
        
        if is_first_run:
            # Count journal files for the welcome message
            journal_dir = self.cargo_monitor.journal_dir
            pattern = os.path.join(journal_dir, "Journal.*.log")
            all_journals = sorted(glob.glob(pattern))
            journal_count = len(all_journals)
            
            if journal_count > 0:
                # Show welcome dialog
                self._show_first_run_welcome_dialog(journal_count, all_journals)
            else:
                print("No journal files found, skipping initial import")
                self._set_status("No journal files found - check journal folder in Settings", 8000)
        else:
            # Not first run - do incremental auto-scan
            self._run_auto_scan_background()
    
    def _show_first_run_welcome_dialog(self, journal_count, all_journals):
        """Show welcome dialog for first-time users"""
        # Get oldest journal date for display
        oldest_date = "unknown"
        if all_journals:
            oldest_file = os.path.basename(all_journals[0])
            try:
                # Parse date from filename: Journal.2023-09-01T120000.01.log
                date_part = oldest_file.split('.')[1].split('T')[0]
                oldest_date = date_part
            except:
                pass
        
        # Estimate time (rough: ~18 journals/second based on test)
        estimated_minutes = max(1, journal_count // (18 * 60))
        time_text = f"{estimated_minutes} minute{'s' if estimated_minutes != 1 else ''}"
        
        dialog = tk.Toplevel(self)
        dialog.title("Welcome to EliteMining!")
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # Set icon
        set_window_icon(dialog)
        
        # Position centered on parent
        dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 200
        y = self.winfo_y() + (self.winfo_height() // 2) - 175
        dialog.geometry(f"400x350+{x}+{y}")
        
        # Main content frame
        content = tk.Frame(dialog, bg="#2b2b2b", padx=20, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = tk.Label(content, text="Welcome to EliteMining!", 
                        font=("Segoe UI", 14, "bold"), 
                        bg="#2b2b2b", fg="#ffffff")
        title.pack(pady=(0, 10))
        
        # Message
        message_text = f"""This appears to be your first time running EliteMining.

Would you like to scan your Elite Dangerous journal files to import your mining history?"""
        
        message = tk.Label(content, text=message_text,
                          font=("Segoe UI", 10),
                          bg="#2b2b2b", fg="#e6e6e6",
                          justify=tk.LEFT, wraplength=360)
        message.pack(pady=(0, 15))
        
        # Bullet points
        bullets_text = f"""• This will import all discovered rings, hotspots, and visited systems
• Found {journal_count:,} journal files dating back to {oldest_date}
• Scanning will take approximately {time_text}
• You can skip this and manually import your history later from Settings → Import History"""
        
        bullets = tk.Label(content, text=bullets_text,
                          font=("Segoe UI", 9),
                          bg="#2b2b2b", fg="#cccccc",
                          justify=tk.LEFT, wraplength=360)
        bullets.pack(pady=(0, 20))
        
        # Question
        question = tk.Label(content, text="Scan now?",
                           font=("Segoe UI", 10, "bold"),
                           bg="#2b2b2b", fg="#ffffff")
        question.pack(pady=(0, 15))
        
        # Button frame
        button_frame = tk.Frame(content, bg="#2b2b2b")
        button_frame.pack()
        
        def on_scan():
            dialog.destroy()
            self._run_initial_import_with_progress()
        
        def on_skip():
            dialog.destroy()
            # Create empty state file so we don't ask again
            # but still allow auto-scan for new journals
            from journal_scan_state import JournalScanState
            state = JournalScanState()
            # Set state to latest journal with current position
            journal_dir = self.cargo_monitor.journal_dir
            pattern = os.path.join(journal_dir, "Journal.*.log")
            all_journals = sorted(glob.glob(pattern))
            if all_journals:
                latest = all_journals[-1]
                file_size = os.path.getsize(latest)
                state.save_state(latest, file_size)
            print("Initial import skipped by user")
        
        # Scan Now button (green, recommended)
        scan_btn = tk.Button(button_frame, text="Scan Now", command=on_scan,
                            bg="#27ae60", fg="white", 
                            font=("Segoe UI", 10, "bold"),
                            width=12, cursor="hand2", relief=tk.FLAT,
                            activebackground="#229954")
        scan_btn.pack(side=tk.LEFT, padx=5)
        
        # Skip button
        skip_btn = tk.Button(button_frame, text="Skip", command=on_skip,
                            bg="#5a5a5a", fg="white",
                            font=("Segoe UI", 10),
                            width=12, cursor="hand2", relief=tk.FLAT,
                            activebackground="#4a4a4a")
        skip_btn.pack(side=tk.LEFT, padx=5)
        
        # Bind Escape to skip
        dialog.bind('<Escape>', lambda e: on_skip())
        
        # Make Scan Now the default (Enter key)
        scan_btn.focus_set()
        dialog.bind('<Return>', lambda e: on_scan())
    
    def _run_initial_import_with_progress(self):
        """Run initial import with progress dialog"""
        import threading
        from incremental_journal_scanner import IncrementalJournalScanner
        
        # Create progress dialog
        progress_dialog = tk.Toplevel(self)
        progress_dialog.title("Importing Journal History")
        progress_dialog.transient(self)
        progress_dialog.grab_set()
        progress_dialog.resizable(False, False)
        progress_dialog.protocol("WM_DELETE_WINDOW", lambda: None)  # Disable X button
        
        # Set icon
        set_window_icon(progress_dialog)
        
        # Position centered on parent
        progress_dialog.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - 200
        y = self.winfo_y() + (self.winfo_height() // 2) - 100
        progress_dialog.geometry(f"400x200+{x}+{y}")
        
        # Content frame
        content = tk.Frame(progress_dialog, bg="#2b2b2b", padx=20, pady=20)
        content.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title = tk.Label(content, text="Importing Mining History", 
                        font=("Segoe UI", 12, "bold"), 
                        bg="#2b2b2b", fg="#ffffff")
        title.pack(pady=(0, 15))
        
        # Progress label
        progress_label = tk.Label(content, text="Preparing scan...",
                                 font=("Segoe UI", 9),
                                 bg="#2b2b2b", fg="#e6e6e6")
        progress_label.pack(pady=(0, 5))
        
        # Progress bar
        progress_bar = ttk.Progressbar(content, length=360, mode='determinate')
        progress_bar.pack(pady=(0, 10))
        
        # Stats label
        stats_label = tk.Label(content, text="Files: 0 | Events: 0",
                              font=("Segoe UI", 9),
                              bg="#2b2b2b", fg="#cccccc")
        stats_label.pack(pady=(0, 15))
        
        # Cancel button
        cancel_requested = {'value': False}
        
        def on_cancel():
            cancel_requested['value'] = True
            cancel_btn.config(state=tk.DISABLED, text="Cancelling...")
        
        cancel_btn = tk.Button(content, text="Cancel", command=on_cancel,
                              bg="#5a5a5a", fg="white",
                              font=("Segoe UI", 9),
                              width=15, cursor="hand2", relief=tk.FLAT,
                              activebackground="#4a4a4a")
        cancel_btn.pack()
        
        # Scan in background
        def scan_with_progress():
            try:
                journal_dir = self.cargo_monitor.journal_dir
                user_db = self.cargo_monitor.user_db
                scanner = IncrementalJournalScanner(journal_dir, user_db)
                
                total_events = 0
                
                def progress_callback(files_done, total_files, current_file):
                    if cancel_requested['value']:
                        return  # Stop processing
                    
                    # Update UI in main thread
                    percent = int((files_done / total_files) * 100) if total_files > 0 else 0
                    self.after(0, lambda: progress_bar.config(value=percent))
                    self.after(0, lambda: progress_label.config(text=f"Scanning: {current_file}"))
                    self.after(0, lambda f=files_done, t=total_files, e=total_events: 
                              stats_label.config(text=f"Files: {f}/{t} | Events: {e:,}"))
                
                # Modified scan that checks for cancel
                files, events = scanner.scan_new_entries(progress_callback=progress_callback)
                total_events = events
                
                # Close dialog and show result
                self.after(0, lambda: progress_dialog.destroy())
                
                if cancel_requested['value']:
                    print(f"Import cancelled by user. Processed {files} files, {events} events (partial data kept)")
                    self.after(0, lambda e=events: self._set_status(f"Import cancelled - {e:,} events imported"))
                    # Update counter even for partial import
                    if hasattr(self, 'ring_finder'):
                        self.after(0, self.ring_finder._update_database_info)
                else:
                    print(f"✓ Import complete: {files} files, {events} events processed")
                    self.after(0, lambda e=events: self._set_status(f"Imported {e:,} journal entries"))
                    # Update database counter after full import
                    if hasattr(self, 'ring_finder'):
                        print("[JOURNAL] Updating database counter after full import...")
                        self.after(0, self.ring_finder._update_database_info)
                    
            except Exception as e:
                print(f"Error during import: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, lambda: progress_dialog.destroy())
                self.after(0, lambda: self._set_status("Import failed"))
        
        thread = threading.Thread(target=scan_with_progress, daemon=True)
        thread.start()
    
    def _run_auto_scan_background(self):
        """Run auto-scan in background thread"""
        import threading
        from incremental_journal_scanner import IncrementalJournalScanner
        
        def scan_in_background():
            try:
                print("[JOURNAL] Auto-scanning journals for new entries...")
                
                # Get journal directory and user database
                journal_dir = self.cargo_monitor.journal_dir
                user_db = self.cargo_monitor.user_db
                
                # Create scanner (callback per-hotspot would be too frequent from background thread)
                scanner = IncrementalJournalScanner(journal_dir, user_db)
                
                # Scan new entries
                files, events = scanner.scan_new_entries(
                    progress_callback=lambda f, t, name: print(f"[JOURNAL] Scanning: {name} ({f}/{t})")
                )
                
                if files > 0 or events > 0:
                    print(f"[JOURNAL] ✓ Auto-scan complete: {files} file(s), {events} event(s) processed")
                    # Update status in UI thread using _set_status for auto-clear
                    event_count = events
                    self.after(0, lambda e=event_count: self._set_status(f"Scanned {e} new journal entries"))
                    # Update database counter in Hotspots Finder tab
                    if hasattr(self, 'ring_finder'):
                        print("[JOURNAL] Scheduling database counter update...")
                        self.after(0, self.ring_finder._update_database_info)
                    else:
                        print("[JOURNAL] WARNING: ring_finder not found, cannot update counter")
                else:
                    print("[JOURNAL] ✓ Auto-scan complete: No new entries")
                    self.after(0, lambda: self._set_status("No new journal entries found"))
                    
            except Exception as e:
                print(f"[JOURNAL] ERROR during auto-scan: {e}")
                import traceback
                traceback.print_exc()
                self.after(0, lambda: self._set_status("Journal scan failed - check journal folder in Settings", 8000))
        
        # Run in background thread to not block UI
        thread = threading.Thread(target=scan_in_background, daemon=True)
        thread.start()

if __name__ == "__main__":
    try:
        app = App()
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
