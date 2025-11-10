# EliteMining Mining Reports API Specification

**Version:** 1.0  
**Last Updated:** November 9, 2025

## Overview

EliteMining app sends mining session data to a server API endpoint for aggregation, analytics, and web dashboard display. This document specifies the data format and API requirements.

---

## API Endpoints

### Mining Session Upload
```
POST {base_url}/api/mining/session
```

### Hotspot Bulk Upload
```
POST {base_url}/api/hotspots/bulk
```

Where `{base_url}` is configurable (e.g., `https://elitemining.example.com`)

### Authentication
```http
X-API-Key: {user_api_key}
```

API key is generated on server when user registers, then pasted into EliteMining app settings.

### Request Headers
```http
Content-Type: application/json
X-API-Key: {api_key}
```

### Request Methods
- **Single Session Upload:** Send one session object to `/api/mining/session`
- **Bulk Session Upload:** Send array of session objects to `/api/mining/session` (for historical data on first enable)
- **Bulk Hotspot Upload:** Send array of hotspot objects to `/api/hotspots/bulk` (once on first enable)

---

## Data Format

### Single Session Request
```json
{
  "cmdr_name": "Commander Name",
  "timestamp": "2025-11-09T14:30:00",
  "system": "Hyades Sector AB-C d1234",
  "body": "Body A Ring",
  "ship": "Python",
  "session_type": "Laser Mining",
  "duration": "06:43",
  "total_tons": 44.0,
  "tph": 461.8,
  "prospectors_used": 120,
  "asteroids_prospected": 120,
  "asteroids_with_materials": 42,
  "hit_rate_percent": 35.5,
  "avg_quality_percent": 28.3,
  "total_average_yield": 12.8,
  "best_material": "Platinum (25.3%)",
  "materials_tracked": 2,
  "total_finds": 23,
  "hotspot_info": {
    "system_name": "Hyades Sector AB-C d1234",
    "system_address": 123456789,
    "body_name": "Body A",
    "body_id": 5,
    "ring_type": "Pristine Metallic",
    "ring_mass": 5965100000,
    "inner_radius": 64972000,
    "outer_radius": 66417000,
    "density": 10.00094,
    "ls_distance": 1234.5,
    "material_name": "Platinum",
    "hotspot_count": 2,
    "scan_date": "2025-11-09T14:30:00",
    "x_coord": 123.45,
    "y_coord": 234.56,
    "z_coord": 345.67,
    "coord_source": "EDSM"
  },
  "materials_mined": {
    "Platinum": {
      "tons": 25.5,
      "tph": 280.1,
      "avg_percentage": 15.3,
      "best_percentage": 32.8,
      "find_count": 15
    },
    "Painite": {
      "tons": 18.5,
      "tph": 181.7,
      "avg_percentage": 10.2,
      "best_percentage": 24.1,
      "find_count": 8
    }
  },
  "mineral_performance": {
    "Platinum": {
      "prospected": 85,
      "hit_rate": 35.5
    },
    "Painite": {
      "prospected": 35,
      "hit_rate": 22.9
### Bulk Session Upload Request
```json
[
  {
    "cmdr_name": "...",
    "timestamp": "...",
    ...
  },
  {
    "cmdr_name": "...",
    "timestamp": "...",
    ...
  }
]
```

### Bulk Hotspot Upload Request
```json
{
  "cmdr_name": "Commander Name",
  "hotspots": [
    {
      "system_name": "Hyades Sector AB-C d1234",
      "system_address": 123456789,
      "body_name": "Body A",
      "body_id": 5,
      "ring_type": "Pristine Metallic",
      "ring_mass": 5965100000,
      "inner_radius": 64972000,
      "outer_radius": 66417000,
      "density": 10.00094,
      "ls_distance": 1234.5,
      "material_name": "Platinum",
      "hotspot_count": 2,
      "scan_date": "2025-11-09T14:30:00",
      "x_coord": 123.45,
      "y_coord": 234.56,
      "z_coord": 345.67,
      "coord_source": "EDSM"
    },
    {
      "system_name": "Another System",
      "body_name": "Body B",
      "material_name": "Painite",
      ...
    }
  ]
}
```

---

## Field Definitions

### Session Metadata
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cmdr_name` | string | Yes | Commander name |
| `timestamp` | string | Yes | ISO 8601 format: "2025-11-09T14:30:00" |
| `system` | string | Yes | System name |
| `body` | string | Yes | Body name with ring info |
| `ship` | string | Yes | Ship type |
| `session_type` | string | Yes | "Laser Mining", "Core Mining", etc. |
| `comment` | string | No | User's session notes/comments |

