"""
System Finder API - Spansh API integration for system searches
Provides nearby system lookup with full server-side filtering (security, allegiance, state, etc.)
"""
import requests
import logging
from typing import List, Dict, Optional, Any

log = logging.getLogger(__name__)


class SystemFinderAPI:
    """Spansh API integration for system finder functionality with server-side filtering"""
    
    # Spansh API URL
    SPANSH_URL = "https://spansh.co.uk/api/systems/search"
    
    # Request timeout
    TIMEOUT = 30
    
    # Maximum results to return
    MAX_RESULTS = 100
    
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
            
            # Convert Spansh format to our format
            converted = []
            for system in results:
                converted.append(cls._convert_spansh_system(system))
            
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
    def _convert_spansh_system(cls, system: Dict) -> Dict:
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
        
        return {
            'systemName': system.get('name', ''),
            'distance': system.get('distance', 0),
            'systemAddress': system.get('id64'),
            'coords': {
                'x': system.get('x', 0),
                'y': system.get('y', 0),
                'z': system.get('z', 0),
            },
            'security': system.get('security') or 'Anarchy',  # Unpopulated = Anarchy
            'allegiance': allegiance,
            'government': system.get('government') or '-',
            'state': state,
            'economy': {'primary': primary_economy, 'secondary': secondary_economy},
            'population': population,
            'faction': faction,
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
            
            return {
                'security': system.get('security') or 'Anarchy',
                'allegiance': allegiance,
                'government': system.get('government') or '-',
                'state': state,
                'economy': {'primary': primary_economy, 'secondary': secondary_economy},
                'population': system.get('population', 0),
                'faction': system.get('controlling_minor_faction') or '-',
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
