import ast
import json
import logging
from pathlib import Path
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import requests
from column_visibility_helper import ColumnVisibilityMixin
from system_finder_api import SystemFinderAPI as API
from ui.search_control import SearchControl
from ui.striped_treeview import StripedTreeview
from check_ring_finder_search import load_methods


Methods = load_methods('app/main.py', 'App', {
    '_create_sysfinder_results_table', '_sysfinder_show_results', '_populate_sysfinder_rows',
    '_sort_sysfinder_column', '_sysfinder_search_complete', '_sysfinder_trader_complete',
    '_on_sysfinder_reference_changed', '_confirm_sysfinder_reference',
    '_update_sysfinder_ref_info', '_sysfinder_ref_info_complete',
    '_update_sysfinder_ref_labels', '_format_sysfinder_population', '_compute_pp_foryou',
    '_compute_pp_merits', '_save_player_power', '_search_systems_worker',
    '_search_material_traders_worker', '_fetch_sysfinder_pp_complete',
    '_sysfinder_option_label', '_sysfinder_option_value',
    '_search_systems', '_search_material_traders',
    '_use_current_system_sysfinder',
})
Methods._create_sysfinder_results_table.__globals__.update(ttk=ttk, threading=threading, logging=logging, SearchControl=SearchControl,
                                                          StripedTreeview=StripedTreeview)


def setUpModule():
    # Some code paths save through the real config module; keep them off app/config.json
    import config
    global _real_config_file, _config_dir
    _config_dir = tempfile.TemporaryDirectory()
    _real_config_file = config.CONFIG_FILE
    config.CONFIG_FILE = str(Path(_config_dir.name) / 'config.json')


def tearDownModule():
    import config
    config.CONFIG_FILE = _real_config_file
    _config_dir.cleanup()


class App(Methods, ColumnVisibilityMixin):
    pass


def translate(language):
    strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
    def get(key):
        value = strings
        for part in key.split('.'):
            if not isinstance(value, dict) or part not in value:
                return key
            value = value[part]
        return value
    return get


class APIChecks(unittest.TestCase):
    def test_empty_search_skips_all_enrichment(self):
        response = Mock()
        response.json.return_value = {'results': [], 'count': 0}
        with patch('system_finder_api.requests.post', return_value=response) as post, \
                patch.object(API, '_batch_get_powerplay') as cache:
            self.assertEqual(API.search_systems('Sol'), [])
            post.assert_called_once()
            cache.assert_not_called()

    def test_timeouts_reach_callers(self):
        with patch('system_finder_api.requests.post', side_effect=requests.Timeout('timeout')), \
                patch('system_finder_api.log.error'):
            with self.assertRaises(requests.Timeout):
                API.search_systems('Sol')
            with self.assertRaises(requests.Timeout):
                API.search_material_traders('Sol', 'Raw')

    def test_reference_and_results_share_powerplay_conversion(self):
        system = dict(name='Sol', controlling_power='A. Lavigny-Duval', power_state='Fortified')
        response = Mock()
        response.json.return_value = {'results': [system]}
        for cached in (None, dict(controlling_power='~none~', power_state='Expansion')):
            with self.subTest(cached=cached), patch('system_finder_api.requests.post', return_value=response), \
                    patch.object(API, '_get_powerplay_from_cache', return_value=cached):
                reference = API.get_system_status('sol')
                expected = API._convert_spansh_system(system, {'Sol': cached} if cached else {})
                self.assertEqual(reference, expected)
        self.assertEqual(API._convert_spansh_system(system)['power'], 'Arissa Lavigny-Duval')

    def test_missing_numbers_stay_distinct_from_zero(self):
        self.assertIsNone(API._convert_spansh_system({'name': 'Unknown'})['distance'])
        self.assertIsNone(API._convert_spansh_system({'name': 'Unknown'})['population'])
        self.assertEqual(API._convert_spansh_system({'name': 'Zero', 'distance': 0, 'population': 0})['distance'], 0)


