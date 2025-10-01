import pandas as pd

# Load the Excel file
excel_file = 'app/data/Hotspots/All_Materials_Combined_Corrected.xlsx'

try:
    excel_data = pd.ExcelFile(excel_file)
    
    print(f'Sheets in {excel_file}:')
    for sheet in excel_data.sheet_names:
        print(f'  - {sheet}')
    
    print('\nSearching for "Coalsack Sector RI-T c3-22" in all sheets...')
    print('=' * 80)
    
    found_any = False
    for sheet_name in excel_data.sheet_names:
        try:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            
            # Search for the system in all string columns
            matches = []
            for col in df.columns:
                if df[col].dtype == 'object':  # String columns
                    mask = df[col].astype(str).str.contains('RI-T c3-22', case=False, na=False)
                    if mask.any():
                        matching_rows = df[mask]
                        matches.extend(matching_rows.index.tolist())
            
            if matches:
                found_any = True
                print(f'\nFOUND in sheet "{sheet_name}":')
                unique_matches = list(set(matches))
                for idx in unique_matches[:10]:  # Show first 10 matches
                    row = df.iloc[idx]
                    system = row.get('System', row.get('system', 'N/A'))
                    ring = row.get('Ring', row.get('ring', row.get('Body', 'N/A')))
                    material = row.get('Material', row.get('material', 'N/A'))
                    print(f'  Row {idx}: {system} | {ring} | {material}')
        except Exception as e:
            print(f'Error reading sheet {sheet_name}: {e}')
    
    if not found_any:
        print('\nNO MATCHES FOUND for "RI-T c3-22" in any sheet.')

except FileNotFoundError:
    print(f'Excel file "{excel_file}" not found in current directory.')
except Exception as e:
    print(f'Error: {e}')