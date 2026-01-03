"""
VoiceAttack Export Helper
Manages one-time XML export setup for keybind preservation
"""

import logging
import json
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VAExportHelper:
    """Helper for managing VA profile XML export"""
    
    def __init__(self, app_data_path: str):
        """
        Initialize export helper
        
        Args:
            app_data_path: Path to app data directory
        """
        self.app_data_path = Path(app_data_path)
        self.config_file = self.app_data_path / "va_export_config.json"
        self.app_data_path.mkdir(parents=True, exist_ok=True)
    
    def get_saved_export_path(self) -> Optional[str]:
        """
        Get path to saved XML export
        
        Returns:
            Path to XML export or None if not configured
        """
        if not self.config_file.exists():
            return None
        
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                export_path = config.get('xml_export_path')
                
                if export_path and Path(export_path).exists():
                    logger.info(f"Found saved export: {export_path}")
                    return export_path
                else:
                    logger.warning(f"Saved export path invalid or missing: {export_path}")
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to read export config: {e}")
            return None
    
    def save_export_path(self, export_path: str):
        """
        Save path to XML export for future use
        
        Args:
            export_path: Path to exported XML profile
        """
        try:
            config = {
                'xml_export_path': export_path,
                'profile_name': self._extract_profile_name(export_path)
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Saved export path: {export_path}")
            
        except Exception as e:
            logger.error(f"Failed to save export config: {e}")
            raise
    
    def is_export_configured(self) -> bool:
        """
        Check if XML export is configured and valid
        
        Returns:
            True if export is configured and file exists
        """
        export_path = self.get_saved_export_path()
        return export_path is not None and Path(export_path).exists()
    
    def get_export_instructions(self) -> str:
        """
        Get instructions for exporting profile
        
        Returns:
            Multi-line instruction string
        """
        return """To enable automatic keybind preservation:

1. Open VoiceAttack
2. Select your EliteMining profile
3. Click the profile dropdown (▼) next to the profile name
4. Select "Export Profile"
5. Check "Export as uncompressed (larger file)"
6. Save as: EliteMining-Keybinds.vap
7. Click "Save Export Path" in this dialog

This is a one-time setup. Future updates will preserve keybinds automatically."""
    
    def _extract_profile_name(self, xml_path: str) -> Optional[str]:
        """Extract profile name from XML file"""
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(xml_path)
            root = tree.getroot()
            name_elem = root.find('Name')
            if name_elem is not None:
                return name_elem.text
        except Exception as e:
            logger.error(f"Failed to extract profile name: {e}")
        
        return None
    
    def suggest_export_location(self) -> str:
        """
        Suggest default export location
        
        Returns:
            Suggested path for XML export
        """
        return str(self.app_data_path / "EliteMining-Keybinds.vap")
    
    def reset_export_config(self):
        """Remove saved export configuration"""
        if self.config_file.exists():
            self.config_file.unlink()
            logger.info("Reset export configuration")
