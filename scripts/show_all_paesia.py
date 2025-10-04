import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all Paesia entries
print("=== ALL PAESIA ENTRIES IN DATABASE ===\n")
cursor.execute('''
    SELECT system_name, body_name, material_name, hotspot_count, 
           ls_distance, ring_type, inner_radius, outer_radius, ring_mass, 
           density, scan_date, coord_source
    FROM hotspot_data 
    WHERE system_name = 'Paesia'
    ORDER BY body_name, material_name
''')

results = cursor.fetchall()
print(f"Found {len(results)} total entries for Paesia\n")
print("=" * 120)

for i, r in enumerate(results, 1):
    print(f"\nEntry {i}:")
    print(f"  System: {r[0]}")
    print(f"  Body: {r[1]}")
    print(f"  Material: {r[2]}")
    print(f"  Hotspot Count: {r[3]}")
    print(f"  LS Distance: {r[4] if r[4] is not None else 'NONE'}")
    print(f"  Ring Type: {r[5] if r[5] else 'NONE'}")
    print(f"  Inner Radius: {r[6] if r[6] else 'NONE'}")
    print(f"  Outer Radius: {r[7] if r[7] else 'NONE'}")
    print(f"  Ring Mass: {r[8] if r[8] else 'NONE'}")
    print(f"  Density: {r[9] if r[9] else 'NONE'}")
    print(f"  Scan Date: {r[10]}")
    print(f"  Source: {r[11]}")
    print("-" * 120)

# Summary by body
print("\n\n=== SUMMARY BY BODY ===\n")
cursor.execute('''
    SELECT body_name, 
           COUNT(*) as material_count,
           MIN(ls_distance) as ls_dist,
           MIN(ring_type) as ring_type
    FROM hotspot_data 
    WHERE system_name = 'Paesia'
    GROUP BY body_name
    ORDER BY body_name
''')

bodies = cursor.fetchall()
for body in bodies:
    print(f"{body[0]}: {body[1]} materials, LS={body[2]}, Type={body[3]}")

conn.close()
