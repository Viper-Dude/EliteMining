import ast
from concurrent.futures import ThreadPoolExecutor
import json
import logging
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import requests
from edsm_distance import EDSMDistanceCalculator
from version import __version__


source = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
original = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'App')
methods = [node for node in original.body if isinstance(node, ast.FunctionDef)
           and node.lineno >= next(n.lineno for n in original.body if isinstance(n, ast.FunctionDef) and n.name == '_build_distance_calculator_tab')
           and node.lineno < next(n.lineno for n in original.body if isinstance(n, ast.FunctionDef) and n.name == '_check_market_api_status')]
node = ast.ClassDef(name='App', bases=[], keywords=[], body=methods, decorator_list=[])
namespace = dict(tk=tk, ttk=ttk, logging=logging, threading=threading,
                 ToolTip=Mock(), compact_classic_button=Mock(),
                 create_action_button=lambda parent, primary=False, **kwargs: tk.Button(parent, **kwargs))
exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), 'app/main.py', 'exec'), namespace)
App = namespace['App']


def translate(language):
    strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
    def get(key):
        value = strings
        for part in key.split('.'):
            value = value[part]
        return value
    return get


namespace['t'] = translate('en')


class Variable:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Widget:
    def __init__(self):
        self.options = {'text': '---'}

    def config(self, **kwargs):
        self.options.update(kwargs)

    def cget(self, key):
        return self.options[key]


class Queue:
    def __init__(self):
        self.pending = {}
        self.sequence = 0

    def after(self, delay, callback, *args):
        self.sequence += 1
        self.pending[self.sequence] = (callback, args)
        return self.sequence

    def cancel(self, key):
        self.pending.pop(key, None)

    def flush(self):
        while self.pending:
            key = next(iter(self.pending))
            callback, args = self.pending.pop(key)
            callback(*args)


class InlineThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def info(coords=None, error=None, visits=0):
    return dict(coords=coords, error=error, visits=visits,
                sol_distance=EDSMDistanceCalculator().calculate_distance(coords, dict(x=0, y=0, z=0)))


def app():
    obj = App()
    for key in ('system_a_name', 'system_b_name', 'status_label', 'ab_label', 'ab_value_label',
                'a_sol_label', 'b_sol_label', 'a_coords_label', 'b_coords_label',
                'a_visits_label', 'b_visits_label', 'to_home_label', 'to_fc_label'):
        setattr(obj, 'distance_' + key, Widget())
    for key in ('current_sol_label', 'home_sol_label', 'fc_sol_label', 'home_visits_label', 'fc_visits_label'):
        setattr(obj, key, Widget())
    for key, value in dict(system_a='A', system_b='B', current_system='Current', home_system='Home', fc_system='Carrier').items():
        setattr(obj, 'distance_' + key, Variable(value))
    obj.current_system = 'Current'
    obj.current_system_coords = (0, 0, 0)
    obj.distance_calculator = EDSMDistanceCalculator()
    obj._distance_calculation_generation = 0
    obj._distance_update_generation = 0
    obj._distance_update_pending = None
    obj._distance_update_running = False
    obj._distance_refresh_generation = 0
    obj._distance_refresh_running = False
    obj.distance_refresh_btn = Widget()
    obj._distance_values = {}
    obj._set_status = Mock()
    obj._save_distance_systems = Mock()
    obj.queue = Queue()
    obj.after = obj.queue.after
    obj.after_cancel = obj.queue.cancel
    return obj


