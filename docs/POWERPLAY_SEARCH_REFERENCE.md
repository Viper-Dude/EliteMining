# PowerPlay Search — Ring Finder Reference

Context for the Spansh-backed PowerPlay filtering work in the Hotspots Finder (Ring Finder) tab. Read this before touching `Power`/`Power State` filters or anything in `system_finder_api.py` with `powerplay` in the name.

## Current architecture (as of v5.3.6)

**PowerPlay filtering is Local Database only.** Picking Data Source = Spansh or Both greys out both the Power and Power State combos, resets them to 'Any', and force-hides the PowerPlay results column (`_on_data_source_changed`, `ring_finder.py`). There is no Spansh-sourced hotspot/ring search path for PowerPlay anymore — an earlier `pp_first_mode` design (query Spansh's systems-search for PP-matched systems, then Spansh's `/api/bodies/search` per system for rings) was removed after the per-system ring lookup proved too slow (~24-25s/call server-side on Spansh's end, no way to bound it) and kept timing out. See "Removed: `pp_first_mode`" below for why, in case this is ever revisited.

**Column-visibility force-hide**: `column_visibility_helper.py`'s `ColumnVisibilityMixin` gained a `force_hidden` set + `_cv_set_force_hidden(config_key, column, hidden)`, independent of the user's own saved visibility preference (`visible` dict) — used to hide the PowerPlay column for Spansh/Both without disturbing what the user had manually toggled. The column-visibility right-click menu also skips force-hidden columns (`_cv_show_menu`), not just excluded ones.

### `_apply_powerplay_filter` (`ring_finder.py`) — the only PP filtering path now

Runs as a post-fetch filter on Local Database search results. Two data sources merged:
1. **EDDN cache** (`_batch_get_powerplay`) — always the baseline.
2. **Spansh enrichment** — for the 4 states Spansh's `/api/systems/search` actually supports (`Exploited`, `Fortified`, `Stronghold`, `Unoccupied`; confirmed directly against Spansh's own systems-search UI, which only lists these 4 in its Power State dropdown — `Expansion`/`Contested` aren't in Spansh's index at all, see `LOCAL_ONLY_PP_STATES`). For these 4 states only, `_fetch_spansh_powerplay_systems(reference_system, max_distance, pp_power, pp_state)` is called, and its results are merged into the EDDN cache dict per-system, keeping whichever source has the **newer `updated_at`** (not "EDDN always wins" — that was an earlier wrong assumption, corrected after being challenged).
3. Whatever Spansh entries actually win the merge (cache was blank, or Spansh newer) are **persisted back** to `system_powerplay` via `SystemFinderAPI._store_powerplay_batch()` — added so future searches/other tabs benefit without re-fetching from Spansh every time. Confirmed via live query that Spansh's `updated_at` is a genuine per-system last-data-changed timestamp (not request time) — same system queried twice seconds apart returned identical timestamps, and values were staggered tens of minutes to hours in the past relative to actual UTC "now".
4. `Expansion`/`Contested` (and `Any`) stay EDDN-cache-only — no Spansh call, no persistence.

### 500 LY search-radius override for the 4 Spansh-backed states

`_search_worker` (`ring_finder.py`): when `pp_state_filter in ('Exploited', 'Fortified', 'Stronghold', 'Unoccupied')`, `max_distance` is overridden to `max(dropdown_value, 500.0)` **before** it's passed to both `_get_hotspots` (the actual Local DB ring search) and `_apply_powerplay_filter`'s Spansh enrichment call — so this widens the real search radius, not just the PowerPlay-enrichment lookup radius. `Expansion`/`Contested` (and no PP filter) still use the Max Distance dropdown as-is (capped at 200 LY for Local).

**Important nuance**: even at 500 LY, this only surfaces hotspots already in the user's local database within that radius — it does not turn Spansh into a hotspot/ring data source. A user asking for "all Fortified/Stronghold systems for Power X with Platinum rings, no reference system, no distance cap" is asking for something this doesn't do; that would require reviving something like `pp_first_mode` (see below) or an Inara-based integration.

### Why only these 4 states, and why not extend to Expansion/Contested

Confirmed directly against Spansh's own systems-search web UI (`spansh.co.uk/systems`, Power State dropdown): only **Exploited, Fortified, Stronghold, Unoccupied** are offered. `Expansion` and `Contested` are absent from Spansh's index entirely — not a limitation in our integration, a limitation of Spansh's own dataset. No workaround short of a different data source (e.g. Inara, which would need an API key + new integration — flagged to the user as a future possibility, not started).

