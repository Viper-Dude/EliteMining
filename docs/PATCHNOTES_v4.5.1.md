# EliteMining v4.5.1 - Patch Notes

**Release Date:** November 12, 2025

---

## What's New

### Distance Calculator Improvements
- **New:** Added "Current System" display field that auto-updates on FSD jumps (green, read-only)
- **New:** Fleet Carrier location now auto-detects on app startup from journal files
- **New:** Live Fleet Carrier tracking - automatically updates FC location when carrier jumps (via `CarrierLocation` event)
- **New:** System name labels now display in Results section (e.g., "System A: Volciates") in orange color for better visibility
- **Changed:** Fleet Carrier field is now read-only (orange text) and auto-managed - no manual editing needed
- **Changed:** Removed "Set" button for Fleet Carrier - location is always auto-detected
- **Changed:** Fleet Carrier auto-detect button renamed to "Refresh FC Location" for clarity
- **Removed:** Fleet Carrier location success dialog - now shows status message at bottom instead
- **Improved:** All input fields now have consistent width (250px) and proper alignment
- **Improved:** Buttons (Use Current, Home, FC) positioned closer to input fields for better layout
- **Improved:** Input fields no longer over-expand when window is resized

### Bug Fixes
- **Fixed:** Timestamp sorting in Fleet Carrier tracker now uses proper datetime comparison for accurate location detection
- **Fixed:** Fleet Carrier tracker now detects `CarrierLocation` events (logged after carrier jump completes)
- **Fixed:** Mining Controls tab logo now moves correctly with window resize (matches Firegroups tab behavior)

---

## Technical Changes
- Added `CarrierLocation` event support to `fleet_carrier_tracker.py`
- Integrated Fleet Carrier live tracking into `prospector_panel.py` journal watcher
- Improved column configuration for Distance Calculator UI (fixed vs expanding columns)
- Enhanced Fleet Carrier detection with datetime-based event sorting

---

## Known Issues
- None

---

## Notes
- Fleet Carrier location is now fully automatic - scans journals on startup and updates live when carrier jumps
- "Refresh FC Location" button available for manual refresh if needed
- All Distance Calculator settings are remembered between sessions

