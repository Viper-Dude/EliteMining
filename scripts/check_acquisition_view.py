"""Window-free checks for the Hotspots Finder Acquisition view."""
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from acquisition_view import AcquisitionMixin, _OverlayStatus  # noqa: E402
from best_minerals_view import BestMineralsMixin  # noqa: E402
from system_finder_api import SystemFinderAPI  # noqa: E402
from ui.search_control import SearchControl  # noqa: E402


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Control:
    """Runs completion callbacks straight away, like SearchControl on the UI thread."""
    def __init__(self):
        self.running = False

    def is_cancelled(self):
        return False

    def complete(self, rows, callback):
        callback(rows)


class View(AcquisitionMixin, BestMineralsMixin):
    pass


def make_view(system=''):
    v = View()
    v._acq = {'system': system, 'state': '', 'radius': None, 'mineral': None, 'busy': False,
              'status': '', 'hint': '', 'spin': 0, 'spinning': True,
              'system_by_row': {}, 'station_by_row': {}, 'source_by_row': {}}
    v._acq_all_label = 'All Minerals'
    v._acq_mineral_var = Var('All Minerals')
    v._acq_control = Mock(running=False)
    v._acq_fill = Mock()
    v._acq_refresh_controls = Mock()
    v._results_view_var = Var('hotspots')
    v.status_var = Mock()
    v.system_var = Var('')
    v.results_tree = Mock()
    v.results_tree.selection.return_value = ()
    v.results_tree.get_children.return_value = ()
    v._format_material_for_display = lambda m: m
    v._to_english = lambda m: m
    return v


ROW = ('1.0', '0', 'Sol', '2 A Ring', '0', '0', 'Metallic', 'Pristine', 'Painite (3)')


class WorkerTests(unittest.TestCase):
    def test_not_eligible_clears_table_and_names_state(self):
        v = make_view('Sol')
        with patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value={'Sol': {'power_state': 'Exploited'}}), \
                patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_systems', return_value={}), \
                patch.object(SystemFinderAPI, '_store_powerplay_batch'):
            v._acquisition_search_worker('Sol', None, Control())
        self.assertIn('Exploited', v._acq['hint'])
        self.assertIn('Sol', v._acq['hint'])
        self.assertEqual(v._acq_fill.call_args.args[0], [])

    def test_no_power_data_says_so(self):
        v = make_view('Sol')
        with patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value={}), \
                patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_systems', return_value={}), \
                patch.object(SystemFinderAPI, '_store_powerplay_batch'):
            v._acquisition_search_worker('Sol', None, Control())
        self.assertNotEqual(v._acq['hint'], '')
        self.assertIn('Sol', v._acq['hint'])
        v._acq_fill.assert_called_once()

    def test_stronghold_uses_30_ly_and_keeps_only_buyers(self):
        v = make_view('Sol')
        v._acquisition_reference_materials = Mock(return_value=['Platinum'])
        render = v._show_acquisition_search_results = Mock()
        nearby = {'Buyer': {'distance': 5}, 'NoBuyer': {'distance': 3}}
        buyers = [{'systemName': 'Buyer', 'sellPrice': 250000, 'stationName': 'Port'}]
        with patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value={'Sol': {'power_state': 'Stronghold'}}), \
                patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_systems', return_value=nearby) as spansh, \
                patch.object(SystemFinderAPI, '_store_powerplay_batch'), \
                patch('marketplace_api.MarketplaceAPI.search_buyers', return_value=buyers):
            v._acquisition_search_worker('Sol', None, Control())
        self.assertEqual(spansh.call_args.args[1], 30.0)
        args = render.call_args.args
        self.assertEqual(args[2], 30.0)
        self.assertEqual([name for name, _ in args[3]], ['Buyer'])

    def test_results_without_candidates_show_hint(self):
        v = make_view('Sol')
        v._show_acquisition_search_results('Sol', 'Fortified', 20.0, [], 'Platinum', {}, {}, {})
        self.assertIn('20', v._acq['hint'])
        self.assertEqual(v._acq['state'], 'Fortified')
        self.assertEqual(v._acq['count'], 0)

    def test_results_fill_table_and_report_count(self):
        v = make_view('Sol')
        rows = [('Buyer', {'distance': 5})]
        v._show_acquisition_search_results('Sol', 'Fortified', 20.0, rows, None, {'Buyer': 1}, {}, {})
        self.assertEqual(v._acq['count'], 1)
        self.assertIs(v._acq_fill.call_args.args[0], rows)
        self.assertEqual(v._acq['radius'], 20.0)


