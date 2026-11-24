import ast
import json
from contextlib import ExitStack
from concurrent.futures import Future
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from marketplace_api import MarketplaceAPI, _short_cache, _short_cache_key_locks, _short_cached
from system_finder_api import SystemFinderAPI
from commodity_market_tab import CommodityMarketTabMixin
from ui.search_control import SearchControl
from check_ring_finder_search import load_methods


class Widget:
    def __init__(self, text='Search'):
        self.options = dict(text=text, state='normal')
        self.exists = True
        self.pending = []

    def config(self, **kwargs):
        self.options.update(kwargs)

    def cget(self, key):
        return self.options[key]

    def winfo_exists(self):
        return self.exists

    def after(self, delay, callback, *args):
        self.pending.append((callback, args))

    def flush(self):
        while self.pending:
            callback, args = self.pending.pop(0)
            callback(*args)


class ImmediateThread:
    def __init__(self, target, args=(), **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


class InlinePool:
    def __init__(self, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def map(self, callback, items):
        return map(callback, items)

    def submit(self, callback, *args):
        future = Future()
        future.set_result(callback(*args))
        return future


class SearchControlTests(unittest.TestCase):
    def setUp(self):
        self.parent, self.button, self.status = Widget(), Widget('Find'), Widget('Previous results')
        self.control = SearchControl(self.parent, self.button, self.status)
        self.translations = patch('ui.search_control.t', lambda key: key)
        self.translations.start()
        self.addCleanup(self.translations.stop)

    def test_stop_waits_for_worker_then_shows_partial_results(self):
        c = self.control
        c.start()
        self.assertEqual(self.button.cget('text'), 'ring_finder.stop')
        c.stop()
        self.assertTrue(c.running)
        self.assertEqual(self.button.cget('state'), 'disabled')
        callback = Mock()
        c.progress('Old progress')
        c.complete([1, 2], callback)
        self.parent.flush()
        callback.assert_called_once_with([1, 2])
        self.assertFalse(c.running)
        self.assertEqual(self.button.cget('text'), 'Find')
        self.assertEqual(self.button.cget('state'), 'normal')
        self.assertEqual(self.status.cget('text'), 'ring_finder.search_stopped')

    def test_stop_before_results_keeps_previous_rows(self):
        c = self.control
        c.start()
        c.stop()
        callback = Mock()
        c.complete([], callback)
        self.parent.flush()
        callback.assert_not_called()

    def test_error_and_empty_success_restore_button(self):
        c = self.control
        on_finish = c.on_finish = Mock()
        c.start()
        c.failed('Unavailable')
        self.parent.flush()
        self.assertFalse(c.running)
        on_finish.assert_called_once()
        c.start()
        callback = Mock()
        c.complete([], callback)
        self.parent.flush()
        callback.assert_called_once_with([])

    def test_old_callbacks_cannot_affect_next_search(self):
        c = self.control
        c.start()
        generation = c._generation
        c.complete([], Mock())
        self.parent.flush()
        c.start()
        self.status.config(text='New search')
        callback = Mock()
        c._finish(generation, [1], callback, ())
        c._progress(generation, 'Old progress')
        self.assertEqual(self.status.cget('text'), 'New search')
        callback.assert_not_called()
        self.assertTrue(c.running)

    def test_closed_dialog_never_renders(self):
        c = self.control
        c.start()
        c.stop()
        self.button.exists = False
        callback = Mock()
        c.complete([1], callback)
        self.parent.flush()
        callback.assert_not_called()


class BackendStopTests(unittest.TestCase):
    def setUp(self):
        _short_cache.clear()
        _short_cache_key_locks.clear()

    def test_stopped_searches_do_not_start_requests(self):
        with patch('requests.get') as get, patch('requests.post') as post:
            for api in (MarketplaceAPI.search_buyers, MarketplaceAPI.search_sellers):
                self.assertEqual(api('Platinum', 'Sol', is_cancelled=lambda: True), [])
            for api in (MarketplaceAPI.search_buyers_galaxy_wide, MarketplaceAPI.search_sellers_galaxy_wide):
                self.assertEqual(api('Platinum', is_cancelled=lambda: True), [])
            self.assertEqual(SystemFinderAPI.search_systems('Sol', is_cancelled=lambda: True), [])
            self.assertEqual(SystemFinderAPI.search_material_traders('Sol', 'Raw', is_cancelled=lambda: True), [])
            get.assert_not_called()
            post.assert_not_called()

    def test_edsm_fill_sends_no_request_after_stop(self):
        from edsm_integration import EDSMIntegration
        edsm = EDSMIntegration(':memory:')
        cancel = threading.Event()

        def answer_then_stop(name):
            cancel.set()
            return None, True
        edsm._fetch_edsm_bodies = Mock(side_effect=answer_then_stop)
        stats = edsm.fill_missing_metadata_for_systems_direct(['A', 'B'], is_cancelled=cancel.is_set)
        edsm._fetch_edsm_bodies.assert_called_once_with('A')
        self.assertEqual(stats['no_data_systems'], ['A'])
        with patch('requests.get') as get:
            EDSMIntegration(':memory:').fill_missing_metadata_for_systems_direct(['C'], is_cancelled=lambda: True)
            get.assert_not_called()

    def test_edsm_errors_are_not_reported_as_missing_data(self):
        from edsm_integration import EDSMIntegration
        edsm = EDSMIntegration(':memory:')
        edsm._fetch_edsm_bodies = Mock(side_effect=[(None, False), ({'bodies': []}, True)])
        edsm._get_rings_needing_metadata_in_system = Mock(return_value=[])
        stats = edsm.fill_missing_metadata_for_systems_direct(['Timed out', 'Nothing to fill'])
        self.assertEqual(stats['no_data_systems'], ['Nothing to fill'])

    def test_stop_keeps_nearby_rows(self):
        for api in (MarketplaceAPI.search_buyers, MarketplaceAPI.search_sellers):
            with self.subTest(api=api.__name__), ExitStack() as stack:
                cancel = threading.Event()
                ardent = stack.enter_context(patch.object(MarketplaceAPI, '_fetch_ardent', return_value=[]))
                stack.enter_context(patch.object(MarketplaceAPI, '_fetch_spansh_nearby', return_value=[]))
                stack.enter_context(patch.object(MarketplaceAPI, '_fetch_spansh_carriers', return_value=[]))
                def eddn(*args, **kwargs):
                    cancel.set()
                    return [dict(systemName='Sol', marketId=1, sellPrice=123)]
                stack.enter_context(patch.object(MarketplaceAPI, '_fetch_eddn_cache', side_effect=eddn))
                stack.enter_context(patch.object(MarketplaceAPI, '_backfill_eddn_cache'))
                rows = api('Platinum', 'Sol', is_cancelled=cancel.is_set)
                self.assertEqual(len(rows), 1)
                self.assertTrue(any('nearby' in c.args[0] for c in ardent.call_args_list))

    def test_cancelled_partial_page_results_are_not_cached(self):
        cancel = threading.Event()
        def partial():
            cancel.set()
            return [1]
        self.assertEqual(_short_cached(('partial',), partial, cancel.is_set), [1])
        self.assertNotIn(('partial',), _short_cache)
        self.assertEqual(_short_cached(('partial',), lambda: [1, 2]), [1, 2])

    def test_cancellation_after_system_request_skips_enrichment(self):
        cancel = threading.Event()
        response = Mock()
        def data():
            cancel.set()
            return dict(results=[dict(name='Sol')])
        response.json.side_effect = data
        with patch('requests.post', return_value=response) as post, \
                patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value={}), \
                patch.object(SystemFinderAPI, '_convert_spansh_system', return_value={'systemName': 'Sol'}):
            rows = SystemFinderAPI.search_systems('Sol', is_cancelled=cancel.is_set)
        self.assertEqual(rows, [{'systemName': 'Sol'}])
        self.assertEqual(post.call_count, 1)


App = type('App', (
    load_methods('app/commodity_market_tab.py', 'CommodityMarketTabMixin', {
        '_search_marketplace', '_search_trade_market',
        '_display_marketplace_search_results', '_display_trade_search_results',
        '_galaxy_market_limit', '_next_commodity_pp_generation',
        '_found_stations_text',
    }),
    load_methods('app/main.py', 'App', {'_search_systems', '_search_material_traders'}),
), {})
for _method in (App._search_marketplace, App._search_systems):
    _method.__globals__.update(SearchControl=SearchControl, MarketplaceAPI=MarketplaceAPI,
                               threading=threading, log=Mock())


class SearchScreenTests(unittest.TestCase):
    def test_marketplace_renderer_receives_enrichment_setting(self):
        app = CommodityMarketTabMixin()
        app._clear_marketplace_results = Mock()
        app.marketplace_buy_mode = SimpleNamespace(get=lambda: False)
        app.marketplace_commodity = SimpleNamespace(get=lambda: 'Platinum')
        app.marketplace_tree = MagicMock()
        app.marketplace_tree.get_children.return_value = ()
        app.marketplace_total_label = Widget()
        app._backfill_commodity_pp_worker = Mock()
        rows = [dict(systemName='Sol', stationName='MMC0', sellPrice=123, demand=10, distance=1)]
        with patch.dict('carrier_names._names', {'MMC0': 'Squad Ship'}), \
                patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value={}), \
                patch('threading.Thread', ImmediateThread):
            app._display_marketplace_results(rows, enrich_powerplay=False)
            app.marketplace_tree.insert.assert_called_once()
            values = app.marketplace_tree.insert.call_args.kwargs['values']
            self.assertEqual(values[1].strip(), 'Squad Ship (MMC0)')
            app.marketplace_tree.item.return_value = values
            item = app.marketplace_tree.insert.return_value
            self.assertEqual(app._row_system_station(app.marketplace_tree, item), ('Sol', 'MMC0'))
            app._backfill_commodity_pp_worker.assert_not_called()
            app._display_marketplace_results(rows, enrich_powerplay=True)
            app._backfill_commodity_pp_worker.assert_called_once()

    def test_market_and_trade_searches_keep_partial_results(self):
        for trade in (False, True):
            with self.subTest(trade=trade):
                app = App()
                app.after = Widget().after
                parent = app.after.__self__
                prefix = 'trade' if trade else 'marketplace'
                for key, value in dict(commodity='Platinum', search_mode='near_system', reference_system='Sol',
                                       max_age='7 days', buy_mode=False, sell_mode=True, exclude_carriers=False,
                                       station_type='All', large_pad_only=False, order_by='Best price').items():
                    setattr(app, prefix + '_' + key, SimpleNamespace(get=lambda value=value: value))
                setattr(app, prefix + '_search_btn', Widget())
                setattr(app, prefix + '_total_label', Widget())
                setattr(app, prefix + '_tree', Mock())
                for key in ('commodity', 'age', 'station_type', 'sort'):
                    setattr(app, '_' + ('trade_' if trade and key != 'commodity' else '') + key + '_rev_map', {})
                app._convert_age_to_days = lambda value: 7
                app._filter_results_by_age = lambda rows, age: rows
                setattr(app, '_save_' + prefix + '_preferences', Mock())
                display = Mock()
                setattr(app, '_display_' + prefix + '_search_results', display)
                def fetch(*args, **kwargs):
                    control = getattr(app, '_' + prefix + '_search_control')
                    control.stop()
                    self.assertTrue(kwargs['is_cancelled']())
                    return [dict(systemName='Sol', demand=10, sellPrice=123)]
                with patch.object(MarketplaceAPI, 'search_buyers', side_effect=fetch), \
                        patch('threading.Thread', ImmediateThread):
                    (app._search_trade_market if trade else app._search_marketplace)()
                parent.flush()
                self.assertEqual(display.call_args.args[0][0]['systemName'], 'Sol')
                self.assertFalse(getattr(app, '_' + prefix + '_search_control').running)

    def test_stopped_market_results_never_start_more_enrichment(self):
        for prefix in ('trade', 'marketplace'):
            with self.subTest(prefix=prefix):
                app = App()
                app.config = Mock()
                control = SearchControl(Widget(), Widget(), Widget())
                control.start()
                control.stop()
                setattr(app, '_' + prefix + '_search_control', control)
                setattr(app, prefix + '_total_label', Widget())
                render = Mock()
                setattr(app, '_display_' + prefix + '_results', render)
                rows = [dict(systemName='Sol')]
                if prefix == 'trade':
                    app._display_trade_search_results(rows, 'galaxy_wide', False, 1)
                else:
                    app._display_marketplace_search_results(rows, 'galaxy_wide', 'Sol', False, False, 1)
                self.assertFalse(render.call_args.kwargs['enrich_powerplay'])

    def test_enter_in_system_search_stops_active_trader_search(self):
        app = App()
        control = SearchControl(Widget(), Widget(), Widget())
        control.start()
        app._traders_search_control = control
        app._search_systems()
        self.assertTrue(control.is_cancelled())


