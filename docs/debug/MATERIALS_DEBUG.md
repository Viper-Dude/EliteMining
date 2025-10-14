# Materials Tracking Debug Guide

## Debug Logging Added

The following debug messages will now appear in the console:

### 1. When ANY MaterialCollected event is found
```
[DEBUG] Processing MaterialCollected event: {...}
```

### 2. When processing the event
```
[MaterialCollected] Category: Raw, Material: Iron, Count: 2
```

### 3. If material is in tracked list (SUCCESS)
```
[MaterialCollected] ✓ Added 2x Iron (Total: 2)
[MaterialCollected] Current materials dict: {'Iron': 2}
[MaterialCollected] Updated popup window display (if window open)
[MaterialCollected] Called update_callback for integrated display
```

### 4. If material NOT in tracked list (FAILURE)
```
[MaterialCollected] ✗ Material 'SomeMaterial' not in tracked list
[MaterialCollected] Available materials: ['Antimony', 'Arsenic', 'Boron', ...]
```

### 5. If category is not "Raw" (SKIPPED)
```
[MaterialCollected] ✗ Skipping non-Raw category: Manufactured
```

## Testing Steps

1. **Start EliteMining** - Watch console for startup messages
2. **Start a mining session** (click Start button)
3. **Mine asteroids** that contain Iron or Nickel
4. **Collect the fragments** (scoop them up)
5. **Watch the console** for MaterialCollected messages

## What to Look For

### GOOD Signs (Working):
- See `[DEBUG] Processing MaterialCollected` messages
- See `✓ Added` messages
- Materials dict shows non-zero values
- Cargo Monitor shows "Engineering Materials" section

### BAD Signs (Not Working):
- NO `[DEBUG] Processing MaterialCollected` messages = Journal not being monitored
- `✗ Material not in tracked list` = Name mismatch
- `✗ Skipping non-Raw category` = Wrong material type
- `WARNING: No update_callback registered!` = Display update broken

## Common Issues

### Issue 1: No debug messages at all
**Cause**: Journal monitoring not running
**Fix**: Check if journal_dir is correct in console output

### Issue 2: Material name not in list
**Cause**: Elite uses different name format
**Example**: Journal might say "iron" but we're looking for "Iron"
**Fix**: Case-insensitive matching needed

### Issue 3: Materials tracked but not displayed
**Cause**: Display update not triggered
**Check**: Look for "Called update_callback" message

## Expected Journal Event Format

```json
{
  "timestamp": "2025-10-14T12:34:56Z",
  "event": "MaterialCollected",
  "Category": "Raw",
  "Name": "iron",
  "Name_Localised": "Iron",
  "Count": 2
}
```

## Tracked Materials List

All 22 materials that should be tracked:
- Antimony (G2)
- Arsenic (G2)
- Boron (G3)
- Cadmium (G3)
- Carbon (G1)
- Chromium (G2)
- Germanium (G2)
- **Iron (G1)** ← You're mining this
- Lead (G1)
- Manganese (G2)
- **Nickel (G1)** ← You're mining this
- Niobium (G3)
- Phosphorus (G1)
- Polonium (G4)
- Rhenium (G1)
- Selenium (G4)
- Sulphur (G1)
- Tin (G3)
- Tungsten (G3)
- Vanadium (G2)
- Zinc (G2)
- Zirconium (G2)

## Next Steps

Run EliteMining, mine some materials, and **paste the console output** here so we can see exactly what's happening!
