"""Ship range, Spansh Galaxy Plotter requests, and the active route."""

import json
import threading
import time
from concurrent.futures import CancelledError, Future
from urllib.parse import quote

import requests

from config import _load_cfg, update_config_value
from version import __version__


# In-game module symbols and jump constants verified against https://github.com/EDCD/coriolis-data
# (modules/standard/frame_shift_drive.json and modules/internal/guardian_fsd_booster.json).
# Each row is fuel power, fuel multiplier, optimal mass, and max fuel per jump.
# Pre-engineered V1 drives share the base module symbols and report their
# modified values in Loadout.Engineering.
_FSD = {
    "int_hyperdrive_size2_class1": (2, 0.011, 48, 0.6),
    "int_hyperdrive_size2_class2": (2, 0.010, 54, 0.6),
    "int_hyperdrive_size2_class3": (2, 0.008, 60, 0.6),
    "int_hyperdrive_size2_class4": (2, 0.010, 75, 0.8),
    "int_hyperdrive_size2_class5": (2, 0.012, 90, 0.9),
    "int_hyperdrive_size3_class1": (2.15, 0.011, 80, 1.2),
    "int_hyperdrive_size3_class2": (2.15, 0.010, 90, 1.2),
    "int_hyperdrive_size3_class3": (2.15, 0.008, 100, 1.2),
    "int_hyperdrive_size3_class4": (2.15, 0.010, 125, 1.5),
    "int_hyperdrive_size3_class5": (2.15, 0.012, 150, 1.8),
    "int_hyperdrive_size4_class1": (2.30, 0.011, 280, 2),
    "int_hyperdrive_size4_class2": (2.30, 0.010, 315, 2),
    "int_hyperdrive_size4_class3": (2.30, 0.008, 350, 2),
    "int_hyperdrive_size4_class4": (2.30, 0.010, 437.5, 2.5),
    "int_hyperdrive_size4_class5": (2.30, 0.012, 525, 3),
    "int_hyperdrive_size5_class1": (2.45, 0.011, 560, 3.3),
    "int_hyperdrive_size5_class2": (2.45, 0.010, 630, 3.3),
    "int_hyperdrive_size5_class3": (2.45, 0.008, 700, 3.3),
    "int_hyperdrive_size5_class4": (2.45, 0.010, 875, 4.1),
    "int_hyperdrive_size5_class5": (2.45, 0.012, 1050, 5),
    "int_hyperdrive_size6_class1": (2.60, 0.011, 960, 5.3),
    "int_hyperdrive_size6_class2": (2.60, 0.010, 1080, 5.3),
    "int_hyperdrive_size6_class3": (2.60, 0.008, 1200, 5.3),
    "int_hyperdrive_size6_class4": (2.60, 0.010, 1500, 6.6),
    "int_hyperdrive_size6_class5": (2.60, 0.012, 1800, 8),
    "int_hyperdrive_size7_class1": (2.75, 0.011, 1440, 8.5),
    "int_hyperdrive_size7_class2": (2.75, 0.010, 1620, 8.5),
    "int_hyperdrive_size7_class3": (2.75, 0.008, 1800, 8.5),
    "int_hyperdrive_size7_class4": (2.75, 0.010, 2250, 10.6),
    "int_hyperdrive_size7_class5": (2.75, 0.012, 2700, 12.8),
    "int_hyperdrive_overcharge_size2_class1": (2, 0.008, 60, 0.6),
    "int_hyperdrive_overcharge_size2_class2": (2, 0.012, 90, 0.9),
    "int_hyperdrive_overcharge_size2_class3": (2, 0.012, 90, 0.9),
    "int_hyperdrive_overcharge_size2_class4": (2, 0.012, 90, 0.9),
    "int_hyperdrive_overcharge_size2_class5": (2, 0.013, 100, 1),
    "int_hyperdrive_overcharge_size3_class1": (2.15, 0.008, 100, 1.2),
    "int_hyperdrive_overcharge_size3_class2": (2.15, 0.012, 150, 1.8),
    "int_hyperdrive_overcharge_size3_class3": (2.15, 0.012, 150, 1.8),
    "int_hyperdrive_overcharge_size3_class4": (2.15, 0.012, 150, 1.8),
    "int_hyperdrive_overcharge_size3_class5": (2.15, 0.013, 167, 1.9),
    "int_hyperdrive_overcharge_size4_class1": (2.30, 0.008, 350, 2),
    "int_hyperdrive_overcharge_size4_class2": (2.30, 0.012, 525, 3),
    "int_hyperdrive_overcharge_size4_class3": (2.30, 0.012, 525, 3),
    "int_hyperdrive_overcharge_size4_class4": (2.30, 0.012, 525, 3),
    "int_hyperdrive_overcharge_size4_class5": (2.30, 0.013, 585, 3.2),
    "int_hyperdrive_overcharge_size5_class1": (2.45, 0.008, 700, 3.3),
    "int_hyperdrive_overcharge_size5_class2": (2.45, 0.012, 1050, 5),
    "int_hyperdrive_overcharge_size5_class3": (2.45, 0.012, 1050, 5),
    "int_hyperdrive_overcharge_size5_class4": (2.45, 0.012, 1050, 5),
    "int_hyperdrive_overcharge_size5_class5": (2.45, 0.013, 1175, 5.2),
    "int_hyperdrive_overcharge_size6_class1": (2.60, 0.008, 1200, 5.3),
    "int_hyperdrive_overcharge_size6_class2": (2.60, 0.012, 1800, 8),
    "int_hyperdrive_overcharge_size6_class3": (2.60, 0.012, 1800, 8),
    "int_hyperdrive_overcharge_size6_class4": (2.60, 0.012, 1800, 8),
    "int_hyperdrive_overcharge_size6_class5": (2.60, 0.013, 2000, 8.3),
    "int_hyperdrive_overcharge_size7_class1": (2.75, 0.008, 1800, 8.5),
    "int_hyperdrive_overcharge_size7_class2": (2.75, 0.012, 2700, 12.8),
    "int_hyperdrive_overcharge_size7_class3": (2.75, 0.012, 2700, 12.8),
    "int_hyperdrive_overcharge_size7_class4": (2.75, 0.012, 2700, 12.8),
    "int_hyperdrive_overcharge_size7_class5": (2.75, 0.013, 3000, 13.1),
    "int_hyperdrive_overcharge_size8_class1": (2.90, 0.008, 2800, 13.6),
    "int_hyperdrive_overcharge_size8_class2": (2.90, 0.012, 4200, 20.4),
    "int_hyperdrive_overcharge_size8_class3": (2.90, 0.012, 4200, 20.4),
    "int_hyperdrive_overcharge_size8_class4": (2.90, 0.012, 4200, 20.4),
    "int_hyperdrive_overcharge_size8_class5": (2.90, 0.013, 4670, 20.7),
    "int_hyperdrive_overcharge_size8_class5_overchargebooster_mkii": (2.5025, 0.011, 4670, 6.8),
}

