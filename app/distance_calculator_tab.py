"""Distance Calculator tab (moved from main.py)."""

import logging
import threading
import tkinter as tk
from tkinter import ttk

from app_utils import create_action_button
from localization import t
from ui.theme import get_theme_colors
from ui.tooltip import ToolTip


class DistanceCalculatorTabMixin:
    def _build_distance_calculator_tab(self, frame: ttk.Frame) -> None:
        """Build the Distance Calculator tab"""
        from edsm_distance import get_distance_calculator
        from fleet_carrier_tracker import get_fleet_carrier_tracker
        from config import load_home_system, load_distance_calculator_systems, load_theme
        from system_autocomplete import SystemAutocomplete
        from ui.help_link import create_labelframe_title

        _dc_colors = self._dc_colors = get_theme_colors(load_theme())
        _dc_bg = _dc_colors["bg"]
        px = self._scaled_px

        self.distance_calculator = get_distance_calculator()
        self.fc_tracker = get_fleet_carrier_tracker()
        self._distance_calculation_generation = 0
        self._distance_update_generation = 0
        self._distance_update_pending = None
        self._distance_update_running = False
        self._distance_refresh_generation = 0
        self._distance_refresh_running = False
        self._distance_values = {}

        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        config_frame = ttk.LabelFrame(main_container, padding=10)
        config_frame.pack(fill="x", pady=(0, 10))
        config_frame.configure(labelwidget=create_labelframe_title(
            config_frame, t('distance_calculator.configuration'), "distance-calculator", t('distance_calculator.help_tooltip'), ToolTip))

        # Columns: label, system, distance info (expands), visits
        config_frame.columnconfigure(0, minsize=px(120))
        config_frame.columnconfigure(1, minsize=px(250))
        config_frame.columnconfigure(2, weight=1)
        config_frame.columnconfigure(3, minsize=px(80))

        def location_row(row, label_key, widget, tooltip_key, bold=False):
            ttk.Label(config_frame, text=t(label_key), font=self._scaled_font(9, "bold" if bold else "normal")).grid(row=row, column=0, sticky="w", pady=3)
            widget.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
            # Narrow so the Fleet Carrier tip doesn't cover the Refresh Locations button
            ToolTip(widget, t(tooltip_key), wraplength=px(220))
            info_frame = tk.Frame(config_frame, bg=_dc_bg)
            info_frame.grid(row=row, column=2, sticky="w", padx=(5, 0), pady=3)
            distance_label = tk.Label(info_frame, text="", font=self._scaled_font(9), fg=_dc_colors["value"], bg=_dc_bg, anchor="w")
            distance_label.pack(side="left")
            sol_label = tk.Label(info_frame, text="", font=self._scaled_font(9), fg=_dc_colors["fg_muted"], bg=_dc_bg, anchor="w")
            sol_label.pack(side="left", padx=(10, 0))
            visits_label = tk.Label(config_frame, text="", font=self._scaled_font(9), fg=_dc_colors["fg_muted"], bg=_dc_bg, anchor="e")
            visits_label.grid(row=row, column=3, sticky="e", padx=(5, 0), pady=3)
            return distance_label, sol_label, visits_label

        self.distance_current_system = tk.StringVar(value="---")
        current_display = tk.Label(config_frame, textvariable=self.distance_current_system, fg=_dc_colors["fg_bright"], bg=_dc_bg,
                                   font=self._scaled_font(9, "bold"), anchor="w", padx=px(3))
        self.current_sol_label, _, self.distance_visits_label = location_row(
            0, 'distance_calculator.current_system', current_display, 'tooltips.current_system', bold=True)

        self.distance_home_system = tk.StringVar(value=load_home_system())
        home_entry = tk.Entry(config_frame, textvariable=self.distance_home_system,
                              bg="#2d2d2d", fg="#ffffff", font=self._scaled_font(9), insertbackground="#ffffff")
        self.distance_to_home_label, self.home_sol_label, self.home_visits_label = location_row(
            1, 'distance_calculator.home_system', home_entry, 'tooltips.home_system')
        self._ac_home = SystemAutocomplete(home_entry, self.distance_home_system, self,
                                           on_select=lambda name: self._distance_set_home())
        home_entry.bind("<Return>", lambda e: (self._ac_home.hide(), self._distance_set_home(e)))
        # add='+' keeps the suggestion list's own FocusOut handler
        home_entry.bind('<FocusOut>', self._distance_home_focus_out, add='+')

        self.distance_fc_system = tk.StringVar(value="")
        fc_display = tk.Label(config_frame, textvariable=self.distance_fc_system, fg=_dc_colors["fg"], bg=_dc_bg,
                              font=self._scaled_font(9), anchor="w", padx=px(3))
        self.distance_to_fc_label, self.fc_sol_label, self.fc_visits_label = location_row(
            2, 'distance_calculator.fleet_carrier', fc_display, 'tooltips.fleet_carrier')

        self.distance_refresh_btn = create_action_button(config_frame, text=t('distance_calculator.refresh_locations'),
                               command=self._distance_refresh_locations)
        self.distance_refresh_btn.grid(row=3, column=0, columnspan=4, pady=(8, 0))
        ToolTip(self.distance_refresh_btn, t('tooltips.refresh_locations'))

        calc_frame = ttk.LabelFrame(main_container, text=t('distance_calculator.system_calculator'), padding=10)
        calc_frame.pack(fill="x", pady=(0, 10))
        calc_frame.columnconfigure(0, minsize=px(80))
        calc_frame.columnconfigure(1, minsize=px(250))
        calc_frame.columnconfigure(2, weight=1)

        def system_row(row, side, value, buttons):
            ttk.Label(calc_frame, text=t('distance_calculator.system_' + side), font=self._scaled_font(9)).grid(row=row, column=0, sticky="w", pady=3)
            var = tk.StringVar(value=value)
            var.trace_add('write', self._invalidate_distance_calculation)
            entry = tk.Entry(calc_frame, textvariable=var, bg="#2d2d2d", fg="#ffffff",
                             font=self._scaled_font(9), insertbackground="#ffffff")
            entry.grid(row=row, column=1, padx=(5, 5), pady=3, sticky="ew")
            entry.bind("<FocusOut>", lambda e: (self._save_distance_systems(), e.widget.selection_clear()))
            autocomplete = SystemAutocomplete(entry, var, self)
            entry.bind("<Return>", lambda e: (autocomplete.hide(), self._calculate_distances()))
            buttons_frame = tk.Frame(calc_frame, bg=_dc_bg)
            buttons_frame.grid(row=row, column=2, pady=3, padx=(5, 0), sticky="w")
            for text_key, tooltip_key, command in buttons:
                btn = create_action_button(buttons_frame, text=t('distance_calculator.' + text_key), command=command)
                btn.pack(side="left", padx=(0, 2))
                ToolTip(btn, t('tooltips.' + tooltip_key))
            return var, autocomplete

        saved_system_a, saved_system_b = load_distance_calculator_systems()
        self.distance_system_a, self._ac_system_a = system_row(0, 'a', saved_system_a, (
            ('use_current', 'use_current', self._distance_use_current_system),))
        self.distance_system_b, self._ac_system_b = system_row(1, 'b', saved_system_b, (
            ('home', 'use_home', self._distance_use_home),
            ('fc', 'use_fc', self._distance_use_fc)))

        calc_btn = create_action_button(calc_frame, primary=True, text=t('distance_calculator.calculate_distance'),
                                        command=self._calculate_distances)
        calc_btn.grid(row=2, column=0, columnspan=3, pady=(8, 3))
        ToolTip(calc_btn, t('tooltips.calculate_distance'))
        calc_frame.after(100, calc_btn.focus_set)

        self.distance_status_label = tk.Label(calc_frame, text="",
                                              font=self._scaled_font(8, "italic"), fg=_dc_colors["fg_muted"], bg=_dc_bg)
        self.distance_status_label.grid(row=3, column=0, columnspan=3, pady=(0, 5))

        results_frame = ttk.LabelFrame(main_container, text=t('distance_calculator.results'), padding=10)
        results_frame.pack(fill="x", pady=(0, 10))

        dist_row = tk.Frame(results_frame, bg=_dc_bg)
        dist_row.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        self.distance_ab_label = tk.Label(dist_row, text='➤ ' + t('distance_calculator.distance'),
                                         font=self._scaled_font(11, "bold"), fg=_dc_colors["fg"], bg=_dc_bg, anchor="w")
        self.distance_ab_label.pack(side="left")
        self.distance_ab_value_label = tk.Label(dist_row, text="---",
                                         font=self._scaled_font(14, "bold"), fg=_dc_colors["value"], bg=_dc_bg, anchor="w")
        self.distance_ab_value_label.pack(side="left", padx=(15, 0))

        tk.Frame(results_frame, height=1, bg=_dc_colors.get("border", "#444444")).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        for column, side in enumerate(('a', 'b')):
            name_label = tk.Label(results_frame, text=t('distance_calculator.system_' + side + '_info') + " ---",
                                  font=self._scaled_font(9, "bold"), fg=_dc_colors["fg"], bg=_dc_bg, anchor="w")
            name_label.grid(row=2, column=column, sticky="w", padx=(0, 20) if side == 'a' else 0, pady=(5, 0))
            setattr(self, 'distance_system_' + side + '_name', name_label)
            for row, (field, key) in enumerate(self._DISTANCE_RESULT_FIELDS, start=3):
                label = tk.Label(results_frame, text=t('distance_calculator.' + key) + " ---",
                                 font=self._scaled_font(9), fg=_dc_colors["fg_dim"], bg=_dc_bg, anchor="w")
                label.grid(row=row, column=column, sticky="w", padx=(10, 20) if side == 'a' else (10, 0))
                setattr(self, 'distance_' + side + '_' + field + '_label', label)

        results_frame.columnconfigure(0, weight=1)
        results_frame.columnconfigure(1, weight=1)

        self.after(1000, self._distance_load_carrier_on_startup)

    _DISTANCE_RESULT_FIELDS = (('sol', 'distance_to_sol'), ('visits', 'visits_label'), ('coords', 'coordinates'))

    def _distance_load_carrier_on_startup(self):
        carrier = self.fc_tracker.carrier_data or {}
        if carrier.get('system'):
            self.distance_fc_system.set(carrier['system'])
        self._update_home_fc_distances()

    def _distance_fill(self, autocomplete, var, value):
        autocomplete.suppress()
        var.set(value)
        autocomplete.unsuppress()
        autocomplete.hide()

    def _distance_use_current_system(self):
        current_system = self.get_current_system()
        if current_system:
            self._distance_fill(self._ac_system_a, self.distance_system_a, current_system)
            self._show_notice(self.distance_status_label, t('distance_calculator.using_current').format(system=current_system), fg=self._dc_colors['info'])
        else:
            self._show_notice(self.distance_status_label, t('distance_calculator.no_current'), fg=self._dc_colors['warning'])

    def _distance_use_home(self):
        home = self.distance_home_system.get().strip()
        if home:
            self._distance_fill(self._ac_system_b, self.distance_system_b, home)
        else:
            self._show_notice(self.distance_status_label, t('distance_calculator.no_home'), fg=self._dc_colors['warning'])

    def _distance_use_fc(self):
        fc = self.distance_fc_system.get().strip()
        if fc:
            self._distance_fill(self._ac_system_b, self.distance_system_b, fc)
        else:
            self._show_notice(self.distance_status_label, t('distance_calculator.no_carrier'), fg=self._dc_colors['warning'])

    def _distance_set_home(self, event=None):
        from config import load_home_system, save_home_system
        home = self.distance_home_system.get().strip()
        if home != load_home_system():
            save_home_system(home)
            key = 'distance_calculator.home_saved' if home else 'distance_calculator.home_cleared'
            self._show_notice(self.distance_status_label, t(key).format(system=home), fg=self._dc_colors['info'])
            self._update_home_fc_distances()

    def _distance_home_focus_out(self, event):
        event.widget.selection_clear()
        # Clicking a suggestion moves focus first; saving now would store the half-typed name.
        if not self._ac_home._mouse_over:
            self._distance_set_home(event)

    def _distance_refresh_locations(self):
        if self._distance_refresh_running:
            return
        parser = getattr(getattr(self, 'cargo_monitor', None), 'journal_parser', None)
        if not parser:
            self._show_notice(self.distance_status_label, t('distance_calculator.no_journal'), fg=self._dc_colors['warning'])
            return
        self._distance_refresh_running = True
        self.distance_refresh_btn.config(state='disabled', text=t('distance_calculator.refreshing'))
        self._distance_refresh_generation += 1
        generation = self._distance_refresh_generation
        initial_current = getattr(self, 'current_system', None)

        def scan_thread():
            try:
                current = parser.get_last_known_system()
                self.after(0, self._apply_distance_location_refresh, generation, initial_current, current)
            except Exception as exc:
                self.after(0, self._apply_distance_location_refresh, generation, initial_current, None, str(exc))
        threading.Thread(target=scan_thread, daemon=True).start()

    def _apply_distance_location_refresh(self, generation, initial_current, current, error=None):
        if generation != self._distance_refresh_generation:
            return
        self.after(350, self._finish_distance_location_refresh, generation)
        if error:
            self._show_notice(self.distance_status_label, t('distance_calculator.scan_failed').format(error=error), fg=self._dc_colors['error'])
            return
        if current and current != initial_current and getattr(self, 'current_system', None) == initial_current:
            self.update_current_system(current, count_visit=False)
        carrier = self.fc_tracker.carrier_data or {}
        self.distance_fc_system.set(carrier.get('system') or '')
        self._update_home_fc_distances()
        key = 'distance_calculator.locations_refreshed' if current or carrier.get('system') else 'distance_calculator.locations_missing'
        self._show_notice(self.distance_status_label, t(key), fg=self._dc_colors['info' if current or carrier.get('system') else 'warning'])

    def _finish_distance_location_refresh(self, generation):
        if generation == self._distance_refresh_generation:
            self._distance_refresh_running = False
            self.distance_refresh_btn.config(state='normal', text=t('distance_calculator.refresh_locations'))

    def _save_distance_systems(self):
        """Save System A and B to config"""
        try:
            from config import save_distance_calculator_systems
            system_a = self.distance_system_a.get().strip()
            system_b = self.distance_system_b.get().strip()
            save_distance_calculator_systems(system_a, system_b)
        except Exception as e:
            logging.getLogger('EliteMining').exception('Could not save distance calculator systems')

    def _invalidate_distance_calculation(self, *args):
        self._distance_calculation_generation += 1
        # The running result is now dropped, so its "Calculating..." notice would never clear.
        label = getattr(self, 'distance_status_label', None)
        if label is not None and label.cget('text') == t('distance_calculator.calculating'):
            label.config(text='')

    def _distance_coordinate_lookup(self, system_name, current_system, current_coords):
        from edsm_distance import SOL_COORDS
        if system_name.casefold() == 'sol':
            return dict(SOL_COORDS)
        if current_system and system_name.casefold() == current_system.casefold() and current_coords is not None:
            return dict(zip(('x', 'y', 'z'), current_coords))
        user_db = getattr(getattr(self, 'cargo_monitor', None), 'user_db', None)
        if user_db:
            coords = user_db._get_coordinates_from_visited_systems(system_name)
            if coords is not None:
                return dict(zip(('x', 'y', 'z'), coords))
        finder = getattr(self, 'ring_finder', None)
        if finder:
            coords = (getattr(finder, 'systems_data', None) or {}).get(system_name.lower())
            if coords is None:
                coords = finder._get_system_coords_from_galaxy_db(system_name)
            if coords is not None:
                return coords
        return self.distance_calculator.get_system_coordinates(system_name)

    def _resolve_distance_systems(self, names, current_system, current_coords, is_cancelled):
        from edsm_distance import SOL_COORDS
        results = {}
        user_db = getattr(getattr(self, 'cargo_monitor', None), 'user_db', None)
        for name in names:
            if is_cancelled():
                break
            key = name.casefold()
            if not name or key in results:
                continue
            info = dict(coords=None, sol_distance=None, visits=None, error=None)
            try:
                info['coords'] = self._distance_coordinate_lookup(name, current_system, current_coords)
                if info['coords'] is not None:
                    info['sol_distance'] = self.distance_calculator.calculate_distance(info['coords'], SOL_COORDS)
            except Exception as exc:
                logging.getLogger('EliteMining').warning('Distance lookup failed for %s: %s', name, exc)
                info['error'] = str(exc)
            if user_db:
                try:
                    visited = user_db.is_system_visited(name)
                    info['visits'] = visited.get('visit_count', 0) if visited else 0
                except Exception:
                    logging.getLogger('EliteMining').exception('Could not load visits for %s', name)
            results[key] = info
        return results

    def _calculate_distances(self):
        names = (self.distance_system_a.get().strip(), self.distance_system_b.get().strip())
        self._invalidate_distance_calculation()
        generation = self._distance_calculation_generation
        self._save_distance_systems()
        for side, name in zip(('a', 'b'), names):
            getattr(self, 'distance_system_' + side + '_name').config(text=t('distance_calculator.system_' + side + '_info') + ' ' + (name or '---'))
            for field, key in self._DISTANCE_RESULT_FIELDS:
                getattr(self, 'distance_' + side + '_' + field + '_label').config(text=t('distance_calculator.' + key) + ' ---', fg=self._dc_colors['fg_dim'])
        self.distance_ab_value_label.config(text='---')
        if not any(names):
            self._show_notice(self.distance_status_label, t('distance_calculator.enter_system'), fg=self._dc_colors['warning'])
            return
        self._show_notice(self.distance_status_label, t('distance_calculator.calculating'), clear_after=0, fg=self._dc_colors['info'])
        current_system = getattr(self, 'current_system', None)
        current_coords = getattr(self, 'current_system_coords', None)

        def worker():
            try:
                results = self._resolve_distance_systems(names, current_system, current_coords,
                    lambda: generation != self._distance_calculation_generation)
                self.after(0, self._apply_distance_results, generation, names, results)
            except Exception as exc:
                self.after(0, self._distance_calculation_failed, generation, names, str(exc))
        threading.Thread(target=worker, daemon=True).start()

    def _distance_calculation_failed(self, generation, names, error):
        if generation == self._distance_calculation_generation and names == (self.distance_system_a.get().strip(), self.distance_system_b.get().strip()):
            self._show_distance_error(error)

    def _apply_distance_results(self, generation, names, results):
        if generation != self._distance_calculation_generation or names != (self.distance_system_a.get().strip(), self.distance_system_b.get().strip()):
            return
        found = 0
        failed = False
        for side, name in zip(('a', 'b'), names):
            if not name:
                continue
            info = results[name.casefold()]
            coords = info['coords']
            if coords is None:
                key = 'distance_calculator.lookup_failed' if info['error'] else 'distance_calculator.coordinates_unavailable'
                getattr(self, 'distance_' + side + '_sol_label').config(text=t(key).format(system=name, error=info['error']), fg=self._dc_colors['error'])
                failed = failed or bool(info['error'])
                continue
            found += 1
            sol_distance = info['sol_distance']
            getattr(self, 'distance_' + side + '_sol_label').config(text=t('distance_calculator.distance_to_sol') + f' {sol_distance:.2f} LY')
            getattr(self, 'distance_' + side + '_coords_label').config(text=t('distance_calculator.coordinates') + f" X: {coords['x']:.2f}, Y: {coords['y']:.2f}, Z: {coords['z']:.2f}")
            if info['visits'] is not None:
                getattr(self, 'distance_' + side + '_visits_label').config(text=t('distance_calculator.visits_label') + f" {info['visits']}")
        if all(names) and found == 2:
            distance = self.distance_calculator.calculate_distance(*(results[name.casefold()]['coords'] for name in names))
            self.distance_ab_value_label.config(text=f'{distance:.2f} LY')
        if failed:
            key, color = 'distance_calculator.lookup_error', 'error'
        elif found == sum(bool(name) for name in names):
            key, color = 'distance_calculator.calculation_complete', 'success'
        else:
            key, color = 'distance_calculator.coordinates_missing', 'warning'
        self._show_notice(self.distance_status_label, t(key), fg=self._dc_colors[color])

    def _show_distance_error(self, error_msg: str):
        logging.getLogger('EliteMining').error('Distance calculation failed: %s', error_msg)
        self._show_notice(self.distance_status_label, t('distance_calculator.calculation_failed').format(error=error_msg), fg=self._dc_colors['error'])

    def _refresh_visit_count(self, system_name=None):
        """Refresh the Configuration visit counts after a visit is recorded"""
        if hasattr(self, 'distance_visits_label'):
            self._update_home_fc_distances()

    def _update_home_fc_distances(self):
        self.after(0, self._schedule_distance_update)

    def _distance_location_inputs(self):
        current = self.distance_current_system.get().strip()
        return ('' if current == '---' else current, self.distance_home_system.get().strip(), self.distance_fc_system.get().strip())

    def _schedule_distance_update(self):
        self._distance_update_generation += 1
        if self._distance_update_pending is not None:
            self.after_cancel(self._distance_update_pending)
        self._distance_update_pending = self.after(100, self._start_distance_update)

    def _start_distance_update(self):
        self._distance_update_pending = None
        if self._distance_update_running:
            return
        names = self._distance_location_inputs()
        generation = self._distance_update_generation
        current_system = getattr(self, 'current_system', None)
        current_coords = getattr(self, 'current_system_coords', None)
        self._distance_update_running = True

        def worker():
            try:
                results = self._resolve_distance_systems(names, current_system, current_coords,
                    lambda: generation != self._distance_update_generation)
            except Exception:
                logging.getLogger('EliteMining').exception('Home/Carrier distance update failed')
                results = {}
            self.after(0, self._apply_distance_updates, generation, names, results)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_distance_updates(self, generation, names, results):
        self._distance_update_running = False
        if generation != self._distance_update_generation or names != self._distance_location_inputs():
            self._schedule_distance_update()
            return
        current_info = results.get(names[0].casefold(), {})
        current_coords = current_info.get('coords')
        sol = current_info.get('sol_distance')
        self.current_sol_label.config(text=f"{sol:.2f} {t('distance_calculator.from_sol')}" if sol is not None else '')
        current_visits = current_info.get('visits')
        self.distance_visits_label.config(text=t('distance_calculator.visits_label') + f' {current_visits}' if current_visits is not None else '')
        values = {'sol': sol}
        for kind, name in zip(('home', 'fc'), names[1:]):
            info = results.get(name.casefold(), {})
            coords = info.get('coords')
            distance = self.distance_calculator.calculate_distance(current_coords, coords)
            values[kind] = distance
            getattr(self, 'distance_to_' + kind + '_label').config(text=f"{distance:.2f} {t('distance_calculator.from_current')}" if distance is not None else '')
            sol_distance = info.get('sol_distance')
            text = f"({t('distance_calculator.sol_distance')} {sol_distance:.2f} LY)" if sol_distance is not None and name.casefold() != 'sol' else ''
            if info.get('error'):
                text = t('distance_calculator.lookup_failed').format(system=name, error=info['error'])
            getattr(self, kind + '_sol_label').config(text=text)
            visits = info.get('visits')
            getattr(self, kind + '_visits_label').config(text=t('distance_calculator.visits_label') + f' {visits}' if visits is not None else '')
        self._distance_values = values
        if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, '_update_distance_display'):
            self.prospector_panel._update_distance_display()
        if hasattr(self, 'ring_finder') and hasattr(self.ring_finder, '_update_sol_distance'):
            self.ring_finder._update_sol_distance(names[0])

    def get_distance_info_text(self) -> str:
        values = getattr(self, '_distance_values', {})
        parts = []
        for key, label in (('sol', 'sol'), ('home', 'home'), ('fc', 'fleet_carrier')):
            value = values.get(key)
            text = f'{value:.2f} LY' if value is not None else '---'
            parts.append(t('mining_session.' + label) + ' ' + text)
        return '➤ ' + ' | '.join(parts)
