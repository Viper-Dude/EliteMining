"""
User Database Management for EliteMining
Handles hotspot data and visited systems tracking
"""

import os
import sqlite3
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from app_utils import get_app_data_dir

log = logging.getLogger("EliteMining.UserDatabase")


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
                log.info(f"User database initialized: {self.db_path}")
                
        except Exception as e:
            log.error(f"Error creating user database tables: {e}")
            raise
    
    def add_hotspot_data(self, system_name: str, body_name: str, material_name: str, 
                        hotspot_count: int, scan_date: str, system_address: Optional[int] = None,
                        body_id: Optional[int] = None, coordinates: Optional[Tuple[float, float, float]] = None,
                        coord_source: str = "journal") -> None:
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
        """
        try:
            # Get coordinates from visited_systems if not provided
            if coordinates is None:
                coordinates = self._get_coordinates_from_visited_systems(system_name)
                if coordinates:
                    coord_source = "visited_systems"
                else:
                    coord_source = "unknown"
            
            x_coord, y_coord, z_coord = coordinates or (None, None, None)
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO hotspot_data 
                    (system_name, body_name, material_name, hotspot_count, 
                     scan_date, system_address, body_id, x_coord, y_coord, z_coord, coord_source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (system_name, body_name, material_name, hotspot_count, 
                      scan_date, system_address, body_id, x_coord, y_coord, z_coord, coord_source))
                conn.commit()
                
        except Exception as e:
            log.error(f"Error adding hotspot data: {e}")

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
                    SELECT visit_count, first_visit_date FROM visited_systems 
                    WHERE system_name = ?
                ''', (system_name,))
                
                result = cursor.fetchone()
                
                if result:
                    # Update existing record
                    visit_count, first_visit = result
                    conn.execute('''
                        UPDATE visited_systems 
                        SET last_visit_date = ?, visit_count = visit_count + 1
                        WHERE system_name = ?
                    ''', (visit_date, system_name))
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
                
                conn.commit()
                
        except Exception as e:
            log.error(f"Error adding visited system: {e}")
    
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
            log.error(f"Error checking visited system: {e}")
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
    
    def has_visited_system(self, system_name: str) -> bool:
        """Check if the player has ever visited a system
        
        Args:
            system_name: Name of the star system
            
        Returns:
            True if system has been visited, False otherwise
        """
        visit_data = self.is_system_visited(system_name)
        return visit_data is not None
    
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