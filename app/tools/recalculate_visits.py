"""
Recalculate Visit Counts

Scans all journal files and recalculates the correct visit_count for each system
based on unique FSDJump/Location/CarrierJump timestamps.

Run this once to fix inflated visit counts in the database.
"""

import os
import sys
import glob
import json
import sqlite3
from collections import defaultdict
from datetime import datetime

def find_journal_dir():
    """Find Elite Dangerous journal directory"""
    # Standard location
    saved_games = os.path.join(os.path.expanduser("~"), "Saved Games", "Frontier Developments", "Elite Dangerous")
    if os.path.isdir(saved_games):
        return saved_games
    return None

def scan_journals_for_visits(journal_dir):
    """Scan all journals and count unique visits per system"""
    
    # Dictionary: system_name -> set of unique timestamps
    system_visits = defaultdict(set)
    
    # Dictionary: system_name -> {first_visit, last_visit, coords, address}
    system_data = {}
    
    journal_pattern = os.path.join(journal_dir, "Journal.*.log")
    journal_files = sorted(glob.glob(journal_pattern))
    
    print(f"Found {len(journal_files)} journal files to scan...")
    
    for i, journal_path in enumerate(journal_files):
        if (i + 1) % 50 == 0:
            print(f"  Processing file {i + 1}/{len(journal_files)}...")
        
        try:
            with open(journal_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_type = event.get('event', '')
                        
                        if event_type in ['FSDJump', 'Location', 'CarrierJump']:
                            system_name = event.get('StarSystem', '')
                            timestamp = event.get('timestamp', '')
                            
                            if system_name and timestamp:
                                # Add this timestamp to the set (duplicates ignored)
                                system_visits[system_name].add(timestamp)
                                
                                # Track first/last visit and other data
                                if system_name not in system_data:
                                    system_data[system_name] = {
                                        'first_visit': timestamp,
                                        'last_visit': timestamp,
                                        'system_address': event.get('SystemAddress'),
                                        'coords': event.get('StarPos', [])
                                    }
                                else:
                                    # Update last visit if newer
                                    if timestamp > system_data[system_name]['last_visit']:
                                        system_data[system_name]['last_visit'] = timestamp
                                    # Update first visit if older
                                    if timestamp < system_data[system_name]['first_visit']:
                                        system_data[system_name]['first_visit'] = timestamp
                                    
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"  Error reading {os.path.basename(journal_path)}: {e}")
            continue
    
    # Calculate visit counts
    results = {}
    for system_name, timestamps in system_visits.items():
        data = system_data.get(system_name, {})
        results[system_name] = {
            'visit_count': len(timestamps),
            'first_visit': data.get('first_visit', ''),
            'last_visit': data.get('last_visit', ''),
            'system_address': data.get('system_address'),
            'coords': data.get('coords', [])
        }
    
    return results

def update_database(visit_data):
    """Update the database with corrected visit counts"""
    
    # Try app/data folder first (dev), then AppData (installed)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(script_dir)  # Go up from tools to app
    data_dir = os.path.join(app_dir, 'data')
    db_path = os.path.join(data_dir, 'user_data.db')
    
    if not os.path.exists(db_path):
        # Fallback to AppData
        app_data = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'EliteMining')
        db_path = os.path.join(app_data, 'user_data.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return 0, 0
    
    print(f"\nUpdating database: {db_path}")
    
    updated = 0
    inserted = 0
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        for system_name, data in visit_data.items():
            # Check if system exists
            cursor.execute('SELECT visit_count FROM visited_systems WHERE system_name = ?', (system_name,))
            result = cursor.fetchone()
            
            coords = data.get('coords', [])
            x_coord = coords[0] if len(coords) > 0 else None
            y_coord = coords[1] if len(coords) > 1 else None
            z_coord = coords[2] if len(coords) > 2 else None
            
            if result:
                old_count = result[0]
                new_count = data['visit_count']
                
                # Update with correct count
                cursor.execute('''
                    UPDATE visited_systems 
                    SET visit_count = ?,
                        first_visit_date = ?,
                        last_visit_date = ?
                    WHERE system_name = ?
                ''', (new_count, data['first_visit'], data['last_visit'], system_name))
                
                if old_count != new_count:
                    updated += 1
                    if old_count > new_count + 10:  # Only show big differences
                        print(f"  Fixed: {system_name}: {old_count} -> {new_count}")
            else:
                # Insert new system
                cursor.execute('''
                    INSERT INTO visited_systems 
                    (system_name, system_address, x_coord, y_coord, z_coord,
                     first_visit_date, last_visit_date, visit_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (system_name, data.get('system_address'), x_coord, y_coord, z_coord,
                      data['first_visit'], data['last_visit'], data['visit_count']))
                inserted += 1
        
        conn.commit()
    
    return updated, inserted

def main():
    print("=" * 60)
    print("EliteMining - Recalculate Visit Counts")
    print("=" * 60)
    print()
    
    # Find journal directory
    journal_dir = find_journal_dir()
    if not journal_dir:
        print("ERROR: Could not find Elite Dangerous journal directory")
        return 1
    
    print(f"Journal directory: {journal_dir}")
    print()
    
    # Scan journals
    print("Scanning all journal files for FSDJump events...")
    print("(This may take a few minutes for large journal histories)")
    print()
    
    visit_data = scan_journals_for_visits(journal_dir)
    
    print()
    print(f"Found {len(visit_data)} unique systems visited")
    
    # Show top 10
    top_systems = sorted(visit_data.items(), key=lambda x: x[1]['visit_count'], reverse=True)[:10]
    print("\nTop 10 most visited systems (from journals):")
    for name, data in top_systems:
        print(f"  {name}: {data['visit_count']} visits")
    
    # Confirm before updating
    print()
    response = input("Update database with corrected counts? (y/n): ").strip().lower()
    if response != 'y':
        print("Aborted.")
        return 0
    
    # Update database
    updated, inserted = update_database(visit_data)
    
    print()
    print(f"Done! Updated {updated} systems, inserted {inserted} new systems.")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
