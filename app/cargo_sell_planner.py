"""Whole-hold sale plans using reported market prices and demand."""
from ui.striped_treeview import StripedTreeview
import math
import threading
import tkinter as tk
import tkinter.font as tkfont
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from itertools import combinations
from tkinter import ttk

from localization import t
from ui.search_control import SearchControl
from marketplace_api import MarketplaceAPI
from config import _load_cfg, update_config_value
from ui.tooltip import ToolTip, add_header_tooltips
from column_visibility_helper import ColumnVisibilityMixin
from core.constants import get_menu_colors
from app_utils import create_action_button, format_market_station_type, open_system_website


def sale_cargo(cargo, missions):
    normalize = MarketplaceAPI.normalize_commodity_name
    reserved = {}
    for mission in missions:
        name = mission.get('commodity_raw') or mission.get('commodity', '')
        name = normalize(name.removeprefix('$').removesuffix('_name;'))
        reserved[name] = reserved.get(name, 0) + max(0, mission['count'] - mission.get('delivered', 0))
    available, protected = {}, {}
    for name, count in cargo.items():
        if not isinstance(count, (int, float)) or count <= 0:
            continue
        key = normalize(name)
        if key in ('drones', 'limpet', 'limpets', 'unknowncargo'):
            continue
        keep = min(count, reserved.get(key, 0))
        reserved[key] = max(0, reserved.get(key, 0) - keep)
        if keep:
            protected[name] = keep
        if count > keep:
            available[name] = count - keep
    return available, protected


def _distance(first, second):
    if first['systemName'].casefold() == second['systemName'].casefold():
        return 0.0
    if any(row.get(axis) is None for row in (first, second) for axis in ('systemX', 'systemY', 'systemZ')):
        return None
    return math.dist([float(first[k]) for k in ('systemX', 'systemY', 'systemZ')],
                     [float(second[k]) for k in ('systemX', 'systemY', 'systemZ')])


def build_plans(cargo, markets, is_cancelled=None):
    total_cargo = sum(cargo.values())
    stations = {}
    for name, rows in markets:
        for row in rows:
            if not row.get('systemName') or not row.get('stationName'):
                continue
            if row.get('sellPrice', 0) <= 0 or row.get('demand', 0) <= 0:
                continue
            key = (row['systemName'].casefold(), row['stationName'].casefold())
            station = stations.setdefault(key, {'info': row, 'prices': {}})
            old = station['prices'].get(name)
            if old is None or row.get('updatedAt', '') > old.get('updatedAt', ''):
                station['prices'][name] = row

    def make_plan(stops):
        sales, total, sold = [], 0, 0
        for name, count in cargo.items():
            remaining = count
            offers = sorted(((i, s['prices'][name]) for i, s in enumerate(stops) if name in s['prices']),
                            key=lambda offer: offer[1]['sellPrice'], reverse=True)
            for i, row in offers:
                qty = min(remaining, row['demand'])
                if qty:
                    sales.append({'stop': i, 'name': name, 'quantity': qty, 'row': row})
                    total += qty * row['sellPrice']
                    sold += qty
                    remaining -= qty
        if len(stops) == 2 and len({sale['stop'] for sale in sales}) < 2:
            return None
        distance = stops[0]['info'].get('distance')
        legs = [distance]
        if len(stops) == 2:
            leg = _distance(stops[0]['info'], stops[1]['info'])
            legs.append(leg)
            distance = distance + leg if distance is not None and leg is not None else None
        return {'stops': stops, 'sales': sales, 'total': total, 'sold': sold,
                'unsold': total_cargo - sold, 'distance': distance, 'legs': legs}

    singles = [make_plan([station]) for station in stations.values()]
    if not singles:
        return []
    score = lambda plan: (plan['total'], plan['sold'])
    best = max(singles, key=score)
    full = [plan for plan in singles if plan['unsold'] == 0]
    quick = min(full or singles, key=lambda plan: (plan['unsold'],
                plan['distance'] if plan['distance'] is not None else math.inf,
                plan['stops'][0]['info'].get('distanceToArrival') or 0))
    pair_best = None
    upper_total = sum(count * max((s['prices'].get(name, {}).get('sellPrice', 0) for s in stations.values()), default=0)
                      for name, count in cargo.items())
    # This ignores demand, so it is a safe upper bound on every two-station payout.
    pairs = () if score(best) >= (upper_total, total_cargo) else combinations(stations.values(), 2)
    for a, b in pairs:
        if is_cancelled and is_cancelled():
            break
        upper_pair = sum(count * max(a['prices'].get(name, {}).get('sellPrice', 0),
                                     b['prices'].get(name, {}).get('sellPrice', 0))
                         for name, count in cargo.items())
        if (upper_pair, total_cargo) <= score(pair_best or best):
            continue
        first, second = a, b
        if (b['info'].get('distance') if b['info'].get('distance') is not None else math.inf) < (
                a['info'].get('distance') if a['info'].get('distance') is not None else math.inf):
            first, second = b, a
        plan = make_plan([first, second])
        if plan and (pair_best is None or score(plan) > score(pair_best)):
            pair_best = plan
            if score(pair_best) >= (upper_total, total_cargo):
                break
    plans = [('one_stop', best), ('quick_sale', quick)]
    if pair_best and score(pair_best) > score(best):
        plans.append(('two_stops', pair_best))
    return plans


