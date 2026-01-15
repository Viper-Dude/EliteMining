"""
Clear all keybinds from VoiceAttack profile
Creates clean profile for installer with no keybinds
"""

import sys
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent.parent.parent / "app"
sys.path.insert(0, str(app_dir))

from va_profile_parser import VAProfileParser

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def clear_keybinds_from_profile(input_profile: str, output_profile: str):
    """
    Remove all keybinds from profile
    
    Args:
        input_profile: Path to source profile
        output_profile: Path to save cleaned profile
    """
    logger.info("="*60)
    logger.info("Clearing Keybinds from Profile")
    logger.info("="*60)
    
    # Parse profile
    logger.info(f"\nReading: {input_profile}")
    parser = VAProfileParser()
    tree = parser.parse(input_profile)
    
    # Clear keybinds from all commands
    cleared_count = 0
    
    for command in tree.findall(".//Command"):
        cmd_name_elem = command.find("CommandString")
        cmd_name = cmd_name_elem.text if cmd_name_elem is not None else "Unknown"
        
        had_keybind = False
        
        # Remove keyboard shortcut elements
        use_shortcut = command.find("UseShortcut")
        if use_shortcut is not None and use_shortcut.text == "true":
            had_keybind = True
        if use_shortcut is not None:
            command.remove(use_shortcut)
        
        shortcut_value = command.find("CommandKeyValue")
        if shortcut_value is not None:
            command.remove(shortcut_value)
        
        keys_released = command.find("KeysReleased")
        if keys_released is not None:
            command.remove(keys_released)
        
        # Remove joystick shortcut elements (CORRECT element names)
        use_joystick = command.find("UseJoystick")
        if use_joystick is not None and use_joystick.text == "true":
            had_keybind = True
        if use_joystick is not None:
            command.remove(use_joystick)
        
        # Remove lowercase joystick elements
        joystick_num = command.find("joystickNumber")
        if joystick_num is not None:
            command.remove(joystick_num)
        
        joystick_btn = command.find("joystickButton")
        if joystick_btn is not None:
            command.remove(joystick_btn)
        
        joystick_num2 = command.find("joystickNumber2")
        if joystick_num2 is not None:
            command.remove(joystick_num2)
        
        joystick_btn2 = command.find("joystickButton2")
        if joystick_btn2 is not None:
            command.remove(joystick_btn2)
        
        joystick_up = command.find("joystickUp")
        if joystick_up is not None:
            command.remove(joystick_up)
        
        joystick_exclusive = command.find("joystickExclusive")
        if joystick_exclusive is not None:
            command.remove(joystick_exclusive)
        
        joystick_value = command.find("JoystickValue")
        if joystick_value is not None:
            command.remove(joystick_value)
        
        joystick_released = command.find("JoystickButtonsReleased")
        if joystick_released is not None:
            command.remove(joystick_released)
        
        # Remove mouse shortcut elements
        use_mouse = command.find("UseMouse")
        if use_mouse is not None and use_mouse.text == "true":
            had_keybind = True
        if use_mouse is not None:
            command.remove(use_mouse)
        
        # Remove all Mouse elements
        for i in range(1, 10):
            mouse_elem = command.find(f"Mouse{i}")
            if mouse_elem is not None:
                command.remove(mouse_elem)
        
        mouse_up = command.find("MouseUpOnly")
        if mouse_up is not None:
            command.remove(mouse_up)
        
        mouse_pass = command.find("MousePassThru")
        if mouse_pass is not None:
            command.remove(mouse_pass)
        
        mouse_value = command.find("MouseValue")
        if mouse_value is not None:
            command.remove(mouse_value)
        
        mouse_released = command.find("MouseButtonsReleased")
        if mouse_released is not None:
            command.remove(mouse_released)
        
        # Remove shortcut options (long press, double tap, etc.)
        # These are the ACTUAL element names used by VoiceAttack
        shortcut_options_to_remove = [
            # Invoked flags
            "DoubleTapInvoked",
            "LongTapInvoked",
            "ShortTapDelayedInvoked",
            # Level settings (controls which input triggers long/double tap)
            "HotkeyDoubleTapLevel",
            "MouseDoubleTapLevel",
            "JoystickDoubleTapLevel",
            "HotkeyLongTapLevel",
            "MouseLongTapLevel",
            "JoystickLongTapLevel",
            # Repeat settings
            "KeepRepeating",
            "RepeatIfKeysDown",
            "RepeatIfMouseDown",
            "RepeatIfJoystickDown",
            # Variable shortcuts
            "UseVariableMouseShortcut",
            "UseVariableJoystickShortcut",
            "VariableJoystickShortcut",
            "VariableMouseShortcut",
            # Other options
            "NoOtherKeysDown",
            "NoOtherMouseButtonsDown",
            "NoOtherJoystickButtonsDown",
            # Legacy names (just in case)
            "DoubleTap",
            "LongPress",
            "InvokeOnSingleTap",
            "InvokeOnShortPress",
            "NoOtherButtonsDown",
            "RepeatWhileHeld",
        ]
        
        for option_name in shortcut_options_to_remove:
            option_elem = command.find(option_name)
            if option_elem is not None:
                command.remove(option_elem)
        
        if had_keybind:
            cleared_count += 1
            logger.debug(f"  Cleared: {cmd_name}")
    
    # Save cleaned profile
    logger.info(f"\n✓ Cleared keybinds from {cleared_count} commands")
    logger.info(f"\nSaving: {output_profile}")
    
    tree.write(output_profile, encoding='utf-8', xml_declaration=True)
    
    logger.info("\n✓ Clean profile created successfully!")
    logger.info("="*60)


