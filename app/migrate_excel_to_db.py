
import pandas as pd
import sqlite3
import os

# Paths
data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
excel_path = os.path.join(data_dir, 'All_Materials_Combined_ready_matched_cleaned_density_locale.xlsx')
db_path = os.path.join(data_dir, 'user_data.db')

# Ensure data directory exists
os.makedirs(data_dir, exist_ok=True)

# Hotspot data columns (from user_database.py)
hotspot_columns = [
    'system_name', 'body_name', 'material_name', 'hotspot_count', 'scan_date',
    'system_address', 'body_id', 'x_coord', 'y_coord', 'z_coord', 'coord_source',
    'ls_distance', 'ring_type', 'density'
]

# Step 1: Read Excel
xls = pd.ExcelFile(excel_path)
all_rows = []

for sheet in xls.sheet_names:
    df = pd.read_excel(xls, sheet_name=sheet)
    # Check required columns
    missing = [col for col in ['system_name', 'body_name', 'material_name', 'hotspot_count', 'scan_date'] if col not in df.columns]
    if missing:
        print(f"Sheet '{sheet}' missing columns: {missing}. Stopping.")
        exit(1)
    # Fill missing columns for DB
    for col in hotspot_columns:
        if col not in df.columns:
            df[col] = ''
    # Convert numeric columns to proper types
    numeric_cols = ['hotspot_count', 'system_address', 'body_id', 'x_coord', 'y_coord', 'z_coord', 'ls_distance', 'density']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    # Only keep relevant columns
    df = df[hotspot_columns]
    all_rows.extend(df.to_dict('records'))


# Step 2: Connect to existing DB and ensure schema matches
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS hotspot_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        system_name TEXT NOT NULL,
        body_name TEXT NOT NULL,
        material_name TEXT NOT NULL,
        hotspot_count INTEGER NOT NULL,
        scan_date TEXT NOT NULL,
        system_address INTEGER,
        body_id INTEGER,
        x_coord REAL,
        y_coord REAL,
        z_coord REAL,
        coord_source TEXT,
        ls_distance REAL,
        ring_type TEXT,
        density REAL,
        UNIQUE(system_name, body_name, material_name)
    )
''')

# Step 3: Insert data
for row in all_rows:
    try:
        conn.execute('''
            INSERT OR REPLACE INTO hotspot_data 
            (system_name, body_name, material_name, hotspot_count, scan_date, system_address, body_id, x_coord, y_coord, z_coord, coord_source, ls_distance, ring_type, density)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', [row[c] for c in hotspot_columns])
    except Exception as e:
        print(f"Error inserting row: {row}\n{e}")
        conn.close()
        exit(1)
conn.commit()
conn.close()
print(f"Migration complete. Data imported into: {db_path}")
