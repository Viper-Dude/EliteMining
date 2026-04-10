# -*- coding: utf-8 -*-
"""
Reusable system name autocomplete for tkinter Entry widgets.
Queries Spansh API for system name suggestions.
"""

import tkinter as tk
import threading
import requests
import urllib.parse


class SystemAutocomplete:
    """Attach autocomplete to a tk/ttk Entry bound to a StringVar.

    Usage:
        ac = SystemAutocomplete(entry_widget, string_var, root_widget)
        # When setting the var programmatically:
        ac.suppress()
        string_var.set("Sol")
        ac.unsuppress()
    """

    def __init__(self, entry: tk.Entry, var: tk.StringVar, root: tk.Misc):
        self._entry = entry
        self._var = var
        self._root = root
        self._listbox_toplevel = None
        self._lb = None
        self._timer = None
        self._request_id = 0
        self._suppressed = False
        self._mouse_over = False

        # Bind entry events
        self._entry.bind('<KeyRelease>', self._on_key, add='+')
        self._entry.bind('<Down>', self._focus_listbox, add='+')
        self._entry.bind('<Escape>', lambda e: self.hide(), add='+')

        # Wrap existing FocusOut — delay hide so listbox click fires first
        self._entry.bind('<FocusOut>', self._on_focusout, add='+')

    # --- public helpers ---

    def suppress(self):
        self._suppressed = True

    def unsuppress(self):
        self._suppressed = False

    def hide(self):
        if self._listbox_toplevel:
            self._listbox_toplevel.destroy()
            self._listbox_toplevel = None
            self._lb = None
        if self._timer is not None:
            self._root.after_cancel(self._timer)
            self._timer = None
        self._mouse_over = False

    # --- internal ---

    def _on_key(self, event):
        if event.keysym in ('Up', 'Down', 'Left', 'Right', 'Escape', 'Return',
                            'Shift_L', 'Shift_R', 'Control_L', 'Control_R',
                            'Alt_L', 'Alt_R', 'Tab', 'BackTab'):
            return
        if self._suppressed:
            return
        text = self._var.get().strip()
        if len(text) < 3:
            self.hide()
            return
        if self._timer is not None:
            self._root.after_cancel(self._timer)
        self._timer = self._root.after(300, lambda: self._query(text))

    def _on_focusout(self, event):
        self._root.after(150, self._delayed_hide)

    def _delayed_hide(self):
        if self._mouse_over:
            return
        self.hide()

    def _query(self, text: str):
        self._request_id += 1
        rid = self._request_id
        threading.Thread(target=self._fetch, args=(text, rid), daemon=True).start()

    def _fetch(self, text: str, rid: int):
        try:
            url = f"https://spansh.co.uk/api/systems/field_values/system_names?q={urllib.parse.quote(text)}"
            resp = requests.get(url, timeout=5)
            if resp.status_code != 200:
                return
            data = resp.json()
            names = [e["name"] for e in data.get("min_max", data.get("values", [])) if "name" in e]
            if rid == self._request_id:
                self._root.after(0, lambda: self._show(names, rid))
        except Exception:
            pass

    def _show(self, names: list, rid: int):
        if rid != self._request_id:
            return
        if not names:
            self.hide()
            return

        if self._listbox_toplevel is None:
            self._listbox_toplevel = tk.Toplevel(self._root)
            self._listbox_toplevel.wm_overrideredirect(True)
            self._listbox_toplevel.wm_attributes("-topmost", True)
            self._lb = tk.Listbox(self._listbox_toplevel, bg="#1e1e1e", fg="#e0e0e0",
                                  selectbackground="#4a3a2a", selectforeground="#ffffff",
                                  font=("Consolas", 10), activestyle="none",
                                  highlightthickness=0, bd=1, relief="solid")
            self._lb.pack(fill="both", expand=True)
            self._lb.bind('<ButtonRelease-1>', self._select)
            self._lb.bind('<Return>', self._select)
            self._lb.bind('<Escape>', lambda e: self.hide())
            self._lb.bind('<Enter>', lambda e: setattr(self, '_mouse_over', True))
            self._lb.bind('<Leave>', lambda e: setattr(self, '_mouse_over', False))

        self._lb.delete(0, tk.END)
        for n in names[:20]:
            self._lb.insert(tk.END, n)

        self._entry.update_idletasks()
        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height()
        w = max(self._entry.winfo_width(), 300)
        h = min(len(names), 20) * 20 + 4
        self._listbox_toplevel.geometry(f"{w}x{h}+{x}+{y}")
        self._listbox_toplevel.deiconify()

    def _select(self, event=None):
        if self._lb is None:
            return
        sel = self._lb.curselection()
        if not sel:
            return
        name = self._lb.get(sel[0])
        self._suppressed = True
        self._var.set(name)
        self._suppressed = False
        self.hide()
        self._entry.focus_set()
        self._entry.icursor(tk.END)

    def _focus_listbox(self, event=None):
        if self._listbox_toplevel and self._lb and self._lb.size() > 0:
            self._lb.focus_set()
            self._lb.selection_clear(0, tk.END)
            self._lb.selection_set(0)
            self._lb.activate(0)
            return "break"
