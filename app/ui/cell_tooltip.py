# -*- coding: utf-8 -*-
"""Hover tooltip for the cells of one Treeview column (e.g. show a full comment/note)."""

import tkinter as tk

from column_visibility_helper import displayed_column
from config import scaled_font, scaled_px


def attach_cell_tooltip(tree, column_name, text_for_item):
    """Show text_for_item(item_id) in a tooltip while hovering a cell of `column_name`.

    Nothing is shown when text_for_item returns an empty string. Uses add='+' bindings
    so it coexists with the tree's existing handlers.
    """
    state = {"tip": None, "key": None}

    def hide(event=None):
        if state["tip"]:
            state["tip"].destroy()
            state["tip"] = None
        state["key"] = None

    def on_motion(event):
        if tree.identify_region(event.x, event.y) != "cell":
            hide()
            return
        item = tree.identify_row(event.y)
        if not item or displayed_column(tree, tree.identify_column(event.x)) != column_name:
            hide()
            return

        key = (item, column_name)
        if key != state["key"]:
            hide()
            text = (text_for_item(item) or "").strip()
            if not text:
                return
            state["key"] = key
            tip = tk.Toplevel(tree)
            tip.withdraw()
            tip.wm_overrideredirect(True)
            tip.wm_attributes("-topmost", True)
            tk.Label(tip, text=text, background="#ffffe0", foreground="#000000",
                     relief="solid", borderwidth=1, font=scaled_font(10),
                     padx=8, pady=6, wraplength=scaled_px(450), justify="left").pack()
            state["tip"] = tip
        if state["tip"]:
            state["tip"].wm_geometry(f"+{event.x_root + 12}+{event.y_root + 16}")
            state["tip"].deiconify()

    tree.bind("<Motion>", on_motion, add="+")
    tree.bind("<Leave>", hide, add="+")
    tree.bind("<ButtonPress-1>", hide, add="+")
