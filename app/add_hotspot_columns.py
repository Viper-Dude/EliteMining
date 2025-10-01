# Overwrite with a fully correct version
import os
import sqlite3
import time

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'user_data.db'))
max_retries = 5

for attempt in range(max_retries):
    try:
        print(f"Attempt {attempt+1} to open database at {db_path} ...")
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        # Add columns if they do not exist
        for col, col_type in [
            ('ls_distance', 'REAL'),
            ('ring_type', 'TEXT'),
            ('density', 'REAL')
        ]:
            try:
                cursor.execute(f'ALTER TABLE hotspot_data ADD COLUMN {col} {col_type}')
                print(f"Added column: {col}")
            except sqlite3.OperationalError as e:
                print(f"Column already exists or error for: {col} ({e})")
        conn.commit()
        conn.close()
        print("Schema update complete.")
        break
    except Exception as e:
        print(f"Error opening or updating database: {e}")
        time.sleep(2)
else:
    print("Failed to update schema after multiple attempts.")
db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'user_data.db'))

# Corrected script with all imports and robust error handling
import os
import sqlite3
import time

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'user_data.db'))
max_retries = 5

for attempt in range(max_retries):
    try:
        print(f"Attempt {attempt+1} to open database at {db_path} ...")
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        # Add columns if they do not exist
        for col, col_type in [
            ('ls_distance', 'REAL'),
            ('ring_type', 'TEXT'),
            ('density', 'REAL')
        ]:
            try:
                cursor.execute(f'ALTER TABLE hotspot_data ADD COLUMN {col} {col_type}')
                print(f"Added column: {col}")
            except sqlite3.OperationalError as e:
                print(f"Column already exists or error for: {col} ({e})")
        conn.commit()
        conn.close()
        print("Schema update complete.")
        break
    except Exception as e:
        print(f"Error opening or updating database: {e}")
        time.sleep(2)
else:
    print("Failed to update schema after multiple attempts.")
