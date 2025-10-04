import json
from pathlib import Path
from collections import defaultdict

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

print("=== SCANNING JOURNALS FOR PAESIA 2 A RING ===\n")

scan_events = []
saa_events = []

for journal in journals[:20]:  # Check last 20 journals
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                # Look for Scan event for body 2
                if event.get('event') == 'Scan':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and event.get('BodyID') == 2:
                        rings = event.get('Rings', [])
                        ls = event.get('DistanceFromArrivalLS')
                        scan_events.append({
                            'timestamp': event.get('timestamp'),
                            'body_name': body_name,
                            'ls': ls,
                            'rings': rings,
                            'journal': journal.name
                        })
                
                # Look for SAASignalsFound for 2 A Ring
                if event.get('event') == 'SAASignalsFound':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and '2 A Ring' in body_name:
                        saa_events.append({
                            'timestamp': event.get('timestamp'),
                            'body_name': body_name,
                            'signals': event.get('Signals', []),
                            'journal': journal.name
                        })
                        
            except (json.JSONDecodeError, Exception):
                continue

print(f"Found {len(scan_events)} Scan events for Paesia body 2")
print(f"Found {len(saa_events)} SAASignalsFound events for 2 A Ring\n")

if scan_events:
    print("=== SCAN EVENTS (Planet/Body 2) ===")
    for scan in scan_events:
        print(f"\nTimestamp: {scan['timestamp']}")
        print(f"Journal: {scan['journal']}")
        print(f"BodyName: {scan['body_name']}")
        print(f"DistanceFromArrivalLS: {scan['ls']}")
        print(f"Rings found: {len(scan['rings'])}")
        for ring in scan['rings']:
            print(f"  - {ring.get('Name')}")
            print(f"    Class: {ring.get('RingClass')}")
            print(f"    InnerRad: {ring.get('InnerRad')}")
            print(f"    OuterRad: {ring.get('OuterRad')}")
            print(f"    MassMT: {ring.get('MassMT')}")

if saa_events:
    print("\n\n=== SAASignalsFound EVENTS (2 A Ring) ===")
    material_summary = defaultdict(lambda: {'count': 0, 'timestamps': []})
    
    for saa in saa_events:
        print(f"\nTimestamp: {saa['timestamp']}")
        print(f"Journal: {saa['journal']}")
        print(f"BodyName: {saa['body_name']}")
        print(f"Signals:")
        for sig in saa['signals']:
            material = sig.get('Type', sig.get('Type_Localised', 'Unknown'))
            count = sig.get('Count', 0)
            print(f"  - {material}: {count}")
            material_summary[material]['count'] += count
            material_summary[material]['timestamps'].append(saa['timestamp'])
    
    print("\n\n=== MATERIAL SUMMARY FROM JOURNALS ===")
    for material, data in sorted(material_summary.items()):
        print(f"{material}: {data['count']} hotspots total, scanned {len(data['timestamps'])} times")

print("\n\n=== DATABASE VS JOURNAL COMPARISON ===")
import sqlite3
conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()
c.execute('''SELECT material_name, ring_type, density, ls_distance, hotspot_count, scan_date
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name = "2 A Ring"
             ORDER BY material_name''')

print("\nDatabase entries:")
for r in c.fetchall():
    print(f"  {r[0]:20} | Type:{r[1]:10} | Density:{r[2]:.6f} | LS:{r[3]:.2f} | Count:{r[4]} | Date:{r[5]}")

conn.close()

print("\n\n=== CONCLUSION ===")
if len(scan_events) > 0:
    scan = scan_events[0]  # Most recent
    print(f"✓ Journal shows ONE body (Paesia 2) with LS={scan['ls']}")
    print(f"✓ This body has {len(scan['rings'])} rings")
    
if len(saa_events) > 0:
    all_materials = list(material_summary.keys())
    print(f"✓ Journal shows these materials in 2 A Ring: {', '.join(all_materials)}")
    
print("\n✗ Database has TWO different ring type entries (Icy and Metallic)")
print("✗ Database has TWO different LS values (811.28 and 820.80)")
print("\n→ This is caused by incorrect data from separate scan sessions")
print("→ Need to determine which one is correct and delete the other")