class CalculationChecks(unittest.TestCase):
    def test_single_system_success_and_empty_side_visits_are_cleared(self):
        obj = app()
        obj.distance_system_b.set('')
        obj.distance_b_visits_label.config(text='Old visits: 99')
        obj._resolve_distance_systems = Mock(return_value={'a': info(dict(x=3, y=4, z=0))})
        with patch('threading.Thread', InlineThread), patch('edsm_distance.requests.get') as network:
            obj._calculate_distances()
            obj.queue.flush()
        self.assertEqual(obj.distance_status_label.cget('text'), translate('en')('distance_calculator.calculation_complete'))
        self.assertIn('5.00 LY', obj.distance_a_sol_label.cget('text'))
        self.assertTrue(obj.distance_b_visits_label.cget('text').endswith('---'))
        network.assert_not_called()

    def test_older_calculation_cannot_overwrite_newer_result(self):
        obj = app()
        workers = []
        obj._resolve_distance_systems = Mock(side_effect=lambda names, *args: {name.casefold(): info(dict(x=3, y=4, z=0)) for name in names})
        with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))):
            obj._calculate_distances()
            obj.distance_system_a.set('New')
            obj._calculate_distances()
        workers[1]()
        obj.queue.flush()
        current = obj.distance_system_a_name.cget('text')
        workers[0]()
        obj.queue.flush()
        self.assertEqual(obj.distance_system_a_name.cget('text'), current)
        self.assertIn('New', current)

    def test_deferred_exception_keeps_original_message(self):
        obj = app()
        obj._resolve_distance_systems = Mock(side_effect=RuntimeError('original error'))
        with patch('threading.Thread', InlineThread), patch('logging.Logger.error'):
            obj._calculate_distances()
            obj.queue.flush()
        self.assertIn('original error', obj.distance_status_label.cget('text'))

    def test_network_failure_is_distinct_from_missing_coordinates(self):
        obj = app()
        obj._distance_coordinate_lookup = Mock(side_effect=[requests.Timeout('timeout'), None])
        with patch('logging.Logger.warning'):
            rows = obj._resolve_distance_systems(('A', 'B'), None, None, lambda: False)
        self.assertEqual(rows['a']['error'], 'timeout')
        self.assertIsNone(rows['b']['error'])
        obj._apply_distance_results(0, ('A', 'B'), rows)
        self.assertIn('Could not look up', obj.distance_a_sol_label.cget('text'))
        self.assertIn('Coordinates unavailable', obj.distance_b_sol_label.cget('text'))

    def test_unique_names_are_resolved_once_including_failures(self):
        obj = app()
        obj._distance_coordinate_lookup = Mock(return_value=None)
        results = obj._resolve_distance_systems(('A', 'a', 'A', ''), None, None, lambda: False)
        obj._distance_coordinate_lookup.assert_called_once()
        self.assertEqual(len(results), 1)

    def test_local_coordinate_sources_precede_network(self):
        obj = app()
        obj.distance_calculator.get_system_coordinates = Mock(return_value=dict(x=9, y=0, z=0))
        obj.cargo_monitor = SimpleNamespace(user_db=SimpleNamespace(_get_coordinates_from_visited_systems=Mock(return_value=(3, 4, 0))))
        self.assertEqual(obj._distance_coordinate_lookup('current', 'Current', (0, 0, 0)), dict(x=0, y=0, z=0))
        self.assertEqual(obj._distance_coordinate_lookup('Visited', None, None), dict(x=3, y=4, z=0))
        obj.cargo_monitor.user_db._get_coordinates_from_visited_systems.return_value = None
        obj.ring_finder = SimpleNamespace(systems_data={}, _get_system_coords_from_galaxy_db=Mock(return_value=dict(x=6, y=0, z=0)))
        self.assertEqual(obj._distance_coordinate_lookup('Local', None, None)['x'], 6)
        obj.ring_finder._get_system_coords_from_galaxy_db.return_value = None
        self.assertEqual(obj._distance_coordinate_lookup('Remote', None, None)['x'], 9)
        obj.distance_calculator.get_system_coordinates.assert_called_once_with('Remote')


class RefreshChecks(unittest.TestCase):
    def test_refresh_button_disables_until_success_or_failure_is_shown(self):
        for error in (None, RuntimeError('scan failed')):
            with self.subTest(error=error):
                obj = app()
                parser = SimpleNamespace(get_last_known_system=Mock(return_value='Current', side_effect=error))
                obj.cargo_monitor = SimpleNamespace(journal_parser=parser)
                obj.fc_tracker = SimpleNamespace(carrier_data={})
                obj._update_home_fc_distances = Mock()
                workers = []
                with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))):
                    obj._distance_refresh_locations()
                    self.assertEqual(obj.distance_refresh_btn.cget('state'), 'disabled')
                    self.assertEqual(obj.distance_refresh_btn.cget('text'), 'Refreshing...')
                    obj._distance_refresh_locations()
                    self.assertEqual(len(workers), 1)
                workers[0]()
                callback, args = obj.queue.pending.pop(next(iter(obj.queue.pending)))
                callback(*args)
                self.assertEqual(obj.distance_refresh_btn.cget('state'), 'disabled')
                obj.queue.flush()
                self.assertEqual(obj.distance_refresh_btn.cget('state'), 'normal')
                self.assertEqual(obj.distance_refresh_btn.cget('text'), 'Refresh Locations')

    def test_repeated_refresh_requests_start_one_worker(self):
        obj = app()
        obj._resolve_distance_systems = Mock(return_value={})
        workers = []
        with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))):
            for _ in range(15):
                obj._update_home_fc_distances()
            obj.queue.flush()
            self.assertEqual(len(workers), 1)
            for _ in range(10):
                obj._update_home_fc_distances()
            obj.queue.flush()
            self.assertEqual(len(workers), 1)
            workers[0]()
            obj.queue.flush()
            self.assertEqual(len(workers), 2)
            workers[1]()
            obj.queue.flush()
        self.assertFalse(obj._distance_update_running)

    def test_old_home_values_are_rejected_and_latest_values_update_dependents(self):
        obj = app()
        obj.distance_home_system.set('New Home')
        obj._apply_distance_updates(0, ('Current', 'Home', 'Carrier'), {})
        self.assertEqual(obj.home_sol_label.cget('text'), '---')
        obj.queue.pending.clear()
        rows = {'current': info(dict(x=0, y=0, z=0)), 'new home': info(dict(x=3, y=4, z=0)), 'carrier': info(dict(x=0, y=0, z=0))}
        obj.prospector_panel = SimpleNamespace(_update_distance_display=Mock())
        obj._apply_distance_updates(obj._distance_update_generation, ('Current', 'New Home', 'Carrier'), rows)
        self.assertEqual(obj._distance_values, dict(sol=0, home=5, fc=0))
        self.assertIn('5.00 LY', obj.get_distance_info_text())
        obj.prospector_panel._update_distance_display.assert_called_once()

    def test_journal_refresh_does_not_overwrite_a_live_jump(self):
        obj = app()
        obj.fc_tracker = SimpleNamespace(carrier_data={'system': 'Latest Carrier'})
        obj.current_system = 'New Jump'
        obj.update_current_system = Mock()
        obj._apply_distance_location_refresh(0, 'Old', 'Scanned')
        obj.update_current_system.assert_not_called()
        self.assertEqual(obj.distance_fc_system.get(), 'Latest Carrier')

    def test_location_scan_error_is_deferred_safely(self):
        obj = app()
        obj.cargo_monitor = SimpleNamespace(journal_parser=SimpleNamespace(get_last_known_system=Mock(side_effect=RuntimeError('scan error'))))
        with patch('threading.Thread', InlineThread):
            obj._distance_refresh_locations()
            obj.queue.flush()
        self.assertIn('scan error', obj._set_status.call_args.args[0])

    def test_home_can_be_cleared_without_enter(self):
        obj = app()
        obj.distance_home_system.set('')
        with patch('config.load_home_system', return_value='Old'), patch('config.save_home_system') as save:
            obj._distance_set_home(SimpleNamespace())
        save.assert_called_once_with('')


