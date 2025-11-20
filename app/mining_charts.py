#!/usr/bin/env python3
"""
Mining Analytics Charts Module
Provides real-time graphical analysis for mining statistics
"""

import json
import os
import sys
from datetime import datetime

# Import matplotlib with error handling for PyInstaller compatibility
try:
    import matplotlib
    matplotlib.use('TkAgg')  # Set backend before importing pyplot
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError as e:
    print(f"Warning: matplotlib not available: {e}")
    MATPLOTLIB_AVAILABLE = False
    # Create dummy classes to prevent errors
    class Figure:
        pass
    class FigureCanvasTkAgg:
        def __init__(self, *args, **kwargs):
            pass

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime, timedelta
try:
    import numpy as np
except ImportError:
    # Create a minimal numpy substitute for basic operations
    class MockNumpy:
        @staticmethod
        def array(data):
            return data
        @staticmethod
        def arange(*args):
            if len(args) == 1:
                return list(range(args[0]))
            elif len(args) == 2:
                return list(range(args[0], args[1]))
            else:
                return list(range(args[0], args[1], args[2]))
    np = MockNumpy()
import csv
import os
from typing import Dict, List, Any, Optional
from mining_statistics import SessionAnalytics

class MiningChartsPanel:
    """Panel containing live mining analytics charts"""
    
    def __init__(self, parent: tk.Widget, session_analytics: SessionAnalytics, main_app=None):
        self.parent = parent
        self.session_analytics = session_analytics
        self.main_app = main_app
        
        # Create main frame
        self.frame = ttk.Frame(parent, padding=8)
        
        # Chart colors for different materials
        self.material_colors = {
            'Platinum': '#E5E4E2',  # Platinum color
            'Painite': '#8B0000',   # Dark red
            'Gold': '#FFD700',      # Gold
            'Osmium': '#4169E1',    # Royal blue
            'Rhodium': '#C0C0C0',   # Silver
            'Palladium': '#CED0DD', # Light gray
            'Silver': '#C0C0C0',    # Silver
            'Default': '#00CED1'    # Dark turquoise
        }
        
        self._create_charts()
        
    def _create_charts(self):
        """Create the chart widgets"""
        
        if not MATPLOTLIB_AVAILABLE:
            # Create a placeholder when matplotlib is not available
            placeholder_frame = ttk.Frame(self.frame)
            placeholder_frame.pack(fill='both', expand=True, padx=10, pady=10)
            
            label = ttk.Label(placeholder_frame, 
                            text="Charts are not available - matplotlib module not found\n"
                                 "Charts functionality is disabled in this build",
                            justify='center',
                            font=('TkDefaultFont', 10))
            label.pack(expand=True)
            return
        
        # Configure button styling to prevent white hover issue
        style = ttk.Style()
        
        # Create custom button style for ALL buttons
        style.configure("Charts.TButton",
                       background="#404040",
                       foreground="#e6e6e6",
                       borderwidth=1,
                       focuscolor="none",
                       relief="raised")
        
        # Create custom checkbutton style  
        style.configure("Charts.TCheckbutton",
                       background="#1e1e1e",
                       foreground="#e6e6e6",
                       focuscolor="none")
        
        # Configure hover and active states for buttons
        style.map("Charts.TButton",
                 background=[('active', '#505050'),   # Darker gray on hover
                            ('pressed', '#303030')],   # Even darker when pressed
                 foreground=[('active', '#ffffff'),   # White text on hover
                            ('pressed', '#ffffff'),    # White text when pressed
                            ('disabled', '#888888')])  # Gray text when disabled
        
        # Configure hover and active states for checkbuttons
        style.map("Charts.TCheckbutton",
                 background=[('active', '#2e2e2e'),   # Slightly lighter on hover
                            ('pressed', '#1a1a1a')],   # Darker when pressed
                 foreground=[('active', '#ffffff'),   # White text on hover
                            ('pressed', '#ffffff'),    # White text when pressed
                            ('disabled', '#888888')])  # Gray text when disabled
        
        # Controls frame with export buttons (ALWAYS at top for visibility)
        controls_frame = ttk.Frame(self.frame)
        controls_frame.pack(fill="x", side="top", pady=(0, 5))
        controls_frame.pack_propagate(False)  # Prevent frame from shrinking
        controls_frame.configure(height=45)  # Larger height for better-sized buttons
        
        # Left side: Chart controls
        chart_controls = ttk.Frame(controls_frame)
        chart_controls.pack(side="left", fill="x", expand=True)
        
        # Refresh button with custom styling - NO MORE WHITE HOVER!
        refresh_btn = ttk.Button(chart_controls, text="🔄 Refresh", command=self.refresh_charts, 
                               style="Charts.TButton")
        refresh_btn.pack(side="left", padx=(0, 10))
        
        # Auto-refresh checkbox with custom styling - NO MORE WHITE HOVER!
        self.auto_refresh_var = tk.BooleanVar(value=True)
        auto_refresh_cb = ttk.Checkbutton(chart_controls, text="Auto-refresh", variable=self.auto_refresh_var,
                                        style="Charts.TCheckbutton")
        auto_refresh_cb.pack(side="left")
        
        # Store buttons for tooltip setup later
        self.refresh_btn = refresh_btn
        self.auto_refresh_cb = auto_refresh_cb
        
        # Right side: Export controls (always visible) - BALANCED SIZE
        export_controls = ttk.Frame(controls_frame)
        export_controls.pack(side="right")
        
        # Better sized export buttons with custom styling - NO MORE WHITE HOVER!
        export_charts_btn = ttk.Button(export_controls, text="📸 PNG", command=self.export_charts_png, 
                                     width=7, style="Charts.TButton")
        export_charts_btn.pack(side="left", padx=(0, 3))
        
        # Note: CSV/data export removed for Mining Analytics (not needed)
        export_all_btn = ttk.Button(export_controls, text="💾 All", command=self.export_charts_png, 
                      width=6, style="Charts.TButton")
        export_all_btn.pack(side="left")

        # Store export buttons for tooltip setup later
        self.export_charts_btn = export_charts_btn
        self.export_all_btn = export_all_btn
        
        # Charts container with notebook for tabs (BELOW controls)
        charts_notebook = ttk.Notebook(self.frame)
        charts_notebook.pack(fill="both", expand=True)
        
        # Timeline Chart Tab - SMALLER size for better visibility
        timeline_frame = ttk.Frame(charts_notebook, padding=5)
        charts_notebook.add(timeline_frame, text="Yield Timeline")
        
        self.timeline_fig = Figure(figsize=(7, 3), dpi=100, facecolor='#2b2b2b')
        self.timeline_ax = self.timeline_fig.add_subplot(111, facecolor='#1e1e1e')
        self.timeline_canvas = FigureCanvasTkAgg(self.timeline_fig, timeline_frame)
        self.timeline_canvas.get_tk_widget().pack(fill="both", expand=True)
        
        # Bar Chart Tab - SMALLER size for better visibility
        bar_frame = ttk.Frame(charts_notebook, padding=5)
        charts_notebook.add(bar_frame, text="Minerals Comparison")
        
        self.bar_fig = Figure(figsize=(5, 3), dpi=100, facecolor='#2b2b2b')
        self.bar_ax = self.bar_fig.add_subplot(111, facecolor='#1e1e1e')
        self.bar_canvas = FigureCanvasTkAgg(self.bar_fig, bar_frame)
        self.bar_canvas.get_tk_widget().pack(fill="both", expand=True)
        
        # Initialize charts
        self._setup_chart_styles()
        self.refresh_charts()
    
    def _setup_chart_styles(self):
        """Setup dark theme styling for charts"""
        
        # Configure matplotlib to use normal font weight by default
        plt.rcParams.update({
            'font.weight': 'normal',
            'axes.labelweight': 'normal',
            'axes.titleweight': 'normal'
        })
        
        # Timeline chart styling
        self.timeline_ax.set_facecolor('#1e1e1e')
        self.timeline_ax.tick_params(colors='white', which='both', labelsize=9)
        self.timeline_ax.spines['bottom'].set_color('white')
        self.timeline_ax.spines['top'].set_color('white')
        self.timeline_ax.spines['left'].set_color('white')
        self.timeline_ax.spines['right'].set_color('white')
        self.timeline_ax.xaxis.label.set_color('white')
        self.timeline_ax.yaxis.label.set_color('white')
        self.timeline_ax.title.set_color('white')
        
        # Bar chart styling
        self.bar_ax.set_facecolor('#1e1e1e')
        self.bar_ax.tick_params(colors='white', which='both', labelsize=9)
        self.bar_ax.spines['bottom'].set_color('white')
        self.bar_ax.spines['top'].set_color('white')
        self.bar_ax.spines['left'].set_color('white')
        self.bar_ax.spines['right'].set_color('white')
        self.bar_ax.xaxis.label.set_color('white')
        self.bar_ax.yaxis.label.set_color('white')
        self.bar_ax.title.set_color('white')
    
    def _get_material_color(self, material_name: str) -> str:
        """Get color for a material"""
        return self.material_colors.get(material_name, self.material_colors['Default'])
    
    def update_charts(self):
        """Update charts with current session data"""
        if not MATPLOTLIB_AVAILABLE:
            return
        if self.auto_refresh_var.get():
            self.refresh_charts()
    
    def refresh_charts(self):
        """Refresh both charts with latest data"""
        if not MATPLOTLIB_AVAILABLE:
            return
        try:
            self._update_timeline_chart()
            self._update_bar_chart()
        except Exception as e:
            print(f"Error refreshing charts: {e}")
    
    def _update_timeline_chart(self):
        """Update the yield timeline chart"""
        self.timeline_ax.clear()
        self._setup_timeline_style()
        
        # Get material statistics
        materials = self.session_analytics.get_tracked_materials()
        
        if not materials:
            self.timeline_ax.text(0.5, 0.5, 'No data available\nStart mining to see yield trends!', 
                                 transform=self.timeline_ax.transAxes, ha='center', va='center',
                                 fontsize=12, color='gray', style='italic')
            self.timeline_canvas.draw()
            return
        
        # Plot yield timeline for each material
        for material in materials:
            stats = self.session_analytics.get_material_statistics(material)
            if stats and stats.finds:
                # Extract data points
                times = [find.timestamp for find in stats.finds]
                percentages = [find.percentage for find in stats.finds]
                
                # Convert to relative time (minutes from start)
                if times:
                    start_time = times[0]
                    relative_times = [(t - start_time).total_seconds() / 60 for t in times]
                    
                    color = self._get_material_color(material)
                    self.timeline_ax.plot(relative_times, percentages, 
                                        marker='o', markersize=4, linewidth=2,
                                        label=material, color=color, alpha=0.8)
        
        self.timeline_ax.set_xlabel('Time (minutes from session start)', fontweight='normal', fontsize=10)
        self.timeline_ax.set_ylabel('Yield (%)', fontweight='normal', fontsize=10)
        self.timeline_ax.set_title('Mining Yield Timeline', fontweight='normal', fontsize=12)
        
        if materials:
            # Position legend outside the plot area (to the right)
            legend = self.timeline_ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', 
                                           facecolor='#2b2b2b', edgecolor='white', fontsize=9)
            for text in legend.get_texts():
                text.set_fontweight('normal')
            self.timeline_ax.grid(True, alpha=0.3, color='gray')
        
        # Adjust layout to prevent label cutoff and accommodate external legend
        self.timeline_fig.subplots_adjust(bottom=0.15, top=0.90, left=0.12, right=0.75)
        self.timeline_canvas.draw()
    
    def _update_bar_chart(self):
        """Update the material comparison bar chart"""
        self.bar_ax.clear()
        self._setup_bar_style()
        
        # Get summary data
        summary_data = self.session_analytics.get_live_summary()
        
        if not summary_data:
            self.bar_ax.text(0.5, 0.5, 'No data available\nStart mining to see material comparison!', 
                           transform=self.bar_ax.transAxes, ha='center', va='center',
                           fontsize=12, color='gray', style='italic')
            self.bar_canvas.draw()
            return
        
        # Prepare data for bar chart
        materials = list(summary_data.keys())
        avg_yields = [summary_data[mat]['avg_percentage'] for mat in materials]
        best_yields = [summary_data[mat]['best_percentage'] for mat in materials]
        colors = [self._get_material_color(mat) for mat in materials]
        
        # Create grouped bar chart with specific legend colors
        x = np.arange(len(materials))
        width = 0.35
        
        # Define legend colors (Option 4: Light blue to dark blue)
        legend_color_avg = '#66B2FF'  # Light blue for Average %
        legend_color_best = '#0066CC'  # Dark blue for Best %
        
        bars1 = self.bar_ax.bar(x - width/2, avg_yields, width, label='Average %', 
                               color=colors, alpha=0.8, edgecolor='white', linewidth=0.5)
        bars2 = self.bar_ax.bar(x + width/2, best_yields, width, label='Best %', 
                               color=colors, alpha=0.6, edgecolor='white', linewidth=0.5)
        
        # Add value labels on bars with improved spacing
        for bar in bars1:
            height = bar.get_height()
            if height > 0:
                # Position Average % labels with more spacing
                self.bar_ax.text(bar.get_x() + bar.get_width()/2., height + 1.0,
                               f'{height:.1f}%', ha='center', va='bottom', 
                               fontsize=8, color='lightgray', fontweight='normal')
        
        for bar in bars2:
            height = bar.get_height()
            if height > 0:
                # Position Best % labels higher to avoid overlap
                self.bar_ax.text(bar.get_x() + bar.get_width()/2., height + 1.0,
                               f'{height:.1f}%', ha='center', va='bottom',
                               fontsize=8, color='white', fontweight='normal')
        
        self.bar_ax.set_xlabel('Minerals', fontweight='normal', fontsize=10)
        self.bar_ax.set_ylabel('Yield (%)', fontweight='normal', fontsize=10)
        self.bar_ax.set_title('Minerals Yield Comparison', fontweight='normal', fontsize=12)
        
        # Set Y-axis limits to provide space for labels above bars
        max_yield = max(max(best_yields) if best_yields else 0, max(avg_yields) if avg_yields else 0)
        self.bar_ax.set_ylim(0, max_yield + 8)  # Add 8% padding above highest bar
        
        self.bar_ax.set_xticks(x)
        self.bar_ax.set_xticklabels(materials, rotation=15, ha='right', fontsize=9, fontweight='normal')
        
        # Create custom legend with specific colors
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor=legend_color_avg, edgecolor='white', label='Average %'),
            Patch(facecolor=legend_color_best, edgecolor='white', label='Best %')
        ]
        
        # Position legend outside the plot area (to the right)
        legend = self.bar_ax.legend(handles=legend_elements, bbox_to_anchor=(1.02, 1), loc='upper left', 
                                  facecolor='#2b2b2b', edgecolor='white', fontsize=9)
        for text in legend.get_texts():
            text.set_fontweight('normal')
        self.bar_ax.grid(True, alpha=0.3, color='gray', axis='y')
        
        # Adjust layout to prevent label cutoff and accommodate external legend
        self.bar_fig.subplots_adjust(bottom=0.30, top=0.82, left=0.12, right=0.75)
        self.bar_canvas.draw()
    
    def _setup_timeline_style(self):
        """Setup timeline chart styling"""
        self.timeline_ax.set_facecolor('#1e1e1e')
        self.timeline_ax.tick_params(colors='white', which='both')
        for spine in self.timeline_ax.spines.values():
            spine.set_color('white')
        self.timeline_ax.xaxis.label.set_color('white')
        self.timeline_ax.yaxis.label.set_color('white')
        self.timeline_ax.title.set_color('white')
    
    def _setup_bar_style(self):
        """Setup bar chart styling"""
        self.bar_ax.set_facecolor('#1e1e1e')
        self.bar_ax.tick_params(colors='white', which='both')
        for spine in self.bar_ax.spines.values():
            spine.set_color('white')
        self.bar_ax.xaxis.label.set_color('white')
        self.bar_ax.yaxis.label.set_color('white')
        self.bar_ax.title.set_color('white')
    
    def pack(self, **kwargs):
        """Pack the main frame"""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        """Grid the main frame"""
        self.frame.grid(**kwargs)
    
    def has_timeline_data(self):
        """Check if the timeline chart has actual data"""
        materials = self.session_analytics.get_tracked_materials()
        return bool(materials)  # If we have tracked materials, we have data
    
    def has_comparison_data(self):
        """Check if the comparison chart has actual data"""
        summary_data = self.session_analytics.get_live_summary()
        return bool(summary_data)  # If we have summary data, we have data
    
    def auto_save_graphs(self, session_system=None, session_body=None, session_timestamp=None):
        """Auto-save graphs to Reports/Mining Session/Graphs/ folder if data exists"""
        if not MATPLOTLIB_AVAILABLE:
            return False
            
        # Only save if we have data
        has_timeline = self.has_timeline_data()
        has_comparison = self.has_comparison_data()
        
        if not has_timeline and not has_comparison:
            return False  # No data to save
        
        try:
            # Use centralized path utility for consistency with other components
            from path_utils import get_reports_dir
            graphs_dir = os.path.join(get_reports_dir(), "Graphs")
            os.makedirs(graphs_dir, exist_ok=True)
            
            # Generate timestamp and filename components
            if session_timestamp:
                timestamp = session_timestamp
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Create session-specific filename prefix
            session_prefix = f"Session_{timestamp}"
            if session_system:
                # Clean system name for filename (remove invalid characters)
                clean_system = "".join(c for c in session_system if c.isalnum() or c in (' ', '-', '_')).strip()
                clean_system = clean_system.replace(' ', '_')
                session_prefix += f"_{clean_system}"
            if session_body:
                # Clean body name for filename  
                clean_body = "".join(c for c in session_body if c.isalnum() or c in (' ', '-', '_')).strip()
                clean_body = clean_body.replace(' ', '_')
                session_prefix += f"_{clean_body}"
            
            saved_files = []
            
            # Save timeline chart if it has data
            timeline_filename = None
            if has_timeline:
                timeline_filename = f"{session_prefix}_Timeline.png"
                timeline_path = os.path.join(graphs_dir, timeline_filename)
                self.timeline_fig.savefig(timeline_path, dpi=300, bbox_inches='tight', 
                                        facecolor='#2b2b2b', edgecolor='none')
                saved_files.append(timeline_filename)
            
            # Save comparison chart if it has data
            comparison_filename = None
            if has_comparison:
                comparison_filename = f"{session_prefix}_Comparison.png"
                comparison_path = os.path.join(graphs_dir, comparison_filename)
                self.bar_fig.savefig(comparison_path, dpi=300, bbox_inches='tight', 
                                   facecolor='#2b2b2b', edgecolor='none')
                saved_files.append(comparison_filename)
            
            # Create/update graph mappings JSON
            self._update_graph_mappings(session_prefix, timeline_filename, comparison_filename)
            
            print(f"Auto-saved graphs: {', '.join(saved_files)} to {graphs_dir}")
            return True
            
        except Exception as e:
            print(f"Error auto-saving graphs: {e}")
            return False

    def _update_graph_mappings(self, session_id, timeline_filename, comparison_filename):
        """Update the graph mappings JSON file"""
        try:
            # Use centralized path utility for consistency
            from path_utils import get_reports_dir
            mappings_file = os.path.join(get_reports_dir(), "Graphs", "graph_mappings.json")
            
            # Load existing mappings
            mappings = {}
            if os.path.exists(mappings_file):
                try:
                    with open(mappings_file, 'r', encoding='utf-8') as f:
                        mappings = json.load(f)
                except (json.JSONDecodeError, IOError):
                    mappings = {}
            
            # Add/update mapping for this session
            mappings[session_id] = {
                "timeline_graph": timeline_filename,
                "comparison_graph": comparison_filename,
                "created": datetime.now().isoformat()
            }
            
            # Save updated mappings
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(mappings, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            print(f"Warning: Could not update graph mappings: {e}")

    def export_charts_png(self):
        """Export both charts as PNG images"""
        if not MATPLOTLIB_AVAILABLE:
            messagebox.showwarning("Export Unavailable", 
                                 "Chart export is not available - matplotlib module not found")
            return
        try:
            # Ask user for directory
            export_dir = filedialog.askdirectory(
                title="Select folder to save charts",
                initialdir=os.path.expanduser("~/Desktop")
            )
            
            if not export_dir:
                return
            
            # Generate timestamp for unique filenames
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Export timeline chart
            timeline_path = os.path.join(export_dir, f"Mining_Timeline_{timestamp}.png")
            self.timeline_fig.savefig(timeline_path, dpi=300, bbox_inches='tight', 
                                    facecolor='#2b2b2b', edgecolor='none')
            
            # Export bar chart
            bar_path = os.path.join(export_dir, f"Mining_Comparison_{timestamp}.png")
            self.bar_fig.savefig(bar_path, dpi=300, bbox_inches='tight', 
                               facecolor='#2b2b2b', edgecolor='none')
            
            from app_utils import centered_message
            centered_message(None, "Export Complete",
                             f"Charts exported successfully!\n\n"
                             f"Timeline: {os.path.basename(timeline_path)}\n"
                             f"Comparison: {os.path.basename(bar_path)}\n\n"
                             f"Location: {export_dir}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export charts:\n{str(e)}")
    
    def export_data_csv(self):
        """CSV export deprecated: data CSV export disabled for Mining Analytics."""
        try:
            messagebox.showinfo("Export Disabled", "CSV data export has been removed from Mining Analytics.")
        except Exception:
            print("CSV data export attempted but is disabled.")
    
    def export_all(self):
        """Export both charts and data"""
        try:
            # Ask user for directory
            export_dir = filedialog.askdirectory(
                title="Select folder to save all exports",
                initialdir=os.path.expanduser("~/Desktop")
            )
            
            if not export_dir:
                return
            
            # Generate timestamp for unique filenames
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Export charts only (data CSV export disabled)
            timeline_chart_path = os.path.join(export_dir, f"Mining_Timeline_{timestamp}.png")
            self.timeline_fig.savefig(timeline_chart_path, dpi=300, bbox_inches='tight', 
                                    facecolor='#2b2b2b', edgecolor='none')
            
            bar_chart_path = os.path.join(export_dir, f"Mining_Comparison_{timestamp}.png")
            self.bar_fig.savefig(bar_chart_path, dpi=300, bbox_inches='tight', 
                               facecolor='#2b2b2b', edgecolor='none')
            
            from app_utils import centered_message
            centered_message(None, "Export Complete",
                             f"Charts exported successfully!\n\n"
                             f"Charts: {os.path.basename(timeline_chart_path)}, {os.path.basename(bar_chart_path)}\n\n"
                             f"Location: {export_dir}\n\nNote: CSV data export has been disabled.")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export all data:\n{str(e)}")
    
    def _export_summary_csv(self, filepath: str):
        """Export mining summary statistics to CSV"""
        summary_data = self.session_analytics.get_live_summary()
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow(['Material', 'Average_Percentage', 'Best_Percentage', 
                           'Latest_Percentage', 'Find_Count', 'Total_Asteroids'])
            
            # Write session summary
            total_asteroids = self.session_analytics.get_total_asteroids()
            
            # Write material data
            for material_name, stats in summary_data.items():
                writer.writerow([
                    material_name,
                    f"{stats['avg_percentage']:.2f}",
                    f"{stats['best_percentage']:.2f}",
                    f"{stats['latest_percentage']:.2f}",
                    stats['find_count'],
                    total_asteroids
                ])
    
    def _export_timeline_csv(self, filepath: str):
        """Export detailed timeline data to CSV"""
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write header
            writer.writerow(['Timestamp', 'Material', 'Percentage', 'Session_Time_Minutes'])
            
            # Get session start time
            session_start = None
            for material_name, material_stats in self.session_analytics.material_stats.items():
                for find in material_stats.finds:
                    if session_start is None or find.timestamp < session_start:
                        session_start = find.timestamp
            
            if session_start is None:
                return  # No data to export
            
            # Collect all finds and sort by timestamp
            all_finds = []
            for material_name, material_stats in self.session_analytics.material_stats.items():
                for find in material_stats.finds:
                    session_minutes = (find.timestamp - session_start).total_seconds() / 60
                    all_finds.append({
                        'timestamp': find.timestamp,
                        'material': material_name,
                        'percentage': find.percentage,
                        'session_minutes': session_minutes
                    })
            
            # Sort by timestamp
            all_finds.sort(key=lambda x: x['timestamp'])
            
            # Write data
            for find in all_finds:
                writer.writerow([
                    find['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    find['material'],
                    f"{find['percentage']:.2f}",
                    f"{find['session_minutes']:.1f}"
                ])

    def setup_tooltips(self):
        """Setup tooltips for buttons after ToolTip class is assigned"""
        if not hasattr(self, 'ToolTip') or not self.ToolTip:
            return
            
        try:
            # Control button tooltips
            if hasattr(self, 'refresh_btn') and self.refresh_btn:
                self.ToolTip(self.refresh_btn, "Manually refresh charts with latest mining data")
            if hasattr(self, 'auto_refresh_cb') and self.auto_refresh_cb:
                self.ToolTip(self.auto_refresh_cb, "Automatically update charts as new data arrives")
                
            # Export button tooltips
            if hasattr(self, 'export_charts_btn') and self.export_charts_btn:
                self.ToolTip(self.export_charts_btn, "Export charts as PNG images")
            if hasattr(self, 'export_all_btn') and self.export_all_btn:
                self.ToolTip(self.export_all_btn, "Export charts (data CSV export disabled)")
        except Exception as e:
            print(f"Warning: Could not setup tooltips for charts: {e}")

# Test function for standalone testing
def test_charts():
    """Test the charts with mock data"""
    
    root = tk.Tk()
    root.title("Mining Analytics Charts Test")
    root.geometry("1000x600")
    root.configure(bg='#2b2b2b')
    
    # Create mock session analytics with test data
    analytics = SessionAnalytics()
    analytics.start_session()
    
    # Add some test data
    import random
    from datetime import datetime, timedelta
    
    materials = ['Platinum', 'Painite', 'Gold', 'Osmium']
    base_time = datetime.now() - timedelta(minutes=30)
    
    for i in range(20):
        for material in materials:
            if random.random() < 0.7:  # 70% chance each material appears
                percentage = random.uniform(15, 45)
                timestamp = base_time + timedelta(minutes=i*1.5)
                
                if material not in analytics.material_stats:
                    from mining_statistics import MaterialStatistics
                    analytics.material_stats[material] = MaterialStatistics(material)
                
                analytics.material_stats[material].add_find(percentage, timestamp)
        
        analytics.total_asteroids_prospected = i + 1
    
    # Create charts panel
    charts = MiningChartsPanel(root, analytics)
    charts.pack(fill="both", expand=True, padx=10, pady=10)
    
    print("🎮 Charts test started!")
    print("📊 Mock data: 20 asteroids with 4 materials")
    print("📈 Check the Timeline and Comparison tabs")
    
    root.mainloop()

if __name__ == "__main__":
    # Only run test function when not in PyInstaller
    import sys
    if not getattr(sys, 'frozen', False):
        test_charts()
