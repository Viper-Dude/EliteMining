import sqlite3

db_path = r"app\data\UserDb for install\user_data.db"
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Get all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in c.fetchall()]
print("Tables in installer database:", tables)

# Check each table for hotspot-related data
for table in tables:
    print(f"\n=== Table: {table} ===")
    c.execute(f"PRAGMA table_info({table})")
    cols = [col[1] for col in c.fetchall()]
    print(f"Columns: {cols}")
    
    # Check if this has hotspot data for Antliae
    if any(keyword in ''.join(cols).lower() for keyword in ['system', 'body', 'ring', 'mineral', 'hotspot']):
        try:
            # Try to find Antliae data
            query = f"SELECT * FROM {table} WHERE "
            conditions = []
            for col in cols:
                if 'name' in col.lower() or 'system' in col.lower():
                    conditions.append(f"{col} LIKE '%Antliae%PX-U%'")
            
            if conditions:
                query += " OR ".join(conditions) + " LIMIT 5"
                c.execute(query)
                rows = c.fetchall()
                if rows:
                    print(f"Found {len(rows)} Antliae PX-U rows:")
                    for row in rows:
                        print(f"  {row}")
        except Exception as e:
            print(f"  Error querying: {e}")

conn.close()
