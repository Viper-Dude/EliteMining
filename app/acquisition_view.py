# -*- coding: utf-8 -*-
"""
Acquisition view of the Hotspots Finder: nearby Unoccupied systems buying the minerals
mined at a Fortified/Stronghold system. Mixed into RingFinder (ring_finder.py).
"""
import re
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from column_visibility_helper import displayed_column
from core.constants import MENU_COLORS
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key


class _OverlayStatus:
    """SearchControl writes Stopping/stopped/failed messages here; the view shows them
    in its table overlay instead of a status label."""

    def __init__(self, view):
        self._view = view

    def winfo_exists(self):
        return True

    def config(self, text=''):
        self._view._acq_set_status(text)


def set_outdated_tag(tree, row_id, outdated: bool):
    """Mark or clear a row whose PowerPlay state changed after the search."""
    tags = [tag for tag in tree.item(row_id, 'tags') if tag != 'pp_outdated']
    if outdated:
        tags.append('pp_outdated')
    tree.item(row_id, tags=tags)


def configure_outdated_tag(tree, theme: str):
    from ui.theme import get_theme_colors
    tree.tag_configure('pp_outdated', foreground=get_theme_colors(theme)['warning'])


def outdated_note(outdated: set, systems) -> str:
    """Heading note while shown rows use a system whose PowerPlay state changed."""
    count = len(outdated & set(systems))
    return ' · ' + t('ring_finder.pp_changed_search_again').format(count=count) if count else ''


