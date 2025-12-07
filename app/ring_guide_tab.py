"""
Ring Guide Tab for EliteMining
Shows which minerals can be found in each ring type
"""

import tkinter as tk
from tkinter import ttk
import logging
import json
import os
from typing import Dict, List

log = logging.getLogger("EliteMining.RingGuide")


def _get_state_file_path() -> str:
    """Get the path to the ring guide state file"""
    try:
        from path_utils import get_app_data_dir
        return os.path.join(get_app_data_dir(), "ring_guide_state.json")
    except:
        # Fallback to app directory
        return os.path.join(os.path.dirname(__file__), "ring_guide_state.json")


class RingGuideTab(tk.Frame):
    """Tab showing minerals available by ring type with expandable sections"""
    
    # Ring data - minerals by ring type and mining method
    RING_DATA = {
        "Icy": {
            "laser_high": ["Low Temp.Diamonds"],
            "laser_low": ["Bromellite", "Hydrogen Peroxide", "Liquid Oxygen", "Lithium Hydroxide", 
                         "Methane Clathrate", "Methanol Monohydrate Crystals", "Tritium", "Water"],
            "core_high": ["Alexandrite", "Grandidierite", "Low Temp.Diamonds", "Void Opals"],
            "core_low": ["Bromellite"]
        },
        "Metallic": {
            "laser_high": ["Osmium", "Painite", "Platinum"],
            "laser_low": ["Bertrandite", "Gold", "Indite", "Palladium", "Praseodymium", "Samarium", "Silver"],
            "core_high": ["Monazite", "Rhodplumsite", "Serendibite"],
            "core_low": ["Painite", "Platinum"]
        },
        "Metal-Rich": {
            "laser_high": ["Osmium"],
            "laser_low": ["Bertrandite", "Coltan", "Gallite", "Gold", "Indite", "Lepidolite", 
                         "Praseodymium", "Samarium", "Silver", "Uraninite"],
            "core_high": ["Alexandrite", "Benitoite", "Monazite", "Rhodplumsite", "Serendibite"],
            "core_low": ["Painite", "Platinum"]
        },
        "Rocky": {
            "laser_high": [],
            "laser_low": ["Bauxite", "Cobalt", "Coltan", "Gallite", "Indite", "Lepidolite", 
                         "Rutile", "Samarium", "Uraninite"],
            "core_high": ["Alexandrite", "Benitoite", "Monazite", "Musgravite", "Serendibite"],
            "core_low": []
        }
    }
    
    def __init__(self, parent, **kwargs):
        # Get theme colors
        try:
            from config import load_theme
            theme = load_theme()
        except:
            theme = "elite_orange"
        
        if theme == "elite_orange":
            self.bg_color = "#0a0a0a"
            self.fg_color = "#ff8c00"
            self.fg_bright = "#ffa500"
            self.fg_dim = "#888888"
            self.accent_bg = "#1a1a1a"
            self.section_bg = "#151515"
            self.header_bg = "#252525"
            self.high_value_color = "#00ff00"  # Green for high value
            self.low_value_color = "#888888"   # Gray for low value
        else:
            self.bg_color = "#1e1e1e"
            self.fg_color = "#e6e6e6"
            self.fg_bright = "#ffffff"
            self.fg_dim = "#888888"
            self.accent_bg = "#2d2d2d"
            self.section_bg = "#252525"
            self.header_bg = "#333333"
            self.high_value_color = "#4CAF50"
            self.low_value_color = "#888888"
        
        super().__init__(parent, bg=self.bg_color, **kwargs)
        
        # Track expanded state for each ring type - load from saved state
        self._expanded = self._load_expanded_state()
        self._section_frames = {}
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the ring guide UI with 2-column layout"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        # Title row
        title_frame = tk.Frame(self, bg=self.bg_color)
        title_frame.pack(fill="x", padx=10, pady=(10, 5))
        
        tk.Label(
            title_frame,
            text=t('ring_guide.title'),
            font=("Segoe UI", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_bright
        ).pack(side="left")
        
        # Subtitle/help text
        tk.Label(
            title_frame,
            text=t('ring_guide.subtitle'),
            font=("Segoe UI", 9),
            bg=self.bg_color,
            fg=self.fg_dim
        ).pack(side="left", padx=(10, 0))
        
        # Main container with 2 columns
        main_container = tk.Frame(self, bg=self.bg_color)
        main_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Left column - Ring types (fixed width, scrollable)
        left_column = tk.Frame(main_container, bg=self.bg_color, width=420)
        left_column.pack(side="left", fill="both", expand=True)
        left_column.pack_propagate(False)  # Keep fixed width
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(left_column, bg=self.bg_color, highlightthickness=0, width=400)
        scrollbar = ttk.Scrollbar(left_column, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.bg_color)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel to canvas and enable on enter/leave
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))
        
        # Create expandable sections for each ring type in left column
        for ring_type in self.RING_DATA.keys():
            self._create_ring_section(ring_type)
        
        # Right column - RES Sites info (fixed width)
        right_column = tk.Frame(main_container, bg=self.bg_color, width=280)
        right_column.pack(side="left", fill="y", padx=(15, 0))
        right_column.pack_propagate(False)  # Keep fixed width
        
        # Add RES Sites info section to right column
        self._create_res_info_section(right_column)
    
    def _create_res_info_section(self, parent):
        """Create expandable RES Sites section in right column"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        # Section container
        section = tk.Frame(parent, bg=self.bg_color)
        section.pack(fill="x", pady=(0, 8))
        
        # Header (clickable to expand/collapse)
        header = tk.Frame(section, bg=self.header_bg, cursor="hand2")
        header.pack(fill="x")
        
        # Expand/collapse indicator
        res_expanded = self._expanded.get("RES Sites", True)
        expand_label = tk.Label(
            header,
            text="[-]" if res_expanded else "[+]",
            font=("Segoe UI", 9),
            bg=self.header_bg,
            fg=self.fg_color
        )
        expand_label.pack(side="left", padx=(10, 5), pady=8)
        self._expand_labels["RES Sites"] = expand_label
        
        tk.Label(
            header,
            text="⚔️ " + t('ring_guide.res_title'),
            font=("Segoe UI", 11, "bold"),
            bg=self.header_bg,
            fg=self.fg_bright
        ).pack(side="left", pady=8)
        
        tk.Label(
            header,
            text=t('ring_guide.res_subtitle'),
            font=("Segoe UI", 9),
            bg=self.header_bg,
            fg=self.fg_dim
        ).pack(side="left", padx=(5, 0), pady=8)
        
        # Content frame
        content = tk.Frame(section, bg=self.section_bg)
        if res_expanded:
            content.pack(fill="x", padx=(10, 0), pady=(5, 0))
        self._section_frames["RES Sites"] = content
        
        # Bind click to toggle
        header.bind("<Button-1>", lambda e: self._toggle_section("RES Sites"))
        for child in header.winfo_children():
            child.bind("<Button-1>", lambda e: self._toggle_section("RES Sites"))
        
        # RES type data: (type, pirates, mining bonus, color)
        res_types = [
            ("Hazardous", t('ring_guide.res_haz_pirates'), "+100%", self.high_value_color),
            ("High", t('ring_guide.res_high_pirates'), "+75%", "#ffcc00"),
            ("Normal", t('ring_guide.res_normal_pirates'), "+50%", self.fg_color),
            ("Low", t('ring_guide.res_low_pirates'), "+20%", self.low_value_color),
        ]
        
        for res_type, pirates, bonus, color in res_types:
            row = tk.Frame(content, bg=self.section_bg)
            row.pack(fill="x", pady=2)
            
            tk.Label(
                row,
                text=f"• {res_type}:",
                font=("Segoe UI", 9, "bold"),
                bg=self.section_bg,
                fg=color,
                width=10,
                anchor="w"
            ).pack(side="left", padx=(5, 3), pady=1)
            
            tk.Label(
                row,
                text=pirates,
                font=("Segoe UI", 9),
                bg=self.section_bg,
                fg=self.fg_color,
                anchor="w"
            ).pack(side="left", pady=1)
            
            tk.Label(
                row,
                text=bonus + " " + t('ring_guide.res_mining'),
                font=("Segoe UI", 9, "bold"),
                bg=self.section_bg,
                fg=self.high_value_color
            ).pack(side="right", padx=(5, 10), pady=1)
        
        # Tip about mining bonus
        tip_frame = tk.Frame(content, bg=self.section_bg)
        tip_frame.pack(fill="x", pady=(8, 5))
        
        tk.Label(
            tip_frame,
            text="💡 " + t('ring_guide.res_tip'),
            font=("Segoe UI", 8, "italic"),
            bg=self.section_bg,
            fg=self.fg_dim,
            wraplength=250,
            justify="left"
        ).pack(side="left", padx=5)
    
    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
    def _create_ring_section(self, ring_type: str):
        """Create an expandable section for a ring type"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        data = self.RING_DATA[ring_type]
        
        # Section container
        section = tk.Frame(self.scrollable_frame, bg=self.bg_color)
        section.pack(fill="x", pady=(0, 8))
        
        # Header (clickable to expand/collapse)
        header = tk.Frame(section, bg=self.header_bg, cursor="hand2")
        header.pack(fill="x")
        
        # Expand/collapse indicator
        self._expand_labels = getattr(self, '_expand_labels', {})
        expand_label = tk.Label(
            header,
            text="[-]" if self._expanded[ring_type] else "[+]",
            font=("Segoe UI", 9),
            bg=self.header_bg,
            fg=self.fg_color
        )
        expand_label.pack(side="left", padx=(10, 5), pady=8)
        self._expand_labels[ring_type] = expand_label
        
        # Ring type name
        tk.Label(
            header,
            text=f"{ring_type} Ring",
            font=("Segoe UI", 11, "bold"),
            bg=self.header_bg,
            fg=self.fg_bright
        ).pack(side="left", pady=8)
        
        # Mineral count
        total_minerals = len(set(data.get('laser_high', []) + data.get('laser_low', []) + 
                                 data.get('core_high', []) + data.get('core_low', [])))
        tk.Label(
            header,
            text=f"({total_minerals} minerals)",
            font=("Segoe UI", 9),
            bg=self.header_bg,
            fg=self.fg_dim
        ).pack(side="left", padx=(10, 0), pady=8)
        
        # Content frame (minerals)
        content = tk.Frame(section, bg=self.section_bg)
        if self._expanded[ring_type]:
            content.pack(fill="x", padx=(20, 0))
        self._section_frames[ring_type] = content
        
        # Bind click to toggle
        def toggle(rt=ring_type):
            self._toggle_section(rt)
        header.bind("<Button-1>", lambda e, rt=ring_type: self._toggle_section(rt))
        for child in header.winfo_children():
            child.bind("<Button-1>", lambda e, rt=ring_type: self._toggle_section(rt))
        
        # Populate content
        self._populate_ring_content(content, data)
    
    def _toggle_section(self, section_name: str):
        """Toggle expand/collapse of a section"""
        self._expanded[section_name] = not self._expanded[section_name]
        
        # Update expand indicator
        if section_name in self._expand_labels:
            self._expand_labels[section_name].configure(
                text="[-]" if self._expanded[section_name] else "[+]"
            )
        
        # Show/hide content
        content = self._section_frames.get(section_name)
        if content:
            if self._expanded[section_name]:
                # Different padding for RES Sites vs ring types
                if section_name == "RES Sites":
                    content.pack(fill="x", padx=(10, 0), pady=(5, 0))
                else:
                    content.pack(fill="x", padx=(20, 0))
            else:
                content.pack_forget()
        
        # Save state
        self._save_expanded_state()
    
    def _load_expanded_state(self) -> Dict[str, bool]:
        """Load expanded state from file"""
        default_state = {ring: True for ring in self.RING_DATA.keys()}
        default_state["RES Sites"] = True  # Include RES Sites section
        try:
            state_file = _get_state_file_path()
            if os.path.exists(state_file):
                with open(state_file, 'r', encoding='utf-8') as f:
                    saved_state = json.load(f)
                    # Merge with defaults (in case new sections are added)
                    for section in default_state:
                        if section in saved_state:
                            default_state[section] = saved_state[section]
                    return default_state
        except Exception as e:
            log.warning(f"Could not load ring guide state: {e}")
        return default_state
    
    def _save_expanded_state(self):
        """Save expanded state to file"""
        try:
            state_file = _get_state_file_path()
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(self._expanded, f, indent=2)
        except Exception as e:
            log.warning(f"Could not save ring guide state: {e}")
    
    def _populate_ring_content(self, content: tk.Frame, data: Dict[str, List[str]]):
        """Populate a ring section with mineral data"""
        try:
            from localization import t
        except:
            def t(key, **kwargs):
                return key.split('.')[-1]
        
        # Create 2x2 grid for mining methods
        methods = [
            ("laser_high", t('ring_guide.laser_high'), self.high_value_color),
            ("laser_low", t('ring_guide.laser_low'), self.low_value_color),
            ("core_high", t('ring_guide.core_high'), self.high_value_color),
            ("core_low", t('ring_guide.core_low'), self.low_value_color),
        ]
        
        for i, (key, label, color) in enumerate(methods):
            minerals = data.get(key, [])
            
            row_frame = tk.Frame(content, bg=self.section_bg)
            row_frame.pack(fill="x", pady=2)
            
            # Method label
            method_label = tk.Label(
                row_frame,
                text=f"{label}:",
                font=("Segoe UI", 9, "bold"),
                bg=self.section_bg,
                fg=color,
                width=14,
                anchor="w"
            )
            method_label.pack(side="left", padx=(10, 5), pady=2)
            
            # Minerals list
            if minerals:
                minerals_text = ", ".join(minerals)
            else:
                minerals_text = "—"
            
            minerals_label = tk.Label(
                row_frame,
                text=minerals_text,
                font=("Segoe UI", 9),
                bg=self.section_bg,
                fg=self.fg_color if minerals else self.fg_dim,
                anchor="w",
                wraplength=280,
                justify="left"
            )
            minerals_label.pack(side="left", fill="x", expand=True, pady=2)
    
    def destroy(self):
        """Clean up on destroy"""
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except:
            pass
        super().destroy()
