#!/usr/bin/env python3
"""
Debug Paesia Alexandrite Search
Compare EliteMining results with what should be in the database
"""

import sys
from pathlib import Path
sys.path.append('app')

import sqlite3
import math

def calculate_distance(coord1, coord2):
    """Calculate distance between two coordinates"""
    if not coord1 or not coord2:
        return 999.9
    
    dx = coord1['x'] - coord2['x']
    dy = coord1['y'] - coord2['y'] 
    dz = coord1['z'] - coord2['z']
    return math.sqrt(dx*dx + dy*dy + dz*dz)

def debug_paesia_search():
    """Debug the Paesia Alexandrite search discrepancy"""
    
    print("=" * 70)
    print("DEBUGGING PAESIA ALEXANDRITE SEARCH")
    print("=" * 70)
    
    # Database path
    db_path = Path("app/data/user_data.db")
    
    # First, check if Paesia coordinates are in our database
    print("1. Checking Paesia coordinates:")
    print("-" * 35)
    
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        
        # Check for Paesia in user database
        cursor.execute("""
            SELECT DISTINCT system_name, x_coord, y_coord, z_coord, coord_source
            FROM hotspot_data 
            WHERE LOWER(system_name) = LOWER(?)
            LIMIT 1
        """, ('Paesia',))
        
        paesia_coords = cursor.fetchone()
        if paesia_coords:
            paesia_system, px, py, pz, source = paesia_coords
            print(f"  Paesia found in user database: ({px}, {py}, {pz}) from {source}")
            paesia_coord_dict = {'x': px, 'y': py, 'z': pz}
        else:
            print("  Paesia NOT found in user database")
            paesia_coord_dict = None
            
            # Check galaxy database  
            galaxy_db = Path("app/data/galaxy_systems.db")
            if galaxy_db.exists():
                with sqlite3.connect(str(galaxy_db)) as galaxy_conn:
                    galaxy_cursor = galaxy_conn.cursor()
                    galaxy_cursor.execute("SELECT x, y, z FROM systems WHERE LOWER(name) = LOWER(?) LIMIT 1", ('Paesia',))
                    galaxy_result = galaxy_cursor.fetchone()
                    if galaxy_result:
                        px, py, pz = galaxy_result
                        print(f"  Paesia found in galaxy database: ({px}, {py}, {pz})")
                        paesia_coord_dict = {'x': px, 'y': py, 'z': pz}
                    else:
                        print("  Paesia NOT found in galaxy database either")
    
    # Check total Alexandrite records
    print(f"\n2. Total Alexandrite records in database:")
    print("-" * 45)
    
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE material_name = ?", ('Alexandrite',))
        total_alex = cursor.fetchone()[0]
        print(f"  Total Alexandrite hotspots: {total_alex}")
        
        # Get some sample Alexandrite records with coordinates
        cursor.execute("""
            SELECT system_name, body_name, hotspot_count, x_coord, y_coord, z_coord, ls_distance
            FROM hotspot_data 
            WHERE material_name = ? AND x_coord IS NOT NULL
            ORDER BY system_name
            LIMIT 10
        """, ('Alexandrite',))
        
        samples = cursor.fetchall()
        print(f"  Sample records with coordinates: {len(samples)}")
        
        for system, body, count, x, y, z, ls in samples[:3]:
            if paesia_coord_dict:
                dist = calculate_distance(paesia_coord_dict, {'x': x, 'y': y, 'z': z})
                print(f"    {system} | {body} | {count} hotspots | {dist:.1f} LY | LS:{ls}")
            else:
                print(f"    {system} | {body} | {count} hotspots | ? LY | LS:{ls}")
    
    # Check if there are any systems within 100 LY of Paesia
    if paesia_coord_dict:
        print(f"\n3. Alexandrite systems within 100 LY of Paesia:")
        print("-" * 50)
        
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT system_name, body_name, hotspot_count, x_coord, y_coord, z_coord, ls_distance
                FROM hotspot_data 
                WHERE material_name = ? AND x_coord IS NOT NULL
            """, ('Alexandrite',))
            
            all_records = cursor.fetchall()
            nearby_systems = []
            
            for system, body, count, x, y, z, ls in all_records:
                if x is not None and y is not None and z is not None:
                    dist = calculate_distance(paesia_coord_dict, {'x': x, 'y': y, 'z': z})
                    if dist <= 100:
                        nearby_systems.append((dist, system, body, count, ls))
            
            nearby_systems.sort()  # Sort by distance
            
            print(f"  Found {len(nearby_systems)} systems within 100 LY:")
            for dist, system, body, count, ls in nearby_systems[:15]:  # Show first 15
                print(f"    {dist:5.1f} LY | {system:<25} | {body} | {count} hotspots | LS:{ls}")
                
            if len(nearby_systems) > 15:
                print(f"    ... and {len(nearby_systems) - 15} more systems")
    
    # Check if the search is working as expected by simulating it
    print(f"\n4. Simulating the ring finder search:")
    print("-" * 40)
    
    if paesia_coord_dict:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT system_name, body_name, material_name, hotspot_count,
                       x_coord, y_coord, z_coord, coord_source, ls_distance, density
                FROM hotspot_data
                WHERE material_name = ?
                ORDER BY hotspot_count DESC, system_name, body_name
            """, ('Alexandrite',))
            
            results = cursor.fetchall()
            filtered_results = []
            
            for system_name, body_name, material_name, hotspot_count, x_coord, y_coord, z_coord, coord_source, ls_distance, density in results:
                if x_coord is not None and y_coord is not None and z_coord is not None:
                    system_coords = {'x': x_coord, 'y': y_coord, 'z': z_coord}
                    distance = calculate_distance(paesia_coord_dict, system_coords)
                    
                    if distance <= 100:  # Within 100 LY
                        filtered_results.append({
                            'system': system_name,
                            'body': body_name,
                            'distance': distance,
                            'hotspots': hotspot_count,
                            'ls': ls_distance
                        })
            
            # Sort by distance
            filtered_results.sort(key=lambda x: x['distance'])
            
            print(f"  Ring finder should return {len(filtered_results)} results:")
            for i, result in enumerate(filtered_results[:10], 1):  # Show top 10
                print(f"    {i:2d}. {result['distance']:5.1f} LY | {result['system']:<25} | {result['body']} | LS:{result['ls']}")
    
    print(f"\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    
    if not paesia_coord_dict:
        print("❌ ISSUE: Paesia coordinates not found - this will cause problems")
    elif paesia_coord_dict:
        print("✅ Paesia coordinates found - search should work")
        
    print("\nIf EliteMining shows different results than expected:")
    print("1. Check if ring finder is using correct search parameters")
    print("2. Verify material filtering is working correctly")  
    print("3. Check if distance calculation is correct")
    print("=" * 70)

if __name__ == "__main__":
    debug_paesia_search()