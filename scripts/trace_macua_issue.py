import sqlite3
import sys
sys.path.insert(0, 'app')

conn = sqlite3.connect('app/data/user_hotspots.db')
c = conn.cursor()

print("=" * 80)
print("MACUA 2 A RING - ALL DATABASE ENTRIES")
print("=" * 80)
c.execute('''
    SELECT material_name, ring_type, ls_distance, density, scan_date 
    FROM hotspot_data 
    WHERE system_name="Macua" AND body_name="2 A Ring" 
    ORDER BY material_name, scan_date
''')

rows = c.fetchall()
for r in rows:
    print(f'{r[0]:15} | Type={str(r[1]):15} | LS={str(r[2]):10} | Density={str(r[3]):10} | Date={r[4]}')

print("\n" + "=" * 80)
print("TESTING SUBQUERY (what metadata SHOULD be available)")
print("=" * 80)
c.execute('''
    SELECT system_name, body_name, 
           MAX(ring_type) as ring_type, 
           MAX(ls_distance) as ls_distance, 
           MAX(density) as density
    FROM hotspot_data 
    WHERE system_name="Macua" AND body_name="2 A Ring" 
      AND (ring_type IS NOT NULL OR ls_distance IS NOT NULL)
    GROUP BY system_name, body_name
''')

result = c.fetchone()
if result:
    print(f'System: {result[0]}')
    print(f'Body: {result[1]}')
    print(f'MAX(ring_type): {result[2]}')
    print(f'MAX(ls_distance): {result[3]}')
    print(f'MAX(density): {result[4]}')
else:
    print("❌ No metadata found!")

print("\n" + "=" * 80)
print("TESTING FULL JOIN QUERY (current Ring Finder query)")
print("=" * 80)
c.execute('''
    SELECT h.system_name, h.body_name, h.material_name, h.hotspot_count,
           COALESCE(h.ring_type, m.ring_type) as ring_type,
           COALESCE(h.ls_distance, m.ls_distance) as ls_distance,
           COALESCE(h.density, m.density) as density
    FROM hotspot_data h
    LEFT JOIN (
        SELECT system_name, body_name,
               MAX(ring_type) as ring_type, 
               MAX(ls_distance) as ls_distance,
               MAX(density) as density
        FROM hotspot_data
        WHERE ring_type IS NOT NULL OR ls_distance IS NOT NULL
        GROUP BY system_name, body_name
    ) m ON h.system_name = m.system_name AND h.body_name = m.body_name
    WHERE h.system_name = "Macua" AND h.body_name = "2 A Ring"
    ORDER BY h.material_name
''')

results = c.fetchall()
print(f"Found {len(results)} rows:\n")
for r in results:
    print(f'{r[2]:15} | Count={r[3]} | Type={str(r[4]):15} | LS={str(r[5]):10} | Density={str(r[6]):10}')

conn.close()
