"""
User Database Management for EliteMining
Handles hotspot data and visited systems tracking
"""

import os
import sqlite3
import logging
import math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from app_utils import get_app_data_dir

log = logging.getLogger("EliteMining.UserDatabase")


def calculate_ring_density(mass: float, inner_radius: float, outer_radius: float) -> Optional[float]:
    """
    Calculate ring density using area-based formula matching EDTools method.
    
    Formula: Density = M / π(R²outer - R²inner)
    Where radii are scaled by dividing by 1,000
    
    Args:
        mass: Ring mass (from journal, in game units)
        inner_radius: Inner radius in meters (from journal)
        outer_radius: Outer radius in meters (from journal)
    
    Returns:
        Calculated density as float, or None if calculation not possible
        
    Example:
        >>> calculate_ring_density(5965100000, 64972000, 66417000)
        10.00094414
    """
    try:
        # Validate inputs
        if mass <= 0 or inner_radius <= 0 or outer_radius <= 0:
            return None
            
        if outer_radius <= inner_radius:
            return None
        
        # Scale radii (divide by 1000 as per EDTools formula)
        r_inner_scaled = inner_radius / 1000
        r_outer_scaled = outer_radius / 1000
        
        # Calculate area: π(R²outer - R²inner)
        area = math.pi * (r_outer_scaled**2 - r_inner_scaled**2)
        
        if area <= 0:
            return None
        
        # Calculate density: M / area
        density = mass / area
        
        # Round to 6 decimal places for consistency with EDTools
        return round(density, 6)
        
    except (ValueError, TypeError, ZeroDivisionError) as e:
        log.warning(f"Failed to calculate density: {e}")
        return None


