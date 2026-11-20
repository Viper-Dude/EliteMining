# EliteMining — Shared Project Instructions (Claude Code and Codex)

This is the single instruction file for both assistants. Codex loads it directly; Claude Code loads it through the `@AGENTS.md` import in [CLAUDE.md](CLAUDE.md). Keep all shared architecture, UI conventions and working rules here. Keep `CLAUDE.md` to that import line plus any Claude-only notes, and put Codex-only notes in the "Codex Only" section at the end. Do not copy these rules into saved memory.

Current explicit user instructions take precedence over saved rules. Treat saved memory as context; report unresolved conflicts before making affected changes.

**Linked guidance — read the matching file before working in that area:**
- [docs/FEATURE_RULES.md](docs/FEATURE_RULES.md) — Mining Sessions/Reports and Commodity Market behavior
- [docs/BUILD_RELEASE.md](docs/BUILD_RELEASE.md) — build, splash and packaging workflow (the user builds; agents don't)
- [docs/VOICEATTACK_UPDATE_HANDOFF.md](docs/VOICEATTACK_UPDATE_HANDOFF.md) — VoiceAttack profile update flow

## Chat Rules

- **Be concise.** Short, direct responses. No padding, no preamble, no trailing summaries of what you just did.
- **Code-first.** Proceed directly with straightforward work. Keep required progress updates brief and useful; avoid narrating routine tool calls.
- **No unsolicited refactoring.** Fix what was asked. Don't clean up surrounding code, rename variables, or restructure unless explicitly requested.
- **No feature creep.** Don't add error handling, validation, or abstractions for scenarios not in scope. Don't design for hypothetical future requirements. Don't add follow-on edits beyond the literal ask (extra tooltips, docs, help text), even when they seem natural; name a worthwhile follow-up briefly and ask first.
- **Flag rule conflicts first.** If a request breaks an established convention (master switches, shared settings, other tabs' behavior), state the conflict and a recommendation in one or two sentences before editing. When asked for an opinion, give a clear recommendation, not a survey.
- **Honest advice.** Don't offer a mitigation that doesn't reach the user's actual goal; say plainly when there is no real fix.
- **No comments unless the WHY is non-obvious.** Don't explain what the code does. Don't add task/PR references in comments.
- **No emojis** unless explicitly asked.
- **Follow existing patterns.** Match the style, naming conventions, and architecture already in the codebase. Check how similar things are done before inventing a new approach.
- **Reuse existing functions.** Before writing new logic, search the likely modules for an existing function that does it (or almost does it), including across tabs (e.g. distance/coordinate lookups in `ring_finder.py`). Reuse or minimally extend it instead of duplicating the implementation. Keep the search bounded to the requested behavior; widen it only when evidence points elsewhere. Text-only edits do not require a helper search.
- **Patch notes** (`docs/PATCHNOTES_v*.md`): one short, precise sentence per change, plain English from the player's view. No technical or dev language (no EDDN, API, cache, database, function names). Put new features and improvements under "New Features & Improvements" and fixes for broken behavior under "Bug Fixes" (both are in `docs/PATCHNOTES_TEMPLATE.md`).
- **When uncertain**, ask one targeted question if the uncertainty materially affects scope, correctness, or risk. Resolve routine implementation choices using existing patterns and session context.
- **Model advice before each new task.** Before starting a new task, recommend in one line which model and reasoning effort to use (from the options in the current tool), with a short reason, and say whether Plan mode would help. Match the Task Effort categories below: a lighter, faster model for small low-risk tasks; the strongest model with high effort for large or high-risk tasks (threading, database writes, VoiceAttack contracts, multiple components). If the current model and effort already fit, say so and continue. If a change would clearly help, stop and wait so the user can switch before implementation starts. Follow-ups within the same task don't need a new recommendation.
- **Don't re-explain decisions** already made in the conversation. Move forward.
- **End-of-chat review.** When the user says they are ending the chat, check whether any lasting decisions, preferences, lessons, or unresolved issues should be saved to project memory or documentation. Check existing guidance to avoid duplication. Update only files the user has authorized you to modify; otherwise briefly identify any recommended updates. Do not save routine chat history or make changes when nothing useful needs preserving.

---

## Task Effort and Validation

Scale inspection, planning, and validation to the change's complexity and consequences. Risk takes precedence over patch size; a small change to database writes, threading, shared configuration, or a VoiceAttack contract may need extensive validation.

- **Small, low-risk tasks** (wording, simple UI adjustments, minor configuration changes): inspect the relevant code, make the change, review the diff, and run a syntax or focused check. No elaborate plans or broad suites.
- **Medium tasks** (bug fixes, existing-feature changes): inspect affected code paths and direct dependencies, run the matching check scripts, and check likely regressions.
- **Large or high-risk tasks** (architecture, concurrency, database changes, multiple components): examine integration points and run comprehensive checks, including relevant failure or recovery paths.
- **Every check answers a question.** Add tests where they give real coverage, not ones that mirror the implementation. Don't run window-opening or broad checks unless the change touches that area; say why before running disruptive ones. Stop once the behavior is supported and applicable checks pass; report what was and wasn't verified.
- **User testing.** The user restarts `app/main.py` and tests manually after each change; don't duplicate that UI testing or assume it has passed. When they report a problem, assume a fresh restart and look for a code cause; don't ask whether they restarted. Give a short numbered test list (one action and expected result per step) only when the behavior isn't obvious.
- **Focused investigation.** Start with the reported symptom and the smallest useful inspection; for runtime-value bugs, prefer a targeted diagnostic and one reproduction. Read instruction files and the memory index once per session, batch independent reads and searches, and don't reread unchanged code.

### Running Checks

- Automated checks are `unittest` scripts in `scripts/check_<area>.py` (e.g. `check_settings.py`, `check_ring_finder_search.py`, `check_marketplace.py`). Run one with `app\.venv\Scripts\python.exe scripts\check_<area>.py`.
- Many check scripts create a Tk root; run only the scripts for the area you changed.
- Syntax check: `app\.venv\Scripts\python.exe -m py_compile <file>`.

### Editing Large Files

- `app/main.py` (~22k lines) and `app/ring_finder.py` (~12k lines) are too large to read whole. Search by function or class name and read only the relevant range.
- Most `app/` Python files (including `main.py`, `ring_finder.py` and `ui/`) and the `.vap` profiles use CRLF line endings; a few, such as `announcer.py`, use LF. Some blank lines have trailing spaces. Single-line edits are fine. For multi-line patch scripts, write the script to a temp file outside the repo, normalize `\r\n` to `\n` before matching, assert each match count is 1, restore CRLF on write, then `py_compile`.

---

## Project Overview

**EliteMining** is a Python/Tkinter desktop application for Elite Dangerous mining. Read the current version from `__version__` in `app/version.py`; do not duplicate the version number here.

**Two modes**: standalone and VoiceAttack-integrated.

**Key data sources**:
- Elite Dangerous journal files (`~/Saved Games/Frontier Developments/Elite Dangerous/`)
- EDDN (Elite Dangerous Data Network) live feed — commodity prices, powerplay, station metadata
- Spansh API — ring/system search, reserve levels
- Ardent API — commodity market data (`marketplace_api.py`)
- Inara — powerplay data (HTML scrape with bot-challenge solving)
- Local SQLite databases: `marketplace_cache.db` (EDDN cache), user database (`user_database.py`)

---

## Core Architecture

### Main Modules
- **`app/main.py`** — Multi-tabbed Tkinter app, CargoMonitor, dark theme, ToolTip system
- **`app/ring_finder.py`** — Ring Finder tab: Spansh/local search, results treeview, context menu, PP column
- **`app/system_finder_api.py`** — Spansh API wrapper + Inara powerplay HTML fetch
- **`app/marketplace_api.py`** — Commodity market lookups (Ardent and other sources)
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
- **Columns**: defined by the `columns` tuple in the results-table setup in `ring_finder.py` (search `columns = ("Distance"`). Hidden columns change display positions, so resolve columns by name with `displayed_column()`, never by fixed index.
- **PowerPlay column**: displays `"Power / State"` or `t('common.pp_no_data')` (`"No data  ↗"`)
- **Context menu**: single-select shows full menu; multi-select shows a separate `multi_menu` with limited options
- **Source column emojis**: `🌐` = Spansh, `🗄️` = Local DB, both = Both

### Powerplay Fetch (Inara)
`SystemFinderAPI.fetch_and_store_powerplay_from_inara(system_name)` in `system_finder_api.py`:
- Uses `requests.Session()` with browser User-Agent
- Detects Inara's bot challenge page (`validatechallenge.php`) and solves it automatically
- Stores result in `system_powerplay` table of `marketplace_cache.db`
- Returns `{'controlling_power': ..., 'power_state': ...}` or `None`

Batch fetch is sequential and rate-limited by the `PP_FETCH_MAX_BATCH` and `PP_FETCH_DELAY_SECS` class constants (defined in both `ring_finder.py` and `main.py`; keep them in step).

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

**Exception for dialogs with child popups** (autocomplete list, right-click menu, combobox dropdown, "please wait" `Toplevel`): the loop re-lifts the dialog above its own children and buries them. Either `lift()` once on open instead of looping, or skip `lift()` while any child is open (track an open flag, check `SystemAutocomplete._listbox_toplevel is None`, or `winfo_exists()` on the wait dialog). A non-modal popup without the loop still needs `-topmost` set once at open, because the main window can be always-on-top.

Use `centered_info_dialog` / `centered_yesno_dialog` from `ui/dialogs.py` for standard dialogs — they already implement all of the above.

---

## UI Conventions

- **Theme colours for new widgets**: Every new widget must use the active theme's colours, never default widget styling. Take colours from the same source as the neighbouring widgets (`load_theme()` / `get_theme_colors()`, or `ttk.Style().lookup(...)` of the parent's style) and set explicit `bg`/`fg`/`selectcolor`/`activebackground` on `tk` widgets such as checkbuttons. A default `ttk.Checkbutton` or similar looks wrong on the Modern and Elite Orange themes. Check new widgets visually in each theme.
- **Modern themes (`modern`, `modern_slate`, `modern_orange`)**: `_modern_recolor_all()` in `app/main.py` only remaps a fixed list of hardcoded greys, once per tab and once per popup, so widgets built or rebuilt later must take their colours from the theme when created. A `tk.Button` with `textvariable` or `image` bypasses `ModernButton` and is never recolored. Use `ttk.Scrollbar`, not `tk.Scrollbar`, in Modern. Gate Modern-only changes on all three theme names so Elite Orange and Dark Gray stay unchanged.
- **Feedback messages**: There is no global status bar. `EliteMiningApp._set_status()` only logs (`[Status]`). Show useful transient feedback (preset confirmations, scan progress, errors) in a label next to the relevant controls with `_show_notice(label, msg)`, using localized strings. Routine confirmations such as toggles stay log-only; real errors may use a popup. Journal scan progress uses `_set_journal_scan_status()` (footer row).
- **UI wording**: plain player language that says what the control or result does (e.g. "Best Minerals to Mine"). No jargon such as rank, query or scope, and no draft-looking slash labels like "Mine/Sell". For naming questions, give one recommendation with a short reason and its main downside.
- **Overlays**: "Enable Text Overlay" is the master switch for every overlay, including Auto Prices (off = Auto Prices uses the popup).
- **TextOverlay window** (`main.py`): it renders wrongly once its size differs from its creation size, so never call `geometry()` with a new size on a live overlay; `show_message()` rebuilds it through `reinstate()` and `_base_size` when the size must change. Keep withdraw/deiconify plus `-topmost` True and `lift()`; don't hide it with `-alpha 0` or toggle `-topmost`. Diagnose with the `[OVERLAY]` log lines before changing window code.

### Tables

Apply these rules whenever creating a table or changing an existing table's columns or layout:

- **Existing patterns**: inspect the closest table in the app first (especially Ring Finder and Commodity Market). Reuse existing helpers, theme styles, scaled fonts, and spacing; do not create a separate table framework.
- **Alignment**: left-align headers and cells by default (a Treeview can't pad cells, so right-aligned numbers touch the next column); center a column only where it looks clearly better. Centered today: the two Announcement material tables, and the Ring Finder Fav (star), Source and Visits columns.
- **Headers and minimum widths**: use short, localized headers consistent with matching columns in other tabs. Each column's minimum width is its translated header measured with the scaled heading font plus scaled padding. Default, restored, and shown-again widths must respect that minimum.
- **Manual resizing**: use `stretch=False` for data columns so Tk does not redistribute their widths. Do not impose a maximum width or reset the user's width during refresh or layout changes. If a table needs an expanding filler column, follow the existing Ring Finder pattern.
- **Scrolling**: provide working horizontal and vertical scrollbars so wide columns and rows beyond the visible height remain reachable.
- **Visibility and ordering**: reuse `ColumnVisibilityMixin` from `app/column_visibility_helper.py` where the table offers column controls. Use `use_displaycolumns=True` to fully hide columns (`width=0` leaves a visible text sliver), and resolve clicked or hovered columns with `displayed_column()` rather than fixed display indices. Reuse existing reorder support where applicable.
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

## Build & Packaging

- The user handles all installer and release-package builds. Agents limit their work to code changes and checks; do not run PyInstaller, `app/create_release.py`, or the installer compiler. The workflow is in [docs/BUILD_RELEASE.md](docs/BUILD_RELEASE.md).
- When changing which images ship, keep the installer image exclusions in `EliteMiningInstaller.iss` and the ZIP image exclusions in `app/create_release.py` in sync.
- Compiled vs dev: detect with `getattr(sys, 'frozen', False)`. Load icons through `get_app_icon_path()`. Never write to `sys._MEIPASS` (read-only).

---

## Configuration

- `config.py`: rate-limited load/save (2-second cache via `_load_cfg()`). Never bypass.
- `_get_config_path()` auto-detects dev vs compiled: dev uses `app/config.json`, production uses `../config.json`

---

## VoiceAttack Integration

- When editing `.vap` profiles, preserve the UTF-8 BOM and CRLF line endings. Validate the XML after edits, and verify condition pairings after adding or removing actions.
- After profile edits, remind the user to re-import the updated `.vap` into VoiceAttack to apply the changes.
- VoiceAttack silently ignores command elements that are out of its export order. Any code that adds elements to a `.vap` must insert them in `COMMAND_ELEMENT_ORDER` (`app/va_keybind_applier.py`), and checks must test the order, because reading the file back in Python does not reveal the problem.
- Renaming an existing player command in the profile requires an entry in `COMMAND_RENAMES` (`app/va_command_renames.py`), or players lose that command's shortcut on update.
- The profile update flow runs only in the installed app, not in `python app/main.py`; test it with a built installer and `va_profile_state.json` set to an older version. See [VOICEATTACK_UPDATE_HANDOFF.md](docs/VOICEATTACK_UPDATE_HANDOFF.md).
- Variables in `Variables/*.txt` use NATO phonetic (A→Alpha, C→Charlie). Case-sensitive. `NATO_REVERSE` maps back ("ALPHA" → "A").
- Use `_atomic_write_text()` for all variable writes (VoiceAttack polls continuously). `VA_VARS` in `main.py` maps tools to variable files.
- Distribution must include `LICENSE.txt` with MIT attribution for EliteVA plugin.
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

- Commit messages are concise and focus on the "why". No `Co-Authored-By` trailers and no Claude/Anthropic or Codex attribution in commits, PR descriptions, or committed content.
- When asked to commit and push, use `git add -A` to include all workspace changes, including pre-existing modified and untracked files, unless the user explicitly limits the scope.
- **Exception:** the user cleans and commits the shipped `Voiceattack Profile/*.vap` files (including test copies such as `backup_clean.vap`) and `docs/INSTALLER_RELEASE_NOTES.txt` themselves. Leave them out of your commits with `git add -A -- . ":(exclude)Voiceattack Profile/*.vap" ":(exclude)docs/INSTALLER_RELEASE_NOTES.txt"`, and don't offer to clean or commit them. Before a release, at most mention once if the shipped profile still has shortcuts.
- The established remote for this checkout is `https://github.com/Viper-Dude/EliteMining.git`. Confirm the current configuration still matches; do not change the destination automatically.

---

## Codex Only

Claude Code ignores this section.

- **Claude's project memory**: at session start, read `C:\Users\olmba\.claude\projects\d--My-Apps-Work-Folder-Elitemining-Working-folder-Releases-EliteMining-Dev\memory\MEMORY.md` (verified for this checkout) and the linked files relevant to the task, resolving links against that `memory` directory. Treat it as context, not rules; don't modify it unless asked. If the path stops working, report it and ask the user for the new location.
- **Fresh sessions**: at a task boundary, when the user moves to an unrelated task or starts a new release, add one line saying it's a good point to start a new session (`/new`), since usage limits are shared. Don't suggest it for follow-ups on the same task.
- **Push verification**: when the user requests a push, verify the remote URL, branch upstream, and remote-tracking reflog for previous pushes, and include that evidence plus the user's request in any approval justification. This does not authorize pushes the user has not requested.
