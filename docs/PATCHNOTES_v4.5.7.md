# EliteMining v4.5.7 - Patch Notes

**Release Date:** November 18, 2025

## New Features & Improvements

### Mining Analytics Panel
- **Added distance display**: Shows Sol, Home, and Fleet Carrier distances (same as Hotspots Finder)
- **Reorganized header layout**: Ship name and distances now share the same row for cleaner layout
- **Added column header tooltips**: Hover over any column header in Prospector Reports and Mineral Analysis tables to see detailed explanations
- **Improved Mineral column header**: Now displays "Mineral (Threshold%)" to clarify the percentage shown next to each material name
- **Increased Mineral column width**: Better accommodates material names with their announcement thresholds
- **Fixed dialog flicker & centering**: Modal popups (bookmarks, reports, exports, update checks) are now centered and display without flicker for a smoother, consistent UX.

- **Added Total Hits column to Reports**: The Prospector Reports table now shows "Total Hits" (asteroids containing tracked materials).
- **Added Tons/Asteroid metric**: The table now shows average tons per asteroid using the session's hits or derived value.
- **Included metrics in detailed reports**: The enhanced HTML report now shows Total Hits and Tons/Asteroid in the Session Summary, Advanced Analytics, and Raw Session Data sections.
