# Distance Calculator Feature - Implementation Plan

**Feature:** EDSM Distance Calculator  
**Started:** November 11, 2025  
**Status:** Planning

---

## Overview

Add a Distance Calculator tab to the main application that uses the EDSM API to calculate distances between Elite Dangerous systems. Provides quick distance calculations for route planning and fleet carrier management.

---

## Requirements

### Core Features
1. **System-to-System Distance Calculator**
   - Calculate distance between any two systems
   - Quick-fill buttons for current system, home, and fleet carrier

2. **Distance to Sol**
   - Automatically show distance to Sol for both systems

3. **System Information Display**
   - Show coordinates (X, Y, Z) for each system
   - Display system names from EDSM

4. **Configuration**
   - Home System setting (saved to config)
   - Fleet Carrier System setting (saved to config)
   - Auto-detect Fleet Carrier from journal files

### Integration Points
- Use existing current system detection (from Ring Finder / Mining Analytics)
- Read Fleet Carrier location from journal files (`CarrierJump`, `Location`, `Docked` events)
- Save settings to `config.json`

---

## UI Design

### Tab Location
- New tab: "Distance Calculator" 
- Positioned after "Commodity Market" tab in main notebook

### Layout
```
┌─ Distance Calculator ────────────────────────────────┐
│                                                       │
│  System A: [___________________] [Use Current]       │
│  System B: [___________________] [Use Home] [Use FC] │
│                                                       │
│  ➤ Distance A ↔ B: 450.32 LY                        │
│                                                       │
│  ─────────────────────────────────────────────────   │
│                                                       │
│  System A Info:                                      │
│  ➤ Distance to Sol: 22,000.45 LY                    │
│  ➤ Coordinates: X: 123.45, Y: -234.56, Z: 345.67    │
│                                                       │
│  System B Info:                                      │
│  ➤ Distance to Sol: 22,450.77 LY                    │
│  ➤ Coordinates: X: 100.00, Y: -200.00, Z: 300.00    │
│                                                       │
│  ─────────────────────────────────────────────────   │
│                                                       │
│  Configuration:                                      │
│  Home System: [___________________] [Set]            │
│  Fleet Carrier: [___________________] [Set]          │
│  [Auto-detect FC from journals]                      │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### UI Elements
- **Entry Fields:** Standard dark theme entry boxes
- **Buttons:** Consistent with app styling (green for action, gray for utility)
- **Labels:** Color-coded results (white for system info, yellow for distances)
- **Separators:** Horizontal lines matching app theme

---

## Implementation Phases

### Phase 1: EDSM Integration Module
**File:** `app/edsm_distance.py`

#### Tasks:
- [x] Test EDSM API endpoints
- [ ] Create `EDSMDistanceCalculator` class
- [ ] Implement `get_system_coordinates(system_name)` method
- [ ] Implement `calculate_distance(system1, system2)` method
- [ ] Add caching for recently queried systems (avoid repeated API calls)
- [ ] Error handling for:
  - System not found
  - Network timeout
  - Invalid API response
  - Malformed system names

#### EDSM API Details
- **Endpoint:** `https://www.edsm.net/api-v1/system`
- **Parameters:**
  - `systemName`: Name of the system
  - `showCoordinates`: 1 (to get X, Y, Z coordinates)
- **Response Format:**
  ```json
  {
    "name": "System Name",
    "coords": {
      "x": 123.45,
      "y": -234.56,
      "z": 345.67
    }
  }
  ```

#### Distance Formula
3D Euclidean Distance:
```python
distance = sqrt((x2-x1)² + (y2-y1)² + (z2-z1)²)
```