class ReferenceChecks(unittest.TestCase):
    def setUp(self):
        self.app = app = App()
        self.current = 'Old'
        app.sysfinder_reference_system = SimpleNamespace(get=lambda: self.current)
        app._sysfinder_ref_requested = None
        app._sysfinder_ref_generation = 0
        app._sysfinder_ref_status = None
        app._update_sysfinder_ref_labels = Mock()
        self.callbacks = []
        app.after = lambda delay, callback, *args: self.callbacks.append((callback, args)) or len(self.callbacks)
        app.after_cancel = Mock()

    def test_old_success_cannot_overwrite_new_reference(self):
        app = self.app
        workers = []
        with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))), \
                patch.object(API, 'get_system_status', return_value={'power': 'Felicia Winters'}):
            app._update_sysfinder_ref_info('Old')
            self.current = 'New'
            app._on_sysfinder_reference_changed()
            workers[0]()
            callback, args = self.callbacks.pop()
            callback(*args)
        self.assertIsNone(app._sysfinder_ref_status)
        self.assertEqual(app._update_sysfinder_ref_labels.call_args.args, (None, 'New'))

    def test_typing_invalidates_details_without_scheduling_a_lookup(self):
        self.app._update_sysfinder_ref_info = Mock()
        for text in ('N', 'Ne', 'New'):
            self.current = text
            self.app._on_sysfinder_reference_changed()
        self.app._update_sysfinder_ref_info.assert_not_called()
        self.assertEqual(self.callbacks, [])
        self.assertEqual(self.app._sysfinder_ref_generation, 3)

    def test_use_current_preserves_existing_details_and_inflight_request(self):
        for status in (None, {'population': 1}):
            with self.subTest(status=status):
                self.current = 'Sol'
                self.app.sysfinder_reference_system.set = Mock()
                self.app.get_current_system = Mock(return_value='Sol')
                self.app._ac_sysfinder_ref = Mock()
                self.app._set_status = Mock()
                self.app._sysfinder_ref_requested = 'Sol'
                self.app._sysfinder_ref_status = status
                self.app._update_sysfinder_ref_info = Mock()
                self.app._use_current_system_sysfinder()
                self.app.sysfinder_reference_system.set.assert_not_called()
                self.app._update_sysfinder_ref_info.assert_not_called()
                self.app._update_sysfinder_ref_labels.assert_not_called()
                self.assertIs(self.app._sysfinder_ref_status, status)

    def test_use_current_changes_and_confirms_a_different_system_once(self):
        def set_system(value):
            self.current = value
            self.app._on_sysfinder_reference_changed()
        self.app.sysfinder_reference_system.set = Mock(side_effect=set_system)
        self.app.get_current_system = Mock(return_value='Sol')
        self.app._ac_sysfinder_ref = Mock()
        self.app._set_status = Mock()
        self.app._update_sysfinder_ref_info = Mock()
        self.app._use_current_system_sysfinder()
        self.app.sysfinder_reference_system.set.assert_called_once_with('Sol')
        self.app._update_sysfinder_ref_info.assert_called_once_with('Sol')

    def test_selection_followed_by_search_shares_one_details_request(self):
        workers = []
        with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))), \
                patch.object(API, 'get_system_status', return_value={'population': 1}):
            self.app._confirm_sysfinder_reference()
            self.app._confirm_sysfinder_reference()
            self.assertEqual(len(workers), 1)
            workers[0]()
            callback, args = self.callbacks.pop()
            callback(*args)
            self.app._confirm_sysfinder_reference()
            self.assertEqual(len(workers), 1)

    def test_failed_details_request_can_be_retried(self):
        workers = []
        with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))), \
                patch.object(API, 'get_system_status', return_value=None):
            self.app._confirm_sysfinder_reference()
            workers[0]()
            callback, args = self.callbacks.pop()
            callback(*args)
            self.app._confirm_sysfinder_reference()
            self.assertEqual(len(workers), 2)

    def test_autocomplete_previews_do_not_confirm_but_selection_does(self):
        from system_autocomplete import SystemAutocomplete
        root = tk.Tk()
        root.withdraw()
        try:
            var = tk.StringVar(root, value='Old')
            self.app.sysfinder_reference_system = var
            var.trace_add('write', self.app._on_sysfinder_reference_changed)
            entry = ttk.Entry(root, textvariable=var)
            ac = SystemAutocomplete(entry, var, root, on_select=self.app._confirm_sysfinder_reference)
            ac._listbox_toplevel = Mock()
            ac._lb = Mock()
            ac._lb.size.return_value = 2
            ac._lb.get.side_effect = lambda index: ('Old', 'New')[index]
            ac._lb.curselection.return_value = (1,)
            workers = []
            with patch('threading.Thread', side_effect=lambda **kw: SimpleNamespace(start=lambda: workers.append(kw['target']))):
                var.set('N')
                var.set('Ne')
                ac._move_selection(1)
                ac._move_selection(1)
                self.assertEqual(workers, [])
                ac._select()
                self.assertEqual(len(workers), 1)
                self.assertEqual(var.get(), 'New')
        finally:
            root.destroy()

    def test_search_and_trader_buttons_confirm_reference_but_stop_does_not(self):
        for method in ('_search_systems', '_search_material_traders'):
            with self.subTest(method=method):
                obj = App()
                obj.after = Mock()
                obj.sysfinder_reference_system = SimpleNamespace(get=lambda: 'Sol')
                obj.sysfinder_search_btn = Mock()
                obj.sysfinder_trader_btn = Mock()
                obj.sysfinder_status_label = Mock()
                obj._ac_sysfinder_ref = Mock()
                obj._confirm_sysfinder_reference = Mock()
                for field in ('allegiance', 'government', 'security', 'economy', 'state', 'population', 'power', 'pp_state', 'trader_type'):
                    setattr(obj, 'sysfinder_' + field, SimpleNamespace(get=lambda: 'Any'))
                with patch('threading.Thread'):
                    getattr(obj, method)()
                    getattr(obj, method)()
                obj._confirm_sysfinder_reference.assert_called_once_with()

    def test_no_controller_and_unpledged_advice(self):
        get = translate('en')
        with patch.dict(Methods._compute_pp_foryou.__globals__, t=get):
            self.assertEqual(self.app._compute_pp_foryou('~none~', 'Unoccupied', 'Felicia Winters'), 'Acquire')
            self.assertEqual(self.app._compute_pp_foryou(None, None, 'Felicia Winters'), '')
            self.assertEqual(self.app._compute_pp_foryou('~none~', 'Unoccupied', 'Select your pledge...'), '')
            self.assertEqual(self.app._compute_pp_foryou('Felicia Winters', 'Fortified', 'Felicia Winters'), get('system_finder.pp_reinforce'))

    def test_pledge_change_refreshes_existing_details_without_request(self):
        self.app.sysfinder_my_power_var = SimpleNamespace(get=lambda: 'Felicia Winters')
        self.app._sysfinder_ref_status = dict(power='Felicia Winters', power_state='Fortified')
        with patch('config.save_player_power'), patch.object(API, 'get_system_status') as fetch:
            self.app._save_player_power()
        self.app._update_sysfinder_ref_labels.assert_called_once_with(self.app._sysfinder_ref_status)
        fetch.assert_not_called()


