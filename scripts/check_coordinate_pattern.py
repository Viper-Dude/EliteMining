import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== CHECKING COORDINATE STORAGE PATTERN ===\n")

# Check a system that has multiple rings to see if coordinates differ per ring
test_systems = [
    "Praea Euq JF-Q b5-4",
    "Delkar",  # Known to have multiple rings
    "Paesia"   # Known system with multiple rings
]

for system in test_systems:
    print("="*80)
    print(f"SYSTEM: {system}")
    print("="*80)
    
    c.execute("""
        SELECT body_name, x_coord, y_coord, z_coord, coord_source 
        FROM hotspot_data 
        WHERE system_name = ?
        ORDER BY body_name
    """, (system,))
    
    results = c.fetchall()
    
    if results:
        # Check if all coordinates are the same
        coords_set = set()
        for body, x, y, z, source in results:
            coord_tuple = (x, y, z) if x is not None else None
            coords_set.add(coord_tuple)
            print(f"  {body:30s} | X={str(x):12s} Y={str(y):12s} Z={str(z):12s} | Source: {source}")
        
        print(f"\n  Unique coordinate sets: {len(coords_set)}")
        if len(coords_set) == 1:
            print("  ✅ All bodies share SAME coordinates (system-level)")
        else:
            print("  ⚠️ Bodies have DIFFERENT coordinates (body-level)")
            for coord in coords_set:
                if coord:
                    print(f"    - {coord}")
    else:
        print(f"  No data found")
    
    print()

# Also check visited_systems table to see its structure
print("\n" + "="*80)
print("VISITED_SYSTEMS TABLE STRUCTURE")
print("="*80)

c.execute("PRAGMA table_info(visited_systems)")
columns = c.fetchall()
print("\nColumns:")
for col in columns:
    print(f"  {col[1]:20s} {col[2]:10s}")

# Check a few entries
print("\nSample entries:")
c.execute("SELECT * FROM visited_systems LIMIT 3")
for row in c.fetchall():
    print(f"  {row}")

conn.close()
