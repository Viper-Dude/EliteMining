import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check for Paesia 2 A Ring
print("=== Checking Paesia 2 A Ring ===")
cursor.execute('''
    SELECT system_name, body_name, material_name, ls_distance, scan_date, coord_source
    FROM hotspot_data 
    WHERE system_name = 'Paesia' AND body_name LIKE '%2 A%'
    ORDER BY body_name, material_name
''')

results = cursor.fetchall()
print(f"\nFound {len(results)} entries:\n")

if results:
    for r in results:
        print(f"System: {r[0]}")
        print(f"Body: {r[1]}")
        print(f"Material: {r[2]}")
        print(f"LS Distance: {r[3]}")
        print(f"Scan Date: {r[4]}")
        print(f"Source: {r[5]}")
        print("-" * 50)
else:
    print("No entries found!")
    
    # Check what bodies ARE in Paesia
    print("\n=== All Paesia bodies in database ===")
    cursor.execute('''
        SELECT DISTINCT body_name 
        FROM hotspot_data 
        WHERE system_name = 'Paesia'
        ORDER BY body_name
    ''')
    bodies = cursor.fetchall()
    for body in bodies:
        print(f"  - {body[0]}")

conn.close()
