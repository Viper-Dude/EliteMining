"""
EliteMining Localization System

Provides centralized localization support for the application.
Supports multiple languages based on Elite Dangerous game language setting.

Usage:
    from localization import t, get_material, get_abbr, init
    
    # Initialize (call once at app startup)
    init(journal_dir)
    
    # Get translated UI string
    label_text = t("ring_finder.ring_type")  # "Ring Type" or "Ringtyp"
    
    # Get localized material name
    name = get_material("Platinum")  # "Platinum" or "Platin"
    
    # Get material abbreviation
    abbr = get_abbr("Platinum")  # "Plat" or "Plat"
    
    # Convert localized name back to English (for database)
    eng_name = to_english("Platin")  # "Platinum"
"""

import os
import sys
import json
import glob
from typing import Dict, Any, Optional

# =============================================================================
# MODULE STATE
# =============================================================================

_current_language: str = 'en'
_strings: Dict[str, Any] = {}
_materials: Dict[str, Any] = {}
_initialized: bool = False

# =============================================================================
# FILE PATHS
# =============================================================================

def _get_localization_dir() -> str:
    """Get the localization directory path"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        # Structure: {app}\Configurator\EliteMining.exe
        # Localization: {app}\app\localization\
        exe_dir = os.path.dirname(sys.executable)
        
        # Check multiple possible locations
        paths = [
            os.path.join(exe_dir, "localization"),  # Same folder as exe
            os.path.join(exe_dir, "app", "localization"),  # exe/app/localization
            os.path.join(os.path.dirname(exe_dir), "app", "localization"),  # parent/app/localization (installer structure)
        ]
        
        for path in paths:
            if os.path.exists(path) and os.path.isdir(path):
                # Verify JSON files exist
                json_files = glob.glob(os.path.join(path, "strings_*.json"))
                if json_files:
                    print(f"[localization] Found localization dir: {path}")
                    return path
        
        # Debug: print what we tried
        print(f"[localization] WARNING: Could not find localization directory")
        print(f"[localization] Exe dir: {exe_dir}")
        for path in paths:
            print(f"[localization] Tried: {path} - exists: {os.path.exists(path)}")
        
        return paths[-1]  # Return last option (installer structure) as fallback
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(__file__))

# =============================================================================
# LANGUAGE DETECTION
# =============================================================================

def detect_language(journal_dir: str = None) -> str:
    """
    Detect the game language from the most recent journal Fileheader.
    
    Args:
        journal_dir: Path to Elite Dangerous journal directory.
                     If None, uses default Saved Games location.
    
    Returns:
        Language code: 'en', 'de', 'fr', 'es', 'ru', 'pt'
        Defaults to 'en' if detection fails.
    """
    if not journal_dir:
        journal_dir = os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous")
    
    try:
        # Find most recent journal file
        journal_pattern = os.path.join(journal_dir, "Journal*.log")
        journal_files = glob.glob(journal_pattern)
        if not journal_files:
            return 'en'
        
        latest_journal = max(journal_files, key=os.path.getmtime)
        
        # Read first few lines to find Fileheader
        with open(latest_journal, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i > 10:  # Only check first 10 lines
                    break
                if '"event":"Fileheader"' in line or '"event": "Fileheader"' in line:
                    try:
                        data = json.loads(line)
                        language = data.get('language', 'English/UK')
                        return _parse_language_code(language)
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        print(f"[localization] Could not detect game language: {e}")
    
    return 'en'

def _parse_language_code(language_string: str) -> str:
    """Parse language code from Elite Dangerous language string"""
    if 'German' in language_string:
        return 'de'
    elif 'French' in language_string:
        return 'fr'
    elif 'Spanish' in language_string:
        return 'es'
    elif 'Russian' in language_string:
        return 'ru'
    elif 'Portuguese' in language_string:
        return 'pt'
    else:
        return 'en'

# =============================================================================
# INITIALIZATION
# =============================================================================

def _load_saved_language() -> str:
    """Load saved language preference from config file"""
    try:
        import sys
        import os
        
        # Try to find config.json - must match config.py logic exactly
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            exe_dir = os.path.dirname(sys.executable)  # .../Configurator
            parent_dir = os.path.dirname(exe_dir)      # .../EliteMining
            
            # Primary: installed version location (matches config.py)
            config_path = os.path.join(parent_dir, "config.json")
        else:
            # Running in development mode
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(app_dir, 'config.json')
        
        print(f"[localization] Looking for config at: {config_path}")
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                lang = config.get('language', 'en')  # Default to English
                # Convert legacy 'auto' setting to 'en'
                if lang == 'auto':
                    lang = 'en'
                print(f"[localization] Found language setting: {lang}")
                return lang
        else:
            print(f"[localization] Config file not found at: {config_path}")
    except Exception as e:
        print(f"[localization] Could not load saved language: {e}")
    
    return 'en'  # Default to English

def init(journal_dir: str = None, language: str = None) -> str:
    """
    Initialize the localization system.
    
    Args:
        journal_dir: Path to Elite Dangerous journal directory (unused, kept for compatibility)
        language: Override language code (if provided, uses this instead of saved preference)
    
    Returns:
        The active language code
    """
    global _current_language, _strings, _materials, _initialized
    
    # Check saved language preference first (defaults to English)
    if language:
        _current_language = language
    else:
        saved_lang = _load_saved_language()
        _current_language = saved_lang if saved_lang else 'en'
        print(f"[localization] Using saved language preference: {_current_language}")
    
    print(f"[localization] Initializing with language: {_current_language}")
    
    # Load string files
    _strings = _load_strings(_current_language)
    _materials = _load_materials(_current_language)
    
    _initialized = True
    return _current_language

def _load_strings(lang: str) -> Dict[str, Any]:
    """Load UI strings for the specified language"""
    loc_dir = _get_localization_dir()
    
    # Try to load requested language, fall back to English
    for try_lang in [lang, 'en']:
        file_path = os.path.join(loc_dir, f"strings_{try_lang}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if try_lang != lang:
                        print(f"[localization] Falling back to English strings")
                    return data
            except Exception as e:
                print(f"[localization] Error loading {file_path}: {e}")
    
    print(f"[localization] Warning: No string files found")
    return {}

def _load_materials(lang: str) -> Dict[str, Any]:
    """Load material names and abbreviations for the specified language"""
    loc_dir = _get_localization_dir()
    
    # Try to load requested language, fall back to English
    for try_lang in [lang, 'en']:
        file_path = os.path.join(loc_dir, f"materials_{try_lang}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if try_lang != lang:
                        print(f"[localization] Falling back to English materials")
                    return data
            except Exception as e:
                print(f"[localization] Error loading {file_path}: {e}")
    
    print(f"[localization] Warning: No material files found")
    return {}

# =============================================================================
# PUBLIC API
# =============================================================================

def get_language() -> str:
    """Get the current language code"""
    return _current_language

def get_saved_preference() -> str:
    """Get the user's saved language preference from config"""
    return _load_saved_language()

