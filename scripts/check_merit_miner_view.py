"""Window-free checks for the Hotspots Finder Merit Miner view."""
import json
import re
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from acquisition_view import AcquisitionMixin  # noqa: E402
from best_minerals_view import BestMineralsMixin  # noqa: E402
from merit_miner_view import MeritMinerMixin  # noqa: E402
from system_finder_api import SystemFinderAPI  # noqa: E402


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Control:
    """Runs completion callbacks straight away, like SearchControl on the UI thread."""
    def __init__(self, cancelled=False):
        self.running = False
        self.cancelled = cancelled
        self.results = None

    def is_cancelled(self):
        return self.cancelled

    def complete(self, rows, callback):
        self.results = rows
        if rows or not self.cancelled:
            callback(rows)


class View(MeritMinerMixin, AcquisitionMixin, BestMineralsMixin):
    pass


def make_view(power='Aisling Duval', minerals=('Platinum',)):
    v = View()
    v._mm = {'busy': False, 'status': '', 'hint': '', 'spin': 0, 'spinning': True, 'ran': False,
             'reference': '', 'power': '',
             'mine_by_row': {}, 'sell_by_row': {}, 'station_by_row': {}, 'source_by_row': {}}
    v._mm_powers = ('Aisling Duval', 'Zemina Torval')
    v._mm_power_prompt = 'Select your pledge...'
    v._mm_power_var = Var(power)
    v._mm_mineral_names = {'Platinum': 'Platinum', 'Painite': 'Painite', 'Osmium': 'Osmium',
                           'LTDs': 'Low Temperature Diamonds'}
    v._mm_mineral_var = Var(minerals[0] if minerals else '')
    v._mm_fill = Mock()
    v._mm_refresh_controls = Mock()
    v._mm_control = Mock(running=False)
    v._results_view_var = Var('hotspots')
    v.status_var = Mock()
    v.system_var = Var('Sol')
    v._format_material_for_display = lambda m: m
    v._lookup_system_coords = Mock(return_value={'x': 0, 'y': 0, 'z': 0})
    return v


def hotspot(system, mineral, distance, ring='A Ring'):
    return {'systemName': system, 'system': system, 'ring': ring, 'distance': f"{distance:.1f}", 'type': mineral}


def run_worker(v, hotspots_by_mineral, states, nearby, buyers, control=None, minerals=None):
    """states: {system: 'Fortified'|'Stronghold'} for the pledged power's systems.
    nearby: {mine system: {unoccupied system: {distance}}}; buyers: {mine system: [rows]}."""
    control = control or Control()
    v._get_hotspots = Mock(side_effect=lambda ref, rt, mineral, *a, **k: [dict(r) for r in hotspots_by_mineral.get(mineral, [])])

    def pp_filter(rows, power, state, *a, **k):
        return [r for r in rows if states.get(r['systemName']) == state], {}
    v._apply_powerplay_filter = Mock(side_effect=pp_filter)
    spansh = Mock(side_effect=lambda system, radius, *a, **k: nearby.get(system, {}))
    with patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_systems', spansh), \
            patch.object(SystemFinderAPI, '_store_powerplay_batch'), \
            patch('marketplace_api.MarketplaceAPI.search_buyers',
                  side_effect=lambda mineral, system, *a, **k: buyers.get(system, [])):
        v._mm_worker('Sol', 'Aisling Duval', minerals or v._mm_selected_minerals(), control)
    return control, spansh


