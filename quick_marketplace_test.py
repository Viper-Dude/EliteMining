#!/usr/bin/env python3
"""
Test EDSM marketplace for Platinum in Col 285 Sector NF-W a45-1
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

try:
    from marketplace_finder import MarketplaceFinder
    print("✅ MarketplaceFinder import successful")
    
    marketplace = MarketplaceFinder()
    print("✅ MarketplaceFinder initialization successful")
    
    # Test with the specific system and commodity from user request
    test_system = "Col 285 Sector NF-W a45-1"
    test_commodity = "Alexandrite"
    
    print(f"\n🔍 Testing {test_commodity} prices near {test_system}")
    print("=" * 60)
    
    # Search for platinum prices
    results = marketplace.find_commodity_prices(test_commodity, test_system, max_results=10)
    
    if results:
        print(f"Found {len(results)} stations selling {test_commodity}:")
        print()
        for i, result in enumerate(results):
            print(f"{i+1}. {result['station_name']} | {result['system_name']}")
            print(f"   Sell Price: {result['sell_price']:,} Cr")
            print(f"   Distance: {result['system_distance']:.1f} Ly")
            print(f"   Demand: {result['demand']:,}, Stock: {result['stock']:,}")
            print(f"   Station Type: {result['station_type']}")
            print()
    else:
        print(f"❌ No {test_commodity} prices found near {test_system}")
    
    print("🎉 Test completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()