import ast
import os
import sys
import tkinter as tk
import unittest
import time
import csv
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from session_statistics_panel import (SessionStatisticsPanel, material_names, prepare_sessions,
                                      select_sessions, location_summary, recent_progress)
from mining_statistics import parse_mineral_performance

tree = ast.parse((ROOT / 'app/prospector_panel.py').read_text(encoding='utf-8'))
panel = next(node for node in tree.body if isinstance(node, ast.ClassDef) and
             any(isinstance(fn, ast.FunctionDef) and fn.name == '_calculate_session_statistics' for fn in node.body))
methods = [node for node in panel.body if isinstance(node, ast.FunctionDef)
           and node.name in ('_calculate_session_statistics', '_parse_elapsed_to_hours', '_get_ship_name_from_session')]
namespace = {'os': os}
exec(compile(ast.Module(body=methods, type_ignores=[]), '<existing-statistics>', 'exec'), namespace)


def owner():
    obj = SimpleNamespace(reports_dir='', main_app=None)
    for name, method in namespace.items():
        if callable(method) and name.startswith('_'):
            setattr(obj, name, method.__get__(obj))
    return obj


def sessions():
    data = []
    for i in range(24):
        data.append(dict(system='Sol' if i % 2 == 0 else 'Achenar', body='A Ring' if i % 3 else 'B Ring',
                         elapsed='01:00:00', overall_tph=str(100 + i), total_tons='100',
                         asteroids_prospected='20', hit_rate_percent='0' if i == 0 else '50',
                         timestamp_utc=f'2026-11-{i + 1:02}T12:00:00Z',
                         best_material='Platinum (40%)', materials_breakdown='Platinum: 80t, Gold: 20t'))
    obj = owner()
    return prepare_sessions(data, obj._parse_elapsed_to_hours, lambda *args: ('Python', ''))


