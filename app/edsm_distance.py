"""Coordinate lookup and distance calculation for the Distance Calculator."""
import logging
import math
import threading
import time
from typing import Dict, Optional

import requests
from version import __version__

logger = logging.getLogger(__name__)

SOL_COORDS = {'x': 0.0, 'y': 0.0, 'z': 0.0}


class EDSMDistanceCalculator:
    def __init__(self):
        self.api_base_url = 'https://www.edsm.net/api-v1/system'
        self.timeout = 15
        # Found coordinates never change, so they stay for the session; misses are re-checked later.
        self.cache = {}
        self.miss_expiry = 600
        self.last_request_time = 0
        self.min_request_interval = 0.5
        self.headers = {'User-Agent': f'EliteMining/{__version__} (+https://github.com/Viper-Dude/EliteMining)'}
        self._rate_lock = threading.Lock()
        self._locks_guard = threading.Lock()
        self._lookup_locks = {}

    def _rate_limit(self):
        with self._rate_lock:
            elapsed = time.monotonic() - self.last_request_time
            if elapsed < self.min_request_interval:
                time.sleep(self.min_request_interval - elapsed)
            self.last_request_time = time.monotonic()

    def _lookup_lock(self, key):
        with self._locks_guard:
            return self._lookup_locks.setdefault(key, threading.Lock())

    def _cached(self, key):
        cached = self.cache.get(key)
        if cached is None:
            return False, None
        if cached['data'] is None and time.monotonic() - cached['timestamp'] >= self.miss_expiry:
            return False, None
        return True, cached['data']

    def _store(self, key, data):
        self.cache[key] = {'data': data, 'timestamp': time.monotonic()}
        return data

    def get_system_coordinates(self, system_name: str) -> Optional[Dict]:
        if not system_name or not system_name.strip():
            return None
        system_name = system_name.strip()
        key = system_name.casefold()
        # Concurrent lookups of the same system share one request; other systems don't wait.
        with self._lookup_lock(key):
            hit, data = self._cached(key)
            if hit:
                return data
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
                        return self._store(key, None)
                    if not isinstance(data, dict):
                        raise ValueError('Invalid system response from EDSM')
                    if not data.get('coords'):
                        return self._store(key, None)
                    result = {'name': data.get('name', system_name),
                              **{axis: float(data['coords'][axis]) for axis in ('x', 'y', 'z')}}
                    return self._store(key, result)
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    response = getattr(exc, 'response', None)
                    if response is not None and 400 <= response.status_code < 500:
                        raise
                    # A timed-out server rarely answers a retry; waiting 3 x 15 s only stalls the tab.
                    if attempt == 2 or isinstance(exc, requests.Timeout):
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
