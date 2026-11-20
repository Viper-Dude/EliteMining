"""Mining Card actions for the Reports tab (moved from prospector_panel.py)."""

import logging
import os
import re

from config import scaled_font

try:
    from localization import t
except Exception:
    def t(key, **kwargs):
        return key

log = logging.getLogger("prospector_panel")


class MiningCardMixin:
    def _get_cmdr_info_for_card(self, session=None, share=False):
        """Get CMDR name and comment for the card; None means cancelled."""
        try:
            from config import _load_cfg
            saved_cmdr = _load_cfg().get('cmdr_name', '').strip()
            return self._show_cmdr_dialog(saved_cmdr, self._report_comment(session) if session else "", share)
        except Exception as e:
            log.error(f"[CARD] Error getting CMDR info: {e}")
            return None

    @staticmethod
    def _report_comment(session) -> str:
        """Comment saved with the session, so the card dialog doesn't ask for it again."""
        comment = (session.get('comment') or "").strip()
        file_path = session.get('file_path', '')
        if not comment and file_path and os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    match = re.search(r'=== SESSION COMMENT ===\s*\n(.+?)(?:\n===|$)', f.read(), re.DOTALL)
                comment = match.group(1).strip() if match else ""
            except OSError:
                comment = ""
        return " ".join(comment.split())

    @staticmethod
    def _session_date_text(session) -> str:
        """Session start from the report file name (Session_YYYY-MM-DD_HH-MM-SS_...)."""
        match = re.match(r'Session_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})', os.path.basename(session.get('file_path', '')))
        return f"{match.group(1)} {match.group(2)}:{match.group(3)}" if match else ""

    def _show_cmdr_dialog(self, current_cmdr="", current_comment="", share=False):
        """Ask for the CMDR name and comment shown on the card."""
        try:
            import tkinter as tk
            from config import load_theme
            from ui.theme import get_theme_colors
            from ui.dialogs import center_window
            from app_utils import create_action_button, get_app_icon_path

            c = get_theme_colors(load_theme())
            bg, fg = c['bg'], c['fg']
            field_bg = c.get('panel', c['bg_accent'])
            heading_fg = c.get('accent', c['tip_fg'])
            parent = self.winfo_toplevel()

            dialog = tk.Toplevel(parent)
            dialog.withdraw()
            dialog.title(t('mining_card.dialog_title'))
            dialog.configure(bg=bg)
            dialog.resizable(False, False)
            try:
                icon_path = get_app_icon_path()
                if icon_path and icon_path.endswith('.ico'):
                    dialog.iconbitmap(icon_path)
            except Exception:
                pass

            frame = tk.Frame(dialog, bg=bg)
            frame.pack(fill="both", expand=True, padx=20, pady=18)
            tk.Label(frame, text=t('mining_card.dialog_heading'), font=scaled_font(13, "bold"),
                     fg=heading_fg, bg=bg).pack(anchor="w", pady=(0, 14))

            def field(label_key, value):
                tk.Label(frame, text=t(label_key), font=scaled_font(10), fg=fg, bg=bg).pack(anchor="w", pady=(0, 4))
                entry = tk.Entry(frame, font=scaled_font(10), width=42, bg=field_bg, fg=fg, insertbackground=fg,
                                 relief="solid", bd=1, highlightthickness=0)
                entry.pack(fill="x", pady=(0, 12))
                entry.insert(0, value)
                return entry

            cmdr_entry = field('mining_card.cmdr_label', current_cmdr)
            comment_entry = field('mining_card.comment_label', current_comment)

            result = {"cmdr": None, "comment": None}

            def on_ok():
                cmdr = cmdr_entry.get().strip()
                comment = comment_entry.get().strip()
                if cmdr:
                    from config import update_config_value
                    update_config_value("cmdr_name", cmdr)
                result["cmdr"] = cmdr or None
                result["comment"] = comment or None
                dialog.destroy()

            buttons = tk.Frame(frame, bg=bg)
            buttons.pack(anchor="e", pady=(6, 0))
            create_action_button(buttons, primary=True, text=t('common.ok'), command=on_ok).pack(side="left", padx=(0, 8))
            def on_cancel():
                # Sharing can be cancelled; for a card, Skip still makes it without the info
                if share:
                    result.clear()
                dialog.destroy()

            create_action_button(buttons, text=t('common.cancel' if share else 'mining_card.skip'),
                                 command=on_cancel).pack(side="left")
            dialog.protocol("WM_DELETE_WINDOW", on_cancel)

            dialog.bind('<Return>', lambda e: on_ok())
            dialog.bind('<Escape>', lambda e: on_cancel())

            center_window(dialog, parent)
            dialog.deiconify()
            dialog.grab_set()
            cmdr_entry.focus_set()
            cmdr_entry.select_range(0, tk.END)
            dialog.wait_window()
            return result or None

        except Exception as e:
            log.error(f"[CARD] Error showing CMDR dialog: {e}")
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
            cmdr_info = self._get_cmdr_info_for_card(session)
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

    def _ring_details(self, system, body):
        """Translated (ring type, reserve level) from saved ring data; "" when unknown."""
        user_db = getattr(getattr(getattr(self, 'main_app', None), 'cargo_monitor', None), 'user_db', None)
        if not (user_db and system and body):
            return "", ""
        from ring_finder import translate_ring_type, translate_reserve_level
        ring_type = translate_ring_type(user_db.get_ring_type(system, body) or "")
        # Old density values stored in the same column translate to "" and are skipped
        reserve = translate_reserve_level(user_db.get_reserve_level(system, body))
        return ring_type or "", reserve or ""

    def _discord_card_text(self, system, body) -> str:
        """Message above the card; the system name sits in a code block so it can be copied."""
        lines = [f"**{t('mining_card.post_system')}**", f"```{system}```"] if system else []
        if body:
            lines.append(f"**{t('mining_card.post_ring')}** {body}")
            ring_type, reserve = self._ring_details(system, body)
            if ring_type:
                lines.append(f"**{t('mining_card.post_ring_type')}** {ring_type}")
            if reserve:
                lines.append(f"**{t('mining_card.post_reserve')}** {reserve}")
        return "\n".join(lines)

    def _share_to_discord(self):
        """Share the selected session to Discord as a Mining Card."""
        if getattr(self, '_discord_share_in_progress', False):
            return
        from app_utils import centered_message
        selected = self.reports_tree_tab.selection()
        if not selected:
            centered_message(self.winfo_toplevel(), "No Selection", "Please select a mining session to share to Discord.")
            return
        session = self.reports_tab_session_lookup.get(selected[0])
        if not session:
            centered_message(self.winfo_toplevel(), "Error", "Session data not found for selected item.")
            return

        from discord_integration import is_discord_enabled, send_mining_card
        if not is_discord_enabled():
            centered_message(self.winfo_toplevel(), "Discord Sharing",
                             "Discord sharing is not available in this version.\n\n"
                             "Contact the administrator if you believe this is an error.")
            return

        cmdr_info = self._get_cmdr_info_for_card(session, share=True)
        if cmdr_info is None:
            return
        card_path = self._generate_mining_card(session, cmdr_info, open_card=False)
        if not card_path:
            return
        self._update_card_button()

        import threading
        parent = self.winfo_toplevel()
        system, body = session.get('system', ''), session.get('body', '')
        self._discord_share_in_progress = True

        def worker():
            try:
                success, message = send_mining_card(card_path, self._discord_card_text(system, body))
            except Exception as e:
                success, message = False, f"Failed to share to Discord: {e}"
            if success:
                message = t('mining_card.shared')
            if not getattr(parent, '_network_closing', False):
                try:
                    parent.after(0, self._finish_discord_share, success, message)
                except RuntimeError:
                    pass
        threading.Thread(target=worker, daemon=True).start()

    def _generate_mining_card(self, session, cmdr_info=None, open_card=True):
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
            core_asteroids = 0
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
                                elif 'Core Asteroids Found:' in line:
                                    try:
                                        core_asteroids = int(line.split(':')[1].strip())
                                    except ValueError:
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
                'core_asteroids': core_asteroids,
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
                'duration_text': duration,
                'session_date': self._session_date_text(session),
            }
            session_info['ring_type'], session_info['reserve'] = self._ring_details(system, body)
            
            
            # Generate the card
            if create_card_from_session(cargo_session_data, session_info, card_path, cmdr_info):
                print(f"[CARD] Mining card generated: {card_filename}")
                if open_card:
                    if os.name == 'nt':  # Windows
                        os.startfile(card_path)
                    else:  # macOS/Linux
                        subprocess.Popen(['xdg-open', card_path])
                return card_path
            from tkinter import messagebox
            messagebox.showerror("Error", "Failed to generate mining card.")
            return None

        except Exception as e:
            log.error(f"[CARD] Error generating mining card: {e}")
            import traceback
            traceback.print_exc()
            from tkinter import messagebox
            messagebox.showerror("Error", f"Failed to generate mining card: {e}")
            return None
