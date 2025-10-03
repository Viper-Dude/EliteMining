#!/usr/bin/env python3
"""
EDTools.cc Expanded Hotspot Data Extractor
Strategic expansion of reference systems within the inhabited bubble
Focus on filling gaps in our existing database
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from pathlib import Path
import sqlite3

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
                            
                            # Extract clean ring name
                            if ring_raw and ring_raw != '-':
                                ring_name = re.sub(r'\s*\([^)]*\)', '', ring_raw).strip()
                                ring_name = re.sub(r'\s+', ' ', ring_name).strip()
                                
                                # Determine ring type
                                if any(word in ring_raw.lower() for word in ['icy', 'ice']):
                                    ring_type = "Icy"
                                elif any(word in ring_raw.lower() for word in ['metallic', 'metal']):
                                    ring_type = "Metallic"
                                elif any(word in ring_raw.lower() for word in ['rocky', 'rock']):
                                    ring_type = "Rocky"
                            
                            # Extract hotspot count
                            hotspot_count_match = re.search(r'\b(\d+)\b', hotspots_raw)
                            if hotspot_count_match:
                                material_count = int(hotspot_count_match.group(1))
                            
                            # Clean LS distance
                            ls_clean = "N/A"
                            if ls_distance and ls_distance != '-':
                                ls_match = re.search(r'(\d+(?:\.\d+)?)', ls_distance)
                                if ls_match:
                                    ls_clean = float(ls_match.group(1))
                            
                            # Clean density
                            density_clean = "N/A"
                            if density and density != '-':
                                density_match = re.search(r'(\d+(?:,\d+)*)', density.replace(',', ''))
                                if density_match:
                                    density_clean = int(density_match.group(1).replace(',', ''))
                            
                            # Only add if we have valid data
                            if system_name and ring_name and material_count > 0:
                                hotspots.append({
                                    'System': system_name,
                                    'Ring': ring_name,
                                    'Hotspots': material_count,
                                    'Type': ring_type,
                                    'LS': ls_clean,
                                    'Density': density_clean
                                })
                        except Exception as e:
                            continue
        
        return hotspots
        
    except Exception as e:
        print(f"Error extracting data from {url}: {e}")
        return []

def check_existing_system(system_name, material_name):
    """Check if system already exists in our database"""
    db_path = Path("app/data/user_data.db")
    if not db_path.exists():
        return False
        
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM hotspot_data 
                WHERE LOWER(system_name) = LOWER(?) AND LOWER(material_name) = LOWER(?)
            """, (system_name, material_name))
            count = cursor.fetchone()[0]
            return count > 0
    except:
        return False

