"""
Marketplace API for commodity price lookups using EDData + Ardent Insight APIs.

Both APIs are queried in parallel. Results are merged by marketId, keeping the
record with the newer updatedAt timestamp so the freshest price always wins.
"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional


class MarketplaceAPI:
    """Dual-API market data: EDData + Ardent Insight, merged by freshness."""

    EDDATA_URL  = "https://api.eddata.dev/v2"
    ARDENT_URL  = "https://api.ardent-insight.com/v2"

    # Keep BASE_URL for any legacy callers; _fetch_both() ignores it
    PRIMARY_URL  = EDDATA_URL
    FALLBACK_URL = ARDENT_URL
    BASE_URL     = PRIMARY_URL
    
    # Map EliteMining commodity names to EDData API names
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
    def _make_api_request(url: str, params: dict, timeout: int = 10) -> requests.Response:
        """Single GET request (kept for compatibility). Raises on failure."""
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response

    @staticmethod
    def _fetch_both(path: str, params: dict, timeout: int = 10) -> List[Dict]:
        """
        Fetch *path* from both EDData and Ardent in parallel, return the raw
        combined list.  Each item keeps its source URL so _merge_by_freshness
        can log it if needed.  If one API fails, the other's results are still
        returned.
        """
        def _get(base: str) -> List[Dict]:
            try:
                url = f"{base}{path}"
                r = requests.get(url, params=params, timeout=timeout)
                r.raise_for_status()
                data = r.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "results" in data:
                    return data["results"]
                return []
            except Exception as e:
                print(f"[DUAL-API] {base} failed: {e}")
                return []

        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_eddata  = pool.submit(_get, MarketplaceAPI.EDDATA_URL)
            fut_ardent  = pool.submit(_get, MarketplaceAPI.ARDENT_URL)
            eddata_rows = fut_eddata.result()
            ardent_rows = fut_ardent.result()

        print(f"[DUAL-API] EDData={len(eddata_rows)}  Ardent={len(ardent_rows)}")
        return eddata_rows + ardent_rows

    @staticmethod
    def _merge_by_freshness(rows: List[Dict]) -> List[Dict]:
        """
        Deduplicate by marketId, keeping the record with the newer updatedAt.
        Records without marketId are kept as-is (e.g. some on-foot settlements).
        """
        from datetime import datetime

        def _ts(row: Dict) -> datetime:
            raw = row.get("updatedAt") or ""
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                return datetime.min

        best: Dict[int, Dict] = {}
        no_id: List[Dict] = []

        for row in rows:
            mid = row.get("marketId")
            if mid is None:
                no_id.append(row)
                continue
            if mid not in best or _ts(row) > _ts(best[mid]):
                best[mid] = row

        merged = list(best.values()) + no_id
        print(f"[DUAL-API] After merge: {len(merged)} unique results")
        return merged
    
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
    def search_buyers(commodity: str, reference_system: str, max_distance: Optional[int] = None, max_days_ago: float = 2, exclude_carriers: bool = False) -> List[Dict]:
        """
        Search for stations buying a commodity near a reference system (for SELLING to them)
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            reference_system: Reference system name
            max_distance: Maximum distance in light years (None for unlimited)
            max_days_ago: Maximum age of data in days (default 2)
            exclude_carriers: Whether to exclude Fleet Carriers from results
            
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

            # --- Nearby imports (both APIs in parallel) ---
            nearby_path = f"/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/imports"
            nearby_params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago,
                "maxDistance": 500,
            }
            if exclude_carriers:
                nearby_params["fleetCarriers"] = False

            print(f"[BUYERS] nearby path: {nearby_path} params: {nearby_params}")
            nearby_rows = MarketplaceAPI._fetch_both(nearby_path, nearby_params)

            # --- Local system imports (both APIs in parallel) ---
            local_path = f"/system/name/{system_encoded}/commodities/imports"
            local_params = {"minVolume": 1, "maxDaysAgo": max_days_ago}

            print(f"[BUYERS] local path: {local_path}")
            local_rows_raw = MarketplaceAPI._fetch_both(local_path, local_params)
            local_rows = [r for r in local_rows_raw if r.get("commodityName", "").lower() == commodity_normalized]
            for r in local_rows:
                r["distance"] = 0

            print(f"[BUYERS] nearby={len(nearby_rows)} local={len(local_rows)}")
            results = MarketplaceAPI._merge_by_freshness(nearby_rows + local_rows)
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[EDDATA API] Request error: {e}")
            return []
        except Exception as e:
            print(f"[EDDATA API] Unexpected error: {e}")
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
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            system_encoded = urllib.parse.quote(reference_system)

            # --- Nearby exports (both APIs in parallel) ---
            nearby_path = f"/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/exports"
            nearby_params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago,
                "maxDistance": 500,
            }
            if exclude_carriers:
                nearby_params["fleetCarriers"] = False

            print(f"[SELLERS] nearby path: {nearby_path} params: {nearby_params}")
            nearby_rows = MarketplaceAPI._fetch_both(nearby_path, nearby_params)

            # --- Local system exports (both APIs in parallel) ---
            local_path = f"/system/name/{system_encoded}/commodities/exports"
            local_params = {"minVolume": 1, "maxDaysAgo": max_days_ago}

            print(f"[SELLERS] local path: {local_path}")
            local_rows_raw = MarketplaceAPI._fetch_both(local_path, local_params)
            local_rows = [r for r in local_rows_raw if r.get("commodityName", "").lower() == commodity_normalized]
            for r in local_rows:
                r["distance"] = 0
                # Local exports endpoint has buyPrice as the actual price
                if r.get("sellPrice", 0) == 0 and r.get("buyPrice", 0) > 0:
                    r["sellPrice"] = r["buyPrice"]

            print(f"[SELLERS] nearby={len(nearby_rows)} local={len(local_rows)}")
            results = MarketplaceAPI._merge_by_freshness(nearby_rows + local_rows)
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[EDDATA API SELLERS] Request error: {e}")
            return []
        except Exception as e:
            print(f"[EDDATA API SELLERS] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_buyers_galaxy_wide(commodity: str, max_days_ago: float = 2, exclude_carriers: bool = False) -> List[Dict]:
        """
        Search for top 100 best prices galaxy-wide (no distance limit) - for SELLING to them
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            max_days_ago: Maximum age of data in days (default 2)
            exclude_carriers: Whether to exclude fleet carriers (default False)
            
        Returns:
            List of station data dictionaries sorted by highest price
        """
        try:
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)

            path = f"/commodity/name/{commodity_encoded}/imports"
            params: dict = {"minVolume": 1, "maxDaysAgo": max_days_ago}
            if exclude_carriers:
                params["fleetCarriers"] = False

            print(f"[GALAXY BUYERS] path: {path} params: {params}")
            rows = MarketplaceAPI._fetch_both(path, params)
            results = MarketplaceAPI._merge_by_freshness(rows)
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[EDDATA API GALAXY] Request error: {e}")
            return []
        except Exception as e:
            print(f"[EDDATA API GALAXY] Unexpected error: {e}")
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
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)

            path = f"/commodity/name/{commodity_encoded}/exports"
            params: dict = {"minVolume": 1, "maxDaysAgo": max_days_ago}
            if exclude_carriers:
                params["fleetCarriers"] = False

            print(f"[GALAXY SELLERS] path: {path} params: {params}")
            rows = MarketplaceAPI._fetch_both(path, params)
            results = MarketplaceAPI._merge_by_freshness(rows)
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[EDDATA API GALAXY SELLERS] Request error: {e}")
            return []
        except Exception as e:
            print(f"[EDDATA API GALAXY SELLERS] Unexpected error: {e}")
            return []
    
    @staticmethod
    def add_distances_to_results(results: List[Dict], reference_system: str) -> List[Dict]:
        """
        Add distance information to galaxy-wide results using local database + EDSM fallback
        
        Args:
            results: List of result dictionaries (with systemX/Y/Z from API)
            reference_system: Name of the reference system
            
        Returns:
            Same list with 'distance' key added to each result
        """
        try:
            ref_x, ref_y, ref_z = None, None, None
            
            # Try local database first (instant!)
            try:
                from local_database import LocalSystemsDatabase
                local_db = LocalSystemsDatabase()
                if local_db.is_database_available():
                    ref_coords = local_db.get_system_coordinates(reference_system)
                    if ref_coords:
                        ref_x, ref_y, ref_z = ref_coords['x'], ref_coords['y'], ref_coords['z']
                        print(f"[DISTANCE CALC] Using local database for {reference_system}")
            except Exception as e:
                print(f"[DISTANCE CALC] Local DB failed: {e}")
            
            # Fallback to EDSM if local DB didn't work
            if ref_x is None:
                import urllib.parse
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
                print(f"[DISTANCE CALC] Using EDSM fallback for {reference_system}")
            
            # Calculate distance for each result using API coordinates (instant, no additional queries!)
            for result in results:
                # Use coordinates already in API response
                sys_x = result.get('systemX')
                sys_y = result.get('systemY')
                sys_z = result.get('systemZ')
                
                if sys_x is not None and sys_y is not None and sys_z is not None:
                    dx = sys_x - ref_x
                    dy = sys_y - ref_y
                    dz = sys_z - ref_z
                    distance = (dx**2 + dy**2 + dz**2) ** 0.5
                    result['distance'] = distance
            
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