class WorkerTests(unittest.TestCase):
    def test_state_sets_sell_radius_and_other_power_excluded(self):
        v = make_view()
        hot = {'Platinum': [hotspot('Fort', 'Platinum', 10), hotspot('Strong', 'Platinum', 12),
                            hotspot('Enemy', 'Platinum', 5)]}
        nearby = {'Fort': {'U1': {'distance': 8}}, 'Strong': {'U2': {'distance': 25}}}
        buyers = {'Fort': [{'systemName': 'U1', 'sellPrice': 100}],
                  'Strong': [{'systemName': 'U2', 'sellPrice': 200}]}
        control, spansh = run_worker(v, hot, {'Fort': 'Fortified', 'Strong': 'Stronghold'}, nearby, buyers)
        radii = {c.args[0]: c.args[1] for c in spansh.call_args_list}
        self.assertEqual(radii, {'Fort': 20.0, 'Strong': 30.0})
        self.assertEqual([r['system'] for r in control.results], ['Fort', 'Strong'])
        self.assertEqual(control.results[1]['sell_system'], 'U2')
        self.assertEqual(control.results[1]['sell_distance'], 25)

    def test_nearest_first_stops_at_five_and_skips_systems_without_buyers(self):
        v = make_view()
        systems = [f'S{i:02d}' for i in range(12)]
        hot = {'Platinum': [hotspot(s, 'Platinum', 30 - i) for i, s in enumerate(systems)]}
        nearby = {s: {'U' + s: {'distance': 3}} for s in systems}
        # Nearest two (S11, S10) have no buyer
        buyers = {s: [{'systemName': 'U' + s, 'sellPrice': 50}] for s in systems if s not in ('S11', 'S10')}
        control, _ = run_worker(v, hot, {s: 'Fortified' for s in systems}, nearby, buyers)
        self.assertEqual([r['system'] for r in control.results], ['S09', 'S08', 'S07', 'S06', 'S05'])

    def test_attempts_are_capped(self):
        v = make_view()
        systems = [f'S{i:02d}' for i in range(30)]
        hot = {'Platinum': [hotspot(s, 'Platinum', i) for i, s in enumerate(systems)]}
        control, spansh = run_worker(v, hot, {s: 'Fortified' for s in systems}, {}, {})
        self.assertEqual(spansh.call_count, View.MM_MAX_ATTEMPTS_PER_MINERAL)
        self.assertEqual(control.results, [])
        self.assertIn('Aisling Duval', v._mm['hint'])

    def test_no_power_systems_gives_hint(self):
        v = make_view()
        hot = {'Platinum': [hotspot('Enemy', 'Platinum', 5)]}
        control, spansh = run_worker(v, hot, {}, {}, {})
        spansh.assert_not_called()
        self.assertEqual(control.results, [])
        self.assertIn('500', v._mm['hint'])

    def test_unoccupied_lookup_shared_across_minerals(self):
        v = make_view()
        hot = {'Platinum': [hotspot('Fort', 'Platinum', 10)], 'Painite': [hotspot('Fort', 'Painite', 10)]}
        nearby = {'Fort': {'U1': {'distance': 8}}}
        buyers = {'Fort': [{'systemName': 'U1', 'sellPrice': 100}]}
        control, spansh = run_worker(v, hot, {'Fort': 'Fortified'}, nearby, buyers,
                                     minerals=['Platinum', 'Painite'])
        self.assertEqual(spansh.call_count, 1)
        self.assertEqual([r['mineral'] for r in control.results], ['Platinum', 'Painite'])

    def test_stop_drops_results(self):
        v = make_view()
        hot = {'Platinum': [hotspot('Fort', 'Platinum', 10)]}
        control, _ = run_worker(v, hot, {'Fort': 'Fortified'}, {}, {}, control=Control(cancelled=True))
        self.assertEqual(control.results, [])
        v._mm_fill.assert_not_called()

    def test_unknown_reference_coordinates(self):
        v = make_view()
        v._lookup_system_coords = Mock(return_value=None)
        control = Control()
        v._mm_worker('Nowhere', 'Aisling Duval', ['Platinum'], control)
        self.assertIn('Nowhere', v._mm['hint'])


