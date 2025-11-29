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
        
        # Primary: installed version location - ONLY use this for installed version
        installed_config = os.path.join(parent_dir, "config.json")
        possible_paths.append(installed_config)
        
        # NOTE: Removed dev fallback to prevent accidentally loading wrong config
    else:
        # Running in development mode - always use dev folder config
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dev_config = os.path.join(script_dir, "config.json")
        possible_paths.append(dev_config)
    
    # Use the first existing config file, or the first path for new installs
    for path in possible_paths:
        if os.path.exists(path):
            print(f"[CONFIG] Using config file: {path}")
            return path
    
    # If no existing config found, use the first path (installed > development)
    result_path = possible_paths[0] if possible_paths else os.path.join(os.path.expanduser("~"), "Documents", "EliteMining", "config.json")
    print(f"[CONFIG] No existing config found, will create: {result_path}")
    return result_path

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
    global _cached_config, _last_load_time
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
        
        # Update cache immediately after save
        _cached_config = cfg.copy()
        _last_load_time = time.time()
            
        # Only log verification if there's an issue
        if not os.path.exists(CONFIG_FILE):
            log.error(f"Config file was not created: {CONFIG_FILE}")
        elif os.path.getsize(CONFIG_FILE) == 0:
            log.error(f"Config file is empty: {CONFIG_FILE}")
            
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

def load_ring_finder_filters() -> Dict[str, Any]:
    """Load ring finder filter settings from config"""
    cfg = _load_cfg()
    return cfg.get("ring_finder_filters", {})

def save_ring_finder_filters(filters: Dict[str, Any]) -> None:
    """Save ring finder filter settings to config"""
    cfg = _load_cfg()
    cfg["ring_finder_filters"] = filters
    _save_cfg(cfg)

def load_mining_analysis_column_widths() -> Dict[str, int]:
    """Load Mining Analysis table column widths from config"""
    cfg = _load_cfg()
    return cfg.get("mining_analysis_column_widths", {})

def save_mining_analysis_column_widths(widths: Dict[str, int]) -> None:
    """Save Mining Analysis table column widths to config"""
    cfg = _load_cfg()
    cfg["mining_analysis_column_widths"] = widths
    _save_cfg(cfg)

def load_bookmarks_column_widths() -> Dict[str, int]:
    """Load Mining Bookmarks table column widths from config"""
    cfg = _load_cfg()
    return cfg.get("bookmarks_column_widths", {})

def save_bookmarks_column_widths(widths: Dict[str, int]) -> None:
    """Save Mining Bookmarks table column widths to config"""
    cfg = _load_cfg()
    cfg["bookmarks_column_widths"] = widths
    _save_cfg(cfg)

def load_ring_finder_column_widths() -> Dict[str, int]:
    """Load Ring Finder table column widths from config"""
    cfg = _load_cfg()
    return cfg.get("ring_finder_column_widths", {})

def save_ring_finder_column_widths(widths: Dict[str, int]) -> None:
    """Save Ring Finder table column widths to config"""
    cfg = _load_cfg()
    cfg["ring_finder_column_widths"] = widths
    _save_cfg(cfg)

def load_commodity_market_column_widths() -> Dict[str, int]:
    """Load Commodity Market table column widths from config"""
    cfg = _load_cfg()
    return cfg.get("commodity_market_column_widths", {})

def save_commodity_market_column_widths(widths: Dict[str, int]) -> None:
    """Save Commodity Market table column widths to config"""
    cfg = _load_cfg()
    cfg["commodity_market_column_widths"] = widths
    _save_cfg(cfg)

def load_prospector_report_column_widths() -> Dict[str, int]:
    """Load Prospector Report table column widths from config"""
    cfg = _load_cfg()
    return cfg.get("prospector_report_column_widths", {})

def save_prospector_report_column_widths(widths: Dict[str, int]) -> None:
    """Save Prospector Report table column widths to config"""
    cfg = _load_cfg()
    cfg["prospector_report_column_widths"] = widths
    _save_cfg(cfg)

def load_mineral_analysis_column_widths() -> Dict[str, int]:
    """Load Mineral Analysis table column widths from config"""
    cfg = _load_cfg()
    return cfg.get("mineral_analysis_column_widths", {})

def save_mineral_analysis_column_widths(widths: Dict[str, int]) -> None:
    """Save Mineral Analysis table column widths to config"""
    cfg = _load_cfg()
    cfg["mineral_analysis_column_widths"] = widths
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
    
    # Add API upload fields if missing
    api_fields_added = []
    if "api_upload_enabled" not in config:
        config["api_upload_enabled"] = False
        api_fields_added.append("api_upload_enabled")
    if "api_endpoint_url" not in config:
        config["api_endpoint_url"] = "https://elitemining.example.com"
        api_fields_added.append("api_endpoint_url")
    if "api_key" not in config:
        config["api_key"] = ""
        api_fields_added.append("api_key")
    if "cmdr_name_for_api" not in config:
        config["cmdr_name_for_api"] = ""
        api_fields_added.append("cmdr_name_for_api")
    
    if api_fields_added:
        log.info(f"Added API upload fields: {', '.join(api_fields_added)}")
    
    # Add Distance Calculator fields if missing
    distance_fields_added = []
    if "home_system" not in config:
        config["home_system"] = ""
        distance_fields_added.append("home_system")
    if "fleet_carrier_system" not in config:
        config["fleet_carrier_system"] = ""
        distance_fields_added.append("fleet_carrier_system")
    if "distance_calculator_system_a" not in config:
        config["distance_calculator_system_a"] = ""
        distance_fields_added.append("distance_calculator_system_a")
    if "distance_calculator_system_b" not in config:
        config["distance_calculator_system_b"] = ""
        distance_fields_added.append("distance_calculator_system_b")
    
    if distance_fields_added:
        log.info(f"Added Distance Calculator fields: {', '.join(distance_fields_added)}")
    
    log.info(f"Config migration completed successfully from {original_version} to {target_version}")
    return config


