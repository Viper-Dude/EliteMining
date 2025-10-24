import sqlite3
import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

db_path = 'app/data/user_data.db'  # Changed from user_hotspots.db

print("="*80)
print("CHECKING MACUA SYSTEM IN USER DATABASE (user_data.db)")
print("="*80)

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check all Macua system entries
c.execute('''SELECT system_name, body_name, material_name, ring_type, density, 
             ls_distance, hotspot_count, scan_date, coord_source, inner_radius, outer_radius, ring_mass
             FROM hotspot_data 
             WHERE system_name = "Macua"
             ORDER BY body_name, material_name''')

results = c.fetchall()

if results:
    print(f"\nFound {len(results)} entries for Macua system:\n")
    
    # Group by body (ring)
    bodies = {}
    for r in results:
        body_name = r[1]
        if body_name not in bodies:
            bodies[body_name] = []
        bodies[body_name].append(r)
    
    for body_name, entries in sorted(bodies.items()):
        print("="*80)
        print(f"BODY: {body_name}")
        print("="*80)
        for r in entries:
            ring_type = r[3] if r[3] else 'MISSING ❌'
            ls_dist = f"{r[5]:.2f}" if r[5] else 'MISSING ❌'
            density = f"{r[4]:.2f}" if r[4] else 'N/A'
            
            print(f"  Material: {r[2]:<20} | Type: {ring_type:<15} | LS: {ls_dist:<12}")
            print(f"    Density: {density:<12} | Inner R: {r[9] if r[9] else 'N/A'} | Outer R: {r[10] if r[10] else 'N/A'}")
            print(f"    Count: {r[6]} | Date: {r[7]} | Source: {r[8]}")
            print()
        print()
else:
    print("\nNO ENTRIES FOUND for Macua system in database!")
    print("\nThis could mean:")
    print("1. Journal events are not being parsed")
    print("2. System name mismatch (check spelling)")
    print("3. Database path is incorrect")

# Check database schema
print("\n" + "="*80)
print("DATABASE SCHEMA CHECK")
print("="*80)
c.execute("PRAGMA table_info(hotspot_data)")
columns = c.fetchall()
print("\nColumns in hotspot_data table:")
for col in columns:
    print(f"  {col[1]} ({col[2]})")

# Check if we have any data at all
c.execute("SELECT COUNT(*) FROM hotspot_data")
total_count = c.fetchone()[0]
print(f"\nTotal entries in database: {total_count}")

conn.close()

print("\n" + "="*80)
print("NEXT STEPS TO DEBUG:")
print("="*80)
print("1. Check journal_parser.py - look for 'Scan' and 'SAASignalsFound' event handling")
print("2. Check if ring_type and ls_distance are being extracted from events")
print("3. Check user_database.py - verify add_hotspot() method saves all fields")
print("4. Look at journal files to see what data Elite is providing")
