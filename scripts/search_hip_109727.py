import json
from pathlib import Path

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime)

print("=== SEARCHING FOR HIP 109727 IN JOURNALS ===\n")

# Track all events
fsd_jumps = []
scans = []
saa_scans = []

for journal in journals:
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                # FSD Jump to system
                if event.get('event') == 'FSDJump' and 'HIP 109727' in event.get('StarSystem', ''):
                    fsd_jumps.append({
                        'timestamp': event.get('timestamp'),
                        'journal': journal.name
                    })
                
                # Scan events
                if event.get('event') == 'Scan':
                    body_name = event.get('BodyName', '')
                    if 'HIP 109727' in body_name:
                        scans.append({
                            'timestamp': event.get('timestamp'),
                            'body_name': body_name,
                            'body_id': event.get('BodyID'),
                            'rings': event.get('Rings', []),
                            'journal': journal.name
                        })
                
                # SAASignalsFound events
                if event.get('event') == 'SAASignalsFound':
                    body_name = event.get('BodyName', '')
                    if 'HIP 109727' in body_name:
                        saa_scans.append({
                            'timestamp': event.get('timestamp'),
                            'body_name': body_name,
                            'signals': event.get('Signals', []),
                            'journal': journal.name
                        })
                        
            except:
                continue

print(f"FSD Jumps to HIP 109727: {len(fsd_jumps)}")
print(f"Scan events: {len(scans)}")
print(f"SAASignalsFound events: {len(saa_scans)}\n")

if fsd_jumps:
    print("="*80)
    print("FSD JUMPS:")
    print("="*80)
    for jump in fsd_jumps[:5]:  # First 5
        print(f"  {jump['timestamp']} ({jump['journal']})")
    if len(fsd_jumps) > 5:
        print(f"  ... and {len(fsd_jumps) - 5} more")

if scans:
    print("\n" + "="*80)
    print("SCAN EVENTS:")
    print("="*80)
    for scan in scans[:10]:  # First 10
        print(f"\n  {scan['timestamp']} ({scan['journal']})")
        print(f"  Body: {scan['body_name']}")
        if scan['rings']:
            print(f"  Rings: {len(scan['rings'])}")
            for ring in scan['rings']:
                print(f"    - {ring.get('Name')}: {ring.get('RingClass')}")

if saa_scans:
    print("\n" + "="*80)
    print("SAA SIGNALS FOUND:")
    print("="*80)
    for saa in saa_scans[:10]:  # First 10
        print(f"\n  {saa['timestamp']} ({saa['journal']})")
        print(f"  Body: {saa['body_name']}")
        print(f"  Materials:")
        for sig in saa['signals']:
            mat = sig.get('Type', sig.get('Type_Localised', ''))
            print(f"    - {mat}: {sig.get('Count')}")

if not fsd_jumps and not scans and not saa_scans:
    print("NO DATA FOUND for HIP 109727 in any journal!")
    print("\nPossible reasons:")
    print("  - System never visited")
    print("  - System visited but no scans performed")
    print("  - Journal files from that time were deleted/archived")

# Check database
print("\n" + "="*80)
print("DATABASE CHECK:")
print("="*80)
import sqlite3
conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()
c.execute('SELECT body_name, material_name, ring_type, hotspot_count FROM hotspot_data WHERE system_name LIKE "%HIP 109727%"')
db_results = c.fetchall()
if db_results:
    print(f"\nFound {len(db_results)} entries in database:")
    for r in db_results:
        print(f"  {r[0]} - {r[1]} ({r[2]}) x{r[3]}")
else:
    print("\nNO entries found in database for HIP 109727")
conn.close()