class TkWidgetTests(unittest.TestCase):
    def test_stop_labels_with_real_tk_ttk_and_modern_buttons(self):
        import tkinter as tk
        from tkinter import ttk
        from ui.modern_widgets import ModernButton
        root = tk.Tk()
        root.withdraw()
        try:
            for language in ('en', 'de'):
                strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
                def translate(key):
                    section, item = key.split('.')
                    return strings[section][item]
                for button_class in (tk.Button, ttk.Button, ModernButton):
                    with self.subTest(language=language, button=button_class.__name__), \
                            patch('ui.search_control.t', translate):
                        button = button_class(root, text=strings['common']['search'])
                        label = tk.Label(root)
                        control = SearchControl(root, button, label)
                        control.start()
                        self.assertEqual(button.cget('text'), strings['ring_finder']['stop'])
                        control.stop()
                        self.assertEqual(button.cget('text'), strings['common']['stopping'])
                        control.complete([], Mock())
                        root.update()
                        self.assertEqual(button.cget('text'), strings['common']['search'])
                        button.destroy()
                        label.destroy()
        finally:
            root.destroy()


class RemainingWorkerTests(unittest.TestCase):
    def make_control(self):
        parent = Widget()
        control = SearchControl(parent, Widget(), Widget())
        control.start()
        return parent, control

    def test_multi_mineral_stop_skips_queued_minerals(self):
        cls = load_methods('app/multi_mineral_tab.py', 'MultiMineralTab', {'_worker'})
        cls._worker.__globals__.update(MarketplaceAPI=MarketplaceAPI, ThreadPoolExecutor=InlinePool)
        tab = cls()
        parent, tab._search_control = self.make_control()
        tab._group = lambda raw, *args: [(name, rows) for name, rows in raw if rows]
        tab._complete = Mock()
        def fetch(*args, **kwargs):
            tab._search_control.stop()
            return [dict(sellPrice=123)]
        with patch.object(MarketplaceAPI, 'search_buyers', side_effect=fetch) as buyers:
            tab._worker(['Platinum', 'Painite', 'Osmium'], 'Sol', 'All', '7 days', False, False)
        parent.flush()
        self.assertEqual(buyers.call_count, 1)
        self.assertEqual(len(tab._complete.call_args.args[0]), 1)

    def test_sell_hold_stop_keeps_completed_prices(self):
        cls = load_methods('app/cargo_sell_planner.py', 'CargoSellPlanner', {'_worker'})
        cls._worker.__globals__.update(MarketplaceAPI=MarketplaceAPI, ThreadPoolExecutor=InlinePool,
                                      build_plans=lambda cargo, markets, **kwargs: [item for item in markets if item[1]])
        tab = cls()
        parent, tab._search_control = self.make_control()
        tab.app = SimpleNamespace(multi_mineral_tab=SimpleNamespace(_filter=lambda rows, *args: rows))
        tab._complete = Mock()
        def fetch(*args, **kwargs):
            tab._search_control.stop()
            return [dict(sellPrice=123, demand=10, distance=1)]
        with patch.object(MarketplaceAPI, 'search_buyers', side_effect=fetch) as buyers:
            tab._worker(('Sol', {'Platinum': 10, 'Painite': 10}, {}), (50, '7 days', False, False))
        parent.flush()
        self.assertEqual(buyers.call_count, 1)
        self.assertEqual(len(tab._complete.call_args.args[1]), 1)

    def test_best_mining_search_stop_keeps_partial_prices(self):
        cls = load_methods('app/best_mining_view.py', 'BestMiningMixin', {'_reverse_search_worker'})
        finder = cls()
        finder.BM_MAX_CANDIDATES = 20
        parent, control = self.make_control()
        finder._get_hotspots = Mock(return_value=[dict(systemName='Mining', type='Platinum', distance=1)])
        finder._parse_materials_from_hotspots = lambda value: ['Platinum', 'Painite']
        finder._expand_abbreviated_materials = lambda value: value
        finder._bm_show_results = Mock()
        local_db = Mock()
        local_db.LocalSystemsDatabase.return_value.is_database_available.return_value = False
        def fetch(*args, **kwargs):
            control.stop()
            return [dict(sellPrice=123)]
        with patch.object(MarketplaceAPI, 'search_buyers', side_effect=fetch) as buyers, \
                patch('concurrent.futures.ThreadPoolExecutor', InlinePool), \
                patch.dict(sys.modules, local_database=local_db):
            finder._reverse_search_worker('Sol', 50, 50, None, control)
        parent.flush()
        self.assertEqual(buyers.call_count, 1)
        self.assertEqual(sum(bool(rows) for rows in finder._bm_show_results.call_args.args[0]['rows_by_material'].values()), 1)

    def test_acquisition_stop_skips_price_searches(self):
        cls = load_methods('app/acquisition_view.py', 'AcquisitionMixin', {'_acquisition_search_worker', '_acq_find_sell_targets',
                                                                         '_acq_drop_no_longer_unoccupied'})
        finder = cls()
        finder.ACQUISITION_RADIUS_BY_STATE = {'Fortified': 20}
        parent, control = self.make_control()
        render = finder._show_acquisition_search_results = Mock()
        def nearby(*args, **kwargs):
            self.assertIn('is_cancelled', kwargs)
            control.stop()
            return {'Target': {'distance': 1}}
        with patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value={'Sol': {'power_state': 'Fortified'}}), \
                patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_systems', side_effect=nearby), \
                patch.object(SystemFinderAPI, '_store_powerplay_batch'), \
                patch.object(MarketplaceAPI, 'search_buyers') as buyers:
            finder._acquisition_search_worker('Sol', 'Platinum', control)
        parent.flush()
        buyers.assert_not_called()
        render.assert_not_called()


