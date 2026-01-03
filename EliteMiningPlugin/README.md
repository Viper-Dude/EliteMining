# EliteMining VoiceAttack Plugin

## Overview

This C# plugin acts as a bridge between VoiceAttack commands and the EliteMining Python application. Instead of having complex logic in VA commands, the plugin handles all the routing and file writing.

## Benefits

✅ **Update-Safe**: Users can update the plugin DLL without losing VA hotkey bindings  
✅ **Cleaner Commands**: VA commands become simple thin wrappers  
✅ **Centralized Logic**: All file writing logic in one place  
✅ **Easy Maintenance**: Update the DLL, not the profile  

## Building

```powershell
cd EliteMiningPlugin
dotnet build -c Release
```

Output: `bin/Release/net8.0/EliteMiningPlugin.dll`

**Note:** Built with .NET 8.0 for modern VoiceAttack compatibility (VoiceAttack 1.10+ supports .NET Core/8+)

## Installation

1. Copy `EliteMiningPlugin.dll` to your VoiceAttack installation directory
2. VoiceAttack will auto-detect the plugin on next launch

## VA Profile Command Structure

All commands now use this simple pattern:

```
Command: "Setting firegroup for mining lasers to charlie"
  Actions:
    - Set text [EM.Param1] to 'lasers'
    - Set text [EM.Param2] to 'charlie'
    - Execute Plugin: EliteMiningPlugin
      Context: "SetFiregroup"
```

## Command Contexts

### UI Commands
- **Context**: `TAB`
  - **Param1**: MINING, SYSTEMS, MARKET, HOTSPOTS, BOOKMARKS, DISTANCE, SETTINGS, VOICEATTACK

- **Context**: `SESSION`
  - **Param1**: START, END, PAUSE, CANCEL

- **Context**: `APP`
  - **Param1**: CLOSE, RESTORE

- **Context**: `SETTINGS`
  - **Param1**: APPLY, IMPORT

- **Context**: `ANNOUNCEMENT`
  - **Param1**: 1-6 (preset number)

### Firegroup Commands
- **Context**: `SetFiregroup`
  - **Param1**: discovery, lasers, prospector, pwa, seismic, ssm, weapons
  - **Param2**: alpha, bravo, charlie, delta, echo, foxtrot

### Fire Button Commands
- **Context**: `SetFireButton`
  - **Param1**: discovery, lasers, prospector, pwa
  - **Param2**: primary, secondary

- **Context**: `SwapFireButton`
  - **Param1**: discovery, lasers, prospector, pwa

### Timer Commands
- **Context**: `SetTimer`
  - **Param1**: lasermining, cargoscoop, laserminingextra, pause, prospectortarget
  - **ParamInt**: seconds

### Toggle Commands
- **Context**: `SetToggle`
  - **Param1**: cargoscoop, laserminingextra, prospectortarget, powersettings, pwa, target
  - **ParamInt**: 0 or 1

## Example VA Commands

### Simple UI Command
```
Command: " Go to mining tab"
  Actions:
    - Set text [EM.Param1] to 'MINING'
    - Execute Plugin: EliteMiningPlugin, Context: "TAB"
```

### Firegroup Command
```
Command: " Setting firegroup for mining lasers to charlie"
  Actions:
    - Set text [EM.Param1] to 'lasers'
    - Set text [EM.Param2] to 'charlie'
    - Execute Plugin: EliteMiningPlugin, Context: "SetFiregroup"
```

### Timer Command
```
Command: " Setting timer for laser mining to 38 seconds"
  Actions:
    - Set text [EM.Param1] to 'lasermining'
    - Set integer [EM.ParamInt] to 38
    - Execute Plugin: EliteMiningPlugin, Context: "SetTimer"
```

## Updating

When releasing a new version:
1. Update logic in `EliteMiningPlugin.cs`
2. Rebuild the DLL
3. Users replace only the DLL file
4. **VA profile and hotkeys remain unchanged!**

## File Output

The plugin writes to the same `Variables/` folder structure:
- `Variables/eliteMiningCommand.txt` - UI commands
- `Variables/fgdiscovery.txt` - Firegroup settings
- `Variables/btnlasers.txt` - Fire button settings
- `Variables/timerlasermining.txt` - Timer values
- `Variables/togglecargoscoop.txt` - Toggle states

Your Python app continues reading these files exactly as before.

## License

GPL-3.0 (same as EliteMining)