_GUARDIAN_BOOST = {
    "int_guardianfsdbooster_size1": 4,
    "int_guardianfsdbooster_size2": 6,
    "int_guardianfsdbooster_size3": 7.75,
    "int_guardianfsdbooster_size4": 9.25,
    "int_guardianfsdbooster_size5": 10.5,
}

_API = "https://spansh.co.uk/api"
_PLOT_TIMEOUT = 120
_ACTIVE_ROUTE_KEY = "active_route"


def fsd_spec(loadout):
    """Derive drive and ship values from the latest journal Loadout."""
    modules = (loadout or {}).get("Modules", [])
    drive = next((module for module in modules
                  if module.get("Slot", "").lower() == "frameshiftdrive"), {})
    item = drive.get("Item", "").lower()
    if item not in _FSD:
        raise ValueError("Loadout has no supported frame shift drive")
    fuel_power, fuel_multiplier, optimal_mass, max_fuel = _FSD[item]
    modifiers = {modifier["Label"].lower(): modifier["Value"]
                 for modifier in drive.get("Engineering", {}).get("Modifiers", [])
                 if "Value" in modifier}
    fuel = loadout["FuelCapacity"]
    booster = next((_GUARDIAN_BOOST[module["Item"].lower()] for module in modules
                    if module.get("On", True) and module.get("Item", "").lower() in _GUARDIAN_BOOST), 0)
    return {
        "fuel_power": fuel_power,
        "fuel_multiplier": fuel_multiplier,
        "optimal_mass": modifiers.get("fsdoptimalmass", optimal_mass),
        "max_fuel_per_jump": modifiers.get("maxfuelperjump", max_fuel),
        "base_mass": loadout["UnladenMass"] + fuel["Reserve"],
        "tank_size": fuel["Main"],
        "internal_tank_size": fuel["Reserve"],
        "range_boost": booster,
        "supercharge_multiplier": 6 if item.endswith("_overchargebooster_mkii") else 4,
        "injection_multiplier": 2,
    }


def jump_range(loadout, fuel, cargo):
    spec = fsd_spec(loadout)
    fuel_used = min(fuel, spec["max_fuel_per_jump"])
    if fuel_used <= 0:
        return 0.0
    mass = spec["base_mass"] + fuel + cargo
    return (spec["optimal_mass"] / mass
            * (fuel_used / spec["fuel_multiplier"]) ** (1 / spec["fuel_power"])
            + spec["range_boost"])


