"""Multi-Mineral sub-tab of Commodity Market: find the best stations to sell several minerals at once."""
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import ttk
from typing import List

from localization import t
from marketplace_api import MarketplaceAPI

MAX_MINERALS = 5
CHECK_COLUMNS = 3
MULTI_MINERALS = ["Platinum", "Rhodplumsite", "Benitoite", "Painite", "Serendibite", "Grandidierite",
                  "Osmium", "Monazite", "Alexandrite", "Low Temperature Diamonds", "Musgravite", "Void Opals"]

ORBITAL_KW = ["Coriolis", "Orbis", "Ocellus", "Outpost", "AsteroidBase", "Asteroid", "Dodec"]
SURFACE_KW = ["Crater", "OnFoot", "Planetary", "Surface"]


class MultiMineralTab:
    """Reuses the main app's commodity/station/age maps, age filter and MarketplaceAPI.search_buyers."""

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

        box = ttk.LabelFrame(container, text=t('marketplace.multi_title'), padding=10)
        box.pack(fill="x", pady=(0, 10))

        ref_row = tk.Frame(box, bg=bg)
        ref_row.pack(fill="x", pady=(0, 8))
        self.status_label = tk.Label(ref_row, text=t('marketplace.multi_hint'), bg=bg, fg="gray",
                                     font=app._scaled_font(8))
        self.status_label.pack(side="right", padx=(0, 5))
        ttk.Label(ref_row, text=t('marketplace.ref_system'), width=12).pack(side="left", padx=(0, 5))
        self.ref_var = tk.StringVar(value=app.marketplace_reference_system.get())
        ref_entry = ttk.Entry(ref_row, textvariable=self.ref_var, width=30)
        ref_entry.pack(side="left", padx=(0, 5))
        ref_entry.bind("<Return>", lambda e: self.start_search())
        from system_autocomplete import SystemAutocomplete
        self._ac_ref = SystemAutocomplete(ref_entry, self.ref_var, app)
        tk.Button(ref_row, text=t('marketplace.use_current'), command=self._use_current_system,
                  bg="#4a3a2a", fg="#e0e0e0", activebackground="#5a4a3a", activeforeground="#ffffff",
                  relief="ridge", bd=1, padx=6, pady=2, font=app._scaled_font(8), cursor="hand2").pack(side="left")

        tk.Label(box, text=t('marketplace.multi_select_minerals').format(max=MAX_MINERALS), bg=bg, fg=fg,
                 font=app._scaled_font(9)).pack(anchor="w", pady=(0, 4))
        grid = tk.Frame(box, bg=bg)
        grid.pack(fill="x", pady=(0, 8))
        self._mineral_vars = {}
        for i, name in enumerate(MULTI_MINERALS):
            var = tk.BooleanVar(value=False)
            self._mineral_vars[name] = var
            cb = tk.Checkbutton(grid, text=app._commodity_map.get(name, name), variable=var,
                                command=lambda n=name: self._on_toggle(n),
                                bg=bg, fg="#e0e0e0", selectcolor=bg, activebackground=bg,
                                activeforeground="#ffffff", highlightthickness=0, bd=0, relief="flat",
                                font=app._scaled_font(9), anchor="w")
            cb.grid(row=i // CHECK_COLUMNS, column=i % CHECK_COLUMNS, sticky="w", padx=(0, 20))

        filt = tk.Frame(box, bg=bg)
        filt.pack(fill="x")
        ttk.Label(filt, text=t('marketplace.station')).pack(side="left", padx=(0, 5))
        self.station_var = tk.StringVar(value=app.marketplace_station_type.get())
        ttk.Combobox(filt, textvariable=self.station_var, state="readonly", width=12,
                     values=[app._station_type_map[k] for k in app._station_type_order]).pack(side="left", padx=(0, 15))
        self.exclude_carriers_var = tk.BooleanVar(value=app.marketplace_exclude_carriers.get())
        self.large_pad_var = tk.BooleanVar(value=app.marketplace_large_pad_only.get())
        for text, var in ((t('marketplace.exclude_carriers'), self.exclude_carriers_var),
                          (t('marketplace.large_pads'), self.large_pad_var)):
            tk.Checkbutton(filt, text=text, variable=var, bg=bg, fg="#e0e0e0", selectcolor=bg,
                           activebackground=bg, activeforeground="#ffffff", highlightthickness=0, bd=0,
                           relief="flat", font=app._scaled_font(9)).pack(side="left", padx=(0, 10))
        ttk.Label(filt, text=t('marketplace.max_age')).pack(side="left", padx=(10, 5))
        self.age_var = tk.StringVar(value=app.marketplace_max_age.get())
        ttk.Combobox(filt, textvariable=self.age_var, state="readonly", width=10,
                     values=[app._age_map[k] for k in app._age_order]).pack(side="left", padx=(0, 15))
        self.search_btn = tk.Button(filt, text="🔍 " + t('marketplace.search'), command=self.start_search,
                                    bg="#2a4a2a", fg="#e0e0e0", activebackground="#3a5a3a",
                                    activeforeground="#ffffff", relief="ridge", bd=1, padx=10, pady=4,
                                    font=app._scaled_font(9, "bold"), cursor="hand2")
        self.search_btn.pack(side="left")

        tk.Label(container, text=t('marketplace.search_results'), bg=bg, fg=fg,
                 font=app._scaled_font(10, "bold")).pack(anchor="w", pady=(10, 0))
        table = ttk.Frame(container, relief="solid", borderwidth=1)
        table.pack(fill="both", expand=True, pady=(5, 0))
        cols = ("location", "pad", "distance", "ls", "demand", "price", "powerstate", "updated", "_spacer")
        self.tree = ttk.Treeview(table, columns=cols, show="tree headings", height=15,
                                 style="Marketplace.Treeview", selectmode="browse")
        headings = {"location": t('marketplace.multi_col_station'),
                    "pad": t('marketplace.pad'), "distance": t('marketplace.distance'),
                    "ls": "LS", "demand": t('marketplace.demand'), "price": t('marketplace.price'),
                    "powerstate": t('marketplace.powerstate'), "updated": t('marketplace.updated')}
        self.tree.heading("#0", text=t('marketplace.multi_col_mineral'), anchor="w")
        import tkinter.font as tkfont
        heading_font = tkfont.Font(font=app._scaled_font(9, "bold"))
        header_pad = app._scaled_px(24)  # header cell padding + sort-arrow space

        def min_for(col):
            return max(heading_font.measure(self.tree.heading(col, "text")) + header_pad, app._scaled_px(50))

        self.tree.column("#0", width=max(app._scaled_px(170), min_for("#0")), minwidth=min_for("#0"),
                         stretch=False, anchor="w")
        widths = {"location": 255, "pad": 45, "distance": 70, "ls": 70, "demand": 80,
                  "price": 120, "powerstate": 150, "updated": 80}
        for c in cols:
            if c == "_spacer":
                self.tree.heading(c, text="", anchor="w")
                self.tree.column(c, width=app._scaled_px(20), stretch=True)
                continue
            anchor = "center" if c == "pad" else "w"
            self.tree.heading(c, text=headings[c], anchor=anchor)
            self.tree.column(c, width=max(app._scaled_px(widths[c]), min_for(c)), minwidth=min_for(c),
                             stretch=False, anchor=anchor)
        app.setup_column_visibility(
            tree=self.tree,
            columns=tuple(c for c in cols if c != "_spacer"),
            default_widths={c: max(app._scaled_px(w), min_for(c)) for c, w in widths.items()},
            config_key='multiple_prices')

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
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

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
        exclude_carriers = self.exclude_carriers_var.get()
        large_pad = self.large_pad_var.get()

        self.status_label.config(text=t('marketplace.searching_selling'))
        self.search_btn.config(state="disabled")
        threading.Thread(target=self._worker, daemon=True,
                         args=(minerals, system, station_type, max_age, exclude_carriers, large_pad)).start()

    def _worker(self, minerals, system, station_type, max_age, exclude_carriers, large_pad):
        try:
            def fetch(mineral):
                return mineral, MarketplaceAPI.search_buyers(mineral, system, None, 30, exclude_carriers)
            with ThreadPoolExecutor(max_workers=3) as pool:
                raw = list(pool.map(fetch, minerals))
            stations = self._group(raw, station_type, max_age, exclude_carriers, large_pad)
            self.app.after(0, lambda: self._complete(stations, len(minerals)))
        except Exception as e:
            err = str(e)
            self.app.after(0, lambda: self._failed(err))

    def _filter(self, results, station_type, max_age, exclude_carriers, large_pad):
        results = [r for r in results if r.get('demand', 0) > 0]
        stype = lambda r: r.get('stationType') or ''
        if exclude_carriers and station_type != "Fleet Carrier":
            results = [r for r in results if "FleetCarrier" not in stype(r)]
        if station_type == "Orbital":
            results = [r for r in results if any(k in stype(r) for k in ORBITAL_KW)
                       and not any(k in stype(r) for k in SURFACE_KW)]
        elif station_type == "Surface":
            results = [r for r in results if any(k in stype(r) for k in SURFACE_KW)]
        elif station_type == "Fleet Carrier":
            results = [r for r in results if "FleetCarrier" in stype(r)]
        elif station_type == "Megaship":
            results = [r for r in results if "Mega" in stype(r)]
        elif station_type == "Stronghold":
            results = [r for r in results if "Stronghold" in stype(r)]
        if large_pad:
            results = [r for r in results if r.get('maxLandingPadSize') == 3]
        return self.app._filter_results_by_age(results, max_age)

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

    def _failed(self, err: str) -> None:
        self.search_btn.config(state="normal")
        self.status_label.config(text=t('marketplace.search_failed').format(error=err))

    def _complete(self, stations, mineral_count: int) -> None:
        from datetime import datetime, timezone
        app = self.app
        self.search_btn.config(state="normal")
        self.tree.delete(*self.tree.get_children())
        if not stations:
            self.status_label.config(text=t('marketplace.no_results'))
            return
        from system_finder_api import SystemFinderAPI
        pp_names = list({s['info'].get('systemName') for s in stations if s['info'].get('systemName')})
        pp_data = SystemFinderAPI._batch_get_powerplay(pp_names) if pp_names else {}

        def powerstate(system):
            e = pp_data.get(system, {})
            power, state = e.get('controlling_power', ''), e.get('power_state', '')
            if power == '~none~':
                return state or t('common.no_data')
            return " / ".join(x for x in (power, state) if x) or t('common.no_data')

        now = datetime.now(timezone.utc)
        pad_map = {0: '?', 1: 'S', 2: 'M', 3: 'L'}

        def age(r):
            try:
                diff = now - datetime.fromisoformat(r.get('updatedAt', '').replace('Z', '+00:00'))
                mins = diff.total_seconds() / 60
                return f"{int(mins)}m" if mins < 60 else f"{int(mins / 60)}h" if mins < 1440 else f"{int(mins / 1440)}d"
            except Exception:
                return "?"

        for s in stations:
            info = s['info']
            dist = info.get('distance')
            ls = info.get('distanceToArrival')
            parent = self.tree.insert("", "end", open=True, text="", values=(
                f"{info.get('systemName', '')} / {info.get('stationName', '')[:25]}",
                                pad_map.get(info.get('maxLandingPadSize'), '?'),
                f"{dist:.1f}" if dist is not None else "-",
                f"{int(ls):,}" if ls is not None else "?", "", "",
                powerstate(info.get('systemName', '')), ""))
            for mineral, r in sorted(s['minerals'].items(), key=lambda kv: -kv[1].get('sellPrice', 0)):
                self.tree.insert(parent, "end", text=app._commodity_map.get(mineral, mineral), values=(
                    "", "", "", "", f"{r.get('demand', 0):,}", f"{r.get('sellPrice', 0):,} CR", "", age(r)))
        self.status_label.config(text=t('marketplace.multi_found').format(count=len(stations)))
