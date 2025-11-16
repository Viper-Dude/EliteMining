"""
EDSM Distance Calculator Module
Integrates with EDSM API to calculate distances between Elite Dangerous systems
"""

import requests
import math
import time
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class EDSMDistanceCalculator:
    """Calculates distances between Elite Dangerous systems using EDSM API"""
    
    def __init__(self):
        self.api_base_url = "https://www.edsm.net/api-v1/system"
        self.timeout = 10  # seconds
        self.cache = {}  # Cache system coordinates
        self.cache_expiry = 300  # 5 minutes
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Rate limiting: 500ms between requests
        
    def _rate_limit(self):
        """Ensure we don't make requests too quickly"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
    
    def _is_cache_valid(self, system_name: str) -> bool:
        """Check if cached data is still valid"""
        if system_name not in self.cache:
            return False
        
        cache_entry = self.cache[system_name]
        age = time.time() - cache_entry.get("timestamp", 0)
        return age < self.cache_expiry
    
    def get_system_coordinates(self, system_name: str) -> Optional[Dict]:
        """
        Get system coordinates from EDSM API with retry logic
        
        Args:
            system_name: Name of the system
            
        Returns:
            Dict with keys: name, x, y, z
            None if system not found or error occurs
        """
        if not system_name or not system_name.strip():
            logger.warning("Empty system name provided")
            return None
        
        system_name = system_name.strip()
        
        # Check cache first
        if self._is_cache_valid(system_name):
            logger.debug(f"Cache hit for system: {system_name}")
            return self.cache[system_name]["data"]
        
        # Retry logic: up to 3 attempts with increasing delays
        max_retries = 3
        retry_delays = [0, 1, 2]  # seconds to wait before each retry
        
        for attempt in range(max_retries):
            try:
                # Rate limiting
                self._rate_limit()
                
                # Add retry delay if not first attempt
                if attempt > 0:
                    logger.info(f"Retry attempt {attempt + 1}/{max_retries} for {system_name}")
                    time.sleep(retry_delays[attempt])
                
                # Query EDSM API
                params = {
                    "systemName": system_name,
                    "showCoordinates": 1
                }
                
                logger.info(f"Querying EDSM for system: {system_name}")
                response = requests.get(self.api_base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                
                data = response.json()
                
                if "coords" not in data:
                    # System genuinely not found - don't retry
                    logger.warning(f"System '{system_name}' not found in EDSM or has no coordinates")
                    return None
                
                result = {
                    "name": data["name"],
                    "x": float(data["coords"]["x"]),
                    "y": float(data["coords"]["y"]),
                    "z": float(data["coords"]["z"])
                }
                
                # Cache the result
                self.cache[system_name] = {
                    "data": result,
                    "timestamp": time.time()
                }
                
                logger.info(f"Successfully retrieved coordinates for {result['name']}")
                return result
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout querying EDSM for {system_name} (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    logger.error(f"All retry attempts failed for {system_name} due to timeout")
                    return None
                continue
                
            except requests.exceptions.ConnectionError:
                logger.warning(f"Connection error querying EDSM for {system_name} (attempt {attempt + 1}/{max_retries})")
                if attempt == max_retries - 1:
                    logger.error(f"All retry attempts failed for {system_name} due to connection error")
                    return None
                continue
                
            except requests.exceptions.HTTPError as e:
                # Don't retry on 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    logger.error(f"HTTP client error for {system_name}: {e}")
                    return None
                # Retry on 5xx errors (server errors)
                logger.warning(f"HTTP error querying EDSM for {system_name} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"All retry attempts failed for {system_name} due to HTTP error")
                    return None
                continue
                
            except Exception as e:
                logger.error(f"Unexpected error querying EDSM for {system_name}: {e}")
                return None
        
        return None
    
    def calculate_distance(self, system1: Dict, system2: Dict) -> Optional[float]:
        """
        Calculate 3D Euclidean distance between two systems
        
        Args:
            system1: Dict with keys x, y, z
            system2: Dict with keys x, y, z
            
        Returns:
            Distance in light years, or None if calculation fails
        """
        if not system1 or not system2:
            return None
        
        try:
            dx = system1["x"] - system2["x"]
            dy = system1["y"] - system2["y"]
            dz = system1["z"] - system2["z"]
            
            distance = math.sqrt(dx*dx + dy*dy + dz*dz)
            return distance
            
        except (KeyError, TypeError) as e:
            logger.error(f"Error calculating distance: {e}")
            return None
    
    def get_distance_between_systems(self, system1_name: str, system2_name: str) -> Tuple[Optional[float], Optional[Dict], Optional[Dict]]:
        """
        Get distance between two systems and return their info
        
        Args:
            system1_name: Name of first system
            system2_name: Name of second system
            
        Returns:
            Tuple of (distance, system1_info, system2_info)
            Any element can be None if lookup/calculation fails
        """
        system1 = self.get_system_coordinates(system1_name)
        system2 = self.get_system_coordinates(system2_name)
        
        if not system1 or not system2:
            return None, system1, system2
        
        distance = self.calculate_distance(system1, system2)
        return distance, system1, system2
    
    def get_distance_to_sol(self, system_name: str) -> Tuple[Optional[float], Optional[Dict]]:
        """
        Get distance from a system to Sol
        
        Args:
            system_name: Name of the system
            
        Returns:
            Tuple of (distance, system_info)
        """
        sol = {"name": "Sol", "x": 0.0, "y": 0.0, "z": 0.0}
        system = self.get_system_coordinates(system_name)
        
        if not system:
            return None, None
        
        distance = self.calculate_distance(system, sol)
        return distance, system
    
    def clear_cache(self):
        """Clear the coordinate cache"""
        self.cache.clear()
        logger.info("EDSM coordinate cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        valid_entries = sum(1 for name in self.cache if self._is_cache_valid(name))
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self.cache) - valid_entries
        }


# Global instance
_calculator = None

def get_distance_calculator() -> EDSMDistanceCalculator:
    """Get or create the global distance calculator instance"""
    global _calculator
    if _calculator is None:
        _calculator = EDSMDistanceCalculator()
    return _calculator
