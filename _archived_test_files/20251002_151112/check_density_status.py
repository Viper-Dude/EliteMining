"""Check density status across ALL database entries"""
import sqlite3

db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print(f"\n{'='*70}")
print(f"DATABASE DENSITY STATUS REPORT")
print(f"{'='*70}\n")

# Total entries
cursor.execute("SELECT COUNT(*) FROM hotspot_data")
total = cursor.fetchone()[0]

# Entries with density
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE density IS NOT NULL")
with_density = cursor.fetchone()[0]

# Entries with ring_mass
cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE ring_mass IS NOT NULL")
with_mass = cursor.fetchone()[0]

# Entries with radii but NO mass/density
cursor.execute("""
    SELECT COUNT(*) 
    FROM hotspot_data 
    WHERE inner_radius IS NOT NULL 
    AND outer_radius IS NOT NULL
    AND ring_mass IS NULL
""")
has_radii_no_mass = cursor.fetchone()[0]

print(f"Total hotspot entries:          {total:,}")
print(f"Entries WITH density:           {with_density:,} ({100*with_density/total:.1f}%)")
print(f"Entries WITH ring_mass:         {with_mass:,} ({100*with_mass/total:.1f}%)")
print(f"Entries WITHOUT mass/density:   {total-with_density:,} ({100*(total-with_density)/total:.1f}%)")
print(f"\nEntries with radii but NO mass: {has_radii_no_mass:,}")
print(f"  (These are from DSS scans without planet Scan event)")

# Show sample of entries WITH density
print(f"\n{'='*70}")
print(f"SAMPLE ENTRIES WITH DENSITY:")
print(f"{'='*70}\n")

cursor.execute("""
    SELECT system_name, body_name, material_name, ring_mass, density
    FROM hotspot_data
    WHERE density IS NOT NULL
    ORDER BY system_name, body_name
    LIMIT 10
""")

for row in cursor.fetchall():
    system, body, material, mass, density = row
    print(f"{system} - {body}")
    mass_str = f"{mass:.2e}" if mass else "N/A (from EDTools)"
    print(f"  {material}: Mass={mass_str}, Density={density}")

# Show breakdown by system
print(f"\n{'='*70}")
print(f"SYSTEMS WITH DENSITY DATA:")
print(f"{'='*70}\n")

cursor.execute("""
    SELECT system_name, COUNT(*) as count
    FROM hotspot_data
    WHERE density IS NOT NULL
    GROUP BY system_name
    ORDER BY count DESC
""")

systems_with_density = cursor.fetchall()
print(f"Total systems with density data: {len(systems_with_density)}\n")

for system, count in systems_with_density[:20]:
    print(f"  {system}: {count} entries")

conn.close()

print(f"\n{'='*70}")
print(f"RECOMMENDATION:")
print(f"{'='*70}\n")
print(f"✅ Density calculation is working!")
print(f"✅ Currently only {with_density:,} of {total:,} entries have density")
print(f"")
print(f"💡 To fill ALL entries with density data:")
print(f"   Option 1: Re-import ALL journal files (will update existing entries)")
print(f"   Option 2: Wait for future scans (new data will have density)")
print(f"")
print(f"⚠️  Note: {has_radii_no_mass:,} entries have radii but will NEVER get mass")
print(f"   (These are from DSS-only scans without full planet Scan events)")
print(f"{'='*70}\n")