class PowerPlayBackfillTests(unittest.TestCase):
    def setUp(self):
        SystemFinderAPI._pp_backfill_cache.clear()
        self.addCleanup(SystemFinderAPI._pp_backfill_cache.clear)
        self.calls = []

    def answer(self, *args, **kwargs):
        state = args[3]
        self.calls.append((args[0], args[1], state))
        return {f'{state} system': dict(power_state=state)}, True

    def backfill(self, reference='Sol', distance=50, **kwargs):
        return SystemFinderAPI._fetch_spansh_powerplay_backfill(reference, distance, **kwargs)

    def test_all_states_are_requested_at_the_same_time(self):
        barrier = threading.Barrier(len(SystemFinderAPI.SPANSH_BACKED_PP_STATES), timeout=5)
        def answer(*args, **kwargs):
            barrier.wait()
            return self.answer(*args, **kwargs)
        with patch.object(SystemFinderAPI, '_query_spansh_powerplay_systems', side_effect=answer):
            merged = self.backfill()
        self.assertEqual(set(merged), {f'{state} system' for state in SystemFinderAPI.SPANSH_BACKED_PP_STATES})

    def test_repeat_search_reuses_the_answer_until_it_expires(self):
        with patch.object(SystemFinderAPI, '_query_spansh_powerplay_systems', side_effect=self.answer):
            first = self.backfill()
            first.clear()
            self.assertEqual(len(self.backfill('sol')), 4)
            self.assertEqual(len(self.calls), 4)
            self.backfill(distance=100)
            self.assertEqual(len(self.calls), 8)
            with patch('time.monotonic', return_value=10 ** 9):
                self.backfill()
            self.assertEqual(len(self.calls), 12)

    def test_failed_or_cancelled_answers_are_not_reused(self):
        def one_fails(*args, **kwargs):
            systems, answered = self.answer(*args, **kwargs)
            return (systems, answered) if args[3] != 'Fortified' else ({}, False)
        with patch.object(SystemFinderAPI, '_query_spansh_powerplay_systems', side_effect=one_fails):
            self.assertEqual(len(self.backfill()), 3)
            self.backfill()
        self.assertEqual(len(self.calls), 8)

    def test_stop_before_the_requests_sends_nothing(self):
        with patch.object(SystemFinderAPI, '_query_spansh_powerplay_systems', side_effect=self.answer):
            self.assertEqual(self.backfill(is_cancelled=lambda: True), {})
        self.assertEqual(self.calls, [])

    def test_each_request_checks_stop_before_it_is_sent(self):
        checks = iter([False])  # Stop arrives right after the backfill starts
        with patch('requests.post') as post:
            self.backfill(is_cancelled=lambda: next(checks, True))
        self.assertEqual(post.call_count, 0)
        self.assertEqual(SystemFinderAPI._pp_backfill_cache, {})


