# EliteMining — Shared Project Instructions (Claude Code and Codex)

This is the single instruction file for both assistants. Codex loads it directly; Claude Code loads it through the `@AGENTS.md` import in [CLAUDE.md](CLAUDE.md). Keep all shared architecture, UI conventions and working rules here. Keep `CLAUDE.md` to that import line plus any Claude-only notes, and put Codex-only notes in the "Codex Only" section at the end. Do not copy these rules into saved memory.

Read applicable nested instruction files and task-relevant documents referenced here. Current explicit user instructions take precedence over saved rules. Treat saved memory as context; report unresolved conflicts before making affected changes.

## Chat Rules

- **Be concise.** Short, direct responses. No padding, no preamble, no trailing summaries of what you just did.
- **Code-first.** Proceed directly with straightforward work. Keep required progress updates brief and useful; avoid narrating routine tool calls.
- **No unsolicited refactoring.** Fix what was asked. Don't clean up surrounding code, rename variables, or restructure unless explicitly requested.
- **No feature creep.** Don't add error handling, validation, or abstractions for scenarios not in scope. Don't design for hypothetical future requirements.
- **No comments unless the WHY is non-obvious.** Don't explain what the code does. Don't add task/PR references in comments.
- **No emojis** unless explicitly asked.
- **Follow existing patterns.** Match the style, naming conventions, and architecture already in the codebase. Check how similar things are done before inventing a new approach.
- **Reuse existing functions.** Before writing new logic, search the likely modules for an existing function that does it (or almost does it), including across tabs (e.g. distance/coordinate lookups in `ring_finder.py`). Reuse or minimally extend it instead of duplicating the implementation. Keep the search bounded to the requested behavior; widen it only when evidence points elsewhere. Text-only edits do not require a helper search.
- **Patch notes** (`docs/PATCHNOTES_v*.md`): one short, precise sentence per change, plain English from the player's view. No technical or dev language (no EDDN, API, cache, database, function names). Put new features and improvements under "New Features & Improvements" and fixes for broken behavior under "Bug Fixes" (both are in `docs/PATCHNOTES_TEMPLATE.md`).
- **Git commits**: No `Co-Authored-By` trailers. Commit messages should be concise and focus on the "why".
- **When uncertain**, ask one targeted question if the uncertainty materially affects scope, correctness, or risk. Resolve routine implementation choices using existing patterns and session context.
- **Don't re-explain decisions** already made in the conversation. Move forward.
- **End-of-chat review.** When the user says they are ending the chat, check whether any lasting decisions, preferences, lessons, or unresolved issues should be saved to project memory or documentation. Check existing guidance to avoid duplication. Update only files the user has authorized you to modify; otherwise briefly identify any recommended updates. Do not save routine chat history or make changes when nothing useful needs preserving.

---

## Task Effort and Validation

Scale inspection, planning, and validation to the change's complexity and consequences. Risk takes precedence over patch size; a small change to database writes, threading, shared configuration, or a VoiceAttack contract may need extensive validation.

