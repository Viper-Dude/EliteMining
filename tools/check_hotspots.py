import sqlite3

# Check BOTH databases
databases = [
    ('DEV', 'app/data/user_data.db'),
    ('INSTALLER', 'app/data/UserDb for install/user_data.db')
]

for db_name, db_path in databases:
    print(f"\n{'='*60}")
    print(f"Checking {db_name} database: {db_path}")
    print('='*60)
    
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        # Check for systems table
        c.execute("SELECT COUNT(*) FROM systems WHERE name LIKE '%Antliae%PX-U%'")
        count = c.fetchone()[0]
        print(f"\nSystems matching 'Antliae PX-U': {count}")
        
        if count > 0:
            c.execute("SELECT id, name, x, y, z FROM systems WHERE name LIKE '%Antliae%PX-U%' LIMIT 5")
            for row in c.fetchall():
                print(f"  {row}")
        
        # Check for hotspots related to this system
        c.execute("""
            SELECT h.system_id, s.name, h.body_name, h.ring_type, h.mineral, h.hotspot_count
            FROM hotspots h
            JOIN systems s ON h.system_id = s.id
            WHERE s.name LIKE '%Antliae%PX-U%'
            LIMIT 10
        """)
        hotspots = c.fetchall()
        print(f"\nHotspots for Antliae PX-U: {len(hotspots)}")
        for row in hotspots:
            print(f"  System ID: {row[0]}, System: {row[1]}, Body: {row[2]}, Ring: {row[3]}, Mineral: {row[4]}, Count: {row[5]}")
        
        conn.close()
        
    except Exception as e:
        print(f"Error checking {db_name} database: {e}")
        import traceback
        traceback.print_exc()
