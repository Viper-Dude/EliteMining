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
    mouse_shortcut: Optional[str] = None
    mouse_release: bool = False
    enabled: bool = True


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
                mouse_shortcut=self.extract_mouse_shortcut(command),
                mouse_release=self.get_mouse_release(command),
                enabled=self.is_command_enabled(command)
            )
        
        # Filter to only commands with keybinds
        keybinds_with_bindings = {
            name: kb for name, kb in keybinds.items()
            if kb.keyboard_shortcut or kb.joystick_shortcut or kb.mouse_shortcut
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
        enabled = command.find("UseJoystick")
        if enabled is None or enabled.text.lower() != "true":
            return None
        
        # Get joystick number and button
        joystick_num = command.find("joystickNumber")
        joystick_btn = command.find("joystickButton")
        
        if joystick_num is not None and joystick_btn is not None:
            num = joystick_num.text
            btn = joystick_btn.text
            
            # Check if it's actually set (not -1 or 0)
            if btn and btn != "-1":
                # Format: "Joystick 1 Button 25"
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
