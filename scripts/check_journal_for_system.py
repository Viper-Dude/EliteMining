import os
import json
import glob
from datetime import datetime

# Find Elite Dangerous journal folder
journal_paths = [
    os.path.expanduser(r'~\Saved Games\Frontier Developments\Elite Dangerous'),
    r'C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous'
]

journal_dir = None
for path in journal_paths:
    if os.path.exists(path):
        journal_dir = path
        break

if not journal_dir:
    print("❌ Journal directory not found!")
    exit(1)

print(f"✅ Journal directory: {journal_dir}\n")

# Get all journal files
journal_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")), 
                      key=os.path.getmtime, reverse=True)

print(f"Found {len(journal_files)} journal files\n")
print("="*80)

# Search for the system
system_name = "Praea Euq JF-Q b5-4"
found_entries = []

print(f"Searching for system: {system_name}\n")

for journal_file in journal_files[:50]:  # Check last 50 files
    try:
        with open(journal_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    
                    # Check if this entry mentions our system
                    if entry.get('StarSystem') == system_name or entry.get('System') == system_name:
                        found_entries.append({
                            'file': os.path.basename(journal_file),
                            'timestamp': entry.get('timestamp', 'Unknown'),
                            'event': entry.get('event', 'Unknown'),
                            'entry': entry
                        })
                        
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        print(f"Error reading {os.path.basename(journal_file)}: {e}")

if found_entries:
    print(f"✅ FOUND {len(found_entries)} entries for '{system_name}':\n")
    
    for i, entry in enumerate(found_entries, 1):
        print(f"Entry {i}:")
        print(f"  File: {entry['file']}")
        print(f"  Timestamp: {entry['timestamp']}")
        print(f"  Event: {entry['event']}")
        
        data = entry['entry']
        
        # Check for coordinates
        if 'StarPos' in data:
            coords = data['StarPos']
            print(f"  ✅ Coordinates: X={coords[0]}, Y={coords[1]}, Z={coords[2]}")
        else:
            print(f"  ❌ No coordinates in this entry")
            
        # Check for bodies/rings
        if 'BodyName' in data:
            print(f"  Body: {data['BodyName']}")
        if 'Rings' in data:
            print(f"  Rings: {len(data['Rings'])} found")
            
        print()
else:
    print(f"❌ NO entries found for system '{system_name}' in journal files")
    print("\nNote: System may not have been visited, or journals were cleared/archived")
