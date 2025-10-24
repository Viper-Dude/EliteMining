"""
One-time script to back-fill ring metadata to all materials in the same ring.
This fixes the issue where some materials have metadata (ls_distance, ring_type)
but others in the same ring don't.
"""

import sqlite3
import os
import sys

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from path_utils import get_app_data_dir

def backfill_ring_metadata():
    """Back-fill ring metadata to materials missing it in the same ring"""
    
    # Get database path
    app_dir = get_app_data_dir()
    db_path = os.path.join(app_dir, 'data', 'user_data.db')
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return
    
    print(f"Opening database: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        
        # Get all unique rings (system + body combinations)
        cursor.execute('''
            SELECT DISTINCT system_name, body_name
            FROM hotspot_data
            ORDER BY system_name, body_name
        ''')
        
        rings = cursor.fetchall()
        print(f"Found {len(rings)} unique rings to process...")
        
        total_updated = 0
        
        for system_name, body_name in rings:
            # For each ring, find a material that HAS metadata
            cursor.execute('''
                SELECT ls_distance, ring_type, inner_radius, outer_radius, ring_mass, density
                FROM hotspot_data
                WHERE system_name = ? AND body_name = ?
                  AND (ls_distance IS NOT NULL OR ring_type IS NOT NULL OR density IS NOT NULL)
                LIMIT 1
            ''', (system_name, body_name))
            
            source_data = cursor.fetchone()
            
            if source_data:
                ls_dist, ring_type, inner_r, outer_r, mass, dens = source_data
                
                # Update other materials in this ring that are missing metadata
                cursor.execute('''
                    UPDATE hotspot_data
                    SET ls_distance = COALESCE(ls_distance, ?),
                        ring_type = COALESCE(ring_type, ?),
                        inner_radius = COALESCE(inner_radius, ?),
                        outer_radius = COALESCE(outer_radius, ?),
                        ring_mass = COALESCE(ring_mass, ?),
                        density = COALESCE(density, ?)
                    WHERE system_name = ? AND body_name = ?
                      AND (ls_distance IS NULL OR ring_type IS NULL OR density IS NULL)
                ''', (ls_dist, ring_type, inner_r, outer_r, mass, dens, system_name, body_name))
                
                updated = cursor.rowcount
                if updated > 0:
                    total_updated += updated
                    print(f"✓ {system_name} - {body_name}: Updated {updated} materials")
        
        conn.commit()
        print(f"\n✅ Complete! Back-filled metadata to {total_updated} materials across {len(rings)} rings")

if __name__ == '__main__':
    try:
        backfill_ring_metadata()
        print("\n✓ Database updated successfully!")
        input("\nPress Enter to exit...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
