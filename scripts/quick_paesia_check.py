import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()

print("PAESIA 2 A RING - ALL MATERIALS:")
print("=" * 80)
c.execute('''SELECT material_name, ring_type, density, ls_distance, hotspot_count
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name = "2 A Ring"
             ORDER BY material_name''')

for r in c.fetchall():
    print(f"{r[0]:20} | Type:{str(r[1]):10} | Density:{str(r[2]):10} | LS:{str(r[3]):6} | Count:{r[4]}")

conn.close()
