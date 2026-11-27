"""VoiceAttack Controls tab and its sub-tabs (moved from main.py)."""

import os
import tkinter as tk
from tkinter import ttk

import announcer
from config import _load_cfg
from core.constants import (
    FIREGROUPS, VA_VARS, TOOL_ORDER, TOGGLES, TIMERS, SOUND_EVENT_CATEGORIES, SOUND_CATEGORY_ORDER,
)
from localization import t
from ui.segmented_selector import SegmentedSelector
from ui.stepper import Stepper
from ui.themed_checkbox import ThemedCheckbutton
from ui.themed_slider import ThemedSlider, slider_colors
from ui.tooltip import ToolTip


class VoiceAttackControlsTabMixin:
    def _build_voiceattack_controls_tab(self, frame: ttk.Frame) -> None:
        """Build the VoiceAttack Controls tab with Mining Controls and Firegroups"""
        # Title row with help link
        va_title_row = ttk.Frame(frame)
        va_title_row.pack(fill="x", pady=(0, 5))
        ttk.Label(va_title_row, text=t('tabs.voiceattack_controls'), font=self._scaled_font(9, "bold")).pack(side="left")
        from ui.help_link import create_help_link
        create_help_link(va_title_row, "voiceattack-controls", t('voiceattack.help_tooltip'), ToolTip).pack(side="left", padx=(6, 0))

        # Create a notebook for VoiceAttack sub-tabs
        self.voiceattack_notebook = ttk.Notebook(frame)
        self.voiceattack_notebook.pack(fill="both", expand=True)

        # === MINING CONTROLS SUB-TAB ===
        mining_controls_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_timers_tab(mining_controls_tab)
        self.voiceattack_notebook.add(mining_controls_tab, text=t('voiceattack.mining_controls'))

        # === FIREGROUPS & FIRE BUTTONS SUB-TAB ===
        firegroups_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_fg_tab(firegroups_tab)
        self.voiceattack_notebook.add(firegroups_tab, text=t('voiceattack.firegroups'))

        # === VOICE FEEDBACK SUB-TAB ===
        voice_feedback_tab = ttk.Frame(self.voiceattack_notebook, padding=8)
        self._build_voice_feedback_tab(voice_feedback_tab)
        self.voiceattack_notebook.add(voice_feedback_tab, text=t('voiceattack.section_voice_feedback'))

    def _build_voice_feedback_tab(self, frame: ttk.Frame) -> None:
        """Voice Feedback sub-tab: voice toggles, volume/balance, per-event sound selection"""
        from config import load_theme
        _bg = "#000000" if load_theme() == "elite_orange" else "#1e1e1e"
        canvas = tk.Canvas(frame, bg=_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        def _update_scrollregion(event=None):
            # Never let the region be shorter than the viewport, or short content can be scrolled into empty space
            canvas.configure(scrollregion=(0, 0, scrollable_frame.winfo_reqwidth(),
                                           max(scrollable_frame.winfo_reqheight(), canvas.winfo_height())))
            if scrollable_frame.winfo_reqheight() > canvas.winfo_height():
                scrollbar.pack(side="right", fill="y")
            else:
                scrollbar.pack_forget()
        scrollable_frame.bind("<Configure>", _update_scrollregion)
        canvas.bind("<Configure>", _update_scrollregion)
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        def _bind_mousewheel_recursive(widget):
            if isinstance(widget, ttk.Combobox):
                return
            widget.bind("<MouseWheel>", _on_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)
        canvas.bind("<MouseWheel>", _on_mousewheel)
        frame.after(100, lambda: _bind_mousewheel_recursive(scrollable_frame))

        scrollable_frame.columnconfigure(0, weight=1)
        _toggle_bg = "#000000" if self.current_theme == "elite_orange" else "#1e1e1e"
        _toggle_fg = "#ff8c00" if self.current_theme == "elite_orange" else "#ffffff"
        toggle_help_translations = {
            "Voice Feedback": "voiceattack.help_voice_feedback",
        }
        r = 0

        # ============================================================
        # VOICE FEEDBACK SUB-SECTION
        # ============================================================
        vf_title_row = ttk.Frame(scrollable_frame, style="Dark.TFrame")
        vf_title_row.grid(row=r, column=0, sticky="w", pady=(10, 2))
        ttk.Label(vf_title_row, text=t('voiceattack.section_voice_feedback'), font=self._scaled_font(10, "bold")).pack(side="left")
        from ui.help_link import create_help_link
        create_help_link(vf_title_row, "voice-feedback", t('voiceattack.voice_feedback_help_tooltip'), ToolTip).pack(side="left", padx=(6, 0))
        r += 1

        for name in ["Voice Feedback"]:
            _fname, helptext = TOGGLES[name]

            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)

            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name],
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                    highlightthickness=0, bd=0, font=self._scaled_font(9),
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")

            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))

            display_help = t(toggle_help_translations[name])
            ToolTip(checkbox, display_help)

            r += 1

        self._vf_controls = []
        self._vf_tts_syncs = []
        _sl_trough = "#1a1a1a" if self.current_theme == "elite_orange" else "#444444"
        _sl_active = "#ff6600" if self.current_theme == "elite_orange" else "#444444"
        for label_key, var_name, lo, hi, default in (
            ('voiceattack.sound_volume', 'sound_volume', 0, 100, 90),
            ('voiceattack.sound_balance', 'sound_balance', -100, 100, 0),
        ):
            try:
                initial = int(_load_cfg().get(var_name, default))
            except (TypeError, ValueError):
                initial = default
            setattr(self, var_name, tk.IntVar(value=max(lo, min(hi, initial))))

            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            tk.Label(rowf, text=t(label_key), bg=_toggle_bg, fg=_toggle_fg,
                     font=self._scaled_font(9), width=14, anchor="w").pack(side="left", padx=(4, 0))
            scale = ThemedSlider(rowf, lo, hi, getattr(self, var_name), command=lambda v: self._write_sound_levels(),
                                 length=self._scaled_px(200), bg=_toggle_bg, fg=_toggle_fg,
                                 font=self._scaled_font(9), fill_from_center=(var_name == 'sound_balance'),
                                 scale=self._scaled_px(100) / 100, **slider_colors(self.current_theme))
            scale.pack(side="left", padx=(8, 0))
            self._vf_controls.append((scale, "normal"))
            if var_name == 'sound_balance':
                ToolTip(scale, t('voiceattack.sound_balance_tip'))
                scale.bind("<Double-Button-1>", lambda e: (self.sound_balance.set(0), self._write_sound_levels()))
            r += 1
        self._write_sound_levels()

        _evhead = ttk.Frame(scrollable_frame, style="Dark.TFrame")
        _evhead.grid(row=r, column=0, sticky="w", pady=(10, 2))
        ttk.Label(_evhead, text=t('voiceattack.section_sound_events'), font=self._scaled_font(10, "bold")).pack(side="left")
        _reset_all_btn = ttk.Button(_evhead, text=t('voiceattack.sound_reset_all'), style="Small.TButton",
                                    command=lambda: self._reset_sound_events())
        _reset_all_btn.pack(side="left", padx=(12, 0))
        self._vf_controls.append((_reset_all_btn, "normal"))
        r += 1
        ttk.Label(scrollable_frame, text=t('voiceattack.voice_set_hint'), font=self._scaled_font(8)).grid(row=r, column=0, sticky="w", pady=(0, 2))
        r += 1
        _cfg = _load_cfg()
        _saved_events = _cfg.get("sound_events", {})
        _saved_tts = _cfg.get("sound_event_tts", {})
        _off_label = t('voiceattack.sound_event_off')
        _tts_label = t('voiceattack.sound_event_tts')
        _default_voice = "Female"
        _tts_voices = announcer.list_voices()
        self.sound_event_options = self._list_sound_events()
        self.sound_event_vars = {}
        self.sound_event_tts_vars = {}
        self.sound_event_names = {}
        self.sound_event_combos = {}
        self._sound_event_packs = {}
        _set_labels = sorted(self._sound_label_map) + [_tts_label, _off_label]
        self._voice_set_active = {c: l for c, l in _cfg.get("sound_voice_sets", {}).items() if l in _set_labels}
        self._voice_set_vars = {}
        _last_category = None
        _ordered_events = sorted(self.sound_event_options.items(),
                                 key=lambda kv: SOUND_CATEGORY_ORDER.index(SOUND_EVENT_CATEGORIES.get(kv[0], "other")))
        for event, packs in _ordered_events:
            _category = SOUND_EVENT_CATEGORIES.get(event, "other")
            if _category != _last_category:
                _last_category = _category
                ttk.Label(scrollable_frame, text=t(f'voiceattack.sound_category_{_category}'),
                          font=self._scaled_font(9, "bold")).grid(row=r, column=0, sticky="w", pady=(6, 2))
                r += 1
                if _set_labels:
                    setf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                    setf.grid(row=r, column=0, sticky="w", pady=(0, 4))
                    tk.Label(setf, text=t('voiceattack.voice_set'), bg=_toggle_bg, fg=_toggle_fg,
                             font=self._scaled_font(9)).pack(side="left", padx=(4, 8))
                    for label in _set_labels:
                        sv = tk.BooleanVar(value=(label == self._voice_set_active.get(_category)))
                        self._voice_set_vars[(_category, label)] = sv
                        _set_cb = ThemedCheckbutton(setf, text=label, variable=sv,
                                       command=lambda c=_category, l=label: self._on_voice_set_toggle(c, l),
                                       bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                       activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                       highlightthickness=0, bd=0, font=self._scaled_font(9),
                                       padx=4, pady=2, anchor="w")
                        self._vf_controls.append((_set_cb, "normal"))
                        _set_cb.pack(side="left", padx=(0, 6))
                    _reset_btn = ttk.Button(setf, text=t('voiceattack.sound_reset'), style="Small.TButton",
                                            command=lambda c=_category: self._reset_sound_events(c))
                    _reset_btn.pack(side="left", padx=(8, 0))
                    self._vf_controls.append((_reset_btn, "normal"))
                    r += 1
            name =t(f'voiceattack.sound_event_{event}')
            if name.endswith(f'sound_event_{event}'):
                name = event.replace('_', ' ').capitalize()
            self.sound_event_names[event] = name
            self._sound_event_packs[event] = packs
            saved = _saved_events.get(event)
            default = next((p for p in packs if p.endswith(f" {_default_voice}")), packs[0])
            _active = self._voice_set_active.get(_category, "")
            if _active:
                initial = _active if _active in packs or _active == _tts_label else _off_label
            elif saved == "":
                initial = _off_label
            elif saved == "tts":
                initial = _tts_label
            else:
                initial = saved if saved in packs else default
            var = tk.StringVar(value=initial)
            self.sound_event_vars[event] = var
            tts_saved = _saved_tts.get(event)
            voice_var = tk.StringVar(value=(tts_saved if tts_saved in _tts_voices else None) or _cfg.get("tts_voice") or (_tts_voices[0] if _tts_voices else ""))
            self.sound_event_tts_vars[event] = voice_var
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            tk.Label(rowf, text=name, bg=_toggle_bg, fg=_toggle_fg,
                     font=self._scaled_font(9), width=40, anchor="w").pack(side="left", padx=(4, 0))
            event_combo = ttk.Combobox(rowf, textvariable=var, values=[_off_label, _tts_label] + packs,
                                       state="readonly", width=22)
            self.sound_event_combos[event] = event_combo
            event_combo.pack(side="left", padx=(8, 0))
            event_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
            event_combo.bind("<<ComboboxSelected>>", lambda e, c=_category: self._clear_voice_set(c), add='+')
            _test_btn = ttk.Button(rowf, text=t('voiceattack.sound_event_test'), style="Small.TButton", width=5,
                                   command=lambda e=event: self._test_sound_event(e))
            _test_btn.pack(side="left", padx=(8, 0))
            self._vf_controls.append((_test_btn, "normal"))
            self._vf_controls.append((event_combo, "readonly"))
            voice_combo = ttk.Combobox(rowf, textvariable=voice_var, values=_tts_voices, state="readonly", width=30)
            voice_combo.pack(side="left", padx=(8, 0))
            voice_combo.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')

            def _sync_tts_widgets(*args, v=var, vc=voice_combo):
                vc.configure(state="readonly" if v.get() == _tts_label and self.toggle_vars["Voice Feedback"].get() else "disabled")
            var.trace_add("write", _sync_tts_widgets)
            self._vf_tts_syncs.append(_sync_tts_widgets)
            _sync_tts_widgets()
            for tv in (var, voice_var):
                tv.trace_add("write", lambda *args: self._save_sound_events())
            r += 1
        frame.after(500, self._poll_sound_trigger)
        self._save_sound_events()

        # Config is the source of truth at startup (all off on a fresh install)
        _cfg = _load_cfg()
        for name, key in self._VOICE_CONFIG_KEYS.items():
            val = 1 if _cfg.get(key) else 0
            self.toggle_vars[name].set(val)
            self._write_var_text(os.path.splitext(TOGGLES[name][0])[0], str(val))
        self.toggle_vars["Voice Feedback"].trace_add("write", lambda *args: self._sync_voice_feedback_enabled())
        self._sync_voice_feedback_enabled()

    # ---------- Firegroups tab ----------
    def _build_fg_tab(self, frame: ttk.Frame) -> None:
        # Columns sized for aligned labels & radios
        frame.grid_columnconfigure(0, weight=0, minsize=230)
        frame.grid_columnconfigure(1, weight=0, minsize=120)
        frame.grid_columnconfigure(2, weight=0, minsize=150)
        frame.grid_columnconfigure(3, weight=1,  minsize=150)

        # Tool name translation mapping
        tool_translations = {
            "Mining lasers/MVR:": "voiceattack.tool_mining_lasers",
            "Discovery scanner:": "voiceattack.tool_discovery_scanner",
            "Prospector limpet:": "voiceattack.tool_prospector",
            "Pulse wave analyser:": "voiceattack.tool_pulse_wave",
            "Seismic charge launcher:": "voiceattack.tool_seismic",
            "Weapons:": "voiceattack.tool_weapons",
            "Sub-surface displacement missile:": "voiceattack.tool_ssm",
        }

        header = ttk.Label(frame, text=t('voiceattack.assign_firegroups'),
                           font=self._scaled_font(11, "bold"))
        header.grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        ttk.Label(frame, text=t('voiceattack.firegroup')).grid(row=1, column=1, sticky="w", padx=(0, 6))
        ttk.Label(frame, text=t('voiceattack.fire_button')).grid(row=1, column=2, columnspan=2, sticky="w")

        row = 2
        for tool in TOOL_ORDER:
            cfg = VA_VARS[tool]
            # Get localized tool name
            display_tool = t(tool_translations.get(tool, tool)) if tool in tool_translations else tool
            ttk.Label(frame, text=display_tool).grid(row=row, column=0, sticky="w", pady=3)

            if cfg["fg"] is not None:
                cb = ttk.Combobox(frame, values=FIREGROUPS, width=6, textvariable=self.tool_fg[tool], state="readonly")
                cb.grid(row=row, column=1, sticky="w")
                self._ship_diff_widgets.append((cb, "style", "TCombobox", (("Firegroups", tool, "fg"),)))
                # Auto-save on change
                self.tool_fg[tool].trace_add("write", lambda *args, t=tool: self._save_firegroup(t))
                # Clear selection
                cb.bind("<<ComboboxSelected>>", lambda e: e.widget.selection_clear(), add='+')
            else:
                ttk.Label(frame, text="—").grid(row=row, column=1, sticky="w")

            if cfg["btn"] is not None:
                fire_btn = SegmentedSelector(
                    frame, [(1, t('voiceattack.primary')), (2, t('voiceattack.secondary'))], self.tool_btn[tool],
                    bg="#1e1e1e", accent=slider_colors(self.current_theme)["accent"], font=self._scaled_font(8),
                    scale=self._scaled_px(100) / 100)
                fire_btn.grid(row=row, column=2, columnspan=2, sticky="w", pady=2)
                self._ship_diff_widgets.append((fire_btn, "outline", "", (("Firegroups", tool, "btn"),)))
                # Auto-save on change
                self.tool_btn[tool].trace_add("write", lambda *args, t=tool: self._save_fire_button(t))
            else:
                ttk.Label(frame, text="—").grid(row=row, column=2, sticky="w")
            row += 1

        # Tip card with bullets - use theme colors
        theme_bg = self.theme_colors["bg"]
        theme_fg = self.theme_colors["fg"]
        card = tk.Frame(frame, bg=theme_bg, borderwidth=0, relief="flat", highlightthickness=0, highlightbackground=theme_bg)
        card.grid(row=row, column=0, columnspan=4, sticky="nsew")
        frame.rowconfigure(row, weight=1)
        card.columnconfigure(0, weight=1)

        # Important notice (always yellow for visibility)
        important_label = tk.Label(
            card, 
            text=t('voiceattack.important_firegroups'),
            font=self._scaled_font(9, "bold"), 
            anchor="w", 
            bg=theme_bg, 
            fg="#ffcc00",
            wraplength=600,
            justify="left"
        )
        important_label.grid(row=0, column=0, sticky="w", padx=8, pady=(60, 8))

        tip_header = tk.Label(card, text=t('voiceattack.tips_help'), font=self._scaled_font(9, "bold"), anchor="w", bg=theme_bg, fg=theme_fg, borderwidth=0, relief="flat", highlightthickness=0)
        tip_header.grid(row=1, column=0, sticky="w", padx=8, pady=(10, 2))

        tips = [
            t('voiceattack.tip_core_mining'),
            t('voiceattack.tip_collector'),
            t('voiceattack.tip_clear_jump'),
            t('voiceattack.tip_stop_all'),
        ]
        r = 2
        for tip in tips:
            lbl = tk.Label(
                card,
                text=f"• {tip}",
                wraplength=600,
                justify="left",
                fg=theme_fg,
                bg=theme_bg,
                font=self._scaled_font(9),
            )
            lbl.grid(row=r, column=0, sticky="w", padx=16, pady=1)
            r += 1

        def _on_cfg_resize(evt):
            wrap = max(320, min(evt.width - 60, 1000))
            for child in card.winfo_children():
                if isinstance(child, tk.Label) and child is not tip_header:
                    child.config(wraplength=wrap)
        frame.bind("<Configure>", _on_cfg_resize)

    # ---------- Timers/Toggles tab ----------
    def _build_timers_tab(self, frame: ttk.Frame) -> None:
        # Theme-aware background color
        from config import load_theme
        _mc_theme = load_theme()
        _mc_bg = "#000000" if _mc_theme == "elite_orange" else "#1e1e1e"
        
        # Create a canvas and scrollbar for scrollable content
        canvas = tk.Canvas(frame, bg=_mc_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel to canvas for scrolling
        def _on_mousewheel_mc(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        # Bind mousewheel to canvas and all child widgets (except spinboxes)
        def _bind_mousewheel_recursive(widget):
            # Skip spinboxes and steppers - they have their own scroll handlers
            if isinstance(widget, (tk.Spinbox, Stepper)):
                return
            widget.bind("<MouseWheel>", _on_mousewheel_mc)
            for child in widget.winfo_children():
                _bind_mousewheel_recursive(child)
        
        # Bind to canvas and scrollable_frame initially
        canvas.bind("<MouseWheel>", _on_mousewheel_mc)
        scrollable_frame.bind("<MouseWheel>", _on_mousewheel_mc)
        
        # Rebind to all children after content is built
        def _bind_all_children():
            _bind_mousewheel_recursive(scrollable_frame)
        frame.after(100, _bind_all_children)
        
        # Now build content in scrollable_frame instead of frame
        scrollable_frame.columnconfigure(0, weight=1)
        
        # Theme-aware colors
        _toggle_bg = "#000000" if self.current_theme == "elite_orange" else "#1e1e1e"
        _toggle_fg = "#ff8c00" if self.current_theme == "elite_orange" else "#ffffff"
        _toggle_tip_fg = "#ffa500"
        _help_fg = "#888888" if self.current_theme == "elite_orange" else "gray"
        
        # Timer name translation mapping (English key -> translation key)
        timer_translations = {
            "Duration for firing mining lasers (standard)": "voiceattack.timer_laser_first",
            "Pause between mining cycles for weapon recharge/cooldown": "voiceattack.timer_pause",
            "Duration for repeated mining cycles (per cycle)": "voiceattack.timer_laser_extra",
            "Delay before targeting the prospector after launching": "voiceattack.timer_target",
            "Delay before retracting cargo scoop after mining sequence": "voiceattack.timer_cargoscoop",
            "Boost Interval (Core Mining)": "voiceattack.timer_boost",
            "FSD Jump Pause Timer": "voiceattack.timer_fsd_jump_pause",
            "FSD System Map Timer": "voiceattack.timer_fsd_system_map",
            "Continuous Prospector Sequence Timer": "voiceattack.timer_cont_prospector_seq",
        }

        # Timer help text translation mapping
        timer_help_translations = {
            "Duration for firing mining lasers (standard)": "voiceattack.help_timer_laser_first",
            "Pause between mining cycles for weapon recharge/cooldown": "voiceattack.help_timer_pause",
            "Duration for repeated mining cycles (per cycle)": "voiceattack.help_timer_laser_extra",
            "Delay before targeting the prospector after launching": "voiceattack.help_timer_target",
            "Delay before retracting cargo scoop after mining sequence": "voiceattack.help_timer_cargoscoop",
            "Boost Interval (Core Mining)": "voiceattack.help_timer_boost",
            "FSD Jump Pause Timer": "voiceattack.help_timer_fsd_jump_pause",
            "FSD System Map Timer": "voiceattack.help_timer_fsd_system_map",
            "Continuous Prospector Sequence Timer": "voiceattack.help_timer_cont_prospector_seq",
        }
        
        # Toggle help text translation mapping
        toggle_help_translations = {
            "Auto Honk": "voiceattack.help_auto_honk",
            "Cargo Scoop": "voiceattack.help_cargo_scoop",
            "Headtracker Docking Control": "voiceattack.help_headtracker",
            "Repeated Mining Cycles": "voiceattack.help_laser_extra",
            "Night Vision": "voiceattack.help_night_vision",
            "FSD Jump Sequence": "voiceattack.help_fsd_jump",
            "Open System Map": "voiceattack.help_open_system_map",
            "Prospector Sequence": "voiceattack.help_prospector_sequence",
            "Continuous Prospector Sequence": "voiceattack.help_continuous_prospector_sequence",
            "Prospector Sound Effect": "voiceattack.help_prospector_sound",
            "Target Prospector": "voiceattack.help_target_prospector",
            "Thrust Up": "voiceattack.help_thrust_up",
            "Pulse Wave Analyser": "voiceattack.help_pulse_wave",
            "Continuous Pulsewave": "voiceattack.help_continuous_pulsewave",
            "Auto Deselect Prospector": "voiceattack.help_auto_deselect_prospector",
            "Voice Feedback": "voiceattack.help_voice_feedback",
        }

        # Store checkbox widgets for dependent toggles
        self.toggle_checkboxes = {}
        
        r = 0
        
        # ============================================================
        # CONTROLS SECTION (simple toggles without sub-items)
        # ============================================================
        controls_header = ttk.Frame(scrollable_frame)
        controls_header.grid(row=r, column=0, sticky="ew")
        controls_header.columnconfigure(1, weight=1)
        
        ttk.Label(controls_header, text=t('voiceattack.timers'), font=self._scaled_font(11, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(controls_header, text=t('voiceattack.tip_stop_commands'), 
                 fg=_toggle_tip_fg, bg=_toggle_bg, font=self._scaled_font(8, "italic")).grid(row=0, column=1, sticky="")
        r += 1
        
        # Controls toggles: Headtracker, Night Vision
        controls_toggles = ["Headtracker Docking Control", "Night Vision"]

        for name in controls_toggles:
            if name not in TOGGLES:
                continue
            _fname, helptext = TOGGLES[name]

            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)

            # Create closure for auto-save
            def make_toggle_trace(toggle_name):
                return lambda *args: self._save_toggle(toggle_name)

            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name],
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                    highlightthickness=0, bd=0, font=self._scaled_font(9),
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")

            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", make_toggle_trace(name))

            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)

            r += 1

        # ============================================================
        # FSD JUMP SEQUENCE SUB-SECTION
        # ============================================================
        ttk.Label(scrollable_frame, text=t('voiceattack.section_fsd_jump'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(10, 2))
        r += 1

        fsd_section_toggles = ["FSD Jump Sequence"]

        for name in fsd_section_toggles:
            if name not in TOGGLES:
                continue
            _fname, helptext = TOGGLES[name]

            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)

            # Create closure for auto-save
            def make_fsd_toggle_trace(toggle_name):
                return lambda *args: self._save_toggle(toggle_name)

            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name],
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                    highlightthickness=0, bd=0, font=self._scaled_font(9),
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")

            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", make_fsd_toggle_trace(name))
            if name == "FSD Jump Sequence":
                self.toggle_vars[name].trace_add("write", lambda *args: self._update_fsdjump_dependencies())

            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            tooltip_help = t('voiceattack.tooltip_fsd_jump') if name == "FSD Jump Sequence" else display_help
            ToolTip(checkbox, tooltip_help)

            # Open System Map checkbox on the same row (depends on FSD Jump Sequence being enabled)
            if name == "FSD Jump Sequence" and "Open System Map" in TOGGLES:
                osm_name = "Open System Map"
                _osm_fname, osm_helptext = TOGGLES[osm_name]
                osm_display_help = t(toggle_help_translations.get(osm_name, osm_name)) if osm_name in toggle_help_translations else osm_helptext
                osm_checkbox = ThemedCheckbutton(rowf, text=osm_name, variable=self.toggle_vars[osm_name],
                                             bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                             activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                             highlightthickness=0, bd=0, font=self._scaled_font(9),
                                             padx=4, pady=2, anchor="w")
                osm_checkbox.pack(side="left", padx=(12, 0))
                self.toggle_checkboxes[osm_name] = osm_checkbox
                self.toggle_vars[osm_name].trace_add("write", lambda *args, n=osm_name: self._save_toggle(n))
                self.toggle_vars[osm_name].trace_add("write", lambda *args: self._update_fsdjump_dependencies())
                ToolTip(osm_checkbox, osm_display_help)

            r += 1

            # FSD Jump Sequence timers (indented, part of ship presets - matches its toggle)
            # "FSD System Map Timer" applies when Open System Map is checked;
            # "FSD Jump Pause Timer" applies when Open System Map is unchecked.
            if name == "FSD Jump Sequence":
                self.fsdjump_timer_spinboxes = {}
                for fsdjump_timer_name in ("FSD System Map Timer", "FSD Jump Pause Timer"):
                    if fsdjump_timer_name not in TIMERS:
                        continue
                    fsdjump_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                    fsdjump_frame.grid(row=r, column=0, sticky="w", pady=2)
                    tk.Label(fsdjump_frame, text="", bg=_toggle_bg, width=2).pack(side="left")

                    _fsdjump_fname, fsdjump_lo, fsdjump_hi, fsdjump_helptext = TIMERS[fsdjump_timer_name]

                    def make_trace_fsdjump(tn, fn, l, h):
                        return lambda *args: self._save_timer(tn, fn, l, h)

                    fsdjump_spinbox = self._make_stepper(fsdjump_frame, fsdjump_lo, fsdjump_hi,
                                                         self.timer_vars[fsdjump_timer_name], _toggle_bg, _toggle_fg)
                    fsdjump_spinbox.pack(side="left", padx=(4, 6))
                    self.fsdjump_timer_spinboxes[fsdjump_timer_name] = fsdjump_spinbox

                    self.timer_vars[fsdjump_timer_name].trace_add("write",
                        make_trace_fsdjump(fsdjump_timer_name, _fsdjump_fname, fsdjump_lo, fsdjump_hi))

                    fsdjump_display_name = t(timer_translations.get(fsdjump_timer_name, fsdjump_timer_name))
                    fsdjump_label = tk.Label(fsdjump_frame, text=f"{fsdjump_display_name} [{fsdjump_lo}..{fsdjump_hi}] {t('voiceattack.seconds')}",
                                              bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                    fsdjump_label.pack(side="left")

                    fsdjump_help = t(timer_help_translations.get(fsdjump_timer_name, fsdjump_timer_name))
                    ToolTip(fsdjump_label, fsdjump_help)
                    r += 1

                # Auto Honk (independent of FSD Jump Sequence)
                if "Auto Honk" in TOGGLES:
                    honk_name = "Auto Honk"
                    _honk_fname, honk_helptext = TOGGLES[honk_name]

                    honk_rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                    honk_rowf.grid(row=r, column=0, sticky="w", pady=2)

                    honk_checkbox = ThemedCheckbutton(honk_rowf, text=honk_name, variable=self.toggle_vars[honk_name],
                                            bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                            activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                            highlightthickness=0, bd=0, font=self._scaled_font(9),
                                            padx=4, pady=2, anchor="w")
                    honk_checkbox.pack(side="left")

                    self.toggle_checkboxes[honk_name] = honk_checkbox
                    self.toggle_vars[honk_name].trace_add("write", lambda *args, n=honk_name: self._save_toggle(n))

                    honk_display_help = t(toggle_help_translations.get(honk_name, honk_name)) if honk_name in toggle_help_translations else honk_helptext
                    ToolTip(honk_checkbox, honk_display_help)

                    r += 1

        # ============================================================
        # LASER MINING SUB-SECTION
        # ============================================================
        ttk.Label(scrollable_frame, text=t('voiceattack.section_laser_mining'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(10, 2))
        r += 1

        # Laser mining timers
        laser_timers = [
            "Boost Interval (Core Mining)",
            "Duration for firing mining lasers (standard)",
            "Duration for repeated mining cycles (per cycle)",
            "Pause between mining cycles for weapon recharge/cooldown",
        ]
        
        for name in laser_timers:
            if name not in TIMERS:
                continue
            _fname, lo, hi, helptext = TIMERS[name]
            
            rowf = ttk.Frame(scrollable_frame)
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            # Create closure with captured values for auto-save
            def make_trace_laser(tn, fn, l, h):
                return lambda *args: self._save_timer(tn, fn, l, h)
            
            self._make_stepper(rowf, lo, hi, self.timer_vars[name], _toggle_bg, _toggle_fg).pack(side="left")
            
            self.timer_vars[name].trace_add("write", make_trace_laser(name, _fname, lo, hi))
            
            display_name = t(timer_translations.get(name, name)) if name in timer_translations else name
            label = ttk.Label(rowf, text=f"{display_name} [{lo}..{hi}] {t('voiceattack.seconds')}")
            label.pack(side="left", padx=(6, 0))
            
            localized_help = t(timer_help_translations.get(name, name)) if name in timer_help_translations else helptext
            ToolTip(label, localized_help)
            r += 1
        
        # Repeated Mining Cycles toggle with repeat count
        if "Repeated Mining Cycles" in TOGGLES:
            name = "Repeated Mining Cycles"
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)
            
            r += 1
            
            # Repeat count spinbox (indented)
            repeat_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            repeat_frame.grid(row=r, column=0, sticky="w", pady=2)
            tk.Label(repeat_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
            
            # Use existing variable (initialized in __init__)
            # NOTE: Don't set up trace until AFTER import runs, to avoid overwriting saved values
            repeat_spinbox = self._make_stepper(repeat_frame, 1, 10, self.laser_extra_repeat_var, _toggle_bg, _toggle_fg,
                                                command=self._save_laser_extra_repeat)
            repeat_spinbox.pack(side="left", padx=(4, 6))
            self._laser_extra_spinbox = repeat_spinbox
            
            repeat_label = tk.Label(repeat_frame, text=f"{t('voiceattack.laser_extra_repeat_label')} [1..10]",
                                   bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
            repeat_label.pack(side="left")
            ToolTip(repeat_label, t('voiceattack.help_laser_extra_repeat'))
            
            self.laser_extra_status_label = tk.Label(repeat_frame, text="", fg=_help_fg, bg=_toggle_bg,
                                                      font=self._scaled_font(8, "italic"))
            self.laser_extra_status_label.pack(side="left", padx=(10, 0))
            # NOTE: Values loaded by _import_all_from_txt at startup, not here
            r += 1
        
        # Pulse Wave Analyser toggle (at end of Laser Mining section)
        if "Pulse Wave Analyser" in TOGGLES:
            name = "Pulse Wave Analyser"
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
            self.toggle_vars[name].trace_add("write", lambda *args: self._update_pulsewave_dependency())
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)

            # Continuous Pulsewave checkbox on the same row
            if "Continuous Pulsewave" in TOGGLES:
                cp_name = "Continuous Pulsewave"
                _cp_fname, cp_helptext = TOGGLES[cp_name]
                cp_display_help = t(toggle_help_translations.get(cp_name, cp_name)) if cp_name in toggle_help_translations else cp_helptext
                cp_checkbox = ThemedCheckbutton(rowf, text=cp_name, variable=self.toggle_vars[cp_name],
                                             bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                             activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                             highlightthickness=0, bd=0, font=self._scaled_font(9),
                                             padx=4, pady=2, anchor="w")
                cp_checkbox.pack(side="left", padx=(20, 0))
                self.toggle_checkboxes[cp_name] = cp_checkbox
                self.toggle_vars[cp_name].trace_add("write", lambda *args, n=cp_name: self._save_toggle(n))
                ToolTip(cp_checkbox, cp_display_help)

            r += 1
        
        ttk.Label(
            scrollable_frame, text=t('voiceattack.section_cargo_scoop_power'),
            font=self._scaled_font(10, "bold"),
        ).grid(row=r, column=0, sticky="w", pady=(10, 2))
        r += 1

        # Cargo Scoop toggle
        if "Cargo Scoop" in TOGGLES:
            name = "Cargo Scoop"
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)
            
            r += 1
            
            # Cargo scoop delay spinbox (indented)
            cargoscoop_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            cargoscoop_frame.grid(row=r, column=0, sticky="w", pady=2)
            tk.Label(cargoscoop_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
            
            cargoscoop_timer_name = "Delay before retracting cargo scoop after mining sequence"
            cargoscoop_spec = TIMERS.get(cargoscoop_timer_name)
            if cargoscoop_spec:
                _fname, lo, hi, _helptext = cargoscoop_spec
                
                # Create closure with captured values
                def make_trace_cargoscoop(tn, fn, l, h):
                    return lambda *args: self._save_timer(tn, fn, l, h)
                
                cargoscoop_spinbox = self._make_stepper(cargoscoop_frame, lo, hi, self.timer_vars[cargoscoop_timer_name],
                                                        _toggle_bg, _toggle_fg)
                cargoscoop_spinbox.pack(side="left", padx=(4, 6))
                
                self.timer_vars[cargoscoop_timer_name].trace_add("write", 
                    make_trace_cargoscoop(cargoscoop_timer_name, _fname, lo, hi))
                
                cargoscoop_display_name = t(timer_translations.get(cargoscoop_timer_name, cargoscoop_timer_name))
                cargoscoop_label = tk.Label(cargoscoop_frame, text=f"{cargoscoop_display_name} [{lo}..{hi}] {t('voiceattack.seconds')}",
                                           bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                cargoscoop_label.pack(side="left")
                
                cargoscoop_help = t(timer_help_translations.get(cargoscoop_timer_name, cargoscoop_timer_name))
                ToolTip(cargoscoop_label, cargoscoop_help)
            r += 1
        
        name = "Power Settings"
        rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
        rowf.grid(row=r, column=0, sticky="w", pady=2)
        label = ttk.Label(rowf, text=t("voiceattack.toggle_power"))
        label.pack(side="left", padx=(4, 8))
        power_selector = SegmentedSelector(
            rowf, [(0, t("voiceattack.power_balanced")), (1, t("voiceattack.power_max_engines")),
                   (2, t("voiceattack.power_max_shields"))], self.toggle_vars[name],
            bg=ttk.Style(rowf).lookup("Dark.TFrame", "background"), track=self.theme_colors["btn_bg"],
            fg=self.theme_colors["fg"], accent=slider_colors(self.current_theme)["accent"],
            font=self._scaled_font(8), scale=self._scaled_px(100) / 100)
        power_selector.pack(side="left")
        self._ship_diff_widgets.append((power_selector, "outline", "", (("Toggles", name),)))
        self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
        ToolTip(label, t("voiceattack.help_power"))
        ToolTip(power_selector, t("voiceattack.help_power"))
        r += 1
        
        # ============================================================
        # PROSPECTOR SUB-SECTION
        # ============================================================
        ttk.Label(scrollable_frame, text=t('voiceattack.section_prospector'), font=self._scaled_font(10, "bold")).grid(row=r, column=0, sticky="w", pady=(10, 2))
        r += 1
        
        # Prospector Sequence toggle
        if "Prospector Sequence" in TOGGLES:
            name = "Prospector Sequence"
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            
            self.toggle_vars[name].trace_add("write", lambda *args: self._update_prospector_dependencies())
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)

            # Continuous Prospector Sequence checkbox on the same row (compact, tooltip-only help)
            if "Continuous Prospector Sequence" in TOGGLES:
                cps_name = "Continuous Prospector Sequence"
                _cps_fname, cps_helptext = TOGGLES[cps_name]
                cps_display_help = t(toggle_help_translations.get(cps_name, cps_name)) if cps_name in toggle_help_translations else cps_helptext
                cps_checkbox = ThemedCheckbutton(rowf, text="Continuous Seq.", variable=self.toggle_vars[cps_name],
                                             bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg,
                                             activebackground=_toggle_bg, activeforeground=_toggle_fg,
                                             highlightthickness=0, bd=0, font=self._scaled_font(9),
                                             padx=4, pady=2, anchor="w")
                cps_checkbox.pack(side="left", padx=(12, 0))
                self.toggle_checkboxes[cps_name] = cps_checkbox
                self.toggle_vars[cps_name].trace_add("write", lambda *args, n=cps_name: self._save_toggle(n))
                self.toggle_vars[cps_name].trace_add("write", lambda *args: self._update_prospector_dependencies())
                ToolTip(cps_checkbox, cps_display_help)

            r += 1

            # Continuous Prospector Sequence timer (indented, under Continuous Seq. checkbox)
            if "Continuous Prospector Sequence Timer" in TIMERS:
                cpst_timer_name = "Continuous Prospector Sequence Timer"
                cpst_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                cpst_frame.grid(row=r, column=0, sticky="w", pady=2)
                tk.Label(cpst_frame, text="", bg=_toggle_bg, width=2).pack(side="left")

                _cpst_fname, cpst_lo, cpst_hi, cpst_helptext = TIMERS[cpst_timer_name]

                def make_trace_cpst(tn, fn, l, h):
                    return lambda *args: self._save_timer(tn, fn, l, h)

                cpst_spinbox = self._make_stepper(cpst_frame, cpst_lo, cpst_hi, self.timer_vars[cpst_timer_name],
                                                  _toggle_bg, _toggle_fg, increment=0.1)
                cpst_spinbox.pack(side="left", padx=(4, 6))
                self.cpst_spinbox = cpst_spinbox

                self.timer_vars[cpst_timer_name].trace_add("write",
                    make_trace_cpst(cpst_timer_name, _cpst_fname, cpst_lo, cpst_hi))

                cpst_display_name = t(timer_translations.get(cpst_timer_name, cpst_timer_name))
                cpst_label = tk.Label(cpst_frame, text=f"{cpst_display_name} [{cpst_lo}..{cpst_hi}] {t('voiceattack.seconds')}",
                                       bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                cpst_label.pack(side="left")
                self.cpst_label = cpst_label
                self._cpst_fg = _toggle_fg

                cpst_help = t(timer_help_translations.get(cpst_timer_name, cpst_timer_name))
                ToolTip(cpst_label, cpst_help)
                r += 1

            # Prospector cooldown time (indented)
            prospector_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            prospector_frame.grid(row=r, column=0, sticky="w", pady=2)
            tk.Label(prospector_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
            
            # Use existing variable (initialized in __init__)
            # NOTE: Don't set up trace during build - import will load values first
            prospector_spinbox = self._make_stepper(prospector_frame, 0.0, 6.0, self.prospector_delay_var, _toggle_bg,
                                                    _toggle_fg, increment=0.1, command=self._save_prospector_delay)
            prospector_spinbox.pack(side="left", padx=(4, 6))
            
            prospector_label = tk.Label(prospector_frame, text=f"{t('voiceattack.prospector_delay_label')} [0.0..6.0] seconds (default: 2.6s)",
                                       bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
            prospector_label.pack(side="left")
            self.prospector_cooldown_spinbox = prospector_spinbox
            self.prospector_cooldown_label = prospector_label

            ToolTip(prospector_label, t('voiceattack.help_prospector_delay_short'))
            
            # NOTE: Values loaded by _import_all_from_txt at startup
            r += 1
            self._update_prospector_dependencies()
        
        # Prospector dependent toggles: Prospector Sound Effect, Thrust Up (depend on Prospector Sequence)
        prospector_dependent_toggles = ["Prospector Sound Effect", "Thrust Up"]
        
        for name in prospector_dependent_toggles:
            if name not in TOGGLES:
                continue
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            # Indent dependent toggles
            tk.Label(rowf, text="", bg=_toggle_bg, width=2).pack(side="left")
            
            # Create closure for auto-save
            def make_dependent_trace(toggle_name):
                return lambda *args: self._save_toggle(toggle_name)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", make_dependent_trace(name))
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)
            
            r += 1
            
            # Thrust Up timing controls
            if name == "Thrust Up":
                # Key hold duration
                thrust_upduration_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                thrust_upduration_frame.grid(row=r, column=0, sticky="w", pady=2)
                tk.Label(thrust_upduration_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
                tk.Label(thrust_upduration_frame, text="", bg=_toggle_bg, width=2).pack(side="left")

                thrust_upduration_spinbox = self._make_stepper(thrust_upduration_frame, 0.5, 3.5, self.thrust_upduration_var, _toggle_bg, _toggle_fg,
                                                   increment=0.1, command=self._save_thrust_upduration)
                thrust_upduration_spinbox.pack(side="left", padx=(4, 6))

                thrust_upduration_label = tk.Label(thrust_upduration_frame, text=f"{t('voiceattack.thrust_upduration_label')} [0.5..3.5] seconds",
                                                   bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                thrust_upduration_label.pack(side="left")
                ToolTip(thrust_upduration_label, t('voiceattack.help_thrust_upduration'))

                r += 1

                # Scoop closed/retracted
                thrust_closed_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                thrust_closed_frame.grid(row=r, column=0, sticky="w", pady=2)
                tk.Label(thrust_closed_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
                tk.Label(thrust_closed_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
                
                # Use existing variable (initialized in __init__)
                # NOTE: Don't set up trace during build - import will load values first
                thrust_closed_spinbox = self._make_stepper(thrust_closed_frame, 0.0, 5.0, self.thrust_closed_var, _toggle_bg, _toggle_fg,
                                                   increment=0.1, command=self._save_thrust_closed)
                thrust_closed_spinbox.pack(side="left", padx=(4, 6))
                
                thrust_closed_label = tk.Label(thrust_closed_frame, text=f"{t('voiceattack.thrust_closed_label')} [0.0..5.0] seconds",
                                              bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                thrust_closed_label.pack(side="left")
                
                ToolTip(thrust_closed_label, t('voiceattack.help_thrust_closed'))
                
                # NOTE: Values loaded by _import_all_from_txt at startup
                r += 1
                
                # Scoop open/deployed
                thrust_open_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                thrust_open_frame.grid(row=r, column=0, sticky="w", pady=2)
                tk.Label(thrust_open_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
                tk.Label(thrust_open_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
                
                # Use existing variable (initialized in __init__)
                # NOTE: Don't set up trace during build - import will load values first
                thrust_open_spinbox = self._make_stepper(thrust_open_frame, 1.0, 5.0, self.thrust_open_var, _toggle_bg, _toggle_fg,
                                                   increment=0.1, command=self._save_thrust_open)
                thrust_open_spinbox.pack(side="left", padx=(4, 6))
                
                thrust_open_label = tk.Label(thrust_open_frame, text=f"{t('voiceattack.thrust_open_label')} [1.0..5.0] seconds",
                                            bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                thrust_open_label.pack(side="left")
                
                ToolTip(thrust_open_label, t('voiceattack.help_thrust_open'))
                
                # NOTE: Values loaded by _import_all_from_txt at startup
                r += 1
        
        # Target Prospector (independent toggle, not dependent on Prospector Sequence)
        if "Target Prospector" in TOGGLES:
            name = "Target Prospector"
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)
            
            r += 1
            
            # Delay before targeting the prospector after launching (indented under Target Prospector)
            target_timer_name = "Delay before targeting the prospector after launching"
            if target_timer_name in TIMERS:
                target_frame = ttk.Frame(scrollable_frame, style="Dark.TFrame")
                target_frame.grid(row=r, column=0, sticky="w", pady=2)
                tk.Label(target_frame, text="", bg=_toggle_bg, width=2).pack(side="left")
                
                _tfname, lo, hi, thelptext = TIMERS[target_timer_name]
                
                # Create closure with captured values for auto-save
                def make_trace_target(tn, fn, l, h):
                    return lambda *args: self._save_timer(tn, fn, l, h)
                
                target_spinbox = self._make_stepper(target_frame, lo, hi, self.timer_vars[target_timer_name],
                                                    _toggle_bg, _toggle_fg)
                target_spinbox.pack(side="left", padx=(4, 6))
                
                self.timer_vars[target_timer_name].trace_add("write", make_trace_target(target_timer_name, _tfname, lo, hi))
                
                target_display_name = t(timer_translations.get(target_timer_name, target_timer_name))
                target_label = tk.Label(target_frame, text=f"{target_display_name} [{lo}..{hi}] {t('voiceattack.seconds')}",
                                       bg=_toggle_bg, fg=_toggle_fg, font=self._scaled_font(9))
                target_label.pack(side="left")
                
                target_help = t(timer_help_translations.get(target_timer_name, target_timer_name))
                ToolTip(target_label, target_help)
                r += 1
        
        # Auto Deselect Prospector toggle (placed in Prospector section)
        if "Auto Deselect Prospector" in TOGGLES:
            name = "Auto Deselect Prospector"
            _fname, helptext = TOGGLES[name]
            
            rowf = ttk.Frame(scrollable_frame, style="Dark.TFrame")
            rowf.grid(row=r, column=0, sticky="w", pady=2)
            
            checkbox = ThemedCheckbutton(rowf, text=name, variable=self.toggle_vars[name], 
                                    bg=_toggle_bg, fg=_toggle_fg, selectcolor=_toggle_bg, 
                                    activebackground=_toggle_bg, activeforeground=_toggle_fg, 
                                    highlightthickness=0, bd=0, font=self._scaled_font(9), 
                                    padx=4, pady=2, anchor="w")
            checkbox.pack(side="left")
            self.toggle_checkboxes[name] = checkbox
            self.toggle_vars[name].trace_add("write", lambda *args, n=name: self._save_toggle(n))
            
            display_help = t(toggle_help_translations.get(name, name)) if name in toggle_help_translations else helptext
            ToolTip(checkbox, display_help)
            
            r += 1
        
        # Initialize dependent toggle states AFTER import has a chance to load values
        # Import runs at 100ms, so we delay this to 150ms
        self.after(150, self._update_prospector_dependencies)
        self.after(150, lambda: self._update_pulsewave_dependency(reset_value=False))
        self.after(150, self._update_fsdjump_dependencies)
        self._ship_register_diff_widgets(scrollable_frame)
