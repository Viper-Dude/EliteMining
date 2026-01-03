# EliteMining Plugin - Quick Start Guide

## What Problem Does This Solve?

**Problem:** When users update your VA profile, they lose all their custom hotkey bindings.

**Solution:** Move logic into a C# plugin DLL. VA commands become thin wrappers that call the plugin. Users update the DLL, keep their profile and hotkeys.

---

## Step 1: Build the Plugin

```powershell
cd "d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\EliteMiningPlugin"
.\build.ps1
```

This creates: `bin\Release\net48\EliteMiningPlugin.dll`

---

## Step 2: Install for Testing

Copy the DLL to your VoiceAttack folder:
```powershell
# Example paths - adjust to your VA installation
Copy-Item "bin\Release\net48\EliteMiningPlugin.dll" "C:\Program Files (x86)\VoiceAttack\EliteMiningPlugin.dll"
# OR
Copy-Item "bin\Release\net48\EliteMiningPlugin.dll" "D:\SteamLibrary\steamapps\common\VoiceAttack\EliteMiningPlugin.dll"
```

Restart VoiceAttack - it will auto-detect the plugin.

---

## Step 3: Create Test Commands

In VoiceAttack, create a new command to test:

### Test Command 1: Switch Tab
```
Command Name: "Test go to mining"
When I say: "test mining tab"
Actions:
  1. Set text [EM.Param1] to 'MINING'
  2. Execute plugin function: 'EliteMiningPlugin.EliteMiningPlugin.VA_Invoke1' with context 'TAB'
```

### Test Command 2: Set Firegroup
```
Command Name: "Test set firegroup"
When I say: "test firegroup charlie"
Actions:
  1. Set text [EM.Param1] to 'lasers'
  2. Set text [EM.Param2] to 'charlie'
  3. Execute plugin function: 'EliteMiningPlugin.EliteMiningPlugin.VA_Invoke1' with context 'SetFiregroup'
```

Say "test mining tab" - check that `Variables\eliteMiningCommand.txt` now contains `TAB:MINING`.

---

## Step 4: Verify Output

The plugin writes to the same files your Python app reads:

```
Variables\
├── eliteMiningCommand.txt       (UI commands)
├── fglasers.txt                 (Firegroup for lasers)
├── fgprospector.txt            (Firegroup for prospector)
├── btnlasers.txt               (Fire button for lasers)
├── timerlasermining.txt        (Timer values)
└── togglecargoscoop.txt        (Toggle states)
```

Your Python app doesn't need any changes - it continues monitoring these files.

---

## Step 5: Convert Your Full Profile

See `NEW_PROFILE_STRUCTURE.md` for the full conversion guide.

**Key Pattern:**
```
Old:  Write file directly in VA command
New:  Set parameters → Call plugin → Plugin writes file
```

---

## Step 6: Distribution

Include in your installer:
1. `EliteMiningPlugin.dll` → VoiceAttack folder
2. New VA profile with plugin-based commands
3. Update instructions

---

## Troubleshooting

### Plugin Not Detected
- Ensure DLL is in VoiceAttack root folder (not in a subfolder)
- Restart VoiceAttack completely
- Check VoiceAttack log for plugin initialization messages

### Commands Not Working
- Check VoiceAttack log (Options → System/Advanced → Event Log)
- Plugin logs in blue: "EliteMining Plugin initialized"
- Errors logged in red with details

### Files Not Created
- Verify VA_APPS variable is set correctly
- Check file permissions in Variables folder
- Look for error messages in VA log

---

## Development Workflow

### Making Changes
1. Edit `EliteMiningPlugin.cs`
2. Run `build.ps1`
3. Copy new DLL to VoiceAttack folder
4. Restart VoiceAttack
5. Test

### Adding New Commands
1. Add new case in `RouteCommand()` method
2. Define what parameters it needs
3. Rebuild and test
4. Update profile with new command

---

## Support

If users have issues:
1. Check VoiceAttack log
2. Verify DLL version matches profile version
3. Test with simple command first
4. Check file permissions

---

## Next Steps

Once working:
1. Convert all existing commands to use plugin
2. Create new "clean" profile
3. Update installer to include plugin DLL
4. Document for users

**Future updates = Just replace the DLL!** 🎉
