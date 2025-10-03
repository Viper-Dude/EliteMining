"""
Combine Corrected Material Files into Single Excel
Combines all *_extracted_corrected.xlsx files into one file with separate sheets
"""

import pandas as pd
import os
import glob

def combine_corrected_materials():
    """Combine all corrected material files into single Excel file"""
    
    print("COMBINING CORRECTED MATERIAL FILES")
    print("==================================")
    
    # Find all corrected extraction files
    hotspot_dir = 'app/data/Hotspots'
    pattern = os.path.join(hotspot_dir, '*_extracted_corrected.xlsx')
    files = glob.glob(pattern)
    
    if not files:
        print("ERROR: No corrected extraction files found!")
        print(f"Looking in: {hotspot_dir}")
        return
    
    print(f"Found {len(files)} corrected material files:")
    for file in sorted(files):
        filename = os.path.basename(file)
        print(f"  - {filename}")
    
    # Create combined Excel file
    output_file = os.path.join(hotspot_dir, 'All_Materials_Combined_Corrected.xlsx')
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        total_records = 0
        materials_processed = 0
        
        for file_path in sorted(files):
            try:
                # Extract material name from filename
                filename = os.path.basename(file_path)
                material_name = filename.replace('_extracted_corrected.xlsx', '')
                
                print(f"\nProcessing: {material_name}")
                
                # Read the material data
                df = pd.read_excel(file_path)
                
                # Ensure sheet name is valid (Excel limit: 31 characters)
                sheet_name = material_name[:31] if len(material_name) > 31 else material_name
                
                # Write to sheet
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                record_count = len(df)
                total_records += record_count
                materials_processed += 1
                
                print(f"  ✅ {material_name}: {record_count:,} records → Sheet '{sheet_name}'")
                
                # Show sample data for verification
                if len(df) > 0:
                    sample = df.iloc[0]
                    print(f"     Sample: {sample['System']} | LS:{sample['LS']} | Ring:{sample['Ring']} | Density:{sample['Density']}")
                
            except Exception as e:
                print(f"  ❌ ERROR processing {filename}: {e}")
                continue
    
    print(f"\n{'='*50}")
    print("COMBINATION SUMMARY")
    print(f"{'='*50}")
    print(f"Materials processed: {materials_processed}")
    print(f"Total records: {total_records:,}")
    print(f"Output file: {output_file}")
    print("\n✅ All corrected materials combined successfully!")
    
    return output_file

if __name__ == "__main__":
    combine_corrected_materials()