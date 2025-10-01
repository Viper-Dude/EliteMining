#!/usr/bin/env python3
"""
Clean up user database by comparing with Hotspots_bubble_cleaned.xlsx
This will fix truncated system names and ensure data consistency
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
    
    print("🧹 EliteMining Database Cleanup Tool")
    print("=" * 50)
    print(f"📊 Database: {os.path.basename(db_path)}")
    print(f"📄 Excel source: {os.path.basename(excel_path)}")
    print()
    
    # Check if files exist
    if not os.path.exists(db_path):
        print(f"❌ Database not found: {db_path}")
        return
    
    if not os.path.exists(excel_path):
        print(f"❌ Excel file not found: {excel_path}")
        print("Available Excel files in directory:")
        for file in os.listdir(os.path.dirname(excel_path)):
            if file.endswith('.xlsx'):
                print(f"   - {file}")
        return
    
    try:
        # Read Excel file
        print("📖 Reading Excel source file...")
        df = pd.read_excel(excel_path)
        print(f"✅ Loaded {len(df)} rows from Excel")
        print(f"📋 Columns: {list(df.columns)}")
        print()
        
        # Show sample Excel data
        print("🔍 Sample Excel data:")
        print(df.head().to_string())
        print()
        
        # Create system name mapping from Excel data
        print("🗺️ Creating system name mapping...")
        system_mapping = create_system_mapping(df)
        print(f"✅ Created {len(system_mapping)} system mappings")
        
        # Show some mapping examples
        print("\n📝 Sample mappings:")
        for i, (short, full) in enumerate(list(system_mapping.items())[:10]):
            print(f"   {short} → {full}")
        print()
        
        # Apply fixes to database
        print("🔧 Applying fixes to database...")
        fix_count = apply_database_fixes(db_path, system_mapping)
        print(f"✅ Fixed {fix_count} database entries")
        
        # Verify fixes
        print("\n🔍 Verifying fixes...")
        verify_fixes(db_path)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def create_system_mapping(df):
    """Create mapping from truncated system names to full system names"""
    
    system_mapping = {}
    
    # Try different column name possibilities
    system_col = None
    body_col = None
    
    for col in df.columns:
        col_lower = str(col).lower()
        if 'system' in col_lower and system_col is None:
            system_col = col
        if any(word in col_lower for word in ['body', 'ring', 'planet']) and body_col is None:
            body_col = col
    
    if not system_col:
        print("⚠️ Could not find system column in Excel file")
        print(f"Available columns: {list(df.columns)}")
        return {}
    
    print(f"📍 Using system column: {system_col}")
    if body_col:
        print(f"🪐 Using body column: {body_col}")
    
    # Process each row to create mappings
    for _, row in df.iterrows():
        try:
            full_system = str(row[system_col]).strip()
            if pd.isna(full_system) or full_system == 'nan':
                continue
            
            # Create various truncated versions that might be in the database
            truncated_versions = get_truncated_versions(full_system)
            
            for truncated in truncated_versions:
                if truncated and truncated != full_system:
                    system_mapping[truncated] = full_system
                    
        except Exception as e:
            continue
    
    return system_mapping

def get_truncated_versions(full_system_name):
    """Generate possible truncated versions of a system name"""
    
    truncated = []
    
    # Split by spaces and take first word(s)
    parts = full_system_name.split()
    
    if len(parts) > 1:
        # First word only (most common truncation)
        truncated.append(parts[0])
        
        # First two words
        if len(parts) > 2:
            truncated.append(' '.join(parts[:2]))
        
        # Handle special cases
        if parts[0] in ['Col', 'HIP', 'HD', 'HR', 'LHS', 'LTT', 'BD+73', 'BD-12']:
            # These often get truncated to just the prefix
            truncated.append(parts[0])
            
            # Sometimes include the number
            if len(parts) > 1 and parts[1].replace('+', '').replace('-', '').isdigit():
                truncated.append(f"{parts[0]} {parts[1]}")
    
    # Remove duplicates and empty strings
    return list(set([t for t in truncated if t.strip()]))

def apply_database_fixes(db_path, system_mapping):
    """Apply fixes to the database"""
    
    fix_count = 0
    
    # Backup database first
    backup_path = db_path.replace('.db', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"💾 Created backup: {os.path.basename(backup_path)}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get all entries that need fixing
            cursor.execute("SELECT id, system_name FROM hotspot_data")
            all_entries = cursor.fetchall()
            
            print(f"🔍 Checking {len(all_entries)} database entries...")
            
            # Process each entry
            for entry_id, current_system_name in all_entries:
                if current_system_name in system_mapping:
                    correct_system_name = system_mapping[current_system_name]
                    
                    # Update the system name
                    cursor.execute("""
                        UPDATE hotspot_data 
                        SET system_name = ? 
                        WHERE id = ?
                    """, (correct_system_name, entry_id))
                    
                    fix_count += 1
                    
                    if fix_count % 100 == 0:
                        print(f"   📝 Fixed {fix_count} entries...")
            
            conn.commit()
            print(f"✅ Applied {fix_count} fixes to database")
            
    except Exception as e:
        print(f"❌ Error applying fixes: {e}")
        # Restore backup if something went wrong
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, db_path)
            print("🔄 Restored database from backup")
    
    return fix_count

def verify_fixes(db_path):
    """Verify that fixes were applied correctly"""
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check for remaining truncated system names
            cursor.execute("""
                SELECT system_name, COUNT(*) as count
                FROM hotspot_data 
                WHERE system_name IN ('Col', 'HIP', 'Praea', 'Wregoe', 'Synuefai', 'Pru', 'Synuefe', 'Swoiwns', 'Sifi', 'Coalsack')
                GROUP BY system_name
                ORDER BY count DESC
            """)
            
            remaining_truncated = cursor.fetchall()
            
            if remaining_truncated:
                print("⚠️ Still have some truncated system names:")
                for system, count in remaining_truncated:
                    print(f"   {system}: {count} entries")
            else:
                print("✅ No obvious truncated system names found")
            
            # Check coordinate coverage
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(x_coord) as with_coords,
                    COUNT(*) - COUNT(x_coord) as without_coords
                FROM hotspot_data
            """)
            
            coord_stats = cursor.fetchone()
            print(f"📍 Coordinate coverage: {coord_stats[1]}/{coord_stats[0]} ({coord_stats[1]/coord_stats[0]*100:.1f}%)")
            
            # Show some examples of fixed entries
            cursor.execute("""
                SELECT system_name, body_name, material_name
                FROM hotspot_data 
                WHERE material_name = 'Low Temp. Diamonds'
                AND system_name NOT IN ('Col', 'HIP', 'Praea', 'Wregoe')
                LIMIT 5
            """)
            
            examples = cursor.fetchall()
            if examples:
                print("\n✅ Examples of properly named systems:")
                for system, body, material in examples:
                    print(f"   {system} - {body} - {material}")
                    
    except Exception as e:
        print(f"❌ Error verifying fixes: {e}")

if __name__ == "__main__":
    clean_user_database()
    print("\n🎉 Database cleanup complete!")
    print("You can now test the ring finder to see if the results match EDTools better.")