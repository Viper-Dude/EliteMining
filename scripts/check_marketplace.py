import json
import math
import random
import sys
import threading
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from localization import t
from app_utils import format_market_pad, format_market_powerplay, format_market_source, format_market_station_type
from cargo_sell_planner import build_plans
from column_visibility_helper import ColumnVisibilityMixin, displayed_column
from marketplace_api import MarketplaceAPI, _short_cache, _short_cache_key_locks, _system_coords_cache
from multi_mineral_tab import MultiMineralTab
from check_search_stop import App, ImmediateThread, Widget
from check_ring_finder_search import load_methods


def market(index, **changes):
    return dict(dict(systemName='Sol', stationName=str(index), marketId=index,
                     sellPrice=100, buyPrice=50, demand=100, stock=20,
                     distance=10, stationType='Coriolis', maxLandingPadSize=3,
                     updatedAt=datetime.now(timezone.utc).isoformat()), **changes)


class MarketTests(unittest.TestCase):
    def test_distances_use_coordinates_from_other_local_market_records(self):
        import sqlite3
        from tempfile import TemporaryDirectory
        from contextlib import closing
        with TemporaryDirectory() as folder:
            db = str(Path(folder) / 'market.db')
            with closing(sqlite3.connect(db)) as conn, conn:
                conn.execute('CREATE TABLE commodity_prices_data (system_name, system_x, system_y, system_z, updated_at)')
                conn.execute('CREATE TABLE system_coords (name, x, y, z)')
                conn.execute("INSERT INTO commodity_prices_data VALUES ('Wolf 1143', 3, 4, 0, '2026-11-18')")
                conn.execute("INSERT INTO system_coords VALUES ('Other', 0, 0, 12)")
            rows = [market(1, systemName='Wolf 1143', distance=None),
                    market(2, systemName='Other', distance=None),
                    market(3, systemName='Unknown', distance=None)]
            with patch.object(MarketplaceAPI, 'EDDN_CACHE_PATH', db), \
                 patch.object(MarketplaceAPI, '_get_system_coords', side_effect=lambda name: (0, 0, 0) if name == 'Sol' else None), \
                 patch('local_database.LocalSystemsDatabase.is_database_available', return_value=False), \
                 patch('marketplace_api.requests.get', return_value=Mock(json=lambda: [])):
                measured = MarketplaceAPI.add_distances_to_results(rows, 'Sol')
            self.assertEqual([r['distance'] for r in measured], [5, 12, None])

    def test_distances_batch_missing_systems_and_reuse_coordinates(self):
        rows = [market(i, systemName=f'Remote {i // 2}', distance=None) for i in range(450)]
        response = Mock()
        def fetch(url, params, **kwargs):
            response = Mock(status_code=200)
            response.json.return_value = [dict(name=name.lower(), coords=dict(x=3, y=4, z=0))
                                          for key, name in params if key == 'systemName[]']
            return response
        with patch.dict(_system_coords_cache, {}, clear=True), \
             patch.object(MarketplaceAPI, 'EDDN_CACHE_PATH', None), \
             patch('local_database.LocalSystemsDatabase.is_database_available', return_value=False), \
             patch.object(MarketplaceAPI, '_get_system_coords', return_value=(0, 0, 0)), \
             patch('marketplace_api.requests.get', side_effect=fetch) as lookup, \
             patch('marketplace_api._time_mod.sleep'):
            measured = MarketplaceAPI.add_distances_to_results(rows, 'Sol')
            self.assertEqual([r['distance'] for r in measured], [5] * 450)
            self.assertEqual(lookup.call_count, 3)
            fresh = [market(1, systemName='Remote 0', distance=None)]
            self.assertEqual(MarketplaceAPI.add_distances_to_results(fresh, 'Sol')[0]['distance'], 5)
            self.assertEqual(lookup.call_count, 3)

    def test_distance_rate_limit_retries_same_batch_and_can_stop(self):
        for stop in (False, True):
            with self.subTest(stop=stop):
                cancelled = [False]
                limited = Mock(status_code=429, headers={'Retry-After': '2'})
                success = Mock(status_code=200)
                success.json.return_value = [dict(name='Remote', coords=dict(x=3, y=4, z=0))]
                def pause(seconds):
                    cancelled[0] = stop
                with patch.dict(_system_coords_cache, {}, clear=True), \
                     patch.object(MarketplaceAPI, 'EDDN_CACHE_PATH', None), \
                     patch('local_database.LocalSystemsDatabase.is_database_available', return_value=False), \
                     patch.object(MarketplaceAPI, '_get_system_coords', return_value=(0, 0, 0)), \
                     patch('marketplace_api.requests.get', side_effect=[limited, success]) as lookup, \
                     patch('marketplace_api._time_mod.sleep', side_effect=pause) as sleep:
                    rows = [market(1, systemName='Remote', distance=None)]
                    measured = MarketplaceAPI.add_distances_to_results(rows, 'Sol', lambda: cancelled[0])
                    self.assertEqual(measured[0]['distance'], None if stop else 5)
                    self.assertEqual(lookup.call_count, 1 if stop else 2)
                    if not stop:
                        self.assertEqual(lookup.call_args_list[0], lookup.call_args_list[1])
                        self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list), 2)

    def test_merge_missing_invalid_and_mixed_timezones(self):
        for stamp in ('', None, 'invalid', '2026-11-14T12:00:00', '2026-11-15T13:00:00+02:00'):
            for reverse in (False, True):
                with self.subTest(stamp=stamp, reverse=reverse):
                    rows = [market(1, updatedAt=stamp, sellPrice=1),
                            market(1, updatedAt='2026-11-15T12:00:00Z', sellPrice=2)]
                    merged = MarketplaceAPI._merge_by_freshness(rows[::-1] if reverse else rows)
                    self.assertEqual(merged[0]['sellPrice'], 2)

    def test_buy_price_and_supply_use_displayed_fields(self):
        rows = [market(1, buyPrice=100, sellPrice=1, stock=3, demand=90),
                market(2, buyPrice=50, sellPrice=100, stock=20, demand=1)]
        for order in ('Best price (lowest)', 'Best supply', 'Best stock'):
            self.assertEqual(MarketplaceAPI.sort_results(rows, order, True)[0]['marketId'], 2)
        self.assertEqual(MarketplaceAPI.sort_results(rows, 'Best demand')[0]['marketId'], 1)
        self.assertEqual(MarketplaceAPI.sort_results(rows, 'Best price (highest)')[0]['marketId'], 2)

    def test_shared_filters_and_unknown_distances(self):
        rows = [market(1), market(2, stationType='FleetCarrier'), market(3, stationType='PlanetaryConstructionDepot'),
                market(4, stationType='SpaceConstructionDepot'), market(5, sellPrice=0),
                market(6, maxLandingPadSize=2), market(7, demand=0)]
        filtered = MarketplaceAPI.filter_results(rows, 'Orbital', 'Any', True, True)
        self.assertEqual([r['marketId'] for r in filtered], [1, 4])
        carriers = MarketplaceAPI.filter_results(rows, 'Fleet Carrier', exclude_carriers=True)
        self.assertEqual([r['marketId'] for r in carriers], [2])
        self.assertEqual([r['marketId'] for r in MarketplaceAPI.sort_results(
            [market(1, distance=None), market(2, distance=0), market(3, distance=1)], 'Distance')], [2, 3, 1])

    def test_age_filter_accepts_utc_naive_and_offset_dates(self):
        now = datetime.now(timezone.utc)
        rows = [market(1, updatedAt=now.isoformat()), market(2, updatedAt=now.replace(tzinfo=None).isoformat()),
                market(3, updatedAt=(now - timedelta(hours=4)).isoformat()), market(4, updatedAt=None)]
        self.assertEqual([r['marketId'] for r in MarketplaceAPI.filter_results(rows, max_age='1 hour')], [1, 2])

    def test_radius_reaches_all_sources_and_filters_returned_rows(self):
        for search in (MarketplaceAPI.search_buyers, MarketplaceAPI.search_sellers):
            with self.subTest(search=search.__name__), ExitStack() as stack:
                _short_cache.clear()
                _short_cache_key_locks.clear()
                ardent = stack.enter_context(patch.object(MarketplaceAPI, '_fetch_ardent',
                    side_effect=lambda path, *args, **kwargs: [market(1, distance=40), market(2, distance=80)] if 'nearby' in path else []))
                sources = [stack.enter_context(patch.object(MarketplaceAPI, name, return_value=[]))
                           for name in ('_fetch_spansh_nearby', '_fetch_spansh_carriers', '_fetch_eddn_cache')]
                stack.enter_context(patch.object(MarketplaceAPI, '_backfill_eddn_cache'))
                self.assertEqual([r['marketId'] for r in search('Platinum', 'Sol', 50)], [1])
                nearby = [c for c in ardent.call_args_list if 'nearby' in c.args[0]]
                self.assertEqual(nearby[0].args[1]['maxDistance'], 50)
                for source in sources:
                    self.assertEqual(source.call_args.args[3], 50)

    def test_spansh_nearby_filters_commodity_and_radius_around_the_reference_system(self):
        now = datetime.now(timezone.utc).isoformat()
        station = dict(market_id=7, system_name='Near', name='Port', type='Coriolis Starport',
                       system_x=10, system_y=0, system_z=0, market_updated_at=now, has_large_pad=True,
                       market=[dict(commodity='Low Temperature Diamonds', sell_price=900, demand=5)])
        response = Mock(json=Mock(return_value={'results': [station]}), raise_for_status=Mock())
        _short_cache.clear()
        _short_cache_key_locks.clear()
        with patch('marketplace_api.tracked_request', return_value=response) as request,                 patch.object(MarketplaceAPI, '_get_system_coords', side_effect=lambda name: (0, 0, 0) if name == 'Sol' else (5, 0, 0)):
            rows = MarketplaceAPI._fetch_spansh_nearby('lowtemperaturediamond', 'Sol', 'buying_commodities', 50, 1)
            body = request.call_args.kwargs['json']
            self.assertEqual(body['filters']['market'][0]['name'], 'Low Temperature Diamonds')
            self.assertIn('demand', body['filters']['market'][0])
            self.assertEqual(body['filters']['distance'], {'min': 0, 'max': 50})
            self.assertEqual(body['reference_coords'], {'x': 0, 'y': 0, 'z': 0})
            self.assertNotIn('buying_commodities', body['filters'])
            self.assertEqual([(r['marketId'], r['distance'], r['sellPrice']) for r in rows], [(7, 10, 900)])
            calls = request.call_count
            MarketplaceAPI._fetch_spansh_nearby('lowtemperaturediamond', 'Sol', 'buying_commodities', 50, 1)
            self.assertEqual(request.call_count, calls)
            MarketplaceAPI._fetch_spansh_nearby('lowtemperaturediamond', 'Other', 'buying_commodities', 50, 1)
            self.assertEqual(request.call_count, calls * 2)
            MarketplaceAPI._fetch_spansh_nearby('gold', 'Sol', 'selling_commodities', 50, 1)
            self.assertIn('supply', request.call_args.kwargs['json']['filters']['market'][0])
        _short_cache.clear()
        _short_cache_key_locks.clear()

    def test_distance_calculation_reuses_coordinate_lookup_and_preserves_zero(self):
        rows = [market(1, systemX=0, systemY=0, systemZ=0),
                market(2, systemName='Other system', systemX=3, systemY=4, systemZ=0)]
        with patch.object(MarketplaceAPI, '_get_system_coords', return_value=(0, 0, 0)) as coords:
            result = MarketplaceAPI.add_distances_to_results(rows, 'Sol')
        coords.assert_called_once_with('Sol')
        self.assertEqual([r['distance'] for r in result], [0, 5])

    def test_display_helpers_handle_missing_data_and_no_controller(self):
        self.assertEqual([format_market_pad(x) for x in (None, 0, 1, 2, 3, 'l')], ['?', '?', 'S', 'M', 'L', 'L'])
        self.assertEqual(format_market_powerplay(dict(controlling_power='~none~', power_state='Expansion')), 'Expansion')
        self.assertEqual(format_market_powerplay(dict(power_state='Unoccupied')), 'Unoccupied')
        self.assertEqual(format_market_station_type('PlanetaryConstructionDepot'), 'Surface/Station')
        self.assertEqual(format_market_station_type('SpaceConstructionDepot'), 'Orbital/Station')

    def test_merge_recovers_coordinates_only_for_the_same_system(self):
        for moved in (False, True):
            for reverse in (False, True):
                with self.subTest(moved=moved, reverse=reverse):
                    older = market(1, systemName='Previous' if moved else 'Sol',
                                   systemX=1, systemY=2, systemZ=3, updatedAt='2026-11-14T00:00:00Z')
                    newer = market(1, systemName='Sol', systemX=None, systemY=None, systemZ=None,
                                   updatedAt='2026-11-15T00:00:00Z', buyPrice=678531)
                    rows = [older, newer] if not reverse else [newer, older]
                    result = MarketplaceAPI._merge_by_freshness(rows)[0]
                    self.assertEqual(result['buyPrice'], 678531)
                    expected = [None, None, None] if moved else [1, 2, 3]
                    self.assertEqual([result[k] for k in ('systemX', 'systemY', 'systemZ')], expected)

    def test_reference_system_carrier_without_coordinates_is_zero_ly(self):
        rows = [market(1, systemName='wregoe md-k d8-19', systemX=None, systemY=None, systemZ=None,
                       distance=None, buyPrice=678531)]
        with patch.object(MarketplaceAPI, '_get_system_coords', return_value=(158.84375, 25.28125, -317)):
            result = MarketplaceAPI.add_distances_to_results(rows, 'Wregoe MD-K d8-19')
        self.assertEqual(result[0]['distance'], 0)
        self.assertEqual(result[0]['systemX'], 158.84375)

    def test_merge_keeps_source_of_the_newer_price_and_fills_station_type(self):
        older = market(1, _source='Ardent', stationType='Coriolis', updatedAt='2026-11-14T00:00:00Z')
        newer = market(1, _source='EDDN', _saved=True, stationType='', updatedAt='2026-11-15T00:00:00Z')
        for rows in ([older, newer], [newer, older]):
            result = MarketplaceAPI._merge_by_freshness(rows)[0]
            self.assertEqual(result['_source'], 'EDDN')
            self.assertEqual(result['stationType'], 'Coriolis')

    def test_equal_timestamps_prefer_the_live_lookup_over_the_saved_copy(self):
        stamp = '2026-11-15T00:00:00Z'
        saved = market(1, _source='Ardent', _saved=True, updatedAt=stamp)
        live = market(1, _source='Ardent', updatedAt=stamp)
        for rows in ([saved, live], [live, saved]):
            self.assertFalse(MarketplaceAPI._merge_by_freshness(rows)[0].get('_saved'))
        newer_saved = market(1, _source='EDDN', _saved=True, updatedAt='2026-11-16T00:00:00Z')
        self.assertTrue(MarketplaceAPI._merge_by_freshness([live, newer_saved])[0].get('_saved'))

    def test_source_label_for_live_saved_and_untagged_rows(self):
        self.assertEqual(format_market_source(market(1, _source='Spansh')), 'Spansh')
        self.assertEqual(format_market_source(market(1, _source='Ardent', _saved=True)), 'Ardent')
        self.assertEqual(format_market_source(market(1, _source=None, _saved=True)), t('marketplace.source_local'))
        self.assertEqual(format_market_source(market(1)), '')

    def test_ardent_rows_are_tagged_with_their_source(self):
        response = Mock()
        response.json.return_value = [market(1), market(2)]
        with patch('marketplace_api.tracked_request', return_value=response):
            rows = MarketplaceAPI._fetch_ardent('/x', {})
        self.assertEqual([r['_source'] for r in rows], ['Ardent', 'Ardent'])


