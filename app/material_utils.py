"""
Material name abbreviation utilities for EliteMining
"""

# Material name abbreviations for compact display
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
    "Bromelite": "Br"
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
