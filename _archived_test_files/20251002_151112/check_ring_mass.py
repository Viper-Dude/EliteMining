"""Check for entries with ring mass in actual database"""
import sqlite3
import os

db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'

if not os.path.exists(db_path):
    print(f"❌ Database not found")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Count entries with ring mass
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE ring_mass IS NOT NULL")
count_with_mass = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM hotspot_data")
total_count = cursor.fetchone()[0]

print(f"\n{'='*60}")
print(f"RING MASS STATUS IN DATABASE")
print(f"{'='*60}\n")
print(f"Total hotspot entries: {total_count}")
print(f"Entries with ring_mass: {count_with_mass}")
print(f"Entries WITHOUT ring_mass: {total_count - count_with_mass}\n")

# Show sample with mass if any exist
if count_with_mass > 0:
    cursor.execute("""
        SELECT system_name, body_name, material_name, 
               inner_radius, outer_radius, ring_mass, density
        FROM hotspot_data
        WHERE ring_mass IS NOT NULL
        LIMIT 5
    """)
    
    print(f"Sample entries WITH ring mass:")
    for row in cursor.fetchall():
        system, body, material, inner, outer, mass, density = row
        print(f"\n  {system} - {body} - {material}")
        print(f"    Inner/Outer: {inner}/{outer}")
        print(f"    Mass: {mass}")
        print(f"    Density: {density} {'✅' if density else '❌ (should calculate!)'}")

print(f"\n{'='*60}\n")

conn.close()