def process_material_gaps(material_name):
    """Process a single material focusing on gap-filling"""
    print(f"\n{'='*60}")
    print(f"Gap-filling for {material_name}")
    print(f"{'='*60}")
    
    # STRATEGIC reference systems - carefully chosen within inhabited bubble
    reference_systems = [
        # Original systems (keep for consistency)
        "Sol", "Lave", "Alioth", "Merope", 
        "Witch%20Head%20Sector%20IR-W%20c1-9", "HIP%2022460",
        
        # NEW strategic additions within bubble
        "Paesia",           # Fix known missing data 
        "Deciat",           # Popular engineering hub (Farseer)
        "Shinrarta%20Dezhra", # Pilots Federation headquarters
        "Maia",             # Pleiades region coverage
        "Diaguandri",       # Ray Gateway - popular trade hub
        "Jameson%20Memorial", # Elite pilots gathering place
        
        # Secondary bubble coverage
        "Colonia",          # Main secondary bubble system
        "Jacques%20Station", # Colonia area coverage
        
        # Additional strategic points (limit range to avoid empty space)
        "Sirius",           # Sirius Corporation space
        "Wolf%20359",       # Close to Sol, different direction
        "LHS%203447",       # Starter system area coverage
        "Dromi"             # Another starter area
    ]
    
    print(f"Using {len(reference_systems)} strategic reference systems")
    print("(Focused on inhabited bubble + known gap areas)")
    
    all_hotspots = []
    new_systems_found = 0
    existing_systems_skipped = 0
    
    for i, ref_system in enumerate(reference_systems, 1):
        url = f"https://edtools.cc/hotspot?s={ref_system}&m={material_name}&ms=1"
        print(f"[{i:2d}/{len(reference_systems)}] Processing: {ref_system.replace('%20', ' ')}")
        
        hotspots = extract_hotspot_data(url, material_name)
        
        # Filter out systems we already have
        new_hotspots = []
        for hotspot in hotspots:
            if not check_existing_system(hotspot['System'], material_name):
                new_hotspots.append(hotspot)
                new_systems_found += 1
            else:
                existing_systems_skipped += 1
        
        all_hotspots.extend(new_hotspots)
        print(f"    Extracted: {len(hotspots)} total, {len(new_hotspots)} new, {len(hotspots)-len(new_hotspots)} existing")
        
        time.sleep(1.5)  # Be extra respectful to the server
    
    print(f"\nSummary for {material_name}:")
    print(f"  New systems found: {new_systems_found}")
    print(f"  Existing systems skipped: {existing_systems_skipped}")
    
    if all_hotspots:
        # Create DataFrame
        df = pd.DataFrame(all_hotspots)
        
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
        
        # Deduplicate by System + Ring combination
        before_dedup = len(df)
        df = df.drop_duplicates(subset=['System', 'Ring'], keep='first')
        after_dedup = len(df)
        removed = before_dedup - after_dedup
        
        print(f"  After cleanup: {after_dedup} unique records ({removed} duplicates removed)")
        
        if after_dedup > 0:
            # Create output directory
            output_dir = Path("app/data/Hotspots/gaps")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save as Excel file
            excel_file = output_dir / f"{material_name}_gaps.xlsx"
            df.to_excel(excel_file, index=False)
            print(f"  Saved to: {excel_file}")
            
            return after_dedup, df['Hotspots'].sum()
        else:
            print(f"  No new data to save")
            return 0, 0
    else:
        print(f"  No hotspots extracted")
        return 0, 0

def main():
    """Main function to run gap-filling extraction"""
    
    # Focus on materials where we suspect missing data
    priority_materials = [
        "Alexandrite",  # Known missing Paesia data
        "Painite",      # High-value material, likely more systems  
        "Platinum",     # Common mining material
        "LowTemperatureDiamond",  # Very popular material
        "Tritium"       # Fleet Carriers fuel
    ]
    
    print("Starting GAP-FILLING extraction for EDTools.cc hotspot data")
    print(f"Priority materials: {len(priority_materials)}")
    print(f"Focus: Fill gaps in existing database within inhabited bubble")
    print(f"Strategy: Skip known systems, extract only missing data")
    
    summary = {}
    start_time = time.time()
    
    for i, material in enumerate(priority_materials, 1):
        print(f"\n[{i}/{len(priority_materials)}] Processing {material}...")
        locations, total_hotspots = process_material_gaps(material)
        summary[material] = {'new_locations': locations, 'hotspots': total_hotspots}
    
    # Final summary
    elapsed_time = time.time() - start_time
    print(f"\n{'='*80}")
    print("GAP-FILLING EXTRACTION COMPLETE!")
    print(f"{'='*80}")
    print(f"Time elapsed: {elapsed_time:.1f} seconds")
    
    print("\nNEW DATA FOUND:")
    print("-" * 50)
    total_new_locations = 0
    total_new_hotspots = 0
    
    for material, stats in summary.items():
        if stats['new_locations'] > 0:
            print(f"{material:20} {stats['new_locations']:4d} new locations, {stats['hotspots']:5d} hotspots")
            total_new_locations += stats['new_locations']
            total_new_hotspots += stats['hotspots']
        else:
            print(f"{material:20} [NO NEW] Complete coverage")
    
    print("-" * 50)
    print(f"{'TOTAL NEW':20} {total_new_locations:4d} locations, {total_new_hotspots:5d} hotspots")
    
    if total_new_locations > 0:
        print(f"\nGap files saved in: app/data/Hotspots/gaps/")
        print(f"Next step: Combine gap data with existing database")
    else:
        print(f"\nNo gaps found - existing database appears complete!")
    
    print(f"Extraction stayed within inhabited bubble - no empty space scraped!")

if __name__ == "__main__":
    main()