class SearchTests(unittest.TestCase):
    def run_search(self, trade, order, rows, buy=False, mode='galaxy_wide', limit='250'):
        app = App()
        parent = Widget()
        app.after = parent.after
        prefix = 'trade' if trade else 'marketplace'
        for key, value in dict(commodity='Platinum', search_mode=mode, reference_system='Sol', max_age='Any',
                               buy_mode=buy, sell_mode=not buy, exclude_carriers=False, station_type='All',
                               large_pad_only=False, order_by=order, galaxy_max_results=limit).items():
            setattr(app, prefix + '_' + key, SimpleNamespace(get=lambda value=value: value))
        setattr(app, prefix + '_search_btn', Widget())
        setattr(app, prefix + '_total_label', Widget())
        setattr(app, prefix + '_tree', Mock())
        for key in ('commodity', 'age', 'station_type', 'sort'):
            setattr(app, '_' + ('trade_' if trade and key != 'commodity' else '') + key + '_rev_map', {})
        app._convert_age_to_days = lambda value: 30
        setattr(app, '_save_' + prefix + '_preferences', Mock())
        display = Mock()
        setattr(app, '_display_' + prefix + '_search_results', display)
        api = ('search_sellers' if buy else 'search_buyers') + ('_galaxy_wide' if mode == 'galaxy_wide' else '')
        def distances(candidates, reference, **kwargs):
            for row in candidates:
                row['distance'] = 1000 - row['marketId']
            return candidates
        with patch.object(MarketplaceAPI, api, return_value=rows), \
                patch.object(MarketplaceAPI, 'add_distances_to_results', side_effect=distances) as measure, \
                patch('threading.Thread', ImmediateThread):
            (app._search_trade_market if trade else app._search_marketplace)()
        parent.flush()
        return display.call_args.args[0], measure

    def test_nearest_candidate_outside_price_top_50_is_included(self):
        for trade in (False, True):
            with self.subTest(trade=trade):
                rows = [market(i, sellPrice=1000-i, distance=None) for i in range(61)]
                found, measure = self.run_search(trade, 'Distance', rows)
                self.assertEqual(len(measure.call_args.args[0]), 61)
                self.assertEqual(found[0]['marketId'], 60)

    def test_limits_follow_selected_sort_and_reduce_distance_work_when_possible(self):
        for trade in (False, True):
            for buy in (False, True):
                for order in ('Distance', 'Best price (lowest)' if buy else 'Best price (highest)',
                              'Best supply' if buy else 'Best demand', 'Last update'):
                    with self.subTest(trade=trade, buy=buy, order=order):
                        rows = [market(i, buyPrice=i+1, sellPrice=i+1, demand=i+1, stock=i+1,
                                       updatedAt=f'2026-11-18T12:{i // 60:02}:{i % 60:02}Z', distance=None)
                                for i in range(400)]
                        # A higher-priced station excluded by the filters must not consume a slot.
                        rows.append(market(999, buyPrice=0, sellPrice=0))
                        found, measure = self.run_search(trade, order, rows, buy, limit='100')
                        self.assertEqual(len(found), 100)
                        self.assertEqual(len(measure.call_args.args[0]), 400 if order == 'Distance' else 100)
                        expected = set(range(100)) if buy and 'price' in order else set(range(300, 400))
                        self.assertEqual({r['marketId'] for r in found}, expected)

    def test_default_limit_all_and_near_system_isolation(self):
        for trade in (False, True):
            for mode, limit, count in (('galaxy_wide', '250', 250), ('galaxy_wide', '500', 400),
                                       ('galaxy_wide', 'All', 400), ('near_system', '100', 400)):
                with self.subTest(trade=trade, mode=mode, limit=limit):
                    found, measure = self.run_search(trade, 'Best price (highest)',
                        [market(i) for i in range(400)], mode=mode, limit=limit)
                    self.assertEqual(len(found), count)
                    if mode == 'near_system':
                        measure.assert_not_called()

    def test_actual_buy_workers_sort_price_and_supply(self):
        for trade in (False, True):
            for order in ('Best price (lowest)', 'Best supply'):
                with self.subTest(trade=trade, order=order):
                    rows = [market(1, buyPrice=100, sellPrice=1, stock=1, demand=90),
                            market(2, buyPrice=50, sellPrice=100, stock=20, demand=1)]
                    found, _ = self.run_search(trade, order, rows, buy=True, mode='near_system')
                    self.assertEqual(found[0]['marketId'], 2)

    def test_every_sort_keeps_and_measures_all_galaxy_matches(self):
        for trade in (False, True):
            for order in ('Distance', 'Best price (lowest)', 'Best supply', 'Last update'):
                with self.subTest(trade=trade, order=order):
                    rows = [market(i, buyPrice=i+1, distance=None) for i in range(139)]
                    found, measure = self.run_search(trade, order, rows, buy=True)
                    self.assertEqual(len(measure.call_args.args[0]), 139)
                    self.assertEqual({r['marketId'] for r in found}, set(range(139)))

    def test_both_renderers_receive_all_matches(self):
        for trade in (False, True):
            with self.subTest(trade=trade):
                app = App()
                app.config = Mock()
                prefix = 'trade' if trade else 'marketplace'
                render = Mock()
                setattr(app, '_display_' + prefix + '_results', render)
                setattr(app, prefix + '_total_label', Widget())
                rows = [market(i) for i in range(139)]
                if trade:
                    app._display_trade_search_results(rows, 'galaxy_wide', True, len(rows))
                else:
                    app._display_marketplace_search_results(rows, 'galaxy_wide', 'Sol', True, False, len(rows))
                self.assertEqual(len(render.call_args.args[0]), 139)

    def test_result_summary_reports_filtered_total_and_selected_order(self):
        strings = json.loads((ROOT / 'app/localization/strings_en.json').read_text(encoding='utf-8-sig'))
        with patch.dict(App._display_trade_search_results.__globals__,
                        t=lambda key: strings['marketplace'][key.split('.')[1]]):
            for trade in (False, True):
                app = App()
                app.config = Mock()
                prefix = 'trade' if trade else 'marketplace'
                setattr(app, '_display_' + prefix + '_results', Mock())
                label = Widget()
                setattr(app, prefix + '_total_label', label)
                rows = [market(i) for i in range(100)]
                if trade:
                    app._display_trade_search_results(rows, 'galaxy_wide', False, 450, 400, 'Distance')
                else:
                    app._display_marketplace_search_results(rows, 'galaxy_wide', 'Sol', False, False,
                                                            450, 400, 'Distance')
                self.assertIn('100', label.cget('text'))
                self.assertIn('400', label.cget('text'))
                self.assertNotIn('450', label.cget('text'))
                self.assertIn('Distance', label.cget('text'))


