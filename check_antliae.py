import sqlite3

conn = sqlite3.connect(r"app\data\UserDb for install\user_data.db")
c = conn.cursor()

# Check for Antliae PX-U hotspot data
c.execute("SELECT system_name, body_name, ring_type, material_name FROM hotspot_data WHERE system_name LIKE ?", ('%Antliae%PX-U%',))
rows = c.fetchall()
print(f"Found {len(rows)} Antliae PX-U rows in installer database:")
for row in rows:
    print(f"  System: {row[0]}, Body: {row[1]}, Ring: {row[2]}, Mineral: {row[3]}")

conn.close()
