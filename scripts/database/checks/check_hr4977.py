import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

system_name = "HR 4977"

print(f"Searching for all entries with system: {system_name}\n")

# Check hotspot_data
cursor.execute("SELECT body_name, material_name, hotspot_count FROM hotspot_data WHERE system_name = ? ORDER BY body_name", (system_name,))
hotspots = cursor.fetchall()

if hotspots:
    print(f"✓ Found {len(hotspots)} entries in hotspot_data:")
    for body, material, count in hotspots:
        print(f"  - {body}: {material} ({count})")
else:
    print("✗ No entries found in hotspot_data")

# Check visited_systems
cursor.execute("SELECT visit_date, x_coord, y_coord, z_coord FROM visited_systems WHERE system_name = ?", (system_name,))
visited = cursor.fetchone()

print(f"\nVisited systems:")
if visited:
    print(f"✓ System visited: {visited[0]}")
    print(f"  Coordinates: ({visited[1]}, {visited[2]}, {visited[3]})")
else:
    print("✗ System not in visited_systems")

conn.close()
