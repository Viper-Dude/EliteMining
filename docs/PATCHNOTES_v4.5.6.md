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

### Code Architecture
- **Refactored VoiceAttack variables into dedicated module**: Created `va_variables.py` for cleaner separation
  - Improved code organization and maintainability
  - Easier to extend with additional VoiceAttack variables in future
  - Reduced main.py complexity

## Technical Details

### VoiceAttack jumpsleft.txt Implementation
- Monitors Elite Dangerous journal for `FSDTarget` events containing `RemainingJumpsInRoute`
- Checks `NavRoute.json` for route clearing (empty Route array)
- Polls every 2 seconds for route changes (minimal overhead)
- Initializes on app startup by scanning recent journal for active routes
- Tracks Docked/Touchdown events to reset jumps to 0

### Changed Files
- `app/va_variables.py`: New module for VoiceAttack variable management
- `app/main.py`: Integrated VA variables manager, removed direct route tracking code
- `app/journal_parser.py`: Added `process_fsd_target()` method for route event processing
- `app/edsm_distance.py`: Added retry logic with exponential backoff for EDSM API calls
- `app/file_watcher.py`: Added navroute.json to monitored files

### For Developers
- `VAVariablesManager` class handles all VoiceAttack variable operations
- Route polling uses same proven approach as cargo monitoring
- Generic `write_variable()` and `read_variable()` methods for future expansion
- Value caching prevents unnecessary file writes

## VoiceAttack Usage Example

Read the jumpsleft variable in your VoiceAttack profile:

```
Check variable: {TXT:jumpsleft}

If {TXT:jumpsleft} = "0"
  Stop FSD Jump Sequence command
  Say "Destination reached"
End If

If {TXT:jumpsleft} > "5"
  Say "{TXT:jumpsleft} jumps remaining"
End If
```

**Values:**
- `0` = At destination or no route plotted
- `1` to `X` = Number of jumps remaining to destination

---

## Known Issues
None reported for this release.

---

## Installation
Standard update - no special installation steps required.

---

**Full Changelog:** https://github.com/Viper-Dude/EliteMining/compare/v4.5.5...v4.5.6
