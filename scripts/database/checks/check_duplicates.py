#!/usr/bin/env python3
"""
Check user_data.db for duplicate hotspots, systems, and rings
"""

import sqlite3
import os
from pathlib import Path
from collections import defaultdict

# Database path
DB_PATH = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db"

def check_database_exists():
    """Verify database exists"""
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at: {DB_PATH}")
        return False
    print(f"✓ Database found: {DB_PATH}")
    return True

def check_hotspot_duplicates():
    """Check for duplicate hotspots"""
    print("\n" + "="*80)
    print("CHECKING FOR DUPLICATE HOTSPOTS")
    print("="*80)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get all hotspots
        cursor.execute("""
            SELECT id, system_name, body_name, material_name, 
                   COUNT(*) as count
            FROM hotspot_data
            GROUP BY system_name, body_name, material_name
            HAVING count > 1
            ORDER BY count DESC
        """)
        
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("✓ No duplicate hotspots found")
            conn.close()
            return 0
        
        print(f"⚠️  Found {len(duplicates)} groups of duplicate hotspots:\n")
        total_dupes = 0
        
        for system, body, material, count in duplicates:
            print(f"  System: {system}")
            print(f"  Body: {body}")
            print(f"  Material: {material}")
            print(f"  Count: {count} (should be 1)")
            
            # Get details of all duplicates
            cursor.execute("""
                SELECT id, ring_type, ls_distance, density, discovered_by
                FROM hotspot_data
                WHERE system_name = ? AND body_name = ? AND material_name = ?
                ORDER BY id
            """, (system, body, material))
            
            for hotspot_id, ring_type, ls_distance, density, discovered_by in cursor.fetchall():
                print(f"    - ID: {hotspot_id}, Ring: {ring_type}, LS: {ls_distance}, Density: {density}, By: {discovered_by}")
            
            print()
            total_dupes += (count - 1)
        
        print(f"📊 Total duplicate entries: {total_dupes}")
        conn.close()
        return total_dupes
        
    except Exception as e:
        print(f"❌ Error checking hotspot duplicates: {e}")
        return -1

def check_system_duplicates():
    """Check for duplicate systems"""
    print("\n" + "="*80)
    print("CHECKING FOR DUPLICATE SYSTEMS")
    print("="*80)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if systems table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='systems'")
        if not cursor.fetchone():
            print("⚠️  No 'systems' table found in database")
            conn.close()
            return 0
        
        # Get all systems with duplicates
        cursor.execute("""
            SELECT system_name, COUNT(*) as count
            FROM systems
            GROUP BY system_name
            HAVING count > 1
            ORDER BY count DESC
        """)
        
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("✓ No duplicate systems found")
            conn.close()
            return 0
        
        print(f"⚠️  Found {len(duplicates)} duplicate systems:\n")
        total_dupes = 0
        
        for system_name, count in duplicates:
            print(f"  System: {system_name}")
            print(f"  Count: {count} (should be 1)")
            
            # Get details
            cursor.execute("""
                SELECT id, coordinates, discovered_by, discovered_date
                FROM systems
                WHERE system_name = ?
                ORDER BY id
            """, (system_name,))
            
            for sys_id, coords, discovered_by, discovered_date in cursor.fetchall():
                print(f"    - ID: {sys_id}, Coords: {coords}, By: {discovered_by}, Date: {discovered_date}")
            
            print()
            total_dupes += (count - 1)
        
        print(f"📊 Total duplicate entries: {total_dupes}")
        conn.close()
        return total_dupes
        
    except Exception as e:
        print(f"❌ Error checking system duplicates: {e}")
        return -1

def check_ring_duplicates():
    """Check for duplicate rings"""
    print("\n" + "="*80)
    print("CHECKING FOR DUPLICATE RINGS")
    print("="*80)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if rings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rings'")
        if not cursor.fetchone():
            print("⚠️  No 'rings' table found in database")
            conn.close()
            return 0
        
        # Get all rings with duplicates
        cursor.execute("""
            SELECT system_name, body_name, ring_name, COUNT(*) as count
            FROM rings
            GROUP BY system_name, body_name, ring_name
            HAVING count > 1
            ORDER BY count DESC
        """)
        
        duplicates = cursor.fetchall()
        
        if not duplicates:
            print("✓ No duplicate rings found")
            conn.close()
            return 0
        
        print(f"⚠️  Found {len(duplicates)} groups of duplicate rings:\n")
        total_dupes = 0
        
        for system, body, ring_name, count in duplicates:
            print(f"  System: {system}")
            print(f"  Body: {body}")
            print(f"  Ring: {ring_name}")
            print(f"  Count: {count} (should be 1)")
            
            # Get details
            cursor.execute("""
                SELECT id, ring_type, discovered_by, discovered_date
                FROM rings
                WHERE system_name = ? AND body_name = ? AND ring_name = ?
                ORDER BY id
            """, (system, body, ring_name))
            
            for ring_id, ring_type, discovered_by, discovered_date in cursor.fetchall():
                print(f"    - ID: {ring_id}, Type: {ring_type}, By: {discovered_by}, Date: {discovered_date}")
            
            print()
            total_dupes += (count - 1)
        
        print(f"📊 Total duplicate entries: {total_dupes}")
        conn.close()
        return total_dupes
        
    except Exception as e:
        print(f"❌ Error checking ring duplicates: {e}")
        return -1

def get_database_stats():
    """Get general database statistics"""
    print("\n" + "="*80)
    print("DATABASE STATISTICS")
    print("="*80)
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Get table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        
        print(f"\nTables in database: {len(tables)}")
        for (table_name,) in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  - {table_name}: {count} rows")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error getting database stats: {e}")

def main():
    """Main function"""
    print("\n" + "🔍 DUPLICATE CHECKER FOR user_data.db" + "\n")
    
    if not check_database_exists():
        return
    
    get_database_stats()
    
    hotspot_dupes = check_hotspot_duplicates()
    system_dupes = check_system_duplicates()
    ring_dupes = check_ring_duplicates()
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Duplicate Hotspots: {hotspot_dupes if hotspot_dupes >= 0 else 'Error'}")
    print(f"Duplicate Systems: {system_dupes if system_dupes >= 0 else 'Error'}")
    print(f"Duplicate Rings: {ring_dupes if ring_dupes >= 0 else 'Error'}")
    
    total = (hotspot_dupes if hotspot_dupes >= 0 else 0) + \
            (system_dupes if system_dupes >= 0 else 0) + \
            (ring_dupes if ring_dupes >= 0 else 0)
    
    print(f"\n{'✓ No duplicates found!' if total == 0 else f'⚠️  Total duplicates: {total}'}")

if __name__ == "__main__":
    main()
