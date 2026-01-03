# Converting "Deploy Weapons" Command

## Overview
This guide shows how to convert "Deploy weapons" from a standalone VA command to a plugin-managed command.

---

## Current Command Structure

```
"Deploy weapons" (Joystick 1 Button 25)
  Begin Condition : [startLasermining] Equals True OR [resetLasermining] Equals True OR [ScanningCores] Equals False
      Write [Blue] 'Deploying Weapons' displayed as [Check]
      Execute command, '((Stop firing lasers))' (and wait until it completes)
      Kill command, 'Reset mining sequence'
      Kill command, 'Start Scanning for Cores;Start Pulse wave scanning'
      Kill command, 'Start mining sequence'
  End Condition
  Pause 1 second
  Begin Boolean Compare : [EliteAPI.Supercruise] Equals False
      Execute command, 'deploy hardpoints' (and wait until it completes)
      Execute command, '((Setting FG for weapons))' (and wait until it completes)
  End Condition
  Begin Boolean Compare : [EliteAPI.AnalysisMode] Equals True
      Execute command, 'Switch Cockpit mode Combat' (and wait until it completes)
  End Condition
```

---

## New Plugin-Managed Structure

### Plugin Code (Already Added)

```csharp
case "DEPLOY_WEAPONS":
    // Configurable pause duration
    vaProxy.SetDecimal("EM.WeaponDeployPause", 1.0m);
    
    // Commands to kill (can be updated in plugin)
    vaProxy.SetText("EM.KillCommands", "Reset mining sequence;Start Scanning for Cores;Start Pulse wave scanning;Start mining sequence");
    
    // Action sequence (can be reordered in plugin)
    vaProxy.SetText("EM.Action1", "STOP_LASERS");
    vaProxy.SetText("EM.Action2", "KILL_SEQUENCES");
    vaProxy.SetText("EM.Action3", "PAUSE");
    vaProxy.SetText("EM.Action4", "DEPLOY_HARDPOINTS");
    vaProxy.SetText("EM.Action5", "SET_FG_WEAPONS");
    vaProxy.SetText("EM.Action6", "CHECK_ANALYSIS_MODE");
    vaProxy.SetText("EM.Action7", "DONE");
    
    vaProxy.SetBoolean("EM.Ready", true);
    break;
```

### New VoiceAttack Command

```
"Deploy weapons" (Joystick 1 Button 25 - KEYBIND PRESERVED!)

1. Call plugin 'EliteMiningPlugin v1.0.0 - Viper-Dude' with context 'DEPLOY_WEAPONS' (wait for return)

2. Begin Boolean Compare: [EM.Ready] Equals True
   
   3. Set integer [ActionIndex] to 1
   
   4. Start Loop While: [EM.Action{INT:ActionIndex}] Does Not Equal 'DONE'
      
      5. Begin Text Compare: [EM.Action{INT:ActionIndex}] Equals 'STOP_LASERS'
         6. Begin Condition: [startLasermining] Equals True OR [resetLasermining] Equals True OR [ScanningCores] Equals False
            7. Write [Blue] 'Deploying Weapons' displayed as [Check]
            8. Execute command '((Stop firing lasers))' (wait)
            End Condition
      
      Else If Text Compare: [EM.Action{INT:ActionIndex}] Equals 'KILL_SEQUENCES'
         9. Kill command [EM.KillCommands]
      
      Else If Text Compare: [EM.Action{INT:ActionIndex}] Equals 'PAUSE'
         10. Pause a variable number of seconds [{DEC:EM.WeaponDeployPause}]
      
      Else If Text Compare: [EM.Action{INT:ActionIndex}] Equals 'DEPLOY_HARDPOINTS'
         11. Begin Boolean Compare: [EliteAPI.Supercruise] Equals False
             12. Execute command 'deploy hardpoints' (wait)
             End Condition
      
      Else If Text Compare: [EM.Action{INT:ActionIndex}] Equals 'SET_FG_WEAPONS'
         13. Execute command '((Setting FG for weapons))' (wait)
      
      Else If Text Compare: [EM.Action{INT:ActionIndex}] Equals 'CHECK_ANALYSIS_MODE'
         14. Begin Boolean Compare: [EliteAPI.AnalysisMode] Equals True
             15. Execute command 'Switch Cockpit mode Combat' (wait)
             End Condition
      
      End Condition
      
      16. Set integer [ActionIndex] to [{INT:ActionIndex} + 1]
   
   End Loop
   
End Condition
```

---

## Step-by-Step Conversion in VoiceAttack

### 1. Backup First!
- Export profile as uncompressed .VAP
- Save as `EliteMining-BACKUP-BeforeDeployWeapons.vap`

### 2. Open "Deploy weapons" Command

### 3. Delete ALL Existing Actions

### 4. Add New Actions:

**Action 1:** Other → Advanced → Execute an External Plugin Function
- Plugin: `EliteMiningPlugin v1.0.0 - Viper-Dude`
- Context: `DEPLOY_WEAPONS`
- ✓ Wait for the plugin function to finish before continuing

**Action 2:** Other → Begin a Conditional (If Statement) Block
- Type: Boolean
- Variable: `EM.Ready`
- Comparison: Equals
- Value: True

**Action 3:** Other → Set an Integer Value
- Variable: `ActionIndex`
- Value: `1`

