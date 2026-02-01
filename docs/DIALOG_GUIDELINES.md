# Dialog and Popup Window Guidelines

## Overview
All popup dialogs and windows in EliteMining must be centered on the main application window for a consistent user experience.

## Required Steps for Creating a Dialog

### 1. Create the Dialog
```python
dialog = tk.Toplevel(self)
dialog.withdraw()  # CRITICAL: Hide immediately to prevent blinking on wrong monitor
dialog.title("Dialog Title")
# NOTE: Do NOT use transient() - it can cause dialog to hide behind parent on multi-monitor setups
# dialog.transient(self)  # DEPRECATED - causes freeze issues
dialog.resizable(False, False)  # Optional: prevent resizing
# Note: Do NOT call grab_set() yet - wait until after centering and showing
```

### 2. Set the App Icon
```python
from app_utils import get_app_icon_path

try:
    icon_path = get_app_icon_path()
    if icon_path and icon_path.endswith('.ico'):
        dialog.iconbitmap(icon_path)
except:
    pass
```

### 3. Configure Theme Colors
```python
from config import load_theme

theme = load_theme()
if theme == "elite_orange":
    bg_color = "#000000"
    fg_color = "#ff8c00"
    btn_bg = "#1a1a1a"
    btn_fg = "#ff9900"
else:
    bg_color = "#1e1e1e"
    fg_color = "#569cd6"
    btn_bg = "#2a3a4a"
    btn_fg = "#e0e0e0"

dialog.configure(bg=bg_color)
```

### 4. Add Widgets
```python
main_frame = tk.Frame(dialog, bg=bg_color, padx=20, pady=15)
main_frame.pack(fill="both", expand=True)

# Add your widgets here...
tk.Label(main_frame, text="Content", bg=bg_color, fg=fg_color).pack()
```

### 5. Center and Show the Dialog (CRITICAL!)
```python
# IMPORTANT: Always call update_idletasks() before centering
dialog.update_idletasks()
self._center_dialog_on_parent(dialog)

# CRITICAL: Show dialog AFTER centering to prevent blinking on wrong monitor
dialog.deiconify()  # Show the dialog in its final position

# Keep dialog visible and on top (prevents freeze on multi-monitor)
dialog.attributes('-topmost', True)
dialog.lift()
dialog.focus_force()

try:
    dialog.grab_set()   # Grab focus (for modal dialogs)
except:
    pass  # grab_set can fail if another grab is active

# Keep dialog on top during wait (CRITICAL for multi-monitor setups)
def keep_on_top():
    try:
        if dialog.winfo_exists():
            dialog.lift()
            dialog.after(100, keep_on_top)
    except:
        pass
dialog.after(100, keep_on_top)

dialog.wait_window()  # Wait for dialog to close
```

## Complete Example

```python
def _show_example_dialog(self) -> None:
    """Show an example dialog properly centered on parent"""
    from config import load_theme
    from app_utils import get_app_icon_path
    
    # Theme colors
    theme = load_theme()
    bg = "#000000" if theme == "elite_orange" else "#1e1e1e"
    fg = "#ff8c00" if theme == "elite_orange" else "#e0e0e0"
    
    # Create dialog
    dialog = tk.Toplevel(self)
    dialog.withdraw()  # Hide immediately to prevent blinking on wrong monitor
    dialog.title("Example Dialog")
    dialog.configure(bg=bg)
    dialog.resizable(False, False)
    dialog.transient(self)
    
    # Set icon
    try:
        icon_path = get_app_icon_path()
        if icon_path and icon_path.endswith('.ico'):
            dialog.iconbitmap(icon_path)
    except:
        pass
    
    # Main content
    frame = tk.Frame(dialog, bg=bg, padx=20, pady=15)
    frame.pack(fill="both", expand=True)
    
    tk.Label(frame, text="Example Content", bg=bg, fg=fg, 
             font=("Segoe UI", 11)).pack(pady=10)
    
    tk.Button(frame, text="OK", command=dialog.destroy,
              bg="#2a2a2a", fg=fg, padx=20, pady=3).pack(pady=10)
    
    # CRITICAL: Center on parent window
    dialog.update_idletasks()
    self._center_dialog_on_parent(dialog)
    dialog.deiconify()  # Show dialog after centering to prevent blinking
    dialog.grab_set()   # Grab focus after showing
    
    dialog.focus_set()
```

## The `_center_dialog_on_parent` Method

This method is defined in `main.py` in the `App` class:

