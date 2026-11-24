# EliteMining — UI Rules

Detailed UI rules moved out of [AGENTS.md](../AGENTS.md). Read the matching section before creating dialogs, themed widgets, overlays or tables.

## Dialogs and Popups

Every `tk.Toplevel` dialog must follow this order exactly to avoid blinking or freeze on multi-monitor:

1. `dialog.withdraw()` — immediately after `tk.Toplevel()`, before any other setup
2. **No `transient()`** — causes dialogs to hide behind parent and freeze
3. Theme colors from `load_theme()` in `config.py`; use `tk.Frame`/`tk.Label` with explicit `bg`/`fg`, not `ttk`
4. Set icon via `get_app_icon_path()` (`app_utils.py`) in a try/except
5. Add all widgets while dialog is hidden
6. `dialog.update_idletasks()`
7. `center_window(dialog, self.parent.winfo_toplevel())` from `ui/dialogs.py`
8. `dialog.deiconify()`
9. `dialog.attributes('-topmost', True)` → `dialog.lift()` → `dialog.focus_force()`
10. `grab_set()` in a try/except
11. `keep_on_top()` loop — reschedules every 100ms via `dialog.after`

**Exception for dialogs with child popups** (autocomplete list, right-click menu, combobox dropdown, "please wait" `Toplevel`): the loop re-lifts the dialog above its own children and buries them. Either `lift()` once on open instead of looping, or skip `lift()` while any child is open (track an open flag, check `SystemAutocomplete._listbox_toplevel is None`, or `winfo_exists()` on the wait dialog). A non-modal popup without the loop still needs `-topmost` set once at open, because the main window can be always-on-top.

Use `centered_info_dialog` / `centered_yesno_dialog` from `ui/dialogs.py` for standard dialogs — they already implement all of the above.

## Theme Colours and Modern Themes

- Every new widget must use the active theme's colours, never default widget styling. Take colours from the same source as the neighbouring widgets (`load_theme()` / `get_theme_colors()`, or `ttk.Style().lookup(...)` of the parent's style) and set explicit `bg`/`fg`/`selectcolor`/`activebackground` on `tk` widgets such as checkbuttons. A default `ttk.Checkbutton` or similar looks wrong on the Modern and Elite Orange themes. Check new widgets visually in each theme.
- Modern themes (`modern`, `modern_slate`, `modern_orange`): `_modern_recolor_all()` in `app/main.py` only remaps a fixed list of hardcoded greys, once per tab and once per popup, so widgets built or rebuilt later must take their colours from the theme when created. A `tk.Button` with `textvariable` or `image` bypasses `ModernButton` and is never recolored. Use `ttk.Scrollbar`, not `tk.Scrollbar`, in Modern. Gate Modern-only changes on all three theme names so Elite Orange and Dark Gray stay unchanged.

## TextOverlay Window

- It renders wrongly once its size differs from its creation size, so never call `geometry()` with a new size on a live overlay; `show_message()` rebuilds it through `reinstate()` and `_base_size` when the size must change.
- Keep withdraw/deiconify plus `-topmost` True and `lift()`; don't hide it with `-alpha 0` or toggle `-topmost`.
- Diagnose with the `[OVERLAY]` log lines before changing window code.

## Tables

Apply these rules whenever creating a table or changing an existing table's columns or layout:

- **Existing patterns**: inspect the closest table in the app first (especially Ring Finder and Commodity Market). Reuse existing helpers, theme styles, scaled fonts, and spacing; do not create a separate table framework.
- **Alignment**: left-align headers and cells by default (a Treeview can't pad cells, so right-aligned numbers touch the next column); center a column only where it looks clearly better. Pad columns are always centered. Centered today: the two Announcement material tables, the Ring Finder Fav (star), Source and Visits columns, and the Pad column in every table plus the Commodity Market Updated column (Mining, Multiple Prices, Trade and Sell My Hold).
- **Headers and minimum widths**: use short, localized headers consistent with matching columns in other tabs. Each column's minimum width is its translated header measured with the scaled heading font plus scaled padding. Default, restored, and shown-again widths must respect that minimum.
- **Manual resizing**: use `stretch=False` for data columns so Tk does not redistribute their widths. Do not impose a maximum width or reset the user's width during refresh or layout changes. If a table needs an expanding filler column, follow the existing Ring Finder pattern.
- **Scrolling**: provide working horizontal and vertical scrollbars so wide columns and rows beyond the visible height remain reachable.
- **Visibility and ordering**: reuse `ColumnVisibilityMixin` from `app/column_visibility_helper.py` where the table offers column controls. Use `use_displaycolumns=True` to fully hide columns (`width=0` leaves a visible text sliver), and resolve clicked or hovered columns with `displayed_column()` rather than fixed display indices. Reuse existing reorder support where applicable.
- **Persistence**: follow existing column-width, visibility, and order persistence through `app/config.py`. Save user resizing and restore it without clipping translated headers; keep hidden columns hidden.
- **Number formatting**: match equivalent columns in existing tabs. LS uses Ring Finder's whole-number format with thousands separators (`f'{int(float(value)):,}'`); LY uses the existing distance precision. Keep unknown values distinct from zero and sort numeric columns by their underlying numeric values.
- **Localization and scale**: use both English and German strings and the app's UI scale helpers; do not hardcode new user-visible labels or unscaled table dimensions.

For new tables, substantial table changes, or shared table-helper changes, verify the full applicable checklist below. For localized changes, check only affected behavior and credible regressions: a header wording change needs translated-header and minimum-width checks, but does not by itself require retesting unchanged ordering or persistence.

1. Drag columns wider and narrower: widths remain stable after release, result refresh, and window resizing; headers remain readable at the minimum width.
2. Scroll horizontally through wide columns and vertically through all rows.
3. Save and reopen the table: widths, visibility, and supported ordering restore correctly.
4. Hide, show, and reorder columns where supported: no text slivers, incorrect context menus, or mismatched tooltips.
5. Check English and German headers, supported UI scales, and number formatting, including fractional LS, zero, and missing data.

Report applicable checks that could not be run; do not claim visual verification from code inspection alone.
