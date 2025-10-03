import sqlite3

# Connect to database
db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Count entries before deletion
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE data_source = 'visited_systems'")
count_before = cursor.fetchone()[0]
print(f"\nFound {count_before} entries with data_source='visited_systems'")

# Show what will be deleted
cursor.execute("SELECT system_name, body_name, material_name FROM hotspot_data WHERE data_source = 'visited_systems'")
entries_to_delete = cursor.fetchall()
print(f"\nEntries to be deleted:")
for entry in entries_to_delete[:10]:  # Show first 10
    print(f"  {entry[0]} - {entry[1]} - {entry[2]}")
if len(entries_to_delete) > 10:
    print(f"  ... and {len(entries_to_delete) - 10} more")

# Ask for confirmation
print(f"\nThis will DELETE {count_before} entries from the database.")
confirm = input("Type 'yes' to proceed: ")

if confirm.lower() == 'yes':
    # Delete entries with data_source='visited_systems'
    cursor.execute("DELETE FROM hotspot_data WHERE data_source = 'visited_systems'")
    conn.commit()
    
    # Count after deletion
    cursor.execute("SELECT COUNT(*) FROM hotspot_data")
    count_after = cursor.fetchone()[0]
    
    print(f"\n✅ Deleted {count_before} journal import entries")
    print(f"✅ Remaining entries in database: {count_after}")
else:
    print("\n❌ Operation cancelled")

conn.close()
