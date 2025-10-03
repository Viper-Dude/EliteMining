import sqlite3

conn = sqlite3.connect(r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db')
cursor = conn.cursor()

# Check specific IDs we know should have visited_systems
cursor.execute("SELECT id, coord_source FROM hotspot_data WHERE id IN (329919, 329920, 329921, 329922, 329923)")
rows = cursor.fetchall()

print("\nChecking specific IDs:")
for row in rows:
    print(f"ID {row[0]}: coord_source = '{row[1]}' (length: {len(row[1]) if row[1] else 0})")

# Check all unique coord_source values
cursor.execute("SELECT DISTINCT coord_source FROM hotspot_data WHERE coord_source IS NOT NULL")
sources = cursor.fetchall()

print(f"\nAll unique coord_source values:")
for s in sources:
    print(f"  '{s[0]}' (length: {len(s[0])})")

# Try wildcard search
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE coord_source LIKE '%visited%'")
count = cursor.fetchone()[0]
print(f"\nEntries with coord_source containing 'visited': {count}")

conn.close()