class TranslationChecks(unittest.TestCase):
    def test_all_filter_labels_map_back_to_canonical_values(self):
        import system_finder_api as api
        options = set()
        for name in ('SECURITY_OPTIONS', 'ALLEGIANCE_OPTIONS', 'GOVERNMENT_OPTIONS',
                     'STATE_OPTIONS', 'ECONOMY_OPTIONS', 'POPULATION_OPTIONS',
                     'MATERIAL_TRADER_OPTIONS', 'ELITE_POWERS', 'POWER_FILTER_OPTIONS', 'PP_STATE_OPTIONS'):
            options.update(getattr(api, name))
        for language in ('en', 'de'):
            with self.subTest(language=language), patch.dict(Methods._sysfinder_option_label.__globals__, t=translate(language)):
                app = App()
                app._sysfinder_option_values = {app._sysfinder_option_label(value): value for value in options}
                self.assertEqual(len(app._sysfinder_option_values), len(options))
                for value in options:
                    label = app._sysfinder_option_label(value)
                    self.assertFalse(label.startswith('system_finder.'))
                    self.assertEqual(app._sysfinder_option_value(label), value)
                if language == 'de':
                    self.assertEqual(app._sysfinder_option_label('Any'), 'Beliebig')
                    self.assertEqual(app._sysfinder_option_label('Stronghold'), 'Hochburg')
                    self.assertEqual(app._sysfinder_option_label('Select your pledge...'), 'Eigene Macht auswählen...')

    def test_localized_pledge_prompt_is_saved_as_canonical_value(self):
        app = App()
        app._sysfinder_option_values = {'Eigene Macht auswählen...': 'Select your pledge...'}
        app.sysfinder_my_power_var = SimpleNamespace(get=lambda: 'Eigene Macht auswählen...')
        with patch('config.save_player_power') as save:
            app._save_player_power()
        save.assert_called_once_with('Select your pledge...')


class WorkerChecks(unittest.TestCase):
    def test_arrival_display_preserves_raw_values_for_sorting(self):
        app = App()
        control = Mock()
        arrivals = (0, 0.9, 2345.9, None)
        rows = [dict(systemName='Sol', distance=0, distanceToArrival=value) for value in arrivals]
        with patch.object(API, 'search_material_traders', return_value=rows), \
                patch.dict(Methods._search_material_traders_worker.__globals__, t=translate('en')):
            app._search_material_traders_worker('Sol', 'Raw', control)
        control.failed.assert_not_called()
        formatted = control.complete.call_args.args[0]
        self.assertEqual([row[0][5] for row in formatted], ['0', '0', '2,345', '-'])
        self.assertEqual([row[2]['ls'] for row in formatted], list(arrivals))


