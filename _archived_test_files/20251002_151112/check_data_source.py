import sqlite3

# Connect to database
db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check the 12th column (index 11) which should be data_source
cursor.execute("SELECT id, system_name, body_name, material_name, data_source FROM hotspot_data WHERE system_name = 'Paesia'")
rows = cursor.fetchall()

print(f"\n{'='*80}")
print(f"CHECKING PAESIA ENTRIES")
print(f"{'='*80}\n")

for row in rows:
    print(f"ID {row[0]}: {row[1]} - {row[2]} - {row[3]} - data_source='{row[4]}'")

# Now check all entries with data_source
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE data_source = 'visited_systems'")
count = cursor.fetchone()[0]
print(f"\n\nTotal entries with data_source='visited_systems': {count}")

# Check if it's maybe stored differently
cursor.execute("SELECT DISTINCT data_source FROM hotspot_data WHERE data_source IS NOT NULL AND data_source != ''")
sources = cursor.fetchall()
print(f"\nAll distinct data_source values:")
for s in sources:
    print(f"  '{s[0]}'")

conn.close()
