#!/usr/bin/env python3
"""
EDTools.cc Hotspot Data Extractor - Improved Version
Extracts clean hotspot information matching the Hotspots_bubble_cleaned.xlsx structure
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from pathlib import Path

def extract_hotspot_data(url, material="Alexandrite"):
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
                            # Look for patterns like "B 3 A Ring", "11 A Ring", "A 4 A Ring"
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
                            elif any(mat in ring_lower for mat in ['ltd', 'diamond', 'tritium', 'bromellite']):
                                ring_type = "Icy" 
                            elif any(mat in ring_lower for mat in ['alexandrite', 'benitoite', 'painite', 'opal', 'monazite', 'musgravite', 'serendibite']):
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
        
        print(f"Extracted {len(hotspots)} {material} hotspots from {url}")
        return hotspots
        
    except Exception as e:
        print(f"Error extracting data from {url}: {e}")
        return []

def main():
    # URLs for Alexandrite hotspot data
    urls = [
        "https://edtools.cc/hotspot?s=Sol&m=Alexandrite&ms=1",
        "https://edtools.cc/hotspot?s=Lave&m=Alexandrite&ms=1", 
        "https://edtools.cc/hotspot?s=Alioth%20&m=Alexandrite&ms=1",
        "https://edtools.cc/hotspot?s=Merope&m=Alexandrite&ms=1",
        "https://edtools.cc/hotspot?s=Witch%20Head%20Sector%20IR-W%20c1-9&m=Alexandrite&ms=1",
        "https://edtools.cc/hotspot?s=HIP%2022460&m=Alexandrite&ms=1"
    ]
    
    all_hotspots = []
    
    for url in urls:
        print(f"Processing: {url}")
        hotspots = extract_hotspot_data(url, "Alexandrite")
        all_hotspots.extend(hotspots)
        time.sleep(1)  # Be respectful to the server
    
    if all_hotspots:
        # Create DataFrame
        df = pd.DataFrame(all_hotspots)
        
        print(f"Raw extracted data: {len(df)} records")
        
        # Clean up data before deduplication
        # Clean system names
        df['System'] = df['System'].str.strip()
        df['System'] = df['System'].str.replace(r'[*\[\]]+', '', regex=True)  # Remove asterisks and brackets
        df['System'] = df['System'].str.replace(r'\s+', ' ', regex=True)      # Normalize whitespace
        
        # Clean ring names  
        df['Ring'] = df['Ring'].str.strip()
        df['Ring'] = df['Ring'].str.replace(r'\s+', ' ', regex=True)          # Normalize whitespace
        
        # Remove entries with empty or malformed system/ring names
        df = df[df['System'].str.len() > 0]
        df = df[df['Ring'].str.len() > 0] 
        df = df[~df['System'].str.contains(r'^[^a-zA-Z]', regex=True, na=False)]  # System must start with letter
        
        print(f"After cleaning: {len(df)} records")
        
        # Advanced deduplication: Remove duplicates based on System + Ring combination
        # Keep the entry with the highest hotspot count (best data quality)
        print("Removing duplicates based on System + Ring...")
        df_dedup = df.loc[df.groupby(['System', 'Ring'])['Hotspots'].idxmax()]
        
        print(f"After deduplication: {len(df_dedup)} unique System+Ring combinations")
        print(f"Removed {len(df) - len(df_dedup)} duplicate entries")
        
        # Sort by distance and hotspot count
        df_final = df_dedup.sort_values(['Distance_LY', 'Hotspots'], ascending=[True, False]).reset_index(drop=True)
        
        # Create output directory
        output_dir = Path("app/data/hotspots")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel with proper structure including LS and Density in main sheet
        # Create main sheet with all required columns: System, Ring, Hotspots, Type, LS, Density
        main_df = df_final[['System', 'Ring', 'Hotspots', 'Type', 'LS', 'Density']].copy()
        
        # Create detailed sheet with all data for reference
        detailed_df = df_final.copy()
        
        output_file = output_dir / "alexandrite_hotspots_fixed.xlsx"
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            # Main sheet with core columns plus LS and Density
            main_df.to_excel(writer, sheet_name='Alexandrite_Hotspots', index=False)
            # Detailed sheet with all data including Distance, URLs, etc.
            detailed_df.to_excel(writer, sheet_name='Detailed_Data', index=False)
        
        print(f"Created Excel file: {output_file}")
        print(f"Final unique hotspots: {len(main_df)}")
        
        # Display sample data
        print("\nSample data (main structure with LS and Density):")
        print(main_df.head(10).to_string(index=False))
        
        print(f"\nAll data including Distance and URLs available in 'Detailed_Data' sheet")
        
        # Show deduplication stats
        print(f"\nData quality summary:")
        print(f"  Total Alexandrite hotspots: {main_df['Hotspots'].sum()}")
        print(f"  Unique systems: {main_df['System'].nunique()}")
        print(f"  Average hotspots per ring: {main_df['Hotspots'].mean():.1f}")
        print(f"  LS range: {main_df['LS'].min():.0f} - {main_df['LS'].max():.0f}")
        print(f"  Ring types: {main_df['Type'].value_counts().to_dict()}")
        
    else:
        print("No hotspot data extracted. The page structure may have changed.")

if __name__ == "__main__":
    main()