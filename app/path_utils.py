"""
Centralized path utilities for EliteMining
Handles differences between development and installer environments

CRITICAL: All user data paths MUST go through these functions to ensure:
1. Correct location in dev vs installer mode
2. User data preservation during updates
3. Proper backup/restore functionality

USER DATA PATHS (must be preserved):
- Ship Presets: get_ship_presets_dir()
- Reports: get_reports_dir()
- Bookmarks: get_bookmarks_file()

APP RESOURCE PATHS (can be overwritten):
- Images: get_images_dir()
"""
import os
import sys

def get_app_data_dir():
    """Get the writable app data directory for both dev and installer"""
    if getattr(sys, 'frozen', False):
        # Installer version - try multiple methods to find the app directory
        va_root = os.environ.get('VA_ROOT')
        if va_root:
            return os.path.join(va_root, "app")
        else:
            # Fallback: use executable directory
            # In PyInstaller, sys.executable points to the .exe file
            # Structure: ...\EliteMining\Configurator\Configurator.exe
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

def get_ship_presets_dir():
    """
    Get ship presets directory - ensures user presets are preserved
    User data location that should NOT be overwritten during updates
    """
    if getattr(sys, 'frozen', False):
        # Installer version - use VA root
        va_root = os.environ.get('VA_ROOT')
        if va_root:
            presets_dir = os.path.join(va_root, "app", "Ship Presets")
            # Ensure directory exists
            os.makedirs(presets_dir, exist_ok=True)
            return presets_dir
    else:
        # Development version - use local folder
        presets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Ship Presets")
        os.makedirs(presets_dir, exist_ok=True)
        return presets_dir
    
    # Fallback - should rarely be used
    presets_dir = os.path.join(get_app_data_dir(), "Ship Presets")
    os.makedirs(presets_dir, exist_ok=True)
    return presets_dir

def get_reports_dir():
    """
    Get reports directory - user's mining session reports
    User data location that should NOT be overwritten during updates
    Protected by backup/restore system during updates
    """
    reports_dir = os.path.join(get_app_data_dir(), "Reports", "Mining Session")
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir

def get_bookmarks_file():
    """
    Get path to mining bookmarks JSON file
    User data file that should NOT be overwritten during updates
    Protected by backup/restore system during updates
    """
    return os.path.join(get_app_data_dir(), "mining_bookmarks.json")

def get_images_dir():
    """
    Get images directory for app assets (logos, icons, etc.)
    These are app resources, NOT user data
    """
    return os.path.join(get_app_data_dir(), "Images")