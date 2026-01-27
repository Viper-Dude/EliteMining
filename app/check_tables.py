import sqlite3

conn = sqlite3.connect('app/user_data.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

# Check for hotspot-related tables
for table in tables:
    if 'hotspot' in table.lower() or 'ring' in table.lower():
        print(f"\nTable: {table}")
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        for col in columns:
            print(f"  - {col[1]} ({col[2]})")