def set_language(lang: str, force: bool = False) -> None:
    """
    Change the current language and reload strings.
    
    Args:
        lang: Language code ('en', 'de', 'fr', 'es', 'ru', 'pt')
        force: If True, change even if user has manual preference
    """
    global _current_language, _strings, _materials
    
    # Check if user has a manual preference set (user preference is always respected)
    if not force:
        saved_pref = _load_saved_language()
        if saved_pref and saved_pref != lang:
            # User has preference set, don't override
            print(f"[localization] Keeping user preference '{saved_pref}', ignoring requested '{lang}'")
            return
    
    _current_language = lang
    _strings = _load_strings(lang)
    _materials = _load_materials(lang)
    print(f"[localization] Language changed to: {lang}")

def t(key: str, **kwargs) -> str:
    """
    Get translated UI string by key.
    
    Args:
        key: Dot-notation key (e.g., "ring_finder.ring_type")
        **kwargs: Format arguments for string interpolation
    
    Returns:
        Translated string, or key if not found
    
    Example:
        t("ring_finder.ring_type")  # "Ring Type"
        t("messages.results_found", count=5)  # "Found 5 results"
    """
    # Auto-initialize if needed
    if not _initialized:
        init()
    
    # Navigate nested keys
    parts = key.split('.')
    value = _strings
    
    for part in parts:
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            # Key not found, return the key itself
            return key
    
    if not isinstance(value, str):
        return key
    
    # Apply format arguments
    if kwargs:
        try:
            return value.format(**kwargs)
        except KeyError:
            return value
    
    return value

def get_material(english_name: str) -> str:
    """
    Get localized material name.
    
    Args:
        english_name: English material name (canonical)
    
    Returns:
        Localized material name, or original if not found
    """
    if not _initialized:
        init()
    
    names = _materials.get('names', {})
    return names.get(english_name, english_name)

