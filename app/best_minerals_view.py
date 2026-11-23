# -*- coding: utf-8 -*-
"""
Best Prices view of the Hotspots Finder: live sell prices for a system's hotspot minerals,
filled by the right-click "Best Minerals to Mine" action and by Auto Prices.
Mixed into RingFinder (ring_finder.py).
"""
import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict, List

from core.constants import MENU_COLORS
from column_visibility_helper import displayed_column
from ui.striped_treeview import StripedTreeview
from ui.theme import modern_color
from ui.themed_checkbox import ThemedCheckbutton

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key

# Same logger name as ring_finder.py so log lines keep their source
log = logging.getLogger('ring_finder')


class BestMineralsMixin:
    def _rank_minerals_inputs(self, scope: str, system_name: str = None):
        """Work out what to price for the selected row: (system_name, fetch_materials,
        extra_candidates, mineral_ring_types), or None (status set) if nothing to rank.

        scope 'ring' = only the clicked ring's hotspot minerals; 'system' = every hotspot
        mineral known anywhere in that row's system (same scope as Auto Prices).
        system_name prices that whole system without needing a selected row."""
        if not (scope == 'system' and system_name):
            selection = self.results_tree.selection()
            if not selection:
                self.status_var.set(t('ring_finder.no_selection'))
                return None

            values = self.results_tree.item(selection[0], 'values')
            if not values or len(values) < 9:
                return None

            system_name = values[2]

        if scope == 'ring':
            ring_type = self._ring_type_rev_map.get(values[6], values[6])
            materials = self._parse_materials_from_hotspots(values[8])
            if not materials:
                self.status_var.set(t('ring_finder.no_hotspot_minerals'))
                return None

            full_materials = list(dict.fromkeys(self._expand_abbreviated_materials(m) for m in materials))

            # Non-hotspot minerals (e.g. Osmium) mineable in this one ring's type - same
            # "Also check" picker as the system-wide ranking, just scoped to the single
            # ring type already sitting in this row instead of a whole-system DB query.
            extra_candidates = [mat for mat in self.NON_HOTSPOT_RING_MINERALS.get(ring_type, [])
                                if mat not in full_materials]

            # Every mineral here (hotspot or "also check") comes from this one row's ring
            # type - so mining method lookup only ever needs to consider that single type.
            mineral_ring_types = {mat: {ring_type} for mat in full_materials + extra_candidates}
        else:
            try:
                hotspot_rows = self.user_db.get_system_hotspots(system_name)
            except Exception:
                hotspot_rows = []
            full_materials = list(dict.fromkeys(
                self._expand_abbreviated_materials(row['material_name'])
                for row in hotspot_rows if row.get('material_name')
            ))
            if not full_materials:
                self.status_var.set(t('ring_finder.no_hotspot_minerals'))
                return None

            # Ring type(s) each hotspot mineral was actually found in, in this system - a
            # mineral like Platinum can be a laser-mine in one ring type and core-only in
            # another, so mining method needs to be checked per ring type, not per mineral.
            mineral_ring_types: Dict[str, set] = {}
            for row in hotspot_rows:
                mat = row.get('material_name')
                rt = row.get('ring_type')
                if mat and rt:
                    mineral_ring_types.setdefault(self._expand_abbreviated_materials(mat), set()).add(rt)

            # Non-hotspot minerals (e.g. Osmium) mineable somewhere in this system, based on
            # its known ring types - offered via the popup's "Also check" picker since
            # hotspot-based ranking can never surface them on its own.
            ring_types_present = {row['ring_type'] for row in hotspot_rows if row.get('ring_type')}
            extra_candidates = sorted(dict.fromkeys(
                mat for ring_type in ring_types_present
                for mat in self.NON_HOTSPOT_RING_MINERALS.get(ring_type, [])
                if mat not in full_materials
            ))
            for mat in extra_candidates:
                mineral_ring_types[mat] = {rt for rt in ring_types_present
                                            if mat in self.NON_HOTSPOT_RING_MINERALS.get(rt, [])}

        # Minerals the user previously ticked in "Also check" (e.g. always wants Osmium
        # tracked) - fetch them upfront alongside the hotspot minerals, so they're
        # already in the ranked table without having to reopen the picker every time.
        try:
            from config import load_also_check_minerals
            always_check = set(load_also_check_minerals())
        except Exception:
            always_check = set()
        preselected_extras = [mat for mat in extra_candidates if mat in always_check]
        return system_name, full_materials + preselected_extras, extra_candidates, mineral_ring_types

    def _cached_rank_results(self, system_name: str, fetch_materials: List[str]):
        """Prefetched prices (from the "prefetch on jump" toggle) if they already cover
        every mineral with an actual priced hit, else None. A prefetch miss (no price
        found, e.g. the jump fetch ran before Ardent/Spansh had indexed the station)
        doesn't count as covered - the caller should do a fresh live fetch instead of
        showing that stale empty result forever."""
        prefetched = getattr(self, '_prefetched_prices', {}).get(system_name)
        if prefetched is None:
            return None
        priced_materials = {mat for mat, best, _ in prefetched if best}
        if not set(fetch_materials).issubset(priced_materials):
            return None
        cached = [(mat, best, priced_rows) for mat, best, priced_rows in prefetched if mat in fetch_materials]
        cached.sort(key=lambda r: r[1].get('sellPrice', 0) if r[1] else -1, reverse=True)
        return cached

    def _fetch_mineral_prices(self, system_name: str, materials: List[str]):
        """Fetch best sell price per mineral concurrently; returns [(mat, best, priced_rows)]
        sorted by best price. Blocking - call from a worker thread."""
        from marketplace_api import MarketplaceAPI
        from concurrent.futures import ThreadPoolExecutor

        results = []
        # All minerals at once, same as the Auto Prices prefetch - capping it made a
        # whole-system lookup run in several slow rounds
        with ThreadPoolExecutor(max_workers=max(len(materials), 1)) as pool:
            # search_buyers (Ardent's /imports) - stations that buy this commodity FROM
            # the player, i.e. where a miner can actually sell it. search_sellers is the
            # opposite direction (stations selling TO players, for buying commodities).
            # 7-day window instead of the 2-day default - Rank Minerals/Find Best Mining
            # System cover quieter systems than the Commodity Market tab, which keeps its
            # own tighter filter.
            futures = {pool.submit(MarketplaceAPI.search_buyers, mat, system_name, None, 7, False): mat for mat in materials}
            for future in futures:
                mat = futures[future]
                try:
                    rows = future.result()
                except Exception:
                    rows = []
                priced_rows = [r for r in rows if r.get('sellPrice', 0) > 0]
                best = max(priced_rows, key=lambda r: r.get('sellPrice', 0)) if priced_rows else None
                # Keep every priced row too, so the "in-system only" toggle can re-rank
                # against local-system stations without a second live fetch.
                results.append((mat, best, priced_rows))

        results.sort(key=lambda r: r[1].get('sellPrice', 0) if r[1] else -1, reverse=True)
        return results

    # ---------------------------------------------------------------------------------
    # Best Prices view: second view of the Hotspots Finder results area
    # ---------------------------------------------------------------------------------

    BP_COLUMNS = ("Mineral", "RingType", "Price", "Station", "Type", "Pad", "Dist", "LS", "Demand", "PowerPlay", "Updated")
    BP_DEFAULT_WIDTHS = {"Mineral": 130, "RingType": 90, "Price": 110, "Station": 280, "Type": 110,
                         "Pad": 50, "Dist": 80, "LS": 70, "Demand": 90, "PowerPlay": 200, "Updated": 90}

    def _build_best_prices_view(self, parent, bg: str, select_bg: str, tree_bg: str, tree_fg: str):
        """Build the Best Prices view (hidden) inside the results area. Filled by the
        right-click "Best Minerals to Mine" action and by Auto Prices."""
        from config import scaled_font, load_theme
        from app_utils import format_market_source
        from ui.cell_tooltip import attach_cell_tooltip
        from report_generator import ReportGenerator

        current_theme = load_theme()
        fg = "#ff8c00" if current_theme == "elite_orange" else "#e6e6e6"

        self._bp = {
            'system': '', 'results': [], 'extra_candidates': [], 'ring_types': {}, 'pp_data': {},
            'scope': 'system', 'ring_name': '', 'busy': False, 'loading': '', 'spin': 0, 'spinning': False,
            'mineral_by_row': {}, 'system_by_row': {}, 'source_by_row': {}, 'extra_vars': {},
            'picker': None,
        }
        self._bp_req = 0
        self._bp_core_materials = {mat for mat, info in ReportGenerator.MATERIAL_TPH_THRESHOLDS.items()
                                   if info.get('is_core', False)}

        frame = ttk.Frame(parent)
        self._bp_frame = frame

        # One control row. Right-hand controls are packed first so a narrow window
        # clips the ring/system name on the left, never the buttons.
        top_row = tk.Frame(frame, bg=bg)
        top_row.pack(fill="x", padx=5, pady=(5, 4))
        self._bp_columns_btn = self._cv_add_columns_button(top_row, 'rank_minerals')

        btn_style = self._view_button_style()
        self._bp_refresh_btn = self._rf_button(top_row, text=t('ring_finder.rank_refresh'), **btn_style,
                                               command=lambda: self._bp_reload(self._bp['scope'], True))
        self._bp_refresh_btn.pack(side="right")
        self._bp_refresh_btn.configure(state="disabled")
        self._bp_extra_btn = self._rf_button(top_row, text=t('ring_finder.also_check_button'), **btn_style,
                                             command=self._bp_show_extra_picker)
        self._bp_extra_btn.pack(side="right", padx=(0, 8))
        self._bp_extra_btn.configure(state="disabled")

        # PowerPlay mode: restrict results to stations in the priced system itself - for
        # undermining/reinforcing, that system is the only place the player can actually
        # sell. Re-ranks the already-fetched priced_rows client-side, no extra live calls.
        from config import load_pp_mode
        self._bp_pp_mode_var = tk.BooleanVar(value=load_pp_mode())
        ThemedCheckbutton(top_row, text=t('ring_finder.pp_mode_checkbox'), variable=self._bp_pp_mode_var,
                          command=self._bp_on_pp_toggle, bg=bg, fg=fg, activebackground=bg,
                          activeforeground=fg, selectcolor=select_bg, font=scaled_font(9)).pack(side="right", padx=(0, 12))

        # This Ring | Whole System - only shown for prices that came from a ring row
        from config import scaled_px
        from ui.segmented_selector import SegmentedSelector
        from ui.themed_slider import slider_colors
        self._bp_scope_var = tk.StringVar(value='ring')
        self._bp_scope_switch = SegmentedSelector(
            top_row, [('ring', t('ring_finder.rank_scope_switch_to_ring')),
                      ('system', t('ring_finder.rank_scope_switch_to_system'))],
            self._bp_scope_var, bg=bg, accent=slider_colors(current_theme)["accent"],
            font=scaled_font(8), scale=scaled_px(100) / 100, gap=scaled_px(4))
        self._bp_scope_var.trace_add('write', lambda *_: self._bp_on_scope_switch())
        from ui.tooltip import add_segment_tooltips
        add_segment_tooltips(self._bp_scope_switch, {
            'ring': t('ring_finder.rank_scope_ring_tooltip'),
            'system': t('ring_finder.rank_scope_system_tooltip')})
        self._bp_scope_label = ttk.Label(top_row, text="", font=scaled_font(9, "bold"))
        self._bp_scope_label.pack(side="left")

        tree_frame = ttk.Frame(frame, relief="solid", borderwidth=1)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(0, 2))

        columns = self.BP_COLUMNS
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", selectmode="browse",
                               style="RingFinder.Treeview")
        self._bp_tree = tree
        self._bp_column_labels = {
            "Mineral": t('ring_finder.col_mineral'),
            "RingType": t('ring_finder.col_mining_method'),
            "Price": t('ring_finder.col_price'),
            "Station": t('ring_finder.col_station'),
            "Type": t('ring_finder.col_station_type'),
            "Pad": t('ring_finder.col_pad'),
            "Dist": t('ring_finder.col_dist'),
            "LS": t('ring_finder.col_ls'),
            "Demand": t('ring_finder.col_demand'),
            "PowerPlay": t('ring_finder.col_powerplay'),
            "Updated": t('ring_finder.col_updated'),
        }
        self._bp_sort_reverse = {col: False for col in columns}
        for col in columns:
            tree.heading(col, text=self._bp_column_labels[col], anchor="w", command=lambda c=col: self._bp_sort(c))
            tree.column(col, width=self.BP_DEFAULT_WIDTHS[col], minwidth=40, anchor="w", stretch=False)

        try:
            from config import load_rank_minerals_column_widths
            for col_name, width in load_rank_minerals_column_widths().items():
                try:
                    if width > 0:
                        tree.column(col_name, width=max(width, tree.column(col_name, "minwidth")))
                except Exception:
                    pass
        except Exception:
            pass

        def save_widths(event=None):
            try:
                from config import save_rank_minerals_column_widths
                save_rank_minerals_column_widths({col: tree.column(col, "width") for col in columns})
            except Exception:
                pass
        tree.bind("<ButtonRelease-1>", save_widths, add='+')

        self.setup_column_visibility(tree=tree, columns=columns, default_widths=dict(self.BP_DEFAULT_WIDTHS),
                                     config_key='rank_minerals', use_displaycolumns=True, allow_reorder=True)
        attach_cell_tooltip(tree, "Updated", lambda item: self._bp['source_by_row'].get(item, ''))

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        # Covers the table while prices load (spinner, like the hotspot search) and
        # holds the "no prices yet" hint before the first lookup
        self._bp_overlay = tk.Frame(tree_frame, bg=tree_bg)
        self._bp_overlay_label = tk.Label(self._bp_overlay, text="", bg=tree_bg, fg=tree_fg,
                                          justify="center", wraplength=scaled_px(600))
        self._bp_overlay_label.place(relx=0.5, rely=0.5, anchor="center")
        self._bp_overlay.grid(row=0, column=0, sticky="nsew")
        self._bp_overlay_fonts = (scaled_font(14, "bold"), scaled_font(10))
        self._bp_update_overlay()

        menu_colors = dict(bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                           activebackground=MENU_COLORS["activebackground"],
                           activeforeground=MENU_COLORS["activeforeground"])
        if current_theme == "elite_orange":
            menu_colors = dict(bg="#1e1e1e", fg="#ff8c00", activebackground="#ff6600", activeforeground="#000000")
        self._bp_row_menu = tk.Menu(frame, tearoff=0, font=scaled_font(9), **menu_colors)
        self._bp_row_menu.add_command(label=t('context_menu.find_sell_station'), command=self._bp_find_sell_station)
        self._bp_row_menu.add_separator()

        def selected_system():
            sel = tree.selection()
            return self._bp['system_by_row'].get(sel[0], '') if sel else ''

        self._bp_row_menu.add_command(label=t('context_menu.copy_system'),
                                      command=lambda: self._bp_copy_system(tree.selection()[0]) if tree.selection() else None)
        self._bp_row_menu.add_command(label=t('context_menu.open_inara'),
                                      command=lambda: self._bp_open_url("https://inara.cz/elite/starsystem/?search={}", selected_system()))
        self._bp_row_menu.add_command(label=t('context_menu.open_edsm'),
                                      command=lambda: self._bp_open_url("https://www.edsm.net/en/system/id/0/name/{}", selected_system()))
        self._bp_row_menu.add_command(label=t('context_menu.open_spansh'),
                                      command=lambda: self._bp_open_url("https://spansh.co.uk/search/{}", selected_system()))

        tree.bind("<Button-1>", self._bp_on_click)
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['rank_minerals'] = self._bp_on_right_click
        self._bp_format_source = format_market_source

    def _bp_new_request(self) -> int:
        """Start a new price request; results from any older request are dropped."""
        self._bp_req += 1
        return self._bp_req

    def _bp_scope_text(self) -> str:
        bp = self._bp
        if bp['busy']:
            return bp['loading']
        if bp['scope'] == 'ring' and bp['ring_name']:
            return f"{bp['ring_name']} ({bp['system']})"
        return bp['system']

    def _bp_set_busy(self, busy: bool, system_name: str = ''):
        bp = self._bp
        bp['busy'] = busy
        if busy:
            bp['loading'] = system_name or bp['system']
        self._bp_scope_label.config(text=self._bp_scope_text())
        state = "disabled" if busy or not bp['system'] else "normal"
        self._bp_refresh_btn.configure(state=state)
        self._bp_scope_switch.configure(state=state)
        self._bp_extra_btn.configure(state=state)
        self._bp_update_overlay()
        if busy and not bp['spinning']:
            bp['spinning'] = True
            bp['spin'] = 0
            self._bp_spin()

    def _bp_update_overlay(self):
        bp = self._bp
        if bp['busy']:
            chars = self._search_overlay_chars
            text = t('ring_finder.ranking_minerals').format(system=bp['loading']) + f"\n\n{chars[bp['spin'] % len(chars)]}"
            font = self._bp_overlay_fonts[0]
        elif not bp['system']:
            text, font = bp.get('hint') or t('ring_finder.best_prices_empty'), self._bp_overlay_fonts[1]
        else:
            self._bp_overlay.grid_remove()
            return
        self._bp_overlay_label.configure(text=text, font=font)
        self._bp_overlay.grid()
        self._bp_overlay.tkraise()

    def _bp_spin(self):
        bp = self._bp
        if not bp['busy']:
            bp['spinning'] = False
            return
        bp['spin'] += 1
        self._bp_update_overlay()
        self.parent.after(100, self._bp_spin)

    def _bp_refresh_controls(self):
        bp = self._bp
        # Scope switch only makes sense when the prices came from a ring row
        if bp['ring_name']:
            if self._bp_scope_var.get() != bp['scope']:
                self._bp_scope_var.set(bp['scope'])  # bp['scope'] already matches, so no reload
            if not self._bp_scope_switch.winfo_manager():
                self._bp_scope_switch.pack(side="left", padx=(0, 10), before=self._bp_scope_label)
        else:
            self._bp_scope_switch.pack_forget()
        self._bp_set_busy(bp['busy'])

    def _bp_lookup_failed(self):
        self._bp['busy'] = False
        self._bp_refresh_controls()

    def _bp_on_scope_switch(self):
        new_scope = self._bp_scope_var.get()
        if new_scope == self._bp['scope']:
            return
        self._bp_reload(new_scope, False)
        if not self._bp['busy']:
            # Reload didn't start (e.g. no ring selected): show the scope still in use
            self._bp_scope_var.set(self._bp['scope'])

    def _show_best_prices(self, system_name: str, results: list, extra_candidates: List[str] = None,
                          mineral_ring_types: Dict[str, set] = None, scope: str = 'system', ring_name: str = '',
                          pp_data: dict = None, req: int = None, switch: bool = True):
        """Fill the Best Prices view and (optionally) switch the results area to it."""
        if req is not None and req != self._bp_req:
            return
        if not hasattr(self, '_bp_tree'):
            return
        self._bp_close_extra_picker()
        if pp_data is None:
            from system_finder_api import SystemFinderAPI
            names = list({best.get('systemName', '') for _, best, _ in results if best and best.get('systemName')} | {system_name})
            pp_data = SystemFinderAPI._batch_get_powerplay(names) if names else {}
        bp = self._bp
        bp['hint'] = ''
        bp['system'] = system_name
        bp['results'] = list(results)
        bp['extra_candidates'] = list(extra_candidates or [])
        bp['ring_types'] = dict(mineral_ring_types or {})
        bp['pp_data'] = dict(pp_data)
        bp['scope'] = scope
        bp['ring_name'] = ring_name
        bp['busy'] = False
        # The same setting is also changed from Settings and Auto Options
        from config import load_pp_mode
        self._bp_pp_mode_var.set(load_pp_mode())
        self._bp_sync_extra_vars()
        self._bp_refresh_controls()
        self._bp_populate()
        if switch:
            self._show_results_view('best_prices')

    def _bp_rows_for_mode(self, mat, best, priced_rows):
        if self._bp_pp_mode_var.get():
            in_system = [r for r in priced_rows if r.get('systemName', '') == self._bp['system']]
            return max(in_system, key=lambda r: r.get('sellPrice', 0)) if in_system else None
        return best

    def _bp_mining_method(self, mat) -> str:
        """Ring type per mineral, from the same hotspot rows the prices came from - so a
        top-priced mineral that's actually core-only in this ring doesn't get mined blind
        with a laser (e.g. Platinum is laser-mineable in Metallic but core-only in Metal
        Rich). Falls back to the static core flag when the ring type isn't known."""
        rts = self._bp['ring_types'].get(mat, set())
        by_rt = {rt: self.MINING_METHOD_BY_RING.get(mat, {}).get(rt) for rt in rts}
        by_rt = {rt: method for rt, method in by_rt.items() if method}
        if not by_rt:
            is_core = mat in self._bp_core_materials
            return t('ring_finder.mining_method_core') if is_core else t('ring_finder.mining_method_laser')

        parts = []
        for rt, method in sorted(by_rt.items()):
            rt_display = self._ring_type_map.get(rt, rt)
            if method == 'both':
                parts.append(f"{t('ring_finder.mining_method_core')}/{rt_display}")
                parts.append(f"{t('ring_finder.mining_method_laser')}/{rt_display}")
            else:
                method_display = t('ring_finder.mining_method_core') if method == 'core' else t('ring_finder.mining_method_laser')
                parts.append(f"{method_display}/{rt_display}")
        return ", ".join(parts)

    @staticmethod
    def _bp_pp_text(pp_entry: dict) -> str:
        pp_power = pp_entry.get('controlling_power', '')
        pp_state = pp_entry.get('power_state', '')
        if pp_power == '~none~':
            return pp_state or t('common.no_data')
        elif pp_power and pp_state:
            return f"{pp_power} / {pp_state}"
        elif pp_power:
            return pp_power
        elif pp_state:
            return pp_state
        return t('common.no_data')

    def _bp_populate(self):
        bp = self._bp
        tree = self._bp_tree
        tree.delete(*tree.get_children())
        bp['mineral_by_row'].clear()
        bp['system_by_row'].clear()
        bp['source_by_row'].clear()
        pp_mode = self._bp_pp_mode_var.get()
        for mat, best, priced_rows in bp['results']:
            row_best = self._bp_rows_for_mode(mat, best, priced_rows)
            if row_best and row_best.get('sellPrice', 0) > 0:
                price = f"{row_best.get('sellPrice', 0):,} CR"
                station_system = row_best.get('systemName', '')
                station = f"{row_best.get('stationName', '')} ({station_system})"
                station_type = self._format_station_type(row_best.get('stationType'))
                pad = self._format_pad_size(row_best.get('maxLandingPadSize'))
                demand_val = row_best.get('demand')
                demand = f"{demand_val:,}" if isinstance(demand_val, (int, float)) else "-"
                dist = f"{row_best.get('distance', 0):.1f}" if row_best.get('distance') is not None else "-"
                station_ls = row_best.get('distanceToArrival')
                ls = f"{int(station_ls):,}" if station_ls is not None else "-"
                powerplay = self._bp_pp_text(bp['pp_data'].get(station_system, {}))
                updated = self._format_data_age(row_best.get('updatedAt', ''))
            elif pp_mode:
                price = t('ring_finder.no_data_in_system')
                station_system = bp['system']
                station = station_type = pad = demand = dist = ls = updated = "-"
                powerplay = self._bp_pp_text(bp['pp_data'].get(bp['system'], {}))
            else:
                price = t('ring_finder.no_data')
                station_system = ""
                station = station_type = pad = demand = dist = ls = powerplay = updated = "-"
            row_id = tree.insert("", "end", values=(self._format_material_for_display(mat), self._bp_mining_method(mat),
                                                    price, station, station_type, pad, dist, ls, demand, powerplay, updated))
            bp['mineral_by_row'][row_id] = mat
            bp['system_by_row'][row_id] = station_system
            if row_best and row_best.get('sellPrice', 0) > 0:
                bp['source_by_row'][row_id] = self._bp_format_source(row_best)

    def _bp_on_pp_toggle(self):
        from config import save_pp_mode
        save_pp_mode(self._bp_pp_mode_var.get())
        self._bp_populate()

    def _bp_sort(self, col):
        tree = self._bp_tree
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        reverse = self._bp_sort_reverse[col]

        if col in ("Dist", "LS", "Demand", "Price"):
            def sort_key(item):
                val = item[0].replace(',', '').replace(' CR', '')
                try:
                    return float(val)
                except ValueError:
                    return float('-inf') if reverse else float('inf')
            data.sort(key=sort_key, reverse=reverse)
        else:
            data.sort(key=lambda item: item[0].lower(), reverse=reverse)

        for index, (_val, child) in enumerate(data):
            tree.move(child, '', index)

        self._bp_sort_reverse[col] = not reverse
        arrow = " ▼" if reverse else " ▲"
        for c in self.BP_COLUMNS:
            tree.heading(c, text=self._bp_column_labels[c] + (arrow if c == col else ""),
                         command=lambda c=c: self._bp_sort(c))

    # --- row actions ---------------------------------------------------------------

    def _bp_copy_system(self, row_id):
        system = self._bp['system_by_row'].get(row_id)
        if system:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(system)
            self.parent.update_idletasks()
            self.status_var.set(f"Copied '{system}' to clipboard")

    @staticmethod
    def _bp_open_url(url_template, system):
        if not system:
            return
        import urllib.parse
        import webbrowser
        webbrowser.open(url_template.format(urllib.parse.quote(system)))

    def _bp_open_inara_and_fetch_pp(self, row_id, system):
        """Open Inara and fetch/store its PowerPlay data - same as the main Hotspots
        Finder table's PowerPlay-cell click (_open_inara/_fetch_pp_from_inara)."""
        self._bp_open_url("https://inara.cz/elite/starsystem/?search={}", system)

        def worker():
            from system_finder_api import SystemFinderAPI
            result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system)
            self.parent.after(0, lambda: self._bp_apply_pp_result(row_id, result))
        threading.Thread(target=worker, daemon=True).start()

    def _bp_apply_pp_result(self, row_id, result):
        tree = self._bp_tree
        if not result or not tree.exists(row_id):
            return
        vals = list(tree.item(row_id, 'values'))
        if len(vals) > 9:
            vals[9] = self._bp_pp_text(result)
            tree.item(row_id, values=vals)

    def _bp_on_click(self, event):
        self._bp_close_extra_picker()
        tree = self._bp_tree
        row_id = tree.identify_row(event.y)
        col = displayed_column(tree, tree.identify_column(event.x))
        if not row_id:
            return
        if col == "Station":
            tree.selection_set(row_id)
            self._bp_copy_system(row_id)
        elif col == "PowerPlay":  # open Inara and refresh PP data, same as main table
            tree.selection_set(row_id)
            system = self._bp['system_by_row'].get(row_id, '')
            if system:
                self._bp_open_inara_and_fetch_pp(row_id, system)

    def _bp_on_right_click(self, event):
        tree = self._bp_tree
        row_id = tree.identify_row(event.y)
        if not row_id:
            return
        tree.selection_set(row_id)
        # Rows without a price have no station system to copy or open
        state = "normal" if self._bp['system_by_row'].get(row_id) else "disabled"
        for index in range(2, self._bp_row_menu.index("end") + 1):
            self._bp_row_menu.entryconfig(index, state=state)
        self._bp_row_menu.tk_popup(event.x_root, event.y_root)

    def _bp_find_sell_station(self):
        selection = self._bp_tree.selection()
        if not selection:
            return
        mat = self._bp['mineral_by_row'].get(selection[0])
        if mat:
            self._find_sell_station_impl(mineral_override=mat, system_override=self._bp['system'])

    # --- "+ Add Minerals" ------------------------------------------------------------

    def _bp_sync_extra_vars(self):
        # Minerals already fetched upfront (previously saved picks) show as ticked
        already_fetched = {r[0] for r in self._bp['results']}
        self._bp['extra_vars'] = {mat: tk.BooleanVar(value=mat in already_fetched)
                                  for mat in self._bp['extra_candidates']}

    def _bp_on_extra_toggle(self, mat):
        bp = self._bp
        try:
            from config import save_also_check_minerals
            save_also_check_minerals([m for m, var in bp['extra_vars'].items() if var.get()])
        except Exception:
            pass
        if bp['extra_vars'][mat].get():
            if not any(r[0] == mat for r in bp['results']):
                threading.Thread(target=self._bp_fetch_extra_mineral, args=(mat, bp['system'], self._bp_req), daemon=True).start()
        else:
            bp['results'][:] = [r for r in bp['results'] if r[0] != mat]
            self._bp_populate()

    def _bp_fetch_extra_mineral(self, mat, system_name, req):
        from marketplace_api import MarketplaceAPI
        try:
            rows = MarketplaceAPI.search_buyers(mat, system_name, None, 7, False)
        except Exception:
            rows = []
        priced_rows = [r for r in rows if r.get('sellPrice', 0) > 0]
        best = max(priced_rows, key=lambda r: r.get('sellPrice', 0)) if priced_rows else None
        self.parent.after(0, lambda: self._bp_add_extra_result(mat, best, priced_rows, req))

    def _bp_add_extra_result(self, mat, best, priced_rows, req):
        bp = self._bp
        if req != self._bp_req:
            return  # the view moved on to another system meanwhile
        if bp['extra_vars'].get(mat) and not bp['extra_vars'][mat].get():
            return  # unchecked again before the fetch finished
        bp['results'].append((mat, best, priced_rows))
        bp['results'].sort(key=lambda r: r[1].get('sellPrice', 0) if r[1] else -1, reverse=True)
        self._bp_populate()

    def _bp_show_extra_picker(self):
        """Persistent picker so several minerals can be ticked in one go (a tk.Menu
        checkbutton closes on every click)."""
        from config import scaled_font, scaled_px, load_theme
        bp = self._bp
        existing = bp.get('picker')
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.lift()
                    existing.focus_force()
                    return
            except Exception:
                pass
        candidates = bp['extra_candidates']
        if not candidates:
            self.status_var.set(t('ring_finder.no_hotspot_minerals'))
            return

        theme = load_theme()
        if theme == "elite_orange":
            bg, fg = "#1e1e1e", "#ff8c00"
        else:
            bg, fg = MENU_COLORS["bg"], MENU_COLORS["fg"]

        picker = tk.Toplevel(self._bp_frame)
        picker.withdraw()
        try:
            from app_utils import get_app_icon_path
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                picker.iconbitmap(icon_path)
        except Exception:
            pass
        picker.title(t('ring_finder.also_check_menu_title'))
        picker.resizable(False, False)
        picker.configure(bg=bg)

        picker_frame = tk.Frame(picker, bg=bg, padx=15, pady=12)
        picker_frame.pack(fill="both", expand=True)

        # Cap the list height and scroll instead of growing past the screen
        MAX_VISIBLE_ROWS = 8
        ROW_HEIGHT_PX = scaled_px(26)
        list_canvas = tk.Canvas(picker_frame, bg=bg, highlightthickness=0, width=scaled_px(220),
                                height=min(len(candidates), MAX_VISIBLE_ROWS) * ROW_HEIGHT_PX)
        list_canvas.pack(side="top", fill="both", expand=True)
        if len(candidates) > MAX_VISIBLE_ROWS:
            list_scrollbar = ttk.Scrollbar(picker_frame, orient="vertical", command=list_canvas.yview)
            list_scrollbar.place(in_=list_canvas, relx=1.0, rely=0, relheight=1.0, anchor="ne")
            list_canvas.configure(yscrollcommand=list_scrollbar.set)

        checklist_frame = tk.Frame(list_canvas, bg=bg)
        list_canvas.create_window((0, 0), window=checklist_frame, anchor="nw")
        for mat in candidates:
            ThemedCheckbutton(checklist_frame, text=self._format_material_for_display(mat),
                              variable=bp['extra_vars'][mat], command=lambda m=mat: self._bp_on_extra_toggle(m),
                              bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                              selectcolor=bg, font=scaled_font(9), anchor="w").pack(fill="x", anchor="w")
        checklist_frame.update_idletasks()
        list_canvas.configure(scrollregion=list_canvas.bbox("all"))

        def on_mousewheel(event):
            if len(candidates) > MAX_VISIBLE_ROWS:
                list_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        def bind_wheel(widget):
            widget.bind("<MouseWheel>", on_mousewheel, add='+')
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(list_canvas)

        ttk.Button(picker_frame, text=t('common.close'), command=self._bp_close_extra_picker).pack(anchor="e", pady=(10, 0))
        picker.protocol("WM_DELETE_WINDOW", self._bp_close_extra_picker)

        bp['picker'] = picker
        self._bp_place_extra_picker()
        picker.deiconify()
        picker.attributes('-topmost', True)
        picker.lift()
        picker.focus_force()
        # Follow the button and close once the view is hidden or the app loses focus -
        # polled, because binding <Configure>/<Button-1> on the main window would need an
        # unbind that also drops the app's own handlers for those events.
        picker.after(400, self._bp_follow_extra_picker)

    def _bp_place_extra_picker(self):
        picker = self._bp.get('picker')
        try:
            btn = self._bp_extra_btn
            anchor = (btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height() + 2)
            picker.geometry(f"+{anchor[0]}+{anchor[1]}")
            self._bp['picker_anchor'] = anchor
        except Exception:
            pass

    def _bp_follow_extra_picker(self):
        picker = self._bp.get('picker')
        try:
            if picker is None or not picker.winfo_exists():
                return
            try:
                app_focused = self.parent.focus_get() is not None
            except Exception:
                app_focused = True
            if not self._bp_extra_btn.winfo_viewable() or not app_focused:
                self._bp_close_extra_picker()
                return
            # Re-anchor only when the button moved (main window moved/resized), so the
            # picker can still be dragged somewhere else
            btn = self._bp_extra_btn
            if (btn.winfo_rootx(), btn.winfo_rooty() + btn.winfo_height() + 2) != self._bp.get('picker_anchor'):
                self._bp_place_extra_picker()
            picker.after(200, self._bp_follow_extra_picker)
        except Exception:
            pass

    def _bp_close_extra_picker(self):
        bp = getattr(self, '_bp', None)
        if not bp:
            return
        picker = bp.get('picker')
        bp['picker'] = None
        if picker is not None:
            try:
                if picker.winfo_exists():
                    picker.destroy()
            except Exception:
                pass

    # --- loading -------------------------------------------------------------------

    def _saved_system_spelling(self, name: str) -> str:
        """The search results' spelling of a typed system name - the hotspot lookup
        matches names exactly, capitals included."""
        wanted = name.lower()
        for item in self.results_tree.get_children():
            values = self.results_tree.item(item, 'values')
            if len(values) > 2 and str(values[2]).lower() == wanted:
                return values[2]
        return name

    def _bp_clear(self, hint: str):
        """Empty the view (no stale prices from another system) and show hint in the table."""
        self._bp_new_request()
        self._bp_close_extra_picker()
        bp = self._bp
        bp.update(system='', results=[], extra_candidates=[], ring_name='', busy=False, hint=hint)
        self._bp_populate()
        self._bp_refresh_controls()

    def _selected_ring_name(self) -> str:
        sel = self.results_tree.selection()
        values = self.results_tree.item(sel[0], 'values') if sel else ()
        return values[3] if len(values) > 3 else ''

    def _rank_minerals_for_system(self, scope: str = 'ring', system_name: str = None):
        """Right-click "Best Minerals to Mine": price the selected row and show the Best Prices
        view. system_name prices that whole system instead (Best Prices click, no row selected)."""
        inputs = self._rank_minerals_inputs(scope, system_name=system_name)
        if inputs is None:
            if system_name:
                self._bp_clear(t('ring_finder.best_prices_no_hotspots').format(system=system_name))
            return
        ring_name = '' if system_name else self._selected_ring_name()
        system_name, fetch_materials, extra_candidates, mineral_ring_types = inputs
        req = self._bp_new_request()

        cached_results = self._cached_rank_results(system_name, fetch_materials)
        if cached_results is not None:
            self._show_best_prices(system_name, cached_results, extra_candidates, mineral_ring_types,
                                   scope=scope, ring_name=ring_name, req=req)
            return

        self._show_results_view('best_prices')
        self._bp_set_busy(True, system_name)
        threading.Thread(target=self._rank_minerals_worker,
                         args=(system_name, fetch_materials, extra_candidates, mineral_ring_types, scope, ring_name, req, False),
                         daemon=True).start()

    def _rank_minerals_worker(self, system_name: str, materials: List[str], extra_candidates: List[str],
                              mineral_ring_types: Dict[str, set], scope: str, ring_name: str, req: int, force: bool):
        """Background worker: fetch best sell price per mineral (cached unless force), then
        show them. extra_candidates are only offered in "+ Add Minerals", not fetched here."""
        from system_finder_api import SystemFinderAPI
        try:
            results = None if force else self._cached_rank_results(system_name, materials)
            if results is None:
                results = self._fetch_mineral_prices(system_name, materials)
            names = list({best.get('systemName', '') for _, best, _ in results if best and best.get('systemName')} | {system_name})
            pp_data = SystemFinderAPI._batch_get_powerplay(names) if names else {}
        except Exception:
            log.exception("Best Prices lookup failed for %s", system_name)
            # Otherwise the view stays on "Updating..." with its buttons disabled
            self.parent.after(0, lambda: req == self._bp_req and self._bp_lookup_failed())
            return
        self.parent.after(0, lambda: self._finish_rank_request(system_name, results, extra_candidates, mineral_ring_types,
                                                               scope, ring_name, pp_data, req))

    def _finish_rank_request(self, system_name, results, extra_candidates, mineral_ring_types, scope, ring_name, pp_data, req):
        if req != self._bp_req:
            return
        self._show_best_prices(system_name, results, extra_candidates, mineral_ring_types, scope=scope,
                               ring_name=ring_name, pp_data=pp_data, req=req)

    def _bp_reload(self, new_scope: str, force: bool):
        """Scope switch / Refresh: reload the view in place. Ring scope re-reads the
        hotspot table's selected row; system scope uses the shown system."""
        bp = self._bp
        if bp['busy'] or not bp['system']:
            return
        if new_scope == 'ring':
            inputs = self._rank_minerals_inputs('ring')
            ring_name = self._selected_ring_name()
        else:
            inputs = self._rank_minerals_inputs('system', system_name=bp['system'])
            ring_name = bp['ring_name']
        if inputs is None:
            return
        system_name, fetch_materials, new_extras, new_ring_types = inputs
        self._bp_close_extra_picker()
        req = self._bp_new_request()
        self._bp_set_busy(True, system_name)
        threading.Thread(target=self._rank_minerals_worker,
                         args=(system_name, fetch_materials, new_extras, new_ring_types, new_scope, ring_name, req, force),
                         daemon=True).start()

    @staticmethod
    def _view_button_style() -> dict:
        """Button colours for the results views' control rows, from the active theme
        (Modern themes draw their own rounded buttons and ignore these)."""
        from config import load_theme, scaled_font
        from ui.theme import get_theme_colors
        colors = get_theme_colors(load_theme())
        return dict(bg=colors['btn_bg'], fg=colors['btn_fg'], activebackground=colors['btn_bg_hover'],
                    activeforeground=colors['btn_fg'], relief="raised", bd=1, cursor="hand2",
                    padx=15, pady=2, font=scaled_font(8, "normal"))

    def _show_results_view(self, view: str):
        var = getattr(self, '_results_view_var', None)
        if var is not None and var.get() != view:
            var.set(view)

    def _on_results_view_click(self):
        """A click on Best Prices loads the selected hotspot row, unless that ring is already
        shown. With no row selected it loads the Reference System's whole-system prices when
        the shown prices are for another system; otherwise it only switches."""
        if self._results_view_var.get() == 'acquisition':
            self._acq_on_view_click()
            return
        if self._results_view_var.get() == 'merit_miner':
            self._mm_on_view_click()
            return
        if self._results_view_var.get() == 'best_mining':
            self._bm_on_view_click()
            return
        bp = self._bp
        if self._results_view_var.get() != 'best_prices' or bp['busy']:
            return
        selection = self.results_tree.selection()
        if not selection:
            reference = self.system_var.get().strip()
            if reference and reference.lower() != bp['system'].lower():
                self._rank_minerals_for_system('system', system_name=self._saved_system_spelling(reference))
            return
        values = self.results_tree.item(selection[0], 'values')
        if not values or len(values) < 9:
            return
        if bp['system'] == values[2] and bp['ring_name'] == values[3]:
            return
        self._rank_minerals_for_system('ring')

    def _apply_results_view(self):
        """Show the hotspot table, the Best Prices, Where to Mine, Acquisition or Merit
        Miner view, each with its own Columns button."""
        from config import scaled_px
        view = self._results_view_var.get()
        acq_frame = getattr(self, '_acq_frame', None)
        mm_frame = getattr(self, '_mm_frame', None)
        bm_frame = getattr(self, '_bm_frame', None)
        if ((view == 'acquisition' and acq_frame is None) or (view == 'merit_miner' and mm_frame is None)
                or (view == 'best_mining' and bm_frame is None)):
            view = 'hotspots'
        more_btn = getattr(self, '_more_btn', None)  # Modern only; opens hotspot search filters
        status = getattr(self, '_results_status_label', None)
        before = {'before': status} if status is not None and status.winfo_manager() else {}
        for btn in (self._columns_btn, more_btn):
            if btn is not None:
                btn.pack_forget()
        # Status, More filters and Columns belong to the hotspot table; the other views
        # have their own label row
        tools_row = getattr(self, '_results_tools_row', None)
        if tools_row is not None:
            if view != 'hotspots':
                tools_row.pack_forget()
            elif not tools_row.winfo_manager():
                tools_row.pack(fill="x", padx=(10, 15), pady=(6, 0), after=self._results_header)
        if view != 'best_prices':
            self._bp_close_extra_picker()
        for frame in (self._hotspots_tree_frame, self._bp_frame, acq_frame, mm_frame, bm_frame):
            if frame is not None:
                frame.pack_forget()
        if view == 'best_prices':
            self._bp_frame.pack(fill="both", expand=True)
        elif view == 'acquisition':
            acq_frame.pack(fill="both", expand=True)
        elif view == 'merit_miner':
            mm_frame.pack(fill="both", expand=True)
        elif view == 'best_mining':
            bm_frame.pack(fill="both", expand=True)
        else:
            self._hotspots_tree_frame.pack(fill="both", expand=True, padx=5, pady=(5, 2))
            self._columns_btn.pack(side="right", padx=(scaled_px(8), 0), **before)
            if more_btn is not None:
                more_btn.pack(side="right", padx=(0, 8), **before)

    # --- Auto Prices -----------------------------------------------------------------

    def _schedule_auto_return(self, req: int, duration_ms: int):
        """After the Auto Prices display time, switch back to Hotspots - unless "Return to
        Hotspots" is off, the user used the app meanwhile, or other prices replaced these."""
        import time
        pending = getattr(self, '_bp_return_after', None)
        if pending is not None:
            try:
                self.parent.after_cancel(pending)
            except Exception:
                pass
        self._bp_return_after = self.parent.after(duration_ms, lambda: self._auto_return_to_hotspots(req, time.monotonic()))

    def _auto_return_to_hotspots(self, req: int, shown_at: float):
        self._bp_return_after = None
        if req != self._bp_req or not self.prices_return_var.get():
            return
        main_app = getattr(getattr(self, 'prospector_panel', None), 'main_app', None)
        if getattr(main_app, '_last_ui_activity', 0) > shown_at:
            return  # the user is reading or using the app, keep the prices
        self._show_results_view('hotspots')

    def _on_auto_prices_ready(self, system_name: str, results: list, extra_candidates, mineral_ring_types):
        # A fetch started at StartJump can finish mid-jump; hold it until FSDJump arrives there
        if self.last_monitored_system == system_name:
            self._present_auto_prices(system_name, results, extra_candidates, mineral_ring_types)
        else:
            self._pending_auto_prices = (system_name, results, extra_candidates, mineral_ring_types)

    def _present_auto_prices(self, system_name: str, results: list, extra_candidates, mineral_ring_types):
        """Show prefetched prices in the Best Prices view (switching to it), plus on the
        text overlay when that option is chosen and the overlay is on."""
        # A lookup started before Auto Prices was turned off must not switch the view
        if not self.prefetch_prices_var.get():
            return
        req = self._bp_new_request()
        self._show_best_prices(system_name, results, extra_candidates, mineral_ring_types, scope='system', req=req)

        main_app = getattr(getattr(self, 'prospector_panel', None), 'main_app', None)
        duration_var = getattr(main_app, 'auto_prices_overlay_duration', None)
        duration_ms = int(duration_var.get() if duration_var is not None else 20) * 1000
        self._schedule_auto_return(req, duration_ms)

        text_overlay = None
        if self.prices_overlay_var.get():
            text_overlay = getattr(main_app, 'text_overlay', None)
        # Only while still in supercruise after the jump - if the user already dropped, skip
        if text_overlay is not None and text_overlay.overlay_enabled and getattr(self, '_in_sc_since_jump', False):
            self._prices_overlay_active = True
            text_overlay.show_message(self._build_prices_overlay_text(system_name, results), duration_ms=duration_ms, ignore_sc_hide=True, wrap_width=1300)
            self.parent.after(duration_ms, lambda: setattr(self, '_prices_overlay_active', False))
