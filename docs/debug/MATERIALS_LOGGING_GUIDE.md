# Engineering Materials Debug Logging - User Guide

## Overview

Debug logging has been added to track the engineering materials counting issue. All debug messages are now written to log files in:

```
C:\Users\<YourUsername>\AppData\Local\EliteMining\logs\
```

## Log File Location

**Installer Version (Release):**
- Automatically logs to: `C:\Users\<YourUsername>\AppData\Local\EliteMining\logs\`
- One log file per session: `elitemining_2025-10-22_14-30-00.log`
- Keeps last 15 log files, auto-deletes older ones

**Development Version (VS Code):**
- Run test script first: `python test_materials_logging.py`
- This will show you the exact log file path
- Or check: `%LOCALAPPDATA%\EliteMining\logs\`

## What Gets Logged

### 1. Background Monitor Heartbeat (Every 60 seconds)
```
2025-10-22 14:35:00 [INFO] [HEARTBEAT] Background monitor alive - Materials: 3
```
- Proves the monitoring thread is still running
- Shows how many material types are currently tracked
- If this stops appearing → thread died

### 2. MaterialCollected Events (When you mine)
```
2025-10-22 14:35:15 [INFO] [MaterialCollected] Raw event data: Category=Raw, Name=iron, Count=2
2025-10-22 14:35:15 [INFO] [MaterialCollected] ✓ Added 2x Iron (Total: 5)
```
- Logs every material you collect
- Shows the raw journal data
- Confirms if it was added to the counter

### 3. Journal File Rotation (Daily)
```
2025-10-22 14:40:00 [INFO] [JOURNAL_ROTATION] Detected new journal file: Journal.251022144000.01.log
```
- Logs when Elite creates a new journal file
- Confirms the app switched to reading the new file

### 4. Errors (If something goes wrong)
```
2025-10-22 14:45:00 [ERROR] [BACKGROUND_MONITOR] ERROR: Permission denied
<full traceback>
```
- Shows exactly what went wrong
- Includes full error details

## How to Review Logs

### Method 1: Open in Notepad
1. Press `Win + R`
2. Type: `%LOCALAPPDATA%\EliteMining\logs`
3. Press Enter
4. Open the most recent `.log` file

### Method 2: Use VS Code
1. In VS Code, open folder: `%LOCALAPPDATA%\EliteMining\logs`
2. Open the latest log file
3. Use Ctrl+F to search for:
   - `[HEARTBEAT]` - Check if monitor is alive
   - `[MaterialCollected]` - Check if materials are being tracked
   - `[ERROR]` - Find any errors

### Method 3: PowerShell (Live monitoring)
```powershell
# Watch the log file in real-time (like tail -f on Linux)
Get-Content "$env:LOCALAPPDATA\EliteMining\logs\elitemining_*.log" -Wait -Tail 20
```

## Troubleshooting Scenarios

### Scenario 1: Materials Stop Being Counted

**What to check in the log:**

1. **Is the heartbeat still appearing?**
   - Search for `[HEARTBEAT]`
   - Should appear every 60 seconds
   - If missing → background thread died

2. **Are MaterialCollected events appearing?**
   - Search for `[MaterialCollected]`
   - Should appear when you collect materials
   - If missing → Elite not writing journal events OR app not reading them

3. **Is there an ERROR message?**
   - Search for `[ERROR]`
   - Will show what broke

### Scenario 2: Journal File Rotation

**What to check:**
- Look for `[JOURNAL_ROTATION]`
- Should appear once per day (when Elite creates new journal)
- Confirms app detected the new file

### Scenario 3: Material Name Mismatch

**What to look for:**
```
[MaterialCollected] ✗ Material 'SomeWeirdName' not in tracked list
```
- Shows the exact name Elite is using
- Means we need to add it to MATERIAL_GRADES

## Testing the Logging

Run the test script to verify logging works:

```powershell
cd "D:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev"
.\.venv\Scripts\Activate.ps1
python test_materials_logging.py
```

This will:
1. Show you the log file path
2. Write test messages
3. Confirm logging is working

## What to Send for Bug Reports

If materials stop being counted, send me:

1. **The log file** from: `%LOCALAPPDATA%\EliteMining\logs\`
   - Most recent file
   - Or the file from when the problem occurred

2. **Time when it happened**
   - "Materials stopped being counted around 14:30"

3. **What you were doing**
   - "Mining in Borann A2 ring"
   - "After update"
   - "After PC woke from sleep"

## Log File Cleanup

- App keeps last **15 log files**
- Older files auto-deleted
- Each file ~1-5 MB (depends on session length)
- Total disk usage: ~15-75 MB

## Technical Details

**Log Levels:**
- `INFO` - Normal events (materials collected, heartbeat)
- `WARNING` - Potential issues (material not tracked, callback missing)
- `ERROR` - Critical errors (thread crash, file access denied)
- `DEBUG` - Verbose details (disabled by default for performance)

**Performance Impact:**
- Minimal (~0.1% CPU)
- Only logs important events
- Async file writing
- No impact on game performance

## Next Steps

1. ✅ Logging is now active
2. ✅ Run the app normally
3. ✅ Mine as usual
4. ⏱️ Wait for the issue to occur
5. 📁 Send me the log file

The log will reveal exactly what's happening when materials stop being counted!