def get_abbr(english_name: str) -> str:
    """
    Get material abbreviation for display.
    
    Args:
        english_name: English material name (canonical)
    
    Returns:
        Abbreviated name for display, or original if not found
    """
    if not _initialized:
        init()
    
    abbrs = _materials.get('abbreviations', {})
    return abbrs.get(english_name, english_name)

def abbreviate_text(text: str) -> str:
    """
    Abbreviate all material names in a text string.
    
    Args:
        text: Text containing material names
    
    Returns:
        Text with material names abbreviated
    """
    if not text or not _initialized:
        return text
    
    abbrs = _materials.get('abbreviations', {})
    result = text
    for full_name, abbr in abbrs.items():
        result = result.replace(full_name, abbr)
    return result

def to_english(localized_name: str) -> str:
    """
    Convert localized material name back to English (for database queries).
    
    Args:
        localized_name: Material name in any supported language
    
    Returns:
        English material name, or original if not found
    """
    if not _initialized:
        init()
    
    to_eng = _materials.get('to_english', {})
    return to_eng.get(localized_name, localized_name)

def get_all_materials() -> list:
    """
    Get list of all localized material names (for dropdowns).
    
    Returns:
        List of material names in current language
    """
    if not _initialized:
        init()
    
    names = _materials.get('names', {})
    return list(names.values())

def get_ring_types() -> dict:
    """
    Get ring type names in current language.
    
    Returns:
        Dict mapping English ring types to localized names
    """
    if not _initialized:
        init()
    
    ring_types = _strings.get('ring_finder', {})
    return {
        'All': ring_types.get('all', 'All'),
        'Metallic': ring_types.get('metallic', 'Metallic'),
        'Rocky': ring_types.get('rocky', 'Rocky'),
        'Icy': ring_types.get('icy', 'Icy'),
        'Metal Rich': ring_types.get('metal_rich', 'Metal Rich'),
    }

def get_station_types() -> dict:
    """
    Get station type names in current language.
    
    Returns:
        Dict mapping English station types to localized names
    """
    if not _initialized:
        init()
    
    marketplace = _strings.get('marketplace', {})
    return {
        'All': marketplace.get('all', 'All'),
        'Orbital': marketplace.get('orbital', 'Orbital'),
        'Surface': marketplace.get('surface', 'Surface'),
        'Fleet Carrier': marketplace.get('fleet_carrier', 'Fleet Carrier'),
        'Megaship': marketplace.get('megaship', 'Megaship'),
        'Stronghold': marketplace.get('stronghold', 'Stronghold'),
    }

def get_sort_options() -> dict:
    """
    Get sort option names in current language.
    
    Returns:
        Dict mapping English sort options to localized names
    """
    if not _initialized:
        init()
    
    marketplace = _strings.get('marketplace', {})
    return {
        'Best price (highest)': marketplace.get('best_price_highest', 'Best price (highest)'),
        'Best price (lowest)': marketplace.get('best_price_lowest', 'Best price (lowest)'),
        'Distance': marketplace.get('distance', 'Distance'),
        'Best supply/demand': marketplace.get('best_supply_demand', 'Best supply/demand'),
        'Best demand': marketplace.get('best_demand', 'Best demand'),
        'Best supply': marketplace.get('best_supply', 'Best supply'),
        'Last update': marketplace.get('last_update', 'Last update'),
    }

def get_age_options() -> dict:
    """
    Get age filter options in current language.
    
    Returns:
        Dict mapping English age options to localized names
    """
    if not _initialized:
        init()
    
    marketplace = _strings.get('marketplace', {})
    return {
        'Any': marketplace.get('any', 'Any'),
        '1 hour': marketplace.get('1_hour', '1 hour'),
        '8 hours': marketplace.get('8_hours', '8 hours'),
        '16 hours': marketplace.get('16_hours', '16 hours'),
        '1 day': marketplace.get('1_day', '1 day'),
        '2 days': marketplace.get('2_days', '2 days'),
    }

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def is_initialized() -> bool:
    """Check if localization system is initialized"""
    return _initialized

def get_available_languages() -> list:
    """
    Get list of available language codes based on installed files.
    
    Returns:
        List of language codes (e.g., ['en', 'de'])
    """
    loc_dir = _get_localization_dir()
    languages = []
    
    try:
        for file in os.listdir(loc_dir):
            if file.startswith('strings_') and file.endswith('.json'):
                lang = file[8:-5]  # Extract 'en' from 'strings_en.json'
                languages.append(lang)
    except Exception:
        pass
    
    return languages if languages else ['en']
