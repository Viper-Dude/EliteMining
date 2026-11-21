import ast
from contextlib import closing
import logging
import math
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Dict, List, Optional
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]


def load_methods(filename, class_name, names):
    source = (ROOT / filename).read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == class_name)
    methods = [node for node in original.body
               if isinstance(node, ast.FunctionDef) and node.name in names]
    # Exercise the real methods without starting the app or opening its databases.
    cls = ast.ClassDef(name=class_name, bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    namespace = dict(List=List, Dict=Dict, Optional=Optional, math=math, re=re, t=lambda key: key)
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[class_name]


Finder = type('RingFinder', (
    load_methods('app/ring_finder.py', 'RingFinder', {
        '_insert_row_batch', '_sort_column', '_update_results', '_powerplay_display',
    }),
    load_methods('app/ring_finder_search.py', 'RingFinderSearchMixin', {
        '_limit_results_by_unique_rings', '_run_search_callback', '_complete_search',
        '_search_worker', '_hotspot_missing_metadata', '_start_edsm_metadata_fill',
        '_edsm_metadata_worker', '_read_filled_ring_metadata', '_apply_edsm_metadata',
        '_start_pp_backfill', '_pp_backfill_worker', '_apply_pp_backfill',
    }),
), {})
EDSM_GLOBALS = Finder._start_edsm_metadata_fill.__globals__
EDSM_GLOBALS.update(log=logging.getLogger('edsm-fill-test'),
                    translate_ring_type=lambda value: f'{value} (translated)')
Database = load_methods('app/user_database.py', 'UserDatabase', {'_normalize_body_name'})
Saves = load_methods('app/ring_finder.py', 'RingFinder', {'_save_filter_settings', '_save_auto_search_state'})


class Parent:
    def __init__(self):
        self.pending = []

    def winfo_exists(self):
        return True

    def after(self, delay, callback, *args):
        self.pending.append((callback, args))

    def flush(self):
        while self.pending:
            callback, args = self.pending.pop(0)
            callback(*args)


class Tree:
    def __init__(self):
        self.rows = {}
        self.order = []
        self.sequence = 0

    def get_children(self, *args):
        return tuple(self.order)

    def insert(self, parent, where, values, tags):
        self.sequence += 1
        key = str(self.sequence)
        self.rows[key] = values
        self.order.append(key)
        return key

    def delete(self, key):
        del self.rows[key]
        self.order.remove(key)

    def set(self, key, column, value=None):
        if value is None:
            return self.rows[key][column]
        self.rows[key][column] = value

    def exists(self, key):
        return key in self.rows

    def move(self, key, parent, index):
        self.order.remove(key)
        self.order.insert(index, key)


def variable(value):
    return SimpleNamespace(get=lambda: value)


def row(system='Sol', body='1 A Ring', **values):
    return dict(systemName=system, bodyName=body, distance='1.0', **values)


class RingFinderSearchTests(unittest.TestCase):
    def setUp(self):
        self.finder = Finder()
        self.finder.user_db = Mock()
        self.finder.user_db._normalize_body_name = Database()._normalize_body_name
        self.finder._search_generation = 1
        self.finder.parent = Parent()
        self.finder.results_tree = Tree()
        self.finder._result_row_hotspots = {}
        self.finder._finish_update_results = Mock()

    def test_ring_limit_keeps_both_sources_even_when_separated(self):
        rows = [row(source='Local'), row(body='2 A Ring'),
                row(body='Sol 1 A Ring', source='Spansh')]
        self.assertEqual(self.finder._limit_results_by_unique_rings(rows, 1),
                         [rows[0], rows[2]])

    def test_ring_limit_preserves_parent_body_designations(self):
        rows = [row(body='2 a A Ring'), row(body='2 A A Ring')]
        self.assertEqual(self.finder._limit_results_by_unique_rings(rows, 2), rows)

    def test_unlimited_results(self):
        rows = [row(), row(body='2 A Ring')]
        self.assertEqual(self.finder._limit_results_by_unique_rings(rows, None), rows)

    def test_old_completion_and_callbacks_cannot_change_new_search(self):
        f = self.finder
        f._update_results = Mock()
        callback = Mock()
        f.parent.after(0, f._complete_search, 1, [row()], 1)
        f.parent.after(0, f._run_search_callback, 1, callback)
        f._search_generation = 2
        f.parent.flush()
        f._update_results.assert_not_called()
        callback.assert_not_called()

    def test_stop_keeps_partial_results_until_another_search_starts(self):
        f = self.finder
        f._update_results = Mock()
        f._stopped_generation = 1
        f._search_generation = 2
        f._complete_search(1, [row()], 10)
        f._update_results.assert_called_once()
        f._update_results.reset_mock()
        f._search_generation = 3
        f._complete_search(1, [row()], 10)
        f._update_results.assert_not_called()

    def test_results_show_without_waiting_for_edsm(self):
        f = self.finder
        f.db_ready = True
        f.systems_data = {}
        f._get_hotspots = Mock(return_value=[row(ls_distance=None)])
        f._is_all_minerals = Mock(return_value=True)
        f._update_results = Mock()
        f._reset_search_button = Mock()
        f.edsm = Mock()
        f._search_worker('Sol', 'All', 'All Minerals', False, 50,
                         dict(x=0, y=0, z=0), 10, search_generation=1, use_spansh_pp=False)
        f.parent.flush()
        f._update_results.assert_called_once()
        self.assertEqual(f.edsm.mock_calls, [])

    def test_results_show_without_waiting_for_powerplay(self):
        f = self.finder
        f.db_ready = True
        f.systems_data = {}
        f._get_hotspots = Mock(return_value=[row()])
        f._is_all_minerals = Mock(return_value=True)
        f._update_results = Mock()
        f._reset_search_button = Mock()
        module = ModuleType('system_finder_api')
        module.SystemFinderAPI = Mock()
        for use_spansh_pp, request in ((True, ('Sol', 50)), (False, None)):
            with self.subTest(use_spansh_pp=use_spansh_pp), patch.dict(sys.modules, system_finder_api=module):
                f._update_results.reset_mock()
                f._search_worker('Sol', 'All', 'All Minerals', False, 50,
                                 dict(x=0, y=0, z=0), 10, search_generation=1, use_spansh_pp=use_spansh_pp)
                f.parent.flush()
                f._update_results.assert_called_once()
                self.assertEqual(f._pp_backfill_request, request)
        self.assertEqual(module.SystemFinderAPI.mock_calls, [])

    def test_old_row_batches_stop_after_a_new_search_or_refresh(self):
        f = self.finder
        rows = [dict(values=(i,), tags=(), is_green=False) for i in range(30)]
        for newer_search in (True, False):
            with self.subTest(newer_search=newer_search):
                f.results_tree = Tree()
                f._results_generation = generation = (f._search_generation, object())
                f._insert_row_batch(rows, 0, 30, 'Sol', 'All', set(), generation=generation)
                self.assertEqual(len(f.results_tree.rows), 25)
                if newer_search:
                    f._search_generation += 1
                else:
                    f._results_generation = (f._search_generation, object())
                f.parent.flush()
                self.assertEqual(len(f.results_tree.rows), 25)
        f._finish_update_results.assert_not_called()

    def test_display_filters_before_limit_and_visit_lookup_only_once(self):
        f = self.finder
        db = f.user_db
        db.bulk_get_visit_counts.return_value = {'Visited': 2}
        for name in ('bulk_get_favourites_for_rings', 'bulk_get_ring_comments_for_rings',
                     'bulk_get_ring_density_for_rings', 'bulk_get_ring_last_mined',
                     'bulk_get_overlaps_for_rings', 'bulk_get_res_for_rings'):
            getattr(db, name).return_value = {}
        f.unvisited_only_var = variable(True)
        f.favourites_only_var = variable(False)
        f.reserve_var = variable('Pristine')
        f.material_var = variable('All')
        f.system_var = variable('Sol')
        f.specific_material_var = variable('All Minerals')
        f.data_source_var = variable('both')
        f.prospector_panel = None
        f._search_result_limit = 1
        f._to_english = lambda value: value
        f._is_all_minerals = lambda value: True
        for name in ('_sort_hotspots_display', '_abbreviate_material_for_display',
                     '_localize_hotspot_display'):
            setattr(f, name, lambda value: value)
        f._get_overlap_display = Mock(return_value='')
        f._get_res_display = Mock(return_value='')
        f._density_label = Mock(return_value='')
        f.systems_data = {}
        f._get_system_coords_from_galaxy_db = Mock(return_value=None)
        module = ModuleType('system_finder_api')
        module.SystemFinderAPI = SimpleNamespace(_batch_get_powerplay=lambda names: {})
        rows = [row('Visited', reserve='Pristine'), row('Wrong reserve', reserve='Low'),
                row('Wanted', reserve='Pristine'), row('Farther', reserve='Pristine')]
        with patch.dict(sys.modules, system_finder_api=module):
            f._update_results(rows)
            f.parent.flush()
        self.assertEqual([values[2] for values in f.results_tree.rows.values()], ['Wanted'])
        db.bulk_get_visit_counts.assert_called_once()
        self.assertEqual(len(f._search_cache), 4)

    def test_visits_sort_numerically_in_both_directions(self):
        f = self.finder
        module = ModuleType('ui.sort_indicator')
        module.apply_sort_arrow = Mock()
        f.sort_reverse = {}
        for value in ('2', '10', '0', '1,000', ''):
            f.results_tree.insert('', 'end', {'Visits': value}, ())
        with patch.dict(sys.modules, {'ui.sort_indicator': module}):
            for reverse, expected in ((False, ['0', '2', '10', '1,000', '']),
                                      (True, ['1,000', '10', '2', '0', ''])):
                f._sort_column('Visits', reverse)
                self.assertEqual([f.results_tree.rows[key]['Visits']
                                  for key in f.results_tree.order], expected)


class InlineThread:
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class EdsmAfterDisplayTests(unittest.TestCase):
    def setUp(self):
        f = self.finder = Finder()
        f.parent = Parent()
        f.results_tree = Tree()
        f._search_generation = 1
        f._results_generation = self.generation = (1, object())
        f._result_row_hotspots = {}
        f.edsm = Mock()
        self.fill = f.edsm.fill_missing_metadata_for_systems_direct
        self.fill.return_value = {'materials_updated': 0, 'no_data_systems': []}

    def show(self, *hotspots):
        for hotspot in hotspots:
            values = {'LS': hotspot.get('ls', 'No data'), 'Ring Type': hotspot.get('ring_type') or 'No data'}
            key = self.finder.results_tree.insert('', 'end', values, ())
            self.finder._result_row_hotspots[key] = hotspot
        return list(self.finder._result_row_hotspots)

    def run_fill(self):
        with patch.dict(EDSM_GLOBALS, threading=SimpleNamespace(Thread=InlineThread)):
            self.finder._start_edsm_metadata_fill(self.generation)

    def queried(self):
        return self.fill.call_args[0][0]

    def use_filled_db(self, folder):
        path = os.path.join(folder, 'user.db')
        with closing(sqlite3.connect(path)) as conn:
            conn.execute('CREATE TABLE hotspot_data (system_name TEXT, body_name TEXT, ring_type TEXT, ls_distance REAL)')
            conn.executemany('INSERT INTO hotspot_data VALUES (?, ?, ?, ?)',
                             [('Sol', '1 A Ring', 'Icy', 1234.5), ('Sol', '2 A Ring', 'Metallic', 99.0)])
            conn.commit()
        self.finder.user_db = SimpleNamespace(db_path=path)
        self.fill.return_value = {'materials_updated': 3, 'no_data_systems': []}

    def test_only_shown_rows_missing_data_are_queried_closest_first(self):
        self.finder._edsm_no_data_systems = {'known miss'}
        self.show(row('Near', ring_type='Icy', ls_distance=None), row('Complete', ring_type='Icy', ls_distance=5),
                  row('Known Miss', ls_distance=None), row('Far', ring_type='No data', ls_distance=7),
                  row('Near', body='2 A Ring', ls_distance=None))
        self.run_fill()
        self.assertEqual(self.queried(), ['Near', 'Far'])

    def test_large_result_lists_query_at_most_30_systems(self):
        self.show(*[row(f'S{i}', ls_distance=None) for i in range(100)])
        self.run_fill()
        self.assertEqual(self.queried(), [f'S{i}' for i in range(30)])

    def test_complete_rows_start_no_lookup(self):
        self.show(row(ring_type='Icy', ls_distance=5))
        self.run_fill()
        self.fill.assert_not_called()

    def test_systems_without_edsm_data_are_not_asked_again(self):
        self.fill.return_value = {'materials_updated': 0, 'no_data_systems': ['Empty']}
        self.show(row('Empty', ls_distance=None), row('Timed out', ls_distance=None))
        self.run_fill()
        self.assertEqual(self.queried(), ['Empty', 'Timed out'])
        self.fill.return_value = {'materials_updated': 0, 'no_data_systems': []}
        self.run_fill()
        self.assertEqual(self.queried(), ['Timed out'])

    def test_lookup_is_cancelled_by_a_new_search_or_redraw(self):
        self.show(row(ls_distance=None))
        self.run_fill()
        is_cancelled = self.fill.call_args[1]['is_cancelled']
        self.assertFalse(is_cancelled())
        self.finder._results_generation = (1, object())
        self.assertTrue(is_cancelled())
        self.finder._results_generation = self.generation
        self.finder._search_generation = 2
        self.assertTrue(is_cancelled())

    def test_filled_values_update_the_shown_rows_in_place(self):
        missing = row('Sol', '1 A Ring', ring_type='No data', ls_distance=None, ls='No data')
        partial = row('Sol', 'Sol 2 A Ring', ring_type='Rocky', ls_distance=None, ls='No data')
        with tempfile.TemporaryDirectory() as folder:
            self.use_filled_db(folder)
            first, second = self.show(missing, partial)
            self.run_fill()
            self.finder.parent.flush()
        rows = self.finder.results_tree.rows
        self.assertEqual(rows[first], {'LS': '1,234', 'Ring Type': 'Icy (translated)'})
        self.assertEqual(rows[second], {'LS': '99', 'Ring Type': 'Rocky'})
        self.assertEqual((missing['ring_type'], missing['ls_distance'], missing['ls']),
                         ('Icy (translated)', 1234.5, '1,234'))

    def test_late_values_cannot_change_a_newer_search_or_redraw(self):
        for newer_search in (True, False):
            with self.subTest(newer_search=newer_search), tempfile.TemporaryDirectory() as folder:
                self.setUp()
                self.use_filled_db(folder)
                hotspot = row('Sol', '1 A Ring', ls_distance=None, ls='No data')
                key, = self.show(hotspot)
                self.run_fill()
                if newer_search:
                    self.finder._search_generation = 2
                else:
                    self.finder._results_generation = (1, object())
                self.finder.parent.flush()
                self.assertEqual(self.finder.results_tree.rows[key]['LS'], 'No data')
                self.assertIsNone(hotspot['ls_distance'])


class PowerPlayAfterDisplayTests(unittest.TestCase):
    def setUp(self):
        f = self.finder = Finder()
        f.parent = Parent()
        f.results_tree = Tree()
        f._search_generation = 1
        f._results_generation = self.generation = (1, object())
        f._result_row_hotspots = {}
        f._pp_backfill_request = ('Sol', 50)
        f._format_pp_age = lambda value: ''
        api = self.api = Mock()
        api._fetch_spansh_powerplay_backfill.return_value = {
            'Newer': dict(controlling_power='Aisling Duval', power_state='Fortified'),
            'Older': dict(controlling_power='Zemina Torval', power_state='Exploited'),
            'Not shown': dict(controlling_power='Nakato Kaine', power_state='Stronghold'),
        }
        api._batch_get_powerplay.return_value = {}
        api._spansh_pp_should_replace_cache.side_effect = lambda entry, cached: entry['power_state'] != 'Exploited'
        self.module = ModuleType('system_finder_api')
        self.module.SystemFinderAPI = api

    def show(self, *hotspots):
        for hotspot in hotspots:
            key = self.finder.results_tree.insert('', 'end', {'PowerPlay': 'common.pp_no_data'}, ())
            self.finder._result_row_hotspots[key] = hotspot
        return list(self.finder._result_row_hotspots)

    def run_backfill(self):
        with patch.dict(EDSM_GLOBALS, threading=SimpleNamespace(Thread=InlineThread)), \
                patch.dict(sys.modules, system_finder_api=self.module):
            self.finder._start_pp_backfill(self.generation)

    def test_newer_spansh_data_fills_the_shown_rows_in_place(self):
        newer, older, second = self.show(row('Newer'), row('Older'), row('Newer', '2 A Ring'))
        self.run_backfill()
        self.finder.parent.flush()
        rows = self.finder.results_tree.rows
        self.assertEqual(rows[newer]['PowerPlay'], 'Aisling Duval / Fortified')
        self.assertEqual(rows[second]['PowerPlay'], 'Aisling Duval / Fortified')
        self.assertEqual(rows[older]['PowerPlay'], 'common.pp_no_data')
        self.api._fetch_spansh_powerplay_backfill.assert_called_once()
        self.assertEqual(self.api._fetch_spansh_powerplay_backfill.call_args[0], ('Sol', 50))
        stored, = self.api._store_powerplay_batch.call_args[0]
        self.assertEqual(set(stored), {'Newer'})

    def test_no_request_or_no_rows_starts_no_lookup(self):
        self.run_backfill()
        self.finder._pp_backfill_request = None
        self.show(row('Newer'))
        self.run_backfill()
        self.api._fetch_spansh_powerplay_backfill.assert_not_called()

    def test_lookup_is_cancelled_by_a_new_search_or_redraw(self):
        self.show(row('Newer'))
        self.run_backfill()
        is_cancelled = self.api._fetch_spansh_powerplay_backfill.call_args[1]['is_cancelled']
        self.assertFalse(is_cancelled())
        self.finder._results_generation = (1, object())
        self.assertTrue(is_cancelled())
        self.finder._results_generation = self.generation
        self.finder._search_generation = 2
        self.assertTrue(is_cancelled())

    def test_late_values_cannot_change_a_newer_search_or_redraw(self):
        for newer_search in (True, False):
            with self.subTest(newer_search=newer_search):
                self.setUp()
                key, = self.show(row('Newer'))
                self.run_backfill()
                if newer_search:
                    self.finder._search_generation = 2
                else:
                    self.finder._results_generation = (1, object())
                self.finder.parent.flush()
                self.assertEqual(self.finder.results_tree.rows[key]['PowerPlay'], 'common.pp_no_data')

    def test_complete_search_keeps_the_request_for_the_shown_results(self):
        f = self.finder
        f._update_results = Mock()
        f._complete_search(1, [row()], 10, ('Colonia', 100))
        self.assertEqual(f._pp_backfill_request, ('Colonia', 100))
        f._complete_search(1, [row()], 10)
        self.assertIsNone(f._pp_backfill_request)


SPANSH_CONSTANTS = ('SPANSH_SIGNAL_NAMES', 'APP_SIGNAL_NAMES', 'SPANSH_HOTSPOT_SIGNALS')


def load_spansh_search():
    cls = load_methods('app/ring_finder_search.py', 'RingFinderSearchMixin', {
        '_search_spansh_with_filters', '_spansh_bodies_to_hotspots', '_is_valid_mining_material',
    })
    namespace = cls._search_spansh_with_filters.__globals__
    tree = ast.parse((ROOT / 'app/ring_finder_search.py').read_text(encoding='utf-8-sig'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(target, 'id', None) in SPANSH_CONSTANTS
                                                for target in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'ring_finder_search.py', 'exec'), namespace)
    namespace.update(log=logging.getLogger('spansh-search-test'),
                     translate_ring_type=lambda value: value,
                     translate_reserve_level=lambda value: value)
    return cls


SpanshSearch = load_spansh_search()


class SpanshPagingTests(unittest.TestCase):
    def setUp(self):
        f = self.finder = SpanshSearch()
        f.parent = Parent()
        f.status_var = Mock()
        f._ring_type_rev_map = {}
        f._resolve_spansh_system_name = Mock(return_value=None)
        f._is_all_minerals = lambda value: value == 'All Minerals'
        f._update_spansh_status = Mock()
        f._last_spansh_call = 0
        f.user_db = Mock()
        self.payloads = []
        sleep = patch('time.sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def serve(self, signal='Painite', pages=10, page_size=500):
        def request(service, method, url, json=None, **kwargs):
            self.payloads.append(json)
            page = json['page']
            bodies = [] if page >= pages else [
                dict(system_name=f'Sys {page}-{i}', name=f'Body {i}', distance=0.01 * (page * page_size + i),
                     rings=[dict(type='Icy', name=f'Sys {page}-{i} A Ring',
                                 signals=[dict(name=signal, count=2)])])
                for i in range(page_size)]
            return SimpleNamespace(raise_for_status=lambda: None,
                                   json=lambda: dict(count=pages * page_size, results=bodies))
        self.finder._search_spansh_with_filters.__globals__['tracked_request'] = request

    def search(self, material='All Minerals', limit=150, stop_at_limit=True):
        return self.finder._search_spansh_with_filters(
            'Sol', 'All', material, 100, limit, dict(x=0, y=0, z=0), stop_at_limit=stop_at_limit)

    def test_paging_stops_once_enough_rings_are_collected(self):
        self.serve()
        rows = self.search(limit=600)
        self.assertEqual(len(self.payloads), 2)
        self.assertEqual(len(rows), 1000)

    def test_paging_continues_when_later_filters_may_drop_rows(self):
        self.serve()
        self.search(limit=150, stop_at_limit=False)
        self.assertEqual(len(self.payloads), 10)

    def test_short_page_ends_paging(self):
        self.serve(pages=1, page_size=40)
        self.search(stop_at_limit=False)
        self.assertEqual(len(self.payloads), 1)

    def test_all_minerals_asks_spansh_for_hotspot_rings_only(self):
        self.serve()
        self.search()
        names = self.payloads[0]['filters']['ring_signals'][0]['name']
        self.assertIn('Void Opal', names)
        self.assertIn('Painite', names)

    def test_void_opals_use_spansh_spelling_and_come_back_in_app_spelling(self):
        self.serve(signal='Void Opal', pages=1, page_size=1)
        rows = self.search(material='Void Opals')
        self.assertEqual(self.payloads[0]['filters']['ring_signals'][0]['name'], ['Void Opal'])
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['type'], rows[0]['count']), ('Void Opals (2)', 2))


