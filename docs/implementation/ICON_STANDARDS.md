# Icon Handling Standards for EliteMining

## Overview
To prevent path issues with app icons across different deployment scenarios (development vs installer), all code should use the centralized `icon_utils.py` module.

## Standard Practices

### ✅ DO - Use Centralized Icon Utilities

```python
# For new windows/dialogs (PREFERRED METHOD)
from icon_utils import set_window_icon

dialog = tk.Toplevel()
set_window_icon(dialog)  # Automatically handles everything

# For cases where you need the icon path
from icon_utils import get_app_icon_path

icon_path = get_app_icon_path()
if icon_path:
    window.iconbitmap(icon_path)
```

### ❌ DON'T - Create Custom Icon Path Logic

```python
# DON'T DO THIS - fragile path logic
icon_path = os.path.join(os.path.dirname(__file__), "..", "logo.ico")

# DON'T DO THIS - hardcoded paths
icon_path = "Images/logo.ico" 

# DON'T DO THIS - duplicate search functions
def find_my_icon():  # Creates maintenance burden
    # ... custom search logic
```

## Migration Checklist

When adding new windows/dialogs:

1. ✅ Import `from icon_utils import set_window_icon`
2. ✅ Call `set_window_icon(your_window)` after creating the window
3. ✅ No need for custom icon path logic

When modifying existing code:

1. ✅ Replace custom icon path functions with `get_app_icon_path()`
2. ✅ Replace manual icon setting with `set_window_icon()`
3. ✅ Remove duplicate icon search logic
4. ✅ Test in both development and installer modes

## Benefits

- **Consistency**: All windows have the same icon handling
- **Maintainability**: Single place to fix icon path issues
- **Reliability**: Handles all deployment scenarios automatically
- **Simplicity**: One function call instead of complex path logic

## Files Using Icon Utils

Current files that should use the centralized approach:
- `main.py` - Main application and dialogs
- `prospector_panel.py` - Prospector dialogs and windows
- `ring_finder.py` - Ring finder dialogs (if any)
- Any new modules with GUI components

## Testing Requirements

When making icon-related changes:
1. ✅ Test in development mode (`python main.py`)
2. ✅ Test in installer mode (compiled executable)
3. ✅ Verify icon appears in all dialogs/windows
4. ✅ Check for any error messages related to icon loading

## Emergency Fallback

If icon loading fails, the `set_window_icon()` function gracefully fails without crashing the application. The window will simply use the default system icon.