class CargoSellPlanner(ColumnVisibilityMixin):
    def __init__(self, frame, app):
        self.app = app
        self.frame = frame
        self.plans = {}
        self.destinations = {}
        self.snapshot = None
        self.preferences = _load_cfg().get('sell_hold', {})
        controls = ttk.Frame(frame, padding=10)
        controls.pack(fill='x')
        from ui.help_link import create_help_link
        heading = ttk.Frame(controls)
        heading.pack(fill='x')
        ttk.Label(heading, text=t('sell_hold.description'), wraplength=900).pack(side='left')
        create_help_link(heading, 'sell-my-hold', t('common.help_tooltip'), ToolTip).pack(side='left', padx=(6, 0))
        reference = ttk.Frame(controls)
        reference.pack(fill='x', pady=(8, 0))
        market_status = app.market_mining_status_label
        self.market_status_label = tk.Label(reference, text=market_status.cget('text'),
                                            fg=market_status.cget('fg'), bg=market_status.cget('bg'),
                                            font=app._scaled_font(8))
        self.market_status_label.pack(side='right', padx=(0, 15))
        ToolTip(self.market_status_label, t('tooltips.market_api_status'))
        ttk.Label(reference, text=t('marketplace.ref_system')).pack(side='left', padx=(0, 6))
        self.system_var = tk.StringVar(value=self.preferences.get('system', app.get_current_system() or ''))
        self.system_entry = ttk.Entry(reference, textvariable=self.system_var, width=30)
        self.system_entry.pack(side='left', padx=(0, 6))
        self.system_entry.bind('<Return>', lambda event: self.search())
        self.system_entry.bind('<FocusOut>', lambda event: self.system_entry.selection_clear())
        from system_autocomplete import SystemAutocomplete
        self._ac_system = SystemAutocomplete(self.system_entry, self.system_var, app)
        create_action_button(reference, text=t('marketplace.use_current'), command=self._use_current_system).pack(side='left')
        filters = ttk.Frame(controls)
        filters.pack(fill='x', pady=8)
        self.large = tk.BooleanVar(value=self.preferences.get('large_pads', app.marketplace_large_pad_only.get()))
        self.carriers = tk.BooleanVar(value=self.preferences.get('exclude_carriers', True))
        self.radius = tk.StringVar(value=self.preferences.get('radius', '150'))
        saved_age = self.preferences.get('age')
        self.age = tk.StringVar(value=app._age_map.get(saved_age, app.marketplace_max_age.get()))
        ttk.Label(filters, text=t('sell_hold.radius')).pack(side='left')
        self.radius_combo = ttk.Combobox(filters, textvariable=self.radius, values=('50', '100', '150', '250', '500'),
                                        state='readonly', width=6)
        self.radius_combo.pack(side='left', padx=6)
        ttk.Checkbutton(filters, text=t('marketplace.large_pads'), variable=self.large).pack(side='left', padx=8)
        ttk.Checkbutton(filters, text=t('marketplace.exclude_carriers'), variable=self.carriers).pack(side='left', padx=8)
        ttk.Label(filters, text=t('marketplace.max_age')).pack(side='left')
        self.age_combo = ttk.Combobox(filters, textvariable=self.age, values=[app._age_map[k] for k in app._age_order],
                                     state='readonly', width=12)
        self.age_combo.pack(side='left', padx=6)
        for combo in (self.radius_combo, self.age_combo):
            combo.bind('<<ComboboxSelected>>', lambda event: event.widget.selection_clear(), add='+')
            combo.bind('<FocusOut>', lambda event: event.widget.selection_clear(), add='+')
        self.button = create_action_button(filters, primary=True, text=t('marketplace.search'), command=self.search)
        self.button.pack(side='left', padx=8)
        self.status = ttk.Label(controls, wraplength=1000)
        self.summary = ttk.Label(controls, wraplength=1000)
        ttk.Label(frame, text=t('sell_hold.notice'), wraplength=1000).pack(side='bottom', anchor='w', padx=10, pady=6)
        self.tables_paned = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        self.tables_paned.pack(fill='both', expand=True, padx=10, pady=5)
        options_pane = ttk.Frame(self.tables_paned)
        details_pane = ttk.Frame(self.tables_paned)
        self.tables_paned.add(options_pane, weight=1)
        self.tables_paned.add(details_pane, weight=2)
        self.tree = self._table(options_pane, ('plan', 'route', 'type', 'payout', 'sold', 'unsold', 'distance', 'arrival', 'extra'),
                                (130, 350, 150, 130, 75, 75, 100, 150, 130), 5)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.details = self._table(details_pane, ('stop', 'type', 'leg_distance', 'commodity', 'quantity', 'price', 'demand', 'arrival', 'updated'),
                                   (330, 150, 100, 180, 80, 110, 100, 100, 180), 10)
        for variable in (self.system_var, self.large, self.carriers, self.radius, self.age):
            variable.trace_add('write', self._save_preferences)
        self.tables_paned.bind('<ButtonRelease-1>', self._save_layout)
        self.tables_paned.bind('<Map>', self._restore_split)
        self._poll()

    def _clear_field_selections(self):
        for widget in (self.system_entry, self.radius_combo, self.age_combo):
            widget.selection_clear()

    def _save_preferences(self, *args):
        self.preferences.update(system=self.system_var.get(), large_pads=self.large.get(),
                                exclude_carriers=self.carriers.get(), radius=self.radius.get(),
                                age=self.app._age_rev_map.get(self.age.get(), self.age.get()))
        update_config_value('sell_hold', self.preferences.copy())

    def _save_layout(self, event=None):
        self.preferences['split'] = self.tables_paned.sashpos(0) / max(1, self.tables_paned.winfo_height())
        for name, tree in (('plan_widths', self.tree), ('detail_widths', self.details)):
            self.preferences[name] = {col: tree.column(col, 'width') for col in tree['columns']}
        self._save_preferences()

    def _restore_split(self, event=None):
        self.tables_paned.unbind('<Map>')
        if 'split' in self.preferences:
            self.tables_paned.after_idle(lambda: self.tables_paned.sashpos(
                0, int(self.preferences['split'] * self.tables_paned.winfo_height())))

    def _table(self, parent, columns, widths, height):
        config_key = 'sell_hold_plans' if columns[0] == 'plan' else 'sell_hold_details'
        header = ttk.Frame(parent)
        header.pack(fill='x', padx=10, pady=(5, 0))
        title_key = 'sale_options' if columns[0] == 'plan' else 'details'
        ttk.Label(header, text=t('sell_hold.' + title_key),
                  font=self.app._scaled_font(10, 'bold')).pack(side='left')
        self._cv_add_columns_button(header, config_key)
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True, padx=10, pady=5)
        tree = StripedTreeview(box, columns=columns, show='headings', height=height,
                           selectmode='browse', style='Marketplace.Treeview')
        heading_font = tkfont.Font(font=self.app._scaled_font(9, 'bold'))
        shared_headers = {'route': 'location', 'stop': 'location', 'distance': 'distance', 'leg_distance': 'distance',
                          'demand': 'demand', 'price': 'price', 'updated': 'updated', 'type': 'type'}
        saved_widths = self.preferences.get('plan_widths' if columns[0] == 'plan' else 'detail_widths', {})
        for col, width in zip(columns, widths):
            key = 'marketplace.' + shared_headers[col] if col in shared_headers else 'sell_hold.' + col
            text = t(key)
            tree.heading(col, text=text, anchor='w')
            minimum = max(heading_font.measure(text) + self.app._scaled_px(24), self.app._scaled_px(50))
            tree.column(col, width=max(saved_widths.get(col, self.app._scaled_px(width)), minimum),
                        anchor='w', minwidth=minimum, stretch=False)
        self.setup_column_visibility(
            tree=tree, columns=columns,
            default_widths={col: tree.column(col, 'width') for col in columns},
            config_key=config_key, use_displaycolumns=True, allow_reorder=True)
        if not hasattr(self, '_context_handlers'):
            self._context_handlers = {}
        self._context_handlers[config_key] = lambda event: self._system_menu(event, tree)
        tree.bind('<Double-1>', lambda event: self._open_row_system(event, tree))
        add_header_tooltips(tree, lambda column: t('sell_hold.header_tips.' + column))
        tree.bind('<ButtonRelease-1>', self._save_layout, add='+')
        y = ttk.Scrollbar(box, orient='vertical', command=tree.yview)
        x = ttk.Scrollbar(box, orient='horizontal', command=tree.xview)
        tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        tree.grid(row=0, column=0, sticky='nsew')
        y.grid(row=0, column=1, sticky='ns')
        x.grid(row=1, column=0, sticky='ew')
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        return tree

    def _cargo(self):
        from mining_missions import get_mission_tracker
        monitor = self.app.cargo_monitor
        cargo, protected = sale_cargo(dict(monitor.cargo_items), get_mission_tracker().get_active_missions())
        return self.system_var.get().strip(), cargo, protected

    def _use_current_system(self):
        self._ac_system.suppress()
        self.system_var.set(self.app.get_current_system() or '')
        self._ac_system.unsuppress()
        self._ac_system.hide()

    def _poll(self):
        searching = getattr(self, '_search_control', None) and self._search_control.running
        if not searching and self.plans and self.snapshot is not None and self.snapshot != self._cargo():
            self.status.config(text=t('sell_hold.changed'))
        self.frame.after(1000, self._poll)

    def search(self):
        if not hasattr(self, '_search_control'):
            self._search_control = SearchControl(self.app, self.button, self.status)
        if self._search_control.running:
            self._search_control.stop()
            return
        self.status.pack(anchor='w')
        self.summary.pack(anchor='w', pady=4)
        system, cargo, protected = self._cargo()
        snapshot = (system, cargo, protected)
        self.summary.config(text=t('sell_hold.cargo').format(
            tons=sum(cargo.values()), reserved=sum(protected.values()), system=system or '?'))
        if not system or not cargo:
            self.tree.delete(*self.tree.get_children())
            self.details.delete(*self.details.get_children())
            self.plans.clear()
            self.destinations.clear()
            self.status.config(text=t('sell_hold.empty'))
            return
        self._search_control.start()
        self.status.config(text=t('sell_hold.searching'))
        options = (int(self.radius.get()), self.app._age_rev_map.get(self.age.get(), self.age.get()),
                   self.carriers.get(), self.large.get())
        threading.Thread(target=self._worker, args=(snapshot, options), daemon=True).start()

    def _worker(self, snapshot, options):
        control = self._search_control
        try:
            system, cargo, protected = snapshot
            radius, age, carriers, large = options
            def fetch(name):
                if control.is_cancelled():
                    return name, []
                rows = MarketplaceAPI.search_buyers(name, system, radius, 30, carriers, is_cancelled=control.is_cancelled)
                rows = MarketplaceAPI.filter_results(rows, 'All', age, carriers, large)
                rows = [row for row in rows if row.get('distance') is not None and row['distance'] <= radius]
                return name, rows
            with ThreadPoolExecutor(max_workers=3) as pool:
                markets = list(pool.map(fetch, cargo))
            plans = build_plans(cargo, markets, is_cancelled=control.is_cancelled)
            control.complete(plans, lambda rows: self._complete(snapshot, rows))
        except Exception as exc:
            message = str(exc)
            control.failed(message)


    def _complete(self, snapshot, plans):
        self.button.config(state='normal')
        changed = snapshot != self._cargo()
        self.snapshot = snapshot
        self.status.config(text=t('sell_hold.changed') if changed and plans else
                           t('sell_hold.results') if plans else t('marketplace.no_results'))
        self.tree.delete(*self.tree.get_children())
        self.details.delete(*self.details.get_children())
        self.plans.clear()
        self.destinations.clear()
        baseline = plans[0][1] if plans else None
        for name, plan in plans:
            route = ' → '.join(s['info']['systemName'] + ' / ' + s['info']['stationName'] for s in plan['stops'])
            distance = f"{plan['distance']:.1f}" if plan['distance'] is not None else '?'
            station_types = ' → '.join(format_market_station_type(s['info'].get('stationType')) for s in plan['stops'])
            arrival = ' → '.join(self._format_arrival(s['info'].get('distanceToArrival')) for s in plan['stops'])
            item = self.tree.insert('', 'end', values=(t('sell_hold.' + name), route, station_types,
                f"{plan['total']:,.0f}", plan['sold'], plan['unsold'], distance, arrival,
                f"{plan['total'] - baseline['total']:+,.0f}"))
            self.plans[item] = plan
        if self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])

    @staticmethod
    def _format_arrival(arrival):
        return f'{int(float(arrival)):,}' if arrival is not None else '?'

    def select(self, event=None):
        self.details.delete(*self.details.get_children())
        self.destinations.clear()
        selection = self.tree.selection()
        if not selection or selection[0] not in self.plans:
            return
        plan = self.plans[selection[0]]
        for sale in sorted(plan['sales'], key=lambda sale: sale['stop']):
            row = sale['row']
            stop = plan['stops'][sale['stop']]['info']
            leg = plan['legs'][sale['stop']]
            try:
                stamp = datetime.fromisoformat(row['updatedAt'].replace('Z', '+00:00'))
                age = (datetime.now(timezone.utc) - stamp.replace(tzinfo=stamp.tzinfo or timezone.utc)).total_seconds() / 3600
                updated = t('sell_hold.hours').format(hours=max(0, age))
            except (ValueError, KeyError, TypeError):
                updated = '?'
            arrival = row.get('distanceToArrival')
            arrival_display = self._format_arrival(arrival)
            item = self.details.insert('', 'end', values=(
                f"{sale['stop'] + 1}. {stop['systemName']} / {stop['stationName']}",
                format_market_station_type(row.get('stationType')),
                f'{leg:.1f}' if leg is not None else '?',
                self.app._commodity_map.get(sale['name'], sale['name']), sale['quantity'],
                f"{row['sellPrice']:,.0f}", row['demand'], arrival_display, updated))
            self.destinations[item] = stop['systemName']

    def _row_systems(self, tree, item):
        if tree is self.tree:
            plan = self.plans.get(item)
            return list(dict.fromkeys(stop['info']['systemName'] for stop in plan['stops'])) if plan else []
        system = self.destinations.get(item)
        return [system] if system else []

    def _system_menu(self, event, tree):
        item = tree.identify_row(event.y)
        if not item or tree.identify_region(event.x, event.y) != 'cell':
            return
        tree.selection_set(item)
        systems = self._row_systems(tree, item)
        if not systems:
            return
        colors = get_menu_colors()
        menu = tk.Menu(tree, tearoff=0, **colors)
        for system in systems:
            target = menu
            if len(systems) > 1:
                target = tk.Menu(menu, tearoff=0, **colors)
                menu.add_cascade(label=system, menu=target)
            target.add_command(label=t('context_menu.copy_system'), command=lambda name=system: self.copy_system(name))
            target.add_separator()
            for site in ('inara', 'edsm', 'spansh'):
                target.add_command(label=t('context_menu.open_' + site),
                                   command=lambda name=system, service=site: self._open_system(name, service))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _open_row_system(self, event, tree):
        if tree.identify_region(event.x, event.y) != 'cell':
            return
        item = tree.identify_row(event.y)
        systems = self._row_systems(tree, item)
        if systems:
            tree.selection_set(item)
            self._open_system(systems[0], 'inara')

    _open_system = staticmethod(open_system_website)

    def copy_system(self, system=None):
        if system is None:
            selection = self.details.selection()
            system = self.destinations.get(selection[0]) if selection else None
        if system:
            self.app.clipboard_clear()
            self.app.clipboard_append(system)
