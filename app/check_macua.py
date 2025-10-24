import sqlite3

conn = sqlite3.connect('data/user_data.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT body_name, ring_type, ls_distance, material_name
    FROM hotspot_data 
    WHERE system_name='Macua' 
    LIMIT 10
''')

print("Macua Ring Data After EDSM Update:")
print("-" * 70)
print(f"{'Ring':<15} {'Type':<20} {'LS Dist':<10} {'Material':<20}")
print("-" * 70)

for row in cursor.fetchall():
    ring = row[0] or "?"
    rtype = row[1] or "MISSING"
    ls = row[2] if row[2] is not None else "MISSING"
    mat = row[3] or "?"
    print(f"{ring:<15} {rtype:<20} {ls:<10} {mat:<20}")

conn.close()