class GalaxyOptionsTests(unittest.TestCase):
    def test_age_preferences_visibility_and_limits_are_isolated_and_restored(self):
        methods = load_methods('app/commodity_market_tab.py', 'CommodityMarketTabMixin', {
            '_setup_galaxy_market_options', '_market_age_preferences', '_galaxy_market_limit'})
        for language in ('en', 'de'):
            strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
            def translate(key):
                section, key = key.split('.')
                return strings[section][key]
            methods._setup_galaxy_market_options.__globals__.update(tk=tk, ttk=ttk, t=translate)
            for prefix in ('marketplace', 'trade'):
                with self.subTest(language=language, prefix=prefix):
                    root = tk.Tk()
                    root.withdraw()
                    try:
                        for name in ('_setup_galaxy_market_options', '_market_age_preferences', '_galaxy_market_limit'):
                            setattr(root, name, getattr(methods, name).__get__(root))
                        ages = {'Any': strings['marketplace']['any'],
                                '1 hour': strings['marketplace']['1_hour'],
                                '1 day': strings['marketplace']['1_day'],
                                '2 days': strings['marketplace']['2_days']}
                        reverse = {value: key for key, value in ages.items()}
                        saved = {}
                        for mode in ('near_system', 'galaxy_wide'):
                            frame = ttk.Frame(root)
                            frame.pack()
                            mode_var = tk.StringVar(root, mode)
                            age_var = tk.StringVar(root, ages[saved.get(prefix + '_max_age', 'Any')])
                            setattr(root, prefix + '_search_mode', mode_var)
                            setattr(root, prefix + '_max_age', age_var)
                            save = Mock(side_effect=lambda: saved.update(root._market_age_preferences(
                                prefix, reverse[age_var.get()])))
                            setattr(root, '_save_' + prefix + '_preferences', save)
                            root._setup_galaxy_market_options(prefix, frame, saved, ages)
                            combo = next(w for w in frame.winfo_children() if isinstance(w, ttk.Combobox))
                            if mode == 'near_system':
                                self.assertFalse(combo.grid_info())
                                self.assertEqual(age_var.get(), ages['Any'])
                                age_var.set(ages['1 hour'])
                                mode_var.set('galaxy_wide')
                                self.assertTrue(combo.grid_info())
                                self.assertEqual(age_var.get(), ages['2 days'])
                                self.assertEqual(root._galaxy_market_limit(prefix), 250)
                                age_var.set(ages['1 day'])
                                getattr(root, prefix + '_galaxy_max_results').set('100')
                                mode_var.set('near_system')
                                self.assertEqual(age_var.get(), ages['1 hour'])
                                self.assertEqual(saved[prefix + '_max_age'], '1 hour')
                                mode_var.set('galaxy_wide')
                                self.assertEqual(age_var.get(), ages['1 day'])
                            else:
                                self.assertEqual(age_var.get(), ages['1 day'])
                                self.assertEqual(root._galaxy_market_limit(prefix), 100)
                                getattr(root, prefix + '_galaxy_max_results').set(translate('marketplace.all'))
                                save()
                                self.assertEqual(saved[prefix + '_galaxy_max_results'], 'All')
                                self.assertIsNone(root._galaxy_market_limit(prefix))
                            frame.destroy()
                    finally:
                        root.destroy()


