#!/usr/bin/env python3
"""
Complete All Materials Gap Extraction
Extract missing data for ALL 13 mining materials using fixed parsing
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
        
        tables = soup.find_all('table')
        if tables:
            for table in tables:
                rows = table.find_all('tr')
                
                # Find header row
                header_row = None
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 6:
                        headers = [cell.get_text(strip=True) for cell in cells]
                        if 'Distance' in headers and 'System' in headers:
                            header_row = headers
                            break
                
                if header_row:
                    for row in rows[1:]:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 6:
                            try:
                                distance = cells[0].get_text(strip=True)
                                system_raw = cells[1].get_text(strip=True) 
                                ring_raw = cells[2].get_text(strip=True)
                                ring_type = cells[3].get_text(strip=True)
                                material_hotspots = cells[4].get_text(strip=True)
                                ls_distance = cells[5].get_text(strip=True)
                                density = cells[6].get_text(strip=True) if len(cells) > 6 else "N/A"
                                
                                # Clean system name
                                system_name = re.sub(r'\[.*?\]', '', system_raw).strip()
                                system_name = system_name.replace('*', '').strip()
                                
                                # Extract ring name
                                ring_name = ""
                                ring_match = re.match(r'^([^A-Z]*[A-Z][^:]*)', ring_raw)
                                if ring_match:
                                    ring_name = ring_match.group(1).strip()
                                    ring_name = re.sub(r'\s*Ring.*$', '', ring_name)
                                    if not ring_name:
                                        ring_name = ring_raw.split('Ring')[0] if 'Ring' in ring_raw else ring_raw[:10]
                                
                                # Parse material count
                                material_count = 0
                                try:
                                    material_count = int(material_hotspots)
                                except:
                                    pattern = f"{material}:(\\d+)"
                                    match = re.search(pattern, ring_raw)
                                    if match:
                                        material_count = int(match.group(1))
                                
                                # Clean LS distance
                                ls_clean = "N/A"
                                if ls_distance and ls_distance != '-':
                                    ls_match = re.search(r'(\d+(?:,\d+)*)', ls_distance.replace(',', ''))
                                    if ls_match:
                                        ls_clean = float(ls_match.group(1))
                                
                                # Clean density
                                density_clean = "N/A"
                                if density and density != '-':
                                    density_match = re.search(r'(\d+(?:\.\d+)?)', density)
                                    if density_match:
                                        density_clean = float(density_match.group(1))
                                
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
        print(f"    Error: {e}")
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
    print(f"\n{'='*60}")
    print(f"Processing {material_name}")
    print(f"{'='*60}")
    
    # Strategic reference systems covering inhabited bubble
    reference_systems = [
        # Core bubble systems
        "Sol", "Lave", "Alioth", "Merope", 
        "Witch%20Head%20Sector%20IR-W%20c1-9", "HIP%2022460",
        
        # Strategic bubble coverage
        "Paesia", "Deciat", "Shinrarta%20Dezhra", "Maia",
        "Diaguandri", "Jameson%20Memorial", "Colonia", "Jacques%20Station",
        "Sirius", "Wolf%20359", "LHS%203447", "Dromi",
        
        # Engineering hub systems (likely to have mining nearby)
        "Farseer%20Inc", "Tod%20McQuinn", "Elvira%20Martuuk", 
        "The%20Dweller", "Lei%20Cheung", "Felicity%20Farseer",
        "Liz%20Ryder", "Hera%20Tani", "Juri%20Ishmaak",
        
        # Additional strategic points
        "Founders%20World", "LHS%20215", "Beta%20Hydri", "Procyon",
        "Tau%20Ceti", "Epsilon%20Eridani", "Vega", "Altair"
    ]
    
    print(f"Using {len(reference_systems)} reference systems (comprehensive bubble coverage)")
    
    all_hotspots = []
    new_found = 0
    existing_skipped = 0
    
    for i, system in enumerate(reference_systems, 1):
        url = f"https://edtools.cc/hotspot?s={system}&m={material_name}&ms=1"
        print(f"[{i:2d}/{len(reference_systems)}] {system.replace('%20', ' '):<25}: ", end="", flush=True)
        
        hotspots = extract_hotspot_data(url, material_name)
        
        new_hotspots = []
        for hotspot in hotspots:
            if not check_existing_system(hotspot['System'], material_name):
                new_hotspots.append(hotspot)
                new_found += 1
            else:
                existing_skipped += 1
        
        all_hotspots.extend(new_hotspots)
        print(f"{len(hotspots):3d} total, {len(new_hotspots):3d} new")
        
        time.sleep(1.0)  # Be respectful to the server
    
    print(f"\nSummary for {material_name}:")
    print(f"  New systems found: {new_found}")
    print(f"  Existing systems skipped: {existing_skipped}")
    
    if all_hotspots:
        df = pd.DataFrame(all_hotspots)
        df = df.drop_duplicates(subset=['System', 'Ring'], keep='first')
        
        output_dir = Path("app/data/Hotspots/all_materials_gaps")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        excel_file = output_dir / f"{material_name}_complete_gaps.xlsx"
        df.to_excel(excel_file, index=False)
        
        print(f"  Final result: {len(df)} unique systems, {df['Hotspots'].sum()} hotspots")
        print(f"  Saved: {excel_file}")
        
        return len(df), df['Hotspots'].sum()
    else:
        print(f"  No new data found")
        return 0, 0

def main():
    """Extract gap data for ALL mining materials"""
    
    # ALL 14 mining materials (including Bromellite as requested)
    all_materials = [
        "Alexandrite", "Painite", "Platinum", "LowTemperatureDiamond", "Tritium",
        "Osmium", "Rhodplumsite", "Serendibite", "Monazite", "Musgravite", 
        "Bixbite", "Jadeite", "Opal", "Bromellite"
    ]
    
    print("COMPLETE ALL-MATERIALS GAP EXTRACTION")
    print(f"Materials: {len(all_materials)} total")
    print("Strategy: Comprehensive inhabited bubble coverage with fixed parsing")
    print(f"Expected: Significant new data for most materials")
    
    summary = {}
    start_time = time.time()
    
    for i, material in enumerate(all_materials, 1):
        print(f"\n[{i:2d}/{len(all_materials)}] Starting {material}...")
        locations, hotspots = process_material_complete(material)
        summary[material] = {'systems': locations, 'hotspots': hotspots}
    
    # Final comprehensive summary
    elapsed_time = time.time() - start_time
    print(f"\n{'='*80}")
    print("ALL-MATERIALS GAP EXTRACTION COMPLETE!")
    print(f"{'='*80}")
    print(f"Time elapsed: {elapsed_time:.1f} seconds ({elapsed_time/60:.1f} minutes)")
    
    print(f"\nCOMPLETE RESULTS:")
    print("-" * 70)
    
    total_systems = 0
    total_hotspots = 0
    materials_with_gaps = 0
    
    for material, stats in summary.items():
        if stats['systems'] > 0:
            print(f"{material:20} {stats['systems']:4d} new systems, {stats['hotspots']:5d} hotspots")
            total_systems += stats['systems']
            total_hotspots += stats['hotspots']
            materials_with_gaps += 1
        else:
            print(f"{material:20} [COMPLETE] No gaps found")
    
    print("-" * 70)
    print(f"{'GRAND TOTAL':20} {total_systems:4d} new systems, {total_hotspots:5d} hotspots")
    print(f"Materials with gaps: {materials_with_gaps}/{len(all_materials)}")
    
    if total_systems > 0:
        print(f"\nSUCCESS! Gap files saved in: app/data/Hotspots/all_materials_gaps/")
        print(f"Next step: Import all gap data into user_data.db")
        
        # Special callout for user-requested materials
        if 'Bromellite' in summary and summary['Bromellite']['systems'] > 0:
            print(f"✓ Bromellite: {summary['Bromellite']['systems']} systems, {summary['Bromellite']['hotspots']} hotspots")
        if 'Painite' in summary and summary['Painite']['systems'] > 0:
            print(f"✓ Painite: {summary['Painite']['systems']} systems, {summary['Painite']['hotspots']} hotspots")
    else:
        print(f"\nUnexpected: No gaps found across all materials")
    
    print(f"\nDatabase now ready for comprehensive mining coverage!")

if __name__ == "__main__":
    main()