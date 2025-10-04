import json
from pathlib import Path
from datetime import datetime

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")

# Get journals from last few days
journals = sorted(journal_dir.glob("Journal.2025-10-*.log"), 
                 key=lambda x: x.stat().st_mtime, reverse=True)

print("=== SEARCHING FOR PAESIA 2 SCAN EVENTS ===\n")

scan_found = False
for journal in journals[:10]:  # Check last 10 journals
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                if event.get('event') == 'Scan':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and event.get('BodyID') == 2:
                        scan_found = True
                        print(f"✅ FOUND SCAN EVENT in {journal.name}")
                        print(f"   Timestamp: {event.get('timestamp')}")
                        print(f"   BodyName: {body_name}")
                        print(f"   DistanceFromArrivalLS: {event.get('DistanceFromArrivalLS')}")
                        
                        rings = event.get('Rings', [])
                        if rings:
                            print(f"   Rings: {len(rings)}")
                            for ring in rings:
                                print(f"      - {ring.get('Name')}")
                                print(f"        Class: {ring.get('RingClass')}")
                                print(f"        InnerRad: {ring.get('InnerRad')}")
                                print(f"        OuterRad: {ring.get('OuterRad')}")
                                print(f"        MassMT: {ring.get('MassMT')}")
                        print()
                        
            except (json.JSONDecodeError, Exception):
                continue

if not scan_found:
    print("❌ NO Scan event found for Paesia body 2 in recent journals")
    print("\nThis means:")
    print("  - You scanned it in a VERY old journal (not in last 10 files)")
    print("  - OR you never detailed-scanned the planet (only FSS discovered it)")
    print("  - The LS data was imported from external source (EDTools/Excel)")
