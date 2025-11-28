"""
Centralized Application Utilities for EliteMining
Handles paths, icons, and other common functions for both development and installer environments
"""

import os
import sys
import tkinter as tk
from typing import Optional
from typing import Any
import datetime as dt
from tkinter import ttk, messagebox
import tkinter as tk


# ==================== PATH UTILITIES ====================

def get_app_data_dir() -> str:
    """
    Get the writable app data directory for both dev and installer.
    
    This is the CANONICAL function for app directory resolution.
    All other code should use this function for consistent path handling.
    
    Returns:
        Path to the app data directory
    """
    if getattr(sys, 'frozen', False):
        # Installer version - try multiple methods to find the app directory
        va_root = os.environ.get('VA_ROOT')
        if va_root:
            return os.path.join(va_root, "app")
        else:
            # Fallback: use executable directory
            # In PyInstaller, sys.executable points to the .exe file
            # Structure: ...\EliteMining\Configurator\EliteMining.exe
            # We need: ...\EliteMining\app\
            exe_dir = os.path.dirname(sys.executable)
            
            # Check if we're in the Configurator subdirectory
            if os.path.basename(exe_dir).lower() == 'configurator':
                # Go up one level to EliteMining, then into app
                parent_dir = os.path.dirname(exe_dir)  # EliteMining folder
                app_dir = os.path.join(parent_dir, "app")
                if os.path.exists(app_dir):
                    return app_dir
            
            # Check if we're in an app subdirectory
            if os.path.basename(exe_dir).lower() == 'app':
                return exe_dir  # We're already in the app directory
            
            # Try app folder as subdirectory of current location
            app_dir = os.path.join(exe_dir, "app")
            if os.path.exists(app_dir):
                return app_dir
            
            # Last resort - use exe directory itself
            return exe_dir
    else:
        # Development version - use actual app directory
        return os.path.dirname(os.path.abspath(__file__))


def get_ship_presets_dir() -> str:
    """Get ship presets directory"""
    if getattr(sys, 'frozen', False):
        # Installer version - use VA root
        va_root = os.environ.get('VA_ROOT')
        if va_root:
            return os.path.join(va_root, "app", "Ship Presets")
    else:
        # Development version - use local folder
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ship Presets")
    
    # Fallback
    return os.path.join(get_app_data_dir(), "Ship Presets")


def get_reports_dir() -> str:
    """Get reports directory"""
    return os.path.join(get_app_data_dir(), "Reports", "Mining Session")


def get_data_dir() -> str:
    """Get the data directory for databases and static files"""
    return os.path.join(get_app_data_dir(), "data")


def get_variables_dir() -> str:
    """
    Get the Variables directory for VoiceAttack integration.
    
    In installer mode: Uses VA_ROOT from environment (VoiceAttack installation)
    In dev mode: Uses local Variables folder in dev directory
    
    Returns:
        Path to the Variables directory
    """
    if getattr(sys, 'frozen', False):
        # Installer version - use VA root from environment
        va_root = os.environ.get('VA_ROOT')
        if va_root:
            return os.path.join(va_root, "Variables")
        # Fallback: construct from app dir
        return os.path.join(os.path.dirname(get_app_data_dir()), "Variables")
    else:
        # Development version - use local Variables folder
        app_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(app_dir, "Variables")


# ==================== ICON UTILITIES ====================

