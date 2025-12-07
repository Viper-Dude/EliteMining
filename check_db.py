import sqlite3

# Check default install database
db_path = r"D:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\UserDb for install\user_data.db"
conn = sqlite3.connect(db_path)

tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables in default install database:")
for t in tables:
    print(f"  - {t[0]}")

# Check if visited_systems exists and its structure
if ('visited_systems',) in tables:
    print("\nvisited_systems table exists!")
    columns = conn.execute("PRAGMA table_info(visited_systems)").fetchall()
    print("Columns:")
    for col in columns:
        print(f"  - {col[1]} ({col[2]})")
    
    count = conn.execute("SELECT COUNT(*) FROM visited_systems").fetchone()[0]
    print(f"\nRows: {count}")
else:
    print("\nvisited_systems table does NOT exist")

# Check migrations table
if ('migrations',) in tables:
    print("\nmigrations table exists!")
    migrations = conn.execute("SELECT * FROM migrations").fetchall()
    print(f"Applied migrations: {migrations}")
else:
    print("\nmigrations table does NOT exist")

conn.close()
