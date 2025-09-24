"""
Detailed Report Generator for EliteMining
Generates HTML reports with charts, statistics, and screenshots
"""

import json
import os
import sys
import base64
import webbrowser
import tempfile
from datetime import datetime
from pathlib import Path

# Chart generation imports
try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend for saving
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# Image processing imports for thumbnails
try:
    from PIL import Image
    import io
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


class ReportGenerator:
    def __init__(self, main_app=None):
        self.main_app = main_app
        
        # Use consistent directory detection logic with the main app
        if main_app and hasattr(main_app, 'va_root'):
            # Use main app's va_root for consistency
            va_root = main_app.va_root
            if getattr(sys, 'frozen', False):
                # Running as executable (installer version)
                app_dir = os.path.join(va_root, "app")
            else:
                # Running as script (development version)
                app_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            # Fallback logic when main_app is not available
            if getattr(sys, 'frozen', False):
                # Running as executable (installer version)
                app_dir = Path(sys.executable).parent / "app"
            else:
                # Running as script (development version)
                app_dir = Path("app")
            
        self.reports_dir = os.path.join(app_dir, "Reports")
        self.mining_session_reports_dir = os.path.join(self.reports_dir, "Mining Session")
        self.enhanced_reports_dir = os.path.join(self.mining_session_reports_dir, "Detailed Reports")
        self.screenshots_dir = os.path.join(self.enhanced_reports_dir, "Screenshots")
        
        # Create directories
        os.makedirs(self.enhanced_reports_dir, exist_ok=True)
        os.makedirs(self.screenshots_dir, exist_ok=True)
        
    def _safe_float(self, value, default=0.0):
        """Safely convert any value to float for formatting"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
        
    def _get_logo_path(self):
        """Get correct logo path for both dev and installer versions"""
        # Use consistent directory detection
        if self.main_app and hasattr(self.main_app, 'va_root'):
            va_root = self.main_app.va_root
            if getattr(sys, 'frozen', False):
                # Running as executable (installer version)
                logo_paths = [
                    os.path.join(va_root, "Images", "elitemining_logo.png"),
                    os.path.join(va_root, "app", "Images", "elitemining_logo.png"),
                    os.path.join(va_root, "Images", "logo.png")
                ]
            else:
                # Running as script (development version)
                app_dir = os.path.dirname(os.path.abspath(__file__))
                parent_dir = os.path.dirname(app_dir)
                logo_paths = [
                    os.path.join(parent_dir, "Images", "elitemining_logo.png"),
                    os.path.join(app_dir, "Images", "elitemining_logo.png"),
                    os.path.join(parent_dir, "Images", "logo.png")
                ]
        else:
            # Fallback logo paths
            logo_paths = [
                "Images/elitemining_logo.png",
                "app/Images/elitemining_logo.png", 
                "../Images/elitemining_logo.png",
                "Images/logo.png",
                "app/Images/logo.png"
            ]
        
        for logo_path in logo_paths:
            if os.path.exists(logo_path):
                return logo_path
                
        # If no logo found, return None
        return None
        
    def _encode_image_base64(self, image_path):
        """Convert image to base64 for HTML embedding"""
        if not image_path or not os.path.exists(image_path):
            return None
            
        try:
            with open(image_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image {image_path}: {e}")
            return None

    def _create_thumbnail_base64(self, image_path, max_width=400, max_height=300):
        """Create a thumbnail version of an image and return as base64"""
        if not image_path or not os.path.exists(image_path) or not PIL_AVAILABLE:
            return self._encode_image_base64(image_path)  # Fallback to full size
            
        try:
            with Image.open(image_path) as img:
                # Convert to RGB if necessary (for PNG with transparency)
                if img.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Create thumbnail
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                
                # Save to bytes
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=85, optimize=True)
                buffer.seek(0)
                
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"Error creating thumbnail for {image_path}: {e}")
            return self._encode_image_base64(image_path)  # Fallback to full size
    
    def _get_default_screenshots_folder(self):
        """Get default screenshots folder path"""
        try:
            if self.main_app and hasattr(self.main_app, 'screenshots_folder_path'):
                return self.main_app.screenshots_folder_path.get() or os.path.join(os.path.expanduser("~"), "Pictures")
            return os.path.join(os.path.expanduser("~"), "Pictures")
        except:
            return os.path.join(os.path.expanduser("~"), "Pictures")
            
    def _get_html_template(self):
        """Get HTML template for reports"""
        return """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>EliteMining Session Report</title>
    <style>
        :root {{
            /* Light theme variables */
            --bg-color: #f5f5f5;
            --container-bg: white;
            --text-color: #333;
            --header-color: #2c3e50;
            --section-bg: #f8f9fa;
            --section-border: #3498db;
            --card-bg: white;
            --card-border: #dee2e6;
            --stat-value-color: #27ae60;
            --stat-label-color: #7f8c8d;
            --table-header-bg: #34495e;
            --table-header-color: white;
            --table-even-row: #f8f9fa;
            --comment-bg: #e8f4fd;
            --comment-border: #0066cc;
            --comment-text-bg: white;
            --comment-text-border: #d1ecf1;
            --no-comment-color: #6c757d;
            --border-color: #dee2e6;
        }}
        
        [data-theme="dark"] {{
            /* Dark theme variables */
            --bg-color: #1a1a1a;
            --container-bg: #2d2d2d;
            --text-color: #e0e0e0;
            --header-color: #4dabf7;
            --section-bg: #3a3a3a;
            --section-border: #4dabf7;
            --card-bg: #404040;
            --card-border: #555555;
            --stat-value-color: #51cf66;
            --stat-label-color: #adb5bd;
            --table-header-bg: #495057;
            --table-header-color: #e0e0e0;
            --table-even-row: #404040;
            --comment-bg: #1c3d5a;
            --comment-border: #4dabf7;
            --comment-text-bg: #404040;
            --comment-text-border: #555555;
            --no-comment-color: #adb5bd;
            --border-color: #555555;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: var(--bg-color);
            color: var(--text-color);
            transition: background-color 0.3s ease, color 0.3s ease;
        }}
        
        .theme-toggle {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--section-border);
            color: white;
            border: none;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            font-size: 20px;
            cursor: pointer;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            transition: all 0.3s ease;
            z-index: 1000;
        }}
        
        .theme-toggle:hover {{
            transform: scale(1.1);
            background: var(--header-color);
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: var(--container-bg);
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: background-color 0.3s ease;
        }}
        
        .header {{
            text-align: center;
            border-bottom: 3px solid var(--header-color);
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        
        .logo {{
            max-height: 80px;
            margin-bottom: 10px;
        }}
        
        .title {{
            color: var(--header-color);
            margin: 10px 0;
        }}
        
        .section {{
            margin: 30px 0;
            padding: 20px;
            border-left: 4px solid var(--section-border);
            background-color: var(--section-bg);
            border-radius: 0 8px 8px 0;
            transition: background-color 0.3s ease;
        }}
        
        .section h2 {{
            color: var(--header-color);
            margin-top: 0;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 10px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .stat-card {{
            background: var(--card-bg);
            padding: 15px;
            border-radius: 8px;
            border: 1px solid var(--card-border);
            text-align: center;
            transition: background-color 0.3s ease, transform 0.2s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
        }}
        
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: var(--stat-value-color);
        }}
        
        .stat-label {{
            color: var(--stat-label-color);
            margin-top: 5px;
        }}
        
        .stat-help {{
            color: #888888;
            font-size: 11px;
            margin-top: 3px;
            font-style: italic;
            opacity: 0.8;
        }}
        
        .stat-card:hover .stat-help {{
            opacity: 1;
            color: #aaaaaa;
        }}
        
        .chart-container {{
            text-align: center;
            margin: 20px 0;
        }}
        
        .chart-container img {{
            max-width: 400px;
            height: auto;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        
        .chart-container img:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
        }}
        
        .screenshot-gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .screenshot {{
            text-align: center;
        }}
        
        .screenshot img {{
            max-width: 300px;
            height: auto;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}
        
        .screenshot img:hover {{
            transform: scale(1.02);
            box-shadow: 0 4px 12px rgba(0, 123, 255, 0.3);
        }}
        
        /* Image Modal Styles */
        .image-modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            padding-top: 50px;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(5px);
        }}
        
        .modal-content {{
            margin: auto;
            display: block;
            width: auto;
            max-width: 95%;
            max-height: 85%;
            border-radius: 8px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
        }}
        
        .modal-caption {{
            margin: 15px auto;
            display: block;
            width: 80%;
            max-width: 700px;
            text-align: center;
            color: #ffffff;
            font-size: 16px;
            font-weight: 500;
            padding: 10px;
            background: rgba(0, 0, 0, 0.7);
            border-radius: 5px;
        }}
        
        .close-modal {{
            position: absolute;
            top: 15px;
            right: 35px;
            color: #ffffff;
            font-size: 40px;
            font-weight: bold;
            transition: 0.3s;
            cursor: pointer;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
        }}
        
        .close-modal:hover,
        .close-modal:focus {{
            color: #007bff;
            text-decoration: none;
        }}
        
        /* Zoom instructions */
        .zoom-hint {{
            position: absolute;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            color: #ffffff;
            background: rgba(0, 0, 0, 0.7);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 14px;
            opacity: 0.8;
        }}
        
        /* Loading animation */
        .modal-loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #ffffff;
            font-size: 18px;
        }}
        
        /* Thumbnail indicators */
        .thumbnail-indicator {{
            position: relative;
        }}
        
        .thumbnail-indicator::after {{
            content: "🔍 Click to expand";
            position: absolute;
            bottom: 5px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 0, 0, 0.8);
            color: white;
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 11px;
            opacity: 0;
            transition: opacity 0.3s ease;
            pointer-events: none;
        }}
        
        .thumbnail-indicator:hover::after {{
            opacity: 1;
        }}
        
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            border-radius: 8px;
            overflow: hidden;
        }}
        
        .data-table th,
        .data-table td {{
            border: 1px solid var(--border-color);
            padding: 8px 12px;
            text-align: left;
            transition: background-color 0.3s ease;
        }}
        
        .data-table th {{
            background-color: var(--table-header-bg);
            color: var(--table-header-color);
        }}
        
        .data-table tr:nth-child(even) {{
            background-color: var(--table-even-row);
        }}
        
        .data-table tr:hover {{
            background-color: var(--section-border);
            color: white;
        }}
        
        .comment-section {{
            background-color: var(--comment-bg);
            border-left: 4px solid var(--comment-border);
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            transition: background-color 0.3s ease;
        }}
        
        .comment-section h3 {{
            margin-top: 0;
            color: var(--comment-border);
            font-size: 1.2em;
        }}
        
        .comment-text {{
            background-color: var(--comment-text-bg);
            padding: 15px;
            border-radius: 4px;
            border: 1px solid var(--comment-text-border);
            white-space: pre-wrap;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            transition: background-color 0.3s ease;
        }}
        
        .no-comment {{
            font-style: italic;
            color: var(--no-comment-color);
        }}
        
        @media print {{
            .theme-toggle {{
                display: none;
            }}
            body {{
                background-color: white;
                color: black;
            }}
            .container {{
                box-shadow: none;
                padding: 0;
                background-color: white;
            }}
            .section {{
                page-break-inside: avoid;
                background-color: #f8f9fa;
            }}
        }}
        
        @media (max-width: 768px) {{
            .container {{
                padding: 15px;
                margin: 10px;
            }}
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            .theme-toggle {{
                width: 40px;
                height: 40px;
                font-size: 16px;
            }}
        }}
    </style>
    <script>
        function toggleTheme() {{
            const html = document.documentElement;
            const currentTheme = html.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            html.setAttribute('data-theme', newTheme);
            
            // Save preference to localStorage
            localStorage.setItem('elitemining-report-theme', newTheme);
            
            // Update button icon
            const button = document.querySelector('.theme-toggle');
            button.textContent = newTheme === 'dark' ? '☀️' : '🌙';
        }}
        
        // Load saved theme preference
        document.addEventListener('DOMContentLoaded', function() {{
            const savedTheme = localStorage.getItem('elitemining-report-theme') || 'dark';
            document.documentElement.setAttribute('data-theme', savedTheme);
            
            // Set initial button icon
            const button = document.querySelector('.theme-toggle');
            button.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
        }});
    </script>
