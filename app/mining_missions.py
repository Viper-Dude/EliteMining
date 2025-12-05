"""
Mining Missions Tracker for EliteMining
Tracks active mining missions from journal and shows progress against cargo
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from path_utils import get_app_data_dir

log = logging.getLogger("EliteMining.MiningMissions")

# Flag to indicate missions module is available
MISSIONS_AVAILABLE = True


class MiningMissionTracker:
    """Tracks active mining missions from journal events"""
    
    # Mining mission name patterns (from journal)
    MINING_MISSION_PATTERNS = [
        "Mission_Mining",
        "Mission_MiningRush", 
        "Mission_Mining_Wing",
    ]
    
    def __init__(self):
        self.active_missions: Dict[int, Dict] = {}  # mission_id -> mission data
        self.completed_missions: List[Dict] = []
        self.callbacks: List[callable] = []  # UI update callbacks
        self._batch_mode = False  # Suppress callbacks/saves during batch processing
        self._batch_changed = False  # Track if anything changed during batch
        self._load_state()
    
    def _get_state_file(self) -> str:
        """Get path to missions state file"""
        return os.path.join(get_app_data_dir(), "mining_missions.json")
    
    def _load_state(self):
        """Load saved mission state"""
        try:
            state_file = self._get_state_file()
            if os.path.exists(state_file):
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.active_missions = {int(k): v for k, v in data.get('active', {}).items()}
                    self.completed_missions = data.get('completed', [])[-20:]  # Keep last 20
                    log.info(f"Loaded {len(self.active_missions)} active mining missions")
        except Exception as e:
            log.warning(f"Could not load missions state: {e}")
    
    def _save_state(self):
        """Save mission state to disk"""
        if self._batch_mode:
            self._batch_changed = True
            return  # Skip during batch processing
        try:
            state_file = self._get_state_file()
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            data = {
                'active': self.active_missions,
                'completed': self.completed_missions[-20:],
                'updated': datetime.now(timezone.utc).isoformat()
            }
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log.warning(f"Could not save missions state: {e}")
    
    def is_mining_mission(self, mission_name: str) -> bool:
        """Check if a mission name is a mining mission"""
        if not mission_name:
            return False
        for pattern in self.MINING_MISSION_PATTERNS:
            if pattern.lower() in mission_name.lower():
                return True
        return False
    
    def add_callback(self, callback: callable):
        """Register a callback for mission updates"""
        if callback not in self.callbacks:
            self.callbacks.append(callback)
    
    def remove_callback(self, callback: callable):
        """Remove a callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def _notify_callbacks(self):
        """Notify all registered callbacks of mission changes"""
        if self._batch_mode:
            self._batch_changed = True
            return  # Skip during batch processing
        for cb in self.callbacks:
            try:
                cb()
            except Exception as e:
                log.warning(f"Mission callback error: {e}")
    
    def start_batch(self):
        """Start batch mode - suppresses callbacks and saves until end_batch()"""
        self._batch_mode = True
        self._batch_changed = False
    
    def end_batch(self):
        """End batch mode - saves and notifies if anything changed"""
        self._batch_mode = False
        if self._batch_changed:
            self._save_state()
            for cb in self.callbacks:
                try:
                    cb()
                except Exception as e:
                    log.warning(f"Mission callback error: {e}")
            self._batch_changed = False
    
    def process_event(self, event: Dict[str, Any]) -> bool:
        """Process a journal event and dispatch to appropriate handler.
        
        Returns True if this was a mining mission event that was processed.
        """
        event_type = event.get('event', '')
        
        if event_type == 'MissionAccepted':
            mission_name = event.get('Name', '')
            if self.is_mining_mission(mission_name):
                self.handle_mission_accepted(event)
                return True
        elif event_type == 'MissionCompleted':
            mission_id = event.get('MissionID')
            if mission_id and mission_id in self.active_missions:
                self.handle_mission_completed(event)
                return True
        elif event_type == 'MissionAbandoned':
            mission_id = event.get('MissionID')
            if mission_id and mission_id in self.active_missions:
                self.handle_mission_abandoned(event)
                return True
        elif event_type == 'MissionFailed':
            mission_id = event.get('MissionID')
            if mission_id and mission_id in self.active_missions:
                self.handle_mission_failed(event)
                return True
        elif event_type == 'CargoDepot':
            # Track deliveries for mining missions
            mission_id = event.get('MissionID')
            if mission_id and mission_id in self.active_missions:
                self.handle_cargo_depot(event)
                return True
        
        return False
    
    def handle_mission_accepted(self, event: Dict[str, Any]):
        """Handle MissionAccepted journal event"""
        mission_name = event.get('Name', '')
        
        if not self.is_mining_mission(mission_name):
            return  # Not a mining mission
        
        mission_id = event.get('MissionID')
        if not mission_id:
            return
        
        # Extract commodity info
        commodity = event.get('Commodity_Localised') or event.get('Commodity', '')
        # Clean up commodity name (remove $ prefix and _name; suffix)
        if commodity.startswith('$'):
            commodity = commodity[1:]
        if commodity.endswith('_name;'):
            commodity = commodity[:-6]
        commodity = commodity.replace('_', ' ').title()
        
        count = event.get('Count', 0)
        reward = event.get('Reward', 0)
        expiry = event.get('Expiry', '')
        
        # Get station/faction info
        faction = event.get('Faction', '')
        
        mission_data = {
            'mission_id': mission_id,
            'name': mission_name,
            'localised_name': event.get('LocalisedName', ''),
            'commodity': commodity,
            'commodity_raw': event.get('Commodity', ''),
            'count': count,
            'collected': 0,  # Will be updated from cargo
            'delivered': 0,  # Track cargo delivered to station
            'reward': reward,
            'expiry': expiry,
            'faction': faction,
            'destination_system': event.get('DestinationSystem', ''),
            'destination_station': event.get('DestinationStation', ''),
            'wing': event.get('Wing', False),
            'accepted_at': event.get('timestamp', datetime.now(timezone.utc).isoformat()),
        }
        
        self.active_missions[mission_id] = mission_data
        log.info(f"Mining mission accepted: {commodity} x{count} (ID: {mission_id})")
        self._save_state()
        self._notify_callbacks()
    
    def handle_mission_completed(self, event: Dict[str, Any]):
        """Handle MissionCompleted journal event"""
        mission_id = event.get('MissionID')
        if mission_id and mission_id in self.active_missions:
            mission = self.active_missions.pop(mission_id)
            mission['completed_at'] = event.get('timestamp')
            self.completed_missions.append(mission)
            log.info(f"Mining mission completed: {mission.get('commodity')} (ID: {mission_id})")
            self._save_state()
            self._notify_callbacks()
    
    def handle_mission_abandoned(self, event: Dict[str, Any]):
        """Handle MissionAbandoned journal event"""
        mission_id = event.get('MissionID')
        if mission_id and mission_id in self.active_missions:
            mission = self.active_missions.pop(mission_id)
            log.info(f"Mining mission abandoned: {mission.get('commodity')} (ID: {mission_id})")
            self._save_state()
            self._notify_callbacks()
    
    def handle_mission_failed(self, event: Dict[str, Any]):
        """Handle MissionFailed journal event"""
        mission_id = event.get('MissionID')
        if mission_id and mission_id in self.active_missions:
            mission = self.active_missions.pop(mission_id)
            log.info(f"Mining mission failed: {mission.get('commodity')} (ID: {mission_id})")
            self._save_state()
            self._notify_callbacks()
    
    def handle_cargo_depot(self, event: Dict[str, Any]):
        """Handle CargoDepot journal event - tracks cargo delivered for missions
        
        CargoDepot event structure:
        - MissionID: ID of the mission
        - UpdateType: "Deliver" when delivering cargo
        - CargoType: The commodity being delivered (e.g. "Bromellite")
        - Count: Amount delivered in this event
        - TotalItemsToDeliver: Total required for mission
        - ItemsDelivered: Total delivered so far
        - Progress: Fraction of mission complete (0.0 to 1.0)
        """
        mission_id = event.get('MissionID')
        if not mission_id or mission_id not in self.active_missions:
            return
        
        update_type = event.get('UpdateType', '')
        if update_type != 'Deliver':
            return
        
        mission = self.active_missions[mission_id]
        items_delivered = event.get('ItemsDelivered', 0)
        
        # Update delivered count
        old_delivered = mission.get('delivered', 0)
        if items_delivered != old_delivered:
            mission['delivered'] = items_delivered
            log.info(f"Mining mission delivery: {mission.get('commodity')} - {items_delivered}/{mission.get('count')} delivered (ID: {mission_id})")
            self._save_state()
            self._notify_callbacks()
    
    def update_progress_from_cargo(self, cargo_items: Dict[str, int]):
        """
        Update mission progress based on current cargo contents.
        
        Args:
            cargo_items: Dict mapping commodity names to quantities
        """
        if not self.active_missions:
            return
        
        updated = False
        for mission_id, mission in self.active_missions.items():
            commodity = mission.get('commodity', '').lower()
            commodity_raw = mission.get('commodity_raw', '').lower()
            
            # Try to match cargo item to mission commodity
            collected = 0
            for cargo_name, qty in cargo_items.items():
                cargo_lower = cargo_name.lower()
                if commodity in cargo_lower or cargo_lower in commodity:
                    collected = qty
                    break
                # Also try raw name match
                if commodity_raw and (commodity_raw in cargo_lower or cargo_lower in commodity_raw):
                    collected = qty
                    break
            
            if mission.get('collected', 0) != collected:
                mission['collected'] = collected
                updated = True
        
        if updated:
            self._save_state()
            self._notify_callbacks()
    
    def get_active_missions(self) -> List[Dict]:
        """Get list of active mining missions sorted by expiry"""
        missions = list(self.active_missions.values())
        # Sort by expiry (soonest first)
        missions.sort(key=lambda m: m.get('expiry', ''))
        return missions
    
    def get_mission_for_commodity(self, commodity: str) -> Optional[Dict]:
        """Get active mission for a specific commodity"""
        commodity_lower = commodity.lower()
        for mission in self.active_missions.values():
            if commodity_lower in mission.get('commodity', '').lower():
                return mission
        return None
    
    def get_required_commodities(self) -> Dict[str, int]:
        """Get dict of commodities needed and total quantities"""
        required = {}
        for mission in self.active_missions.values():
            commodity = mission.get('commodity', '')
            if commodity:
                count = mission.get('count', 0) - mission.get('collected', 0)
                if count > 0:
                    required[commodity] = required.get(commodity, 0) + count
        return required
    
    def clear_all_missions(self):
        """Clear all active missions (for testing/reset)"""
        self.active_missions.clear()
        self._save_state()
        self._notify_callbacks()


# Global tracker instance
_tracker: Optional[MiningMissionTracker] = None


def get_mission_tracker() -> MiningMissionTracker:
    """Get or create the global mission tracker instance"""
    global _tracker
    if _tracker is None:
        _tracker = MiningMissionTracker()
    return _tracker
