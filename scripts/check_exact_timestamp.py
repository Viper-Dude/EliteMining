import json
from pathlib import Path

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")

# Find the journal from Oct 4, 2025 around 09:11:59
target_journal = journal_dir / "Journal.2025-10-04T110902.01.log"

print(f"Checking journal: {target_journal.name}\n")
print("="*80)

found_events = []

with open(target_journal, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            event = json.loads(line)
            timestamp = event.get('timestamp', '')
            
            # Look around that time (09:11 to 09:12)
            if '2025-10-04T09:11' in timestamp or '2025-10-04T09:12' in timestamp:
                body_name = event.get('BodyName', '')
                if 'Paesia' in body_name and '2' in body_name:
                    found_events.append(event)
                    print(f"\n{event.get('event')} at {timestamp}")
                    print(f"Body: {body_name}")
                    if event.get('event') == 'SAASignalsFound':
                        print("Signals:")
                        for sig in event.get('Signals', []):
                            mat = sig.get('Type', sig.get('Type_Localised'))
                            print(f"  - {mat}: {sig.get('Count')}")
                    print("-"*80)
        except:
            continue

print(f"\nTotal events found: {len(found_events)}")
