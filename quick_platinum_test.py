#!/usr/bin/env python3
"""
Quick Platinum Test - Limited API calls
"""

import requests
import math
from datetime import datetime

def quick_platinum_test():
    """Quick test with just a few systems"""
    print("=== Quick Platinum Price Test ===")
    
    # Just test a few known systems
    test_systems = ["Sol", "Deciat", "Shinrarta Dezhra"]
    
    for system in test_systems:
        print(f"\n🔍 Testing {system}...")
        
        # Get stations
        try:
            response = requests.get(
                "https://www.edsm.net/api-system-v1/stations",
                params={"systemName": system, "showMarket": 1},
                timeout=5
            )
            
            if response.status_code == 200:
                stations = response.json().get('stations', [])
                print(f"   Found {len(stations)} stations")
                
                # Test just first station with market
                for station in stations[:2]:  # Only first 2 stations
                    if station.get('marketId'):
                        print(f"   Testing: {station['name']}")
                        
                        # Get market data
                        market_response = requests.get(
                            "https://www.edsm.net/api-system-v1/stations/market",
                            params={"marketId": station['marketId']},
                            timeout=5
                        )
                        
                        if market_response.status_code == 200:
                            market_data = market_response.json()
                            commodities = market_data.get('commodities', [])
                            
                            # Look for platinum
                            platinum_found = False
                            for commodity in commodities:
                                if 'platinum' in commodity.get('name', '').lower():
                                    sell_price = commodity.get('sellPrice', 0)
                                    demand = commodity.get('demand', 0)
                                    
                                    if sell_price > 0:
                                        print(f"      💎 Platinum: {sell_price:,} CR/t (Demand: {demand:,}t)")
                                        platinum_found = True
                            
                            if not platinum_found:
                                print(f"      ❌ No platinum buying at {station['name']}")
                        break  # Only test one station per system
            else:
                print(f"   ❌ API Error: {response.status_code}")
                
        except requests.Timeout:
            print(f"   ⏰ Timeout for {system}")
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    quick_platinum_test()