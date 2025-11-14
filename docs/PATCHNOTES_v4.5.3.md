# EliteMining v4.5.3 - Patch Notes

**Release Date:** November 13, 2025

---

## Bug Fixes

### Hotspots Finder
- **Fixed:** Distance filter bug where systems with hotspots were excluded from search results at 300 LY
  - Systems with hotspots are now prioritized and always included in search results
  - 5000 system limit now applies only to systems without hotspots
  - Ensures mining locations are never cut off from search results regardless of distance
- **Fixed:** Hotspot counter now accurately counts actual hotspots instead of database rows
- **Added:** Distance to Sol display for reference system in search interface

---

## Known Issues
- Ardent API does not yet support "Dodec" station type (shows as "SurfaceStation" instead)
- EDSM/EDDN shows Dodec stations as "Planetary Outpost" (legacy name)
- Elite Dangerous journals correctly identify Dodec stations, but marketplace API data sources have not been updated

---