- **Small, low-risk tasks** (wording, simple UI adjustments, minor configuration changes): inspect the relevant code and required paired resources, make the change directly, and review the diff with an applicable syntax, format, or visual check. Avoid elaborate plans and full test suites unless a specific risk justifies them.
- **Keep validation proportional.** For small changes, inspect the affected code, review the diff, and run only focused checks for the changed behavior. Do not run broader regression suites or tests that open windows unless the change directly affects those areas or a focused check reveals a specific problem. Explain why before running disruptive tests. Keep searches narrow and avoid unrelated investigation to conserve usage.
- **User testing workflow.** The user always restarts `app/main.py` and manually tests after each fix or implementation. For small changes, use focused code and syntax checks rather than duplicating the user's UI testing. Avoid opening test windows unless needed to investigate a specific problem. Do not assume the user's planned testing has already passed.
- **Manual test instructions only when needed.** If the user needs guidance to verify a change, provide a simple, short numbered list with one action and its expected result per step. Omit test instructions when the behavior is obvious or no guidance is needed.
- **Medium tasks** (bug fixes, existing-feature changes, several affected functions): inspect affected code paths and direct dependencies, run targeted tests, and check likely regressions.
- **Large or high-risk tasks** (architecture, major refactoring, concurrency, database changes, multiple components): examine dependencies and integration points, and run appropriate comprehensive tests covering compatibility and relevant failure or recovery paths.
- **Read once, reuse context.** Read original instruction files and the memory index once per session, plus task-relevant linked guidance. Reuse established facts; reread when files change, context is missing, or newly relevant scope requires additional guidance. Do not read unrelated memories or repeatedly inspect unchanged code.
- **Keep investigation focused.** Start with the reported symptom and the smallest useful inspection. For runtime-value bugs, prefer a targeted observation or diagnostic and one reproduction over speculative exploration. Broaden the search when evidence warrants it.
- **Use tools efficiently.** Batch independent searches and reads, request only useful output, and keep plans proportional to the work.
- **Choose checks for a reason.** Each test or validation step should answer a specific correctness or regression question. Add tests where they provide meaningful coverage; avoid tests that merely mirror implementation details. Do not reduce necessary testing to save tokens.
- **Stop when sufficient evidence exists.** Once the requested behavior is supported and applicable checks pass, stop. Repeat or broaden checks only after relevant edits, failures, or new unresolved concerns. Report validation and material limitations accurately.

---

## Project Overview

**EliteMining** is a Python/Tkinter desktop application for Elite Dangerous mining. Read the current version from `__version__` in `app/version.py`; do not duplicate the version number here.

**Two modes**: standalone and VoiceAttack-integrated.

**Key data sources**:
- Elite Dangerous journal files (`~/Saved Games/Frontier Developments/Elite Dangerous/`)
- EDDN (Elite Dangerous Data Network) live feed — commodity prices, powerplay, station metadata
- Spansh API — ring/system search, reserve levels
- Inara — powerplay data (HTML scrape with bot-challenge solving)
- Local SQLite databases: `marketplace_cache.db` (EDDN cache), user database (`user_database.py`)

---

## Core Architecture

### Main Modules
- **`app/main.py`** — Multi-tabbed Tkinter app, CargoMonitor, dark theme, ToolTip system
- **`app/ring_finder.py`** — Ring Finder tab: Spansh/local search, results treeview, context menu, PP column
- **`app/system_finder_api.py`** — Spansh API wrapper + Inara powerplay HTML fetch
- **`app/eddn_listener.py`** — EDDN ZMQ listener, writes to `marketplace_cache.db`
- **`app/journal_parser.py`** — Journal file monitoring and event parsing
- **`app/user_database.py`** — Local ring/hotspot/visit database
- **`app/prospector_panel.py`** — Prospector session tracking from journal
- **`app/config.py`** — Rate-limited config load/save, path detection, theme
- **`app/localization/`** — `strings_en.json` + `strings_de.json`; use `from localization import t`

### Threading Pattern
Background work always uses a daemon thread + `parent.after(0, callback)` to run UI updates on the main thread:
```python
threading.Thread(target=self._worker, args=(arg,), daemon=True).start()

def _worker(self, arg):
    result = do_work(arg)
    self.parent.after(0, lambda: self._complete(result))
```

### Inline Imports in Background Methods
`ring_finder.py` imports `SystemFinderAPI` inline inside thread worker methods (not at module top):
```python
def _some_worker(self, arg):
    from system_finder_api import SystemFinderAPI
    result = SystemFinderAPI.some_method(arg)
```

### Localization
Always update **both** `strings_en.json` and `strings_de.json` for any new UI string. Never hardcode user-visible text in Python.
```python
from localization import t
label = t('section.key')
text_with_var = t('section.key').format(name=value)
```

---

## Ring Finder

`ring_finder.py` is the largest and most complex module. Key patterns:

- **Treeview**: `ttk.Treeview` with `selectmode='extended'` — Ctrl+click adds rows, Shift+click selects range
- **PP column** (index 11): displays `"Power / State"` or `t('common.pp_no_data')` (`"No data  ↗"`)
- **Context menu**: single-select shows full menu; multi-select shows a separate `multi_menu` with limited options
- **Column indices**: Distance=0, LS=1, System=2, Planet/Ring=3, Sol Dist=4, Visits=5, Ring Type=6, Reserve=7, Hotspots=8, Overlap=9, RES Site=10, PowerPlay=11, Source=12
- **Source column emojis**: `🌐` = Spansh, `🗄️` = Local DB, both = Both

