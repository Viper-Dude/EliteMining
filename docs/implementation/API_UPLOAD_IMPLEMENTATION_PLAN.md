# EliteMining API Upload Feature - Implementation Plan

**Feature:** Mining Reports API Upload  
**Started:** November 9, 2025  
**Status:** Planning Complete ✓

---

## Overview

Implement API upload functionality to send mining session data to a server for aggregation, analytics, and web dashboard display.

---

## Implementation Phases

### ✅ Phase 0: Planning & Documentation
**Status:** COMPLETE  
**Completed:** November 9, 2025

- [x] Define data format and API structure
- [x] Create API specification document (`docs/API_SPECIFICATION.md`)
- [x] Share spec with server developer
- [x] Confirm TXT reports have complete data
- [x] Define retry/queue strategy

---

### ⏳ Phase 1: Core API Uploader Module
**Status:** NOT STARTED  
**File:** `app/api_uploader.py`

#### Tasks:
- [ ] Create `APIUploader` class
  - [ ] Initialize with config (endpoint URL, API key, CMDR name)
  - [ ] Set enabled/disabled state
  - [ ] Track upload statistics

- [ ] Implement TXT report parser
  - [ ] Parse session metadata (system, body, ship, duration, timestamp)
  - [ ] Parse refined minerals section
  - [ ] Parse mineral analysis section (prospecting data)
  - [ ] Parse cargo material breakdown
  - [ ] Parse engineering materials section
  - [ ] Parse session comments
  - [ ] Handle missing/malformed sections gracefully

- [ ] Implement JSON builder
  - [ ] Convert parsed TXT data to API JSON format
  - [ ] Include all required fields from spec
  - [ ] Calculate derived fields (TPH, hit rates, etc.)
  - [ ] Add optional hotspot_info if session in tracked hotspot
  - [ ] Handle optional fields properly
  - [ ] Validate data before sending
  - [ ] Build hotspot bulk upload JSON structure
- [ ] Implement JSON builder
  - [ ] Convert parsed TXT data to API JSON format
  - [ ] Include all required fields from spec
  - [ ] Calculate derived fields (TPH, hit rates, etc.)
  - [ ] Handle optional fields properly
- [ ] Implement HTTP client
  - [ ] POST request with JSON body to `/api/mining/session`
  - [ ] POST request to `/api/hotspots/bulk` for hotspot data
  - [ ] Set headers (Content-Type, X-API-Key)
  - [ ] Configurable timeout (10 seconds default)
  - [ ] Handle connection errors
  - [ ] Handle HTTP error responses (400, 401, 429, 500)
  - [ ] Parse success/error responses
  - [ ] Handle HTTP error responses (400, 401, 429, 500)
  - [ ] Parse success/error responses

- [ ] Implement retry logic
  - [ ] Attempt 1: Immediate send
  - [ ] Attempt 2: 30 seconds after failure
  - [ ] Attempt 3: 2 minutes after second failure
  - [ ] Attempt 4: 5 minutes after third failure
  - [ ] After 4 failures: queue for later

- [ ] Implement queue manager
  - [ ] Queue file: `failed_api_uploads.json` in app data directory
  - [ ] Add failed upload to queue with metadata
  - [ ] Retry queued uploads on app startup
  - [ ] Remove from queue on success
  - [ ] Limit queue size (e.g., 100 sessions max)

**Dependencies:**
- `requests` library (already used in project)
**Testing:**
- [ ] Test TXT parser with real session files
- [ ] Test hotspot database query
- [ ] Test JSON output matches API spec (sessions + hotspots)
- [ ] Test HTTP client with mock endpoint (both endpoints)
- [ ] Test retry logic with simulated failures
- [ ] Test queue persistence across app restarts
- [ ] Test hotspot matching to sessions
- [ ] Test HTTP client with mock endpoint
- [ ] Test retry logic with simulated failures
- [ ] Test queue persistence across app restarts

