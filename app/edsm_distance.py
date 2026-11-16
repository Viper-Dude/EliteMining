"""Coordinate lookup and distance calculation for the Distance Calculator."""
import logging
import math
import threading
import time
from typing import Dict, Optional

import requests
from version import __version__

logger = logging.getLogger(__name__)


class EDSMDistanceCalculator:
    def __init__(self):
        self.api_base_url = 'https://www.edsm.net/api-v1/system'
        self.timeout = 15
        self.cache = {}
        self.cache_expiry = 300
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self.headers = {'User-Agent': f'EliteMining/{__version__} (+https://github.com/Viper-Dude/EliteMining)'}
        self._lookup_lock = threading.Lock()

    def _rate_limit(self):
        elapsed = time.monotonic() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.monotonic()

    def get_system_coordinates(self, system_name: str) -> Optional[Dict]:
        if not system_name or not system_name.strip():
            return None
        system_name = system_name.strip()
        key = system_name.casefold()
        # Concurrent calculations share the lookup and its cache entry.
        with self._lookup_lock:
            cached = self.cache.get(key)
            if cached and time.monotonic() - cached['timestamp'] < self.cache_expiry:
                return cached['data']
            for attempt in range(3):
                if attempt:
                    time.sleep(attempt * 2)
                try:
                    self._rate_limit()
                    response = requests.get(self.api_base_url,
                                            params={'systemName': system_name, 'showCoordinates': 1},
                                            timeout=self.timeout, headers=self.headers)
                    response.raise_for_status()
                    if not response.text.strip():
                        raise ValueError('Empty response from EDSM')
                    data = response.json()
                    if not data:
                        return None
                    if not isinstance(data, dict):
                        raise ValueError('Invalid system response from EDSM')
                    if not data.get('coords'):
                        return None
                    result = {'name': data.get('name', system_name),
                              **{axis: float(data['coords'][axis]) for axis in ('x', 'y', 'z')}}
                    self.cache[key] = {'data': result, 'timestamp': time.monotonic()}
                    return result
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    response = getattr(exc, 'response', None)
                    if response is not None and 400 <= response.status_code < 500:
                        raise
                    if attempt == 2:
                        logger.warning('Coordinate lookup failed for %s: %s', system_name, exc)
                        raise
        return None

    def calculate_distance(self, system1: Dict, system2: Dict) -> Optional[float]:
        if not system1 or not system2:
            return None
        try:
            return math.dist([system1[axis] for axis in ('x', 'y', 'z')],
                             [system2[axis] for axis in ('x', 'y', 'z')])
        except (KeyError, TypeError, ValueError):
            return None


_calculator = None


def get_distance_calculator() -> EDSMDistanceCalculator:
    global _calculator
    if _calculator is None:
        _calculator = EDSMDistanceCalculator()
    return _calculator
