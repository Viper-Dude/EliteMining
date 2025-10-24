"""
EDSM Integration Module - Automatic fallback for missing ring metadata

This module provides automatic integration with EDSM (Elite Dangerous Star Map)
to fill in missing ring metadata when journal data is incomplete.

Flow:
1. Detect rings with hotspots but missing LS distance or ring type
2. Query EDSM API for system body data (free, no API key needed)
3. Parse ring metadata from response
4. Update database with missing information
5. Propagate to all materials in the same ring

Use case: When users DSS a ring without FSS scanning first, journal only
provides hotspot data but not ring metadata. EDSM fills the gap.
"""

import requests
import time
import sqlite3
from typing import Dict, List, Optional, Tuple
import urllib.parse


class EDSMIntegration:
    """
    Handles automatic fallback to EDSM API for missing ring metadata.
    """
    
    EDSM_API_BASE = "https://www.edsm.net/api-system-v1"
    REQUEST_DELAY = 0.5  # Seconds between requests (be nice to EDSM)
    TIMEOUT = 10  # Request timeout in seconds
    
    def __init__(self, user_db_path: str):
        """
        Initialize EDSM integration.
        
        Args:
            user_db_path: Path to user_data.db database
        """
        self.user_db_path = user_db_path
        self.last_request_time = 0
        
    def _rate_limit(self):
        """Ensure we don't spam EDSM with too many requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)
        self.last_request_time = time.time()
    
    def _query_edsm_system(self, system_name: str) -> Optional[Dict]:
        """
        Query EDSM API for system body data.
        
        Args:
            system_name: Star system name
            
        Returns:
            JSON response dict or None if request failed
        """
        try:
            self._rate_limit()
            
            # URL encode system name (handles spaces, special chars)
            encoded_name = urllib.parse.quote(system_name)
            url = f"{self.EDSM_API_BASE}/bodies?systemName={encoded_name}"
            
            print(f"[EDSM] Querying: {system_name}")
            
            response = requests.get(url, timeout=self.TIMEOUT)
            
            if response.status_code == 200:
                data = response.json()
                if data and "bodies" in data:
                    print(f"[EDSM] ✓ Found {len(data['bodies'])} bodies in {system_name}")
                    return data
                else:
                    print(f"[EDSM] ✗ No body data for {system_name}")
                    return None
            else:
                print(f"[EDSM] ✗ HTTP {response.status_code} for {system_name}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"[EDSM] ✗ Timeout querying {system_name}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"[EDSM] ✗ Error querying {system_name}: {e}")
            return None
        except Exception as e:
            print(f"[EDSM] ✗ Unexpected error: {e}")
            return None
    
    def _extract_ring_data(self, edsm_data: Dict, ring_name: str) -> Optional[Dict]:
        """
        Extract ring metadata from EDSM response.
        
        Args:
            edsm_data: EDSM API response JSON
            ring_name: Ring name from DB (can be partial like "1 A Ring" or full like "Macua 1 A Ring")
            
        Returns:
            Dict with ring metadata or None if not found
        """
        if not edsm_data or "bodies" not in edsm_data:
            return None
        
        # Normalize ring name - ensure it ends with " Ring" for EDSM matching
        normalized_ring_name = ring_name
        if not ring_name.endswith(" Ring"):
            # Check if it ends with a ring letter (A, B, C, D, E)
            parts = ring_name.split()
            if parts and len(parts[-1]) == 1 and parts[-1] in "ABCDE":
                normalized_ring_name = ring_name + " Ring"
        
        # Try to find a matching body and ring
        # EDSM includes system name in ring names, but DB might only have body number
        # Example: DB has "1 A Ring", EDSM has "Macua 1 A Ring"
        
        for body in edsm_data["bodies"]:
            body_name = body.get("name", "")
            if "rings" not in body:
                continue
            
            # Find matching ring
            for ring in body["rings"]:
                ring_edsm_name = ring.get("name", "")
                
                # Try multiple matching strategies:
                # 1. Exact match (rare, but try it)
                if ring_edsm_name == normalized_ring_name or ring_edsm_name == ring_name:
                    return {
                        "ring_type": ring.get("type"),
                        "ls_distance": body.get("distanceToArrival"),
                        "inner_radius": ring.get("innerRadius"),
                        "outer_radius": ring.get("outerRadius"),
                        "ring_mass": ring.get("mass")
                    }
                
                # 2. EDSM name ends with our ring name (most common)
                # "Macua 1 A Ring" ends with "1 A Ring"
                if ring_edsm_name.endswith(normalized_ring_name):
                    return {
                        "ring_type": ring.get("type"),
                        "ls_distance": body.get("distanceToArrival"),
                        "inner_radius": ring.get("innerRadius"),
                        "outer_radius": ring.get("outerRadius"),
                        "ring_mass": ring.get("mass")
                    }
                
                # 3. Our name ends with EDSM name (reverse case)
                if normalized_ring_name.endswith(ring_edsm_name):
                    return {
                        "ring_type": ring.get("type"),
                        "ls_distance": body.get("distanceToArrival"),
                        "inner_radius": ring.get("innerRadius"),
                        "outer_radius": ring.get("outerRadius"),
                        "ring_mass": ring.get("mass")
                    }
        
        return None
    
    def _calculate_density(self, inner_radius: Optional[float], outer_radius: Optional[float], 
                          mass: Optional[float]) -> Optional[float]:
        """
        Calculate ring density from dimensions and mass.
        
        Args:
            inner_radius: Inner radius in meters
            outer_radius: Outer radius in meters
            mass: Ring mass in MT
            
        Returns:
            Density value or None if calculation not possible
        """
        if not all([inner_radius, outer_radius, mass]):
            return None
        
        try:
            # Volume of annulus (ring) = π * height * (R² - r²)
            # Assuming height = 1 for 2D calculation
            import math
            volume = math.pi * (outer_radius**2 - inner_radius**2)
            if volume > 0:
                return mass / volume
            return None
        except:
            return None
    
    def _update_ring_metadata(self, system_name: str, body_name: str, 
                             metadata: Dict) -> int:
        """
        Update database with ring metadata for ALL materials in the ring.
        
        Args:
            system_name: System name
            body_name: Ring name that matched (from DB or EDSM format)
            metadata: Ring metadata dict
            
        Returns:
            Number of rows updated
        """
        try:
            conn = sqlite3.connect(self.user_db_path)
            cursor = conn.cursor()
            
            # Calculate density if we have the data
            density = self._calculate_density(
                metadata.get("inner_radius"),
                metadata.get("outer_radius"),
                metadata.get("ring_mass")
            )
            
            # Try to match ring names flexibly:
            # DB has: "1 A Ring", EDSM has: "Macua 1 A Ring"
            # Extract the short form (body number + ring letter)
            # E.g., "Macua 1 A Ring" -> "1 A Ring"
            short_ring_name = body_name
            if system_name in body_name:
                # Remove system name prefix to get short form
                short_ring_name = body_name.replace(system_name, "").strip()
            
            # Update using exact match on the short ring name
            cursor.execute("""
                UPDATE hotspot_data
                SET ring_type = ?,
                    ls_distance = ?,
                    inner_radius = ?,
                    outer_radius = ?,
                    ring_mass = ?,
                    density = ?
                WHERE system_name = ?
                  AND body_name = ?
                  AND (ring_type IS NULL OR ls_distance IS NULL)
            """, (
                metadata.get("ring_type"),
                metadata.get("ls_distance"),
                metadata.get("inner_radius"),
                metadata.get("outer_radius"),
                metadata.get("ring_mass"),
                density,
                system_name,
                short_ring_name
            ))
            
            rows_updated = cursor.rowcount
            conn.commit()
            conn.close()
            
            if rows_updated > 0:
                print(f"[EDSM] ✓ Updated {rows_updated} materials in {short_ring_name}")
                print(f"       Type: {metadata.get('ring_type')}, LS: {metadata.get('ls_distance')}")
            
            return rows_updated
            
        except Exception as e:
            print(f"[EDSM] ✗ Database update error: {e}")
            return 0
    
    def get_incomplete_rings(self) -> List[Tuple[str, str]]:
        """
        Find rings with hotspots but missing metadata.
        
        Returns:
            List of (system_name, body_name) tuples for incomplete rings
        """
        try:
            conn = sqlite3.connect(self.user_db_path)
            cursor = conn.cursor()
            
            # Find unique rings with hotspots but missing metadata
            cursor.execute("""
                SELECT DISTINCT system_name, body_name
                FROM hotspot_data
                WHERE material_name IS NOT NULL
                  AND (ring_type IS NULL OR ls_distance IS NULL)
                ORDER BY system_name, body_name
            """)
            
            results = cursor.fetchall()
            conn.close()
            
            return results
            
        except Exception as e:
            print(f"[EDSM] ✗ Error querying incomplete rings: {e}")
            return []
    
    def fill_missing_metadata(self) -> Dict[str, int]:
        """
        Automatically fill missing ring metadata using EDSM fallback.
        
        This is the main entry point - call this to fix all missing data.
        
        Returns:
            Dict with stats: {
                "rings_checked": int,
                "systems_queried": int,
                "rings_updated": int,
                "materials_updated": int
            }
        """
        stats = {
            "rings_checked": 0,
            "systems_queried": 0,
            "rings_updated": 0,
            "materials_updated": 0
        }
        
        # Get rings with missing data
        incomplete_rings = self.get_incomplete_rings()
        stats["rings_checked"] = len(incomplete_rings)
        
        if not incomplete_rings:
            print("[EDSM] No missing ring metadata found - all complete!")
            return stats
        
        print(f"[EDSM] Found {len(incomplete_rings)} rings with missing metadata")
        
        # Group by system to minimize API calls
        systems_to_query = {}
        for system_name, body_name in incomplete_rings:
            if system_name not in systems_to_query:
                systems_to_query[system_name] = []
            systems_to_query[system_name].append(body_name)
        
        # Query each system once
        for system_name, ring_names in systems_to_query.items():
            stats["systems_queried"] += 1
            
            # Query EDSM for this system
            edsm_data = self._query_edsm_system(system_name)
            
            if not edsm_data:
                continue
            
            # Try to fill metadata for each ring in this system
            for ring_name in ring_names:
                ring_metadata = self._extract_ring_data(edsm_data, ring_name)
                
                if ring_metadata:
                    rows_updated = self._update_ring_metadata(
                        system_name, 
                        ring_name, 
                        ring_metadata
                    )
                    
                    if rows_updated > 0:
                        stats["rings_updated"] += 1
                        stats["materials_updated"] += rows_updated
        
        # Summary
        print(f"\n[EDSM] Metadata fill complete:")
        print(f"       Rings checked: {stats['rings_checked']}")
        print(f"       Systems queried: {stats['systems_queried']}")
        print(f"       Rings updated: {stats['rings_updated']}")
        print(f"       Total materials updated: {stats['materials_updated']}")
        
        return stats
    
    def fill_missing_metadata_for_systems(self, system_names: List[str]) -> Dict[str, int]:
        """
        Fill missing ring metadata for specific systems only (optimized for result sets).
        
        Args:
            system_names: List of system names to check and update
            
        Returns:
            Stats dict with results
        """
        stats = {
            "rings_checked": 0,
            "systems_queried": 0,
            "rings_updated": 0,
            "materials_updated": 0
        }
        
        # Get incomplete rings only for specified systems
        all_incomplete = self.get_incomplete_rings()
        systems_set = set(system_names)
        incomplete_rings = [(sys, ring) for sys, ring in all_incomplete if sys in systems_set]
        
        stats["rings_checked"] = len(incomplete_rings)
        
        if not incomplete_rings:
            return stats
        
        # Group by system
        systems_to_query = {}
        for system_name, body_name in incomplete_rings:
            if system_name not in systems_to_query:
                systems_to_query[system_name] = []
            systems_to_query[system_name].append(body_name)
        
        # Query each system once
        for system_name, ring_names in systems_to_query.items():
            stats["systems_queried"] += 1
            
            edsm_data = self._query_edsm_system(system_name)
            
            if not edsm_data:
                continue
            
            for ring_name in ring_names:
                ring_metadata = self._extract_ring_data(edsm_data, ring_name)
                
                if ring_metadata:
                    rows_updated = self._update_ring_metadata(
                        system_name, 
                        ring_name, 
                        ring_metadata
                    )
                    
                    if rows_updated > 0:
                        stats["rings_updated"] += 1
                        stats["materials_updated"] += rows_updated
        
        return stats


def fill_missing_ring_metadata(user_db_path: str) -> Dict[str, int]:
    """
    Convenience function to fill missing ring metadata using EDSM.
    
    Args:
        user_db_path: Path to user_data.db
        
    Returns:
        Stats dict with results
    """
    edsm = EDSMIntegration(user_db_path)
    return edsm.fill_missing_metadata()


if __name__ == "__main__":
    # Test/standalone execution
    import os
    import sys
    
    # Default path (adjust if needed)
    db_path = os.path.join(os.path.dirname(__file__), "data", "user_data.db")
    
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    
    if not os.path.exists(db_path):
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)
    
    print(f"Using database: {db_path}\n")
    stats = fill_missing_ring_metadata(db_path)
    
    print("\nDone!")
