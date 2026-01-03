# EliteMining Update Strategy - VAICOM Model

## Current Problem
- Updating VAP profile overwrites user's keybinds
- Binary VAP format can't be easily parsed
- XML format doesn't work with EliteVA

## Solution: Don't Update the Profile!

### VAICOM Approach (Proven)
1. **Profile installed once** - contains commands with user's keybinds
2. **Commands call plugin** - EliteMiningPlugin.dll
3. **Plugin executes app** - Python application
4. **Updates only touch:** Plugin DLL + Python app files
5. **Profile NEVER updated** = keybinds preserved forever!

## EliteMining Update Structure

### Files That NEVER Change (User Keeps Forever)
```
VoiceAttack Profiles/
└── EliteMining-Profile.vap  ← User's keybinds stay here
```

### Files That Get Updated
```
VoiceAttack/Apps/EliteMining/
├── EliteMiningPlugin.dll        ← Update this
├── app/                          ← Update all Python files
│   ├── *.py
│   ├── ui/
│   ├── core/
│   └── ...
├── Images/                       ← Update resources
├── localization/                 ← Update translations
└── config.json.template          ← Update template (not user's config)
```

### Files User Modified (Preserve)
```
VoiceAttack/Apps/EliteMining/
├── config.json          ← User's settings - DON'T OVERWRITE
├── Variables/           ← Runtime data - preserve
├── user_data.db         ← User's database - preserve
└── *.json               ← User's bookmarks/missions - preserve
```

## Update Workflow

### 1. Initial Installation
- Install VA profile with default commands
- Install plugin DLL
- Install Python app
- User customizes keybinds in VA profile

### 2. Subsequent Updates
```python
def update_elitemining():
    # Download new version
    new_version = download_latest_release()
    
    # Extract to temp
    extract_to_temp(new_version)
    
    # Update only app files
    update_files = [
        "EliteMiningPlugin.dll",
        "app/**/*.py",
        "Images/**/*",
        "localization/**/*"
    ]
    
    # Preserve user data
    preserve_files = [
        "config.json",
        "user_data.db",
        "*.json bookmarks/missions",
        "Variables/**/*"
    ]
    
    # Copy new files, skip preserved
    for file in update_files:
        copy_if_newer(file, skip=preserve_files)
    
    # Done! Profile and keybinds untouched
```

### 3. User Experience
1. App shows "Update available" notification
2. User clicks "Update"
3. App downloads and installs new files
4. User's profile, keybinds, settings all preserved
5. Restart VA to load new plugin

## Benefits

✅ **Zero keybind management** - Never touch profile
✅ **Works with binary VAP** - Don't need to parse it
✅ **EliteVA compatible** - Binary format works
✅ **User data preserved** - Config, database, bookmarks safe
✅ **Simple updates** - Just file replacement
✅ **Industry standard** - Same as VAICOM, HCS

## Implementation

1. Remove all VAP parsing/updating code
2. Create file-based updater
3. Preserve user data during updates
4. Show import dialog only for NEW installations

This is the **production-ready solution** that actually works!
