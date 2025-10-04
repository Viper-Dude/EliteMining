import sqlite3
import math

conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()

print("=== PAESIA 2 A RING - DETAILED DATA ===\n")
c.execute('''SELECT material_name, ring_type, density, ls_distance, hotspot_count, x_coord, y_coord, z_coord, scan_date 
             FROM hotspot_data 
             WHERE system_name = ? AND body_name = ?
             ORDER BY material_name''', 
          ('Paesia', '2 A Ring'))

paesia_coords = (107.59375, -15.0625, 130.4375)  # From search

print(f"{'Material':<20} | {'Ring Type':<12} | {'Density':<10} | {'LS':<8} | {'Hotspots':<4} | Distance from Paesia")
print("-" * 110)

materials_data = {}
for r in c.fetchall():
    if r[5] and r[6] and r[7]:  # has coordinates
        dx = r[5] - paesia_coords[0]
        dy = r[6] - paesia_coords[1]
        dz = r[7] - paesia_coords[2]
        dist_ly = math.sqrt(dx*dx + dy*dy + dz*dz)
    else:
        dist_ly = None
    
    materials_data[r[0]] = {
        'ring_type': r[1],
        'density': r[2],
        'ls': r[3],
        'hotspots': r[4],
        'coords': f"{r[5]},{r[6]},{r[7]}" if r[5] else "None",
        'dist': dist_ly,
        'scan_date': r[8]
    }
    
    dist_str = f"{dist_ly:.2f} LY" if dist_ly is not None else "No coords"
    print(f"{r[0]:<20} | {str(r[1]):<12} | {str(r[2]):<10} | {str(r[3]):<8} | {r[4]:<4} | {dist_str}")

print("\n=== ANALYSIS ===")
print(f"\nTotal materials found: {len(materials_data)}")

# Check if all have same coords
coords_set = set([m['coords'] for m in materials_data.values()])
print(f"Unique coordinate sets: {len(coords_set)}")
for coords in coords_set:
    mats = [m for m, data in materials_data.items() if data['coords'] == coords]
    print(f"  Coords {coords}: {', '.join(mats)}")

# Check ring types
ring_types = set([m['ring_type'] for m in materials_data.values()])
print(f"\nUnique ring types: {ring_types}")

# Check LS distances
ls_values = set([m['ls'] for m in materials_data.values()])
print(f"Unique LS values: {ls_values}")

conn.close()
