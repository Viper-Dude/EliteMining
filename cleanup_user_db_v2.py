#!/usr/bin/env python3
"""
Clean up user database by comparing with Hotspots_bubble_cleaned.xlsx
This version handles UNIQUE constraints properly by merging duplicate entries
"""

import sqlite3
import pandas as pd
import os
from datetime import datetime
import re

def clean_user_database():
    """Clean up user database using Excel source file as reference"""
    
    # Paths
    db_path = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\user_data.db"
    excel_path = r"d:\My Apps Work Folder\Elitemining Working folder\Releases\EliteMining-Dev\app\data\Hotspots\Hotspots_bubble_cleaned.xlsx"
    
    print("🧹 EliteMining Database Cleanup Tool v2")
    print("=" * 50)
    print(f"Database: {os.path.basename(db_path)}")
    print(f"Excel source: {os.path.basename(excel_path)}")
    
    # Read Excel file
    print("\nReading Excel source file...")
    try:
        df = pd.read_excel(excel_path)
        print(f"Loaded {len(df)} rows from Excel")
        print(f"Columns: {df.columns.tolist()}")
        
        # Show sample data
        print(f"\nSample Excel data:")
        print(df.head())
        
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    # Create system name mapping
    print(f"\nCreating system name mapping...")
    system_mapping = create_system_mapping(df)
    print(f"Created {len(system_mapping)} system mappings")
    
    # Show some sample mappings
    print(f"\nSample mappings:")
    sample_items = list(system_mapping.items())[:10]
    for short, full in sample_items:
        print(f"   {short} → {full}")
    
    # Apply fixes to database with proper constraint handling
    print(f"\nApplying fixes to database...")
    fix_count = apply_database_fixes_v2(db_path, system_mapping)
    print(f"Fixed {fix_count} database entries")
    
    # Verify the fixes
    print(f"\nVerifying fixes...")
    verify_fixes(db_path)

def create_system_mapping(df):
    """Create mapping from truncated to full system names"""
    system_mapping = {}
    
    system_column = 'System'  # Column with full system names
    
    for _, row in df.iterrows():
        full_system = str(row[system_column]).strip()
        if full_system and full_system != 'nan':
            # Get truncated versions of this system name
            truncated_versions = get_truncated_versions(full_system)
            
            # Map each truncated version to the full name
            for truncated in truncated_versions:
                if truncated and len(truncated.strip()) > 0:
                    # Prefer the shortest mapping (most specific)
                    if truncated not in system_mapping or len(full_system) < len(system_mapping[truncated]):
                        system_mapping[truncated] = full_system
    
    return system_mapping

def get_truncated_versions(full_system_name):
    """Get possible truncated versions of a system name"""
    truncated = []
    
    # Split by spaces and common delimiters
    parts = re.split(r'\s+', full_system_name)
    
    if parts:
        # First word only (most common truncation)
        truncated.append(parts[0])
        
        # First two parts if second is a number or sector indicator
        if len(parts) > 1:
            second_part = parts[1]
            # Check if it's a number, +/- number, or sector indicator
            if (second_part.replace('+', '').replace('-', '').isdigit() or 
                second_part.lower() in ['sector', 'sys']):
                truncated.append(f"{parts[0]} {second_part}")
                
        # Sometimes include up to 3 parts for complex names
        if len(parts) > 2:
            third_part = parts[2]
            if third_part.lower() in ['sector', 'sys'] or third_part.replace('+', '').replace('-', '').isdigit():
                truncated.append(f"{parts[0]} {parts[1]} {third_part}")
    
    # Remove duplicates and empty strings
    return list(set([t for t in truncated if t.strip()]))