### Session Statistics
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `duration` | string | Yes | Session duration as "HH:MM" (e.g., "06:43") |
| `total_tons` | float | Yes | Total tons of materials refined |
| `tph` | float | Yes | Tons per hour |
| `prospectors_used` | integer | Yes | Number of prospector limpets used |
| `asteroids_prospected` | integer | Yes | Total asteroids prospected |
| `asteroids_with_materials` | integer | Yes | Asteroids containing tracked materials |
| `hit_rate_percent` | float | Yes | Percentage of asteroids with valuable materials |
| `avg_quality_percent` | float | Yes | Average yield percentage across all asteroids |
| `total_average_yield` | float | Yes | Total average yield across all tracked materials |
| `best_material` | string | No | Best performing material with percentage (e.g., "Platinum (25.3%)") |
| `materials_tracked` | integer | Yes | Number of different material types tracked |
| `total_finds` | integer | Yes | Total number of material finds across all asteroids |

### Materials Mined
Object with material names as keys, each containing:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tons` | float | Yes | Tons of this material refined |
| `tph` | float | Yes | Tons per hour for this material |
| `avg_percentage` | float | Yes | Average percentage found in asteroids |
| `best_percentage` | float | Yes | Best (highest) percentage found |
| `find_count` | integer | Yes | Number of times this material was found |

### Mineral Performance
Object with material names as keys, each containing:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prospected` | integer | Yes | Number of asteroids prospected for this material |
| `hit_rate` | float | Yes | Hit rate percentage for this material |

### Engineering Materials
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `engineering_materials` | object | No | Raw materials collected (e.g., `{"Iron": 45, "Nickel": 23}`) |
| `engineering_materials_total` | integer | No | Total count of engineering materials |

### Hotspot Information (Optional in Session)
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `hotspot_info` | object | No | Hotspot data if session was in a tracked hotspot |
| `system_name` | string | Yes* | System name |
| `system_address` | integer | Yes* | System address from journal |
| `body_name` | string | Yes* | Body name (without ring) |
| `body_id` | integer | Yes* | Body ID from journal |
| `ring_type` | string | Yes* | Ring type (e.g., "Pristine Metallic") |
| `ring_mass` | integer | Yes* | Ring mass |
| `inner_radius` | integer | Yes* | Inner radius in meters |
| `outer_radius` | integer | Yes* | Outer radius in meters |
| `density` | float | Yes* | Ring density |
| `ls_distance` | float | Yes* | Distance from arrival point in light-seconds |
| `material_name` | string | Yes* | Hotspot material name |
| `hotspot_count` | integer | Yes* | Number of overlapping hotspots |
| `scan_date` | string | Yes* | ISO 8601 format scan timestamp |
| `x_coord` | float | No | System X coordinate |
| `y_coord` | float | No | System Y coordinate |
| `z_coord` | float | No | System Z coordinate |
| `coord_source` | string | No | Source of coordinates (e.g., "EDSM", "journal") |

*Required if `hotspot_info` is present

---

## Response Format

### Success Response - Session Upload
```json
{
  "success": true,
  "message": "Session data received",
  "sessions_processed": 1
}
```

For bulk session uploads:
```json
{
  "success": true,
  "message": "Bulk upload completed",
  "sessions_processed": 15
}
```

### Success Response - Hotspot Upload
```json
{
  "success": true,
  "message": "Hotspot data received",
  "hotspots_processed": 42
}
```

### Error Responses
- `200 OK` - Success
- `400 Bad Request` - Invalid data format
- `401 Unauthorized` - Invalid/missing API key
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

---

## Client Behavior

### Upload Timing
- **Automatic**: After each mining session ends (if enabled in settings)
  - Sends session data with optional hotspot info
