"""
Fresh Import of Corrected Material Data
Imports corrected data into clean database with proper LS values and density
"""

import pandas as pd
import sqlite3
from datetime import datetime
import os

def fresh_import_corrected_data():
    """Import corrected material data into clean database"""
    
    print("FRESH IMPORT OF CORRECTED MATERIAL DATA")
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
        # Step 1: Verify database is clean
        print("\n=== DATABASE STATUS CHECK ===")
        cursor = conn.execute('SELECT COUNT(*) FROM hotspot_data')
        existing_count = cursor.fetchone()[0]
        
        if existing_count > 0:
            print(f"WARNING: Database contains {existing_count} existing records!")
            response = input("Continue anyway? (y/N): ").strip().lower()
            if response not in ['y', 'yes']:
                print("Import cancelled")
                return
        else:
            print("✅ Database is clean (0 records)")
        
        # Step 2: Import corrected data
        print("\n=== IMPORTING CORRECTED DATA ===")
        excel_file = pd.ExcelFile(excel_path)
        sheet_names = excel_file.sheet_names
        
        total_imported = 0
        total_errors = 0
        scan_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
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
                    
                    # Prepare data with CORRECT FORMATS
                    system_name = str(row['System']).strip()
                    material_name = sheet_name  # Use sheet name as material
                    hotspot_count = int(row['Hotspots'])
                    ring_type = str(row['Type']).strip()
                    
                    # CORRECT LS distance handling (remove commas, convert to float)
                    ls_raw = str(row['LS']).replace(',', '').replace(' ', '')
                    ls_distance = float(ls_raw)
                    
                    # CORRECT density handling (convert to scaled integer)
                    density_raw = float(row['Density'])
                    density = int(density_raw * 1000000)  # Scale for storage
                    
                    # Insert with correct format
                    cursor = conn.execute('''
                        INSERT INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, scan_date, 
                         ring_type, ls_distance, density, data_source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (system_name, body_name, material_name, hotspot_count, scan_date,
                          ring_type, ls_distance, density, 'edtools_fresh'))
                    
                    imported_count += 1
                    
                except Exception as e:
                    error_count += 1
                    if error_count <= 5:  # Show first 5 errors only
                        print(f"    Error processing row: {e}")
                        print(f"    Row data: System={row.get('System')}, LS={row.get('LS')}, Ring={row.get('Ring')}")
                    continue
            
            print(f"  ✅ Imported: {imported_count}")
            if error_count > 0:
                print(f"  ❌ Errors: {error_count}")
            
            total_imported += imported_count
            total_errors += error_count
        
        conn.commit()
        
        # Step 3: Verify final database status
        print("\n=== IMPORT VERIFICATION ===")
        cursor = conn.execute('SELECT COUNT(*) FROM hotspot_data')
        final_count = cursor.fetchone()[0]
        
        print(f"Total records imported: {final_count:,}")
        
        # Step 4: Verify sample data with correct formats
        print("\n=== SAMPLE VERIFICATION ===")
        cursor = conn.execute('''
            SELECT system_name, body_name, material_name, ls_distance, density, ring_type
            FROM hotspot_data 
            WHERE data_source = 'edtools_fresh' 
            ORDER BY system_name 
            LIMIT 5
        ''')
        samples = cursor.fetchall()
        
        print("Sample imported records:")
        for sample in samples:
            # Convert density back to display format
            density_display = float(sample[4]) / 1000000 if sample[4] else 0
            print(f"  {sample[0]} | {sample[1]} | {sample[2]} | LS:{sample[3]} | Density:{density_display:.6f} | Type:{sample[5]}")
        
        # Step 5: Check for specific test systems
        print("\n=== SPECIFIC SYSTEM CHECK ===")
        test_systems = ['Delkar', 'LFT 65', 'Macua']
        
        for system in test_systems:
            cursor = conn.execute('''
                SELECT system_name, body_name, material_name, ls_distance, density
                FROM hotspot_data 
                WHERE system_name = ? 
                LIMIT 3
            ''', (system,))
            results = cursor.fetchall()
            
            if results:
                print(f"{system} system records:")
                for result in results:
                    density_display = float(result[4]) / 1000000 if result[4] else 0
                    print(f"  {result[1]} | {result[2]} | LS:{result[3]} | Density:{density_display:.6f}")
            else:
                print(f"{system}: No records found")
        
        print(f"\n✅ FRESH IMPORT COMPLETED!")
        print(f"Summary:")
        print(f"  - Total imported: {total_imported:,}")
        print(f"  - Total errors: {total_errors}")
        print(f"  - Database contains accurate LS values and densities!")
        print(f"  - Ring finder should now show correct distances!")

if __name__ == "__main__":
    fresh_import_corrected_data()