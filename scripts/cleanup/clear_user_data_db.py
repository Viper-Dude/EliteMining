import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'user_data.db'))
if not os.path.exists(db_path):
    print(f"Database file not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
try:
    conn.execute('DELETE FROM hotspot_data')
    conn.execute('DELETE FROM visited_systems')
    conn.commit()
    print("All data deleted from hotspot_data and visited_systems.")
except Exception as e:
    print(f"Error clearing database: {e}")
finally:
    conn.close()
