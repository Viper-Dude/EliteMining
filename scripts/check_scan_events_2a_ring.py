import json
import os
import gzip
from pathlib import Path

print("=== SEARCHING FOR 'Paesia 2 a A Ring' SCAN EVENTS ===\n")

# Get journal directory from environment or use default Elite path
journal_dir = os.path.expandvars(r'%USERPROFILE%\Saved Games\Frontier Developments\Elite Dangerous')

if not os.path.exists(journal_dir):
    print(f"❌ Journal directory not found: {journal_dir}")
    exit(1)

print(f"Scanning journals in: {journal_dir}\n")

scan_events_found = []
saa_events_found = []

# Scan all journal files
for file in sorted(os.listdir(journal_dir)):
    if file.startswith('Journal.') and file.endswith('.log'):
        filepath = os.path.join(journal_dir, file)
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        event_type = entry.get('event', '')
                        
                        # Check for Scan events with Rings
                        if event_type == 'Scan':
                            rings = entry.get('Rings', [])
                            for ring in rings:
                                ring_name = ring.get('Name', '')
                                if 'Paesia' in ring_name and '2 a A Ring' in ring_name:
                                    scan_events_found.append({
                                        'file': file,
                                        'ring_name': ring_name,
                                        'ring_class': ring.get('RingClass', 'Unknown'),
                                        'ls_distance': entry.get('DistanceFromArrivalLS'),
                                        'inner_radius': ring.get('InnerRad'),
                                        'outer_radius': ring.get('OuterRad'),
                                        'mass': ring.get('MassMT')
                                    })
                        
                        # Check for SAASignalsFound events
                        if event_type == 'SAASignalsFound':
                            body_name = entry.get('BodyName', '')
                            if 'Paesia' in body_name and '2 a A Ring' in body_name:
                                saa_events_found.append({
                                    'file': file,
                                    'body_name': body_name,
                                    'system_address': entry.get('SystemAddress'),
                                    'body_id': entry.get('BodyID'),
                                    'signals': entry.get('Signals', [])
                                })
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Error reading {file}: {e}")

print("=" * 70)
print(f"\n📊 RESULTS:\n")
print(f"Scan events found for 'Paesia 2 a A Ring': {len(scan_events_found)}")
print(f"SAASignalsFound events found: {len(saa_events_found)}")

if scan_events_found:
    print("\n✅ SCAN EVENTS FOUND:")
    print("-" * 70)
    for i, scan in enumerate(scan_events_found[:3], 1):  # Show first 3
        print(f"\n{i}. File: {scan['file']}")
        print(f"   Ring: {scan['ring_name']}")
        print(f"   Ring Class: {scan['ring_class']}")
        print(f"   LS Distance: {scan['ls_distance']}")
        print(f"   Inner Radius: {scan['inner_radius']}")
        print(f"   Outer Radius: {scan['outer_radius']}")
        print(f"   Mass: {scan['mass']}")
else:
    print("\n❌ NO SCAN EVENTS FOUND for 'Paesia 2 a A Ring'")
    print("\nThis means:")
    print("  • The ring metadata (type, LS, density) will NOT auto-populate")
    print("  • You never scanned the parent body with Detailed Surface Scanner")
    print("  • You only fired prospector limpets (SAASignalsFound events)")

if saa_events_found:
    print(f"\n✅ Found {len(saa_events_found)} SAASignalsFound events")
    print("   (These contain hotspot data but NO ring metadata)")

print("\n" + "=" * 70)
print("\nCONCLUSION:")
if not scan_events_found:
    print("  ❌ Ring metadata will NOT populate from journals")
    print("  ✅ We need to manually add ring_type, ls_distance, density to database")
else:
    print("  ✅ Ring metadata exists and should populate on reimport")
