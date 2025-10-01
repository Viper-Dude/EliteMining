#!/usr/bin/env python3
"""
CORRECTED EXTRACTION - All Materials with Proper EDTools.cc URLs
Overwrites existing files in all_materials_gaps folder
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
from pathlib import Path
import os

def fetch_material_data(system, material):
    """Fetch material data from EDTools.cc using CORRECT URL format"""
    base_url = "https://edtools.cc/hotspot"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    params = {
        's': system,     # s = system
        'm': material,   # m = material  
        'ms': 1         # ms = material search flag
    }
    
    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching {material} from {system}: {e}")
        return None

def parse_hotspot_table(html_content):
    """Parse the hotspot table from EDTools.cc HTML"""
    if not html_content:
        return []
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find the table with hotspot data
    table = soup.find('table')
    if not table:
        return []
    
    # Get all rows except header
    rows = table.find_all('tr')[1:]
    
    hotspots = []
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 6:  # Ensure we have enough columns
            try:
                system = cells[0].get_text(strip=True)
                ring = cells[1].get_text(strip=True) 
                hotspots_count = cells[2].get_text(strip=True)
                ring_type = cells[3].get_text(strip=True)
                ls_distance = cells[4].get_text(strip=True)
                density = cells[5].get_text(strip=True)
                
                # Skip empty or invalid entries
                if not system or system.lower() in ['', 'system']:
                    continue
                
                hotspots.append({
                    'System': system,
                    'Ring': ring,
                    'Hotspots': hotspots_count,
                    'Type': ring_type,
                    'LS': ls_distance,
                    'Density': density
                })
                
            except Exception as e:
                print(f"Error parsing row: {e}")
                continue
    
    return hotspots

def process_material_corrected(material):
    """Process one material with proper URLs"""
    
    # Reference systems for comprehensive coverage
    reference_systems = [
        'Sol', 'Lave', 'Alioth', 'Merope', 'Witch Head Sector IR-W c1-9',
        'HIP 22460', 'Paesia', 'Deciat', 'Shinrarta Dezhra', 'Maia',
        'Diaguandri', 'Jameson Memorial', 'Colonia', 'Jacques Station',
        'Sirius', 'Wolf 359', 'LHS 3447', 'Dromi'  # Reduced for faster processing
    ]
    
    print(f"Processing {material} using {len(reference_systems)} reference systems")
    
    all_hotspots = []
    existing_systems = set()
    
    for i, system in enumerate(reference_systems, 1):
        print(f"[{i:2d}/{len(reference_systems)}] {system:25} : ", end='', flush=True)
        
        html = fetch_material_data(system, material)
        if html:
            hotspots = parse_hotspot_table(html)
            
            new_count = 0
            for hotspot in hotspots:
                system_key = f"{hotspot['System']}_{hotspot['Ring']}"
                if system_key not in existing_systems:
                    all_hotspots.append(hotspot)
                    existing_systems.add(system_key)
                    new_count += 1
                    
                    # Check for Paesia specifically
                    if 'Paesia' in hotspot['System']:
                        print(f"\n    ✅ PAESIA: {hotspot['System']} - {hotspot['Ring']} - {hotspot['Hotspots']} hotspots", end='')
            
            print(f"{len(hotspots):3d} total, {new_count:3d} new")
        else:
            print("  0 total,   0 new")
        
        time.sleep(0.5)  # Be respectful to the server
    
    return all_hotspots

def main():
    """Extract all materials with corrected URLs"""
    
    # Valid materials from ring finder dropdown
    materials = [
        'Alexandrite', 'Benitoite', 'Bromellite', 'Grandidierite',
        'LowTemperatureDiamond', 'Monazite', 'Musgravite', 'Opal', 
        'Painite', 'Platinum', 'Rhodplumsite', 'Serendibite', 'Tritium'
    ]
    
    print("="*70)
    print("CORRECTED EXTRACTION - ALL MATERIALS")
    print("="*70)
    print("Using proper EDTools.cc URLs: https://edtools.cc/hotspot?s=System&m=Material&ms=1")
    print(f"Extracting {len(materials)} materials, overwriting existing gap files")
    print("="*70)
    
    output_dir = Path("app/data/Hotspots/all_materials_gaps")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    for i, material in enumerate(materials, 1):
        print(f"\n[{i:2d}/{len(materials)}] Starting {material}...")
        print("="*50)
        
        try:
            hotspots = process_material_corrected(material)
            
            if hotspots:
                df = pd.DataFrame(hotspots)
                
                # Use consistent naming - overwrite existing files
                output_file = output_dir / f"{material}_complete_gaps.xlsx"
                df.to_excel(output_file, index=False)
                
                unique_systems = len(set(h['System'] for h in hotspots))
                paesia_count = sum(1 for h in hotspots if 'Paesia' in h['System'])
                
                print(f"\nSummary for {material}:")
                print(f"  Total records: {len(hotspots)}")
                print(f"  Unique systems: {unique_systems}")
                print(f"  Paesia records: {paesia_count}")
                print(f"  Saved: {output_file}")
                
                if paesia_count > 0:
                    print(f"  🎯 PAESIA FOUND IN {material}!")
            else:
                print(f"\nNo data found for {material}")
                
        except Exception as e:
            print(f"\nERROR processing {material}: {e}")
            continue
    
    print("\n" + "="*70)
    print("CORRECTED EXTRACTION COMPLETE")
    print("="*70)
    print("All files saved to: app/data/Hotspots/all_materials_gaps/")
    print("Ready for merge process with corrected data")

if __name__ == "__main__":
    main()