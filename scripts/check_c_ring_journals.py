import json
from pathlib import Path

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime)

print("SEARCHING FOR 2 C RING IN JOURNALS")
print("="*70)

found_c_ring = []

for journal in journals:
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                if event.get('event') == 'SAASignalsFound':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and '2 C Ring' in body_name:
                        found_c_ring.append({
                            'body_name': body_name,
                            'signals': event.get('Signals', []),
                            'timestamp': event.get('timestamp'),
                            'journal': journal.name
                        })
            except:
                continue

print(f"Scanned {len(journals)} journal files\n")
print("RESULT:")
print("="*70)

if found_c_ring:
    print(f"\nFOUND {len(found_c_ring)} entries for 2 C Ring in journals:")
    for item in found_c_ring:
        print(f"\n  Body: {item['body_name']}")
        print(f"  Date: {item['timestamp']}")
        print(f"  Journal: {item['journal']}")
        print(f"  Materials:")
        for sig in item['signals']:
            print(f"    - {sig.get('Type', sig.get('Type_Localised'))}: {sig.get('Count')}")
    
    print("\n\n>>> YES! 2 C Ring WAS found in journal files!")
    print(">>> This means the phantom ring CAN be scanned in-game")
    print(">>> It exists in the journal but physically disappeared")
else:
    print("\nNO 2 C Ring entries found in journals!")
    print("\n>>> The C Ring in database came from external source")
