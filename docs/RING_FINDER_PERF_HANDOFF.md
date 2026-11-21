# Ring Finder Search Performance — Handoff

Updated: 21 November 2026

Start a new chat with: "Read docs/RING_FINDER_PERF_HANDOFF.md and continue with the next step."

## Goal

Make Ring Finder searches (Local, Spansh, Both, Ring Search, Any Ring) show results faster and stop dropping rings silently. Keep the visible behaviour the same unless a step below says otherwise. This is a set of targeted fixes, not a rewrite.

## Findings in short

- The local database queries are not the bottleneck. Measured read-only on the user's DBs around Sol: 0.05–0.3 s at 50–200 LY (18,724 rings in total, 8,906 systems).
- The time is spent in network steps that run one after another before any row appears. Each has its own wait or timeout:
  1. Spansh name lookup (30 s timeout)
  2. Spansh body pages (1.5 s gap between pages, up to 10 or 30 pages)
  3. PowerPlay backfill (4 Spansh requests, 10 s timeout each)
  4. EDSM metadata fallback (up to 30 systems, 0.5 s gap and 15 s timeout each)
- The Spansh and EDSM timings were not measured live; they come from the waits and timeouts in the code.
- Two caps can silently drop rings at large radii (see step 6).

## Rules for this work

- One step per commit. Step 0 only moves code; never move and change behaviour in the same commit (see [MAIN_SPLIT_HANDOFF.md](MAIN_SPLIT_HANDOFF.md)).
- `ring_finder.py` is CRLF. Patch with a script outside the repo: normalize to `\n`, assert one match each, restore CRLF, then `py_compile`.
- Another chat may be editing the checkout. Re-read the target range right before patching.
- After each step, run `py_compile`, then `scripts\check_ring_finder_search.py` and `scripts\check_search_stop.py`. Add tests to those scripts for each behaviour change. The user restarts the app and tests it.
- Start each step by giving the user a one-line model and effort suggestion from the table below, and say whether Plan mode helps.
- Stop must keep working at every step. Each new network call must check `is_cancelled` before it is sent.
- New UI text goes in `strings_en.json` and `strings_de.json` via `t()`.
- Shared callers: `_get_hotspots()` is also used by Find Best Mining System (`_reverse_search_worker`, about line 8168). `_fill_missing_metadata_edsm()` is also used by Overlaps Only and RES Only. `_fetch_spansh_powerplay_backfill()` is also used by the Star Systems tab (`system_finder_api.py`, about line 611). Check each of them when a step touches these functions.

## Progress

| Step | What | Model, effort | Plan mode | Status |
|---|---|---|---|---|
| 0a | Delete unused methods | Sonnet 5.5, low | No | Done, user-tested, committed `1ce9b69` |
| 0b | Move search code into its own module | Opus 5.5, high | No | Done 21 Nov 2026, user-tested, committed |
| 1 | Stop Spansh paging at the result limit, plus the D2 test | Opus 5.5, medium | No | Done 21 Nov 2026, user-tested, committed |
| 2 | EDSM fallback after display | Opus 5.5, high | Yes | Next |
| 3 | PowerPlay backfill: parallel and cached | Opus 5.5, high | Yes | Not started |
| 4 | Cache the Spansh name lookup | Sonnet 5.5, medium | No | Not started |
| 5 | Remove shared state from worker threads | Opus 5.5, high | Yes | Not started |
| 6 | Local range query rewrite | Opus 5.5, high | Yes | Not started |
| 7 | `_update_results`: prefetch after the limit | Sonnet 5.5, medium | No | Not started |
| 8 | Any Ring mode uses the paged Spansh path | Opus 5.5, medium | No | Not started |
| 9 | Cleanup: debug prints, hardcoded text | Sonnet 5.5, low | No | Not started |

Recommended order: 0a, 0b, 1, 2, 3, 4, 5, 6, 7, 8, 9. Steps 1–3 give the biggest time savings.

## Decisions (user, 21 Nov 2026)

- **D1 — yes:** rows appear right away, and the PowerPlay, ring type and LS columns fill in a moment later (steps 2 and 3).
- **D2 — yes, as an experiment in step 1:** send `ring_signals` with every mineral name for "All Minerals". Keep it only if live test counts match the current results.
- **D3 — deferred:** drop the duplicate `hotspot_data` indexes only when `user_database.py` is being changed anyway.

## Steps

### 0a — Delete unused methods (done)

