# VoiceAttack Keybind Preservation System

**Status:** Implemented but not yet enabled in releases (planned for v4.8.0)

## Overview

The keybind preservation system allows users to update EliteMining's VoiceAttack profile without losing their custom keybind configurations. This solves the major pain point where every profile update required users to reconfigure all their keybinds manually.

## Architecture

### Core Components

1. **`va_keybind_extractor.py`** - Extracts keybinds from VoiceAttack profiles
2. **`va_keybind_applier.py`** - Applies keybinds to profiles
3. **`va_profile_updater.py`** - Orchestrates the update process
4. **`va_export_helper.py`** - Manages user XML exports
5. **`clear_keybinds.py`** - Cleans keybinds from profiles for release

### Data Flow

```
User Profile (XML) → Extractor → Keybinds Dict → Applier → Updated Profile (XML)
```

## How It Works

### Step 1: User Preparation (Before Update)
User exports their current profile as XML:
- VoiceAttack → Profile → Export Profile
- Save as type: **"VoiceAttack Profile Expanded as XML (*.vap)"**
- Save location: User's choice (tracked by export_helper)

### Step 2: Update Process
When user updates EliteMining:

1. **Locate keybind source:**
   - Checks for saved XML export (preferred)
   - Falls back to current profile backup if no export

2. **Extract keybinds:**
   - Parses XML profile
   - Extracts keybind data from each command
   - Returns: `{command_name: {keybind_data}}`

3. **Install new profile:**
   - Copies new clean .vap to VoiceAttack Apps folder

4. **Restore keybinds:**
   - Matches commands by name
   - Applies saved keybinds to new profile
   - Skips commands not found in new profile

5. **Finalize:**
   - User imports updated profile in VoiceAttack
   - Keybinds are preserved!

## File Formats

### Profile Format Requirements
- **Release profiles:** XML format (readable, editable)
- **User exports:** XML format (required for keybind extraction)
- **Binary .vap:** Cannot be read - not supported

### Keybind Data Structure

```python
{
    "Command Name": {
        "UseShortcut": "true/false",
        "UseShortcutKey": "Key code",
        "UseShortcutKeyShift": "true/false",
        "UseShortcutKeyAlt": "true/false",
        "UseShortcutKeyCtrl": "true/false",
        "UseShortcutKeyWin": "true/false"
    }
}
```

## Command Matching Strategy

### Why Not Use GUIDs?
VoiceAttack regenerates command IDs (`<Id>` and `<BaseId>`) on every import. Test results showed **0% ID persistence**.

### Name-Based Matching (Current)
- Matches commands by `<CommandString>` (command name)
- Handles renamed commands: keybinds lost
- Handles new commands: no keybinds applied
- Handles deleted commands: keybinds ignored

**Limitation:** If command is renamed between versions, keybind is lost.

## Usage Guide

### For Users (v4.8.0+)

**Before updating:**
```
1. Open VoiceAttack
2. Profile → Export Profile
3. Save as: "VoiceAttack Profile Expanded as XML"
4. Save anywhere (app remembers location)
5. Install EliteMining update
6. Import updated profile
7. Keybinds restored automatically!
```

### For Developers (Creating Releases)

**Clean profile for release:**
```bash
python EliteMiningPlugin/scripts/clear_keybinds.py
# Input: EliteMining Dev v4.75-Profile.vap
# Output: EliteMining-Profile-CLEAN.vap
```

**Ensure XML format:**
- Export from VoiceAttack as "VoiceAttack Profile Expanded as XML"
- Verify file is XML (open in text editor - should see `<?xml`)
- Rename to: `EliteMining-Profile.vap`
- Include in installer/ZIP

**Test the update process:**
```bash
# 1. Export your current profile as XML
# 2. Run update with test profile
# 3. Verify keybinds are preserved
# 4. Check logs in app/logs/
```

## Scripts Reference

### `clear_keybinds.py`
**Purpose:** Remove all keybinds from profile for clean release
**Location:** `EliteMiningPlugin/scripts/clear_keybinds.py`
**Usage:**
```bash
python EliteMiningPlugin/scripts/clear_keybinds.py
# Prompts for input/output files
```

