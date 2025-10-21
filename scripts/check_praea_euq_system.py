import sqlite3

db_path = 'app/data/galaxy_systems.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

system_name = "Praea Euq JF-Q b5-4"

print(f"=== CHECKING GALAXY DATABASE FOR: {system_name} ===\n")

# Check systems table
print("="*80)
print("SYSTEMS TABLE")
print("="*80)
c.execute('''SELECT * FROM systems WHERE name LIKE ?''', (f'%{system_name}%',))
system_results = c.fetchall()

if system_results:
    print(f"\nFound {len(system_results)} system(s):\n")
    # Get column names
    c.execute("PRAGMA table_info(systems)")
    columns = [col[1] for col in c.fetchall()]
    
    for row in system_results:
        for col, val in zip(columns, row):
            print(f"  {col}: {val}")
        print()
else:
    print(f"❌ No system found matching '{system_name}'\n")

# Check rings table
print("="*80)
print("RINGS TABLE (if exists)")
print("="*80)
try:
    c.execute('''SELECT * FROM rings WHERE system_name LIKE ?''', (f'%{system_name}%',))
    ring_results = c.fetchall()
    
    if ring_results:
        print(f"\nFound {len(ring_results)} ring(s):\n")
        # Get column names
        c.execute("PRAGMA table_info(rings)")
        columns = [col[1] for col in c.fetchall()]
        
        for row in ring_results:
            print("-" * 80)
            for col, val in zip(columns, row):
                print(f"  {col}: {val}")
            print()
    else:
        print(f"❌ No rings found for system '{system_name}'\n")
except sqlite3.OperationalError as e:
    print(f"⚠️ Rings table doesn't exist in galaxy_systems.db: {e}\n")

# Check hotspots table (if it exists)
print("="*80)
print("HOTSPOTS TABLE")
print("="*80)
try:
    c.execute('''SELECT * FROM hotspots WHERE system_name LIKE ?''', (f'%{system_name}%',))
    hotspot_results = c.fetchall()
    
    if hotspot_results:
        print(f"\nFound {len(hotspot_results)} hotspot(s):\n")
        # Get column names
        c.execute("PRAGMA table_info(hotspots)")
        columns = [col[1] for col in c.fetchall()]
        
        for row in hotspot_results:
            print("-" * 80)
            for col, val in zip(columns, row):
                print(f"  {col}: {val}")
            print()
    else:
        print(f"❌ No hotspots found for system '{system_name}'\n")
except sqlite3.OperationalError as e:
    print(f"⚠️ Hotspots table may not exist: {e}\n")

# Summary
print("="*80)
print("SUMMARY")
print("="*80)
print(f"Systems found: {len(system_results)}")
try:
    print(f"Rings found: {len(ring_results)}")
except:
    print("Rings found: N/A (table doesn't exist)")
try:
    print(f"Hotspots found: {len(hotspot_results)}")
except:
    print("Hotspots found: N/A (table doesn't exist)")

print(f"\nTarget: System '{system_name}', Body '11 B', Ring Type 'Metallic', Hotspot 'Bromelite'")

if system_results:
    print("\n✅ System exists in database")
    for row in system_results:
        print(f"   Name: {row[1]}")
        print(f"   Coordinates: X={row[2]}, Y={row[3]}, Z={row[4]}")
        print(f"   Population: {row[5]}")
else:
    print("\n❌ System NOT found in galaxy_systems.db")
    print("   Note: This database contains system data, not ring/hotspot data")
    print("   Ring and hotspot data is stored in user_data.db")

conn.close()
