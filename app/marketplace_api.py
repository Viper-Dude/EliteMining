"""
Marketplace API for commodity price lookups using EDData + Ardent Insight + Spansh APIs.

All three APIs are queried in parallel. Results are merged by marketId, keeping the
record with the newer updatedAt timestamp so the freshest price always wins.
"""
import requests
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional

_system_coords_cache: Dict[str, object] = {}  # module-level coord cache


class MarketplaceAPI:
    """Dual-API market data: EDData + Ardent Insight + Spansh + EDDN cache, merged by freshness."""

    EDDATA_URL  = "https://api.eddata.dev/v2"
    ARDENT_URL  = "https://api.ardent-insight.com/v2"
    SPANSH_URL  = "https://spansh.co.uk"

    # Set by main.py on boot when EDDN listener is started
    EDDN_CACHE_PATH = None

    # Keep BASE_URL for any legacy callers; _fetch_both() ignores it
    PRIMARY_URL  = EDDATA_URL
    FALLBACK_URL = ARDENT_URL
    BASE_URL     = PRIMARY_URL

    # Map normalized EDData commodity names -> Spansh display names
    SPANSH_COMMODITY_MAP = {
        "opal":                   "Void Opal",
        "lowtemperaturediamond":  "Low Temperature Diamond",
        "painite":                "Painite",
        "platinum":               "Platinum",
        "bromellite":             "Bromellite",
        "alexandrite":            "Alexandrite",
        "benitoite":              "Benitoite",
        "grandidierite":          "Grandidierite",
        "monazite":               "Monazite",
        "musgravite":             "Musgravite",
        "rhodplumsite":           "Rhodplumsite",
        "serendibite":            "Serendibite",
        "taaffeite":              "Taaffeite",
        "tritium":                "Tritium",
        "gold":                   "Gold",
        "silver":                 "Silver",
        "palladium":              "Palladium",
    }

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
    def _fetch_spansh(
        commodity_normalized: str,
        reference_system: str,
        filter_type: str,
        max_distance: int = 500,
        max_days_ago: float = 2,
        exclude_carriers: bool = False,
        size: int = 100,
    ) -> List[Dict]:
        """
        Fetch commodity data from Spansh (POST API) using parallel pagination
        (3 pages x 100) sorted by most recent market update.  Returns rows
        normalized to the same format as EDData / Ardent.

        For galaxy-wide (max_distance=0) all results are kept.
        For distance-limited searches, results are filtered by distance field.
        """
        try:
            from datetime import datetime, timedelta, timezone

            spansh_name = MarketplaceAPI.SPANSH_COMMODITY_MAP.get(
                commodity_normalized,
                commodity_normalized.title(),
            )

            # Parallel paginated fetch — 3 pages x 100 results
            def _fetch_page(page_num):
                try:
                    body = {
                        "filters": {filter_type: {"value": [spansh_name]}},
                        "sort": [{"market_updated_at": {"direction": "desc"}}],
                        "size": 100,
                        "page": page_num,
                    }
                    if reference_system and max_distance:
                        body["reference_system"] = reference_system
                    resp = requests.post(
                        f"{MarketplaceAPI.SPANSH_URL}/api/stations/search",
                        json=body, timeout=15)
                    resp.raise_for_status()
                    return resp.json().get("results", [])
                except Exception as e:
                    print(f"[SPANSH] page {page_num} error: {e}")
                    return []

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(_fetch_page, p) for p in range(3)]
                results = []
                for f in futures:
                    results.extend(f.result())

            print(f"[SPANSH] fetched {len(results)} stations from 3 pages")

            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_ago + 0.5)

            # Spansh type -> EDData-compatible stationType mapping
            _type_map = {
                "Fleet Carrier":       "FleetCarrier",
                "Stronghold Carrier":  "StrongholdCarrier",
                "Planetary Port":      "CraterPort",
                "Planetary Outpost":   "CraterOutpost",
                "Coriolis Starport":   "Coriolis",
                "Orbis Starport":      "Orbis",
                "Ocellus Starport":    "Ocellus",
                "Dodecahedron Starport": "Dodec",
                "Outpost":             "Outpost",
                "Asteroid Base":       "AsteroidBase",
                "Mega Ship":           "MegaShip",
                "Odyssey Settlement":  "OnFootSettlement",
            }

            normalized: List[Dict] = []
            seen_ids = set()
            for station in results:
                mid = station.get("market_id")
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)

                dist = station.get("distance") or 0
                if max_distance and dist > max_distance:
                    continue

                spansh_type = station.get("type") or ""
                eddata_type = _type_map.get(spansh_type, spansh_type)

                # Skip carriers — handled separately by _fetch_spansh_carriers
                if eddata_type == "FleetCarrier" or spansh_type == "Drake-Class Carrier":
                    continue

                updated_raw = station.get("market_updated_at") or ""
                if updated_raw:
                    try:
                        ts = datetime.fromisoformat(updated_raw)
                        if ts < cutoff:
                            continue
                    except Exception:
                        pass

                market = station.get("market") or []
                entry = next(
                    (item for item in market
                     if item.get("commodity", "").lower() == spansh_name.lower()),
                    None,
                )
                if not entry:
                    continue

                # Derive maxLandingPadSize from Spansh pad counts
                if station.get("large_pads", 0) or station.get("has_large_pad"):
                    pad_size = 3
                elif station.get("medium_pads", 0):
                    pad_size = 2
                elif station.get("small_pads", 0):
                    pad_size = 1
                else:
                    pad_size = 0

                # Spansh uses same field conventions as EDData/EDDN:
                # sell_price = what station pays you, buy_price = what you pay
                # supply/stock = station has for sale, demand = station wants to buy
                sell_p = entry.get("sell_price", 0)
                buy_p  = entry.get("buy_price", 0)
                dem    = entry.get("demand", 0)
                stk    = entry.get("supply", 0) or entry.get("stock", 0)

                normalized.append({
                    "marketId":          mid,
                    "updatedAt":         updated_raw,
                    "systemName":        station.get("system_name"),
                    "stationName":       station.get("name"),
                    "stationType":       eddata_type,
                    "maxLandingPadSize": pad_size,
                    "distance":          dist,
                    "distanceToArrival": station.get("distance_to_arrival") or 0,
                    "sellPrice":         sell_p,
                    "buyPrice":          buy_p,
                    "demand":            dem,
                    "stock":             stk,
                    "commodityName":     commodity_normalized,
                    "systemX":           station.get("system_x"),
                    "systemY":           station.get("system_y"),
                    "systemZ":           station.get("system_z"),
                    "_source":           "Spansh",
                })

            print(f"[SPANSH] {filter_type}: {len(normalized)} results for {spansh_name}")
            return normalized

        except Exception as e:
            print(f"[SPANSH] Error fetching {commodity_normalized}: {e}")
            return []

    @staticmethod
    def _fetch_spansh_carriers(
        commodity_normalized: str,
        reference_system: str,
        filter_type: str,
        max_distance: int = 500,
        max_days_ago: float = 30,
        exclude_carriers: bool = False,
    ) -> List[Dict]:
        """
        Fetch fleet carrier market data from Spansh.  Spansh's commodity
        filters (buying_commodities / selling_commodities) do NOT apply to
        carriers, so we fetch recent carriers and match commodities locally.

        Uses parallel pagination (10 pages x 100) sorted by market_updated_at.
        """
        if exclude_carriers:
            return []

        try:
            import math
            from datetime import datetime, timedelta, timezone

            ref_coords = MarketplaceAPI._get_system_coords(reference_system) if reference_system else None
            rx, ry, rz = ref_coords if ref_coords else (0, 0, 0)

            spansh_name = MarketplaceAPI.SPANSH_COMMODITY_MAP.get(
                commodity_normalized, commodity_normalized.title())

            def _fetch_page(page_num):
                try:
                    body = {
                        "filters": {"type": {"value": ["Drake-Class Carrier"]}},
                        "sort": [{"market_updated_at": {"direction": "desc"}}],
                        "size": 100,
                        "page": page_num,
                    }
                    resp = requests.post(
                        f"{MarketplaceAPI.SPANSH_URL}/api/stations/search",
                        json=body, timeout=15)
                    resp.raise_for_status()
                    return resp.json().get("results", [])
                except Exception:
                    return []

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(_fetch_page, p) for p in range(2)]
                raw = []
                for f in futures:
                    raw.extend(f.result())

            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_ago + 0.5)

            normalized: List[Dict] = []
            seen_ids = set()
            for station in raw:
                mid = station.get("market_id")
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)

                # Distance filter (skip for galaxy-wide where max_distance=0)
                sx = station.get("system_x")
                sy = station.get("system_y")
                sz = station.get("system_z")
                if max_distance and ref_coords:
                    if sx is None or sy is None or sz is None:
                        continue
                    dist = math.sqrt((sx - rx) ** 2 + (sy - ry) ** 2 + (sz - rz) ** 2)
                    if dist > max_distance:
                        continue
                else:
                    dist = station.get("distance") or 0

                updated_raw = station.get("market_updated_at") or ""
                if updated_raw:
                    try:
                        ts = datetime.fromisoformat(updated_raw)
                        if ts < cutoff:
                            continue
                    except Exception:
                        pass

                # Match commodity locally
                market = station.get("market") or []
                entry = next(
                    (item for item in market
                     if item.get("commodity", "").lower() == spansh_name.lower()),
                    None,
                )
                if not entry:
                    continue

                # Spansh uses same field conventions as EDData/EDDN.
                # Pass through all fields — UI filters by mode.
                sell_p = entry.get("sell_price", 0)
                buy_p  = entry.get("buy_price", 0)
                dem    = entry.get("demand", 0)
                stk    = entry.get("supply", 0) or entry.get("stock", 0)

                if station.get("large_pads", 0) or station.get("has_large_pad"):
                    pad_size = 3
                else:
                    pad_size = 3  # All carriers have large pads

                normalized.append({
                    "marketId":          mid,
                    "updatedAt":         updated_raw,
                    "systemName":        station.get("system_name"),
                    "stationName":       station.get("name"),
                    "stationType":       "FleetCarrier",
                    "maxLandingPadSize": pad_size,
                    "distance":          dist,
                    "distanceToArrival": station.get("distance_to_arrival") or 0,
                    "sellPrice":         sell_p,
                    "buyPrice":          buy_p,
                    "demand":            dem,
                    "stock":             stk,
                    "commodityName":     commodity_normalized,
                    "systemX":           sx,
                    "systemY":           sy,
                    "systemZ":           sz,
                    "_source":           "Spansh",
                })

            print(f"[SPANSH CARRIERS] {filter_type}: {len(normalized)} carriers for {spansh_name}")
            return normalized

        except Exception as e:
            print(f"[SPANSH CARRIERS] Error: {e}")
            return []

    @staticmethod
    def _fetch_eddn_cache(
        commodity_normalized: str,
        reference_system: str,
        filter_type: str,
        max_distance: int = 500,
        max_days_ago: float = 0.333,  # 8 hours default query window (listener retains 24h)
        exclude_carriers: bool = False,
    ) -> List[Dict]:
        """
        Query local EDDN cache (marketplace_cache.db) for real-time market data.

        EDDN data is the freshest possible — pushed by players in real-time.
        """
        if not MarketplaceAPI.EDDN_CACHE_PATH:
            return []

        try:
            import sqlite3, math, os
            from datetime import datetime, timedelta, timezone

            if not os.path.exists(MarketplaceAPI.EDDN_CACHE_PATH):
                return []

            # EDDN uses lowercase names like "platinum", "painite"
            # Spansh uses title case like "Platinum", "Painite"
            # Match both formats
            spansh_name = MarketplaceAPI.SPANSH_COMMODITY_MAP.get(
                commodity_normalized, commodity_normalized.title())

            ref_coords = MarketplaceAPI._get_system_coords(reference_system) if reference_system else None
            rx, ry, rz = ref_coords if ref_coords else (0, 0, 0)

            cutoff = (datetime.now(timezone.utc) - timedelta(days=max_days_ago)).isoformat()

            with sqlite3.connect(MarketplaceAPI.EDDN_CACHE_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Query by commodity name — match EDData normalized OR Spansh display name
                cursor.execute('''
                    SELECT system_name, system_x, system_y, system_z,
                           station_name, station_type, commodity_name,
                           sell_price, buy_price, demand, stock,
                           distance_to_arrival, market_id, updated_at
                    FROM commodity_prices_data
                    WHERE (LOWER(commodity_name) = LOWER(?) OR LOWER(commodity_name) = LOWER(?))
                      AND updated_at > ?
                ''', (commodity_normalized, spansh_name, cutoff))

                rows = cursor.fetchall()

            # Batch-resolve coordinates for all systems missing them in one query
            coords_cache = {}
            missing_systems = {row["system_name"] for row in rows
                               if row["system_x"] is None and row["system_name"]}
            if missing_systems:
                try:
                    from local_database import LocalSystemsDatabase
                    galaxy_db = LocalSystemsDatabase()
                    if galaxy_db.is_database_available():
                        import sqlite3 as _sqlite3
                        placeholders = ",".join("?" for _ in missing_systems)
                        with _sqlite3.connect(str(galaxy_db.db_path)) as _gconn:
                            _gconn.row_factory = _sqlite3.Row
                            _gcur = _gconn.cursor()
                            _gcur.execute(
                                f"SELECT name, x, y, z FROM systems WHERE name IN ({placeholders})",
                                list(missing_systems)
                            )
                            for gr in _gcur.fetchall():
                                coords_cache[gr["name"]] = (gr["x"], gr["y"], gr["z"])
                except Exception as _ce:
                    print(f"[EDDN CACHE] Batch coord lookup failed: {_ce}")

            normalized: List[Dict] = []
            for row in rows:
                sx = row["system_x"]
                sy = row["system_y"]
                sz = row["system_z"]

                # Resolve missing coords from galaxy DB
                if sx is None and row["system_name"] in coords_cache:
                    sx, sy, sz = coords_cache[row["system_name"]]

                # Distance filter
                if max_distance and ref_coords and sx is not None and sy is not None and sz is not None:
                    dist = math.sqrt((sx - rx) ** 2 + (sy - ry) ** 2 + (sz - rz) ** 2)
                    if dist > max_distance:
                        continue
                elif max_distance and ref_coords:
                    continue  # No coords even after lookup, skip
                else:
                    dist = 0

                stype = row["station_type"] or "Unknown"
                # Detect carriers by market_id range (3.7 billion+)
                mid = row["market_id"] or 0
                is_carrier = ("Carrier" in stype or "FleetCarrier" in stype or "Drake" in stype
                              or (mid >= 3700000000 and mid < 4000000000))
                if exclude_carriers and is_carrier:
                    continue

                # Pass through all fields — UI picks correct ones by mode
                sell_p = row["sell_price"] or 0
                buy_p  = row["buy_price"] or 0
                dem    = row["demand"] or 0
                stk    = row["stock"] or 0

                # Normalize station type for EDData compatibility
                _type_map = {
                    "FleetCarrier": "FleetCarrier",
                    "Coriolis": "Coriolis",
                    "Orbis": "Orbis",
                    "Ocellus": "Ocellus",
                    "Dodec": "Dodec",
                    "Outpost": "Outpost",
                    "CraterOutpost": "CraterOutpost",
                    "CraterPort": "CraterPort",
                }
                if is_carrier:
                    eddata_type = "FleetCarrier"
                else:
                    eddata_type = _type_map.get(stype, stype)

                # Determine pad size
                if is_carrier or eddata_type in ("Coriolis", "Orbis", "Ocellus", "Dodec"):
                    pad_size = 3
                elif "Outpost" in eddata_type:
                    pad_size = 2
                else:
                    pad_size = 1

                normalized.append({
                    "marketId":          row["market_id"],
                    "updatedAt":         row["updated_at"] or "",
                    "systemName":        row["system_name"],
                    "stationName":       row["station_name"],
                    "stationType":       eddata_type,
                    "maxLandingPadSize": pad_size,
                    "distance":          dist,
                    "distanceToArrival": row["distance_to_arrival"] or 0,
                    "sellPrice":         sell_p,
                    "buyPrice":          buy_p,
                    "demand":            dem,
                    "stock":             stk,
                    "commodityName":     commodity_normalized,
                    "systemX":           sx,
                    "systemY":           sy,
                    "systemZ":           sz,
                    "_source":           "EDDN",
                })

            print(f"[EDDN CACHE] {filter_type}: {len(normalized)} results for {spansh_name}")
            return normalized

        except Exception as e:
            print(f"[EDDN CACHE] Error: {e}")
            return []

    @staticmethod
    @staticmethod
    def _get_system_coords(system_name: str):
        """Return (x, y, z) for system_name, or None on failure. Results are cached."""
        return MarketplaceAPI._get_system_coords_cached(system_name)

    @staticmethod
    def _get_system_coords_cached(system_name: str):  # type: ignore[override]
        """Cached implementation — avoid repeated DB opens for the same system."""
        if system_name in _system_coords_cache:
            return _system_coords_cache[system_name]
        result = None
        try:
            from local_database import LocalSystemsDatabase
            db = LocalSystemsDatabase()
            if db.is_database_available():
                c = db.get_system_coordinates(system_name)
                if c:
                    result = c['x'], c['y'], c['z']
        except Exception:
            pass
        if result is None:
            try:
                import urllib.parse
                url = "https://www.edsm.net/api-v1/system?systemName={}&showCoordinates=1".format(
                    urllib.parse.quote(system_name))
                r = requests.get(url, timeout=8)
                r.raise_for_status()
                coords = r.json().get('coords', {})
                if coords:
                    result = coords['x'], coords['y'], coords['z']
            except Exception:
                pass
        _system_coords_cache[system_name] = result
        return result

    @staticmethod
    def _fetch_spansh_nearby(
        commodity_normalized: str,
        reference_system: str,
        filter_type: str,
        max_distance: int = 500,
        max_days_ago: float = 2,
        exclude_carriers: bool = False,
        size: int = 500,
    ) -> List[Dict]:
        """
        Spansh nearby search using parallel paginated queries sorted by
        market_updated_at desc.  Fetches 3 pages of 100 results concurrently
        (300 total) then filters by 3-D distance from reference_system.
        """
        try:
            import math
            from datetime import datetime, timedelta, timezone

            ref_coords = MarketplaceAPI._get_system_coords(reference_system)
            if ref_coords is None:
                print(f"[SPANSH NEARBY] Cannot get coords for {reference_system}")
                return []
            rx, ry, rz = ref_coords

            spansh_name = MarketplaceAPI.SPANSH_COMMODITY_MAP.get(
                commodity_normalized, commodity_normalized.title())

            # Parallel paginated fetch — 3 pages x 100 results
            def _fetch_page(page_num):
                try:
                    body = {
                        "filters": {filter_type: {"value": [spansh_name]}},
                        "sort": [{"market_updated_at": {"direction": "desc"}}],
                        "size": 100,
                        "page": page_num,
                    }
                    resp = requests.post(
                        f"{MarketplaceAPI.SPANSH_URL}/api/stations/search",
                        json=body, timeout=15)
                    resp.raise_for_status()
                    return resp.json().get("results", [])
                except Exception as e:
                    print(f"[SPANSH NEARBY] page {page_num} error: {e}")
                    return []

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(_fetch_page, p) for p in range(3)]
                raw_results = []
                for f in futures:
                    raw_results.extend(f.result())

            print(f"[SPANSH NEARBY] fetched {len(raw_results)} stations from 3 pages")

            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_ago + 0.5)

            _type_map = {
                "Fleet Carrier":       "FleetCarrier",
                "Stronghold Carrier":  "StrongholdCarrier",
                "Planetary Port":      "CraterPort",
                "Planetary Outpost":   "CraterOutpost",
                "Coriolis Starport":   "Coriolis",
                "Orbis Starport":      "Orbis",
                "Ocellus Starport":    "Ocellus",
                "Dodecahedron Starport": "Dodec",
                "Outpost":             "Outpost",
                "Asteroid Base":       "AsteroidBase",
                "Mega Ship":           "MegaShip",
                "Odyssey Settlement":  "OnFootSettlement",
            }

            normalized: List[Dict] = []
            seen_ids = set()
            for station in raw_results:
                # Deduplicate by market_id
                mid = station.get("market_id")
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)

                # Calculate 3-D distance from reference system
                sx = station.get("system_x")
                sy = station.get("system_y")
                sz = station.get("system_z")
                if sx is None or sy is None or sz is None:
                    continue
                dist = math.sqrt((sx - rx) ** 2 + (sy - ry) ** 2 + (sz - rz) ** 2)
                if max_distance and dist > max_distance:
                    continue

                spansh_type = station.get("type") or ""
                eddata_type = _type_map.get(spansh_type, spansh_type)

                # Skip carriers — handled separately by _fetch_spansh_carriers
                if eddata_type == "FleetCarrier" or spansh_type == "Drake-Class Carrier":
                    continue

                updated_raw = station.get("market_updated_at") or ""
                if updated_raw:
                    try:
                        ts = datetime.fromisoformat(updated_raw)
                        if ts < cutoff:
                            continue
                    except Exception:
                        pass

                market = station.get("market") or []
                entry = next(
                    (item for item in market
                     if item.get("commodity", "").lower() == spansh_name.lower()),
                    None,
                )
                if not entry:
                    continue

                if station.get("large_pads", 0) or station.get("has_large_pad"):
                    pad_size = 3
                elif station.get("medium_pads", 0):
                    pad_size = 2
                elif station.get("small_pads", 0):
                    pad_size = 1
                else:
                    pad_size = 0

                # Spansh uses same field conventions as EDData/EDDN:
                # sell_price = what station pays you, buy_price = what you pay
                # supply/stock = station has for sale, demand = station wants to buy
                sell_p = entry.get("sell_price", 0)
                buy_p  = entry.get("buy_price", 0)
                dem    = entry.get("demand", 0)
                stk    = entry.get("supply", 0) or entry.get("stock", 0)

                normalized.append({
                    "marketId":          mid,
                    "updatedAt":         updated_raw,
                    "systemName":        station.get("system_name"),
                    "stationName":       station.get("name"),
                    "stationType":       eddata_type,
                    "maxLandingPadSize": pad_size,
                    "distance":          dist,
                    "distanceToArrival": station.get("distance_to_arrival") or 0,
                    "sellPrice":         sell_p,
                    "buyPrice":          buy_p,
                    "demand":            dem,
                    "stock":             stk,
                    "commodityName":     commodity_normalized,
                    "systemX":           sx,
                    "systemY":           sy,
                    "systemZ":           sz,
                    "_source":           "Spansh",
                })

            print(f"[SPANSH NEARBY] {filter_type}: {len(normalized)} results within {max_distance} LY for {spansh_name}")
            return normalized

        except Exception as e:
            print(f"[SPANSH NEARBY] Error: {e}")
            return []

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

            # Run EDData+Ardent, Spansh stations, Spansh carriers, and EDDN cache in parallel
            with ThreadPoolExecutor(max_workers=4) as _pool:
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_both, nearby_path, nearby_params)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh_nearby,
                    commodity_normalized, reference_system, "buying_commodities",
                    500, max_days_ago, exclude_carriers, 500
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, reference_system, "buying_commodities",
                    500, max_days_ago, exclude_carriers
                )
                _fut_eddn = _pool.submit(
                    MarketplaceAPI._fetch_eddn_cache,
                    commodity_normalized, reference_system, "buying_commodities",
                    500, max_days_ago, exclude_carriers
                )
                nearby_rows  = _fut_both.result()
                spansh_rows  = _fut_spansh.result()
                carrier_rows = _fut_carriers.result()
                eddn_rows    = _fut_eddn.result()
            nearby_rows = nearby_rows + spansh_rows + carrier_rows + eddn_rows

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

            # Run EDData+Ardent, Spansh stations, Spansh carriers, and EDDN cache in parallel
            with ThreadPoolExecutor(max_workers=4) as _pool:
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_both, nearby_path, nearby_params)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh_nearby,
                    commodity_normalized, reference_system, "selling_commodities",
                    500, max_days_ago, exclude_carriers, 500
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, reference_system, "selling_commodities",
                    500, max_days_ago, exclude_carriers
                )
                _fut_eddn = _pool.submit(
                    MarketplaceAPI._fetch_eddn_cache,
                    commodity_normalized, reference_system, "selling_commodities",
                    500, max_days_ago, exclude_carriers
                )
                nearby_rows  = _fut_both.result()
                spansh_rows  = _fut_spansh.result()
                carrier_rows = _fut_carriers.result()
                eddn_rows    = _fut_eddn.result()
            nearby_rows = nearby_rows + spansh_rows + carrier_rows + eddn_rows

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

            with ThreadPoolExecutor(max_workers=4) as _pool:
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_both, path, params)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh,
                    commodity_normalized, "Sol", "buying_commodities",
                    0, max_days_ago, exclude_carriers, 1000
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, None, "buying_commodities",
                    0, max_days_ago, exclude_carriers
                )
                _fut_eddn = _pool.submit(
                    MarketplaceAPI._fetch_eddn_cache,
                    commodity_normalized, None, "buying_commodities",
                    0, max_days_ago, exclude_carriers
                )
                rows        = _fut_both.result()
                spansh_rows = _fut_spansh.result()
                carrier_rows = _fut_carriers.result()
                eddn_rows    = _fut_eddn.result()
            rows = rows + spansh_rows + carrier_rows + eddn_rows

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

            with ThreadPoolExecutor(max_workers=4) as _pool:
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_both, path, params)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh,
                    commodity_normalized, "Sol", "selling_commodities",
                    0, max_days_ago, exclude_carriers, 1000
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, None, "selling_commodities",
                    0, max_days_ago, exclude_carriers
                )
                _fut_eddn = _pool.submit(
                    MarketplaceAPI._fetch_eddn_cache,
                    commodity_normalized, None, "selling_commodities",
                    0, max_days_ago, exclude_carriers
                )
                rows        = _fut_both.result()
                spansh_rows = _fut_spansh.result()
                carrier_rows = _fut_carriers.result()
                eddn_rows    = _fut_eddn.result()
            rows = rows + spansh_rows + carrier_rows + eddn_rows

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
