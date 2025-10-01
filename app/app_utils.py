"""
Centralized Application Utilities for EliteMining
Handles paths, icons, and other common functions for both development and installer environments
"""

import os
import sys
import tkinter as tk
from typing import Optional


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
            # We want the directory containing the app folder
            exe_dir = os.path.dirname(sys.executable)
            # Check if we're in an app subdirectory
            if os.path.basename(exe_dir).lower() == 'app':
                return exe_dir  # We're already in the app directory
            else:
                # We're in the root, app directory should be a subdirectory
                app_dir = os.path.join(exe_dir, "app")
                if os.path.exists(app_dir):
                    return app_dir
                else:
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