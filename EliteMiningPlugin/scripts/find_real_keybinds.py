import xml.etree.ElementTree as ET

tree = ET.parse('EliteMining 4.7.5 testing-Profile.vap')
root = tree.getroot()

commands = root.findall('.//Command')

print("Looking for commands with actual keybinds...\n")

for cmd in commands:
    cmd_name = cmd.find('CommandString')
    name = cmd_name.text if cmd_name is not None else "Unknown"
    
    # Find commands with actual values
    keyboard = cmd.find('CommandKeyValue')
    joystick = cmd.find('JoystickValue')  
    mouse = cmd.find('MouseValue')
    
    has_keybind = False
    
    if keyboard is not None and keyboard.text:
        print(f"✓ {name}")
        print(f"  Keyboard: {keyboard.text}")
        has_keybind = True
    
    if joystick is not None and joystick.text:
        if not has_keybind:
            print(f"✓ {name}")
        print(f"  Joystick: {joystick.text}")
        has_keybind = True
    
    if mouse is not None and mouse.text:
        if not has_keybind:
            print(f"✓ {name}")
        print(f"  Mouse: {mouse.text}")
        has_keybind = True
    
    if has_keybind:
        print()
