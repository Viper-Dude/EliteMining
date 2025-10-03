"""Check OT Serpentis entries"""
import sqlite3

db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT id, system_name, body_name, material_name 
    FROM hotspot_data 
    WHERE system_name LIKE '%Serpentis%'
""")

results = cursor.fetchall()

print(f"\n{'='*80}")
print(f"FOUND {len(results)} ENTRIES FOR SERPENTIS SYSTEMS")
print(f"{'='*80}\n")

for r in results[:20]:
    print(f"ID: {r[0]:6} | System: {r[1]:20} | Body: '{r[2]:20}' | Material: {r[3]}")

conn.close()
