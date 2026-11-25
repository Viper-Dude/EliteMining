"""Checks for the route planner core. No Spansh requests or local config writes."""

import json
from concurrent.futures import CancelledError
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import route_planner as route


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


class ActiveRouteChecks(unittest.TestCase):
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
            future = planner.plot({}, lambda: False)
            try:
                self.assertTrue(entered.wait(3))
                self.assertTrue(worker_threads[0].daemon)
                with self.assertRaises(RuntimeError):
                    planner.plot({}, lambda: False)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=3), STOPS)
            self.assertIsNone(planner.active_route)


if __name__ == "__main__":
    unittest.main()
