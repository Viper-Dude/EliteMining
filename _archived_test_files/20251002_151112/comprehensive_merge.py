#!/usr/bin/env python3
"""
Comprehensive Gap Data Merge into Master Excel
Combines all gap files from multiple directories and cleans the data
"""

import pandas as pd
from pathlib import Path
import re
from datetime import datetime

def load_existing_master():
    """Load the existing all_materials_hotspots.xlsx master file"""
    master_file = Path("app/data/Hotspots/all_materials_hotspots.xlsx")
    
    if master_file.exists():
        print(f"Loading existing master file: {master_file}")
        df_master = pd.read_excel(master_file)
        print(f"  Current master records: {len(df_master)}")
        
        # Ensure Material column exists
        if 'Material' not in df_master.columns:
            print("  WARNING: Master file missing Material column - will add during merge")
            
        return df_master
    else:
        print("No existing master file found - will create new one")
        return pd.DataFrame(columns=['System', 'Ring', 'Hotspots', 'Type', 'LS', 'Density', 'Material'])

def load_all_gap_files():
    """Load gap files from all directories"""
    gap_data = {}
    total_gap_records = 0
    
    # Directory 1: all_materials_gaps (all extraction files)
    gap_dir1 = Path("app/data/Hotspots/all_materials_gaps")
    if gap_dir1.exists():
        gap_files1 = list(gap_dir1.glob("*_complete_gaps.xlsx")) + list(gap_dir1.glob("*_corrected_gaps.xlsx"))
        print(f"Found {len(gap_files1)} files in all_materials_gaps/")
        
        for gap_file in gap_files1:
            # Handle both naming patterns
            material = gap_file.stem.replace('_complete_gaps', '').replace('_corrected_gaps', '')
            try:
                df_gap = pd.read_excel(gap_file)
                df_gap['Material'] = material
                gap_data[material] = df_gap
                total_gap_records += len(df_gap)
                print(f"  {material:20} {len(df_gap):4d} records")
            except Exception as e:
                print(f"  ERROR loading {gap_file}: {e}")
    
    # Directory 2: corrected_gaps (corrected extraction)
    gap_dir2 = Path("app/data/Hotspots/corrected_gaps") 
    if gap_dir2.exists():
        gap_files2 = list(gap_dir2.glob("*_corrected_gaps.xlsx"))
        print(f"Found {len(gap_files2)} files in corrected_gaps/")
        
        for gap_file in gap_files2:
            material = gap_file.stem.replace('_corrected_gaps', '')
            try:
                df_gap = pd.read_excel(gap_file)
                df_gap['Material'] = material
                # If material already exists, combine the data
                if material in gap_data:
                    print(f"  {material:20} MERGING {len(df_gap):4d} + {len(gap_data[material]):4d} records")
                    gap_data[material] = pd.concat([gap_data[material], df_gap], ignore_index=True)
                else:
                    gap_data[material] = df_gap
                    print(f"  {material:20} {len(df_gap):4d} records")
                total_gap_records += len(df_gap)
            except Exception as e:
                print(f"  ERROR loading {gap_file}: {e}")
    
    print(f"Total gap records loaded: {total_gap_records}")
    return gap_data