### Powerplay Fetch (Inara)
`SystemFinderAPI.fetch_and_store_powerplay_from_inara(system_name)` in `system_finder_api.py`:
- Uses `requests.Session()` with browser User-Agent
- Detects Inara's bot challenge page (`validatechallenge.php`) and solves it automatically
- Stores result in `system_powerplay` table of `marketplace_cache.db`
- Returns `{'controlling_power': ..., 'power_state': ...}` or `None`

Batch fetch: `PP_FETCH_MAX_BATCH = 25`, `PP_FETCH_DELAY_SECS = 1.5` (sequential, rate-limited).

---

## EDDN & Database

### marketplace_cache.db
SQLite database at `SystemFinderAPI.EDDN_CACHE_PATH` (set from `main.py` after EDDN listener starts).

Key tables:
- `commodity_prices_data` — live market prices from EDDN
- `system_powerplay` — `(system_name PK, controlling_power, power_state, powers, updated_at)`
- `station_metadata` — station details
- `system_coords` — system coordinates

### EDDN Powerplay Fields (PP2.0)
From `FSDJump`/`Location` journal events:
- `ControllingPower` — the controlling power name (PP2.0 explicit field)
- `PowerplayState` — the system's powerplay state (Stronghold, Fortified, Exploited, etc.)
- `Powers` — list of all powers present

---

## Dialog / Popup Rules

Every `tk.Toplevel` dialog must follow this order exactly to avoid blinking or freeze on multi-monitor:

1. `dialog.withdraw()` — immediately after `tk.Toplevel()`, before any other setup
2. **No `transient()`** — causes dialogs to hide behind parent and freeze
3. Theme colors from `load_theme()` in `config.py`; use `tk.Frame`/`tk.Label` with explicit `bg`/`fg`, not `ttk`
4. Set icon via `get_app_icon_path()` (`app_utils.py`) in a try/except
5. Add all widgets while dialog is hidden
6. `dialog.update_idletasks()`
7. `center_window(dialog, self.parent.winfo_toplevel())` from `ui/dialogs.py`
8. `dialog.deiconify()`
9. `dialog.attributes('-topmost', True)` → `dialog.lift()` → `dialog.focus_force()`
10. `grab_set()` in a try/except
11. `keep_on_top()` loop — reschedules every 100ms via `dialog.after`

Use `centered_info_dialog` / `centered_yesno_dialog` from `ui/dialogs.py` for standard dialogs — they already implement all of the above.

---

## UI Conventions

- **Column headers**: use short wording consistent with matching columns in existing tabs. Set each column's minimum width to its translated header text measured with the scaled heading font, plus scaled padding, so headers cannot be squeezed or clipped. Default and restored widths must respect that minimum.

- **Tables**: columns and headers are left-aligned by default (a Treeview can't pad cells, so right-aligned numbers touch the next column); center a column only where it looks clearly better. Centered today: the two Announcement material tables stay centered, and the Ring Finder Fav (star), Source and Visits columns.
- **Theme colours for new widgets**: Every new widget must use the active theme's colours, never default widget styling. Take colours from the same source as the neighbouring widgets (`load_theme()` / `get_theme_colors()`, or `ttk.Style().lookup(...)` of the parent's style) and set explicit `bg`/`fg`/`selectcolor`/`activebackground` on `tk` widgets such as checkbuttons. A default `ttk.Checkbutton` or similar looks wrong on the Modern and Elite Orange themes. Check new widgets visually in each theme.
- **Modern themes (`modern`, `modern_slate`, `modern_orange`)**: `_modern_recolor_all()` in `app/main.py` only remaps a fixed list of hardcoded greys, once per tab and once per popup, so widgets built or rebuilt later must take their colours from the theme when created. A `tk.Button` with `textvariable` or `image` bypasses `ModernButton` and is never recolored. Use `ttk.Scrollbar`, not `tk.Scrollbar`, in Modern. Gate Modern-only changes on all three theme names so Elite Orange and Dark Gray stay unchanged.
- **Feedback messages**: There is no global status bar. `EliteMiningApp._set_status()` only logs (`[Status]`). Show useful transient feedback (preset confirmations, scan progress, errors) in a label next to the relevant controls with `_show_notice(label, msg)`, using localized strings. Routine confirmations such as toggles stay log-only; real errors may use a popup. Journal scan progress uses `_set_journal_scan_status()` (footer row).
- **Overlays**: "Enable Text Overlay" is the master switch for every overlay, including Auto Prices (off = Auto Prices uses the popup).

