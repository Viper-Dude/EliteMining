"""Mining Card actions for the Reports tab (moved from prospector_panel.py)."""

import logging
import os

from config import scaled_font

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key

log = logging.getLogger("prospector_panel")


class MiningCardMixin:
    def _get_cmdr_info_for_card(self):
        """Get CMDR name and comment for mining card (similar to Discord share)"""
        try:
            from config import _load_cfg
            
            # Check if CMDR name is already saved
            cfg = _load_cfg()
            saved_cmdr = cfg.get('cmdr_name', '').strip()
            
            # Show dialog
            cmdr_result = self._show_cmdr_dialog(saved_cmdr)
            return cmdr_result
                
        except Exception as e:
            log.error(f"[DEBUG] Error getting CMDR info: {e}")
            return None

    def _show_cmdr_dialog(self, current_cmdr=""):
        """Show custom CMDR input dialog (adapted from Discord dialog)"""
        try:
            import tkinter as tk
            
            # Create toplevel window
            dialog = tk.Toplevel(self.winfo_toplevel())
            dialog.title("Mining Card Info")
            dialog.configure(bg="#1e1e1e")
            dialog.resizable(False, False)
            
            # Set app icon
            try:
                from icon_utils import set_window_icon
                set_window_icon(dialog)
            except Exception as e:
                print(f"[DEBUG] Could not set dialog icon: {e}")
            
            # Make it modal FIRST
            dialog.transient(self.winfo_toplevel())
            
            # Set size
            dialog_width = 450
            dialog_height = 300
            
            # Force dialog to appear on same screen as main window
            main_window = self.winfo_toplevel()
            
            # Wait for main window to be ready
            main_window.update()
            dialog.update()
            
            # Get main window center
            main_x = main_window.winfo_x()
            main_y = main_window.winfo_y()
            main_width = main_window.winfo_width()
            main_height = main_window.winfo_height()
            
            # Calculate center position
            x = main_x + (main_width - dialog_width) // 2
            y = main_y + (main_height - dialog_height) // 2
            
            # Set position explicitly
            dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
            
            # Force it to appear
            dialog.update()
            dialog.deiconify()
            dialog.grab_set()
            dialog.focus_force()
            
            # Main frame
            main_frame = tk.Frame(dialog, bg="#1e1e1e")
            main_frame.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Title
            title_label = tk.Label(main_frame, text="Add Your Info to Card",
                                  font=scaled_font(14, "bold", family="Arial"),
                                  fg="#FF8C00", bg="#1e1e1e")
            title_label.pack(pady=(0, 15))

            # CMDR Name label
            cmdr_label = tk.Label(main_frame, text="CMDR Name (optional):",
                                 font=scaled_font(10, family="Arial"),
                                 fg="#ffffff", bg="#1e1e1e")
            cmdr_label.pack(anchor="w", pady=(0, 5))

            # CMDR Name input
            cmdr_entry = tk.Entry(main_frame, font=scaled_font(11, family="Arial"), width=35,
                                 bg="#333333", fg="#ffffff",
                                 insertbackground="#ffffff",
                                 relief="solid", bd=1)
            cmdr_entry.pack(pady=(0, 15))
            cmdr_entry.insert(0, current_cmdr)
            cmdr_entry.focus()
            cmdr_entry.select_range(0, tk.END)

            # Comment label
            comment_label = tk.Label(main_frame, text="Comment (optional):",
                                   font=scaled_font(10, family="Arial"),
                                   fg="#ffffff", bg="#1e1e1e")
            comment_label.pack(anchor="w", pady=(0, 5))

            # Comment input
            comment_entry = tk.Entry(main_frame, font=scaled_font(10, family="Arial"), width=35,
                                   bg="#333333", fg="#ffffff",
                                   insertbackground="#ffffff",
                                   relief="solid", bd=1)
            comment_entry.pack(pady=(0, 20))
            
            # Result variable
            result = {"cmdr": None, "comment": None}
            
            def on_ok():
                cmdr = cmdr_entry.get().strip()
                comment = comment_entry.get().strip()
                
                # Save CMDR name to config if provided
                if cmdr:
                    from config import update_config_value
                    update_config_value("cmdr_name", cmdr)
                
                result["cmdr"] = cmdr if cmdr else None
                result["comment"] = comment if comment else None
                dialog.destroy()
            
            def on_skip():
                # Skip without saving
                dialog.destroy()
            
            # Buttons frame
            button_frame = tk.Frame(main_frame, bg="#1e1e1e")
            button_frame.pack(pady=(10, 0))
            
            ok_button = tk.Button(button_frame, text="OK", command=on_ok,
                                 font=scaled_font(10, "bold", family="Arial"),
                                 bg="#FF8C00", fg="#ffffff",
                                 activebackground="#FFA500",
                                 activeforeground="#ffffff",
                                 width=10, relief="flat", cursor="hand2")
            ok_button.pack(side="left", padx=5)

            skip_button = tk.Button(button_frame, text="Skip", command=on_skip,
                                   font=scaled_font(10, family="Arial"),
                                   bg="#555555", fg="#ffffff",
                                   activebackground="#666666",
                                   activeforeground="#ffffff",
                                   width=10, relief="flat", cursor="hand2")
            skip_button.pack(side="left", padx=5)
            
            # Bind Enter key to OK
            dialog.bind('<Return>', lambda e: on_ok())
            dialog.bind('<Escape>', lambda e: on_skip())
            
            # Wait for dialog to close
            dialog.wait_window()
            
            return result
            
        except Exception as e:
            log.error(f"[DEBUG] Error showing CMDR dialog: {e}")
            import traceback
            traceback.print_exc()
            return None


    def _create_mining_card_from_report(self):
        """Create mining card PNG from selected report in main Reports tab"""
        try:
            selected = self.reports_tree_tab.selection()
            if not selected:
                from tkinter import messagebox
                messagebox.showwarning("No Selection", "Please select a mining session to create a card.")
                return
            
            item_id = selected[0]
            if item_id not in self.reports_tab_session_lookup:
                from tkinter import messagebox
                messagebox.showerror("Error", "Session data not found for selected item.")
                return
            
            session = self.reports_tab_session_lookup[item_id]
            
            # Get CMDR name and comment
            cmdr_info = self._get_cmdr_info_for_card()
            if cmdr_info is None:
                return  # User cancelled
            
            self._generate_mining_card(session, cmdr_info)
            
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to create mining card: {e}")


    def _get_card_path(self, session) -> str:
        """Expected Cards/ PNG path for a session (file may not exist)"""
        from path_utils import get_reports_dir
        import datetime

        system = session.get('system', 'Unknown')
        body = session.get('body', 'Unknown')
        file_path = session.get('file_path', '')

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        if file_path and os.path.exists(file_path):
            filename = os.path.basename(file_path)
            if filename.startswith('Session_'):
                parts = filename.replace('.txt', '').split('_')
                if len(parts) >= 3:
                    timestamp = f"{parts[1]}_{parts[2]}"

        card_filename = f"Session_{timestamp}_{system.replace(' ', '_')}_{body.replace(' ', '_')}_Card.png"
        return os.path.join(get_reports_dir(), "Cards", card_filename)

    def _selected_report_card_exists(self) -> bool:
        selected = self.reports_tree_tab.selection()
        session = self.reports_tab_session_lookup.get(selected[0]) if len(selected) == 1 else None
        return bool(session) and os.path.exists(self._get_card_path(session))

    def _update_card_button(self) -> None:
        key = 'reports.open_mining_card' if self._selected_report_card_exists() else 'reports.mining_card'
        self._card_btn.configure(text=t(key))

    def _on_mining_card_button(self) -> None:
        if self._selected_report_card_exists():
            self._open_mining_card_from_report()
        else:
            self._create_mining_card_from_report()
            self._update_card_button()

    def _open_mining_card_from_report(self):
        """Open the saved mining card PNG for the selected report"""
        selected = self.reports_tree_tab.selection()
        session = self.reports_tab_session_lookup.get(selected[0]) if selected else None
        card_path = self._get_card_path(session) if session else None
        if card_path and os.path.exists(card_path):
            os.startfile(card_path)

    def _generate_mining_card(self, session, cmdr_info=None):
        """Generate mining card PNG from session data"""
        try:
            from mining_card_generator import create_card_from_session
            import subprocess

            # Parse session data to extract needed info
            system = session.get('system', 'Unknown')
            body = session.get('body', 'Unknown')
            duration = session.get('duration', 'Unknown')
            ship = session.get('ship', None)
            session_type_from_session = session.get('session_type', '')
            file_path = session.get('file_path', '')

            card_path = self._get_card_path(session)
            os.makedirs(os.path.dirname(card_path), exist_ok=True)
            card_filename = os.path.basename(card_path)

            # Parse materials from report file
            materials_mined = {}
            total_tons = 0
            tph = 0
            prospectors_used = 0
            session_duration_hours = 0
            avg_yield = 0
            session_type = session_type_from_session
            
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Parse ship name if not already available
                    if not ship:
                        for line in content.split('\n'):
                            if line.startswith('Ship:'):
                                ship = line.replace('Ship:', '').strip()
                                break
                    
                    # Parse session type if in header
                    if not session_type and '(Single Session)' in content:
                        session_type = 'Single Session'
                    elif not session_type and '(Multi-Session)' in content:
                        session_type = 'Multi-Session'
                    
                    # Parse MINERAL ANALYSIS section for prospecting data
                    asteroids_prospected = 0
                    hit_rate = 0
                    prospecting_speed = 0
                    mineral_performance = {}  # Dict of {mineral_name: {avg, best, finds}}
                    
                    if '=== MINERAL ANALYSIS ===' in content:
                        lines = content.split('\n')
                        in_analysis = False
                        in_performance = False
                        current_mineral = None
                        
                        for i, line in enumerate(lines):
                            if '=== MINERAL ANALYSIS ===' in line:
                                in_analysis = True
                                continue
                            if in_analysis:
                                if line.startswith('==='):
                                    break
                                if '--- Mineral Performance ---' in line:
                                    in_performance = True
                                    continue
                                    
                                if 'Overall Quality:' in line and '%' in line:
                                    try:
                                        avg_yield = float(line.split(':')[1].split('%')[0].strip())
                                    except:
                                        pass
                                elif 'Asteroids Prospected:' in line:
                                    try:
                                        asteroids_prospected = int(line.split(':')[1].strip())
                                    except:
                                        pass
                                elif 'Hit Rate:' in line and '%' in line:
                                    try:
                                        hit_rate = float(line.split(':')[1].split('%')[0].strip())
                                    except:
                                        pass
                                elif 'Prospecting Speed:' in line:
                                    try:
                                        prospecting_speed = float(line.split(':')[1].split('asteroids')[0].strip())
                                    except:
                                        pass
                                
                                # Parse mineral performance details
                                if in_performance:
                                    if line.strip() and not line.startswith('  ') and ':' in line and line.strip().endswith(':'):
                                        # This is a mineral name line like "Bromellite:"
                                        current_mineral = line.strip().rstrip(':')
                                        mineral_performance[current_mineral] = {'avg': 0, 'best': 0, 'finds': 0, 'core_hits': 0}
                                    elif current_mineral and '• Average:' in line:
                                        try:
                                            avg_val = float(line.split(':')[1].split('%')[0].strip())
                                            mineral_performance[current_mineral]['avg'] = avg_val
                                        except:
                                            pass
                                    elif current_mineral and '• Best:' in line:
                                        try:
                                            best_val = float(line.split(':')[1].split('%')[0].strip())
                                            mineral_performance[current_mineral]['best'] = best_val
                                        except:
                                            pass
                                    elif current_mineral and '• Core Hits:' in line:
                                        try:
                                            core_hits_val = int(line.split(':', 1)[1].strip())
                                            mineral_performance[current_mineral]['core_hits'] = core_hits_val
                                        except:
                                            pass
                                    elif current_mineral and ('• Hits:' in line or '• Finds:' in line):
                                        try:
                                            # Support legacy 'Finds: 12x' and new 'Hits: 12'
                                            raw_val = line.split(':', 1)[1].strip()
                                            raw_val = raw_val.replace('x', '')
                                            hits_val = int(raw_val)
                                            mineral_performance[current_mineral]['finds'] = hits_val
                                        except:
                                            pass
                    
                    # Parse engineering materials section
                    engineering_materials_total = 0
                    engineering_materials_list = []  # List of {material, grade, quantity}
                    materials_tracked = 0
                    total_finds = 0
                    
                    if '=== ENGINEERING MATERIALS COLLECTED ===' in content:
                        lines = content.split('\n')
                        in_eng_section = False
                        current_grade = None
                        for line in lines:
                            if '=== ENGINEERING MATERIALS COLLECTED ===' in line:
                                in_eng_section = True
                                continue
                            if in_eng_section:
                                if line.startswith('==='):
                                    break
                                if 'Total Engineering Materials:' in line:
                                    try:
                                        engineering_materials_total = int(line.split(':')[1].split('pieces')[0].strip())
                                    except:
                                        pass
                                elif 'Grade' in line and '(' in line and line.strip().endswith(':'):
                                    # Parse grade info like "Grade 1 (Very Common):"
                                    try:
                                        current_grade = line.split('(')[0].strip()
                                    except:
                                        pass
                                elif current_grade and ':' in line and line.strip() and not line.strip().startswith('Total'):
                                    # Parse material line like "  Nickel: 18"
                                    try:
                                        parts = line.split(':')
                                        material_name = parts[0].strip()
                                        quantity = int(parts[1].strip())
                                        engineering_materials_list.append({
                                            'material': material_name,
                                            'grade': current_grade,
                                            'quantity': quantity
                                        })
                                    except:
                                        pass
                    
                    # Parse materials tracked and total finds from MINERAL ANALYSIS
                    if '=== MINERAL ANALYSIS ===' in content:
                        lines = content.split('\n')
                        for line in lines:
                            if 'Minerals Tracked:' in line:
                                try:
                                    materials_tracked = int(line.split(':')[1].strip())
                                except:
                                    pass
                            elif 'Total Material Hits:' in line or 'Total Material Finds:' in line:
                                try:
                                    raw_val = line.split(':', 1)[1].strip()
                                    raw_val = raw_val.replace('x', '')
                                    total_finds = int(raw_val)
                                except:
                                    pass
                    
                    # Parse materials from CARGO MATERIAL BREAKDOWN section
                    if '=== CARGO MATERIAL BREAKDOWN ===' in content:
                        lines = content.split('\n')
                        in_materials = False
                        for line in lines:
                            if '=== CARGO MATERIAL BREAKDOWN ===' in line:
                                in_materials = True
                                continue
                            if in_materials:
                                if line.startswith('==='):
                                    break
                                if 'Prospector Limpets Used:' in line:
                                    try:
                                        prospectors_used = int(line.split(':')[1].strip())
                                    except:
                                        pass
                                elif ':' in line and 't' in line and '(' in line:
                                    # Parse material line: "Material: XXt (YY.Y t/hr)"
                                    try:
                                        parts = line.split(':')
                                        if len(parts) >= 2:
                                            mat_name = parts[0].strip()
                                            rest = parts[1].strip()
                                            tons_part = rest.split('t')[0].strip()
                                            tons = float(tons_part)
                                            
                                            tph_part = rest.split('(')[1].split('t/hr')[0].strip()
                                            mat_tph = float(tph_part)
                                            
                                            materials_mined[mat_name] = {
                                                'tons': tons,
                                                'tph': mat_tph
                                            }
                                            total_tons += tons
                                    except Exception as e:
                                        log.error(f"[CARD] Error parsing material line: {line}, {e}")
                    
                    # Parse session duration for overall TPH from first line
                    lines = content.split('\n')
                    if lines and '—' in lines[0]:
                        first_line = lines[0]
                        if 'Total' in first_line and 't' in first_line:
                            try:
                                # Extract duration (format: "Session: System — Body — HH:MM:SS — Total XXt")
                                parts = first_line.split('—')
                                if len(parts) >= 3:
                                    duration_str = parts[2].strip()
                                    
                                    # Parse duration - could be "HH:MM:SS" or "XXh YYm"
                                    if ':' in duration_str:
                                        time_parts = duration_str.split(':')
                                        if len(time_parts) == 3:
                                            h = int(time_parts[0])
                                            m = int(time_parts[1])
                                            s = int(time_parts[2])
                                            session_duration_hours = h + (m / 60.0) + (s / 3600.0)
                                    elif 'h' in duration_str:
                                        h = int(duration_str.split('h')[0].strip())
                                        m_str = duration_str.split('h')[1].split('m')[0].strip() if 'm' in duration_str else '0'
                                        m = int(m_str) if m_str else 0
                                        session_duration_hours = h + (m / 60.0)
                                    
                                    # Extract total tons
                                    if 'Total' in first_line:
                                        total_match = first_line.split('Total')[1].split('t')[0].strip()
                                        parsed_total = float(total_match.replace(',', ''))
                                        if parsed_total > 0:
                                            total_tons = parsed_total
                                    
                                    # Calculate TPH
                                    if session_duration_hours > 0 and total_tons > 0:
                                        tph = total_tons / session_duration_hours
                                        print(f"[CARD] Calculated TPH: {tph:.1f} from {total_tons:.0f}t / {session_duration_hours:.2f}h")
                            except Exception as e:
                                log.error(f"[CARD] Error parsing session stats: {e}")
                                import traceback
                                traceback.print_exc()
            
            # Build cargo session data structure
            cargo_session_data = {
                'total_tons_mined': total_tons,
                'session_duration': session_duration_hours * 3600,
                'materials_mined': materials_mined,
                'prospectors_used': prospectors_used,
                'session_type': session_type,
                'avg_yield': avg_yield,
                'asteroids_prospected': asteroids_prospected,
                'hit_rate': hit_rate,
                'prospecting_speed': prospecting_speed,
                'mineral_performance': mineral_performance,
                'engineering_materials_total': engineering_materials_total,
                'engineering_materials_list': engineering_materials_list,
                'materials_tracked': materials_tracked,
                'total_finds': total_finds
            }
            
            # Build session info
            session_info = {
                'system': system,
                'body': body,
                'ship': ship,
                'duration_text': duration
            }
            
            print(f"[CARD DEBUG] session_info: {session_info}")
            print(f"[CARD DEBUG] cargo_session_data session_type: {cargo_session_data.get('session_type')}")
            
            # Generate the card
            if create_card_from_session(cargo_session_data, session_info, card_path, cmdr_info):
                print(f"[CARD] Mining card generated: {card_filename}")
                
                # Open the card image directly
                if os.name == 'nt':  # Windows
                    os.startfile(card_path)
                else:  # macOS/Linux
                    subprocess.Popen(['xdg-open', card_path])
                    
            else:
                from tkinter import messagebox
                messagebox.showerror("Error", "Failed to generate mining card.")
                
        except Exception as e:
            log.error(f"[CARD] Error generating mining card: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to generate mining card: {e}")
