import sqlite3
import re

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

# Find body names with lowercase letters in positions where capitals are expected
# Pattern: Find rings with lowercase letters after numbers or spaces (should be capitals)
cursor.execute("""
    SELECT DISTINCT body_name, COUNT(*) as count
    FROM hotspot_data 
    WHERE body_name LIKE '% Ring'
    ORDER BY body_name
""")

print("Checking body names for lowercase letter issues:\n")

issues_found = []
for body_name, count in cursor.fetchall():
    # Check for patterns like "11 h" where h should be H
    # Look for space followed by lowercase letter followed by space or capital
    pattern = r'\s+([a-z])\s+[A-Z]'
    if re.search(pattern, body_name):
        issues_found.append((body_name, count))
        print(f"❌ '{body_name}' ({count} records) - has lowercase letter that should be capital")

if not issues_found:
    print("✅ No lowercase letter issues found in body names")
else:
    print(f"\n⚠️  Found {len(issues_found)} body names with lowercase letter issues")

conn.close()
