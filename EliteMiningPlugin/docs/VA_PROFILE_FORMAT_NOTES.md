# VoiceAttack Profile Format Notes

## File Formats

VoiceAttack profiles (.VAP) can be in two formats:

### 1. Compressed (Binary) - Default
- **Extension:** `.vap`
- **Format:** Custom VoiceAttack binary/compressed format
- **Header:** EC DD 05 58... (proprietary)
- **Cannot be parsed** directly by XML libraries

### 2. Uncompressed (XML) - Export Option
- **Extension:** `.vap`
- **Format:** Plain XML
- **Header:** `<?xml version="1.0"...`
- **Can be parsed** by standard XML libraries

## Current Limitation

The auto-updater currently **requires uncompressed XML** format.

## Workaround

### Option 1: Export as Uncompressed (For Testing)

In VoiceAttack:
1. Right-click profile → **Export**
2. ☐ **Uncheck** "Compress profile data"
3. Save as `.vap` file
4. Use this file for testing

### Option 2: VoiceAttack Database Access (Preferred - Future)

VoiceAttack stores profiles in `VoiceAttack.dat` database. 

**Future enhancement:** Add database access to read/write profiles directly from the database, bypassing the .VAP file format entirely.

## Solution Plan

### Phase 1 (Current - Testing)
Use uncompressed .VAP files for development/testing

### Phase 2 (Future - Production)
Access VoiceAttack.dat database directly:
- Read profiles from database
- Modify in memory
- Write back to database
- No .VAP file manipulation needed

## For Now

To test the updater, export an **uncompressed** EliteMining profile:

```
VoiceAttack → Profile Options → Export → ☐ Compress profile data
```

Save as `EliteMining-Profile-Uncompressed.vap` for testing.
