# Splitting main.py — Handover

Start a new chat with: "Read docs/MAIN_SPLIT_HANDOFF.md and continue with the next step."

## Goal

Make `app/main.py` (and later `prospector_panel.py` and `ring_finder.py`) smaller by moving self-contained code into its own modules. The aim is cheaper, safer AI-assisted edits and fewer clashes between parallel chats. It is not a rewrite.

## Rules

- Only move code, one step per commit. Never move and change behaviour in the same commit.
- Re-import moved names in `main.py` so existing references keep working.
- Patch with a script outside the repo: normalize to `\n`, assert one match each, restore CRLF, then `py_compile`.
- Check every moved block for names it used from `main.py` (`t`, `log`, helpers, constants) and import them in the new module.
- After each step: `py_compile`, an undefined-name scan of the new module, then the matching check scripts. The user restarts the app and tests it.
- Plain top-level imports are picked up by PyInstaller, so the specs need no change.
- Move tabs only when a task already touches that tab. Don't do a dedicated "refactor everything" push.
- Stop if a step causes trouble that's hard to explain.

## Progress

| Step | What | Status | main.py lines after |
|---|---|---|---|
| 0 | Starting point | — | 21,293 |
| 1 | Pilot: overlays and log handler | Done 20 Nov 2026, not committed, waiting for the user's app test | 20,515 (−778) |
| 2 | `CargoMonitor` into `cargo_monitor.py` | Next | about −2,690 |
| 3 | Tabs and dialogs, when they're touched | Open | — |
| 4 | `prospector_panel.py`, `ring_finder.py` | Later | — |

Line counts are physical lines, including blank lines.

## Step 1 — Pilot (done)

- New `app/overlays.py` (781 lines): `TextOverlay`, `CargoTextOverlay`, and the game-window helpers `_foreground_window_title`, `is_game_focused`, `_find_game_window_rect` and `get_game_monitor_offset`. It imports `t` from `localization` directly and uses the same `EliteMining` logger.
- `SafeRotatingFileHandler` moved into `app/logging_setup.py`.
- `main.py` re-imports all of these, so no other code changed.
- Verified: `py_compile` on all three files, standalone import of `overlays`, an undefined-name scan (none found), `check_sidebar.py` (6 tests OK).
- Not verified: the running app. The user's test is to restart the app, check that an announcement overlay and the cargo overlay show on the game monitor, and that `~\EliteMining.log` is written.
- Small difference: `main.py`'s own `t()` swallows translation errors, while `overlays.py` uses `localization.t` directly. It's only used for the overlay window title and the T/hr line.

## Step 2 — CargoMonitor (next)

- `class CargoMonitor` starts at about line 282 of `main.py` and runs to `class App` (about line 2968).
- Higher risk: it involves threading, the shared journal reader (`add_journal_listener`, see `docs/JOURNAL_REVIEW_HANDOFF.md`), and `_process_journal_event_impl` (about 540 lines).
- Before moving, list everything it uses from `main.py` (`_atomic_write_text`, constants from `core.constants`, `t`, `log`, config helpers) and anything that patches `main.CargoMonitor` in `scripts/check_*.py`.
- Checks to run afterwards: `check_cargo_tracking.py`, `check_journal_reading.py`, `check_session_location.py`, `check_fleet_carrier.py`, `check_sidebar.py`.
- Use the strongest model with high effort, and Plan mode.

## Step 3 — Candidates in App (move when touched)

The largest builder methods, by size: `_build_timers_tab` (about 760 lines), `_build_interface_options_tab` (710), `_build_announcements_tab` (530), `_create_main_sidebar` (450), `_build_system_finder_tab` (375), `_build_mining_commodities_tab` (305), `_build_trade_commodities_tab` (285), and backup/restore (`_create_backup`, `_show_restore_options_dialog`, about 500 together).

Lowest-risk approach: a mixin class in its own module (for example `class TimersTabMixin` in `timers_tab.py`), added to `App`'s bases, with the method bodies unchanged. Once a tab's code is in its own module, a proper class like `mining_missions_tab.py` is possible, but optional.
