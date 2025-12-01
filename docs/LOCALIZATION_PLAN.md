# EliteMining Localization Plan

## Overview
This document describes the plan to implement a full localization system for EliteMining, supporting multiple languages based on the Elite Dangerous in-game language setting.

## Platform Approach: Hybrid (Local + GitHub)

### Architecture Decision
**Chosen: Option C - Hybrid Approach**

| Component | Description |
|-----------|-------------|
| **Local JSON Files** | Bundled with app, works offline, fast loading |
| **GitHub Translations** | Community contributes via PRs to `/translations` folder |
| **Optional Updates** | App can check for newer translations on startup (future) |

**Benefits:**
- ✅ Works offline (local files)
- ✅ Community can contribute via GitHub
- ✅ No external service dependency
- ✅ No cost
- ✅ Version controlled with code
- ✅ Updates can be pushed between releases (optional future feature)

---

## Supported Languages
| Code | Language | Status | Priority |
|------|----------|--------|----------|
| en | English (UK/US) | 🟡 Baseline | P1 |
| de | German | 🔴 Not Started | P1 |
| fr | French | 🔴 Not Started | P2 |
| es | Spanish | 🔴 Not Started | P2 |
| ru | Russian | 🔴 Not Started | P3 |
| pt | Portuguese | 🔴 Not Started | P3 |

**Status Legend:** 🟢 Complete | 🟡 In Progress | 🔴 Not Started

---

## Architecture

### Directory Structure
```
app/
  localization/
    __init__.py              # Localization manager & helper functions
    strings_en.json          # English UI strings
    strings_de.json          # German UI strings
    strings_fr.json          # French UI strings (future)
    materials_en.json        # English material names + abbreviations
    materials_de.json        # German material names + abbreviations
    materials_fr.json        # French material names (future)
```

### JSON File Structure

#### UI Strings (strings_xx.json)
```json
{
  "meta": {
    "language": "English",
    "code": "en",
    "version": "1.0",
    "author": "EliteMining Team"
  },
  "common": {
    "search": "Search",
    "cancel": "Cancel",
    "save": "Save",
    "close": "Close",
    "apply": "Apply",
    "reset": "Reset",
    "all": "All",
    "none": "None",
    "yes": "Yes",
    "no": "No"
  },
  "tabs": {
    "mining_session": "Mining Session",
    "hotspots_finder": "Hotspots Finder",
    "commodity_market": "Commodity Market",
    "distance_calculator": "Distance Calculator",
    "voiceattack_controls": "VoiceAttack Controls",
    "bookmarks": "Bookmarks",
    "settings": "Settings",
    "about": "About"
  },
  "ring_finder": {
    "ring_type": "Ring Type",
    "mineral": "Mineral",
    "all_minerals": "All Minerals",
    "metallic": "Metallic",
    "rocky": "Rocky",
    "icy": "Icy",
    "metal_rich": "Metal Rich",
    "max_distance": "Max Distance (LY)",
    "max_results": "Max Results",
    "overlaps_only": "Overlaps Only",
    "res_only": "RES Only",
    "auto_search": "Auto-Search",
    "no_results": "No hotspots found within {distance} LY",
    "searching": "Searching...",
    "results_found": "Found {count} results"
  },
  "mining_session": {
    "start_session": "Start Session",
    "stop_session": "Stop Session",
    "elapsed": "Elapsed",
    "cargo_status": "Cargo Status",
    "limpets": "Limpets",
    "total_mined": "Total Mined",
    "yield": "Yield %"
  },
  "reports": {
    "minerals_column": "Minerals (Tonnage, Yields & T/hr)",
    "engineering_materials": "Engineering Materials",
    "export_csv": "Export CSV",
    "open_folder": "Open Folder",
    "mining_card": "Mining Card"
  },
  "settings": {
    "journal_directory": "Journal Directory",
    "announcement_thresholds": "Announcement Thresholds",
    "voiceattack_integration": "VoiceAttack Integration",
    "theme": "Theme",
    "dark_theme": "Dark Theme",
    "light_theme": "Light Theme"
  },
  "messages": {
    "error_no_journal": "No journal files found",
    "error_connection": "Connection error",
    "session_saved": "Session saved successfully",
    "hotspot_added": "New hotspot discovered!"
  },
  "tooltips": {
    "ring_type_filter": "Filter by ring type:\n- Metallic: Platinum, Gold, Silver\n- Icy: LTDs, Tritium, Bromellite\n- Rocky: Alexandrite, Benitoite, Opals\n- Metal Rich: Painite, Osmium",
    "mineral_filter": "Filter by specific material:\nAutomatically shows only confirmed hotspots"
  }
}
```

