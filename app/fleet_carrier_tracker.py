"""
Fleet Carrier Tracker Module
Thin wrapper around JournalParser.carrier_data for easy access from the UI.
All actual parsing is done by journal_parser.py event handlers.
"""

import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class FleetCarrierTracker:
    """Provides access to fleet carrier data collected by JournalParser."""

    def __init__(self):
        self._journal_parser = None

    def set_journal_parser(self, parser):
        """Attach the JournalParser instance so we can read its carrier_data."""
        self._journal_parser = parser
        logger.info("FleetCarrierTracker: journal parser attached")

    @property
    def carrier_data(self) -> Optional[Dict]:
        """Return the live carrier_data dict from the journal parser, or None."""
        if self._journal_parser is None:
            return None
        return self._journal_parser.carrier_data

    def set_on_updated(self, callback):
        """Register a callback fired whenever carrier data changes.
        The callback receives the carrier_data dict as its only argument.
        """
        if self._journal_parser is not None:
            self._journal_parser.on_carrier_updated = callback

    # ------------------------------------------------------------------
    # Convenience accessors (backwards-compatible with old code)
    # ------------------------------------------------------------------

    def get_carrier_system(self) -> Optional[str]:
        cd = self.carrier_data
        return cd['system'] if cd else None

    def get_carrier_name(self) -> Optional[str]:
        cd = self.carrier_data
        return cd['name'] if cd else None

    def get_carrier_callsign(self) -> Optional[str]:
        cd = self.carrier_data
        return cd['callsign'] if cd else None

    def get_carrier_info(self) -> Optional[Dict]:
        """Legacy-compatible summary dict."""
        cd = self.carrier_data
        if not cd or not cd.get('system'):
            return None
        return {
            'carrier_name': cd.get('name'),
            'callsign': cd.get('callsign'),
            'system_name': cd.get('system'),
            'fuel_level': cd.get('fuel_level'),
            'fuel_capacity': cd.get('fuel_capacity', 1000),
            'balance': cd.get('balance'),
            'reserve_percent': cd.get('reserve_percent'),
            'space_free': cd.get('space_free'),
            'space_total': cd.get('space_total'),
            'jump_destination': cd.get('jump_destination'),
            'jump_departure_time': cd.get('jump_departure_time'),
            'crew': cd.get('crew', []),
            'docking_access': cd.get('docking_access'),
            'timestamp': cd.get('last_updated'),
        }



    def set_journal_directory(self, journal_dir: str):
        """Accept a journal directory - no-op; JournalParser handles all file reading."""
        pass


# Global instance
_tracker = None


def get_fleet_carrier_tracker() -> FleetCarrierTracker:
    """Get or create the global fleet carrier tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = FleetCarrierTracker()
    return _tracker

