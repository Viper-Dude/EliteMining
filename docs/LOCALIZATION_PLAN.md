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

### Future Option: Weblate Integration
**Weblate** (https://weblate.org) is a free, open-source web-based translation platform.

| Feature | Benefit |
|---------|---------|
| Web-based UI | Translators don't need coding skills |
| Git integration | Auto-syncs with GitHub repo |
| Translation memory | Reuses previous translations |
| Machine translation | Auto-suggestions (Google/DeepL) |
| Quality checks | Catches formatting issues |
| Free hosting | Free for open source projects |

**How it would work:**
1. Keep JSON format (compatible with Weblate)
2. Connect Weblate to GitHub repo
3. Translators use web UI at weblate.org
4. Changes auto-commit to repo
5. App pulls latest translations on build

**When to add:** Consider adding Weblate when:
- Community grows and more translators contribute
- Managing PRs for translations becomes overhead
- Need professional translation workflow

**Reference:** https://docs.weblate.org/en/latest/formats.html

---

## Supported Languages
| Code | Language | Status | Priority |
|------|----------|--------|----------|
| en | English (UK/US) | 🟢 Complete | P1 |
| de | German | 🟢 Complete | P1 |
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
**Status:** 🟢 Complete

| Task | Description | Status |
|------|-------------|--------|
| 1.1 | Create `localization/` directory | 🟢 Done |
| 1.2 | Create `__init__.py` with core functions | 🟢 Done |
| 1.3 | Create `strings_en.json` (English baseline) | 🟢 Done |
| 1.4 | Create `materials_en.json` (English materials) | 🟢 Done |
| 1.5 | Migrate `material_utils.py` to use new system | 🟢 Done |
| 1.6 | Create `strings_de.json` (German UI strings) | 🟢 Done |
| 1.7 | Create `materials_de.json` (German materials) | 🟢 Done |
| 1.8 | Initialize localization in main.py | 🟢 Done |
| 1.9 | Test language detection | 🟢 Done |

**Deliverable:** Working localization framework with English + German strings

---

### Phase 2: Ring Finder Localization (Pilot)
**Status:** 🟢 Complete

| Task | Description | Status |
|------|-------------|--------|
| 2.1 | Extract all Ring Finder UI strings | 🟢 Done |
| 2.2 | Replace hardcoded strings with `t()` calls | 🟢 Done |
| 2.3 | Localize dropdown values (ring types) | 🟢 Done |
| 2.4 | Localize material names in dropdown | 🟢 Done |
| 2.5 | Localize tooltips | 🟢 Done |
| 2.6 | Localize result columns | 🟢 Done |
| 2.7 | Create `strings_de.json` for Ring Finder | 🟢 Done |
| 2.8 | Create `materials_de.json` | 🟢 Done |
| 2.9 | Test with German game language | 🟢 Done |

**Deliverable:** Fully localized Ring Finder tab

---

### Phase 3: Mining Session Localization
**Status:** 🟢 Complete

| Task | Description | Status |
|------|-------------|--------|
| 3.1 | Extract Mining Session UI strings | 🟢 Done |
| 3.2 | Replace hardcoded strings | 🟢 Done |
| 3.3 | Localize Cargo Monitor | 🟢 Done |
| 3.4 | Localize Material Analysis table | 🟢 Done |
| 3.5 | Localize Prospector results | 🟢 Done |
| 3.6 | Localize session buttons (Start, Pause, End, Cancel) | 🟢 Done |
| 3.7 | Localize checkboxes (Auto-start, Prompt when full, Multi-Session) | 🟢 Done |
| 3.8 | Localize sub-tabs (Mining Analytics, Graphs, Reports, Statistics) | 🟢 Done |
| 3.9 | Add German translations | 🟢 Done |
| 3.10 | Test with German game language | 🟢 Done |

**Deliverable:** Fully localized Mining Session tab

---

### Phase 4: Reports Localization
**Status:** 🟢 Complete

| Task | Description | Status |
|------|-------------|--------|
| 4.1 | Extract Reports UI strings | 🟢 Done |
| 4.2 | Localize column headers | 🟢 Done |
| 4.3 | Localize Reports table (Minerals column) | 🟢 Done |
| 4.4 | Localize filter dropdown options | 🟢 Done |
| 4.5 | Localize buttons (Rebuild CSV, Open Folder, Export CSV, Share to Discord, Mining Card) | 🟢 Done |
| 4.6 | Add German translations | 🟢 Done |
| 4.7 | Test with German game language | 🟢 Done |

**Deliverable:** Fully localized Reports tab

---

### Phase 5: Remaining Tabs
**Status:** 🟢 Complete

| Task | Description | Status |
|------|-------------|--------|
| 5.1 | Commodity Market tab | 🟢 Done |
| 5.2 | Distance Calculator tab | 🟢 Done |
| 5.3 | VoiceAttack Controls tab | 🟢 Done |
| 5.4 | Bookmarks tab | 🟢 Done |
| 5.5 | Settings tab | 🟢 Done |
| 5.6 | About tab | 🟢 Done |
| 5.7 | Main window (status bar, menus) | 🟢 Done |
| 5.8 | Sidebar (Ship Presets, Cargo Monitor) | 🟢 Done |
| 5.9 | Add German translations for all | 🟢 Done |
| 5.10 | Context menus (all tables) | 🟢 Done |
| 5.11 | Dialogs (Add/Edit Bookmark, Set Overlap, Set RES) | 🟢 Done |

**Deliverable:** Fully localized application

---

### Phase 6: Tooltips Localization
**Status:** 🟢 Complete

**Overview:** ~120+ ToolTip calls across the application have been localized.

| File | Count | Status |
|------|-------|--------|
| `main.py` | ~45 | 🟢 Done |
| `prospector_panel.py` | ~55 | 🟢 Done |
| `ring_finder.py` | ~12 | 🟢 Done |
| `mining_charts.py` | ~6 | 🟢 Done |

| Task | Description | Status |
|------|-------------|--------|
| 6.1 | Add `tooltips` section to JSON files | 🟢 Done |
| 6.2 | Ring Finder tooltips | 🟢 Done |
| 6.3 | Distance Calculator tooltips (~8) | 🟢 Done |
| 6.4 | Commodity Marketplace tooltips (~12) | 🟢 Done |
| 6.5 | Mining Session/Prospector tooltips (~25) | 🟢 Done |
| 6.6 | Settings tooltips (~15) | 🟢 Done |
| 6.7 | Reports/Bookmarks tooltips (~15) | 🟢 Done |
| 6.8 | Charts tooltips (~6) | 🟢 Done |
| 6.9 | German translations for all tooltips | 🟢 Done |
| 6.10 | Table header tooltips (Prospektor-Berichte) | 🟢 Done |
| 6.11 | Table header tooltips (Materialanalyse - 9 cols) | 🟢 Done |
| 6.12 | Table header tooltips (Berichte - 19 cols) | 🟢 Done |
| 6.13 | VoiceAttack Controls - Timers tooltips (6) | 🟢 Done |
| 6.14 | VoiceAttack Controls - Toggles tooltips (9) | 🟢 Done |
| 6.15 | Fix Unicode emoji crash (U+2705 in print statements) | 🟢 Done |
| 6.16 | Session End Dialogs (Refinery, Comment) | 🟢 Done |
| 6.17 | Add Refinery Contents Dialog | 🟢 Done |
| 6.18 | Material Selector Dialog | 🟢 Done |

**Bug Fix:** Replaced `✅` emoji (U+2705) in print statements with `[OK]` - Windows console couldn't encode the character, causing app crash on startup.

**Deliverable:** All major tooltips localized in German

---

### Phase 7: Additional Languages & Language Switcher
**Status:** 🟡 In Progress

| Task | Description | Status |
|------|-------------|--------|
| 7.1 | Language switcher UI (flag icon in status bar) | 🟢 Done |
| 7.2 | Flag images for EN/DE | 🟢 Done |
| 7.3 | Click-to-change popup menu | 🟢 Done |
| 7.4 | Themed restart dialog | 🟢 Done |
| 7.5 | Tooltip for language switcher | 🟢 Done |
| 7.6 | French translations | 🔴 Not Started |
| 7.7 | Spanish translations | 🔴 Not Started |
| 7.8 | Russian translations | 🔴 Not Started |
| 7.9 | Portuguese translations | 🔴 Not Started |
| 7.10 | Create translation guide for community | 🔴 Not Started |

**Deliverable:** Multi-language support with easy language switching

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
| 1 | Framework Setup | 🟢 Complete | 100% |
| 2 | Ring Finder (Hotspot-Finder) | 🟢 Complete | 100% |
| 3 | Mining Session (Bergbau-Sitzung) | 🟢 Complete | 100% |
| 4 | Reports (Berichte) | 🟢 Complete | 100% |
| 5 | Remaining Tabs + Context Menus + Dialogs | 🟢 Complete | 100% |
| 5b | Dynamic Status Messages | 🟢 Complete | 100% |
| 6 | Tooltips Localization | 🟢 Complete | 100% |
| 7 | Language Switcher & Additional Languages | 🟡 In Progress | 50% |

**Overall Progress: 99%** (Language switcher complete, additional languages pending)

---

## Status Now (For New Chat Sessions)

### ✅ What's Working:
1. **Localization Framework** - Complete
   - `app/localization/` directory with `__init__.py`, JSON string files
   - `strings_en.json`, `strings_de.json` for UI
   - `materials_en.json`, `materials_de.json` for materials + abbreviations

2. **Language Settings**
   - Language selector in **Settings > General Settings**
   - Saved to `config.json` as `"language": "de"` or `"auto"`
   - User preference respected (game detection doesn't override manual setting)

3. **German UI Working:**
   - **Main Tabs:** Bergbau-Sitzung, Hotspot-Finder, Rohstoffmarkt, Entfernungsrechner, VoiceAttack-Steuerung, Lesezeichen, Einstellungen, Über
   - **Sidebar:** Schiff-Presets (VoiceAttack), Frachtüberwachung, Frachtstatus, Drohne
   - **Buttons:** Importieren, Anwenden, Aktuelles System, Suchen, Dunkles Design
   - **Ring Finder:** All labels, column headers, ring types, material abbreviations
   - **Mining Session:** 
     - Buttons: Start, Pause, Ende, Abbrechen
     - Checkboxes: Auto-Start, Nachfrage bei voll, Multi-Sitzung
     - Labels: Sitzungsübersicht, Vergangen
     - Sub-tabs: Bergbau-Analytik, Grafiken, Berichte, Statistiken
     - Tables: Prospektor-Berichte, Materialanalyse (all column headers)
     - Distance info: Sol, Heimat, Flottenträger
   - **Reports Tab:**
     - Column headers: Datum/Zeit, Dauer, Typ, Schiff, System, Planet/Ring, etc.
     - Filter dropdown: Alle Sitzungen, Letzter Tag, Letzte 7 Tage, Hohe Ausbeute, etc.
     - Buttons: CSV neu erstellen, Ordner öffnen, CSV exportieren, Auf Discord teilen, Bergbau-Karte
   - **Graphs Tab:**
     - Buttons: Aktualisieren, Auto-Aktualisierung, PNG exportieren, Alle exportieren
     - Chart titles: Ausbeute-Zeitverlauf, Mineralien-Vergleich
   - **Statistics Tab:**
     - All section headers and labels in German
     - Top 5 Beste Systeme table
   - **Commodity Marketplace:**
     - All labels: Rohstoffpreise suchen, Nahe System, Galaxisweit, Verkaufen, Kaufen
     - Filters: Station, Träger ausschließen, Große Landeplätze, Sortieren nach, Max. Alter
     - Column headers: Standort, Typ, Pad, Entfernung, Nachfrage/Angebot, Preis, Aktualisiert
     - **Commodity dropdown:** Localized mineral names (Platin, Painit, Alexandrit, Tieftemperaturdiamanten, etc.)
     - **Language-specific positioning:** All dropdown labels have separate German/English padding values
   - **Distance Calculator:**
     - Configuration: Konfiguration, Aktuelles System, Heimatsystem, Flottenträger
     - Calculator: System-Entfernungsrechner, System A/B, Entfernung berechnen
     - Results: Ergebnisse, Entfernung zu Sol, Besuche, Koordinaten
     - Labels: LY von Sol, LY von aktuellem
   - **VoiceAttack Controls:**
     - Sub-tabs: Bergbau-Steuerung, Feuergruppen & Feuertasten
   - **Settings:**
     - Sub-tabs: Ankündigungen, Allgemeine Einstellungen
   - **About:**
     - Description: Bergbau-Begleiter für Elite Dangerous
     - Links: Discord, Reddit, GitHub, Dokumentation, Fehler melden
   - **Cargo Monitor:** Drohne, Frachtüberwachung, Hinweis: Inhalt in Raffinerie nicht in Summen enthalten

4. **Language-Specific UI Positioning (Commodity Marketplace)**
   All dropdown labels have separate padding values for German/English to ensure proper alignment:
   
   | Element | Line | German (left, gap) | English (left, gap) |
   |---------|------|-------------------|---------------------|
   | **Commodity:** | ~11953 | `(59, 34)` | `(59, 17)` |
   | **Sort by:** | ~12033 | `(0, 3)` | `(55, 43)` |
   | **Max age:** | ~12059 | `(369, 26)` | `(365, 35)` |

### 🔜 Next Steps (Phase 6 - Tooltips):
All ~103 tooltips across the app need to be localized. Currently all tooltips display in English.

**Priority order:**
1. Ring Finder tooltips (finish remaining ~5)
2. Distance Calculator tooltips (~8)
3. Marketplace tooltips (~12)
4. Mining Session tooltips (~25)
5. Settings tooltips (~15)
6. Reports/Bookmarks tooltips (~15)
7. Charts tooltips (~6)

### 📁 Key Files:
- `app/main.py` - main app with localization init
- `app/ring_finder.py` - Hotspot Finder tab
- `app/prospector_panel.py` - Mining Session tab (15,000+ lines)
- `app/localization/__init__.py` - core localization functions
- `app/localization/strings_en.json` - English UI strings
- `app/localization/strings_de.json` - German UI strings
- `docs/LOCALIZATION_PLAN.md` - this file

---

## Known Issues (To Fix)

*No critical known issues at this time.*

---

## Notes & Decisions

### 2024-12-01 - Initial Planning
- Decision: Use JSON files for translations (easier for non-developers)
- Decision: English as fallback for all missing strings
- Decision: Database stays English-only for compatibility
- Decision: Start with Ring Finder as pilot module
- Decision: **Hybrid approach** - Local JSON + GitHub community translations
- Decision: Optional online translation updates (future feature)
- Decision: **Weblate** noted as future option for web-based translation management
- Existing: `material_utils.py` already has German abbreviations (will be migrated)

### 2024-12-01 - Phase 1 Complete
- Created `app/localization/` directory structure
- Implemented `__init__.py` with core functions: `init()`, `t()`, `get_abbr()`, `get_material()`, `to_english()`
- Created `strings_en.json` and `strings_de.json` for UI strings
- Created `materials_en.json` and `materials_de.json` for material names + abbreviations
- Updated `material_utils.py` as backward-compatible wrapper
- Added localization initialization to `main.py`
- Tested: Language detection working (German detected from journal)
- Tested: Abbreviations working (`LTD` → `TTD` for German)

### 2024-12-02 - Phase 3, 4 & 5 Complete
- **Mining Session Tab (Bergbau-Sitzung)** fully localized:
  - Session buttons: Start, Pause, Ende, Abbrechen (with dynamic Pause/Weiter toggle)
  - Checkboxes: Auto-Start, Nachfrage bei voll, Multi-Sitzung
  - Labels: Sitzungsübersicht, Vergangen, Entfernungen, Schiff, System, Planet/Ring
  - Sub-tabs: Bergbau-Analytik, Grafiken, Berichte, Statistiken
  - Prospektor-Berichte table: Mineralien, Asteroid-Inhalt, Zeit
  - Materialanalyse table: Mineral (Thr%), Tonnen, T/Std, T/Ast, Durchschn %, Best %, Aktuell %, Treffer
  - Distance info: Sol, Heimat, Flottenträger (LY von Sol, LY von aktuellem)
  - Double-click hint localized

- **Reports Tab (Berichte)** fully localized:
  - All 19 column headers (Datum/Zeit, Dauer, Typ, Schiff, System, Planet/Ring, Gesamt Tonnen, T/Std, etc.)
  - Filter dropdown with 16 options (Alle Sitzungen, Letzter Tag, Letzte 7 Tage, Hohe Ausbeute, etc.)
  - Filter logic updated to use internal keys instead of display text
  - Buttons: CSV neu erstellen, Ordner öffnen, CSV exportieren, Auf Discord teilen, Bergbau-Karte

- **Graphs Tab (Grafiken)** fully localized:
  - Buttons: Aktualisieren, Auto-Aktualisierung, PNG, Alle
  - Chart titles: Ausbeute-Zeitverlauf, Mineralien-Vergleich

- **Statistics Tab (Statistiken)** fully localized:
  - Section headers: Gesamtstatistik, Bestleistungen (Records)
  - All labels (Gesamte Sitzungen, Gesamte Bergbauzeit, etc.)
  - Top 5 Beste Systeme table

- **Commodity Marketplace (Rohstoffmarkt)** fully localized:
  - Search section: Rohstoffpreise suchen
  - Radio buttons: Nahe System (500 LY), Galaxisweit (Top 30)
  - Checkboxes: Verkaufen, Kaufen, Träger ausschließen, Große Landeplätze
  - Filters: Station, Sortieren nach, Max. Alter
  - Column headers: Standort, Typ, Pad, Entfernung, Nachfrage/Angebot, Preis, Aktualisiert
  - Buttons: Aktuelles System, Suchen

- **Distance Calculator (Entfernungsrechner)** fully localized:
  - Configuration: Konfiguration, Aktuelles System, Heimatsystem, Flottenträger
  - Calculator: System-Entfernungsrechner, System A/B
  - Buttons: Aktuelles System, Heimat, FT, Standorte aktualisieren, Entfernung berechnen
  - Results: Ergebnisse, Entfernung, System A/B Info, Entfernung zu Sol, Besuche, Koordinaten
  - Dynamic labels: LY von Sol, LY von aktuellem, Berechnung abgeschlossen

- **VoiceAttack Controls (VoiceAttack-Steuerung)** fully localized:
  - Sub-tabs: Bergbau-Steuerung, Feuergruppen & Feuertasten

- **Settings (Einstellungen)** fully localized:
  - Sub-tabs: Ankündigungen, Allgemeine Einstellungen

- **About (Über)** fully localized:
  - Description: Bergbau-Begleiter für Elite Dangerous
  - Copyright, license text
  - Link buttons: Discord, Reddit, GitHub, Dokumentation, Fehler melden

- **Cargo Monitor** localized:
  - Drohne (instead of Limpet)
  - Hinweis: Inhalt in Raffinerie nicht in Summen enthalten
  - Ingenieur-Materialien header

- **Consistency improvements:**
  - "Aktuelles System" button text consistent across Ring Finder, Distance Calculator, Marketplace

### 2024-12-02 - Context Menus & Dialogs Complete
- **All Context Menus (Right-Click Menus)** fully localized:
  - **Ship Presets:** Als neu speichern, Überschreiben, Bearbeiten, Duplizieren, Umbenennen, Exportieren, Importieren, Alle erweitern, Alle einklappen, Löschen
  - **Ring Finder:** Systemname kopieren, Überlappung setzen..., RES setzen..., Diesen Standort als Lesezeichen speichern
  - **Reports Tab:** Bericht öffnen (TXT/HTML), Detaillierten Bericht erstellen, Systemname kopieren, Auf Discord teilen, Bergbau-Karte erstellen, Zeilenumbruch aktivieren/deaktivieren, Raffinerieinhalt hinzufügen, Löschen-Optionen
  - **Bookmarks Tab:** Systemname kopieren, Lesezeichen bearbeiten, Ausgewählte löschen
  - **Commodity Marketplace:** In Inara öffnen, In EDSM öffnen, Systemname kopieren

- **All Dialogs** fully localized:
  - **Add/Edit Bookmark Dialog:** Title, all field labels (System, Körper/Ring, Ringtyp, Gefundene Mineralien, Durchschn. Ausbeute %, Überlappungs-Mineralien, Überlappungstyp, RES-Standort, RES-Mineralien, Bewertung, Notizen), buttons (Speichern, Abbrechen)
  - **Set Overlap Dialog:** Title (Überlappung setzen), labels (Überlappung setzen für:, Mineral:, Überlappung:), options (Keine, 2x, 3x), buttons
  - **Set RES Dialog:** Title (RES-Standort setzen), labels (RES-Standort setzen für:, Mineral:, RES-Typ:), options (Keine, Haz, High, Low), buttons

### 2024-12-02 - Dynamic Status Messages Complete
- **Ring Finder Status Messages** fully localized:
  - Searching: "⏳ Suche nach Ringen..."
  - Loading: "Lade Systemdatenbank..."
  - Ready: "Bereit - Community-Datenbank geladen"
  - Found results: "{count} Standort(e) in der Nähe von '{system}' gefunden"
  - Found materials: "{count} {material} Standort(e) in der Nähe von '{system}' gefunden"
  - No results: "Keine Ringe innerhalb der Suchkriterien für '{system}' gefunden"
  - Current system: "Aktuelles System: {system}"
  - Coordinates not available: "Aktuelles System: {system} (Koordinaten nicht verfügbar)"
  - Database info: "Gesamt: {hotspots} Hotspots in {systems} Systemen"

- **Commodity Marketplace Status Messages** fully localized:
  - Searching: "🔍 Suche nach Stationen zum Kaufen/Verkaufen..."
  - Calculating: "⏳ Berechne Entfernungen..."
  - Found stations: "✓ {count} Stationen gefunden (Top 30 nach Preis)"
  - No results: "❌ Keine Ergebnisse gefunden"
  - Select commodity: "❌ Bitte wählen Sie einen Rohstoff"
  - Enter system: "❌ Bitte geben Sie ein Referenzsystem ein"
  - All carriers warning: "⚠️ {count} Stationen gefunden, aber alle sind Flottenträger..."
  - Filter warning: "⚠️ {count} Stationen gefunden, aber keine entspricht Ihren Filtern..."
  - Copied: "✓ '{system}' in Zwischenablage kopiert"
  - Export success: "✅ {count} Ergebnisse exportiert nach {path}"
  - Export failed: "❌ Export fehlgeschlagen: {error}"

- **Status Bar (CMDR Info)** fully localized:
  - "CMDR:" (unchanged)
  - "| Akt. Syst:" (Current System)
  - "| Besuche:" (Visits)
  - "| Syst. in Route:" (Systems in Route)
  - "| Ges. Syst:" (Total Systems)
  - Tooltip: "Gesamt besuchte Systeme (aus Spielstatistik). Aktualisiert beim Neustart von Elite Dangerous."

- **Cargo Monitor Status Messages** fully localized:
  - Empty cargo: "📦 Leerer Frachtraum"
  - Start mining: "⛏️ Mit dem Bergbau beginnen!"
  - Total: "{count}t gesamt"
  - No details: "💡 Keine Artikeldetails"

- **Announcements Settings** fully localized:
  - "Kern-Asteroiden" (Core Asteroids)
  - "Normale Asteroiden" (Non-Core Asteroids)
  - Tooltips translated

- **VoiceAttack Tip** fully localized:
  - "Alle Profilbefehle stoppen" (Stop all profile commands)

### Tooltips Identified (~103 total):
- Tooltips remain in English and will be Phase 6
- main.py: ~40 tooltips
- prospector_panel.py: ~45 tooltips  
- ring_finder.py: ~12 tooltips (some already done)
- mining_charts.py: ~6 tooltips

### 2024-12-03 - Language Switcher Complete
- **Language Flag Switcher** added to status bar (bottom right, next to theme button):
  - Single flag icon showing current language (UK flag for English, German flag for German)
  - Click to open popup menu with all available languages
  - Checkmark indicates current selection
  - Flag images loaded from `app/Images/` folder (`united-kingdom.png`, `german-flag.png`)
  - Images auto-scaled to ~21px for proper display
  - Hover tooltip: "Click to change language" / "Klicken, um die Sprache zu ändern"
  - Themed restart dialog (centered, dark/orange style) after language change
  - Theme button resized to match flag height for visual consistency

### What's Working in German UI (Updated):
- ✅ All main tabs (8 tabs fully translated)
- ✅ Ring Finder: Complete
- ✅ Mining Session: Complete (including distance info: Sol, Heimat, Flottenträger)
- ✅ Reports: Complete
- ✅ Graphs: Complete
- ✅ Statistics: Complete
- ✅ Commodity Marketplace: Complete
- ✅ Distance Calculator: Complete
- ✅ VoiceAttack Controls: Complete (sub-tab names)
- ✅ Settings: Complete (sub-tab names)
- ✅ About: Complete
- ✅ Sidebar (Schiff-Presets, Frachtüberwachung)
- ✅ Material abbreviations (TTD, LeOp, Brom, Gran, etc.)
- ✅ All context menus (right-click menus)
- ✅ All dialogs (Add/Edit Bookmark, Set Overlap, Set RES)
- ✅ All dynamic status messages (Ring Finder, Commodity Marketplace, Cargo Monitor)
- ✅ Status bar (CMDR info line)
- ✅ Announcement settings (Core/Non-Core Asteroids)
- ✅ Language switcher (flag icon with popup menu)
- ❌ Additional languages: French, Spanish, Russian, Portuguese (not started)

---

## References
- Elite Dangerous supported languages: English, German, French, Spanish, Russian, Portuguese
- Journal `Fileheader` language field format: `"language":"German/DE"`
- Existing material translations in `journal_parser.py` MATERIAL_NAME_MAP
