# Enhanced Hotspot Finder with EDDN Integration

## Overview

The Enhanced Hotspot Finder is a major upgrade to EliteMining that provides comprehensive mining hotspot location services with real-time community data integration through the Elite Dangerous Data Network (EDDN).

## Key Features

### 🌐 Live Community Data (EDDN)
- **Real-time Integration**: Connects to Elite Dangerous Data Network live stream
- **Community Discoveries**: Receives mining hotspot discoveries from other commanders
- **ZeroMQ Protocol**: Uses efficient ZeroMQ messaging for live data
- **Automatic Processing**: Filters and processes fssbodysignals messages for mining hotspots

### 📊 Hybrid Data Sources
- **EDDN Live Data**: Real-time community mining hotspot discoveries
- **Local Database**: Comprehensive database with 98 verified hotspots
- **EDSM Integration**: Enhanced coordinate data for accurate distance calculations
- **Source Identification**: Clear indication of data source in results

### 🔍 Enhanced Search Capabilities
- **Material Filtering**: Filter by specific mining materials
- **Distance Calculations**: Calculate distances from current system
- **Auto-Detection**: Automatically detect current system from game journals
- **Sortable Results**: Sort by distance, system, material type, etc.

## EDDN Integration Details

### What is EDDN?
The Elite Dangerous Data Network (EDDN) is a community-driven live data feed that collects and distributes real-time game data from Elite Dangerous commanders worldwide.

### How It Works
1. **Connection**: Connects to `tcp://eddn.edcd.io:9500` using ZeroMQ
2. **Message Processing**: Listens for `fssbodysignals` schema messages
3. **Hotspot Detection**: Identifies mining hotspot signals from FSS scans
4. **Data Integration**: Combines live data with local database
5. **Real-time Updates**: Provides immediate access to community discoveries

### Supported Materials
- **Platinum**: High-value core mining
- **Low Temperature Diamonds**: Premium core mining
- **Painite**: Laser mining
- **Void Opals**: Core mining
- **Alexandrite**: Core mining
- **Tritium**: Fuel mining
- **And more**: All major mining materials

## Installation Requirements

### Dependencies
```bash
pip install pyzmq  # For EDDN integration
pip install requests  # For EDSM API
```

### Optional Components
- **EDSM API**: Enhanced coordinate data (requires API key)
- **Game Journal Detection**: Automatic current system detection

## Usage Guide

### 1. Basic Search
```
1. Enter system name in "Search System" field
2. Select material filter (optional)
3. Set maximum distance limit
4. Click "Find Hotspots"
```

### 2. EDDN Live Data
```
1. Click "Connect to EDDN" button
2. Status will show "Connected" when active
3. Live discoveries will appear with "EDDN Live" source
4. Combine with local database for comprehensive results
```

### 3. Distance Calculations
```
1. Enter current system in "Current System" field
2. Click "Auto-Detect" to get from game journal
3. Results will show accurate distances in light years
```

## User Interface

### Search Controls
- **Search System**: Target system name (partial matches supported)
- **Current System**: Your current location for distance calculations
- **Material Filter**: Filter results by mining material type
- **Max Distance**: Limit results by distance from current system

### EDDN Controls
- **Status Indicator**: Shows EDDN connection status
- **Connect/Disconnect**: Toggle EDDN live data stream
- **Info Display**: Shows EDDN availability and requirements

### Results Display
- **Source Column**: Indicates data source (EDDN Live / Local DB)
- **Distance**: Light years from current system
- **System**: Target system name
- **Ring**: Planetary ring designation
- **Type**: Mining material type
- **Hotspots**: Number of hotspots
- **LS**: Distance from star in light seconds
- **Density**: Ring density rating

## Technical Architecture

### Data Flow
```
EDDN Stream → ZeroMQ → Message Processing → Data Integration → UI Display
     ↓
Local Database → Coordinate Enhancement → Distance Calculation → Results
     ↓
EDSM API → System Coordinates → Distance Validation → Final Results
```

### Error Handling
- **Graceful Degradation**: Falls back to local database if EDDN fails
- **Dependency Checking**: Automatically detects ZeroMQ availability
- **Connection Recovery**: Handles network interruptions gracefully
- **Cache Management**: Intelligent caching to reduce API calls

## Configuration

### EDSM API Key (Optional)
Add to `config.json`:
```json
{
  "edsm_api_key": "your_api_key_here"
}
```

### EDDN Settings
- **Auto-Connect**: Can be enabled in Interface Options
- **Cache Limits**: Live data limited to 1000 recent entries
- **Timeout Settings**: Configurable connection timeouts

## Performance Considerations

### Memory Usage
- **Live Data Cache**: Limited to 1000 recent EDDN entries
- **Local Database**: 98 hotspots with minimal memory footprint
- **Coordinate Cache**: System coordinates cached for 1 hour

### Network Usage
- **EDDN Stream**: Minimal bandwidth usage
- **EDSM API**: Only used when needed for coordinates
- **Efficient Processing**: ZeroMQ provides low-latency messaging

## Troubleshooting

### Common Issues

#### "ZMQ Not Available"
**Solution**: Install PyZMQ dependency
```bash
pip install pyzmq
```

#### "EDDN Connection Failed"
**Causes**:
- Network connectivity issues
- Firewall blocking TCP connections
- EDDN service temporarily unavailable

**Solutions**:
- Check internet connection
- Verify firewall settings
- Try reconnecting later

#### "No EDDN Data Received"
**Explanation**: Normal behavior - mining hotspot discoveries are infrequent
**Action**: Leave connected and data will appear when available

### Debug Information
Enable debug output in console to see:
- EDDN connection status
- Message processing details
- Data integration results

## Future Enhancements

### Planned Features
- **Historical Data**: Archive of past EDDN discoveries
- **Hotspot Quality**: Community rating system
- **Real-time Notifications**: Alerts for new discoveries
- **Data Export**: Export hotspot data to various formats

### Community Integration
- **Data Contribution**: Automatic sharing of discoveries
- **Verification System**: Community validation of hotspot data
- **Mining Reports**: Integration with mining session tracking

## Contributing

The Enhanced Hotspot Finder is part of the EliteMining project. Community contributions are welcome for:

- **Database Updates**: New verified hotspots
- **EDDN Processing**: Enhanced message filtering
- **UI Improvements**: Better user experience
- **Performance Optimization**: Faster data processing

---

*Enhanced Hotspot Finder with EDDN Integration - Bringing real-time community data to EliteMining*