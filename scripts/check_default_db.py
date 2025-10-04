import sqlite3

db_path = 'app/data/UserDb for install/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== CHECKING DEFAULT DATABASE: UserDb for install/user_data.db ===\n")

# Check for Paesia 2 A Ring
c.execute('''SELECT material_name, ring_type, density, ls_distance, hotspot_count, scan_date
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name = "2 A Ring"
             ORDER BY material_name''')

results = c.fetchall()

if results:
    print(f"Found {len(results)} entries for Paesia 2 A Ring:\n")
    print(f"{'Material':<20} | {'Type':<12} | {'Density':<12} | {'LS':<10} | Count | Date")
    print("-" * 85)
    
    icy_count = 0
    metallic_count = 0
    
    for r in results:
        print(f"{r[0]:<20} | {str(r[1]):<12} | {str(r[2]):<12} | {str(r[3]):<10} | {r[4]:<5} | {r[5]}")
        if r[1] and 'Icy' in str(r[1]):
            icy_count += 1
        if r[1] and 'Metal' in str(r[1]):
            metallic_count += 1
    
    print(f"\nSUMMARY:")
    print(f"  Icy ring entries: {icy_count}")
    print(f"  Metallic ring entries: {metallic_count}")
    
    if icy_count > 0:
        print(f"\n❌ ISSUE CONFIRMED: Default database has {icy_count} incorrect Icy ring entries!")
        print("   These are from the phantom C Ring that was removed by Frontier.")
    else:
        print(f"\n✅ Default database is clean - no Icy ring entries found.")
        
else:
    print("No Paesia 2 A Ring entries found in default database.")

# Check for any 2 C Ring entries
print("\n\n=== CHECKING FOR PAESIA 2 C RING (Phantom Ring) ===\n")
c.execute('''SELECT body_name, material_name, ring_type, ls_distance, hotspot_count
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name LIKE "%2 C%"
             ORDER BY body_name, material_name''')

c_ring_results = c.fetchall()
if c_ring_results:
    print(f"Found {len(c_ring_results)} entries for Paesia 2 C Ring (phantom):")
    for r in c_ring_results:
        print(f"  {r[0]} - {r[1]} ({r[2]}) - LS:{r[3]}")
else:
    print("No Paesia 2 C Ring entries found (good!).")

conn.close()

print("\n" + "=" * 85)
print("RECOMMENDATION:")
if results and icy_count > 0:
    print("❌ Default database needs cleanup - delete Icy ring entries for Paesia 2 A Ring")
elif not results:
    print("⚠️  Default database has no Paesia data - may need to be populated")
else:
    print("✅ Default database is already clean!")