class StartTests(unittest.TestCase):
    def start(self, v, system):
        with patch('acquisition_view.threading.Thread') as thread:
            v._acq_start(system)
        return thread

    def test_start_switches_view_and_runs_worker(self):
        v = make_view()
        thread = self.start(v, 'Sol')
        self.assertEqual(v._results_view_var.value, 'acquisition')
        v._acq_control.start.assert_called_once()
        self.assertEqual(thread.call_args.kwargs['args'][1:3], ('Sol', None))
        self.assertTrue(v._acq['busy'])
        self.assertEqual(v._acq_fill.call_args.args[0], [])  # no rows from the last system stay

    def test_new_system_resets_mineral_same_system_keeps_it(self):
        v = make_view('Sol')
        v._acq_mineral_var.set('Platinum')
        thread = self.start(v, 'sol')
        self.assertEqual(thread.call_args.kwargs['args'][2], 'Platinum')
        thread = self.start(v, 'LTT 4835')
        self.assertEqual(v._acq_mineral_var.value, 'All Minerals')
        self.assertIsNone(thread.call_args.kwargs['args'][2])

    def test_low_temp_diamonds_name(self):
        v = make_view()
        v._acq_mineral_var.set('Low Temp Diamonds')
        self.assertEqual(v._acq_mineral_filter(), 'Low Temperature Diamonds')

    def test_right_click_entry_uses_row_system(self):
        v = make_view()
        v._acq_start = Mock()
        v._find_acquisition_targets_for_system()
        v.status_var.set.assert_called_once()
        v._acq_start.assert_not_called()
        v.results_tree.selection.return_value = ('row1',)
        v.results_tree.item.return_value = ROW
        v._find_acquisition_targets_for_system()
        v._acq_start.assert_called_once_with('Sol')

    def test_refresh_stops_a_running_search(self):
        v = make_view('Sol')
        v._acq_start = Mock()
        v._acq_control.running = True
        v._acq_on_refresh()
        v._acq_control.stop.assert_called_once()
        v._acq_start.assert_not_called()
        v._acq_control.running = False
        v._acq_on_refresh()
        v._acq_start.assert_called_once_with('Sol')


class PowerAndMenuTests(unittest.TestCase):
    def test_row_eligibility_from_powerplay_cell(self):
        self.assertTrue(View._acq_row_eligible('Aisling Duval / Fortified (3d)'))
        self.assertTrue(View._acq_row_eligible('Zemina Torval / Stronghold'))
        self.assertTrue(View._acq_row_eligible('No data \u2197'))  # unknown: let the search decide
        self.assertTrue(View._acq_row_eligible(''))
        self.assertFalse(View._acq_row_eligible('Unoccupied (2d)'))
        self.assertFalse(View._acq_row_eligible('Zemina Torval / Exploited'))
        self.assertFalse(View._acq_row_eligible('Felicia Winters / Contested'))

    def test_worker_passes_controlling_power(self):
        v = make_view('Sol')
        v._acquisition_reference_materials = Mock(return_value=['Platinum'])
        render = v._show_acquisition_search_results = Mock()
        pp = {'Sol': {'power_state': 'Fortified', 'controlling_power': 'Zemina Torval'}}
        with patch.object(SystemFinderAPI, '_batch_get_powerplay', return_value=pp), \
                patch.object(SystemFinderAPI, '_fetch_spansh_powerplay_systems', return_value={}), \
                patch.object(SystemFinderAPI, '_store_powerplay_batch'):
            v._acquisition_search_worker('Sol', None, Control())
        self.assertEqual(render.call_args.args[8], 'Zemina Torval')

    def test_other_power_note_in_name(self):
        v = make_view('Sol')
        v._acq.update(state='Fortified', radius=20.0, count=2, owner='Zemina Torval')
        for my_power, shown in (('Aisling Duval', True), ('Zemina Torval', False),
                                ('Select your pledge...', False), ('Not pledged', False)):
            with patch('config.load_player_power', return_value=my_power):
                self.assertEqual('Zemina Torval' in v._acq_name_text(), shown, my_power)
        v._acq['owner'] = '~none~'
        with patch('config.load_player_power', return_value='Aisling Duval'):
            self.assertNotIn('~none~', v._acq_name_text())

    def test_start_keeps_mineral_handed_over(self):
        v = make_view('Sol')
        v._acq_mineral_combo = Mock()
        v._acq_mineral_combo.cget.return_value = ('All Minerals', 'Platinum')
        with patch('acquisition_view.threading.Thread') as thread:
            v._acq_start('LTT 4835', 'Platinum')
        self.assertEqual(thread.call_args.kwargs['args'][2], 'Platinum')
        with patch('acquisition_view.threading.Thread') as thread:
            v._acq_start('Wolf 359', 'Not a mineral')
        self.assertIsNone(thread.call_args.kwargs['args'][2])

    def test_hotspot_menu_groups_view_items(self):
        src = (ROOT / 'app' / 'ring_finder.py').read_text(encoding='utf-8')
        rank = src.index("add('rank_minerals', 'context_menu.best_minerals_to_mine'")
        acq = src.index("add('acquisition', 'context_menu.find_acquisition_targets'")
        self.assertLess(rank, acq)
        self.assertEqual(src[rank:acq].count('\n'), 1)  # the very next menu line
        self.assertIn("self._ctx_idx['acquisition'], state=", src)


