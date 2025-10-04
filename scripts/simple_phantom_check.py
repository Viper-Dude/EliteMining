import json
from pathlib import Path

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime)

print("SEARCHING FOR PHANTOM MATERIALS IN ALL JOURNALS")
print("="*70)

phantom_materials = ['Grandidierite', 'Tritium', 'grandidierite', 'tritium']
found_phantom = []

for journal in journals:
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                if event.get('event') == 'SAASignalsFound':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and '2 A Ring' in body_name:
                        for sig in event['signals']:
                            material = sig.get('Type', sig.get('Type_Localised', ''))
                            if any(phantom in material for phantom in phantom_materials):
                                found_phantom.append({
                                    'ring': body_name,
                                    'material': material,
                                    'count': sig.get('Count'),
                                    'timestamp': event.get('timestamp'),
                                    'journal': journal.name
                                })
            except:
                continue

print(f"\nScanned {len(journals)} journal files")
print(f"\nRESULT:")
print("="*70)

if found_phantom:
    print(f"FOUND {len(found_phantom)} PHANTOM MATERIAL ENTRIES IN JOURNALS:")
    for item in found_phantom:
        print(f"\n  Ring: {item['ring']}")
        print(f"  Material: {item['material']}")
        print(f"  Count: {item['count']}")
        print(f"  Date: {item['timestamp']}")
        print(f"  Journal: {item['journal']}")
    print("\n>>> The phantom data CAME FROM JOURNAL FILES!")
else:
    print("NO PHANTOM MATERIALS (Grandidierite, Tritium) found in journals!")
    print("\n>>> Journal files are CLEAN")
    print(">>> The phantom data came from:")
    print("    1. External import (Excel/EDSM)")
    print("    2. Database migration from old version")
    print("    3. Manual data entry")
