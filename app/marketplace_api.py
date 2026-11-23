"""
Marketplace API for commodity price lookups using Ardent Insight + Spansh APIs.

All sources are queried in parallel. Results are merged by marketId, keeping the
record with the newer updatedAt timestamp so the freshest price always wins.
"""
import logging
import requests
from service_status import tracked_request
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Optional

_system_coords_cache: Dict[str, object] = {}  # module-level coord cache
_source_column_ready: set = set()  # cache paths already checked for the source column

import threading as _threading
import time as _time_mod

_SHORT_CACHE_TTL = 300  # seconds
_short_cache: Dict[tuple, tuple] = {}  # key -> (timestamp, value)
_short_cache_guard = _threading.Lock()
_short_cache_key_locks: Dict[tuple, object] = {}


def _short_cached(key: tuple, fetch, is_cancelled=None):
    """Return fetch() result, reused for _SHORT_CACHE_TTL seconds. Concurrent callers
    with the same key wait for one fetch instead of each issuing the same request."""
    with _short_cache_guard:
        hit = _short_cache.get(key)
        if hit and _time_mod.time() - hit[0] < _SHORT_CACHE_TTL:
            return hit[1]
        key_lock = _short_cache_key_locks.setdefault(key, _threading.Lock())
    with key_lock:
        with _short_cache_guard:
            hit = _short_cache.get(key)
            if hit and _time_mod.time() - hit[0] < _SHORT_CACHE_TTL:
                return hit[1]
        if is_cancelled and is_cancelled():
            return []
        value = fetch()
        if value and not (is_cancelled and is_cancelled()):
            with _short_cache_guard:
                _short_cache[key] = (_time_mod.time(), value)
        return value


