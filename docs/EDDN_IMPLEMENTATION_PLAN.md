# EDDN Listener Implementation Plan

## What is EDDN?
Elite Dangerous Data Network - real-time message stream of game events from players running EDMC/EDDI

## Architecture
```
Players with EDMC → EDDN Stream → Your Listener → Local Database → Fast Searches
```

## Implementation Steps

### 1. Install Dependencies
```bash
pip install pyzmq  # ZeroMQ messaging library
```

### 2. Create EDDN Listener Service
- Connect to `tcp://eddn.edcd.io:9500`
- Subscribe to market commodity messages
- Parse incoming JSON messages
- Update local market_data.db

### 3. Database Schema
```sql
CREATE TABLE market_prices (
    system_name TEXT,
    station_name TEXT,
    commodity_name TEXT,
    sell_price INTEGER,
    buy_price INTEGER,
    demand INTEGER,
    stock INTEGER,
    timestamp DATETIME,
    PRIMARY KEY (system_name, station_name, commodity_name)
);
```

### 4. Background Service
- Run continuously in background
- Auto-start with app
- Handle reconnections
- Log updates

### 5. Query Local Database
Replace EDSM API calls with:
```sql
SELECT * FROM market_prices 
WHERE commodity_name = 'Alexandrite'
AND system_name IN (nearby_systems)
ORDER BY sell_price DESC
```

## Benefits
- ✅ Instant searches (local database)
- ✅ No rate limits
- ✅ Real-time data (updated by community)
- ✅ Works offline (uses cached data)

## Drawbacks
- ⚠️ Complex setup
- ⚠️ Requires background service
- ⚠️ ~500MB database size
- ⚠️ Network bandwidth for stream

## Next Steps
1. Test aggressive caching (already implemented)
2. If caching not enough, implement EDDN listener
3. Package as Windows service for auto-start

---
**Status:** Caching implemented. EDDN is backup plan if needed.
