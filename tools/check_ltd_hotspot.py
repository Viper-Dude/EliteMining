#!/usr/bin/env python3
"""
Check journal for ALL hotspots in Col 285 Sector CC-K a38-2
AND check what's in user_database
"""

import os
import json
import glob
import sqlite3
from datetime import datetime

# Get Elite Dangerous journal directory
journal_dir = os.path.expanduser(r"~\Saved Games\Frontier Developments\Elite Dangerous")

target_system = "Col 285 Sector CC-K a38-2"

# Check user_database first
db_path = r"D:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_database.db"
print(f"=== USER DATABASE ENTRIES FOR {target_system} ===\n")

try:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT system_name, body_name, material_name, hotspot_count, scan_date, coord_source, res_tag, overlap_tag
            FROM hotspot_data 
            WHERE system_name LIKE ?
            ORDER BY body_name, material_name
        ''', (f"%{target_system}%",))
        rows = cursor.fetchall()
        
        if rows:
            print(f"Found {len(rows)} entries:\n")
            for row in rows:
                system, body, material, count, scan_date, coord_source, res_tag, overlap_tag = row
                print(f"  {body} | {material}: count={count} | scanned={scan_date} | source={coord_source} | res={res_tag} | overlap={overlap_tag}")
        else:
            print("No entries found in user_database!")
except Exception as e:
    print(f"Error reading database: {e}")

print(f"\n\n=== JOURNAL ENTRIES FOR {target_system} ===\n")

found_hotspots = []
current_system = ""

# Process all journals
for journal_file in journal_files:
    try:
        with open(journal_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    event = json.loads(line)
                    
                    # Track current system from FSDJump or Location events
                    if event.get('event') in ['FSDJump', 'Location', 'CarrierJump']:
                        current_system = event.get('StarSystem', '')
                    
                    # Look for SAASignalsFound (ring hotspots from DSS scan)
                    if event.get('event') == 'SAASignalsFound':
                        body_name = event.get('BodyName', '')
                        
                        # Check if this is in our target system
                        if target_system.lower() in body_name.lower():
                            signals = event.get('Signals', [])
                            for sig in signals:
                                sig_type = sig.get('Type_Localised') or sig.get('Type', '')
                                count = sig.get('Count', 0)
                                timestamp = event.get('timestamp', '')
                                
                                found_hotspots.append({
                                    'timestamp': timestamp,
                                    'body': body_name,
                                    'signal_type': sig_type,
                                    'count': count,
                                    'event_type': 'SAASignalsFound',
                                    'journal_file': os.path.basename(journal_file)
                                })
                
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        print(f"Error reading {journal_file}: {e}")

if found_hotspots:
    print(f"\nFound {len(found_hotspots)} hotspot entries for {target_system}:\n")
    
    # Group by body
    bodies = {}
    for hotspot in found_hotspots:
        body = hotspot['body']
        if body not in bodies:
            bodies[body] = []
        bodies[body].append(hotspot)
    
    for body, hotspots in sorted(bodies.items()):
        print(f"=== {body} ===")
        # Get most recent scan for this body
        latest = sorted(hotspots, key=lambda x: x['timestamp'], reverse=True)
        seen = set()
        for h in latest:
            key = (h['signal_type'], h['count'])
            if key not in seen:
                seen.add(key)
                print(f"  {h['signal_type']}: {h['count']} hotspots")
                print(f"    Scanned: {h['timestamp']}")
                print(f"    Journal: {h['journal_file']}")
        print()
else:
    print(f"\nNo hotspots found in journals for {target_system}")
    print("\nThis means the ring scan data is NOT in any journal file.")
    print("The data in user_database must have come from elsewhere.")
