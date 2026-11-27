"""Check the Voice Commands reference against shipped profiles without Tk."""

import gzip
import json
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from va_phrase_reference import (
    GROUPS, _command_phrases, category_group, is_hidden_category, load_reference, reference_rows,
)
from va_profile_parser import VAProfileParser


class VoiceReferenceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profiles = sorted((ROOT / "Voiceattack Profile").glob("*.vap"))
        if not profiles:
            raise AssertionError("No shipped VoiceAttack profiles to check")
        parser = VAProfileParser()
        cls.commands = {profile: parser.get_all_commands(parser.parse(profile)) for profile in profiles}
        cls.entries = [entry for profile in profiles for entry in load_reference(profile)]

    def test_all_shipped_categories_are_mapped_or_hidden(self):
        for profile, commands in self.commands.items():
            categories = {command.findtext("Category") or "" for command in commands}
            for category in categories:
                with self.subTest(profile=profile.name, category=category):
                    if not is_hidden_category(category):
                        self.assertIn(category_group(category), GROUPS)

    def test_called_hidden_and_non_spoken_commands_are_omitted(self):
        profile = ET.Element("Profile")
        for category, name, spoken in (
            ("Commands - Panels", "((*PanelMove*))", "true"),
            ("Called Commands - Future", "Future helper", "true"),
            ("Dev's commands", "Dev command", "true"),
            ("EliteApi", "API command", "true"),
            ("", "Uncategorized command", "true"),
            ("EliteMining App Commands", "Keyboard-only command", "false"),
            ("SRV commands", "Deploy Buggy", "true"),
            ("Commands  - Flight Throttle", "Quarter throttle", "true"),
        ):
            command = ET.SubElement(profile, "Command")
            ET.SubElement(command, "Category").text = category
            ET.SubElement(command, "CommandString").text = name
            ET.SubElement(command, "UseSpokenPhrase").text = spoken

        with TemporaryDirectory() as folder:
            path = Path(folder) / "test.vap"
            path.write_bytes(gzip.compress(ET.tostring(profile)))
            entries = load_reference(path)
        self.assertEqual(len(entries), 1)
        rows = list(reference_rows(entries, "ships"))
        self.assertEqual([row.main_phrase for row in rows], ["Quarter throttle"])
        self.assertFalse(list(reference_rows(self.entries, "mining", "PanelMove")))
        self.assertFalse(list(reference_rows(self.entries, "mining", "License and Credit")))

    def test_ships_include_all_ship_commands_and_exclude_srv(self):
        rows = list(reference_rows(self.entries, "ships"))
        expected = [
            _command_phrases(command.findtext("CommandString"))[0].main
            for commands in self.commands.values() for command in commands
            if (command.findtext("Category") or "").partition(" (")[0].strip().casefold() == "ship commands"
        ]
        self.assertTrue(expected)
        ship_phrases = {row.main_phrase for row in rows}
        self.assertLessEqual(set(expected), ship_phrases)
        self.assertTrue(list(reference_rows(self.entries, "mining", "jump to super cruise")))
        self.assertFalse(list(reference_rows(self.entries, "mining", "buggy")))
        self.assertFalse(list(reference_rows(self.entries, "mining", "SRV")))

    def test_miscellaneous_has_its_own_group(self):
        self.assertEqual(category_group("Miscellaneous"), "miscellaneous")
        category = "Commands - Miscellaneous (assign your keys and buttons here)"
        self.assertEqual(category_group(category), "miscellaneous")
        map_phrases = {"Open Galaxy Map", "Close Galaxy Map", "Open System Map", "Close System Map"}
        rows = list(reference_rows(self.entries, "miscellaneous"))
        self.assertLessEqual(map_phrases, {row.main_phrase for row in rows})
        matches = [row.group for row in reference_rows(self.entries, "ships", "Open Galaxy Map")
                   if row.main_phrase == "Open Galaxy Map"]
        self.assertEqual(matches, ["miscellaneous"])

    def test_unknown_category_is_logged_once(self):
        with self.assertLogs("va_phrase_reference", level="INFO") as logs:
            for _ in range(2):
                self.assertIsNone(category_group("Unmapped test category"))
        self.assertEqual(len(logs.output), 1)
        self.assertIn("Unmapped test category", logs.output[0])

    def test_mining_category_instructions_can_change(self):
        for category in (
            "Custom Keybinds for Mining control (set you own keybinds here)",
            "Mining control (assign your keys and buttons here)",
            "Mining control (bind the controls for your ship)",
            "Mining control",
        ):
            with self.subTest(category=category):
                self.assertEqual(category_group(category), "mining")

    def test_shipped_phrase_formatting(self):
        shipped = [command.findtext("CommandString") or ""
                   for commands in self.commands.values() for command in commands]
        cases = (
            ("Enable thrust up;", "Enable or disable thrust up", "Enable or disable thrust up"),
            ("Say [delay;timer;duration] for cargo scoop;", "Say delay for cargo scoop",
             "Say delay, timer or duration for cargo scoop"),
            ("Set [duration;timer] for [firing;]", "Set duration for firing laser mining to 1\u201350 seconds",
             "Set duration or timer for (firing) laser or lasers (mining) to 1\u201350 seconds"),
            ("Set [timer;delay] for [target;targeting;]", "Set timer for target prospector to 1\u201350 seconds",
             "Set timer or delay for (target or targeting) prospector to 1\u201350 seconds"),
            ("Set firegroup for mining lasers to [alpha;", "Set firegroup for mining lasers to alpha \u2026 hotel",
             "Set firegroup for mining lasers to alpha \u2026 hotel"),
            ("Deploy [SRV; Buggy]", "Deploy SRV one \u2026 four", "Deploy SRV or Buggy (one \u2026 four)"),
            ("Cargo scoop toggle to [0]", "Cargo scoop toggle to 0", "Cargo scoop toggle to 0"),
            ("[Show; Unhide; Maximize] Voiceattack", "Show Voiceattack", "Show, Unhide or Maximize Voiceattack"),
            ("Toggle night vision ", "Toggle night vision", "Toggle night vision"),
        )
        for prefix, main, detail in cases:
            with self.subTest(prefix=prefix):
                phrase = _command_phrases(next(name for name in shipped if name.startswith(prefix)))[0]
                self.assertEqual((phrase.main, phrase.detail), (main, detail))
        toggles = next(name for name in shipped if name.startswith("Enable thrust up;"))
        self.assertEqual([phrase.main for phrase in _command_phrases(toggles)],
                         ["Enable or disable thrust up", "Turn on or off thrust up"])

    def test_search_uses_alternate_phrases_across_groups(self):
        row = next(reference_rows(self.entries, "voiceattack", "  LAUNCH PROSPECTOR "))
        self.assertEqual((row.group, row.main_phrase), ("mining", "Launch prospector"))
        self.assertEqual(len(row.other_phrases), 5)
        self.assertIn("Start prospector sequence", row.other_phrases)
        self.assertNotIn(row.main_phrase, row.other_phrases)

        row = next(reference_rows(self.entries, "mining", "mining lasers to golf"))
        self.assertEqual((row.group, row.main_phrase), ("firegroups", "Set firegroup for mining lasers to golf"))
        row = next(reference_rows(self.entries, "mining", "disable thrust up"))
        self.assertEqual(row.main_phrase, "Disable thrust up")
        self.assertEqual(row.other_phrases, ("Turn on or off thrust up",))
        self.assertTrue(all(row.group == "mining" for row in reference_rows(self.entries, "mining", " ")))

    def test_profile_description_follows_the_command(self):
        primary = next(row for row in reference_rows(self.entries, "mining")
                       if row.main_phrase == "Start prospector sequence")
        alternate = next(reference_rows(self.entries, "ships", "launch prospector"))
        self.assertIn("targets it automatically", primary.description)
        self.assertEqual(alternate.description, primary.description)
        simple = next(reference_rows(self.entries, "ships", "Open Galaxy Map"))
        self.assertEqual(simple.description, "")

    def test_english_and_german_strings(self):
        keys = {f"reference_group_{group}" for group in GROUPS}
        keys.update(f"reference_{key}" for key in (
            "tab", "group", "search", "say_this", "other_ways", "also_works", "loading", "empty", "missing", "error",
        ))
        for language in ("en", "de"):
            with self.subTest(language=language):
                path = ROOT / "app" / "localization" / f"strings_{language}.json"
                strings = json.loads(path.read_text(encoding="utf-8-sig"))["voiceattack"]
                self.assertFalse(keys - strings.keys(), keys - strings.keys())
                self.assertTrue(all(strings[key].strip() for key in keys))


if __name__ == "__main__":
    unittest.main()
