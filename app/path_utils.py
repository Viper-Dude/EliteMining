"""
Centralized path utilities for EliteMining
Handles differences between development and installer environments
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

def get_ship_presets_dir():
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

def get_reports_dir():
    """Get reports directory"""
    return os.path.join(get_app_data_dir(), "Reports", "Mining Session")