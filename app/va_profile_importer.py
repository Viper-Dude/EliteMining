"""
VoiceAttack Profile Importer
Automates profile import using UI automation
"""

import logging
import time
import subprocess
from pathlib import Path
from typing import Optional
import pyautogui

logger = logging.getLogger(__name__)


class VAProfileImporter:
    """Automate VoiceAttack profile import using UI automation"""
    
    def __init__(self, va_exe_path: str):
        """
        Initialize importer
        
        Args:
            va_exe_path: Path to VoiceAttack.exe
        """
        self.va_exe = Path(va_exe_path)
        
    def import_profile(self, vap_path: str, timeout: int = 30) -> bool:
        """
        Automatically import profile into VoiceAttack
        
        Uses mouse automation to click Import Profile button
        
        Args:
            vap_path: Path to .VAP file to import
            timeout: Seconds to wait for import to complete
            
        Returns:
            True if successful
        """
        vap_file = Path(vap_path)
        if not vap_file.exists():
            logger.error(f"VAP file not found: {vap_path}")
            return False
        
        try:
            logger.info(f"Importing profile: {vap_path}")
            
            # Step 1: Focus VoiceAttack window
            if not self._focus_voiceattack():
                logger.error("Could not focus VoiceAttack window")
                return False
            
            time.sleep(1)
            
            # Step 2: Try to find "Import Profile" button using OCR or pattern matching
            logger.info("Searching for Import Profile button...")
            
            # Use pyautogui to locate button by image (if we have screenshot)
            # Or try common locations based on VA's default layout
            
            # Alternative: Use accessibility API or UI Automation
            # For now, let's try a simpler approach: use the menu bar
            
            # Click on the profile dropdown/button area (typically top-left area of profile list)
            # This is a guess - we need to find the actual button location
            logger.info("Attempting to access profile menu...")
            
            # Right-click in the profile list area to get context menu
            # Get VoiceAttack window position and size
            import win32gui
            hwnd = win32gui.FindWindow(None, "VoiceAttack")
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                x, y, width, height = rect
                
                # Click in profile list area (rough estimate - left side, middle)
                click_x = x + 150
                click_y = y + 100
                
                logger.info(f"Right-clicking at ({click_x}, {click_y})")
                pyautogui.rightClick(click_x, click_y)
                time.sleep(0.5)
                
                # Look for "Import" in context menu (should be visible)
                # Type 'i' to select Import option
                pyautogui.press('i')
                time.sleep(2)
            
            # Now file dialog should be open
            logger.info("Entering file path...")
            
            # Clear and type path
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.2)
            pyautogui.write(str(vap_file.absolute()), interval=0.02)
            time.sleep(0.5)
            
            # Open file
            logger.info("Confirming import...")
            pyautogui.press('enter')
            time.sleep(2)
            
            # Confirm overwrite if prompted
            pyautogui.press('enter')
            time.sleep(1)
            
            logger.info("Profile import initiated")
            return True
            
        except Exception as e:
            logger.error(f"Failed to import profile: {e}")
            return False
    
    def _focus_voiceattack(self) -> bool:
        """
        Bring VoiceAttack window to foreground
        
        Returns:
            True if successful
        """
        try:
            # Use pyautogui to find and click VoiceAttack window
            # Or use Windows API to bring window to foreground
            
            # Simple approach: Use Alt+Tab to switch to VA
            # Better approach: Use win32gui to find window by title
            
            import win32gui
            import win32con
            
            def callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if "VoiceAttack" in title:
                        windows.append((hwnd, title))
                return True
            
            windows = []
            win32gui.EnumWindows(callback, windows)
            
            if not windows:
                logger.warning("VoiceAttack window not found")
                return False
            
            # Focus first VoiceAttack window found
            hwnd = windows[0][0]
            logger.info(f"Focusing VoiceAttack window: {windows[0][1]}")
            
            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # Bring to foreground
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
            
            return True
            
        except ImportError:
            logger.warning("pywin32 not available, using fallback method")
            # Fallback: just try to start VoiceAttack
            return True
        except Exception as e:
            logger.error(f"Failed to focus VoiceAttack: {e}")
            return False
    
    def import_profile_simple(self, vap_path: str) -> bool:
        """
        Simple import: Just open the file with Windows
        
        The .VAP file should be associated with VoiceAttack and trigger import
        
        Args:
            vap_path: Path to .VAP file
            
        Returns:
            True if file opened successfully
        """
        try:
            import subprocess
            import os
            
            logger.info(f"Opening profile with default application: {vap_path}")
            
            # Use os.startfile (most reliable on Windows)
            os.startfile(vap_path)
            
            logger.info("Profile file opened - VoiceAttack should show import dialog")
            return True
            
        except Exception as e:
            logger.error(f"Failed to open profile file: {e}")
            return False
    
    def delete_profile_from_voiceattack(self, profile_name: str) -> bool:
        """
        Delete a profile from VoiceAttack by clicking through UI
        
        Args:
            profile_name: Name of profile to delete (e.g., "EliteMining Dev 4.7.5-Profile")
            
        Returns:
            True if successful
        """
        try:
            logger.info(f"Attempting to delete profile: {profile_name}")
            
            # Focus VoiceAttack
            if not self._focus_voiceattack():
                logger.error("Could not focus VoiceAttack")
                return False
            
            time.sleep(1)
            
            # Right-click in profile list area to get context menu
            import win32gui
            hwnd = win32gui.FindWindow(None, "VoiceAttack")
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                x, y, width, height = rect
                
                # Click in profile list area (left side)
                click_x = x + 150
                click_y = y + 100
                
                logger.info(f"Right-clicking profile list at ({click_x}, {click_y})")
                pyautogui.rightClick(click_x, click_y)
                time.sleep(0.5)
                
                # Look for "Delete" in context menu
                # Usually 'd' key selects Delete
                pyautogui.press('d')
                time.sleep(1)
                
                # Confirm deletion dialog
                logger.info("Confirming deletion...")
                pyautogui.press('enter')
                time.sleep(1)
                
                logger.info(f"Profile deleted: {profile_name}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete profile: {e}")
            return False
    
    def show_import_instructions(self, vap_path: str) -> bool:
        """
        Show user-friendly import instructions
        
        Args:
            vap_path: Path to updated profile
            
        Returns:
            True if instructions shown
        """
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            # Create hidden root window
            root = tk.Tk()
            root.withdraw()
            
            message = f"""Profile Update Ready!

Your EliteMining profile has been updated with all keybinds preserved.

📂 Updated profile location:
{vap_path}

To complete the update:
1. Click "OK" below to open VoiceAttack
2. In VoiceAttack, import the profile:
   • Right-click in profile list → Import Profile
   • Or use the Import button
3. Select the file (path copied to clipboard!)

Your keybinds are already restored in the new profile!"""
            
            # Copy path to clipboard
            import pyperclip
            pyperclip.copy(vap_path)
            
            messagebox.showinfo("EliteMining Profile Update", message)
            
            root.destroy()
            return True
            
        except Exception as e:
            logger.error(f"Failed to show instructions: {e}")
            return False
