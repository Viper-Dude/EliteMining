"""
VoiceAttack Database Access
Direct manipulation of VoiceAttack.dat database file
"""

import logging
import struct
import shutil
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


class VADatabaseError(Exception):
    """VoiceAttack database operation error"""
    pass


class VADatabase:
    """Direct access to VoiceAttack.dat database"""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize database access
        
        Args:
            db_path: Path to VoiceAttack.dat (if None, uses default location)
        """
        if db_path:
            self.db_path = Path(db_path)
        else:
            # Default location: %APPDATA%\VoiceAttack\VoiceAttack.dat
            appdata = Path.home() / "AppData" / "Roaming" / "VoiceAttack"
            self.db_path = appdata / "VoiceAttack.dat"
        
        logger.info(f"VA Database path: {self.db_path}")
    
    def exists(self) -> bool:
        """Check if database exists"""
        return self.db_path.exists()
    
    def backup(self) -> Path:
        """
        Create backup of database
        
        Returns:
            Path to backup file
        """
        if not self.exists():
            raise VADatabaseError(f"Database not found: {self.db_path}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.db_path.parent / f"VoiceAttack-{timestamp}.dat.backup"
        
        shutil.copy2(self.db_path, backup_path)
        logger.info(f"Database backed up to: {backup_path}")
        
        return backup_path
    
    def restore(self, backup_path: Path):
        """Restore database from backup"""
        shutil.copy2(backup_path, self.db_path)
        logger.info(f"Database restored from: {backup_path}")
    
    def analyze_structure(self) -> Dict:
        """
        Analyze database structure
        
        Returns:
            Dict with database info
        """
        if not self.exists():
            raise VADatabaseError(f"Database not found: {self.db_path}")
        
        with open(self.db_path, 'rb') as f:
            data = f.read()
        
        info = {
            'size': len(data),
            'header': data[:32].hex(),
            'format': 'Unknown'
        }
        
        # Check for .NET binary serialization marker
        if data[0:1] == b'\x00':
            info['format'] = 'Possible .NET Binary Serialization'
        
        # Look for XML markers (profiles might be stored as XML)
        if b'<?xml' in data:
            info['contains_xml'] = True
            xml_count = data.count(b'<?xml')
            info['xml_sections'] = xml_count
            logger.info(f"Found {xml_count} XML sections in database")
        else:
            info['contains_xml'] = False
        
        # Look for profile names
        if b'EliteMining' in data:
            info['contains_elitemining'] = True
            logger.info("Found EliteMining profile in database")
        
        return info
    
    def extract_profiles(self) -> List[Dict]:
        """
        Extract all profiles from database
        
        Returns:
            List of profile dictionaries
        """
        if not self.exists():
            raise VADatabaseError(f"Database not found: {self.db_path}")
        
        with open(self.db_path, 'rb') as f:
            data = f.read()
        
        profiles = []
        
        # Find all XML sections (each likely a profile)
        start_marker = b'<?xml'
        pos = 0
        
        while True:
            pos = data.find(start_marker, pos)
            if pos == -1:
                break
            
            # Find end of XML (look for closing Profile tag)
            end_pos = data.find(b'</Profile>', pos)
            if end_pos == -1:
                logger.warning(f"XML section at {pos} has no closing tag")
                pos += len(start_marker)
                continue
            
            end_pos += len(b'</Profile>')
            
            # Extract XML
            xml_data = data[pos:end_pos]
            
            try:
                # Parse XML
                root = ET.fromstring(xml_data)
                
                # Extract profile name
                name_elem = root.find('Name')
                profile_name = name_elem.text if name_elem is not None else "Unknown"
                
                profiles.append({
                    'name': profile_name,
                    'offset': pos,
                    'length': end_pos - pos,
                    'xml': xml_data
                })
                
                logger.info(f"Found profile: {profile_name} at offset {pos}")
                
            except ET.ParseError as e:
                logger.warning(f"Failed to parse XML at offset {pos}: {e}")
            
            pos = end_pos
        
        return profiles
    
    def get_profile(self, profile_name: str) -> Optional[bytes]:
        """
        Get profile XML by name
        
        Args:
            profile_name: Name of profile to extract
            
        Returns:
            Profile XML as bytes, or None if not found
        """
        profiles = self.extract_profiles()
        
        for profile in profiles:
            if profile['name'] == profile_name or profile_name in profile['name']:
                return profile['xml']
        
        logger.warning(f"Profile not found: {profile_name}")
        return None
    
    def update_profile(self, profile_name: str, new_xml: bytes) -> bool:
        """
        Update profile in database
        
        Args:
            profile_name: Name of profile to update
            new_xml: New profile XML
            
        Returns:
            True if successful
        """
        if not self.exists():
            raise VADatabaseError(f"Database not found: {self.db_path}")
        
        # Backup first
        backup_path = self.backup()
        
        try:
            # Read entire database
            with open(self.db_path, 'rb') as f:
                data = bytearray(f.read())
            
            # Find profile
            profiles = self.extract_profiles()
            target_profile = None
            
            for profile in profiles:
                if profile['name'] == profile_name or profile_name in profile['name']:
                    target_profile = profile
                    break
            
            if not target_profile:
                raise VADatabaseError(f"Profile not found: {profile_name}")
            
            # Replace profile XML
            old_length = target_profile['length']
            new_length = len(new_xml)
            offset = target_profile['offset']
            
            logger.info(f"Updating profile '{profile_name}' at offset {offset}")
            logger.info(f"Old size: {old_length}, New size: {new_length}")
            
            # Replace data
            data[offset:offset+old_length] = new_xml
            
            # Write back to database
            with open(self.db_path, 'wb') as f:
                f.write(data)
            
            logger.info(f"Profile '{profile_name}' updated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update profile: {e}")
            # Restore backup on failure
            self.restore(backup_path)
            raise VADatabaseError(f"Profile update failed: {e}")
    
    def get_profile_xml_tree(self, profile_name: str) -> Optional[ET.ElementTree]:
        """
        Get profile as XML tree
        
        Args:
            profile_name: Name of profile
            
        Returns:
            ElementTree or None
        """
        xml_data = self.get_profile(profile_name)
        if not xml_data:
            return None
        
        try:
            root = ET.fromstring(xml_data)
            return ET.ElementTree(root)
        except ET.ParseError as e:
            logger.error(f"Failed to parse profile XML: {e}")
            return None
