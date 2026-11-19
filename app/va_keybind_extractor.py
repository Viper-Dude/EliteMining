"""
VoiceAttack Keybind Extractor
Extracts keybinds from VoiceAttack profile XML (VoiceAttack 2 export element names)
"""

import xml.etree.ElementTree as ET
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MOUSE_BUTTON_ELEMENTS = tuple(f"Mouse{i}" for i in range(1, 10))


@dataclass
class CommandKeybinds:
    """Keybinds for a single command. A group is only applied when its use_* flag is set."""
    command_name: str
    enabled: bool = True
    keep_repeating: bool = False
    # Keyboard
    use_shortcut: bool = False
    key_value: str = "0"
    key_shift: str = "0"
    key_alt: str = "0"
    key_ctrl: str = "0"
    key_win: str = "0"
    key_passthru: bool = False
    key_up: bool = False
    repeat_if_keys_down: bool = False
    hotkey_double_tap_level: int = 0
    hotkey_long_tap_level: int = 0
    # Joystick
    use_joystick: bool = False
    joystick_number: str = "0"
    joystick_button: str = "0"
    joystick_number2: str = "0"
    joystick_button2: str = "0"
    joystick_up: bool = False
    joystick_exclusive: bool = False
    repeat_if_joystick_down: bool = False
    joystick_double_tap_level: int = 0
    joystick_long_tap_level: int = 0
    # Mouse
    use_mouse: bool = False
    mouse_buttons: Tuple[bool, ...] = (False,) * 9
    mouse_up_only: bool = False
    mouse_passthru: Optional[bool] = None
    repeat_if_mouse_down: bool = False
    mouse_double_tap_level: int = 0
    mouse_long_tap_level: int = 0

    def has_binding(self) -> bool:
        return self.use_shortcut or self.use_joystick or self.use_mouse


def is_internal_command(name: str) -> bool:
    """Commands named ((...)) are called by other commands and are never bound."""
    return name.startswith("((")


def command_phrases(name: str) -> List[str]:
    """Spoken phrases of a command, lower-cased."""
    return [p.strip().lower() for p in name.split(";") if p.strip()]


class VAKeybindExtractor:
    """Extract keybinds from VoiceAttack profile XML"""

    def __init__(self):
        # (command name, reason) for bindings that are never carried over
        self.skipped: List[Tuple[str, str]] = []

    def extract(self, profile_xml: ET.ElementTree) -> Dict[str, CommandKeybinds]:
        """Return command name -> keybinds, only for commands with a binding."""
        self.skipped = []
        keybinds = {}

        for command in profile_xml.findall(".//Command"):
            cmd_name = self.get_command_name(command)
            if not cmd_name or is_internal_command(cmd_name):
                continue

            kb = CommandKeybinds(
                command_name=cmd_name,
                enabled=self.is_command_enabled(command),
                keep_repeating=self.get_bool_option(command, "KeepRepeating"),
                use_shortcut=self.get_bool_option(command, "UseShortcut"),
                key_value=self.get_text(command, "keyValue"),
                key_shift=self.get_text(command, "keyShift"),
                key_alt=self.get_text(command, "keyAlt"),
                key_ctrl=self.get_text(command, "keyCtrl"),
                key_win=self.get_text(command, "keyWin"),
                key_passthru=self.get_bool_option(command, "keyPassthru"),
                key_up=self.get_bool_option(command, "onlyKeyUp"),
                repeat_if_keys_down=self.get_bool_option(command, "RepeatIfKeysDown"),
                hotkey_double_tap_level=self.get_int_option(command, "HotkeyDoubleTapLevel"),
                hotkey_long_tap_level=self.get_int_option(command, "HotkeyLongTapLevel"),
                use_joystick=self.get_bool_option(command, "UseJoystick"),
                joystick_number=self.get_text(command, "joystickNumber"),
                joystick_button=self.get_text(command, "joystickButton"),
                joystick_number2=self.get_text(command, "joystickNumber2"),
                joystick_button2=self.get_text(command, "joystickButton2"),
                joystick_up=self.get_bool_option(command, "joystickUp"),
                joystick_exclusive=self.get_bool_option(command, "joystickExclusive"),
                repeat_if_joystick_down=self.get_bool_option(command, "RepeatIfJoystickDown"),
                joystick_double_tap_level=self.get_int_option(command, "JoystickDoubleTapLevel"),
                joystick_long_tap_level=self.get_int_option(command, "JoystickLongTapLevel"),
                use_mouse=self.get_bool_option(command, "UseMouse"),
                mouse_buttons=tuple(self.get_bool_option(command, n) for n in MOUSE_BUTTON_ELEMENTS),
                mouse_up_only=self.get_bool_option(command, "MouseUpOnly"),
                mouse_passthru=self.get_nullable_bool(command, "MousePassThru"),
                repeat_if_mouse_down=self.get_bool_option(command, "RepeatIfMouseDown"),
                mouse_double_tap_level=self.get_int_option(command, "MouseDoubleTapLevel"),
                mouse_long_tap_level=self.get_int_option(command, "MouseLongTapLevel"),
            )

            # The variable's name is not mapped; a variable shortcut without a name crashes VoiceAttack.
            variable = False
            for use_attr, flag in (("use_shortcut", "UseVariableHotkey"),
                                   ("use_mouse", "UseVariableMouseShortcut"),
                                   ("use_joystick", "UseVariableJoystickShortcut")):
                if self.get_bool_option(command, flag) and getattr(kb, use_attr):
                    setattr(kb, use_attr, False)
                    variable = True
            if variable:
                self.skipped.append((cmd_name, "variable"))

            if kb.has_binding():
                keybinds[cmd_name] = kb

        logger.info(f"Extracted keybinds from {len(keybinds)} commands")
        return keybinds

    def get_command_name(self, command: ET.Element) -> str:
        """Get command's full name"""
        name_elem = command.find("CommandString")
        if name_elem is not None and name_elem.text:
            return name_elem.text
        return ""

    def is_command_enabled(self, command: ET.Element) -> bool:
        """Check if command is enabled"""
        enabled = command.find("Enabled")
        if enabled is not None and enabled.text:
            return enabled.text.strip().lower() == "true"
        return True  # Default to enabled

    def get_text(self, command: ET.Element, element_name: str, default: str = "0") -> str:
        elem = command.find(element_name)
        if elem is not None and elem.text and elem.text.strip():
            return elem.text.strip()
        return default

    def get_bool_option(self, command: ET.Element, element_name: str) -> bool:
        """Get a boolean option from command XML"""
        elem = command.find(element_name)
        if elem is not None and elem.text:
            return elem.text.strip().lower() == "true"
        return False

    def get_nullable_bool(self, command: ET.Element, element_name: str) -> Optional[bool]:
        elem = command.find(element_name)
        if elem is not None and elem.text and elem.text.strip():
            return elem.text.strip().lower() == "true"
        return None

    def get_int_option(self, command: ET.Element, element_name: str) -> int:
        """Get an integer option from command XML"""
        elem = command.find(element_name)
        if elem is not None and elem.text:
            try:
                return int(elem.text)
            except ValueError:
                return 0
        return 0
