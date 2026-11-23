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


def make_view(reference='Sol', mineral='All Minerals', pp_mode=False):
    v = View()
    v._bm = {'busy': False, 'status': '', 'hint': '', 'spin': 0, 'spinning': True, 'ran': False,
             'system': '', 'count': 0, 'cache': None,
             'system_by_row': {}, 'sell_system_by_row': {}, 'source_by_row': {}}
    v._bm_all_label = 'All Minerals'
    v._bm_mineral_var = Var(mineral)
    v._bm_distance_var = Var('50')
    v._bm_pp_mode_var = Var(pp_mode)
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
            'systemZ': 0.0, 'distanceToArrival': ls, 'stationType': 'Coriolis', 'updatedAt': '1h'}


def cache(rows_by_material, candidates=None, coords=None, target='Sol'):
    return {'target_system': target,
            'candidates': candidates or [('MineA', {'distance': 5.0, 'materials': {'Platinum'}}),
                                         ('MineB', {'distance': 9.0, 'materials': {'Platinum', 'Painite'}})],
            'rows_by_material': rows_by_material,
            'candidate_coords': coords if coords is not None else {'MineA': {'x': 0, 'y': 0, 'z': 0},
                                                                   'MineB': {'x': 100, 'y': 0, 'z': 0}},
            'max_distance': 50.0}


class RankTests(unittest.TestCase):
    def rank(self, c, pp_mode):
        return BestMiningMixin._rerank_reverse_search_results(
            c['target_system'], c['candidates'], c['rows_by_material'], c['candidate_coords'],
            c['max_distance'], pp_mode)

    def test_without_pp_mode_each_candidate_uses_its_nearest_buyer(self):
        c = cache({'Platinum': [buyer('Near A', 100, x=2), buyer('Near B', 90, x=98), buyer('Sol', 500, x=300)],
                   'Painite': [buyer('Near B2', 300, x=101)]})
        results = self.rank(c, False)
        by_system = {r['system']: r for r in results}
        self.assertEqual(by_system['MineA']['best']['systemName'], 'Near A')
        self.assertEqual(by_system['MineB']['best']['systemName'], 'Near B2')
        self.assertEqual(by_system['MineB']['mineral'], 'Painite')
        self.assertEqual([r['system'] for r in results], ['MineB', 'MineA'])  # highest price first

    def test_pp_mode_counts_only_the_reference_system(self):
        c = cache({'Platinum': [buyer('Near A', 900, x=2), buyer('Sol', 300), buyer('Sol', 350, station='Dock')],
                   'Painite': [buyer('Near B2', 999, x=101)]})
        results = self.rank(c, True)
        for r in results:
            self.assertEqual(r['best']['systemName'], 'Sol')
            self.assertEqual(r['best']['sellPrice'], 350)
            self.assertEqual(r['mineral'], 'Platinum')


class RenderTests(unittest.TestCase):
    def test_toggle_reranks_cached_prices_without_a_search(self):
        v = make_view()
        v._bm['cache'] = cache({'Platinum': [buyer('Near A', 100, x=2), buyer('Sol', 300, x=300)]})
        with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}), \
                patch('marketplace_api.MarketplaceAPI.search_buyers') as buyers, \
                patch('config.save_pp_mode'):
            v._bm_rerender()
            first = v._bm_tree.values(v._bm_tree.order[0], 'Station')
            v._bm_pp_mode_var.set(True)
            v._bm_on_pp_toggle()
        buyers.assert_not_called()
        self.assertEqual(first, 'Port (Near A)')
        self.assertEqual(v._bm_tree.values(v._bm_tree.order[0], 'Station'), 'Port')
        self.assertEqual(v._bm_tree.values(v._bm_tree.order[0], 'Price'), '300 CR')

    def test_pp_mode_without_a_market_shows_hint_not_empty_rows(self):
        v = make_view(pp_mode=True)
        v._bm['cache'] = cache({'Platinum': [buyer('Near A', 100, x=2)]})
        with patch('system_finder_api.SystemFinderAPI._batch_get_powerplay', return_value={}):
            v._bm_rerender()
        self.assertEqual(v._bm_tree.order, [])
        self.assertIn('Sol', v._bm['hint'])
        self.assertEqual(v._bm['count'], 0)

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
        self.assertEqual(v._bm_tree.values(row, 'Dist'), '5.0')
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
        self.assertEqual(thread.call_args.kwargs['args'][1:4], ('Sol', 50.0, 'Low Temperature Diamonds'))

    def test_view_click_runs_only_once(self):
        v = make_view()
        v._bm_sync_pp_mode = Mock()
        v._bm_start = Mock()
        v._bm_on_view_click()
        v._bm['ran'] = True
        v._bm_on_view_click()
        v._bm_start.assert_called_once()

    def test_view_click_without_reference_does_not_search(self):
        v = make_view(reference='')
        v._bm_sync_pp_mode = Mock()
        v._bm_start = Mock()
        v._bm_on_view_click()
        v._bm_start.assert_not_called()

    def test_no_candidates_hint(self):
        v = make_view()
        v._get_hotspots = Mock(return_value=[])
        control = Mock()
        control.is_cancelled.return_value = False
        v._reverse_search_worker('Sol', 50.0, None, control)
        rows, callback = control.complete.call_args.args
        self.assertEqual(rows, [])
        v._bm_fill = Mock()
        callback(rows)
        self.assertIn('Sol', v._bm['hint'])


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
