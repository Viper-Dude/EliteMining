"""Voice Commands sub-tab for the shipped VoiceAttack profile."""

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import font as tkfont, ttk

from config import _load_cfg, load_theme, scaled_font, scaled_px, update_config_value
from localization import t
from ui.striped_treeview import StripedTreeview
from ui.theme import get_theme_colors
from va_phrase_reference import GROUPS, ReferenceEntry, ReferenceRow, load_reference, reference_rows


log = logging.getLogger(__name__)
_WIDTHS_KEY = "va_reference_column_widths"
_COLUMN_WIDTHS = {"say_this": 470, "other_ways": 105, "group": 160}


class VoiceCommandsTab(ttk.Frame):
    def __init__(self, notebook, find_profile):
        super().__init__(notebook, padding=scaled_px(8))
        self._find_profile = find_profile
        self._profile_key = None
        self._load_status = None
        self._entries: list[ReferenceEntry] = []
        self._row_details: dict[str, ReferenceRow] = {}
        self._group_labels = {group: t(f"voiceattack.reference_group_{group}") for group in GROUPS}

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(0, scaled_px(6)))
        ttk.Label(filters, text=t("voiceattack.reference_group")).pack(side="left", padx=(0, scaled_px(4)))
        labels = tuple(self._group_labels.values())
        self._groups = ttk.Combobox(filters, state="readonly", values=labels, width=max(map(len, labels)) + 3)
        self._groups.current(0)
        self._groups.pack(side="left", padx=(0, scaled_px(12)))
        self._groups.bind("<<ComboboxSelected>>", self._on_group_selected)
        self._groups.bind("<FocusOut>", lambda event: event.widget.selection_clear())
        ttk.Label(filters, text=t("voiceattack.reference_search")).pack(side="left", padx=(0, scaled_px(4)))
        self._search = tk.StringVar(self)
        ttk.Entry(filters, textvariable=self._search, width=24).pack(side="left")

        self._notice = ttk.Label(self)
        self._notice.pack(fill="x", pady=(0, scaled_px(4)))

        table = ttk.Frame(self)
        table.pack(fill="both", expand=True)
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self._columns = tuple(_COLUMN_WIDTHS)
        self._tree = StripedTreeview(table, columns=self._columns, displaycolumns=self._columns[:2],
                                     show="headings", selectmode="browse", height=10)
        heading_font = tkfont.Font(root=self, font=scaled_font(9, "bold"))
        saved_widths = _load_cfg().get(_WIDTHS_KEY) or {}
        self._widths = {}
        for column, default in _COLUMN_WIDTHS.items():
            label = t(f"voiceattack.reference_{column}")
            min_width = heading_font.measure(label) + scaled_px(24)
            width = max(min_width, saved_widths.get(column, scaled_px(default)))
            self._widths[column] = width
            self._tree.heading(column, text=label, anchor="w")
            self._tree.column(column, width=width, minwidth=min_width, anchor="w", stretch=False)

        vertical = ttk.Scrollbar(table, orient="vertical", command=self._tree.yview)
        horizontal = ttk.Scrollbar(table, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self._tree.bind("<<TreeviewSelect>>", self._show_details)
        self._tree.bind("<ButtonRelease-1>", self._save_widths, add="+")

        theme = get_theme_colors(load_theme())
        details_frame = ttk.Frame(self)
        details_frame.pack(fill="x", pady=(scaled_px(6), 0))
        self._details = tk.Text(
            details_frame, height=2, width=1, wrap="word", state="disabled", exportselection=False,
            font=scaled_font(9), bg=theme["tree_bg"], fg=theme["fg"],
            selectbackground=theme["selection_bg"], selectforeground=theme["selection_fg"],
            padx=scaled_px(6), pady=scaled_px(4), relief="flat", highlightthickness=0,
        )
        details_scroll = ttk.Scrollbar(details_frame, orient="vertical", command=self._details.yview)
        self._details.configure(yscrollcommand=details_scroll.set)
        details_scroll.pack(side="right", fill="y")
        self._details.pack(side="left", fill="x", expand=True)

        self._search.trace_add("write", self._refresh_rows)
        self.bind("<Map>", self._on_show, add="+")
        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add="+")

    def _on_group_selected(self, event):
        self._groups.selection_clear()
        self._refresh_rows()

    def _on_tab_changed(self, event):
        if self.master.select() == str(self):
            self._clear_group_focus()
            self.after(50, self._clear_group_focus)

    def _clear_group_focus(self):
        if self.master.select() != str(self):
            return
        if self.focus_get() == self._groups:
            self.master.focus_set()
        self._groups.selection_clear()

    def _on_show(self, event):
        try:
            filename = self._find_profile()
            path = Path(filename) if filename else None
            key = (path, path.stat().st_mtime_ns) if path else None
        except FileNotFoundError:
            key = None
        except OSError:
            log.exception("Could not locate the shipped VoiceAttack profile")
            self._profile_key = None
            self._set_reference([], "error")
            return

        if key is None:
            self._profile_key = None
            self._set_reference([], "missing")
        elif key != self._profile_key:
            self._profile_key = key
            self._set_reference([], "loading")
            threading.Thread(target=self._load_profile, args=(key,), daemon=True).start()

    def _load_profile(self, key):
        try:
            entries = load_reference(key[0])
            status = None
        except Exception:
            log.exception("Could not read the shipped VoiceAttack profile: %s", key[0])
            entries, status = [], "error"

        def complete():
            if key == self._profile_key and self.winfo_exists():
                self._set_reference(entries, status)

        try:
            self.after(0, complete)
        except (tk.TclError, RuntimeError):
            # The application can close while the profile is being parsed.
            pass

    def _set_reference(self, entries, status):
        self._entries = entries
        self._load_status = status
        self._refresh_rows()

    def _refresh_rows(self, *args):
        search = self._search.get().strip()
        self._tree.configure(displaycolumns=self._columns if search else self._columns[:2])
        self._tree.delete(*self._tree.get_children())
        self._row_details.clear()
        self._tree.xview_moveto(0)
        self._tree.yview_moveto(0)
        rows = reference_rows(self._entries, GROUPS[self._groups.current()], search)
        for row in sorted(rows, key=lambda row: row.main_phrase.casefold()):
            count = f"+{len(row.other_phrases)}" if row.other_phrases else ""
            item = self._tree.insert("", "end", values=(row.main_phrase, count, self._group_labels[row.group]))
            self._row_details[item] = row
        self._show_details()

        status = self._load_status or ("empty" if not self._row_details else None)
        if status:
            self._notice.configure(text=t(f"voiceattack.reference_{status}"))
            self._notice.pack(fill="x", pady=(0, scaled_px(4)), before=self._tree.master)
        else:
            self._notice.pack_forget()

    def _show_details(self, event=None):
        selection = self._tree.selection()
        row = self._row_details.get(selection[0]) if selection else None
        lines = []
        if row and row.description:
            lines.append(row.description)
        if row and row.other_phrases:
            lines.append(t("voiceattack.reference_also_works") + " " + " · ".join(row.other_phrases))
        self._details.configure(state="normal")
        self._details.delete("1.0", "end")
        self._details.insert("1.0", "\n".join(lines))
        self._details.yview_moveto(0)
        self._details.configure(state="disabled")

    def _save_widths(self, event):
        widths = {column: self._tree.column(column, "width") for column in self._columns}
        if widths != self._widths:
            self._widths = widths
            update_config_value(_WIDTHS_KEY, widths)
