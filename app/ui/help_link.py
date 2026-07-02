# -*- coding: utf-8 -*-
"""
EliteMining Help Link Widget
Small clickable "?" label that opens a README section on GitHub.
"""

import tkinter as tk
from tkinter import ttk
import webbrowser

from config import load_theme
from ui.theme import get_theme_colors

REPO_URL = "https://github.com/Viper-Dude/EliteMining"


def create_help_link(parent, anchor: str, tooltip_text: str = "", tooltip_class=None,
                      bg: str = None, fg: str = None) -> tk.Label:
    """Create a clickable '?' label that opens the README at the given anchor.

    `bg`/`fg` default to the current theme's background and tip color. Pass them
    explicitly when the parent widget doesn't use the shared theme background
    (e.g. a frame with its own hardcoded color), to avoid a mismatched box.

    Caller is responsible for packing/gridding the returned widget.
    """
    theme = get_theme_colors(load_theme())
    link = tk.Label(parent, text="?", font=("Segoe UI", 9, "bold"),
                     bg=bg or theme["bg"], fg=fg or theme["tip_fg"], cursor="hand2")
    link.bind("<Button-1>", lambda e: webbrowser.open(f"{REPO_URL}#{anchor}"))
    if tooltip_class and tooltip_text:
        tooltip_class(link, tooltip_text)
    return link


def create_labelframe_title(parent, title: str, anchor: str, tooltip_text: str = "", tooltip_class=None) -> ttk.Frame:
    """Build a title+'?' row usable as a ttk.LabelFrame's `labelwidget`.

    Create the LabelFrame without `text=`, then attach the result:
        lf = ttk.LabelFrame(parent, padding=10)
        lf.configure(labelwidget=create_labelframe_title(lf, "Title", "anchor", tip, ToolTip))
    """
    title_row = ttk.Frame(parent)
    ttk.Label(title_row, text=title, style="TLabelframe.Label").pack(side="left")
    create_help_link(title_row, anchor, tooltip_text, tooltip_class).pack(side="left", padx=(6, 0))
    return title_row
