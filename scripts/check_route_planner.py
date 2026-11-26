"""Check route planning with mocked Spansh requests and a temporary config."""

import json
from concurrent.futures import CancelledError
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))


def setUpModule():
    global CargoMonitor, t, route, ShipRouteTab, UserDatabase, VAProcessManager
    global FleetCarrierRouteTab, FleetCarrierTracker, JournalParser

    if __package__:
        from .route_check_config import isolated_route_config
    else:
        from route_check_config import isolated_route_config

    unittest.enterModuleContext(isolated_route_config())
    from localization import init, t
    init(language="en")

    from cargo_monitor import CargoMonitor
    from fleet_carrier_route_tab import FleetCarrierRouteTab
    from fleet_carrier_tracker import FleetCarrierTracker
    from journal_parser import JournalParser
    import route_planner as route
    from route_tab import ShipRouteTab
    from user_database import UserDatabase
    from va_process_manager import VAProcessManager


LOADOUT = {
    "event": "Loadout",
    "Ship": "lakonminer",
    "UnladenMass": 600.725058,
    "FuelCapacity": {"Main": 32, "Reserve": 0.6},
    "Modules": [{
        "Slot": "FrameShiftDrive",
        "Item": "int_hyperdrive_overcharge_size5_class5",
        "Engineering": {"Modifiers": [{"Label": "FSDOptimalMass", "Value": 1997.514343}]},
    }],
}
STOPS = [
    {"id64": "10477373803", "name": "Sol"},
    {"id64": "1", "name": "Intermediate"},
    {"id64": "3657466647274", "name": "Paesia"},
]
CARRIER_STOPS = [
    {**STOPS[0], "distance": 0, "distance_to_destination": 169.76, "fuel_in_tank": 30,
     "fuel_used": 0, "tritium_in_market": 0, "must_restock": 1, "restock_amount": 30,
     "has_icy_ring": False, "is_system_pristine": False, "is_desired_destination": 1,
     "x": 0, "y": 0, "z": 0},
    {**STOPS[2], "distance": 169.76, "distance_to_destination": 0, "fuel_in_tank": 0,
     "fuel_used": 30, "tritium_in_market": 0, "must_restock": 0, "restock_amount": 0,
     "has_icy_ring": True, "is_system_pristine": True, "is_desired_destination": 1,
     "x": 107.59375, "y": -15.0625, "z": 130.4375},
]
FIXTURES = Path(__file__).with_name("fixtures")


class ShipChecks(unittest.TestCase):
    def test_jump_ranges(self):
        for fuel, cargo, expected in [(5.2, 0, 38.03), (32, 0, 36.42),
                                      (32, 144, 29.67), (32, 344, 23.6)]:
            with self.subTest(fuel=fuel, cargo=cargo):
                self.assertAlmostEqual(route.jump_range(LOADOUT, fuel, cargo), expected, delta=0.05)

    def test_slef_and_form(self):
        slef = [{"header": {"appName": "EliteMining", "appVersion": route.__version__},
                 "data": LOADOUT}]
        self.assertEqual(json.loads(route.build_slef(LOADOUT)), slef)
        expected = {
            "source": 10477373803, "destination": "Paesia", "cargo": 144,
            "is_supercharged": 0, "use_supercharge": 1, "exclude_secondary": 1,
            "refuel_every_scoopable": 1, "reserve_size": 0,
            "fuel_power": 2.45, "fuel_multiplier": 0.013, "optimal_mass": 1997.514343,
            "max_fuel_per_jump": 5.2, "base_mass": 601.325058, "tank_size": 32,
            "internal_tank_size": 0.6, "range_boost": "", "algorithm": "beam",
            "supercharge_multiplier": 4, "injection_multiplier": 2,
        }
        for mode, always, required in [(None, 0, 0), ("required", 0, 1), ("always", 1, 0)]:
            with self.subTest(injection_mode=mode):
                form = route.build_route_form(LOADOUT, 10477373803, "Paesia", 144, injection_mode=mode)
                self.assertEqual(json.loads(form.pop("ship_build")), slef)
                self.assertEqual(form, dict(expected, use_injections=always, use_injections_when_required=required))

    def test_normal_drive_engineering_and_guardian_booster(self):
        loadout = {**LOADOUT, "Modules": [
            {"Item": "int_guardianfsdbooster_size5", "On": True},
            {"Slot": "FrameShiftDrive", "Item": "Int_Hyperdrive_Size5_Class5",
             "Engineering": {"Modifiers": [{"Label": "MaxFuelPerJump", "Value": 6}]}},
        ]}
        spec = route.fsd_spec(loadout)
        self.assertEqual(spec["optimal_mass"], 1050)
        self.assertEqual(spec["max_fuel_per_jump"], 6)
        self.assertEqual(spec["range_boost"], 10.5)
        self.assertEqual(route.jump_range(loadout, 0, 0), 0)


class RouteDatabaseChecks(unittest.TestCase):
    def test_bulk_hotspots_sum_per_mineral_and_chunk_systems(self):
        db = UserDatabase.__new__(UserDatabase)
        db.db_path = ":memory:"
        conn = sqlite3.connect(db.db_path)
        self.addCleanup(conn.close)
        conn.execute("""
            CREATE TABLE hotspot_data (
                system_name TEXT, body_name TEXT, material_name TEXT,
                hotspot_count INTEGER, res_tag TEXT, overlap_tag TEXT
            )
        """)
        other_systems = [f"System {index}" for index in range(500)]
        conn.executemany("INSERT INTO hotspot_data VALUES (?, ?, ?, ?, ?, ?)", [
            ("Alpha", "A Ring", "Platinum", 2, None, None),
            ("Alpha", "B Ring", "Platinum", 3, None, None),
            ("Alpha", "A Ring", "Painite", 2, None, None),
            ("Alpha", "C Ring", "Painite", None, None, "Overlap"),
            ("Alpha", "A Ring", "Tritium", None, "RES", None),
            ("Alpha", "D Ring", "Monazite", 0, "RES", None),
            ("Alpha", "E Ring", "Void Opals", None, None, None),
            ("Unrequested", "A Ring", "Platinum", 5, None, None),
            *((system, "A Ring", "Tritium", 1, None, None) for system in other_systems),
        ])
        conn.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 500)

        with patch("user_database.sqlite3.connect", return_value=conn):
            result = db.bulk_get_hotspot_counts_for_systems(["Alpha", "Empty", *other_systems])

        self.assertEqual(result, {
            "Alpha": {"Platinum": 5, "Painite": 3, "Tritium": 1},
            **{system: {"Tritium": 1} for system in other_systems},
        })


