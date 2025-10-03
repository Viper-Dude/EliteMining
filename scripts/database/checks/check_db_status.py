"""Quick check of current database state"""
import sqlite3

conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

print("\n" + "="*60)
print("DATABASE STATUS CHECK")
print("="*60)

# Check all distinct material names
cursor.execute("SELECT DISTINCT material_name FROM hotspot_data ORDER BY material_name")
materials = [r[0] for r in cursor.fetchall()]

print("\nAll distinct material names:")
for mat in materials:
    print(f'  "{mat}"')

# Check for problem materials
problems = []

# Check for old database format names
if 'LowTemperatureDiamond' in materials:
    problems.append("❌ 'LowTemperatureDiamond' should be 'Low Temperature Diamonds'")

if 'Opal' in materials:
    problems.append("❌ 'Opal' should be 'Void Opals'")

# Check for any other variants
expected_materials = {
    'Alexandrite', 'Benitoite', 'Bromellite', 'Grandidierite',
    'Low Temperature Diamonds', 'Monazite', 'Musgravite', 'Painite',
    'Platinum', 'Rhodplumsite', 'Serendibite', 'Tritium', 'Void Opals'
}

unexpected = set(materials) - expected_materials
if unexpected:
    print("\n⚠️  Unexpected materials found:")
    for mat in unexpected:
        problems.append(f"❌ Unexpected: '{mat}'")

print("\n" + "="*60)
if problems:
    print("ISSUES FOUND:")
    print("="*60)
    for problem in problems:
        print(problem)
    print("\n✅ RECOMMENDATION: Run fix_material_names.py script")
else:
    print("✅ DATABASE IS CLEAN - No issues found!")
print("="*60)

conn.close()
