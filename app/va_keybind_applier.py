"""
VoiceAttack Keybind Applier
Applies keybinds to VoiceAttack profile XML
"""

import xml.etree.ElementTree as ET
import logging
from typing import Dict
from app.va_keybind_extractor import CommandKeybinds

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
                keybinds.joystick_release
            )
        
        # Apply mouse shortcut
        if keybinds.mouse_shortcut:
            self.set_mouse_shortcut(
                command,
                keybinds.mouse_shortcut,
                keybinds.mouse_release
            )
        
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
    
    def set_joystick_shortcut(self, command: ET.Element, shortcut: str, release: bool = False):
        """Set joystick shortcut on command"""
        use_joystick = command.find("UseJoystick")
        if use_joystick is None:
            use_joystick = ET.SubElement(command, "UseJoystick")
        use_joystick.text = "true"
        
        shortcut_elem = command.find("JoystickValue")
        if shortcut_elem is None:
            shortcut_elem = ET.SubElement(command, "JoystickValue")
        shortcut_elem.text = shortcut
        
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