NameLookup = load_methods('app/ring_finder_search.py', 'RingFinderSearchMixin', {'_resolve_spansh_system_name'})


class SpanshNameLookupTests(unittest.TestCase):
    def setUp(self):
        self.finder = NameLookup()
        self.calls = []
        self.answer = SimpleNamespace(status_code=200, json=lambda: dict(values=['HIP 21750', 'HIP 21750 A']))

        def request(service, method, url, **kwargs):
            self.calls.append((service, kwargs['params']['q'], kwargs['timeout']))
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer
        NameLookup._resolve_spansh_system_name.__globals__.update(
            tracked_request=request, log=logging.getLogger('name-lookup-test'))

    def test_answer_is_reused_for_any_capitalization(self):
        self.assertEqual(self.finder._resolve_spansh_system_name('hip 21750'), 'HIP 21750')
        self.assertEqual(self.finder._resolve_spansh_system_name('Hip 21750 '), 'HIP 21750')
        self.assertEqual(self.calls, [('spansh', 'hip 21750', 10)])

    def test_journal_name_needs_no_request(self):
        self.finder.prospector_panel = SimpleNamespace(last_system='Col 285 Sector AB-C d1-2',
                                                       main_app=SimpleNamespace(current_system=None))
        self.assertEqual(self.finder._resolve_spansh_system_name('col 285 sector ab-c d1-2'),
                         'Col 285 Sector AB-C d1-2')
        self.assertEqual(self.calls, [])

    def test_stop_sends_no_request(self):
        self.assertIsNone(self.finder._resolve_spansh_system_name('Sol', is_cancelled=lambda: True))
        self.assertEqual(self.calls, [])

    def test_failed_lookup_is_asked_again(self):
        self.answer = OSError('offline')
        self.assertIsNone(self.finder._resolve_spansh_system_name('Sol'))
        self.answer = SimpleNamespace(status_code=500, json=lambda: {})
        self.assertIsNone(self.finder._resolve_spansh_system_name('Sol'))
        self.answer = SimpleNamespace(status_code=200, json=lambda: dict(values=['Sol']))
        self.assertEqual(self.finder._resolve_spansh_system_name('sol'), 'Sol')
        self.assertEqual(len(self.calls), 3)


