"""Window-free checks for the Hotspots Finder Where to Mine (Best Mining System) view."""
import json
import re
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from best_minerals_view import BestMineralsMixin  # noqa: E402
from best_mining_view import BestMiningMixin  # noqa: E402


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Tree:
    """Just enough of a Treeview for _bm_fill and the click handler."""
    def __init__(self, displaycolumns=('#all',)):
        self.rows = {}
        self.order = []
        self.config = {'columns': BestMiningMixin.BM_COLUMNS, 'displaycolumns': displaycolumns}
        self.click_row = ''
        self.click_column = '#1'

    def __getitem__(self, key):
        return self.config[key]

    def get_children(self, item=''):
        return tuple(self.order)

    def delete(self, *items):
        for item in items:
            self.rows.pop(item, None)
            self.order.remove(item)

    def insert(self, parent, index, values):
        row_id = f'r{len(self.rows) + 1}'
        self.rows[row_id] = list(values)
        self.order.append(row_id)
        return row_id

    def values(self, row_id, column):
        return self.rows[row_id][BestMiningMixin.BM_COLUMNS.index(column)]

    def identify_row(self, y):
        return self.click_row

    def identify_column(self, x):
        return self.click_column

    def selection_set(self, row_id):
        pass


class View(BestMiningMixin, BestMineralsMixin):
    pass


def make_view(reference='Sol', mineral='All Minerals'):
    v = View()
    v._bm = {'busy': False, 'status': '', 'hint': '', 'spin': 0, 'spinning': True, 'ran': False,
             'system': '', 'count': 0, 'cache': None,
             'system_by_row': {}, 'sell_system_by_row': {}, 'source_by_row': {}}
    v._bm_all_label = 'All Minerals'
    v._bm_mineral_var = Var(mineral)
    v._bm_distance_var = Var('50')
    v._bm_sell_distance_var = Var('50')
    v._bm_control = Mock(running=False)
    v._bm_refresh_controls = Mock()
    v._bm_tree = Tree()
    v.system_var = Var(reference)
    v._results_view_var = Var('hotspots')
    v._saved_system_spelling = lambda name: name
    v._to_english = lambda m: 'Low Temp Diamonds' if m == 'LTDs' else m
    v._format_material_for_display = lambda m: m
    v._format_station_type = lambda s: s or '-'
    v._format_data_age = lambda ts: ts or '-'
    return v


def buyer(system, price, x=0.0, station='Port', ls=1234.6):
    return {'systemName': system, 'stationName': station, 'sellPrice': price, 'systemX': x, 'systemY': 0.0,
            'systemZ': 0.0, 'distanceToArrival': ls, 'stationType': 'Coriolis', 'updatedAt': '1h', 'demand': 12345}


def cache(rows_by_material, candidates=None, coords=None, sell_distance=50.0):
    return {'candidates': candidates or [('MineA', {'distance': 5.0, 'materials': {'Platinum'}}),
                                         ('MineB', {'distance': 9.0, 'materials': {'Platinum', 'Painite'}})],
            'rows_by_material': rows_by_material,
            'candidate_coords': coords if coords is not None else {'MineA': {'x': 0, 'y': 0, 'z': 0},
                                                                   'MineB': {'x': 100, 'y': 0, 'z': 0}},
            'max_distance': 50.0, 'sell_distance': sell_distance}


