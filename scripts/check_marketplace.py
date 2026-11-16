import json
import math
import random
import sys
import threading
import tkinter as tk
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

from app_utils import format_market_pad, format_market_powerplay, format_market_station_type
from cargo_sell_planner import build_plans
from column_visibility_helper import ColumnVisibilityMixin, displayed_column
from marketplace_api import MarketplaceAPI, _short_cache, _short_cache_key_locks
from multi_mineral_tab import MultiMineralTab
from check_search_stop import App, ImmediateThread, Widget


def market(index, **changes):
    return dict(dict(systemName='Sol', stationName=str(index), marketId=index,
                     sellPrice=100, buyPrice=50, demand=100, stock=20,
                     distance=10, stationType='Coriolis', maxLandingPadSize=3,
                     updatedAt=datetime.now(timezone.utc).isoformat()), **changes)


class MarketTests(unittest.TestCase):
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
                self.assertEqual(ardent.call_args_list[0].args[1]['maxDistance'], 50)
                for source in sources:
                    self.assertEqual(source.call_args.args[3], 50)

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


class SearchTests(unittest.TestCase):
    def run_search(self, trade, order, rows, buy=False, mode='galaxy_wide'):
        app = App()
        parent = Widget()
        app.after = parent.after
        prefix = 'trade' if trade else 'marketplace'
        for key, value in dict(commodity='Platinum', search_mode=mode, reference_system='Sol', max_age='Any',
                               buy_mode=buy, sell_mode=not buy, exclude_carriers=False, station_type='All',
                               large_pad_only=False, order_by=order).items():
            setattr(app, prefix + '_' + key, SimpleNamespace(get=lambda value=value: value))
        setattr(app, prefix + '_search_btn', Widget())
        setattr(app, prefix + '_total_label', Widget())
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
                tab.tree.column('location', width=600)
                tab.tree.event_generate('<ButtonRelease-1>', x=0, y=0)
                root.update()
                self.assertEqual(widths['location'], 600)
                stations = [dict(info=market(i, distanceToArrival=ls), minerals={})
                            for i, ls in enumerate(('1234.9', 0, None))]
                with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
                    tab._complete(stations, 1)
                self.assertEqual([tab.tree.set(item, 'ls') for item in tab.tree.get_children()], ['1,234', '0', '?'])
                root.geometry('800x650+-3000+-3000')
                root.update()
                self.assertEqual(tab.tree.column('location', 'width'), 600)
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
                root._cv_set_order('multiple_prices', ['updated', 'location'])
                self.assertEqual(displayed_column(tab.tree, '#1'), 'updated')
                self.assertEqual(tab.tree.column('location', 'width'), 600)
                self.cancel_callbacks(root)
                frame.destroy()
                frame = tk.Frame(root)
                frame.pack(fill='both', expand=True)
                restored = MultiMineralTab(frame, root)
                root.update()
                self.assertEqual(restored.tree.column('location', 'width'), 600)
                self.assertNotIn('price', restored.tree['displaycolumns'])
                self.assertEqual(displayed_column(restored.tree, '#1'), 'updated')
                root._cv_toggle('price', 'multiple_prices')
                self.assertIn('price', restored.tree['displaycolumns'])
                self.assertGreaterEqual(restored.tree.column('price', 'width'), restored.tree.column('price', 'minwidth'))


if __name__ == '__main__':
    unittest.main()