def main():
    """Main entry point"""
    
    # Standard path for VoiceAttack profile
    project_root = Path(__file__).parent.parent.parent
    standard_profile_dir = project_root / "Voiceattack Profile"
    
    # Check if arguments provided
    if len(sys.argv) >= 2:
        input_profile = sys.argv[1]
        if len(sys.argv) >= 3:
            output_profile = sys.argv[2]
        else:
            input_path = Path(input_profile)
            output_profile = str(input_path.parent / f"{input_path.stem}-Clean{input_path.suffix}")
    else:
        # Interactive mode
        print("\n" + "="*60)
        print("VoiceAttack Profile Keybind Cleaner")
        print("="*60)
        
        # Find profile in standard directory
        if standard_profile_dir.exists():
            profiles = list(standard_profile_dir.glob("EliteMining*.vap"))
            if profiles:
                # Use the most recent profile
                profiles.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                default_input = str(profiles[0])
                print(f"\nDefault profile directory: {standard_profile_dir}")
                print(f"Found profile: {profiles[0].name}")
            else:
                default_input = ""
        else:
            default_input = ""
        
        # Prompt for input file
        if default_input:
            input_choice = input(f"\nInput profile [{default_input}]: ").strip().strip('"')
            if input_choice:
                # If user entered just a filename (not a full path), resolve it relative to standard dir
                input_path_obj = Path(input_choice)
                if not input_path_obj.is_absolute() and standard_profile_dir.exists():
                    input_profile = str(standard_profile_dir / input_choice)
                else:
                    input_profile = input_choice
            else:
                input_profile = default_input
        else:
            input_profile = input("\nEnter input profile path: ").strip().strip('"')
        
        # Suggest output file in same directory
        input_path = Path(input_profile)
        suggested_output = str(input_path.parent / f"{input_path.stem}-Clean{input_path.suffix}")
        
        output_choice = input(f"\nOutput file [{suggested_output}]: ").strip().strip('"')
        if output_choice:
            # If user entered just a filename (not a full path), resolve it relative to input file's directory
            output_path_obj = Path(output_choice)
            if not output_path_obj.is_absolute():
                output_profile = str(input_path.parent / output_choice)
            else:
                output_profile = output_choice
        else:
            output_profile = suggested_output
        
        print()
    
    if not Path(input_profile).exists():
        logger.error(f"Input profile not found: {input_profile}")
        return 1
    
    try:
        clear_keybinds_from_profile(input_profile, output_profile)
        return 0
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
