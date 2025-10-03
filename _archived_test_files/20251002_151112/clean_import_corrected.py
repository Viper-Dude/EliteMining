"""
Clean Import of Corrected Material Data
Removes old EDTools data and imports corrected data with proper LS values and density
"""

import pandas as pd
import sqlite3
from datetime import datetime
import os

def clean_import_corrected_data():
    """Remove old EDTools data and import corrected material data"""
    
    print("CLEAN IMPORT OF CORRECTED MATERIAL DATA")
    print("=======================================")
    
    # Database and Excel file paths
    db_path = 'app/data/user_data.db'
    excel_path = 'app/data/Hotspots/All_Materials_Combined_Corrected.xlsx'
    
    if not os.path.exists(excel_path):
        print(f"ERROR: Corrected Excel file not found: {excel_path}")
        return
    
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        return
    
    print(f"Database: {db_path}")
    print(f"Excel source: {excel_path}")
    
    with sqlite3.connect(db_path) as conn:
        # Step 1: Show current database status
        print("\n=== CURRENT DATABASE STATUS ===")
        cursor = conn.execute('SELECT COUNT(*) FROM hotspot_data')
        total_before = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM hotspot_data WHERE data_source = 'edtools_import'")
        old_edtools_count = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM hotspot_data WHERE data_source != 'edtools_import' OR data_source IS NULL")
        other_sources_count = cursor.fetchone()[0]
        
        print(f"Total records: {total_before:,}")
        print(f"Old EDTools records (to be removed): {old_edtools_count:,}")
        print(f"Other source records (to be kept): {other_sources_count:,}")
        
        # Step 2: Remove old EDTools data
        print("\n=== REMOVING OLD EDTOOLS DATA ===")
        cursor = conn.execute("DELETE FROM hotspot_data WHERE data_source = 'edtools_import'")
        deleted_count = cursor.rowcount
        print(f"Deleted old EDTools records: {deleted_count:,}")
        
        # Step 3: Import corrected data
        print("\n=== IMPORTING CORRECTED DATA ===")
        excel_file = pd.ExcelFile(excel_path)
        sheet_names = excel_file.sheet_names
        
        total_imported = 0
        total_errors = 0
        
        for sheet_name in sheet_names:
            print(f"\nProcessing {sheet_name}...")
            
            # Read sheet data
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            print(f"  Records to import: {len(df)}")
            
            imported_count = 0
            error_count = 0
            
            for _, row in df.iterrows():
                try:
                    # Extract body name from Ring column (e.g., '2 A Ring' -> '2 A')
                    ring_text = str(row['Ring'])
                    if 'Ring' in ring_text:
                        body_name = ring_text.replace('Ring', '').strip()
                    else:
                        body_name = ring_text
                    
                    # Prepare data for database with CORRECTED values
                    system_name = str(row['System'])
                    material_name = sheet_name  # Use sheet name as material
                    hotspot_count = int(row['Hotspots'])
                    scan_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    ring_type = str(row['Type'])
                    ls_distance = float(row['LS'].replace(',', ''))  # Remove commas from LS values
                    density = int(float(row['Density']) * 1000000)  # Convert to int with scaling
                    
                    # Insert corrected data
                    cursor = conn.execute('''
                        INSERT OR IGNORE INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, scan_date, 
                         ring_type, ls_distance, density, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (system_name, body_name, material_name, hotspot_count, scan_date,
                          ring_type, ls_distance, density, 'edtools_corrected'))
                    
                    if cursor.rowcount > 0:
                        imported_count += 1
                    
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:  # Show first 5 errors only
                        print(f"    Error processing row: {e}")
                    continue
            
            print(f"  ✅ Imported: {imported_count}")
            if error_count > 0:
                print(f"  ❌ Errors: {error_count}")
            
            total_imported += imported_count
            total_errors += error_count
        
        conn.commit()
        
        # Step 4: Verify final database status
        print("\n=== FINAL DATABASE STATUS ===")
        cursor = conn.execute('SELECT COUNT(*) FROM hotspot_data')
        total_after = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM hotspot_data WHERE data_source = 'edtools_corrected'")
        new_edtools_count = cursor.fetchone()[0]
        
        print(f"Total records after import: {total_after:,}")
        print(f"New corrected EDTools records: {new_edtools_count:,}")
        print(f"Net change: {total_after - total_before:+,}")
        
        # Step 5: Verify sample corrected data
        print("\n=== SAMPLE CORRECTED DATA ===")
        cursor = conn.execute('''
            SELECT system_name, body_name, material_name, ls_distance, density, data_source
            FROM hotspot_data 
            WHERE data_source = 'edtools_corrected' 
            ORDER BY system_name 
            LIMIT 5
        ''')
        samples = cursor.fetchall()
        
        print("Sample corrected records:")
        for sample in samples:
            density_display = float(sample[4]) / 1000000 if sample[4] else 0
            print(f"  {sample[0]} | {sample[1]} | {sample[2]} | LS:{sample[3]} | Density:{density_display:.6f}")
        
        print(f"\n✅ CLEAN IMPORT COMPLETED!")
        print(f"Summary:")
        print(f"  - Removed old EDTools records: {deleted_count:,}")
        print(f"  - Imported corrected records: {total_imported:,}")
        print(f"  - Total errors: {total_errors}")
        print(f"  - Database now has correct LS values and densities!")

if __name__ == "__main__":
    clean_import_corrected_data()