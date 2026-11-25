"""Shared right-click editing menu for single-line text fields."""

import tkinter as tk
from tkinter import ttk

from core.constants import get_menu_colors
from localization import t


def show_entry_context_menu(event):
    widget = event.widget
    if widget.bind("<Button-3>"):
        return

    if isinstance(widget, ttk.Entry):
        disabled = widget.instate(("disabled",))
        readonly = widget.instate(("readonly",))
    else:
        state = widget.cget("state")
        disabled = state == tk.DISABLED
        readonly = state == "readonly"

    if disabled or (readonly and isinstance(widget, ttk.Combobox)):
        return

    widget.focus_set()
    selected = widget.selection_present()
    try:
        can_paste = not readonly and bool(widget.clipboard_get())
    except tk.TclError:
        can_paste = False

    # Reuse the same Tk name so repeated clicks replace the previous menu.
    menu = tk.Menu(widget.winfo_toplevel(), name="entry_context_menu", tearoff=0, **get_menu_colors())
    menu.add_command(label=t("common.cut"), command=lambda: widget.event_generate("<<Cut>>"),
                     state=tk.NORMAL if selected and not readonly else tk.DISABLED)
    menu.add_command(label=t("common.copy"), command=lambda: widget.event_generate("<<Copy>>"),
                     state=tk.NORMAL if selected else tk.DISABLED)
    menu.add_command(label=t("common.paste"), command=lambda: widget.event_generate("<<Paste>>"),
                     state=tk.NORMAL if can_paste else tk.DISABLED)
    menu.add_command(label=t("common.select_all"), command=lambda: widget.selection_range(0, tk.END))
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()
    return "break"