### Mining-for-Acquisition context (why Fortified/Stronghold/Unoccupied/Expansion/Contested all matter)

Confirmed via web research (Frontier forums, Inara's PP2.0 guide, EDPowerPlay guide) — PowerPlay 2.0 has 6 system states: Unoccupied, Exploited, Fortified, Stronghold, Expansion, Contested. For mining-for-Acquisition merits specifically: mine commodities in your Power's **Fortified** (20 Ly support bubble) or **Stronghold** (30 Ly) system, then **sell** in a nearby **acquisition-state system** (Unoccupied, Expansion, or Contested — Contested is what Unoccupied/Expansion escalate into once 2+ Powers pass 30% progress) within that same 20/30 Ly radius. This is distinct from Reinforcement/Undermining mining (raising/attacking a system's own tier), which uses different CP-progress mechanics Spansh also exposes (`Power State Reinforcement`/`Power State Undermining` numeric filters) but which are out of scope here — not wired into anything in this app.

The app does not yet compute or surface "nearest acquisition-target system within 20/30 Ly of this Fortified/Stronghold result" — that would be a separate feature (a per-matched-system secondary Spansh query), discussed but not built as of v5.3.6.

## Removed: `pp_first_mode`

Previously, when Data Source was Spansh/Both and a specific Power or Fortified/Stronghold state was selected, `_search_worker` queried Spansh's systems-search for matching systems first, then called `_search_spansh_rings_for_systems` (one `/api/bodies/search` call per matched system, run concurrently via `ThreadPoolExecutor`) to fetch rings for exactly those systems. This avoided the normal distance-paginated ring search's page-size cap, which could silently never reach a Power's territory in dense star regions.

**Removed because**: the per-system `/api/bodies/search` call is inherently slow server-side on Spansh's end (~24-25s per call, confirmed consistent across multiple systems in testing), and started **timing out entirely** (30s timeout hit on all 3 systems in a repro run) rather than just being slow. A retry-with-longer-timeout (45s) was tried first but didn't meaningfully help. Decision: stop using Spansh as a hotspot/ring source altogether; PowerPlay filtering is Local Database only now (see above). If revisited, `_search_spansh_rings_for_systems` was deleted outright (not commented out) — would need to be rewritten from `git log` history, not resurrected from dead code.

### Bug found and fixed while `pp_first_mode` existed: Arissa Lavigny-Duval name mismatch

Still relevant — this fix lives in the surviving enrichment path too. Frontier's own journal/EDDN `ControllingPower` field abbreviates **only this one Power** to `"A. Lavigny-Duval"` (every other Power is written in full). Confirmed via direct API testing that **Spansh's own dataset uses the same abbreviated form**, not the full name our `POWER_FILTER_OPTIONS` dropdown uses.

Fix, in `system_finder_api.py`:
- `_POWER_NAME_ALIASES = {'A. Lavigny-Duval': 'Arissa Lavigny-Duval'}` + `_POWER_NAME_ALIASES_REVERSE` (auto-derived).
- `_normalize_power_name()` applied at every EDDN-cache/Spansh-response read site (`_batch_get_powerplay`, `_get_powerplay_from_cache`, `_fetch_spansh_powerplay_systems`, `_fetch_spansh_powerplay_for_named_systems`, `_convert_spansh_system`'s fallback) — converts abbreviated → full name for display/comparison.
- Reverse alias applied in `_build_spansh_filters` when building the `controlling_power` filter to send **to** Spansh — converts full → abbreviated before the request, since sending "Arissa Lavigny-Duval" to Spansh silently returns zero matches.

**If any other Power is ever found to have a similar quirk, add it to `_POWER_NAME_ALIASES`** — the reverse map and all read sites already handle it generically.

## UI constraints

**Power requires a real State.** Picking a specific Power with State still on "Any" would query Spansh for that Power's *entire* territory with no state filter — confirmed via live test: ~2,890 systems for one power vs. ~435 when narrowed to Fortified. Enforcement (`ring_finder.py`):
- `_on_pp_power_changed`: picking a Power while State is Any auto-sets State to Fortified.
- `_on_pp_state_changed`: setting State back to Any while a Power is selected resets Power to Any too.
- Saved-settings load path also normalizes a stale invalid combination from before this rule existed.

**Data Source constraint.** `_on_data_source_changed`: switching to Spansh/Both resets Power/State to Any, disables both combos (`state="disabled"`), and force-hides the PowerPlay column; switching back to Local re-enables the combos and unhides the column.

Tooltips (`ring_finder.pp_power_tooltip` / `pp_state_tooltip` in both `strings_en.json` and `strings_de.json`) reflect all of the above: Local Database only, requires a specific State, which 4 states get the 500 LY Spansh-backed search vs. which 2 stay EDDN-cache-only at the dropdown's Max Distance. **Note**: there are two separate `pp_power_tooltip`/`pp_state_tooltip` keys in the locale JSON files — one under `ring_finder`, one under `system_finder` (the separate Star Systems tab, which still queries Spansh directly for all states with no Local-DB dependency and doesn't need any of these constraints). Don't conflate them.

## CSV export

Added independently of the PowerPlay work (same release) — right-click on the Ring Finder results (on a row, or empty space when results exist) → "Export All Results to CSV...". Exports all currently loaded rows using the currently visible columns/order (respects column visibility, including the PowerPlay force-hide above). Strips UI-only decoration from cell values before writing (Source column's 🌐/🗄️ emojis become "Spansh"/"Local"/"Spansh, Local"; the `↗` no-data-link arrow and `⭐` favourite star are stripped from other columns). Filename defaults to `ring_finder_results_YYYY-MM-DD_HHMM.csv`. Result dialog (`_show_export_result_dialog`) is a custom theme-aware `tk.Toplevel` (follows the standard dialog checklist — withdraw/icon/build/center/deiconify/topmost/grab/keep-on-top) with an added "Open File" button (cross-platform via `os.startfile`/`open`/`xdg-open`) shown only on success.

## Known deferred/parked items

- **Concurrent Spansh health-check timeout**: the unrelated periodic "Spansh: Online" indicator check (`main.py:_check_sysfinder_spansh_status`) could time out while heavy per-system Spansh traffic was in flight, back when `pp_first_mode` existed. Likely moot now that `pp_first_mode` is removed (Local DB PP filtering only makes 1-2 fast systems-search calls), but not re-verified.
- **Nearest acquisition-target lookup**: surfacing "nearest Unoccupied/Expansion/Contested system within 20/30 Ly of this Fortified/Stronghold result, to sell into" — discussed, not built. Would need a second, small-radius Spansh query per matched system.
- **Galaxy-wide / no-reference-system PowerPlay search**: a user asked for "all Fortified/Stronghold systems for Power X with Platinum rings, no distance limit." Not doable within current architecture without reviving a Spansh-as-ring-source path (the exact thing removed for being too slow) or a wholly different data source. Not started.
- **Reinforcement/Undermining mining support**: Spansh exposes `Power State Reinforcement`/`Power State Undermining` numeric progress filters (0 to 100,000,000 range) for these other PP2.0 activities. Confirmed to exist, not the same as Acquisition mining, not wired into anything — out of scope unless explicitly requested.
- **Exploited/Unoccupied Spansh enrichment**: previously declined 3x in an earlier session ("no direct gameplay reason to prioritize"), later reversed — now enabled alongside Fortified/Stronghold once the user clarified the ask was "extend the existing Local DB + Spansh logic to every state Spansh supports," not tied to a specific mining mechanic.

## Key files

- `app/ring_finder.py` — `_search_worker` (500 LY override), `_apply_powerplay_filter` (Spansh enrichment + persistence), `_on_pp_power_changed`/`_on_pp_state_changed`, `_on_data_source_changed` (grey-out + column force-hide), `_export_results_to_csv`, `_show_export_result_dialog`, `_open_path`.
- `app/system_finder_api.py` — `_fetch_spansh_powerplay_systems`, `_store_powerplay_batch` (new — persists Spansh enrichment to `system_powerplay`), `_fetch_spansh_powerplay_for_named_systems` (unused, kept correct), `_normalize_power_name`, `_POWER_NAME_ALIASES(_REVERSE)`, `_build_spansh_filters`, `LOCAL_ONLY_PP_STATES`.
- `app/column_visibility_helper.py` — `force_hidden` set, `_cv_set_force_hidden()`.
- `app/localization/strings_en.json` / `strings_de.json` — `ring_finder.pp_power_tooltip`/`pp_state_tooltip`, `context_menu.export_results_csv`/`export_results_success`/`export_results_failed`/`export_open_file`.
