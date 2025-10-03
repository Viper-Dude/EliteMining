import sqlite3
import math

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

reference_system = "Musca Dark Region BG-X c1-43"
close_system = "Musca Dark Region LY-Q b5-12"

print(f"Reference system (new): {reference_system}")
print(f"Close system (where you came from): {close_system}\n")

# Check reference system
cursor.execute("SELECT x_coord, y_coord, z_coord FROM visited_systems WHERE system_name = ?", (reference_system,))
ref_coords = cursor.fetchone()

if ref_coords:
    print(f"✓ Reference system has coordinates: {ref_coords}")
else:
    print("✗ Reference system NOT in visited_systems")
    ref_coords = None

# Check close system
cursor.execute("SELECT x_coord, y_coord, z_coord FROM visited_systems WHERE system_name = ?", (close_system,))
close_coords = cursor.fetchone()

if close_coords:
    print(f"✓ Close system has coordinates: {close_coords}")
else:
    print("✗ Close system NOT in visited_systems")

# Calculate distance
if ref_coords and close_coords:
    dist = math.sqrt(
        (ref_coords[0]-close_coords[0])**2 + 
        (ref_coords[1]-close_coords[1])**2 + 
        (ref_coords[2]-close_coords[2])**2
    )
    print(f"\n→ Distance: {dist:.2f} LY")

# Check if close system has hotspots
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE system_name = ?", (close_system,))
hotspot_count = cursor.fetchone()[0]
print(f"\n✓ Close system has {hotspot_count} hotspot records in database")

if hotspot_count > 0:
    cursor.execute("SELECT DISTINCT body_name, material_name FROM hotspot_data WHERE system_name = ? LIMIT 5", (close_system,))
    print("\nSample hotspots:")
    for body, material in cursor.fetchall():
        print(f"  - {body}: {material}")

conn.close()
