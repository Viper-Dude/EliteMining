import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

# Check for diamond and opal variants
print("Checking for Low Temperature Diamonds and Void Opals variants:\n")
cursor.execute("""
    SELECT DISTINCT material_name, COUNT(*) as count
    FROM hotspot_data 
    WHERE material_name LIKE '%diamond%' OR material_name LIKE '%opal%'
    GROUP BY material_name
    ORDER BY material_name
""")

results = cursor.fetchall()
print(f"Found {len(results)} distinct diamond/opal variants:\n")
for material, count in results:
    print(f"  '{material}': {count} records")

conn.close()
