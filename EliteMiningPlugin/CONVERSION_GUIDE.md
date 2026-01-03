# VoiceAttack Command Conversion Guide

## Overview
This guide shows how to convert each EliteMining command from direct file writing to using the plugin.

---

## Command Conversion Pattern

### OLD WAY (Direct File Write):
```
Action: Write (overwrite), 'TAB:MINING' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'
```

### NEW WAY (Plugin):
```
Action 1: Set text [EM.Param1] to 'MINING'
Action 2: Execute plugin 'EliteMiningPlugin v1.0.0' with context 'TAB'
```

---

## TAB Commands (Switch Tabs)

### Pattern:
- **Old:** `Write 'TAB:XXXX' to eliteMiningCommand.txt`
- **New:** Set `[EM.Param1]` to tab name, call plugin with context `TAB`

### Conversions:

| Command | EM.Param1 Value | Context |
|---------|----------------|---------|
| Go to mining / Show mining tab | `MINING` | `TAB` |
| Go to hotspots / Find hotspots | `HOTSPOTS` | `TAB` |
| Go to market / Commodity market | `MARKET` | `TAB` |
| Go to systems / System finder | `SYSTEMS` | `TAB` |
| Go to distance / Distance calculator | `DISTANCE` | `TAB` |
| Go to voiceattack / Show voiceattack tab | `VOICEATTACK` | `TAB` |
| Go to bookmarks / Open bookmarks | `BOOKMARKS` | `TAB` |
| Go to settings / Open settings | `SETTINGS` | `TAB` |

### Example Conversion:
**Command:** "Go to mining"
```
OLD:
  Write (overwrite), 'TAB:MINING' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'

NEW:
  1. Set text [EM.Param1] to 'MINING'
  2. Execute plugin 'EliteMiningPlugin v1.0.0' with context 'TAB' (wait for return)
```

---

## SESSION Commands (Mining Session Control)

### Pattern:
- **Old:** `Write 'SESSION:XXXX' to eliteMiningCommand.txt`
- **New:** Set `[EM.Param1]` to action, call plugin with context `SESSION`

### Conversions:

| Command | EM.Param1 Value | Context |
|---------|----------------|---------|
| Begin mining / Start mining session | `START` | `SESSION` |
| End mining session | `END` | `SESSION` |
| Abort mining / Cancel mining session | `CANCEL` | `SESSION` |
| Reset mining session | `RESET` | `SESSION` |

### Example Conversion:
**Command:** "Begin mining"
```
OLD:
  Write (overwrite), 'SESSION:START' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'

NEW:
  1. Set text [EM.Param1] to 'START'
  2. Execute plugin 'EliteMiningPlugin v1.0.0' with context 'SESSION' (wait for return)
```

---

## SETTINGS Commands

### Pattern:
- **Old:** `Write 'SETTINGS:XXXX' to eliteMiningCommand.txt`
- **New:** Set `[EM.Param1]` to action, call plugin with context `SETTINGS`

### Conversions:

| Command | EM.Param1 Value | Context |
|---------|----------------|---------|
| Import game settings / Import from game | `IMPORT` | `SETTINGS` |
| Apply game settings / Apply to game | `APPLY` | `SETTINGS` |

### Example Conversion:
**Command:** "Import game settings"
```
OLD:
  Write (overwrite), 'SETTINGS:IMPORT' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'

NEW:
  1. Set text [EM.Param1] to 'IMPORT'
  2. Execute plugin 'EliteMiningPlugin v1.0.0' with context 'SETTINGS' (wait for return)
```

---

## ANNOUNCEMENT Commands (Load Presets)

### Pattern:
- **Old:** `Write 'ANNOUNCEMENT:LOAD:N' to eliteMiningCommand.txt`
- **New:** Set `[EM.ParamInt]` to preset number, call plugin with context `ANNOUNCEMENT`

### Conversions:

| Command | EM.Param1 Value | EM.ParamInt Value | Context |
|---------|----------------|------------------|---------|
| Announcement 1 / Load announcement 1 | `LOAD` | `1` | `ANNOUNCEMENT` |
| Announcement 2 / Load announcement 2 | `LOAD` | `2` | `ANNOUNCEMENT` |
| Announcement 3 / Load announcement 3 | `LOAD` | `3` | `ANNOUNCEMENT` |
| Announcement 4 / Load announcement 4 | `LOAD` | `4` | `ANNOUNCEMENT` |
| Announcement 5 / Load announcement 5 | `LOAD` | `5` | `ANNOUNCEMENT` |
| Announcement 6 / Load announcement 6 | `LOAD` | `6` | `ANNOUNCEMENT` |