```python
def _center_dialog_on_parent(self, dialog) -> None:
    """Center a dialog window on the main application window."""
    # Force geometry update to get accurate dimensions
    dialog.update()
    
    # Get main window position and size
    main_x = self.winfo_x()
    main_y = self.winfo_y()
    main_width = self.winfo_width()
    main_height = self.winfo_height()
    
    # Get dialog size - try reqwidth first, fall back to actual width
    dialog_width = dialog.winfo_reqwidth()
    dialog_height = dialog.winfo_reqheight()
    
    # If reqwidth returned too small, use actual dimensions
    if dialog_width < 50:
        dialog_width = dialog.winfo_width()
    if dialog_height < 50:
        dialog_height = dialog.winfo_height()
    
    # If still too small, use reasonable defaults
    if dialog_width < 50:
        dialog_width = 400
    if dialog_height < 50:
        dialog_height = 300
    
    # Calculate centered position relative to main window
    # DO NOT apply screen bounds - we want it on the same monitor as main window
    x = main_x + (main_width - dialog_width) // 2
    y = main_y + (main_height - dialog_height) // 2
    
    # Apply position with explicit size
    dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
```

**Important for Multi-Monitor Setups:**
- DO NOT use `winfo_screenwidth()` or `winfo_screenheight()` to clamp positions
- These return total virtual screen size, not individual monitor dimensions
- This causes dialogs to appear on wrong monitors
- Always position relative to parent window without screen bounds checking

## Multi-Monitor Dialog Blinking Prevention

**Problem:** Dialogs briefly flash on the wrong monitor before appearing in the correct position.

**Root Cause:** `tk.Toplevel()` creates dialogs visible by default, usually on the primary monitor. When you then center/position the dialog, it moves from the primary monitor to the correct monitor, causing a visible "blink" or "flash".

**Solution:** The withdraw/deiconify pattern:

```python
# 1. Create and IMMEDIATELY hide the dialog
dialog = tk.Toplevel(self)
dialog.withdraw()  # Hide before it appears on screen

# 2. Configure and build the dialog
dialog.title("My Dialog")
dialog.configure(bg=bg_color)
# ... add all widgets ...

# 3. Center the dialog (while still hidden)
dialog.update_idletasks()
self._center_dialog_on_parent(dialog)

# 4. Show the dialog in its final position
dialog.deiconify()  # Now it appears only once, in the correct location
dialog.grab_set()   # Grab focus after showing
```

**Key Points:**
- Call `withdraw()` immediately after creating the Toplevel
- Build all widgets while the dialog is hidden
- Center the dialog while hidden
- Call `deiconify()` only after centering is complete
- Call `grab_set()` after `deiconify()` to ensure proper focus

This ensures the dialog appears instantly in the correct position without any visible movement or flashing.

## Common Mistakes to Avoid

1. **Forgetting `withdraw()`** - Dialog will blink on wrong monitor in multi-monitor setups
2. **Calling `grab_set()` before `deiconify()`** - Can cause focus issues; always grab after showing
3. **Forgetting `update_idletasks()`** - Dialog dimensions will be 1x1 if you don't call this first
4. **Centering before adding widgets** - Always add all widgets BEFORE centering
5. **Using `winfo_width()` instead of `winfo_reqwidth()`** - Use `reqwidth` for initial sizing
6. **Using `transient(self)`** - Can cause dialog to hide behind parent on multi-monitor setups, leading to app freeze
7. **Hardcoding colors** - Always use theme-aware colors from `load_theme()`
8. **Missing `keep_on_top()` loop** - Dialog may hide behind parent, causing freeze

## Why Dialogs Can Freeze the App

When a modal dialog with `wait_window()` hides behind the main window:

1. **`wait_window()` is blocking** - It waits for the dialog to be destroyed
2. **User can't see or click the hidden dialog** - No way to close it
3. **`grab_set()` captures all input** - Clicks on main window are captured but can't be processed
4. **Main thread is blocked** - Entire app becomes unresponsive

**Solution:** Use the `keep_on_top()` pattern:
```python
def keep_on_top():
    try:
        if dialog.winfo_exists():
            dialog.lift()
            dialog.after(100, keep_on_top)
    except:
        pass
dialog.after(100, keep_on_top)
```

This ensures the dialog stays visible even if the user clicks on the main window.

## Checklist for New Dialogs

- [ ] Create with `tk.Toplevel(self)`
- [ ] **Immediately call `dialog.withdraw()` to prevent blinking**
- [ ] **Do NOT use `transient(self)`** - causes hiding issues on multi-monitor
- [ ] Set app icon with `get_app_icon_path()`
- [ ] Use theme colors from `load_theme()`
- [ ] Add all widgets before centering
- [ ] Call `update_idletasks()` before centering
- [ ] Call `self._center_dialog_on_parent(dialog)`
- [ ] **Call `dialog.deiconify()` to show dialog after centering**
- [ ] Set `dialog.attributes('-topmost', True)` and `dialog.lift()`
- [ ] **Add `keep_on_top()` loop to prevent freeze**
- [ ] **Call `dialog.grab_set()` in try/except after deiconify**
- [ ] Add localization keys to both `strings_en.json` and `strings_de.json`
