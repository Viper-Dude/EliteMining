import sqlite3

print("=== CHECKING WHAT'S ACTUALLY IN THE DATABASE ===\n")

db_path = "app/data/UserDb for install/user_data.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check a few systems from the screenshot
systems_to_check = [
    "Col 285 Sector UE-G c11-5",
    "Khan Gubii",
    "HIP 77818"
]

for system in systems_to_check:
    print(f"\n{system}:")
    print("-" * 70)
    
    cursor.execute('''
        SELECT body_name, material_name, hotspot_count
        FROM hotspot_data
        WHERE system_name = ?
        ORDER BY body_name, material_name
    ''', (system,))
    
    results = cursor.fetchall()
    
    if results:
        current_body = None
        for r in results:
            if r[0] != current_body:
                print(f"\n  {r[0]}:")
                current_body = r[0]
            print(f"    {r[1]}: {r[2]}")
    else:
        print("  No data found")

conn.close()
