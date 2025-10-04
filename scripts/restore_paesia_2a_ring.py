import sqlite3
import os

print("=== RESTORING PAESIA 2 a A RING TO DEFAULT DATABASE ===\n")

default_db_path = "app/data/UserDb for install/user_data.db"

if not os.path.exists(default_db_path):
    print(f"❌ Database not found: {default_db_path}")
    exit(1)

conn = sqlite3.connect(default_db_path)
cursor = conn.cursor()

# First, check if 2 a A Ring already exists
cursor.execute('''SELECT body_name, material_name, hotspot_count 
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" AND body_name LIKE "%2 a A Ring%"''')
existing = cursor.fetchall()

if existing:
    print("⚠️  Found existing '2 a A Ring' entries:")
    for e in existing:
        print(f"    {e[0]} - {e[1]}: {e[2]} hotspot(s)")
    print("\n❓ These entries already exist. Skipping insertion.")
else:
    print("✓ No existing '2 a A Ring' entries found. Adding data...\n")
    
    # Based on scan results: Grandidierite, Tritium
    # Using today's date as scan_date
    new_entries = [
        ("Paesia", "2 a A Ring", "Grandidierite", 3, "2025-10-01"),
        ("Paesia", "2 a A Ring", "Tritium", 2, "2025-10-01"),
    ]
    
    for entry in new_entries:
        try:
            cursor.execute('''INSERT OR REPLACE INTO hotspot_data 
                             (system_name, body_name, material_name, hotspot_count, scan_date)
                             VALUES (?, ?, ?, ?, ?)''', entry)
            print(f"✓ Added: {entry[1]} - {entry[2]}: {entry[3]} hotspot(s)")
        except Exception as e:
            print(f"❌ Error adding {entry[2]}: {e}")
    
    conn.commit()
    print("\n✓ Database updated successfully!")

# Verify final state
print("\n" + "="*60)
print("FINAL STATE - All Paesia rings in default database:")
print("="*60)
cursor.execute('''SELECT DISTINCT body_name, material_name, hotspot_count 
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name, material_name''')
results = cursor.fetchall()

current_body = None
for r in results:
    if r[0] != current_body:
        print(f"\n{r[0]}:")
        current_body = r[0]
    print(f"  • {r[1]}: {r[2]} hotspot(s)")

conn.close()
print("\n✓ Done!")
