# Missing Ring Coordinates Fix

## Problem
Some rings in the database had missing coordinates (NULL values) even though other rings in the same system had coordinates. This caused those rings to be filtered out during ring finder searches, making them invisible to users.

**Example:** 
- System: Praea Euq JF-Q b5-4
- Ring 11 A: Had coordinates ✅
- Ring 11 B: No coordinates ❌ (not showing in search results)

## Root Cause
When rings were scanned at different times, coordinate capture wasn't always consistent. Older scans (2024) sometimes lacked coordinate data, while newer scans (2025) captured them properly.

## Solution Implemented
Added automatic coordinate fixing to the journal import process:

### File Modified
`app/journal_parser.py`

### Changes Made
1. **Added new method** `_fix_missing_ring_coordinates()`:
   - Identifies systems with mixed coordinate data
   - Copies coordinates from rings that have them to rings that don't
   - All rings in same system share identical system-level coordinates
   
2. **Modified** `parse_all_journals()`:
   - Calls coordinate fix automatically after parsing journals
   - Logs how many entries were fixed

### How It Works
When a user clicks "Import History":

1. Journal files are parsed normally
2. Hotspot data is stored in the database
3. **NEW:** Automatic scan for missing coordinates
4. **NEW:** Copy coordinates between rings in same system
5. Import complete - all rings now searchable

## Benefits
- ✅ **Automatic:** Fixes happen during every journal import
- ✅ **User-friendly:** No manual database maintenance needed
- ✅ **Consistent:** Every user's database gets fixed when they import
- ✅ **Safe:** Only copies coordinates within the same system
- ✅ **Logged:** Shows how many entries were fixed

## Testing Results
First run after implementation:
- Fixed 47 systems with mixed coordinate data
- Updated 229 hotspot entries total
- Example: Praea Euq JF-Q b5-4 - 11 B Ring now shows in searches

## Future Benefit
Any future imports that encounter this issue will automatically fix it, ensuring the database stays clean without user intervention.
