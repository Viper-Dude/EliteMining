"""Run with VoiceStudio open: py EliteMining-VoiceStudio.py [--test]"""
import argparse
import json
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

VOICES = ("US Male 01", "US Female 01", "UK Male 01", "UK Female 01")
CALLOUTS = (
    ("all_profile_commands_stopped_and_reset", "All profile commands stopped and reset."),
    ("cargo_scoop_retraction_aborted", "Cargo Scoop retraction aborted."),
    ("continuous_boost_initiated", "Continuous boost initiated."),
    ("continuous_boost_terminated", "Continuous boost terminated."),
    ("continuous_pulse_wave_scanning_initiated", "Continuous pulse wave scanning initiated."),
    ("core_scanning_initiated", "Core scanning initiated."),
    ("core_scanning_terminated", "Core scanning terminated."),
    ("executing_clear_and_vector_protocol", "Executing clear and vector protocol."),
    ("mining_sequence_reset_complete", "Mining sequence reset complete."),
    ("mining_sequence_reset_initiated", "Mining sequence reset initiated."),
    ("prospector_sequence_initiated", "Prospector sequence initiated."),
    ("pulse_wave_scanning_terminated", "Pulse wave scanning terminated."),
    ("requesting_docking_clearance", "Requesting docking clearance."),
    ("retract_scoop_set_power_and_firegroup", "Retracting scoop. Setting power and fire group."),
    ("seismic_charge_system_online", "Seismic charge system online."),
    ("starting_mining_seq", "Starting Mining Sequence."),
    ("sub_surface_displacement_system_online", "Sub-surface displacement system online."),
    ("weapons_activated", "Weapons activated."),
)


def request(route, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        f"http://localhost:3900/v1/audio/{route}",
        data=data,
        headers={"Authorization": "Bearer local", "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=300 if data else 15) as response:
            return response.read()
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"VoiceStudio returned HTTP {exc.code}: {detail}") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="Generate the first callout in each voice.")
    args = parser.parse_args()

    profiles = json.loads(request("voices"))["voices"]
    voice_ids = {}
    for name in VOICES:
        matches = [
            profile["voice_id"]
            for profile in profiles
            if profile.get("name") == name and profile.get("type") == "profile"
        ]
        if len(matches) != 1:
            available = ", ".join(p["name"] for p in profiles if p.get("type") == "profile")
            raise RuntimeError(f"Expected one saved profile named {name!r}. Available: {available}")
        voice_ids[name] = matches[0]

    root = Path(__file__).resolve().parent / "EliteMining-VoiceStudio-WAV"
    callouts = CALLOUTS[:1] if args.test else CALLOUTS
    for name, voice_id in voice_ids.items():
        folder = root / name
        folder.mkdir(parents=True, exist_ok=True)
        for stem, line in callouts:
            path = folder / f"{stem}.wav"
            if path.exists():
                print(f"Skipping existing: {name}/{path.name}", flush=True)
                continue
            print(f"Generating: {name}/{path.name}", flush=True)
            audio = request("speech", {
                "model": "tts-1",
                "voice": voice_id,
                "input": line,
                "response_format": "wav",
                "speed": 0.7,
                "num_step": 64,
            })
            if len(audio) <= 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
                raise RuntimeError("VoiceStudio did not return WAV audio.")
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".tmp", delete=False) as temp:
                temp_path = Path(temp.name)
                try:
                    with temp:
                        temp.write(audio)
                    temp_path.rename(path)
                finally:
                    temp_path.unlink(missing_ok=True)

    print(f"Finished. Output: {root}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        sys.exit(f"Batch stopped: {exc}\nKeep VoiceStudio open and rerun to resume.")