**Action 4:** Other → Start a Loop
- Loop type: While
- Condition type: Text
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Does Not Equal
- Value: `DONE`

**Action 5:** Other → Begin a Conditional (If Statement) Block
- Type: Text
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Equals
- Value: `STOP_LASERS`

**Action 6:** Other → Begin a Conditional (If Statement) Block
- Complex condition: `[startLasermining] Equals True OR [resetLasermining] Equals True OR [ScanningCores] Equals False`

**Action 7:** Write a Value to the Event Log
- Text: `Deploying Weapons`
- Color: Blue
- Display: Check

**Action 8:** Other → Execute Another Command
- Command: `((Stop firing lasers))`
- ✓ Wait until command completes

**Action 9:** Other → End a Conditional

**Action 10:** Other → Else If
- Type: Text
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Equals
- Value: `KILL_SEQUENCES`

**Action 11:** Other → Stop Command
- Command: `{TXT:EM.KillCommands}`

**Action 12:** Other → Else If
- Type: Text
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Equals
- Value: `PAUSE`

**Action 13:** Pause → Pause for a Specified Amount of Time
- Type: Variable
- Variable: `{DEC:EM.WeaponDeployPause}`

**Action 14:** Other → Else If
- Type: Text  
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Equals
- Value: `DEPLOY_HARDPOINTS`

**Action 15:** Other → Begin a Conditional (If Statement) Block
- Type: Boolean
- Variable: `EliteAPI.Supercruise`
- Comparison: Equals
- Value: False

**Action 16:** Other → Execute Another Command
- Command: `deploy hardpoints`
- ✓ Wait until command completes

**Action 17:** Other → End a Conditional

**Action 18:** Other → Else If
- Type: Text
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Equals
- Value: `SET_FG_WEAPONS`

**Action 19:** Other → Execute Another Command
- Command: `((Setting FG for weapons))`
- ✓ Wait until command completes

**Action 20:** Other → Else If
- Type: Text
- Variable: `EM.Action{INT:ActionIndex}`
- Comparison: Equals
- Value: `CHECK_ANALYSIS_MODE`

**Action 21:** Other → Begin a Conditional (If Statement) Block
- Type: Boolean
- Variable: `EliteAPI.AnalysisMode`
- Comparison: Equals
- Value: True

**Action 22:** Other → Execute Another Command
- Command: `Switch Cockpit mode Combat`
- ✓ Wait until command completes

**Action 23:** Other → End a Conditional

**Action 24:** Other → End a Conditional (for the Else If chain)

**Action 25:** Other → Set an Integer Value
- Variable: `ActionIndex`
- Value: Set to computed value
- Expression: `{INT:ActionIndex} + 1`

**Action 26:** Other → End Loop

**Action 27:** Other → End a Conditional (for EM.Ready check)

### 5. Save Command

### 6. Build and Deploy Plugin

```powershell
cd EliteMiningPlugin
.\build.ps1
```

Close VoiceAttack, wait for build to complete, restart VoiceAttack.

### 7. Test!

- Press Joystick 1 Button 25 (your keybind)
- Verify weapons deploy
- Check VA log for errors

---

## What's Updatable Now

### Via Plugin DLL (no profile import needed):

1. **Pause duration:**
   ```csharp
   vaProxy.SetDecimal("EM.WeaponDeployPause", 1.5m); // Change to 1.5 seconds
   ```

2. **Commands to kill:**
   ```csharp
   vaProxy.SetText("EM.KillCommands", "Reset mining sequence;Start mining sequence"); // Remove some
   ```

3. **Action sequence order:**
   ```csharp
   // Reorder or remove actions
   vaProxy.SetText("EM.Action1", "PAUSE");  // Pause first instead
   vaProxy.SetText("EM.Action2", "STOP_LASERS");
   // etc.
   ```

4. **Add new actions:**
   ```csharp
   vaProxy.SetText("EM.Action7", "NEW_ACTION");
   vaProxy.SetText("EM.Action8", "DONE");
   ```
   Then add the action handler in VA command

### Users Keep:
✅ Joystick 1 Button 25 keybind
✅ All hotkeys
✅ HOTAS bindings

---

## Future-Proofing

**Q: What if "Start Scanning for Cores" gets converted later?**

**A:** It still works! The command name stays the same, so:
- `Kill command 'Start Scanning for Cores'` still works
- `Execute command 'Start Scanning for Cores'` still works

The command just has different internal logic, but externally it's still the same VA command.

---

## Troubleshooting

**Command doesn't execute:**
- Check EM.Ready is True in VA variables
- Check EM.Action1 through EM.Action7 are set
- Check VA log for plugin errors

**Wrong action executes:**
- Verify action names match exactly (case-sensitive)
- Check ActionIndex incrementing properly

**Pause wrong duration:**
- Check EM.WeaponDeployPause decimal variable
- Plugin sets it, VA must read it as decimal

---

## Benefits

✅ **Update pause timing** - Just change plugin, rebuild DLL
✅ **Change which commands to kill** - Update plugin list
✅ **Reorder actions** - Rearrange in plugin
✅ **Add new actions** - Add to plugin, extend VA command once
✅ **Users never lose keybinds** - Command wrapper stays the same

This is the pattern for converting complex game action commands!
