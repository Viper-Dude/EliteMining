"""
VoiceAttack Keybind Manager via Plugin
Uses VA plugin commands to export/import keybinds
"""

import logging
import time
import json
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class VAKeybindManager:
    """Manage keybinds through VoiceAttack plugin commands"""
    
    def __init__(self, variables_path: str):
        """
        Initialize keybind manager
        
        Args:
            variables_path: Path to Variables folder (VA_APPS/EliteMining/Variables)
        """
        self.variables_path = Path(variables_path)
        self.keybinds_file = self.variables_path / "elitemining_keybinds.json"
        self.command_file = self.variables_path / "eliteMiningCommand.txt"
        
    def export_keybinds(self, timeout: int = 30) -> bool:
        """
        Export all keybinds from active profile
        
        This triggers the VA plugin which executes a VA command
        that exports keybinds to JSON file.
        
        Args:
            timeout: Seconds to wait for export
            
        Returns:
            True if successful
        """
        try:
            logger.info("Requesting keybind export from VoiceAttack...")
            
            # Clear status files
            status_file = self.variables_path / "keybind_export_status.txt"
            if status_file.exists():
                status_file.unlink()
            
            # Trigger plugin command
            # Plugin will execute VA command: ((Export All Keybinds))
            self._write_command("PLUGIN:EXPORT_KEYBINDS")
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < timeout:
                if status_file.exists():
                    status = status_file.read_text().strip()
                    if status == "SUCCESS":
                        logger.info("Keybinds exported successfully")
                        
                        # Verify keybinds file exists
                        if self.keybinds_file.exists():
                            return True
                        else:
                            logger.error("Export succeeded but keybinds file not found")
                            return False
                    else:
                        logger.error(f"Export failed: {status}")
                        return False
                
                time.sleep(0.5)
            
            logger.error("Keybind export timed out")
            return False
            
        except Exception as e:
            logger.error(f"Failed to export keybinds: {e}")
            return False
    
    def import_keybinds(self, keybinds_data: Dict, timeout: int = 30) -> bool:
        """
        Import keybinds to active profile
        
        Args:
            keybinds_data: Dict of keybinds to import
            timeout: Seconds to wait for import
            
        Returns:
            True if successful
        """
        try:
            logger.info(f"Importing {len(keybinds_data)} keybinds to VoiceAttack...")
            
            # Write keybinds to file
            with open(self.keybinds_file, 'w') as f:
                json.dump(keybinds_data, f, indent=2)
            
            # Clear status file
            status_file = self.variables_path / "keybind_import_status.txt"
            if status_file.exists():
                status_file.unlink()
            
            # Trigger plugin command
            # Plugin will execute VA command: ((Import All Keybinds))
            self._write_command("PLUGIN:IMPORT_KEYBINDS")
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < timeout:
                if status_file.exists():
                    status = status_file.read_text().strip()
                    if status == "SUCCESS":
                        logger.info("Keybinds imported successfully")
                        return True
                    else:
                        logger.error(f"Import failed: {status}")
                        return False
                
                time.sleep(0.5)
            
            logger.error("Keybind import timed out")
            return False
            
        except Exception as e:
            logger.error(f"Failed to import keybinds: {e}")
            return False
    
    def load_keybinds(self) -> Optional[Dict]:
        """
        Load keybinds from exported file
        
        Returns:
            Dict of keybinds or None
        """
        try:
            if not self.keybinds_file.exists():
                logger.warning(f"Keybinds file not found: {self.keybinds_file}")
                return None
            
            with open(self.keybinds_file, 'r') as f:
                keybinds = json.load(f)
            
            logger.info(f"Loaded {len(keybinds)} keybinds from file")
            return keybinds
            
        except Exception as e:
            logger.error(f"Failed to load keybinds: {e}")
            return None
    
    def _write_command(self, command: str):
        """Write command to file for VA to process"""
        self.variables_path.mkdir(parents=True, exist_ok=True)
        with open(self.command_file, 'w') as f:
            f.write(command)
        logger.debug(f"Wrote command: {command}")