def apply_database_fixes_v2(db_path, system_mapping):
    """Apply fixes to the database with proper UNIQUE constraint handling"""
    
    fix_count = 0
    
    # Backup database first
    backup_path = db_path.replace('.db', f'_backup_v2_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"Created backup: {os.path.basename(backup_path)}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get all entries that need fixing
            cursor.execute("SELECT id, system_name, body_name, material_name, hotspot_count FROM hotspot_data")
            all_entries = cursor.fetchall()
            
            print(f"Checking {len(all_entries)} database entries...")
            
            # Group by what the corrected record would look like
            corrections_needed = {}
            entries_to_delete = []
            
            for entry_id, current_system_name, body_name, material_name, hotspot_count in all_entries:
                if current_system_name in system_mapping:
                    correct_system_name = system_mapping[current_system_name]
                    corrected_key = (correct_system_name, body_name, material_name)
                    
                    if corrected_key not in corrections_needed:
                        corrections_needed[corrected_key] = {
                            'entries': [],
                            'total_hotspots': 0,
                            'best_entry_id': entry_id
                        }
                    
                    corrections_needed[corrected_key]['entries'].append(entry_id)
                    corrections_needed[corrected_key]['total_hotspots'] += hotspot_count
                    
                    # Keep the entry with the most hotspots as primary
                    cursor.execute("SELECT hotspot_count FROM hotspot_data WHERE id = ?", 
                                 (corrections_needed[corrected_key]['best_entry_id'],))
                    current_best_count = cursor.fetchone()[0]
                    
                    if hotspot_count > current_best_count:
                        corrections_needed[corrected_key]['best_entry_id'] = entry_id
            
            print(f"Found {len(corrections_needed)} groups that need correction")
            
            # Apply corrections
            for (correct_system, body, material), correction_info in corrections_needed.items():
                entries = correction_info['entries']
                best_id = correction_info['best_entry_id']
                total_hotspots = correction_info['total_hotspots']
                
                if len(entries) == 1:
                    # Simple case: just update the system name
                    cursor.execute("""
                        UPDATE hotspot_data 
                        SET system_name = ?
                        WHERE id = ?
                    """, (correct_system, best_id))
                    fix_count += 1
                    
                else:
                    # Complex case: merge multiple entries
                    print(f"  Merging {len(entries)} entries for {correct_system} - {body} - {material}")
                    
                    # Update the best entry with corrected name and merged hotspot count
                    cursor.execute("""
                        UPDATE hotspot_data 
                        SET system_name = ?, hotspot_count = ?
                        WHERE id = ?
                    """, (correct_system, total_hotspots, best_id))
                    
                    # Delete the other entries
                    other_entries = [eid for eid in entries if eid != best_id]
                    for entry_id in other_entries:
                        cursor.execute("DELETE FROM hotspot_data WHERE id = ?", (entry_id,))
                    
                    fix_count += len(entries)
            
            conn.commit()
            
    except Exception as e:
        print(f"Error applying fixes: {e}")
        
        # Restore from backup
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, db_path)
            print("Restored database from backup")
        
        return 0
    
    return fix_count

def verify_fixes(db_path):
    """Verify that the fixes were applied correctly"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check for remaining truncated system names
            truncated_systems = ['Col', 'HIP', 'Praea', 'Wregoe', 'Synuefai', 'Pru', 'Synuefe', 'Swoiwns', 'Sifi', 'Coalsack']
            
            remaining_truncated = []
            for system in truncated_systems:
                cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE system_name = ?", (system,))
                count = cursor.fetchone()[0]
                if count > 0:
                    remaining_truncated.append((system, count))
            
            if remaining_truncated:
                print("Still have some truncated system names:")
                for system, count in remaining_truncated[:10]:  # Show top 10
                    print(f"   {system}: {count} entries")
            else:
                print("✅ No obvious truncated system names found")
            
            # Check coordinate coverage
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(x_coord) as with_coords
                FROM hotspot_data
            """)
            
            coord_stats = cursor.fetchone()
            print(f"Coordinate coverage: {coord_stats[1]}/{coord_stats[0]} ({coord_stats[1]/coord_stats[0]*100:.1f}%)")
            
            # Show some examples of corrected entries
            cursor.execute("""
                SELECT DISTINCT system_name
                FROM hotspot_data 
                WHERE system_name LIKE 'Col 285%' OR system_name LIKE 'HIP %'
                LIMIT 5
            """)
            
            examples = cursor.fetchall()
            if examples:
                print("\n✅ Examples of corrected system names:")
                for (system_name,) in examples:
                    print(f"   {system_name}")
                    
    except Exception as e:
        print(f"Error verifying fixes: {e}")

if __name__ == "__main__":
    clean_user_database()
    print("\n🎉 Database cleanup complete!")
    print("You can now test the ring finder to see if the results match EDTools better.")