class CommodityPowerplayFillInTests(unittest.TestCase):
    def setUp(self):
        cls = load_methods('app/commodity_market_tab.py', 'CommodityMarketTabMixin', {
            '_next_commodity_pp_generation', '_commodity_pp_generation_current',
            '_start_commodity_pp_backfill', '_backfill_commodity_pp_worker',
            '_backfill_commodity_pp_complete'})
        cls._backfill_commodity_pp_worker.__globals__.update(threading=threading, log=Mock())
        self.app = cls()
        self.parent = Widget()
        self.app.after = self.parent.after
        self.tree = Mock()
        self.tree.__getitem__ = Mock(return_value=('system', 'station', 'powerstate'))
        self.tree.get_children.return_value = ('row',)
        self.tree.item.return_value = (' Sol ', ' Station ', ' ? ')
        self.entry = dict(controlling_power='Aisling Duval', power_state='Fortified', updated_at='2026-11-22')

    def run_fill_in(self, during_lookup=None):
        def lookup(names, is_cancelled=None):
            self.is_cancelled = is_cancelled
            if during_lookup:
                during_lookup()
            return {'Sol': dict(self.entry)}
        with patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_for_named_systems', side_effect=lookup),                 patch.object(SystemFinderAPI, '_spansh_pp_should_replace_cache', return_value=True),                 patch.object(SystemFinderAPI, '_store_powerplay_batch') as store,                 patch('threading.Thread', ImmediateThread):
            self.app._start_commodity_pp_backfill(self.tree, ['Sol'], {})
        self.parent.flush()
        return store

    def updated_rows(self):
        return [c for c in self.tree.item.call_args_list if 'values' in c.kwargs]

    def test_current_search_fills_the_powerplay_column(self):
        store = self.run_fill_in()
        store.assert_called_once()
        self.assertFalse(self.is_cancelled())
        self.assertEqual(len(self.updated_rows()), 1)

    def test_newer_search_stops_the_older_fill_in(self):
        store = self.run_fill_in(during_lookup=lambda: self.app._next_commodity_pp_generation(self.tree))
        self.assertTrue(self.is_cancelled())
        store.assert_called_once()  # answers already received are still kept for later searches
        self.assertEqual(self.updated_rows(), [])

    def test_other_table_search_does_not_stop_the_fill_in(self):
        self.run_fill_in(during_lookup=lambda: self.app._next_commodity_pp_generation(Mock()))
        self.assertEqual(len(self.updated_rows()), 1)


