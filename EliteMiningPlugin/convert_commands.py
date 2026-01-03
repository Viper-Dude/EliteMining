"""
VoiceAttack Profile Command Converter
Converts EliteMining commands from direct file writing to plugin-based approach
"""

# Command mappings for each category
TAB_COMMANDS = {
    'TAB:MINING': ('MINING', 'TAB'),
    'TAB:HOTSPOTS': ('HOTSPOTS', 'TAB'),
    'TAB:MARKET': ('MARKET', 'TAB'),
    'TAB:SYSTEMS': ('SYSTEMS', 'TAB'),
    'TAB:DISTANCE': ('DISTANCE', 'TAB'),
    'TAB:VOICEATTACK': ('VOICEATTACK', 'TAB'),
    'TAB:BOOKMARKS': ('BOOKMARKS', 'TAB'),
    'TAB:SETTINGS': ('SETTINGS', 'TAB'),
}

SESSION_COMMANDS = {
    'SESSION:START': ('START', 'SESSION'),
    'SESSION:END': ('END', 'SESSION'),
    'SESSION:CANCEL': ('CANCEL', 'SESSION'),
    'SESSION:RESET': ('RESET', 'SESSION'),
}

SETTINGS_COMMANDS = {
    'SETTINGS:IMPORT': ('IMPORT', 'SETTINGS'),
    'SETTINGS:APPLY': ('APPLY', 'SETTINGS'),
}

APP_COMMANDS = {
    'APP:CLOSE': ('CLOSE', 'APP'),
    'APP:MINIMIZE': ('MINIMIZE', 'APP'),
    'APP:RESTORE': ('RESTORE', 'APP'),
}

def parse_announcement_command(command_str):
    """Parse ANNOUNCEMENT:LOAD:N commands"""
    parts = command_str.split(':')
    if len(parts) == 3 and parts[0] == 'ANNOUNCEMENT':
        action = parts[1]  # LOAD
        number = parts[2]  # 1, 2, 3, etc.
        return (action, number, 'ANNOUNCEMENT')
    return None

def parse_preset_command(command_str):
    """Parse PRESET:LOAD:N or PRESET:SAVE:N commands"""
    parts = command_str.split(':')
    if len(parts) == 3 and parts[0] == 'PRESET':
        action = parts[1]  # LOAD or SAVE
        number = parts[2]  # 1, 2, 3, etc.
        return (action, number, 'PRESET')
    return None

def convert_command(old_command_text):
    """
    Convert old command format to new plugin format
    Returns tuple: (param1, param2, paramInt, context) or None
    """
    # Check simple mappings first
    all_commands = {**TAB_COMMANDS, **SESSION_COMMANDS, **SETTINGS_COMMANDS, **APP_COMMANDS}
    
    if old_command_text in all_commands:
        param1, context = all_commands[old_command_text]
        return (param1, None, None, context)
    
    # Check announcement commands
    announcement = parse_announcement_command(old_command_text)
    if announcement:
        action, number, context = announcement
        return (action, None, int(number), context)
    
    # Check preset commands
    preset = parse_preset_command(old_command_text)
    if preset:
        action, number, context = preset
        return (action, None, int(number), context)
    
    return None

def generate_va_instructions(command_name, old_text, conversion):
    """Generate human-readable conversion instructions"""
    param1, param2, paramInt, context = conversion
    
    instructions = [
        f"\n{'='*60}",
        f"COMMAND: {command_name}",
        f"{'='*60}",
        f"\nOLD ACTION:",
        f"  Write (overwrite), '{old_text}' to file '{{VA_APPS}}\\EliteMining\\Variables\\eliteMiningCommand.txt'",
        f"\nNEW ACTIONS:",
    ]
    
    action_num = 1
    
    # Add Param1 if needed
    if param1:
        instructions.append(f"  {action_num}. Set text [EM.Param1] to '{param1}'")
        action_num += 1
    
    # Add Param2 if needed
    if param2:
        instructions.append(f"  {action_num}. Set text [EM.Param2] to '{param2}'")
        action_num += 1
    
    # Add ParamInt if needed
    if paramInt is not None:
        instructions.append(f"  {action_num}. Set integer [EM.ParamInt] to {paramInt}")
        action_num += 1
    
    # Add plugin execution
    instructions.extend([
        f"  {action_num}. Execute plugin 'EliteMiningPlugin v1.0.0 - Viper-Dude' with context '{context}'",
        f"      ✓ Check 'Wait for the plugin function to finish before continuing'",
        ""
    ])
    
    return "\n".join(instructions)

# Read CSV and generate conversions
import csv

def process_profile_csv(csv_path):
    """Process the VoiceAttack profile CSV and generate conversion instructions"""
    conversions = {}  # Use dict to deduplicate by action
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 7:
                continue
            
            command_name = row[0].strip()
            actions = row[6]  # Actions column
            
            # Look for Write commands to eliteMiningCommand.txt
            if 'eliteMiningCommand.txt' in actions and 'Write' in actions:
                # Extract the written text (between quotes)
                import re
                match = re.search(r"'([^']+)'", actions)
                if match:
                    old_text = match.group(1)
                    conversion = convert_command(old_text)
                    
                    if conversion:
                        # Use old_text as key to deduplicate
                        if old_text not in conversions:
                            instructions = generate_va_instructions(command_name, old_text, conversion)
                            conversions[old_text] = instructions
    
    return list(conversions.values())

if __name__ == "__main__":
    csv_path = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\EliteMining Dev 4.7.4-Profile.csv"
    output_path = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\EliteMiningPlugin\CONVERSION_INSTRUCTIONS.txt"
    
    print("Processing VoiceAttack profile...")
    conversions = process_profile_csv(csv_path)
    
    print(f"Found {len(conversions)} commands to convert")
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("ELITEMINING VOICEATTACK COMMAND CONVERSION INSTRUCTIONS\n")
        f.write("=" * 80 + "\n")
        f.write("\nThis file contains step-by-step instructions for converting each command\n")
        f.write("from direct file writing to using the EliteMiningPlugin.\n")
        f.write("\nFor each command below:\n")
        f.write("  1. Open VoiceAttack\n")
        f.write("  2. Edit Profile\n")
        f.write("  3. Find and select the command\n")
        f.write("  4. Delete the OLD ACTION\n")
        f.write("  5. Add the NEW ACTIONS as shown\n")
        f.write("  6. Save\n")
        f.write("  7. Test\n\n")
        
        for conversion in conversions:
            f.write(conversion)
    
    print(f"\nConversion instructions written to:\n{output_path}")
    print("\nOpen this file and follow the instructions for each command!")
