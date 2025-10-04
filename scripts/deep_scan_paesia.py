import json
from pathlib import Path
from collections import defaultdict

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime)

print("=== DEEP SCAN: ALL PAESIA RING EVENTS ===\n")
print(f"Scanning {len(journals)} journal files...\n")

# Track everything
all_rings_found = defaultdict(list)

for journal in journals:
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                # ANY event with Paesia and Ring in body name
                if event.get('event') in ['Scan', 'SAASignalsFound', 'FSSBodySignals']:
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and 'Ring' in body_name:
                        
                        event_data = {
                            'event_type': event.get('event'),
                            'body_name': body_name,
                            'body_id': event.get('BodyID'),
                            'timestamp': event.get('timestamp'),
                            'journal': journal.name
                        }
                        
                        # Get specific data based on event type
                        if event.get('event') == 'Scan':
                            event_data['rings'] = event.get('Rings', [])
                            event_data['ls_distance'] = event.get('DistanceFromArrivalLS')
                        
                        elif event.get('event') == 'SAASignalsFound':
                            event_data['signals'] = event.get('Signals', [])
                        
                        all_rings_found[body_name].append(event_data)
                        
            except:
                continue

print(f"Found {sum(len(v) for v in all_rings_found.values())} total ring events")
print(f"Unique rings: {len(all_rings_found)}\n")

# Show each ring
for ring_name in sorted(all_rings_found.keys()):
    events = all_rings_found[ring_name]
    print("="*80)
    print(f"RING: {ring_name}")
    print("="*80)
    print(f"Total events: {len(events)}")
    
    # Group by event type
    by_type = defaultdict(list)
    for e in events:
        by_type[e['event_type']].append(e)
    
    for event_type, type_events in sorted(by_type.items()):
        print(f"\n{event_type}: {len(type_events)} events")
        
        if event_type == 'Scan':
            # Show first Scan event details
            first = type_events[0]
            print(f"  First scan: {first['timestamp']} ({first['journal']})")
            print(f"  LS Distance: {first.get('ls_distance')}")
            if first.get('rings'):
                print(f"  Rings in Scan event: {len(first['rings'])}")
                for r in first['rings']:
                    print(f"    - {r.get('Name')}: {r.get('RingClass')}")
        
        elif event_type == 'SAASignalsFound':
            # Collect all unique materials
            all_materials = set()
            for e in type_events:
                for sig in e.get('signals', []):
                    mat = sig.get('Type', sig.get('Type_Localised', ''))
                    all_materials.add(mat)
            print(f"  Materials found: {', '.join(sorted(all_materials))}")

print("\n" + "="*80)
print("CRITICAL CHECK: Looking for Icy materials in 2 A Ring")
print("="*80)

# Check specifically for 2 A Ring icy materials
a_ring_events = all_rings_found.get('Paesia 2 A Ring', [])
icy_materials = []

for event in a_ring_events:
    if event['event_type'] == 'SAASignalsFound':
        for sig in event.get('signals', []):
            mat = sig.get('Type', sig.get('Type_Localised', ''))
            # Check if it's an icy material
            if mat in ['Grandidierite', 'Tritium', 'Low Temperature Diamonds', 'Alexandrite', 
                      '$Grandidierite_Name;', '$Tritium_Name;', '$LowTemperatureDiamond_Name;']:
                icy_materials.append({
                    'material': mat,
                    'count': sig.get('Count'),
                    'timestamp': event['timestamp'],
                    'journal': event['journal']
                })

if icy_materials:
    print(f"\nFOUND {len(icy_materials)} ICY MATERIAL ENTRIES IN 2 A RING:")
    for item in icy_materials:
        print(f"\n  Material: {item['material']}")
        print(f"  Count: {item['count']}")
        print(f"  Timestamp: {item['timestamp']}")
        print(f"  Journal: {item['journal']}")
    print("\n>>> ICY MATERIALS FOUND IN JOURNALS FOR 2 A RING!")
else:
    print("\nNO icy materials found in 2 A Ring journal events.")
    print(">>> The icy data is NOT coming from journals!")
