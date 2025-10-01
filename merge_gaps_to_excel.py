#!/usr/bin/env python3
"""
Step 1: Merge Gap Data into Master Excel File
Merges all individual gap files into the existing all_materials_hotspots.xlsx
"""

import pandas as pd
from pathlib import Path
import sqlite3
from datetime import datetime
import re

def load_existing_master():
    """Load the existing all_materials_hotspots.xlsx master file"""
    master_file = Path("app/data/Hotspots/all_materials_hotspots.xlsx")
    
    if master_file.exists():
        print(f"Loading existing master file: {master_file}")
        df_master = pd.read_excel(master_file)
        print(f"  Current master records: {len(df_master)}")
        return df_master
    else:
        print("No existing master file found - will create new one")
        return pd.DataFrame(columns=['System', 'Ring', 'Hotspots', 'Type', 'LS', 'Density', 'Material'])

def load_gap_files():
    """Load all gap files from the extraction"""
    gap_dir = Path("app/data/Hotspots/all_materials_gaps")
    
    if not gap_dir.exists():
        print("ERROR: Gap directory not found. Extraction may not be complete.")
        return {}
    
    gap_files = list(gap_dir.glob("*_complete_gaps.xlsx"))
    print(f"Found {len(gap_files)} gap files:")
    
    gap_data = {}
    total_gap_records = 0
    
    for gap_file in gap_files:
        # Extract material name from filename
        material = gap_file.stem.replace('_complete_gaps', '')
        
        try:
            df_gap = pd.read_excel(gap_file)
            df_gap['Material'] = material  # Add material column
            
            gap_data[material] = df_gap
            total_gap_records += len(df_gap)
            
            print(f"  {material:20} {len(df_gap):4d} gap records")
            
        except Exception as e:
            print(f"  ERROR loading {gap_file}: {e}")
    
    print(f"Total gap records to merge: {total_gap_records}")
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
    # Remove entries with empty or very short system names
    df = df[df['System'].str.len() > 2]
    df = df[df['Ring'].str.len() > 0]
    
    # Remove entries where system name looks like garbage (starts with non-letter)
    df = df[df['System'].str.match(r'^[A-Za-z]', na=False)]
    
    # Remove entries with system names that are clearly garbage
    garbage_patterns = [
        r'^[0-9]+$',  # Only numbers
        r'^[^a-zA-Z0-9\s\-]+',  # Starts with special characters
        r'^\s*$',  # Only whitespace
        r'^(N/A|NA|null|undefined|error)$',  # Common error values
        r'^\d+\.\d+$',  # Decimal numbers only
    ]
    
    for pattern in garbage_patterns:
        df = df[~df['System'].str.match(pattern, case=False, na=False)]
    
    # 4. Clean material names
    df['Material'] = df['Material'].astype(str).str.strip()
    
    # 5. Validate numeric fields
    df['Hotspots'] = pd.to_numeric(df['Hotspots'], errors='coerce')
    df = df[df['Hotspots'] > 0]  # Remove zero or invalid hotspot counts
    
    # 6. Clean LS distances (allow N/A but validate numbers)
    df['LS'] = df['LS'].replace(['N/A', 'n/a', 'NA', ''], pd.NA)
    
    # 7. Clean density values
    df['Density'] = df['Density'].replace(['N/A', 'n/a', 'NA', ''], pd.NA)
    
    # 8. Remove entries with missing critical data
    df = df.dropna(subset=['System', 'Ring', 'Material', 'Hotspots'])
    
    # 9. Standardize ring types
    ring_type_mapping = {
        'icy': 'Icy',
        'ICY': 'Icy', 
        'ice': 'Icy',
        'metallic': 'Metallic',
        'METALLIC': 'Metallic',
        'metal': 'Metallic',
        'rocky': 'Rocky',
        'ROCKY': 'Rocky',
        'rock': 'Rocky'
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
        # Clean each material's data before combining
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
    
    # Identify duplicates to avoid
    if len(df_master) > 0:
        # Create comparison keys (case insensitive)
        df_master['merge_key'] = (df_master['System'].str.lower() + '|' + 
                                 df_master['Ring'].str.lower() + '|' + 
                                 df_master['Material'].str.lower())
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
    
    # Final deduplication pass (in case of any remaining duplicates)
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
    
    print(f"  {'TOTAL':20} {material_summary['Unique_Systems'].sum():4d} systems, {material_summary['Total_Hotspots'].sum():5d} hotspots")

def main():
    """Main merge process"""
    print("="*60)
    print("STEP 1: MERGE GAP DATA INTO MASTER EXCEL")
    print("="*60)
    
    # Load existing master
    df_master = load_existing_master()
    
    # Load gap files
    gap_data = load_gap_files()
    
    if not gap_data:
        print("No gap data found. Nothing to merge.")
        return
    
    # Merge
    df_final = merge_with_master(df_master, gap_data)
    
    # Save
    save_updated_master(df_final)
    
    print("="*60)
    print("EXCEL MERGE COMPLETE!")
    print("="*60)
    print("Next step: Run database import script")

if __name__ == "__main__":
    main()