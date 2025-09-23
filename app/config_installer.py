"""
Config Migration Handler for EliteMining Installer

This script determines whether to overwrite config.json during installation
based on breaking changes and provides migration capabilities.
"""

import os
import sys
import json
import shutil
from pathlib import Path

def main():
    """
    Main installer config handler
    
    Returns exit codes:
    0: Success - config handled appropriately
    1: Error occurred
    2: User config preserved (no overwrite needed)
    3: Config overwritten due to breaking changes
    """
    
    if len(sys.argv) < 3:
        print("Usage: config_installer.py <source_config.json> <target_directory>")
        return 1
    
    source_config = Path(sys.argv[1])
    target_dir = Path(sys.argv[2])
    target_config = target_dir / "config.json"
    
    try:
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Load new config from installer
        with open(source_config, 'r', encoding='utf-8') as f:
            new_config = json.load(f)
        
        # Check if existing config exists and is valid
        if target_config.exists():
            try:
                with open(target_config, 'r', encoding='utf-8') as f:
                    existing_config = json.load(f)
                
                # Check if migration is needed
                if needs_migration(existing_config, new_config):
                    print("Config migration needed - preserving user settings where possible")
                    
                    # Backup existing config
                    backup_path = target_config.with_suffix('.json.backup')
                    shutil.copy2(target_config, backup_path)
                    print(f"Backed up existing config to: {backup_path}")
                    
                    # Migrate config
                    migrated_config = migrate_user_config(existing_config, new_config)
                    
                    # Write migrated config
                    with open(target_config, 'w', encoding='utf-8') as f:
                        json.dump(migrated_config, f, indent=2)
                    
                    print("Config successfully migrated with preserved user settings")
                    return 3  # Config was overwritten due to migration
                else:
                    print("Existing config is compatible - preserving user settings")
                    return 2  # Config preserved, no changes needed
                    
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Existing config is corrupted: {e}")
                print("Installing fresh config")
        else:
            print("No existing config found - installing fresh config")
        
        # Install fresh config (first install or corrupted existing)
        shutil.copy2(source_config, target_config)
        print(f"Fresh config installed to: {target_config}")
        return 0
        
    except Exception as e:
        print(f"Error handling config: {e}")
        return 1


def needs_migration(existing_config: dict, new_config: dict) -> bool:
    """Check if existing config needs migration"""
    
    # Version check
    existing_version = existing_config.get("config_version", "0.0.0")
    new_version = new_config.get("config_version", "0.0.0")
    
    if existing_version != new_version:
        return True
    
    # Structure check - look for breaking changes
    breaking_changes = [
        # Preset system
        ("announce_preset_1", dict),
        ("announce_preset_2", dict), 
        ("announce_preset_3", dict),
        ("announce_preset_4", dict),
        ("announce_preset_5", dict),
        ("last_material_settings", dict),
    ]
    
    for key, expected_type in breaking_changes:
        if key not in existing_config:
            return True
        if not isinstance(existing_config[key], expected_type):
            return True
    
    # Check preset structure for Core/Non-Core fields
    for i in range(1, 6):
        preset_key = f"announce_preset_{i}"
        if preset_key in existing_config:
            preset = existing_config[preset_key]
            if not isinstance(preset, dict):
                return True
            if "Core Asteroids" not in preset or "Non-Core Asteroids" not in preset:
                return True
    
    return False


def migrate_user_config(existing_config: dict, new_config: dict) -> dict:
    """Migrate existing config to new structure while preserving user settings"""
    
    # Start with new config structure
    migrated = new_config.copy()
    
    # Preserve user settings that are safe to keep
    safe_to_preserve = [
        "tts_volume", "va_folder", "window", "text_overlay_enabled",
        "text_overlay_transparency", "text_overlay_color", "text_overlay_position",
        "text_overlay_size", "text_overlay_duration", "stay_on_top", "tts_voice",
        "announcements", "cargo_monitor_enabled", "cargo_monitor_position",
        "cargo_monitor_transparency", "tooltips_enabled"
    ]
    
    for key in safe_to_preserve:
        if key in existing_config:
            migrated[key] = existing_config[key]
    
    # Handle announce_map and min_pct_map migration 
    if "announce_map" in existing_config:
        # Distribute to all presets if they don't have their own
        for i in range(1, 6):
            preset_key = f"announce_preset_{i}"
            if preset_key in migrated:
                if not migrated[preset_key].get("announce_map"):
                    migrated[preset_key]["announce_map"] = existing_config["announce_map"].copy()
    
    if "min_pct_map" in existing_config:
        for i in range(1, 6):
            preset_key = f"announce_preset_{i}"
            if preset_key in migrated:
                if not migrated[preset_key].get("min_pct_map"):
                    migrated[preset_key]["min_pct_map"] = existing_config["min_pct_map"].copy()
    
    # Preserve last_material_settings if it exists and is valid
    if "last_material_settings" in existing_config:
        last_settings = existing_config["last_material_settings"]
        if isinstance(last_settings, dict):
            # Merge with new structure
            new_last_settings = migrated.get("last_material_settings", {})
            for key in ["announce_map", "min_pct_map", "announce_threshold"]:
                if key in last_settings:
                    new_last_settings[key] = last_settings[key]
            
            # Set default Core/Non-Core if not present
            if "Core Asteroids" not in new_last_settings:
                new_last_settings["Core Asteroids"] = last_settings.get("Core Asteroids", True)
            if "Non-Core Asteroids" not in new_last_settings:
                new_last_settings["Non-Core Asteroids"] = last_settings.get("Non-Core Asteroids", False)
            
            migrated["last_material_settings"] = new_last_settings
    
    print("User settings preserved during migration")
    return migrated


if __name__ == "__main__":
    sys.exit(main())