import os
import sys
import json
import logging
import time
from typing import Dict, Any, Optional
VA_TTS_ANNOUNCEMENT = "ttsProspectorAnnouncement"

# Rate limiting for config loading
_last_load_time = 0
_cached_config = {}

# Get the correct config file path based on execution context
def _get_config_path() -> str:
    # Always try to use a shared config location for consistency
    # Priority: 1) Installed location, 2) Development location, 3) User Documents
    
    possible_paths = []
    
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_dir = os.path.dirname(sys.executable)  # .../Configurator
        parent_dir = os.path.dirname(exe_dir)      # .../EliteMining
        
        # Primary: installed version location
        installed_config = os.path.join(parent_dir, "config.json")
        possible_paths.append(installed_config)
        
        # Fallback: check for development config to migrate settings
        dev_build_config = os.path.join(parent_dir, "app", "config.json")
        possible_paths.append(dev_build_config)
    else:
        # Running in development mode - always use dev folder config
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dev_config = os.path.join(script_dir, "config.json")
        possible_paths.append(dev_config)
    
    # Use the first existing config file, or the first path for new installs
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # If no existing config found, use the first path (installed > development)
    return possible_paths[0] if possible_paths else os.path.join(os.path.expanduser("~"), "Documents", "EliteMining", "config.json")

CONFIG_FILE = _get_config_path()
log = logging.getLogger("EliteMining.Config")

def _load_cfg() -> Dict[str, Any]:
    global _last_load_time, _cached_config
    now = time.time()
    
    # Only reload if more than 2 seconds have passed
    if now - _last_load_time < 2.0 and _cached_config:
        return _cached_config.copy()
    
    _last_load_time = now
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _cached_config = data
                return data
        except Exception as e:
            log.warning(f"Failed to load config from {CONFIG_FILE}: {e}")
    else:
        log.warning(f"Config file not found: {CONFIG_FILE}")
    
    _cached_config = {}
    return {}

def _save_cfg(cfg: Dict[str, Any]) -> None:
    try:
        # Ensure the directory exists
        config_dir = os.path.dirname(CONFIG_FILE)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)
            log.info(f"Created config directory: {config_dir}")
        
        # Single concise log message instead of 3 verbose ones
        log.info(f"Config saved (v{cfg.get('config_version', 'MISSING')}): {os.path.basename(CONFIG_FILE)}")
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
            
        # Only log verification if there's an issue
        if not os.path.exists(CONFIG_FILE):
            log.error(f"Config file was not created: {CONFIG_FILE}")
        elif os.path.getsize(CONFIG_FILE) == 0:
            log.error(f"Config file is empty: {CONFIG_FILE}")
        else:
            log.error(f"Config file does not exist after save!")
            
    except Exception as e:
        log.exception("Failed saving config: %s", e)

def update_config_value(key: str, value: Any) -> None:
    """Update a single config key without affecting other values"""
    cfg = _load_cfg()
    cfg[key] = value
    _save_cfg(cfg)

def update_config_values(updates: Dict[str, Any]) -> None:
    """Update multiple config keys without affecting other values"""
    cfg = _load_cfg()
    cfg.update(updates)
    _save_cfg(cfg)

def load_saved_va_folder() -> Optional[str]:
    cfg = _load_cfg()
    p = cfg.get("va_folder")
    return p if p and os.path.isdir(p) else None

def save_va_folder(folder: str) -> None:
    cfg = _load_cfg()
    cfg["va_folder"] = folder
    _save_cfg(cfg)

def load_window_geometry() -> Dict[str, Any]:
    cfg = _load_cfg()
    return cfg.get("window", {})

def save_window_geometry(geom: Dict[str, Any]) -> None:
    cfg = _load_cfg()
    cfg["window"] = geom
    _save_cfg(cfg)

def load_cargo_window_position() -> Dict[str, int]:
    """Load cargo monitor window position from config"""
    cfg = _load_cfg()
    return cfg.get("cargo_window", {"x": 100, "y": 100})

