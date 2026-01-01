import sqlite3
conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()
cursor.execute("SELECT system_name, visit_count, first_visit_date, last_visit_date FROM visited_systems WHERE system_name = 'Namnetes'")
result = cursor.fetchone()
if result:
    print(f"System: {result[0]}")
    print(f"Visit Count: {result[1]}")
    print(f"First Visit: {result[2]}")
    print(f"Last Visit: {result[3]}")
else:
    print("Namnetes NOT FOUND in visited_systems table")
    
# Also check total count
cursor.execute("SELECT COUNT(*) FROM visited_systems")
total = cursor.fetchone()[0]
print(f"\nTotal visited systems: {total}")

conn.close()
