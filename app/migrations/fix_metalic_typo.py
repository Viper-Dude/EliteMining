"""
Migration: Fix 'Metalic' Typo (v4.82)

Fixes the typo 'Metalic' → 'Metallic' in the ring_type column
of the hotspot_data table.

This typo was present in older journal parsers and prevents
proper duplicate detection when saving Spansh data.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

log = logging.getLogger(__name__)

MIGRATION_VERSION = "4.82_fix_metalic_typo"


def get_database_path():
    """Get the user database path for installer version"""
    # For installer: EliteMining\app\data\user_data.db
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        exe_dir = os.path.dirname(sys.executable)
        # exe is in EliteMining\Configurator, data is in EliteMining\app\data
        if os.path.basename(exe_dir).lower() == 'configurator':
            app_dir = os.path.dirname(exe_dir)
            data_dir = os.path.join(app_dir, 'app', 'data')
        else:
            data_dir = os.path.join(exe_dir, 'data')
    else:
        # Running from source
        script_dir = os.path.dirname(os.path.abspath(__file__))
        app_dir = os.path.dirname(script_dir)  # Go up from migrations to app
        data_dir = os.path.join(app_dir, 'data')
    
    return os.path.join(data_dir, 'user_data.db')


def is_migration_needed(db_path):
    """Check if this migration has already been applied"""
    if not os.path.exists(db_path):
        return False
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if migrations table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='migrations'
            """)
            if not cursor.fetchone():
                # Create migrations table
                cursor.execute("""
                    CREATE TABLE migrations (
                        id INTEGER PRIMARY KEY,
                        version TEXT UNIQUE,
                        applied_date TEXT
                    )
                """)
                conn.commit()
                return True  # New migrations table, run all migrations
            
            # Check if this specific migration was already applied
            cursor.execute("""
                SELECT version FROM migrations 
                WHERE version = ?
            """, (MIGRATION_VERSION,))
            
            if cursor.fetchone():
                log.info(f"[MIGRATION] {MIGRATION_VERSION} already applied - skipping")
                return False
            
            # Check if there are any rows with the typo
            cursor.execute("""
                SELECT COUNT(*) FROM hotspot_data 
                WHERE ring_type = 'Metalic'
            """)
            count = cursor.fetchone()[0]
            
            if count > 0:
                log.info(f"[MIGRATION] Found {count} rows with 'Metalic' typo - migration needed")
                return True
            else:
                # No typos found, but record migration anyway to prevent re-checking
                log.info(f"[MIGRATION] No 'Metalic' typos found - marking as applied")
                cursor.execute("""
                    INSERT INTO migrations (version, applied_date) 
                    VALUES (?, ?)
                """, (MIGRATION_VERSION, datetime.utcnow().isoformat() + "Z"))
                conn.commit()
                return False
                
    except Exception as e:
        log.error(f"[MIGRATION] Error checking if migration needed: {e}")
        return False


def run_migration(db_path):
    """Fix the 'Metalic' → 'Metallic' typo"""
    log.info(f"[MIGRATION {MIGRATION_VERSION}] Starting...")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Count rows before
            cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE ring_type = 'Metalic'")
            before_count = cursor.fetchone()[0]
            
            log.info(f"[MIGRATION {MIGRATION_VERSION}] Fixing {before_count} rows")
            
            # Fix the typo
            cursor.execute("""
                UPDATE hotspot_data 
                SET ring_type = 'Metallic' 
                WHERE ring_type = 'Metalic'
            """)
            
            rows_updated = cursor.rowcount
            
            # Verify
            cursor.execute("SELECT COUNT(*) FROM hotspot_data WHERE ring_type = 'Metalic'")
            after_count = cursor.fetchone()[0]
            
            # Record migration
            cursor.execute("""
                INSERT INTO migrations (version, applied_date) 
                VALUES (?, ?)
            """, (MIGRATION_VERSION, datetime.utcnow().isoformat() + "Z"))
            
            conn.commit()
            
            log.info(f"[MIGRATION {MIGRATION_VERSION}] ✓ Complete: {rows_updated} rows updated, {after_count} remaining")
            
            if after_count > 0:
                log.warning(f"[MIGRATION {MIGRATION_VERSION}] Warning: {after_count} rows still have 'Metalic'")
                return False
            
            return True
            
    except Exception as e:
        log.error(f"[MIGRATION {MIGRATION_VERSION}] Error: {e}", exc_info=True)
        return False


def main():
    """Run migration if needed"""
    db_path = get_database_path()
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return False
    
    print(f"Checking database: {db_path}")
    
    if is_migration_needed(db_path):
        print(f"Running migration: {MIGRATION_VERSION}")
        success = run_migration(db_path)
        if success:
            print("✓ Migration completed successfully")
            return True
        else:
            print("✗ Migration failed")
            return False
    else:
        print(f"Migration not needed or already applied")
        return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    success = main()
    sys.exit(0 if success else 1)
