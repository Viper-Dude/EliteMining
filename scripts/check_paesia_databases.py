import sqlite3
import os

print("=== Checking Paesia in both databases ===\n")

# Check user_data.db in app/data (User Database - hotspot_data table)
user_db_path = "app/data/user_data.db"
if os.path.exists(user_db_path):
    print("1. USER DATABASE (app/data/user_data.db)")
    print("-" * 60)
    conn = sqlite3.connect(user_db_path)
    cursor = conn.cursor()
    
    # Check hotspot_data table
    cursor.execute('''SELECT DISTINCT system_name, body_name, material_name, hotspot_count, scan_date
                      FROM hotspot_data 
                      WHERE system_name = "Paesia" 
                      ORDER BY body_name, material_name''')
    results = cursor.fetchall()
    
    if results:
        current_body = None
        for r in results:
            if r[1] != current_body:
                print(f"\n  Ring: {r[1]}")
                current_body = r[1]
            print(f"    {r[2]}: {r[3]} hotspot(s) - Scan: {r[4]}")
        print(f"\n  Total entries: {len(results)}")
    else:
        print("  ❌ No Paesia entries found in hotspot_data")
    
    conn.close()
else:
    print(f"  ❌ Not found: {user_db_path}")

print("\n" + "=" * 60 + "\n")

# Check default database in app/data/UserDb for install (Default DB - hotspot_data table)
default_db_path = "app/data/UserDb for install/user_data.db"
if os.path.exists(default_db_path):
    print("2. DEFAULT DATABASE (app/data/UserDb for install/user_data.db)")
    print("-" * 60)
    conn = sqlite3.connect(default_db_path)
    cursor = conn.cursor()
    
    # Check hotspot_data table
    cursor.execute('''SELECT DISTINCT system_name, body_name, material_name, hotspot_count, scan_date
                      FROM hotspot_data 
                      WHERE system_name = "Paesia" 
                      ORDER BY body_name, material_name''')
    results = cursor.fetchall()
    
    if results:
        current_body = None
        for r in results:
            if r[1] != current_body:
                print(f"\n  Ring: {r[1]}")
                current_body = r[1]
            print(f"    {r[2]}: {r[3]} hotspot(s) - Scan: {r[4]}")
        print(f"\n  Total entries: {len(results)}")
    else:
        print("  ❌ No Paesia entries found in hotspot_data")
    
    conn.close()
else:
    print(f"  ❌ Not found: {default_db_path}")
