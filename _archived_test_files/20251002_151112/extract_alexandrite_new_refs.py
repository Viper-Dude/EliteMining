"""
Alexandrite Extraction - New Reference Systems
Extract Alexandrite using Macua and Paesia reference systems only
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os

def get_alexandrite_new_urls():
    """Generate URLs for Alexandrite using new reference systems"""
    material_name = "Alexandrite"
    urls = [
        f'https://edtools.cc/hotspot?s=Paesia&m={material_name}&ms=1',
        f'https://edtools.cc/hotspot?s=Macua&m={material_name}&ms=1'
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

def extract_alexandrite_new_refs():
    """Extract Alexandrite hotspot data using new reference systems"""
    print(f"\n{'='*60}")
    print(f"ALEXANDRITE EXTRACTION - NEW REFERENCE SYSTEMS")
    print(f"{'='*60}")
    
    urls = get_alexandrite_new_urls()
    print(f"Using reference systems: Paesia, Macua")
    print(f"Processing {len(urls)} URLs...")
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    all_data = []
    
    for i, url in enumerate(urls, 1):
        ref_system = "Paesia" if "Paesia" in url else "Macua"
        try:
            print(f"  URL {i:2d}/{len(urls)}: {ref_system} - Processing...", end="")
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
    output_file = f'app/data/Hotspots/Alexandrite_extracted_NEW_REFS.xlsx'
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df_cleaned.to_excel(output_file, index=False)
    
    print(f"Cleaned Alexandrite records: {len(df_cleaned)}")
    print(f"Removed {len(df) - len(df_cleaned)} invalid/duplicate records")
    print(f"Saved to: {output_file}")
    
    # Show sample data
    if len(df_cleaned) > 0:
        print("\nSample cleaned data:")
        print(df_cleaned.head(5).to_string(index=False))
        
        # Show unique systems count
        print(f"\nUnique systems found: {df_cleaned['System'].nunique()}")
        print(f"Ring type distribution: {dict(df_cleaned['Type'].value_counts())}")
    
    return len(df_cleaned)

def main():
    """Main extraction process"""
    print("ALEXANDRITE EXTRACTION - NEW REFERENCE SYSTEMS")
    print("=" * 50)
    print("Using new reference systems:")
    print("- Paesia")
    print("- Macua")
    print("\nOutput: Alexandrite_extracted_NEW_REFS.xlsx")
    
    input("\nPress ENTER to start extraction...")
    
    try:
        record_count = extract_alexandrite_new_refs()
        print(f"\n✅ Alexandrite extraction completed: {record_count:,} records")
        print(f"Saved to: app/data/Hotspots/Alexandrite_extracted_NEW_REFS.xlsx")
        
    except Exception as e:
        print(f"\n❌ ERROR extracting Alexandrite: {e}")

if __name__ == "__main__":
    main()