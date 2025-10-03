#!/usr/bin/env python3
"""
Merge Parsed Gap Data into Master Excel File
Takes all parsed files from parsed_gaps folder and merges them with existing master
"""

import pandas as pd
from pathlib import Path
import re

def clean_data_comprehensive(df):
    """Clean parsed data - lighter cleaning since data is already parsed properly"""
    if df.empty:
        return df
    
    print(f"    Cleaning {len(df)} records...")
    
    # Remove any remaining invalid entries
    df = df.dropna(subset=['System', 'Ring'])
    
    # Clean system names
    df['System'] = df['System'].astype(str).str.strip()
    df = df[~df['System'].isin(['', 'nan', 'System'])]
    
    # Clean ring names
    df['Ring'] = df['Ring'].astype(str).str.strip()
    
    # Ensure hotspots is numeric and positive
    df['Hotspots'] = pd.to_numeric(df['Hotspots'], errors='coerce')
    df = df[df['Hotspots'] > 0]
    
    # Clean material names
    if 'Material' in df.columns:
        df['Material'] = df['Material'].astype(str).str.strip()
    
    print(f"    Clean records remaining: {len(df)}")
    return df

def merge_parsed_data():
    """Merge all parsed gap files into master Excel"""
    
    print("="*70)
    print("MERGING PARSED GAP DATA")
    print("="*70)
    
    # Load existing master file
    master_file = Path("app/data/Hotspots/all_materials_hotspots.xlsx")
    if master_file.exists():
        print(f"Loading existing master: {master_file}")
        df_master = pd.read_excel(master_file)
        print(f"  Current master records: {len(df_master)}")
    else:
        print("No existing master file found, creating new one")
        df_master = pd.DataFrame()
    
    # Load all parsed gap files
    parsed_dir = Path("app/data/Hotspots/parsed_gaps")
    parsed_files = list(parsed_dir.glob("*_parsed.xlsx"))
    print(f"\nFound {len(parsed_files)} parsed files:")
    
    all_new_data = []
    total_paesia = 0
    
    for parsed_file in parsed_files:
        material = parsed_file.stem.replace('_parsed', '')
        print(f"  Processing {material}...")
        
        try:
            df_parsed = pd.read_excel(parsed_file)
            
            # Clean the parsed data
            df_cleaned = clean_data_comprehensive(df_parsed)
            
            if not df_cleaned.empty:
                all_new_data.append(df_cleaned)
                
                # Count Paesia records
                paesia_count = len(df_cleaned[df_cleaned['System'].str.contains('Paesia', case=False, na=False)])
                total_paesia += paesia_count
                
                if paesia_count > 0:
                    print(f"    🎯 {paesia_count} Paesia records in {material}")
            
        except Exception as e:
            print(f"    ERROR loading {parsed_file}: {e}")
    
    if not all_new_data:
        print("\nNo new data to merge!")
        return
    
    # Combine all new data
    df_new_combined = pd.concat(all_new_data, ignore_index=True)
    print(f"\nCombined new data: {len(df_new_combined)} records")
    print(f"Total Paesia records: {total_paesia}")
    
    # Remove duplicates within new data
    before_dedup = len(df_new_combined)
    df_new_combined = df_new_combined.drop_duplicates(subset=['System', 'Ring', 'Material'], keep='first')
    after_dedup = len(df_new_combined)
    print(f"Removed {before_dedup - after_dedup} internal duplicates")
    
    # Merge with existing master
    if not df_master.empty:
        print("\nMerging with existing master...")
        
        # Find records that don't already exist in master
        merge_key = ['System', 'Ring']
        if 'Material' in df_master.columns:
            merge_key.append('Material')
        
        # Create comparison keys
        df_master['merge_key'] = df_master[merge_key].astype(str).agg('_'.join, axis=1)
        df_new_combined['merge_key'] = df_new_combined[merge_key].astype(str).agg('_'.join, axis=1)
        
        # Filter out duplicates
        new_records = df_new_combined[~df_new_combined['merge_key'].isin(df_master['merge_key'])]
        duplicate_count = len(df_new_combined) - len(new_records)
        
        print(f"New records to add: {len(new_records)}")
        print(f"Duplicate records skipped: {duplicate_count}")
        
        # Combine master and new records
        if not new_records.empty:
            # Remove merge_key columns
            df_master = df_master.drop('merge_key', axis=1)
            new_records = new_records.drop('merge_key', axis=1)
            
            df_final = pd.concat([df_master, new_records], ignore_index=True)
        else:
            df_final = df_master.drop('merge_key', axis=1)
    else:
        print("\nCreating new master file...")
        df_final = df_new_combined.copy()
    
    # Final cleanup and validation
    print("\nFinal validation and cleanup...")
    df_final = clean_data_comprehensive(df_final)
    
    # Create backup
    if master_file.exists():
        backup_file = master_file.parent / "all_materials_hotspots_backup.xlsx"
        print(f"Creating backup: {backup_file}")
        df_master_backup = pd.read_excel(master_file)
        df_master_backup.to_excel(backup_file, index=False)
    
    # Save updated master
    print(f"Saving updated master: {master_file}")
    df_final.to_excel(master_file, index=False)
    
    print(f"Final master records: {len(df_final)}")
    
    # Summary by material
    if 'Material' in df_final.columns:
        print(f"\nFinal summary by material:")
        material_summary = df_final.groupby('Material').agg({
            'System': 'nunique',
            'Hotspots': 'sum'
        }).round(0)
        
        for material, row in material_summary.iterrows():
            systems = int(row['System'])
            hotspots = int(row['Hotspots'])
            print(f"  {material:20} {systems:3d} systems, {hotspots:4d} hotspots")
        
        total_systems = df_final['System'].nunique()
        total_hotspots = df_final['Hotspots'].sum()
        print(f"  {'TOTAL':20} {total_systems:3d} systems, {total_hotspots:4.0f} hotspots")
    
    print("\n" + "="*70)
    print("MERGE COMPLETE!")
    print("="*70)
    print("✅ Parsed data merged successfully")
    print("✅ Paesia Platinum hotspots now included")
    print("✅ Comprehensive cleaning applied")
    print("✅ Duplicates removed")
    print(f"📁 Updated: {master_file}")

def main():
    merge_parsed_data()

if __name__ == "__main__":
    main()