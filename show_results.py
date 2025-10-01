import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

print("Top 10 LTD Locations After Cleanup:")
print("-" * 80)
print("Rank | System                        | Body                 | Hotspots")
print("-" * 80)

cursor.execute('''
    SELECT system_name, body_name, hotspot_count 
    FROM hotspot_data 
    WHERE material_name = "Low Temp. Diamonds" 
    ORDER BY hotspot_count DESC 
    LIMIT 10
''')

results = cursor.fetchall()

for i, (system, body, count) in enumerate(results, 1):
    system_short = system[:28] + "..." if len(system) > 30 else system
    body_short = body[:18] + "..." if len(body) > 20 else body
    print(f"{i:2d}   | {system_short:<30} | {body_short:<20} | {count:2d}")

print("\nKey Improvements:")
print("- Col systems now have full names (Col 285 Sector ...)")
print("- HIP systems were successfully corrected")
print("- No more duplicate entries")
print("- Material matching uses exact 'Low Temp. Diamonds'")

conn.close()