"""
Button Style Showcase for EliteMining
Shows all available button styles you can use in the app
"""

import tkinter as tk
from tkinter import ttk, messagebox

class ButtonShowcase(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("EliteMining Button Style Showcase")
        self.geometry("1200x800")
        self.configure(bg="#1e1e1e")
        
        # Create main container with scrollbar
        main_container = tk.Frame(self, bg="#1e1e1e")
        main_container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Canvas and scrollbar
        canvas = tk.Canvas(main_container, bg="#1e1e1e", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1e1e1e")
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Title
        title = tk.Label(scrollable_frame, text="🎨 Button Style Gallery", 
                        font=("Segoe UI", 16, "bold"), bg="#1e1e1e", fg="#ffffff")
        title.pack(pady=(10, 20))
        
        # Instructions
        instructions = tk.Label(scrollable_frame, 
                               text="Click any button to copy its code to clipboard", 
                               font=("Segoe UI", 10, "italic"), bg="#1e1e1e", fg="#888888")
        instructions.pack(pady=(0, 20))
        
        # Create button styles
        self.create_button_styles(scrollable_frame)
        
        # Mousewheel binding
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def copy_code(self, code, style_name):
        """Copy button code to clipboard"""
        # Use tkinter's built-in clipboard
        self.clipboard_clear()
        self.clipboard_append(code)
        self.update()  # Keep clipboard after window closes
        messagebox.showinfo("Copied!", f"{style_name} code copied to clipboard!")
    
    def create_section(self, parent, title):
        """Create a section header"""
        section_frame = tk.Frame(parent, bg="#1e1e1e")
        section_frame.pack(fill="x", pady=(20, 10), padx=20)
        
        tk.Label(section_frame, text=title, font=("Segoe UI", 12, "bold"), 
                bg="#1e1e1e", fg="#4da6ff").pack(anchor="w")
        
        separator = tk.Frame(section_frame, height=2, bg="#444444")
        separator.pack(fill="x", pady=(5, 0))
        
        return section_frame
    
    def create_button_row(self, parent, style_name, button_config, code):
        """Create a row with button example and info"""
        row_frame = tk.Frame(parent, bg="#1e1e1e")
        row_frame.pack(fill="x", pady=5, padx=20)
        
        # Button example
        btn = tk.Button(row_frame, text=style_name, **button_config,
                       command=lambda: self.copy_code(code, style_name))
        btn.pack(side="left", padx=(0, 20))
        
        # Style name label
        name_label = tk.Label(row_frame, text=f"→ {style_name}", 
                             font=("Segoe UI", 9), bg="#1e1e1e", fg="#ffffff")
        name_label.pack(side="left")
        
        return row_frame
    
    def create_button_styles(self, parent):
        """Create all button style examples"""
        
        # ===== STANDARD RELIEF STYLES =====
        self.create_section(parent, "📦 Standard Relief Styles")
        
        styles = [
            ("Flat", {
                "bg": "#2a2a2a", "fg": "#e0e0e0", 
                "relief": "flat", "bd": 0,
                "font": ("Segoe UI", 9),
                "cursor": "hand2"
            }),
            ("Raised", {
                "bg": "#2a2a2a", "fg": "#e0e0e0", 
                "relief": "raised", "bd": 2,
                "font": ("Segoe UI", 9),
                "cursor": "hand2"
            }),
            ("Sunken", {
                "bg": "#2a2a2a", "fg": "#e0e0e0", 
                "relief": "sunken", "bd": 2,
                "font": ("Segoe UI", 9),
                "cursor": "hand2"
            }),
            ("Ridge", {
                "bg": "#2a4a2a", "fg": "#e0e0e0", 
                "relief": "ridge", "bd": 2,
                "font": ("Segoe UI", 9),
                "cursor": "hand2"
            }),
            ("Groove", {
                "bg": "#2a2a2a", "fg": "#e0e0e0", 
                "relief": "groove", "bd": 2,
                "font": ("Segoe UI", 9),
                "cursor": "hand2"
            }),
        ]
        
        for style_name, config in styles:
            code = f'''tk.Button(parent, text="{style_name}",
    bg="{config['bg']}", fg="{config['fg']}",
    relief="{config['relief']}", bd={config['bd']},
    font=("Segoe UI", 9), cursor="hand2")'''
            self.create_button_row(parent, style_name, config, code)
        
        # ===== COLOR THEMES =====
        self.create_section(parent, "🎨 Color Themes")
        
        color_styles = [
            ("Success (Green)", {
                "bg": "#2a4a2a", "fg": "#e0e0e0",
                "activebackground": "#3a5a3a", "activeforeground": "#ffffff",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 9), "cursor": "hand2"
            }),
            ("Danger (Red)", {
                "bg": "#4a2a2a", "fg": "#e0e0e0",
                "activebackground": "#5a3a3a", "activeforeground": "#ffffff",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 9), "cursor": "hand2"
            }),
            ("Warning (Orange)", {
                "bg": "#4a3a2a", "fg": "#e0e0e0",
                "activebackground": "#5a4a3a", "activeforeground": "#ffffff",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 9), "cursor": "hand2"
            }),
            ("Info (Blue)", {
                "bg": "#2a3a4a", "fg": "#e0e0e0",
                "activebackground": "#3a4a5a", "activeforeground": "#ffffff",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 9), "cursor": "hand2"
            }),
            ("Elite Orange", {
                "bg": "#ff7700", "fg": "#000000",
                "activebackground": "#ff8820", "activeforeground": "#000000",
                "relief": "flat", "bd": 0,
                "font": ("Segoe UI", 9, "bold"), "cursor": "hand2"
            }),
        ]
        
        for style_name, config in color_styles:
            code = f'''tk.Button(parent, text="{style_name}",
    bg="{config['bg']}", fg="{config['fg']}",
    activebackground="{config['activebackground']}",
    activeforeground="{config['activeforeground']}",
    relief="{config['relief']}", bd={config['bd']},
    font=("Segoe UI", 9), cursor="hand2")'''
            self.create_button_row(parent, style_name, config, code)
        
        # ===== MODERN FLAT STYLES =====
        self.create_section(parent, "✨ Modern Flat Styles")
        
        modern_styles = [
            ("Dark Flat", {
                "bg": "#2d2d2d", "fg": "#ffffff",
                "activebackground": "#404040", "activeforeground": "#ffffff",
                "relief": "flat", "bd": 0,
                "font": ("Segoe UI", 9), "cursor": "hand2",
                "padx": 20, "pady": 8
            }),
            ("Accent Flat", {
                "bg": "#4da6ff", "fg": "#ffffff",
                "activebackground": "#66b3ff", "activeforeground": "#ffffff",
                "relief": "flat", "bd": 0,
                "font": ("Segoe UI", 9, "bold"), "cursor": "hand2",
                "padx": 20, "pady": 8
            }),
            ("Outline Style", {
                "bg": "#1e1e1e", "fg": "#4da6ff",
                "activebackground": "#2a2a2a", "activeforeground": "#66b3ff",
                "relief": "solid", "bd": 2,
                "font": ("Segoe UI", 9), "cursor": "hand2",
                "padx": 20, "pady": 6
            }),
        ]
        
        for style_name, config in modern_styles:
            code = f'''tk.Button(parent, text="{style_name}",
    bg="{config['bg']}", fg="{config['fg']}",
    activebackground="{config['activebackground']}",
    activeforeground="{config['activeforeground']}",
    relief="{config['relief']}", bd={config['bd']},
    font=("Segoe UI", 9), cursor="hand2",
    padx={config.get('padx', 10)}, pady={config.get('pady', 5)})'''
            self.create_button_row(parent, style_name, config, code)
        
        # ===== ICON BUTTONS =====
        self.create_section(parent, "🔰 Icon Buttons")
        
        icon_styles = [
            ("✅ Check", {
                "text": "✅ Confirm",
                "bg": "#2a4a2a", "fg": "#ffffff",
                "activebackground": "#3a5a3a",
                "relief": "raised", "bd": 2,
                "font": ("Segoe UI", 10), "cursor": "hand2"
            }),
            ("❌ Cancel", {
                "text": "❌ Cancel",
                "bg": "#4a2a2a", "fg": "#ffffff",
                "activebackground": "#5a3a3a",
                "relief": "raised", "bd": 2,
                "font": ("Segoe UI", 10), "cursor": "hand2"
            }),
            ("⚙️ Settings", {
                "text": "⚙️ Settings",
                "bg": "#2a3a4a", "fg": "#ffffff",
                "activebackground": "#3a4a5a",
                "relief": "raised", "bd": 2,
                "font": ("Segoe UI", 10), "cursor": "hand2"
            }),
            ("📊 Report", {
                "text": "📊 Report",
                "bg": "#2a2a4a", "fg": "#ffffff",
                "activebackground": "#3a3a5a",
                "relief": "raised", "bd": 2,
                "font": ("Segoe UI", 10), "cursor": "hand2"
            }),
        ]
        
        for style_name, config in icon_styles:
            btn_config = config.copy()
            text = btn_config.pop("text")
            code = f'''tk.Button(parent, text="{text}",
    bg="{config['bg']}", fg="{config['fg']}",
    activebackground="{config['activebackground']}",
    relief="{config['relief']}", bd={config['bd']},
    font=("Segoe UI", 10), cursor="hand2")'''
            self.create_button_row(parent, style_name, btn_config, code)
        
        # ===== SIZE VARIANTS =====
        self.create_section(parent, "📏 Size Variants")
        
        size_styles = [
            ("Small", {
                "bg": "#2a4a2a", "fg": "#e0e0e0",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 7), "cursor": "hand2",
                "padx": 8, "pady": 2
            }),
            ("Medium", {
                "bg": "#2a4a2a", "fg": "#e0e0e0",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 9), "cursor": "hand2",
                "padx": 12, "pady": 4
            }),
            ("Large", {
                "bg": "#2a4a2a", "fg": "#e0e0e0",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 11, "bold"), "cursor": "hand2",
                "padx": 20, "pady": 8
            }),
        ]
        
        for style_name, config in size_styles:
            code = f'''tk.Button(parent, text="{style_name}",
    bg="{config['bg']}", fg="{config['fg']}",
    relief="{config['relief']}", bd={config['bd']},
    font=("Segoe UI", {config['font'][1]}), cursor="hand2",
    padx={config['padx']}, pady={config['pady']})'''
            self.create_button_row(parent, style_name, config, code)
        
        # ===== SPECIAL EFFECTS =====
        self.create_section(parent, "✨ Special Effects")
        
        special_styles = [
            ("Disabled Look", {
                "bg": "#3a3a3a", "fg": "#666666",
                "relief": "flat", "bd": 0,
                "font": ("Segoe UI", 9), "cursor": "arrow",
                "state": "normal"  # Would be "disabled" in real use
            }),
            ("Bold Text", {
                "bg": "#2a4a2a", "fg": "#ffffff",
                "activebackground": "#3a5a3a",
                "relief": "ridge", "bd": 1,
                "font": ("Segoe UI", 9, "bold"), "cursor": "hand2"
            }),
            ("Underline", {
                "bg": "#1e1e1e", "fg": "#4da6ff",
                "activebackground": "#2a2a2a",
                "relief": "flat", "bd": 0,
                "font": ("Segoe UI", 9, "underline"), "cursor": "hand2"
            }),
        ]
        
        for style_name, config in special_styles:
            code = f'''tk.Button(parent, text="{style_name}",
    bg="{config['bg']}", fg="{config['fg']}",
    relief="{config['relief']}", bd={config['bd']},
    font=("Segoe UI", 9{', "bold"' if 'bold' in str(config['font']) else ''}),
    cursor="{config['cursor']}")'''
            self.create_button_row(parent, style_name, config, code)

if __name__ == "__main__":
    app = ButtonShowcase()
    app.mainloop()