### New and Changed Tables

Apply these rules whenever creating a table or changing an existing table's columns or layout:

- **Existing patterns**: inspect the closest table in the app first (especially Ring Finder and Commodity Market). Reuse existing helpers, theme styles, scaled fonts, and spacing; do not create a separate table framework.
- **Alignment**: left-align headers and cells by default, preserving the centered exceptions listed above.
- **Headers and minimum widths**: use short, localized headers and measure them with the scaled heading font plus scaled padding. Default, restored, and shown-again column widths must respect that minimum.
- **Manual resizing**: use `stretch=False` for data columns so Tk does not redistribute their widths. Do not impose a maximum width or reset the user's width during refresh or layout changes. If a table needs an expanding filler column, follow the existing Ring Finder pattern.
- **Scrolling**: provide working horizontal and vertical scrollbars so wide columns and rows beyond the visible height remain reachable.
- **Visibility and ordering**: reuse `ColumnVisibilityMixin` from `app/column_visibility_helper.py` where the table offers column controls. Use `use_displaycolumns=True` to fully hide columns, and resolve clicked or hovered columns with `displayed_column()` rather than fixed display indices. Reuse existing reorder support where applicable.
- **Persistence**: follow existing column-width, visibility, and order persistence through `app/config.py`. Save user resizing and restore it without clipping translated headers; keep hidden columns hidden.
- **Number formatting**: match equivalent columns in existing tabs. LS uses Ring Finder's whole-number format with thousands separators (`f'{int(float(value)):,}'`); LY uses the existing distance precision. Keep unknown values distinct from zero and sort numeric columns by their underlying numeric values.
- **Localization and scale**: use both English and German strings and the app's UI scale helpers; do not hardcode new user-visible labels or unscaled table dimensions.

For new tables, substantial table changes, or shared table-helper changes, verify the full applicable checklist below. For localized changes, check only affected behavior and credible regressions: a header wording change needs translated-header and minimum-width checks, but does not by itself require retesting unchanged ordering or persistence.

1. Drag columns wider and narrower: widths remain stable after release, result refresh, and window resizing; headers remain readable at the minimum width.
2. Scroll horizontally through wide columns and vertically through all rows.
3. Save and reopen the table: widths, visibility, and supported ordering restore correctly.
4. Hide, show, and reorder columns where supported: no text slivers, incorrect context menus, or mismatched tooltips.
5. Check English and German headers, supported UI scales, and number formatting, including fractional LS, zero, and missing data.

Report applicable checks that could not be run; do not claim visual verification from code inspection alone.

---

## Logs

- **Installed build**: `%LOCALAPPDATA%\EliteMining\logs\elitemining_<timestamp>.log` (one file per session, from `logging_setup.py`).
- **Dev run** (`python app/main.py`): `~\EliteMining.log` (rotates at 512KB to `.log.1`, so search `.log.1` too).
- Only INFO and above is written; overlay diagnostics are tagged `[OVERLAY]`.

---

## Build & Release

The user handles all installer and release-package builds. Agents must limit their work to code changes and tests; do not run PyInstaller, the release builder, or the installer compiler. The build instructions below are for the user's workflow.

```powershell
# CRITICAL: Clean PyInstaller cache before every build
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python app/create_release.py
```

