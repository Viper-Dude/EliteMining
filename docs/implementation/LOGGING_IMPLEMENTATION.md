# Logging System Implementation

## Overview
Per-session logging system for the EliteMining installer version to capture debug messages for troubleshooting.

## Files Added/Modified

### New Files
- **`app/logging_setup.py`** - Core logging module
  - Creates timestamped log files per session
  - Auto-cleanup (keeps last 15 sessions)
  - Only activates for packaged executables (`sys.frozen`)
  - Silences noisy third-party loggers (matplotlib, PIL, urllib3)

### Modified Files
- **`app/main.py`** - Added logging initialization at startup
- **`app/user_database.py`** - Added logging for database operations
- **`Configurator.spec`** - Added new modules to hiddenimports

## Log Configuration

### Location
- **Windows**: `%LOCALAPPDATA%\EliteMining\logs\`
- **Other**: `~/.elitemining/logs/`

### File Naming
Format: `elitemining_YYYY-MM-DD_HH-MM-SS.log`

Examples:
- `elitemining_2025-10-03_14-30-15.log`
- `elitemining_2025-10-03_09-15-42.log`

### Rotation Policy
- **Max size per log**: 2 MB
- **Keep last**: 15 sessions (~30 MB total)
- **Auto-cleanup**: On app startup

## Logged Events

### Mining Sessions
```
[SESSION] Started mining session - Cargo: 0/512t, Prospectors: 50
[SESSION] Ended mining session - Duration: 45.3min, Mined: 487.5t, Prospectors used: 42, Materials: 3
```

### Journal Scanning
```
[JOURNAL] Auto-scan disabled by user preference
[JOURNAL] Starting auto-scan on startup...
[JOURNAL] Auto-scanning journals for new entries...
[JOURNAL] Scanning: Journal.2025-10-03T14.log (1/3)
[JOURNAL] ✓ Auto-scan complete: 3 file(s), 247 event(s) processed
[JOURNAL] ERROR during auto-scan: [error details]
```

### Database Operations
```
[DATABASE] Added hotspot: Sol - Jupiter A Ring - Platinum x3
[DATABASE] New system visited: Deciat
```

### Interface Operations
```
[INTERFACE] TTS engine reinitialized successfully
[INTERFACE] Failed to reinitialize TTS engine
```

## Building the Installer

### Prerequisites
- Python 3.x with PyInstaller installed
- All dependencies in requirements.txt

### Build Command
```batch
build_eliteMining_with_icon.bat
```

Or manually:
```batch
python -m PyInstaller --clean Configurator.spec
```

### Output
- Executable: `dist/Configurator.exe`
- Includes: All Python modules + logging_setup.py

## Testing Logging

### Development Mode
Logging is **disabled** when running from source (`python app/main.py`) to avoid cluttering development environment.

Test: Run `python app/main.py` - no log files will be created ✅

### Installer Mode
Logging is **enabled** automatically when running the packaged executable.

Test: Run `dist/Configurator.exe` - logs will be created in `%LOCALAPPDATA%\EliteMining\logs\` ✅

### Manual Testing in Development
To test logging without building the installer, temporarily modify `app/main.py`:
```python
# Change this line:
log_file = setup_logging()

# To this:
log_file = setup_logging(force_enable=True)  # Test mode
```

**Remember to change it back before committing!**

## Troubleshooting

### Logs not being created?
1. Check if running packaged executable (not from source)
2. Verify `%LOCALAPPDATA%\EliteMining\logs\` directory exists
3. Check file permissions

### Log file too large?
- Increase max size in `logging_setup.py` (default 2MB)
- Decrease sessions kept (default 15)

### Missing log messages?
- Check if logging level is appropriate (default DEBUG)
- Verify print statements use proper format tags: `[SESSION]`, `[JOURNAL]`, etc.

## Future Enhancements
- [ ] Add log viewer in UI
- [ ] Compress old logs (.gz)
- [ ] Email/upload logs for support
- [ ] Log rotation by time (daily)
- [ ] User-configurable log levels
