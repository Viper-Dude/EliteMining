"""
Journal Scanning State Manager

Tracks the last processed journal file and position to enable
incremental scanning on app startup.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging

log = logging.getLogger(__name__)


class JournalScanState:
    """Manages persistent state for journal scanning"""
    
    def __init__(self, state_file: str = "last_journal_scan.json"):
        """
        Initialize state manager
        
        Args:
            state_file: Path to state file (relative to app data dir)
        """
        # Get app data directory
        from path_utils import get_app_data_dir
        self.state_file = os.path.join(get_app_data_dir(), state_file)
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load state from file, return empty dict if not found or invalid"""
        if not os.path.exists(self.state_file):
            log.info("No previous journal scan state found")
            return {}
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                log.info(f"Loaded journal scan state: last file={state.get('last_journal_file')}, position={state.get('last_file_position')}")
                return state
        except Exception as e:
            log.error(f"Failed to load journal scan state: {e}")
            return {}
    
    def save_state(self, journal_file: str, file_position: int, timestamp: str = None):
        """
        Save current scanning state
        
        Args:
            journal_file: Full path to last processed journal file
            file_position: Byte position in file where we stopped
            timestamp: Optional timestamp of last processed event
        """
        self.state = {
            'last_journal_file': journal_file,
            'last_file_position': file_position,
            'last_scan_timestamp': timestamp or datetime.now().isoformat(),
            'last_update': datetime.now().isoformat()
        }
        
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
            log.debug(f"Saved journal scan state: {self.state}")
        except Exception as e:
            log.error(f"Failed to save journal scan state: {e}")
    
    def get_last_journal_file(self) -> Optional[str]:
        """Get last processed journal file path"""
        return self.state.get('last_journal_file')
    
    def get_last_file_position(self) -> int:
        """Get last processed file position (byte offset)"""
        return self.state.get('last_file_position', 0)
    
    def get_last_scan_timestamp(self) -> Optional[str]:
        """Get timestamp of last scan"""
        return self.state.get('last_scan_timestamp')
    
    def is_state_stale(self, days: int = 30) -> bool:
        """
        Check if state is older than specified days
        
        Args:
            days: Number of days to consider state fresh
            
        Returns:
            True if state is stale or missing
        """
        last_update = self.state.get('last_update')
        if not last_update:
            return True
        
        try:
            last_date = datetime.fromisoformat(last_update)
            age = datetime.now() - last_date
            is_stale = age > timedelta(days=days)
            if is_stale:
                log.warning(f"Journal scan state is {age.days} days old (stale)")
            return is_stale
        except Exception as e:
            log.error(f"Failed to parse last update timestamp: {e}")
            return True
    
    def reset(self):
        """Reset state (force full rescan)"""
        self.state = {}
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
                log.info("Reset journal scan state")
            except Exception as e:
                log.error(f"Failed to delete state file: {e}")
