import sqlite3

# Check the systems mentioned in debug to see their LTD status
db_path = r"app/data/user_data.db"

with sqlite3.connect(db_path) as conn:
    cursor = conn.cursor()
    
    print("LTD Search Analysis")
    print("=" * 50)
    
    # Check how many LTD entries exist
    cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE material_name = 'Low Temp. Diamonds'")
    total_ltd = cursor.fetchone()[0]
    print(f"Total LTD entries in database: {total_ltd}")
    
    # Check specific systems from debug output
    systems_mentioned = ['LFT 65', 'Tollan', 'LHS 6128', 'Fusang']
    
    print(f"\nSystems mentioned in debug:")
    for system in systems_mentioned:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM hotspot_data 
            WHERE system_name = ? AND material_name = 'Low Temp. Diamonds'
        """, (system,))
        ltd_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) 
            FROM hotspot_data 
            WHERE system_name = ?
        """, (system,))
        total_count = cursor.fetchone()[0]
        
        print(f"  {system}: {ltd_count} LTD out of {total_count} total materials")
        
        # Show LTD details if any
        if ltd_count > 0:
            cursor.execute("""
                SELECT body_name, hotspot_count
                FROM hotspot_data
                WHERE system_name = ? AND material_name = 'Low Temp. Diamonds'
                ORDER BY hotspot_count DESC
            """, (system,))
            details = cursor.fetchall()
            for body, count in details:
                print(f"    - {body}: {count} hotspots")
    
    print(f"\nTop 10 LTD locations that should be showing:")
    cursor.execute("""
        SELECT system_name, body_name, hotspot_count
        FROM hotspot_data 
        WHERE material_name = 'Low Temp. Diamonds'
        ORDER BY hotspot_count DESC
        LIMIT 10
    """)
    
    top_ltd = cursor.fetchall()
    for i, (system, body, count) in enumerate(top_ltd, 1):
        print(f"  {i:2d}. {system} - {body} ({count} hotspots)")