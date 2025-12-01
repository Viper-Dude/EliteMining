"""
Material name abbreviation utilities for EliteMining

This module provides centralized material abbreviations for consistent display
across the app. Supports multiple languages based on game settings.

Future: This will be migrated to a full localization system.
"""

import os
import glob
import json

# =============================================================================
# GAME LANGUAGE DETECTION
# =============================================================================

_cached_game_language = None

def detect_game_language(journal_dir: str = None) -> str:
    """
    Detect the game language from the most recent journal Fileheader.
    
    Args:
        journal_dir: Path to Elite Dangerous journal directory.
                     If None, uses default Saved Games location.
    
    Returns:
        Language code: 'en', 'de', 'fr', 'es', 'ru', etc.
        Defaults to 'en' if detection fails.
    """
    global _cached_game_language
    
    # Return cached value if available
    if _cached_game_language:
        return _cached_game_language
    
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
            for line in f:
                if '"event":"Fileheader"' in line or '"event": "Fileheader"' in line:
                    try:
                        data = json.loads(line)
                        language = data.get('language', 'English/UK')
                        # Parse language code (e.g., "German/DE" -> "de", "English/UK" -> "en")
                        if 'German' in language:
                            _cached_game_language = 'de'
                        elif 'French' in language:
                            _cached_game_language = 'fr'
                        elif 'Spanish' in language:
                            _cached_game_language = 'es'
                        elif 'Russian' in language:
                            _cached_game_language = 'ru'
                        elif 'Portuguese' in language:
                            _cached_game_language = 'pt'
                        else:
                            _cached_game_language = 'en'
                        return _cached_game_language
                    except json.JSONDecodeError:
                        pass
                # Only check first 10 lines
                if f.tell() > 5000:
                    break
    except Exception as e:
        print(f"[material_utils] Could not detect game language: {e}")
    
    _cached_game_language = 'en'
    return 'en'

def clear_language_cache():
    """Clear cached language (call when game restarts or language changes)"""
    global _cached_game_language
    _cached_game_language = None

def get_game_language() -> str:
    """Get current game language code (cached)"""
    global _cached_game_language
    return _cached_game_language or 'en'

def set_game_language(lang_code: str):
    """Manually set game language (e.g., from Fileheader event)"""
    global _cached_game_language
    _cached_game_language = lang_code

# =============================================================================
# DISPLAY ABBREVIATIONS (for UI - Ring Finder, Reports table)
# =============================================================================

# English display abbreviations (readable, not chemical symbols)
DISPLAY_ABBR_EN = {
    'Alexandrite': 'Alex',
    'Bauxite': 'Baux',
    'Benitoite': 'Beni',
    'Bertrandite': 'Bert',
    'Bromellite': 'Brom',
    'Cobalt': 'Coba',
    'Coltan': 'Colt',
    'Gallite': 'Gall',
    'Gold': 'Gold',
    'Goslarite': 'Gosl',
    'Grandidierite': 'Gran',
    'Haematite': 'Haem',
    'Hydrogen Peroxide': 'H2O2',
    'Indite': 'Indi',
    'Lepidolite': 'Lepi',
    'Liquid Oxygen': 'LOX',
    'Lithium Hydroxide': 'LiOH',
    'Low Temperature Diamonds': 'LTD',
    'Low Temp Diamonds': 'LTD',
    'Methane Clathrate': 'MeCl',
    'Methanol Monohydrate Crystals': 'MeOH',
    'Monazite': 'Mona',
    'Musgravite': 'Musg',
    'Osmium': 'Osmi',
    'Painite': 'Pain',
    'Palladium': 'Pall',
    'Platinum': 'Plat',
    'Praseodymium': 'Pras',
    'Rhodplumsite': 'Rhod',
    'Rutile': 'Ruti',
    'Samarium': 'Sama',
    'Serendibite': 'Sere',
    'Silver': 'Silv',
    'Tritium': 'Trit',
    'Uraninite': 'Uran',
    'Void Opals': 'Opals',
    'Water': 'H2O',
}

