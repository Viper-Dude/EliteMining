# EliteMining — Architecture Notes

Background moved out of [AGENTS.md](../AGENTS.md). Read when working on data fetching, Ring Finder, powerplay or the EDDN cache.

## Data Sources

- Elite Dangerous journal files (`~/Saved Games/Frontier Developments/Elite Dangerous/`)
- EDDN live feed — commodity prices, powerplay, station metadata
- Spansh API — ring/system search, reserve levels
- Ardent API — commodity market data (`marketplace_api.py`)
- Inara — powerplay data (HTML scrape with bot-challenge solving)
- Local SQLite: `marketplace_cache.db` (EDDN cache) and the user database (`user_database.py`)

## Main Modules

- `app/main.py` — multi-tabbed Tkinter app, CargoMonitor, dark theme, ToolTip system
- `app/ring_finder.py` — Ring Finder tab: Spansh/local search, results treeview, context menu, PP column
- `app/system_finder_api.py` — Spansh API wrapper + Inara powerplay HTML fetch
- `app/marketplace_api.py` — commodity market lookups (Ardent and other sources)
- `app/eddn_listener.py` — EDDN ZMQ listener, writes to `marketplace_cache.db`
- `app/journal_parser.py` — journal file monitoring and event parsing
- `app/user_database.py` — local ring/hotspot/visit database
- `app/prospector_panel.py` — prospector session tracking from journal
- `app/config.py` — rate-limited config load/save, path detection, theme
- `app/localization/` — `strings_en.json` + `strings_de.json`; use `from localization import t`

## Threading Pattern

Background work uses a daemon thread + `parent.after(0, callback)` to run UI updates on the main thread:

```python
threading.Thread(target=self._worker, args=(arg,), daemon=True).start()

def _worker(self, arg):
    result = do_work(arg)
    self.parent.after(0, lambda: self._complete(result))
```

`ring_finder.py` imports `SystemFinderAPI` inline inside thread worker methods, not at module top.

## Ring Finder Powerplay Fetch (Inara)

- `SystemFinderAPI.fetch_and_store_powerplay_from_inara(system_name)` in `system_finder_api.py` uses `requests.Session()` with a browser User-Agent, detects and solves Inara's bot challenge page (`validatechallenge.php`), stores the result in the `system_powerplay` table, and returns `{'controlling_power': ..., 'power_state': ...}` or `None`.
- Batch fetch is sequential and rate-limited by the `PP_FETCH_MAX_BATCH` and `PP_FETCH_DELAY_SECS` class constants, defined in both `ring_finder.py` and `main.py`; keep them in step.

## marketplace_cache.db

SQLite database at `SystemFinderAPI.EDDN_CACHE_PATH` (set from `main.py` after the EDDN listener starts). Key tables: `commodity_prices_data`, `system_powerplay` `(system_name PK, controlling_power, power_state, powers, updated_at)`, `station_metadata`, `system_coords`.

PP2.0 fields from `FSDJump`/`Location` journal events: `ControllingPower`, `PowerplayState`, `Powers`.