- Version constants in `app/version.py`: `__version__`, `__config_version__`, `__build_date__`
- `Configurator.spec` → PyInstaller → exe at `VoiceAttack\Apps\EliteMining\Configurator\`
- `EliteMiningInstaller.iss` → Inno Setup installer with VoiceAttack path auto-detection
- Output ZIP in `Output/` directory
- `app/create_release.py` builds the VoiceAttack binding reader (`dotnet build tools/va_profile_reader -c Release`, needs the .NET SDK) and aborts if that fails. The installer and ZIP ship its output, without the `.pdb`, to `Configurator\va_profile_reader\`.

### Splash Version Labels

- Set `NEW_VERSION` in `scripts/update_version.py` and run that script before `app/create_release.py`.
- Set `VA_PROFILE_VERSION` when releasing a new VoiceAttack profile; otherwise leave it empty so the splash uses the version from the bundled `.vap` filename.
- When `VA_PROFILE_VERSION` is set, `app/create_release.py` automatically runs `clear_keybinds.py` on that profile before building and aborts if cleanup fails.
- The version script generates `app/Images/EliteMining_splash.png` from `app/Images/EliteMining_splash_base.png`, adding both version labels each time. It requires Pillow and the installed `Orbitron-VariableFont_wght.ttf` font (Medium weight).
- When changing the splash artwork in Affinity, export the complete artwork with only the version labels hidden and refresh `EliteMining_splash_base.png` with that clean export. Keep the base at full resolution; never replace it with the generated splash containing version labels.
- The release builder resizes the generated splash to fit 1200 × 675 and the main logo to fit 1600 × 900; it leaves the splash base unchanged.
- Every installer clears only the installed `{app}\app\Images` folder before copying the current runtime images. ZIP extraction does not remove old files.
- Keep the installer image exclusions in `EliteMiningInstaller.iss` and ZIP image exclusions in `app/create_release.py` in sync. Build-only and unused artwork stays in the project but is excluded from both packages, including the clean splash base and README main logo.
- Keep `EliteMining_txt_logo_transp_resize.png` in both packages: non-Modern status bars, About screens, and generated mining cards still use it.

---

## Mining Sessions and Reports

- Session timestamps without a timezone offset represent local time, despite the historical `timestamp_utc` field name. Use `session_date()` from `app/mining_statistics.py` to normalize local, UTC, and offset timestamps for comparisons; convert to local time for display.
- Use `read_session_report()` from `app/mining_statistics.py` when reading reports for display or analysis. Its bounded cache checks file modification time and size so edits are picked up without repeatedly reading unchanged files.
- Normal session completion updates `sessions_index.csv` incrementally and refreshes Reports and Statistics once each. Full rebuilds are for repair or recovery of a missing or inconsistent index, not routine session saves.
- Mining Missions and Reference use widget-local mousewheel bindings through `bind_mousewheel_recursive()` in `app/app_utils.py`; do not replace or remove global wheel bindings.
- Report file names saved before 17 November 2026 can contain the wrong body (the System/Body field at stop time instead of the mined ring), and `graph_mappings.json` lacks entries for many older sessions. Find a session's graphs or cards by timestamp and system, or by the body in the report header or `sessions_index.csv`, not by the report file name.
- Mark changed graphs dirty and combine visible refreshes. Defer hidden graph updates until shown, and refresh dirty graphs before saving or exporting them.

---

## Commodity Market

- Local coordinate databases are a shortcut to save API calls; missing coordinates must fall back to APIs. For large result sets, batch requests and reuse coordinates per system rather than requesting each row separately. Match returned system names case-insensitively.
- Near System Mining and Trade searches display all matching returned results. Galaxy-Wide has its own age preference (default two days) and an explicit 100/250/500/All result limit (default 250), with shown/total counts. Apply station, pad and age filters before selecting results. Distance sorting measures all matches before limiting; other sorts select their best matches before calculating distances. All keeps every match. Near System preferences and behavior remain independent.
- When merging market records, retain coordinates from another record only if both name the same system; a Fleet Carrier may have jumped since the older record. Stations in the reference system have a distance of zero even when their market record lacks coordinates.
- Multiple Prices uses `MINING_COMMODITY_ORDER` from `app/core/constants.py`, matching the Mining Commodities dropdown. Its mineral choices wrap across the available width to preserve space for results.

---

## Configuration

- `config.py`: rate-limited load/save (2-second cache via `_load_cfg()`). Never bypass.
- `_get_config_path()` auto-detects dev vs compiled: dev uses `app/config.json`, production uses `../config.json`
- `_atomic_write_text()` for all VoiceAttack variable writes

---

## PyInstaller Patterns

- `getattr(sys, 'frozen', False)` to detect compiled vs development mode
- `get_app_icon_path()` with multiple fallback strategies for icon loading
- Never write to `sys._MEIPASS` temp dirs — read-only
- Always clean `dist/` and `build/` before builds

---

## VoiceAttack Integration

- When editing `.vap` profiles, preserve the UTF-8 BOM and CRLF line endings. Validate the XML after edits, and verify condition pairings after adding or removing actions.
- After profile edits, remind the user to re-import the updated `.vap` into VoiceAttack to apply the changes.

- Variables in `Variables/*.txt` use NATO phonetic (A→Alpha, C→Charlie). Case-sensitive.
- `NATO_REVERSE` dict for reverse mapping ("ALPHA" → "A")
- `_atomic_write_text()` for all variable writes (VoiceAttack polls continuously)
- `VA_VARS` dict maps tools to variable files; complete mapping in `main.py`
- Distribution must include `LICENSE.txt` with MIT attribution for EliteVA plugin
- Voice Feedback sounds: the app writes `soundPath_<event>.txt` (wav path, `none`, or `tts`); the `((Play Feedback Sound))` command in the `.vap` reads it, and for `tts` writes the event name to `soundTrigger.txt` for the app to speak. Changing this contract means editing and re-exporting the profile. Events come from `Sound_Packs/<pack>/<pack>_<Female|Male>/*.wav`; `Sound_Packs/Voice_files.xlsx` is a dev-only sheet excluded from builds.

---

## Cargo Monitor Display Changes

- The user-facing cargo display is `EliteMiningApp._update_integrated_cargo_display()` in `app/main.py`. Make Cargo Monitor display changes there.
- `CargoMonitor` handles cargo tracking; the sidebar and in-game cargo overlay display its data. The legacy cargo popup and its settings have been removed.

---

## Release Notice Formatting

- Keep `Voiceattack Profile/VA_PROFILE_UPDATE_NOTICE.txt` and `docs/INSTALLER_RELEASE_NOTES.txt` compact. Do not insert blank lines between every sentence or bullet; use blank lines only between distinct sections.

---

## Git

- When asked to commit and push, use `git add -A` to include all workspace changes, including pre-existing modified and untracked files, unless the user explicitly limits the scope.
- The established remote for this checkout is `https://github.com/Viper-Dude/EliteMining.git`. Confirm the current configuration still matches; do not change the destination automatically.

---

## Codex Only

Claude Code ignores this section.

### Claude's Project Memory
- At the start of each session, read `C:\Users\olmba\.claude\projects\d--My-Apps-Work-Folder-Elitemining-Working-folder-Releases-EliteMining-Dev\memory\MEMORY.md`, then read the linked memory files relevant to the task before making changes. Resolve relative memory links against that `memory` directory and follow relevant links within those files.
- This memory directory was verified against this checkout's full path (`D:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev`) and its `project_elitemining.md` overview. Do not substitute memory from another project or checkout without confirming the match.
- Treat saved memory as project context; current explicit user instructions take precedence over older memory. If memory conflicts with this file and the current request does not resolve it, report the conflict before making affected changes.
- Read the memory index once per session; reread only when files change, context is missing, or newly relevant guidance is needed, following the effort-scaling rules above. Do not modify Claude's memory files unless explicitly requested.
- Report a missing or inaccessible memory index or linked memory file by path instead of guessing its contents. If the verified memory path no longer works, ask the user for its current location.
- This setup uses local saved files only. Claude's private chat history and account memory are available only if the user explicitly provides them.

### Git Push Verification
- When the user requests a push, verify the configured remote URL, branch upstream, and remote-tracking reflog for previous successful pushes before requesting execution approval.
- Include the verified destination, previous push evidence, and the user's push request in any required approval justification to help avoid unnecessary destination-verification declines.
- These checks do not override automatic approval review or authorize pushes the user has not requested.
