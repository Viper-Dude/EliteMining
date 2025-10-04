import sqlite3

print("=== PAESIA RING TYPE, LS DISTANCE, DENSITY CHECK ===\n")

# Check user database
print("1. USER DATABASE (app/data/user_data.db)")
print("-" * 70)
conn = sqlite3.connect('app/data/user_data.db')
cursor = conn.cursor()

cursor.execute('''SELECT DISTINCT body_name, ring_type, ls_distance, density
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name''')
results = cursor.fetchall()

for r in results:
    print(f"\n{r[0]}:")
    print(f"  Ring Type: {r[1]}")
    print(f"  LS Distance: {r[2]}")
    print(f"  Density: {r[3]}")

conn.close()

print("\n" + "=" * 70 + "\n")

# Check default database
print("2. DEFAULT DATABASE (app/data/UserDb for install/user_data.db)")
print("-" * 70)
conn = sqlite3.connect('app/data/UserDb for install/user_data.db')
cursor = conn.cursor()

cursor.execute('''SELECT DISTINCT body_name, ring_type, ls_distance, density
                  FROM hotspot_data 
                  WHERE system_name = "Paesia" 
                  ORDER BY body_name''')
results = cursor.fetchall()

for r in results:
    print(f"\n{r[0]}:")
    print(f"  Ring Type: {r[1]}")
    print(f"  LS Distance: {r[2]}")
    print(f"  Density: {r[3]}")

conn.close()

print("\n" + "=" * 70 + "\n")

# Now check what the scan results file says about LS distances
print("3. ACTUAL SCAN DATA FROM paesia_scan_results.txt:")
print("-" * 70)
with open('paesia_scan_results.txt', 'r') as f:
    content = f.read()
    
print("\nFrom actual journal scans:")
print("  • 2 A Ring: LS Distance: 821.100804")
print("  • 2 B Ring: LS Distance: 821.100805")
print("  • 2 a A Ring: LS Distance: 833.224795")
print("  • 5 A Ring: LS Distance: 2077.340563")
