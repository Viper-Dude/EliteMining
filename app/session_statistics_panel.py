"""Saved-session statistics, location records and recent mining history."""
import csv
import logging
import os
import re
import threading
import tkinter as tk
import tkinter.font as tkfont
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Queue, Empty
from tkinter import ttk

from column_visibility_helper import ColumnVisibilityMixin, displayed_column
from app_utils import bind_mousewheel_recursive, open_system_website
from config import _load_cfg, update_config_value, scaled_font, scaled_px
from core.constants import get_menu_colors
from localization import t, get_material
from mining_statistics import session_date
from ui.tooltip import ToolTip, add_header_tooltips


def material_names(row):
    names = re.findall(r'(?:^|[,;])\s*([^:,;]+):', row.get('materials_breakdown', '').strip('"'))
    best = re.sub(r'\s*\([^)]*\)', '', row.get('best_material', '')).strip()
    if best and best.lower() not in ('unknown', 'none'):
        names.append(best)
    return sorted(set(name.strip() for name in names))


def prepare_sessions(rows, parse_elapsed, ship_lookup):
    prepared = []
    for source in rows:
        try:
            row = dict(source)
            row['_tph'] = float(row.get('overall_tph') or 0)
            row['_tons'] = float(row.get('total_tons') or 0)
            row['_asteroids'] = int(row.get('asteroids_prospected') or 0)
            row['_hit'] = float(row.get('hit_rate_percent') or 0)
            row['_hours'] = parse_elapsed(row.get('elapsed') or '')
            row['_stamp'] = session_date(row.get('timestamp_utc', ''))
            row['_materials'] = material_names(row)
            row['_ship'], row['_report'] = ship_lookup(row.get('system', ''), row.get('body', ''), row.get('timestamp_utc', ''))
            prepared.append(row)
        except (ValueError, TypeError):
            continue
    return prepared


def select_sessions(rows, ship='', mineral='', days=0, now=None):
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days) if days else None
    return [row for row in rows if (not ship or row['_ship'] == ship)
            and (not mineral or mineral in row['_materials'])
            and (not cutoff or row['_stamp'] and row['_stamp'] >= cutoff)]


def location_summary(rows, mineral=''):
    groups = defaultdict(list)
    for row in rows:
        if row['_tons'] > 0 and row.get('system', '').strip():
            key = (row['system'].strip().casefold(), row.get('body', '').strip().casefold())
            groups[key].append(row)
    ranked, recent = [], []
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    for sessions in groups.values():
        latest = max(sessions, key=lambda row: row['_stamp'] or oldest)
        best = max(sessions, key=lambda row: row['_tph'])
        entry = {'latest': latest, 'best': best, 'count': len(sessions),
                 'hours': sum(row['_hours'] for row in sessions),
                 'avg': sum(row['_tph'] for row in sessions) / len(sessions),
                 'low': min(row['_tph'] for row in sessions)}
        finds = [row.get('_performance', {}).get(mineral, {}) for row in sessions] if mineral else []
        finds = [find for find in finds if 'hits' in find]
        samples = [(find, max(0, find['hits'] - find.get('core_hits', 0))) for find in finds]
        surface = [(find, count) for find, count in samples if count and 'avg' in find]
        hits = sum(count for find, count in surface)
        entry['mineral_avg'] = sum(find['avg'] * count for find, count in surface) / hits if hits else None
        entry['mineral_best'] = max((find['best'] for find, count in samples if count and 'best' in find), default=None)
        entry['mineral_hits'] = sum(find['hits'] for find in finds) if finds else None
        ranked.append(entry)
        if latest['_stamp']:
            recent.append(entry)
    ranked.sort(key=lambda entry: entry['best']['_tph'], reverse=True)
    recent.sort(key=lambda entry: entry['latest']['_stamp'], reverse=True)
    return ranked[:10], recent[:10]


def recent_progress(rows):
    ordered = sorted((row for row in rows if row['_stamp'] and row['_tons'] > 0),
                     key=lambda row: row['_stamp'], reverse=True)
    def metrics(group):
        if not group:
            return None
        asteroid_sessions = [row for row in group if row['_asteroids'] > 0]
        return (sum(row['_tph'] for row in group) / len(group),
                sum(row['_hit'] for row in group) / len(group),
                sum(row['_tons'] / row['_asteroids'] for row in asteroid_sessions) / len(asteroid_sessions)
                if asteroid_sessions else None)
    return len(ordered[:10]), len(ordered[10:20]), metrics(ordered[:10]), metrics(ordered[10:20])


