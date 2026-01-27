"""One-time script to fix 'Metalic' typo in database - CLOSE THE APP FIRST"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "data", "user_data.db")

print(f"Opening database: {db_path}")

try:
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cursor.fetchall()]
        print(f"Tables found: {tables}")
        
        # Try different possible table names
        for table_name in ['hotspot_data', 'hotspots', 'rings', 'mining_hotspots']:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE ring_type = 'Metalic'")
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"Found {count} rows with 'Metalic' in table {table_name}")
                    cursor.execute(f"UPDATE {table_name} SET ring_type = 'Metallic' WHERE ring_type = 'Metalic'")
                    conn.commit()
                    print(f"✓ Fixed {cursor.rowcount} rows in {table_name}")
                    break
            except sqlite3.OperationalError:
                continue
        else:
            print("Could not find hotspot table or no typos found")
            
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
