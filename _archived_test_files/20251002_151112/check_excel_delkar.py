import pandas as pd

# Read the Excel file
excel_file = 'app/data/Hotspots/All_Materials_Combined_Corrected.xlsx'

try:
    # Get all sheet names first
    xl_file = pd.ExcelFile(excel_file)
    sheet_names = xl_file.sheet_names
    print(f"Found {len(sheet_names)} sheets in Excel file:")
    for i, sheet in enumerate(sheet_names):
        print(f"  {i+1}. {sheet}")
    
    print("\n" + "="*80)
    
    # Search all sheets for Delkar entries
    all_delkar_entries = []
    
    for sheet_name in sheet_names:
        print(f"\nChecking sheet: '{sheet_name}'")
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            print(f"  Columns: {list(df.columns)}")
            print(f"  Rows: {len(df)}")
            
            # Try to find Delkar entries (handle different column names)
            delkar_entries = None
            if 'System' in df.columns:
                delkar_entries = df[df['System'] == 'Delkar']
            elif 'system_name' in df.columns:
                delkar_entries = df[df['system_name'] == 'Delkar']
            elif 'SystemName' in df.columns:
                delkar_entries = df[df['SystemName'] == 'Delkar']
            
            if delkar_entries is not None and len(delkar_entries) > 0:
                print(f"  *** FOUND {len(delkar_entries)} Delkar entries in sheet '{sheet_name}' ***")
                
                # Look specifically for 7 A Ring entries
                for _, row in delkar_entries.iterrows():
                    # Check different possible column names for body/ring
                    body_ring = None
                    for col in ['Ring', 'Body', 'body_name', 'BodyName']:
                        if col in df.columns:
                            body_ring = str(row.get(col, '')).strip()
                            break
                    
                    if body_ring and '7 A' in body_ring:
                        print(f"    🎯 FOUND 7 A Ring entry!")
                        # Print all available data for this entry
                        for col in df.columns:
                            value = row.get(col, 'N/A')
                            print(f"      {col}: {value}")
                        print()
                        
                        all_delkar_entries.append({
                            'sheet': sheet_name,
                            'data': row.to_dict()
                        })
                    elif body_ring:
                        print(f"    Found other ring: {body_ring}")
            else:
                print(f"  No Delkar entries found in this sheet")
                
        except Exception as e:
            print(f"  Error reading sheet '{sheet_name}': {e}")
    
    print("\n" + "="*80)
    print(f"\nSUMMARY: Found {len(all_delkar_entries)} Delkar 7 A Ring entries across all sheets")
    
    if all_delkar_entries:
        print("\nDETAILS:")
        for i, entry in enumerate(all_delkar_entries):
            print(f"\nEntry {i+1} (from sheet '{entry['sheet']}'):")
            for key, value in entry['data'].items():
                print(f"  {key}: {value}")
    
except Exception as e:
    print(f"Error reading Excel file: {e}")