class ViewClickTests(unittest.TestCase):
    def make(self, shown='', selected=None, reference=''):
        v = make_view(shown)
        v._acq_start = Mock()
        v._results_view_var = Var('acquisition')
        v.system_var = Var(reference)
        if selected:
            v.results_tree.selection.return_value = ('row1',)
            v.results_tree.item.return_value = selected
        v._rank_minerals_for_system = Mock()
        return v

    def test_selected_row_runs_for_its_system(self):
        v = self.make(shown='Other', selected=ROW)
        v._on_results_view_click()
        v._acq_start.assert_called_once_with('Sol')
        v._rank_minerals_for_system.assert_not_called()

    def test_shown_system_only_switches(self):
        v = self.make(shown='SOL', selected=ROW)
        v._on_results_view_click()
        v._acq_start.assert_not_called()

    def test_no_selection_uses_reference_spelling(self):
        v = self.make(shown='Sol', reference='ltt 4835')
        v.results_tree.get_children.return_value = ('r1',)
        v.results_tree.item.side_effect = lambda item, option=None: ('1.0', '0', 'LTT 4835', '2 A Ring')
        v._on_results_view_click()
        v._acq_start.assert_called_once_with('LTT 4835')

    def test_running_search_is_left_alone(self):
        v = self.make(shown='Other', selected=ROW)
        v._acq_control.running = True
        v._on_results_view_click()
        v._acq_start.assert_not_called()


class ApplyViewTests(unittest.TestCase):
    def make(self, view):
        v = BestMineralsMixin()
        v._results_view_var = Var(view)
        for name in ('_hotspots_tree_frame', '_bp_frame', '_acq_frame', '_columns_btn', '_more_btn'):
            setattr(v, name, Mock(name=name))
        v._results_status_label = None
        v._bp_close_extra_picker = Mock()
        with patch('config.scaled_px', side_effect=lambda n: n):
            v._apply_results_view()
        return v

    def shown(self, v):
        names = ('_hotspots_tree_frame', '_bp_frame', '_acq_frame', '_columns_btn', '_more_btn')
        return {n for n in names if getattr(v, n).pack.called}

    def test_acquisition_shows_only_its_frame_and_columns_button(self):
        v = self.make('acquisition')
        self.assertEqual(self.shown(v), {'_acq_frame'})  # its Columns button sits in its own row
        v._bp_close_extra_picker.assert_called_once()

    def test_best_prices_unchanged(self):
        v = self.make('best_prices')
        self.assertEqual(self.shown(v), {'_bp_frame'})
        v._bp_close_extra_picker.assert_not_called()

    def test_hotspots_unchanged(self):
        v = self.make('hotspots')
        self.assertEqual(self.shown(v), {'_hotspots_tree_frame', '_columns_btn', '_more_btn'})


class OutdatedResultTests(unittest.TestCase):
    def test_superseded_search_is_dropped(self):
        parent = Mock()
        parent.after.side_effect = lambda delay, fn, *args: fn(*args)
        button = Mock()
        button.cget.return_value = 'Refresh'
        control = SearchControl(parent, button, Mock())
        old, new = Mock(), Mock()
        control.start()
        generation_one = control._generation
        control.start()
        parent.after(0, control._finish, generation_one, [1], old, ())
        control.complete([2], new)
        old.assert_not_called()
        new.assert_called_once_with([2])

    def test_stop_message_lands_in_overlay(self):
        v = make_view('Sol')
        v._acq_update_overlay = Mock()
        _OverlayStatus(v).config(text='Search stopped')
        self.assertEqual(v._acq['hint'], 'Search stopped')
        v._acq_update_overlay.assert_called_once()


class StringsTests(unittest.TestCase):
    NEW = ('view_acquisition', 'acquisition_view_name', 'acquisition_view_empty', 'acquisition_search_found')
    REMOVED = ('acquisition_search_title', 'acquisition_search_reference_label',
               'acquisition_search_hint', 'acquisition_search_no_reference', 'acquisition_search_complete')

    def test_new_strings_in_both_languages_and_popup_strings_gone(self):
        for lang in ('en', 'de'):
            data = json.loads((ROOT / 'app' / 'localization' / f'strings_{lang}.json').read_text(encoding='utf-8'))
            for key in self.NEW:
                self.assertTrue(data['ring_finder'].get(key), (lang, key))
            for key in self.REMOVED:
                self.assertNotIn(key, data['ring_finder'], (lang, key))
        source = (ROOT / 'app' / 'acquisition_view.py').read_text(encoding='utf-8')
        for key in self.REMOVED:
            self.assertNotIn(key, source)


if __name__ == '__main__':
    unittest.main()
