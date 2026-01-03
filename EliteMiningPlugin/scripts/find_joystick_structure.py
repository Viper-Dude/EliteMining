import xml.etree.ElementTree as ET

tree = ET.parse('EliteMining 4.7.5 testing-Profile.vap')
root = tree.getroot()

commands = root.findall('.//Command')

print("Looking for joystick bindings...\n")

# Find the "deploy weapons" command
for cmd in commands:
    cmd_name = cmd.find('CommandString')
    name = cmd_name.text if cmd_name is not None else "Unknown"
    
    if "deploy weapons" in name.lower() or "start mining" in name.lower():
        print(f"Command: {name}")
        print("\nAll elements:")
        for elem in cmd:
            if elem.text and elem.text.strip():
                print(f"  {elem.tag}: {elem.text}")
        print("\n" + "="*60 + "\n")
        break
