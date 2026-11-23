# -*- coding: utf-8 -*-
"""
Merit Miner view of the Hotspots Finder: the nearest Fortified/Stronghold systems of the
player's power with hotspots for the chosen mineral, each with the best Unoccupied
system in range to sell it for merits. Mixed into RingFinder (ring_finder.py).
"""
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk

from acquisition_view import _OverlayStatus
from column_visibility_helper import displayed_column
from core.constants import MENU_COLORS
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key


class _MMOverlayStatus(_OverlayStatus):
    def config(self, text=''):
        self._view._mm_set_status(text)


class MeritMinerMixin:
    MM_SEARCH_RADIUS = 500.0
    MM_MAX_RESULTS = 5
    MM_MAX_ATTEMPTS = 15
    MM_BATCH = 3  # mining systems checked at once; each sends ~6 requests, mostly to Spansh

    MM_COLUMNS = ("Mineral", "MineSystem", "Ring", "State", "Dist", "SellSystem", "Station", "Pad",
                  "SellDist", "Demand", "Price", "Updated")
    MM_DEFAULT_WIDTHS = {"Mineral": 110, "MineSystem": 180, "Ring": 110, "State": 90, "Dist": 80,
                         "SellSystem": 180, "Station": 180, "Pad": 50, "SellDist": 90, "Demand": 90,
                         "Price": 110, "Updated": 80}
    # Columns whose right-click/click acts on the selling system instead of the mining one
    MM_SELL_COLUMNS = ("SellSystem", "Station", "Pad", "SellDist", "Demand", "Price", "Updated")

    # ---------------------------------------------------------------------------------
    # Merit Miner view: fourth view of the Hotspots Finder results area
    # ---------------------------------------------------------------------------------

    def _build_merit_miner_view(self, parent, bg: str, tree_bg: str, tree_fg: str):
        import tkinter.font as tkfont
        from config import scaled_font, scaled_px, load_theme, load_merit_miner_minerals
        from ui.cell_tooltip import attach_cell_tooltip
        from system_finder_api import ELITE_POWERS

        current_theme = load_theme()

        self._mm = {
            'busy': False, 'status': '', 'hint': '', 'spin': 0, 'spinning': False, 'ran': False,
            'reference': '', 'power': '', 'count': 0,
            'mine_by_row': {}, 'sell_by_row': {}, 'station_by_row': {}, 'source_by_row': {},
        }

        frame = ttk.Frame(parent)
        self._mm_frame = frame

        # Right-hand controls are packed first so a narrow window clips the label, not them
        top_row = tk.Frame(frame, bg=bg)
        top_row.pack(fill="x", padx=5, pady=(5, 4))
        self._mm_columns_btn = self._cv_add_columns_button(top_row, 'merit_miner')

        btn_style = self._view_button_style()
        self._mm_search_btn = self._rf_button(top_row, text=t('ring_finder.search'), **btn_style,
                                              command=self._mm_on_search)
        self._mm_search_btn.pack(side="right")

        # One mineral at a time: "All Minerals" would mean a buyer search per mineral for
        # every candidate system. Display names map back to English for the search.
        self._mm_mineral_names = {}
        for display in self._get_available_materials()[1:]:
            english = self._to_english(display)
            self._mm_mineral_names[display] = "Low Temperature Diamonds" if english == "Low Temp Diamonds" else english
        saved = load_merit_miner_minerals()
        saved_display = next((d for d, e in self._mm_mineral_names.items() if saved and e == saved[0]), '')
        self._mm_mineral_var = tk.StringVar(value=saved_display)
        self._mm_mineral_combo = ttk.Combobox(top_row, textvariable=self._mm_mineral_var, width=14, state="readonly",
                                              values=tuple(self._mm_mineral_names))
        self._mm_mineral_combo.pack(side="right", padx=(0, 8))
        self._mm_mineral_combo.bind('<<ComboboxSelected>>', self._mm_on_mineral_selected, add='+')
        ttk.Label(top_row, text=t('ring_finder.mineral') + ':').pack(side="right", padx=(0, 4))

        self._mm_power_prompt = t('system_finder.pledge_prompt')
        self._mm_powers = tuple(ELITE_POWERS[1:])
        self._mm_power_var = tk.StringVar(value=self._mm_power_prompt)
        self._mm_power_combo = ttk.Combobox(top_row, textvariable=self._mm_power_var, width=22, state="readonly",
                                            values=(self._mm_power_prompt,) + self._mm_powers)
        self._mm_power_combo.pack(side="right", padx=(0, 8))
        self._mm_power_combo.bind('<<ComboboxSelected>>', self._mm_on_power_selected, add='+')
        ttk.Label(top_row, text=t('system_finder.pp_my_power') + ':').pack(side="right", padx=(0, 4))

        self._mm_name_label = ttk.Label(top_row, text="", font=scaled_font(9, "bold"))
        self._mm_name_label.pack(side="left")

        tree_frame = ttk.Frame(frame, relief="solid", borderwidth=1)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(0, 2))

        columns = self.MM_COLUMNS
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", selectmode="browse",
                               style="RingFinder.Treeview")
        self._mm_tree = tree
        column_labels = {
            "Mineral": t('ring_finder.col_mineral'),
            "MineSystem": t('ring_finder.merit_miner_col_mine_system'),
            "Ring": t('ring_finder.merit_miner_col_ring'),
            "State": t('ring_finder.merit_miner_col_state'),
            "Dist": t('ring_finder.col_dist'),
            "SellSystem": t('ring_finder.merit_miner_col_sell_system'),
            "Station": t('ring_finder.col_station'),
            "Pad": t('ring_finder.col_pad'),
            "SellDist": t('ring_finder.merit_miner_col_sell_dist'),
            "Demand": t('ring_finder.col_demand'),
            "Price": t('ring_finder.col_price'),
            "Updated": t('ring_finder.col_updated'),
        }
        heading_font = tkfont.Font(font=scaled_font(9, "bold"))
        header_pad = scaled_px(24)
        default_widths = {}
        for col in columns:
            tree.heading(col, text=column_labels[col], anchor="w")
            min_w = max(heading_font.measure(column_labels[col]) + header_pad, scaled_px(50))
            default_widths[col] = max(scaled_px(self.MM_DEFAULT_WIDTHS[col]), min_w)
            tree.column(col, width=default_widths[col], minwidth=min_w, anchor="w", stretch=False)

        try:
            from config import load_merit_miner_column_widths
            for col_name, width in load_merit_miner_column_widths().items():
                if col_name in columns and width > 0:
                    tree.column(col_name, width=max(width, tree.column(col_name, "minwidth")))
        except Exception:
            pass

        def save_widths(event=None):
            try:
                from config import save_merit_miner_column_widths
                save_merit_miner_column_widths({col: tree.column(col, "width") for col in columns})
            except Exception:
                pass
        tree.bind("<ButtonRelease-1>", save_widths, add='+')

        self.setup_column_visibility(tree=tree, columns=columns, default_widths=default_widths,
                                     config_key='merit_miner', use_displaycolumns=True, allow_reorder=True)
        attach_cell_tooltip(tree, "Updated", lambda item: self._mm['source_by_row'].get(item, ''))

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self._mm_overlay = tk.Frame(tree_frame, bg=tree_bg)
        self._mm_overlay_label = tk.Label(self._mm_overlay, text="", bg=tree_bg, fg=tree_fg,
                                          justify="center", wraplength=scaled_px(600))
        self._mm_overlay_label.place(relx=0.5, rely=0.5, anchor="center")
        self._mm_overlay.grid(row=0, column=0, sticky="nsew")
        self._mm_overlay_fonts = (scaled_font(14, "bold"), scaled_font(10))

        menu_colors = dict(bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                           activebackground=MENU_COLORS["activebackground"],
                           activeforeground=MENU_COLORS["activeforeground"])
        if current_theme == "elite_orange":
            menu_colors = dict(bg="#1e1e1e", fg="#ff8c00", activebackground="#ff6600", activeforeground="#000000")
        self._mm_row_menu = tk.Menu(frame, tearoff=0, font=scaled_font(9), **menu_colors)
        self._mm_menu_target = {'system': '', 'station': ''}
        target = self._mm_menu_target
        self._mm_row_menu.add_command(label=t('context_menu.open_inara'), command=lambda: self._mm_open_inara())
        self._mm_row_menu.add_command(label=t('context_menu.open_edsm'), command=lambda: self._bp_open_url(
            "https://www.edsm.net/en/system/id/0/name/{}", target['system']))
        self._mm_row_menu.add_command(label=t('context_menu.open_spansh'), command=lambda: self._bp_open_url(
            "https://spansh.co.uk/search/{}", target['system']))
        self._mm_row_menu.add_separator()
        self._mm_row_menu.add_command(label=t('context_menu.copy_system'),
                                      command=lambda: self._mm_copy(target['system']))

        tree.bind("<Button-1>", self._mm_on_click)
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['merit_miner'] = self._mm_on_right_click

        self._mm_control = SearchControl(self.parent, self._mm_search_btn, _MMOverlayStatus(self),
                                         on_finish=self._mm_on_finish)
        self._mm_sync_power()

    # --- inputs --------------------------------------------------------------------

    def _mm_selected_mineral(self) -> str:
        return self._mm_mineral_names.get(self._mm_mineral_var.get(), '')

    def _mm_power(self) -> str:
        power = self._mm_power_var.get()
        return power if power in self._mm_powers else ''

    def _mm_sync_power(self):
        """Show the shared My Power setting (Star Systems may have changed it)."""
        from config import load_player_power
        saved = load_player_power()
        self._mm_power_var.set(saved if saved in self._mm_powers else self._mm_power_prompt)
        self._mm_refresh_controls()

    def _mm_on_power_selected(self, event=None):
        from config import save_player_power
        self._mm_power_combo.selection_clear()
        power = self._mm_power()
        main_app = getattr(getattr(self, 'prospector_panel', None), 'main_app', None)
        star_var = getattr(main_app, 'sysfinder_my_power_var', None)
        if star_var is not None and hasattr(main_app, '_save_player_power'):
            # Star Systems saves and refreshes its own labels
            star_var.set(main_app._sysfinder_option_label(power or 'Select your pledge...'))
            main_app._save_player_power()
        else:
            save_player_power(power or 'Select your pledge...')
        self._mm_refresh_controls()

    def _mm_on_mineral_selected(self, event=None):
        from config import save_merit_miner_minerals
        self._mm_mineral_combo.selection_clear()
        mineral = self._mm_selected_mineral()
        save_merit_miner_minerals([mineral] if mineral else [])
        self._mm_refresh_controls()

    # --- state and overlay ---------------------------------------------------------

    def _mm_ready_hint(self) -> str:
        """Why Search can't run yet, or '' when it can."""
        if not self._mm_power():
            return t('ring_finder.merit_miner_pick_power')
        if not self._mm_selected_mineral():
            return t('ring_finder.merit_miner_pick_minerals')
        return ''

    def _mm_refresh_controls(self):
        mm = self._mm
        if not mm['busy']:
            # The power is shown in the My Power box beside it
            self._mm_name_label.config(text=t('ring_finder.merit_miner_view_name').format(
                count=mm['count'], system=mm['reference']) if mm.get('count') else '')
        if not mm['busy']:
            self._mm_search_btn.configure(state="disabled" if self._mm_ready_hint() else "normal")
        self._mm_update_overlay()

    def _mm_update_overlay(self):
        mm = self._mm
        if mm['busy']:
            chars = self._search_overlay_chars
            text = f"{mm['status']}\n\n{chars[mm['spin'] % len(chars)]}"
            font = self._mm_overlay_fonts[0]
        elif not self._mm_tree.get_children():
            text = mm['hint'] or self._mm_ready_hint() or t('ring_finder.merit_miner_empty')
            font = self._mm_overlay_fonts[1]
        else:
            self._mm_overlay.grid_remove()
            return
        self._mm_overlay_label.configure(text=text, font=font)
        self._mm_overlay.grid()
        self._mm_overlay.tkraise()

    def _mm_spin(self):
        mm = self._mm
        if not mm['busy']:
            mm['spinning'] = False
            return
        mm['spin'] += 1
        self._mm_update_overlay()
        self.parent.after(100, self._mm_spin)

    def _mm_set_status(self, text: str):
        mm = self._mm
        mm['status'] = text
        mm['hint'] = text
        self._mm_update_overlay()

    def _mm_on_finish(self):
        self._mm['busy'] = False
        self._mm_refresh_controls()

    # --- running a search ----------------------------------------------------------

    def _mm_on_view_click(self):
        """A click on Merit Miner shows the view; the first time, it also searches when
        a power and mineral are already set."""
        self._mm_sync_power()
        if not self._mm['ran'] and not self._mm_control.running and not self._mm_ready_hint():
            self._mm_start()

    def _mm_on_search(self):
        if self._mm_control.running:
            self._mm_control.stop()
        else:
            self._mm_start()

    def _mm_start(self):
        mm = self._mm
        if self._mm_ready_hint():
            self._mm_refresh_controls()
            return
        reference = self.system_var.get().strip()
        if not reference:
            mm['hint'] = t('ring_finder.enter_reference_system')
            self._mm_fill([])
            return
        reference = self._saved_system_spelling(reference)
        power = self._mm_power()
        mineral = self._mm_selected_mineral()
        mm.update(busy=True, ran=True, hint='', reference=reference, power=power, count=0,
                  status=t('ring_finder.merit_miner_searching').format(power=power, system=reference))
        self._mm_fill([])
        self._show_results_view('merit_miner')
        control = self._mm_control
        control.start()
        self._mm_refresh_controls()
        if not mm['spinning']:
            mm['spinning'] = True
            mm['spin'] = 0
            self._mm_spin()
        threading.Thread(target=control.run, args=(self._mm_worker, reference, power, mineral, control),
                         daemon=True).start()

    def _mm_worker(self, reference: str, power: str, mineral: str, control):
        """Background worker: nearest Fortified/Stronghold hotspot systems of power for
        mineral, then the best-paying Unoccupied buyer within that state's radius."""
        is_cancelled = control.is_cancelled
        coords = self._lookup_system_coords(reference, is_cancelled=is_cancelled)
        if not coords:
            hint = t('ring_finder.coords_not_found_warning').format(system=reference)
            control.complete([], lambda rows: self._mm_show_results(rows, hint))
            return
        if is_cancelled():
            control.complete([], self._mm_show_results)
            return

        hotspots = self._get_hotspots(reference, "All", mineral, False, self.MM_SEARCH_RADIUS, None,
                                      data_source='database', is_cancelled=is_cancelled, reference_coords=coords)

        state_by_system = {}
        for state in ('Fortified', 'Stronghold'):
            if is_cancelled():
                control.complete([], self._mm_show_results)
                return
            matched, _enrichment = self._apply_powerplay_filter(
                hotspots, power, state, reference, self.MM_SEARCH_RADIUS, is_cancelled=is_cancelled)
            for row in matched:
                state_by_system.setdefault(row.get('systemName') or row.get('system', ''), state)

        candidates = self._mm_candidate_systems(hotspots, state_by_system)
        results = self._mm_find_sell_targets(mineral, candidates, is_cancelled)
        if is_cancelled():
            control.complete([], self._mm_show_results)
            return

        hint = ''
        if not results:
            key = 'merit_miner_no_mine_systems' if not candidates else 'merit_miner_no_buyers'
            hint = t('ring_finder.' + key).format(power=power, minerals=self._format_material_for_display(mineral),
                                                  system=reference, radius=int(self.MM_SEARCH_RADIUS))
        control.complete(results, lambda rows: self._mm_show_results(rows, hint))

    @staticmethod
    def _mm_candidate_systems(hotspots: list, state_by_system: dict) -> list:
        """[(system, ring, state, distance)] nearest first, one entry per system (its
        nearest-listed ring), only systems in state_by_system."""
        systems = {}
        for row in hotspots:
            system = row.get('systemName') or row.get('system', '')
            state = state_by_system.get(system)
            if not state or system in systems:
                continue
            try:
                distance = float(row.get('distance', 0) or 0)
            except (TypeError, ValueError):
                distance = 0.0
            systems[system] = (system, row.get('ring', ''), state, distance)
        return sorted(systems.values(), key=lambda c: c[3])

    def _mm_find_sell_targets(self, mineral: str, candidates: list, is_cancelled) -> list:
        """Walk candidates nearest first in small parallel batches until enough have a buyer."""
        from system_finder_api import SystemFinderAPI
        found = []
        attempts = candidates[:self.MM_MAX_ATTEMPTS]

        def check(candidate):
            system, ring, state, distance = candidate
            if is_cancelled():
                return None
            radius = self.ACQUISITION_RADIUS_BY_STATE[state]
            nearby = SystemFinderAPI._fetch_spansh_powerplay_systems(system, radius, 'Any', 'Unoccupied',
                                                                    is_cancelled=is_cancelled)
            SystemFinderAPI._store_powerplay_batch(nearby)
            sells, prices, _best, rows = self._acq_find_sell_targets(system, radius, [mineral], is_cancelled,
                                                                     nearby=nearby)
            if not sells:
                return None
            sell_system = max(sells, key=lambda s: prices.get(s[0], 0))[0]
            return {'mineral': mineral, 'system': system, 'ring': ring, 'state': state, 'distance': distance,
                    'sell_system': sell_system, 'sell_distance': nearby.get(sell_system, {}).get('distance', 0),
                    'price': prices.get(sell_system, 0), 'buyer': rows.get(sell_system, {})}

        for start in range(0, len(attempts), self.MM_BATCH):
            if is_cancelled() or len(found) >= self.MM_MAX_RESULTS:
                break
            batch = attempts[start:start + self.MM_BATCH]
            with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                for hit in pool.map(check, batch):
                    if hit and len(found) < self.MM_MAX_RESULTS:
                        found.append(hit)
        return found

    def _mm_show_results(self, results: list, hint: str = ''):
        mm = self._mm
        mm['hint'] = hint
        mm['count'] = len(results)
        self._mm_fill(results)

    def _mm_fill(self, results: list):
        from app_utils import format_market_source
        mm = self._mm
        tree = self._mm_tree
        tree.delete(*tree.get_children())
        for key in ('mine_by_row', 'sell_by_row', 'station_by_row', 'source_by_row'):
            mm[key].clear()
        state_labels = {'Fortified': t('ring_finder.merit_miner_state_fortified'),
                        'Stronghold': t('ring_finder.merit_miner_state_stronghold')}
        for hit in results:
            buyer = hit['buyer']
            station = buyer.get('stationName', '') or '-'
            demand = buyer.get('demand')
            row_id = tree.insert("", "end", values=(
                self._format_material_for_display(hit['mineral']), hit['system'], hit['ring'] or '-',
                state_labels.get(hit['state'], hit['state']), f"{hit['distance']:.1f}", hit['sell_system'],
                station, self._format_pad_size(buyer.get('maxLandingPadSize')), f"{hit['sell_distance']:.1f}",
                f"{demand:,}" if isinstance(demand, (int, float)) else '-', f"{hit['price']:,} CR", self._format_data_age(buyer.get('updatedAt', ''))))
            mm['mine_by_row'][row_id] = hit['system']
            mm['sell_by_row'][row_id] = hit['sell_system']
            mm['station_by_row'][row_id] = station if station != '-' else ''
            mm['source_by_row'][row_id] = format_market_source(buyer)
        self._mm_refresh_controls()

    # --- row actions ---------------------------------------------------------------

    def _mm_row_target(self, row_id, column_id) -> dict:
        """Mining or selling system for a clicked cell, by column."""
        mm = self._mm
        column = displayed_column(self._mm_tree, column_id) if column_id else None
        if column in self.MM_SELL_COLUMNS:
            return {'system': mm['sell_by_row'].get(row_id, ''), 'station': mm['station_by_row'].get(row_id, '')}
        return {'system': mm['mine_by_row'].get(row_id, ''), 'station': ''}

    def _mm_copy(self, system: str):
        if system:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(system)
            self.parent.update_idletasks()

    def _mm_open_inara(self):
        target = self._mm_menu_target
        if target['station']:
            self._bp_open_url("https://inara.cz/elite/stations/?search={}", target['station'])
        else:
            self._bp_open_url("https://inara.cz/elite/starsystem/?search={}", target['system'])

    def _mm_on_click(self, event):
        row_id = self._mm_tree.identify_row(event.y)
        if row_id:
            self._mm_tree.selection_set(row_id)
            self._mm_copy(self._mm_row_target(row_id, self._mm_tree.identify_column(event.x))['system'])

    def _mm_on_right_click(self, event):
        row_id = self._mm_tree.identify_row(event.y)
        if row_id and self._mm['mine_by_row'].get(row_id):
            self._mm_tree.selection_set(row_id)
            self._mm_menu_target.update(self._mm_row_target(row_id, self._mm_tree.identify_column(event.x)))
            try:
                self._mm_row_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._mm_row_menu.grab_release()
