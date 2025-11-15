# EliteMining v4.5.4 - Patch Notes

**Release Date:** November 14, 2025

## 🐛 Bug Fixes

### Hotspots Finder
- **Fixed ring scan auto-selection issue**: Scanned rings no longer appear "clicked" or selected when detected
  - Rings now show green highlight indicator when scanned
  - View still auto-scrolls to show newly scanned rings
  - Removed unwanted automatic selection that made rings appear as if manually clicked

### Journal Import System
- **Fixed journal import skipping hotspots**: Resolved issue where journal imports would skip legitimate hotspot data
  - Journal scans can now properly add new hotspots to the database
  - Journal data can now update existing hotspots that have unknown or missing data sources
  - Fixed logic that incorrectly skipped hotspots when existing data had no coord_source
  - Ensures database synchronization between different installations when importing from the same journal files
  
**Impact:** Users who experienced missing hotspots/systems after journal imports should now see correct counts matching their actual scanned data. Re-importing journals (or deleting `last_journal_scan.json` for full rescan) will add previously skipped entries.

---

## 📝 Technical Details

### Changed Files
- `app/ring_finder.py`: Removed auto-selection of newly scanned rings
- `app/user_database.py`: Fixed journal import skip logic to allow proper hotspot addition and updates

### For Developers
- Removed `selection_set()` call when displaying new ring scans (line ~2913)
- Removed problematic coord_source skip condition that prevented journal data from updating unknown-source entries
- Added proper update logic for journal data to update entries with `coord_source` of None/""/unknown

---

## 🔍 Known Issues
None reported for this release.

---

## 📦 Installation
Standard update - no special installation steps required.

---

**Full Changelog:** https://github.com/[your-repo]/EliteMining/compare/v4.5.3...v4.5.4