def save_cargo_window_position(x: int, y: int) -> None:
    """Save cargo monitor window position to config"""
    cfg = _load_cfg()
    cfg["cargo_window"] = {"x": x, "y": y}
    _save_cfg(cfg)


# --- Safe text write (atomic) ---
def _atomic_write_text(path: str, text: str) -> None:
    try:
        folder = os.path.dirname(path) or "."
        os.makedirs(folder, exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, path)
    except Exception as e:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        log.exception("Atomic write failed for %s: %s", path, e)


# --- Config Migration System ---
def needs_config_migration(config: Dict[str, Any]) -> bool:
    """Check if config needs migration based on version or missing required fields"""
    from version import get_config_version
    
    current_config_version = get_config_version()
    file_config_version = config.get("config_version", "0.0.0")
    
    # Force migration for versions before 4.3.6
    if file_config_version in ["4.1.7", "4.1.8"]:
        log.info(f"Forcing migration from {file_config_version} to {current_config_version}")
        return True
    
    # Version-based migration check
    if file_config_version != current_config_version:
        log.info(f"Config version mismatch: file={file_config_version}, current={current_config_version}")
        return True
    
    # Structure-based migration check (for critical new fields)
    required_fields = [
        "announce_preset_1", "announce_preset_2", "announce_preset_3", 
        "announce_preset_4", "announce_preset_5", "last_material_settings"
    ]
    
    for field in required_fields:
        if field not in config:
            log.info(f"Missing required field: {field}")
            return True
    
    # Check if presets have Core/Non-Core fields (recent addition)
    for i in range(1, 6):
        preset_key = f"announce_preset_{i}"
        if preset_key in config:
            preset_data = config[preset_key]
            if "Core Asteroids" not in preset_data or "Non-Core Asteroids" not in preset_data:
                log.info(f"Preset {i} missing Core/Non-Core asteroid fields")
                return True
    
    return False


def should_overwrite_config() -> bool:
    """
    Determine if installer should overwrite existing config.json
    
    Returns:
        True: Overwrite (breaking changes need migration)
        False: Preserve existing config (safe to keep user settings)
    """
    try:
        existing_config = _load_cfg()
        return needs_config_migration(existing_config)
    except Exception as e:
        log.warning(f"Could not check existing config: {e}")
        return True  # If we can't read it, safer to overwrite


