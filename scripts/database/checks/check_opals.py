"""Quick check for Opal variants in database"""
import sqlite3
import os

db_path = os.path.join("app", "data", "user_data.db")

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check for opal variants
    cursor.execute("""
        SELECT material_name, COUNT(*) as count
        FROM hotspot_data 
        WHERE material_name LIKE '%opal%' COLLATE NOCASE
        GROUP BY material_name
        ORDER BY material_name
    """)
    
    results = cursor.fetchall()
    
    print("Material names containing 'opal':")
    print("-" * 50)
    
    if results:
        for material, count in results:
            print(f"  '{material}' - {count} records")
    else:
        print("  No opal materials found in database")
    
    print()
    
    # Check all distinct materials for reference
    cursor.execute("""
        SELECT DISTINCT material_name 
        FROM hotspot_data 
        ORDER BY material_name
    """)
    
    all_materials = [row[0] for row in cursor.fetchall()]
    print(f"\nTotal distinct materials in database: {len(all_materials)}")
    print("\nAll materials:")
    for material in all_materials:
        print(f"  - {material}")
    
    conn.close()
else:
    print(f"Database not found: {db_path}")
