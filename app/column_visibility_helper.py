"""
Column Visibility Helper
Provides reusable column visibility functionality for all tables in EliteMining
"""

import tkinter as tk
from typing import Dict, Callable
from localization import t


def displayed_column(tree, column_id):
    """Column name for an identify_column() result such as '#3', resolved against the
    columns actually displayed (honours displaycolumns). None if out of range."""
    displayed = tree['displaycolumns']
    names = tree['columns'] if displayed in ('#all', ('#all',)) else displayed
    try:
        return names[int(column_id[1:]) - 1]
    except (ValueError, IndexError):
        return None


class ColumnVisibilityMixin:
    """
    Mixin class to add column visibility functionality to any table.
    
    Usage:
    1. Add to your class: class MyTable(ColumnVisibilityMixin):
    2. Call setup_column_visibility() after creating your treeview
    3. Supports multiple trees in same class by using config_key as namespace
    """
    
    def setup_column_visibility(self, tree, columns, default_widths, config_key, use_displaycolumns=False, on_change=None, allow_reorder=False):
        """
        Setup column visibility for a treeview

        Args:
            tree: The ttk.Treeview widget
            columns: List/tuple of column identifiers
            default_widths: Dict mapping column names to default widths
            config_key: Unique key for saving preferences (e.g., 'prospector_report')
            use_displaycolumns: If True, hide columns via the Treeview's displaycolumns
                (fully removes them from layout) instead of width=0 (which can leave a
                rendering sliver that bleeds into the next visible column on Windows).
                Callers using this must resolve identify_column() results against
                tree['displaycolumns'], not tree['columns'].
            on_change: Optional zero-arg callable run after the user toggles a column
                or resets visibility (e.g. to resize the containing window).
        """
        # Store per-tree data using config_key as namespace
        if not hasattr(self, '_cv_trees'):
            self._cv_trees = {}

        # Capture original stretch values before any visibility changes
        original_stretch = {}
        for col in columns:
            try:
                original_stretch[col] = tree.column(col, 'stretch')
            except Exception:
                original_stretch[col] = False

        self._cv_trees[config_key] = {
            'tree': tree,
            'columns': columns,
            'default_widths': default_widths,
            'visible': {col: True for col in columns},
            'saved_widths': {},  # Store actual widths before hiding
            'original_stretch': original_stretch,  # Store original stretch per column
            'excluded_from_menu': set(),  # Columns hidden from the visibility menu
            'force_hidden': set(),  # Columns force-hidden by app logic, independent of user visibility pref
            'use_displaycolumns': use_displaycolumns,
            'on_change': on_change,
            'allow_reorder': allow_reorder,
        }
        
        # Bind right-click with config_key context
        tree.bind("<Button-3>", lambda e, key=config_key: self._cv_handle_right_click(e, key))
        
        # Load saved visibility
        self._cv_load_visibility(config_key)
        if allow_reorder:
            from config import load_column_order
            self._cv_set_order(config_key, load_column_order(config_key), save=False)
    
    def _cv_add_columns_button(self, parent, config_key, **grid_options):
        from config import load_theme, scaled_font, scaled_px
        from ui.modern_widgets import RoundedButton

        def show_columns():
            self._cv_show_order_dialog(config_key)

        if load_theme() in ("modern", "modern_slate", "modern_orange"):
            button = RoundedButton(parent, text=t('ring_finder.columns_button'),
                                   command=show_columns, font=scaled_font(9),
                                   padx=scaled_px(10), pady=scaled_px(4))
        else:
            from ui.theme import get_theme_colors
            colors = get_theme_colors(load_theme())
            button = tk.Button(parent, text=t('ring_finder.columns_button'),
                               command=show_columns, font=scaled_font(8), cursor="hand2",
                               bg=colors['btn_bg'], fg=colors['btn_fg'],
                               activebackground=colors['btn_bg_hover'], activeforeground=colors['btn_fg'],
                               padx=scaled_px(6), pady=scaled_px(2), relief="ridge", bd=1)
        if grid_options:
            button.grid(**grid_options)
        else:
            button.pack(side="right", padx=(scaled_px(8), 0))
        return button

    def _cv_handle_right_click(self, event, config_key):
        """Route row right-clicks to the table's context menu."""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        tree = tree_data['tree']
        region = tree.identify_region(event.x, event.y)
        
        if region == "heading" or event.y <= 25:
            return
        
        # Otherwise, call the original context menu if it exists
        # For tables with their own context menus, look for specific handlers
        context_handler = None
        
        # Check for tree-specific context menu handlers
        if hasattr(self, '_context_handlers') and config_key in self._context_handlers:
            context_handler = self._context_handlers[config_key]
        elif hasattr(self, '_original_context_menu'):
            context_handler = self._original_context_menu
        
        if context_handler:
            context_handler(event)
    
    @staticmethod
    def _cv_clean_heading(text):
        """Heading text without a trailing sort arrow (" ▲" / " ▼")."""
        return text[:-2] if text.endswith((" ▲", " ▼")) else text

    def _cv_apply_displaycolumns(self, config_key):
        """Rebuild the tree's displaycolumns from current visibility state (use_displaycolumns mode)."""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data or not tree_data.get('use_displaycolumns'):
            return
        tree = tree_data['tree']
        columns = tree_data['columns']
        visible = tree_data['visible']
        force_hidden = tree_data.get('force_hidden', set())
        full_columns = tree_data.get('order', tree['columns'])
        shown = [col for col in full_columns
                 if col not in columns or (visible.get(col, True) and col not in force_hidden)]
        tree.configure(displaycolumns=shown)

    def _cv_set_order(self, config_key, order, save=True):
        tree_data = self._cv_trees[config_key]
        columns = list(tree_data['tree']['columns'])
        configurable = tree_data['columns']
        tree_data['order'] = [col for col in dict.fromkeys(list(order) + columns) if col in configurable]
        tree_data['order'].extend(col for col in columns if col not in configurable)
        self._cv_apply_displaycolumns(config_key)
        if save:
            from config import save_column_order
            save_column_order(config_key, tree_data['order'])

    def _cv_show_order_dialog(self, config_key):
        from config import load_theme, scaled_font, scaled_px
        from tkinter import ttk
        from ui.theme import get_theme_colors
        from ui.dialogs import center_window
        from app_utils import get_app_icon_path

        tree_data = self._cv_trees[config_key]
        tree = tree_data['tree']
        colors = get_theme_colors(load_theme())
        order = list(tree_data['order'])
        visible = tree_data['visible'].copy()
        excluded = tree_data['excluded_from_menu'] | tree_data['force_hidden']
        editable = set(tree_data['columns']) - excluded
        parent = tree.winfo_toplevel()
        previous_grab = parent.grab_current()
        dialog = tk.Toplevel(parent)
        dialog.withdraw()
        dialog.title(t('column_order.title'))
        dialog.configure(bg=colors['bg'])
        dialog.resizable(False, False)
        keep_on_top_job = None

        def close():
            if keep_on_top_job is not None:
                dialog.after_cancel(keep_on_top_job)
            dialog.destroy()

        dialog.protocol('WM_DELETE_WINDOW', close)
        try:
            icon = get_app_icon_path()
            if icon:
                dialog.iconbitmap(icon)
        except Exception:
            pass

        content = tk.Frame(dialog, bg=colors['bg'])
        content.pack(padx=scaled_px(16), pady=scaled_px(12))
        tk.Label(content, text=t('column_order.description'), bg=colors['bg'], fg=colors['fg'],
                 font=scaled_font(9)).pack(anchor="w", pady=(0, scaled_px(8)))
        list_frame = tk.Frame(content, bg=colors['bg'])
        list_frame.pack(fill="both", expand=True)
        listing = ttk.Treeview(list_frame, columns=('visible',), show='tree headings',
                               height=12, selectmode='browse')
        listing.heading('#0', text=t('column_order.column'), anchor='w')
        listing.heading('visible', text=t('column_order.visible'), anchor='center')
        listing.column('#0', width=scaled_px(240), minwidth=scaled_px(180))
        listing.column('visible', width=scaled_px(80), minwidth=scaled_px(70), stretch=False, anchor='center')
        listing.pack(side="left", fill="both", expand=True)
        scrollbar = tk.Scrollbar(list_frame, command=listing.yview)
        scrollbar.pack(side="right", fill="y")
        listing.configure(yscrollcommand=scrollbar.set)
        controls = tk.Frame(content, bg=colors['bg'])
        controls.pack(fill="x", pady=(scaled_px(8), 0))

        def populate(selected=None):
            listing.delete(*listing.get_children())
            for col in order:
                if col in editable:
                    listing.insert('', tk.END, iid=col,
                                   text=self._cv_clean_heading(tree.heading(col, 'text')),
                                   values=('☑' if visible[col] else '☐',))
            rows = listing.get_children()
            if rows:
                selected = selected if selected in rows else rows[0]
                listing.selection_set(selected)
                listing.focus(selected)
                listing.see(selected)
            update_buttons()

        def update_buttons(event=None):
            selected = listing.selection()
            rows = listing.get_children()
            index = rows.index(selected[0]) if selected else -1
            left_button.configure(state="normal" if index > 0 else "disabled")
            right_button.configure(state="normal" if 0 <= index < len(rows) - 1 else "disabled")

        def move(direction):
            selected = listing.selection()
            if not selected:
                return
            rows = listing.get_children()
            index = rows.index(selected[0])
            target = index + direction
            if 0 <= target < len(rows):
                source_index, target_index = order.index(rows[index]), order.index(rows[target])
                order[source_index], order[target_index] = order[target_index], order[source_index]
                populate(selected[0])

        def toggle_visible(column):
            visible[column] = not visible[column]
            populate(column)

        def on_click(event):
            column = listing.identify_row(event.y)
            if column and listing.identify_column(event.x) == '#1':
                toggle_visible(column)
                return "break"

        def on_space(event):
            selected = listing.selection()
            if selected:
                toggle_visible(selected[0])
            return "break"

        def reset_defaults():
            order[:] = tree['columns']
            visible.update({col: True for col in editable})
            populate()

        def apply_order():
            tree_data['visible'].update({col: visible[col] for col in editable})
            self._cv_set_order(config_key, order)
            self._cv_save_visibility(config_key)
            close()

        def button(parent, text, command):
            return tk.Button(parent, text=text, command=command, bg=colors['btn_bg'], fg=colors['btn_fg'],
                             activebackground=colors['btn_bg_hover'], activeforeground=colors['btn_fg'],
                             font=scaled_font(9), padx=scaled_px(8), pady=scaled_px(3), cursor="hand2")

        left_button = button(controls, t('column_order.move_left'), lambda: move(-1))
        left_button.pack(side="left")
        right_button = button(controls, t('column_order.move_right'), lambda: move(1))
        right_button.pack(side="left", padx=(scaled_px(6), 0))
        button(controls, t('column_order.reset'), reset_defaults).pack(side="right", padx=(scaled_px(12), 0))
        actions = tk.Frame(content, bg=colors['bg'])
        actions.pack(fill="x", pady=(scaled_px(12), 0))
        button(actions, t('common.cancel'), close).pack(side="right")
        button(actions, t('common.apply'), apply_order).pack(side="right", padx=(0, scaled_px(6)))
        listing.bind('<<TreeviewSelect>>', update_buttons)
        listing.bind('<Button-1>', on_click)
        listing.bind('<space>', on_space)
        populate()
        dialog.update_idletasks()
        center_window(dialog, tree.winfo_toplevel())
        previous_menu_state = getattr(parent, '_row_menu_open', False)
        parent._row_menu_open = True
        dialog.deiconify()
        dialog.attributes('-topmost', True)
        dialog.lift()
        dialog.focus_force()
        try:
            dialog.grab_set()
        except tk.TclError:
            pass

        def keep_on_top():
            nonlocal keep_on_top_job
            if dialog.winfo_exists():
                dialog.lift()
                keep_on_top_job = dialog.after(100, keep_on_top)

        keep_on_top_job = dialog.after(100, keep_on_top)
        try:
            dialog.wait_window()
        finally:
            parent._row_menu_open = previous_menu_state
            if previous_grab is not None and previous_grab.winfo_exists():
                try:
                    previous_grab.grab_set()
                except tk.TclError:
                    pass

    def _cv_set_force_hidden(self, config_key, column, hidden: bool):
        """Force a column out of the display regardless of the user's saved visibility
        preference (e.g. hiding PowerPlay when Data Source can't provide PowerPlay data).
        Does not touch the saved 'visible' preference, so it's restored as-is when unhidden."""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        force_hidden = tree_data.setdefault('force_hidden', set())
        if hidden:
            force_hidden.add(column)
        else:
            force_hidden.discard(column)
        self._cv_apply_displaycolumns(config_key)

    def _cv_toggle(self, column, config_key):
        """Toggle column visibility"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        tree = tree_data['tree']
        visible = tree_data['visible']
        default_widths = tree_data['default_widths']
        saved_widths = tree_data['saved_widths']
        
        is_visible = visible.get(column, True)
        visible[column] = not is_visible

        if tree_data.get('use_displaycolumns'):
            if not visible[column]:
                current_width = tree.column(column, "width")
                if current_width > 0:
                    saved_widths[column] = current_width
            self._cv_apply_displaycolumns(config_key)
            self._cv_save_visibility(config_key)
            return

        if visible[column]:
            # Show column - restore saved width or default, and original stretch
            width_to_restore = saved_widths.get(column, default_widths[column])
            orig_stretch = tree_data.get('original_stretch', {}).get(column, False)
            from config import scaled_px
            tree.column(column, width=width_to_restore, minwidth=scaled_px(50), stretch=orig_stretch)
        else:
            # Hide column - save current width first, then set to 0
            current_width = tree.column(column, "width")
            if current_width > 0:
                saved_widths[column] = current_width
            tree.column(column, width=0, minwidth=0, stretch=False)

        self._cv_save_visibility(config_key)
    
    def _cv_reset(self, config_key):
        """Reset all columns to visible (keep current widths)"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        tree = tree_data['tree']
        columns = tree_data['columns']
        visible = tree_data['visible']
        default_widths = tree_data['default_widths']

        if tree_data.get('use_displaycolumns'):
            for col in columns:
                visible[col] = True
                if tree.column(col, "width") == 0:
                    orig_stretch = tree_data.get('original_stretch', {}).get(col, False)
                    from config import scaled_px
                    tree.column(col, width=default_widths[col], minwidth=scaled_px(50), stretch=orig_stretch)
            self._cv_apply_displaycolumns(config_key)
            self._cv_save_visibility(config_key)
            return

        for col in columns:
            visible[col] = True
            current_width = tree.column(col, "width")
            if current_width == 0:
                # Column was hidden, restore default width and original stretch
                orig_stretch = tree_data.get('original_stretch', {}).get(col, False)
                tree.column(col, width=default_widths[col], minwidth=50, stretch=orig_stretch)

        self._cv_save_visibility(config_key)
    
    def _cv_set_excluded(self, config_key, column, exclude: bool):
        """Add or remove a column from the visibility menu without affecting its visible state."""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        excluded = tree_data['excluded_from_menu']
        if exclude:
            excluded.add(column)
        else:
            excluded.discard(column)

    def _cv_save_visibility(self, config_key):
        """Save column visibility preferences"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        try:
            from config import save_column_visibility
            save_column_visibility(config_key, tree_data['visible'])
        except Exception as e:
            print(f"[DEBUG] Could not save column visibility for {config_key}: {e}")
        if tree_data.get('on_change'):
            tree_data['on_change']()
    
    def _cv_load_visibility(self, config_key):
        """Load column visibility preferences"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        try:
            from config import load_column_visibility
            saved = load_column_visibility(config_key)
            if saved:
                tree = tree_data['tree']
                visible = tree_data['visible']
                use_displaycolumns = tree_data.get('use_displaycolumns')
                for col, vis in saved.items():
                    if col in visible:
                        visible[col] = vis
                        if not vis and not use_displaycolumns:
                            tree.column(col, width=0, minwidth=0, stretch=False)
                if use_displaycolumns:
                    self._cv_apply_displaycolumns(config_key)

                # Schedule a delayed re-application to handle cases where
                # column widths are loaded after visibility setup
                tree.after(100, lambda: self._cv_reapply_visibility(config_key))
        except Exception as e:
            print(f"[DEBUG] Could not load column visibility for {config_key}: {e}")
    
    def _cv_reapply_visibility(self, config_key):
        """Re-apply visibility settings after initialization is complete"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        tree = tree_data['tree']
        visible = tree_data['visible']

        if tree_data.get('use_displaycolumns'):
            self._cv_apply_displaycolumns(config_key)
            return

        for col, vis in visible.items():
            if not vis:
                tree.column(col, width=0, minwidth=0, stretch=False)
