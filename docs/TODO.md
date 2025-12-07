# EliteMining TODO List

## 🔴 High Priority


- [ ] **Auto populate cmdrs name*** In the post to discord
- [ ] **Ship name auto populate the ship name*** Ship presetd



### Bug Fixes
- [ ] **



---

## 🟡 Medium Priority

### Features
- [ ] **System Finder Tab** - New tab to search nearby systems by criteria (like Inara)
  - Reference System + "Current System" button
  - Max Distance dropdown (50ly, 100ly, 150ly, 200ly, etc.)
  - Filter dropdowns:
    - Allegiance: Any / Federation / Empire / Alliance / Independent
    - Government: Any / Democracy / Corporate / Patronage / Feudal / Dictatorship / etc.
    - Security: Any / High / Medium / Low / Anarchy
    - Economy: Any / Industrial / Agriculture / Extraction / Refinery / etc.
    - Population: Any / Low (<1M) / Medium (1M-100M) / High (100M-1B) / Very High (>1B)
    - State: Any / Expansion / War / Civil War / Boom / Famine / etc.
  - Results table: System | Distance | Security | Allegiance | State | Population | Faction
  - Uses EDData API `/v2/system/name/{system}/nearby` + `/v2/system/name/{system}/status`
  - Context menu: Copy system, Open in Inara, Open in EDSM

- [ ] **Tools Tab** - Create new "Tools" main tab with sub-tabs:
  - Distance Calculator (move from main tabs)
  - Bookmarks (move from main tabs)
  - Future: Material Finder, Route Planner, etc.
  - Reduces main tab bar clutter, groups utility features together

### Code Quality
- [ ] **Auto populate cmdrs name*** In the paost to discord

---

## 🟢 Low Priority

### Future Enhancements
- [ ] Additional language support (French, Spanish, Russian, Portuguese)
- [ ] Community translation guide
- [ ] Weblate integration for web-based translations

---

## ✅ Recently Completed

### December 2, 2025
- [x] Localized Mining Session tab (Bergbau-Sitzung)
- [x] Localized Reports tab (Berichte) 
- [x] Localized Graphs tab (Grafiken)
- [x] Localized Statistics tab (Statistiken)
- [x] Localized Commodity Marketplace (Rohstoffmarkt)
- [x] Localized Distance Calculator (Entfernungsrechner)
- [x] Localized VoiceAttack Controls tab
- [x] Localized Settings tab
- [x] Localized About tab
- [x] Fixed distance info display (Sol, Heimat, Flottenträger)
- [x] Made "Aktuelles System" button consistent across app

---

## Notes

### Fleet Carrier Visit Count Issue
**Problem:** When player is docked on a Fleet Carrier and the FC jumps to a new system, the visit count for the new system may not be recorded properly.

**Expected behavior:** 
- Visit count should increment when FC arrives in new system
- Current system display should update after FC jump
- Distance calculations should update

**Files to check:**
- `app/journal_parser.py` - CarrierJump event handling
- `app/user_database.py` - visit tracking
- `app/main.py` - system update callbacks

---

*Last updated: December 2, 2025*
