# <img src="https://github.com/Viper-Dude/EliteMining/blob/main/app/Images/logo_multi.ico" width="32" height="32"> EliteMining
**Release Date:** November 25, 2025

## New Features & Improvements

### Mining Session Statistics Tab - Redesign (more in development)
- **Expanded Top Systems** from Top 3 to Top 5, now ranked by T/hr performance
- **New "Session Overview" header** for improved visual organization
- **Added "Best Records" section** with all-time best performance metrics:
  - Best T/hr
  - Best System
  - Most Mined Ton Session
  - Most Mined System
  - Most Mined Minerals
- **Improved Top 5 Systems layout** with color-coded information:
  - System | Body (White)
  - Minerals: [Type] (Orange)
  - T/Asteroid | T/hr (Green)
- **No duplicate system/ring combinations** - each unique system|body listed once
- **Auto-refresh statistics** after each mining session (removed manual refresh button)
- **Better visual hierarchy** with separator lines and dedicated headers

### UI Improvements
- **Bookmarks tab moved to main tabs** - Bookmarks tab is now a top-level tab between VoiceAttack Controls and Settings (previously nested inside Mining Session tab)

### Mining Reports
- **Ship info now displayed in HTML reports** - Session Summary and Efficiency Breakdown sections show ship name and type
- **Type-11 Prospector scoring adjustment** - Ring Quality scoring uses +25% thresholds for TPH and T/Asteroid to account for Type-11's faster mining mechanics (clearly indicated with badge)
- **Dynamic scoring explanation** - Efficiency Breakdown shows actual thresholds being applied based on ship type and mining method

### Enhanced Text Overlay
- **Core asteroid detection now displayed** - Enhanced overlay shows "CORE DETECTED: [MATERIAL]" at the bottom when a motherlode asteroid is detected, matching in-game format

---

## Bugfixes

### System Location Tracking
- **Fixed current system not updating after fleet carrier jump** - Distance Calculator, Ring Finder, and Mining Session now properly detect your current system when jumping with fleet carrier
- **Smart timestamp-based system detection** - App scans all journal events and selects the most recent location event by comparing timestamps, ensuring correct system even when multiple location events exist in the journal
- **Enhanced startup system detection** - App now scans journal for most recent FSDJump, Location, Docked, or CarrierJump event to set your system accurately on startup

### Ring Finder (Hotspots Finder)
- **Fixed all rows highlighting green on system jump** - Only newly scanned rings are now highlighted, not the entire result set
- **Fixed repeated auto-refresh when approaching rings** - Proximity-detected rings no longer trigger unnecessary search refreshes when hotspots already exist in database

### Database
- **Automatic cleanup of duplicate hotspot entries** - Migration removes incorrectly stored hotspot entries caused by system name extraction bug (affects only "Omicron Capricorni B" system)

### Installer
- **Fixed installer not detecting VoiceAttack installations** - Installer now checks C:\Program Files directory explicitly, bypassing system path redirection issues with 32-bit installer on 64-bit Windows
- **Fixed manual VoiceAttack path selection not installing VA profile** - Installer now correctly validates VoiceAttack folder when user manually browses to installation directory

### VoiceAttack Integration
- Fixed "Deploy Weapons" command not working

---

## VoiceAttack Profile
- No update/changes - latest VoiceAttack profile version is v4.5.8 (included in the installer)

### How to update to the latest profile
- Backup and delete existing EliteMining profile
- Open VoiceAttack → Profile > Import Profile
- Select EliteMining-Profile.vap
- Configure your mining hotkeys in the "Custom Key-binds for Mining Control" category

---

## Notes!
- If installer fails with errors, right-click the installer and select "Run as administrator
- If existing detailed reports (HTML) may not display correctly you need to delete all reports completely. (right click meny - Delete Complete Session)

[![Discord](https://img.shields.io/badge/Discord%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5dsF3UshRR)
