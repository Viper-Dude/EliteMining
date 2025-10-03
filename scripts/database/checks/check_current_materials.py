"""Check what material names are currently in search results"""
import sqlite3
import os

db_path = os.path.join("app", "data", "user_data.db")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current material names in database
    cursor.execute("""
        SELECT DISTINCT material_name 
        FROM hotspot_data 
        ORDER BY material_name
    """)
    
    print("Current material names in database:")
    print("-" * 50)
    for row in cursor.fetchall():
        print(f"  '{row[0]}'")
    
    print("\n" + "=" * 50)
    
    # Check specifically for LTD variants
    cursor.execute("""
        SELECT system_name, body_name, material_name, hotspot_count
        FROM hotspot_data 
        WHERE material_name LIKE '%diamond%' OR material_name LIKE '%temp%'
        COLLATE NOCASE
        ORDER BY system_name, body_name
        LIMIT 20
    """)
    
    print("\nDiamond/Temperature entries (first 20):")
    print("-" * 50)
    results = cursor.fetchall()
    if results:
        for system, body, material, count in results:
            print(f"  {system} / {body} / '{material}' ({count}x)")
    else:
        print("  No diamond entries found")
    
    conn.close()
else:
    print(f"Database not found: {db_path}")