### Example Conversion:
**Command:** "Announcement 1"
```
OLD:
  Write (overwrite), 'ANNOUNCEMENT:LOAD:1' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'

NEW:
  1. Set text [EM.Param1] to 'LOAD'
  2. Set integer [EM.ParamInt] to 1
  3. Execute plugin 'EliteMiningPlugin v1.0.0' with context 'ANNOUNCEMENT' (wait for return)
```

---

## APP Commands (Application Control)

### Pattern:
- **Old:** `Write 'APP:XXXX' to eliteMiningCommand.txt`
- **New:** Set `[EM.Param1]` to action, call plugin with context `APP`

### Conversions:

| Command | EM.Param1 Value | Context |
|---------|----------------|---------|
| Exit Elite Mining / Close app | `CLOSE` | `APP` |
| Minimize Elite Mining | `MINIMIZE` | `APP` |
| Restore Elite Mining | `RESTORE` | `APP` |

### Example Conversion:
**Command:** "Exit Elite Mining"
```
OLD:
  Write (overwrite), 'APP:CLOSE' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'

NEW:
  1. Set text [EM.Param1] to 'CLOSE'
  2. Execute plugin 'EliteMiningPlugin v1.0.0' with context 'APP' (wait for return)
```

---

## PRESET Commands (Ship Presets - NOT YET IMPLEMENTED IN PLUGIN)

### Pattern:
- **Old:** `Write 'PRESET:LOAD:N' to eliteMiningCommand.txt`
- **New:** Set `[EM.Param1]` to action, `[EM.ParamInt]` to number, call plugin with context `PRESET`

**Note:** These commands are defined in the plugin but you'll need to verify they work with your Python app.

### Conversions:

| Command | EM.Param1 Value | EM.ParamInt Value | Context |
|---------|----------------|------------------|---------|
| Load preset 1 | `LOAD` | `1` | `PRESET` |
| Save preset 1 | `SAVE` | `1` | `PRESET` |
| Load preset 2 | `LOAD` | `2` | `PRESET` |
| Save preset 2 | `SAVE` | `2` | `PRESET` |

---

## Step-by-Step Conversion Process

### For Each Command:

1. **Open the command in VoiceAttack**
   - Edit Profile → Select command → Edit

2. **Identify the old action**
   - Look for: "Write (overwrite), 'XXX' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'"

3. **Delete the old action**
   - Select it and click Delete

4. **Add new actions:**
   
   **For simple commands (like TAB):**
   - Action 1: Other → Set a Text Value
     - Variable: `EM.Param1`
     - Value: (see table above)
   - Action 2: Other → Advanced → Execute an External Plugin Function
     - Plugin: `EliteMiningPlugin v1.0.0 - Viper-Dude`
     - Context: (see table above)
     - ✅ Wait for function to return
   
   **For numbered commands (like ANNOUNCEMENT):**
   - Action 1: Other → Set a Text Value
     - Variable: `EM.Param1`
     - Value: `LOAD` (or action type)
   - Action 2: Other → Set an Integer Value
     - Variable: `EM.ParamInt`
     - Value: (preset number)
   - Action 3: Other → Advanced → Execute an External Plugin Function
     - Plugin: `EliteMiningPlugin v1.0.0 - Viper-Dude`
     - Context: `ANNOUNCEMENT`
     - ✅ Wait for function to return

5. **Test the command**
   - Save and say the voice command
   - Verify it works

6. **Repeat for all commands**

---

## Quick Conversion Checklist

- [ ] TAB commands (8 variations × multiple commands = ~40 commands)
- [ ] SESSION commands (~4 commands)
- [ ] SETTINGS commands (~2 commands)
- [ ] ANNOUNCEMENT commands (~12 commands)
- [ ] APP commands (~1-3 commands)
- [ ] Test all converted commands
- [ ] Export new profile
- [ ] Document changes for users

---

## Benefits After Conversion

✅ **Users keep their hotkeys** - Commands structure stays the same  
✅ **Easy updates** - Just replace the DLL, no profile re-import  
✅ **Cleaner commands** - No file paths, just parameters  
✅ **Better maintainability** - Logic centralized in plugin  
✅ **Less error-prone** - No file permission issues  

---

## Testing Strategy

1. **Start with one TAB command** - "Go to mining"
2. **Test thoroughly** - Verify tab switches
3. **Convert all TAB commands** - They're identical pattern
4. **Move to SESSION commands** - Different pattern
5. **Continue with remaining types**
6. **Final testing** - Test random sampling of all commands

---

## Estimated Time

- **Per command conversion:** 1-2 minutes
- **Total commands:** ~60-80 commands
- **Total time:** 1-2 hours (with breaks)

**Tip:** Convert in batches by category to speed up the process!
