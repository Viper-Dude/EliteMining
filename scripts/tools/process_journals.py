"""
Journal Processing Utility for EliteMining
Processes journal files to populate hotspot and visited systems data
"""

import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from journal_parser import JournalParser
from user_database import UserDatabase
import glob


def process_journals_batch(max_files=None, progress_callback=None):
    """Process journal files in batches to populate user database
    
    Args:
        max_files: Maximum number of files to process (None for all)
        progress_callback: Callback function for progress updates
    """
    # Get Elite Dangerous journal directory
    journal_dir = os.path.expanduser(r"~\Saved Games\Frontier Developments\Elite Dangerous")
    
    if not os.path.exists(journal_dir):
        print(f"Journal directory not found: {journal_dir}")
        return
    
    # Create parser
    parser = JournalParser(journal_dir)
    
    # Get journal files
    journal_files = parser.find_journal_files()
    if not journal_files:
        print("No journal files found!")
        return
    
    # Limit files if specified
    if max_files and max_files < len(journal_files):
        # Take the most recent files
        journal_files = journal_files[-max_files:]
        print(f"Processing last {max_files} journal files out of {len(parser.find_journal_files())} total")
    else:
        print(f"Processing all {len(journal_files)} journal files")
    
    # Process files
    stats = parser.parse_all_journals(progress_callback)
    
    # Show results
    print(f"\nProcessing complete!")
    print(f"Files processed: {stats['files_processed']}")
    print(f"Events processed: {stats['events_processed']}")
    print(f"Hotspots found: {stats['hotspots_found']}")
    print(f"Systems visited: {stats['systems_visited']}")
    
    # Show database stats
    db_stats = parser.user_db.get_database_stats()
    print(f"\nDatabase stats: {db_stats}")
    
    return stats


def show_sample_hotspots(limit=10):
    """Show sample hotspot data from the database"""
    db = UserDatabase()
    
    try:
        import sqlite3
        with sqlite3.connect(db.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT system_name, body_name, material_name, hotspot_count, scan_date
                FROM hotspot_data 
                ORDER BY scan_date DESC 
                LIMIT ?
            ''', (limit,))
            
            results = cursor.fetchall()
            
            if results:
                print(f"\nRecent hotspot scans (last {len(results)}):")
                for row in results:
                    print(f"  {row['system_name']} - {row['body_name']} - {row['material_name']} ({row['hotspot_count']})")
            else:
                print("No hotspot data in database")
                
    except Exception as e:
        print(f"Error showing sample hotspots: {e}")


def clear_database():
    """Clear the user database (for testing)"""
    db_path = os.path.join(os.path.dirname(__file__), "user_data.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Cleared database: {db_path}")
    else:
        print("Database not found")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Process Elite Dangerous journal files for mining data")
    parser.add_argument("--max-files", type=int, help="Maximum number of journal files to process")
    parser.add_argument("--clear", action="store_true", help="Clear database before processing")
    parser.add_argument("--sample", action="store_true", help="Show sample hotspot data")
    
    args = parser.parse_args()
    
    if args.clear:
        clear_database()
    
    if args.sample:
        show_sample_hotspots()
    else:
        def progress_callback(current, total, stats):
            print(f"Progress: {current}/{total} files - Hotspots: {stats['hotspots_found']}, Systems: {stats['systems_visited']}")
        
        process_journals_batch(max_files=args.max_files, progress_callback=progress_callback)