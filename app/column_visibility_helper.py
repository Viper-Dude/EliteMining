"""
Column Visibility Helper
Provides reusable column visibility functionality for all tables in EliteMining
"""

import tkinter as tk
from typing import Dict, Callable
from localization import t


class ColumnVisibilityMixin:
    """
    Mixin class to add column visibility functionality to any table.
    
    Usage:
    1. Add to your class: class MyTable(ColumnVisibilityMixin):
    2. Call setup_column_visibility() after creating your treeview
    3. Supports multiple trees in same class by using config_key as namespace
    """
    
    def setup_column_visibility(self, tree, columns, default_widths, config_key):
        """
        Setup column visibility for a treeview
        
        Args:
            tree: The ttk.Treeview widget
            columns: List/tuple of column identifiers
            default_widths: Dict mapping column names to default widths
            config_key: Unique key for saving preferences (e.g., 'prospector_report')
        """
        # Store per-tree data using config_key as namespace
        if not hasattr(self, '_cv_trees'):
            self._cv_trees = {}
        
        self._cv_trees[config_key] = {
            'tree': tree,
            'columns': columns,
            'default_widths': default_widths,
            'visible': {col: True for col in columns},
            'saved_widths': {}  # Store actual widths before hiding
        }
        
        # Bind right-click with config_key context
        tree.bind("<Button-3>", lambda e, key=config_key: self._cv_handle_right_click(e, key))
        
        # Load saved visibility
        self._cv_load_visibility(config_key)
    
    def _cv_handle_right_click(self, event, config_key):
        """Handle right-click - show column menu on header, normal context menu on rows"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        tree = tree_data['tree']
        region = tree.identify_region(event.x, event.y)
        
        # Show column menu on header
        if region == "heading" or event.y <= 25:
            self._cv_show_menu(event, config_key)
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
    
    def _cv_show_menu(self, event, config_key):
        """Show column visibility menu"""
        tree_data = self._cv_trees.get(config_key)
        if not tree_data:
            return
        
        tree = tree_data['tree']
        columns = tree_data['columns']
        visible = tree_data['visible']
        
        from config import load_theme
        current_theme = load_theme()
        
        # Theme colors
        if current_theme == "elite_orange":
            menu_bg = "#1e1e1e"
            menu_fg = "#ff8c00"
            menu_active_bg = "#3a3a3a"
            menu_active_fg = "#ffffff"
            select_color = "#ff8c00"
        else:
            menu_bg = "#1e1e1e"
            menu_fg = "#e0e0e0"
            menu_active_bg = "#3a3a3a"
            menu_active_fg = "#ffffff"
            select_color = "#4a4a4a"
        
        # Create menu
        menu = tk.Menu(tree, tearoff=0, bg=menu_bg, fg=menu_fg,
                      activebackground=menu_active_bg, activeforeground=menu_active_fg,
                      selectcolor=select_color)
        
        menu.add_command(label=t('ring_finder.column_visibility'), state="disabled")
        menu.add_separator()
        
        # Store vars to prevent garbage collection
        if not hasattr(self, '_cv_menu_vars'):
            self._cv_menu_vars = {}
        self._cv_menu_vars[config_key] = {}
        
        # Add checkboxes for each column
        for col in columns:
            display_name = tree.heading(col, "text")
            is_visible = visible.get(col, True)
            var = tk.BooleanVar(value=is_visible)
            self._cv_menu_vars[config_key][col] = var
            menu.add_checkbutton(label=display_name,
                                variable=var,
                                command=lambda c=col, k=config_key: self._cv_toggle(c, k))
        
        menu.add_separator()
        menu.add_command(label=t('ring_finder.reset_to_default'), 
                        command=lambda k=config_key: self._cv_reset(k))
        
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
    
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
        
        if visible[column]:
            # Show column - restore saved width or default
            width_to_restore = saved_widths.get(column, default_widths[column])
            tree.column(column, width=width_to_restore, minwidth=50)
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
        
        for col in columns:
            visible[col] = True
            current_width = tree.column(col, "width")
            if current_width == 0:
                # Column was hidden, restore default width
                tree.column(col, width=default_widths[col], minwidth=50)
        
        self._cv_save_visibility(config_key)
    
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
                for col, vis in saved.items():
                    if col in visible:
                        visible[col] = vis
                        if not vis:
                            tree.column(col, width=0, minwidth=0, stretch=False)
                
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
        
        for col, vis in visible.items():
            if not vis:
                tree.column(col, width=0, minwidth=0, stretch=False)
