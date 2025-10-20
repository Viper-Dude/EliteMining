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
            font=("Arial", self.font_size, "normal"),  # Changed to Arial for thinner appearance
            wraplength=580,  # Increased from 380 to reduce text wrapping
            justify="left",
            relief="flat",  # No border
            bd=0,  # No border width
            highlightthickness=0  # No highlight
        )
        self.text_label.pack(fill="both", expand=True, padx=10, pady=10)
        
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
            
        # Update text and show window
        self.text_label.config(text=message)
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
                # Always use normal weight with Arial font for thinner appearance
                family = "Arial"  # Changed from Segoe UI to Arial
                style = "normal"  # Force normal weight
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
        screen_width = self.overlay_window.winfo_screenwidth()
        screen_height = self.overlay_window.winfo_screenheight()
        
        window_width = 600
        window_height = 120
        
        if self.position == "upper_left":
            # Position in upper-left corner with some margin
            x_pos = 50
        else:  # upper_right (default)
            # Position in upper-right corner with margin
            x_pos = screen_width - window_width - 50
        
        # Ensure window stays on screen
        x_pos = max(0, min(x_pos, screen_width - window_width))
        y_pos = max(0, min(50, screen_height - window_height))
        
        self.overlay_window.geometry(f"{window_width}x{window_height}+{x_pos}+{y_pos}")
            
    def destroy(self):
        """Clean up the overlay"""
        if self.overlay_window:
            if self.fade_timer:
                self.overlay_window.after_cancel(self.fade_timer)
            self.overlay_window.destroy()
            self.overlay_window = None

