# Journal Path Change - Import Prompt Implementation Plan

**Date:** October 2, 2025  
**Feature:** Show import prompt when user changes journal path

---

## 🎯 REQUIREMENTS

1. ✅ Fix announcer bug (prevent old announcements)
2. ✅ Show popup when user changes journal path
3. ✅ Popup MUST open on same monitor as main window (not secondary monitor)
4. ✅ Use consistent app icon across all windows
5. ✅ Save user preference (don't ask again option)
6. ✅ Clear, user-friendly messaging

---

## 🔧 IMPLEMENTATION STEPS

### **Step 1: Fix Announcer Bug (prospector_panel.py)**

**Location:** Lines 5031-5036 and Line 5054

**Changes:**

```python
# Change 1: Line 5031-5036 - When path changes, seek to end of file
if self._jrnl_path != latest:
    self._jrnl_path = latest
    
    # Skip to end of file to avoid reading old events
    try:
        file_size = os.path.getsize(latest)
        self._jrnl_pos = file_size  # Start at end, not 0!
    except Exception:
        self._jrnl_pos = 0
    
    self._last_mtime = current_mtime
    self._last_size = current_size

# Change 2: Line 5054 - Fix truthiness check
with open(self._jrnl_path, "r", encoding="utf-8") as f:
    if self._jrnl_pos > 0:  # Explicit comparison, not truthiness
        f.seek(self._jrnl_pos)
    new_data = f.read()
```

---

### **Step 2: Add Import Prompt Dialog (main.py)**

**Location:** After `_change_journal_dir()` method

**New Method:**

```python
def _show_journal_import_prompt(self, new_path: str) -> None:
    """Show dialog asking if user wants to import journal history from new path"""
    from config import _load_cfg, update_config_value
    
    # Check if user disabled this prompt
    cfg = _load_cfg()
    if not cfg.get("ask_import_on_path_change", True):
        return  # User disabled the prompt
    
    # Create modal dialog
    dialog = tk.Toplevel(self)
    dialog.title("Import Journal History?")
    dialog.configure(bg="#2c3e50")
    dialog.geometry("500x280")
    dialog.resizable(False, False)
    dialog.transient(self)
    dialog.grab_set()
    
    # Set app icon (consistent across app)
    try:
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(__file__), "app_icon.ico")
        
        if os.path.exists(icon_path):
            dialog.iconbitmap(icon_path)
    except Exception:
        pass  # Icon not critical
    
    # CENTER ON PARENT (SAME MONITOR!)
    dialog.update_idletasks()
    x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
    y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
    dialog.geometry(f"+{x}+{y}")
    
    # Title label
    title_label = tk.Label(
        dialog, 
        text="Import Journal History?",
        bg="#2c3e50", 
        fg="#ecf0f1", 
        font=("Segoe UI", 12, "bold")
    )
    title_label.pack(pady=(20, 10))
    
    # Info text
    info_text = (
        f"You've changed to a new journal folder:\n\n"
        f"{new_path}\n\n"
        f"Would you like to scan these journal files for\n"
        f"hotspot data to add to your database?\n\n"
        f"Note: This will NOT trigger announcements."
    )
    
    info_label = tk.Label(
        dialog,
        text=info_text,
        bg="#2c3e50",
        fg="#bdc3c7",
        font=("Segoe UI", 10),
        justify="center"
    )
    info_label.pack(pady=10)
    
    # Checkbox for "don't ask again"
    dont_ask_var = tk.IntVar(value=0)
    checkbox = tk.Checkbutton(
        dialog,
        text="Don't ask me again when changing paths",
        variable=dont_ask_var,
        bg="#2c3e50",
        fg="#bdc3c7",
        selectcolor="#34495e",
        activebackground="#2c3e50",
        activeforeground="#ecf0f1",
        font=("Segoe UI", 9)
    )
    checkbox.pack(pady=10)
    
    # Button frame
    btn_frame = tk.Frame(dialog, bg="#2c3e50")
    btn_frame.pack(pady=20)
    
    result = {"import": False, "dont_ask": False}
    
    def on_import():
        result["import"] = True
        result["dont_ask"] = bool(dont_ask_var.get())
        dialog.destroy()
    
    def on_skip():
        result["import"] = False
        result["dont_ask"] = bool(dont_ask_var.get())
        dialog.destroy()
    
    # Import button
    import_btn = tk.Button(
        btn_frame,
        text="Import Now",
        command=on_import,
        bg="#27ae60",
        fg="white",
        font=("Segoe UI", 10, "bold"),
        width=12,
        height=1,
        relief=tk.FLAT,
        cursor="hand2"
    )
    import_btn.pack(side=tk.LEFT, padx=10)
    
    # Skip button
    skip_btn = tk.Button(
        btn_frame,
        text="Skip",
        command=on_skip,
        bg="#95a5a6",
        fg="white",
        font=("Segoe UI", 10),
        width=12,
        height=1,
        relief=tk.FLAT,
        cursor="hand2"
    )
    skip_btn.pack(side=tk.LEFT, padx=10)
    
    # Bind Escape key to skip
    dialog.bind('<Escape>', lambda e: on_skip())
    
    # Wait for user response
    dialog.wait_window()
    
    # Save "don't ask again" preference
    if result["dont_ask"]:
        update_config_value("ask_import_on_path_change", False)
    
    # Trigger import if requested
    if result["import"]:
        self._import_journal_history()
```

---

### **Step 3: Update _change_journal_dir() to Call Prompt**

**Location:** main.py, Line ~5095

**Modify:**

```python
def _change_journal_dir(self) -> None:
    """Change the Elite Dangerous journal folder"""
    from tkinter import filedialog
    
    # Get current directory from prospector panel if available
    current_dir = None
    if hasattr(self, 'prospector_panel') and hasattr(self.prospector_panel, 'journal_dir'):
        current_dir = self.prospector_panel.journal_dir
    
    sel = filedialog.askdirectory(
        title="Select Elite Dangerous Journal folder",
        initialdir=current_dir or os.path.expanduser("~")
    )
    
    if sel and os.path.isdir(sel):
        # Update prospector panel if it exists
        if hasattr(self, 'prospector_panel'):
            self.prospector_panel.journal_dir = sel
            self.prospector_panel._jrnl_path = None
            self.prospector_panel._jrnl_pos = 0
        
        # Update cargo_monitor to keep them synchronized
        if hasattr(self, 'cargo_monitor'):
            self.cargo_monitor.journal_dir = sel
            # Update dependent paths in cargo_monitor
            self.cargo_monitor.cargo_json_path = os.path.join(sel, "Cargo.json")
            self.cargo_monitor.status_json_path = os.path.join(sel, "Status.json")
        
        # Save to config.json so it persists across restarts
        from config import update_config_value
        update_config_value("journal_dir", sel)
        
        # Update the UI label
        if hasattr(self, 'journal_lbl'):
            self.journal_lbl.config(text=sel)
        
        self._set_status("Journal folder updated and saved.")
        
        # NEW: Show import prompt (if not disabled)
        self._show_journal_import_prompt(sel)
```

---

### **Step 4: Add Setting to Re-enable Prompt (Interface Options)**

**Location:** main.py, in `_build_interface_options_tab()`

**Add to Interface Options:**

```python
# After journal folder section, add checkbox

# Import prompt preference
r += 1
ttk.Separator(frame, orient="horizontal").grid(
    row=r, column=0, columnspan=3, sticky="ew", pady=10
)

r += 1
import_prompt_label = tk.Label(
    frame,
    text="Journal Import Prompt:",
    bg=BG_COLOR,
    fg=FG_COLOR,
    font=("Segoe UI", 10)
)
import_prompt_label.grid(row=r, column=0, sticky="w", pady=5)

# Checkbox variable
self.ask_import_on_path_change = tk.IntVar()

import_prompt_check = tk.Checkbutton(
    frame,
    text="Ask to import history when changing journal folder",
    variable=self.ask_import_on_path_change,
    command=self._save_import_prompt_preference,
    bg=BG_COLOR,
    fg=FG_COLOR,
    selectcolor="#34495e",
    activebackground=BG_COLOR,
    activeforeground=FG_COLOR,
    font=("Segoe UI", 9)
)
import_prompt_check.grid(row=r, column=1, columnspan=2, sticky="w", pady=5)

# Load preference
cfg = _load_cfg()
self.ask_import_on_path_change.set(1 if cfg.get("ask_import_on_path_change", True) else 0)
```

**Add save method:**

```python
def _save_import_prompt_preference(self) -> None:
    """Save import prompt preference to config"""
    from config import update_config_value
    update_config_value("ask_import_on_path_change", bool(self.ask_import_on_path_change.get()))
```

---

### **Step 5: Use Consistent Icon Helper Function**

**Location:** main.py, at module level

**Add helper function:**

```python
def set_window_icon(window):
    """Set app icon for any tkinter window - consistent across app"""
    try:
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
        else:
            icon_path = os.path.join(os.path.dirname(__file__), "app_icon.ico")
        
        if os.path.exists(icon_path):
            window.iconbitmap(icon_path)
    except Exception:
        pass  # Icon not critical, fail silently
```

**Usage in dialog:**

```python
# In _show_journal_import_prompt():
set_window_icon(dialog)
```

**Update other dialogs to use this helper:**
- `_import_journal_history()` progress window
- `_ask_preset_name()` dialog
- Any other toplevel windows

---

## 📊 CONFIG.JSON STRUCTURE

```json
{
  "journal_dir": "D:\\JournalTestFolder",
  "ask_import_on_path_change": true,
  "tooltips_enabled": true,
  "stay_on_top": false,
  ...
}
```

**Default value:** `true` (ask by default)

---

## 🎨 UI MOCKUP

```
┌──────────────────────────────────────────────┐
│  Import Journal History?                  [X]│
├──────────────────────────────────────────────┤
│                                               │
│           Import Journal History?            │
│                                               │
│  You've changed to a new journal folder:     │
│                                               │
│  D:\JournalTestFolder                        │
│                                               │
│  Would you like to scan these journal files  │
│  for hotspot data to add to your database?   │
│                                               │
│  Note: This will NOT trigger announcements.  │
│                                               │
│  ☐ Don't ask me again when changing paths   │
│                                               │
│        ┌─────────────┐  ┌─────────────┐     │
│        │ Import Now  │  │    Skip     │     │
│        └─────────────┘  └─────────────┘     │
│                                               │
└──────────────────────────────────────────────┘
```

**Colors:**
- Background: #2c3e50 (dark blue-grey)
- Title: #ecf0f1 (white)
- Text: #bdc3c7 (light grey)
- Import button: #27ae60 (green)
- Skip button: #95a5a6 (grey)

---

## ✅ TESTING CHECKLIST

### **Dialog Positioning:**
- [ ] Opens centered on main window
- [ ] Opens on SAME monitor as main window
- [ ] Doesn't open on secondary monitor
- [ ] Modal (blocks main window until closed)

### **Icon Consistency:**
- [ ] Dialog has app icon
- [ ] Import progress window has app icon
- [ ] All toplevel windows use same icon
- [ ] Icon loads in frozen (exe) mode
- [ ] Icon loads in dev mode

### **Functionality:**
- [ ] "Import Now" triggers import
- [ ] "Skip" just closes dialog
- [ ] Checkbox saves preference
- [ ] Setting in Interface Options works
- [ ] Preference persists across restarts

### **Announcer Fix:**
- [ ] Changing path doesn't trigger announcements
- [ ] Old events not read on path change
- [ ] Only NEW events trigger announcements
- [ ] Works on app restart
- [ ] Works on journal file rollover

---

## 📝 FILES TO MODIFY

1. **app/prospector_panel.py**
   - Lines 5031-5036: Fix path change handling
   - Line 5054: Fix truthiness check

2. **app/main.py**
   - Add: `set_window_icon()` helper function
   - Add: `_show_journal_import_prompt()` method
   - Add: `_save_import_prompt_preference()` method
   - Modify: `_change_journal_dir()` to call prompt
   - Modify: `_build_interface_options_tab()` add checkbox
   - Update: All toplevel windows to use `set_window_icon()`

3. **app/config.py**
   - No changes needed (uses existing functions)

---

## 🚀 IMPLEMENTATION ORDER

1. **Step 1:** Add `set_window_icon()` helper
2. **Step 2:** Fix announcer bug (prospector_panel.py)
3. **Step 3:** Create `_show_journal_import_prompt()` method
4. **Step 4:** Update `_change_journal_dir()` to call prompt
5. **Step 5:** Add checkbox to Interface Options
6. **Step 6:** Update existing dialogs to use icon helper
7. **Step 7:** Test all scenarios

---

## ⚠️ IMPORTANT NOTES

### **Window Positioning Formula:**
```python
# Always use this for centering on parent
dialog.update_idletasks()  # ← CRITICAL! Updates geometry
x = self.winfo_x() + (self.winfo_width() // 2) - (dialog.winfo_width() // 2)
y = self.winfo_y() + (self.winfo_height() // 2) - (dialog.winfo_height() // 2)
dialog.geometry(f"+{x}+{y}")
```

**Why this works:**
- `self.winfo_x()` = Parent window X position (handles multi-monitor)
- `self.winfo_y()` = Parent window Y position
- Centers dialog relative to parent, not screen

### **Icon Path Resolution:**
```python
if getattr(sys, 'frozen', False):
    # Running as .exe
    icon_path = os.path.join(sys._MEIPASS, "app_icon.ico")
else:
    # Running in dev mode
    icon_path = os.path.join(os.path.dirname(__file__), "app_icon.ico")
```

**This handles both:**
- Development mode (source files)
- Production mode (PyInstaller exe)

---

**Ready to implement? This plan covers all requirements!** 🎯

---

*End of Implementation Plan*
