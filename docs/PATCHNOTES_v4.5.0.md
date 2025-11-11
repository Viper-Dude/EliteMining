# EliteMining v4.5.0 - Patch Notes

**Release Date:** November 11, 2025

---

## What's New

### Distance Calculator (NEW!)
- **New:** Distance Calculator tab for calculating distances between any two systems using EDSM data
- **New:** Auto-tracks Home System and Fleet Carrier locations with live distance updates from current position
- **New:** Fleet Carrier auto-detection from journal files
- **New:** All calculator settings (System A, System B, Home, FC) are remembered between sessions
- **New:** Shows coordinates and distance to Sol for all systems

### User Interface
- **Changed:** Removed visual popup notification for update checks at startup. Update check status now displays in the bottom left status label instead (shows for 3 seconds).
- **New:** All table column widths are now remembered and restored on app restart. Applies to:
  - Mining Analysis (Reports Tab) - Session list
  - Prospector Report - Asteroid prospecting list
  - Mineral Analysis - Live mining statistics
  - Mining Bookmarks - Saved mining locations
  - Ring Finder - Search results
  - Commodity Market - Market prices

### Documentation
- **Cleaned:** Removed duplicate sections in API specification and implementation plan documents
- **Aligned:** API specification now properly aligned with implementation plan

### Ring Finder
- **Fixed:** Ring Finder now works after Fleet Carrier jumps while offline. Added EDSM API fallback for reference system coordinates when not found in local databases. This resolves the issue where logging in after a carrier jump would show "No rings found" due to missing system coordinates.
- **Fixed:** Reference system hotspots now always appear in search results at 0 LY. Previously, newly scanned hotspots in the reference system could be excluded from results.
- **Fixed:** Search results are now sorted by distance (closest first) to ensure accurate ordering within the 5000 system performance limit.
- **Changed:** Max distance filter capped at 300 LY (removed 400/500 LY options) for optimal performance and accurate results.
- **New:** All filter settings (Ring Type, Mineral, Max Distance, Max Results, Min Hotspots) are now saved and restored on app restart.

---

## Known Issues
- None

---

## Notes
- EDSM API queries may add a slight delay (~1-2 seconds) when searching from systems not in the bundled galaxy database
- Update check still runs automatically at startup, just less intrusive now
