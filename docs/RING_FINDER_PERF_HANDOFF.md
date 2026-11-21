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
| 2 | EDSM fallback after display | Opus 5.5, high | Yes | Done 21 Nov 2026, user-tested |
| 3 | PowerPlay backfill: parallel and cached | Opus 5.5, high | Yes | Done 21 Nov 2026, user-tested, committed |
| 4 | Cache the Spansh name lookup | Sonnet 5.5, medium | No | Done 21 Nov 2026, user-tested, committed |
| 5 | Remove shared state from worker threads | Opus 5.5, high | Yes | Done 21 Nov 2026, user-tested, committed |
| 6 | Local range query rewrite | Opus 5.5, high | Yes | Done 21 Nov 2026, user-tested, committed |
| 7 | `_update_results`: prefetch after the limit | Sonnet 5.5, medium | No | Done 21 Nov 2026, awaiting user test |
| 8 | Delete the dead Any Ring mode (changed from: use the paged Spansh path) | Opus 5.5, medium | No | Done 21 Nov 2026, awaiting user test |
| 9 | Cleanup: debug prints, hardcoded text | Sonnet 5.5, low | No | Done 21 Nov 2026, awaiting user test |

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
- Done 21 Nov 2026:
  - The worker no longer calls EDSM. When `_finish_update_results` runs, it calls `_start_edsm_metadata_fill(generation)` (`ring_finder_search.py`). That only checks the rows actually shown, through `_result_row_hotspots` (tree item → hotspot dict, filled in `_insert_row_batch`), closest first. The old cap stays: all systems under 100 rows, otherwise 30.
  - A daemon thread runs the EDSM fill, then reads the filled values back from `hotspot_data` per (system, ring). `_apply_edsm_metadata` sets the LS and Ring Type cells, plus the hotspot dicts, in place. Stale updates are dropped by checking `_results_generation` and `_search_generation`. Rows are not re-sorted.
  - `edsm_integration.py`:
    - `_fetch_edsm_bodies` returns `(data, responded)`.
    - `fill_missing_metadata_for_systems_direct` takes `is_cancelled` (checked before each system) and returns `no_data_systems`: systems EDSM answered for with nothing to fill. Timeouts and errors are not included.
    - The Ring Finder remembers `no_data_systems` for the session in `_edsm_no_data_systems`. The Cargo Monitor's call on a new scan is unaffected.
  - Overlaps Only and RES Only no longer call EDSM inside `_get_all_overlaps_for_search` / `_get_all_res_for_search`. They used to query twice.
  - Bug fixed along the way: the old `_refresh_hotspot_metadata_from_db` matched on `material_name = hotspot['type']`, but `type` holds display text, so filled values only showed on the next search. Both old methods are removed.
  - Tests: `EdsmAfterDisplayTests` (7) plus a worker test in `check_ring_finder_search.py`, 23 OK. 2 EDSM stop/error tests in `check_search_stop.py`, 21 OK.

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
- Done 21 Nov 2026:
  - `system_finder_api.py`: `_query_spansh_powerplay_systems` returns `(systems, answered)`; `_fetch_spansh_powerplay_systems` is now a wrapper returning only the systems. `_fetch_spansh_powerplay_backfill` sends the 4 requests through a 4-thread pool (each checks `is_cancelled` first) and caches complete answers in `_pp_backfill_cache` by `(reference_system.lower(), max_distance)` for `PP_BACKFILL_CACHE_SECS = 300`. Failed or cancelled answers are not cached. The Star Systems tab gets both.
  - `_search_worker` no longer calls Spansh for PowerPlay. It passes `pp_backfill = (reference_system, max_distance)` to `_complete_search`, which stores it in `_pp_backfill_request` after the generation check. `_finish_update_results` then calls `_start_pp_backfill(generation)` next to the EDSM fill. A daemon thread fetches the backfill, keeps the shown systems where `_spansh_pp_should_replace_cache` says Spansh is better, saves them with `_store_powerplay_batch`, and `_apply_pp_backfill` sets only the PowerPlay cells, with the same generation checks as step 2.
  - The PowerPlay cell text moved into `RingFinder._powerplay_display(pp_entry, hotspot)` (`ring_finder.py`), used by `_update_results` and the in-place update.
  - `use_spansh_pp` is now `data_source == 'database' and spansh_pp_var`: Spansh/Both searches hide the PowerPlay column, so they no longer send the 4 requests.
  - Only the shown rows are backfilled now (before: every row before the Max Results cut). Like the EDSM fill, the backfill also runs after Stop shows partial results.
  - Live, real function: Sol 50 LY sequential 7.9 s, parallel 2.3 s, same 998 systems; cached repeat 0 s. Colonia 100 LY: 4.0 s to 2.7 s (0 systems).
  - Tests: `PowerPlayAfterDisplayTests` (5) plus a worker test in `check_ring_finder_search.py`, 29 OK. `PowerPlayBackfillTests` (5) in `check_search_stop.py`, 26 OK. `check_star_systems.py` 19 OK.