#### Materials (materials_xx.json)
```json
{
  "meta": {
    "language": "English",
    "code": "en",
    "version": "1.0"
  },
  "names": {
    "Platinum": "Platinum",
    "Painite": "Painite",
    "Osmium": "Osmium",
    "Low Temperature Diamonds": "Low Temperature Diamonds",
    "Void Opals": "Void Opals"
  },
  "abbreviations": {
    "Platinum": "Plat",
    "Painite": "Pain",
    "Osmium": "Osmi",
    "Low Temperature Diamonds": "LTD",
    "Void Opals": "Opals"
  },
  "to_english": {
    "Platinum": "Platinum"
  }
}
```

### Localization Manager (__init__.py)
```python
# Key functions to implement:
def init(journal_dir=None)          # Initialize and detect language
def get_language() -> str           # Get current language code
def set_language(code: str)         # Manually set language
def t(key: str, **kwargs) -> str    # Get translated UI string
def get_material(name: str) -> str  # Get localized material name
def get_abbr(name: str) -> str      # Get material abbreviation
def to_english(name: str) -> str    # Convert localized name to English (for DB)
```

---

## Implementation Phases

### Phase 1: Framework Setup
**Status:** 🔴 Not Started

| Task | Description | Status |
|------|-------------|--------|
| 1.1 | Create `localization/` directory | 🔴 |
| 1.2 | Create `__init__.py` with core functions | 🔴 |
| 1.3 | Create `strings_en.json` (English baseline) | 🔴 |
| 1.4 | Create `materials_en.json` (English materials) | 🔴 |
| 1.5 | Migrate `material_utils.py` to use new system | 🔴 |
| 1.6 | Test language detection | 🔴 |

**Deliverable:** Working localization framework with English strings

---

### Phase 2: Ring Finder Localization (Pilot)
**Status:** 🔴 Not Started

| Task | Description | Status |
|------|-------------|--------|
| 2.1 | Extract all Ring Finder UI strings | 🔴 |
| 2.2 | Replace hardcoded strings with `t()` calls | 🔴 |
| 2.3 | Localize dropdown values (ring types) | 🔴 |
| 2.4 | Localize material names in dropdown | 🔴 |
| 2.5 | Localize tooltips | 🔴 |
| 2.6 | Localize result columns | 🔴 |
| 2.7 | Create `strings_de.json` for Ring Finder | 🔴 |
| 2.8 | Create `materials_de.json` | 🔴 |
| 2.9 | Test with German game language | 🔴 |

**Deliverable:** Fully localized Ring Finder tab

---

### Phase 3: Mining Session Localization
**Status:** 🔴 Not Started

| Task | Description | Status |
|------|-------------|--------|
| 3.1 | Extract Mining Session UI strings | 🔴 |
| 3.2 | Replace hardcoded strings | 🔴 |
| 3.3 | Localize Cargo Monitor | 🔴 |
| 3.4 | Localize Material Analysis table | 🔴 |
| 3.5 | Localize Prospector results | 🔴 |
| 3.6 | Add German translations | 🔴 |
| 3.7 | Test with German game language | 🔴 |

**Deliverable:** Fully localized Mining Session tab

---

### Phase 4: Reports Localization
**Status:** 🔴 Not Started

