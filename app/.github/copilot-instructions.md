# EliteMining Development Guide

## Architecture Overview

EliteMining is a sophisticated mining assistant for Elite Dangerous with dual operational modes:
- **Standalone Mode**: Manual mining with real-time analytics, announcements, and session tracking
- **VoiceAttack Integration**: Full voice/hotkey automation with mining sequences

### Core Components

**Main Application** (`main.py`): 
- Tkinter GUI with tabbed interface (Dashboard with Firegroups/Timers tabs, Interface Options, Mining Session)
- Configuration management via JSON files (`config.json`) and VoiceAttack variable files (`Variables/*.txt`)
- Dark theme with custom styling and global ToolTip system (`ToolTip.set_enabled()`)
- Window state persistence and CargoMonitor background thread for real-time cargo tracking

**Mining Session Management** (`prospector_panel.py`):
- Real-time Elite Dangerous journal monitoring with startup skip mechanism
- ProspectorPanel class handles session lifecycle (start/pause/stop) with cargo snapshots
- Material analysis using SessionAnalytics from `mining_statistics.py`
- Report generation with TPH calculations, material breakdowns, and CSV indexing
- Announcement filtering based on thresholds (Core vs Non-Core asteroids)

**Text-to-Speech System** (`announcer.py`):
- Windows SAPI integration with voice selection and volume control
- Diagnostic capabilities for TTS troubleshooting (`diagnose_tts()`)
- Settings persistence with graceful fallback to available voices

## Build & Release System

**Automated Release Process** (`create_release.py`):
- Pipeline: PyInstaller → ZIP packaging → Inno Setup installer
- Expects `build_eliteMining_with_icon.bat` and `EliteMiningInstaller.iss` in parent directory
- Builds from `Configurator.spec` → `dist/Configurator.exe` → `Output/EliteMining_{version}.zip` + installer
- **Critical**: Delete `dist/` and `build/` folders to force clean PyInstaller rebuild

**PyInstaller Configuration** (`Configurator.spec`):
- Multi-module analysis with hidden imports for matplotlib, numpy, PIL
- Includes data folders: `Images/`, `Settings/`, `Reports/`, `Variables/`
- One-file executable with UPX compression and icon embedding

## Key Data Flows

1. **Journal Monitoring**: Elite Dangerous writes events → CargoMonitor/ProspectorPanel read → UI updates
2. **Session Tracking**: Start session → capture cargo snapshot → monitor ProspectedAsteroid events → calculate material differences on stop
3. **VoiceAttack Integration**: Settings written to `Variables/*.txt` as NATO phonetic alphabet (A→Alpha, B→Bravo)
4. **Report Generation**: Session data + material analysis → formatted text reports + CSV index → Reports window display

## Development Patterns

### Configuration Management
- All settings use `_load_cfg()` and `_save_cfg()` from `config.py`
- VoiceAttack variables written as NATO phonetic alphabet to `Variables/*.txt`
- Atomic file writes with `_atomic_write_text()` prevent VoiceAttack reading partial files
- Ship presets stored in `Settings/*.json` with firegroups, timers, toggles

### UI Consistency
- Use ToolTip class for all help text (respects global enable/disable toggle)
- Dark theme styling via ttk.Style configuration in main.py
- StringVar/IntVar for data binding with automatic persistence
- Consistent error handling via messagebox with descriptive context

### Error Handling
- Silent failures in background threads (cargo monitoring, journal watching)
- Extensive logging for debugging journal processing and TTS issues
- Graceful TTS voice fallback when saved voice unavailable

## Essential Files

**Configuration**: `config.json` (window geometry, TTS settings), `Settings/*.json` (ship presets)
**Reports**: `Reports/Mining Session/sessions_index.csv`, individual session text files
**VoiceAttack**: `Variables/*.txt` files (firegroups, timers, toggles as NATO alphabet)
**Build**: `Configurator.spec` (PyInstaller), `create_release.py`, parent directory bat/iss files

## Development Workflows

### Clean Release Build
```powershell
# Clean previous builds
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
python create_release.py
```

### Adding Material Tracking
1. Update material lists in `prospector_panel.py` (RARE_MATERIALS, COMMON_MATERIALS)
2. Modify announcement filtering in `ProspectorPanel._summaries_from_event()`
3. Enhance `mining_statistics.py` MaterialStatistics class if needed

### Testing Elite Dangerous Integration
- Use test journal files in default Elite Dangerous folder
- ProspectorPanel startup skip prevents processing old events
- CargoMonitor can be tested independently with background monitoring

## Common Gotchas

- **Build Cache**: PyInstaller reuses cached builds - delete `dist/` and `build/` folders if executable contains old code
- Journal monitoring uses file position tracking - resets can cause duplicate processing
- VoiceAttack variable names are case-sensitive and use specific formats
- Text overlay transparency affects visibility - coordinate with dark themes
- ProspectorPanel initialization depends on main app components being ready
- Session analytics require material selection from announcement panel settings