def build_slef(loadout):
    return json.dumps([{
        "header": {"appName": "EliteMining", "appVersion": __version__},
        "data": loadout,
    }])


def build_route_form(loadout, source, destination, cargo, *, is_supercharged=False,
                     use_supercharge=True, use_injections_when_required=False):
    form = fsd_spec(loadout)
    form.update({
        "source": source,
        "destination": destination,
        "is_supercharged": int(is_supercharged),
        "use_supercharge": int(use_supercharge),
        "use_injections": 0,
        "use_injections_when_required": int(use_injections_when_required),
        "exclude_secondary": 1,
        "refuel_every_scoopable": 1,
        "reserve_size": 0,
        "range_boost": form["range_boost"] or "",
        "ship_build": build_slef(loadout),
        "cargo": cargo,
        "algorithm": "beam",
    })
    return form


class SpanshRouteClient:
    """Blocking calls for the plot worker."""

    def __init__(self, session):
        self.session = session
        self.session.headers["User-Agent"] = f"EliteMining/{__version__}"

    def start_plot(self, form):
        response = self.session.post(f"{_API}/generic/route", data=form, timeout=15)
        response.raise_for_status()
        job = response.json().get("job")
        if response.status_code != 202 or not job:
            raise ValueError("Spansh did not return a route job")
        return str(job)

    def poll(self, job, is_cancelled):
        deadline = time.monotonic() + _PLOT_TIMEOUT
        delay = 2
        url = f"{_API}/results/{quote(job, safe='')}"
        while True:
            poll_at = min(time.monotonic() + delay, deadline)
            while True:
                if is_cancelled():
                    raise CancelledError()
                remaining = poll_at - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.1))

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Spansh route plot timed out")
            response = self.session.get(url, timeout=min(15, remaining))
            if is_cancelled():
                raise CancelledError()
            if time.monotonic() >= deadline:
                raise TimeoutError("Spansh route plot timed out")
            response.raise_for_status()
            if response.status_code == 202:
                delay = min(delay * 2, 8)
                continue
            payload = response.json()
            stops = (payload.get("result") or {}).get("jumps")
            if (response.status_code != 200 or payload.get("status") != "ok"
                    or not isinstance(stops, list) or not stops):
                raise ValueError("Spansh did not return route stops")
            return stops


def _matches_stop(event, stop):
    address = event.get("SystemAddress")
    if address is not None and stop.get("id64") is not None:
        return str(address) == str(stop["id64"])
    name = event.get("StarSystem")
    return bool(name and name.casefold() == stop["name"].casefold())


class RoutePlanner:
    """Owns one active route. The caller applies a plot result on its own thread."""

    def __init__(self):
        self.active_route = _load_cfg().get(_ACTIVE_ROUTE_KEY)
        self.is_supercharged = False
        self._plot_lock = threading.Lock()
        self._plot = None

    def plot(self, form, is_cancelled):
        """Return a Future for the stops. All HTTP calls run in a daemon thread."""
        def worker():
            if not future.set_running_or_notify_cancel():
                return
            try:
                if is_cancelled():
                    raise CancelledError()
                with requests.Session() as session:
                    client = SpanshRouteClient(session)
                    stops = client.poll(client.start_plot(form), is_cancelled)
            except Exception as error:
                future.set_exception(error)
            else:
                future.set_result(stops)

        with self._plot_lock:
            if self._plot is not None and not self._plot.done():
                raise RuntimeError("A route plot is already running")
            future = self._plot = Future()
            threading.Thread(target=worker, daemon=True).start()
        return future

    def _save_route(self, route):
        update_config_value(_ACTIVE_ROUTE_KEY, route)
        self.active_route = route

    def set_route(self, stops, source_view):
        self._save_route({
            "stops": stops,
            "current_index": 0,
            "source_view": source_view,
            "time": time.time(),
            "off_route": False,
        })

    def clear_route(self):
        self._save_route(None)

    def handle_journal_events(self, events):
        for event in events:
            event_type = event.get("event")
            if event_type == "JetConeBoost":
                self.is_supercharged = True
            elif event_type == "FSDJump":
                self.is_supercharged = False
                self._advance_route(event)

    def _advance_route(self, event):
        route = self.active_route
        if not route:
            return
        index = route["current_index"]
        stops = route["stops"]
        if index + 1 < len(stops) and _matches_stop(event, stops[index + 1]):
            index += 1
            off_route = False
        else:
            off_route = not any(_matches_stop(event, stop) for stop in stops)
        if index != route["current_index"] or off_route != route["off_route"]:
            self._save_route({**route, "current_index": index, "off_route": off_route})
