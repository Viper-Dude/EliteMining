#!/usr/bin/env python3
"""
Commodity Marketplace Finder for EliteMining
Finds best selling prices for commodities using EDSM API
"""

import requests
import json
import math
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from threading import Thread
import sqlite3
import os

log = logging.getLogger("EliteMining.MarketplaceFinder")

class MarketplaceFinder:
    """
    Finds commodity selling stations with price comparison
    Uses EDSM API for live market data
    """
    
    def __init__(self, database_path: str = None):
        self.database_path = database_path or "marketplace_cache.db"
        self.api_timeout = 10
        self.api_delay = 1.0  # 1 second delay to avoid EDSM rate limiting (429 errors)
        self._init_database()
        
        # Cache for system coordinates to avoid repeated API calls
        self.system_coords_cache = {}
        self.market_data_cache = {}  # Cache market data for session
        
        # Known mining commodities
        self.mining_commodities = [
            'Platinum', 'Palladium', 'Gold', 'Silver', 'Painite',
            'Bertrandite', 'Indite', 'Gallite', 'Coltan', 'Uraninite',
            'Bromellite', 'Rutile', 'Pyroxeres', 'Alexandrite',
            'Benitoite', 'Grandidierite', 'Monazite', 'Musgravite',
            'Serendibite', 'Taaffeite', 'Jadeite', 'Opal', 'Bauxite',
            'Lepidolite', 'Lithium Hydroxide', 'Methanol Monohydrate',
            'Liquid Oxygen', 'Tritium'
        ]
    
    def _init_database(self):
        """Initialize SQLite cache database"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # System coordinates cache
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_coords (
                        name TEXT PRIMARY KEY,
                        x REAL,
                        y REAL, 
                        z REAL,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Market data cache
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS market_cache (
                        market_id INTEGER,
                        commodity_name TEXT,
                        system_name TEXT,
                        station_name TEXT,
                        station_type TEXT,
                        buy_price INTEGER,
                        sell_price INTEGER,
                        stock INTEGER,
                        demand INTEGER,
                        distance_to_arrival INTEGER,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (market_id, commodity_name)
                    )
                ''')
                
                # Stations cache (cache station lists per system for 6 hours)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS stations_cache (
                        system_name TEXT PRIMARY KEY,
                        stations_json TEXT,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # FTS5 full-text search table for fast commodity searches
                cursor.execute('''
                    CREATE VIRTUAL TABLE IF NOT EXISTS commodity_prices_fts USING fts5(
                        system_name,
                        station_name,
                        station_type,
                        commodity_name,
                        sell_price UNINDEXED,
                        buy_price UNINDEXED,
                        demand UNINDEXED,
                        stock UNINDEXED,
                        distance_to_arrival UNINDEXED,
                        market_id UNINDEXED,
                        updated_at UNINDEXED,
                        tokenize = 'porter ascii'
                    )
                ''')
                
                # Regular table for additional data (coordinates, etc)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS commodity_prices_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        system_name TEXT,
                        system_x REAL,
                        system_y REAL,
                        system_z REAL,
                        station_name TEXT,
                        station_type TEXT,
                        commodity_name TEXT,
                        sell_price INTEGER,
                        buy_price INTEGER,
                        demand INTEGER,
                        stock INTEGER,
                        distance_to_arrival INTEGER,
                        market_id INTEGER,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(system_name, station_name, commodity_name)
                    )
                ''')
                
                # Index for fast lookups
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_commodity_system 
                    ON commodity_prices_data(commodity_name, system_name)
                ''')
                
                conn.commit()
        except Exception as e:
            log.error(f"Database initialization failed: {e}")
    
    def get_system_coordinates(self, system_name: str) -> Optional[Dict]:
        """Get system coordinates with caching"""
        # Check cache first
        if system_name in self.system_coords_cache:
            return self.system_coords_cache[system_name]
        
        # Check database cache
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT x, y, z FROM system_coords WHERE name = ? AND updated_at > ?',
                    (system_name, datetime.now() - timedelta(days=7))  # Cache for 7 days
                )
                row = cursor.fetchone()
                if row:
                    coords = {'x': row[0], 'y': row[1], 'z': row[2]}
                    self.system_coords_cache[system_name] = coords
                    return coords
        except Exception as e:
            log.error(f"Database read error: {e}")
        
        # Fetch from API
        url = "https://www.edsm.net/api-v1/system"
        params = {
            "systemName": system_name,
            "showCoordinates": 1
        }
        
        try:
            time.sleep(self.api_delay)  # Rate limiting
            response = requests.get(url, params=params, timeout=self.api_timeout)
            
            if response.status_code == 200:
                data = response.json()
                if 'coords' in data:
                    coords = data['coords']
                    
                    # Cache in memory and database
                    self.system_coords_cache[system_name] = coords
                    
                    try:
                        with sqlite3.connect(self.database_path) as conn:
                            cursor = conn.cursor()
                            cursor.execute(
                                'INSERT OR REPLACE INTO system_coords (name, x, y, z) VALUES (?, ?, ?, ?)',
                                (system_name, coords['x'], coords['y'], coords['z'])
                            )
                            conn.commit()
                    except Exception as e:
                        log.error(f"Database write error: {e}")
                    
                    return coords
                    
        except Exception as e:
            log.error(f"Error getting coordinates for {system_name}: {e}")
        
        return None
    
    def calculate_distance(self, coords1: Dict, coords2: Dict) -> float:
        """Calculate distance between two coordinate points"""
        if not coords1 or not coords2:
            return float('inf')
        
        dx = coords1['x'] - coords2['x']
        dy = coords1['y'] - coords2['y']
        dz = coords1['z'] - coords2['z']
        
        return math.sqrt(dx*dx + dy*dy + dz*dz)
    
    def get_system_stations(self, system_name: str) -> List[Dict]:
        """Get all stations in a system with market data (cached for 6 hours)"""
        # Check cache first (6 hour expiry)
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT stations_json, updated_at FROM stations_cache 
                    WHERE system_name = ? 
                    AND datetime(updated_at, '+6 hours') > datetime('now')
                ''', (system_name,))
                row = cursor.fetchone()
                
                if row:
                    stations = json.loads(row[0])
                    return stations
        except Exception as e:
            log.error(f"Cache read error for {system_name}: {e}")
        
        # Not in cache or expired - fetch from EDSM
        url = "https://www.edsm.net/api-system-v1/stations"
        params = {
            "systemName": system_name,
            "showMarket": 1,
            "showShipyard": 1,
            "showOutfitting": 1,
            "showFleetCarriers": 1,
            "showInformation": 1  # This includes updateTime data
        }
        
        try:
            time.sleep(self.api_delay)  # Rate limiting
            response = requests.get(url, params=params, timeout=self.api_timeout)
            
            if response.status_code == 429:
                # Rate limited - wait longer and retry once
                print(f"DEBUG: Rate limited for {system_name}, waiting 5 seconds...")
                time.sleep(5)
                response = requests.get(url, params=params, timeout=self.api_timeout)
            
            if response.status_code == 200:
                data = response.json()
                stations = data.get('stations', [])
                
                # Cache the result
                try:
                    with sqlite3.connect(self.database_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO stations_cache (system_name, stations_json, updated_at)
                            VALUES (?, ?, datetime('now'))
                        ''', (system_name, json.dumps(stations)))
                        conn.commit()
                except Exception as e:
                    log.error(f"Cache write error for {system_name}: {e}")
                
                return stations
                
        except Exception as e:
            log.error(f"Error getting stations for {system_name}: {e}")
        
        return []
    
    def cache_commodity_prices(self, system_name: str, system_coords: Dict, station_data: Dict, commodities: List[Dict]):
        """Cache commodity prices in FTS5 for fast searching"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                station_name = station_data.get('name', '')
                station_type = station_data.get('type', '')
                market_id = station_data.get('marketId', 0)
                distance_to_arrival = station_data.get('distanceToArrival', 0)
                
                for commodity in commodities:
                    commodity_name = commodity.get('name', '')
                    sell_price = commodity.get('sellPrice', 0)
                    buy_price = commodity.get('buyPrice', 0)
                    demand = commodity.get('demand', 0)
                    stock = commodity.get('stock', 0)
                    
                    if not commodity_name:
                        continue
                    
                    # Insert into data table
                    cursor.execute('''
                        INSERT OR REPLACE INTO commodity_prices_data 
                        (system_name, system_x, system_y, system_z, station_name, station_type,
                         commodity_name, sell_price, buy_price, demand, stock, distance_to_arrival,
                         market_id, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ''', (system_name, system_coords.get('x'), system_coords.get('y'), system_coords.get('z'),
                          station_name, station_type, commodity_name, sell_price, buy_price,
                          demand, stock, distance_to_arrival, market_id))
                    
                    # Insert into FTS5 for search
                    cursor.execute('''
                        INSERT INTO commodity_prices_fts 
                        (system_name, station_name, station_type, commodity_name, sell_price,
                         buy_price, demand, stock, distance_to_arrival, market_id, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    ''', (system_name, station_name, station_type, commodity_name, sell_price,
                          buy_price, demand, stock, distance_to_arrival, market_id))
                
                conn.commit()
        except Exception as e:
            log.error(f"Error caching commodity prices: {e}")
    
    def get_station_market_data(self, market_id: int) -> Optional[Dict]:
        """Get market data for a specific station with session caching"""
        # Check session cache first
        if market_id in self.market_data_cache:
            return self.market_data_cache[market_id]
            
        url = "https://www.edsm.net/api-system-v1/stations/market"
        params = {
            "marketId": market_id
        }
        
        try:
            time.sleep(self.api_delay)  # Rate limiting
            response = requests.get(url, params=params, timeout=self.api_timeout)
            
            if response.status_code == 200:
                data = response.json()
                # Cache for this session
                self.market_data_cache[market_id] = data
                return data
                
        except Exception as e:
            log.error(f"Error getting market data for {market_id}: {e}")
        
        return None
    
    def search_cached_commodity_prices(self, commodity_name: str, center_system: str, 
                                       max_distance: float, max_results: int = 50) -> List[Dict]:
        """
        Fast search using FTS5 cached data (instant, no API calls)
        
        Args:
            commodity_name: Name of commodity to search for
            center_system: System to calculate distances from  
            max_distance: Maximum distance in LY
            max_results: Maximum results to return
            
        Returns:
            List of cached commodity prices sorted by distance
        """
        try:
            # Get center system coordinates
            center_coords = self.get_system_coordinates(center_system)
            if not center_coords:
                return []
            
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Search FTS5 for commodity
                cursor.execute('''
                    SELECT d.system_name, d.system_x, d.system_y, d.system_z,
                           d.station_name, d.station_type, d.sell_price, d.buy_price,
                           d.demand, d.stock, d.distance_to_arrival, d.market_id,
                           d.updated_at
                    FROM commodity_prices_fts f
                    JOIN commodity_prices_data d ON 
                        f.system_name = d.system_name AND 
                        f.station_name = d.station_name AND
                        f.commodity_name = d.commodity_name
                    WHERE f.commodity_name MATCH ?
                    AND d.sell_price > 0
                    AND datetime(d.updated_at, '+48 hours') > datetime('now')
                ''', (commodity_name,))
                
                results = []
                for row in cursor.fetchall():
                    system_coords = {'x': row[1], 'y': row[2], 'z': row[3]}
                    distance = self.calculate_distance(center_coords, system_coords)
                    
                    if distance <= max_distance:
                        results.append({
                            'system_name': row[0],
                            'system_distance': distance,
                            'station_name': row[4],
                            'station_type': row[5],
                            'commodity_name': commodity_name,
                            'sell_price': row[6],
                            'buy_price': row[7],
                            'demand': row[8],
                            'stock': row[9],
                            'arrival_distance': row[10],
                            'market_id': row[11]
                        })
                
                # Sort by distance
                results.sort(key=lambda x: x['system_distance'])
                return results[:max_results]
                
        except Exception as e:
            log.error(f"FTS5 search error: {e}")
            return []
    
    def find_commodity_prices(self, commodity_name: str, center_system: str, 
                            search_systems: List[str] = None, max_results: int = 50) -> List[Dict]:
        """
        Find commodity selling prices sorted by distance from center system
        
        Args:
            commodity_name: Name of commodity to search for (e.g., "Platinum")
            center_system: System to calculate distances from
            search_systems: List of systems to search (if None, uses common systems)
            max_results: Maximum number of results to return
            
        Returns:
            List of dictionaries with station/price data sorted by distance
        """
        log.info(f"Searching for {commodity_name} prices near {center_system}")
        
        # Get center system coordinates
        center_coords = self.get_system_coordinates(center_system)
        if not center_coords:
            log.error(f"Could not find coordinates for {center_system}")
            return []
        
        # Use provided systems or get all systems within radius
        if search_systems is None:
            # Get all systems within max distance instead of hardcoded list
            search_systems = self._get_systems_within_radius(center_system, max_distance=100)
            if not search_systems:
                # Fallback to known systems if radius search fails
                search_systems = [
                    center_system, "Sol", "Shinrarta Dezhra", "Deciat", "Borann",
                    "LHS 2936", "Fuelum", "Diaguandri", "LHS 3447", "Eravate",
                    "Jameson Memorial", "i Bootis", "LHS 20", "Wolf 397"
                ]
        
        commodity_offers = []
        
        for system_name in search_systems:
            try:
                # Get system coordinates and distance
                system_coords = self.get_system_coordinates(system_name)
                if not system_coords:
                    continue
                
                distance = self.calculate_distance(center_coords, system_coords)
                
                # Get stations in system
                stations = self.get_system_stations(system_name)
                
                for station in stations:
                    if not station.get('haveMarket') or not station.get('marketId'):
                        continue
                    
                    # Get market data
                    market_data = self.get_station_market_data(station['marketId'])
                    if not market_data or 'commodities' not in market_data:
                        continue
                    
                    # Look for the commodity
                    for commodity in market_data['commodities']:
                        comm_name = commodity.get('name', '')
                        if commodity_name.lower() in comm_name.lower():
                            sell_price = commodity.get('sellPrice', 0)
                            
                            if sell_price > 0:  # Station is buying this commodity
                                offer = {
                                    'system_name': system_name,
                                    'system_distance': distance,
                                    'station_name': station.get('name'),
                                    'station_type': station.get('type'),
                                    'arrival_distance': station.get('distanceToArrival', 0),
                                    'commodity_name': comm_name,
                                    'buy_price': commodity.get('buyPrice', 0),
                                    'sell_price': sell_price,
                                    'stock': commodity.get('stock', 0),
                                    'demand': commodity.get('demand', 0),
                                    'market_id': station['marketId']
                                }
                                
                                commodity_offers.append(offer)
                                
                                if len(commodity_offers) >= max_results * 2:  # Get extra to sort
                                    break
                    
                    if len(commodity_offers) >= max_results * 2:
                        break
                        
            except Exception as e:
                log.error(f"Error processing system {system_name}: {e}")
                continue
        
        # Sort by distance and return top results
        commodity_offers.sort(key=lambda x: x['system_distance'])
        
        log.info(f"Found {len(commodity_offers)} {commodity_name} offers")
        return commodity_offers[:max_results]
    
    def _get_systems_within_radius(self, center_system: str, max_distance: int = 100) -> List[str]:
        """
        Get all systems within radius using EDSM sphere-systems API
        
        Args:
            center_system: System name to search around
            max_distance: Maximum distance in light years
            
        Returns:
            List of system names within radius
        """
        # EDSM API can't handle large radius - cap at 50 LY max
        # Systems beyond 50 LY will be filtered later by distance check
        api_radius = min(max_distance, 50)
        
        url = "https://www.edsm.net/api-v1/sphere-systems"
        params = {
            "systemName": center_system,
            "radius": api_radius,
            "showInformation": 1
        }
        
        timeout = 30
        
        try:
            time.sleep(self.api_delay)  # Rate limiting
            response = requests.get(url, params=params, timeout=timeout)
            
            print(f"DEBUG EDSM: Status {response.status_code}, URL: {response.url}")
            
            if response.status_code == 200:
                systems_data = response.json()
                print(f"DEBUG EDSM: Got response with {len(systems_data) if isinstance(systems_data, list) else 'unknown'} items")
                
                # Extract system names and sort by distance
                systems_with_distance = []
                for system in systems_data:
                    system_name = system.get('name')
                    distance = system.get('distance', 999999)
                    if system_name:
                        systems_with_distance.append((system_name, distance))
                
                # Sort by distance (closest first)
                systems_with_distance.sort(key=lambda x: x[1])
                systems = [name for name, dist in systems_with_distance]
                
                log.info(f"Found {len(systems)} systems within {max_distance} LY of {center_system}")
                return systems
            else:
                log.error(f"EDSM sphere-systems API error: {response.status_code}")
                print(f"DEBUG EDSM: Error response: {response.text[:200]}")
                
        except Exception as e:
            log.error(f"Error getting systems within radius: {e}")
            print(f"DEBUG EDSM: Exception: {e}")
        
        return []
    
    def get_mining_commodities(self) -> List[str]:
        """Get list of known mining commodities"""
        return self.mining_commodities.copy()
    
    def clear_cache(self):
        """Clear cached data (for testing/refresh)"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM system_coords')
                cursor.execute('DELETE FROM market_cache')
                conn.commit()
            
            self.system_coords_cache.clear()
            log.info("Cache cleared")
            
        except Exception as e:
            log.error(f"Error clearing cache: {e}")

# Example usage and testing
if __name__ == "__main__":
    # Simple test
    marketplace = MarketplaceFinder()
    
    print("Testing MarketplaceFinder...")
    results = marketplace.find_commodity_prices("Platinum", "Sol", max_results=10)
    
    print(f"\nFound {len(results)} Platinum offers:")
    for result in results:
        print(f"{result['system_name']}: {result['station_name']} - {result['sell_price']:,} CR/t "
              f"({result['system_distance']:.1f} LY)")