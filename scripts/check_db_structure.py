import sqlite3

db_path = 'app/data/galaxy_systems.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== DATABASE STRUCTURE ===\n")

# Get list of all tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()

print(f"Tables in database: {[t[0] for t in tables]}\n")

# Show structure of each table
for table in tables:
    table_name = table[0]
    print("="*80)
    print(f"TABLE: {table_name}")
    print("="*80)
    
    # Get column info
    c.execute(f"PRAGMA table_info({table_name})")
    columns = c.fetchall()
    
    print("\nColumns:")
    for col in columns:
        print(f"  {col[1]} ({col[2]}) - Primary Key: {col[5]}")
    
    # Get row count
    c.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = c.fetchone()[0]
    print(f"\nRow count: {count}")
    
    # Show first 3 rows as sample
    if count > 0:
        c.execute(f"SELECT * FROM {table_name} LIMIT 3")
        samples = c.fetchall()
        print("\nSample data (first 3 rows):")
        for i, row in enumerate(samples, 1):
            print(f"\nRow {i}:")
            for col, val in zip([c[1] for c in columns], row):
                # Truncate long values
                val_str = str(val)
                if len(val_str) > 100:
                    val_str = val_str[:100] + "..."
                print(f"  {col}: {val_str}")
    
    print("\n")

conn.close()
