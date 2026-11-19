"""
VoiceAttack Keybind Applier
Applies keybinds to VoiceAttack profile XML (VoiceAttack 2 export element names)
"""

import xml.etree.ElementTree as ET
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
try:
    from app.va_keybind_extractor import CommandKeybinds, MOUSE_BUTTON_ELEMENTS, command_phrases, is_internal_command
    from app.va_command_renames import COMMAND_RENAMES
except ImportError:
    from va_keybind_extractor import CommandKeybinds, MOUSE_BUTTON_ELEMENTS, command_phrases, is_internal_command
    from va_command_renames import COMMAND_RENAMES

logger = logging.getLogger(__name__)

XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"

# Reasons a binding was not applied
NO_MATCH = "no_match"
AMBIGUOUS = "ambiguous"
VARIABLE = "variable"


@dataclass
class MergeResult:
    applied: List[str] = field(default_factory=list)  # old command names
    matched_by: Dict[str, str] = field(default_factory=dict)  # old name -> exact/renamed/phrase
    not_applied: List[Tuple[str, str]] = field(default_factory=list)  # (old name, reason)


class VAKeybindApplier:
    """Apply keybinds to VoiceAttack profile XML"""

    def __init__(self, renames: Optional[Dict[str, str]] = None):
        self.renames = COMMAND_RENAMES if renames is None else renames
        self.last_result = MergeResult()

    def apply(self, profile_xml: ET.ElementTree,
              keybinds: Dict[str, CommandKeybinds]) -> ET.ElementTree:
        """Apply keybinds to the new profile; the outcome is left in self.last_result."""
        result = MergeResult()
        targets: Dict[str, ET.Element] = {}
        for command in profile_xml.findall(".//Command"):
            name = self.get_command_name(command)
            if name and not is_internal_command(name) and name not in targets:
                targets[name] = command

        claimed: Dict[str, str] = {}  # new command name -> old name
        pending: List[str] = []

        for old_name in keybinds:
            if old_name in targets:
                claimed[old_name] = old_name
                result.matched_by[old_name] = "exact"
            else:
                pending.append(old_name)

        still_pending = []
        for old_name in pending:
            new_name = self.renames.get(old_name)
            if new_name and new_name in targets and new_name not in claimed:
                claimed[new_name] = old_name
                result.matched_by[old_name] = "renamed"
            else:
                still_pending.append(old_name)

        # Shared-phrase fallback: only an unambiguous, one-to-one match is applied
        phrase_owner: Dict[str, List[str]] = {}
        for new_name in targets:
            if new_name in claimed:
                continue
            for phrase in command_phrases(new_name):
                phrase_owner.setdefault(phrase, []).append(new_name)

        picks: Dict[str, str] = {}
        for old_name in still_pending:
            candidates = {n for p in command_phrases(old_name) for n in phrase_owner.get(p, [])}
            if len(candidates) == 1:
                picks[old_name] = next(iter(candidates))
            elif len(candidates) > 1:
                result.not_applied.append((old_name, AMBIGUOUS))
            else:
                result.not_applied.append((old_name, NO_MATCH))
        pick_counts: Dict[str, int] = {}
        for new_name in picks.values():
            pick_counts[new_name] = pick_counts.get(new_name, 0) + 1
        for old_name, new_name in picks.items():
            if pick_counts[new_name] > 1:
                result.not_applied.append((old_name, AMBIGUOUS))
            else:
                claimed[new_name] = old_name
                result.matched_by[old_name] = "phrase"

        for new_name, old_name in claimed.items():
            self.apply_keybinds_to_command(targets[new_name], keybinds[old_name])
            result.applied.append(old_name)

        logger.info(f"Applied keybinds: {len(result.applied)} applied, {len(result.not_applied)} not applied")
        for old_name, reason in result.not_applied:
            logger.warning(f"Keybind not applied ({reason}): {old_name}")
        self.last_result = result
        return profile_xml

    def apply_keybinds_to_command(self, command: ET.Element, kb: CommandKeybinds):
        """Apply the enabled binding groups of one command"""
        if kb.use_shortcut:
            self._set(command, "UseShortcut", True)
            self._set(command, "keyValue", kb.key_value)
            self._set(command, "keyShift", kb.key_shift)
            self._set(command, "keyAlt", kb.key_alt)
            self._set(command, "keyCtrl", kb.key_ctrl)
            self._set(command, "keyWin", kb.key_win)
            self._set(command, "keyPassthru", kb.key_passthru)
            self._set(command, "onlyKeyUp", kb.key_up)
            self._set(command, "RepeatIfKeysDown", kb.repeat_if_keys_down)
            self._set(command, "HotkeyDoubleTapLevel", kb.hotkey_double_tap_level)
            self._set(command, "HotkeyLongTapLevel", kb.hotkey_long_tap_level)

        if kb.use_joystick:
            self._set(command, "UseJoystick", True)
            self._set(command, "joystickNumber", kb.joystick_number)
            self._set(command, "joystickButton", kb.joystick_button)
            self._set(command, "joystickNumber2", kb.joystick_number2)
            self._set(command, "joystickButton2", kb.joystick_button2)
            self._set(command, "joystickUp", kb.joystick_up)
            self._set(command, "joystickExclusive", kb.joystick_exclusive)
            self._set(command, "RepeatIfJoystickDown", kb.repeat_if_joystick_down)
            self._set(command, "JoystickDoubleTapLevel", kb.joystick_double_tap_level)
            self._set(command, "JoystickLongTapLevel", kb.joystick_long_tap_level)

        if kb.use_mouse:
            self._set(command, "UseMouse", True)
            for elem_name, value in zip(MOUSE_BUTTON_ELEMENTS, kb.mouse_buttons):
                self._set(command, elem_name, value)
            self._set(command, "MouseUpOnly", kb.mouse_up_only)
            if kb.mouse_passthru is not None:
                self._set(command, "MousePassThru", kb.mouse_passthru)
            self._set(command, "RepeatIfMouseDown", kb.repeat_if_mouse_down)
            self._set(command, "MouseDoubleTapLevel", kb.mouse_double_tap_level)
            self._set(command, "MouseLongTapLevel", kb.mouse_long_tap_level)

        self._set(command, "KeepRepeating", kb.keep_repeating)
        self._set(command, "Enabled", kb.enabled)

    def _set(self, command: ET.Element, elem_name: str, value):
        elem = command.find(elem_name)
        if elem is None:
            elem = ET.SubElement(command, elem_name)
        elem.attrib.pop(XSI_NIL, None)
        if isinstance(value, bool):
            elem.text = "true" if value else "false"
        else:
            elem.text = str(value)

    def get_command_name(self, command: ET.Element) -> str:
        """Get command name"""
        name_elem = command.find("CommandString")
        if name_elem is not None and name_elem.text:
            return name_elem.text
        return ""
