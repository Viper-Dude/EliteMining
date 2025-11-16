# EliteMining v4.5.5 - Patch Notes

**Release Date:** November 16, 2025

## New Features & Improvements

### Commodity Market
- **Optimized commodity search performance**: Improved search speed and reliability
  - Migrated to EDData API with automatic Ardent API fallback
  - Added Galaxy-Wide Top 30 search mode for finding best prices across the entire galaxy
  - Enhanced distance calculation using local database for instant results
  - Improved station type display: Shows specific types (Orbital/Coriolis, Orbital/Dodec, Surface/Crater Outpost, etc.)
  - Fixed station filtering to handle all station types correctly
  - Added helpful tooltip explaining Galaxy-Wide search limitations

### VoiceAttack Controls
- **Enhanced FSD Jump Sequence**: Now auto-closes system map and initiates next jump in route (previously only opened map)
  - Complete automation for multi-jump routes
  - Added tip: Use "Stop all profile commands" to interrupt active sequences
  - Renamed from "Open System Map" for clarity

### Distance Calculator
- **Added retry logic**: Automatic retry on temporary EDSM API failures
  - Up to 3 retry attempts with smart backoff delays
  - Better handling of network timeouts and connection issues
  - Improved reliability without requiring app restart

## Bug Fixes

### Commodity Market
- **Fixed NoneType errors in station filtering**: Surface station filters no longer crash when station type is missing
- **Fixed distance sorting**: Galaxy-Wide results now properly sort by distance after calculation completes

## Documentation

### README Updates
- **Reorganized VoiceAttack Controls section**: Separated firegroups, timers, and toggles into dedicated section
- **Removed outdated terminology**: Eliminated references to "Dashboard" and "Main Window"
- **Added comprehensive toggle descriptions**: Each toggle now has clear explanation of behavior

---

## Technical Details

### Changed Files
- `app/marketplace_api.py`: EDData API integration with fallback logic
- `app/main.py`: Station type display improvements, distance sorting fix, NoneType error fixes
- `app/edsm_distance.py`: Added retry logic with exponential backoff
- `app/core/constants.py`: Updated FSD Jump Sequence toggle description
- `README.md`: Restructured VoiceAttack Controls documentation

### For Developers
- New `search_buyers_galaxy_wide()` method in MarketplaceAPI
- Added local database fallback for distance calculations
- Station type display now shows category/specific type (e.g., "Orbital/Dodec")
- Retry logic implements 0s, 1s, 2s backoff pattern

---

## Known Issues
None reported for this release.

---

## Installation
Standard update - no special installation steps required.

---

**Full Changelog:** https://github.com/Viper-Dude/EliteMining/compare/v4.5.4...v4.5.5