</head>
<body>
    <button class="theme-toggle" onclick="toggleTheme()" title="Toggle Theme">🌙</button>
    <div class="container">
        <div class="header">
            {logo_section}
            <h1 class="title">Elite Dangerous Mining Session Report</h1>
            <p><strong>Generated:</strong> {generation_time}</p>
        </div>
        
        <div class="section">
            <h2>📊 Session Summary</h2>
            <div class="stats-grid">
                {session_stats}
            </div>
        </div>
        
        {charts_section}
        
        {screenshots_section}
        
        {statistics_section}
        
        {advanced_analytics_section}
        
        {comment_section}
        
        <div class="section">
            <h2>📋 Material Breakdown</h2>
            {materials_table}
        </div>
        
        <div class="section">
            <h2>🔢 Raw Session Data</h2>
            {raw_data_table}
        </div>
    </div>
    
    <!-- Image Modal -->
    <div id="imageModal" class="image-modal">
        <span class="close-modal">&times;</span>
        <img class="modal-content" id="modalImg">
        <div id="caption" class="modal-caption"></div>
        <div class="zoom-hint">Click image to zoom • ESC to close</div>
    </div>

    <script>
        // Image modal functionality
        document.addEventListener('DOMContentLoaded', function() {{
            const modal = document.getElementById('imageModal');
            const modalImg = document.getElementById('modalImg');
            const caption = document.getElementById('caption');
            const closeBtn = document.querySelector('.close-modal');
            
            // Add click handlers to all chart and screenshot images
            const images = document.querySelectorAll('.chart-container img, .screenshot img');
            
            images.forEach(function(img, index) {{
                // Add thumbnail indicator class
                img.parentElement.classList.add('thumbnail-indicator');
                
                img.onclick = function() {{
                    modal.style.display = 'block';
                    modalImg.src = this.src;
                    caption.textContent = this.alt || this.title || `Image ${{index + 1}}`;
                    
                    // Add loading state
                    modalImg.style.opacity = '0';
                    modalImg.onload = function() {{
                        this.style.opacity = '1';
                    }};
                }};
            }});
            
            // Close modal handlers
            closeBtn.onclick = function() {{
                modal.style.display = 'none';
            }};
            
            modal.onclick = function(event) {{
                if (event.target === modal) {{
                    modal.style.display = 'none';
                }}
            }};
            
            // Keyboard navigation
            document.addEventListener('keydown', function(event) {{
                if (event.key === 'Escape') {{
                    modal.style.display = 'none';
                }}
            }});
            
            // Add smooth transition for modal images
            modalImg.style.transition = 'opacity 0.3s ease';
        }});
    </script>
