# EliteMining — Shared Architecture and Project Rules

This file carries forward the shared rules from the project's original CLAUDE.md, with the additional shared rules from AGENTS.md. It is the single source of shared project rules for Claude and Codex. Read it before making changes, along with applicable ancestor and nested instruction files and task-relevant documents referenced here.

Keep shared architecture, UI conventions, and working rules here. Keep assistant-specific setup in [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md); do not duplicate shared rules in those files or saved memory. Current explicit user instructions take precedence over saved rules. Treat saved memory as context; report unresolved conflicts before making affected changes.

## Chat Rules

- **Be concise.** Short, direct responses. No padding, no preamble, no trailing summaries of what you just did.
- **Code-first.** Show code changes directly. Don't narrate what you're about to do — just do it.
- **No unsolicited refactoring.** Fix what was asked. Don't clean up surrounding code, rename variables, or restructure unless explicitly requested.
- **No feature creep.** Don't add error handling, validation, or abstractions for scenarios not in scope. Don't design for hypothetical future requirements.
- **No comments unless the WHY is non-obvious.** Don't explain what the code does. Don't add task/PR references in comments.
- **No emojis** unless explicitly asked.
- **Follow existing patterns.** Match the style, naming conventions, and architecture already in the codebase. Check how similar things are done before inventing a new approach.
- **Reuse existing functions.** Before writing new logic, check if an existing function already does it (or almost does it). Call it, or extract a shared helper/add a parameter — don't copy-paste and duplicate the implementation. This applies across tabs and modules, not just within one file (e.g. distance/coordinate lookups already exist in `ring_finder.py`).
- **Patch notes** (`docs/PATCHNOTES_v*.md`): one short, precise sentence per change, plain English from the player's view. No technical or dev language (no EDDN, API, cache, database, function names).
- **Git commits**: No `Co-Authored-By` trailers. Commit messages should be concise and focus on the "why".
- **When uncertain**, ask one targeted question rather than listing options or making assumptions.
- **Don't re-explain decisions** already made in the conversation. Move forward.

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

Before marking table work complete, verify:

1. Drag columns wider and narrower: widths remain stable after release, result refresh, and window resizing; headers remain readable at the minimum width.
2. Scroll horizontally through wide columns and vertically through all rows.
3. Save and reopen the table: widths, visibility, and supported ordering restore correctly.
4. Hide, show, and reorder columns where supported: no text slivers, incorrect context menus, or mismatched tooltips.
5. Check English and German headers, supported UI scales, and number formatting, including fractional LS, zero, and missing data.

Report any checks that could not be run; do not claim visual verification from code inspection alone.

---

## Logs

- **Installed build**: `%LOCALAPPDATA%\EliteMining\logs\elitemining_<timestamp>.log` (one file per session, from `logging_setup.py`).
- **Dev run** (`python app/main.py`): `~\EliteMining.log` (rotates at 512KB to `.log.1`, so search `.log.1` too).
- Only INFO and above is written; overlay diagnostics are tagged `[OVERLAY]`.

---

## Build & Release

```powershell
# CRITICAL: Clean PyInstaller cache before every build
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python app/create_release.py
```

- Version constants in `app/version.py`: `__version__`, `__config_version__`, `__build_date__`
- `Configurator.spec` → PyInstaller → exe at `VoiceAttack\Apps\EliteMining\Configurator\`
- `EliteMiningInstaller.iss` → Inno Setup installer with VoiceAttack path auto-detection
- Output ZIP in `Output/` directory

### Splash Version Labels

- Set `NEW_VERSION` in `scripts/update_version.py` and run that script before `app/create_release.py`.
- Set `VA_PROFILE_VERSION` when releasing a new VoiceAttack profile; otherwise leave it empty so the splash uses the version from the bundled `.vap` filename.
- The version script generates `app/Images/EliteMining_splash.png` from `app/Images/EliteMining_splash_base.png`, adding both version labels each time. It requires Pillow and the installed `Orbitron-VariableFont_wght.ttf` font (Medium weight).
- When changing the splash artwork in Affinity, export the complete artwork with only the version labels hidden and refresh `EliteMining_splash_base.png` with that clean export. Keep the base at full resolution; never replace it with the generated splash containing version labels.
- The release builder resizes the generated splash to fit 1200 × 675 and the main logo to fit 1600 × 900; it leaves the splash base unchanged.

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
- The legacy popup (`CargoMonitor.update_display()`) is not exposed to users in the shipped app. Do not propagate display changes to it unless the user explicitly asks.
- `docs/CARGO_MONITOR_REFERENCE.md` and the cargo warning document contain outdated instructions to always update both displays. Follow this section for the scope of display changes.

