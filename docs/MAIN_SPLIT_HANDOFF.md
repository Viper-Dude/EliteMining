# Splitting main.py — Handover

Start a new chat with: "Read docs/MAIN_SPLIT_HANDOFF.md and continue with the next step."

## Goal

Make `app/main.py` (and later `prospector_panel.py` and `ring_finder.py`) smaller by moving self-contained code into its own modules. The aim is cheaper, safer AI-assisted edits and fewer clashes between parallel chats. It is not a rewrite.

## Rules

- Only move code, one step per commit. Never move and change behaviour in the same commit.
- Re-import moved names in `main.py` so existing references keep working.
- Patch with a script outside the repo: normalize to `\n`, assert one match each, restore CRLF, then `py_compile`.
- Check every moved block for names it used from `main.py` (`t`, `log`, helpers, constants) and import them in the new module. Use a scope-aware scan (Python's `symtable`: report each function's implicit globals the module doesn't define). A flat AST scan misses names that one method imports locally while another relies on `main.py`'s import; that caused the `JournalParser` startup crash in step 2. The check scripts can't catch it either, because they run methods in their own namespaces.
- After each step: `py_compile`, an undefined-name scan of the new module, then the matching check scripts. The user restarts the app and tests it.
- Plain top-level imports are picked up by PyInstaller, so the specs need no change.
- Move tabs only when a task already touches that tab. Don't do a dedicated "refactor everything" push.
- Stop if a step causes trouble that's hard to explain.

## Progress

| Step | What | Status | main.py lines after |
|---|---|---|---|
| 0 | Starting point | — | 21,293 |
| 1 | Pilot: overlays and log handler | Done, user-tested, committed `1b7eee1` | 20,515 (−778) |
| 2 | `CargoMonitor` into `cargo_monitor.py` | Done and committed 20 Nov 2026; app start and cargo list OK, in-game test pending | 17,833 (−2,682) |
| 3 | Tabs and dialogs, when they're touched | In progress (only alongside other work) | — |
| 3a | VoiceAttack Controls tab into `voiceattack_controls_tab.py` | Done 22 Nov 2026; checks OK, app test pending | 16,734 (−1,116) |
| 3b | Commodity Market tab into `commodity_market_tab.py` | Done 22 Nov 2026; checks OK, user-tested | 14,275 (−2,363) |
| 3c | Distance Calculator tab into `distance_calculator_tab.py` | Done 23 Nov 2026 (`6719590`); checks OK | 13,831 (−444 from the move) |
| 4 | `prospector_panel.py`, `ring_finder.py` | Later | — |
| 4a | Best Minerals to Mine and Auto Prices into `best_minerals_view.py` (`BestMineralsMixin`) | Done 23 Nov 2026; checks OK | ring_finder.py 8,181 (−1,015) |

Line counts are physical lines, including blank lines.

## Step 1 — Pilot (done)

- New `app/overlays.py` (781 lines): `TextOverlay`, `CargoTextOverlay`, and the game-window helpers `_foreground_window_title`, `is_game_focused`, `_find_game_window_rect` and `get_game_monitor_offset`. It imports `t` from `localization` directly and uses the same `EliteMining` logger.
- `SafeRotatingFileHandler` moved into `app/logging_setup.py`.
- `main.py` re-imports all of these, so no other code changed.
- Verified: `py_compile` on all three files, standalone import of `overlays`, an undefined-name scan (none found), `check_sidebar.py` (6 tests OK), and the user's app test (overlays and log OK).
- Small difference: `main.py`'s own `t()` swallows translation errors, while `overlays.py` uses `localization.t` directly. It's only used for the overlay window title and the T/hr line.
- Seen during the test, not caused by the move: with no `overlay_mode` saved, the settings screen falls back to Enhanced (`main.py` `_load_text_overlay_preference`) but `prospector_panel.py` `_show_prospector_overlay_or_standard` falls back to Standard. Fixed 20 Nov 2026: the prospector fallback is now "enhanced" too.

## Step 2 — CargoMonitor (done, in-game test pending)

- New `app/cargo_monitor.py` (about 2,700 lines) holds `class CargoMonitor` unchanged. It imports `glob, json, logging, os, re, threading, time, tkinter as tk`, `_load_cfg`, `JournalParser`, `journal_resume_offset`, `read_complete_journal_lines`, `t` (from `localization`), `centered_yesno_dialog`, `RefineryDialog` and `UserDatabase`, and uses the `EliteMining` logger.
- Everything it uses from the app goes through `self.main_app_ref`, so it has no links to `main.py` globals.
- `main.py` imports it back with `from cargo_monitor import CargoMonitor`. The now-unused imports `journal_resume_offset`, `read_complete_journal_lines`, `UserDatabase` and `RefineryDialog` were removed from `main.py`.
- Check scripts that read `CargoMonitor` source now point to `app/cargo_monitor.py`: `check_cargo_tracking.py`, `check_fleet_carrier.py`, `check_journal_reading.py`, `check_network_responsiveness.py`.
- Verified: `py_compile`, standalone import, undefined-name scan (none), and 106 tests OK across `check_cargo_tracking` (8), `check_journal_reading` (42), `check_fleet_carrier` (17), `check_network_responsiveness` (25), `check_session_location` (8) and `check_sidebar` (6).
- First run crashed with `name 'JournalParser' is not defined`. Fixed by adding the missing imports (`JournalParser`, `re`, `time`, `tk`) found by the scope-aware scan. A later "hang at start" could not be reproduced; the next start was fine.
- User-tested: the app starts and the cargo list is correct. Still to test in game (the user will do it at the end of the task): a jump or docking updates the current system; mining a fragment updates the cargo count and the cargo overlay; the log shows no new errors.
- Commit by staging the specific paths. Running the app changes tracked `Variables/*.txt` files, so don't use the broad `git add -A` for this work.

## Step 3 — Candidates in App (move when touched)

The largest builder methods, by size: `_build_interface_options_tab` (710), `_build_announcements_tab` (530), `_create_main_sidebar` (450), `_build_system_finder_tab` (375), `_build_mining_commodities_tab` (305), `_build_trade_commodities_tab` (285), and backup/restore (`_create_backup`, `_show_restore_options_dialog`, about 500 together).

Step 3c: `DistanceCalculatorTabMixin` holds the builder and all Distance Calculator methods (build, fills, home save, location refresh, calculation and live Home/Carrier updates, `get_distance_info_text`). `_check_market_api_status` and `_queue_search_service_status`, which sat in that section, stay in `main.py`. `check_distance_calculator.py` loads the mixin from the new module.

Step 3b: `CommodityMarketTabMixin` holds the Mining and Trade Commodities builders, tables, context menus, preferences, searches, display, Powerplay fill-in and sorting (55 methods). Star Systems and `_check_market_api_status` stay in `main.py`; Multiple Prices and Sell My Hold were already separate modules. `check_marketplace.py` and `check_search_stop.py` load these methods from the new module. It imports `localization.t` directly, like step 3a, instead of `main.py`'s error-swallowing wrapper.

Step 3a: `VoiceAttackControlsTabMixin` holds `_build_voiceattack_controls_tab`, `_build_voice_feedback_tab`, `_build_fg_tab` and `_build_timers_tab` unchanged; the helpers they call (`_save_toggle`, `_update_*_dependencies`, sound-event methods) stay in `main.py`. `check_voiceattack_controls.py` reads `_build_timers_tab` from the new module.

Lowest-risk approach: a mixin class in its own module (for example `class TimersTabMixin` in `timers_tab.py`), added to `App`'s bases, with the method bodies unchanged. Once a tab's code is in its own module, a proper class like `mining_missions_tab.py` is possible, but optional.