### 4 — Cache the Spansh name lookup

- `_resolve_spansh_system_name` (about line 3323) adds a request to `systems/field_values/system_names` on every Spansh search.
- It has a 30 s timeout, doesn't go through `tracked_request`, and Stop can't interrupt it.
- Fix: cache by lowercase name for the session, skip the call when the name came from the journal (exact case already known), use `tracked_request`, a shorter timeout and an `is_cancelled` check.
- Model: Sonnet 5.5, medium effort.
- Done 21 Nov 2026, in `ring_finder_search.py`:
  - A name matching (case-insensitively) `last_monitored_system`, `prospector_panel.last_system` or `main_app.current_system` returns the journal spelling with no request.
  - Spansh answers (status 200, including "no match") are cached in `_spansh_name_cache` by lowercase name for the session. Errors and non-200 answers are not cached.
  - The request goes through `tracked_request` with a 10 s timeout. `_search_spansh_with_filters` passes `is_cancelled`, and no request is sent once Stop is pressed.
  - Tests: `SpanshNameLookupTests` (4) in `check_ring_finder_search.py`, 33 OK. `check_search_stop.py` 26 OK.

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
- Done 21 Nov 2026:
  - `search_hotspots` passes `force_database` and the reused Spansh rows (`cached_spansh`, taken when `_use_cached_spansh` is set, and the flag is cleared right away) to the worker. Before, the flag stayed set after a Local search and a later Spansh search reused old rows.
  - `_search_worker` writes nothing on self. `_apply_powerplay_filter` returns `(rows, enrichment)`. `_get_hotspots` takes `force_database`, `reference_coords`, `cached_spansh` and `spansh_fetched` (a dict that receives fresh Spansh rows). `_complete_search` stores `_spansh_pp_enrichment`, `current_system_coords` and `_cached_spansh_results` only after its generation check.
  - `reference_coords` is passed down to `_search_user_database_first` / `_get_user_database_hotspots`. Find Best Mining System passes none, so it keeps the old `_last_search_key` fallback. That's why `search_hotspots` still resets `current_system_coords` on the UI thread at the start.
  - `_load_systems_cache` no longer replaces `systems_data` (it was only ever set to `{}`).
  - Tests: `SearchStateTests` (4) in `check_ring_finder_search.py`, 37 OK. `check_search_stop.py` 26 OK, `check_star_systems.py` 19 OK.

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
- Done 21 Nov 2026, in `ring_finder_search.py`:
  - `_find_systems_in_range` is replaced by `_local_systems_in_range(cursor, ...)`. It starts from `hotspot_data`, not the galaxy DB:
    - systems whose rows have coordinates are filtered by sphere distance in Python (one scan of the distinct system coordinates);
    - systems with rows missing coordinates get one batched, case-insensitive lookup through `_get_galaxy_coords_batch`, then `visited_systems`, then the same system's other rows;
    - the reference system falls back to the reference coordinates (distance 0) instead of EDSM.
  - The found coordinates go into `coord_cache`, so the per-row loop saves them with the existing `UPDATE` and makes no per-row galaxy or EDSM lookups on this path.
  - Removed: the `LIMIT 50000`, the 5,000-system cap and `max_process_limit = 10000`. Favourites Only skips the range lookup. The name search used when there are no reference coordinates is unchanged.
  - Specific-mineral searches load every ring's other minerals in one batched query before the loop.
  - Comparison on copies of the user's DBs, old vs new, for Sol, Colonia and HIP 21991 at 50–500 LY (All Minerals, Platinum, Icy LTD, Painite):
    - identical rows and order wherever the old path wasn't capped;
    - 500 LY All Minerals: old 10,000 rows (cap), new about 15,500;
    - 500 LY Painite: 4–5 extra rings without stored coordinates, previously lost to the galaxy limit.
    - Time: 200 LY 1.6 s to 0.18 s, 500 LY 5.0 s to 0.34 s, 500 LY Painite 4.6 s to 0.23 s.
  - Tests: `LocalRangeQueryTests` (7) in `check_ring_finder_search.py`, 44 OK. `check_search_stop.py` 26 OK, `check_star_systems.py` 19 OK.

