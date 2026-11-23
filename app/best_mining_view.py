# -*- coding: utf-8 -*-
"""
Where to Mine view of the Hotspots Finder (the Best Mining System search): mining systems
near the Reference System, ranked by the best live sell price for their hotspot minerals.
Mixed into RingFinder (ring_finder.py).
"""
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from acquisition_view import _OverlayStatus
from column_visibility_helper import displayed_column
from core.constants import MENU_COLORS
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from ui.themed_checkbox import ThemedCheckbutton

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key


class _BMOverlayStatus(_OverlayStatus):
    def config(self, text=''):
        self._view._bm_set_status(text)


class BestMiningMixin:
    BM_COLUMNS = ("System", "Dist", "Mineral", "Price", "Station", "SellDist", "Type", "LS", "PowerPlay", "Updated")
    BM_DEFAULT_WIDTHS = {"System": 200, "Dist": 80, "Mineral": 130, "Price": 110, "Station": 260, "SellDist": 90,
                         "Type": 110, "LS": 70, "PowerPlay": 200, "Updated": 90}
    BM_NUMERIC_COLUMNS = ("Dist", "SellDist", "LS", "Price")
    BM_DISTANCES = ("10", "20", "30", "50", "100", "150", "200")
    BM_MAX_CANDIDATES = 20

    # ---------------------------------------------------------------------------------
    # Where to Mine view: fifth view of the Hotspots Finder results area
    # ---------------------------------------------------------------------------------

    def _build_best_mining_view(self, parent, bg: str, select_bg: str, tree_bg: str, tree_fg: str):
        import tkinter.font as tkfont
        from config import (scaled_font, scaled_px, load_theme, load_pp_mode,
                            load_reverse_search_mineral)
        from ui.cell_tooltip import attach_cell_tooltip

        current_theme = load_theme()
        fg = "#ff8c00" if current_theme == "elite_orange" else "#e6e6e6"

        self._bm = {
            'busy': False, 'status': '', 'hint': '', 'spin': 0, 'spinning': False, 'ran': False,
            'system': '', 'count': 0, 'cache': None,
            'system_by_row': {}, 'sell_system_by_row': {}, 'source_by_row': {},
        }

        frame = ttk.Frame(parent)
        self._bm_frame = frame

        # Right-hand controls are packed first so a narrow window clips the label, not them
        top_row = tk.Frame(frame, bg=bg)
        top_row.pack(fill="x", padx=5, pady=(5, 4))
        self._bm_columns_btn = self._cv_add_columns_button(top_row, 'best_mining')

        btn_style = self._view_button_style()
        self._bm_search_btn = self._rf_button(top_row, text=t('ring_finder.search'), **btn_style,
                                              command=self._bm_on_search)
        self._bm_search_btn.pack(side="right")

        # Shared with Best Prices, Auto Options and Settings (in-system prices)
        self._bm_pp_mode_var = tk.BooleanVar(value=load_pp_mode())
        ThemedCheckbutton(top_row, text=t('ring_finder.where_to_mine_pp_mode'), variable=self._bm_pp_mode_var,
                          command=self._bm_on_pp_toggle, bg=bg, fg=fg, activebackground=bg,
                          activeforeground=fg, selectcolor=select_bg, font=scaled_font(9)).pack(side="right", padx=(0, 12))

        self._bm_distance_var = tk.StringVar(value="50")
        distance_combo = ttk.Combobox(top_row, textvariable=self._bm_distance_var, width=6, state="readonly",
                                      values=self.BM_DISTANCES)
        distance_combo.pack(side="right", padx=(0, 12))
        distance_combo.bind('<<ComboboxSelected>>', lambda e: distance_combo.selection_clear(), add='+')
        ttk.Label(top_row, text=t('ring_finder.reverse_search_max_distance')).pack(side="right", padx=(0, 4))

        self._bm_all_label = t('ring_finder.all_minerals')
        available = self._get_available_materials()
        saved = load_reverse_search_mineral()
        saved_display = next((m for m in available[1:] if self._bm_to_english(m) == saved), None) if saved else None
        self._bm_mineral_var = tk.StringVar(value=saved_display or self._bm_all_label)
        self._bm_mineral_combo = ttk.Combobox(top_row, textvariable=self._bm_mineral_var, width=16, state="readonly",
                                              values=(self._bm_all_label,) + tuple(available[1:]))
        self._bm_mineral_combo.pack(side="right", padx=(0, 12))
        self._bm_mineral_combo.bind('<<ComboboxSelected>>', self._bm_on_mineral_selected, add='+')
        ttk.Label(top_row, text=t('ring_finder.mineral') + ':').pack(side="right", padx=(0, 4))

        self._bm_name_label = ttk.Label(top_row, text="", font=scaled_font(9, "bold"))
        self._bm_name_label.pack(side="left")

        tree_frame = ttk.Frame(frame, relief="solid", borderwidth=1)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(0, 2))

        columns = self.BM_COLUMNS
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", selectmode="browse",
                               style="RingFinder.Treeview")
        self._bm_tree = tree
        self._bm_column_labels = {
            "System": t('ring_finder.col_mine_here'),
            "Dist": t('ring_finder.col_dist'),
            "Mineral": t('ring_finder.col_best_mineral'),
            "Price": t('ring_finder.col_price'),
            "Station": t('ring_finder.col_sell_here'),
            "SellDist": t('ring_finder.merit_miner_col_sell_dist'),
            "Type": t('ring_finder.col_station_type'),
            "LS": t('ring_finder.col_ls'),
            "PowerPlay": t('ring_finder.col_powerplay'),
            "Updated": t('ring_finder.col_updated'),
        }
        self._bm_sort_reverse = {col: False for col in columns}
        heading_font = tkfont.Font(font=scaled_font(9, "bold"))
        header_pad = scaled_px(24)
        default_widths = {}
        for col in columns:
            label = self._bm_column_labels[col]
            tree.heading(col, text=label, anchor="w", command=lambda c=col: self._bm_sort(c))
            min_w = max(heading_font.measure(label) + header_pad, scaled_px(50))
            default_widths[col] = max(scaled_px(self.BM_DEFAULT_WIDTHS[col]), min_w)
            tree.column(col, width=default_widths[col], minwidth=min_w, anchor="w", stretch=False)

        try:
            from config import load_reverse_search_column_widths
            for col_name, width in load_reverse_search_column_widths().items():
                if col_name in columns and width > 0:
                    tree.column(col_name, width=max(width, tree.column(col_name, "minwidth")))
        except Exception:
            pass

        def save_widths(event=None):
            try:
                from config import save_reverse_search_column_widths
                save_reverse_search_column_widths({col: tree.column(col, "width") for col in columns})
            except Exception:
                pass
        tree.bind("<ButtonRelease-1>", save_widths, add='+')

        self.setup_column_visibility(tree=tree, columns=columns, default_widths=default_widths,
                                     config_key='best_mining', use_displaycolumns=True, allow_reorder=True)
        attach_cell_tooltip(tree, "Updated", lambda item: self._bm['source_by_row'].get(item, ''))

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self._bm_overlay = tk.Frame(tree_frame, bg=tree_bg)
        self._bm_overlay_label = tk.Label(self._bm_overlay, text="", bg=tree_bg, fg=tree_fg,
                                          justify="center", wraplength=scaled_px(600))
        self._bm_overlay_label.place(relx=0.5, rely=0.5, anchor="center")
        self._bm_overlay.grid(row=0, column=0, sticky="nsew")
        self._bm_overlay_fonts = (scaled_font(14, "bold"), scaled_font(10))

        menu_colors = dict(bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                           activebackground=MENU_COLORS["activebackground"],
                           activeforeground=MENU_COLORS["activeforeground"])
        if current_theme == "elite_orange":
            menu_colors = dict(bg="#1e1e1e", fg="#ff8c00", activebackground="#ff6600", activeforeground="#000000")
        self._bm_row_menu = tk.Menu(frame, tearoff=0, font=scaled_font(9), **menu_colors)

        def selected_system():
            sel = tree.selection()
            return self._bm['system_by_row'].get(sel[0], '') if sel else ''

        self._bm_row_menu.add_command(label=t('context_menu.copy_system'),
                                      command=lambda: self._bm_copy(selected_system()))
        self._bm_row_menu.add_command(label=t('context_menu.open_inara'), command=lambda: self._bp_open_url(
            "https://inara.cz/elite/starsystem/?search={}", selected_system()))
        self._bm_row_menu.add_command(label=t('context_menu.open_edsm'), command=lambda: self._bp_open_url(
            "https://www.edsm.net/en/system/id/0/name/{}", selected_system()))
        self._bm_row_menu.add_command(label=t('context_menu.open_spansh'), command=lambda: self._bp_open_url(
            "https://spansh.co.uk/search/{}", selected_system()))

        tree.bind("<Button-1>", self._bm_on_click)
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['best_mining'] = self._bm_on_right_click

        self._bm_control = SearchControl(self.parent, self._bm_search_btn, _BMOverlayStatus(self),
                                         on_finish=self._bm_on_finish)
        self._bm_refresh_controls()

    # --- inputs --------------------------------------------------------------------

    def _bm_to_english(self, display: str) -> str:
        mineral = self._to_english(display)
        return "Low Temperature Diamonds" if mineral == "Low Temp Diamonds" else mineral

    def _bm_mineral_filter(self) -> Optional[str]:
        """None for All Minerals, else the full English mineral name."""
        display = self._bm_mineral_var.get()
        return None if display == self._bm_all_label else self._bm_to_english(display)

    def _bm_on_mineral_selected(self, event=None):
        from config import save_reverse_search_mineral
        self._bm_mineral_combo.selection_clear()
        save_reverse_search_mineral(self._bm_mineral_filter() or "")

    def _bm_on_pp_toggle(self):
        """Re-rank the fetched prices for the new mode; no new search."""
        from config import save_pp_mode
        save_pp_mode(self._bm_pp_mode_var.get())
        self._bm_rerender()

    def _bm_sync_pp_mode(self):
        """Pick up the shared in-system setting if Best Prices or Settings changed it."""
        from config import load_pp_mode
        pp_mode = load_pp_mode()
        if self._bm_pp_mode_var.get() != pp_mode:
            self._bm_pp_mode_var.set(pp_mode)
            self._bm_rerender()

    # --- state and overlay ---------------------------------------------------------

    def _bm_refresh_controls(self):
        bm = self._bm
        if not bm['busy']:
            self._bm_name_label.config(text=t('ring_finder.where_to_mine_found').format(
                count=bm['count']) if bm.get('count') else '')
        self._bm_update_overlay()

    def _bm_update_overlay(self):
        bm = self._bm
        if bm['busy']:
            chars = self._search_overlay_chars
            text = f"{bm['status']}\n\n{chars[bm['spin'] % len(chars)]}"
            font = self._bm_overlay_fonts[0]
        elif not self._bm_tree.get_children():
            text = bm['hint'] or t('ring_finder.where_to_mine_empty')
            font = self._bm_overlay_fonts[1]
        else:
            self._bm_overlay.grid_remove()
            return
        self._bm_overlay_label.configure(text=text, font=font)
        self._bm_overlay.grid()
        self._bm_overlay.tkraise()

    def _bm_spin(self):
        bm = self._bm
        if not bm['busy']:
            bm['spinning'] = False
            return
        bm['spin'] += 1
        self._bm_update_overlay()
        self.parent.after(100, self._bm_spin)

    def _bm_set_status(self, text: str):
        bm = self._bm
        bm['status'] = text
        bm['hint'] = text
        self._bm_update_overlay()

    def _bm_on_finish(self):
        self._bm['busy'] = False
        self._bm_refresh_controls()

    # --- running a search ----------------------------------------------------------

    def _bm_show_view(self):
        """Best Mining System button and voice command: show the view (searching the
        first time, like a click on the view)."""
        self._show_results_view('best_mining')
        self._bm_on_view_click()

    def _bm_on_view_click(self):
        """A click on Where to Mine shows the view; the first time, it also searches when
        a Reference System is set."""
        self._bm_sync_pp_mode()
        if not self._bm['ran'] and not self._bm_control.running and self.system_var.get().strip():
            self._bm_start()

    def _bm_on_search(self):
        if self._bm_control.running:
            self._bm_control.stop()
        else:
            self._bm_start()

    def _bm_start(self):
        bm = self._bm
        reference = self.system_var.get().strip()
        if not reference:
            bm.update(hint=t('ring_finder.enter_reference_system'), count=0, cache=None)
            self._bm_fill([])
            return
        reference = self._saved_system_spelling(reference)
        try:
            max_distance = float(self._bm_distance_var.get())
        except (TypeError, ValueError):
            max_distance = 50.0
        mineral_filter = self._bm_mineral_filter()
        bm.update(busy=True, ran=True, hint='', system=reference, count=0, cache=None,
                  status=t('ring_finder.reverse_search_searching').format(system=reference))
        self._bm_fill([])
        self._show_results_view('best_mining')
        control = self._bm_control
        control.start()
        self._bm_refresh_controls()
        if not bm['spinning']:
            bm['spinning'] = True
            bm['spin'] = 0
            self._bm_spin()
        threading.Thread(target=control.run,
                         args=(self._reverse_search_worker, reference, max_distance, mineral_filter, control),
                         daemon=True).start()

    def _reverse_search_worker(self, target_system: str, max_distance: float, mineral_filter: Optional[str], control):
        """Background worker: find candidate mining systems near target_system and fetch
        live prices for their hotspot minerals. Ranking happens on the UI thread, so the
        PowerPlay-mode box can re-rank the same prices without a new search.

        mineral_filter: None for all minerals, or an exact full mineral name (e.g.
        'Painite') to restrict candidates to that one mineral's hotspots."""
        try:
            hotspots = self._get_hotspots(target_system, 'All', 'All Minerals', False,
                                          max_distance, max_results=None, data_source='database', is_cancelled=control.is_cancelled)
        except Exception:
            hotspots = []

        # Collect unique candidate systems (nearest first), each with its distinct hotspot minerals.
        # 'type' can be a single material name or a combined "Mona(1), Rhod(1)" display string
        # (the "All Minerals" view groups every hotspot in a ring into one field) - parse it the
        # same way Rank Minerals does rather than assuming one material per row.
        candidates = {}
        for h in hotspots:
            sys_name = h.get('systemName', h.get('system', ''))
            type_field = h.get('type', h.get('material_name', ''))
            if not sys_name or not type_field:
                continue
            try:
                distance = float(h.get('distance', 999999))
            except (TypeError, ValueError):
                distance = 999999.0
            entry = candidates.setdefault(sys_name, {'distance': distance, 'materials': set(), 'coords': None})
            if not entry['coords'] and h.get('coords'):
                entry['coords'] = h['coords']
            for mat in self._parse_materials_from_hotspots(type_field):
                full_mat = self._expand_abbreviated_materials(mat)
                if mineral_filter is not None and full_mat != mineral_filter:
                    continue
                entry['materials'].add(full_mat)

        # Drop candidates left with no materials after filtering
        candidates = {sys_name: entry for sys_name, entry in candidates.items() if entry['materials']}

        candidate_list = sorted(candidates.items(), key=lambda kv: kv[1]['distance'])[:self.BM_MAX_CANDIDATES]

        if not candidate_list or control.is_cancelled():
            hint = t('ring_finder.reverse_search_no_candidates').format(system=target_system)
            control.complete([], lambda rows: self._bm_show_no_results(hint))
            return

        # One live fetch per unique mineral, centered on target_system - candidates near
        # the same target share these results, so this stays cheap regardless of how
        # many candidates there are (each search_buyers call already does a paginated
        # Ardent+Spansh+EDDN fetch, so one per (candidate, mineral) pair was minutes-slow).
        from marketplace_api import MarketplaceAPI
        from concurrent.futures import ThreadPoolExecutor

        rows_by_material = {}
        unique_materials = list({mat for _, entry in candidate_list for mat in entry['materials']})
        def fetch(mat):
            if control.is_cancelled():
                return []
            return MarketplaceAPI.search_buyers(mat, target_system, None, 7, False, is_cancelled=control.is_cancelled)

        with ThreadPoolExecutor(max_workers=min(len(unique_materials), 4)) as pool:
            futures = {pool.submit(fetch, mat): mat for mat in unique_materials}
            for future in futures:
                mat = futures[future]
                try:
                    rows = future.result()
                except Exception:
                    rows = []
                rows_by_material[mat] = [r for r in rows if r.get('sellPrice', 0) > 0]

        # Candidate coordinates for local (non-PP) distance re-ranking. The hotspot rows
        # carry them; the bundled galaxy database lacks many hotspot systems, so it is only
        # the fallback (local SQLite, no network calls).
        candidate_coords = {sys_name: entry['coords'] for sys_name, entry in candidate_list if entry.get('coords')}
        missing = [sys_name for sys_name, _entry in candidate_list if sys_name not in candidate_coords]
        if missing:
            try:
                from local_database import LocalSystemsDatabase
                local_db = LocalSystemsDatabase()
                if local_db.is_database_available():
                    for sys_name in missing:
                        coords = local_db.get_system_coordinates(sys_name)
                        if coords:
                            candidate_coords[sys_name] = coords
            except Exception:
                pass

        cache = {
            'target_system': target_system,
            'candidates': candidate_list,
            'rows_by_material': rows_by_material,
            'candidate_coords': candidate_coords,
            'max_distance': max_distance,
        }
        # Partial prices after a Stop still show (SearchControl runs this when rows exist)
        control.complete(candidate_list, lambda rows: self._bm_show_results(cache))

    @staticmethod
    def _rerank_reverse_search_results(target_system: str, candidate_list, rows_by_material: dict,
                                       candidate_coords: dict, max_distance: float, pp_mode: bool) -> list:
        """Rank candidates by best-priced mineral from already-fetched price data:
        [{system, distance, mineral, best}] highest price first."""
        def dist_from_candidate(coords, r):
            sx, sy, sz = r.get('systemX'), r.get('systemY'), r.get('systemZ')
            if sx is None or sy is None or sz is None:
                return None
            try:
                return ((float(sx) - coords['x'])**2 + (float(sy) - coords['y'])**2
                         + (float(sz) - coords['z'])**2) ** 0.5
            except (TypeError, ValueError):
                return None

        def best_for(sys_name, mat):
            priced_rows = rows_by_material.get(mat, [])
            if pp_mode:
                # PowerPlay reinforce/undermine/acquisition only pay out for sales made
                # exactly in target_system.
                priced_rows = [r for r in priced_rows if r.get('systemName', '') == target_system]
                return max(priced_rows, key=lambda r: r.get('sellPrice', 0)) if priced_rows else None

            # Outside PP mode, pick the nearest priced station to THIS candidate, capped
            # to the same Max Distance the user searched with - a station outside that
            # radius isn't "local" no matter how much closer it is than the target-wide
            # best price, so it's better to show No data than a misleadingly far seller.
            coords = candidate_coords.get(sys_name)
            if coords is None:
                return None

            rows_with_dist = [(r, dist_from_candidate(coords, r)) for r in priced_rows]
            rows_with_dist = [(r, d) for r, d in rows_with_dist if d is not None and d <= max_distance]
            if not rows_with_dist:
                return None
            best_row, _ = min(rows_with_dist, key=lambda rd: rd[1])
            return best_row

        results = []
        for sys_name, entry in candidate_list:
            best_mat = None
            best_price = None
            coords = candidate_coords.get(sys_name)
            for mat in entry['materials']:
                priced = best_for(sys_name, mat)
                if priced and (best_price is None or priced.get('sellPrice', 0) > best_price.get('sellPrice', 0)):
                    best_mat = mat
                    best_price = priced
            results.append({
                'system': sys_name,
                'distance': entry['distance'],
                'mineral': best_mat,
                'best': best_price,
                # Mining system to buyer; Max Distance caps it, so it explains hidden systems
                'sell_distance': dist_from_candidate(coords, best_price) if coords and best_price else None,
            })

        results.sort(key=lambda r: r['best'].get('sellPrice', 0) if r['best'] else -1, reverse=True)
        return results

    def _bm_show_no_results(self, hint: str):
        self._bm.update(hint=hint, count=0, cache=None)
        self._bm_fill([])

    def _bm_show_results(self, cache: dict):
        self._bm['cache'] = cache
        self._bm_rerender()

    def _bm_rerender(self):
        """Rank the cached prices for the current PowerPlay-mode setting and show them."""
        bm = self._bm
        cache = bm.get('cache')
        # No busy check: SearchControl runs the results callback before it clears busy, and a
        # new search clears the cache, so a toggle during a search has nothing to redraw
        if cache is None:
            return
        pp_mode = self._bm_pp_mode_var.get()
        results = self._rerank_reverse_search_results(
            cache['target_system'], cache['candidates'], cache['rows_by_material'],
            cache['candidate_coords'], cache['max_distance'], pp_mode)
        bm['hint'] = ''
        # A system with nowhere to sell nearby is no answer to "where to mine", so only
        # priced rows are listed; the hint says why when none are left
        priced = [r for r in results if r['best']]
        if results and not priced:
            if pp_mode:
                bm['hint'] = t('ring_finder.reverse_search_no_market_data').format(system=cache['target_system'])
            else:
                bm['hint'] = t('ring_finder.where_to_mine_no_buyers').format(
                    count=len(results), distance=int(cache['max_distance']))
        results = priced
        bm['count'] = len(results)
        self._bm_fill(results, pp_mode)

    def _bm_fill(self, results: list, pp_mode: bool = False):
        from app_utils import format_market_source
        from system_finder_api import SystemFinderAPI
        bm = self._bm
        tree = self._bm_tree
        tree.delete(*tree.get_children())
        for key in ('system_by_row', 'sell_system_by_row', 'source_by_row'):
            bm[key].clear()
        pp_names = list({r['best'].get('systemName', '') for r in results if r['best'] and r['best'].get('systemName')})
        pp_data = SystemFinderAPI._batch_get_powerplay(pp_names) if pp_names else {}
        for r in results:
            best = r['best']
            station_system = ''
            if best and r['mineral']:
                price = f"{best.get('sellPrice', 0):,} CR"
                station_system = best.get('systemName', '')
                if pp_mode or not station_system:
                    # Always the Reference System in PowerPlay mode, so the name alone is enough
                    station = best.get('stationName', '') or "-"
                else:
                    station = f"{best.get('stationName', '')} ({station_system})"
                station_type = self._format_station_type(best.get('stationType'))
                station_ls = best.get('distanceToArrival')
                ls = f"{int(float(station_ls)):,}" if station_ls is not None else "-"
                updated = self._format_data_age(best.get('updatedAt', ''))
                powerplay = self._bp_pp_text(pp_data.get(station_system, {}))
            else:
                price = t('ring_finder.no_data')
                station = station_type = ls = updated = powerplay = "-"
            sell_distance = r.get('sell_distance')
            sell_dist = f"{sell_distance:.1f}" if sell_distance is not None else "-"
            mineral_display = self._format_material_for_display(r['mineral']) if r['mineral'] else "-"
            row_id = tree.insert("", "end", values=(
                r['system'], f"{r['distance']:.1f}", mineral_display, price, station, sell_dist,
                station_type, ls, powerplay, updated))
            bm['system_by_row'][row_id] = r['system']
            bm['sell_system_by_row'][row_id] = station_system
            if best and r['mineral']:
                bm['source_by_row'][row_id] = format_market_source(best)
        self._bm_refresh_controls()

    def _bm_sort(self, col):
        tree = self._bm_tree
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        reverse = self._bm_sort_reverse[col]

        if col in self.BM_NUMERIC_COLUMNS:
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

        self._bm_sort_reverse[col] = not reverse
        arrow = " ▼" if reverse else " ▲"
        for c in self.BM_COLUMNS:
            tree.heading(c, text=self._bm_column_labels[c] + (arrow if c == col else ""),
                         command=lambda c=c: self._bm_sort(c))

    # --- row actions ---------------------------------------------------------------

    def _bm_copy(self, system: str):
        if system:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(system)
            self.parent.update_idletasks()

    def _bm_on_click(self, event):
        """PowerPlay cell: open the selling system on Inara and refresh its PowerPlay data,
        like the hotspot table. Any other cell copies the mining system."""
        tree = self._bm_tree
        row_id = tree.identify_row(event.y)
        if not row_id:
            return
        tree.selection_set(row_id)
        if displayed_column(tree, tree.identify_column(event.x)) == "PowerPlay":
            self._bm_open_inara_and_fetch_pp(row_id, self._bm['sell_system_by_row'].get(row_id, ''))
        else:
            self._bm_copy(self._bm['system_by_row'].get(row_id, ''))

    def _bm_open_inara_and_fetch_pp(self, row_id, system: str):
        if not system:
            return
        self._bp_open_url("https://inara.cz/elite/starsystem/?search={}", system)

        def worker():
            from system_finder_api import SystemFinderAPI
            result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system)
            self.parent.after(0, lambda: self._bm_apply_pp_result(row_id, system, result))
        threading.Thread(target=worker, daemon=True).start()

    def _bm_apply_pp_result(self, row_id, system: str, result):
        tree = self._bm_tree
        if not result or not tree.exists(row_id) or self._bm['sell_system_by_row'].get(row_id) != system:
            return
        tree.set(row_id, "PowerPlay", self._bp_pp_text(result))

    def _bm_on_right_click(self, event):
        row_id = self._bm_tree.identify_row(event.y)
        if row_id and self._bm['system_by_row'].get(row_id):
            self._bm_tree.selection_set(row_id)
            try:
                self._bm_row_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._bm_row_menu.grab_release()