class SessionStatisticsPanel(ColumnVisibilityMixin):
    def __init__(self, parent, owner):
        self.owner = owner
        self.parent = parent
        self.rows = []
        self.visited_rows = []
        self.lookups = {}
        self.loading = False
        self.preferences = _load_cfg().get('session_statistics', {})
        self._initial_mineral = self.preferences.get('mineral', '')
        controls = ttk.Frame(parent)
        controls.pack(fill='x', pady=(0, 8))
        self.ship = tk.StringVar(value=self.preferences.get('ship') or t('statistics_expanded.all_ships'))
        self.mineral = tk.StringVar(value=self.preferences.get('mineral', ''))
        self.period = tk.StringVar()
        self.periods = {t('reports.all_time'): 0, t('reports.last_7_days'): 7,
                        t('reports.last_30_days'): 30, t('reports.last_90_days'): 90}
        self.period.set(next((key for key, value in self.periods.items()
                              if value == self.preferences.get('days', 0)), next(iter(self.periods))))
        for key, variable, width in [('ship', self.ship, 25), ('mineral', self.mineral, 22), ('period', self.period, 16)]:
            ttk.Label(controls, text=t('statistics_expanded.' + key)).pack(side='left', padx=(0, 5))
            combo = ttk.Combobox(controls, textvariable=variable, width=width, state='readonly')
            combo.pack(side='left', padx=(0, 12))
            combo.bind('<<ComboboxSelected>>', lambda event: (event.widget.selection_clear(), self.apply_filters()))
            setattr(self, key + '_combo', combo)
        self.period_combo.configure(values=list(self.periods))
        self.refresh_button = ttk.Button(controls, text=t('statistics_expanded.refresh'), command=self.reload)
        self.refresh_button.pack(side='right')
        self.note = ttk.Label(parent, text=t('statistics_expanded.scope'), wraplength=1000)
        self.note.pack(anchor='w', pady=(0, 5))
        parent.bind('<Configure>', lambda event: self.note.configure(
            wraplength=max(scaled_px(100), min(event.width - scaled_px(20), scaled_px(800)))), add='+')
        self.book = ttk.Notebook(parent)
        self.book.pack(fill='both', expand=True)
        overview = ttk.Frame(self.book, padding=8)
        self.book.add(overview, text=t('statistics_expanded.overview'))
        from config import load_theme
        from ui.theme import get_theme_colors
        colors = get_theme_colors(load_theme())
        self.overview_canvas = tk.Canvas(overview, bg=colors['bg'], highlightthickness=0)
        scroll = ttk.Scrollbar(overview, command=self.overview_canvas.yview)
        self.overview_canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self.overview_canvas.pack(fill='both', expand=True)
        self.overview_content = tk.Frame(self.overview_canvas, bg=colors['bg'])
        self.overview_window = self.overview_canvas.create_window(
            (0, 0), window=self.overview_content, anchor='nw')
        for name in ('overview', 'progress'):
            text = tk.Text(self.overview_content, width=1, height=1, wrap='word', relief='flat',
                           borderwidth=0, highlightthickness=0, font=scaled_font(10), state='disabled',
                           bg=colors['bg'], fg=colors['fg'], insertbackground=colors['fg'],
                           padx=scaled_px(12), pady=scaled_px(12))
            text.tag_configure('heading', font=scaled_font(11, 'bold'))
            text.bind('<Configure>', lambda event: self._fit_overview_text(event.widget))
            setattr(self, name, text)
        self.overview_content.bind('<Configure>', lambda event: self.overview_canvas.configure(
            scrollregion=self.overview_canvas.bbox('all')))
        self.overview_canvas.bind('<Configure>', self._layout_overview)
        bind_mousewheel_recursive(self.overview_canvas, self._scroll_overview)
        self.best_tree = self._table('best_locations', ('system', 'body', 'distance', 'ls', 'mineral_avg', 'mineral_best', 'mineral_hits', 'best', 'avg', 'low', 'count', 'hours', 'duration', 'date', 'mineral'))
        self.recent_tree = self._table('recent_locations', ('system', 'body', 'distance', 'ls', 'date', 'mineral', 'mineral_avg', 'mineral_best', 'mineral_hits', 'tph', 'ship', 'duration', 'count', 'hours'))
        self.visited_tree = self._table('recent_systems', ('system', 'date', 'distance', 'visits'))
        self.book.bind('<<NotebookTabChanged>>', self._on_tab_changed)
        self.parent.bind('<Map>', self._on_map, add='+')
        self.parent.after_idle(self.reload)

    def _layout_overview(self, event):
        self.overview_canvas.itemconfigure(self.overview_window, width=event.width)
        wide = event.width >= scaled_px(850)
        gap = scaled_px(8)
        self.overview_content.columnconfigure(0, weight=1, uniform='overview')
        self.overview_content.columnconfigure(1, weight=1 if wide else 0, uniform='overview' if wide else '')
        self.overview.grid(row=0, column=0, sticky='new', padx=(0, gap if wide else 0))
        self.progress.grid(row=0 if wide else 1, column=1 if wide else 0,
                           sticky='new', pady=(0 if wide else gap, 0))

    def _fit_overview_text(self, widget):
        pixels = int(widget.tk.call(widget, 'count', '-update', '-ypixels', '1.0', 'end'))
        line_height = tkfont.Font(font=widget.cget('font')).metrics('linespace')
        height = max(1, (pixels + line_height - 1) // line_height)
        if int(widget.cget('height')) != height:
            widget.configure(height=height)

    def _scroll_overview(self, event):
        self.overview_canvas.yview_scroll(int(-event.delta / 120), 'units')
        return 'break'

    def _on_map(self, event):
        if event.widget is self.parent:
            self.reload()

    def _on_tab_changed(self, event=None):
        self._update_filter_controls()
        if self._visits_selected():
            self.reload()

    def _visits_selected(self):
        return self.book.select() == str(self.visited_tree.master.master)

    def _update_filter_controls(self):
        visits = self._visits_selected()
        for combo in (self.ship_combo, self.mineral_combo, self.period_combo):
            combo.configure(state='disabled' if visits else 'readonly')
        self.note.configure(text=t('statistics_expanded.visits_scope' if visits else 'statistics_expanded.scope'))

    def _table(self, name, columns):
        pane = ttk.Frame(self.book, padding=8)
        self.book.add(pane, text=t('statistics_expanded.' + name))
        header = ttk.Frame(pane)
        header.pack(fill='x')
        ttk.Label(header, text=t('statistics_expanded.' + name), font=scaled_font(10, 'bold')).pack(side='left')
        key = 'statistics_' + name
        self._cv_add_columns_button(header, key)
        table = ttk.Frame(pane)
        table.pack(fill='both', expand=True, pady=(5, 0))
        tree = ttk.Treeview(table, columns=columns + ('_spacer',), show='headings', selectmode='browse')
        heading_font = tkfont.Font(font=scaled_font(9, 'bold'))
        for col in columns:
            text = t('statistics_expanded.col_minerals_mined' if col == 'mineral'
                     else 'statistics_expanded.col_' + col)
            minimum = max(heading_font.measure(text) + scaled_px(24), scaled_px(60))
            anchor = 'center' if col in ('tph', 'count', 'hours') else 'w'
            tree.heading(col, text=text, anchor=anchor, command=lambda c=col, widget=tree: self._sort(widget, c))
            width = scaled_px(210 if col == 'system' else 150 if col in ('body', 'ship', 'mineral', 'date') else 100)
            saved = self.preferences.get(name + '_widths', {}).get(col, width)
            tree.column(col, width=max(saved, minimum), minwidth=minimum, anchor=anchor, stretch=False)
        tree.heading('_spacer', text='')
        tree.column('_spacer', width=scaled_px(20), minwidth=scaled_px(20), stretch=True)
        self.setup_column_visibility(tree, columns, {col: tree.column(col, 'width') for col in columns},
                                     key, use_displaycolumns=True, allow_reorder=True)
        self._context_handlers = getattr(self, '_context_handlers', {})
        self._context_handlers[key] = lambda event: self._menu(event, tree)
        tree.bind('<Double-1>', lambda event: self._open_clicked(event, tree))
        tree.bind('<Control-c>', lambda event: self._copy_selected_system(tree))
        tree.bind('<ButtonRelease-1>', lambda event: self._save_widths(tree, name), add='+')
        report_tips = {'system': 'system', 'body': 'body', 'ship': 'ship', 'date': 'datetime',
                       'duration': 'duration', 'tph': 'tph'}
        if name == 'recent_systems':
            report_tips.pop('date')
        add_header_tooltips(tree, lambda column: t('tooltips.reports_' + report_tips[column])
                            if column in report_tips else t('statistics_expanded.header_tips.' +
                            ('visit_date' if name == 'recent_systems' and column == 'date' else column)))
        x = ttk.Scrollbar(table, orient='horizontal', command=tree.xview)
        y = ttk.Scrollbar(table, orient='vertical', command=tree.yview)
        tree.configure(xscrollcommand=x.set, yscrollcommand=y.set)
        tree.grid(row=0, column=0, sticky='nsew')
        x.grid(row=1, column=0, sticky='ew')
        y.grid(row=0, column=1, sticky='ns')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        if name != 'recent_systems':
            ToolTip(header, t('statistics_expanded.ranking_help' if name == 'best_locations' else 'statistics_expanded.recent_help'))
        self.lookups[tree] = {}
        return tree

    def _save_widths(self, tree, name):
        self.preferences[name + '_widths'] = {col: tree.column(col, 'width') for col in tree['columns'] if col != '_spacer'}
        update_config_value('session_statistics', self.preferences.copy())

    def reload(self):
        if self.loading:
            return
        self.loading = True
        self.refresh_button.configure(state='disabled')
        app = self.owner.main_app
        current_system = app.get_current_system() if app else None
        path = Path(self.owner.reports_dir) / 'sessions_index.csv'
        if not path.exists() and any(path.parent.glob('Session_*.txt')):
            try:
                self.owner._rebuild_csv_from_files_tab(str(path), silent=True)
            except Exception:
                logging.getLogger('EliteMining').exception('Could not rebuild session index')
                self._load_failed()
                return
        # Startup idle callbacks can run before mainloop; keep all Tk calls on the UI thread.
        results = Queue()
        def worker():
            try:
                if path.exists():
                    with path.open(encoding='utf-8-sig', newline='') as stream:
                        rows = prepare_sessions(csv.DictReader(stream), self.owner._parse_elapsed_to_hours,
                                                self.owner._get_ship_name_from_session)
                    from mining_statistics import parse_mineral_performance
                    for row in rows:
                        row['_performance'] = parse_mineral_performance(row['_report']) if row['_report'] else {}
                    self._add_location_distances(rows, current_system)
                else:
                    rows = []
                user_db = getattr(getattr(app, 'cargo_monitor', None), 'user_db', None)
                visited = user_db.get_recent_visited_systems(limit=20) if user_db else []
                for row in visited:
                    row['_stamp'] = session_date(row['last_visit_date'])
                self._add_location_distances(visited, current_system, include_ls=False)
                results.put(('loaded', (rows, visited)))
            except Exception:
                logging.getLogger('EliteMining').exception('Could not load session statistics')
                results.put(('failed', None))
        threading.Thread(target=worker, daemon=True).start()
        self.parent.after(50, lambda: self._poll_load(results))

    def _poll_load(self, results):
        try:
            status, rows = results.get_nowait()
        except Empty:
            self.parent.after(50, lambda: self._poll_load(results))
            return
        if status == 'loaded':
            self._loaded(*rows)
        else:
            self._load_failed()

    def _add_location_distances(self, rows, current_system, include_ls=True):
        if not rows:
            return
        app = self.owner.main_app
        finder = getattr(app, 'ring_finder', None)
        user_db = getattr(getattr(app, 'cargo_monitor', None), 'user_db', None)
        coordinates, locations = {}, {}
        def coords(system):
            if not system or not finder:
                return None
            if system not in coordinates:
                value = finder.systems_data.get(system.lower()) or finder._get_system_coords_from_galaxy_db(system)
                if not value and user_db:
                    visited = user_db._get_coordinates_from_visited_systems(system)
                    value = dict(zip(('x', 'y', 'z'), visited)) if visited else None
                if not value and user_db:
                    for hotspot in user_db.get_system_hotspots(system):
                        if all(hotspot.get(axis + '_coord') is not None for axis in ('x', 'y', 'z')):
                            value = {axis: hotspot[axis + '_coord'] for axis in ('x', 'y', 'z')}
                            break
                if not value:
                    value = finder._get_system_coords_from_edsm(system)
                coordinates[system] = value
            return coordinates[system]
        reference = coords(current_system)
        for row in rows:
            system, body = row.get('system', ''), row.get('body', '')
            key = (system, body)
            if key not in locations:
                target = coords(system)
                distance = (0.0 if current_system and system.casefold() == current_system.casefold()
                            else finder._calculate_distance(reference, target) if reference and target else None)
                ls = user_db.get_ls_distance(system, body) if user_db and include_ls else None
                locations[key] = distance, ls
            row['_distance'], row['_ls'] = locations[key]

    def _load_failed(self):
        self.loading = False
        self.refresh_button.configure(state='normal')
        self.note.configure(text=t('statistics_expanded.load_failed'))

    def _loaded(self, rows, visited=None):
        self.loading = False
        self.rows = rows
        self.visited_rows = visited or []
        self.refresh_button.configure(state='normal')
        ships = sorted({row['_ship'] for row in rows if row['_ship']})
        font = tkfont.Font(font=self.ship_combo.cget('font'))
        char_width = max(1, font.measure('0'))
        width = max(25, (max((font.measure(name) for name in ships), default=0) + char_width - 1) // char_width + 2)
        self.ship_combo.configure(values=[t('statistics_expanded.all_ships')] + ships, width=width)
        minerals = sorted({name for row in rows for name in row['_materials']})
        self.mineral_map = {get_material(name): name for name in minerals}
        self.mineral_combo.configure(values=[''] + sorted(self.mineral_map))
        if self._initial_mineral:
            self.mineral.set(get_material(self._initial_mineral))
            self._initial_mineral = ''
        self.apply_filters()
        self._show_visited_systems()

    def _show_visited_systems(self):
        tree = self.visited_tree
        tree.delete(*tree.get_children())
        self.lookups[tree].clear()
        for row in self.visited_rows:
            values = dict(system=row['system'], date=self._date(row), visits=row['visits'],
                          distance=f"{row['_distance']:.1f}" if row.get('_distance') is not None else '—')
            item = tree.insert('', 'end', values=[values.get(col, '') for col in tree['columns']])
            self.lookups[tree][item] = row
        if getattr(tree, '_sort_column', None):
            tree._sort_reverse = not tree._sort_reverse
            self._sort(tree, tree._sort_column)

    @staticmethod
    def _date(row):
        return row['_stamp'].astimezone().strftime('%Y-%m-%d %H:%M') if row['_stamp'] else '—'

    def apply_filters(self):
        days = self.periods[self.period.get()]
        mineral = getattr(self, 'mineral_map', {}).get(self.mineral.get(), self.mineral.get())
        ship = '' if self.ship.get() == t('statistics_expanded.all_ships') else self.ship.get()
        self.preferences.update(ship=ship, mineral=mineral, days=days)
        update_config_value('session_statistics', self.preferences.copy())
        rows = select_sessions(self.rows, ship, mineral, days)
        stats = self.owner._calculate_session_statistics(rows)
        self._update_filter_controls()
        self._overview(rows, stats)
        best, recent = location_summary(rows, mineral)
        for tree in (self.best_tree, self.recent_tree):
            tree.delete(*tree.get_children())
            self.lookups[tree].clear()
        for tree, entries, field in ((self.best_tree, best, 'best'), (self.recent_tree, recent, 'latest')):
            for entry in entries:
                row = entry[field]
                values = {'system': row['system'], 'body': row.get('body', ''), 'date': self._date(row),
                          'mineral_avg': f"{entry['mineral_avg']:.1f}" if entry['mineral_avg'] is not None else '—',
                          'mineral_best': f"{entry['mineral_best']:.1f}" if entry['mineral_best'] is not None else '—',
                          'mineral_hits': entry['mineral_hits'] if entry['mineral_hits'] is not None else '—',
                          'distance': f"{row['_distance']:.1f}" if row.get('_distance') is not None else '—',
                          'ls': f"{row['_ls']:.0f}" if row.get('_ls') is not None else '—',
                          'mineral': ', '.join(get_material(name) for name in row['_materials']),
                          'tph': f"{row['_tph']:.1f}", 'best': f"{entry['best']['_tph']:.1f}",
                          'avg': f"{entry['avg']:.1f}", 'low': f"{entry['low']:.1f}", 'count': entry['count'],
                          'hours': f"{entry['hours']:.2f}", 'duration': row.get('elapsed', ''), 'ship': row['_ship']}
                item = tree.insert('', 'end', values=[values.get(col, '') for col in tree['columns']])
                self.lookups[tree][item] = row
            if getattr(tree, '_sort_column', None):
                tree._sort_reverse = not tree._sort_reverse
                self._sort(tree, tree._sort_column)

    def _overview(self, rows, stats):
        def label(key, value):
            return t('statistics.' + key) + ' ' + str(value)
        count = len(rows)
        avg_tons = stats.get('total_tonnage', 0) / count if count else 0
        avg_seconds = round(stats.get('total_time_hours', 0) * 3600 / count) if count else 0
        hours, remainder = divmod(avg_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        lines = [t('statistics.session_overview'), '']
        for key, value in [('total_sessions', len(rows)), ('total_time', f"{stats.get('total_time_hours', 0):.2f} h"),
                           ('avg_session_duration', f'{hours:02}:{minutes:02}:{seconds:02}'),
                           ('total_tonnage', f"{stats.get('total_tonnage', 0):,.1f} t"),
                           ('avg_session_tons', f'{avg_tons:,.1f} t'),
                           ('avg_tph', f"{sum(row['_tph'] for row in rows) / len(rows) if rows else 0:.1f}"), ('systems_mined', stats.get('unique_systems', 0)),
                           ('total_asteroids', stats.get('total_asteroids', 0)),
                           ('avg_hit_rate', f"{sum(row['_hit'] for row in rows) / len(rows) if rows else 0:.1f}%")]:
            lines.append(label(key, value))
        lines.extend(['', t('statistics_expanded.records'), '', t('statistics_expanded.record_help'), ''])
        if rows:
            record = max(rows, key=lambda row: row['_tph'])
            lines += [t('statistics_expanded.record').format(tph=record['_tph'], system=record.get('system', ''),
                      body=record.get('body', ''), duration=record.get('elapsed', ''), date=self._date(record)),
                      label('most_mined_ton_session', f"{max(row['_tons'] for row in rows):,.1f} t"),
                      label('most_mined_system', stats.get('most_mined_system', '—')),
                      label('most_mined_minerals', get_material(stats.get('most_collected_material', '')))]
        else:
            lines.append(t('statistics_expanded.no_sessions'))
        n, previous_n, current, previous = recent_progress(rows)
        progress = [t('statistics_expanded.progress'), '',
                    t('statistics_expanded.progress_help').format(current=n, previous=previous_n), '']
        if current:
            for i, key in enumerate(('tph', 'hit', 'tpa')):
                now_value = current[i]
                old_value = previous[i] if previous else None
                progress.append(t('statistics_expanded.metric_' + key) + ': ' +
                             ('—' if now_value is None else f'{now_value:.1f}') + ' / ' +
                             ('—' if old_value is None else f'{old_value:.1f}') +
                             (f' ({now_value - old_value:+.1f})' if now_value is not None and old_value is not None else ''))
        self.progress.configure(state='normal')
        self.progress.delete('1.0', 'end')
        self.progress.insert('1.0', '\n'.join(progress))
        self.progress.tag_add('heading', '1.0', '1.end')
        self.progress.configure(state='disabled')
        self.parent.after_idle(lambda: self._fit_overview_text(self.progress))
        self.overview.configure(state='normal')
        for tag in self.overview.tag_names():
            if tag.startswith('location_'):
                self.overview.tag_delete(tag)
        self.overview.delete('1.0', 'end')
        self.overview.insert('1.0', '\n'.join(lines))
        self.overview.tag_add('body', '1.0', 'end')
        for heading in (t('statistics.session_overview'), t('statistics_expanded.records')):
            position = self.overview.search(heading, '1.0', stopindex='end', exact=True)
            if position:
                self.overview.tag_add('heading', position, f'{position}+{len(heading)}c')
        if rows:
            self._link_location('location_record', f"{record.get('system', '')} | {record.get('body', '')}",
                                record.get('system', ''))
            system = stats.get('most_mined_system', '')
            prefix = t('statistics.most_mined_system') + ' '
            self._link_location('location_most', prefix + system, system, len(prefix))
        self.overview.configure(state='disabled')
        self.parent.after_idle(lambda: self._fit_overview_text(self.overview))

    def _link_location(self, tag, text, system, offset=0):
        if not system:
            return
        position = self.overview.search(text, '1.0', stopindex='end', exact=True)
        if not position:
            return
        self.overview.tag_add(tag, f'{position}+{offset}c', f'{position}+{offset + len(system)}c')
        self.overview.tag_configure(tag, underline=True)
        self.overview.tag_bind(tag, '<Double-1>', lambda event: self._copy(system))
        self.overview.tag_bind(tag, '<Button-3>', lambda event: self._copy_menu(event, system))
        self.overview.tag_bind(tag, '<Enter>', lambda event: self.overview.configure(cursor='hand2'))
        self.overview.tag_bind(tag, '<Leave>', lambda event: self.overview.configure(cursor='xterm'))

    def _copy_menu(self, event, system):
        menu = tk.Menu(self.overview, tearoff=0, **get_menu_colors())
        menu.add_command(label=t('context_menu.copy_system'), command=lambda: self._copy(system))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy_selected_system(self, tree):
        selection = tree.selection()
        if selection and selection[0] in self.lookups[tree]:
            self._copy(self.lookups[tree][selection[0]]['system'])
        return 'break'

    def _sort(self, tree, column):
        reverse = getattr(tree, '_sort_column', None) != column or not getattr(tree, '_sort_reverse', False)
        def key(item):
            value = tree.set(item, column)
            if tree is self.visited_tree:
                row = self.lookups[tree][item]
                if column == 'distance':
                    return row['_distance'] if row.get('_distance') is not None else (float('-inf') if reverse else float('inf'))
                if column == 'date':
                    return row['_stamp'] or datetime.min.replace(tzinfo=timezone.utc)
                if column == 'visits':
                    return row['visits']
            if column == 'duration':
                return self.owner._parse_elapsed_to_hours(value)
            return (float('-inf') if value == '—' else float(value)) if column in ('tph', 'best', 'avg', 'low', 'count', 'hours', 'distance', 'ls', 'mineral_avg', 'mineral_best', 'mineral_hits') else value.casefold()
        for i, item in enumerate(sorted(tree.get_children(), key=key, reverse=reverse)):
            tree.move(item, '', i)
        for col in tree['columns']:
            if col == '_spacer':
                continue
            text = t('statistics_expanded.col_minerals_mined' if col == 'mineral'
                     else 'statistics_expanded.col_' + col)
            tree.heading(col, text=text + (' ▼' if reverse else ' ▲') if col == column else text)
        tree._sort_column, tree._sort_reverse = column, reverse

    def _open_clicked(self, event, tree):
        item = tree.identify_row(event.y)
        if tree.identify_region(event.x, event.y) == 'cell' and item in self.lookups[tree]:
            row = self.lookups[tree][item]
            tree.selection_set(item)
            if displayed_column(tree, tree.identify_column(event.x)) == 'system':
                open_system_website(row['system'])
            else:
                self._open_report(row)

    @staticmethod
    def _open_report(row):
        if row.get('_report') and os.path.exists(row['_report']):
            os.startfile(row['_report'])

    def _menu(self, event, tree):
        item = tree.identify_row(event.y)
        if item not in self.lookups[tree]:
            return
        tree.selection_set(item)
        row = self.lookups[tree][item]
        menu = tk.Menu(tree, tearoff=0, **get_menu_colors())
        menu.add_command(label=t('context_menu.copy_system'), command=lambda: self._copy(row['system']))
        menu.add_separator()
        for site in ('inara', 'edsm', 'spansh'):
            menu.add_command(label=t('context_menu.open_' + site),
                             command=lambda service=site: open_system_website(row['system'], service))
        menu.add_separator()
        if '_report' in row:
            menu.add_command(label=t('statistics_expanded.open_report'), command=lambda: self._open_report(row),
                             state='normal' if row['_report'] and os.path.exists(row['_report']) else 'disabled')
        app = self.owner.main_app
        menu.add_command(label=t('statistics_expanded.find_location'), command=lambda: self._find_location(row),
                         state='normal' if app and hasattr(app, 'ring_finder') else 'disabled')
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _copy(self, system):
        self.parent.clipboard_clear()
        self.parent.clipboard_append(system)

    def _find_location(self, row):
        app = self.owner.main_app
        finder = app.ring_finder
        finder.system_var.set(row['system'])
        for tab in app.notebook.tabs():
            if app.notebook.nametowidget(tab) == finder.parent:
                app.notebook.select(tab)
                break
        finder.search_hotspots()