### 7 — `_update_results`: prefetch after the limit

- `_update_results` (about lines 5566–5589) runs on the UI thread. Before the Max Results cut, it runs about 9 bulk DB queries and reads the whole reports CSV (`get_last_mined_lookup`) for every system in the results.
- Visit counts and favourites must stay before the cut, because they drive the Unvisited Only and Favourites Only filters.
- Fetch these after `_limit_results_by_unique_rings` instead: comments, density, last mined (CSV and overrides), overlaps, RES, PowerPlay, and the existing-ring check.
- The existing test `test_display_filters_before_limit_and_visit_lookup_only_once` must still pass.
- Model: Sonnet 5.5, medium effort.
- Done 21 Nov 2026, in `ring_finder.py` `_update_results`:
  - Comments, density, last-mined CSV lookup and last-mined overrides are now fetched after `_limit_results_by_unique_rings`, for the shown systems only. Visit counts and favourites stay before the cut. Overlaps, RES, PowerPlay and the existing-ring check were already after it.
  - `_last_mined_lookup` (used by the right-click and edit-ring dialog) now covers only the shown systems, which are the only rows those dialogs can open.
  - Tests: the existing limit test now also checks that comments and density are fetched for the one shown system only. `check_ring_finder_search.py` 44 OK, `check_search_stop.py` 26 OK.

### 8 — Any Ring mode uses the paged Spansh path

- `_search_spansh_rings` (about line 3677) sends one unfiltered request for 5,000 bodies with a 60 s timeout, and Stop can't interrupt it.
- Its comment says filters break the API, but `_search_spansh_with_filters` uses the same `rings` type filter without problems.
- Fix: route Any Ring mode through `_search_spansh_with_filters(ring_type_only=True)`. Keep the 1,000 LY radius and the "Spansh only" behaviour.
- Also keep Spansh's system coordinates, so the Sol column doesn't need a galaxy lookup on the UI thread for every row.
- Compare results for 2–3 systems before and after.
- Model: Opus 5.5, medium effort.
- Changed 21 Nov 2026 (user decision): the Any Ring checkbox was hidden ("feature disabled") and nothing set `any_ring_var`, so the whole path was dead. Ring Search (Spansh) already uses `_search_spansh_with_filters(ring_type_only=True)` with the step 1 paging, Stop checks and Spansh coordinates.
- Done: removed `_search_spansh_rings`, `_convert_spansh_to_hotspots`, the `any_ring_mode` worker parameter and branch, the 1,000 LY override, the hidden checkbox, `_on_any_ring_changed` and the `any_ring_var` check in `_update_favourites_only_controls` (about 330 lines). Checks: ring_finder_search 44, search_stop 26, star_systems 19, all OK.
- Left for step 9: the now-unused string keys `ring_finder.any_ring`, `any_ring_tooltip`, `any_ring_mode`, `spansh_timeout` and `spansh_error` in both string files.

### 9 — Cleanup

- Remove the stack-trace print in `search_hotspots` (about line 2817), the per-ring prints in the Spansh loops (`[RING SEARCH] Found`, `[SPANSH DB LOOKUP] Formatted`), and the `Delkar` debug block (about line 4149).
- Move hardcoded English status text to `t()` with German translations:
  - "Querying Spansh API..."
  - "Fetching Spansh data... page x/y"
  - "Spansh search timed out"
  - "Spansh API error"
  - the `status_label` text at about line 5153
- Remove the unused string keys left by step 8 (listed there) from `strings_en.json` and `strings_de.json`.
- Done 21 Nov 2026: removed the stack-trace print, the `[RING SEARCH] Found` print and the Delkar debug block (the `[SPANSH DB LOOKUP]` print went with step 8). The four Spansh status messages now use `t()`: new keys `spansh_querying` and `spansh_fetching_page`, and the existing `spansh_timeout` / `spansh_error` (so the old "try reducing distance" wording now shows). The dead `status_label` update (no such attribute on the finder, error swallowed) was removed. The unused `any_ring*` keys were removed from both string files. The remaining `traceback.print_exc()` calls in error handlers stay. Checks: ring_finder_search 44, search_stop 26, OK.
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
