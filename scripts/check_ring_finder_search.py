import ast
import logging
import math
import os
from pathlib import Path
import re
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
        '_insert_row_batch', '_sort_column', '_update_results',
    }),
    load_methods('app/ring_finder_search.py', 'RingFinderSearchMixin', {
        '_limit_results_by_unique_rings', '_run_search_callback', '_complete_search',
        '_search_worker',
    }),
), {})
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

    def set(self, key, column):
        return self.rows[key][column]

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

    def test_new_search_during_metadata_lookup_discards_old_results(self):
        f = self.finder
        f.db_ready = True
        f.systems_data = {}
        f._get_hotspots = Mock(return_value=[row()])
        f._is_all_minerals = Mock(return_value=True)
        f._update_results = Mock()
        f._reset_search_button = Mock()
        f._fill_missing_metadata_edsm = Mock(
            side_effect=lambda rows: setattr(f, '_search_generation', 2))
        f._search_worker('Sol', 'All', 'All Minerals', False, 50,
                         dict(x=0, y=0, z=0), 10, search_generation=1, use_spansh_pp=False)
        f.parent.flush()
        f._update_results.assert_not_called()
        f._reset_search_button.assert_not_called()

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