# German display abbreviations
# German full names from Elite Dangerous in-game + appropriate abbreviations
DISPLAY_ABBR_DE = {
    # German name -> German abbreviation
    'Alexandrit': 'Alex',
    'Bauxit': 'Baux',
    'Benitoit': 'Beni',
    'Bertrandit': 'Bert',
    'Bromellit': 'Brom',
    'Kobalt': 'Koba',
    'Coltan': 'Colt',
    'Gallit': 'Gall',
    'Gold': 'Gold',
    'Goslarit': 'Gosl',
    'Grandidierit': 'Gran',
    'Hämatit': 'Häma',
    'Wasserstoffperoxid': 'WaPer',
    'Indit': 'Indi',
    'Lepidolith': 'Lepi',
    'Flüssigsauerstoff': 'FlüSa',
    'Lithiumhydroxid': 'LiHyd',
    'Tieftemperaturdiamanten': 'TTD',
    'Methanclathrat': 'MeCla',
    'Methanolmonohydratkristalle': 'MeKri',
    'Monazit': 'Mona',
    'Musgravit': 'Musg',
    'Osmium': 'Osm',
    'Painit': 'Pain',
    'Palladium': 'Pall',
    'Platin': 'Plat',
    'Praseodym': 'Pras',
    'Rhodplumsit': 'Rhod',
    'Rutil': 'Ruti',
    'Samarium': 'Sama',
    'Serendibit': 'Sere',
    'Silber': 'Silb',
    'Tritium': 'Trit',
    'Uraninit': 'Uran',
    'Leeren-Opale': 'LeOp',
    'Wasser': 'H2O',
    
    # Also map English names to German abbreviations (for database which stores English)
    'Alexandrite': 'Alex',
    'Bauxite': 'Baux',
    'Benitoite': 'Beni',
    'Bertrandite': 'Bert',
    'Bromellite': 'Brom',
    'Cobalt': 'Koba',
    'Coltan': 'Colt',
    'Gallite': 'Gall',
    'Gold': 'Gold',
    'Goslarite': 'Gosl',
    'Grandidierite': 'Gran',
    'Haematite': 'Häma',
    'Hydrogen Peroxide': 'WaPer',
    'Indite': 'Indi',
    'Lepidolite': 'Lepi',
    'Liquid Oxygen': 'FlüSa',
    'Lithium Hydroxide': 'LiHyd',
    'Low Temperature Diamonds': 'TTD',
    'Low Temp Diamonds': 'TTD',
    'Methane Clathrate': 'MeCla',
    'Methanol Monohydrate Crystals': 'MeKri',
    'Monazite': 'Mona',
    'Musgravite': 'Musg',
    'Osmium': 'Osm',
    'Painite': 'Pain',
    'Palladium': 'Pall',
    'Platinum': 'Plat',
    'Praseodymium': 'Pras',
    'Rhodplumsite': 'Rhod',
    'Rutile': 'Ruti',
    'Samarium': 'Sama',
    'Serendibite': 'Sere',
    'Silver': 'Silb',
    'Tritium': 'Trit',
    'Uraninite': 'Uran',
    'Void Opals': 'LeOp',
    'Water': 'H2O',
}

def get_display_abbreviations(language: str = None) -> dict:
    """
    Get the display abbreviations dictionary for the specified language.
    
    Args:
        language: Language code ('en', 'de', etc.). If None, uses detected game language.
    
    Returns:
        Dictionary mapping material names to abbreviations
    """
    if language is None:
        language = get_game_language()
    
    if language == 'de':
        return DISPLAY_ABBR_DE
    else:
        return DISPLAY_ABBR_EN

def abbreviate_material(material_name: str, language: str = None) -> str:
    """
    Get abbreviated display name for a material.
    
    Args:
        material_name: Full material name (English or localized)
        language: Language code. If None, uses detected game language.
    
    Returns:
        Abbreviated name for display, or original if no abbreviation found
    """
    abbr_dict = get_display_abbreviations(language)
    return abbr_dict.get(material_name, material_name)

