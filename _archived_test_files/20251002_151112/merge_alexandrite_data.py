"""
Merge New Alexandrite Data into Combined File
Merges Alexandrite_extracted_NEW_REFS.xlsx into All_Materials_Combined_Corrected.xlsx
"""

import pandas as pd
import os
from openpyxl import load_workbook

def merge_alexandrite_data():
    """Merge new Alexandrite data into the combined Excel file"""
    
    # File paths
    new_data_file = 'app/data/Hotspots/Alexandrite_extracted_NEW_REFS.xlsx'
    combined_file = 'app/data/Hotspots/All_Materials_Combined_Corrected.xlsx'
    backup_file = 'app/data/Hotspots/All_Materials_Combined_Corrected_BACKUP.xlsx'
    
    print("MERGING ALEXANDRITE DATA")
    print("=" * 40)
    
    # Check if files exist
    if not os.path.exists(new_data_file):
        print(f"❌ Error: {new_data_file} not found!")
        return False
        
    if not os.path.exists(combined_file):
        print(f"❌ Error: {combined_file} not found!")
        return False
    
    try:
        # Create backup of combined file
        print("Creating backup of combined file...")
        import shutil
        shutil.copy2(combined_file, backup_file)
        print(f"✅ Backup created: {backup_file}")
        
        # Read new Alexandrite data
        print("Reading new Alexandrite data...")
        new_alex_df = pd.read_excel(new_data_file)
        print(f"✅ New data: {len(new_alex_df)} records")
        
        # Read existing combined file and current Alexandrite sheet
        print("Reading existing Alexandrite sheet...")
        existing_alex_df = pd.read_excel(combined_file, sheet_name='Alexandrite')
        print(f"✅ Existing data: {len(existing_alex_df)} records")
        
        # Show comparison
        print(f"\nDATA COMPARISON:")
        print(f"Existing Alexandrite: {len(existing_alex_df)} records, {existing_alex_df['System'].nunique()} unique systems")
        print(f"New Alexandrite:      {len(new_alex_df)} records, {new_alex_df['System'].nunique()} unique systems")
        
        # Combine the data
        print("\nCombining data...")
        combined_alex_df = pd.concat([existing_alex_df, new_alex_df], ignore_index=True)
        
        # Remove duplicates based on System, Ring, LS
        print("Removing duplicates...")
        before_dedup = len(combined_alex_df)
        combined_alex_df = combined_alex_df.drop_duplicates(subset=['System', 'Ring', 'LS'], keep='first')
        after_dedup = len(combined_alex_df)
        duplicates_removed = before_dedup - after_dedup
        
        print(f"✅ Combined data: {after_dedup} records")
        print(f"✅ Removed {duplicates_removed} duplicates")
        print(f"✅ Final unique systems: {combined_alex_df['System'].nunique()}")
        
        # Load the workbook to preserve all sheets
        print("Loading workbook...")
        with pd.ExcelWriter(combined_file, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            # Write the updated Alexandrite sheet
            combined_alex_df.to_excel(writer, sheet_name='Alexandrite', index=False)
            print("✅ Updated Alexandrite sheet in combined file")
        
        # Verify the update
        print("Verifying update...")
        verification_df = pd.read_excel(combined_file, sheet_name='Alexandrite')
        print(f"✅ Verification: {len(verification_df)} records in updated sheet")
        
        # Show summary
        print(f"\nSUMMARY:")
        print(f"Original Alexandrite records: {len(existing_alex_df)}")
        print(f"New records added: {len(new_alex_df)}")
        print(f"Duplicates removed: {duplicates_removed}")
        print(f"Final Alexandrite records: {len(verification_df)}")
        print(f"Net change: +{len(verification_df) - len(existing_alex_df)} records")
        
        # Show sample of new data
        if len(new_alex_df) > 0:
            print(f"\nSample of new data added:")
            print(new_alex_df.head(3).to_string(index=False))
        
        return True
        
    except Exception as e:
        print(f"❌ Error during merge: {e}")
        
        # Restore from backup if something went wrong
        if os.path.exists(backup_file):
            print("Restoring from backup...")
            import shutil
            shutil.copy2(backup_file, combined_file)
            print("✅ Restored from backup")
        
        return False

def main():
    """Main merge process"""
    print("ALEXANDRITE DATA MERGE TOOL")
    print("=" * 30)
    print("This will merge the new Alexandrite data into the combined file")
    print("Source: Alexandrite_extracted_NEW_REFS.xlsx")
    print("Target: All_Materials_Combined_Corrected.xlsx (Alexandrite sheet)")
    
    print("\nProceeding with merge...")
    
    success = merge_alexandrite_data()
    if success:
        print("\n🎉 Merge completed successfully!")
    else:
        print("\n❌ Merge failed!")

if __name__ == "__main__":
    main()