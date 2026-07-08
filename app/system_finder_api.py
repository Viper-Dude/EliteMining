"""
System Finder API - Spansh API integration for system searches
Provides nearby system lookup with full server-side filtering (security, allegiance, state, etc.)
"""
import requests
import logging
import sqlite3
import json
import re
import datetime
from typing import List, Dict, Optional, Any

log = logging.getLogger(__name__)


class SystemFinderAPI:
    """Spansh API integration for system finder functionality with server-side filtering"""

    # Spansh API URLs
    SPANSH_URL = "https://spansh.co.uk/api/systems/search"
    SPANSH_STATIONS_URL = "https://spansh.co.uk/api/stations/search"

    # Request timeout
    TIMEOUT = 30

    # Maximum results to return
    MAX_RESULTS = 500

    # Set from main.py after EDDN listener starts — enables local powerplay cache lookups
    EDDN_CACHE_PATH = None
    
    @classmethod
    def _batch_get_powerplay(cls, system_names: List[str]) -> Dict[str, Dict]:
        """
        Query local EDDN powerplay cache for a list of systems in one SQL call.
        Returns {system_name: {controlling_power, power_state}} for hits only.
        Falls back to empty dict if cache unavailable.
        """
        if not cls.EDDN_CACHE_PATH or not system_names:
            return {}
        try:
            placeholders = ','.join('?' * len(system_names))
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                rows = conn.execute(
                    f'SELECT system_name, controlling_power, power_state, updated_at FROM system_powerplay'
                    f' WHERE system_name IN ({placeholders}) COLLATE NOCASE',
                    system_names
                ).fetchall()
            return {
                row[0]: {'controlling_power': row[1], 'power_state': row[2], 'updated_at': row[3]}
                for row in rows if row[1]  # only rows where controlling_power is known
            }
        except Exception as e:
            log.debug(f"[SYSTEM_FINDER] EDDN powerplay batch lookup error: {e}")
            return {}

    @classmethod
    def _get_powerplay_from_cache(cls, system_name: str) -> Optional[Dict]:
        """Single-system EDDN powerplay cache lookup. Returns None if not cached."""
        if not cls.EDDN_CACHE_PATH:
            return None
        try:
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                row = conn.execute(
                    'SELECT controlling_power, power_state, updated_at FROM system_powerplay'
                    ' WHERE system_name = ? COLLATE NOCASE',
                    (system_name,)
                ).fetchone()
            if row and row[0]:
                return {'controlling_power': row[0], 'power_state': row[1], 'updated_at': row[2]}
        except Exception as e:
            log.debug(f"[SYSTEM_FINDER] EDDN powerplay lookup error: {e}")
        return None

    # Actual Inara HTML: <span class="bigger"><span class="positive">Stronghold</span></span>
    # The nested span inside "bigger" requires (?:<[^>]+>)? to skip the inner tag.
    _INARA_PP_PATTERN = re.compile(
        r'<span class="uppercase minor small">Powerplay</span>'
        r'.*?<a href="/elite/power/\d+/">([^<]+)</a>\s*<small>\(Controlling\)</small>'
        r'.*?<span class="bigger">(?:<[^>]+>)?([^<]+)</span>',
        re.DOTALL
    )

    # No controlling power: <span class="bigger">Expansion</span> or
    # <span class="bigger"><span class="minor">Unoccupied</span></span>
    _INARA_PP_NO_CONTROLLER_PATTERN = re.compile(
        r'<span class="uppercase minor small">Powerplay</span>\s*<br>\s*'
        r'<span class="bigger">(?:<[^>]+>)?([^<]+)<'
    )

    _INARA_CHALLENGE_PATTERN = re.compile(r"'([a-f0-9]{32})'")

    _INARA_HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    @classmethod
    def fetch_and_store_powerplay_from_inara(cls, system_name: str) -> Optional[Dict]:
        """Fetch powerplay data for system_name from Inara and store to cache.
        Returns {'controlling_power': ..., 'power_state': ...} on success, None on failure."""
        if not cls.EDDN_CACHE_PATH:
            return None
        try:
            import urllib.parse, random
            url = f"https://inara.cz/elite/starsystem/?search={urllib.parse.quote(system_name)}"
            session = requests.Session()
            session.headers.update(cls._INARA_HEADERS)
            resp = session.get(url, timeout=10)
            html = resp.text
            # Inara bot challenge: 503 page with a base64-encoded /validatechallenge.php endpoint
            if resp.status_code == 503 or 'challenge-container' in html:
                cm = cls._INARA_CHALLENGE_PATTERN.search(html)
                if cm:
                    token = cm.group(1)
                    ts = int(datetime.datetime.utcnow().timestamp() * 1000)
                    cf = random.randint(0, 9999)
                    session.post(
                        'https://inara.cz/validatechallenge.php',
                        data=f'challenge={urllib.parse.quote(token)}&ts={ts}&cf={cf}',
                        headers={'Content-Type': 'application/x-www-form-urlencoded'},
                        timeout=10
                    )
                    resp = session.get(url, timeout=10)
                    resp.raise_for_status()
                    html = resp.text
            m = cls._INARA_PP_PATTERN.search(html)
            timestamp = datetime.datetime.utcnow().isoformat()
            if m:
                controlling_power = m.group(1).strip()
                power_state = m.group(2).strip()
            else:
                m2 = cls._INARA_PP_NO_CONTROLLER_PATTERN.search(html)
                if m2:
                    controlling_power = '~none~'
                    power_state = m2.group(1).strip()
                elif len(html) > 15000:
                    # Valid system page but Powerplay section didn't match either pattern
                    controlling_power = '~none~'
                    power_state = ''
                else:
                    return None
            with sqlite3.connect(cls.EDDN_CACHE_PATH) as conn:
                conn.execute(
                    'INSERT OR REPLACE INTO system_powerplay '
                    '(system_name, controlling_power, power_state, powers, updated_at) '
                    'VALUES (?, ?, ?, ?, ?)',
                    (system_name, controlling_power, power_state, None, timestamp)
                )
                conn.commit()
            return {'controlling_power': controlling_power, 'power_state': power_state}
        except Exception as e:
            log.debug(f"[POWERPLAY] Inara fetch error for {system_name!r}: {e}")
            return None

    @classmethod
    def search_systems(cls, reference_system: str, filters: Dict[str, str] = None,
                       max_results: int = None, progress_callback=None) -> List[Dict]:
        """
        Search for systems using Spansh API with server-side filtering.
        
        Args:
            reference_system: Name of the reference system
            filters: Dict of filter criteria:
                - security: 'Any' or specific value (High, Medium, Low, Anarchy)
                - allegiance: 'Any' or specific value (Federation, Empire, Alliance, Independent)
                - government: 'Any' or specific value
                - state: 'Any' or specific value (War, Boom, Bust, etc.)
                - economy: 'Any' or specific value
                - population: 'Any' or population range key
            max_results: Maximum number of results (default 100)
            progress_callback: Optional callback(current, total, message) for progress
            
        Returns:
            List of systems with full status info, sorted by distance
        """
        if progress_callback:
            progress_callback(0, 100, "Searching systems...")
        
        max_results = max_results or cls.MAX_RESULTS
        filters = filters or {}
        
        # Build Spansh filter object
        spansh_filters = cls._build_spansh_filters(filters)
        
        # Build request payload
        payload = {
            'reference_system': reference_system,
            'size': max_results,
            'sort': [{'distance': {'direction': 'asc'}}]
        }
        
        if spansh_filters:
            payload['filters'] = spansh_filters
        
        log.info(f"[SYSTEM_FINDER] Searching near {reference_system} with filters: {filters}")
        print(f"[SYSTEM_FINDER DEBUG] Spansh payload: {payload}")
        
        try:
            if progress_callback:
                progress_callback(20, 100, "Searching Spansh galaxy database...")
            
            response = requests.post(cls.SPANSH_URL, json=payload, timeout=cls.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            total_count = data.get('count', 0)
            results = data.get('results', [])
            
            log.info(f"[SYSTEM_FINDER] Spansh returned {len(results)} of {total_count} matching systems")
            print(f"[SYSTEM_FINDER DEBUG] Found {total_count} total, returned {len(results)}")
            
            if progress_callback:
                progress_callback(80, 100, f"Processing {len(results)} results...")
            
            # Batch-fetch powerplay data from local EDDN cache for all returned systems
            system_names = [s.get('name', '') for s in results if s.get('name')]
            pp_cache = cls._batch_get_powerplay(system_names)

            # Convert Spansh format to our format
            converted = []
            for system in results:
                converted.append(cls._convert_spansh_system(system, pp_cache))
            
            if progress_callback:
                progress_callback(100, 100, f"Found {len(converted)} systems")
            
            return converted
            
        except requests.exceptions.RequestException as e:
            log.error(f"[SYSTEM_FINDER] Spansh API error: {e}")
            print(f"[SYSTEM_FINDER DEBUG] API error: {e}")
            return []
        except Exception as e:
            log.error(f"[SYSTEM_FINDER] Unexpected error: {e}")
            print(f"[SYSTEM_FINDER DEBUG] Unexpected error: {e}")
            return []
    
    @classmethod
    def _build_spansh_filters(cls, filters: Dict[str, str]) -> Dict:
        """Convert our filter format to Spansh API format"""
        spansh_filters = {}
        
        # Security filter
        security = filters.get('security', 'Any')
        if security and security != 'Any':
            # Map our values to Spansh values
            security_map = {
                'High': 'High',
                'Medium': 'Medium', 
                'Low': 'Low',
                'Anarchy': 'Anarchy',
                'None': 'Anarchy'  # Unpopulated = Anarchy
            }
            if security in security_map:
                spansh_filters['security'] = {'value': security_map[security]}
        
        # Allegiance filter
        allegiance = filters.get('allegiance', 'Any')
        if allegiance and allegiance != 'Any':
            spansh_filters['allegiance'] = {'value': allegiance}
        
        # Government filter
        government = filters.get('government', 'Any')
        if government and government != 'Any':
            spansh_filters['government'] = {'value': government}
        
        # State filter - uses controlling_minor_faction_state
        state = filters.get('state', 'Any')
        if state and state != 'Any' and state != 'None' and state != '-':
            # Spansh expects array for state
            spansh_filters['controlling_minor_faction_state'] = {'value': [state]}
        
        # Economy filter - uses primary_economy
        economy = filters.get('economy', 'Any')
        if economy and economy != 'Any':
            spansh_filters['primary_economy'] = {'value': economy}
        
        # Population filter
        population = filters.get('population', 'Any')
        if population and population != 'Any':
            pop_filter = cls._build_population_filter(population)
            if pop_filter:
                spansh_filters['population'] = pop_filter

        # Powerplay — controlling power. Spansh's 'power' field lists ALL powers present/contesting
        # in the system, not just the controller, so filtering on it barely restricts results.
        # 'controlling_power' is the actual controller and is what we want to filter by.
        power = filters.get('power', 'Any')
        if power and power != 'Any':
            spansh_filters['controlling_power'] = {'value': [power]}

        # Powerplay — system state
        pp_state = filters.get('pp_state', 'Any')
        if pp_state and pp_state != 'Any':
            spansh_filters['power_state'] = {'value': [pp_state]}

        return spansh_filters
    
    @classmethod
    def _build_population_filter(cls, population: str) -> Optional[Dict]:
        """Convert population filter string to Spansh format"""
        # Inara-style population thresholds
        if population == 'None':
            return {'value': 0, 'comparison': '<='}
        elif population == 'Above 1':
            return {'value': 1, 'comparison': '>='}
        elif population == 'Above 10,000':
            return {'value': 10000, 'comparison': '>='}
        elif population == 'Above 100,000':
            return {'value': 100000, 'comparison': '>='}
        elif population == 'Above 1,000,000':
            return {'value': 1000000, 'comparison': '>='}
        elif population == 'Above 1,000,000,000':
            return {'value': 1000000000, 'comparison': '>='}
        elif population == 'Below 10,000':
            return {'value': 10000, 'comparison': '<'}
        elif population == 'Below 100,000':
            return {'value': 100000, 'comparison': '<'}
        elif population == 'Below 1,000,000':
            return {'value': 1000000, 'comparison': '<'}
        elif population == 'Below 1,000,000,000':
            return {'value': 1000000000, 'comparison': '<'}
        return None
    
    @classmethod
    def _convert_spansh_system(cls, system: Dict, pp_cache: Dict = None) -> Dict:
        """Convert Spansh system format to our display format"""
        # Get economy info
        primary_economy = system.get('primary_economy') or '-'
        secondary_economy = system.get('secondary_economy')
        
        # Get state - controlling faction state (show 'Normal' if no active state)
        state = system.get('controlling_minor_faction_state')
        if not state or state == 'None':
            state = 'Normal'
        
        # Get controlling faction name
        faction = system.get('controlling_minor_faction') or '-'
        
        # For unpopulated systems, show 'Independent' allegiance (matches Inara)
        allegiance = system.get('allegiance')
        if not allegiance or allegiance == 'None':
            allegiance = 'Independent'  # Unpopulated systems are in Independent space
        
        population = system.get('population', 0)
        
        system_name = system.get('name', '')

        # Powerplay — EDDN cache only; no Spansh fallback (Spansh PP data can be cycles stale)
        cached_pp = (pp_cache or {}).get(system_name)
        if cached_pp:
            pp_power = cached_pp['controlling_power']
            pp_state = cached_pp['power_state'] or None
            pp_updated_at = cached_pp.get('updated_at')
        else:
            pp_power = None
            pp_state = None
            pp_updated_at = None

        return {
            'systemName': system_name,
            'distance': system.get('distance', 0),
            'systemAddress': system.get('id64'),
            'coords': {
                'x': system.get('x', 0),
                'y': system.get('y', 0),
                'z': system.get('z', 0),
            },
            'security': system.get('security') or 'Anarchy',
            'allegiance': allegiance,
            'government': system.get('government') or '-',
            'state': state,
            'economy': {'primary': primary_economy, 'secondary': secondary_economy},
            'population': population,
            'faction': faction,
            'power': pp_power,
            'power_state': pp_state,
            'power_updated_at': pp_updated_at,
        }
    
    @classmethod
    def search_material_traders(cls, reference_system: str, trader_type: str,
                                max_results: int = None, progress_callback=None) -> List[Dict]:
        """
        Search for the nearest stations with a specific material trader using Spansh API.

        Args:
            reference_system: Name of the reference system
            trader_type: 'Encoded', 'Manufactured', or 'Raw'
            max_results: Maximum number of results (default 100)
            progress_callback: Optional callback(current, total, message) for progress

        Returns:
            List of stations sorted by distance, each with system/station info

        NOTE: If results come back empty, verify the Spansh filter field name for
        material_trader against https://spansh.co.uk/api/stations/search schema,
        as it may be 'has_encoded_materials_trader' / 'has_manufactured_materials_trader' /
        'has_raw_materials_trader' boolean flags instead of a single typed field.
        """
        if progress_callback:
            progress_callback(0, 100, f"Searching for {trader_type} material traders...")

        max_results = max_results or cls.MAX_RESULTS

        # Map our trader type labels to Spansh API values
        trader_type_map = {
            'Encoded':       'Encoded',
            'Manufactured':  'Manufactured',
            'Raw':           'Raw',
        }
        spansh_trader_type = trader_type_map.get(trader_type, trader_type)

        payload = {
            'reference_system': reference_system,
            'size': max_results,
            'sort': [{'distance': {'direction': 'asc'}}],
            'filters': {
                'material_trader': {'value': spansh_trader_type}
            }
        }

        log.info(f"[SYSTEM_FINDER] Searching {trader_type} material traders near {reference_system}")
        print(f"[SYSTEM_FINDER DEBUG] Material trader payload: {payload}")

        try:
            if progress_callback:
                progress_callback(20, 100, "Searching Spansh station database...")

            response = requests.post(cls.SPANSH_STATIONS_URL, json=payload, timeout=cls.TIMEOUT)
            response.raise_for_status()
            data = response.json()

            total_count = data.get('count', 0)
            results = data.get('results', [])

            log.info(f"[SYSTEM_FINDER] Spansh returned {len(results)} of {total_count} material trader stations")
            print(f"[SYSTEM_FINDER DEBUG] Material traders found: {total_count} total, {len(results)} returned")

            if progress_callback:
                progress_callback(80, 100, f"Processing {len(results)} results...")

            converted = [cls._convert_spansh_station(s, trader_type) for s in results]

            if progress_callback:
                progress_callback(100, 100, f"Found {len(converted)} {trader_type} material traders")

            return converted

        except requests.exceptions.RequestException as e:
            log.error(f"[SYSTEM_FINDER] Spansh stations API error: {e}")
            print(f"[SYSTEM_FINDER DEBUG] Material trader API error: {e}")
            return []
        except Exception as e:
            log.error(f"[SYSTEM_FINDER] Unexpected error in material trader search: {e}")
            print(f"[SYSTEM_FINDER DEBUG] Material trader unexpected error: {e}")
            return []

    @classmethod
    def _convert_spansh_station(cls, station: Dict, trader_type: str = '') -> Dict:
        """Convert Spansh station format to our display format for material traders"""
        # Derive max landing pad from pad counts
        if station.get('large_pads', 0) or station.get('has_large_pad'):
            pad_size = 'L'
        elif station.get('medium_pads', 0):
            pad_size = 'M'
        elif station.get('small_pads', 0):
            pad_size = 'S'
        else:
            pad_size = '-'

        return {
            'systemName':        station.get('system_name', ''),
            'distance':          station.get('distance', 0),
            'stationName':       station.get('name', ''),
            'stationType':       station.get('type') or '-',
            'landingPad':        pad_size,
            'distanceToArrival': station.get('distance_to_arrival'),
            'isPlanetary':       station.get('is_planetary', False),
            'traderType':        trader_type,
        }

    # Legacy method for backwards compatibility - now uses Spansh
    @classmethod
    def get_systems_with_status(cls, reference_system: str, max_range: int = 100,
                                 progress_callback=None) -> List[Dict]:
        """
        Legacy method - now uses Spansh without filters.
        Kept for backwards compatibility.
        """
        return cls.search_systems(reference_system, filters={}, 
                                  max_results=cls.MAX_RESULTS, 
                                  progress_callback=progress_callback)
    
    @classmethod
    def get_system_status(cls, system_name: str) -> Optional[Dict]:
        """
        Get detailed status for a single system using Spansh API.
        
        Args:
            system_name: Name of the system
            
        Returns:
            Dict with system status (security, allegiance, government, state, economy, population)
        """
        try:
            # Use Spansh search to find the system (it will be first result at 0 distance)
            payload = {
                'reference_system': system_name,
                'size': 1,
                'sort': [{'distance': {'direction': 'asc'}}]
            }
            
            response = requests.post(cls.SPANSH_URL, json=payload, timeout=cls.TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            results = data.get('results', [])
            if not results:
                log.warning(f"[SYSTEM_FINDER] No results for system: {system_name}")
                return None
            
            # First result should be the system itself (0 distance)
            system = results[0]
            
            # Verify it's the right system (name match)
            if system.get('name', '').lower() != system_name.lower():
                log.warning(f"[SYSTEM_FINDER] System name mismatch: {system.get('name')} != {system_name}")
                return None
            
            # Get state (show 'Normal' if no active state)
            state = system.get('controlling_minor_faction_state')
            if not state or state == 'None':
                state = 'Normal'
            
            # Get allegiance - default to Independent for unpopulated
            allegiance = system.get('allegiance')
            if not allegiance or allegiance == 'None':
                allegiance = 'Independent'
            
            # Get economy
            primary_economy = system.get('primary_economy') or '-'
            secondary_economy = system.get('secondary_economy')
            
            # Powerplay — EDDN cache only; no Spansh fallback (Spansh PP data can be cycles stale)
            cached_pp = cls._get_powerplay_from_cache(system_name)
            if cached_pp:
                power = cached_pp['controlling_power']
                power_state = cached_pp['power_state'] or None
                log.debug(f"[POWERPLAY] EDDN cache hit: power={power!r} state={power_state!r}")
            else:
                power = None
                power_state = None
                log.debug(f"[POWERPLAY] No EDDN cache entry for {system_name!r}")

            return {
                'security': system.get('security') or 'Anarchy',
                'allegiance': allegiance,
                'government': system.get('government') or '-',
                'state': state,
                'economy': {'primary': primary_economy, 'secondary': secondary_economy},
                'population': system.get('population', 0),
                'faction': system.get('controlling_minor_faction') or '-',
                'power': power,
                'power_state': power_state,
            }
            
        except requests.exceptions.RequestException as e:
            log.error(f"[SYSTEM_FINDER] Spansh API error for {system_name}: {e}")
            return None
        except Exception as e:
            log.error(f"[SYSTEM_FINDER] Error getting system status: {e}")
            return None
    
    @classmethod
    def filter_systems(cls, systems: List[Dict], filters: Dict[str, Any]) -> List[Dict]:
        """
        Legacy local filter method - no longer needed with Spansh server-side filtering.
        Kept for backwards compatibility but just returns systems unchanged.
        """
        # With Spansh, filtering is done server-side, so this is a no-op
        return systems


# Predefined filter options for UI dropdowns
SECURITY_OPTIONS = ['Any', 'High', 'Medium', 'Low', 'Anarchy']

ALLEGIANCE_OPTIONS = ['Any', 'Federation', 'Empire', 'Alliance', 'Independent', 'Pilots Federation']

GOVERNMENT_OPTIONS = [
    'Any', 'Anarchy', 'Communism', 'Confederacy', 'Cooperative', 
    'Corporate', 'Democracy', 'Dictatorship', 'Feudal', 
    'Patronage', 'Prison Colony', 'Theocracy'
]

STATE_OPTIONS = [
    'Any', 'Boom', 'Bust', 'Civil Liberty', 'Civil Unrest',
    'Civil War', 'Drought', 'Election', 'Expansion', 'Famine', 
    'Infrastructure Failure', 'Investment', 'Lockdown', 'Natural Disaster',
    'Outbreak', 'Pirate Attack', 'Public Holiday', 'Retreat', 
    'Terrorist Attack', 'War'
]

ECONOMY_OPTIONS = [
    'Any', 'Agriculture', 'Colony', 'Extraction', 'High Tech',
    'Industrial', 'Military', 'Prison', 'Refinery', 'Service',
    'Terraforming', 'Tourism'
]

# Inara-style population options
POPULATION_OPTIONS = [
    'Any', 'None', 'Above 1', 'Above 10,000', 'Above 100,000',
    'Above 1,000,000', 'Above 1,000,000,000',
    'Below 10,000', 'Below 100,000', 'Below 1,000,000', 'Below 1,000,000,000'
]

# Material trader types
MATERIAL_TRADER_OPTIONS = ['Encoded', 'Manufactured', 'Raw']

# Powerplay powers — used for "My Power" pledge dropdown
ELITE_POWERS = [
    "Select your pledge...", "Aisling Duval", "Archon Delaine",
    "Arissa Lavigny-Duval", "Denton Patreus", "Edmund Mahon",
    "Felicia Winters", "Li Yong-Rui", "Pranav Antal",
    "Yuri Grom", "Zemina Torval"
]

# Power filter options for system search (includes Any)
POWER_FILTER_OPTIONS = [
    'Any', 'Aisling Duval', 'Archon Delaine',
    'Arissa Lavigny-Duval', 'Denton Patreus', 'Edmund Mahon',
    'Felicia Winters', 'Li Yong-Rui', 'Pranav Antal',
    'Yuri Grom', 'Zemina Torval'
]

# Powerplay state filter options
PP_STATE_OPTIONS = [
    'Any', 'Exploited', 'Fortified', 'Stronghold',
    'Contested', 'Expansion'
]
