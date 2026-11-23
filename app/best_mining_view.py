# -*- coding: utf-8 -*-
"""
Find Best Mining System: mining systems near a system you want to sell in, ranked by
live sell price. Mixed into RingFinder (ring_finder.py).
"""
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from core.constants import MENU_COLORS
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from ui.theme import modern_color
from ui.themed_checkbox import ThemedCheckbutton

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key


class BestMiningMixin:
    def _show_reverse_search_dialog(self):
        """Show the "Find Best Mining System" dialog - pick a target (reinforcement/
        delivery) system, search nearby mining systems, rank by each candidate's own
        best hotspot mineral sell price (or, in PowerPlay mode, price at the target)."""
        from config import scaled_font, load_theme

        # Hide the main Reference System autocomplete dropdown if it's open - it's a
        # separate always-on-top Toplevel that would otherwise render behind this dialog.
        if hasattr(self, '_system_ac'):
            self._system_ac.hide()

        current_theme = load_theme()
        if current_theme == "elite_orange":
            bg, fg = "#1e1e1e", "#ff8c00"
        else:
            bg, fg = MENU_COLORS["bg"], MENU_COLORS["fg"]

        dialog = tk.Toplevel(self.parent)
        dialog.withdraw()

        try:
            from app_utils import get_app_icon_path
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass

        dialog.title(t('ring_finder.reverse_search_title'))
        dialog.resizable(True, True)
        dialog.configure(bg=bg)

        frame = tk.Frame(dialog, bg=bg, padx=15, pady=15)
        frame.pack(fill="both", expand=True)
        dialog._content_frame = frame

        input_row = tk.Frame(frame, bg=bg)
        input_row.pack(fill="x", pady=(0, 10))

        tk.Label(input_row, text=t('ring_finder.reverse_search_target_label'),
                 bg=bg, fg=fg, font=scaled_font(9)).pack(side="left")
        target_var = tk.StringVar()
        target_entry = ttk.Entry(input_row, textvariable=target_var, width=24)
        target_entry.pack(side="left", padx=(8, 15))

        from system_autocomplete import SystemAutocomplete
        SystemAutocomplete(target_entry, target_var, dialog)

        tk.Label(input_row, text=t('ring_finder.reverse_search_max_distance'),
                 bg=bg, fg=fg, font=scaled_font(9)).pack(side="left")
        max_dist_var = tk.StringVar(value="50")
        max_dist_combo = ttk.Combobox(input_row, textvariable=max_dist_var, width=6, state="readonly")
        max_dist_combo['values'] = ("10", "20", "30", "50", "100", "150", "200")
        max_dist_combo.pack(side="left", padx=(8, 15))

        second_row = tk.Frame(frame, bg=bg)
        second_row.pack(fill="x", pady=(0, 10))

        tk.Label(second_row, text=t('ring_finder.mineral'),
                 bg=bg, fg=fg, font=scaled_font(9)).pack(side="left")
        from config import load_reverse_search_mineral, save_reverse_search_mineral
        available_materials = self._get_available_materials()
        saved_mineral = load_reverse_search_mineral()
        saved_display = next((m for m in available_materials if self._to_english(m) == saved_mineral), None) if saved_mineral else None
        mineral_var = tk.StringVar(value=saved_display or t('ring_finder.all_minerals'))
        mineral_combo = ttk.Combobox(second_row, textvariable=mineral_var, width=16, state="readonly")
        mineral_combo['values'] = available_materials
        mineral_combo.pack(side="left", padx=(8, 0))

        def on_mineral_selected(event=None):
            mineral_display = mineral_var.get()
            if mineral_display == t('ring_finder.all_minerals'):
                save_reverse_search_mineral("")
            else:
                english = self._to_english(mineral_display)
                if english == "Low Temp Diamonds":
                    english = "Low Temperature Diamonds"
                save_reverse_search_mineral(english)
        mineral_combo.bind('<<ComboboxSelected>>', on_mineral_selected)

        # Off by default: this tool is general-purpose (best nearby mining system for
        # any delivery target), so it searches a price radius around the target like the
        # Commodity Market tab. PowerPlay reinforce/undermine/acquisition only pay out
        # for sales made in the exact target system - turning this on restricts pricing
        # to that exact system instead, at the cost of "No data" wherever it has no market.
        from config import load_pp_mode, save_pp_mode
        pp_mode_var = tk.BooleanVar(value=load_pp_mode())

        def on_pp_mode_toggle():
            # Re-rank/re-render from the already-fetched rows_by_material instead of a
            # second live search - same "instant toggle" behavior as Rank Minerals' own
            # PowerPlay-mode checkbox.
            save_pp_mode(pp_mode_var.get())
            if dialog._search_control.running:
                return
            cached = getattr(dialog, '_reverse_search_cache', None)
            if cached is None:
                return
            self._rerank_reverse_search_results(cached['target_system'], cached['candidates'],
                                                cached['rows_by_material'], cached['candidate_coords'],
                                                cached['max_distance'], pp_mode_var.get(), dialog, status_label, search_btn)

        pp_check = ThemedCheckbutton(second_row, text=t('ring_finder.pp_mode_checkbox_target'),
                                  variable=pp_mode_var, command=on_pp_mode_toggle, bg=bg, fg=fg,
                                  activebackground=bg, activeforeground=fg,
                                  selectcolor=bg, font=scaled_font(9))
        pp_check.pack(side="left", padx=(15, 0))

        status_label = tk.Label(frame, text="", bg=bg, fg=fg, font=scaled_font(9))
        status_label.pack(anchor="w", pady=(0, 10))

        def run_search():
            if dialog._search_control.running:
                dialog._search_control.stop()
                return
            target_system = target_var.get().strip()
            if not target_system:
                status_label.config(text=t('ring_finder.reverse_search_no_target'))
                return
            mineral_display = mineral_var.get()
            if mineral_display == t('ring_finder.all_minerals'):
                mineral_filter = None
            else:
                mineral_filter = self._to_english(mineral_display)
                if mineral_filter == "Low Temp Diamonds":
                    mineral_filter = "Low Temperature Diamonds"
            status_label.config(text=t('ring_finder.reverse_search_searching').format(system=target_system))
            dialog._search_control.start()
            threading.Thread(target=dialog._search_control.run,
                             args=(self._reverse_search_worker, target_system, float(max_dist_var.get()), mineral_filter, pp_mode_var.get(), dialog, status_label, search_btn, dialog._search_control),
                             daemon=True).start()

        search_btn = ttk.Button(input_row, text=t('ring_finder.reverse_search_search_btn'), command=run_search)
        search_btn.pack(side="left")
        dialog._search_control = SearchControl(self.parent, search_btn, status_label)

        target_entry.bind('<Return>', lambda e: run_search())

        def save_reverse_search_geometry(event=None):
            try:
                from config import save_reverse_search_window_geometry
                save_reverse_search_window_geometry({'width': dialog.winfo_width(), 'height': dialog.winfo_height()})
            except Exception:
                pass

        def close_reverse_search_dialog():
            save_reverse_search_geometry()
            dialog._search_control.stop()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", close_reverse_search_dialog)

        dialog.update_idletasks()

        try:
            from config import load_reverse_search_window_geometry
            saved_geom = load_reverse_search_window_geometry()
            if saved_geom.get('width') and saved_geom.get('height'):
                min_w, min_h = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
                dialog.geometry(f"{max(saved_geom['width'], min_w)}x{max(saved_geom['height'], min_h)}")
        except Exception:
            pass

        from ui.dialogs import center_window
        center_window(dialog, self.parent.winfo_toplevel())
        dialog.deiconify()
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except Exception:
            pass

        dialog._row_menu_open = False
        # No repeating keep-on-top loop here (unlike the modal Rank Minerals dialog) -
        # this dialog spawns its own child popups (autocomplete listbox, combobox
        # dropdown, wait dialog, right-click menu), and a 100ms re-lift loop fights all
        # of them for stacking order. One-time lift on open is enough; _close_reverse_
        # search_wait_dialog() re-lifts once after the wait popup closes.

    def _reverse_search_worker(self, target_system: str, max_distance: float, mineral_filter: Optional[str],
                               pp_mode: bool, dialog, status_label, search_btn, control):
        """Background worker: find candidate mining systems near target_system, rank each
        by its own best hotspot mineral sell price.

        mineral_filter: None for all minerals, or an exact full mineral name (e.g.
        'Painite') to restrict candidates to that one mineral's hotspots.
        pp_mode: if True, price is only counted from stations exactly in target_system
        (PowerPlay reinforce/undermine/acquisition only pay out there). If False, each
        candidate is ranked by whichever fetched station is nearest to THAT candidate
        (see _rerank_reverse_search_results) rather than simply the single best price
        near the target - otherwise every candidate would show the same distant station."""
        MAX_CANDIDATES = 20

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
            entry = candidates.setdefault(sys_name, {'distance': distance, 'materials': set()})
            for mat in self._parse_materials_from_hotspots(type_field):
                full_mat = self._expand_abbreviated_materials(mat)
                if mineral_filter is not None and full_mat != mineral_filter:
                    continue
                entry['materials'].add(full_mat)

        # Drop candidates left with no materials after filtering
        candidates = {sys_name: entry for sys_name, entry in candidates.items() if entry['materials']}

        candidate_list = sorted(candidates.items(), key=lambda kv: kv[1]['distance'])[:MAX_CANDIDATES]

        if not candidate_list or control.is_cancelled():
            control.complete([], lambda rows: self._reverse_search_no_results(target_system, dialog, status_label, search_btn))
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

        # Candidate coordinates for local (non-PP) distance re-ranking below - local
        # SQLite lookups, no network calls, so doing one per candidate is instant.
        candidate_coords = {}
        try:
            from local_database import LocalSystemsDatabase
            local_db = LocalSystemsDatabase()
            if local_db.is_database_available():
                for sys_name, _entry in candidate_list:
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
        def show_results(candidates):
            dialog._reverse_search_cache = cache
            self._rerank_reverse_search_results(
                target_system, candidates, rows_by_material, candidate_coords, max_distance, pp_mode, dialog, status_label, search_btn)
        control.complete(candidate_list, show_results)

    def _rerank_reverse_search_results(self, target_system: str, candidate_list, rows_by_material: dict,
                                       candidate_coords: dict, max_distance: float, pp_mode: bool, dialog, status_label, search_btn):
        """Rank candidates by best-priced mineral from already-fetched price data, then
        display. Called after a live search, and again (no new fetch) whenever the
        PowerPlay-mode checkbox is toggled."""
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
            })

        results.sort(key=lambda r: r['best'].get('sellPrice', 0) if r['best'] else -1, reverse=True)
        self._show_reverse_search_results(target_system, results, pp_mode, dialog, status_label, search_btn)

    def _show_reverse_search_wait_dialog(self, target_system: str):
        """Show a small "please wait" dialog while the reverse-search worker fetches
        candidate systems and live prices - same pattern as the Rank Minerals wait dialog."""
        from config import scaled_font, load_theme

        current_theme = load_theme()
        if current_theme == "elite_orange":
            bg, fg = "#1e1e1e", "#ff8c00"
        else:
            bg, fg = MENU_COLORS["bg"], MENU_COLORS["fg"]

        dialog = tk.Toplevel(self.parent)
        dialog.withdraw()

        try:
            from app_utils import get_app_icon_path
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                dialog.iconbitmap(icon_path)
        except Exception:
            pass

        dialog.title(t('ring_finder.reverse_search_title'))
        dialog.resizable(False, False)
        dialog.configure(bg=bg)

        frame = tk.Frame(dialog, bg=bg, padx=30, pady=25)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=t('ring_finder.reverse_search_searching').format(system=target_system),
                 bg=bg, fg=fg, font=scaled_font(9)).pack()

        dialog.update_idletasks()
        from ui.dialogs import center_window
        center_window(dialog, self.parent.winfo_toplevel())
        dialog.deiconify()
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except Exception:
            pass

        self._reverse_search_wait_dialog = dialog

    def _close_reverse_search_wait_dialog(self, parent_dialog=None):
        wait_dialog = getattr(self, '_reverse_search_wait_dialog', None)
        if wait_dialog is not None:
            try:
                if wait_dialog.winfo_exists():
                    wait_dialog.grab_release()
                    wait_dialog.destroy()
            except Exception:
                pass
            self._reverse_search_wait_dialog = None

        # Re-lift the search dialog now that the wait popup covering it is gone.
        if parent_dialog is not None:
            try:
                if parent_dialog.winfo_exists():
                    parent_dialog.lift()
            except Exception:
                pass

    def _reverse_search_no_results(self, target_system: str, dialog, status_label, search_btn):
        self._close_reverse_search_wait_dialog(dialog)
        status_label.config(text=t('ring_finder.reverse_search_no_candidates').format(system=target_system))
        search_btn.config(state="normal")

    def _show_reverse_search_results(self, target_system: str, results: list, pp_mode: bool, dialog, status_label, search_btn):
        """Populate the reverse search dialog with a ranked results table."""
        from config import scaled_font, load_theme

        self._close_reverse_search_wait_dialog(dialog)
        search_btn.config(state="normal")

        # In PowerPlay mode, search_buyers results are restricted to stations exactly
        # in target_system (see _reverse_search_worker) - if that system has no known
        # market at all, every candidate legitimately comes back with no price. Say so
        # plainly instead of leaving a table full of "No data" with no explanation.
        if pp_mode and results and all(not r['best'] for r in results):
            status_label.config(text=t('ring_finder.reverse_search_no_market_data').format(system=target_system))
        else:
            status_label.config(text=t('ring_finder.reverse_search_complete').format(count=len(results), system=target_system))

        # Remove any previous results table (and its wrapping frame/scrollbar) before
        # showing a new one - destroying only the tree left an empty tree_frame +
        # scrollbar behind on every search, stacking up as stray boxes in the dialog.
        old_tree_frame = getattr(dialog, '_results_tree_frame', None)
        had_previous_results = old_tree_frame is not None
        # Preserve the user's current window size across a PowerPlay-mode toggle re-render -
        # only a fresh search (no previous results table yet) should reset to natural size.
        current_width = dialog.winfo_width() if had_previous_results else None
        current_height = dialog.winfo_height() if had_previous_results else None
        if old_tree_frame is not None:
            try:
                old_tree_frame.destroy()
            except Exception:
                pass

        current_theme = load_theme()
        if current_theme == "elite_orange":
            bg, fg, tree_bg, tree_fg, header_bg = "#1e1e1e", "#ff8c00", "#1e1e1e", "#ff8c00", "#1a1a1a"
            selection_bg, selection_fg = "#ff6600", "#000000"
        elif current_theme in ("modern", "modern_slate", "modern_orange"):
            bg, fg, tree_bg, tree_fg, header_bg = MENU_COLORS["bg"], MENU_COLORS["fg"], modern_color("#1D2228"), modern_color("#E6EAF0"), modern_color("#14171B")
            selection_bg, selection_fg = modern_color("#4A3520"), "#FFFFFF"
        else:
            bg, fg, tree_bg, tree_fg, header_bg = MENU_COLORS["bg"], MENU_COLORS["fg"], "#1e1e1e", "#e6e6e6", "#2a2a2a"
            selection_bg, selection_fg = "#0078d7", "#ffffff"

        frame = dialog._content_frame

        style = ttk.Style()
        style.configure("ReverseSearch.Treeview",
                       borderwidth=1, relief="solid", bordercolor="#333333",
                       background=tree_bg, foreground=tree_fg, fieldbackground=tree_bg,
                       font=scaled_font(9))
        style.configure("ReverseSearch.Treeview.Heading",
                       borderwidth=1, relief="groove", background=header_bg, foreground=tree_fg,
                       padding=[5, 5], anchor="w", font=scaled_font(9, "bold"))
        style.map("ReverseSearch.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])

        # Bulk-fetch PowerPlay data from the local EDDN cache for all result systems in one
        # query - same pattern as Rank Minerals / Commodity Market.
        from system_finder_api import SystemFinderAPI
        pp_names = list({r['best'].get('systemName', '') for r in results if r['best'] and r['best'].get('systemName')})
        pp_data = SystemFinderAPI._batch_get_powerplay(pp_names) if pp_names else {}

        tree_frame = tk.Frame(frame, bg=bg)
        tree_frame.pack(fill="both", expand=True, pady=(0, 10))

        columns = ("System", "Dist", "Mineral", "Price", "Station", "Type", "LS", "PowerPlay", "Updated")
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", height=min(len(results), 10),
                            selectmode="browse", style="ReverseSearch.Treeview")
        column_labels = {
            "System": t('ring_finder.col_mine_here'),
            "Dist": t('ring_finder.col_dist'),
            "Mineral": t('ring_finder.col_best_mineral'),
            "Price": t('ring_finder.col_price'),
            "Station": t('ring_finder.col_sell_here'),
            "Type": t('ring_finder.col_station_type'),
            "LS": t('ring_finder.col_ls'),
            "PowerPlay": t('ring_finder.col_powerplay'),
            "Updated": t('ring_finder.col_updated'),
        }
        sort_reverse = {col: False for col in columns}

        def sort_by_column(col):
            data = [(tree.set(child, col), child) for child in tree.get_children('')]
            reverse = sort_reverse[col]

            if col in ("Dist", "LS"):
                def sort_key(item):
                    val = item[0].replace(',', '')
                    try:
                        return float(val)
                    except ValueError:
                        return float('-inf') if reverse else float('inf')
                data.sort(key=sort_key, reverse=reverse)
            elif col == "Price":
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

            sort_reverse[col] = not reverse
            arrow = " ▼" if reverse else " ▲"
            for c in columns:
                tree.heading(c, text=column_labels[c] + (arrow if c == col else ""),
                            command=lambda c=c: sort_by_column(c))

        for col in columns:
            tree.heading(col, text=column_labels[col], anchor="w", command=lambda c=col: sort_by_column(c))
        tree.column("System", width=200, minwidth=40, anchor="w", stretch=False)
        tree.column("Dist", width=80, minwidth=40, anchor="w", stretch=False)
        tree.column("Mineral", width=130, minwidth=40, anchor="w", stretch=False)
        tree.column("Price", width=110, minwidth=40, anchor="w", stretch=False)
        tree.column("Station", width=260, minwidth=40, anchor="w", stretch=False)
        tree.column("Type", width=110, minwidth=40, anchor="w", stretch=False)
        tree.column("LS", width=70, minwidth=40, anchor="w", stretch=False)
        tree.column("PowerPlay", width=200, minwidth=40, anchor="w", stretch=False)
        tree.column("Updated", width=90, minwidth=40, anchor="w", stretch=False)

        try:
            from config import load_reverse_search_column_widths
            saved_widths = load_reverse_search_column_widths()
            for col_name, width in saved_widths.items():
                try:
                    if width > 0:
                        current_minwidth = tree.column(col_name, "minwidth")
                        tree.column(col_name, width=max(width, current_minwidth))
                except Exception:
                    pass
        except Exception:
            pass

        def save_reverse_search_widths(event=None):
            try:
                from config import save_reverse_search_column_widths
                widths = {col: tree.column(col, "width") for col in columns}
                save_reverse_search_column_widths(widths)
            except Exception:
                pass
        tree.bind("<ButtonRelease-1>", save_reverse_search_widths, add='+')

        system_by_row = {}
        source_by_row = {}
        from app_utils import format_market_source
        from ui.cell_tooltip import attach_cell_tooltip
        attach_cell_tooltip(tree, "Updated", lambda item: source_by_row.get(item, ''))
        for r in results:
            best = r['best']
            if best and r['mineral']:
                price = f"{best.get('sellPrice', 0):,} CR"
                station_system = best.get('systemName', '')
                if pp_mode:
                    # Always target_system in PP mode - showing it again on every row
                    # would just repeat the System column for no reason.
                    station = best.get('stationName', '') or "-"
                else:
                    # search_buyers' radius means the station can be a different system
                    # than the one in the System column - show which one it actually is.
                    station = f"{best.get('stationName', '')} ({station_system})" if station_system else (best.get('stationName', '') or "-")
                station_type = self._format_station_type(best.get('stationType'))
                station_ls = best.get('distanceToArrival')
                ls = f"{int(station_ls):,}" if station_ls is not None else "-"
                updated = self._format_data_age(best.get('updatedAt', ''))

                pp_entry = pp_data.get(station_system, {})
                pp_power = pp_entry.get('controlling_power', '')
                pp_state = pp_entry.get('power_state', '')
                if pp_power == '~none~':
                    powerplay = pp_state or t('common.no_data')
                elif pp_power and pp_state:
                    powerplay = f"{pp_power} / {pp_state}"
                elif pp_power:
                    powerplay = pp_power
                elif pp_state:
                    powerplay = pp_state
                else:
                    powerplay = t('common.no_data')
            else:
                price = t('ring_finder.no_data')
                station = "-"
                station_type = "-"
                ls = "-"
                updated = "-"
                powerplay = "-"
            mineral_display = self._format_material_for_display(r['mineral']) if r['mineral'] else "-"
            row_id = tree.insert("", "end", values=(
                r['system'], f"{r['distance']:.1f}", mineral_display, price, station,
                station_type, ls, powerplay, updated))
            system_by_row[row_id] = r['system']
            if best and r['mineral']:
                source_by_row[row_id] = format_market_source(best)

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)
        dialog._results_tree = tree
        dialog._results_tree_frame = tree_frame

        def copy_system_for_row(row_id):
            system = system_by_row.get(row_id)
            if system:
                self.parent.clipboard_clear()
                self.parent.clipboard_append(system)
                self.parent.update_idletasks()
                self.status_var.set(f"Copied '{system}' to clipboard")

        def open_in_browser(url_template, system):
            import urllib.parse
            import webbrowser
            webbrowser.open(url_template.format(urllib.parse.quote(system)))

        row_menu = tk.Menu(dialog, tearoff=0,
                           bg=MENU_COLORS["bg"] if current_theme != "elite_orange" else "#1e1e1e",
                           fg=MENU_COLORS["fg"] if current_theme != "elite_orange" else "#ff8c00",
                           activebackground=MENU_COLORS["activebackground"] if current_theme != "elite_orange" else "#ff6600",
                           activeforeground=MENU_COLORS["activeforeground"] if current_theme != "elite_orange" else "#000000",
                           font=scaled_font(9))
        row_menu.add_command(label=t('context_menu.copy_system'),
                             command=lambda: copy_system_for_row(tree.selection()[0]) if tree.selection() else None)
        row_menu.add_command(label=t('context_menu.open_inara'),
                             command=lambda: open_in_browser("https://inara.cz/elite/starsystem/?search={}", system_by_row.get(tree.selection()[0], '')) if tree.selection() else None)
        row_menu.add_command(label=t('context_menu.open_edsm'),
                             command=lambda: open_in_browser("https://www.edsm.net/en/system/id/0/name/{}", system_by_row.get(tree.selection()[0], '')) if tree.selection() else None)
        row_menu.add_command(label=t('context_menu.open_spansh'),
                             command=lambda: open_in_browser("https://spansh.co.uk/search/{}", system_by_row.get(tree.selection()[0], '')) if tree.selection() else None)

        def open_inara_and_fetch_pp(row_id, system):
            """Open Inara and fetch/store its PowerPlay data - same as the main
            Hotspots Finder table's PowerPlay-cell click (_open_inara/_fetch_pp_from_inara)."""
            open_in_browser("https://inara.cz/elite/starsystem/?search={}", system)

            def worker():
                from system_finder_api import SystemFinderAPI
                result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system)
                self.parent.after(0, lambda: apply_pp_result(row_id, system, result))
            threading.Thread(target=worker, daemon=True).start()

        def apply_pp_result(row_id, system, result):
            if not result or not tree.exists(row_id):
                return
            pp_power = result.get('controlling_power', '')
            pp_state = result.get('power_state', '')
            if pp_power == '~none~':
                pp_str = pp_state or t('common.no_data')
            elif pp_power and pp_state:
                pp_str = f"{pp_power} / {pp_state}"
            elif pp_power:
                pp_str = pp_power
            elif pp_state:
                pp_str = pp_state
            else:
                pp_str = t('common.no_data')
            vals = list(tree.item(row_id, 'values'))
            if len(vals) > 7:
                vals[7] = pp_str
                tree.item(row_id, values=vals)

        def on_click(event):
            row_id = tree.identify_row(event.y)
            col = tree.identify_column(event.x)
            if not row_id:
                return
            if col == "#1":  # System column
                tree.selection_set(row_id)
                copy_system_for_row(row_id)
            elif col == "#8":  # PowerPlay column - open Inara and refresh PP data, same as main table
                tree.selection_set(row_id)
                system = system_by_row.get(row_id, '')
                if system:
                    open_inara_and_fetch_pp(row_id, system)

        def on_right_click(event):
            row_id = tree.identify_row(event.y)
            if row_id and system_by_row.get(row_id):
                tree.selection_set(row_id)
                dialog._row_menu_open = True
                try:
                    row_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    dialog._row_menu_open = False

        tree.bind("<Button-1>", on_click)
        tree.bind("<Button-3>", on_right_click)

        # Don't tie the floor to the table's full natural width (every column fixed-width,
        # no stretch) - that made the window unshrinkable. The horizontal scrollbar above
        # keeps the table usable below that width, so only guard against the input row.
        if had_previous_results:
            # Re-render (e.g. PowerPlay-mode toggle) - keep whatever size the user has
            # the window at now, don't snap back to natural/saved size.
            dialog.update_idletasks()
            dialog.minsize(500, dialog.winfo_reqheight())
            dialog.geometry(f"{current_width}x{current_height}")
        else:
            dialog.geometry("")  # Clear any fixed size from before results were added
            dialog.update_idletasks()
            min_h = dialog.winfo_reqheight()
            dialog.minsize(500, min_h)
            try:
                from config import load_reverse_search_window_geometry
                saved_geom = load_reverse_search_window_geometry()
                if saved_geom.get('width') and saved_geom.get('height'):
                    # Floor width at 1300 - older sessions saved a narrow size back when this
                    # branch's width could fall through to the input row's reqwidth. Height
                    # stays natural/saved (min_h) so the window still shrinks to fit few rows.
                    target_w = max(saved_geom['width'], 1300)
                    target_h = max(saved_geom['height'], min_h)
                    # Recenter on the main window - geometry("WxH") alone keeps the dialog's
                    # current top-left, so widening it here would grow off to the right
                    # instead of staying centered.
                    parent_top = self.parent.winfo_toplevel()
                    parent_top.update_idletasks()
                    x = parent_top.winfo_x() + (parent_top.winfo_width() - target_w) // 2
                    y = parent_top.winfo_y() + (parent_top.winfo_height() - target_h) // 2
                    dialog.geometry(f"{target_w}x{target_h}+{x}+{y}")
                else:
                    # geometry("") alone doesn't widen the window to the table's full
                    # column width (the tree's natural size doesn't propagate up through
                    # its expanding frame) - size explicitly so all columns are visible
                    # without the user having to drag the window wider first.
                    tree_width = sum(tree.column(col, "width") for col in columns) + 40
                    target_w = max(tree_width, dialog.winfo_reqwidth(), 1300)
                    # Don't use center_window here - it recomputes size from
                    # winfo_reqwidth/reqheight (the natural/content size), which would
                    # silently shrink the window right back down after we just widened it.
                    parent_top = self.parent.winfo_toplevel()
                    parent_top.update_idletasks()
                    x = parent_top.winfo_x() + (parent_top.winfo_width() - target_w) // 2
                    y = parent_top.winfo_y() + (parent_top.winfo_height() - min_h) // 2
                    dialog.geometry(f"{target_w}x{min_h}+{x}+{y}")
            except Exception:
                from ui.dialogs import center_window
                center_window(dialog, self.parent.winfo_toplevel())
