import sqlite3

# Connect to database
db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Query all Paesia entries
cursor.execute("SELECT * FROM hotspot_data WHERE system_name LIKE '%Paesia%'")
rows = cursor.fetchall()

print(f"\n{'='*80}")
print(f"FOUND {len(rows)} ENTRIES FOR PAESIA IN user_data.db")
print(f"{'='*80}\n")

for i, row in enumerate(rows, 1):
    print(f"Entry #{i}:")
    print(f"  ID: {row[0]}")
    print(f"  System: {row[1]}")
    print(f"  Body: {row[2]}")
    print(f"  Ring: {row[3]}")
    print(f"  Material: {row[4]}")
    print(f"  Count: {row[5]}")
    print(f"  Ring Type: {row[6]}")
    print(f"  LS Distance: {row[7]}")
    print(f"  Density: {row[8]}")
    print(f"  Inner Radius: {row[9]}")
    print(f"  Outer Radius: {row[10]}")
    print(f"  Source: {row[11]}")
    print()

conn.close()
