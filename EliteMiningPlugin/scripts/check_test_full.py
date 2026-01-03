import xml.etree.ElementTree as ET

tree = ET.parse('EliteMining 4.7.5 testing-Profile.vap')
root = tree.getroot()

# Find Test command
commands = root.findall('.//Command')
for cmd in commands:
    name_elem = cmd.find('CommandString')
    if name_elem is not None and name_elem.text == 'Test':
        print("Found 'Test' command!")
        print("\nAll elements:")
        for elem in cmd:
            print(f"  {elem.tag}: {elem.text if elem.text else '(empty)'}")
        break
