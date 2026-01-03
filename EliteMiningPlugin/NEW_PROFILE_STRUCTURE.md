# New VA Profile Structure - Plugin Based

This document shows how to convert your existing VA commands to use the plugin.

## Before (Current) vs After (Plugin)

### Example 1: UI Tab Commands

**BEFORE (Current):**
```
Command: " Go to mining tab"
  Actions:
    - Write (overwrite), 'TAB:MINING' to file '{VA_APPS}\EliteMining\Variables\eliteMiningCommand.txt'
```

**AFTER (Plugin):**
```
Command: " Go to mining tab"
  Actions:
    - Set text [EM.Param1] to 'MINING'
    - Execute Plugin: EliteMiningPlugin, Context: "TAB"
```

**Benefits:** Users keep their hotkeys! When you update the plugin, the command still works.

---

### Example 2: Firegroup Commands

**BEFORE (Current):**
```
Command: " Setting firegroup for mining lasers to charlie"
  Actions:
    - Write (overwrite), 'charlie' to file '{VA_APPS}\EliteMining\Variables\fglasers.txt'
```

**AFTER (Plugin):**
```
Command: " Setting firegroup for mining lasers to charlie"
  Actions:
    - Set text [EM.Param1] to 'lasers'
    - Set text [EM.Param2] to 'charlie'
    - Execute Plugin: EliteMiningPlugin, Context: "SetFiregroup"
```

---

### Example 3: Timer Commands

**BEFORE (Current):**
```
Command: " Setting timer for laser mining to 38 seconds"
  Actions:
    - Write (overwrite), '38' to file '{VA_APPS}\EliteMining\Variables\timerlasermining.txt'
```

**AFTER (Plugin):**
```
Command: " Setting timer for laser mining to 38 seconds"
  Actions:
    - Set text [EM.Param1] to 'lasermining'
    - Set integer [EM.ParamInt] to 38
    - Execute Plugin: EliteMiningPlugin, Context: "SetTimer"
```

---

### Example 4: Toggle Commands

**BEFORE (Current):**
```
Command: " Setting toggle for cargo scoop to 1"
  Actions:
    - Write (overwrite), '1' to file '{VA_APPS}\EliteMining\Variables\togglecargoscoop.txt'
```

**AFTER (Plugin):**
```
Command: " Setting toggle for cargo scoop to 1"
  Actions:
    - Set text [EM.Param1] to 'cargoscoop'
    - Set integer [EM.ParamInt] to 1
    - Execute Plugin: EliteMiningPlugin, Context: "SetToggle"
```

---

### Example 5: Swap/Switch Commands

**BEFORE (Current):**
```
Command: " Swap lasers"
  Actions:
    - Set text [btnlasersValue] to [{VA_DIR}\Apps\EliteMining\Variables\btnLasers.txt]
    - Begin Text Compare : [btnlasersValue] Equals 'primary'
      - Set text [btnlasersValue] to 'secondary'
      - Write (overwrite), 'secondary' to file '{VA_DIR}\Apps\EliteMining\Variables\btnLasers.txt'
    - Else
      - Set text [btnlasersValue] to 'primary'
      - Write (overwrite), 'primary' to file '{VA_DIR}\Apps\EliteMining\Variables\btnLasers.txt'
    - End Condition
```

**AFTER (Plugin):**
```
Command: " Swap lasers"
  Actions:
    - Set text [EM.Param1] to 'lasers'
    - Execute Plugin: EliteMiningPlugin, Context: "SwapFireButton"
```

**Much simpler!** The plugin handles the logic.

---

## Complete Command Reference

### All UI Commands
All these use the same pattern:
- Set text [EM.Param1] to '<TAB_NAME>'
- Execute Plugin: EliteMiningPlugin, Context: "TAB"

Tab names: MINING, SYSTEMS, MARKET, HOTSPOTS, BOOKMARKS, DISTANCE, SETTINGS, VOICEATTACK

### All Session Commands
- Set text [EM.Param1] to '<ACTION>'
- Execute Plugin: EliteMiningPlugin, Context: "SESSION"

Actions: START, END, PAUSE, CANCEL

### All Firegroup Commands
- Set text [EM.Param1] to '<TOOL>'
- Set text [EM.Param2] to '<FIREGROUP>'
- Execute Plugin: EliteMiningPlugin, Context: "SetFiregroup"

Tools: discovery, lasers, prospector, pwa, seismic, ssm, weapons
Firegroups: alpha, bravo, charlie, delta, echo, foxtrot

### All Fire Button Commands
- Set text [EM.Param1] to '<TOOL>'
- Set text [EM.Param2] to '<BUTTON>'
- Execute Plugin: EliteMiningPlugin, Context: "SetFireButton"

Tools: discovery, lasers, prospector, pwa
Buttons: primary, secondary

---

## Migration Strategy

### Option 1: Full Replacement (Recommended)
1. Build the plugin DLL
2. Create a new "clean" VA profile with all commands using the plugin
3. Users import the new profile
4. **First time only** - users lose bindings, but this is the LAST time ever

### Option 2: Gradual Migration
1. Keep existing profile
2. Add plugin-based commands alongside old commands
3. Gradually deprecate old commands
4. Eventually remove old commands in next major version

### Option 3: Auto-Migration Script
1. Create a tool that reads the old profile
2. Generates a new profile with plugin commands
3. Preserves all hotkeys
4. Users run once to migrate

---

## Future Updates

After this plugin is deployed, ALL future updates work like this:

**Developer (You):**
1. Modify `EliteMiningPlugin.cs`
2. Rebuild DLL
3. Release new DLL file

**Users:**
1. Replace `EliteMiningPlugin.dll` in VoiceAttack folder
2. **Done!** All hotkeys and commands still work

No more profile re-imports. No more lost bindings. Just replace the DLL.
