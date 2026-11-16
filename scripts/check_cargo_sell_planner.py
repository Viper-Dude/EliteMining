import sys
import unittest
import tkinter as tk
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))

from cargo_sell_planner import CargoSellPlanner, build_plans, sale_cargo


def market(station, price, demand=100, distance=10, system='Sol', **kwargs):
    return dict(systemName=system, stationName=station, sellPrice=price, demand=demand,
                distance=distance, updatedAt='2026-11-15T12:00:00Z', **kwargs)


class CargoSellPlannerTests(unittest.TestCase):
    def setUp(self):
        self.preferences = {}
        load = patch('cargo_sell_planner._load_cfg', side_effect=lambda: {'sell_hold': self.preferences.copy()})
        save = patch('cargo_sell_planner.update_config_value', side_effect=lambda key, value: self.preferences.update(value))
        load.start()
        save.start()
        self.addCleanup(load.stop)
        self.addCleanup(save.stop)

    def test_missions_reserve_outstanding_not_uncollected(self):
        available, protected = sale_cargo({'Platinum': 100, 'Limpets': 20}, [
            {'commodity_raw': '$platinum_name;', 'count': 60, 'delivered': 10, 'collected': 100},
            {'commodity': 'Platinum', 'count': 20, 'delivered': 5},
        ])
        self.assertEqual(available, {'Platinum': 35})
        self.assertEqual(protected, {'Platinum': 65})

    def test_mission_reservation_cannot_exceed_cargo(self):
        self.assertEqual(sale_cargo({'Painite': 5}, [{'commodity': 'Painite', 'count': 20}]),
                         ({}, {'Painite': 5}))

    def test_quantity_weighted_one_stop(self):
        plans = dict(build_plans({'Platinum': 100, 'Gold': 1}, [
            ('Platinum', [market('A', 100), market('B', 90)]),
            ('Gold', [market('A', 10), market('B', 500)]),
        ]))
        self.assertEqual(plans['one_stop']['total'], 10010)
        self.assertEqual(plans['one_stop']['stops'][0]['info']['stationName'], 'A')
        self.assertEqual(plans['two_stops']['total'], 10500)

    def test_split_sales_respect_demand_without_double_counting(self):
        plans = dict(build_plans({'Platinum': 100}, [
            ('Platinum', [market('A', 100, 40), market('B', 90, 70)]),
        ]))
        plan = plans['two_stops']
        self.assertEqual(plan['total'], 9400)
        self.assertEqual(plan['sold'], 100)
        self.assertEqual(plan['unsold'], 0)
        self.assertEqual(sum(s['quantity'] for s in plan['sales']), 100)

    def test_partial_sales_are_explicit(self):
        plans = dict(build_plans({'Gold': 100, 'Silver': 20}, [('Gold', [market('A', 10, 30)])]))
        self.assertEqual(plans['one_stop']['unsold'], 90)
        self.assertNotIn('two_stops', plans)

    def test_best_payout_is_not_most_tonnage(self):
        plans = dict(build_plans({'Gold': 100, 'Platinum': 1}, [
            ('Gold', [market('A', 10)]), ('Platinum', [market('B', 10000)]),
        ]))
        self.assertEqual(plans['one_stop']['total'], 10000)
        self.assertEqual(plans['one_stop']['unsold'], 100)

    def test_quick_sale_uses_nearest_complete_option(self):
        plans = dict(build_plans({'Gold': 100}, [('Gold', [
            market('A', 100, distance=100), market('B', 90, distance=10), market('C', 120, 5, 1),
        ])]))
        self.assertEqual(plans['quick_sale']['stops'][0]['info']['stationName'], 'B')

    def test_two_stop_route_uses_coordinates(self):
        plans = dict(build_plans({'Gold': 100}, [('Gold', [
            market('A', 100, 40, 10, 'Alpha', systemX=0, systemY=0, systemZ=0),
            market('B', 90, 60, 12, 'Beta', systemX=3, systemY=4, systemZ=0),
        ])]))
        self.assertEqual(plans['two_stops']['distance'], 15)
        self.assertEqual(plans['two_stops']['legs'], [10, 5])

    def test_unknown_route_is_not_zero(self):
        plans = dict(build_plans({'Gold': 100}, [('Gold', [
            market('A', 100, 40, system='Alpha'), market('B', 90, 60, system='Beta'),
        ])]))
        self.assertIsNone(plans['two_stops']['distance'])
        self.assertEqual(plans['two_stops']['legs'], [10, None])

    def test_empty_results(self):
        self.assertEqual(build_plans({'Gold': 100}, [('Gold', [])]), [])

    def test_system_links_encode_names(self):
        with patch('webbrowser.open') as open_url:
            for site, prefix in (
                ('inara', 'https://inara.cz/elite/starsystem/?search='),
                ('edsm', 'https://www.edsm.net/en/system/id/0/name/'),
                ('spansh', 'https://spansh.co.uk/search/'),
            ):
                CargoSellPlanner._open_system('Col 285 Sector', site)
                open_url.assert_called_with(prefix + 'Col%20285%20Sector')

    def test_cargo_uses_selected_reference_system(self):
        tab = CargoSellPlanner.__new__(CargoSellPlanner)
        tab.app = SimpleNamespace(
            cargo_monitor=SimpleNamespace(current_system='', cargo_items={'Platinum': 43, 'Osmium': 4}),
            get_current_system=lambda: 'Wregoe MD-K d8-19')
        tracker = SimpleNamespace(get_active_missions=lambda: [])
        tab.system_var = SimpleNamespace(get=lambda: ' Wregoe MD-K d8-19 ')
        with patch('mining_missions.get_mission_tracker', return_value=tracker):
            self.assertEqual(tab._cargo(), ('Wregoe MD-K d8-19', {'Platinum': 43, 'Osmium': 4}, {}))

    def test_tab_keeps_results_when_cargo_changes_during_mining(self):
        root = tk.Tk()
        root.withdraw()
        try:
            root.marketplace_large_pad_only = tk.BooleanVar(root, False)
            root.marketplace_max_age = tk.StringVar(root, '2 days')
            root.market_mining_status_label = tk.Label(root, text='Market API', fg='gray', bg='#1e1e1e')
            root._age_map = {'2 days': '2 days'}
            root._age_rev_map = {'2 days': '2 days'}
            root._age_order = ['2 days']
            root._commodity_map = {}
            root._scaled_font = lambda size, *style: ('Segoe UI', size, *style)
            root._scaled_px = lambda size: size
            root.get_current_system = lambda: 'Sol'
            frame = ttk.Frame(root)
            frame.pack(fill='both', expand=True)
            snapshot = ('Sol', {'Gold': 100}, {})
            with patch.object(CargoSellPlanner, '_cargo', return_value=snapshot):
                tab = CargoSellPlanner(frame, root)
                for tree in (tab.tree, tab.details):
                    import tkinter.font as tkfont
                    heading_font = tkfont.Font(font=root._scaled_font(9, 'bold'))
                    for col in tree['columns']:
                        self.assertGreaterEqual(tree.column(col, 'minwidth'),
                                                heading_font.measure(tree.heading(col, 'text')) + 24)
                self.assertEqual(tab.system_var.get(), 'Sol')
                tab.system_var.set('Achenar')
                tab._use_current_system()
                self.assertEqual(tab.system_var.get(), 'Sol')
                tab.radius.set('250')
                tab.large.set(True)
                tab.carriers.set(False)
                self.assertEqual(self.preferences['radius'], '250')
                self.assertTrue(self.preferences['large_pads'])
                self.assertFalse(self.preferences['exclude_carriers'])
                root.geometry('1100x800+-3000+-3000')
                root.deiconify()
                root.update()
                for combo in (tab.radius_combo, tab.age_combo):
                    combo.selection_range(0, 'end')
                    combo.event_generate('<<ComboboxSelected>>')
                    self.assertFalse(combo.selection_present())
                self.assertEqual(len(tab.tables_paned.panes()), 2)
                tab.tables_paned.sashpos(0, 180)
                self.assertEqual(tab.tables_paned.sashpos(0), 180)
                tab._save_layout()
                second_frame = ttk.Frame(root)
                second_tab = CargoSellPlanner(second_frame, root)
                self.assertEqual(second_tab.radius.get(), '250')
                self.assertTrue(second_tab.large.get())
                self.assertFalse(second_tab.carriers.get())
                self.assertEqual(second_tab.system_var.get(), 'Sol')
                plans = build_plans({'Gold': 100}, [('Gold', [market('A', 100)])])
                tab._complete(snapshot, plans)
                tab.select()
                self.assertEqual(len(tab.tree.get_children()), 2)
                self.assertEqual(len(tab.details.get_children()), 1)
                row = tab.details.get_children()[0]
                self.assertEqual(tab.details.set(row, 'leg_distance'), '10.0')
                tab.details.selection_set(row)
                tab.copy_system()
                self.assertEqual(root.clipboard_get(), 'Sol')
                self.assertEqual(tab._row_systems(tab.details, row), ['Sol'])
                plan_row = tab.tree.get_children()[0]
                original_stops = tab.plans[plan_row]['stops']
                tab.plans[plan_row]['stops'] = [
                    {'info': {'systemName': 'Sol'}}, {'info': {'systemName': 'Achenar'}}]
                self.assertEqual(tab._row_systems(tab.tree, plan_row), ['Sol', 'Achenar'])
                with patch.object(tab.tree, 'identify_region', return_value='cell'), \
                     patch.object(tab.tree, 'identify_row', return_value=plan_row), \
                     patch('webbrowser.open') as open_url:
                    tab._open_row_system(SimpleNamespace(x=10, y=30), tab.tree)
                    open_url.assert_called_once_with('https://inara.cz/elite/starsystem/?search=Sol')
                tab.plans[plan_row]['stops'] = original_stops
            with patch.object(CargoSellPlanner, '_cargo', return_value=('Sol', {'Gold': 50}, {})):
                tab._poll()
                self.assertEqual(len(tab.tree.get_children()), 2)
                self.assertEqual(len(tab.details.get_children()), 1)
                self.assertIn('last search', tab.status.cget('text'))
                tab._complete(snapshot, plans)
                tab.select()
                self.assertEqual(len(tab.tree.get_children()), 2)
                self.assertEqual(len(tab.details.get_children()), 1)
                self.assertIn('last search', tab.status.cget('text'))
                self.assertEqual(tab.snapshot, snapshot)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
