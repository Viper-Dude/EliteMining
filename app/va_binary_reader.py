"""
VoiceAttack Binary Profile Reader using .NET
Reads compressed .VAP files using .NET BinaryFormatter
"""

import logging
import clr
import sys
from pathlib import Path
from io import BytesIO

logger = logging.getLogger(__name__)

# Add .NET assemblies
clr.AddReference("System")
clr.AddReference("mscorlib")

from System.IO import FileStream, FileMode, MemoryStream
from System.Runtime.Serialization.Formatters.Binary import BinaryFormatter
from System import Array, Byte


class VABinaryReader:
    """Read VoiceAttack binary format using .NET"""
    
    def read_vap(self, vap_path: str) -> str:
        """
        Read compressed .VAP file and extract XML
        
        Args:
            vap_path: Path to .VAP file
            
        Returns:
            Profile XML as string
        """
        try:
            logger.info(f"Reading binary VAP with .NET: {vap_path}")
            
            # Open file stream
            file_stream = FileStream(vap_path, FileMode.Open)
            
            try:
                # Try to deserialize using BinaryFormatter
                formatter = BinaryFormatter()
                obj = formatter.Deserialize(file_stream)
                
                logger.info(f"Deserialized object type: {obj.GetType()}")
                
                # The object might contain XML as a property
                # Common properties: Xml, XmlData, ProfileXml, Data
                for prop_name in ['Xml', 'XmlData', 'ProfileXml', 'Data', 'ToString']:
                    try:
                        prop = obj.GetType().GetProperty(prop_name)
                        if prop:
                            value = prop.GetValue(obj, None)
                            if value and isinstance(value, str) and '<?xml' in value:
                                logger.info(f"Found XML in property: {prop_name}")
                                return value
                    except:
                        pass
                
                # Try ToString()
                xml_str = str(obj)
                if '<?xml' in xml_str:
                    logger.info("Found XML via ToString()")
                    return xml_str
                
                logger.error("Could not find XML in deserialized object")
                return None
                
            finally:
                file_stream.Close()
                
        except Exception as e:
            logger.error(f"Failed to read binary VAP: {e}")
            raise
    
    def read_database(self, db_path: str) -> list:
        """
        Read profiles from VoiceAttack.dat
        
        Args:
            db_path: Path to VoiceAttack.dat
            
        Returns:
            List of profile XML strings
        """
        try:
            logger.info(f"Reading VoiceAttack database: {db_path}")
            
            file_stream = FileStream(db_path, FileMode.Open)
            
            try:
                formatter = BinaryFormatter()
                obj = formatter.Deserialize(file_stream)
                
                logger.info(f"Database object type: {obj.GetType()}")
                
                # VoiceAttack.dat likely contains a collection of profiles
                # Try to iterate and extract XML from each
                profiles = []
                
                # If it's a collection/list
                try:
                    for item in obj:
                        # Try to get XML from item
                        for prop_name in ['Xml', 'XmlData', 'ProfileXml']:
                            try:
                                prop = item.GetType().GetProperty(prop_name)
                                if prop:
                                    value = prop.GetValue(item, None)
                                    if value and '<?xml' in str(value):
                                        profiles.append(str(value))
                                        break
                            except:
                                pass
                except:
                    pass
                
                return profiles
                
            finally:
                file_stream.Close()
                
        except Exception as e:
            logger.error(f"Failed to read database: {e}")
            raise