- `_get_nearby_systems` (about line 4439), `_get_edsm_bodies_with_rings` (about 4298) and `_get_fallback_hotspots` (about 4849) have no callers in `app/` or `scripts/`. That's about 600 lines, including more EDSM request loops.
- Done 21 Nov 2026: removed with a patch script (620 lines). `py_compile`, `check_ring_finder_search.py` (11 OK) and `check_search_stop.py` (19 OK) passed. The dead `_get_fallback_hotspots` also called a nonexistent `_get_system_coords`.
- Model: Sonnet 5.5, low effort.

### 0b — Move search code into `app/ring_finder_search.py`

- Create `class RingFinderSearchMixin` holding the search pipeline unchanged:
  - `search_hotspots`, `_search_worker`, `_run_search_callback`, `_complete_search`
  - `_fill_missing_metadata_edsm`, `_refresh_hotspot_metadata_from_db`, `_limit_results_by_unique_rings`
  - `_resolve_spansh_system_name`, `_search_spansh_with_filters`, `_search_spansh_rings`, `_convert_spansh_to_hotspots`
  - `_apply_powerplay_filter`, `_get_hotspots`, `_search_user_database_first`, `_get_user_database_hotspots`
  - `_calculate_distance`, `_get_system_coords_from_galaxy_db`, `_find_systems_in_range`, `_get_system_coords_from_edsm`
  - Optionally `_get_all_overlaps_for_search` and `_get_all_res_for_search`
- Add the mixin to `RingFinder`'s bases, ahead of `ColumnVisibilityMixin`.
- Run a scope-aware undefined-name scan (`symtable`) of the new module. Watch for `t`, `log`, `tracked_request`, `translate_ring_type`, `translate_reserve_level`, `requests`, `math`, `threading` and the `typing` names.
- Check scripts that read `ring_finder.py` source must point to the new file where needed.
- Model: Opus 5.5, high effort (the move is large, and a missed import crashes at runtime).
- Done 21 Nov 2026:
  - Moved the contiguous block from `search_hotspots` up to `_update_results` (2,133 lines, 23 methods). Besides the methods listed above, that block also holds `_is_valid_mining_material`, `_material_matches`, `_determine_ring_type_from_material` and `_clean_ring_name`. Overlaps and RES search stayed in `ring_finder.py`.
  - `translate_reserve_level` and `translate_ring_type` moved too, to avoid a circular import. `ring_finder.py` re-imports them, so `from ring_finder import translate_ring_type` (`prospector_panel.py`, `mining_card_mixin.py`) still works.
  - The new module uses `logging.getLogger('ring_finder')`, so log lines keep the same logger name.
  - Verified: the moved text is byte-identical to `1ce9b69`, and the rest of `ring_finder.py` is unchanged apart from the import and class bases. The `symtable` scan found nothing new (only `__file__`, same as before). There are no method name clashes in the MRO.
  - `check_ring_finder_search.py` now builds `Finder` from both files, and `check_search_stop.py`'s syntax test includes the new file. Checks passed: ring_finder_search 11, search_stop 19, bookmarks 34, star_systems 19, visited_systems 6, distance_calculator 17.
- Line numbers in steps 1–9 below still refer to the old `ring_finder.py`. Search by method name; most of them now live in `ring_finder_search.py`.

### 1 — Stop Spansh paging at the result limit

- In `_search_spansh_with_filters` (about line 3366), `max_results` is never used.
- The page loop runs up to 10 pages of 500 bodies (All Minerals, All ring types) or 30 pages (Ring Search), with 1.5 s between pages. That's at least ~15 s or ~45 s.
- Fix: count unique matching rings while converting each page, and stop once the count reaches `max_results`. Spansh sorts by distance, so the closest rings are already in hand.
  - Ring Search passes `spansh_limit` (capped at 150), so it benefits too.
  - Keep the `last_body_distance >= max_distance` stop and the `is_cancelled` check.
- Find Best Mining System calls `_get_hotspots(..., max_results=None)`. Decide whether it needs a limit, and don't change its results without telling the user.
- D2 experiment: for "All Minerals", send `ring_signals` with every valid mineral name (`_is_valid_mining_material` list) and `count: [1, 9999]`. Compare ring counts against the current method for 2–3 reference systems before keeping it.
- Tests: paging stops at the limit, Stop still works between pages, and the limit counts rings, not rows.
- Model: Opus 5.5, medium effort.
- Done 21 Nov 2026, all in `ring_finder_search.py`:
  - The per-body conversion moved into `_spansh_bodies_to_hotspots()` and now runs per page.
  - Paging stops once `max_results` rings are collected, or on a short page.
  - The early stop is off (`spansh_stop_at_limit=False`) when a filter that runs after the fetch could drop rows: Min Hotspots > 1, Unvisited Only, a Reserve filter, or a Power/PowerPlay State filter. The flag is computed in `search_hotspots` and passed through `_search_worker` and `_get_hotspots`.
