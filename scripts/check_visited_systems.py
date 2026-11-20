from contextlib import closing
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from user_database import UserDatabase
from session_statistics_panel import SessionStatisticsPanel, session_date
from check_session_statistics import owner
from check_ring_finder_search import load_methods


def cancel_callbacks(root):
    for callback in root.tk.call('after', 'info'):
        root.tk.call('after', 'cancel', callback)


def database(path):
    db = UserDatabase.__new__(UserDatabase)
    db.db_path = str(path)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute('''CREATE TABLE visited_systems (
            system_name TEXT PRIMARY KEY, system_address INTEGER,
            x_coord REAL, y_coord REAL, z_coord REAL,
            first_visit_date TEXT NOT NULL, last_visit_date TEXT NOT NULL, visit_count INTEGER DEFAULT 1)''')
    return db


App = load_methods('app/main.py', 'App', {
    '_process_journals_for_catchup', '_process_journals_for_catchup_with_progress', 'record_system_visit',
})
App.record_system_visit.__globals__.update(os=os, log=logging.getLogger('visit-test'))


class VisitDataChecks(unittest.TestCase):
    def setUp(self):
        connect = sqlite3.connect
        class Connection(sqlite3.Connection):
            def __exit__(self, *args):
                try:
                    return super().__exit__(*args)
                finally:
                    self.close()
        replacement = patch('sqlite3.connect', lambda *args, **kwargs: connect(*args, factory=Connection, **kwargs))
        replacement.start()
        self.addCleanup(replacement.stop)

    def test_recent_systems_are_unique_limited_and_newest_first(self):
        with tempfile.TemporaryDirectory() as folder:
            db = database(Path(folder) / 'visits.db')
            for i in range(12):
                db.add_visited_system(f'System {i}', f'2026-11-{i + 1:02}T12:00:00Z')
            db.add_visited_system('System 0', '2026-11-15T12:00:00Z')
            db.add_visited_system('System 0', '2026-11-15T12:00:00Z')
            db.add_visited_system('Unconfirmed', '0001-01-01T00:00:00Z')
            recent = db.get_recent_visited_systems()
            self.assertEqual(len(recent), 10)
            self.assertEqual(recent[0]['system'], 'System 0')
            self.assertEqual(recent[0]['visits'], 2)
            self.assertEqual(len({row['system'] for row in recent}), 10)
            self.assertNotIn('Unconfirmed', [row['system'] for row in recent])
            self.assertEqual(len(db.get_recent_visited_systems(limit=20)), 12)

    def test_both_history_scans_count_aboard_carrier_but_not_remote_carrier(self):
        events = [
            dict(event='FSDJump', StarSystem='Sol', timestamp='2026-11-01T12:00:00Z', StarPos=[0, 0, 0]),
            dict(event='CarrierJump', StarSystem='Aboard', timestamp='2026-11-01T13:00:00Z', StarPos=[3, 4, 0]),
            dict(event='CarrierLocation', StarSystem='Remote', timestamp='2026-11-01T14:00:00Z'),
            dict(event='FSDJump', StarSystem='Sol', timestamp='2026-11-01T15:00:00Z', StarPos=[0, 0, 0]),
            dict(event='Location', StarSystem='Sol', timestamp='2026-11-01T16:00:00Z'),
        ]
        for method in ('_process_journals_for_catchup', '_process_journals_for_catchup_with_progress'):
            with self.subTest(method=method), tempfile.TemporaryDirectory() as folder:
                db = database(Path(folder) / 'visits.db')
                journal = Path(folder) / 'Journal.log'
                journal.write_text('\n'.join(json.dumps(event) for event in events), encoding='utf-8')
                app = App()
                parser = Mock(on_carrier_updated=None, carrier_data={})
                app.cargo_monitor = SimpleNamespace(user_db=db, journal_parser=parser)
                app.after = Mock()
                app._ensure_current_system_visited = Mock()
                app._trigger_ring_auto_search = Mock()
                disabled_missions = SimpleNamespace(MISSIONS_AVAILABLE=False, get_mission_tracker=lambda: None)
                with patch.dict(sys.modules, mining_missions=disabled_missions,
                                path_utils=SimpleNamespace(get_app_data_dir=lambda: folder)):
                    getattr(app, method)([str(journal)])
                    getattr(app, method)([str(journal)])
                visits = {row['system']: row['visits'] for row in db.get_recent_visited_systems()}
                self.assertEqual(visits, {'Sol': 2, 'Aboard': 1})
                parser.process_carrier_event.assert_any_call(events[2])
                parser.process_carrier_event.assert_any_call(events[1])

    def test_system_distances_do_not_look_up_ls(self):
        finder = SimpleNamespace(systems_data={'sol': dict(x=0, y=0, z=0), 'aboard': dict(x=3, y=4, z=0)},
                                 _calculate_distance=lambda a, b: sum((a[k] - b[k]) ** 2 for k in a) ** 0.5)
        db = SimpleNamespace(get_ls_distance=Mock())
        panel = SessionStatisticsPanel.__new__(SessionStatisticsPanel)
        panel.owner = SimpleNamespace(main_app=SimpleNamespace(ring_finder=finder, cargo_monitor=SimpleNamespace(user_db=db)))
        rows = [dict(system='Sol'), dict(system='Aboard')]
        panel._add_location_distances(rows, 'Sol', include_ls=False)
        self.assertEqual([row['_distance'] for row in rows], [0, 5])
        db.get_ls_distance.assert_not_called()


