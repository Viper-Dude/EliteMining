# EliteMining TODO List

## 🔴 High Priority


- [ ] **Auto populate cmdrs name*** In the post to discord
- [ ] **Ship name auto populate the ship name*** Ship presetd



### Bug Fixes
- [ ] **Fix system visit counts on Fleet Carriers** - Visit counts should update when arriving at or sitting on a Fleet Carrier (currently not tracking FC location changes properly)



---

## 🟡 Medium Priority

### Features
- [ ] Bookmarks tab - finish internal localization

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
