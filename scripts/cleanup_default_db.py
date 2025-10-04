import sqlite3
import shutil
from datetime import datetime

# Paths
db_path = 'app/data/UserDb for install/user_data.db'
backup_path = f'app/data/UserDb for install/user_data_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

print("=== CLEANING DEFAULT DATABASE ===\n")

# Create backup first
print(f"1. Creating backup: {backup_path}")
shutil.copy2(db_path, backup_path)
print("   ✓ Backup created\n")

# Connect to database
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Check what will be deleted
print("2. Checking for phantom ring data...\n")

c.execute('''SELECT body_name, material_name, ring_type, ls_distance, hotspot_count
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name = "2 C Ring"''')

phantom_entries = c.fetchall()

if phantom_entries:
    print(f"   Found {len(phantom_entries)} entries to delete:")
    for entry in phantom_entries:
        print(f"   - {entry[0]}: {entry[1]} ({entry[2]}) - LS:{entry[3]} - Count:{entry[4]}")
    
    # Delete the phantom ring
    print("\n3. Deleting phantom ring entries...")
    c.execute('''DELETE FROM hotspot_data 
                 WHERE system_name = "Paesia" AND body_name = "2 C Ring"''')
    
    deleted_count = c.rowcount
    conn.commit()
    print(f"   ✓ Deleted {deleted_count} entries\n")
else:
    print("   No phantom ring entries found (already clean)\n")

# Verify cleanup
print("4. Verifying cleanup...\n")

c.execute('''SELECT body_name, material_name, ring_type, ls_distance
             FROM hotspot_data 
             WHERE system_name = "Paesia" AND body_name LIKE "%2%Ring%"
             ORDER BY body_name, material_name''')

remaining = c.fetchall()

if remaining:
    print(f"   Remaining Paesia 2 rings in database:")
    for entry in remaining:
        print(f"   ✓ {entry[0]}: {entry[1]} ({entry[2]}) - LS:{entry[3]}")
else:
    print("   No Paesia entries remaining")

conn.close()

print("\n" + "="*70)
print("CLEANUP COMPLETE!")
print("="*70)
print(f"✓ Backup saved to: {backup_path}")
print(f"✓ Default database cleaned: {db_path}")
print("\nThe phantom 2 C Ring has been removed from the default database.")
print("New users will no longer get this incorrect data!")
