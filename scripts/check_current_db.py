import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== CHECKING CURRENT USER DATABASE (After replacement) ===\n")

# Check ALL Paesia 2 rings
c.execute('''SELECT body_name, material_name, ring_type, density, ls_distance, hotspot_count, scan_date, coord_source
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name LIKE "%2%Ring%"
             ORDER BY body_name, material_name''')

results = c.fetchall()

if results:
    print(f"Found {len(results)} entries for Paesia 2 rings:\n")
    
    # Group by ring
    rings = {}
    for r in results:
        ring_name = r[0]
        if ring_name not in rings:
            rings[ring_name] = []
        rings[ring_name].append(r)
    
    for ring_name, entries in sorted(rings.items()):
        print("="*80)
        print(f"RING: {ring_name}")
        print("="*80)
        for r in entries:
            print(f"  Material: {r[1]:<20} | Type: {r[2]:<12} | Density: {str(r[3]):<12} | LS: {str(r[4]):<10}")
            print(f"    Count: {r[5]} | Date: {r[6]} | Source: {r[7]}")
        print()

# Check if 2 C Ring exists
print("\n" + "="*80)
print("SPECIFIC CHECK: 2 C RING")
print("="*80)

c.execute('''SELECT material_name, ring_type, ls_distance, scan_date, coord_source
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name = "2 C Ring"''')

c_ring = c.fetchall()
if c_ring:
    print(f"\nFOUND 2 C Ring with {len(c_ring)} materials:")
    for r in c_ring:
        print(f"  {r[0]} ({r[1]}) - LS: {r[2]} - Date: {r[3]} - Source: {r[4]}")
    print("\n>>> This is the PHANTOM ring that should NOT be scanned in-game!")
else:
    print("\nNo 2 C Ring found.")

conn.close()
