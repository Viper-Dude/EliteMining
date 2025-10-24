"""
Check what data exists for Macua rings in the database
"""

import sqlite3
import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from path_utils import get_app_data_dir

def check_macua_rings():
    """Check all Macua ring data"""
    
    # Get database path
    app_dir = get_app_data_dir()
    db_path = os.path.join(app_dir, 'data', 'user_data.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    
    print(f"Checking database: {db_path}\n")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Get all Macua rings
        cursor.execute('''
            SELECT DISTINCT body_name
            FROM hotspot_data
            WHERE system_name = 'Macua'
            ORDER BY body_name
        ''')
        
        rings = [row[0] for row in cursor.fetchall()]
        print(f"Found {len(rings)} Macua rings in database:")
        for ring in rings:
            print(f"  - {ring}")
        
        print("\n" + "="*80 + "\n")
        
        # Check each ring for metadata
        for ring_name in rings:
            print(f"Ring: {ring_name}")
            print("-" * 40)
            
            cursor.execute('''
                SELECT material_name, ls_distance, ring_type, density, inner_radius, outer_radius
                FROM hotspot_data
                WHERE system_name = 'Macua' AND body_name = ?
                ORDER BY material_name
            ''', (ring_name,))
            
            materials = cursor.fetchall()
            
            has_metadata = False
            for mat, ls, ring_type, dens, inner, outer in materials:
                if ls or ring_type or dens:
                    has_metadata = True
                    print(f"  ✓ {mat}: LS={ls}, Type={ring_type}, Density={dens}")
                else:
                    print(f"  ✗ {mat}: No metadata")
            
            if not has_metadata:
                print(f"  ⚠️ NO RING HAS ANY METADATA!")
            
            print()

if __name__ == '__main__':
    try:
        check_macua_rings()
        input("\nPress Enter to exit...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
