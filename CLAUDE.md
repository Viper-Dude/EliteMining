# EliteMining — Claude Code Instructions

## Chat Rules

- **Be concise.** Short, direct responses. No padding, no preamble, no trailing summaries of what you just did.
- **Code-first.** Show code changes directly. Don't narrate what you're about to do — just do it.
- **No unsolicited refactoring.** Fix what was asked. Don't clean up surrounding code, rename variables, or restructure unless explicitly requested.
- **No feature creep.** Don't add error handling, validation, or abstractions for scenarios not in scope. Don't design for hypothetical future requirements.
- **No comments unless the WHY is non-obvious.** Don't explain what the code does. Don't add task/PR references in comments.
- **No emojis** unless explicitly asked.
- **Follow existing patterns.** Match the style, naming conventions, and architecture already in the codebase. Check how similar things are done before inventing a new approach.
- **Git commits**: No `Co-Authored-By` trailers. Commit messages should be concise and focus on the "why".
- **When uncertain**, ask one targeted question rather than listing options or making assumptions.
- **Don't re-explain decisions** already made in the conversation. Move forward.

---

## Project Overview

**EliteMining** is a Python/Tkinter desktop application for Elite Dangerous mining. Current version: **5.1.9** (`app/version.py`).

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

- Variables in `Variables/*.txt` use NATO phonetic (A→Alpha, C→Charlie). Case-sensitive.
- `NATO_REVERSE` dict for reverse mapping ("ALPHA" → "A")
- `_atomic_write_text()` for all variable writes (VoiceAttack polls continuously)
- `VA_VARS` dict maps tools to variable files; complete mapping in `main.py`
- Distribution must include `LICENSE.txt` with MIT attribution for EliteVA plugin

---

## Critical: Two Cargo Displays

See `docs/CARGO_MONITOR_REFERENCE.md`. **Always update both** when changing cargo display:

1. **Integrated display** (primary, always visible) — `_update_integrated_cargo_display()` ~line 3570 in `main.py`
2. **Popup window** (secondary, manually opened) — `update_display()` ~line 1850 in `main.py`
