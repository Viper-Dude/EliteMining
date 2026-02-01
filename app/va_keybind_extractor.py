"""
VoiceAttack Keybind Extractor
Extracts keybinds from VoiceAttack profile XML
"""

import xml.etree.ElementTree as ET
import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CommandKeybinds:
    """Keybinds for a single command"""
    command_name: str
    keyboard_shortcut: Optional[str] = None
    keyboard_release: bool = False
    joystick_shortcut: Optional[str] = None
    joystick_release: bool = False
    joystick_number: Optional[str] = None
    joystick_button: Optional[str] = None
    joystick_number2: Optional[str] = None
    joystick_button2: Optional[str] = None
    mouse_shortcut: Optional[str] = None
    mouse_release: bool = False
    enabled: bool = True
    # Shortcut options (using correct VoiceAttack element names)
    double_tap_invoked: bool = False  # "Shortcut is invoked when pressed twice (double tap)"
    long_tap_invoked: bool = False  # "Shortcut is invoked when long-pressed"
    short_tap_delayed_invoked: bool = False  # "Invoke also on short/standard press (Advanced)"
    # Level settings (0=disabled, 1=keyboard, 2=mouse, 3=joystick)
    hotkey_double_tap_level: int = 0
    mouse_double_tap_level: int = 0
    joystick_double_tap_level: int = 0
    hotkey_long_tap_level: int = 0
    mouse_long_tap_level: int = 0
    joystick_long_tap_level: int = 0
    # Repeat settings
    keep_repeating: bool = False
    repeat_if_keys_down: bool = False
    repeat_if_mouse_down: bool = False
    repeat_if_joystick_down: bool = False
    # No other buttons
    no_other_keys_down: bool = False
    no_other_mouse_buttons_down: bool = False
    no_other_joystick_buttons_down: bool = False
    # Variable shortcuts
    use_variable_joystick_shortcut: bool = False
    use_variable_mouse_shortcut: bool = False


