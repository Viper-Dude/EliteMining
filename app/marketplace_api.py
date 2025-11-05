"""
Marketplace API for commodity price lookups using Ardent API
"""
import requests
from typing import List, Dict, Optional


class MarketplaceAPI:
    """Ardent API integration for commodity market data"""
    
    BASE_URL = "https://api.ardent-insight.com/v2"
    
    # Map EliteMining commodity names to Ardent API names
    COMMODITY_NAME_MAP = {
        # Void Opals -> opal
        "void opals": "opal",
        "void opal": "opal",
        "opals": "opal",
        
        # Low Temperature Diamonds -> lowtemperaturediamond  
        "low temperature diamonds": "lowtemperaturediamond",
        "low temperature diamond": "lowtemperaturediamond",
        "ltd": "lowtemperaturediamond",
        
        # Ensure common names work
        "bromellite": "bromellite",
        "alexandrite": "alexandrite",
        "benitoite": "benitoite",
        "grandidierite": "grandidierite",
        "monazite": "monazite",
        "musgravite": "musgravite",
        "painite": "painite",
        "platinum": "platinum",
        "rhodplumsite": "rhodplumsite",
        "serendibite": "serendibite",
        "taaffeite": "taaffeite",
        "tritium": "tritium",
    }
    
    @staticmethod
    def normalize_commodity_name(commodity: str) -> str:
        """
        Normalize commodity name for Ardent API
        
        Args:
            commodity: User-entered commodity name (e.g., "Void Opals", "Low Temperature Diamonds")
            
        Returns:
            Normalized commodity name for Ardent API (e.g., "opal", "lowtemperaturediamond")
        """
        # Convert to lowercase and check mapping
        commodity_lower = commodity.strip().lower()
        
        if commodity_lower in MarketplaceAPI.COMMODITY_NAME_MAP:
            return MarketplaceAPI.COMMODITY_NAME_MAP[commodity_lower]
        
        # If not in map, return as-is (lowercase, no spaces)
        return commodity_lower.replace(" ", "")
    
    @staticmethod
    def search_buyers(commodity: str, reference_system: str, max_distance: Optional[int] = None, max_days_ago: float = 2) -> List[Dict]:
        """
        Search for stations buying a commodity near a reference system (for SELLING to them)
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            reference_system: Reference system name
            max_distance: Maximum distance in light years (None for unlimited)
            max_days_ago: Maximum age of data in days (default 2)
            
        Returns:
            List of station data dictionaries with keys:
            - system_name, station_name, station_type
            - sell_price, demand
            - system_distance, arrival_distance
            - updated
        """
        try:
            # Normalize and URL encode commodity and system names
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            system_encoded = urllib.parse.quote(reference_system)
            
            # Build URL - uses "imports" endpoint (places that BUY/import the commodity)
            url = f"{MarketplaceAPI.BASE_URL}/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/imports"
            
            # Build query parameters - use API maximum distance for best results
            params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago,
                "maxDistance": 500  # API maximum is 500 LY
            }
            
            # Call API for nearby systems
            print(f"[ARDENT API] URL: {url}")
            print(f"[ARDENT API] Params: {params}")
            response = requests.get(url, params=params, timeout=10)
            print(f"[ARDENT API] Status: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            # API returns a list directly, not a dict with 'results'
            if isinstance(data, list):
                print(f"[ARDENT API] Found {len(data)} nearby results")
                results = data
            elif isinstance(data, dict) and "results" in data:
                print(f"[ARDENT API] Found {len(data['results'])} results in dict")
                results = data["results"]
            else:
                print(f"[ARDENT API] Unexpected response type: {type(data)}")
                results = []
            
            # ALSO query local system imports (nearby endpoint excludes reference system)
            local_url = f"{MarketplaceAPI.BASE_URL}/system/name/{system_encoded}/commodities/imports"
            local_params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago
            }
            
            print(f"[ARDENT API LOCAL] URL: {local_url}")
            print(f"[ARDENT API LOCAL] Params: {local_params}")
            local_response = requests.get(local_url, params=local_params, timeout=10)
            print(f"[ARDENT API LOCAL] Status: {local_response.status_code}")
            
            if local_response.status_code == 200:
                local_data = local_response.json()
                if isinstance(local_data, list):
                    # Filter for the specific commodity (use normalized name)
                    commodity_imports = [r for r in local_data if r.get('commodityName', '').lower() == commodity_normalized]
                    print(f"[ARDENT API LOCAL] Found {len(commodity_imports)} local results for {commodity}")
                    
                    # Add distance=0 for local results and merge
                    for imp in commodity_imports:
                        imp['distance'] = 0
                    results.extend(commodity_imports)
                    print(f"[ARDENT API] Total after merging: {len(results)} results")
            
            if results and len(results) > 0:
                print(f"[ARDENT API] Sample result keys: {list(results[0].keys())}")
                print(f"[ARDENT API] First result sample: {results[0]}")
            
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[ARDENT API] Request error: {e}")
            return []
        except Exception as e:
            print(f"[ARDENT API] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_sellers(commodity: str, reference_system: str, max_distance: Optional[int] = None, max_days_ago: float = 2, exclude_carriers: bool = True) -> List[Dict]:
        """
        Search for stations selling a commodity near a reference system (for BUYING from them)
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            reference_system: Reference system name
            max_distance: Maximum distance in light years (None for unlimited)
            max_days_ago: Maximum age of data in days (default 2)
            
        Returns:
            List of station data dictionaries with keys:
            - system_name, station_name, station_type
            - buy_price, stock
            - system_distance, arrival_distance
            - updated
        """
        try:
            # Normalize and URL encode commodity and system names
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            system_encoded = urllib.parse.quote(reference_system)
            
            # Build URL - uses "exports" endpoint (places that SELL/export the commodity)
            url = f"{MarketplaceAPI.BASE_URL}/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/exports"
            
            # Build query parameters - use API maximum distance for best results
            params = {
                "minVolume": 1,  # Only show stations with stock > 0 (per Ardent API docs)
                "maxDaysAgo": max_days_ago,
                "maxDistance": 500  # API maximum is 500 LY
            }
            # Note: Not using fleetCarriers parameter - will filter client-side for consistency with imports
            
            # Call API for nearby systems
            print(f"[ARDENT API SELLERS] URL: {url}")
            print(f"[ARDENT API SELLERS] Params: {params}")
            response = requests.get(url, params=params, timeout=10)
            print(f"[ARDENT API SELLERS] Status: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            # API returns a list directly, not a dict with 'results'
            if isinstance(data, list):
                print(f"[ARDENT API SELLERS] Found {len(data)} nearby results")
                results = data
            elif isinstance(data, dict) and "results" in data:
                print(f"[ARDENT API SELLERS] Found {len(data['results'])} results in dict")
                results = data["results"]
            else:
                print(f"[ARDENT API SELLERS] Unexpected response type: {type(data)}")
                results = []
            
            # ALSO query local system exports (nearby endpoint excludes reference system)
            local_url = f"{MarketplaceAPI.BASE_URL}/system/name/{system_encoded}/commodities/exports"
            local_params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago
            }
            
            print(f"[ARDENT API SELLERS LOCAL] URL: {local_url}")
            print(f"[ARDENT API SELLERS LOCAL] Params: {local_params}")
            local_response = requests.get(local_url, params=local_params, timeout=10)
            print(f"[ARDENT API SELLERS LOCAL] Status: {local_response.status_code}")
            
            if local_response.status_code == 200:
                local_data = local_response.json()
                if isinstance(local_data, list):
                    # Filter for the specific commodity (use normalized name)
                    commodity_exports = [r for r in local_data if r.get('commodityName', '').lower() == commodity_normalized]
                    print(f"[ARDENT API SELLERS LOCAL] Found {len(commodity_exports)} local results for {commodity}")
                    
                    # Add distance=0 and fix price field for local results
                    # NOTE: Local /commodities/exports endpoint has sellPrice=0 and actual price in buyPrice
                    for export in commodity_exports:
                        export['distance'] = 0
                        if export.get('sellPrice', 0) == 0 and export.get('buyPrice', 0) > 0:
                            export['sellPrice'] = export['buyPrice']  # Fix backwards field naming
                    results.extend(commodity_exports)
                    print(f"[ARDENT API SELLERS] Total after merging: {len(results)} results")
            
            if results and len(results) > 0:
                print(f"[ARDENT API SELLERS] Sample result keys: {list(results[0].keys())}")
                print(f"[ARDENT API SELLERS] First result sample: {results[0]}")
            
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[ARDENT API SELLERS] Request error: {e}")
            return []
        except Exception as e:
            print(f"[ARDENT API SELLERS] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_buyers_galaxy_wide(commodity: str, max_days_ago: float = 2) -> List[Dict]:
        """
        Search for top 100 best prices galaxy-wide (no distance limit) - for SELLING to them
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            max_days_ago: Maximum age of data in days (default 2)
            
        Returns:
            List of station data dictionaries sorted by highest price
        """
        try:
            # Normalize and URL encode commodity name
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            
            # Use galaxy-wide imports endpoint (no system reference needed)
            url = f"{MarketplaceAPI.BASE_URL}/commodity/name/{commodity_encoded}/imports"
            
            # Build query parameters for top results
            params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago
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
    def search_sellers_galaxy_wide(commodity: str, max_days_ago: float = 2, exclude_carriers: bool = True) -> List[Dict]:
        """
        Search for top 100 best prices galaxy-wide (no distance limit) - for BUYING from them
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            max_days_ago: Maximum age of data in days (default 2)
            
        Returns:
            List of station data dictionaries sorted by lowest price
        """
        try:
            # Normalize and URL encode commodity name
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            
            # Use galaxy-wide exports endpoint (no system reference needed)
            url = f"{MarketplaceAPI.BASE_URL}/commodity/name/{commodity_encoded}/exports"
            
            # Build query parameters for top results
            params = {
                "minVolume": 1,  # Only show stations with stock > 0 (per Ardent API docs)
                "maxDaysAgo": max_days_ago
            }
            # Note: Not using fleetCarriers parameter - will filter client-side for consistency
            
            # Call API
            print(f"[ARDENT API GALAXY SELLERS] URL: {url}")
            print(f"[ARDENT API GALAXY SELLERS] Params: {params}")
            response = requests.get(url, params=params, timeout=10)
            print(f"[ARDENT API GALAXY SELLERS] Status: {response.status_code}")
            response.raise_for_status()
            
            data = response.json()
            
            # API returns a list directly
            if isinstance(data, list):
                print(f"[ARDENT API GALAXY SELLERS] Found {len(data)} results")
                if data:
                    print(f"[ARDENT API GALAXY SELLERS] Sample result keys: {list(data[0].keys())}")
                    print(f"[ARDENT API GALAXY SELLERS] First result sample: {data[0]}")
                return data[:100]  # Return top 100
            else:
                print(f"[ARDENT API GALAXY SELLERS] Unexpected response type: {type(data)}")
                return []
            
        except requests.exceptions.RequestException as e:
            print(f"[ARDENT API GALAXY SELLERS] Request error: {e}")
            return []
        except Exception as e:
            print(f"[ARDENT API GALAXY SELLERS] Unexpected error: {e}")
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
