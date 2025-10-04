import sqlite3
from datetime import datetime

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check the exact update logic scenario for Paesia 2 A Ring
print("=== ANALYZING UPDATE LOGIC FOR PAESIA 2 A RING ===\n")

cursor.execute('''
    SELECT system_name, body_name, material_name, hotspot_count,
           ls_distance, ring_type, scan_date, coord_source
    FROM hotspot_data 
    WHERE system_name = 'Paesia' AND body_name = '2 A Ring'
    ORDER BY material_name
    LIMIT 1
''')

result = cursor.fetchone()
if result:
    print("Current database state:")
    print(f"  Material: {result[2]}")
    print(f"  Hotspot Count: {result[3]}")
    print(f"  LS Distance: {result[4]}")
    print(f"  Ring Type: {result[5]}")
    print(f"  Scan Date: {result[6]}")
    print(f"  Coord Source: {result[7]}")
    
    # Parse scan date
    scan_date = datetime.fromisoformat(result[6].replace('Z', '+00:00'))
    print(f"\n  Parsed Date: {scan_date}")
    
    print("\n" + "="*60)
    print("\n🔍 WHAT HAPPENS WHEN SAASignalsFound IS PROCESSED:")
    print("\nScenario: You enter the ring and DSS scan it")
    print("  - SAASignalsFound event is created with TODAY's timestamp")
    print("  - ring_info cache is EMPTY (no Scan event in current journal)")
    print("  - ls_distance = None (from cache)")
    print("  - ring_type = None (from cache)")
    print("  - scan_date = TODAY (2025-10-04)")
    print("\nDatabase UPDATE Logic:")
    print("  1. Check: scan_date > existing_date?")
    print(f"     TODAY (2025-10-04) > {result[6]}?")
    print(f"     Answer: YES - newer scan date!")
    print("\n  2. Action: UPDATE with NONE values!")
    print(f"     UPDATE SET ls_distance = None (was: {result[4]})")
    print(f"     UPDATE SET ring_type = None (was: {result[5]})")
    print("\n❌ BUG IDENTIFIED: Newer scan with incomplete data OVERWRITES complete old data!")

conn.close()
