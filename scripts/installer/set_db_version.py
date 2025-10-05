#!/usr/bin/env python3
"""
Set database version for EliteMining installer database
"""

import sqlite3
import sys
from pathlib import Path

def set_database_version(db_path: str, version: str):
    """Set version in database_version table"""
    try:
        db_file = Path(db_path)
        if not db_file.exists():
            print(f"Database file not found: {db_path}")
            return False
            
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Create version table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS database_version (
                version TEXT PRIMARY KEY,
                updated_date TEXT DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Insert or update version (clean first to avoid duplicates)
        cursor.execute('DELETE FROM database_version')
        cursor.execute('''
            INSERT INTO database_version (version, updated_date) 
            VALUES (?, datetime('now'))
        ''', (version,))
        
        conn.commit()
        conn.close()
        
        print(f"Successfully set database version to: {version}")
        return True
        
    except Exception as e:
        print(f"Error setting database version: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: set_db_version.py <database_path> <version>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    version = sys.argv[2]
    
    if set_database_version(db_path, version):
        sys.exit(0)
    else:
        sys.exit(1)