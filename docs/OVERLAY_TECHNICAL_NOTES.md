# Overlay Technical Notes

## Architecture

Two overlay classes in `main.py`:
- **TextOverlay** — event-driven (mining events, prospector results). Shows temporarily, auto-hides after duration.
- **CargoTextOverlay** — persistent. Updates every 2 seconds while enabled.

Both render on the **game monitor** using `get_game_monitor_offset()` which finds the Elite Dangerous window via `EnumWindows`.

## Critical Rules

### TextOverlay: Must use `withdraw()` / `deiconify()`
- `withdraw()` to hide, `deiconify()` to show
- **Must call `_set_window_position()` after `_fit_window_to_content()` every time before showing** — Windows can reset the window position to the parent app's monitor otherwise
- Do NOT use `wm_attributes("-alpha", 0/1)` for TextOverlay — `deiconify()` after `withdraw()` combined with `_set_window_position()` is the only pattern that reliably places it on the correct monitor

### CargoTextOverlay: Must use `wm_attributes("-alpha", 0/1)`
- `alpha=0` to hide, `alpha=1` to show
- Uses a **fixed-size window** (700x600) with transparent background (`#000001` + `-transparentcolor`)
- Text is right-aligned (`anchor="ne"`, `justify="left"`) so it hugs the right edge of the screen
- Do NOT use `withdraw()` / `deiconify()` for CargoTextOverlay — it causes position drift on multi-monitor setups

### Font Size Changes (CargoTextOverlay)
- Clear canvas items (`canvas.delete("all")`) and reset `_outline_items = []`
- Do NOT call `canvas.config(width=, height=)` — tkinter caches geometry internally and won't shrink back
- Do NOT use `_fit_window_to_content()` with dynamic resizing — the fixed-size transparent window approach eliminates all sizing bugs

## Game Focus / Visibility Logic

The periodic update loop (`_periodic_integrated_cargo_update`) manages overlay visibility:

### When "Only show when game focused" is ENABLED:
- **Game focused** → show overlays (`_game_hidden = False`)
- **Game not focused** → hide overlays (`_game_hidden = True`)

### When "Only show when game focused" is DISABLED:
- **Game window exists** → show overlays (`_game_hidden = False`)
- **Game not running** → hide overlays (`_game_hidden = True`)
- Overlays should NEVER show when the game is not running

## DPI Awareness

- Uses `SetProcessDpiAwareness(1)` = System DPI Aware (locks to primary monitor DPI at startup)
- `SetProcessDpiAwareness(2)` (Per-Monitor) is NOT safe with tkinter
- DPI or resolution changes require app restart — documented in README Known Limitations

## Multi-Monitor Debugging Checklist

If overlays stop appearing on the correct monitor:
1. Verify `_find_game_window_rect()` returns valid coordinates
2. Verify `_set_window_position()` is called AFTER `_fit_window_to_content()` in TextOverlay's `show_message()`
3. Check that `_game_hidden` flag is being set/cleared correctly in the periodic update loop
4. Confirm the correct show/hide method is used for each overlay type (see Critical Rules above)
