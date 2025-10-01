#!/usr/bin/env python3
"""
Priority Materials Gap Extraction - Test run with corrected parsing
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

def main():
    """Quick test extraction for priority materials"""
    
    priority_materials = ["Alexandrite", "Painite", "LowTemperatureDiamond"]
    
    # Focus on key systems that should have missing data
    key_systems = [
        "Paesia", "Deciat", "Sol", "Colonia",
        "Shinrarta%20Dezhra", "Maia"
    ]
    
    print("PRIORITY MATERIALS GAP EXTRACTION (QUICK TEST)")
    print(f"Materials: {priority_materials}")
    print(f"Reference systems: {len(key_systems)}")
    
    total_summary = {}
    
    for material in priority_materials:
        print(f"\n--- Processing {material} ---")
        
        all_hotspots = []
        new_found = 0
        existing_skipped = 0
        
        for i, system in enumerate(key_systems, 1):
            url = f"https://edtools.cc/hotspot?s={system}&m={material}&ms=1"
            print(f"[{i}/{len(key_systems)}] {system.replace('%20', ' ')}: ", end="")
            
            hotspots = extract_hotspot_data(url, material)
            
            new_hotspots = []
            for hotspot in hotspots:
                if not check_existing_system(hotspot['System'], material):
                    new_hotspots.append(hotspot)
                    new_found += 1
                else:
                    existing_skipped += 1
            
            all_hotspots.extend(new_hotspots)
            print(f"{len(hotspots)} total, {len(new_hotspots)} new")
            
            time.sleep(1.0)
        
        # Save results
        if all_hotspots:
            df = pd.DataFrame(all_hotspots)
            df = df.drop_duplicates(subset=['System', 'Ring'], keep='first')
            
            output_dir = Path("app/data/Hotspots/priority_gaps")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            excel_file = output_dir / f"{material}_priority_gaps.xlsx"
            df.to_excel(excel_file, index=False)
            
            # Check for Paesia specifically
            paesia_count = len(df[df['System'] == 'Paesia'])
            
            total_summary[material] = {
                'new_systems': len(df),
                'total_hotspots': df['Hotspots'].sum(),
                'paesia_rings': paesia_count,
                'file': excel_file
            }
            
            print(f"  RESULT: {len(df)} new systems, {df['Hotspots'].sum()} hotspots")
            if paesia_count > 0:
                print(f"  SUCCESS: Found {paesia_count} Paesia rings!")
            print(f"  Saved: {excel_file}")
        else:
            total_summary[material] = {'new_systems': 0, 'total_hotspots': 0, 'paesia_rings': 0}
            print(f"  RESULT: No new data")
    
    print(f"\n{'='*60}")
    print("PRIORITY EXTRACTION SUMMARY")
    print(f"{'='*60}")
    
    grand_total_systems = 0
    grand_total_hotspots = 0
    
    for material, stats in total_summary.items():
        print(f"{material:20} {stats['new_systems']:4d} systems, {stats['total_hotspots']:5d} hotspots")
        if stats['paesia_rings'] > 0:
            print(f"{'':20} --> Paesia data found!")
        grand_total_systems += stats['new_systems']
        grand_total_hotspots += stats['total_hotspots']
    
    print("-" * 60)
    print(f"{'TOTAL':20} {grand_total_systems:4d} systems, {grand_total_hotspots:5d} hotspots")
    
    if grand_total_systems > 0:
        print(f"\nSUCCESS: Extraction working with fixed parsing!")
        print(f"Files saved in: app/data/Hotspots/priority_gaps/")
    else:
        print(f"\nISSUE: Still no data extracted - need further debugging")

if __name__ == "__main__":
    main()