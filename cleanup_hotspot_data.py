import pandas as pd
import re

def cleanup_hotspot_data(file_path):
    """
    Clean up hotspot data extracted from EDTools.cc
    """
    # Read the data
    df = pd.read_excel(file_path)
    
    original_count = len(df)
    print(f"Original records: {original_count}")
    
    # 1. Remove asterisks from system names
    df['System'] = df['System'].str.replace('*', '', regex=False)
    
    # 2. Clean LS column - keep only numeric values
    df['LS'] = df['LS'].astype(str).str.replace(r'[^\d.]', '', regex=True)
    df = df[df['LS'] != '']
    
    # 3. Clean Density column - remove "outer/inner" text, keep only numbers
    df['Density'] = df['Density'].astype(str)
    df['Density'] = df['Density'].str.replace(r'(outer|inner)\s*', '', regex=True, flags=re.IGNORECASE)
    df['Density'] = df['Density'].str.replace(r'[^\d.]', '', regex=True)
    
    # 4. Round density to 8 decimal places
    df['Density'] = pd.to_numeric(df['Density'], errors='coerce')
    df['Density'] = df['Density'].round(8)
    
    # 5. Clean ring names - extract only ring identifier
    def clean_ring_name(ring_str):
        pattern = r'(\w+\s*\w*\s*Ring)'
        match = re.search(pattern, str(ring_str))
        if match:
            return match.group(1).strip()
        return str(ring_str).strip()
    
    df['Ring'] = df['Ring'].apply(clean_ring_name)
    
    # 6. Remove empty/invalid rows
    df = df[df['System'].notna()]
    df = df[df['System'].str.strip() != '']
    df = df[df['Ring'].notna()]
    df = df[df['Hotspots'].notna()]
    df = df[df['Type'].notna()]
    
    # 7. Remove duplicates
    df = df.drop_duplicates(subset=['System', 'Ring'])
    
    # 8. Trim whitespace from all text columns
    df['System'] = df['System'].str.strip()
    df['Ring'] = df['Ring'].str.strip()
    df['Type'] = df['Type'].str.strip()
    
    # 9. Sort by system name
    df = df.sort_values('System')
    
    # Save cleaned data
    df.to_excel(file_path, sheet_name='Platinum', index=False)
    
    cleaned_count = len(df)
    print(f"Cleaned records: {cleaned_count}")
    print(f"Removed {original_count - cleaned_count} invalid/duplicate records")
    
    return cleaned_count

if __name__ == "__main__":
    # Test with Platinum file
    file_path = "app/data/hotspots/Platinum_extracted.xlsx"
    cleanup_hotspot_data(file_path)
    print("Cleanup completed!")