class PlannerTests(unittest.TestCase):
    def test_pruning_matches_exhaustive_payout_and_tonnage(self):
        rng = random.Random(42)
        for _ in range(100):
            cargo = {'Gold': rng.randint(1, 100), 'Silver': rng.randint(1, 100)}
            offers = {i: {name: (rng.randint(1, 200), rng.randint(1, 100)) for name in cargo} for i in range(8)}
            markets = [(name, [market(i, sellPrice=data[name][0], demand=data[name][1]) for i, data in offers.items()]) for name in cargo]
            def payout(stops):
                total = sold = 0
                for name, count in cargo.items():
                    remaining = count
                    for price, demand in sorted((offers[i][name] for i in stops), reverse=True):
                        qty = min(remaining, demand)
                        remaining -= qty
                        total += qty * price
                        sold += qty
                return total, sold
            expected = max(payout(stops) for stops in list(combinations(offers, 1)) + list(combinations(offers, 2)))
            plans = build_plans(cargo, markets)
            self.assertEqual(max((p['total'], p['sold']) for _, p in plans), expected)

    def test_stop_skips_pairs_and_retains_one_stop_results(self):
        stop = Mock(return_value=True)
        plans = build_plans({'Gold': 100}, [('Gold', [market(i, demand=10, sellPrice=i+1) for i in range(100)])], stop)
        stop.assert_called_once()
        self.assertEqual([name for name, _ in plans], ['one_stop', 'quick_sale'])

    def test_complete_best_price_sale_never_enumerates_pairs(self):
        with patch('cargo_sell_planner.combinations') as pairs:
            build_plans({'Gold': 100}, [('Gold', [market(i, sellPrice=i+1) for i in range(1000)])])
        pairs.assert_not_called()


