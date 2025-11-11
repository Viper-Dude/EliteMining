import sqlite3

conn = sqlite3.connect('d:/My Apps Work Folder/Elitemining Working folder/Releases/EliteMining-Dev/app/data/user_data.db')
cursor = conn.cursor()

print("TABLE STRUCTURE:")
cursor.execute('PRAGMA table_info(hotspot_data)')
for row in cursor.fetchall():
    print(row)

print("\nSAMPLE DATA (Phrasinigus):")
cursor.execute("SELECT system_name, body_name, material_name, ring_type, ls_distance FROM hotspot_data WHERE system_name = 'Phrasinigus' LIMIT 10")
for row in cursor.fetchall():
    print(row)

print("\nSAMPLE DATA (HIP 59865):")
cursor.execute("SELECT system_name, body_name, material_name, ring_type, ls_distance FROM hotspot_data WHERE system_name = 'HIP 59865' LIMIT 10")
for row in cursor.fetchall():
    print(row)

conn.close()
