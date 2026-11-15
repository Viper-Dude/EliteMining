# -*- coding: utf-8 -*-
"""
EliteMining Tooltip Widget
Simple tooltip class with global enable/disable support.
"""

import tkinter as tk

from config import scaled_font


def add_header_tooltips(tree, text_for_column):
    from column_visibility_helper import displayed_column
    tooltip = ToolTip(tree, '', follow_pointer=True)

    def heading_hover(event):
        column = displayed_column(tree, tree.identify_column(event.x)) if tree.identify_region(event.x, event.y) == 'heading' else None
        text = text_for_column(column) if column and column != '_spacer' else ''
        if text != tooltip.text:
            tooltip.on_leave()
            tooltip.text = text
            if text:
                tooltip.on_enter()

    tree.bind('<Motion>', heading_hover, add='+')
    tree.bind('<ButtonPress-1>', tooltip.on_leave, add='+')
    return tooltip


class ToolTip:
    """Tooltip widget that displays help text when hovering over a widget."""
    
    tooltips_enabled = True  # Global tooltip enable/disable flag
    _tooltip_instances = {}  # Store references to prevent garbage collection
    
    def __init__(self, widget, text, follow_pointer=False):
        self.widget = widget
        self.text = text
        self.follow_pointer = follow_pointer
        self.tooltip_window = None
        self.tooltip_timer = None  # For delay timer
        
        # Remove any existing tooltip for this widget
        if widget in ToolTip._tooltip_instances:
            old_tooltip = ToolTip._tooltip_instances[widget]
            try:
                widget.unbind("<Enter>")
                widget.unbind("<Leave>")
                # Cancel any existing timer
                if old_tooltip.tooltip_timer:
                    widget.after_cancel(old_tooltip.tooltip_timer)
            except:
                pass
        
        # Store this instance to prevent garbage collection
        ToolTip._tooltip_instances[widget] = self
        
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)
        self.tooltip_window = None

    def on_enter(self, event=None):
        if self.tooltip_window or not self.text or not ToolTip.tooltips_enabled:
            return
        
        # Cancel any existing timer
        if self.tooltip_timer:
            self.widget.after_cancel(self.tooltip_timer)
        
        # Start a timer to show tooltip after 700ms delay (best practice)
        self.tooltip_timer = self.widget.after(700, self._show_tooltip)

    def _show_tooltip(self):
        """Actually create and show the tooltip window"""
        if self.tooltip_window or not self.text or not ToolTip.tooltips_enabled:
            return
            
        try:
            # Get widget position and size
            widget_x = self.widget.winfo_rootx()
            widget_y = self.widget.winfo_rooty()
            widget_width = self.widget.winfo_width()
            widget_height = self.widget.winfo_height()
            
            # Get the main window bounds for positioning reference
            root_window = self.widget.winfo_toplevel()
            root_x = root_window.winfo_x()
            root_y = root_window.winfo_y()
            root_width = root_window.winfo_width()
            root_height = root_window.winfo_height()
            
            # Tooltip dimensions
            tooltip_width = 340
            tooltip_height = 60
            
            # Check if widget is in the bottom area of the window (like the Import/Apply buttons)
            widget_relative_y = widget_y - root_y
            if widget_relative_y > root_height * 0.8:  # If widget is in bottom 20% of window
                # Position tooltip to the right of the widget at same level
                x = widget_x + widget_width + 15
                y = widget_y + (widget_height // 2) - (tooltip_height // 2)  # Center vertically with widget
            else:
                # Default position: below and slightly right of the widget
                x = widget_x + 10
                y = widget_y + widget_height + 8
            
            # Horizontal positioning adjustments
            if x + tooltip_width > root_x + root_width:
                x = widget_x + widget_width - tooltip_width - 10
            
            # Ensure tooltip stays within reasonable bounds of the main window
            x = max(root_x - 50, min(x, root_x + root_width + 50))
            y = max(root_y + 20, min(y, root_y + root_height - 20))

            self.tooltip_window = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            
            # Ensure tooltip appears on top
            tw.wm_attributes("-topmost", True)
            tw.lift()
            
            label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                            font=scaled_font(8), wraplength=340,
                            padx=4, pady=2)
            label.pack()
            if self.follow_pointer:
                tw.update_idletasks()
                width, height = tw.winfo_reqwidth(), tw.winfo_reqheight()
                pointer_x, pointer_y = self.widget.winfo_pointerxy()
                x = max(root_x, min(pointer_x + 12, root_x + root_width - width))
                y = pointer_y + 20
                if y + height > root_y + root_height:
                    y = pointer_y - height - 12
                y = max(root_y, y)
                tw.wm_geometry(f"+{x}+{y}")
            
            # Make sure it's visible
            tw.update()
        except Exception as e:
            self.tooltip_window = None

    def on_leave(self, event=None):
        # Cancel the timer if mouse leaves before tooltip appears
        if self.tooltip_timer:
            self.widget.after_cancel(self.tooltip_timer)
            self.tooltip_timer = None
            
        # Hide tooltip if it's currently showing
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    @classmethod
    def set_enabled(cls, enabled: bool):
        """Enable or disable all tooltips globally"""
        cls.tooltips_enabled = enabled
