#!/usr/bin/env python3
"""
EDTools.cc Hotspot Data Extractor
Extracts detailed hotspot information from EDTools.cc and creates Excel sheets
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import urllib.parse
import time
from pathlib import Path

def extract_hotspot_data(url):
    """Extract hotspot data from EDTools.cc hotspot page"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the reference system from the page
        reference_system = "Unknown"
        try:
            # Look for the reference system in the page content
            ref_text = soup.find(text=re.compile(r'Distances are from'))
            if ref_text:
                match = re.search(r'Distances are from (.+?)\s*\[', ref_text)
                if match:
                    reference_system = match.group(1).strip()
        except:
            pass
        
        # Extract table data
        hotspots = []
        
        # Look for table or structured data containing hotspot information
        # Try different selectors based on EDTools.cc structure
        
        # Method 1: Look for table rows
        tables = soup.find_all('table')
        if tables:
            for table in tables:
                rows = table.find_all('tr')
                for row in rows[1:]:  # Skip header
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 5:  # Distance, System, Ring Type, Hotspots, LS
                        try:
                            distance = cells[0].get_text(strip=True)
                            system = cells[1].get_text(strip=True)
                            ring_type = cells[2].get_text(strip=True)
                            hotspot_count = cells[3].get_text(strip=True)
                            ls_distance = cells[4].get_text(strip=True)
                            density = cells[5].get_text(strip=True) if len(cells) > 5 else "N/A"
                            
                            # Clean up the data
                            system = re.sub(r'\[.*?\]', '', system).strip()  # Remove clipboard links
                            distance = re.sub(r'[^\d.]', '', distance)
                            hotspot_count = re.sub(r'[^\d]', '', hotspot_count)
                            ls_distance = re.sub(r'[^\d.]', '', ls_distance)
                            
                            hotspots.append({
                                'Reference_System': reference_system,
                                'Distance_LY': float(distance) if distance else 0,
                                'System_Name': system,
                                'Ring_Type': ring_type,
                                'Hotspot_Count': int(hotspot_count) if hotspot_count else 0,
                                'LS_Distance': float(ls_distance) if ls_distance else 0,
                                'Density': density,
                                'Material': 'Alexandrite',
                                'Source_URL': url
                            })
                        except Exception as e:
                            print(f"Error parsing row: {e}")
                            continue
        
        # Method 2: Look for div-based structure (fallback)
        if not hotspots:
            # Try to find data in div structures or other HTML elements
            content_divs = soup.find_all('div', class_=re.compile(r'result|data|row'))
            # Implementation would depend on actual HTML structure
        
        print(f"Extracted {len(hotspots)} hotspots from {url}")
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
        hotspots = extract_hotspot_data(url)
        all_hotspots.extend(hotspots)
        time.sleep(1)  # Be respectful to the server
    
    if all_hotspots:
        # Create DataFrame
        df = pd.DataFrame(all_hotspots)
        
        # Remove duplicates based on system name and ring type
        df = df.drop_duplicates(subset=['System_Name', 'Ring_Type'])
        
        # Sort by distance and hotspot count
        df = df.sort_values(['Distance_LY', 'Hotspot_Count'], ascending=[True, False])
        
        # Create output directory
        output_dir = Path("app/data/hotspots")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel
        output_file = output_dir / "alexandrite_hotspots.xlsx"
        df.to_excel(output_file, index=False, sheet_name='Alexandrite_Hotspots')
        
        print(f"Created Excel file: {output_file}")
        print(f"Total unique hotspots: {len(df)}")
        
        # Display sample data
        print("\nSample data:")
        print(df.head(10).to_string(index=False))
        
    else:
        print("No hotspot data extracted. The page structure may have changed.")

if __name__ == "__main__":
    main()