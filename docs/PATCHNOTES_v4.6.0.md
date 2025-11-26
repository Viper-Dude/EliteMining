# <img src="https://github.com/Viper-Dude/EliteMining/blob/main/app/Images/logo_multi.ico" width="32" height="32"> EliteMining
**Release Date:** November 26, 2025

## New Features & Improvements

### Hotspots Finder - RES Sites
- Added **RES Only** filter to show rings with Resource Extraction Sites (Hazardous, High, Low)
- Added **RES Site** column showing RES type with mineral abbreviation (e.g., "HAZ Plat", "High LTD")
- Added **Set RES...** right-click option to set RES sites for any ring
- Pre-loaded database with 71 known RES site locations

### Hotspots Finder - Overlaps
- Renamed "Tag Overlap" to **Set Overlap** in right-click menu
- Overlaps Only and RES Only filters are now mutually exclusive
- LS distance now displays correctly for overlap entries
- Pre-loaded database with 161 known overlap locations

### Hotspots Finder - Display Improvements
- Hotspots column now shows full material list (e.g., "Plat (3), Sere (2)") when using Overlaps/RES filters
- RES column now includes mineral abbreviation like the Overlap column
- Improved dark theme styling for Set Overlap and Set RES dialogs

### How to Add/Remove Overlaps and RES Sites
1. Right-click any ring in the search results
2. Select **Set Overlap...** or **Set RES...**
3. Choose a mineral and overlap type (2x/3x) or RES level (Hazardous/High/Low)
4. To remove, select **"None"** and click Save
5. Data is saved locally and appears in future searches

### Bookmarks Tab
- Added **RES Site** column to bookmarks table
- Changed Overlap column format from star icons to **"Plat 2x"** format
- Added **RES Site** and **RES Minerals** fields in bookmark dialog
- **Database sync** - Overlap and RES data from bookmarks syncs to Ring Finder searches
- **Auto-fill from Ring Finder** - Bookmarking a ring pre-fills overlap and RES data

## Hotfix

### Overlaps Only Search
- Fixed LS distance showing "No data" for known overlap locations

### Mining Session
- Fixed Planet/Ring field sometimes showing system name numbers (e.g., "72681A Ring") instead of clean body designation (e.g., "A")

### VoiceAttack Profile
- Updated to **v4.6.0** - Minor optimisation and improvements

### How to update to the latest Voiceattack profile
- Backup and delete existing EliteMining profile
- Open VoiceAttack → Profile > Import Profile
- Select EliteMining-Profile.vap
- Configure your mining hotkeys in the "Custom Key-binds for Mining Control" category

## Notes!
- First search after update may take a moment while loading overlap and RES data
- If installer fails with errors, right-click the installer and select "Run as administrator
- If existing detailed reports (HTML) may not display correctly you need to delete all reports completely. (right click meny - Delete Complete Session)

[![Discord](https://img.shields.io/badge/Discord%20Community-Join%20Server-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/5dsF3UshRR)
