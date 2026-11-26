"""Star Systems tab (moved from main.py)."""

import logging
import threading
import tkinter as tk
from tkinter import ttk

from app_utils import create_action_button
from localization import t
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from ui.theme import modern_color
from ui.tooltip import ToolTip


class StarSystemsTabMixin:
    def _build_system_finder_tab(self, frame: ttk.Frame) -> None:
        """Build the System Finder tab - search nearby systems by criteria"""
        from system_finder_api import (
            SECURITY_OPTIONS, ALLEGIANCE_OPTIONS, GOVERNMENT_OPTIONS,
            STATE_OPTIONS, ECONOMY_OPTIONS, POPULATION_OPTIONS,
            MATERIAL_TRADER_OPTIONS, ELITE_POWERS,
            POWER_FILTER_OPTIONS, PP_STATE_OPTIONS
        )
        from config import load_theme
        
        self._sysfinder_option_values = {}
        def localized_options(options):
            labels = [self._sysfinder_option_label(value) for value in options]
            self._sysfinder_option_values.update(zip(labels, options))
            return labels

        # Get theme colors
        sf_theme = load_theme()
        if sf_theme == "elite_orange":
            sf_bg = "#0a0a0a"
            sf_menu_bg = "#1e1e1e"
            sf_menu_fg = "#ff8c00"
            sf_menu_active_bg = "#ff6600"
            sf_menu_active_fg = "#000000"
        else:
            sf_bg = "#1e1e1e"
            sf_menu_bg = "#2d2d2d"
            sf_menu_fg = "#e0e0e0"
            sf_menu_active_bg = "#3a3a3a"
            sf_menu_active_fg = "#ffffff"
        
        # Main container
        main_container = ttk.Frame(frame)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Search section
        search_frame = ttk.LabelFrame(main_container, padding=10)
        search_frame.pack(fill="x", pady=(0, 0) if sf_theme in ("modern", "modern_slate", "modern_orange") else (0, 10))
        from ui.help_link import create_labelframe_title, create_help_link
        search_frame.configure(labelwidget=create_labelframe_title(
            search_frame, t('system_finder.title'), "star-systems", t('system_finder.help_tooltip'), ToolTip))

        # Configure grid weights
        for i in range(4):
            search_frame.columnconfigure(i, weight=1)
        
        # Row 0: Reference system, Use Current System button, and Search button
        row = 0
        ttk.Label(search_frame, text=t('system_finder.reference_system') + ":").grid(
            row=row, column=0, sticky="w", padx=(0, 5), pady=3)
        
        # Frame to hold entry, buttons side by side
        ref_frame = ttk.Frame(search_frame)
        ref_frame.grid(row=row, column=1, columnspan=3, sticky="ew", padx=5, pady=3)
        
        self.sysfinder_reference_system = tk.StringVar()
        self.sysfinder_ref_entry = ttk.Entry(
            ref_frame, textvariable=self.sysfinder_reference_system, width=30
        )
        self.sysfinder_ref_entry.pack(side="left")
        # Autocomplete
        from system_autocomplete import SystemAutocomplete
        self._ac_sysfinder_ref = SystemAutocomplete(self.sysfinder_ref_entry, self.sysfinder_reference_system, self,
                                                     on_select=self._confirm_sysfinder_reference)
        self.sysfinder_ref_entry.bind("<Return>", lambda e: (self._ac_sysfinder_ref.hide(), self._search_systems()))
        
        # Use Current System button - right next to entry (like ring finder)
        self.sysfinder_use_current_btn = create_action_button(
            ref_frame, text=t('ring_finder.use_current_system'),
            command=self._use_current_system_sysfinder,
            bg="#4a3a2a", fg="#e0e0e0",
            activebackground="#5a4a3a", activeforeground="#ffffff",
            relief="ridge", bd=1, cursor="hand2"
        )
        self.sysfinder_use_current_btn.pack(side="left", padx=(5, 0))
        
        # Search button - moved to Row 0 for faster access
        self.sysfinder_search_btn = create_action_button(
            ref_frame, primary=True, text=t('system_finder.search'),
            command=self._search_systems,
            bg="#2a4a2a", fg="#e0e0e0",
            activebackground="#3a5a3a", activeforeground="#ffffff",
            relief="ridge", bd=1, cursor="hand2"
        )
        self.sysfinder_search_btn.pack(side="left", padx=(10, 0))

        # Spansh status indicator - to the right of Search button
        self.sysfinder_spansh_status_label = tk.Label(
            ref_frame, text=t('system_finder.service_checking').format(service='Spansh'),
            font=self._scaled_font(8), fg="#888888",
            bg=ttk.Style().lookup('TFrame', 'background')
        )
        if self.current_theme not in ("modern", "modern_slate", "modern_orange"):
            self.sysfinder_spansh_status_label.pack(side="right", padx=(0, 8))

        # EDDN status indicator - to the left of Spansh
        self.sysfinder_eddn_status_label = tk.Label(
            ref_frame, text=t('system_finder.service_checking').format(service='EDDN'),
            font=self._scaled_font(8), fg="#888888",
            bg=ttk.Style().lookup('TFrame', 'background')
        )
        if self.current_theme not in ("modern", "modern_slate", "modern_orange"):
            self.sysfinder_eddn_status_label.pack(side="right", padx=(0, 4))
        
        # Row 1: Allegiance and Population
        row = 1
        ttk.Label(search_frame, text=t('system_finder.allegiance') + ":").grid(
            row=row, column=0, sticky="w", padx=(0, 5), pady=3)
        
        self.sysfinder_allegiance = tk.StringVar(value=self._sysfinder_option_label("Any"))
        allegiance_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_allegiance,
            values=localized_options(ALLEGIANCE_OPTIONS), width=15, state="readonly"
        )
        allegiance_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(search_frame, text=t('system_finder.population') + ":").grid(
            row=row, column=2, sticky="w", padx=(15, 5), pady=3)
        
        self.sysfinder_population = tk.StringVar(value=self._sysfinder_option_label("Any"))
        pop_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_population,
            values=localized_options(POPULATION_OPTIONS), width=22, state="readonly"
        )
        pop_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        
        # Row 2: Government and Security
        row = 2
        ttk.Label(search_frame, text=t('system_finder.government') + ":").grid(
            row=row, column=0, sticky="w", padx=(0, 5), pady=3)
        
        self.sysfinder_government = tk.StringVar(value=self._sysfinder_option_label("Any"))
        gov_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_government,
            values=localized_options(GOVERNMENT_OPTIONS), width=15, state="readonly"
        )
        gov_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(search_frame, text=t('system_finder.security') + ":").grid(
            row=row, column=2, sticky="w", padx=(15, 5), pady=3)
        
        self.sysfinder_security = tk.StringVar(value=self._sysfinder_option_label("Any"))
        security_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_security,
            values=localized_options(SECURITY_OPTIONS), width=22, state="readonly"
        )
        security_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        
        # Row 3: Economy and State
        row = 3
        ttk.Label(search_frame, text=t('system_finder.economy') + ":").grid(
            row=row, column=0, sticky="w", padx=(0, 5), pady=3)
        
        self.sysfinder_economy = tk.StringVar(value=self._sysfinder_option_label("Any"))
        economy_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_economy,
            values=localized_options(ECONOMY_OPTIONS), width=15, state="readonly"
        )
        economy_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        
        ttk.Label(search_frame, text=t('system_finder.state') + ":").grid(
            row=row, column=2, sticky="w", padx=(15, 5), pady=3)
        
        self.sysfinder_state = tk.StringVar(value=self._sysfinder_option_label("Any"))
        state_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_state,
            values=localized_options(STATE_OPTIONS), width=18, state="readonly"
        )
        state_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        
        # Row 4: Power and PP State filters
        row = 4
        ttk.Label(search_frame, text=t('system_finder.pp_power') + ":").grid(
            row=row, column=0, sticky="w", padx=(0, 5), pady=3)

        self.sysfinder_power = tk.StringVar(value=self._sysfinder_option_label("Any"))
        power_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_power,
            values=localized_options(POWER_FILTER_OPTIONS), width=22, state="readonly"
        )
        power_combo.grid(row=row, column=1, sticky="w", padx=5, pady=3)
        power_combo.bind("<<ComboboxSelected>>", lambda e: power_combo.selection_clear())
        ToolTip(power_combo, t('system_finder.pp_power_tooltip'))

        ttk.Label(search_frame, text=t('system_finder.pp_state') + ":").grid(
            row=row, column=2, sticky="w", padx=(15, 5), pady=3)

        self.sysfinder_pp_state = tk.StringVar(value=self._sysfinder_option_label("Any"))
        pp_state_combo = ttk.Combobox(
            search_frame, textvariable=self.sysfinder_pp_state,
            values=localized_options(PP_STATE_OPTIONS), width=18, state="readonly"
        )
        pp_state_combo.grid(row=row, column=3, sticky="w", padx=5, pady=3)
        pp_state_combo.bind("<<ComboboxSelected>>", lambda e: pp_state_combo.selection_clear())
        ToolTip(pp_state_combo, t('system_finder.pp_state_tooltip'))

        # Row 5: Reference system info display
        row = 5
        ref_info_frame = tk.Frame(search_frame, bg=sf_bg)
        ref_info_frame.grid(row=row, column=0, columnspan=4, pady=(8, 3), sticky="ew")
        
        # Store background color for later updates
        self._sysfinder_ref_bg = sf_bg
        
        # Reference system info - using multiple labels for white/yellow styling
        # Labels in white, values in yellow (like CMDR status line)
        font_label = self._scaled_font(9)
        font_value = self._scaled_font(9, "bold")
        
        # Row 0: My Power config (compact, above system info)
        from config import load_player_power
        row0_mypower = tk.Frame(ref_info_frame, bg=sf_bg)
        row0_mypower.pack(anchor="center", pady=(2, 10))
        tk.Label(row0_mypower, text=t('system_finder.pp_my_power') + ':', font=font_label, fg="#aaaaaa", bg=sf_bg).pack(side="left")
        _saved_power = load_player_power()
        if _saved_power in ("Not pledged", ""):
            _saved_power = "Select your pledge..."
        self.sysfinder_my_power_var = tk.StringVar(value=self._sysfinder_option_label(_saved_power))
        mypower_combo = ttk.Combobox(
            row0_mypower, textvariable=self.sysfinder_my_power_var,
            values=localized_options(ELITE_POWERS), width=22, state="readonly"
        )
        mypower_combo.pack(side="left", padx=(4, 0))
        mypower_combo.bind("<<ComboboxSelected>>", lambda e: (mypower_combo.selection_clear(), self._save_player_power()))

        # Row 1: System name (centered)
        row1_container = tk.Frame(ref_info_frame, bg=sf_bg)
        row1_container.pack(anchor="center")
        
        tk.Label(row1_container, text=t('system_finder.col_system') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_system = tk.Label(row1_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_system.pack(side="left")
        
        # Row 2: Properties (centered)
        row2_container = tk.Frame(ref_info_frame, bg=sf_bg)
        row2_container.pack(anchor="center")
        
        tk.Label(row2_container, text=t('system_finder.security') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_sec = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_sec.pack(side="left")
        
        tk.Label(row2_container, text=' | ' + t('system_finder.allegiance') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_alleg = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_alleg.pack(side="left")
        
        tk.Label(row2_container, text=' | ' + t('system_finder.government') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_gov = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_gov.pack(side="left")
        
        tk.Label(row2_container, text=' | ' + t('system_finder.economy') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_eco = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_eco.pack(side="left")
        
        tk.Label(row2_container, text=' | ' + t('system_finder.population') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_pop = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_pop.pack(side="left")
        
        tk.Label(row2_container, text=' | ' + t('system_finder.state') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_state = tk.Label(row2_container, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_state.pack(side="left")

        # Reserve the row during loading so the results table stays in place.
        pp_container = tk.Frame(ref_info_frame, bg=sf_bg, height=self._scaled_px(24))
        pp_container.pack(fill='x')
        pp_container.pack_propagate(False)
        row_pp = tk.Frame(pp_container, bg=sf_bg)
        self.sysfinder_pp_frame = row_pp
        tk.Label(row_pp, text=t('system_finder.powerplay') + ':', font=font_label, fg="#aaaaaa", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_pp_power = tk.Label(row_pp, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_pp_power.pack(side="left")
        tk.Label(row_pp, text=' | ' + t('system_finder.state') + ':', font=font_label, fg="white", bg=sf_bg).pack(side="left")
        self.sysfinder_ref_val_pp_state = tk.Label(row_pp, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_pp_state.pack(side="left")
        _foryou_lbl = tk.Label(row_pp, text=' | ' + t('system_finder.pp_for_you') + ':', font=font_label, fg="white", bg=sf_bg)
        _foryou_lbl.pack(side="left")
        self.sysfinder_ref_val_pp_foryou = tk.Label(row_pp, text=" -", font=font_value, fg="#ff9900", bg=sf_bg)
        self.sysfinder_ref_val_pp_foryou.pack(side="left")
        ToolTip(_foryou_lbl, t('system_finder.pp_tooltip_foryou'))
        ToolTip(self.sysfinder_ref_val_pp_foryou, t('system_finder.pp_tooltip_foryou'))
        _merits_lbl = tk.Label(row_pp, text=' | ' + t('system_finder.pp_merits') + ':', font=font_label, fg="white", bg=sf_bg)
        _merits_lbl.pack(side="left")
        self.sysfinder_ref_val_pp_merits = tk.Label(row_pp, text=" -", font=font_value, fg="#ffcc00", bg=sf_bg)
        self.sysfinder_ref_val_pp_merits.pack(side="left")
        ToolTip(_merits_lbl, t('system_finder.pp_tooltip_merits'))
        ToolTip(self.sysfinder_ref_val_pp_merits, t('system_finder.pp_tooltip_merits'))
        create_help_link(row_pp, "powerplay-merit-mining", t('system_finder.pp_tooltip_merits'), ToolTip,
                          bg=sf_bg, fg="#ffcc00").pack(side="left", padx=(4, 0))


        if sf_theme in ("modern", "modern_slate", "modern_orange"):
            trader_ctrl_frame = ttk.Frame(row0_mypower)
            trader_ctrl_frame.pack(side="left", padx=(self._scaled_px(24), 0))
            ttk.Label(trader_ctrl_frame, text=t('system_finder.material_trader') + ':').pack(side="left", padx=(0, 5))
        else:
            ttk.Separator(search_frame, orient='horizontal').grid(
                row=6, column=0, columnspan=4, sticky="ew", pady=(8, 4))
            ttk.Label(search_frame, text=t('system_finder.material_trader') + ':').grid(
                row=7, column=0, sticky="e", padx=(0, 5), pady=3)
            trader_ctrl_frame = ttk.Frame(search_frame)
            trader_ctrl_frame.grid(row=7, column=1, columnspan=3, sticky="w", padx=5, pady=3)

        self.sysfinder_trader_type = tk.StringVar(value=self._sysfinder_option_label("Encoded"))
        trader_combo = ttk.Combobox(
            trader_ctrl_frame, textvariable=self.sysfinder_trader_type,
            values=localized_options(MATERIAL_TRADER_OPTIONS), width=15, state="readonly"
        )
        trader_combo.pack(side="left")
        trader_combo.bind("<<ComboboxSelected>>", lambda e: trader_combo.selection_clear())

        self.sysfinder_trader_btn = create_action_button(
            trader_ctrl_frame, primary=True, text=t('system_finder.find_nearest'),
            command=self._search_material_traders,
            bg="#2a4a2a", fg="#e0e0e0",
            activebackground="#3a5a3a", activeforeground="#ffffff",
            relief="ridge", bd=1, cursor="hand2"
        )
        self.sysfinder_trader_btn.pack(side="left", padx=(10, 0))

        self._sysfinder_ref_requested = None
        self._sysfinder_ref_generation = 0
        self._sysfinder_ref_status = None
        self.sysfinder_reference_system.trace_add('write', self._on_sysfinder_reference_changed)

        # Results section
        results_frame = ttk.LabelFrame(main_container, padding=(5, 8, 5, 5))
        results_frame.pack(fill="both", expand=True, pady=(self._scaled_px(4), 0) if sf_theme in ("modern", "modern_slate", "modern_orange") else (5, 0))
        self.sysfinder_results_frame = results_frame

        # Title row: "Systems" + help text + status/count, used as the LabelFrame's title
        title_row = ttk.Frame(results_frame)
        self.sysfinder_results_title = ttk.Label(title_row, text=t('system_finder.systems'), style="TLabelframe.Label")
        self.sysfinder_results_title.pack(side="left")
        systems_info = ttk.Label(title_row, text="\u24d8", foreground=modern_color("#8A94A3"),
                                 cursor="hand2", font=self._scaled_font(10))
        systems_info.pack(side="left", padx=(6, 2))
        ToolTip(systems_info, t('ring_finder.right_click_help'))
        if sf_theme not in ("modern", "modern_slate", "modern_orange"):
            self.sysfinder_status_label = ttk.Label(title_row, text="", font=self._scaled_font(8))
            self.sysfinder_status_label.pack(side="left", padx=(10, 0))
        title_row.pack(fill="x", pady=(0, 4))
        self._sysfinder_columns_buttons = {
            key: self._cv_add_columns_button(title_row, key)
            for key in ('system_finder', 'system_finder_traders')
        }
        if sf_theme in ("modern", "modern_slate", "modern_orange"):
            self.sysfinder_status_label = ttk.Label(title_row, text="", anchor="w",
                font=self._scaled_font(9, "bold"), foreground=modern_color("#E6EAF0"))
            self.sysfinder_status_label.pack(side="left", fill="x", expand=True, padx=(10, 0))
        
        # Store theme colors for context menu (before creating it)
        self._sysfinder_menu_bg = sf_menu_bg
        self._sysfinder_menu_fg = sf_menu_fg
        self._sysfinder_menu_active_bg = sf_menu_active_bg
        self._sysfinder_menu_active_fg = sf_menu_active_fg
        
        # Create results table
        self._sysfinder_tables = {}
        self._create_sysfinder_results_table(results_frame)
        self._create_sysfinder_results_table(results_frame, trader=True)
        self._sysfinder_show_results('system_finder')
        
        # Create context menu
        self._create_sysfinder_context_menu()
        
        # Auto-populate current system after a delay
        self.after(2000, self._populate_sysfinder_system)
        
        # Start Spansh and EDDN status checks
        self.after(300000, self._check_sysfinder_spansh_status)
        self.after(300000, self._check_sysfinder_eddn_status)
        
        # Remove focus from entry field (prevent highlight on tab switch)
        # Focus the frame instead of the entry
        frame.focus_set()
    
    def _create_sysfinder_results_table(self, parent_frame, trader=False):
        """Create results table for system finder"""
        table_frame = ttk.Frame(parent_frame, relief="solid", borderwidth=1)
        
        config_key = 'system_finder_traders' if trader else 'system_finder'
        if trader:
            definitions = (
                ('system', 'system_finder.col_system', 150),
                ('distance', 'system_finder.col_distance', 70),
                ('station', 'ring_finder.col_station', 160),
                ('type', 'marketplace.type', 110),
                ('pad', 'marketplace.pad', 55),
                ('ls', 'system_finder.col_arrival', 100),
                ('planetary', 'system_finder.col_planetary', 90),
            )
        else:
            definitions = tuple((col, 'system_finder.col_' + col, width) for col, width in (
                ('system', 150), ('distance', 70), ('security', 80), ('allegiance', 90),
                ('state', 180), ('population', 100), ('economy', 120), ('powerplay', 170)))
        columns = tuple(col for col, _, _ in definitions) + ('_spacer',)

        # Configure treeview style based on theme
        from config import load_theme
        current_theme = load_theme()
        style = ttk.Style()
        
        if current_theme == "elite_orange":
            tree_bg = "#1e1e1e"
            tree_fg = "#ff8c00"
            header_bg = "#1a1a1a"
            selection_bg = "#ff6600"
            selection_fg = "#000000"
        else:
            tree_bg = "#1e1e1e"
            tree_fg = "#e6e6e6"
            header_bg = "#2a2a2a"
            selection_bg = "#0078d7"
            selection_fg = "#ffffff"
        
        style.configure("SystemFinder.Treeview",
                       rowheight=self._scaled_px(25),
                       background=tree_bg,
                       foreground=tree_fg,
                       fieldbackground=tree_bg,
                       font=self._scaled_font(9))
        style.configure("SystemFinder.Treeview.Heading",
                       background=header_bg,
                       foreground=tree_fg,
                       font=self._scaled_font(9, "bold"))
        style.map("SystemFinder.Treeview",
                 background=[('selected', selection_bg)],
                 foreground=[('selected', selection_fg)])
        
        tree = StripedTreeview(
            table_frame, columns=columns, show="headings", height=15, style="SystemFinder.Treeview"
        )
        
        numeric_columns = {'distance', 'population', 'ls'}
        for col, key, _ in definitions:
            tree.heading(col, text=t(key), anchor='w',
                         command=lambda c=col: self._sort_sysfinder_column(c, c in numeric_columns))
        tree.heading('_spacer', text='', anchor='w')

        # Column widths
        # minwidth is derived from the actual rendered header text width (at the
        # scaled heading font) rather than a fixed guess, so headers can never be
        # squeezed below what their own label needs, at any UI scale or language.
        import tkinter.font as _tkfont
        _heading_font = _tkfont.Font(font=self._scaled_font(9, "bold"))
        _base_widths = {col: width for col, _, width in definitions}
        _header_pad = self._scaled_px(24)  # header cell padding + sort-arrow space

        def _min_for(col_name):
            header_text = tree.heading(col_name, "text")
            text_width = _heading_font.measure(header_text) + _header_pad
            return max(text_width, self._scaled_px(50))

        _minwidths = {col: _min_for(col) for col in _base_widths}

        _anchors = {col: "w" for col in _base_widths}
        for col_name, base_width in _base_widths.items():
            tree.column(col_name, width=max(self._scaled_px(base_width), _minwidths[col_name]),
                                       minwidth=_minwidths[col_name], anchor=_anchors[col_name], stretch=False)

        # Spacer column — always last, gives the real last column a draggable right border
        tree.column("_spacer", width=self._scaled_px(20), minwidth=self._scaled_px(20),
                                   anchor="w", stretch=True)

        # Setup column visibility for system finder (exclude _spacer from menu)
        _visibility_columns = tuple(c for c in columns if c != "_spacer")
        self.setup_column_visibility(
            tree=tree,
            columns=_visibility_columns,
            default_widths={col: max(self._scaled_px(w), _minwidths[col]) for col, w in _base_widths.items()},
            config_key=config_key,
            allow_reorder=True,
            use_displaycolumns=True
        )
        
        # Vertical scrollbar
        v_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=v_scrollbar.set)
        
        # Horizontal scrollbar (like Ring Finder)
        h_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(xscrollcommand=h_scrollbar.set)
        
        # Configure row tags for alternating colors (like Ring Finder)
        tree.tag_configure('oddrow', background='#1e1e1e')
        tree.tag_configure('evenrow', background='#1a1a1a')
        
        # Grid layout for treeview and scrollbars (like Ring Finder)
        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        
        # Configure grid weights
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)
        
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers[config_key] = self._show_sysfinder_context_menu
        tree.bind('<Double-1>', self._sysfinder_on_double_click)
        tree._sysfinder_sort_reverse = {}
        tree._sysfinder_numbers = {}
        self._sysfinder_tables[config_key] = {'tree': tree, 'frame': table_frame}

        from config import _load_cfg, update_config_value
        saved_widths = _load_cfg().get(config_key + '_column_widths', {})
        # The State column now holds several states; widen a saved narrow default once.
        state_flag = config_key + '_state_width_widened'
        if 'state' in _base_widths and 'state' in saved_widths and not _load_cfg().get(state_flag):
            saved_widths['state'] = max(saved_widths['state'], self._scaled_px(180))
            from config import update_config_values
            update_config_values({config_key + '_column_widths': saved_widths, state_flag: True})
        for col in _base_widths:
            if col in saved_widths:
                tree.column(col, width=max(saved_widths[col], _minwidths[col]))

        def save_widths(event):
            widths = {col: tree.column(col, 'width') for col in _base_widths}
            update_config_value(config_key + '_column_widths', widths)
        tree.bind('<ButtonRelease-1>', save_widths, add='+')

    def _create_sysfinder_context_menu(self):
        """Create context menu for system finder results with theme colors"""
        menu_bg = getattr(self, '_sysfinder_menu_bg', '#1e1e1e')
        menu_fg = getattr(self, '_sysfinder_menu_fg', '#ff8c00')
        menu_active_bg = getattr(self, '_sysfinder_menu_active_bg', '#ff6600')
        menu_active_fg = getattr(self, '_sysfinder_menu_active_fg', '#000000')
        
        self.sysfinder_context_menu = tk.Menu(self, tearoff=0,
            bg=menu_bg, fg=menu_fg,
            activebackground=menu_active_bg, activeforeground=menu_active_fg,
            selectcolor=menu_active_bg, font=self._scaled_font(9))
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.copy_system'),
            command=self._copy_sysfinder_system
        )
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.find_hotspots'),
            command=self._find_hotspots_from_sysfinder
        )
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.set_as_reference'),
            command=self._set_sysfinder_as_reference
        )
        self.sysfinder_context_menu.add_separator()
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.open_inara'),
            command=self._open_sysfinder_inara
        )
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.open_edsm'),
            command=self._open_sysfinder_edsm
        )
        self.sysfinder_context_menu.add_command(
            label=t('system_finder.open_spansh'),
            command=self._open_sysfinder_spansh
        )
    
    def _show_sysfinder_context_menu(self, event):
        """Show context menu on right-click"""
        try:
            item = self.sysfinder_tree.identify_row(event.y)
            if item:
                self.sysfinder_tree.selection_set(item)
                self.sysfinder_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.sysfinder_context_menu.grab_release()
    
    def _copy_sysfinder_system(self):
        """Copy selected system name to clipboard"""
        selection = self.sysfinder_tree.selection()
        if selection:
            item = self.sysfinder_tree.item(selection[0])
            system_name = item['values'][0]
            self.clipboard_clear()
            self.clipboard_append(system_name)
            self._set_status(t('marketplace.copied_to_clipboard').format(system=system_name), 3000)
    
    def _find_hotspots_from_sysfinder(self):
        """Switch to Hotspots Finder with the selected system as reference"""
        selection = self.sysfinder_tree.selection()
        if not selection:
            return
        system_name = self.sysfinder_tree.item(selection[0])['values'][0]
        if not system_name:
            return
        self.switch_to_tab('hotspots_finder')
        if hasattr(self, 'ring_finder'):
            self.ring_finder.system_var.set(system_name)
            if hasattr(self.ring_finder, 'min_hotspots_var'):
                self.ring_finder.min_hotspots_var.set("1")
            if hasattr(self.ring_finder, 'distance_var'):
                self.ring_finder.distance_var.set("100")
            if hasattr(self.ring_finder, 'max_results_var'):
                self.ring_finder.max_results_var.set("200")
            self.after(100, self.ring_finder.search_hotspots)

    def _set_sysfinder_as_reference(self):
        """Set the selected system as the reference system and re-run the search"""
        selection = self.sysfinder_tree.selection()
        if not selection:
            return
        system_name = self.sysfinder_tree.item(selection[0])['values'][0]
        if not system_name:
            return
        self.sysfinder_reference_system.set(system_name)
        self.after(100, self._search_systems)

    def _sysfinder_on_double_click(self, event):
        """Open Inara and fetch/refresh PP data when double-clicking a row."""
        item = self.sysfinder_tree.identify_row(event.y)
        if not item:
            return
        self.sysfinder_tree.selection_set(item)
        self._open_sysfinder_inara()

    def _open_sysfinder_inara(self):
        selection = self.sysfinder_tree.selection()
        if selection:
            from app_utils import open_system_website
            open_system_website(self.sysfinder_tree.set(selection[0], 'system'))
            self._fetch_sysfinder_pp_from_inara()

    def _fetch_sysfinder_pp_from_inara(self):
        """Fetch Inara powerplay for all uniquely-named selected systems (up to PP_FETCH_MAX_BATCH)."""
        selection = self.sysfinder_tree.selection()
        if not selection:
            return
        seen = set()
        systems = []
        for item in selection:
            vals = self.sysfinder_tree.item(item, 'values')
            if vals and len(vals) > 0:
                sys_name = vals[0]
                if sys_name and sys_name not in seen:
                    seen.add(sys_name)
                    systems.append(sys_name)
        if not systems:
            return
        if len(systems) > self.PP_FETCH_MAX_BATCH:
            systems = systems[:self.PP_FETCH_MAX_BATCH]
        if len(systems) == 1:
            self.sysfinder_status_label.config(text=t('ring_finder.fetching_pp').format(system=systems[0]))
        else:
            self.sysfinder_status_label.config(text=t('ring_finder.fetching_pp_batch').format(n=len(systems)))
        threading.Thread(target=self._fetch_sysfinder_pp_batch_worker, args=(systems,), daemon=True).start()

    def _fetch_sysfinder_pp_batch_worker(self, systems):
        """Sequential background fetch: one Inara request per system with a delay between."""
        import time
        from system_finder_api import SystemFinderAPI
        total = len(systems)
        done = 0
        failed = 0
        for i, system_name in enumerate(systems):
            self.after(0, lambda n=system_name, idx=i + 1:
                self.sysfinder_status_label.config(text=t('ring_finder.fetching_pp_progress').format(
                    current=idx, total=total, system=n)))
            result = SystemFinderAPI.fetch_and_store_powerplay_from_inara(system_name)
            if result:
                done += 1
            else:
                failed += 1
            quiet = total > 1
            self.after(0, lambda n=system_name, r=result, q=quiet:
                self._fetch_sysfinder_pp_complete(n, r, quiet=q))
            if i < total - 1:
                time.sleep(self.PP_FETCH_DELAY_SECS)
        if total > 1:
            self.after(0, lambda d=done, f=failed:
                self.sysfinder_status_label.config(text=t('ring_finder.fetching_pp_done').format(done=d, failed=f)))

    def _fetch_sysfinder_pp_complete(self, system_name, result, quiet=False):
        """Update treeview row(s) for system_name with fetched PP data (runs on main thread)."""
        if result:
            from app_utils import format_market_powerplay
            pp_power = result.get('controlling_power', '')
            pp_str = format_market_powerplay({**result, 'power_state': self._sysfinder_option_label(result.get('power_state') or '')}, include_age=True, no_data=t('common.pp_no_data'))
            tree = self._sysfinder_tables['system_finder']['tree']
            for item in tree.get_children():
                vals = list(tree.item(item, 'values'))
                if vals and len(vals) > 7 and vals[0] == system_name:
                    vals[7] = pp_str
                    tree.item(item, values=vals)
            if result.get('system_info'):
                self._sysfinder_apply_system_info(system_name, result['system_info'])
            if not quiet:
                if pp_power == '~none~':
                    self.sysfinder_status_label.config(text=t('ring_finder.pp_fetch_no_power').format(system=system_name))
                else:
                    self.sysfinder_status_label.config(text=t('ring_finder.pp_fetch_success').format(system=system_name, power=pp_str))
        else:
            if not quiet:
                self.sysfinder_status_label.config(text=t('ring_finder.pp_fetch_none').format(system=system_name))

        if hasattr(self, 'sysfinder_reference_system') and self.sysfinder_reference_system.get() == system_name:
            self._update_sysfinder_ref_info(system_name)

    def _open_sysfinder_edsm(self):
        selection = self.sysfinder_tree.selection()
        if selection:
            from app_utils import open_system_website
            open_system_website(self.sysfinder_tree.set(selection[0], 'system'), 'edsm')

    def _open_sysfinder_spansh(self):
        selection = self.sysfinder_tree.selection()
        if selection:
            from app_utils import open_system_website
            open_system_website(self.sysfinder_tree.set(selection[0], 'system'), 'spansh')

    def _use_current_system_sysfinder(self):
        """Use current system from journal for system finder"""
        try:
            current = self.get_current_system()
            if current:
                if self.sysfinder_reference_system.get().strip() != current:
                    self._ac_sysfinder_ref.suppress()
                    self.sysfinder_reference_system.set(current)
                    self._ac_sysfinder_ref.unsuppress()
                self._ac_sysfinder_ref.hide()
                self._confirm_sysfinder_reference()
                self._set_status(t('system_finder.using_current').format(system=current), 3000)
            else:
                self._show_notice(self.sysfinder_status_label, t('ring_finder.could_not_detect_system'), 3000)
        except Exception as e:
            logging.error(f"[SYSTEM_FINDER] Error getting current system: {e}")
    
    def _populate_sysfinder_system(self):
        """Auto-populate system finder with current system"""
        try:
            current = self.get_current_system()
            if current and hasattr(self, 'sysfinder_reference_system'):
                if not self.sysfinder_reference_system.get():
                    if hasattr(self, '_ac_sysfinder_ref'):
                        self._ac_sysfinder_ref.suppress()
                    self.sysfinder_reference_system.set(current)
                    if hasattr(self, '_ac_sysfinder_ref'):
                        self._ac_sysfinder_ref.unsuppress()
                    self._confirm_sysfinder_reference()
                    # Remove selection/focus from entry field
                    if hasattr(self, 'sysfinder_ref_entry'):
                        self.sysfinder_ref_entry.selection_clear()
                        self.focus_set()  # Move focus to main window
        except Exception:
            pass
    
    @staticmethod
    def _sysfinder_option_label(value):
        if value == 'Select your pledge...':
            return t('system_finder.pledge_prompt')
        key = 'system_finder.options.' + value.lower().replace(' ', '_').replace(',', '')
        label = t(key)
        return value if label == key else label

    @classmethod
    def _sysfinder_state_label(cls, state):
        if state == 'Normal':
            return t('system_finder.normal')
        return ', '.join(cls._sysfinder_option_label(s) for s in state.split(', '))

    def _sysfinder_option_value(self, value):
        return getattr(self, '_sysfinder_option_values', {}).get(value, value)

    @staticmethod
    def _compute_pp_foryou(power: str, power_state: str, player_power: str) -> str:
        """Return contextual Powerplay action text for the player."""
        if not player_power or player_power in ('Select your pledge...', 'Not pledged'):
            return ''
        if power == '~none~' or (power_state or '').lower() in ('unoccupied', 'expansion'):
            return t('system_finder.pp_acquire')
        if not power:
            return ''
        if power == player_power:
            return t('system_finder.pp_reinforce')
        return t('system_finder.pp_undermine')

    @staticmethod
    def _compute_pp_merits(power_state: str, bgs_state: str) -> str:
        """Return a merit yield indicator string.

        PP2.0 only ever reports six system states (Unoccupied, Expansion, Contested,
        Exploited, Fortified, Stronghold — confirmed against live EDDN data). Undermining
        a rival's system carries a +15% merit buff; acquiring an Unoccupied/Expansion
        system carries 0% buff, so those rank lower despite being "available" targets.
        """
        if not power_state:
            return ""
        boom = bool(bgs_state and bgs_state.lower() == "boom")
        state = power_state.lower()
        if state == "stronghold":
            base = "+"      # already maxed, lowest reinforcement/undermining priority
        elif state == "contested":
            base = "+++"    # actively up for grabs, highest priority window
        elif state in ("exploited", "fortified"):
            base = "++"     # undermining buff applies
        else:
            base = "+"      # Unoccupied, Expansion — acquisition gets no merit buff
        if boom and base != "+++":
            base += "+"     # Boom adds one tier
        context = " (Boom)" if boom else ""
        return f"{base}{context}"

    def _on_sysfinder_reference_changed(self, *args):
        self._sysfinder_ref_generation += 1
        self._sysfinder_ref_requested = None
        self._sysfinder_ref_status = None
        system = self.sysfinder_reference_system.get().strip()
        self._update_sysfinder_ref_labels(None, system)

    def _confirm_sysfinder_reference(self, system_name=None):
        system = (system_name or self.sysfinder_reference_system.get()).strip()
        if system and system != self._sysfinder_ref_requested:
            self._update_sysfinder_ref_info(system)

    def _update_sysfinder_ref_info(self, system_name: str):
        if system_name != self.sysfinder_reference_system.get().strip():
            return
        self._sysfinder_ref_requested = system_name
        self._sysfinder_ref_generation += 1
        generation = self._sysfinder_ref_generation
        self._sysfinder_ref_status = None
        self._update_sysfinder_ref_labels(None, system_name, loading=True)

        def fetch_info():
            from system_finder_api import SystemFinderAPI
            status = SystemFinderAPI.get_system_status(system_name)
            self.after(0, self._sysfinder_ref_info_complete, system_name, generation, status)
        threading.Thread(target=fetch_info, daemon=True).start()

    def _sysfinder_ref_info_complete(self, system_name, generation, status):
        if generation != self._sysfinder_ref_generation or system_name != self.sysfinder_reference_system.get().strip():
            return
        self._sysfinder_ref_status = status
        if status is None:
            self._sysfinder_ref_requested = None
        self._update_sysfinder_ref_labels(status, system_name)

    @staticmethod
    def _format_sysfinder_population(population):
        if population is None:
            return '-'
        for threshold, suffix in ((1_000_000_000, 'B'), (1_000_000, 'M'), (1_000, 'K')):
            if population >= threshold:
                return f'{population / threshold:.1f}{suffix}'
        return str(population)

    def _update_sysfinder_ref_labels(self, status, system_name=None, loading=False):
        system_name = system_name or self.sysfinder_reference_system.get().strip()
        self.sysfinder_ref_val_system.config(text=' ' + (system_name or t('system_finder.enter_system')))
        empty = ' ...' if loading else ' -'
        fields = {'sec': 'security', 'alleg': 'allegiance', 'gov': 'government', 'eco': 'economy',
                  'pop': 'population', 'state': 'state'}
        for label, field in fields.items():
            value = status.get(field) if status else None
            if status and field == 'population':
                value = self._format_sysfinder_population(value)
            elif isinstance(value, dict):
                value = value.get('primary')
            elif field == 'state' and value:
                value = self._sysfinder_state_label(value)
            if isinstance(value, str) and field not in ('population', 'state'):
                value = self._sysfinder_option_label(value)
            getattr(self, 'sysfinder_ref_val_' + label).config(text=' ' + str(value) if value is not None and value != '' else empty)
        power = status.get('power') if status else None
        power_state = status.get('power_state') if status else None
        if not (power or power_state):
            self.sysfinder_pp_frame.pack_forget()
            return
        if power == '~none~':
            power_text = t('common.pp_no_power')
        else:
            power_text = power or '-'
        player_power = self._sysfinder_option_value(self.sysfinder_my_power_var.get())
        self.sysfinder_ref_val_pp_power.config(text=' ' + power_text)
        self.sysfinder_ref_val_pp_state.config(text=' ' + self._sysfinder_option_label(power_state or '-'))
        self.sysfinder_ref_val_pp_foryou.config(text=' ' + self._compute_pp_foryou(power, power_state, player_power))
        bgs_state = 'Boom' if 'Boom' in (status.get('active_states') or []) else status.get('state')
        self.sysfinder_ref_val_pp_merits.config(text=' ' + self._compute_pp_merits(power_state, bgs_state))
        self.sysfinder_pp_frame.pack(anchor='center')

    def _check_sysfinder_spansh_status(self):
        self.ring_finder._check_spansh_status()
        self.after(300000, self._check_sysfinder_spansh_status)

    def _update_sysfinder_spansh_status(self, status: str):
        """Update Spansh status label in system finder - called on UI thread"""
        if status == "online":
            status_text = t('system_finder.service_online').format(service='Spansh')
            status_color = "#00ff00"
        else:
            status_text = t('system_finder.service_offline').format(service='Spansh')
            status_color = "#ff4444"

        if hasattr(self, 'sysfinder_spansh_status_label'):
            self.sysfinder_spansh_status_label.config(text=status_text, fg=status_color)
        self._update_footer_indicator('spansh', status)

    def _check_sysfinder_eddn_status(self):
        self.ring_finder._check_eddn_status()
        self.after(300000, self._check_sysfinder_eddn_status)

    def _update_sysfinder_eddn_status(self, status: str):
        """Update EDDN status label in system finder - called on UI thread"""
        if status == "online":
            status_text = t('system_finder.service_online').format(service='EDDN')
            status_color = "#00ff00"
        else:
            status_text = t('system_finder.service_offline').format(service='EDDN')
            status_color = "#ff4444"

        if hasattr(self, 'sysfinder_eddn_status_label'):
            self.sysfinder_eddn_status_label.config(text=status_text, fg=status_color)
        self._update_footer_indicator('eddn', status)

    def _search_systems(self):
        """Search for systems matching criteria"""
        if getattr(self, '_traders_search_control', None) and self._traders_search_control.running:
            self._traders_search_control.stop()
            return
        if not hasattr(self, '_systems_search_control'):
            self._systems_search_control = SearchControl(self, self.sysfinder_search_btn, self.sysfinder_status_label)
        control = self._systems_search_control
        if control.running:
            control.stop()
            return
        reference = self.sysfinder_reference_system.get().strip()
        if not reference:
            self.sysfinder_status_label.config(text=t('system_finder.no_system_entered'))
            return
        
        self._ac_sysfinder_ref.hide()
        self._confirm_sysfinder_reference()
        control.on_finish = lambda: self.sysfinder_trader_btn.config(state='normal')
        control.start()
        self.sysfinder_trader_btn.config(state='disabled')
        self.sysfinder_status_label.config(text=t('system_finder.searching'))
        
        filters = {
            'allegiance': self.sysfinder_allegiance.get(),
            'government': self.sysfinder_government.get(),
            'security': self.sysfinder_security.get(),
            'economy': self.sysfinder_economy.get(),
            'state': self.sysfinder_state.get(),
            'population': self.sysfinder_population.get(),
            'power': self.sysfinder_power.get() if hasattr(self, 'sysfinder_power') else 'Any',
            'pp_state': self.sysfinder_pp_state.get() if hasattr(self, 'sysfinder_pp_state') else 'Any',
        }

        filters = {key: self._sysfinder_option_value(value) for key, value in filters.items()}

        # Run search in background thread
        thread = threading.Thread(target=self._search_systems_worker, args=(reference, filters, control), daemon=True)
        thread.start()
    
    def _search_systems_worker(self, reference, filters, control):
        """Background worker for system search - uses Spansh API with server-side filtering"""
        try:
            from system_finder_api import SystemFinderAPI
            
            def progress_callback(current, total, message):
                control.progress(message)

            # Check if any filters are active
            has_filters = any(v not in ('Any', '') for v in filters.values())
            
            # Use new Spansh-based search with server-side filtering
            systems = SystemFinderAPI.search_systems(
                reference_system=reference,
                filters=filters,
                max_results=100,
                progress_callback=progress_callback,
                is_cancelled=control.is_cancelled
            )
            
            
            if not systems:
                control.complete([], self._sysfinder_search_complete, None, has_filters)
                return

            # Pre-format rows in background thread to keep main thread work minimal
            formatted_rows = []
            for idx, system in enumerate(systems):
                row_tag = 'oddrow' if idx % 2 == 0 else 'evenrow'
                values, numbers = self._format_sysfinder_row(system)
                formatted_rows.append((values, row_tag, numbers))

            control.complete(formatted_rows, self._sysfinder_search_complete, None, has_filters)
            
        except Exception as e:
            logging.error(f"[SYSTEM_FINDER] Search error: {e}")
            import traceback
            traceback.print_exc()
            control.failed(str(e))
    
    def _sysfinder_search_complete(self, results: list, error: str = None, had_filters: bool = False):
        self._sysfinder_show_results('system_finder')
        self._populate_sysfinder_rows(results)
        if error:
            text = t('marketplace.search_failed').format(error=error)
        elif results:
            text = t('system_finder.results_count').format(count=len(results))
        else:
            text = t('system_finder.no_filter_results' if had_filters else 'system_finder.no_results')
        self.sysfinder_status_label.config(text=text)

    def _sort_sysfinder_column(self, column: str, numeric: bool):
        tree = self.sysfinder_tree
        reverse = tree._sysfinder_sort_reverse.get(column, False)
        tree._sysfinder_sort_reverse[column] = not reverse
        items = list(tree.get_children())
        if numeric:
            def value(item):
                return tree._sysfinder_numbers.get(item, {}).get(column)
            known = [item for item in items if value(item) is not None]
            unknown = [item for item in items if value(item) is None]
            items = sorted(known, key=value, reverse=reverse) + unknown
        else:
            items.sort(key=lambda item: tree.set(item, column).lower(), reverse=reverse)
        for index, item in enumerate(items):
            tree.move(item, '', index)
        from ui.sort_indicator import apply_sort_arrow
        apply_sort_arrow(tree, column, reverse)

    def _sysfinder_show_results(self, config_key):
        for key, data in self._sysfinder_tables.items():
            data['frame'].pack_forget()
            self._sysfinder_columns_buttons[key].pack_forget()
        data = self._sysfinder_tables[config_key]
        self.sysfinder_tree = data['tree']
        data['frame'].pack(fill='both', expand=True, padx=2, pady=2)
        self._sysfinder_columns_buttons[config_key].pack(side='right', padx=(self._scaled_px(8), 0))
        label = 'system_finder.systems' if config_key == 'system_finder' else 'system_finder.material_traders'
        self.sysfinder_results_title.config(text=t(label))

    def _format_sysfinder_row(self, system):
        """Return (values, numbers) for a Star Systems result row."""
        pop = system.get('population')
        pop_str = self._format_sysfinder_population(pop)
        economy = system.get('economy', {})
        eco_str = economy.get('primary') or '-' if isinstance(economy, dict) else (str(economy) if economy else '-')
        distance = system.get('distance')
        dist_str = f"{distance:.1f}" if distance is not None else "-"
        state_val = system.get('state', 'Normal')
        if not state_val or state_val in ('-', 'None'):
            state_val = 'Normal'
        from app_utils import format_market_powerplay
        pp_str = format_market_powerplay({
            'controlling_power': system.get('power'),
            'power_state': self._sysfinder_option_label(system.get('power_state') or ''),
            'updated_at': system.get('power_updated_at'),
        }, include_age=True, no_data=t('common.pp_no_data'))
        values = (system.get('systemName', '-'), dist_str, self._sysfinder_option_label(system.get('security') or '-'),
                  self._sysfinder_option_label(system.get('allegiance') or '-'), self._sysfinder_state_label(state_val),
                  pop_str, self._sysfinder_option_label(eco_str), pp_str)
        return values, {'distance': distance, 'population': pop, 'system': system}

    def _sysfinder_apply_system_info(self, system_name, info):
        """Update result rows for system_name when info comes from a newer report than the row shows."""
        from system_finder_api import SystemFinderAPI
        tree = self._sysfinder_tables['system_finder']['tree']
        for item in tree.get_children():
            numbers = tree._sysfinder_numbers.get(item) or {}
            system = numbers.get('system')
            if not system or system.get('systemName', '').lower() != system_name.lower():
                continue
            updated = SystemFinderAPI.apply_system_info(system, info)
            if not updated:
                continue
            new_values, new_numbers = self._format_sysfinder_row(updated)
            vals = list(tree.item(item, 'values'))
            # Keep the PowerPlay cell, which has its own refresh
            vals[2:7] = new_values[2:7]
            tree.item(item, values=vals)
            numbers.update(population=new_numbers['population'], system=updated)

    def _populate_sysfinder_rows(self, results):
        tree = self.sysfinder_tree
        tree.delete(*tree.get_children())
        tree._sysfinder_numbers.clear()
        for values, row_tag, numbers in results:
            item = tree.insert('', 'end', values=values, tags=(row_tag,))
            tree._sysfinder_numbers[item] = numbers
        tree._sysfinder_sort_reverse.clear()
        from ui.sort_indicator import apply_sort_arrow
        apply_sort_arrow(tree, None, False)

    def _search_material_traders(self):
        """Search for nearest material traders"""
        if getattr(self, '_systems_search_control', None) and self._systems_search_control.running:
            self._systems_search_control.stop()
            return
        if not hasattr(self, '_traders_search_control'):
            self._traders_search_control = SearchControl(self, self.sysfinder_trader_btn, self.sysfinder_status_label)
        control = self._traders_search_control
        if control.running:
            control.stop()
            return
        reference = self.sysfinder_reference_system.get().strip()
        if not reference:
            self.sysfinder_status_label.config(text=t('system_finder.no_system_entered'))
            return
        self._ac_sysfinder_ref.hide()
        self._confirm_sysfinder_reference()
        control.on_finish = lambda: self.sysfinder_search_btn.config(state='normal')
        control.start()
        self.sysfinder_search_btn.config(state="disabled")
        self.sysfinder_status_label.config(text=t('system_finder.searching_traders'))
        threading.Thread(target=self._search_material_traders_worker,
                         args=(reference, self._sysfinder_option_value(self.sysfinder_trader_type.get()), control), daemon=True).start()

    def _search_material_traders_worker(self, reference, trader_type, control):
        """Background worker for material trader search"""
        try:
            from system_finder_api import SystemFinderAPI

            def progress_callback(current, total, message):
                control.progress(message)

            results = SystemFinderAPI.search_material_traders(
                reference_system=reference,
                trader_type=trader_type,
                max_results=50,
                progress_callback=progress_callback,
                is_cancelled=control.is_cancelled
            )

            formatted_rows = []
            for idx, r in enumerate(results):
                row_tag = 'oddrow' if idx % 2 == 0 else 'evenrow'
                dist = r.get('distance')
                arrival = r.get('distanceToArrival')
                arrival_str = f"{int(float(arrival)):,}" if arrival is not None else '-'
                planetary = t('common.yes' if r.get('isPlanetary') else 'common.no')
                formatted_rows.append((
                    (r.get('systemName', '-'),
                     f"{dist:.1f}" if dist is not None else '-',
                     r.get('stationName', '-'),
                     r.get('stationType', '-'),
                     r.get('landingPad', '-'),
                     arrival_str,
                     planetary),
                    row_tag, {'distance': dist, 'ls': arrival}
                ))

            control.complete(formatted_rows, self._sysfinder_trader_complete, None)
        except Exception as e:
            logging.error(f"[SYSTEM_FINDER] Material trader search error: {e}")
            control.failed(str(e))

    def _sysfinder_trader_complete(self, results: list, error: str = None):
        self._sysfinder_show_results('system_finder_traders')
        self._populate_sysfinder_rows(results)
        if error:
            text = t('marketplace.search_failed').format(error=error)
        elif results:
            text = t('system_finder.trader_results_count').format(count=len(results))
        else:
            text = t('system_finder.no_traders')
        self.sysfinder_status_label.config(text=text)
