"""Window-free checks for the Hotspots Finder Best Prices view and Auto Prices."""
import ast
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

from best_minerals_view import BestMineralsMixin  # noqa: E402


def load_methods(filename, class_name, names):
    source = (ROOT / filename).read_text(encoding='utf-8-sig')
    tree = ast.parse(source)
    original = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == class_name)
    methods = [node for node in original.body
               if isinstance(node, ast.FunctionDef) and node.name in names]
    cls = ast.ClassDef(name=class_name, bases=[], keywords=[], body=methods, decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    namespace = dict(List=List, Dict=Dict, Optional=Optional, t=lambda key: key)
    exec(compile(module, filename, 'exec'), namespace)
    return namespace[class_name]


class Var:
    def __init__(self, value):
        self.value = value
        self.writes = 0

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        self.writes += 1


def make_view():
    view = BestMineralsMixin()
    view._bp_req = 0
    view._bp = {'system': '', 'results': [], 'picker': None}
    view.status_var = Mock()
    view.parent = Mock()
    view._show_best_prices = Mock()
    view.prefetch_prices_var = Var(True)
    return view


RESULTS = [('Painite', {'sellPrice': 400000, 'systemName': 'Sol'}, [])]


class AutoPricesTests(unittest.TestCase):
    def test_overlay_off_fills_and_switches_view(self):
        view = make_view()
        view.prices_overlay_var = Var(False)
        view._present_auto_prices('Sol', RESULTS, [], {})
        view._show_best_prices.assert_called_once()
        kwargs = view._show_best_prices.call_args.kwargs
        self.assertEqual(kwargs['req'], view._bp_req)
        self.assertNotIn('switch', kwargs)  # default switch=True

    def test_overlay_on_also_fills_view(self):
        view = make_view()
        view.prices_overlay_var = Var(True)
        overlay = Mock(overlay_enabled=True)
        view.prospector_panel = Mock()
        view.prospector_panel.main_app.text_overlay = overlay
        view.prospector_panel.main_app.auto_prices_overlay_duration = Var(15)
        view._in_sc_since_jump = True
        view._build_prices_overlay_text = Mock(return_value='text')
        view._present_auto_prices('Sol', RESULTS, [], {})
        view._show_best_prices.assert_called_once()
        overlay.show_message.assert_called_once()
        self.assertEqual(overlay.show_message.call_args.kwargs['duration_ms'], 15000)

    def test_overlay_skipped_after_drop_but_view_still_filled(self):
        view = make_view()
        view.prices_overlay_var = Var(True)
        overlay = Mock(overlay_enabled=True)
        view.prospector_panel = Mock()
        view.prospector_panel.main_app.text_overlay = overlay
        view.prospector_panel.main_app.auto_prices_overlay_duration = Var(20)
        view._in_sc_since_jump = False
        view._present_auto_prices('Sol', RESULTS, [], {})
        view._show_best_prices.assert_called_once()
        overlay.show_message.assert_not_called()

    def test_auto_prices_off_never_switches(self):
        view = make_view()
        view.prefetch_prices_var = Var(False)
        view.prices_overlay_var = Var(False)
        view._present_auto_prices('Sol', RESULTS, [], {})
        view._show_best_prices.assert_not_called()

    def test_auto_prices_only_runs_when_enabled(self):
        source = (ROOT / 'app' / 'ring_finder.py').read_text(encoding='utf-8-sig').splitlines()
        calls = [i for i, line in enumerate(source)
                 if re.search(r'self\._(present_auto_prices|prefetch_prices_new_system)\(', line)
                 and 'def ' not in line]
        self.assertTrue(calls)
        for i in calls:
            window = '\n'.join(source[max(0, i - 6):i + 1])
            self.assertIn('prefetch_prices_var.get()', window, f'unguarded call at line {i + 1}')


class RequestTests(unittest.TestCase):
    def test_stale_fetch_is_dropped(self):
        view = make_view()
        old = view._bp_new_request()
        view._bp_new_request()
        view._finish_rank_request('Sol', RESULTS, [], {}, 'system', '', {}, old)
        view._show_best_prices.assert_not_called()

    def test_current_fetch_is_shown(self):
        view = make_view()
        req = view._bp_new_request()
        view._finish_rank_request('Sol', RESULTS, [], {}, 'ring', '2 A Ring', {}, req)
        view._show_best_prices.assert_called_once()
        self.assertEqual(view._show_best_prices.call_args.kwargs['ring_name'], '2 A Ring')

    def test_show_best_prices_ignores_stale_request(self):
        view = BestMineralsMixin()
        view._bp_req = 5
        view._bp = {'system': 'Old'}
        view._show_best_prices('New', RESULTS, req=4)
        self.assertEqual(view._bp['system'], 'Old')


class ViewSwitchTests(unittest.TestCase):
    def test_show_results_view_writes_only_on_change(self):
        view = BestMineralsMixin()
        view._results_view_var = Var('hotspots')
        view._show_results_view('hotspots')
        self.assertEqual(view._results_view_var.writes, 0)
        view._show_results_view('best_prices')
        self.assertEqual(view._results_view_var.value, 'best_prices')

    def test_manual_search_returns_to_hotspots(self):
        cls = load_methods('app/ring_finder.py', 'RingFinder', {'_on_search_btn_clicked'})
        finder = cls()
        order = []
        finder._search_in_progress = False
        finder._show_results_view = lambda view: order.append(view)
        finder.search_hotspots = lambda: order.append('search')
        finder._on_search_btn_clicked()
        self.assertEqual(order, ['hotspots', 'search'])

    def test_stop_click_keeps_view(self):
        cls = load_methods('app/ring_finder.py', 'RingFinder', {'_on_search_btn_clicked'})
        finder = cls()
        finder._search_in_progress = True
        finder._search_generation = 1
        finder._show_results_view = Mock()
        finder._reset_search_button = Mock()
        finder._update_new_entries_label = Mock()
        finder._on_search_btn_clicked()
        finder._show_results_view.assert_not_called()


class BestPricesClickTests(unittest.TestCase):
    def make(self, selected_values, shown_system='Sol', shown_ring='', busy=False, view='best_prices', reference='Sol'):
        view_obj = BestMineralsMixin()
        view_obj.system_var = Var(reference)
        view_obj._results_view_var = Var(view)
        view_obj._bp = {'system': shown_system, 'ring_name': shown_ring, 'busy': busy}
        view_obj.results_tree = Mock()
        view_obj.results_tree.selection.return_value = ('row1',) if selected_values else ()
        view_obj.results_tree.item.return_value = selected_values
        view_obj.results_tree.get_children.return_value = ()
        view_obj._rank_minerals_for_system = Mock()
        return view_obj

    ROW = ('1.0', '0', 'Sol', '2 A Ring', '0', '0', 'Metallic', 'Pristine', 'Painite (3)')

    def test_selected_other_ring_loads_it(self):
        v = self.make(self.ROW, shown_system='Sol', shown_ring='')  # Auto Prices showed the whole system
        v._on_results_view_click()
        v._rank_minerals_for_system.assert_called_once_with('ring')

    def test_ring_already_shown_only_switches(self):
        v = self.make(self.ROW, shown_system='Sol', shown_ring='2 A Ring')
        v._on_results_view_click()
        v._rank_minerals_for_system.assert_not_called()

    def test_no_selection_keeps_current_prices(self):
        v = self.make((), shown_system='Sol', reference='sol ')
        v._on_results_view_click()
        v._rank_minerals_for_system.assert_not_called()

    def test_no_selection_new_reference_loads_its_prices(self):
        v = self.make((), shown_system='Sol', reference='LTT 4835')
        v._on_results_view_click()
        v._rank_minerals_for_system.assert_called_once_with('system', system_name='LTT 4835')

    def test_typed_reference_uses_saved_spelling(self):
        v = self.make((), shown_system='Sol', reference='ltt 4835')
        v.results_tree.get_children.return_value = ('r1', 'r2')
        rows = {'r1': ('1.0', '0', 'Wregoe AB-C d1', '1 A Ring'), 'r2': ('2.0', '0', 'LTT 4835', '2 A Ring')}
        v.results_tree.item.side_effect = lambda item, option=None: rows[item]
        v._on_results_view_click()
        v._rank_minerals_for_system.assert_called_once_with('system', system_name='LTT 4835')

    def test_reference_without_hotspots_clears_old_prices(self):
        v = BestMineralsMixin()
        v._rank_minerals_inputs = Mock(return_value=None)
        v._bp_clear = Mock()
        v._rank_minerals_for_system('system', system_name='Wregoe AB-C d1')
        v._bp_clear.assert_called_once()
        self.assertIn('Wregoe AB-C d1', v._bp_clear.call_args.args[0])

    def test_hotspots_click_and_busy_do_nothing(self):
        for kwargs in ({'view': 'hotspots'}, {'busy': True}):
            v = self.make(self.ROW, shown_system='Other', **kwargs)
            v._on_results_view_click()
            v._rank_minerals_for_system.assert_not_called()


class AutoReturnTests(unittest.TestCase):
    def make(self, return_on=True, last_activity=0.0):
        v = BestMineralsMixin()
        v._bp_req = 3
        v.prices_return_var = Var(return_on)
        v._results_view_var = Var('best_prices')
        v.prospector_panel = Mock()
        v.prospector_panel.main_app._last_ui_activity = last_activity
        return v

    def test_returns_when_app_left_alone(self):
        v = self.make(last_activity=10.0)
        v._auto_return_to_hotspots(3, shown_at=20.0)
        self.assertEqual(v._results_view_var.value, 'hotspots')

    def test_stays_when_app_used_after_prices_appeared(self):
        v = self.make(last_activity=25.0)
        v._auto_return_to_hotspots(3, shown_at=20.0)
        self.assertEqual(v._results_view_var.value, 'best_prices')

    def test_stays_when_toggle_off(self):
        v = self.make(return_on=False)
        v._auto_return_to_hotspots(3, shown_at=20.0)
        self.assertEqual(v._results_view_var.value, 'best_prices')

    def test_stays_when_other_prices_replaced_them(self):
        v = self.make()
        v._auto_return_to_hotspots(2, shown_at=20.0)
        self.assertEqual(v._results_view_var.value, 'best_prices')

    def test_auto_prices_schedules_return_with_display_time(self):
        v = make_view()
        v.prices_overlay_var = Var(False)
        v.prospector_panel = Mock()
        v.prospector_panel.main_app.auto_prices_overlay_duration = Var(30)
        v._schedule_auto_return = Mock()
        v._present_auto_prices('Sol', RESULTS, [], {})
        v._schedule_auto_return.assert_called_once_with(v._bp_req, 30000)

    def test_new_schedule_cancels_previous_timer(self):
        v = BestMineralsMixin()
        v.parent = Mock()
        v.parent.after.side_effect = ['id1', 'id2']
        v._schedule_auto_return(1, 20000)
        v._schedule_auto_return(2, 20000)
        v.parent.after_cancel.assert_called_once_with('id1')


class InputsTests(unittest.TestCase):
    def test_system_scope_works_without_selection(self):
        view = BestMineralsMixin()
        view.results_tree = Mock()
        view.results_tree.selection.return_value = ()
        view.status_var = Mock()
        view.user_db = Mock()
        view.user_db.get_system_hotspots.return_value = [{'material_name': 'Painite', 'ring_type': 'Metallic'}]
        view._expand_abbreviated_materials = lambda m: m
        view.NON_HOTSPOT_RING_MINERALS = {'Metallic': ['Osmium']}
        result = view._rank_minerals_inputs('system', system_name='Sol')
        self.assertIsNotNone(result)
        self.assertEqual(result[0], 'Sol')
        self.assertIn('Painite', result[1])
        view.results_tree.selection.assert_not_called()

    def test_ring_scope_still_needs_selection(self):
        view = BestMineralsMixin()
        view.results_tree = Mock()
        view.results_tree.selection.return_value = ()
        view.status_var = Mock()
        self.assertIsNone(view._rank_minerals_inputs('ring', system_name='Sol'))


class AddMineralsBoxTests(unittest.TestCase):
    """The Add Minerals dropdown-style box and its borderless checklist, on a real Tk root."""
    def setUp(self):
        import tkinter as tk
        from tkinter import ttk
        self.root = tk.Tk()
        self.root.withdraw()
        frame = ttk.Frame(self.root)
        frame.pack()
        v = BestMineralsMixin()
        v.parent = self.root
        v._bp_frame = frame
        v._bp = {'picker': None, 'extra_candidates': ['Osmium', 'Rutile'], 'extra_vars': {}, 'results': []}
        v._bp_extra_text = tk.StringVar(value='+ Add Minerals')
        v._bp_extra_btn = ttk.Combobox(frame, textvariable=v._bp_extra_text, state='readonly', values=())
        v._bp_extra_btn.pack()
        v._format_material_for_display = lambda m: m
        v._bp_sync_extra_vars()
        self.view = v

    def tearDown(self):
        self.root.destroy()

    def test_click_opens_and_closes_the_checklist(self):
        v = self.view
        self.assertEqual(v._bp_on_extra_click(), 'break')
        picker = v._bp['picker']
        self.assertTrue(picker.winfo_exists())
        self.assertTrue(picker.overrideredirect())  # no window title bar or Close button
        v._bp_on_extra_click()
        self.assertIsNone(v._bp['picker'])

    def test_disabled_box_does_not_open(self):
        v = self.view
        v._bp_extra_btn.configure(state='disabled')
        self.assertEqual(v._bp_on_extra_click(), 'break')
        self.assertIsNone(v._bp['picker'])

    def test_label_counts_ticked_minerals(self):
        v = self.view
        v._bp['extra_vars']['Osmium'].set(True)
        v._bp_refresh_extra_label()
        self.assertEqual(v._bp_extra_text.get(), '+ Add Minerals (1)')
        v._bp['extra_vars']['Osmium'].set(False)
        v._bp_refresh_extra_label()
        self.assertEqual(v._bp_extra_text.get(), '+ Add Minerals')


if __name__ == '__main__':
    unittest.main()
