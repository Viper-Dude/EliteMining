"""Refinery contents dialog shared by the main window and the Mining Session tab."""

import os
import tkinter as tk
from tkinter import ttk, messagebox

from app_utils import get_app_icon_path
from localization import t, get_material
from ui.theme import get_theme_colors


class RefineryDialog:
    def __init__(self, parent, cargo_monitor, current_cargo_items=None):
        self.parent = parent
        self.cargo_monitor = cargo_monitor
        self.current_cargo_items = current_cargo_items or {}
        
        # Load existing refinery contents from cargo monitor
        if cargo_monitor and hasattr(cargo_monitor, 'refinery_contents'):
            self.refinery_contents = cargo_monitor.refinery_contents.copy()
        else:
            self.refinery_contents = {}
            
        self.result = None
        
        # Create dialog window (withdraw first to avoid flicker)
        self.dialog = tk.Toplevel(parent)
        self.dialog.withdraw()
        self.dialog.title(t('refinery_dialog.title'))
        self.dialog.geometry("600x750")
        self.dialog.configure(bg="#1e1e1e")
        self.dialog.resizable(True, True)  # Allow resizing so user can adjust if needed
        
        # Set icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                self.dialog.iconbitmap(icon_path)
            elif icon_path and os.path.exists(icon_path):
                self.dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except Exception as e:
            print(f"[RefineryDialog] Could not set icon: {e}")
            pass  # Silently handle icon loading errors
        
        # Center the dialog on parent window
        self.dialog.update_idletasks()
        
        # Calculate dynamic width based on materials
        material_count = len(self.current_cargo_items) if hasattr(self, 'current_cargo_items') and self.current_cargo_items else 0
        
        # Auto-width for up to 3-4 materials
        if material_count <= 4:
            # Calculate width based on longest material name
            max_name_length = 0
            if hasattr(self, 'current_cargo_items') and self.current_cargo_items:
                max_name_length = max(len(name) for name in self.current_cargo_items.keys())
            
            # Base width + material name width + button space
            base_width = 450
            name_width = max_name_length * 8  # ~8 pixels per character
            button_width = 220  # Space for quantity buttons
            calculated_width = max(base_width, min(800, base_width + name_width + button_width))
            dialog_width = calculated_width
        else:
            dialog_width = 750  # Default width for many materials
        
        # Calculate dynamic height based on material count
        base_height = 750
        if material_count > 2:
            extra_rows = (material_count - 2 + 1) // 2  # Round up
            dialog_height = min(950, base_height + (extra_rows * 60))
        else:
            dialog_height = base_height
        
        if parent:
            parent.update_idletasks()
            # Use winfo_x/winfo_y for correct multi-monitor positioning
            parent_x = parent.winfo_x()
            parent_y = parent.winfo_y()
            parent_width = parent.winfo_width()
            parent_height = parent.winfo_height()
            
            x = parent_x + (parent_width - dialog_width) // 2
            y = parent_y + (parent_height - dialog_height) // 2
            
            # Ensure dialog stays on screen (clamp to visible area)
            x = max(0, x)
            y = max(0, y)
        else:
            x = (self.dialog.winfo_screenwidth() // 2) - (dialog_width // 2)
            y = (self.dialog.winfo_screenheight() // 2) - (dialog_height // 2)
        
        self.dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        self._create_ui()
        # Now show dialog centered and make it modal
        # Keep topmost permanently so it stays above main app's always-on-top window
        self.dialog.transient(parent)
        self.dialog.attributes('-topmost', True)
        self.dialog.deiconify()
        self.dialog.lift()
        self.dialog.focus_force()
        try:
            self.dialog.grab_set()
        except:
            pass
        
    def _create_ui(self):
        """Create the refinery dialog UI"""
        from core.constants import MINING_MATERIALS
        
        # Main frame
        main_frame = tk.Frame(self.dialog, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = tk.Label(main_frame, text="⚗️ " + t('refinery_dialog.title'), 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Manual add section (moved to top for dropdown space)
        manual_frame = tk.LabelFrame(main_frame, text="🔍 " + t('refinery_dialog.add_other_minerals'), 
                                   bg="#1e1e1e", fg="#ffffff", 
                                   font=("Segoe UI", 10, "bold"))
        manual_frame.pack(fill="x", pady=(0, 15))
        
        manual_inner = tk.Frame(manual_frame, bg="#1e1e1e")
        manual_inner.pack(fill="x", padx=10, pady=10)
        
        # Configure grid columns for proper spacing
        manual_inner.columnconfigure(1, weight=1)  # Material dropdown column
        manual_inner.columnconfigure(3, weight=0)  # Quantity entry column
        
        # Material selection
        tk.Label(manual_inner, text=t('refinery_dialog.material_label'), bg="#1e1e1e", fg="#ffffff").grid(row=0, column=0, sticky="w", padx=(0, 5))
        
        self.material_var = tk.StringVar(value=t('refinery_dialog.select_material'))
        
        # Material selection button using standard app styling
        from config import load_theme as _load_theme
        _mat_btn_bg = get_theme_colors(_load_theme())["btn_bg"] if _load_theme() in ("modern", "modern_slate", "modern_orange") else "#4a9eff"
        material_btn = tk.Button(manual_inner, textvariable=self.material_var,
                               command=self._open_material_selector,
                               bg=_mat_btn_bg, fg="#ffffff", 
                               font=("Segoe UI", 9))
        material_btn.grid(row=0, column=1, padx=5, sticky="w")
        
        # Quantity entry
        tk.Label(manual_inner, text=t('refinery_dialog.quantity_label'), bg="#1e1e1e", fg="#ffffff").grid(row=0, column=2, sticky="w", padx=(10, 5))
        
        self.quantity_var = tk.StringVar()
        quantity_entry = tk.Entry(manual_inner, textvariable=self.quantity_var, width=8,
                                bg="#2d2d2d", fg="#ffffff", 
                                insertbackground="#ffffff",  # Cursor color
                                selectbackground="#404040",   # Selection background
                                selectforeground="#ffffff",   # Selection text
                                relief="sunken", bd=1)
        quantity_entry.grid(row=0, column=3, padx=5)
        
        tk.Label(manual_inner, text=t('refinery_dialog.tons'), bg="#1e1e1e", fg="#ffffff").grid(row=0, column=4, sticky="w", padx=(5, 0))
        
        # Add button
        add_btn = tk.Button(manual_inner, text=t('refinery_dialog.add_button'), 
                          command=self._add_manual_material,
                          bg="#4a9eff", fg="#ffffff", 
                          font=("Segoe UI", 9, "bold"))
        add_btn.grid(row=0, column=5, padx=(10, 0))

        # Session summary
        if self.cargo_monitor:
            summary_frame = tk.Frame(main_frame, bg="#2d2d2d", relief="raised", bd=1)
            summary_frame.pack(fill="x", pady=(0, 15))
            
            cargo_total = getattr(self.cargo_monitor, 'current_cargo', 0)
            capacity = getattr(self.cargo_monitor, 'max_cargo', 0)
            
            summary_label = tk.Label(summary_frame, 
                                   text="📦 " + t('refinery_dialog.cargo_hold_detected', total=cargo_total),
                                   bg="#2d2d2d", fg="#ffffff", 
                                   font=("Segoe UI", 10))
            summary_label.pack(pady=8)
        
        # Quick add from cargo section
        if self.current_cargo_items:
            cargo_frame = tk.LabelFrame(main_frame, text="📦 " + t('refinery_dialog.quick_add_cargo'), 
                                      bg="#1e1e1e", fg="#ffffff", 
                                      font=("Segoe UI", 10, "bold"))
            cargo_frame.pack(fill="x", pady=(0, 15))
            
            cargo_inner = tk.Frame(cargo_frame, bg="#1e1e1e")
            cargo_inner.pack(fill="x", padx=10, pady=10)
            
            # Create quick-add buttons for materials in cargo
            row = 0
            col = 0
            for material, quantity in self.current_cargo_items.items():
                # Normalize material name for comparison
                normalized_material = material.replace("LowTemperatureDiamonds", "Low Temperature Diamonds")
                if normalized_material in MINING_MATERIALS:  # Only show known mining materials
                    # Use the normalized name for display
                    display_material = normalized_material
                    material_frame = tk.Frame(cargo_inner, bg="#1e1e1e")
                    material_frame.grid(row=row, column=col, padx=5, pady=5, sticky="w")
                    
                    # Material label - use normalized name
                    mat_label = tk.Label(material_frame, text=f"{display_material}:", 
                                       bg="#1e1e1e", fg="#ffffff", 
                                       font=("Segoe UI", 9))
                    mat_label.pack(side="left")
                    
                    # Quick add buttons - use normalized name
                    for amount in [1, 4, 6, 8, 10]:
                        btn = tk.Button(material_frame, text=f"+{amount}t", 
                                      command=lambda m=display_material, a=amount: self._quick_add_material(m, a),
                                      bg="#404040", fg="#ffffff", 
                                      font=("Segoe UI", 8), width=6)
                        btn.pack(side="left", padx=2)
                    
                    col += 1
                    if col > 1:  # 2 columns
                        col = 0
                        row += 1
        
        # Current refinery contents
        contents_frame = tk.LabelFrame(main_frame, text="⚗️ " + t('refinery_dialog.current_refinery'), 
                                     bg="#1e1e1e", fg="#ffffff", 
                                     font=("Segoe UI", 10, "bold"))
        contents_frame.pack(fill="x", pady=(0, 15))
        
        # Scrollable list of refinery contents - with fixed height
        list_frame = tk.Frame(contents_frame, bg="#1e1e1e")
        list_frame.pack(fill="x", padx=10, pady=10)
        
        self.contents_listbox = tk.Listbox(list_frame, bg="#2d2d2d", fg="#ffffff", 
                                         selectbackground="#404040", 
                                         font=("Segoe UI", 9), height=6)
        self.contents_listbox.pack(side="left", fill="x", expand=True)
        
        from config import load_theme as _lt_sb
        _SB = ttk.Scrollbar if _lt_sb() in ("modern", "modern_slate", "modern_orange") else tk.Scrollbar
        scrollbar = _SB(list_frame, orient="vertical", command=self.contents_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.contents_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Edit and Remove buttons
        button_container = tk.Frame(contents_frame, bg="#1e1e1e")
        button_container.pack(pady=(0, 10))
        
        edit_btn = tk.Button(button_container, text=t('refinery_dialog.edit_selected'), 
                           command=self._edit_selected,
                           bg="#4a9eff", fg="#ffffff")
        edit_btn.pack(side="left", padx=(0, 5))
        
        remove_btn = tk.Button(button_container, text=t('refinery_dialog.remove_selected'), 
                             command=self._remove_selected,
                             bg="#ff6b6b", fg="#ffffff")
        remove_btn.pack(side="left")
        
        # Summary section
        self.summary_frame = tk.Frame(main_frame, bg="#2d2d2d", relief="raised", bd=1)
        self.summary_frame.pack(fill="x", pady=(0, 15))
        
        self.summary_label = tk.Label(self.summary_frame, 
                                    text=t('dialogs.refinery_total', count=0),
                                    bg="#2d2d2d", fg="#ffffff", 
                                    font=("Segoe UI", 10, "bold"))
        self.summary_label.pack(pady=8)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="#1e1e1e")
        button_frame.pack(fill="x")
        
        clear_btn = tk.Button(button_frame, text=t('refinery_dialog.clear_all'), 
                            command=self._clear_all,
                            bg="#666666", fg="#ffffff")
        clear_btn.pack(side="left")
        
        cancel_btn = tk.Button(button_frame, text=t('dialogs.cancel'), 
                             command=self._cancel,
                             bg="#666666", fg="#ffffff")
        cancel_btn.pack(side="right", padx=(5, 0))
        
        apply_btn = tk.Button(button_frame, text=t('refinery_dialog.apply_to_session'), 
                            command=self._apply,
                            bg="#4caf50", fg="#ffffff", 
                            font=("Segoe UI", 9, "bold"))
        apply_btn.pack(side="right", padx=(5, 0))
        
        # Update display to show any existing refinery contents
        self._update_display()
        self._update_summary()
    
    def _quick_add_material(self, material, amount):
        """Add material from quick-add buttons"""
        # Check refinery capacity limit (10t max)
        current_total = sum(self.refinery_contents.values())
        if current_total + amount > 10.0:
            remaining_capacity = 10.0 - current_total
            self._show_capacity_error(current_total, remaining_capacity, amount)
            return
            
        if material in self.refinery_contents:
            self.refinery_contents[material] += amount
        else:
            self.refinery_contents[material] = amount
        self._update_display()
        
        # Trigger CSV update if this is being used after session end
        self._check_and_trigger_csv_update({material: amount})
    
    def _add_manual_material(self):
        """Add material from manual entry"""
        material = self.material_var.get()
        
        # Check if material is selected
        if not material or material == t('refinery_dialog.select_material'):
            messagebox.showerror(t('dialogs.error'), t('refinery_dialog.select_material_error'))
            return
            
        try:
            quantity_str = self.quantity_var.get().strip()
            if not quantity_str:
                messagebox.showerror(t('dialogs.error'), t('refinery_dialog.invalid_quantity'))
                return
                
            quantity = float(quantity_str)
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            
            # Check refinery capacity limit (10t max)
            current_total = sum(self.refinery_contents.values())
            if current_total + quantity > 10.0:
                remaining_capacity = 10.0 - current_total
                self._show_capacity_error(current_total, remaining_capacity, quantity)
                return
                
            if material in self.refinery_contents:
                self.refinery_contents[material] += quantity
            else:
                self.refinery_contents[material] = quantity
                
            self.quantity_var.set("")  # Clear entry
            self._update_display()
            
            # Trigger CSV update if this is being used after session end
            self._check_and_trigger_csv_update({material: quantity})
            
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid positive number for quantity.")
    
    def _check_and_trigger_csv_update(self, added_materials: dict):
        """Check if we should trigger CSV update when materials are added manually"""
        # DISABLED: Refinery materials are now handled in end_session_tracking()
        # This function was causing double-writes and cross-session data contamination
        # The materials are stored in refinery_contents and added to the report at session end
        pass

    def _show_capacity_error(self, current, available, amount):
        """Show themed capacity exceeded error dialog, always on top"""
        from config import load_theme
        from app_utils import get_app_icon_path

        theme = load_theme()
        if theme == "elite_orange":
            bg = "#000000"
            fg = "#ff8c00"
            btn_bg = "#1a1a1a"
            btn_fg = "#ff9900"
        else:
            bg = "#1e1e1e"
            fg = "#e0e0e0"
            btn_bg = "#2a3a4a"
            btn_fg = "#e0e0e0"

        err = tk.Toplevel(self.dialog)
        err.withdraw()
        err.title(t('refinery_dialog.capacity_exceeded_title'))
        err.configure(bg=bg)
        err.resizable(False, False)

        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                err.iconbitmap(icon_path)
        except:
            pass

        frame = tk.Frame(err, bg=bg, padx=20, pady=15)
        frame.pack(fill="both", expand=True)

        msg = t('refinery_dialog.capacity_exceeded_msg',
                current=current, available=available, amount=amount)
        tk.Label(frame, text=msg, bg=bg, fg=fg,
                 font=("Segoe UI", 10), justify="left").pack(pady=(0, 14))

        tk.Button(frame, text="OK", command=err.destroy,
                  bg=btn_bg, fg=btn_fg, activebackground=btn_bg, activeforeground=btn_fg,
                  font=("Segoe UI", 9), padx=24, pady=4, relief="flat",
                  cursor="hand2").pack()

        err.update_idletasks()
        # Center on the refinery dialog
        dw = err.winfo_reqwidth() or 300
        dh = err.winfo_reqheight() or 150
        px = self.dialog.winfo_x()
        py = self.dialog.winfo_y()
        pw = self.dialog.winfo_width()
        ph = self.dialog.winfo_height()
        err.geometry(f"{dw}x{dh}+{px + (pw - dw)//2}+{py + (ph - dh)//2}")

        err.deiconify()
        err.attributes('-topmost', True)
        err.lift()
        err.focus_force()
        try:
            err.grab_set()
        except:
            pass

        def keep_on_top():
            try:
                if err.winfo_exists():
                    err.lift()
                    err.after(100, keep_on_top)
            except:
                pass
        err.after(100, keep_on_top)
        err.wait_window()

    def _remove_selected(self):
        """Remove selected material from refinery contents"""
        selection = self.contents_listbox.curselection()
        if selection:
            index = selection[0]
            materials = list(self.refinery_contents.keys())
            if index < len(materials):
                material = materials[index]
                del self.refinery_contents[material]
                self._update_display()
    
    def _edit_selected(self):
        """Edit the quantity of selected material"""
        selection = self.contents_listbox.curselection()
        if not selection:
            messagebox.showwarning(t('dialogs.warning'), t('refinery_dialog.select_material_error'))
            return
            
        index = selection[0]
        materials = list(self.refinery_contents.keys())
        if index < len(materials):
            material = materials[index]
            current_qty = self.refinery_contents[material]
            
            # Create custom edit dialog with dark theme and proper positioning
            new_qty = self._show_edit_quantity_dialog(material, current_qty)
            
            if new_qty is not None:
                if new_qty == 0:
                    # Remove if quantity is 0
                    del self.refinery_contents[material]
                else:
                    # Update quantity
                    self.refinery_contents[material] = new_qty
                self._update_display()
                
    def _show_edit_quantity_dialog(self, material, current_qty):
        """Show a custom dark-themed edit quantity dialog positioned near parent"""
        # Create dialog window
        edit_dialog = tk.Toplevel(self.dialog)
        edit_dialog.title(t('refinery_dialog.edit_quantity_title'))
        edit_dialog.geometry("400x200")
        edit_dialog.configure(bg="#1e1e1e")
        edit_dialog.resizable(False, False)
        edit_dialog.transient(self.dialog)
        
        # Set app icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                edit_dialog.iconbitmap(icon_path)
            elif icon_path:
                edit_dialog.iconphoto(False, tk.PhotoImage(file=icon_path))
        except:
            pass  # Silently handle icon loading errors
        
        # Position near parent dialog
        self.dialog.update_idletasks()
        edit_dialog.update_idletasks()
        
        # Calculate center position relative to parent dialog
        parent_x = self.dialog.winfo_x()
        parent_y = self.dialog.winfo_y()
        parent_width = self.dialog.winfo_width()
        parent_height = self.dialog.winfo_height()
        
        dialog_width = 400
        dialog_height = 200
        x = parent_x + (parent_width - dialog_width) // 2
        y = parent_y + (parent_height - dialog_height) // 2
        
        # Ensure on screen
        x = max(0, x)
        y = max(0, y)
        
        edit_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        
        # Force dialog to stay on top and have focus
        edit_dialog.lift()
        edit_dialog.focus_force()
        
        try:
            edit_dialog.grab_set()
        except:
            pass
        
        # Create UI with dark theme
        main_frame = tk.Frame(edit_dialog, bg="#1e1e1e", padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = tk.Label(main_frame, text=t('refinery_dialog.edit_quantity_prompt', material=material), 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Current quantity info
        info_label = tk.Label(main_frame, text=t('refinery_dialog.current_quantity', qty=current_qty), 
                             bg="#1e1e1e", fg="#cccccc", 
                             font=("Segoe UI", 10))
        info_label.pack(pady=(0, 10))
        
        # New quantity entry
        entry_frame = tk.Frame(main_frame, bg="#1e1e1e")
        entry_frame.pack(pady=(0, 20))
        
        tk.Label(entry_frame, text=t('refinery_dialog.new_quantity'), bg="#1e1e1e", fg="#ffffff",
                font=("Segoe UI", 10)).pack(side="left")
        
        quantity_var = tk.StringVar(value=str(current_qty))
        quantity_entry = tk.Entry(entry_frame, textvariable=quantity_var, width=10,
                                bg="#2d2d2d", fg="#ffffff", 
                                insertbackground="#ffffff",
                                selectbackground="#404040",
                                selectforeground="#ffffff",
                                font=("Segoe UI", 10),
                                relief="sunken", bd=1)
        quantity_entry.pack(side="left", padx=(10, 5))
        
        tk.Label(entry_frame, text=t('refinery_dialog.tons'), bg="#1e1e1e", fg="#ffffff",
                font=("Segoe UI", 10)).pack(side="left")
        
        # Focus and select all text
        quantity_entry.focus_set()
        quantity_entry.select_range(0, tk.END)
        
        # Buttons
        button_frame = tk.Frame(main_frame, bg="#1e1e1e")
        button_frame.pack()
        
        result = [None]  # Use list to store result (mutable)
        
        def ok_clicked():
            try:
                value = float(quantity_var.get())
                if value < 0:
                    messagebox.showerror("Invalid Input", "Quantity cannot be negative.", parent=edit_dialog)
                    return
                result[0] = value
                edit_dialog.destroy()
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid number.", parent=edit_dialog)
        
        def cancel_clicked():
            result[0] = None
            edit_dialog.destroy()
        
        # OK button
        ok_btn = tk.Button(button_frame, text=t('common.ok'), command=ok_clicked,
                          bg="#4caf50", fg="#ffffff", 
                          font=("Segoe UI", 9, "bold"), width=8)
        ok_btn.pack(side="left", padx=(0, 10))
        
        # Cancel button  
        cancel_btn = tk.Button(button_frame, text=t('common.cancel'), command=cancel_clicked,
                              bg="#666666", fg="#ffffff", 
                              font=("Segoe UI", 9), width=8)
        cancel_btn.pack(side="left")
        
        # Bind Enter key to OK and Escape to Cancel
        edit_dialog.bind('<Return>', lambda e: ok_clicked())
        edit_dialog.bind('<Escape>', lambda e: cancel_clicked())
        
        # Wait for dialog to close and return result
        edit_dialog.wait_window()
        return result[0]
    
    def _clear_all(self):
        """Clear all refinery contents"""
        self.refinery_contents.clear()
        self._update_display()
    
    def _update_display(self):
        """Update the contents listbox and summary"""
        self.contents_listbox.delete(0, tk.END)
        
        for material, quantity in self.refinery_contents.items():
            self.contents_listbox.insert(tk.END, f"{material}: {quantity} tons")
        
        self._update_summary()
    
    def _update_summary(self):
        """Update the summary label"""
        total = sum(self.refinery_contents.values())
        self.summary_label.configure(text=t('refinery_dialog.refinery_total', total=total))
        
        # Update final calculation if we have cargo data
        if self.cargo_monitor:
            cargo_total = getattr(self.cargo_monitor, 'current_cargo', 0)
            final_total = cargo_total + total
            
            summary_text = t('refinery_dialog.refinery_total', total=total) + "\n"
            summary_text += t('refinery_dialog.final_total', cargo=cargo_total, refinery=total, total=final_total)
            self.summary_label.configure(text=summary_text)
    
    def _cancel(self):
        """Cancel the dialog"""
        self.result = None
        self.dialog.destroy()
    
    def _apply(self):
        """Apply the refinery contents"""
        self.result = self.refinery_contents.copy()
        # Rebuild CSV after materials are applied
        if hasattr(self.cargo_monitor, 'main_app_ref') and hasattr(self.cargo_monitor.main_app_ref, 'prospector_panel'):
            prospector_panel = self.cargo_monitor.main_app_ref.prospector_panel
            csv_path = os.path.join(prospector_panel.reports_dir, "sessions_index.csv")
            prospector_panel.after(100, lambda: prospector_panel._rebuild_csv_from_files_tab(csv_path))
        self.dialog.destroy()
    
    def show(self):
        """Show the dialog and return the result"""
        self.dialog.wait_window()
        return self.result
    
    def _open_material_selector(self):
        """Open a material selection window"""
        from core.constants import MINING_MATERIALS
        
        # Create selection window
        selector = tk.Toplevel(self.dialog)
        selector.title(t('refinery_dialog.select_material_title'))
        selector.geometry("400x500")
        selector.configure(bg="#1e1e1e")
        selector.resizable(False, False)
        selector.transient(self.dialog)
        selector.grab_set()
        
        # Set icon using the same method as main app
        try:
            icon_path = get_app_icon_path()
            if icon_path and icon_path.endswith('.ico'):
                selector.iconbitmap(icon_path)
            elif icon_path:
                selector.iconphoto(False, tk.PhotoImage(file=icon_path))
        except:
            pass  # Silently handle icon loading errors
        
        # Center on parent
        selector.update_idletasks()
        x = self.dialog.winfo_x() + (self.dialog.winfo_width() // 2) - 200
        y = self.dialog.winfo_y() + (self.dialog.winfo_height() // 2) - 250
        selector.geometry(f"400x500+{x}+{y}")
        
        # Title
        title_label = tk.Label(selector, text=t('refinery_dialog.select_mining_material'), 
                              bg="#1e1e1e", fg="#ffffff", 
                              font=("Segoe UI", 12, "bold"))
        title_label.pack(pady=15)
        
        # Search frame
        search_frame = tk.Frame(selector, bg="#1e1e1e")
        search_frame.pack(fill="x", padx=20, pady=(0, 10))
        
        tk.Label(search_frame, text=t('refinery_dialog.search'), bg="#1e1e1e", fg="#ffffff").pack(side="left")
        search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=search_var, bg="#404040", fg="#ffffff")
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))
        
        # Materials listbox
        list_frame = tk.Frame(selector, bg="#1e1e1e")
        list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        
        from config import load_theme as _lt_sb
        _SB = ttk.Scrollbar if _lt_sb() in ("modern", "modern_slate", "modern_orange") else tk.Scrollbar
        scrollbar = _SB(list_frame)
        scrollbar.pack(side="right", fill="y")
        
        materials_list = tk.Listbox(list_frame, bg="#2d2d2d", fg="#ffffff",
                                  selectbackground="#404040", 
                                  font=("Segoe UI", 9),
                                  yscrollcommand=scrollbar.set)
        materials_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=materials_list.yview)
        
        # Populate list with localized material names
        materials = list(MINING_MATERIALS.keys())
        for material in sorted(materials):
            materials_list.insert(tk.END, get_material(material))
        
        # Search function
        def filter_materials(*args):
            search_term = search_var.get().lower()
            materials_list.delete(0, tk.END)
            for material in sorted(materials):
                localized = get_material(material)
                if search_term in localized.lower():
                    materials_list.insert(tk.END, localized)
        
        search_var.trace('w', filter_materials)
        
        # Buttons
        btn_frame = tk.Frame(selector, bg="#1e1e1e")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        def select_material():
            selection = materials_list.curselection()
            if selection:
                selected = materials_list.get(selection[0])
                self.material_var.set(selected)
            selector.destroy()
        
        def cancel_selection():
            selector.destroy()
        
        select_btn = tk.Button(btn_frame, text=t('common.select'), command=select_material,
                             bg="#4a9eff", fg="#ffffff", font=("Segoe UI", 9, "bold"))
        select_btn.pack(side="right", padx=(5, 0))
        
        cancel_btn = tk.Button(btn_frame, text=t('dialogs.cancel'), command=cancel_selection,
                             bg="#666666", fg="#ffffff", font=("Segoe UI", 9))
        cancel_btn.pack(side="right")
        
        # Double-click to select
        materials_list.bind("<Double-Button-1>", lambda e: select_material())
        
        # Focus search entry
        search_entry.focus_set()
