"""
VoiceAttack Profile Parser
Parses .VAP profile files (compressed or XML format)
"""

import xml.etree.ElementTree as ET
import re
import logging
import gzip
import zlib
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class VAProfileParser:
    """Parse VoiceAttack .VAP profile files"""
    
    def parse(self, vap_path: str) -> ET.ElementTree:
        """
        Parse .VAP file (handles both compressed and uncompressed)
        
        Args:
            vap_path: Path to .VAP file
            
        Returns:
            ElementTree of parsed XML
            
        Raises:
            FileNotFoundError: If VAP file doesn't exist
            ET.ParseError: If XML is invalid
        """
        vap_file = Path(vap_path)
        if not vap_file.exists():
            raise FileNotFoundError(f"VAP file not found: {vap_path}")
        
        # Try to detect if file is compressed
        with open(vap_path, 'rb') as f:
            header = f.read(2)
        
        try:
            # Check for gzip magic number (1f 8b)
            if header == b'\x1f\x8b':
                logger.info(f"Detected gzip compressed VAP file: {vap_path}")
                with gzip.open(vap_path, 'rt', encoding='utf-8') as f:
                    xml_content = f.read()
                tree = ET.fromstring(xml_content)
                logger.info(f"Successfully decompressed and parsed VAP file")
                return ET.ElementTree(tree)
            else:
                # Try parsing as plain XML first
                try:
                    logger.info(f"Attempting to parse as uncompressed XML: {vap_path}")
                    tree = ET.parse(vap_path)
                    logger.info(f"Parsed uncompressed VAP file: {vap_path}")
                    return tree
                except ET.ParseError:
                    # Not plain XML, try DEFLATE decompression
                    logger.info(f"Not plain XML, trying DEFLATE decompression...")
                    with open(vap_path, 'rb') as f:
                        compressed_data = f.read()
                    
                    try:
                        # Try raw DEFLATE decompression
                        decompressed = zlib.decompress(compressed_data)
                        xml_content = decompressed.decode('utf-8')
                        tree = ET.fromstring(xml_content)
                        logger.info(f"Successfully decompressed with DEFLATE: {vap_path}")
                        return ET.ElementTree(tree)
                    except zlib.error:
                        # Try with -zlib.MAX_WBITS (raw deflate)
                        try:
                            decompressed = zlib.decompress(compressed_data, -zlib.MAX_WBITS)
                            xml_content = decompressed.decode('utf-8')
                            tree = ET.fromstring(xml_content)
                            logger.info(f"Successfully decompressed with raw DEFLATE: {vap_path}")
                            return ET.ElementTree(tree)
                        except Exception as e:
                            logger.error(f"Failed all decompression methods: {e}")
                            raise Exception(f"Cannot decompress VAP file. Try exporting as uncompressed XML from VoiceAttack.")
        except ET.ParseError as e:
            logger.error(f"Failed to parse VAP file: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reading VAP file: {e}")
            raise
    
    def get_profile_name(self, tree: ET.ElementTree) -> str:
        """
        Extract profile name from XML
        
        Args:
            tree: Parsed XML tree
            
        Returns:
            Profile name
        """
        profile = tree.getroot()
        name_elem = profile.find("Name")
        if name_elem is not None and name_elem.text:
            return name_elem.text
        return "Unknown Profile"
    
    def get_profile_version(self, tree: ET.ElementTree) -> str:
        """
        Extract profile version from XML
        
        Args:
            tree: Parsed XML tree
            
        Returns:
            Version string (e.g., "4.7.5")
        """
        profile = tree.getroot()
        
        # Look for custom version element
        version_elem = profile.find(".//Version")
        if version_elem is not None and version_elem.text:
            return version_elem.text
        
        # Parse from profile name: "EliteMining v4.76" or "EliteMining Dev 4.7.5-Profile"
        name = self.get_profile_name(tree)
        match = re.search(r'v?(\d+\.\d+(?:\.\d+)?)', name)
        if match:
            version = match.group(1)
            logger.info(f"Extracted version from name: {version}")
            return version
        
        logger.warning("Could not determine profile version")
        return "unknown"
    
    def get_all_commands(self, tree: ET.ElementTree) -> List[ET.Element]:
        """
        Get all Command elements
        
        Args:
            tree: Parsed XML tree
            
        Returns:
            List of Command elements
        """
        commands = tree.findall(".//Command")
        logger.info(f"Found {len(commands)} commands in profile")
        return commands
    
    def get_command_count(self, tree: ET.ElementTree) -> int:
        """
        Get total number of commands
        
        Args:
            tree: Parsed XML tree
            
        Returns:
            Number of commands
        """
        return len(self.get_all_commands(tree))
    
    def save(self, tree: ET.ElementTree, output_path: str, compress: bool = True):
        """
        Save XML tree to file
        
        Args:
            tree: XML tree to save
            output_path: Path to save to
            compress: Whether to compress (gzip) the output
        """
        if compress:
            # Save as compressed (VoiceAttack default format)
            xml_str = ET.tostring(tree.getroot(), encoding='utf-8', xml_declaration=True)
            with gzip.open(output_path, 'wb') as f:
                f.write(xml_str)
            logger.info(f"Saved compressed profile to: {output_path}")
        else:
            # Save as plain XML
            tree.write(output_path, encoding='utf-8', xml_declaration=True)
            logger.info(f"Saved uncompressed profile to: {output_path}")