def get_app_icon_path() -> Optional[str]:
    """
    Get the path to the application icon, handling both development and compiled environments.
    
    This is the CANONICAL function for icon path resolution. All other code should use this
    function to ensure consistent icon handling across development and installer modes.
    
    Returns:
        Path to icon file if found, None otherwise
    """
    # Try multiple approaches to find the icon
    search_paths = []
    
    # Method 1: Use __file__ if available (development) or _MEIPASS (PyInstaller)
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
    
    # Method 4: App data directory and parent directories
    try:
        app_dir = get_app_data_dir()
        search_paths.extend([
            app_dir,
            os.path.dirname(app_dir),  # Parent of app dir
            os.path.join(app_dir, "Images"),
            os.path.join(os.path.dirname(app_dir), "Images")
        ])
    except:
        pass
    
    # Method 5: Hardcoded relative paths (for various deployment scenarios)
    search_paths.extend(['.', 'app', '..', '../app'])
    
    # Try each path with different icon names and subdirectories
    icon_names = ['logo.ico', 'logo_multi.ico', 'logo.png']
    subdirectories = ['Images', 'images', 'img', '']  # Empty string for base path
    
    for base_path in search_paths:
        for subdir in subdirectories:
            for icon_name in icon_names:
                if subdir:
                    icon_path = os.path.join(base_path, subdir, icon_name)
                else:
                    icon_path = os.path.join(base_path, icon_name)
                    
                if os.path.exists(icon_path):
                    return icon_path
    
    return None


def set_window_icon(window: tk.Tk | tk.Toplevel) -> bool:
    """
    Set the icon for a Tkinter window using the standard app icon.
    
    This function should be used by ALL windows and dialogs to ensure consistent
    icon handling. It automatically handles .ico vs .png files and fallbacks.
    
    Args:
        window: The Tkinter window or dialog to set the icon for
        
    Returns:
        True if icon was set successfully, False otherwise
    """
    try:
        icon_path = get_app_icon_path()
        if not icon_path:
            return False
            
        if icon_path.endswith('.ico'):
            # Use iconbitmap for .ico files (Windows standard)
            window.iconbitmap(icon_path)
        else:
            # Use iconphoto for .png files (cross-platform)
            icon_image = tk.PhotoImage(file=icon_path)
            window.iconphoto(False, icon_image)
        
        return True
        
    except Exception:
        # Icon setting failed, but don't crash the application
        return False


# ==================== Centered Dialog Helpers ====================
def _center_child_over_parent(child: tk.Toplevel, parent: Optional[tk.Widget]) -> None:
    try:
        if parent:
            parent.update_idletasks()
            child.update_idletasks()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            cw = child.winfo_width()
            ch = child.winfo_height()
            x = px + (pw - cw) // 2
            y = py + (ph - ch) // 2
        else:
            child.update_idletasks()
            sw = child.winfo_screenwidth()
            sh = child.winfo_screenheight()
            cw = child.winfo_width()
            ch = child.winfo_height()
            x = (sw - cw) // 2
            y = (sh - ch) // 2
        child.geometry(f"+{x}+{y}")
    except Exception:
        try:
            # Best-effort fallback
            child.geometry(f"+{(child.winfo_screenwidth() // 2) - 200}+{(child.winfo_screenheight() // 2) - 100}")
        except Exception:
            pass


def centered_message(parent: Optional[tk.Widget], title: str, message: str, icon: str = 'info') -> None:
    """Show a centered info/warning/error dialog. Icon can be 'info', 'warning', or 'error'."""
    from tkinter import ttk
    
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.resizable(False, False)
    set_window_icon(dialog)
    
    # Use ttk frame for themed look
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)
    
    ttk.Label(frame, text=message, font=("Segoe UI", 10), wraplength=420, justify="left").pack(pady=(0, 15))
    
    btn_frame = ttk.Frame(frame)
    btn_frame.pack()
    
    def on_ok():
        dialog.destroy()
    
    ok_btn = ttk.Button(btn_frame, text="OK", width=12, command=on_ok)
    ok_btn.pack()
    
    # Keyboard binding
    dialog.bind("<Return>", lambda e: on_ok())
    dialog.bind("<Escape>", lambda e: on_ok())
    
    # Center on parent window manually
    dialog.update_idletasks()
    dialog_width = dialog.winfo_reqwidth()
    dialog_height = dialog.winfo_reqheight()
    
    if parent:
        parent.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
    else:
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
    
    dialog.geometry(f"+{x}+{y}")
    dialog.deiconify()
    dialog.transient(parent)
    dialog.grab_set()
    dialog.attributes('-topmost', True)
    dialog.lift()
    ok_btn.focus_set()
    dialog.wait_window()


