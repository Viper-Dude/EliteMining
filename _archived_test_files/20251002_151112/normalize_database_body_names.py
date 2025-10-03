"""
One-time database cleanup script to normalize body names
Removes system name prefixes from body_name entries to ensure consistency

This script should be run ONCE after implementing the body name normalization fix.
After running, it can be safely deleted.
"""

import sqlite3
import os

def normalize_body_name(body_name: str, system_name: str) -> str:
    """Normalize body name by removing system name prefix if present"""
    if body_name and system_name:
        if body_name.lower().startswith(system_name.lower()):
            normalized = body_name[len(system_name):].strip()
            if normalized:
                return normalized
    return body_name

def main():
    db_path = r'd:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db'
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    print(f"\n{'='*80}")
    print(f"DATABASE BODY NAME NORMALIZATION")
    print(f"{'='*80}\n")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get all hotspot entries
        cursor.execute("SELECT id, system_name, body_name FROM hotspot_data")
        all_entries = cursor.fetchall()
        
        print(f"Found {len(all_entries)} total entries in database\n")
        
        entries_to_update = []
        
        # Check which entries need normalization
        for entry_id, system_name, body_name in all_entries:
            normalized = normalize_body_name(body_name, system_name)
            if normalized != body_name:
                entries_to_update.append((entry_id, system_name, body_name, normalized))
        
        if not entries_to_update:
            print("✅ No entries need normalization - database is already clean!")
            return
        
        print(f"Found {len(entries_to_update)} entries that need normalization:\n")
        
        # Show first 10 examples
        for i, (entry_id, system_name, old_name, new_name) in enumerate(entries_to_update[:10]):
            print(f"  {i+1}. ID {entry_id}: '{old_name}' → '{new_name}'")
        
        if len(entries_to_update) > 10:
            print(f"  ... and {len(entries_to_update) - 10} more\n")
        else:
            print()
        
        # Confirm before proceeding
        response = input("Proceed with normalization? (yes/no): ").strip().lower()
        
        if response != 'yes':
            print("\n❌ Aborted - no changes made")
            return
        
        print(f"\n{'='*80}")
        print("NORMALIZING BODY NAMES...")
        print(f"{'='*80}\n")
        
        updated_count = 0
        duplicate_count = 0
        
        for entry_id, system_name, old_name, new_name in entries_to_update:
            # Check if normalized name would create a duplicate
            cursor.execute('''
                SELECT id, data_source FROM hotspot_data 
                WHERE id != ? AND system_name = ? AND body_name = ?
            ''', (entry_id, system_name, new_name))
            
            potential_duplicate = cursor.fetchone()
            
            if potential_duplicate:
                dup_id, dup_source = potential_duplicate
                # Delete the entry with system prefix (keep the clean one)
                cursor.execute("DELETE FROM hotspot_data WHERE id = ?", (entry_id,))
                duplicate_count += 1
                print(f"  ✓ Removed duplicate ID {entry_id} (kept ID {dup_id})")
            else:
                # Update the body name
                cursor.execute('''
                    UPDATE hotspot_data 
                    SET body_name = ? 
                    WHERE id = ?
                ''', (new_name, entry_id))
                updated_count += 1
        
        conn.commit()
        
        print(f"\n{'='*80}")
        print("NORMALIZATION COMPLETE!")
        print(f"{'='*80}\n")
        print(f"✅ Updated: {updated_count} entries")
        print(f"✅ Removed duplicates: {duplicate_count} entries")
        print(f"✅ Total cleaned: {updated_count + duplicate_count} entries\n")
        
        # Verify final state
        cursor.execute("SELECT COUNT(*) FROM hotspot_data")
        final_count = cursor.fetchone()[0]
        print(f"Final database size: {final_count} entries\n")
        
    except Exception as e:
        print(f"\n❌ Error during normalization: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    print(f"{'='*80}\n")
    print("💡 This script can now be safely deleted.")
    print()

if __name__ == "__main__":
    main()
