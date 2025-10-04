import json
from pathlib import Path
from collections import defaultdict

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime)

print("=== SEARCHING FOR ALL PAESIA 2 RING VARIATIONS ===\n")

# Track all unique body names
unique_bodies = defaultdict(list)

for journal in journals:
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                if event.get('event') == 'SAASignalsFound':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and '2' in body_name and 'Ring' in body_name:
                        unique_bodies[body_name].append({
                            'timestamp': event.get('timestamp'),
                            'signals': event.get('Signals', []),
                            'journal': journal.name
                        })
            except:
                continue

print(f"Found {len(unique_bodies)} unique body name variations:\n")
print("="*80)

for body_name in sorted(unique_bodies.keys()):
    events = unique_bodies[body_name]
    print(f"\nBODY NAME: '{body_name}'")
    print(f"Total scans: {len(events)}")
    
    # Get all materials
    all_materials = set()
    for event in events:
        for sig in event.get('signals', []):
            mat = sig.get('Type', sig.get('Type_Localised', ''))
            all_materials.add(mat)
    
    print(f"Materials: {', '.join(sorted(all_materials))}")
    print(f"First scan: {events[0]['timestamp']} ({events[0]['journal']})")
    print(f"Last scan: {events[-1]['timestamp']} ({events[-1]['journal']})")

print("\n" + "="*80)
print("EXACT NAME MATCHING:")
print("="*80)

# Check specific variations
variations = [
    'Paesia 2 A Ring',
    'Paesia 2 a A Ring',
    'Paesia 2 A A Ring',
    'Paesia 2 C Ring'
]

for variation in variations:
    if variation in unique_bodies:
        count = len(unique_bodies[variation])
        mats = set()
        for e in unique_bodies[variation]:
            for sig in e.get('signals', []):
                mats.add(sig.get('Type', sig.get('Type_Localised', '')))
        print(f"\n✓ FOUND: '{variation}'")
        print(f"  Scans: {count}")
        print(f"  Materials: {', '.join(sorted(mats))}")
    else:
        print(f"\n✗ NOT FOUND: '{variation}'")