def abbreviate_material_text(text: str, language: str = None) -> str:
    """
    Abbreviate all material names in a text string.
    
    Args:
        text: Text containing material names (e.g., "Platinum (3), Painite (2)")
        language: Language code. If None, uses detected game language.
    
    Returns:
        Text with material names abbreviated
    """
    if not text:
        return text
    
    abbr_dict = get_display_abbreviations(language)
    result = text
    for full_name, abbr in abbr_dict.items():
        result = result.replace(full_name, abbr)
    return result


# =============================================================================
# LEGACY: Chemical symbol abbreviations (kept for backward compatibility)
# =============================================================================

MATERIAL_ABBREVIATIONS = {
    "Platinum": "Pt",
    "Palladium": "Pd", 
    "Gold": "Au",
    "Silver": "Ag",
    "Osmium": "Os",
    "Painite": "Pn",
    "Rhodplumsite": "Rh",
    "Serendibite": "Sr",
    "Alexandrite": "Al",
    "Benitoite": "Bn",
    "Monazite": "Mz",
    "Musgravite": "Mg",
    "Taaffeite": "Tf",
    "Jadeite": "Jd",
    "Opal": "Op",
    "Void Opals": "VO",
    "Low Temperature Diamonds": "LTD",
    "Praseodymium": "Pr",
    "Samarium": "Sm",
    "Europium": "Eu",
    "Gadolinium": "Gd",
    "Neodymium": "Nd",
    "Yttrium": "Yt",
    "Lanthanum": "La",
    "Thulium": "Th",
    "Erbium": "Er",
    "Holmium": "Ho",
    "Dysprosium": "Dy",
    "Terbium": "Tb",
    "Cerium": "Ce",
    "Ytterbium": "Yb",
    "Lutetium": "Lu",
    "Barite": "Ba",
    "Uraninite": "Ur",
    "Moissanite": "Ms",
    "Goslarite": "Gs",
    "Cryolite": "Cy",
    "Covellite": "Cv",
    "Coltan": "Co",
    "Gallite": "Ga",
    "Indite": "In",
    "Lepidolite": "Lp",
    "Lithium Hydroxide": "LiOH",
    "Methane Clathrate": "MC",
    "Methanol Monohydrate": "MM",
    "Water": "H2O",
    "Ammonia": "NH3",
    "Hydrogen Peroxide": "H2O2",
    "Liquid Oxygen": "LOX",
    "Tritium": "T",
    "Rutile": "Rt",
    "Bromellite": "Br"
}

def abbreviate_materials_breakdown(materials_breakdown: str, use_abbreviations: bool = True) -> str:
    """
    Convert materials breakdown to abbreviated format for table display.
    
    Args:
        materials_breakdown: Original format like "Platinum:13t; Osmium:5t; Praseodymium:5t"
        use_abbreviations: Whether to use short abbreviations
    
    Returns:
        Abbreviated format like "Pt:13t, Os:5t, Pr:5t"
    """
    if not materials_breakdown or materials_breakdown == "—":
        return "—"
    
    if not use_abbreviations:
        return materials_breakdown
    
    # Split by semicolon and process each material
    parts = []
    for part in materials_breakdown.split(';'):
        part = part.strip()
        if ':' in part:
            material, amount = part.split(':', 1)
            material = material.strip()
            amount = amount.strip()
            
            # Get abbreviation or use first 3 chars if not found
            abbrev = MATERIAL_ABBREVIATIONS.get(material, material[:3])
            parts.append(f"{abbrev}:{amount}")
    
    return ", ".join(parts)

def get_tooltip_text(materials_breakdown: str) -> str:
    """
    Get full tooltip text for material breakdown display.
    
    Args:
        materials_breakdown: Original format like "Platinum:13t; Osmium:5t; Praseodymium:5t"
    
    Returns:
        Formatted tooltip text with full material names
    """
    if not materials_breakdown or materials_breakdown == "—":
        return "No cargo materials tracked"
    
    # Format for tooltip - replace semicolons with newlines for better readability
    formatted = materials_breakdown.replace(';', '\n').replace(':', ': ')
    return f"Materials Breakdown:\n{formatted}"

