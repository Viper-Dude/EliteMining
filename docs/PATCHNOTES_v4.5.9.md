# <img src="https://github.com/Viper-Dude/EliteMining/blob/main/app/Images/logo_multi.ico" width="32" height="32"> EliteMining
**Release Date:** November 23, 2025

## New Features & Improvements

### Mining Session Statistics Tab - Major Redesign
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

## Bugfixes

### System Location Tracking
- **Fixed current system not updating after fleet carrier jump** - Distance Calculator, Ring Finder, and Mining Session now properly detect your current system when jumping with fleet carrier
- **Smart timestamp-based system detection** - App scans all journal events and selects the most recent location event by comparing timestamps, ensuring correct system even when multiple location events exist in the journal
- **Enhanced startup system detection** - App now scans journal for most recent FSDJump, Location, Docked, or CarrierJump event to set your system accurately on startup

### Installer
- **Fixed installer not detecting VoiceAttack installations** - Installer now checks C:\Program Files directory explicitly, bypassing system path redirection issues with 32-bit installer on 64-bit Windows
- **Fixed manual VoiceAttack path selection not installing VA profile** - Installer now correctly validates VoiceAttack folder when user manually browses to installation directory

### VoiceAttack Integration
- Fixed "Deploy Weapons" command not working

### Voiceattack Profile
- No update/changes - lates voiceattack version is v4.5.8

### How to update to the latest profile
- Backup and delete existing EliteMining profile
- Open VoiceAttack → Profile > Import Profile
- Select EliteMining-Profile.vap
- Configure your mining hotkeys in the "Custom Key-binds for Mining Control" category

## Notes!
- Statistics tab now automatically updates when mining sessions complete
- If you have issues with statistics display, try refreshing the Reports tab first

[![Discord](https://img.shields.io/badge/Discord%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5dsF3UshRR)
