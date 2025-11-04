"""
Marketplace API for commodity price lookups using Ardent API
"""
import requests
from typing import List, Dict, Optional


class MarketplaceAPI:
    """Ardent API integration for commodity market data"""
    
    BASE_URL = "https://api.ardent-insight.com/v2"
    
    @staticmethod
    def search_buyers(commodity: str, reference_system: str, max_distance: Optional[int] = None) -> List[Dict]:
        """
        Search for stations buying a commodity near a reference system
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds")
            reference_system: Reference system name
            max_distance: Maximum distance in light years (None for unlimited)
            
        Returns:
            List of station data dictionaries with keys:
            - system_name, station_name, station_type
            - sell_price, demand
            - system_distance, arrival_distance
            - updated
        """
        try:
            # URL encode commodity and system names
            import urllib.parse
            commodity_encoded = urllib.parse.quote(commodity.lower())
            system_encoded = urllib.parse.quote(reference_system)
            
            # Build URL - uses "imports" endpoint (places that BUY/import the commodity)
            url = f"{MarketplaceAPI.BASE_URL}/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/imports"
            
            # Build query parameters - use API maximum distance for best results
            params = {
                "minVolume": 1,
                "maxDaysAgo": 30,
                "maxDistance": 500  # API maximum is 500 LY
            }
            
            # Call API
            print(f"[ARDENT API] URL: {url}")
            print(f"[ARDENT API] Params: {params}")
            response = requests.get(url, params=params, timeout=10)
            print(f"[ARDENT API] Status: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            
            # API returns a list directly, not a dict with 'results'
            if isinstance(data, list):
                print(f"[ARDENT API] Found {len(data)} results")
                if data:
                    print(f"[ARDENT API] Sample result keys: {list(data[0].keys())}")
                    print(f"[ARDENT API] First result sample: {data[0]}")
                return data
            elif isinstance(data, dict) and "results" in data:
                print(f"[ARDENT API] Found {len(data['results'])} results in dict")
                return data["results"]
            else:
                print(f"[ARDENT API] Unexpected response type: {type(data)}")
                return []
            
        except requests.exceptions.RequestException as e:
            print(f"[ARDENT API] Request error: {e}")
            return []
        except Exception as e:
            print(f"[ARDENT API] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_buyers_galaxy_wide(commodity: str) -> List[Dict]:
        """
        Search for top 100 best prices galaxy-wide (no distance limit)
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds")
            
        Returns:
            List of station data dictionaries sorted by highest price
        """
        try:
            # URL encode commodity name
            import urllib.parse
            commodity_encoded = urllib.parse.quote(commodity.lower())
            
            # Use galaxy-wide imports endpoint (no system reference needed)
            url = f"{MarketplaceAPI.BASE_URL}/commodity/name/{commodity_encoded}/imports"
            
            # Build query parameters for top results
            params = {
                "minVolume": 1,
                "maxDaysAgo": 30
            }
            
            # Call API
            print(f"[ARDENT API GALAXY] URL: {url}")
            print(f"[ARDENT API GALAXY] Params: {params}")
            response = requests.get(url, params=params, timeout=10)
            print(f"[ARDENT API GALAXY] Status: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            
            # API returns a list directly
            if isinstance(data, list):
                print(f"[ARDENT API GALAXY] Found {len(data)} results")
                if data:
                    print(f"[ARDENT API GALAXY] Sample result keys: {list(data[0].keys())}")
                    print(f"[ARDENT API GALAXY] First result sample: {data[0]}")
                return data[:100]  # Return top 100
            else:
                print(f"[ARDENT API GALAXY] Unexpected response type: {type(data)}")
                return []
            
        except requests.exceptions.RequestException as e:
            print(f"[ARDENT API GALAXY] Request error: {e}")
            return []
        except Exception as e:
            print(f"[ARDENT API GALAXY] Unexpected error: {e}")
            return []
    
    @staticmethod
    def add_distances_to_results(results: List[Dict], reference_system: str) -> List[Dict]:
        """
        Add distance information to galaxy-wide results by querying EDSM API
        
        Args:
            results: List of result dictionaries
            reference_system: Name of the reference system
            
        Returns:
            Same list with 'distance' key added to each result
        """
        try:
            import urllib.parse
            
            # Get reference system coordinates from EDSM
            system_encoded = urllib.parse.quote(reference_system)
            edsm_url = f"https://www.edsm.net/api-v1/system?systemName={system_encoded}&showCoordinates=1"
            
            response = requests.get(edsm_url, timeout=5)
            response.raise_for_status()
            ref_data = response.json()
            
            if not ref_data or 'coords' not in ref_data:
                print(f"[DISTANCE CALC] Could not get coordinates for {reference_system}")
                return results
            
            ref_coords = ref_data['coords']
            ref_x, ref_y, ref_z = ref_coords['x'], ref_coords['y'], ref_coords['z']
            
            # Calculate distance for each result
            for result in results:
                system_name = result.get('systemName')
                if not system_name:
                    continue
                
                # Get system coordinates from EDSM
                system_encoded = urllib.parse.quote(system_name)
                edsm_url = f"https://www.edsm.net/api-v1/system?systemName={system_encoded}&showCoordinates=1"
                
                try:
                    sys_response = requests.get(edsm_url, timeout=3)
                    sys_response.raise_for_status()
                    sys_data = sys_response.json()
                    
                    if sys_data and 'coords' in sys_data:
                        sys_coords = sys_data['coords']
                        dx = sys_coords['x'] - ref_x
                        dy = sys_coords['y'] - ref_y
                        dz = sys_coords['z'] - ref_z
                        distance = (dx**2 + dy**2 + dz**2) ** 0.5
                        result['distance'] = distance
                except Exception as e:
                    print(f"[DISTANCE CALC] Error getting coords for {system_name}: {e}")
                    # Don't add distance if we can't calculate it
            
            return results
            
        except Exception as e:
            print(f"[DISTANCE CALC] Error: {e}")
            return results
    
    @staticmethod
    def get_station_types() -> List[str]:
        """Get list of station types for filtering"""
        return [
            "Coriolis Starport",
            "Orbis Starport", 
            "Ocellus Starport",
            "Asteroid Base",
            "Planetary Outpost",
            "Planetary Port",
            "Fleet Carrier",
            "Odyssey Settlement"
        ]
