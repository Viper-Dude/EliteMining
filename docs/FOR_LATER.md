# EliteMining - For Later

Saved: 17 November 2026

## Decision

Finish testing the journal-reading fix and, if everything works as intended, keep this release focused on stability. Leave the two remaining optimization items for a future release. There is no agreed release date for them.

Work on one item at a time, with approval before implementation and testing between changes. This document records future work; it does not authorize starting it.

## Where we stopped

| Original item | Status | Plain-English purpose |
| --- | --- | --- |
| 1. GUI responsiveness | Implemented; user reported Discord sharing and jumping, scanning, and mining worked | Keep slow online requests from holding up the app. |
| 2. Journal reading | Implemented; awaiting user confirmation from in-game testing | Prevent missed or repeated events when journal entries arrive in pieces, files change, or files are temporarily locked. |
| 3. Faster system lookups | Deferred | Help the app find system information more quickly in its local database. |
| 4. Safer settings saves | Deferred | Better protect saved preferences if a settings write is interrupted. |

After item 2, 107 relevant automated checks passed, including 34 new journal checks. This was targeted validation, not a claim that every project test passes. Previously identified Statistics UI test failures were outside this work.

Before considering item 2 fully verified, check normal jumping, prospector launches, scanning, mining, cargo, and session totals. Also leave EliteMining open while restarting the game to check switching to a new journal file.

## Item 3 - Faster system lookups

**What it means:** A database index acts like a book's index: it can help find a system without searching through many entries.

**Why revisit it:** Local system and coordinate lookups may become noticeably slower with a large database. An index that matches the actual search could help; it will not speed up a slow external service.

**Evidence and limits:** The coordinate lookup uses `WHERE name = ? COLLATE NOCASE`. Before changing anything, inspect the current database indexes and query plan and measure real lookup times. Do not assume a suitable index is missing or promise a speed increase without checking.

**Starting points:**

- `app/ring_finder.py`: `_get_system_coords_from_galaxy_db()`.
- `app/system_finder_api.py`: system-name lookups and related cache queries.
- The code that creates or updates the affected database, once the exact database and query are confirmed.

**Possible change:** Add only the index demonstrated to be useful, through the existing database setup/update path. Keep returned results and name matching identical.

**Benefit:** Faster affected local lookups if measurement confirms a bottleneck.

**Risk:** Low to medium. Index creation takes time and disk space and can slow database writes. Check compatibility with existing installations and the packaged database.

**Before calling it done:** Compare timings before and after; verify mixed-case names, unknown systems, coordinates, distances, and search results remain correct.

**Priority:** Medium; revisit when local searches feel slow or measurements justify it.

## Item 4 - Safer settings saves

**What it means:** Write the complete new settings to a temporary file, then replace the previous file after the write succeeds.

**Why revisit it:** `_save_cfg()` currently writes directly to the settings file. An interrupted or failed write could leave it incomplete. This is a verified write pattern and a potential failure risk; no settings loss was reported in this work.

**Starting points:**

- `app/config.py`: `_save_cfg()`, `_load_cfg()`, `flush_config()`, and the callers that update shared settings.
- `scripts/check_settings.py` and `scripts/check_voiceattack_controls.py`.

**Possible change:** Use a temporary file in the same directory and replace the settings file only after successfully writing it. Review overlapping saves so an older snapshot cannot overwrite newer settings.

**Benefit:** Better protection of preferences during interrupted or failed saves.

**Risk:** Medium. Many features share configuration. Preserve the existing cache, save throttling, pending-save flush, file location, preset behavior, and VoiceAttack compatibility.

**Before calling it done:** Simulate write/replacement failures using temporary files, confirm the previous settings survive, and verify rapid changes, restart persistence, presets, and backup/restore.

**Priority:** Medium; revisit for a future reliability release, or sooner if settings problems are reported.

## How to resume

### Handoff for in-game testing

- Item 1 touched `app/main.py`, `app/prospector_panel.py`, `app/journal_parser.py`, `app/api_uploader.py`, and `app/eddn_sender.py`. Its regression script is `scripts/check_network_responsiveness.py` (25 checks).
- Item 2 touched `app/main.py` and `app/prospector_panel.py`, added the shared `app/journal_reader.py`, and added `scripts/check_journal_reading.py` (34 checks). It covers partial writes, UTF-8, file rotation, locks, overlapping reads, startup history suppression, and catch-up checkpoints.
- The 107 passing checks comprised journal reading (34), network responsiveness (25), Fleet Carrier (17), cargo tracking (8), mining tab (12), VoiceAttack controls (8), and `VisitDataChecks` from `check_visited_systems.py` (3). The unrelated Statistics UI tests were excluded from that count.
- Run the relevant script with `.venv\Scripts\python.exe -B scripts/check_journal_reading.py` or `.venv\Scripts\python.exe -B scripts/check_network_responsiveness.py` from the project root. Tests use isolated fixtures; in-game testing is still needed.
- No release build, commit, or push was performed for these two fixes. The workspace also contains unrelated earlier changes; preserve them when investigating a problem.
- If testing reveals an issue, note what happened, what you expected, the approximate time, and whether the game had just restarted or created a new journal. Relevant logs are described in `ARCHITECTURE.md`.

### Returning to deferred work

Ask: "Read docs/FOR_LATER.md and review item 3 [or item 4]. Check whether it is still needed, explain the proposed change simply, and wait for my approval before implementing it."

Re-read the current project instructions and affected code first. Keep changes small, preserve existing features and behavior, and stop after the approved item for testing. Broader cleanup or rewrites are not part of these deferred items.
