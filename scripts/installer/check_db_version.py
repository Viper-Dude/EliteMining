#!/usr/bin/env python3
"""
Check database version for EliteMining database
"""

import sqlite3
import sys
from pathlib import Path

def get_database_version(db_path: str):
    """Get version from database_version table"""
    try:
        db_file = Path(db_path)
        if not db_file.exists():
            print(f"Database file not found: {db_path}")
            return None
            
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Check if version table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='database_version'")
        if not cursor.fetchone():
            print("No database_version table found - database version: 1.0.0 (default)")
            conn.close()
            return "1.0.0"
        
        # Get version
        cursor.execute("SELECT version FROM database_version ORDER BY version DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"Database version: {result[0]}")
            return result[0]
        else:
            print("Database version table exists but no version found - defaulting to 1.0.0")
            return "1.0.0"
        
    except Exception as e:
        print(f"Error reading database version: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: check_db_version.py <database_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    version = get_database_version(db_path)
    
    if version:
        sys.exit(0)
    else:
        sys.exit(1)