### `test_id_persistence.py`
**Purpose:** Test if VoiceAttack preserves command IDs
**Location:** `EliteMiningPlugin/test scrip/test_id_persistence.py`
**Result:** IDs do NOT persist (0/5 matches)

## Configuration Files

### `va_export_config.json`
Stores user's XML export location:
```json
{
    "last_export_path": "C:/Users/.../EliteMining-Backup.vap",
    "last_export_date": "2026-01-03T15:30:00"
}
```

**Location:** `app/va_export_config.json`

## Error Handling

### Common Issues

**1. No XML export found**
- **Cause:** User didn't export before update
- **Fallback:** Uses current profile backup
- **Risk:** May not have latest keybinds

**2. Binary .vap format**
- **Cause:** User exported as regular .vap (binary)
- **Solution:** Re-export as XML
- **Error:** "Cannot read binary format"

**3. Command not found**
- **Cause:** Command renamed/deleted in new version
- **Behavior:** Keybind skipped, logged
- **User impact:** Must reconfigure that keybind

**4. VoiceAttack not closing**
- **Cause:** Process stuck or user intervention
- **Solution:** Manual close + retry
- **Prevention:** Add timeout + force close

## Testing Checklist

Before enabling in production:

- [ ] Test with XML export
- [ ] Test fallback (no export)
- [ ] Test with binary export (should fail gracefully)
- [ ] Test with renamed commands
- [ ] Test with new commands
- [ ] Test with deleted commands
- [ ] Test VoiceAttack close/restart
- [ ] Test progress reporting
- [ ] Test error recovery
- [ ] Test logging output
- [ ] Verify clean profile has no keybinds
- [ ] Verify updated profile works in VoiceAttack

## Future Enhancements

### Potential Improvements
1. **Smart command matching** - Fuzzy matching for renamed commands
2. **Keybind conflict detection** - Warn about duplicate keybinds
3. **Backup retention** - Keep last N backups
4. **GUI integration** - Visual keybind editor
5. **Export reminder** - Prompt user before update
6. **Automatic export** - Export on profile detection

### Known Limitations
- Cannot preserve keybinds for renamed commands
- Requires user to export manually before update
- No cross-profile keybind management
- No keybind validation (duplicates, conflicts)

## Rollout Plan

### v4.75 (Current)
- ✅ Profile converted to XML format
- ✅ Documentation added
- ✅ Clean profile scripts ready
- ❌ Update feature disabled (testing)

### v4.8.0 (Next)
- Enable keybind preservation
- Add UI for XML export reminder
- Add validation and error reporting
- Document user workflow

### v4.9.0+ (Future)
- Automatic export detection
- Advanced matching algorithms
- GUI keybind editor
- Cross-profile management

## Technical Notes

### VoiceAttack XML Structure
```xml
<Profile>
  <Commands>
    <Command>
      <CommandString>Command Name</CommandString>
      <Id>GUID</Id>
      <BaseId>GUID</BaseId>
      <UseShortcut>true</UseShortcut>
      <UseShortcutKey>68</UseShortcutKey>
      <!-- ... more keybind fields ... -->
    </Command>
  </Commands>
</Profile>
```

### Key Fields
- `CommandString` - Command name (used for matching)
- `Id` - Regenerated on import (not persistent)
- `BaseId` - Also regenerated (not persistent)
- `UseShortcut` - Enable/disable keybind
- `UseShortcutKey` - Virtual key code

### Virtual Key Codes
VoiceAttack uses Windows virtual key codes:
- 68 = 'D' key
- 70 = 'F' key
- 112-123 = F1-F12
- See: https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes

## Support & Troubleshooting

### For Users
- Check FAQ.md for common issues
- Enable logging in app settings
- Check `app/logs/va_profile_updater.log`
- Discord: Support channel

### For Developers
- Run tests: `pytest tests/test_keybind_*.py`
- Check logs: `app/logs/`
- Debug: Set `logging.DEBUG` level
- Test with: `test_id_persistence.py`

## References

- VoiceAttack Help: `EliteMiningPlugin/docs/VoiceAttackHelp.txt`
- Profile Parser: `app/va_profile_parser.py`
- Binary Reader: `app/va_binary_reader.py`
- Export Helper: `app/va_export_helper.py`

---

**Last Updated:** 2026-01-03
**Author:** EliteMining Development Team
**Status:** Ready for v4.8.0 rollout
