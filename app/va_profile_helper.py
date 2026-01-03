"""
VoiceAttack Profile Helper Wrapper
Uses C# tool to read/write VA binary profiles
"""

import logging
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class VAProfileHelper:
    """Wrapper for VAProfileHelper.exe C# tool"""
    
    def __init__(self):
        """Initialize helper"""
        self.helper_exe = Path(__file__).parent.parent / "tools" / "VAProfileHelper" / "bin" / "Release" / "net48" / "VAProfileHelper.exe"
        
        if not self.helper_exe.exists():
            logger.warning(f"VAProfileHelper not found at: {self.helper_exe}")
            logger.info("Run: dotnet build tools/VAProfileHelper.csproj -c Release")
    
    def export_keybinds(self, vap_path: str, output_json: str) -> bool:
        """
        Export keybinds from VAP file (any format)
        
        Args:
            vap_path: Path to .VAP file (compressed or XML)
            output_json: Path to output JSON file
            
        Returns:
            True if successful
        """
        if not self.helper_exe.exists():
            logger.error("VAProfileHelper.exe not built")
            return False
        
        try:
            logger.info(f"Exporting keybinds using C# helper...")
            
            result = subprocess.run(
                [str(self.helper_exe), "export", vap_path, output_json],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully exported keybinds to: {output_json}")
                logger.debug(result.stdout)
                return True
            else:
                logger.error(f"Export failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to run helper: {e}")
            return False
    
    def import_keybinds(self, vap_path: str, keybinds_json: str, output_vap: str) -> bool:
        """
        Import keybinds to VAP file
        
        Args:
            vap_path: Path to source .VAP file
            keybinds_json: Path to keybinds JSON
            output_vap: Path to output .VAP file
            
        Returns:
            True if successful
        """
        if not self.helper_exe.exists():
            logger.error("VAProfileHelper.exe not built")
            return False
        
        try:
            logger.info(f"Importing keybinds using C# helper...")
            
            result = subprocess.run(
                [str(self.helper_exe), "import", vap_path, keybinds_json, output_vap],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully imported keybinds to: {output_vap}")
                logger.debug(result.stdout)
                return True
            else:
                logger.error(f"Import failed: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to run helper: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if helper tool is available"""
        return self.helper_exe.exists()