class LookupChecks(unittest.TestCase):
    def response(self, payload):
        result = requests.Response()
        result.status_code = 200
        result._content = json.dumps(payload).encode()
        return result

    def test_cache_ignores_case_and_header_uses_current_version(self):
        calc = EDSMDistanceCalculator()
        with patch('edsm_distance.requests.get', return_value=self.response(dict(name='A', coords=dict(x=3, y=4, z=0)))) as get:
            self.assertEqual(calc.get_system_coordinates('A'), calc.get_system_coordinates(' a '))
        get.assert_called_once()
        self.assertIn(__version__, calc.headers['User-Agent'])

    def test_timeout_retries_then_propagates(self):
        calc = EDSMDistanceCalculator()
        with patch('edsm_distance.requests.get', side_effect=requests.Timeout('offline')) as get, \
                patch('edsm_distance.time.sleep'), patch('edsm_distance.logger.warning'):
            with self.assertRaises(requests.Timeout):
                calc.get_system_coordinates('A')
        self.assertEqual(get.call_count, 3)

    def test_unknown_system_is_not_a_network_error(self):
        with patch('edsm_distance.requests.get', return_value=self.response({})):
            self.assertIsNone(EDSMDistanceCalculator().get_system_coordinates('Unknown'))

    def test_concurrent_same_system_lookup_is_shared(self):
        calc = EDSMDistanceCalculator()
        started, release = threading.Event(), threading.Event()
        def fetch(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(3))
            return self.response(dict(name='A', coords=dict(x=1, y=0, z=0)))
        with patch('edsm_distance.requests.get', side_effect=fetch) as get, ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(calc.get_system_coordinates, 'A')
            self.assertTrue(started.wait(3))
            second = pool.submit(calc.get_system_coordinates, 'a')
            release.set()
            self.assertEqual(first.result(timeout=3), second.result(timeout=3))
        get.assert_called_once()


class BuildChecks(unittest.TestCase):
    def test_tab_builds_in_both_languages_and_scaled_fonts(self):
        for language in ('en', 'de'):
            for scale in (1, 1.5):
                with self.subTest(language=language, scale=scale):
                    root = tk.Tk()
                    root.withdraw()
                    try:
                        obj = app()
                        obj._scaled_font = lambda size, weight='normal': ('Arial', round(size * scale), weight)
                        obj._scaled_px = lambda value: round(value * scale)
                        with patch.dict(namespace, t=translate(language)), \
                                patch('config.load_home_system', return_value='Home'), \
                                patch('config.load_distance_calculator_systems', return_value=('A', 'B')), \
                                patch('config.load_theme', return_value='dark_gray'), \
                                patch('system_autocomplete.SystemAutocomplete'):
                            frame = ttk.Frame(root)
                            obj._build_distance_calculator_tab(frame)
                            obj.distance_system_a.set('Changed')
                            self.assertEqual(obj._distance_calculation_generation, 1)
                            def descendants(widget):
                                for child in widget.winfo_children():
                                    yield child
                                    yield from descendants(child)
                            home = next(widget for widget in descendants(frame) if isinstance(widget, tk.Entry)
                                        and str(widget.cget('textvariable')) == str(obj.distance_home_system))
                            self.assertTrue(home.bind('<FocusOut>'))
                    finally:
                        for callback in root.tk.call('after', 'info'):
                            root.tk.call('after', 'cancel', callback)
                        root.destroy()


if __name__ == '__main__':
    unittest.main()
