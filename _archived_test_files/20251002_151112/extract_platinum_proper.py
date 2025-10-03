#!/usr/bin/env python3
"""
Extract just Platinum using the proven methodology from extract_remaining_corrected.py
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
from pathlib import Path

# Copy the working extraction logic
def fetch_material_data(system, material, distance=100):
    """Fetch material data from EDTools.cc using correct URL format"""
    base_url = "https://edtools.cc/hotspot"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    params = {
        's': system,        # s = system
        'm': material,      # m = material  
        'ms': 1            # ms = material search flag
    }
    
    try:
        response = requests.get(base_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def parse_hotspot_table(html_content):
    """Parse the hotspot table from EDTools.cc HTML"""
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

def extract_platinum():
    """Extract Platinum using the proven reference systems methodology"""
    
    # Use the same reference systems that worked for other materials
    reference_systems = [
        'Sol', 'Lave', 'Alioth', 'Merope', 'Witch Head Sector IR-W c1-9',
        'HIP 22460', 'Paesia', 'Deciat', 'Shinrarta Dezhra', 'Maia',
        'Diaguandri', 'Jameson Memorial', 'Colonia', 'Jacques Station',
        'Sirius', 'Wolf 359', 'LHS 3447', 'Dromi', 'Farseer Inc',
        'Tod McQuinn', 'Elvira Martuuk', 'The Dweller', 'Lei Cheung',
        'Felicity Farseer', 'Liz Ryder', 'Hera Tani', 'Juri Ishmaak',
        'Founders World', 'LHS 215', 'Beta Hydri', 'Procyon', 'Tau Ceti',
        'Epsilon Eridani', 'Vega', 'Altair'
    ]
    
    print("="*60)
    print("PLATINUM RE-EXTRACTION")
    print("="*60)
    print(f"Processing Platinum using {len(reference_systems)} reference systems")
    
    all_hotspots = []
    existing_systems = set()
    
    for i, system in enumerate(reference_systems, 1):
        print(f"[{i:2d}/{len(reference_systems)}] {system:25} : ", end='', flush=True)
        
        html = fetch_material_data(system, 'Platinum')
        if html:
            hotspots = parse_hotspot_table(html)
            
            new_count = 0
            for hotspot in hotspots:
                system_key = f"{hotspot['System']}_{hotspot['Ring']}"
                if system_key not in existing_systems:
                    all_hotspots.append(hotspot)
                    existing_systems.add(system_key)
                    new_count += 1
            
            print(f"{len(hotspots):3d} total, {new_count:3d} new")
            
            # Check for Paesia specifically
            paesia_records = [h for h in hotspots if 'Paesia' in h['System']]
            if paesia_records:
                print(f"    ✅ PAESIA FOUND: {len(paesia_records)} records!")
                for p in paesia_records:
                    print(f"       {p['System']} - {p['Ring']} - {p['Hotspots']} hotspots")
        else:
            print("  0 total,   0 new")
        
        time.sleep(1.0)  # Be respectful to the server
    
    print(f"\nSummary for Platinum:")
    print(f"  New systems found: {len(all_hotspots)}")
    print(f"  Final result: {len(set(h['System'] for h in all_hotspots))} unique systems, {len(all_hotspots)} hotspots")
    
    # Save results
    if all_hotspots:
        df = pd.DataFrame(all_hotspots)
        output_file = "app/data/Hotspots/platinum_reextracted.xlsx"
        df.to_excel(output_file, index=False)
        print(f"  Saved: {output_file}")
        
        # Check for Paesia in final results
        paesia_final = df[df['System'].str.contains('Paesia', case=False, na=False)]
        print(f"\n  PAESIA CHECK: {len(paesia_final)} Paesia records in final results")
        if len(paesia_final) > 0:
            print("  Paesia records:")
            for _, row in paesia_final.iterrows():
                print(f"    {row['System']} - {row['Ring']} - {row['Hotspots']} hotspots")
    
    return all_hotspots

if __name__ == "__main__":
    results = extract_platinum()
    print("\n" + "="*60)
    print("RE-EXTRACTION COMPLETE")
    print("="*60)