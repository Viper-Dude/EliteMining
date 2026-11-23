# -*- coding: utf-8 -*-
"""
Find Acquisition Systems for the Hotspots Finder: nearby Unoccupied systems buying the
minerals mined at a Fortified/Stronghold system. Mixed into RingFinder (ring_finder.py).
"""
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from core.constants import MENU_COLORS
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from ui.theme import modern_color

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key


class AcquisitionMixin:
    def _find_acquisition_targets_for_system(self):
        """Right-click "Find Acquisition Targets" - open the acquisition dialog pre-filled
        with the selected row's system and run the search immediately."""
        selection = self.results_tree.selection()
        if not selection:
            self.status_var.set(t('ring_finder.no_selection'))
            return

        values = self.results_tree.item(selection[0], 'values')
        if not values or len(values) < 3:
            return

        system_name = values[2]
        if system_name:
            self._show_acquisition_search_dialog(reference_system=system_name)

    # PowerPlay Acquisition-mining sell radius: mine in a Fortified (20 Ly) or
    # Stronghold (30 Ly) system, sell in a nearby Unoccupied system within that radius.
    ACQUISITION_RADIUS_BY_STATE = {'Fortified': 20.0, 'Stronghold': 30.0}

    def _show_acquisition_search_dialog(self, reference_system: str = None):
        """Show the "Find Acquisition Targets" dialog - pick a Fortified/Stronghold
        system and list nearby Unoccupied systems within the state's own 20/30 Ly
        acquisition-mining sell radius.

        reference_system: if given (e.g. from a result row's right-click menu), pre-fills
        the field with it - the user still has to click Search (or press Enter) to run it,
        so they can change the mineral picker first if the local-DB default isn't right."""
        from config import scaled_font, load_theme

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

        dialog.title(t('ring_finder.acquisition_search_title'))
        dialog.resizable(True, True)
        dialog.configure(bg=bg)

        frame = tk.Frame(dialog, bg=bg, padx=15, pady=15)
        frame.pack(fill="both", expand=True)
        dialog._content_frame = frame

        input_row = tk.Frame(frame, bg=bg)
        input_row.pack(fill="x", pady=(0, 10))

        tk.Label(input_row, text=t('ring_finder.acquisition_search_reference_label'),
                 bg=bg, fg=fg, font=scaled_font(9)).pack(side="left")
        prefill = reference_system.strip() if reference_system else (self.system_var.get().strip() if hasattr(self, 'system_var') else "")
        reference_var = tk.StringVar(value=prefill)
        reference_entry = ttk.Entry(input_row, textvariable=reference_var, width=24)
        reference_entry.pack(side="left", padx=(8, 15))

        from system_autocomplete import SystemAutocomplete
        SystemAutocomplete(reference_entry, reference_var, dialog)

        mineral_row = tk.Frame(frame, bg=bg)
        mineral_row.pack(fill="x", pady=(0, 10))

        tk.Label(mineral_row, text=t('ring_finder.mineral'),
                 bg=bg, fg=fg, font=scaled_font(9)).pack(side="left")
        available_materials = self._get_available_materials()
        # Always default to "All Minerals" - it checks every mineral known to be mined
        # at the reference system (per the local DB) and keeps whichever prices best per
        # candidate, which covers the single-mineral case too without the user having to
        # pick one manually every time the dialog opens.
        mineral_var = tk.StringVar(value=t('ring_finder.all_minerals'))
        mineral_combo = ttk.Combobox(mineral_row, textvariable=mineral_var, width=22, state="readonly")
        extra_minerals = {m for ring, mins in self.NON_HOTSPOT_RING_MINERALS.items() if ring != 'Icy' for m in mins}
        picker_minerals = sorted(set(available_materials[1:]) | extra_minerals)
        mineral_combo['values'] = (available_materials[0],) + tuple(picker_minerals)
        mineral_combo.pack(side="left", padx=(8, 0))
        mineral_combo.bind('<<ComboboxSelected>>', lambda e: e.widget.selection_clear(), add='+')

        status_label = tk.Label(frame, text=t('ring_finder.acquisition_search_hint'),
                                bg=bg, fg=fg, font=scaled_font(9), justify="left", wraplength=620)
        status_label.pack(anchor="w", pady=(0, 10), fill="x")

        # Rewrap to the dialog's current width instead of clipping - the hint text is
        # long enough to overflow the default width, and this dialog is resizable.
        def rewrap_status_label(event=None):
            status_label.config(wraplength=max(status_label.winfo_width(), 200))
        status_label.bind("<Configure>", rewrap_status_label)

        def run_search():
            if dialog._search_control.running:
                dialog._search_control.stop()
                return
            reference_system = reference_var.get().strip()
            if not reference_system:
                status_label.config(text=t('ring_finder.acquisition_search_no_reference'))
                return
            mineral_display = mineral_var.get()
            if mineral_display == t('ring_finder.all_minerals'):
                mineral_filter = None
            else:
                mineral_filter = self._to_english(mineral_display)
                if mineral_filter == "Low Temp Diamonds":
                    mineral_filter = "Low Temperature Diamonds"
            status_label.config(text=t('ring_finder.acquisition_search_checking').format(system=reference_system))
            dialog._search_control.start()
            threading.Thread(target=dialog._search_control.run,
                             args=(self._acquisition_search_worker, reference_system, mineral_filter, dialog, status_label, search_btn, dialog._search_control),
                             daemon=True).start()

        search_btn = ttk.Button(input_row, text=t('ring_finder.reverse_search_search_btn'), command=run_search)
        search_btn.pack(side="left")
        dialog._search_control = SearchControl(self.parent, search_btn, status_label)

        reference_entry.bind('<Return>', lambda e: run_search())

        def close_acquisition_dialog():
            try:
                from config import save_acquisition_search_window_width
                save_acquisition_search_window_width(dialog.winfo_width())
            except Exception:
                pass
            dialog._search_control.stop()
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW", close_acquisition_dialog)

        dialog.update_idletasks()
        from config import load_acquisition_search_window_width
        default_width = dialog.winfo_reqwidth() * 2
        target_width = max(load_acquisition_search_window_width() or default_width, dialog.winfo_reqwidth())
        from ui.dialogs import center_window
        center_window(dialog, self.parent.winfo_toplevel())
        # center_window resets the size to the content's natural width, so apply the
        # wanted width afterwards and keep the window centered on the same spot.
        dialog.update_idletasks()
        main = self.parent.winfo_toplevel()
        height = dialog.winfo_reqheight()
        x = main.winfo_x() + (main.winfo_width() - target_width) // 2
        y = main.winfo_y() + (main.winfo_height() - height) // 2
        dialog.geometry(f"{target_width}x{height}+{x}+{y}")
        dialog.deiconify()
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except Exception:
            pass

        dialog._row_menu_open = False

    def _acquisition_search_worker(self, reference_system: str, mineral_filter: Optional[str], dialog, status_label, search_btn, control):
        """Background worker: determine reference_system's own PowerPlay state
        (cache-first, Spansh fallback), pick the matching 20/30 Ly acquisition radius,
        then list nearby Unoccupied systems within it - each with the selected mineral's
        best sell price there, if any (that's the actual point of an acquisition
        target: somewhere to sell what was mined at reference_system)."""
        from system_finder_api import SystemFinderAPI

        pp_cache = SystemFinderAPI._batch_get_powerplay([reference_system])
        entry = pp_cache.get(reference_system, {})
        power_state = entry.get('power_state', '')

        if power_state not in self.ACQUISITION_RADIUS_BY_STATE:
            # Cache had no usable state - ask Spansh directly for this one system before
            # giving up, same enrichment call _apply_powerplay_filter already relies on.
            for state in ('Fortified', 'Stronghold'):
                spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_systems(
                    reference_system, 5.0, 'Any', state, is_cancelled=control.is_cancelled)
                if reference_system in spansh_pp:
                    power_state = state
                    SystemFinderAPI._store_powerplay_batch({reference_system: spansh_pp[reference_system]})
                    break

        radius = self.ACQUISITION_RADIUS_BY_STATE.get(power_state)
        if radius is None:
            control.complete([], lambda rows: self._acquisition_search_not_eligible(reference_system, power_state, dialog, status_label, search_btn))
            return

        nearby = SystemFinderAPI._fetch_spansh_powerplay_systems(reference_system, radius, 'Any', 'Unoccupied', is_cancelled=control.is_cancelled)
        SystemFinderAPI._store_powerplay_batch(nearby)

        all_candidates = sorted(nearby.items(), key=lambda kv: kv[1].get('distance', 999999))

        # mineral_filter=None ("All Minerals") means: check every mineral known to be
        # mined at reference_system, and keep whichever prices best per candidate -
        # a Fortified/Stronghold system often mines more than one commodity.
        minerals_to_check = [mineral_filter] if mineral_filter else self._acquisition_reference_materials(reference_system)

        # Only candidates with an actual buy order for one of minerals_to_check are useful
        # here - ring/hotspot data at the Unoccupied system is irrelevant (you mine at
        # reference_system, you only sell at the Unoccupied one), so there's no reason to
        # list systems that can't even buy what you're selling.
        sell_prices = {}
        best_mineral = {}
        best_rows = {}
        if all_candidates and minerals_to_check:
            # One live buyer-search per mineral, centered on reference_system, covers every
            # candidate in the same radius (same pattern as _reverse_search_worker) - cheap
            # regardless of how many Unoccupied systems came back.
            from marketplace_api import MarketplaceAPI
            from concurrent.futures import ThreadPoolExecutor
            candidate_names = {sys_name for sys_name, _ in all_candidates}

            def fetch(mineral):
                if control.is_cancelled():
                    return mineral, []
                try:
                    return mineral, MarketplaceAPI.search_buyers(mineral, reference_system, int(radius), 7, False, is_cancelled=control.is_cancelled)
                except Exception:
                    return mineral, []

            with ThreadPoolExecutor(max_workers=min(len(minerals_to_check), 4)) as pool:
                for mineral, rows in pool.map(fetch, minerals_to_check):
                    for row in rows:
                        sys_name = row.get('systemName', '')
                        if sys_name not in candidate_names:
                            continue
                        price = row.get('sellPrice', 0)
                        if price and price > sell_prices.get(sys_name, 0):
                            sell_prices[sys_name] = price
                            best_mineral[sys_name] = mineral
                            best_rows[sys_name] = row

        results = [(sys_name, sys_entry) for sys_name, sys_entry in all_candidates if sys_name in sell_prices]

        control.complete(results, lambda rows: self._show_acquisition_search_results(
            reference_system, power_state, radius, rows, mineral_filter, sell_prices, best_mineral, dialog, status_label, search_btn, best_rows))

    def _acquisition_search_not_eligible(self, reference_system: str, power_state: str, dialog, status_label, search_btn):
        search_btn.config(state="normal")
        if power_state:
            status_label.config(text=t('ring_finder.acquisition_search_wrong_state').format(system=reference_system, state=power_state))
        else:
            status_label.config(text=t('ring_finder.acquisition_search_no_data').format(system=reference_system))

    def _show_acquisition_search_results(self, reference_system: str, power_state: str, radius: float,
                                         results: list, mineral_filter: Optional[str], sell_prices: dict,
                                         best_mineral: dict, dialog, status_label, search_btn, best_rows: dict = None):
        """Populate the acquisition search dialog with nearby Unoccupied systems."""
        best_rows = best_rows or {}
        from config import scaled_font, load_theme

        search_btn.config(state="normal")

        mineral_display = self._format_material_for_display(mineral_filter) if mineral_filter else t('ring_finder.all_minerals')
        if not results:
            status_label.config(text=t('ring_finder.acquisition_search_no_candidates').format(
                system=reference_system, state=power_state, radius=int(radius), mineral=mineral_display))
        else:
            status_label.config(text=t('ring_finder.acquisition_search_complete').format(
                count=len(results), system=reference_system, state=power_state, radius=int(radius), mineral=mineral_display))

        old_tree_frame = getattr(dialog, '_acq_results_tree_frame', None)
        if old_tree_frame is not None:
            try:
                old_tree_frame.destroy()
            except Exception:
                pass

        if not results:
            return

        current_theme = load_theme()
        if current_theme == "elite_orange":
            bg, tree_bg, tree_fg, header_bg = "#1e1e1e", "#1e1e1e", "#ff8c00", "#1a1a1a"
            selection_bg, selection_fg = "#ff6600", "#000000"
        elif current_theme in ("modern", "modern_slate", "modern_orange"):
            bg, tree_bg, tree_fg, header_bg = MENU_COLORS["bg"], modern_color("#1D2228"), modern_color("#E6EAF0"), modern_color("#14171B")
            selection_bg, selection_fg = modern_color("#4A3520"), "#FFFFFF"
        else:
            bg, tree_bg, tree_fg, header_bg = MENU_COLORS["bg"], "#1e1e1e", "#e6e6e6", "#2a2a2a"
            selection_bg, selection_fg = "#0078d7", "#ffffff"

        frame = dialog._content_frame

        style = ttk.Style()
        style.configure("AcquisitionSearch.Treeview",
                       borderwidth=1, relief="solid", bordercolor="#333333",
                       background=tree_bg, foreground=tree_fg, fieldbackground=tree_bg,
                       font=scaled_font(9))
        style.configure("AcquisitionSearch.Treeview.Heading",
                       borderwidth=1, relief="groove", background=header_bg, foreground=tree_fg,
                       padding=[5, 5], anchor="w", font=scaled_font(9, "bold"))
        style.map("AcquisitionSearch.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])

        tree_frame = tk.Frame(frame, bg=bg)
        tree_frame.pack(fill="both", expand=True, pady=(0, 10))

        columns_header = ttk.Frame(tree_frame)
        columns_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self._cv_add_columns_button(columns_header, 'acquisition_search')

        show_mineral_col = mineral_filter is None
        columns = ("System", "Station", "Type", "Pad", "Dist", "Power", "Mineral", "Demand", "Price", "Updated")
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", height=min(len(results), 15),
                            selectmode="browse", style="AcquisitionSearch.Treeview")
        price_header = (t('ring_finder.acquisition_search_col_price').format(mineral=t('ring_finder.all_minerals'))
                        if show_mineral_col else
                        t('ring_finder.acquisition_search_col_price').format(mineral=self._format_material_for_display(mineral_filter)))
        column_labels = {
            "System": t('ring_finder.acquisition_search_col_system'),
            "Station": t('ring_finder.col_station'),
            "Type": t('ring_finder.col_station_type'),
            "Pad": t('ring_finder.col_pad'),
            "Dist": t('ring_finder.col_dist'),
            "Power": t('ring_finder.acquisition_search_col_power'),
            "Mineral": t('ring_finder.col_best_mineral'),
            "Demand": t('ring_finder.col_demand'),
            "Price": price_header,
            "Updated": t('ring_finder.col_updated'),
        }
        for col in columns:
            tree.heading(col, text=column_labels[col], anchor="w")
        default_widths = {"System": 200, "Station": 200, "Type": 120, "Pad": 50, "Dist": 80, "Power": 150,
                          "Mineral": 110, "Demand": 90, "Price": 120, "Updated": 80}
        tree.column("System", width=default_widths["System"], minwidth=40, anchor="w", stretch=False)
        tree.column("Station", width=default_widths["Station"], minwidth=40, anchor="w", stretch=False)
        tree.column("Type", width=default_widths["Type"], minwidth=40, anchor="w", stretch=False)
        tree.column("Pad", width=default_widths["Pad"], minwidth=40, anchor="w", stretch=False)
        tree.column("Dist", width=default_widths["Dist"], minwidth=40, anchor="w", stretch=False)
        tree.column("Power", width=default_widths["Power"], minwidth=40, anchor="w", stretch=False)
        tree.column("Mineral", width=default_widths["Mineral"], minwidth=40, anchor="w", stretch=False)
        tree.column("Demand", width=default_widths["Demand"], minwidth=40, anchor="w", stretch=False)
        tree.column("Price", width=default_widths["Price"], minwidth=40, anchor="w", stretch=False)
        tree.column("Updated", width=default_widths["Updated"], minwidth=40, anchor="w", stretch=False)

        def fit_dialog_width_to_columns():
            shown = tree['displaycolumns']
            shown = columns if shown in ('#all', ('#all',)) else shown
            table_width = sum(tree.column(c, 'width') for c in shown) + v_scrollbar.winfo_reqwidth() + 6
            dialog.update_idletasks()
            width = max(table_width + 30, 500)
            dialog.geometry(f"{width}x{dialog.winfo_height()}")

        self.setup_column_visibility(tree=tree, columns=columns, default_widths=default_widths,
                                     config_key='acquisition_search', use_displaycolumns=True,
                                     on_change=fit_dialog_width_to_columns, allow_reorder=True)
        # Best Mineral only means something when "All Minerals" was searched
        self._cv_set_force_hidden('acquisition_search', 'Mineral', not show_mineral_col)

        system_by_row = {}
        station_by_row = {}
        source_by_row = {}
        from app_utils import format_market_source
        from ui.cell_tooltip import attach_cell_tooltip
        attach_cell_tooltip(tree, "Updated", lambda item: source_by_row.get(item, ''))
        for sys_name, sys_entry in results:
            power = sys_entry.get('controlling_power', '') or t('ring_finder.pp_unoccupied')
            if power == '~none~':
                power = t('ring_finder.pp_unoccupied')
            distance = sys_entry.get('distance', 0)
            price = sell_prices.get(sys_name, 0)
            buyer_row = best_rows.get(sys_name, {})
            station = buyer_row.get('stationName', '') or '-'
            demand = buyer_row.get('demand')
            mineral_display_row = self._format_material_for_display(best_mineral.get(sys_name, ''))
            row_id = tree.insert("", "end", values=(
                sys_name, station, self._format_station_type(buyer_row.get('stationType')),
                self._format_pad_size(buyer_row.get('maxLandingPadSize')), f"{distance:.1f}", power,
                mineral_display_row, f"{demand:,}" if isinstance(demand, (int, float)) else '-',
                f"{price:,} CR", self._format_data_age(buyer_row.get('updatedAt', ''))))
            system_by_row[row_id] = sys_name
            station_by_row[row_id] = station
            source_by_row[row_id] = format_market_source(buyer_row)

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=v_scrollbar.set)
        tree.grid(row=1, column=0, sticky="nsew")
        v_scrollbar.grid(row=1, column=1, sticky="ns")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(1, weight=1)
        dialog._acq_results_tree = tree
        dialog._acq_results_tree_frame = tree_frame

        def copy_system_for_row(row_id):
            system = system_by_row.get(row_id)
            if system:
                self.parent.clipboard_clear()
                self.parent.clipboard_append(system)
                self.parent.update_idletasks()

        def on_click(event):
            row_id = tree.identify_row(event.y)
            if row_id:
                tree.selection_set(row_id)
                copy_system_for_row(row_id)
        tree.bind("<Button-1>", on_click)

        def open_url(url_template, value):
            import urllib.parse
            import webbrowser
            webbrowser.open(url_template.format(urllib.parse.quote_plus(value.strip())))

        def selected_row_value(mapping):
            selection = tree.selection()
            return mapping.get(selection[0], '') if selection else ''

        row_menu = tk.Menu(dialog, tearoff=0,
                           bg=MENU_COLORS["bg"] if current_theme != "elite_orange" else "#1e1e1e",
                           fg=MENU_COLORS["fg"] if current_theme != "elite_orange" else "#ff8c00",
                           activebackground=MENU_COLORS["activebackground"] if current_theme != "elite_orange" else "#ff6600",
                           activeforeground=MENU_COLORS["activeforeground"] if current_theme != "elite_orange" else "#000000",
                           font=scaled_font(9))
        row_menu.add_command(label=t('context_menu.open_inara'),
                             command=lambda: open_url("https://inara.cz/elite/stations/?search={}", selected_row_value(station_by_row)))
        row_menu.add_command(label=t('context_menu.open_edsm'),
                             command=lambda: open_url("https://www.edsm.net/en/search/stations/index/name/{}/", selected_row_value(station_by_row)))
        row_menu.add_command(label=t('context_menu.open_spansh'),
                             command=lambda: open_url("https://spansh.co.uk/search/{}", selected_row_value(system_by_row)))
        row_menu.add_separator()
        row_menu.add_command(label=t('context_menu.copy_system'),
                             command=lambda: copy_system_for_row(tree.selection()[0]) if tree.selection() else None)

        def on_right_click(event):
            row_id = tree.identify_row(event.y)
            if row_id and system_by_row.get(row_id):
                tree.selection_set(row_id)
                dialog._row_menu_open = True
                try:
                    row_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    dialog._row_menu_open = False
                    row_menu.grab_release()

        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['acquisition_search'] = on_right_click

        dialog.update_idletasks()
        dialog.minsize(500, dialog.winfo_reqheight())
        dialog.geometry(f"{dialog.winfo_width()}x{dialog.winfo_reqheight()}")

    def _acquisition_reference_materials(self, system_name: str) -> list:
        """English material names known to be minable at system_name, from the local
        database - used to default the acquisition dialog's mineral picker to
        whatever the user is actually mining there instead of "All Minerals"."""
        try:
            rows = self.user_db.get_system_hotspots(system_name)
        except Exception:
            rows = []
        return list({row.get('material_name', '') for row in rows if row.get('material_name')})