---
#### Tasks:
- [ ] Add new config fields to `config.json.template`:
  ```json
  {
    "api_upload_enabled": false,
    "api_endpoint_url": "https://elitemining.example.com",
    "api_key": "",
    "cmdr_name_for_api": ""
  }
  ```
  Note: Base URL only, endpoints are `/api/mining/session` and `/api/hotspots/bulk`api_upload_enabled": false,
    "api_endpoint_url": "https://elitemining.example.com/api/mining/session",
    "api_key": "",
    "cmdr_name_for_api": ""
  }
  ```

- [ ] Update `config.py` to handle new fields
  - [ ] Add getters for API settings
  - [ ] Add setters for API settings
  - [ ] Ensure backward compatibility (default to disabled)
  - [ ] Validate URL format
  - [ ] Validate API key is not empty when enabled

- [ ] Migration for existing users
  - [ ] Add new fields with defaults on first load
  - [ ] Preserve existing config values

**Testing:**
- [ ] Test config load with new fields
- [ ] Test config save preserves all values
- [ ] Test backward compatibility with old config files
- [ ] Test validation rejects invalid URLs

#### Tasks:
- [ ] Add API Upload section to General Settings tab
  - [ ] Enable/Disable checkbox with consent message
  - [ ] Consent message: "By enabling, you agree to share: Mining sessions, Hotspot locations, Materials data"
  - [ ] API Endpoint URL text field (base URL only, default: https://elitemining.example.com)
  - [ ] API Key text field (password-style)
  - [ ] CMDR Name text field
  - [ ] Test Connection button
  - [ ] Upload Statistics display (sessions uploaded, hotspots uploaded, last upload time)
  - [ ] Manual Bulk Upload button (sessions + hotspots)
  - [ ] API Endpoint URL text field (with default)
  - [ ] API Key text field (password-style)
  - [ ] CMDR Name text field
  - [ ] Test Connection button
  - [ ] Upload Statistics display (sessions uploaded, last upload time)
  - [ ] Manual Bulk Upload button

- [ ] Implement UI callbacks
  - [ ] Save settings on change
  - [ ] Test connection validates endpoint and API key
  - [ ] Show success/error messages
  - [ ] Bulk upload shows progress dialog
**UI Layout:**
```
┌─ API Upload Settings ────────────────────────┐
│                                               │
│ [✓] Enable API Upload                        │
│                                               │
│ ℹ️ By enabling, you agree to share:          │
│   • Mining session statistics                │
│   • Discovered hotspot locations             │
│   • Materials and performance data           │
│                                               │
│ CMDR Name: [_________________]                │
│                                               │
│ API Endpoint: [_________________________]    │
│                                               │
│ API Key: [********************]              │
│                                               │
│ [Test Connection] [Bulk Upload All Data]     │
│                                               │
│ Status: ✓ Last upload: 5 minutes ago         │
│ Sessions uploaded: 42  |  Hotspots: 15       │
│                                               │
└───────────────────────────────────────────────┘
```                                             │
│ [Test Connection] [Bulk Upload All Sessions] │
│                                               │
│ Status: ✓ Last upload: 5 minutes ago         │
│ Total sessions uploaded: 42                   │
│                                               │
└───────────────────────────────────────────────┘
```

**Testing:**
- [ ] Test UI enables/disables correctly
- [ ] Test settings save and load
- [ ] Test connection validates properly
- [ ] Test bulk upload with multiple sessions
- [ ] Test error messages display correctly

---

### ⏳ Phase 4: Session End Integration
**Status:** NOT STARTED  
**Files:** `app/prospector_panel.py`, `app/main.py`