class AcquisitionMixin:
    # PowerPlay Acquisition-mining sell radius: mine in a Fortified (20 Ly) or
    # Stronghold (30 Ly) system, sell in a nearby Unoccupied system within that radius.
    ACQUISITION_RADIUS_BY_STATE = {'Fortified': 20.0, 'Stronghold': 30.0}
    # PowerPlay states with no acquisition range
    ACQ_OTHER_STATES = ('Unoccupied', 'Exploited', 'Expansion', 'Contested')

    ACQ_COLUMNS = ("System", "Station", "Type", "Pad", "Dist", "Power", "Mineral", "Demand", "Price", "Updated")
    ACQ_DEFAULT_WIDTHS = {"System": 200, "Station": 200, "Type": 120, "Pad": 50, "Dist": 80, "Power": 150,
                          "Mineral": 110, "Demand": 90, "Price": 120, "Updated": 80}

    # ---------------------------------------------------------------------------------
    # Acquisition view: third view of the Hotspots Finder results area
    # ---------------------------------------------------------------------------------

    def _build_acquisition_view(self, parent, bg: str, tree_bg: str, tree_fg: str):
        """Build the Acquisition view (hidden) inside the results area. Filled by the
        right-click "Find Acquisition Systems" action and by clicking Acquisition."""
        import tkinter.font as tkfont
        from config import scaled_font, scaled_px, load_theme
        from ui.cell_tooltip import attach_cell_tooltip

        current_theme = load_theme()

        self._acq = {
            'system': '', 'state': '', 'radius': None, 'mineral': None, 'busy': False, 'count': 0, 'owner': '',
            'status': '', 'hint': '', 'spin': 0, 'spinning': False,
            'system_by_row': {}, 'station_by_row': {}, 'source_by_row': {}, 'outdated': set(),
        }

        frame = ttk.Frame(parent)
        self._acq_frame = frame

        # One control row; right-hand controls are packed first so a narrow window clips
        # the system name on the left, never the controls.
        top_row = tk.Frame(frame, bg=bg)
        top_row.pack(fill="x", padx=5, pady=(5, 4))
        self._acq_columns_btn = self._cv_add_columns_button(top_row, 'acquisition_search')

        btn_style = self._view_button_style()
        self._acq_refresh_btn = self._rf_button(top_row, text=t('ring_finder.rank_refresh'), **btn_style,
                                                command=self._acq_on_refresh)
        self._acq_refresh_btn.pack(side="right")
        self._acq_refresh_btn.configure(state="disabled")

        self._acq_all_label = t('ring_finder.all_minerals')
        available = self._get_available_materials()
        extra = {self._format_material_for_display(m)
                 for ring, mins in self.NON_HOTSPOT_RING_MINERALS.items() if ring != 'Icy' for m in mins}
        self._acq_mineral_var = tk.StringVar(value=self._acq_all_label)
        self._acq_mineral_combo = ttk.Combobox(top_row, textvariable=self._acq_mineral_var, width=20, state="readonly",
                                               values=(self._acq_all_label,) + tuple(sorted(set(available[1:]) | extra)))
        self._acq_mineral_combo.pack(side="right", padx=(0, 8))
        self._acq_mineral_combo.bind('<<ComboboxSelected>>', self._acq_on_mineral_selected, add='+')

        self._acq_name_label = ttk.Label(top_row, text="", font=scaled_font(9, "bold"))
        self._acq_name_label.pack(side="left")

        tree_frame = ttk.Frame(frame, relief="solid", borderwidth=1)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=(0, 2))

        columns = self.ACQ_COLUMNS
        tree = StripedTreeview(tree_frame, columns=columns, show="headings", selectmode="browse",
                               style="RingFinder.Treeview")
        self._acq_tree = tree
        configure_outdated_tag(tree, current_theme)
        column_labels = {
            "System": t('ring_finder.acquisition_search_col_system'),
            "Station": t('ring_finder.col_station'),
            "Type": t('ring_finder.col_station_type'),
            "Pad": t('ring_finder.col_pad'),
            "Dist": t('ring_finder.col_dist'),
            "Power": t('ring_finder.acquisition_search_col_power'),
            "Mineral": t('ring_finder.col_best_mineral'),
            "Demand": t('ring_finder.col_demand'),
            "Price": self._acq_price_header(None),
            "Updated": t('ring_finder.col_updated'),
        }
        self._acq_heading_font = tkfont.Font(font=scaled_font(9, "bold"))
        self._acq_header_pad = scaled_px(24)
        default_widths = {}
        for col in columns:
            tree.heading(col, text=column_labels[col], anchor="w")
            min_w = self._acq_min_width(col)
            default_widths[col] = max(scaled_px(self.ACQ_DEFAULT_WIDTHS[col]), min_w)
            tree.column(col, width=default_widths[col], minwidth=min_w, anchor="w", stretch=False)

        try:
            from config import load_acquisition_search_column_widths
            for col_name, width in load_acquisition_search_column_widths().items():
                if col_name in columns and width > 0:
                    tree.column(col_name, width=max(width, tree.column(col_name, "minwidth")))
        except Exception:
            pass

        def save_widths(event=None):
            try:
                from config import save_acquisition_search_column_widths
                save_acquisition_search_column_widths({col: tree.column(col, "width") for col in columns})
            except Exception:
                pass
        tree.bind("<ButtonRelease-1>", save_widths, add='+')

        self.setup_column_visibility(tree=tree, columns=columns, default_widths=default_widths,
                                     config_key='acquisition_search', use_displaycolumns=True, allow_reorder=True)
        attach_cell_tooltip(tree, "Updated", lambda item: self._acq['source_by_row'].get(item, ''))

        v_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        # Covers the table while searching (spinner) and holds the hint/not-eligible text
        self._acq_overlay = tk.Frame(tree_frame, bg=tree_bg)
        self._acq_overlay_label = tk.Label(self._acq_overlay, text="", bg=tree_bg, fg=tree_fg,
                                           justify="center", wraplength=scaled_px(600))
        self._acq_overlay_label.place(relx=0.5, rely=0.5, anchor="center")
        self._acq_overlay.grid(row=0, column=0, sticky="nsew")
        self._acq_overlay_fonts = (scaled_font(14, "bold"), scaled_font(10))

        menu_colors = dict(bg=MENU_COLORS["bg"], fg=MENU_COLORS["fg"],
                           activebackground=MENU_COLORS["activebackground"],
                           activeforeground=MENU_COLORS["activeforeground"])
        if current_theme == "elite_orange":
            menu_colors = dict(bg="#1e1e1e", fg="#ff8c00", activebackground="#ff6600", activeforeground="#000000")
        self._acq_row_menu = tk.Menu(frame, tearoff=0, font=scaled_font(9), **menu_colors)

        def selected(mapping):
            sel = tree.selection()
            return mapping.get(sel[0], '') if sel else ''

        self._acq_row_menu.add_command(label=t('context_menu.copy_system'),
                                       command=lambda: self._acq_copy_system(tree.selection()[0]) if tree.selection() else None)
        self._acq_row_menu.add_command(label=t('context_menu.open_inara'), command=lambda: self._bp_open_url(
            "https://inara.cz/elite/stations/?search={}", selected(self._acq['station_by_row'])))
        self._acq_row_menu.add_command(label=t('context_menu.open_edsm'), command=lambda: self._bp_open_url(
            "https://www.edsm.net/en/search/stations/index/name/{}/", selected(self._acq['station_by_row'])))
        self._acq_row_menu.add_command(label=t('context_menu.open_spansh'), command=lambda: self._bp_open_url(
            "https://spansh.co.uk/search/{}", selected(self._acq['system_by_row'])))

        tree.bind("<Button-1>", self._acq_on_click)
        tree.bind("<Double-1>", self._acq_on_double_click)
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['acquisition_search'] = self._acq_on_right_click

        self._acq_control = SearchControl(self.parent, self._acq_refresh_btn, _OverlayStatus(self),
                                          on_finish=self._acq_on_finish)
        self._acq_refresh_controls()

    def _acq_min_width(self, col) -> int:
        from config import scaled_px
        text = self._acq_tree.heading(col, "text")
        return max(self._acq_heading_font.measure(text) + self._acq_header_pad, scaled_px(50))

    def _acq_price_header(self, mineral_filter: Optional[str]) -> str:
        mineral = self._format_material_for_display(mineral_filter) if mineral_filter else t('ring_finder.all_minerals')
        return t('ring_finder.acquisition_search_col_price').format(mineral=mineral)

    # --- state and overlay ---------------------------------------------------------

    def _acq_name_text(self) -> str:
        acq = self._acq
        if acq['system'] and acq['state'] and acq['radius'] and not acq['busy']:
            name = t('ring_finder.acquisition_view_name').format(
                system=acq['system'], state=acq['state'], radius=int(acq['radius']))
            if acq.get('count'):
                name += ' · ' + t('ring_finder.acquisition_search_found').format(count=acq['count'])
            if self._acq_other_power():
                name += ' · ' + t('ring_finder.acquisition_not_my_power').format(power=acq['owner'])
            return name + outdated_note(acq.get('outdated', set()), acq['system_by_row'].values())
        return acq['system']

    def _acq_other_power(self) -> bool:
        """True when the searched system is controlled by a power other than My Power."""
        from config import load_player_power
        from system_finder_api import ELITE_POWERS
        owner = self._acq.get('owner', '')
        my_power = load_player_power()
        return bool(owner) and owner != '~none~' and my_power in ELITE_POWERS[1:] and owner != my_power

    @classmethod
    def _acq_row_eligible(cls, pp_text: str) -> bool:
        """False when a hotspot row's PowerPlay cell shows a state with no acquisition
        range; unknown states stay allowed (the search looks them up)."""
        words = re.findall(r'[A-Za-z]+', pp_text or '')
        return not any(state in words for state in cls.ACQ_OTHER_STATES)

    def _acq_refresh_controls(self):
        acq = self._acq
        self._acq_name_label.config(text=self._acq_name_text())
        if not acq['busy']:
            self._acq_refresh_btn.configure(state="normal" if acq['system'] else "disabled")
        self._acq_update_overlay()

    def _acq_update_overlay(self):
        acq = self._acq
        if acq['busy']:
            chars = self._search_overlay_chars
            text = f"{acq['status']}\n\n{chars[acq['spin'] % len(chars)]}"
            font = self._acq_overlay_fonts[0]
        elif not self._acq_tree.get_children():
            text, font = acq['hint'] or t('ring_finder.acquisition_view_empty'), self._acq_overlay_fonts[1]
        else:
            self._acq_overlay.grid_remove()
            return
        self._acq_overlay_label.configure(text=text, font=font)
        self._acq_overlay.grid()
        self._acq_overlay.tkraise()

    def _acq_spin(self):
        acq = self._acq
        if not acq['busy']:
            acq['spinning'] = False
            return
        acq['spin'] += 1
        self._acq_update_overlay()
        self.parent.after(100, self._acq_spin)

    def _acq_set_status(self, text: str):
        acq = self._acq
        acq['status'] = text
        acq['hint'] = text
        self._acq_update_overlay()

    def _acq_on_finish(self):
        self._acq['busy'] = False
        self._acq_refresh_controls()

    # --- running a search ----------------------------------------------------------

    def _acq_mineral_filter(self) -> Optional[str]:
        display = self._acq_mineral_var.get()
        if display == self._acq_all_label:
            return None
        mineral = self._to_english(display)
        return "Low Temperature Diamonds" if mineral == "Low Temp Diamonds" else mineral

    def _acq_start(self, system_name: str, mineral_display: str = None):
        """Search system_name and switch to the Acquisition view. A new system starts on
        All Minerals unless mineral_display (a mineral picker label) is given; Refresh and
        the mineral picker keep the chosen mineral."""
        acq = self._acq
        if mineral_display and mineral_display in self._acq_mineral_combo.cget('values'):
            self._acq_mineral_var.set(mineral_display)
        elif system_name.lower() != acq['system'].lower():
            self._acq_mineral_var.set(self._acq_all_label)
        mineral_filter = self._acq_mineral_filter()
        acq.update(system=system_name, state='', radius=None, mineral=mineral_filter, busy=True, hint='', count=0, owner='',
                   status=t('ring_finder.acquisition_search_checking').format(system=system_name))
        self._acq_fill([], mineral_filter, {}, {}, {})
        self._show_results_view('acquisition')
        control = self._acq_control
        control.start()
        self._acq_refresh_controls()
        if not acq['spinning']:
            acq['spinning'] = True
            acq['spin'] = 0
            self._acq_spin()
        threading.Thread(target=control.run,
                         args=(self._acquisition_search_worker, system_name, mineral_filter, control),
                         daemon=True).start()

    def _find_acquisition_targets_for_system(self):
        """Right-click "Find Acquisition Systems": search the selected row's system."""
        selection = self.results_tree.selection()
        if not selection:
            self.status_var.set(t('ring_finder.no_selection'))
            return

        values = self.results_tree.item(selection[0], 'values')
        if not values or len(values) < 3:
            return

        system_name = values[2]
        if system_name:
            self._acq_start(system_name)

    def _acq_on_view_click(self):
        """A click on Acquisition searches the selected hotspot row's system, or the
        Reference System with no row selected, unless that system is already shown."""
        if self._acq_control.running:
            return
        selection = self.results_tree.selection()
        if selection:
            values = self.results_tree.item(selection[0], 'values')
            system = values[2] if values and len(values) > 2 else ''
        else:
            reference = self.system_var.get().strip()
            system = self._saved_system_spelling(reference) if reference else ''
        if system and system.lower() != self._acq['system'].lower():
            self._acq_start(system)

    def _acq_on_refresh(self):
        if self._acq_control.running:
            self._acq_control.stop()
        elif self._acq['system']:
            self._acq_start(self._acq['system'])

    def _acq_on_mineral_selected(self, event=None):
        self._acq_mineral_combo.selection_clear()
        if self._acq['system']:
            self._acq_start(self._acq['system'])

    def _acquisition_search_worker(self, reference_system: str, mineral_filter: Optional[str], control):
        """Background worker: determine reference_system's own PowerPlay state
        (cache-first, Spansh fallback), pick the matching 20/30 Ly acquisition radius,
        then list nearby Unoccupied systems within it - each with the selected mineral's
        best sell price there, if any (that's the actual point of an acquisition
        target: somewhere to sell what was mined at reference_system)."""
        from system_finder_api import SystemFinderAPI

        pp_cache = SystemFinderAPI._batch_get_powerplay([reference_system])
        entry = pp_cache.get(reference_system, {})
        power_state = entry.get('power_state', '')
        owner = entry.get('controlling_power', '')

        if power_state not in self.ACQUISITION_RADIUS_BY_STATE:
            # Cache had no usable state - ask Spansh directly for this one system before
            # giving up, same enrichment call _apply_powerplay_filter already relies on.
            for state in ('Fortified', 'Stronghold'):
                spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_systems(
                    reference_system, 5.0, 'Any', state, is_cancelled=control.is_cancelled)
                if reference_system in spansh_pp:
                    # A newer saved state (e.g. Unoccupied from an Inara check) wins over Spansh's
                    found = SystemFinderAPI._prefer_newer_powerplay(
                        {reference_system: spansh_pp[reference_system]})[reference_system]
                    if found.get('power_state') == state:
                        power_state = state
                        owner = found.get('controlling_power', '')
                    break

        radius = self.ACQUISITION_RADIUS_BY_STATE.get(power_state)
        if radius is None:
            control.complete([], lambda rows: self._acquisition_search_not_eligible(reference_system, power_state))
            return

        # mineral_filter=None ("All Minerals") means: check every mineral known to be
        # mined at reference_system, and keep whichever prices best per candidate -
        # a Fortified/Stronghold system often mines more than one commodity.
        minerals_to_check = [mineral_filter] if mineral_filter else self._acquisition_reference_materials(reference_system)
        results, sell_prices, best_mineral, best_rows = self._acq_find_sell_targets(
            reference_system, radius, minerals_to_check, control.is_cancelled)

        control.complete(results, lambda rows: self._show_acquisition_search_results(
            reference_system, power_state, radius, rows, mineral_filter, sell_prices, best_mineral, best_rows, owner))

    @staticmethod
    def _acq_drop_no_longer_unoccupied(nearby: dict) -> dict:
        """Spansh's Unoccupied systems, minus those a newer saved state (e.g. from an Inara
        check) shows are no longer Unoccupied."""
        from system_finder_api import SystemFinderAPI
        fresh = SystemFinderAPI._prefer_newer_powerplay(nearby)
        return {name: entry for name, entry in fresh.items()
                if entry.get('power_state') in ('Unoccupied', nearby[name].get('power_state'))}

    def _acq_find_sell_targets(self, mine_system: str, radius: float, minerals: list, is_cancelled,
                               nearby: dict = None):
        """Unoccupied systems within radius of mine_system that buy one of minerals:
        (results [(system, pp entry)] nearest first, sell_prices, best_mineral, best_rows),
        the last three keyed by system name. Runs on a worker thread. nearby: the
        Unoccupied systems around mine_system if already fetched."""
        from system_finder_api import SystemFinderAPI

        if nearby is None:
            nearby = SystemFinderAPI._fetch_spansh_powerplay_systems(mine_system, radius, 'Any', 'Unoccupied', is_cancelled=is_cancelled)
            nearby = self._acq_drop_no_longer_unoccupied(nearby)

        all_candidates = sorted(nearby.items(), key=lambda kv: kv[1].get('distance', 999999))

        # Only candidates with an actual buy order for one of minerals are useful here -
        # ring/hotspot data at the Unoccupied system is irrelevant (you mine at
        # mine_system, you only sell at the Unoccupied one), so there's no reason to
        # list systems that can't even buy what you're selling.
        sell_prices = {}
        best_mineral = {}
        best_rows = {}
        if all_candidates and minerals:
            # One live buyer-search per mineral, centered on mine_system, covers every
            # candidate in the same radius (same pattern as _reverse_search_worker) - cheap
            # regardless of how many Unoccupied systems came back.
            from marketplace_api import MarketplaceAPI
            from concurrent.futures import ThreadPoolExecutor
            candidate_names = {sys_name for sys_name, _ in all_candidates}

            def fetch(mineral):
                if is_cancelled():
                    return mineral, []
                try:
                    return mineral, MarketplaceAPI.search_buyers(mineral, mine_system, int(radius), 7, False, is_cancelled=is_cancelled)
                except Exception:
                    return mineral, []

            with ThreadPoolExecutor(max_workers=min(len(minerals), 4)) as pool:
                for mineral, rows in pool.map(fetch, minerals):
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
        return results, sell_prices, best_mineral, best_rows

    def _acquisition_search_not_eligible(self, reference_system: str, power_state: str):
        if power_state:
            hint = t('ring_finder.acquisition_search_wrong_state').format(system=reference_system, state=power_state)
        else:
            hint = t('ring_finder.acquisition_search_no_data').format(system=reference_system)
        self._acq['hint'] = hint
        self._acq_fill([], self._acq['mineral'], {}, {}, {})

    def _show_acquisition_search_results(self, reference_system: str, power_state: str, radius: float,
                                         results: list, mineral_filter: Optional[str], sell_prices: dict,
                                         best_mineral: dict, best_rows: dict = None, owner: str = ''):
        acq = self._acq
        acq['state'] = power_state
        acq['owner'] = owner
        acq['radius'] = radius
        mineral_display = self._format_material_for_display(mineral_filter) if mineral_filter else t('ring_finder.all_minerals')
        acq['count'] = len(results)
        if not results:
            acq['hint'] = t('ring_finder.acquisition_search_no_candidates').format(
                system=reference_system, state=power_state, radius=int(radius), mineral=mineral_display)
        self._acq_fill(results, mineral_filter, sell_prices, best_mineral, best_rows or {})

    def _acq_fill(self, results: list, mineral_filter: Optional[str], sell_prices: dict,
                  best_mineral: dict, best_rows: dict):
        from app_utils import format_market_source
        acq = self._acq
        tree = self._acq_tree
        tree.delete(*tree.get_children())
        for mapping in (acq['system_by_row'], acq['station_by_row'], acq['source_by_row']):
            mapping.clear()
        acq.setdefault('outdated', set()).clear()

        tree.heading("Price", text=self._acq_price_header(mineral_filter))
        min_w = self._acq_min_width("Price")
        tree.column("Price", minwidth=min_w, width=max(tree.column("Price", "width"), min_w))
        # Best Mineral only means something when "All Minerals" was searched
        self._cv_set_force_hidden('acquisition_search', 'Mineral', mineral_filter is not None)

        for sys_name, sys_entry in results:
            power = sys_entry.get('controlling_power', '') or t('system_finder.pp_unoccupied')
            if power == '~none~':
                power = t('system_finder.pp_unoccupied')
            distance = sys_entry.get('distance', 0)
            price = sell_prices.get(sys_name, 0)
            buyer_row = best_rows.get(sys_name, {})
            station = buyer_row.get('stationName', '') or '-'
            demand = buyer_row.get('demand')
            row_id = tree.insert("", "end", values=(
                sys_name, station, self._format_station_type(buyer_row.get('stationType')),
                self._format_pad_size(buyer_row.get('maxLandingPadSize')), f"{distance:.1f}", power,
                self._format_material_for_display(best_mineral.get(sys_name, '')),
                f"{demand:,}" if isinstance(demand, (int, float)) else '-',
                f"{price:,} CR", self._format_data_age(buyer_row.get('updatedAt', ''))))
            acq['system_by_row'][row_id] = sys_name
            acq['station_by_row'][row_id] = station
            acq['source_by_row'][row_id] = format_market_source(buyer_row)
        self._acq_refresh_controls()

    # --- row actions ---------------------------------------------------------------

    def _acq_copy_system(self, row_id):
        system = self._acq['system_by_row'].get(row_id)
        if system:
            self.parent.clipboard_clear()
            self.parent.clipboard_append(system)
            self.parent.update_idletasks()

    def _acq_on_click(self, event):
        row_id = self._acq_tree.identify_row(event.y)
        if row_id:
            self._acq_tree.selection_set(row_id)
            self._acq_copy_system(row_id)

    def _acq_on_double_click(self, event):
        """Like the hotspot table: the System or Station cell opens the system on Inara and
        rechecks its PowerPlay state."""
        tree = self._acq_tree
        if tree.identify_region(event.x, event.y) != "cell":
            return
        row_id = tree.identify_row(event.y)
        if row_id and displayed_column(tree, tree.identify_column(event.x)) in ("System", "Station"):
            self._open_inara_and_check_pp(self._acq['system_by_row'].get(row_id, ''), self._acq_apply_pp_result)

    def _open_inara_and_check_pp(self, system: str, on_result):
        """Open system on Inara and read its PowerPlay state there (saved, so later searches
        use it when it is newer); on_result(system, result) runs on the UI thread."""
        if not system:
            return
        self._bp_open_url("https://inara.cz/elite/starsystem/?search={}", system)

        def worker():
            from system_finder_api import SystemFinderAPI
            result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system)
            self.parent.after(0, lambda: on_result(system, result))
        threading.Thread(target=worker, daemon=True).start()

    def _acq_apply_pp_result(self, system: str, result):
        """A selling system that is no longer Unoccupied can't earn acquisition merits: mark
        its rows and show its new PowerPlay state."""
        if not result:
            return
        acq = self._acq
        tree = self._acq_tree
        outdated = acq.setdefault('outdated', set())
        if result.get('power_state') == 'Unoccupied':
            outdated.discard(system)
        else:
            outdated.add(system)
        for row_id, name in acq['system_by_row'].items():
            if name == system and tree.exists(row_id):
                if system in outdated:
                    tree.set(row_id, 'Power', self._bp_pp_text(result))
                set_outdated_tag(tree, row_id, system in outdated)
        self._acq_refresh_controls()

    def _acq_on_right_click(self, event):
        row_id = self._acq_tree.identify_row(event.y)
        if row_id and self._acq['system_by_row'].get(row_id):
            self._acq_tree.selection_set(row_id)
            try:
                self._acq_row_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self._acq_row_menu.grab_release()

    def _acquisition_reference_materials(self, system_name: str) -> list:
        """English material names known to be minable at system_name, from the local
        database - the minerals "All Minerals" checks."""
        try:
            rows = self.user_db.get_system_hotspots(system_name)
        except Exception:
            rows = []
        return list({row.get('material_name', '') for row in rows if row.get('material_name')})
