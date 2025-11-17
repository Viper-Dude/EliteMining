# EliteMining v4.5.6 - Patch Notes

**Release Date:** November 17, 2025

## New Features & Improvements

### VoiceAttack Integration
- **Added jumpsleft.txt variable**: New VoiceAttack variable that tracks remaining jumps in plotted route
  - Automatically updates when plotting/clearing routes
  - Updates in real-time as you make jumps
  - Resets to 0 when docking or landing
  - Enables automation stopping at destination
  - File location: `Variables/jumpsleft.txt`

### Hotspots Finder
- **Fixed search filters**: Resolved issue where "All" ring type filter would return no results
- **Improved search performance**: Reduced unnecessary EDSM queries when data already exists in database

### User Interface
- **Enhanced table styling**: Added visible borders and improved visual separation for all tables across the app
  - Applies to: Prospector Reports, Mineral Analysis, Session Reports, Bookmarks, Hotspots Finder, and Commodity Market
  - Left-aligned column headers for better readability

### Bug Fixes
- **Fixed first asteroid not announcing**: Resolved issue where the first prospected asteroid after app startup would not trigger voice announcements or overlay text

### VoiceAttack jumpsleft.txt Implementation
- Monitors Elite Dangerous journal for `FSDTarget` events containing `RemainingJumpsInRoute`
- Checks `NavRoute.json` for route clearing (empty Route array)
- Polls every 2 seconds for route changes (minimal overhead)
- Initializes on app startup by scanning recent journal for active routes
- Tracks Docked/Touchdown events to reset jumps to 0
  