# API Upload Configuration
def load_api_upload_enabled() -> bool:
    """Load API upload enabled state from config"""
    cfg = _load_cfg()
    return cfg.get("api_upload_enabled", False)

def save_api_upload_enabled(enabled: bool) -> None:
    """Save API upload enabled state to config"""
    cfg = _load_cfg()
    cfg["api_upload_enabled"] = enabled
    _save_cfg(cfg)

def load_api_endpoint_url() -> str:
    """Load API endpoint URL from config"""
    cfg = _load_cfg()
    return cfg.get("api_endpoint_url", "https://elitemining.example.com")

def save_api_endpoint_url(url: str) -> None:
    """Save API endpoint URL to config (validates URL format)"""
    url = url.strip().rstrip('/')
    if url and not (url.startswith('http://') or url.startswith('https://')):
        raise ValueError("URL must start with http:// or https://")
    cfg = _load_cfg()
    cfg["api_endpoint_url"] = url
    _save_cfg(cfg)

def load_api_key() -> str:
    """Load API key from config"""
    cfg = _load_cfg()
    return cfg.get("api_key", "")

def save_api_key(key: str) -> None:
    """Save API key to config"""
    cfg = _load_cfg()
    cfg["api_key"] = key.strip()
    _save_cfg(cfg)

def load_cmdr_name_for_api() -> str:
    """Load Commander name for API from config"""
    cfg = _load_cfg()
    return cfg.get("cmdr_name_for_api", "")

def save_cmdr_name_for_api(name: str) -> None:
    """Save Commander name for API to config"""
    cfg = _load_cfg()
    cfg["cmdr_name_for_api"] = name.strip()
    _save_cfg(cfg)

def load_api_upload_settings() -> Dict[str, Any]:
    """Load all API upload settings as a dict"""
    cfg = _load_cfg()
    return {
        "enabled": cfg.get("api_upload_enabled", False),
        "endpoint_url": cfg.get("api_endpoint_url", "https://elitemining.example.com"),
        "api_key": cfg.get("api_key", ""),
        "cmdr_name": cfg.get("cmdr_name_for_api", "")
    }

def save_api_upload_settings(settings: Dict[str, Any]) -> None:
    """Save all API upload settings from a dict"""
    cfg = _load_cfg()
    if "enabled" in settings:
        cfg["api_upload_enabled"] = settings["enabled"]
    if "endpoint_url" in settings:
        url = settings["endpoint_url"].strip().rstrip('/')
        if url and not (url.startswith('http://') or url.startswith('https://')):
            raise ValueError("URL must start with http:// or https://")
        cfg["api_endpoint_url"] = url
    if "api_key" in settings:
        cfg["api_key"] = settings["api_key"].strip()
    if "cmdr_name" in settings:
        cfg["cmdr_name_for_api"] = settings["cmdr_name"].strip()
    _save_cfg(cfg)


# Distance Calculator Configuration
def load_home_system() -> str:
    """Load home system from config"""
    cfg = _load_cfg()
    return cfg.get("home_system", "")

def save_home_system(system_name: str) -> None:
    """Save home system to config"""
    cfg = _load_cfg()
    cfg["home_system"] = system_name.strip()
    _save_cfg(cfg)

def load_fleet_carrier_system() -> str:
    """Load fleet carrier system from config"""
    cfg = _load_cfg()
    return cfg.get("fleet_carrier_system", "")

def save_fleet_carrier_system(system_name: str) -> None:
    """Save fleet carrier system to config"""
    cfg = _load_cfg()
    cfg["fleet_carrier_system"] = system_name.strip()
    _save_cfg(cfg)

def load_distance_calculator_systems() -> tuple:
    """Load System A and System B from config"""
    cfg = _load_cfg()
    system_a = cfg.get("distance_calculator_system_a", "")
    system_b = cfg.get("distance_calculator_system_b", "")
    return system_a, system_b

def save_distance_calculator_systems(system_a: str, system_b: str) -> None:
    """Save System A and System B to config"""
    cfg = _load_cfg()
    cfg["distance_calculator_system_a"] = system_a.strip()
    cfg["distance_calculator_system_b"] = system_b.strip()
    _save_cfg(cfg)

# Theme settings
def load_theme() -> str:
    """Load current theme setting. Default is 'elite_orange'."""
    cfg = _load_cfg()
    return cfg.get("theme", "elite_orange")

def save_theme(theme: str) -> None:
    """Save theme setting"""
    cfg = _load_cfg()
    cfg["theme"] = theme
    _save_cfg(cfg)

def load_sidebar_sash_position() -> Optional[int]:
    """Load saved sidebar sash position (Ship Presets / Cargo Monitor split)"""
    cfg = _load_cfg()
    return cfg.get("sidebar_sash_position")

def save_sidebar_sash_position(position: int) -> None:
    """Save sidebar sash position"""
    cfg = _load_cfg()
    cfg["sidebar_sash_position"] = position
    _save_cfg(cfg)

def load_main_sash_position() -> Optional[int]:
    """Load saved main horizontal sash position (content / sidebar split)"""
    cfg = _load_cfg()
    return cfg.get("main_sash_position")

def save_main_sash_position(position: int) -> None:
    """Save main horizontal sash position"""
    cfg = _load_cfg()
    cfg["main_sash_position"] = position
    _save_cfg(cfg)