class NamedSystemPowerplayTests(unittest.TestCase):
    def setUp(self):
        SystemFinderAPI._named_pp_cache.clear()
        self.addCleanup(SystemFinderAPI._named_pp_cache.clear)
        self.asked = []
        self.fail = set()

    def post(self, url, json=None, **kwargs):
        name = json['reference_system']
        self.asked.append(name)
        if name in self.fail:
            raise OSError('offline')
        response = Mock()
        results = [dict(name=name, controlling_power='Aisling Duval', power_state='Fortified',
                        updated_at='2026-11-22')] if name == 'Sol' else []
        response.json.return_value = dict(results=results)
        return response

    def lookup(self, names, **kwargs):
        with patch('requests.post', side_effect=self.post), patch('time.sleep'):
            return SystemFinderAPI._fetch_spansh_powerplay_for_named_systems(names, **kwargs)

    def test_repeat_lookup_reuses_answers_until_they_expire(self):
        first = self.lookup(['Sol', 'Lave'])
        self.assertEqual(set(first), {'Sol'})
        self.assertEqual(self.lookup(['Sol', 'Lave']), first)
        self.assertEqual(self.asked, ['Sol', 'Lave'])
        with patch('time.monotonic', return_value=10 ** 9):
            self.lookup(['Sol'])
        self.assertEqual(self.asked, ['Sol', 'Lave', 'Sol'])

    def test_failed_requests_are_retried(self):
        self.fail = {'Sol'}
        self.assertEqual(self.lookup(['Sol']), {})
        self.fail = set()
        self.assertEqual(set(self.lookup(['Sol'])), {'Sol'})
        self.assertEqual(self.asked, ['Sol', 'Sol'])

    def test_stop_skips_the_remaining_systems(self):
        checks = iter([False])
        self.lookup(['Sol', 'Lave'], is_cancelled=lambda: next(checks, True))
        self.assertEqual(self.asked, ['Sol'])


class SyntaxTests(unittest.TestCase):
    def test_changed_modules_parse(self):
        for name in ('main.py', 'commodity_market_tab.py', 'ring_finder.py', 'ring_finder_search.py', 'marketplace_api.py', 'system_finder_api.py',
                     'edsm_integration.py', 'multi_mineral_tab.py', 'cargo_sell_planner.py', 'ui/search_control.py'):
            with self.subTest(name=name):
                ast.parse((ROOT / 'app' / name).read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    unittest.main()
