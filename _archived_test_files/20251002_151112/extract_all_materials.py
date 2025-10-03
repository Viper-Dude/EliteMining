#!/usr/bin/env python3
"""
EDTools.cc Complete Hotspot Data Extractor
Extracts all materials from EDTools.cc into separate Excel files
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from pathlib import Path

def extract_hotspot_data(url, material):
    """Extract hotspot data from EDTools.cc hotspot page with proper parsing"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        hotspots = []
        
        # Look for table rows containing hotspot data
        tables = soup.find_all('table')
        if tables:
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 5:  # Distance, System, Ring Type, Hotspots, LS, Density
                        try:
                            distance = cells[0].get_text(strip=True)
                            system_raw = cells[1].get_text(strip=True) 
                            ring_raw = cells[2].get_text(strip=True)
                            hotspots_raw = cells[3].get_text(strip=True)
                            ls_distance = cells[4].get_text(strip=True)
                            density = cells[5].get_text(strip=True) if len(cells) > 5 else "N/A"
                            
                            # Clean system name - remove clipboard links, asterisks, and extra text
                            system_name = re.sub(r'\[.*?\]', '', system_raw).strip()
                            system_name = system_name.replace('*', '').strip()
                            
                            # Parse ring data to extract clean ring name and hotspot count for our material
                            ring_name = ""
                            material_count = 0
                            ring_type = "Unknown"
                            
                            # Extract ring name (before material data starts)
                            ring_match = re.search(r'^([A-Z]?\s*\d+\s*[A-Z]?\s*[A-Z]?\s*Ring)', ring_raw, re.IGNORECASE)
                            if ring_match:
                                ring_name = ring_match.group(1).strip()
                            else:
                                # Fallback: try to extract any ring identifier
                                ring_fallback = re.search(r'^([^:]*)', ring_raw)
                                if ring_fallback:
                                    ring_name = ring_fallback.group(1).strip()
                            
                            # Extract hotspot count for our specific material
                            material_pattern = rf'{material}:(\d+)'
                            material_match = re.search(material_pattern, ring_raw, re.IGNORECASE)
                            if material_match:
                                material_count = int(material_match.group(1))
                            
                            # Determine ring type based on materials present
                            ring_lower = ring_raw.lower()
                            if any(mat in ring_lower for mat in ['platinum', 'palladium', 'gold', 'silver', 'osmium']):
                                ring_type = "Metallic"
                            elif any(mat in ring_lower for mat in ['ltd', 'diamond', 'tritium', 'bromellite', 'lowtemperaturediamond']):
                                ring_type = "Icy" 
                            elif any(mat in ring_lower for mat in ['alexandrite', 'benitoite', 'painite', 'opal', 'monazite', 'musgravite', 'serendibite', 'grandidierite', 'rhodplumsite']):
                                ring_type = "Rocky"
                            
                            # Only include if this material has hotspots
                            if material_count > 0 and system_name and ring_name:
                                # Clean up numeric values
                                distance_val = 0
                                try:
                                    distance_val = float(re.sub(r'[^\d.]', '', distance)) if distance else 0
                                except:
                                    pass
                                    
                                ls_val = 0
                                try:
                                    ls_val = float(re.sub(r'[^\d.]', '', ls_distance)) if ls_distance else 0
                                except:
                                    pass
                                
                                # Clean density - remove commas
                                density_clean = density.replace(',', '') if density != "N/A" else "N/A"
                                
                                hotspots.append({
                                    'System': system_name,
                                    'Ring': ring_name,
                                    'Hotspots': material_count,
                                    'Type': ring_type,
                                    'Distance_LY': distance_val,
                                    'LS': ls_val,
                                    'Density': density_clean,
                                    'Material': material,
                                    'Source_URL': url
                                })
                                
                        except Exception as e:
                            print(f"Error parsing row: {e}")
                            continue
        
        return hotspots
        
    except Exception as e:
        print(f"Error extracting data from {url}: {e}")
        return []

