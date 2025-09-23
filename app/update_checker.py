"""
Update checker module for EliteMining
Checks GitHub releases for new versions
"""

import requests
import threading
import time
import json
import os
from pathlib import Path
from packaging import version
import tkinter as tk
from tkinter import messagebox
import webbrowser

class UpdateChecker:
    """Handles checking for application updates"""
    
    def __init__(self, current_version: str, check_url: str, settings_dir: str = None):
        self.current_version = current_version
        self.check_url = check_url
        
        # Use provided settings directory or create one in user's app data
        if settings_dir:
            settings_path = Path(settings_dir)
        else:
            # Fallback to user's local app data
            import os
            app_data = os.path.expanduser("~/.elitemining")
            settings_path = Path(app_data)
        
        settings_path.mkdir(exist_ok=True)
        self.last_check_file = settings_path / "last_update_check.json"
        
    def should_check_for_updates(self, interval_seconds: int = 86400) -> bool:
        """Check if enough time has passed since last update check"""
        try:
            if not self.last_check_file.exists():
                return True
                
            with open(self.last_check_file, 'r') as f:
                data = json.load(f)
                last_check = data.get('last_check', 0)
                
            return time.time() - last_check > interval_seconds
        except:
            return True
    
    def save_last_check_time(self):
        """Save current time as last check time"""
        try:
            data = {'last_check': time.time()}
            with open(self.last_check_file, 'w') as f:
                json.dump(data, f)
        except:
            pass
    
    def check_for_updates_async(self, parent_window=None, show_no_updates=False):
        """Check for updates in background thread"""
        def worker():
            try:
                self._check_for_updates(parent_window, show_no_updates)
            except Exception as e:
                print(f"Update check failed: {e}")
        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
    
    def _check_for_updates(self, parent_window=None, show_no_updates=False):
        """Check GitHub API for latest release"""
        try:
            print(f"Checking for updates... Current version: {self.current_version}")
            
            response = requests.get(self.check_url, timeout=10)
            if response.status_code != 200:
                print(f"Update check failed: HTTP {response.status_code}")
                return
            
            release_data = response.json()
            latest_version = release_data.get('tag_name', '').lstrip('v')
            download_url = None
            
            # Find the .exe file in assets
            for asset in release_data.get('assets', []):
                if asset['name'].endswith('.exe'):
                    download_url = asset['browser_download_url']
                    break
            
            if not download_url:
                # Fallback to release page if no exe found
                download_url = release_data.get('html_url')
            
            self.save_last_check_time()
            
            # Compare versions
            if self._is_newer_version(latest_version, self.current_version):
                # Show update notification
                if parent_window:
                    parent_window.after(0, self._show_update_dialog, 
                                      latest_version, download_url, parent_window)
                else:
                    print(f"Update available: {latest_version}")
            elif show_no_updates:
                if parent_window:
                    parent_window.after(0, self._show_no_updates_dialog, parent_window)
                else:
                    print("No updates available")
            
        except Exception as e:
            print(f"Update check error: {e}")
    
    def _is_newer_version(self, latest: str, current: str) -> bool:
        """Compare version strings"""
        try:
            return version.parse(latest) > version.parse(current)
        except:
            # Fallback to string comparison
            return latest > current
    
    def _show_update_dialog(self, latest_version: str, download_url: str, parent_window):
        """Show update available dialog"""
        try:
            result = messagebox.askyesno(
                "Update Available",
                f"A new version of EliteMining is available!\n\n"
                f"Current version: {self.current_version}\n"
                f"Latest version: {latest_version}\n\n"
                f"Would you like to download the update?",
                parent=parent_window
            )
            
            if result and download_url:
                webbrowser.open(download_url)
        except:
            pass
    
    def _show_no_updates_dialog(self, parent_window):
        """Show no updates available dialog"""
        try:
            messagebox.showinfo(
                "No Updates",
                f"You are running the latest version ({self.current_version})",
                parent=parent_window
            )
        except:
            pass
    
    def manual_check(self, parent_window=None):
        """Manually check for updates (show result regardless)"""
        self.check_for_updates_async(parent_window, show_no_updates=True)