class RouteTabChecks(unittest.TestCase):
    def test_carrier_table_loads_saved_layout_with_removed_restock_column(self):
        import config
        import tkinter as tk
        from tkinter import ttk

        layout = {
            "carrier_route_column_order": ["restock", "restock_amount", "system", "fuel_left"],
            "carrier_route_column_visibility": {"restock": True, "fuel_left": False},
            "carrier_route_column_widths": {"restock": 114, "restock_amount": 181},
        }
        folder = self.enterContext(tempfile.TemporaryDirectory())
        config_file = Path(folder) / "config.json"
        config_file.write_text(json.dumps(layout), encoding="utf-8")
        self.enterContext(patch.multiple(
            config, CONFIG_FILE=str(config_file), _cached_config={}, _cache_dirty=False,
            _last_load_time=0,
        ))

        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        tab = FleetCarrierRouteTab.__new__(FleetCarrierRouteTab)
        ttk.Frame.__init__(tab, root)
        tab.colors = {"bg": "#222222", "fg": "#ffffff"}
        tab._build_table()

        self.assertNotIn("restock", tab.tree["columns"])
        displayed = tab.tree["displaycolumns"]
        self.assertEqual(displayed[:2], ("restock_amount", "system"))
        self.assertNotIn("restock", displayed)
        self.assertNotIn("fuel_left", displayed)
        self.assertEqual(tab.tree.column("restock_amount", "width"), 181)

    def test_reverse_swaps_only_the_endpoints_in_both_plotters(self):
        import tkinter as tk

        for tab_class in (ShipRouteTab, FleetCarrierRouteTab):
            with self.subTest(tab=tab_class.__name__):
                tab = tab_class.__new__(tab_class)
                root = tk.Tcl()
                tab.source = tk.StringVar(root, "Sol")
                tab.destination = tk.StringVar(root)
                tab.reverse_button = Mock()
                tab.search = Mock(running=False)
                tab._autocomplete = [Mock(), Mock()]
                tab._plot_or_stop = Mock()
                for variable in (tab.source, tab.destination):
                    variable.trace_add("write", tab._update_reverse_button)

                tab._update_reverse_button()
                tab.reverse_button.configure.assert_called_with(state="disabled")
                tab.destination.set("Paesia")
                tab.reverse_button.configure.assert_called_with(state="normal")
                tab.search.running = True
                tab._update_reverse_button()
                tab.reverse_button.configure.assert_called_with(state="disabled")
                tab._reverse_route()
                self.assertEqual((tab.source.get(), tab.destination.get()), ("Sol", "Paesia"))

                tab.search.running = False
                tab._reverse_route()
                self.assertEqual((tab.source.get(), tab.destination.get()), ("Paesia", "Sol"))
                tab._plot_or_stop.assert_not_called()
                for autocomplete in tab._autocomplete:
                    autocomplete.hide.assert_called_once_with()

    def test_carrier_import_updates_endpoints_and_only_the_carrier_route(self):
        tab = FleetCarrierRouteTab.__new__(FleetCarrierRouteTab)
        tab.app = Mock()
        tab.notice = Mock()
        tab.search = Mock(running=False)
        tab.colors = {"error": "red"}
        tab.source, tab.destination = Mock(), Mock()
        tab._autocomplete = [Mock(), Mock()]
        tab._show_route = Mock()
        tab._sync_carrier_progress = Mock()
        tab.planner = route.RoutePlanner()
        tab.planner.set_route(STOPS, source_view="route")
        tab.planner.set_carrier_route(list(reversed(CARRIER_STOPS)))
        existing_ship_route = tab.planner.active_route
        existing_carrier_route = tab.planner.active_carrier_route

        with tempfile.TemporaryDirectory() as folder, \
             patch("route_table.filedialog.askopenfilename") as dialog, \
             patch("route_table.filedialog.asksaveasfilename") as save, \
             patch("route_table.centered_yesno_dialog", return_value=False) as confirm:
            path = Path(folder) / "carrier.csv"
            dialog.return_value = str(path)
            path.write_text(route.serialize_route(CARRIER_STOPS, ".csv", carrier=True), encoding="utf-8")
            tab._import_route()
            self.assertIs(tab.planner.active_carrier_route, existing_carrier_route)
            tab._show_route.assert_not_called()

            confirm.return_value = True
            tab._import_route()
            self.assertIs(tab.planner.active_route, existing_ship_route)
            self.assertEqual(tab.planner.active_carrier_route["stops"], CARRIER_STOPS)
            tab.source.set.assert_called_once_with("Sol")
            tab.destination.set.assert_called_once_with("Paesia")
            tab._show_route.assert_called_once_with(tab.planner.active_carrier_route)
            tab._sync_carrier_progress.assert_called_once_with()

            path = path.with_suffix(".json")
            save.return_value = str(path)
            tab._export_route()
            self.assertEqual(route.parse_route(path.read_text(encoding="utf-8"), ".json", carrier=True),
                             CARRIER_STOPS)

    def test_import_validates_file_before_confirming_replacement(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.app = Mock()
        tab.notice = Mock()
        tab.search = Mock(running=False)
        tab._show_route = Mock()
        tab._publish_route_progress = Mock()
        tab.colors = {"error": "red"}
        existing = {"stops": STOPS}
        tab.planner = Mock(active_route=existing)
        tab.planner.set_route.side_effect = lambda stops, source_view: setattr(
            tab.planner, "active_route", {"stops": stops, "source_view": source_view})

        with tempfile.TemporaryDirectory() as folder, \
             patch("route_table.filedialog.askopenfilename") as dialog, \
             patch("route_table.centered_yesno_dialog", return_value=False) as confirm:
            path = Path(folder) / "route.json"
            path.write_bytes(b"{bad json")
            dialog.return_value = str(path)
            tab._import_route()
            self.assertIs(tab.planner.active_route, existing)
            tab.app._show_notice.assert_called_once_with(tab.notice, t("route.import_failed"), fg="red")
            confirm.assert_not_called()

            path = path.with_suffix(".txt")
            path.write_text("Sol\nPaesia\n", encoding="utf-8-sig")
            dialog.return_value = str(path)
            tab._import_route()
            confirm.assert_called_once_with(tab.app, t("tabs.route"), t("route.replace"))
            self.assertIs(tab.planner.active_route, existing)
            tab.planner.set_route.assert_not_called()

            confirm.return_value = True
            tab._import_route()
            tab.planner.set_route.assert_called_once_with([{"name": "Sol"}, {"name": "Paesia"}],
                                                          source_view="import")
            tab._show_route.assert_called_once_with(tab.planner.active_route)
            tab._publish_route_progress.assert_called_once_with()

    def test_cargo_follows_the_hold_until_a_valid_edit(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.cargo = SimpleNamespace(current_cargo=144, max_cargo=344)
        tab.cargo_input = Mock()
        tab.cargo_input.get.return_value = "144"
        tab._cargo_edited = False
        tab._current_system = lambda: "Sol"
        tab._default_source = "Sol"
        tab._displayed_route = None
        tab.planner = SimpleNamespace(active_route=None)
        tab.after = Mock()
        tab._update_jump_range = Mock()

        tab.cargo.current_cargo = 150
        tab._refresh()
        tab.cargo_input.set.assert_called_once_with("150")
        self.assertEqual(tab._route_cargo(), 150)
        for invalid in ("-1", "345", "1.5", "cargo"):
            self.assertFalse(tab._validate_cargo(invalid))
            self.assertFalse(tab._cargo_edited)

        self.assertTrue(tab._validate_cargo("344"))
        tab._update_jump_range.assert_called_with(344)
        tab.cargo_input.get.return_value = "344"
        tab.cargo_input.set.reset_mock()
        tab.cargo.current_cargo = 160
        tab._refresh()
        tab.cargo_input.set.assert_not_called()
        self.assertEqual(tab._route_cargo(), 344)

        tab.cargo.max_cargo = 64
        tab._refresh()
        tab.cargo_input.set.assert_called_once_with("64")
        tab._update_jump_range.assert_called_with(64)
        self.assertTrue(tab._validate_cargo("0"))
        tab._update_jump_range.assert_called_with(0)

        tab.cargo_input.get.return_value = ""
        tab.cargo.current_cargo = 32
        self.assertTrue(tab._validate_cargo(""))
        self.assertFalse(tab._cargo_edited)
        self.assertEqual(tab._route_cargo(), 32)
        tab._update_jump_range.assert_called_with(32)
        tab.cargo_input.set.reset_mock()
        tab._refresh()
        tab.cargo_input.set.assert_not_called()

    def test_cockpit_uses_the_next_stop_after_the_planner_advances(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.app = Mock()
        tab.copy_after_jump = Mock(**{"get.return_value": True})
        tab._copy_system = Mock()
        with patch.object(route, "_load_cfg", return_value={}), patch.object(route, "update_config_value"):
            tab.planner = route.RoutePlanner()
            tab.planner.set_route(STOPS, "route")
            tab._publish_route_progress()
            tab.app._write_var_text.assert_any_call("routeNextSystem", STOPS[1]["name"])
            tab.app._write_var_text.assert_any_call("routeJumpsLeft", "2")
            tab._copy_system.assert_not_called()
            tab.app.text_overlay.show_message.assert_not_called()

            jump = [{"event": "FSDJump", "StarSystem": STOPS[1]["name"]}]
            tab.planner.handle_journal_events(jump)
            tab._on_journal_events(jump)
            next_system = STOPS[2]["name"]
            tab.app._write_var_text.assert_any_call("routeNextSystem", next_system)
            tab.app._write_var_text.assert_called_with("routeJumpsLeft", "1")
            tab._copy_system.assert_called_once_with(next_system)

            tab.copy_after_jump.get.return_value = False
            tab._on_journal_events(jump)
            tab._copy_system.assert_called_once()
            tab.app.text_overlay.show_message.assert_not_called()

            arrival = [{"event": "FSDJump", "StarSystem": next_system}]
            tab.planner.handle_journal_events(arrival)
            tab._on_journal_events(arrival)
            tab.app._write_var_text.assert_any_call("routeNextSystem", "")
            tab.app._write_var_text.assert_called_with("routeJumpsLeft", "0")

    def test_plot_next_in_game_uses_the_current_waypoint_file(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.app = Mock(vars_dir=str(Path("Development copy") / "Variables"))
        tab.planner = Mock(active_route={"stops": STOPS, "current_index": 0, "off_route": False})
        tab.after = Mock()
        with patch("route_tab.threading.Thread") as worker, \
             patch("route_tab.focus_game_window") as focus, \
             patch("route_tab.is_game_focused", return_value=True):
            tab._plot_next_in_game()
            focus.assert_called_once_with()
            worker.assert_not_called()
            delay, dispatch = tab.after.call_args.args
            self.assertGreater(delay, 0)
            dispatch()
            tab.app._write_var_text.assert_any_call("routeNextSystem", STOPS[1]["name"])
            expected_file = Path(tab.app.vars_dir) / "routeNextSystem.txt"
            worker.assert_called_once_with(target=tab._send_plot_waypoint, args=(expected_file,),
                                           daemon=True)
            worker.return_value.start.assert_called_once_with()

            worker.reset_mock()
            tab.planner.active_route["current_index"] = len(STOPS) - 1
            tab.app._write_var_text.reset_mock()
            tab._plot_next_in_game()
            worker.assert_not_called()
            tab.app._write_var_text.assert_not_called()

    def test_plot_next_in_game_waits_for_game_focus(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.app = Mock()
        tab.notice = Mock()
        tab.colors = {"warning": "yellow"}
        tab.planner = Mock(active_route={"stops": STOPS, "current_index": 0})
        with patch("route_tab.is_game_focused", return_value=False), \
             patch("route_tab.threading.Thread") as worker:
            tab._dispatch_plot_waypoint()
            worker.assert_not_called()
            tab.app._write_var_text.assert_not_called()
            tab.app._show_notice.assert_called_once_with(
                tab.notice, t("route.game_focus_required"), fg="yellow")

    def test_plot_next_in_game_reports_missing_voiceattack(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.app = Mock()
        tab.notice = Mock()
        tab.colors = {"warning": "yellow"}
        tab.after = lambda delay, callback: callback()
        with patch.object(VAProcessManager, "send_command", return_value=False) as send:
            waypoint_file = Path("Variables/routeNextSystem.txt")
            tab._send_plot_waypoint(waypoint_file)
            send.assert_called_once_with("Plot next waypoint", passed_text=str(waypoint_file))
            tab.app._show_notice.assert_called_once_with(
                tab.notice, t("route.voiceattack_required"), fg="yellow")

    def test_voiceattack_command_targets_the_running_executable(self):
        waypoint_file = str(Path("App With Spaces") / "Variables" / "routeNextSystem.txt")
        executable = Path("VoiceAttack 2") / "VoiceAttack.exe"
        other = Mock(info={"name": "Other.exe"})
        running = Mock(info={"name": "VoiceAttack.exe"}, **{"exe.return_value": str(executable)})
        with patch("va_process_manager.psutil.process_iter", return_value=[other, running]) as scan, \
             patch("va_process_manager.subprocess.Popen") as popen:
            self.assertTrue(VAProcessManager.send_command("Plot next waypoint", passed_text=waypoint_file))
            popen.assert_called_once()
            self.assertEqual(popen.call_args.args[0], [
                str(executable), "-command", "Plot next waypoint", "-PassedText", f'"{waypoint_file}"',
            ])
            other.exe.assert_not_called()

            popen.reset_mock()
            scan.return_value = [other]
            self.assertFalse(VAProcessManager.send_command("Plot next waypoint", passed_text=waypoint_file))
            popen.assert_not_called()

    def test_route_button_uses_override_and_other_views_use_live_cargo(self):
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.cargo = SimpleNamespace(latest_loadout=LOADOUT, current_cargo=144, max_cargo=344)
        tab.cargo_input = Mock()
        tab.cargo_input.get.return_value = "344"
        tab._cargo_edited = True
        tab._current_system = lambda: "Sol"
        tab.source = Mock()
        tab.source.get.return_value = "Sol"
        tab.destination = Mock()
        tab.destination.get.return_value = "Paesia"
        tab.search = Mock(running=False)
        tab.app = Mock()
        tab.notice = Mock()
        tab.planner = Mock(active_route=None, is_supercharged=False, plot_running=False)
        tab.injection_grade = Mock()
        tab.injection_grade.current.return_value = 0
        tab.injection_every_jump = Mock(**{"get.return_value": False})
        tab.use_supercharge = Mock(**{"get.return_value": True})
        tab._autocomplete = []
        tab._update_buttons = Mock()
        tab._wait_for_plot = Mock()
        tab._spin_plot_overlay = Mock()
        tab._plot_overlay = Mock()
        tab.focus_get = Mock(return_value=None)
        tab.colors = {"fg": "#000000"}

        tab._plot_or_stop()
        self.assertEqual(tab.planner.plot.call_args.args[0]["cargo"], 344)
        tab.plot_to_system("Paesia", source_view="market")
        self.assertEqual(tab.planner.plot.call_args.args[0]["cargo"], 144)

    def test_route_rows_show_required_injections_and_spansh_time(self):
        tab = Mock()
        tab.tree.get_children.return_value = ()
        stops = [
            {**STOPS[0], "must_refuel": True},
            {**STOPS[1], "distance": 20, "must_refuel": True, "must_inject": True},
            {**STOPS[2], "distance": 30, "must_inject": False},
        ]
        ShipRouteTab._show_route(tab, {"stops": stops, "current_index": 0, "off_route": False})
        rows = [call.kwargs["values"] for call in tab.tree.insert.call_args_list]
        self.assertEqual([values[5] for values in rows], ["", t("common.yes"), ""])
        tab.totals.configure.assert_called_with(text=t("route.totals").format(jumps=2, distance=50, minutes=4))

    def test_sol_distance_uses_stop_coordinates(self):
        tab = Mock()
        tab.tree.get_children.return_value = ()
        stops = [
            {**STOPS[0], "x": 0, "y": 0, "z": 0},
            {**STOPS[1], "x": 3, "y": 4, "z": 12},
            STOPS[2],
        ]

        ShipRouteTab._show_route(tab, {"stops": stops, "current_index": 0, "off_route": False})

        rows = [call.kwargs["values"] for call in tab.tree.insert.call_args_list]
        self.assertEqual([values[-4:] for values in rows], [
            ("", "", "0.00", ""), ("", "", "13.00", ""), ("", "", "", ""),
        ])

    def test_route_details_show_the_latest_mining_date_for_each_system(self):
        systems = ["Sol", "Paesia", "Unmined"]
        active = {"stops": [{"name": system} for system in systems]}
        tab = ShipRouteTab.__new__(ShipRouteTab)
        tab.planner = SimpleNamespace(active_route=active)
        tab._route_details_request = 0
        tab.tree = Mock()
        tab.after = lambda delay, callback, *args: callback(*args)
        panel = Mock()
        tab.app = SimpleNamespace(prospector_panel=panel)
        panel.get_last_mined_lookup.return_value = {
            ("SOL", "Sol 1 A Ring"): ("12/30/25 10:00", "2025-12-30T10:00:00"),
            ("SOL", "Sol 3 A Ring"): ("12/32/26 12:00", "invalid"),
            ("paesia", "Paesia 1 A Ring"): ("01/03/26 09:00", "2026-01-03T09:00:00"),
        }
        user_db = Mock()
        tab.cargo = SimpleNamespace(user_db=user_db)
        user_db.bulk_get_hotspot_counts_for_systems.return_value = {}
        user_db.bulk_get_reserve_levels_for_rings.return_value = {}
        user_db.bulk_get_ring_last_mined.return_value = {
            ("sol", "Sol 2 A Ring"): "01/02/26 09:00",
            ("Paesia", "Paesia 1 A Ring"): "01/01/26 10:00",
        }

        with patch("route_tab.threading.Thread") as worker:
            tab._load_route_details(active)
            worker.call_args.kwargs["target"]()

        self.assertEqual([args for args, _ in tab.tree.set.call_args_list if args[1] == "last_mined"], [
            ("0", "last_mined", "01/02/26 09:00"),
            ("1", "last_mined", "01/03/26 09:00"),
            ("2", "last_mined", ""),
        ])

    def test_injection_grade_applies_to_both_sale_legs(self):
        tab = Mock()
        tab.cargo.latest_loadout = LOADOUT
        tab.cargo.current_cargo = 144
        tab.planner.active_route = None
        tab.planner.is_supercharged = False
        tab.planner.plot_running = False
        tab._autocomplete = []
        tab.colors = {"fg": "#000000"}
        tab.use_supercharge.get.return_value = True

        for grade, every_jump, always, required, multiplier in [
            (0, False, 0, 0, 2),
            (0, True, 0, 0, 2),
            (1, False, 0, 1, 1.25),
            (2, False, 0, 1, 1.5),
            (3, False, 0, 1, 2),
            (1, True, 1, 0, 1.25),
            (2, True, 1, 0, 1.5),
            (3, True, 1, 0, 2),
        ]:
            with self.subTest(grade=grade, every_jump=every_jump):
                tab.injection_grade.current.return_value = grade
                tab.injection_every_jump.get.return_value = every_jump
                ShipRouteTab._plot(tab, "Sol", "Intermediate", second="Paesia", sold_first=104,
                               source_view="sell_hold")

                args, kwargs = tab.planner.plot.call_args
                for form, cargo in [(args[0], 144), (kwargs["second_form"], 40)]:
                    self.assertEqual(form["use_injections"], always)
                    self.assertEqual(form["use_injections_when_required"], required)
                    self.assertEqual(form["injection_multiplier"], multiplier)
                    self.assertEqual(form["cargo"], cargo)


class RouteStartupChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.cargo = CargoMonitor.__new__(CargoMonitor)
        self.cargo.journal_dir = folder.name
        self.cargo._lock = threading.Lock()
        self.cargo.last_journal_file = None
        self.cargo.latest_loadout = None
        self.cargo.ship_info_changed_callback = None
        self.cargo._update_ship_info = Mock()
        self.cargo.route_planner = SimpleNamespace(active_route=None, is_supercharged=False)

    def write_journal(self, day, *events):
        path = self.folder / f"Journal.2026-11-{day}T100000.01.log"
        path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        return path

    def test_main_menu_loadout_comes_from_the_latest_matching_journal(self):
        self.write_journal(21, {**LOADOUT, "Ship": "python"})
        self.write_journal(22, {**LOADOUT, "Ship": "asp"}, LOADOUT, {"event": "JetConeBoost"})
        self.write_journal(23, {"event": "Shutdown"})
        active = self.write_journal(24, {"event": "Music", "MusicTrack": "MainMenu"})

        self.cargo.start_journal_monitoring()

        self.assertEqual(self.cargo.latest_loadout, LOADOUT)
        self.assertEqual(self.cargo.last_journal_file, str(active))
        self.assertEqual(self.cargo.last_file_size, active.stat().st_size)
        self.assertFalse(self.cargo.route_planner.is_supercharged)
        self.assertEqual(route.build_route_form(self.cargo.latest_loadout, "Sol", "Paesia", 144)["tank_size"], 32)

        new_loadout = {**LOADOUT, "Ship": "python"}
        self.write_journal(25, new_loadout)
        self.cargo.start_journal_monitoring()
        self.assertEqual(self.cargo.latest_loadout, new_loadout)

    def test_range_uses_full_tank_only_when_status_has_no_fuel(self):
        self.cargo.latest_loadout = {**LOADOUT, "MaxJumpRange": 38.03}
        self.cargo.current_cargo = 144
        self.cargo.ship_name = ""
        self.cargo.ship_type = ""
        status_path = self.folder / "Status.json"
        self.cargo.status_json_path = str(status_path)
        tab = SimpleNamespace(cargo=self.cargo, ship_info_label=Mock(), range_label=Mock())
        for status, fuel in [({}, 32), ({"Fuel": {"FuelMain": 5.2}}, 5.2), ({"Fuel": {"FuelMain": 0}}, 0)]:
            with self.subTest(status=status):
                status_path.write_text(json.dumps(status), encoding="utf-8")
                self.cargo.last_status_mtime = 0
                self.cargo._check_status_for_ship_changes()
                ShipRouteTab._update_jump_range(tab, self.cargo.current_cargo)
                expected = route.jump_range(self.cargo.latest_loadout, fuel, self.cargo.current_cargo)
                tab.range_label.configure.assert_called_with(text=t("route.range").format(current=expected, maximum=38.03))


def response(status, payload):
    return Mock(status_code=status, **{"json.return_value": payload})


class PlotChecks(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.session = Mock(headers={})
        self.client = route.SpanshRouteClient(self.session)
        clock = patch.multiple(route.time, monotonic=lambda: self.now, sleep=self.sleep)
        clock.start()
        self.addCleanup(clock.stop)

        self.config = {}
        for patcher in (
            patch.object(route, "_load_cfg", side_effect=self.config.copy),
            patch.object(route, "update_config_value", side_effect=self.config.__setitem__),
            patch.object(route.requests, "Session"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        route.requests.Session.return_value.__enter__.return_value = self.session

    def sleep(self, duration):
        self.now += duration

    def test_post_and_poll_backoff(self):
        self.session.post.return_value = response(202, {"job": "abc"})
        times = []
        replies = iter([
            response(202, {"status": "queued"}),
            response(202, {"status": "queued"}),
            response(200, {"status": "ok", "result": {"jumps": STOPS}}),
        ])

        def get(*args, **kwargs):
            times.append(self.now)
            return next(replies)

        self.session.get.side_effect = get
        form = route.build_route_form(LOADOUT, "Sol", "Paesia", 144)
        job = self.client.start_plot(form)
        self.assertEqual(self.session.headers["User-Agent"], f"EliteMining/{route.__version__}")
        self.session.post.assert_called_once_with(f"{route._API}/generic/route", data=form, timeout=15)
        self.assertEqual(self.client.poll(job, lambda: False), STOPS)
        self.assertEqual(times, [2, 6, 14])
        self.assertTrue(all(call.args == (f"{route._API}/results/abc",)
                            for call in self.session.get.call_args_list))

    def test_cancel_during_wait(self):
        with self.assertRaises(CancelledError):
            self.client.poll("abc", lambda: self.now >= 0.3)
        self.session.get.assert_not_called()

    def test_timeout(self):
        self.session.get.return_value = response(202, {"status": "queued"})
        with self.assertRaises(TimeoutError):
            self.client.poll("abc", lambda: False)
        self.assertEqual(self.now, 120)

    def test_carrier_posts_names_or_known_ids_without_lookup(self):
        self.session.post.return_value = response(202, {"job": "carrier"})
        planner = route.RoutePlanner()
        for source, destination, expected_source, expected_destination in [
            (" Sol ", "Paesia", "Sol", "Paesia"),
            (10477373803, "Paesia", 10477373803, "Paesia"),
            ("Sol", "3657466647274", "Sol", "3657466647274"),
        ]:
            with self.subTest(source=source, destination=destination):
                self.session.reset_mock()
                self.session.get.side_effect = [
                    response(202, {"status": "queued"}),
                    response(200, {"status": "ok", "result": {"jumps": CARRIER_STOPS}}),
                ]
                future = planner.plot_carrier(source, destination, 4000, lambda: False)

                self.assertEqual(future.result(timeout=3), CARRIER_STOPS)
                self.assertEqual(self.session.get.call_args_list, [
                    call(f"{route._API}/results/carrier", timeout=15),
                    call(f"{route._API}/results/carrier", timeout=15),
                ])
                self.session.post.assert_called_once_with(f"{route._API}/fleetcarrier/route", data={
                    "source": expected_source, "destinations": [expected_destination],
                    "capacity": 25000, "mass": 25000, "capacity_used": 4000, "calculate_starting_fuel": 1,
                }, timeout=15)
        self.assertIsNone(planner.active_carrier_route)
        self.assertEqual(self.config, {})

    def test_carrier_posts_known_tank_fuel_including_zero(self):
        self.session.post.return_value = response(202, {"job": "carrier"})
        self.session.get.return_value = response(200, {"status": "ok", "result": {"jumps": CARRIER_STOPS}})
        planner = route.RoutePlanner()
        for fuel in (500, 0):
            with self.subTest(fuel=fuel):
                planner.plot_carrier("Sol", "Paesia", 4000, lambda: False, fuel_level=fuel).result(timeout=3)
                self.assertEqual(self.session.post.call_args.kwargs["data"], {
                    "source": "Sol", "destinations": ["Paesia"], "capacity": 25000,
                    "mass": 25000, "capacity_used": 4000, "calculate_starting_fuel": 0,
                    "fuel_loaded": fuel, "tritium_stored": 0,
                })

    def test_carrier_rejects_missing_or_identical_endpoints(self):
        planner = route.RoutePlanner()
        for source, destination, error in [
            ("Sol", " ", "endpoints are required"),
            ("Sol", " sOL ", "must be different"),
            (10477373803, "10477373803", "must be different"),
        ]:
            with self.subTest(source=source, destination=destination), self.assertRaisesRegex(ValueError, error):
                planner.plot_carrier(source, destination, 0, lambda: False)
        route.requests.Session.assert_not_called()

    def test_carrier_rejects_invalid_used_capacity(self):
        planner = route.RoutePlanner()
        for used_capacity in (None, -1, 25_001, 1.5, True):
            with self.subTest(used_capacity=used_capacity), self.assertRaisesRegex(ValueError, "used capacity"):
                planner.plot_carrier(10477373803, 3657466647274, used_capacity, lambda: False)
        route.requests.Session.assert_not_called()

    def test_carrier_plot_failures_preserve_both_routes(self):
        planner = route.RoutePlanner()
        planner.set_route(STOPS, "route")
        planner.set_carrier_route(CARRIER_STOPS)
        before = self.config.copy()
        refused = response(400, {"status": "error"})
        refused.raise_for_status.side_effect = route.requests.HTTPError("plot failed")
        accepted = response(202, {"job": "carrier"})
        for post_reply, poll_reply, error in [
            (refused, None, route.requests.HTTPError),
            (accepted, response(200, {"status": "ok", "result": {
                "incomplete": True, "jumps": CARRIER_STOPS[:1],
            }}), ValueError),
            (accepted, response(200, {"status": "ok", "result": {"jumps": [{}]}}), ValueError),
            (accepted, response(202, {"status": "queued"}), TimeoutError),
        ]:
            with self.subTest(error=error, reply=poll_reply):
                self.session.post.return_value = post_reply
                self.session.get.return_value = poll_reply
                future = planner.plot_carrier(10477373803, 3657466647274, 0, lambda: False)
                with self.assertRaises(error):
                    future.result(timeout=3)
                self.assertEqual(self.config, before)
                self.assertEqual(planner.active_carrier_route, before["active_carrier_route"])
                self.assertEqual(planner.active_route, before["active_route"])

    def test_carrier_cancel_before_post(self):
        planner = route.RoutePlanner()
        future = planner.plot_carrier("Sol", "Paesia", 0, lambda: True)
        with self.assertRaises(CancelledError):
            future.result(timeout=3)
        route.requests.Session.assert_not_called()
        self.assertEqual(self.config, {})

    def test_carrier_stop_keeps_ship_plot_blocked_until_worker_exits(self):
        planner = route.RoutePlanner()
        planner.set_carrier_route(CARRIER_STOPS)
        self.session.post.return_value = response(202, {"job": "carrier"})
        poll_entered = threading.Event()
        poll_release = threading.Event()
        cancelled = threading.Event()

        def poll(*args, **kwargs):
            poll_entered.set()
            if not poll_release.wait(3):
                raise TimeoutError()
            return response(200, {"status": "ok", "result": {"jumps": CARRIER_STOPS}})

        self.session.get.side_effect = poll
        ship_form = route.build_route_form(LOADOUT, "Sol", "Paesia", 144)
        future = planner.plot_carrier(10477373803, 3657466647274, 25000, cancelled.is_set)
        try:
            self.assertTrue(poll_entered.wait(3))
            with self.assertRaisesRegex(RuntimeError, "already running"):
                planner.plot(ship_form, lambda: False)
            cancelled.set()
            with self.assertRaisesRegex(RuntimeError, "already running"):
                planner.plot(ship_form, lambda: False)
        finally:
            poll_release.set()
        with self.assertRaises(CancelledError):
            future.result(timeout=3)
        self.session.post.assert_called_once()
        self.assertEqual(planner.active_carrier_route["stops"], CARRIER_STOPS)

        self.session.post.return_value = response(202, {"job": "ship"})
        self.session.get.side_effect = None
        self.session.get.return_value = response(200, {"status": "ok", "result": {"jumps": STOPS}})
        self.assertEqual(planner.plot(ship_form, lambda: False).result(timeout=3), STOPS)


class RouteFileChecks(unittest.TestCase):
    def test_spansh_fixtures_and_bare_json_list(self):
        json_text = (FIXTURES / "spansh_galaxy_plotter.json").read_text(encoding="utf-8-sig")
        json_stops = route.parse_route(json_text, ".json")
        csv_text = (FIXTURES / "spansh_galaxy_plotter.csv").read_text(encoding="utf-8-sig")
        csv_stops = route.parse_route(csv_text, ".txt")

        for stops in (json_stops, csv_stops):
            self.assertEqual(len(stops), 10)
            self.assertEqual((stops[0]["name"], stops[-1]["name"]), ("Wregoe XD-E b39-2", "Sol"))
        self.assertEqual(json_stops[-1]["id64"], "10477373803")
        self.assertTrue(all("id64" not in stop for stop in csv_stops))
        self.assertEqual(json_stops, route.parse_route(json.dumps(json_stops), ".json"))
        self.assertEqual(csv_stops[1]["fuel_in_tank"], 32)
        self.assertEqual(csv_stops[1]["fuel_used"], 4.98277187347412)
        self.assertTrue(csv_stops[1]["must_refuel"])
        for extension, stops in ((".json", json_stops), (".csv", csv_stops)):
            exported = route.parse_route(route.serialize_route(stops, extension), extension)
            for index, stop in enumerate(exported):
                remaining = sum(item["distance"] for item in stops[index + 1:])
                self.assertAlmostEqual(stop["distance_to_destination"], remaining)
                self.assertEqual(stop, dict(stops[index], distance_to_destination=stop["distance_to_destination"]))

    def test_export_round_trips_and_recalculates_joined_route(self):
        stops = [
            {"name": "Sol", "id64": "10477373803", "distance": 0, "distance_to_destination": 22},
            {"name": "Paesia", "distance": 22, "distance_to_destination": 0,
             "must_refuel": False, "has_neutron": True, "must_inject": 1.25},
            {"name": "Mikyll", "distance": 40, "distance_to_destination": 0},
        ]
        original = [stop.copy() for stop in stops]
        expected = [dict(stop, distance_to_destination=remaining)
                    for stop, remaining in zip(stops, (62, 40, 0))]

        json_text = route.serialize_route(stops, ".JSON")
        self.assertEqual(json.loads(json_text), {"result": {"jumps": expected},
                                                "status": "ok", "state": "completed"})
        self.assertEqual(route.parse_route(json_text, ".json"), expected)

        csv_text = route.serialize_route(stops, ".csv")
        fixture_header = (FIXTURES / "spansh_galaxy_plotter.csv").read_bytes().splitlines(keepends=True)[0]
        self.assertEqual(csv_text.encode("utf-8").splitlines(keepends=True)[0], fixture_header)
        self.assertIn('"Paesia","22","40","","","No","Yes","Yes"\n', csv_text)
        csv_expected = [dict(stop) for stop in expected]
        del csv_expected[0]["id64"]
        csv_expected[1]["must_inject"] = 1
        self.assertEqual(route.parse_route(csv_text, ".csv"), csv_expected)
        self.assertEqual(stops, original)

    def test_carrier_files_round_trip_and_reject_incomplete_routes(self):
        for extension in (".json", ".csv", ".txt"):
            with self.subTest(extension=extension):
                exported = route.serialize_route(CARRIER_STOPS, extension, carrier=True)
                expected = ([{"name": stop["name"]} for stop in CARRIER_STOPS]
                            if extension == ".txt" else CARRIER_STOPS)
                self.assertEqual(route.parse_route(exported, extension, carrier=True), expected)
        incomplete = json.dumps({"result": {"incomplete": True, "jumps": CARRIER_STOPS}})
        with self.assertRaises(ValueError):
            route.parse_route(incomplete, ".json", carrier=True)

    def test_plain_text_and_name_only_routes(self):
        stops = [{"name": "Sol"}, {"name": "Jackson's Lighthouse"}, {"name": "Wregoe XD-E b39-2"}]
        text = "\ufeffSol\r\n\r\n  Jackson's Lighthouse  \nWregoe XD-E b39-2\n"
        self.assertEqual(route.parse_route(text, ".txt"), stops)
        self.assertEqual(route.serialize_route(stops, ".txt"), "Sol\nJackson's Lighthouse\nWregoe XD-E b39-2\n")
        for extension in (".json", ".csv"):
            self.assertEqual(route.parse_route(route.serialize_route(stops, extension), extension), stops)

    def test_rejects_empty_and_invalid_files(self):
        csv_header = (FIXTURES / "spansh_galaxy_plotter.csv").read_text(encoding="utf-8").splitlines()[0]
        for extension, text in ((".txt", " \n"), (".txt", "{garbage!}"), (".txt", "Sol\x00"),
                                (".json", "{garbage!}"), (".json", "[]"),
                                (".json", '[{"name":"Sol","distance":"far"}]'),
                                (".csv", csv_header), (".csv", f'{csv_header}\n"Sol","bad"')):
            with self.subTest(extension=extension, text=text):
                with self.assertRaises(ValueError):
                    route.parse_route(text, extension)


class CarrierProgressChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.enterContext(patch("path_utils.get_app_data_dir", return_value=folder.name))
        self.parser = JournalParser(folder.name, user_db=Mock())
        self.folder = folder.name
        self.tracker = FleetCarrierTracker()
        self.tracker.set_journal_parser(self.parser)
        self.parser.process_carrier_event({"event": "CarrierStats", "CarrierID": 111, "FuelLevel": 896})
        self.departure = "2026-11-26T12:00:00Z"
        self.due = datetime.fromisoformat(self.departure).timestamp() + 300
        self.now = self.due - 900
        self.enterContext(patch.object(route.time, "time", side_effect=lambda: self.now))
        self.planner = route.RoutePlanner()
        self.planner.clear_route()
        self.planner.set_carrier_route(STOPS)
        self.legacy_callback = Mock()
        self.tracker.set_on_updated(self.legacy_callback)
        self.parser.finish_carrier_catchup()

    def request(self, name="Paesia", departure=None, **fields):
        self.event("CarrierJumpRequest", "11:56:00", SystemName=name,
                   DepartureTime=departure or self.departure, **fields)

    def event(self, kind, clock, **fields):
        self.parser.process_carrier_event({
            "CarrierID": 111, "event": kind, "timestamp": f"2026-11-26T{clock}Z", **fields,
        })

    def sync(self):
        before = deepcopy(self.tracker.carrier_data)
        file = Path(self.folder) / "last_carrier_data.json"
        save = file.read_bytes()
        delay = self.planner.sync_carrier_progress(self.tracker.route_snapshot())
        self.assertEqual(self.tracker.carrier_data, before)
        self.assertEqual(file.read_bytes(), save)
        return delay

    def assert_progress(self, index, *, off_route=False, applied=None):
        active = self.planner.active_carrier_route
        self.assertEqual((active["current_index"], active["off_route"]), (index, off_route))
        self.assertEqual(active.get("applied_request"), applied)

    def test_departure_plus_five_advances_and_saves_request_with_cursor(self):
        self.request()
        self.now = self.due - 1
        self.assertEqual(self.sync(), 1)
        self.assert_progress(0)
        self.now += 1
        self.assertIsNone(self.sync())
        self.assert_progress(2, applied={"destination": "Paesia", "departure_time": self.departure})
        import config
        config.flush_config()
        saved = json.loads(Path(config.CONFIG_FILE).read_text(encoding="utf-8"))
        self.assertEqual(saved["active_carrier_route"], self.planner.active_carrier_route)

    def test_cancellation_and_replacement_use_only_the_current_request(self):
        self.request()
        self.assertEqual(self.sync(), 900)
        self.event("CarrierJumpCancelled", "11:57:00")
        self.now = self.due
        self.assertIsNone(self.sync())
        self.assert_progress(0)
        self.request()
        replacement = "2026-11-26T12:20:00Z"
        self.request("Intermediate", replacement)
        self.assertEqual(self.sync(), 1200)
        self.now += 1200
        self.assertIsNone(self.sync())
        self.assert_progress(1, applied={"destination": "Intermediate", "departure_time": replacement})

    def test_arrival_before_timer_uses_system_address_and_resolves_request(self):
        self.request()
        self.assertIsNotNone(self.sync())
        self.event("CarrierJump", "12:01:00", StarSystem="Alternate spelling", SystemAddress=3657466647274)
        self.assertIsNone(self.sync())
        applied = {"destination": "Paesia", "departure_time": self.departure}
        self.assert_progress(2, applied=applied)
        self.assertIsNone(self.tracker.carrier_data["jump_destination"])

        self.request("Sol", "2026-11-26T12:20:00Z")
        self.event("CarrierJump", "12:01:00", StarSystem="Alternate spelling", SystemAddress=3657466647274)
        self.assertEqual(self.tracker.carrier_data["jump_destination"], "Sol")
        saved = self.planner.active_carrier_route
        self.assertIsNone(self.sync())
        self.assertIs(self.planner.active_carrier_route, saved)

    def test_later_confirmations_correct_the_same_cursor_and_restart_cannot_reapply(self):
        self.request()
        self.now = self.due
        self.sync()
        applied = {"destination": "Paesia", "departure_time": self.departure}
        self.event("CarrierLocation", "11:58:00", StarSystem="Sol")
        self.assertIsNone(self.sync())
        self.assert_progress(2, applied=applied)
        self.event("CarrierLocation", "12:06:00", StarSystem="Off-route", SystemAddress=999)
        self.assertIsNone(self.sync())
        self.assert_progress(2, off_route=True, applied=applied)
        self.event("CarrierLocation", "12:07:00", StarSystem="Off-route", SystemAddress=1)
        self.assertIsNone(self.sync())
        self.assert_progress(1, applied=applied)
        self.event("CarrierFinance", "12:08:00", CarrierBalance=5000)
        self.parser = JournalParser(self.folder, user_db=Mock())
        self.tracker.set_journal_parser(self.parser)
        self.planner = route.RoutePlanner()
        self.parser.finish_carrier_catchup()
        self.assertIsNone(self.sync())
        self.assert_progress(1, applied=applied)
        self.assertEqual(self.tracker.carrier_data["jump_destination"], "Paesia")

    def test_startup_catchup_resolves_pending_from_location_and_preserves_subscriber(self):
        self.request()
        self.parser = JournalParser(self.folder, user_db=Mock())
        self.tracker.set_journal_parser(self.parser)
        self.tracker.set_on_updated(self.legacy_callback)
        self.legacy_callback.reset_mock()
        on_route_update = Mock()
        self.tracker.set_on_route_updated(on_route_update)
        self.parser._suppress_carrier_notifications = True
        self.now = self.due + 100
        self.assertIsNone(self.sync())
        self.assert_progress(0)
        self.event("CarrierLocation", "12:02:00", StarSystem="Paesia")
        self.event("CarrierFinance", "12:03:00", CarrierBalance=5000)
        on_route_update.assert_not_called()
        self.legacy_callback.assert_not_called()
        self.parser._suppress_carrier_notifications = False
        self.parser._notify_carrier_updated()
        self.parser.finish_carrier_catchup()
        on_route_update.assert_called_once_with()
        self.legacy_callback.assert_called_once()
        self.assertIsNone(self.sync())
        self.assert_progress(2, applied={"destination": "Paesia", "departure_time": self.departure})

    def test_startup_catchup_can_advance_a_saved_request_without_arrival(self):
        self.request()
        self.parser = JournalParser(self.folder, user_db=Mock())
        self.tracker.set_journal_parser(self.parser)
        self.now = self.due
        self.assertIsNone(self.sync())
        self.assert_progress(0)
        self.parser.finish_carrier_catchup()
        self.assertIsNone(self.sync())
        self.assert_progress(2, applied={"destination": "Paesia", "departure_time": self.departure})

    def test_timer_cancellation_and_replacement_cancel_the_previous_tk_job(self):
        tab = object.__new__(FleetCarrierRouteTab)
        tab.planner, tab.tracker = self.planner, self.tracker
        tab._jump_job = None
        tab.after = Mock(side_effect=["original", "replacement"])
        tab.after_cancel = Mock()
        self.request()
        tab._sync_carrier_progress()
        tab.after.assert_called_with(900000, tab._jump_timer_fired)
        self.request("Intermediate", "2026-11-26T12:20:00Z")
        tab._sync_carrier_progress()
        tab.after_cancel.assert_called_once_with("original")
        tab.after.assert_called_with(2100000, tab._jump_timer_fired)
        self.event("CarrierJumpCancelled", "11:58:00")
        tab._sync_carrier_progress()
        tab.after_cancel.assert_called_with("replacement")
        self.assertIsNone(tab._jump_job)
        self.assertEqual(tab.after.call_count, 2)

    def test_foreign_and_squadron_events_never_move_the_carrier_route(self):
        self.request()
        for ownership in ({"CarrierID": 222}, {"CarrierType": "SquadronCarrier"}):
            self.request("Intermediate", **ownership)
            self.event("CarrierJumpCancelled", "12:01:00", **ownership)
            self.event("CarrierJump", "12:02:00", StarSystem="Paesia", **ownership)
            self.event("CarrierLocation", "12:03:00", StarSystem="Intermediate", **ownership)
        self.assertEqual(self.sync(), 900)
        self.assert_progress(0)
        self.assertEqual(self.tracker.carrier_data["jump_destination"], "Paesia")

    def test_historical_location_does_not_become_fresh_after_stats(self):
        self.event("CarrierLocation", "11:49:59", StarSystem="Intermediate")
        self.event("CarrierStats", "11:51:00", FuelLevel=915)
        self.assertIsNone(self.sync())
        self.assert_progress(0)

    def test_hidden_tab_timer_copy_and_ship_voiceattack_are_independent(self):
        tab = object.__new__(FleetCarrierRouteTab)
        tab.planner, tab.tracker = self.planner, self.tracker
        tab._jump_job = None
        tab._refresh_job = None
        tab._autocomplete = []
        tab.after = Mock(side_effect=lambda delay, callback: "jump" if delay else "sync")
        tab.after_cancel = Mock()
        tab.search = SimpleNamespace(running=False)
        tab.tree = Mock()
        tab.copy_button, tab.clear_button = Mock(), Mock()
        tab.reverse_button, tab.export_button, tab.import_button = Mock(), Mock(), Mock()
        tab.source = SimpleNamespace(get=lambda: "Sol")
        tab.destination = SimpleNamespace(get=lambda: "Paesia")
        tab._copy_system = Mock()
        self.tracker.set_on_route_updated(tab._on_carrier_updated)
        self.planner.set_route(STOPS, "market")
        ship = object.__new__(ShipRouteTab)
        ship.planner = self.planner
        ship.app = SimpleNamespace(_write_var_text=Mock())
        ship.copy_after_jump = SimpleNamespace(get=lambda: False)

        self.request("Intermediate")
        tab.after.assert_called_once_with(0, tab._sync_carrier_progress)
        tab._sync_carrier_progress()
        tab._pause_refresh(None)
        tab.after.assert_called_with(900000, tab._jump_timer_fired)
        tab.after_cancel.assert_not_called()
        self.now = self.due
        tab._jump_timer_fired()
        tab.tree.set.assert_called_with("1", "number", "▷ 1")
        tab._copy_next()
        tab._copy_system.assert_called_once_with("Paesia")
        self.assertEqual(self.planner.active_route["current_index"], 0)
        ship.app._write_var_text.assert_not_called()

        self.planner.handle_journal_events([{"event": "FSDJump", "StarSystem": "Intermediate"}])
        ship._on_journal_events([{"event": "FSDJump", "StarSystem": "Intermediate"}])
        ship.app._write_var_text.assert_has_calls([call("routeNextSystem", "Paesia"), call("routeJumpsLeft", "1")])
        self.event("CarrierJump", "12:22:00", StarSystem="Paesia")
        tab._sync_carrier_progress()
        tab.copy_button.configure.assert_called_with(state="disabled")
        tab._copy_next()
        tab._copy_system.assert_called_once()
        self.assertEqual(self.planner.active_route["current_index"], 1)
        self.assertEqual(ship.app._write_var_text.call_count, 2)

    def test_carrier_totals_show_hours_and_minutes_in_both_languages(self):
        tab = object.__new__(FleetCarrierRouteTab)
        tab.tree, tab.totals = Mock(), Mock()
        tab.tree.get_children.return_value = ()
        tab._show_progress, tab._load_hotspots, tab._update_buttons = Mock(), Mock(), Mock()
        active = {"stops": [CARRIER_STOPS[0], *[CARRIER_STOPS[1]] * 31]}
        localization = Path(__file__).resolve().parents[1] / "app" / "localization"
        for language, text in (("en", "about 10 h 20 min"), ("de", "ca. 10 Std. 20 Min.")):
            with self.subTest(language=language):
                strings = json.loads((localization / f"strings_{language}.json").read_text(encoding="utf-8"))
                with patch("fleet_carrier_route_tab.t", side_effect=lambda key: strings["route"][key[6:]]
                           if key.startswith("route.") else key):
                    tab._show_route(active)
                self.assertIn(text, tab.totals.configure.call_args.kwargs["text"])


class ActiveRouteChecks(unittest.TestCase):
    def test_ship_and_carrier_routes_restore_and_clear_independently(self):
        config = {}
        with patch.object(route, "_load_cfg", side_effect=config.copy), \
             patch.object(route, "update_config_value", side_effect=config.__setitem__):
            planner = route.RoutePlanner()
            planner.set_route(STOPS, "market")
            planner.set_carrier_route(CARRIER_STOPS)
            planner.handle_journal_events([{"event": "FSDJump", "StarSystem": "Paesia"}])

            restored = route.RoutePlanner()
            self.assertEqual(restored.active_route, {
                "stops": STOPS, "current_index": 2, "source_view": "market",
                "time": planner.active_route["time"], "off_route": False,
            })
            self.assertEqual(restored.active_carrier_route["stops"], CARRIER_STOPS)
            self.assertEqual(restored.active_carrier_route["current_index"], 0)
            restored.clear_carrier_route()
            self.assertEqual(route.RoutePlanner().active_route, planner.active_route)
            self.assertIsNone(route.RoutePlanner().active_carrier_route)

            restored.set_carrier_route(CARRIER_STOPS)
            restored.clear_route()
            self.assertIsNone(route.RoutePlanner().active_route)
            self.assertEqual(route.RoutePlanner().active_carrier_route, restored.active_carrier_route)

    def test_jump_skips_to_later_stop_and_saves_progress(self):
        config = {}
        with patch.object(route, "_load_cfg", lambda: config.copy()), \
             patch.object(route, "update_config_value", config.__setitem__):
            planner = route.RoutePlanner()
            planner.set_route(STOPS, "route")
            planner.handle_journal_events([{"event": "FSDJump", "StarSystem": "Elsewhere"}])
            planner.handle_journal_events([{"event": "FSDJump", "SystemAddress": 3657466647274}])

            restored = route.RoutePlanner().active_route
            self.assertEqual(restored["current_index"], 2)
            self.assertFalse(restored["off_route"])

    def test_journal_progress_and_config_restore(self):
        config = {}
        with patch.object(route, "_load_cfg", lambda: config.copy()), \
             patch.object(route, "update_config_value", config.__setitem__):
            planner = route.RoutePlanner()
            planner.set_route(STOPS, "market")
            planner.handle_journal_events([{"event": "JetConeBoost"}])
            self.assertTrue(planner.is_supercharged)
            planner.handle_journal_events([{"event": "FSDJump", "SystemAddress": 2}])
            self.assertFalse(planner.is_supercharged)
            self.assertTrue(planner.active_route["off_route"])
            self.assertEqual(planner.active_route["current_index"], 0)

            planner.handle_journal_events([{"event": "FSDJump", "SystemAddress": 1}])
            planner = route.RoutePlanner()
            self.assertEqual(planner.active_route["current_index"], 1)
            self.assertFalse(planner.active_route["off_route"])
            self.assertEqual(planner.active_route["source_view"], "market")
            self.assertGreater(planner.active_route["time"], 0)

            planner.handle_journal_events([{"event": "FSDJump", "StarSystem": "paesia"}])
            self.assertEqual(planner.active_route["current_index"], 2)
            planner.clear_route()
            self.assertIsNone(route.RoutePlanner().active_route)

    def test_plot_uses_one_daemon_worker(self):
        entered = threading.Event()
        release = threading.Event()
        client = Mock()
        worker_threads = []

        def poll(job, is_cancelled):
            worker_threads.append(threading.current_thread())
            entered.set()
            if not release.wait(3):
                raise TimeoutError()
            return STOPS

        client.poll.side_effect = poll
        with patch.object(route, "_load_cfg", return_value={}), \
             patch.object(route.requests, "Session"), \
             patch.object(route, "SpanshRouteClient", return_value=client):
            planner = route.RoutePlanner()
            future = planner.plot({"source": "Sol", "destination": "Paesia"}, lambda: False)
            try:
                self.assertTrue(entered.wait(3))
                self.assertTrue(worker_threads[0].daemon)
                with self.assertRaises(RuntimeError):
                    planner.plot({}, lambda: False)
                with self.assertRaises(RuntimeError):
                    planner.plot_carrier(10477373803, 3657466647274, 0, lambda: False)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=3), STOPS)
            self.assertIsNone(planner.active_route)

    def test_sale_legs_join_at_the_first_stop(self):
        first = {"source": "Sol", "destination": "Intermediate", "cargo": 144}
        second = {"source": "Intermediate", "destination": "Paesia", "cargo": 44}
        arrival = {**STOPS[1], "distance": 22, "must_refuel": True}
        client = Mock()
        client.poll.side_effect = [[STOPS[0], arrival], STOPS[1:]]
        with patch.object(route, "_load_cfg", return_value={}), \
             patch.object(route.requests, "Session"), \
             patch.object(route, "SpanshRouteClient", return_value=client):
            planner = route.RoutePlanner()
            future = planner.plot(first, lambda: False, second_form=second)
            self.assertEqual(future.result(timeout=3), [STOPS[0], arrival, STOPS[2]])
            self.assertEqual(client.start_plot.call_args_list, [call(first), call(second)])

            client.reset_mock()
            client.poll.side_effect = [STOPS[1:]]
            local = {**first, "source": "intermediate"}
            future = planner.plot(local, lambda: False, second_form=second)
            self.assertEqual(future.result(timeout=3), STOPS[1:])
            client.start_plot.assert_called_once_with(second)

    def test_cancel_between_sale_legs(self):
        first = {"source": "Sol", "destination": "Intermediate"}
        second = {"source": "Intermediate", "destination": "Paesia"}
        cancelled = threading.Event()

        def finish_first(job, is_cancelled):
            cancelled.set()
            return STOPS[:2]

        client = Mock()
        client.poll.side_effect = finish_first
        with patch.object(route, "_load_cfg", return_value={"active_route": STOPS}), \
             patch.object(route.requests, "Session"), \
             patch.object(route, "SpanshRouteClient", return_value=client):
            planner = route.RoutePlanner()
            future = planner.plot(first, cancelled.is_set, second_form=second)
            with self.assertRaises(CancelledError):
                future.result(timeout=3)
            client.start_plot.assert_called_once_with(first)
            self.assertIs(planner.active_route, STOPS)


if __name__ == "__main__":
    unittest.main()