class UserDatabase:
    """Manages user-specific data including hotspots and visited systems"""
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the user database
        
        Args:
            db_path: Path to database file. If None, uses default location.
        """
        if db_path is None:
            # Place database in data directory using proper path resolution
            app_dir = get_app_data_dir()
            data_dir = os.path.join(app_dir, "data")
            
            # Create data directory if it doesn't exist
            os.makedirs(data_dir, exist_ok=True)
            
            db_path = os.path.join(data_dir, "user_data.db")
            
        self.db_path = db_path
        self._create_tables()
        self._run_migrations()
    
    def _get_migration_version(self, migration_name: str) -> int:
        """Get the version number for a specific migration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Create migration tracking table if it doesn't exist
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS migration_history (
                        migration_name TEXT PRIMARY KEY,
                        version INTEGER DEFAULT 0,
                        applied_at TEXT
                    )
                ''')
                cursor.execute('SELECT version FROM migration_history WHERE migration_name = ?', (migration_name,))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception:
            return 0
    
    def _set_migration_version(self, migration_name: str, version: int) -> None:
        """Set the version number for a specific migration"""
        try:
            from datetime import datetime
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO migration_history (migration_name, version, applied_at)
                    VALUES (?, ?, ?)
                ''', (migration_name, version, datetime.now().isoformat()))
                conn.commit()
        except Exception as e:
            print(f"[MIGRATION] Error setting migration version: {e}")
        
    def _run_migrations(self) -> None:
        """Run database migrations silently on startup (only runs each migration once)"""
        try:
            # Migration v4.4.6: Normalize material names to fix language duplicates
            self._migrate_material_names_v446()
            
            # v4.7.2: Apply overlap data from CSV file (version 3 - added new overlaps)
            if self._get_migration_version('overlap_csv') < 3:
                log.info("[Migration] Applying overlap data from CSV...")
                print("[MIGRATION] Applying overlap data from CSV...")
                self._apply_overlap_data_from_csv()
                self._set_migration_version('overlap_csv', 3)
            else:
                log.info("[Migration] Overlap CSV already applied (version 3)")
            
            # v4.7.2: Apply RES site data from CSV file (version 3 - added new RES sites)
            if self._get_migration_version('res_csv') < 3:
                log.info("[Migration] Applying RES site data from CSV...")
                print("[MIGRATION] Applying RES site data from CSV...")
                self._apply_res_data_from_csv()
                self._set_migration_version('res_csv', 3)
            else:
                log.info("[Migration] RES CSV already applied (version 3)")
            
            # v4.7.2: Merge hotspot data from bundled install database (one-time migration)
            # This adds 34K+ community hotspots while preserving user's existing data
            if self._get_migration_version('hotspot_merge_v472') < 1:
                log.info("[Migration] Merging hotspot data from bundled database...")
                print("[MIGRATION] Merging hotspot data from bundled database...")
                self._merge_hotspots_from_bundled_db()
                self._set_migration_version('hotspot_merge_v472', 1)
            else:
                log.info("[Migration] Hotspot merge v4.7.2 already applied")
            
            # v4.7.6: Fix corrupted body_name entries where body_name has wrong system prefix
            # e.g., system_name="Palliyan" but body_name="HIP 54072 A 1 A Ring"
            if self._get_migration_version('fix_body_name_prefix_v476') < 1:
                log.info("[Migration] Fixing corrupted body_name prefixes...")
                print("[MIGRATION] Fixing corrupted body_name prefixes...")
                self._fix_body_name_prefix_corruption()
                self._set_migration_version('fix_body_name_prefix_v476', 1)
            else:
                log.info("[Migration] Body name prefix fix v4.7.6 already applied")
            
            # v4.7.7: Normalize multi-star system names and backfill coordinates
            # e.g., system="HIP 39383 BC", body="3 A Ring" -> system="HIP 39383", body="BC 3 A Ring"
            if self._get_migration_version('normalize_multistar_systems') < 1:
                log.info("[Migration] Normalizing multi-star system names...")
                print("[MIGRATION] Normalizing multi-star system names...")
                self._normalize_multistar_system_names()
                self._set_migration_version('normalize_multistar_systems', 1)
            else:
                log.info("[Migration] Multi-star system normalization already applied")
                
        except Exception as e:
            print(f"[MIGRATION ERROR] {e}")
            log.error(f"[Migration] Error during migration: {e}")
            import traceback
            traceback.print_exc()
            log.error(traceback.format_exc())
    
    def _migrate_material_names_v446(self) -> None:
        """Migrate material names to English-only format (v4.4.6)
        
        Fixes duplicate hotspots caused by mixed language entries.
        Runs once, silently on first startup after v4.4.6 update.
        """
        # Inline normalization to avoid circular import with journal_parser
        def normalize_name(name: str) -> str:
            """Normalize material name to English canonical form"""
            # Common non-English mappings (German, French, Spanish, etc.)
            mappings = {
                # German names
                'tieftemperaturdiamanten': 'Low Temperature Diamonds',
                'alexandrit': 'Alexandrite',
                'bromellit': 'Bromellite',
                'grandidierit': 'Grandidierite',
                'monazit': 'Monazite',
                'painit': 'Painite',
                'benito it': 'Benitoite',
                'musgrafit': 'Musgravite',
                'rhodplumsit': 'Rhodplumsite',
                'serendibit': 'Serendibite',
                'tritium': 'Tritium',  # Same in all languages
                'platin': 'Platinum',
                'leereopal': 'Void Opals',
                'leerenopal': 'Void Opals',
                # Standard English variants
                'lowtemperaturediamond': 'Low Temperature Diamonds',
                'low temp diamonds': 'Low Temperature Diamonds',
                'low temperature diamonds': 'Low Temperature Diamonds',
                'opal': 'Void Opals',
                'void opal': 'Void Opals',
                'void opals': 'Void Opals',
            }
            
            lower_name = name.lower().strip()
            if lower_name in mappings:
                return mappings[lower_name]
            
            # Title case for standard names
            return name.strip().title()
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if migration needed by looking for non-English material names
                cursor.execute("SELECT DISTINCT material_name FROM hotspot_data")
                materials = [row[0] for row in cursor.fetchall()]
                
                updates_needed = {}
                for material_name in materials:
                    normalized = normalize_name(material_name)
                    if material_name != normalized:
                        updates_needed[material_name] = normalized
                
                if not updates_needed:
                    print("[MIGRATION v4.4.6] No non-English material names found - database is clean")
                    log.info("[Migration v4.4.6] No non-English material names found - database is clean")
                    return  # No migration needed
                
                print(f"[MIGRATION v4.4.6] Found {len(updates_needed)} material names to normalize:")
                log.info(f"[Migration v4.4.6] Found {len(updates_needed)} material names to normalize:")
                for old, new in updates_needed.items():
                    print(f"  '{old}' -> '{new}'")
                    log.info(f"  '{old}' -> '{new}'")
                
                for old_name, new_name in updates_needed.items():
                    # Check for duplicates that would be created
                    cursor.execute("""
                        SELECT DISTINCT h1.system_name, h1.body_name
                        FROM hotspot_data h1
                        WHERE h1.material_name = ?
                        AND EXISTS (
                            SELECT 1 FROM hotspot_data h2 
                            WHERE h2.system_name = h1.system_name 
                            AND h2.body_name = h1.body_name 
                            AND h2.material_name = ?
                        )
                    """, (old_name, new_name))
                    
                    duplicates = cursor.fetchall()
                    
                    if duplicates:
                        print(f"  [MIGRATION] Merging {len(duplicates)} duplicate entries for '{old_name}' -> '{new_name}'")
                        log.info(f"  Merging {len(duplicates)} duplicate entries for '{old_name}' -> '{new_name}'")
                    
                    # Merge duplicates: Keep the NEWER entry between old and new names
                    for system, body in duplicates:
                        # Get both entries
                        cursor.execute("""
                            SELECT id, scan_date, hotspot_count FROM hotspot_data
                            WHERE system_name = ? AND body_name = ? AND material_name IN (?, ?)
                            ORDER BY scan_date DESC
                        """, (system, body, old_name, new_name))
                        
                        entries = cursor.fetchall()
                        if len(entries) >= 2:
                            # Keep the newest entry, delete the rest
                            keep_id = entries[0][0]
                            cursor.execute("""
                                DELETE FROM hotspot_data
                                WHERE system_name = ? AND body_name = ? 
                                AND material_name IN (?, ?)
                                AND id != ?
                            """, (system, body, old_name, new_name, keep_id))
                            
                            # Update the kept entry to use the new name
                            cursor.execute("""
                                UPDATE hotspot_data 
                                SET material_name = ? 
                                WHERE id = ?
                            """, (new_name, keep_id))
                    
                    # Update remaining entries that don't have duplicates
                    cursor.execute("""
                        UPDATE hotspot_data 
                        SET material_name = ? 
                        WHERE material_name = ?
                    """, (new_name, old_name))
                
                conn.commit()
                print(f"[MIGRATION v4.4.6] ✅ Completed successfully - {len(updates_needed)} materials normalized")
                log.info(f"[Migration v4.4.6] Completed successfully - {len(updates_needed)} materials normalized")
                
        except Exception as e:
            print(f"[MIGRATION v4.4.6 ERROR] {e}")
            log.error(f"[Migration v4.4.6] Error: {e}")
            import traceback
            traceback.print_exc()
            raise
        
        # Migration v4.5.9: Clean up incorrectly extracted system names
        # Due to a bug in system name extraction from ring body names, some entries
        # were stored with wrong system names (e.g., "Omicron Capricorni B B" instead of "Omicron Capricorni B")
        # 
        # The bug pattern: System "X Y" with body "Z 3 A Ring" was incorrectly stored as
        # system "X Y Z" with body "3 A Ring" when current_system was not available.
        # 
        # Detection: Find system names ending with " X" (space + single letter) where body
        # starts with a number, and a matching correct entry exists.
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Find potentially incorrect entries:
                # - System name ends with space + single uppercase letter (A-Z)
                # - Body name starts with a digit
                # Pattern: "System Name X" | "1 A Ring" should be "System Name" | "X 1 A Ring"
                cursor.execute('''
                    SELECT DISTINCT h1.system_name, h1.body_name
                    FROM hotspot_data h1
                    WHERE h1.system_name GLOB '* [A-Z]'
                    AND h1.body_name GLOB '[0-9]*'
                ''')
                potential_duplicates = cursor.fetchall()
                
                if not potential_duplicates:
                    return
                
                total_deleted = 0
                systems_cleaned = set()
                
                for wrong_system, wrong_body in potential_duplicates:
                    # Extract the letter suffix from wrong system name
                    # e.g., "Omicron Capricorni B B" -> suffix="B", correct_system="Omicron Capricorni B"
                    parts = wrong_system.rsplit(' ', 1)
                    if len(parts) != 2:
                        continue
                    correct_system, letter_suffix = parts
                    
                    # Build what the correct body name should be
                    # e.g., wrong_body="4 B Ring", correct_body="B 4 B Ring"
                    correct_body = f"{letter_suffix} {wrong_body}"
                    
                    # Check if the correct entry exists
                    cursor.execute('''
                        SELECT COUNT(*) FROM hotspot_data 
                        WHERE system_name = ? AND body_name = ?
                    ''', (correct_system, correct_body))
                    
                    if cursor.fetchone()[0] > 0:
                        # Correct entry exists - this is a confirmed duplicate, delete the wrong one
                        cursor.execute('''
                            DELETE FROM hotspot_data 
                            WHERE system_name = ? AND body_name = ?
                        ''', (wrong_system, wrong_body))
                        deleted = cursor.rowcount
                        if deleted > 0:
                            total_deleted += deleted
                            systems_cleaned.add(wrong_system)
                
                if total_deleted > 0:
                    conn.commit()
                    print(f"[MIGRATION v4.5.9] ✅ Cleaned up {total_deleted} duplicate entries from {len(systems_cleaned)} incorrectly named system(s)")
                    for sys in sorted(systems_cleaned):
                        log.info(f"[Migration v4.5.9] Cleaned duplicates from '{sys}'")
                    
        except Exception as e:
            print(f"[MIGRATION v4.5.9 ERROR] {e}")
            log.error(f"[Migration v4.5.9] Error: {e}")
    
    def _apply_overlap_data_from_csv(self) -> None:
        """Apply overlap data from CSV file to hotspot entries
        
        Reads overlaps.csv from app/data folder and:
        1. Updates existing entries with overlap_tag (preserves user-set values)
        2. Inserts new entries for systems not in database
        
        CSV format: System,Body,Material,Overlap
        """
        import csv
        from datetime import datetime
        
        try:
            # Find the overlaps.csv file
            # Try relative to app/data directory first, then check common locations
            csv_paths = [
                os.path.join(os.path.dirname(__file__), 'data', 'overlaps.csv'),
                os.path.join(get_app_data_dir(), 'data', 'overlaps.csv'),  # For installed version
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'overlaps.csv'),
            ]
            
            # Log all paths being checked
            log.info(f"[Overlap CSV] Searching for overlaps.csv...")
            for path in csv_paths:
                exists = os.path.exists(path)
                log.info(f"[Overlap CSV] Checking: {path} - {'EXISTS' if exists else 'NOT FOUND'}")
            
            csv_path = None
            for path in csv_paths:
                if os.path.exists(path):
                    csv_path = path
                    break
            
            if not csv_path:
                # No CSV file found - this is normal for fresh installs
                log.warning("[Overlap CSV] No overlaps.csv found in any location")
                print("[MIGRATION] Warning: overlaps.csv not found")
                return
            
            log.info(f"[Overlap CSV] Using: {csv_path}")
            print(f"[MIGRATION] Found overlaps.csv at: {csv_path}")
            
            updated_count = 0
            inserted_count = 0
            skipped_count = 0
            scan_date = datetime.now().strftime('%Y-%m-%d')
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    for row in reader:
                        system_name = row.get('System', '').strip()
                        body_name = row.get('Body', '').strip()
                        material = row.get('Material', '').strip()
                        overlap = row.get('Overlap', '').strip()
                        
                        if not all([system_name, body_name, material, overlap]):
                            continue
                        
                        # Normalize body name
                        body_name = self._normalize_body_name(body_name, system_name)
                        
                        # Check if entry exists
                        cursor.execute('''
                            SELECT overlap_tag FROM hotspot_data 
                            WHERE system_name = ? AND body_name = ? AND material_name = ?
                        ''', (system_name, body_name, material))
                        
                        result = cursor.fetchone()
                        
                        if result is None:
                            # Entry doesn't exist - INSERT new entry with overlap data
                            cursor.execute('''
                                INSERT INTO hotspot_data 
                                (system_name, body_name, material_name, hotspot_count, scan_date, 
                                 overlap_tag, coord_source, data_source)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (system_name, body_name, material, 0, scan_date, 
                                  overlap, 'overlap_csv', 'Overlap CSV Import'))
                            inserted_count += 1
                            continue
                        
                        current_tag = result[0]
                        if current_tag is not None:
                            # User already has a tag set - don't overwrite
                            skipped_count += 1
                            continue
                        
                        # Apply the overlap tag to existing entry
                        cursor.execute('''
                            UPDATE hotspot_data 
                            SET overlap_tag = ?
                            WHERE system_name = ? AND body_name = ? AND material_name = ?
                        ''', (overlap, system_name, body_name, material))
                        
                        if cursor.rowcount > 0:
                            updated_count += 1
                    
                    conn.commit()
            
            total = updated_count + inserted_count
            if total > 0:
                print(f"[OVERLAP DATA] Applied {total} overlaps ({updated_count} updated, {inserted_count} inserted)")
                log.info(f"[Overlap Data] Applied {total} overlaps ({updated_count} updated, {inserted_count} inserted)")
                
        except Exception as e:
            # Don't fail startup if CSV processing fails
            print(f"[OVERLAP DATA] Warning: Could not apply overlap data: {e}")
            log.warning(f"[Overlap Data] Could not apply overlap data: {e}")
    
    def _apply_res_data_from_csv(self) -> None:
        """Apply RES (Resource Extraction Site) data from CSV file to hotspot entries
        
        Reads res_sites.csv from app/data folder and:
        1. Updates existing entries with res_tag (preserves user-set values)
        2. Inserts new entries for systems not in database
        
        CSV format: System,Body,Material,RES
        RES values: Hazardous, High, Low
        """
        import csv
        from datetime import datetime
        
        try:
            # Find the res_sites.csv file
            csv_paths = [
                os.path.join(os.path.dirname(__file__), 'data', 'res_sites.csv'),
                os.path.join(get_app_data_dir(), 'data', 'res_sites.csv'),  # For installed version
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'res_sites.csv'),
            ]
            
            # Log all paths being checked
            log.info(f"[RES CSV] Searching for res_sites.csv...")
            for path in csv_paths:
                exists = os.path.exists(path)
                log.info(f"[RES CSV] Checking: {path} - {'EXISTS' if exists else 'NOT FOUND'}")
            
            csv_path = None
            for path in csv_paths:
                if os.path.exists(path):
                    csv_path = path
                    break
            
            if not csv_path:
                # No CSV file found - this is normal for fresh installs
                log.warning("[RES CSV] No res_sites.csv found in any location")
                print("[MIGRATION] Warning: res_sites.csv not found")
                return
            
            log.info(f"[RES CSV] Using: {csv_path}")
            print(f"[MIGRATION] Found res_sites.csv at: {csv_path}")
            
            updated_count = 0
            inserted_count = 0
            skipped_count = 0
            scan_date = datetime.now().strftime('%Y-%m-%d')
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    
                    for row in reader:
                        system_name = row.get('System', '').strip()
                        body_name = row.get('Body', '').strip()
                        material = row.get('Material', '').strip()
                        res_type = row.get('RES', '').strip()
                        
                        if not all([system_name, body_name, material, res_type]):
                            continue
                        
                        # Normalize body name
                        body_name = self._normalize_body_name(body_name, system_name)
                        
                        # Check if entry exists
                        cursor.execute('''
                            SELECT res_tag FROM hotspot_data 
                            WHERE system_name = ? AND body_name = ? AND material_name = ?
                        ''', (system_name, body_name, material))
                        
                        result = cursor.fetchone()
                        
                        if result is None:
                            # Entry doesn't exist - INSERT new entry with RES data
                            cursor.execute('''
                                INSERT INTO hotspot_data 
                                (system_name, body_name, material_name, hotspot_count, scan_date, 
                                 res_tag, coord_source, data_source)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (system_name, body_name, material, 0, scan_date, 
                                  res_type, 'res_csv', 'RES CSV Import'))
                            inserted_count += 1
                            continue
                        
                        current_tag = result[0]
                        if current_tag is not None:
                            # User already has a tag set - don't overwrite
                            skipped_count += 1
                            continue
                        
                        # Apply the RES tag to existing entry
                        cursor.execute('''
                            UPDATE hotspot_data 
                            SET res_tag = ?
                            WHERE system_name = ? AND body_name = ? AND material_name = ?
                        ''', (res_type, system_name, body_name, material))
                        
                        if cursor.rowcount > 0:
                            updated_count += 1
                    
                    conn.commit()
            
            total = updated_count + inserted_count
            if total > 0:
                print(f"[RES DATA] Applied {total} RES sites ({updated_count} updated, {inserted_count} inserted)")
                log.info(f"[RES Data] Applied {total} RES sites ({updated_count} updated, {inserted_count} inserted)")
                
        except Exception as e:
            # Don't fail startup if CSV processing fails
            print(f"[RES DATA] Warning: Could not apply RES data: {e}")
            log.warning(f"[RES Data] Could not apply RES data: {e}")
    
    def _merge_hotspots_from_bundled_db(self) -> None:
        """Merge hotspot data from bundled install database (v4.7.2 one-time migration)
        
        This migration:
        1. Reads hotspots from the bundled 'UserDb for install/user_data.db'
        2. Adds ONLY hotspots that don't exist in user's database
        3. Does NOT overwrite any existing user data
        4. Does NOT touch visited_systems table
        
        This gives new installs AND existing users access to 34K+ community hotspots.
        """
        from datetime import datetime
        
        try:
            # Find the bundled database
            bundled_db_paths = [
                os.path.join(os.path.dirname(__file__), 'data', 'UserDb for install', 'user_data.db'),
                os.path.join(get_app_data_dir(), 'data', 'UserDb for install', 'user_data.db'),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app', 'data', 'UserDb for install', 'user_data.db'),
            ]
            
            log.info("[Migration v4.7.2] Searching for bundled hotspot database...")
            bundled_db_path = None
            for path in bundled_db_paths:
                exists = os.path.exists(path)
                log.info(f"[Migration v4.7.2] Checking: {path} - {'EXISTS' if exists else 'NOT FOUND'}")
                if exists:
                    bundled_db_path = path
                    break
            
            if not bundled_db_path:
                log.warning("[Migration v4.7.2] Bundled database not found - skipping migration")
                print("[MIGRATION v4.7.2] Bundled hotspot database not found - skipping")
                return
            
            # Don't try to merge with ourselves
            if os.path.normpath(bundled_db_path) == os.path.normpath(self.db_path):
                log.info("[Migration v4.7.2] Bundled DB is same as user DB - skipping")
                return
            
            print(f"[MIGRATION v4.7.2] Merging hotspots from: {bundled_db_path}")
            log.info(f"[Migration v4.7.2] Source database: {bundled_db_path}")
            
            inserted_count = 0
            skipped_count = 0
            
            # Open bundled database (read-only)
            bundled_conn = sqlite3.connect(f"file:{bundled_db_path}?mode=ro", uri=True)
            bundled_cursor = bundled_conn.cursor()
            
            # Get all hotspots from bundled database
            bundled_cursor.execute('''
                SELECT system_name, body_name, material_name, hotspot_count, scan_date,
                       system_address, body_id, x_coord, y_coord, z_coord, coord_source,
                       ring_type, ls_distance, density, data_source, 
                       inner_radius, outer_radius, ring_mass, overlap_tag, res_tag
                FROM hotspot_data
            ''')
            
            bundled_hotspots = bundled_cursor.fetchall()
            bundled_conn.close()
            
            log.info(f"[Migration v4.7.2] Found {len(bundled_hotspots)} hotspots in bundled database")
            print(f"[MIGRATION v4.7.2] Processing {len(bundled_hotspots)} hotspots...")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                for row in bundled_hotspots:
                    system_name, body_name, material_name = row[0], row[1], row[2]
                    
                    # Check if this hotspot already exists in user's database
                    cursor.execute('''
                        SELECT id FROM hotspot_data 
                        WHERE system_name = ? AND body_name = ? AND material_name = ?
                    ''', (system_name, body_name, material_name))
                    
                    if cursor.fetchone() is not None:
                        # Hotspot already exists - DO NOT overwrite user's data
                        skipped_count += 1
                        continue
                    
                    # Insert new hotspot (user doesn't have this one)
                    try:
                        cursor.execute('''
                            INSERT INTO hotspot_data 
                            (system_name, body_name, material_name, hotspot_count, scan_date,
                             system_address, body_id, x_coord, y_coord, z_coord, coord_source,
                             ring_type, ls_distance, density, data_source,
                             inner_radius, outer_radius, ring_mass, overlap_tag, res_tag)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', row)
                        inserted_count += 1
                    except sqlite3.IntegrityError:
                        # Race condition - entry was added between check and insert
                        skipped_count += 1
                
                conn.commit()
            
            total_in_user_db = 0
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM hotspot_data")
                total_in_user_db = cursor.fetchone()[0]
            
            print(f"[MIGRATION v4.7.2] Added {inserted_count} new hotspots, skipped {skipped_count} existing")
            print(f"[MIGRATION v4.7.2] User database now has {total_in_user_db} total hotspots")
            log.info(f"[Migration v4.7.2] Added {inserted_count} new hotspots, skipped {skipped_count} existing")
            log.info(f"[Migration v4.7.2] User database now has {total_in_user_db} total hotspots")
            
        except Exception as e:
            # Don't fail startup if migration fails
            print(f"[MIGRATION v4.7.2] Warning: Could not merge hotspots: {e}")
            log.warning(f"[Migration v4.7.2] Could not merge hotspots: {e}")
            import traceback
            log.error(traceback.format_exc())
    
    def _fix_body_name_prefix_corruption(self) -> None:
        """Fix corrupted body_name entries where body_name has wrong system prefix (v4.7.6)
        
        This fixes entries like:
        - system_name="Palliyan", body_name="HIP 54072 A 1 A Ring" 
        Should become:
        - system_name="HIP 54072", body_name="A 1 A Ring"
        
        The bug occurred when scanning rings in multi-star systems where the ring
        body name had a different system prefix than the current system.
        """
        import re
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Find entries where body_name contains a system-like prefix that doesn't match system_name
                # Pattern: body_name starts with letters/numbers but NOT with the system_name
                # and contains " Ring" indicating it's a full ring name with wrong prefix
                cursor.execute('''
                    SELECT id, system_name, body_name, material_name, hotspot_count, scan_date,
                           system_address, body_id, x_coord, y_coord, z_coord, coord_source,
                           ring_type, ls_distance, density, data_source,
                           inner_radius, outer_radius, ring_mass, overlap_tag, res_tag
                    FROM hotspot_data
                    WHERE body_name LIKE '% Ring'
                    AND body_name NOT LIKE system_name || ' %'
                    AND body_name GLOB '[A-Za-z]*'
                    AND LENGTH(body_name) > 15
                ''')
                
                corrupted_entries = cursor.fetchall()
                
                if not corrupted_entries:
                    print("[MIGRATION v4.7.6] No corrupted body_name prefixes found - database is clean")
                    log.info("[Migration v4.7.6] No corrupted body_name prefixes found - database is clean")
                    return
                
                print(f"[MIGRATION v4.7.6] Found {len(corrupted_entries)} entries with potentially corrupted body_name prefixes")
                log.info(f"[Migration v4.7.6] Found {len(corrupted_entries)} entries to check")
                
                fixed_count = 0
                deleted_duplicates = 0
                
                for row in corrupted_entries:
                    entry_id = row[0]
                    old_system = row[1]
                    old_body = row[2]
                    material_name = row[3]
                    
                    # Extract the real system name from the body_name
                    # Pattern: "HIP 54072 A 1 A Ring" -> system="HIP 54072", body="A 1 A Ring"
                    ring_match = re.search(r'\s+([A-Z]?\s*\d*\s*[A-Z]\s+Ring)$', old_body, re.IGNORECASE)
                    if not ring_match:
                        continue
                    
                    ring_part = ring_match.group(1).strip()
                    extracted_system = old_body[:ring_match.start()].strip()
                    
                    # Validate: extracted system should be different from stored system
                    if extracted_system.lower() == old_system.lower():
                        continue
                    
                    # Normalize the ring designation
                    normalized_body = ' '.join(ring_part.split())
                    
                    # Check if a correct entry already exists
                    cursor.execute('''
                        SELECT id FROM hotspot_data 
                        WHERE system_name = ? AND body_name = ? AND material_name = ?
                    ''', (extracted_system, normalized_body, material_name))
                    
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Correct entry already exists - delete the corrupted duplicate
                        cursor.execute('DELETE FROM hotspot_data WHERE id = ?', (entry_id,))
                        deleted_duplicates += 1
                        log.debug(f"[Migration v4.7.6] Deleted duplicate: {old_system}/{old_body} (correct entry exists for {extracted_system}/{normalized_body})")
                    else:
                        # Update the entry with correct system and body names
                        cursor.execute('''
                            UPDATE hotspot_data 
                            SET system_name = ?, body_name = ?
                            WHERE id = ?
                        ''', (extracted_system, normalized_body, entry_id))
                        fixed_count += 1
                        log.debug(f"[Migration v4.7.6] Fixed: {old_system}/{old_body} -> {extracted_system}/{normalized_body}")
                
                conn.commit()
                
                total_processed = fixed_count + deleted_duplicates
                if total_processed > 0:
                    print(f"[MIGRATION v4.7.6] ✅ Fixed {fixed_count} entries, removed {deleted_duplicates} duplicates")
                    log.info(f"[Migration v4.7.6] Fixed {fixed_count} entries, removed {deleted_duplicates} duplicates")
                else:
                    print("[MIGRATION v4.7.6] ✅ All entries verified - no fixes needed")
                    log.info("[Migration v4.7.6] All entries verified - no fixes needed")
                    
        except Exception as e:
            # Don't fail startup if migration fails
            print(f"[MIGRATION v4.7.6] Warning: Could not fix body_name prefixes: {e}")
            log.warning(f"[Migration v4.7.6] Could not fix body_name prefixes: {e}")
            import traceback
            log.error(traceback.format_exc())
    
    def _normalize_multistar_system_names(self) -> None:
        """Normalize multi-star system names for consistent database storage (v4.7.7)
        
        Multi-star systems like "HIP 39383 BC" should be stored as:
        - system_name: "HIP 39383" (base system, matches visited_systems for coordinates)
        - body_name: "BC 3 A Ring" (star designation moved to body name)
        
        This ensures coordinates can be found from visited_systems table and 
        hotspots appear immediately in searches.
        """
        import re
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Find entries where system_name ends with a star designation (A, B, AB, BC, etc.)
                # Pattern: ends with " A", " B", " AB", " BC", " ABC", etc.
                cursor.execute('''
                    SELECT id, system_name, body_name, material_name, hotspot_count, scan_date,
                           system_address, body_id, x_coord, y_coord, z_coord, coord_source,
                           ring_type, ls_distance, density, inner_radius, outer_radius, ring_mass
                    FROM hotspot_data
                    WHERE body_name LIKE '% Ring'
                ''')
                
                all_entries = cursor.fetchall()
                
                if not all_entries:
                    print("[MIGRATION v4.7.7] No ring entries to process")
                    log.info("[Migration v4.7.7] No ring entries to process")
                    return
                
                # Pattern to detect star designation at end of system name
                star_designation_pattern = re.compile(r'^(.+?)\s+([A-Z]{1,3})$')
                
                # Load visited_systems for coordinate lookup
                cursor.execute('SELECT system_name, x_coord, y_coord, z_coord FROM visited_systems WHERE x_coord IS NOT NULL')
                visited_systems = {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}
                
                # Also load galaxy database systems
                galaxy_systems = set()
                try:
                    from pathlib import Path
                    script_dir = Path(__file__).parent
                    galaxy_db_path = script_dir / "data" / "galaxy_systems.db"
                    if galaxy_db_path.exists():
                        with sqlite3.connect(str(galaxy_db_path)) as galaxy_conn:
                            galaxy_cursor = galaxy_conn.cursor()
                            galaxy_cursor.execute('SELECT name FROM systems')
                            galaxy_systems = {row[0] for row in galaxy_cursor.fetchall()}
                except Exception as e:
                    log.debug(f"[Migration v4.7.7] Could not load galaxy systems: {e}")
                
                fixed_count = 0
                coords_backfilled = 0
                deleted_duplicates = 0
                
                for row in all_entries:
                    entry_id = row[0]
                    old_system = row[1]
                    old_body = row[2]
                    material_name = row[3]
                    x_coord = row[8]
                    
                    # Skip if already has coordinates (likely already correct)
                    # But still check for system name normalization
                    
                    # Check if system name ends with star designation
                    match = star_designation_pattern.match(old_system)
                    if not match:
                        # No star designation - just try to backfill coordinates if missing
                        if x_coord is None and old_system in visited_systems:
                            coords = visited_systems[old_system]
                            cursor.execute('''
                                UPDATE hotspot_data 
                                SET x_coord = ?, y_coord = ?, z_coord = ?, coord_source = 'visited_systems'
                                WHERE id = ?
                            ''', (coords[0], coords[1], coords[2], entry_id))
                            coords_backfilled += 1
                        continue
                    
                    base_system = match.group(1)
                    star_designation = match.group(2)
                    
                    # Check if base system exists in visited_systems or galaxy database
                    base_exists = base_system in visited_systems or base_system in galaxy_systems
                    full_exists = old_system in visited_systems or old_system in galaxy_systems
                    
                    # Only normalize if base system exists but full name doesn't
                    if not base_exists:
                        # Base system not found - can't normalize, just try coordinate backfill
                        if x_coord is None and old_system in visited_systems:
                            coords = visited_systems[old_system]
                            cursor.execute('''
                                UPDATE hotspot_data 
                                SET x_coord = ?, y_coord = ?, z_coord = ?, coord_source = 'visited_systems'
                                WHERE id = ?
                            ''', (coords[0], coords[1], coords[2], entry_id))
                            coords_backfilled += 1
                        continue
                    
                    if full_exists:
                        # Full system name exists (e.g., "HIP 39383 BC" is a real system in galaxy)
                        # Don't normalize, just backfill coordinates if needed
                        if x_coord is None and old_system in visited_systems:
                            coords = visited_systems[old_system]
                            cursor.execute('''
                                UPDATE hotspot_data 
                                SET x_coord = ?, y_coord = ?, z_coord = ?, coord_source = 'visited_systems'
                                WHERE id = ?
                            ''', (coords[0], coords[1], coords[2], entry_id))
                            coords_backfilled += 1
                        continue
                    
                    # Base system exists but full name doesn't - normalize!
                    # Move star designation to body name
                    new_system = base_system
                    new_body = f"{star_designation} {old_body}" if not old_body.startswith(star_designation) else old_body
                    new_body = ' '.join(new_body.split())  # Clean up spacing
                    
                    # Check if normalized entry already exists
                    cursor.execute('''
                        SELECT id, x_coord FROM hotspot_data 
                        WHERE system_name = ? AND body_name = ? AND material_name = ?
                    ''', (new_system, new_body, material_name))
                    
                    existing = cursor.fetchone()
                    
                    if existing:
                        # Correct entry already exists - delete this one
                        cursor.execute('DELETE FROM hotspot_data WHERE id = ?', (entry_id,))
                        deleted_duplicates += 1
                        log.debug(f"[Migration v4.7.7] Deleted duplicate: {old_system}/{old_body} (correct entry exists)")
                    else:
                        # Update to normalized format
                        new_coords = visited_systems.get(new_system)
                        if new_coords:
                            cursor.execute('''
                                UPDATE hotspot_data 
                                SET system_name = ?, body_name = ?, 
                                    x_coord = ?, y_coord = ?, z_coord = ?, coord_source = 'visited_systems'
                                WHERE id = ?
                            ''', (new_system, new_body, new_coords[0], new_coords[1], new_coords[2], entry_id))
                            coords_backfilled += 1
                        else:
                            cursor.execute('''
                                UPDATE hotspot_data 
                                SET system_name = ?, body_name = ?
                                WHERE id = ?
                            ''', (new_system, new_body, entry_id))
                        fixed_count += 1
                        log.debug(f"[Migration v4.7.7] Normalized: {old_system}/{old_body} -> {new_system}/{new_body}")
                
                conn.commit()
                
                total_processed = fixed_count + deleted_duplicates + coords_backfilled
                if total_processed > 0:
                    print(f"[MIGRATION v4.7.7] ✅ Normalized {fixed_count} entries, backfilled {coords_backfilled} coordinates, removed {deleted_duplicates} duplicates")
                    log.info(f"[Migration v4.7.7] Normalized {fixed_count} entries, backfilled {coords_backfilled} coordinates, removed {deleted_duplicates} duplicates")
                else:
                    print("[MIGRATION v4.7.7] ✅ All entries verified - no fixes needed")
                    log.info("[Migration v4.7.7] All entries verified - no fixes needed")
                    
        except Exception as e:
            # Don't fail startup if migration fails
            print(f"[MIGRATION v4.7.7] Warning: Could not normalize multi-star systems: {e}")
            log.warning(f"[Migration v4.7.7] Could not normalize multi-star systems: {e}")
            import traceback
            log.error(traceback.format_exc())
        
    def _create_tables(self) -> None:
        """Create database tables if they don't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS hotspot_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        system_name TEXT NOT NULL,
                        body_name TEXT NOT NULL,
                        material_name TEXT NOT NULL,
                        hotspot_count INTEGER NOT NULL,
                        scan_date TEXT NOT NULL,
                        system_address INTEGER,
                        body_id INTEGER,
                        x_coord REAL,
                        y_coord REAL,
                        z_coord REAL,
                        coord_source TEXT,
                        UNIQUE(system_name, body_name, material_name)
                    )
                ''')
                
                # Add coordinate columns to existing hotspot_data table if they don't exist
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN x_coord REAL')
                    print("Added x_coord column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN y_coord REAL')
                    print("Added y_coord column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN z_coord REAL')
                    print("Added z_coord column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN coord_source TEXT')
                    print("Added coord_source column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN ring_type TEXT')
                    print("Added ring_type column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN ls_distance REAL')
                    print("Added ls_distance column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN inner_radius REAL')
                    print("Added inner_radius column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN outer_radius REAL')
                    print("Added outer_radius column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN ring_mass REAL')
                    print("Added ring_mass column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN density REAL')
                    print("Added density column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN overlap_tag TEXT')
                    print("Added overlap_tag column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                try:
                    conn.execute('ALTER TABLE hotspot_data ADD COLUMN res_tag TEXT')
                    print("Added res_tag column to hotspot_data")
                except sqlite3.OperationalError:
                    pass  # Column already exists
                
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS visited_systems (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        system_name TEXT NOT NULL UNIQUE,
                        system_address INTEGER,
                        x_coord REAL,
                        y_coord REAL, 
                        z_coord REAL,
                        first_visit_date TEXT NOT NULL,
                        last_visit_date TEXT NOT NULL,
                        visit_count INTEGER DEFAULT 1
                    )
                ''')
                
                # Create indexes for better query performance
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_hotspot_system 
                    ON hotspot_data(system_name)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_hotspot_body 
                    ON hotspot_data(body_name)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_visited_system 
                    ON visited_systems(system_name)
                ''')
                
                conn.commit()
                # Only log init message once per session to reduce log spam
                if not getattr(self.__class__, '_init_logged', False):
                    log.info(f"User database initialized: {self.db_path}")
                    self.__class__._init_logged = True
                
        except Exception as e:
            log.error(f"Error creating user database tables: {e}")
            raise
    
    def _normalize_body_name(self, body_name: str, system_name: str) -> str:
        """Normalize body name by removing system name prefix and fixing case issues
        
        This ensures consistency between EDTools data (e.g., "2 A Ring") and 
        journal data (e.g., "Paesia 2 A Ring"), and fixes malformed names like
        "2 a A Ring" → "2 A Ring".
        
        Args:
            body_name: Original body name
            system_name: System name to potentially remove from body name
            
        Returns:
            Normalized body name without system prefix and with proper casing
        """
        import re
        
        if not body_name:
            return body_name
            
        # First, remove system name prefix if present
        if system_name and body_name.lower().startswith(system_name.lower()):
            body_name = body_name[len(system_name):].strip()
            if not body_name:
                return body_name
        
        # IMPORTANT: Do NOT normalize lowercase letters in ring names!
        # Names like "2 a A Ring" and "2 A Ring" are DIFFERENT physical rings.
        # The lowercase letter (e.g., 'a', 'b', 'c') indicates the parent body designation.
        # Example: "Paesia 2 a A Ring" is a ring around planet "2 a", NOT planet "2".
        # These must remain distinct to prevent data corruption.
        
        # Ensure proper spacing
        body_name = ' '.join(body_name.split())
        
        return body_name
    
    def bulk_update_reserve_levels(self, system_name: str, reserve_levels: Dict[str, str]) -> int:
        """Bulk update reserve levels for all rings in a system
        
        Updates database entries with reserve levels from Spansh, but only if:
        - Existing value is NULL/missing
        - Existing value is numeric (old density data)
        - Existing value differs from new reserve level (mismatch)
        
        Args:
            system_name: Name of the star system
            reserve_levels: Dict mapping ring_name -> reserve_level (e.g., "1 B Ring" -> "Pristine")
            
        Returns:
            Number of entries updated
        """
        if not reserve_levels:
            return 0
        
        updated_count = 0
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get all hotspots for this system
                cursor.execute('''
                    SELECT DISTINCT body_name, density FROM hotspot_data
                    WHERE system_name = ?
                ''', (system_name,))
                
                all_entries = cursor.fetchall()
                
                if not all_entries:
                    return 0
                
                log.info(f"[BULK RESERVE] Found {len(all_entries)} unique rings in {system_name}")
                
                for body_name, existing_density in all_entries:
                    # Try to match this body_name with a reserve level
                    # Body name in DB is "2 A Ring", reserve_levels keys are "Tiraon 2 A Ring"
                    # So check if body_name is IN ring_name (not the other way around)
                    matched_reserve = None
                    
                    for ring_name, reserve_level in reserve_levels.items():
                        # Check if body_name is in ring_name (e.g., "2 A Ring" in "Tiraon 2 A Ring")
                        if body_name.lower() in ring_name.lower():
                            matched_reserve = reserve_level
                            break
                    
                    if not matched_reserve:
                        continue
                    
                    should_update = False
                    
                    if not existing_density:
                        # No existing value - update
                        should_update = True
                        log.info(f"[BULK RESERVE] {system_name} - {body_name}: NULL -> {matched_reserve}")
                    else:
                        # Check if existing is numeric (old density)
                        try:
                            float(existing_density)
                            should_update = True
                            log.info(f"[BULK RESERVE] {system_name} - {body_name}: {existing_density} (numeric) -> {matched_reserve}")
                        except (ValueError, TypeError):
                            # It's text - check for mismatch
                            if existing_density != matched_reserve:
                                should_update = True
                                log.info(f"[BULK RESERVE] {system_name} - {body_name}: {existing_density} -> {matched_reserve} (mismatch)")
                    
                    if should_update:
                        cursor.execute('''
                            UPDATE hotspot_data
                            SET density = ?
                            WHERE system_name = ? AND body_name = ?
                        ''', (matched_reserve, system_name, body_name))
                        updated_count += cursor.rowcount
                
                conn.commit()
                
                if updated_count > 0:
                    log.info(f"[BULK RESERVE] Updated {updated_count} entries in {system_name}")
                
        except Exception as e:
            log.error(f"[BULK RESERVE] Error updating reserve levels for {system_name}: {e}")
        
        return updated_count
    
    def check_ring_exists(self, system_name: str, body_name: str) -> bool:
        """Check if any hotspot entry exists for a ring in the database
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (ring)
            
        Returns:
            bool: True if any entry exists for this ring, False otherwise
        """
        try:
            # Normalize body name to match stored format
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ?
                ''', (system_name, body_name))
                
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            log.error(f"Error checking ring existence: {e}")
            return False
    
    def check_hotspot_exists(self, system_name: str, body_name: str, material_name: str) -> bool:
        """Check if a hotspot entry already exists in the database
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (ring)
            material_name: Name of the material
            
        Returns:
            bool: True if entry exists, False otherwise
        """
        try:
            # Normalize body name to match stored format
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (system_name, body_name, material_name))
                
                count = cursor.fetchone()[0]
                return count > 0
        except Exception as e:
            log.error(f"Error checking hotspot existence: {e}")
            return False
    
    def get_hotspot_data(self, system_name: str, body_name: str, material_name: str) -> Optional[dict]:
        """Get existing hotspot data for comparison
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (ring)
            material_name: Name of the material
            
        Returns:
            dict with hotspot data or None if not found
        """
        try:
            # Normalize body name to match stored format
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT hotspot_count, x_coord, y_coord, z_coord, ring_type, ls_distance
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (system_name, body_name, material_name))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'hotspot_count': row[0],
                        'x_coord': row[1],
                        'y_coord': row[2],
                        'z_coord': row[3],
                        'ring_type': row[4],
                        'ls_distance': row[5]
                    }
                return None
        except Exception as e:
            log.error(f"Error getting hotspot data: {e}")
            return None
    
    def get_reserve_level(self, system_name: str, body_name: str) -> Optional[str]:
        """Get reserve level for a ring
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (ring)
            
        Returns:
            Reserve level string or None
        """
        try:
            # Normalize body name to match stored format
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Query density column in hotspot_data (where bulk_update_reserve_levels stores it)
                cursor.execute('''
                    SELECT density FROM hotspot_data
                    WHERE system_name = ? AND body_name = ? AND density IS NOT NULL
                    LIMIT 1
                ''', (system_name, body_name))
                
                row = cursor.fetchone()
                
                if row and row[0]:
                    # Check if it's a reserve level string (not numeric density)
                    try:
                        float(row[0])
                        return None  # It's numeric density, not reserve level
                    except (ValueError, TypeError):
                        return row[0]  # It's a reserve level string (Pristine, Major, etc.)
                
                return None
                
        except Exception as e:
            log.error(f"Error getting reserve level: {e}")
            return None
    
    def set_reserve_level(self, system_name: str, body_name: str, reserve_level: Optional[str]) -> bool:
        """Set reserve level for a ring
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (ring)
            reserve_level: Reserve level ('Pristine', 'Major', 'Common', 'Low', 'Depleted') or None to clear
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Normalize body name to match stored format
            body_name = self._normalize_body_name(body_name, system_name)
            
            log.info(f"[SET RESERVE] Setting reserve for {system_name} - {body_name} to {reserve_level}")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if entries exist for this ring
                cursor.execute('''
                    SELECT COUNT(*) FROM hotspot_data
                    WHERE system_name = ? AND body_name = ?
                ''', (system_name, body_name))
                
                count = cursor.fetchone()[0]
                log.info(f"[SET RESERVE] Found {count} entries for this ring")
                
                if count > 0:
                    # Update existing entries
                    cursor.execute('''
                        UPDATE hotspot_data
                        SET density = ?
                        WHERE system_name = ? AND body_name = ?
                    ''', (reserve_level, system_name, body_name))
                    log.info(f"[SET RESERVE] Updated {cursor.rowcount} rows")
                elif reserve_level:
                    # No entries exist, create a placeholder
                    log.info(f"[SET RESERVE] No entries found, creating placeholder")
                    from datetime import datetime
                    scan_date = datetime.now().strftime('%Y-%m-%d')
                    cursor.execute('''
                        INSERT INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, scan_date, density)
                        VALUES (?, ?, ?, 0, ?, ?)
                    ''', (system_name, body_name, 'Unknown', scan_date, reserve_level))
                    log.info(f"[SET RESERVE] Inserted placeholder row")
                
                conn.commit()
                log.info(f"[SET RESERVE] Changes committed successfully")
                return True
                
        except Exception as e:
            log.error(f"Error setting reserve level: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def add_hotspot_data(self, system_name: str, body_name: str, material_name: str, 
                        hotspot_count: int, scan_date: str, system_address: Optional[int] = None,
                        body_id: Optional[int] = None, coordinates: Optional[Tuple[float, float, float]] = None,
                        coord_source: str = "journal", ring_type: Optional[str] = None,
                        ls_distance: Optional[float] = None, inner_radius: Optional[float] = None,
                        outer_radius: Optional[float] = None, ring_mass: Optional[float] = None,
                        density: Optional[float] = None) -> None:
        """Add or update hotspot data
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (ring)
            material_name: Name of the material (e.g., "Platinum")
            hotspot_count: Number of hotspots for this material
            scan_date: ISO format date string when the scan occurred
            system_address: Elite Dangerous system address
            body_id: Elite Dangerous body ID
            coordinates: (x, y, z) coordinates if available
            coord_source: Source of coordinates ('journal', 'visited_systems', 'edsm', 'unknown')
            ring_type: Type of ring ('Rocky', 'Metallic', 'Metal Rich', 'Icy', etc.)
            ls_distance: Distance from arrival star in light-seconds
            inner_radius: Inner radius of ring in meters
            outer_radius: Outer radius of ring in meters
            ring_mass: Ring mass (for density calculation)
            density: Pre-calculated density (from EDTools) or None to calculate
        """
        try:
            # Normalize body name to prevent duplicates between EDTools and journal data
            body_name = self._normalize_body_name(body_name, system_name)
            
            # Calculate density if not provided (EDTools) but we have mass and radii (journal)
            if density is None and ring_mass and inner_radius and outer_radius:
                density = calculate_ring_density(ring_mass, inner_radius, outer_radius)
                if density:
                    log.debug(f"Calculated density for {system_name} - {body_name}: {density}")
            
            # Get coordinates from visited_systems if not provided
            if coordinates is None:
                coordinates = self._get_coordinates_from_visited_systems(system_name)
                if coordinates:
                    coord_source = "visited_systems"
                else:
                    coord_source = "unknown"
            
            x_coord, y_coord, z_coord = coordinates or (None, None, None)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if this hotspot already exists
                cursor.execute('''
                    SELECT id, coord_source, ls_distance, ring_type, scan_date, hotspot_count
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (system_name, body_name, material_name))
                
                existing = cursor.fetchone()
                
                if existing:
                    existing_id, existing_coord_source, existing_ls, existing_ring_type, existing_date, existing_count = existing
                    
                    # Log existing data for debugging
                    log.debug(f"Found existing hotspot: {system_name} - {body_name} - {material_name} | coord_source={existing_coord_source} | ls={existing_ls} | type={existing_ring_type}")
                    log.debug(f"New data: coord_source={coord_source} | ls={ls_distance} | type={ring_type}")
                    
                    # Determine if we should update
                    should_update = False
                    update_reason = None
                    
                    # Check if we have ring_mass or density to add
                    cursor.execute('SELECT ring_mass, density, inner_radius, outer_radius FROM hotspot_data WHERE id = ?', (existing_id,))
                    extra_data_check = cursor.fetchone()
                    existing_mass, existing_density, existing_inner, existing_outer = extra_data_check if extra_data_check else (None, None, None, None)
                    
                    # Count completeness of new vs existing data
                    new_data_fields = [
                        ls_distance is not None,
                        ring_type is not None,
                        inner_radius is not None,
                        outer_radius is not None,
                        ring_mass is not None,
                        density is not None
                    ]
                    existing_data_fields = [
                        existing_ls is not None,
                        existing_ring_type is not None,
                        existing_inner is not None,
                        existing_outer is not None,
                        existing_mass is not None,
                        existing_density is not None
                    ]
                    
                    new_data_count = sum(new_data_fields)
                    existing_data_count = sum(existing_data_fields)
                    
                    # Journal scans with actual hotspot counts always override database entries with count=0
                    # This handles cases where old imports have count=0 but journal has real scan data
                    if hotspot_count > 0 and existing_count == 0:
                        should_update = True
                        update_reason = "journal scan data overrides empty count"
                    # Always update if hotspot count is higher (regardless of coord_source)
                    elif hotspot_count > existing_count:
                        should_update = True
                        update_reason = "higher hotspot count"
                    # Always update if it's a newer scan with new data (regardless of coord_source)
                    elif scan_date > existing_date and new_data_count > 0:
                        should_update = True
                        update_reason = "newer scan with data"
                    # Update if journal has more complete information
                    elif coord_source == "visited_systems":
                        # Check for ring mass/density updates
                        if (ring_mass and not existing_mass) or (density and not existing_density):
                            should_update = True
                            update_reason = "adding ring mass/density data"
                        # Update journal data with newer journal data
                        elif ls_distance and not existing_ls:
                            should_update = True
                            update_reason = "adding LS distance"
                        elif ring_type and not existing_ring_type:
                            should_update = True
                            update_reason = "adding ring type"
                        elif scan_date > existing_date and new_data_count >= existing_data_count:
                            # Only update if newer AND at least as complete
                            should_update = True
                            update_reason = f"newer scan date with equal/better data ({new_data_count}/{len(new_data_fields)} fields vs {existing_data_count}/{len(existing_data_fields)} fields)"
                        elif scan_date > existing_date and new_data_count < existing_data_count:
                            # Newer but less complete - don't overwrite good data
                            log.debug(f"Skipping update for {system_name} - {body_name} - {material_name}: newer scan but less complete ({new_data_count} vs {existing_data_count} fields)")
                            return
                        # Allow journal data to update entries with no coord_source (unknown origin)
                        elif existing_coord_source in (None, "", "unknown") and new_data_count > 0:
                            should_update = True
                            update_reason = "updating unknown-source data with journal data"
                        else:
                            log.debug(f"No update needed for {system_name} - {body_name} - {material_name}: existing_coord_source={existing_coord_source}, new_data_count={new_data_count}")
                    
                    if should_update:
                        log.debug(f"Updating hotspot ({update_reason}): {system_name} - {body_name} - {material_name}")
                        cursor.execute('''
                            UPDATE hotspot_data 
                            SET hotspot_count = ?, scan_date = ?, system_address = ?, body_id = ?,
                                x_coord = ?, y_coord = ?, z_coord = ?, coord_source = ?, 
                                ring_type = ?, ls_distance = ?, inner_radius = ?, outer_radius = ?,
                                ring_mass = ?, density = ?
                            WHERE id = ?
                        ''', (hotspot_count, scan_date, system_address, body_id,
                              x_coord, y_coord, z_coord, coord_source,
                              ring_type, ls_distance, inner_radius, outer_radius,
                              ring_mass, density, existing_id))
                    else:
                        log.debug(f"Skipping duplicate (no new info): {system_name} - {body_name} - {material_name}")
                        return
                else:
                    # Insert new hotspot
                    cursor.execute('''
                        INSERT INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, 
                         scan_date, system_address, body_id, x_coord, y_coord, z_coord, coord_source, 
                         ring_type, ls_distance, inner_radius, outer_radius, ring_mass, density)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (system_name, body_name, material_name, hotspot_count, 
                          scan_date, system_address, body_id, x_coord, y_coord, z_coord, coord_source, 
                          ring_type, ls_distance, inner_radius, outer_radius, ring_mass, density))
                    log.debug(f"Added hotspot: {system_name} - {body_name} - {material_name} x{hotspot_count}")
                
                # Back-fill ring metadata to other materials in the same ring
                # This ensures all materials in a ring share the same metadata (ls_distance, ring_type, density, etc.)
                if any([ls_distance, ring_type, inner_radius, outer_radius, ring_mass, density]):
                    cursor.execute('''
                        UPDATE hotspot_data
                        SET ls_distance = COALESCE(ls_distance, ?),
                            ring_type = COALESCE(ring_type, ?),
                            inner_radius = COALESCE(inner_radius, ?),
                            outer_radius = COALESCE(outer_radius, ?),
                            ring_mass = COALESCE(ring_mass, ?),
                            density = COALESCE(density, ?)
                        WHERE system_name = ? 
                          AND body_name = ? 
                          AND material_name != ?
                          AND (ls_distance IS NULL OR ring_type IS NULL OR density IS NULL)
                    ''', (ls_distance, ring_type, inner_radius, outer_radius, ring_mass, density,
                          system_name, body_name, material_name))
                    
                    updated_count = cursor.rowcount
                    if updated_count > 0:
                        log.info(f"Back-filled ring metadata to {updated_count} other materials in {system_name} - {body_name}")
                
                conn.commit()
                
        except Exception as e:
            log.error(f"Error adding hotspot data: {e}")

    def update_ring_metadata(self, system_name: str, body_name: str, ring_type: str = None,
                            ls_distance: float = None, inner_radius: float = None,
                            outer_radius: float = None, ring_mass: float = None,
                            density: float = None, reserve_level: str = None) -> int:
        """Update ring metadata for hotspots that are missing it
        
        This is called when a Scan event provides ring data after SAASignalsFound
        already created the hotspot records with NULL metadata.
        
        Args:
            system_name: Star system name
            body_name: Ring body name (e.g., "3 A Ring")
            ring_type: Ring type (Rocky, Metallic, Icy, Metal Rich)
            ls_distance: Distance from arrival star in light seconds
            inner_radius: Inner radius in meters
            outer_radius: Outer radius in meters
            ring_mass: Ring mass in megatons
            density: Calculated ring density (or reserve_level text from Spansh)
            reserve_level: Reserve level text from Spansh (Pristine, Major, Common, Low, Depleted)
            
        Returns:
            Number of records updated
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if existing density is old numeric data or reserve level text
                # Old data: numeric like "10.00094414", Reserve data: text like "Pristine"
                cursor.execute('''
                    SELECT density FROM hotspot_data
                    WHERE system_name = ? AND body_name = ?
                    LIMIT 1
                ''', (system_name, body_name))
                
                existing_density = cursor.fetchone()
                has_reserve_already = False
                existing_reserve = None
                
                log.info(f"[RESERVE] Checking {system_name} - {body_name}")
                log.info(f"[RESERVE] Existing density in DB: {existing_density[0] if existing_density and existing_density[0] else 'NULL'}")
                log.info(f"[RESERVE] New reserve_level from Spansh: {reserve_level if reserve_level else 'None'}")
                
                if existing_density and existing_density[0]:
                    # Check if existing value is reserve level (text) vs old density (number)
                    try:
                        float(existing_density[0])
                        # It's a number - old density data, can be overwritten
                        has_reserve_already = False
                        log.info(f"[RESERVE] Existing value is NUMERIC (old density) - can overwrite")
                    except (ValueError, TypeError):
                        # It's text - already has reserve level
                        has_reserve_already = True
                        existing_reserve = existing_density[0]
                        log.info(f"[RESERVE] Existing value is TEXT (reserve level) - checking for mismatch")
                
                # Update strategy:
                # 1. If new reserve_level exists and (no old reserve OR mismatch) - update
                # 2. If new reserve_level matches existing reserve - skip
                # 3. If no reserve_level - only update if density is NULL
                if reserve_level:
                    if not has_reserve_already:
                        # No existing reserve (NULL or numeric) - update
                        log.info(f"[RESERVE] UPDATING density to: {reserve_level}")
                        cursor.execute('''
                            UPDATE hotspot_data
                            SET ring_type = COALESCE(ring_type, ?),
                                ls_distance = COALESCE(ls_distance, ?),
                                inner_radius = COALESCE(inner_radius, ?),
                                outer_radius = COALESCE(outer_radius, ?),
                                ring_mass = COALESCE(ring_mass, ?),
                                density = ?
                            WHERE system_name = ? 
                              AND body_name = ?
                        ''', (ring_type, ls_distance, inner_radius, outer_radius, ring_mass, reserve_level,
                              system_name, body_name))
                    elif existing_reserve != reserve_level:
                        # Has reserve but it's different - update with new data
                        log.info(f"[RESERVE] MISMATCH - Updating from '{existing_reserve}' to '{reserve_level}'")
                        cursor.execute('''
                            UPDATE hotspot_data
                            SET ring_type = COALESCE(ring_type, ?),
                                ls_distance = COALESCE(ls_distance, ?),
                                inner_radius = COALESCE(inner_radius, ?),
                                outer_radius = COALESCE(outer_radius, ?),
                                ring_mass = COALESCE(ring_mass, ?),
                                density = ?
                            WHERE system_name = ? 
                              AND body_name = ?
                        ''', (ring_type, ls_distance, inner_radius, outer_radius, ring_mass, reserve_level,
                              system_name, body_name))
                    else:
                        # Has reserve and it matches - skip
                        log.info(f"[RESERVE] SKIPPING update - reserve level matches ('{existing_reserve}')")
                        cursor.execute('''
                            UPDATE hotspot_data
                            SET ring_type = COALESCE(ring_type, ?),
                                ls_distance = COALESCE(ls_distance, ?),
                                inner_radius = COALESCE(inner_radius, ?),
                                outer_radius = COALESCE(outer_radius, ?),
                                ring_mass = COALESCE(ring_mass, ?)
                            WHERE system_name = ? 
                              AND body_name = ?
                        ''', (ring_type, ls_distance, inner_radius, outer_radius, ring_mass,
                              system_name, body_name))
                else:
                    # No reserve level from Spansh - only update if density is NULL
                    log.info(f"[RESERVE] No reserve from Spansh - using calculated density: {density}")
                    cursor.execute('''
                        UPDATE hotspot_data
                        SET ring_type = COALESCE(ring_type, ?),
                            ls_distance = COALESCE(ls_distance, ?),
                            inner_radius = COALESCE(inner_radius, ?),
                            outer_radius = COALESCE(outer_radius, ?),
                            ring_mass = COALESCE(ring_mass, ?),
                            density = COALESCE(density, ?)
                        WHERE system_name = ? 
                          AND body_name = ?
                          AND (ring_type IS NULL OR ls_distance IS NULL OR density IS NULL)
                    ''', (ring_type, ls_distance, inner_radius, outer_radius, ring_mass, density,
                          system_name, body_name))
                
                updated = cursor.rowcount
                conn.commit()
                
                if updated > 0:
                    log.info(f"Updated ring metadata for {updated} hotspots in {system_name} - {body_name}")
                
                return updated
                
        except Exception as e:
            log.error(f"Error updating ring metadata: {e}")
            return 0

    def _get_coordinates_from_visited_systems(self, system_name: str) -> Optional[Tuple[float, float, float]]:
        """Get coordinates for a system from visited_systems table"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT x_coord, y_coord, z_coord 
                    FROM visited_systems 
                    WHERE system_name = ? AND x_coord IS NOT NULL
                ''', (system_name,))
                
                result = cursor.fetchone()
                if result:
                    return (result[0], result[1], result[2])
                return None
                
        except Exception as e:
            log.error(f"Error getting coordinates for {system_name}: {e}")
            return None
    
    def get_system_hotspots(self, system_name: str) -> List[Dict[str, Any]]:
        """Get all hotspot data for a specific system
        
        Args:
            system_name: Name of the star system
            
        Returns:
            List of dictionaries containing hotspot data
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM hotspot_data 
                    WHERE system_name = ? 
                    ORDER BY body_name, material_name
                ''', (system_name,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            log.error(f"Error getting system hotspots: {e}")
            return []
    
    def get_body_hotspots(self, system_name: str, body_name: str) -> List[Dict[str, Any]]:
        """Get hotspot data for a specific body in a system
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body
            
        Returns:
            List of dictionaries containing hotspot data (deduplicated and summed)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT 
                        system_name,
                        body_name,
                        material_name,
                        SUM(hotspot_count) as total_hotspot_count,
                        MAX(scan_date) as latest_scan_date
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ?
                    GROUP BY system_name, body_name, UPPER(material_name)
                    ORDER BY material_name
                ''', (system_name, body_name))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        'system_name': row[0],
                        'body_name': row[1], 
                        'material_name': row[2],
                        'hotspot_count': row[3],
                        'scan_date': row[4]
                    })
                
                return results
                
        except Exception as e:
            log.error(f"Error getting body hotspots: {e}")
            return []
    
    def get_ls_distance(self, system_name: str, body_name: str) -> Optional[float]:
        """Get LS distance for a body from database
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (e.g., "2 A Ring")
            
        Returns:
            LS distance in light-seconds if available, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ls_distance 
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ?
                      AND ls_distance IS NOT NULL
                    LIMIT 1
                ''', (system_name, body_name))
                
                result = cursor.fetchone()
                if result:
                    log.debug(f"Retrieved LS distance from database: {system_name} - {body_name} = {result[0]} Ls")
                    return result[0]
                return None
                
        except Exception as e:
            log.error(f"Error getting LS distance for {system_name} - {body_name}: {e}")
            return None
    
    def get_ring_metadata(self, system_name: str, body_name: str) -> Optional[dict]:
        """Get ring metadata from database (for previously scanned rings)
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body (e.g., "2 A Ring")
            
        Returns:
            Dictionary with ring_type, ls_distance, density, etc. if available, None otherwise
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT ring_type, ls_distance, density, inner_radius, outer_radius, ring_mass
                    FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ?
                      AND (ring_type IS NOT NULL OR ls_distance IS NOT NULL)
                    LIMIT 1
                ''', (system_name, body_name))
                
                result = cursor.fetchone()
                if result:
                    metadata = {
                        'ring_type': result[0],
                        'ls_distance': result[1],
                        'density': result[2],
                        'inner_radius': result[3],
                        'outer_radius': result[4],
                        'ring_mass': result[5]
                    }
                    log.debug(f"Retrieved ring metadata from database: {system_name} - {body_name} = {metadata}")
                    return metadata
                return None
                
        except Exception as e:
            log.error(f"Error getting ring metadata for {system_name} - {body_name}: {e}")
            return None
    
    def format_hotspots_for_display(self, system_name: str, body_name: str) -> str:
        """Format hotspots for display in Ring Finder table
        
        Args:
            system_name: Name of the star system
            body_name: Name of the celestial body
            
        Returns:
            Formatted string like "Platinum (3), Painite (2)" or "-" if no data
        """
        hotspots = self.get_body_hotspots(system_name, body_name)
        
        if not hotspots:
            return "-"
        
        # Format as "Material (count), Material (count)"
        formatted = []
        for hotspot in hotspots:
            material = hotspot['material_name']
            count = hotspot['hotspot_count']
            formatted.append(f"{material} ({count})")
        
        return ", ".join(formatted)
    
    def add_visited_system(self, system_name: str, visit_date: str, 
                          system_address: Optional[int] = None,
                          coordinates: Optional[Tuple[float, float, float]] = None) -> None:
        """Add or update visited system data
        
        Args:
            system_name: Name of the star system
            visit_date: ISO format date string when visited
            system_address: Elite Dangerous system address
            coordinates: (x, y, z) coordinates if available
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Check if system already exists
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT visit_count, first_visit_date, last_visit_date FROM visited_systems 
                    WHERE system_name = ?
                ''', (system_name,))
                
                result = cursor.fetchone()
                
                if result:
                    visit_count, first_visit, last_visit = result
                    
                    # Only increment visit count if this visit is NEWER than the last recorded visit
                    # This prevents:
                    # 1. Duplicate counting from multiple sources processing same event (same timestamp)
                    # 2. Re-counting old visits when catchup scan re-processes old journals
                    if visit_date > last_visit:
                        conn.execute('''
                            UPDATE visited_systems 
                            SET last_visit_date = ?, visit_count = visit_count + 1
                            WHERE system_name = ?
                        ''', (visit_date, system_name))
                        log.debug(f"Updated visit to system: {system_name} (visit #{visit_count + 1})")
                    else:
                        # Same or older timestamp - already recorded, skip increment
                        log.debug(f"Skipping duplicate/old visit record for: {system_name}")
                else:
                    # Insert new record
                    x_coord, y_coord, z_coord = coordinates or (None, None, None)
                    conn.execute('''
                        INSERT INTO visited_systems 
                        (system_name, system_address, x_coord, y_coord, z_coord,
                         first_visit_date, last_visit_date, visit_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                    ''', (system_name, system_address, x_coord, y_coord, z_coord,
                          visit_date, visit_date))
                    log.debug(f"New system visited: {system_name}")
                
                conn.commit()
                
        except Exception as e:
            log.error(f"Error adding visited system: {e}")
    
    def get_total_visits_count(self) -> int:
        """Get total count of visited systems (used to detect first install)
        
        Returns:
            Number of unique systems visited
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM visited_systems')
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            log.error(f"Error getting visits count: {e}")
            return 0
    
    def is_system_visited(self, system_name: str) -> Optional[Dict[str, Any]]:
        """Check if a system has been visited
        
        Args:
            system_name: Name of the star system
            
        Returns:
            Dictionary with visit data or None if never visited
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT * FROM visited_systems 
                    WHERE system_name = ?
                ''', (system_name,))
                
                result = cursor.fetchone()
                return dict(result) if result else None
                
        except Exception as e:
            log.error(f"Error checking visited system '{system_name}': {e}")
            return None
    
    def format_visited_status(self, system_name: str) -> str:
        """Format visited status for display in Ring Finder table
        
        Args:
            system_name: Name of the star system
            
        Returns:
            Formatted string like "Yes (2024-09-15)" or "Never"
        """
        visit_data = self.is_system_visited(system_name)
        
        if not visit_data:
            return "Never"
        
        last_visit = visit_data['last_visit_date']
        visit_count = visit_data['visit_count']
        
        try:
            # Parse the date and format it nicely
            date_obj = datetime.fromisoformat(last_visit.replace('Z', '+00:00'))
            date_str = date_obj.strftime('%Y-%m-%d')
            
            if visit_count == 1:
                return f"Yes ({date_str})"
            else:
                return f"{visit_count} visits ({date_str})"
                
        except Exception:
            # Fallback if date parsing fails
            if visit_count == 1:
                return "Yes"
            else:
                return f"{visit_count} visits"
    
    def get_last_visited_system(self) -> Optional[str]:
        """Get the most recently visited system from the database.
        
        This is used to initialize the visit tracking on app startup,
        allowing detection of carrier jumps that occurred while the app was offline.
        
        Returns:
            Name of the most recently visited system, or None if no visits recorded
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT system_name FROM visited_systems 
                    ORDER BY last_visit_date DESC
                    LIMIT 1
                ''')
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            log.error(f"Error getting last visited system: {e}")
            return None
    
    def has_visited_system(self, system_name: str) -> bool:
        """Check if the player has ever visited a system
        
        Args:
            system_name: Name of the star system
            
        Returns:
            True if system has been visited, False otherwise
        """
        visit_data = self.is_system_visited(system_name)
        return visit_data is not None
    
    def update_visit_count(self, system_name: str, new_count: int) -> bool:
        """Update the visit count for a system (for manual correction)
        
        Args:
            system_name: Name of the star system
            new_count: New visit count (0 to delete the record)
            
        Returns:
            True if update was successful
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if new_count <= 0:
                    # Delete the visit record
                    cursor.execute('''
                        DELETE FROM visited_systems WHERE system_name = ?
                    ''', (system_name,))
                    log.info(f"Deleted visit record for: {system_name}")
                else:
                    # Check if record exists
                    cursor.execute('SELECT 1 FROM visited_systems WHERE system_name = ?', (system_name,))
                    exists = cursor.fetchone() is not None
                    
                    # Get current timestamp for the update
                    from datetime import datetime
                    current_timestamp = datetime.utcnow().isoformat() + "Z"
                    
                    if exists:
                        # Update existing record - also update last_visit_date
                        cursor.execute('''
                            UPDATE visited_systems 
                            SET visit_count = ?, last_visit_date = ?
                            WHERE system_name = ?
                        ''', (new_count, current_timestamp, system_name))
                    else:
                        # Create new record
                        cursor.execute('''
                            INSERT INTO visited_systems 
                            (system_name, first_visit_date, last_visit_date, visit_count)
                            VALUES (?, ?, ?, ?)
                        ''', (system_name, current_timestamp, current_timestamp, new_count))
                    
                    log.info(f"Updated visit count for {system_name} to {new_count}")
                
                conn.commit()
                return True
                
        except Exception as e:
            log.error(f"Error updating visit count: {e}")
            return False

    def set_overlap_tag(self, system_name: str, body_name: str, material_name: str, overlap_tag: Optional[str]) -> bool:
        """Set overlap tag for a specific hotspot
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            material_name: Name of the material (e.g., "Platinum")
            overlap_tag: Overlap value ('2x', '3x') or None to clear
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Normalize body name
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Try UPDATE first
                cursor.execute('''
                    UPDATE hotspot_data 
                    SET overlap_tag = ?
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (overlap_tag, system_name, body_name, material_name))
                
                # If no row updated and we have a value to set, INSERT new row
                if cursor.rowcount == 0 and overlap_tag:
                    from datetime import datetime
                    scan_date = datetime.now().strftime('%Y-%m-%d')
                    cursor.execute('''
                        INSERT INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, scan_date, overlap_tag)
                        VALUES (?, ?, ?, 1, ?, ?)
                    ''', (system_name, body_name, material_name, scan_date, overlap_tag))
                
                conn.commit()
                return True
        except Exception as e:
            log.error(f"Error setting overlap tag: {e}")
            return False
    
    def get_overlap_tag(self, system_name: str, body_name: str, material_name: str) -> Optional[str]:
        """Get overlap tag for a specific hotspot
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            material_name: Name of the material
            
        Returns:
            Overlap tag ('2x', '3x') or None if not set
        """
        try:
            # Normalize body name
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT overlap_tag FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (system_name, body_name, material_name))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            log.error(f"Error getting overlap tag: {e}")
            return None
    
    def set_res_tag(self, system_name: str, body_name: str, material_name: str, res_tag: Optional[str]) -> bool:
        """Set RES tag for a specific hotspot
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            material_name: Name of the material (e.g., "Platinum")
            res_tag: RES value ('Hazardous', 'High', 'Low') or None to clear
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Normalize body name
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Try UPDATE first
                cursor.execute('''
                    UPDATE hotspot_data 
                    SET res_tag = ?
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (res_tag, system_name, body_name, material_name))
                
                # If no row updated and we have a value to set, INSERT new row
                if cursor.rowcount == 0 and res_tag:
                    from datetime import datetime
                    scan_date = datetime.now().strftime('%Y-%m-%d')
                    cursor.execute('''
                        INSERT INTO hotspot_data 
                        (system_name, body_name, material_name, hotspot_count, scan_date, res_tag)
                        VALUES (?, ?, ?, 1, ?, ?)
                    ''', (system_name, body_name, material_name, scan_date, res_tag))
                
                conn.commit()
                return True
        except Exception as e:
            log.error(f"Error setting RES tag: {e}")
            return False
    
    def get_res_tag(self, system_name: str, body_name: str, material_name: str) -> Optional[str]:
        """Get RES tag for a specific hotspot
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            material_name: Name of the material
            
        Returns:
            RES tag ('Hazardous', 'High', 'Low') or None if not set
        """
        try:
            # Normalize body name
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT res_tag FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND material_name = ?
                ''', (system_name, body_name, material_name))
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            log.error(f"Error getting RES tag: {e}")
            return None
    
    def get_overlaps_for_ring(self, system_name: str, body_name: str) -> List[Dict]:
        """Get all overlap tags for a ring
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            
        Returns:
            List of dicts with material_name and overlap_tag for materials with tags
        """
        try:
            # Normalize body name
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT material_name, overlap_tag FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND overlap_tag IS NOT NULL
                    ORDER BY material_name
                ''', (system_name, body_name))
                results = cursor.fetchall()
                return [{'material_name': r[0], 'overlap_tag': r[1]} for r in results]
        except Exception as e:
            log.error(f"Error getting overlaps for ring: {e}")
            return []
    
    def get_res_for_ring(self, system_name: str, body_name: str) -> List[Dict]:
        """Get all RES tags for a ring
        
        Args:
            system_name: Name of the star system
            body_name: Name of the ring body
            
        Returns:
            List of dicts with material_name and res_tag for materials with RES tags
        """
        try:
            # Normalize body name
            body_name = self._normalize_body_name(body_name, system_name)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT material_name, res_tag FROM hotspot_data 
                    WHERE system_name = ? AND body_name = ? AND res_tag IS NOT NULL
                    ORDER BY material_name
                ''', (system_name, body_name))
                results = cursor.fetchall()
                return [{'material_name': r[0], 'res_tag': r[1]} for r in results]
        except Exception as e:
            log.error(f"Error getting RES for ring: {e}")
            return []
    
    def get_database_stats(self) -> Dict[str, int]:
        """Get statistics about the database contents
        
        Returns:
            Dictionary with counts of hotspots and visited systems
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('SELECT COUNT(*) FROM hotspot_data')
                hotspot_count = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(DISTINCT system_name || body_name) FROM hotspot_data')
                unique_bodies = cursor.fetchone()[0]
                
                cursor.execute('SELECT COUNT(*) FROM visited_systems')
                visited_count = cursor.fetchone()[0]
                
                return {
                    'total_hotspots': hotspot_count,
                    'unique_bodies': unique_bodies,
                    'visited_systems': visited_count
                }
                
        except Exception as e:
            log.error(f"Error getting database stats: {e}")
            return {'total_hotspots': 0, 'unique_bodies': 0, 'visited_systems': 0}
    
    def _get_nearby_visited_systems(self, center_x: float, center_y: float, center_z: float, 
                                   max_distance: float, exclude_system: str = "") -> List[Dict[str, Any]]:
        """Get visited systems within specified distance from reference coordinates
        
        Args:
            center_x, center_y, center_z: Reference coordinates 
            max_distance: Maximum distance in light years
            exclude_system: System name to exclude from results
            
        Returns:
            List of systems with name, distance, and coordinates
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Query visited systems with coordinates
                query = '''
                    SELECT DISTINCT system_name, x_coord, y_coord, z_coord
                    FROM visited_systems 
                    WHERE x_coord IS NOT NULL AND y_coord IS NOT NULL AND z_coord IS NOT NULL
                      AND system_name != ?
                '''
                
                cursor.execute(query, (exclude_system,))
                results = cursor.fetchall()
                
                nearby_systems = []
                max_distance_squared = max_distance * max_distance
                
                for row in results:
                    system_name, x, y, z = row
                    
                    # Calculate 3D distance
                    dx = center_x - x
                    dy = center_y - y  
                    dz = center_z - z
                    dist_squared = dx*dx + dy*dy + dz*dz
                    
                    if dist_squared <= max_distance_squared:
                        distance = dist_squared ** 0.5
                        nearby_systems.append({
                            'name': system_name,
                            'distance': distance,
                            'coordinates': {'x': x, 'y': y, 'z': z}
                        })
                
                # Sort by distance
                nearby_systems.sort(key=lambda s: s['distance'])
                return nearby_systems
                
        except Exception as e:
            log.error(f"Error searching nearby visited systems: {e}")
            return []