class RankTests(unittest.TestCase):
    def rank(self, c):
        return BestMiningMixin._rerank_reverse_search_results(
            c['candidates'], c['rows_by_material'], c['candidate_coords'], c['sell_distance'])

    def test_each_candidate_uses_its_best_price_within_sell_range(self):
        c = cache({'Platinum': [buyer('Near A', 100, x=2), buyer('Far A', 400, x=40), buyer('Near B', 90, x=98),
                                buyer('Too Far', 999, x=300)],
                   'Painite': [buyer('Near B2', 300, x=101)]})
        results = self.rank(c)
        by_system = {r['system']: r for r in results}
        self.assertEqual(by_system['MineA']['best']['systemName'], 'Far A')
        self.assertAlmostEqual(by_system['MineA']['sell_distance'], 40.0)
        self.assertEqual(by_system['MineB']['best']['systemName'], 'Near B2')  # Far A is 60 Ly from MineB
        self.assertEqual(by_system['MineB']['mineral'], 'Painite')
        self.assertEqual([r['system'] for r in results], ['MineA', 'MineB'])

    def test_nearest_mining_system_comes_first(self):
        c = cache({'Platinum': [buyer('Near A', 100, x=2), buyer('Near B', 900, x=98)]})
        self.assertEqual([r['system'] for r in self.rank(c)], ['MineA', 'MineB'])  # 5 Ly before 9 Ly
        c['candidates'][0][1]['distance'] = 20.0
        self.assertEqual([r['system'] for r in self.rank(c)], ['MineB', 'MineA'])

    def test_equal_prices_pick_the_nearer_buyer(self):
        c = cache({'Platinum': [buyer('Farther', 200, x=30), buyer('Nearer', 200, x=10)]},
                  candidates=[('MineA', {'distance': 5.0, 'materials': {'Platinum'}})])
        self.assertEqual(self.rank(c)[0]['best']['systemName'], 'Nearer')

    def test_sell_within_is_separate_from_max_distance(self):
        c = cache({'Platinum': [buyer('Far A', 400, x=80)]}, sell_distance=100.0,
                  candidates=[('MineA', {'distance': 5.0, 'materials': {'Platinum'}})])
        self.assertEqual(self.rank(c)[0]['best']['systemName'], 'Far A')  # 80 Ly > Max Distance 50
        c['sell_distance'] = 50.0
        self.assertIsNone(self.rank(c)[0]['best'])

    def test_candidate_without_coordinates_is_unpriced(self):
        c = cache({'Platinum': [buyer('Near A', 100, x=2)]}, coords={},
                  candidates=[('MineA', {'distance': 5.0, 'materials': {'Platinum'}})])
        self.assertIsNone(self.rank(c)[0]['best'])


class RenderTests(unittest.TestCase):
    def test_results_show_while_the_search_is_still_marked_busy(self):
        # SearchControl calls the results callback first and clears busy afterwards
        v = make_view()
        v._bm['busy'] = True
        with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
            v._bm_show_results(cache({'Platinum': [buyer('Near A', 100, x=2)]}))
        self.assertEqual(len(v._bm_tree.order), 1)  # MineB has no buyer within 50 Ly
        self.assertEqual(v._bm['count'], 1)

    def test_systems_without_a_buyer_in_range_are_hidden(self):
        v = make_view()
        # MineA has a buyer 2 Ly away; MineB's only buyer is 98 Ly away
        v._bm['cache'] = cache({'Platinum': [buyer('Near A', 100, x=2)]})
        with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
            v._bm_rerender()
        self.assertEqual(list(v._bm['system_by_row'].values()), ['MineA'])
        self.assertEqual(v._bm['count'], 1)
        self.assertEqual(v._bm['hint'], '')

    def test_no_buyer_anywhere_gives_hint(self):
        v = make_view()
        v._bm['cache'] = cache({'Platinum': [buyer('Far', 100, x=500)]})
        with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
            v._bm_rerender()
        self.assertEqual(v._bm_tree.order, [])
        self.assertIn('50', v._bm['hint'])

    def test_row_formatting(self):
        v = make_view()
        v._bm['cache'] = cache({'Platinum': [buyer('Near A', 123456, x=2, ls=1234.6)]},
                               candidates=[('MineA', {'distance': 5.0, 'materials': {'Platinum'}})])
        pp = {'Near A': {'controlling_power': '~none~', 'power_state': 'Unoccupied'}}
        with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value=pp):
            v._bm_rerender()
        row = v._bm_tree.order[0]
        self.assertEqual(v._bm_tree.values(row, 'Price'), '123,456 CR')
        self.assertEqual(v._bm_tree.values(row, 'LS'), '1,234')
        self.assertEqual(v._bm_tree.values(row, 'Demand'), '12,345')
        self.assertEqual(v._bm_tree.values(row, 'Dist'), '5.0')
        self.assertEqual(v._bm_tree.values(row, 'SellDist'), '2.0')  # MineA at x=0, buyer at x=2
        self.assertEqual(v._bm_tree.values(row, 'PowerPlay'), 'Unoccupied')
        self.assertEqual(v._bm['sell_system_by_row'][row], 'Near A')
        self.assertEqual(v._bm['system_by_row'][row], 'MineA')