def clean_data_comprehensive(df):
    """Apply comprehensive data cleaning - remove garbage text and invalid entries"""
    print(f"  Applying comprehensive data cleaning...")
    initial_count = len(df)
    
    # 1. Clean system names
    df['System'] = df['System'].astype(str).str.strip()
    df['System'] = df['System'].str.replace(r'\[.*?\]', '', regex=True)  # Remove clipboard links
    df['System'] = df['System'].str.replace('*', '')  # Remove asterisks
    df['System'] = df['System'].str.replace(r'\s+', ' ', regex=True)  # Normalize spaces
    
    # 2. Clean ring names
    df['Ring'] = df['Ring'].astype(str).str.strip()
    df['Ring'] = df['Ring'].str.replace(r'\s+', ' ', regex=True)  # Normalize spaces
    
    # 3. Remove garbage/invalid entries
    df = df[df['System'].str.len() > 2]
    df = df[df['Ring'].str.len() > 0]
    df = df[df['System'].str.match(r'^[A-Za-z]', na=False)]
    
    # 4. Remove garbage patterns
    garbage_patterns = [
        r'^[0-9]+$',  # Only numbers
        r'^[^a-zA-Z0-9\s\-]+',  # Starts with special characters
        r'^\s*$',  # Only whitespace
        r'^(N/A|NA|null|undefined|error)$',  # Common error values
        r'^\d+\.\d+$',  # Decimal numbers only
    ]
    
    for pattern in garbage_patterns:
        df = df[~df['System'].str.match(pattern, case=False, na=False)]
    
    # 5. Clean material names (only if Material column exists)
    if 'Material' in df.columns:
        df['Material'] = df['Material'].astype(str).str.strip()
    
    # 6. Validate numeric fields
    df['Hotspots'] = pd.to_numeric(df['Hotspots'], errors='coerce')
    df = df[df['Hotspots'] > 0]
    
    # 7. Clean LS distances
    df['LS'] = df['LS'].replace(['N/A', 'n/a', 'NA', ''], pd.NA)
    
    # 8. Clean density values
    df['Density'] = df['Density'].replace(['N/A', 'n/a', 'NA', ''], pd.NA)
    
    # 9. Remove entries with missing critical data
    required_cols = ['System', 'Ring', 'Hotspots']
    if 'Material' in df.columns:
        required_cols.append('Material')
    df = df.dropna(subset=required_cols)
    
    # 10. Standardize ring types
    ring_type_mapping = {
        'icy': 'Icy', 'ICY': 'Icy', 'ice': 'Icy',
        'metallic': 'Metallic', 'METALLIC': 'Metallic', 'metal': 'Metallic',
        'rocky': 'Rocky', 'ROCKY': 'Rocky', 'rock': 'Rocky'
    }
    df['Type'] = df['Type'].str.strip()
    df['Type'] = df['Type'].replace(ring_type_mapping)
    
    cleaned_count = len(df)
    removed_count = initial_count - cleaned_count
    print(f"    Removed {removed_count} garbage/invalid records")
    print(f"    Clean records remaining: {cleaned_count}")
    
    return df

def merge_with_master(df_master, gap_data):
    """Merge gap data with master, avoiding duplicates and cleaning garbage"""
    print(f"\nMerging gap data with master...")
    
    # Combine all gap data
    all_gap_records = []
    for material, df_gap in gap_data.items():
        print(f"  Processing {material}...")
        df_gap_clean = clean_data_comprehensive(df_gap.copy())
        all_gap_records.append(df_gap_clean)
    
    if not all_gap_records:
        print("No gap data to merge")
        return df_master
    
    df_all_gaps = pd.concat(all_gap_records, ignore_index=True)
    print(f"Combined clean gap records: {len(df_all_gaps)}")
    
    # Clean existing master data too
    if len(df_master) > 0:
        print("Cleaning existing master data...")
        df_master = clean_data_comprehensive(df_master.copy())
    
    # Handle master data without Material column
    if len(df_master) > 0 and 'Material' not in df_master.columns:
        print("Master data missing Material column - will be combined as legacy data")
        df_master['Material'] = 'Legacy'  # Temporary placeholder
    
    # Identify duplicates to avoid
    if len(df_master) > 0:
        # Create comparison keys (case insensitive)
        df_master['merge_key'] = (df_master['System'].str.lower() + '|' + 
                                 df_master['Ring'].str.lower() + '|' + 
                                 df_master.get('Material', 'Legacy').str.lower())
        df_all_gaps['merge_key'] = (df_all_gaps['System'].str.lower() + '|' + 
                                   df_all_gaps['Ring'].str.lower() + '|' + 
                                   df_all_gaps['Material'].str.lower())
        
        # Find new records (not in master)
        new_records = df_all_gaps[~df_all_gaps['merge_key'].isin(df_master['merge_key'])].copy()
        
        # Clean up merge keys
        df_master = df_master.drop('merge_key', axis=1)
        new_records = new_records.drop('merge_key', axis=1)
        
        print(f"New records to add: {len(new_records)}")
        print(f"Duplicate records skipped: {len(df_all_gaps) - len(new_records)}")
        
        # Merge
        df_final = pd.concat([df_master, new_records], ignore_index=True)
    else:
        # No existing master data
        df_final = df_all_gaps.copy()
        print(f"Creating new master with all gap data: {len(df_final)}")
    
    # Final deduplication pass
    print("Final deduplication pass...")
    initial_final = len(df_final)
    df_final = df_final.drop_duplicates(subset=['System', 'Ring', 'Material'], keep='first')
    final_final = len(df_final)
    if initial_final != final_final:
        print(f"  Removed {initial_final - final_final} additional duplicates")
    
    return df_final

