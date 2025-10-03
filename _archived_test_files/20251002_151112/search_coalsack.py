"""Search journals for Coalsack Dark Region EW-M ring data"""
import json
import glob
import os
from datetime import datetime

journal_dir = os.path.join(os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")

if not os.path.exists(journal_dir):
    print(f"❌ Journal directory not found: {journal_dir}")
    exit(1)

# Get all journal files
journal_files = sorted(glob.glob(os.path.join(journal_dir, "Journal.*.log")))

print(f"\n{'='*70}")
print(f"SEARCHING FOR: Coalsack Dark Region EW-M")
print(f"{'='*70}\n")
print(f"Scanning {len(journal_files)} journal files...\n")

# Track all events for this system
fsd_jumps = []
scans = []
saa_signals = []

target_system = "Coalsack Dark Region EW-M"

for journal_file in journal_files:
    try:
        with open(journal_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    event_type = event.get('event')
                    
                    # Check for FSDJump
                    if event_type == 'FSDJump':
                        system = event.get('StarSystem', '')
                        if target_system in system:
                            fsd_jumps.append({
                                'file': os.path.basename(journal_file),
                                'timestamp': event.get('timestamp'),
                                'system': system
                            })
                    
                    # Check for Scan events
                    elif event_type == 'Scan':
                        body_name = event.get('BodyName', '')
                        if target_system in body_name:
                            rings = event.get('Rings', [])
                            if rings:
                                scans.append({
                                    'file': os.path.basename(journal_file),
                                    'timestamp': event.get('timestamp'),
                                    'body': body_name,
                                    'rings': rings
                                })
                    
                    # Check for SAASignalsFound
                    elif event_type == 'SAASignalsFound':
                        body_name = event.get('BodyName', '')
                        if target_system in body_name:
                            saa_signals.append({
                                'file': os.path.basename(journal_file),
                                'timestamp': event.get('timestamp'),
                                'body': body_name,
                                'signals': event.get('Signals', [])
                            })
                            
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {journal_file}: {e}")

# Display results
print(f"{'='*70}")
print(f"RESULTS:")
print(f"{'='*70}\n")

if fsd_jumps:
    print(f"✅ Found {len(fsd_jumps)} FSDJump(s):")
    for jump in fsd_jumps:
        print(f"  • {jump['timestamp']} - {jump['system']}")
        print(f"    File: {jump['file']}")
    print()

if scans:
    print(f"✅ Found {len(scans)} Scan event(s) with rings:")
    for scan in scans:
        print(f"\n  • {scan['timestamp']} - {scan['body']}")
        print(f"    File: {scan['file']}")
        print(f"    Rings found: {len(scan['rings'])}")
        for ring in scan['rings']:
            ring_name = ring.get('Name', 'Unknown')
            ring_class = ring.get('RingClass', 'Unknown')
            mass = ring.get('MassMT')
            inner = ring.get('InnerRad')
            outer = ring.get('OuterRad')
            print(f"\n      Ring: {ring_name}")
            print(f"        Class: {ring_class}")
            print(f"        Mass: {mass if mass else 'N/A'} MT")
            print(f"        Inner Radius: {inner if inner else 'N/A'} m")
            print(f"        Outer Radius: {outer if outer else 'N/A'} m")
            
            # Calculate density if we have data
            if mass and inner and outer:
                import math
                r_inner = inner / 1000
                r_outer = outer / 1000
                area = math.pi * (r_outer**2 - r_inner**2)
                density = round(mass / area, 6)
                print(f"        ✅ Calculated Density: {density}")
    print()

if saa_signals:
    print(f"✅ Found {len(saa_signals)} SAASignalsFound event(s):")
    for signal in saa_signals:
        print(f"\n  • {signal['timestamp']} - {signal['body']}")
        print(f"    File: {signal['file']}")
        print(f"    Hotspots found:")
        for sig in signal['signals']:
            material = sig.get('Type_Localised', sig.get('Type', 'Unknown'))
            count = sig.get('Count', 0)
            print(f"      - {material}: {count}")
    print()

if not fsd_jumps and not scans and not saa_signals:
    print(f"❌ No events found for '{target_system}'")
    print(f"\nTip: Make sure the system name is spelled correctly!")

print(f"{'='*70}\n")
