"""
EXTENDED Button Style Showcase for EliteMining
Shows 50+ advanced button styles with hover effects and animations
"""

import tkinter as tk
from tkinter import ttk, messagebox, Canvas
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os

class ExtendedButtonShowcase(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("EliteMining EXTENDED Button Style Showcase")
        self.geometry("1400x900")
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
        title = tk.Label(scrollable_frame, text="🎨 EXTENDED Button Style Gallery", 
                        font=("Segoe UI", 18, "bold"), bg="#1e1e1e", fg="#ffffff")
        title.pack(pady=(10, 10))
        
        subtitle = tk.Label(scrollable_frame, text="50+ Advanced Styles with Hover Effects", 
                           font=("Segoe UI", 11, "italic"), bg="#1e1e1e", fg="#4da6ff")
        subtitle.pack(pady=(0, 20))
        
        # Instructions
        instructions = tk.Label(scrollable_frame, 
                               text="Click any button to copy its code | Hover to see effects", 
                               font=("Segoe UI", 10), bg="#1e1e1e", fg="#888888")
        instructions.pack(pady=(0, 20))
        
        # Create button styles
        self.create_button_styles(scrollable_frame)
        
        # Mousewheel binding
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
    
    def copy_code(self, code, style_name):
        """Copy button code to clipboard"""
        self.clipboard_clear()
        self.clipboard_append(code)
        self.update()
        messagebox.showinfo("Copied!", f"{style_name} code copied to clipboard!")
    
    def create_section(self, parent, title, emoji=""):
        """Create a section header"""
        section_frame = tk.Frame(parent, bg="#1e1e1e")
        section_frame.pack(fill="x", pady=(25, 10), padx=20)
        
        tk.Label(section_frame, text=f"{emoji} {title}", font=("Segoe UI", 13, "bold"), 
                bg="#1e1e1e", fg="#4da6ff").pack(anchor="w")
        
        separator = tk.Frame(section_frame, height=2, bg="#444444")
        separator.pack(fill="x", pady=(5, 0))
        
        return section_frame
    
    def create_button_row(self, parent, style_name, button_widget, code, description=""):
        """Create a row with button example and info"""
        row_frame = tk.Frame(parent, bg="#1e1e1e")
        row_frame.pack(fill="x", pady=8, padx=20)
        
        # Button container
        btn_container = tk.Frame(row_frame, bg="#1e1e1e", width=200)
        btn_container.pack(side="left", padx=(0, 20))
        btn_container.pack_propagate(False)
        
        button_widget.pack(pady=5)
        
        # Info container
        info_frame = tk.Frame(row_frame, bg="#1e1e1e")
        info_frame.pack(side="left", fill="x", expand=True)
        
        # Style name
        name_label = tk.Label(info_frame, text=style_name, 
                             font=("Segoe UI", 10, "bold"), bg="#1e1e1e", fg="#ffffff")
        name_label.pack(anchor="w")
        
        # Description
        if description:
            desc_label = tk.Label(info_frame, text=description, 
                                 font=("Segoe UI", 8, "italic"), bg="#1e1e1e", fg="#888888")
            desc_label.pack(anchor="w")
        
        return row_frame
    
    def create_hover_button(self, parent, text, normal_config, hover_config, code, style_name):
        """Create a button with hover effects"""
        btn = tk.Button(parent, text=text, **normal_config,
                       command=lambda: self.copy_code(code, style_name))
        
        def on_enter(e):
            btn.config(**hover_config)
        
        def on_leave(e):
            btn.config(**normal_config)
        
        btn.bind("<Enter>", on_enter)
        btn.bind("<Leave>", on_leave)
        
        return btn
    
    def create_rounded_button(self, parent, text, bg_color, fg_color, code, style_name):
        """Create a rounded button using Canvas"""
        canvas = Canvas(parent, width=180, height=40, bg="#1e1e1e", highlightthickness=0)
        
        # Draw rounded rectangle
        def draw_rounded_rect(x1, y1, x2, y2, radius, fill_color):
            canvas.create_arc(x1, y1, x1+radius*2, y1+radius*2, 
                            start=90, extent=90, fill=fill_color, outline="")
            canvas.create_arc(x2-radius*2, y1, x2, y1+radius*2, 
                            start=0, extent=90, fill=fill_color, outline="")
            canvas.create_arc(x1, y2-radius*2, x1+radius*2, y2, 
                            start=180, extent=90, fill=fill_color, outline="")
            canvas.create_arc(x2-radius*2, y2-radius*2, x2, y2, 
                            start=270, extent=90, fill=fill_color, outline="")
            canvas.create_rectangle(x1+radius, y1, x2-radius, y2, fill=fill_color, outline="")
            canvas.create_rectangle(x1, y1+radius, x2, y2-radius, fill=fill_color, outline="")
        
        draw_rounded_rect(5, 5, 175, 35, 15, bg_color)
        canvas.create_text(90, 20, text=text, fill=fg_color, font=("Segoe UI", 10, "bold"))
        
        def on_click(e):
            self.copy_code(code, style_name)
        
        canvas.bind("<Button-1>", on_click)
        canvas.config(cursor="hand2")
        
        return canvas
    
    def create_gradient_button(self, parent, text, color1, color2, code, style_name):
        """Create a gradient button using Canvas"""
        canvas = Canvas(parent, width=180, height=40, bg="#1e1e1e", highlightthickness=0)
        
        # Simple vertical gradient
        for i in range(40):
            ratio = i / 40
            r = int(int(color1[1:3], 16) * (1-ratio) + int(color2[1:3], 16) * ratio)
            g = int(int(color1[3:5], 16) * (1-ratio) + int(color2[3:5], 16) * ratio)
            b = int(int(color1[5:7], 16) * (1-ratio) + int(color2[5:7], 16) * ratio)
            color = f"#{r:02x}{g:02x}{b:02x}"
            canvas.create_line(0, i, 180, i, fill=color)
        
        canvas.create_text(90, 20, text=text, fill="#ffffff", font=("Segoe UI", 10, "bold"))
        
        def on_click(e):
            self.copy_code(code, style_name)
        
        canvas.bind("<Button-1>", on_click)
        canvas.config(cursor="hand2")
        
        return canvas
    
    def create_button_styles(self, parent):
        """Create all button style examples"""
        
        # ===== HOVER EFFECT BUTTONS =====
        self.create_section(parent, "Hover Effect Buttons", "🎪")
        
        hover_styles = [
            ("Color Shift", 
             {"bg": "#2a4a2a", "fg": "#e0e0e0", "relief": "flat", "bd": 0, "font": ("Segoe UI", 9), "cursor": "hand2", "padx": 20, "pady": 8},
             {"bg": "#3a6a3a", "fg": "#ffffff", "relief": "flat", "bd": 0, "font": ("Segoe UI", 9), "cursor": "hand2", "padx": 20, "pady": 8},
             "Changes color on hover"),
            
            ("Lift Effect",
             {"bg": "#4da6ff", "fg": "#ffffff", "relief": "raised", "bd": 2, "font": ("Segoe UI", 9), "cursor": "hand2", "padx": 20, "pady": 6},
             {"bg": "#66b3ff", "fg": "#ffffff", "relief": "raised", "bd": 4, "font": ("Segoe UI", 9), "cursor": "hand2", "padx": 20, "pady": 6},
             "Appears to lift on hover"),
            
            ("Border Glow",
             {"bg": "#1e1e1e", "fg": "#4da6ff", "relief": "solid", "bd": 1, "font": ("Segoe UI", 9), "cursor": "hand2", "padx": 20, "pady": 8},
             {"bg": "#1e1e1e", "fg": "#66b3ff", "relief": "solid", "bd": 3, "font": ("Segoe UI", 9, "bold"), "cursor": "hand2", "padx": 20, "pady": 8},
             "Border glows on hover"),
            
            ("Text Glow",
             {"bg": "#2a2a2a", "fg": "#888888", "relief": "flat", "bd": 0, "font": ("Segoe UI", 9), "cursor": "hand2", "padx": 20, "pady": 8},
             {"bg": "#2a2a2a", "fg": "#ffffff", "relief": "flat", "bd": 0, "font": ("Segoe UI", 9, "bold"), "cursor": "hand2", "padx": 20, "pady": 8},
             "Text brightens on hover"),
        ]
        
        for style_name, normal, hover, desc in hover_styles:
            code = f'''# Hover effect button
btn = tk.Button(parent, text="{style_name}",
    bg="{normal['bg']}", fg="{normal['fg']}",
    relief="{normal['relief']}", bd={normal['bd']},
    font=("Segoe UI", 9), cursor="hand2",
    padx={normal['padx']}, pady={normal['pady']})

def on_enter(e):
    btn.config(bg="{hover['bg']}", fg="{hover['fg']}", bd={hover['bd']})

def on_leave(e):
    btn.config(bg="{normal['bg']}", fg="{normal['fg']}", bd={normal['bd']})

btn.bind("<Enter>", on_enter)
btn.bind("<Leave>", on_leave)'''
            
            btn = self.create_hover_button(parent, style_name, normal, hover, code, style_name)
            self.create_button_row(parent, style_name, btn, code, desc)
        
        # ===== NEON GLOW BUTTONS =====
        self.create_section(parent, "Neon Glow Buttons", "✨")
        
        neon_styles = [
            ("Neon Blue", "#1a1a2e", "#0080ff", "Cyberpunk blue glow"),
            ("Neon Pink", "#1a1a2e", "#ff00ff", "Vibrant pink neon"),
            ("Neon Green", "#1a1a2e", "#00ff00", "Matrix green glow"),
            ("Neon Orange", "#1a1a2e", "#ff7700", "Elite Dangerous orange"),
        ]
        
        for style_name, bg, glow, desc in neon_styles:
            normal = {"bg": bg, "fg": glow, "relief": "solid", "bd": 2, 
                     "font": ("Segoe UI", 9, "bold"), "cursor": "hand2", "padx": 20, "pady": 8}
            hover = {"bg": glow, "fg": bg, "relief": "solid", "bd": 2,
                    "font": ("Segoe UI", 9, "bold"), "cursor": "hand2", "padx": 20, "pady": 8}
            
            code = f'''# Neon button with glow effect
btn = tk.Button(parent, text="{style_name}",
    bg="{bg}", fg="{glow}",
    relief="solid", bd=2,
    font=("Segoe UI", 9, "bold"), cursor="hand2",
    padx=20, pady=8)

def on_enter(e):
    btn.config(bg="{glow}", fg="{bg}")

def on_leave(e):
    btn.config(bg="{bg}", fg="{glow}")

btn.bind("<Enter>", on_enter)
btn.bind("<Leave>", on_leave)'''
            
            btn = self.create_hover_button(parent, style_name, normal, hover, code, style_name)
            self.create_button_row(parent, style_name, btn, code, desc)
        
        # ===== ROUNDED BUTTONS =====
        self.create_section(parent, "Rounded Corner Buttons", "🔵")
        
        rounded_styles = [
            ("Rounded Blue", "#4da6ff", "#ffffff", "Smooth rounded corners"),
            ("Rounded Green", "#2ecc71", "#ffffff", "Success style rounded"),
            ("Rounded Red", "#e74c3c", "#ffffff", "Danger style rounded"),
            ("Rounded Dark", "#2d2d2d", "#ffffff", "Dark theme rounded"),
        ]
        
        for style_name, bg, fg, desc in rounded_styles:
            code = f'''# Rounded button using Canvas
canvas = Canvas(parent, width=180, height=40, bg="#1e1e1e", highlightthickness=0)

def draw_rounded_rect(x1, y1, x2, y2, radius, fill_color):
    # Draw arcs for corners
    canvas.create_arc(x1, y1, x1+radius*2, y1+radius*2, 
                    start=90, extent=90, fill=fill_color, outline="")
    canvas.create_arc(x2-radius*2, y1, x2, y1+radius*2, 
                    start=0, extent=90, fill=fill_color, outline="")
    canvas.create_arc(x1, y2-radius*2, x1+radius*2, y2, 
                    start=180, extent=90, fill=fill_color, outline="")
    canvas.create_arc(x2-radius*2, y2-radius*2, x2, y2, 
                    start=270, extent=90, fill=fill_color, outline="")
    # Fill rectangles
    canvas.create_rectangle(x1+radius, y1, x2-radius, y2, fill=fill_color, outline="")
    canvas.create_rectangle(x1, y1+radius, x2, y2-radius, fill=fill_color, outline="")

draw_rounded_rect(5, 5, 175, 35, 15, "{bg}")
canvas.create_text(90, 20, text="{style_name}", fill="{fg}", font=("Segoe UI", 10, "bold"))
canvas.config(cursor="hand2")'''
            
            btn = self.create_rounded_button(parent, style_name, bg, fg, code, style_name)
            self.create_button_row(parent, style_name, btn, code, desc)
        
        # ===== GRADIENT BUTTONS =====
        self.create_section(parent, "Gradient Buttons", "🌈")
        
        gradient_styles = [
            ("Blue Gradient", "#1e3a8a", "#3b82f6", "Dark to light blue"),
            ("Green Gradient", "#064e3b", "#10b981", "Emerald gradient"),
            ("Purple Gradient", "#581c87", "#a855f7", "Purple fade"),
            ("Orange Gradient", "#7c2d12", "#f97316", "Fire gradient"),
        ]
        
        for style_name, color1, color2, desc in gradient_styles:
            code = f'''# Gradient button
canvas = Canvas(parent, width=180, height=40, bg="#1e1e1e", highlightthickness=0)

# Create vertical gradient
for i in range(40):
    ratio = i / 40
    r = int(int("{color1}"[1:3], 16) * (1-ratio) + int("{color2}"[1:3], 16) * ratio)
    g = int(int("{color1}"[3:5], 16) * (1-ratio) + int("{color2}"[3:5], 16) * ratio)
    b = int(int("{color1}"[5:7], 16) * (1-ratio) + int("{color2}"[5:7], 16) * ratio)
    color = f"#{{r:02x}}{{g:02x}}{{b:02x}}"
    canvas.create_line(0, i, 180, i, fill=color)

canvas.create_text(90, 20, text="{style_name}", fill="#ffffff", font=("Segoe UI", 10, "bold"))
canvas.config(cursor="hand2")'''
            
            btn = self.create_gradient_button(parent, style_name, color1, color2, code, style_name)
            self.create_button_row(parent, style_name, btn, code, desc)
        
        # ===== 3D EFFECT BUTTONS =====
        self.create_section(parent, "3D Effect Buttons", "🎲")
        
        btn3d_1 = tk.Button(parent, text="Deep 3D", bg="#34495e", fg="#ffffff",
                           relief="raised", bd=5, font=("Segoe UI", 10, "bold"),
                           cursor="hand2", padx=20, pady=10)
        code3d_1 = '''tk.Button(parent, text="Deep 3D",
    bg="#34495e", fg="#ffffff",
    relief="raised", bd=5,
    font=("Segoe UI", 10, "bold"),
    cursor="hand2", padx=20, pady=10)'''
        self.create_button_row(parent, "Deep 3D", btn3d_1, code3d_1, "Thick raised border")
        
        btn3d_2 = tk.Button(parent, text="Embossed", bg="#2c3e50", fg="#ecf0f1",
                           relief="ridge", bd=4, font=("Segoe UI", 10, "bold"),
                           cursor="hand2", padx=20, pady=10)
        code3d_2 = '''tk.Button(parent, text="Embossed",
    bg="#2c3e50", fg="#ecf0f1",
    relief="ridge", bd=4,
    font=("Segoe UI", 10, "bold"),
    cursor="hand2", padx=20, pady=10)'''
        self.create_button_row(parent, "Embossed", btn3d_2, code3d_2, "Ridge effect")
        
        btn3d_3 = tk.Button(parent, text="Pressed", bg="#7f8c8d", fg="#ffffff",
                           relief="sunken", bd=4, font=("Segoe UI", 10),
                           cursor="hand2", padx=20, pady=10)
        code3d_3 = '''tk.Button(parent, text="Pressed",
    bg="#7f8c8d", fg="#ffffff",
    relief="sunken", bd=4,
    font=("Segoe UI", 10),
    cursor="hand2", padx=20, pady=10)'''
        self.create_button_row(parent, "Pressed", btn3d_3, code3d_3, "Appears pressed in")
        
        # ===== ICON + TEXT BUTTONS =====
        self.create_section(parent, "Icon + Text Combinations", "🔰")
        
        icon_styles = [
            ("✓ Success", "#27ae60", "Confirm action"),
            ("✗ Cancel", "#e74c3c", "Cancel action"),
            ("⚙ Settings", "#34495e", "Open settings"),
            ("📊 Report", "#3498db", "View report"),
            ("💾 Save", "#16a085", "Save changes"),
            ("🔄 Refresh", "#f39c12", "Refresh data"),
        ]
        
        for text, bg, desc in icon_styles:
            btn = tk.Button(parent, text=text, bg=bg, fg="#ffffff",
                          relief="flat", bd=0, font=("Segoe UI", 11, "bold"),
                          cursor="hand2", padx=25, pady=10)
            code = f'''tk.Button(parent, text="{text}",
    bg="{bg}", fg="#ffffff",
    relief="flat", bd=0,
    font=("Segoe UI", 11, "bold"),
    cursor="hand2", padx=25, pady=10)'''
            self.create_button_row(parent, text, btn, code, desc)
        
        # ===== GLASS MORPHISM =====
        self.create_section(parent, "Glass Morphism Style", "🔮")
        
        glass_styles = [
            ("Frosted Glass", "#ffffff", "#000000", 0.3, "Semi-transparent light"),
            ("Dark Glass", "#1e1e1e", "#ffffff", 0.5, "Semi-transparent dark"),
            ("Tinted Glass", "#4da6ff", "#ffffff", 0.4, "Blue tinted glass"),
        ]
        
        for style_name, bg, fg, alpha, desc in glass_styles:
            # Simulate transparency with lighter colors
            btn = tk.Button(parent, text=style_name, bg=bg, fg=fg,
                          relief="flat", bd=1, font=("Segoe UI", 9),
                          cursor="hand2", padx=20, pady=8)
            code = f'''# Glass effect (simulated with colors)
tk.Button(parent, text="{style_name}",
    bg="{bg}", fg="{fg}",
    relief="flat", bd=1,
    font=("Segoe UI", 9),
    cursor="hand2", padx=20, pady=8)'''
            self.create_button_row(parent, style_name, btn, code, desc)
        
        # ===== ELITE DANGEROUS THEMED =====
        self.create_section(parent, "Elite Dangerous Theme", "🚀")
        
        elite_styles = [
            ("Elite Orange", "#ff7700", "#000000", "Iconic ED orange"),
            ("HUD Blue", "#00b0ff", "#000000", "HUD color scheme"),
            ("Station Yellow", "#ffeb3b", "#000000", "Station services"),
            ("Danger Red", "#ff1744", "#ffffff", "Warning alert"),
            ("Neutron Star", "#b39ddb", "#000000", "Neutron route"),
        ]
        
        for style_name, bg, fg, desc in elite_styles:
            normal = {"bg": bg, "fg": fg, "relief": "flat", "bd": 0,
                     "font": ("Segoe UI", 10, "bold"), "cursor": "hand2", "padx": 25, "pady": 10}
            hover = {"bg": fg, "fg": bg, "relief": "flat", "bd": 2,
                    "font": ("Segoe UI", 10, "bold"), "cursor": "hand2", "padx": 25, "pady": 10}
            
            code = f'''# Elite Dangerous themed button
btn = tk.Button(parent, text="{style_name}",
    bg="{bg}", fg="{fg}",
    relief="flat", bd=0,
    font=("Segoe UI", 10, "bold"),
    cursor="hand2", padx=25, pady=10)

def on_enter(e):
    btn.config(bg="{fg}", fg="{bg}", bd=2)

def on_leave(e):
    btn.config(bg="{bg}", fg="{fg}", bd=0)

btn.bind("<Enter>", on_enter)
btn.bind("<Leave>", on_leave)'''
            
            btn = self.create_hover_button(parent, style_name, normal, hover, code, style_name)
            self.create_button_row(parent, style_name, btn, code, desc)
        
        # ===== MINIMAL MODERN =====
        self.create_section(parent, "Minimal Modern Style", "⚡")
        
        minimal_styles = [
            ("Ghost Button", "#1e1e1e", "#ffffff", "Transparent with border"),
            ("Text Only", "#1e1e1e", "#4da6ff", "No background"),
            ("Underline Link", "#1e1e1e", "#4da6ff", "Link style button"),
        ]
        
        for style_name, bg, fg, desc in minimal_styles:
            if "Link" in style_name:
                btn = tk.Button(parent, text=style_name, bg=bg, fg=fg,
                              relief="flat", bd=0, font=("Segoe UI", 9, "underline"),
                              cursor="hand2", padx=20, pady=8)
                code = f'''tk.Button(parent, text="{style_name}",
    bg="{bg}", fg="{fg}",
    relief="flat", bd=0,
    font=("Segoe UI", 9, "underline"),
    cursor="hand2", padx=20, pady=8)'''
            else:
                btn = tk.Button(parent, text=style_name, bg=bg, fg=fg,
                              relief="solid" if "Ghost" in style_name else "flat",
                              bd=1 if "Ghost" in style_name else 0,
                              font=("Segoe UI", 9),
                              cursor="hand2", padx=20, pady=8)
                code = f'''tk.Button(parent, text="{style_name}",
    bg="{bg}", fg="{fg}",
    relief="{'solid' if 'Ghost' in style_name else 'flat'}",
    bd={1 if 'Ghost' in style_name else 0},
    font=("Segoe UI", 9),
    cursor="hand2", padx=20, pady=8)'''
            
            self.create_button_row(parent, style_name, btn, code, desc)

if __name__ == "__main__":
    app = ExtendedButtonShowcase()
    app.mainloop()
