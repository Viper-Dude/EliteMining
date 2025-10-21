import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

system_name = "Praea Euq JF-Q b5-4"

print(f"=== CHECKING USER DATABASE FOR: {system_name} ===\n")

# First, check what tables exist
print("="*80)
print("DATABASE STRUCTURE")
print("="*80)
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()
print(f"Tables: {[t[0] for t in tables]}\n")

# Check hotspot_data table
print("="*80)
print("HOTSPOT_DATA TABLE")
print("="*80)
c.execute('''SELECT * FROM hotspot_data WHERE system_name LIKE ?''', (f'%{system_name}%',))
hotspot_results = c.fetchall()

if hotspot_results:
    print(f"\n✅ Found {len(hotspot_results)} hotspot entries:\n")
    
    # Get column names
    c.execute("PRAGMA table_info(hotspot_data)")
    columns = [col[1] for col in c.fetchall()]
    
    # Group by body
    bodies = {}
    for row in hotspot_results:
        body_name = row[columns.index('body_name')]
        if body_name not in bodies:
            bodies[body_name] = []
        bodies[body_name].append(row)
    
    for body_name, entries in sorted(bodies.items()):
        print("=" * 80)
        print(f"BODY: {body_name}")
        print("=" * 80)
        for row in entries:
            data = dict(zip(columns, row))
            print(f"  System: {data.get('system_name')}")
            print(f"  Body: {data.get('body_name')}")
            print(f"  Material: {data.get('material_name')}")
            print(f"  Ring Type: {data.get('ring_type')}")
            print(f"  Density: {data.get('density')}")
            print(f"  LS Distance: {data.get('ls_distance')}")
            print(f"  Hotspot Count: {data.get('hotspot_count')}")
            print(f"  Scan Date: {data.get('scan_date')}")
            print(f"  Coord Source: {data.get('coord_source')}")
            print("-" * 80)
else:
    print(f"❌ No hotspot data found for system '{system_name}'\n")

# Also try a broader search
print("\n" + "="*80)
print("BROADER SEARCH (Praea Euq)")
print("="*80)
c.execute('''SELECT DISTINCT system_name, body_name FROM hotspot_data WHERE system_name LIKE ?''', ('%Praea Euq%',))
broad_results = c.fetchall()

if broad_results:
    print(f"\nFound {len(broad_results)} system/body combinations with 'Praea Euq':\n")
    for row in broad_results:
        print(f"  System: {row[0]}, Body: {row[1]}")
else:
    print("No systems found matching 'Praea Euq'")

# Summary
print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print(f"Target: System '{system_name}', Body '11 B', Ring 'Metallic', Hotspot 'Bromelite'")
print(f"Hotspot entries found: {len(hotspot_results)}")

if hotspot_results:
    print("\n✅ System EXISTS in user_data.db hotspot_data table")
else:
    print("\n❌ System NOT found in user_data.db")

conn.close()
