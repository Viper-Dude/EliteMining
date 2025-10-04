import sqlite3

print("=== ADDING METADATA TO 'Paesia 2 a A Ring' IN DEFAULT DATABASE ===\n")

db_path = "app/data/UserDb for install/user_data.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check what columns exist
cursor.execute("PRAGMA table_info(hotspot_data)")
columns = [col[1] for col in cursor.fetchall()]
print(f"Available columns: {columns}\n")

# Check current state
print("BEFORE UPDATE:")
print("-" * 70)
cursor.execute('''SELECT body_name, material_name, ring_type, ls_distance, density,
                         inner_radius, outer_radius
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name = "2 a A Ring"
                  ORDER BY material_name''')
results = cursor.fetchall()

for r in results:
    print(f"Material: {r[1]}")
    print(f"  Ring Type: {r[2]}")
    print(f"  LS Distance: {r[3]}")
    print(f"  Density: {r[4]}")
    print(f"  Inner Radius: {r[5]}")
    print(f"  Outer Radius: {r[6]}")
    print()

# Update with metadata from journal scan events
print("\n" + "=" * 70)
print("UPDATING METADATA...")
print("-" * 70)

cursor.execute('''UPDATE hotspot_data 
                  SET ring_type = 'Icy',
                      ls_distance = 833.224795,
                      density = 7.105351,
                      inner_radius = 8855600.0,
                      outer_radius = 23075000.0
                  WHERE system_name = "Paesia" 
                    AND body_name = "2 a A Ring"''')

rows_updated = cursor.rowcount
conn.commit()

print(f"✓ Updated {rows_updated} row(s)")

# Verify update
print("\n" + "=" * 70)
print("AFTER UPDATE:")
print("-" * 70)
cursor.execute('''SELECT body_name, material_name, ring_type, ls_distance, density,
                         inner_radius, outer_radius
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name = "2 a A Ring"
                  ORDER BY material_name''')
results = cursor.fetchall()

for r in results:
    print(f"Material: {r[1]}")
    print(f"  Ring Type: {r[2]}")
    print(f"  LS Distance: {r[3]}")
    print(f"  Density: {r[4]}")
    print(f"  Inner Radius: {r[5]}")
    print(f"  Outer Radius: {r[6]}")
    print()

conn.close()

print("=" * 70)
print("\n✅ DEFAULT DATABASE UPDATED SUCCESSFULLY!")
