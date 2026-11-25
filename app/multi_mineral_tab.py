"""Multi-Mineral sub-tab of Commodity Market: find the best stations to sell several minerals at once."""
from ui.striped_treeview import StripedTreeview
from ui.themed_checkbox import ThemedCheckbutton
from ui.theme import modern_color
from ui.tooltip import ToolTip
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk
from typing import List

from localization import t
from ui.search_control import SearchControl
from carrier_names import station_display_name
from marketplace_api import MarketplaceAPI
from core.constants import MINING_COMMODITY_ORDER, get_menu_colors
from app_utils import create_action_button, format_market_pad, format_market_powerplay, format_market_source, format_market_station_type, format_relative_age

MAX_MINERALS = 5

class MultiMineralTab:
    """Uses the shared market filters and the main app's localized option maps."""

    def __init__(self, frame: ttk.Frame, main_app):
        self.app = main_app
        self._build(frame)

    def _build(self, frame: ttk.Frame) -> None:
        app = self.app
        from config import load_theme
        theme = load_theme()
        bg = "#000000" if theme == "elite_orange" else "#1e1e1e"
        self._bg = bg
        fg = "#ff8c00" if theme == "elite_orange" else "#e0e0e0"

        container = ttk.Frame(frame)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        search_header = ttk.Frame(container)
        search_header.pack(fill="x")
        ttk.Label(search_header, text=t('marketplace.multi_title'), style="TLabelframe.Label").pack(side="left")
        if theme not in ("modern", "modern_slate", "modern_orange"):
            self.status_label = tk.Label(search_header, text='', bg=bg, fg="gray",
                                         font=app._scaled_font(8))
            self.status_label.pack(side="right", padx=(0, 5))
        box = ttk.LabelFrame(container, padding=10)
        box.pack(fill="x", pady=(0, 10))

        ref_row = tk.Frame(box, bg=bg)
        ref_row.pack(fill="x", pady=(0, 8))
        ttk.Label(ref_row, text=t('marketplace.ref_system'), width=12).pack(side="left", padx=(0, 5))
        self.ref_var = tk.StringVar(value=app.marketplace_reference_system.get())
        ref_entry = ttk.Entry(ref_row, textvariable=self.ref_var, width=30)
        ref_entry.pack(side="left", padx=(0, 5))
        self.ref_entry = ref_entry
        ref_entry.bind("<Return>", lambda e: self.start_search())
        ref_entry.bind("<FocusOut>", lambda e: e.widget.selection_clear())
        from system_autocomplete import SystemAutocomplete
        self._ac_ref = SystemAutocomplete(ref_entry, self.ref_var, app)
        create_action_button(ref_row, text=t('marketplace.use_current'), command=self._use_current_system,
                  bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                  relief="ridge", bd=1, cursor="hand2").pack(side="left")

        tk.Label(box, text=t('marketplace.multi_select_minerals').format(max=MAX_MINERALS), bg=bg, fg=fg,
                 font=app._scaled_font(9)).pack(anchor="w", pady=(0, 4))
        grid = tk.Frame(box, bg=bg)
        grid.pack(fill="x", pady=(0, 8))
        self._mineral_checks = []
        self._mineral_columns = 0
        self._mineral_vars = {}
        for name in MINING_COMMODITY_ORDER:
            var = tk.BooleanVar(value=False)
            self._mineral_vars[name] = var
            cb = ThemedCheckbutton(grid, text=app._commodity_map.get(name, name), variable=var,
                                command=lambda n=name: self._on_toggle(n),
                                bg=bg, fg="#e0e0e0", selectcolor=bg, activebackground=bg,
                                activeforeground="#ffffff", highlightthickness=0, bd=0, relief="flat",
                                font=app._scaled_font(9), anchor="w")
            self._mineral_checks.append(cb)
            cb.grid(row=0, column=0, sticky="w", padx=(0, app._scaled_px(16)))
        grid.bind('<Configure>', self._layout_minerals)

        filt = tk.Frame(box, bg=bg)
        filt.pack(fill="x")
        ttk.Label(filt, text=t('marketplace.station')).pack(side="left", padx=(0, 5))
        self.station_var = tk.StringVar(value=app.marketplace_station_type.get())
        ttk.Combobox(filt, textvariable=self.station_var, state="readonly", width=12,
                     values=[app._station_type_map[k] for k in app._station_type_order]).pack(side="left", padx=(0, 15))
        self.exclude_carriers_var = tk.BooleanVar(value=app.marketplace_exclude_carriers.get())
        self.large_pad_var = tk.BooleanVar(value=app.marketplace_large_pad_only.get())
        self.station_var.trace_add('write', self._on_station_type_change)
        for text, var in ((t('marketplace.exclude_carriers'), self.exclude_carriers_var),
                          (t('marketplace.large_pads'), self.large_pad_var)):
            cb = ThemedCheckbutton(filt, text=text, variable=var, bg=bg, fg="#e0e0e0", selectcolor=bg,
                           activebackground=bg, activeforeground="#ffffff", highlightthickness=0, bd=0,
                           relief="flat", font=app._scaled_font(9))
            if var is self.exclude_carriers_var:
                self.exclude_carriers_cb = cb
            cb.pack(side="left", padx=(0, 10))
        self._on_station_type_change()
        ttk.Label(filt, text=t('marketplace.max_age')).pack(side="left", padx=(10, 5))
        self.age_var = tk.StringVar(value=app.marketplace_max_age.get())
        ttk.Combobox(filt, textvariable=self.age_var, state="readonly", width=10,
                     values=[app._age_map[k] for k in app._age_order]).pack(side="left", padx=(0, 15))
        self.search_btn = create_action_button(filt, primary=True, text="🔍 " + t('marketplace.search'), command=self.start_search,
                                    bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                    activeforeground="#ffffff", relief="ridge", bd=1, cursor="hand2")
        self.search_btn.pack(side="left")

        results_header = ttk.Frame(container)
        results_header.pack(fill="x", pady=(10, 0))
        ttk.Label(results_header, text=t('marketplace.search_results'),
                  font=app._scaled_font(10, "bold")).pack(side="left")
        results_info = ttk.Label(results_header, text="ⓘ", foreground=modern_color("#8A94A3"),
                                 cursor="hand2", font=app._scaled_font(10))
        results_info.pack(side="left", padx=(6, 2))
        ToolTip(results_info, t('marketplace.multi_results_info') + "\n\n" + t('marketplace.fc_docking_note'))
        app._cv_add_columns_button(results_header, 'multiple_prices')
        self.toggle_btn = create_action_button(results_header, text=t('marketplace.multi_collapse_all'),
                                               command=self._toggle_all)
        self.toggle_btn.pack(side="right", padx=(0, 6))
        self._collapsed = False
        if theme in ("modern", "modern_slate", "modern_orange"):
            self.status_label = ttk.Label(results_header, text='', anchor="w",
                font=app._scaled_font(9, "bold"), foreground=modern_color("#E6EAF0"))
            self.status_label.pack(side="left", fill="x", expand=True, padx=(10, 0))
        table = ttk.Frame(container, relief="solid", borderwidth=1)
        table.pack(fill="both", expand=True, pady=(5, 0))
        cols = ("system", "station", "type", "pad", "distance", "ls", "demand", "price", "powerstate", "updated", "_spacer")
        self.tree = StripedTreeview(table, columns=cols, show="tree headings", height=15,
                                 style="Marketplace.Treeview", selectmode="browse")
        headings = {"system": t('ring_finder.col_system'), "station": t('ring_finder.col_station'),
                    "type": t('marketplace.type'), "pad": t('marketplace.pad'), "distance": t('marketplace.distance'),
                    "ls": "LS", "demand": t('marketplace.demand'), "price": t('marketplace.price'),
                    "powerstate": t('marketplace.powerstate'), "updated": t('marketplace.updated')}
        self.tree.heading("#0", text=t('marketplace.multi_col_mineral'), anchor="w",
                          command=lambda: self._sort("#0"))
        self._sort_col = None
        self._sort_rev = False
        import tkinter.font as tkfont
        heading_font = tkfont.Font(font=app._scaled_font(9, "bold"))
        header_pad = app._scaled_px(24)  # header cell padding + sort-arrow space

        def min_for(col):
            return max(heading_font.measure(self.tree.heading(col, "text")) + header_pad, app._scaled_px(50))

        self.tree.column("#0", width=max(app._scaled_px(170), min_for("#0")), minwidth=min_for("#0"),
                         stretch=False, anchor="w")
        widths = {"system": 180, "station": 210, "type": 95, "pad": 45, "distance": 70, "ls": 70, "demand": 80,
                  "price": 120, "powerstate": 150, "updated": 80}
        for c in cols:
            if c == "_spacer":
                self.tree.heading(c, text="", anchor="w")
                self.tree.column(c, width=app._scaled_px(20), stretch=True)
                continue
            anchor = "center" if c in ("pad", "updated") else "w"
            self.tree.heading(c, text=headings[c], anchor=anchor, command=lambda col=c: self._sort(col))
            self.tree.column(c, width=max(app._scaled_px(widths[c]), min_for(c)), minwidth=min_for(c),
                             stretch=False, anchor=anchor)
        app.setup_column_visibility(
            tree=self.tree,
            columns=tuple(c for c in cols if c != "_spacer"),
            default_widths={c: max(app._scaled_px(w), min_for(c)) for c, w in widths.items()},
            config_key='multiple_prices', allow_reorder=True, use_displaycolumns=True)
        from config import load_column_order
        saved_order = list(load_column_order('multiple_prices') or [])
        if saved_order and 'type' not in saved_order and 'location' in saved_order:
            saved_order.insert(saved_order.index('location') + 1, 'type')
        app._cv_split_saved_column('multiple_prices', 'location', ('system', 'station'), saved_order)

        from config import load_multiple_prices_column_widths, save_multiple_prices_column_widths
        for col, width in load_multiple_prices_column_widths().items():
            try:
                self.tree.column(col, width=max(width, self.tree.column(col, "minwidth")))
            except tk.TclError:
                pass

        def save_widths(event=None):
            widths = {}
            for col in ("#0",) + tuple(c for c in cols if c != "_spacer"):
                w = self.tree.column(col, "width")
                if w > 0:
                    widths[col] = w
            save_multiple_prices_column_widths(widths)
        self.tree.bind("<ButtonRelease-1>", save_widths)
        self.tree.bind("<Double-1>", lambda e: app._on_commodity_tree_double_click(e, self.tree, refresh_powerplay=False))
        if not hasattr(app, '_context_handlers'):
            app._context_handlers = {}
        app._context_handlers['multiple_prices'] = self._show_context_menu
        self._row_source = {}
        from ui.cell_tooltip import attach_cell_tooltip
        attach_cell_tooltip(self.tree, "updated", lambda item: self._row_source.get(item, ''))
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        system = self.tree.set(self.tree.parent(item) or item, 'system')
        if not system:
            return
        self.tree.selection_set(item)
        menu = tk.Menu(self.tree, tearoff=0, font=self.app._scaled_font(9), **get_menu_colors())
        menu.add_command(label=t('context_menu.plot_route'),
                         command=lambda: self.app.route_tab.plot_to_system(system, source_view="multiple_prices"))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # Station rows hold location/pad/distance/LS/powerplay; their mineral rows hold mineral/demand/price/age.
    _PAD_ORDER = {"?": 0, "S": 1, "M": 2, "L": 3}

    @staticmethod
    def _num(text, default=float("inf")):
        try:
            return float(str(text).replace(",", "").replace("CR", "").strip())
        except ValueError:
            return default

    @staticmethod
    def _age_minutes(text):
        text = str(text).strip()
        try:
            return float(text[:-1]) * {"m": 1, "h": 60, "d": 1440}[text[-1]]
        except (ValueError, KeyError, IndexError):
            return float("inf")

    def _toggle_all(self) -> None:
        collapse = not self._collapsed
        self._collapsed = collapse
        for item in self.tree.get_children():
            self.tree.item(item, open=not collapse)
        self.toggle_btn.configure(text=t('marketplace.multi_expand_all' if collapse else 'marketplace.multi_collapse_all'))

    def _sort(self, col: str) -> None:
        """Sort stations by a column. Mineral-level columns order stations by their best mineral row
        (and the mineral rows inside each station by the same column)."""
        tree = self.tree
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col, self._sort_rev = col, False
        vals = ("system", "station", "type", "pad", "distance", "ls", "demand", "price", "powerstate", "updated")
        idx = {c: i for i, c in enumerate(vals)}

        def child_key(item):
            if col == "#0":
                return str(tree.item(item, "text")).lower()
            v = tree.item(item, "values")[idx[col]]
            return self._age_minutes(v) if col == "updated" else self._num(v, 0)

        def station_key(item):
            if col in ("demand", "price", "updated", "#0"):
                keys = [child_key(c) for c in tree.get_children(item)]
                if not keys:
                    return float("inf") if col == "updated" else (0 if col != "#0" else "")
                return min(keys) if col in ("updated", "#0") else max(keys)
            v = tree.item(item, "values")[idx[col]]
            if col == "pad":
                return self._PAD_ORDER.get(str(v), 0)
            if col in ("distance", "ls"):
                return self._num(v)
            return str(v).lower()

        parents = list(tree.get_children())
        for parent in parents:
            if col in ("demand", "price", "updated", "#0"):
                for pos, child in enumerate(sorted(tree.get_children(parent), key=child_key, reverse=self._sort_rev)):
                    tree.move(child, parent, pos)
        for pos, parent in enumerate(sorted(parents, key=station_key, reverse=self._sort_rev)):
            tree.move(parent, "", pos)
        self._show_sort_arrow()

    def _show_sort_arrow(self) -> None:
        from ui.sort_indicator import apply_sort_arrow, strip_sort_arrow, ARROW_UP, ARROW_DOWN
        apply_sort_arrow(self.tree, self._sort_col, self._sort_rev)
        text = strip_sort_arrow(str(self.tree.heading("#0", "text")))
        arrow = (ARROW_DOWN if self._sort_rev else ARROW_UP) if self._sort_col == "#0" else ""
        self.tree.heading("#0", text=text + arrow)

    def _layout_minerals(self, event):
        grid = event.widget
        cell_width = max(cb.winfo_reqwidth() for cb in self._mineral_checks) + self.app._scaled_px(16)
        columns = max(1, min(len(self._mineral_checks), event.width // cell_width))
        if columns == self._mineral_columns:
            return
        for column in range(self._mineral_columns):
            grid.columnconfigure(column, minsize=0)
        for column in range(columns):
            grid.columnconfigure(column, minsize=cell_width)
        for index, cb in enumerate(self._mineral_checks):
            cb.grid_configure(row=index // columns, column=index % columns)
        self._mineral_columns = columns

    def _on_toggle(self, name: str) -> None:
        if sum(v.get() for v in self._mineral_vars.values()) > MAX_MINERALS:
            self._mineral_vars[name].set(False)
            self.status_label.config(text=t('marketplace.multi_max_reached').format(max=MAX_MINERALS))

    def _use_current_system(self) -> None:
        rf = getattr(self.app, 'ring_finder', None)
        if rf:
            rf._auto_detect_system()
            system = rf.system_var.get()
            if system:
                self._ac_ref.suppress()
                self.ref_var.set(system)
                self._ac_ref.unsuppress()
                self._ac_ref.hide()

    def set_minerals(self, minerals: List[str]) -> None:
        """Tick exactly these (English-named) minerals, capped at MAX_MINERALS."""
        for v in self._mineral_vars.values():
            v.set(False)
        for name in [m for m in minerals if m in self._mineral_vars][:MAX_MINERALS]:
            self._mineral_vars[name].set(True)

    def start_search(self) -> None:
        if not hasattr(self, '_search_control'):
            self._search_control = SearchControl(self.app, self.search_btn, self.status_label)
        if self._search_control.running:
            self._search_control.stop()
            return
        app = self.app
        minerals = [n for n, v in self._mineral_vars.items() if v.get()]
        system = self.ref_var.get().strip()
        if not minerals:
            self.status_label.config(text=t('marketplace.multi_select_one'))
            return
        if not system:
            self.status_label.config(text=t('marketplace.enter_reference_system'))
            return
        station_type = app._station_type_rev_map.get(self.station_var.get(), self.station_var.get())
        max_age = app._age_rev_map.get(self.age_var.get(), self.age_var.get())
        exclude_carriers = self.exclude_carriers_var.get() and station_type != "Fleet Carrier"
        large_pad = self.large_pad_var.get()

        self.status_label.config(text=t('marketplace.searching_selling'))
        self._search_control.start()
        threading.Thread(target=self._worker, daemon=True,
                         args=(minerals, system, station_type, max_age, exclude_carriers, large_pad)).start()

    def _worker(self, minerals, system, station_type, max_age, exclude_carriers, large_pad):
        control = self._search_control
        try:
            def fetch(mineral):
                if control.is_cancelled():
                    return mineral, []
                return mineral, MarketplaceAPI.search_buyers(mineral, system, None, MarketplaceAPI.convert_age_to_days(max_age), exclude_carriers, is_cancelled=control.is_cancelled)
            with ThreadPoolExecutor(max_workers=3) as pool:
                raw = list(pool.map(fetch, minerals))
            stations = self._group(raw, station_type, max_age, exclude_carriers, large_pad)
            control.complete(stations, self._complete, len(minerals))
        except Exception as e:
            err = str(e)
            control.failed(err)

    def _filter(self, results, station_type, max_age, exclude_carriers, large_pad):
        return MarketplaceAPI.filter_results(results, station_type, max_age, exclude_carriers, large_pad)

    def _group(self, raw, station_type, max_age, exclude_carriers, large_pad):
        """Group per-mineral results by station; most minerals bought first, then highest total price."""
        grouped = {}
        for mineral, results in raw:
            for r in self._filter(results, station_type, max_age, exclude_carriers, large_pad):
                key = (r.get('systemName', ''), r.get('stationName', ''))
                entry = grouped.setdefault(key, {'info': r, 'minerals': {}})
                prev = entry['minerals'].get(mineral)
                if prev is None or r.get('sellPrice', 0) > prev.get('sellPrice', 0):
                    entry['minerals'][mineral] = r
        stations = list(grouped.values())
        stations.sort(key=lambda s: (len(s['minerals']),
                                     sum(m.get('sellPrice', 0) for m in s['minerals'].values())), reverse=True)
        return stations[:50]


    def _complete(self, stations, mineral_count: int) -> None:
        app = self.app
        self.search_btn.config(state="normal")
        self.tree.delete(*self.tree.get_children())
        self._row_source = {}
        self._sort_col, self._sort_rev = None, False
        self._show_sort_arrow()
        self._collapsed = False
        self.toggle_btn.configure(text=t('marketplace.multi_collapse_all'))
        if not stations:
            self.status_label.config(text=t('marketplace.no_results'))
            return
        from system_finder_api import SystemFinderAPI
        pp_names = list({s['info'].get('systemName') for s in stations if s['info'].get('systemName')})
        pp_data = SystemFinderAPI._batch_get_powerplay(pp_names) if pp_names else {}

        for s in stations:
            info = s['info']
            dist = info.get('distance')
            ls = info.get('distanceToArrival')
            parent = self.tree.insert("", "end", open=True, text="", values=(
                info.get('systemName', ''),
                station_display_name(info),
                format_market_station_type(info.get('stationType')),
                format_market_pad(info.get('maxLandingPadSize')),
                f"{dist:.1f}" if dist is not None else "-",
                f"{int(float(ls)):,}" if ls is not None else "?", "", "",
                format_market_powerplay(pp_data.get(info.get('systemName', ''), {})), ""))
            for mineral, r in sorted(s['minerals'].items(), key=lambda kv: -kv[1].get('sellPrice', 0)):
                child = self.tree.insert(parent, "end", text=app._commodity_map.get(mineral, mineral), values=(
                    "", "", "", "", "", "", f"{r.get('demand', 0):,}", f"{r.get('sellPrice', 0):,} CR", "", format_relative_age(r.get('updatedAt')) or '?'))
                self._row_source[child] = format_market_source(r)
        self.status_label.config(text=t('marketplace.multi_found').format(count=len(stations)))

    def _on_station_type_change(self, *args):
        carrier = self.app._station_type_rev_map.get(self.station_var.get(), self.station_var.get()) == 'Fleet Carrier'
        if carrier:
            self.exclude_carriers_var.set(False)
        self.exclude_carriers_cb.config(state='disabled' if carrier else 'normal')