def process_material(material_name):
    """Process a single material and create its Excel file"""
    print(f"\n{'='*60}")
    print(f"Processing {material_name}")
    print(f"{'='*60}")
    
    # Reference systems
    reference_systems = [
        "Sol", "Lave", "Alioth%20", "Merope", 
        "Witch%20Head%20Sector%20IR-W%20c1-9", "HIP%2022460"
    ]
    
    all_hotspots = []
    
    for ref_system in reference_systems:
        url = f"https://edtools.cc/hotspot?s={ref_system}&m={material_name}&ms=1"
        print(f"Processing: {url}")
        
        hotspots = extract_hotspot_data(url, material_name)
        all_hotspots.extend(hotspots)
        print(f"Extracted {len(hotspots)} {material_name} hotspots")
        
        time.sleep(1)  # Be respectful to the server
    
    if all_hotspots:
        # Create DataFrame
        df = pd.DataFrame(all_hotspots)
        
        print(f"Raw extracted data: {len(df)} records")
        
        # Clean up data before deduplication
        df['System'] = df['System'].str.strip()
        df['System'] = df['System'].str.replace(r'[*\[\]]+', '', regex=True)
        df['System'] = df['System'].str.replace(r'\s+', ' ', regex=True)
        
        df['Ring'] = df['Ring'].str.strip()
        df['Ring'] = df['Ring'].str.replace(r'\s+', ' ', regex=True)
        
        # Remove entries with empty or malformed system/ring names
        df = df[df['System'].str.len() > 0]
        df = df[df['Ring'].str.len() > 0] 
        df = df[~df['System'].str.contains(r'^[^a-zA-Z]', regex=True, na=False)]
        
        print(f"After cleaning: {len(df)} records")
        
        # Advanced deduplication: Remove duplicates based on System + Ring combination
        df_dedup = df.loc[df.groupby(['System', 'Ring'])['Hotspots'].idxmax()]
        
        print(f"After deduplication: {len(df_dedup)} unique System+Ring combinations")
        print(f"Removed {len(df) - len(df_dedup)} duplicate entries")
        
        # Sort by distance and hotspot count
        df_final = df_dedup.sort_values(['Distance_LY', 'Hotspots'], ascending=[True, False]).reset_index(drop=True)
        
        # Create output directory
        output_dir = Path("app/data/hotspots")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel
        main_df = df_final[['System', 'Ring', 'Hotspots', 'Type', 'LS', 'Density']].copy()
        detailed_df = df_final.copy()
        
        output_file = output_dir / f"{material_name.lower()}_hotspots.xlsx"
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            main_df.to_excel(writer, sheet_name=f'{material_name}_Hotspots', index=False)
            detailed_df.to_excel(writer, sheet_name='Detailed_Data', index=False)
        
        print(f"✅ Created: {output_file}")
        print(f"Final unique hotspots: {len(main_df)}")
        print(f"Total {material_name} hotspots: {main_df['Hotspots'].sum()}")
        print(f"Unique systems: {main_df['System'].nunique()}")
        print(f"Ring types: {main_df['Type'].value_counts().to_dict()}")
        
        return len(main_df), main_df['Hotspots'].sum()
    else:
        print(f"❌ No hotspot data extracted for {material_name}")
        return 0, 0

def main():
    """Extract all materials"""
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
    
    print("🚀 Starting complete hotspot data extraction...")
    print(f"Materials to process: {len(materials)}")
    print(f"Reference systems per material: 6")
    print(f"Total URLs to process: {len(materials) * 6}")
    
    summary = {}
    start_time = time.time()
    
    for i, material in enumerate(materials, 1):
        print(f"\n[{i}/{len(materials)}] Processing {material}...")
        locations, total_hotspots = process_material(material)
        summary[material] = {'locations': locations, 'hotspots': total_hotspots}
    
    # Final summary
    elapsed_time = time.time() - start_time
    print(f"\n{'='*80}")
    print("🎉 EXTRACTION COMPLETE!")
    print(f"{'='*80}")
    print(f"Time elapsed: {elapsed_time:.1f} seconds")
    print(f"Files created: {len([m for m in summary.values() if m['locations'] > 0])}")
    
    print("\nSUMMARY BY MATERIAL:")
    print("-" * 60)
    total_locations = 0
    total_hotspots = 0
    
    for material, stats in summary.items():
        if stats['locations'] > 0:
            print(f"{material:20} {stats['locations']:4d} locations, {stats['hotspots']:5d} hotspots")
            total_locations += stats['locations'] 
            total_hotspots += stats['hotspots']
        else:
            print(f"{material:20} ❌ NO DATA")
    
    print("-" * 60)
    print(f"{'TOTAL':20} {total_locations:4d} locations, {total_hotspots:5d} hotspots")
    print(f"\nAll files saved in: app/data/hotspots/")

if __name__ == "__main__":
    main()