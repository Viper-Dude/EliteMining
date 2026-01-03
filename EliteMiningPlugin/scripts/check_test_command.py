from app.va_profile_parser import VAProfileParser
from app.va_keybind_extractor import VAKeybindExtractor

# Parse profile
tree = VAProfileParser().parse('EliteMining 4.7.5 testing-Profile.vap')

# Extract keybinds
keybinds = VAKeybindExtractor().extract(tree)

# Find "Test" command
test_kb = keybinds.get('Test')

if test_kb:
    print("✓ 'Test' command found!")
    if test_kb.keyboard_shortcut:
        print(f"  Keyboard: {test_kb.keyboard_shortcut}")
    if test_kb.joystick_shortcut:
        print(f"  Joystick: {test_kb.joystick_shortcut}")
    if test_kb.mouse_shortcut:
        print(f"  Mouse: {test_kb.mouse_shortcut}")
else:
    print("✗ 'Test' command NOT found in extracted keybinds")
    print("\nAll extracted commands:")
    for cmd_name in sorted(keybinds.keys()):
        print(f"  - {cmd_name}")
