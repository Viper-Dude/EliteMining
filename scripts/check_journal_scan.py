import json
import os
from pathlib import Path

# Get journal directory
journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")

# Find most recent journal
journal_files = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime, reverse=True)

if not journal_files:
    print("No journal files found!")
    exit()

print(f"Checking most recent journal: {journal_files[0].name}\n")

# Look for Scan events for Paesia 2
found_scan = False
found_saa = False

with open(journal_files[0], 'r', encoding='utf-8') as f:
    for line in f:
        try:
            event = json.loads(line)
            
            # Check for FSDJump to Paesia
            if event.get('event') == 'FSDJump' and event.get('StarSystem') == 'Paesia':
                print(f"✓ Found FSDJump to Paesia at {event.get('timestamp')}")
            
            # Check for Scan event with body 2 and rings
            if event.get('event') == 'Scan':
                body_name = event.get('BodyName', '')
                if 'Paesia' in body_name and event.get('BodyID') == 2:
                    found_scan = True
                    print(f"\n✓ Found Scan event for body ID 2:")
                    print(f"  BodyName: {body_name}")
                    print(f"  DistanceFromArrivalLS: {event.get('DistanceFromArrivalLS')}")
                    
                    rings = event.get('Rings', [])
                    if rings:
                        print(f"  Rings found: {len(rings)}")
                        for ring in rings:
                            print(f"    - {ring.get('Name')} (Class: {ring.get('RingClass')})")
                    else:
                        print("  No rings in this Scan event")
            
            # Check for SAASignalsFound
            if event.get('event') == 'SAASignalsFound':
                body_name = event.get('BodyName', '')
                if 'Paesia' in body_name and '2 A Ring' in body_name:
                    found_saa = True
                    print(f"\n✓ Found SAASignalsFound for 2 A Ring:")
                    print(f"  BodyName: {body_name}")
                    print(f"  SystemAddress: {event.get('SystemAddress')}")
                    print(f"  Signals: {event.get('Signals', [])}")
                    
        except json.JSONDecodeError:
            continue

if not found_scan:
    print("\n❌ NO Scan event found for Paesia body 2!")
    print("This is why LS distance is missing - the Scan event needs to be in the journal")
    
if not found_saa:
    print("\n❌ NO SAASignalsFound event found for Paesia 2 A Ring!")