class InputTests(unittest.TestCase):
    def test_unpledged_blocks_search(self):
        v = make_view(power='Select your pledge...')
        self.assertNotEqual(v._mm_ready_hint(), '')
        with patch('merit_miner_view.threading.Thread') as thread:
            v._mm_start()
        thread.assert_not_called()

    def test_no_minerals_blocks_search(self):
        v = make_view(minerals=())
        self.assertNotEqual(v._mm_ready_hint(), '')

    def test_start_runs_worker_with_inputs(self):
        v = make_view(minerals=('LTDs',))
        v._saved_system_spelling = lambda name: name
        with patch('merit_miner_view.threading.Thread') as thread:
            v._mm_start()
        self.assertEqual(v._results_view_var.value, 'merit_miner')
        self.assertEqual(thread.call_args.kwargs['args'][1:4],
                         ('Sol', 'Aisling Duval', ['Low Temperature Diamonds']))

    def test_view_click_runs_only_once(self):
        v = make_view()
        v._mm_sync_power = Mock()
        v._mm_start = Mock()
        v._mm_on_view_click()
        v._mm['ran'] = True
        v._mm_on_view_click()
        v._mm_start.assert_called_once()


class FillTests(unittest.TestCase):
    def test_demand_column_follows_buyer(self):
        v = make_view()
        del v._mm_fill
        tree = Mock()
        tree.get_children.return_value = ()
        tree.insert.side_effect = ['r1', 'r2']
        v._mm_tree = tree
        v._format_pad_size = lambda pad: pad or '-'
        v._format_data_age = lambda ts: ts
        hit = {'mineral': 'Platinum', 'system': 'Fort', 'ring': 'A Ring', 'state': 'Fortified', 'distance': 10.0,
               'sell_system': 'U1', 'sell_distance': 8.0, 'price': 100}
        with patch('app_utils.format_market_source', return_value=''):
            v._mm_fill([dict(hit, buyer={'stationName': 'Port', 'demand': 12345}), dict(hit, buyer={})])
        rows = [c.kwargs['values'] for c in tree.insert.call_args_list]
        demand = View.MM_COLUMNS.index('Demand')
        self.assertEqual(len(rows[0]), len(View.MM_COLUMNS))
        self.assertEqual(rows[0][demand], '12,345')
        self.assertEqual(rows[1][demand], '-')


class StringTests(unittest.TestCase):
    def test_keys_in_both_languages(self):
        src = (ROOT / 'app' / 'merit_miner_view.py').read_text(encoding='utf-8')
        keys = set(re.findall(r"t\('ring_finder\.(merit_miner_[a-z_]+|view_merit_miner[a-z_]*)'\)", src))
        keys |= {'merit_miner_no_mine_systems', 'merit_miner_no_buyers', 'view_merit_miner', 'view_merit_miner_tooltip'}
        for lang in ('en', 'de'):
            data = json.loads((ROOT / 'app' / 'localization' / f'strings_{lang}.json').read_text(encoding='utf-8'))
            missing = sorted(k for k in keys if k not in data['ring_finder'])
            self.assertEqual(missing, [], lang)


class PledgeTests(unittest.TestCase):
    def test_events_map_to_power(self):
        from journal_parser import JournalParser as JP
        self.assertEqual(JP.pledged_power_from_event({'event': 'Powerplay', 'Power': 'Aisling Duval'}), 'Aisling Duval')
        self.assertEqual(JP.pledged_power_from_event({'event': 'PowerplayJoin', 'Power': 'Zemina Torval'}), 'Zemina Torval')
        self.assertEqual(JP.pledged_power_from_event({'event': 'PowerplayDefect', 'FromPower': 'Zemina Torval',
                                                      'ToPower': 'A. Lavigny-Duval'}), 'Arissa Lavigny-Duval')
        self.assertEqual(JP.pledged_power_from_event({'event': 'PowerplayLeave', 'Power': 'Yuri Grom'}), JP.NOT_PLEDGED)
        self.assertIsNone(JP.pledged_power_from_event({'event': 'PowerplayMerits', 'Power': 'Yuri Grom'}))
        self.assertIsNone(JP.pledged_power_from_event({'event': 'FSDJump', 'ControllingPower': 'Yuri Grom'}))

    def test_latest_pledge_comes_from_newest_journal(self):
        import os
        import tempfile
        import time
        from journal_parser import JournalParser
        with tempfile.TemporaryDirectory() as tmp:
            def write(name, events, age):
                path = os.path.join(tmp, name)
                with open(path, 'w', encoding='utf-8') as f:
                    for e in events:
                        f.write(json.dumps(e) + '\n')
                stamp = time.time() - age
                os.utime(path, (stamp, stamp))
            write('Journal.2026-11-01T100000.01.log',
                  [{'event': 'Powerplay', 'Power': 'Yuri Grom', 'timestamp': '2026-11-01T10:00:00Z'}], 200)
            write('Journal.2026-11-20T100000.01.log',
                  [{'event': 'Powerplay', 'Power': 'Yuri Grom', 'timestamp': '2026-11-20T10:00:00Z'},
                   {'event': 'PowerplayDefect', 'ToPower': 'Aisling Duval', 'timestamp': '2026-11-20T11:00:00Z'}], 100)
            write('Journal.2026-11-22T100000.01.log', [{'event': 'FSDJump', 'StarSystem': 'Sol'}], 10)
            parser = JournalParser.__new__(JournalParser)
            parser.journal_dir = tmp
            self.assertEqual(parser.latest_pledged_power(), ('Aisling Duval', '2026-11-20T11:00:00Z'))
            self.assertIsNone(parser.latest_pledged_power(max_files=1))