class RunTests(unittest.TestCase):
    def test_no_reference_gives_hint_and_no_worker(self):
        v = make_view(reference='')
        with patch('best_mining_view.threading.Thread') as thread:
            v._bm_start()
        thread.assert_not_called()
        self.assertTrue(v._bm['hint'])

    def test_start_runs_worker_with_inputs(self):
        v = make_view(mineral='LTDs')
        v._bm_spin = Mock()
        with patch('best_mining_view.threading.Thread') as thread:
            v._bm_start()
        self.assertEqual(v._results_view_var.value, 'best_mining')
        self.assertEqual(thread.call_args.kwargs['args'][1:5], ('Sol', 50.0, 50.0, 'Low Temperature Diamonds'))

    def test_view_click_runs_only_once(self):
        v = make_view()
        v._bm_start = Mock()
        v._bm_on_view_click()
        v._bm['ran'] = True
        v._bm_on_view_click()
        v._bm_start.assert_called_once()

    def test_view_click_without_reference_does_not_search(self):
        v = make_view(reference='')
        v._bm_start = Mock()
        v._bm_on_view_click()
        v._bm_start.assert_not_called()

    def test_candidate_coordinates_come_from_hotspot_rows(self):
        # The bundled galaxy database misses many hotspot systems; the rows have coordinates
        v = make_view()
        v._get_hotspots = Mock(return_value=[
            {'systemName': 'MineA', 'type': 'Platinum', 'distance': '5.0', 'coords': {'x': 1, 'y': 2, 'z': 3}},
            {'systemName': 'MineB', 'type': 'Platinum', 'distance': '9.0', 'coords': None}])
        v._parse_materials_from_hotspots = lambda value: [value]
        v._expand_abbreviated_materials = lambda value: value
        v._bm_show_results = Mock()
        control = Mock()
        control.is_cancelled.return_value = False
        local_db = Mock()
        local_db.is_database_available.return_value = True
        local_db.get_system_coordinates.side_effect = lambda name: {'x': 9, 'y': 9, 'z': 9} if name == 'MineB' else None
        with patch('marketplace_api.MarketplaceAPI.search_buyers', return_value=[]) as buyers, \
                patch('local_database.LocalSystemsDatabase', return_value=local_db):
            v._reverse_search_worker('Sol', 50.0, 30.0, 'Platinum', control)
        self.assertEqual(buyers.call_args.args[2], 80)  # Max Distance + Sell Within
        callback = control.complete.call_args.args[1]
        callback([])
        coords = v._bm_show_results.call_args.args[0]['candidate_coords']
        self.assertEqual(coords['MineA'], {'x': 1, 'y': 2, 'z': 3})
        self.assertEqual(coords['MineB'], {'x': 9, 'y': 9, 'z': 9})  # fallback only for the missing one
        local_db.get_system_coordinates.assert_called_once_with('MineB')

    def test_no_candidates_hint(self):
        v = make_view()
        v._get_hotspots = Mock(return_value=[])
        control = Mock()
        control.is_cancelled.return_value = False
        v._reverse_search_worker('Sol', 50.0, 50.0, None, control)
        rows, callback = control.complete.call_args.args
        self.assertEqual(rows, [])
        v._bm_fill = Mock()
        callback(rows)
        self.assertIn('Sol', v._bm['hint'])


