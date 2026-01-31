"""
VoiceAttack Keybind Applier
Applies keybinds to VoiceAttack profile XML
"""

import xml.etree.ElementTree as ET
import logging
from typing import Dict
try:
    from app.va_keybind_extractor import CommandKeybinds
except ImportError:
    from va_keybind_extractor import CommandKeybinds

logger = logging.getLogger(__name__)


class VAKeybindApplier:
    """Apply keybinds to VoiceAttack profile XML"""
    
    def apply(self, profile_xml: ET.ElementTree, 
              keybinds: Dict[str, CommandKeybinds]) -> ET.ElementTree:
        """
        Apply keybinds to profile
        
        Args:
            profile_xml: New profile XML tree
            keybinds: Keybinds to apply
        
        Returns:
            Modified profile XML tree
        """
        matched = 0
        unmatched = []
        
        for command in profile_xml.findall(".//Command"):
            cmd_name = self.get_command_name(command)
            
            if cmd_name in keybinds:
                self.apply_keybinds_to_command(command, keybinds[cmd_name])
                matched += 1
            else:
                if self.has_any_keybind(command):
                    unmatched.append(cmd_name)
        
        logger.info(f"Applied keybinds: {matched} matched")
        if unmatched:
            logger.warning(f"Unmatched commands with keybinds: {len(unmatched)}")
            logger.debug(f"Unmatched: {unmatched[:10]}")  # Log first 10
        
        return profile_xml
    
    def apply_keybinds_to_command(self, command: ET.Element, 
                                   keybinds: CommandKeybinds):
        """Apply keybinds to a single command"""
        
        # Apply keyboard shortcut
        if keybinds.keyboard_shortcut:
            self.set_keyboard_shortcut(
                command, 
                keybinds.keyboard_shortcut,
                keybinds.keyboard_release
            )
        
        # Apply joystick shortcut
        if keybinds.joystick_shortcut:
            self.set_joystick_shortcut(
                command,
                keybinds.joystick_shortcut,
                keybinds.joystick_release,
                keybinds.joystick_number,
                keybinds.joystick_button,
                keybinds.joystick_number2,
                keybinds.joystick_button2
            )
        
        # Apply mouse shortcut
        if keybinds.mouse_shortcut:
            self.set_mouse_shortcut(
                command,
                keybinds.mouse_shortcut,
                keybinds.mouse_release
            )
        
        # Apply shortcut options
        self.set_shortcut_options(command, keybinds)
        
        # Apply enabled state
        self.set_enabled(command, keybinds.enabled)
    
    def set_keyboard_shortcut(self, command: ET.Element, shortcut: str, release: bool = False):
        """Set keyboard shortcut on command"""
        # Enable keyboard shortcut
        use_shortcut = command.find("UseShortcut")
        if use_shortcut is None:
            use_shortcut = ET.SubElement(command, "UseShortcut")
        use_shortcut.text = "true"
        
        # Set shortcut value
        shortcut_elem = command.find("CommandKeyValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "CommandKeyValue")
        shortcut_elem.text = shortcut
        
        # Set release mode
        release_elem = command.find("KeysReleased")
        if release_elem is None:
            release_elem = ET.SubElement(command, "KeysReleased")
        release_elem.text = "true" if release else "false"
    
    def set_joystick_shortcut(self, command: ET.Element, shortcut: str, release: bool = False,
                               joystick_number: str = None, joystick_button: str = None,
                               joystick_number2: str = None, joystick_button2: str = None):
        """Set joystick shortcut on command"""
        use_joystick = command.find("UseJoystick")
        if use_joystick is None:
            use_joystick = ET.SubElement(command, "UseJoystick")
        use_joystick.text = "true"
        
        shortcut_elem = command.find("JoystickValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "JoystickValue")
        shortcut_elem.text = shortcut
        
        cmd_name = self.get_command_name(command)
        
        # Check if this is a compound keybind (has second button)
        is_compound = joystick_button2 and joystick_button2 not in ('0', '-1', '')
        
        if is_compound:
            logger.info(f"[COMPOUND KEYBIND] Applying compound keybind to '{cmd_name}': Joystick {joystick_number} Button {joystick_button} + Joystick {joystick_number2} Button {joystick_button2}")
        
        # Always set primary joystick number and button
        if joystick_number is not None:
            num_elem = command.find("joystickNumber")
            if num_elem is None:
                num_elem = ET.SubElement(command, "joystickNumber")
            num_elem.text = joystick_number
        
        if joystick_button is not None:
            btn_elem = command.find("joystickButton")
            if btn_elem is None:
                btn_elem = ET.SubElement(command, "joystickButton")
            btn_elem.text = joystick_button
        
        # Set secondary joystick number and button (for compound keybinds)
        num2_elem = command.find("joystickNumber2")
        if num2_elem is None:
            num2_elem = ET.SubElement(command, "joystickNumber2")
        num2_elem.text = joystick_number2 if joystick_number2 else "0"
        
        btn2_elem = command.find("joystickButton2")
        if btn2_elem is None:
            btn2_elem = ET.SubElement(command, "joystickButton2")
        btn2_elem.text = joystick_button2 if joystick_button2 else "0"
        
        if not is_compound:
            logger.debug(f"[SIMPLE KEYBIND] Applied simple keybind to '{cmd_name}': {shortcut}")
        
        release_elem = command.find("JoystickButtonsReleased")
        if release_elem is None:
            release_elem = ET.SubElement(command, "JoystickButtonsReleased")
        release_elem.text = "true" if release else "false"
    
    def set_mouse_shortcut(self, command: ET.Element, shortcut: str, release: bool = False):
        """Set mouse shortcut on command"""
        use_mouse = command.find("UseMouse")
        if use_mouse is None:
            use_mouse = ET.SubElement(command, "UseMouse")
        use_mouse.text = "true"
        
        shortcut_elem = command.find("MouseValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "MouseValue")
        shortcut_elem.text = shortcut
        
        release_elem = command.find("MouseButtonsReleased")
        if release_elem is None:
            release_elem = ET.SubElement(command, "MouseButtonsReleased")
        release_elem.text = "true" if release else "false"
    
    def set_enabled(self, command: ET.Element, enabled: bool):
        """Set command enabled state"""
        enabled_elem = command.find("Enabled")
        if enabled_elem is None:
            enabled_elem = ET.SubElement(command, "Enabled")
        enabled_elem.text = "true" if enabled else "false"    
    def get_command_name(self, command: ET.Element) -> str:
        """Get command name from XML"""
        cmd_name = command.find("CommandString")
        if cmd_name is not None and cmd_name.text:
            return cmd_name.text
        return "Unknown"    
    def set_shortcut_options(self, command: ET.Element, keybinds: CommandKeybinds):
        """Set shortcut options on command using correct VoiceAttack element names"""
        # Boolean options
        bool_options = [
            ("DoubleTapInvoked", keybinds.double_tap_invoked),
            ("LongTapInvoked", keybinds.long_tap_invoked),
            ("ShortTapDelayedInvoked", keybinds.short_tap_delayed_invoked),
            ("KeepRepeating", keybinds.keep_repeating),
            ("RepeatIfKeysDown", keybinds.repeat_if_keys_down),
            ("RepeatIfMouseDown", keybinds.repeat_if_mouse_down),
            ("RepeatIfJoystickDown", keybinds.repeat_if_joystick_down),
            ("NoOtherKeysDown", keybinds.no_other_keys_down),
            ("NoOtherMouseButtonsDown", keybinds.no_other_mouse_buttons_down),
            ("NoOtherJoystickButtonsDown", keybinds.no_other_joystick_buttons_down),
            ("UseVariableJoystickShortcut", keybinds.use_variable_joystick_shortcut),
            ("UseVariableMouseShortcut", keybinds.use_variable_mouse_shortcut),
        ]
        
        for elem_name, value in bool_options:
            elem = command.find(elem_name)
            if elem is None:
                elem = ET.SubElement(command, elem_name)
            elem.text = "true" if value else "false"
        
        # Integer level options
        int_options = [
            ("HotkeyDoubleTapLevel", keybinds.hotkey_double_tap_level),
            ("MouseDoubleTapLevel", keybinds.mouse_double_tap_level),
            ("JoystickDoubleTapLevel", keybinds.joystick_double_tap_level),
            ("HotkeyLongTapLevel", keybinds.hotkey_long_tap_level),
            ("MouseLongTapLevel", keybinds.mouse_long_tap_level),
            ("JoystickLongTapLevel", keybinds.joystick_long_tap_level),
        ]
        
        for elem_name, value in int_options:
            elem = command.find(elem_name)
            if elem is None:
                elem = ET.SubElement(command, elem_name)
            elem.text = str(value)
    
    def clear_shortcut_options(self, command: ET.Element):
        """Clear all shortcut options (reset to defaults)"""
        # Boolean options to set to false
        bool_options_to_clear = [
            "DoubleTapInvoked",
            "LongTapInvoked",
            "ShortTapDelayedInvoked",
            "KeepRepeating",
            "RepeatIfKeysDown",
            "RepeatIfMouseDown",
            "RepeatIfJoystickDown",
            "NoOtherKeysDown",
            "NoOtherMouseButtonsDown",
            "NoOtherJoystickButtonsDown",
            "UseVariableJoystickShortcut",
            "UseVariableMouseShortcut",
            "KeysReleased",
            "JoystickButtonsReleased",
            "MouseButtonsReleased",
        ]
        
        for elem_name in bool_options_to_clear:
            elem = command.find(elem_name)
            if elem is not None:
                elem.text = "false"
        
        # Integer options to set to 0
        int_options_to_clear = [
            "HotkeyDoubleTapLevel",
            "MouseDoubleTapLevel",
            "JoystickDoubleTapLevel",
            "HotkeyLongTapLevel",
            "MouseLongTapLevel",
            "JoystickLongTapLevel",
        ]
        
        for elem_name in int_options_to_clear:
            elem = command.find(elem_name)
            if elem is not None:
                elem.text = "0"
    
    def get_command_name(self, command: ET.Element) -> str:
        """Get command name"""
        name_elem = command.find("CommandString")
        if name_elem is not None and name_elem.text:
            return name_elem.text
        return ""
    
    def has_any_keybind(self, command: ET.Element) -> bool:
        """Check if command has any keybind"""
        has_keyboard = command.find("UseShortcut")
        has_joystick = command.find("UseJoystick")
        has_mouse = command.find("UseMouse")
        
        return (
            (has_keyboard is not None and has_keyboard.text == "true") or
            (has_joystick is not None and has_joystick.text == "true") or
            (has_mouse is not None and has_mouse.text == "true")
        )
