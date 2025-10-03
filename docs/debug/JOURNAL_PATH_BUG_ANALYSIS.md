# Journal Directory Path Issue Analysis

**Date:** October 2, 2025  
**Issues:** Path not saved, Import uses wrong path

---

## 🔍 INVESTIGATION FINDINGS

### **Problem 1: Path Not Remembered on Restart**

#### Root Cause:
**The journal_dir is NEVER saved to config.json!**

#### Evidence:
1. **`_change_journal_dir()` in main.py (Line 5072-5098):**
   ```python
   if sel and os.path.isdir(sel):
       # Update prospector panel if it exists
       if hasattr(self, 'prospector_panel'):
           self.prospector_panel.journal_dir = sel  # ← Only sets in memory
           self.prospector_panel._jrnl_path = None
           self.prospector_panel._jrnl_pos = 0
       
       # Update the UI label
       if hasattr(self, 'journal_lbl'):
           self.journal_lbl.config(text=sel)
       
       self._set_status("Journal folder updated.")
       # ❌ NO SAVE TO CONFIG.JSON!
   ```

2. **`_change_journal_dir()` in prospector_panel.py (Line 2902-2910):**
   ```python
   if sel and os.path.isdir(sel):
       self.journal_dir = sel  # ← Only sets in memory
       self.journal_lbl.config(text=sel)
       self._jrnl_path = None
       self._jrnl_pos = 0
       self._set_status("Journal folder updated.")
       # ❌ NO SAVE TO CONFIG.JSON!
   ```

3. **No `_save_journal_dir_preference()` function exists!**
   - The code references it (Line 5128-5129) but it's never defined:
   ```python
   if hasattr(self.prospector_panel, '_save_journal_dir_preference'):
       self.prospector_panel._save_journal_dir_preference()  # ← Function doesn't exist!
   ```

4. **On App Restart:**
   - `CargoMonitor.__init__()` (Line 1066): 
     ```python
     self.journal_dir = os.path.expanduser("~\\Saved Games\\Frontier Developments\\Elite Dangerous")
     ```
   - Always resets to hardcoded default!

---

### **Problem 2: Import History Uses Wrong Path**

#### Root Cause:
**Two different objects manage journal_dir, and they're not synchronized!**

#### Evidence:
1. **CargoMonitor has its own journal_dir (Line 1066):**
   ```python
   class CargoMonitor:
       def __init__(self, ...):
           self.journal_dir = os.path.expanduser("~\\Saved Games\\...")
   ```

2. **ProspectorPanel has its own journal_dir (Line 398 in prospector_panel.py):**
   ```python
   self.journal_dir = self._detect_journal_dir_default() or ""
   ```

3. **Import uses CargoMonitor's journal_dir (Line 5010):**
   ```python
   journal_dir = self.cargo_monitor.journal_dir  # ← Always the hardcoded default!
   ```

4. **When you change path:**
   - UI updates `self.prospector_panel.journal_dir` ✅
   - BUT: `self.cargo_monitor.journal_dir` is NEVER updated! ❌
   - Import reads from cargo_monitor, so it uses old path!

---

## 🐛 THE BUG BREAKDOWN

### **Current Flow (BROKEN):**

```
1. App Starts
   ├─> CargoMonitor.journal_dir = "C:\Users\...\Saved Games\..."
   └─> ProspectorPanel.journal_dir = "C:\Users\...\Saved Games\..."

2. User Clicks "Change Journal Dir" in Interface Options
   ├─> main._change_journal_dir() called
   ├─> Updates: self.prospector_panel.journal_dir = "D:\CustomPath"
   └─> ❌ DOES NOT UPDATE: self.cargo_monitor.journal_dir
   └─> ❌ DOES NOT SAVE to config.json

3. User Clicks "Import Journal History"
   ├─> _import_journal_history() called
   ├─> Uses: self.cargo_monitor.journal_dir
   └─> ❌ WRONG PATH! Still using hardcoded default!

4. App Restarts
   ├─> CargoMonitor.journal_dir = hardcoded default (no saved config)
   ├─> ProspectorPanel.journal_dir = hardcoded default (no saved config)
   └─> ❌ Custom path LOST!
```

---

## 🔧 SOLUTION ARCHITECTURE

### **What Needs to Happen:**

1. **Save journal_dir to config.json when changed**
   - Add `_save_journal_dir_preference()` function
   - Call it after changing path

2. **Load journal_dir from config.json on startup**
   - Load in `CargoMonitor.__init__()`
   - Load in `ProspectorPanel.__init__()`

3. **Synchronize both objects when path changes**
   - Update BOTH `cargo_monitor.journal_dir` AND `prospector_panel.journal_dir`
   - Keep them in sync

4. **Use consistent path for imports**
   - Either always use cargo_monitor.journal_dir
   - OR always use prospector_panel.journal_dir
   - But ensure they're synchronized!