**Testing:**
- [x] Test with known systems (Ch'ingsonde, Tucanae Sector CV-Y b2)
- [ ] Test with system name variations (case sensitivity, special characters)
- [ ] Test with non-existent systems
- [ ] Test with network timeouts
- [ ] Test cache functionality

---

### Phase 2: Configuration Management
**Files:** `app/config.json.template`, `app/config.py`

#### Tasks:
- [ ] Add new config fields:
  ```json
  {
    "home_system": "",
    "fleet_carrier_system": "",
    "distance_calculator_cache": {}
  }
  ```

- [ ] Add config getters/setters:
  - [ ] `load_home_system()`
  - [ ] `save_home_system(system_name)`
  - [ ] `load_fleet_carrier_system()`
  - [ ] `save_fleet_carrier_system(system_name)`

- [ ] Migration for existing users
  - [ ] Add new fields with defaults on first load

**Testing:**
- [ ] Test config save/load
- [ ] Test backward compatibility

---

### Phase 3: Fleet Carrier Detection
**File:** `app/edsm_distance.py` or `app/fleet_carrier_tracker.py`

#### Tasks:
- [ ] Implement journal file reader for Fleet Carrier events
- [ ] Parse `CarrierJump` event:
  ```json
  {
    "event": "CarrierJump",
    "StarSystem": "System Name",
    "SystemAddress": 123456789,
    "StarPos": [x, y, z]
  }
  ```

- [ ] Parse `Location` event (when docked at carrier):
  ```json
  {
    "event": "Location",
    "Docked": true,
    "StationName": "Carrier Name",
    "StarSystem": "System Name",
    "StarPos": [x, y, z]
  }
  ```

- [ ] Store last known Fleet Carrier location
- [ ] Update Fleet Carrier system in config when detected

**Testing:**
- [ ] Test with real journal files containing CarrierJump
- [ ] Test with Location events at fleet carrier
- [ ] Test with no fleet carrier data

---

### Phase 4: UI Implementation
**File:** `app/main.py`

#### Tasks:
- [ ] Create Distance Calculator tab in main notebook
- [ ] Build UI layout matching design spec
- [ ] Implement UI components:
  - [ ] System A entry field
  - [ ] System B entry field
  - [ ] "Use Current" button
  - [ ] "Use Home" button
  - [ ] "Use FC" button
  - [ ] Distance result labels
  - [ ] System info labels (coordinates, distance to Sol)
  - [ ] Home System config field
  - [ ] Fleet Carrier config field
  - [ ] "Set" buttons for config
  - [ ] "Auto-detect FC" button

- [ ] Implement event handlers:
  - [ ] Calculate distance on system name change
  - [ ] Update results display
  - [ ] Handle "Use Current" click
  - [ ] Handle "Use Home" click
  - [ ] Handle "Use FC" click
  - [ ] Handle "Set" button clicks (save to config)
  - [ ] Handle "Auto-detect FC" click

- [ ] Add loading indicators for API calls
- [ ] Add error message display

**Testing:**
- [ ] Test all UI interactions
- [ ] Test with valid system names
- [ ] Test with invalid system names
- [ ] Test quick-fill buttons
- [ ] Test config save/load from UI

---

### Phase 5: Current System Integration
**File:** `app/main.py`

#### Tasks:
- [ ] Locate existing current system tracking code
  - Used in Ring Finder: `self.current_system`
  - Used in Mining Analytics: similar tracking
  
- [ ] Create shared accessor for current system
- [ ] Update Distance Calculator when current system changes
- [ ] Add visual indicator showing current system

**Testing:**
- [ ] Test current system detection from journals
- [ ] Test auto-update when system changes
- [ ] Test with no current system detected

---

### Phase 6: Polish & Optimization
**Files:** All

#### Tasks:
- [ ] Add tooltips to all UI elements
- [ ] Implement caching to reduce API calls
- [ ] Add "Calculate" button (optional, or auto-calculate on change)
- [ ] Add copy-to-clipboard for coordinates
- [ ] Add keyboard shortcuts (Enter to calculate)
- [ ] Performance optimization:
  - [ ] Debounce API calls (wait 500ms after typing stops)
  - [ ] Cache results for 5 minutes
  - [ ] Batch requests if possible

- [ ] Visual enhancements:
  - [ ] Loading spinner during API calls
  - [ ] Success/error icons
  - [ ] Color-coded distance ranges (green: close, yellow: medium, red: far)

**Testing:**
- [ ] Test with rapid system name changes
- [ ] Test cache hit/miss rates
- [ ] Test keyboard shortcuts
- [ ] Test tooltips display

---

### Phase 7: Documentation
**Files:** `README.md`, `docs/DISTANCE_CALCULATOR.md`

#### Tasks:
- [ ] User documentation:
  - [ ] How to use Distance Calculator
  - [ ] How to set Home System
  - [ ] How to auto-detect Fleet Carrier
  - [ ] Explanation of coordinates

- [ ] Developer documentation:
  - [ ] EDSM API integration details
  - [ ] Caching strategy
  - [ ] Error handling approach

- [ ] Update main README with new feature

**Testing:**
- [ ] Review documentation for clarity
- [ ] Test documented workflows

---

### Phase 8: Testing & Release
**Files:** All

#### Tasks:
- [ ] Unit tests:
  - [ ] Test distance calculation formula
  - [ ] Test EDSM API parsing
  - [ ] Test cache functionality
  - [ ] Test config save/load

- [ ] Integration tests:
  - [ ] Test with real EDSM API
  - [ ] Test with real journal files
  - [ ] Test UI interactions end-to-end

- [ ] User acceptance testing:
  - [ ] Test with various system names
  - [ ] Test edge cases
  - [ ] Test performance with slow network

- [ ] Release preparation:
  - [ ] Update version number
  - [ ] Create changelog
  - [ ] Build installer
  - [ ] Test installer

**Testing:**
- [ ] All tests pass
- [ ] No regressions in existing features
- [ ] Performance benchmarks met

---

## Technical Details

### Dependencies
- **Existing:** `requests` library (already in project)
- **EDSM API:** No API key required for coordinate queries
- **Python modules:** `math` (for distance calculation), `json`, `datetime`

### Error Handling
1. **System Not Found:** Display "System not found in EDSM database"
2. **Network Error:** Display "Unable to connect to EDSM. Check internet connection"
3. **Timeout:** Display "Request timed out. Try again"
4. **Invalid Input:** Display "Please enter a valid system name"

### Performance Targets
- **API Response Time:** < 2 seconds per system lookup
- **UI Responsiveness:** No blocking during API calls
- **Cache Hit Rate:** > 80% for repeated lookups
- **Memory Usage:** < 10MB for cache

---

## Success Criteria

- [ ] Distance Calculator tab visible in main notebook
- [ ] Successfully calculates distance between any two valid systems
- [ ] Displays distance to Sol for both systems
- [ ] Shows system coordinates (X, Y, Z)
- [ ] "Use Current" button populates current system
- [ ] "Use Home" button populates saved home system
- [ ] "Use FC" button populates fleet carrier location
- [ ] Home System saves to config
- [ ] Fleet Carrier System saves to config
- [ ] Auto-detect finds fleet carrier from journals
- [ ] Error messages display for invalid systems
- [ ] API calls are cached to reduce network usage
- [ ] UI matches app styling and theme
- [ ] No impact on existing features
- [ ] All tests pass

---

## Timeline Estimate

- **Phase 1:** 2-3 hours (EDSM module)
- **Phase 2:** 30 minutes (Config)
- **Phase 3:** 1-2 hours (Fleet Carrier detection)
- **Phase 4:** 3-4 hours (UI implementation)
- **Phase 5:** 1 hour (Current system integration)
- **Phase 6:** 2 hours (Polish)
- **Phase 7:** 1 hour (Documentation)
- **Phase 8:** 2 hours (Testing & release)

**Total:** ~12-15 hours

---

## Notes

- EDSM API is free and doesn't require authentication for coordinate queries
- System names are case-insensitive in EDSM
- Some systems may not have coordinates if they haven't been visited/submitted
- Fleet Carrier detection only works if journals contain carrier events
- Consider adding "Jump Range" calculator in future (calculate number of jumps needed)

---

## Updates Log

**2025-11-11:** 
- Planning phase complete
- EDSM API tested successfully
- Distance calculations verified with test systems

---

*This document will be updated as implementation progresses.*
