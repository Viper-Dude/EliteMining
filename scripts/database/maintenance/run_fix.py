import sqlite3
import shutil
from datetime import datetime

db_path = "app/data/user_data.db"

# Create backup
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{db_path}.backup_{timestamp}"
shutil.copy2(db_path, backup_path)
print(f"✓ Backup created: {backup_path}\n")

# Fix the duplicates
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Fix Low Temp. Diamonds → Low Temperature Diamonds
cursor.execute("UPDATE hotspot_data SET material_name = 'Low Temperature Diamonds' WHERE material_name = 'Low Temp. Diamonds'")
rows1 = cursor.rowcount

# Fix Void Opal → Void Opals
cursor.execute("UPDATE hotspot_data SET material_name = 'Void Opals' WHERE material_name = 'Void Opal'")
rows2 = cursor.rowcount

conn.commit()
print(f"✓ Fixed 'Low Temp. Diamonds' → 'Low Temperature Diamonds' ({rows1} records)")
print(f"✓ Fixed 'Void Opal' → 'Void Opals' ({rows2} records)")

# Verify
cursor.execute("SELECT DISTINCT material_name FROM hotspot_data WHERE material_name LIKE '%diamond%' OR material_name LIKE '%opal%' ORDER BY material_name")
print("\nCurrent diamond/opal variants:")
for (mat,) in cursor.fetchall():
    cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE material_name = ?", (mat,))
    count = cursor.fetchone()[0]
    print(f"  '{mat}': {count} records")

conn.close()
print(f"\n✓ Done! Backup: {backup_path}")
