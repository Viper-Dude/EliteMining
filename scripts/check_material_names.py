import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== MATERIAL NAMES IN 11 B RING ===\n")

c.execute("""
    SELECT material_name, hotspot_count 
    FROM hotspot_data 
    WHERE system_name = 'Praea Euq JF-Q b5-4' 
    AND body_name LIKE '%11 B%'
    ORDER BY material_name
""")

results = c.fetchall()

print(f"Found {len(results)} materials:\n")
for mat_name, count in results:
    print(f"  '{mat_name}' (repr: {repr(mat_name)}) - {count} hotspots")

conn.close()
