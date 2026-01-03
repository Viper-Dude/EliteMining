"""
VoiceAttack Process Manager
Manages VoiceAttack process (start/stop/detect)
"""

import psutil
import subprocess
import time
import logging
import winreg
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VAProcessManager:
    """Manage VoiceAttack process"""
    
    def __init__(self):
        self.va_exe = self.find_voiceattack_exe()
        if self.va_exe:
            logger.info(f"Found VoiceAttack at: {self.va_exe}")
        else:
            logger.warning("VoiceAttack installation not found")
    
    def find_voiceattack_exe(self) -> Optional[Path]:
        """
        Find VoiceAttack installation
        
        Returns:
            Path to VoiceAttack.exe or None if not found
        """
        # Check common locations
        common_paths = [
            Path(r"C:\Program Files\VoiceAttack\VoiceAttack.exe"),
            Path(r"C:\Program Files (x86)\VoiceAttack\VoiceAttack.exe"),
            Path(r"D:\SteamLibrary\steamapps\common\VoiceAttack 2\VoiceAttack.exe"),
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\VoiceAttack 2\VoiceAttack.exe"),
        ]
        
        for path in common_paths:
            if path.exists():
                return path
        
        # Check registry
        va_path = self.get_va_path_from_registry()
        if va_path and va_path.exists():
            return va_path
        
        # Check if running and get path from process
        if self.is_running():
            for proc in psutil.process_iter(['name', 'exe']):
                if proc.info['name'] and proc.info['name'].lower() == 'voiceattack.exe':
                    exe_path = Path(proc.info['exe'])
                    if exe_path.exists():
                        return exe_path
        
        return None
    
    def get_va_path_from_registry(self) -> Optional[Path]:
        """Try to get VoiceAttack path from Windows registry"""
        try:
            # Check uninstall registry key
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\VoiceAttack"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                install_location = winreg.QueryValueEx(key, "InstallLocation")[0]
                va_exe = Path(install_location) / "VoiceAttack.exe"
                if va_exe.exists():
                    return va_exe
        except (WindowsError, FileNotFoundError):
            pass
        
        # Try 32-bit registry key
        try:
            key_path = r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\VoiceAttack"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                install_location = winreg.QueryValueEx(key, "InstallLocation")[0]
                va_exe = Path(install_location) / "VoiceAttack.exe"
                if va_exe.exists():
                    return va_exe
        except (WindowsError, FileNotFoundError):
            pass
        
        return None
    
    def is_running(self) -> bool:
        """
        Check if VoiceAttack is running
        
        Returns:
            True if VoiceAttack process is found
        """
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == 'voiceattack.exe':
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    
    def close_voiceattack(self, timeout: int = 10) -> bool:
        """
        Gracefully close VoiceAttack
        
        Args:
            timeout: Seconds to wait for close
        
        Returns:
            True if closed successfully
        """
        if not self.is_running():
            logger.info("VoiceAttack is not running")
            return True
        
        # Find process
        for proc in psutil.process_iter(['name', 'pid']):
            try:
                if proc.info['name'] and proc.info['name'].lower() == 'voiceattack.exe':
                    logger.info(f"Closing VoiceAttack (PID: {proc.info['pid']})")
                    
                    try:
                        # Try graceful close first (sends WM_CLOSE)
                        proc.terminate()
                        proc.wait(timeout=timeout)
                        logger.info("VoiceAttack closed gracefully")
                        return True
                        
                    except psutil.TimeoutExpired:
                        logger.warning("Graceful close timed out, forcing...")
                        proc.kill()
                        proc.wait(timeout=5)
                        logger.info("VoiceAttack force closed")
                        return True
                        
                    except Exception as e:
                        logger.error(f"Failed to close VoiceAttack: {e}")
                        return False
                        
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return False
    
    def start_voiceattack(self, wait_for_start: bool = True) -> bool:
        """
        Start VoiceAttack
        
        Args:
            wait_for_start: Wait for process to start
        
        Returns:
            True if started successfully
        """
        if self.is_running():
            logger.warning("VoiceAttack is already running")
            return True
        
        if not self.va_exe:
            logger.error("VoiceAttack executable not found")
            return False
        
        try:
            # Start VoiceAttack
            logger.info(f"Starting VoiceAttack: {self.va_exe}")
            subprocess.Popen([str(self.va_exe)])
            
            if not wait_for_start:
                return True
            
            # Wait for it to start
            for i in range(15):  # 15 second timeout
                time.sleep(1)
                if self.is_running():
                    logger.info(f"VoiceAttack started successfully (took {i+1}s)")
                    return True
            
            logger.error("VoiceAttack failed to start within timeout")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start VoiceAttack: {e}")
            return False
    
    def get_va_data_path(self) -> Optional[Path]:
        """
        Get VoiceAttack data directory
        
        Returns:
            Path to VoiceAttack data folder
        """
        if not self.va_exe:
            return None
        
        # Data is in same directory as exe
        return self.va_exe.parent
