import os
import json
from pathlib import Path

# Find journal folder
journal_path = Path(os.path.expanduser("~")) / "Saved Games" / "Frontier Developments" / "Elite Dangerous"

if not journal_path.exists():
    print(f"Journal path not found: {journal_path}")
    exit()

# Search for Namnetes in recent journals
journals = sorted(journal_path.glob("Journal.*.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:5]

print(f"Checking {len(journals)} most recent journals for Namnetes...")

for journal in journals:
    print(f"\n--- {journal.name} ---")
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            if 'Namnetes' in line:
                try:
                    event = json.loads(line.strip())
                    event_type = event.get('event', '')
                    timestamp = event.get('timestamp', '')
                    print(f"  {event_type} at {timestamp}")
                except:
                    pass
