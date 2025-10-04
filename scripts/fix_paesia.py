import sqlite3

db_path = 'app/data/user_data.db'

print("=== FIXING PAESIA 2 A RING DATA ===\n")

# First, let's check if there's a 2 C Ring with data we can reference
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('''
    SELECT ls_distance, ring_type 
    FROM hotspot_data 
    WHERE system_name = 'Paesia' AND body_name = '2 C Ring'
    LIMIT 1
''')

ref_data = cursor.fetchone()
if ref_data and ref_data[0]:
    print(f"Found reference data from 2 C Ring: LS={ref_data[0]}, Type={ref_data[1]}")
    print("\nNote: 2 A Ring and 2 C Ring should have similar (but not identical) LS distances")
    print("They orbit the same body (planet 2) but may be different ring belts\n")
else:
    print("No reference data found from other rings of body 2\n")

# Check current state
cursor.execute('''
    SELECT COUNT(*), MIN(scan_date), MAX(scan_date)
    FROM hotspot_data 
    WHERE system_name = 'Paesia' AND body_name = '2 A Ring'
''')

stats = cursor.fetchone()
print(f"Current 2 A Ring entries: {stats[0]}")
print(f"Date range: {stats[1]} to {stats[2]}")

print("\n" + "="*60)
print("\n💡 SOLUTION OPTIONS:\n")
print("1. If you have the correct LS distance, I can update it")
print("2. Or next time you visit Paesia 2, do a FULL scan (not just DSS)")
print("   - Target the planet in supercruise")
print("   - Use Discovery Scanner (honk)")
print("   - This will create a Scan event with LS distance")
print("   - Then the new logic will update the database correctly")

print("\n📋 Manual Update Query (if you know the LS distance):")
print("""
UPDATE hotspot_data 
SET ls_distance = YOUR_LS_VALUE_HERE,
    ring_type = 'Icy' 
WHERE system_name = 'Paesia' AND body_name = '2 A Ring'
""")

conn.close()
