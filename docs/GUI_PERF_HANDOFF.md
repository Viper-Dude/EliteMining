# GUI Responsiveness — Handoff

Updated: 21 November 2026

Start a new chat with: "Read docs/GUI_PERF_HANDOFF.md and continue with the next step."

## Goal

Remove the remaining short UI freezes (jumps, ring scans, startup, Commodity Market results) without changing what the player sees. This is a set of small targeted fixes, not a rewrite. Ring Finder search speed was handled separately in [RING_FINDER_PERF_HANDOFF.md](RING_FINDER_PERF_HANDOFF.md); nothing here changes that pipeline.

## Findings in short

- Idle cost is low. Every recurring UI-thread timer together uses well under 1% of the UI thread. Measured: game window lookup 0.4 ms, `load_theme()` at most 0.14 ms, Variables watcher (51 files every 500 ms) and command file check (every 250 ms) negligible.
- Already in good shape, leave alone: Ring Finder batched inserts and generation checks, threaded saves, cargo sidebar redraws only on change, charts redraw only while visible, Modern recolor once per tab, CargoMonitor caches the journal folder listing for 5 s. A code scan found no network calls on the UI thread in the main UI modules.
- The freezes come from short bursts of synchronous work on the UI thread, partly against a database that the EDDN thread locks many times a second.

## Confirmed issues

