import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== COORDINATES FOR BOTH RINGS ===\n")

c.execute("""
    SELECT DISTINCT body_name, x_coord, y_coord, z_coord, coord_source, scan_date 
    FROM hotspot_data 
    WHERE system_name = 'Praea Euq JF-Q b5-4'
    ORDER BY body_name
""")

results = c.fetchall()

for body, x, y, z, source, date in results:
    print(f"{body}:")
    print(f"  Coordinates: X={x}, Y={y}, Z={z}")
    print(f"  Source: {source}")
    print(f"  Scan Date: {date}\n")

conn.close()
