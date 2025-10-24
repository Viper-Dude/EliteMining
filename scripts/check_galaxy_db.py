"""Check contents of galaxy_systems.db"""
import sqlite3
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

db_path = os.path.join(os.path.dirname(__file__), '..', 'app', 'data', 'galaxy_systems.db')

print(f"Checking: {db_path}\n")

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    
    # Get tables
    cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables: {tables}\n")
    
    # Check systems table
    if 'systems' in tables:
        cursor.execute('SELECT COUNT(*) FROM systems')
        print(f"Systems count: {cursor.fetchone()[0]}")
        
        cursor.execute('SELECT * FROM systems LIMIT 3')
        print("Sample systems:")
        for row in cursor.fetchall():
            print(f"  {row}")
    
    print()
    
    # Check hotspot_data table  
    if 'hotspot_data' in tables:
        cursor.execute('SELECT COUNT(*) FROM hotspot_data')
        print(f"Hotspots count: {cursor.fetchone()[0]}")
        
        # Check for Macua in default DB
        cursor.execute('SELECT * FROM hotspot_data WHERE system_name = "Macua" LIMIT 5')
        macua_data = cursor.fetchall()
        if macua_data:
            print("\nMacua data in galaxy_systems.db:")
            for row in macua_data:
                print(f"  {row}")
        else:
            print("\nNo Macua data in galaxy_systems.db")
        
        # Check column structure
        cursor.execute('PRAGMA table_info(hotspot_data)')
        columns = cursor.fetchall()
        print("\nHotspot_data columns:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")

input("\nPress Enter to exit...")
