"""Check for malformed ring names in database"""
import sqlite3

db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check for malformed entries with lowercase 'a' or other issues
cursor.execute("""
    SELECT id, system_name, body_name, material_name, ring_type, ls_distance, scan_date, coord_source
    FROM hotspot_data 
    WHERE body_name LIKE '%a A%' OR body_name LIKE '%a B%' OR body_name LIKE '%a C%'
""")

results = cursor.fetchall()

if results:
    print(f"\n{'='*80}")
    print(f"FOUND {len(results)} MALFORMED RING NAME ENTRIES:")
    print(f"{'='*80}\n")
    
    for r in results:
        print(f"ID: {r[0]}")
        print(f"  System: {r[1]}")
        print(f"  Body: '{r[2]}' ← MALFORMED")
        print(f"  Material: {r[3]}")
        print(f"  Ring Type: {r[4]}")
        print(f"  LS: {r[5]}")
        print(f"  Date: {r[6]}")
        print(f"  Source: {r[7]}")
        print()
else:
    print("\n✅ No malformed entries found")

conn.close()
