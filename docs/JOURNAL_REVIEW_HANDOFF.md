# Journal Review Handoff

Updated: 20 November 2026 (after `9783abf`). Version in progress: 5.6.7 (not released).

Origin: an honest review of the GUI, features, performance, the file watcher (watchdog) and the journal parser. All planned batches, plus the silent-failure logging pass, are implemented and pushed. The first in-game test (installer build before `172c5b0`) is done; the fixes it led to still need a retest in the next test build.

## Commits (on origin/main)

- `f3ab5ae` Read the journal once, move the watch with the folder, and translate session UI text
- `6f95295` Log journal, overlay and voice failures instead of hiding them
- `7c7dca6` Move the new patch notes into the unreleased 5.6.7 notes
- `894b740` Log failed saves instead of hiding them, and write Auto Search state atomically (see "Silent-failure logging" below)
- `682016c` Add the 5.6.7 installer release notes
- `172c5b0` Fix missing ring type on carrier-side sessions and skip empty reports (see "In-game test findings" below)
- `9783abf` Fix splash hang at startup and log error prints in the installed app (see "Startup hang and print-to-log" below)

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

**In-game test findings (20 Nov 2026, installer build; fixed in `172c5b0`)**
- Jumps-left, prospecting and auto-end on supercruise worked. The log showed no failure lines except the two below.
- *Missing ring type:* with a carrier parked in a ring, the game only names the planet or moon (e.g. `2 a`, `BodyType: Planet`) on SupercruiseExit and on Location after undocking, never the ring. The report saved "2 A" (moon shown title-cased, looks like the ring) and the ring type lookup found nothing. Status.json has no BodyName in a ring, so it can't help. New `ProspectorPanel._resolve_session_ring` runs in `_session_stop`: a non-ring body becomes the ring last mined around that planet (reports CSV via `get_last_mined_lookup`; a moon `2 a` matches planet 2's rings), else the planet's only ring in `hotspot_data`, else unchanged.
- *0-ton reports:* `_session_stop` now saves nothing (report, CSV row, graphs) when cargo data says 0 t; with no cargo data it still saves.
- *Auto-switch "too fast":* switch logic is unchanged since 5.6.6; events now arrive every 0.5 s instead of up to 1 s. On user request the Hotspots Finder switch now waits `RING_FINDER_SWITCH_DELAY_MS` (3000) after SupercruiseEntry/FSDJump/session end in supercruise, is cancelled on SupercruiseExit, and re-checks the guards when it fires.
- *Crash:* `_handle_journal_events` used `self.app` on CarrierLocation (pre-existing, now visible through listener logging); it dropped the rest of that event batch for the Mining Session. Now `self.main_app`.
- *Startup "Journal capacity/ship scan failed":* the CargoMonitor startup scan called `_on_cargo_capacity_detected` before `cargo_max_capacity` existed. It now defers with `after(0)`.
- The constant ~8 s gap between journal timestamps and log times is the game clock ahead of the PC clock, not app lag.
- Checks after `172c5b0`: `check_session_location` (8, two new), `check_mining_tab` (12), `check_session_statistics` (17), `check_journal_reading` (42), `check_cargo_tracking` (8). All passed.

**Startup hang and print-to-log (`9783abf`)**
- *Splash hang:* the `172c5b0` deferral (`after(0)` in `_on_cargo_capacity_detected` when `cargo_max_capacity` did not exist yet) re-queued itself forever, because the splash `update()` keeps running pending callbacks. The installer build hung on "Initializing systems...". The capacity is now stored in `_pending_detected_capacity` and applied right after `_load_cargo_preferences()` in `App.__init__`, wrapped in try/except with `log.exception`. Never use `after(0)` for startup-time retries while the splash is up.
- *Charmap crash:* the "Auto-updated cargo capacity" print contained an emoji and raised a charmap error on a cp1252 console; it is now a `log.info` without the emoji. Other emoji prints can hit the same error (the VA variables init already logged one with a check mark).
- *Print-to-log:* 272 single-argument `print(` calls whose message contained error/fail/warning/exception became `log.error` or `log.warning` (104 `main.py`, 100 `prospector_panel.py`, 68 `ring_finder.py`; "warn" in the text gives warning). Two stay prints because they run before logging exists (localization init warning, single-instance mutex warning). Prints reporting a failure without those words are not converted.
- Checks passed: `check_cargo_tracking` (8), `check_journal_reading` (42), `check_session_location` (8), `check_ring_finder_search` (11); the dev app got past the splash with a cp1252 console. Installer build not yet retested.

## Open items

1. **Retest passed on the installer build from `9783abf` (20 Nov 2026).** Splash, startup log, supercruise tab switch, carrier ring type and empty-session reports all worked. The log showed one leftover `self.app` in the CarrierLocation handler (distance update), now `self.main_app`; uncommitted, needs a rebuild and carrier retest. Original list:
   - The app gets past the splash screen, and the startup log has no "Applying detected cargo capacity at startup failed" line.
   - Error lines from the converted prints now appear in the installed log.
   - About 3 s after entering supercruise, the tab switches to Hotspots Finder (if the app was idle for 30 s).
   - A session started after undocking from the carrier in the ring shows "2 A Ring / Metallic" in Reports.
   - Starting and stopping a session without mining saves no report.
   - No "Journal capacity/ship scan failed" or "Journal listener ... failed" lines in the startup log.
2. Not yet covered by the first test: changing the journal folder, restarting the game while the app runs, German session summary, importing journal history, and the `894b740` smoke test (delete a report, Ring Finder filters, announcement preset, Auto Search and prefetch prices toggles). Unless the user reports otherwise, treat these as untested.

## Deliberately skipped (and why)

- **Sorting journal files by name in `JournalParser.find_journal_files`:** old journal file names use a different date format, so name order can be wrong. Keep mtime.
- **`transient()` in 13 live dialogs, plus hardcoded dark backgrounds** (~58 spots in `main.py`, `prospector_panel.py`, `ring_finder.py`): each dialog has its own show sequence, some use `transient` on purpose, and the result can't be verified without seeing it. Fix a dialog when it is next changed. The four Ring Finder right-click dialogs also lack `withdraw()` and can flash on the wrong monitor.
- **About 316 remaining silent `except: pass` blocks across `main.py`, `prospector_panel.py` and `ring_finder.py`.** The first in-game logs pointed only at the two failures fixed in `172c5b0`, so there is no lead for more. Revisit only if new log lines appear. Tier-B reasons are listed under "Silent-failure logging".
- **Patch notes for `172c5b0`:** left out on user request.
- **306 `hasattr(self, ...)` guards and the remaining non-error `print(` calls in `main.py`:** pointed out in the review, no fix requested.

## Local state at handover

- Uncommitted and not mine: `app/Variables/miningSessionSummary.txt` (dev-run output). `docs/INSTALLER_RELEASE_NOTES.txt` was committed in `682016c` at the user's request.
- The two `app/config.json.backup_*` files were deleted.
- `app/main.py`, `prospector_panel.py`, `ring_finder.py`, `file_watcher.py` are CRLF; `config.py`, `journal_parser.py`, the localization JSON and `scripts/check_*.py` are LF.
