"""
Market.json Handler for EDDN sending
Reads Market.json from Elite Dangerous and sends commodity data to EDDN
"""

import json
import os
import logging
from typing import Dict, List, Optional

log = logging.getLogger('EliteMining.MarketHandler')


class MarketHandler:
    """Handles Market.json file and sends data to EDDN"""
    
    def __init__(self, eddn_sender):
        """
        Initialize market handler
        
        Args:
            eddn_sender: EDDNSender instance
        """
        self.eddn_sender = eddn_sender
        self.last_market_id = None
        self.current_system = None
        self.current_station = None
    
    def process_journal_event(self, event: Dict):
        """
        Process journal events to update game state
        
        Args:
            event: Journal event dictionary
        """
        event_type = event.get('event')
        
        # Update game info from LoadGame
        if event_type == 'LoadGame':
            self.eddn_sender.update_game_info(event)
        
        # Track current location
        elif event_type in ['Location', 'FSDJump', 'CarrierJump']:
            self.current_system = event.get('StarSystem')
            self.current_station = None  # Clear station on jump
        
        # Track docking
        elif event_type == 'Docked':
            self.current_station = event.get('StationName')
            self.current_system = event.get('StarSystem')
        
    def process_market_file(self, market_file_path: str):
        """
        Process Market.json file and send to EDDN
        
        Args:
            market_file_path: Path to Market.json
        """
        try:
            # Read Market.json
            with open(market_file_path, 'r', encoding='utf-8') as f:
                market_data = json.load(f)
            
            # Extract required fields
            market_id = market_data.get('MarketID')
            station_name = market_data.get('StationName')
            system_name = market_data.get('StarSystem')
            commodities = market_data.get('Items', [])
            
            if not all([market_id, station_name, system_name]):
                log.warning("Market.json missing required fields")
                return
            
            # Skip if same market (avoid duplicate sends)
            if market_id == self.last_market_id:
                return
            
            self.last_market_id = market_id
            
            # Convert Elite's format to EDDN format
            eddn_commodities = self._convert_commodities(commodities)
            
            # Get station metadata
            station_data = {
                'type': market_data.get('StationType'),
                'distanceToArrival': market_data.get('DistanceToArrival')
            }
            
            # Send to EDDN
            if self.eddn_sender.enabled:
                success = self.eddn_sender.send_commodity_data(
                    system_name=system_name,
                    station_name=station_name,
                    market_id=market_id,
                    commodities=eddn_commodities,
                    station_data=station_data
                )
                
                if success:
                    log.info(f"✅ Sent market data for {station_name} ({len(eddn_commodities)} commodities)")
                else:
                    log.warning(f"❌ Failed to send market data for {station_name}")
            
        except FileNotFoundError:
            # Market.json doesn't exist yet (player hasn't docked)
            pass
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse Market.json: {e}")
        except Exception as e:
            log.error(f"Error processing Market.json: {e}")
    
    def _convert_commodities(self, elite_commodities: List[Dict]) -> List[Dict]:
        """
        Convert Elite Dangerous commodity format to EDDN format (EDDN compliant)
        
        Args:
            elite_commodities: List of commodities from Market.json
            
        Returns:
            List of commodities in EDDN format
        """
        eddn_format = []
        
        for item in elite_commodities:
            # Skip NonMarketable items (e.g., Limpets)
            category = item.get('Category', '')
            if 'NonMarketable' in category:
                continue
            
            # Skip items with legality string (not normally traded)
            if item.get('Legality', ''):
                continue
            
            # Clean commodity name: remove $ prefix and _name; suffix
            name = item.get('Name', '')
            if name.startswith('$'):
                name = name[1:]  # Remove $
            if name.endswith('_name;'):
                name = name[:-6]  # Remove _name;
            
            if not name:
                continue
            
            # Build commodity in EDDN format (excluding forbidden fields)
            commodity = {
                'name': name,
                'buyPrice': item.get('BuyPrice', 0),
                'sellPrice': item.get('SellPrice', 0),
                'demand': item.get('Demand', 0),
                'stock': item.get('Stock', 0),
                'demandBracket': item.get('DemandBracket', 0),
                'stockBracket': item.get('StockBracket', 0)
            }
            
            # Add optional meanPrice if present
            if 'MeanPrice' in item:
                commodity['meanPrice'] = item['MeanPrice']
            
            # Add optional statusFlags if present
            if 'StatusFlags' in item:
                commodity['statusFlags'] = item['StatusFlags']
            
            # Only include commodities with actual price data
            if commodity['buyPrice'] > 0 or commodity['sellPrice'] > 0:
                eddn_format.append(commodity)
        
        return eddn_format