class StatisticsChecks(unittest.TestCase):
    def test_startup_load_without_mainloop(self):
        root = tk.Tk()
        root.withdraw()
        from tkinter import ttk
        frame = ttk.Frame(root)
        frame.pack()
        try:
            with tempfile.TemporaryDirectory() as folder, \
                 patch('session_statistics_panel._load_cfg', return_value={}), \
                 patch('session_statistics_panel.update_config_value'), \
                 patch.object(SessionStatisticsPanel, '_add_location_distances'):
                row = {key: value for key, value in sessions()[0].items() if not key.startswith('_')}
                with (Path(folder) / 'sessions_index.csv').open('w', encoding='utf-8', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow(row)
                obj = owner()
                obj.reports_dir = folder
                widget = SessionStatisticsPanel(frame, obj)
                root.update()
                deadline = time.monotonic() + 3
                while widget.loading and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(widget.loading)
                self.assertEqual(str(widget.refresh_button.cget('state')), 'normal')
                self.assertIn('Total Sessions: 1', widget.overview.get('1.0', 'end'))
                self.assertEqual(len(widget.best_tree.get_children()), 1)
        finally:
            root.destroy()
    def test_report_mineral_parser(self):
        text = '''--- Mineral Performance ---
Platinum:
  • Average: 35.9%
  • Best: 50.3%
  • Hits: 5
  • Tons: 291.0t
Osmium:
  • Average: 29.8%
  • Best: 29.8%
  • Hits: 1
Overall Quality: 22.7% average yield
=== CARGO MATERIAL BREAKDOWN ===
Gold:
  • Average: 99.0%
'''
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'session.txt'
            path.write_text(text, encoding='utf-8')
            for heading in ('Mineral', 'Material'):
                path.write_text(text.replace('Mineral Performance', heading + ' Performance'), encoding='utf-8')
                performance = parse_mineral_performance(path)
                self.assertEqual(performance['Platinum'], {'avg': 35.9, 'best': 50.3, 'hits': 5})
                self.assertNotIn('Gold', performance)

    def test_mineral_average_is_hit_weighted(self):
        rows = sessions()[:3]
        for row in rows:
            row.update(system='Sol', body='A Ring')
        rows[0]['_performance'] = {'Platinum': {'avg': 10, 'best': 20, 'hits': 2}}
        rows[1]['_performance'] = {'Platinum': {'avg': 40, 'best': 50, 'hits': 1}}
        best, recent = location_summary(rows, 'Platinum')
        self.assertEqual(best[0]['mineral_avg'], 20)
        self.assertEqual(best[0]['mineral_best'], 50)
        self.assertEqual(best[0]['mineral_hits'], 3)
        self.assertIsNone(location_summary(rows)[0][0]['mineral_avg'])
        self.assertIsNone(location_summary(rows, 'Gold')[0][0]['mineral_hits'])
        self.assertEqual(recent[0]['mineral_avg'], 20)

    def test_materials_old_and_new_formats(self):
        self.assertEqual(material_names({'materials_breakdown': 'Gold: 10; Silver: 20'}), ['Gold', 'Silver'])
        self.assertEqual(sessions()[0]['_materials'], ['Gold', 'Platinum'])

    def test_filters_keep_session_totals(self):
        selected = select_sessions(sessions(), 'Python', 'Gold', 7, datetime(2026, 11, 25, tzinfo=timezone.utc))
        self.assertEqual(len(selected), 7)
        self.assertEqual(selected[-1]['_tph'], 123)
        self.assertEqual(select_sessions(sessions(), 'Cutter'), [])

    def test_locations_unique_and_latest(self):
        ranked, recent = location_summary(sessions())
        self.assertEqual(len(recent), 4)
        self.assertEqual(recent[0]['latest']['_tph'], 123)
        self.assertEqual(sum(row['count'] for row in ranked), 24)
        self.assertEqual(ranked[0]['best']['_tph'], 123)

    def test_short_record_stays_distinct_from_average(self):
        rows = sessions()[:2]
        rows[1].update(system='Sol', body='B Ring', _hours=0.01, _tph=10000)
        ranked, _ = location_summary(rows)
        self.assertEqual(ranked[0]['avg'], 5050)
        self.assertEqual(ranked[0]['count'], 2)
        self.assertAlmostEqual(ranked[0]['hours'], 1.01)

    def test_recent_has_twenty_distinct_locations_not_twenty_sessions(self):
        rows = sessions()
        for i, row in enumerate(rows):
            row['body'] = str(i)
        best, recent = location_summary(rows)
        self.assertEqual(len(best), 20)
        self.assertEqual(best[0]['best']['_tph'], 123)
        self.assertEqual(len(recent), 20)
        self.assertEqual(recent[0]['latest']['body'], '23')

    def test_nonmining_visits_excluded(self):
        rows = sessions()[:1]
        rows[0]['_tons'] = 0
        self.assertEqual(location_summary(rows), ([], []))
        self.assertEqual(recent_progress(rows), (0, 0, None, None))

    def test_progress_uses_two_disjoint_groups(self):
        n, previous_n, current, previous = recent_progress(sessions())
        self.assertEqual((n, previous_n), (10, 10))
        self.assertEqual(current[0], 118.5)
        self.assertEqual(previous[0], 108.5)
        self.assertEqual(current[2], 5)

    def test_unknown_dates_not_recent(self):
        rows = sessions()[:1]
        rows[0]['_stamp'] = None
        self.assertEqual(location_summary(rows)[1], [])
        self.assertEqual(select_sessions(rows, days=7), [])

    def test_existing_calculator_accepts_filtered_sessions(self):
        result = owner()._calculate_session_statistics(sessions()[:2])
        self.assertEqual(result['total_sessions'], 2)
        self.assertEqual(result['total_tonnage'], 200)
        self.assertEqual(result['total_time_hours'], 2)

    def test_distances_reuse_lookups_and_preserve_unknowns(self):
        from unittest.mock import Mock
        finder = SimpleNamespace(systems_data={'sol': {'x': 0, 'y': 0, 'z': 0}},
            _get_system_coords_from_galaxy_db=Mock(return_value={'x': 3, 'y': 4, 'z': 0}),
            _calculate_distance=Mock(return_value=5.0))
        database = SimpleNamespace(get_ls_distance=Mock(return_value=1234.5))
        widget = SessionStatisticsPanel.__new__(SessionStatisticsPanel)
        widget.owner = SimpleNamespace(main_app=SimpleNamespace(ring_finder=finder,
            cargo_monitor=SimpleNamespace(user_db=database)))
        rows = sessions()[:3]
        rows[2]['body'] = rows[0]['body']
        widget._add_location_distances(rows, 'Sol')
        self.assertEqual(rows[0]['_distance'], 0)
        self.assertEqual(rows[1]['_distance'], 5)
        self.assertEqual(rows[0]['_ls'], 1234.5)
        self.assertEqual(database.get_ls_distance.call_count, 2)
        widget.owner.main_app = None
        widget._add_location_distances(rows, None)
        self.assertIsNone(rows[0]['_distance'])
        self.assertIsNone(rows[0]['_ls'])

    def test_missing_coordinates_use_hotspots_then_existing_online_lookup(self):
        from unittest.mock import Mock
        zero = {'x': 0, 'y': 0, 'z': 0}
        finder = SimpleNamespace(systems_data={'sol': zero},
            _get_system_coords_from_galaxy_db=Mock(return_value=None),
            _get_system_coords_from_edsm=Mock(return_value={'x': 6, 'y': 8, 'z': 0}),
            _calculate_distance=lambda a, b: sum((a[k] - b[k]) ** 2 for k in ('x', 'y', 'z')) ** 0.5)
        database = SimpleNamespace(_get_coordinates_from_visited_systems=Mock(return_value=None),
            get_system_hotspots=Mock(side_effect=lambda system: [{'x_coord': 3, 'y_coord': 4, 'z_coord': 0}]
                                    if system == 'Hotspot Only' else []), get_ls_distance=Mock(return_value=None))
        widget = SessionStatisticsPanel.__new__(SessionStatisticsPanel)
        widget.owner = SimpleNamespace(main_app=SimpleNamespace(ring_finder=finder,
            cargo_monitor=SimpleNamespace(user_db=database)))
        rows = [{'system': 'Hotspot Only', 'body': 'A Ring'}, {'system': 'Online Only', 'body': 'A Ring'},
                {'system': 'Online Only', 'body': 'B Ring'}]
        widget._add_location_distances(rows, 'Sol')
        self.assertEqual([row['_distance'] for row in rows], [5, 10, 10])
        finder._get_system_coords_from_edsm.assert_called_once_with('Online Only')

    def test_bad_numeric_rows_skipped_and_zero_hits_preserved(self):
        source = dict(system='Sol', body='A Ring', total_tons='bad', overall_tph='1')
        obj = owner()
        self.assertEqual(prepare_sessions([source], obj._parse_elapsed_to_hours, lambda *args: ('', '')), [])
        current = recent_progress(sessions()[:1])[2]
        self.assertEqual(current[1], 0)

    def test_location_search_uses_existing_search_and_selects_tab(self):
        from unittest.mock import Mock
        parent = object()
        finder = SimpleNamespace(parent=parent, system_var=Mock(), search_hotspots=Mock())
        notebook = SimpleNamespace(tabs=lambda: ['rings'], nametowidget=lambda tab: parent, select=Mock())
        widget = SessionStatisticsPanel.__new__(SessionStatisticsPanel)
        widget.owner = SimpleNamespace(main_app=SimpleNamespace(ring_finder=finder, notebook=notebook))
        widget._find_location({'system': 'Sol'})
        notebook.select.assert_called_once_with('rings')
        finder.system_var.set.assert_called_once_with('Sol')
        finder.search_hotspots.assert_called_once()

    def test_ui_filters_sorting_and_empty_results(self):
        root = tk.Tk()
        root.geometry('1200x800+-3000+-3000')
        from tkinter import ttk
        frame = ttk.Frame(root)
        frame.pack(fill='both', expand=True)
        try:
            with patch('session_statistics_panel._load_cfg', return_value={}), \
                 patch('session_statistics_panel.update_config_value'), \
                 patch.object(SessionStatisticsPanel, 'reload'):
                widget = SessionStatisticsPanel(frame, owner())
                self.assertEqual(widget.ship.get(), 'All Ships')
                data = sessions()
                long_ship = 'Mega Bumper - Type-11 Prospector'
                data[0]['_ship'] = long_ship
                widget._loaded(data)
                root.update()
                self.assertGreater(int(widget.ship_combo.cget('width')), 25)
                self.assertEqual(widget.overview.cget('wrap'), 'word')
                self.assertTrue(widget.overview.tag_ranges('body'))
                overview_text = widget.overview.get('1.0', 'end')
                self.assertIn('Average Tons per Session: 100.0 t', overview_text)
                self.assertIn('Average Session Duration: 01:00:00', overview_text)
                self.assertNotIn('Recent Progress', overview_text)
                self.assertIn('Session Records', overview_text)
                self.assertIn('Average T/hr: 118.5 / 108.5 (+10.0)', widget.progress.get('1.0', 'end'))
                from config import scaled_px
                for width, column in ((1100, 1), (650, 0), (1100, 1)):
                    root.geometry(f'{scaled_px(width)}x800+-3000+-3000')
                    root.update()
                    self.assertEqual(int(widget.progress.grid_info()['column']), column)
                    self.assertEqual(widget.overview.yview(), (0.0, 1.0))
                    self.assertEqual(widget.progress.yview(), (0.0, 1.0))
                    if column:
                        self.assertEqual(widget.overview.winfo_y(), widget.progress.winfo_y())
                    else:
                        self.assertGreater(widget.progress.winfo_y(), widget.overview.winfo_y())
                        widget.overview_canvas.yview_moveto(1)
                        root.update()
                        self.assertAlmostEqual(widget.overview_canvas.yview()[1], 1.0)
                self.assertEqual(len(widget.best_tree.get_children()), 4)
                self.assertEqual(len(widget.recent_tree.get_children()), 4)
                widget._sort(widget.best_tree, 'best')
                first = widget.best_tree.get_children()[0]
                self.assertEqual(widget.best_tree.set(first, 'best'), '123.0')
                widget.best_tree.selection_set(first)
                with patch.object(widget.best_tree, 'identify_row', return_value=first), \
                     patch.object(widget.best_tree, 'identify_region', return_value='cell'), \
                     patch.object(widget.best_tree, 'identify_column', return_value='#1'), \
                     patch('session_statistics_panel.open_system_website') as open_site:
                    widget._open_clicked(SimpleNamespace(x=5, y=30), widget.best_tree)
                    open_site.assert_called_once_with(widget.lookups[widget.best_tree][first]['system'])
                widget._copy_selected_system(widget.best_tree)
                self.assertEqual(root.clipboard_get(), widget.lookups[widget.best_tree][first]['system'])
                for tag in ('location_record', 'location_most'):
                    start, end = widget.overview.tag_ranges(tag)
                    self.assertIn(widget.overview.get(start, end), ('Sol', 'Achenar'))
                    self.assertTrue(widget.overview.tk.call(widget.overview, 'tag', 'bind', tag, '<Button-3>'))
                widget.mineral.set('Gold')
                widget.apply_filters()
                self.assertEqual(len(widget.best_tree.get_children()), 4)
                widget.ship.set('Cutter')
                widget.apply_filters()
                self.assertEqual(widget.best_tree.get_children(), ())
                self.assertIn('No saved sessions', widget.overview.get('1.0', 'end'))
                self.assertIn('Average Tons per Session: 0.0 t', widget.overview.get('1.0', 'end'))
                self.assertIn('Average Session Duration: 00:00:00', widget.overview.get('1.0', 'end'))
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
