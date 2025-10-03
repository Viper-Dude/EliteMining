"""
Create Clean User Database for Installer
Builds a fresh user_data.db from All_Materials_Combined_Corrected.xlsx
This will be the clean database included with the installer
"""

import pandas as pd
import sqlite3
import os
import shutil
from pathlib import Path
from datetime import datetime

def create_clean_user_database():
    """Create a clean user database from the Excel file for installer use"""
    
    print("CREATING CLEAN USER DATABASE FOR INSTALLER")
    print("=" * 60)
    
    # File paths
    excel_file = "app/data/Hotspots/All_Materials_Combined_Corrected.xlsx"
    clean_db_path = "app/data/user_data_clean.db"
    backup_current = "app/data/user_data_backup_before_clean.db"
    
    # Backup current database
    if os.path.exists("app/data/user_data.db"):
        print("Creating backup of current database...")
        shutil.copy2("app/data/user_data.db", backup_current)
        print(f"✅ Backup saved: {backup_current}")
    
    # Remove existing clean database if it exists
    if os.path.exists(clean_db_path):
        os.remove(clean_db_path)
        print(f"Removed existing clean database")
    
    # Create database structure
    print("Creating database structure...")
    with sqlite3.connect(clean_db_path) as conn:
        # Create hotspot_data table with all required columns
        conn.execute('''
            CREATE TABLE hotspot_data (
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
                ring_type TEXT,
                ls_distance REAL,
                density REAL,
                data_source TEXT,
                UNIQUE(system_name, body_name, material_name)
            )
        ''')
        
        # Create visited_systems table (empty for clean install)
        conn.execute('''
            CREATE TABLE visited_systems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_name TEXT UNIQUE NOT NULL,
                visit_date TEXT NOT NULL,
                system_address INTEGER,
                x_coord REAL,
                y_coord REAL,
                z_coord REAL
            )
        ''')
        
        # Create indexes for performance
        conn.execute('CREATE INDEX idx_hotspot_system_material ON hotspot_data(system_name, material_name)')
        conn.execute('CREATE INDEX idx_hotspot_material ON hotspot_data(material_name)')
        conn.execute('CREATE INDEX idx_visited_system ON visited_systems(system_name)')
        
        conn.commit()
        print("✅ Database structure created")
    
    # Load and process Excel data
    print("Loading Excel data...")
    excel_file_obj = pd.ExcelFile(excel_file)
    total_records = 0
    
    with sqlite3.connect(clean_db_path) as conn:
        for sheet_name in excel_file_obj.sheet_names:
            print(f"  Processing sheet: {sheet_name}")
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Add material column
            df['Material'] = sheet_name
            
            # Prepare data for database
            df_clean = df.copy()
            
            # Clean system names
            df_clean['System'] = df_clean['System'].astype(str).str.strip()
            df_clean['System'] = df_clean['System'].str.replace(r'\[.*?\]', '', regex=True)
            df_clean['System'] = df_clean['System'].str.replace('*', '')
            df_clean['System'] = df_clean['System'].str.replace(r'\s+', ' ', regex=True)
            
            # Clean ring names
            df_clean['Ring'] = df_clean['Ring'].astype(str).str.strip()
            
            # Handle numeric fields
            df_clean['LS'] = pd.to_numeric(df_clean['LS'], errors='coerce')
            df_clean['Density'] = pd.to_numeric(df_clean['Density'], errors='coerce')
            df_clean['Hotspots'] = pd.to_numeric(df_clean['Hotspots'], errors='coerce')
            
            # Remove invalid records
            df_clean = df_clean.dropna(subset=['System', 'Ring', 'Hotspots'])
            df_clean = df_clean[df_clean['Hotspots'] > 0]
            
            # Standardize ring types
            type_mapping = {
                'icy': 'Icy', 'ICY': 'Icy', 'ice': 'Icy',
                'metallic': 'Metallic', 'METALLIC': 'Metallic', 'metal': 'Metallic',
                'rocky': 'Rocky', 'ROCKY': 'Rocky', 'rock': 'Rocky'
            }
            df_clean['Type'] = df_clean['Type'].fillna('Unknown')
            df_clean['Type'] = df_clean['Type'].replace(type_mapping)
            
            # Fill missing values
            df_clean['LS'] = df_clean['LS'].fillna(0)
            df_clean['Density'] = df_clean['Density'].fillna(0)
            
            # Insert into database
            for _, row in df_clean.iterrows():
                try:
                    conn.execute('''
                        INSERT OR REPLACE INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, 
                         scan_date, system_address, body_id, x_coord, y_coord, z_coord, coord_source,
                         ring_type, ls_distance, density, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        row['System'], row['Ring'], row['Material'], int(row['Hotspots']),
                        datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 0, 0, 0.0, 0.0, 0.0, 'excel_import',
                        row['Type'], float(row['LS']) if pd.notna(row['LS']) else 0.0,
                        float(row['Density']) if pd.notna(row['Density']) else 0.0, 'excel_import'
                    ))
                    total_records += 1
                except Exception as e:
                    print(f"    Error inserting record: {e}")
                    continue
            
            conn.commit()
            print(f"    Inserted: {len(df_clean)} records")
    
    # Final verification
    print("\nVerifying clean database...")
    with sqlite3.connect(clean_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM hotspot_data")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT material_name) FROM hotspot_data")
        material_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT system_name) FROM hotspot_data")
        system_count = cursor.fetchone()[0]
        
        print(f"✅ Total hotspot records: {total_count:,}")
        print(f"✅ Unique materials: {material_count}")
        print(f"✅ Unique systems: {system_count:,}")
    
    # Get file size
    file_size = os.path.getsize(clean_db_path) / (1024 * 1024)  # MB
    print(f"✅ Database size: {file_size:.1f} MB")
    
    print(f"\n🎉 CLEAN DATABASE CREATED SUCCESSFULLY!")
    print(f"📁 Location: {clean_db_path}")
    print(f"📦 Ready for installer packaging")
    print(f"🔄 Current database backed up to: {backup_current}")
    
    return clean_db_path

def main():
    """Main execution"""
    print("Creating clean user database for installer...")
    
    if not os.path.exists("app/data/Hotspots/All_Materials_Combined_Corrected.xlsx"):
        print("❌ ERROR: All_Materials_Combined_Corrected.xlsx not found!")
        return
    
    try:
        clean_db_path = create_clean_user_database()
        print(f"\n✅ SUCCESS: Clean database ready at {clean_db_path}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    main()