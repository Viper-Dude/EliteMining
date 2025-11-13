# EliteMining v4.5.2 - Patch Notes

**Release Date:** November 13, 2025

---

## What's New

### VoiceAttack Controls
- **New:** Added "Open System Map" toggle (`toggleSystem.txt`)
  - Automatically opens system map after FSD jump
  - Toggle file: `Variables/toggleSystem.txt`
  - Help text: "Automatically open system map after FSD jump"

### Distance Calculator
- **New:** Current System now displays distance to Sol (yellow text, same format as Home/FC distances)
- **Improved:** Home System field - press Enter to save (no button needed)
- **Improved:** Cleaner interface with instant visual feedback when setting home system

### UI Improvements
- **Changed:** Toggle checkboxes now show help text inline in italic format instead of tooltips
- **Improved:** More readable toggle descriptions without needing hover
- **New:** Added "VoiceAttack integration" label above Import/Apply buttons
- **New:** Ship Presets title now shows "(VoiceAttack only)" to clarify functionality
- **Improved:** Help text for VoiceAttack features displayed inline for better visibility
- **Improved:** Expanded default window size (1200x700) for better layout on new installs

---

## Bug Fixes
- **Fixed:** Logo positioning in Mining Controls tab now properly anchored to prevent hiding on window resize
- **Removed:** Logo from Mining Controls tab for cleaner appearance
---

## Known Issues
- Ardent API does not yet support "Dodec" station type (shows as "SurfaceStation" instead)
- EDSM/EDDN shows Dodec stations as "Planetary Outpost" (legacy name)
- Elite Dangerous journals correctly identify Dodec stations, but marketplace API data sources have not been updated

---

## Notes
- Startup performance significantly improved - no more UI freeze during journal scanning
- All system-related data now synchronized across Mining Session, Hotspots Finder, and Distance Calculator
- Toggle help text changes make settings more discoverable without hovering
