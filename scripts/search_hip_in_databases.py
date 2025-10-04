import sqlite3

print("=== SEARCHING DATABASE FOR HIP 109727 ===\n")

# Check active database
print("ACTIVE DATABASE (app/data/user_data.db):")
print("="*80)
conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()

c.execute('''SELECT system_name, body_name, material_name, ring_type, density, 
             ls_distance, hotspot_count, scan_date, coord_source
             FROM hotspot_data 
             WHERE system_name LIKE "%HIP 109727%"
             ORDER BY body_name, material_name''')

active_results = c.fetchall()
if active_results:
    print(f"\nFound {len(active_results)} entries:\n")
    for r in active_results:
        print(f"System: {r[0]}")
        print(f"Body: {r[1]}")
        print(f"Material: {r[2]}")
        print(f"Ring Type: {r[3]}")
        print(f"Density: {r[4]}")
        print(f"LS Distance: {r[5]}")
        print(f"Hotspot Count: {r[6]}")
        print(f"Scan Date: {r[7]}")
        print(f"Coord Source: {r[8]}")
        print("-"*80)
else:
    print("No entries found")

conn.close()

# Check default database
print("\n\nDEFAULT DATABASE (app/data/UserDb for install/user_data.db):")
print("="*80)
conn = sqlite3.connect('app/data/UserDb for install/user_data.db')
c = conn.cursor()

c.execute('''SELECT system_name, body_name, material_name, ring_type, density, 
             ls_distance, hotspot_count, scan_date
             FROM hotspot_data 
             WHERE system_name LIKE "%HIP 109727%"
             ORDER BY body_name, material_name''')

default_results = c.fetchall()
if default_results:
    print(f"\nFound {len(default_results)} entries:\n")
    for r in default_results:
        print(f"System: {r[0]}")
        print(f"Body: {r[1]}")
        print(f"Material: {r[2]}")
        print(f"Ring Type: {r[3]}")
        print(f"Density: {r[4]}")
        print(f"LS Distance: {r[5]}")
        print(f"Hotspot Count: {r[6]}")
        print(f"Scan Date: {r[7]}")
        print("-"*80)
else:
    print("No entries found")

conn.close()

print("\n\nCONCLUSION:")
print("="*80)
if active_results and not default_results:
    print("HIP 109727 is in ACTIVE database but NOT in DEFAULT database")
    print("→ Was added by external import (Excel) or old journal import")
elif active_results and default_results:
    print("HIP 109727 is in BOTH databases")
    print("→ Came from default pre-populated database")
elif not active_results:
    print("HIP 109727 is NOT in active database (search failed?)")
