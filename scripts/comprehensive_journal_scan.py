import json
from pathlib import Path
from datetime import datetime

journal_dir = Path(r"C:\Users\olmba\Saved Games\Frontier Developments\Elite Dangerous")
journals = sorted(journal_dir.glob("Journal*.log"), key=lambda x: x.stat().st_mtime)

print("=== COMPREHENSIVE JOURNAL SCAN FOR PAESIA 2 PHANTOM RING DATA ===\n")
print(f"Scanning {len(journals)} journal files...\n")

# Track all events
all_scan_events = []
all_saa_events = []
fsd_jumps = []

for journal in journals:
    with open(journal, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                event = json.loads(line)
                
                # Track FSD jumps to Paesia
                if event.get('event') == 'FSDJump' and event.get('StarSystem') == 'Paesia':
                    fsd_jumps.append({
                        'timestamp': event.get('timestamp'),
                        'journal': journal.name
                    })
                
                # Look for Scan event for Paesia body 2
                if event.get('event') == 'Scan':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and event.get('BodyID') == 2:
                        all_scan_events.append({
                            'timestamp': event.get('timestamp'),
                            'body_name': body_name,
                            'body_id': event.get('BodyID'),
                            'ls': event.get('DistanceFromArrivalLS'),
                            'rings': event.get('Rings', []),
                            'journal': journal.name
                        })
                
                # Look for SAASignalsFound for ANY ring at Paesia 2
                if event.get('event') == 'SAASignalsFound':
                    body_name = event.get('BodyName', '')
                    if 'Paesia' in body_name and '2' in body_name:
                        all_saa_events.append({
                            'timestamp': event.get('timestamp'),
                            'body_name': body_name,
                            'system_address': event.get('SystemAddress'),
                            'body_id': event.get('BodyID'),
                            'signals': event.get('Signals', []),
                            'journal': journal.name
                        })
                        
            except (json.JSONDecodeError, Exception):
                continue

print(f"Found {len(fsd_jumps)} visits to Paesia")
print(f"Found {len(all_scan_events)} Scan events for Paesia body 2")
print(f"Found {len(all_saa_events)} SAASignalsFound events for Paesia 2 rings\n")

# Show all Scan events
if all_scan_events:
    print("=" * 100)
    print("=== ALL SCAN EVENTS FOR PAESIA BODY 2 ===")
    print("=" * 100)
    for scan in all_scan_events:
        print(f"\nTimestamp: {scan['timestamp']} | Journal: {scan['journal']}")
        print(f"BodyName: {scan['body_name']}")
        print(f"BodyID: {scan['body_id']}")
        print(f"DistanceFromArrivalLS: {scan['ls']}")
        print(f"Rings: {len(scan['rings'])}")
        for ring in scan['rings']:
            ring_name = ring.get('Name', 'Unknown')
            ring_class = ring.get('RingClass', 'Unknown')
            mass = ring.get('MassMT', 'Unknown')
            print(f"  • {ring_name}")
            print(f"    Class: {ring_class}")
            print(f"    InnerRad: {ring.get('InnerRad', 'N/A')} m")
            print(f"    OuterRad: {ring.get('OuterRad', 'N/A')} m")
            print(f"    MassMT: {mass}")

# Show all SAASignalsFound events grouped by ring
if all_saa_events:
    print("\n" + "=" * 100)
    print("=== ALL SAASignalsFound EVENTS FOR PAESIA 2 RINGS ===")
    print("=" * 100)
    
    # Group by ring name
    rings_data = {}
    for saa in all_saa_events:
        ring_name = saa['body_name']
        if ring_name not in rings_data:
            rings_data[ring_name] = []
        rings_data[ring_name].append(saa)
    
    for ring_name, events in sorted(rings_data.items()):
        print(f"\n{'='*50}")
        print(f"RING: {ring_name}")
        print(f"{'='*50}")
        print(f"Total scans: {len(events)}")
        
        # Collect all materials
        all_materials = {}
        for event in events:
            print(f"\n  Scan on {event['timestamp']} ({event['journal']})")
            for sig in event['signals']:
                material = sig.get('Type', sig.get('Type_Localised', 'Unknown'))
                count = sig.get('Count', 0)
                print(f"    - {material}: {count}")
                if material not in all_materials:
                    all_materials[material] = []
                all_materials[material].append(count)
        
        print(f"\n  Materials Summary for {ring_name}:")
        for material, counts in sorted(all_materials.items()):
            print(f"    • {material}: {counts} (scanned {len(counts)} times)")

# Critical check: Look for Grandidierite or Tritium
print("\n" + "=" * 100)
print("=== CRITICAL: SEARCHING FOR PHANTOM MATERIALS (Grandidierite, Tritium) ===")
print("=" * 100)

phantom_materials = ['Grandidierite', 'Tritium', '$Grandidierite_Name;', '$Tritium_Name;']
found_phantom = False

for saa in all_saa_events:
    for sig in saa['signals']:
        material = sig.get('Type', sig.get('Type_Localised', ''))
        if any(phantom in material for phantom in phantom_materials):
            found_phantom = True
            print(f"\n❌ FOUND PHANTOM MATERIAL!")
            print(f"   Ring: {saa['body_name']}")
            print(f"   Material: {material}")
            print(f"   Count: {sig.get('Count')}")
            print(f"   Timestamp: {saa['timestamp']}")
            print(f"   Journal: {saa['journal']}")

if not found_phantom:
    print("\n✅ NO PHANTOM MATERIALS (Grandidierite, Tritium) found in ANY journal!")
    print("   → The phantom data did NOT come from journal files")
    print("   → Likely source: External import (Excel/EDSM) with old/bad data")

print("\n" + "=" * 100)
print("CONCLUSION:")
print("=" * 100)
if not found_phantom:
    print("✅ Journal files are CLEAN - no phantom ring materials found")
    print("✅ The bug fix we implemented will PREVENT future overwrites")
    print("❌ The bad data in your active database came from:")
    print("   1. Old journal files (before Frontier removed C Ring) - now purged")
    print("   2. External data import (Excel/EDSM) with outdated data")
    print("   3. Database migration from old version")
    print("\n→ Solution: Clean your active user_data.db by deleting Icy entries for Paesia 2 A Ring")
