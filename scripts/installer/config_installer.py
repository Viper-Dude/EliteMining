"""
Config and Database Migration Handler for EliteMining Installer

This script determines whether to overwrite config.json and user_data.db during installation
based on breaking changes and provides migration capabilities.
"""

import os
import sys
import json
import shutil
import sqlite3
from pathlib import Path

def main():
    """
    Main installer config and database handler
    
    Usage: 
    config_installer.py config <source_config.json> <target_directory>
    config_installer.py database <source_db> <target_directory> <new_db_version>
    
    Returns exit codes:
    0: Success - file handled appropriately
    1: Error occurred
    2: User file preserved (no overwrite needed)
    3: File overwritten due to breaking changes
    """
    
    if len(sys.argv) < 4:
        print("Usage:")
        print("  config_installer.py config <source_config.json> <target_directory>")
        print("  config_installer.py database <source_db> <target_directory> <new_db_version>")
        return 1
    
    operation = sys.argv[1].lower()
    
    if operation == "config":
        return handle_config(sys.argv[2], sys.argv[3])
    elif operation == "database":
        if len(sys.argv) < 5:
            print("Database operation requires version parameter")
            return 1
        return handle_database(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(f"Unknown operation: {operation}")
        return 1


def handle_config(source_config_path: str, target_directory: str) -> int:
    """Handle config.json version checking and migration"""
    source_config = Path(source_config_path)
    target_dir = Path(target_directory)
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


def handle_database(source_db_path: str, target_directory: str, new_version: str) -> int:
    """Handle user_data.db version checking and replacement"""
    source_db = Path(source_db_path)
    target_dir = Path(target_directory)
    target_db = target_dir / "user_data.db"
    
    try:
        # Ensure target directory exists
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if existing database exists
        if target_db.exists():
            try:
                existing_version = get_database_version(target_db)
                print(f"Found existing database version: {existing_version}")
                print(f"New database version: {new_version}")
                
                if compare_versions(new_version, existing_version) > 0:
                    print("Database update required - backing up existing database")
                    
                    # Create backup
                    backup_path = target_db.parent / f"user_data_backup_{existing_version}.db"
                    shutil.copy2(target_db, backup_path)
                    print(f"Backup created: {backup_path}")
                    
                    # Copy new database
                    shutil.copy2(source_db, target_db)
                    
                    # Set new version in database
                    set_database_version(target_db, new_version)
                    
                    print("Database updated successfully")
                    return 3  # Overwritten
                else:
                    print("Database is current - no update needed")
                    return 2  # Preserved
                    
            except Exception as e:
                print(f"Error reading existing database version: {e}")
                print("Installing new database as fallback")
                # Fall through to new installation
        
        # New installation or fallback
        print("Installing new database")
        shutil.copy2(source_db, target_db)
        set_database_version(target_db, new_version)
        return 0  # Success
        
    except Exception as e:
        print(f"Error handling database: {e}")
        return 1


def get_database_version(db_path: Path) -> str:
    """Get version from database_version table"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if version table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='database_version'")
        if not cursor.fetchone():
            conn.close()
            return "1.0.0"  # Default for databases without version table
        
        # Get version
        cursor.execute("SELECT version FROM database_version ORDER BY version DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else "1.0.0"
        
    except Exception:
        return "1.0.0"  # Default if any error


def set_database_version(db_path: Path, version: str) -> None:
    """Set version in database_version table"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create version table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS database_version (
                version TEXT PRIMARY KEY,
                updated_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert or update version
        cursor.execute('''
            INSERT OR REPLACE INTO database_version (version, updated_date) 
            VALUES (?, datetime('now'))
        ''', (version,))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Warning: Could not set database version: {e}")


def compare_versions(version1: str, version2: str) -> int:
    """
    Compare two version strings
    Returns: 1 if version1 > version2, -1 if version1 < version2, 0 if equal
    """
    def normalize_version(v):
        return [int(x) for x in v.split('.')]
    
    v1_parts = normalize_version(version1)
    v2_parts = normalize_version(version2)
    
    # Pad shorter version with zeros
    max_len = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_len - len(v1_parts)))
    v2_parts.extend([0] * (max_len - len(v2_parts)))
    
    for v1, v2 in zip(v1_parts, v2_parts):
        if v1 > v2:
            return 1
        elif v1 < v2:
            return -1
    
    return 0


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
        "cargo_monitor_transparency", "tooltips_enabled", "discord_webhook_url",
        "discord_enabled", "discord_username"
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