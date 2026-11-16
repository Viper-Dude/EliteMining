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


# Global instance
_tracker = None


def get_fleet_carrier_tracker() -> FleetCarrierTracker:
    """Get or create the global fleet carrier tracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = FleetCarrierTracker()
    return _tracker

