import sqlite3

# Check backup before fix
conn = sqlite3.connect('app/data/user_data.db.backup_20251003_001825')
cursor = conn.cursor()

cursor.execute("""
    SELECT DISTINCT material_name, COUNT(*) as count
    FROM hotspot_data 
    WHERE material_name LIKE '%diamond%' OR material_name LIKE '%opal%'
    GROUP BY material_name
    ORDER BY material_name
""")

print("Backup before fix (001825):")
for material, count in cursor.fetchall():
    print(f"  '{material}': {count} records")

conn.close()