class TableChecks(unittest.TestCase):
    def test_full_tab_builds_with_both_result_modes(self):
        for language in ('en', 'de'):
            with self.subTest(language=language):
                self.check_full_tab(language)

    def check_full_tab(self, language):
        source = ast.parse((ROOT / 'app/main.py').read_text(encoding='utf-8-sig'))
        cls = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'App')
        build = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == '_build_system_finder_tab')
        namespace = dict(tk=tk, ttk=ttk, ToolTip=Mock(), modern_color=lambda color: color, StripedTreeview=StripedTreeview,
                         t=translate(language),
                         create_action_button=lambda parent, primary=False, **kwargs: tk.Button(parent, **kwargs))
        exec(compile(ast.Module(body=[build], type_ignores=[]), 'app/main.py', 'exec'), namespace)
        root = tk.Tk()
        root.geometry('1300x850+-3000+-3000')
        try:
            app = App()
            app.current_theme = 'dark_gray'
            app._scaled_font = lambda size, weight='normal': ('Arial', size, weight)
            app._scaled_px = lambda value: value
            app.after = Mock()
            for name in ('_use_current_system_sysfinder', '_search_systems', '_search_material_traders',
                         '_show_sysfinder_context_menu', '_sysfinder_on_double_click',
                         '_create_sysfinder_context_menu', '_populate_sysfinder_system',
                         '_check_sysfinder_spansh_status', '_check_sysfinder_eddn_status'):
                setattr(app, name, Mock())
            frame = ttk.Frame(root)
            frame.pack(fill='both', expand=True)
            with patch.dict(Methods._sysfinder_option_label.__globals__, t=translate(language)), \
                    patch('config.load_theme', return_value='dark_gray'), \
                    patch('config._load_cfg', return_value={}), \
                    patch('config.load_player_power', return_value='Felicia Winters'), \
                    patch('config.load_column_visibility', return_value={}), \
                    patch('config.load_column_order', return_value=[]), \
                    patch('system_autocomplete.SystemAutocomplete'):
                namespace['_build_system_finder_tab'](app, frame)
                root.update()
                root.update_idletasks()
                table_frame = app._sysfinder_tables['system_finder']['frame']
                layout = (table_frame.winfo_rooty(), table_frame.winfo_height())
                self.assertGreater(layout[1], 1)
                for status in (None, dict(power='Felicia Winters', power_state='Fortified', population=1), None):
                    app._update_sysfinder_ref_labels(status, 'Sol', loading=status is None)
                    root.update_idletasks()
                    self.assertEqual((table_frame.winfo_rooty(), table_frame.winfo_height()), layout)
            self.assertEqual(len(app._sysfinder_tables), 2)
            self.assertIs(app.sysfinder_tree, app._sysfinder_tables['system_finder']['tree'])
            self.assertIsNotNone(app._cv_trees['system_finder_traders'])
            self.assertEqual(app.sysfinder_allegiance.get(), translate(language)('system_finder.options.any'))
            self.assertEqual(app._sysfinder_option_value(app.sysfinder_trader_type.get()), 'Encoded')
        finally:
            for callback in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', callback)
            root.destroy()

    def test_modes_localization_scale_sorting_and_persistence(self):
        for language in ('en', 'de'):
            for scale in (1, 1.5, 2):
                with self.subTest(language=language, scale=scale):
                    self.check_table(language, scale)

    def check_table(self, language, scale):
        root = tk.Tk()
        root.geometry('650x300+-3000+-3000')
        container = ttk.Frame(root)
        container.pack(fill='both', expand=True)
        get = translate(language)
        config = {}
        visible = {'system_finder': {'security': False}}
        orders = {'system_finder_traders': ['ls', 'system', 'station']}
        def make():
            app = App()
            app._scaled_font = lambda size, weight='normal': ('Arial', round(size * scale), weight)
            app._scaled_px = lambda value: round(value * scale)
            app._sysfinder_tables = {}
            app._show_sysfinder_context_menu = Mock()
            app._sysfinder_on_double_click = Mock()
            app.sysfinder_results_title = ttk.Label(container)
            app.sysfinder_status_label = ttk.Label(container)
            app._sysfinder_columns_buttons = {key: ttk.Button(container) for key in ('system_finder', 'system_finder_traders')}
            app._create_sysfinder_results_table(container)
            app._create_sysfinder_results_table(container, trader=True)
            return app
        try:
            with patch.dict(Methods._create_sysfinder_results_table.__globals__, t=get), \
                    patch('config.load_theme', return_value='dark_gray'), \
                    patch('config._load_cfg', return_value=config), \
                    patch('config.update_config_value', side_effect=lambda key, value: config.update({key: value})), \
                    patch('config.load_column_visibility', side_effect=lambda key: visible.get(key, {})), \
                    patch('config.load_column_order', side_effect=lambda key: orders.get(key, [])), \
                    patch('config.save_column_visibility', side_effect=lambda key, value: visible.update({key: value.copy()})), \
                    patch('config.save_column_order', side_effect=lambda key, value: orders.update({key: value.copy()})):
                app = make()
                app._sysfinder_show_results('system_finder')
                systems = app.sysfinder_tree
                self.assertNotIn('security', systems['displaycolumns'])
                systems.column('system', width=1400)
                rows = [(('Sol', '0', 'High', '-', 'Normal', '1M', '-', '-'), 'oddrow', {'distance': 0, 'population': 1000001})]
                app._sysfinder_search_complete(rows)
                root.update()
                self.assertEqual(systems.column('system', 'width'), 1400)
                systems.event_generate('<ButtonRelease-1>', x=5, y=5)
                root.update()
                trader_rows = []
                for i in range(30):
                    arrival = None if i == 29 else i + 0.9
                    trader_rows.append(((f'System {i}', '0.0', 'Station', 'Outpost', 'M', '-' if arrival is None else str(int(arrival)), get('common.no')), 'oddrow', {'distance': i * 0.001, 'ls': arrival}))
                app._sysfinder_trader_complete(trader_rows)
                root.update()
                traders = app.sysfinder_tree
                self.assertIn('station', traders['displaycolumns'])
                self.assertNotIn('powerplay', traders['columns'])
                self.assertEqual(traders['displaycolumns'][:3], ('ls', 'system', 'station'))
                self.assertEqual(traders.heading('planetary', 'text'), get('system_finder.col_planetary'))
                app._fetch_sysfinder_pp_complete('Sol', dict(controlling_power='~none~', power_state='Expansion'), quiet=True)
                self.assertEqual(systems.set(systems.get_children()[0], 'powerplay'), 'Expansion')
                self.assertEqual(len(traders.get_children()), 30)
                for _ in range(2):
                    app._sort_sysfinder_column('ls', True)
                    self.assertEqual(traders.set(traders.get_children()[-1], 'system'), 'System 29')
                app._sort_sysfinder_column('distance', True)
                self.assertEqual(traders.set(traders.get_children()[0], 'system'), 'System 0')
                app._sort_sysfinder_column('distance', True)
                self.assertEqual(traders.set(traders.get_children()[0], 'system'), 'System 29')
                app._cv_toggle('station', 'system_finder_traders')
                self.assertNotIn('station', traders['displaycolumns'])
                app._cv_toggle('station', 'system_finder_traders')
                self.assertIn('station', traders['displaycolumns'])
                traders.column('station', width=1500)
                traders.xview_moveto(1)
                traders.yview_moveto(1)
                root.update()
                self.assertGreater(traders.xview()[0], 0)
                self.assertGreater(traders.yview()[0], 0)
                traders.event_generate('<ButtonRelease-1>', x=5, y=5)
                root.update()
                app._sysfinder_show_results('system_finder')
                root.geometry('900x450+-3000+-3000')
                root.update()
                self.assertEqual(systems.column('system', 'width'), 1400)
                for data in app._sysfinder_tables.values():
                    tree = data['tree']
                    for col in tree['columns']:
                        if col == '_spacer':
                            continue
                        self.assertFalse(tree.column(col, 'stretch'))
                        self.assertEqual(str(tree.column(col, 'anchor')), 'w')
                        self.assertGreaterEqual(tree.column(col, 'width'), tree.column(col, 'minwidth'))
                restored = make()
                self.assertEqual(restored._sysfinder_tables['system_finder']['tree'].column('system', 'width'), 1400)
                self.assertEqual(restored._sysfinder_tables['system_finder_traders']['tree'].column('station', 'width'), 1500)
                self.assertNotIn('security', restored._sysfinder_tables['system_finder']['tree']['displaycolumns'])
                config['system_finder_column_widths']['distance'] = 1
                minimum = make()._sysfinder_tables['system_finder']['tree']
                self.assertGreaterEqual(minimum.column('distance', 'width'), minimum.column('distance', 'minwidth'))
        finally:
            for callback in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', callback)
            root.destroy()


if __name__ == '__main__':
    unittest.main()
