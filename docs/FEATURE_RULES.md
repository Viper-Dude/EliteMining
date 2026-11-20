# EliteMining — Feature Rules

Detailed behavior rules for specific features. Read the matching section before changing that feature. General rules live in [AGENTS.md](../AGENTS.md).

## Mining Sessions and Reports

- Session timestamps without a timezone offset represent local time, despite the historical `timestamp_utc` field name. Use `session_date()` from `app/mining_statistics.py` to normalize local, UTC, and offset timestamps for comparisons; convert to local time for display.
- Use `read_session_report()` from `app/mining_statistics.py` when reading reports for display or analysis. Its bounded cache checks file modification time and size so edits are picked up without repeatedly reading unchanged files.
- Normal session completion updates `sessions_index.csv` incrementally and refreshes Reports and Statistics once each. Full rebuilds are for repair or recovery of a missing or inconsistent index, not routine session saves.
- Mining Missions and Reference use widget-local mousewheel bindings through `bind_mousewheel_recursive()` in `app/app_utils.py`; do not replace or remove global wheel bindings.
- Mark changed graphs dirty and combine visible refreshes. Defer hidden graph updates until shown, and refresh dirty graphs before saving or exporting them.

### Known legacy data

- Report file names saved before 17 November 2026 can contain the wrong body (the System/Body field at stop time instead of the mined ring), and `graph_mappings.json` lacks entries for many older sessions. Find a session's graphs or cards by timestamp and system, or by the body in the report header or `sessions_index.csv`, not by the report file name.

## Commodity Market

- Local coordinate databases are a shortcut to save API calls; missing coordinates must fall back to APIs. For large result sets, batch requests and reuse coordinates per system rather than requesting each row separately. Match returned system names case-insensitively.
- Near System Mining and Trade searches display all matching returned results. Galaxy-Wide has its own age preference (default two days) and an explicit 100/250/500/All result limit (default 250), with shown/total counts. Apply station, pad and age filters before selecting results. Distance sorting measures all matches before limiting; other sorts select their best matches before calculating distances. All keeps every match. Near System preferences and behavior remain independent.
- When merging market records, retain coordinates from another record only if both name the same system; a Fleet Carrier may have jumped since the older record. Stations in the reference system have a distance of zero even when their market record lacks coordinates.
- Multiple Prices uses `MINING_COMMODITY_ORDER` from `app/core/constants.py`, matching the Mining Commodities dropdown. Its mineral choices wrap across the available width to preserve space for results.
