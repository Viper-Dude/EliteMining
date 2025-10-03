import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

cursor.execute("SELECT DISTINCT body_name, COUNT(*) FROM hotspot_data WHERE body_name LIKE '% Ring' GROUP BY body_name ORDER BY body_name")

print("Ring body names with lowercase BODY DESIGNATIONS (excluding 'Ring'):\n")

found = []
for body_name, count in cursor.fetchall():
    # Remove " A Ring", " B Ring", " C Ring" etc from the end to check just the body designation
    parts = body_name.split()
    if len(parts) >= 2 and parts[-1] == 'Ring':
        # Check everything except the ring designation at the end (last 2 parts: "A Ring")
        body_part = ' '.join(parts[:-2])
        
        # Now check if body part has any lowercase single letters (body designations)
        # Pattern: single lowercase letter that's a standalone part
        body_parts = body_part.split()
        for part in body_parts:
            if len(part) == 1 and part.islower():
                found.append((body_name, count))
                print(f"'{body_name}' - {count} records")
                break

if not found:
    print("✅ No lowercase body designation issues found")
else:
    print(f"\n⚠️  Found {len(found)} ring names with lowercase body designations")
    print(f"Total affected records: {sum(c for _, c in found)}")

conn.close()
