# VoiceAttack Keybind Export/Import Commands

## Overview
These commands allow automatic backup and restore of keybinds during profile updates.

## Required Commands to Add

### 1. Export All Keybinds Command

**Command Name:** `((Export All Keybinds))`  
**Spoken Phrase:** Leave blank (internal only)  
**Description:** Exports all command keybinds to JSON file

**Actions:**

```
1. Set Text [EM.ExportData] to ''
2. Set Integer [EM.CommandCount] to 0

3. Begin Loop While: [{STATE_ACTIVEPROFILE}] Does Not Equal ''
   
   // For each command in profile, check if it has keybinds
   // This pseudo-code shows the logic - actual implementation
   // would use VA's built-in command listing if available
   
   4. Get command shortcut info
   5. If shortcut exists:
      6. Append to [EM.ExportData]: 
         {
           "command": "{CMDNAME}",
           "keyboard": "{KEYVALUE}",
           "joystick": "{JOYSTICKVALUE}",
           "mouse": "{MOUSEVALUE}"
         },
      7. Set Integer [EM.CommandCount] to [{EM.CommandCount}] + 1
   
8. End Loop

9. Write [EM.ExportData] to file: 
   {VA_APPS}\EliteMining\Variables\elitemining_keybinds.json

10. Write 'SUCCESS' to file:
    {VA_APPS}\EliteMining\Variables\keybind_export_status.txt
```

### 2. Import All Keybinds Command

**Command Name:** `((Import All Keybinds))`  
**Spoken Phrase:** Leave blank (internal only)  
**Description:** Imports keybinds from JSON and applies to commands

**Actions:**

```
1. Read file: {VA_APPS}\EliteMining\Variables\elitemining_keybinds.json
   into [EM.ImportData]

2. Set Integer [EM.ImportCount] to 0

3. Begin Loop: Parse JSON array

   4. Get command name, keyboard, joystick, mouse values
   
   5. If command exists in profile:
      6. Set command keyboard shortcut
      7. Set command joystick shortcut  
      8. Set command mouse shortcut
      9. Set Integer [EM.ImportCount] to [{EM.ImportCount}] + 1
   
10. End Loop

11. Write 'SUCCESS' to file:
    {VA_APPS}\EliteMining\Variables\keybind_import_status.txt
```

## Problem: VA Doesn't Have Direct Command Property Access!

**Unfortunately**, VoiceAttack's command actions **cannot directly read or set shortcuts** from other commands. The commands would need to be edited manually or through external means.

## Alternative Solution: Use External JSON + Manual Reassignment

Since VA can't programmatically set shortcuts, we need a different approach:

### **Option A: VA Inline Functions (C# Code)**

Create an inline function that uses reflection or VA's internal APIs to:
- Read command shortcuts
- Write to JSON
- Read from JSON
- Apply shortcuts

### **Option B: Use Variables File + Python Does the Work**

1. Python extracts keybinds from .VAP file (XML) ✅ Already done!
2. Python saves keybinds
3. Python applies keybinds to new .VAP file ✅ Already done!
4. User imports updated .VAP ✅ Already done!

**We already have this working!** The plugin/command approach adds unnecessary complexity.

## Recommendation

**Stick with the XML-based approach** we already built, but make the user experience better:

1. EliteMining automatically exports profile as XML when needed
2. Process keybinds in Python
3. Show user notification with import button
4. One-click import

This is simpler and more reliable than trying to use VA commands/plugin.
