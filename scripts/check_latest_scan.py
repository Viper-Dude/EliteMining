import json
from pathlib import Path

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")

# Get the most recent journal from today
target_journal = journal_dir / "Journal.2025-10-04T151936.01.log"

print(f"Checking: {target_journal.name}\n")
print("="*80)

# Find the latest scan of Paesia 2 a A Ring
found = []

with open(target_journal, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            event = json.loads(line)
            
            if event.get('event') == 'SAASignalsFound':
                body_name = event.get('BodyName', '')
                if body_name == 'Paesia 2 a A Ring':
                    found.append(event)
        except:
            continue

if found:
    print(f"Found {len(found)} scans of 'Paesia 2 a A Ring' in this journal:\n")
    
    for i, event in enumerate(found, 1):
        print(f"Scan #{i} at {event.get('timestamp')}:")
        print("Signals:")
        for sig in event.get('Signals', []):
            mat_type = sig.get('Type', '')
            mat_local = sig.get('Type_Localised', '')
            count = sig.get('Count', 0)
            print(f"  - Type: '{mat_type}' | Localised: '{mat_local}' | Count: {count}")
        print("-"*80)
else:
    print("No scans found in this journal")
