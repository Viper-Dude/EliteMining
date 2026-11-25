"""Checks for route planning. No Spansh requests or local config writes."""

import json
from concurrent.futures import CancelledError
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from cargo_monitor import CargoMonitor
from localization import t
import route_planner as route
from route_tab import RouteTab


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
        form = route.build_route_form(LOADOUT, 10477373803, "Paesia", 144)
        self.assertEqual(json.loads(form.pop("ship_build")), slef)
        self.assertEqual(form, {
            "source": 10477373803, "destination": "Paesia", "cargo": 144,
            "is_supercharged": 0, "use_supercharge": 1, "use_injections": 0,
            "use_injections_when_required": 0, "exclude_secondary": 1,
            "refuel_every_scoopable": 1, "reserve_size": 0,
            "fuel_power": 2.45, "fuel_multiplier": 0.013, "optimal_mass": 1997.514343,
            "max_fuel_per_jump": 5.2, "base_mass": 601.325058, "tank_size": 32,
            "internal_tank_size": 0.6, "range_boost": "", "algorithm": "beam",
            "supercharge_multiplier": 4, "injection_multiplier": 2,
        })

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


class RouteTabChecks(unittest.TestCase):
    def test_import_validates_file_before_confirming_replacement(self):
        tab = RouteTab.__new__(RouteTab)
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
             patch("route_tab.filedialog.askopenfilename") as dialog, \
             patch("route_tab.centered_yesno_dialog", return_value=False) as confirm:
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
        tab = RouteTab.__new__(RouteTab)
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
        tab = RouteTab.__new__(RouteTab)
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

    def test_route_button_uses_override_and_other_views_use_live_cargo(self):
        tab = RouteTab.__new__(RouteTab)
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
        tab.planner = Mock(active_route=None, is_supercharged=False)
        tab.injection_grade = Mock()
        tab.injection_grade.current.return_value = 0
        tab.use_supercharge = Mock(**{"get.return_value": True})
        tab._autocomplete = []
        tab._update_buttons = Mock()
        tab._wait_for_plot = Mock()
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
        RouteTab._show_route(tab, {"stops": stops, "current_index": 0, "off_route": False})
        rows = [call.kwargs["values"] for call in tab.tree.insert.call_args_list]
        self.assertEqual([values[-2] for values in rows], ["", t("common.yes"), ""])
        tab.totals.configure.assert_called_with(text=t("route.totals").format(jumps=2, distance=50, minutes=4))

    def test_injection_grade_applies_to_both_sale_legs(self):
        tab = Mock()
        tab.cargo.latest_loadout = LOADOUT
        tab.cargo.current_cargo = 144
        tab.planner.active_route = None
        tab.planner.is_supercharged = False
        tab._autocomplete = []
        tab.colors = {"fg": "#000000"}
        tab.use_supercharge.get.return_value = True

        for grade, enabled, multiplier in [(0, 0, 2), (1, 1, 1.25), (2, 1, 1.5), (3, 1, 2)]:
            with self.subTest(grade=grade):
                tab.injection_grade.current.return_value = grade
                RouteTab._plot(tab, "Sol", "Intermediate", second="Paesia", sold_first=104,
                               source_view="sell_hold")

                args, kwargs = tab.planner.plot.call_args
                for form, cargo in [(args[0], 144), (kwargs["second_form"], 40)]:
                    self.assertEqual(form["use_injections"], 0)
                    self.assertEqual(form["use_injections_when_required"], enabled)
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
        status_path = self.folder / "Status.json"
        self.cargo.status_json_path = str(status_path)
        tab = SimpleNamespace(cargo=self.cargo, range_label=Mock())
        for status, fuel in [({}, 32), ({"Fuel": {"FuelMain": 5.2}}, 5.2), ({"Fuel": {"FuelMain": 0}}, 0)]:
            with self.subTest(status=status):
                status_path.write_text(json.dumps(status), encoding="utf-8")
                self.cargo.last_status_mtime = 0
                self.cargo._check_status_for_ship_changes()
                RouteTab._update_jump_range(tab, self.cargo.current_cargo)
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


class ActiveRouteChecks(unittest.TestCase):
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