class VisitTableChecks(unittest.TestCase):
    def test_visits_load_without_any_mining_sessions(self):
        root = tk.Tk()
        root.withdraw()
        frame = ttk.Frame(root)
        frame.pack()
        try:
            with tempfile.TemporaryDirectory() as folder, \
                    patch('session_statistics_panel._load_cfg', return_value={}), \
                    patch('session_statistics_panel.update_config_value'):
                db_path = os.path.join(folder, 'user_data.db')
                with closing(sqlite3.connect(db_path)) as connection:
                    connection.execute('CREATE TABLE hotspot_data (system_name, body_name, material_name, '
                                       'hotspot_count, overlap_tag, res_tag)')
                db = SimpleNamespace(db_path=db_path, get_recent_visited_systems=Mock(
                    return_value=[dict(system='Sol', last_visit_date='2026-11-15T12:00:00Z', visits=3)]))
                finder = SimpleNamespace(systems_data={'sol': dict(x=0, y=0, z=0)})
                obj = owner()
                obj.reports_dir = folder
                obj.main_app = SimpleNamespace(get_current_system=lambda: 'Sol', ring_finder=finder,
                                               cargo_monitor=SimpleNamespace(user_db=db))
                panel = SessionStatisticsPanel(frame, obj)
                root.update()
                deadline = time.monotonic() + 3
                while panel.loading and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(panel.loading)
                self.assertEqual(len(panel.visited_tree.get_children()), 1)
                item = panel.visited_tree.get_children()[0]
                self.assertEqual(panel.visited_tree.set(item, 'distance'), '0.0')
                self.assertEqual(panel.visited_tree.set(item, 'visits'), '3')
                self.assertEqual(panel.best_tree.get_children(), ())
                db.get_recent_visited_systems.assert_called_once_with(limit=20)
        finally:
            cancel_callbacks(root)
            root.destroy()

    def test_table_filter_independence_sorting_columns_and_scrolling(self):
        for language in ('en', 'de'):
            with self.subTest(language=language):
                strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
                def translate(key):
                    value = strings
                    for part in key.split('.'):
                        value = value[part]
                    return value
                root = tk.Tk()
                root.geometry('650x300+-3000+-3000')
                frame = ttk.Frame(root)
                frame.pack(fill='both', expand=True)
                preferences = {'recent_systems_widths': {'system': 1300, 'date': 1, 'distance': 1, 'visits': 1}}
                try:
                    with patch('session_statistics_panel._load_cfg', return_value={'session_statistics': preferences}), \
                            patch('session_statistics_panel.update_config_value'), \
                            patch('session_statistics_panel.t', translate), \
                            patch('config.load_column_visibility', return_value={}), \
                            patch('config.load_column_order', return_value=[]), \
                            patch.object(SessionStatisticsPanel, 'reload'):
                        panel = SessionStatisticsPanel(frame, owner())
                        rows = [dict(system=f'System {i}', _stamp=session_date(f'2026-11-{15 - i:02}T12:00:00Z'),
                                     _distance=None if i == 9 else float(i), visits=i + 1) for i in range(10)]
                        panel._loaded([], rows)
                        tree = panel.visited_tree
                        panel.book.select(tree.master.master)
                        root.update()
                        self.assertEqual(len(tree.get_children()), 10)
                        self.assertEqual(panel.filter_controls.winfo_manager(), '')
                        self.assertEqual(tree.heading('visits', 'text'), strings['statistics_expanded']['col_visits'])
                        for col in ('system', 'date', 'distance', 'visits'):
                            self.assertEqual(str(tree.column(col, 'anchor')), 'w')
                            self.assertFalse(tree.column(col, 'stretch'))
                            self.assertGreaterEqual(tree.column(col, 'width'), tree.column(col, 'minwidth'))
                        tree.xview_moveto(1)
                        tree.yview_moveto(1)
                        root.update()
                        self.assertGreater(tree.xview()[0], 0)
                        self.assertGreater(tree.yview()[0], 0)
                        panel._sort(tree, 'visits')
                        self.assertEqual(tree.set(tree.get_children()[0], 'visits'), '10')
                        for _ in range(2):
                            panel._sort(tree, 'distance')
                            self.assertEqual(tree.set(tree.get_children()[-1], 'distance'), '—')
                        panel.ship.set('No matching ship')
                        panel.apply_filters()
                        self.assertEqual(len(tree.get_children()), 10)
                        widths = {col: tree.column(col, 'width') for col in tree['columns'] if col != '_spacer'}
                        panel._show_visited_systems()
                        root.geometry('900x450+-3000+-3000')
                        root.update()
                        self.assertEqual(widths, {col: tree.column(col, 'width') for col in widths})
                        key = 'statistics_recent_systems'
                        panel._cv_trees[key]['visible']['date'] = False
                        panel._cv_set_order(key, ['visits', 'system', 'distance', 'date'], save=False)
                        self.assertEqual(tree['displaycolumns'][:3], ('visits', 'system', 'distance'))
                        first = tree.get_children()[0]
                        with patch.object(tree, 'identify_row', return_value=first), \
                                patch.object(tree, 'identify_region', return_value='cell'), \
                                patch.object(tree, 'identify_column', return_value='#2'), \
                                patch('session_statistics_panel.open_system_website') as open_site:
                            panel._open_clicked(SimpleNamespace(x=5, y=30), tree)
                            open_site.assert_called_once_with(panel.lookups[tree][first]['system'])
                        panel._cv_trees[key]['visible']['date'] = True
                        panel._cv_apply_displaycolumns(key)
                        self.assertIn('date', tree['displaycolumns'])
                        panel._save_widths(tree, 'recent_systems')
                        with patch('config.load_column_visibility', return_value={'date': False}), \
                                patch('config.load_column_order', return_value=['visits', 'system', 'distance', 'date']):
                            restored_frame = ttk.Frame(root)
                            restored = SessionStatisticsPanel(restored_frame, owner())
                            self.assertEqual(restored.visited_tree.column('system', 'width'), widths['system'])
                            self.assertEqual(restored.visited_tree['displaycolumns'][:3], ('visits', 'system', 'distance'))
                            self.assertNotIn('date', restored.visited_tree['displaycolumns'])
                            cancel_callbacks(root)
                            restored_frame.destroy()
                        panel.book.select(0)
                        root.update()
                        self.assertEqual(str(panel.ship_combo.cget('state')), 'readonly')
                finally:
                    cancel_callbacks(root)
                    root.destroy()


if __name__ == '__main__':
    unittest.main()
