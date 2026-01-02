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


def get_theme_colors(theme_name: str) -> dict:
    """Get the color dictionary for the specified theme."""
    if theme_name == "elite_orange":
        return THEME_ELITE_ORANGE
    else:
        return THEME_DARK_GRAY
