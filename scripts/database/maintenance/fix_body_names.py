import sqlite3
import shutil
from datetime import datetime

db_path = 'app/data/user_data.db'

# Create backup
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = f"{db_path}.backup_{timestamp}"
shutil.copy2(db_path, backup_path)
print(f"✓ Backup created: {backup_path}\n")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all body names with lowercase issues
cursor.execute("SELECT DISTINCT body_name FROM hotspot_data WHERE body_name LIKE '% Ring'")

fixes = []
for (body_name,) in cursor.fetchall():
    parts = body_name.split()
    if len(parts) >= 2 and parts[-1] == 'Ring':
        # Check body designation parts (everything except last 2: "A Ring")
        body_parts = parts[:-2]
        
        # Fix any single lowercase letters (body designations)
        fixed_parts = []
        changed = False
        for part in body_parts:
            if len(part) == 1 and part.islower():
                fixed_parts.append(part.upper())
                changed = True
            else:
                fixed_parts.append(part)
        
        if changed:
            # Reconstruct full body name
            new_body_name = ' '.join(fixed_parts + parts[-2:])
            fixes.append((body_name, new_body_name))

print(f"Found {len(fixes)} body names to fix:\n")

# Apply fixes
total_updated = 0
for old_name, new_name in fixes:
    # Count records
    cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE body_name = ?", (old_name,))
    count = cursor.fetchone()[0]
    
    print(f"  '{old_name}' → '{new_name}' ({count} records)")
    
    # Update
    cursor.execute("UPDATE hotspot_data SET body_name = ? WHERE body_name = ?", (new_name, old_name))
    total_updated += count

conn.commit()
conn.close()

print(f"\n✓ Fixed {len(fixes)} body names")
print(f"✓ Updated {total_updated} total records")
print(f"✓ Backup: {backup_path}")
