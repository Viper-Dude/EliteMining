#!/usr/bin/env python3
"""
Parse and Clean All Materials Gap Files
Handles the corrected data format where:
- System = Distance (in LY)
- Ring = Actual system name  
- Hotspots = Complex ring data like "2 A RingPainite:1Platinum:2Rhodplumsite:1"
"""

import pandas as pd
import re
from pathlib import Path

def parse_ring_data(ring_data_str, target_material):
    """
    Parse ring data string to extract hotspot info for target material
    Example: "2 A RingPainite:1Platinum:2Rhodplumsite:1" -> extracts Platinum:2
    """
    if not isinstance(ring_data_str, str):
        return []
    
    results = []
    
    # Extract ring identifier (like "2 A", "5 A", "AB 1 A", etc.)
    ring_match = re.search(r'^([A-Z0-9\s]+)\s+Ring', ring_data_str)
    if not ring_match:
        return results
        
    ring_id = ring_match.group(1).strip()
    
    # Find the target material and its hotspot count
    material_pattern = f'{target_material}:(\d+)'
    material_matches = re.findall(material_pattern, ring_data_str, re.IGNORECASE)
    
    if material_matches:
        hotspot_count = int(material_matches[0])
        results.append({
            'ring': ring_id,
            'hotspots': hotspot_count
        })
    
    return results

def parse_material_file(file_path, material_name):
    """Parse a single material file and convert to standard format"""
    print(f"Parsing {file_path.name}...")
    
    try:
        df = pd.read_excel(file_path)
        print(f"  Loaded {len(df)} records")
        
        parsed_records = []
        paesia_count = 0
        
        for _, row in df.iterrows():
            distance = row['System']  # This is actually distance
            system_name = str(row['Ring']).strip()  # This is the actual system name
            ring_data = str(row['Hotspots'])  # Complex ring/material data
            ring_type = row['Type']
            ls_distance = row['LS'] 
            density = row['Density']
            
            # Skip invalid entries
            if system_name in ['nan', '', 'Ring']:
                continue
                
            # Remove * suffix from system names
            system_name = system_name.rstrip('*')
            
            # Parse the ring data for this specific material
            ring_info = parse_ring_data(ring_data, material_name)
            
            for ring in ring_info:
                parsed_record = {
                    'System': system_name,
                    'Ring': ring['ring'],
                    'Hotspots': ring['hotspots'],
                    'Type': ring_type,
                    'LS': ls_distance,
                    'Density': density,
                    'Material': material_name
                }
                parsed_records.append(parsed_record)
                
                # Track Paesia specifically
                if 'paesia' in system_name.lower():
                    paesia_count += 1
                    print(f"    ✅ PAESIA: {system_name} - Ring {ring['ring']} - {ring['hotspots']} {material_name} hotspots")
        
        print(f"  Parsed to {len(parsed_records)} hotspot records")
        print(f"  Paesia records: {paesia_count}")
        
        return parsed_records
        
    except Exception as e:
        print(f"  ERROR parsing {file_path}: {e}")
        return []

def main():
    """Parse all material files in the gaps folder"""
    
    print("="*70)
    print("PARSING ALL MATERIALS GAP FILES")
    print("="*70)
    print("Converting corrected extraction format to standard database format")
    
    gaps_dir = Path("app/data/Hotspots/all_materials_gaps")
    gap_files = list(gaps_dir.glob("*_complete_gaps.xlsx"))
    
    print(f"\nFound {len(gap_files)} files to parse:")
    for f in gap_files:
        print(f"  {f.name}")
    
    parsed_dir = Path("app/data/Hotspots/parsed_gaps")
    parsed_dir.mkdir(parents=True, exist_ok=True)
    
    total_records = 0
    total_paesia = 0
    
    for gap_file in gap_files:
        # Extract material name from filename
        material_name = gap_file.stem.replace('_complete_gaps', '')
        
        # Parse the file
        parsed_records = parse_material_file(gap_file, material_name)
        
        if parsed_records:
            # Save parsed data
            df_parsed = pd.DataFrame(parsed_records)
            output_file = parsed_dir / f"{material_name}_parsed.xlsx"
            df_parsed.to_excel(output_file, index=False)
            
            paesia_in_material = sum(1 for r in parsed_records if 'paesia' in r['System'].lower())
            total_paesia += paesia_in_material
            total_records += len(parsed_records)
            
            print(f"  Saved: {output_file} ({len(parsed_records)} records)")
        
        print()
    
    print("="*70)
    print("PARSING COMPLETE")
    print("="*70)
    print(f"📊 Total parsed records: {total_records}")
    print(f"🎯 Total Paesia records found: {total_paesia}")
    print(f"📁 Parsed files saved to: {parsed_dir}")
    print("\nReady for merge into master database!")

if __name__ == "__main__":
    main()