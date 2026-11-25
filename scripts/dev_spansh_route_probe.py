"""Probe the Spansh Galaxy Plotter using a journal's Type-11 loadout."""

import argparse
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from version import __version__


API = "https://spansh.co.uk/api"
FSD_FIELDS = {
    "fuel_power": 2.45,
    "fuel_multiplier": 0.013,
    "optimal_mass": 1997.514343,
    "max_fuel_per_jump": 5.2,
    "supercharge_multiplier": 4,
    "injection_multiplier": 2,
}


def read_loadout(journal):
    loadout = None
    with journal.open(encoding="utf-8-sig") as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "Loadout" and event.get("Ship") == "lakonminer":
                loadout = event
    if loadout is None:
        raise ValueError("No Type-11 Prospector Loadout found in the journal")
    return {
        field: loadout[field]
        for field in ("event", "Ship", "UnladenMass", "FuelCapacity", "Modules")
    }


def request(path, form=None, timeout=15):
    data = urlencode(form).encode("ascii") if form is not None else None
    req = Request(f"{API}/{path}", data=data, headers={"User-Agent": f"EliteMining/{__version__}"})
    try:
        response = urlopen(req, timeout=timeout)
    except HTTPError as error:
        response = error
    with response:
        status = response.code
        try:
            payload = json.load(response)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError(f"Spansh returned HTTP {status} without JSON") from None
        return status, payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("journal", type=Path, nargs="?", help="Send build data from this journal instead of the synthetic example")
    parser.add_argument("--ids", action="store_true", help="Use Sol and Paesia id64s instead of names")
    parser.add_argument("--omit-fsd", action="store_true", help="Omit explicit drive fields, retaining SLEF")
    args = parser.parse_args()
    try:
        loadout = read_loadout(args.journal) if args.journal else {
            "event": "Loadout",
            "Ship": "lakonminer",
            "UnladenMass": 500,
            "FuelCapacity": {"Main": 32, "Reserve": 0.6},
            "Modules": [{"Slot": "FrameShiftDrive", "Item": "int_hyperdrive_size5_class5"}],
        }
        fuel = loadout["FuelCapacity"]
        form = {
            "source": 10477373803 if args.ids else "Sol",
            "destination": 3657466647274 if args.ids else "Paesia",
            "is_supercharged": 0,
            "use_supercharge": 1,
            "use_injections": 0,
            "use_injections_when_required": 0,
            "exclude_secondary": 1,
            "refuel_every_scoopable": 1,
            "reserve_size": 0,
            "base_mass": loadout["UnladenMass"] + fuel["Reserve"],
            "tank_size": fuel["Main"],
            "internal_tank_size": fuel["Reserve"],
            "range_boost": "",
            "ship_build": json.dumps([{
                "header": {"appName": "EliteMining", "appVersion": __version__},
                "data": loadout,
            }]),
            "cargo": 144,
            "algorithm": "beam",
        }
        if not args.omit_fsd:
            form.update(FSD_FIELDS)
        status, payload = request("generic/route", form)
        print(f"POST generic/route: HTTP {status}, status={payload.get('status')!r}")
        if status != 202 or not payload.get("job"):
            print(payload.get("error") or payload.get("message") or "No job returned")
            return 1

        deadline = time.monotonic() + 120
        delay = 2
        path = "results/" + quote(str(payload["job"]), safe="")
        while deadline - time.monotonic() > delay:
            time.sleep(delay)
            status, result = request(path, timeout=min(15, max(0.1, deadline - time.monotonic())))
            print(f"GET results: HTTP {status}, status={result.get('status')!r}")
            if status == 200:
                route = result.get("result")
                if not isinstance(route, dict):
                    print(result.get("error") or "No route returned")
                    return 1
                print(json.dumps({
                    key: value for key, value in route.items() if key not in ("ship_build", "parameters")
                }, indent=2))
                return 0
            if status != 202:
                print(result.get("error") or "Polling failed")
                return 1
            delay = min(8, delay * 2)
        print("Timed out waiting for Spansh")
    except (OSError, ValueError, KeyError) as error:
        print(error, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
