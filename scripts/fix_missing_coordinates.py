import sqlite3

db_path = 'app/data/user_data.db'
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== FIXING MISSING COORDINATES FOR RINGS IN SAME SYSTEM ===\n")

# Step 1: Find all systems that have BOTH rings with coords AND rings without coords
c.execute("""
    SELECT DISTINCT system_name
    FROM hotspot_data
    WHERE system_name IN (
        -- Systems with at least one ring that HAS coordinates
        SELECT system_name FROM hotspot_data WHERE x_coord IS NOT NULL
    )
    AND system_name IN (
        -- Systems with at least one ring that LACKS coordinates
        SELECT system_name FROM hotspot_data WHERE x_coord IS NULL
    )
    ORDER BY system_name
""")

systems_to_fix = [row[0] for row in c.fetchall()]

print(f"Found {len(systems_to_fix)} systems with mixed coordinate data:\n")

if not systems_to_fix:
    print("✅ No systems need fixing - all rings have consistent coordinate data!")
    conn.close()
    exit(0)

# Show systems that will be fixed
for system in systems_to_fix:
    print(f"  - {system}")

print("\n" + "="*80)
print("FIXING COORDINATES...")
print("="*80 + "\n")

total_rows_updated = 0

for system_name in systems_to_fix:
    # Get coordinates from any ring in this system that HAS coordinates
    c.execute("""
        SELECT x_coord, y_coord, z_coord, coord_source
        FROM hotspot_data
        WHERE system_name = ? AND x_coord IS NOT NULL
        LIMIT 1
    """, (system_name,))
    
    coord_data = c.fetchone()
    
    if coord_data:
        x, y, z, source = coord_data
        
        # Count how many rows need updating
        c.execute("""
            SELECT COUNT(*) 
            FROM hotspot_data 
            WHERE system_name = ? AND x_coord IS NULL
        """, (system_name,))
        
        rows_to_update = c.fetchone()[0]
        
        # Update all rings in this system that are missing coordinates
        c.execute("""
            UPDATE hotspot_data
            SET x_coord = ?,
                y_coord = ?,
                z_coord = ?,
                coord_source = ?
            WHERE system_name = ? AND x_coord IS NULL
        """, (x, y, z, source, system_name))
        
        updated = c.rowcount
        total_rows_updated += updated
        
        print(f"✅ {system_name}")
        print(f"   Updated {updated} rows with coordinates: X={x}, Y={y}, Z={z}")
        print(f"   Source: {source}\n")

# Commit changes
conn.commit()

print("="*80)
print("SUMMARY")
print("="*80)
print(f"Systems fixed: {len(systems_to_fix)}")
print(f"Total hotspot entries updated: {total_rows_updated}")
print("\n✅ Database updated successfully!")
print("   All rings in the same system now share coordinates.")

conn.close()
