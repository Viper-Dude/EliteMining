import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.execute('SELECT body_name, material_name, ring_type FROM hotspot_data WHERE system_name = "Delkar" ORDER BY body_name, material_name')
results = cursor.fetchall()

print("Database ring_type values for Delkar:")
print("Body | Material | Ring Type")
print("-" * 40)
for row in results:
    ring_type_value = row[2] if row[2] is not None else "NULL"
    print(f"{row[0]:10s} | {row[1]:15s} | {ring_type_value}")

conn.close()