- D2 kept. "All Minerals" sends `ring_signals` with `SPANSH_HOTSPOT_SIGNALS`, the 13 names Spansh actually uses. Live test, closest 150 rings:
  - Sol 50 LY: identical. The old method used 10 pages (20.6 s) and only reached 33 LY. The filtered one covered the full 50 LY.
  - Colonia 100 LY: identical. Old: 10 pages, 21.9 s, 21 LY.
  - The real function, live, for Sol 50 LY with limit 150: 1 request, 0.7 s.
- Bug found and fixed: Spansh spells it "Void Opal". A Spansh "Void Opals" search returned 0 results, and "All Minerals" dropped Void Opal hotspots, because `_is_valid_mining_material` doesn't know the singular. `SPANSH_SIGNAL_NAMES` and `APP_SIGNAL_NAMES` now map the name both ways, so saved rows stay "Void Opals". Any Ring mode (`_search_spansh_rings`) still shows the raw Spansh name; step 8 replaces that path.
- Tests: 5 new in `check_ring_finder_search.py` (`SpanshPagingTests`); 16 OK. `check_search_stop` 19 OK.

### 2 — EDSM fallback after display

- `_fill_missing_metadata_edsm` (about line 3159) runs in `_search_worker` before `_complete_search`. It checks up to 30 systems one at a time, with `REQUEST_DELAY = 0.5` and `TIMEOUT = 15` in `edsm_integration.py`.
- Stop doesn't interrupt it, and it doesn't remember failures, so systems EDSM can't fill are queried again on every search (14 such systems in the user's DB).
- It also runs on the full result set, before the Max Results cut in `_update_results`.
- Fix:
  - Run it only for the rows actually shown (after `_limit_results_by_unique_rings`).
  - Keep a per-session set of systems that returned no data.
  - Pass `is_cancelled`, and check it between systems in `fill_missing_metadata_for_systems_direct`.
- With D1 = yes: start it on a background thread after the rows are inserted, then update the affected rows in place, checking `_results_generation` so stale updates are dropped.
- Overlaps Only and RES Only (lines 2491 and 2673) call it too; give them the same treatment.
- Model: Opus 5.5, high effort (threading plus in-place row updates).

### 3 — PowerPlay backfill: parallel and cached

- When no Power or PowerPlay State filter is set, `_search_worker` (about lines 3077–3096) calls `SystemFinderAPI._fetch_spansh_powerplay_backfill`.
- That makes 4 Spansh requests in a row (Exploited, Fortified, Stronghold, Unoccupied), each with `ENRICHMENT_TIMEOUT = 10`, before any row shows.
- It runs for Spansh and Both searches, and for Local searches when "Spansh PP" is ticked.
- Fix in `system_finder_api.py`:
  - Run the 4 requests in parallel (a small thread pool, each checking `is_cancelled`).
  - Cache the merged result by `(reference_system.lower(), max_distance)` for a few minutes, so Auto Search and repeat searches skip it.
  - The Star Systems tab shares this function, so check it too.
- With D1 = yes: run the backfill after display and refresh only the PowerPlay column.
- Model: Opus 5.5, high effort.

### 4 — Cache the Spansh name lookup

- `_resolve_spansh_system_name` (about line 3323) adds a request to `systems/field_values/system_names` on every Spansh search.
- It has a 30 s timeout, doesn't go through `tracked_request`, and Stop can't interrupt it.
- Fix: cache by lowercase name for the session, skip the call when the name came from the journal (exact case already known), use `tracked_request`, a shorter timeout and an `is_cancelled` check.
- Model: Sonnet 5.5, medium effort.

### 5 — Remove shared state from worker threads

- Worker threads write `self._spansh_pp_enrichment`, `self._cached_spansh_results`, `self.current_system_coords` and `self._force_database`.
  - An older search that has passed its last generation check can overwrite `_spansh_pp_enrichment` for a newer one, which puts wrong data in the PowerPlay column.
  - `_force_database` is set on the UI thread and cleared in the worker, so it can carry over into the next search.
- Fix:
  - Pass `force_database` as a worker argument.
  - Return the enrichment and the Spansh rows with the results to `_complete_search`, and only store them there, after the generation check.
- Also: at startup, `_load_systems_cache` sets `systems_data = {}` from the preload thread and can wipe coordinates cached from an FSDJump. Merge instead of replacing.
- Tests: an old search finishing late cannot change the PowerPlay data of a newer search.
- Model: Opus 5.5, high effort.

