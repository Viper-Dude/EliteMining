"""
EDDN (Elite Dangerous Data Network) Listener
Real-time market data stream from community players

Connects to EDDN ZeroMQ stream and updates local commodity database
"""

import zmq
import zlib
import json
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional
import logging

log = logging.getLogger('EliteMining.EDDN')


class EDDNListener:
    """
    Listens to EDDN stream and updates local commodity price database
    """
    
    EDDN_RELAY = "tcp://eddn.edcd.io:9500"
    RECONNECT_DELAY = 30  # Seconds between reconnection attempts
    CLEANUP_INTERVAL = 3600  # Clean up old data every hour
    MAX_DATA_AGE_HOURS = 48  # Keep data for 2 days (48 hours)
    
    def __init__(self, database_path: str):
        """
        Initialize EDDN listener
        
        Args:
            database_path: Path to marketplace_cache.db
        """
        self.database_path = database_path
        self.running = False
        self.thread = None
        self.cleanup_thread = None
        self.messages_received = 0
        self.last_message_time = None
        self.last_cleanup_time = time.time()
        
    def start(self):
        """Start the EDDN listener in background thread"""
        if self.running:
            log.warning("EDDN listener already running")
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        log.info("EDDN listener started (with auto-cleanup every hour)")
        
    def stop(self):
        """Stop the EDDN listener"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        log.info("EDDN listener stopped")
    
    def _cleanup_loop(self):
        """Periodic cleanup of old data (runs in background thread)"""
        while self.running:
            try:
                # Wait for cleanup interval
                time.sleep(self.CLEANUP_INTERVAL)
                
                if not self.running:
                    break
                
                # Perform cleanup
                log.info("🧹 Running database cleanup (removing data older than 2 days)...")
                deleted_count = self._cleanup_old_data()
                log.info(f"🧹 Cleanup complete: Removed {deleted_count:,} old records")
                
            except Exception as e:
                log.error(f"Cleanup loop error: {e}")
    
    def _cleanup_old_data(self) -> int:
        """
        Remove data older than MAX_DATA_AGE_HOURS
        
        Returns:
            Number of records deleted
        """
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Delete old data from main table
                cursor.execute(f'''
                    DELETE FROM commodity_prices_data
                    WHERE datetime(updated_at, '+{self.MAX_DATA_AGE_HOURS} hours') < datetime('now')
                ''')
                deleted_data = cursor.rowcount
                
                # Delete corresponding FTS5 entries (match by system+station+commodity)
                cursor.execute(f'''
                    DELETE FROM commodity_prices_fts
                    WHERE rowid IN (
                        SELECT f.rowid FROM commodity_prices_fts f
                        LEFT JOIN commodity_prices_data d ON 
                            f.system_name = d.system_name AND 
                            f.station_name = d.station_name AND 
                            f.commodity_name = d.commodity_name
                        WHERE d.system_name IS NULL
                    )
                ''')
                deleted_fts = cursor.rowcount
                
                # Vacuum to reclaim space
                cursor.execute('VACUUM')
                
                conn.commit()
                
                return deleted_data + deleted_fts
                
        except Exception as e:
            log.error(f"Error cleaning up old data: {e}")
            return 0
        
    def _listen_loop(self):
        """Main listening loop (runs in background thread)"""
        context = zmq.Context()
        
        while self.running:
            try:
                # Create socket and connect
                log.info(f"Connecting to EDDN: {self.EDDN_RELAY}")
                subscriber = context.socket(zmq.SUB)
                subscriber.connect(self.EDDN_RELAY)
                subscriber.subscribe(b'')  # Subscribe to all messages
                subscriber.setsockopt(zmq.RCVTIMEO, 60000)  # 60 second timeout
                
                log.info("Connected to EDDN stream")
                
                # Listen for messages
                while self.running:
                    try:
                        # Receive compressed message
                        raw_message = subscriber.recv()
                        
                        # Decompress
                        message_json = zlib.decompress(raw_message).decode('utf-8')
                        message = json.loads(message_json)
                        
                        # Process message
                        self._process_message(message)
                        
                        # Update stats
                        self.messages_received += 1
                        self.last_message_time = datetime.now()
                        
                        # Log every 50 messages
                        if self.messages_received % 50 == 0:
                            log.info(f"📡 EDDN: Processed {self.messages_received} messages")
                        
                        # Log first few messages to show it's working
                        if self.messages_received <= 5:
                            log.info(f"📡 EDDN: Message #{self.messages_received} received")
                        
                    except zmq.Again:
                        # Timeout - check if we should continue
                        log.debug("EDDN: Receive timeout (no messages)")
                        continue
                        
                    except Exception as e:
                        log.error(f"EDDN: Error processing message: {e}")
                        continue
                
                subscriber.close()
                
            except Exception as e:
                log.error(f"EDDN: Connection error: {e}")
                if self.running:
                    log.info(f"EDDN: Reconnecting in {self.RECONNECT_DELAY} seconds...")
                    time.sleep(self.RECONNECT_DELAY)
        
        context.term()
        log.info("EDDN listener loop exited")
        
    def _process_message(self, message: dict):
        """
        Process incoming EDDN message and update database
        
        Args:
            message: Decoded EDDN message
        """
        try:
            schema_ref = message.get('$schemaRef', '')
            
            # We only care about commodity market data
            if 'commodity' not in schema_ref.lower():
                return
            
            # Extract message data
            msg_data = message.get('message', {})
            header = message.get('header', {})
            
            system_name = msg_data.get('systemName')
            station_name = msg_data.get('stationName')
            timestamp = msg_data.get('timestamp') or header.get('gatewayTimestamp')
            commodities = msg_data.get('commodities', [])
            
            if not system_name or not station_name or not commodities:
                return
            
            # Get station metadata
            market_id = msg_data.get('marketId', 0)
            station_type = msg_data.get('stationType', 'Unknown')
            
            # Update database
            self._update_commodity_prices(
                system_name=system_name,
                station_name=station_name,
                station_type=station_type,
                market_id=market_id,
                commodities=commodities,
                timestamp=timestamp
            )
            
        except Exception as e:
            log.error(f"EDDN: Error processing message: {e}")
            
    def _update_commodity_prices(self, system_name: str, station_name: str, 
                                 station_type: str, market_id: int,
                                 commodities: list, timestamp: str):
        """
        Update commodity prices in database
        
        Args:
            system_name: System name
            station_name: Station name
            station_type: Station type (e.g., "Coriolis")
            market_id: Market ID
            commodities: List of commodity data
            timestamp: ISO timestamp of data
        """
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Get system coordinates (if we have them cached)
                cursor.execute('''
                    SELECT x, y, z FROM system_coords WHERE name = ?
                ''', (system_name,))
                coords_row = cursor.fetchone()
                
                system_x = coords_row[0] if coords_row else None
                system_y = coords_row[1] if coords_row else None
                system_z = coords_row[2] if coords_row else None
                
                # Update each commodity
                for commodity in commodities:
                    commodity_name = commodity.get('name')
                    sell_price = commodity.get('sellPrice', 0)
                    buy_price = commodity.get('buyPrice', 0)
                    demand = commodity.get('demand', 0)
                    stock = commodity.get('stock', 0)
                    
                    if not commodity_name:
                        continue
                    
                    # Insert/update in data table
                    cursor.execute('''
                        INSERT OR REPLACE INTO commodity_prices_data
                        (system_name, system_x, system_y, system_z, station_name, station_type,
                         commodity_name, sell_price, buy_price, demand, stock, distance_to_arrival,
                         market_id, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (system_name, system_x, system_y, system_z, station_name, station_type,
                          commodity_name, sell_price, buy_price, demand, stock, 0,
                          market_id, timestamp))
                    
                    # Delete old FTS5 entry if exists
                    cursor.execute('''
                        DELETE FROM commodity_prices_fts 
                        WHERE system_name = ? AND station_name = ? AND commodity_name = ?
                    ''', (system_name, station_name, commodity_name))
                    
                    # Insert into FTS5
                    cursor.execute('''
                        INSERT INTO commodity_prices_fts
                        (system_name, station_name, station_type, commodity_name, sell_price,
                         buy_price, demand, stock, distance_to_arrival, market_id, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (system_name, station_name, station_type, commodity_name, sell_price,
                          buy_price, demand, stock, 0, market_id, timestamp))
                
                conn.commit()
                
        except Exception as e:
            log.error(f"EDDN: Database update error: {e}")
    
    def get_stats(self) -> dict:
        """Get listener statistics"""
        return {
            'running': self.running,
            'messages_received': self.messages_received,
            'last_message_time': self.last_message_time
        }
    
    def get_database_stats(self) -> dict:
        """Get database population statistics"""
        try:
            with sqlite3.connect(self.database_path) as conn:
                cursor = conn.cursor()
                
                # Count total commodity records
                cursor.execute('SELECT COUNT(*) FROM commodity_prices_data')
                total_records = cursor.fetchone()[0]
                
                # Count unique systems
                cursor.execute('SELECT COUNT(DISTINCT system_name) FROM commodity_prices_data')
                unique_systems = cursor.fetchone()[0]
                
                # Count unique stations
                cursor.execute('SELECT COUNT(DISTINCT station_name) FROM commodity_prices_data')
                unique_stations = cursor.fetchone()[0]
                
                # Get most recent update
                cursor.execute('SELECT MAX(updated_at) FROM commodity_prices_data')
                last_update = cursor.fetchone()[0]
                
                return {
                    'total_records': total_records,
                    'unique_systems': unique_systems,
                    'unique_stations': unique_stations,
                    'last_update': last_update
                }
        except Exception as e:
            log.error(f"Error getting database stats: {e}")
            return {
                'total_records': 0,
                'unique_systems': 0,
                'unique_stations': 0,
                'last_update': None
            }


# Example usage
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    # Start listener
    listener = EDDNListener("app/data/marketplace_cache.db")
    listener.start()
    
    try:
        # Run for a while
        print("EDDN listener running. Press Ctrl+C to stop...")
        while True:
            time.sleep(10)
            stats = listener.get_stats()
            print(f"Stats: {stats['messages_received']} messages, "
                  f"Last: {stats['last_message_time']}")
    except KeyboardInterrupt:
        print("\nStopping...")
        listener.stop()
