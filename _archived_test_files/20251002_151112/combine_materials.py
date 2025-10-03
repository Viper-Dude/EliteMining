#!/usr/bin/env python3
"""
Combine All Material Hotspot Data into Single Excel File
Creates one Excel file with each material as a separate sheet tab
"""

import pandas as pd
from pathlib import Path
import os

def combine_all_materials():
    """Combine all material hotspot files into one Excel file"""
    
    # Materials list (same order as extraction)
    materials = [
        "Alexandrite",
        "Benitoite", 
        "Bromellite",
        "Grandidierite",
        "LowTemperatureDiamond",
        "Monazite",
        "Musgravite", 
        "Opal",
        "Painite",
        "Platinum",
        "Rhodplumsite",
        "Serendibite",
        "Tritium"
    ]
    
    hotspots_dir = Path("app/data/hotspots")
    
    # Check that all files exist
    missing_files = []
    for material in materials:
        filename = f"{material.lower()}_hotspots.xlsx"
        file_path = hotspots_dir / filename
        if not file_path.exists():
            missing_files.append(filename)
    
    if missing_files:
        print(f"❌ Missing files: {missing_files}")
        return
    
    # Create combined Excel file
    output_file = hotspots_dir / "all_materials_hotspots.xlsx"
    
    print("🔗 Combining all material hotspot data...")
    print(f"📂 Source directory: {hotspots_dir}")
    print(f"📄 Output file: {output_file}")
    
    # Create Excel writer
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        
        total_locations = 0
        total_hotspots = 0
        summary_data = []
        
        for i, material in enumerate(materials, 1):
            print(f"[{i:2d}/{len(materials)}] Processing {material}...")
            
            # Read the main sheet from each material file
            filename = f"{material.lower()}_hotspots.xlsx"
            file_path = hotspots_dir / filename
            
            try:
                # Read the main hotspots sheet (first sheet, which contains the core data)
                df = pd.read_excel(file_path, sheet_name=0)  # First sheet
                
                # Verify we have the expected columns
                expected_cols = ['System', 'Ring', 'Hotspots', 'Type', 'LS', 'Density']
                if not all(col in df.columns for col in expected_cols):
                    print(f"⚠️  Warning: {material} missing expected columns")
                    print(f"    Expected: {expected_cols}")
                    print(f"    Found: {list(df.columns)}")
                
                # Write to combined file with material name as sheet name
                # Sheet names are limited to 31 characters in Excel
                sheet_name = material[:31] if len(material) > 31 else material
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                # Collect summary stats
                locations = len(df)
                hotspots = df['Hotspots'].sum()
                unique_systems = df['System'].nunique()
                
                total_locations += locations
                total_hotspots += hotspots
                
                # Ring type breakdown
                ring_types = df['Type'].value_counts().to_dict()
                ring_type_str = ", ".join([f"{k}: {v}" for k, v in ring_types.items()])
                
                summary_data.append({
                    'Material': material,
                    'Locations': locations,
                    'Total_Hotspots': hotspots,
                    'Unique_Systems': unique_systems,
                    'Avg_Hotspots_Per_Ring': round(hotspots / locations, 1),
                    'Ring_Types': ring_type_str
                })
                
                print(f"    ✅ {locations:3d} locations, {hotspots:4d} hotspots, {unique_systems:3d} systems")
                
            except Exception as e:
                print(f"    ❌ Error processing {material}: {e}")
                continue
        
        # Create summary sheet
        print("\n📊 Creating summary sheet...")
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Add totals row to summary
        totals_row = pd.DataFrame({
            'Material': ['TOTAL'],
            'Locations': [total_locations],
            'Total_Hotspots': [total_hotspots], 
            'Unique_Systems': [''],
            'Avg_Hotspots_Per_Ring': [round(total_hotspots / total_locations, 1)],
            'Ring_Types': ['']
        })
        
        # Append totals to summary sheet
        with pd.ExcelWriter(output_file, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
            summary_with_total = pd.concat([summary_df, totals_row], ignore_index=True)
            summary_with_total.to_excel(writer, sheet_name='Summary', index=False)
    
    print(f"\n🎉 COMBINATION COMPLETE!")
    print(f"📄 Created: {output_file}")
    print(f"📊 Total sheets: {len(materials) + 1} ({len(materials)} materials + 1 summary)")
    print(f"🎯 Total locations: {total_locations:,}")
    print(f"💎 Total hotspots: {total_hotspots:,}")
    
    # List all sheets created
    print(f"\n📑 Sheets in combined file:")
    print(f"   1. Summary (overview of all materials)")
    for i, material in enumerate(materials, 2):
        sheet_name = material[:31] if len(material) > 31 else material
        print(f"   {i:2d}. {sheet_name}")
    
    return output_file

def main():
    """Main function"""
    print("🚀 Starting material hotspot combination...")
    
    try:
        output_file = combine_all_materials()
        if output_file:
            print(f"\n✅ SUCCESS: All materials combined into {output_file}")
        else:
            print(f"\n❌ FAILED: Could not create combined file")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    main()