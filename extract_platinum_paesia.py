#!/usr/bin/env python3
"""
Quick Platinum extraction focused on finding Paesia records
"""

import requests
import pandas as pd
from bs4 import BeautifulSoup
import time
from pathlib import Path

def extract_platinum_from_paesia():
    """Extract Platinum data using Paesia as reference system"""
    url = 'https://edtools.cc/hotspot.php'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    print("="*60)
    print("PLATINUM EXTRACTION - PAESIA FOCUSED")
    print("="*60)
    print("Searching for Platinum hotspots using Paesia as reference...")
    
    params = {
        'system': 'Paesia',
        'bodytype': '',
        'material': 'Platinum',
        'distancely': 100  # 100 LY radius
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the results table
        table = soup.find('table')
        if not table:
            print("❌ No results table found")
            return []
        
        rows = table.find_all('tr')[1:]  # Skip header row
        print(f"Found {len(rows)} total records")
        
        results = []
        paesia_records = []
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 6:
                system = cells[0].get_text(strip=True)
                ring = cells[1].get_text(strip=True)
                hotspots = cells[2].get_text(strip=True)
                ring_type = cells[3].get_text(strip=True)
                ls_distance = cells[4].get_text(strip=True)
                density = cells[5].get_text(strip=True)
                
                record = {
                    'System': system,
                    'Ring': ring,
                    'Hotspots': hotspots,
                    'Type': ring_type,
                    'LS': ls_distance,
                    'Density': density
                }
                
                results.append(record)
                
                # Check for Paesia specifically
                if 'Paesia' in system:
                    paesia_records.append(record)
                    print(f"✅ PAESIA FOUND: {system} | {ring} | {hotspots} hotspots | {ring_type}")
        
        print(f"\nRESULTS:")
        print(f"  Total Platinum records: {len(results)}")
        print(f"  Paesia Platinum records: {len(paesia_records)}")
        
        if len(paesia_records) == 0:
            print("\n❌ NO PLATINUM HOTSPOTS FOUND IN PAESIA SYSTEM")
            print("This confirms that Paesia does not have Platinum hotspots in EDTools.cc database")
        else:
            print(f"\n✅ PAESIA PLATINUM HOTSPOTS CONFIRMED:")
            for record in paesia_records:
                print(f"  {record['System']} - Ring {record['Ring']} - {record['Hotspots']} hotspots")
        
        return results
        
    except Exception as e:
        print(f"❌ Error during extraction: {e}")
        return []

def main():
    results = extract_platinum_from_paesia()
    
    if results:
        # Save results for comparison
        df = pd.DataFrame(results)
        output_file = "app/data/Hotspots/platinum_paesia_test.xlsx"
        df.to_excel(output_file, index=False)
        print(f"\n💾 Results saved to: {output_file}")
        
        # Show first few records for verification
        print("\nFirst 5 records:")
        print(df.head().to_string())
    
    print("\n" + "="*60)
    print("EXTRACTION COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()