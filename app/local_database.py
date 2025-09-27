"""
Local Systems Database Manager for Elite Mining Tool

This module handles downloading, caching, and querying EDSM bulk data locally
to provide comprehensive spatial system searches without relying on broken APIs.
"""

import os
import sqlite3
import gzip
import json
import math
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from datetime import datetime, timedelta
import threading
import time

class LocalSystemsDatabase:
    """Manages local systems database for spatial searches"""
    
    def __init__(self, cache_dir: str = None):
        """Initialize the local database manager
        
        Args:
            cache_dir: Directory to store database files. If None, uses app data directory.
        """
        # Try to find bundled database first (installed with app)
        script_dir = Path(__file__).parent
        bundled_db_path = script_dir / "data" / "galaxy_systems.db"
        
        if bundled_db_path.exists():
            # Use bundled database (no cache dir needed)
            self.db_path = bundled_db_path
            self.cache_dir = bundled_db_path.parent
            self.is_bundled = True
            print(f"✅ Using bundled galaxy database: {self.db_path}")
        else:
            # Fallback to old behavior for development/testing
            if cache_dir is None:
                app_data = os.path.expanduser("~/.elitemining")
                os.makedirs(app_data, exist_ok=True)
                cache_dir = app_data
                
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(exist_ok=True)
            self.db_path = self.cache_dir / "systems.db"
            self.is_bundled = False
            print(f"⚠️ No bundled database found, using cache: {self.db_path}")
            
        self.download_path = self.cache_dir / "systemsPopulated.json.gz"
        self.metadata_path = self.cache_dir / "database_metadata.json"
        
        # EDSM populated systems URL (306 MB) - fallback for development
        self.edsm_url = "https://www.edsm.net/dump/systemsPopulated.json.gz"
        
        # Download state
        self.is_downloading = False
        self.download_progress = 0.0
        self.download_status = "Ready"
        self.download_error = None
        
        # Query cache for performance
        self.query_cache = {}
        self.cache_max_size = 100  # Maximum cached queries
        self.cache_timeout = 3600  # Cache timeout in seconds (1 hour)
        
    def is_database_available(self) -> bool:
        """Check if local database exists and is usable"""
        return self.db_path.exists() and self._verify_database()
        
    def get_database_info(self) -> Dict:
        """Get information about the current database"""
        info = {"exists": self.db_path.exists()}
        
        if not info["exists"]:
            return info
            
        try:
            # Get basic file info
            info["size_mb"] = round(self.db_path.stat().st_size / (1024 * 1024), 1)
            info["is_bundled"] = self.is_bundled
            
            # Try to get metadata if available
            if self.metadata_path.exists():
                with open(self.metadata_path, 'r') as f:
                    metadata = json.load(f)
                info.update(metadata)
                info["age_days"] = (datetime.now() - datetime.fromisoformat(metadata.get("created_at", datetime.now().isoformat()))).days
            else:
                # For bundled database, get info from database itself
                if self.is_bundled:
                    try:
                        conn = sqlite3.connect(str(self.db_path))
                        cursor = conn.cursor()
                        cursor.execute("SELECT value FROM metadata WHERE key = 'systems_count'")
                        systems_count = cursor.fetchone()
                        if systems_count:
                            info["systems_count"] = int(systems_count[0])
                        
                        cursor.execute("SELECT value FROM metadata WHERE key = 'created'")
                        created = cursor.fetchone()
                        if created:
                            info["created_at"] = created[0]
                            info["age_days"] = (datetime.now() - datetime.fromisoformat(created[0])).days
                        conn.close()
                    except:
                        info["age_days"] = 0
                        
            return info
        except Exception:
            return {"exists": False}
            
    def needs_update(self, max_age_days: int = 7) -> bool:
        """Check if database needs updating"""
        info = self.get_database_info()
        if not info.get("exists", False):
            return True
        return info.get("age_days", 999) > max_age_days
        
    def download_systems_data(self, progress_callback: Callable[[float, str], None] = None) -> bool:
        """Download EDSM populated systems data
        
        Args:
            progress_callback: Function called with (progress_percent, status_message)
            
        Returns:
            True if download successful, False otherwise
        """
        if self.is_downloading:
            return False
            
        self.is_downloading = True
        self.download_progress = 0.0
        self.download_status = "Starting download..."
        self.download_error = None
        
        try:
            # Download with progress tracking
            if progress_callback:
                progress_callback(0.0, "Connecting to EDSM...")
                
            response = requests.get(self.edsm_url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            if progress_callback:
                progress_callback(5.0, f"Downloading {total_size / (1024*1024):.1f} MB...")
            
            # Download in chunks
            with open(self.download_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 80  # 80% for download
                            self.download_progress = progress
                            
                            if progress_callback:
                                progress_callback(progress, f"Downloaded {downloaded_size / (1024*1024):.1f} MB")
                                
            self.download_status = "Download complete, processing..."
            if progress_callback:
                progress_callback(80.0, "Download complete, building database...")
                
            # Build database from downloaded data
            success = self._build_database_from_file(progress_callback)
            
            if success:
                self.download_status = "Database ready"
                self.download_progress = 100.0
                if progress_callback:
                    progress_callback(100.0, "Database ready")
                    
                # Save metadata
                self._save_metadata()
                
            return success
            
        except Exception as e:
            self.download_error = str(e)
            self.download_status = f"Download failed: {str(e)}"
            if progress_callback:
                progress_callback(0.0, f"Error: {str(e)}")
            return False
            
        finally:
            self.is_downloading = False
            
    def _build_database_from_file(self, progress_callback: Callable[[float, str], None] = None) -> bool:
        """Build SQLite database from downloaded JSON file"""
        try:
            if progress_callback:
                progress_callback(85.0, "Creating database...")
                
            # Remove existing database
            if self.db_path.exists():
                self.db_path.unlink()
                
            # Create new database
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Create systems table with spatial indexing support
            cursor.execute('''
                CREATE TABLE systems (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    x REAL NOT NULL,
                    y REAL NOT NULL, 
                    z REAL NOT NULL,
                    population INTEGER,
                    allegiance TEXT,
                    government TEXT,
                    economy TEXT,
                    security TEXT
                )
            ''')
            
            # Create spatial index using R-Tree (if available)
            try:
                cursor.execute('''
                    CREATE VIRTUAL TABLE systems_spatial USING rtree(
                        id,
                        x_min, x_max,
                        y_min, y_max,
                        z_min, z_max
                    )
                ''')
                has_rtree = True
            except:
                # Fallback to regular index if R-Tree not available
                cursor.execute('CREATE INDEX idx_systems_coords ON systems (x, y, z)')
                has_rtree = False
                
            if progress_callback:
                progress_callback(90.0, "Loading systems data...")
                
            # Load and parse JSON data
            systems_count = 0
            batch_size = 1000
            batch = []
            
            with gzip.open(self.download_path, 'rt', encoding='utf-8') as f:
                systems = json.load(f)
                total_systems = len(systems)
                
                for i, system in enumerate(systems):
                    if 'coords' not in system:
                        continue
                        
                    coords = system['coords']
                    
                    # Prepare system data
                    system_data = (
                        system.get('name', ''),
                        coords['x'],
                        coords['y'], 
                        coords['z'],
                        system.get('population', 0),
                        system.get('allegiance', ''),
                        system.get('government', ''),
                        system.get('primaryEconomy', ''),
                        system.get('security', '')
                    )
                    
                    batch.append(system_data)
                    
                    # Insert batch
                    if len(batch) >= batch_size:
                        cursor.executemany('''
                            INSERT INTO systems (name, x, y, z, population, allegiance, government, economy, security)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', batch)
                        
                        # Insert into spatial index if available
                        if has_rtree:
                            for j, (name, x, y, z, *_) in enumerate(batch):
                                row_id = systems_count + j + 1
                                cursor.execute('''
                                    INSERT INTO systems_spatial VALUES (?, ?, ?, ?, ?, ?, ?)
                                ''', (row_id, x, x, y, y, z, z))
                        
                        systems_count += len(batch)
                        batch = []
                        
                        # Update progress
                        progress = 90.0 + ((i / total_systems) * 8.0)
                        if progress_callback:
                            progress_callback(progress, f"Processed {systems_count:,} systems...")
                            
                # Insert remaining batch
                if batch:
                    cursor.executemany('''
                        INSERT INTO systems (name, x, y, z, population, allegiance, government, economy, security)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', batch)
                    
                    if has_rtree:
                        for j, (name, x, y, z, *_) in enumerate(batch):
                            row_id = systems_count + j + 1
                            cursor.execute('''
                                INSERT INTO systems_spatial VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (row_id, x, x, y, y, z, z))
                    
                    systems_count += len(batch)
                    
            conn.commit()
            conn.close()
            
            if progress_callback:
                progress_callback(98.0, f"Database created with {systems_count:,} systems")
            
            # Auto-cleanup downloaded JSON file to save space
            self.cleanup_old_files()
                
            print(f"✅ Created local systems database with {systems_count:,} systems")
            print(f"✅ R-Tree spatial indexing: {'Enabled' if has_rtree else 'Disabled (using regular index)'}")
            
            return True
            
        except Exception as e:
            print(f"❌ Database creation failed: {e}")
            if progress_callback:
                progress_callback(0.0, f"Database creation failed: {str(e)}")
            return False
            
    def _save_metadata(self):
        """Save database metadata"""
        metadata = {
            "created_at": datetime.now().isoformat(),
            "source_url": self.edsm_url,
            "version": "1.0"
        }
        
        with open(self.metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
            
    def _verify_database(self) -> bool:
        """Verify database is valid and accessible"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM systems")
            count = cursor.fetchone()[0]
            conn.close()
            return count > 0
        except:
            return False
            
    def find_nearby_systems(self, center_x: float, center_y: float, center_z: float, 
                           max_distance: float, limit: int = 100, cache_context: str = None) -> List[Dict]:
        """Find systems within radius of center point
        
        Args:
            center_x, center_y, center_z: Center coordinates
            max_distance: Maximum distance in light years
            limit: Maximum number of results to return
            cache_context: Additional context for cache key (e.g., search filters)
            
        Returns:
            List of system dictionaries with name, coordinates, and distance
        """
        if not self.is_database_available():
            return []
            
        # Create cache key for this query - include context for better cache differentiation
        cache_key = f"{center_x:.1f}_{center_y:.1f}_{center_z:.1f}_{max_distance}_{limit}"
        if cache_context:
            cache_key += f"_{cache_context}"
        
        current_time = time.time()
        
        # Check cache first
        if cache_key in self.query_cache:
            cached_data = self.query_cache[cache_key]
            if current_time - cached_data['timestamp'] < self.cache_timeout:
                print(f"🗄️ Cache hit for spatial query: {len(cached_data['results'])} systems (context: {cache_context or 'none'})")
                return cached_data['results']
            else:
                # Remove expired cache entry
                del self.query_cache[cache_key]
        
        try:
            # Use connection pooling for better performance
            conn = sqlite3.connect(str(self.db_path))
            # Enable Write-Ahead Logging for better read performance
            conn.execute("PRAGMA journal_mode=WAL")
            # Optimize for read performance
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=10000")  # 10MB cache
            conn.execute("PRAGMA temp_store=MEMORY")
            
            cursor = conn.cursor()
            
            # Check if R-Tree spatial index is available
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='systems_spatial'")
            has_rtree = cursor.fetchone() is not None
            
            if has_rtree:
                # Use R-Tree for efficient spatial query with optimized bounds
                bounds_buffer = max_distance * 0.1  # Small buffer for edge cases
                query = '''
                    SELECT s.name, s.x, s.y, s.z, s.population, s.allegiance,
                           ((s.x - ?) * (s.x - ?) + (s.y - ?) * (s.y - ?) + (s.z - ?) * (s.z - ?)) as dist_squared
                    FROM systems s
                    JOIN systems_spatial ss ON s.id = ss.id
                    WHERE ss.x_min <= ? AND ss.x_max >= ?
                      AND ss.y_min <= ? AND ss.y_max >= ?
                      AND ss.z_min <= ? AND ss.z_max >= ?
                      AND ((s.x - ?) * (s.x - ?) + (s.y - ?) * (s.y - ?) + (s.z - ?) * (s.z - ?)) <= ?
                    ORDER BY dist_squared
                    LIMIT ?
                '''
                
                max_distance_squared = max_distance * max_distance
                params = (
                    center_x, center_x, center_y, center_y, center_z, center_z,  # For distance calculation
                    center_x + max_distance + bounds_buffer, center_x - max_distance - bounds_buffer,
                    center_y + max_distance + bounds_buffer, center_y - max_distance - bounds_buffer, 
                    center_z + max_distance + bounds_buffer, center_z - max_distance - bounds_buffer,
                    center_x, center_x, center_y, center_y, center_z, center_z,  # For WHERE distance filter
                    max_distance_squared,
                    limit
                )
            else:
                # Fallback to regular query with coordinate bounds and distance calculation
                query = '''
                    SELECT name, x, y, z, population, allegiance,
                           ((x - ?) * (x - ?) + (y - ?) * (y - ?) + (z - ?) * (z - ?)) as dist_squared
                    FROM systems
                    WHERE x BETWEEN ? AND ?
                      AND y BETWEEN ? AND ?
                      AND z BETWEEN ? AND ?
                      AND ((x - ?) * (x - ?) + (y - ?) * (y - ?) + (z - ?) * (z - ?)) <= ?
                    ORDER BY dist_squared
                    LIMIT ?
                '''
                
                max_distance_squared = max_distance * max_distance
                params = (
                    center_x, center_x, center_y, center_y, center_z, center_z,  # For distance calculation
                    center_x - max_distance, center_x + max_distance,
                    center_y - max_distance, center_y + max_distance,
                    center_z - max_distance, center_z + max_distance,
                    center_x, center_x, center_y, center_y, center_z, center_z,  # For WHERE distance filter
                    max_distance_squared,
                    limit
                )
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()
            
            # Convert results to expected format
            nearby_systems = []
            for row in results:
                name, x, y, z, population, allegiance, dist_squared = row
                distance = math.sqrt(dist_squared)
                
                nearby_systems.append({
                    'name': name,
                    'distance': distance,
                    'coordinates': {'x': x, 'y': y, 'z': z},
                    'population': population,
                    'allegiance': allegiance
                })
            
            # Cache results if we have data
            if nearby_systems:
                # Manage cache size
                if len(self.query_cache) >= self.cache_max_size:
                    # Remove oldest entries
                    oldest_key = min(self.query_cache.keys(), 
                                   key=lambda k: self.query_cache[k]['timestamp'])
                    del self.query_cache[oldest_key]
                
                # Add to cache
                self.query_cache[cache_key] = {
                    'results': nearby_systems,
                    'timestamp': current_time
                }
                
            print(f"🗄️ Found {len(nearby_systems)} systems within {max_distance} LY using {'R-Tree' if has_rtree else 'regular'} index")
            return nearby_systems
            
        except Exception as e:
            print(f"❌ Local database query failed: {e}")
            return []
            
    def cleanup_old_files(self):
        """Remove old download files to save space"""
        try:
            if self.download_path.exists():
                self.download_path.unlink()
                print(f"✅ Cleaned up download file: {self.download_path}")
        except Exception as e:
            print(f"⚠️ Could not clean up download file: {e}")
            
    def clear_cache(self, context_filter: str = None):
        """Clear query cache to free memory
        
        Args:
            context_filter: If provided, only clear cache entries containing this context
        """
        if context_filter:
            # Clear only matching cache entries
            keys_to_remove = [key for key in self.query_cache.keys() if context_filter in key]
            for key in keys_to_remove:
                del self.query_cache[key]
            print(f"🗑️ Query cache cleared for context '{context_filter}' ({len(keys_to_remove)} entries)")
        else:
            # Clear all cache
            self.query_cache.clear()
            print("🗑️ Query cache cleared (all entries)")
        
    def get_cache_stats(self) -> Dict:
        """Get cache performance statistics"""
        return {
            'cached_queries': len(self.query_cache),
            'max_cache_size': self.cache_max_size,
            'cache_timeout_hours': self.cache_timeout / 3600
        }