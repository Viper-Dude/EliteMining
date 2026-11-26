"""Table, plot feedback and clipboard helpers shared by both route panes."""

import tkinter as tk
from tkinter import font, ttk

from column_visibility_helper import ColumnVisibilityMixin
from config import scaled_font, scaled_px
from localization import t
from ui.striped_treeview import StripedTreeview


class RouteTableMixin(ColumnVisibilityMixin):
    def _build_route_table(self, widths, header_keys, config_key):
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        self.tree = StripedTreeview(frame, columns=tuple(widths), show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        tree_style = ttk.Style(self)
        overlay_bg = tree_style.lookup("Treeview", "fieldbackground") or self.colors["bg"]
        overlay_fg = tree_style.lookup("Treeview", "foreground") or self.colors["fg"]
        self._plot_overlay = tk.Frame(frame, bg=overlay_bg)
        self._plot_overlay_label = tk.Label(self._plot_overlay, bg=overlay_bg, fg=overlay_fg,
                                            font=scaled_font(14, "bold"), justify="center",
                                            wraplength=scaled_px(600))
        self._plot_overlay_label.place(relx=0.5, rely=0.5, anchor="center")
        self._plot_overlay_text = ""
        self._plot_spin = 0

        heading_font = font.Font(root=self, font=ttk.Style(self).lookup("Treeview.Heading", "font"))
        for column, width in widths.items():
            header = t(header_keys.get(column, f"route.column_{column}"))
            minimum = heading_font.measure(header)
            if column == "number":
                minimum = max(minimum, heading_font.measure("▷ 999"))
            minimum += scaled_px(16)
            self.tree.heading(column, text=header, anchor="w")
            self.tree.column(column, width=max(minimum, scaled_px(width)),
                             minwidth=minimum, anchor="w", stretch=False)

        self.setup_column_visibility(
            self.tree, tuple(widths), {column: self.tree.column(column, "width") for column in widths},
            config_key, use_displaycolumns=True, allow_reorder=True, persist_widths=True,
        )

    def _spin_plot_overlay(self):
        if not self.search.running:
            return
        chars = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        self._plot_spin += 1
        spinner = chars[self._plot_spin % len(chars)]
        self._plot_overlay_label.configure(text=f"{self._plot_overlay_text}\n\n{spinner}")
        self.after(100, self._spin_plot_overlay)

    def _wait_for_plot(self, future, *args):
        if future.done():
            self.search.complete(None, self._finish_plot, future, *args)
        else:
            self.after(100, self._wait_for_plot, future, *args)

    def _plot_idle(self):
        self._plot_overlay.grid_remove()
        if self.search.is_cancelled():
            self.app._show_notice(self.notice, t("ring_finder.search_stopped"), fg=self.colors["fg"])
        self._update_buttons()

    def _copy_system(self, system):
        self.clipboard_clear()
        self.clipboard_append(system)
        self.app._show_notice(self.notice, t("route.copied").format(system=system), fg=self.colors["fg"])
