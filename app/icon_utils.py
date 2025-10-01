"""
Icon Utilities for EliteMining
Centralized icon path resolution and window icon setting
"""

import os
import sys
import tkinter as tk
from typing import Optional


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
    
    # Method 4: Hardcoded relative paths (for various deployment scenarios)
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


# Legacy compatibility - keep existing function name for backward compatibility
def get_app_icon_path_legacy() -> str:
    """Legacy function name for backward compatibility"""
    return get_app_icon_path() or ""


# Example usage documentation:
"""
STANDARD USAGE PATTERNS:

1. For new windows/dialogs (RECOMMENDED):
   ```python
   from icon_utils import set_window_icon
   
   dialog = tk.Toplevel()
   dialog.title("My Dialog")
   dialog.geometry("400x300")
   set_window_icon(dialog)  # ← Add this line for consistent icons
   ```

2. For existing code that needs icon path:
   ```python
   from icon_utils import get_app_icon_path
   
   icon_path = get_app_icon_path()
   if icon_path:
       window.iconbitmap(icon_path)  # For .ico files
   ```

3. For classes that need icon functionality:
   ```python
   from icon_utils import set_window_icon
   
   class MyDialog:
       def __init__(self, parent):
           self.dialog = tk.Toplevel(parent)
           self.dialog.title("My Dialog")
           set_window_icon(self.dialog)  # ← Always add this
   ```

COPY-PASTE TEMPLATE for new dialogs:
```python
# Standard dialog setup with icon
dialog = tk.Toplevel(parent)
dialog.title("Dialog Title")
dialog.geometry("WIDTHxHEIGHT")
dialog.transient(parent)
dialog.grab_set()
set_window_icon(dialog)  # ← Handles icon automatically
```

MIGRATION GUIDE:
- Replace all custom icon path logic with `get_app_icon_path()`
- Replace manual icon setting with `set_window_icon(window)`
- Remove duplicate icon search functions from individual modules
- Always test in both development and installer modes
"""