class TableApp(tk.Tk, ColumnVisibilityMixin):
    pass


class MultiplePricesTableTests(unittest.TestCase):
    @staticmethod
    def cancel_callbacks(root):
        for callback in root.tk.call('after', 'info'):
            root.tk.call('after', 'cancel', callback)

    def test_scroll_resize_hide_reorder_and_restore_in_both_languages(self):
        for language, scale in ((language, scale) for language in ('en', 'de') for scale in (1, 1.1, 1.2, 1.3, 1.5)):
            with self.subTest(language=language, scale=scale), ExitStack() as stack:
                strings = json.loads((ROOT / f'app/localization/strings_{language}.json').read_text(encoding='utf-8-sig'))
                def translate(key):
                    value = strings
                    for part in key.split('.'):
                        value = value[part]
                    return value
                widths = {}
                visibility = {}
                order = []
                stack.enter_context(patch('multi_mineral_tab.t', translate))
                stack.enter_context(patch('config.load_multiple_prices_column_widths', side_effect=lambda: widths.copy()))
                stack.enter_context(patch('config.save_multiple_prices_column_widths', side_effect=lambda value: widths.update(value)))
                stack.enter_context(patch('config.load_column_visibility', side_effect=lambda key: visibility.copy()))
                stack.enter_context(patch('config.save_column_visibility', side_effect=lambda key, value: visibility.update(value)))
                stack.enter_context(patch('config.load_column_order', side_effect=lambda key: order.copy()))
                stack.enter_context(patch('config.save_column_order', side_effect=lambda key, value: order.__setitem__(slice(None), value)))
                root = TableApp()
                stack.callback(root.destroy)
                stack.callback(self.cancel_callbacks, root)
                root.geometry('700x650+-3000+-3000')
                root._scaled_font = lambda size, *style: ('Segoe UI', round(size * scale), *style)
                root._scaled_px = lambda size: round(size * scale)
                for key, value in dict(reference_system='Sol', station_type='All', exclude_carriers=True,
                                       large_pad_only=False, max_age='Any').items():
                    setattr(root, 'marketplace_' + key, tk.BooleanVar(root, value) if isinstance(value, bool) else tk.StringVar(root, value))
                root._station_type_map = {key: key for key in ('All', 'Fleet Carrier')}
                root._station_type_rev_map = {}
                root._station_type_order = ['All', 'Fleet Carrier']
                root._commodity_map = {}
                root._age_map = {'Any': 'Any'}
                root._age_order = ['Any']
                root._cv_add_columns_button = lambda *args: None
                frame = tk.Frame(root)
                frame.pack(fill='both', expand=True)
                tab = MultiMineralTab(frame, root)
                root.update()
                narrow_rows = max(cb.grid_info()['row'] for cb in tab._mineral_checks) + 1
                root.geometry('1500x850+-3000+-3000')
                root.update()
                wide_rows = max(cb.grid_info()['row'] for cb in tab._mineral_checks) + 1
                self.assertLess(wide_rows, narrow_rows)
                for cb in tab._mineral_checks:
                    self.assertLessEqual(cb.winfo_x() + cb.winfo_width(), cb.master.winfo_width())
                root.geometry('700x650+-3000+-3000')
                root.update()
                heading_font = tkfont.Font(font=root._scaled_font(9, 'bold'))
                for column in ('#0',) + tuple(c for c in tab.tree['columns'] if c != '_spacer'):
                    self.assertGreaterEqual(tab.tree.column(column, 'minwidth'),
                                            heading_font.measure(tab.tree.heading(column, 'text')) + root._scaled_px(24))
                tab.station_var.set('Fleet Carrier')
                self.assertFalse(tab.exclude_carriers_var.get())
                self.assertEqual(str(tab.exclude_carriers_cb['state']), 'disabled')
                tab.station_var.set('All')
                self.assertEqual(str(tab.exclude_carriers_cb['state']), 'normal')
                tab.tree.column('station', width=600)
                tab.tree.event_generate('<ButtonRelease-1>', x=0, y=0)
                root.update()
                self.assertEqual(widths['station'], 600)
                stations = [dict(info=market(i, distanceToArrival=ls), minerals={})
                            for i, ls in enumerate(('1234.9', 0, None))]
                with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
                    tab._complete(stations, 1)
                self.assertEqual([tab.tree.set(item, 'ls') for item in tab.tree.get_children()], ['1,234', '0', '?'])
                root.geometry('800x650+-3000+-3000')
                root.update()
                self.assertEqual(tab.tree.column('station', 'width'), 600)
                tab.tree.xview_moveto(1)
                root.update()
                self.assertGreater(tab.tree.xview()[0], 0)
                self.assertTrue(tab.tree['xscrollcommand'])
                for i in range(60):
                    tab.tree.insert('', 'end', values=(str(i),))
                tab.tree.yview_moveto(1)
                root.update()
                self.assertGreater(tab.tree.yview()[0], 0)
                root._cv_toggle('price', 'multiple_prices')
                self.assertNotIn('price', tab.tree['displaycolumns'])
                root._cv_set_order('multiple_prices', ['updated', 'station'])
                self.assertEqual(displayed_column(tab.tree, '#1'), 'updated')
                self.assertEqual(tab.tree.column('station', 'width'), 600)
                self.cancel_callbacks(root)
                frame.destroy()
                frame = tk.Frame(root)
                frame.pack(fill='both', expand=True)
                restored = MultiMineralTab(frame, root)
                root.update()
                self.assertEqual(restored.tree.column('station', 'width'), 600)
                self.assertNotIn('price', restored.tree['displaycolumns'])
                self.assertEqual(displayed_column(restored.tree, '#1'), 'updated')
                root._cv_toggle('price', 'multiple_prices')
                self.assertIn('price', restored.tree['displaycolumns'])
                self.assertGreaterEqual(restored.tree.column('price', 'width'), restored.tree.column('price', 'minwidth'))

    def test_saved_layout_puts_system_and_station_where_location_was(self):
        with ExitStack() as stack:
            widths, visibility, order = {}, {'location': False}, ['pad', 'location', 'type']
            stack.enter_context(patch('multi_mineral_tab.t', lambda key: key))
            stack.enter_context(patch('config.load_multiple_prices_column_widths', side_effect=lambda: widths.copy()))
            stack.enter_context(patch('config.save_multiple_prices_column_widths', side_effect=lambda value: widths.update(value)))
            stack.enter_context(patch('config.load_column_visibility', side_effect=lambda key: visibility.copy()))
            stack.enter_context(patch('config.save_column_visibility', side_effect=lambda key, value: visibility.update(value)))
            stack.enter_context(patch('config.load_column_order', side_effect=lambda key: order.copy()))
            stack.enter_context(patch('config.save_column_order', side_effect=lambda key, value: order.__setitem__(slice(None), value)))
            root = TableApp()
            stack.callback(root.destroy)
            stack.callback(self.cancel_callbacks, root)
            root.withdraw()
            root._scaled_font = lambda size, *style: ('Segoe UI', size, *style)
            root._scaled_px = lambda size: size
            for key, value in dict(reference_system='Sol', station_type='All', exclude_carriers=True,
                                   large_pad_only=False, max_age='Any').items():
                setattr(root, 'marketplace_' + key, tk.BooleanVar(root, value) if isinstance(value, bool) else tk.StringVar(root, value))
            root._station_type_map = {key: key for key in ('All', 'Fleet Carrier')}
            root._station_type_rev_map = {}
            root._station_type_order = ['All', 'Fleet Carrier']
            root._commodity_map = {}
            root._age_map = {'Any': 'Any'}
            root._age_order = ['Any']
            root._cv_add_columns_button = lambda *args: None
            tab = MultiMineralTab(tk.Frame(root), root)
            shown = list(tab.tree['displaycolumns'])
            self.assertEqual(shown[:2], ['pad', 'type'])
            self.assertNotIn('system', shown)
            self.assertNotIn('station', shown)
            visibility.clear()
            order[:] = ['pad', 'location']
            tab = MultiMineralTab(tk.Frame(root), root)
            self.assertEqual(list(tab.tree['displaycolumns'])[:4], ['pad', 'system', 'station', 'type'])
            with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
                tab._complete([dict(info=market(0, stationName='A Very Long Station Name / With Slash'),
                                    minerals={'Gold': market(0)})], 1)
            parent = tab.tree.get_children()[0]
            self.assertEqual(tab.tree.set(parent, 'station'), 'A Very Long Station Name / With Slash')
            child = tab.tree.get_children(parent)[0]
            self.assertTrue(tab.tree.set(child, 'demand'))


if __name__ == '__main__':
    unittest.main()
