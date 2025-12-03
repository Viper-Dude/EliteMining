"""
Material name abbreviation utilities for EliteMining

This module provides backward-compatible wrappers around the new localization system.
All new code should import directly from `localization` module instead.

Migration note: This file is kept for backward compatibility with existing code.
The actual implementation has moved to app/localization/
"""

# =============================================================================
# IMPORTS FROM NEW LOCALIZATION SYSTEM
# =============================================================================

try:
    from localization import (
        detect_language as detect_game_language,
        get_language as get_game_language,
        set_language as set_game_language,
        get_abbr as abbreviate_material,
        abbreviate_text as abbreviate_material_text,
        init as _init_localization,
    )
    
    _USE_NEW_LOCALIZATION = True
    
    def clear_language_cache():
        """Clear cached language (call when game restarts or language changes)"""
        _init_localization()
    
    def get_display_abbreviations(language=None):
        """Get abbreviations dict - wrapper for backward compatibility"""
        from localization import _materials, get_language
        if language is None:
            language = get_language()
        return _materials.get('abbreviations', {})

except ImportError:
    # Fallback if localization module not available
    _USE_NEW_LOCALIZATION = False
    import os
    import glob
    import json

    _cached_game_language = None

    def detect_game_language(journal_dir: str = None) -> str:
        global _cached_game_language
        if _cached_game_language:
            return _cached_game_language
        
        if not journal_dir:
            journal_dir = os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous")
        
        try:
            journal_pattern = os.path.join(journal_dir, "Journal*.log")
            journal_files = glob.glob(journal_pattern)
            if not journal_files:
                return 'en'
            
            latest_journal = max(journal_files, key=os.path.getmtime)
            
            with open(latest_journal, 'r', encoding='utf-8') as f:
                for line in f:
                    if '"event":"Fileheader"' in line:
                        try:
                            data = json.loads(line)
                            language = data.get('language', 'English/UK')
                            if 'German' in language:
                                _cached_game_language = 'de'
                            else:
                                _cached_game_language = 'en'
                            return _cached_game_language
                        except:
                            pass
                    if f.tell() > 5000:
                        break
        except:
            pass
        
        _cached_game_language = 'en'
        return 'en'

    def clear_language_cache():
        global _cached_game_language
        _cached_game_language = None

    def get_game_language() -> str:
        global _cached_game_language
        return _cached_game_language or 'en'

    def set_game_language(lang_code: str):
        global _cached_game_language
        _cached_game_language = lang_code

    # Fallback abbreviations
    _FALLBACK_ABBR = {
        'Platinum': 'Plat', 'Painite': 'Pain', 'Osmium': 'Osmi',
        'Low Temperature Diamonds': 'LTD', 'Void Opals': 'Opals',
        'Tritium': 'Trit', 'Bromellite': 'Brom', 'Alexandrite': 'Alex',
        'Monazite': 'Mona', 'Musgravite': 'Musg', 'Grandidierite': 'Gran',
        'Serendibite': 'Sere', 'Rhodplumsite': 'Rhod', 'Benitoite': 'Beni',
    }

    def get_display_abbreviations(language=None):
        return _FALLBACK_ABBR

    def abbreviate_material(material_name, language=None):
        return _FALLBACK_ABBR.get(material_name, material_name)

    def abbreviate_material_text(text, language=None):
        if not text:
            return text
        result = text
        for full_name, abbr in _FALLBACK_ABBR.items():
            result = result.replace(full_name, abbr)
        return result


# =============================================================================
# LEGACY API (kept for backward compatibility with older code)
# =============================================================================

# Chemical symbol abbreviations (legacy - some code may still use these)
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