#### Tasks:
- [ ] Hook into session end event
  - [ ] Locate where TXT report is saved (in `_save_session_report_with_timestamp`)
  - [ ] Add API upload call after successful report save
  - [ ] Pass session file path to uploader
  - [ ] Handle upload errors gracefully (don't block session end)

- [ ] Implement upload trigger
  - [ ] Check if API upload is enabled
  - [ ] Parse TXT file that was just saved
  - [ ] Send to API uploader
  - [ ] Log success/failure
  - [ ] Queue on failure

- [ ] Add to main app initialization
  - [ ] Initialize API uploader on app start
  - [ ] Retry queued uploads on startup
  - [ ] Pass config to uploader

**Code Location:**
- Session end: `prospector_panel.py` → `end_mining_session_internal()`
- Report save: `prospector_panel.py` → `_save_session_report_with_timestamp()`

#### Tasks:
- [ ] Implement bulk session upload function
  - [ ] Scan `Reports/Mining Session/` directory for TXT files
  - [ ] Use `sessions_index.csv` to get file list
  - [ ] Parse each TXT file
  - [ ] Build array of session objects
  - [ ] Send as bulk upload (single POST with array to `/api/mining/session`)
  - [ ] Show progress (e.g., "Uploading 15 of 42 sessions...")
  - [ ] Handle partial failures (some sessions succeed, some fail)

- [ ] Implement bulk hotspot upload function
  - [ ] Query all hotspots from `user_data.db` hotspot_data table
  - [ ] Build array of hotspot objects
  - [ ] Send as bulk upload (single POST to `/api/hotspots/bulk`)
  - [ ] Show progress (e.g., "Uploading 42 hotspots...")
  - [ ] Handle upload failures

- [ ] Implement combined bulk upload
  - [ ] Upload hotspots first
  - [ ] Then upload sessions
**Testing:**
- [ ] Test bulk upload with 1 session
- [ ] Test bulk upload with 10 sessions
- [ ] Test bulk upload with 100+ sessions
- [ ] Test bulk hotspot upload with multiple hotspots
- [ ] Test combined upload (hotspots + sessions)
- [ ] Test progress reporting for both types
- [ ] Test cancellation
- [ ] Test partial failure handling
- [ ] Test duplicate prevention on re-enablen
  - [ ] Scan `Reports/Mining Session/` directory for TXT files
  - [ ] Use `sessions_index.csv` to get file list
  - [ ] Parse each TXT file
  - [ ] Build array of session objects
  - [ ] Send as bulk upload (single POST with array)
  - [ ] Show progress (e.g., "Uploading 15 of 42 sessions...")
  - [ ] Handle partial failures (some sessions succeed, some fail)

- [ ] Add progress callback
  - [ ] Report current file being processed
  - [ ] Report upload progress
  - [ ] Allow cancellation

- [ ] Handle large datasets
  - [ ] Batch uploads (e.g., 50 sessions per request)
  - [ ] Rate limiting (delay between batches)
  - [ ] Resume on failure

**Testing:**
- [ ] Test bulk upload with 1 session
- [ ] Test bulk upload with 10 sessions
- [ ] Test bulk upload with 100+ sessions
- [ ] Test progress reporting
- [ ] Test cancellation
- [ ] Test partial failure handling

---

### ⏳ Phase 6: Error Handling & Logging
**Status:** NOT STARTED  
**Files:** `app/api_uploader.py`, `app/logging_setup.py`

#### Tasks:
- [ ] Add logging for API operations
  - [ ] Log upload attempts (success/failure)
  - [ ] Log retry attempts
  - [ ] Log queue operations
  - [ ] Log parsing errors
  - [ ] Use existing logging setup

- [ ] Implement user notifications
  - [ ] Success: Silent or brief notification
  - [ ] Failure: Show error message with option to retry
  - [ ] Persistent failure: Suggest checking settings
  - [ ] Queue full: Notify user to clear queue

- [ ] Add error recovery
  - [ ] Network timeout: Retry with backoff
  - [ ] Invalid API key: Notify user, don't retry
  - [ ] Server error (500): Retry
  - [ ] Rate limit (429): Backoff and retry
  - [ ] Bad request (400): Log error, don't retry

**Testing:**
- [ ] Test all error scenarios
- [ ] Test notifications display correctly
- [ ] Test logging captures all events
- [ ] Test error recovery works

---

### ⏳ Phase 7: Testing & Validation
**Status:** NOT STARTED

#### Tasks:
- [ ] Unit tests for TXT parser
  - [ ] Test with complete session files
  - [ ] Test with incomplete/malformed files
  - [ ] Test with various material counts
  - [ ] Test with engineering materials
  - [ ] Test with missing sections

- [ ] Unit tests for JSON builder
  - [ ] Verify all required fields present
  - [ ] Verify data types correct
  - [ ] Verify calculations accurate

- [ ] Integration tests
  - [ ] Test end-to-end session upload
  - [ ] Test bulk upload
  - [ ] Test retry logic
  - [ ] Test queue persistence

- [ ] Mock server testing
  - [ ] Create simple mock endpoint
  - [ ] Test successful uploads
  - [ ] Test error responses
  - [ ] Test timeout handling

- [ ] Real server testing
  - [ ] Test with actual server endpoint
  - [ ] Verify data arrives correctly
  - [ ] Test authentication
  - [ ] Test rate limiting

**Testing:**
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Manual testing complete
- [ ] Server integration verified

---

### ⏳ Phase 8: Documentation
**Status:** NOT STARTED

#### Tasks:
- [ ] Update user documentation
  - [ ] Add API upload feature to README
  - [ ] Create setup guide (how to get API key)
  - [ ] Document configuration options
  - [ ] Add troubleshooting section

- [ ] Update developer documentation
  - [ ] Document `api_uploader.py` module
  - [ ] Add code comments
  - [ ] Document config fields
  - [ ] Document integration points

- [ ] Create user guide
  - [ ] How to enable API upload
  - [ ] How to register for API key
  - [ ] How to bulk upload historical data
  - [ ] Privacy information (what data is sent)

**Files to Update:**
- [ ] `README.md`
- [ ] `docs/API_SPECIFICATION.md` (already created)
- [ ] `docs/USER_GUIDE_API_UPLOAD.md` (new)
- [ ] In-app help text

---

### ⏳ Phase 9: Release Preparation
**Status:** NOT STARTED

#### Tasks:
- [ ] Code review
  - [ ] Review all new code
  - [ ] Check error handling
  - [ ] Verify logging
  - [ ] Check performance

- [ ] Security review
  - [ ] API key stored securely
  - [ ] No sensitive data logged
  - [ ] HTTPS enforced
  - [ ] Input validation

- [ ] Performance testing
  - [ ] Test with large bulk uploads
  - [ ] Check memory usage
  - [ ] Verify no UI blocking
  - [ ] Test queue performance

- [ ] Update version
  - [ ] Increment version in `version.py`
  - [ ] Add changelog entry
  - [ ] Tag release

- [ ] Create release
  - [ ] Build installer with new feature
  - [ ] Test installer version
  - [ ] Create release notes
  - [ ] Publish release

---

## Current Status Summary

**Phase 0:** ✅ COMPLETE  
**Phase 1:** ⏳ NOT STARTED  
**Phase 2:** ⏳ NOT STARTED  
**Phase 3:** ⏳ NOT STARTED  
**Phase 4:** ⏳ NOT STARTED  
**Phase 5:** ⏳ NOT STARTED  
**Phase 6:** ⏳ NOT STARTED  
**Timeline Estimate**

- **Phase 1:** 5-7 hours (Core uploader + hotspot reader)
- **Phase 2:** 1 hour (Config)
- **Phase 3:** 2-3 hours (UI with consent)
- **Phase 4:** 1-2 hours (Integration)
- **Phase 5:** 3 hours (Bulk upload for sessions + hotspots)
- **Phase 6:** 2 hours (Error handling)
- **Phase 7:** 4-5 hours (Testing with hotspots)
- **Phase 8:** 2 hours (Documentation)
- **Phase 9:** 2 hours (Release prep)

**Total:** ~22-29 hours of development
- `os` / `pathlib` - File operations
- `datetime` - Timestamp handling
- `re` - TXT parsing

### EliteMining Modules
- `path_utils.py` - App data directory
- `config.py` - Configuration management
- `logging_setup.py` - Logging
- `prospector_panel.py` - Session end hook

### External
- Server API endpoint (developed in parallel)

---

## Timeline Estimate

- **Phase 1:** 4-6 hours (Core uploader)
- **Phase 2:** 1 hour (Config)
- **Phase 3:** 2-3 hours (UI)
- **Phase 4:** 1 hour (Integration)
- **Phase 5:** 2 hours (Bulk upload)
## Success Criteria

- [x] API specification created and shared
- [ ] TXT reports parse correctly (100% success rate on valid files)
- [ ] Hotspot database queries return all data
- [ ] JSON output matches API spec exactly (sessions + hotspots)
- [ ] Uploads succeed when server available (both endpoints)
- [ ] Retry logic works for transient failures
- [ ] Queue persists across app restarts
- [ ] UI shows clear consent message
- [ ] UI is intuitive and responsive
- [ ] Bulk upload handles 100+ sessions
- [ ] Bulk upload handles all hotspots
- [ ] Hotspot info correctly attached to sessions
- [ ] No data loss on failures
- [ ] Performance impact < 100ms per upload
- [ ] All tests pass
- [ ] Documentation completerd pattern)
- UI implementation (similar to existing settings)

