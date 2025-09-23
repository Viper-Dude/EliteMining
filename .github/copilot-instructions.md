# EliteMining AI Coding Agent Instructions

## Project Overview
EliteMining is a comprehensive Python/Tkinter application for Elite Dangerous mining automation and analytics, supporting both standalone and VoiceAttack-integrated modes. The codebase features robust configuration with rate limiting, advanced cargo monitoring with ship change detection, session tracking, and TTS announcements, with a focus on reliability and seamless Elite Dangerous integration.

**Core Architecture**: Multi-threaded Tkinter GUI with background Elite Dangerous journal monitoring, cargo tracking via multiple JSON sources (Journal, Cargo.json, Status.json), Windows SAPI TTS integration, and bidirectional VoiceAttack communication through NATO phonetic alphabet text files.

**Version**: 4.0.5 (see `app/version.py` for current version constants and config schema versioning)

## Key Components & Data Flows

### Core Application Architecture
- **Main GUI (`main.py`)**: Multi-tabbed Tkinter application with sophisticated **ToolTip system** (global enable/disable, positioning logic for edge cases), **CargoMonitor class** for real-time multi-source cargo tracking with background monitoring threads, and **dark theme styling** via ttk.Style configuration.
- **Session Management (`prospector_panel.py`)**: Elite Dangerous journal file monitoring with **startup skip logic** to prevent processing old events, deduplication via event tracking, and integration with `mining_statistics.py` for analytics.
- **TTS System (`announcer.py`)**: Windows SAPI integration with voice fallback logic, **diagnostic capabilities** for voice recycling issues, and cleanup of debug messages for production.
- **Version Management (`version.py`)**: Application versioning with separate config schema version tracking for backward compatibility (`__version__`, `__config_version__`, `__build_date__`).

### Configuration & State Management
- **Configuration (`config.py`, `config.json`)**: **Rate-limited config loading** (2-second cache) via `_load_cfg()`/`_save_cfg()`, **context-aware path detection** using `_get_config_path()` for development vs. compiled executable environments, and atomic file operations via `_atomic_write_text()`.
- **Ship Presets**: JSON-based ship configurations in `Settings/*.json` containing firegroups, timers, toggles with automatic binding to UI StringVar/IntVar for persistence.

