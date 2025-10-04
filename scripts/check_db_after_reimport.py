import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()

print("CURRENT DATABASE AFTER REIMPORT:")
print("="*80)

c.execute('''SELECT body_name, material_name, ring_type, ls_distance, hotspot_count, scan_date
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name LIKE "%2%"
             ORDER BY body_name, material_name''')

for r in c.fetchall():
    print(f"{r[0]:20} | {r[1]:20} | {r[2]:12} | LS:{str(r[3]):8} | Count:{r[4]} | {r[5]}")

conn.close()
