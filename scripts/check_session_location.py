import ast
import datetime as dt
import glob
import json
import os
import re
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))
from journal_reader import journal_resume_offset, read_complete_journal_lines


def load_methods(path, names, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    methods = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), 'exec'), namespace)
    return {name: namespace[name] for name in names}


NAMESPACE = dict(globals(), MISSIONS_AVAILABLE=False, CHARTS_AVAILABLE=False,
                 t=lambda key: key, _clean_name=lambda name: name,
                 _atomic_write_text=lambda path, text: Path(path).write_text(text, encoding='utf-8'))
METHODS = load_methods(ROOT / 'app/prospector_panel.py', {
    '_read_initial_location_from_journal', '_extract_location_display',
    '_watch_once', '_session_start', '_session_stop',
    '_save_session_report_with_timestamp',
}, NAMESPACE)
DB_METHODS = load_methods(ROOT / 'app/user_database.py',
                          {'_normalize_body_name', 'bulk_get_ring_types'}, dict(globals()))


class Value:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class SessionLocationChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.journal = Path(self.folder.name) / 'Journal.2026-11-17T191720.01.log'
        self.system = 'Wregoe XL-U c16-15'
        self.body = 'BC 9 A Ring'
        self.journal.write_text(json.dumps(dict(
            event='Location', timestamp='2026-11-17T18:18:29Z',
            StarSystem=self.system, Body=f'{self.system} {self.body}',
            BodyType='PlanetaryRing')) + '\n', encoding='utf-8')
        self.panel = Mock()
        p = self.panel
        for name, method in METHODS.items():
            if name.startswith('_') and name != '_extract_location_display':
                setattr(p, name, method.__get__(p))
        p.main_app = None
        p.journal_dir = self.folder.name
        p.reports_dir = self.folder.name
        p.session_active = False
        p.session_system = Value()
        p.session_body = Value()
        p.session_elapsed = Value()
        p.live_tph_var = Value()
        p.multi_session_var = Value(False)
        p.last_station_name = p.last_carrier_name = ''
        p.session_mining_system = p.session_mining_body = ''
        p._get_current_system.side_effect = lambda: p.last_system
        p._find_latest_journal.return_value = str(self.journal)
        p._journal_attached = False
        p._active_seconds.return_value = 3600
        p._cargo_full_dialog = None
        p.session_analytics.get_live_summary.return_value = {}
        p.session_analytics.get_session_info.return_value = {}
        p._read_initial_location_from_journal()
        p._session_start()
        p._watch_once()

    def mine(self):
        with self.journal.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(event='MiningRefined', Type='Tritium')) + '\n')
        self.panel._watch_once()

    def save(self, ring_type='Icy'):
        p = self.panel
        p.main_app = Mock()
        p.main_app.cargo_monitor.user_db.get_ring_type.return_value = ring_type
        p.main_app.cargo_monitor.get_live_session_materials.return_value = {'Tritium': 1}
        p.main_app.cargo_monitor.end_session_tracking.return_value = {
            'materials_mined': {'Tritium': 1}, 'total_tons_mined': 1,
        }
        p.session_elapsed.set('01:00:00')
        p._session_stop(silent=True)
        p._update_csv_with_session.assert_called_once()
        return p._update_csv_with_session.call_args.args[:2]

    def test_restart_already_in_ring(self):
        self.mine()
        self.assertEqual(self.save(), (self.system, self.body))
        report = next(Path(self.folder.name).glob('Session_*.txt'))
        self.assertIn(f'{self.system} — {self.body}', report.read_text(encoding='utf-8'))
        self.assertIn('Ring Type: Icy\n', report.read_text(encoding='utf-8'))

    def test_location_written_between_startup_scan_and_journal_attach(self):
        p = self.panel
        p.last_body = 'Old system 1 A Ring'
        p.last_body_type = 'PlanetaryRing'
        p.session_body.set('')
        p._journal_attached = False
        p._watch_once()
        self.assertEqual(p.last_body, f'{self.system} {self.body}')
        p._update_location_display.assert_called()

    def test_session_start_recovers_location_after_many_events(self):
        with self.journal.open('a', encoding='utf-8') as stream:
            stream.write((json.dumps({'event': 'Cargo'}) + '\n') * 1100)
        p = self.panel
        p.session_active = False
        p.last_body = p.last_body_type = ''
        p.session_body.set('')
        p._session_start()
        self.assertEqual(p.session_body.get(), self.body)
        self.assertEqual(self.save(), (self.system, self.body))

    def test_location_changes_preserve_report_and_ring_type(self):
        self.mine()
        p = self.panel
        p.last_system = 'Wregoe MD-K d8-19'
        p.last_body = 'V0W-W7T'
        p.session_system.set(p.last_system)
        p.session_body.set(p.last_body)
        pair = self.save()
        self.assertEqual(pair, (self.system, self.body))
        report = next(Path(self.folder.name).glob('Session_*.txt'))
        self.assertIn('Wregoe_XL-U_c16-15_BC_9_A_Ring', report.name)
        self.assertIn(f'{self.system} — {self.body}', report.read_text(encoding='utf-8'))
        self.assertIn('Ring Type: Icy\n', report.read_text(encoding='utf-8'))
        p.main_app.cargo_monitor.user_db.get_ring_type.assert_called_once_with(self.system, self.body)
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.execute('CREATE TABLE hotspot_data (system_name TEXT, body_name TEXT, ring_type TEXT)')
            conn.execute('INSERT INTO hotspot_data VALUES (?, ?, ?)', (*pair, 'Icy'))
            conn.commit()
            db = Mock(db_path=':memory:')
            db._normalize_body_name = DB_METHODS['_normalize_body_name']
            lookup = DB_METHODS['bulk_get_ring_types']
            with patch.dict(lookup.__globals__, sqlite3=SimpleNamespace(connect=lambda path: conn)):
                self.assertEqual(lookup(db, [pair]), {pair: 'Icy'})

    def test_new_session_clears_preserved_location(self):
        self.mine()
        p = self.panel
        p.session_active = False
        p.last_system = 'Sol'
        p.last_body = 'Sol 1 A Ring'
        p.session_system.set('Sol')
        p.session_body.set('1 A Ring')
        p._session_start()
        self.assertEqual(p.session_mining_system, '')
        self.assertEqual(p.session_mining_body, '')
        self.mine()
        self.assertEqual(self.save(), ('Sol', '1 A Ring'))

    def test_no_refining_uses_current_session_location(self):
        self.assertEqual(self.save(ring_type=None), (self.system, self.body))
        report = next(Path(self.folder.name).glob('Session_*.txt'))
        self.assertNotIn('Ring Type:', report.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