class VAKeybindExtractor:
    """Extract keybinds from VoiceAttack profile XML"""
    
    def extract(self, profile_xml: ET.ElementTree) -> Dict[str, CommandKeybinds]:
        """
        Extract all keybinds from profile
        
        Args:
            profile_xml: Parsed profile XML tree
            
        Returns:
            Dict mapping command name to keybinds
        """
        keybinds = {}
        
        for command in profile_xml.findall(".//Command"):
            cmd_name = self.get_command_name(command)
            if not cmd_name:
                continue
            
            keybinds[cmd_name] = CommandKeybinds(
                command_name=cmd_name,
                keyboard_shortcut=self.extract_keyboard_shortcut(command),
                keyboard_release=self.get_keyboard_release(command),
                joystick_shortcut=self.extract_joystick_shortcut(command),
                joystick_release=self.get_joystick_release(command),
                joystick_number=self.get_joystick_number(command),
                joystick_button=self.get_joystick_button(command),
                joystick_number2=self.get_joystick_number2(command),
                joystick_button2=self.get_joystick_button2(command),
                mouse_shortcut=self.extract_mouse_shortcut(command),
                mouse_release=self.get_mouse_release(command),
                enabled=self.is_command_enabled(command),
                # Shortcut options (correct VoiceAttack element names)
                double_tap_invoked=self.get_bool_option(command, "DoubleTapInvoked"),
                long_tap_invoked=self.get_bool_option(command, "LongTapInvoked"),
                short_tap_delayed_invoked=self.get_bool_option(command, "ShortTapDelayedInvoked"),
                # Level settings
                hotkey_double_tap_level=self.get_int_option(command, "HotkeyDoubleTapLevel"),
                mouse_double_tap_level=self.get_int_option(command, "MouseDoubleTapLevel"),
                joystick_double_tap_level=self.get_int_option(command, "JoystickDoubleTapLevel"),
                hotkey_long_tap_level=self.get_int_option(command, "HotkeyLongTapLevel"),
                mouse_long_tap_level=self.get_int_option(command, "MouseLongTapLevel"),
                joystick_long_tap_level=self.get_int_option(command, "JoystickLongTapLevel"),
                # Repeat settings
                keep_repeating=self.get_bool_option(command, "KeepRepeating"),
                repeat_if_keys_down=self.get_bool_option(command, "RepeatIfKeysDown"),
                repeat_if_mouse_down=self.get_bool_option(command, "RepeatIfMouseDown"),
                repeat_if_joystick_down=self.get_bool_option(command, "RepeatIfJoystickDown"),
                # No other buttons
                no_other_keys_down=self.get_bool_option(command, "NoOtherKeysDown"),
                no_other_mouse_buttons_down=self.get_bool_option(command, "NoOtherMouseButtonsDown"),
                no_other_joystick_buttons_down=self.get_bool_option(command, "NoOtherJoystickButtonsDown"),
                # Variable shortcuts
                use_variable_joystick_shortcut=self.get_bool_option(command, "UseVariableJoystickShortcut"),
                use_variable_mouse_shortcut=self.get_bool_option(command, "UseVariableMouseShortcut"),
            )
        
        # Filter to only commands with actual keybinds
        # Include commands with keyboard, mouse, or joystick shortcuts
        # Exclude joystick 0 button 0 (means no keybind set)
        def has_real_keybind(kb):
            if kb.keyboard_shortcut or kb.mouse_shortcut:
                return True
            if kb.joystick_shortcut:
                # Exclude "Joystick 0 Button 0" which means no keybind
                if kb.joystick_shortcut == "Joystick 0 Button 0":
                    return False
                return True
            # Also include if joystick_button is set to a real value
            if kb.joystick_button and kb.joystick_button not in ('0', '-1', ''):
                return True
            # Button 0 on joystick 1+ is valid
            if kb.joystick_button == '0' and kb.joystick_number and kb.joystick_number != '0':
                return True
            return False
        
        keybinds_with_bindings = {
            name: kb for name, kb in keybinds.items()
            if has_real_keybind(kb)
        }
        
        logger.info(f"Extracted keybinds from {len(keybinds_with_bindings)} commands")
        return keybinds_with_bindings
    
    def get_command_name(self, command: ET.Element) -> str:
        """Get command's full name"""
        name_elem = command.find("CommandString")
        if name_elem is not None and name_elem.text:
            return name_elem.text
        return ""
    
    def extract_keyboard_shortcut(self, command: ET.Element) -> Optional[str]:
        """Extract keyboard shortcut if present"""
        # Check if keyboard shortcut is enabled
        enabled = command.find("UseShortcut")
        if enabled is None or enabled.text.lower() != "true":
            return None
        
        # Get the shortcut string
        shortcut = command.find("CommandKeyValue")
        if shortcut is not None and shortcut.text:
            return shortcut.text
        
        return None
    
    def get_keyboard_release(self, command: ET.Element) -> bool:
        """Check if keyboard shortcut is on release"""
        release = command.find("KeysReleased")
        if release is not None and release.text.lower() == "true":
            return True
        return False
    
    def extract_joystick_shortcut(self, command: ET.Element) -> Optional[str]:
        """Extract joystick button shortcut if present"""
        # First, try to get the full JoystickValue (handles compound keybinds like "Button 31 + Button 8")
        joystick_value = command.find("JoystickValue")
        if joystick_value is not None and joystick_value.text and joystick_value.text.strip():
            # Return the full joystick value string (may contain compound keybinds)
            value = joystick_value.text
            cmd_name = self.get_command_name(command)
            if '+' in value:
                logger.info(f"[COMPOUND KEYBIND] Extracted compound keybind for '{cmd_name}': {value}")
            return value
        
        # Fallback: construct from individual joystickNumber and joystickButton
        # Note: Extract even if UseJoystick is false, as VA sometimes exports this way
        joystick_num = command.find("joystickNumber")
        joystick_btn = command.find("joystickButton")
        
        if joystick_num is not None and joystick_btn is not None:
            num = joystick_num.text
            btn = joystick_btn.text
            
            # Check if it's actually set (not -1 or 0)
            # Button 0 with joystick 0 means no keybind set
            if btn and btn not in ("-1", "0"):
                # Format: "Joystick 1 Button 25"
                return f"Joystick {num} Button {btn}"
            elif btn == "0" and num and num != "0":
                # Button 0 on joystick 1+ is valid (some HOTAS have button 0)
                return f"Joystick {num} Button {btn}"
        
        return None
    
    def get_joystick_release(self, command: ET.Element) -> bool:
        """Check if joystick shortcut is on release"""
        release = command.find("JoystickButtonsReleased")
        if release is not None and release.text.lower() == "true":
            return True
        return False
    
    def extract_mouse_shortcut(self, command: ET.Element) -> Optional[str]:
        """Extract mouse button shortcut if present"""
        enabled = command.find("UseMouse")
        if enabled is None or enabled.text.lower() != "true":
            return None
        
        shortcut = command.find("MouseValue")
        if shortcut is not None and shortcut.text:
            return shortcut.text
        
        return None
    
    def get_mouse_release(self, command: ET.Element) -> bool:
        """Check if mouse shortcut is on release"""
        release = command.find("MouseButtonsReleased")
        if release is not None and release.text.lower() == "true":
            return True
        return False
    
    def is_command_enabled(self, command: ET.Element) -> bool:
        """Check if command is enabled"""
        enabled = command.find("Enabled")
        if enabled is not None:
            return enabled.text == "True"
        return True  # Default to enabled
    
    def get_bool_option(self, command: ET.Element, element_name: str) -> bool:
        """Get a boolean option from command XML"""
        elem = command.find(element_name)
        if elem is not None and elem.text:
            return elem.text.lower() == "true"
        return False
    
    def get_int_option(self, command: ET.Element, element_name: str) -> int:
        """Get an integer option from command XML"""
        elem = command.find(element_name)
        if elem is not None and elem.text:
            try:
                return int(elem.text)
            except ValueError:
                return 0
        return 0
    
    def get_joystick_number(self, command: ET.Element) -> Optional[str]:
        """Get joystick number"""
        elem = command.find("joystickNumber")
        if elem is not None and elem.text:
            return elem.text
        return None
    
    def get_joystick_button(self, command: ET.Element) -> Optional[str]:
        """Get joystick button"""
        elem = command.find("joystickButton")
        if elem is not None and elem.text:
            return elem.text
        return None

    def get_joystick_number2(self, command: ET.Element) -> Optional[str]:
        """Get second joystick number (for compound keybinds)"""
        elem = command.find("joystickNumber2")
        if elem is not None and elem.text:
            return elem.text
        return None
    
    def get_joystick_button2(self, command: ET.Element) -> Optional[str]:
        """Get second joystick button (for compound keybinds)"""
        elem = command.find("joystickButton2")
        if elem is not None and elem.text:
            return elem.text
        return None
