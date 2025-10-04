import sqlite3

print("=== CHECKING ACTUAL PAESIA RINGS ===\n")

# Check user database
print("1. USER DATABASE (app/data/user_data.db)")
print("-" * 60)
conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

cursor.execute('''SELECT DISTINCT body_name 
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name''')
rings = cursor.fetchall()

print("Rings found:")
for r in rings:
    print(f"  • {r[0]}")
conn.close()

print("\n" + "=" * 60 + "\n")

# Check default database
print("2. DEFAULT DATABASE (app/data/UserDb for install/user_data.db)")
print("-" * 60)
conn = sqlite3.connect('app/data/UserDb for install/user_data.db')
cursor = conn.cursor()

cursor.execute('''SELECT DISTINCT body_name 
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name''')
rings = cursor.fetchall()

print("Rings found:")
for r in rings:
    print(f"  • {r[0]}")
conn.close()

print("\n" + "=" * 60 + "\n")
print("CONCLUSION:")
print("If you see '2 A Ring' it means the normalization removed '2 A A Ring'")
print("If '2 A A Ring' should exist, then the last fix broke it!")