class BuyerSearchTests(unittest.TestCase):
    def test_reference_system_rows_get_its_name_and_position(self):
        import marketplace_api
        from marketplace_api import MarketplaceAPI

        def ardent(path, params, is_cancelled=None):
            if path.endswith('/commodities/imports'):
                return [{'commodityName': 'platinum', 'marketId': 7, 'stationName': 'Dock', 'sellPrice': 300}]
            return []
        with patch.dict(marketplace_api._system_coords_cache, {'Ref Sys': (1.0, 2.0, 3.0)}), \
                patch.dict(marketplace_api._short_cache, clear=True), \
                patch.object(MarketplaceAPI, '_fetch_ardent', side_effect=ardent), \
                patch.object(MarketplaceAPI, '_fetch_spansh_nearby', return_value=[]), \
                patch.object(MarketplaceAPI, '_fetch_spansh_carriers', return_value=[]), \
                patch.object(MarketplaceAPI, '_fetch_eddn_cache', return_value=[]), \
                patch.object(MarketplaceAPI, '_backfill_eddn_cache'):
            rows = MarketplaceAPI.search_buyers('Platinum', 'Ref Sys', 80, 7, False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['systemName'], 'Ref Sys')
        self.assertEqual((rows[0]['systemX'], rows[0]['systemY'], rows[0]['systemZ']), (1.0, 2.0, 3.0))


class ClickTests(unittest.TestCase):
    def setUp(self):
        self.v = make_view()
        self.v._bm_copy = Mock()
        self.v._bm_open_inara_and_fetch_pp = Mock()
        self.v._bm['system_by_row']['r1'] = 'MineA'
        self.v._bm['sell_system_by_row']['r1'] = 'Near A'

    def test_powerplay_cell_found_by_name_when_columns_are_reordered(self):
        self.v._bm_tree = Tree(displaycolumns=('PowerPlay', 'System', 'Price'))
        self.v._bm_tree.click_row = 'r1'
        self.v._bm_tree.click_column = '#1'
        self.v._bm_on_click(Mock(x=0, y=0))
        self.v._bm_open_inara_and_fetch_pp.assert_called_once_with('r1', 'Near A')
        self.v._bm_copy.assert_not_called()

    def test_other_cells_copy_the_mining_system(self):
        self.v._bm_tree = Tree(displaycolumns=('PowerPlay', 'System', 'Price'))
        self.v._bm_tree.click_row = 'r1'
        self.v._bm_tree.click_column = '#3'
        self.v._bm_on_click(Mock(x=0, y=0))
        self.v._bm_copy.assert_called_once_with('MineA')
        self.v._bm_open_inara_and_fetch_pp.assert_not_called()


class StringTests(unittest.TestCase):
    def test_keys_in_both_languages(self):
        src = (ROOT / 'app' / 'best_mining_view.py').read_text(encoding='utf-8')
        keys = set(re.findall(r"t\('ring_finder\.([a-z_]+)'\)", src))
        keys |= {'view_where_to_mine', 'view_where_to_mine_tooltip'}
        for lang in ('en', 'de'):
            data = json.loads((ROOT / 'app' / 'localization' / f'strings_{lang}.json').read_text(encoding='utf-8'))
            missing = sorted(k for k in keys if k not in data['ring_finder'])
            self.assertEqual(missing, [], lang)

    def test_view_is_wired_into_the_results_switch(self):
        rf = (ROOT / 'app' / 'ring_finder.py').read_text(encoding='utf-8')
        self.assertIn("('best_mining', t('ring_finder.view_where_to_mine'))", rf)
        bmv = (ROOT / 'app' / 'best_minerals_view.py').read_text(encoding='utf-8')
        self.assertIn("view == 'best_mining'", bmv)
        self.assertIn("self._bm_on_view_click()", bmv)


if __name__ == '__main__':
    unittest.main()
