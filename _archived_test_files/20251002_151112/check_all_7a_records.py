import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.execute('''
    SELECT body_name, material_name, ring_type, hotspot_count 
    FROM hotspot_data 
    WHERE system_name = "Delkar" AND body_name LIKE "%7 A%" 
    ORDER BY material_name
''')
results = cursor.fetchall()

print(f"All Delkar 7 A Ring database records ({len(results)} total):")
print("Body | Material | Ring Type | Count")
print("-" * 50)
for row in results:
    ring_type_value = row[2] if row[2] is not None else "NULL"
    print(f"{row[0]:15s} | {row[1]:15s} | {ring_type_value:10s} | {row[3]}")

conn.close()