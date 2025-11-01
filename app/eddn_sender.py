"""
EDDN (Elite Dangerous Data Network) Sender
Sends market data to EDDN for community sharing

Follows EDDN schema specifications
"""

import requests
import json
import gzip
from datetime import datetime, timezone
from typing import Optional, Dict, List
import logging

log = logging.getLogger('EliteMining.EDDN_Sender')


class EDDNSender:
    """
    Sends market and system data to EDDN
    """
    
    EDDN_UPLOAD_URL = "https://eddn.edcd.io:4430/upload/"
    
    # Schema URLs (use exact paths from live EDDN)
    SCHEMA_COMMODITY_V3 = "https://eddn.edcd.io/schemas/commodity/3"
    SCHEMA_JOURNAL_V1 = "https://eddn.edcd.io/schemas/journal/1"
    
    def __init__(self, commander_name: str = "Unknown", app_name: str = "EliteMining", app_version: str = "4.4.1"):
        """
        Initialize EDDN sender
        
        Args:
            commander_name: Elite Dangerous commander name
            app_name: Application name
            app_version: Application version
        """
        self.commander_name = commander_name
        self.app_name = app_name
        self.app_version = app_version
        self.enabled = False
        self.messages_sent = 0
        
        # Game version info (updated from journal LoadGame event)
        self.game_version = ""
        self.game_build = ""
        self.horizons = None
        self.odyssey = None
        
    def set_enabled(self, enabled: bool):
        """Enable or disable EDDN sending"""
        self.enabled = enabled
        log.info(f"EDDN sending {'enabled' if enabled else 'disabled'}")
    
    def update_game_info(self, load_game_event: Dict):
        """
        Update game version info from LoadGame journal event
        
        Args:
            load_game_event: LoadGame event from journal
        """
        self.game_version = load_game_event.get('GameVersion', '')
        self.game_build = load_game_event.get('Build', '')
        self.horizons = load_game_event.get('Horizons')
        self.odyssey = load_game_event.get('Odyssey')
        
        # Update commander name if available
        if 'Commander' in load_game_event:
            self.commander_name = load_game_event['Commander']
        
        log.info(f"Updated game info: {self.game_version}, Horizons={self.horizons}, Odyssey={self.odyssey}")
        
    def send_commodity_data(self, system_name: str, station_name: str, 
                           market_id: int, commodities: List[Dict],
                           station_data: Optional[Dict] = None) -> bool:
        """
        Send commodity market data to EDDN
        
        Args:
            system_name: System name
            station_name: Station name
            market_id: Market ID
            commodities: List of commodity dictionaries
            station_data: Optional station metadata
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
            
        try:
            # Build EDDN message
            message = {
                "$schemaRef": self.SCHEMA_COMMODITY_V3,
                "header": {
                    "uploaderID": self.commander_name,
                    "softwareName": self.app_name,
                    "softwareVersion": self.app_version,
                    "gameversion": self.game_version if self.game_version else "",
                    "gamebuild": self.game_build if self.game_build else "",
                    "gatewayTimestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "message": {
                    "systemName": system_name,
                    "stationName": station_name,
                    "marketId": market_id,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "commodities": commodities
                }
            }
            
            # Add horizons/odyssey flags if available
            if self.horizons is not None:
                message['message']['horizons'] = self.horizons
            if self.odyssey is not None:
                message['message']['odyssey'] = self.odyssey
            
            # Add optional station data
            if station_data:
                if 'type' in station_data:
                    message['message']['stationType'] = station_data['type']
                if 'distanceToArrival' in station_data:
                    message['message']['distanceToArrival'] = station_data['distanceToArrival']
            
            # Send to EDDN
            success = self._send_message(message)
            
            if success:
                self.messages_sent += 1
                log.info(f"✅ Sent market data for {station_name} in {system_name} to EDDN")
            
            return success
            
        except Exception as e:
            log.error(f"Error sending commodity data to EDDN: {e}")
            return False
    
    def send_journal_event(self, event_type: str, event_data: Dict) -> bool:
        """
        Send journal event to EDDN
        
        Args:
            event_type: Event type (e.g., "FSDJump", "Docked")
            event_data: Event data from journal
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
            
        try:
            # Filter sensitive data
            filtered_data = self._filter_journal_data(event_data)
            
            # Build EDDN message
            message = {
                "$schemaRef": self.SCHEMA_JOURNAL_V1,
                "header": {
                    "uploaderID": self.commander_name,
                    "softwareName": self.app_name,
                    "softwareVersion": self.app_version,
                    "gatewayTimestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                },
                "message": filtered_data
            }
            
            # Send to EDDN
            success = self._send_message(message)
            
            if success:
                self.messages_sent += 1
                log.debug(f"Sent journal event '{event_type}' to EDDN")
            
            return success
            
        except Exception as e:
            log.error(f"Error sending journal event to EDDN: {e}")
            return False
    
    def _send_message(self, message: Dict) -> bool:
        """
        Send message to EDDN gateway
        
        Args:
            message: EDDN message dictionary
            
        Returns:
            True if sent successfully
        """
        try:
            # Convert to JSON
            json_data = json.dumps(message, ensure_ascii=False)
            
            # Compress with gzip
            compressed_data = gzip.compress(json_data.encode('utf-8'))
            
            # Send to EDDN
            response = requests.post(
                self.EDDN_UPLOAD_URL,
                data=compressed_data,
                headers={
                    'Content-Type': 'application/json; charset=utf-8',
                    'Content-Encoding': 'gzip'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            else:
                log.warning(f"EDDN upload failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            log.error(f"Error sending to EDDN: {e}")
            return False
    
    def _filter_journal_data(self, event_data: Dict) -> Dict:
        """
        Filter sensitive data from journal events
        
        Args:
            event_data: Raw journal event data
            
        Returns:
            Filtered event data safe for EDDN
        """
        # Remove sensitive fields that shouldn't be shared
        sensitive_fields = ['Commander', 'FID', 'Name', 'Ship', 'ShipID']
        
        filtered = event_data.copy()
        for field in sensitive_fields:
            filtered.pop(field, None)
        
        return filtered
    
    def get_stats(self) -> Dict:
        """Get sender statistics"""
        return {
            'enabled': self.enabled,
            'messages_sent': self.messages_sent,
            'commander': self.commander_name
        }


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Create sender
    sender = EDDNSender(commander_name="TestCMDR", app_name="EliteMining", app_version="4.4.1")
    sender.set_enabled(True)
    
    # Example: Send commodity data
    commodities = [
        {
            "name": "Platinum",
            "buyPrice": 0,
            "sellPrice": 285000,
            "demand": 1000,
            "stock": 0
        }
    ]
    
    success = sender.send_commodity_data(
        system_name="Sol",
        station_name="Abraham Lincoln",
        market_id=128666762,
        commodities=commodities
    )
    
    print(f"Send successful: {success}")
    print(f"Stats: {sender.get_stats()}")
