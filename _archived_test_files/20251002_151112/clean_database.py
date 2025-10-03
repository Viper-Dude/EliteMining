"""
Clean Database - Remove ALL Hotspot Data
Completely wipes the hotspot_data table for fresh import
"""

import sqlite3
import os

def clean_database():
    """Remove ALL hotspot data from database"""
    
    print("CLEANING DATABASE - REMOVING ALL HOTSPOT DATA")
    print("=============================================")
    
    # Database path
    db_path = 'app/data/user_data.db'
    
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        return
    
    print(f"Database: {db_path}")
    
    with sqlite3.connect(db_path) as conn:
        # Step 1: Show current database status
        print("\n=== CURRENT DATABASE STATUS ===")
        cursor = conn.execute('SELECT COUNT(*) FROM hotspot_data')
        total_records = cursor.fetchone()[0]
        
        print(f"Total hotspot records: {total_records:,}")
        
        # Show breakdown by data source
        cursor = conn.execute('SELECT data_source, COUNT(*) FROM hotspot_data GROUP BY data_source')
        sources = cursor.fetchall()
        
        print("Records by source:")
        for source, count in sources:
            source_name = source if source else "Unknown/NULL"
            print(f"  {source_name}: {count:,}")
        
        # Step 2: Confirm deletion
        print(f"\n⚠️  WARNING: About to delete ALL {total_records:,} hotspot records!")
        print("This includes:")
        print("  - All EDTools data (corrected and old)")
        print("  - All personal journal data") 
        print("  - All galaxy database data")
        print("  - All manually imported data")
        
        response = input("\nProceed with complete deletion? (yes/NO): ").strip().lower()
        
        if response not in ['yes', 'y']:
            print("❌ Operation cancelled by user")
            return
        
        # Step 3: Delete ALL hotspot data
        print("\n=== DELETING ALL HOTSPOT DATA ===")
        cursor = conn.execute('DELETE FROM hotspot_data')
        deleted_count = cursor.rowcount
        
        conn.commit()
        
        print(f"✅ Deleted ALL hotspot records: {deleted_count:,}")
        
        # Step 4: Verify deletion
        cursor = conn.execute('SELECT COUNT(*) FROM hotspot_data')
        remaining = cursor.fetchone()[0]
        
        print(f"Remaining hotspot records: {remaining}")
        
        if remaining == 0:
            print("✅ Database completely cleaned!")
            print("Ready for fresh import of corrected data")
        else:
            print(f"⚠️  Warning: {remaining} records still remain")
        
        # Reset auto-increment counter
        cursor = conn.execute('DELETE FROM sqlite_sequence WHERE name = "hotspot_data"')
        conn.commit()
        print("✅ Reset auto-increment counter")

if __name__ == "__main__":
    clean_database()