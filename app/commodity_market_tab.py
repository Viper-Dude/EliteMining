"""Commodity Market tab: Mining Commodities and Trade Commodities sub-tabs (moved from main.py)."""

import logging
import threading
import tkinter as tk
from tkinter import ttk

from app_utils import create_action_button
from column_visibility_helper import displayed_column
from config import _load_cfg
from core.constants import MENU_COLORS
from localization import t, get_station_types, get_sort_options, get_age_options, get_material, get_abbr
from marketplace_api import MarketplaceAPI
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from ui.theme import modern_color
from ui.themed_checkbox import ThemedCheckbutton, ThemedRadiobutton
from ui.tooltip import ToolTip

log = logging.getLogger("EliteMining")


class CommodityMarketTabMixin:
    def _build_marketplace_tab(self, frame: ttk.Frame) -> None:
        """Build the Commodity Market tab with sub-tabs for Mining and Trade commodities"""
        # Create sub-notebook for Mining vs Trade commodities
        sub_notebook = ttk.Notebook(frame)
        sub_notebook.pack(fill="both", expand=True)
        
        # Mining Commodities sub-tab
        mining_tab = ttk.Frame(sub_notebook, padding=8)
        self._build_mining_commodities_tab(mining_tab)
        sub_notebook.add(mining_tab, text=t('tabs.mining_commodities'))
        
        # Multiple Prices sub-tab
        from multi_mineral_tab import MultiMineralTab
        multi_tab = ttk.Frame(sub_notebook, padding=8)
        self.multi_mineral_tab = MultiMineralTab(multi_tab, self)
        self.market_sub_notebook = sub_notebook
        self.market_multi_tab_frame = multi_tab
        sub_notebook.add(multi_tab, text=t('tabs.multi_mineral'))

        from cargo_sell_planner import CargoSellPlanner
        sell_hold_tab = ttk.Frame(sub_notebook, padding=8)
        self.cargo_sell_planner = CargoSellPlanner(sell_hold_tab, self)
        sub_notebook.add(sell_hold_tab, text=t('sell_hold.title'))
        
        # Trade Commodities sub-tab
        trade_tab = ttk.Frame(sub_notebook, padding=8)
        self._build_trade_commodities_tab(trade_tab)
        sub_notebook.add(trade_tab, text=t('tabs.trade_commodities'))

        def _clear_market_sub_focus(event=None):
            sub_notebook.focus_set()
            self.multi_mineral_tab.ref_entry.selection_clear()
            self.cargo_sell_planner._clear_field_selections()
        sub_notebook.bind('<<NotebookTabChanged>>', lambda e: (_clear_market_sub_focus(), self.after(50, _clear_market_sub_focus)))
    
    def _build_mining_commodities_tab(self, frame: ttk.Frame) -> None:
        """Build the Mining Commodities sub-tab - matches original Commodity Market design"""
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search section
        search_header = ttk.Frame(main_container)
        search_header.pack(fill="x")
        from ui.help_link import create_labelframe_title
        create_labelframe_title(
            search_header, t('marketplace.search_title'), "commodity-market", t('marketplace.help_tooltip'), ToolTip).pack(side="left")
        search_frame = ttk.LabelFrame(main_container, padding=10)
        search_frame.pack(fill="x", pady=(0, 10))

        # Load marketplace preferences from config
        cfg = _load_cfg()
        self.marketplace_search_mode = tk.StringVar(value=cfg.get('marketplace_search_mode', 'near_system'))
        self.marketplace_sell_mode = tk.BooleanVar(value=cfg.get('marketplace_sell_mode', True))
        self.marketplace_buy_mode = tk.BooleanVar(value=cfg.get('marketplace_buy_mode', False))
        
        # Get theme for checkbox/radiobutton styling
        from config import load_theme
        _mkt_cb_theme = load_theme()
        if _mkt_cb_theme == "elite_orange":
            _mkt_cb_bg = "#000000"  # Black background for orange theme
            _mkt_cb_select = "#000000"
        else:
            _mkt_cb_bg = "#1e1e1e"
            _mkt_cb_select = "#1e1e1e"
        
        # Row 0: Search Mode (Near/Galaxy) + Sell/Buy
        row0_frame = tk.Frame(search_frame, bg=_mkt_cb_bg)
        row0_frame.pack(fill="x", pady=(0, 10))

        if _mkt_cb_theme not in ("modern", "modern_slate", "modern_orange"):
            self.marketplace_total_label = tk.Label(search_header, text='',
                                                   bg=_mkt_cb_bg, fg="gray", font=self._scaled_font(8))
            self.marketplace_total_label.pack(side="right", padx=(0, 5))

        # Start market API status check
        self.after(1000, self._check_market_api_status)

        rb1 = ThemedRadiobutton(row0_frame, text=t('marketplace.near_system'), variable=self.marketplace_search_mode,
                      value="near_system", bg=_mkt_cb_bg, fg="#ffffff", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        rb1.pack(side="left", padx=(0, 15))
        rb1.config(takefocus=0)
        ToolTip(rb1, t('tooltips.near_system_search'))
        
        rb2 = ThemedRadiobutton(row0_frame, text=t('marketplace.galaxy_wide'), variable=self.marketplace_search_mode,
                      value="galaxy_wide", bg=_mkt_cb_bg, fg="#ffffff", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        rb2.pack(side="left", padx=(0, 20))
        rb2.config(takefocus=0)
        ToolTip(rb2, t('tooltips.galaxy_wide_search'))
        
        ttk.Separator(row0_frame, orient="vertical").pack(side="left", fill="y", padx=(0, 15))
        
        sell_cb = ThemedCheckbutton(row0_frame, text=t('marketplace.sell'), variable=self.marketplace_sell_mode,
                      command=self._on_sell_mode_toggle, bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        sell_cb.pack(side="left", padx=(0, 10))
        ToolTip(sell_cb, t('tooltips.sell_mode'))
        
        buy_cb = ThemedCheckbutton(row0_frame, text=t('marketplace.buy'), variable=self.marketplace_buy_mode,
                      command=self._on_buy_mode_toggle, bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        buy_cb.pack(side="left")
        ToolTip(buy_cb, t('tooltips.buy_mode'))
        
        # Filter grid: rows share real grid columns instead of pack()+magic-padx,
        # so "Sort by"/"Max age" stay aligned under "Commodity"/"Station" at any UI scale.
        filter_grid = tk.Frame(search_frame, bg=_mkt_cb_bg)
        filter_grid.pack(fill="x", pady=(0, 10))
        for _col in (0, 1, 2, 3, 4):
            filter_grid.grid_columnconfigure(_col, weight=0)
        row1_frame = filter_grid  # kept for any code below still referencing row1_frame

        # Row 1 (grid row 0): Reference System + Commodity
        ttk.Label(filter_grid, text=t('marketplace.ref_system'), width=12).grid(row=0, column=0, sticky="w", padx=(0, 5), pady=(0, 8))
        self.marketplace_reference_system = tk.StringVar(value=cfg.get('marketplace_reference_system', ''))
        # Ref System entry + "Current System" button share a sub-frame packed into
        # column 1, so "Current System"'s width doesn't force column 2 wide and
        # strand the checkboxes below it far from the Station dropdown.
        ref_entry_frame = tk.Frame(filter_grid, bg=_mkt_cb_bg)
        ref_entry_frame.grid(row=0, column=1, columnspan=2, sticky="w", pady=(0, 8))

        self.marketplace_ref_entry = ttk.Entry(ref_entry_frame, textvariable=self.marketplace_reference_system, width=30)
        self.marketplace_ref_entry.pack(side="left", padx=(0, 5))
        self.marketplace_ref_entry.bind("<Return>", lambda e: self._search_marketplace())
        self.marketplace_ref_entry.bind("<FocusOut>", lambda e: e.widget.selection_clear())
        # Autocomplete
        from system_autocomplete import SystemAutocomplete
        self._ac_marketplace_ref = SystemAutocomplete(self.marketplace_ref_entry, self.marketplace_reference_system, self)

        self.marketplace_use_current_btn = create_action_button(ref_entry_frame, text=t('marketplace.use_current'),
                                    command=self._use_current_system_marketplace,
                                    bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                                    relief="ridge", bd=1, cursor="hand2",
                                    highlightbackground=_mkt_cb_bg, highlightcolor=_mkt_cb_bg)
        self.marketplace_use_current_btn.pack(side="left")

        # Commodity label with consistent spacing
        ttk.Label(filter_grid, text=t('marketplace.commodity_type')).grid(row=0, column=3, sticky="w", padx=(0, 8), pady=(0, 8))

        # Commodity list with localization
        from core.constants import MINING_COMMODITY_ORDER
        self._commodity_order = list(MINING_COMMODITY_ORDER)
        
        # Low Temperature Diamonds is too long for the dropdown, so it uses its short form
        def format_commodity_display(name):
            if name == "Low Temperature Diamonds":
                return get_abbr(name)
            return get_material(name)
        
        self._commodity_map = {k: format_commodity_display(k) for k in self._commodity_order}
        self._commodity_rev_map = {v: k for k, v in self._commodity_map.items()}
        for old_display in ("Low Temperature Diamonds", "Low Temp. Diamonds"):
            self._commodity_rev_map.setdefault(old_display, "Low Temperature Diamonds")
        
        saved_commodity = cfg.get('marketplace_commodity', 'Alexandrite')
        self.marketplace_commodity = tk.StringVar(value=self._commodity_map.get(saved_commodity, saved_commodity))
        sorted_commodities = [self._commodity_map[k] for k in self._commodity_order]
        commodity_combo = ttk.Combobox(filter_grid, textvariable=self.marketplace_commodity,
                                     values=sorted_commodities, state="readonly", width=16)
        commodity_combo.grid(row=0, column=4, sticky="w", pady=(0, 8))
        commodity_combo.bind("<Return>", lambda e: self._search_marketplace())
        commodity_combo.bind("<<ComboboxSelected>>", lambda e: self._save_marketplace_preferences())
        commodity_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')

        # Row 2 (grid row 1): Station type filters + Sort by (aligned with Row 1)
        row2_frame = filter_grid

        # Station type localization maps
        station_type_map = get_station_types()
        self._station_type_order = ['All', 'Orbital', 'Surface', 'Fleet Carrier', 'Megaship', 'Stronghold']
        self._station_type_map = {k: station_type_map.get(k, k) for k in self._station_type_order}
        self._station_type_rev_map = {v: k for k, v in self._station_type_map.items()}
        
        # Sort options localization maps (full map for all modes)
        self._sort_options_map = get_sort_options()
        self._sort_rev_map = {v: k for k, v in self._sort_options_map.items()}
        
        # Age options localization maps
        age_options_map = get_age_options()
        self._age_order = ['Any', '1 hour', '8 hours', '16 hours', '1 day', '2 days']
        self._age_map = {k: age_options_map.get(k, k) for k in self._age_order}
        self._age_rev_map = {v: k for k, v in self._age_map.items()}
        
        # Station label aligned under Ref. System (grid column 0/1)
        station_label = ttk.Label(row2_frame, text=t('marketplace.station'), width=12)
        station_label.grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(0, 8))
        saved_station = cfg.get('marketplace_station_type', 'All')
        self.marketplace_station_type = tk.StringVar(value=self._station_type_map.get(saved_station, saved_station))
        station_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_station_type,
                                values=[self._station_type_map[k] for k in self._station_type_order],
                                state="readonly", width=12)
        station_combo.grid(row=1, column=1, sticky="w", pady=(0, 8))
        station_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
        ToolTip(station_combo, t('tooltips.station_type_filter'))

        def on_station_type_change(*args):
            selected = self.marketplace_station_type.get()
            english_val = self._station_type_rev_map.get(selected, selected)
            if english_val == "Fleet Carrier":
                self.marketplace_exclude_carriers.set(False)
                self.marketplace_exclude_cb.config(state="disabled")
            else:
                self.marketplace_exclude_cb.config(state="normal")
            self._save_marketplace_preferences()
        self.marketplace_station_type.trace_add("write", on_station_type_change)

        # Checkboxes share grid column 2 in their own packed sub-frame
        row2_checks_frame = tk.Frame(row2_frame, bg=_mkt_cb_bg)
        row2_checks_frame.grid(row=1, column=2, sticky="w", padx=(15, 25), pady=(0, 8))

        self.marketplace_exclude_carriers = tk.BooleanVar(value=cfg.get('marketplace_exclude_carriers', True))
        self.marketplace_exclude_cb = ThemedCheckbutton(row2_checks_frame, text=t('marketplace.exclude_carriers'), variable=self.marketplace_exclude_carriers,
                      command=self._save_marketplace_preferences,
                      bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        self.marketplace_exclude_cb.pack(side="left", padx=(0, 10))
        ToolTip(self.marketplace_exclude_cb, t('tooltips.exclude_carriers'))
        # Apply initial state if Fleet Carrier is already selected
        if self._station_type_rev_map.get(self.marketplace_station_type.get(), '') == 'Fleet Carrier':
            self.marketplace_exclude_carriers.set(False)
            self.marketplace_exclude_cb.config(state="disabled")

        self.marketplace_large_pad_only = tk.BooleanVar(value=cfg.get('marketplace_large_pad_only', False))
        large_pad_cb = ThemedCheckbutton(row2_checks_frame, text=t('marketplace.large_pads'), variable=self.marketplace_large_pad_only,
                      command=self._save_marketplace_preferences,
                      bg=_mkt_cb_bg, fg="#e0e0e0", selectcolor=_mkt_cb_select,
                      activebackground=_mkt_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        large_pad_cb.pack(side="left")
        ToolTip(large_pad_cb, t('tooltips.large_pads'))

        # Sort by label aligned under Commodity (grid column 3/4)
        ttk.Label(row2_frame, text=t('marketplace.sort_by')).grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(0, 8))
        saved_sort = cfg.get('marketplace_order_by', 'Distance')
        # Determine initial sort options based on sell mode (default)
        initial_sort_order = ['Best price (highest)', 'Distance', 'Best demand', 'Last update']
        self.marketplace_order_by = tk.StringVar(value=self._sort_options_map.get(saved_sort, saved_sort))
        self.marketplace_order_combo = ttk.Combobox(row2_frame, textvariable=self.marketplace_order_by,
                                     values=[self._sort_options_map.get(k, k) for k in initial_sort_order],
                                     state="readonly", width=20)
        self.marketplace_order_combo.grid(row=1, column=4, sticky="w", pady=(0, 8))
        self.marketplace_order_combo.bind("<<ComboboxSelected>>", lambda e: self._save_marketplace_preferences())
        self.marketplace_order_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
        ToolTip(self.marketplace_order_combo, t('tooltips.sort_by'))

        # Row 3 (grid row 2): Search button and Max Age (aligned under Station / Sort by)
        row3_frame = filter_grid

        search_btn = create_action_button(row3_frame, primary=True, text="🔍 " + t('marketplace.search'),
                              command=self._search_marketplace,
                              bg="#2a4a2a", fg="#e0e0e0", 
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, cursor="hand2")
        self.marketplace_search_btn = search_btn
        search_btn.grid(row=2, column=0, columnspan=3, sticky="w")

        # Max Age aligned under Sort by (grid column 3/4)
        _max_age_fg = "#ff8c00" if _mkt_cb_theme == "elite_orange" else "#e0e0e0"
        max_age_label = tk.Label(row3_frame, text=t('marketplace.max_age'), bg=_mkt_cb_bg, fg=_max_age_fg)
        max_age_label.grid(row=2, column=3, sticky="w", padx=(0, 8))
        saved_age = cfg.get('marketplace_max_age', '8 hours')
        self.marketplace_max_age = tk.StringVar(value=self._age_map.get(saved_age, saved_age))
        age_combo = ttk.Combobox(row3_frame, textvariable=self.marketplace_max_age,
                                values=[self._age_map[k] for k in self._age_order],
                                state="readonly", width=10)
        age_combo.grid(row=2, column=4, sticky="w")
        age_combo.bind("<<ComboboxSelected>>", lambda e: self._save_marketplace_preferences())
        age_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
        ToolTip(age_combo, t('tooltips.max_age'))
        
        # EDTools button hidden (keep for future reference)
        # edtools_btn = tk.Button(search_frame, text="🔍 Search EDTools.cc", 
        #                        command=self._open_edtools_market,
        #                        bg="#2a4a2a", fg="#e0e0e0")
        # edtools_btn.grid(row=4, column=0, columnspan=5, pady=(5, 5))
        
        # Results section with help text on same line as label
        results_header = tk.Frame(main_container, bg=_mkt_cb_bg)
        results_header.pack(fill="x", pady=(10, 0))
        
        _results_fg = "#ff8c00" if _mkt_cb_theme == "elite_orange" else "#ffffff"
        tk.Label(results_header, text=t('marketplace.search_results'), 
                bg=_mkt_cb_bg, fg=_results_fg, 
                font=self._scaled_font(10, "bold")).pack(side="left")
        
        results_info = ttk.Label(results_header, text="\u24d8", foreground=modern_color("#8A94A3"),
                                 cursor="hand2", font=self._scaled_font(10))
        results_info.pack(side="left", padx=(6, 2))
        if _mkt_cb_theme in ("modern", "modern_slate", "modern_orange"):
            ToolTip(results_info, t('marketplace.right_click_options') + "\n\n" + t('marketplace.fc_docking_note'))
        else:
            ToolTip(results_info, t('marketplace.right_click_options'))
            tk.Label(results_header, text="  •  " + t('marketplace.fc_docking_note'),
                    bg=_mkt_cb_bg, fg="#888888",
                    font=self._scaled_font(8)).pack(side="left")
        
        self._cv_add_columns_button(results_header, 'mining_commodities')

        # Average price label (right side, before total count)
        _avg_fg = "#ffd700"  # gold — visible on both dark and orange themes
        self.marketplace_avg_label = tk.Label(results_header, text="",
                                              bg=_mkt_cb_bg, fg=_avg_fg, font=self._scaled_font(8, "bold"))
        self.marketplace_avg_label.pack(side="right", padx=(0, 10))
        self.marketplace_best_label = tk.Label(results_header, text="",
                                               bg=_mkt_cb_bg, fg=_avg_fg, font=self._scaled_font(8, "bold"))
        self.marketplace_best_label.pack(side="right", padx=(0, 10))

        if _mkt_cb_theme in ("modern", "modern_slate", "modern_orange"):
            self.marketplace_total_label = ttk.Label(results_header, text='', anchor="w",
                font=self._scaled_font(9, "bold"), foreground=modern_color("#E6EAF0"))
            self.marketplace_total_label.pack(side="left", fill="x", expand=True, padx=(10, 0))

        results_frame = tk.Frame(main_container, bg="#2d2d2d", relief="sunken", bd=1)
        results_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        # Create results table
        self._create_marketplace_results_table(results_frame)

        # Add tooltips
        ToolTip(self.marketplace_ref_entry, t('tooltips.reference_system'))
        ToolTip(self.marketplace_use_current_btn, t('tooltips.use_current_market'))
        ToolTip(search_btn, t('tooltips.search_market'))
        ToolTip(commodity_combo, t('tooltips.select_commodity'))
        
        # Initialize dropdown options based on current buy/sell mode
        self._update_marketplace_order_options()
        
        # Load saved preferences
        self._load_marketplace_preferences()
        self._setup_galaxy_market_options('marketplace', filter_grid, cfg, self._age_map)
    
    def _build_trade_commodities_tab(self, frame: ttk.Frame) -> None:
        """Build the Trade Commodities sub-tab with category selection"""
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Search section
        search_header = ttk.Frame(main_container)
        search_header.pack(fill="x")
        from ui.help_link import create_labelframe_title
        create_labelframe_title(
            search_header, t('marketplace.search_title'), "commodity-market", t('marketplace.help_tooltip'), ToolTip).pack(side="left")
        search_frame = ttk.LabelFrame(main_container, padding=10)
        search_frame.pack(fill="x", pady=(0, 10))

        # Load marketplace preferences from config
        cfg = _load_cfg()
        self.trade_search_mode = tk.StringVar(value=cfg.get('trade_search_mode', 'near_system'))
        self.trade_sell_mode = tk.BooleanVar(value=cfg.get('trade_sell_mode', True))
        self.trade_buy_mode = tk.BooleanVar(value=cfg.get('trade_buy_mode', False))
        
        # Get theme for checkbox/radiobutton styling
        from config import load_theme
        _trade_cb_theme = load_theme()
        if _trade_cb_theme == "elite_orange":
            _trade_cb_bg = "#000000"
            _trade_cb_select = "#000000"
        else:
            _trade_cb_bg = "#1e1e1e"
            _trade_cb_select = "#1e1e1e"
        
        # Row 0: Search Mode (Near/Galaxy) + Sell/Buy
        row0_frame = tk.Frame(search_frame, bg=_trade_cb_bg)
        row0_frame.pack(fill="x", pady=(0, 10))

        if _trade_cb_theme not in ("modern", "modern_slate", "modern_orange"):
            self.trade_total_label = tk.Label(search_header, text='',
                                              bg=_trade_cb_bg, fg="gray", font=self._scaled_font(8))
            self.trade_total_label.pack(side="right", padx=(0, 5))

        rb1 = ThemedRadiobutton(row0_frame, text=t('marketplace.near_system'), variable=self.trade_search_mode,
                      value="near_system", bg=_trade_cb_bg, fg="#ffffff", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        rb1.pack(side="left", padx=(0, 15))
        rb1.config(takefocus=0)
        ToolTip(rb1, t('tooltips.near_system_search'))
        
        rb2 = ThemedRadiobutton(row0_frame, text=t('marketplace.galaxy_wide'), variable=self.trade_search_mode,
                      value="galaxy_wide", bg=_trade_cb_bg, fg="#ffffff", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        rb2.pack(side="left", padx=(0, 20))
        rb2.config(takefocus=0)
        ToolTip(rb2, t('tooltips.galaxy_wide_search'))
        
        ttk.Separator(row0_frame, orient="vertical").pack(side="left", fill="y", padx=(0, 15))
        
        sell_cb = ThemedCheckbutton(row0_frame, text=t('marketplace.sell'), variable=self.trade_sell_mode,
                      command=self._on_trade_sell_mode_toggle, bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        sell_cb.pack(side="left", padx=(0, 10))
        ToolTip(sell_cb, t('tooltips.sell_mode'))
        
        buy_cb = ThemedCheckbutton(row0_frame, text=t('marketplace.buy'), variable=self.trade_buy_mode,
                      command=self._on_trade_buy_mode_toggle, bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        buy_cb.pack(side="left")
        ToolTip(buy_cb, t('tooltips.buy_mode'))
        
        # Filter grid: rows share real grid columns instead of pack()+magic-padx,
        # so "Sort by"/"Max age" stay aligned under "Category"/"Station" at any UI scale.
        filter_grid = tk.Frame(search_frame, bg=_trade_cb_bg)
        filter_grid.pack(fill="x", pady=(0, 10))
        for _col in (0, 1, 2, 3, 4, 5, 6):
            filter_grid.grid_columnconfigure(_col, weight=0)
        row1_frame = filter_grid

        ttk.Label(row1_frame, text=t('marketplace.ref_system'), width=12).grid(row=0, column=0, sticky="w", padx=(0, 5), pady=(0, 8))
        self.trade_reference_system = tk.StringVar(value=cfg.get('trade_reference_system', ''))
        # Ref System entry + "Current System" button share a sub-frame packed into
        # column 1, so "Current System"'s width doesn't force column 2 wide and
        # strand the checkboxes below it far from the Station dropdown.
        ref_entry_frame = tk.Frame(row1_frame, bg=_trade_cb_bg)
        ref_entry_frame.grid(row=0, column=1, columnspan=2, sticky="w", pady=(0, 8))

        self.trade_ref_entry = ttk.Entry(ref_entry_frame, textvariable=self.trade_reference_system, width=24)
        self.trade_ref_entry.pack(side="left", padx=(0, 5))
        self.trade_ref_entry.bind("<Return>", lambda e: self._search_trade_market())
        self.trade_ref_entry.bind("<FocusOut>", lambda e: e.widget.selection_clear())
        # Autocomplete
        from system_autocomplete import SystemAutocomplete
        self._ac_trade_ref = SystemAutocomplete(self.trade_ref_entry, self.trade_reference_system, self)

        self.trade_use_current_btn = create_action_button(ref_entry_frame, text=t('marketplace.use_current'),
                                    command=self._use_current_system_trade,
                                    bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                                    relief="ridge", bd=1, cursor="hand2",
                                    highlightbackground=_trade_cb_bg, highlightcolor=_trade_cb_bg)
        self.trade_use_current_btn.pack(side="left")

        # Category dropdown
        ttk.Label(row1_frame, text=t('marketplace.category')).grid(row=0, column=3, sticky="w", padx=(0, 8), pady=(0, 8))

        # Get sorted category list from commodities data
        self._trade_categories = sorted(self.commodities_data.keys()) if self.commodities_data else []
        saved_category = cfg.get('trade_category', self._trade_categories[0] if self._trade_categories else 'Chemicals')
        self.trade_category = tk.StringVar(value=saved_category)
        category_combo = ttk.Combobox(row1_frame, textvariable=self.trade_category,
                                     values=self._trade_categories, state="readonly", width=18)
        category_combo.grid(row=0, column=4, sticky="w", padx=(0, 15), pady=(0, 8))
        category_combo.bind("<<ComboboxSelected>>", self._on_trade_category_changed)
        category_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')

        # Commodity dropdown (populated based on category)
        ttk.Label(row1_frame, text=t('marketplace.commodity_type')).grid(row=0, column=5, sticky="w", padx=(0, 8), pady=(0, 8))
        self.trade_commodity = tk.StringVar()
        self.trade_commodity_combo = ttk.Combobox(row1_frame, textvariable=self.trade_commodity,
                                                 values=[], state="readonly", width=20)
        self.trade_commodity_combo.grid(row=0, column=6, sticky="w", pady=(0, 8))
        self.trade_commodity_combo.bind("<Return>", lambda e: self._search_trade_market())
        self.trade_commodity_combo.bind("<<ComboboxSelected>>", lambda e: self._save_trade_preferences())
        self.trade_commodity_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')

        # Populate initial commodity list
        self._update_trade_commodity_list()

        # Row 2 (grid row 1): All filters (same layout as mining tab)
        row2_frame = filter_grid

        # Station type
        station_type_map = get_station_types()
        self._trade_station_type_order = ['All', 'Orbital', 'Surface', 'Fleet Carrier', 'Megaship', 'Stronghold']
        self._trade_station_type_map = {k: station_type_map.get(k, k) for k in self._trade_station_type_order}
        self._trade_station_type_rev_map = {v: k for k, v in self._trade_station_type_map.items()}
        
        # Sort options
        self._trade_sort_options_map = get_sort_options()
        self._trade_sort_rev_map = {v: k for k, v in self._trade_sort_options_map.items()}
        
        # Age options
        age_options_map = get_age_options()
        self._trade_age_order = ['Any', '1 hour', '8 hours', '16 hours', '1 day', '2 days']
        self._trade_age_map = {k: age_options_map.get(k, k) for k in self._trade_age_order}
        self._trade_age_rev_map = {v: k for k, v in self._trade_age_map.items()}
        
        station_label = ttk.Label(row2_frame, text=t('marketplace.station'), width=12)
        station_label.grid(row=1, column=0, sticky="w", padx=(0, 5), pady=(0, 8))
        saved_station = cfg.get('trade_station_type', 'All')
        self.trade_station_type = tk.StringVar(value=self._trade_station_type_map.get(saved_station, saved_station))
        station_combo = ttk.Combobox(row2_frame, textvariable=self.trade_station_type,
                                values=[self._trade_station_type_map[k] for k in self._trade_station_type_order],
                                state="readonly", width=12)
        station_combo.grid(row=1, column=1, sticky="w", pady=(0, 8))
        station_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
        ToolTip(station_combo, t('tooltips.station_type_filter'))

        def on_trade_station_type_change(*args):
            selected = self.trade_station_type.get()
            english_val = self._trade_station_type_rev_map.get(selected, selected)
            if english_val == "Fleet Carrier":
                self.trade_exclude_carriers.set(False)
                self.trade_exclude_cb.config(state="disabled")
            else:
                self.trade_exclude_cb.config(state="normal")
            self._save_trade_preferences()
        self.trade_station_type.trace_add("write", on_trade_station_type_change)

        # Checkboxes share grid column 2 in their own packed sub-frame
        row2_checks_frame = tk.Frame(row2_frame, bg=_trade_cb_bg)
        row2_checks_frame.grid(row=1, column=2, sticky="w", padx=(15, 25), pady=(0, 8))

        self.trade_exclude_carriers = tk.BooleanVar(value=cfg.get('trade_exclude_carriers', True))
        self.trade_exclude_cb = ThemedCheckbutton(row2_checks_frame, text=t('marketplace.exclude_carriers'), variable=self.trade_exclude_carriers,
                      command=self._save_trade_preferences,
                      bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        self.trade_exclude_cb.pack(side="left", padx=(0, 10))
        ToolTip(self.trade_exclude_cb, t('tooltips.exclude_carriers'))
        if self._trade_station_type_rev_map.get(self.trade_station_type.get(), '') == 'Fleet Carrier':
            self.trade_exclude_carriers.set(False)
            self.trade_exclude_cb.config(state="disabled")

        self.trade_large_pad_only = tk.BooleanVar(value=cfg.get('trade_large_pad_only', False))
        large_pad_cb = ThemedCheckbutton(row2_checks_frame, text=t('marketplace.large_pads'), variable=self.trade_large_pad_only,
                      command=self._save_trade_preferences,
                      bg=_trade_cb_bg, fg="#e0e0e0", selectcolor=_trade_cb_select,
                      activebackground=_trade_cb_bg, activeforeground="#ffffff",
                      highlightthickness=0, bd=0, relief="flat", font=self._scaled_font(9))
        large_pad_cb.pack(side="left")
        ToolTip(large_pad_cb, t('tooltips.large_pads'))

        # Sort by aligned under Category (grid column 3/4)
        ttk.Label(row2_frame, text=t('marketplace.sort_by')).grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(0, 8))
        saved_sort = cfg.get('trade_order_by', 'Distance')
        initial_sort_order = ['Best price (highest)', 'Distance', 'Best demand', 'Last update']
        self.trade_order_by = tk.StringVar(value=self._trade_sort_options_map.get(saved_sort, saved_sort))
        self.trade_order_combo = ttk.Combobox(row2_frame, textvariable=self.trade_order_by,
                                     values=[self._trade_sort_options_map.get(k, k) for k in initial_sort_order],
                                     state="readonly", width=18)
        self.trade_order_combo.grid(row=1, column=4, sticky="w", pady=(0, 8))
        self.trade_order_combo.bind("<<ComboboxSelected>>", lambda e: self._save_trade_preferences())
        self.trade_order_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
        ToolTip(self.trade_order_combo, t('tooltips.sort_by'))

        # Row 3 (grid row 2): Search button and Max Age (aligned under Station / Sort by)
        row3_frame = filter_grid

        search_btn = create_action_button(row3_frame, primary=True, text="🔍 " + t('marketplace.search'),
                              command=self._search_trade_market,
                              bg="#2a4a2a", fg="#e0e0e0",
                              activebackground="#3a5a3a", activeforeground="#ffffff",
                              relief="ridge", bd=1, cursor="hand2")
        self.trade_search_btn = search_btn
        search_btn.grid(row=2, column=0, columnspan=3, sticky="w")

        # Max Age aligned under Sort by (grid column 3/4)
        _max_age_fg = "#ff8c00" if _trade_cb_theme == "elite_orange" else "#e0e0e0"
        max_age_label = tk.Label(row3_frame, text=t('marketplace.max_age'), bg=_trade_cb_bg, fg=_max_age_fg)
        max_age_label.grid(row=2, column=3, sticky="w", padx=(0, 8))
        saved_age = cfg.get('trade_max_age', '8 hours')
        self.trade_max_age = tk.StringVar(value=self._trade_age_map.get(saved_age, saved_age))
        age_combo = ttk.Combobox(row3_frame, textvariable=self.trade_max_age,
                                values=[self._trade_age_map[k] for k in self._trade_age_order],
                                state="readonly", width=10)
        age_combo.grid(row=2, column=4, sticky="w")
        age_combo.bind("<<ComboboxSelected>>", lambda e: self._save_trade_preferences())
        age_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
        ToolTip(age_combo, t('tooltips.max_age'))

        # Results section
        results_header = tk.Frame(main_container, bg=_trade_cb_bg)
        results_header.pack(fill="x", pady=(10, 0))
        
        _results_fg = "#ff8c00" if _trade_cb_theme == "elite_orange" else "#ffffff"
        tk.Label(results_header, text=t('marketplace.search_results'), 
                bg=_trade_cb_bg, fg=_results_fg, 
                font=self._scaled_font(10, "bold")).pack(side="left")
        
        results_info = ttk.Label(results_header, text="\u24d8", foreground=modern_color("#8A94A3"),
                                 cursor="hand2", font=self._scaled_font(10))
        results_info.pack(side="left", padx=(6, 2))
        if _trade_cb_theme in ("modern", "modern_slate", "modern_orange"):
            ToolTip(results_info, t('marketplace.right_click_options') + "\n\n" + t('marketplace.fc_docking_note'))
        else:
            ToolTip(results_info, t('marketplace.right_click_options'))
            tk.Label(results_header, text="  •  " + t('marketplace.fc_docking_note'),
                    bg=_trade_cb_bg, fg="#888888",
                    font=self._scaled_font(8)).pack(side="left")
        
        self._cv_add_columns_button(results_header, 'trade_commodities')

        # Average price label (right side, before total count)
        _avg_fg = "#ffd700"  # gold — visible on both dark and orange themes
        self.trade_avg_label = tk.Label(results_header, text="",
                                        bg=_trade_cb_bg, fg=_avg_fg, font=self._scaled_font(8, "bold"))
        self.trade_avg_label.pack(side="right", padx=(0, 10))
        self.trade_best_label = tk.Label(results_header, text="",
                                         bg=_trade_cb_bg, fg=_avg_fg, font=self._scaled_font(8, "bold"))
        self.trade_best_label.pack(side="right", padx=(0, 10))

        if _trade_cb_theme in ("modern", "modern_slate", "modern_orange"):
            self.trade_total_label = ttk.Label(results_header, text='', anchor="w",
                font=self._scaled_font(9, "bold"), foreground=modern_color("#E6EAF0"))
            self.trade_total_label.pack(side="left", fill="x", expand=True, padx=(10, 0))

        results_frame = tk.Frame(main_container, bg="#2d2d2d", relief="sunken", bd=1)
        results_frame.pack(fill="both", expand=True, pady=(5, 0))
        
        # Create results table
        self._create_trade_results_table(results_frame)

        # Add tooltips
        ToolTip(self.trade_ref_entry, t('tooltips.reference_system'))
        ToolTip(self.trade_use_current_btn, t('tooltips.use_current_market'))
        ToolTip(search_btn, t('tooltips.search_market'))
        ToolTip(category_combo, t('tooltips.select_category'))
        ToolTip(self.trade_commodity_combo, t('tooltips.select_commodity'))
        
        # Initialize dropdown options based on current buy/sell mode
        self._update_trade_order_options()
        
        # Load saved preferences
        self._load_trade_preferences()
        self._setup_galaxy_market_options('trade', filter_grid, cfg, self._trade_age_map)

    def _create_marketplace_results_table(self, parent_frame):
        """Create results table for marketplace search"""
        table_frame = ttk.Frame(parent_frame, relief="solid", borderwidth=1)
        table_frame.pack(fill="both", expand=True, padx=2, pady=2)
        
        # Define columns with LS (light-seconds from star)
        # _spacer is an always-empty trailing column (never in the visibility menu) that
        # absorbs extra horizontal space, same as Ring Finder's results table - without it
        # the last real column gets force-stretched and its right border isn't draggable.
        columns = ("system", "station", "type", "pad", "distance", "ls", "demand", "price", "powerstate", "updated", "_spacer")
        
        # Configure Marketplace Treeview style (theme-aware)
        from config import load_theme
        _mkt_theme = load_theme()
        style = ttk.Style()
        
        if _mkt_theme == "elite_orange":
            _mkt_bg = "#1e1e1e"
            _mkt_fg = "#ff8c00"
            _mkt_hdr = "#1a1a1a"
            _mkt_sel_bg = "#ff6600"
            _mkt_sel_fg = "#000000"
        else:
            _mkt_bg = "#1e1e1e"
            _mkt_fg = "#e6e6e6"
            _mkt_hdr = "#2a2a2a"
            _mkt_sel_bg = "#0078d7"
            _mkt_sel_fg = "#ffffff"
        
        # Main treeview styling
        style.configure("Marketplace.Treeview",
                       rowheight=self._scaled_px(25),
                       borderwidth=1,
                       relief="solid",
                       bordercolor="#333333",
                       background=_mkt_bg,
                       foreground=_mkt_fg,
                       fieldbackground=_mkt_bg,
                       font=self._scaled_font(9))
        
        # Column header styling with borders
        style.configure("Marketplace.Treeview.Heading",
                       borderwidth=1,
                       relief="groove",  # Creates visible column separators
                       background=_mkt_hdr,
                       foreground=_mkt_fg,
                       padding=[5, 5],
                       anchor="w",
                       font=self._scaled_font(9, "bold"))  # Left-align all headers
        
        # Row selection styling
        style.map("Marketplace.Treeview",
                 background=[('selected', _mkt_sel_bg)],
                 foreground=[('selected', _mkt_sel_fg)])
        
        # Add subtle column separation via heading relief
        style.layout("Marketplace.Treeview.Heading", [
            ('Treeheading.cell', {'sticky': 'nswe'}),
            ('Treeheading.border', {'sticky':'nswe', 'children': [
                ('Treeheading.padding', {'sticky':'nswe', 'children': [
                    ('Treeheading.image', {'side':'right', 'sticky':''}),
                    ('Treeheading.text', {'sticky':'we'})
                ]})
            ]})
        ])
        
        # Create Treeview with custom style
        self.marketplace_tree = StripedTreeview(table_frame, columns=columns, show="headings", height=15, style="Marketplace.Treeview")
        
        # Define headings with sorting - explicitly set anchor to left-align header text
        numeric_columns = {"distance", "ls", "demand", "price", "updated"}
        for col in columns:
            if col == "_spacer":
                self.marketplace_tree.heading(col, text="", anchor="w")
                continue
            is_numeric = col in numeric_columns
            self.marketplace_tree.heading(col, text=self._get_column_title(col),
                                         anchor="center" if col in ("pad", "updated") else "w",
                                         command=lambda c=col, n=is_numeric: self._sort_marketplace_column(c, n))

        # Track sort state
        self.marketplace_sort_column = None
        self.marketplace_sort_reverse = False

        # Set column widths - Add extra padding to create visual separation
        # Using slightly increased widths and padding to create column spacing effect
        # minwidth is derived from the actual rendered header text width (at the
        # scaled heading font) rather than a fixed guess, so headers can never be
        # squeezed below what their own label needs, at any UI scale or language.
        # "demand" header text toggles between Demand/Supply at runtime, so measure
        # both possible strings and take the larger one.
        import tkinter.font as _tkfont
        _heading_font = _tkfont.Font(font=self._scaled_font(9, "bold"))
        _base_widths = {"system": 180, "station": 210, "type": 95, "pad": 45, "distance": 70, "ls": 70,
                        "demand": 75, "price": 125, "powerstate": 150, "updated": 95}
        _header_pad = self._scaled_px(24)  # header cell padding + sort-arrow space

        def _min_for(col_name):
            if col_name == "demand":
                text_width = max(_heading_font.measure(t('marketplace.demand')),
                                  _heading_font.measure(t('marketplace.supply')))
            else:
                header_text = self.marketplace_tree.heading(col_name, "text")
                text_width = _heading_font.measure(header_text)
            return max(text_width + _header_pad, self._scaled_px(50))

        _minwidths = {col: _min_for(col) for col in _base_widths}

        for col_name, base_width in _base_widths.items():
            self.marketplace_tree.column(col_name, width=max(self._scaled_px(base_width), _minwidths[col_name]),
                                         minwidth=_minwidths[col_name], anchor="center" if col_name in ("pad", "updated") else "w", stretch=False)

        # Spacer column - always last, gives every real column a draggable right border and
        # absorbs extra width instead of force-stretching the last real column.
        self.marketplace_tree.column("_spacer", width=self._scaled_px(20), minwidth=self._scaled_px(20), anchor="w", stretch=True)

        # Setup column visibility for mining commodities (exclude _spacer from the menu)
        self.setup_column_visibility(
            tree=self.marketplace_tree,
            columns=tuple(c for c in columns if c != "_spacer"),
            default_widths={col: max(self._scaled_px(w), _minwidths[col]) for col, w in _base_widths.items()},
            config_key='mining_commodities',
            allow_reorder=True,
            use_displaycolumns=True
        )
        self._cv_split_saved_column('mining_commodities', 'location', ('system', 'station'))

        # Load saved column widths from config — but never let an old (pre-scale)
        # saved width sit below the current scaled minwidth, or headers get squeezed.
        try:
            from config import load_commodity_market_column_widths
            saved_widths = load_commodity_market_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        current_minwidth = self.marketplace_tree.column(col_name, "minwidth")
                        self.marketplace_tree.column(col_name, width=max(width, current_minwidth))
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Commodity Market column widths: {e}")

        # Bind column resize event to save widths
        def save_marketplace_widths(event=None):
            try:
                from config import save_commodity_market_column_widths
                widths = {}
                for col in columns:
                    try:
                        widths[col] = self.marketplace_tree.column(col, "width")
                    except:
                        pass
                save_commodity_market_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Commodity Market column widths: {e}")
        
        self.marketplace_tree.bind("<ButtonRelease-1>", save_marketplace_widths)
        # Deselect when clicking empty space
        self.marketplace_tree.bind("<Button-1>", lambda e: self._deselect_on_empty_click(e, self.marketplace_tree))
        # Double-click the Powerplay cell to open Inara and fetch/refresh its data
        self.marketplace_tree.bind("<Double-1>", lambda e: self._on_commodity_tree_double_click(e, self.marketplace_tree))
        self._marketplace_row_source = {}
        from ui.cell_tooltip import attach_cell_tooltip
        attach_cell_tooltip(self.marketplace_tree, "updated", lambda item: self._marketplace_row_source.get(item, ''))
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.marketplace_tree.yview)
        self.marketplace_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.marketplace_tree.xview)
        self.marketplace_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure row tags for alternating colors (theme-aware, matches Ring Finder)
        if self.current_theme == "elite_orange":
            self.marketplace_tree.tag_configure('oddrow', background='#1e1e1e', foreground='#ff8c00')
            self.marketplace_tree.tag_configure('evenrow', background='#252525', foreground='#ff8c00')
        else:
            self.marketplace_tree.tag_configure('oddrow', background='#1e1e1e', foreground='#e6e6e6')
            self.marketplace_tree.tag_configure('evenrow', background='#282828', foreground='#e6e6e6')
        
        # Grid layout for treeview and scrollbars (like Ring Finder)
        self.marketplace_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        # Add right-click context menu
        self._create_marketplace_context_menu()
        # Register context menu handler for mining commodities
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['mining_commodities'] = self._show_marketplace_context_menu
        # Note: Right-click binding handled by column visibility mixin
    
    def _get_column_title(self, col):
        """Get display title for column - dynamically changes based on buy/sell mode"""
        # Check mode for demand/stock label
        is_buy_mode = self.marketplace_buy_mode.get() if hasattr(self, 'marketplace_buy_mode') else False
        
        titles = {
            "system": t('ring_finder.col_system'),
            "station": t('ring_finder.col_station'),
            "type": t('marketplace.type'),
            "pad": t('marketplace.pad'),
            "distance": t('marketplace.distance'),
            "ls": "LS",
            "demand": t('marketplace.supply') if is_buy_mode else t('marketplace.demand'),  # Dynamic based on mode
            "price": t('marketplace.price_cr'),
            "updated": t('marketplace.updated'),
            "powerstate": t('marketplace.powerstate')
        }
        return titles.get(col, col)
    
    def _update_marketplace_column_headers(self):
        """Update column headers when mode changes"""
        if hasattr(self, 'marketplace_tree'):
            numeric_columns = {"distance", "ls", "demand", "price", "updated"}
            for col in ("system", "station", "type", "pad", "distance", "ls", "demand", "price", "updated", "powerstate"):
                is_numeric = col in numeric_columns
                self.marketplace_tree.heading(col, text=self._get_column_title(col),
                                            anchor="center" if col in ("pad", "updated") else "w",
                                            command=lambda c=col, n=is_numeric: self._sort_marketplace_column(c, n))
    
    def _create_marketplace_context_menu(self):
        """Create right-click context menu for marketplace results"""
        # Get theme-aware menu colors
        from config import load_theme
        current_theme = load_theme()
        if current_theme == "elite_orange":
            menu_bg = "#1e1e1e"
            menu_fg = "#ff8c00"
            menu_active_bg = "#ff6600"
            menu_active_fg = "#000000"
        else:
            menu_bg = MENU_COLORS["bg"]
            menu_fg = MENU_COLORS["fg"]
            menu_active_bg = MENU_COLORS["activebackground"]
            menu_active_fg = MENU_COLORS["activeforeground"]
        
        self.marketplace_context_menu = tk.Menu(self, tearoff=0,
                                               bg=menu_bg, fg=menu_fg,
                                               activebackground=menu_active_bg,
                                               activeforeground=menu_active_fg,
                                               selectcolor=menu_active_bg,
                                               font=self._scaled_font(9))
        self.marketplace_context_menu.add_command(label=t('context_menu.open_inara'), command=self._open_inara_from_menu)
        self.marketplace_context_menu.add_command(label=t('context_menu.open_edsm'), command=self._open_edsm_from_menu)
        self.marketplace_context_menu.add_command(label=t('context_menu.open_spansh'), command=self._open_spansh_from_menu)
        self.marketplace_context_menu.add_separator()
        self.marketplace_context_menu.add_command(label=t('context_menu.find_hotspots'), command=self._find_hotspots_from_marketplace)
        self.marketplace_context_menu.add_separator()
        self.marketplace_context_menu.add_command(label=t('context_menu.copy_system'), command=self._copy_marketplace_system)
    
    def _create_trade_context_menu(self):
        """Create right-click context menu for trade commodities results (without Find Hotspots)"""
        # Get theme-aware menu colors
        from config import load_theme
        current_theme = load_theme()
        if current_theme == "elite_orange":
            menu_bg = "#1e1e1e"
            menu_fg = "#ff8c00"
            menu_active_bg = "#ff6600"
            menu_active_fg = "#000000"
        else:
            menu_bg = MENU_COLORS["bg"]
            menu_fg = MENU_COLORS["fg"]
            menu_active_bg = MENU_COLORS["activebackground"]
            menu_active_fg = MENU_COLORS["activeforeground"]
        
        self.trade_context_menu = tk.Menu(self, tearoff=0,
                                          bg=menu_bg, fg=menu_fg,
                                          activebackground=menu_active_bg,
                                          activeforeground=menu_active_fg,
                                          selectcolor=menu_active_bg,
                                          font=self._scaled_font(9))
        self.trade_context_menu.add_command(label=t('context_menu.open_inara'), command=self._open_inara_from_trade_menu)
        self.trade_context_menu.add_command(label=t('context_menu.open_edsm'), command=self._open_edsm_from_trade_menu)
        self.trade_context_menu.add_command(label=t('context_menu.open_spansh'), command=self._open_spansh_from_trade_menu)
        self.trade_context_menu.add_separator()
        self.trade_context_menu.add_command(label=t('context_menu.copy_system'), command=self._copy_trade_system)
    
    @staticmethod
    def _row_system_station(tree, item):
        """(system, station) from a results row's System and Station cells."""
        values = tree.item(item, 'values')
        if not values or len(values) < 2:
            return "", ""
        return str(values[0]).strip(), str(values[1]).strip()

    def _selected_system_station(self, tree):
        selection = tree.selection()
        return self._row_system_station(tree, selection[0]) if selection else ("", "")

    def _open_station_on_inara(self, tree):
        import urllib.parse
        import webbrowser
        _system, station = self._selected_system_station(tree)
        if station:
            webbrowser.open(f"https://inara.cz/elite/stations/?search={urllib.parse.quote_plus(station)}")

    def _open_station_on_edsm(self, tree):
        import urllib.parse
        import webbrowser
        _system, station = self._selected_system_station(tree)
        if station:
            webbrowser.open(f"https://www.edsm.net/en/search/stations/index/name/{urllib.parse.quote(station)}/")

    def _open_system_on_spansh(self, tree):
        import urllib.parse
        import webbrowser
        system, _station = self._selected_system_station(tree)
        if system:
            webbrowser.open(f"https://spansh.co.uk/search/{urllib.parse.quote(system)}")

    def _copy_selected_system(self, tree, label):
        system, _station = self._selected_system_station(tree)
        if system:
            self.clipboard_clear()
            self.clipboard_append(system)
            label.config(text=t('marketplace.copied_to_clipboard').format(system=system))

    def _open_inara_from_menu(self):
        self._open_station_on_inara(self.marketplace_tree)

    def _open_edsm_from_menu(self):
        self._open_station_on_edsm(self.marketplace_tree)

    def _open_spansh_from_menu(self):
        self._open_system_on_spansh(self.marketplace_tree)

    def _copy_marketplace_system(self):
        self._copy_selected_system(self.marketplace_tree, self.marketplace_total_label)
    
    def _find_hotspots_from_marketplace(self):
        """Open Hotspots Finder with the selected commodity to find mining locations"""
        # Get the currently selected commodity from the dropdown
        commodity_display = self.marketplace_commodity.get()
        
        # Convert localized name to English for ring finder
        commodity_english = self._commodity_rev_map.get(commodity_display, commodity_display)
        
        if not commodity_english:
            self.marketplace_total_label.config(text=t('marketplace.select_commodity'))
            return
        
        # Get the system from the selected row
        system_name = self._selected_system_station(self.marketplace_tree)[0] or None
        
        # Switch to Hotspots Finder tab
        try:
            self.notebook.select(1)  # Hotspots Finder is typically tab index 1
            
            # Set the mineral in ring finder
            if hasattr(self, 'ring_finder'):
                # Get localized mineral name for the dropdown
                from localization import get_material
                try:
                    localized_mineral = get_material(commodity_english)
                except:
                    localized_mineral = commodity_english
                
                # Set the mineral dropdown
                self.ring_finder.specific_material_var.set(localized_mineral)
                
                # Set reference system from selected row
                if system_name and hasattr(self.ring_finder, 'system_var'):
                    self.ring_finder.system_var.set(system_name)
                
                # Set Min Hotspots = 1
                if hasattr(self.ring_finder, 'min_hotspots_var'):
                    self.ring_finder.min_hotspots_var.set("1")
                
                # Set Max Distance = 100 LY
                if hasattr(self.ring_finder, 'distance_var'):
                    self.ring_finder.distance_var.set("100")
                
                # Set Max Results = 200 (highest available option)
                if hasattr(self.ring_finder, 'max_results_var'):
                    self.ring_finder.max_results_var.set("200")
                
                # Trigger search after a short delay to let UI update
                self.after(100, self.ring_finder.search_hotspots)
                
                print(f"[MARKETPLACE] Searching hotspots for {commodity_english} near {system_name or 'current system'}")
                
        except Exception as e:
            log.error(f"[MARKETPLACE] Error opening hotspots finder: {e}")
            import traceback
            traceback.print_exc()
    
    def _open_inara_from_trade_menu(self):
        self._open_station_on_inara(self.trade_tree)

    def _open_edsm_from_trade_menu(self):
        self._open_station_on_edsm(self.trade_tree)

    def _open_spansh_from_trade_menu(self):
        self._open_system_on_spansh(self.trade_tree)
    
    def _show_trade_context_menu(self, event):
        """Show context menu on right-click in Trade Commodities table"""
        try:
            # Select item under cursor
            item = self.trade_tree.identify_row(event.y)
            if item:
                self.trade_tree.selection_set(item)
                self.trade_tree.focus(item)
                self.trade_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.trade_context_menu.grab_release()
    
    def _copy_trade_system(self):
        self._copy_selected_system(self.trade_tree, self.trade_total_label)
    
    def _populate_marketplace_system(self):
        """Auto-populate marketplace system on startup (independent of ring finder's reference system)"""
        try:
            detected_system = self.get_current_system()
            if detected_system:
                if hasattr(self, '_ac_marketplace_ref'):
                    self._ac_marketplace_ref.suppress()
                self.marketplace_reference_system.set(detected_system)
                if hasattr(self, '_ac_marketplace_ref'):
                    self._ac_marketplace_ref.unsuppress()
        except:
            pass
    
    def _on_sell_mode_toggle(self):
        """Handle sell checkbox toggle - ensure only one mode is active"""
        if self.marketplace_sell_mode.get():
            # If sell is checked, uncheck buy
            self.marketplace_buy_mode.set(False)
        else:
            # If sell is unchecked, check buy (must have one mode active)
            self.marketplace_buy_mode.set(True)
        
        # Update column headers to reflect mode change
        self._update_marketplace_column_headers()
        
        # Update order by dropdown options for sell mode
        self._update_marketplace_order_options()
        
        # Save preference
        self._save_marketplace_preferences()
    
    def _on_buy_mode_toggle(self):
        """Handle buy checkbox toggle - ensure only one mode is active"""
        if self.marketplace_buy_mode.get():
            # If buy is checked, uncheck sell
            self.marketplace_sell_mode.set(False)
        else:
            # If buy is unchecked, check sell (must have one mode active)
            self.marketplace_sell_mode.set(True)
        
        # Update column headers to reflect mode change
        self._update_marketplace_column_headers()
        
        # Update order by dropdown options for buy mode
        self._update_marketplace_order_options()
        
        # Save preference
        self._save_marketplace_preferences()
    
    def _update_marketplace_order_options(self):
        """Update Order by dropdown options based on buy/sell mode"""
        if hasattr(self, 'marketplace_order_combo'):
            is_buy_mode = self.marketplace_buy_mode.get()
            current_value = self.marketplace_order_by.get()
            # Get English value for comparison
            current_english = self._sort_rev_map.get(current_value, current_value)
            
            if is_buy_mode:
                # Buy mode options (English keys)
                options_keys = ["Best price (lowest)", "Distance", "Best supply", "Last update"]
            else:
                # Sell mode options (English keys)
                options_keys = ["Best price (highest)", "Distance", "Best demand", "Last update"]
            
            # Convert to localized values
            options = [self._sort_options_map.get(k, k) for k in options_keys]
            self.marketplace_order_combo['values'] = options
            
            # Update current selection if it was one of the changing options
            if "Best price" in current_english or "price" in current_english.lower():
                self.marketplace_order_by.set(options[0])
            elif "supply" in current_english.lower() or "demand" in current_english.lower():
                self.marketplace_order_by.set(options[2])
            # Distance and Last update remain the same
    
    def _setup_galaxy_market_options(self, prefix, filter_grid, cfg, age_map):
        mode = getattr(self, prefix + '_search_mode')
        age = getattr(self, prefix + '_max_age')
        age_reverse = {value: key for key, value in age_map.items()}
        options = {
            'mode': mode.get(),
            'ages': {
                'near_system': age_reverse.get(age.get(), age.get()),
                'galaxy_wide': cfg.get(prefix + '_galaxy_max_age', '2 days'),
            },
        }
        if not hasattr(self, '_galaxy_market_options'):
            self._galaxy_market_options = {}
        self._galaxy_market_options[prefix] = options
        saved_limit = str(cfg.get(prefix + '_galaxy_max_results', '250'))
        if saved_limit not in ('100', '250', '500', 'All'):
            saved_limit = '250'
        limit = tk.StringVar(value=t('marketplace.all') if saved_limit == 'All' else saved_limit)
        setattr(self, prefix + '_galaxy_max_results', limit)
        label = ttk.Label(filter_grid, text=t('marketplace.max_results'))
        label.grid(row=3, column=3, sticky='w', padx=(0, 8), pady=(8, 0))
        combo = ttk.Combobox(filter_grid, textvariable=limit,
                             values=('100', '250', '500', t('marketplace.all')), state='readonly', width=10)
        combo.grid(row=3, column=4, sticky='w', pady=(8, 0))
        save = getattr(self, '_save_' + prefix + '_preferences')
        combo.bind('<<ComboboxSelected>>', lambda e: save())
        combo.bind('<<ComboboxSelected>>', lambda e: e.widget.selection_clear(), add='+')

        def show_mode():
            selected = options['mode']
            age.set(age_map.get(options['ages'][selected], options['ages'][selected]))
            for widget in (label, combo):
                if selected == 'galaxy_wide':
                    widget.grid()
                else:
                    widget.grid_remove()

        def change_mode(*args):
            options['ages'][options['mode']] = age_reverse.get(age.get(), age.get())
            options['mode'] = mode.get()
            show_mode()
            save()

        show_mode()
        mode.trace_add('write', change_mode)

    def _galaxy_market_limit(self, prefix):
        variable = getattr(self, prefix + '_galaxy_max_results', None)
        value = variable.get() if variable is not None else '250'
        return int(value) if value in ('100', '250', '500') else None

    def _market_age_preferences(self, prefix, max_age):
        options = getattr(self, '_galaxy_market_options', {}).get(prefix)
        if options is None:
            return {prefix + '_max_age': max_age}
        options['ages'][options['mode']] = max_age
        limit = self._galaxy_market_limit(prefix)
        return {
            prefix + '_max_age': options['ages']['near_system'],
            prefix + '_galaxy_max_age': options['ages']['galaxy_wide'],
            prefix + '_galaxy_max_results': limit if limit is not None else 'All',
        }

    def _convert_age_to_days(self, age_str):
        """Convert max age string to days for API (API expects integer days, rounds up sub-day values)"""
        age_map = {
            "Any": 30,
            "1 hour": 1,    # API doesn't support hours, use 1 day minimum
            "8 hours": 1,   # API doesn't support hours, use 1 day minimum
            "16 hours": 1,  # API doesn't support hours, use 1 day minimum
            "1 day": 1,
            "2 days": 2
        }
        return age_map.get(age_str, 1)  # Default to 1 day
    
    
    def _use_current_system_marketplace(self):
        """Use current system from journal/hotspots finder for marketplace search"""
        try:
            # Use ring finder's auto-detect logic
            if hasattr(self, 'ring_finder'):
                self.ring_finder._auto_detect_system()
                detected_system = self.ring_finder.system_var.get()
                if detected_system:
                    self._ac_marketplace_ref.suppress()
                    self.marketplace_reference_system.set(detected_system)
                    self._ac_marketplace_ref.unsuppress()
                    self._ac_marketplace_ref.hide()
                    return
            
            # Fallback: No ring finder available
            self._show_notice(self.marketplace_total_label, t('ring_finder.could_not_detect_system'))

        except Exception as e:
            log.error(f"Error getting current system: {e}")
            self._show_notice(self.marketplace_total_label, t('ring_finder.could_not_detect_system'))
    
    # Removed _toggle_search_mode() - reference system now always visible for both modes
    
    def _load_marketplace_preferences(self):
        """Load all marketplace preferences from config and apply them"""
        from config import _load_cfg
        cfg = _load_cfg()
        
        # Load search mode
        if 'marketplace_search_mode' in cfg:
            self.marketplace_search_mode.set(cfg['marketplace_search_mode'])
        
        # Load buy/sell mode
        if 'marketplace_sell_mode' in cfg:
            self.marketplace_sell_mode.set(cfg['marketplace_sell_mode'])
        if 'marketplace_buy_mode' in cfg:
            self.marketplace_buy_mode.set(cfg['marketplace_buy_mode'])
        
        # Load commodity (convert English to localized)
        if 'marketplace_commodity' in cfg:
            commodity_english = cfg['marketplace_commodity']
            commodity_localized = self._commodity_map.get(commodity_english, commodity_english)
            if commodity_localized in self._commodity_map.values():
                self.marketplace_commodity.set(commodity_localized)
        
        # Load station type (convert English to localized)
        if 'marketplace_station_type' in cfg:
            station_type_english = cfg['marketplace_station_type']
            station_type_localized = self._station_type_map.get(station_type_english, station_type_english)
            if station_type_localized in self._station_type_map.values():
                self.marketplace_station_type.set(station_type_localized)
        
        # Load checkboxes
        if 'marketplace_exclude_carriers' in cfg:
            self.marketplace_exclude_carriers.set(cfg['marketplace_exclude_carriers'])
        if 'marketplace_large_pad_only' in cfg:
            self.marketplace_large_pad_only.set(cfg['marketplace_large_pad_only'])
        
        # Load order by (convert English to localized)
        if 'marketplace_order_by' in cfg:
            order_by_english = cfg['marketplace_order_by']
            order_by_localized = self._sort_options_map.get(order_by_english, order_by_english)
            if order_by_localized in self._sort_options_map.values():
                self.marketplace_order_by.set(order_by_localized)
        
        # Load max age (convert English to localized)
        if 'marketplace_max_age' in cfg:
            max_age_english = cfg['marketplace_max_age']
            max_age_localized = self._age_map.get(max_age_english, max_age_english)
            if max_age_localized in self._age_map.values():
                self.marketplace_max_age.set(max_age_localized)
    
    def _save_marketplace_preferences(self):
        """Save all marketplace preferences to config"""
        from config import update_config_values
        # Convert localized values back to English for saving
        station_type_english = self._station_type_rev_map.get(self.marketplace_station_type.get(), self.marketplace_station_type.get())
        order_by_english = self._sort_rev_map.get(self.marketplace_order_by.get(), self.marketplace_order_by.get())
        max_age_english = self._age_rev_map.get(self.marketplace_max_age.get(), self.marketplace_max_age.get())
        commodity_english = self._commodity_rev_map.get(self.marketplace_commodity.get(), self.marketplace_commodity.get())
        updates = {
            "marketplace_search_mode": str(self.marketplace_search_mode.get()),
            "marketplace_sell_mode": bool(self.marketplace_sell_mode.get()),
            "marketplace_buy_mode": bool(self.marketplace_buy_mode.get()),
            "marketplace_reference_system": str(self.marketplace_reference_system.get()),
            "marketplace_commodity": commodity_english,
            "marketplace_station_type": station_type_english,
            "marketplace_exclude_carriers": bool(self.marketplace_exclude_carriers.get()),
            "marketplace_large_pad_only": bool(self.marketplace_large_pad_only.get()),
            "marketplace_order_by": order_by_english,
        }
        updates.update(self._market_age_preferences('marketplace', max_age_english))
        update_config_values(updates)
    
    # ==================== TRADE COMMODITIES TAB HELPERS ====================
    def _on_trade_category_changed(self, event=None):
        """Update commodity list when category changes"""
        self._update_trade_commodity_list()
        self._save_trade_preferences()
    
    def _update_trade_commodity_list(self):
        """Populate commodity dropdown based on selected category"""
        category = self.trade_category.get()
        if category in self.commodities_data:
            commodities = sorted(self.commodities_data[category])
            self.trade_commodity_combo['values'] = commodities
            # Select first commodity if current value not in new list
            current = self.trade_commodity.get()
            if current not in commodities and commodities:
                self.trade_commodity.set(commodities[0])
    
    def _on_trade_sell_mode_toggle(self):
        """Handle sell mode toggle for trade tab"""
        if not self.trade_sell_mode.get():
            self.trade_sell_mode.set(True)
        else:
            self.trade_buy_mode.set(False)
        self._update_trade_order_options()
        self._save_trade_preferences()
    
    def _on_trade_buy_mode_toggle(self):
        """Handle buy mode toggle for trade tab"""
        if not self.trade_buy_mode.get():
            self.trade_buy_mode.set(True)
        else:
            self.trade_sell_mode.set(False)
        self._update_trade_order_options()
        self._save_trade_preferences()
    
    def _update_trade_order_options(self):
        """Update sort options based on sell/buy mode for trade tab"""
        if self.trade_sell_mode.get():
            sort_order = ['Best price (highest)', 'Distance', 'Best demand', 'Last update']
        else:
            sort_order = ['Best price (lowest)', 'Distance', 'Best supply', 'Last update']
        self.trade_order_combo['values'] = [self._trade_sort_options_map.get(k, k) for k in sort_order]
        current = self._trade_sort_rev_map.get(self.trade_order_by.get(), self.trade_order_by.get())
        if 'price' in current.lower():
            self.trade_order_by.set(self.trade_order_combo['values'][0])
        elif 'supply' in current.lower() or 'demand' in current.lower():
            self.trade_order_by.set(self.trade_order_combo['values'][2])
    
    def _use_current_system_trade(self):
        """Fill trade reference system with current system"""
        if self.current_system:
            self._ac_trade_ref.suppress()
            self.trade_reference_system.set(self.current_system)
            self._ac_trade_ref.unsuppress()
            self._ac_trade_ref.hide()
            self._save_trade_preferences()
        else:
            self._show_notice(self.trade_total_label, t('ring_finder.could_not_detect_system'))
    
    def _load_trade_preferences(self):
        """Load all trade preferences from config and apply them"""
        from config import _load_cfg
        cfg = _load_cfg()
        
        # Load search mode
        if 'trade_search_mode' in cfg:
            self.trade_search_mode.set(cfg['trade_search_mode'])
        
        # Load buy/sell mode
        if 'trade_sell_mode' in cfg:
            self.trade_sell_mode.set(cfg['trade_sell_mode'])
        if 'trade_buy_mode' in cfg:
            self.trade_buy_mode.set(cfg['trade_buy_mode'])
        
        # Load category and update commodity list
        if 'trade_category' in cfg:
            category = cfg['trade_category']
            if category in self._trade_categories:
                self.trade_category.set(category)
                self._update_trade_commodity_list()
        
        # Load commodity
        if 'trade_commodity' in cfg:
            commodity = cfg['trade_commodity']
            # Check if commodity is in current category's list
            current_values = self.trade_commodity_combo['values']
            if commodity in current_values:
                self.trade_commodity.set(commodity)
        
        # Load station type (convert English to localized)
        if 'trade_station_type' in cfg:
            station_type_english = cfg['trade_station_type']
            station_type_localized = self._trade_station_type_map.get(station_type_english, station_type_english)
            if station_type_localized in self._trade_station_type_map.values():
                self.trade_station_type.set(station_type_localized)
        
        # Load checkboxes
        if 'trade_exclude_carriers' in cfg:
            self.trade_exclude_carriers.set(cfg['trade_exclude_carriers'])
        if 'trade_large_pad_only' in cfg:
            self.trade_large_pad_only.set(cfg['trade_large_pad_only'])
        
        # Load order by (convert English to localized)
        if 'trade_order_by' in cfg:
            order_by_english = cfg['trade_order_by']
            order_by_localized = self._trade_sort_options_map.get(order_by_english, order_by_english)
            if order_by_localized in self._trade_sort_options_map.values():
                self.trade_order_by.set(order_by_localized)
        
        # Load max age (convert English to localized)
        if 'trade_max_age' in cfg:
            max_age_english = cfg['trade_max_age']
            max_age_localized = self._trade_age_map.get(max_age_english, max_age_english)
            if max_age_localized in self._trade_age_map.values():
                self.trade_max_age.set(max_age_localized)
    
    def _save_trade_preferences(self):
        """Save all trade preferences to config"""
        from config import update_config_values
        station_type_english = self._trade_station_type_rev_map.get(self.trade_station_type.get(), self.trade_station_type.get())
        order_by_english = self._trade_sort_rev_map.get(self.trade_order_by.get(), self.trade_order_by.get())
        max_age_english = self._trade_age_rev_map.get(self.trade_max_age.get(), self.trade_max_age.get())
        updates = {
            "trade_search_mode": str(self.trade_search_mode.get()),
            "trade_sell_mode": bool(self.trade_sell_mode.get()),
            "trade_buy_mode": bool(self.trade_buy_mode.get()),
            "trade_reference_system": str(self.trade_reference_system.get()),
            "trade_category": str(self.trade_category.get()),
            "trade_commodity": str(self.trade_commodity.get()),
            "trade_station_type": station_type_english,
            "trade_exclude_carriers": bool(self.trade_exclude_carriers.get()),
            "trade_large_pad_only": bool(self.trade_large_pad_only.get()),
            "trade_order_by": order_by_english,
        }
        updates.update(self._market_age_preferences('trade', max_age_english))
        update_config_values(updates)
    
    def _search_trade_market(self):
        """Search for trade commodity prices using same backend as mining commodities"""
        if not hasattr(self, '_trade_search_control'):
            self._trade_search_control = SearchControl(self, self.trade_search_btn, self.trade_total_label)
        control = self._trade_search_control
        if control.running:
            control.stop()
            return
        try:
            self._save_trade_preferences()
            
            commodity = self.trade_commodity.get()
            search_mode = self.trade_search_mode.get()
            
            if not commodity:
                self.trade_total_label.config(text=t('marketplace.select_commodity'))
                return
            
            if search_mode == "near_system":
                ref_system = self.trade_reference_system.get().strip()
                if not ref_system:
                    self.trade_total_label.config(text=t('marketplace.enter_system'))
                    return
            
            reference_system = self.trade_reference_system.get().strip()
            max_age_str = self._trade_age_rev_map.get(self.trade_max_age.get(), self.trade_max_age.get())
            max_days_ago = self._convert_age_to_days(max_age_str)
            is_buy_mode = self.trade_buy_mode.get()
            exclude_carriers = self.trade_exclude_carriers.get()
            trade_station_type_filter = self._trade_station_type_rev_map.get(self.trade_station_type.get(), self.trade_station_type.get())
            exclude_carriers = exclude_carriers and trade_station_type_filter != "Fleet Carrier"
            large_pad_only = self.trade_large_pad_only.get()
            trade_order_by = self._trade_sort_rev_map.get(self.trade_order_by.get(), self.trade_order_by.get())

            max_results = self._galaxy_market_limit('trade') if search_mode == 'galaxy_wide' else None
            order_label = self.trade_order_by.get()

            # Show searching status
            is_buy_mode = self.trade_buy_mode.get()
            if is_buy_mode:
                self.trade_total_label.config(text=t('marketplace.searching_buying'))
            else:
                self.trade_total_label.config(text=t('marketplace.searching_selling'))
            self._next_commodity_pp_generation(self.trade_tree)
            control.start()
            
            # Run search in background thread to prevent UI freeze
            import threading
            def search_thread():
                try:
                    # Call appropriate API based on search mode and buy/sell mode
                    if search_mode == "galaxy_wide":
                        if is_buy_mode:
                            results = MarketplaceAPI.search_sellers_galaxy_wide(commodity, max_days_ago, exclude_carriers, is_cancelled=control.is_cancelled)
                        else:
                            results = MarketplaceAPI.search_buyers_galaxy_wide(commodity, max_days_ago, exclude_carriers, is_cancelled=control.is_cancelled)
                    else:
                        if is_buy_mode:
                            results = MarketplaceAPI.search_sellers(commodity, reference_system, None, max_days_ago, exclude_carriers, is_cancelled=control.is_cancelled)
                        else:
                            results = MarketplaceAPI.search_buyers(commodity, reference_system, None, max_days_ago, exclude_carriers, is_cancelled=control.is_cancelled)
                    
                    # Do heavy filtering/sorting in background thread (keeps UI responsive)
                    original_count = len(results)

                    results = MarketplaceAPI.filter_results(
                        results, trade_station_type_filter, max_age_str, exclude_carriers, large_pad_only, is_buy_mode)
                    matched_count = len(results) if search_mode == 'galaxy_wide' else None
                    if search_mode == 'galaxy_wide':
                        results_sorted = MarketplaceAPI.prepare_galaxy_results(
                            results, trade_order_by, is_buy_mode, max_results, reference_system,
                            is_cancelled=control.is_cancelled,
                            on_distances=lambda: control.progress(t('marketplace.calculating_distances')))
                    else:
                        results_sorted = MarketplaceAPI.sort_results(results, trade_order_by, is_buy_mode)
                    control.complete(results_sorted, self._display_trade_search_results,
                                     search_mode, is_buy_mode, original_count, matched_count, order_label,
                                     commodity, reference_system)
                except Exception as e:
                    log.error(f"trade search failed: {e}")
                    control.failed(str(e))
            
            thread = threading.Thread(target=search_thread, daemon=True)
            thread.start()
            
        except Exception as e:
            log.error(f"Trade search failed: {e}")
            control.failed(str(e))
    
    @staticmethod
    def _found_stations_text(count, is_buy_mode, commodity, reference_system):
        key = 'found_stations_selling' if is_buy_mode else 'found_stations_buying'
        return t('marketplace.' + key).format(count=count, commodity=commodity, system=reference_system)

    def _display_trade_search_results(self, results_sorted: list, search_mode: str, is_buy_mode: bool, original_count: int,
                                      matched_count=None, order_label='', commodity='', reference_system=''):
        """Display pre-filtered/sorted trade results on the main thread (UI only)"""
        control = getattr(self, '_trade_search_control', None)
        enrich_powerplay = not (control and control.is_cancelled())
        self.config(cursor="")
        if not results_sorted:
            self._clear_trade_results()
            if original_count > 0:
                self.trade_total_label.config(text=t('marketplace.no_match_filters').format(count=original_count))
            else:
                self.trade_total_label.config(text=t('marketplace.no_results'))
            return

        self._display_trade_results(results_sorted, enrich_powerplay=enrich_powerplay)
        if search_mode == 'galaxy_wide' and matched_count is not None:
            self.trade_total_label.config(text=t('marketplace.showing_matches').format(
                shown=len(results_sorted), total=matched_count, sort=order_label))
        else:
            self.trade_total_label.config(text=self._found_stations_text(len(results_sorted), is_buy_mode, commodity, reference_system))

    def _create_trade_results_table(self, parent_frame):
        """Create results table for trade commodities - separate from mining table"""
        # Create own table frame
        table_frame = tk.Frame(parent_frame, bg="#1a1a1a")
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Column definitions - same structure as marketplace with LS column
        # _spacer is an always-empty trailing column (never in the visibility menu) that
        # absorbs extra horizontal space, same as Ring Finder's results table - without it
        # the last real column gets force-stretched and its right border isn't draggable.
        columns = ("system", "station", "type", "pad", "distance", "ls", "demand", "price", "powerstate", "updated", "_spacer")

        # Create separate Treeview for trade tab
        self.trade_tree = StripedTreeview(table_frame, columns=columns, show="headings", height=15, style="Marketplace.Treeview")

        # Define headings with sorting
        numeric_columns = {"distance", "ls", "demand", "price", "updated"}
        for col in columns:
            if col == "_spacer":
                self.trade_tree.heading(col, text="", anchor="w")
                continue
            is_numeric = col in numeric_columns
            self.trade_tree.heading(col, text=self._get_column_title(col),
                                    anchor="center" if col in ("pad", "updated") else "w",
                                    command=lambda c=col, n=is_numeric: self._sort_trade_column(c, n))
        
        # Track sort state
        self.trade_sort_column = None
        self.trade_sort_reverse = False
        
        # Set column widths
        # minwidth is derived from the actual rendered header text width (at the
        # scaled heading font) rather than a fixed guess, so headers can never be
        # squeezed below what their own label needs, at any UI scale or language.
        # "demand" header text toggles between Demand/Supply at runtime, so measure
        # both possible strings and take the larger one.
        import tkinter.font as _tkfont
        _heading_font = _tkfont.Font(font=self._scaled_font(9, "bold"))
        _base_widths = {"system": 180, "station": 210, "type": 95, "pad": 45, "distance": 70, "ls": 70,
                        "demand": 75, "price": 125, "powerstate": 150, "updated": 95}
        _header_pad = self._scaled_px(24)  # header cell padding + sort-arrow space

        def _min_for(col_name):
            if col_name == "demand":
                text_width = max(_heading_font.measure(t('marketplace.demand')),
                                  _heading_font.measure(t('marketplace.supply')))
            else:
                header_text = self.trade_tree.heading(col_name, "text")
                text_width = _heading_font.measure(header_text)
            return max(text_width + _header_pad, self._scaled_px(50))

        _minwidths = {col: _min_for(col) for col in _base_widths}

        for col_name, base_width in _base_widths.items():
            self.trade_tree.column(col_name, width=max(self._scaled_px(base_width), _minwidths[col_name]),
                                   minwidth=_minwidths[col_name], anchor="center" if col_name in ("pad", "updated") else "w", stretch=False)

        # Spacer column - always last, gives every real column a draggable right border and
        # absorbs extra width instead of force-stretching the last real column.
        self.trade_tree.column("_spacer", width=self._scaled_px(20), minwidth=self._scaled_px(20), anchor="w", stretch=True)

        # Setup column visibility for trade commodities (exclude _spacer from the menu)
        self.setup_column_visibility(
            tree=self.trade_tree,
            columns=tuple(c for c in columns if c != "_spacer"),
            default_widths={col: max(self._scaled_px(w), _minwidths[col]) for col, w in _base_widths.items()},
            config_key='trade_commodities',
            allow_reorder=True,
            use_displaycolumns=True
        )
        self._cv_split_saved_column('trade_commodities', 'location', ('system', 'station'))

        # Load saved column widths from config — but never let an old (pre-scale)
        # saved width sit below the current scaled minwidth, or headers get squeezed.
        try:
            from config import load_trade_commodities_column_widths
            saved_widths = load_trade_commodities_column_widths()
            if saved_widths:
                for col_name, width in saved_widths.items():
                    try:
                        current_minwidth = self.trade_tree.column(col_name, "minwidth")
                        self.trade_tree.column(col_name, width=max(width, current_minwidth))
                    except:
                        pass
        except Exception as e:
            print(f"[DEBUG] Could not load Trade Commodities column widths: {e}")

        # Bind column resize event to save widths
        def save_trade_widths(event=None):
            try:
                from config import save_trade_commodities_column_widths
                widths = {}
                for col in columns:
                    try:
                        widths[col] = self.trade_tree.column(col, "width")
                    except:
                        pass
                save_trade_commodities_column_widths(widths)
            except Exception as e:
                print(f"[DEBUG] Could not save Trade Commodities column widths: {e}")
        
        self.trade_tree.bind("<ButtonRelease-1>", save_trade_widths)
        # Double-click the Powerplay cell to open Inara and fetch/refresh its data
        self.trade_tree.bind("<Double-1>", lambda e: self._on_commodity_tree_double_click(e, self.trade_tree))
        self._trade_row_source = {}
        from ui.cell_tooltip import attach_cell_tooltip
        attach_cell_tooltip(self.trade_tree, "updated", lambda item: self._trade_row_source.get(item, ''))

        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.trade_tree.yview)
        self.trade_tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.trade_tree.xview)
        self.trade_tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure row tags for alternating colors (theme-aware, matches Ring Finder)
        if self.current_theme == "elite_orange":
            self.trade_tree.tag_configure('oddrow', background='#1e1e1e', foreground='#ff8c00')
            self.trade_tree.tag_configure('evenrow', background='#252525', foreground='#ff8c00')
        else:
            self.trade_tree.tag_configure('oddrow', background='#1e1e1e', foreground='#e6e6e6')
            self.trade_tree.tag_configure('evenrow', background='#282828', foreground='#e6e6e6')
        
        # Grid layout for treeview and scrollbars (like Mining Commodities)
        self.trade_tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        # Add right-click context menu
        self._create_trade_context_menu()
        # Register context menu handler for trade commodities
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers['trade_commodities'] = self._show_trade_context_menu
        # Note: Right-click binding handled by column visibility mixin
    
    def _sort_trade_column(self, col: str, is_numeric: bool):
        """Sort trade results table by column"""
        # Toggle sort direction
        if self.trade_sort_column == col:
            self.trade_sort_reverse = not self.trade_sort_reverse
        else:
            self.trade_sort_column = col
            self.trade_sort_reverse = False
        
        # Get all items
        items = [(self.trade_tree.set(item, col), item) for item in self.trade_tree.get_children('')]
        
        # Sort items
        if is_numeric:
            def parse_value(val):
                try:
                    # Handle "?" or "-" for unknown values
                    val = val.strip()
                    if val in ('?', '-', ''):
                        return 999999
                    # Handle time-based values (e.g., "30m", "1h", "2d")
                    if val.endswith('m'):
                        return float(val[:-1])
                    elif val.endswith('h'):
                        return float(val[:-1]) * 60
                    elif val.endswith('d'):
                        return float(val[:-1]) * 1440
                    # Remove " CR", " LY", commas, spaces
                    val = val.replace(' CR', '').replace(' LY', '').replace(',', '').strip()
                    return float(val) if val else 999999
                except:
                    return 999999
            items.sort(key=lambda x: parse_value(x[0]), reverse=self.trade_sort_reverse)
        else:
            items.sort(key=lambda x: x[0].lower(), reverse=self.trade_sort_reverse)
        
        # Rearrange items
        for index, (val, item) in enumerate(items):
            self.trade_tree.move(item, '', index)

        from ui.sort_indicator import apply_sort_arrow
        apply_sort_arrow(self.trade_tree, col, self.trade_sort_reverse)

    def _display_trade_results(self, results: list, enrich_powerplay=True):
        """Display trade search results in trade table"""
        # Clear existing results
        self.trade_tree.delete(*self.trade_tree.get_children())
        self._trade_row_source = {}
        self.trade_sort_column = None
        self.trade_sort_reverse = False
        from ui.sort_indicator import apply_sort_arrow
        apply_sort_arrow(self.trade_tree, None, False)
        if hasattr(self, 'trade_avg_label'):
            self.trade_avg_label.config(text="")
        if hasattr(self, 'trade_best_label'):
            self.trade_best_label.config(text="")

        # Compute average and best price across all results
        if results and hasattr(self, 'trade_avg_label'):
            is_buy_mode = self.trade_buy_mode.get()
            price_field = 'buyPrice' if is_buy_mode else 'sellPrice'
            prices = [r.get(price_field, 0) for r in results if r.get(price_field, 0) > 0]
            if prices:
                avg = sum(prices) // len(prices)
                self.trade_avg_label.config(text=t('marketplace.avg_price').format(price=f'{avg:,}'))
                best = min(prices) if is_buy_mode else max(prices)
                key = 'marketplace.best_buy_price' if is_buy_mode else 'marketplace.best_sell_price'
                self.trade_best_label.config(text=t(key).format(price=f'{best:,}'))

        # Determine mode for correct field handling
        is_buy_mode = self.trade_buy_mode.get()

        # Bulk-fetch PowerPlay data from the local EDDN cache for all result systems in one
        # query - local-only, no Spansh/Inara calls.
        from system_finder_api import SystemFinderAPI
        _trade_pp_names = list({r.get('systemName', '') for r in results if r.get('systemName')})
        _trade_pp_data = SystemFinderAPI._batch_get_powerplay(_trade_pp_names) if _trade_pp_names else {}

        from app_utils import format_market_station_type, format_market_pad, format_relative_age, format_market_powerplay, format_market_source

        # Display results
        for row_index, result in enumerate(results):
            system_name = result.get('systemName', 'Unknown')
            station_name = result.get('stationName', 'Unknown')
            station_type = format_market_station_type(result.get('stationType'))
            pad = format_market_pad(result.get('maxLandingPadSize'))

            # DISTANCE
            if 'distance' in result and result['distance'] is not None:
                distance = f"{result['distance']:.1f}"
            else:
                distance = "-"
            
            # LS (Station distance from star)
            station_ls = result.get('distanceToArrival')
            if station_ls is not None:
                # 0 is valid for fleet carriers at arrival point
                ls = f"{int(float(station_ls)):,}"
            else:
                ls = "?"
            
            # DEMAND/STOCK
            if is_buy_mode:
                volume = f"{result.get('stock', 0):,}" if result.get('stock', 0) > 0 else "0"
            else:
                volume = f"{result.get('demand', 0):,}" if result.get('demand', 0) > 0 else "0"
            
            # PRICE
            if is_buy_mode:
                price = f"{result.get('buyPrice', 0):,}"
            else:
                price = f"{result.get('sellPrice', 0):,}"
            
            updated = format_relative_age(result.get('updatedAt')) or '?'
            powerstate = format_market_powerplay(_trade_pp_data.get(result.get('systemName', ''), {}))

            # Insert row with alternating row tag
            row_tag = 'oddrow' if row_index % 2 == 0 else 'evenrow'
            row_id = self.trade_tree.insert('', 'end', values=(
                f" {system_name} ",
                f" {station_name} ",
                f" {station_type} ",
                f" {pad} ",
                f" {distance} ",
                f" {ls} ",
                f" {volume} ",
                f" {price} ",
                f" {powerstate} ",
                f" {updated} ",
                ""
            ), tags=(row_tag,))
            self._trade_row_source[row_id] = format_market_source(result)

        # Backfill/refresh PowerPlay from Spansh's own Exploited/Fortified/Stronghold/Unoccupied
        # data - queried for every result system, not just ones missing from the EDDN cache,
        # so a stale cached entry gets replaced whenever Spansh's is newer (mirrors Ring
        # Finder/Star Systems' updated_at comparison).
        if _trade_pp_names and enrich_powerplay:
            self._start_commodity_pp_backfill(self.trade_tree, _trade_pp_names, _trade_pp_data)

    def _clear_trade_results(self):
        """Clear trade results table"""
        if hasattr(self, 'trade_tree'):
            self.trade_tree.delete(*self.trade_tree.get_children())
            self._trade_row_source = {}
        if hasattr(self, 'trade_avg_label'):
            self.trade_avg_label.config(text="")
        if hasattr(self, 'trade_best_label'):
            self.trade_best_label.config(text="")
    
    def _search_marketplace(self):
        """Search for commodity prices using Ardent API (threaded to prevent UI freeze)"""
        if not hasattr(self, '_marketplace_search_control'):
            self._marketplace_search_control = SearchControl(self, self.marketplace_search_btn, self.marketplace_total_label)
        control = self._marketplace_search_control
        if control.running:
            control.stop()
            return
        try:
            # Save current search parameters
            self._save_marketplace_preferences()
            
            # Convert localized commodity name to English for API
            commodity_display = self.marketplace_commodity.get()
            commodity = self._commodity_rev_map.get(commodity_display, commodity_display)
            search_mode = self.marketplace_search_mode.get()
            
            # Validation
            if not commodity:
                self.marketplace_total_label.config(text=t('marketplace.select_commodity'))
                return
            
            # Mode-specific validation
            reference_system = ""
            if search_mode == "near_system":
                reference_system = self.marketplace_reference_system.get().strip()
                if not reference_system:
                    self.marketplace_total_label.config(text=t('marketplace.enter_reference_system'))
                    return
            
            # Convert max age to days
            max_age_str = self._age_rev_map.get(self.marketplace_max_age.get(), self.marketplace_max_age.get())
            
            # Determine buy/sell mode
            is_buy_mode = self.marketplace_buy_mode.get()
            
            # Get exclude carriers setting
            exclude_carriers = self.marketplace_exclude_carriers.get()
            
            # Capture all filter state upfront (main thread)
            station_type_filter = self._station_type_rev_map.get(self.marketplace_station_type.get(), self.marketplace_station_type.get())
            exclude_carriers = exclude_carriers and station_type_filter != "Fleet Carrier"
            large_pad_only = self.marketplace_large_pad_only.get()
            order_by = self._sort_rev_map.get(self.marketplace_order_by.get(), self.marketplace_order_by.get())
            
            max_results = self._galaxy_market_limit('marketplace') if search_mode == 'galaxy_wide' else None
            order_label = self.marketplace_order_by.get()

            distance_reference = reference_system or self.marketplace_reference_system.get().strip()

            # Show searching status
            if is_buy_mode:
                self.marketplace_total_label.config(text=t('marketplace.searching_buying'))
            else:
                self.marketplace_total_label.config(text=t('marketplace.searching_selling'))
            self._next_commodity_pp_generation(self.marketplace_tree)
            control.start()
            
            # Run search in background thread to prevent UI freeze
            import threading
            def search_thread():
                try:
                    # Request only the needed day window (the 1000-row cap hides fresh rows otherwise); hour-level filtering stays local
                    api_days = MarketplaceAPI.convert_age_to_days(max_age_str)
                    
                    if search_mode == "galaxy_wide":
                        if is_buy_mode:
                            results = MarketplaceAPI.search_sellers_galaxy_wide(commodity, api_days, exclude_carriers, is_cancelled=control.is_cancelled)
                        else:
                            results = MarketplaceAPI.search_buyers_galaxy_wide(commodity, api_days, exclude_carriers, is_cancelled=control.is_cancelled)
                    else:
                        if is_buy_mode:
                            results = MarketplaceAPI.search_sellers(commodity, reference_system, None, api_days, exclude_carriers, is_cancelled=control.is_cancelled)
                        else:
                            results = MarketplaceAPI.search_buyers(commodity, reference_system, None, api_days, exclude_carriers, is_cancelled=control.is_cancelled)
                    
                    # Do heavy filtering/sorting in background thread (keeps UI responsive)
                    original_count = len(results)

                    results = MarketplaceAPI.filter_results(
                        results, station_type_filter, max_age_str, exclude_carriers, large_pad_only, is_buy_mode)
                    matched_count = len(results) if search_mode == 'galaxy_wide' else None
                    if search_mode == 'galaxy_wide':
                        results_sorted = MarketplaceAPI.prepare_galaxy_results(
                            results, order_by, is_buy_mode, max_results, distance_reference,
                            is_cancelled=control.is_cancelled,
                            on_distances=lambda: control.progress(t('marketplace.calculating_distances')))
                    else:
                        results_sorted = MarketplaceAPI.sort_results(results, order_by, is_buy_mode)
                    control.complete(results_sorted, self._display_marketplace_search_results,
                                     search_mode, reference_system, is_buy_mode, exclude_carriers, original_count, matched_count, order_label,
                                     commodity_display)
                except Exception as e:
                    log.error(f"marketplace search failed: {e}")
                    control.failed(str(e))
            
            thread = threading.Thread(target=search_thread, daemon=True)
            thread.start()
                
        except Exception as e:
            control.failed(str(e))

    def _display_marketplace_search_results(self, results_sorted: list, search_mode: str, reference_system: str,
                                             is_buy_mode: bool, exclude_carriers: bool, original_count: int,
                                             matched_count=None, order_label='', commodity=''):
        """Display pre-filtered/sorted marketplace results on the main thread (UI only)"""
        control = getattr(self, '_marketplace_search_control', None)
        enrich_powerplay = not (control and control.is_cancelled())
        self.config(cursor="")
        if not results_sorted:
            self._clear_marketplace_results()
            if original_count > 0:
                if exclude_carriers:
                    self.marketplace_total_label.config(text=t('marketplace.all_fleet_carriers').format(count=original_count))
                else:
                    self.marketplace_total_label.config(text=t('marketplace.no_match_filters').format(count=original_count))
            else:
                self.marketplace_total_label.config(text=t('marketplace.no_results'))
            return

        self._display_marketplace_results(results_sorted, enrich_powerplay=enrich_powerplay)
        if search_mode == 'galaxy_wide' and matched_count is not None:
            self.marketplace_total_label.config(text=t('marketplace.showing_matches').format(
                shown=len(results_sorted), total=matched_count, sort=order_label))
        else:
            self.marketplace_total_label.config(text=self._found_stations_text(len(results_sorted), is_buy_mode, commodity, reference_system))

    def _on_commodity_tree_double_click(self, event, tree, refresh_powerplay=True):
        """Open Inara from a System, Station or Powerplay cell, refreshing Powerplay when supported."""
        if tree.identify_region(event.x, event.y) != "cell":
            return
        item = tree.identify_row(event.y)
        if not item:
            return
        col_name = displayed_column(tree, tree.identify_column(event.x))
        if col_name not in ("system", "station", "powerstate"):
            return

        system_name = self._row_system_station(tree, item)[0]
        if not system_name:
            return

        import urllib.parse
        import webbrowser
        webbrowser.open(f"https://inara.cz/elite/starsystem/?search={urllib.parse.quote(system_name)}")

        tree.selection_set(item)
        if not refresh_powerplay:
            return
        label = self.marketplace_total_label if tree is self.marketplace_tree else self.trade_total_label
        label.config(text=t('ring_finder.fetching_pp').format(system=system_name))
        threading.Thread(target=self._fetch_commodity_pp_worker, args=(system_name, tree), daemon=True).start()

    def _fetch_commodity_pp_worker(self, system_name, tree):
        """Background fetch of a single system's Powerplay data from Inara for a Commodity
        Market results tree, then update every matching row on the main thread."""
        from system_finder_api import SystemFinderAPI
        result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system_name)
        self.after(0, lambda: self._fetch_commodity_pp_complete(system_name, result, tree))

    def _fetch_commodity_pp_complete(self, system_name, result, tree):
        """Update Powerplay cell(s) for system_name in the given tree with fetched data."""
        label = self.marketplace_total_label if tree is self.marketplace_tree else self.trade_total_label
        if result:
            from app_utils import format_market_powerplay
            pp_power = result.get('controlling_power', '')
            pp_str = format_market_powerplay(result, include_age=True)

            columns = tree['columns']
            pp_col_index = columns.index('powerstate')
            for item in tree.get_children():
                vals = list(tree.item(item, 'values'))
                if not vals:
                    continue
                row_system = str(vals[0]).strip()
                if row_system == system_name and len(vals) > pp_col_index:
                    vals[pp_col_index] = f" {pp_str} "
                    tree.item(item, values=vals)

            if pp_power == '~none~':
                label.config(text=t('ring_finder.pp_fetch_no_power').format(system=system_name))
            else:
                label.config(text=t('ring_finder.pp_fetch_success').format(system=system_name, power=pp_str))
        else:
            label.config(text=t('ring_finder.pp_fetch_none').format(system=system_name))

    def _next_commodity_pp_generation(self, tree):
        """Advance the Powerplay fill-in generation for tree; older fill-ins on it then stop."""
        generations = self.__dict__.setdefault('_commodity_pp_generations', {})
        key = str(tree)
        generations[key] = generations.get(key, 0) + 1
        return generations[key]

    def _commodity_pp_generation_current(self, tree, generation):
        return self.__dict__.get('_commodity_pp_generations', {}).get(str(tree)) == generation

    def _start_commodity_pp_backfill(self, tree, system_names, cached_pp_data):
        generation = self._next_commodity_pp_generation(tree)
        threading.Thread(target=self._backfill_commodity_pp_worker,
                         args=(system_names, cached_pp_data, tree, generation), daemon=True).start()

    def _backfill_commodity_pp_worker(self, system_names, cached_pp_data, tree, generation):
        """Background lookup of Spansh's own Exploited/Fortified/Stronghold/Unoccupied
        PowerPlay data for every result system, then update rows on the main thread wherever
        Spansh's data should replace what the EDDN cache already had (same comparison Ring
        Finder/Star Systems use - newer updated_at, or filling a blank controlling_power)."""
        from system_finder_api import SystemFinderAPI
        is_cancelled = lambda: not self._commodity_pp_generation_current(tree, generation)
        spansh_pp = SystemFinderAPI._fetch_spansh_powerplay_for_named_systems(
            system_names, is_cancelled=is_cancelled)
        newer_pp = {}
        for sys_name, entry in spansh_pp.items():
            cached = cached_pp_data.get(sys_name)
            if SystemFinderAPI._spansh_pp_should_replace_cache(entry, cached):
                newer_pp[sys_name] = entry
        if newer_pp:
            SystemFinderAPI._store_powerplay_batch(newer_pp)
        if is_cancelled():
            log.info("[POWERPLAY] Commodity Market Powerplay fill-in stopped: a newer search started")
            return
        self.after(0, lambda: self._backfill_commodity_pp_complete(newer_pp, tree, generation))

    def _backfill_commodity_pp_complete(self, pp_data, tree, generation):
        """Update Powerplay cell(s) for every system in pp_data with Spansh-backfilled data."""
        if not pp_data or not self._commodity_pp_generation_current(tree, generation):
            return
        columns = tree['columns']
        pp_col_index = columns.index('powerstate')
        for item in tree.get_children():
            vals = list(tree.item(item, 'values'))
            if not vals or len(vals) <= pp_col_index:
                continue
            entry = pp_data.get(str(vals[0]).strip())
            if not entry:
                continue
            from app_utils import format_market_powerplay
            pp_str = format_market_powerplay(entry)
            vals[pp_col_index] = f" {pp_str} "
            tree.item(item, values=vals)

    def _clear_marketplace_results(self):
        """Clear marketplace results tree"""
        self.marketplace_tree.delete(*self.marketplace_tree.get_children())
        self._marketplace_row_source = {}
        if hasattr(self, 'marketplace_avg_label'):
            self.marketplace_avg_label.config(text="")
        if hasattr(self, 'marketplace_best_label'):
            self.marketplace_best_label.config(text="")
    
    def _display_marketplace_results(self, results, enrich_powerplay=True):
        """Display marketplace results (already sorted by user's selected criteria)"""
        self._clear_marketplace_results()

        # Results are already sorted by the search function based on user's "Sort by" selection
        # DO NOT re-sort here - just display them as provided

        # Compute average and best price across all results
        if results and hasattr(self, 'marketplace_avg_label'):
            is_buy_mode = self.marketplace_buy_mode.get()
            price_field = 'buyPrice' if is_buy_mode else 'sellPrice'
            prices = [r.get(price_field, 0) for r in results if r.get(price_field, 0) > 0]
            if prices:
                avg = sum(prices) // len(prices)
                self.marketplace_avg_label.config(text=t('marketplace.avg_price').format(price=f'{avg:,}'))
                best = min(prices) if is_buy_mode else max(prices)
                key = 'marketplace.best_buy_price' if is_buy_mode else 'marketplace.best_sell_price'
                self.marketplace_best_label.config(text=t(key).format(price=f'{best:,}'))
            else:
                self.marketplace_avg_label.config(text="")
                self.marketplace_best_label.config(text="")
        
        commodity = self.marketplace_commodity.get()
        self._populate_marketplace_results(results, commodity, enrich_powerplay=enrich_powerplay)
    
    def _populate_marketplace_results(self, results, commodity, enrich_powerplay=True):
        """Populate marketplace results in UI"""
        try:
            # Determine mode for correct field handling
            is_buy_mode = self.marketplace_buy_mode.get()
            self._marketplace_row_source = {}
            self.marketplace_sort_column = None
            self.marketplace_sort_reverse = False
            from ui.sort_indicator import apply_sort_arrow
            apply_sort_arrow(self.marketplace_tree, None, False)

            # Bulk-fetch PowerPlay data from the local EDDN cache for all result systems in one
            # query - local-only, no Spansh/Inara calls (unlike Ring Finder's PowerPlay column).
            from system_finder_api import SystemFinderAPI
            _pp_system_names = list({r.get('systemName', '') for r in results if r.get('systemName')})
            _pp_data = SystemFinderAPI._batch_get_powerplay(_pp_system_names) if _pp_system_names else {}

            from app_utils import format_market_station_type, format_market_pad, format_relative_age, format_market_powerplay, format_market_source

            # Populate results (sorted by distance - closest first)
            for row_index, result in enumerate(results):
                system_name = result['systemName']
                station_name = result['stationName']
                station_type = format_market_station_type(result.get('stationType'))
                pad = format_market_pad(result.get('maxLandingPadSize'))

                # DISTANCE (System distance) - calculate for both modes
                if result.get('distance') is not None:
                    distance = f"{result['distance']:.1f}"
                else:
                    distance = "-"  # No distance available
                
                # LS (Station distance from star) - from distanceToArrival field
                station_ls = result.get('distanceToArrival')
                if station_ls is not None:
                    # 0 is valid for fleet carriers at arrival point
                    ls = f"{int(float(station_ls)):,}"
                else:
                    ls = "?"
                
                # DEMAND/STOCK - depends on mode
                if is_buy_mode:
                    # Buy mode (exports endpoint): use 'stock' field
                    volume = f"{result.get('stock', 0):,}" if result.get('stock', 0) > 0 else "0"
                else:
                    # Sell mode (imports endpoint): use 'demand' field
                    volume = f"{result.get('demand', 0):,}" if result.get('demand', 0) > 0 else "0"
                
                # PRICE - depends on mode
                # NOTE: Ardent API exports endpoint has price in 'buyPrice' field (backwards naming!)
                if is_buy_mode:
                    # Buy mode (exports endpoint): Use 'buyPrice' (what YOU pay to buy FROM them)
                    # API has backwards field naming - sellPrice is 0, actual price is in buyPrice
                    price = f"{result.get('buyPrice', 0):,}"
                else:
                    # Sell mode (imports endpoint): Use 'sellPrice' (what YOU get when selling TO them)
                    price = f"{result.get('sellPrice', 0):,}"
                
                updated = format_relative_age(result.get('updatedAt')) or '?'
                powerstate = format_market_powerplay(_pp_data.get(result.get('systemName', ''), {}))

                # Insert with alternating row tags for visual separation
                tag = 'evenrow' if row_index % 2 == 0 else 'oddrow'

                # Add subtle visual separator using spacing
                row_id = self.marketplace_tree.insert("", "end", values=(
                    f" {system_name} ",
                    f" {station_name} ",
                    f" {station_type} ",
                    f" {pad} ",
                    f" {distance} ",
                    f" {ls} ",
                    f" {volume} ",
                    f" {price} ",
                    f" {powerstate} ",
                    f" {updated} ",
                    ""
                ), tags=(tag,))
                self._marketplace_row_source[row_id] = format_market_source(result)

            # Backfill/refresh PowerPlay from Spansh's own Exploited/Fortified/Stronghold/
            # Unoccupied data - queried for every result system, not just ones missing from
            # the EDDN cache, so a stale cached entry gets replaced whenever Spansh's is newer
            # (mirrors Ring Finder/Star Systems' updated_at comparison).
            if _pp_system_names and enrich_powerplay:
                self._start_commodity_pp_backfill(self.marketplace_tree, _pp_system_names, _pp_data)
            
        except Exception as e:
            self.marketplace_total_label.config(text=t('marketplace.display_error').format(error=e))
            log.error(f"Error populating results: {e}")

    def _show_marketplace_context_menu(self, event):
        """Show the context menu when right-clicking on marketplace results"""
        try:
            # Select the item under cursor
            item = self.marketplace_tree.identify_row(event.y)
            if item:
                self.marketplace_tree.selection_set(item)
                self.marketplace_tree.focus(item)
                self.marketplace_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.marketplace_context_menu.grab_release()

    def _sort_marketplace_column(self, column, numeric):
        """Sort marketplace results by column"""
        try:
            # Get all items from the tree
            items = [(self.marketplace_tree.item(item, 'values'), item) for item in self.marketplace_tree.get_children()]
            
            if not items:
                return
            
            # Check if we're clicking the same column
            if self.marketplace_sort_column == column:
                # Reverse the sort direction
                self.marketplace_sort_reverse = not self.marketplace_sort_reverse
            else:
                # New column, start with ascending
                self.marketplace_sort_column = column
                self.marketplace_sort_reverse = False
            
            # Get column index - column IDs, not display names (must match the treeview's
            # actual column order, including the trailing _spacer)
            column_ids = ("system", "station", "type", "pad", "distance", "ls", "demand", "price", "powerstate", "updated", "_spacer")

            # Map display names to column IDs
            display_to_id = {
                "Station Type": "type",
                "Pad": "pad",
                "Distance": "distance",
                "LS": "ls",
                "Demand": "demand",
                "Price": "price",
                "Updated": "updated",
                "Powerplay": "powerstate"
            }
            
            # Get the column ID from display name
            col_id = display_to_id.get(column, column)
            col_index = column_ids.index(col_id)
            
            # Define sort function based on column type
            if numeric:
                def sort_key(item):
                    value = item[0][col_index].strip()
                    try:
                        if value in ('?', '-', ''):
                            return 999999999
                        if col_id == "updated":
                            if value.endswith('m'):
                                return float(value[:-1])
                            if value.endswith('h'):
                                return float(value[:-1]) * 60
                            if value.endswith('d'):
                                return float(value[:-1]) * 1440
                            return 999999999
                        return float(value.replace(" LY", "").replace(" CR", "").replace(",", ""))
                    except ValueError:
                        return 999999999
            else:
                def sort_key(item):
                    # String sorting
                    return item[0][col_index].lower()
            
            # Sort items
            items.sort(key=sort_key, reverse=self.marketplace_sort_reverse)
            
            # Clear tree and re-insert sorted items, re-applying row tags
            for values, item in items:
                self.marketplace_tree.move(item, '', 'end')
            
            from ui.sort_indicator import apply_sort_arrow
            apply_sort_arrow(self.marketplace_tree, col_id, self.marketplace_sort_reverse)

        except Exception as e:
            log.error(f"Error sorting marketplace column: {e}")
            self.marketplace_total_label.config(text=t('marketplace.sort_error').format(error=e))
