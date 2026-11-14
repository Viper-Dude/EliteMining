# -*- coding: utf-8 -*-
"""
EliteMining Theme Configuration
Centralized color definitions for the Elite Orange and Dark Gray themes.
"""

# ============================================================================
# CENTRALIZED THEME COLOR CONFIGURATION
# ============================================================================
# Adjust these values to customize the Elite Orange theme appearance.
# All orange/accent colors throughout the app will use these values.

THEME_ELITE_ORANGE = {
    # Main background colors
    "bg": "#000000",              # Pure black background
    "bg_dark": "#0a0a0a",         # Slightly lighter black for contrast
    "bg_accent": "#1a1a1a",       # Dark gray for panels/accents
    
    # Orange text colors (adjust brightness here)
    "fg": "#ff8c00",              # Primary orange text (Dark Orange)
    "fg_bright": "#ffa500",       # Brighter orange for highlights
    "fg_dim": "#cc7000",          # Dimmer orange for secondary text
    "fg_muted": "#888888",        # Gray for disabled/help text
    
    # Selection colors
    "selection_bg": "#ff6600",    # Orange selection background
    "selection_fg": "#000000",    # Black text on selection
    
    # Button colors
    "btn_bg": "#333333",          # Button background
    "btn_bg_hover": "#444444",    # Button hover
    "btn_bg_disabled": "#1a1a1a", # Button disabled
    "btn_fg": "#ff8c00",          # Button text (orange)
    "btn_fg_disabled": "#666666", # Disabled button text
    
    # Treeview/Table colors
    "tree_bg": "#000000",         # Tree background
    "tree_fg": "#ff8c00",         # Tree text
    "tree_selected_bg": "#ff6600", # Selected row
    "tree_selected_fg": "#000000", # Selected row text
    "tree_heading_bg": "#1a1a1a", # Column headers
    "tree_heading_fg": "#ffa500", # Column header text
    
    # Tip/info colors
    "tip_fg": "#ffa500",          # Tip text (bright orange)
    "help_fg": "#888888",         # Help text (gray)
}

THEME_DARK_GRAY = {
    # Main background colors
    "bg": "#1e1e1e",              # Dark gray background
    "bg_dark": "#1e1e1e",         # Same as bg
    "bg_accent": "#2d2d2d",       # Lighter gray for panels
    
    # Text colors
    "fg": "#e6e6e6",              # Light gray text
    "fg_bright": "#ffffff",       # White for highlights
    "fg_dim": "#cccccc",          # Dimmer for secondary
    "fg_muted": "gray",           # Gray for help text
    
    # Selection colors
    "selection_bg": "#444444",    # Gray selection
    "selection_fg": "#ffffff",    # White text on selection
    
    # Button colors
    "btn_bg": "#333333",
    "btn_bg_hover": "#444444",
    "btn_bg_disabled": "#1a1a1a",
    "btn_fg": "#ffffff",
    "btn_fg_disabled": "#666666",
    
    # Treeview/Table colors
    "tree_bg": "#1e1e1e",
    "tree_fg": "#e6e6e6",
    "tree_selected_bg": "#444444",
    "tree_selected_fg": "#ffffff",
    "tree_heading_bg": "#2d2d2d",
    "tree_heading_fg": "#ffffff",
    
    # Tip/info colors
    "tip_fg": "#ffa500",          # Orange tips
    "help_fg": "gray",
}


THEME_MODERN = {
    "bg": "#14171B",
    "bg_dark": "#14171B",
    "bg_accent": "#1D2228",       # Panels
    "fg": "#E6EAF0",
    "fg_bright": "#FFFFFF",
    "fg_dim": "#B4BCC8",
    "fg_muted": "#8A94A3",
    "selection_bg": "#4A3520",    # Warm selected row
    "selection_fg": "#FFFFFF",
    "btn_bg": "#262C34",
    "btn_bg_hover": "#323A44",
    "btn_bg_disabled": "#1D2228",
    "btn_fg": "#E6EAF0",
    "btn_fg_disabled": "#666E7A",
    "tree_bg": "#1D2228",
    "tree_fg": "#E6EAF0",
    "tree_selected_bg": "#4A3520",
    "tree_selected_fg": "#FFFFFF",
    "tree_heading_bg": "#14171B",
    "tree_heading_fg": "#E6EAF0",
    "tip_fg": "#FF9A32",
    "help_fg": "#8A94A3",
    # Modern-only extras
    "panel": "#1D2228",
    "border": "#343B44",
    "accent": "#FF9A32",
    "accent_fg": "#14171B",
    "row_alt": "#20262D",
    "online": "#3DDC84",
}

