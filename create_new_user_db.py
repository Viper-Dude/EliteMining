#!/usr/bin/env python3
"""
Create New User Database from All Materials Hotspot Data
Builds a new user_data.db from the clean all_materials_hotspots.xlsx file
"""

import pandas as pd
import sqlite3
from pathlib import Path
import os
from datetime import datetime
import shutil

def get_system_coordinates(system_name, galaxy_db_path):
    """Get system coordinates from galaxy_systems.db"""
    try:
        with sqlite3.connect(str(galaxy_db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT x, y, z FROM systems WHERE name = ? LIMIT 1", (system_name,))
            result = cursor.fetchone()
            if result:
                return result[0], result[1], result[2]
    except Exception as e:
        print(f"Warning: Could not get coordinates for {system_name}: {e}")
    return None, None, None

def create_new_user_database():
    """Create new user_data.db from all_materials_hotspots.xlsx"""
    
    # File paths
    excel_file = Path("app/data/Hotspots/all_materials_hotspots.xlsx")
    galaxy_db = Path("app/data/galaxy_systems.db")
    new_db_path = Path("app/data/user_data_new.db")
    old_db_path = Path("app/data/user_data.db")
    backup_db_path = Path("app/data/user_data_backup.db")
    
    print("Creating new user database from clean hotspot data...")
    print(f"Source Excel file: {excel_file}")
    print(f"Galaxy database: {galaxy_db}")
    print(f"New database: {new_db_path}")
    
    # Check source files exist
    if not excel_file.exists():
        print(f"ERROR: Excel file not found: {excel_file}")
        return False
        
    if not galaxy_db.exists():
        print(f"WARNING: Galaxy database not found: {galaxy_db}")
        print("Coordinates will be set to NULL")
    
    # Remove existing new database if it exists
    if new_db_path.exists():
        new_db_path.unlink()
        print("Removed existing new database")
    
    # Create new database with proper schema
    print("\nCreating database schema...")
    with sqlite3.connect(str(new_db_path)) as conn:
        cursor = conn.cursor()
        
        # Create hotspot_data table
        cursor.execute('''
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
                density INTEGER,
                data_source TEXT,
                UNIQUE(system_name, body_name, material_name)
            )
        ''')
        
        # Create visited_systems table (empty for now)
        cursor.execute('''
            CREATE TABLE visited_systems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                system_name TEXT NOT NULL UNIQUE,
                system_address INTEGER,
                x_coord REAL,
                y_coord REAL, 
                z_coord REAL,
                first_visit_date TEXT NOT NULL,
                last_visit_date TEXT NOT NULL,
                visit_count INTEGER DEFAULT 1
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX idx_hotspot_system ON hotspot_data(system_name)')
        cursor.execute('CREATE INDEX idx_hotspot_body ON hotspot_data(body_name)')
        cursor.execute('CREATE INDEX idx_hotspot_material ON hotspot_data(material_name)')
        cursor.execute('CREATE INDEX idx_visited_system ON visited_systems(system_name)')
        
        conn.commit()
        print("Database schema created successfully")
    
    # Materials to process (excluding Summary sheet)
    materials = [
        "Alexandrite", "Benitoite", "Bromellite", "Grandidierite", 
        "LowTemperatureDiamond", "Monazite", "Musgravite", "Opal",
        "Painite", "Platinum", "Rhodplumsite", "Serendibite", "Tritium"
    ]
    
    total_records = 0
    systems_with_coords = 0
    scan_date = datetime.now().isoformat()
    
    print(f"\nProcessing {len(materials)} materials...")
    
    # Process each material sheet
    with sqlite3.connect(str(new_db_path)) as conn:
        cursor = conn.cursor()
        
        for i, material in enumerate(materials, 1):
            print(f"[{i:2d}/{len(materials)}] Processing {material}...")
            
            try:
                # Read material sheet from Excel
                df = pd.read_excel(excel_file, sheet_name=material)
                material_records = 0
                
                for _, row in df.iterrows():
                    system_name = str(row['System']).strip()
                    ring_name = str(row['Ring']).strip()
                    hotspot_count = int(row['Hotspots'])
                    ring_type = str(row['Type']).strip()
                    ls_distance = float(row['LS']) if pd.notna(row['LS']) else None
                    density = int(row['Density']) if pd.notna(row['Density']) and str(row['Density']).replace(',', '').isdigit() else None
                    
                    # Get coordinates from galaxy database
                    x_coord, y_coord, z_coord = None, None, None
                    coord_source = "unknown"
                    
                    if galaxy_db.exists():
                        x_coord, y_coord, z_coord = get_system_coordinates(system_name, galaxy_db)
                        if x_coord is not None:
                            coord_source = "galaxy_systems.db"
                            systems_with_coords += 1
                    
                    # Insert into database
                    try:
                        cursor.execute('''
                            INSERT OR REPLACE INTO hotspot_data 
                            (system_name, body_name, material_name, hotspot_count, scan_date,
                             x_coord, y_coord, z_coord, coord_source, ring_type, 
                             ls_distance, density, data_source)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            system_name, ring_name, material, hotspot_count, scan_date,
                            x_coord, y_coord, z_coord, coord_source, ring_type,
                            ls_distance, density, "EDTools.cc"
                        ))
                        material_records += 1
                        total_records += 1
                        
                    except Exception as e:
                        print(f"    ERROR inserting {system_name} - {material}: {e}")
                        continue
                
                print(f"    SUCCESS: {material_records} records added")
                
            except Exception as e:
                print(f"    ERROR processing {material}: {e}")
                continue
        
        conn.commit()
    
    # Final statistics
    print(f"\nDatabase creation complete!")
    print(f"Total records inserted: {total_records:,}")
    print(f"Systems with coordinates: {systems_with_coords:,}")
    print(f"Database file size: {new_db_path.stat().st_size / (1024*1024):.1f} MB")
    
    # Verify database integrity
    print("\nVerifying database...")
    with sqlite3.connect(str(new_db_path)) as conn:
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM hotspot_data")
        db_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT system_name) FROM hotspot_data")
        unique_systems = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT material_name) FROM hotspot_data")
        unique_materials = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE x_coord IS NOT NULL")
        coords_count = cursor.fetchone()[0]
        
        print(f"Database verification:")
        print(f"  Total hotspot records: {db_count:,}")
        print(f"  Unique systems: {unique_systems:,}")
        print(f"  Materials: {unique_materials}")
        print(f"  Records with coordinates: {coords_count:,} ({coords_count/db_count*100:.1f}%)")
    
    # Backup old database and replace with new one
    print(f"\nReplacing old database...")
    if old_db_path.exists():
        # Create backup
        shutil.copy2(old_db_path, backup_db_path)
        print(f"Backed up old database to: {backup_db_path}")
        
        # Replace with new database
        shutil.move(new_db_path, old_db_path)
        print(f"New database installed as: {old_db_path}")
    else:
        # Just rename new database
        shutil.move(new_db_path, old_db_path)
        print(f"New database created as: {old_db_path}")
    
    print(f"\nSUCCESS: New user_data.db created with clean hotspot data!")
    return True

def main():
    """Main function"""
    print("=" * 60)
    print("USER DATABASE CREATION FROM CLEAN HOTSPOT DATA")
    print("=" * 60)
    
    try:
        success = create_new_user_database()
        if success:
            print("\nALL COMPLETE! New user_data.db is ready for use.")
        else:
            print("\nFAILED: Could not create new database")
    except Exception as e:
        print(f"\nERROR: {e}")

if __name__ == "__main__":
    main()