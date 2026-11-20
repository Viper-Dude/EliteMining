# Journal Review Handoff

Updated: 20 November 2026. Version in progress: 5.6.7 (not released).

Origin: an honest review of the GUI, features, performance, the file watcher (watchdog) and the journal parser. All planned batches, plus the silent-failure logging pass, are implemented and pushed. The in-game test is still pending.

## Commits (on origin/main)

- `f3ab5ae` Read the journal once, move the watch with the folder, and translate session UI text
- `6f95295` Log journal, overlay and voice failures instead of hiding them
- `7c7dca6` Move the new patch notes into the unreleased 5.6.7 notes
- `894b740` Log failed saves instead of hiding them, and write Auto Search state atomically (see "Silent-failure logging" below)

## What changed

**Journal reading (`app/main.py`, `app/prospector_panel.py`, `app/ring_finder.py`)**
- `CargoMonitor` is the only live journal reader. `_read_new_journal_entries` parses each line once and `_dispatch_journal_events` sends one `after(0)` per batch to the main thread. `_deliver_journal_events` runs cargo first, then each listener, each isolated by try/except with `log.exception`.
- Anything needing live journal events registers with `cargo_monitor.add_journal_listener(cb)` and receives a list of parsed dicts. Current listeners: `ProspectorPanel._handle_journal_events` and `RingFinder._on_journal_events`. Never read the file or wrap `process_journal_event`.
- `_process_journal_event_impl` accepts a dict or a string. `market_handler.process_journal_event` is called from there for every line (EDDN game state).
- `ProspectorPanel._watch_once` is gone. `_attach_journal` only reads the initial location; `_handle_journal_events` holds the old loop body. The startup "old event" skip is now `continue`, not `return`.
- The background monitor loop no longer exits when `journal_monitor_active` is False; it pauses.
- The journal folder is re-listed at most every 5 s (`_journal_list_time`) in the cargo monitor.

**Watchdog (`app/file_watcher.py`, `app/main.py`)**
- The callback handles only Market.json and NavRoute.json. The old "last 2 KB / last 10 lines" journal branch is deleted.
- Jumps-left is owned by the 2 s `_poll_route_status` in `main.py`. It can lag up to 2 s.
- `App._rewatch_journal_dir(old, new)` moves the watch when the journal folder changes (both change sites).
- The 100 ms debounce in `EliteFileHandler` now defers instead of dropping: the first change in a burst fires immediately, later ones schedule one trailing call (`_pending`, one timer per file). Covered only by a throwaway test, not a repo check.
- `remove_watch` unschedules the watchdog handler (`self.watches`). One module-level `_is_elite_file` (includes navroute.json).

**UI and logging**
- Session summary line: `mining_session.summary_*` keys (en/de), theme colours via `_summary_colors`.
- Import journal history window: standard dialog order, `dialogs.*` keys, updates via `after(0)`, error shown on failure.
- Silent `except: pass` now logs in: Status.json check, journal capacity scan, journal event processing, capacity recovery, forced Loadout scan and cargo refresh, prospector `_tick` (once per distinct error), live summary, overlay destroy and timer cancel (TclError ignored), Ring Finder auto-refresh, saved voice, voice list, preset file listing.
- Removed unused code: `CargoMonitor.reset_cargo_hold`, `App.reset_cargo_hold`, `App._validate_cargo_monitor`.