APP_TITLE = "EliteMining"
APP_VERSION = "v4.3.3"
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
        
        # Set icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                self.dialog.iconbitmap(icon_path)
            elif icon_path:
                self.dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except:
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
        self.cargo_window = None
        self.cargo_label = None
        self.position = "upper_right"
        self.display_mode = "progress"  # "progress", "detailed", "compact"
        self.transparency = 90
        self.max_cargo = 200  # Will be auto-detected from journal
        self.current_cargo = 0
        self.cargo_items = {}  # Dict of item_name: quantity
        self.refinery_contents = {}  # Dict of refinery material adjustments
        self.materials_collected = {}  # Dict of engineering material_name: quantity (Raw materials only)
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
                    
        except Exception as e:
            # Log error but don't break other functionality
            print(f"Warning: Failed to refresh Ring Finder after hotspot add: {e}")
    
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
            
            # Clear and update cargo items
            self.cargo_items.clear()
            for item in inventory:
                name = item.get("Name", "").lower()
                name_localized = item.get("Name_Localised", "")
                item_count = item.get("Count", 0)
                stolen = item.get("Stolen", 0)
                
                # Use localized name if available, otherwise clean up internal name
                if name_localized:
                    display_name = name_localized
                else:
                    display_name = name.replace("_", " ").title()
                
                if display_name and item_count > 0:
                    self.cargo_items[display_name] = item_count
            
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
        """Update cargo item quantity"""
        if quantity <= 0:
            self.cargo_items.pop(item_name, None)
        else:
            self.cargo_items[item_name] = quantity
        
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
                
                # Format: Material Name (GX)  quantity
                # Limit name length for alignment
                display_name = material_name[:20]
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
        """Reset engineering materials counter (called when mining session starts)"""
        self.materials_collected.clear()
        if hasattr(self, 'cargo_window') and self.cargo_window:
            self.update_display()
        print("[CargoMonitor] Engineering materials counter reset")
    
    def start_journal_monitoring(self):
        """Start monitoring Elite Dangerous journal files"""
        self.journal_monitor_active = True
        self.find_latest_journal()
    
    def _start_background_monitoring(self):
        """Start background monitoring that works without cargo window"""
        self.last_status_mtime = 0
        self.last_capacity_check = 0
        
        def background_monitor():
            while self.journal_monitor_active:
                try:
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
                    pass  # Silently handle errors in background
                
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
        
        # Only check if we have had mining activity and enough time has passed
        if (self.last_mining_activity and 
            not self.session_end_dialog_shown and 
            self.cargo_items and  # Only if we have cargo items detected
            len(self.cargo_items) > 0):
            
            time_since_activity = time.time() - self.last_mining_activity
            
            # If 5 minutes have passed since last mining activity
            if time_since_activity >= self.mining_activity_timeout:
                self.session_end_dialog_shown = True
                
                # Show refinery dialog
                try:
                    dialog = RefineryDialog(
                        parent=self.cargo_window if self.cargo_window else None,
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
                                          f"These materials will be included in mining reports and statistics.")
                    
                except Exception as e:
                    print(f"Error showing refinery dialog: {e}")
    
    def record_mining_activity(self):
        """Record that mining activity occurred (call when cargo changes)"""
        import time
        self.last_mining_activity = time.time()
        self.session_end_dialog_shown = False  # Reset dialog flag if activity resumes
    
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
                    self.cargo_items.clear()
                    for item in inventory:
                        name = item.get("Name", "").replace("$", "").replace("_name;", "")
                        name_localized = item.get("Name_Localised", name)
                        item_name = name_localized if name_localized else name.replace("_", " ").title()
                        item_count = item.get("Count", 0)
                        if item_name and item_count > 0:
                            self.cargo_items[item_name] = item_count
                    
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
                except Exception as saa_err:
                    print(f"Warning: Failed to process SAASignalsFound event: {saa_err}")
            
            elif event_type == "MaterialCollected":
                # Track engineering materials collected (Raw materials only)
                try:
                    category = event.get("Category", "")
                    material_name_raw = event.get("Name_Localised", event.get("Name", "")).strip()
                    count = event.get("Count", 1)
                    
                    if category == "Raw":
                        # Normalize material name to Title Case for matching
                        material_name = material_name_raw.title()
                        
                        # Only track materials in our predefined list
                        if material_name in self.MATERIAL_GRADES:
                            self.materials_collected[material_name] = self.materials_collected.get(material_name, 0) + count
                            
                            # Update popup window display if it exists
                            if hasattr(self, 'cargo_window') and self.cargo_window:
                                self.update_display()
                            
                            # Notify main app to update integrated display
                            if self.update_callback:
                                self.update_callback()
                except Exception as mat_err:
                    print(f"Warning: Failed to process MaterialCollected event: {mat_err}")
                        
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
        
        # Calculate materials mined during session
        materials_mined = {}
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
        
        session_data = {
            'start_snapshot': self.session_start_snapshot,
            'end_snapshot': end_snapshot,
            'materials_mined': materials_mined,
            'engineering_materials': self.materials_collected.copy(),  # Add engineering materials
            'prospectors_used': prospectors_used,
            'total_tons_mined': sum(materials_mined.values()),
            'session_duration': end_snapshot['timestamp'] - self.session_start_snapshot['timestamp']
        }
        
        # Log session end
        duration_mins = session_data['session_duration'] / 60
        print(f"[SESSION] Ended mining session - Duration: {duration_mins:.1f}min, Mined: {session_data['total_tons_mined']:.1f}t, "
              f"Prospectors used: {prospectors_used}, Materials: {len(materials_mined)}")
        
        # Clear the session tracking
        self.session_start_snapshot = None
        
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
        
        # Add refinery contents to live calculation
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
            
        materials_mined = {}
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
                materials_mined[item_name] = round(current_qty - start_qty, 1)
        
        # Add refinery contents per material
        if hasattr(self, 'refinery_contents') and self.refinery_contents:
            for material_name, refinery_qty in self.refinery_contents.items():
                if material_name in materials_mined:
                    materials_mined[material_name] += refinery_qty
                else:
                    materials_mined[material_name] = refinery_qty
                materials_mined[material_name] = round(materials_mined[material_name], 1)
        
        return materials_mined

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
            "Small": 14,      # Small text (increased from 12)
            "Normal": 16,     # Normal text (increased from 14)
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

        # Comprehensive Dashboard with all mining controls
        dashboard_tab = ttk.Frame(self.notebook, padding=8)
        self._build_comprehensive_dashboard(dashboard_tab)
        self.notebook.add(dashboard_tab, text="Dashboard")

        # Settings tab
        interface_tab = ttk.Frame(self.notebook, padding=8)
        self._build_interface_options_tab(interface_tab)
        self.notebook.add(interface_tab, text="Settings")

        # Hotspots Finder tab
        ring_finder_tab = ttk.Frame(self.notebook, padding=8)
        self._setup_ring_finder(ring_finder_tab)
        self.notebook.add(ring_finder_tab, text="Hotspots Finder")

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
                
                # Format: Material (GX)  quantity
                display_name = material_name[:13]
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
    
    def _on_cargo_changed(self):
        """Callback when cargo monitor data changes - update integrated display"""
        try:
            self._update_integrated_cargo_display()
            
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
    def _build_comprehensive_dashboard(self, frame: ttk.Frame) -> None:
        # Simple dashboard with sub-tabs (no sidebar here)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # Create a nested notebook for sub-tabs
        self.dashboard_notebook = ttk.Notebook(frame)
        self.dashboard_notebook.pack(fill="both", expand=True)

        # === FIREGROUPS & FIRE BUTTONS SUB-TAB ===
        fg_tab = ttk.Frame(self.dashboard_notebook, padding=8)
        self._build_fg_tab(fg_tab)
        self.dashboard_notebook.add(fg_tab, text="Firegroups & Fire Buttons")

        # === MINING SEQUENCE CONTROLS SUB-TAB ===
        timers_toggles_tab = ttk.Frame(self.dashboard_notebook, padding=8)
        self._build_timers_tab(timers_toggles_tab)
        self.dashboard_notebook.add(timers_toggles_tab, text="Mining Sequence Controls")

        # === MINING SESSION SUB-TAB ===
        session_tab = ttk.Frame(self.dashboard_notebook, padding=8)
        self._build_mining_session_tab(session_tab)
        self.dashboard_notebook.add(session_tab, text="Mining Session")

    def _build_mining_session_tab(self, frame: ttk.Frame) -> None:
        """Build the mining session control tab"""
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        
        # Create the ProspectorPanel within this frame
        try:
            self.prospector_panel = ProspectorPanel(frame, self.va_root, self._set_status, self.toggle_vars, self.text_overlay, self, self.announcement_vars, self.main_announcement_enabled, ToolTip)
            self.prospector_panel.grid(row=0, column=0, sticky="nsew")
            
            # Set auto-start preference after panel is created
            enabled = bool(self.auto_start_session.get())
            self.prospector_panel.auto_start_on_prospector = enabled
            # Sync checkbox in Mining Analytics tab
            if hasattr(self.prospector_panel, 'auto_start_var'):
                self.prospector_panel.auto_start_var.set(1 if enabled else 0)
            
            # Set prompt on cargo full preference after panel is created
            prompt_enabled = bool(self.prompt_on_cargo_full.get())
            self.prospector_panel.prompt_on_cargo_full = prompt_enabled
            # Sync checkbox in Mining Analytics tab
            if hasattr(self.prospector_panel, 'prompt_on_full_var'):
                self.prospector_panel.prompt_on_full_var.set(1 if prompt_enabled else 0)
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
            webbrowser.open("https://discord.gg/8fmpUpn5HJ")
        
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
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1
        
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
        
        # Auto-start session on first prospector checkbox
        tk.Checkbutton(scrollable_frame, text="Auto-start Session on First Prospector Launch", variable=self.auto_start_session, 
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Automatically start a mining session when you fire your first prospector limpet. The session will only auto-start if no session is currently active.", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
                 font=("Segoe UI", 8, "italic")).grid(row=r, column=0, sticky="w", pady=(0, 12))
        r += 1

        # Prompt when cargo full checkbox
        tk.Checkbutton(scrollable_frame, text="Prompt when cargo full (idle 1 min)", variable=self.prompt_on_cargo_full, 
                      bg="#1e1e1e", fg="#ffffff", selectcolor="#1e1e1e", activebackground="#1e1e1e", 
                      activeforeground="#ffffff", highlightthickness=0, bd=0, font=("Segoe UI", 9), 
                      padx=4, pady=2, anchor="w", relief="flat", highlightbackground="#1e1e1e", 
                      highlightcolor="#1e1e1e", takefocus=False).grid(row=r, column=0, sticky="w")
        r += 1
        tk.Label(scrollable_frame, text="Shows a prompt to end the session when cargo is 100% full and has been idle (no cargo changes) for 1 minute. Helps you remember to save your session before unloading cargo.", wraplength=760, justify="left", fg="gray", bg="#1e1e1e",
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
            label = ttk.Label(rowf, text=f"Set timer for {name} [{lo}..{hi}] seconds")
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
        # Pass setting to prospector panel
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel.auto_start_on_prospector = enabled
            # Also sync the checkbox in Mining Analytics tab
            if hasattr(self.prospector_panel, 'auto_start_var'):
                self.prospector_panel.auto_start_var.set(1 if enabled else 0)
        self._set_status(f"Auto-start session on first prospector {'enabled' if enabled else 'disabled'}")

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
        # Pass setting to prospector panel
        if hasattr(self, 'prospector_panel') and self.prospector_panel:
            self.prospector_panel.prompt_on_cargo_full = enabled
            # Also sync the checkbox in Mining Analytics tab
            if hasattr(self.prospector_panel, 'prompt_on_full_var'):
                self.prospector_panel.prompt_on_full_var.set(1 if enabled else 0)
        self._set_status(f"Prompt when cargo full {'enabled' if enabled else 'disabled'}")

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
        
        self.text_overlay_enabled.set(1 if enabled else 0)
        self.text_overlay_transparency.set(transparency)
        self.text_overlay_color.set(color)
        self.text_overlay_position.set(position)
        self.text_overlay_size.set(size)
        self.text_overlay_duration.set(duration)
        
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
            "text_overlay_duration": int(self.text_overlay_duration.get())
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
        try:
            from config import needs_config_migration, migrate_config, _save_cfg
            
            cfg = _load_cfg()
            if needs_config_migration(cfg):
                print("Config migration needed - updating configuration...")
                
                # Backup original config
                import shutil
                from config import CONFIG_FILE
                backup_path = CONFIG_FILE + ".backup"
                try:
                    shutil.copy2(CONFIG_FILE, backup_path)
                    print(f"Backed up original config to: {backup_path}")
                except Exception as e:
                    print(f"Could not create backup: {e}")
                
                # Migrate config
                migrated_config = migrate_config(cfg)
                _save_cfg(migrated_config)
                print("Config successfully migrated!")
            else:
                print("Config is up to date")
                
        except Exception as e:
            print(f"Config migration check failed: {e}")
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
        
        # Clean up text overlay
        if hasattr(self, 'text_overlay'):
            self.text_overlay.destroy()
            
        # Clean up cargo monitor
        if hasattr(self, 'cargo_monitor'):
            self.cargo_monitor.hide()
            self.cargo_monitor.stop_journal_monitoring()
            
        # Clean up matplotlib resources
        try:
            import matplotlib.pyplot as plt
            plt.close('all')
        except:
            pass
            
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
            self.ring_finder = RingFinder(parent_frame, self.prospector_panel, app_dir)
            
            # Check if there were any pending hotspot additions while Ring Finder was being created
            if getattr(self, '_pending_ring_finder_refresh', False):
                self._refresh_ring_finder()
                
        except Exception as e:
            print(f"Ring finder setup failed: {e}")

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