def centered_askyesno(parent: Optional[tk.Widget], title: str, message: str) -> bool:
    """Show a centered Yes/No dialog and return True if Yes."""
    from tkinter import ttk
    
    dialog = tk.Toplevel(parent)
    dialog.withdraw()
    dialog.title(title)
    dialog.resizable(False, False)
    set_window_icon(dialog)
    
    # Use ttk frame for themed look
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)
    
    ttk.Label(frame, text=message, font=("Segoe UI", 10), wraplength=420, justify="left").pack(pady=(0, 15))
    
    btn_frame = ttk.Frame(frame)
    btn_frame.pack()
    
    result = {'value': False}
    def on_yes():
        result['value'] = True
        dialog.destroy()
    def on_no():
        result['value'] = False
        dialog.destroy()
    
    yes_btn = ttk.Button(btn_frame, text="Yes", width=10, command=on_yes)
    yes_btn.pack(side=tk.LEFT, padx=(0, 10))
    no_btn = ttk.Button(btn_frame, text="No", width=10, command=on_no)
    no_btn.pack(side=tk.LEFT)
    
    # Keyboard bindings
    dialog.bind("<Return>", lambda e: on_yes())
    dialog.bind("<Escape>", lambda e: on_no())
    
    # Center on parent window manually
    dialog.update_idletasks()
    dialog_width = dialog.winfo_reqwidth()
    dialog_height = dialog.winfo_reqheight()
    
    if parent:
        parent.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
    else:
        x = (dialog.winfo_screenwidth() - dialog_width) // 2
        y = (dialog.winfo_screenheight() - dialog_height) // 2
    
    dialog.geometry(f"+{x}+{y}")
    dialog.deiconify()
    dialog.transient(parent)
    dialog.grab_set()
    dialog.attributes('-topmost', True)
    dialog.lift()
    yes_btn.focus_set()
    dialog.wait_window()
    return result['value']


# ==================== LEGACY COMPATIBILITY ====================

# Keep old function names for backward compatibility during migration
def get_app_icon_path_legacy() -> str:
    """Legacy function name for backward compatibility"""
    return get_app_icon_path() or ""


# ==================== USAGE EXAMPLES ====================
"""
STANDARD USAGE PATTERNS:

1. For app data paths:
   ```python
   from app_utils import get_app_data_dir, get_data_dir
   
   config_path = os.path.join(get_app_data_dir(), "config.json")
   db_path = os.path.join(get_data_dir(), "user_data.db")
   ```

2. For new windows/dialogs (RECOMMENDED):
   ```python
   from app_utils import set_window_icon
   
   dialog = tk.Toplevel()
   dialog.title("My Dialog")
   dialog.geometry("400x300")
   set_window_icon(dialog)  # ← Add this line for consistent icons
   ```

3. For existing code that needs icon path:
   ```python
   from app_utils import get_app_icon_path
   
   icon_path = get_app_icon_path()
   if icon_path:
       window.iconbitmap(icon_path)  # For .ico files
   ```

COPY-PASTE TEMPLATE for new dialogs:
```python
from app_utils import set_window_icon

# Standard dialog setup with icon
dialog = tk.Toplevel(parent)
dialog.title("Dialog Title")
dialog.geometry("WIDTHxHEIGHT")
dialog.transient(parent)
dialog.grab_set()
set_window_icon(dialog)  # ← Handles icon automatically
```

MIGRATION CHECKLIST:
□ Replace custom path logic with get_app_data_dir()
□ Replace custom icon logic with get_app_icon_path() or set_window_icon()
□ Remove duplicate utility functions from individual modules
□ Test in both development and installer modes
□ Update imports to use app_utils instead of individual modules
"""