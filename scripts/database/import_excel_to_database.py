#!/usr/bin/env python3
"""
Step 2: Import Updated Excel into Database
Imports the merged all_materials_hotspots.xlsx into user_data.db
"""

import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime
import shutil
import re

def backup_database():
    """Create backup of existing database"""
    db_path = Path("app/data/user_data.db")  # Correct path
    backup_path = Path(f"app/data/user_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
    
    if db_path.exists():
        print(f"Creating database backup: {backup_path}")
        shutil.copy2(db_path, backup_path)
        return True
    else:
        print("No existing database found")
        return False

def load_master_excel():
    """Load the updated master Excel file"""
    master_file = Path("app/data/Hotspots/all_materials_hotspots.xlsx")
    
    if not master_file.exists():
        print("ERROR: Master Excel file not found. Run merge script first.")
        return None
    
    print(f"Loading master Excel: {master_file}")
    df = pd.read_excel(master_file)
    print(f"  Records to import: {len(df)}")
    
    # Validate required columns
    required_cols = ['System', 'Ring', 'Hotspots', 'Type', 'LS', 'Density', 'Material']
    missing_cols = [col for col in required_cols if col not in df.columns]
    
    if missing_cols:
        print(f"ERROR: Missing columns in Excel: {missing_cols}")
        return None
    
    return df

def prepare_database_data(df):
    """Prepare data for database insertion with comprehensive cleaning"""
    print("Preparing data for database with cleaning...")
    initial_count = len(df)
    
    # Create a copy to avoid modifying original
    df_db = df.copy()
    
    # 1. Additional data cleaning before database import
    print("  Applying final data cleaning...")
    
    # Clean system names again (in case Excel had issues)
    df_db['System'] = df_db['System'].astype(str).str.strip()
    df_db['System'] = df_db['System'].str.replace(r'\[.*?\]', '', regex=True)
    df_db['System'] = df_db['System'].str.replace('*', '')
    df_db['System'] = df_db['System'].str.replace(r'\s+', ' ', regex=True)
    
    # Clean ring names  
    df_db['Ring'] = df_db['Ring'].astype(str).str.strip()
    df_db['Ring'] = df_db['Ring'].str.replace(r'\s+', ' ', regex=True)
    
    # Remove any remaining garbage entries
    df_db = df_db[df_db['System'].str.len() > 2]
    df_db = df_db[df_db['Ring'].str.len() > 0]
    df_db = df_db[df_db['System'].str.match(r'^[A-Za-z]', na=False)]
    
    # Remove invalid material names
    valid_materials = {
        'Alexandrite', 'Painite', 'Platinum', 'LowTemperatureDiamond', 'Tritium',
        'Osmium', 'Rhodplumsite', 'Serendibite', 'Monazite', 'Musgravite', 
        'Bixbite', 'Jadeite', 'Opal', 'Bromellite'
    }
    df_db = df_db[df_db['Material'].isin(valid_materials)]
    
    # 2. Rename columns to match database schema
    column_mapping = {
        'System': 'system_name',
        'Ring': 'body_name',  # Map Ring to body_name in database
        'Material': 'material_name',
        'Hotspots': 'hotspot_count',
        'Type': 'ring_type',
        'LS': 'ls_distance',
        'Density': 'density'
    }
    
    df_db = df_db.rename(columns=column_mapping)
    
    # 3. Clean and validate data types
    df_db['system_name'] = df_db['system_name'].str.strip()
    df_db['body_name'] = df_db['body_name'].str.strip()  # Fixed column name
    df_db['material_name'] = df_db['material_name'].str.strip()
    
    # Handle N/A values for numeric columns
    df_db['ls_distance'] = pd.to_numeric(df_db['ls_distance'], errors='coerce')
    df_db['density'] = pd.to_numeric(df_db['density'], errors='coerce')
    df_db['hotspot_count'] = pd.to_numeric(df_db['hotspot_count'], errors='coerce')
    
    # Remove records with invalid hotspot counts
    df_db = df_db[df_db['hotspot_count'] > 0]
    df_db = df_db[df_db['hotspot_count'].notna()]
    
    # Fill NaN with appropriate defaults for optional fields
    df_db['ls_distance'] = df_db['ls_distance'].fillna(0)
    df_db['density'] = df_db['density'].fillna(0)
    
    # Add required database columns with defaults
    df_db['scan_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    df_db['system_address'] = 0  # Default value
    df_db['body_id'] = 0  # Default value  
    df_db['x_coord'] = 0.0  # Default value (will be populated later if coordinates found)
    df_db['y_coord'] = 0.0  # Default value (will be populated later if coordinates found)
    df_db['z_coord'] = 0.0  # Default value (will be populated later if coordinates found)
    df_db['coord_source'] = 'import'  # Default value
    df_db['data_source'] = 'excel_import'  # Default value
    
    # Standardize ring types
    df_db['ring_type'] = df_db['ring_type'].fillna('Unknown')
    ring_type_mapping = {
        'icy': 'Icy', 'ICY': 'Icy', 'ice': 'Icy',
        'metallic': 'Metallic', 'METALLIC': 'Metallic', 'metal': 'Metallic',  
        'rocky': 'Rocky', 'ROCKY': 'Rocky', 'rock': 'Rocky'
    }
    df_db['ring_type'] = df_db['ring_type'].replace(ring_type_mapping)
    
    # Ensure all required columns are present in correct order for database
    required_db_columns = [
        'system_name', 'body_name', 'material_name', 'hotspot_count', 'scan_date',
        'system_address', 'body_id', 'x_coord', 'y_coord', 'z_coord', 'coord_source',
        'ring_type', 'ls_distance', 'density', 'data_source'
    ]
    
    # Reorder DataFrame columns to match database schema exactly
    df_db = df_db[required_db_columns]
    
    # Try to populate coordinates from galaxy database
    try:
        print("  Attempting to populate coordinates from galaxy database...")
        galaxy_db_path = Path("app/data/galaxy_systems.db")
        
        if galaxy_db_path.exists():
            with sqlite3.connect(str(galaxy_db_path)) as galaxy_conn:
                galaxy_cursor = galaxy_conn.cursor()
                
                # Get unique systems for coordinate lookup
                unique_systems = df_db['system_name'].unique()
                coord_updates = 0
                
                for system in unique_systems:
                    galaxy_cursor.execute("SELECT x, y, z FROM systems WHERE name = ?", (system,))
                    coords = galaxy_cursor.fetchone()
                    
                    if coords:
                        # Update coordinates for all records with this system
                        mask = df_db['system_name'] == system
                        df_db.loc[mask, 'x_coord'] = coords[0]
                        df_db.loc[mask, 'y_coord'] = coords[1] 
                        df_db.loc[mask, 'z_coord'] = coords[2]
                        df_db.loc[mask, 'coord_source'] = 'galaxy_db'
                        coord_updates += len(df_db[mask])
                
                print(f"    Updated coordinates for {coord_updates} records from galaxy database")
        else:
            print("    Galaxy database not found, using default coordinates")
            
    except Exception as e:
        print(f"    Warning: Could not populate coordinates: {e}")
    
    
    # 4. Final deduplication
    df_db = df_db.drop_duplicates(subset=['system_name', 'body_name', 'material_name'], keep='first')
    
    final_count = len(df_db)
    removed_count = initial_count - final_count
    
    if removed_count > 0:
        print(f"    Removed {removed_count} invalid/duplicate records during cleaning")
    print(f"    Prepared {final_count} clean records for database")
    
    return df_db

def import_to_database(df_db):
    """Import data to SQLite database"""
    db_path = Path("app/data/user_data.db")
    print(f"Importing to database: {db_path}")
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            # Check if table exists
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hotspot_data'")
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                print("Creating hotspot_data table...")
                cursor.execute("""
                    CREATE TABLE hotspot_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        system_name TEXT NOT NULL,
                        body_name TEXT NOT NULL,
                        material_name TEXT NOT NULL,
                        hotspot_count INTEGER NOT NULL,
                        scan_date TEXT NOT NULL,
                        system_address INTEGER DEFAULT 0,
                        body_id INTEGER DEFAULT 0,
                        x_coord REAL DEFAULT 0.0,
                        y_coord REAL DEFAULT 0.0,
                        z_coord REAL DEFAULT 0.0,
                        coord_source TEXT DEFAULT 'import',
                        ring_type TEXT DEFAULT 'Unknown',
                        ls_distance REAL DEFAULT 0,
                        density REAL DEFAULT 0,
                        data_source TEXT DEFAULT 'excel_import',
                        UNIQUE(system_name, body_name, material_name)
                    )
                """)
                conn.commit()
            
            # Get current record count
            cursor.execute("SELECT COUNT(*) FROM hotspot_data")
            current_count = cursor.fetchone()[0]
            print(f"  Current database records: {current_count}")
            
            # Clear existing data for complete refresh
            print("  Clearing existing data for fresh import...")
            cursor.execute("DELETE FROM hotspot_data")
            conn.commit()
            
            # Insert new data
            print("  Inserting new data...")
            df_db.to_sql('hotspot_data', conn, if_exists='append', index=False)
            
            # Get final count
            cursor.execute("SELECT COUNT(*) FROM hotspot_data")
            final_count = cursor.fetchone()[0]
            print(f"  Final database records: {final_count}")
            
            # Create indexes for performance
            print("  Creating indexes...")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_material ON hotspot_data(system_name, material_name)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_material ON hotspot_data(material_name)")
            conn.commit()
            
            return True
            
    except Exception as e:
        print(f"ERROR importing to database: {e}")
        return False

def verify_import():
    """Verify the database import was successful"""
    db_path = Path("app/data/user_data.db")
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            # Total records
            cursor.execute("SELECT COUNT(*) FROM hotspot_data")
            total_count = cursor.fetchone()[0]
            
            # Records by material
            cursor.execute("""
                SELECT material_name, COUNT(*) as record_count, 
                       COUNT(DISTINCT system_name) as system_count,
                       SUM(hotspot_count) as total_hotspots
                FROM hotspot_data 
                GROUP BY material_name 
                ORDER BY material_name
            """)
            material_stats = cursor.fetchall()
            
            print(f"\nDatabase import verification:")
            print(f"  Total records: {total_count}")
            print(f"  Records by material:")
            
            for material, record_count, system_count, total_hotspots in material_stats:
                print(f"    {material:20} {record_count:4d} records, {system_count:4d} systems, {total_hotspots:5d} hotspots")
            
            # Test specific query (e.g., Paesia Alexandrite)
            cursor.execute("""
                SELECT system_name, body_name, hotspot_count, ls_distance
                FROM hotspot_data 
                WHERE system_name = 'Paesia' AND material_name = 'Alexandrite'
            """)
            paesia_results = cursor.fetchall()
            
            print(f"\nVerification: Paesia Alexandrite data:")
            for system, ring, hotspots, ls in paesia_results:
                print(f"    {system} - {ring} - {hotspots} hotspots - {ls} LS")
                
            return len(paesia_results) > 0
            
    except Exception as e:
        print(f"ERROR verifying import: {e}")
        return False

def main():
    """Main database import process"""
    print("="*60)
    print("STEP 2: IMPORT EXCEL TO DATABASE")
    print("="*60)
    
    # Create backup
    backup_created = backup_database()
    
    # Load Excel data
    df = load_master_excel()
    if df is None:
        return
    
    # Prepare for database
    df_db = prepare_database_data(df)
    
    # Import to database
    success = import_to_database(df_db)
    
    if success:
        # Verify import
        verification_success = verify_import()
        
        print("="*60)
        if verification_success:
            print("DATABASE IMPORT COMPLETE & VERIFIED!")
            print("✓ Paesia Alexandrite data found in database")
        else:
            print("DATABASE IMPORT COMPLETE (verification had issues)")
        print("="*60)
        print("Ring finder should now show complete data including Paesia!")
    else:
        print("="*60)
        print("DATABASE IMPORT FAILED!")
        print("="*60)
        if backup_created:
            print("Database backup available for restoration if needed")

if __name__ == "__main__":
    main()