</body>
</html>
        """
        
    def generate_report(self, session_data, include_charts=True, include_screenshots=True, include_statistics=True):
        """Generate enhanced HTML report"""
        try:
            # Get logo
            logo_path = self._get_logo_path()
            logo_section = ""
            if logo_path:
                logo_base64 = self._encode_image_base64(logo_path)
                if logo_base64:
                    logo_section = f'<img src="data:image/png;base64,{logo_base64}" alt="EliteMining Logo" class="logo">'
            
            # Generate session stats
            session_stats = self._generate_session_stats(session_data)
            
            # Generate charts section
            charts_section = ""
            if include_charts:
                charts_section = self._generate_charts_section(session_data)
            
            # Generate screenshots section
            screenshots_section = ""
            if include_screenshots:
                screenshots_section = self._generate_screenshots_section(session_data)
                
            # Generate statistics section
            statistics_section = ""
            if include_statistics:
                statistics_section = self._generate_statistics_section(session_data)
            
            # Generate advanced mining analytics section
            advanced_analytics_section = self._generate_advanced_analytics_section(session_data)
            
            # Generate comment section
            comment_section = self._generate_comment_section(session_data)
            
            # Generate materials table
            materials_table = self._generate_materials_table(session_data)
            
            # Generate raw data table
            raw_data_table = self._generate_raw_data_table(session_data)
            
            # Fill template
            html_content = self._get_html_template().format(
                logo_section=logo_section,
                generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                session_stats=session_stats,
                charts_section=charts_section,
                screenshots_section=screenshots_section,
                statistics_section=statistics_section,
                advanced_analytics_section=advanced_analytics_section,
                comment_section=comment_section,
                materials_table=materials_table,
                raw_data_table=raw_data_table
            )
            
            return html_content
            
        except Exception as e:
            print(f"Error generating report: {e}")
            return None
            
    def _generate_session_stats(self, session_data):
        """Generate session statistics HTML"""
        if not session_data:
            return "<p>No session data available</p>"
        
        # Use correct field names from CSV/reports tab data
        # Duration comes as already formatted string (e.g., "06:43")
        duration_str = session_data.get('duration', '0h 0m')
        if duration_str and ':' in duration_str:
            # Duration is already formatted as "06:43", just add "h" and "m"
            parts = duration_str.split(':')
            if len(parts) == 2:
                duration_str = f"{parts[0]}h {parts[1]}m"
        
        # TPH comes as already calculated float/string (e.g., "461.8")
        tph_value = session_data.get('tph', 0)
        if isinstance(tph_value, str):
            try:
                tph_value = float(tph_value)
            except:
                tph_value = 0.0
        elif tph_value is None:
            tph_value = 0.0
        
        # Tons comes as already calculated float/string (e.g., "44.0")  
        tons_value = session_data.get('tons', 0)
        if isinstance(tons_value, str):
            try:
                tons_value = float(tons_value)
            except:
                tons_value = 0.0
        elif tons_value is None:
            tons_value = 0.0
        
        # Prospectors used
        prospectors_used = session_data.get('prospectors', 0)
        if isinstance(prospectors_used, str):
            try:
                prospectors_used = int(prospectors_used) if prospectors_used != '—' else 0
            except:
                prospectors_used = 0
        
        # Materials count
        materials_count = session_data.get('materials', 0)
        if isinstance(materials_count, str):
            try:
                materials_count = int(materials_count) if materials_count != '—' else 0
            except:
                materials_count = 0
        
        stats_html = f"""
        <div class="stat-card">
            <div class="stat-value">{self._safe_float(tons_value):.1f}</div>
            <div class="stat-label">Total Tons Mined</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{self._safe_float(tph_value):.1f}</div>
            <div class="stat-label">Tons per Hour</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{duration_str}</div>
            <div class="stat-label">Session Duration</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{prospectors_used}</div>
            <div class="stat-label">Prospectors Used</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{materials_count}</div>
            <div class="stat-label">Material Types</div>
        </div>
        """
        
        return stats_html
        
    def _generate_charts_section(self, session_data):
        """Generate charts section HTML"""
        charts_html = """
        <div class="section">
            <h2>📈 Mining Charts</h2>
        """
        
        try:
            # First try to use saved session graphs (works without matplotlib for PNG files)
            saved_charts_html = self._add_saved_charts(session_data)
            
            # If saved charts found, use them
            if saved_charts_html:
                charts_html += saved_charts_html
            else:
                # If no saved charts found and matplotlib available, generate them
                if MATPLOTLIB_AVAILABLE:
                    # Generate material breakdown pie chart
                    pie_chart_base64 = self._generate_pie_chart(session_data)
                    if pie_chart_base64:
                        charts_html += f"""
                        <div class="chart-container">
                            <h3>Material Breakdown</h3>
                            <img src="data:image/png;base64,{pie_chart_base64}" alt="Material Breakdown Chart">
                        </div>
                        """
                    
                    # Generate yield timeline chart if available
                    timeline_chart_base64 = self._generate_timeline_chart(session_data)
                    if timeline_chart_base64:
                        charts_html += f"""
                        <div class="chart-container">
                            <h3>Yield Timeline</h3>
                            <img src="data:image/png;base64,{timeline_chart_base64}" alt="Yield Timeline Chart">
                        </div>
                        """
                else:
                    charts_html += "<p><em>Charts are not available - matplotlib module not found and no saved charts</em></p>"
                    
        except Exception as e:
            print(f"Error generating charts: {e}")
            charts_html += "<p><em>Error generating charts</em></p>"
            
        charts_html += "</div>"
        return charts_html

    def _add_saved_charts(self, session_data):
        """Try to add saved charts for this session and return HTML string or None"""
        try:
            # Try to identify the session from session_data
            session_id = self._get_session_id_from_data(session_data)
            if not session_id:
                return None
            
            # Load graph mappings
            graphs_dir = os.path.join(os.path.dirname(__file__), "Reports", "Mining Session", "Graphs")
            mappings_file = os.path.join(graphs_dir, "graph_mappings.json")
            
            if not os.path.exists(mappings_file):
                return None
            
            with open(mappings_file, 'r', encoding='utf-8') as f:
                mappings = json.load(f)
            
            # First try exact match
            if session_id in mappings:
                matched_session_id = session_id
            else:
                # Try fuzzy matching - look for sessions with same system, body, and similar timestamp (within same minute)
                matched_session_id = None
                session_parts = session_id.split('_')
                if len(session_parts) >= 4:  # Session_YYYY-MM-DD_HH-MM-SS_System_Body...
                    target_datetime = session_parts[1] + "_" + session_parts[2]  # YYYY-MM-DD_HH-MM-SS
                    target_system = "_".join(session_parts[3:-1]) if len(session_parts) > 4 else session_parts[3]
                    target_body = session_parts[-1]
                    
                    # Extract date and hour-minute for fuzzy matching
                    target_date = session_parts[1]  # YYYY-MM-DD
                    target_hour_min = session_parts[2].split('-')[:2]  # [HH, MM]
                    
                    for mapping_key in mappings.keys():
                        mapping_parts = mapping_key.split('_')
                        if len(mapping_parts) >= 4:
                            map_date = mapping_parts[1]
                            map_hour_min = mapping_parts[2].split('-')[:2]
                            map_system = "_".join(mapping_parts[3:-1]) if len(mapping_parts) > 4 else mapping_parts[3]
                            map_body = mapping_parts[-1]
                            
                            # Check if same date, same hour:minute, same system, same body
                            if (map_date == target_date and 
                                map_hour_min == target_hour_min and 
                                map_system == target_system and 
                                map_body == target_body):
                                matched_session_id = mapping_key
                                break
                
                if not matched_session_id:
                    return None
            
            session_graphs = mappings[matched_session_id]
            charts_html = ""
            
            # Add timeline chart if available
            if session_graphs.get('timeline_graph'):
                timeline_path = os.path.join(graphs_dir, session_graphs['timeline_graph'])
                if os.path.exists(timeline_path):
                    timeline_base64 = self._encode_image_base64(timeline_path)
                    if timeline_base64:
                        charts_html += f"""
                        <div class="chart-container">
                            <h3>Yield Timeline</h3>
                            <img src="data:image/png;base64,{timeline_base64}" alt="Yield Timeline Chart">
                        </div>
                        """
            
            # Add comparison chart if available
            if session_graphs.get('comparison_graph'):
                comparison_path = os.path.join(graphs_dir, session_graphs['comparison_graph'])
                if os.path.exists(comparison_path):
                    comparison_base64 = self._encode_image_base64(comparison_path)
                    if comparison_base64:
                        charts_html += f"""
                        <div class="chart-container">
                            <h3>Material Comparison</h3>
                            <img src="data:image/png;base64,{comparison_base64}" alt="Material Comparison Chart">
                        </div>
                        """
            
            # Add pie chart for material breakdown (still generated dynamically)
            pie_chart_base64 = self._generate_pie_chart(session_data)
            if pie_chart_base64:
                charts_html += f"""
                <div class="chart-container">
                    <h3>Material Breakdown</h3>
                    <img src="data:image/png;base64,{pie_chart_base64}" alt="Material Breakdown Chart">
                </div>
                """
            
            return charts_html if charts_html else None
            
        except Exception as e:
            print(f"Error loading saved charts: {e}")
            return None

    def _get_session_id_from_data(self, session_data):
        """Extract session ID from session data to match with saved graphs"""
        try:
            # Try to get timestamp, system, and body from session data
            timestamp = None
            system = session_data.get('system', '').strip()
            body = session_data.get('body', '').strip()
            
            # Try to extract timestamp from session data
            if 'date' in session_data:
                date_str = session_data['date']
                
                # Try to parse different date formats and convert to our timestamp format
                try:
                    # Handle formats like "09/24/25 16:04" or "2025-09-24 16:04:31"
                    if '/' in date_str and len(date_str.split(' ')) >= 2:
                        # Format like "09/24/25 16:04"
                        date_part, time_part = date_str.split(' ', 1)
                        month, day, year = date_part.split('/')
                        # Convert 2-digit year to 4-digit
                        if len(year) == 2:
                            year = f"20{year}"
                        
                        # Parse time (might be HH:MM or HH:MM:SS)
                        time_parts = time_part.split(':')
                        if len(time_parts) == 2:
                            hour, minute = time_parts
                            second = "00"
                        else:
                            hour, minute, second = time_parts
                        
                        # Format as our timestamp format: YYYY-MM-DD_HH-MM-SS
                        timestamp = f"{year}-{month.zfill(2)}-{day.zfill(2)}_{hour.zfill(2)}-{minute.zfill(2)}-{second.zfill(2)}"
                        
                except Exception:
                    # If parsing fails, skip timestamp
                    pass
            
            if not timestamp or not system:
                return None
            
            # Clean system and body names (same as in auto_save_graphs)
            clean_system = "".join(c for c in system if c.isalnum() or c in (' ', '-', '_')).strip()
            clean_system = clean_system.replace(' ', '_')
            
            clean_body = "".join(c for c in body if c.isalnum() or c in (' ', '-', '_')).strip()
            clean_body = clean_body.replace(' ', '_')
            
            # Construct session ID (same format as in auto_save_graphs)
            session_id = f"Session_{timestamp}"
            if clean_system:
                session_id += f"_{clean_system}"
            if clean_body:
                session_id += f"_{clean_body}"
            
            return session_id
            
        except Exception as e:
            print(f"Error extracting session ID: {e}")
            return None
        
    def _generate_pie_chart(self, session_data):
        """Generate material breakdown pie chart"""
        if not MATPLOTLIB_AVAILABLE:
            return None
            
        materials_mined = session_data.get('materials_mined', {})
        if not materials_mined:
            return None
            
        try:
            # Create figure
            fig, ax = plt.subplots(figsize=(8, 6))
            fig.patch.set_facecolor('white')
            
            # Prepare data
            materials = list(materials_mined.keys())
            quantities = list(materials_mined.values())
            
            # Define colors for materials
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', 
                     '#DDA0DD', '#98D8C8', '#F7DC6F', '#AED6F1', '#F8C471']
            
            # Create pie chart
            wedges, texts, autotexts = ax.pie(quantities, labels=materials, colors=colors[:len(materials)], 
                                            autopct='%1.1f%%', startangle=90)
            
            # Improve text appearance
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
            
            ax.set_title('Material Breakdown by Quantity', fontsize=14, fontweight='bold', pad=20)
            
            # Save to base64
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                plt.savefig(temp_path, dpi=100, bbox_inches='tight', facecolor='white')
                plt.close(fig)
                plt.clf()  # Clear the current figure
                
                # Wait a moment for file to be released
                import time
                time.sleep(0.1)
                
                with open(temp_path, 'rb') as img_file:
                    chart_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                    
                return chart_base64
            finally:
                # Clean up temp file
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                except:
                    pass  # Ignore cleanup errors
                
        except Exception as e:
            print(f"Error generating pie chart: {e}")
            return None
            
    def _generate_timeline_chart(self, session_data):
        """Generate yield timeline chart (placeholder for now)"""
        if not MATPLOTLIB_AVAILABLE:
            return None
            
        try:
            # Create a simple session progress chart
            fig, ax = plt.subplots(figsize=(10, 4))
            fig.patch.set_facecolor('white')
            
            duration = session_data.get('session_duration', 0)
            total_tons = session_data.get('total_tons_mined', 0)
            
            if duration > 0:
                # Create a simple progress line
                time_points = [0, duration/4, duration/2, 3*duration/4, duration]
                cumulative_tons = [0, total_tons*0.2, total_tons*0.5, total_tons*0.8, total_tons]
                
                ax.plot(time_points, cumulative_tons, 'b-o', linewidth=2, markersize=6)
                ax.fill_between(time_points, cumulative_tons, alpha=0.3)
                
                ax.set_xlabel('Session Time (seconds)', fontweight='bold')
                ax.set_ylabel('Cumulative Tons Mined', fontweight='bold')
                ax.set_title('Mining Progress Timeline', fontsize=14, fontweight='bold', pad=20)
                ax.grid(True, alpha=0.3)
                
                # Save to base64
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                    temp_path = temp_file.name
                
                try:
                    plt.savefig(temp_path, dpi=100, bbox_inches='tight', facecolor='white')
                    plt.close(fig)
                    plt.clf()  # Clear the current figure
                    
                    # Wait a moment for file to be released
                    import time
                    time.sleep(0.1)
                    
                    with open(temp_path, 'rb') as img_file:
                        chart_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                        
                    return chart_base64
                finally:
                    # Clean up temp file
                    try:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                    except:
                        pass  # Ignore cleanup errors
                    
        except Exception as e:
            print(f"Error generating timeline chart: {e}")
            return None
        
    def _generate_screenshots_section(self, session_data):
        """Generate screenshots section HTML"""
        screenshots_html = """
        <div class="section">
            <h2>📸 Session Screenshots</h2>
        """
        
        # Get screenshots from session data or prospector panel
        screenshots = session_data.get('screenshots', [])
        
        if not screenshots:
            screenshots_html += "<p><em>No screenshots added to this report. Right-click the report in EliteMining and select 'Generate Detailed Report' to add screenshots.</em></p>"
        else:
            screenshots_html += '<div class="screenshot-gallery">'
            
            for i, screenshot_path in enumerate(screenshots):
                if os.path.exists(screenshot_path):
                    screenshot_base64 = self._encode_image_base64(screenshot_path)
                    if screenshot_base64:
                        filename = os.path.basename(screenshot_path)
                        screenshots_html += f"""
                        <div class="screenshot">
                            <img src="data:image/png;base64,{screenshot_base64}" alt="Screenshot {i+1}" title="Click to view full size">
                            <p><strong>{filename}</strong></p>
                        </div>
                        """
                else:
                    screenshots_html += f"""
                    <div class="screenshot">
                        <p><em>Screenshot not found: {os.path.basename(screenshot_path)}</em></p>
                    </div>
                    """
            
            screenshots_html += '</div>'
            
        screenshots_html += "</div>"
        return screenshots_html
        
    def _generate_statistics_section(self, session_data):
        """Generate overall statistics section HTML"""
        statistics_html = """
        <div class="section">
            <h2>📊 Overall Mining Statistics</h2>
        """
        
        try:
            # Try to import and use mining statistics
            from mining_statistics import SessionAnalytics
            
            # Create analytics instance and load existing data
            analytics = SessionAnalytics()
            stats = analytics.calculate_statistics()
            
            if stats and stats.get('total_sessions', 0) > 0:
                statistics_html += """
                <div class="stats-grid">
                """
                
                # Add key lifetime statistics
                statistics_html += f"""
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_sessions', 0)}</div>
                    <div class="stat-label">Total Sessions</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{self._safe_float(stats.get('total_tonnage', 0)):.1f}</div>
                    <div class="stat-label">Lifetime Tonnage</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{self._safe_float(stats.get('avg_tonnage_per_session', 0)):.1f}</div>
                    <div class="stat-label">Avg Tons/Session</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{self._safe_float(stats.get('avg_hit_rate', 0)):.1f}%</div>
                    <div class="stat-label">Avg Hit Rate</div>
                </div>
                """
                
                # Best session info
                best_session = stats.get('best_session', {})
                if best_session:
                    statistics_html += f"""
                    <div class="stat-card">
                        <div class="stat-value">{self._safe_float(best_session.get('tonnage', 0)):.1f}</div>
                        <div class="stat-label">Best Session (tons)</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{self._safe_float(best_session.get('tph', 0)):.1f}</div>
                        <div class="stat-label">Best TPH</div>
                    </div>
                    """
                
                # Most collected material
                most_material = stats.get('most_collected_material', 'None')
                statistics_html += f"""
                <div class="stat-card">
                    <div class="stat-value">{most_material}</div>
                    <div class="stat-label">Most Collected</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_asteroids', 0)}</div>
                    <div class="stat-label">Total Asteroids</div>
                </div>
                """
                
                statistics_html += "</div>"
                
                # Add performance comparison for current session
                current_tonnage = session_data.get('total_tons_mined', 0)
                avg_tonnage = stats.get('avg_tonnage_per_session', 0)
                
                if current_tonnage > 0 and avg_tonnage > 0:
                    performance_pct = ((current_tonnage - avg_tonnage) / avg_tonnage) * 100
                    performance_text = f"{performance_pct:+.1f}%" 
                    performance_color = "#27ae60" if performance_pct >= 0 else "#e74c3c"
                    
                    statistics_html += f"""
                    <div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; text-align: center;">
                        <h4>Session Performance vs Average</h4>
                        <span style="font-size: 24px; font-weight: bold; color: {performance_color};">{performance_text}</span>
                        <p style="margin: 5px 0 0 0; color: #7f8c8d;">
                            Current: {self._safe_float(current_tonnage):.1f}t | Average: {self._safe_float(avg_tonnage):.1f}t
                        </p>
                    </div>
                    """
                    
            else:
                # Try to get basic statistics from the main app's prospector panel
                if hasattr(self.main_app, 'prospector_panel'):
                    try:
                        # Use the same method the Statistics tab uses
                        statistics_html += f"""
                        <div style="background: var(--section-bg); padding: 15px; border-radius: 8px; margin: 20px 0; color: var(--text-color);">
                            <h4 style="margin-top: 0; color: var(--header-color);">Session Overview</h4>
                            <p style="color: var(--text-color);"><strong>System:</strong> {session_data.get('system', 'Unknown')}</p>
                            <p style="color: var(--text-color);"><strong>Body:</strong> {session_data.get('body', 'Unknown')}</p>
                            <p style="color: var(--text-color);"><strong>Total Tonnage:</strong> {session_data.get('tons', 0)}t</p>
                            <p style="color: var(--text-color);"><strong>TPH:</strong> {session_data.get('tph', 0)}</p>
                            <p style="color: var(--text-color);"><strong>Duration:</strong> {session_data.get('duration', 'Unknown')}</p>
                        </div>
                        """
                    except:
                        statistics_html += "<p><em>Basic session data displayed above</em></p>"
                else:
                    statistics_html += "<p><em>No historical statistics available</em></p>"
                
        except Exception as e:
            print(f"Error generating statistics: {e}")
            statistics_html += f"<p><em>Error loading statistics: {e}</em></p>"
            
        statistics_html += "</div>"
        return statistics_html
        
    def _parse_duration_to_minutes(self, duration_str):
        """Parse duration string like '06:43' to minutes for calculations"""
        try:
            if ':' in duration_str:
                parts = duration_str.split(':')
                if len(parts) >= 2:
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    return hours * 60 + minutes
            return 0
        except:
            return 0
        
    def _generate_advanced_analytics_section(self, session_data):
        """Generate advanced mining analytics section HTML"""
        analytics_html = """
        <div class="section">
            <h2>🎯 Advanced Mining Analytics</h2>
        """
        
        try:
            # Use correct field names from CSV/reports tab data
            tons_value = session_data.get('tons', 0)
            if isinstance(tons_value, str):
                try:
                    total_tons = float(tons_value)
                except:
                    total_tons = 0.0
            else:
                total_tons = float(tons_value) if tons_value is not None else 0.0
            
            duration_str = session_data.get('duration', '0:0')
            # Parse duration string to minutes for calculations
            duration_minutes = self._parse_duration_to_minutes(duration_str) if duration_str else 0
            
            prospectors_value = session_data.get('prospectors', 0)
            if isinstance(prospectors_value, str):
                try:
                    prospectors_used = int(prospectors_value) if prospectors_value != '—' else 0
                except:
                    prospectors_used = 0
            else:
                prospectors_used = prospectors_value
                
            materials_mined = session_data.get('materials_mined', {})
            
            # Check if we have CSV data with detailed analytics
            hit_rate = None
            avg_quality = None
            asteroids_prospected = None
            best_material = None
            
            # Try to extract from CSV data if available
            if 'hit_rate_percent' in session_data:
                hit_rate = session_data.get('hit_rate_percent')
            if 'avg_quality_percent' in session_data:
                avg_quality = session_data.get('avg_quality_percent')
            if 'asteroids_prospected' in session_data:
                asteroids_prospected = session_data.get('asteroids_prospected')
            if 'best_material' in session_data:
                best_material = session_data.get('best_material')
            
            # Try to parse session text file for detailed analytics if CSV data not available
            session_text_data = self._parse_session_analytics_from_text(session_data)
            if session_text_data:
                if hit_rate is None:
                    hit_rate = session_text_data.get('hit_rate')
                if avg_quality is None:
                    avg_quality = session_text_data.get('avg_quality')
                if asteroids_prospected is None:
                    asteroids_prospected = session_text_data.get('asteroids_prospected')
                if best_material is None:
                    best_material = session_text_data.get('best_material')
            
            # Convert string values to floats to avoid formatting errors
            if hit_rate is not None and isinstance(hit_rate, str):
                try:
                    hit_rate = float(hit_rate)
                except:
                    hit_rate = None
            
            if avg_quality is not None and isinstance(avg_quality, str):
                try:
                    avg_quality = float(avg_quality)
                except:
                    avg_quality = None
                    
            if asteroids_prospected is not None and isinstance(asteroids_prospected, str):
                try:
                    asteroids_prospected = int(asteroids_prospected)
                except:
                    asteroids_prospected = None
            
            # Prospecting Performance Section
            if any([hit_rate is not None, avg_quality is not None, asteroids_prospected is not None]):
                analytics_html += """
                <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                    <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">⛏️ Prospecting Performance</h3>
                    <div class="stats-grid">
                """
                
                if hit_rate is not None:
                    analytics_html += f"""
                    <div class="stat-card">
                        <div class="stat-value">{self._safe_float(hit_rate):.1f}%</div>
                        <div class="stat-label">Hit Rate</div>
                    </div>
                    """
                
                if avg_quality is not None:
                    analytics_html += f"""
                    <div class="stat-card">
                        <div class="stat-value">{self._safe_float(avg_quality):.1f}%</div>
                        <div class="stat-label">Average Quality</div>
                    </div>
                    """
                
                if asteroids_prospected is not None:
                    analytics_html += f"""
                    <div class="stat-card">
                        <div class="stat-value">{asteroids_prospected}</div>
                        <div class="stat-label">Asteroids Prospected</div>
                    </div>
                    """
                
                if prospectors_used > 0 and asteroids_prospected:
                    efficiency = (asteroids_prospected / prospectors_used) * 100 if prospectors_used > 0 else 0
                    analytics_html += f"""
                    <div class="stat-card">
                        <div class="stat-value">{self._safe_float(efficiency):.0f}%</div>
                        <div class="stat-label">Prospector Efficiency</div>
                    </div>
                    """
                
                analytics_html += "</div></div>"
            
            # Material Analysis Section
            if materials_mined:
                analytics_html += """
                <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                    <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">💎 Material Analysis</h3>
                """
                
                # Sort materials by quantity for analysis
                sorted_materials = sorted(materials_mined.items(), key=lambda x: x[1], reverse=True)
                
                # Top material stats
                if sorted_materials:
                    top_material, top_quantity = sorted_materials[0]
                    top_percentage = (top_quantity / total_tons) * 100 if total_tons > 0 else 0
                    
                    analytics_html += f"""
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value">{top_material}</div>
                            <div class="stat-label">Top Material</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{self._safe_float(top_quantity):.1f}t</div>
                            <div class="stat-label">Top Material Yield</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{self._safe_float(top_percentage):.1f}%</div>
                            <div class="stat-label">% of Total Yield</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{len(materials_mined)}</div>
                            <div class="stat-label">Material Diversity</div>
                        </div>
                    </div>
                    """
                
                # Check for manual refinery materials
                refinery_materials = self._identify_manual_materials(session_data)
                if refinery_materials:
                    analytics_html += f"""
                    <div style="margin-top: 15px; padding: 15px; background: var(--comment-bg); border-radius: 8px; border: 1px solid var(--comment-border);">
                        <h4 style="margin-top: 0; color: var(--header-color);">📦 Manual Refinery Additions</h4>
                        <p style="color: var(--text-color); margin-bottom: 10px;"><strong>Materials manually added from refinery:</strong></p>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                    """
                    
                    for material, quantity in sorted(refinery_materials.items(), key=lambda x: x[1], reverse=True):
                        percentage = (quantity / total_tons) * 100 if total_tons > 0 else 0
                        analytics_html += f"""
                        <div style="background: var(--card-bg); padding: 10px; border-radius: 5px; border: 1px solid var(--card-border); text-align: center;">
                            <div style="font-weight: bold; color: var(--stat-value-color);">{material}</div>
                            <div style="color: var(--text-color);">{self._safe_float(quantity):.1f}t ({self._safe_float(percentage):.1f}%)</div>
                        </div>
                        """
                    
                    total_manual = sum(refinery_materials.values())
                    manual_percentage = (total_manual / total_tons) * 100 if total_tons > 0 else 0
                    analytics_html += f"""
                        </div>
                        <p style="margin-top: 10px; text-align: center; color: var(--text-color);"><strong>Total Manual: {self._safe_float(total_manual):.1f}t ({self._safe_float(manual_percentage):.1f}% of session)</strong></p>
                    </div>
                    """
                
                analytics_html += "</div>"
            
            # Efficiency Metrics Section
            if duration_minutes > 0 and total_tons > 0:
                analytics_html += """
                <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                    <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">⚡ Efficiency Breakdown</h3>
                    <div style="background: #2a2a2a; padding: 12px; border-radius: 6px; margin-bottom: 15px; border-left: 4px solid #4CAF50;">
                        <p style="color: #cccccc; margin: 0; font-size: 13px;">
                            <strong>💡 Understanding Your Mining Metrics:</strong><br>
                            These metrics help you evaluate and compare different mining sessions. Hover over each card for detailed explanations.
                        </p>
                    </div>
                    <div class="stats-grid">
                """
                
                # Calculate various efficiency metrics using correct TPH from session data
                tph_value = session_data.get('tph', 0)
                if isinstance(tph_value, str):
                    try:
                        tph = float(tph_value)
                    except:
                        tph = (total_tons / (duration_minutes / 60)) if duration_minutes > 0 else 0
                else:
                    tph = tph_value
                
                if prospectors_used > 0:
                    tons_per_prospector = total_tons / prospectors_used
                    analytics_html += f"""
                    <div class="stat-card" title="How efficient your prospector limpets are. Shows tons of valuable materials found per prospector limpet used. Higher numbers mean you're better at targeting asteroids with good materials rather than wasting prospectors on empty rocks.">
                        <div class="stat-value">{self._safe_float(tons_per_prospector):.1f}t</div>
                        <div class="stat-label">Efficiency per Prospector</div>
                        <div class="stat-help">💡 Tons found per prospector used</div>
                    </div>
                    """
                
                if asteroids_prospected and asteroids_prospected > 0:
                    tons_per_asteroid = total_tons / asteroids_prospected
                    analytics_html += f"""
                    <div class="stat-card" title="Average tons of valuable materials found per asteroid that you prospected. This shows how good you are at selecting profitable asteroids. Higher values indicate better asteroid selection skills.">
                        <div class="stat-value">{self._safe_float(tons_per_asteroid):.1f}t</div>
                        <div class="stat-label">Tons/Asteroid</div>
                        <div class="stat-help">🎯 Average yield per asteroid prospected</div>
                    </div>
                    """
                
                # Time efficiency
                if len(materials_mined) > 0:
                    materials_per_hour = len(materials_mined) / (duration_minutes / 60)
                    analytics_html += f"""
                    <div class="stat-card" title="How many different types of materials you're discovering per hour of mining. Higher numbers suggest you're mining in a diverse asteroid field with variety. Some miners prefer focused mining (few types, high volume) while others prefer variety (many types for different uses).">
                        <div class="stat-value">{self._safe_float(materials_per_hour):.1f}</div>
                        <div class="stat-label">Material Types/Hour</div>
                        <div class="stat-help">🔍 Different materials found per hour</div>
                    </div>
                    """
                
                # Session intensity rating
                intensity = "Low"
                intensity_explanation = ""
                if tph > 100:
                    intensity = "High"
                    intensity_explanation = f"High activity mining - {tph:.1f} tons/hour"
                elif tph > 50:
                    intensity = "Medium"
                    intensity_explanation = f"Moderate activity mining - {tph:.1f} tons/hour"
                else:
                    intensity_explanation = f"Relaxed mining pace - {tph:.1f} tons/hour"
                
                analytics_html += f"""
                <div class="stat-card" title="Mining activity level based on your tons per hour rate. High (>100 t/h) = intense active mining, Medium (50-100 t/h) = steady mining, Low (<50 t/h) = casual mining with breaks or lower efficiency.">
                    <div class="stat-value">{intensity}</div>
                    <div class="stat-label">Session Intensity</div>
                    <div class="stat-help">⚡ {intensity_explanation}</div>
                </div>
                """
                
                analytics_html += "</div></div>"
            
            # Session Benchmarking (if we have access to historical data)
            benchmark_html = self._generate_session_benchmarking(session_data)
            if benchmark_html:
                analytics_html += benchmark_html
                
        except Exception as e:
            print(f"Error generating advanced analytics: {e}")
            analytics_html += f"""
            <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; border: 1px solid #f5c6cb;">
                <p><strong>Error:</strong> Could not generate advanced analytics: {str(e)}</p>
            </div>
            """
        
        analytics_html += "</div>"
        return analytics_html
        
    def _identify_manual_materials(self, session_data):
        """Identify materials that were manually added from refinery"""
        try:
            session_file_path = session_data.get('session_file_path')
            if not session_file_path or not os.path.exists(session_file_path):
                return {}
            
            with open(session_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            manual_materials = {}
            
            # Look for manual refinery additions indicators
            # Check for specific patterns that indicate manual addition
            import re
            
            # Pattern 1: Look for "Added refinery materials" messages
            refinery_matches = re.findall(r'Added refinery materials.*?({.*?})', content, re.DOTALL)
            for match in refinery_matches:
                try:
                    # Parse the materials dict if it's in a readable format
                    # This would need to be adapted based on actual logging format
                    pass
                except:
                    continue
            
            # Pattern 2: Check if session mentions "refinery" or "manual"
            if any(keyword in content.lower() for keyword in ['refinery', 'manual', 'added']):
                # Try to identify by checking for sudden material additions
                # or specific markers in the session text
                pass
            
            # Pattern 3: Look for cargo breakdown vs refined materials discrepancies
            # Parse REFINED MATERIALS section
            refined_section = re.search(r'=== REFINED MATERIALS ===(.*?)(?:===|\Z)', content, re.DOTALL)
            if refined_section:
                refined_materials = {}
                refined_text = refined_section.group(1)
                
                # Parse refined materials: " - Painite 12t (125.75 t/hr)"
                material_matches = re.findall(r' - ([A-Za-z\s]+)\s+(\d+(?:\.\d+)?)t', refined_text)
                for mat_name, quantity in material_matches:
                    refined_materials[mat_name.strip()] = float(quantity)
            
            # Parse CARGO MATERIAL BREAKDOWN section  
            cargo_section = re.search(r'=== CARGO MATERIAL BREAKDOWN ===(.*?)(?:===|\Z)', content, re.DOTALL)
            if cargo_section:
                cargo_materials = {}
                cargo_text = cargo_section.group(1)
                
                # Parse cargo materials: "Platinum: 32t"
                material_matches = re.findall(r'^([A-Za-z\s]+):\s*(\d+(?:\.\d+)?)t\s*$', cargo_text, re.MULTILINE)
                for mat_name, quantity in material_matches:
                    cargo_materials[mat_name.strip()] = float(quantity)
            
            # For now, we'll assume all materials listed are legitimate mining results
            # In the future, this could be enhanced by comparing session start/end snapshots
            # or looking for specific manual addition markers in the logs
            
            # Check if there are any indications this session had manual additions
            # by looking for keywords or specific patterns
            if ('manual' in content.lower() or 
                'refinery' in content.lower() or 
                'added' in content.lower()):
                # If we suspect manual additions but can't parse them specifically,
                # return empty for now but this could be enhanced
                pass
            
            return manual_materials
            
        except Exception as e:
            print(f"Error identifying manual materials: {e}")
            return {}
        
    def _parse_session_analytics_from_text(self, session_data):
        """Parse detailed analytics from session text file"""
        try:
            session_file_path = session_data.get('session_file_path')
            if not session_file_path or not os.path.exists(session_file_path):
                return None
            
            with open(session_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            analytics_data = {}
            
            # Parse hit rate
            import re
            hit_rate_match = re.search(r'Hit Rate:\s*([\d.]+)%', content)
            if hit_rate_match:
                analytics_data['hit_rate'] = float(hit_rate_match.group(1))
            
            # Parse average quality
            avg_quality_match = re.search(r'Average Quality:\s*([\d.]+)%', content)
            if avg_quality_match:
                analytics_data['avg_quality'] = float(avg_quality_match.group(1))
            
            # Parse asteroids prospected
            asteroids_match = re.search(r'(\d+)\s+asteroids? prospected', content, re.IGNORECASE)
            if asteroids_match:
                analytics_data['asteroids_prospected'] = int(asteroids_match.group(1))
            
            # Parse best material
            best_material_match = re.search(r'Best Material:\s*([^(\n]+)', content)
            if best_material_match:
                analytics_data['best_material'] = best_material_match.group(1).strip()
            
            return analytics_data if analytics_data else None
            
        except Exception as e:
            print(f"Error parsing session analytics: {e}")
            return None
        
    def _generate_session_benchmarking(self, session_data):
        """Generate session benchmarking comparison"""
        try:
            # Try to import and use mining statistics for comparison
            from mining_statistics import SessionAnalytics
            
            analytics = SessionAnalytics()
            stats = analytics.calculate_statistics()
            
            if not stats or stats.get('total_sessions', 0) < 2:
                return None
            
            # Use correct field names
            tons_value = session_data.get('tons', 0)
            if isinstance(tons_value, str):
                try:
                    current_tons = float(tons_value)
                except:
                    current_tons = 0.0
            else:
                current_tons = float(tons_value) if tons_value is not None else 0.0
                
            tph_value = session_data.get('tph', 0)
            if isinstance(tph_value, str):
                try:
                    current_tph = float(tph_value)
                except:
                    current_tph = 0.0
            else:
                current_tph = float(tph_value) if tph_value is not None else 0.0
            
            avg_tons = stats.get('avg_tonnage_per_session', 0)
            best_tons = stats.get('best_session', {}).get('tonnage', 0)
            best_tph = stats.get('best_session', {}).get('tph', 0)
            
            benchmark_html = """
            <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">🏆 Session Benchmarking</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
            """
            
            # Tonnage comparison
            if avg_tons > 0:
                tonnage_vs_avg = ((current_tons - avg_tons) / avg_tons) * 100
                tonnage_color = "#27ae60" if tonnage_vs_avg >= 0 else "#e74c3c"
                tonnage_icon = "📈" if tonnage_vs_avg >= 0 else "📉"
                
                benchmark_html += f"""
                <div style="background: var(--card-bg); padding: 15px; border-radius: 8px; border: 1px solid var(--card-border); text-align: center;">
                    <div style="font-size: 24px;">{tonnage_icon}</div>
                    <div style="font-weight: bold; color: {tonnage_color}; font-size: 18px;">{tonnage_vs_avg:+.1f}%</div>
                    <div style="color: var(--text-color); font-size: 12px; margin-top: 5px;">vs Average Tonnage</div>
                    <div style="color: var(--text-color); font-size: 11px;">Current: {self._safe_float(current_tons):.1f}t | Avg: {self._safe_float(avg_tons):.1f}t</div>
                </div>
                """
            
            # TPH comparison
            if current_tph > 0 and best_tph > 0:
                tph_vs_best = (current_tph / best_tph) * 100
                tph_icon = "🚀" if tph_vs_best >= 80 else "⚡" if tph_vs_best >= 50 else "🐌"
                
                benchmark_html += f"""
                <div style="background: var(--card-bg); padding: 15px; border-radius: 8px; border: 1px solid var(--card-border); text-align: center;">
                    <div style="font-size: 24px;">{tph_icon}</div>
                    <div style="font-weight: bold; color: var(--stat-value-color); font-size: 18px;">{self._safe_float(tph_vs_best):.0f}%</div>
                    <div style="color: var(--text-color); font-size: 12px; margin-top: 5px;">of Best TPH</div>
                    <div style="color: var(--text-color); font-size: 11px;">Current: {self._safe_float(current_tph):.1f} | Best: {self._safe_float(best_tph):.1f}</div>
                </div>
                """
            
            # Session ranking
            total_sessions = stats.get('total_sessions', 0)
            # Estimate ranking based on tonnage (simplified)
            estimated_rank = max(1, min(total_sessions, int(total_sessions * (1 - (current_tons / max(best_tons, 1))))))
            rank_suffix = "st" if estimated_rank == 1 else "nd" if estimated_rank == 2 else "rd" if estimated_rank == 3 else "th"
            
            benchmark_html += f"""
            <div style="background: var(--card-bg); padding: 15px; border-radius: 8px; border: 1px solid var(--card-border); text-align: center;">
                <div style="font-size: 24px;">🏅</div>
                <div style="font-weight: bold; color: var(--stat-value-color); font-size: 18px;">#{estimated_rank}{rank_suffix}</div>
                <div style="color: var(--text-color); font-size: 12px; margin-top: 5px;">Estimated Rank</div>
                <div style="color: var(--text-color); font-size: 11px;">out of {total_sessions} sessions</div>
            </div>
            """
            
            benchmark_html += "</div></div>"
            return benchmark_html
            
        except Exception as e:
            print(f"Error generating benchmarking: {e}")
            return None
        
    def _generate_comment_section(self, session_data):
        """Generate comment section HTML"""
        comment = session_data.get('comment', '').strip()
        
        if comment:
            # Escape HTML characters for security
            import html
            escaped_comment = html.escape(comment)
            
            comment_html = f"""
        <div class="section">
            <h2>💬 Session Comments</h2>
            <div class="comment-section">
                <h3>Notes & Observations</h3>
                <div class="comment-text">{escaped_comment}</div>
            </div>
        </div>
            """
        else:
            comment_html = f"""
        <div class="section">
            <h2>💬 Session Comments</h2>
            <div class="comment-section">
                <h3>Notes & Observations</h3>
                <div class="comment-text no-comment">No comments recorded for this session</div>
            </div>
        </div>
            """
        
        return comment_html
        
    def _generate_materials_table(self, session_data):
        """Generate materials breakdown table"""
        materials_mined = session_data.get('materials_mined', {})
        if not materials_mined:
            return "<p>No materials mined this session</p>"
            
        table_html = """
        <table class="data-table">
            <thead>
                <tr>
                    <th>Material</th>
                    <th>Quantity (tons)</th>
                    <th>Percentage</th>
                </tr>
            </thead>
            <tbody>
        """
        
        total_tons = sum(materials_mined.values())
        for material, quantity in sorted(materials_mined.items(), key=lambda x: x[1], reverse=True):
            percentage = (quantity / total_tons * 100) if total_tons > 0 else 0
            table_html += f"""
                <tr>
                    <td>{material}</td>
                    <td>{quantity:.1f}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
            """
            
        table_html += """
            </tbody>
        </table>
        """
        
        return table_html
        
    def _generate_raw_data_table(self, session_data):
        """Generate raw session data table"""
        if not session_data:
            return "<p>No session data available</p>"
            
        start_snapshot = session_data.get('start_snapshot', {})
        end_snapshot = session_data.get('end_snapshot', {})
        
        table_html = """
        <table class="data-table">
            <thead>
                <tr>
                    <th>Property</th>
                    <th>Value</th>
                </tr>
            </thead>
            <tbody>
        """
        
        # Determine session timing information
        session_start = "Unknown"
        session_end = "Unknown"
        
        if start_snapshot.get('timestamp'):
            session_start = datetime.fromtimestamp(start_snapshot.get('timestamp')).strftime("%Y-%m-%d %H:%M:%S")
        elif session_data.get('date') and session_data.get('date') != 'Unknown':
            session_start = f"{session_data.get('date')} (Date from report)"
        
        if end_snapshot.get('timestamp'):
            session_end = datetime.fromtimestamp(end_snapshot.get('timestamp')).strftime("%Y-%m-%d %H:%M:%S")
        elif session_data.get('date') != 'Unknown' and session_data.get('duration') != '00:00:00':
            session_end = f"Start + {session_data.get('duration')} duration"
        
        # Build properties list based on available data
        properties = []
        
        # Always show these if we have detailed report data
        if session_data.get('data_source') == 'Report Entry':
            # Detailed report from tree data - show relevant mining statistics
            materials_count = len(session_data.get('materials_mined', {}))
            materials_list = ', '.join(session_data.get('materials_mined', {}).keys()) if materials_count > 0 else 'None recorded'
            
            properties.extend([
                ("Report Date", session_data.get('date', 'Unknown')),
                ("Session Duration", session_data.get('duration', 'Unknown')),
                ("Mining Location", f"{session_data.get('system', 'Unknown')} - {session_data.get('body', 'Unknown')}"),
                ("Materials Found", f"{materials_count} types: {materials_list}"),
                ("Data Source", "Report entry from mining log")
            ])
        else:
            # Original detailed session data - only show cargo if we have meaningful data
            cargo_available = (start_snapshot.get('total_cargo', 0) > 0 or 
                             end_snapshot.get('total_cargo', 0) > 0 or 
                             start_snapshot.get('max_cargo', 0) > 0)
            
            properties.extend([
                ("Session Start", session_start),
                ("Session End", session_end),
                ("Data Source", "Detailed mining session data")
            ])
            
            # Only add cargo information if we have meaningful data
            if cargo_available:
                properties.extend([
                    ("Start Cargo", f"{start_snapshot.get('total_cargo', 0)} tons"),
                    ("End Cargo", f"{end_snapshot.get('total_cargo', 0)} tons"),
                    ("Max Cargo", f"{start_snapshot.get('max_cargo', 0)} tons")
                ])
            else:
                properties.append(("Cargo Tracking", "Not available for this session"))
        
        for prop, value in properties:
            table_html += f"""
                <tr>
                    <td>{prop}</td>
                    <td>{value}</td>
                </tr>
            """
            
        table_html += """
            </tbody>
        </table>
        """
        
        return table_html
        
    def preview_report(self, html_content):
        """Preview report in system browser"""
        try:
            # Create temporary HTML file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(html_content)
                temp_path = f.name
                
            # Open in default browser
            webbrowser.open(f'file://{temp_path}')
            return temp_path
            
        except Exception as e:
            print(f"Error previewing report: {e}")
            return None
            
    def save_report(self, html_content, session_filename):
        """Save HTML report to Reports folder"""
        try:
            # Generate HTML filename from session filename
            if session_filename.endswith('.txt'):
                html_filename = session_filename.replace('.txt', '.html')
            elif session_filename.endswith('.html'):
                html_filename = session_filename
            else:
                html_filename = f"{session_filename}.html"
                
            html_path = os.path.join(self.enhanced_reports_dir, html_filename)
            
            # Save HTML file
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            return html_path
            
        except Exception as e:
            print(f"Error saving report: {e}")
            return None