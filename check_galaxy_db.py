import sqlite3

conn = sqlite3.connect('app/data/galaxy_systems.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print(f'Tables in galaxy_systems.db: {tables}')

for table_name in tables:
    cursor.execute(f"SELECT COUNT(*) FROM {table_name[0]}")
    count = cursor.fetchone()[0]
    print(f'  {table_name[0]}: {count:,} rows')
    
    cursor.execute(f"PRAGMA table_info({table_name[0]})")
    columns = cursor.fetchall()
    print(f'  Columns: {[col[1] for col in columns]}')

conn.close()
