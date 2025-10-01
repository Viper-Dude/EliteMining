import sqlite3

db_path = 'app/data/user_data.db'
print('=== DELKAR INVESTIGATION ===')

with sqlite3.connect(db_path) as conn:
    # Check all materials for Delkar
    cursor = conn.execute('''
        SELECT system_name, body_name, material_name, ls_distance, density, ring_type, hotspot_count
        FROM hotspot_data 
        WHERE system_name = 'Delkar'
        ORDER BY body_name, material_name
    ''')
    results = cursor.fetchall()
    
    print(f'Total Delkar records in database: {len(results)}')
    print('Body | Material | LS | Ring Type | Hotspots')
    print('-' * 60)
    
    for row in results:
        density_display = float(row[4]) / 1000000 if row[4] else 0
        print(f'{row[1]:10s} | {row[2]:15s} | {row[3]:7.1f} | {row[5]:8s} | {row[6]}')
    
    # Check for issues
    print('\n=== POTENTIAL ISSUES ===')
    
    # Check for ring type mismatches
    cursor = conn.execute('''
        SELECT body_name, COUNT(DISTINCT ring_type) as type_count, GROUP_CONCAT(DISTINCT ring_type) as types
        FROM hotspot_data 
        WHERE system_name = 'Delkar'
        GROUP BY body_name
        HAVING COUNT(DISTINCT ring_type) > 1
    ''')
    type_conflicts = cursor.fetchall()
    
    if type_conflicts:
        print('Ring type conflicts found:')
        for conflict in type_conflicts:
            print(f'  {conflict[0]}: {conflict[2]} (should be consistent)')
    else:
        print('No ring type conflicts found')