THEME_MODERN_SLATE = {
    **THEME_MODERN,
    "bg": "#101010",
    "bg_dark": "#101010",
    "bg_accent": "#191919",
    "fg": "#DEDEDE",
    "fg_dim": "#B5B5B5",
    "fg_muted": "#909090",
    "selection_bg": "#383838",
    "btn_bg": "#252525",
    "btn_bg_hover": "#333333",
    "btn_bg_disabled": "#191919",
    "btn_fg": "#DEDEDE",
    "btn_fg_disabled": "#686868",
    "tree_bg": "#191919",
    "tree_fg": "#DEDEDE",
    "tree_selected_bg": "#383838",
    "tree_heading_bg": "#101010",
    "tree_heading_fg": "#DEDEDE",
    "tip_fg": "#D8D8D8",
    "help_fg": "#909090",
    "panel": "#191919",
    "border": "#343434",
    "accent": "#D8D8D8",
    "accent_fg": "#101010",
    "row_alt": "#212121",
}

THEME_MODERN_ORANGE = {
    **THEME_MODERN,
    "bg": "#0E0E0E",
    "bg_dark": "#0E0E0E",
    "bg_accent": "#191919",
    "fg": "#ED9A32",
    "fg_bright": "#FFB454",
    "fg_dim": "#C58A3F",
    "fg_muted": "#929292",
    "selection_bg": "#4A3018",
    "btn_bg": "#262626",
    "btn_bg_hover": "#333333",
    "btn_bg_disabled": "#191919",
    "btn_fg": "#ED9A32",
    "btn_fg_disabled": "#6C6C6C",
    "tree_bg": "#191919",
    "tree_fg": "#ED9A32",
    "tree_selected_bg": "#4A3018",
    "tree_heading_bg": "#0E0E0E",
    "tree_heading_fg": "#ED9A32",
    "tip_fg": "#FF9A32",
    "help_fg": "#929292",
    "panel": "#191919",
    "border": "#343434",
    "accent": "#FF9A32",
    "accent_fg": "#0E0E0E",
    "row_alt": "#212121",
}

_MODERN_SLATE_COLORS = {
    value.lower(): THEME_MODERN_SLATE[key]
    for key, value in THEME_MODERN.items()
}
_MODERN_SLATE_COLORS.update({
    "#ffb05a": "#F0F0F0", "#e88a28": "#BBBBBB",
    "#2a3038": "#121212", "#232a31": "#212121",
    "#323941": "#343434", "#434b55": "#494949",
    "#ffb347": "#D8D8D8",
})


_MODERN_ORANGE_COLORS = {
    value.lower(): THEME_MODERN_ORANGE[key]
    for key, value in THEME_MODERN.items()
}
_MODERN_ORANGE_COLORS.update({
    "#2a3038": "#222222", "#232a31": "#212121",
    "#323941": "#343434", "#434b55": "#484848",
    "#ffb347": "#FFB454",
})


def modern_color(color: str) -> str:
    """Resolve legacy Modern colors for the selected Modern palette."""
    from config import load_theme
    theme = load_theme()
    if theme == "modern_slate":
        return _MODERN_SLATE_COLORS.get(color.lower(), color)
    if theme == "modern_orange":
        return _MODERN_ORANGE_COLORS.get(color.lower(), color)
    return color


THEMES = {
    "elite_orange": THEME_ELITE_ORANGE,
    "dark_gray": THEME_DARK_GRAY,
    "modern": THEME_MODERN,
    "modern_slate": THEME_MODERN_SLATE,
    "modern_orange": THEME_MODERN_ORANGE,
}

THEME_ORDER = ["elite_orange", "dark_gray", "modern", "modern_slate", "modern_orange"]


def get_theme_colors(theme_name: str) -> dict:
    """Get the color dictionary for the specified theme."""
    return THEMES.get(theme_name, THEME_DARK_GRAY)


def next_theme(theme_name: str) -> str:
    """Theme the toggle button switches to."""
    i = THEME_ORDER.index(theme_name) if theme_name in THEME_ORDER else 1
    return THEME_ORDER[(i + 1) % len(THEME_ORDER)]