class MarketplaceAPI:
    """Market data: Ardent Insight + Spansh + EDDN cache, merged by freshness."""

    ARDENT_URL  = "https://api.ardent-insight.com/v2"
    SPANSH_URL  = "https://spansh.co.uk"

    # Set by main.py on boot when EDDN listener is started
    EDDN_CACHE_PATH = None

    # Spansh circuit breaker - after this many consecutive failures, skip Spansh
    # entirely for the cooldown instead of paying its 15s timeout on every mineral.
    SPANSH_FAILURE_THRESHOLD = 2
    SPANSH_COOLDOWN_SECONDS = 60
    _spansh_failure_count = 0
    _spansh_open_until = 0.0

    @staticmethod
    def _spansh_available() -> bool:
        import time
        if MarketplaceAPI._spansh_failure_count < MarketplaceAPI.SPANSH_FAILURE_THRESHOLD:
            return True
        if time.monotonic() >= MarketplaceAPI._spansh_open_until:
            return True  # cooldown elapsed - let one call through as a probe
        return False

    @staticmethod
    def _spansh_record_result(success: bool) -> None:
        import time
        if success:
            MarketplaceAPI._spansh_failure_count = 0
            MarketplaceAPI._spansh_open_until = 0.0
        else:
            MarketplaceAPI._spansh_failure_count += 1
            if MarketplaceAPI._spansh_failure_count >= MarketplaceAPI.SPANSH_FAILURE_THRESHOLD:
                MarketplaceAPI._spansh_open_until = time.monotonic() + MarketplaceAPI.SPANSH_COOLDOWN_SECONDS

    # Map normalized commodity names -> Spansh display names
    SPANSH_COMMODITY_MAP = {
        "opal":                   "Void Opal",
        "lowtemperaturediamond":  "Low Temperature Diamonds",
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

    # Map EliteMining commodity names to API names
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
        is_cancelled=None,
    ) -> List[Dict]:
        """
        Fetch commodity data from Spansh (POST API) using parallel pagination
        (3 pages x 100) sorted by most recent market update.  Returns rows
        normalized to the same format as Ardent.

        For galaxy-wide (max_distance=0) all results are kept.
        For distance-limited searches, results are filtered by distance field.
        """
        if is_cancelled and is_cancelled():
            return []
        if not MarketplaceAPI._spansh_available():
            print("[SPANSH] Skipped - circuit breaker open (recent failures)")
            return []
        try:
            from datetime import datetime, timedelta, timezone

            spansh_name = MarketplaceAPI.SPANSH_COMMODITY_MAP.get(
                commodity_normalized,
                commodity_normalized.title(),
            )

            page_errors = [0]

            # Spansh ignores buying_/selling_commodities filters; only "market" filters the commodity.
            volume_field = "supply" if filter_type == "selling_commodities" else "demand"
            filters = {"market": [{"name": spansh_name,
                                   volume_field: {"comparison": "<=>", "value": [1, 999999999]}}]}
            if max_distance:
                filters["distance"] = {"min": 0, "max": max_distance}

            # Parallel paginated fetch — 3 pages x 100 results
            def _fetch_page(page_num):
                if is_cancelled and is_cancelled():
                    return []
                try:
                    body = {
                        "filters": filters,
                        "sort": [{"market_updated_at": {"direction": "desc"}}],
                        "size": 100,
                        "page": page_num,
                    }
                    if reference_system and max_distance:
                        body["reference_system"] = reference_system
                    resp = tracked_request('spansh', requests.post,
                        f"{MarketplaceAPI.SPANSH_URL}/api/stations/search",
                        json=body, timeout=15)
                    resp.raise_for_status()
                    return resp.json().get("results", [])
                except Exception as e:
                    print(f"[SPANSH] page {page_num} error: {e}")
                    page_errors[0] += 1
                    return []

            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(_fetch_page, p) for p in range(3)]
                results = []
                for f in futures:
                    results.extend(f.result())

            MarketplaceAPI._spansh_record_result(success=page_errors[0] < 3)

            print(f"[SPANSH] fetched {len(results)} stations from 3 pages")

            cutoff = datetime.now(timezone.utc) - timedelta(days=max_days_ago + 0.5)

            # Spansh type -> EDDN-compatible stationType mapping
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
                "Asteroid base":       "AsteroidBase",
                "Dodec Starport":      "Dodec",
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

                dist = station.get("distance") or None
                if max_distance and (dist is None or dist > max_distance):
                    continue

                spansh_type = station.get("type") or ""
                mapped_type = _type_map.get(spansh_type, spansh_type)

                # Skip carriers — handled separately by _fetch_spansh_carriers
                if mapped_type == "FleetCarrier" or spansh_type == "Drake-Class Carrier":
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

                # Spansh uses same field conventions as EDDN:
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
                    "stationType":       mapped_type,
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
            MarketplaceAPI._spansh_record_result(success=False)
            return []

    @staticmethod
    def _fetch_spansh_carriers(
        commodity_normalized: str,
        reference_system: str,
        filter_type: str,
        max_distance: int = 500,
        max_days_ago: float = 30,
        exclude_carriers: bool = False,
        is_cancelled=None,
    ) -> List[Dict]:
        """
        Fetch fleet carrier market data from Spansh.  Spansh's commodity
        filters (buying_commodities / selling_commodities) do NOT apply to
        carriers, so we fetch recent carriers and match commodities locally.

        Uses parallel pagination (10 pages x 100) sorted by market_updated_at.
        """
        if is_cancelled and is_cancelled():
            return []
        if exclude_carriers:
            return []
        if not MarketplaceAPI._spansh_available():
            print("[SPANSH CARRIERS] Skipped - circuit breaker open (recent failures)")
            return []

        try:
            import math
            from datetime import datetime, timedelta, timezone

            ref_coords = MarketplaceAPI._get_system_coords(reference_system) if reference_system else None
            rx, ry, rz = ref_coords if ref_coords else (0, 0, 0)

            spansh_name = MarketplaceAPI.SPANSH_COMMODITY_MAP.get(
                commodity_normalized, commodity_normalized.title())

            page_errors = [0]

            def _fetch_page(page_num):
                if is_cancelled and is_cancelled():
                    return []
                try:
                    body = {
                        "filters": {"type": {"value": ["Drake-Class Carrier"]}},
                        "sort": [{"market_updated_at": {"direction": "desc"}}],
                        "size": 100,
                        "page": page_num,
                    }
                    resp = tracked_request('spansh', requests.post,
                        f"{MarketplaceAPI.SPANSH_URL}/api/stations/search",
                        json=body, timeout=15)
                    resp.raise_for_status()
                    return resp.json().get("results", [])
                except Exception:
                    page_errors[0] += 1
                    return []

            def _fetch_all_pages():
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(_fetch_page, p) for p in range(2)]
                    pages = []
                    for f in futures:
                        pages.extend(f.result())
                MarketplaceAPI._spansh_record_result(success=page_errors[0] < 2)
                return pages

            # Carrier list doesn't depend on the commodity, so minerals share one download
            raw = _short_cached(("spansh_carriers",), _fetch_all_pages, is_cancelled)

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
                if ref_coords and sx is not None and sy is not None and sz is not None:
                    dist = math.sqrt((sx - rx) ** 2 + (sy - ry) ** 2 + (sz - rz) ** 2)
                    if max_distance and dist > max_distance:
                        continue
                elif max_distance and ref_coords:
                    continue  # No coords, skip when distance-limited
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

                # Spansh uses same field conventions as EDDN.
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
            MarketplaceAPI._spansh_record_result(success=False)
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

            MarketplaceAPI._ensure_source_column()
            with sqlite3.connect(MarketplaceAPI.EDDN_CACHE_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Query commodity data, LEFT JOIN station_metadata to fill in missing
                # station types (commodity messages don't carry stationType).
                cursor.execute('''
                    SELECT c.system_name, c.system_x, c.system_y, c.system_z,
                           c.station_name, c.commodity_name,
                           c.sell_price, c.buy_price, c.demand, c.stock,
                           c.market_id, c.updated_at, c.source,
                           c.station_type                                                     AS cached_type,
                           m.station_type                                                     AS meta_type,
                           CASE WHEN COALESCE(c.station_type, 'Unknown') IN ('', 'Unknown')
                                     AND m.station_type IS NULL AND c.market_id > 0 THEN
                               (SELECT s.station_type FROM commodity_prices_data s
                                WHERE s.market_id = c.market_id AND s.system_name = c.system_name
                                  AND s.station_type NOT IN ('', 'Unknown')
                                ORDER BY s.updated_at DESC LIMIT 1)
                           END                                                                AS sibling_type,
                           -- Live price reports never carry LS; the station's other commodity rows often do.
                           -- Same system only, so a carrier's LS never follows it after a jump.
                           COALESCE(c.distance_to_arrival, m.distance_to_arrival,
                               CASE WHEN c.market_id > 0 THEN
                                   (SELECT s.distance_to_arrival FROM commodity_prices_data s
                                    WHERE s.market_id = c.market_id AND s.system_name = c.system_name
                                      AND s.distance_to_arrival IS NOT NULL
                                    ORDER BY s.updated_at DESC LIMIT 1)
                               END)                                                           AS distance_to_arrival,
                           COALESCE(m.max_landing_pad_size, 0)                                AS meta_pad_size
                    FROM commodity_prices_data c
                    LEFT JOIN station_metadata m ON c.market_id = m.market_id
                    WHERE (LOWER(c.commodity_name) = LOWER(?) OR LOWER(c.commodity_name) = LOWER(?))
                      AND c.updated_at > ?
                ''', (commodity_normalized, spansh_name, cutoff))

                rows = cursor.fetchall()

            # Batch-resolve coordinates for all systems missing them, chunked to stay
            # under SQLite's max-variable limit (can be as low as 999 on some builds).
            coords_cache = {}
            missing_systems = [row["system_name"] for row in rows
                               if row["system_x"] is None and row["system_name"]]
            if missing_systems:
                _CHUNK = 500
                unique_missing = list(set(missing_systems))
                try:
                    from local_database import LocalSystemsDatabase
                    galaxy_db = LocalSystemsDatabase()
                    if galaxy_db.is_database_available():
                        import sqlite3 as _sqlite3
                        with _sqlite3.connect(str(galaxy_db.db_path)) as _gconn:
                            _gconn.row_factory = _sqlite3.Row
                            _gcur = _gconn.cursor()
                            for i in range(0, len(unique_missing), _CHUNK):
                                chunk = unique_missing[i:i + _CHUNK]
                                placeholders = ",".join("?" for _ in chunk)
                                _gcur.execute(
                                    f"SELECT name, x, y, z FROM systems WHERE name IN ({placeholders})",
                                    chunk
                                )
                                for gr in _gcur.fetchall():
                                    coords_cache[gr["name"]] = (gr["x"], gr["y"], gr["z"])
                except Exception as _ce:
                    print(f"[EDDN CACHE] Batch coord lookup failed: {_ce}")
                still_missing = [name for name in unique_missing if name not in coords_cache]
                coords_cache.update(MarketplaceAPI._cached_system_coords(still_missing))

            normalized: List[Dict] = []
            for row in rows:
                sx = row["system_x"]
                sy = row["system_y"]
                sz = row["system_z"]

                if ref_coords and (row['system_name'] or '').casefold() == (reference_system or '').casefold():
                    sx, sy, sz = ref_coords

                # Resolve missing coords from galaxy DB
                if sx is None and row["system_name"] in coords_cache:
                    sx, sy, sz = coords_cache[row["system_name"]]

                # Distance filter
                if ref_coords and sx is not None and sy is not None and sz is not None:
                    dist = math.sqrt((sx - rx) ** 2 + (sy - ry) ** 2 + (sz - rz) ** 2)
                    if max_distance and dist > max_distance:
                        continue
                elif max_distance and ref_coords:
                    continue  # No coords even after lookup, skip
                else:
                    dist = None

                mid = row["market_id"] or 0
                stype = MarketplaceAPI._resolve_cached_station_type(
                    row["cached_type"], row["meta_type"], mid)
                if stype == "Unknown":
                    stype = MarketplaceAPI._resolve_cached_station_type(row["sibling_type"], None, mid)
                is_stronghold = "Stronghold" in stype
                is_carrier = (not is_stronghold) and (
                    "Carrier" in stype or "Drake" in stype
                    or (stype == "Unknown" and MarketplaceAPI._is_carrier_market_id(mid)))
                if exclude_carriers and is_carrier:
                    continue

                # Pass through all fields — UI picks correct ones by mode
                sell_p = row["sell_price"] or 0
                buy_p  = row["buy_price"] or 0
                dem    = row["demand"] or 0
                stk    = row["stock"] or 0

                # Normalize station type for EDDN compatibility
                # Exact matches first; unknown/new types fall through to substring logic below
                _type_map = {
                    "FleetCarrier": "FleetCarrier",
                    "StrongholdCarrier": "StrongholdCarrier",
                    "Coriolis": "Coriolis",
                    "Orbis": "Orbis",
                    "Ocellus": "Ocellus",
                    "Bernal": "Ocellus",  # the journal's name for an Ocellus
                    "Dodec Starport": "Dodec",
                    "Asteroid base": "AsteroidBase",
                    "Dodec": "Dodec",
                    "Outpost": "Outpost",
                    "CraterOutpost": "CraterOutpost",
                    "CraterPort": "CraterPort",
                    "AsteroidBase": "AsteroidBase",
                    "MegaShip": "MegaShip",
                    "OnFootSettlement": "OnFootSettlement",
                    # Trailblazers / colonization types
                    "SpaceConstructionDepot": "OrbitalStation",
                    "PlanetaryConstructionDepot": "SurfaceStation",
                }
                if is_stronghold:
                    mapped_type = "StrongholdCarrier"
                elif is_carrier:
                    mapped_type = "FleetCarrier"
                else:
                    mapped_type = _type_map.get(stype, stype)

                # Determine pad size — prefer station_metadata value, then infer from type
                meta_pad = row["meta_pad_size"] or 0
                if meta_pad > 0:
                    pad_size = meta_pad
                elif is_carrier or mapped_type in ("Coriolis", "Orbis", "Ocellus", "Dodec"):
                    pad_size = 3
                elif mapped_type in ("AsteroidBase", "CraterPort", "MegaShip", "StrongholdCarrier", "OrbitalStation"):
                    pad_size = 3
                elif "Outpost" in mapped_type:
                    pad_size = 2
                else:
                    # Unknown type — don't guess; 0 shows as '?' in UI
                    pad_size = 0

                # distanceToArrival — NULL from commodity messages (not in EDDN schema);
                # may be filled from station_metadata (populated by Docked events).
                dist_to_arrival = row["distance_to_arrival"]  # None if not known

                normalized.append({
                    "marketId":          row["market_id"],
                    "updatedAt":         row["updated_at"] or "",
                    "systemName":        row["system_name"],
                    "stationName":       row["station_name"],
                    "stationType":       mapped_type,
                    "maxLandingPadSize": pad_size,
                    "distance":          dist,
                    "distanceToArrival": dist_to_arrival,
                    "sellPrice":         sell_p,
                    "buyPrice":          buy_p,
                    "demand":            dem,
                    "stock":             stk,
                    "commodityName":     commodity_normalized,
                    "systemX":           sx,
                    "systemY":           sy,
                    "systemZ":           sz,
                    "_source":           row["source"],
                    "_saved":            True,
                })

            print(f"[EDDN CACHE] {filter_type}: {len(normalized)} results for {spansh_name}")
            return normalized

        except Exception as e:
            print(f"[EDDN CACHE] Error: {e}")
            return []

    @staticmethod
    def _ensure_source_column() -> None:
        path = MarketplaceAPI.EDDN_CACHE_PATH
        if not path or path in _source_column_ready:
            return
        import sqlite3
        from eddn_listener import EDDNListener
        try:
            with sqlite3.connect(path) as conn:
                EDDNListener.ensure_source_column(conn.cursor())
            _source_column_ready.add(path)
        except Exception as e:
            print(f"[EDDN CACHE] Source column check failed: {e}")

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
                r = requests.get(url, timeout=15, headers={"User-Agent": "EliteMining/5.1.3"})
                r.raise_for_status()
                coords = r.json().get('coords', {})
                if coords:
                    result = coords['x'], coords['y'], coords['z']
            except Exception:
                pass
        if result is not None:
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
        is_cancelled=None,
    ) -> List[Dict]:
        """
        Spansh nearby search: the 300 most recently updated stations within
        max_distance of reference_system that trade the commodity (3 pages of
        100 fetched concurrently).
        """
        if is_cancelled and is_cancelled():
            return []
        if not MarketplaceAPI._spansh_available():
            print("[SPANSH NEARBY] Skipped - circuit breaker open (recent failures)")
            return []
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

            page_errors = [0]

            # Spansh ignores buying_/selling_commodities filters; only "market" filters the commodity.
            volume_field = "supply" if filter_type == "selling_commodities" else "demand"
            filters = {"market": [{"name": spansh_name,
                                   volume_field: {"comparison": "<=>", "value": [1, 999999999]}}]}
            if max_distance:
                filters["distance"] = {"min": 0, "max": max_distance}

            # Parallel paginated fetch — 3 pages x 100 results
            def _fetch_page(page_num):
                if is_cancelled and is_cancelled():
                    return []
                try:
                    body = {
                        "filters": filters,
                        "sort": [{"market_updated_at": {"direction": "desc"}}],
                        "size": 100,
                        "page": page_num,
                        # Coordinates, not the name: Spansh rejects systems it doesn't know
                        "reference_coords": {"x": rx, "y": ry, "z": rz},
                    }
                    resp = tracked_request('spansh', requests.post,
                        f"{MarketplaceAPI.SPANSH_URL}/api/stations/search",
                        json=body, timeout=15)
                    resp.raise_for_status()
                    return resp.json().get("results", [])
                except Exception as e:
                    print(f"[SPANSH NEARBY] page {page_num} error: {e}")
                    page_errors[0] += 1
                    return []

            def _fetch_all_pages():
                with ThreadPoolExecutor(max_workers=3) as pool:
                    futures = [pool.submit(_fetch_page, p) for p in range(3)]
                    pages = []
                    for f in futures:
                        pages.extend(f.result())
                MarketplaceAPI._spansh_record_result(success=page_errors[0] < 3)
                print(f"[SPANSH NEARBY] fetched {len(pages)} stations from 3 pages")
                return pages

            raw_results = _short_cached(("spansh_nearby", filter_type, spansh_name, rx, ry, rz, max_distance),
                                        _fetch_all_pages, is_cancelled)

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
                "Asteroid base":       "AsteroidBase",
                "Dodec Starport":      "Dodec",
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
                mapped_type = _type_map.get(spansh_type, spansh_type)

                # Skip carriers — handled separately by _fetch_spansh_carriers
                if mapped_type == "FleetCarrier" or spansh_type == "Drake-Class Carrier":
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

                # Spansh uses same field conventions as EDDN:
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
                    "stationType":       mapped_type,
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
            MarketplaceAPI._spansh_record_result(success=False)
            return []


    @staticmethod
    def _fetch_ardent(path: str, params: dict, timeout: int = 10, is_cancelled=None) -> List[Dict]:
        """
        Fetch *path* from Ardent API.
        """
        if is_cancelled and is_cancelled():
            return []
        try:
            url = f"{MarketplaceAPI.ARDENT_URL}{path}"
            r = tracked_request('market', requests.get, url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict) and "results" in data:
                rows = data["results"]
            else:
                rows = []
            print(f"[ARDENT] {len(rows)} results")
            for row in rows:
                if isinstance(row, dict):
                    row["_source"] = "Ardent"
            return rows
        except Exception as e:
            print(f"[ARDENT] {MarketplaceAPI.ARDENT_URL} failed: {e}")
            return []

    @staticmethod
    def _is_carrier_market_id(mid) -> bool:
        # Drake carriers seen so far are 3,700-3,717 million; colony settlements and
        # outposts start around 3,789 million, so the split sits between the two.
        return 3700000000 <= (mid or 0) < 3750000000

    @staticmethod
    def _resolve_cached_station_type(cached_type, meta_type, mid) -> str:
        """Station type for a cached price row. Older builds guessed 'FleetCarrier' for any
        market ID from 3.7 to 4 billion and saved it, which mislabelled colony settlements;
        that saved label is ignored above the carrier range."""
        cached = cached_type or "Unknown"
        if cached == "FleetCarrier" and 3750000000 <= (mid or 0) < 4000000000:
            cached = "Unknown"
        if cached != "Unknown":
            return cached
        return meta_type or "Unknown"

    @staticmethod
    def _merge_by_freshness(rows: List[Dict]) -> List[Dict]:
        """
        Deduplicate by marketId, keeping the fresher price data but
        preserving station metadata (stationType, maxLandingPadSize) from
        whichever source has valid data.  EDDN is freshest for prices but
        often lacks station metadata — Ardent/Spansh fill that in.
        """
        from datetime import datetime, timezone

        def _ts(row: Dict) -> datetime:
            raw = row.get("updatedAt") or ""
            try:
                stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc)
            except (ValueError, TypeError, AttributeError):
                return datetime.min.replace(tzinfo=timezone.utc)

        def _has_meta(row: Dict) -> bool:
            """True when the row carries valid station-type metadata."""
            stype = row.get("stationType") or ""
            return bool(stype) and stype != "Unknown"

        def _pick_dist_to_arrival(winner: Dict, loser: Dict):
            """Return the best (non-None, non-zero) distanceToArrival from either record."""
            w = winner.get("distanceToArrival")
            l = loser.get("distanceToArrival")
            # Prefer a real non-zero value; 0 is valid for fleet carriers
            if w is not None:
                return w
            return l  # may still be None — UI shows '?'

        def _preserve_coords(winner, other):
            axes = ('systemX', 'systemY', 'systemZ')
            same_system = (winner.get('systemName') or '').casefold() == (other.get('systemName') or '').casefold()
            # Carrier coordinates from a previous system must never follow it after a jump.
            if same_system and winner.get('systemName') and any(winner.get(k) is None for k in axes) and all(other.get(k) is not None for k in axes):
                winner = dict(winner)
                for key in axes:
                    winner[key] = other[key]
            return winner

        best: Dict[int, Dict] = {}
        no_id: List[Dict] = []

        for row in rows:
            mid = row.get("marketId")
            if mid is None:
                no_id.append(row)
                continue
            if mid not in best:
                best[mid] = row
            else:
                existing = best[mid]
                # On equal timestamps the saved copy is usually this same live record backfilled earlier.
                if _ts(row) > _ts(existing) or (_ts(row) == _ts(existing) and existing.get("_saved") and not row.get("_saved")):
                    # Newer record wins for pricing data
                    merged = dict(row)
                    # Preserve metadata from older record if newer lacks it
                    if not _has_meta(merged) and _has_meta(existing):
                        merged["stationType"] = existing["stationType"]
                    if merged.get("maxLandingPadSize", 0) <= 1 and existing.get("maxLandingPadSize", 0) > 1:
                        merged["maxLandingPadSize"] = existing["maxLandingPadSize"]
                    merged["distanceToArrival"] = _pick_dist_to_arrival(merged, existing)
                    best[mid] = _preserve_coords(merged, existing)
                else:
                    # Existing is newer — patch in metadata from newer row if existing lacks it
                    if not _has_meta(existing) and _has_meta(row):
                        best[mid] = dict(existing)
                        best[mid]["stationType"] = row["stationType"]
                    if existing.get("maxLandingPadSize", 0) <= 1 and row.get("maxLandingPadSize", 0) > 1:
                        best[mid] = dict(best[mid])
                        best[mid]["maxLandingPadSize"] = row["maxLandingPadSize"]
                    if best[mid].get("distanceToArrival") is None:
                        best[mid] = dict(best[mid])
                        best[mid]["distanceToArrival"] = _pick_dist_to_arrival(existing, row)
                    best[mid] = _preserve_coords(best[mid], row)

        merged = list(best.values()) + no_id
        source_counts: Dict[str, int] = {}
        for row in merged:
            label = row.get("_source") or ("Saved" if row.get("_saved") else "Unknown")
            source_counts[label] = source_counts.get(label, 0) + 1
        print(f"[DUAL-API] After merge: {len(merged)} unique results")
        print(f"[DUAL-API] Price sources: {', '.join(f'{k} {v}' for k, v in sorted(source_counts.items()))}")
        return merged

    @staticmethod
    def _backfill_eddn_cache(rows: List[Dict]) -> None:
        """Write live Ardent/Spansh search results into the local EDDN cache
        (commodity_prices_data) so the next lookup for the same station finds it
        locally, even if EliteMining's own EDDN listener never saw that station's
        market broadcast live. Only tracked commodities are stored, matching what
        the listener itself keeps.
        """
        if not MarketplaceAPI.EDDN_CACHE_PATH or not rows:
            return
        try:
            import sqlite3, os
            from eddn_listener import EDDNListener

            if not os.path.exists(MarketplaceAPI.EDDN_CACHE_PATH):
                return

            to_write = [r for r in rows if r.get("marketId") and r.get("systemName")
                        and r.get("commodityName", "").lower() in EDDNListener.TRACKED_COMMODITIES]
            if not to_write:
                return

            MarketplaceAPI._ensure_source_column()
            with sqlite3.connect(MarketplaceAPI.EDDN_CACHE_PATH) as conn:
                cursor = conn.cursor()
                for r in to_write:
                    cursor.execute(EDDNListener.PRICE_UPSERT_SQL, (r.get("systemName"), r.get("systemX"), r.get("systemY"), r.get("systemZ"),
                          r.get("stationName"), r.get("stationType"), r.get("commodityName", "").lower(),
                          r.get("sellPrice", 0), r.get("buyPrice", 0), r.get("demand", 0), r.get("stock", 0),
                          r.get("distanceToArrival"), r.get("marketId"), r.get("updatedAt"), r.get("_source")))
                conn.commit()
        except Exception as e:
            print(f"[EDDN CACHE] Backfill error: {e}")

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
    def convert_age_to_days(age_str: str) -> int:
        """Max Age label to the whole-day window the price APIs accept (sub-day values round up to 1)."""
        age_map = {"Any": 30, "1 hour": 1, "8 hours": 1, "16 hours": 1, "1 day": 1, "2 days": 2}
        return age_map.get(age_str, 1)

    @staticmethod
    def search_buyers(commodity: str, reference_system: str, max_distance: Optional[int] = None, max_days_ago: float = 2, exclude_carriers: bool = False, is_cancelled=None) -> List[Dict]:
        """
        Search for stations buying a commodity near a reference system (for SELLING to them)
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            reference_system: Reference system name
            max_distance: Maximum distance in light years (None uses the default 500 LY search)
            max_days_ago: Maximum age of data in days (default 2)
            exclude_carriers: Whether to exclude Fleet Carriers from results
            
        Returns:
            List of station data dictionaries with keys:
            - system_name, station_name, station_type
            - sell_price, demand
            - system_distance, arrival_distance
            - updated
        """
        if is_cancelled and is_cancelled():
            return []
        try:
            # Normalize and URL encode commodity and system names
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            system_encoded = urllib.parse.quote(reference_system)

            # --- Nearby imports (both APIs in parallel) ---
            nearby_path = f"/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/imports"
            search_distance = 500 if max_distance is None else max_distance
            nearby_params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago,
                "maxDistance": search_distance,
            }
            if exclude_carriers:
                nearby_params["fleetCarriers"] = False

            print(f"[BUYERS] nearby path: {nearby_path} params: {nearby_params}")

            local_path = f"/system/name/{system_encoded}/commodities/imports"
            local_params = {"minVolume": 1, "maxDaysAgo": max_days_ago}

            # Run Ardent, Spansh stations, Spansh carriers, EDDN cache and the reference-system list in parallel
            with ThreadPoolExecutor(max_workers=5) as _pool:
                # Same response for every commodity in this system - fetch once, filter per commodity
                _fut_local = _pool.submit(
                    _short_cached,
                    ("ardent_local", reference_system, max_days_ago),
                    lambda: MarketplaceAPI._fetch_ardent(local_path, local_params, is_cancelled=is_cancelled), is_cancelled)
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_ardent, nearby_path, nearby_params, is_cancelled=is_cancelled)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh_nearby,
                    commodity_normalized, reference_system, "buying_commodities",
                    search_distance, max_days_ago, exclude_carriers, 500, is_cancelled=is_cancelled
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, reference_system, "buying_commodities",
                    search_distance, max_days_ago, exclude_carriers, is_cancelled=is_cancelled
                )
                _fut_eddn = _pool.submit(
                    MarketplaceAPI._fetch_eddn_cache,
                    commodity_normalized, reference_system, "buying_commodities",
                    search_distance, max_days_ago, exclude_carriers
                )
                nearby_rows  = _fut_both.result()
                spansh_rows  = _fut_spansh.result()
                carrier_rows = _fut_carriers.result()
                eddn_rows    = _fut_eddn.result()
                local_rows_raw = _fut_local.result()
            nearby_rows = nearby_rows + spansh_rows + carrier_rows + eddn_rows

            if is_cancelled and is_cancelled():
                return MarketplaceAPI._merge_by_freshness(nearby_rows)

            print(f"[BUYERS] local path: {local_path}")
            local_rows = [r for r in local_rows_raw if r.get("commodityName", "").lower() == commodity_normalized]
            for r in local_rows:
                r["distance"] = 0

            print(f"[BUYERS] nearby={len(nearby_rows)} local={len(local_rows)}")
            results = MarketplaceAPI._merge_by_freshness(nearby_rows + local_rows)
            MarketplaceAPI._backfill_eddn_cache(results)
            if max_distance is not None and max_distance > 0:
                results = [r for r in results if r.get('distance') is not None and r['distance'] <= max_distance]
            if exclude_carriers:
                results = [r for r in results if 'FleetCarrier' not in (r.get('stationType') or '')]
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[MARKET API] Request error: {e}")
            return []
        except Exception as e:
            print(f"[MARKET API] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_sellers(commodity: str, reference_system: str, max_distance: Optional[int] = None, max_days_ago: float = 2, exclude_carriers: bool = True, is_cancelled=None) -> List[Dict]:
        """
        Search for stations selling a commodity near a reference system (for BUYING from them)
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            reference_system: Reference system name
            max_distance: Maximum distance in light years (None uses the default 500 LY search)
            max_days_ago: Maximum age of data in days (default 2)
            
        Returns:
            List of station data dictionaries with keys:
            - system_name, station_name, station_type
            - buy_price, stock
            - system_distance, arrival_distance
            - updated
        """
        if is_cancelled and is_cancelled():
            return []
        try:
            import urllib.parse
            commodity_normalized = MarketplaceAPI.normalize_commodity_name(commodity)
            commodity_encoded = urllib.parse.quote(commodity_normalized)
            system_encoded = urllib.parse.quote(reference_system)

            # --- Nearby exports (both APIs in parallel) ---
            nearby_path = f"/system/name/{system_encoded}/commodity/name/{commodity_encoded}/nearby/exports"
            search_distance = 500 if max_distance is None else max_distance
            nearby_params = {
                "minVolume": 1,
                "maxDaysAgo": max_days_ago,
                "maxDistance": search_distance,
            }
            if exclude_carriers:
                nearby_params["fleetCarriers"] = False

            print(f"[SELLERS] nearby path: {nearby_path} params: {nearby_params}")

            local_path = f"/system/name/{system_encoded}/commodities/exports"
            local_params = {"minVolume": 1, "maxDaysAgo": max_days_ago}

            # Run Ardent, Spansh stations, Spansh carriers, EDDN cache and the reference-system list in parallel
            with ThreadPoolExecutor(max_workers=5) as _pool:
                # Same response for every commodity in this system - fetch once, filter per commodity
                _fut_local = _pool.submit(
                    _short_cached,
                    ("ardent_local_exports", reference_system, max_days_ago),
                    lambda: MarketplaceAPI._fetch_ardent(local_path, local_params, is_cancelled=is_cancelled), is_cancelled)
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_ardent, nearby_path, nearby_params, is_cancelled=is_cancelled)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh_nearby,
                    commodity_normalized, reference_system, "selling_commodities",
                    search_distance, max_days_ago, exclude_carriers, 500, is_cancelled=is_cancelled
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, reference_system, "selling_commodities",
                    search_distance, max_days_ago, exclude_carriers, is_cancelled=is_cancelled
                )
                _fut_eddn = _pool.submit(
                    MarketplaceAPI._fetch_eddn_cache,
                    commodity_normalized, reference_system, "selling_commodities",
                    search_distance, max_days_ago, exclude_carriers
                )
                nearby_rows  = _fut_both.result()
                spansh_rows  = _fut_spansh.result()
                carrier_rows = _fut_carriers.result()
                eddn_rows    = _fut_eddn.result()
                local_rows_raw = _fut_local.result()
            nearby_rows = nearby_rows + spansh_rows + carrier_rows + eddn_rows

            if is_cancelled and is_cancelled():
                return MarketplaceAPI._merge_by_freshness(nearby_rows)

            print(f"[SELLERS] local path: {local_path}")
            local_rows = [r for r in local_rows_raw if r.get("commodityName", "").lower() == commodity_normalized]
            for r in local_rows:
                r["distance"] = 0
                # Local exports endpoint is scoped to reference_system by the URL and
                # doesn't echo systemName back - stamp it so callers filtering by exact
                # system match (e.g. PowerPlay reinforce/undermine pricing) see these rows.
                r["systemName"] = reference_system
                # Local exports endpoint has buyPrice as the actual price
                if r.get("sellPrice", 0) == 0 and r.get("buyPrice", 0) > 0:
                    r["sellPrice"] = r["buyPrice"]

            print(f"[SELLERS] nearby={len(nearby_rows)} local={len(local_rows)}")
            results = MarketplaceAPI._merge_by_freshness(nearby_rows + local_rows)
            MarketplaceAPI._backfill_eddn_cache(results)
            if max_distance is not None and max_distance > 0:
                results = [r for r in results if r.get('distance') is not None and r['distance'] <= max_distance]
            if exclude_carriers:
                results = [r for r in results if 'FleetCarrier' not in (r.get('stationType') or '')]
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"[MARKET API SELLERS] Request error: {e}")
            return []
        except Exception as e:
            print(f"[MARKET API SELLERS] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_buyers_galaxy_wide(commodity: str, max_days_ago: float = 2, exclude_carriers: bool = False, is_cancelled=None) -> List[Dict]:
        """
        Search for top 100 best prices galaxy-wide (no distance limit) - for SELLING to them
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            max_days_ago: Maximum age of data in days (default 2)
            exclude_carriers: Whether to exclude fleet carriers (default False)
            
        Returns:
            List of station data dictionaries sorted by highest price
        """
        if is_cancelled and is_cancelled():
            return []
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
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_ardent, path, params, is_cancelled=is_cancelled)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh,
                    commodity_normalized, "Sol", "buying_commodities",
                    0, max_days_ago, exclude_carriers, 1000, is_cancelled=is_cancelled
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, None, "buying_commodities",
                    0, max_days_ago, exclude_carriers, is_cancelled=is_cancelled
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
            MarketplaceAPI._backfill_eddn_cache(results)
            return results

        except requests.exceptions.RequestException as e:
            print(f"[MARKET API GALAXY] Request error: {e}")
            return []
        except Exception as e:
            print(f"[MARKET API GALAXY] Unexpected error: {e}")
            return []
    
    @staticmethod
    def search_sellers_galaxy_wide(commodity: str, max_days_ago: float = 2, exclude_carriers: bool = True, is_cancelled=None) -> List[Dict]:
        """
        Search for top 100 best prices galaxy-wide (no distance limit) - for BUYING from them
        
        Args:
            commodity: Commodity name (e.g., "Painite", "Low Temperature Diamonds", "Void Opals")
            max_days_ago: Maximum age of data in days (default 2)
            
        Returns:
            List of station data dictionaries sorted by lowest price
        """
        if is_cancelled and is_cancelled():
            return []
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
                _fut_both   = _pool.submit(MarketplaceAPI._fetch_ardent, path, params, is_cancelled=is_cancelled)
                _fut_spansh = _pool.submit(
                    MarketplaceAPI._fetch_spansh,
                    commodity_normalized, "Sol", "selling_commodities",
                    0, max_days_ago, exclude_carriers, 1000, is_cancelled=is_cancelled
                )
                _fut_carriers = _pool.submit(
                    MarketplaceAPI._fetch_spansh_carriers,
                    commodity_normalized, None, "selling_commodities",
                    0, max_days_ago, exclude_carriers, is_cancelled=is_cancelled
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
            MarketplaceAPI._backfill_eddn_cache(results)
            return results

        except requests.exceptions.RequestException as e:
            print(f"[MARKET API GALAXY SELLERS] Request error: {e}")
            return []
        except Exception as e:
            print(f"[MARKET API GALAXY SELLERS] Unexpected error: {e}")
            return []
    
    @staticmethod
    def _cached_system_coords(system_names) -> Dict[str, tuple]:
        """Coordinates from the market cache: other price records, then EDDN jump and docking reports."""
        coord_lookup = {}
        if not MarketplaceAPI.EDDN_CACHE_PATH or not system_names:
            return coord_lookup
        try:
            import sqlite3
            from contextlib import closing
            system_names = list(system_names)
            with closing(sqlite3.connect(MarketplaceAPI.EDDN_CACHE_PATH)) as conn:
                for start in range(0, len(system_names), 500):
                    names = system_names[start:start + 500]
                    placeholders = ','.join('?' for _ in names)
                    rows = conn.execute(
                        f"SELECT system_name, system_x, system_y, system_z FROM commodity_prices_data "
                        f"WHERE system_name IN ({placeholders}) "
                        "AND system_x IS NOT NULL AND system_y IS NOT NULL AND system_z IS NOT NULL "
                        "ORDER BY updated_at", names)
                    for name, x, y, z in rows:
                        coord_lookup[name] = (x, y, z)
                    rows = conn.execute(
                        f"SELECT name, x, y, z FROM system_coords WHERE name IN ({placeholders}) "
                        "AND x IS NOT NULL AND y IS NOT NULL AND z IS NOT NULL", names)
                    for name, x, y, z in rows:
                        coord_lookup[name] = (x, y, z)
        except Exception as e:
            logging.warning("[DISTANCE CALC] Market coord lookup failed: %s", e)
        return coord_lookup

    @staticmethod
    def add_distances_to_results(results: List[Dict], reference_system: str, is_cancelled=None) -> List[Dict]:
        """
        Add distance information to galaxy-wide results using local database + EDSM fallback
        
        Args:
            results: List of result dictionaries (with systemX/Y/Z from API)
            reference_system: Name of the reference system
            
        Returns:
            Same list with 'distance' key added to each result
        """
        try:
            if is_cancelled and is_cancelled():
                return results
            ref_coords = MarketplaceAPI._get_system_coords(reference_system)
            if ref_coords is None:
                logging.warning("[DISTANCE CALC] No reference coordinates for %s; %d results", reference_system, len(results))
                return results
            ref_x, ref_y, ref_z = ref_coords

            for result in results:
                if (result.get('systemName') or '').casefold() == reference_system.casefold():
                    result['systemX'], result['systemY'], result['systemZ'] = ref_coords
                    result['distance'] = 0.0

            # Batch-resolve missing coords from galaxy DB for results without systemX/Y/Z
            missing_coord_results = [r for r in results
                                     if any(r.get(axis) is None for axis in ('systemX', 'systemY', 'systemZ')) and r.get('systemName')]
            if missing_coord_results:
                try:
                    from local_database import LocalSystemsDatabase
                    import sqlite3 as _sqlite3
                    galaxy_db = LocalSystemsDatabase()
                    if galaxy_db.is_database_available():
                        missing_names = list({r['systemName'] for r in missing_coord_results})
                        placeholders = ",".join("?" for _ in missing_names)
                        with _sqlite3.connect(str(galaxy_db.db_path)) as _conn:
                            _conn.row_factory = _sqlite3.Row
                            _cur = _conn.cursor()
                            _cur.execute(
                                f"SELECT name, x, y, z FROM systems WHERE name IN ({placeholders})",
                                missing_names
                            )
                            coord_lookup = {row['name']: (row['x'], row['y'], row['z'])
                                            for row in _cur.fetchall()}
                        for result in missing_coord_results:
                            coords = coord_lookup.get(result['systemName'])
                            if coords:
                                result['systemX'], result['systemY'], result['systemZ'] = coords
                except Exception as _ce:
                    logging.warning("[DISTANCE CALC] Batch coord lookup failed: %s", _ce)

            if MarketplaceAPI.EDDN_CACHE_PATH:
                missing_names = list({r['systemName'] for r in missing_coord_results
                                      if any(r.get(axis) is None for axis in ('systemX', 'systemY', 'systemZ'))})
                coord_lookup = MarketplaceAPI._cached_system_coords(missing_names)
                for result in missing_coord_results:
                    coords = coord_lookup.get(result['systemName'])
                    if coords:
                        result['systemX'], result['systemY'], result['systemZ'] = coords

            missing_names = list({r['systemName'] for r in missing_coord_results
                                  if any(r.get(axis) is None for axis in ('systemX', 'systemY', 'systemZ'))})
            coord_lookup = {name.casefold(): _system_coords_cache[name] for name in missing_names
                            if _system_coords_cache.get(name) is not None}
            missing_names = [name for name in missing_names if name.casefold() not in coord_lookup]

            def wait_for_edsm(seconds):
                while seconds > 0:
                    if is_cancelled and is_cancelled():
                        return False
                    pause = min(seconds, 0.1)
                    _time_mod.sleep(pause)
                    seconds -= pause
                return not (is_cancelled and is_cancelled())

            def fetch_coords(names):
                for attempt in range(3):
                    if is_cancelled and is_cancelled():
                        return None
                    try:
                        response = requests.get(
                            'https://www.edsm.net/api-v1/systems',
                            params=[('systemName[]', name) for name in names] + [('showCoordinates', 1)],
                            headers={'User-Agent': 'EliteMining/5.1.3'}, timeout=15)
                        if response.status_code == 429:
                            retry_after = response.headers.get('Retry-After')
                            try:
                                delay = max(1.1, float(retry_after))
                            except (TypeError, ValueError):
                                from email.utils import parsedate_to_datetime
                                try:
                                    delay = max(1.1, parsedate_to_datetime(retry_after).timestamp() - _time_mod.time())
                                except (TypeError, ValueError, AttributeError):
                                    delay = 10 * (2 ** attempt)
                            logging.warning("[DISTANCE CALC] EDSM rate limit; retry %d/3 in %.1fs",
                                            attempt + 1, delay)
                            if attempt == 2 or not wait_for_edsm(delay):
                                return None
                            continue
                        response.raise_for_status()
                        return response.json()
                    except Exception as e:
                        logging.warning("[DISTANCE CALC] EDSM batch lookup failed (%d systems; sample %s): %s",
                                        len(names), names[:3], str(e).split(' for url:')[0])
                        return []

            logging.info("[DISTANCE CALC] Reference %s; %d results; %d systems need EDSM",
                         reference_system, len(results), len(missing_names))
            for start in range(0, len(missing_names), 100):
                if start and not wait_for_edsm(1.1):
                    break
                systems = fetch_coords(missing_names[start:start + 100])
                if systems is None:
                    break
                for system in systems:
                    coords = system.get('coords') or {}
                    if all(coords.get(axis) is not None for axis in ('x', 'y', 'z')):
                        name = system['name'].casefold()
                        coord_lookup[name] = coords['x'], coords['y'], coords['z']
                        _system_coords_cache[name] = coord_lookup[name]
            for name in missing_names:
                coords = coord_lookup.get(name.casefold())
                if coords:
                    _system_coords_cache[name] = coords
            for result in missing_coord_results:
                coords = coord_lookup.get(result['systemName'].casefold())
                if coords:
                    result['systemX'], result['systemY'], result['systemZ'] = coords

            # Calculate distance for each result
            for result in results:
                if is_cancelled and is_cancelled():
                    break
                sys_x = result.get('systemX')
                sys_y = result.get('systemY')
                sys_z = result.get('systemZ')

                if sys_x is not None and sys_y is not None and sys_z is not None:
                    try:
                        dx = float(sys_x) - ref_x
                        dy = float(sys_y) - ref_y
                        dz = float(sys_z) - ref_z
                        result['distance'] = (dx**2 + dy**2 + dz**2) ** 0.5
                    except (TypeError, ValueError) as e:
                        print(f"[DISTANCE CALC] Bad coords for {result.get('systemName')}: {e}")

            unresolved = [r.get('systemName') for r in results if r.get('distance') is None]
            logging.info("[DISTANCE CALC] Completed: %d/%d distances; unresolved sample: %s",
                         len(results) - len(unresolved), len(results), list(dict.fromkeys(unresolved))[:10])
            return results
            
        except Exception:
            logging.exception("[DISTANCE CALC] Failed")
            return results
    

    @staticmethod
    def filter_results_by_age(results, max_age_str):
        """Filter results by max age locally (for accurate hour-level filtering)

        The API only supports maxDaysAgo (integer days), so for hour-based filters
        we need to filter the results locally using the updatedAt timestamp.

        NOTE: Filter values are set to include results that DISPLAY as that time.
        e.g., "1 hour" filter includes results showing "1h" (60-119 min old)
        """
        from datetime import datetime, timezone, timedelta

        # Map age string to hours (values include the displayed hour range)
        age_hours_map = {
            "Any": None,       # No filtering
            "1 hour": 2,       # Include results showing "1h" (60-119 min)
            "8 hours": 9,      # Include results showing "8h" (480-539 min)
            "16 hours": 17,    # Include results showing "16h"
            "1 day": 25,       # Include results showing "1d" (24h)
            "2 days": 49       # Include results showing "2d" (48h)
        }

        max_hours = age_hours_map.get(max_age_str)
        if max_hours is None:
            return results  # No age filtering

        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=max_hours)

        filtered = []
        for result in results:
            updated_at = result.get('updatedAt')
            if not updated_at:
                continue  # Skip results without timestamp

            try:
                # Parse ISO timestamp (e.g., "2024-11-03T12:30:00Z" or "2024-11-03T12:30:00.000Z")
                updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                updated_time = updated_time.replace(tzinfo=updated_time.tzinfo or timezone.utc)
                if updated_time >= cutoff_time:
                    filtered.append(result)
            except Exception:
                # If parsing fails, include the result (conservative)
                filtered.append(result)

        return filtered


    @staticmethod
    def filter_results(results, station_type='All', max_age='Any', exclude_carriers=False,
                       large_pad=False, is_buy_mode=False):
        volume = 'stock' if is_buy_mode else 'demand'
        price = 'buyPrice' if is_buy_mode else 'sellPrice'
        results = [r for r in results if r.get(volume, 0) > 0 and r.get(price, 0) > 0]
        if exclude_carriers and station_type != 'Fleet Carrier':
            results = [r for r in results if 'FleetCarrier' not in (r.get('stationType') or '')]
        orbital = ('Coriolis', 'Orbis', 'Ocellus', 'Bernal', 'Outpost', 'Asteroid', 'Dodec', 'Orbital', 'Space')
        surface = ('Crater', 'OnFoot', 'Planetary', 'Surface', 'Ground', 'Settlement')
        if station_type == 'Orbital':
            results = [r for r in results if any(k in (r.get('stationType') or '') for k in orbital)
                       and not any(k in (r.get('stationType') or '') for k in surface)]
        elif station_type == 'Surface':
            results = [r for r in results if any(k in (r.get('stationType') or '') for k in surface)]
        elif station_type in ('Fleet Carrier', 'Megaship', 'Stronghold'):
            keyword = {'Fleet Carrier': 'FleetCarrier', 'Megaship': 'Mega', 'Stronghold': 'Stronghold'}[station_type]
            results = [r for r in results if keyword in (r.get('stationType') or '')]
        if large_pad:
            results = [r for r in results if r.get('maxLandingPadSize') == 3]
        return MarketplaceAPI.filter_results_by_age(results, max_age)

    @staticmethod
    def prepare_galaxy_results(results, order_by, is_buy_mode=False, max_results=250,
                               reference_system='', is_cancelled=None, on_distances=None):
        ranked = MarketplaceAPI.sort_results(results, order_by, is_buy_mode)
        distance_sort = order_by == 'Distance'
        if max_results is not None and not distance_sort:
            ranked = ranked[:max_results]
        if ranked and reference_system and not (is_cancelled and is_cancelled()):
            if on_distances:
                on_distances()
            ranked = MarketplaceAPI.add_distances_to_results(ranked, reference_system, is_cancelled=is_cancelled)
            ranked = MarketplaceAPI.sort_results(ranked, order_by, is_buy_mode)
        return ranked if max_results is None else ranked[:max_results]

    @staticmethod
    def sort_results(results, order_by, is_buy_mode=False):
        if 'Best price' in order_by:
            field = 'buyPrice' if is_buy_mode else 'sellPrice'
            return sorted(results, key=lambda r: r.get(field, 0), reverse=not is_buy_mode)
        if any(word in order_by.lower() for word in ('supply', 'stock', 'demand')):
            field = 'stock' if is_buy_mode else 'demand'
            return sorted(results, key=lambda r: r.get(field, 0), reverse=True)
        if 'Last update' in order_by:
            from datetime import datetime, timezone
            def timestamp(row):
                try:
                    stamp = datetime.fromisoformat(row.get('updatedAt', '').replace('Z', '+00:00'))
                    return stamp.replace(tzinfo=stamp.tzinfo or timezone.utc)
                except (ValueError, TypeError, AttributeError):
                    return datetime.min.replace(tzinfo=timezone.utc)
            return sorted(results, key=timestamp, reverse=True)
        return sorted(results, key=lambda r: float('inf') if r.get('distance') is None else r['distance'])
