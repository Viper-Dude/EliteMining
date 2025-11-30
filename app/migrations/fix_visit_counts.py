"""
Migration: Fix Visit Counts (v4.6.5)

Recalculates visit_count for all systems in visited_systems table
by scanning journal files and counting unique timestamps.

This fixes inflated visit counts caused by duplicate event processing.
"""

import os
import sys
import glob
import json
import sqlite3
from collections import defaultdict
import logging

log = logging.getLogger(__name__)

MIGRATION_VERSION = "4.6.5_fix_visit_counts_v2"


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


def get_journal_dir():
    """Get Elite Dangerous journal directory"""
    saved_games = os.path.join(os.path.expanduser("~"), "Saved Games", 
                               "Frontier Developments", "Elite Dangerous")
    if os.path.isdir(saved_games):
        return saved_games
    return None


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
                return True
            
            # Check if this migration was already applied
            cursor.execute("SELECT 1 FROM migrations WHERE version = ?", 
                          (MIGRATION_VERSION,))
            return cursor.fetchone() is None
            
    except Exception as e:
        log.error(f"Error checking migration status: {e}")
        return False


def mark_migration_complete(db_path):
    """Mark this migration as completed"""
    try:
        with sqlite3.connect(db_path) as conn:
            from datetime import datetime
            conn.execute("""
                INSERT OR REPLACE INTO migrations (version, applied_date)
                VALUES (?, ?)
            """, (MIGRATION_VERSION, datetime.now().isoformat()))
            conn.commit()
    except Exception as e:
        log.error(f"Error marking migration complete: {e}")


def scan_journals_for_visits(journal_dir, progress_callback=None):
    """Scan all journals and count unique visits per system"""
    
    system_visits = defaultdict(set)  # system_name -> set of timestamps
    system_data = {}  # system_name -> metadata
    
    journal_pattern = os.path.join(journal_dir, "Journal.*.log")
    journal_files = sorted(glob.glob(journal_pattern))
    
    total_files = len(journal_files)
    
    for i, journal_path in enumerate(journal_files):
        if progress_callback and (i + 1) % 100 == 0:
            progress_callback(i + 1, total_files)
        
        try:
            with open(journal_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        event = json.loads(line.strip())
                        event_type = event.get('event', '')
                        
                        # Only count actual arrivals (FSDJump, CarrierJump), not Location events
                        # Location fires on game load - doesn't mean you traveled there
                        if event_type in ['FSDJump', 'CarrierJump']:
                            system_name = event.get('StarSystem', '')
                            timestamp = event.get('timestamp', '')
                            
                            if system_name and timestamp:
                                system_visits[system_name].add(timestamp)
                                
                                if system_name not in system_data:
                                    system_data[system_name] = {
                                        'first_visit': timestamp,
                                        'last_visit': timestamp,
                                        'system_address': event.get('SystemAddress'),
                                        'coords': event.get('StarPos', [])
                                    }
                                else:
                                    if timestamp > system_data[system_name]['last_visit']:
                                        system_data[system_name]['last_visit'] = timestamp
                                    if timestamp < system_data[system_name]['first_visit']:
                                        system_data[system_name]['first_visit'] = timestamp
                                        
                    except json.JSONDecodeError:
                        continue
        except Exception:
            continue
    
    # Build results
    results = {}
    for system_name, timestamps in system_visits.items():
        data = system_data.get(system_name, {})
        results[system_name] = {
            'visit_count': len(timestamps),
            'first_visit': data.get('first_visit', ''),
            'last_visit': data.get('last_visit', ''),
            'system_address': data.get('system_address'),
            'coords': data.get('coords', [])
        }
    
    return results


def apply_migration(db_path, visit_data):
    """Update database with corrected visit counts"""
    
    updated = 0
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if visited_systems table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='visited_systems'
            """)
            if not cursor.fetchone():
                log.info("No visited_systems table found, skipping migration")
                return 0
            
            for system_name, data in visit_data.items():
                cursor.execute(
                    'SELECT visit_count FROM visited_systems WHERE system_name = ?', 
                    (system_name,)
                )
                result = cursor.fetchone()
                
                if result:
                    old_count = result[0]
                    new_count = data['visit_count']
                    
                    if old_count != new_count:
                        cursor.execute('''
                            UPDATE visited_systems 
                            SET visit_count = ?,
                                first_visit_date = ?,
                                last_visit_date = ?
                            WHERE system_name = ?
                        ''', (new_count, data['first_visit'], data['last_visit'], system_name))
                        updated += 1
            
            conn.commit()
            
    except Exception as e:
        log.error(f"Error applying migration: {e}")
        return 0
    
    return updated


def run_migration(progress_callback=None):
    """
    Run the visit count fix migration.
    
    Args:
        progress_callback: Optional callback(current, total, message) for progress updates
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    db_path = get_database_path()
    
    if not os.path.exists(db_path):
        return True, "No database found, migration not needed"
    
    if not is_migration_needed(db_path):
        return True, "Migration already applied"
    
    journal_dir = get_journal_dir()
    if not journal_dir:
        return False, "Could not find Elite Dangerous journal directory"
    
    if progress_callback:
        progress_callback(0, 100, "Scanning journal files...")
    
    # Scan journals
    def scan_progress(current, total):
        if progress_callback:
            pct = int((current / total) * 80)  # 0-80% for scanning
            progress_callback(pct, 100, f"Scanning journals ({current}/{total})...")
    
    visit_data = scan_journals_for_visits(journal_dir, scan_progress)
    
    if not visit_data:
        mark_migration_complete(db_path)
        return True, "No visit data found in journals"
    
    if progress_callback:
        progress_callback(85, 100, "Updating database...")
    
    # Apply updates
    updated = apply_migration(db_path, visit_data)
    
    if progress_callback:
        progress_callback(95, 100, "Finalizing...")
    
    # Mark complete
    mark_migration_complete(db_path)
    
    if progress_callback:
        progress_callback(100, 100, "Complete")
    
    return True, f"Fixed visit counts for {updated} systems"


# Allow running standalone for testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("Running visit count fix migration...")
    
    def progress(current, total, message):
        print(f"  [{current}%] {message}")
    
    success, message = run_migration(progress)
    print(f"\nResult: {message}")
