"""
Detailed Report Generator for EliteMining
Generates HTML reports with charts, statistics, and screenshots
"""

import json
import logging
import os
import re
import sys
import base64
import webbrowser
import tempfile
from datetime import datetime
from pathlib import Path

# Set up logging for this module
log = logging.getLogger(__name__)

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
    # Material-specific TPH thresholds for fair scoring across different materials
    # Each material has different natural yield rates, so "Excellent" means different TPH
    MATERIAL_TPH_THRESHOLDS = {
        # Metallic Ring (Laser Mining) - ordered by yield potential
        'Platinum': {'excellent': 800, 'good': 600, 'fair': 400},
        'Painite': {'excellent': 600, 'good': 450, 'fair': 300},
        'Osmium': {'excellent': 400, 'good': 300, 'fair': 200},
        'Palladium': {'excellent': 400, 'good': 300, 'fair': 200},
        'Gold': {'excellent': 350, 'good': 250, 'fair': 150},
        'Silver': {'excellent': 350, 'good': 250, 'fair': 150},
        
        # Icy Ring (Laser Mining)
        'Bromellite': {'excellent': 500, 'good': 350, 'fair': 200},
        'Tritium': {'excellent': 400, 'good': 300, 'fair': 200},
        
        # Core Mining (any ring) - much lower TPH is normal
        'Void Opals': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Low Temperature Diamonds': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Alexandrite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Musgravite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Monazite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Benitoite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Serendibite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Grandidierite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
        'Rhodplumsite': {'excellent': 120, 'good': 90, 'fair': 60, 'is_core': True},
    }
    
    # Default thresholds for unknown materials (use Platinum as baseline)
    DEFAULT_THRESHOLDS = {'excellent': 800, 'good': 600, 'fair': 400}
    
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
        self.log = logging.getLogger(__name__)

    def _derive_total_finds(self, session_data):
        """Derive/return total hits (number of asteroids that contained tracked materials)

        Priority:
        1. session_data['total_finds'] explicit numeric field
        2. derive from 'hit_rate' and 'asteroids_prospected' (rounded)
        3. sum 'hits' from mineral_performance data
        4. return None if not derivable
        """
        try:
            # Explicit value if present
            explicit_total = None
            if 'total_finds' in session_data and session_data.get('total_finds') not in (None, '', '—'):
                try:
                    raw = str(session_data.get('total_finds')).strip()
                    # Extract digits from common formats (e.g., '5', '5x')
                    m = re.search(r"(\d+)", raw)
                    if m:
                        explicit_total = int(m.group(1))
                    else:
                        explicit_total = int(float(raw))
                except Exception:
                    explicit_total = None
            # If explicit value is provided and >0, prefer it. If explicit is 0, prefer derived if available.
            if explicit_total is not None and explicit_total > 0:
                return explicit_total

            # Derive from hit rate and asteroids prospected
            ap_raw = session_data.get('asteroids_prospected') or session_data.get('asteroids') or session_data.get('prospects') or session_data.get('prospected')
            hr_raw = session_data.get('hit_rate') or session_data.get('hit_rate_percent')
            if ap_raw not in (None, '', '—') and hr_raw not in (None, '', '—'):
                try:
                    ap_val = int(str(ap_raw).strip())
                except Exception:
                    ap_val = 0
                try:
                    hr_val = float(str(hr_raw).replace('%', '').strip())
                except Exception:
                    hr_val = 0.0

                if ap_val > 0 and hr_val > 0:
                    derived = int(round(ap_val * (hr_val / 100.0)))
                    if derived > 0:
                        return derived

            # Try to sum from mineral_performance data
            mineral_perf = session_data.get('mineral_performance', {})
            if mineral_perf and isinstance(mineral_perf, dict):
                total_hits = 0
                for material_data in mineral_perf.values():
                    if isinstance(material_data, dict):
                        hits = material_data.get('hits') or material_data.get('total_hits') or material_data.get('count') or material_data.get('finds')
                        if hits:
                            try:
                                total_hits += int(hits)
                            except Exception:
                                pass
                if total_hits > 0:
                    return total_hits
            
            # Try to build and sum from material TPA entries (this will use the latest logic)
            try:
                material_entries = self._build_material_tpa_entries(session_data)
                if material_entries:
                    total_from_entries = sum(e['hits'] for e in material_entries if e['hits'] and not e.get('hits_estimated'))
                    if total_from_entries > 0:
                        return total_from_entries
            except Exception:
                pass

            # If derived not possible and explicit provided, return explicit (may be 0)
            if explicit_total is not None:
                return explicit_total
            return None
        except Exception:
            return None

    def _compute_tons_per_asteroid(self, session_data):
        """Compute average tons per asteroid using the preferred denominator (hits then prospected)

        Returns (tons_per_asteroid_float_or_None, used_denominator)
        used_denominator can be 'hits', 'prospected' or None
        """
        try:
            # Try to get total tons from known fields
            total_raw = session_data.get('total_tons') if session_data.get('total_tons') is not None else session_data.get('tons') if session_data.get('tons') is not None else session_data.get('total') if session_data.get('total') is not None else 0
            try:
                total_tons = float(str(total_raw).replace('—', '0').replace(',', ''))
            except Exception:
                total_tons = 0.0

            if total_tons <= 0:
                return (None, None)

            # 1) Use explicit hits from derive
            hits = self._derive_total_finds(session_data)
            if hits is not None and hits > 0:
                return (total_tons / hits, 'hits')

            # 2) Try to compute from per-material data
            material_entries = self._build_material_tpa_entries(session_data)
            if material_entries:
                total_material_tons = sum(e['tons'] for e in material_entries if e['tons'])
                total_material_hits = sum(e['hits'] for e in material_entries if e['hits'])
                if total_material_hits > 0 and total_material_tons > 0:
                    return (total_material_tons / total_material_hits, 'hits')

            # 3) Use asteroids_prospected fallback
            ap_raw = session_data.get('asteroids_prospected') or session_data.get('asteroids') or session_data.get('prospects') or session_data.get('prospected')
            try:
                ap_int = int(str(ap_raw).strip())
            except Exception:
                ap_int = 0
            if ap_int > 0:
                return (total_tons / ap_int, 'prospected')

            return (None, None)
        except Exception:
            return (None, None)
        
    def _safe_float(self, value, default=0.0):
        """Safely convert any value to float for formatting"""
        try:
            return float(value)
        except (ValueError, TypeError):
            return default

    def _normalize_material_tons(self, raw_value):
        """Normalize a material value to a float tonnage"""
        if raw_value is None:
            return None

        if isinstance(raw_value, dict):
            for key in ("tons", "quantity", "value", "total"):
                candidate = raw_value.get(key)
                if candidate is not None:
                    return self._normalize_material_tons(candidate)
            return None

        if isinstance(raw_value, str):
            sanitized = raw_value.replace('t', '').replace(',', '').strip()
            if sanitized == '':
                return None
            try:
                return float(sanitized)
            except ValueError:
                return None

        if isinstance(raw_value, (int, float)):
            return float(raw_value)

        return None

    def _get_primary_material_and_thresholds(self, session_data):
        """
        Detect the primary material being mined (by highest TPH) and return appropriate thresholds.
        
        Returns: (primary_material_name, thresholds_dict, is_core_material)
        """
        try:
            materials_mined_raw = session_data.get('materials_mined', {})
            session_duration_hours = session_data.get('session_duration', 0) / 3600.0
            
            if not materials_mined_raw or session_duration_hours <= 0:
                return (None, self.DEFAULT_THRESHOLDS, False)
            
            # Calculate TPH for each material
            material_tphs = {}
            for mat_name, value in materials_mined_raw.items():
                # Skip summary entries
                if mat_name.lower() in ['total cargo collected', 'total', 'cargo collected', 'total refined']:
                    continue
                    
                tons = self._normalize_material_tons(value)
                if tons and tons > 0:
                    tph = tons / session_duration_hours
                    # Expand material name for matching
                    expanded_name = self._expand_material_name(mat_name)
                    material_tphs[expanded_name] = tph
            
            if not material_tphs:
                return (None, self.DEFAULT_THRESHOLDS, False)
            
            # Find material with highest TPH
            primary_material = max(material_tphs, key=material_tphs.get)
            primary_tph = material_tphs[primary_material]
            
            # Get thresholds for this material
            thresholds = self.MATERIAL_TPH_THRESHOLDS.get(primary_material, self.DEFAULT_THRESHOLDS)
            is_core = thresholds.get('is_core', False)
            
            return (primary_material, thresholds, is_core)
            
        except Exception as e:
            log.error(f"Error detecting primary material: {e}")
            return (None, self.DEFAULT_THRESHOLDS, False)

    def _find_performance_entry(self, material_name, perf_data):
        """Find mineral performance entry using fuzzy match on names"""
        if not perf_data:
            return None

        # Exact match (case-sensitive)
        if material_name in perf_data:
            return perf_data[material_name]

        # Case-insensitive exact match
        normalized = material_name.lower().strip()
        for name, value in perf_data.items():
            if name.lower().strip() == normalized:
                return value
        
        # Fuzzy matching (substring, prefix)
        for name, value in perf_data.items():
            lowered = name.lower().strip()
            if lowered.startswith(normalized) or normalized.startswith(lowered):
                return value
            if normalized in lowered or lowered in normalized:
                return value
        
        return None

    def _extract_material_hits(self, perf_entry):
        """Return an integer hit count for a material if available"""
        if perf_entry is None:
            return None

        if isinstance(perf_entry, (int, float)):
            return int(perf_entry)

        if isinstance(perf_entry, str):
            match = re.search(r"(\d+)", perf_entry)
            if match:
                return int(match.group(1))
            return None

        if isinstance(perf_entry, dict):
            for key in ("finds", "hits", "find_count", "finds_count"):
                value = perf_entry.get(key)
                if value is not None:
                    return self._extract_material_hits(value)

        return None

    def _build_material_tpa_entries(self, session_data):
        """Return per-material tons, hits, and tons per asteroid"""
        materials = session_data.get("materials_mined", {}) or {}
        if not materials:
            return []

        perf_data = session_data.get("mineral_performance", {}) or {}
        entries = []

        total_tons = sum([self._normalize_material_tons(v) or 0.0 for v in materials.values()])
        total_finds = None
        try:
            total_finds = int(session_data.get('total_finds') or self._derive_total_finds(session_data) or 0)
        except Exception:
            total_finds = None

        hit_rate_global = None
        try:
            hr = session_data.get('hit_rate') or session_data.get('hit_rate_percent')
            if hr is not None and hr != '—':
                hit_rate_global = float(str(hr).replace('%', '').strip())
        except Exception:
            hit_rate_global = None

        for material_name, raw_value in materials.items():
            tons = self._normalize_material_tons(raw_value)
            if tons is None:
                continue

            perf_entry = self._find_performance_entry(material_name, perf_data)
            hits = self._extract_material_hits(perf_entry)
            hits_estimated = False
            
            # Debug: log when performance entry is not found or has no hits
            if perf_data:
                try:
                    if perf_entry is None:
                        self.log.debug(f"[REPORT] No perf_entry for '{material_name}'. Available in mineral_performance: {list(perf_data.keys())}")
                    else:
                        self.log.debug(f"[REPORT] Material '{material_name}': perf_entry={perf_entry}, extracted hits={hits}, tons={tons}")
                except Exception:
                    pass
            if hits is None or hits == 0:
                # Try estimating hits based on total finds proportionally using tonnage
                if total_finds and total_tons > 0:
                    est = int(round(total_finds * (tons / total_tons)))
                    if est <= 0:
                        est = 1
                    hits = est
                    hits_estimated = True
                elif hit_rate_global is not None and session_data.get('asteroids_prospected'):
                    try:
                        asts = int(session_data.get('asteroids_prospected'))
                        est = int(round(asts * (hit_rate_global / 100.0) * (tons / total_tons))) if total_tons > 0 else None
                        if est and est > 0:
                            hits = est
                            hits_estimated = True
                    except Exception:
                        pass
            # Last-resort fallback: if we still have no valid hits, assign 1 hit per material (estimated)
            if hits is None or hits == 0:
                hits = 1
                hits_estimated = True
            tpa = (tons / hits) if hits and hits > 0 else None
            entries.append({
                "material": material_name,
                "display_name": self._expand_material_name(material_name),
                "tons": tons,
                "hits": hits,
                "hits_estimated": hits_estimated,
                "tpa": tpa
            })
            # Debug log for missing values
            try:
                if (hits is None or hits == 0) or tpa is None:
                    self.log.debug("[REPORT] %s tons=%s hits=%s hits_est=%s tpa=%s total_finds=%s total_tons=%s", material_name, tons, hits, hits_estimated, tpa, total_finds, total_tons)
            except Exception:
                pass

        return sorted(entries, key=lambda e: e["tons"], reverse=True)

    def _expand_material_name(self, name: str) -> str:
        """Expand common material abbreviations to full names for display."""
        if not name:
            return name
        map = {
            # Metallic ring materials
            'plat': 'Platinum', 'pt': 'Platinum', 'platinum': 'Platinum',
            'osmi': 'Osmium', 'os': 'Osmium', 'osmium': 'Osmium',
            'pain': 'Painite', 'pn': 'Painite', 'painite': 'Painite',
            'pd': 'Palladium', 'pall': 'Palladium', 'palladium': 'Palladium',
            'au': 'Gold', 'gold': 'Gold', 'ag': 'Silver', 'silver': 'Silver',
            # Icy ring materials
            'brom': 'Bromellite', 'bromellite': 'Bromellite',
            'trit': 'Tritium', 'tritium': 'Tritium',
            'ltd': 'Low Temperature Diamonds', 'low temperature diamonds': 'Low Temperature Diamonds',
            'lowtemperaturediamonds': 'Low Temperature Diamonds',
            # Core materials
            'vo': 'Void Opals', 'void opals': 'Void Opals', 'voidopals': 'Void Opals',
            'alex': 'Alexandrite', 'alexandrite': 'Alexandrite',
            'musg': 'Musgravite', 'musgravite': 'Musgravite',
            'mono': 'Monazite', 'monazite': 'Monazite',
            'beni': 'Benitoite', 'benitoite': 'Benitoite',
            'seren': 'Serendibite', 'serendibite': 'Serendibite',
            'grand': 'Grandidierite', 'grandidierite': 'Grandidierite',
            'rhod': 'Rhodplumsite', 'rhodplumsite': 'Rhodplumsite',
        }
        key = str(name).strip().lower()
        return map.get(key, name)
        
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
    <meta name="color-scheme" content="light">
    <style>
        * {{
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
            color-adjust: exact;
        }}
        
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
            display: inline-block;
            text-align: center;
            margin: 20px 10px;
            vertical-align: top;
            width: 420px;
        }}
        
        .charts-grid {{
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
        
        /* Engineering Materials Styles */
        .materials-summary-box {{
            background: linear-gradient(135deg, var(--section-bg) 0%, var(--card-bg) 100%);
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid var(--section-border);
            margin: 20px 0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .materials-summary-box h3 {{
            color: var(--header-color);
            margin-top: 0;
            margin-bottom: 15px;
            font-size: 1.4em;
        }}
        
        .summary-text {{
            font-size: 1.1em;
            color: var(--text-color);
            margin: 10px 0;
            line-height: 1.6;
        }}
        
        .summary-total {{
            font-size: 1.2em;
            color: var(--stat-value-color);
            margin: 15px 0 0 0;
        }}
        
        .grade-cell {{
            font-weight: bold;
            vertical-align: middle;
            text-align: center;
            border-right: 2px solid var(--border-color);
        }}
        
        .grade-1 {{
            background-color: #d4edda;
            color: #155724;
        }}
        
        .grade-2 {{
            background-color: #d1ecf1;
            color: #0c5460;
        }}
        
        .grade-3 {{
            background-color: #fff3cd;
            color: #856404;
        }}
        
        .grade-4 {{
            background-color: #f8d7da;
            color: #721c24;
        }}
        
        [data-theme="dark"] .grade-1 {{
            background-color: #2d5a3d;
            color: #a8d5ba;
        }}
        
        [data-theme="dark"] .grade-2 {{
            background-color: #1c4a5e;
            color: #8fd4e8;
        }}
        
        [data-theme="dark"] .grade-3 {{
            background-color: #5e4e1c;
            color: #f0d896;
        }}
        
        [data-theme="dark"] .grade-4 {{
            background-color: #5e1c24;
            color: #f5a5ae;
        }}
        
        @media print {{
            /* Force light theme colors for printing */
            * {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
                color-adjust: exact !important;
            }}
            
            :root, [data-theme="dark"] {{
                --bg-color: white !important;
                --container-bg: white !important;
                --text-color: black !important;
                --header-color: #2c3e50 !important;
                --section-bg: #f8f9fa !important;
                --section-border: #3498db !important;
                --card-bg: white !important;
                --card-border: #dee2e6 !important;
                --stat-value-color: #27ae60 !important;
                --stat-label-color: #7f8c8d !important;
                --table-header-bg: #34495e !important;
                --table-header-color: white !important;
                --table-even-row: #f8f9fa !important;
                --comment-bg: #e8f4fd !important;
                --comment-border: #0066cc !important;
                --comment-text-bg: white !important;
                --comment-text-border: #d1ecf1 !important;
                --border-color: #dee2e6 !important;
            }}
            
            .theme-toggle {{
                display: none !important;
            }}
            
            body {{
                background-color: white !important;
                color: black !important;
            }}
            
            .container {{
                box-shadow: none !important;
                padding: 0 !important;
                background-color: white !important;
            }}
            
            .section {{
                page-break-inside: avoid;
                background-color: #f8f9fa !important;
            }}
            
            .stat-card {{
                page-break-inside: avoid;
            }}
            
            .data-table th {{
                background-color: #34495e !important;
                color: white !important;
            }}
            
            .data-table tr:nth-child(even) {{
                background-color: #f8f9fa !important;
            }}
            
            .header {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
            
            /* Preserve gradient colors for yield cards */
            div[style*="linear-gradient"], div[style*="background:"] {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
            }}
            
            /* Preserve gradient colors for yield cards */
            div[style*="linear-gradient"] {{
                -webkit-print-color-adjust: exact !important;
                print-color-adjust: exact !important;
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
            <h2>📋 Mineral Breakdown</h2>
            {materials_table}
        </div>
        
        {engineering_materials_section}
        
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
            const images = document.querySelectorAll('.chart-container img, .screenshot img, div[style*="flex"] img[alt*="Material Breakdown"]');
            
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
            import time
            
            # Small delay to ensure all data is written (timing issue in compiled version)
            time.sleep(0.2)
            
            # Log incoming session data for debugging
            log.info(f"[Report Generator] Starting report generation...")
            log.info(f"[Report Generator] Session data keys: {list(session_data.keys())}")
            log.info(f"[Report Generator] asteroids_prospected in input: {session_data.get('asteroids_prospected')}")
            
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
            
            # Generate engineering materials section
            engineering_materials_section = self._generate_engineering_materials_section(session_data)
            
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
                engineering_materials_section=engineering_materials_section,
                raw_data_table=raw_data_table
            )
            
            return html_content
            
        except Exception as e:
            log.error(f"Error generating report: {e}")
            import traceback
            log.error(f"Traceback: {traceback.format_exc()}")
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
        
        # Asteroids prospected - try to get from session_data or parse from text file
        asteroids_prospected = session_data.get('asteroids_prospected')
        
        # Debug logging for asteroids_prospected
        log.info(f"[Report Generator] asteroids_prospected from session_data: {asteroids_prospected}")
        
        if asteroids_prospected is None:
            log.info("[Report Generator] asteroids_prospected is None, trying to parse from text file...")
            # Try to parse from session text file
            session_text_data = self._parse_session_analytics_from_text(session_data)
            if session_text_data:
                asteroids_prospected = session_text_data.get('asteroids_prospected')
                log.info(f"[Report Generator] asteroids_prospected from text file: {asteroids_prospected}")
            else:
                log.info("[Report Generator] No session text data found")
        if isinstance(asteroids_prospected, str):
            try:
                asteroids_prospected = int(asteroids_prospected) if asteroids_prospected != '—' else None
                log.info(f"[Report Generator] asteroids_prospected after int conversion: {asteroids_prospected}")
            except:
                asteroids_prospected = None
                log.warning("[Report Generator] Failed to convert asteroids_prospected to int")
        
        # Materials count
        materials_count = session_data.get('materials', 0)
        if isinstance(materials_count, str):
            try:
                materials_count = int(materials_count) if materials_count != '—' else 0
            except:
                materials_count = 0
        
        # Get session type (from cargo data or parse from header as fallback)
        session_type = session_data.get('session_type', '')
        if not session_type:
            # Fallback: Parse from header if session_type not in data
            header = session_data.get('header', '')
            if "(Multi-Session)" in header:
                session_type = "Multi-Session"
            elif "(Single Session)" in header:
                session_type = "Single Session"
            else:
                session_type = "Single Session"  # Default
        else:
            # Clean up session_type (remove parentheses if present)
            session_type = session_type.replace("(", "").replace(")", "")
        
        # Add Total Hits and Tons/Asteroid to session stats
        # Use derive/compute helpers
        derived_hits = self._derive_total_finds(session_data)
        tons_per_asteroid_val, tons_per_source = self._compute_tons_per_asteroid(session_data)

        # Pretty formatting for hits and tons/asteroid
        # Normalize derived_hits display - avoid showing 'None' as string
        if derived_hits is not None:
            total_hits_display = str(derived_hits)
        else:
            raw_total_finds = session_data.get('total_finds')
            if raw_total_finds not in (None, '', '—'):
                try:
                    total_hits_display = str(int(float(str(raw_total_finds).strip())))
                except Exception:
                    total_hits_display = str(raw_total_finds)
            else:
                total_hits_display = '—'
        tons_per_display = f"{self._safe_float(tons_per_asteroid_val):.1f}t" if tons_per_asteroid_val is not None else '—'
        asteroids_display = str(asteroids_prospected) if asteroids_prospected is not None else '—'

        stats_html = f"""
        <div class="stat-card">
            <div class="stat-value">{session_type}</div>
            <div class="stat-label">Session Type</div>
        </div>
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
            <div class="stat-value">{asteroids_display}</div>
            <div class="stat-label">Asteroids Prospected</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{materials_count}</div>
            <div class="stat-label">Mineral Types</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{total_hits_display}</div>
            <div class="stat-label">Total Hits</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{tons_per_display}</div>
            <div class="stat-label">Tons/Asteroid</div>
        </div>
        """
        
        # Add Ship Info card if available
        ship_name = session_data.get('ship_name', '')
        if ship_name:
            # Parse ship name and type from format "Ship Name - Ship Type"
            if ' - ' in ship_name:
                ship_display_name, ship_type = ship_name.rsplit(' - ', 1)
            else:
                ship_display_name = ship_name
                ship_type = ''
            
            # Check for scoring adjustments
            ship_name_lower = ship_name.lower()
            is_type_11 = 'type-11 prospector' in ship_name_lower
            
            # Build adjustment note
            if is_type_11:
                adjustment_note = "⚖️ +50% TPH thresholds"
            else:
                adjustment_note = ""
            
            ship_tooltip = f"Ship used for this mining session: {ship_name}"
            if is_type_11:
                ship_tooltip += ". Type-11 Prospector has faster mining mechanics, so TPH scoring thresholds are increased by 50% (1200/900/600 instead of 800/600/400)."
            
            stats_html += f"""
        <div class="stat-card" title="{ship_tooltip}">
            <div class="stat-value" style="font-size: 1.2em;">{ship_display_name if ship_display_name else ship_type}</div>
            <div class="stat-label">🚀 Ship</div>
            <div class="stat-help">{ship_type if ship_display_name and ship_type else ''}{' • ' + adjustment_note if adjustment_note and ship_type else adjustment_note}</div>
        </div>
        """
        
        return stats_html
        
    def _generate_charts_section(self, session_data):
        """Generate charts section HTML"""
        charts_html = """
        <div class="section">
            <h2>📈 Mining Charts</h2>
            <div class="charts-grid">
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
            
        charts_html += """
            </div>
        </div>"""
        return charts_html

    def _add_saved_charts(self, session_data):
        """Try to add saved charts for this session and return HTML string or None"""
        try:
            # Try to identify the session from session_data
            session_id = self._get_session_id_from_data(session_data)
            if not session_id:
                return None
            
            # Load graph mappings - use same path logic as graph saving
            if self.main_app and hasattr(self.main_app, 'va_root'):
                if getattr(sys, 'frozen', False):
                    # Running as executable (installer version)
                    app_dir = os.path.join(self.main_app.va_root, "app")
                else:
                    # Running as script (development version)
                    app_dir = os.path.dirname(os.path.abspath(__file__))
            else:
                # Fallback
                app_dir = os.path.dirname(__file__)
                
            graphs_dir = os.path.join(app_dir, "Reports", "Mining Session", "Graphs")
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
                            <h3>Mineral Comparison</h3>
                            <img src="data:image/png;base64,{comparison_base64}" alt="Mineral Comparison Chart">
                        </div>
                        """
            
            # Add pie chart for material breakdown (still generated dynamically) - moved to Session Overview
            # pie_chart_base64 = self._generate_pie_chart(session_data)
            # if pie_chart_base64:
            #     charts_html += f"""
            #     <div class="chart-container">
            #         <h3>Material Breakdown</h3>
            #         <img src="data:image/png;base64,{pie_chart_base64}" alt="Material Breakdown Chart">
            #     </div>
            #     """
            
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
            
            ax.set_title('Mineral Breakdown by Quantity', fontsize=14, fontweight='bold', pad=20)
            
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
                        pie_chart_base64 = self._generate_pie_chart(session_data)
                        
                        statistics_html += f"""
                        <div style="background: var(--section-bg); padding: 15px; border-radius: 8px; margin: 20px 0; color: var(--text-color); display: flex; align-items: flex-start; gap: 20px;">
                            <div style="flex: 1;">
                                <h4 style="margin-top: 0; color: var(--header-color);">Session Overview</h4>
                                <p style="color: var(--text-color);"><strong>System:</strong> {session_data.get('system', 'Unknown')}</p>
                                <p style="color: var(--text-color);"><strong>Body:</strong> {session_data.get('body', 'Unknown')}</p>
                                <p style="color: var(--text-color);"><strong>Total Tonnage:</strong> {session_data.get('tons', 0)}t</p>
                                <p style="color: var(--text-color);"><strong>TPH:</strong> {session_data.get('tph', 0)}</p>
                                <p style="color: var(--text-color);"><strong>Duration:</strong> {session_data.get('duration', 'Unknown')}</p>
                            </div>
                            {"<div style='flex-shrink: 0;'><img src='data:image/png;base64," + pie_chart_base64 + "' alt='Mineral Breakdown Chart' style='max-width: 200px; height: auto; border: 1px solid var(--border-color); border-radius: 8px; cursor: pointer;'></div>" if pie_chart_base64 else ""}
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
            # Normalize materials_mined so values are floats (tons) for calculations
            materials_mined = {k: (self._normalize_material_tons(v) or 0.0) for k, v in (materials_mined or {}).items()}
            
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
            
            # Get core asteroids count for mining type detection
            core_asteroids = session_data.get('core_asteroids', 0)
            if session_text_data and core_asteroids == 0:
                core_asteroids = session_text_data.get('core_asteroids', 0)
            # Store in session_data for scoring logic to access
            session_data['core_asteroids'] = core_asteroids
            session_data['asteroids_prospected'] = asteroids_prospected
            
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
            
            # Yield Breakdown Section - Show both comprehensive and filtered yields
            individual_yields = session_data.get('individual_yields', {})
            filtered_yields = session_data.get('filtered_yields', {})
            total_avg_yield = session_data.get('total_average_yield', 0.0)
            
            # Fallback: calculate from individual_yields if not stored
            if not total_avg_yield and individual_yields:
                total_avg_yield = sum(individual_yields.values()) / len(individual_yields)
            
            if individual_yields or filtered_yields or total_avg_yield:
                analytics_html += """
                <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                    <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">📊 Mineral Yield Analysis</h3>
                """
                
                # Show Total Average Yield prominently at the top
                if total_avg_yield and total_avg_yield > 0:
                    # Color code based on yield quality
                    if total_avg_yield >= 15.0:
                        yield_color = "#4CAF50"
                    elif total_avg_yield >= 10.0:
                        yield_color = "#2196F3"
                    elif total_avg_yield >= 5.0:
                        yield_color = "#FF9800"
                    else:
                        yield_color = "#9E9E9E"
                    
                    analytics_html += f"""
                    <div style="text-align: center; margin-bottom: 25px; padding: 20px; background: linear-gradient(135deg, {yield_color}, {yield_color}CC); border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                        <div style="font-size: 48px; font-weight: bold; color: white; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">{self._safe_float(total_avg_yield):.1f}%</div>
                        <div style="font-size: 18px; color: white; margin-top: 10px; font-weight: 600;">Total Average Yield</div>
                        <div style="font-size: 14px; color: rgba(255,255,255,0.9); margin-top: 5px; font-style: italic;">Average yield across all selected materials and prospected asteroids</div>
                    </div>
                    """
                
                # Show filtered yields first if available (announcement threshold based)
                if filtered_yields:
                    analytics_html += """
                    <div style="margin-bottom: 25px;">
                        <h4 style="color: #4CAF50; margin-bottom: 15px; font-size: 16px;">🎯 Asteroids Above Announcement Thresholds</h4>
                        <p style="color: #cccccc; font-size: 14px; margin-bottom: 15px; font-style: italic;">
                            Selected materials that exceeded announcement panel thresholds - your premium finds
                        </p>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                    """
                    
                    # Sort filtered yields by percentage (highest first)
                    sorted_filtered = sorted(filtered_yields.items(), key=lambda x: x[1], reverse=True)
                    
                    for material, yield_percent in sorted_filtered:
                        # Color code based on yield quality - filtered yields tend to be higher
                        if yield_percent >= 30.0:
                            color_style = "background: linear-gradient(135deg, #4CAF50, #45a049); color: white;"
                        elif yield_percent >= 20.0:
                            color_style = "background: linear-gradient(135deg, #2196F3, #1976D2); color: white;"
                        elif yield_percent >= 10.0:
                            color_style = "background: linear-gradient(135deg, #FF9800, #F57C00); color: white;"
                        else:
                            color_style = "background: linear-gradient(135deg, #9E9E9E, #757575); color: white;"
                        
                        analytics_html += f"""
                        <div class="yield-card" style="padding: 12px; border-radius: 6px; text-align: center; {color_style} border: 1px solid rgba(255,255,255,0.2);">
                            <div style="font-size: 14px; font-weight: bold; margin-bottom: 4px;">{self._expand_material_name(material)}</div>
                            <div style="font-size: 18px; font-weight: bold;">{yield_percent:.1f}%</div>
                        </div>
                        """
                    
                    analytics_html += "</div></div>"
                
                # Show comprehensive yields (all asteroids)
                if individual_yields:
                    analytics_html += """
                    <div style="margin-bottom: 15px;">
                        <h4 style="color: #2196F3; margin-bottom: 15px; font-size: 16px;">🌍 All Asteroids Prospected</h4>
                        <p style="color: #cccccc; font-size: 14px; margin-bottom: 15px; font-style: italic;">
                            Selected materials across all prospected asteroids - overall efficiency
                        </p>
                    """
                    
                    # Calculate total average yield for display
                    total_yield = sum(individual_yields.values()) / len(individual_yields) if individual_yields else 0
                    
                    analytics_html += f"""
                        <div style="margin-bottom: 15px;">
                            <div class="stat-card" style="display: inline-block; margin-right: 20px;">
                                <div class="stat-value">{total_yield:.1f}%</div>
                                <div class="stat-label">Total Average Yield</div>
                            </div>
                            <div class="stat-card" style="display: inline-block;">
                                <div class="stat-value">{len(individual_yields)}</div>
                                <div class="stat-label">Materials Analyzed</div>
                            </div>
                        </div>
                        
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                    """
                    
                    # Sort materials by yield percentage (highest first)
                    sorted_yields = sorted(individual_yields.items(), key=lambda x: x[1], reverse=True)
                    
                    for material, yield_percent in sorted_yields:
                        # Color code based on yield quality - comprehensive yields tend to be lower
                        if yield_percent >= 15.0:
                            color_style = "background: linear-gradient(135deg, #4CAF50, #45a049); color: white;"
                        elif yield_percent >= 10.0:
                            color_style = "background: linear-gradient(135deg, #2196F3, #1976D2); color: white;"
                        elif yield_percent >= 5.0:
                            color_style = "background: linear-gradient(135deg, #FF9800, #F57C00); color: white;"
                        else:
                            color_style = "background: linear-gradient(135deg, #9E9E9E, #757575); color: white;"
                        
                        analytics_html += f"""
                        <div class="yield-card" style="padding: 12px; border-radius: 6px; text-align: center; {color_style} border: 1px solid rgba(255,255,255,0.2);">
                            <div style="font-size: 14px; font-weight: bold; margin-bottom: 4px;">{self._expand_material_name(material)}</div>
                            <div style="font-size: 18px; font-weight: bold;">{yield_percent:.1f}%</div>
                        </div>
                        """
                    
                    analytics_html += "</div></div>"
                
                analytics_html += "</div>"
            
            # Material Analysis Section
            if materials_mined:
                analytics_html += """
                <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                    <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">💎 Most Mined Material Analysis</h3>
                """
                
                # Sort materials by quantity for analysis
                sorted_materials = sorted(materials_mined.items(), key=lambda x: (x[1] or 0.0), reverse=True)
                
                # Top material stats
                if sorted_materials:
                    top_material, top_quantity = sorted_materials[0]
                    top_percentage = (top_quantity / total_tons) * 100 if total_tons > 0 else 0
                    
                    analytics_html += f"""
                    <div class="stats-grid">
                            <div class="stat-card">
                                <div class="stat-value">{self._expand_material_name(top_material)}</div>
                            <div class="stat-label">Most Mined Material</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{self._safe_float(top_quantity):.1f}t</div>
                            <div class="stat-label">Tonnage Mined</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{self._safe_float(top_percentage):.1f}%</div>
                            <div class="stat-label">% of Total Tonnage</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">{len(materials_mined)}</div>
                            <div class="stat-label">Total Materials</div>
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
                            <div style="font-weight: bold; color: var(--stat-value-color);">{self._expand_material_name(material)}</div>
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
            
            material_tpa_entries = self._build_material_tpa_entries(session_data)
            if material_tpa_entries:
                row_html = ""
                for entry in material_tpa_entries:
                    hits_display = f"{entry['hits']}" if entry['hits'] is not None else '—'
                    tpa_display = f"{self._safe_float(entry['tpa']):.2f}t" if entry['tpa'] is not None else '—'
                    row_html += f"""
                        <tr>
                            <td>{entry.get('display_name', entry['material'])}</td>
                            <td>{self._safe_float(entry['tons']):.1f}t</td>
                            <td>{hits_display}</td>
                            <td>{tpa_display}</td>
                        </tr>
                    """
                analytics_html += f"""
                <div style=\"background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);\">
                    <h3 style=\"margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;\">🧾 Per-Material Tons/Asteroid</h3>
                    <table class=\"data-table\">
                        <thead>
                            <tr>
                                <th>Material</th>
                                <th>Tonnage</th>
                                <th>Hits</th>
                                <th>Tons/Asteroid</th>
                            </tr>
                        </thead>
                        <tbody>
                            {row_html}
                        </tbody>
                    </table>
                </div>
                """

            # Efficiency Metrics Section
            if duration_minutes > 0 and total_tons > 0:
                # Detect ship type for threshold adjustments
                ship_name_str = session_data.get('ship_name', '').lower()
                is_type_11_ship = 'type-11 prospector' in ship_name_str
                
                # Detect primary material for scoring thresholds
                primary_material, base_thresholds, is_core_material = self._get_primary_material_and_thresholds(session_data)
                
                # Check if this is a core mining session
                core_asteroids_count = session_data.get('core_asteroids', 0)
                asteroids_for_core_check = session_data.get('asteroids_prospected', 0)
                is_core_session = is_core_material
                if not is_core_material and core_asteroids_count > 0 and asteroids_for_core_check > 0:
                    core_ratio = core_asteroids_count / asteroids_for_core_check
                    is_core_session = core_ratio > 0.3
                
                # Build dynamic scoring explanation based on material and ship
                type_11_mult = 1.25 if is_type_11_ship and not is_core_session else 1.0
                
                if is_core_session:
                    scoring_note = f"""<br><br>
                            <strong>⚖️ Core Mining Detected ({primary_material or 'Unknown'}):</strong> TPH thresholds set for core mining (120/90/60 t/hr)."""
                    tph_thresholds = "≥120=70pts, ≥90=50pts, ≥60=30pts, &lt;60=10pts (Core)"
                    tpa_thresholds = "≥20t/ast=30pts, ≥15t/ast=20pts, ≥10t/ast=10pts, &lt;10t/ast=5pts"
                elif is_type_11_ship:
                    exc = int(base_thresholds['excellent'] * type_11_mult)
                    good = int(base_thresholds['good'] * type_11_mult)
                    fair = int(base_thresholds['fair'] * type_11_mult)
                    scoring_note = f"""<br><br>
                            <strong>⚖️ {primary_material or 'Material'} + Type-11:</strong> TPH thresholds adjusted for material type and Type-11 (×1.25)."""
                    tph_thresholds = f"≥{exc}=70pts, ≥{good}=50pts, ≥{fair}=30pts, &lt;{fair}=10pts"
                    tpa_thresholds = "≥25t/ast=30pts, ≥19t/ast=20pts, ≥12t/ast=10pts, &lt;12t/ast=5pts (Type-11)"
                else:
                    exc = base_thresholds['excellent']
                    good = base_thresholds['good']
                    fair = base_thresholds['fair']
                    if primary_material:
                        scoring_note = f"""<br><br>
                            <strong>⚖️ {primary_material} Mining:</strong> TPH thresholds adjusted for this material type."""
                    else:
                        scoring_note = ""
                    tph_thresholds = f"≥{exc}=70pts, ≥{good}=50pts, ≥{fair}=30pts, &lt;{fair}=10pts"
                    tpa_thresholds = "≥20t/ast=30pts, ≥15t/ast=20pts, ≥10t/ast=10pts, &lt;10t/ast=5pts"
                
                analytics_html += f"""
                <div style="background: var(--section-bg); padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid var(--border-color);">
                    <h3 style="margin-top: 0; color: var(--header-color); border-bottom: 2px solid var(--border-color); padding-bottom: 10px;">⚡ Efficiency Breakdown</h3>
                    <div style="background: #2a2a2a; padding: 12px; border-radius: 6px; margin-bottom: 15px; border-left: 4px solid #4CAF50;">
                        <p style="color: #cccccc; margin: 0; font-size: 13px;">
                            <strong>💡 Material-Aware Scoring:</strong><br>
                            Ring Quality is scored based on your <strong>primary material</strong> ({primary_material or 'Unknown'}). Different materials have different "Excellent" thresholds - Bromellite at 500 t/hr is just as impressive as Platinum at 800 t/hr!<br><br>
                            <strong>🎯 Ring Quality Ratings:</strong><br>
                            • <strong>Excellent:</strong> Outstanding for this material - bookmark it!<br>
                            • <strong>Good:</strong> Solid performance for this material<br>
                            • <strong>Fair:</strong> Acceptable efficiency<br>
                            • <strong>Poor:</strong> Below average - try a different spot<br><br>
                            <strong>📊 Scoring (100 pts):</strong> TPH (70%): {tph_thresholds} | Yield (30%): {tpa_thresholds}<br>
                            <em>Excellent=85+pts, Good=65-84pts, Fair=45-64pts, Poor=&lt;45pts</em>{scoring_note}
                        </p>
                    </div>
                    <div class="stats-grid">
                """
                
                # Add Ship card with adjustment indicator in Efficiency section
                ship_name_full = session_data.get('ship_name', '')
                if ship_name_full:
                    if ' - ' in ship_name_full:
                        ship_display, ship_type_display = ship_name_full.rsplit(' - ', 1)
                    else:
                        ship_display = ship_name_full
                        ship_type_display = ''
                    
                    # Build adjustment badge
                    if is_core_session:
                        adjustment_badge = '<span style="background: #9C27B0; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 5px;">Core Mining</span>'
                        ship_help = "⚖️ Core mining thresholds applied"
                    elif is_type_11_ship:
                        adjustment_badge = '<span style="background: #FF9800; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; margin-left: 5px;">+50% TPH</span>'
                        ship_help = "⚖️ Type-11 threshold adjustment"
                    else:
                        adjustment_badge = ""
                        ship_help = "Standard scoring thresholds"
                    
                    ship_tooltip = f"Mining ship: {ship_name_full}."
                    if is_type_11_ship and not is_core_session:
                        ship_tooltip += " Type-11 has +50% TPH thresholds (1200/900/600)."
                    elif is_core_session:
                        ship_tooltip += " Core mining detected - using core thresholds (120/90/60)."
                    
                    analytics_html += f"""
                    <div class="stat-card" title="{ship_tooltip}">
                        <div class="stat-value" style="font-size: 1.1em;">{ship_display if ship_display else ship_type_display}{adjustment_badge}</div>
                        <div class="stat-label">🚀 Mining Ship</div>
                        <div class="stat-help">{ship_type_display + ' • ' if ship_display and ship_type_display else ''}{ship_help}</div>
                    </div>
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
                
                # Total Average Yield - shows overall prospecting efficiency
                total_avg_yield = session_data.get('total_average_yield', 0.0)
                if not total_avg_yield and session_data.get('individual_yields'):
                    total_avg_yield = sum(session_data['individual_yields'].values()) / len(session_data['individual_yields'])
                
                if total_avg_yield and total_avg_yield > 0:
                    analytics_html += f"""
                    <div class="stat-card" title="Your overall prospecting efficiency across all asteroids scanned. This is the average yield percentage of valuable minerals found in every asteroid you prospected. Higher values mean you're consistently finding rich asteroids.">
                        <div class="stat-value">{self._safe_float(total_avg_yield):.1f}%</div>
                        <div class="stat-label">Total Average Yield</div>
                        <div class="stat-help">🎯 Overall prospecting efficiency</div>
                    </div>
                    """
                
                # Hit Rate - asteroid selection accuracy
                # Ensure hit_rate is converted to numeric before comparisons
                hit_rate = session_data.get('hit_rate_percent', 0)
                try:
                    if isinstance(hit_rate, str):
                        hit_rate = float(hit_rate.replace('%', '').strip()) if hit_rate not in ('', '—') else 0.0
                except Exception:
                    try:
                        hit_rate = float(hit_rate)
                    except Exception:
                        hit_rate = 0.0
                if hit_rate and float(hit_rate) > 0:
                    analytics_html += f"""
                    <div class="stat-card" title="Percentage of asteroids that contained your target materials above announcement thresholds. Shows how accurate you are at selecting profitable asteroids. Higher rates mean better targeting skills and less wasted prospector limpets.">
                        <div class="stat-value">{self._safe_float(hit_rate):.1f}%</div>
                        <div class="stat-label">Hit Rate</div>
                        <div class="stat-help">🎯 Asteroid selection accuracy</div>
                    </div>
                    """
                
                # Tons/Asteroid - key metric for comparing mining locations
                tons_per_asteroid_display, _ = self._compute_tons_per_asteroid(session_data)
                if tons_per_asteroid_display is not None and tons_per_asteroid_display > 0:
                    analytics_html += f"""
                    <div class="stat-card" title="Average tons of valuable materials per asteroid that contained tracked materials. This is the key metric for comparing different mining locations - higher values mean richer asteroids and better mining spots.">
                        <div class="stat-value">{self._safe_float(tons_per_asteroid_display):.1f}t</div>
                        <div class="stat-label">Tons/Asteroid</div>
                        <div class="stat-help">💎 Average yield per asteroid hit</div>
                    </div>
                    """
                
                hits = None
                tons_per_asteroid = 0.0  # Initialize to avoid UnboundLocalError in Ring Quality section
                if asteroids_prospected and asteroids_prospected > 0:
                    # Compute average tons per asteroid using the most accurate denominator available.
                    # Prefer explicit 'total_finds' (actual asteroids that contained materials/hits).
                    # If 'total_finds' not available but hit_rate is present, derive hits = asteroids_prospected * hit_rate/100.
                    # Fallback to legacy behavior: divide by asteroids_prospected.
                    hits = None
                    if 'total_finds' in session_data and isinstance(session_data.get('total_finds'), (int, float)) and session_data.get('total_finds') > 0:
                        hits = int(session_data.get('total_finds'))
                    elif hit_rate is not None and isinstance(hit_rate, (int, float)) and hit_rate > 0:
                        try:
                            hits = int(round(float(asteroids_prospected) * (float(hit_rate) / 100.0)))
                        except Exception:
                            hits = None
                    else:
                        try:
                            hits = int(asteroids_prospected)
                        except Exception:
                            hits = None

                    if hits and hits > 0:
                        tons_per_asteroid = total_tons / hits
                        label = "Tons/Asteroid (per hit)"
                        help_text = "🎯 Average tons of valuable materials per asteroid that contained tracked materials (uses total hits when available)."
                    else:
                        try:
                            tons_per_asteroid = total_tons / float(asteroids_prospected)
                        except Exception:
                            tons_per_asteroid = 0.0
                        label = "Tons/Asteroid"
                        help_text = "🎯 Average yield per asteroid prospected (fallback - hits unavailable)"

                    analytics_html += f"""
                    <div class="stat-card" title="{help_text}">
                        <div class="stat-value">{self._safe_float(tons_per_asteroid):.1f}t</div>
                        <div class="stat-label">{label}</div>
                        <div class="stat-help">{help_text}</div>
                    </div>
                    """

                # Also show Total Hits in Advanced Analytics if available
                if hits and hits > 0:
                    analytics_html += f"""
                    <div class="stat-card" title="Number of asteroids containing tracked materials (hits)">
                        <div class="stat-value">{hits}</div>
                        <div class="stat-label">Total Hits</div>
                        <div class="stat-help">🔎 Asteroids that contained tracked materials during this session</div>
                    </div>
                    """
                
                # Ring Quality Assessment - Material-aware scoring system
                # Different materials have different natural yield rates, so we score based on primary material
                ring_quality = "Poor"
                quality_explanation = ""
                quality_score = 0
                
                # Check if using Type-11 Prospector - apply ×1.25 TPH threshold multiplier
                ship_name_str = session_data.get('ship_name', '').lower()
                is_type_11 = 'type-11 prospector' in ship_name_str
                type_11_multiplier = 1.25 if is_type_11 else 1.0
                
                # Detect primary material and get appropriate thresholds
                primary_material, base_thresholds, is_core_material = self._get_primary_material_and_thresholds(session_data)
                
                # Check if this is a core mining session (from core asteroid count)
                core_asteroids = session_data.get('core_asteroids', 0)
                asteroids_prospected_for_core = session_data.get('asteroids_prospected', 0)
                is_core_mining = is_core_material
                
                if not is_core_material and core_asteroids > 0 and asteroids_prospected_for_core > 0:
                    core_ratio = core_asteroids / asteroids_prospected_for_core
                    is_core_mining = core_ratio > 0.3
                
                # Apply Type-11 multiplier to thresholds (not for core mining)
                if is_type_11 and not is_core_mining:
                    tph_excellent = base_thresholds['excellent'] * type_11_multiplier
                    tph_good = base_thresholds['good'] * type_11_multiplier
                    tph_fair = base_thresholds['fair'] * type_11_multiplier
                    mining_type_note = f" ({primary_material or 'Unknown'}, Type-11)"
                elif is_core_mining:
                    tph_excellent = 120
                    tph_good = 90
                    tph_fair = 60
                    mining_type_note = f" ({primary_material or 'Core'}, Core Mining)"
                else:
                    tph_excellent = base_thresholds['excellent']
                    tph_good = base_thresholds['good']
                    tph_fair = base_thresholds['fair']
                    mining_type_note = f" ({primary_material})" if primary_material else ""
                
                # Factor 1: TPH (70% weight) - Primary speed indicator (material-adjusted)
                if tph >= tph_excellent:
                    quality_score += 70
                elif tph >= tph_good:
                    quality_score += 50
                elif tph >= tph_fair:
                    quality_score += 30
                else:
                    quality_score += 10
                
                # Factor 2: Tons/Asteroid (30% weight) - Yield quality indicator
                ring_tons_per_asteroid, _ = self._compute_tons_per_asteroid(session_data)
                if ring_tons_per_asteroid is None:
                    ring_tons_per_asteroid = tons_per_asteroid  # Fallback to local calculation
                
                # T/Asteroid thresholds - adjusted for icy ring materials (lower natural yield)
                # Icy ring materials like Bromellite have ~50% lower T/Asteroid than metallic
                icy_materials = ['Bromellite', 'Tritium', 'Low Temperature Diamonds']
                is_icy_material = primary_material in icy_materials
                
                if is_type_11 and not is_core_mining:
                    if is_icy_material:
                        # Icy ring T/Asteroid thresholds (lower due to material properties)
                        tpa_excellent = 18
                        tpa_good = 14
                        tpa_fair = 10
                    else:
                        # Metallic ring T/Asteroid thresholds
                        tpa_excellent = 25
                        tpa_good = 19
                        tpa_fair = 12
                else:
                    if is_icy_material:
                        tpa_excellent = 15
                        tpa_good = 11
                        tpa_fair = 8
                    else:
                        tpa_excellent = 20
                        tpa_good = 15
                        tpa_fair = 10
                    tpa_excellent = 20
                    tpa_good = 15
                    tpa_fair = 10
                
                if ring_tons_per_asteroid >= tpa_excellent:
                    quality_score += 30
                elif ring_tons_per_asteroid >= tpa_good:
                    quality_score += 20
                elif ring_tons_per_asteroid >= tpa_fair:
                    quality_score += 10
                else:
                    quality_score += 5
                
                # Determine overall ring quality
                if quality_score >= 85:
                    ring_quality = "Excellent"
                    quality_explanation = f"Outstanding mining location - {tph:.1f} t/h, {ring_tons_per_asteroid:.1f} t/asteroid{mining_type_note}"
                elif quality_score >= 65:
                    ring_quality = "Good"
                    quality_explanation = f"Solid mining location - {tph:.1f} t/h, {ring_tons_per_asteroid:.1f} t/asteroid{mining_type_note}"
                elif quality_score >= 45:
                    ring_quality = "Fair" 
                    quality_explanation = f"Acceptable mining spot - {tph:.1f} t/h, {ring_tons_per_asteroid:.1f} t/asteroid{mining_type_note}"
                else:
                    quality_explanation = f"Suboptimal mining location - {tph:.1f} t/h, {ring_tons_per_asteroid:.1f} t/asteroid{mining_type_note}"
                
                # Build tooltip with material-specific thresholds
                tooltip_base = f"Ring quality scored based on your primary material ({primary_material or 'Unknown'}). Different materials have different 'Excellent' thresholds."
                if is_core_mining:
                    tooltip_extra = f" Core mining detected: TPH thresholds 120/90/60 t/hr."
                elif is_type_11:
                    tooltip_extra = f" Type-11 ×1.25: TPH thresholds {tph_excellent:.0f}/{tph_good:.0f}/{tph_fair:.0f} t/hr for {primary_material or 'this material'}."
                else:
                    tooltip_extra = f" TPH thresholds: {tph_excellent:.0f}/{tph_good:.0f}/{tph_fair:.0f} t/hr for {primary_material or 'this material'}."
                
                analytics_html += f"""
                <div class="stat-card" title="{tooltip_base}{tooltip_extra}">
                    <div class="stat-value">{ring_quality}</div>
                    <div class="stat-label">Ring Quality</div>
                    <div class="stat-help">💎 {quality_explanation}</div>
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
            
            # Parse average/overall quality (TXT uses "Overall Quality")
            avg_quality_match = re.search(r'(?:Average|Overall) Quality:\s*([\d.]+)%', content)
            if avg_quality_match:
                analytics_data['avg_quality'] = float(avg_quality_match.group(1))
            
            # Parse asteroids prospected
            asteroids_match = re.search(r'Asteroids Prospected:\s*(\d+)', content)
            if asteroids_match:
                analytics_data['asteroids_prospected'] = int(asteroids_match.group(1))
            
            # Parse core asteroids found (for core mining detection)
            core_asteroids_match = re.search(r'Core Asteroids Found:\s*(\d+)', content)
            if core_asteroids_match:
                analytics_data['core_asteroids'] = int(core_asteroids_match.group(1))
            
            # Parse best material/performer (TXT uses "Best Performer")
            best_material_match = re.search(r'Best (?:Material|Performer):\s*([^(\n]+)', content)
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
        materials_mined_raw = session_data.get('materials_mined', {})
        # Normalize values to float tons in case they are dicts {'tons': x, 'tph': y}
        materials_mined = {k: (self._normalize_material_tons(v) or 0.0) for k, v in (materials_mined_raw or {}).items()}
        if not materials_mined:
            return "<p>No materials mined this session</p>"
        
        # Filter out summary entries like "Total Cargo Collected"
        filtered_materials = {k: v for k, v in materials_mined.items() 
                             if k.lower() not in ['total cargo collected', 'total', 'cargo collected', 'total refined']}
        
        if not filtered_materials:
            return "<p>No materials mined this session</p>"
            
        # Calculate session duration for TPH
        session_duration_hours = session_data.get('session_duration', 0) / 3600.0
        
        table_html = """
        <table class="data-table">
            <thead>
                <tr>
                    <th>Material</th>
                    <th>Quantity (tons)</th>
                    <th>T/hr</th>
                    <th>Percentage</th>
                </tr>
            </thead>
            <tbody>
        """
        
        total_tons = sum(filtered_materials.values())
        for material, quantity in sorted(filtered_materials.items(), key=lambda x: x[1], reverse=True):
            percentage = (quantity / total_tons * 100) if total_tons > 0 else 0
            mat_tph = (quantity / session_duration_hours) if session_duration_hours > 0 else 0
            table_html += f"""
                <tr>
                    <td>{self._expand_material_name(material)}</td>
                    <td>{quantity:.1f}</td>
                    <td>{mat_tph:.1f}</td>
                    <td>{percentage:.1f}%</td>
                </tr>
            """
            
        table_html += """
            </tbody>
        </table>
        """
        
        return table_html
    
    def _generate_engineering_materials_section(self, session_data):
        """Generate engineering materials section (Option 1 + 2: Summary box + Detailed table)"""
        engineering_materials = session_data.get('engineering_materials', {})
        
        if not engineering_materials:
            return ""  # Return empty if no materials
        
        # Material grades mapping
        MATERIAL_GRADES = {
            "Antimony": 2, "Arsenic": 2, "Boron": 3, "Cadmium": 3,
            "Carbon": 1, "Chromium": 2, "Germanium": 2, "Iron": 1,
            "Lead": 1, "Manganese": 2, "Nickel": 1, "Niobium": 3,
            "Phosphorus": 1, "Polonium": 4, "Rhenium": 1, "Selenium": 4,
            "Sulphur": 1, "Tin": 3, "Tungsten": 3, "Vanadium": 2,
            "Zinc": 2, "Zirconium": 2
        }
        
        grade_names = {
            1: "Very Common",
            2: "Common",
            3: "Standard",
            4: "Rare"
        }
        
        # Group materials by grade
        materials_by_grade = {}
        total_pieces = 0
        for material_name, quantity in engineering_materials.items():
            grade = MATERIAL_GRADES.get(material_name, 0)
            if grade not in materials_by_grade:
                materials_by_grade[grade] = []
            materials_by_grade[grade].append((material_name, quantity))
            total_pieces += quantity
        
        # Generate summary box (compact overview)
        summary_materials = sorted(engineering_materials.items(), key=lambda x: x[1], reverse=True)[:3]
        summary_text = ", ".join([f"{mat} ({qty}) G{MATERIAL_GRADES.get(mat, 0)}" for mat, qty in summary_materials])
        if len(engineering_materials) > 3:
            summary_text += f" +{len(engineering_materials)-3} more"
        
        html = f"""
        <div class="materials-summary-box">
            <h3>🔩 Engineering Materials Collected</h3>
            <p class="summary-text">{summary_text}</p>
            <p class="summary-total"><strong>Total: {total_pieces} pieces</strong></p>
        </div>
        
        <h3>Engineering Materials by Grade</h3>
        <table class="data-table">
            <thead>
                <tr>
                    <th>Grade</th>
                    <th>Material</th>
                    <th>Quantity</th>
                </tr>
            </thead>
            <tbody>
        """
        
        # Generate table rows grouped by grade
        for grade in sorted(materials_by_grade.keys()):
            grade_label = f"Grade {grade} ({grade_names.get(grade, 'Unknown')})"
            materials = sorted(materials_by_grade[grade])
            
            for idx, (material_name, quantity) in enumerate(materials):
                if idx == 0:
                    # First material in grade - show grade label
                    html += f"""
                <tr>
                    <td rowspan="{len(materials)}" class="grade-cell grade-{grade}">{grade_label}</td>
                    <td>{material_name}</td>
                    <td>{quantity}</td>
                </tr>
                    """
                else:
                    # Subsequent materials - no grade label
                    html += f"""
                <tr>
                    <td>{material_name}</td>
                    <td>{quantity}</td>
                </tr>
                    """
        
        html += """
            </tbody>
        </table>
        """
        
        return html
        
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
            materials_list = ', '.join([self._expand_material_name(m) for m in session_data.get('materials_mined', {}).keys()]) if materials_count > 0 else 'None recorded'
            
            base_props = [
                ("Report Date", session_data.get('date', 'Unknown')),
                ("Session Duration", session_data.get('duration', 'Unknown')),
            ]
            
            # Add ship name if available
            ship_name = session_data.get('ship_name', '').strip()
            if ship_name:
                base_props.append(("Ship", ship_name))
            
            base_props.extend([
                ("Mining Location", f"{session_data.get('system', 'Unknown')} - {session_data.get('body', 'Unknown')}"),
                ("Minerals Found", f"{materials_count} types: {materials_list}"),
            ])
            
            properties.extend(base_props)
            # Add Total Hits and Tons/Asteroid
            derived_hits = self._derive_total_finds(session_data)
            derived_tpa, _ = self._compute_tons_per_asteroid(session_data)
            # Normalize display values for raw data table
            if derived_hits is not None:
                total_hits_raw_display = str(derived_hits)
            else:
                raw_total_finds = session_data.get('total_finds')
                if raw_total_finds not in (None, '', '—'):
                    try:
                        total_hits_raw_display = str(int(float(str(raw_total_finds).strip())))
                    except Exception:
                        total_hits_raw_display = str(raw_total_finds)
                else:
                    total_hits_raw_display = '—'
            properties.append(("Total Hits", total_hits_raw_display))
            properties.append(("Tons/Asteroid", f"{self._safe_float(derived_tpa):.1f}t" if derived_tpa is not None else '—'))
            
            # Add prospecting analytics from TXT file
            session_text_data = self._parse_session_analytics_from_text(session_data)
            
            # Prospectors Used
            prospectors_used = session_data.get('prospectors', session_data.get('prospects', session_data.get('prospectors_used')))
            if prospectors_used is not None and str(prospectors_used) not in ('', '0', '—'):
                properties.append(("Prospectors Used", str(prospectors_used)))
            
            # Asteroids Prospected
            asteroids_prospected = session_data.get('asteroids_prospected')
            if asteroids_prospected is None and session_text_data:
                asteroids_prospected = session_text_data.get('asteroids_prospected')
            if asteroids_prospected is not None:
                properties.append(("Asteroids Prospected", str(asteroids_prospected)))
            
            # Hit Rate
            hit_rate = session_data.get('hit_rate_percent')
            if hit_rate is None and session_text_data:
                hit_rate = session_text_data.get('hit_rate')
            if hit_rate is not None:
                properties.append(("Hit Rate", f"{self._safe_float(hit_rate):.1f}%"))
            
            # Average Quality
            avg_quality = session_data.get('avg_quality_percent')
            if avg_quality is None and session_text_data:
                avg_quality = session_text_data.get('avg_quality')
            if avg_quality is not None:
                properties.append(("Average Quality", f"{self._safe_float(avg_quality):.1f}%"))
            
            # Best Performer
            best_material = session_data.get('best_material')
            if best_material is None and session_text_data:
                best_material = session_text_data.get('best_material')
            if best_material:
                properties.append(("Best Performer", best_material))
            
            # Add engineering materials if any were collected
            engineering_materials = session_data.get('engineering_materials', {})
            if engineering_materials:
                # Format: "Iron (45), Nickel (23), Carbon (89) - Total: 157 pieces"
                eng_list = ', '.join([f"{mat} ({qty})" for mat, qty in sorted(engineering_materials.items())])
                total_pieces = sum(engineering_materials.values())
                properties.append(("Engineering Materials", f"{eng_list} - Total: {total_pieces} pieces"))
            
            properties.append(("Data Source", "Report entry from mining log"))
        else:
            # Original detailed session data - only show cargo if we have meaningful data
            cargo_available = (start_snapshot.get('total_cargo', 0) > 0 or 
                             end_snapshot.get('total_cargo', 0) > 0 or 
                             start_snapshot.get('max_cargo', 0) > 0)
            
            properties.extend([
                ("Session Start", session_start),
                ("Session End", session_end),
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
            
            # Add engineering materials if any were collected
            engineering_materials = session_data.get('engineering_materials', {})
            if engineering_materials:
                # Format: "Iron (45), Nickel (23), Carbon (89) - Total: 157 pieces"
                eng_list = ', '.join([f"{mat} ({qty})" for mat, qty in sorted(engineering_materials.items())])
                total_pieces = sum(engineering_materials.values())
                properties.append(("Engineering Materials", f"{eng_list} - Total: {total_pieces} pieces"))
            
            properties.append(("Data Source", "Detailed mining session data"))
        # Add raw fields for total hits and tons/asteroid for original session format as well
        derived_hits = self._derive_total_finds(session_data)
        derived_tpa, _ = self._compute_tons_per_asteroid(session_data)
        if not any(p[0] == 'Total Hits' for p in properties):
            if derived_hits is not None:
                total_hits_raw_display = str(derived_hits)
            else:
                raw_total_finds = session_data.get('total_finds')
                if raw_total_finds not in (None, '', '—'):
                    try:
                        total_hits_raw_display = str(int(float(str(raw_total_finds).strip())))
                    except Exception:
                        total_hits_raw_display = str(raw_total_finds)
                else:
                    total_hits_raw_display = '—'
            properties.append(("Total Hits", total_hits_raw_display))
        if not any(p[0] == 'Tons/Asteroid' for p in properties):
            properties.append(("Tons/Asteroid", f"{self._safe_float(derived_tpa):.1f}t" if derived_tpa is not None else '—'))

        material_tpa_entries = self._build_material_tpa_entries(session_data)
        if material_tpa_entries:
            rates = []
            for entry in material_tpa_entries:
                hits_text = f", Hits: {entry['hits']}" if entry['hits'] is not None else ''
                tpa_value = entry['tpa']
                tpa_text = f"{self._safe_float(tpa_value):.2f}t" if tpa_value is not None else '—'
                display = entry.get('display_name', entry['material'])
                rates.append(f"{display}: {self._safe_float(entry['tons']):.1f}t ({tpa_text}{hits_text})")
            properties.append(("Material Tons/Asteroid", "; ".join(rates)))
        
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