def save_updated_master(df_final):
    """Save the updated master file with backup"""
    master_file = Path("app/data/Hotspots/all_materials_hotspots.xlsx")
    backup_file = Path("app/data/Hotspots/all_materials_hotspots_backup.xlsx")
    
    # Create backup of existing file
    if master_file.exists():
        print(f"Creating backup: {backup_file}")
        import shutil
        shutil.copy2(master_file, backup_file)
    
    # Save updated master
    print(f"Saving updated master: {master_file}")
    df_final.to_excel(master_file, index=False)
    print(f"  Final master records: {len(df_final)}")
    
    # Show summary by material
    print(f"\nFinal summary by material:")
    material_summary = df_final.groupby('Material').agg({
        'System': 'nunique',
        'Hotspots': 'sum'
    }).rename(columns={'System': 'Unique_Systems', 'Hotspots': 'Total_Hotspots'})
    
    for material, row in material_summary.iterrows():
        print(f"  {material:20} {row['Unique_Systems']:4d} systems, {row['Total_Hotspots']:5d} hotspots")
    
    total_systems = material_summary['Unique_Systems'].sum()
    total_hotspots = material_summary['Total_Hotspots'].sum()
    print(f"  {'TOTAL':20} {total_systems:4d} systems, {total_hotspots:5d} hotspots")
    
    return total_systems, total_hotspots

def main():
    """Main comprehensive merge process"""
    print("="*70)
    print("COMPREHENSIVE GAP DATA MERGE + CLEANING")
    print("="*70)
    print("Merging all gap files into all_materials_hotspots.xlsx")
    print("Includes: garbage removal, duplicate cleaning, data validation")
    
    # Load existing master
    df_master = load_existing_master()
    
    # Load all gap files from multiple directories
    gap_data = load_all_gap_files()
    
    if not gap_data:
        print("No gap data found. Nothing to merge.")
        return
    
    # Merge with comprehensive cleaning
    df_final = merge_with_master(df_master, gap_data)
    
    # Save with backup
    total_systems, total_hotspots = save_updated_master(df_final)
    
    print("="*70)
    print("COMPREHENSIVE MERGE + CLEANING COMPLETE!")
    print("="*70)
    print(f"✅ Garbage text removed from system/ring names")
    print(f"✅ Duplicates removed (case-insensitive)")
    print(f"✅ Invalid entries filtered out")
    print(f"✅ Data validation applied")
    print(f"✅ Backup created: all_materials_hotspots_backup.xlsx")
    print(f"")
    print(f"🎯 RESULT: {total_systems} systems with {total_hotspots} hotspots")
    print(f"📁 Updated: app/data/Hotspots/all_materials_hotspots.xlsx")
    print(f"")
    print(f"Next step: Import to database with import_excel_to_database.py")

if __name__ == "__main__":
    main()