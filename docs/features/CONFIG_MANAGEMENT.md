# EliteMining Config Management System

## Overview

This system provides intelligent config.json management for EliteMining installations and updates. It ensures user settings are preserved when possible while enabling critical updates when the config structure changes.

## How It Works

### 1. Version Tracking

- **Config Version**: Each config.json has a `config_version` field matching the app version
- **Breaking Changes**: When config structure changes require migration, increment `__config_version__` in `version.py`

### 2. Migration Detection

The system checks for migration needs based on:

- **Version Mismatch**: File version != current app version
- **Missing Fields**: Required new fields (presets, Core/Non-Core asteroids, etc.)
- **Structure Changes**: Invalid field types or missing nested structures

### 3. Installer Behavior

#### **Preserve User Settings** (when config is compatible)

```text
- Existing config version matches current
- All required fields present
- No breaking structural changes
→ Result: Keep existing config untouched
```

#### **Intelligent Migration** (when updates needed)

```text
- Config version outdated or missing fields
- Backup original → Migrate settings → Install updated config
→ Result: New structure + preserved user preferences
```

#### **Fresh Install** (no existing config)

```text
- Install new config.json with current version
→ Result: Clean default configuration
```

## Files and Components

### Core Files

- **`version.py`**: Contains `__config_version__` - increment when config structure changes
- **`config.py`**: Migration logic (`needs_config_migration`, `migrate_config`)
- **`config_installer.py`**: Standalone Python migration script for installers
- **`config_installer.bat`**: Fallback batch script when Python unavailable

### Installer Integration

- **`EliteMiningInstaller.iss`**: Inno Setup script with smart config handling
- Tries Python migration first, falls back to batch script
- Only overwrites config when migration needed

### Application Integration

- **`main.py`**: App startup checks config and migrates if needed
- Handles cases where installer didn't run migration
- Creates backups before migration

## When to Update Config Version

### Increment `__config_version__` when you add

- ✅ New required fields to root config
- ✅ New preset structure changes  
- ✅ Changes to announcement system structure
- ✅ Breaking changes to existing field formats

### Safe changes (no version increment needed)

- ✅ New optional fields with defaults
- ✅ Value changes to existing fields
- ✅ UI text or label updates
- ✅ Bug fixes that don't change structure

## Usage Examples

### For Regular Updates (v4.0.5)

```python
# version.py - no config changes needed
__version__ = "4.0.5"
__config_version__ = "4.0.4"  # Keep same - no breaking changes
```

→ **Result**: Installer preserves all user settings

### For Breaking Changes (v4.1.0)

```python
# version.py - new feature requires config migration
__version__ = "4.1.0"  
__config_version__ = "4.1.0"  # Increment - breaking changes

# config.py - add migration logic in migrate_config()
def migrate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing migration code ...
    
    # Add new feature migration
    if "new_feature_settings" not in config:
        config["new_feature_settings"] = {
            "enabled": True,
            "threshold": 50.0
        }
```

→ **Result**: Installer migrates config, preserves user settings where possible

## Benefits

1. **User-Friendly**: Settings preserved across updates automatically
2. **Developer-Friendly**: Clear system for handling breaking changes  
3. **Reliable**: Multiple fallback layers (Python → Batch → App startup)
4. **Safe**: Always creates backups before migration
5. **Flexible**: Supports both minor updates and major overhauls

## Migration Workflow

```text
1. User runs installer/update
2. System checks existing config version
3a. Compatible → Keep existing (exit)
3b. Needs migration → Backup → Migrate → Install new
4. App startup double-checks and migrates if needed
5. User retains settings + gets new features
```

This system ensures smooth updates while maintaining user customizations and enabling new features to be properly integrated.