| # | Issue | Where | Evidence |
|---|---|---|---|
| C1 | `marketplace_cache.db` (65 MB, 162k price rows) uses the rollback journal (`journal_mode=delete`). The EDDN thread opens a connection and commits per message; each commit holds the lock 7 ms median, 26 ms max (timed on a copy). The UI thread writes to it on every FSDJump and reads it when Commodity Market results are shown, so it can wait on that lock. | `eddn_listener.py:89` (init), `cargo_monitor.py:1681` and `:1688` (FSDJump upserts), `system_finder_api.py` `_batch_get_powerplay` (called from `main.py` `_populate_marketplace_results`) | `PRAGMA journal_mode`, timed commits |
| C2 | Two 2 s UI-thread timers each list the journal folder (2,673 files on the user's PC, grows every session), read the last 5 KB of the newest journal, and both write `jumpsleft`. About 3.5 ms each with a warm cache; spikes with a cold cache or antivirus. The CargoMonitor background thread already knows the newest journal. `va_variables.write_variable` writes with plain `open()`, not `_atomic_write_text()`. | `main.py` `_poll_route_status` (~6454), `va_variables.py` `poll_route_status` (128) and `write_variable` (~30) | Timing script |
| C3 | All live journal events run on the UI thread, including their DB writes: FSDJump visit + PowerPlay + system info, `update_ring_metadata` per ring on Scan, hotspot writes on SAASignalsFound. Likely cause of hitches on a jump or FSS burst. Not measured yet. | `cargo_monitor.py` `_dispatch_journal_events` (1292) → `_process_journal_event_impl` | Code inspection |
| C4 | matplotlib (about 0.33 s warm, more cold) is imported when `main.py` imports `prospector_panel`, before the splash appears. | `prospector_panel.py:110` → `mining_charts.py:22` | `-X importtime` |
| C6 | The cargo overlay rewrites its 9 canvas text items and re-sets alpha every 2 s even when the text is unchanged. | `overlays.py` `CargoTextOverlay.update_cargo` (765–768) | Code inspection |
| C8 | The Reports table mouse-move handler sets the cursor on every move, even when unchanged. | `prospector_panel.py` `_handle_mouse_motion` (~11289) | Code inspection |

Dropped after review:

- C5 (Ring Finder count queries, about 90 ms at startup and after saves, `ring_finder.py` `_update_database_info` / `_get_available_materials`): the main-split rule would need a module move first. Not worth it.
- C7 (`mining_charts.py` resize debounce uses `hasattr`, so it fires only once): harmless, because `FigureCanvasTkAgg` packed with `fill="both", expand=True` resizes itself. Do not "fix" it; making it fire would double the redraws. Removing it is optional cleanup.

## Rules for this work

- One step per commit. Never move code and change behaviour in the same commit (see [MAIN_SPLIT_HANDOFF.md](MAIN_SPLIT_HANDOFF.md)).
- Most `app/` files are CRLF. Patch with a script outside the repo: normalize to `\n`, assert one match each, restore CRLF, then `py_compile`.
- Another chat may be editing the checkout. Re-read the target range right before patching.
- Start each step by giving the user the one-line model and effort suggestion from the table, and say whether Plan mode helps.
- Read [ARCHITECTURE_NOTES.md](ARCHITECTURE_NOTES.md) before steps 1 and 3, [VOICEATTACK_RULES.md](VOICEATTACK_RULES.md) before step 2, [UI_RULES.md](UI_RULES.md) before step 5, and [BUILD_RELEASE.md](BUILD_RELEASE.md) before step 4.
- Shared code to keep working:
  - `marketplace_cache.db` is also written by the Ring Finder PowerPlay backfill thread (`_store_powerplay_batch`) and read by Commodity Market, Star Systems and `system_info_cache.py`.
  - `_upsert_pp_from_event` is also called from journal catch-up (`journal_parser.py:1183`, `:1374`), which already runs in the background. Change only the live call sites, not the function.
  - The Ring Finder auto-refresh after a ring scan (`cargo_monitor.py` ~437–458) and auto-search on a jump expect the scan's `hotspot_data` rows to be stored already. The step 2 EDSM fill reads `hotspot_data` back from its own thread.
  - Ring Finder step 5 removed shared state from worker threads; don't bring it back.
- The user restarts the app and tests. Report what was and wasn't verified.

## Progress

| Step | What | Model, effort | Plan mode | Status |
|---|---|---|---|---|
| 0 | Temporary UI stall logger (dev only) and baseline | Sonnet 5.5, low | No | Logger committed; baseline test pending |
| 1 | `marketplace_cache.db` to WAL | Opus 5.5, high | No | Done (checks pass; in-game test at the end) |
| 2 | One route timer, no folder listing, atomic `jumpsleft` | Sonnet 5.5, medium | No | Done (`check_route_status.py` 12/12). Side effect: the old second timer rewrote the FSDTarget count after arrival, so the arrival 0 now sticks |
| 3a | FSDJump cache upserts off the UI thread | Opus 5.5, high | Yes | Done: one worker (`_queue_cache_upserts`), also used for CarrierJump and Location (same code); `check_journal_reading.py` 47/47 |
| 3b | Scan / SAA writes off the UI thread (only if step 0 shows stalls) | Opus 5.5, high | Yes | Not started |
| 4 | Import matplotlib after the splash | Sonnet 5.5, medium | No | Not started |
| 5 | Skip unchanged cargo overlay redraw and cursor changes | Sonnet 5.5, low | No | Not started |
| 6 | Remove the stall logger, re-measure, final notes | Sonnet 5.5, low | No | Not started |

Recommended order: 0, 1, 2, 3a, (3b), 4, 5, 6. Steps 1 and 3a give the biggest gain.

## Decisions (user, 21 Nov 2026)

- **D1 — yes:** in step 2, switch `va_variables.write_variable` to `_atomic_write_text()` (AGENTS.md requires it for every `Variables/*.txt` value). Values stay exactly the same.
- **D2 — yes:** do step 3b only if the step 0 log shows UI stalls over about 50 ms on a ring scan or FSS burst.
- **D3 (user):** in-game testing is done once, when the whole task is finished. Ask for an earlier test only when a decision depends on it. So the step 0 log will be taken with WAL (step 1) already in place, and there are no pre-WAL numbers. Before deciding 3b, ask for one short ring-scan/FSS log.

## Steps

### 0 — Temporary UI stall logger and baseline

- Add a dev-only heartbeat: `after(100)` that logs `[UI-STALL]` with the delay when it runs more than 50 ms late, plus the name of the last journal event batch delivered (set in `_deliver_journal_events`). Enable it only when not frozen (`not getattr(sys, 'frozen', False)`), so it never ships.
- User test: start the app, wait for the splash to close, jump 2–3 times, honk and FSS a ringed system, open Commodity Market and show results. Send `~\EliteMining.log`.
- Record the stalls per action in the "Measurements" section below. This decides D2 and gives the before numbers for step 6.
- Commit this, so step 6 can remove it cleanly.

### 1 — `marketplace_cache.db` to WAL

- In `EDDNListener._init_database` (`eddn_listener.py:89`), run `PRAGMA journal_mode=WAL` once. The mode is stored in the file, so every later connection uses it.
- Python's `sqlite3.connect` already has a 5 s busy timeout by default, so no `busy_timeout` change is needed. WAL removes reader/writer blocking; writers still take turns, which matters because the PowerPlay backfill thread also writes.
- Checked 21 Nov 2026: the installer, `create_release.py` and the Settings backup don't ship or copy `marketplace_cache.db`, and nothing deletes or moves it. WAL adds `-wal` and `-shm` files next to it; nothing needs to handle them.
- `local_database.py:411` and `user_database.py:111` already use WAL (same pattern).
- Failure path: if switching fails (database locked at startup), log it and carry on in the current mode; never block startup.
- Tests: add to `scripts\check_marketplace_indexes.py` (or a new `check_marketplace_cache.py`): the mode is WAL after init on a temp DB, and a reader succeeds while another connection holds an open write transaction.

### 2 — One route timer, no folder listing

- Keep `main._poll_route_status` as the only route timer; remove the `_poll_va_variables` timer that calls `va_variables.poll_route_status`.
  - Move its one extra check into `main._poll_route_status`: NavRoute.json with an empty `Route` sets 0 jumps. Read NavRoute.json only when its mtime changes (main already tracks `_navroute_mtime`).
  - Keep the arrival check (current system = final route system sets 0) and the event priority order exactly as they are.
- Use `self.cargo_monitor.last_journal_file` for the newest journal. Fall back to the old folder listing only when it is `None` or missing (startup, journal folder change).
- D1: `write_variable` uses `_atomic_write_text()` from `config.py` (no import from `main.py`, to avoid a circular import).
- `jumpsleft` must get the same values at the same moments: 0 on NavRouteClear / Docked / Touchdown / arrival / empty route, else `RemainingJumpsInRoute`, or route length minus 1 on NavRoute.
- Tests: new `scripts\check_route_status.py` with a temp journal folder: FSDTarget, NavRoute, NavRouteClear, arrival at the final system, empty NavRoute.json, and no folder listing when `last_journal_file` is set (patch `os.listdir` to fail). Also run `check_voiceattack_controls.py`.
- User test: plot a route, jump, clear the route, dock; check the jumps value VoiceAttack reads.

### 3a — FSDJump cache upserts off the UI thread

- In `_process_journal_event_impl` (FSDJump branch, `cargo_monitor.py` ~1678–1695), move only the two `marketplace_cache.db` upserts (`_upsert_pp_from_event`, `_upsert_system_info_from_event`) to one shared FIFO worker thread owned by CargoMonitor (a `queue.Queue` and one daemon thread, started once).
  - After each write, post the existing UI follow-up with `main_app.after(0, ...)`: `_fetch_sysfinder_pp_complete(..., quiet=True)` and `_sysfinder_apply_system_info`. Today the PP follow-up runs directly; it must now go through `after(0)`.
  - One worker keeps the writes in journal order.
- Leave `update_current_system` (visit recording, user DB in WAL, small single-row queries) on the UI thread.
- Failure path: an exception in a job is logged and the worker keeps running; the app closing with jobs queued drops them (same as today's daemon threads).
- Tests: add to `scripts\check_journal_reading.py`: the FSDJump branch queues the jobs and returns without touching the DB; jobs run in order; the UI follow-ups are posted through `after`; a failing job doesn't stop the next one.
- User test: jump with the Star Systems tab showing the current system; the PowerPlay and State columns still update after the jump.

### 3b — Scan / SAA writes off the UI thread (only if step 0 shows stalls, per D2)

- Use the same worker for `process_scan` → `update_ring_metadata` and `process_saa_signals_found`.
- The Ring Finder auto-refresh after a new ring or hotspot must run after the write: queue the refresh trigger as the next job, then post it with `after(0)`, instead of starting the delay timer right away.
- Check every listener that reads those rows on the same event batch; any that needs the stored data must also be posted through the worker.
- Tests: the auto-refresh is triggered only after the write job; order is kept across Scan then SAASignalsFound.
- User test: honk and map a ringed system with Auto Search on; new hotspots appear and are highlighted as before.

### 4 — Import matplotlib after the splash

- In `mining_charts.py`, move the matplotlib imports from module level into a small loader called from `MiningChartsPanel.__init__` (sets the module globals and `MATPLOTLIB_AVAILABLE`). `prospector_panel.py`'s `from mining_charts import MiningChartsPanel` then stays cheap.
- Keep `matplotlib.use('TkAgg')` before `pyplot` is imported.
- Check `report_generator.py` and `main.py:11440`: they import matplotlib inside functions already; don't change them.
- Packaging: check the main app spec's `hiddenimports` still lists `matplotlib.backends.backend_tkagg` (the user builds; don't run PyInstaller).
- Expected: the splash appears about 0.3 s sooner (more on a cold start). Total startup time doesn't change, since the panel is still built during startup.
- Tests: `check_mining_tab.py`; `-X importtime` shows no matplotlib when importing `prospector_panel`.

### 5 — Skip unchanged overlay redraw and cursor changes

- `CargoTextOverlay.update_cargo`: skip `_draw_text` when the message and font size equal the last drawn ones. Reset the stored message in `reinstate()`, `set_font_size()`, `set_enabled()` and when the window is recreated. Keep the existing alpha logic unchanged: the overlay vanish root cause was never found (see memory "Overlay visibility lessons"), so don't touch topmost or alpha here.
- `_handle_mouse_motion` (Reports table): only call `tree.configure(cursor=...)` when the value differs from `tree.cget("cursor")`.
- Tests: `check_cargo_tracking.py` (overlay) and `check_mining_tab.py`.
- User test: the cargo overlay updates when cargo changes, after a font size change, and after toggling the overlay off and on.

### 6 — Remove the stall logger, re-measure, final notes

- Run the step 0 user test again with the logger, record the after numbers, then remove the logger in its own commit.
- Patch notes: one player-facing line only if a change is noticeable (for example "The app no longer pauses briefly after a jump"). Steps 1, 2 and 5 are not player-visible.

## Measurements

21 Nov 2026, user's PC, read-only:

| What | Time |
|---|---|
| `os.listdir` of the journal folder (2,673 files) | 3.5 ms |
| One route poll (listing + tail read + JSON) | 3.5 ms, run by two timers every 2 s |
| `glob("Journal.*.log")` | 8.8 ms (CargoMonitor, background, every 5 s) |
| Game window lookup (`EnumWindows`, game not running) | 0.4 ms |
| `load_theme()` with disk reload | 0.14 ms |
| `marketplace_cache.db` commit of 15 price rows (copy) | 7.0 ms median, 26.1 ms max |
| matplotlib + pyplot + dates import (warm) | 0.33 s |
| Ring Finder count queries (49,647 rows) | 66 + 14 + 10 ms |

Step 0 baseline: logger added (`_start_ui_stall_logger` in `main.py`, `last_batch_info` in `cargo_monitor._deliver_journal_events`, both marked TEMP); user test and log numbers pending.

## Not verified

- No frame timings in the running app, nothing with the game running, no cold-start numbers.
- The real cost of C3 during a jump or FSS burst (step 0 measures it).
- Nothing visual.
