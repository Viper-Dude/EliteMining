#!/usr/bin/env python3
"""
EDTools.cc Complete Gap-Filling Extractor
Uses the corrected parsing logic to extract missing hotspot data for all materials
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from pathlib import Path
import sqlite3

def extract_hotspot_data(url, material):
    """Extract hotspot data from EDTools.cc hotspot page with corrected parsing"""
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
                
                # Find header row to understand column structure
                header_row = None
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 6:
                        headers = [cell.get_text(strip=True) for cell in cells]
                        if 'Distance' in headers and 'System' in headers:
                            header_row = headers
                            break
                
                if header_row:
                    for row in rows[1:]:  # Skip header
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 6:  # Need at least 6 columns
                            try:
                                distance = cells[0].get_text(strip=True)
                                system_raw = cells[1].get_text(strip=True) 
                                ring_raw = cells[2].get_text(strip=True)
                                ring_type = cells[3].get_text(strip=True)
                                material_hotspots = cells[4].get_text(strip=True)
                                ls_distance = cells[5].get_text(strip=True)
                                density = cells[6].get_text(strip=True) if len(cells) > 6 else "N/A"
                                
                                # Clean system name - remove clipboard links, asterisks
                                system_name = re.sub(r'\\[.*?\\]', '', system_raw).strip()
                                system_name = system_name.replace('*', '').strip()
                                
                                # Extract ring name from the complex ring string
                                # Example: "2 C RingAlexandrite:1Bromellite:1..."
                                ring_name = ""
                                ring_match = re.match(r'^([^A-Z]*[A-Z][^:]*)', ring_raw)
                                if ring_match:
                                    ring_name = ring_match.group(1).strip()
                                    # Clean up ring name
                                    ring_name = re.sub(r'\\s*Ring.*$', '', ring_name)
                                    if not ring_name:
                                        ring_name = ring_raw.split('Ring')[0] if 'Ring' in ring_raw else ring_raw[:10]
                                
                                # Parse material count from the hotspots column
                                material_count = 0
                                try:
                                    material_count = int(material_hotspots)
                                except:
                                    # If not a direct number, try to extract from ring data
                                    pattern = f"{material}:(\\d+)"
                                    match = re.search(pattern, ring_raw)
                                    if match:
                                        material_count = int(match.group(1))
                                
                                # Clean LS distance
                                ls_clean = "N/A"
                                if ls_distance and ls_distance != '-':
                                    ls_match = re.search(r'(\\d+(?:,\\d+)*)', ls_distance.replace(',', ''))
                                    if ls_match:
                                        ls_clean = float(ls_match.group(1))
                                
                                # Clean density
                                density_clean = "N/A"
                                if density and density != '-':
                                    density_match = re.search(r'(\\d+(?:\\.\\d+)?)', density)
                                    if density_match:
                                        density_clean = float(density_match.group(1))
                                
                                # Only add if we have valid data and the material count > 0
                                if system_name and ring_name and material_count > 0:
                                    hotspots.append({
                                        'System': system_name,
                                        'Ring': ring_name,
                                        'Hotspots': material_count,
                                        'Type': ring_type.strip(),
                                        'LS': ls_clean,
                                        'Density': density_clean
                                    })
                            except Exception as e:
                                continue
        
        return hotspots
        
    except Exception as e:
        print(f"    Error extracting data from {url}: {e}")
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

def process_material_complete(material_name):
    """Process a single material with comprehensive reference systems"""
    print(f"\\n{'='*60}")
    print(f"Gap-filling for {material_name}")
    print(f"{'='*60}")
    
    # Comprehensive reference systems within inhabited bubble
    reference_systems = [
        # Original systems
        "Sol", "Lave", "Alioth", "Merope", 
        "Witch%20Head%20Sector%20IR-W%20c1-9", "HIP%2022460",
        
        # Strategic bubble coverage
        "Paesia",           # Fix known missing data 
        "Deciat",           # Popular engineering hub
        "Shinrarta%20Dezhra", # Pilots Federation HQ
        "Maia",             # Pleiades region
        "Diaguandri",       # Ray Gateway hub
        "Jameson%20Memorial", # Elite pilots
        "Colonia",          # Secondary bubble
        "Jacques%20Station", # Colonia area
        "Sirius",           # Sirius Corp space
        "Wolf%20359",       # Close to Sol
        "LHS%203447",       # Starter area
        "Dromi",            # Starter area
        
        # Additional strategic coverage
        "Farseer%20Inc",    # Engineering
        "Tod%20The%20Blaster%20McQuinn", # Engineering
        "Elvira%20Martuuk", # Engineering  
        "The%20Dweller",    # Engineering
        "Lei%20Cheung",     # Engineering
        "Felicity%20Farseer", # Engineering
    ]
    
    print(f"Using {len(reference_systems)} comprehensive reference systems")
    print("(Full inhabited bubble coverage)")
    
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
        print(f"    Found: {len(hotspots)} total, {len(new_hotspots)} new, {len(hotspots)-len(new_hotspots)} existing")
        
        time.sleep(1.2)  # Respectful rate limiting
    
    print(f"\\nSummary for {material_name}:")
    print(f"  New systems found: {new_systems_found}")
    print(f"  Existing systems skipped: {existing_systems_skipped}")
    
    if all_hotspots:
        # Create DataFrame
        df = pd.DataFrame(all_hotspots)
        
        # Clean up data
        df['System'] = df['System'].str.strip()
        df['Ring'] = df['Ring'].str.strip()
        
        # Remove invalid entries
        df = df[df['System'].str.len() > 0]
        df = df[df['Ring'].str.len() > 0] 
        
        # Deduplicate
        before_dedup = len(df)
        df = df.drop_duplicates(subset=['System', 'Ring'], keep='first')
        after_dedup = len(df)
        removed = before_dedup - after_dedup
        
        print(f"  After cleanup: {after_dedup} unique records ({removed} duplicates removed)")
        
        if after_dedup > 0:
            # Create output directory
            output_dir = Path("app/data/Hotspots/gaps_complete")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Save as Excel file
            excel_file = output_dir / f"{material_name}_gaps_complete.xlsx"
            df.to_excel(excel_file, index=False)
            print(f"  Saved to: {excel_file}")
            
            return after_dedup, df['Hotspots'].sum()
        else:
            print(f"  No valid data to save")
            return 0, 0
    else:
        print(f"  No hotspots extracted")
        return 0, 0

def main():
    """Main function to run complete gap-filling extraction"""
    
    # All mining materials
    all_materials = [
        "Alexandrite", "Painite", "Platinum", "LowTemperatureDiamond", "Tritium",
        "Osmium", "Rhodplumsite", "Serendibite", "Monazite", "Musgravite", 
        "Bixbite", "Jadeite", "Opal"
    ]
    
    print("COMPLETE GAP-FILLING EXTRACTION")
    print(f"Materials: {len(all_materials)}")
    print(f"Strategy: Extract all missing hotspot data within inhabited bubble")
    print(f"Expected: Large number of new systems due to fixed parsing")
    
    summary = {}
    start_time = time.time()
    
    for i, material in enumerate(all_materials, 1):
        print(f"\\n[{i}/{len(all_materials)}] Processing {material}...")
        locations, total_hotspots = process_material_complete(material)
        summary[material] = {'new_locations': locations, 'hotspots': total_hotspots}
    
    # Final summary
    elapsed_time = time.time() - start_time
    print(f"\\n{'='*80}")
    print("COMPLETE GAP-FILLING EXTRACTION FINISHED!")
    print(f"{'='*80}")
    print(f"Time elapsed: {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)")
    
    print("\\nNEW DATA EXTRACTED:")
    print("-" * 60)
    total_new_locations = 0
    total_new_hotspots = 0
    
    for material, stats in summary.items():
        if stats['new_locations'] > 0:
            print(f"{material:20} {stats['new_locations']:4d} new systems, {stats['hotspots']:5d} hotspots")
            total_new_locations += stats['new_locations']
            total_new_hotspots += stats['hotspots']
        else:
            print(f"{material:20} [COMPLETE] No gaps found")
    
    print("-" * 60)
    print(f"{'GRAND TOTAL':20} {total_new_locations:4d} new systems, {total_new_hotspots:5d} hotspots")
    
    if total_new_locations > 0:
        print(f"\\nGap files saved in: app/data/Hotspots/gaps_complete/")
        print(f"Next step: Import gap data into user_data.db")
        print(f"Expected: Paesia Alexandrite data now available!")
    else:
        print(f"\\nUnexpected: No gaps found - this suggests an issue")
    
    print(f"\\nExtraction completed with fixed parsing logic")

if __name__ == "__main__":
    main()