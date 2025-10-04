import sqlite3

print("=== INVESTIGATING PAESIA RING TYPE/LS/DENSITY DATA ===\n")

# Check user database - get ALL columns
print("1. USER DATABASE (app/data/user_data.db)")
print("-" * 60)
conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

# First, check table schema
cursor.execute("PRAGMA table_info(hotspot_data)")
columns = cursor.fetchall()
print("Available columns in hotspot_data:")
for col in columns:
    print(f"  • {col[1]} ({col[2]})")

print("\n" + "-" * 60)
print("Paesia ring data:")
cursor.execute('''SELECT body_name, material_name, hotspot_count, 
                         system_address, body_id, x_coord, y_coord, z_coord
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name, material_name''')
results = cursor.fetchall()

current_body = None
for r in results:
    if r[0] != current_body:
        print(f"\n{r[0]}:")
        print(f"  System Address: {r[3]}, Body ID: {r[4]}")
        print(f"  Coords: {r[5]}, {r[6]}, {r[7]}")
        print(f"  Materials:")
        current_body = r[0]
    print(f"    • {r[1]}: {r[2]} hotspot(s)")

conn.close()

print("\n" + "=" * 60 + "\n")

# Check default database
print("2. DEFAULT DATABASE (app/data/UserDb for install/user_data.db)")
print("-" * 60)
conn = sqlite3.connect('app/data/UserDb for install/user_data.db')
cursor = conn.cursor()

# Check schema
cursor.execute("PRAGMA table_info(hotspot_data)")
columns = cursor.fetchall()
print("Available columns in hotspot_data:")
for col in columns:
    print(f"  • {col[1]} ({col[2]})")

print("\n" + "-" * 60)
print("Paesia ring data:")
cursor.execute('''SELECT body_name, material_name, hotspot_count,
                         system_address, body_id, x_coord, y_coord, z_coord
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name, material_name''')
results = cursor.fetchall()

current_body = None
for r in results:
    if r[0] != current_body:
        print(f"\n{r[0]}:")
        print(f"  System Address: {r[3]}, Body ID: {r[4]}")
        print(f"  Coords: {r[5]}, {r[6]}, {r[7]}")
        print(f"  Materials:")
        current_body = r[0]
    print(f"    • {r[1]}: {r[2]} hotspot(s)")

conn.close()

print("\n" + "=" * 60)
print("\nNOTE: Ring Type, LS Distance, and Density are NOT stored")
print("in hotspot_data table. Need to check where this data comes from!")
