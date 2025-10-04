import sqlite3

print("=== CHECKING PAESIA 2 a A RING DATA IN DEFAULT DATABASE ===\n")

db_path = "app/data/UserDb for install/user_data.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get ALL data for 2 a A Ring
print("1. FULL DATA FOR 'Paesia 2 a A Ring':")
print("-" * 70)
cursor.execute('''SELECT id, body_name, material_name, hotspot_count, 
                         ring_type, ls_distance, density, scan_date
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name = "2 a A Ring"
                  ORDER BY material_name''')
results = cursor.fetchall()

total_hotspots = 0
for r in results:
    print(f"ID: {r[0]}")
    print(f"  Material: {r[2]}")
    print(f"  Hotspot Count: {r[3]}")
    print(f"  Ring Type: {r[4]}")
    print(f"  LS Distance: {r[5]}")
    print(f"  Density: {r[6]}")
    print(f"  Scan Date: {r[7]}")
    print()
    total_hotspots += r[3]

print(f"Total individual material entries: {len(results)}")
print(f"Sum of hotspot counts: {total_hotspots}")

# Check if there are duplicates
print("\n" + "=" * 70)
print("\n2. CHECKING FOR DUPLICATE ENTRIES:")
print("-" * 70)
cursor.execute('''SELECT material_name, COUNT(*) as count
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name = "2 a A Ring"
                  GROUP BY material_name
                  HAVING COUNT(*) > 1''')
duplicates = cursor.fetchall()

if duplicates:
    print("⚠️  DUPLICATES FOUND:")
    for d in duplicates:
        print(f"  {d[0]}: {d[1]} entries")
else:
    print("✓ No duplicates found")

# Check what "All Materials" query would return
print("\n" + "=" * 70)
print("\n3. SIMULATING 'ALL MATERIALS' QUERY:")
print("-" * 70)
cursor.execute('''SELECT DISTINCT material_name, hotspot_count
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name = "2 a A Ring"
                  ORDER BY material_name''')
results = cursor.fetchall()

print("Materials returned by DISTINCT query:")
for r in results:
    print(f"  {r[0]}: {r[1]} hotspots")

print(f"\nTotal materials: {len(results)}")
print(f"Sum of hotspots: {sum(r[1] for r in results)}")

conn.close()

print("\n" + "=" * 70)
print("\nCONCLUSION:")
print("If 'All Materials' shows '(5)', it's summing Gran(3) + Tri(2) = 5")
print("This is CORRECT behavior - it's the total hotspot count for the ring")
