#!/usr/bin/env python3
"""
Mining Card Generator
Creates visual PNG cards from mining session data
"""

import os
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


def generate_mining_card(session_data, output_path, cmdr_info=None):
    """
    Generate a mining card PNG from session data
    
    Args:
        session_data: Dict containing session information
        output_path: Full path where PNG will be saved
        cmdr_info: Optional dict with 'cmdr' and 'comment' keys
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Card dimensions and styling
        CARD_WIDTH = 800
        LINE_HEIGHT = 35
        PADDING = 40
        
        # Colors (Elite Dangerous orange theme)
        BG_COLOR = (20, 20, 25)  # Dark background
        BORDER_COLOR = (255, 140, 0)  # Elite orange
        TEXT_COLOR = (220, 220, 220)  # Light gray text
        HEADER_COLOR = (255, 180, 60)  # Bright orange for headers
        
        # Calculate card height based on content (add logo height + stats boxes + performance)
        materials_count = len(session_data.get('materials_mined', {}))
        mineral_performance_count = len(session_data.get('mineral_performance', {}))
        eng_materials_count = len(session_data.get('engineering_materials_list', []))
        
        base_height = 450  # Base height for headers, stats, and footer (minimal padding)
        logo_height = 120  # Reserve space for logo
        materials_height = materials_count * LINE_HEIGHT  # Height for materials list
        # Table height: header (30) + rows (30 each) + padding + title
        performance_height = ((mineral_performance_count + 1) * 30) + 60 if mineral_performance_count > 0 else 0  # Mineral performance table
        prospecting_height = 200  # Space for prospecting stats (increased for more data)
        engineering_height = ((eng_materials_count + 1) * LINE_HEIGHT) + 20 if eng_materials_count > 0 else (LINE_HEIGHT if session_data.get('engineering_materials_total', 0) > 0 else 0)
        
        # Add height for CMDR name at top
        cmdr_name_height = LINE_HEIGHT if cmdr_info and cmdr_info.get('cmdr') else 0
        
        # Add height for Session Notes section at bottom
        notes_height = (LINE_HEIGHT * 2) + 60 if cmdr_info and cmdr_info.get('comment') else 0
        
        card_height = base_height + logo_height + materials_height + performance_height + prospecting_height + engineering_height + cmdr_name_height + notes_height
        
        # Create image
        img = Image.new('RGB', (CARD_WIDTH, card_height), BG_COLOR)
        draw = ImageDraw.Draw(img)
        
        # Load fonts (fallback to default if not available)
        try:
            title_font = ImageFont.truetype("arial.ttf", 28)
            header_font = ImageFont.truetype("arial.ttf", 22)
            body_font = ImageFont.truetype("arial.ttf", 18)
            small_font = ImageFont.truetype("arial.ttf", 14)
        except:
            title_font = ImageFont.load_default()
            header_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Draw border
        border_thickness = 3
        draw.rectangle(
            [(0, 0), (CARD_WIDTH - 1, card_height - 1)],
            outline=BORDER_COLOR,
            width=border_thickness
        )
        
        # Draw inner decorative border
        inner_border = 8
        draw.rectangle(
            [(inner_border, inner_border), (CARD_WIDTH - inner_border - 1, card_height - inner_border - 1)],
            outline=BORDER_COLOR,
            width=1
        )
        
        y_position = PADDING
        
        # Add EliteMining logo at top
        try:
            # Get logo from app installation directory
            import sys
            if getattr(sys, 'frozen', False):
                # PyInstaller - executable is in Configurator folder, app is one level up
                configurator_dir = os.path.dirname(sys.executable)
                app_dir = os.path.join(os.path.dirname(configurator_dir), 'app')
            else:
                # Dev mode
                app_dir = os.path.dirname(os.path.abspath(__file__))
            
            logo_path = os.path.join(app_dir, 'Images', 'EliteMining_txt_logo_transp_resize.png')
            print(f"[CARD DEBUG] Looking for logo at: {logo_path}")
            print(f"[CARD DEBUG] Logo exists: {os.path.exists(logo_path)}")
            
            if os.path.exists(logo_path):
                logo = Image.open(logo_path)
                print(f"[CARD DEBUG] Logo loaded successfully, size: {logo.size}")
                # Resize logo to fit (max width 300px)
                logo_max_width = 300
                if logo.width > logo_max_width:
                    ratio = logo_max_width / logo.width
                    new_height = int(logo.height * ratio)
                    logo = logo.resize((logo_max_width, new_height), Image.LANCZOS)
                
                # Center logo
                logo_x = (CARD_WIDTH - logo.width) // 2
                img.paste(logo, (logo_x, y_position), logo if logo.mode == 'RGBA' else None)
                y_position += logo.height + 10
                
                # Add branding text below logo
                tagline = "Your Elite Dangerous Mining Companion"
                tagline_bbox = draw.textbbox((0, 0), tagline, font=small_font)
                tagline_width = tagline_bbox[2] - tagline_bbox[0]
                tagline_x = (CARD_WIDTH - tagline_width) // 2
                draw.text((tagline_x, y_position), tagline, fill=TEXT_COLOR, font=small_font)
                y_position += LINE_HEIGHT + 10
        except Exception as e:
            print(f"[CARD] Could not load logo: {e}")
            # Fallback to text title if logo fails
            title = "ELITE MINING SESSION REPORT"
            title_bbox = draw.textbbox((0, 0), title, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (CARD_WIDTH - title_width) // 2
            draw.text((title_x, y_position), title, fill=HEADER_COLOR, font=title_font)
            y_position += 50
        
        # Horizontal line under title (thicker)
        draw.line([(PADDING, y_position), (CARD_WIDTH - PADDING, y_position)], fill=BORDER_COLOR, width=3)
        y_position += 30
        
        # CMDR name at top (if provided)
        if cmdr_info and cmdr_info.get('cmdr'):
            cmdr_name = cmdr_info.get('cmdr')
            draw.text((PADDING, y_position), f"CMDR: {cmdr_name}", fill=HEADER_COLOR, font=body_font)
            y_position += LINE_HEIGHT
        
        # Session info
        system = session_data.get('system', 'Unknown System')
        body = session_data.get('body', 'Unknown Body')
        ship = session_data.get('ship', None)
        session_type = session_data.get('session_type', '')
        
        draw.text((PADDING, y_position), f"System: {system}", fill=TEXT_COLOR, font=body_font)
        y_position += LINE_HEIGHT
        
        draw.text((PADDING, y_position), f"Body: {body}", fill=TEXT_COLOR, font=body_font)
        y_position += LINE_HEIGHT
        
        if ship:
            draw.text((PADDING, y_position), f"Ship: {ship}", fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT
        
        if session_type:
            draw.text((PADDING, y_position), f"Session Type: {session_type}", fill=HEADER_COLOR, font=body_font)
            y_position += LINE_HEIGHT
        
        y_position += 20
        
        # STATS BOXES - 5 key metrics in a grid
        duration = session_data.get('duration', 'Unknown')
        total_tons = session_data.get('total_tons', 0)
        tph = session_data.get('tph', 0)
        prospectors = session_data.get('prospectors_used', 0)
        materials_mined = session_data.get('materials_mined', {})
        mineral_types = len(materials_mined)
        
        # Calculate efficiency
        efficiency = total_tons / prospectors if prospectors > 0 else 0
        
        # Draw stats boxes background
        box_height = 60
        box_spacing = 10
        boxes_per_row = 5
        box_width = (CARD_WIDTH - (2 * PADDING) - (box_spacing * (boxes_per_row - 1))) // boxes_per_row
        
        stats = [
            ("Duration", duration),
            ("Total Tons", f"{total_tons:.0f}t"),
            ("Tons/Hour", f"{tph:.1f}"),
            ("Prospectors", str(prospectors)),
            ("Commodities", str(mineral_types))
        ]
        
        box_y = y_position
        for i, (label, value) in enumerate(stats):
            box_x = PADDING + (i * (box_width + box_spacing))
            
            # Draw multiple shadow layers for depth effect
            draw.rectangle(
                [(box_x + 4, box_y + 4), (box_x + box_width + 4, box_y + box_height + 4)],
                fill=(0, 0, 0),
                outline=None
            )
            draw.rectangle(
                [(box_x + 2, box_y + 2), (box_x + box_width + 2, box_y + box_height + 2)],
                fill=(10, 10, 10),
                outline=None
            )
            
            # Draw box background (MUCH lighter for dramatic contrast)
            draw.rectangle(
                [(box_x, box_y), (box_x + box_width, box_y + box_height)],
                fill=(55, 55, 60),
                outline=BORDER_COLOR,
                width=3
            )
            
            # Draw value (BOLDER - draw 3 times for stronger bold effect)
            value_bbox = draw.textbbox((0, 0), value, font=header_font)
            value_width = value_bbox[2] - value_bbox[0]
            value_x = box_x + (box_width - value_width) // 2
            value_y = box_y + 8
            
            # Strong bold effect - draw text 3 times with offsets
            draw.text((value_x, value_y), value, fill=HEADER_COLOR, font=header_font)
            draw.text((value_x + 1, value_y), value, fill=HEADER_COLOR, font=header_font)
            draw.text((value_x, value_y + 1), value, fill=HEADER_COLOR, font=header_font)
            
            # Draw label (small)
            label_bbox = draw.textbbox((0, 0), label, font=small_font)
            label_width = label_bbox[2] - label_bbox[0]
            label_x = box_x + (box_width - label_width) // 2
            draw.text((label_x, box_y + 38), label, fill=TEXT_COLOR, font=small_font)
        
        y_position = box_y + box_height + 30
        
        # Materials header with efficiency info (thicker line)
        draw.line([(PADDING, y_position), (CARD_WIDTH - PADDING, y_position)], fill=BORDER_COLOR, width=3)
        y_position += 15
        
        materials_title = "COMMODITIES COLLECTED"
        draw.text((PADDING, y_position), materials_title, fill=HEADER_COLOR, font=header_font)
        
        # Add efficiency on the right side
        if efficiency > 0:
            efficiency_text = f"Efficiency: {efficiency:.2f} t/limpet"
            eff_bbox = draw.textbbox((0, 0), efficiency_text, font=small_font)
            eff_width = eff_bbox[2] - eff_bbox[0]
            draw.text((CARD_WIDTH - PADDING - eff_width, y_position + 5), efficiency_text, fill=TEXT_COLOR, font=small_font)
        
        y_position += 40
        
        draw.line([(PADDING, y_position), (CARD_WIDTH - PADDING, y_position)], fill=BORDER_COLOR, width=2)
        y_position += 20
        
        # Materials list
        materials_mined = session_data.get('materials_mined', {})
        if materials_mined:
            # Sort by quantity (highest first) - handle both dict and numeric values
            # Convert all materials to normalized format first
            normalized_materials = []
            for mat_name, mat_data in materials_mined.items():
                try:
                    if isinstance(mat_data, dict):
                        # Handle nested dict structure: {'tons': {'tons': X, 'tph': Y}, 'tph': Z}
                        tons_value = mat_data.get('tons', 0)
                        if isinstance(tons_value, dict):
                            # Nested dict
                            tons = float(tons_value.get('tons', 0))
                            tph = float(tons_value.get('tph', 0))
                        else:
                            # Simple dict
                            tons = float(tons_value)
                            tph = float(mat_data.get('tph', 0))
                    else:
                        tons = float(mat_data) if mat_data else 0.0
                        tph = 0.0
                    normalized_materials.append((mat_name, tons, tph))
                except Exception as e:
                    print(f"[CARD DEBUG] Error processing material {mat_name}: {mat_data}, error: {e}")
                    # Skip problematic materials
                    continue
            
            # Sort by tons (now all numeric)
            try:
                sorted_materials = sorted(normalized_materials, key=lambda x: float(x[1]), reverse=True)
            except Exception as e:
                print(f"[CARD DEBUG] Error sorting materials: {normalized_materials}")
                print(f"[CARD DEBUG] Error: {e}")
                raise
            
            # Calculate best performer
            best_performer = sorted_materials[0] if sorted_materials else None
            
            for material_name, tons, mat_tph in sorted_materials:
                # Calculate percentage of total
                percentage = (tons / total_tons * 100) if total_tons > 0 else 0
                
                # Material name
                draw.text((PADDING + 10, y_position), material_name, fill=TEXT_COLOR, font=body_font)
                
                # Tons and t/hr
                stats_text = f"{tons:.0f}t  ({mat_tph:.1f} t/hr)"
                stats_bbox = draw.textbbox((0, 0), stats_text, font=body_font)
                stats_width = stats_bbox[2] - stats_bbox[0]
                draw.text((CARD_WIDTH - PADDING - 120 - stats_width, y_position), stats_text, fill=TEXT_COLOR, font=body_font)
                
                # Percentage
                pct_text = f"{percentage:.0f}%"
                pct_bbox = draw.textbbox((0, 0), pct_text, font=body_font)
                pct_width = pct_bbox[2] - pct_bbox[0]
                draw.text((CARD_WIDTH - PADDING - pct_width, y_position), pct_text, fill=HEADER_COLOR, font=body_font)
                
                # Draw progress bar
                bar_width = 80
                bar_height = 8
                bar_x = CARD_WIDTH - PADDING - 110
                bar_y = y_position + 18
                
                # Background bar
                draw.rectangle(
                    [(bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height)],
                    fill=(50, 50, 55),
                    outline=None
                )
                
                # Filled bar
                filled_width = int(bar_width * (percentage / 100))
                if filled_width > 0:
                    draw.rectangle(
                        [(bar_x, bar_y), (bar_x + filled_width, bar_y + bar_height)],
                        fill=BORDER_COLOR,
                        outline=None
                    )
                
                y_position += LINE_HEIGHT
        else:
            draw.text((PADDING, y_position), "  No refined materials.", fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT
        
        y_position += 25
        
        # Performance Summary Box - TWO COLUMN LAYOUT
        if best_performer and sorted_materials:
            draw.line([(PADDING, y_position), (CARD_WIDTH - PADDING, y_position)], fill=BORDER_COLOR, width=3)
            y_position += 15
            
            perf_title = "PERFORMANCE SUMMARY"
            draw.text((PADDING, y_position), perf_title, fill=HEADER_COLOR, font=header_font)
            y_position += 35
            
            # Calculate column positions
            col1_x = PADDING + 10
            col2_x = CARD_WIDTH // 2 + 20
            
            # Get all data
            best_name, best_tons, best_tph = best_performer
            avg_yield = session_data.get('avg_yield', 0)
            asteroids_prospected = session_data.get('asteroids_prospected', 0)
            hit_rate = session_data.get('hit_rate', 0)
            prospecting_speed = session_data.get('prospecting_speed', 0)
            materials_tracked = session_data.get('materials_tracked', 0)
            total_finds = session_data.get('total_finds', 0)
            
            # Row 1: Best Performer | Total Average Yield
            draw.text((col1_x, y_position), f"Best Performer: {best_name} ({best_tph:.1f} t/hr)", fill=TEXT_COLOR, font=body_font)
            if avg_yield > 0:
                draw.text((col2_x, y_position), f"Total Avg Yield: {avg_yield:.1f}%", fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT
            
            # Row 2: Efficiency | Asteroids
            if efficiency > 0:
                draw.text((col1_x, y_position), f"Efficiency: {efficiency:.2f} t/limpet", fill=TEXT_COLOR, font=body_font)
            if asteroids_prospected > 0:
                draw.text((col2_x, y_position), f"Asteroids: {asteroids_prospected}", fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT
            
            # Row 3: Minerals Tracked | Total Hits
            if materials_tracked > 0:
                draw.text((col1_x, y_position), f"Minerals Tracked: {materials_tracked}", fill=TEXT_COLOR, font=body_font)
            if total_finds and int(total_finds) > 0:
                draw.text((col2_x, y_position), f"Total Hits: {int(total_finds)}", fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT
            # Optional row: Tons per Asteroid (display under Total Hits if available)
            tons_per_ast = session_data.get('tons_per_asteroid')
            if tons_per_ast is not None:
                draw.text((col2_x, y_position), f"Tons/Asteroid: {tons_per_ast:.1f}t", fill=TEXT_COLOR, font=body_font)
                y_position += LINE_HEIGHT
            
            # Row 4: Hit Rate | Prospecting Speed
            if hit_rate > 0:
                draw.text((col1_x, y_position), f"Hit Rate: {hit_rate:.1f}%", fill=TEXT_COLOR, font=body_font)
            if prospecting_speed > 0:
                draw.text((col2_x, y_position), f"Speed: {prospecting_speed:.1f} ast/min", fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT
            
            # Individual mineral performance - TABLE FORMAT
            mineral_performance = session_data.get('mineral_performance', {})
            if mineral_performance:
                y_position += 10
                draw.text((PADDING + 10, y_position), "MINERAL PERFORMANCE", fill=HEADER_COLOR, font=header_font)
                y_position += LINE_HEIGHT + 5
                
                # Table dimensions
                table_x = PADDING + 20
                table_width = CARD_WIDTH - (2 * PADDING) - 40
                col_widths = [
                    int(table_width * 0.40),  # Mineral name (40%)
                    int(table_width * 0.20),  # Avg (20%)
                    int(table_width * 0.20),  # Best (20%)
                    int(table_width * 0.20)   # Hits (20%)
                ]
                row_height = 30
                
                # Draw table border
                table_height = (len(mineral_performance) + 1) * row_height + 4
                draw.rectangle(
                    [(table_x, y_position), (table_x + table_width, y_position + table_height)],
                    outline=BORDER_COLOR,
                    width=2
                )
                
                # Draw header row background
                draw.rectangle(
                    [(table_x + 2, y_position + 2), (table_x + table_width - 2, y_position + row_height)],
                    fill=(40, 40, 45),
                    outline=None
                )
                
                # Header text
                headers = ["Mineral", "Avg %", "Best %", "Hits"]
                x_pos = table_x + 10
                for i, header in enumerate(headers):
                    draw.text((x_pos, y_position + 8), header, fill=HEADER_COLOR, font=body_font)
                    x_pos += col_widths[i]
                
                # Horizontal line after header
                y_position += row_height
                draw.line(
                    [(table_x + 2, y_position), (table_x + table_width - 2, y_position)],
                    fill=BORDER_COLOR,
                    width=1
                )
                
                # Data rows
                for mineral_name, perf in mineral_performance.items():
                    y_position += row_height
                    avg = perf.get('avg', 0)
                    best = perf.get('best', 0)
                    hits = perf.get('finds', 0)
                    
                    # Draw row data
                    x_pos = table_x + 10
                    draw.text((x_pos, y_position - 22), mineral_name, fill=TEXT_COLOR, font=body_font)
                    
                    x_pos += col_widths[0]
                    draw.text((x_pos, y_position - 22), f"{avg:.1f}%", fill=TEXT_COLOR, font=body_font)
                    
                    x_pos += col_widths[1]
                    draw.text((x_pos, y_position - 22), f"{best:.1f}%", fill=TEXT_COLOR, font=body_font)
                    
                    x_pos += col_widths[2]
                    draw.text((x_pos, y_position - 22), f"{hits}", fill=TEXT_COLOR, font=body_font)
                
                y_position += 10
            
            # Engineering materials
            eng_materials_total = session_data.get('engineering_materials_total', 0)
            eng_materials_list = session_data.get('engineering_materials_list', [])
            
            if eng_materials_total > 0:
                y_position += 10
                
                if eng_materials_list:
                    # Show detailed breakdown
                    draw.text((PADDING + 10, y_position), f"ENGINEERING MATERIALS ({eng_materials_total} total)", fill=HEADER_COLOR, font=header_font)
                    y_position += LINE_HEIGHT
                    
                    for eng_mat in eng_materials_list:
                        material = eng_mat.get('material', '')
                        grade = eng_mat.get('grade', '')
                        quantity = eng_mat.get('quantity', 0)
                        
                        eng_text = f"{material} ({grade}): {quantity}x"
                        draw.text((PADDING + 20, y_position), eng_text, fill=TEXT_COLOR, font=body_font)
                        y_position += LINE_HEIGHT
                else:
                    # Fallback to simple total
                    draw.text((PADDING + 10, y_position), f"Engineering Materials: {eng_materials_total} pieces collected", fill=TEXT_COLOR, font=body_font)
                    y_position += LINE_HEIGHT
            
            y_position += 15
        
        # Session Notes section (if comment provided)
        if cmdr_info and cmdr_info.get('comment'):
            comment = cmdr_info.get('comment')
            
            y_position += 10
            draw.line([(PADDING, y_position), (CARD_WIDTH - PADDING, y_position)], fill=BORDER_COLOR, width=3)
            y_position += 15
            
            draw.text((PADDING, y_position), "SESSION NOTES", fill=HEADER_COLOR, font=header_font)
            y_position += LINE_HEIGHT
            
            draw.text((PADDING + 10, y_position), f'"{comment}"', fill=TEXT_COLOR, font=body_font)
            y_position += LINE_HEIGHT + 10
        
        # Footer (thicker line)
        y_position += 10
        draw.line([(PADDING, y_position), (CARD_WIDTH - PADDING, y_position)], fill=BORDER_COLOR, width=3)
        y_position += 15
        
        # Timestamp
        timestamp = session_data.get('timestamp', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        draw.text((PADDING, y_position), f"Generated: {timestamp}", fill=TEXT_COLOR, font=small_font)
        
        # Save image
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path, 'PNG')
        print(f"[MINING CARD] Generated: {output_path}")
        return True
        
    except Exception as e:
        print(f"[MINING CARD] Error generating card: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_card_from_session(cargo_session_data, session_info, output_path, cmdr_info=None):
    """
    Create mining card from session end data
    
    Args:
        cargo_session_data: Cargo tracking session data from end_session_tracking()
        session_info: Additional session info (system, body, ship, duration text)
        output_path: Full path where PNG will be saved
        cmdr_info: Optional dict with 'cmdr' and 'comment' keys
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Build card data structure
        card_data = {
            'system': session_info.get('system', 'Unknown System'),
            'body': session_info.get('body', 'Unknown Body'),
            'ship': session_info.get('ship', None),
            'duration': session_info.get('duration_text', 'Unknown'),
            'total_tons': cargo_session_data.get('total_tons_mined', 0),
            'session_type': cargo_session_data.get('session_type', '').replace('(', '').replace(')', ''),
            'prospectors_used': cargo_session_data.get('prospectors_used', 0),
            'avg_yield': cargo_session_data.get('avg_yield', 0),
            'asteroids_prospected': cargo_session_data.get('asteroids_prospected', 0),
            'hit_rate': cargo_session_data.get('hit_rate', 0),
            'prospecting_speed': cargo_session_data.get('prospecting_speed', 0),
            'mineral_performance': cargo_session_data.get('mineral_performance', {}),
            'engineering_materials_total': cargo_session_data.get('engineering_materials_total', 0),
            'engineering_materials_list': cargo_session_data.get('engineering_materials_list', []),
            'materials_tracked': cargo_session_data.get('materials_tracked', 0),
            'total_finds': cargo_session_data.get('total_finds', 0) if cargo_session_data.get('total_finds') not in (None, '', '—') else 0,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'materials_mined': {}
        }
        
        # Calculate TPH
        session_duration_hours = cargo_session_data.get('session_duration', 0) / 3600.0
        card_data['tph'] = card_data['total_tons'] / session_duration_hours if session_duration_hours > 0 else 0
        # Calculate Tons/Asteroid (prefer total_finds if >0, derive otherwise)
        try:
            total_finds_val = cargo_session_data.get('total_finds')
            if total_finds_val in (None, '', '—'):
                # Derive from hit_rate_percent and asteroids_prospected
                ap = cargo_session_data.get('asteroids_prospected') or cargo_session_data.get('asteroids') or cargo_session_data.get('prospects')
                hr = cargo_session_data.get('hit_rate') or cargo_session_data.get('hit_rate_percent')
                if ap and hr:
                    try:
                        ap_i = int(str(ap).strip())
                        hr_v = float(str(hr).replace('%', '').strip())
                        derived_hits = int(round(ap_i * (hr_v / 100.0)))
                        total_finds_val = derived_hits if derived_hits > 0 else 0
                    except Exception:
                        total_finds_val = 0
                else:
                    total_finds_val = 0
            else:
                try:
                    total_finds_val = int(float(str(total_finds_val).strip()))
                except Exception:
                    total_finds_val = 0
            if total_finds_val > 0:
                card_data['tons_per_asteroid'] = card_data['total_tons'] / total_finds_val
            else:
                card_data['tons_per_asteroid'] = None
        except Exception:
            card_data['tons_per_asteroid'] = None
        
        # Build materials dict with tons and tph - handle both dict and numeric formats
        materials_mined = cargo_session_data.get('materials_mined', {})
        for material_name, quantity in materials_mined.items():
            # Handle nested dict structure
            if isinstance(quantity, dict):
                # Already has tons and tph
                tons = quantity.get('tons', 0)
                mat_tph = quantity.get('tph', 0)
            else:
                # Just a number
                tons = float(quantity) if quantity else 0
                mat_tph = tons / session_duration_hours if session_duration_hours > 0 else 0
            
            card_data['materials_mined'][material_name] = {
                'tons': tons,
                'tph': mat_tph
            }
        
        return generate_mining_card(card_data, output_path, cmdr_info)
        
    except Exception as e:
        print(f"[MINING CARD] Error creating card: {e}")
        import traceback
        traceback.print_exc()
        return False
