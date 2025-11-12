"""
Fleet Carrier Tracker Module
Detects and tracks fleet carrier location from Elite Dangerous journal files
"""

import os
import json
import glob
from typing import Optional, Dict
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class FleetCarrierTracker:
    """Tracks fleet carrier location from journal files"""
    
    def __init__(self, journal_dir: Optional[str] = None):
        self.journal_dir = journal_dir
        self.last_known_carrier = None
        self.last_carrier_system = None
        self.last_carrier_timestamp = None
        
    def set_journal_directory(self, journal_dir: str):
        """Set the journal directory to scan"""
        self.journal_dir = journal_dir
        logger.info(f"Fleet carrier tracker journal directory set to: {journal_dir}")
    
    def _parse_journal_line(self, line: str) -> Optional[Dict]:
        """Parse a single journal line as JSON"""
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            return None
    
    def _process_carrier_jump_event(self, event: Dict):
        """Process a CarrierJump event"""
        try:
            system_name = event.get("StarSystem")
            timestamp = event.get("timestamp")
            
            if system_name:
                self.last_carrier_system = system_name
                self.last_carrier_timestamp = timestamp
                logger.info(f"Fleet Carrier jumped to: {system_name} at {timestamp}")
                return True
        except Exception as e:
            logger.error(f"Error processing CarrierJump event: {e}")
        return False
    
    def _process_location_event(self, event: Dict):
        """Process a Location event (when docked at carrier)"""
        try:
            # Check if docked at a station
            docked = event.get("Docked", False)
            station_type = event.get("StationType", "")
            
            # Fleet Carriers have StationType "FleetCarrier"
            if docked and station_type == "FleetCarrier":
                system_name = event.get("StarSystem")
                timestamp = event.get("timestamp")
                carrier_name = event.get("StationName")
                
                if system_name:
                    self.last_known_carrier = carrier_name
                    self.last_carrier_system = system_name
                    self.last_carrier_timestamp = timestamp
                    logger.info(f"Detected at Fleet Carrier '{carrier_name}' in {system_name} at {timestamp}")
                    return True
        except Exception as e:
            logger.error(f"Error processing Location event: {e}")
        return False
    
    def _process_docked_event(self, event: Dict):
        """Process a Docked event"""
        try:
            station_type = event.get("StationType", "")
            
            # Fleet Carriers have StationType "FleetCarrier"
            if station_type == "FleetCarrier":
                system_name = event.get("StarSystem")
                timestamp = event.get("timestamp")
                carrier_name = event.get("StationName")
                
                if system_name:
                    self.last_known_carrier = carrier_name
                    self.last_carrier_system = system_name
                    self.last_carrier_timestamp = timestamp
                    logger.info(f"Docked at Fleet Carrier '{carrier_name}' in {system_name} at {timestamp}")
                    return True
        except Exception as e:
            logger.error(f"Error processing Docked event: {e}")
        return False
    
    def scan_journals_for_carrier(self) -> Optional[str]:
        """
        Scan journal files for fleet carrier location
        
        Returns:
            System name where fleet carrier is located, or None if not found
        """
        if not self.journal_dir or not os.path.exists(self.journal_dir):
            logger.warning(f"Journal directory not set or doesn't exist: {self.journal_dir}")
            return None
        
        logger.info(f"Scanning journals in {self.journal_dir} for fleet carrier...")
        
        # Get all journal files sorted by modification time (newest first)
        journal_pattern = os.path.join(self.journal_dir, "Journal.*.log")
        journal_files = sorted(
            glob.glob(journal_pattern),
            key=os.path.getmtime,
            reverse=True
        )
        
        if not journal_files:
            logger.warning("No journal files found")
            return None
        
        # Scan recent journal files (last 5 files should be enough)
        files_to_scan = journal_files[:5]
        logger.info(f"Scanning {len(files_to_scan)} recent journal files")
        
        # Collect all carrier events with timestamps
        carrier_events = []
        
        for journal_file in files_to_scan:
            try:
                with open(journal_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        event = self._parse_journal_line(line)
                        if not event:
                            continue
                        
                        event_type = event.get("event")
                        timestamp = event.get("timestamp")
                        
                        # Collect relevant carrier events
                        # Use CarrierLocation event - but ONLY for YOUR FleetCarrier (not SquadronCarrier)
                        if event_type == "CarrierLocation":
                            carrier_type = event.get("CarrierType", "")
                            system_name = event.get("StarSystem")
                            carrier_id = event.get("CarrierID")
                            
                            # ONLY track YOUR FleetCarrier, ignore SquadronCarrier
                            if carrier_type == "FleetCarrier" and system_name and timestamp:
                                carrier_events.append({
                                    "timestamp": timestamp,
                                    "system": system_name,
                                    "carrier_name": None,
                                    "event_type": "CarrierLocation"
                                })
                                logger.debug(f"Found CarrierLocation (FleetCarrier): {system_name} at {timestamp}")
                        # Also check CarrierJump as fallback (only for YOUR carrier)
                        elif event_type == "CarrierJump":
                            system_name = event.get("StarSystem")
                            if system_name and timestamp:
                                carrier_events.append({
                                    "timestamp": timestamp,
                                    "system": system_name,
                                    "carrier_name": None,
                                    "event_type": "CarrierJump"
                                })
                                logger.debug(f"Found CarrierJump: {system_name} at {timestamp}")
                            
            except Exception as e:
                logger.error(f"Error reading journal file {journal_file}: {e}")
                continue
        
        # Sort by timestamp (most recent first) and take the most recent
        if carrier_events:
            # Convert timestamps to datetime for proper sorting
            for event in carrier_events:
                try:
                    event["datetime"] = datetime.fromisoformat(event["timestamp"].replace('Z', '+00:00'))
                except:
                    # Fallback: keep string comparison if parsing fails
                    event["datetime"] = event["timestamp"]
            
            # Sort by datetime (most recent first)
            carrier_events.sort(key=lambda x: x["datetime"], reverse=True)
            most_recent = carrier_events[0]
            
            self.last_carrier_system = most_recent["system"]
            self.last_known_carrier = most_recent["carrier_name"]
            self.last_carrier_timestamp = most_recent["timestamp"]
            
            logger.info(f"Fleet Carrier last seen in: {self.last_carrier_system} at {self.last_carrier_timestamp}")
            logger.info(f"Event type: {most_recent['event_type']}")
            if self.last_known_carrier:
                logger.info(f"Fleet Carrier name: {self.last_known_carrier}")
        else:
            logger.info("No fleet carrier location found in journals")
            self.last_carrier_system = None
            self.last_known_carrier = None
            self.last_carrier_timestamp = None
        
        return self.last_carrier_system
    
    def get_carrier_info(self) -> Optional[Dict]:
        """
        Get detailed fleet carrier information
        
        Returns:
            Dict with carrier_name, system_name, timestamp or None
        """
        if not self.last_carrier_system:
            return None
        
        return {
            "carrier_name": self.last_known_carrier,
            "system_name": self.last_carrier_system,
            "timestamp": self.last_carrier_timestamp
        }


# Global instance
_tracker = None

def get_fleet_carrier_tracker() -> FleetCarrierTracker:
    """Get or create the global fleet carrier tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = FleetCarrierTracker()
    return _tracker
