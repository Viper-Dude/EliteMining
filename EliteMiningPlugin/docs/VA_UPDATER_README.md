# VoiceAttack Profile Auto-Updater

Automatic VoiceAttack profile updater that preserves user keybinds during updates.

## What It Does

✅ **Detects** new profile versions  
✅ **Backs up** current profile automatically  
✅ **Extracts** all user keybinds (keyboard, joystick, mouse)  
✅ **Closes** VoiceAttack gracefully  
✅ **Installs** new profile  
✅ **Restores** all keybinds to new profile  
✅ **Restarts** VoiceAttack  
✅ **Rolls back** automatically if anything fails  

## Components

### Core Modules

| Module | Purpose |
|--------|---------|
| `va_profile_updater.py` | Main orchestrator |
| `va_profile_parser.py` | Parse .VAP XML files |
| `va_keybind_extractor.py` | Extract keybinds from profile |
| `va_keybind_applier.py` | Apply keybinds to new profile |
| `va_process_manager.py` | Start/stop VoiceAttack |

### Testing

- `test_va_updater.py` - Test suite to verify functionality

## Requirements

**IMPORTANT:** EliteMining profiles must be **exported as uncompressed XML** for the updater to work.

### How to Export Uncompressed Profile:

1. Open VoiceAttack
2. Right-click your EliteMining profile
3. Select **"Export Profile"**
4. **UNCHECK** "Export as compressed binary"
5. Save to: `VoiceAttack 2/Apps/EliteMining/EliteMining-Profile.vap`

**Why?** VoiceAttack's compressed format uses proprietary binary serialization that cannot be parsed. The updater needs XML format to extract and restore keybinds. After updating, you import the profile normally and VoiceAttack will work with both EliteAPI and EliteVA.

## Installation

Already included in EliteMining! No additional setup needed.

## Usage

### From Python Code

```python
from app.va_profile_updater import VAProfileUpdater

# Initialize
updater = VAProfileUpdater(app_data_path)

# Check for update
update_info = updater.check_for_update(
    latest_version="4.8.0",
    download_url="https://example.com/profile.vap",
    release_notes="Bug fixes and improvements"
)

if update_info:
    # Progress callback (optional)
    def on_progress(step: str, progress: int):
        print(f"{step} ({progress}%)")
    
    # Perform update
    result = updater.update_profile(
        new_vap_path="path/to/new/profile.vap",
        progress_callback=on_progress
    )
    
    if result.success:
        print(f"Success! Restored {result.keybinds_restored} keybinds")
        print(f"Backup: {result.backup_path}")
    else:
        print(f"Failed: {result.message}")
```

### Integration with EliteMining UI

```python
def show_update_dialog():
    """Show update available dialog"""
    from tkinter import messagebox
    
    update_info = updater.check_for_update(...)
    if not update_info:
        return
    
    message = f"""New VoiceAttack Profile Available!

Current Version: {update_info.current_version}
New Version: {update_info.latest_version}

Your keybinds will be automatically preserved.

Update now?"""
    
    if messagebox.askyesno("Profile Update", message):
        # Download new profile
        new_vap = download_profile(update_info.download_url)
        
        # Show progress dialog
        progress = ProgressDialog("Updating...")
        
        # Execute update
        result = updater.update_profile(
            new_vap,
            progress_callback=progress.update
        )
        
        progress.close()
        
        # Show result
        if result.success:
            messagebox.showinfo("Success", result.message)
        else:
            messagebox.showerror("Failed", result.message)
```

## Testing

Run the test suite to verify everything works:

```bash
python test_va_updater.py
```

**Tests:**
1. ✓ VoiceAttack Detection
2. ✓ Profile Detection
3. ✓ Keybind Extraction  
4. ✓ Backup Creation

## How It Works

### Update Process

```
1. Backup Current Profile
   └─> Saves to: AppData/EliteMining/Backups/EliteMining-{version}-{timestamp}.vap

2. Extract Keybinds
   └─> Reads XML, extracts all keyboard/joystick/mouse bindings

3. Close VoiceAttack
   └─> Graceful shutdown (sends WM_CLOSE)
   └─> Force kill if necessary after timeout

4. Install New Profile
   └─> Copies new .VAP over old one

5. Restore Keybinds
   └─> Matches commands by name
   └─> Applies saved keybinds to new profile
   └─> Saves modified XML

6. Restart VoiceAttack
   └─> Launches VoiceAttack.exe
   └─> Waits for process to start

7. Success!
   └─> Shows confirmation with keybind count
```

### Rollback on Failure

If **any** step fails:
1. Stop update process
2. Restore backup profile
3. Restart VoiceAttack
4. Show error message

## Keybind Support

Preserves **all** keybind types:

- ✅ Keyboard shortcuts (`Ctrl+Shift+K`)
- ✅ Joystick buttons (`Joystick 1 Button 25`)
- ✅ Mouse buttons (`Middle Mouse Button`)
- ✅ Key release modes
- ✅ Command enabled/disabled state

## Backup System

**Automatic backups** on every update:

- Location: `AppData/Local/EliteMining/Backups/`
- Format: `EliteMining-{version}-{timestamp}.vap`
- Example: `EliteMining-4.7.5-20250103_143052.vap`

**Retention:** Backups are kept forever. You can manually delete old ones.

## Error Handling

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| VoiceAttack not found | Not installed or non-standard path | Updater will prompt for location |
| Failed to close VA | Process stuck | Force kill with confirmation |
| Backup failed | Disk full / permissions | Check free space, run as admin |
| Keybind mismatch | Command renamed | Logged as warning, command skipped |

### Recovery

- **Automatic rollback** on any failure
- **Original profile restored** from backup
- **VoiceAttack restarted** automatically
- **Full error logging** for debugging

## Requirements

### Python Packages

```
psutil>=5.9.0  # Process management
```

Install with:
```bash
pip install psutil
```

### VoiceAttack

- **Minimum version:** VoiceAttack 1.7+
- **Installation:** Standard or Steam version
- **Profile format:** .VAP (uncompressed XML)

## Limitations

- **Same-named commands only:** Keybinds restored by matching command names
- **Renamed commands:** Will not match (logged as warning)
- **New commands:** Imported without keybinds (as expected)
- **Removed commands:** Keybinds lost (as expected)

## Troubleshooting

### VoiceAttack Not Detected

```python
from app.va_process_manager import VAProcessManager

manager = VAProcessManager()
if not manager.va_exe:
    print("VoiceAttack not found!")
    print("Install to: C:\\Program Files\\VoiceAttack\\")
```

### Profile Not Found

Check profile is named correctly:
- Must contain "EliteMining" or "elitemining"
- Must be .vap file
- Must be in VoiceAttack directory

### Keybinds Not Restored

1. Check command names match exactly (case-sensitive)
2. Check VA log for warnings
3. Verify backup contains keybinds:
   ```python
   keybinds = updater.extract_keybinds(backup_path)
   print(f"Found: {len(keybinds)} keybinds")
   ```

## Future Enhancements

Planned features:

- [ ] Diff view (show changes before updating)
- [ ] Selective update (choose which commands)
- [ ] Cloud backup sync
- [ ] Auto-update scheduling
- [ ] Version history & rollback UI

## Architecture

See [docs/VA_PROFILE_AUTO_UPDATER.md](../docs/VA_PROFILE_AUTO_UPDATER.md) for complete design documentation.

## Support

If you encounter issues:

1. Run `test_va_updater.py` to diagnose
2. Check logs in EliteMining app
3. Report issue with test results

---

**Made with ❤️ for Elite Dangerous commanders who want hassle-free updates!**
