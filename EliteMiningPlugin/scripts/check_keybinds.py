import xml.etree.ElementTree as ET

tree = ET.parse('EliteMining 4.7.5 testing-Profile.vap')
root = tree.getroot()

# Find commands with any keybind-related elements
commands = root.findall('.//Command')

print(f"Total commands: {len(commands)}\n")

# Check first few commands for keybind elements
for i, cmd in enumerate(commands[:5]):
    cmd_name = cmd.find('CommandString')
    name = cmd_name.text if cmd_name is not None else "Unknown"
    
    print(f"Command {i+1}: {name}")
    
    # Check for various keybind elements
    keyboard = cmd.find('CommandKeyValue')
    use_shortcut = cmd.find('UseShortcut')
    joystick_num = cmd.find('JoystickNumber')
    joystick_btn = cmd.find('JoystickButton')
    mouse = cmd.find('MouseButton')
    
    if use_shortcut is not None:
        print(f"  - UseShortcut: {use_shortcut.text}")
    if keyboard is not None:
        print(f"  - CommandKeyValue: '{keyboard.text}'")
    if joystick_num is not None:
        print(f"  - JoystickNumber: {joystick_num.text}")
    if joystick_btn is not None:
        print(f"  - JoystickButton: {joystick_btn.text}")
    if mouse is not None:
        print(f"  - MouseButton: {mouse.text}")
    
    print()

# Count commands with keybinds
keyboard_count = len([c for c in commands if c.find('UseShortcut') is not None and c.find('UseShortcut').text.lower() == 'true'])
joystick_count = len([c for c in commands if c.find('JoystickNumber') is not None and c.find('JoystickNumber').text != '-1'])
mouse_count = len([c for c in commands if c.find('MouseButton') is not None and c.find('MouseButton').text != '-1'])

print(f"Summary:")
print(f"  Commands with keyboard shortcuts: {keyboard_count}")
print(f"  Commands with joystick buttons: {joystick_count}")
print(f"  Commands with mouse buttons: {mouse_count}")
