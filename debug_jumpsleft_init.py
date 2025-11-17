"""
Debug jumpsleft initialization
"""
import os
import json

journal_dir = r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous"

# Find most recent journal
journal_files = [f for f in os.listdir(journal_dir) if f.startswith('Journal.') and f.endswith('.log')]
journal_files.sort(reverse=True)
latest_journal = os.path.join(journal_dir, journal_files[0])

print(f"Latest journal: {journal_files[0]}")
print(f"Full path: {latest_journal}")

# Scan for FSDTarget
jumps_remaining = None
with open(latest_journal, 'r', encoding='utf-8') as f:
    # Read last 50KB
    f.seek(0, 2)
    file_size = f.tell()
    f.seek(max(0, file_size - 51200))
    lines = f.readlines()
    
    print(f"\nScanning last {len(lines)} lines...")
    
    # Scan backwards
    fsd_target_found = False
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            event_type = event.get('event')
            
            if event_type == 'FSDTarget':
                jumps_remaining = event.get('RemainingJumpsInRoute', 0)
                print(f"\n✓ Found FSDTarget event:")
                print(f"  Timestamp: {event.get('timestamp')}")
                print(f"  Target: {event.get('Name')}")
                print(f"  RemainingJumpsInRoute: {jumps_remaining}")
                fsd_target_found = True
                break
            elif event_type in ['NavRouteClear', 'Docked', 'Touchdown']:
                print(f"\n✓ Found {event_type} event - route cleared/completed")
                jumps_remaining = 0
                break
        except json.JSONDecodeError:
            continue

if not fsd_target_found and jumps_remaining is None:
    print("\n✗ No FSDTarget or route clear events found")
    jumps_remaining = 0

print(f"\nResult: jumpsleft should be {jumps_remaining}")

# Write it
vars_dir = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\Variables"
jumpsleft_path = os.path.join(vars_dir, "jumpsleft.txt")
with open(jumpsleft_path, 'w') as f:
    f.write(str(jumps_remaining))

print(f"✓ Written to {jumpsleft_path}")
