"""Checks for the VoiceAttack keybind extractor/applier. Works on in-memory copies only."""
import os
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "app"))

from va_profile_parser import VAProfileParser  # noqa: E402
from va_keybind_extractor import VAKeybindExtractor  # noqa: E402
from va_keybind_applier import VAKeybindApplier  # noqa: E402

failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def cmd(name, **fields):
    base = {"CommandString": name, "Enabled": "true", "UseShortcut": "false", "UseJoystick": "false",
            "UseMouse": "false", "UseVariableHotkey": "false", "UseVariableMouseShortcut": "false",
            "UseVariableJoystickShortcut": "false"}
    base.update(fields)
    body = "".join(f"<{k}>{v}</{k}>" for k, v in base.items())
    return f"<Command>{body}</Command>"


def tree(*cmds):
    return ET.ElementTree(ET.fromstring("<Profile><Commands>" + "".join(cmds) + "</Commands></Profile>"))


def real_profiles():
    parser = VAProfileParser()
    path = os.path.join(ROOT, "Voiceattack Profile", "Test_profile", "EliteMining v1.0.0-Profile.vap")
    src = parser.parse(path)
    ex = VAKeybindExtractor()
    kb = ex.extract(src)
    check(len(kb) == 68, f"real export: 68 bound player commands (got {len(kb)})")
    check(not any(n.startswith("((") for n in kb), "real export: no internal commands")
    check(not ex.skipped, "real export: no variable shortcuts")
    target = parser.parse(path)
    # wipe the bindings in the target so the round trip is meaningful
    for c in target.findall(".//Command"):
        for n in ("UseShortcut", "UseJoystick", "UseMouse"):
            c.find(n).text = "false"
    ap = VAKeybindApplier()
    ap.apply(target, kb)
    check(len(ap.last_result.applied) == 68 and not ap.last_result.not_applied, "round trip: all 68 applied")
    check(VAKeybindExtractor().extract(target) == kb, "round trip: re-extracted bindings identical")


def synthetic():
    old = tree(
        cmd("Boost", UseShortcut="true", keyValue="66", keyCtrl="1"),
        cmd("Old name;spoken one", UseJoystick="true", joystickNumber="1", joystickButton="5", joystickUp="true"),
        cmd("Shared phrase;alpha", UseMouse="true", Mouse3="true", MouseUpOnly="true"),
        cmd("Dup;beta", UseJoystick="true", joystickNumber="1", joystickButton="9"),
        cmd("Gone", UseShortcut="true", keyValue="70"),
        cmd("Var cmd", UseJoystick="true", UseVariableJoystickShortcut="true", joystickNumber="1", joystickButton="2"),
        cmd("((Internal))", UseShortcut="true", keyValue="1"),
        cmd("Disabled", Enabled="false", UseShortcut="true", keyValue="71"),
    )
    new = tree(
        cmd("Boost"),
        cmd("Renamed command;other", MousePassThru=""),
        cmd("Brand new;alpha"),
        cmd("Amb one;beta"), cmd("Amb two;beta"),
        cmd("Var cmd"), cmd("Disabled"),
        cmd("((Internal))"),
    )
    ex = VAKeybindExtractor()
    kb = ex.extract(old)
    check("((Internal))" not in kb, "internal command skipped")
    check("Var cmd" not in kb and ("Var cmd", "variable") in ex.skipped, "variable shortcut skipped and reported")
    check(kb["Disabled"].enabled is False, "Enabled=false read correctly")
    ap = VAKeybindApplier(renames={"Old name;spoken one": "Renamed command;other"})
    ap.apply(new, kb)
    r = ap.last_result
    check(r.matched_by["Boost"] == "exact", "exact match")
    check(r.matched_by["Old name;spoken one"] == "renamed", "rename list match")
    check(r.matched_by["Shared phrase;alpha"] == "phrase", "shared phrase match")
    check(("Dup;beta", "ambiguous") in r.not_applied, "ambiguous phrase not applied")
    check(("Gone", "no_match") in r.not_applied, "unmatched reported")
    def f(name, el):
        for c in new.findall(".//Command"):
            if c.find("CommandString").text == name:
                return c.find(el)
    check(f("Boost", "keyValue").text == "66" and f("Boost", "keyCtrl").text == "1", "keyboard fields written")
    check(f("Renamed command;other", "joystickUp").text == "true", "joystick release written")
    check(f("Brand new;alpha", "Mouse3").text == "true" and f("Brand new;alpha", "MouseUpOnly").text == "true", "mouse fields written")
    check(f("Var cmd", "UseJoystick").text == "false" and f("Var cmd", "UseVariableJoystickShortcut").text == "false",
          "variable shortcut never switched on")
    check(f("Disabled", "Enabled").text == "false", "disabled state carried over")


if __name__ == "__main__":
    real_profiles()
    synthetic()
    print("FAILED" if failures else "ALL PASSED")
    sys.exit(1 if failures else 0)