**Silent-failure logging (`894b740`)**
- Of 339 `except: pass` blocks in `main.py`, `prospector_panel.py` and `ring_finder.py`, 23 that guard writes now log: active announcement preset save/clear/retry, marketplace filters on close, system visit recording (`record_system_visit` logs each distinct error once), last-known-system read, forced cargo refresh, first-install scan (one summary warning for failed hotspot events), report delete (graph/screenshot files and mapping JSON), report filter save, Ring Finder filter save/load, hotspot coordinate commit, Auto Search and prefetch prices state saves.
- `ring_finder.py` now has a module `log`.
- `_save_auto_search_state` and `_save_prefetch_prices_state` write `Variables/autoSearch.txt` and `prefetchPrices.txt` through `_atomic_write_text()`. A failed write logs "Atomic write failed for ..." from `config.py`.
- Deliberately left silent: read-only per-row DB lookups during search and display refresh (would flood the log), Tk/UI blocks, parsing fallbacks, crash-log writers, legacy file cleanup, `_atomic_write_text` fallback cleanup, `_sync_fc_location` (x2), the resume-offset seek in `_process_journals_for_catchup`.
- New failure-path checks: `check_visited_systems` (failed visit save logs once), `check_ring_finder_search` (`RingFinderSaveFailureTests`: filter save logs; Auto Search file written atomically and a failed write is logged).

**Checks** (`app\.venv\Scripts\python.exe scripts\check_<area>.py`)
- `check_journal_reading` (42; includes `SharedReaderChecks`, `BackgroundMonitorChecks`, folder-relist throttle), `check_session_location` (6), `check_cargo_tracking` (8), `check_fleet_carrier` (17), `check_network_responsiveness` (25), `check_session_statistics` (17), `check_mining_tab` (12), `check_sidebar` (6), `check_settings` (14). All passed at last run. After `894b740` these also passed: `check_visited_systems` (6), `check_ring_finder_search` (11), `check_config_saving` (14), `check_voiceattack_controls` (13).
- Not run: PyInstaller build, anything in the real game. The dev app was started and looked fine.

## Open items

1. **In-game test (user, pending):**
   - Launch a prospector; the session should auto-start, and prospecting results and cargo should update.
   - Plot a route; jumps-left counts down and drops to 0 on docking.
   - Auto Search / Auto Prices triggers once per jump.
   - Change the journal folder, then dock at a market; an EDDN upload is logged.
   - Restart the game while the app runs; the new journal is picked up within ~5 s.
   - Session summary in English and German.
   - Settings -> import journal history with a real folder.
   - Check the log for new "failed" lines from the logging changes.
   - Also smoke-test the `894b740` changes: delete a report in Reports, change Ring Finder filters, pick an announcement preset, toggle Auto Search and prefetch prices (`Variables/autoSearch.txt` and `prefetchPrices.txt` should flip between 1 and 0).
2. **`docs/INSTALLER_RELEASE_NOTES.txt`** (user-owned): add the five new 5.6.7 lines (see `PATCHNOTES_v5.6.7.md`).

## Deliberately skipped (and why)

- **Sorting journal files by name in `JournalParser.find_journal_files`:** old journal file names use a different date format, so name order can be wrong. Keep mtime.
- **`transient()` in 13 live dialogs, plus hardcoded dark backgrounds** (~58 spots in `main.py`, `prospector_panel.py`, `ring_finder.py`): each dialog has its own show sequence, some use `transient` on purpose, and the result can't be verified without seeing it. Fix a dialog when it is next changed. The four Ring Finder right-click dialogs also lack `withdraw()` and can flash on the wrong monitor.
- **About 316 remaining silent `except: pass` blocks across `main.py`, `prospector_panel.py` and `ring_finder.py`.** Next step after the in-game test: use the new log lines to find which silent blocks hide real failures, and convert those. Tier-B reasons are listed under "Silent-failure logging".
- **306 `hasattr(self, ...)` guards and 356 `print(` calls in `main.py`:** pointed out in the review, no fix requested.

## Local state at handover

- Uncommitted and not mine: `app/Variables/miningSessionSummary.txt` (dev-run output), `docs/INSTALLER_RELEASE_NOTES.txt` (user-owned).
- The two `app/config.json.backup_*` files were deleted.
- `app/main.py`, `prospector_panel.py`, `ring_finder.py`, `file_watcher.py` are CRLF; `config.py`, `journal_parser.py`, the localization JSON and `scripts/check_*.py` are LF.
