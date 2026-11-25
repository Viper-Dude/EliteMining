"""Plot, share and follow the active route."""

import logging
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, ttk

from app_utils import create_action_button
from column_visibility_helper import ColumnVisibilityMixin
from config import _load_cfg, load_theme, scaled_font, scaled_px, update_config_value
from core.constants import get_menu_colors
from localization import t
from route_planner import build_route_form, jump_range, parse_route, serialize_route
from system_autocomplete import SystemAutocomplete
from ui.dialogs import centered_yesno_dialog
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from ui.theme import get_theme_colors
from ui.themed_checkbox import ThemedCheckbutton
from ui.tooltip import ToolTip, add_header_tooltips


log = logging.getLogger("EliteMining")

_INJECTION_GRADES = (("off", None), ("basic", 1.25), ("standard", 1.5), ("premium", 2))


class RouteTab(ttk.Frame, ColumnVisibilityMixin):
    def __init__(self, app):
        super().__init__(app.notebook, padding=scaled_px(8))
        self.app = app
        self.cargo = app.cargo_monitor
        self.planner = self.cargo.route_planner
        self.colors = get_theme_colors(load_theme())
        self._default_source = self._current_system()
        self.source = tk.StringVar(self, self._default_source)
        self.destination = tk.StringVar(self)
        self.use_supercharge = tk.BooleanVar(self, True)
        self.copy_after_jump = tk.BooleanVar(self, _load_cfg().get("route_copy_after_jump", True))
        self._cargo_edited = False
        self.cargo_input = tk.StringVar(self, str(self._route_cargo()))
        self._displayed_route = None
        self._refresh_job = None

        button_colors = dict(bg=self.colors["btn_bg"], fg=self.colors["btn_fg"],
                             activebackground=self.colors["btn_bg_hover"], activeforeground=self.colors["btn_fg"],
                             disabledforeground=self.colors["btn_fg_disabled"])
        fields = ttk.Frame(self)
        fields.pack(fill="x")
        fields.columnconfigure(0, minsize=scaled_px(80))
        fields.columnconfigure(1, minsize=scaled_px(250))
        fields.columnconfigure(2, weight=1)
        self._autocomplete = []
        for row, (key, var) in enumerate((("from", self.source), ("to", self.destination))):
            ttk.Label(fields, text=t(f"route.{key}"), font=scaled_font(9)).grid(
                row=row, column=0, sticky="w", pady=scaled_px(3))
            entry = ttk.Entry(fields, textvariable=var, width=1, font=scaled_font(9))
            entry.grid(row=row, column=1, padx=scaled_px(5), pady=scaled_px(3), sticky="ew")
            entry.bind("<FocusOut>", lambda event: event.widget.selection_clear(), add="+")
            entry.bind("<Map>", lambda event: self.after_idle(self._clear_system_focus, event.widget), add="+")
            self._autocomplete.append(SystemAutocomplete(entry, var, app))
        current_button = create_action_button(fields, text=t("distance_calculator.use_current"),
                                              command=self._use_current_system, **button_colors)
        current_button.grid(row=0, column=2, sticky="w", padx=(scaled_px(5), 0))
        ToolTip(current_button, t("tooltips.use_current"), preserve_bindings=True)

        options = ttk.Frame(self)
        options.pack(fill="x", pady=scaled_px(5))
        supercharge = ThemedCheckbutton(options, text=t("route.supercharge"), variable=self.use_supercharge,
                                        font=scaled_font(9), bg=self.colors["bg"], fg=self.colors["fg"])
        supercharge.pack(side="left", padx=(0, scaled_px(12)))
        ToolTip(supercharge, t("route.tips.supercharge"))

        ttk.Label(options, text=t("route.injections")).pack(side="left", padx=(0, scaled_px(5)))
        grades = tuple(t(f"route.injection_{grade}") for grade, _ in _INJECTION_GRADES)
        self.injection_grade = ttk.Combobox(options, values=grades, state="readonly",
                                            width=max(map(len, grades)), font=scaled_font(9))
        self.injection_grade.current(0)
        self.injection_grade.pack(side="left")
        ToolTip(self.injection_grade, t("route.tips.injections"))

        ship_info = ttk.Frame(self)
        ship_info.pack(anchor="w")
        self.range_label = ttk.Label(ship_info)
        self.range_label.pack(side="left", padx=(0, scaled_px(16)))
        ToolTip(self.range_label, t("route.tips.range"))
        ttk.Label(ship_info, text=t("route.cargo")).pack(side="left", padx=(0, scaled_px(5)))
        cargo_entry = ttk.Entry(ship_info, textvariable=self.cargo_input, width=5, font=scaled_font(9),
                                validate="key", validatecommand=(self.register(self._validate_cargo), "%P"))
        cargo_entry.pack(side="left", padx=(0, scaled_px(4)))
        cargo_entry.bind("<FocusOut>", lambda event: self.cargo_input.set(
            self.cargo_input.get() or str(self._route_cargo())))
        ttk.Label(ship_info, text=t("route.cargo_unit")).pack(side="left")
        ToolTip(cargo_entry, t("route.tips.cargo"))

        copy_after_jump = ThemedCheckbutton(
            self, text=t("route.copy_after_jump"), variable=self.copy_after_jump,
            command=lambda: update_config_value("route_copy_after_jump", self.copy_after_jump.get()),
            font=scaled_font(9), bg=self.colors["bg"], fg=self.colors["fg"],
        )
        copy_after_jump.pack(anchor="w", pady=(scaled_px(5), 0))
        ToolTip(copy_after_jump, t("route.tips.copy_after_jump"))

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=scaled_px(6))
        plot_button = create_action_button(actions, text=t("route.plot"), primary=True,
                                           command=self._plot_or_stop, **button_colors)
        self.copy_button = create_action_button(actions, text=t("route.copy_next"),
                                                command=self._copy_next, **button_colors)
        self.clear_button = create_action_button(actions, text=t("route.clear"),
                                                 command=self._clear, **button_colors)
        for button, key in ((plot_button, "plot"), (self.copy_button, "copy_next"), (self.clear_button, "clear")):
            button.pack(side="left", padx=(0, scaled_px(6)))
            ToolTip(button, t(f"route.tips.{key}"), preserve_bindings=True)
        self.export_button = create_action_button(actions, text=t("route.export"),
                                                  command=self._export_route, **button_colors)
        self.import_button = create_action_button(actions, text=t("route.import"),
                                                  command=self._import_route, **button_colors)
        for button in (self.export_button, self.import_button):
            button.pack(side="left", padx=(0, scaled_px(6)))
        self._cv_add_columns_button(actions, "route")
        self.notice = tk.Label(actions, bg=self.colors["bg"], fg=self.colors["fg"], font=scaled_font(9))
        self.notice.pack(side="left")
        self.search = SearchControl(self, plot_button, self.notice, on_finish=self._plot_idle)

        help_label = ttk.Label(self, text=t("route.help"), justify="left")
        help_label.pack(side="bottom", fill="x", pady=(scaled_px(4), 0))
        help_label.bind("<Configure>", lambda event: help_label.configure(wraplength=event.width))
        self.totals = ttk.Label(self)
        self.totals.pack(side="bottom", anchor="w", pady=(scaled_px(5), 0))
        ToolTip(self.totals, t("route.tips.totals"))
        self._build_table()
        self._show_route(self.planner.active_route)
        self._publish_route_progress()
        self.cargo.add_journal_listener(self._on_journal_events)
        self.bind("<Map>", self._refresh)
        self.bind("<Unmap>", self._pause_refresh)

    def _build_table(self):
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        widths = {"number": 55, "system": 280, "jump": 80,
                  "star": 125, "refuel": 68, "inject": 68, "jumps_left": 90}
        self.tree = StripedTreeview(frame, columns=tuple(widths), show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)

        heading_font = font.Font(root=self, font=ttk.Style(self).lookup("Treeview.Heading", "font"))
        for column, width in widths.items():
            header = t(f"route.column_{column}")
            minimum = heading_font.measure(header)
            if column == "number":
                minimum = max(minimum, heading_font.measure("▷ 999"))
            minimum += scaled_px(16)
            self.tree.heading(column, text=header, anchor="w")
            self.tree.column(column, width=max(minimum, scaled_px(width)),
                             minwidth=minimum, anchor="w", stretch=False)

        self.setup_column_visibility(
            self.tree, tuple(widths), {column: self.tree.column(column, "width") for column in widths},
            "route", use_displaycolumns=True, allow_reorder=True, persist_widths=True,
        )
        add_header_tooltips(self.tree, lambda column: t(f"route.header_tips.{column}"))
        self.tree.bind("<Button-3>", self._show_row_menu)

    def _current_system(self):
        return self.app.get_current_system() or self.cargo.current_system or ""

    def _use_current_system(self):
        current = self._current_system()
        if current:
            self.app._distance_fill(self._autocomplete[0], self.source, current)
            self._default_source = current
            self.app._show_notice(self.notice, t("distance_calculator.using_current").format(system=current),
                                  fg=self.colors["fg"])
        else:
            self.app._show_notice(self.notice, t("distance_calculator.no_current"), fg=self.colors["warning"])

    def _clear_system_focus(self, entry):
        if entry.focus_get() == entry:
            self.master.focus_set()
        entry.selection_clear()

    def _refresh(self, event=None):
        current = self._current_system()
        if current != self._default_source and self.source.get() == self._default_source:
            self._autocomplete[0].hide()
            self.source.set(current)
        self._default_source = current
        cargo = self._route_cargo()
        cargo_text = self.cargo_input.get()
        if cargo_text and int(cargo_text) != cargo:
            self.cargo_input.set(str(cargo))
        self._update_jump_range(cargo)
        if self.planner.active_route is not self._displayed_route:
            self._show_route(self.planner.active_route)
        self._refresh_job = self.after(1000, self._refresh)

    def _route_cargo(self):
        cargo = int(self.cargo_input.get() or "0") if self._cargo_edited else self.cargo.current_cargo
        return min(max(0, cargo), self.cargo.max_cargo)

    def _validate_cargo(self, value):
        capacity = self.cargo.max_cargo
        if value and (len(value) > len(str(capacity)) or not value.isdecimal() or int(value) > capacity):
            return False
        self._cargo_edited = bool(value)
        self._update_jump_range(int(value) if value else self._route_cargo())
        return True

    def _update_jump_range(self, cargo):
        loadout = self.cargo.latest_loadout
        fuel = self.cargo.fuel_main
        if fuel is None and loadout:
            fuel = (loadout.get("FuelCapacity") or {}).get("Main")
        range_text = t("route.range_unavailable")
        if loadout and fuel is not None:
            try:
                current_range = jump_range(loadout, fuel, cargo)
                range_text = t("route.range").format(current=current_range, maximum=loadout["MaxJumpRange"])
            except (ValueError, KeyError):
                pass
        self.range_label.configure(text=range_text)

    def _pause_refresh(self, event):
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
        for autocomplete in self._autocomplete:
            autocomplete.hide()

    def _show_route(self, route):
        self._displayed_route = route
        self.tree.delete(*self.tree.get_children())
        self.totals.configure(text="")
        if route:
            stops = route["stops"]
            current = route["current_index"]
            off_route = route["off_route"]
            distance = 0
            for index, stop in enumerate(stops):
                jump = stop.get("distance")
                if index and jump is not None:
                    distance += jump
                stars = []
                if stop.get("is_scoopable"):
                    stars.append(t("route.scoopable"))
                if stop.get("has_neutron"):
                    stars.append(t("route.neutron"))
                self.tree.insert("", "end", iid=str(index), values=(
                    f"▷ {index}" if index == current and not off_route else index, stop["name"],
                    f"{jump:.2f}" if jump is not None else "", ", ".join(stars),
                    t("common.yes") if stop.get("must_refuel") else "",
                    t("common.yes") if stop.get("must_inject") else "", len(stops) - index - 1,
                ))
            self.tree.see(str(current))
            jumps = len(stops) - 1
            # Spansh estimates one minute per jump and two extra per refuel stop.
            minutes = jumps + 2 * sum(bool(stop.get("must_refuel")) for stop in stops[1:])
            self.totals.configure(text=t("route.totals").format(jumps=jumps, distance=distance, minutes=minutes))
            if off_route:
                self.app._show_notice(self.notice, t("route.off_route"), fg=self.colors["warning"])
        self._update_buttons()

    def _update_buttons(self):
        route = self.planner.active_route
        has_next = route and route["current_index"] + 1 < len(route["stops"])
        self.copy_button.configure(state="normal" if has_next else "disabled")
        self.clear_button.configure(state="normal" if route and not self.search.running else "disabled")
        self.export_button.configure(state="normal" if route else "disabled")
        self.import_button.configure(state="disabled" if self.search.running else "normal")

    def _plot_or_stop(self):
        if self.search.running:
            self.search.stop()
            return
        self._plot(self.source.get().strip(), self.destination.get().strip(), cargo=self._route_cargo())

    def plot_sale_route(self, systems, sold_first):
        first, *remaining = systems
        self.plot_to_system(first, source_view="sell_hold", second=remaining[0] if remaining else None,
                            sold_first=sold_first)

    def plot_to_system(self, destination, *, source_view, second=None, sold_first=0):
        self.app.notebook.select(self)
        if not self.search.running:
            self._plot(self._current_system().strip(), destination, second=second,
                       sold_first=sold_first, source_view=source_view)

    def _plot(self, source, destination, *, cargo=None, second=None, sold_first=0, source_view="route"):
        if not source or not destination:
            self.app._show_notice(self.notice, t("route.enter_systems"), fg=self.colors["warning"])
            return
        loadout = self.cargo.latest_loadout
        if cargo is None:
            cargo = self.cargo.current_cargo
        _, multiplier = _INJECTION_GRADES[self.injection_grade.current()]
        options = dict(use_supercharge=self.use_supercharge.get(),
                       use_injections_when_required=multiplier is not None, injection_multiplier=multiplier)
        try:
            form = build_route_form(
                loadout, source, destination, cargo, **options,
                is_supercharged=self.planner.is_supercharged and source.casefold() == self._current_system().casefold(),
            )
            second_form = (build_route_form(loadout, destination, second, max(0, cargo - sold_first), **options)
                           if second else None)
        except (ValueError, KeyError):
            self.app._show_notice(self.notice, t("route.ship_unavailable"), fg=self.colors["warning"])
            return
        for autocomplete in self._autocomplete:
            autocomplete.hide()
        if self.planner.active_route and not centered_yesno_dialog(
                self.app, t("tabs.route"), t("route.replace")):
            return

        if source_view != "route":
            self.source.set(source)
            self.destination.set(second or destination)
        self.search.start()
        self._update_buttons()
        self.app._show_notice(self.notice, t("route.plotting"), clear_after=0, fg=self.colors["fg"])
        future = self.planner.plot(form, self.search.is_cancelled, second_form=second_form)
        self._wait_for_plot(future, source_view)

    def _wait_for_plot(self, future, source_view):
        if future.done():
            self.search.complete(None, self._finish_plot, future, source_view)
        else:
            self.after(100, self._wait_for_plot, future, source_view)

    def _finish_plot(self, _results, future, source_view):
        try:
            stops = future.result()
        except TimeoutError:
            self.app._show_notice(self.notice, t("route.timeout"), fg=self.colors["error"])
        except Exception:
            log.exception("Route plot failed")
            self.app._show_notice(self.notice, t("route.plot_failed"), fg=self.colors["error"])
        else:
            self._apply_route(stops, source_view)
            if self.copy_after_jump.get():
                self._copy_next()

    def _apply_route(self, stops, source_view):
        self.app._show_notice(self.notice, "")
        self.planner.set_route(stops, source_view=source_view)
        self._show_route(self.planner.active_route)
        self._publish_route_progress()

    def _plot_idle(self):
        if self.search.is_cancelled():
            self.app._show_notice(self.notice, t("ring_finder.search_stopped"), fg=self.colors["fg"])
        self._update_buttons()

    def _export_route(self):
        route = self.planner.active_route
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
            contents = serialize_route(route["stops"], path.suffix)
            path.write_text(contents, encoding="utf-8", newline="")
        except (OSError, ValueError):
            self.app._show_notice(self.notice, t("route.export_failed"), fg=self.colors["error"])

    def _import_route(self):
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
            stops = parse_route(path.read_text(encoding="utf-8-sig"), path.suffix)
        except (OSError, ValueError, RecursionError):
            self.app._show_notice(self.notice, t("route.import_failed"), fg=self.colors["error"])
            return
        if self.planner.active_route and not centered_yesno_dialog(
                self.app, t("tabs.route"), t("route.replace")):
            return
        self._apply_route(stops, source_view="import")

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
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_next(self):
        route = self.planner.active_route
        if route and route["current_index"] + 1 < len(route["stops"]):
            self._copy_system(route["stops"][route["current_index"] + 1]["name"])

    def _copy_system(self, system):
        self.clipboard_clear()
        self.clipboard_append(system)
        self.app._show_notice(self.notice, t("route.copied").format(system=system), fg=self.colors["fg"])

    def _on_journal_events(self, events):
        # CargoMonitor delivers to the planner first, including when this tab is hidden.
        if self.planner.active_route and any(event.get("event") == "FSDJump" for event in events):
            self._publish_route_progress(jumped=True)

    def _publish_route_progress(self, *, jumped=False):
        route = self.planner.active_route
        system, jumps = "", 0
        if route:
            next_index = route["current_index"] + 1
            jumps = len(route["stops"]) - next_index
            if jumps:
                system = route["stops"][next_index]["name"]
        self.app._write_var_text("routeNextSystem", system)
        self.app._write_var_text("routeJumpsLeft", str(jumps))

        if jumped and system and not route["off_route"] and self.copy_after_jump.get():
            self._copy_system(system)

    def _clear(self):
        self.planner.clear_route()
        self._show_route(None)
        self._publish_route_progress()
        self.app._show_notice(self.notice, t("route.cleared"), fg=self.colors["fg"])
