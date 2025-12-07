# Dialog and Popup Window Guidelines

## Overview
All popup dialogs and windows in EliteMining must be centered on the main application window for a consistent user experience.

## Required Steps for Creating a Dialog

### 1. Create the Dialog
```python
dialog = tk.Toplevel(self)
dialog.title("Dialog Title")
dialog.transient(self)  # Keep on top of parent
dialog.grab_set()       # Make modal (optional, for blocking dialogs)
dialog.resizable(False, False)  # Optional: prevent resizing
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

### 5. Center the Dialog (CRITICAL!)
```python
# IMPORTANT: Always call update_idletasks() before centering
dialog.update_idletasks()
self._center_dialog_on_parent(dialog)

# Set focus
dialog.focus_set()
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
    dialog.title("Example Dialog")
    dialog.configure(bg=bg)
    dialog.resizable(False, False)
    dialog.transient(self)
    dialog.grab_set()
    
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

## Common Mistakes to Avoid

1. **Forgetting `update_idletasks()`** - Dialog dimensions will be 1x1 if you don't call this first
2. **Centering before adding widgets** - Always add all widgets BEFORE centering
3. **Using `winfo_width()` instead of `winfo_reqwidth()`** - Use `reqwidth` for initial sizing
4. **Not using `transient(self)`** - Dialog may appear behind main window
5. **Hardcoding colors** - Always use theme-aware colors from `load_theme()`

## Checklist for New Dialogs

- [ ] Create with `tk.Toplevel(self)`
- [ ] Set `transient(self)` for proper window stacking
- [ ] Set app icon with `get_app_icon_path()`
- [ ] Use theme colors from `load_theme()`
- [ ] Add all widgets before centering
- [ ] Call `update_idletasks()` before centering
- [ ] Call `self._center_dialog_on_parent(dialog)`
- [ ] Set focus with `dialog.focus_set()`
- [ ] Add localization keys to both `strings_en.json` and `strings_de.json`
