"""Read and format the spoken commands in the shipped VoiceAttack profile."""

import logging
import re
from dataclasses import dataclass
from functools import cache
from itertools import product
from pathlib import Path

from va_keybind_extractor import is_internal_command
from va_profile_parser import VAProfileParser


log = logging.getLogger(__name__)

GROUPS = ("mining", "mining_settings", "check_settings", "firegroups", "ships", "miscellaneous", "app", "voiceattack")
_FIRE_BUTTON_PREFIX = "commands - set fire button for "
_CATEGORY_GROUPS = {
    "mining control": "mining",
    "custom keybinds for mining control": "mining",
    "commands - set toggles": "mining_settings",
    "commands - set timers": "mining_settings",
    "commands - set power settings": "mining_settings",
    "commands - set counters": "mining_settings",
    "commands - check status": "check_settings",
    "commands - set firegroups": "firegroups",
    _FIRE_BUTTON_PREFIX: "firegroups",
    "commands - macros fg": "firegroups",
    "commands - weapons": "firegroups",
    "ship commands": "ships",
    "commands - flight throttle": "ships",
    "commands - mode switches": "ships",
    "commands - panels": "ships",
    "commands - misc": "miscellaneous",
    "commands - miscellaneous": "miscellaneous",
    "miscellaneous": "miscellaneous",
    "commands target": "ships",
    "trackir": "ships",
    "elitemining app commands": "app",
    "elitemining - information": "app",
    "voiceattack - control": "voiceattack",
}
_BRACKETS = re.compile(r"\[([^\[\]]*)\]")
_NUMBER_RANGE = re.compile(r"(\d+)\s*\.\.\s*(\d+)")
_TOGGLE = re.compile(r"(enable|disable|turn on|turn off) (.+)", re.IGNORECASE)
_TOGGLE_PAIRS = {
    "enable": ("disable", "Enable or disable"),
    "disable": ("enable", "Enable or disable"),
    "turn on": ("turn off", "Turn on or off"),
    "turn off": ("turn on", "Turn on or off"),
}


@dataclass(frozen=True)
class ReferencePhrase:
    main: str
    detail: str
    variants: tuple[str, ...]


@dataclass(frozen=True)
class ReferenceEntry:
    group: str
    phrases: tuple[ReferencePhrase, ...]
    description: str


@dataclass(frozen=True)
class ReferenceRow:
    group: str
    main_phrase: str
    other_phrases: tuple[str, ...]
    description: str


def is_hidden_category(category: str) -> bool:
    category = category.strip()
    return category in ("", "Dev's commands", "EliteApi", "SRV commands") or category.startswith("Called Commands")


@cache
def category_group(category: str) -> str | None:
    if is_hidden_category(category):
        return None
    name = " ".join(category.split())
    # Category instructions can change independently of the name used to group commands.
    name = re.sub(r" \(.*\)$", "", name).casefold()
    if name.startswith(_FIRE_BUTTON_PREFIX):
        name = _FIRE_BUTTON_PREFIX
    group = _CATEGORY_GROUPS.get(name)
    if group is None:
        log.info("Unmapped VoiceAttack command category: %s", category)
    return group


def _clean_phrase(phrase: str) -> str:
    phrase = " ".join(phrase.split())
    return phrase[:1].upper() + phrase[1:]


def _format_phrase(phrase: str) -> ReferencePhrase:
    main_parts, detail_parts, choices = [], [], []
    # Keep the choices searchable even when the table only shows the first one.
    for index, part in enumerate(_BRACKETS.split(phrase)):
        if index % 2 == 0:
            main = detail = part
            variants = (part,)
        elif number_range := _NUMBER_RANGE.fullmatch(part.strip()):
            main = detail = f"{number_range[1]}–{number_range[2]}"
            variants = (main,)
        else:
            variants = tuple(choice.strip() for choice in part.split(";"))
            words = [word for word in variants if word]
            if len(words) >= 4:
                main = detail = f"{words[0]} … {words[-1]}"
            else:
                main = words[0] if words else ""
                detail = ", ".join(words[:-1]) + f" or {words[-1]}" if len(words) > 1 else main
            if detail and "" in variants:
                detail = f"({detail})"
        main_parts.append(main)
        detail_parts.append(detail)
        choices.append(variants)

    return ReferencePhrase(
        main=_clean_phrase("".join(main_parts)),
        detail=_clean_phrase("".join(detail_parts)),
        variants=tuple(dict.fromkeys(_clean_phrase("".join(words)) for words in product(*choices))),
    )


def _command_phrases(command: str) -> tuple[ReferencePhrase, ...]:
    # VoiceAttack also uses semicolons inside bracket choices.
    names = [_clean_phrase(name) for name in re.split(r";(?![^\[\]]*\])", command) if name.strip()]
    indices = {name.casefold(): index for index, name in enumerate(names)}
    phrases = []
    merged = set()
    for index, name in enumerate(names):
        if index in merged:
            continue
        phrase = _format_phrase(name)
        if toggle := _TOGGLE.fullmatch(name):
            partner, summary = _TOGGLE_PAIRS[toggle[1].casefold()]
            other_index = indices.get(f"{partner} {toggle[2]}".casefold())
            if other_index is not None and other_index > index:
                merged.add(other_index)
                combined = _format_phrase(f"{summary} {toggle[2]}")
                phrase = ReferencePhrase(combined.main, combined.detail,
                                         phrase.variants + _format_phrase(names[other_index]).variants)
        phrases.append(phrase)
    return tuple(phrases)


def load_reference(profile_path: str | Path) -> list[ReferenceEntry]:
    parser = VAProfileParser()
    entries = []
    for command in parser.get_all_commands(parser.parse(profile_path)):
        group = category_group(command.findtext("Category") or "")
        name = (command.findtext("CommandString") or "").strip()
        if not group or not name or is_internal_command(name):
            continue
        if group not in ("ships", "miscellaneous") and command.findtext("UseSpokenPhrase") == "false":
            continue
        phrases = _command_phrases(name)
        if phrases:
            description = (command.findtext("Description") or "").strip()
            entries.append(ReferenceEntry(group, phrases, description))
    return entries


def reference_rows(entries: list[ReferenceEntry], group: str, search: str = ""):
    query = search.strip().casefold()
    for entry in entries:
        if query:
            for index, phrase in enumerate(entry.phrases):
                match = next((text for text in (*phrase.variants, phrase.main) if query in text.casefold()), None)
                if match is not None:
                    break
            else:
                continue
        elif entry.group == group:
            index, match = 0, entry.phrases[0].main
        else:
            continue
        yield ReferenceRow(entry.group, match,
                           tuple(phrase.detail for i, phrase in enumerate(entry.phrases) if i != index),
                           entry.description)