def migrate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Migrate config to current version, preserving user settings where possible"""
    import logging
    from datetime import datetime
    from version import get_config_version
    
    log = logging.getLogger("EliteMining.Migration")
    log.info(f"Starting config migration at {datetime.now().isoformat()}")
    
    original_version = config.get("config_version", "unknown")
    target_version = get_config_version()
    log.info(f"Migrating from {original_version} to {target_version}")
    
    # Add version field if missing
    config["config_version"] = target_version
    log.info(f"Updated config_version to {target_version}")
    
    # Add missing presets with defaults
    default_preset_structure = {
        "announce_map": {},
        "min_pct_map": {},
        "announce_threshold": 20.0,
        "Core Asteroids": True,
        "Non-Core Asteroids": True
    }
    
    presets_added = 0
    for i in range(1, 6):
        preset_key = f"announce_preset_{i}"
        if preset_key not in config:
            config[preset_key] = default_preset_structure.copy()
            presets_added += 1
        else:
            # Ensure Core/Non-Core fields exist in existing presets
            if "Core Asteroids" not in config[preset_key]:
                config[preset_key]["Core Asteroids"] = (i % 2 == 1)  # Alternate defaults
                log.info(f"Added Core Asteroids field to preset {i}")
            if "Non-Core Asteroids" not in config[preset_key]:
                config[preset_key]["Non-Core Asteroids"] = (i % 2 == 0)
                log.info(f"Added Non-Core Asteroids field to preset {i}")
    
    
    # Ensure last_material_settings exists and has Core/Non-Core fields
    if "last_material_settings" not in config:
        config["last_material_settings"] = {
            "announce_map": {},
            "min_pct_map": {},
            "announce_threshold": 20.0,
            "Core Asteroids": True,
            "Non-Core Asteroids": False
        }
        log.info("Added missing last_material_settings configuration")
    else:
        last_settings = config["last_material_settings"]
        if "Core Asteroids" not in last_settings:
            last_settings["Core Asteroids"] = True
            log.info("Added Core Asteroids field to last_material_settings")
        if "Non-Core Asteroids" not in last_settings:
            last_settings["Non-Core Asteroids"] = False
            log.info("Added Non-Core Asteroids field to last_material_settings")
    
    # Add Tritium to all presets and main announce/min_pct maps
    materials_added = []
    if "announce_map" in config and "Tritium" not in config["announce_map"]:
        config["announce_map"]["Tritium"] = True
        materials_added.append("Tritium")
    if "min_pct_map" in config and "Tritium" not in config["min_pct_map"]:
        config["min_pct_map"]["Tritium"] = 20.0
    
    # Add Tritium to all saved presets
    for i in range(1, 6):
        preset_key = f"announce_preset_{i}"
        if preset_key in config:
            if "announce_map" in config[preset_key] and "Tritium" not in config[preset_key]["announce_map"]:
                config[preset_key]["announce_map"]["Tritium"] = True
            if "min_pct_map" in config[preset_key] and "Tritium" not in config[preset_key]["min_pct_map"]:
                config[preset_key]["min_pct_map"]["Tritium"] = 20.0
    
    # Add Tritium to last_material_settings
    if "last_material_settings" in config:
        if "announce_map" in config["last_material_settings"] and "Tritium" not in config["last_material_settings"]["announce_map"]:
            config["last_material_settings"]["announce_map"]["Tritium"] = True
        if "min_pct_map" in config["last_material_settings"] and "Tritium" not in config["last_material_settings"]["min_pct_map"]:
            config["last_material_settings"]["min_pct_map"]["Tritium"] = 20.0
    
    # Add Coltan to all presets and main announce/min_pct maps
    if "announce_map" in config and "Coltan" not in config["announce_map"]:
        config["announce_map"]["Coltan"] = True
        materials_added.append("Coltan")
    if "min_pct_map" in config and "Coltan" not in config["min_pct_map"]:
        config["min_pct_map"]["Coltan"] = 20.0
    
    # Add Coltan to all saved presets
    for i in range(1, 6):
        preset_key = f"announce_preset_{i}"
        if preset_key in config:
            if "announce_map" in config[preset_key] and "Coltan" not in config[preset_key]["announce_map"]:
                config[preset_key]["announce_map"]["Coltan"] = True
            if "min_pct_map" in config[preset_key] and "Coltan" not in config[preset_key]["min_pct_map"]:
                config[preset_key]["min_pct_map"]["Coltan"] = 20.0
    
    # Add Coltan to last_material_settings
    if "last_material_settings" in config:
        if "announce_map" in config["last_material_settings"] and "Coltan" not in config["last_material_settings"]["announce_map"]:
            config["last_material_settings"]["announce_map"]["Coltan"] = True
        if "min_pct_map" in config["last_material_settings"] and "Coltan" not in config["last_material_settings"]["min_pct_map"]:
            config["last_material_settings"]["min_pct_map"]["Coltan"] = 20.0
    
    if materials_added:
        log.info(f"Added new materials: {', '.join(materials_added)}")
    
    # Add Discord integration fields if missing
    discord_fields_added = []
    if "discord_webhook_url" not in config:
        config["discord_webhook_url"] = "https://discord.com/api/webhooks/1431645227634131005/ZtoPZTa-_d1hYrP11FZbP_jBpb4nVo8e8HSMK3i33-7Nmu94wm7Xzc3GUEb2nPfr0DcO"
        discord_fields_added.append("discord_webhook_url")
    if "discord_enabled" not in config:
        config["discord_enabled"] = True
        discord_fields_added.append("discord_enabled")
    if "discord_username" not in config:
        config["discord_username"] = ""
        discord_fields_added.append("discord_username")
    
    if discord_fields_added:
        log.info(f"Added Discord integration fields: {', '.join(discord_fields_added)}")
    
    log.info(f"Config migration completed successfully from {original_version} to {target_version}")
    return config