| Task | Description | Status |
|------|-------------|--------|
| 4.1 | Extract Reports UI strings | 🔴 |
| 4.2 | Localize column headers | 🔴 |
| 4.3 | Localize Reports table (Minerals column) | 🔴 |
| 4.4 | Localize export formats (keep English for files?) | 🔴 |
| 4.5 | Add German translations | 🔴 |
| 4.6 | Test with German game language | 🔴 |

**Deliverable:** Fully localized Reports tab

---

### Phase 5: Remaining Tabs
**Status:** 🔴 Not Started

| Task | Description | Status |
|------|-------------|--------|
| 5.1 | Commodity Market tab | 🔴 |
| 5.2 | Distance Calculator tab | 🔴 |
| 5.3 | VoiceAttack Controls tab | 🔴 |
| 5.4 | Bookmarks tab | 🔴 |
| 5.5 | Settings tab | 🔴 |
| 5.6 | About tab | 🔴 |
| 5.7 | Main window (status bar, menus) | 🔴 |
| 5.8 | Add German translations for all | 🔴 |

**Deliverable:** Fully localized application

---

### Phase 6: Additional Languages
**Status:** 🔴 Not Started

| Task | Description | Status |
|------|-------------|--------|
| 6.1 | French translations | 🔴 |
| 6.2 | Spanish translations | 🔴 |
| 6.3 | Russian translations | 🔴 |
| 6.4 | Portuguese translations | 🔴 |
| 6.5 | Create translation guide for community | 🔴 |

**Deliverable:** Multi-language support

---

## Technical Notes

### Language Detection
- Automatically detected from Elite Dangerous journal `Fileheader` event
- Field: `"language":"German/DE"`, `"language":"English/UK"`, etc.
- Detection runs at app startup and when new journal file is created
- Can be manually overridden in Settings (future)

### Database Compatibility
- Database always stores **English** material names
- Localized names converted to English before DB queries
- `to_english()` function handles reverse mapping

### Fallback Behavior
- If translation missing, fall back to English
- Log warning for missing translations (dev mode)

### Performance
- JSON files loaded once at startup
- Strings cached in memory
- No performance impact during normal operation

### File Exports
- CSV/TXT exports: Keep English for data compatibility
- HTML reports: Use localized strings for display
- Consider adding export language option (future)

---

## Testing Checklist

### Per-Phase Testing
- [ ] All UI strings display correctly
- [ ] No truncation or overflow issues
- [ ] Special characters display correctly (ä, ö, ü, ß)
- [ ] Material names match in-game exactly
- [ ] Dropdowns show correct localized values
- [ ] Database queries work with localized input
- [ ] Fallback to English works for missing strings

### Full Integration Testing
- [ ] Switch game to German, restart app
- [ ] Switch game to English, restart app
- [ ] All tabs display correctly
- [ ] Reports generate correctly
- [ ] No console errors

---

## Current Status Summary

| Phase | Description | Status | Completion |
|-------|-------------|--------|------------|
| 1 | Framework Setup | 🔴 Not Started | 0% |
| 2 | Ring Finder | 🔴 Not Started | 0% |
| 3 | Mining Session | 🔴 Not Started | 0% |
| 4 | Reports | 🔴 Not Started | 0% |
| 5 | Remaining Tabs | 🔴 Not Started | 0% |
| 6 | Additional Languages | 🔴 Not Started | 0% |

**Overall Progress: 0%**

---

## Notes & Decisions

### 2024-12-01 - Initial Planning
- Decision: Use JSON files for translations (easier for non-developers)
- Decision: English as fallback for all missing strings
- Decision: Database stays English-only for compatibility
- Decision: Start with Ring Finder as pilot module
- Decision: **Hybrid approach** - Local JSON + GitHub community translations
- Decision: Optional online translation updates (future feature)
- Existing: `material_utils.py` already has German abbreviations (will be migrated)

---

## References
- Elite Dangerous supported languages: English, German, French, Spanish, Russian, Portuguese
- Journal `Fileheader` language field format: `"language":"German/DE"`
- Existing material translations in `journal_parser.py` MATERIAL_NAME_MAP
