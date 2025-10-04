import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
c = conn.cursor()

print("=== PAESIA 2 A RING - ALL ENTRIES ===\n")
c.execute('''SELECT material_name, ring_type, density, ls_distance, x_coord, y_coord, z_coord 
             FROM hotspot_data 
             WHERE system_name = ? AND body_name = ?''', 
          ('Paesia', '2 A Ring'))

print(f"{'Material':<20} | {'Ring Type':<12} | {'Density':<10} | {'LS':<8} | Coordinates")
print("-" * 90)

for r in c.fetchall():
    coords = f"{r[4]:.2f},{r[5]:.2f},{r[6]:.2f}" if r[4] else "None"
    print(f"{r[0]:<20} | {str(r[1]):<12} | {str(r[2]):<10} | {str(r[3]):<8} | {coords}")

print("\n=== CHECKING FOR DUPLICATE SYSTEMS ===\n")
c.execute('''SELECT DISTINCT system_name, body_name, x_coord, y_coord, z_coord 
             FROM hotspot_data 
             WHERE body_name LIKE '%2 A Ring%' ''')

systems = c.fetchall()
print(f"Found {len(systems)} different '2 A Ring' entries:")
for s in systems:
    coords = f"{s[2]:.2f},{s[3]:.2f},{s[4]:.2f}" if s[2] else "None"
    print(f"  {s[0]} - {s[1]} at {coords}")

conn.close()