### Elite Dangerous Integration
- **Multi-Source Cargo Monitoring**: CargoMonitor class tracks cargo via **Journal events, Cargo.json, and Status.json** with `refresh_ship_capacity()` for automatic ship change detection and **background monitoring threads** (`_start_background_monitoring()`) that work without UI windows.
- **Journal Processing**: Prospector event parsing with **material classification** (RARE_MATERIALS, COMMON_MATERIALS), announcement filtering, and session lifecycle management.
- **Real-Time Data Paths**: `~\Saved Games\Frontier Developments\Elite Dangerous\` contains Journal*.log, Cargo.json, Status.json files monitored continuously for game state changes.

### VoiceAttack Communication
- **NATO Phonetic Variables**: Firegroup mappings use NATO alphabet in `Variables/*.txt` files (A→"Alpha", C→"Charlie") with `NATO_REVERSE` dict for bidirectional conversion.
- **EliteVA Plugin**: Full Elite Dangerous API integration via `app/EliteVA/` with proper MIT license attribution and keybinding files.
- **Variable Structure**: `VA_VARS` dict maps tools to variable files: `{"Mining lasers": {"fg": "fgLasers", "btn": "btnLasers"}}` with atomic writes to prevent VoiceAttack reading partial files.

## Essential Files & Directories
- `app/main.py` (CargoMonitor class), `app/prospector_panel.py`, `app/announcer.py`, `app/mining_statistics.py`, `app/config.py`
- `config.json` (window geometry, TTS, announce map), `app/Settings/*.json` (ship presets)
- `Variables/*.txt` (VoiceAttack variables, NATO format)
- `app/EliteVA/` (EliteVA plugin with MIT license), `LICENSE.txt` (EliteVA licensing)
- `Configurator.spec`, `create_release.py`, `EliteMiningInstaller.iss`, `build_eliteMining_with_icon.bat`
- `app/Images/`, `app/Reports/`, `app/Output/`

## Development Patterns & Conventions

### Configuration Management Patterns
- **Rate-Limited Loading**: Always use `_load_cfg()`/`_save_cfg()` with 2-second cache to prevent config spam (20+ loads prevented per operation). Never bypass this system.
- **Context-Aware Paths**: Use `_get_config_path()` for automatic dev vs. compiled path detection. Development mode uses `app/config.json`, compiled uses parent `EliteMining/config.json`.
- **Atomic File Operations**: Use `_atomic_write_text()` for all VoiceAttack variable writes to prevent partial file reads during VA polling cycles.

### UI Architecture Patterns  
- **ToolTip System**: Use `ToolTip` class for all help text with global enable/disable via `ToolTip.tooltips_enabled`. Includes **smart positioning logic** for bottom-area widgets (Import/Apply buttons) to avoid screen edge clipping.
- **Data Binding**: All UI uses `StringVar`/`IntVar` with automatic persistence via config system. Scrollable frames (`ttk.Scrollbar`) required for all tabs to handle content overflow.
- **Dark Theme**: Consistent styling via `ttk.Style` configuration in main.py initialization with custom button/label colors.

### Background Processing Patterns
- **Multi-Threading**: CargoMonitor and ProspectorPanel use background threads with **silent failure** philosophy - extensive logging but no user-visible errors to avoid interrupting gameplay.
- **Ship Change Detection**: `refresh_ship_capacity()` monitors Status.json changes and automatically updates cargo capacity when ship swaps occur (handles ShipyardSwap, StoredShips events).
- **Journal Processing**: Startup skip logic prevents processing historical events, deduplication via event ID tracking prevents announcement spam.
- **Continuous Monitoring**: `_start_background_monitoring()` creates daemon threads that monitor Elite Dangerous files every 0.5 seconds, independent of UI window state.

### VoiceAttack Integration Patterns
- **NATO Alphabet Mapping**: All firegroup variables use NATO phonetic (`FIREGROUPS` → `NATO` → files). Use `NATO_REVERSE` for conversion back to letters. Example: "C" → "Charlie" in `fgLasers.txt`.
- **Variable File Structure**: Follow `VA_VARS` pattern: tool name → {fg: "fgLasers", btn: "btnLasers"} with corresponding `Variables/*.txt` files. Complete mapping in `main.py` lines 366-374.
- **EliteVA Plugin**: Always include `app/EliteVA/` directory with MIT license attribution in `LICENSE.txt` for distribution compliance.
- **Atomic File Writes**: Use `_atomic_write_text()` function for all VoiceAttack variable writes to prevent partial file reads during VA polling cycles.

### PyInstaller Compatibility Patterns
- **Execution Context**: Use `getattr(sys, 'frozen', False)` to detect compiled vs. development mode for resource path resolution.
- **Icon Path Detection**: Use `get_app_icon_path()` pattern with multiple search strategies (MEI temp, script dir, CWD, exe dir) for robust icon loading.
- **Build Environment**: Always clean `dist/` and `build/` directories before PyInstaller runs to prevent caching issues.

## Build & Release Workflow

### Automated Build Process
```powershell
# CRITICAL: Clean PyInstaller cache to prevent stale builds
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python app/create_release.py
```

**Build Pipeline**: 
1. `app/create_release.py` (ReleaseBuilder class) automates entire build process with step-by-step output
2. Executes `build_eliteMining_with_icon.bat` → `Configurator.spec` → PyInstaller with automatic pause bypass
3. Version control via `app/version.py` constants (`__version__`, `__config_version__`, `__build_date__`)
4. Creates ZIP archive with EliteVA integration in `Output/` directory
5. Inno Setup (`EliteMiningInstaller.iss`) → Windows installer with VoiceAttack path auto-detection
6. **Final Structure**: Executable at `VoiceAttack\Apps\EliteMining\Configurator\`, config at `VoiceAttack\Apps\EliteMining\`

**ReleaseBuilder Features**:
- Automated command execution with proper error handling and output capture
- Step-by-step progress reporting for build transparency
- Batch file automation (handles pause statements automatically)
- Cross-platform path handling for different development environments

### Build Configuration Details
- **Configurator.spec**: Uses `logo_multi.ico`, excludes console window, includes UPX compression
- **EliteMiningInstaller.iss**: Auto-detects VoiceAttack paths (Steam, Program Files), handles EliteVA plugin licensing
- **Path Logic**: Installer creates parent/child directory structure to separate executable from config/data files

## VoiceAttack Variable Integration
- Variables in `Variables/*.txt` use NATO phonetic (A→Alpha, etc). **Case-sensitive**: must be exact NATO words ("Charlie", not "charlie").
- Button mappings: "primary"/"secondary" or numeric in `btn*.txt`.
- Use `NATO_REVERSE` for reverse mapping ("ALPHA" → "A").
- TTS announcements use `VA_TTS_ANNOUNCEMENT = "ttsProspectorAnnouncement"` constant from `config.py`.
- Complete tool mapping in `VA_VARS` dict: Mining lasers, Discovery scanner, Prospector limpet, Pulse wave analyser, Seismic charge launcher, Weapons, Sub-surface displacement missile.

## Critical Architecture Decisions & Common Gotchas

### Performance & Reliability Fixes
- **Config Loading Spam**: Rate limiting in `_load_cfg()` prevents 20+ loads per operation (2-second cache). **Never bypass this system**.
- **Path Inconsistencies**: `_get_config_path()` handles dev vs. compiled context automatically. Development uses `app/config.json`, production uses `../config.json`.
- **Ship Change Detection**: CargoMonitor uses Status.json polling to detect ship swaps and calls `refresh_ship_capacity()` automatically.
- **Journal Processing Loop Prevention**: ProspectorPanel implements startup skip logic and event deduplication to prevent processing old events or announcement spam.

### PyInstaller-Specific Issues
- **Build Caching**: Always delete `dist/` and `build/` directories before builds. PyInstaller caching can cause mysterious failures with stale dependencies.
- **Multiple Processes**: Compiled app shows multiple processes in Task Manager - this is normal PyInstaller behavior, not a bug.
- **Icon Loading**: Use `get_app_icon_path()` with multiple fallback strategies since resource paths differ between dev and compiled modes.
- **MEI Temp Directory**: PyInstaller uses `sys._MEIPASS` for temporary file extraction - handle both this and normal file paths.

### VoiceAttack Integration Gotchas  
- **NATO Phonetic Format**: Variable files must contain exact NATO words ("Charlie", not "charlie" or "CHARLIE"). Case matters for VoiceAttack parsing.
- **File Timing**: Use `_atomic_write_text()` to prevent VoiceAttack reading partial files during rapid updates. VoiceAttack polls these files continuously.
- **EliteVA Licensing**: Distribution **must include** `LICENSE.txt` with MIT license attribution for EliteVA plugin legal compliance.

### TTS System Issues
- **Voice Recycling**: Windows SAPI occasionally "loses" voices. Provide "Fix TTS" button that reinitializes the TTS engine via `_initialize_tts()`.
- **Voice Fallback**: Always implement graceful fallback when saved voice unavailable (voice uninstalled, system change).
- **Debug Message Cleanup**: Remove excessive debug logging in production TTS to avoid log spam during mining sessions.

## Implementation Examples

### Adding New Ship Presets
```json
// app/Settings/MyShip.json
{
  "ship_name": "My Mining Ship",
  "firegroups": {"A": "Discovery scanner", "B": "Pulse wave analyser", "C": "Mining lasers"},
  "timers": {"boost_interval": 30, "cargo_scoop_delay": 2},
  "toggles": {"mining": true, "prospector": true}
}
```
Ship presets auto-populate UI dropdowns and sync with VoiceAttack variables via NATO phonetic conversion.

### Adding New Material Types
1. **Update Material Lists** in `prospector_panel.py`:
```python
RARE_MATERIALS = ["Alexandrite", "Benitoite", "NewRareMaterial"]
COMMON_MATERIALS = ["Bauxite", "Bertrandite", "NewCommonMaterial"] 
```

2. **Update Announcement Logic** in `ProspectorPanel._summaries_from_event()`:
```python
# Add filtering logic for new material categories
if material_name in NEW_MATERIAL_CATEGORY:
    category = "new_category"
```

3. **Update Config Schema** in `config.json`:
```json
"announce_map": {"NewRareMaterial": true, "NewCommonMaterial": false}
"min_pct_map": {"NewRareMaterial": 15.0}
```

### VoiceAttack Variable Integration
```python
# Adding new firegroup mapping
VA_VARS = {
    "New Mining Tool": {"fg": "fgNewTool", "btn": "btnNewTool"},
    # Creates Variables/fgNewTool.txt and Variables/btnNewTool.txt
}

# NATO conversion example
firegroup_letter = "D"  # Delta
nato_word = NATO[firegroup_letter]  # "Delta" 
_atomic_write_text("Variables/fgNewTool.txt", nato_word)
```

### UI Consistency
- Use ToolTip class for all help text (respects global enable/disable toggle)
- Dark theme styling via ttk.Style configuration in main.py
- StringVar/IntVar for data binding with automatic persistence
- Consistent error handling via messagebox with descriptive context
- All tabs use scrollable frames for content overflow handling

### Error Handling
- Silent failures in background threads (cargo monitoring, journal watching)
- Extensive logging for debugging journal processing and TTS issues
- Graceful TTS voice fallback when saved voice unavailable
- TTS reinitialization available via "Fix TTS" button for voice recycling issues

### PyInstaller Compatibility Patterns
- Use `getattr(sys, 'frozen', False)` to detect compiled vs development mode
- File paths must be absolute and context-aware: `config.py` uses `_get_config_path()`
- Development mode: config in project root (parent of app folder)
- Production mode: installer places executable at `VoiceAttack\Apps\EliteMining\Configurator\` but config at `VoiceAttack\Apps\EliteMining\`
- Always test both VS Code and installer versions for path-dependent features
- Installer structure: executable in Configurator subfolder, config in parent EliteMining folder

## Essential Files

**Configuration**: `config.json` (window geometry, TTS settings), `Settings/*.json` (ship presets)
**Reports**: `Reports/Mining Session/sessions_index.csv`, individual session text files
**VoiceAttack**: `Variables/*.txt` files (firegroups, timers, toggles as NATO alphabet)
**Build**: `Configurator.spec` (PyInstaller), `create_release.py`, parent directory bat/iss files

## Development Workflows

### Clean Release Build
```powershell
# Clean previous builds - CRITICAL for PyInstaller
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python app/create_release.py
```

### VoiceAttack Variable Integration
- Variables written as NATO phonetic: `fgLasers.txt` contains "Charlie" for firegroup C
- Button mappings: "primary"/"secondary" or numeric values in `btn*.txt` files
- Use `_import_all_from_txt()` and `_export_all_to_txt()` for synchronization
- `NATO_REVERSE` dict converts "ALPHA" → "A" for reverse mapping

### Adding Material Tracking
1. Update material lists in `prospector_panel.py` (RARE_MATERIALS, COMMON_MATERIALS)
2. Modify announcement filtering in `ProspectorPanel._summaries_from_event()`
3. Enhance `mining_statistics.py` MaterialStatistics class if needed
4. Update `config.json` announce_map and min_pct_map for new materials

### Testing Elite Dangerous Integration
- Use test journal files in default Elite Dangerous folder: `~\Saved Games\Frontier Developments\Elite Dangerous\`
- Test cargo monitoring with Cargo.json and Status.json files for ship change scenarios
- ProspectorPanel startup skip prevents processing old events
- CargoMonitor background monitoring works without UI windows
- TTS announcements can be tested via Interface Options tab test buttons
- Validate both VS Code development and compiled executable versions for path consistency

### Recent Architecture Updates (v4.0.5)
- **Config System**: Added rate limiting to prevent spam (2-second cache in `_load_cfg()`), fixed path detection for dev/compiled consistency via `_get_config_path()`
- **Cargo Monitor**: Enhanced with ship change detection, Status.json integration, background monitoring threads that work without UI windows
- **Build Process**: EliteVA integration with proper MIT licensing, streamlined release automation via `create_release.py` ReleaseBuilder class
- **Version Management**: Separated application version from config schema version in `version.py` for backward compatibility
- **Background Processing**: CargoMonitor now runs continuous monitoring threads (`_start_background_monitoring()`) independent of cargo window state
- **Update System**: Added update checking infrastructure with configurable intervals and GitHub API integration for release detection