---

## 📋 PROPOSED FIX DETAILS

### **Step 1: Add Save/Load Functions**

**In config.py (or create helper in main.py):**
```python
def save_journal_dir_preference(journal_dir: str):
    """Save journal directory to config.json"""
    update_config_value("journal_dir", journal_dir)

def load_journal_dir_preference() -> Optional[str]:
    """Load journal directory from config.json"""
    cfg = _load_cfg()
    return cfg.get("journal_dir", None)
```

### **Step 2: Update CargoMonitor Init**

**In CargoMonitor.__init__() (Line 1066):**
```python
# OLD:
self.journal_dir = os.path.expanduser("~\\Saved Games\\...")

# NEW:
from config import load_journal_dir_preference
saved_dir = load_journal_dir_preference()
if saved_dir and os.path.exists(saved_dir):
    self.journal_dir = saved_dir
else:
    self.journal_dir = os.path.expanduser("~\\Saved Games\\...")
```

### **Step 3: Update ProspectorPanel Init**

**In ProspectorPanel.__init__() (Line 398 in prospector_panel.py):**
```python
# OLD:
self.journal_dir = self._detect_journal_dir_default() or ""

# NEW:
from config import load_journal_dir_preference
saved_dir = load_journal_dir_preference()
if saved_dir and os.path.exists(saved_dir):
    self.journal_dir = saved_dir
else:
    self.journal_dir = self._detect_journal_dir_default() or ""
```

### **Step 4: Update _change_journal_dir in main.py**

**In main._change_journal_dir() (Line 5072):**
```python
if sel and os.path.isdir(sel):
    # Update BOTH objects
    if hasattr(self, 'prospector_panel'):
        self.prospector_panel.journal_dir = sel
        self.prospector_panel._jrnl_path = None
        self.prospector_panel._jrnl_pos = 0
    
    # NEW: Also update cargo_monitor
    if hasattr(self, 'cargo_monitor'):
        self.cargo_monitor.journal_dir = sel
        # Update dependent paths
        self.cargo_monitor.cargo_json_path = os.path.join(sel, "Cargo.json")
        self.cargo_monitor.status_json_path = os.path.join(sel, "Status.json")
    
    # NEW: Save to config
    from config import update_config_value
    update_config_value("journal_dir", sel)
    
    # Update the UI label
    if hasattr(self, 'journal_lbl'):
        self.journal_lbl.config(text=sel)
    
    self._set_status("Journal folder updated and saved.")
```

### **Step 5: Update _change_journal_dir in prospector_panel.py**

**In prospector_panel._change_journal_dir() (Line 2902):**
```python
if sel and os.path.isdir(sel):
    self.journal_dir = sel
    self.journal_lbl.config(text=sel)
    self._jrnl_path = None
    self._jrnl_pos = 0
    
    # NEW: Save to config
    from config import update_config_value
    update_config_value("journal_dir", sel)
    
    self._set_status("Journal folder updated and saved.")
```

---

## ✅ EXPECTED BEHAVIOR AFTER FIX

### **Scenario 1: Change Path**
```
1. User clicks "Change…" → selects "D:\CustomPath"
2. ✅ Updates prospector_panel.journal_dir → "D:\CustomPath"
3. ✅ Updates cargo_monitor.journal_dir → "D:\CustomPath"
4. ✅ Saves to config.json: {"journal_dir": "D:\CustomPath"}
5. ✅ UI label shows: "D:\CustomPath"
```

### **Scenario 2: Import History**
```
1. User clicks "Import Journal History"
2. ✅ Uses cargo_monitor.journal_dir → "D:\CustomPath"
3. ✅ Imports from correct location!
```

### **Scenario 3: Restart App**
```
1. App starts
2. ✅ CargoMonitor loads from config → "D:\CustomPath"
3. ✅ ProspectorPanel loads from config → "D:\CustomPath"
4. ✅ UI label shows: "D:\CustomPath"
5. ✅ Path persists!
```

---

## 🎯 FILES TO MODIFY

1. **app/config.py** (or add helpers in main.py)
   - Add `save_journal_dir_preference()`
   - Add `load_journal_dir_preference()`

2. **app/main.py**
   - Line ~1066: Update `CargoMonitor.__init__()`
   - Line ~5072: Update `_change_journal_dir()`

3. **app/prospector_panel.py**
   - Line ~398: Update `__init__()`
   - Line ~2902: Update `_change_journal_dir()`

---

## 🧪 TESTING CHECKLIST

After implementing fix:

- [ ] Change journal path → verify config.json updated
- [ ] Restart app → verify path remembered
- [ ] Import history → verify uses correct path
- [ ] Change path again → verify both objects updated
- [ ] Check UI label → verify shows correct path
- [ ] Default case → verify works when no custom path set

---

*End of Analysis*
