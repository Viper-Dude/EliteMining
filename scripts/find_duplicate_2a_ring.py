import sqlite3

print("=== FINDING DUPLICATE 2 A RING ENTRIES ===\n")

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

# Get ALL entries for 2 A Ring with full details
cursor.execute('''SELECT body_name, material_name, ring_type, ls_distance, density, scan_date
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name = "2 A Ring"
                  ORDER BY material_name''')
results = cursor.fetchall()

print("ALL '2 A Ring' entries in user database:")
print("-" * 70)
for r in results:
    print(f"\nMaterial: {r[1]}")
    print(f"  Ring Type: {r[2]}")
    print(f"  LS Distance: {r[3]}")
    print(f"  Density: {r[4]}")
    print(f"  Scan Date: {r[5]}")

conn.close()

print("\n" + "=" * 70)
print("\nANALYSIS:")
print("  • Icy ring with LS 811.278 - This looks like phantom 2 C Ring data!")
print("  • Metalic ring with LS 820.804 - This is the real 2 A Ring!")
print("  • Real 2 A Ring should be: Metallic, LS ~821.1")
