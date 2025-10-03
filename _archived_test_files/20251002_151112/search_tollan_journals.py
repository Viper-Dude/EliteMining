"""Search journal files for Tollan scan data"""
import json
import os
import glob
from datetime import datetime

# Elite Dangerous journal folder
journal_dir = os.path.join(os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")

print(f"\n{'='*80}")
print(f"SEARCHING JOURNAL FILES FOR TOLLAN SCANS")
print(f"{'='*80}\n")
print(f"Journal folder: {journal_dir}\n")

if not os.path.exists(journal_dir):
    print("❌ Journal folder not found!")
    exit(1)

# Find all journal files from May 2024
journal_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")))

print(f"Found {len(journal_files)} journal files total\n")

# Search for Tollan-related events
tollan_events = []

for journal_file in journal_files:
    try:
        with open(journal_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    event = json.loads(line.strip())
                    
                    # Look for FSSAllBodiesFound or SAAScanComplete events in Tollan
                    if event.get('StarSystem') == 'Tollan':
                        event_type = event.get('event')
                        if event_type in ['FSSAllBodiesFound', 'SAAScanComplete', 'FSSDiscoveryScan', 'Scan']:
                            tollan_events.append({
                                'file': os.path.basename(journal_file),
                                'line': line_num,
                                'timestamp': event.get('timestamp'),
                                'event': event_type,
                                'full_event': event
                            })
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {journal_file}: {e}")

print(f"{'='*80}")
print(f"FOUND {len(tollan_events)} TOLLAN-RELATED EVENTS")
print(f"{'='*80}\n")

for i, evt in enumerate(tollan_events, 1):
    print(f"\n--- Event #{i} ---")
    print(f"File: {evt['file']}")
    print(f"Timestamp: {evt['timestamp']}")
    print(f"Event Type: {evt['event']}")
    print(f"\nFull Event Data:")
    print(json.dumps(evt['full_event'], indent=2))
    
    # Check for ring data
    body_name = evt['full_event'].get('BodyName', 'N/A')
    rings = evt['full_event'].get('Rings', [])
    
    if rings:
        print(f"\n🔍 RING DATA FOUND:")
        for ring in rings:
            print(f"  - Name: {ring.get('Name')}")
            print(f"    Type: {ring.get('RingClass')}")
            print(f"    Inner Radius: {ring.get('InnerRad')}")
            print(f"    Outer Radius: {ring.get('OuterRad')}")

if not tollan_events:
    print("\n❌ No Tollan events found in journal files")
    print("\nThis could mean:")
    print("  1. Journal files from May 2024 have been deleted")
    print("  2. Tollan was scanned before journal tracking began")
    print("  3. Data was imported from a different source")
