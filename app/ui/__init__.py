# -*- coding: utf-8 -*-
"""
EliteMining UI Components
Reusable UI widgets and theme configuration.
"""

from ui.theme import (
    THEME_ELITE_ORANGE,
    THEME_DARK_GRAY,
    get_theme_colors
)

from ui.tooltip import ToolTip

from ui.dialogs import (
    centered_yesno_dialog,
    center_window,
    centered_info_dialog
)

__all__ = [
    # Theme
    'THEME_ELITE_ORANGE',
    'THEME_DARK_GRAY', 
    'get_theme_colors',
    # Widgets
    'ToolTip',
    # Dialogs
    'centered_yesno_dialog',
    'center_window',
    'centered_info_dialog',
]