### Medium Risk
- Retry logic (complex edge cases)
- Queue management (persistence issues)
- Bulk upload (performance with large datasets)

### High Risk
- Server availability during development (mitigation: mock endpoint)
- API spec changes (mitigation: version API, maintain backward compatibility)
- Network issues in user environments (mitigation: robust error handling)

**2025-11-09:** 
- Planning phase complete
- API spec created and shared with server dev
- Added hotspot sharing functionality to spec
- Simplified to single enable/disable toggle with full consent
- Two endpoints: `/api/mining/session` and `/api/hotspots/bulk`

## Success Criteria

- [x] API specification created and shared
- [ ] TXT reports parse correctly (100% success rate on valid files)
- [ ] JSON output matches API spec exactly
- [ ] Uploads succeed when server available
- [ ] Retry logic works for transient failures
- [ ] Queue persists across app restarts
- [ ] UI is intuitive and responsive
- [ ] Bulk upload handles 100+ sessions
- [ ] No data loss on failures
- [ ] Performance impact < 100ms per upload
- [ ] All tests pass
- [ ] Documentation complete

---

## Notes

- Keep API uploader optional and disabled by default
- Maintain backward compatibility with existing features
- Don't block UI during uploads (use threading if needed)
- Provide clear error messages for users
- Log all operations for troubleshooting
- Support self-hosting with configurable endpoint

---

## Updates Log

**2025-11-09:** Planning phase complete, API spec created and shared with server dev

---

*This document will be updated as implementation progresses.*
