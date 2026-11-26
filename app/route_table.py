"""Table, plot feedback and clipboard helpers shared by both route panes."""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, ttk

from app_utils import create_action_button, open_system_website
from column_visibility_helper import ColumnVisibilityMixin, displayed_column
from core.constants import get_menu_colors
from config import scaled_font, scaled_px
from localization import t
from route_planner import parse_route, serialize_route
from ui.dialogs import centered_yesno_dialog
from ui.striped_treeview import StripedTreeview


class RouteTableMixin(ColumnVisibilityMixin):
    def _build_route_file_actions(self, config_key, button_colors):
        file_actions = ttk.Frame(self)
        file_actions.pack(fill="x", pady=(0, scaled_px(6)))
        self.export_button = create_action_button(file_actions, text=t("route.export"),
                                                  command=self._export_route, **button_colors)
        self.import_button = create_action_button(file_actions, text=t("route.import"),
                                                  command=self._import_route, **button_colors)
        for button in (self.export_button, self.import_button):
            button.pack(side="left", padx=(0, scaled_px(6)))
        self._cv_add_columns_button(file_actions, config_key)
        self.notice = tk.Label(file_actions, bg=self.colors["bg"], fg=self.colors["fg"], font=scaled_font(9))
        self.notice.pack(side="left")

    def _can_reverse_route(self):
        return not self.search.running and bool(self.source.get().strip() and self.destination.get().strip())

    def _update_reverse_button(self, *_args):
        self.reverse_button.configure(state="normal" if self._can_reverse_route() else "disabled")

    def _reverse_route(self):
        if self._can_reverse_route():
            source, destination = self.source.get(), self.destination.get()
            for autocomplete in self._autocomplete:
                autocomplete.hide()
            self.source.set(destination)
            self.destination.set(source)

    def _export_route_file(self, route, *, carrier=False):
        if not route:
            return
        filename = filedialog.asksaveasfilename(
            parent=self.app, title=t("route.export"), defaultextension="",
            filetypes=[(t("route.json_files"), "*.json"), (t("route.csv_files"), "*.csv"),
                       (t("route.text_files"), "*.txt")],
        )
        if not filename:
            return
        path = Path(filename)
        try:
            contents = serialize_route(route["stops"], path.suffix, carrier=carrier)
            path.write_text(contents, encoding="utf-8", newline="")
        except (OSError, ValueError):
            self.app._show_notice(self.notice, t("route.export_failed"), fg=self.colors["error"])

    def _import_route_file(self, route, *, carrier=False):
        if self.search.running:
            return
        filename = filedialog.askopenfilename(
            parent=self.app, title=t("route.import"),
            filetypes=[(t("route.route_files"), ("*.json", "*.csv", "*.txt"))],
        )
        if not filename:
            return
        path = Path(filename)
        try:
            stops = parse_route(path.read_text(encoding="utf-8-sig"), path.suffix, carrier=carrier)
        except (OSError, ValueError, RecursionError):
            self.app._show_notice(self.notice, t("route.import_failed"), fg=self.colors["error"])
            return
        if route and not centered_yesno_dialog(self.app, t("tabs.route"), t("route.replace")):
            return
        return stops

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
        self.tree.bind("<Button-3>", self._show_row_menu)
        self.tree.bind("<Double-1>", self._open_system_inara)

    def _show_row_menu(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.tree.selection_set(row)
        system = self.tree.set(row, "system")
        menu = tk.Menu(self.tree, tearoff=0, **get_menu_colors())
        menu.add_command(label=t("context_menu.copy_system"), command=lambda: self._copy_system(system))
        menu.add_command(label=t("context_menu.find_hotspots"), command=lambda: self._show_system_hotspots(system))
        menu.add_separator()
        for site in ("inara", "edsm", "spansh"):
            menu.add_command(label=t(f"context_menu.open_{site}"),
                             command=lambda site=site: open_system_website(system, site))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_system_inara(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if displayed_column(self.tree, self.tree.identify_column(event.x)) != "system":
            return
        row = self.tree.identify_row(event.y)
        if row:
            open_system_website(self.tree.set(row, "system"))

    def _show_system_hotspots(self, system):
        self.app.switch_to_tab("hotspots_finder")
        ring_finder = self.app.ring_finder
        ring_finder.system_var.set(system)
        ring_finder.min_hotspots_var.set("1")
        ring_finder.distance_var.set("100")
        ring_finder.max_results_var.set("200")
        ring_finder._show_results_view("hotspots")
        self.after(100, ring_finder.search_hotspots)

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