class ApplyPledgeTests(unittest.TestCase):
    """_apply_journal_pledge from main.py, run without the app."""

    def setUp(self):
        import ast
        tree = ast.parse((ROOT / 'app' / 'main.py').read_text(encoding='utf-8-sig'))
        app_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'App')
        method = next(n for n in app_cls.body if isinstance(n, ast.FunctionDef) and n.name == '_apply_journal_pledge')
        module = ast.Module(body=[ast.ClassDef(name='Harness', bases=[], keywords=[], decorator_list=[], body=[method])],
                            type_ignores=[])
        ast.fix_missing_locations(module)
        from journal_parser import JournalParser
        ns = {'JournalParser': JournalParser, 'log': Mock()}
        exec(compile(module, 'main.py', 'exec'), ns)
        self.cfg = {'player_power': 'Yuri Grom', 'player_power_journal_time': '2026-11-20T10:00:00Z'}
        self.patches = [
            patch('config.load_player_power', lambda: self.cfg.get('player_power', '')),
            patch('config.save_player_power', lambda p: self.cfg.__setitem__('player_power', p)),
            patch('config.load_player_power_journal_time', lambda: self.cfg.get('player_power_journal_time', '')),
            patch('config.save_player_power_journal_time', lambda ts: self.cfg.__setitem__('player_power_journal_time', ts)),
        ]
        for p in self.patches:
            p.start()
        self.app = ns['Harness']()
        self.app.sysfinder_my_power_var = Var('Yuri Grom')
        self.app._sysfinder_option_label = lambda v: 'PROMPT' if v == 'Select your pledge...' else v
        self.app.ring_finder = Mock()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_newer_event_updates_everywhere(self):
        self.app._apply_journal_pledge('Aisling Duval', '2026-11-23T09:00:00Z')
        self.assertEqual(self.cfg['player_power'], 'Aisling Duval')
        self.assertEqual(self.app.sysfinder_my_power_var.value, 'Aisling Duval')
        self.app.ring_finder._mm_sync_power.assert_called_once()

    def test_already_applied_event_keeps_manual_pick(self):
        self.cfg['player_power'] = 'Zemina Torval'  # picked by hand after that login
        self.app._apply_journal_pledge('Yuri Grom', '2026-11-20T10:00:00Z')
        self.assertEqual(self.cfg['player_power'], 'Zemina Torval')
        self.app.ring_finder._mm_sync_power.assert_not_called()

    def test_leave_shows_prompt(self):
        self.app._apply_journal_pledge('Not pledged', '2026-11-23T09:00:00Z')
        self.assertEqual(self.cfg['player_power'], 'Not pledged')
        self.assertEqual(self.app.sysfinder_my_power_var.value, 'PROMPT')

if __name__ == '__main__':
    unittest.main()
