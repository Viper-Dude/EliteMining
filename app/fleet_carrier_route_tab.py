"""Plot and display the player's Fleet Carrier route."""

import logging
from math import ceil
import threading
import tkinter as tk
from tkinter import ttk

from app_utils import create_action_button
from config import load_theme, scaled_font, scaled_px
from core.constants import get_menu_colors
from edsm_distance import SOL_COORDS, get_distance_calculator
from fleet_carrier_tracker import get_fleet_carrier_tracker
from localization import t
from route_planner import PLAYER_CARRIER_CAPACITY
from route_table import RouteTableMixin
from system_autocomplete import SystemAutocomplete
from ui.search_control import SearchControl
from ui.theme import get_theme_colors


log = logging.getLogger("EliteMining")
_TABLE_KEY = "carrier_route"


def _format_amount(value, spec=",.0f"):
    return "" if value is None else format(value, spec)


def _route_total(stops, field, unit, spec=",.0f"):
    values = [stop.get(field) for stop in stops]
    if None in values:
        return t("route.carrier_unknown")
    return f"{_format_amount(sum(values), spec)} {unit}"


class FleetCarrierRouteTab(ttk.Frame, RouteTableMixin):
    def __init__(self, parent, app):
        super().__init__(parent, padding=scaled_px(8))
        self.app = app
        self.cargo = app.cargo_monitor
        self.planner = self.cargo.route_planner
        self.tracker = get_fleet_carrier_tracker()
        self.colors = get_theme_colors(load_theme())
        self._default_source = ""
        self._capacity_edited = False
        self._refresh_job = None
        self._jump_job = None
        self.source = tk.StringVar(self)
        saved_route = self.planner.active_carrier_route
        self.destination = tk.StringVar(self, saved_route["stops"][-1]["name"] if saved_route else "")
        self.used_capacity = tk.StringVar(self)
        self.entries = []
        self._autocomplete = []

        fields = ttk.Frame(self)
        fields.pack(fill="x")
        fields.columnconfigure(0, minsize=scaled_px(80))
        fields.columnconfigure(1, minsize=scaled_px(250))
        for row, (key, variable) in enumerate((("from", self.source), ("to", self.destination))):
            ttk.Label(fields, text=t(f"route.{key}"), font=scaled_font(9)).grid(
                row=row, column=0, sticky="w", pady=scaled_px(3))
            entry = ttk.Entry(fields, textvariable=variable, width=1, font=scaled_font(9))
            entry.grid(row=row, column=1, padx=scaled_px(5), pady=scaled_px(3), sticky="ew")
            entry.bind("<FocusOut>", lambda event: event.widget.selection_clear(), add="+")
            entry.bind("<Return>", lambda event: None if self.search.running else self._plot_or_stop(), add="+")
            self.entries.append(entry)
            self._autocomplete.append(SystemAutocomplete(entry, variable, app))

        capacity_row = ttk.Frame(self)
        capacity_row.pack(anchor="w", pady=(scaled_px(5), 0))
        self.carrier_info_label = ttk.Label(capacity_row)
        self.carrier_info_label.pack(side="left", padx=(0, scaled_px(16)))
        ttk.Label(capacity_row, text=t("route.carrier_capacity")).pack(side="left", padx=(0, scaled_px(5)))
        self.capacity_entry = ttk.Entry(
            capacity_row, textvariable=self.used_capacity, width=6, font=scaled_font(9),
            validate="key", validatecommand=(self.register(self._validate_capacity), "%P"),
        )
        self.capacity_entry.pack(side="left", padx=(0, scaled_px(4)))
        self.capacity_entry.bind("<FocusOut>", lambda event: self.after_idle(self._refresh_inputs), add="+")
        self.entries.append(self.capacity_entry)
        ttk.Label(capacity_row, text=t("route.cargo_unit")).pack(side="left")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=scaled_px(6))
        button_colors = dict(bg=self.colors["btn_bg"], fg=self.colors["btn_fg"],
                             activebackground=self.colors["btn_bg_hover"], activeforeground=self.colors["btn_fg"],
                             disabledforeground=self.colors["btn_fg_disabled"])
        plot_button = create_action_button(actions, text=t("route.plot"), primary=True,
                                           command=self._plot_or_stop, **button_colors)
        self.copy_button = create_action_button(actions, text=t("route.copy_next"),
                                                command=self._copy_next, **button_colors)
        self.clear_button = create_action_button(actions, text=t("route.clear"),
                                                 command=self._clear, **button_colors)
        for button in (plot_button, self.copy_button, self.clear_button):
            button.pack(side="left", padx=(0, scaled_px(6)))
        self._cv_add_columns_button(actions, _TABLE_KEY)
        self.notice = tk.Label(actions, bg=self.colors["bg"], fg=self.colors["fg"], font=scaled_font(9))
        self.notice.pack(side="left")
        self.search = SearchControl(self, plot_button, self.notice, on_finish=self._plot_idle)

        summary = ttk.Frame(self)
        summary.pack(side="bottom", fill="x", pady=(scaled_px(5), 0))
        summary.columnconfigure(0, weight=1)
        self.totals = ttk.Label(summary)
        self.totals.grid(row=0, column=0, sticky="ew")
        self.totals.bind("<Configure>", lambda event: self.totals.configure(wraplength=event.width))
        self.tank_fuel = ttk.Label(summary)
        self.tank_fuel.grid(row=0, column=1, sticky="ne", padx=(scaled_px(12), 0))
        self._build_table()
        self._refresh_inputs()
        self._show_route(saved_route)
        self.bind("<Map>", self._refresh)
        self.bind("<Unmap>", self._pause_refresh)
        self.bind("<Destroy>", self._stop_tracking)
        self.tracker.set_on_route_updated(self._on_carrier_updated)
        self._on_carrier_updated()

    def _build_table(self):
        widths = {
            "number": 55, "system": 280, "jump": 80, "jumps_left": 90,
            "fuel_used": 90, "fuel_left": 90, "restock": 70, "restock_amount": 110,
            "icy_ring": 95, "tritium_hotspots": 125, "sol": 120,
        }
        self._build_route_table(widths, {"sol": "ring_finder.col_sol_dist"}, _TABLE_KEY)
        self.tree.bind("<Button-3>", self._show_row_menu)

    def _validate_capacity(self, value):
        if value and (len(value) > 5 or not value.isdecimal() or int(value) > PLAYER_CARRIER_CAPACITY):
            return False
        self._capacity_edited = bool(value)
        return True

    def _refresh_inputs(self):
        data = self.tracker.carrier_data or {}
        name, callsign = data.get("name"), data.get("callsign")
        identity = f"{name} ({callsign})" if name and callsign else name or callsign or ""
        self.carrier_info_label.configure(text=identity)
        system = data.get("system") or ""
        if system != self._default_source and self.source.get() == self._default_source:
            self._autocomplete[0].hide()
            self.source.set(system)
        self._default_source = system

        total, free = data.get("space_total"), data.get("space_free")
        if not self._capacity_edited and self.focus_get() != self.capacity_entry:
            used = total - free if total is not None and free is not None else None
            self.used_capacity.set(str(used) if used is not None else "")
        fuel = data.get("fuel_level")
        fuel_text = (f"{_format_amount(fuel)} {t('route.cargo_unit')}" if fuel is not None
                     else t("route.carrier_unknown"))
        self.tank_fuel.configure(text=t("route.carrier_tank_fuel").format(fuel=fuel_text))

    def _refresh(self, event=None):
        self._refresh_inputs()
        self._refresh_job = self.after(1000, self._refresh)

    def _pause_refresh(self, event):
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
            self._refresh_job = None
        for autocomplete in self._autocomplete:
            autocomplete.hide()

    def _on_carrier_updated(self):
        self.after(0, self._sync_carrier_progress)

    def _cancel_jump_timer(self):
        if self._jump_job is not None:
            self.after_cancel(self._jump_job)
            self._jump_job = None

    def _stop_tracking(self, event):
        self.tracker.set_on_route_updated(None)
        self._cancel_jump_timer()

    def _sync_carrier_progress(self):
        self._cancel_jump_timer()
        previous = self.planner.active_carrier_route
        # A queued callback or timer must read the request that is still current.
        delay = self.planner.sync_carrier_progress(self.tracker.route_snapshot())
        route = self.planner.active_carrier_route
        if route is not previous:
            self._show_progress(route, previous)
            self._update_buttons()
        if delay is not None:
            self._jump_job = self.after(ceil(delay * 1000), self._jump_timer_fired)

    def _jump_timer_fired(self):
        self._jump_job = None
        self._sync_carrier_progress()

    def _plot_or_stop(self):
        if self.search.running:
            self.search.stop()
            return
        source, destination = self.source.get().strip(), self.destination.get().strip()
        capacity = self.used_capacity.get()
        if not source or not destination:
            message = "route.enter_systems"
        elif source.casefold() == destination.casefold():
            message = "route.carrier_same_system"
        elif not capacity.isdecimal() or int(capacity) > PLAYER_CARRIER_CAPACITY:
            message = "route.carrier_enter_capacity"
        elif self.planner.plot_running:
            message = "route.plot_busy"
        else:
            self._plot(source, destination, int(capacity))
            return
        self.app._show_notice(self.notice, t(message), fg=self.colors["warning"])

    def _plot(self, source, destination, capacity):
        for autocomplete in self._autocomplete:
            autocomplete.hide()
        self.search.start()
        self._update_buttons()
        self._plot_overlay_text = t("route.plotting_to").format(system=destination)
        self._plot_overlay.grid(row=0, column=0, sticky="nsew")
        self._plot_overlay.tkraise()
        self._spin_plot_overlay()
        self.app._show_notice(self.notice, t("route.plotting"), clear_after=0, fg=self.colors["fg"])
        fuel = (self.tracker.carrier_data or {}).get("fuel_level")
        future = self.planner.plot_carrier(source, destination, capacity, self.search.is_cancelled, fuel_level=fuel)
        self._wait_for_plot(future)

    def _finish_plot(self, _results, future):
        try:
            stops = future.result()
        except TimeoutError:
            self.app._show_notice(self.notice, t("route.timeout"), fg=self.colors["error"])
        except Exception:
            log.exception("Fleet Carrier route plot failed")
            self.app._show_notice(self.notice, t("route.plot_failed"), fg=self.colors["error"])
        else:
            self.planner.set_carrier_route(stops)
            self.app._show_notice(self.notice, "")
            self._show_route(self.planner.active_carrier_route)
            self._sync_carrier_progress()

    def _show_route(self, route):
        self.tree.delete(*self.tree.get_children())
        self.totals.configure(text="")
        if route:
            stops = route["stops"]
            jumps = len(stops) - 1
            calculator = get_distance_calculator()
            for index, stop in enumerate(stops):
                icy_ring = ""
                if stop.get("has_icy_ring"):
                    icy_ring = t("ring_finder.reserve_pristine" if stop.get("is_system_pristine") else "common.yes")
                self.tree.insert("", "end", iid=str(index), values=(
                    index, stop["name"],
                    _format_amount(stop.get("distance"), ".2f"), jumps - index,
                    _format_amount(stop.get("fuel_used")), _format_amount(stop.get("fuel_in_tank")),
                    t("common.yes") if stop.get("must_restock") else "",
                    _format_amount(stop.get("restock_amount")), icy_ring, "",
                    _format_amount(calculator.calculate_distance(stop, SOL_COORDS), ".2f"),
                ))
            tonnes = t("route.cargo_unit")
            hours, minutes = divmod(jumps * 20, 60)
            self.totals.configure(text=t("route.carrier_totals").format(
                jumps=jumps, hours=hours, minutes=minutes,
                distance=_route_total(stops[1:], "distance", t("route.ly_unit"), ".2f"),
                fuel_used=_route_total(stops, "fuel_used", tonnes),
                restock=_route_total(stops, "restock_amount", tonnes),
            ))
            self._show_progress(route)
            self._load_hotspots(route)
        self._update_buttons()

    def _show_progress(self, route, previous=None):
        current = route["current_index"]
        off_route = route["off_route"]
        if previous:
            old_index = previous["current_index"]
            if old_index == current and previous["off_route"] == off_route:
                return
            self.tree.set(str(old_index), "number", old_index)
        self.tree.set(str(current), "number", current if off_route else f"▷ {current}")
        self.tree.see(str(current))
        if not self.search.running:
            if off_route:
                self.app._show_notice(self.notice, t("route.off_route"), fg=self.colors["warning"])
            elif previous and previous["off_route"]:
                self.app._show_notice(self.notice, "")

    def _load_hotspots(self, route):
        systems = [stop["name"] for stop in route["stops"]]
        user_db = self.cargo.user_db

        def read_hotspots():
            hotspots = user_db.bulk_get_hotspot_counts_for_systems(systems)
            self.after(0, self._show_hotspots, route, systems, hotspots)

        self.after(0, threading.Thread(target=read_hotspots, daemon=True).start)

    def _show_hotspots(self, route, systems, hotspots):
        active = self.planner.active_carrier_route
        if active and route["stops"] is active["stops"]:
            for index, system in enumerate(systems):
                count = hotspots.get(system, {}).get("Tritium")
                self.tree.set(str(index), "tritium_hotspots", _format_amount(count))

    def _update_buttons(self):
        route = self.planner.active_carrier_route
        self.copy_button.configure(state="normal" if self._next_system() else "disabled")
        self.clear_button.configure(state="normal" if route and not self.search.running else "disabled")

    def _next_system(self):
        route = self.planner.active_carrier_route
        if route and route["current_index"] + 1 < len(route["stops"]):
            return route["stops"][route["current_index"] + 1]["name"]
        return ""

    def _copy_next(self):
        system = self._next_system()
        if system:
            self._copy_system(system)

    def _show_row_menu(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        row = self.tree.identify_row(event.y)
        if row:
            self.tree.selection_set(row)
            system = self.tree.set(row, "system")
            menu = tk.Menu(self.tree, tearoff=0, **get_menu_colors())
            menu.add_command(label=t("context_menu.copy_system"), command=lambda: self._copy_system(system))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

    def _clear(self):
        self._cancel_jump_timer()
        self.planner.clear_carrier_route()
        self._show_route(None)
        self.app._show_notice(self.notice, t("route.cleared"), fg=self.colors["fg"])