### 6 — Local range query rewrite

Current problems in `_get_user_database_hotspots` and `_find_systems_in_range`:

- The galaxy query (about line 5429) has `LIMIT 50000` with no `ORDER BY`. Around the bubble, the 200 LY box holds 54,189 systems and the 500 LY box (used by PowerPlay-state searches) holds 83,460, so arbitrary systems are dropped.
  - Rings that have coordinates are added back by the `hotspot_data` box query, so only rows without coordinates are lost (4,976 rows have none). Measured loss: 2 rings at 200 LY.
- The query doesn't use the existing R-tree `systems_spatial`; it scans the whole table (about 0.1 s).
- About 37,000 systems with no hotspot rows go through the batched `IN` queries at 200 LY. They can never match.
- `max_process_limit = 10000` (about line 5162) cuts rows before the distance sort and before the PowerPlay filter. A 500 LY "All Minerals" search has about 15,754 rings in the box.

Fix:

- Query `hotspot_data` directly by bounding box on its own coordinates, then filter by sphere distance. Measured 0.06 s against 0.15 s, with the same rings.
- Backfill missing coordinates once, from `galaxy_systems.db` in one batched lookup, and keep the existing `UPDATE` that saves them.
- Sort by distance before any cap, or remove the cap.
- Keep these paths working: Favourites Only (no radius), the reference system itself (distance 0), and rows without coordinates when there are no reference coordinates.
- For specific-material searches, replace the per-row query for the other minerals on the same ring (about line 5267) with one batched query.
- Model: Opus 5.5, high effort (local DB read path, many edge cases).

### 7 — `_update_results`: prefetch after the limit

- `_update_results` (about lines 5566–5589) runs on the UI thread. Before the Max Results cut, it runs about 9 bulk DB queries and reads the whole reports CSV (`get_last_mined_lookup`) for every system in the results.
- Visit counts and favourites must stay before the cut, because they drive the Unvisited Only and Favourites Only filters.
- Fetch these after `_limit_results_by_unique_rings` instead: comments, density, last mined (CSV and overrides), overlaps, RES, PowerPlay, and the existing-ring check.
- The existing test `test_display_filters_before_limit_and_visit_lookup_only_once` must still pass.
- Model: Sonnet 5.5, medium effort.

### 8 — Any Ring mode uses the paged Spansh path

- `_search_spansh_rings` (about line 3677) sends one unfiltered request for 5,000 bodies with a 60 s timeout, and Stop can't interrupt it.
- Its comment says filters break the API, but `_search_spansh_with_filters` uses the same `rings` type filter without problems.
- Fix: route Any Ring mode through `_search_spansh_with_filters(ring_type_only=True)`. Keep the 1,000 LY radius and the "Spansh only" behaviour.
- Also keep Spansh's system coordinates, so the Sol column doesn't need a galaxy lookup on the UI thread for every row.
- Compare results for 2–3 systems before and after.
- Model: Opus 5.5, medium effort.

### 9 — Cleanup

- Remove the stack-trace print in `search_hotspots` (about line 2817), the per-ring prints in the Spansh loops (`[RING SEARCH] Found`, `[SPANSH DB LOOKUP] Formatted`), and the `Delkar` debug block (about line 4149).
- Move hardcoded English status text to `t()` with German translations:
  - "Querying Spansh API..."
  - "Fetching Spansh data... page x/y"
  - "Spansh search timed out"
  - "Spansh API error"
  - the `status_label` text at about line 5153
- D3 (deferred): in `user_database.py`, `idx_system_name` duplicates `idx_hotspot_system` and `idx_body_name` duplicates `idx_hotspot_body`. Both system indexes are also covered by `idx_hotspot_unique_key`.
- Model: Sonnet 5.5, low effort.

## Measurements (21 Nov 2026, user's DBs, read-only, reference Sol)

| Radius | Current local path | Direct `hotspot_data` box query | Rings | Galaxy query truncated |
|---|---|---|---|---|
| 50 LY | 0.27 s | 0.08 s | 33 | No |
| 100 LY | 0.09 s | 0.04 s | 451 | No |
| 200 LY | 0.15 s | 0.06 s | 6,045 vs 6,043 | Yes |

Other measurements:

- A per-ring `get_body_hotspots` call (new connection each time) takes about 0.5 ms.
- A per-row galaxy coordinate lookup takes about 0.5 ms.

Neither is a priority.

## Not verified

- No live Spansh or EDSM requests were made. The network times are estimates from the waits and timeouts in the code.
- Nothing in the UI was tested. The user tests each step after restarting the app.
