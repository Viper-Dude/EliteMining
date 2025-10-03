import sqlite3
import re

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

# Get all unique body names that contain " Ring"
cursor.execute("""
    SELECT DISTINCT body_name, COUNT(*) as count
    FROM hotspot_data 
    WHERE body_name LIKE '% Ring'
    ORDER BY body_name
""")

print("Scanning all ring body names for lowercase letters:\n")

issues = []
for body_name, count in cursor.fetchall():
    # Split the body name into parts
    parts = body_name.split()
    
    # Check each part for lowercase single letters that should be capitals
    # These appear after numbers or between other capitals
    found_issue = False
    for i, part in enumerate(parts):
        # Single lowercase letter that's not part of a word
        if len(part) == 1 and part.islower():
            # Check context - should be between number/capital and capital/Ring
            if i > 0 and i < len(parts) - 1:
                prev_part = parts[i-1]
                next_part = parts[i+1]
                # If previous is number or capital, and next is capital or "Ring"
                if (prev_part.isdigit() or prev_part.isupper()) and (next_part[0].isupper() or next_part == "Ring"):
                    found_issue = True
                    break
    
    if found_issue:
        issues.append((body_name, count))
        print(f"❌ '{body_name}' ({count} records)")

if not issues:
    print("✅ No lowercase letter issues found")
else:
    print(f"\n⚠️  Total: {len(issues)} body names with lowercase letters")
    print(f"Total affected records: {sum(c for _, c in issues)}")

conn.close()