class RingFinderSaveFailureTests(unittest.TestCase):
    def setUp(self):
        Saves._save_filter_settings.__globals__.update(os=os, log=logging.getLogger('ring-save-test'))
        app_path = patch.object(sys, 'path', [str(ROOT / 'app')] + sys.path)
        app_path.start()
        self.addCleanup(app_path.stop)

    def test_failed_filter_save_is_logged(self):
        finder = Saves()
        finder._filters_loaded = True
        with self.assertLogs('ring-save-test', 'ERROR') as logs:
            finder._save_filter_settings()
        self.assertIn('Saving Ring Finder filters failed', logs.output[0])

    def test_auto_search_state_is_written_and_failure_is_logged(self):
        with tempfile.TemporaryDirectory() as folder:
            finder = Saves()
            finder.prospector_panel = None
            finder.auto_search_var = SimpleNamespace(get=lambda: True)
            finder.vars_dir = folder
            finder._save_auto_search_state()
            self.assertEqual((Path(folder) / 'autoSearch.txt').read_text(encoding='utf-8'), '1')
            self.assertFalse((Path(folder) / 'autoSearch.txt.tmp').exists())

            blocker = Path(folder) / 'Variables'
            blocker.write_text('not a folder', encoding='utf-8')
            finder.vars_dir = str(blocker)
            with self.assertLogs(level='ERROR') as logs:
                finder._save_auto_search_state()
        self.assertIn('Atomic write failed', logs.output[0])


if __name__ == '__main__':
    unittest.main()
