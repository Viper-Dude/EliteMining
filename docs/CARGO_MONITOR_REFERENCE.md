# Cargo Monitor Display Architecture

## CRITICAL: Two Separate Display Systems

The CargoMonitor class has **TWO INDEPENDENT DISPLAY METHODS** that must be kept in sync:

## 1. INTEGRATED DISPLAY (PRIMARY - Default)

### What Users See

**This is the default display in the main EliteMining window**

- Located in bottom pane of main app
- Always visible when app is running
- Most users interact with this display

### Code Location

- **Class**: `EliteMiningApp` in `app/main.py`
- **Creation Method**: `_create_integrated_cargo_monitor()` - Line ~3516
- **Update Method**: `_update_integrated_cargo_display()` - Line ~3570
- **Update Trigger**: `_periodic_integrated_cargo_update()` - Every 1 second

### Widgets

```python
self.integrated_cargo_summary   # Header: "128/200t (64%)"
self.integrated_cargo_text      # Main display area
self.integrated_status_label    # Status line (hidden but functional)
```

### When to Modify

**MODIFY THIS FIRST** - This is what users see!

## 2. POPUP WINDOW DISPLAY (SECONDARY - Optional)

### What Users See

- Separate floating window (optional)
- Must be manually opened
- Rarely used by most users
- Can be positioned anywhere on screen

### Code Location

- **Class**: `CargoMonitor` in `app/main.py`
- **Creation Method**: `create_window()` - Line ~1195
- **Update Method**: `update_display()` - Line ~1850
- **Update Trigger**: Called when cargo data changes

### Widgets

```python
self.cargo_summary   # Header: "Total: 128/200 tons (64%)"
self.cargo_text      # Main display area
self.status_label    # Status line
self.capacity_label  # Capacity info
```

### When to Modify

**MODIFY SECOND** - Keep in sync with integrated display

## Workflow for Display Changes

### Step-by-Step Process

1. **ALWAYS START WITH INTEGRATED DISPLAY**

   ```text
   File: app/main.py
   Method: _update_integrated_cargo_display() (line ~3570)
   ```

2. **THEN UPDATE POPUP WINDOW**

   ```text
   File: app/main.py
   Method: update_display() (line ~1850)
   ```

3. **TEST BOTH DISPLAYS**
   - Main app: Check integrated display (always visible)
   - Popup: Open cargo window and verify

## Shared Data Sources

Both displays pull from the same data in `CargoMonitor`:

```python
# Cargo Hold Data
self.cargo_items = {}           # Dict: item_name -> quantity (tons)
self.current_cargo = 0          # Total cargo weight
self.max_cargo = 200            # Ship capacity

# Engineering Materials Data
self.materials_collected = {}   # Dict: material_name -> count
self.MATERIAL_GRADES = {}       # Material -> Grade mapping

# Refinery Data
self.refinery_contents = {}     # Refinery hopper contents
```

## Quick Reference: What to Modify Where

### Adding New Data Display:

| Task | Integrated Display | Popup Window |
|------|-------------------|--------------|
| Add new section | `_update_integrated_cargo_display()` Line ~3630 | `update_display()` Line ~1883 |
| Change formatting | `_update_integrated_cargo_display()` | `update_display()` |
| Add new widget | `_create_integrated_cargo_monitor()` Line ~3516 | `create_window()` Line ~1195 |
| Change colors/fonts | Both methods | Both methods |

### Data Collection:

| Task | Location |
|------|----------|
| Add event handler | `process_journal_event()` Line ~2245 |
| Add data storage | `__init__()` Line ~1081 |
| Reset data | Create new method + hook into session |

---

## Checklist for Display Modifications

When modifying cargo display:

- [ ] Modify `_update_integrated_cargo_display()` FIRST (line ~3570)
- [ ] Test in main app window
- [ ] Modify `update_display()` SECOND (line ~1850)
- [ ] Test popup window (if applicable)
- [ ] Verify both displays show same data
- [ ] Update this documentation if architecture changes

## Common Mistakes to Avoid

**Mistake 1**: Only modifying popup window display

- **Result**: Changes not visible in main app
- **Fix**: Always modify integrated display first

**Mistake 2**: Forgetting to update both displays

- **Result**: Displays show different data
- **Fix**: Use checklist above

**Mistake 3**: Testing only popup window

- **Result**: Main display issues not caught
- **Fix**: Test integrated display first (default view)

## Code Search Shortcuts

Find display methods quickly:

```bash
# Integrated display (PRIMARY)
grep -n "_update_integrated_cargo_display" app/main.py

# Popup window (SECONDARY)
grep -n "def update_display" app/main.py

# Both displays
grep -n "cargo_text.insert" app/main.py
```

## Architecture Diagram

```text
EliteMining App
├── Main Window (EliteMiningApp)
│   ├── Top Pane: Mining controls, firegroups, etc.
│   └── Bottom Pane: Integrated Cargo Monitor (PRIMARY)
│       ├── self.integrated_cargo_text
│       ├── self.integrated_cargo_summary
│       └── Updates: _update_integrated_cargo_display()
│
└── Cargo Monitor (CargoMonitor)
    ├── Data Layer (shared by both displays)
    │   ├── self.cargo_items
    │   ├── self.materials_collected
    │   └── self.refinery_contents
    │
    ├── Integrated Display (DEFAULT)
    │   └── Method: _update_integrated_cargo_display()
    │
    └── Popup Window (optional)
        ├── self.cargo_window
        ├── self.cargo_text
        └── Method: update_display()
```

## Last Updated

- Date: 2025-10-14
- Updated by: Materials tracking implementation
- Version: 4.2.7

## Future Improvements

Consider refactoring to eliminate duplication:

1. **Extract display logic** into shared method
2. **Single source of truth** for formatting
3. **Template-based** display generation

This would prevent the two-display sync issue entirely.