- **First Enable**: Bulk upload of historical data
  - Uploads all past mining sessions from TXT reports
  - Uploads all discovered hotspots from user database
- **Retry**: Failed uploads queued and retried with exponential backoff

### Retry Logic
1. **First retry**: 30 seconds after failure
2. **Second retry**: 2 minutes after first retry
3. **Third retry**: 5 minutes after second retry
4. **Final failure**: Store in queue, notify user

### Queue Storage
Failed uploads stored in: `{app_data_dir}/failed_api_uploads.json`

```json
{
  "queue": [
    {
      "session_data": {...},
      "timestamp": "2025-11-09T14:30:00Z",
      "retry_count": 0,
      "last_error": "Connection timeout"
    }
  ]
}
```

---

## Privacy & Security

### User Consent
By enabling API upload, users agree to share:
- ✓ Mining session statistics and materials
- ✓ Discovered hotspot locations and details
- ✓ System/body names and coordinates
- ✓ Commander name

A clear consent message is shown when enabling the feature.

### Data NOT Sent
- Screenshots
- Ship loadout details
- Private bookmarks/notes (except hotspot data)
- Private communications

### Data Sent
- Session statistics and materials
- Hotspot locations from user database
- System/body names and coordinates (public Elite Dangerous data)
- Ring metadata (mass, radius, density)
- Commander name (required for dashboard)

---

## Example Implementation

### Python Client Example
```python
import requests
import json

def upload_session(base_url, api_key, session_data):
    headers = {
        'Content-Type': 'application/json',
        'X-API-Key': api_key
    }
    
    endpoint = f"{base_url}/api/mining/session"
    
    response = requests.post(
        endpoint,
        headers=headers,
        json=session_data,
        timeout=10
    )
    
    return response.json()
```
### Server Endpoint Examples (FastAPI)
```python
from fastapi import FastAPI, Header, HTTPException
from typing import List, Union

app = FastAPI()

@app.post("/api/mining/session")
async def receive_session(
    session_data: Union[dict, List[dict]],
    x_api_key: str = Header(None)
):
    # Validate API key
    if not validate_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Handle single or bulk upload
    sessions = [session_data] if isinstance(session_data, dict) else session_data
    
    # Store in database
    for session in sessions:
        store_session(session)
        
        # Store hotspot if present
        if 'hotspot_info' in session:
            store_hotspot(session['hotspot_info'])
    
    return {
        "success": True,
        "message": "Session data received",
        "sessions_processed": len(sessions)
    }

@app.post("/api/hotspots/bulk")
async def receive_hotspots(
    data: dict,
    x_api_key: str = Header(None)
):
    # Validate API key
    if not validate_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Store hotspots in database
    cmdr_name = data.get('cmdr_name')
    hotspots = data.get('hotspots', [])
    
    for hotspot in hotspots:
        store_hotspot(hotspot, cmdr_name)
    
    return {
        "success": True,
        "message": "Hotspot data received",
        "hotspots_processed": len(hotspots)
    }
```

---

## Testing

### Mock Endpoint for Development
```python
# Simple test endpoint that accepts any data
@app.post("/api/mining/session")
def mock_endpoint(data: dict):
    print(f"Received: {json.dumps(data, indent=2)}")
    return {"success": True, "sessions_processed": 1}

@app.post("/api/hotspots/bulk")
def mock_hotspot_endpoint(data: dict):
    print(f"Received hotspots: {len(data.get('hotspots', []))}")
    return {"success": True, "hotspots_processed": len(data.get('hotspots', []))}
```

### Test Data
See example session JSON above for complete test payload.

---

## Configuration

### App Settings (config.json)
```json
{
  "api_upload_enabled": false,
  "api_endpoint_url": "https://elitemining.example.com",
  "api_key": "",
  "cmdr_name_for_api": ""
}
```

**Note:** `api_endpoint_url` is the base URL only. Endpoints `/api/mining/session` and `/api/hotspots/bulk` are appended by the client.

### Self-Hosting Support
- Endpoint URL fully configurable
- No hardcoded server addresses
- Users can run own server instances

---

## Questions?

Contact: [Your contact info or GitHub issues]
