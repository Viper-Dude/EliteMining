"""
Alexandrite Re-extraction Script
Re-extract Alexandrite hotspot data using the 43 URL method
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os

def get_alexandrite_urls():
    """Generate the 43 URLs for Alexandrite across 9 directional sectors"""
    material_name = "Alexandrite"
    urls = [
        # Southeast-Below direction
        f'https://edtools.cc/hotspot?s=Sol&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Chukchitan&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Col%2520285%2520Sector%2520HG-N%2520c7-25&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520WT-Z%2520c16-7&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520IY-P%2520d6-9&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252023759&m={material_name}&ms=1',
        
        # Northeast Direction
        f'https://edtools.cc/hotspot?s=Hyades%2520Sector%2520LY-P%2520b6-2%2520&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Col%2520285%2520Sector%2520VW-F%2520b26-2&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Wregoe%2520AO-X%2520c28-21&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Merope&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=IC%25204604%2520Sector%2520AV-Y%2520c10&m={material_name}&ms=1',
        
        # East Direction
        f'https://edtools.cc/hotspot?s=Sounti&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252025497&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520SX-D%2520b59-0&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520XR-H%2520d11-45&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520PI-X%2520b48-7&m={material_name}&ms=1',
        
        # South East Direction
        f'https://edtools.cc/hotspot?s=ICZ%2520DB-W%2520b2-5&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252025497&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520VA-C%2520b46-2&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%25209931&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520ZP-F%2520c27-15&m={material_name}&ms=1',
        
        # South Direction
        f'https://edtools.cc/hotspot?s=Awngtei%2520Ji&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%25204420&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520TL-T%2520b49-1&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%25203967&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=synuefe%2520SZ-H%2520c25-4&m={material_name}&ms=1',
        
        # Southwest Direction
        f'https://edtools.cc/hotspot?s=Psi-1%2520Aquarii%2520&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%2520116164&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefai%2520IT-K%2520c24-4&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefai%2520SI-T%2520b49-0&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Synuefe%2520MU-P%2520b50-0&m={material_name}&ms=1',
        
        # West Direction
        f'https://edtools.cc/hotspot?s=Atora&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HR%25208487&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%2520101839&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Wredguia%2520SJ-M%2520b48-7&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Wredguia%2520JC-D%2520d12-66&m={material_name}&ms=1',
        
        # Northwest Direction
        f'https://edtools.cc/hotspot?s=Manit&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252087815&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252065650&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252099387&m={material_name}&ms=1',
        
        # North Direction
        f'https://edtools.cc/hotspot?s=Suessi&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=HIP%252063405&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Melotte%2520111%2520AV%25201981&m={material_name}&ms=1'
    ]
    return urls

def clean_ring_name(ring_str):
    """Clean ring name properly - keep body identifiers"""
    if pd.isna(ring_str):
        return ring_str
    ring_str = str(ring_str)
    
    # Remove material contamination after 'Ring'
    if 'Ring' in ring_str:
        # Split at 'Ring' and take everything up to and including 'Ring'
        ring_part = ring_str.split('Ring')[0] + 'Ring'
        return ring_part.strip()
    
    # Fallback: take first reasonable part
    parts = ring_str.split()
    if len(parts) >= 3:
        return f'{parts[0]} {parts[1]} {parts[2]}'
    return ring_str

def remove_asterisks(text):
    """Remove asterisks from system names"""
    if pd.isna(text):
        return text
    return str(text).replace('*', '')

def clean_density(density_str):
    """Extract density value from complex density string"""
    if pd.isna(density_str):
        return density_str
    try:
        # Extract first number from density string
        numbers = re.findall(r'[\d.]+', str(density_str))
        if numbers:
            density = float(numbers[0])
            return round(density, 8)
        return density_str
    except:
        return density_str

def safe_float_convert(value):
    """Safely convert LS values to float"""
    try:
        # Remove commas from numbers like '2,279'
        clean_value = str(value).replace(',', '')
        return float(clean_value)
    except:
        return None

def extract_alexandrite():
    """Extract Alexandrite hotspot data using 43 URLs"""
    print(f"\n{'='*60}")
    print(f"RE-EXTRACTING: Alexandrite")
    print(f"{'='*60}")
    
    urls = get_alexandrite_urls()
    print(f"Processing {len(urls)} URLs...")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    all_data = []
    
    for i, url in enumerate(urls, 1):
        try:
            print(f"  URL {i:2d}/{len(urls)}: Processing...", end="")
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                table = soup.find('table')
                
                if table:
                    rows = table.find_all('tr')[1:]  # Skip header
                    row_count = 0
                    
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 7:  # Ensure we have all columns
                            # CORRECTED COLUMN MAPPING:
                            distance = cols[0].get_text(strip=True)      # Distance (not used)
                            system = cols[1].get_text(strip=True)        # System
                            ring = cols[2].get_text(strip=True)          # Ring (contaminated)
                            ring_type = cols[3].get_text(strip=True)     # Type
                            hotspots = cols[4].get_text(strip=True)      # Hotspots
                            ls_distance = cols[5].get_text(strip=True)   # LS (CORRECTED!)
                            density = cols[6].get_text(strip=True)       # Density
                            
                            all_data.append([system, ls_distance, ring, hotspots, ring_type, density])
                            row_count += 1
                    
                    print(f" {row_count} records")
                else:
                    print(" No table found")
            else:
                print(f" HTTP {response.status_code}")
                
            time.sleep(2)  # Rate limiting
            
        except Exception as e:
            print(f" ERROR: {str(e)}")
            continue
    
    print(f"\nRaw Alexandrite records: {len(all_data)}")
    
    # Create DataFrame and apply cleaning
    df = pd.DataFrame(all_data, columns=['System', 'LS', 'Ring', 'Hotspots', 'Type', 'Density'])
    
    # Apply cleaning functions
    df['System'] = df['System'].apply(remove_asterisks)
    df['Ring'] = df['Ring'].apply(clean_ring_name)
    df['Density'] = df['Density'].apply(clean_density)
    
    # Remove invalid records
    df = df.dropna(subset=['System', 'LS', 'Ring'])
    df['LS_numeric'] = df['LS'].apply(safe_float_convert)
    df = df.dropna(subset=['LS_numeric'])
    df = df.drop('LS_numeric', axis=1)
    
    # Remove duplicates
    df_cleaned = df.drop_duplicates(subset=['System', 'Ring', 'LS'], keep='first')
    
    # Save to file
    output_file = f'app/data/Hotspots/Alexandrite_extracted_corrected_NEW.xlsx'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df_cleaned.to_excel(output_file, index=False)
    
    print(f"Cleaned Alexandrite records: {len(df_cleaned)}")
    print(f"Removed {len(df) - len(df_cleaned)} invalid/duplicate records")
    print(f"Saved to: {output_file}")
    
    # Show sample data
    if len(df_cleaned) > 0:
        print("\nSample cleaned data:")
        print(df_cleaned.head(5).to_string(index=False))
    
    return len(df_cleaned)

def main():
    """Main extraction process"""
    print("ALEXANDRITE RE-EXTRACTION")
    print("=========================")
    print("This will re-extract Alexandrite using the 43 URL method")
    print("Output: Alexandrite_extracted_corrected_NEW.xlsx")
    
    input("\nPress ENTER to start extraction...")
    
    try:
        record_count = extract_alexandrite()
        print(f"\n✅ Alexandrite extraction completed: {record_count:,} records")
        print(f"Saved to: app/data/Hotspots/Alexandrite_extracted_corrected_NEW.xlsx")
        
    except Exception as e:
        print(f"\n❌ ERROR extracting Alexandrite: {e}")

if __name__ == "__main__":
    main()