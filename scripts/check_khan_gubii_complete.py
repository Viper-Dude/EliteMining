import sqlite3

print("=== COMPLETE DATA CHECK FOR KHAN GUBII ===\n")

db_path = "app/data/UserDb for install/user_data.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

system = "Khan Gubii"

print(f"System: {system}")
print("=" * 70)

# Get ALL data for this system
cursor.execute('''
    SELECT body_name, material_name, hotspot_count, ring_type, ls_distance, density
    FROM hotspot_data
    WHERE system_name = ?
    ORDER BY body_name, material_name
''', (system,))

results = cursor.fetchall()

if results:
    print(f"\nFound {len(results)} entries:\n")
    current_body = None
    for r in results:
        if r[0] != current_body:
            print(f"\n{r[0]}:")
            print(f"  Ring Type: {r[3]}, LS: {r[4]}, Density: {r[5]}")
            print(f"  Materials:")
            current_body = r[0]
        print(f"    • {r[1]}: {r[2]} hotspot(s)")
else:
    print("  No data found")

# Also check with GROUP_CONCAT to see what the query returns
print("\n" + "=" * 70)
print("\nGROUP_CONCAT QUERY (what search uses):")
print("-" * 70)

cursor.execute('''
    SELECT body_name, 
           GROUP_CONCAT(material_name || ' (' || hotspot_count || ')', ', ') as materials
    FROM hotspot_data
    WHERE system_name = ?
    GROUP BY body_name
    ORDER BY body_name
''', (system,))

grouped = cursor.fetchall()

for g in grouped:
    print(f"\n{g[0]}: {g[1]}")

conn.close()
