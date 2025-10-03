"""Check Tollan entries in database"""
import sqlite3

db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT id, system_name, body_name, material_name, ring_type, ls_distance, coord_source, scan_date
    FROM hotspot_data 
    WHERE system_name = 'Tollan'
""")

results = cursor.fetchall()

print(f"\n{'='*80}")
print(f"FOUND {len(results)} ENTRIES FOR TOLLAN")
print(f"{'='*80}\n")

for r in results:
    print(f"ID: {r[0]}")
    print(f"  System: {r[1]}")
    print(f"  Body: '{r[2]}'")
    print(f"  Material: {r[3]}")
    print(f"  Ring Type: {r[4]}")
    print(f"  LS Distance: {r[5]}")
    print(f"  Source: {r[6]}")
    print(f"  Scan Date: {r[7]}")
    print()

conn.close()
