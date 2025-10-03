import sqlite3

# Connect to database
db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Count entries before deletion
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE data_source = 'visited_systems'")
count_before = cursor.fetchone()[0]

print(f"\n{'='*80}")
print(f"STEP 1: REMOVING JOURNAL IMPORT ENTRIES")
print(f"{'='*80}\n")
print(f"Found {count_before} entries with data_source='visited_systems'")

if count_before > 0:
    # Show sample entries
    cursor.execute("SELECT system_name, body_name, material_name FROM hotspot_data WHERE data_source = 'visited_systems' LIMIT 10")
    sample_entries = cursor.fetchall()
    print(f"\nSample entries to be deleted:")
    for entry in sample_entries:
        print(f"  {entry[0]} - {entry[1]} - {entry[2]}")
    
    # Delete entries
    print(f"\nDeleting {count_before} journal import entries...")
    cursor.execute("DELETE FROM hotspot_data WHERE data_source = 'visited_systems'")
    conn.commit()
    
    # Verify deletion
    cursor.execute("SELECT COUNT(*) FROM hotspot_data")
    count_after = cursor.fetchone()[0]
    
    print(f"\n✅ Successfully deleted {count_before} journal import entries")
    print(f"✅ Remaining entries in database: {count_after}")
else:
    print("\nNo journal import entries found to delete.")

conn.close()
print(f"\n{'='*80}")
print("STEP 1 COMPLETE - Database cleaned")
print(f"{'='*80}\n")
