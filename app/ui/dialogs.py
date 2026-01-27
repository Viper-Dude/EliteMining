# -*- coding: utf-8 -*-
"""
EliteMining Dialog Helpers
Centered dialog utilities for Yes/No prompts, info messages, etc.
"""

import tkinter as tk
from tkinter import ttk

# Import translation function - will be injected at runtime
_translate_func = None


def set_translate_func(t_func):
    """Set the translation function to use for dialog text."""
    global _translate_func
    _translate_func = t_func


def _t(key, **kwargs):
    """Get translated text, falling back to key if no translator set."""
    if _translate_func:
        return _translate_func(key, **kwargs)
    # Fallback: return last part of key
    return key.split('.')[-1]


def center_window(child, parent):
    """Center `child` (Toplevel) on `parent` (Tk or Toplevel)."""
    parent.update_idletasks()
    child.update_idletasks()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    cw = child.winfo_width()
    ch = child.winfo_height()
    x = px + (pw - cw) // 2
    y = py + (ph - ch) // 2
    child.geometry(f"+{x}+{y}")


def centered_yesno_dialog(parent, title, message):
    """Show a Yes/No dialog centered over parent window. Returns True for Yes, False for No."""
    dialog = tk.Toplevel(parent)
    dialog.withdraw()  # Prevent flicker while we layout and center
    try:
        from app_utils import get_app_icon_path
        icon_path = get_app_icon_path()
        if icon_path and icon_path.endswith('.ico'):
            dialog.iconbitmap(icon_path)
        elif icon_path:
            dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
    except Exception:
        pass
    dialog.title(title)
    dialog.resizable(False, False)
    
    # Use ttk frame for themed look
    frame = ttk.Frame(dialog, padding=20)
    frame.pack(fill="both", expand=True)
    
    ttk.Label(frame, text=message, font=("Segoe UI", 10)).pack(pady=(0, 15))
    
    btn_frame = ttk.Frame(frame)
    btn_frame.pack()
    
    result = {'value': None}
    def on_yes():
        result['value'] = True
        dialog.destroy()
    def on_no():
        result['value'] = False
        dialog.destroy()
    
    yes_btn = ttk.Button(btn_frame, text=_t('common.yes'), width=10, command=on_yes)
    yes_btn.pack(side=tk.LEFT, padx=(0, 10))
    no_btn = ttk.Button(btn_frame, text=_t('common.no'), width=10, command=on_no)
    no_btn.pack(side=tk.LEFT)
    
    # Keyboard bindings
    dialog.bind("<Return>", lambda e: on_yes())
    dialog.bind("<Escape>", lambda e: on_no())
    
    # Center on parent window manually
    dialog.update_idletasks()
    dialog_width = dialog.winfo_reqwidth()
    dialog_height = dialog.winfo_reqheight()
    
    # Get parent's actual position and size
    parent.update_idletasks()
    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_width = parent.winfo_width()
    parent_height = parent.winfo_height()
    
    # Calculate centered position
    x = parent_x + (parent_width - dialog_width) // 2
    y = parent_y + (parent_height - dialog_height) // 2
    
    dialog.geometry(f"+{x}+{y}")
    dialog.deiconify()  # Show centered immediately
    
    # Now set modal behavior
    dialog.transient(parent)
    dialog.grab_set()
    dialog.attributes('-topmost', True)
    dialog.lift()
    yes_btn.focus_set()
    dialog.wait_window()
    return result['value']


def centered_info_dialog(parent, title, message):
    """Show an Info dialog centered over parent window with theme-aware colors. Returns when OK pressed."""
    from config import load_theme
    
    # Get theme colors
    theme = load_theme()
    if theme == "elite_orange":
        bg_color = "#000000"
        fg_color = "#ff8c00"
        btn_bg = "#1a1a1a"
        btn_fg = "#ff9900"
    else:
        bg_color = "#1e1e1e"
        fg_color = "#569cd6"
        btn_bg = "#2a3a4a"
        btn_fg = "#e0e0e0"
    
    dialog = tk.Toplevel(parent)
    dialog.withdraw()  # Prevent flicker while laying out
    dialog.configure(bg=bg_color)
    
    # Set app icon
    try:
        from app_utils import get_app_icon_path
        icon_path = get_app_icon_path()
        if icon_path and icon_path.endswith('.ico'):
            dialog.iconbitmap(icon_path)
        elif icon_path:
            dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
    except Exception:
        pass
    
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.transient(parent)
    
    # Message label
    label = tk.Label(dialog, text=message, padx=20, pady=20, 
                    bg=bg_color, fg=fg_color, font=("Segoe UI", 10),
                    justify="left", wraplength=500)
    label.pack()
    
    # Button frame
    btn_frame = tk.Frame(dialog, bg=bg_color)
    btn_frame.pack(pady=(0, 15))
    
    def on_ok():
        dialog.destroy()
    
    ok_btn = tk.Button(btn_frame, text=_t('common.ok'), width=10, command=on_ok,
                      bg=btn_bg, fg=btn_fg, font=("Segoe UI", 10),
                      activebackground=btn_bg, activeforeground=btn_fg,
                      cursor="hand2", relief="flat", bd=0)
    ok_btn.pack()
    
    # Update and center on parent
    dialog.update_idletasks()
    
    top_parent = parent.winfo_toplevel() if parent else None
    if top_parent:
        center_window(dialog, top_parent)
    
    dialog.deiconify()  # Show centered
    dialog.grab_set()
    dialog.attributes('-topmost', True)
    dialog.lift()
    dialog.focus_force()
    dialog.wait_window()

