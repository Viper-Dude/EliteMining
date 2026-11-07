"""Generate one test WAV with VoiceStudio open."""
import json
from pathlib import Path
from urllib.request import Request, urlopen

VOICE = "US Female 01"
LINE = "All profile commands stopped and reset."


def request(route, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(
        f"http://localhost:3900/v1/audio/{route}",
        data=data,
        headers={"Authorization": "Bearer local", "Content-Type": "application/json"},
    )
    with urlopen(req, timeout=300 if data else 15) as response:
        return response.read()


def main():
    profiles = json.loads(request("voices"))["voices"]
    matches = [
        profile["voice_id"]
        for profile in profiles
        if profile.get("type") == "profile" and profile.get("name") == VOICE
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one saved VoiceStudio profile named {VOICE!r}.")

    print(f"{VOICE}: {LINE}", flush=True)
    audio = request("speech", {
        "model": "tts-1",
        "voice": matches[0],
        "input": LINE,
        "response_format": "wav",
        "speed": 0.7,
        "num_step": 64,
    })
    if len(audio) <= 44 or audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise RuntimeError("VoiceStudio did not return WAV audio.")

    output = Path(__file__).resolve().with_name("all_profile_commands_stopped_and_reset_US_Female_01_TEST.wav")
    output.write_bytes(audio)
    print(f"Saved: {output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        raise SystemExit(f"Test failed: {exc}") from None
