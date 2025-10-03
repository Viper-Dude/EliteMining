"""
Fix malformed ring names in database
Fixes entries like "2 a A Ring" → "2 A Ring", "ABC 8 a A Ring" → "ABC 8 A Ring"
"""

import sqlite3
import os
import re

def normalize_ring_name(body_name: str) -> str:
    """Fix malformed ring names with lowercase letters"""
    if not body_name:
        return body_name
    
    # Fix patterns like "2 a A Ring" → "2 A Ring"
    body_name = re.sub(r'\s+a\s+([A-Z])\s+Ring', r' \1 Ring', body_name, flags=re.IGNORECASE)
    body_name = re.sub(r'\s+b\s+([A-Z])\s+Ring', r' \1 Ring', body_name, flags=re.IGNORECASE)
    body_name = re.sub(r'\s+c\s+([A-Z])\s+Ring', r' \1 Ring', body_name, flags=re.IGNORECASE)
    body_name = re.sub(r'\s+d\s+([A-Z])\s+Ring', r' \1 Ring', body_name, flags=re.IGNORECASE)
    
    # Ensure proper spacing
    body_name = ' '.join(body_name.split())
    
    return body_name

def main():
    db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"\n{'='*80}")
    print(f"FIX MALFORMED RING NAMES")
    print(f"{'='*80}\n")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all entries with malformed names
        cursor.execute("""
            SELECT id, system_name, body_name, material_name
            FROM hotspot_data 
            WHERE body_name LIKE '%a A%' OR body_name LIKE '%a B%' 
               OR body_name LIKE '%a C%' OR body_name LIKE '%a D%'
               OR body_name LIKE '%b A%' OR body_name LIKE '%b B%'
               OR body_name LIKE '%b C%' OR body_name LIKE '%c A%'
               OR body_name LIKE '%c B%' OR body_name LIKE '%d A%'
        """)
        
        all_malformed = cursor.fetchall()
        
        if not all_malformed:
            print("✅ No malformed ring names found - database is clean!")
            return
        
        print(f"Found {len(all_malformed)} malformed entries\n")
        
        # Show first 10 examples
        print("Examples of fixes:\n")
        for i, (entry_id, system, body, material) in enumerate(all_malformed[:10]):
            fixed = normalize_ring_name(body)
            print(f"  {i+1}. '{body}' → '{fixed}'")
        
        if len(all_malformed) > 10:
            print(f"  ... and {len(all_malformed) - 10} more\n")
        else:
            print()
        
        # Confirm
        response = input("Proceed with fixing malformed ring names? (yes/no): ").strip().lower()
        
        if response != 'yes':
            print("\n❌ Aborted - no changes made")
            return
        
        print(f"\n{'='*80}")
        print("FIXING RING NAMES...")
        print(f"{'='*80}\n")
        
        updated_count = 0
        duplicate_count = 0
        
        for entry_id, system, old_name, material in all_malformed:
            fixed_name = normalize_ring_name(old_name)
            
            if fixed_name == old_name:
                continue  # No change needed
            
            # Check if fixed name would create duplicate
            cursor.execute("""
                SELECT id FROM hotspot_data 
                WHERE id != ? AND system_name = ? AND body_name = ? AND material_name = ?
            """, (entry_id, system, fixed_name, material))
            
            duplicate = cursor.fetchone()
            
            if duplicate:
                # Delete the malformed entry (keep the good one)
                cursor.execute("DELETE FROM hotspot_data WHERE id = ?", (entry_id,))
                duplicate_count += 1
            else:
                # Update to fixed name
                cursor.execute("""
                    UPDATE hotspot_data 
                    SET body_name = ? 
                    WHERE id = ?
                """, (fixed_name, entry_id))
                updated_count += 1
        
        conn.commit()
        
        print(f"\n{'='*80}")
        print("FIX COMPLETE!")
        print(f"{'='*80}\n")
        print(f"✅ Updated: {updated_count} entries")
        print(f"✅ Removed duplicates: {duplicate_count} entries")
        print(f"✅ Total fixed: {updated_count + duplicate_count} entries\n")
        
        # Final verification
        cursor.execute("SELECT COUNT(*) FROM hotspot_data")
        final_count = cursor.fetchone()[0]
        print(f"Final database size: {final_count} entries\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
