"""Check the route poll that writes jumpsleft.txt for VoiceAttack, using a temp journal folder."""

import ast
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from va_variables import VAVariablesManager

TREE = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
APP = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'App')
METHODS = {n.name: n for n in APP.body if isinstance(n, ast.FunctionDef)}
SELECTED = ('_latest_journal_for_route', '_poll_route_status')


class RouteStatusChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = folder.name
        ns = {'os': os, 'json': json, 'log': logging.getLogger('check_route_status')}
        module = ast.Module(body=[ast.ClassDef(
            name='Harness', bases=[], keywords=[], decorator_list=[],
            body=[METHODS[name] for name in SELECTED])], type_ignores=[])
        ast.fix_missing_locations(module)
        exec(compile(module, str(ROOT / 'app/main.py'), 'exec'), ns)
        self.app = ns['Harness']()
        self.written = []
        self.scheduled = []
        self.app.prospector_panel = types.SimpleNamespace(journal_dir=self.dir)
        self.app.cargo_monitor = types.SimpleNamespace(last_journal_file=None)
        self.app.after = lambda ms, fn, *args: self.scheduled.append(ms)
        self.app.get_current_system = lambda: self.current_system
        self.app._write_jumps_left = self.written.append
        self.current_system = 'Start'
        self.journal = self.write_journal('Journal.2026-11-21T100000.01.log', [])

    def write_journal(self, name, events):
        path = os.path.join(self.dir, name)
        with open(path, 'w', encoding='utf-8') as f:
            for event in events:
                f.write(json.dumps(event) + '\n')
        return path

    def write_navroute(self, systems, mtime=None):
        path = os.path.join(self.dir, 'NavRoute.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'event': 'NavRoute', 'Route': [{'StarSystem': s} for s in systems]}, f)
        if mtime is not None:
            os.utime(path, (mtime, mtime))

    def poll(self, events, use_monitor=True):
        self.write_journal(os.path.basename(self.journal), events)
        self.app.cargo_monitor.last_journal_file = self.journal if use_monitor else None
        self.app._poll_route_status()
        self.assertEqual(self.scheduled[-1], 2000)

    def test_fsdtarget_sets_remaining_jumps(self):
        self.write_navroute(['Start', 'A', 'B', 'End'])
        self.poll([{'event': 'FSDTarget', 'RemainingJumpsInRoute': 3}])
        self.assertEqual(self.written, [3])
        self.poll([{'event': 'FSDTarget', 'RemainingJumpsInRoute': 3}])
        self.assertEqual(self.written, [3], 'unchanged value must not be rewritten')

    def test_navroute_event_uses_route_length_minus_one(self):
        self.write_navroute(['Start', 'A', 'B', 'C', 'End'])
        self.poll([{'event': 'NavRoute'}])
        self.assertEqual(self.written, [4])

    def test_clear_docked_and_touchdown_set_zero(self):
        for event in ('NavRouteClear', 'Docked', 'Touchdown'):
            self.app._cached_route_jumps = 5
            self.written.clear()
            self.poll([{'event': 'FSDTarget', 'RemainingJumpsInRoute': 5}, {'event': event}])
            self.assertEqual(self.written, [0], event)

    def test_fsdjump_is_skipped_to_find_the_target(self):
        self.write_navroute(['Start', 'A', 'B', 'End'])
        self.poll([{'event': 'FSDTarget', 'RemainingJumpsInRoute': 2}, {'event': 'FSDJump'}])
        self.assertEqual(self.written, [2])

    def test_arrival_at_final_system_sets_zero(self):
        self.write_navroute(['Start', 'A', 'End'])
        self.current_system = 'End'
        self.poll([{'event': 'FSDTarget', 'RemainingJumpsInRoute': 1}])
        self.assertEqual(self.written, [0])

    def test_empty_navroute_file_sets_zero(self):
        self.app._cached_route_jumps = 4
        self.write_navroute([])
        self.poll([{'event': 'FSDJump'}])
        self.assertEqual(self.written, [0])

    def test_navroute_file_is_read_only_when_it_changes(self):
        self.write_navroute([], mtime=1000)
        self.poll([])
        self.app._cached_route_jumps = 4
        real_open = open

        def guarded(path, *args, **kwargs):
            self.assertNotEqual(os.path.basename(str(path)), 'NavRoute.json')
            return real_open(path, *args, **kwargs)

        with patch('builtins.open', side_effect=guarded):
            self.app._poll_route_status()
        self.assertEqual(self.written, [0])

    def test_no_folder_listing_when_monitor_knows_the_journal(self):
        self.write_journal(os.path.basename(self.journal), [{'event': 'FSDTarget', 'RemainingJumpsInRoute': 2}])
        self.app.cargo_monitor.last_journal_file = self.journal
        with patch('os.listdir', side_effect=AssertionError('folder listed')):
            self.app._poll_route_status()
        self.assertEqual(self.written, [2])

    def test_falls_back_to_newest_journal_without_monitor(self):
        self.write_journal(os.path.basename(self.journal), [{'event': 'FSDTarget', 'RemainingJumpsInRoute': 7}])
        self.write_journal('Journal.2026-11-21T120000.01.log', [{'event': 'FSDTarget', 'RemainingJumpsInRoute': 2}])
        self.app.cargo_monitor.last_journal_file = None
        self.app._poll_route_status()
        self.assertEqual(self.written, [2])

    def test_monitor_journal_from_another_folder_is_ignored(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        stale = os.path.join(other.name, 'Journal.2026-11-21T130000.01.log')
        with open(stale, 'w', encoding='utf-8') as f:
            f.write(json.dumps({'event': 'FSDTarget', 'RemainingJumpsInRoute': 9}) + '\n')
        self.write_journal(os.path.basename(self.journal), [{'event': 'FSDTarget', 'RemainingJumpsInRoute': 2}])
        self.app.cargo_monitor.last_journal_file = stale
        self.app._poll_route_status()
        self.assertEqual(self.written, [2])


class JumpsLeftFileChecks(unittest.TestCase):
    def test_write_is_atomic_and_values_are_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = VAVariablesManager(folder, folder)
            with patch('os.replace', wraps=os.replace) as replace:
                manager.update_jumps_left(3)
                manager.update_jumps_left(3)
                manager.update_jumps_left(0)
            self.assertEqual(replace.call_count, 2)
            with open(os.path.join(folder, 'jumpsleft.txt'), encoding='utf-8') as f:
                self.assertEqual(f.read(), '0')
            self.assertEqual(sorted(os.listdir(folder)), ['jumpsleft.txt'])

    def test_old_route_poll_is_gone(self):
        self.assertFalse(hasattr(VAVariablesManager, 'poll_route_status'))
        self.assertNotIn('_poll_va_variables', METHODS)


if __name__ == '__main__':
    unittest.main()
