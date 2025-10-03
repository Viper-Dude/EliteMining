import sqlite3

# Connect to database
db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get column names
cursor.execute("PRAGMA table_info(hotspot_data)")
columns = cursor.fetchall()
print("\nColumn mapping:")
for col in columns:
    print(f"  Index {col[0]}: {col[1]} ({col[2]})")

# Query Paesia with all columns
cursor.execute("SELECT * FROM hotspot_data WHERE system_name = 'Paesia' AND id = 329919")
row = cursor.fetchone()

if row:
    print(f"\nEntry ID 329919 (should have visited_systems):")
    for i, val in enumerate(row):
        col_name = columns[i][1]
        print(f"  [{i}] {col_name}: {val}")

conn.close()
